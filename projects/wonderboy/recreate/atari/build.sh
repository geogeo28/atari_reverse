#!/bin/bash
# Build WB.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a drive
# for Hatari.
#
#   build.sh            -> the M1 build: stage the image, take the machine, run SMOKE_VBLS vblanks
#                          through the reconstructed vbl_handler, hand it back, dump STATS.BIN
#   build.sh novbl      -> M1's NEGATIVE CONTROL: identical, minus the level-4 vector install. Every
#                          M1 assertion that depends on the machine driving the reconstruction must
#                          FAIL, and smoke.py inverts its verdict for this build.
#   build.sh m2         -> the FRAME build: the image is the ORIGINAL's post-boot RAM instead of the
#                          program plus seeds, and the shim runs game_main_loop rather than counting
#                          vblanks. Needs `python3 atari/original.py dump` first — the image cannot
#                          be computed, only measured (gen_image.py's honesty line).
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

# THE MODES THAT RUN FRAMES, in one place. They stage the original's post-boot RAM and its palette,
# they carry M2_ENTRY_UNWIND, and they are the ones smoke.py stages `PENS.IMG` for. smoke.py SCRAPES
# this line rather than keeping its own list — a second spelling would let a new frame mode boot
# without the palette it needs and report "no M2.BIN", which reads like a crash (CLAUDE.md §5).
FRAME_MODES="m2 m5fault m5flash m6rearm play"

MODE="${1:-m1}"
case "$MODE" in
  m1)    DEF="" ;;
  # The control. Suppressing the ONE install is what makes M1's positives falsifiable: no vblank
  # reaches the reconstruction, so its counter stays at gen_image.py's seeded 0, the tempo byte stays
  # at the unwritten sentinel, the floppy timer never expires and the chip is never touched.
  novbl) DEF="-DSMOKE_NO_VBL_INSTALL" ;;
  m2)    DEF="-DSMOKE_M2" ;;
  # M5's SENSITIVITY CONTROL: the frame build with ONE pen corrupted on its way to the shifter. It is
  # a machine-COLOUR fault and nothing else — the reconstruction draws the same bytes — so every
  # surface that reads colour (the pens, the hardware vector, the rendered picture) must go red and
  # the framebuffer compare must not.
  #
  # PEN 3 RATHER THAN AN ARBITRARY ONE, and the reason is the rendered half of that claim: pen 3 is
  # $777, the white the HUD's panels and text are drawn in, so it is certainly on screen at every
  # anchor. A pen that happened not to appear in the picture would make the control's `picture`
  # arm fail for a reason about coverage rather than about the fault — which is the trap the sibling
  # project fell into and had to document.
  #
  # SMOKE.PY DOES NOT READ THIS LINE. The number reaches the check through the RECORD — the shim
  # publishes it as `M2.BIN`'s `fault_pen` and `assert_only_the_faulted_pen` requires the divergence
  # to be at exactly that pen and no other. Scraping it out of this script instead was the round's
  # own defect: the per-mode `.PRG`s persist while this file is edited, so the scrape would name a
  # pen the running binary need not have injected — the staleness hazard `capture_pc` exists to
  # avoid, reproduced one control over.
  m5fault) DEF="-DSMOKE_M2 -DM5_FAULT_PEN=3" ;;
  # M5's FLASH RUN: the frame build with `flip_screen`'s white-flash countdown armed. The seed is the
  # ORIGINAL's own operand — `move.w #$2,$714.w` at $1328, the lightning arm of `player_weapon_fire`
  # — and atari/original.py pokes the same word into the shipped binary at the same instant, so this
  # is one declared fabrication applied to both sides rather than a fixture on ours.
  # wonderboy_main.c's `arm_the_flash` has the census that says why it cannot be driven instead.
  # The seed itself is scraped from ../include/wonderboy.h below, once REC is known.
  m5flash) DEF="-DSMOKE_M2" ;;
  # M6's NEGATIVE CONTROL: the frame build re-publishing the staged palette after every frame. The
  # same sixteen words through the same sink, so no snapshot in this project can tell it from `m2` —
  # the framebuffer, the pens, the hardware vector and the rendered picture are all identical. Only
  # the ORDERED TIMELINE moves, which is what makes it the control that shows M6 can fail.
  m6rearm) DEF="-DSMOKE_M2 -DSMOKE_M6_REARM" ;;
  # THE BUILD A PERSON PLAYS, and the only one here that is not a measurement. It is `m2` with the
  # frame count and the watchdog lifted (wonderboy_main.c's SMOKE_PLAY block says why each has to
  # go), so the reconstruction's frame loop runs until the window is closed. `atari/run.sh` builds
  # it and launches Hatari with a screen, sound and a joystick; `smoke.py play` is the half of it a
  # headless run can assert.
  play)  DEF="-DSMOKE_M2 -DSMOKE_PLAY" ;;
  *) echo "usage: build.sh [m1 | novbl | $(echo "$FRAME_MODES" | tr ' ' '|')]"; exit 2 ;;
esac

# Whether $MODE is one of FRAME_MODES, as a word match rather than a substring one.
is_frame_mode() { case " $FRAME_MODES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

# ...AND THE TWO LISTS IN THIS FILE ARE PINNED TO EACH OTHER. `FRAME_MODES` is what smoke.py scrapes,
# but the `case` above is what decides whether a mode compiles -DSMOKE_M2 — so a new frame mode added
# to one and not the other would stage the M1 image and report "no M2.BIN", which is exactly the
# symptom FRAME_MODES exists to prevent. Derived from $DEF rather than restated a third time.
case "$DEF" in
  *-DSMOKE_M2*) is_frame_mode "$MODE" || {
      echo "ERROR: mode '$MODE' compiles -DSMOKE_M2 but is not in FRAME_MODES=\"$FRAME_MODES\"."
      echo "       It would be built as a frame binary and staged with the M1 image and no palette."
      exit 1; } ;;
  *) ! is_frame_mode "$MODE" || {
      echo "ERROR: mode '$MODE' is in FRAME_MODES but does not compile -DSMOKE_M2."
      exit 1; } ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
