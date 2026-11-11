#!/usr/bin/env python3
"""Post text (+ optional video or image) to Facebook groups you have joined.

  post_fbgroup.py TEXT_FILE GROUP_ID [GROUP_ID ...] [--media FILE] [--draft] [--shots DIR]

- Reads each group's About page first and prints its rules: stop and skip a group whose rules
  ban promotion or links (e.g. "no self-promo", "DILARANG PROMOSI").
- Join first (by hand, or join_fbgroup.py). A group that still shows "Join group" is skipped
  with a note.
- Trap: a word in the text that matches a Page name (e.g. "Pets" in a URL) opens a "mention"
  list; a click inside the text closes it, otherwise Post would tag that Page.
- --draft fills the composer and saves a screenshot without posting. Look at it.
- Each post is logged (tabrelay log) as platform "fbgroup".
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

DLG = '[...document.querySelectorAll("[role=dialog]")].find(d=>d.querySelector("[contenteditable=true]"))'
ED = DLG + '.querySelector("[contenteditable=true]")'


def nav(tab, url, wait=8):
    tr.evaluate(tab, f"(()=>{{location.href={url!r};return 1}})()")
    time.sleep(wait)


def main():
    a = sys.argv[1:]
    media = a[a.index("--media") + 1] if "--media" in a else None
    shots = a[a.index("--shots") + 1] if "--shots" in a else tempfile.gettempdir()
    draft = "--draft" in a
    skip = {media, shots}
    args = [x for x in a if not x.startswith("--") and x not in skip]
    text_file, groups = args[0], args[1:]
    text = open(text_file).read().strip()
    for g in groups:
        # A fresh tab per group: an unsent draft blocks navigation ("Leave page?").
        tab = tr.job("open", url=f"https://www.facebook.com/groups/{g}/about")["tabId"]
        try:
            time.sleep(8)
            tr.front(tab)
            if f"/groups/{g}" not in tr.evaluate(tab, "location.href"):
                print(f"=== {g}: page did not open, skipped")
                continue
            main_txt = tr.evaluate(tab, '(document.querySelector("[role=main]")||document.body).innerText')
            name = main_txt.split("\n")[0][:60]
            i = main_txt.find("Group rules")
            print(f"=== {g} {name}\n  rules: " + (main_txt[i:i + 600].replace("\n", " | ") if i >= 0 else "(none listed)"))
            head = main_txt[:300].split("Related groups")[0]  # suggested groups carry their own "Join group"
            if "Join group" in head and "\nJoined" not in head:
                print("  SKIP: not a member (join the group first)")
                continue
            nav(tab, f"https://www.facebook.com/groups/{g}/")
            if not tr.evaluate(tab, '!![...document.querySelectorAll("[role=main] [role=button]")].find(b=>(b.innerText||"").trim()=="Write something...")'):
                print("  SKIP: no 'Write something' box (buy/sell-only group: an ad there is off-topic)")
                continue
            # The composer dialog sometimes opens slowly or ignores the first click: wait, retry once.
            for _ in range(2):
                tr.click(tab, '[...document.querySelectorAll("[role=main] [role=button]")].find(b=>(b.innerText||"").trim()=="Write something...")')
                if tr.wait_for(tab, "!!(" + DLG + ")", 20, 2):
                    break
            else:
                print("  CHECK: composer did not open, skipped")
                continue
            time.sleep(2)
            tr.click(tab, ED)
            tr.fill_lines(tab, ED, text.split("\n"))
            time.sleep(1)
            x, y = tr.evaluate(tab, '(()=>{const b=' + ED + '.getBoundingClientRect();return [b.x+b.width/2,b.y+10]})()')
            tr.click_at(tab, x, y)  # closes a mention typeahead
            time.sleep(1)
            if media:
                if not tr.evaluate(tab, '!!(' + DLG + '.querySelector("input[type=file]"))'):
                    tr.click(tab, DLG + '.querySelector("[aria-label=\\"Photo/video\\"]")')
                    time.sleep(2)
                tr.set_files(tab, '[...document.querySelectorAll("[role=dialog] input[type=file]")].pop()', [media])
                time.sleep(25)
            shot = os.path.join(shots, f"fbgroup_{g}.png")
            tr.shot(tab, shot)
            print("  filled, screenshot", shot)
            if draft:
                continue
            x, y = tr.evaluate(tab, '(()=>{const b=[...' + DLG + '.querySelectorAll("[role=button]")].find(b=>(b.getAttribute("aria-label")||b.innerText||"").trim()=="Post").getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2]})()')
            tr.click_at(tab, x, y)
            time.sleep(20)
            open_dlg = tr.evaluate(tab, '!!(' + DLG + ')')
            if open_dlg:
                # Show Facebook's message (e.g. "You can't post right now") so callers can stop.
                msg = tr.evaluate(tab, '[...document.querySelectorAll("[role=dialog],[role=alertdialog]")].map(d=>d.innerText).join(" | ").replace(/\\s+/g," ").slice(0,400)')
                print("  CHECK: composer still open: " + msg)
            else:
                print("  posted")
            if not open_dlg:
                tr.record_post("fbgroup", media or text_file, f"{name} group post (facebook.com/groups/{g})", "posted")
        finally:
            tr.job("close", tabId=int(tab))


if __name__ == "__main__":
    main()
