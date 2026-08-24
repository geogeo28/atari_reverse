#!/usr/bin/env bash
#
# assert_trap_registers.sh — refuse a GEMDOS/XBIOS trap wrapper that does not save %d2/%a2.
#
#   tools/assert_trap_registers.sh [--expect N] <file.s> [<file.s> ...]
#
# THE WORKSPACE'S ONE HARDWARE-ONLY BUG CLASS THAT NOTHING ELSE CAN SEE. TOS preserves only
# %d3-%d7/%a3-%a6 across a trap; m68k GCC's SysV ABI believes %d2-%d7/%a2-%a6 are callee-saved and
# caches live values in %d2/%a2 across a call to any wrapper. That pair is therefore exactly what
# the compiler expects to survive and TOS may destroy, and a wrapper that does not save it silently
# corrupts ONE VARIABLE IN ITS C CALLER. It shipped three bombs on the STE in BuggyBoy
# (`projects/buggyboy/recreate/README.md`, "On-target register rule"); `docs/on-target-execution.md`
# taxonomy 3 has the measurement.
#
# It is invisible to every differential a project in this workspace has — the Musashi oracle services
# traps in-process and clobbers nothing — invisible to the compiler, and invisible under emulation,
# because a given TOS build may happen to leave a benign value in the pair. The SOURCE is the one
# place the discipline is legible, so this is a source scan run from the build.
#
# ROUTINE BY ROUTINE AND NOT FILE-WIDE, because a file-wide grep is satisfied by one wrapper saving
# the pair while a new one beside it does not. A routine runs from a column-0 `label:` to THE NEXT
# LABEL OR END OF FILE — not to its first `rts`, which would leave everything past a guard clause's
# early return unread.
#
# WHAT IS FLAGGED is a routine that issues a `trap` AND returns (`rts`/`rte`) without carrying both
# halves of the pair. A routine that traps and NEVER returns is exempt by that rule rather than by an
# exception list: `_start`'s own `trap #1` is Pterm0, and a pair clobbered on the way out of the
# program has no caller left to corrupt.
#
# AND THE SCAN PROVES IT CAN FAIL, on every run, which a check with nothing to reject cannot
# demonstrate. The same awk program — not a second copy of it — is re-run over the source with the
# save halves stripped, and again with the RESTORE halves stripped, and each mutation must name every
# wrapper. `--expect N` adds the third control: the count of trap wrappers the scan actually
# evaluated, so a regex that rotted reds here instead of passing vacuously over a file it no longer
# parses.
#
# Exit status: 0 clean, 1 a wrapper (or a control) failed, 2 bad command line.
set -euo pipefail

SELF=$(basename "$0")
USAGE="usage: $SELF [--expect N] <file.s> [<file.s> ...]"

# The awk output's two line kinds, so the shell half parses them rather than guessing.
OFFENDER_TAG="ROUTINE"
COUNT_TAG="WRAPPERS"

# The two halves of the pair, as `sed` addresses the mutation controls delete. They are spelled here
# and matched inside the awk program below; the awk copy is the authority and these two only have to
# hit the same lines for a control to be able to break the file.
SAVE_HALF_SED='movem\.l[ 	]*%d2\/%a2,-(%sp)'
RESTORE_HALF_SED='movem\.l[ 	]*(%sp)+,%d2\/%a2'

# ONE SCAN PROGRAM, over stdin, used by the real check and by both mutation controls. A second copy
# for the controls is how the first draft of this gate came to have a control that tested a DIFFERENT
# program from the one that guards the build (it dropped the restore half entirely).
scan_trap_wrappers() {
  awk -v offender="$OFFENDER_TAG" -v counted="$COUNT_TAG" '
    function close_routine() {
      if (routine != "" && has_trap && returns) {
        wrappers++
        if (!(saved && restored)) print offender, routine
      }
      routine = ""; has_trap = saved = restored = returns = 0
    }
    # `|` opens a comment in GAS m68k syntax, so prose ABOUT the pair cannot satisfy the scan.
    { sub(/\|.*/, "") }
    /^[A-Za-z_][A-Za-z_0-9]*:/ { close_routine(); routine = substr($0, 1, index($0, ":") - 1) }
    $1 == "trap"                       { has_trap = 1 }
    /movem\.l[ \t]*%d2\/%a2,-\(%sp\)/  { saved = 1 }
    /movem\.l[ \t]*\(%sp\)\+,%d2\/%a2/ { restored = 1 }
    # FIELD-MATCHED AND NOT ANCHORED TO END OF LINE: a trailing `| comment` on an rts is this
    # workspace house style, and an anchored /rts$/ reads such a routine as never closing — the
    # hole a mutation found in the first draft.
    $1 == "rts" || $1 == "rte"         { returns = 1 }
    END { close_routine(); print counted, wrappers + 0 }
  '
}

