import os
import sys
from datetime import timedelta
from flask import Flask, jsonify, send_from_directory, request

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database.db_config import _load_env_file, ensure_users_table, ensure_booking_and_queue_tables
from backend.routes.station_routes import station_bp
from backend.routes.recommendation_routes import recommendation_bp
from backend.routes.demand_routes import demand_bp
from backend.routes.auth_routes import auth_bp
from backend.routes.booking_routes import booking_bp
from backend.routes.queue_routes import queue_bp

# Ensure .env is loaded
_load_env_file()

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# ============================================================================
# FLASK SESSION SECURITY CONFIGURATION
# ============================================================================
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "CRITICAL SECURITY CONFIGURATION ERROR: 'SECRET_KEY' is not set in the environment or .env file. "
        "Flask session security cannot start without a cryptographically strong SECRET_KEY."
    )
app.secret_key = secret_key

is_production = os.getenv("FLASK_ENV") == "production"
cookie_secure_env = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(is_production or cookie_secure_env),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.getenv("SESSION_LIFETIME_HOURS", "8"))),
)

# ============================================================================
# CORS & CREDENTIAL RESTRICTIONS
# ============================================================================
DEFAULT_TRUSTED_ORIGINS = {
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:3000",
    "http://localhost:3000"
}
env_origins = os.getenv("TRUSTED_ORIGINS")
if env_origins:
    TRUSTED_ORIGINS = {o.strip() for o in env_origins.split(",") if o.strip()}
else:
    TRUSTED_ORIGINS = DEFAULT_TRUSTED_ORIGINS

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and origin in TRUSTED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    else:
        # Same-origin or non-trusted: allow necessary headers without credential sharing
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

# Ensure users and booking/queue tables are initialized
ensure_users_table()
ensure_booking_and_queue_tables()

# Register API blueprints
app.register_blueprint(station_bp)
app.register_blueprint(recommendation_bp)
app.register_blueprint(demand_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(queue_bp)

# Root route: serve frontend index.html if it exists, otherwise return API info
@app.route("/", methods=["GET"])
def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({
        "message": "Welcome to ChargeFindr AI API",
        "endpoints": {
            "health": "/api/health",
            "stations": "/api/stations",
            "locations": "/api/stations/locations",
            "alerts": "/api/stations/alerts",
            "recommend": "/api/recommend",
            "demand": "/api/demand",
            "demand_metadata": "/api/demand/metadata",
            "auth_csrf": "/api/auth/csrf",
            "auth_register": "/api/auth/register",
            "auth_login": "/api/auth/login",
            "auth_logout": "/api/auth/logout",
            "auth_me": "/api/auth/me",
            "admin_overview": "/api/admin/overview",
            "admin_users": "/api/admin/users",
            "admin_stations": "/api/admin/stations",
            "available_slots": "/api/bookings/available-slots",
            "create_booking": "/api/bookings",
            "my_bookings": "/api/bookings/my",
            "cancel_booking": "/api/bookings/<id>/cancel",
            "booking_alternatives": "/api/bookings/<id>/alternatives",
            "queue_status": "/api/queue/status/<station_id>",
            "join_queue": "/api/queue/join",
            "my_queue": "/api/queue/my",
            "cancel_queue": "/api/queue/<id>/cancel"
        }
    })

# Generic 404 handler
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

# Generic 500 handler
@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    print("==================================================")
    print(" Starting ChargeFindr AI Backend Server")
    print(" Running on: http://127.0.0.1:5000")
    print(" API Health: http://127.0.0.1:5000/api/health")
    print(" Stations:   http://127.0.0.1:5000/api/stations")
    print(" Auth CSRF:  http://127.0.0.1:5000/api/auth/csrf")
    print("==================================================")
    app.run(host="127.0.0.1", port=5000, debug=True)
