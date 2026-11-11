#!/usr/bin/env python3
"""Join Discord servers with your logged-in Discord account.

  join_discord.py GUILD_ID [GUILD_ID ...] [--shots DIR]

For each server: open its preview (/channels/<id>), click "Join <server>", then walk Discord's
onboarding: question screens are skipped (no notification roles), the rules screen is scrolled to
the end and accepted with Finish. Prints: joined / already member / CAPTCHA / CHECK (see shot).

A captcha (hCaptcha) or an outside verification (Bloxlink, a website sign-in) needs you: the
script brings that tab to the front, prints CAPTCHA and leaves the tab open for you. Read each
server's rules and ad channels before posting (post_discord.py --survey, then read #rules /
#how-to-advertise). Never post in honeypot / "do not type" channels.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402


def go(tab, path, wait=9):
    tr.evaluate(tab, "(()=>{history.pushState({},'',%r);dispatchEvent(new PopStateEvent('popstate'));return 1})()" % path)
    time.sleep(wait)


def button(tab, test):
    """Centre of the last visible button whose text passes the JS test (t = trimmed text)."""
    return tr.evaluate(tab, "(()=>{const b=[...document.querySelectorAll('button,[role=button]')].filter(b=>{const t=(b.innerText||'').trim();"
                            "return b.getBoundingClientRect().width>0&&(" + test + ")}).pop();if(!b)return null;"
                            "const r=b.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2,b.disabled===true]})()")


def member(tab, guild):
    t = tr.evaluate(tab, "document.body.innerText")
    listed = tr.evaluate(tab, "!!document.querySelector('[data-list-item-id=\"guildsnav___%s\"]')" % guild)
    return listed and "preview mode" not in t and "/onboarding" not in tr.evaluate(tab, "location.pathname")


def captcha(tab):
    return tr.evaluate(tab, "[...document.querySelectorAll('iframe')].some(f=>/captcha/.test(f.src))")


def main():
    a = sys.argv[1:]
    shots = a[a.index("--shots") + 1] if "--shots" in a else tempfile.gettempdir()
    guilds = [x for x in a if x.isdigit()]
    tab = tr.job("open", url="https://discord.com/channels/@me")["tabId"]
    keep = False
    try:
        time.sleep(12)
        tr.front(tab)
        for g in guilds:
            go(tab, f"/channels/{g}")
            name = tr.evaluate(tab, "document.title")[:60]
            if member(tab, g):
                print(f"{g} {name}: already member")
                continue
            xy = button(tab, "/^Join /.test(t)")
            if not xy:
                tr.shot(tab, os.path.join(shots, f"dcjoin_{g}.png"))
                print(f"{g} {name}: CHECK no Join button (invite-only, or age-gated?)")
                continue
            tr.click_at(tab, xy[0], xy[1])
            time.sleep(6)
            for _ in range(12):  # onboarding: question screens, then the rules screen
                if captcha(tab):
                    break
                if member(tab, g):
                    break
                tr.evaluate(tab, "[...document.querySelectorAll('*')].filter(e=>e.scrollHeight>e.clientHeight+20)"
                                 ".forEach(e=>{e.scrollTop=e.scrollHeight})")
                time.sleep(1)
                # Rules screens sometimes have an "I have read and agree" checkbox.
                cb = tr.evaluate(tab, "(()=>{const c=[...document.querySelectorAll('[role=checkbox],input[type=checkbox]')]"
                                      ".find(c=>c.getBoundingClientRect().width>0&&c.getAttribute('aria-checked')!=='true'&&!c.checked);"
                                      "if(!c)return null;const r=c.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")
                if cb:
                    tr.click_at(tab, *cb)
                    time.sleep(1)
                nxt = button(tab, "/^(Finish|Complete|Submit|Skip|Next|Accept|Agree)/.test(t)")
                if not nxt or nxt[2]:
                    time.sleep(3)
                    continue
                tr.click_at(tab, nxt[0], nxt[1])
                time.sleep(4)
            time.sleep(4)
            if captcha(tab):
                tr.front(tab, force=True)
                keep = True
                print(f"{g} {name}: CAPTCHA, the tab is in front for you")
                break
            if member(tab, g):
                print(f"{g} {name}: joined")
            else:
                tr.shot(tab, os.path.join(shots, f"dcjoin_{g}.png"))
                print(f"{g} {name}: CHECK, see dcjoin_{g}.png")
    finally:
        if not keep:
            tr.job("close", tabId=int(tab))


if __name__ == "__main__":
    main()