offenders_of() { sed -n "s/^$OFFENDER_TAG //p" <<<"$1"; }
count_of()     { sed -n "s/^$COUNT_TAG //p" <<<"$1"; }

# A mutation control: with `$2` deleted from `$1`, the scan must name every wrapper it counts.
refuse_a_scan_that_cannot_fail() {
  local file=$1 half=$2 what=$3 output named counted
  output=$(sed "s/$half//" "$file" | scan_trap_wrappers)
  named=$(offenders_of "$output" | grep -c . || true)
  counted=$(count_of "$output")
  [ "$named" = "$counted" ] && [ "$counted" -gt 0 ] && return 0
  echo "ERROR: $SELF's own control failed on $file: with every $what removed the scan named"
  echo "       $named of $counted trap wrapper(s), and it must name all of them. The patterns match"
  echo "       neither the trap nor the movem — so the check has been passing for the wrong reason."
  echo "       Fix the scan, not this control."
  return 1
}

check_file() {
  local file=$1 expect=$2 output offenders counted
  [ -f "$file" ] || { echo "ERROR: $SELF: no such file: $file"; return 1; }
  refuse_a_scan_that_cannot_fail "$file" "$SAVE_HALF_SED" "%d2/%a2 SAVE" || return 1
  refuse_a_scan_that_cannot_fail "$file" "$RESTORE_HALF_SED" "%d2/%a2 RESTORE" || return 1

  output=$(scan_trap_wrappers <"$file")
  offenders=$(offenders_of "$output")
  counted=$(count_of "$output")
  if [ -n "$offenders" ]; then
    echo "ERROR: a routine in $file issues a TOS trap without saving %d2/%a2 around it:"
    echo "$offenders" | sed 's/^/         /'
    echo "       TOS treats %d0-%d2/%a0-%a2 as volatile and GCC treats %d2/%a2 as callee-saved, so"
    echo "       the trap would destroy a live value in the C caller. It fails on hardware only —"
    echo "       see docs/on-target-execution.md taxonomy 3 — and this scan is the only surface that"
    echo "       can see it. Save the pair, and move the routine's C argument offsets by 8."
    return 1
  fi
  if [ -n "$expect" ] && [ "$counted" != "$expect" ]; then
    echo "ERROR: $SELF read $counted trap wrapper(s) in $file and the build expects $expect."
    echo "       Either a wrapper was added or removed — update the caller's count — or the scan no"
    echo "       longer parses this file, in which case it has been passing over routines it cannot"
    echo "       see."
    return 1
  fi
  echo "   $file: $counted trap wrapper(s), all saving %d2/%a2 (scan proved failable both halves)"
}

main() {
  local expect=""
  while [ $# -gt 0 ] && [ "${1#-}" != "$1" ]; do
    case $1 in
      --expect) [ $# -ge 2 ] || { echo "$USAGE" >&2; return 2; }; expect=$2; shift 2 ;;
      -h|--help) echo "$USAGE"; return 0 ;;
      *) echo "$SELF: unknown option $1" >&2; echo "$USAGE" >&2; return 2 ;;
    esac
  done
  [ $# -ge 1 ] || { echo "$USAGE" >&2; return 2; }
  # `--expect` is a count of ONE file's wrappers, so it may not be spread over several.
  [ -z "$expect" ] || [ $# -eq 1 ] || {
    echo "$SELF: --expect takes a single file" >&2; return 2; }
  for file in "$@"; do
    check_file "$file" "$expect" || return 1
  done
}

main "$@"
