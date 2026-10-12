"""Automatic checks. Run with:  python3 -m unittest discover tests

They use fake leads and a pretend Smartlead server on this computer,
so nothing real is ever uploaded.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import clean  # noqa: E402

SAMPLE = os.path.join(ROOT, "sample", "FAKE_vulcan7_export.csv")


class NameAndAddressCleanup(unittest.TestCase):
    def test_names(self):
        self.assertEqual(clean.split_full_name("GARCIA, MARIA L", "first_last"), ("Maria", "Garcia"))
        self.assertEqual(clean.split_full_name("JOHN & MARY SMITH", "first_last"), ("John", "Smith"))
        self.assertEqual(clean.split_full_name("SMITH JOHN & MARY", "last_first"), ("John", "Smith"))
        self.assertEqual(clean.split_full_name("AL JONES ET AL", "first_last"), ("Al", "Jones"))
        self.assertEqual(clean.tidy_name("mcDONALD-o'brien"), "McDonald-O'Brien")
        self.assertEqual(clean.first_word("JOHN A & MARY"), "John")

    def test_companies(self):
        for name in ("SUNSET HOLDINGS LLC", "THE OBRIEN FAMILY TRUST", "ESTATE OF HELEN BROOKS", "SMITH JOHN TR"):
            self.assertTrue(clean.is_company(name), name)
        for name in ("JOHN SMITH", "TRACY CORPUZ", "ESTELLE BANKS"):
            self.assertFalse(clean.is_company(name), name)

    def test_addresses(self):
        self.assertEqual(clean.tidy_address(" 5678   E CAMELBACK RD  UNIT 12b "), "5678 E Camelback Rd Unit 12B")
        self.assertEqual(clean.tidy_address("400 s 1ST ave"), "400 S 1st Ave")
        self.assertEqual(clean.tidy_state("Arizona"), "AZ")
        self.assertEqual(clean.tidy_zip("85018-1234"), "85018")


def scrub_sample(**overrides):
    settings = clean.load_settings(os.path.join(ROOT, "settings.ini"))
    settings.update(overrides)
    headers, rows = clean.read_csv(SAMPLE)
    cols, emails = clean.match_columns(headers, settings["columns"])
    return clean.scrub([("fake.csv", headers, rows, cols, emails)], settings, overrides.get("_already", {}))


class Scrub(unittest.TestCase):
    def test_default_choices(self):
        leads, removed = scrub_sample()
        emails = [l["email"] for l in leads]
        self.assertEqual(len(leads), 7)
        self.assertIn("john.smith@example.com", emails)
        self.assertNotIn("jsmith2@example.com", emails)  # second email not used in "first" mode
        self.assertEqual(len(set(emails)), len(emails))
        reasons = " | ".join(r["reason"] for r in removed)
        for expected in ("No email address", "not valid", "same property", "No property address"):
            self.assertIn(expected, reasons)

    def test_all_emails_and_skip_companies(self):
        leads, removed = scrub_sample(emails_per_owner="all", companies_and_trusts="skip")
        emails = [l["email"] for l in leads]
        self.assertIn("jsmith2@example.com", emails)
        self.assertIn("d.park@example.com", emails)
        self.assertEqual(emails.count("jsmith2@example.com"), 1)  # also in row 8: duplicate
        self.assertFalse(any(l["is_company_or_trust"] for l in leads))
        self.assertEqual(sum("Company or trust" in r["reason"] for r in removed), 3)

    def test_already_loaded_is_skipped(self):
        leads, removed = scrub_sample(_already={"maria.garcia@example.com": "2026-10-01"})
        self.assertNotIn("maria.garcia@example.com", [l["email"] for l in leads])
        self.assertIn("Already sent to Smartlead on 2026-10-01", [r["reason"] for r in removed])


class FakeSmartlead(BaseHTTPRequestHandler):
    received = []

    def log_message(self, *args):
        pass

    def _reply(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply({"id": 999, "name": "FAKE test campaign"})

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeSmartlead.received.append((self.path, data))
        self._reply({"ok": True, "upload_count": len(data["lead_list"]), "already_added_to_campaign": 0})


class LiveRunAgainstPretendSmartlead(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), FakeSmartlead)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.work = tempfile.mkdtemp()
        for item in ("run_daily.py", "settings.ini", "pipeline"):
            src = os.path.join(ROOT, item)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(self.work, item))
        os.makedirs(os.path.join(self.work, "vulcan7-inbox"))
        shutil.copy(SAMPLE, os.path.join(self.work, "vulcan7-inbox", "today.csv"))
        settings = os.path.join(self.work, "settings.ini")
        with open(settings) as f:
            text = f.read().replace("PUT_CAMPAIGN_NUMBER_HERE", "999")
        with open(settings, "w") as f:
            f.write(text)
        FakeSmartlead.received = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.work)

    def run_tool(self, *args):
        env = dict(os.environ, SMARTLEAD_API_KEY="fake-key",
                   SMARTLEAD_BASE_URL="http://127.0.0.1:%d/api/v1" % self.server.server_port)
        return subprocess.run([sys.executable, os.path.join(self.work, "run_daily.py")] + list(args),
                              capture_output=True, text=True, env=env, cwd=self.work)

    def test_test_mode_sends_nothing(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(FakeSmartlead.received, [])
        self.assertTrue(os.path.exists(os.path.join(self.work, "vulcan7-inbox", "today.csv")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "records")))

    def test_live_uploads_records_and_never_repeats(self):
        result = self.run_tool("--live")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(FakeSmartlead.received), 1)
        path, body = FakeSmartlead.received[0]
        self.assertTrue(path.startswith("/api/v1/campaigns/999/leads?api_key="))
        lead = body["lead_list"][0]
        self.assertEqual(lead["first_name"], "John")
        self.assertEqual(lead["custom_fields"]["property_address"], "1234 N Main St")
        self.assertEqual(lead["custom_fields"]["city"], "Scottsdale")
        self.assertEqual(lead["custom_fields"]["video_url"], "")
        self.assertFalse(body["settings"]["ignore_unsubscribe_list"])
        self.assertNotIn("fake-key", result.stdout)  # key never printed
        self.assertEqual(os.listdir(os.path.join(self.work, "vulcan7-inbox")), [])  # moved to processed

        # Same file again tomorrow: everyone is skipped, nothing uploaded.
        shutil.copy(SAMPLE, os.path.join(self.work, "vulcan7-inbox", "again.csv"))
        result = self.run_tool("--live")
        self.assertEqual(len(FakeSmartlead.received), 1)
        self.assertIn("Ready to upload:    0", result.stdout)


if __name__ == "__main__":
    unittest.main()
