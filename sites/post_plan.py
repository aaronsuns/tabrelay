#!/usr/bin/env python3
"""Post a batch: one plan file, many (platform, video, text) posts, run one after another.
Posts already in the posting log (tabrelay log) are skipped, so a plan can simply be re-run after a
failure.

  post_plan.py PLAN.json [--draft] [--only youtube,tiktok,...] [--shots DIR]

PLAN.json:
  {"videos": "/dir/with/the/mp4s",            (optional base for relative video paths)
   "posts": [
     {"platform": "youtube", "video": "clip_en.mp4", "title": "...", "description": "..."},
     {"platform": "tiktok",  "video": "clip_en.mp4", "caption": ["line", "line"]},
     {"platform": "xhs",     "video": "clip_zh.mp4", "title": "<= 20 chars", "body": ["line"]},
     {"platform": "facebook","video": "clip_en.mp4", "text": ["line", "line"]},
     {"platform": "x",       "video": "clip_en.mp4", "text": ["<= 280 chars in all"]},
     {"platform": "instagram","video": "clip_en.mp4", "text": ["line", "#tags"]},
     {"platform": "threads",  "video": "clip_en.mp4", "text": ["<= 500 chars, links clickable"]}
   ]}
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPT = {"youtube": "post_youtube.py", "tiktok": "post_tiktok.py", "xhs": "post_xhs.py",
          "facebook": "post_facebook.py", "douyin": "post_douyin.py", "wechat": "post_wechat.py",
          "x": "post_x.py", "instagram": "post_instagram.py", "threads": "post_threads.py"}
START = {"youtube": "https://studio.youtube.com", "tiktok": "https://www.tiktok.com/tiktokstudio",
         "xhs": "https://creator.xiaohongshu.com", "facebook": "https://www.facebook.com",
         "douyin": "https://creator.douyin.com", "wechat": "https://channels.weixin.qq.com/platform",
         "x": "https://x.com/home", "instagram": "https://www.instagram.com/",
         "threads": "https://www.threads.com/"}


def main():
    a = sys.argv[1:]
    plan = json.load(open(a[0]))
    base = os.path.expanduser(plan.get("videos") or os.path.dirname(os.path.abspath(a[0])))
    only = set(a[a.index("--only") + 1].split(",")) if "--only" in a else None
    extra = [x for x in ("--draft",) if x in a]
    if "--shots" in a:
        extra += ["--shots", a[a.index("--shots") + 1]]
    failed = []
    tabs = {}  # one window per platform, reused: parallel background uploads are unreliable
    for i, post in enumerate(plan["posts"]):
        platform = post["platform"]
        if only and platform not in only:
            continue
        video = os.path.join(base, os.path.expanduser(post["video"]))
        meta = {k: v for k, v in post.items() if k not in ("platform", "video")}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"== {i + 1}/{len(plan['posts'])} {platform} {post['video']}", flush=True)
        if platform not in tabs:
            tabs[platform] = tr.job("open", url=START[platform])["tabId"]
        r = subprocess.run([sys.executable, os.path.join(HERE, SCRIPT[platform]), video, f.name,
                            "--tab", str(tabs[platform])] + extra)
        os.unlink(f.name)
        if r.returncode != 0:
            failed.append(f"{platform} {post['video']}")
    # Close the windows this plan opened (leftover tabs are hard to tell from ones in use).
    # A draft run leaves them open for a look.
    if "--draft" not in a:
        for tab in tabs.values():
            try:
                tr.job("close", tabId=int(tab))
            except RuntimeError:
                pass
    if failed:
        sys.exit("failed (re-run the plan to retry just these): " + ", ".join(failed))


if __name__ == "__main__":
    main()
