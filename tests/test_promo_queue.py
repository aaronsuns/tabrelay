import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sites"))
import promo_queue as pq  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_promo_bans(self):
        for rules in ("Group rules: No self-promo or spam", "Self promotion is not allowed here",
                      "No advertising of any kind", "Ingen reklam i gruppen", "群规：禁止广告",
                      "DILARANG PROMOSI", "no publiques promociones"):
            self.assertEqual(pq.classify_rules(rules), "promo", rules)

    def test_link_bans(self):
        for rules in ("No external links please", "Links are not allowed", "Inga länkar", "禁止发链接"):
            self.assertEqual(pq.classify_rules(rules), "links", rules)

    def test_promo_wins_over_links(self):
        self.assertEqual(pq.classify_rules("No links. No self promotion."), "promo")

    def test_harmless_rules(self):
        for rules in ("", "Be kind and courteous. No hate speech.", "Respect everyone's privacy", None):
            self.assertEqual(pq.classify_rules(rules), "", rules)

    def test_block_notice(self):
        self.assertTrue(pq.is_blocked("CHECK: composer still open: You can't post right now"))
        self.assertTrue(pq.is_blocked("We limit how often you can post"))
        self.assertFalse(pq.is_blocked("  posted"))


class OutcomeTest(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(pq.outcome("=== 1 G\n  filled\n  posted\n"), ("posted", ""))
        self.assertEqual(pq.outcome("  SKIP: not a member (join the group first)")[0], "pending")
        self.assertEqual(pq.outcome("  SKIP: no 'Write something' box")[0], "skipped")
        self.assertEqual(pq.outcome("Traceback ...\nRuntimeError: boom"), ("failed", "RuntimeError: boom"))
        self.assertEqual(pq.outcome(""), ("failed", "?"))

    def test_runnable(self):
        self.assertTrue(pq.runnable({}))
        self.assertTrue(pq.runnable({"status": "pending"}))
        self.assertTrue(pq.runnable({"status": "failed", "tries": pq.MAX_TRIES - 1}))
        self.assertFalse(pq.runnable({"status": "failed", "tries": pq.MAX_TRIES}))
        self.assertFalse(pq.runnable({"status": "posted"}))
        self.assertFalse(pq.runnable({"status": "skipped"}))

    def test_hours(self):
        self.assertTrue(pq.in_hours(9, 9, 22))
        self.assertTrue(pq.in_hours(21, 9, 22))
        self.assertFalse(pq.in_hours(22, 9, 22))
        self.assertFalse(pq.in_hours(3, 9, 22))


class QueueStateTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    @staticmethod
    def read(p):
        with open(p) as f:
            return f.read()

    def queue_file(self, sub, items, answer=None):
        os.makedirs(os.path.join(self.dir, sub), exist_ok=True)
        p = os.path.join(self.dir, sub, "queue.json")
        with open(p, "w") as f:
            json.dump({"answer": answer, "items": items}, f)
        return p

    def test_state_file_names_differ_per_path(self):
        a = pq.state_file(os.path.join(self.dir, "one", "queue.json"), self.dir)
        b = pq.state_file(os.path.join(self.dir, "two", "queue.json"), self.dir)
        self.assertNotEqual(a, b)
        self.assertEqual(a, pq.state_file(os.path.join(self.dir, "one", "queue.json"), self.dir))
        self.assertTrue(os.path.basename(a).startswith("one-queue-"))

    def test_state_is_kept_outside_the_queue_and_merged_back(self):
        qf = self.queue_file("p", [{"group": "1", "text": "a.txt"}, {"group": "2", "text": "b.txt"}])
        before = self.read(qf)
        q = pq.Queue(qf, self.dir)
        q.items[0].update(status="posted", at="2030-01-02 10:00")
        q.items[1].update(status="failed", tries=1, at="2030-01-02 12:00", why="x")
        q.save()
        self.assertEqual(self.read(qf), before)
        q2 = pq.Queue(qf, self.dir)
        self.assertEqual(q2.items[0]["status"], "posted")
        self.assertEqual(q2.items[1]["tries"], 1)
        self.assertEqual(q2.posted_on("2030-01-02"), 1)
        self.assertEqual(q2.posted_on("2030-01-03"), 0)
        self.assertEqual(q2.last_post(), "2030-01-02 10:00")

    def test_least_recent_queue_goes_first(self):
        q1 = pq.Queue(self.queue_file("a", [{"group": "1", "text": "t"}]), self.dir)
        q2 = pq.Queue(self.queue_file("b", [{"group": "2", "text": "t"}]), self.dir)
        q3 = pq.Queue(self.queue_file("c", [{"group": "3", "text": "t"}]), self.dir)
        q1.items[0].update(status="posted", at="2030-01-02 10:00")
        q2.items[0].update(status="posted", at="2030-01-01 10:00")
        self.assertEqual([q.qf for q in pq.order([q1, q2, q3])], [q3.qf, q2.qf, q1.qf])

    def test_relative_paths(self):
        qf = os.path.join(self.dir, "p", "queue.json")
        self.assertEqual(pq.path(qf, "ad.txt"), os.path.join(self.dir, "p", "ad.txt"))
        self.assertEqual(pq.path(qf, "/abs/ad.txt"), "/abs/ad.txt")

    def test_args(self):
        a = pq.parse_args(["q1.json", "q2.json", "--per-day", "3", "--dry"])
        self.assertEqual((a.queues, a.per_day, a.per_run, a.dry), (["q1.json", "q2.json"], 3, 1, True))


if __name__ == "__main__":
    unittest.main()
