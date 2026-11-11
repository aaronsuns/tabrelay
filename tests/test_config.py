import json
import os
import tempfile
import unittest
import unittest.mock

import tabrelay


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, text):
        p = os.path.join(self.dir.name, "config.json")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_missing_file_is_empty(self):
        self.assertEqual(tabrelay.load_config(os.path.join(self.dir.name, "nope.json")), {})

    def test_valid_file(self):
        p = self.write(json.dumps({"profile": "You@Example.com"}))
        self.assertEqual(tabrelay.load_config(p), {"profile": "You@Example.com"})

    def test_broken_file_is_ignored(self):
        p = self.write("{not json")
        with unittest.mock.patch("sys.stderr"):
            self.assertEqual(tabrelay.load_config(p), {})

    def test_non_object_is_ignored(self):
        p = self.write("[1, 2]")
        with unittest.mock.patch("sys.stderr"):
            self.assertEqual(tabrelay.load_config(p), {})

    def test_profile_precedence(self):
        cfg = {"profile": " Config@Example.com "}
        self.assertEqual(tabrelay.default_profile(cfg, env={}), "config@example.com")
        self.assertEqual(tabrelay.default_profile(cfg, env={"TABRELAY_PROFILE": "Env@Example.com"}), "env@example.com")
        self.assertEqual(tabrelay.default_profile({}, env={}), "")

    def test_paths(self):
        home = os.path.expanduser("~")
        self.assertEqual(tabrelay.config_path({}), os.path.join(home, ".config", "tabrelay", "config.json"))
        self.assertEqual(tabrelay.config_path({"XDG_CONFIG_HOME": "/x"}), "/x/tabrelay/config.json")
        self.assertEqual(tabrelay.config_path({"TABRELAY_CONFIG": "/y/c.json"}), "/y/c.json")
        self.assertEqual(tabrelay.data_dir({}), os.path.join(home, ".local", "share", "tabrelay"))
        self.assertEqual(tabrelay.data_dir({"XDG_DATA_HOME": "/d"}), "/d/tabrelay")
        self.assertEqual(tabrelay.data_dir({"TABRELAY_DATA_DIR": "/z"}), "/z")


if __name__ == "__main__":
    unittest.main()
