#!/usr/bin/env python3
"""tabrelay: drive pages in your real, logged-in Chrome from the command line.

The Tabrelay extension (./extension) picks up jobs from a small local server and runs them as
Chrome DevTools Protocol commands through chrome.debugger, in the Chrome profile you are already
signed in to, on the sites you allowed in the extension's options page only.

  tabrelay serve                     run the local server (other commands start it when it's missing)
  tabrelay ping                      is the extension connected? (prints its version and profile)
  tabrelay profiles                  Chrome profiles whose extension copy has checked in
  tabrelay tabs                      open tabs on allowed sites
  tabrelay open URL                  new background window with URL; prints the tab id
  tabrelay eval TAB JS               run JS in the page (awaits promises), print the JSON result
  tabrelay shot TAB FILE.png         screenshot
  tabrelay file TAB JS PATH...       JS must evaluate to an <input type=file>; sets it to PATH(s)
  tabrelay type TAB TEXT             type TEXT into whatever has focus
  tabrelay key TAB KEY               press a key (Enter, Tab, Escape, Backspace, ...)
  tabrelay click TAB JS              JS evaluates to an element; a real mouse click on its centre
  tabrelay front TAB                 raise the tab's window (only when a site insists on it)
  tabrelay close TAB | detach TAB    close the tab | stop debugging it (Chrome's info bar goes)
  tabrelay reload                    reload the extension from disk after editing it
  tabrelay reload-ext NAME|ID        reload another unpacked extension (macOS, Apple Events)
  tabrelay log                       what the site scripts have posted (posted.jsonl)
  tabrelay config                    show the config file, data dir and profile in use

Environment: TABRELAY_PROFILE (Chrome profile to use: the Google account email the profile is
signed in to), TABRELAY_CONFIG (config file path), TABRELAY_DATA_DIR, TABRELAY_FRONT=1.
"""

import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

__version__ = "0.1.0"

PORT = 47833  # fixed: the extension's host permission names it
HERE = os.path.dirname(os.path.realpath(__file__))
TOKEN_FILE = os.path.join(HERE, "extension", "token.json")
TOKEN_HEADER = "X-Tabrelay-Token"


# ---------------------------------------------------------------------------------------------
# Configuration


def config_path(env=None) -> str:
    env = os.environ if env is None else env
    if env.get("TABRELAY_CONFIG"):
        return os.path.expanduser(env["TABRELAY_CONFIG"])
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "tabrelay", "config.json")


def load_config(path=None) -> dict:
    """The config file as a dict; {} when it doesn't exist. A broken file is reported, not fatal."""
    path = path or config_path()
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"tabrelay: ignoring unreadable config {path}: {e}", file=sys.stderr)
        return {}
    if not isinstance(cfg, dict):
        print(f"tabrelay: ignoring config {path}: not a JSON object", file=sys.stderr)
        return {}
    return cfg


def default_profile(cfg=None, env=None) -> str:
    """The Chrome profile jobs go to: TABRELAY_PROFILE, else the config's "profile", else "" (any)."""
    env = os.environ if env is None else env
    if env.get("TABRELAY_PROFILE"):
        return env["TABRELAY_PROFILE"].strip().lower()
    cfg = load_config() if cfg is None else cfg
    return str(cfg.get("profile") or "").strip().lower()


def data_dir(env=None) -> str:
    env = os.environ if env is None else env
    if env.get("TABRELAY_DATA_DIR"):
        return os.path.expanduser(env["TABRELAY_DATA_DIR"])
    base = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "tabrelay")


CONFIG = load_config()
PROFILE = default_profile(CONFIG)
LOG_DIR = data_dir()


def token() -> str:
    """The shared secret between this command and the extension (created on first use, mode 600)."""
    if not os.path.exists(TOKEN_FILE):
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"token": secrets.token_hex(24)}, f)
    with open(TOKEN_FILE) as f:
        return json.load(f)["token"]


