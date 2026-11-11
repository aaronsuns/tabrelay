#!/usr/bin/env python3
"""Post a video to Douyin (抖音) through creator.douyin.com in the logged-in Chrome, via Tabrelay.

  post_douyin.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"title": "<= 30 characters", "body": ["line", ...]}
After 发布 the page goes to 内容管理; new posts show there once processed/reviewed.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://creator.douyin.com/creator-micro/content/upload"
TITLE = "document.querySelector('input[placeholder*=作品标题]')"
BODY = ("(document.querySelector('.zone-container[contenteditable=true]') ||"
        " document.querySelector('.editor-kit-container [contenteditable=true]'))")


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    if len(meta["title"]) > 30:
        sys.exit("title is over 30 characters")
    done = tr.already_posted("douyin", video, meta["title"])
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']}; --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"dy_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
        tr.front(tab)
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
        tr.front(tab)
    if not tr.wait_for(tab, "!!document.querySelector('input[type=file]')", 60):
        fail("no_upload_box")
    tr.set_files(tab, "document.querySelector('input[type=file]')", [video])
    if not tr.wait_for(tab, f"!!{TITLE} && !!{BODY}", 120):
        fail("form")
    time.sleep(2)
    # Uploaded: the 重新上传 control shows and no upload progress is left.
    if not tr.wait_for(tab, "document.body.innerText.includes('重新上传') && !/上传中|上传进度|%/.test("
                            "(document.querySelector('[class*=upload]')||{innerText:''}).innerText)", 300, 2, keep_front=True):
        fail("upload")

    def dismiss():
        tr.evaluate(tab, "(()=>{[...document.querySelectorAll('button')].filter(b=>b.offsetParent &&"
                         " /^(我知道了|知道了)$/.test(b.innerText.trim())).forEach(b=>b.click()); return 1})()")

    dismiss()
    if tr.fill_lines(tab, TITLE, [meta["title"]]) != meta["title"]:
        fail("title")
    body = meta["body"][:-1] + [meta["body"][-1] + " "]  # the space closes the topic list
    focused = f"({BODY}.contains(document.activeElement) || {BODY} === document.activeElement)"
    end = time.time() + 180  # the editor takes focus only once the video is parsed
    while True:
        tr.front(tab)
        tr.click(tab, BODY)
        if tr.wait_for(tab, focused, 5):
            break
        if time.time() > end:
            fail("body_focus")
    if meta["body"][0][:10] not in tr.fill_lines(tab, BODY, body, clear=False):
        fail("body")
    if tr.evaluate(tab, TITLE + ".value") != meta["title"]:
        fail("title_changed")
    time.sleep(1)
    tr.key(tab, "Escape")
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    dismiss()
    tr.click(tab, tr.by_text("发布", "button"))
    if not tr.wait_for(tab, "location.href.includes('/content/manage')", 60):
        fail("publish")
    snap("published")
    tr.record_post("douyin", video, meta["title"], "published")
    tr.detach(tab)
    print("published")


if __name__ == "__main__":
    main()
