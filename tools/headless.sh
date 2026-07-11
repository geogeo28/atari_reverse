#!/bin/bash
# Bootstrap an Atari ST .PRG into an analyzed Ghidra project + decompiled C.
# Generic: works on any GEMDOS .PRG.
#
#   headless.sh <proj_dir> <proj_name> <prg> [base_hex] [out_c]
#
# Pipeline: raw import (68000 BE) -> PrgLoader (rebuild+reloc+symbols, pre-analysis)
#           -> auto-analysis -> AtariOsTrapAnnotate -> ExportDecompC.
set -euo pipefail

GHIDRA=/opt/homebrew/Cellar/ghidra/12.1.2/libexec
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
HERE="$(cd "$(dirname "$0")" && pwd)"

PROJ_DIR="$1"; PROJ_NAME="$2"; PRG="$3"; BASE="${4:-0x10000}"; OUT="${5:-$PROJ_DIR/decomp.c}"
mkdir -p "$PROJ_DIR"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$PRG" \
  -loader BinaryLoader -loader-baseAddr 0 -processor "68000:BE:32:default" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript PrgLoader.java "$PRG" "$BASE" \
  -postScript AtariOsTrapAnnotate.java \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite

echo "--- decompiled C -> $OUT ; open project with: ghidraRun ($PROJ_DIR)"