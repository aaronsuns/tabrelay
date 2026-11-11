#!/usr/bin/env python3
"""Post a video to X through x.com's composer in the logged-in Chrome, via Tabrelay.

  post_x.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB] [--handle NAME]

META.json: {"text": ["line", ...]}   (280 characters in all; links count as 23)
--handle NAME  your X user name, to look up the new post's link (default: read from the page's
               Profile link)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://x.com/compose/post"
# X's late-2026 composer is a plain <textarea> with no data-testids; the old ids are kept as fallbacks.
BOX = "(document.querySelector('[data-testid=tweetTextarea_0]')||document.querySelector('[role=dialog] textarea'))"
BTN = ("(document.querySelector('[role=dialog] [data-testid=tweetButton]')||document.querySelector('[data-testid=tweetButton]')"
       "||[...document.querySelectorAll('[role=dialog] button')].find(b=>(b.innerText||'').trim()==='Post'))")
FILE = "(document.querySelector('[data-testid=fileInput]')||document.querySelector('[role=dialog] input[type=file]'))"


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    handle = a[a.index("--handle") + 1].lstrip("@") if "--handle" in a else None
    text_key = meta["text"][0]
    done = tr.already_posted("x", video, text_key)
    if done and "--again" not in a and not draft:
        print(f"skip: already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        return
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"x_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
    tr.front(tab)
    if not tr.wait_for(tab, "!!" + BOX, 60):
        fail("no_composer")
    # A cut-off earlier run leaves its draft (text and video) in the composer: X allows one video
    # per post, so remove any media already attached before adding ours.
    for _ in range(4):
        rm = tr.evaluate(tab, "[...document.querySelectorAll('[aria-label=\"Remove media\"]')].length")
        if not rm:
            break
        tr.click(tab, "document.querySelector('[aria-label=\"Remove media\"]')")
        time.sleep(1)
    # Enter is a plain new line in X's editor.
    # A trailing space closes the hashtag typeahead, which otherwise swallows the Post click.
    got = tr.fill_lines(tab, BOX, meta["text"][:-1] + [meta["text"][-1] + " "])
    if text_key.split()[0] not in got:
        fail("text")
    tr.set_files(tab, FILE, [video])
    # The button stays disabled while the video uploads.
    ready = (f"(()=>{{const b={BTN}; return b && b.getAttribute('aria-disabled')!=='true' && !b.disabled"
             " && !!document.querySelector('[data-testid=attachments] video, [data-testid=attachments], [role=dialog] video')})()")
    if not tr.wait_for(tab, ready, 300, 2, keep_front=True):
        fail("upload")
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    tr.click(tab, BTN)
    if not tr.wait_for(tab, "!document.querySelector('[role=dialog] [data-testid=tweetTextarea_0], [role=dialog] textarea')", 120, 2):
        fail("posting")
    if not handle:
        handle = (tr.evaluate(tab, "document.querySelector('a[data-testid=AppTabBar_Profile_Link]')?.getAttribute('href')||''")
                  or "").strip("/")
    link = "posted"
    if handle:
        tr.evaluate(tab, f"location.href={json.dumps(f'https://x.com/{handle}')}")
        first = json.dumps(text_key[:40])
        link = tr.wait_for(tab, "[...document.querySelectorAll('article')].filter(a=>a.innerText.includes(" + first + "))"
                                ".map(a=>a.querySelector('a[href*=\"/status/\"] time')?.parentElement?.href)[0]",
                           30) or link
    snap("posted")
    tr.record_post("x", video, text_key, link)
    tr.detach(tab)
    print(link)


if __name__ == "__main__":
    main()
