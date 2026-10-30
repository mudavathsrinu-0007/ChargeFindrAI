from decimal import Decimal
from backend.database.db_config import get_db_connection

def calculate_station_score(station, preferred_charger="Any", preferred_area="Any", priority="balanced"):
    """
    Multi-criteria ranking function for EV charging stations.
    Considers port availability, distance, waiting time, charger type compatibility, and demand.
    Returns a score out of 100 and a list of human-readable explanation bullet points.
    """
    score = 0.0
    reasons = []

    raw_avail = station.get("available_ports")
    raw_total = station.get("total_ports")
    raw_wait = station.get("estimated_wait_minutes")
    raw_dist = station.get("distance_km")
    raw_cap = station.get("capacity_kw")
    raw_demand = station.get("demand_level")
    raw_location = station.get("location")
    raw_charger = station.get("charger_type")

    # Safe numeric bounding: total_ports >= 1, 0 <= available_ports <= total_ports
    total_ports = max(1, int(raw_total) if raw_total is not None and int(raw_total) > 0 else 1)
    available_ports = max(0, int(raw_avail) if raw_avail is not None else 0)
    available_ports = min(available_ports, total_ports)

    # Distinguish known wait time from missing/unreported wait time
    has_known_wait = raw_wait is not None and raw_wait != ""
    wait_minutes = max(0, int(raw_wait)) if has_known_wait else None

    # Safe non-negative distance
    has_known_dist = raw_dist is not None and raw_dist != ""
    distance_km = max(0.0, float(raw_dist)) if has_known_dist else 99.0

    # Safe non-negative capacity
    capacity_kw = max(0.0, float(raw_cap)) if raw_cap is not None and raw_cap != "" else 0.0

    charger_type = str(raw_charger or "").strip()
    demand_level = str(raw_demand or "Medium").strip()
    location = str(raw_location or "").strip()
    preferred_charger = str(preferred_charger or "Any").strip()
    preferred_area = str(preferred_area or "Any").strip()
    priority = str(priority or "balanced").strip().lower()

    # 1. Availability Evaluation (Weight: up to 35 points)
    if available_ports > 0:
        avail_ratio = available_ports / total_ports
        avail_points = 20.0 + (avail_ratio * 15.0)
        score += avail_points
        reasons.append(f"{available_ports} of {total_ports} ports currently available")
    else:
        # Congestion penalty: ensures a zero-port station does not outrank comparable open stations merely due to distance
        score -= 20.0
        reasons.append("Currently congested: 0 ports available (-20 congestion penalty)")

    # 2. Wait Time Evaluation (Weight: up to 25 points)
    if has_known_wait:
        wait_penalty = min(wait_minutes * 1.0, 25.0)
        wait_points = max(0.0, 25.0 - wait_penalty)
        score += wait_points
        if wait_minutes <= 10:
            reasons.append(f"Low wait time estimated at {wait_minutes} mins")
        else:
            reasons.append(f"Expected wait time of {wait_minutes} mins")
    else:
        # Do not claim unknown wait time is zero; award neutral baseline
        score += 10.0
        reasons.append("Wait time unknown: estimated queue time not reported")

    # 3. Distance & Area Proximity (Weight: up to 20 points + 10 target area bonus)
    dist_penalty = min(distance_km * 2.5, 20.0)
    dist_points = max(0.0, 20.0 - dist_penalty)
    score += dist_points

    if has_known_dist:
        if distance_km <= 3.0:
            reasons.append(f"Close proximity ({distance_km:.1f} km away)")
        elif distance_km > 10.0:
            reasons.append(f"Farther distance ({distance_km:.1f} km away)")
    else:
        reasons.append("Distance unknown (standard default applied)")

    if preferred_area and preferred_area.lower() != "any":
        if preferred_area.lower() in location.lower():
            score += 10.0
            reasons.append(f"Located directly in your target area ({preferred_area})")

    # 4. Charger Type & Capacity Compatibility (Weight: up to 20 points)
    if preferred_charger and preferred_charger.lower() != "any":
        if preferred_charger.lower() in charger_type.lower():
            score += 15.0
            reasons.append(f"Matches preferred charger type ({charger_type})")
        else:
            reasons.append(f"Alternative charger type ({charger_type})")
    else:
        # Default bonus for higher charging power
        score += min(capacity_kw / 10.0, 15.0)
        reasons.append(f"Charging power: {capacity_kw} kW")

    # 5. Demand Level Adjustment
    if demand_level.lower() == "low":
        score += 5.0
        reasons.append("Low demand station (smooth turnaround, +5 bonus)")
    elif demand_level.lower() == "high":
        score -= 5.0
        reasons.append("High demand station (possible queue buildup, -5 penalty)")

    # 6. User priority weighting adjustment with full transparent explanations
    if priority == "fastest_charger" and "fast" in charger_type.lower():
        score += 10.0
        reasons.append("Priority bonus: fast charging power matched (+10 bonus)")
    elif priority == "shortest_wait" and (wait_minutes is not None and wait_minutes <= 10):
        score += 10.0
        reasons.append(f"Priority bonus: low queue wait ({wait_minutes} mins, +10 bonus)")

    final_score = round(max(0.0, min(100.0, score)), 1)
    return final_score, reasons


