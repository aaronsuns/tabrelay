#!/usr/bin/env python3
"""Post a video as an Instagram Reel through instagram.com's
"Create" dialog in the logged-in Chrome, via Tabrelay.

  post_instagram.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB] [--handle NAME]

META.json: {"text": ["line", ...]}   (links in captions are not clickable)
--handle NAME  your Instagram user name: after posting, the reel link is looked up on your profile
Keeps the video's own aspect ratio (Crop > Original) and leaves "Share to Facebook" off:
Facebook reels are posted separately with post_facebook.py.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://www.instagram.com/"
DLG = "[role=dialog]"


def items(tab):
    return tr.evaluate(tab, f"[...document.querySelectorAll('{DLG} *')].filter(e=>e.childElementCount==0&&e.innerText)"
                            ".map(e=>e.innerText.trim())")


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    handle = a[a.index("--handle") + 1].lstrip("@") if "--handle" in a else None
    text_key = meta["text"][0]
    done = tr.already_posted("instagram", video, text_key)
    if done and "--again" not in a and not draft:
        print(f"skip: already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        return
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"ig_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
    tr.front(tab)
    create = ("[...document.querySelectorAll('a,div[role=button],span')].find(e=>/^(Create|New post)$/"
              ".test((e.innerText||'').trim()) || e.querySelector?.('svg[aria-label=\"New post\"]'))")
    if not tr.wait_for(tab, "!!" + create, 60):
        fail("no_create")
    tr.click(tab, create)
    time.sleep(2)
    if "Post" in items(tab) and "Select from computer" not in items(tab):
        tr.click(tab, tr.leaf("Post"))  # the Create menu: Post / Live / Ad
        time.sleep(2)
    if not tr.wait_for(tab, f"!!document.querySelector('{DLG} input[type=file]')", 30):
        fail("no_upload_box")
    tr.set_files(tab, f"document.querySelector('{DLG} input[type=file]')", [video])
    if not tr.wait_for(tab, f"[...document.querySelectorAll('{DLG} *')].some(e=>e.innerText==='Crop')", 120, 2,
                       keep_front=True):
        fail("crop")
    # Aspect ratio: the button in the bottom-left corner of the crop view, then Original.
    corner = tr.evaluate(tab, f"(()=>{{const d=document.querySelector('{DLG} [role=dialog]')||"
                              f"document.querySelector('{DLG}'); const bs=[...d.querySelectorAll('[role=button],button')]"
                              ".filter(b=>b.querySelector('svg')); const r=bs.map(b=>b.getBoundingClientRect())"
                              ".sort((p,q)=>(q.bottom-p.bottom)||(p.left-q.left))[0]; return r?[r.x+r.width/2,r.y+r.height/2]:null})()")
    if corner:
        tr.click_at(tab, *corner)
        time.sleep(1.5)
    try:
        tr.click(tab, tr.leaf("Original"))
    except RuntimeError:
        pass
    time.sleep(1)
    for _ in range(2):  # Crop -> Edit -> details
        tr.click(tab, tr.leaf("Next"))
        time.sleep(4)
    editor = f"document.querySelector('{DLG} [contenteditable=true]')"
    if not tr.wait_for(tab, "!!" + editor, 60):
        fail("caption_box")
    got = tr.fill_lines(tab, editor, meta["text"])
    if text_key.split()[0] not in got:
        fail("text")
    # Share to Facebook must stay off.
    on = tr.evaluate(tab, f"[...document.querySelectorAll('{DLG} input[type=checkbox]')].filter(c=>c.checked).length")
    if on:
        fail("share_toggle_on")
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    tr.click(tab, tr.leaf("Share"))
    ok = tr.wait_for(tab, "/has been shared/.test(document.body.innerText)", 600, 3, keep_front=True)
    if not ok:
        fail("sharing")
    link = "shared"
    if handle:
        tr.evaluate(tab, f"location.href={json.dumps(f'https://www.instagram.com/{handle}/reels/')}")
        link = tr.wait_for(tab, "[...document.querySelectorAll('a[href*=\"/reel/\"]')].map(a=>a.href)[0]", 30) or link
    snap("posted")
    tr.record_post("instagram", video, text_key, link)
    tr.detach(tab)
    print(link)


if __name__ == "__main__":
    main()
