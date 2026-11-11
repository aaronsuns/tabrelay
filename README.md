# Tabrelay

**Drive your real, logged-in Chrome from the command line, from scripts and from AI agents.**

Tabrelay is a small Chrome extension plus a single-file Python command. The command sends jobs
(open a page, run JavaScript, click, type, upload a file, take a screenshot) to the extension
over `127.0.0.1`, and the extension carries them out with the Chrome DevTools Protocol in the
Chrome you already use: your profile, your cookies, your logins and your 2FA.

```
tabrelay (Python) ──127.0.0.1:47833──▶ Tabrelay extension (Chrome) ──CDP──▶ the page
```

- **Your real browser.** No separate automation browser to log in to, no copied cookies, no
  "Chrome is being controlled by automated test software" profile.
- **Doesn't steal your screen.** Jobs run in background windows and tabs; pages are told they
  have focus (focus emulation), so uploads and lazy pages keep working while you keep typing
  elsewhere.
- **Several Chrome profiles.** Load the extension in each profile; every job goes to exactly one
  of them.
- **Fenced in.** The extension only touches the sites on an allow-list that you edit in the
  extension's own options page, and only obeys jobs carrying a local secret token.
- **Small.** Python 3.10+ standard library only, no build step, no npm. About 1,100 lines
  without the site scripts.

