import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app

class TestStage5Alerts(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    # =========================================================================
    # PART 1: LIVE DATABASE VERIFICATION
    # =========================================================================
    def test_01_live_db_alerts_endpoint(self):
        """Test GET /api/stations/alerts against live MySQL database."""
        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        print("\n--- LIVE DATABASE ALERT RESPONSE ---")
        print(f"Status: {response.status_code}")
        print(f"Success: {data.get('success')}")
        print(f"Has Alert: {data.get('has_alert')}")
        print(f"Alert Count: {data.get('count')}")
        print(f"Is Sample Data: {data.get('is_sample_data')}")
        print(f"Note: {data.get('note')}")

        # Required fields in response
        self.assertTrue(data.get("success"))
        self.assertIn("has_alert", data)
        self.assertIn("count", data)
        self.assertIn("alerts", data)
        self.assertIn("is_sample_data", data)
        self.assertTrue(data.get("is_sample_data"))

        # In current DB: VoltWay Charging (ID 4) has 0 ports, 25 min wait (Congested)
        self.assertTrue(data.get("has_alert"))
        self.assertGreaterEqual(data.get("count"), 1)

        alert = data["alerts"][0]
        congested = alert["congested_station"]
        alt = alert["recommended_alternative"]

        print(f"Congested Station: {congested.get('station_name')} (Ports: {congested.get('available_ports')}, Wait: {congested.get('estimated_wait_minutes')}m)")
        print(f"Alternative: {alt.get('station_name') if alt else 'None'} (Ports: {alt.get('available_ports') if alt else 'N/A'}, Wait: {alt.get('estimated_wait_minutes') if alt else 'N/A'}m)")
        print(f"Message: {alert.get('message')}")

        self.assertEqual(congested.get("station_name"), "VoltWay Charging")
        self.assertEqual(congested.get("available_ports"), 0)
        self.assertGreater(congested.get("estimated_wait_minutes"), 20)

        # Alternative must be GreenCharge Hub (ID 1, 3 ports, 5 mins)
        self.assertIsNotNone(alt)
        self.assertEqual(alt.get("station_name"), "GreenCharge Hub")
        self.assertGreater(alt.get("available_ports"), 1)
        self.assertLessEqual(alt.get("estimated_wait_minutes"), 8)
        self.assertNotEqual(alt.get("station_id"), congested.get("station_id"))

    # =========================================================================
    # PART 2: ISOLATED MOCKED TESTS (NON-DESTRUCTIVE EDGE CASES)
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_02_no_congested_stations(self, mock_get_conn):
        """Case A: When all stations have available ports and low wait times, no alerts should fire."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 1, "station_name": "Station A", "location": "Area A",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.44"), "longitude": Decimal("78.38")
            },
            {
                "station_id": 2, "station_name": "Station B", "location": "Area B",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 2, "total_ports": 4, "estimated_wait_minutes": 10,
                "demand_level": "Medium", "latitude": Decimal("17.45"), "longitude": Decimal("78.39")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data.get("success"))
        self.assertFalse(data.get("has_alert"))
        self.assertEqual(data.get("count"), 0)
        self.assertEqual(data.get("alerts"), [])

    @patch("backend.routes.station_routes.get_db_connection")
    def test_03_congested_station_no_suitable_alternative(self, mock_get_conn):
        """Case B: When congested station exists, but no other stations meet alternative criteria (>1 port, <=8 min wait)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 1, "station_name": "Congested Stn", "location": "Area A",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 30,
                "demand_level": "High", "latitude": Decimal("17.44"), "longitude": Decimal("78.38")
            },
            {
                "station_id": 2, "station_name": "Busy Stn B", "location": "Area B",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 1, "total_ports": 4, "estimated_wait_minutes": 15,  # only 1 port, 15m wait (not eligible)
                "demand_level": "High", "latitude": Decimal("17.45"), "longitude": Decimal("78.39")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("has_alert"))
        self.assertEqual(data.get("count"), 1)
        alert = data["alerts"][0]
        self.assertIsNone(alert.get("recommended_alternative"))
        self.assertIn("No low-wait alternative currently available", alert.get("message"))

    @patch("backend.routes.station_routes.get_db_connection")
    def test_04_congestion_by_high_wait_time_only(self, mock_get_conn):
        """Case C: Station has available ports (>0) but wait time > 20 mins, so it is congested."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 10, "station_name": "Long Queue Stn", "location": "Area X",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 2, "total_ports": 6, "estimated_wait_minutes": 35,  # wait > 20 mins
                "demand_level": "High", "latitude": Decimal("17.44"), "longitude": Decimal("78.38")
            },
            {
                "station_id": 11, "station_name": "Quick Stn Y", "location": "Area Y",
                "distance_km": Decimal("3.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 4, "total_ports": 6, "estimated_wait_minutes": 3,
                "demand_level": "Low", "latitude": Decimal("17.45"), "longitude": Decimal("78.39")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data.get("has_alert"))
        congested = data["alerts"][0]["congested_station"]
        self.assertEqual(congested.get("station_id"), 10)
        self.assertIn("35 mins wait", congested.get("reason"))
        self.assertEqual(data["alerts"][0]["recommended_alternative"]["station_id"], 11)

    @patch("backend.routes.station_routes.get_db_connection")
    def test_05_empty_database(self, mock_get_conn):
        """Case D: Empty database returns has_alert=False and count=0."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data.get("success"))
        self.assertFalse(data.get("has_alert"))
        self.assertEqual(data.get("count"), 0)
        self.assertEqual(data.get("alerts"), [])

    @patch("backend.routes.station_routes.get_db_connection")
    def test_06_db_connection_failure(self, mock_get_conn):
        """Case E: Database connection failure returns HTTP 500 cleanly."""
        mock_get_conn.return_value = None

        response = self.client.get("/api/stations/alerts")
        self.assertEqual(response.status_code, 500)
        data = response.get_json()

        self.assertFalse(data.get("success"))
        self.assertFalse(data.get("has_alert"))
        self.assertIn("Database connection failed", data.get("error"))

    # =========================================================================
    # PART 3: REGRESSION TEST FOR EXISTING ENDPOINTS
    # =========================================================================
    def test_07_regression_existing_endpoints(self):
        """Confirm all previously implemented endpoints continue to function without degradation."""
        # 1. Health
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.get_json().get("database"), "connected")

        # 2. Stations
        res_stations = self.client.get("/api/stations")
        self.assertEqual(res_stations.status_code, 200)
        self.assertEqual(res_stations.get_json().get("count"), 5)

        # 3. Locations
        res_locations = self.client.get("/api/stations/locations")
        self.assertEqual(res_locations.status_code, 200)
        self.assertGreater(res_locations.get_json().get("count"), 0)

        # 4. Recommendation
        res_rec = self.client.post("/api/recommend", json={
            "location": "Any",
            "charger_type": "Any",
            "priority": "balanced"
        })
        self.assertEqual(res_rec.status_code, 200)
        rec_data = res_rec.get_json().get("data", {})
        self.assertGreater(len(rec_data.get("recommendations", [])), 0)

        # 5. Demand Inference
        res_demand = self.client.get("/api/demand?hour=18&day_of_week=2")
        self.assertEqual(res_demand.status_code, 200)
        demand_data = res_demand.get_json().get("data", {})
        self.assertIn("predicted_demand_kwh", demand_data)
        self.assertEqual(len(demand_data.get("hourly_curve", [])), 24)

        # 6. Demand Metadata
        res_meta = self.client.get("/api/demand/metadata")
        self.assertEqual(res_meta.status_code, 200)
        meta_data = res_meta.get_json().get("data", {})
        self.assertIn("metrics", meta_data)
        self.assertEqual(meta_data.get("total_samples"), 72856)

        print("\nAll 6 regression endpoints passed successfully!")

if __name__ == "__main__":
    unittest.main(verbosity=2)