def get_station_recommendations(criteria=None):
    """
    Fetch all stations from MySQL, apply scoring, and rank them.
    Filters out or demotes congested stations appropriately.
    """
    if criteria is None:
        criteria = {}

    preferred_area = str(criteria.get("location") or "Any").strip()
    preferred_charger = str(criteria.get("charger_type") or "Any").strip()
    priority = str(criteria.get("priority") or "balanced").strip().lower()

    conn = get_db_connection()
    if not conn:
        raise Exception("Database connection failed while fetching stations for recommendation.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM charging_stations ORDER BY station_id ASC;")
        rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()

    ranked_stations = []
    for row in rows:
        raw_avail = row.get("available_ports")
        raw_total = row.get("total_ports")
        raw_wait = row.get("estimated_wait_minutes")
        raw_dist = row.get("distance_km")
        raw_cap = row.get("capacity_kw")
        raw_lat = row.get("latitude")
        raw_lng = row.get("longitude")

        total_ports = max(1, int(raw_total) if raw_total is not None and int(raw_total) > 0 else 1)
        avail_ports = max(0, int(raw_avail)) if raw_avail is not None else 0
        avail_ports = min(avail_ports, total_ports)

        station = {
            "station_id": row.get("station_id"),
            "station_name": str(row.get("station_name") or "Unknown Station"),
            "location": str(row.get("location") or "Unspecified Location"),
            "distance_km": float(raw_dist) if isinstance(raw_dist, Decimal) else float(raw_dist if raw_dist is not None else 99.0),
            "charger_type": str(row.get("charger_type") or "Standard AC"),
            "capacity_kw": float(raw_cap) if isinstance(raw_cap, Decimal) else float(raw_cap if raw_cap is not None else 0.0),
            "available_ports": avail_ports,
            "total_ports": total_ports,
            "estimated_wait_minutes": int(raw_wait) if raw_wait is not None else None,
            "demand_level": str(row.get("demand_level") or "Medium"),
            "latitude": float(raw_lat) if isinstance(raw_lat, Decimal) else raw_lat,
            "longitude": float(raw_lng) if isinstance(raw_lng, Decimal) else raw_lng
        }

        score, reasons = calculate_station_score(
            station,
            preferred_charger=preferred_charger,
            preferred_area=preferred_area,
            priority=priority
        )

        station["recommendation_score"] = score
        station["reasons"] = reasons
        station["is_available"] = station["available_ports"] > 0
        # Present 0 if wait time was null for backwards-compatible JSON schema
        if station["estimated_wait_minutes"] is None:
            station["estimated_wait_minutes"] = 0

        ranked_stations.append(station)

    # Rank highest score first.
    # Deterministic tie-breakers: score desc, wait mins asc, distance asc, station_id asc
    ranked_stations.sort(key=lambda s: (
        -s["recommendation_score"],
        s["estimated_wait_minutes"] if s.get("estimated_wait_minutes") is not None else 999,
        s["distance_km"] if s.get("distance_km") is not None else 999.0,
        s["station_id"] if s.get("station_id") is not None else 0
    ))

    for index, s in enumerate(ranked_stations, start=1):
        s["rank"] = index

    return {
        "user_criteria": {
            "location": preferred_area,
            "charger_type": preferred_charger,
            "priority": priority
        },
        "total_evaluated": len(ranked_stations),
        "recommendations": ranked_stations,
        "disclaimer": "Sample demonstration data. Distances and availability are demonstration values."
    }