def notify(title, text):
    """A desktop notification where one is available (macOS, notify-send); always printed too."""
    print(f"[{title}] {text}", file=sys.stderr)
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f"display notification {json.dumps(text)} with title {json.dumps(title)}"],
                       check=False, capture_output=True)
    else:
        try:
            subprocess.run(["notify-send", title, text], check=False, capture_output=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------
# Server: /next (the extension long-polls), /result/<id> (the extension answers), /job (the CLI
# submits a job and waits for its result).


class Router:
    """Job queues per Chrome profile. A job for a profile waits for that profile's extension copy;
    a job without one (key "*") goes to whichever copy asks first."""

    def __init__(self):
        self.cv = threading.Condition()
        self.queues: dict = {}
        self.seen: dict = {}  # profile -> last time its extension copy polled

    def put(self, job, profile=""):
        key = (profile or "*").lower()
        with self.cv:
            self.queues.setdefault(key, deque()).append(job)
            self.cv.notify_all()

    def take(self, profile="", timeout=20.0):
        profile = (profile or "").lower()
        end = time.monotonic() + timeout
        with self.cv:
            self.seen[profile] = time.time()
            while True:
                for key in (profile, "*"):
                    q = self.queues.get(key)
                    if q:
                        return q.popleft()
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self.cv.wait(left)

    def profiles(self, within=90):
        now = time.time()
        with self.cv:
            return sorted(p or "(not signed in)" for p, t in self.seen.items() if now - t < within)


router = Router()
waiting: dict = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def deny(self, why):
        self.send(403, json.dumps({"error": why}).encode())

    def trusted_origin(self) -> bool:
        """Refuse anything a web page could send: a foreign Host (DNS rebinding) or a page Origin.
        The extension's requests carry no Origin or a chrome-extension:// one."""
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.startswith("chrome-extension://")

    def do_GET(self):
        if not self.trusted_origin():
            return self.deny("forbidden origin")
        url = urlparse(self.path)
        if url.path == "/next":
            profile = (parse_qs(url.query).get("p") or [""])[0]
            job = router.take(profile, timeout=20)
            if job is None:
                return self.send(204)
            return self.send(200, json.dumps(job).encode())
        self.send(404)

    def do_POST(self):
        if not self.trusted_origin():
            return self.deny("forbidden origin")
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send(400, b'{"error": "bad json"}')
        if self.path.startswith("/result/"):
            slot = waiting.get(self.path[len("/result/"):])
            if slot:
                slot["result"] = body
                slot["event"].set()
            return self.send(200, b"{}")
        if self.path == "/job":
            if not secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), token()):
                return self.deny("missing or wrong token")
            if body.get("kind") == "profiles":
                return self.send(200, json.dumps({"result": {"profiles": router.profiles()}}).encode())
            job = dict(body, id=uuid.uuid4().hex, token=token())
            slot = {"event": threading.Event()}
            waiting[job["id"]] = slot
            router.put(job, body.get("profile"))
            ok = slot["event"].wait(body.get("timeout", 120))
            waiting.pop(job["id"], None)
            if not ok:
                seen = router.profiles()
                hint = f" Connected profiles: {', '.join(seen)}." if seen else " No extension has checked in."
                return self.send(504, json.dumps({"error": "no answer from the extension (is Chrome open?)" + hint}).encode())
            return self.send(200, json.dumps(slot["result"]).encode())
        self.send(404)


def serve(port=PORT):
    token()
    print(f"tabrelay serving on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


# ---------------------------------------------------------------------------------------------
# Client

_started = False


def _start_server() -> bool:
    """Start `tabrelay serve` in the background (once per process), wait for its port."""
    global _started
    if _started:
        return False
    _started = True
    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(os.path.join(LOG_DIR, "serve.log"), "a")
    subprocess.Popen([sys.executable, os.path.realpath(__file__), "serve"], stdout=log, stderr=log,
                     start_new_session=True)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            print("… started tabrelay serve; the extension checks in within 30 s (click its icon to hurry)",
                  file=sys.stderr)
            return True
        except OSError:
            time.sleep(0.1)
    return False


def job(kind, timeout=120, **kw):
    """Send one job to the extension and return its result (raises RuntimeError on its error)."""
    if PROFILE:
        kw.setdefault("profile", PROFILE)
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/job", method="POST",
                                 data=json.dumps(dict(kw, kind=kind, timeout=timeout)).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header(TOKEN_HEADER, token())
    try:
        with urllib.request.urlopen(req, timeout=timeout + 10) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = json.loads(e.read() or b"{}")
    except urllib.error.URLError:
        if not _start_server():
            sys.exit("tabrelay serve isn't running and couldn't be started")
        return job(kind, timeout=timeout, **kw)
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def cdp(tab, method, params=None, timeout=120):
    return job("cdp", timeout=timeout, tabId=int(tab), method=method, params=params or {})


def evaluate(tab, js, by_value=True):
    r = cdp(tab, "Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": by_value,
                                      "userGesture": True})
    if r.get("exceptionDetails"):
        d = r["exceptionDetails"]
        raise RuntimeError((d.get("exception") or {}).get("description") or d.get("text"))
    return r["result"].get("value") if by_value else r["result"]


