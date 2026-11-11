#!/bin/sh
# macOS: install sites/promo_queue.py as a launchd agent: every 2 hours, one queue run (it posts at
# most 1 group per run, 6 per day, only 09-22, and stops itself if Facebook limits posting).
#   scripts/install-promo-queue.sh QUEUE.json [QUEUE2.json ...]   install (or reinstall)
#   scripts/install-promo-queue.sh --uninstall                    remove it
# Re-run with the full list whenever a queue is added: the limits count across all queues.
set -e
LABEL=tabrelay.promo-queue
PL="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ "$1" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PL"
  echo "removed $LABEL"
  exit 0
fi
[ $# -gt 0 ] || { echo "usage: $0 QUEUE.json [QUEUE2.json ...] | --uninstall" >&2; exit 2; }
ROOT=$(cd "$(dirname "$0")/.." && pwd)
QS=""
for q in "$@"; do
  [ -f "$q" ] || { echo "no such queue file: $q" >&2; exit 2; }
  QS="$QS<string>$(cd "$(dirname "$q")" && pwd)/$(basename "$q")</string>"
done
PY=$(command -v python3)
LOG="${TABRELAY_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/tabrelay}"
mkdir -p "$LOG" "$HOME/Library/LaunchAgents"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$ROOT/sites/promo_queue.py</string>$QS</array>
  <key>StartInterval</key><integer>7200</integer>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardOutPath</key><string>$LOG/promo-queue.log</string>
  <key>StandardErrorPath</key><string>$LOG/promo-queue.log</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PL"
echo "installed $PL for $*; log: $LOG/promo-queue.log; status: $ROOT/sites/promo_queue.py $* --status"
