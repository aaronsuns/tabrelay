#!/usr/bin/env python3
"""Post a video as a Facebook Reel on your profile, through facebook.com's "Create reel"
dialog in the logged-in Chrome, via Tabrelay.

  post_facebook.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"text": ["line", ...], "audience": "Public"}   (audience: Public | Friends;
the profile's default is Friends, so promos set Public)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://www.facebook.com/reels/create/?surface=ADDL_PROFILE_PLUS"
D = "[role=dialog] [role=button], [role=dialog] button"
EDITOR = "document.querySelector('[role=dialog] [contenteditable=true]')"


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    audience = meta.get("audience", "Public")
    text_key = meta["text"][0]
    done = tr.already_posted("facebook", video, text_key)
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"fb_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
        tr.front(tab)
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
        tr.front(tab)
    if not tr.wait_for(tab, "!!document.querySelector('[role=dialog] input[type=file]')", 60):
        fail("no_upload_box")
    tr.set_files(tab, "document.querySelector('[role=dialog] input[type=file]')", [video])

    def heading():
        return tr.evaluate(tab, "(()=>{const d=[...document.querySelectorAll('[role=dialog]')].pop();"
                                " return d ? d.innerText.split('\\n')[0] : ''})()")

    # Next only moves on once the upload is done: press it until the next step shows.
    for want in ("Edit reel", "Reel settings"):
        end = time.time() + 300
        while heading() != want:
            tr.front(tab)
            if time.time() > end:
                fail("step_" + want.replace(" ", "_"))
            try:
                tr.click(tab, tr.by_text("Next", D))
            except RuntimeError:
                pass
            tr.wait_for(tab, f"(()=>{{const d=[...document.querySelectorAll('[role=dialog]')].pop();"
                             f" return d && d.innerText.startsWith({json.dumps(want)})}})()", 10)
    if not tr.wait_for(tab, "!!" + EDITOR, 30):
        fail("settings")
    # Never click a bare "Close": the page's own Close leaves the dialog and drops the upload.
    # A trailing space closes the hashtag typeahead, which otherwise swallows the next click.
    got = tr.fill_lines(tab, EDITOR, meta["text"][:-1] + [meta["text"][-1] + " "], clear=False)
    if text_key not in got:
        fail("text")
    current = tr.evaluate(tab, "(()=>{const b=[...document.querySelectorAll('[role=dialog] [role=button]')]"
                               ".find(e=>e.offsetParent && /^(Public|Friends|Only me|Custom)/.test(e.innerText));"
                               " return b ? b.innerText.split('\\n')[0] : ''})()")
    if current != audience:
        tr.click(tab, "[...document.querySelectorAll('[role=dialog] [role=button]')].find(e=>e.offsetParent &&"
                      " /^(Public|Friends|Only me|Custom)/.test(e.innerText))")
        radio = ("[...document.querySelectorAll('[role=dialog] [role=radio], [role=dialog] input[type=radio]')]"
                 f".find(e=>new RegExp('^{audience}').test((e.getAttribute('aria-label')||'')+"
                 "(e.closest('label,[role=listitem]')?.innerText||'')))")
        if not tr.wait_for(tab, "!!" + radio, 20):
            # The picker sometimes hangs loading: back out and open it again, once.
            tr.click(tab, "[...document.querySelectorAll('[role=dialog] [aria-label=Back]')].pop()")
            time.sleep(3)
            tr.click(tab, "[...document.querySelectorAll('[role=dialog] [role=button]')].find(e=>e.offsetParent &&"
                          " /^(Public|Friends|Only me|Custom)/.test(e.innerText))")
            if not tr.wait_for(tab, "!!" + radio, 30):
                fail("audience_picker")
        time.sleep(1)
        tr.click(tab, radio)
        time.sleep(1)
        tr.click(tab, tr.by_text("Done", D))
        time.sleep(2)
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    # Post stays disabled until the video is attached and processed (its preview shows).
    post = tr.by_text("Post", D)
    if not tr.wait_for(tab, f"(()=>{{const b={post}; return b && b.getAttribute('aria-disabled')!=='true'}})()", 300, 2,
                       keep_front=True):
        fail("post_disabled")
    tr.click(tab, post)
    if not tr.wait_for(tab, "!" + EDITOR, 180, 2):
        fail("posting")
    snap("posted")
    tr.record_post("facebook", video, text_key, f"reel, {audience}")
    tr.detach(tab)
    print("posted")


if __name__ == "__main__":
    main()
