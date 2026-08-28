#!/bin/bash
# Bootstrap this project (full import + analysis). Re-run wipes names; use reapply.sh after.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/headless.sh" "$HERE/ghidra_proj" zynaps "$HERE/bin/ZYNAPS17.PRG" 0x10000 "$HERE/decomp.c" "68000:BE:32:default"
