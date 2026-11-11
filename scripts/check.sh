#!/bin/sh
# Run every cheap check: versions agree, Python syntax, extension JS syntax, unit tests (Python and node).
set -e
cd "$(dirname "$0")/.."
echo "== version"
scripts/version.sh
echo "== python -m py_compile"
python3 - <<'PY'
import glob, py_compile, sys
files = ["tabrelay.py", "keepalive.py"] + sorted(glob.glob("sites/*.py")) + sorted(glob.glob("tests/*.py"))
for f in files:
    py_compile.compile(f, doraise=True, cfile=None)
print(f"{len(files)} files ok")
PY
find . -name __pycache__ -type d -prune -exec rm -rf {} +
echo "== node --check"
for f in extension/*.js; do node --input-type=module --check < "$f" || { echo "syntax error in $f" >&2; exit 1; }; done  # ES modules
echo "$(ls extension/*.js | wc -l | tr -d ' ') files ok"
echo "== python -m unittest"
python3 -m unittest discover -s tests -t . "$@"
echo "== node --test"
node --test tests/*.test.mjs
echo "all checks passed"
