#!/bin/sh
# Build the release assets from the committed tree (HEAD) into dist/:
#   tabrelay-extension-VERSION.zip  the extension folder, ready for "Load unpacked" after unzipping
#   tabrelay-VERSION.tar.gz         command, extension, site scripts, helper scripts and docs
#   RELEASE_NOTES.md                body for the GitHub release
# Only tracked files go in (git archive), so extension/token.json can never be packed.
# Usage: scripts/build-release.sh [TAG]   (TAG, e.g. v0.1.0, must match the version)
set -e
cd "$(dirname "$0")/.."
VERSION=$(scripts/version.sh "$@")
rm -rf dist && mkdir dist
git archive --format=zip --prefix="tabrelay-extension-$VERSION/" -o "dist/tabrelay-extension-$VERSION.zip" HEAD:extension
git archive --format=tar --prefix="tabrelay-$VERSION/" HEAD \
  tabrelay.py keepalive.py bin extension sites scripts \
  README.md DISCLAIMER.md LICENSE config.example.json | gzip -9n > "dist/tabrelay-$VERSION.tar.gz"
for f in dist/*.zip dist/*.tar.gz; do
  case "$f" in *.zip) unzip -l "$f" ;; *) tar -tzf "$f" ;; esac | grep -q 'token\.json' && { echo "token.json in $f" >&2; exit 1; }
done
REPO=${GITHUB_REPOSITORY:-aaronsuns/tabrelay}
cat > dist/RELEASE_NOTES.md <<NOTES
Tabrelay $VERSION: drive your real, logged-in Chrome from the command line, scripts and AI agents, without stealing focus.

## Install

1. Download \`tabrelay-$VERSION.tar.gz\` and unpack it:
   \`\`\`sh
   tar -xzf tabrelay-$VERSION.tar.gz && cd tabrelay-$VERSION
   ./bin/tabrelay config        # creates extension/token.json, the local secret
   \`\`\`
2. In Chrome open \`chrome://extensions\`, turn on **Developer mode**, click **Load unpacked** and
   pick the \`extension/\` folder inside \`tabrelay-$VERSION/\` (it holds the token the command uses).
3. Add the sites your scripts need on the **Tabrelay: allowed sites** page, then run \`./bin/tabrelay ping\`.

\`tabrelay-extension-$VERSION.zip\` is the same extension folder on its own (no token). If you load
that one instead, copy \`extension/token.json\` from your tabrelay folder into it first.

Requirements: Chrome (or another Chromium with \`chrome.debugger\`), Python 3.10+. No other dependencies.

Read the [Disclaimer](https://github.com/$REPO/blob/v$VERSION/DISCLAIMER.md) before using the site scripts.
Docs: [README](https://github.com/$REPO/blob/v$VERSION/README.md) · [tabrelay.zexa.se](https://tabrelay.zexa.se)
NOTES
ls -l dist