Project page: [tabrelay.zexa.se](https://tabrelay.zexa.se) · by [Aaron Sun](https://github.com/aaronsuns) · MIT licence

> Tabrelay is for automating **your own** browser and accounts. Read the
> [Disclaimer](#disclaimer) before you use the site scripts.

## Contents

- [Why not Playwright, Puppeteer or Selenium?](#why-not-playwright-puppeteer-or-selenium)
- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Command reference](#command-reference)
- [Python API: writing your own site script](#python-api-writing-your-own-site-script)
- [Included site scripts](#included-site-scripts)
- [Keeping logins alive](#keeping-logins-alive)
- [macOS notes](#macos-notes)
- [Security](#security)
- [FAQ](#faq)
- [Development and releasing](#development)
- [Disclaimer](#disclaimer)

## Why not Playwright, Puppeteer or Selenium?

Those drive a **separate** browser that the tool starts (or one started with
`--remote-debugging-port`). That is the right choice for tests and for anything that runs on a
server. For your own day-to-day accounts it has costs: you log in again in that browser, 2FA and
"new device" checks get in the way, some sites treat automation browsers with suspicion, and a
debugging port on your everyday browser gives *every* local program full control of *every*
site.

Tabrelay goes the other way: it runs inside the browser you already use, through the extension
API `chrome.debugger`, only on sites you allowed, and only for callers that hold the token. It
does less than Playwright (no auto-waiting locators, no browser management, Chrome/Chromium
only, and a page can tell a debugger is attached) but needs nothing besides Chrome and Python.

## Install

Tabrelay is **not on the Chrome Web Store**; you load it as an unpacked extension.

1. Get the code, either a release or a git checkout:
   - **Release:** download `tabrelay-VERSION.tar.gz` from the
     [latest release](https://github.com/aaronsuns/tabrelay/releases/latest) and unpack it:
     ```sh
     tar -xzf tabrelay-0.1.0.tar.gz
     cd tabrelay-0.1.0
     ```
   - **Git:**
     ```sh
     git clone https://github.com/aaronsuns/tabrelay.git
     cd tabrelay
     ```
2. Run `./bin/tabrelay config` once. It creates `extension/token.json` (the local secret the
   extension checks; git ignores it) and shows the paths in use.
3. In Chrome open `chrome://extensions`, turn on **Developer mode** (top right), click
   **Load unpacked** and pick the `extension/` folder inside that folder. Load this one rather
   than a copy elsewhere: the command and the extension share `extension/token.json`. (Each
   release also has `tabrelay-extension-VERSION.zip`, the extension folder on its own; if you
   load that, copy your `extension/token.json` into it first.)
4. The **Tabrelay: allowed sites** page opens. Add the domains your scripts need (one per line,
   e.g. `example.com`) and **Save**. You can come back to it any time:
   `chrome://extensions` → Tabrelay → **Details** → **Extension options**.
5. Put the command on your `PATH` (optional):
   ```sh
   ln -s "$PWD/bin/tabrelay" ~/.local/bin/tabrelay
   ```

Requirements: Chrome or another Chromium browser with extension and `chrome.debugger` support,
Python 3.10 or newer. macOS and Linux are what it is used on; the core has no OS-specific code
(Windows should work but is untested). The macOS extras are described under
[macOS notes](#macos-notes).

## Quick start

```sh
tabrelay ping                     # starts the local server if needed, waits for the extension
# {"ok": true, "version": "0.1.0", "profile": "you@example.com", "sites": 1}

TAB=$(tabrelay open https://example.com/)          # a new background window; prints the tab id
tabrelay eval "$TAB" 'document.title'              # "Example Domain"
tabrelay click "$TAB" 'document.querySelector("a")'
tabrelay shot "$TAB" /tmp/example.png
tabrelay close "$TAB"
```

The first command starts `tabrelay serve` in the background. The extension checks in within 30
seconds (click its toolbar icon to make it connect right away).

While Tabrelay is working on a tab, Chrome shows a bar saying that **"Tabrelay" started
debugging this browser**. That is Chrome being honest about the `debugger` permission; leave it
(clicking Cancel detaches the tab). `tabrelay detach TAB` removes it when you are done.

## Configuration

Optional file `~/.config/tabrelay/config.json` (or `$XDG_CONFIG_HOME/tabrelay/config.json`, or
any path in `TABRELAY_CONFIG`). See [`config.example.json`](config.example.json):

```json
{
  "profile": "you@example.com",
  "keepalive": {
    "github": {"url": "https://github.com/notifications", "every": 1440,
               "marker": "Notifications", "login": "https://github.com/login"}
  }
}
```

| Setting | What it does |
|---|---|
| `profile` | The Chrome profile jobs go to: the Google account email that profile is signed in to. Empty or missing: whichever profile's extension asks first. |
| `keepalive` | Sites for [keepalive.py](#keeping-logins-alive). |

Environment variables override the file:

| Variable | Meaning |
|---|---|
| `TABRELAY_PROFILE` | Profile for this command, e.g. `TABRELAY_PROFILE=work@example.com tabrelay tabs`. Works for every script. |
| `TABRELAY_CONFIG` | Path of the config file. |
| `TABRELAY_DATA_DIR` | Where logs and state go (default `~/.local/share/tabrelay`, or `$XDG_DATA_HOME/tabrelay`). |
| `TABRELAY_FRONT=1` | Let scripts raise the window to the front (only for sites that stall in the background). |

**The allow-list is not in the config file on purpose.** It lives in the extension
(`chrome.storage.local` of each profile) and only the extension's options page can change it.
See [Security](#security).

### Several Chrome profiles

Load the same `extension/` folder in each profile (and allow sites in each one's options page).
Each copy reports the Google account its profile is signed in to, and the server keeps one job
queue per account. `tabrelay profiles` lists the copies that are connected. Pick one with
`profile` in the config or `TABRELAY_PROFILE`. A profile that isn't signed in to Chrome reports
no email; leave `profile` empty to reach it. With several profiles connected and no `profile`
set, a job goes to whichever one asks first, so set one.

## Command reference

| Command | What it does |
|---|---|
| `tabrelay serve` | Run the local server in the foreground (other commands start it when it is missing; its log is `serve.log` in the data dir). |
| `tabrelay ping` | Check the extension answers; prints its version, profile and number of allowed sites. |
| `tabrelay profiles` | Chrome profiles whose extension copy has checked in during the last 90 s. |
| `tabrelay tabs` | Open tabs on allowed sites (id, url, title). |
| `tabrelay open URL` | Open URL in a new, unfocused window; prints the tab id. |
| `tabrelay eval TAB JS` | Evaluate JS in the page (promises are awaited); prints the result as JSON. |
| `tabrelay click TAB JS` | JS evaluates to an element; scrolls it into view and sends a real mouse click to its centre. |
| `tabrelay type TAB TEXT` | Type TEXT into the focused element. |
| `tabrelay key TAB KEY` | Press a key: `Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, arrow keys. |
| `tabrelay file TAB JS PATH...` | JS evaluates to an `<input type=file>`; sets its files. |
| `tabrelay shot TAB FILE.png` | Screenshot of the tab. |
| `tabrelay front TAB` | Bring the tab's window to the front (avoid; see `front()` below). |
| `tabrelay close TAB` | Close the tab (accepting any "Leave site?" dialog). |
| `tabrelay detach TAB` | Stop debugging the tab (Chrome's info bar goes away). |
| `tabrelay reload` | Reload the extension from disk after you edited it. |
| `tabrelay reload-ext NAME\|ID` | macOS: reload *another* unpacked extension, e.g. one you are developing ([details](#macos-notes)). |
| `tabrelay log` | The posting log written by the site scripts (`posted.jsonl`). |
| `tabrelay config` | Paths, profile and port in use; creates the token if it doesn't exist yet. |

Every job has a timeout (120 s by default). Errors from the page or the extension are printed and
the command exits non-zero.

## Python API: writing your own site script

`tabrelay.py` is also a module. Put it on `sys.path` (the scripts in `sites/` add the repo root)
and import it:

```python
#!/usr/bin/env python3
"""Print the titles of the first few stories on a news site."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import tabrelay as tr

tab = tr.job("open", url="https://news.ycombinator.com/")["tabId"]   # allow ycombinator.com first
try:
    tr.front(tab)                                   # focus emulation: works in the background
    if not tr.wait_for(tab, "document.querySelectorAll('.titleline a').length > 0", 30):
        sys.exit("page did not load")
    for title in tr.evaluate(tab, "[...document.querySelectorAll('.titleline > a')].slice(0, 5).map(a => a.innerText)"):
        print(title)
finally:
    tr.job("close", tabId=tab)
```

The building blocks:

| Function | Use |
|---|---|
| `job(kind, **fields)` | Raw job: `open` (`url`, `background=True` for an inactive tab in an existing window), `tabs`, `close`, `detach`, `ping`, `events`, `cdp`. |
| `cdp(tab, method, params)` | Any [DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/) command on the tab (a few that reach beyond the tab's site are refused). |
| `evaluate(tab, js)` | Run JS, await promises, return the value. |
| `wait_for(tab, js, seconds, every)` | Poll until JS is truthy; returns the value or `None`. |
| `click(tab, js)` / `click_at(tab, x, y)` / `tap(tab, js)` | Real mouse events (tap hovers first, for hover menus). |
| `type_text(tab, text)` / `key(tab, name)` / `fill_lines(tab, js, lines)` | Typing; `fill_lines` handles rich editors (contenteditable, Draft.js, ProseMirror). |
| `set_files(tab, js, paths)` / `choose_file(tab, click_js, paths)` | File uploads; `choose_file` intercepts the page's own file chooser. |
| `by_text(text)` / `leaf(text)` / `deep(js)` | JS helpers: element by its text; `deep` gives you `dq(selector)` which also searches open shadow roots. |
| `shot(tab, path)` | Screenshot. |
| `front(tab)` | Focus emulation and an active lifecycle state, so background tabs keep working. `front(tab, force=True)` really raises the window. |
| `already_posted(...)` / `record_post(...)` | The posting log: skip things that already went out. |
| `notify(title, text)` | Desktop notification (macOS, or `notify-send` on Linux). |

Tips from the included scripts:

- Prefer `wait_for` over `sleep`; most pages render after load.
- Give a script `--draft` (fill everything, don't submit) and `--shots DIR` (screenshot each
  step) from the start. You'll need both when the site changes.
- When a click "does nothing", the page may still be hydrating: retry, or click by coordinates
  with `click_at`.
- After you finish with a tab, `close` it or `detach` it so the debugging bar goes away.

## Included site scripts

`sites/` holds scripts for sites that offer no usable posting API to individuals. They are
examples as much as tools: sites change their pages often, so expect to fix selectors. Read the
[Disclaimer](#disclaimer) first, and add each site's domain to the allow-list.

| Script | What it does |
|---|---|
| `post_youtube.py VIDEO META.json` | Upload through YouTube Studio (`{"title", "description", "kids"}`). |
| `post_tiktok.py VIDEO META.json` | TikTok Studio upload (`{"caption": [lines]}`). |
| `post_instagram.py VIDEO META.json` | Instagram Reel (`{"text": [lines]}`; `--handle NAME` to print the reel's link). |
| `post_facebook.py VIDEO META.json` | Facebook Reel on your profile (`{"text": [lines], "audience": "Public"}`). |
| `post_x.py VIDEO META.json` | X post with a video (`{"text": [lines]}`, 280 characters). |
| `post_threads.py MEDIA META.json` | Threads post with a video or image (`{"text": [lines]}`, 500 characters). |
| `post_xhs.py VIDEO META.json` | Xiaohongshu video note (`{"title" (≤ 20 chars), "body": [lines]}`). |
| `post_douyin.py VIDEO META.json` | Douyin (`{"title" (≤ 30 chars), "body": [lines]}`). |
| `post_wechat.py VIDEO META.json` | WeChat Channels (`{"short_title", "body", "prefilled_location"?}`). |
| `post_plan.py PLAN.json` | A batch of the above, one after the other; finished posts are skipped on a re-run. |
| `post_discord.py TEXT_FILE /channels/G/C ...` | A text message to Discord channels; `--survey GUILD` lists a server's channels. |
| `join_discord.py GUILD_ID ...` | Join Discord servers and walk their onboarding; captchas are left for you. |
| `post_fbgroup.py TEXT_FILE GROUP_ID ...` | Post to Facebook groups you are in; prints each group's rules first. |
| `join_fbgroup.py GROUP_ID ... --answer TEXT` | Join Facebook groups, answering membership questions with your text. |
| `promo_queue.py QUEUE.json ...` | A slow Facebook group queue: read rules, join, post at most 1 group per run and 6 per day. |

Every posting script takes `--draft`, `--again` (post even if the posting log says it's done),
`--shots DIR` and `--tab TAB` (reuse an open tab); details are in each script's docstring
(`head -30 sites/post_x.py`).

**Rules first.** The group scripts are built to behave like a careful person, and you should
keep it that way:

- `post_fbgroup.py` prints each group's rules before posting. `promo_queue.py` reads them before
  joining and **skips groups whose rules ban self-promotion**, uses a link-free text where links
  are banned (or skips the group), posts at most 1 group per run, 6 per day, between 09 and 22,
  and **stops completely when Facebook says to slow down** until you clear it by hand.
- `join_fbgroup.py` has no default answer: you write what goes into membership questions.
- `post_discord.py --survey` exists so you read each server's rules and channel topics first.
  Never post in channels meant to catch bots ("honeypot", "do not type here").

On macOS, `scripts/install-promo-queue.sh QUEUE.json` runs the queue every 2 hours with launchd
(`--uninstall` removes it).

## Keeping logins alive

Some sites end a web session after a few hours without a visit. `keepalive.py` visits each site
from the `keepalive` section of your config in an **inactive background tab**, waits for the page
to refresh its session, checks a marker that only the logged-in page shows, and closes the tab.
A lost login raises a desktop notification with the login URL.

```sh
./keepalive.py --only github     # test one site now
./keepalive.py --status          # last visit and state per site
scripts/install-keepalive.sh     # macOS: run it every 30 minutes (launchd label tabrelay.keepalive)
```

On Linux, a cron line does the same: `*/30 * * * * /path/to/tabrelay/keepalive.py >> ~/.local/share/tabrelay/keepalive.log 2>&1`.
It never starts Chrome; if Chrome isn't running the run is skipped.

## macOS notes

- **Background windows.** macOS Chrome throttles windows that are hidden or behind others.
  `front(tab)` keeps a page working without raising it. A few sites still stall (a `<video>`
  preview that never loads); `TABRELAY_FRONT=1` or `front(tab, force=True)` raises the window as
  a last resort.
- **`tabrelay reload-ext NAME|ID`** reloads another unpacked extension (say, one you are
  developing) by opening `chrome://extensions` through AppleScript. It needs Chrome's
  **View → Developer → Allow JavaScript from Apple Events**. (Turning an extension off and on
  does not re-read an unpacked extension's files; this does.)
- **`scripts/chrome-js.sh URLPART 'JS'`** runs JavaScript in the first tab of *any* profile whose
  URL contains URLPART, through Apple Events, without the extension. Handy for profiles where
  Tabrelay isn't installed. It needs the same Apple Events setting in that profile, is not
  limited by the allow-list, and does not await promises.
- **launchd installers** in `scripts/` write a plist to `~/Library/LaunchAgents/` with the
  labels `tabrelay.keepalive` and `tabrelay.promo-queue`, logging to the data dir. Re-run them
  after moving the checkout; `--uninstall` removes them.

## Security

Tabrelay gives a program on your computer control over pages where you are logged in. Know
what protects what:

- **The token.** `extension/token.json` is a random secret created on first use with mode 600
  and ignored by git. The server only accepts jobs (`POST /job`) that send it in a header, and the
  extension only runs jobs that carry it. So another user account on the machine can't send jobs,
  and a program that grabs the port while Tabrelay isn't running can't feed the extension jobs.
  Any program running **as you** can read the file, so the token does not protect you from
  software you already run; it is not a sandbox.
- **Localhost only.** The server binds to `127.0.0.1:47833`, never to other interfaces. It
  refuses requests whose `Host` isn't `127.0.0.1`/`localhost` (DNS rebinding) and requests with
  a web page `Origin`, so websites you visit can't drive it. **Never expose or forward this
  port** (no `ssh -R`, no tunnels, no `0.0.0.0` proxies).
- **The allow-list lives in the extension.** The extension acts only on `https` pages whose host
  is on the list (or a subdomain of a listed domain). It checks the tab's current URL on every
  command, refuses to `open` or navigate to other sites, and refuses a few DevTools commands that
  reach beyond the tab (cookies of all sites, other targets). The list is stored in the
  extension's own storage and **only its options page can change it**; nothing the command line
  sends can widen it. Keep it as short as your scripts need. It is a guard rail, not a sandbox:
  JavaScript running in an allowed page can do whatever that page can do, including navigating
  away (later commands on that tab are then refused).
- **The `debugger` permission** is powerful: on a tab it can read and change everything,
  including form fields and network traffic. Chrome shows the "started debugging this browser"
  bar whenever it is in use. The extension also asks for `tabs` (find and open tabs),
  `identity` + `identity.email` (only to learn which Google account the profile is signed in to,
  for routing between profiles), `storage` (the allow-list) and `alarms` (to reconnect).
- **Your agents.** If you let an AI agent run `tabrelay`, it acts as you on the allowed sites.
  Allow only the sites the task needs, prefer `--draft`, and review what it posts.
- **No telemetry.** The extension talks to `127.0.0.1:47833` and to the pages it drives,
  nothing else.

Found a security problem? Please open a GitHub issue without exploit details and ask for a
private contact, or use GitHub's private vulnerability reporting.

## FAQ

**Does it work with Brave, Edge, Arc, Chromium?**
Probably, if the browser supports unpacked MV3 extensions and `chrome.debugger`. Profile routing
needs `chrome.identity.getProfileUserInfo`, which only reports an email where the browser has
Google sign-in; elsewhere leave `profile` empty. Only Chrome is regularly used.

**Firefox or Safari?** No: they don't have `chrome.debugger`.

**Why isn't it on the Chrome Web Store?** An extension that can debug pages is exactly what a
store should be wary of, and loading it unpacked means you run the code you can read.

**"not on the allow-list"?** Add the domain on the options page (`chrome://extensions` →
Tabrelay → Details → Extension options). `example.com` covers its subdomains too.

**`tabrelay ping` times out.** Is Chrome running with the extension enabled in that profile?
Click the Tabrelay toolbar icon to reconnect immediately. `tabrelay profiles` shows which
profiles are connected; a `TABRELAY_PROFILE`/`profile` that doesn't match any of them waits
forever. If you moved the checkout, load the extension again from the new folder (the token is
read from the extension folder).

**Can it run headless or on a server?** That's not what it is for: use Playwright there.

**Will sites detect it?** A page can notice a debugger is attached, and every site has its own
rules on automation. See the [Disclaimer](#disclaimer).

**Can I use another port?** The port (47833) is written in both `tabrelay.py` and the extension's
`manifest.json`/`background.js`; change all three together.

**Is there a short alias?** Make your own, e.g. `alias trl=tabrelay`. (Not `tr`: that would
shadow the standard Unix `tr` command.)

## Development

```sh
scripts/check.sh      # versions agree, py_compile everything, node --check the extension, python and node unit tests
```

CI (`.github/workflows/ci.yml`) runs `scripts/check.sh` on Python 3.10 and 3.12 for every push
to `main` and every pull request.

The tests cover the pure parts: config loading, the server's job routing and request checks,
keepalive scheduling, the group queue's rule matching and state, and the extension's allow-list.
After editing the extension, `tabrelay reload` reloads it without a click.

### Releasing

The version lives in two places that must agree (`scripts/version.sh` checks it, and so does
CI): `__version__` in `tabrelay.py` and `"version"` in `extension/manifest.json`.

1. Bump both to the new version, e.g. `0.2.0`, and run `scripts/check.sh`.
2. Commit and push to `main`; wait for CI to go green.
3. Tag and push the tag:
   ```sh
   git tag -a v0.2.0 -m "Tabrelay 0.2.0"
   git push origin v0.2.0
   ```
4. The **Release** workflow (`.github/workflows/release.yml`) runs the checks, checks that the
   tag equals the version, builds `tabrelay-extension-0.2.0.zip` and `tabrelay-0.2.0.tar.gz`
   with `scripts/build-release.sh` (from tracked files only, so no `token.json`), and publishes
   a GitHub release with install notes. Watch it with `gh run watch`.
5. If it fails: fix on `main`, then move the tag (`git tag -d v0.2.0 && git push origin :v0.2.0`,
   re-tag, push again). A re-run on an existing release replaces its assets.

`scripts/build-release.sh` also works locally (output in `dist/`, ignored by git).

The project page [tabrelay.zexa.se](https://tabrelay.zexa.se) is `site/` (a static page served
by Cloudflare Workers): `cd site && npx wrangler@4 deploy`.

## Disclaimer

Tabrelay is provided as is, for automating **your own browser and your own accounts**. You are
responsible for following each site's terms of service, its automation and anti-spam rules, the
rules of every community you post in, and the law where you live. Don't use it for spam, mass
posting, fake engagement or accounts you don't control. Tabrelay is not affiliated with any of
the sites its scripts work with. Sites change: scripts can break, misbehave, or get an account
limited or banned. The full text is in [DISCLAIMER.md](DISCLAIMER.md).

## Licence

[MIT](LICENSE)
