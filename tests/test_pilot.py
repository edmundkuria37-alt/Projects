import json
import threading
import unittest
import urllib.request
from datetime import date, datetime, timedelta
from http.server import HTTPServer

from model import unit_economics
from pilot import db, loans, mpesa, scoring, telemetry
from pilot.server import make_handler

START = date(2026, 1, 5)


def seed(conn, grace_days=3):
    conn.execute("INSERT INTO riders (id, name, msisdn, consent_at) VALUES (1, 'Otieno', '254712000001', '2026-01-05')")
    conn.execute("INSERT INTO vehicles VALUES ('IMEI1', 'KMFA 123A', 1, 'Pilot SACCO')")
    conn.execute("INSERT INTO loans VALUES ('BB001', 'IMEI1', 120000, 2000, 70, ?, ?)",
                 (START.isoformat(), grace_days))
    conn.commit()


def pay(conn, receipt, amount, when: date):
    return mpesa.record_c2b(conn, {
        "TransID": receipt, "TransAmount": str(amount), "BillRefNumber": "bb001 ",
        "TransTime": when.strftime("%Y%m%d") + "090000", "MSISDN": "254712000001",
    })


class MpesaTest(unittest.TestCase):
    def test_duplicate_callback_is_ignored_and_ref_is_normalised(self):
        conn = db.connect()
        seed(conn)
        self.assertEqual(pay(conn, "QAB1", 2000, START), {"stored": True, "matched": True})
        self.assertEqual(pay(conn, "QAB1", 2000, START), {"stored": False, "matched": True})
        self.assertEqual(conn.execute("SELECT SUM(amount) FROM payments").fetchone()[0], 2000)


class LoanTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        seed(self.conn)

    def test_status_before_first_installment(self):
        s = loans.status(self.conn, "BB001", START + timedelta(days=3))
        self.assertEqual((s.due_to_date, s.arrears, s.days_late), (0, 0, 0))

    def test_days_late_counts_from_oldest_uncovered_installment(self):
        pay(self.conn, "Q1", 2000, START + timedelta(days=7))
        s = loans.status(self.conn, "BB001", START + timedelta(days=13))
        self.assertEqual(s.arrears, 0)
        s = loans.status(self.conn, "BB001", START + timedelta(days=18))   # week-2 due on day 14
        self.assertEqual((s.arrears, s.days_late), (2000, 4))

    def test_collections_escalate_then_release(self):
        day = START + timedelta(days=8)
        self.assertEqual(loans.run_collections(self.conn, day)[0]["action"], "REMINDER")
        day = START + timedelta(days=10)
        self.assertEqual(loans.run_collections(self.conn, day)[0]["action"], "WARNING")
        day = START + timedelta(days=11)
        self.assertEqual(loans.run_collections(self.conn, day)[0]["action"], "IMMOBILIZE_ON_STOP")
        self.assertEqual(loans.run_collections(self.conn, day), [])          # no duplicate lock command
        pay(self.conn, "Q2", 2000, day)
        self.assertEqual(loans.run_collections(self.conn, day)[0]["action"], "RELEASE")
        kinds = [r["kind"] for r in self.conn.execute("SELECT kind FROM commands ORDER BY id")]
        self.assertEqual(kinds, ["IMMOBILIZE_ON_STOP", "RELEASE"])

    def test_reminders_are_deduplicated_per_day(self):
        day = START + timedelta(days=8)
        loans.run_collections(self.conn, day)
        loans.run_collections(self.conn, day)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)


def trip(start: datetime, n: int, speed=30.0, dlat=0.0008):
    return [{"ts": (start + timedelta(seconds=10 * i)).isoformat(), "lat": -1.28 + dlat * i, "lon": 36.82,
             "speed_kmh": speed, "ignition": True} for i in range(n)]


class TelemetryTest(unittest.TestCase):
    def test_summary_distance_hours_and_events(self):
        conn = db.connect()
        seed(conn)
        pts = trip(datetime(2026, 1, 6, 8), 361)        # 1 hour, ~32 km
        pts[100]["speed_kmh"] = 75                       # overspeed
        pts[101]["speed_kmh"] = 0                        # then hard stop: 75 -> 0 in 10s
        self.assertEqual(telemetry.ingest(conn, "IMEI1", pts), 361)
        self.assertEqual(telemetry.ingest(conn, "IMEI1", pts), 0)
        s = telemetry.daily_summary(conn, "IMEI1", "2026-01-06")
        self.assertAlmostEqual(s["km"], 32.0, delta=1.0)
        self.assertAlmostEqual(s["riding_hours"], 1.0, delta=0.02)
        self.assertEqual((s["overspeed_events"], s["harsh_brakes"]), (1, 1))

    def test_reporting_gap_is_not_counted_as_a_trip(self):
        conn = db.connect()
        seed(conn)
        a = trip(datetime(2026, 1, 6, 8), 2)
        b = trip(datetime(2026, 1, 6, 12), 2, dlat=0.0008)
        b[0]["lat"] += 1
        b[1]["lat"] += 1
        telemetry.ingest(conn, "IMEI1", a + b)
        self.assertLess(telemetry.daily_summary(conn, "IMEI1", "2026-01-06")["km"], 1)


class ScoringTest(unittest.TestCase):
    def test_good_rider_outscores_late_payer(self):
        as_of = START + timedelta(days=42)
        scores = {}
        for label, pays in [("good", True), ("late", False)]:
            conn = db.connect()
            seed(conn)
            for d in range(1, 43):
                day = START + timedelta(days=d)
                if day.weekday() < 6:
                    telemetry.ingest(conn, "IMEI1", trip(datetime.combine(day, datetime.min.time()) + timedelta(hours=8), 400))
                if pays and d % 7 == 0:
                    pay(conn, f"Q{d}", 2000, day)
            scores[label] = scoring.score(conn, 1, as_of)
        self.assertEqual(scores["good"]["components"]["repayment"], 1.0)
        self.assertGreater(scores["good"]["score"], scores["late"]["score"] + 200)
        self.assertTrue(300 <= scores["late"]["score"] <= 850)


class ServerTest(unittest.TestCase):
    def test_mpesa_callback_ack_and_command_poll(self):
        conn = db.connect()
        seed(conn)
        srv = HTTPServer(("127.0.0.1", 0), make_handler(conn))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"

        def post(path, body):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req))

        try:
            ack = post("/mpesa/c2b/confirmation", {"TransID": "QX1", "TransAmount": "500", "BillRefNumber": "BB001",
                                                   "TransTime": "20260106090000", "MSISDN": "254712000001"})
            self.assertEqual(ack["ResultCode"], 0)
            post("/jobs/collections", {"as_of": (START + timedelta(days=12)).isoformat()})
            cmds = json.load(urllib.request.urlopen(base + "/devices/IMEI1/commands"))
            self.assertEqual([c["kind"] for c in cmds], ["IMMOBILIZE_ON_STOP"])
        finally:
            srv.shutdown()
            srv.server_close()


class ModelTest(unittest.TestCase):
    def test_base_case_reaches_target_in_year_three(self):
        y = unit_economics.yearly(unit_economics.simulate(unit_economics.Assumptions()))
        self.assertGreater(y[2]["revenue"], 130e6)
        self.assertLess(y[0]["revenue"], y[1]["revenue"])


if __name__ == "__main__":
    unittest.main()
