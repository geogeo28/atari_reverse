#!/bin/bash
# Build WB.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a drive
# for Hatari.
#
#   build.sh            -> the M1 build: stage the image, take the machine, run SMOKE_VBLS vblanks
#                          through the reconstructed vbl_handler, hand it back, dump STATS.BIN
#   build.sh novbl      -> M1's NEGATIVE CONTROL: identical, minus the level-4 vector install. Every
#                          M1 assertion that depends on the machine driving the reconstruction must
#                          FAIL, and smoke.py inverts its verdict for this build.
#
# Writes disk/{WB.PRG,WB.IMG} and keeps build/WB-<mode>.PRG so a check needing two builds in
# sequence does not have to rebuild. build/ and disk/ are gitignored (repo .gitignore already covers
# projects/*/recreate/atari/{build,disk}/).
#
# THE CORES ARE COMPILED UNCHANGED except for one flag they themselves anticipate: -DWB_ON_TARGET
# turns the `#ifdef` arm inside `../src/game.c`'s and `../src/stage.c`'s shifter sinks into real
# stores. The differential .so never sees that define, so `make test` is untouched — and
# `assert_the_differential_build_is_unchanged` below MEASURES that rather than asserting it in prose.
#
# THE SEAM IS THE LINK, not the include path. Every kit symbol Wonder Boy calls is a real symbol, so
# the kit's src/{hw,psg,sched,os_refusal,dosound_log}.c are simply left out. THE SURFACE IS SIX
# SYMBOLS AND wonderboy_backend.c OWES FIVE OF THEM: `os_refused` is the sixth and is deliberately
# NOT defined, because -DOS_NO_REFUSAL_TALLY makes the kit's own os.h serve an inline identity for
# it. Joust needs a `shim_include/os.h` shadow because the helpers it replaces are `static inline`;
# this game calls none of those — which is a property of the CORES and so is checked, below, rather
# than believed.
set -euo pipefail

MODE="${1:-m1}"
case "$MODE" in
  m1)    DEF="" ;;
  # The control. Suppressing the ONE install is what makes M1's positives falsifiable: no vblank
  # reaches the reconstruction, so its counter stays at gen_image.py's seeded 0, the tempo byte stays
  # at the unwritten sentinel, the floppy timer never expires and the chip is never touched.
  novbl) DEF="-DSMOKE_NO_VBL_INSTALL" ;;
  *) echo "usage: build.sh [m1 | novbl]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
KIT="$(cd "$REC/../../../tools/recreate_kit" && pwd)"     # the shared harness
BIN="$REC/../bin"                                         # projects/wonderboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="WB.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc

