#!/bin/bash
# Bootstrap an Atari ST .PRG into an analyzed Ghidra project + decompiled C.
# Generic: works on any GEMDOS .PRG.
#
#   headless.sh <proj_dir> <proj_name> <prg> [base_hex] [out_c] [processor] [extra_pre ...]
#
# processor defaults to 68000:BE:32:default; use 68000:BE:32:MC68030 for programs
# that use 68010/020/030 instructions (movec, moves, extended addressing, ...).
#
# Each optional extra_pre is one whole pre-script invocation as a single word-split
# string, e.g. "SetRegisterValue.java a4 0x24f1a" — inserted after PrgLoader and before
# LineAResolve, i.e. still ahead of auto-analysis. Projects that need none pass none.
#
# Pipeline: raw import (68000 BE) -> PrgLoader (rebuild+reloc+symbols, pre-analysis)
#           -> LineAResolve -> auto-analysis -> LineAResolve (reanalyze)
#           -> SeedFunctions -> AtariOsTrapAnnotate -> ExportDecompC.
#
# LineAResolve runs twice because a $aXXX opcode halts disassembly: once before
# analysis (the entry path) and once after it (code only auto-analysis reached).
# tools/load_dump.sh runs the same three steps — keep the two lists in sync.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; PRG="$3"; BASE="${4:-0x10000}"
OUT="${5:-$PROJ_DIR/decomp.c}"; PROC="${6:-68000:BE:32:default}"
EXTRA_PRE=()
if [ "$#" -gt 6 ]; then
  shift 6
  for spec in "$@"; do
    EXTRA_PRE+=(-preScript $spec)     # unquoted on purpose: "Script.java arg arg" is one clause
  done
fi
mkdir -p "$PROJ_DIR"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$PRG" \
  -loader BinaryLoader -loader-baseAddr 0 -processor "$PROC" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript PrgLoader.java "$PRG" "$BASE" \
  ${EXTRA_PRE[@]+"${EXTRA_PRE[@]}"} \
  -preScript LineAResolve.java \
  -postScript LineAResolve.java reanalyze \
  -postScript SeedFunctions.java \
  -postScript AtariOsTrapAnnotate.java \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite

echo "--- decompiled C -> $OUT (processor $PROC); open project with: ghidraRun ($PROJ_DIR)"