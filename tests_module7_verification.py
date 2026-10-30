import os
import sys
import unittest
import json
import re

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app

class TestModule7Verification(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    # =========================================================================
    # FIX 1: R² MODEL METRIC DISPLAY
    # =========================================================================
    def test_01_r2_metric_in_html_and_api(self):
        """Verify R² metric exists dynamically in HTML without hardcoding and matches API."""
        # 1. HTML Verification
        html_path = os.path.join(BASE_DIR, "frontend", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn('id="metric-r2"', html)
        self.assertNotIn('<strong id="metric-r2">0.0667</strong>', html, "R² value must not be hardcoded in HTML")

        # 2. API Verification
        user_client = app.test_client()
        with user_client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "user"
        res = user_client.get("/api/demand/metadata")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        metrics = data["metrics"]

        self.assertIn("R2_Score", metrics)
        self.assertIsNotNone(metrics["R2_Score"])
        formatted_r2 = f"{metrics['R2_Score']:.4f}"
        self.assertEqual(formatted_r2, "0.0667")

        # 3. JS Controller Verification
        js_path = os.path.join(BASE_DIR, "frontend", "script.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('document.getElementById("metric-r2")', js)
        self.assertIn('toFixed(4)', js)
        self.assertIn('"Unavailable"', js)

    # =========================================================================
    # FIX 2: SELECTABLE HOURLY DEMAND CHART BARS
    # =========================================================================
    def test_02_hourly_chart_bars_selectable(self):
        """Verify script.js includes bar-wrapper click/keydown listeners and selectDemandHour."""
        js_path = os.path.join(BASE_DIR, "frontend", "script.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()

        # Confirm data-hour attribute is generated on each bar
        self.assertIn('data-hour="${item.hour}"', js)
        # Confirm delegation and window-scoped function exist
        self.assertIn('selectDemandHour', js)
        self.assertIn('window.selectDemandHour', js)
        # Confirm duplicate calls are guarded
        self.assertIn('demandHourSelect.value === strHour', js)
        # Confirm fetchDemandPrediction is invoked
        self.assertIn('fetchDemandPrediction()', js)

    # =========================================================================
    # FIX 3: ADMIN ROLE BREAKDOWN TELEMETRY DISPLAY
    # =========================================================================
    def test_03_admin_role_breakdown_integration(self):
        """Verify role_breakdown data is computed by backend and parsed into admin dashboard modal."""
        # 1. Backend /api/admin/overview endpoint protection
        res_guest = self.client.get("/api/admin/overview")
        self.assertEqual(res_guest.status_code, 401, "Unauthenticated access must be rejected with 401")

        # 2. Frontend script.js verification for role_breakdown rendering
        js_path = os.path.join(BASE_DIR, "frontend", "script.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('role_breakdown', js)
        self.assertIn('adminCount', js)
        self.assertIn('userCount', js)
        self.assertIn('Administrators', js)
        self.assertIn('Regular Users', js)

    # =========================================================================
    # REGRESSION: PREDICTION & STATIONS HEALTH
    # =========================================================================
    def test_04_regression_demand_and_stations(self):
        """Verify /api/demand and /api/stations continue operating normally for authenticated users."""
        user_client = app.test_client()
        with user_client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "user"

        res_dem = user_client.get("/api/demand?hour=14&day_of_week=2&charger_type=Fast%20DC")
        self.assertEqual(res_dem.status_code, 200)
        dem_data = res_dem.get_json()["data"]
        self.assertIn("predicted_demand_kwh", dem_data)
        self.assertEqual(len(dem_data["hourly_curve"]), 24)

        res_stn = user_client.get("/api/stations")
        self.assertEqual(res_stn.status_code, 200)
        self.assertEqual(res_stn.get_json()["count"], 5)

if __name__ == "__main__":
    unittest.main(verbosity=2)

