#!/usr/bin/env python3
"""Post a video note to Xiaohongshu (小红书) through creator.xiaohongshu.com in the logged-in
Chrome, via Tabrelay.

  post_xhs.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"title": "<= 20 characters", "body": ["line", "line", ...],
            "original": {"city": "上海", "day": 5}}   (optional: 内容来源声明 > 自主拍摄,
            shot in that city on that day of the current month; city level only, never a street)
The body's hashtags stay plain text (no topic picker). Prints "published" on success.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://creator.xiaohongshu.com/publish/publish?source=official&from=tab_switch"


def declare_original(tab, orig):
    """内容设置 > 添加内容类型声明 > 内容来源声明 > 自主拍摄, with a city and a day."""
    tr.tap(tab, "[...document.querySelectorAll('*')].filter(e=>e.offsetParent &&"
                " /^添加内容类型声明$/.test((e.innerText||'').trim())).pop()")
    x, y = tr.pos(tab, tr.leaf("内容来源声明"))
    tr.cdp(tab, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(1.2)
    tr.tap(tab, tr.leaf("自主拍摄"))
    tr.tap(tab, "document.querySelector('input[placeholder=下拉选择地点]')", 1)
    tr.type_text(tab, orig["city"])
    time.sleep(3)
    tr.tap(tab, tr.leaf(orig["city"]), 1)
    tr.tap(tab, "document.querySelector('input[placeholder=下拉选择日期]')", 1.5)
    tr.tap(tab, "[...document.querySelectorAll('td,div,span')].filter(e=>e.offsetParent && e.childElementCount==0"
                f" && (e.innerText||'').trim()=='{int(orig['day'])}' && !/disabled|prev|next|out/.test("
                "e.className+' '+(e.parentElement?.className||''))).shift()", 1)
    tr.tap(tab, tr.leaf("确认"), 1.5)
    if "拍摄于" not in tr.evaluate(tab, "document.body.innerText"):
        sys.exit("the 自主拍摄 declaration didn't stick")


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    if len(meta["title"]) > 20:
        sys.exit("title is over 20 characters: " + meta["title"])
    done = tr.already_posted("xhs", video, meta["title"])
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"xhs_{name}.png"))

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
        tr.front(tab)
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
        tr.front(tab)
    if not tr.wait_for(tab, "!!document.querySelector('input.upload-input')", 60):
        snap("no_upload")
        sys.exit("no upload box (logged out?)")
    tr.set_files(tab, "document.querySelector('input.upload-input')", [video])
    if not tr.wait_for(tab, "!!document.querySelector('input.d-text[placeholder*=标题]')", 120):
        snap("no_form")
        sys.exit("the form didn't appear")
    time.sleep(2)
    tr.evaluate(tab, "(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()=='我知道了');"
                     " if(b) b.click(); return true})()")
    time.sleep(1)
    tr.click(tab, "document.querySelector('input.d-text[placeholder*=标题]')")
    tr.type_text(tab, meta["title"])
    tr.click(tab, "document.querySelector('.tiptap.ProseMirror')")
    for i, line in enumerate(meta["body"]):
        if i:
            tr.key(tab, "Enter")
        if line:
            tr.type_text(tab, line)
    time.sleep(1)
    tr.key(tab, "Escape")  # a topic suggestion list may be open after the last hashtag
    if meta.get("original"):
        declare_original(tab, meta["original"])
    title = tr.evaluate(tab, "document.querySelector('input.d-text[placeholder*=标题]').value")
    if title != meta["title"]:
        sys.exit(f"title came out as {title!r}")
    # Uploaded: the file box shows the file name and no progress.
    name = os.path.basename(video)
    ok = tr.wait_for(tab, f"(()=>{{const t=document.body.innerText; return t.includes({json.dumps(name)})"
                          " && !/上传中|%/.test(t.split('设置封面')[0])})()", 300, 2)
    snap("filled")
    if not ok:
        sys.exit("upload didn't finish")
    if draft:
        print(f"draft (tab {tab})")
        return
    # 发布 sits in a closed shadow root: click its spot (right of 暂存离开, the bar's centre + 72).
    x, y = tr.evaluate(tab, "(()=>{const r=document.querySelector('xhs-publish-btn').getBoundingClientRect();"
                            " return [r.x + r.width / 2 + 72, r.y + r.height / 2]})()")
    time.sleep(3)
    for _ in range(3):
        # Only while still on the form, so a slow success page never means a second post.
        if tr.evaluate(tab, "location.href.includes('/publish/success')"):
            break
        tr.click_at(tab, x, y)
        if tr.wait_for(tab, "location.href.includes('/publish/success')", 20):
            break
    else:
        snap("not_published")
        sys.exit("no success page")
    snap("published")
    tr.record_post("xhs", video, meta["title"], "published")
    tr.detach(tab)
    print("published")


if __name__ == "__main__":
    main()
