#!/bin/bash
# macOS: run JS in the first Chrome tab (any profile, any window) whose URL contains URLPART, via
# Apple Events. No extension needed, so it also works in profiles where Tabrelay isn't installed.
#   scripts/chrome-js.sh URLPART 'JS expression'   prints the result (a promise is NOT awaited: use sync JS)
# Needs View > Developer > Allow JavaScript from Apple Events, turned on in EACH profile you use it
# with (Chrome updates can turn it off again). It can reach every tab, not just an allow-list, so
# treat it as a sharper tool than tabrelay. Background windows render slowly: poll until the page
# is ready.
# Open a page in a given profile (the directory name is shown in chrome://version > Profile Path):
#   open -na "Google Chrome" --args --profile-directory="<profile dir>" URL
[ $# -eq 2 ] || { echo "usage: $0 URLPART 'JS expression'" >&2; exit 2; }
osascript - "$1" "$2" <<'AS'
on run argv
  set part to item 1 of argv
  set js to item 2 of argv
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if URL of t contains part then return execute t javascript js
      end repeat
    end repeat
  end tell
  return "no tab"
end run
AS
