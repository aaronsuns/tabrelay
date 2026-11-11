#!/usr/bin/env python3
"""Join Facebook groups with your logged-in account, answering membership questions.

  join_fbgroup.py GROUP_ID [GROUP_ID ...] --answer "text" [--shots DIR]

For each group: open it, click "Join group". If Facebook shows membership questions, every text
box gets the --answer text (required: write an honest one-liner about who you are and why you
want to join; it goes to every question), every "agree to the rules" checkbox is ticked (so read
the rules first: ticking means you agree to them), and the form is submitted.
Prints: joined / requested (pending admin approval) / already member / CHECK (look at the shot).
Read the group's rules before posting anyway (post_fbgroup.py prints them).
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr  # noqa: E402


def center(tab, js):
    return tr.evaluate(tab, "(()=>{const e=" + js + ";if(!e)return null;e.scrollIntoView({block:'center'});"
                            "const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")


def main():
    a = sys.argv[1:]
    if "--answer" not in a or a.index("--answer") + 1 >= len(a) or not a[a.index("--answer") + 1].strip():
        sys.exit(__doc__)
    answer = a[a.index("--answer") + 1]
    shots = a[a.index("--shots") + 1] if "--shots" in a else tempfile.gettempdir()
    skip = {answer, shots}
    groups = [x for x in a if not x.startswith("--") and x not in skip]
    if not groups:
        sys.exit(__doc__)
    for g in groups:
        tab = tr.job("open", url=f"https://www.facebook.com/groups/{g}/", background=True)["tabId"]
        try:
            time.sleep(9)
            tr.front(tab)
            name = tr.evaluate(tab, "(document.querySelector('[role=main] h1')||{}).innerText||''")[:50]
            btn = "[...document.querySelectorAll('[role=main] [role=button]')].find(b=>(b.innerText||'').trim()=='Join group')"
            if not tr.evaluate(tab, "!!" + btn):
                state = tr.evaluate(tab, "document.querySelector('[role=main]').innerText.slice(0,800)")
                print(f"{g} {name}: " + ("requested (pending)" if "Cancel request" in state else "already member"))
                continue
            tr.click_at(tab, *center(tab, btn))
            # The button spins for a while; wait until it changes or a questions dialog appears.
            tr.wait_for(tab, "!(" + btn + ") || [...document.querySelectorAll('[role=dialog]')].some(d=>/question|Answer|rules|Submit/i.test(d.innerText))", 25, 2)
            time.sleep(2)
            dlg = "[...document.querySelectorAll('[role=dialog]')].find(d=>/question|Answer|rules|Submit/i.test(d.innerText))"
            if tr.evaluate(tab, "!!(" + dlg + ")"):
                n = tr.evaluate(tab, "[...(" + dlg + ").querySelectorAll('textarea,[contenteditable=true],input[type=text]')].length")
                for i in range(n):
                    xy = center(tab, "[...(" + dlg + ").querySelectorAll('textarea,[contenteditable=true],input[type=text]')][" + str(i) + "]")
                    if xy:
                        tr.click_at(tab, *xy)
                        tr.cdp(tab, "Input.insertText", {"text": answer})
                        time.sleep(0.5)
                # agree-to-rules checkboxes / single-choice answers: tick unticked checkboxes
                for _ in range(6):
                    xy = center(tab, "[...(" + dlg + ").querySelectorAll('[role=checkbox],input[type=checkbox]')].find(c=>c.getAttribute('aria-checked')!=='true'&&!c.checked)")
                    if not xy:
                        break
                    tr.click_at(tab, *xy)
                    time.sleep(0.5)
                tr.shot(tab, os.path.join(shots, f"join_{g}.png"))
                sub = "[...(" + dlg + ").querySelectorAll('[role=button]')].find(b=>/^(Submit|Done|Send)$/.test((b.innerText||b.getAttribute('aria-label')||'').trim()))"
                xy = center(tab, sub)
                if not xy:
                    print(f"{g} {name}: CHECK form not submitted, see join_{g}.png")
                    continue
                tr.click_at(tab, *xy)
                time.sleep(5)
            state = tr.evaluate(tab, "document.querySelector('[role=main]').innerText.slice(0,800)")
            if "Cancel request" in state or "pending" in state.lower():
                print(f"{g} {name}: requested (pending admin approval)")
            elif "Joined" in state:
                print(f"{g} {name}: joined")
            else:
                tr.shot(tab, os.path.join(shots, f"join_{g}.png"))
                print(f"{g} {name}: CHECK, see join_{g}.png")
        finally:
            tr.job("close", tabId=int(tab))


if __name__ == "__main__":
    main()
