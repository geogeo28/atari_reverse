#!/bin/bash
# Bootstrap an Atari ST .PRG into an analyzed Ghidra project + decompiled C.
# Generic: works on any GEMDOS .PRG.
#
#   headless.sh <proj_dir> <proj_name> <prg> [base_hex] [out_c] [processor]
#
# processor defaults to 68000:BE:32:default; use 68000:BE:32:MC68030 for programs
# that use 68010/020/030 instructions (movec, moves, extended addressing, ...).
#
# Pipeline: raw import (68000 BE) -> PrgLoader (rebuild+reloc+symbols, pre-analysis)
#           -> auto-analysis -> AtariOsTrapAnnotate -> ExportDecompC.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; PRG="$3"; BASE="${4:-0x10000}"
OUT="${5:-$PROJ_DIR/decomp.c}"; PROC="${6:-68000:BE:32:default}"
mkdir -p "$PROJ_DIR"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$PRG" \
  -loader BinaryLoader -loader-baseAddr 0 -processor "$PROC" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript PrgLoader.java "$PRG" "$BASE" \
  -postScript AtariOsTrapAnnotate.java \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite

echo "--- decompiled C -> $OUT (processor $PROC); open project with: ghidraRun ($PROJ_DIR)"