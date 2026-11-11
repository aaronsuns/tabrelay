#!/usr/bin/env python3
"""Post a video to YouTube (Shorts when vertical and short) through YouTube Studio's upload
dialog in the logged-in Chrome, via Tabrelay.

  post_youtube.py VIDEO.mp4 META.json [--draft] [--again] [--shots DIR] [--tab TAB]

META.json: {"title": "...", "description": "line\\nline", "kids": false}
--draft     stop before publishing (the video stays private, the dialog open)
--shots DIR save a screenshot after each step
--tab TAB   use an open Studio tab (an upload dialog already open with this file goes on
            from Details)
Prints the video link.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

DQ = ('const dq=(sel,root=document)=>{const out=[];const walk=r=>{r.querySelectorAll(sel).forEach(e=>out.push(e));'
      'r.querySelectorAll("*").forEach(e=>{if(e.shadowRoot)walk(e.shadowRoot)})};walk(root);return out};')


class Studio:
    def __init__(self, tab, shots):
        self.tab = tab
        self.shots = shots
        self.n = 0

    def ev(self, js):
        return tr.evaluate(self.tab, "(()=>{" + DQ + js + "})()")

    def el(self, js):
        return "(()=>{" + DQ + js + "})()"

    def snap(self, name):
        if self.shots:
            self.n += 1
            tr.shot(self.tab, os.path.join(self.shots, f"yt_{self.n:02d}_{name}.png"))

    def wait(self, js, seconds=60):
        v = tr.wait_for(self.tab, "(()=>{" + DQ + js + "})()", seconds)
        if not v:
            self.snap("timeout")
            raise SystemExit("timed out waiting for: " + js)
        return v

    def fill(self, index, text):
        # Focus the contenteditable box, clear it, type line by line (Enter between lines).
        tr.click(self.tab, self.el(f"return dq('#textbox')[{index}]"))
        self.ev(f"const b=dq('#textbox')[{index}]; b.focus(); document.execCommand('selectAll'); return true")
        tr.key(self.tab, "Backspace")
        for i, line in enumerate(text.split("\n")):
            if i:
                tr.key(self.tab, "Enter")
            if line:
                tr.type_text(self.tab, line)
        return self.ev(f"return dq('#textbox')[{index}].innerText")

    def next(self):
        tr.click(self.tab, self.el("return dq('#next-button')[0]"))
        time.sleep(2)


def main():
    a = sys.argv[1:]
    video, meta = a[0], json.load(open(a[1]))
    draft = "--draft" in a
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    tab = int(a[a.index("--tab") + 1]) if "--tab" in a else None
    done = tr.already_posted("youtube", video, meta["title"])
    if done and "--again" not in a and not draft:
        print("skip: " + f"already posted {done['at']} ({done.get('result', '')}); --again to post anyway")
        sys.exit(0)
    if shots:
        os.makedirs(shots, exist_ok=True)

    if tab is None:
        tab = tr.job("open", url="https://studio.youtube.com")["tabId"]
        tr.front(tab)
    s = Studio(tab, shots)
    tr.front(tab)
    # A share dialog left open by the last upload.
    s.ev("const b=dq('ytcp-button, button').filter(b=>b.offsetParent && /^Close$/.test(b.innerText.trim()))[0]; if (b) b.click(); return true")
    time.sleep(1)
    if not s.ev("return dq('#textbox').some(e => e.offsetParent !== null)"):
        s.wait("return location.href.includes('studio.youtube.com/channel') && !!(document.querySelector('#upload-icon'))", 60)
        tr.click(tab, "document.querySelector('#upload-icon')")
        s.wait("return dq('input[type=file][name=Filedata]').length > 0", 30)
        tr.set_files(tab, s.el("return dq('input[type=file][name=Filedata]')[0]"), [video])
        s.wait("return dq('#textbox').length >= 2", 120)
        time.sleep(2)
    s.snap("uploaded")

    title = s.fill(0, meta["title"])
    desc = s.fill(1, meta["description"])
    if title.strip() != meta["title"].strip():
        raise SystemExit(f"title came out as {title!r}")
    s.ev("const r=dq('tp-yt-paper-radio-button[name=%s]')[0]; r.scrollIntoView({block:'center'}); return true"
         % ("VIDEO_MADE_FOR_KIDS_MFK" if meta.get("kids") else "VIDEO_MADE_FOR_KIDS_NOT_MFK"))
    tr.click(tab, s.el("return dq('tp-yt-paper-radio-button[name=%s]')[0]"
                       % ("VIDEO_MADE_FOR_KIDS_MFK" if meta.get("kids") else "VIDEO_MADE_FOR_KIDS_NOT_MFK")))
    time.sleep(1)
    s.snap("details")

    for step in ("elements", "checks", "visibility"):
        s.next()
        s.snap(step)
    s.wait("return dq('tp-yt-paper-radio-button[name=PUBLIC]').length > 0", 30)
    if draft:
        print(f"draft (tab {tab}, dialog open on Visibility)")
        return
    tr.click(tab, s.el("return dq('tp-yt-paper-radio-button[name=PUBLIC]')[0]"))
    time.sleep(1)
    s.snap("public")
    tr.click(tab, s.el("return dq('#done-button')[0]"))
    s.wait("return dq('ytcp-video-share-dialog, ytcp-prechecks-warning-dialog').some(e => e.offsetParent !== null)"
           " || dq('*').some(e => e.childElementCount === 0 && /^(Video published|Video processing)$/.test((e.innerText || '').trim()))", 120)
    time.sleep(2)
    s.snap("done")
    link = s.ev("const a=dq('a').find(a=>/youtube\\.com\\/(shorts|watch)/.test(a.href)); return a ? a.href.split('?')[0] : '(processing: see Studio > Content)'")
    s.ev("const b=dq('ytcp-button, button').filter(b=>b.offsetParent && /^Close$/.test(b.innerText.trim()))[0]; if (b) b.click(); return !!b")
    tr.record_post("youtube", video, meta["title"], link)
    tr.detach(tab)
    print(link)


if __name__ == "__main__":
    main()
