from flask import Blueprint, request, jsonify
from backend.services.demand_service import predict_demand, get_model_metadata

demand_bp = Blueprint("demand_bp", __name__)

@demand_bp.route("/api/demand", methods=["GET"])
def get_demand_prediction():
    """
    Return charging demand predictions and 24-hour forecast curve.
    Optional query parameters:
      - hour: int (0 to 23)
      - day_of_week: int (0=Monday, 6=Sunday)
      - charger_type: str ("Fast DC" or "AC Type 2")
      - location: str ("public area", "apartment", etc.)
    """
    try:
        hour_param = request.args.get("hour")
        hour = int(hour_param) if hour_param is not None and hour_param.isdigit() else None

        dow_param = request.args.get("day_of_week")
        day_of_week = int(dow_param) if dow_param is not None and dow_param.isdigit() else None

        charger_type = request.args.get("charger_type", "Fast DC")
        location = request.args.get("location", "public area")

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


