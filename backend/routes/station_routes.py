import math
from flask import Blueprint, jsonify
from decimal import Decimal
from backend.database.db_config import get_db_connection
from backend.routes.auth_routes import login_required

station_bp = Blueprint("station_bp", __name__)

def serialize_station(row):
    """Convert MySQL row dictionary to a JSON-safe dictionary with numeric types."""
    dist = row.get("distance_km")
    cap = row.get("capacity_kw")
    lat = row.get("latitude")
    lng = row.get("longitude")
    return {
        "station_id": row.get("station_id"),
        "station_name": row.get("station_name"),
        "location": row.get("location"),
        "distance_km": float(dist) if isinstance(dist, Decimal) else dist,
        "charger_type": row.get("charger_type"),
        "capacity_kw": float(cap) if isinstance(cap, Decimal) else cap,
        "available_ports": row.get("available_ports"),
        "total_ports": row.get("total_ports"),
        "estimated_wait_minutes": row.get("estimated_wait_minutes"),
        "demand_level": row.get("demand_level"),
        "latitude": float(lat) if isinstance(lat, Decimal) else lat,
        "longitude": float(lng) if isinstance(lng, Decimal) else lng
    }

@station_bp.route("/api/health", methods=["GET"])
def health_check():
    """Verify that backend server and database connection are operational."""
    db_status = "disconnected"
    conn = get_db_connection()
    if conn and conn.is_connected():
        db_status = "connected"
        conn.close()

    return jsonify({
        "status": "healthy",
        "service": "ChargeFindr AI Backend",
        "database": db_status
    }), 200

