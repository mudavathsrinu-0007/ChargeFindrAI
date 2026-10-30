import os
import sys
import unittest

# Ensure ChargeFindrAI is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend.services.recommendation_service import calculate_station_score, get_station_recommendations


class TestModule3RecommendationEngine(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "user"
            sess["csrf_token"] = "test_csrf_token"

    # -------------------------------------------------------------------------
    # 1. INPUT VALIDATION & PRIORITY NORMALIZATION
    # -------------------------------------------------------------------------
    def test_01_non_string_inputs_return_http_400(self):
        """Non-string inputs for location, charger_type, and priority must return HTTP 400 (never 500)."""
        # Non-string location
        res = self.client.post("/api/recommend", json={"location": 12345})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["success"])
        self.assertIn("Invalid type for 'location'", res.get_json()["error"])

        # Non-string charger_type
        res = self.client.post("/api/recommend", json={"charger_type": ["Fast DC"]})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["success"])
        self.assertIn("Invalid type for 'charger_type'", res.get_json()["error"])

        # Non-string priority
        res = self.client.post("/api/recommend", json={"priority": 99})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["success"])
        self.assertIn("Invalid type for 'priority'", res.get_json()["error"])

    def test_02_priority_normalization_and_unsupported_values(self):
        """Valid priority strings must be normalized (case-insensitive); unsupported values return HTTP 400."""
        # Case insensitive normalization
        res_caps = self.client.post("/api/recommend", json={"priority": "FASTEST_CHARGER"})
        self.assertEqual(res_caps.status_code, 200)
        self.assertTrue(res_caps.get_json()["success"])
        self.assertEqual(res_caps.get_json()["data"]["user_criteria"]["priority"], "fastest_charger")

        res_title = self.client.post("/api/recommend", json={"priority": "  Balanced  "})
        self.assertEqual(res_title.status_code, 200)
        self.assertTrue(res_title.get_json()["success"])
        self.assertEqual(res_title.get_json()["data"]["user_criteria"]["priority"], "balanced")

        # Unsupported priority value
        res_unsupported = self.client.post("/api/recommend", json={"priority": "cheapest"})
        self.assertEqual(res_unsupported.status_code, 400)
        self.assertFalse(res_unsupported.get_json()["success"])
        self.assertIn("Unsupported priority value", res_unsupported.get_json()["error"])

    # -------------------------------------------------------------------------
    # 2. STATION AVAILABILITY & CONGESTION PENALTY
    # -------------------------------------------------------------------------
    def test_03_zero_port_station_cannot_outrank_open_station_merely_due_to_proximity(self):
        """A station with 0 available ports must not outrank a comparable operational station with open ports."""
        congested_close = {
            "station_id": 1,
            "station_name": "Full Hub",
            "location": "Madhapur, Hyderabad",
            "distance_km": 1.0,  # Very close
            "charger_type": "Fast DC",
            "capacity_kw": 60.0,
            "available_ports": 0,
            "total_ports": 4,
            "estimated_wait_minutes": 5,
            "demand_level": "Medium"
        }
        operational_farther = {
            "station_id": 2,
            "station_name": "Open Hub",
            "location": "Madhapur, Hyderabad",
            "distance_km": 7.0,  # 7 km away
            "charger_type": "Fast DC",
            "capacity_kw": 60.0,
            "available_ports": 2,
            "total_ports": 4,
            "estimated_wait_minutes": 10,
            "demand_level": "Medium"
        }

        score_congested, reasons_congested = calculate_station_score(
            congested_close, preferred_area="Madhapur, Hyderabad", preferred_charger="Fast DC"
        )
        score_operational, reasons_operational = calculate_station_score(
            operational_farther, preferred_area="Madhapur, Hyderabad", preferred_charger="Fast DC"
        )

        # Operational station with open ports must strictly outrank the congested station
        self.assertGreater(score_operational, score_congested)
        self.assertTrue(any("congested" in r.lower() for r in reasons_congested))
        self.assertTrue(any("2 of 4 ports currently available" in r for r in reasons_operational))

    # -------------------------------------------------------------------------
    # 3. BOUNDARY VALIDATION & SAFE CLAMPING
    # -------------------------------------------------------------------------
    def test_04_boundary_validation_negative_and_overflow_values(self):
        """Malformed or negative numbers must be safely clamped to valid ranges."""
        malformed = {
            "station_id": 10,
            "station_name": "Malformed Hub",
            "location": "Hyderabad",
            "distance_km": -5.0,  # Negative distance
            "charger_type": "Fast DC",
            "capacity_kw": -20.0,  # Negative capacity
            "available_ports": 10,  # Available exceeds total
            "total_ports": 4,
            "estimated_wait_minutes": -15,  # Negative wait
            "demand_level": "Medium"
        }
        score, reasons = calculate_station_score(malformed)
        self.assertIsInstance(score, float)
        self.assertLessEqual(score, 100.0)
        self.assertGreaterEqual(score, 0.0)
        # Bounded so it clamped available to 4 of 4
        self.assertTrue(any("4 of 4 ports" in r for r in reasons))
        # Non-negative wait time reason
        self.assertTrue(any("0 mins" in r for r in reasons))

    def test_05_unknown_wait_time_does_not_claim_zero(self):
        """If wait time is unknown (None), reasons must not claim it is 0 mins."""
        station_missing_wait = {
            "station_id": 11,
            "station_name": "No Wait Data Hub",
            "location": "Hyderabad",
            "distance_km": 4.0,
            "charger_type": "Fast DC",
            "capacity_kw": 50.0,
            "available_ports": 2,
            "total_ports": 4,
            "estimated_wait_minutes": None,
            "demand_level": "Medium"
        }
        score, reasons = calculate_station_score(station_missing_wait)
        self.assertTrue(any("wait time unknown" in r.lower() for r in reasons))
        self.assertFalse(any("0 mins" in r for r in reasons))

    # -------------------------------------------------------------------------
    # 4. EXPLANATION COMPLETENESS
    # -------------------------------------------------------------------------
    def test_06_explanations_cover_distance_demand_and_priority(self):
        """Reasons must transparently document distance proximity, high demand penalties, and priority bonuses."""
        station = {
            "station_id": 12,
            "station_name": "Proximity Hub",
            "location": "Madhapur, Hyderabad",
            "distance_km": 1.5,
            "charger_type": "Fast DC",
            "capacity_kw": 60.0,
            "available_ports": 3,
            "total_ports": 4,
            "estimated_wait_minutes": 5,
            "demand_level": "High"
        }
        # With fastest_charger priority
        score_fast, reasons_fast = calculate_station_score(station, priority="fastest_charger")
        self.assertTrue(any("close proximity" in r.lower() for r in reasons_fast))
        self.assertTrue(any("high demand" in r.lower() for r in reasons_fast))
        self.assertTrue(any("priority bonus" in r.lower() for r in reasons_fast))

        # With shortest_wait priority
        score_wait, reasons_wait = calculate_station_score(station, priority="shortest_wait")
        self.assertTrue(any("priority bonus: low queue wait" in r.lower() for r in reasons_wait))

    # -------------------------------------------------------------------------
    # 5. DETERMINISTIC RANKING & TIE-BREAKING
    # -------------------------------------------------------------------------
    def test_07_deterministic_tie_breaking(self):
        """When scores tie, rankings must break ties deterministically using wait mins, distance, and station ID."""
        res = get_station_recommendations({"location": "Any", "charger_type": "Any", "priority": "balanced"})
        recs = res["recommendations"]
        self.assertEqual(len(recs), 5)
        # Check consecutive ranks are 1..5
        ranks = [s["rank"] for s in recs]
        self.assertEqual(ranks, [1, 2, 3, 4, 5])
        # Ensure scores are non-increasing
        for i in range(len(recs) - 1):
            self.assertGreaterEqual(recs[i]["recommendation_score"], recs[i + 1]["recommendation_score"])


if __name__ == "__main__":
    unittest.main()

