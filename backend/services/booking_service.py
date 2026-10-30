import re
import secrets
from datetime import datetime, date, time, timedelta
from mysql.connector import Error
from backend.database.db_config import get_db_connection

VALID_DURATIONS = {30, 60, 90, 120}
MIN_ADVANCE_CANCEL_MINUTES = 30
DEFAULT_GRACE_PERIOD_MINUTES = 15

def normalize_reg_number(reg_str):
    """Normalize vehicle registration number to uppercase without irregular spaces."""
    if not reg_str:
        return ""
    return re.sub(r'[^A-Za-z0-9]', '', reg_str).upper()

def evaluate_missed_bookings(conn=None):
    """
    Check for confirmed bookings where the scheduled start time plus grace period
    has elapsed without check-in/completion, and mark them as MISSED.
    Releases capacity automatically.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    if not conn:
        return 0

    try:
        cursor = conn.cursor(dictionary=True)
        # Select bookings that are CONFIRMED and past (booking_date + start_time + grace_period)
        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M:%S")

        query = """
            UPDATE station_bookings
            SET status = 'MISSED',
                updated_at = NOW()
            WHERE status = 'CONFIRMED'
              AND (
                  booking_date < %s
                  OR (
                      booking_date = %s
                      AND TIMESTAMP(CONCAT(booking_date, ' ', start_time)) + INTERVAL grace_period_minutes MINUTE < NOW()
                  )
              );
        """
        cursor.execute(query, (current_date_str, current_date_str))
        updated_count = cursor.rowcount
        conn.commit()
        cursor.close()
        return updated_count
    except Error as e:
        print(f"[Booking Service Error] evaluate_missed_bookings failed: {e}")
        return 0
    finally:
        if should_close and conn and conn.is_connected():
            conn.close()

def get_available_slots(station_id, booking_date_str, duration_minutes=60):
    """
    Calculate and return list of available time slots for a given station and date.
    - Operating hours: 08:00 to 22:00.
    - Interval: 30 minutes.
    - Disables past slots for today.
    - Checks overlap with active CONFIRMED bookings on RESERVED chargers.
    """
    evaluate_missed_bookings()

    try:
        station_id = int(station_id)
        duration_minutes = int(duration_minutes)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid station ID or duration parameter."}, 400

    if duration_minutes not in VALID_DURATIONS:
        return {"success": False, "error": f"Invalid duration. Allowed values: {sorted(list(VALID_DURATIONS))} minutes."}, 400

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid date format. Expected YYYY-MM-DD."}, 400

    today = date.today()
    if booking_date < today:
        return {"success": False, "error": "Cannot view or book slots for past dates."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Verify station exists
        cursor.execute("SELECT station_id, station_name, location, total_ports, charger_type FROM charging_stations WHERE station_id = %s", (station_id,))
        station = cursor.fetchone()
        if not station:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Station #{station_id} not found."}, 404

        # 2. Get reserved chargers for this station
        cursor.execute("""
            SELECT charger_id, port_number, charger_type, capacity_kw
            FROM station_chargers
            WHERE station_id = %s AND allocation_type = 'RESERVED' AND status != 'MAINTENANCE'
        """, (station_id,))
        reserved_chargers = cursor.fetchall()
        total_reserved_ports = len(reserved_chargers)

        if total_reserved_ports == 0:
            cursor.close()
            conn.close()
            return {
                "success": True,
                "station_id": station_id,
                "station_name": station["station_name"],
                "booking_date": booking_date_str,
                "duration_minutes": duration_minutes,
                "total_reserved_ports": 0,
                "slots": [],
                "message": "No reserved charging ports available at this station."
            }, 200

        # 3. Fetch existing confirmed bookings for this date and station
        cursor.execute("""
            SELECT booking_id, charger_id, port_number, start_time, end_time
            FROM station_bookings
            WHERE station_id = %s AND booking_date = %s AND status = 'CONFIRMED'
        """, (station_id, booking_date_str))
        existing_bookings = cursor.fetchall()

        cursor.close()
        conn.close()

        # 4. Generate 30-min time slots from 08:00 to 22:00
        slots = []
        now = datetime.now()
        start_hour, end_hour = 8, 22

        current_slot_dt = datetime.combine(booking_date, time(start_hour, 0))
        day_end_dt = datetime.combine(booking_date, time(end_hour, 0))

        while current_slot_dt + timedelta(minutes=duration_minutes) <= day_end_dt:
            slot_start_time = current_slot_dt.time()
            slot_end_dt = current_slot_dt + timedelta(minutes=duration_minutes)
            slot_end_time = slot_end_dt.time()

            start_str = slot_start_time.strftime("%H:%M")
            end_str = slot_end_time.strftime("%H:%M")

            is_past = (booking_date == today and current_slot_dt <= now)

            # Count overlapping bookings
            overlapping_count = 0
            booked_ports = set()
            for b in existing_bookings:
                b_start = b["start_time"]
                b_end = b["end_time"]
                # Convert time delta/objects if needed
                if isinstance(b_start, timedelta):
                    b_start = (datetime.min + b_start).time()
                if isinstance(b_end, timedelta):
                    b_end = (datetime.min + b_end).time()

                # Overlap condition: start < other_end and end > other_start
                if slot_start_time < b_end and slot_end_time > b_start:
                    overlapping_count += 1
                    booked_ports.add(b["port_number"])

            available_ports = max(0, total_reserved_ports - overlapping_count)
            is_available = (not is_past) and (available_ports > 0)

            status_reason = "available"
            if is_past:
                status_reason = "past"
            elif available_ports == 0:
                status_reason = "fully_booked"

            slots.append({
                "start_time": start_str,
                "end_time": end_str,
                "available": is_available,
                "is_past": is_past,
                "free_ports": available_ports,
                "total_ports": total_reserved_ports,
                "status_reason": status_reason
            })

            current_slot_dt += timedelta(minutes=30)

        return {
            "success": True,
            "station_id": station_id,
            "station_name": station["station_name"],
            "location": station["location"],
            "charger_type": station["charger_type"],
            "booking_date": booking_date_str,
            "duration_minutes": duration_minutes,
            "total_reserved_ports": total_reserved_ports,
            "slots": slots
        }, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Database query error: {str(e)}"}, 500

def create_booking(user_id, data):
    """
    Create a new slot reservation.
    Enforces concurrency protection using MySQL transactions and FOR UPDATE locking.
    Prevents double booking of the same physical charger.
    """
    evaluate_missed_bookings()

    if not user_id:
        return {"success": False, "error": "Authentication required."}, 401

    station_id = data.get("station_id")
    driver_name = str(data.get("driver_name", "")).strip()
    vehicle_model = str(data.get("vehicle_model", "")).strip()
    vehicle_reg_raw = str(data.get("vehicle_reg_number", "")).strip()
    booking_date_str = str(data.get("booking_date", "")).strip()
    start_time_str = str(data.get("start_time", "")).strip()
    duration_minutes = data.get("duration_minutes", 60)

    # Input validations
    if not station_id:
        return {"success": False, "error": "Charging station selection is required."}, 400

    if not driver_name or len(driver_name) < 2 or len(driver_name) > 100:
        return {"success": False, "error": "Full driver name must be between 2 and 100 characters."}, 400

    if not vehicle_model or len(vehicle_model) < 2 or len(vehicle_model) > 100:
        return {"success": False, "error": "Vehicle name/model must be between 2 and 100 characters."}, 400

    vehicle_reg_normalized = normalize_reg_number(vehicle_reg_raw)
    if not vehicle_reg_normalized or len(vehicle_reg_normalized) < 4 or len(vehicle_reg_normalized) > 20:
        return {"success": False, "error": "Valid vehicle registration number is required (4-20 alphanumeric characters)."}, 400

    try:
        duration_minutes = int(duration_minutes)
        if duration_minutes not in VALID_DURATIONS:
            return {"success": False, "error": f"Duration must be one of {sorted(list(VALID_DURATIONS))} minutes."}, 400
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid duration value."}, 400

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid booking date format. Use YYYY-MM-DD."}, 400

    today = date.today()
    if booking_date < today:
        return {"success": False, "error": "Cannot book slots in the past."}, 400

    # Parse start time (accept HH:MM or HH:MM:SS)
    try:
        if len(start_time_str) == 5:
            slot_start_time = datetime.strptime(start_time_str, "%H:%M").time()
        else:
            slot_start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid start time format. Use HH:MM."}, 400

    # Check operating hours (08:00 - 22:00)
    slot_start_dt = datetime.combine(booking_date, slot_start_time)
    slot_end_dt = slot_start_dt + timedelta(minutes=duration_minutes)
    operating_open = datetime.combine(booking_date, time(8, 0))
    operating_close = datetime.combine(booking_date, time(22, 0))

    if slot_start_dt < operating_open or slot_end_dt > operating_close:
        return {"success": False, "error": "Bookings are only available within operational hours (08:00 to 22:00)."}, 400

    # If booking is for today, must be in future
    if booking_date == today and slot_start_dt <= datetime.now():
        return {"success": False, "error": "Selected slot start time has already passed for today."}, 400

    slot_end_time = slot_end_dt.time()
    start_time_sql = slot_start_time.strftime("%H:%M:%S")
    end_time_sql = slot_end_time.strftime("%H:%M:%S")

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        # Start transaction for strict isolation
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        # 1. Check if user already has an active CONFIRMED booking overlapping this window anywhere
        cursor.execute("""
            SELECT booking_id, booking_reference, station_id, start_time, end_time
            FROM station_bookings
            WHERE user_id = %s
              AND booking_date = %s
              AND status = 'CONFIRMED'
              AND (start_time < %s AND end_time > %s)
            FOR UPDATE;
        """, (user_id, booking_date_str, end_time_sql, start_time_sql))
        user_conflict = cursor.fetchone()
        if user_conflict:
            conn.rollback()
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": f"You already have a confirmed booking ({user_conflict['booking_reference']}) overlapping with this time window."
            }, 409

        # 2. Lock reserved chargers for this station to prevent race conditions
        cursor.execute("""
            SELECT sc.charger_id, sc.port_number, sc.charger_type, sc.capacity_kw, cs.station_name, cs.location
            FROM station_chargers sc
            JOIN charging_stations cs ON sc.station_id = cs.station_id
            WHERE sc.station_id = %s AND sc.allocation_type = 'RESERVED' AND sc.status != 'MAINTENANCE'
            FOR UPDATE;
        """, (station_id,))
        reserved_chargers = cursor.fetchall()

        if not reserved_chargers:
            conn.rollback()
            cursor.close()
            conn.close()
            return {"success": False, "error": "Selected station has no active reserved charging ports."}, 400

        # 3. Find an available charger not booked in this slot
        allocated_charger = None
        for ch in reserved_chargers:
            cid = ch["charger_id"]
            cursor.execute("""
                SELECT booking_id FROM station_bookings
                WHERE charger_id = %s
                  AND booking_date = %s
                  AND status = 'CONFIRMED'
                  AND (start_time < %s AND end_time > %s)
                LIMIT 1
                FOR UPDATE;
            """, (cid, booking_date_str, end_time_sql, start_time_sql))
            conflict = cursor.fetchone()
            if not conflict:
                allocated_charger = ch
                break

        if not allocated_charger:
            conn.rollback()
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": "Conflict: No charging ports are available at this station for the chosen time slot. It was just booked by another driver. Please choose another time slot."
            }, 409

        # 4. Generate unique booking reference: BK-YYYYMMDD-XXXX
        ref_prefix = f"BK-{booking_date.strftime('%Y%m%d')}-"
        ref_suffix = secrets.token_hex(2).upper()
        booking_reference = f"{ref_prefix}{ref_suffix}"

        # 5. Insert confirmed booking
        cursor.execute("""
            INSERT INTO station_bookings (
                booking_reference, user_id, station_id, charger_id, port_number,
                charger_type, driver_name, vehicle_model, vehicle_reg_number,
                booking_date, start_time, end_time, duration_minutes, status, grace_period_minutes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMED', %s);
        """, (
            booking_reference,
            user_id,
            station_id,
            allocated_charger["charger_id"],
            allocated_charger["port_number"],
            allocated_charger["charger_type"],
            driver_name,
            vehicle_model,
            vehicle_reg_normalized,
            booking_date_str,
            start_time_sql,
            end_time_sql,
            duration_minutes,
            DEFAULT_GRACE_PERIOD_MINUTES
        ))

        new_booking_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": "Slot successfully reserved! Your booking confirmation is ready.",
            "booking": {
                "booking_id": new_booking_id,
                "booking_reference": booking_reference,
                "station_id": station_id,
                "station_name": allocated_charger["station_name"],
                "location": allocated_charger["location"],
                "port_number": allocated_charger["port_number"],
                "charger_type": allocated_charger["charger_type"],
                "capacity_kw": float(allocated_charger["capacity_kw"]),
                "driver_name": driver_name,
                "vehicle_model": vehicle_model,
                "vehicle_reg_number": vehicle_reg_normalized,
                "booking_date": booking_date_str,
                "start_time": slot_start_time.strftime("%H:%M"),
                "end_time": slot_end_time.strftime("%H:%M"),
                "duration_minutes": duration_minutes,
                "status": "CONFIRMED",
                "grace_period_minutes": DEFAULT_GRACE_PERIOD_MINUTES
            }
        }, 201

    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return {"success": False, "error": f"Booking transaction failed: {str(e)}"}, 500

def get_user_bookings(user_id):
    """Fetch all bookings belonging to a specific user, ordered chronologically."""
    evaluate_missed_bookings()

    if not user_id:
        return {"success": False, "error": "Authentication required."}, 401

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                b.booking_id,
                b.booking_reference,
                b.user_id,
                b.station_id,
                b.port_number,
                b.charger_type,
                b.driver_name,
                b.vehicle_model,
                b.vehicle_reg_number,
                DATE_FORMAT(b.booking_date, '%Y-%m-%d') AS booking_date,
                TIME_FORMAT(b.start_time, '%H:%i') AS start_time,
                TIME_FORMAT(b.end_time, '%H:%i') AS end_time,
                b.duration_minutes,
                b.status,
                b.grace_period_minutes,
                b.cancellation_reason,
                DATE_FORMAT(b.created_at, '%Y-%m-%d %H:%i') AS created_at,
                cs.station_name,
                cs.location
            FROM station_bookings b
            JOIN charging_stations cs ON b.station_id = cs.station_id
            WHERE b.user_id = %s
            ORDER BY b.booking_date DESC, b.start_time DESC;
        """, (user_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Add cancellable status flag based on 30-min policy
        now = datetime.now()
        for r in rows:
            is_cancellable = False
            if r["status"] == "CONFIRMED":
                b_dt = datetime.strptime(f"{r['booking_date']} {r['start_time']}", "%Y-%m-%d %H:%M")
                if b_dt - now > timedelta(minutes=MIN_ADVANCE_CANCEL_MINUTES):
                    is_cancellable = True
            r["is_cancellable"] = is_cancellable

        return {"success": True, "bookings": rows, "count": len(rows)}, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Database query failed: {str(e)}"}, 500

def cancel_booking(user_id, booking_id, reason=None, is_admin=False):
    """
    Cancel a confirmed booking adhering strictly to the cancellation policy.
    Cancellation is allowed ONLY if > 30 minutes before the scheduled start time.
    """
    evaluate_missed_bookings()

    try:
        booking_id = int(booking_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid booking ID."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT booking_id, booking_reference, user_id, station_id,
                   DATE_FORMAT(booking_date, '%Y-%m-%d') AS booking_date,
                   TIME_FORMAT(start_time, '%H:%i') AS start_time,
                   status
            FROM station_bookings
            WHERE booking_id = %s
        """, (booking_id,))
        booking = cursor.fetchone()

        if not booking:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Booking #{booking_id} not found."}, 404

        # Ownership enforcement
        if not is_admin and booking["user_id"] != user_id:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Access denied. You can only cancel your own bookings."}, 403

        if booking["status"] != "CONFIRMED":
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": f"Booking cannot be cancelled because its current status is '{booking['status']}'."
            }, 400

        # Enforce cancellation policy: strictly > 30 minutes before start time
        if not is_admin:
            now = datetime.now()
            b_start_dt = datetime.strptime(f"{booking['booking_date']} {booking['start_time']}", "%Y-%m-%d %H:%M")
            time_remaining = b_start_dt - now

            if time_remaining <= timedelta(minutes=MIN_ADVANCE_CANCEL_MINUTES):
                cursor.close()
                conn.close()
                return {
                    "success": False,
                    "error": (
                        "Cancellation policy violation: Bookings can only be cancelled at least 30 minutes "
                        f"before the scheduled start time. Your slot is scheduled to start in less than "
                        f"{max(0, int(time_remaining.total_seconds() // 60))} minutes."
                    )
                }, 400

        cancel_msg = reason.strip() if reason else "Cancelled by user"
        cursor.execute("""
            UPDATE station_bookings
            SET status = 'CANCELLED',
                cancellation_reason = %s,
                updated_at = NOW()
            WHERE booking_id = %s;
        """, (cancel_msg, booking_id))
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": f"Booking {booking['booking_reference']} has been successfully cancelled. The reserved slot is now released.",
            "booking_id": booking_id,
            "status": "CANCELLED"
        }, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to cancel booking: {str(e)}"}, 500

def get_alternative_slots(user_id, booking_id):
    """
    Suggest alternative available slots for a missed booking.
    Searches next available slots at the same station first, then nearby stations.
    Does NOT automatically rebook; requires explicit user selection and confirmation.
    """
    evaluate_missed_bookings()

    try:
        booking_id = int(booking_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid booking ID."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.*, cs.station_name, cs.location, cs.charger_type
            FROM station_bookings b
            JOIN charging_stations cs ON b.station_id = cs.station_id
            WHERE b.booking_id = %s
        """, (booking_id,))
        booking = cursor.fetchone()

        if not booking:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Booking #{booking_id} not found."}, 404

        if booking["user_id"] != user_id:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Access denied."}, 403

        target_station_id = booking["station_id"]
        duration = booking["duration_minutes"]
        today_str = date.today().strftime("%Y-%m-%d")
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        cursor.close()
        conn.close()

        # Look for available slots at same station today & tomorrow
        same_station_alternatives = []
        for test_date in [today_str, tomorrow_str]:
            res, code = get_available_slots(target_station_id, test_date, duration)
            if code == 200 and res.get("slots"):
                for s in res["slots"]:
                    if s["available"]:
                        same_station_alternatives.append({
                            "station_id": target_station_id,
                            "station_name": booking["station_name"],
                            "location": booking["location"],
                            "date": test_date,
                            "start_time": s["start_time"],
                            "end_time": s["end_time"],
                            "duration_minutes": duration,
                            "charger_type": booking["charger_type"],
                            "match_type": "Same Station"
                        })
                        if len(same_station_alternatives) >= 3:
                            break
            if len(same_station_alternatives) >= 3:
                break

        # Also look for available slots at other stations
        conn2 = get_db_connection()
        other_station_alternatives = []
        if conn2:
            cur2 = conn2.cursor(dictionary=True)
            cur2.execute("SELECT station_id, station_name FROM charging_stations WHERE station_id != %s LIMIT 3", (target_station_id,))
            other_stations = cur2.fetchall()
            cur2.close()
            conn2.close()

            for ost in other_stations:
                res, code = get_available_slots(ost["station_id"], today_str, duration)
                if code == 200 and res.get("slots"):
                    for s in res["slots"]:
                        if s["available"]:
                            other_station_alternatives.append({
                                "station_id": ost["station_id"],
                                "station_name": ost["station_name"],
                                "location": res.get("location", ""),
                                "date": today_str,
                                "start_time": s["start_time"],
                                "end_time": s["end_time"],
                                "duration_minutes": duration,
                                "charger_type": res.get("charger_type", "Fast DC"),
                                "match_type": "Alternative Station"
                            })
                            break

        all_suggestions = same_station_alternatives + other_station_alternatives

        return {
            "success": True,
            "original_booking": {
                "booking_id": booking["booking_id"],
                "booking_reference": booking["booking_reference"],
                "station_name": booking["station_name"],
                "status": booking["status"],
                "driver_name": booking["driver_name"],
                "vehicle_model": booking["vehicle_model"],
                "vehicle_reg_number": booking["vehicle_reg_number"]
            },
            "alternatives": all_suggestions,
            "message": "Alternative slot suggestions generated. Select a slot to confirm your new reservation."
        }, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to retrieve alternatives: {str(e)}"}, 500

def admin_get_all_bookings():
    """Retrieve all bookings across all stations for administrator oversight."""
    evaluate_missed_bookings()

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database service unavailable."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                b.booking_id,
                b.booking_reference,
                b.user_id,
                u.email AS user_email,
                u.full_name AS user_name,
                b.station_id,
                cs.station_name,
                b.port_number,
                b.charger_type,
                b.driver_name,
                b.vehicle_model,
                b.vehicle_reg_number,
                DATE_FORMAT(b.booking_date, '%Y-%m-%d') AS booking_date,
                TIME_FORMAT(b.start_time, '%H:%i') AS start_time,
                TIME_FORMAT(b.end_time, '%H:%i') AS end_time,
                b.duration_minutes,
                b.status,
                b.grace_period_minutes,
                DATE_FORMAT(b.created_at, '%Y-%m-%d %H:%i') AS created_at
            FROM station_bookings b
            JOIN users u ON b.user_id = u.user_id
            JOIN charging_stations cs ON b.station_id = cs.station_id
            ORDER BY b.booking_date DESC, b.start_time DESC;
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"success": True, "bookings": rows, "count": len(rows)}, 200

    except Error as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Database query failed: {str(e)}"}, 500

