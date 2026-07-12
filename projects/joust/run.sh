#!/bin/bash
# Bootstrap the (depacked) Joust project: full import + analysis. Re-run wipes names.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/headless.sh" "$HERE/ghidra_proj" Joust "$HERE/bin/JOUST.PRG" 0x10000 "$HERE/decomp.c"