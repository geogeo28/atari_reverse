#!/bin/bash
# Bootstrap an ATARI TOS ROM IMAGE into an analyzed Ghidra project + decompiled C.
#
#   load_rom.sh <proj_dir> <proj_name> <rom.img> <base_hex> [names_file] [out_c] [processor] \
#               [extra_pre ...]
#
# A ROM is not a .PRG: no GEMDOS header, no relocation table, no symbols. It is imported
# raw at the address it runs at (0xFC0000 for a 192 KB ST ROM), so a Ghidra address IS a
# ROM address. RomLoader then builds the address ranges the image references but does not
# contain (RAM + system variables, GEM's BSS, the I/O page, the cartridge port) and sets
# the entry point from the OS header's reset PC.
#
# [names_file] is a name map in the tools/ghidra_scripts/ApplyNames format. It is applied
# TWICE on purpose: once BEFORE analysis, where each `fn` line seeds a function so that
# analysis follows the dispatch tables (a TOS ROM reaches nearly all of its code through
# trap/Line-A/Line-F tables, which no flow follower discovers by itself), and once after,
# so the names land on the functions analysis created. Only the name map goes in the POST
# position: a generated seed file names its entries `FUN_<addr>`, and re-applying it after
# analysis would rename the functions AtariOsTrapAnnotate had just named back to `FUN_`.
# Pass a seed file as an extra_pre instead.
#
# Each optional extra_pre is one whole pre-script invocation as a single word-split string,
# e.g. "SetRegisterValue.java a5 0 0xfc0688 0xfc4e5d" or "ApplyNames.java out/seeds.txt" —
# inserted after RomLoader and BEFORE the name map, so a seed's default name never overwrites
# a name the map has. Projects that need none pass none.
#
# Pipeline: raw import -> RomLoader (blocks + header + entry, pre-analysis) -> extra_pre
#           -> ApplyNames (seed) -> LineAResolve -> LineFResolve -> auto-analysis
#           -> LineAResolve (reanalyze) -> LineFResolve (reanalyze) -> SeedFunctions
#           -> AtariOsTrapAnnotate -> ApplyNames -> ExportDecompC.
#
# Both opcode resolvers run twice for the reason headless.sh gives: a $aXXX (Line-A) or
# $fXXX (GEM Line-F call) word halts the 68000 disassembler, so one pass is needed to
# unblock the entry path before analysis and one to catch words in code only analysis
# reached. Keep the shared steps in sync with headless.sh / load_dump.sh.
#
# The run FAILS LOUDLY: analyzeHeadless is teed to <proj_dir>/../out/headless.log, and a
# script error, an exception or a missing/empty export is a non-zero exit — Ghidra itself
# reports a failed script on stderr and carries on to the next one with exit code 0.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; ROM="$3"; BASE="$4"
NAMES="${5:-}"; OUT="${6:-$PROJ_DIR/decomp.c}"; PROC="${7:-68000:BE:32:default}"
EXTRA_PRE=()
if [ "$#" -gt 7 ]; then
  shift 7
  for spec in "$@"; do
    EXTRA_PRE+=(-preScript $spec)     # unquoted on purpose: "Script.java arg arg" is one clause
  done
fi

LOG_DIR="$(dirname "$PROJ_DIR")/out"
LOG="$LOG_DIR/headless.log"
mkdir -p "$PROJ_DIR" "$LOG_DIR"

NAME_PRE=(); NAME_POST=()
if [ -n "$NAMES" ]; then
  NAME_PRE=(-preScript ApplyNames.java "$NAMES")
  NAME_POST=(-postScript ApplyNames.java "$NAMES")
fi

if ! "$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$ROM" \
  -loader BinaryLoader -loader-baseAddr "${BASE#0x}" -processor "$PROC" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript RomLoader.java "$BASE" \
  ${EXTRA_PRE[@]+"${EXTRA_PRE[@]}"} \
  ${NAME_PRE[@]+"${NAME_PRE[@]}"} \
  -preScript LineAResolve.java \
  -preScript LineFResolve.java \
  -postScript LineAResolve.java reanalyze \
  -postScript LineFResolve.java reanalyze \
  -postScript SeedFunctions.java \
  -postScript AtariOsTrapAnnotate.java \
  ${NAME_POST[@]+"${NAME_POST[@]}"} \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite 2>&1 | tee "$LOG"; then
  echo "load_rom.sh: analyzeHeadless exited non-zero -- see $LOG" >&2
  exit 1
fi

# Ghidra logs a failed script as "REPORT SCRIPT ERROR" plus the stack trace and keeps going,
# so the exit code above says nothing about the scripts. The second alternative is a stack
# trace's own header line ("java.lang.NullPointerException: ..."), anchored so that the word
# inside an ordinary log message does not match.
SCRIPT_ERROR_RE='REPORT SCRIPT ERROR|^[a-zA-Z.]*(Exception|Error)(: |$)'
FAIL_LINES_SHOWN=5
if grep -qE "$SCRIPT_ERROR_RE" "$LOG"; then
  echo "load_rom.sh: a script failed during analysis -- see $LOG:" >&2
  grep -nE "$SCRIPT_ERROR_RE" "$LOG" | head -"$FAIL_LINES_SHOWN" >&2
  exit 1
fi
if [ ! -s "$OUT" ]; then
  echo "load_rom.sh: no decompiled C at $OUT (ExportDecompC produced nothing) -- see $LOG" >&2
  exit 1
fi

echo "--- ROM analyzed -> $OUT (processor $PROC); open project with: ghidraRun ($PROJ_DIR)"
