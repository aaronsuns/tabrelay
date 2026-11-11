"""The local server: job routing per Chrome profile, and refusing requests a web page could send."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import tabrelay


class RouterTest(unittest.TestCase):
    def test_profile_job_goes_to_that_profile(self):
        r = tabrelay.Router()
        r.put({"id": 1}, "A@example.com")
        self.assertIsNone(r.take("b@example.com", timeout=0.05))
        self.assertEqual(r.take("a@example.com", timeout=0.05), {"id": 1})

    def test_job_without_profile_goes_to_anyone(self):
        r = tabrelay.Router()
        r.put({"id": 1})
        self.assertEqual(r.take("b@example.com", timeout=0.05), {"id": 1})
        self.assertIsNone(r.take("", timeout=0.05))

    def test_own_queue_first_then_fifo(self):
        r = tabrelay.Router()
        r.put({"id": "any"})
        r.put({"id": "a1"}, "a")
        r.put({"id": "a2"}, "a")
        self.assertEqual([r.take("a", 0.05)["id"] for _ in range(3)], ["a1", "a2", "any"])

    def test_take_wakes_up_on_put(self):
        r = tabrelay.Router()
        threading.Timer(0.05, lambda: r.put({"id": 7})).start()
        self.assertEqual(r.take("x", timeout=2), {"id": 7})

    def test_profiles_seen(self):
        r = tabrelay.Router()
        r.take("a@example.com", 0)
        r.take("", 0)
        self.assertEqual(r.profiles(), ["(not signed in)", "a@example.com"])


class HandlerTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = mock.patch.object(tabrelay, "TOKEN_FILE", os.path.join(d.name, "token.json"))
        p.start()
        self.addCleanup(p.stop)
        self.token = tabrelay.token()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), tabrelay.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, path, body, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="POST",
                                     data=json.dumps(body).encode(), headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_token_file_is_private(self):
        self.assertEqual(os.stat(tabrelay.TOKEN_FILE).st_mode & 0o777, 0o600)

    def test_job_needs_token(self):
        code, out = self.post("/job", {"kind": "profiles"})
        self.assertEqual(code, 403)
        code, out = self.post("/job", {"kind": "profiles"}, {tabrelay.TOKEN_HEADER: "wrong"})
        self.assertEqual(code, 403)
        code, out = self.post("/job", {"kind": "profiles"}, {tabrelay.TOKEN_HEADER: self.token})
        self.assertEqual(code, 200)
        self.assertIn("profiles", out["result"])

    def test_web_page_origin_is_refused(self):
        h = {tabrelay.TOKEN_HEADER: self.token, "Origin": "https://evil.example"}
        self.assertEqual(self.post("/job", {"kind": "profiles"}, h)[0], 403)
        self.assertEqual(self.post("/result/x", {}, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.post("/result/x", {}, {"Origin": "chrome-extension://abc"})[0], 200)

    def test_foreign_host_is_refused(self):
        h = {tabrelay.TOKEN_HEADER: self.token, "Host": f"rebind.example:{self.port}"}
        self.assertEqual(self.post("/job", {"kind": "profiles"}, h)[0], 403)

    def test_job_round_trip(self):
        def extension():
            job = tabrelay.router.take("me@example.com", timeout=5)
            self.assertEqual(job["token"], self.token)
            self.post(f"/result/{job['id']}", {"result": {"echo": job["kind"]}})
        threading.Thread(target=extension, daemon=True).start()
        code, out = self.post("/job", {"kind": "ping", "timeout": 5}, {tabrelay.TOKEN_HEADER: self.token})
        self.assertEqual((code, out), (200, {"result": {"echo": "ping"}}))


if __name__ == "__main__":
    unittest.main()
