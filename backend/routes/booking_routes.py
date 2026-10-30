from flask import Blueprint, request, jsonify, session
from backend.routes.auth_routes import login_required, admin_required, csrf_protect
from backend.services.booking_service import (
    get_available_slots,
    create_booking,
    get_user_bookings,
    cancel_booking,
    get_alternative_slots,
    admin_get_all_bookings
)

booking_bp = Blueprint("booking_bp", __name__)

@booking_bp.route("/api/bookings/available-slots", methods=["GET"])
@login_required
def route_available_slots():
    """
    Query available charging slots for a given station and date.
    Query params:
        station_id (int)
        date (YYYY-MM-DD)
        duration (int: 30, 60, 90, 120 - default 60)
    """
    station_id = request.args.get("station_id")
    date_str = request.args.get("date")
    duration = request.args.get("duration", 60)

    if not station_id or not date_str:
        return jsonify({
            "success": False,
            "error": "Query parameters 'station_id' and 'date' (YYYY-MM-DD) are required."
        }), 400

    result, status_code = get_available_slots(station_id, date_str, duration)
    return jsonify(result), status_code

@booking_bp.route("/api/bookings", methods=["POST"])
@login_required
@csrf_protect
def route_create_booking():
    """
    Create a new reserved charging slot.
    Guarantees concurrency isolation, physical port assignment, and double-booking prevention.
    """
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}

    result, status_code = create_booking(user_id, data)
    return jsonify(result), status_code

@booking_bp.route("/api/bookings/my", methods=["GET"])
@login_required
def route_my_bookings():
    """
    Retrieve all bookings for the currently authenticated user.
    """
    user_id = session.get("user_id")
    result, status_code = get_user_bookings(user_id)
    return jsonify(result), status_code

@booking_bp.route("/api/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
@csrf_protect
def route_cancel_booking(booking_id):
    """
    Cancel a confirmed reservation subject to the 30-minute advance cancellation policy.
    """
    user_id = session.get("user_id")
    is_admin = (session.get("role") == "admin")
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Cancelled by user")

    result, status_code = cancel_booking(user_id, booking_id, reason=reason, is_admin=is_admin)
    return jsonify(result), status_code

@booking_bp.route("/api/bookings/<int:booking_id>/alternatives", methods=["GET"])
@login_required
def route_alternative_slots(booking_id):
    """
    Retrieve recommended alternative slots for a missed booking.
    """
    user_id = session.get("user_id")
    result, status_code = get_alternative_slots(user_id, booking_id)
    return jsonify(result), status_code

@booking_bp.route("/api/admin/bookings", methods=["GET"])
@admin_required
def route_admin_bookings():
    """
    Admin overview: list all bookings across all stations.
    """
    result, status_code = admin_get_all_bookings()
    return jsonify(result), status_code