# The image comes FIRST: its byte length is the one source of truth for how much wonderboy_main.c
# must read back in, and both it and the address it lands at are passed straight to the compiler.
# WB_STAGED_AT is scraped from ../project.toml rather than written here — that file is where the
# 0x3f8 load base is argued for, and a second spelling could drift from the loader gen_image.py uses.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
"$PY" "$HERE/gen_image.py" "$BIN/disk1/AUTO/SWB.PRG" "$DISK/WB.IMG"
IMG_BYTES=$(wc -c < "$DISK/WB.IMG" | tr -d ' ')           # BSD wc pads with spaces
STAGED_AT=$(sed -n 's/^load_base *= *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/project.toml")
[ -n "$STAGED_AT" ] || { echo "ERROR: no load_base in $REC/project.toml"; exit 1; }
DEF="$DEF -DPROGRAM_BYTES=$IMG_BYTES -DWB_STAGED_AT=$STAGED_AT"

# -Wno-array-bounds: the shim dereferences fixed hardware addresses (the shifter, the MFP, the ACIA)
#   as absolute pointers, which GCC reads as an out-of-bounds array[0] access.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises wonderboy_backend.c's hand-written
#   memset/memcpy loops and replaces them with calls to memcpy/memset — i.e. with themselves.
# -DOS_NO_REFUSAL_TALLY: the kit's os.h anticipates exactly this build and compiles `os_refused`
#   down to an inline identity, so src/os_refusal.c is not needed. The one game-side call site
#   (../src/sound.c:786) then simply returns its sentinel, which is the routine bailing out of a
#   malformed sound pattern — and ../STATUS.md records that that opcode band ($98..$b7) has no
#   on-target story of its own yet.
# shim_include is on the path for tos.h / wonderboy_target.h / string.h ONLY; it shadows no kit header.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY -DWB_ON_TARGET \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra -Wno-array-bounds"
CORES="$(ls "$REC"/src/*.c)"

# Comments stripped WITHOUT expanding includes: -fpreprocessed tells the preprocessor its input is
# already preprocessed, so `#include` is left alone while comments and line splices go. Both scans
# below need that — a core's prose mentions the very identifiers they hunt for, and the first draft
# of each tripped on its own documentation.
strip_comments() { $CC -fpreprocessed -E -P "$1" 2>/dev/null; }

# ---- the claim in the banner, measured ---------------------------------------------------------
# -DWB_ON_TARGET is passed HERE and nowhere else, so the `#ifdef` arms in ../src/game.c and
# ../src/stage.c must vanish for the differential build. Asserted at the SOURCE, by preprocessing
# the two touched cores exactly as kit.mk does — without the define — and requiring that not one
# `wb_target_` token survives. A source-level check rather than an artifact comparison because it
# holds whether or not a .so has been built, and because it names the two files that carry the risk.
assert_the_differential_build_is_unchanged() {
  local HOST_CC="${CC_HOST:-cc}" LEAKED
  for CORE in "$REC/src/game.c" "$REC/src/stage.c"; do
    LEAKED=$($HOST_CC -E -I"$REC/include" -I"$KIT/include" "$CORE" 2>/dev/null \
             | grep -c 'wb_target_' || true)
    [ "$LEAKED" = "0" ] || {
      # NO BACKTICKS IN THESE STRINGS. The first draft wrote a tidy `make test` in the message and
      # bash ran it: inside double quotes a backtick pair is command substitution, so the failure
      # path silently launched the whole differential suite before printing anything. Found when the
      # RED-check's output carried a clang error no part of this script compiles.
      echo "ERROR: $CORE reaches wb_target_* WITHOUT -DWB_ON_TARGET ($LEAKED references)."
      echo "       The differential .so would link the on-target arm, and the suite would no longer"
      echo "       be measuring the same code as before. Check the #ifdef guard."
      exit 1; }
  done
  # ...and the same claim from the other end when the artifact is there: the built .so must not name
  # the shim at all. Conditional because build/ is gitignored and a fresh clone has no .so yet.
  if [ -f "$REC/build/libwonderboy.so" ] && nm "$REC/build/libwonderboy.so" 2>/dev/null \
       | grep -q 'wb_target_'; then
    echo "ERROR: $REC/build/libwonderboy.so names wb_target_* — the differential build is NOT unchanged"
    exit 1
  fi
}

# ---- the seam tripwire the symbol scan CANNOT be --------------------------------------------
# The post-link scan further down looks for MODEL SYMBOLS, and it is blind to the half of the kit
# that has none: `os_random`, `os_giaccess`, `os_bconin`, `os_bconstat`, `os_crawio`, `os_super` and
# the whole staged-file family are `static inline` in the kit's os.h. A core that started calling one
# would compile THE MODEL into the PRG — no undefined symbol, no g_* global, nothing for `nm` to
# find — and this build would happily "verify" the reconstruction against a keyboard that does not
# exist. That is precisely the false-green class the whole project is built to refuse.
#
# So the cores are scanned at the SOURCE for calls to anything named os_*, and the allowed set is
# named here. It is two: `os_in_image` is pure arithmetic over OS_IMAGE_SIZE and correct unchanged,
# and `os_refused` compiles to an inline identity under -DOS_NO_REFUSAL_TALLY. Anything else is a
# model with no on-target meaning, and adding one to this list is a decision about what the machine
# really answers — which is the decision this check exists to force someone to make in the open.
OS_HELPERS_WITH_AN_ON_TARGET_MEANING="os_in_image|os_refused"

assert_no_core_calls_a_modelled_os_helper() {
  local FOUND
  FOUND=$(for CORE in $CORES; do
            strip_comments "$CORE" \
              | grep -oE '\bos_[a-z_0-9]+[[:space:]]*\(' \
              | grep -oE '\bos_[a-z_0-9]+' \
              | grep -vxE "$OS_HELPERS_WITH_AN_ON_TARGET_MEANING" \
              | sed "s|^|$(basename "$CORE"): |"
          done | sort -u || true)
  [ -z "$FOUND" ] || {
    echo "ERROR: a core calls a MODELLED os.h helper, which is static inline and so would be"
    echo "       compiled into the PRG with nothing for the symbol scan to catch:"
    echo "$FOUND" | sed 's/^/         /'
    echo "       Give it a real on-target meaning (wonderboy_backend.c) and add it to"
    echo "       OS_HELPERS_WITH_AN_ON_TARGET_MEANING, or do not call it from a core."
    exit 1; }
}

echo ">> check the seam (the differential build, and the static-inline half the symbol scan misses)"
assert_the_differential_build_is_unchanged
assert_no_core_calls_a_modelled_os_helper

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/wonderboy_os.s" "$HERE/wonderboy_main.c" "$HERE/wonderboy_backend.c" $CORES \
    -lgcc -o "$BUILD/wonderboy.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# NONE of the kit's off-target models may have been linked in. The build leaves their sources out,
# but a header that grew a `static inline` fallback — or a core that started calling one — would
# reintroduce the model silently and this build would "verify" against it. Checked, not trusted.
for MODEL in g_hw_reset g_psg_reset g_sched_reset g_dosound g_os_refusal_reset sched_poll8; do
  if m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="'"$MODEL"'"{found=1} END{exit !found}'; then
    echo "ERROR: the off-target model symbol $MODEL is in the PRG — a kit src/*.c leaked into the link"
    exit 1
  fi
done

# ...and the mirror: the FIVE the backend owes must all be there, so a core that stopped calling one
# cannot quietly shrink the surface README.md enumerates. Five and not six: the surface is six
# symbols, and the sixth — `os_refused` — is deliberately undefined here (see the banner).
for SYM in hw_read8 psg_port_read psg_port_write sched_wait8 sched_poll16; do
  m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="'"$SYM"'"{found=1} END{exit !found}' \
    || { echo "ERROR: $SYM is not in the PRG — wonderboy_backend.c no longer covers the surface"; exit 1; }
done

# Drop .debug_* (and their .rela.debug_*, which carry odd-offset fixups mkprg would choke on);
# keep .rela.text/.rela.data, the R_68K_32 fixups the GEMDOS relocation table is built from.
m68k-elf-strip --strip-debug "$BUILD/wonderboy.elf"

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/wonderboy.elf" "$BUILD/wonderboy.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/wonderboy.elf" "$BUILD/wonderboy.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/$PRG"
cp "$BUILD/$PRG" "$BUILD/WB-$MODE.PRG"
ls -l "$DISK/$PRG" "$DISK/WB.IMG"
