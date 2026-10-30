import os
import sys
import unittest
import json
import secrets

# Ensure ChargeFindrAI is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend.database.db_config import get_db_connection


class TestAuthRbacStations(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def get_csrf(self, client=None):
        c = client or self.client
        res = c.get("/api/auth/csrf")
        self.assertEqual(res.status_code, 200)
        return res.get_json()["csrf_token"]

    # =========================================================================
    # 1. REGISTRATION & CONFIRM PASSWORD VALIDATION
    # =========================================================================
    def test_01_registration_validation_and_confirm_password(self):
        """Verify registration enforces matching Confirm Password and user-only role."""
        csrf = self.get_csrf()

        # 1. Mismatched passwords
        res_mismatch = self.client.post("/api/auth/register", json={
            "full_name": "Test Driver",
            "email": "driver.mismatch@chargefindr.local",
            "password": "ValidPassword123!",
            "confirm_password": "DifferentPassword456!"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res_mismatch.status_code, 400)
        self.assertIn("Passwords do not match", res_mismatch.get_json()["error"])

        # 2. Matching passwords with privilege escalation attempt
        csrf2 = self.get_csrf()
        test_email = f"driver.{secrets.token_hex(4)}@chargefindr.local"
        res_success = self.client.post("/api/auth/register", json={
            "full_name": "Valid Driver",
            "email": test_email,
            "password": "ValidPassword123!",
            "confirm_password": "ValidPassword123!",
            "role": "admin"  # Tampering attempt
        }, headers={"X-CSRF-Token": csrf2})
        self.assertEqual(res_success.status_code, 201)
        data = res_success.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "user", "Public registration must strictly assign role 'user'.")

    # =========================================================================
    # 2. LOGIN & SESSION PERSISTENCE
    # =========================================================================
    def test_02_login_and_session_persistence(self):
        """Verify login creates persistent session across multiple requests."""
        client = app.test_client()
        csrf = self.get_csrf(client)

        login_res = client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(login_res.status_code, 200)

        # Check session persists across multiple GET /api/auth/me requests
        for _ in range(3):
            me_res = client.get("/api/auth/me")
            self.assertEqual(me_res.status_code, 200)
            self.assertTrue(me_res.get_json()["authenticated"])
            self.assertEqual(me_res.get_json()["user"]["email"], "test.duplicate@chargefindr.local")

    # =========================================================================
    # 3. UNAUTHORIZED DASHBOARD / API ACCESS PROTECTION
    # =========================================================================
    def test_03_unauthorized_dashboard_api_access_blocked(self):
        """Verify unauthenticated requests to dashboard endpoints receive HTTP 401."""
        unauth_client = app.test_client()

        endpoints = [
            ("GET", "/api/stations"),
            ("GET", "/api/stations/locations"),
            ("GET", "/api/stations/alerts"),
            ("POST", "/api/recommend"),
            ("GET", "/api/demand"),
            ("GET", "/api/demand/metadata"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                res = unauth_client.get(endpoint)
            else:
                res = unauth_client.post(endpoint, json={"location": "Any"})
            self.assertEqual(res.status_code, 401, f"{endpoint} must require authentication.")
            self.assertIn("Authentication required", res.get_json()["error"])

    # =========================================================================
    # 4. USER ROLE PERMISSIONS (DASHBOARD ALLOWED, ADMIN BLOCKED)
    # =========================================================================
    def test_04_user_role_permissions_enforced(self):
        """Verify regular USER can access dashboard APIs but receives HTTP 403 on admin routes."""
        user_client = app.test_client()
        csrf = self.get_csrf(user_client)

        # Authenticate as regular user
        user_client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})

        # Permitted dashboard APIs (HTTP 200)
        res_stations = user_client.get("/api/stations")
        self.assertEqual(res_stations.status_code, 200)

        res_rec = user_client.post("/api/recommend", json={"location": "Any", "priority": "balanced"})
        self.assertEqual(res_rec.status_code, 200)

        res_demand = user_client.get("/api/demand?hour=14&day_of_week=3")
        self.assertEqual(res_demand.status_code, 200)

        # Forbidden admin APIs (HTTP 403)
        res_overview = user_client.get("/api/admin/overview")
        self.assertEqual(res_overview.status_code, 403)

        res_users = user_client.get("/api/admin/users")
        self.assertEqual(res_users.status_code, 403)

        user_csrf = self.get_csrf(user_client)
        res_add_stn = user_client.post("/api/admin/stations", json={
            "station_name": "Unauthorized Station",
            "location": "Hyderabad"
        }, headers={"X-CSRF-Token": user_csrf})
        self.assertEqual(res_add_stn.status_code, 403)

    # =========================================================================
    # 5. ADMIN PERMISSIONS & STATION CRUD OPERATIONS
    # =========================================================================
    def test_05_admin_station_crud_operations(self):
        """Verify ADMIN can create, update, and delete charging stations with CSRF protection."""
        admin_client = app.test_client()
        csrf = self.get_csrf(admin_client)

        # 1. Log in as admin
        admin_login = admin_client.post("/api/auth/login", json={
            "email": "admin@chargefindr.local",
            "password": "Admin@ChargeFindr2026"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(admin_login.status_code, 200)
        admin_csrf = admin_login.get_json()["csrf_token"]

        # 2. Telemetry and User list
        res_overview = admin_client.get("/api/admin/overview")
        self.assertEqual(res_overview.status_code, 200)
        res_users = admin_client.get("/api/admin/users")
        self.assertEqual(res_users.status_code, 200)
        self.assertGreaterEqual(res_users.get_json()["count"], 1)

        # 3. Create new EV station (POST)
        new_station_payload = {
            "station_name": "Automated Unit Test Station",
            "location": "Banjara Hills, Hyderabad",
            "charger_type": "Fast DC",
            "capacity_kw": 120.0,
            "distance_km": 3.5,
            "total_ports": 6,
            "available_ports": 4,
            "estimated_wait_minutes": 2,
            "demand_level": "Low",
            "latitude": 17.4156,
            "longitude": 78.4350
        }
        res_create = admin_client.post("/api/admin/stations", json=new_station_payload, headers={"X-CSRF-Token": admin_csrf})
        self.assertEqual(res_create.status_code, 201)
        created_stn = res_create.get_json()["station"]
        stn_id = created_stn["station_id"]
        self.assertIsNotNone(stn_id)

        # 4. Update the station (PUT)
        update_payload = {
            "available_ports": 1,
            "estimated_wait_minutes": 18,
            "demand_level": "High"
        }
        res_update = admin_client.put(f"/api/admin/stations/{stn_id}", json=update_payload, headers={"X-CSRF-Token": admin_csrf})
        self.assertEqual(res_update.status_code, 200)
        updated_stn = res_update.get_json()["station"]
        self.assertEqual(updated_stn["available_ports"], 1)
        self.assertEqual(updated_stn["estimated_wait_minutes"], 18)

        # 5. Delete the station (DELETE)
        res_delete = admin_client.delete(f"/api/admin/stations/{stn_id}", headers={"X-CSRF-Token": admin_csrf})
        self.assertEqual(res_delete.status_code, 200)
        self.assertTrue(res_delete.get_json()["success"])

        # 6. Verify station is deleted
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT station_id FROM charging_stations WHERE station_id = %s;", (stn_id,))
        deleted_row = cur.fetchone()
        cur.close()
        conn.close()
        self.assertIsNone(deleted_row)

    # =========================================================================
    # 6. LOGOUT AND SESSION TERMINATION
    # =========================================================================
    def test_06_logout_terminates_session(self):
        """Verify logout invalidates session identity and denies protected access."""
        client = app.test_client()
        csrf = self.get_csrf(client)

        login_res = client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})
        auth_csrf = login_res.get_json()["csrf_token"]

        # Logout
        logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": auth_csrf})
        self.assertEqual(logout_res.status_code, 200)

        # Check /api/auth/me reflects guest status
        me_res = client.get("/api/auth/me")
        self.assertFalse(me_res.get_json()["authenticated"])

        # Check /api/stations is blocked with 401
        stations_res = client.get("/api/stations")
        self.assertEqual(stations_res.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)

