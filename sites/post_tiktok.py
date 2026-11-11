#!/usr/bin/env python3
"""Post a video to TikTok through TikTok Studio's web upload page in the logged-in Chrome, via Tabrelay.

  post_tiktok.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"caption": ["line", "line", ...]}   (who can see it: Everyone, the page default)
New posts sit in "Content under review" (Only me) for a few minutes, then go public.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp"
EDITOR = "document.querySelector('.public-DraftEditor-content')"


def dismiss(tab):
    tr.evaluate(tab, "(()=>{[...document.querySelectorAll('button')].filter(b=>b.offsetParent &&"
                     " /^(Got it|OK)$/.test(b.innerText.trim())).forEach(b=>b.click()); return 1})()")


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    done = tr.already_posted("tiktok", video, meta["caption"][0])
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"tt_{name}.png"))

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
        tr.front(tab)
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
        tr.front(tab)
    if not tr.wait_for(tab, "!!document.querySelector('input[type=file][accept^=video]')", 60):
        snap("no_upload")
        sys.exit("no upload box (logged out?)")
    tr.set_files(tab, "document.querySelector('input[type=file][accept^=video]')", [video])
    name = os.path.basename(video)
    if not tr.wait_for(tab, f"!!{EDITOR} && document.body.innerText.includes('Uploaded')", 300, 2):
        snap("no_upload_done")
        sys.exit("upload didn't finish")
    time.sleep(2)
    dismiss(tab)
    tr.click(tab, EDITOR)
    tr.evaluate(tab, f"(()=>{{{EDITOR}.focus(); document.execCommand('selectAll'); return 1}})()")
    tr.key(tab, "Backspace")
    for i, line in enumerate(meta["caption"]):
        if i:
            tr.key(tab, "Enter")
        tr.type_text(tab, line)
    time.sleep(1)
    tr.key(tab, "Escape")  # the hashtag suggestions
    text = tr.evaluate(tab, EDITOR + ".innerText")
    if meta["caption"][0] not in text or name.rsplit(".", 1)[0] == text.strip():
        snap("caption")
        sys.exit(f"caption came out as {text!r}")
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    dismiss(tab)
    tr.click(tab, "[...document.querySelectorAll('button')].find(b=>b.innerText.trim()=='Post')")
    # Sometimes a "post now?" confirmation (content check still running).
    time.sleep(3)
    tr.evaluate(tab, "(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.offsetParent &&"
                     " /^Post now$/.test(b.innerText.trim())); if(b) b.click(); return 1})()")
    if not tr.wait_for(tab, "location.href.includes('/tiktokstudio/content')", 60):
        snap("not_posted")
        sys.exit("didn't reach the posts list")
    snap("posted")
    tr.record_post("tiktok", video, meta["caption"][0], "posted")
    tr.detach(tab)
    print("posted")


if __name__ == "__main__":
    main()
