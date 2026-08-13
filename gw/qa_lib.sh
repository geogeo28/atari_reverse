# Shared helpers for the Finder Quick Action scripts (qa_*.sh). Sourced, not executed.
#
# A Quick Action has no terminal: stdout/stderr go nowhere a user will ever look, so every
# outcome has to reach one of two surfaces — a Notification Center banner (failures) or the
# log file (everything). Silent failure is the one thing that must not happen.

readonly QA_LOG_FILE="$HOME/Library/Logs/AtariQuickActions.log"
readonly OSASCRIPT_BIN="/usr/bin/osascript"

# Created once here so every writer — qa_log and the emulator's own redirect — can assume it.
mkdir -p "$(dirname "$QA_LOG_FILE")"

qa_log() {
  printf '%s %s: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$QA_ACTION_NAME" "$*" >>"$QA_LOG_FILE"
}

# AppleScript string literals only escape backslash and double quote; do both before
# interpolating. A denied TCC prompt or a non-GUI session makes osascript fail, which must not
# swallow the caller's own error reporting.
qa_notify() {
  local message="$1" escaped
  escaped=$(printf '%s' "$message" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  "$OSASCRIPT_BIN" -e "display notification \"$escaped\" with title \"$QA_ACTION_NAME\"" \
    || qa_log "notification failed (osascript unavailable or denied)"
}

qa_fail() {
  local message="$1"
  qa_log "FAIL: $message"
  qa_notify "$message"
  printf '%s: %s\n' "$QA_ACTION_NAME" "$message" >&2
  exit 1
}

# -f as well as -r: a directory is readable, and a directory passed as a ROM or disk image
# reaches the emulator as a startup crash instead of a message anyone can act on.
qa_require_readable() {
  local path="$1" role="$2"
  [ -f "$path" ] && [ -r "$path" ] || qa_fail "$role not found or unreadable: $path"
}

# Case-insensitive extension of a path, or the empty string when there is no dot in the basename.
qa_extension() {
  local base="${1##*/}"
  [ "$base" = "${base%.*}" ] && return 0
  printf '%s' "${base##*.}" | tr '[:upper:]' '[:lower:]'
}

# Predicate, not an assertion, because one caller aborts on a bad extension and the other only
# skips that file. Takes a space-separated list of lowercase extensions.
qa_has_extension() {
  local extension candidate
  extension=$(qa_extension "$1")
  for candidate in $2; do
    [ "$extension" = "$candidate" ] && return 0
  done
  return 1
}