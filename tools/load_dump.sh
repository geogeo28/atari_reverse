#!/bin/bash
# Analyze a RAW MEMORY DUMP (depacked program captured from Hatari).
#   load_dump.sh <proj_dir> <proj_name> <dump.bin> <base_hex> [entry_hex] [out_c] [processor]
# The dump is imported raw at <base_hex> (already relocated — no PrgLoader), then
# LoadDump seeds the entry, auto-analysis runs, traps are annotated, C is exported.
# processor defaults to 68000:BE:32:default (use 68000:BE:32:MC68030 for 68010/020/030 code).
#
# The LineAResolve / SeedFunctions steps below are the same three the .PRG path runs
# (same SLEIGH, same entry-then-follow-flow shape) — keep them in sync with headless.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; DUMP="$3"; BASE="$4"
ENTRY="${5:-$BASE}"; OUT="${6:-$PROJ_DIR/decomp.c}"; PROC="${7:-68000:BE:32:default}"
mkdir -p "$PROJ_DIR"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -import "$DUMP" \
  -loader BinaryLoader -loader-baseAddr "$BASE" -processor "$PROC" \
  -scriptPath "$HERE/ghidra_scripts" \
  -preScript LoadDump.java "$ENTRY" \
  -preScript LineAResolve.java \
  -postScript LineAResolve.java reanalyze \
  -postScript SeedFunctions.java \
  -postScript AtariOsTrapAnnotate.java \
  -postScript ExportDecompC.java "$OUT" \
  -overwrite

echo "--- dump analyzed -> $OUT (processor $PROC); open project with: ghidraRun ($PROJ_DIR)"