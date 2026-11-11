import unittest

import keepalive


class KeepaliveConfigTest(unittest.TestCase):
    def test_sites_from_config(self):
        sites = keepalive.load_sites({"keepalive": {
            "a": {"url": "https://a.example/", "marker": "Inbox|Home", "every": 90},
            "b": {"url": "https://b.example/", "marker": "Dashboard", "login": "https://b.example/login"},
        }})
        self.assertEqual(sites["a"], ("https://a.example/", 90, "Inbox|Home", "https://a.example/"))
        self.assertEqual(sites["b"], ("https://b.example/", 720, "Dashboard", "https://b.example/login"))

    def test_empty(self):
        self.assertEqual(keepalive.load_sites({}), {})

    def test_bad_entries(self):
        for bad in ({"keepalive": []}, {"keepalive": {"a": {"url": "https://a.example/"}}},
                    {"keepalive": {"a": {"url": "http://a.example/", "marker": "x"}}},
                    {"keepalive": {"a": {"url": "https://a.example/", "marker": "("}}}):
            with self.assertRaises(ValueError):
                keepalive.load_sites(bad)

    def test_due(self):
        sites = {"fast": ("u", 90, "m", "l"), "slow": ("u", 720, "m", "l")}
        now = 1_000_000
        state = {"fast": {"ts": now - 89 * 60}, "slow": {"ts": now - 60 * 60}}
        self.assertEqual(keepalive.due(sites, state, now), ["fast"])  # within the 2-minute slack
        self.assertEqual(keepalive.due(sites, {}, now), ["fast", "slow"])
        self.assertEqual(keepalive.due(sites, state, now, everything=True), ["fast", "slow"])
        self.assertEqual(keepalive.due(sites, state, now, only={"slow"}), ["slow"])


if __name__ == "__main__":
    unittest.main()
