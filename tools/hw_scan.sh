#!/bin/bash
# Dump a project's function boundaries, call graph and hardware accesses out of its Ghidra DB.
# Reads the DB, writes a TSV; no re-import, no re-analysis (like reapply.sh).
#
#   hw_scan.sh <proj_dir> <proj_name> <program_name> <out_tsv> [image_size_hex]
#
# image_size_hex is the differential oracle's flat image size (project.toml's `image_size`,
# default 0x100000): every address at or above it is off-image to the oracle, which is what
# makes an access invisible to a memory-only differential. Post-process with hw_portability.py.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ghidra_env.sh"          # sets $GHIDRA, exports $JAVA_HOME (override via GHIDRA_HOME)

PROJ_DIR="$1"; PROJ_NAME="$2"; PROG="$3"; OUT="$4"; IMAGE_SIZE="${5:-0x100000}"
mkdir -p "$(dirname "$OUT")"      # the Ghidra script opens $OUT directly and will not create it

"$GHIDRA/support/analyzeHeadless" "$PROJ_DIR" "$PROJ_NAME" \
  -process "$PROG" -noanalysis \
  -scriptPath "$HERE/ghidra_scripts" \
  -postScript HwPortabilityScan.java "$OUT" "$IMAGE_SIZE"

echo "--- hardware scan -> $OUT ; classify with: python3 $HERE/hw_portability.py $OUT"
