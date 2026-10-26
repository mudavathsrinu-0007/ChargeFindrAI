import re
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database.db_config import get_db_connection

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_registration_input(full_name, email, password):
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

    return True, None, name_clean, email_clean

def register_user(full_name, email, password, role="user", is_controlled_provision=False):
    """
    Register a new user in the MySQL database.
    Security guarantee: Public callers cannot set an administrative role.
    Role is strictly hardcoded to 'user' unless is_controlled_provision is explicitly True.
    Returns: (dict_response, http_status_code)
    """
    is_valid, err_msg, name_clean, email_clean = validate_registration_input(full_name, email, password)
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

