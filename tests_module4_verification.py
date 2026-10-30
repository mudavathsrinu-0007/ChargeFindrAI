import os
import sys
import unittest

# Ensure ChargeFindrAI is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend.services.demand_service import predict_demand, get_model_metadata, categorize_demand


class TestModule4DemandPrediction(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "user"

    # -------------------------------------------------------------------------
    # 1. SAFE LOCATION HANDLING
    # -------------------------------------------------------------------------
    def test_01_safe_location_handling_null_and_empty(self):
        """predict_demand must safely handle location=None and empty strings without crashing."""
        # 1. location=None
        res_null = predict_demand(hour=14, day_of_week=2, location=None)
        self.assertIsInstance(res_null, dict)
        self.assertTrue(res_null["is_ml_model"])
        self.assertIn("Public Area", res_null["location_benchmark"])

        # 2. location=""
        res_empty = predict_demand(hour=14, day_of_week=2, location="")
        self.assertIsInstance(res_empty, dict)
        self.assertTrue(res_empty["is_ml_model"])

    # -------------------------------------------------------------------------
    # 2. INPUT VALIDATION (HOUR & DAY_OF_WEEK)
    # -------------------------------------------------------------------------
    def test_02_hour_validation_valid_and_invalid(self):
        """GET /api/demand must accept hours 0-23 and reject out-of-range or malformed values with HTTP 400."""
        # Valid boundaries: 0 and 23
        res_0 = self.client.get("/api/demand?hour=0")
        self.assertEqual(res_0.status_code, 200)
        self.assertEqual(res_0.get_json()["data"]["hour"], 0)

        res_23 = self.client.get("/api/demand?hour=23")
        self.assertEqual(res_23.status_code, 200)
        self.assertEqual(res_23.get_json()["data"]["hour"], 23)

        # Out-of-range hours: -1, 24, 99
        res_neg = self.client.get("/api/demand?hour=-1")
        self.assertEqual(res_neg.status_code, 400)
        self.assertFalse(res_neg.get_json()["success"])
        self.assertIn("hour", res_neg.get_json()["error"].lower())

        res_24 = self.client.get("/api/demand?hour=24")
        self.assertEqual(res_24.status_code, 400)
        self.assertFalse(res_24.get_json()["success"])

        res_99 = self.client.get("/api/demand?hour=99")
        self.assertEqual(res_99.status_code, 400)

        # Malformed hours: "abc", "12.5"
        res_str = self.client.get("/api/demand?hour=midday")
        self.assertEqual(res_str.status_code, 400)

    def test_03_day_of_week_validation_valid_and_invalid(self):
        """GET /api/demand must accept day_of_week 0-6 and reject out-of-range or malformed values with HTTP 400."""
        # Valid boundaries: 0 (Monday) and 6 (Sunday)
        res_mon = self.client.get("/api/demand?day_of_week=0")
        self.assertEqual(res_mon.status_code, 200)
        self.assertEqual(res_mon.get_json()["data"]["day_of_week"], 0)

        res_sun = self.client.get("/api/demand?day_of_week=6")
        self.assertEqual(res_sun.status_code, 200)
        self.assertEqual(res_sun.get_json()["data"]["day_of_week"], 6)

        # Out-of-range: -1, 7, 99
        res_neg = self.client.get("/api/demand?day_of_week=-1")
        self.assertEqual(res_neg.status_code, 400)
        self.assertFalse(res_neg.get_json()["success"])

        res_7 = self.client.get("/api/demand?day_of_week=7")
        self.assertEqual(res_7.status_code, 400)

        # Malformed: "friday"
        res_str = self.client.get("/api/demand?day_of_week=friday")
        self.assertEqual(res_str.status_code, 400)

    # -------------------------------------------------------------------------
    # 3. ACCURATE DEMAND ADVISORY LABELS
    # -------------------------------------------------------------------------
    def test_04_categorize_demand_accurate_session_energy_advisory(self):
        """categorize_demand messages must not describe high session kWh as proof of station congestion."""
        # Low demand (< 12 kWh)
        lvl_low, adv_low = categorize_demand(10.5)
        self.assertEqual(lvl_low, "Low")
        self.assertIn("rapid", adv_low.lower())

        # Medium demand (12 - 20 kWh)
        lvl_med, adv_med = categorize_demand(16.0)
        self.assertEqual(lvl_med, "Medium")
        self.assertIn("regular", adv_med.lower())

        # High demand (> 20 kWh)
        lvl_high, adv_high = categorize_demand(25.0)
        self.assertEqual(lvl_high, "High")
        self.assertIn("longer", adv_high.lower())
        self.assertIn("session", adv_high.lower())
        # Ensure it does NOT claim station queue or physical station congestion
        self.assertNotIn("queue probability", adv_high.lower())
        self.assertNotIn("grid load", adv_high.lower())

    # -------------------------------------------------------------------------
    # 4. FORECAST TERMINOLOGY & METADATA CONTRACT
    # -------------------------------------------------------------------------
    def test_05_forecast_terminology_and_metadata_contract(self):
        """API response must clearly identify 24-hr hourly profile and location benchmark."""
        res = self.client.get("/api/demand?hour=15&day_of_week=3&charger_type=Fast%20DC")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]

        # Clarified forecast type & benchmark
        self.assertIn("forecast_type", data)
        self.assertIn("Hourly Sensitivity Profile", data["forecast_type"])
        self.assertIn("location_benchmark", data)
        self.assertIn("Public Area", data["location_benchmark"])

        # Preserved core fields
        self.assertIn("predicted_demand_kwh", data)
        self.assertIn("demand_level", data)
        self.assertIn("advisory", data)
        self.assertIn("hourly_curve", data)
        self.assertEqual(len(data["hourly_curve"]), 24)

        # Metadata contract
        meta = data["metadata"]
        self.assertEqual(meta["train_samples"], 58284)
        self.assertEqual(meta["test_samples"], 14572)
        self.assertEqual(meta["metrics"]["MAE"], 10.2878)
        self.assertEqual(meta["metrics"]["RMSE"], 13.4438)
        self.assertEqual(meta["metrics"]["R2_Score"], 0.0667)


if __name__ == "__main__":
    unittest.main()

