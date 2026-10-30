from flask import Blueprint, request, jsonify, session
from backend.routes.auth_routes import login_required, admin_required, csrf_protect
from backend.services.queue_service import (
    get_station_queue_status,
    join_queue,
    get_user_active_ticket,
    cancel_queue_ticket,
    admin_get_all_queues
)

queue_bp = Blueprint("queue_bp", __name__)

@queue_bp.route("/api/queue/status/<int:station_id>", methods=["GET"])
@login_required
def route_station_queue_status(station_id):
    """
    Get live queue status for a charging station (waiting drivers, walk-in ports, wait time).
    """
    result, status_code = get_station_queue_status(station_id)
    return jsonify(result), status_code

@queue_bp.route("/api/queue/join", methods=["POST"])
@login_required
@csrf_protect
def route_join_queue():
    """
    Join the rapid walk-in charging queue.
    Enforces duplicate active ticket prevention (HTTP 409) and FIFO order.
    """
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}

    result, status_code = join_queue(user_id, data)
    return jsonify(result), status_code

@queue_bp.route("/api/queue/my", methods=["GET"])
@login_required
def route_my_queue_ticket():
    """
    Fetch the currently authenticated user's active walk-in ticket with dynamic position.
    """
    user_id = session.get("user_id")
    result, status_code = get_user_active_ticket(user_id)
    return jsonify(result), status_code

@queue_bp.route("/api/queue/<int:queue_id>/cancel", methods=["POST"])
@login_required
@csrf_protect
def route_cancel_queue(queue_id):
    """
    Leave/cancel an active walk-in queue ticket.
    """
    user_id = session.get("user_id")
    is_admin = (session.get("role") == "admin")

    result, status_code = cancel_queue_ticket(user_id, queue_id, is_admin=is_admin)
    return jsonify(result), status_code

@queue_bp.route("/api/admin/queues", methods=["GET"])
@admin_required
def route_admin_queues():
    """
    Administrator overview of active and recent walk-in queues.
    """
    station_id = request.args.get("station_id")
    result, status_code = admin_get_all_queues(station_id)
    return jsonify(result), status_code

