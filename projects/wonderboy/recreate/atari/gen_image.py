#!/usr/bin/env python3
"""Stage the program image for the on-target Wonder Boy build — and declare what it is NOT.

TWO IMAGES, and the difference between them is the whole of §2 of atari/README.md:

    gen_image.py <SWB.PRG> <out/WB.IMG>                    # M1: the PROGRAM, plus named seeds
    gen_image.py <SWB.PRG> <out/WB.IMG> --dump <RAM.BIN>   # M2: the ORIGINAL's post-boot RAM

WHAT THE M1 IMAGE EMITS is the differential harness's OWN base image, narrowed to the bytes that are
not zero: the relocated `SWB.PRG` over ``[0x3f8, 0x218d0)``, with a named set of seed words written
into it. `recreate_kit.harness.BASE_IMAGE` is built by exactly one call (``loader.load_image(PRG)``),
and this uses that call, so the bytes the PRG carries on target are the bytes every green test in
``../test/`` ran against. Nothing is transcribed.

WHAT THE M2 IMAGE EMITS is `atari/original.py`'s dump: the game's whole address space
``[0x3f8, 0x80000)`` as the SHIPPED 1989 binary left it at ``$f8b4``, the boot's last instruction
before `jmp $4a0.w`. NO SEEDS ARE WRITTEN INTO IT — a seed is a value chosen so a check can see
something, and M2's check is a frame-for-frame comparison against that same binary, which any chosen
byte would move away from. What the M1 seeds do for M1, the original's own state does for M2.

WHY THE PROGRAM'S OWN BYTES HAVE TO BE THERE AT ALL, since none of them execute here: the
reconstruction reads them. `SWB.PRG` has no data or bss segment — its 0x214d8 bytes of text carry
every table the cores index (the behaviour dispatch at $938, the sprite descriptors, the message
strings, the sound module at $17adc, the palette table), so `image + <Ghidra address>` has to hold
them at exactly those offsets. The relocation is done HERE because GEMDOS relocates a `.PRG` for the
address IT chose, which is not 0x3f8.

=======================  THE HONESTY LINE  =======================

**A STAGED IMAGE IS A DECLARED FABRICATION OF THE BOOT'S RESULT.** `game_main_loop` is `jmp`ed into
with a stage already loaded, and THIS FILE does not load one.

What is unported has shrunk since that sentence was first written and the shape of the claim has
changed with it. `load_resource_by_index`, the tile installer at $e67e and `sprites_cru_install` at
$e87c are all RECONSTRUCTED (batch 44 phases A and B), and batch 44 phase C composed the whole chain
that calls them — `boot_load_stage` in `../src/boot.c`, $e5ba..$f8b4, differentially verified against
the original end to end. So the products below CAN be computed host-side now. What is still unported
is the FDC driver below the file-load seam and the Copylock at $ecca, and what is still true of THIS
file is simpler and narrower: **it stages a dump because nothing here runs that chain**, not because
the chain cannot be run.

**AND "CAN BE COMPUTED" HAS TWO CONDITIONS, both measured and both still standing.** The chain runs
off target only through phase B's GEMDOS **substitution** at the file-load seam — `disk_read_file`
stands in for `$5e7c` and the FDC driver below it never executes. And the kit's staged-file model
lays files contiguously into an area whose size is the model's own — `STAGING_CAPACITY` in
`../test/test_boot.py`, derived there from the staging base and the stack guard — and **`SPRITES.CRU`
does not fit it**. So the sprite arm is driven over the PREFIX of that file which fits beside
whatever else the case stages, which makes the prefix's length a property of the case and not a
number to write down here. `../test/test_boot_chain.py`'s
`test_the_sprites_file_is_staged_as_the_prefix_the_model_can_hold` is what derives and pins it;
`../test/test_boot.py` is what measures that this is the only boot resource the model cannot hold
whole. A build that wired `boot_load_stage` in here would meet the same ceiling, so it is written
down where the wiring would happen and not only in the batch notes.

**THE M1 IMAGE FABRICATES ALMOST ALL OF IT**, as a range of zeros each (the map is
`../project.toml`'s, the chain `../STATUS.md`'s):

  $1d43e..$2103e  bg_tile_bitmaps      120 x $80 tiles the $e67e loop selects out of depacked
                                       TILEDATA.RAD. `bg_tile_install` IS ported, so the range is
                                       computable — and cheaply: it needs TILEDATA.RAD, `rad_depack`
                                       and that one installer, NOT a run of the whole stage chain.
                                       What stands in the way is this file itself: it links no
                                       compiled core and calls no reconstruction, so there is
                                       nothing here to run. Same reason for the two below.
  $217d8..$254c0  the depacked level overlay (OVALAY<stage>.RAD), which carries bg_tile_index at
                                       $21e90 and the map. `rad_depack` IS ported and verified, and
                                       this range too is computable; same reason for leaving it.
  $24898..       resource_table_header / the 20-byte sprite descriptors, and
  $25298..       the SPRITES.CRU cell data `sprites_cru_install` selects per stage. The routine IS
                                       ported. TWO things stand between that and a computed range:
                                       the resting extent is still not established anywhere, which
                                       is why the range is written open-ended, and the whole file
                                       does not fit the staged-file model (above).
  $44000..$70000 the eight $5800 pre-shifted scroll buffers. The builders ARE ported.
  $70000/$78000  the two 32000-byte screens.

So the M1 image can run the routines that read the PROGRAM, and it cannot run a frame.

**THE M2 IMAGE FABRICATES THE BOOT AND NOT THE DATA, AND THAT IS A DIFFERENT SENTENCE.** Every range
above is present in it, MEASURED off the shipped 1989 binary at `$f8b4` under Hatari — see
`atari/original.py` for the anchor, the three injections that stand in for a player, the two negative
controls that show the injections are what carry the boot there, and the mis-anchor measurement. What
remains fabricated is that nothing in THIS build produced them: this image is the boot's result handed
over rather than its result recomputed. That is now a statement about THIS FILE and not about what is
reconstructed — the chain that would produce them is composed and verified off target (batch 44 phase
C's `boot_load_stage`), and what would replace the dump is an on-target build that RUNS it. Until
that build exists the dump is the reference, and PROVENANCE below is the receipt.

AND WHAT IT DOES NOT MEASURE, because it is not the same twice: 512 bytes at $f314..$f514 are the
COPYLOCK'S RUN-TIME SCRATCH. The shipped file's bytes there disassemble as line-A words and
impossible operands; the protection overwrites them during the boot's first resource load, and
`original.py variance` shows it writes something DIFFERENT on every boot. So this band is one run's
accident inside the staged span rather than a measured product. It is inert — the region lies
between `copylock_illegal_handler` ($ee02) and `copylock_restore_state` ($f542), no reconstructed
function is inside it, and nothing under `../src/` reads there — and it is named here because an
image that calls itself the original's memory owes a list of which of its bytes are not.

==================================================================

THE SEEDS ARE A SET, and they are the only bytes here that are not the file's. Each is a word the
BOOT would have written and the shim must not be caught reading uninitialised; each is named with
what reads it, because an unexplained seed is indistinguishable from a fudge.

Usage: gen_image.py <SWB.PRG> <out/WB.IMG>
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "tools"))       # reverse/tools — the shared recreate kit
from recreate_kit import project                         # noqa: E402
project.load(HERE.parent)                                # recreate/ — binds the kit's loader
import loader                                            # noqa: E402

sys.path.insert(0, str(HERE.parent / "test"))            # ../test/layout.py scrapes the C headers
from layout import wb                                    # noqa: E402

sys.path.insert(0, str(HERE))                            # the anchor and the span it dumped
import original                                          # noqa: E402


def word(value):
    return bytes(((value >> 8) & 0xff, value & 0xff))


# THE SEED SET. Addresses come from ../include/wonderboy.h through layout.py rather than being
# written here, so a constant that moves in the C moves here (test/layout.py is the project's
# Python<->C single source of truth).
def seeds():
    return {
        # vbl_handler's own counter. The boot chain does not write it — it ships in the .PRG — but
        # the smoke's whole M1 assertion is "this word advanced by the number of vblanks", so it is
        # seeded to a known 0 rather than to whatever the file happens to hold.
        wb("VBL_COUNTER"): word(0),

        # ...and the countdown whose expiry is the ONE arm of vbl_handler that reaches the YM2149.
        # Seeded to a small value so the M1 run witnesses floppy_deselect_drives on a real chip;
        # smoke.py reads this same number out of the map below rather than restating it.
        wb("FLOPPY_IDLE_TIMER"): word(FLOPPY_IDLE_TICKS),

        # snd_music_tick_body's ENTRY GATE ($17ca0): it returns at once while the engine is disabled
        # and no SFX flag is up. That is the state a machine that has not started a song is in, and
        # it is what makes the M1 tick deterministic — the drop-value store above the gate still
        # happens, so the two REAL hardware reads still steer, but no music driver runs over a stage
        # this image does not contain.
        wb("SND_ENGINE_ENABLED"): bytes([wb("SND_ENGINE_DISABLED")]),
        wb("SND_SFX_ACTIVE_FLAGS"): bytes(wb("SND_SFX_ACTIVE_FLAGS_LEN")),
        wb("SND_TICK_DROP_ACC"): bytes(1),
        # The byte tempo_drop_value writes from the two real hardware reads. Seeded to a value that
        # is NONE of the three it can write ($00/$2b/$48), so "the tick ran and chose" is separable
        # from "the tick never ran" — a 0 seed would be indistinguishable from the 50 Hz answer.
        wb("SND_TICK_DROP_VALUE"): bytes([TICK_DROP_UNWRITTEN]),

        # The IKBD report byte the shim's ACIA handler files into. Cleared so that "a reply arrived"
        # is a change and not a coincidence — the same clr.b the game's own boot waits do ($e494).
        wb("JOY1_STATE"): bytes(1),

        # ...and the raw scancode byte beside it, which is the one `sched_wait8` spins on. The .PRG
        # ships it as 0 already; seeding it says so, because wonderboy_main.c uses zero as its
        # "the controller has not spoken" sentinel and a sentinel that rests on an unstated property
        # of the shipped image is a sentinel waiting to be wrong.
        wb("KEY_LAST_SCANCODE"): bytes(1),
    }


# vblanks before the idle timer expires. Small enough that a short run witnesses the expiry, and
# larger than 1 so that the DECREMENT arm is exercised and not only the fire.
FLOPPY_IDLE_TICKS = 5

# Not WB_SND_TICK_DROP_50HZ ($00), _60HZ ($2b) or _MONO ($48). $ff is outside the set of three, which
# is what makes it a witness rather than a value.
TICK_DROP_UNWRITTEN = 0xff


# ============================  THE M2 IMAGE'S PROVENANCE  ======================================
#
# WHERE EVERY BYTE OF THE DUMPED IMAGE COMES FROM, as an ASSERTION rather than as prose: the dump is
# compared against the relocated `SWB.PRG` over the program span, and each band below says what the
# comparison there must find. A band that stops behaving as described is a loud failure, which is
# what stops this table becoming a description of a file it no longer describes.
#
# The bands do not cover the whole image. Above PROGRAM_END the shipped file has nothing to compare
# against at all — that region IS the boot's product, and its being non-empty is checked separately.
FILE_ZEROS = "zero in the shipped file: the boot writes it, so every non-zero byte is measured"
# THE FIRST DRAFT OF THIS CAPTION CALLED THE BAND RECOVERED CODE, and `original.py variance`
# refuted it: the bytes are DIFFERENT after every boot and read as a descending, wrapping sequence —
# the protection's own trace samples, not anything it decrypted. So the band is one run's scratch and
# not data at all. (Described rather than quoted: a retraction that reproduces the old wording keeps
# it greppable for ever — docs/methodology.md.) Staged because the image is a span and this is inside
# it; inert because no reconstructed function lies between $ee02 and $f542 and nothing under ../src/
# reads there.
FILE_COPYLOCK_SCRATCH = "the copylock's run-time scratch, DIFFERENT every boot (original.py variance)"
# THIS ONE WAS WRITTEN AS `FILE_ZEROS` FIRST AND THE CHECK BELOW REFUSED IT, which is the whole
# reason the expectations are asserted rather than captioned: $217d8 is `startup_relocate_and_run` —
# the relocator that copied the body to $400 and jumped there — so the band is live program bytes,
# not padding. It is dead by the anchor (its one job is done before $400 is entered) and the overlay
# depacks straight over it, which is `../project.toml`'s "overlays depacking to 0x217d8, immediately
# after the body".
FILE_DEAD_RELOCATOR = "the spent relocator, which the overlay depack writes over"
GAME_VARIABLES = "the game's own variables, which live in holes in its code (it has no bss)"

PROVENANCE = (
    # (name, start, end, expectation). `end` of None runs to the end of the program span.
    ("bg_tile_bitmaps", 0x1d43e, 0x2103e, FILE_ZEROS),
    ("the copylock's scratch", 0xf314, 0xf514, FILE_COPYLOCK_SCRATCH),
    ("the overlay over the relocator", 0x217d8, None, FILE_DEAD_RELOCATOR),
)

# EVERYTHING THE NAMED BANDS DO NOT CLAIM, reported as one figure with a ceiling rather than as a
# fourth row. It was a row once, distinguished from the others by a `ceiling is not None` test and by
# being LAST — so the residue was whatever the rows above it happened not to have claimed, and
# reordering the table silently changed what it measured. It is now computed after the loop, where
# "the rest" is what the code says rather than what the ordering implies.
#
# These bytes vary with WHICH vblank the anchor fell on — the frame counter, the actor tables' free
# markers, the scroll cursors — so an exact count would be a fixture rather than a fact. What is
# asserted is that they stay a rounding error against the 136,408-byte program span; the measured
# figure is printed on every run and 373 was the reading when this was written.
RESIDUE_CEILING = 1024

# ...AND WHAT LIES ABOVE THE PROGRAM SPAN, which the band table cannot speak about at all: past
# PROGRAM_END the shipped file has nothing to compare against, so "differs from the file" is not
# defined there. That region IS the boot's product — the sprite pool, the eight scroll buffers, both
# screens — and it is the whole reason the dump exists, so its being NON-EMPTY is checked directly.
# An earlier draft of this file's prose claimed the check existed while nothing performed it: a dump
# truncated to the program span would have staged 380 KB of zeros and passed every band above.
#
# THE FLOOR IS MEASURED AND THE FIRST DRAFT'S WAS GUESSED — it was set to 0x40000 on an assumption
# about how full the region "should" be, and the very first run reddened a dump that was perfectly
# good. Measured: 198,359 of the 386,864 bytes above PROGRAM_END are set (the region is half empty by
# design — the scroll buffers are $5800 apart with $800 unused between them, and a stage's sprite
# pool does not fill its span). This floor is well under that and enormously over the ~0 a truncated
# or pre-boot dump would give, which is the failure it exists to catch.
BOOT_PRODUCT_MIN_NONZERO = 0x20000


def band_diffs(image, dump, lo, hi, start, end):
    start = lo if start is None else start
    end = hi if end is None else end
    return {i for i in range(max(start, lo), min(end, hi)) if image[i] != dump[i - lo]}


def report_provenance(image, dump, lo, hi, staged_end):
    """Check the dumped image against the shipped file, band by band. Returns the problems."""
    problems = []
    claimed = set()
    for name, start, end, expectation in PROVENANCE:
        found = band_diffs(image, dump, lo, hi, start, end)
        claimed |= found
        first, last = (lo if start is None else start), (hi if end is None else end)
        print(f"   {name} [{first:#x},{last:#x}): {len(found)} of {last - first} bytes "
              f"differ — {expectation}")
        if not found:
            problems.append(f"{name} is byte-identical to the shipped file, so the boot wrote "
                            f"nothing there and this dump did not run the chain it claims to")
        # THE EXPECTATION IS CHECKED, not captioned. A zeros band whose file bytes stopped being
        # zero would mean the band has moved onto real program content, and every "measured"
        # byte in it would then be overwriting something the .PRG shipped.
        if expectation is FILE_ZEROS and any(image[i] for i in range(first, last)):
            problems.append(f"{name} is not all zeros in the shipped file after all — the band "
                            f"names the wrong range, or the range now overlaps program content")

    residue = {i for i in range(lo, hi) if image[i] != dump[i - lo]} - claimed
    print(f"   {GAME_VARIABLES}: {len(residue)} of {hi - lo} bytes differ")
    if len(residue) > RESIDUE_CEILING:
        problems.append(f"{len(residue)} bytes differ outside the named bands, past the "
                        f"{RESIDUE_CEILING}-byte ceiling — see PROVENANCE's note")

    above = dump[hi - lo:staged_end - lo]
    set_bytes = sum(1 for byte in above if byte)
    print(f"   the boot's products above [{hi:#x},{staged_end:#x}): {set_bytes} of {len(above)} "
          f"bytes are non-zero — the tiles, the sprite pool, the scroll buffers and both screens")
    if set_bytes < BOOT_PRODUCT_MIN_NONZERO:
        problems.append(f"only {set_bytes} bytes above {hi:#x} are set, under the "
                        f"{BOOT_PRODUCT_MIN_NONZERO} this dump should carry — the boot chain did "
                        f"not run, or the dump was truncated to the program span")
    return problems


def stage_from_dump(dump_path, lo, staged_end):
    dump = Path(dump_path).read_bytes()
    want = staged_end - lo
    if len(dump) != want:
        raise SystemExit(f"{dump_path} is {len(dump)} bytes, expected {want} for "
                         f"[{lo:#x},{staged_end:#x}) — run `atari/original.py dump` again")
    return dump


def main():
    prg, out = sys.argv[1], sys.argv[2]
    from_dump = sys.argv[sys.argv.index("--dump") + 1] if "--dump" in sys.argv else None
    image = loader.load_image(prg)                       # also sets loader.PROGRAM_END
    lo, hi = loader.LOAD_BASE, loader.PROGRAM_END

    if from_dump:
        blob = stage_from_dump(from_dump, lo, original.GAME_SPAN_END)
        print(f"{out}: {len(blob)} bytes  [{lo:#x},{original.GAME_SPAN_END:#x})  "
              f"— the ORIGINAL's RAM at ${original.BOOT_ANCHOR_PC:x}, no seeds")
        problems = report_provenance(image, blob, lo, hi, original.GAME_SPAN_END)
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
    else:
        for addr, data in sorted(seeds().items()):
            if not (lo <= addr and addr + len(data) <= hi):
                raise SystemExit(f"seed {addr:#x}+{len(data)} falls outside the staged block "
                                 f"[{lo:#x},{hi:#x}) — the .PRG would never receive it")
            image[addr:addr + len(data)] = data
        blob = bytes(image[lo:hi])
        print(f"{out}: {len(blob)} bytes  [{lo:#x},{hi:#x})  + {len(seeds())} seeds")

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(blob)


if __name__ == "__main__":
    main()
