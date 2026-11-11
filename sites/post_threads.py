#!/usr/bin/env python3
"""Post a video (or image) to Threads
via threads.com's composer in the logged-in Chrome, via Tabrelay.

  post_threads.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB] [--handle NAME]

META.json: {"text": ["line", ...]}   (500 characters; links are clickable on Threads)
--handle NAME  your Threads user name: after posting, the post link is looked up on your profile
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://www.threads.com/"
DLG = "[...document.querySelectorAll('[role=dialog]')].find(d=>d.querySelector('[contenteditable=true]'))"
BOX = DLG + "?.querySelector('[contenteditable=true]')"
POST = "[...(" + DLG + ")?.querySelectorAll('[role=button]')||[]].find(b=>(b.innerText||'').trim()=='Post')"


def main():
    a = sys.argv[1:]
    media, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    handle = a[a.index("--handle") + 1].lstrip("@") if "--handle" in a else None
    text_key = meta["text"][0]
    done = tr.already_posted("threads", media, text_key)
    if done and "--again" not in a and not draft:
        print(f"skip: already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        return
    if len("\n".join(meta["text"])) > 500:
        sys.exit("text over 500 characters")
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"threads_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    opened = tab is None  # opened here (not by post_plan): close it at the end
    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
    tr.front(tab)
    opener = "[...document.querySelectorAll('[role=button],a')].find(b=>(b.getAttribute('aria-label')||b.innerText||'').trim()=='New thread')"
    if not tr.wait_for(tab, "!!" + opener, 60):
        fail("no_new_thread_button")
    # A single click sometimes does nothing (page still hydrating): retry by coordinates, then
    # fall back to the feed's "What's new?" box.
    whatsnew = "[...document.querySelectorAll('[role=button],span')].find(b=>(b.innerText||'').trim()==\"What's new?\")"
    for sel in (opener, opener, opener, whatsnew):
        xy = tr.evaluate(tab, "(()=>{const b=" + sel + "; if(!b) return null; const r=b.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]})()")
        if xy:
            tr.click_at(tab, *xy)
        if tr.wait_for(tab, "!!(" + BOX + ")", 15):
            break
    else:
        fail("no_composer")
    got = tr.fill_lines(tab, BOX, meta["text"][:-1] + [meta["text"][-1] + " "])
    if text_key.split()[0] not in got:
        fail("text")
    tr.set_files(tab, "[...(" + DLG + ").querySelectorAll('input[type=file]')].pop()", [media])
    # Post stays disabled until the upload is processed.
    ready = ("(()=>{const b=" + POST + "; const d=" + DLG + "; return !!b && b.getAttribute('aria-disabled')!=='true'"
             " && !!d.querySelector('video,img[src^=blob]')})()")
    if not tr.wait_for(tab, ready, 300, 2, keep_front=True):
        fail("upload")
    time.sleep(2)
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    tr.click(tab, POST)
    if not tr.wait_for(tab, "!(" + DLG + ")", 180, 2, keep_front=True):
        fail("posting")
    # The video uploads AFTER the dialog closes ("Posting..." bar). Leaving the page now cancels
    # the post, so wait for Threads' "Posted" toast (with its View link).
    if not tr.wait_for(tab, "/\\bPosted\\b/.test(document.body.innerText) && !/Posting/.test(document.body.innerText)", 600, 3, keep_front=True):
        fail("upload_after_post")
    time.sleep(3)
    link = "posted"
    if handle:
        tr.evaluate(tab, f"location.href={json.dumps(f'https://www.threads.com/@{handle}')}")
        first = json.dumps(text_key[:30])
        link = tr.wait_for(tab, "[...document.querySelectorAll('a[href*=\"/post/\"]')].find(a=>{let p=a;for(let i=0;i<8&&p;i++){p=p.parentElement;if(p&&p.innerText.includes(" + first + "))return true}return false})?.href",
                           40) or link
    snap("posted")
    tr.record_post("threads", media, text_key, link)
    if opened:
        tr.job("close", tabId=int(tab))
    else:
        tr.detach(tab)
    print(link)


if __name__ == "__main__":
    main()
