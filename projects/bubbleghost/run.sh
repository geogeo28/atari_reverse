#!/bin/bash
# Bootstrap this project (full import + analysis). Re-run wipes names; use reapply.sh after.
#
# Ghidra is fed bin/GHOST_RT.PRG, not bin/GHOST_PLAIN.PRG: the Alcyon/DRI C crt0 at 0x10036
# moves the DATA segment above the BSS before anything else runs, so the file layout
# [TEXT][DATA][BSS] is not the layout the program executes in. tools/prg_relayout.py rebuilds
# the image the way crt0 leaves it, [TEXT][BSS][DATA], which makes a Ghidra address the RUN-TIME
# address for code and globals alike. a4 — the small model's data pointer, which crt0 parks on
# the BSS/DATA boundary — is pinned before analysis so `n(a4)` globals decompile as
# DAT_<run-time address> that names.txt can label with `var`.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BASE=0x10000

python3 "$REPO/tools/prg_relayout.py" "$HERE/bin/GHOST_PLAIN.PRG" -o "$HERE/bin/GHOST_RT.PRG"

# a4 = p_dbase + p_blen (crt0 0x10096) = load base + the relayout image's text length,
# read back from the header rather than repeated as a literal.
A4=$(python3 -c 'import struct,sys; print(hex(int(sys.argv[1],16)+struct.unpack_from(">I",open(sys.argv[2],"rb").read(),2)[0]))' \
     "$BASE" "$HERE/bin/GHOST_RT.PRG")

# The crt0 reaches the global-data initialiser at 0x16d8e only through `jsr 48(a5)` with
# a5 = p_tbase, so flow analysis never disassembles it and ~1 KB of TEXT would stay out of
# decomp.c. Seeding it as a pre-script lets auto-analysis follow the flow from there. The seed
# keeps Ghidra's default FUN_ name so the DB carries no name names.txt does not.
mkdir -p "$HERE/out"
SEED="$HERE/out/seed_functions.txt"
echo 'fn 0x16d8e FUN_00016d8e' > "$SEED"

exec "$REPO/tools/headless.sh" "$HERE/ghidra_proj" bubbleghost "$HERE/bin/GHOST_RT.PRG" \
  "$BASE" "$HERE/decomp.c" "68000:BE:32:default" \
  "SetRegisterValue.java a4 $A4" \
  "ApplyNames.java $SEED"
