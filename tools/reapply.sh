#!/bin/bash
# Re-apply a name map to an existing project and re-export decompiled C.
# No re-import / re-analysis: fast iteration for the naming loop.
#
#   reapply.sh <proj_dir> <proj_name> <program_name> <names_file> [out_c]
#
# e.g. program_name = BUGGYBOY.PRG (the imported program inside the project).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; PROG="$3"; NAMES="$4"; OUT="${5:-$PROJ_DIR/decomp.c}"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -process "$PROG" -noanalysis \
  -scriptPath "$HERE/ghidra_scripts" \
  -postScript ApplyNames.java "$NAMES" \
  -postScript ExportDecompC.java "$OUT"