#!/bin/bash
# Bootstrap this project (full import + analysis). Re-run wipes names; use reapply.sh after.
#
# BASE IS 0x3F8, NOT the workspace default 0x10000: SWB.PRG's entry stub copies
# the image from file offset 8 to absolute $400 and jumps there, so the body is
# position-DEPENDENT and its absolute operands are "image offset + 0x3F8".
# At 0x10000 every absolute reference dangles and Ghidra recovers 57 functions;
# at 0x3F8 it recovers 186. See notes/architecture.md.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/headless.sh" "$HERE/ghidra_proj" wonderboy "$HERE/bin/disk1/AUTO/SWB.PRG" 0x3f8 "$HERE/decomp.c" "68000:BE:32:default"
