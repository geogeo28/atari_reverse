#!/bin/bash
# Bootstrap this project (full import + analysis). Re-run wipes names; use reapply.sh after.
#
# The target is the TOS 1.02 (US) ROM image, not a .PRG: it is imported raw at 0xFC0000,
# the address it is decoded at on the ST, so a Ghidra address IS a ROM address. The image
# is Atari copyright and gitignored — it is referenced where it lies and never copied in.
#
# gen_seeds.py runs first because a TOS ROM reaches nearly all of its code through trap,
# Line-A and Line-F dispatch tables that no flow follower discovers: its output seeds one
# function per table target under Ghidra's own default name. It is a PRE-script only
# (load_rom.sh applies names.txt after it, and again after analysis), so a seed's default
# name can never overwrite an evidence-backed one.
#
# a5 is the BIOS/XBIOS's base register: the shared dispatcher zeroes it (`suba.l a5,a5` at
# 0xFC082C) before every handler, so `202d 044e` reads the system variable at $44E, not an
# unknown `unaff_A5 + 0x44e`. Pinning it to 0 is what makes those bodies readable — but only
# over the BIOS/XBIOS, where it holds: the boot's RAM-test helper at 0xFC0672 is entered with
# a5 = its return address, and the VDI/AES take a5 as an incoming pointer. See COMPONENTS.md,
# "The a5 base register".
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROM="$HERE/../../tools/hatari/TOS102US.img"
BASE=0xFC0000
A5_PIN_START=0xfc0688       # first byte above the boot's a5-return helper 0xFC0672..0xFC0686
A5_PIN_END=0xfc4e5d         # last byte of the BIOS/XBIOS bodies; GEMDOS glue starts at 0xFC4E5E

mkdir -p "$HERE/out"
python3 "$HERE/gen_seeds.py" "$ROM" -o "$HERE/out/seeds.txt"

exec "$HERE/../../tools/load_rom.sh" "$HERE/ghidra_proj" tos102us "$ROM" "$BASE" \
  "$HERE/names.txt" "$HERE/decomp.c" "68000:BE:32:default" \
  "SetRegisterValue.java a5 0 $A5_PIN_START $A5_PIN_END" \
  "ApplyNames.java $HERE/out/seeds.txt"
