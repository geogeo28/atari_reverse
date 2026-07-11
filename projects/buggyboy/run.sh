#!/bin/bash
# Bootstrap the BuggyBoy project (full import + analysis). Re-run wipes names; use reapply.sh after.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/headless.sh" "$HERE/ghidra_proj" BuggyBoy "$HERE/bin/BUGGYBOY.PRG" 0x10000 "$HERE/decomp.c"