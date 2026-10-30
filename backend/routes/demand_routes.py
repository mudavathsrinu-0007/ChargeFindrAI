from flask import Blueprint, request, jsonify
from backend.services.demand_service import predict_demand, get_model_metadata
from backend.routes.auth_routes import login_required

demand_bp = Blueprint("demand_bp", __name__)

@demand_bp.route("/api/demand", methods=["GET"])
@login_required
def get_demand_prediction():
    """
    Return charging demand predictions and 24-hour illustrative hourly forecast profile.
    Optional query parameters:
      - hour: int (0 to 23)
      - day_of_week: int (0=Monday, 6=Sunday)
      - charger_type: str ("Fast DC" or "AC Type 2")
      - location: str ("public area", "apartment", etc.)
    """
    try:
        # Validate hour (0 to 23)
        hour = None
        hour_param = request.args.get("hour")
        if hour_param is not None and hour_param.strip() != "":
            try:
                hour = int(hour_param)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": f"Invalid 'hour': '{hour_param}' must be an integer between 0 and 23."
                }), 400
            if hour < 0 or hour > 23:
                return jsonify({
                    "success": False,
                    "error": f"Out-of-range 'hour': {hour} must be an integer between 0 and 23."
                }), 400

        # Validate day_of_week (0 to 6)
        day_of_week = None
        dow_param = request.args.get("day_of_week")
        if dow_param is not None and dow_param.strip() != "":
            try:
                day_of_week = int(dow_param)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": f"Invalid 'day_of_week': '{dow_param}' must be an integer between 0 and 6."
                }), 400
            if day_of_week < 0 or day_of_week > 6:
                return jsonify({
                    "success": False,
                    "error": f"Out-of-range 'day_of_week': {day_of_week} must be an integer between 0 (Monday) and 6 (Sunday)."
                }), 400

        charger_type = request.args.get("charger_type") or "Fast DC"
        location = request.args.get("location") or "public area"

        result = predict_demand(
            hour=hour,
            day_of_week=day_of_week,
            charger_type=charger_type,
            location=location
        )

        return jsonify({
            "success": True,
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Demand prediction failed: {str(e)}"
        }), 500

@demand_bp.route("/api/demand/metadata", methods=["GET"])
@login_required
def get_demand_metadata():
    """Return model evaluation metrics and chronological training split metadata."""
    try:
        meta = get_model_metadata()
        return jsonify({
            "success": True,
            "data": meta
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to retrieve model metadata: {str(e)}"
        }), 500