def element(tab, js):
    obj = evaluate(tab, js, by_value=False)
    if obj.get("subtype") == "null" or "objectId" not in obj:
        raise RuntimeError("no element: " + js)
    return obj["objectId"]


def set_files(tab, js, paths):
    cdp(tab, "DOM.setFileInputFiles", {"objectId": element(tab, js), "files": [os.path.abspath(p) for p in paths]})


def events(tab, method=None):
    return job("events", tabId=int(tab), method=method)["events"]


def choose_file(tab, click_js, paths, seconds=15):
    """Upload through the page's own file chooser: intercept the dialog, click what opens it,
    hand the chooser's input the files. For pages whose visible input isn't the one they read."""
    cdp(tab, "Page.enable")
    cdp(tab, "Page.setInterceptFileChooserDialog", {"enabled": True})
    events(tab, "Page.fileChooserOpened")  # drop stale ones
    try:
        click(tab, click_js)
        end = time.time() + seconds
        while time.time() < end:
            got = events(tab, "Page.fileChooserOpened")
            if got:
                cdp(tab, "DOM.setFileInputFiles", {"files": [os.path.abspath(p) for p in paths],
                                                   "backendNodeId": got[-1]["params"]["backendNodeId"]})
                return
            time.sleep(0.5)
        raise RuntimeError("no file chooser opened")
    finally:
        cdp(tab, "Page.setInterceptFileChooserDialog", {"enabled": False})


def type_text(tab, text):
    cdp(tab, "Input.insertText", {"text": text})


KEYS = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46, "ArrowDown": 40, "ArrowUp": 38,
        "ArrowLeft": 37, "ArrowRight": 39}


def key(tab, name, modifiers=0):
    code = KEYS.get(name, 0)
    base = {"key": name, "code": name, "windowsVirtualKeyCode": code, "modifiers": modifiers}
    if name == "Enter":
        base["text"] = "\r"
    cdp(tab, "Input.dispatchKeyEvent", dict(base, type="keyDown"))
    cdp(tab, "Input.dispatchKeyEvent", dict(base, type="keyUp"))


