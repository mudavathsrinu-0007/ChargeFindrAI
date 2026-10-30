import re
import secrets
from datetime import datetime, timedelta
from mysql.connector import Error
from backend.database.db_config import get_db_connection

def normalize_reg_number(reg_str):
    """Normalize vehicle registration number."""
    if not reg_str:
        return ""
    return re.sub(r'[^A-Za-z0-9]', '', reg_str).upper()

def get_station_queue_status(station_id):
    """
    Get live queue metrics for a specific charging station.
    Calculates waiting drivers, active charging sessions, and estimated wait times
    based exclusively on dedicated WALKIN ports.
    """
    try:
        station_id = int(station_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid station ID."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch station metadata
        cursor.execute("""
            SELECT station_id, station_name, location, total_ports, charger_type
            FROM charging_stations
            WHERE station_id = %s
        """, (station_id,))
        station = cursor.fetchone()

        if not station:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Station #{station_id} not found."}, 404

        # 2. Count dedicated walk-in ports
        cursor.execute("""
            SELECT COUNT(*) AS walkin_ports
            FROM station_chargers
            WHERE station_id = %s AND allocation_type = 'WALKIN' AND status != 'MAINTENANCE'
        """, (station_id,))
        walkin_ports = cursor.fetchone()["walkin_ports"] or 0

        # 3. Count waiting and active charging queue tickets
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN status = 'WAITING' THEN 1 ELSE 0 END) AS waiting_count,
                SUM(CASE WHEN status IN ('READY', 'CHARGING') THEN 1 ELSE 0 END) AS active_charging_count
            FROM walkin_queue
            WHERE station_id = %s;
        """, (station_id,))
        counts = cursor.fetchone()
        waiting_count = int(counts["waiting_count"] or 0)
        active_charging_count = int(counts["active_charging_count"] or 0)

        cursor.close()
        conn.close()

        # Calculate estimated wait time for next driver in line
        # Assuming ~15 minutes per rapid walk-in charging session per port
        if waiting_count == 0:
            estimated_wait = 0
        else:
            effective_ports = max(walkin_ports, 1)
            estimated_wait = max(5, int((waiting_count * 15) / effective_ports))

        return {
            "success": True,
            "station_id": station_id,
            "station_name": station["station_name"],
            "location": station["location"],
            "charger_type": station["charger_type"],
            "walkin_ports": walkin_ports,
            "waiting_count": waiting_count,
            "active_charging_count": active_charging_count,
            "estimated_wait_minutes": estimated_wait
        }, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to retrieve queue status: {str(e)}"}, 500

def join_queue(user_id, data):
    """
    Join the rapid walk-in queue for an EV charging station.
    - FIFO ordering strictly enforced.
    - Prevents duplicate active tickets across stations for the same user (HTTP 409).
    - Allocates ticket from dedicated walk-in capacity.
    """
    if not user_id:
        return {"success": False, "error": "Authentication required."}, 401

    station_id = data.get("station_id")
    driver_name = str(data.get("driver_name", "")).strip()
    vehicle_model = str(data.get("vehicle_model", "")).strip()
    vehicle_reg_raw = str(data.get("vehicle_reg_number", "")).strip()
    charger_type = str(data.get("charger_type", "")).strip()

    # Validations
    if not station_id:
        return {"success": False, "error": "Station selection is required."}, 400

    if not driver_name or len(driver_name) < 2 or len(driver_name) > 100:
        return {"success": False, "error": "Driver full name must be between 2 and 100 characters."}, 400

    if not vehicle_model or len(vehicle_model) < 2 or len(vehicle_model) > 100:
        return {"success": False, "error": "Vehicle name/model must be between 2 and 100 characters."}, 400

    reg_normalized = normalize_reg_number(vehicle_reg_raw)
    if not reg_normalized or len(reg_normalized) < 4 or len(reg_normalized) > 20:
        return {"success": False, "error": "Valid vehicle registration number is required (4-20 alphanumeric characters)."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        # 1. Prevent duplicate active tickets for this user
        cursor.execute("""
            SELECT q.queue_id, q.queue_ticket, q.station_id, cs.station_name, q.status
            FROM walkin_queue q
            JOIN charging_stations cs ON q.station_id = cs.station_id
            WHERE q.user_id = %s AND q.status IN ('WAITING', 'READY', 'CHARGING')
            FOR UPDATE;
        """, (user_id,))
        active_ticket = cursor.fetchone()

        if active_ticket:
            conn.rollback()
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": f"Duplicate queue entry rejected: You already hold an active ticket ({active_ticket['queue_ticket']}) at {active_ticket['station_name']} with status '{active_ticket['status']}'. Please leave or complete that queue before joining another."
            }, 409

        # 2. Check station and walk-in ports
        cursor.execute("""
            SELECT cs.station_id, cs.station_name, cs.location, cs.charger_type,
                   (SELECT COUNT(*) FROM station_chargers sc WHERE sc.station_id = cs.station_id AND sc.allocation_type = 'WALKIN' AND sc.status != 'MAINTENANCE') AS walkin_ports
            FROM charging_stations cs
            WHERE cs.station_id = %s
            FOR UPDATE;
        """, (station_id,))
        station = cursor.fetchone()

        if not station:
            conn.rollback()
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Station #{station_id} not found."}, 404

        walkin_ports = station["walkin_ports"] or 0
        if walkin_ports == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return {"success": False, "error": "This station currently has no walk-in charging ports configured."}, 400

        if not charger_type:
            charger_type = station["charger_type"] or "Fast DC"

        # 3. Calculate FIFO queue position (number of people currently waiting ahead)
        cursor.execute("""
            SELECT COUNT(*) AS waiting_ahead
            FROM walkin_queue
            WHERE station_id = %s AND status = 'WAITING';
        """, (station_id,))
        waiting_ahead = cursor.fetchone()["waiting_ahead"] or 0
        current_position = waiting_ahead + 1

        # Calculate estimated wait
        effective_ports = max(walkin_ports, 1)
        estimated_wait = max(5, int((current_position * 15) / effective_ports))

        # 4. Generate unique queue ticket: WQ-S{sid}-{token}
        ticket_code = f"WQ-S{station_id}-{secrets.token_hex(2).upper()}"

        # 5. Insert queue record
        cursor.execute("""
            INSERT INTO walkin_queue (
                queue_ticket, user_id, station_id, charger_type, driver_name,
                vehicle_model, vehicle_reg_number, status, priority_score,
                estimated_wait_minutes, joined_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'WAITING', 0, %s, NOW());
        """, (
            ticket_code,
            user_id,
            station_id,
            charger_type,
            driver_name,
            vehicle_model,
            reg_normalized,
            estimated_wait
        ))

        new_queue_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": "You have successfully joined the Rapid Walk-in Charging Queue!",
            "ticket": {
                "queue_id": new_queue_id,
                "queue_ticket": ticket_code,
                "station_id": station_id,
                "station_name": station["station_name"],
                "location": station["location"],
                "charger_type": charger_type,
                "driver_name": driver_name,
                "vehicle_model": vehicle_model,
                "vehicle_reg_number": reg_normalized,
                "status": "WAITING",
                "position": current_position,
                "estimated_wait_minutes": estimated_wait,
                "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        }, 201

    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return {"success": False, "error": f"Failed to join walk-in queue: {str(e)}"}, 500

def get_user_active_ticket(user_id):
    """
    Retrieve the active queue ticket for the logged-in user with dynamic live position
    and recalculated estimated wait time.
    """
    if not user_id:
        return {"success": False, "error": "Authentication required."}, 401

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                q.queue_id,
                q.queue_ticket,
                q.user_id,
                q.station_id,
                cs.station_name,
                cs.location,
                q.charger_type,
                q.driver_name,
                q.vehicle_model,
                q.vehicle_reg_number,
                q.status,
                q.priority_score,
                DATE_FORMAT(q.joined_at, '%Y-%m-%d %H:%i') AS joined_at,
                DATE_FORMAT(q.called_at, '%Y-%m-%d %H:%i') AS called_at,
                (SELECT COUNT(*) FROM station_chargers sc WHERE sc.station_id = q.station_id AND sc.allocation_type = 'WALKIN' AND sc.status != 'MAINTENANCE') AS walkin_ports
            FROM walkin_queue q
            JOIN charging_stations cs ON q.station_id = cs.station_id
            WHERE q.user_id = %s AND q.status IN ('WAITING', 'READY', 'CHARGING')
            ORDER BY q.queue_id DESC
            LIMIT 1;
        """, (user_id,))
        ticket = cursor.fetchone()

        if not ticket:
            cursor.close()
            conn.close()
            return {"success": True, "ticket": None, "message": "No active walk-in queue ticket."}, 200

        # Recalculate dynamic live queue position
        position = 1
        est_wait = 0
        walkin_ports = max(int(ticket["walkin_ports"] or 1), 1)

        if ticket["status"] == "WAITING":
            cursor.execute("""
                SELECT COUNT(*) AS ahead_count
                FROM walkin_queue
                WHERE station_id = %s AND status = 'WAITING' AND queue_id < %s;
            """, (ticket["station_id"], ticket["queue_id"]))
            ahead = cursor.fetchone()["ahead_count"] or 0
            position = ahead + 1
            est_wait = max(5, int((position * 15) / walkin_ports))
        elif ticket["status"] == "READY":
            position = 0  # It's their turn!
            est_wait = 0
        elif ticket["status"] == "CHARGING":
            position = 0
            est_wait = 0

        cursor.close()
        conn.close()

        ticket["position"] = position
        ticket["estimated_wait_minutes"] = est_wait

        return {"success": True, "ticket": ticket}, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to fetch active queue ticket: {str(e)}"}, 500