KIT="$(cd "$REC/../../../tools/recreate_kit" && pwd)"     # the shared harness
BIN="$REC/../bin"                                         # projects/wonderboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="WB.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc

# THE FLASH SEED IS THE ORIGINAL'S OWN OPERAND, scraped from the header that quotes the instruction
# rather than written here — one canonical definition, and a build that cannot find it refuses rather
# than compiling an empty `-DM5_FLASH_SEED=`.
if [ "$MODE" = m5flash ]; then
  FLASH_SEED=$(sed -n 's/^#define WB_PLAYER_LIGHTNING_FLASH *\([0-9][0-9]*\)u.*/\1/p' \
               "$REC/include/wonderboy.h")
  [ -n "$FLASH_SEED" ] || { echo "ERROR: no WB_PLAYER_LIGHTNING_FLASH in $REC/include/wonderboy.h";
                            exit 1; }
  DEF="$DEF -DM5_FLASH_SEED=$FLASH_SEED"
fi

# The image comes FIRST: its byte length is the one source of truth for how much wonderboy_main.c
# must read back in, and both it and the address it lands at are passed straight to the compiler.
# WB_STAGED_AT is scraped from ../project.toml rather than written here — that file is where the
# 0x3f8 load base is argued for, and a second spelling could drift from the loader gen_image.py uses.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
if is_frame_mode "$MODE"; then
  # THE M2 IMAGE IS MEASURED, NOT COMPUTED, and this is where that costs something: the dump has to
  # exist before the build, and a stale one is worse than a missing one because it would build.
  DUMP="$BUILD/ORIGRAM.BIN"; REGS="$BUILD/ORIGREGS.txt"; PENS="$BUILD/ORIGPENS.BIN"
  # THE THREE ARTEFACTS MUST BE ONE BOOT'S, and an existence test cannot say that: an interrupted
  # dump leaves this boot's RAM beside the previous boot's registers and palette, all three present.
  # original.py stamps a manifest (boot id + size + digest each) after all three land, and this
  # verifies against it — so a mixed or half-written set refuses the build instead of producing an
  # image and an A5 from different boots.
  "$PY" -c "
import sys; sys.path.insert(0, '$HERE')
import original
ok, message = original.check_manifest('$BUILD')
print(('   ' if ok else 'ERROR: ') + message)
sys.exit(0 if ok else 1)" || exit 1
  "$PY" "$HERE/gen_image.py" "$BIN/disk1/AUTO/SWB.PRG" "$DISK/WB.IMG" --dump "$DUMP"
  # The palette is the boot's product too and it does not live in RAM — see wonderboy_main.c's
  # STAGED_PENS_FILE. Copied rather than generated: it is 32 bytes of measurement.
  cp "$PENS" "$DISK/PENS.IMG"
  # `game_main_loop` is `jmp`ed into and inherits the boot's registers; a5 is the sprite pass's
  # `unwind` and the ONE field of its argument that is a real input (../include/blit.h). Taken from
  # the same dump as the memory, so the two cannot come from different boots.
  #
  # PARSED BY original.py's OWN READER rather than by a sed here. The first draft was a sed, it did
  # not match (BSD sed has no `\b`), and even fixed it would have been a second spelling of a format
  # Python already parses — CLAUDE.md §5's across-a-language-boundary duplication, in the one place
  # where a silent mismatch would compile a plausible wrong number into the frame build.
  UNWIND=$("$PY" -c "
import sys; sys.path.insert(0, '$HERE')
import original
from pathlib import Path
value = original.register(Path('$REGS').read_text(), 'A5')
print('%#010x' % value if value is not None else '')")
  [ -n "$UNWIND" ] || { echo "ERROR: no A5 in $REGS — re-run \`atari/original.py dump\`"; exit 1; }
  DEF="$DEF -DM2_ENTRY_UNWIND=$UNWIND"
else
  "$PY" "$HERE/gen_image.py" "$BIN/disk1/AUTO/SWB.PRG" "$DISK/WB.IMG"
fi
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
# THE IMAGE IS KEPT PER MODE TOO, and it is not filing: the modes stage DIFFERENT images (m1 the
# program plus seeds at 136,408 bytes, m2 the original's post-boot RAM at 523,272) and the .PRG has
# its size compiled in. smoke.py runs five modes against one drive, so without a per-mode copy to
# re-stage from, `smoke.py m2` after `build.sh m1` boots the frame build over the M1 image — which
# is how the first draft failed, loudly here but silently for any future pair whose sizes agree.
cp "$DISK/WB.IMG" "$BUILD/WB-$MODE.IMG"
# The palette belongs to the FRAME modes alone. Keyed on the MODE and not on the file's existence: a
# `[ -f ... ] && cp ...` would have copied m2's leftover into an m1 build (measured, harmlessly —
# nothing reads it there), and as the tail of a `set -e` script a false test aborts the build.
if is_frame_mode "$MODE"; then
  cp "$DISK/PENS.IMG" "$BUILD/WB-$MODE.PENS"
else
  rm -f "$DISK/PENS.IMG" "$BUILD/WB-$MODE.PENS"
fi
ls -l "$DISK/$PRG" "$DISK/WB.IMG"
