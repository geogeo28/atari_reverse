"""The ASM-TWIN differential for the frame loop's DRAW-AND-COLLIDE STAGE: `../src/asm/frame_draw.S`
must leave the image byte-for-byte where its C core in `../src/frame.c` leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_frame.py` pins the C core against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_frame.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_frame.py`'S STAGING, IMPORTED RATHER THAN RESTATED — its `world` (which has the
ORACLE play a section before a case starts) and its poke builders. Importing it also installs this
battery's `ctypes` signatures for the five frame glues, which is why nothing here declares them
again. The door table, the candidate arming and the three source-reading pins are the FAMILY's and
live in `asm_frame_common.py`, whose header says why.

WHAT IS THIS TWIN'S OWN, against its four wave-C/wave-D siblings.

**1. IT IS THE ONE FRAME TWIN WITH A BYTE PIN.** `object_pair_overlap_mark`'s tail
[0x11cfe, 0x11d30) names no global, carries no immediate-to-Dn operation and — because this twin
reserves `%a0` rather than the family's `%a5` — permutes no register, so those fifty bytes ARE the
original's own machine code. `test_the_pair_tail_is_the_originals_own_bytes` compares them. The
other four frame twins have no span with all three properties and say so in their headers; this one
was laid out to have one.

**2. ITS WINDOW REGISTER IS `%a0`, NOT `%a5`**, which is why every family scraper here is passed
`WINDOW_REGISTER`. The slice uses all seven address registers, so the reconstruction's extra base
had to come out of the one live-range gap there is — `frame_draw.S`'s register map has the
argument. The scan's positive control below is what would say so if that ever stopped matching.

**3. NO ENTRY REGISTERS AND NO ANSWER.** The stage takes the image alone and its C is `void`, so
`expect_ret=common.VOID_STAGE`. What stands in place of an answer surface is that every case asserts
the C wrote something (the family differential does that) and that the cases below reach the arms
by staging, not by hope — `test_the_cases_reach_the_pair_walk` is the control that says the
all-pairs sweep, which is the whole reason this twin exists, actually ran.

**4. THE COST BANDS ARE THE POINT OF THE WAVE**, and unlike wave D's they are read on TWO worlds: a
busy frame and a quiet one. This stage's cost is a function of how many entities are on screen, and
a single band would have hidden exactly the effect the twin was written for. See the cost section.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import asm_twins
import asm_frame_common as common
import test_frame as frame
from recreate_kit.asm_twin import ASM_LINK_BASE

DRAW_S = common.ASM_DIR / "frame_draw.S"

TWIN = "frame_draw_objects_and_collide_asm"
# The span of the original this twin transcribes. Its end is the next slice's entry, which is also
# the `bra` the stage leaves through — it has no `rts` of its own.
ORIGINAL_ENTRY = frame.ENTRY_DRAW_AND_COLLIDE         # 0x11c00
ORIGINAL_END = frame.ENTRY_RESOLVE                    # 0x11d30

# This twin's base register — see the module header, point 2, and frame_draw.S's register map.
WINDOW_REGISTER = "%a0"

# The entity table, as this stage walks it — `test_frame.py`'s own constants, which its `MIRRORS`
# already pin against include/entity.h and include/frame.h. Restating the four numbers here (an
# earlier draft did, two lines below a working import of them) would have put a fourth, UNPINNED
# spelling in the file: this suite is not a `test_<stem>.py` for any `src/<stem>.c`, so
# test_constants.py's battery pins do not reach it and nothing would have said so.
ENTITY_STRIDE = frame.ENTITY_STRIDE
ENTITY_ALIVE = frame.ENTITY_ALIVE
ENTITY_PIXEL_HIT = frame.ENTITY_PIXEL_HIT
ENTITY_SLOTS = frame.ENTITY_SLOTS


def entity_record(slot):
    return frame.A_ENTITY_TABLE + slot * ENTITY_STRIDE


def leaves_the_image_where_the_c_does(world, extra=None):
    """This stage's arguments to the family's differential (`asm_frame_common`, which says what its
    three assertions are and what each one closes).

    There is nothing of this suite's own in the shores but their simplicity: the stage takes the
    image and nothing else, and answers nothing.
    """
    return common.leaves_the_image_where_the_c_does(
        TWIN, world, extra,
        c_call=lambda lib, buf: lib.g_frame_draw_objects_and_collide(buf),
        twin_args=(), expect_ret=common.VOID_STAGE)


# ============================================================ the game, played

# THE WORLDS THIS SUITE USES, and the pair is the point rather than a convenience. `busy` is a frame
# the oracle played into with every one of the eleven actor slots live; `quiet` is an earlier frame
# of the same section with four. The stage's cost — and its all-pairs walk's very existence — depend
# on which, so a suite that used one world would be testing half the routine. `frame.world` is
# `functools.lru_cache`d, so naming them as functions costs nothing per case.
#
# `quiet` IS NOT THE QUIETEST FRAME THERE IS, and the reason is a real property of the stage rather
# than a convenience: measured over section 0, every frame before the first wave arrives writes
# ZERO bytes — the few live records are static scenery whose pixels are already in the buffer being
# drawn into, so the sprite pass changes nothing and the mask-table clear clears zeros. The family
# differential refuses such a case outright ("the C core wrote nothing"), and rightly: two untouched
# images compare equal. Frame 60 is the lightest one that still draws.
BUSY_FRAMES = 141          # where atari/census.py's section-0 sweep finds 11 of 11 actor slots live
QUIET_FRAMES = 60          # ...and the lightest frame of the same section that still DRAWS


def busy_world():
    return frame.world(0, BUSY_FRAMES)


def quiet_world():
    return frame.world(0, QUIET_FRAMES)


@pytest.mark.parametrize("world", ("busy", "quiet"))
def test_the_twin_matches_the_c_over_a_played_frame(world):
    """The differential over both worlds, which between them drive every arm the stage has: the
    sprite pass over all twenty slots, the mask-table clear, and — on the busy world — the
    all-pairs walk with its `bsr` into the transcribed pair body."""
    leaves_the_image_where_the_c_does(busy_world() if world == "busy" else quiet_world())


# ...and it STOPS one short of BUSY_FRAMES, because `test_the_twin_matches_the_c_over_a_played_frame`
# already stages that world: an inclusive range made the two cases identical, which is a full 1 MiB
# differential run (C core and twin) for a second copy of one assertion.
@pytest.mark.parametrize("frames", tuple(range(BUSY_FRAMES - 6, BUSY_FRAMES)))
def test_the_twin_matches_the_c_over_the_busy_stretch(frames):
    """Seven consecutive frames of the busiest stretch the oracle plays into, each its own world.

    A SWEEP RATHER THAN ONE FRAME, because the pair walk's shape changes frame to frame with which
    records the blitter marked: one staged frame exercises one set of overlaps, and the arms that
    matter here are "this pair rejected on the first compare" against "this pair marked both rows".
    """
    leaves_the_image_where_the_c_does(frame.world(0, frames))


def test_the_cases_reach_the_pair_walk():
    """THE POSITIVE CONTROL FOR THE WHOLE SUITE, and without it every case above could be green over
    a stage that never ran the routine this twin exists for.

    The all-pairs walk only calls `object_pair_overlap_mark` for a `left` the sprite pass marked,
    and the sprite pass only marks a record that was drawn and overlapped something. So a world with
    nothing on screen takes the stage's `beq` at 0x11c7c nineteen times (the outer walk is
    `left = 1..19`) and the pair body — 35 of the twin's 86 instructions, and the only span with a
    byte pin — is never entered.

    This asserts the busy world really does reach it, by counting the pairs the walk would call
    over the image as it stands AFTER the sprite pass (which is what sets the flags it reads), run
    by the ORACLE so the count is the original's own and not a restatement of ours.
    """
    image = harness.make_image(frame.world_pokes(busy_world()))
    after_sprites, _writes, _regs = emu.run(bytearray(image), ORIGINAL_ENTRY, {},
                                            stop_pc=SPRITE_PASS_END_PC,
                                            max_insns=frame.FRAME_MAX_INSNS)
    pairs = sum(1
                for left in range(1, ENTITY_SLOTS)
                if after_sprites[entity_record(left) + ENTITY_PIXEL_HIT]
                for right in range(left)
                if after_sprites[entity_record(right) + ENTITY_ALIVE])
    assert pairs >= MIN_PAIRS_THE_BUSY_WORLD_WALKS, (
        f"the busy world walks only {pairs} ordered pair(s), so the transcribed "
        f"`object_pair_overlap_mark` body is barely reached and every differential above is passing "
        f"over the arm this twin was written for. Re-stage it — atari/census.py finds the busiest "
        f"frame of a section")


# Where the original's sprite pass ends and its collision walk begins — the `move.w #$14,d0` that
# starts the mask-table clear. Read by the control above so it can see the flags the sprite pass set.
SPRITE_PASS_END_PC = 0x11c56
# What "the busy world really is busy" means, from the measurement rather than from a wish: the
# frame atari/bench_tier.py prices walks 51 pairs. A floor well under that still fails loudly if the
# staging drifts to a quiet frame, without breaking every time the oracle's play shifts by one.
MIN_PAIRS_THE_BUSY_WORLD_WALKS = 20


# ============================================================ reading frame_draw.S back

# The scrapers are the family's (`asm_frame_common`), and they resolve this twin's object from its
# source path themselves. What stays here is what is THIS file's: which span of the original, which
# base register, and the counts below.
WINDOWED_OPERAND_COUNT = 7


def test_the_window_scan_reads_every_global_this_twin_names():
    """The scan's positive control. `window_pin_failures` is vacuous over an empty operand list, so
    a twin whose operand shape stopped matching — a different window register, a differently named
    origin — would pass the pin below by reaching no globals at all. It is doubly worth having here:
    this is the one frame twin whose register is not the family's `%a5`, so a scraper called without
    `WINDOW_REGISTER` finds nothing and says everything is fine."""
    failure = common.window_scan_failure(DRAW_S, WINDOWED_OPERAND_COUNT, WINDOW_REGISTER)
    assert failure is None, failure


def test_every_windowed_global_is_inside_the_signed_displacement():
    """THE WHOLE OF WHAT MAKES `%a0 = image + FGB` LEGAL for this twin: a global outside the signed
    16-bit window is one gas refuses outright, and this says which global and how far out before the
    build does."""
    failures = common.window_pin_failures(DRAW_S, WINDOW_REGISTER)
    assert not failures, "\n".join(failures)


def test_the_box_width_equate_is_collision_cs_own():
    """THE ONE `.equ` IN THIS TWIN THAT test_constants.py CANNOT PIN, pinned here instead.

    `test_asm_twin_equates_match_the_headers` only covers `.equ` names that an `include/*.h` also
    defines. `OBJECT_BOX_WIDTH` is `src/collision.c`'s own `#define`, so that pin skips it — in
    SILENCE, which is the exact failure its own docstring says it exists to prevent. The twin uses
    it twice, at 0x11cf2 and 0x11cfa, both OUTSIDE the byte-pinned tail.

    What would go wrong without this: someone widens the box in `src/collision.c` (a real
    collision-tuning edit), `test_collision.py`'s mirror moves with it, and the twin keeps
    `add.w #$10`. The two shores then disagree only on pairs whose x-gap falls in the widened band —
    which the staged worlds may simply never produce. Green suite, wrong collisions on target.
    """
    equates = common.equates(common.asm_object_for(DRAW_S))
    assert BOX_WIDTH_EQUATE in equates, (
        f"src/asm/frame_draw.S no longer declares `.equ {BOX_WIDTH_EQUATE}` — if the twin stopped "
        f"naming the box width, this pin is testing nothing")
    source = (common.REC / "src" / "collision.c").read_text()
    marker = f"#define {BOX_WIDTH_EQUATE} "
    assert marker in source, (
        f"src/collision.c no longer defines {BOX_WIDTH_EQUATE}; it is the canonical spelling the "
        f"twin's `.equ` is pinned against, so say where it went")
    expected = int(source[source.index(marker) + len(marker):].split()[0].rstrip("uU"), 0)
    assert equates[BOX_WIDTH_EQUATE] == expected, (
        f"src/asm/frame_draw.S assembles {BOX_WIDTH_EQUATE} as "
        f"{equates[BOX_WIDTH_EQUATE]:#x}, but src/collision.c defines it as {expected:#x} — the "
        f"twin's box test and the C's would disagree on exactly the pairs in between")


# `src/collision.c`'s own `#define`, which is why it needs the pin above rather than test_constants'.
BOX_WIDTH_EQUATE = "OBJECT_BOX_WIDTH"


def test_the_twin_transcribes_the_original_instruction_for_instruction():
    """EVERY INSTRUCTION OF THE ORIGINAL, ONCE, IN ORDER — and this stands where the byte pin cannot
    reach, which for this twin is the 65 instructions outside the pinned tail (the tail is 50 BYTES
    and 21 instructions; the twin is 86 in all).

    It catches what a differential cannot: an instruction dropped on a path the game's own data
    never takes, one transcribed twice, an arm moved in front of another, a comment left naming an
    address the line no longer transcribes.
    """
    failure = common.transcription_failure(DRAW_S, ORIGINAL_ENTRY, ORIGINAL_END)
    assert failure is None, failure


# ---- the byte pin, which no other frame twin has ----

# The span of the original whose bytes the twin reproduces exactly, and the two `.globl` labels that
# bracket it in the assembled blob. See the module header, point 1.
PAIR_TAIL_LO, PAIR_TAIL_HI = 0x11cfe, 0x11d30
PAIR_TAIL_BODY = "frame_draw_pair_tail_body"


def test_the_pair_tail_is_the_originals_own_bytes():
    """FIFTY BYTES — 21 instructions — THAT ARE NOT A TRANSCRIPTION BUT A COPY: the four signed
    rejections and the reciprocal mark of `object_pair_overlap_mark`, which the busy frame runs
    fifty-one times.

    This is the strongest check any frame twin has, and it exists because of a layout choice rather
    than luck: the span names no global (so position-independence does not re-encode it), carries no
    immediate-to-Dn operation (so gas's ANDI/CMPI re-spelling does not reach it — see
    src/asm/README.md, "What wave B added") and keeps the original's own `%a3`-`%a6` (so no
    permutation changes a register field). Break any one of those three and this test is what says
    so.
    """
    blob = common.twins()
    lo = blob.entry(PAIR_TAIL_BODY) - ASM_LINK_BASE
    hi = blob.entry(PAIR_TAIL_BODY + "_end") - ASM_LINK_BASE
    ours = blob.bin.read_bytes()[lo:hi]
    theirs = harness.BASE_IMAGE[PAIR_TAIL_LO:PAIR_TAIL_HI]
    assert hi - lo == PAIR_TAIL_HI - PAIR_TAIL_LO, (
        f"the twin's pinned span is {hi - lo} bytes and the original's is "
        f"{PAIR_TAIL_HI - PAIR_TAIL_LO} — an instruction was added or dropped inside the bracket")
    assert ours == theirs, (
        "the twin's pair tail is no longer the original's own machine code:\n"
        + "\n".join(f"  +{at:#04x}: original {theirs[at]:#04x}, twin {ours[at]:#04x}"
                    for at in range(len(theirs)) if theirs[at] != ours[at]))


def test_no_two_globals_share_the_pinned_brackets_address():
    """WAVE B'S LESSON 4, ASKED OF THIS FILE. A `_body_end` label sits at the first byte PAST the
    span, and if the next thing in the file starts there the two names share an address —
    `atari/profile.py` resolves a profiled call by address and reports it by name, so a whole
    routine's cycles come back under the bracket label and the routine has no row at all.

    Here the epilogue lies between the bracket and the next `.globl`, so they differ; this asserts
    it rather than assuming it, because the gap is one edit wide.
    """
    blob = common.twins()
    at = blob.entry(PAIR_TAIL_BODY + "_end")
    sharing = sorted(name for name, address in blob.symbols.items()
                     if address == at and name != PAIR_TAIL_BODY + "_end")
    assert not sharing, (
        f"{PAIR_TAIL_BODY}_end shares its address with {', '.join(sharing)} — a profiler row for "
        f"either will be reported under one name and the other will have none")


# ============================================================ what the twin COSTS

# READ THIS BEFORE READING A RATIO HERE.
#
# THE DOOR CHARGES NOTHING FOR A C BODY (`asm_frame_common`'s door, and test_asm_frame_fire.py's
# cost note says it at length): off target the twin's `jsr` to `asteroids_draw` stops the run, the
# harness calls the host C and resumes, so the core's body costs the emulated machine nothing, while
# the ORIGINAL executes its own `bsr $159be` in full. Two of this twin's three callees are doors.
#
# WHAT MAKES THESE BANDS DIFFERENT FROM WAVE D'S, and why they are the point of the wave rather than
# a formality: THE THIRD CALLEE IS NOT A DOOR. `draw_sprite_masked_collide_asm` is in this same blob
# and really executes on both sides, and it is the largest single thing the stage does. So the
# ratios below are dominated by work both shores actually perform, which is what a cost pin wants.
#
#   world   sprites   original     twin   excess   measured      bar   slack
#   busy         14     91,038   95,146   +4,108     1.0451   1.0452   7 cyc
#   quiet         8     46,970   49,514   +2,544     1.0542   1.0543   7 cyc
#
# THE EXCESS IS THE SPRITE SEAM AND NOTHING ELSE, and the two bands are what SAY so rather than a
# claim about them: +4,108 over fourteen calls and +2,544 over eight is ~295 and ~318 cycles a
# call, and there is no other per-call term in the stage. `draw_sprite_masked_collide_asm` carries a
# C signature, so this twin's trampoline turns two pointers into image offsets and that twin's
# prologue turns them straight back into pointers.
#
# IT IS THE NEXT LEVER RATHER THAN A DEFECT. The C this twin replaces paid that same seam AND
# 31,966 cycles of loop-and-glue on top of it: on the busy frame the C is 132,094 against the twin's
# 95,146, so the twin collects 36,948 and leaves 4,108. Closing the rest needs a second,
# register-ABI entry point in sprite.S — a change to a shipped and pinned twin, deliberately not
# made in this wave. STATUS.md carries it.
#
# THE BARS ARE SET FROM THE MEASUREMENT with a margin in CYCLES, not percent (src/asm/README.md,
# "one bar that moved"): ~7 cycles on each, so one extra register in the prologue's `movem` pair
# (16 cycles round trip) reddens both. Both readings are deterministic — Musashi counts cycles and
# `frame.world` is the oracle's own output — so the margin is for a legitimate re-translation, not
# for noise.
COST_BARS = {"busy": 1.0452, "quiet": 1.0543}


def _cost_case(world, band):
    """Clock the ORIGINAL and the twin over one staged world, and hold the twin to that band's bar.

    The twin goes through the differential on the way, so a cost reading can never be taken from a
    call that computed the wrong thing.
    """
    run = leaves_the_image_where_the_c_does(world)
    image = harness.make_image(frame.world_pokes(world))
    _final, _writes, regs = emu.run(bytearray(image), ORIGINAL_ENTRY, {},
                                    stop_pc=ORIGINAL_END, max_insns=frame.FRAME_MAX_INSNS)
    # The shared assertion, not a local restatement of it.
    asm_twins.assert_within_the_bar(f"{TWIN} ({band})", regs["cycles"], run.cycles,
                                    COST_BARS[band])


def test_the_twin_costs_what_it_costs_on_a_busy_frame():
    """THE READING THE WAVE WAS COMMISSIONED ON: eleven of eleven actor slots live, fourteen sprites
    drawn and fifty-one ordered pairs walked. This is the frame a player feels and the one every
    averaged instrument before `atari/bench_tier.py` hid."""
    _cost_case(busy_world(), "busy")


def test_the_twin_costs_what_it_costs_on_a_quiet_frame():
    """The control, and it is not a formality. Half the sprites and no pair walk worth the name, so
    the stage's absolute cost roughly halves — and the twin's own excess halves with it, +2,544
    against +4,108, which is what says the excess is PER SPRITE CALL rather than a fixed frame cost.
    A single band could not distinguish those two, and they suggest opposite next moves."""
    _cost_case(quiet_world(), "quiet")
