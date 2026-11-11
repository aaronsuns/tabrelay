import { parseList } from "./allowlist.js";

const box = document.getElementById("list");
const status = document.getElementById("status");
const invalid = document.getElementById("invalid");

async function load() {
  const { allow } = await chrome.storage.local.get({ allow: [] });
  box.value = (Array.isArray(allow) ? allow : []).join("\n");
}

document.getElementById("save").addEventListener("click", async () => {
  const { domains, invalid: bad } = parseList(box.value);
  await chrome.storage.local.set({ allow: domains });
  box.value = domains.join("\n");
  status.className = "ok";
  status.textContent = `Saved ${domains.length} site${domains.length === 1 ? "" : "s"}.`;
  invalid.textContent = bad.length ? "Ignored (not a domain): " + bad.join(", ") : "";
});

load();
