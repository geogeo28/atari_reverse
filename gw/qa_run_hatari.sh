#!/bin/bash
# Boot an Atari ST disk image in Hatari, detached from the caller.
#   qa_run_hatari.sh <disk.st|.stx|.msa|.dim>
#
# Backs the "Run in Hatari" Quick Action; also runnable straight from a shell.
set -euo pipefail

readonly QA_ACTION_NAME="Run in Hatari"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=qa_lib.sh
source "$SCRIPT_DIR/qa_lib.sh"

readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly HATARI_BIN="/opt/homebrew/bin/hatari"
# Same override knob as tools/hatari_run.sh, so one env var retargets both. Services inherit a
# minimal environment, so the fallback is an absolute in-repo path rather than a PATH lookup.
readonly DEFAULT_TOS_IMAGE="$REPO_ROOT/tools/hatari/TOS104US.img"
readonly TOS_IMAGE="${TOS_IMG:-$DEFAULT_TOS_IMAGE}"
# Hatari 2.6.1 reads all four as floppy images (manual: "*.ST, *.MSA, *.DIM and *.STX").
readonly RUNNABLE_EXTENSIONS="st stx msa dim"
# Matches tools/hatari_run.sh: 1 MiB ST, RGB monitor, low-res desktop.
readonly MACHINE_ARGS=(--memsize 1 --monitor rgb --tos-res low)
readonly STARTUP_GRACE_SECONDS=1

launch_detached() {
  local image="$1" pid
  # Finder waits on the Quick Action's process group, so the emulator must outlive this script:
  # nohup detaches it from the session and the redirect frees the inherited pipes.
  nohup "$HATARI_BIN" "${MACHINE_ARGS[@]}" --tos "$TOS_IMAGE" --disk-a "$image" >>"$QA_LOG_FILE" 2>&1 &
  pid=$!

  # Hatari validates its ROM and image only after starting, so a bad one surfaces as an early
  # exit. Without this probe the action reports success and opens nothing. The job is left in
  # the shell's table on purpose: disowning it would let a dead child linger as a zombie, which
  # kill -0 still reports as alive.
  sleep "$STARTUP_GRACE_SECONDS"
  kill -0 "$pid" 2>/dev/null \
    || qa_fail "Hatari exited immediately on ${image##*/} — see $QA_LOG_FILE"

  qa_log "launched hatari pid $pid on $image (TOS $TOS_IMAGE)"
}

main() {
  [ "$#" -eq 1 ] || qa_fail "Select exactly one disk image (got $#). Hatari runs one machine per window."
  local image="$1"

  qa_require_readable "$HATARI_BIN" "Hatari"
  qa_require_readable "$TOS_IMAGE" "TOS ROM"
  qa_require_readable "$image" "Disk image"
  qa_has_extension "$image" "$RUNNABLE_EXTENSIONS" \
    || qa_fail "Not an Atari disk image: ${image##*/} (expected ${RUNNABLE_EXTENSIONS// /, })"

  launch_detached "$image"
}

main "$@"