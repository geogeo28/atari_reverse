#!/bin/bash
# Apply names.txt to the project DB and re-export decomp.c (fast, no re-analysis).
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/reapply.sh" "$HERE/ghidra_proj" wonderboy SWB.PRG "$HERE/names.txt" "$HERE/decomp.c"
