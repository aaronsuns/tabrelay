// The site allow-list: the extension only acts on https pages whose host is a listed domain or a
// subdomain of one. Kept free of chrome.* calls so it can be unit-tested with node.

// Turn what a user typed ("https://www.Example.com/path", "*.example.com", "example.com.") into a
// bare lower-case host name, or "" when it isn't one.
export function normalizeEntry(entry) {
  let s = String(entry || "").trim().toLowerCase();
  s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//, ""); // scheme
  s = s.replace(/[/?#].*$/, ""); // path, query, fragment
  s = s.replace(/^\*\./, ""); // "*.example.com" means the same as "example.com"
  s = s.replace(/:\d+$/, ""); // port
  s = s.replace(/\.+$/, ""); // trailing dot
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(s)) return "";
  if (s.split(".").some((part) => !part || part.startsWith("-") || part.endsWith("-"))) return "";
  return s;
}

// Parse the options page's text (one domain per line, # comments) into a clean, de-duplicated list
// plus the lines that were not domains.
export function parseList(text) {
  const domains = [];
  const invalid = [];
  for (const raw of String(text || "").split(/\r?\n/)) {
    const line = raw.replace(/#.*$/, "").trim();
    if (!line) continue;
    const d = normalizeEntry(line);
    if (!d) invalid.push(line);
    else if (!domains.includes(d)) domains.push(d);
  }
  return { domains, invalid };
}

export function isAllowed(url, list) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:") return false;
    const host = u.hostname.toLowerCase().replace(/\.$/, "");
    return (list || []).some((h) => host === h || host.endsWith("." + h));
  } catch (_) {
    return false;
  }
}

// CDP commands that would reach past the tab's own site: cookie access for every site, opening
// other targets, and navigating to a site that isn't allowed. Returns why a command is refused,
// or "" when it may run. (A guard rail: script inside an allowed page can still do whatever that
// page itself can do.)
const BLOCKED_METHODS = new Set([
  "Network.getAllCookies",
  "Network.clearBrowserCookies",
  "Network.clearBrowserCache",
  "Storage.getCookies",
  "Storage.setCookies",
  "Storage.clearCookies",
  "Storage.clearDataForOrigin",
  "Storage.clearDataForStorageKey",
  "Browser.close",
  "Browser.crash",
]);

export function cdpRefusal(method, params, list) {
  const m = String(method || "");
  if (BLOCKED_METHODS.has(m) || m.startsWith("Target.")) return "CDP method not available through Tabrelay: " + m;
  const p = params || {};
  if (m === "Page.navigate" && !isAllowed(p.url, list)) return "not an allowed site: " + p.url;
  if (m === "Network.getCookies" && Array.isArray(p.urls) && !p.urls.every((u) => isAllowed(u, list)))
    return "cookies of a site that isn't allowed";
  if ((m === "Network.setCookie" || m === "Network.deleteCookies") && p.url && !isAllowed(p.url, list))
    return "cookies of a site that isn't allowed";
  if (m === "Network.setCookies") return "CDP method not available through Tabrelay: " + m;
  return "";
}
