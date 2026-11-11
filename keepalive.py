#!/usr/bin/env python3
"""Keep site logins alive in your Chrome without keeping their tabs open.

  keepalive.py            visit every site that is due (run it every 30 min, e.g. from launchd/cron)
  keepalive.py --all      visit every site now
  keepalive.py --status   last visit and login state per site
  keepalive.py --only a,b visit just these sites now (handy when testing a marker)

Some sites end a web session after a few hours without a visit. Each visit opens the site's
logged-in page in an INACTIVE background tab of an existing Chrome window (no new window, no focus
change), lets the page's own scripts run for ~25 s so the site can refresh its session, checks the
page still shows something only a logged-in user sees, and closes the tab.

The sites come from the "keepalive" section of the config file (~/.config/tabrelay/config.json):

  "keepalive": {
    "youtube": {"url": "https://studio.youtube.com/", "every": 720,
                "marker": "Dashboard", "login": "https://studio.youtube.com/"}
  }

  url     the page to visit (its domain must be on the extension's allow-list)
  every   minutes between visits (default 720)
  marker  a JavaScript regular expression the logged-in page's text matches
  login   where to log in again (shown in the notification; default: url)

When a login is gone, a desktop notification names the site and the login URL (once, until it is
fixed). Scripts can check the state first: `keepalive.py --status`. Some sites end sessions on the
server after a fixed time however often they are visited; the log line for a lost login says how
long it lasted, so you can see which.

Does nothing when Chrome or the extension isn't answering (machine asleep, Chrome closed): it
never launches Chrome. State: ~/.local/share/tabrelay/keepalive.json.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import tabrelay as tr  # noqa: E402

STATE = os.path.join(tr.LOG_DIR, "keepalive.json")
LOGIN_URL = re.compile(r"login|signin|sign_in|sign-in|passport|accounts\.google", re.I)


def load_sites(cfg):
    """{name: (url, every_minutes, marker, login_url)} from the config's "keepalive" section.
    Raises ValueError naming the first bad entry."""
    raw = cfg.get("keepalive")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('"keepalive" must be an object of {name: {url, every, marker, login}}')
    sites = {}
    for name, s in raw.items():
        if not isinstance(s, dict) or not s.get("url") or not s.get("marker"):
            raise ValueError(f'keepalive site {name!r} needs at least "url" and "marker"')
        if not str(s["url"]).startswith("https://"):
            raise ValueError(f"keepalive site {name!r}: url must be https://")
        try:
            re.compile(s["marker"])
        except re.error as e:
            raise ValueError(f"keepalive site {name!r}: marker is not a valid regular expression ({e})") from None
        sites[name] = (s["url"], int(s.get("every", 720)), s["marker"], s.get("login") or s["url"])
    return sites


def due(sites, state, now, only=None, everything=False):
    """Names of the sites to visit now: --only, --all, or those whose interval has passed (with two
    minutes of slack, so a 30-minute timer doesn't skip a site that is due in 30 minutes)."""
    if only is not None:
        return [n for n in sites if n in only]
    if everything:
        return list(sites)
    return [n for n, (_, every, _, _) in sites.items() if now - state.get(n, {}).get("ts", 0) >= every * 60 - 120]


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE)


def visit(site):
    url, _, marker, _ = site
    tab = tr.job("open", url=url, background=True)["tabId"]
    try:
        ok = False
        href = url  # if the page never answers, report where it was sent
        for _ in range(6):  # up to ~30 s for the page and its session refresh
            time.sleep(5)
            try:
                href, has = tr.evaluate(tab, f"[location.href, new RegExp({json.dumps(marker)}).test(document.body?.innerText||'')]")
            except Exception:  # noqa: BLE001
                continue
            if LOGIN_URL.search(href):
                break
            if has:
                ok = True
                time.sleep(10)  # let its background calls (token refresh) finish
                break
        return ok, href if not ok else url
    finally:
        try:
            tr.job("close", tabId=int(tab))
        except Exception:  # noqa: BLE001
            pass


def main():
    a = sys.argv[1:]
    try:
        sites = load_sites(tr.CONFIG)
    except ValueError as e:
        sys.exit(f"keepalive: {e} (in {tr.config_path()})")
    if not sites:
        sys.exit(f'keepalive: no sites configured; add a "keepalive" section to {tr.config_path()} '
                 "(see config.example.json)")
    st = load()
    if "--status" in a:
        for n in sites:
            s = st.get(n, {})
            print(f"{n:14} {'ok' if s.get('ok') else 'LOGGED OUT' if 'ok' in s else '-':10} "
                  f"last {s.get('at', '-')}  since {s.get('since', '-')}  "
                  f"{'' if s.get('ok', True) else s.get('where', '')}")
        return
    try:
        if not tr.job("ping", timeout=40).get("ok"):
            return
    except Exception:  # noqa: BLE001
        return  # Chrome closed or machine asleep: try next time
    now = time.time()
    only = set(a[a.index("--only") + 1].split(",")) if "--only" in a else None
    for n in due(sites, st, now, only, "--all" in a):
        s = st.get(n, {})
        try:
            ok, where = visit(sites[n])
        except Exception as e:  # noqa: BLE001
            print(f"{time.strftime('%Y-%m-%d %H:%M')} {n}: error {e}", file=sys.stderr)
            continue
        was_ok = s.get("ok", True)
        stamp = time.strftime("%Y-%m-%d %H:%M")
        # How long a login lasts: "since" is when this state began (first seen logged in / out).
        lasted = ""
        if not ok and was_ok and s.get("since_ts"):
            lasted = f" (logged in for about {(now - s['since_ts']) / 3600:.0f} h since {s.get('since')})"
        changed = ok != was_ok or not s.get("since")
        st[n] = {"ok": ok, "ts": now, "at": stamp, "where": where,
                 "since": stamp if changed else s.get("since"),
                 "since_ts": now if changed else s.get("since_ts", now)}
        save(st)
        print(f"{stamp} {n}: {'ok' if ok else 'LOGGED OUT ' + where}{lasted}")
        if not ok and was_ok:
            tr.notify("Login expired", f"{n}: log in again at {sites[n][3]}")


if __name__ == "__main__":
    main()
