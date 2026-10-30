import unittest
import json
from datetime import datetime, date, timedelta, time
from backend.app import app
from backend.database.db_config import get_db_connection, ensure_booking_and_queue_tables
from backend.services.auth_service import register_user

class TestBookingAndQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()
        ensure_booking_and_queue_tables()

        # Clean test records from previous test runs (preserving existing seed users <= 8)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM station_bookings WHERE user_id > 8")
        cur.execute("DELETE FROM walkin_queue WHERE user_id > 8")
        cur.execute("DELETE FROM users WHERE email LIKE '%@testbq.com'")
        conn.commit()
        cur.close()
        conn.close()

        cls.user1_email = "booker1@testbq.com"
        cls.user2_email = "booker2@testbq.com"
        cls.admin_email = "admin_bq@testbq.com"

        register_user("Booker One", cls.user1_email, "Password123!", role="user", is_controlled_provision=True, confirm_password="Password123!")
        register_user("Booker Two", cls.user2_email, "Password123!", role="user", is_controlled_provision=True, confirm_password="Password123!")
        register_user("Admin BQ", cls.admin_email, "Password123!", role="admin", is_controlled_provision=True, confirm_password="Password123!")

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id, email, role FROM users WHERE email IN (%s, %s, %s)",
                    (cls.user1_email, cls.user2_email, cls.admin_email))
        users = cur.fetchall()
        cur.close()
        conn.close()

        cls.user_map = {u["email"]: u for u in users}

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM station_bookings WHERE user_id > 8")
        cur.execute("DELETE FROM walkin_queue WHERE user_id > 8")
        cur.execute("DELETE FROM users WHERE email LIKE '%@testbq.com'")
        conn.commit()
        cur.close()
        conn.close()

    def setUp(self):
        # Guarantee a fresh slate for bookings and queues between tests
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM station_bookings WHERE user_id > 8")
        cur.execute("DELETE FROM walkin_queue WHERE user_id > 8")
        conn.commit()
        cur.close()
        conn.close()

    def _login_session(self, client, email, role="user"):
        user_info = self.user_map[email]
        with client.session_transaction() as sess:
            sess["user_id"] = user_info["user_id"]
            sess["email"] = user_info["email"]
            sess["role"] = role
            sess["csrf_token"] = "test-csrf-token-12345"

    def test_01_available_slots_retrieval(self):
        """Verify GET /api/bookings/available-slots returns valid 30-min intervals and respects operating hours."""
        c = app.test_client()
        self._login_session(c, self.user1_email)

        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        res = c.get(f"/api/bookings/available-slots?station_id=1&date={tomorrow}&duration=60")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreater(len(data["slots"]), 0)
        self.assertEqual(data["slots"][0]["start_time"], "08:00")
        self.assertEqual(data["slots"][0]["end_time"], "09:00")
        self.assertTrue(data["slots"][0]["available"])

    def test_02_booking_creation_and_reference(self):
        """Verify POST /api/bookings creates a booking with reference BK-YYYYMMDD-XXXX."""
        c = app.test_client()
        self._login_session(c, self.user1_email)

        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "station_id": 1,
            "driver_name": "Booker One",
            "vehicle_model": "Tata Nexon EV",
            "vehicle_reg_number": "TS09EA1234",
            "booking_date": tomorrow,
            "start_time": "10:00",
            "duration_minutes": 60
        }
        res = c.post("/api/bookings",
                     data=json.dumps(payload),
                     content_type="application/json",
                     headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("BK-", data["booking"]["booking_reference"])
        self.assertEqual(data["booking"]["status"], "CONFIRMED")
        self.assertEqual(data["booking"]["port_number"], 1)

    def test_03_double_booking_and_concurrency_conflict(self):
        """Verify booking the same port window when fully booked returns HTTP 409 Conflict."""
        tomorrow = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")

        # Station 1 has 2 reserved ports. Book both ports for 14:00 - 15:00
        c1 = app.test_client()
        self._login_session(c1, self.user1_email)
        payload1 = {
            "station_id": 1,
            "driver_name": "Driver Port 1",
            "vehicle_model": "MG ZS EV",
            "vehicle_reg_number": "TS07FA5555",
            "booking_date": tomorrow,
            "start_time": "14:00",
            "duration_minutes": 60
        }
        res1 = c1.post("/api/bookings", data=json.dumps(payload1), content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res1.status_code, 201)

        c2 = app.test_client()
        self._login_session(c2, self.user2_email)
        payload2 = {
            "station_id": 1,
            "driver_name": "Driver Port 2",
            "vehicle_model": "Hyundai Ioniq 5",
            "vehicle_reg_number": "TS08GA7777",
            "booking_date": tomorrow,
            "start_time": "14:00",
            "duration_minutes": 60
        }
        res2 = c2.post("/api/bookings", data=json.dumps(payload2), content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res2.status_code, 201)

        # 3rd attempt by a 3rd driver for the exact same station/time window must return 409 Conflict
        c3 = app.test_client()
        self._login_session(c3, self.admin_email)
        payload3 = {
            "station_id": 1,
            "driver_name": "Driver Port 3 Overflow",
            "vehicle_model": "BYD Atto 3",
            "vehicle_reg_number": "TS09HA9999",
            "booking_date": tomorrow,
            "start_time": "14:30",
            "duration_minutes": 60
        }
        res3 = c3.post("/api/bookings", data=json.dumps(payload3), content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res3.status_code, 409)
        self.assertIn("Conflict", res3.get_json()["error"])

    def test_04_user_isolation(self):
        """Verify users can only view their own bookings and cannot cancel other users' bookings."""
        c1 = app.test_client()
        self._login_session(c1, self.user1_email)

        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "station_id": 1,
            "driver_name": "Booker One",
            "vehicle_model": "Tata Nexon EV",
            "vehicle_reg_number": "TS09EA1234",
            "booking_date": tomorrow,
            "start_time": "10:00",
            "duration_minutes": 60
        }
        res_create = c1.post("/api/bookings", data=json.dumps(payload), content_type="application/json",
                             headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_create.status_code, 201)
        target_b1_id = res_create.get_json()["booking"]["booking_id"]

        # Booker 1 gets their bookings
        res1 = c1.get("/api/bookings/my")
        self.assertEqual(res1.status_code, 200)
        b1_list = res1.get_json()["bookings"]
        self.assertEqual(len(b1_list), 1)

        # Booker 2 tries to cancel Booker 1's booking
        c2 = app.test_client()
        self._login_session(c2, self.user2_email)
        res_hack = c2.post(f"/api/bookings/{target_b1_id}/cancel",
                           data=json.dumps({}),
                           content_type="application/json",
                           headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_hack.status_code, 403)
        self.assertIn("Access denied", res_hack.get_json()["error"])

    def test_05_cancellation_policy(self):
        """Verify cancellation is allowed > 30 mins before start, and rejected <= 30 mins."""
        c = app.test_client()
        self._login_session(c, self.user1_email)
        target_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
        payload = {
            "station_id": 2,
            "driver_name": "Booker One",
            "vehicle_model": "Tata Tiago EV",
            "vehicle_reg_number": "TS09KA1111",
            "booking_date": target_date,
            "start_time": "11:00",
            "duration_minutes": 60
        }
        res = c.post("/api/bookings", data=json.dumps(payload), content_type="application/json",
                     headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res.status_code, 201)
        b_id = res.get_json()["booking"]["booking_id"]

        # Cancel it -> should succeed (> 30 mins)
        res_cancel = c.post(f"/api/bookings/{b_id}/cancel",
                            data=json.dumps({"reason": "Plan changed"}),
                            content_type="application/json",
                            headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.get_json()["status"], "CANCELLED")

        # Now test rejection when start time is <= 30 minutes away
        near_start = (datetime.now() + timedelta(minutes=10)).time()
        near_end = (datetime.now() + timedelta(minutes=70)).time()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO station_bookings (
                booking_reference, user_id, station_id, charger_id, port_number,
                charger_type, driver_name, vehicle_model, vehicle_reg_number,
                booking_date, start_time, end_time, duration_minutes, status
            ) VALUES (%s, %s, 1, 1, 1, 'Fast DC', 'Urgent Driver', 'EV Car', 'TS09URGENT', %s, %s, %s, 60, 'CONFIRMED');
        """, (f"BK-TEST-NEAR-{int(datetime.now().timestamp())}", self.user_map[self.user1_email]["user_id"],
              date.today().strftime("%Y-%m-%d"), near_start.strftime("%H:%M:%S"), near_end.strftime("%H:%M:%S")))
        conn.commit()
        near_b_id = cur.lastrowid
        cur.close()
        conn.close()

        # Attempt to cancel near booking
        res_near_cancel = c.post(f"/api/bookings/{near_b_id}/cancel",
                                 data=json.dumps({}),
                                 content_type="application/json",
                                 headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_near_cancel.status_code, 400)
        self.assertIn("Cancellation policy violation", res_near_cancel.get_json()["error"])

    def test_06_missed_slot_handling_and_alternatives(self):
        """Verify missed bookings past grace period are marked MISSED and provide alternative suggestions."""
        past_start = (datetime.now() - timedelta(minutes=25)).time()
        past_end = (datetime.now() + timedelta(minutes=35)).time()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO station_bookings (
                booking_reference, user_id, station_id, charger_id, port_number,
                charger_type, driver_name, vehicle_model, vehicle_reg_number,
                booking_date, start_time, end_time, duration_minutes, status, grace_period_minutes
            ) VALUES (%s, %s, 1, 2, 2, 'Fast DC', 'Missed Driver', 'EV Car', 'TS09MISSED', %s, %s, %s, 60, 'CONFIRMED', 15);
        """, (f"BK-TEST-MISSED-{int(datetime.now().timestamp())}", self.user_map[self.user1_email]["user_id"],
              date.today().strftime("%Y-%m-%d"), past_start.strftime("%H:%M:%S"), past_end.strftime("%H:%M:%S")))
        conn.commit()
        missed_b_id = cur.lastrowid
        cur.close()
        conn.close()

        c = app.test_client()
        self._login_session(c, self.user1_email)

        # Trigger get_alternative_slots which runs evaluate_missed_bookings
        res = c.get(f"/api/bookings/{missed_b_id}/alternatives")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["original_booking"]["status"], "MISSED")
        self.assertGreater(len(data["alternatives"]), 0)

    def test_07_queue_status_metrics(self):
        """Verify GET /api/queue/status/<station_id> returns dedicated walk-in metrics."""
        c = app.test_client()
        self._login_session(c, self.user1_email)

        res = c.get("/api/queue/status/1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("walkin_ports", data)
        self.assertIn("waiting_count", data)
        self.assertIn("estimated_wait_minutes", data)

    def test_08_queue_join_and_duplicate_prevention(self):
        """Verify joining queue issues ticket, and duplicate active join returns HTTP 409."""
        c1 = app.test_client()
        self._login_session(c1, self.user1_email)

        payload = {
            "station_id": 1,
            "driver_name": "Booker One",
            "vehicle_model": "Mahindra XUV400",
            "vehicle_reg_number": "TS09WQ1111",
            "charger_type": "Fast DC"
        }
        res1 = c1.post("/api/queue/join",
                       data=json.dumps(payload),
                       content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()
        self.assertTrue(data1["success"])
        self.assertIn("WQ-S1-", data1["ticket"]["queue_ticket"])

        # Attempt to join again while holding active ticket -> 409 Conflict
        res_dup = c1.post("/api/queue/join",
                          data=json.dumps(payload),
                          content_type="application/json",
                          headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_dup.status_code, 409)
        self.assertIn("Duplicate queue entry rejected", res_dup.get_json()["error"])

    def test_09_queue_fifo_position_and_dynamic_update(self):
        """Verify sequential tickets receive FIFO positions and positions update when earlier driver leaves."""
        c1 = app.test_client()
        self._login_session(c1, self.user1_email)
        payload1 = {
            "station_id": 1,
            "driver_name": "Booker One",
            "vehicle_model": "Mahindra XUV400",
            "vehicle_reg_number": "TS09WQ1111",
            "charger_type": "Fast DC"
        }
        res1 = c1.post("/api/queue/join",
                       data=json.dumps(payload1),
                       content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res1.status_code, 201)
        my_t1 = res1.get_json()["ticket"]
        t1_id = my_t1["queue_id"]
        t1_pos = my_t1["position"]

        # Booker 2 joins the same station queue
        c2 = app.test_client()
        self._login_session(c2, self.user2_email)
        payload2 = {
            "station_id": 1,
            "driver_name": "Booker Two",
            "vehicle_model": "MG Comet EV",
            "vehicle_reg_number": "TS09WQ2222",
            "charger_type": "Fast DC"
        }
        res2 = c2.post("/api/queue/join",
                       data=json.dumps(payload2),
                       content_type="application/json",
                       headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res2.status_code, 201)
        my_t2 = res2.get_json()["ticket"]
        self.assertGreater(my_t2["position"], t1_pos)

        # Booker 1 leaves the queue
        res_leave = c1.post(f"/api/queue/{t1_id}/cancel",
                            data=json.dumps({}),
                            content_type="application/json",
                            headers={"X-CSRF-Token": "test-csrf-token-12345"})
        self.assertEqual(res_leave.status_code, 200)

        # Booker 2's position dynamically moves up
        res_t2_updated = c2.get("/api/queue/my")
        self.assertEqual(res_t2_updated.status_code, 200)
        updated_t2 = res_t2_updated.get_json()["ticket"]
        self.assertEqual(updated_t2["position"], t1_pos)

    def test_10_csrf_and_auth_enforcement(self):
        """Verify unauthenticated calls receive HTTP 401 and forged CSRF on state changes receives HTTP 403."""
        anon_client = app.test_client()
        res_unauth = anon_client.get("/api/bookings/my")
        self.assertEqual(res_unauth.status_code, 401)

        auth_client = app.test_client()
        self._login_session(auth_client, self.user1_email)
        res_no_csrf = auth_client.post("/api/bookings",
                                       data=json.dumps({}),
                                       content_type="application/json")
        self.assertEqual(res_no_csrf.status_code, 403)

    def test_11_admin_oversight(self):
        """Verify admin can view all bookings and walk-in queues across all stations."""
        user_client = app.test_client()
        self._login_session(user_client, self.user1_email, role="user")
        res_user = user_client.get("/api/admin/bookings")
        self.assertEqual(res_user.status_code, 403)

        admin_client = app.test_client()
        self._login_session(admin_client, self.admin_email, role="admin")
        res_admin_b = admin_client.get("/api/admin/bookings")
        self.assertEqual(res_admin_b.status_code, 200)
        self.assertIn("bookings", res_admin_b.get_json())

        res_admin_q = admin_client.get("/api/admin/queues")
        self.assertEqual(res_admin_q.status_code, 200)
        self.assertIn("queues", res_admin_q.get_json())

if __name__ == "__main__":
    unittest.main()
