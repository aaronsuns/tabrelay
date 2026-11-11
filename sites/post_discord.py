#!/usr/bin/env python3
"""Post one text message to Discord channels in your logged-in Discord web app.

  post_discord.py TEXT_FILE /channels/<guild>/<channel> [...]   [--survey GUILD_ID ...]

- Text is pasted through a ClipboardEvent, which keeps line breaks (Shift+Enter over CDP doesn't).
- In a background window the first Enter after a paste sometimes doesn't send: it clicks the
  box and presses Enter again, then checks the last message.
- A channel whose box says "You do not have permission" is skipped.
- --survey lists every channel of the given servers (name, text/forum, locked). Use it to pick
  channels, then READ the server's rules / channel topic before posting.
- NEVER post in channels called honeypot / "dont talk" / "leave empty": they auto-ban.
- Each post is written to the posting log (tabrelay log) as platform "discord".
Joining: join_discord.py; captchas, OAuth-style verification bots and website verifications
are your clicks (the script brings the tab to the front for you).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402


def go(tab, path, wait=6):
    tr.evaluate(tab, f"(()=>{{history.pushState({{}},'',{json.dumps(path)}); dispatchEvent(new PopStateEvent('popstate')); return 1}})()")
    time.sleep(wait)


def last(tab, n=1):
    return tr.evaluate(tab, f"[...document.querySelectorAll('li[id^=chat-messages]')].slice(-{n}).map(li=>li.innerText.slice(0,1800))") or [""]


def survey(tab, guild):
    go(tab, f"/channels/{guild}", 7)
    seen = {}
    for _ in range(10):
        for h, label in tr.evaluate(tab, "[...document.querySelectorAll('a[href^=\"/channels/\"]')].map(a=>[a.getAttribute('href'),(a.getAttribute('aria-label')||'').replace(/\\s+/g,' ').slice(0,80)]).filter(x=>x[0].split('/').length>3)"):
            seen[h] = label
        tr.evaluate(tab, "(()=>{const s=document.querySelector('nav[aria-label] [class*=scroller]');if(s)s.scrollTop+=600;return 1})()")
        time.sleep(0.7)
    print("=== server", guild)
    for h, label in seen.items():
        print("  ", h, "|", label)


def send(tab, text, path):
    go(tab, path)
    box = tr.evaluate(tab, "document.querySelector('[role=textbox]')?.getAttribute('aria-label')||''")
    if not box.startswith("Message"):
        print("SKIP (no permission)", path)
        return False
    before = last(tab, 3)
    tr.click(tab, "document.querySelector('[role=textbox]')")
    tr.evaluate(tab, f"(()=>{{const e=document.activeElement; const dt=new DataTransfer(); dt.setData('text/plain',{json.dumps(text)}); e.dispatchEvent(new ClipboardEvent('paste',{{clipboardData:dt,bubbles:true,cancelable:true}})); return 1}})()")
    time.sleep(1)
    tr.key(tab, "Enter")
    time.sleep(6)
    key = text.strip().splitlines()[0][:30]
    sent = lambda: any(key in m for m in last(tab, 3)) and last(tab, 3) != before
    if not sent():
        tr.click(tab, "document.querySelector('[role=textbox]')")
        tr.key(tab, "Enter")
        time.sleep(5)
    form = tr.evaluate(tab, "document.querySelector('form')?.innerText.replace(/\\s+/g,' ').slice(0,200)") or ""
    ok = sent() or "Slowmode" in form and any(c.isdigit() for c in form.split("Slowmode")[0][-8:])
    print("OK" if ok else "CHECK", path, "|", form[-90:])
    return ok


def main():
    a = sys.argv[1:]
    tab = tr.job("open", url="https://discord.com/channels/@me")["tabId"]
    time.sleep(8)
    tr.front(tab)
    try:
        if a and a[0] == "--survey":
            for g in a[1:]:
                survey(tab, g)
            return
        text = open(a[0]).read().strip()
        for path in a[1:]:
            if send(tab, text, path):
                tr.record_post("discord", a[0], f"{path}: {text.splitlines()[0][:80]}", "posted")
    finally:
        tr.job("close", tabId=int(tab))


if __name__ == "__main__":
    main()
