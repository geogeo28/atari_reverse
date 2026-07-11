#!/bin/bash
# Analyze a RAW MEMORY DUMP (depacked program captured from Hatari).
#   load_dump.sh <proj_dir> <proj_name> <dump.bin> <base_hex> [entry_hex] [out_c]
# The dump is imported raw at <base_hex> (already relocated — no PrgLoader), then
# LoadDump seeds the entry, auto-analysis runs, traps are annotated, C is exported.
set -euo pipefail

GHIDRA=/opt/homebrew/Cellar/ghidra/12.1.2/libexec
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
HERE="$(cd "$(dirname "$0")" && pwd)"

PROJ_DIR="$1"; PROJ_NAME="$2"; DUMP="$3"; BASE="$4"
ENTRY="${5:-$BASE}"; OUT="${6:-$PROJ_DIR/decomp.c}"
mkdir -p "$PROJ_DIR"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$DUMP" \
  -loader BinaryLoader -loader-baseAddr "$BASE" -processor "68000:BE:32:default" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript LoadDump.java "$ENTRY" \
  -postScript AtariOsTrapAnnotate.java \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite

echo "--- dump analyzed -> $OUT ; open project with: ghidraRun ($PROJ_DIR)"