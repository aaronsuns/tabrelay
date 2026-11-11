#!/usr/bin/env python3
"""Post a video to WeChat Channels (微信视频号) through channels.weixin.qq.com in the logged-in
Chrome, via Tabrelay.

  post_wechat.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"short_title": "6-16 chars, no emoji", "body": ["line", ...], "original": true,
            "prefilled_location": "the area name the page pre-fills"}
"original" ticks 声明原创 (only possible when publishing, not afterwards; untested so far:
the script stops with a screenshot if a dialog it doesn't know appears).
The page pre-fills a location near you. Put that text (e.g. your district, exactly as the page
shows it) in META "prefilled_location" and the script switches it to 不显示位置 and checks it
is gone; without it, the location is left as the page set it (a warning is printed).

Traps: the form lives in a <wujie-app> shadow root (use tr.deep); the visible file input is
not the one the page reads, so the upload goes through the intercepted file chooser
(tr.choose_file); and the page reads the video in a <video> element, which Chrome pauses in
background windows, so the window is brought to the front for the upload.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

URL = "https://channels.weixin.qq.com/platform/post/create"


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    if not 6 <= len(meta["short_title"]) <= 16:
        sys.exit("short_title must be 6-16 characters")
    done = tr.already_posted("wechat", video, meta["short_title"])
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']}; --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    def snap(name):
        if shots:
            tr.shot(tab, os.path.join(shots, f"wx_{name}.png"))

    def fail(step):
        snap(step)
        sys.exit("stuck at: " + step)

    if tab is None:
        tab = tr.job("open", url=URL)["tabId"]
        tr.front(tab)
    else:
        tr.cdp(tab, "Page.navigate", {"url": URL})
        tr.front(tab)
    zone = tr.deep("return dq('*').find(e=>e.offsetParent && e.childElementCount<6 &&"
                   " /支持上传/.test(e.innerText||'') && (e.innerText||'').length<80)")
    if not tr.wait_for(tab, f"!!{zone}", 60):
        fail("no_upload_zone")
    tr.front(tab, force=True)  # its <video> preview stalls in the background
    tr.choose_file(tab, zone, [video])
    busy = tr.deep("return dq('*').some(e=>e.offsetParent && e.childElementCount==0 &&"
                   " /正在处理文件|上传中|取消上传|^\\d+%$/.test((e.innerText||'').trim()))")
    started = tr.wait_for(tab, tr.deep("return dq('*').some(e=>e.offsetParent && /封面预览/.test(e.innerText||'')"
                                       " && e.childElementCount==0)"), 120, 2)
    end = time.time() + 300
    while started and tr.evaluate(tab, busy):
        if time.time() > end:
            fail("upload")
        tr.front(tab, force=True)  # it stalls whenever the window drops to the back
        time.sleep(3)
    if not started:
        fail("upload")

    body = meta["body"][:-1] + [meta["body"][-1] + " "]
    got = tr.fill_lines(tab, tr.deep("return dq('.input-editor')[0]"), body, clear=False)
    if meta["body"][0][:10] not in got:
        fail("body")
    tr.key(tab, "Escape")
    title = tr.fill_lines(tab, tr.deep("return dq('input[placeholder*=短标题]')[0]"), [meta["short_title"]])
    if title != meta["short_title"]:
        fail("short_title")

    # Location: open the picker (its arrow) and pick 不显示位置; retried, the list animates in.
    where = meta.get("prefilled_location")
    if not where:
        print("warning: no prefilled_location in META: the location is left as the page set it", file=sys.stderr)
    home = tr.deep("return dq('*').some(e=>e.offsetParent && e.childElementCount==0 &&"
                   f" (e.innerText||'').includes({json.dumps(where)}))") if where else "false"
    for _ in range(4):
        if not tr.evaluate(tab, home):
            break
        hide = tr.deep("return dq('*').filter(e=>e.offsetParent && e.childElementCount==0 &&"
                       " (e.innerText||'').trim()=='不显示位置').pop()")
        if not tr.evaluate(tab, f"!!{hide}"):
            field = tr.deep("return dq('*').find(e=>e.offsetParent && e.childElementCount==0 &&"
                            " (e.innerText||'').trim()=='位置')")
            y = tr.evaluate(tab, f"(()=>{{const r=({field}).getBoundingClientRect(); return r.y + r.height / 2}})()")
            tr.click_at(tab, 930, y)
            time.sleep(2)
        tr.tap(tab, hide, 1.5)
    if tr.evaluate(tab, home):
        fail("location_not_hidden")
    if meta.get("original"):
        # 声明原创 opens a 原创权益 dialog: agree to the terms, then its 声明原创 button.
        box = tr.deep("return dq('*').filter(e=>e.offsetParent && /声明后，作品将展示原创标记/.test(e.innerText||'')"
                      " && e.innerText.length<60).pop()")
        if not tr.evaluate(tab, f"!!{box}"):
            fail("no_original_option")
        tr.click(tab, box)
        time.sleep(2)
        agree = tr.deep("return dq('*').filter(e=>e.offsetParent && /我已阅读并同意/.test(e.innerText||'')"
                        " && e.innerText.length<80).pop()")
        if tr.evaluate(tab, f"!!{agree}"):
            ax, ay = tr.evaluate(tab, f"(()=>{{const r=({agree}).getBoundingClientRect(); return [r.x + 8, r.y + 10]}})()")
            tr.click_at(tab, ax, ay)  # the checkbox sits at the start of the line
            time.sleep(1)
            tr.tap(tab, tr.deep("return dq('button').filter(b=>b.offsetParent && b.innerText.trim()=='声明原创').pop()"), 2)
        ticked = tr.deep("return dq('*').some(e=>e.offsetParent && /声明后，作品将展示原创标记/.test(e.innerText||'')"
                         " && (e.querySelector('.weui-desktop-icon-checkbox-checked, :checked, [class*=checked]')"
                         " || (e.previousElementSibling||{}).className?.includes?.('checked')))")
        snap("original")
    snap("filled")
    if draft:
        print(f"draft (tab {tab})")
        return
    tr.click(tab, tr.deep("return dq('button').find(b=>b.offsetParent && b.innerText.trim()=='发表')"))
    if not tr.wait_for(tab, tr.deep("return dq('*').some(e=>e.offsetParent && (e.innerText||'').trim()=='已发表')")
                       + " || location.href.includes('/post/list')", 60, 1):
        fail("publish")
    snap("published")
    tr.record_post("wechat", video, meta["short_title"], "published")
    tr.detach(tab)
    print("published")


if __name__ == "__main__":
    main()
