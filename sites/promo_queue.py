#!/usr/bin/env python3
"""Drip-post a queue of Facebook group posts: read the rules, join, post, slowly.

  promo_queue.py QUEUE.json [QUEUE2.json ...]            one run: join what's due, post at most --per-run groups
  promo_queue.py QUEUE.json [QUEUE2.json ...] --status   what's done / waiting / skipped
  options: --per-run N (1)  --per-day N (6)  --joins N (3)  --hours 9-22  --dry

QUEUE.json: {"answer": "membership-question answer"?,
             "items": [{"group": "ID", "text": "path", "text_nolink": "path"?, "media": "path"?,
             "lang": "es"?, "answer": "..."?, "note": ""?}, ...]}
(paths may start with ~; relative paths are relative to the queue file)

"answer" (per queue or per item) is what join_fbgroup.py writes into membership questions. Without
one, a group you are not in yet is left "pending" until you join it yourself.

Several queues run together: the limits count across all of them, because they share one Facebook
account. The queue file is never written (it can live in a git repo that should stay clean):
progress goes to ~/.local/share/tabrelay/promo-queue/<dir>-<queue>-<hash>.state.json, per group
"status" (todo / pending / posted / skipped / failed) plus "at" and "why".

Why slowly: posting the same link in many groups in a short time gets a Facebook account blocked
from posting, and looks like spam to the groups. Default: 1 post per run, 6 per day, 09-22 local
time. If Facebook shows a block or "slow down" notice, the runner stops (state "blocked" at the
top level), raises a notification, and nothing posts until you clear it (set "blocked" to null
in the state file).

Rules first: before joining or posting, each group's About page is read. Rules that ban
self-promotion skip the group; rules that ban links use "text_nolink" (or skip the group if there
is none). The rule matching is a regular expression over several languages: it errs towards
skipping, but it can't understand every rule, so read the rules of the groups you queue.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
MAX_TRIES = 3  # a failed post is retried on later runs, at most this many times in all

BAN_PROMO = re.compile(r"(?i)no (self[- ]?)?promo|self[- ]?promotion.{0,40}(not allowed|aren.t allowed|prohibit)|no advertis|"
                       r"autopromoci|no publiques promociones|dilarang (ber)?promosi|promosi diri|proibid[oa].{0,20}divulga|"
                       r"không quảng cáo|cấm quảng cáo|ห้ามโฆษณา|禁止广告|禁止宣傳|禁止推广|"
                       r"ingen (egen)?reklam|reklam (är )?(inte|ej) tillåten|ingen marknadsföring|förbjudet att (göra )?reklam|"
                       r"ingen reklame|reklame (er )?(ikke|ikkje) (tilladt|tillatt|tillat)|"
                       r"不允许.{0,4}广告|禁止.{0,4}广告|谢绝.{0,4}广告|不得.{0,6}广告|禁止.{0,4}推广")
BAN_LINKS = re.compile(r"(?i)no (outside |external |foreign )?links|links? (are )?(not allowed|prohibited)|outside links|"
                       r"prohibido publicar.{0,20}links|enlaces? prohibid|dilarang.{0,20}link|cấm.{0,10}link|ห้าม.{0,10}ลิงก์|"
                       r"inga länkar|länkar (är )?(inte|ej) tillåtna|ingen lenker|ingen links|禁止.{0,4}链接|不允许.{0,4}链接")
BLOCK = re.compile(r"(?i)you can.t post right now|temporarily blocked|you.re temporarily|slow down|"
                   r"we limit how often|tạm thời bị chặn|ถูกบล็อกชั่วคราว")


def classify_rules(rules):
    """"promo" when the rules ban self-promotion, "links" when they ban links, else ""."""
    if BAN_PROMO.search(rules or ""):
        return "promo"
    if BAN_LINKS.search(rules or ""):
        return "links"
    return ""


def is_blocked(log):
    return bool(BLOCK.search(log or ""))


def outcome(log):
    """(status, why) for one post_fbgroup.py run, from its output."""
    if "  posted" in log:
        return "posted", ""
    if "SKIP: not a member" in log:
        return "pending", "not a member yet"
    if "SKIP: no 'Write something'" in log:
        return "skipped", "members can't post (admin-only or buy/sell)"
    return "failed", (log.strip().splitlines() or ["?"])[-1][:160]


def runnable(item):
    """Whether this run should look at the item (todo, pending, or failed fewer than MAX_TRIES times)."""
    st = item.get("status", "todo")
    return st in ("todo", "pending") or (st == "failed" and item.get("tries", 0) < MAX_TRIES)


def in_hours(hour, h0, h1):
    return h0 <= hour < h1


def path(q, p):
    p = os.path.expanduser(p)
    return p if os.path.isabs(p) else os.path.join(os.path.dirname(q), p)


def state_file(qf, base=None):
    """<data dir>/promo-queue/<dir>-<queue>-<hash of the full path>.state.json"""
    d = os.path.join(base or tr.LOG_DIR, "promo-queue")
    os.makedirs(d, exist_ok=True)
    qf = os.path.abspath(qf)
    stem = os.path.basename(qf).removesuffix(".json")
    parent = os.path.basename(os.path.dirname(qf))
    h = hashlib.sha1(qf.encode()).hexdigest()[:8]
    return os.path.join(d, f"{parent}-{stem}-{h}.state.json")


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def about(g):
    tab = tr.job("open", url=f"https://www.facebook.com/groups/{g}/about", background=True)["tabId"]
    try:
        time.sleep(9)
        txt = tr.evaluate(tab, "(document.querySelector('[role=main]')||document.body).innerText")
    finally:
        tr.job("close", tabId=int(tab))
    name = txt.split("\n")[0][:60]
    i = txt.find("Group rules")
    rules = txt[i:i + 5000] if i >= 0 else ""
    if "Join group" in txt[:500]:
        member = "no"
    elif "Cancel request" in txt[:800]:
        member = "pending"
    else:
        member = "yes"
    return name, rules, member


class Queue:
    def __init__(self, qf, base=None):
        self.qf = qf
        self.sf = state_file(qf, base)
        try:
            with open(self.sf) as f:
                self.state = json.load(f)
        except (OSError, ValueError):
            self.state = {"blocked": None, "items": {}}
        with open(qf) as f:
            raw = json.load(f)
        self.answer = raw.get("answer")
        self.items = [dict(it, **self.state["items"].get(it["group"], {})) for it in raw["items"]]

    def save(self):
        for it in self.items:
            self.state["items"][it["group"]] = {k: it[k] for k in ("status", "at", "why", "name", "tries") if k in it}
        tmp = self.sf + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.sf)

    def posted_on(self, day):
        return sum(1 for it in self.items if it.get("status") == "posted" and it.get("at", "").startswith(day))

    def last_post(self):
        return max([it.get("at", "") for it in self.items if it.get("status") == "posted"] or [""])


def order(queues):
    """The queue that posted least recently goes first."""
    return sorted(queues, key=lambda q: q.last_post())


def parse_args(argv):
    p = argparse.ArgumentParser(description="Drip-post a queue of Facebook group posts.")
    p.add_argument("queues", nargs="+")
    p.add_argument("--status", action="store_true")
    p.add_argument("--per-run", type=int, default=1)
    p.add_argument("--per-day", type=int, default=6)
    p.add_argument("--joins", type=int, default=3)
    p.add_argument("--hours", default="9-22")
    p.add_argument("--dry", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    h0, h1 = (int(x) for x in args.hours.split("-"))
    queues = [Queue(os.path.abspath(os.path.expanduser(x))) for x in args.queues]

    if args.status:
        for q in queues:
            print("==", q.qf)
            for it in q.items:
                print(f"{it.get('status', 'todo'):8} {it['group']:28} {it.get('lang', ''):3} {it.get('name', '')[:40]:40} "
                      f"{it.get('at', '')} {it.get('why', '')}")
            print("blocked:", q.state.get("blocked"))
        return
    blocked = [q.state["blocked"] for q in queues if q.state.get("blocked")]
    if blocked:  # one Facebook account: a block in any queue stops them all
        print("queue is blocked:", blocked[0])
        return
    if not in_hours(time.localtime().tm_hour, h0, h1):
        print("outside posting hours")
        return
    try:
        if not tr.job("ping", timeout=40).get("ok"):
            return
    except Exception:  # noqa: BLE001
        return
    today = time.strftime("%Y-%m-%d")
    posted_today = sum(q.posted_on(today) for q in queues)
    posts = joined = 0
    for q in order(queues):
        if posts >= args.per_run or posted_today >= args.per_day:
            break
        n, j = run_queue(q, args.per_run - posts, args.per_day - posted_today, args.joins - joined, args.dry)
        if n is None:
            return
        posts += n
        posted_today += n
        joined += j


def run_queue(q, per_run, per_day, joins, dry):
    """Post at most min(per_run, per_day) groups of one queue. Returns (posts, joins), or
    (None, None) when Facebook blocked posting."""
    qf, items, save = q.qf, q.items, q.save
    posts = joined = 0
    for it in items:
        if not runnable(it):
            continue
        if posts >= per_run or posts >= per_day:
            break
        g = it["group"]
        name, rules, member = about(g)
        it["name"] = name
        text = path(qf, it["text"])
        ban = classify_rules(rules)
        if ban == "promo":
            it.update(status="skipped", why="rules ban self-promotion", at=now())
            save()
            print(g, name, "skipped: rules ban promotion")
            continue
        if ban == "links":
            if it.get("text_nolink"):
                text = path(qf, it["text_nolink"])
            else:
                it.update(status="skipped", why="rules ban links, no text_nolink", at=now())
                save()
                continue
        if member == "no":
            answer = it.get("answer") or q.answer
            if not answer:
                it.update(status="pending", why="not a member, and no membership answer in the queue: join it yourself")
                save()
                continue
            if joined >= joins:
                continue
            if dry:
                print(g, name, "would join")
                continue
            out = subprocess.run([sys.executable, os.path.join(HERE, "join_fbgroup.py"), g, "--answer", answer],
                                 capture_output=True, text=True).stdout
            joined += 1
            print(out.strip())
            if "joined" not in out:
                it.update(status="pending", why="join requested", at=now())
                save()
                continue
        elif member == "pending":
            it.update(status="pending", why="waiting for admin approval")
            save()
            continue
        if dry:
            print(g, name, "would post", os.path.basename(text))
            continue
        cmd = [sys.executable, os.path.join(HERE, "post_fbgroup.py"), text, g]
        if it.get("media"):
            cmd += ["--media", path(qf, it["media"])]
        out = subprocess.run(cmd, capture_output=True, text=True)
        log = out.stdout + out.stderr
        print(log.strip()[-600:])
        if is_blocked(log):
            q.state["blocked"] = f"{now()} Facebook limited posting (group {g})"
            save()
            tr.notify("Promo queue", "Facebook limited posting; the queue stopped. Check the account.")
            return None, None
        status, why = outcome(log)
        if status == "failed":
            it["tries"] = it.get("tries", 0) + 1
        it.update(status=status, why=why)
        if status != "pending":
            it["at"] = now()
        if status == "posted":
            posts += 1
        save()
    return posts, joined


if __name__ == "__main__":
    main()
