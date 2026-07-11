#!/bin/bash
# Export current names from a project's Ghidra DB back to names.txt format.
# Use to recover names made/edited in the GUI. Diff the output against your
# curated names.txt and merge — this does NOT overwrite names.txt.
#
#   dump_names.sh <proj_dir> <proj_name> <program_name> <out_file>
set -euo pipefail

GHIDRA=/opt/homebrew/Cellar/ghidra/12.1.2/libexec
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
HERE="$(cd "$(dirname "$0")" && pwd)"

PROJ_DIR="$1"; PROJ_NAME="$2"; PROG="$3"; OUT="$4"

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -process "$PROG" -noanalysis \
  -scriptPath "$HERE/ghidra_scripts" \
  -postScript DumpNames.java "$OUT"

echo "--- dumped -> $OUT ; diff against names.txt and merge new/changed lines"