import os
import sys
import unittest
import json

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend.database.db_config import get_db_connection

class TestStage6Auth(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def get_fresh_csrf(self, client=None):
        c = client or self.client
        res = c.get("/api/auth/csrf")
        self.assertEqual(res.status_code, 200)
        return res.get_json()["csrf_token"]

    # =========================================================================
    # 1. DATABASE SCHEMA & CHARGING STATIONS PRESERVATION
    # =========================================================================
    def test_01_schema_and_station_preservation(self):
        """Verify users table exists and charging_stations data has not been modified."""
        conn = get_db_connection()
        self.assertIsNotNone(conn, "Database connection must be operational.")

        cursor = conn.cursor(dictionary=True)
        # Check users table columns
        cursor.execute("DESCRIBE users;")
        cols = {row["Field"]: row for row in cursor.fetchall()}
        self.assertIn("user_id", cols)
        self.assertIn("full_name", cols)
        self.assertIn("email", cols)
        self.assertIn("password_hash", cols)
        self.assertIn("role", cols)
        self.assertIn("created_at", cols)

        # Check charging_stations record count remains exactly 5
        cursor.execute("SELECT COUNT(*) AS total FROM charging_stations;")
        station_count = cursor.fetchone()["total"]
        self.assertEqual(station_count, 5, "Charging stations table must contain exactly 5 records.")

        cursor.close()
        conn.close()

    # =========================================================================
    # 2. CSRF ENFORCEMENT ON STATE-CHANGING ENDPOINTS
    # =========================================================================
    def test_02_csrf_protection_enforcement(self):
        """Verify state-changing auth endpoints reject missing and forged CSRF tokens."""
        # 1. Missing CSRF header
        res_no_csrf = self.client.post("/api/auth/register", json={
            "full_name": "CSRF Victim",
            "email": "victim@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res_no_csrf.status_code, 403)
        self.assertIn("CSRF", res_no_csrf.get_json()["error"])

        # 2. Bogus / Forged CSRF header
        res_bad_csrf = self.client.post("/api/auth/register", json={
            "full_name": "CSRF Victim",
            "email": "victim@example.com",
            "password": "Password123!"
        }, headers={"X-CSRF-Token": "forged_malicious_token_abc123"})
        self.assertEqual(res_bad_csrf.status_code, 403)
        self.assertIn("CSRF", res_bad_csrf.get_json()["error"])

    # =========================================================================
    # 3. REGISTRATION VALIDATION
    # =========================================================================
    def test_03_registration_validation(self):
        """Verify input validation rejects short passwords, invalid emails, and empty names."""
        csrf = self.get_fresh_csrf()

        # Missing / Short Name
        res1 = self.client.post("/api/auth/register", json={
            "full_name": " ",
            "email": "valid@example.com",
            "password": "Password123!"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res1.status_code, 400)
        self.assertIn("name", res1.get_json()["error"].lower())

        # Invalid Email Format
        res2 = self.client.post("/api/auth/register", json={
            "full_name": "Valid Name",
            "email": "invalid-email-format",
            "password": "Password123!"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res2.status_code, 400)
        self.assertIn("email", res2.get_json()["error"].lower())

        # Password < 8 characters
        res3 = self.client.post("/api/auth/register", json={
            "full_name": "Valid Name",
            "email": "shortpass@example.com",
            "password": "short"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res3.status_code, 400)
        self.assertIn("8 characters", res3.get_json()["error"])

        # Whitespace-only password
        res4 = self.client.post("/api/auth/register", json={
            "full_name": "Valid Name",
            "email": "spacepass@example.com",
            "password": "        "
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res4.status_code, 400)

    # =========================================================================
    # 4. FORGED ADMIN REGISTRATION DEFENSE & ROLE ASSIGNMENT
    # =========================================================================
    def test_04_forged_admin_prevention(self):
        """Verify that public registration strictly assigns role 'user' and ignores forged role inputs."""
        csrf = self.get_fresh_csrf()
        test_email = "test.regular.driver@chargefindr.local"

        res = self.client.post("/api/auth/register", json={
            "full_name": "Test Driver",
            "email": test_email,
            "password": "SecurePassword123!",
            "role": "admin",      # Attempted privilege escalation
            "is_admin": True      # Alternate parameter tampering
        }, headers={"X-CSRF-Token": csrf})

        # Could be 201 or 409 if already exists from prior run
        self.assertIn(res.status_code, [201, 409])
        if res.status_code == 201:
            data = res.get_json()
            self.assertEqual(data["user"]["role"], "user", "Public registration must never assign admin role.")
            self.assertNotIn("password_hash", data["user"], "Password hash must never be returned in API response.")

            # Direct database verification
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT role FROM users WHERE email = %s;", (test_email,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            self.assertEqual(row["role"], "user", "Role in database must be strictly 'user'.")

    # =========================================================================
    # 5. DUPLICATE EMAIL REJECTION
    # =========================================================================
    def test_05_duplicate_email_conflict(self):
        """Verify attempting to register with an existing email returns HTTP 409 Conflict."""
        csrf = self.get_fresh_csrf()
        dup_email = "test.duplicate@chargefindr.local"

        # First registration
        self.client.post("/api/auth/register", json={
            "full_name": "Original User",
            "email": dup_email,
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})

        # Second registration with identical email
        csrf2 = self.get_fresh_csrf()
        res_dup = self.client.post("/api/auth/register", json={
            "full_name": "Duplicate User",
            "email": dup_email,
            "password": "DifferentPassword123!"
        }, headers={"X-CSRF-Token": csrf2})

        self.assertEqual(res_dup.status_code, 409)
        self.assertFalse(res_dup.get_json()["success"])
        self.assertIn("already exists", res_dup.get_json()["error"])

    # =========================================================================
    # 6. AUTHENTICATION FAILURES
    # =========================================================================
    def test_06_authentication_failures(self):
        """Verify failed login attempts return uniform HTTP 401 without account enumeration."""
        csrf = self.get_fresh_csrf()

        # Non-existent user
        res1 = self.client.post("/api/auth/login", json={
            "email": "nonexistent.user.999@chargefindr.local",
            "password": "SomePassword123!"
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.get_json()["error"], "Invalid email or password.")

        # Existing user, wrong password
        csrf2 = self.get_fresh_csrf()
        res2 = self.client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "WrongPassword123!"
        }, headers={"X-CSRF-Token": csrf2})
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.get_json()["error"], "Invalid email or password.")

    # =========================================================================
    # 7. SUCCESSFUL LOGIN, SESSION FIXATION PROTECTION, PROFILE INSPECTION
    # =========================================================================
    def test_07_login_and_profile_session(self):
        """Verify successful login rotates CSRF token, sets session cookie, and populates /api/auth/me."""
        client = app.test_client()
        csrf = self.get_fresh_csrf(client)

        login_res = client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})

        self.assertEqual(login_res.status_code, 200)
        data = login_res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("csrf_token", data)
        self.assertNotEqual(data["csrf_token"], csrf, "Login must rotate and issue a fresh CSRF token.")

        # Check /api/auth/me
        me_res = client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertTrue(me_data["authenticated"])
        self.assertEqual(me_data["user"]["email"], "test.duplicate@chargefindr.local")
        self.assertEqual(me_data["user"]["role"], "user")

    # =========================================================================
    # 8. LOGOUT AND SESSION DESTRUCTION
    # =========================================================================
    def test_08_logout_and_session_clearing(self):
        """Verify logout purges session identity and returns guest status on /api/auth/me."""
        client = app.test_client()
        csrf = self.get_fresh_csrf(client)

        # Login
        login_res = client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf})
        auth_csrf = login_res.get_json()["csrf_token"]

        # Logout with fresh auth CSRF
        logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": auth_csrf})
        self.assertEqual(logout_res.status_code, 200)

        # Confirm session cleared
        me_res = client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        self.assertFalse(me_res.get_json()["authenticated"])
        self.assertIsNone(me_res.get_json()["user"])

    # =========================================================================
    # 9. ROLE-BASED ACCESS CONTROL (RBAC) ON ADMIN ROUTE
    # =========================================================================
    def test_09_rbac_admin_overview_access(self):
        """Verify guest (401), regular user (403), and admin (200) access control on /api/admin/overview."""
        # 1. Unauthenticated guest
        guest_client = app.test_client()
        res_guest = guest_client.get("/api/admin/overview")
        self.assertEqual(res_guest.status_code, 401)
        self.assertFalse(res_guest.get_json()["success"])

        # 2. Regular user (role='user')
        user_client = app.test_client()
        csrf_user = self.get_fresh_csrf(user_client)
        user_client.post("/api/auth/login", json={
            "email": "test.duplicate@chargefindr.local",
            "password": "SecurePassword123!"
        }, headers={"X-CSRF-Token": csrf_user})
        res_user = user_client.get("/api/admin/overview")
        self.assertEqual(res_user.status_code, 403)
        self.assertFalse(res_user.get_json()["success"])
        self.assertIn("Administrator privileges are required", res_user.get_json()["error"])

        # 3. Administrator user (role='admin')
        admin_client = app.test_client()
        csrf_admin = self.get_fresh_csrf(admin_client)
        admin_client.post("/api/auth/login", json={
            "email": "admin@chargefindr.local",
            "password": "Admin@ChargeFindr2026"
        }, headers={"X-CSRF-Token": csrf_admin})
        res_admin = admin_client.get("/api/admin/overview")
        self.assertEqual(res_admin.status_code, 200)
        self.assertTrue(res_admin.get_json()["success"])
        overview = res_admin.get_json()["data"]
        self.assertGreaterEqual(overview["total_users"], 1)
        self.assertEqual(overview["total_stations"], 5)
        self.assertEqual(overview["database_status"], "connected")

    # =========================================================================
    # 10. REGRESSION VERIFICATION OF ALL EXISTING STAGE 1–5 ENDPOINTS
    # =========================================================================
    def test_10_regression_existing_endpoints(self):
        """Confirm that all Stage 1–5 endpoints remain completely operational without regression."""
        # 1. Health
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.get_json()["database"], "connected")

        # 2. Stations List
        res_stations = self.client.get("/api/stations")
        self.assertEqual(res_stations.status_code, 200)
        self.assertEqual(res_stations.get_json()["count"], 5)

        # 3. Dynamic Locations
        res_locations = self.client.get("/api/stations/locations")
        self.assertEqual(res_locations.status_code, 200)
        self.assertGreater(res_locations.get_json()["count"], 0)

        # 4. Smart Alerts
        res_alerts = self.client.get("/api/stations/alerts")
        self.assertEqual(res_alerts.status_code, 200)
        self.assertTrue(res_alerts.get_json()["has_alert"])

        # 5. Public Recommendation (Unauthenticated POST works without CSRF restriction)
        res_rec = self.client.post("/api/recommend", json={
            "location": "Any",
            "charger_type": "Any",
            "priority": "balanced"
        })
        self.assertEqual(res_rec.status_code, 200)
        self.assertGreater(len(res_rec.get_json()["data"]["recommendations"]), 0)

        # 6. ML Demand Inference
        res_demand = self.client.get("/api/demand?hour=18&day_of_week=2")
        self.assertEqual(res_demand.status_code, 200)
        self.assertIn("predicted_demand_kwh", res_demand.get_json()["data"])
        self.assertEqual(len(res_demand.get_json()["data"]["hourly_curve"]), 24)

        # 7. ML Model Metadata
        res_meta = self.client.get("/api/demand/metadata")
        self.assertEqual(res_meta.status_code, 200)
        self.assertEqual(res_meta.get_json()["data"]["total_samples"], 72856)

        print("\n[VERIFIED] All Stage 1–5 public endpoints passed regression checks!")

if __name__ == "__main__":
    unittest.main(verbosity=2)