def cancel_queue_ticket(user_id, queue_id, is_admin=False):
    """
    Cancel an active ticket (driver leaves the walk-in queue).
    Dynamic positions of remaining drivers will adjust automatically on their next fetch.
    """
    try:
        queue_id = int(queue_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid queue ID."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM walkin_queue WHERE queue_id = %s", (queue_id,))
        ticket = cursor.fetchone()

        if not ticket:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Queue ticket #{queue_id} not found."}, 404

        if not is_admin and ticket["user_id"] != user_id:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Access denied. You can only leave your own queue."}, 403

        if ticket["status"] not in ("WAITING", "READY"):
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": f"Cannot cancel ticket because its current status is '{ticket['status']}'."
            }, 400

        cursor.execute("""
            UPDATE walkin_queue
            SET status = 'CANCELLED',
                completed_at = NOW()
            WHERE queue_id = %s;
        """, (queue_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": f"Ticket {ticket['queue_ticket']} cancelled. You have left the queue.",
            "queue_id": queue_id,
            "status": "CANCELLED"
        }, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to cancel queue ticket: {str(e)}"}, 500

def admin_get_all_queues(station_id=None):
    """Retrieve all tickets in walk-in queue for administrator dashboard."""
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                q.queue_id,
                q.queue_ticket,
                q.user_id,
                u.email AS user_email,
                u.full_name AS user_name,
                q.station_id,
                cs.station_name,
                q.charger_type,
                q.driver_name,
                q.vehicle_model,
                q.vehicle_reg_number,
                q.status,
                q.estimated_wait_minutes,
                DATE_FORMAT(q.joined_at, '%Y-%m-%d %H:%i') AS joined_at,
                DATE_FORMAT(q.called_at, '%Y-%m-%d %H:%i') AS called_at,
                DATE_FORMAT(q.completed_at, '%Y-%m-%d %H:%i') AS completed_at
            FROM walkin_queue q
            JOIN users u ON q.user_id = u.user_id
            JOIN charging_stations cs ON q.station_id = cs.station_id
        """
        params = []
        if station_id:
            query += " WHERE q.station_id = %s"
            params.append(station_id)

        query += " ORDER BY q.queue_id DESC LIMIT 100;"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return {"success": True, "queues": rows, "count": len(rows)}, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to retrieve queues: {str(e)}"}, 500

