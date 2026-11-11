#!/bin/sh
# Print the release version. Fails when tabrelay.py's __version__ and the extension manifest's
# "version" disagree, or (with an argument such as v0.1.0 or 0.1.0) when they differ from it.
set -e
cd "$(dirname "$0")/.."
python3 - "$@" <<'PY'
import json, re, sys
py = re.search(r'^__version__ = "([^"]+)"', open("tabrelay.py").read(), re.M).group(1)
ext = json.load(open("extension/manifest.json"))["version"]
if py != ext:
    sys.exit(f"version mismatch: tabrelay.py {py} != extension/manifest.json {ext}")
if len(sys.argv) > 1 and sys.argv[1].removeprefix("v") != py:
    sys.exit(f"version mismatch: tag {sys.argv[1]} != {py}")
print(py)
PY
