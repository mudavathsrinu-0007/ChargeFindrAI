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
from backend.routes.station_routes import calculate_haversine_distance, select_alternative_station

class TestModule6Verification(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "user"
            sess["csrf_token"] = "test_csrf_token"

    # =========================================================================
    # 1. UNIT TESTS FOR HAVERSINE DISTANCE
    # =========================================================================
    def test_01_haversine_calculation(self):
        """Test Haversine distance accuracy between known coordinates."""
        # Gachibowli (17.4401, 78.3489) to Madhapur (17.4483, 78.3915) is ~4.61 km
        dist = calculate_haversine_distance(17.4401, 78.3489, 17.4483, 78.3915)
        self.assertIsNotNone(dist)
        self.assertAlmostEqual(dist, 4.61, delta=0.2)

        # Missing or invalid coordinates return None safely
        self.assertIsNone(calculate_haversine_distance(None, 78.3489, 17.4483, 78.3915))
        self.assertIsNone(calculate_haversine_distance(17.4401, None, 17.4483, 78.3915))
        self.assertIsNone(calculate_haversine_distance("invalid", 78.3489, 17.4483, 78.3915))
        self.assertIsNone(calculate_haversine_distance(105.0, 78.3489, 17.4483, 78.3915))  # Out of range lat

    # =========================================================================
    # 2. CHARGER TYPE COMPATIBILITY & FALLBACK
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_02_same_charger_type_preference(self, mock_get_conn):
        """Verify candidate with same charger type is selected over AC charger with more ports/closer origin."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 1, "station_name": "Congested DC Stn", "location": "Area A",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("90"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 25,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                "station_id": 2, "station_name": "AC Super-Available Stn", "location": "Area B",
                "distance_km": Decimal("1.0"), "charger_type": "AC Type 2", "capacity_kw": Decimal("22"),
                "available_ports": 4, "total_ports": 4, "estimated_wait_minutes": 0,
                "demand_level": "Low", "latitude": Decimal("17.4410"), "longitude": Decimal("78.3410")
            },
            {
                "station_id": 3, "station_name": "DC Compatible Stn", "location": "Area C",
                "distance_km": Decimal("5.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 2, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.4500"), "longitude": Decimal("78.3500")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data["has_alert"])
        alert = data["alerts"][0]
        alt = alert["recommended_alternative"]

        self.assertIsNotNone(alt)
        # Must select DC Compatible Stn (ID 3), NOT AC Stn (ID 2)
        self.assertEqual(alt["station_id"], 3)
        self.assertEqual(alt["charger_type"], "Fast DC")
        self.assertFalse(alt["is_charger_fallback"])
        self.assertTrue(alt["is_same_charger_type"])
        self.assertIn("Recommend re-routing to DC Compatible Stn", alert["message"])
        self.assertNotIn("Fallback alternative:", alert["message"])

    @patch("backend.routes.station_routes.get_db_connection")
    def test_03_incompatible_charger_fallback(self, mock_get_conn):
        """When no same-type alternative exists, use different type only as clearly labelled fallback."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 1, "station_name": "Congested DC Hub", "location": "Area A",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("120"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 30,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                "station_id": 2, "station_name": "AC Fallback Stn", "location": "Area B",
                "distance_km": Decimal("2.0"), "charger_type": "AC Type 2", "capacity_kw": Decimal("22"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 4,
                "demand_level": "Low", "latitude": Decimal("17.4450"), "longitude": Decimal("78.3450")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        alert = data["alerts"][0]
        alt = alert["recommended_alternative"]

        self.assertIsNotNone(alt)
        self.assertEqual(alt["station_id"], 2)
        self.assertTrue(alt["is_charger_fallback"])
        self.assertFalse(alt["is_same_charger_type"])

        # Message must clearly label fallback and charging speed difference
        self.assertIn("Fallback alternative: AC Fallback Stn", alert["message"])
        self.assertIn("differs in charging speed", alert["message"])
        self.assertIn("No low-wait Fast DC stations available", alert["message"])

    # =========================================================================
    # 3. HAVERSINE DISTANCE ORDERING (NOT CITY ORIGIN)
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_04_haversine_distance_ordering(self, mock_get_conn):
        """Rank alternatives using actual Haversine distance between coordinates, not city-origin distance_km."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 10, "station_name": "Congested Origin Stn", "location": "Origin",
                "distance_km": Decimal("15.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 25,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                # Physically close (~0.77 km away) but city-origin distance_km is high (20.0 km)
                "station_id": 11, "station_name": "Nearby Stn (High Origin)", "location": "Nearby",
                "distance_km": Decimal("20.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.4450"), "longitude": Decimal("78.3450")
            },
            {
                # Physically far (~8.0 km away) but city-origin distance_km is low (1.0 km)
                "station_id": 12, "station_name": "Far Stn (Low Origin)", "location": "Far",
                "distance_km": Decimal("1.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.4900"), "longitude": Decimal("78.3900")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()
        alt = data["alerts"][0]["recommended_alternative"]

        # Station 11 is closer by coordinates (~0.77 km vs ~8 km)
        self.assertEqual(alt["station_id"], 11)
        self.assertLess(alt["distance_between_km"], 1.5)

    # =========================================================================
    # 4. ONE-PORT ALTERNATIVES & BUFFER PREFERENCE
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_05_one_port_alternative_fallback(self, mock_get_conn):
        """Allow station with at least 1 port as fallback when no station with >1 ports qualifies."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 20, "station_name": "Congested Stn", "location": "Area X",
                "distance_km": Decimal("3.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 35,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                # Only 1 port available (would have been rejected under old >1 rule)
                "station_id": 21, "station_name": "Single Port Stn", "location": "Area Y",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 1, "total_ports": 4, "estimated_wait_minutes": 4,
                "demand_level": "Medium", "latitude": Decimal("17.4450"), "longitude": Decimal("78.3450")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()
        alt = data["alerts"][0]["recommended_alternative"]

        self.assertIsNotNone(alt)
        self.assertEqual(alt["station_id"], 21)
        self.assertEqual(alt["available_ports"], 1)

    @patch("backend.routes.station_routes.get_db_connection")
    def test_06_multi_port_preferred_over_single_port(self, mock_get_conn):
        """Stations with >1 ports are preferred over 1-port stations within the same tier."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 30, "station_name": "Congested Stn", "location": "Area X",
                "distance_km": Decimal("3.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 35,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                "station_id": 31, "station_name": "Single Port Stn (Closer)", "location": "Area Y",
                "distance_km": Decimal("3.5"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 1, "total_ports": 4, "estimated_wait_minutes": 3,
                "demand_level": "Medium", "latitude": Decimal("17.4420"), "longitude": Decimal("78.3420")
            },
            {
                "station_id": 32, "station_name": "Multi Port Stn (Further)", "location": "Area Z",
                "distance_km": Decimal("5.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.4500"), "longitude": Decimal("78.3500")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()
        alt = data["alerts"][0]["recommended_alternative"]

        # Station 32 has 3 ports (>1), preferred over Station 31 (1 port)
        self.assertEqual(alt["station_id"], 32)

    # =========================================================================
    # 5. MULTIPLE CONGESTED STATIONS & NULL-SAFETY
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_07_multiple_congested_stations(self, mock_get_conn):
        """Multiple congested stations return all alerts cleanly with correct counts."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 101, "station_name": "Congested 1", "location": "Loc 1",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 25,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                "station_id": 102, "station_name": "Congested 2", "location": "Loc 2",
                "distance_km": Decimal("3.0"), "charger_type": "AC Type 2", "capacity_kw": Decimal("22"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 30,
                "demand_level": "High", "latitude": Decimal("17.4500"), "longitude": Decimal("78.3500")
            },
            {
                "station_id": 103, "station_name": "Open DC Station", "location": "Loc 3",
                "distance_km": Decimal("4.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 3, "total_ports": 4, "estimated_wait_minutes": 3,
                "demand_level": "Low", "latitude": Decimal("17.4420"), "longitude": Decimal("78.3420")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()

        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["alerts"]), 2)
        self.assertEqual(data["alerts"][0]["congested_station"]["station_id"], 101)
        self.assertEqual(data["alerts"][1]["congested_station"]["station_id"], 102)

    @patch("backend.routes.station_routes.get_db_connection")
    def test_08_null_safe_messages(self, mock_get_conn):
        """Handle missing port counts and wait times safely; never output literal 'None' or 'null' in text."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 201, "station_name": "Null Ports Stn", "location": "Loc A",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": None, "total_ports": 4, "estimated_wait_minutes": 30,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            },
            {
                "station_id": 202, "station_name": "Open Stn", "location": "Loc B",
                "distance_km": Decimal("3.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 2, "total_ports": 4, "estimated_wait_minutes": 5,
                "demand_level": "Low", "latitude": Decimal("17.4450"), "longitude": Decimal("78.3450")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()
        alert = data["alerts"][0]

        self.assertNotIn("None", alert["message"])
        self.assertNotIn("null", alert["message"])
        self.assertIn("long queue with 30 mins wait", alert["message"])

    # =========================================================================
    # 6. NEVER RECOMMEND SELF & NO SUITABLE ALTERNATIVE
    # =========================================================================
    @patch("backend.routes.station_routes.get_db_connection")
    def test_09_never_recommend_self(self, mock_get_conn):
        """A station must never recommend itself as an alternative."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "station_id": 301, "station_name": "Lone Congested Stn", "location": "Solo",
                "distance_km": Decimal("2.0"), "charger_type": "Fast DC", "capacity_kw": Decimal("60"),
                "available_ports": 0, "total_ports": 4, "estimated_wait_minutes": 25,
                "demand_level": "High", "latitude": Decimal("17.4400"), "longitude": Decimal("78.3400")
            }
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        res = self.client.get("/api/stations/alerts")
        data = res.get_json()
        alert = data["alerts"][0]

        self.assertIsNone(alert["recommended_alternative"])
        self.assertIn("No low-wait alternative currently available", alert["message"])

    # =========================================================================
    # 7. LIVE MYSQL DATABASE VERIFICATION
    # =========================================================================
    def test_10_live_db_verification(self):
        """Test against live MySQL database; VoltWay Charging (ID 4) routes to GreenCharge Hub (ID 1)."""
        res = self.client.get("/api/stations/alerts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data["success"])
        self.assertTrue(data["has_alert"])
        self.assertGreaterEqual(data["count"], 1)

        alert = data["alerts"][0]
        congested = alert["congested_station"]
        alt = alert["recommended_alternative"]

        self.assertEqual(congested["station_name"], "VoltWay Charging")
        self.assertEqual(congested["available_ports"], 0)
        self.assertEqual(alt["station_name"], "GreenCharge Hub")
        self.assertEqual(alt["charger_type"], "Fast DC")
        self.assertTrue(alt["is_same_charger_type"])
        self.assertFalse(alt["is_charger_fallback"])
        self.assertIsNotNone(alt["distance_between_km"])
        self.assertGreater(alt["distance_between_km"], 0.0)

if __name__ == "__main__":
    unittest.main(verbosity=2)

