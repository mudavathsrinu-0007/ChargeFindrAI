from flask import Blueprint, jsonify
from decimal import Decimal
from backend.database.db_config import get_db_connection

station_bp = Blueprint("station_bp", __name__)

def serialize_station(row):
    """Convert MySQL row dictionary to a JSON-safe dictionary with numeric types."""
    return {
        "station_id": row.get("station_id"),
        "station_name": row.get("station_name"),
        "location": row.get("location"),
        "distance_km": float(row["distance_km"]) if isinstance(row.get("distance_km"), Decimal) else row.get("distance_km"),
        "charger_type": row.get("charger_type"),
        "capacity_kw": float(row["capacity_kw"]) if isinstance(row.get("capacity_kw"), Decimal) else row.get("capacity_kw"),
        "available_ports": row.get("available_ports"),
        "total_ports": row.get("total_ports"),
        "estimated_wait_minutes": row.get("estimated_wait_minutes"),
        "demand_level": row.get("demand_level"),
        "latitude": float(row["latitude"]) if isinstance(row.get("latitude"), Decimal) else row.get("latitude"),
        "longitude": float(row["longitude"]) if isinstance(row.get("longitude"), Decimal) else row.get("longitude")
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

@station_bp.route("/api/stations/alerts", methods=["GET"])
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
        conn.close()

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

        # Eligible alternative criteria: available_ports > 1 AND estimated_wait_minutes <= 8
        eligible_alternatives = [
            s for s in stations
            if (s.get("available_ports") is not None and s.get("available_ports") > 1)
            and (s.get("estimated_wait_minutes") is not None and s.get("estimated_wait_minutes") <= 8)
        ]
        # Sort candidates by lowest wait time, highest available ports, then distance
        eligible_alternatives.sort(
            key=lambda s: (
                s.get("estimated_wait_minutes") if s.get("estimated_wait_minutes") is not None else 999,
                -(s.get("available_ports") if s.get("available_ports") is not None else 0),
                s.get("distance_km") if s.get("distance_km") is not None else 999.0
            )
        )

        alerts = []
        for c in congested_stations:
            # Recommend an alternative only if eligible and never the congested station itself
            alt = next(
                (a for a in eligible_alternatives if a.get("station_id") != c.get("station_id")),
                None
            )

            # Determine human-readable congestion reasons
            reasons = []
            if c.get("available_ports") == 0:
                reasons.append("0 available ports")
            if c.get("estimated_wait_minutes") is not None and c["estimated_wait_minutes"] > 20:
                reasons.append(f"long queue with {c['estimated_wait_minutes']} mins wait")
            reason_str = " and ".join(reasons) if reasons else "high demand congestion"

            if alt:
                message = (
                    f"Notice: {c.get('station_name')} ({c.get('location')}) is currently congested ({reason_str}). "
                    f"Recommend re-routing to {alt.get('station_name')} ({alt.get('location')}) "
                    f"with {alt.get('available_ports')} available ports (~{alt.get('estimated_wait_minutes')} min wait)."
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
                    "available_ports": c.get("available_ports"),
                    "total_ports": c.get("total_ports"),
                    "estimated_wait_minutes": c.get("estimated_wait_minutes"),
                    "demand_level": c.get("demand_level"),
                    "reason": reason_str
                },
                "recommended_alternative": {
                    "station_id": alt.get("station_id"),
                    "station_name": alt.get("station_name"),
                    "location": alt.get("location"),
                    "available_ports": alt.get("available_ports"),
                    "total_ports": alt.get("total_ports"),
                    "estimated_wait_minutes": alt.get("estimated_wait_minutes"),
                    "demand_level": alt.get("demand_level")
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
        if conn and conn.is_connected():
            conn.close()
        return jsonify({
            "success": False,
            "has_alert": False,
            "count": 0,
            "alerts": [],
            "is_sample_data": True,
            "error": f"Failed to compute station alerts: {str(e)}"
        }), 500



