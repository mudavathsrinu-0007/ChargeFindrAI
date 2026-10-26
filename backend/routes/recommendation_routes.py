from flask import Blueprint, request, jsonify
from backend.services.recommendation_service import get_station_recommendations

recommendation_bp = Blueprint("recommendation_bp", __name__)

@recommendation_bp.route("/api/recommend", methods=["POST", "GET"])
def recommend_stations():
    """
    Accept user criteria and return ranked charging stations with transparent reasoning.
    Accepts JSON body: { "location": "Madhapur", "charger_type": "Fast DC", "priority": "balanced" }
    """
    try:
        criteria = {}
        if request.method == "POST":
            criteria = request.get_json(silent=True) or {}
        elif request.method == "GET":
            criteria = {
                "location": request.args.get("location", "Any"),
                "charger_type": request.args.get("charger_type", "Any"),
                "priority": request.args.get("priority", "balanced")
            }

        result = get_station_recommendations(criteria)
        return jsonify({
            "success": True,
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to compute recommendations: {str(e)}"
        }), 500

