from flask import Blueprint, request, jsonify
from backend.services.recommendation_service import get_station_recommendations
from backend.routes.auth_routes import login_required

recommendation_bp = Blueprint("recommendation_bp", __name__)

VALID_PRIORITIES = {"balanced", "fastest_charger", "shortest_wait"}

@recommendation_bp.route("/api/recommend", methods=["POST", "GET"])
@login_required
def recommend_stations():
    """
    Accept user criteria and return ranked charging stations with transparent reasoning.
    Accepts JSON body: { "location": "Madhapur", "charger_type": "Fast DC", "priority": "balanced" }
    """
    try:
        criteria = {}
        if request.method == "POST":
            # Reject non-JSON Content-Type when request body is present
            if request.data and not request.is_json:
                return jsonify({
                    "success": False,
                    "error": "Request body must be valid application/json."
                }), 400

            criteria = request.get_json(silent=True)
            if criteria is None and request.data.strip():
                return jsonify({
                    "success": False,
                    "error": "Malformed JSON payload."
                }), 400

            criteria = criteria or {}
            if not isinstance(criteria, dict):
                return jsonify({
                    "success": False,
                    "error": "Request payload must be a JSON object."
                }), 400

        elif request.method == "GET":
            criteria = {
                "location": request.args.get("location", "Any"),
                "charger_type": request.args.get("charger_type", "Any"),
                "priority": request.args.get("priority", "balanced")
            }

        # 1. Type validation for location
        raw_location = criteria.get("location", "Any")
        if raw_location is None:
            location = "Any"
        elif isinstance(raw_location, str):
            location = raw_location.strip() or "Any"
        else:
            return jsonify({
                "success": False,
                "error": f"Invalid type for 'location': expected string, received {type(raw_location).__name__}."
            }), 400

        # 2. Type validation for charger_type
        raw_charger = criteria.get("charger_type", "Any")
        if raw_charger is None:
            charger_type = "Any"
        elif isinstance(raw_charger, str):
            charger_type = raw_charger.strip() or "Any"
        else:
            return jsonify({
                "success": False,
                "error": f"Invalid type for 'charger_type': expected string, received {type(raw_charger).__name__}."
            }), 400

        # 3. Type and value validation for priority (normalized with strip().lower())
        raw_priority = criteria.get("priority", "balanced")
        if raw_priority is None:
            priority = "balanced"
        elif isinstance(raw_priority, str):
            priority = raw_priority.strip().lower()
            if priority not in VALID_PRIORITIES:
                return jsonify({
                    "success": False,
                    "error": f"Unsupported priority value: '{raw_priority}'. "
                             f"Accepted values: {', '.join(sorted(VALID_PRIORITIES))}."
                }), 400
        else:
            return jsonify({
                "success": False,
                "error": f"Invalid type for 'priority': expected string, received {type(raw_priority).__name__}."
            }), 400

        validated_criteria = {
            "location": location,
            "charger_type": charger_type,
            "priority": priority
        }

        result = get_station_recommendations(validated_criteria)
        return jsonify({
            "success": True,
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to compute recommendations: {str(e)}"
        }), 500

