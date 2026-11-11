#!/bin/sh
# macOS: install keepalive.py as a launchd agent that runs every 30 min while you are logged in
# and the Mac is awake; keepalive.py itself decides which sites are due. Re-run after moving the
# repo.
#   scripts/install-keepalive.sh              install (or reinstall)
#   scripts/install-keepalive.sh --uninstall  remove it
set -e
LABEL=tabrelay.keepalive
PL="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ "$1" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PL"
  echo "removed $LABEL"
  exit 0
fi
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v python3)
LOG="${TABRELAY_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/tabrelay}"
mkdir -p "$LOG" "$HOME/Library/LaunchAgents"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$ROOT/keepalive.py</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardOutPath</key><string>$LOG/keepalive.log</string>
  <key>StandardErrorPath</key><string>$LOG/keepalive.log</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PL"
echo "installed $PL; log: $LOG/keepalive.log; state: $ROOT/keepalive.py --status"
