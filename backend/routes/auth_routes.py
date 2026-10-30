import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session, make_response
from backend.services.auth_service import (
    register_user,
    authenticate_user,
    get_user_by_id,
    get_admin_system_overview,
    admin_get_all_users,
    admin_create_station,
    admin_update_station,
    admin_delete_station
)

auth_bp = Blueprint("auth_bp", __name__)

# ============================================================================
# AUTHORIZATION & CSRF DECORATORS
# ============================================================================

def login_required(f):
    """Ensure that the client possesses an active authenticated session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({
                "success": False,
                "error": "Authentication required. Please log in to access this resource."
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Ensure that the client is authenticated with administrator privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({
                "success": False,
                "error": "Authentication required. Please log in as an administrator."
            }), 401
        if session.get("role") != "admin":
            return jsonify({
                "success": False,
                "error": "Access denied. Administrator privileges are required."
            }), 403
        return f(*args, **kwargs)
    return decorated_function

def csrf_protect(f):
    """
    Validate CSRF token for state-changing HTTP methods (POST, PUT, DELETE, PATCH).
    Token is provided via 'X-CSRF-Token' request header and compared with session token.
    Uses secrets.compare_digest to prevent timing attacks.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            token_header = request.headers.get("X-CSRF-Token")
            token_session = session.get("csrf_token")

            if not token_header or not token_session or not secrets.compare_digest(str(token_header), str(token_session)):
                return jsonify({
                    "success": False,
                    "error": "Invalid or missing CSRF token. Request rejected."
                }), 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# AUTHENTICATION & CSRF ENDPOINTS
# ============================================================================

@auth_bp.route("/api/auth/csrf", methods=["GET"])
def get_csrf_token():
    """
    Issue or return the session CSRF token.
    Sets a non-HttpOnly readable cookie for SPA convenience while storing
    the canonical token in the encrypted/signed session.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    csrf_token = session["csrf_token"]
    response = make_response(jsonify({
        "success": True,
        "csrf_token": csrf_token
    }), 200)

    # Set cookie for client script accessibility (SameSite=Lax for CSRF prevention)
    response.set_cookie(
        "csrf_token",
        csrf_token,
        samesite="Lax",
        secure=request.is_secure,
        httponly=False
    )
    return response

@auth_bp.route("/api/auth/register", methods=["POST"])
@csrf_protect
def register():
    """
    Register a new user account.
    Security policy: Role is unconditionally set to 'user'. Any submitted role fields are ignored.
    """
    data = request.get_json(silent=True) or {}
    full_name = data.get("full_name")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    result, status_code = register_user(
        full_name=full_name,
        email=email,
        password=password,
        role="user",
        is_controlled_provision=False,
        confirm_password=confirm_password
    )
    return jsonify(result), status_code

@auth_bp.route("/api/auth/login", methods=["POST"])
@csrf_protect
def login():
    """
    Authenticate user credentials, clear old session state (fixation protection),
    and establish authenticated session identity with a fresh CSRF token.
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    result, status_code = authenticate_user(email, password)
    if status_code != 200:
        return jsonify(result), status_code

    user = result["user"]

    # 1. Clear any prior unauthenticated/stale session (prevents session fixation attacks)
    session.clear()
    session.permanent = True

    # 2. Assign authenticated session identity
    session["user_id"] = user["user_id"]
    session["user_name"] = user["full_name"]
    session["role"] = user["role"]

    # 3. Rotate and issue fresh CSRF token for the authenticated session
    fresh_csrf = secrets.token_hex(32)
    session["csrf_token"] = fresh_csrf

    response = make_response(jsonify({
        "success": True,
        "message": f"Welcome back, {user['full_name']}!",
        "user": user,
        "csrf_token": fresh_csrf
    }), 200)

    response.set_cookie(
        "csrf_token",
        fresh_csrf,
        samesite="Lax",
        secure=request.is_secure,
        httponly=False
    )
    return response

@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
@csrf_protect
def logout():
    """
    Terminate active user session and purge all stored session identifiers.
    """
    session.clear()
    # Issue a fresh guest CSRF token on logout
    new_csrf = secrets.token_hex(32)
    session["csrf_token"] = new_csrf

    response = make_response(jsonify({
        "success": True,
        "message": "Logged out successfully.",
        "csrf_token": new_csrf
    }), 200)

    response.set_cookie(
        "csrf_token",
        new_csrf,
        samesite="Lax",
        secure=request.is_secure,
        httponly=False
    )
    return response

@auth_bp.route("/api/auth/me", methods=["GET"])
def get_current_user():
    """
    Inspect current session status and return authenticated user identity.
    If unauthenticated, returns guest status without throwing an error.
    """
    # Ensure CSRF token is present in session
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({
            "success": True,
            "authenticated": False,
            "user": None,
            "csrf_token": session["csrf_token"]
        }), 200

    user = get_user_by_id(user_id)
    if not user:
        # User record may have been deleted from DB
        session.clear()
        session["csrf_token"] = secrets.token_hex(32)
        return jsonify({
            "success": True,
            "authenticated": False,
            "user": None,
            "csrf_token": session["csrf_token"]
        }), 200

    return jsonify({
        "success": True,
        "authenticated": True,
        "user": {
            "user_id": user["user_id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"]
        },
        "csrf_token": session["csrf_token"]
    }), 200

# ============================================================================
# DEMONSTRATION ADMIN ROUTE (ROLE-BASED ACCESS CONTROL)
# ============================================================================

@auth_bp.route("/api/admin/overview", methods=["GET"])
@admin_required
def admin_overview():
    """
    Administrative system telemetry endpoint.
    Protected strictly by @admin_required.
    Guests receive HTTP 401; authenticated non-admin users receive HTTP 403.
    """
    overview = get_admin_system_overview()
    if not overview:
        return jsonify({
            "success": False,
            "error": "Failed to retrieve system overview from database."
        }), 500

    return jsonify({
        "success": True,
        "message": "Administrative system telemetry retrieved successfully.",
        "data": overview
    }), 200

@auth_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_users():
    """List all registered users (admin-only)."""
    users = admin_get_all_users()
    if users is None:
        return jsonify({
            "success": False,
            "error": "Failed to fetch user list from database."
        }), 500
    return jsonify({
        "success": True,
        "count": len(users),
        "data": users
    }), 200

@auth_bp.route("/api/admin/stations", methods=["POST"])
@admin_required
@csrf_protect
def admin_add_station():
    """Create a new EV charging station record (admin-only)."""
    data = request.get_json(silent=True) or {}
    result, status_code = admin_create_station(data)
    return jsonify(result), status_code

@auth_bp.route("/api/admin/stations/<int:station_id>", methods=["PUT"])
@admin_required
@csrf_protect
def admin_edit_station(station_id):
    """Update an existing EV charging station record (admin-only)."""
    data = request.get_json(silent=True) or {}
    result, status_code = admin_update_station(station_id, data)
    return jsonify(result), status_code

@auth_bp.route("/api/admin/stations/<int:station_id>", methods=["DELETE"])
@admin_required
@csrf_protect
def admin_remove_station(station_id):
    """Delete an EV charging station record (admin-only)."""
    result, status_code = admin_delete_station(station_id)
    return jsonify(result), status_code

