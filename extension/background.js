// Tabrelay: picks up jobs from the local `tabrelay` server (127.0.0.1:47833) and runs them in this
// logged-in browser through the Chrome DevTools Protocol (chrome.debugger), only on the sites in
// the allow-list (edited on the options page, kept in chrome.storage.local), and only for jobs
// carrying the token in token.json (written by `tabrelay`, never committed), so another local
// program can't drive the browser by posing as the server.
//
// Nothing a job can do changes the allow-list: only the options page writes it.
//
// Jobs: {kind:"ping"} | {kind:"open", url, background?} -> {tabId} | {kind:"tabs"}
//       {kind:"cdp", tabId, method, params} -> CDP result | {kind:"close", tabId}
//       {kind:"events", tabId, method?}  buffered CDP events since the last read
//       {kind:"detach", tabId}   stop debugging the tab (Chrome's info bar goes away)
//       {kind:"reload"}          reload the extension from disk (after an edit; no clicking)

import { cdpRefusal, isAllowed } from "./allowlist.js";

const BRIDGE = "http://127.0.0.1:47833";
const VERSION = chrome.runtime.getManifest().version;
// Shipped default: empty. Add your sites on the options page.
const DEFAULT_ALLOW = [];

let pumping = false;
let token = null;
const attached = new Set();

let allowList = null;
async function getAllowList() {
  if (allowList === null) {
    const got = await chrome.storage.local.get({ allow: DEFAULT_ALLOW });
    allowList = Array.isArray(got.allow) ? got.allow : [];
  }
  return allowList;
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.allow) allowList = Array.isArray(changes.allow.newValue) ? changes.allow.newValue : [];
});

async function allowed(url) {
  return isAllowed(url, await getAllowList());
}

function notAllowed(url) {
  return new Error(
    "not on the allow-list: " + url + " (add the domain on the Tabrelay options page: chrome://extensions > Tabrelay > Details > Extension options)",
  );
}

// The Google account this Chrome profile is signed in to: tabrelay routes each job to one profile.
let email = null;
async function profileEmail() {
  if (email === null) {
    try {
      email = (await chrome.identity.getProfileUserInfo({ accountStatus: "ANY" })).email || "";
    } catch (_) {
      email = "";
    }
  }
  return email;
}

async function getToken() {
  if (!token) token = (await (await fetch(chrome.runtime.getURL("token.json"))).json()).token;
  return token;
}

async function checkTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  const url = tab.pendingUrl || tab.url;
  if (!(await allowed(url))) throw notAllowed(url);
  return tab;
}

async function attach(tabId) {
  if (attached.has(tabId)) return;
  await chrome.debugger.attach({ tabId }, "1.3");
  attached.add(tabId);
}
chrome.debugger.onDetach.addListener((src) => attached.delete(src.tabId));

// CDP events (Page.fileChooserOpened, ...) kept per tab until a job reads them.
const events = new Map();
chrome.debugger.onEvent.addListener((src, method, params) => {
  // "Leave site?" when a tab we close has unsaved work: always leave (it would otherwise block
  // this job, and every job after it, until someone clicks).
  if (method === "Page.javascriptDialogOpening" && params.type === "beforeunload") {
    chrome.debugger.sendCommand({ tabId: src.tabId }, "Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
  }
  const list = events.get(src.tabId) || [];
  list.push({ method, params });
  if (list.length > 200) list.shift();
  events.set(src.tabId, list);
});

async function run(job) {
  switch (job.kind) {
    case "ping":
      return { ok: true, version: VERSION, profile: await profileEmail(), sites: (await getAllowList()).length };
    case "open": {
      if (!(await allowed(job.url))) throw notAllowed(job.url);
      if (job.background) {
        // An inactive tab in an existing window: no new window, no focus change.
        const wins = await chrome.windows.getAll({ windowTypes: ["normal"] });
        if (wins.length) {
          const tab = await chrome.tabs.create({ url: job.url, active: false, windowId: wins[0].id });
          return { tabId: tab.id, windowId: tab.windowId };
        }
      }
      const win = await chrome.windows.create({ url: job.url, focused: false, width: 1400, height: 1000 });
      return { tabId: win.tabs[0].id, windowId: win.id };
    }
    case "tabs": {
      const list = await getAllowList();
      const tabs = await chrome.tabs.query({});
      return { tabs: tabs.filter((t) => isAllowed(t.url || "", list)).map((t) => ({ id: t.id, url: t.url, title: t.title })) };
    }
    case "cdp": {
      const why = cdpRefusal(job.method, job.params, await getAllowList());
      if (why) throw new Error(why);
      await checkTab(job.tabId);
      await attach(job.tabId);
      return await chrome.debugger.sendCommand({ tabId: job.tabId }, job.method, job.params || {});
    }
    case "events": {
      // Read (and clear) the tab's buffered CDP events, optionally only one method.
      const list = events.get(job.tabId) || [];
      const pick = list.filter((e) => !job.method || e.method === job.method);
      events.set(job.tabId, list.filter((e) => job.method && e.method !== job.method));
      return { events: pick };
    }
    case "detach": {
      if (attached.has(job.tabId)) await chrome.debugger.detach({ tabId: job.tabId });
      attached.delete(job.tabId);
      return { ok: true };
    }
    case "reload":
      setTimeout(() => chrome.runtime.reload(), 500);
      return { ok: true, version: VERSION };
    case "close": {
      await checkTab(job.tabId);
      await attach(job.tabId);
      await chrome.debugger.sendCommand({ tabId: job.tabId }, "Page.enable", {});
      await Promise.race([chrome.tabs.remove(job.tabId), new Promise((r) => setTimeout(r, 10000))]);
      return { ok: true };
    }
  }
  throw new Error("unknown job " + job.kind);
}

function keepAlive() {
  return setInterval(() => chrome.runtime.getPlatformInfo(() => {}), 20000);
}

async function pump() {
  if (pumping) return;
  pumping = true;
  const timer = keepAlive();
  try {
    const want = await getToken();
    for (;;) {
      const r = await fetch(`${BRIDGE}/next?p=${encodeURIComponent(await profileEmail())}`, { cache: "no-store" });
      if (r.status === 204) continue;
      if (!r.ok) break;
      const job = await r.json();
      let result;
      if (job.token !== want) {
        result = { error: "bad token" };
      } else {
        try {
          result = { result: await run(job) };
        } catch (e) {
          result = { error: String(e && e.message ? e.message : e) };
        }
      }
      await fetch(`${BRIDGE}/result/${job.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      });
    }
  } catch (_) {
    // tabrelay isn't serving (or token.json doesn't exist yet); the alarm tries again.
  } finally {
    clearInterval(timer);
    pumping = false;
  }
}

chrome.alarms.create("pump", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => pump());
chrome.runtime.onStartup.addListener(() => pump());
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") chrome.runtime.openOptionsPage();
  pump();
});
chrome.action.onClicked.addListener(() => pump());
pump();