def click(tab, js):
    rect = evaluate(tab, f"(() => {{ const e = ({js}); if (!e) return null; e.scrollIntoView({{block: 'center'}});"
                         " const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
    if not rect:
        raise RuntimeError("no element: " + js)
    x, y = rect
    for t in ("mousePressed", "mouseReleased"):
        cdp(tab, "Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1})


def click_at(tab, x, y):
    for t in ("mouseMoved", "mousePressed", "mouseReleased"):
        cdp(tab, "Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1})


def shot(tab, path):
    data = cdp(tab, "Page.captureScreenshot", {"format": "png"})["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))


def front(tab, force=False):
    """Keep a background tab working WITHOUT stealing the screen: Chrome throttles background
    windows (uploads stall, <video> metadata never loads, hover menus don't open), so the page
    is told it has focus (focus emulation) and is kept in the active lifecycle state. You can
    keep using the machine while a script runs: the window is only raised with force=True or
    TABRELAY_FRONT=1 (a last resort for a site that still stalls in the background)."""
    for method, params in (("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                           ("Page.setWebLifecycleState", {"state": "active"})):
        try:
            cdp(tab, method, params)
        except RuntimeError:
            pass
    if force or os.environ.get("TABRELAY_FRONT") == "1":
        try:
            cdp(tab, "Page.bringToFront")
        except RuntimeError:
            pass


def wait_for(tab, js, seconds=60, every=1.0, keep_front=False):
    """Poll JS until it returns something truthy (returned) or the time is up (None)."""
    end = time.time() + seconds
    while time.time() < end:
        if keep_front:
            front(tab)
        try:
            v = evaluate(tab, js)
            if v:
                return v
        except RuntimeError:
            pass
        time.sleep(every)
    return None


# Deep query: a recursive walk through open shadow roots (for pages built from web components).
DQ = ('const dq=(sel,root=document)=>{const out=[];const walk=r=>{r.querySelectorAll(sel).forEach(e=>out.push(e));'
      'r.querySelectorAll("*").forEach(e=>{if(e.shadowRoot)walk(e.shadowRoot)})};walk(root);return out};')


def deep(js):
    """JS function body with dq() in scope, as an expression."""
    return "(()=>{" + DQ + js + "})()"


def by_text(text, selector="button, [role=button], a"):
    """JS expression: the first visible element matching selector whose text is exactly text."""
    return deep(f"return dq({json.dumps(selector)}).find(e=>e.offsetParent!==null && "
                f"(e.innerText||e.textContent||'').trim()==={json.dumps(text)})")


def click_text(tab, text, selector="button, [role=button], a"):
    click(tab, by_text(text, selector))


def fill_lines(tab, js, lines, clear=True):
    """Click a text box / rich editor (contenteditable, Draft.js, ProseMirror), optionally clear it,
    then type lines with Enter between them. Returns its text afterwards."""
    click(tab, js)
    if clear:
        evaluate(tab, f"(()=>{{const e=({js}); e.focus(); if ('value' in e && e.tagName!='DIV') e.select();"
                      " else document.execCommand('selectAll'); return 1})()")
        key(tab, "Backspace")
    for i, line in enumerate(lines):
        if i:
            key(tab, "Enter")
        if line:
            type_text(tab, line)
    return evaluate(tab, f"(()=>{{const e=({js}); return e.value !== undefined && e.tagName!='DIV' ? e.value : e.innerText}})()")


def pos(tab, js):
    """Centre of the element js evaluates to, scrolled into view; None when missing."""
    return evaluate(tab, f"(()=>{{const e=({js}); if(!e) return null; e.scrollIntoView({{block:'center'}});"
                         " const r=e.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]})()")


def leaf(text, exact=True):
    """JS: the last visible leaf element whose text is (or contains) text."""
    cond = (f"(e.innerText||'').trim()==={json.dumps(text)}" if exact
            else f"(e.innerText||'').includes({json.dumps(text)})")
    return f"[...document.querySelectorAll('*')].filter(e=>e.offsetParent && e.childElementCount==0 && {cond}).pop()"


def tap(tab, js, wait=1.5):
    """Hover then a real click on the element's centre (for menus that need hover)."""
    if not pos(tab, js):
        raise RuntimeError("no element: " + js)
    time.sleep(0.3)
    x, y = evaluate(tab, f"(()=>{{const r=({js}).getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]}})()")
    cdp(tab, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    click_at(tab, x, y)
    time.sleep(wait)


def detach(tab):
    try:
        job("detach", tabId=int(tab))
    except RuntimeError:
        pass


# Posting log: one JSON line per post, so the same file + text never goes out twice by accident.
def _post_key(platform, path, text):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    k = f"{platform}:{h.hexdigest()[:16]}:{hashlib.sha1(text.encode()).hexdigest()[:12]}"
    return k + (":" + PROFILE.lower() if PROFILE else "")


def already_posted(platform, path, text):
    log = os.path.join(LOG_DIR, "posted.jsonl")
    k = _post_key(platform, path, text)
    if os.path.exists(log):
        for line in open(log):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("key") == k:
                return rec
    return None


def record_post(platform, path, text, result=""):
    os.makedirs(LOG_DIR, exist_ok=True)
    rec = {"key": _post_key(platform, path, text), "platform": platform, "file": os.path.basename(path),
           "text": text[:200], "result": result, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if PROFILE:
        rec["profile"] = PROFILE.lower()
    with open(os.path.join(LOG_DIR, "posted.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


RELOAD_JS = r"""
new Promise((res) => chrome.developerPrivate.getExtensionsInfo((list) => {
  const q = %s.toLowerCase();
  const e = list.find((x) => x.id === q) || list.find((x) => x.location === "UNPACKED" && x.name.toLowerCase().includes(q));
  if (!e) return res("ERR no unpacked extension matching " + q);
  chrome.developerPrivate.reload(e.id, { failQuietly: true, populateErrorForUnpacked: true }, (err) => {
    setTimeout(() => chrome.developerPrivate.getExtensionInfo(e.id, (n) =>
      res(JSON.stringify({ id: e.id, before: e.version, name: n && n.name, version: n && n.version, state: n && n.state,
        loadError: err ? (err.error || JSON.stringify(err)) : null,
        errors: n ? (n.manifestErrors || []).concat(n.runtimeErrors || []).map((x) => x.message).slice(0, 5) : [] }))), 800);
  });
})).then((x) => { document.title = "TABRELAY_RES:" + x; });
"""


def reload_ext(name):
    """Reload an unpacked extension from disk via chrome://extensions (macOS AppleScript; needs
    Chrome's View > Developer > Allow JavaScript from Apple Events). Prints its new version and
    any load errors."""
    if sys.platform != "darwin":
        sys.exit("reload-ext needs macOS (Apple Events); elsewhere use the reload button in chrome://extensions")
    js = RELOAD_JS % json.dumps(name)
    script = f"""
tell application "Google Chrome"
  set w to front window
  set t to make new tab at end of tabs of w with properties {{URL:"chrome://extensions"}}
  delay 1.5
  execute t javascript {json.dumps(js)}
  set res to ""
  repeat 40 times
    delay 0.25
    set res to title of t
    if res starts with "TABRELAY_RES:" then exit repeat
  end repeat
  close t
  return res
end tell"""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode:
        if "Apple Events" in r.stderr or "AppleScript" in r.stderr:
            sys.exit("Turn on Chrome > View > Developer > Allow JavaScript from Apple Events, then retry.")
        sys.exit(r.stderr.strip())
    return r.stdout.strip().removeprefix("TABRELAY_RES:")


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = a[0]
    need = {"open": 2, "eval": 3, "shot": 3, "file": 4, "type": 3, "key": 3, "click": 3, "front": 2,
            "close": 2, "detach": 2, "reload-ext": 2}
    if len(a) < need.get(cmd, 1):
        sys.exit(f"tabrelay {cmd}: missing arguments (tabrelay help)")
    if cmd == "--version":
        print(__version__)
    elif cmd == "serve":
        serve()
    elif cmd == "ping":
        print(json.dumps(job("ping", timeout=40)))
    elif cmd == "profiles":
        print("\n".join(job("profiles")["profiles"]) or "(no extension has checked in yet)")
    elif cmd == "tabs":
        print(json.dumps(job("tabs"), indent=2, ensure_ascii=False))
    elif cmd == "open":
        print(job("open", url=a[1])["tabId"])
    elif cmd == "eval":
        print(json.dumps(evaluate(a[1], a[2]), indent=2, ensure_ascii=False))
    elif cmd == "shot":
        shot(a[1], a[2])
        print(a[2])
    elif cmd == "file":
        set_files(a[1], a[2], a[3:])
    elif cmd == "type":
        type_text(a[1], a[2])
    elif cmd == "key":
        key(a[1], a[2])
    elif cmd == "click":
        click(a[1], a[2])
    elif cmd == "front":
        front(a[1], force=True)
    elif cmd == "close":
        job("close", tabId=int(a[1]))
    elif cmd == "detach":
        detach(a[1])
    elif cmd == "reload":
        print(json.dumps(job("reload")))
    elif cmd == "reload-ext":
        print(reload_ext(a[1]))
    elif cmd == "log":
        p = os.path.join(LOG_DIR, "posted.jsonl")
        print(open(p).read() if os.path.exists(p) else "(nothing posted yet)")
    elif cmd == "config":
        print(json.dumps({"config": config_path(), "config_exists": os.path.exists(config_path()),
                          "profile": PROFILE or "(any)", "data_dir": LOG_DIR, "token_file": TOKEN_FILE,
                          "port": PORT}, indent=2))
    else:
        sys.exit(f"unknown command {cmd!r} (tabrelay help)")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"tabrelay: {e}")
