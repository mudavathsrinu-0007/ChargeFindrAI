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

    available_ports = station.get("available_ports", 0)
    total_ports = max(station.get("total_ports", 1), 1)
    wait_minutes = station.get("estimated_wait_minutes", 0)
    distance_km = float(station.get("distance_km", 99.0))
    capacity_kw = float(station.get("capacity_kw", 0.0))
    charger_type = station.get("charger_type", "")
    demand_level = station.get("demand_level", "Medium")
    location = station.get("location", "")

    # 1. Availability Evaluation (Weight: up to 35 points)
    if available_ports > 0:
        avail_ratio = available_ports / total_ports
        avail_points = 20.0 + (avail_ratio * 15.0)
        score += avail_points
        reasons.append(f"{available_ports} of {total_ports} ports currently available")
    else:
        score += 0.0
        reasons.append("Currently congested: 0 ports available")

    # 2. Wait Time Evaluation (Weight: up to 25 points)
    # Shorter wait time earns more points
    wait_penalty = min(wait_minutes * 1.0, 25.0)
    wait_points = max(0.0, 25.0 - wait_penalty)
    score += wait_points
    if wait_minutes <= 10:
        reasons.append(f"Low wait time estimated at {wait_minutes} mins")
    else:
        reasons.append(f"Expected wait time of {wait_minutes} mins")

    # 3. Distance & Area Proximity (Weight: up to 20 points)
    dist_penalty = min(distance_km * 2.5, 20.0)
    dist_points = max(0.0, 20.0 - dist_penalty)
    score += dist_points

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
        reasons.append("Low demand station (smooth turnaround)")
    elif demand_level.lower() == "high":
        score -= 5.0

    # User priority weighting adjustment
    if priority == "fastest_charger" and "fast" in charger_type.lower():
        score += 10.0
    elif priority == "shortest_wait" and wait_minutes <= 10:
        score += 10.0

    final_score = round(max(0.0, min(100.0, score)), 1)
    return final_score, reasons


def get_station_recommendations(criteria=None):
    """
    Fetch all stations from MySQL, apply scoring, and rank them.
    Filters out or demotes congested stations appropriately.
    """
    if criteria is None:
        criteria = {}

    preferred_area = criteria.get("location", "Any")
    preferred_charger = criteria.get("charger_type", "Any")
    priority = criteria.get("priority", "balanced")

    conn = get_db_connection()
    if not conn:
        raise Exception("Database connection failed while fetching stations for recommendation.")

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM charging_stations;")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    ranked_stations = []
    for row in rows:
        station = {
            "station_id": row["station_id"],
            "station_name": row["station_name"],
            "location": row["location"],
            "distance_km": float(row["distance_km"]) if isinstance(row["distance_km"], Decimal) else float(row["distance_km"] or 0),
            "charger_type": row["charger_type"],
            "capacity_kw": float(row["capacity_kw"]) if isinstance(row["capacity_kw"], Decimal) else float(row["capacity_kw"] or 0),
            "available_ports": int(row["available_ports"]),
            "total_ports": int(row["total_ports"]),
            "estimated_wait_minutes": int(row["estimated_wait_minutes"]),
            "demand_level": row["demand_level"],
            "latitude": float(row["latitude"]) if isinstance(row.get("latitude"), Decimal) else row.get("latitude"),
            "longitude": float(row["longitude"]) if isinstance(row.get("longitude"), Decimal) else row.get("longitude")
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
        ranked_stations.append(station)

    # Rank highest score first. If tied, sort by wait minutes ascending
    ranked_stations.sort(key=lambda s: (-s["recommendation_score"], s["estimated_wait_minutes"]))

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

