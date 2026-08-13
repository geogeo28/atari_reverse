#!/bin/bash
# Mount Atari ST .st sector images as native macOS volumes, then reveal them in Finder.
#   qa_mount_st.sh <disk.st> [more.st ...]
#
# Backs the "Mount Atari ST Disk" Quick Action; also runnable straight from a shell.
set -euo pipefail

readonly QA_ACTION_NAME="Mount Atari ST Disk"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=qa_lib.sh
source "$SCRIPT_DIR/qa_lib.sh"

readonly HDIUTIL_BIN="/usr/bin/hdiutil"
readonly OPEN_BIN="/usr/bin/open"
# A .st has no partition map and no DDM, so hdiutil will not autodetect it; this class says
# "the file is exactly the sectors, nothing else", which is what makes the FAT12 volume mount.
readonly RAW_IMAGE_KEY="diskimage-class=CRawDiskImage"
# Read-only because this is a preservation toolkit: a read-write mount lets macOS write
# .fseventsd into the image, which measurably changes its checksum. Writing is a deliberate
# act, not a side effect of right-clicking.
readonly ATTACH_ARGS=(-readonly -imagekey "$RAW_IMAGE_KEY")
readonly MOUNTABLE_EXTENSION="st"

# hdiutil pads its columns with tabs and the mount point is last, so a volume name containing
# spaces survives; a volume name containing a tab cannot exist. `|| true` keeps a no-match grep
# from tripping pipefail, so the caller's empty-result guard is the thing that reports it.
mount_point_of() {
  printf '%s\n' "$1" | grep -o '/Volumes/.*' | head -1 || true
}

# Logs the reason and returns 1 rather than exiting, so one bad file in a multi-select does not
# strand the rest of the selection.
mount_image() {
  local image="$1" name="${1##*/}" attach_output mount_point

  if [ ! -f "$image" ] || [ ! -r "$image" ]; then
    qa_log "skipped $name: not a readable file"
    return 1
  fi
  if ! qa_has_extension "$image" "$MOUNTABLE_EXTENSION"; then
    qa_log "skipped $name: not a .$MOUNTABLE_EXTENSION sector image (.stx and .msa are containers, not filesystems)"
    return 1
  fi
  if ! attach_output=$("$HDIUTIL_BIN" attach "${ATTACH_ARGS[@]}" "$image" 2>&1); then
    qa_log "skipped $name: $(printf '%s' "$attach_output" | tail -1)"
    return 1
  fi

  mount_point=$(mount_point_of "$attach_output")
  if [ -z "$mount_point" ]; then
    qa_log "skipped $name: hdiutil attached it but macOS mounted no volume (unreadable FAT12 boot sector?)"
    return 1
  fi

  qa_log "mounted $image at $mount_point (read-only)"
  "$OPEN_BIN" "$mount_point"
  printf '%s\n' "$mount_point"
}

main() {
  [ "$#" -ge 1 ] || qa_fail "No file selected."

  local image failures=0 total="$#"
  for image in "$@"; do
    mount_image "$image" || failures=$((failures + 1))
  done

  [ "$failures" -eq 0 ] \
    || qa_fail "Mounted $((total - failures)) of $total images — see $QA_LOG_FILE"
}

main "$@"