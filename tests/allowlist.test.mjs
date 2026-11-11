// node --test: the extension's allow-list and CDP guard (extension/allowlist.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../extension/allowlist.js", import.meta.url), "utf8");
const { isAllowed, normalizeEntry, parseList, cdpRefusal } = await import("data:text/javascript," + encodeURIComponent(src));

test("domains and subdomains over https only", () => {
  const list = ["example.com"];
  assert.equal(isAllowed("https://example.com/x", list), true);
  assert.equal(isAllowed("https://www.example.com/", list), true);
  assert.equal(isAllowed("https://a.b.example.com/", list), true);
  assert.equal(isAllowed("https://EXAMPLE.com./", list), true);
  assert.equal(isAllowed("http://example.com/", list), false);
  assert.equal(isAllowed("https://notexample.com/", list), false);
  assert.equal(isAllowed("https://example.com.evil.net/", list), false);
  assert.equal(isAllowed("https://evil.net/?u=https://example.com", list), false);
  assert.equal(isAllowed("chrome://extensions", list), false);
  assert.equal(isAllowed("not a url", list), false);
  assert.equal(isAllowed("https://example.com/", []), false);
  assert.equal(isAllowed("https://example.com/", undefined), false);
});

test("a subdomain entry does not allow its parent", () => {
  assert.equal(isAllowed("https://studio.example.com/", ["studio.example.com"]), true);
  assert.equal(isAllowed("https://example.com/", ["studio.example.com"]), false);
});

test("entries are normalized", () => {
  assert.equal(normalizeEntry("https://www.Example.com/path?q=1"), "www.example.com");
  assert.equal(normalizeEntry("*.example.com"), "example.com");
  assert.equal(normalizeEntry(" example.com. "), "example.com");
  assert.equal(normalizeEntry("example.com:8443"), "example.com");
  assert.equal(normalizeEntry("localhost"), "");
  assert.equal(normalizeEntry("exa mple.com"), "");
  assert.equal(normalizeEntry("-bad.com"), "");
  assert.equal(normalizeEntry(""), "");
});

test("the options text is parsed", () => {
  const { domains, invalid } = parseList("# mine\nexample.com\nhttps://example.com/again\n\nfoo bar\nsite.org # comment\n");
  assert.deepEqual(domains, ["example.com", "site.org"]);
  assert.deepEqual(invalid, ["foo bar"]);
});

test("CDP commands that reach past the site are refused", () => {
  const list = ["example.com"];
  assert.equal(cdpRefusal("Runtime.evaluate", { expression: "1" }, list), "");
  assert.equal(cdpRefusal("Page.navigate", { url: "https://example.com/a" }, list), "");
  assert.match(cdpRefusal("Page.navigate", { url: "https://other.net/" }, list), /not an allowed site/);
  assert.match(cdpRefusal("Network.getAllCookies", {}, list), /not available/);
  assert.match(cdpRefusal("Storage.getCookies", {}, list), /not available/);
  assert.match(cdpRefusal("Target.createTarget", { url: "https://example.com" }, list), /not available/);
  assert.equal(cdpRefusal("Network.getCookies", {}, list), "");
  assert.equal(cdpRefusal("Network.getCookies", { urls: ["https://example.com/"] }, list), "");
  assert.match(cdpRefusal("Network.getCookies", { urls: ["https://bank.example.org/"] }, list), /isn't allowed/);
});