@station_bp.route("/api/stations", methods=["GET"])
@login_required
def get_all_stations():
    """Retrieve all charging stations from MySQL database."""
    conn = get_db_connection()
    if not conn:
        return jsonify({
            "success": False,
            "error": "Database connection failed. Ensure MySQL is running."
        }), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM charging_stations ORDER BY station_id ASC;")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        stations = [serialize_station(row) for row in rows]
        return jsonify({
            "success": True,
            "count": len(stations),
            "data": stations,
            "note": "Sample demonstration records from local MySQL database"
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({
            "success": False,
            "error": f"Failed to fetch stations: {str(e)}"
        }), 500

@station_bp.route("/api/stations/locations", methods=["GET"])
@login_required
def get_distinct_locations():
    """Retrieve distinct station locations from MySQL database."""
    conn = get_db_connection()
    if not conn:
        return jsonify({
            "success": False,
            "error": "Database connection failed. Ensure MySQL is running."
        }), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT DISTINCT location FROM charging_stations "
            "WHERE location IS NOT NULL AND TRIM(location) <> '' "
            "ORDER BY location ASC;"
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        locations = [row["location"] for row in rows]
        return jsonify({
            "success": True,
            "count": len(locations),
            "data": locations
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({
            "success": False,
            "error": f"Failed to fetch locations: {str(e)}"
        }), 500

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two GPS coordinates in kilometers
    using the Haversine formula.
    Returns None if any coordinate is missing, invalid, or out of mathematical range.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        if not (-90.0 <= lat1 <= 90.0 and -90.0 <= lat2 <= 90.0 and -180.0 <= lon1 <= 180.0 and -180.0 <= lon2 <= 180.0):
            return None
        r = 6371.0  # Mean radius of Earth in km
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(r * c, 2)
    except (ValueError, TypeError):
        return None

def select_alternative_station(congested_station, all_stations):
    """
    Select and rank the optimal alternative charging station for a congested station.
    Priorities:
    1. Prefer alternatives with the same charger type as the congested station.
    2. If no compatible alternative exists, use a different charger type only as a fallback.
       Never claim the charging speed is equivalent.
    3. Rank suitable alternatives using the actual Haversine distance between coordinates.
    4. Allow a station with at least one available port (>= 1) as a fallback when no station
       with more available ports (> 1) qualifies.
    5. Never recommend the congested station itself.
    Returns: tuple (best_alt, is_fallback, haversine_km)
    """
    c_id = congested_station.get("station_id")
    c_type = (congested_station.get("charger_type") or "").strip().lower()
    c_lat = congested_station.get("latitude")
    c_lng = congested_station.get("longitude")

    candidates = []
    for s in all_stations:
        # Never recommend the congested station itself
        if s.get("station_id") == c_id:
            continue

        avail = s.get("available_ports")
        wait = s.get("estimated_wait_minutes")

        # Must have at least 1 available port
        if avail is None or avail < 1:
            continue

        # Must have low queue time (<= 8 mins)
        if wait is None or wait > 8 or wait < 0:
            continue

        # Calculate actual Haversine distance between station coordinates
        dist = calculate_haversine_distance(c_lat, c_lng, s.get("latitude"), s.get("longitude"))
        # Safe fallback distance if coordinates are absent
        if dist is None:
            c_dist = congested_station.get("distance_km")
            s_dist = s.get("distance_km")
            if c_dist is not None and s_dist is not None:
                try:
                    dist = round(abs(float(s_dist) - float(c_dist)), 2)
                except (ValueError, TypeError):
                    dist = float(s_dist) if s_dist is not None else 999.0
            else:
                dist = float(s.get("distance_km") or 999.0)

        s_type = (s.get("charger_type") or "").strip().lower()
        is_same_type = (s_type == c_type) and bool(c_type)

        candidates.append({
            "station": s,
            "available_ports": avail,
            "wait_minutes": wait,
            "haversine_km": dist,
            "is_same_type": is_same_type
        })

    if not candidates:
        return None, False, None

    # Partition candidates by charger type compatibility
    same_type_candidates = [item for item in candidates if item["is_same_type"]]
    other_type_candidates = [item for item in candidates if not item["is_same_type"]]

    def sort_pool(pool):
        # 1. Primary: available_ports > 1 preferred over available_ports == 1
        # 2. Shortest Haversine distance ascending
        # 3. Lowest wait time ascending
        # 4. Highest available ports descending
        # 5. Station ID ascending (deterministic)
        return sorted(
            pool,
            key=lambda item: (
                0 if item["available_ports"] > 1 else 1,
                item["haversine_km"] if item["haversine_km"] is not None else 999.0,
                item["wait_minutes"] if item["wait_minutes"] is not None else 999,
                -item["available_ports"],
                item["station"].get("station_id") or 999
            )
        )

    if same_type_candidates:
        sorted_same = sort_pool(same_type_candidates)
        best = sorted_same[0]
        return best["station"], False, best["haversine_km"]

    # Fallback to different charger type only when no compatible alternative exists
    sorted_other = sort_pool(other_type_candidates)
    best = sorted_other[0]
    return best["station"], True, best["haversine_km"]

@station_bp.route("/api/stations/alerts", methods=["GET"])
@login_required
def get_station_alerts():
    """Retrieve congestion alerts and recommended low-wait alternative stations."""
    conn = get_db_connection()
    if not conn:
        return jsonify({
            "success": False,
            "has_alert": False,
            "count": 0,
            "alerts": [],
            "is_sample_data": True,
            "error": "Database connection failed. Ensure MySQL is running."
        }), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM charging_stations ORDER BY station_id ASC;")
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return jsonify({
                "success": True,
                "has_alert": False,
                "count": 0,
                "alerts": [],
                "is_sample_data": True,
                "note": "No charging stations found in database."
            }), 200

        stations = [serialize_station(row) for row in rows]

        # Congested station criteria: available_ports == 0 OR estimated_wait_minutes > 20
        congested_stations = [
            s for s in stations
            if (s.get("available_ports") is not None and s.get("available_ports") == 0)
            or (s.get("estimated_wait_minutes") is not None and s.get("estimated_wait_minutes") > 20)
        ]

        alerts = []
        for c in congested_stations:
            alt, is_fallback, haversine_km = select_alternative_station(c, stations)

            # Determine human-readable congestion reasons safely
            reasons = []
            avail = c.get("available_ports")
            wait = c.get("estimated_wait_minutes")

            if avail is not None and avail == 0:
                reasons.append("0 available ports")
            elif avail is None:
                reasons.append("unknown port availability")
            elif avail < 0:
                reasons.append("invalid port status")

            if wait is not None and wait > 20:
                reasons.append(f"long queue with {wait} mins wait")
            elif wait is None and (avail is None or avail == 0):
                reasons.append("unverified queue status")

            reason_str = " and ".join(reasons) if reasons else "high demand congestion"

            if alt:
                alt_ports = alt.get("available_ports")
                alt_wait = alt.get("estimated_wait_minutes")
                alt_ports_text = f"{alt_ports} available ports" if alt_ports is not None else "available ports"
                alt_wait_text = f"~{alt_wait} min wait" if alt_wait is not None else "minimal queue"
                dist_suffix = f", ~{haversine_km} km away" if haversine_km is not None else ""

                if is_fallback:
                    c_type = c.get("charger_type") or "primary"
                    alt_type = alt.get("charger_type") or "alternative"
                    message = (
                        f"Notice: {c.get('station_name')} ({c.get('location')}) is currently congested ({reason_str}). "
                        f"No low-wait {c_type} stations available. "
                        f"Fallback alternative: {alt.get('station_name')} ({alt.get('location')}) "
                        f"with {alt_ports_text} ({alt_wait_text}{dist_suffix}). "
                        f"Note: This station provides {alt_type} charging, which differs in charging speed from {c_type}."
                    )
                else:
                    message = (
                        f"Notice: {c.get('station_name')} ({c.get('location')}) is currently congested ({reason_str}). "
                        f"Recommend re-routing to {alt.get('station_name')} ({alt.get('location')}) "
                        f"with {alt_ports_text} ({alt_wait_text}{dist_suffix})."
                    )
            else:
                message = (
                    f"Notice: {c.get('station_name')} ({c.get('location')}) is currently congested ({reason_str}). "
                    f"No low-wait alternative currently available (<= 8 mins wait)."
                )

            alerts.append({
                "congested_station": {
                    "station_id": c.get("station_id"),
                    "station_name": c.get("station_name"),
                    "location": c.get("location"),
                    "charger_type": c.get("charger_type"),
                    "capacity_kw": c.get("capacity_kw"),
                    "available_ports": c.get("available_ports"),
                    "total_ports": c.get("total_ports"),
                    "estimated_wait_minutes": c.get("estimated_wait_minutes"),
                    "demand_level": c.get("demand_level"),
                    "latitude": c.get("latitude"),
                    "longitude": c.get("longitude"),
                    "reason": reason_str
                },
                "recommended_alternative": {
                    "station_id": alt.get("station_id"),
                    "station_name": alt.get("station_name"),
                    "location": alt.get("location"),
                    "charger_type": alt.get("charger_type"),
                    "capacity_kw": alt.get("capacity_kw"),
                    "available_ports": alt.get("available_ports"),
                    "total_ports": alt.get("total_ports"),
                    "estimated_wait_minutes": alt.get("estimated_wait_minutes"),
                    "demand_level": alt.get("demand_level"),
                    "latitude": alt.get("latitude"),
                    "longitude": alt.get("longitude"),
                    "distance_km": alt.get("distance_km"),
                    "distance_between_km": haversine_km,
                    "is_same_charger_type": not is_fallback,
                    "is_charger_fallback": is_fallback
                } if alt else None,
                "message": message
            })

        return jsonify({
            "success": True,
            "has_alert": len(alerts) > 0,
            "count": len(alerts),
            "alerts": alerts,
            "is_sample_data": True,
            "note": "Station availability and wait times are stored demonstration records, not live IoT telemetry."
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "has_alert": False,
            "count": 0,
            "alerts": [],
            "is_sample_data": True,
            "error": f"Failed to compute station alerts: {str(e)}"
        }), 500
    finally:
        if conn and conn.is_connected():
            conn.close()



