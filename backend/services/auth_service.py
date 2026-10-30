import re
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database.db_config import get_db_connection

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_registration_input(full_name, email, password, confirm_password=None):
    """
    Validate and normalize registration inputs.
    Returns: (is_valid: bool, error_message: str or None, normalized_name: str, normalized_email: str)
    """
    if not full_name or not isinstance(full_name, str):
        return False, "Full name is required.", "", ""
    name_clean = full_name.strip()
    if len(name_clean) < 2 or len(name_clean) > 100:
        return False, "Full name must be between 2 and 100 characters.", "", ""

    if not email or not isinstance(email, str):
        return False, "Email address is required.", "", ""
    email_clean = email.strip().lower()
    if len(email_clean) > 150 or not EMAIL_REGEX.match(email_clean):
        return False, "Please enter a valid email address.", "", ""

    if not password or not isinstance(password, str):
        return False, "Password is required.", "", ""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long.", "", ""
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters.", "", ""
    if password.strip() == "":
        return False, "Password cannot consist solely of whitespace characters.", "", ""

    if confirm_password is not None:
        if not isinstance(confirm_password, str) or password != confirm_password:
            return False, "Passwords do not match.", "", ""

    return True, None, name_clean, email_clean

def register_user(full_name, email, password, role="user", is_controlled_provision=False, confirm_password=None):
    """
    Register a new user in the MySQL database.
    Security guarantee: Public callers cannot set an administrative role.
    Role is strictly hardcoded to 'user' unless is_controlled_provision is explicitly True.
    Returns: (dict_response, http_status_code)
    """
    is_valid, err_msg, name_clean, email_clean = validate_registration_input(
        full_name, email, password, confirm_password
    )
    if not is_valid:
        return {
            "success": False,
            "error": err_msg
        }, 400

    # Public registration MUST always assign role 'user'
    assigned_role = "user"
    if is_controlled_provision and role in ["user", "admin"]:
        assigned_role = role

    conn = get_db_connection()
    if not conn:
        return {
            "success": False,
            "error": "Database connection failed. Ensure MySQL is running."
        }, 500

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Parameterized check for existing duplicate email
        cursor.execute("SELECT user_id FROM users WHERE email = %s LIMIT 1;", (email_clean,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.close()
            conn.close()
            return {
                "success": False,
                "error": "An account with this email address already exists."
            }, 409

        # 2. Hash password with Werkzeug (scrypt algorithm)
        pwd_hash = generate_password_hash(password, method="scrypt")

        # 3. Parameterized INSERT
        cursor.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (%s, %s, %s, %s);
            """,
            (name_clean, email_clean, pwd_hash, assigned_role)
        )
        conn.commit()
        new_user_id = cursor.lastrowid
        cursor.close()
        conn.close()

        # 4. Return sanitized user data (NEVER expose password hash)
        return {
            "success": True,
            "message": "User registered successfully.",
            "user": {
                "user_id": new_user_id,
                "full_name": name_clean,
                "email": email_clean,
                "role": assigned_role
            }
        }, 201

    except mysql.connector.Error as db_err:
        if conn and conn.is_connected():
            conn.close()
        # Handle race condition duplicate key error (MySQL 1062)
        if db_err.errno == 1062:
            return {
                "success": False,
                "error": "An account with this email address already exists."
            }, 409
        return {
            "success": False,
            "error": f"Database error during registration: {str(db_err)}"
        }, 500
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return {
            "success": False,
            "error": f"Registration failed: {str(e)}"
        }, 500

def authenticate_user(email, password):
    """
    Authenticate user credentials against MySQL records.
    Returns: (dict_response, http_status_code)
    """
    if not email or not isinstance(email, str) or not password or not isinstance(password, str):
        return {
            "success": False,
            "error": "Email and password are required."
        }, 400

    email_clean = email.strip().lower()

    conn = get_db_connection()
    if not conn:
        return {
            "success": False,
            "error": "Database connection failed. Ensure MySQL is running."
        }, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, password_hash, role FROM users WHERE email = %s LIMIT 1;",
            (email_clean,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # Uniform error message to prevent account enumeration
        if not user or not check_password_hash(user["password_hash"], password):
            return {
                "success": False,
                "error": "Invalid email or password."
            }, 401

        # Sanitized user record returned on successful authentication
        return {
            "success": True,
            "message": "Authentication successful.",
            "user": {
                "user_id": user["user_id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "role": user["role"]
            }
        }, 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return {
            "success": False,
            "error": f"Authentication failed: {str(e)}"
        }, 500

def get_user_by_id(user_id):
    """
    Retrieve user by ID excluding sensitive password hash.
    Returns: user dictionary or None
    """
    if not user_id:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, role, created_at FROM users WHERE user_id = %s LIMIT 1;",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and "created_at" in user and user["created_at"]:
            user["created_at"] = user["created_at"].isoformat()

        return user
    except Exception:
        if conn and conn.is_connected():
            conn.close()
        return None

def get_admin_system_overview():
    """
    Retrieve system telemetry and record counts for authenticated administrators only.
    Returns: dict with counts and security diagnostic flags.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total_users FROM users;")
        user_count = cursor.fetchone()["total_users"]

        cursor.execute("SELECT COUNT(*) AS total_stations FROM charging_stations;")
        station_count = cursor.fetchone()["total_stations"]

        cursor.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role;")
        role_breakdown = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "database_status": "connected",
            "total_users": user_count,
            "total_stations": station_count,
            "role_breakdown": role_breakdown,
            "security_mode": "Strict (HttpOnly, SameSite=Lax, CSRF Protected)"
        }
    except Exception:
        if conn and conn.is_connected():
            conn.close()
        return None

def admin_get_all_users():
    """
    Retrieve all user accounts for authenticated administrators only.
    Excludes sensitive password hashes.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, role, created_at, updated_at "
            "FROM users ORDER BY user_id ASC;"
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        users = []
        for r in rows:
            users.append({
                "user_id": r["user_id"],
                "full_name": r["full_name"],
                "email": r["email"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None
            })
        return users
    except Exception:
        if conn and conn.is_connected():
            conn.close()
        return None

def admin_create_station(data):
    """
    Create a new EV charging station record in MySQL.
    Admin-only operation with parameterized queries and strict validation.
    """
    if not isinstance(data, dict):
        return {"success": False, "error": "Invalid payload format. Must be a JSON object."}, 400

    name = data.get("station_name")
    location = data.get("location")
    if not name or not isinstance(name, str) or not name.strip():
        return {"success": False, "error": "Station name is required."}, 400
    if not location or not isinstance(location, str) or not location.strip():
        return {"success": False, "error": "Location is required."}, 400

    charger_type = data.get("charger_type", "Fast DC")
    if charger_type not in ["Fast DC", "AC Type 2", "DC CCS", "CHAdeMO"]:
        charger_type = str(charger_type).strip() or "Fast DC"

    try:
        distance_km = float(data.get("distance_km", 2.0))
        capacity_kw = float(data.get("capacity_kw", 50.0))
        total_ports = int(data.get("total_ports", 4))
        available_ports = int(data.get("available_ports", 2))
        estimated_wait_minutes = int(data.get("estimated_wait_minutes", 5))
        demand_level = str(data.get("demand_level", "Medium")).strip()
        if demand_level not in ["Low", "Medium", "High"]:
            demand_level = "Medium"

        lat = data.get("latitude")
        lng = data.get("longitude")
        latitude = float(lat) if lat is not None and str(lat).strip() != "" else None
        longitude = float(lng) if lng is not None and str(lng).strip() != "" else None
    except (ValueError, TypeError) as num_err:
        return {"success": False, "error": f"Invalid numeric input: {str(num_err)}"}, 400

    if total_ports < 1:
        return {"success": False, "error": "Total ports must be at least 1."}, 400
    if available_ports < 0 or available_ports > total_ports:
        return {"success": False, "error": "Available ports must be between 0 and total ports."}, 400
    if estimated_wait_minutes < 0:
        return {"success": False, "error": "Estimated wait time cannot be negative."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO charging_stations (
                station_name, location, distance_km, charger_type, capacity_kw,
                available_ports, total_ports, estimated_wait_minutes, demand_level,
                latitude, longitude
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                name.strip(), location.strip(), distance_km, charger_type, capacity_kw,
                available_ports, total_ports, estimated_wait_minutes, demand_level,
                latitude, longitude
            )
        )
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": f"Station '{name.strip()}' created successfully.",
            "station": {
                "station_id": new_id,
                "station_name": name.strip(),
                "location": location.strip(),
                "distance_km": distance_km,
                "charger_type": charger_type,
                "capacity_kw": capacity_kw,
                "available_ports": available_ports,
                "total_ports": total_ports,
                "estimated_wait_minutes": estimated_wait_minutes,
                "demand_level": demand_level,
                "latitude": latitude,
                "longitude": longitude
            }
        }, 201
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to create station: {str(e)}"}, 500

def admin_update_station(station_id, data):
    """
    Update an existing EV charging station record in MySQL.
    Admin-only operation with parameterized queries and strict validation.
    """
    if not isinstance(data, dict):
        return {"success": False, "error": "Invalid payload format. Must be a JSON object."}, 400

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM charging_stations WHERE station_id = %s;", (station_id,))
        existing = cursor.fetchone()
        if not existing:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Station with ID {station_id} does not exist."}, 404

        name = data.get("station_name", existing["station_name"])
        location = data.get("location", existing["location"])
        charger_type = data.get("charger_type", existing["charger_type"])
        demand_level = data.get("demand_level", existing["demand_level"])

        try:
            distance_km = float(data.get("distance_km", existing["distance_km"]))
            capacity_kw = float(data.get("capacity_kw", existing["capacity_kw"]))
            total_ports = int(data.get("total_ports", existing["total_ports"]))
            available_ports = int(data.get("available_ports", existing["available_ports"]))
            estimated_wait_minutes = int(data.get("estimated_wait_minutes", existing["estimated_wait_minutes"]))

            lat = data.get("latitude", existing["latitude"])
            lng = data.get("longitude", existing["longitude"])
            latitude = float(lat) if lat is not None and str(lat).strip() != "" else None
            longitude = float(lng) if lng is not None and str(lng).strip() != "" else None
        except (ValueError, TypeError) as num_err:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Invalid numeric input: {str(num_err)}"}, 400

        if total_ports < 1:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Total ports must be at least 1."}, 400
        if available_ports < 0 or available_ports > total_ports:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Available ports must be between 0 and total ports."}, 400
        if estimated_wait_minutes < 0:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Estimated wait time cannot be negative."}, 400

        cursor.execute(
            """
            UPDATE charging_stations SET
                station_name = %s,
                location = %s,
                distance_km = %s,
                charger_type = %s,
                capacity_kw = %s,
                available_ports = %s,
                total_ports = %s,
                estimated_wait_minutes = %s,
                demand_level = %s,
                latitude = %s,
                longitude = %s
            WHERE station_id = %s;
            """,
            (
                str(name).strip(), str(location).strip(), distance_km, str(charger_type).strip(),
                capacity_kw, available_ports, total_ports, estimated_wait_minutes,
                str(demand_level).strip(), latitude, longitude, station_id
            )
        )
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": f"Station #{station_id} updated successfully.",
            "station": {
                "station_id": station_id,
                "station_name": str(name).strip(),
                "location": str(location).strip(),
                "distance_km": distance_km,
                "charger_type": str(charger_type).strip(),
                "capacity_kw": capacity_kw,
                "available_ports": available_ports,
                "total_ports": total_ports,
                "estimated_wait_minutes": estimated_wait_minutes,
                "demand_level": str(demand_level).strip(),
                "latitude": latitude,
                "longitude": longitude
            }
        }, 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to update station: {str(e)}"}, 500

def admin_delete_station(station_id):
    """
    Delete an EV charging station record from MySQL.
    Admin-only operation with parameterized queries.
    """
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed."}, 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT station_name FROM charging_stations WHERE station_id = %s;", (station_id,))
        existing = cursor.fetchone()
        if not existing:
            cursor.close()
            conn.close()
            return {"success": False, "error": f"Station with ID {station_id} does not exist."}, 404

        name = existing["station_name"]
        cursor.execute("DELETE FROM charging_stations WHERE station_id = %s;", (station_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "message": f"Station #{station_id} ('{name}') was deleted successfully."
        }, 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return {"success": False, "error": f"Failed to delete station: {str(e)}"}, 500


