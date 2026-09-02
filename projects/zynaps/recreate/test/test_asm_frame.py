"""The ASM-TWIN differential for the frame loop's LAST STAGE: `../src/asm/frame.S` must leave the
image byte-for-byte where its C core in `../src/frame.c` leaves it, and answer with the same
`frame_exit`.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_frame.py` pins the C core against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_frame.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_frame.py`'S, IMPORTED RATHER THAN RESTATED — its world staging (`world`, which
has the ORACLE play a section for four frames before a case starts), its poke builders and its fuzz
generator. Importing it also installs this battery's `ctypes` signatures for the five frame glues,
which is why nothing here declares them again.

WHAT IS DIFFERENT ABOUT THIS TWIN, and why this file carries more machinery than its neighbours.

**1. It CALLS SIXTEEN VERIFIED C CORES**, through the kit's callback door (`asm_twin.py`'s DOOR_BASE
and TRAP_MODEL.md, "The callback door"). A door needs a TABLE, and `asm_twins.py`'s module-level
singleton is built without one — a frame case run through it would jump into the band, execute the
zeros there and die as a sentinel timeout naming neither the door nor the callee. So this suite
builds its own `AsmTwins` with DOOR_TABLE below, and — because `asm_twins.matches_the_c` reaches for
that singleton rather than taking a blob — carries its own differential in `leaves_the_image_where_
the_c_does`. That function is `matches_the_c` plus the two things a frame case needs and a leaf case
does not: its own blob, and the candidate arming below. `asm_twins.py` itself is left alone.

**2. BOTH SIDES NEED THE CANDIDATE ARMED.** The stage ends on two busy-waits and a `bset` of the
MFP, which off target go through the kit's scheduled-write and hardware models — and those models
live in the candidate `.so`, which the twin reaches through the SAME door. `harness.differential`
arms them before its one candidate run; a twin case makes TWO (the C core, then the twin), so
`arm_the_candidate` is called before each. Without it the ACIA status reads undeclared, the send
loop spins to its cap and the run is a refusal rather than a comparison — measured, and it is why
every case asserts the refusal tally as well as the image.

**3. THERE IS NO BYTE PIN, and the reason is in `frame.S`'s header**: the stage names sixty-six
globals and the reconstruction is position-independent, so `tst.b $19aad.l` becomes
`tst.b A_boss_sequence_active-FGB(%a5)` — a different encoding, a different length, in almost every
instruction of the file. `frame.S` has no `_body_end` bracket labels for a byte pin to use and no
span it could pin: the starfield's three loops and the two explosion passes' loops, which its header
names as the pinnable ones, each reload `A_screen_back`, `A_starfield_pixel_masks` or
`A_explosion_*_frame_ptrs` base-relative, so none of them is the original's own bytes. What stands
in its place is `test_the_twin_transcribes_the_original_instruction_for_instruction`, which is
strictly about ORDER and COMPLETENESS rather than about encoding, plus the cost pins and the
differential.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import functools
import random
import re
from pathlib import Path

import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import loader
import asm_twins
import test_frame as frame
from recreate_kit import harness as kit_harness
from recreate_kit.asm_twin import AsmTwins, DoorCallback, elf_symbols

REC = Path(__file__).resolve().parents[1]
FRAME_S = REC / "src" / "asm" / "frame.S"
FRAME_OBJ = REC / "build" / "asm" / "frame.o"
PRG_DIS = REC.parent / "out" / "prg_dis.txt"

TWIN = "frame_resolve_hits_and_game_state_asm"
# The span of the original this twin transcribes, and the register the frame loop enters it with.
ORIGINAL_ENTRY = frame.ENTRY_RESOLVE                  # 0x11d30
ORIGINAL_END = 0x1296e                                # one past the `bra.w $10f4e` at 0x1296a
SOUND_CHANNEL = frame.ENTITY_SLOTS                    # D0 on entry — src/frame.c's `sound_channel`


# ============================================================ the callback door

# THE SIXTEEN C CORES THE TWIN CALLS, plus the two kit seams that can only ever be host code.
#
# `nargs` INCLUDES the image pointer wherever `takes_image` is true, and every row here is the
# core's own C prototype in ../include or in tools/recreate_kit/include — `sched_wait8(image, addr,
# until, site_pc)` and `hw_bset8(addr, bit)`. The SLOT NUMBERS are `frame.S`'s `.equ ZY_DOOR_*` and
# are pinned against it by `test_the_door_slots_are_the_ones_the_twin_jumps_to`, so this table and
# the assembly cannot drift apart in silence: a table that renumbered would send every case to the
# wrong host function with nothing but a diff to say so.
#
# `returns=False` is a core declared `void`. The door then POISONS D0 rather than publishing the
# host's arbitrary return register, so a stub that branched on a value the machine leaves undefined
# fails here instead of flaking on target.
#
# `takes_image=False` is the two that touch HARDWARE rather than the image: their argument 0 is a
# register address, and substituting a host pointer over it would corrupt exactly the value they
# need.
DOOR_TABLE = {
    0: DoorCallback("collision_chain_walk", 2),
    1: DoorCallback("score_add_bcd", 3),
    2: DoorCallback("enemy_morph_to_type6", 2, returns=False),
    3: DoorCallback("ship_resolve_entity_hits", 3, returns=False),
    4: DoorCallback("entity_type_is_lockable", 2),
    5: DoorCallback("powerup_downgrade_on_death", 1, returns=False),
    6: DoorCallback("bomb_update", 3, returns=False),
    7: DoorCallback("ikbd_send_cmd", 1, takes_image=False, returns=False),
    8: DoorCallback("mothership_segment_hit", 2),
    9: DoorCallback("explosion_spawn", 3, returns=False),
    10: DoorCallback("shot_retire_kind32", 3),
    11: DoorCallback("shot_retire_kind36", 2),
    12: DoorCallback("shot_retire_kind33", 3),
    13: DoorCallback("sound_start", 3, returns=False),
    14: DoorCallback("screen_flip_buffers", 1, returns=False),
    15: DoorCallback("game_over_screen", 1, returns=False),
    16: DoorCallback("sched_wait8", 4),
    17: DoorCallback("hw_bset8", 2, takes_image=False, returns=False),
}

_TWINS = None


def twins():
    """The assembled blob with THIS project's door table, loaded once per worker.

    Its own instance rather than `asm_twins.twins()`: that one is shared by the leaf suites and is
    built with no table at all (this file's header says what happens to a frame case run through
    it). `AsmTwins.require()` raises with the build command if the twins were never assembled —
    LOUD rather than skipped, since a skip would look like coverage.
    """
    global _TWINS
    if _TWINS is None:
        _TWINS = AsmTwins(REC / "build" / "asm", loader.IMAGE_SIZE,
                          callbacks=DOOR_TABLE, lib=harness._lib)
    return _TWINS


# The stage's two busy-waits, flattened once into the pair of arrays both models take. Spelt from
# `test_frame.py`'s own FRAME_SCHED/WAIT_SITES so the twin's waits are released exactly where the C
# battery releases them.
SCHEDULE = emu.schedule_entries(list(frame.FRAME_SCHED))
WAIT_SITES = emu.wait_site_pcs(list(frame.FRAME_SCHED), list(frame.WAIT_SITES))


def arm_the_candidate():
    """Everything `harness.differential` installs before a candidate run, done here for BOTH runs.

    The four models the stage reaches are GLOBAL STATE in the candidate `.so`, and each is left
    consumed by the run that used it — the schedule's entries fired, the wait sites' poll counts
    spent, the ledgers full. Re-arming between the C run and the twin's is therefore not hygiene but
    the comparison itself: an unarmed second run would poll to `OS_SCHED_POLL_MAX`, skip the flip
    and differ from the first for a reason that has nothing to do with the transcription.

    `_seed_candidate_hw(None)` is the one that looks like a no-op and is not: `g_hw_reset` is what
    installs `os.h`'s model DEFAULTS, and the ACIA's "transmitter empty" is one of them. Never
    called, the byte reads undeclared, `ikbd_send_cmd` spins to `IKBD_TX_POLL_MAX` and tallies
    seventeen refusals — measured.

    `kit_harness.arm_candidate` IS `differential`'s own block, made public for this caller — so the
    day the kit grows a fifth model to arm, this suite gets it. A hand copy here would stay green
    without it: both shores of THIS comparison would be armed by the same stale block, symmetric and
    wrong, and the byte diff would prove nothing while reporting success.
    """
    kit_harness.arm_candidate(scheduled=SCHEDULE, sites=WAIT_SITES)


# ============================================================ the differential

# `include/frame.h`'s enum, mirrored for the cases to name their arm by. Pinned against the header
# AND against frame.S's own `.equ`s by `test_the_exit_enum_is_the_headers`.
FRAME_EXIT_TITLE = 0
FRAME_EXIT_RELOAD_SECTION = 1
FRAME_EXIT_RESTART_SECTION = 2
FRAME_EXIT_ADVANCE_SECTION = 3
FRAME_EXIT_NEXT_FRAME = 4


def leaves_the_image_where_the_c_does(world, extra=None, expect=FRAME_EXIT_NEXT_FRAME,
                                      refusal_free=True):
    """The whole differential: the twin and its C core over one staged world, compared whole.

    Three assertions, and each closes a hole the other two leave:

      the IMAGE      all 1 MiB of it, so a byte the twin computes differently anywhere fails here.
                     The C is asserted to have CHANGED the image first — this stage always writes
                     (the starfield alone repaints eighteen stars), so a case in which it wrote
                     nothing is a staging fault, and two untouched images would compare equal.
      the EXIT       `%d0` against the C's return. This stage is the one twin in the project whose
                     answer is control flow: the original `bra`s to one of five addresses and the
                     twin answers with `include/frame.h`'s enum for it, so an arm that returned the
                     wrong value would leave a perfect image (`frame.S`, "THE EXITS").
      the REFUSALS   both sides made the SAME number of refused `os_*` calls. A refused call means
                     the TOS model declined to serve the candidate and the run tested nothing —
                     `harness._vet_no_os_refusal`'s argument, one shore over. `refusal_free=False`
                     is for a case whose refusals are a shared C CORE's rather than the twin's; the
                     equality still holds and the count is then the control.

    `expect` is DECLARED rather than read back, so a case that staged the wrong world fails saying
    which arm it wanted instead of quietly agreeing with itself.
    """
    image = harness.make_image(frame.world_pokes(world, extra))

    arm_the_candidate()
    buf = harness.candidate_image(image)
    c_exit = harness._lib.g_frame_resolve_hits_and_game_state(buf, SOUND_CHANNEL)
    c_image, c_refusals = bytes(buf), harness._lib.g_os_refusal_count()
    assert c_image != bytes(image), (
        "the C core wrote nothing, so comparing the twin against it tests nothing — the case is "
        "staged wrong or the glue was not called")
    assert c_exit == expect, (
        f"the C core left through {c_exit}, not the {expect} this case says it stages")

    arm_the_candidate()
    run = twins().call(image, TWIN, SOUND_CHANNEL)
    twin_refusals = harness._lib.g_os_refusal_count()

    if run.image != c_image:
        diffs = [(at, c_image[at], run.image[at])
                 for at in range(len(c_image)) if c_image[at] != run.image[at]]
        pytest.fail(f"{TWIN} diverges from the C core in {len(diffs)} bytes (C, then asm)\n"
                    f"{harness.report(diffs)}")
    assert run.d0 == c_exit, (
        f"{TWIN} answered frame_exit {run.d0}, the C core {c_exit} — the image is identical, so "
        f"this is an exit arm returning the wrong enum and nothing else here can see it")
    assert twin_refusals == c_refusals, (
        f"the twin made {twin_refusals} refused os_* call(s) and the C core {c_refusals} — the two "
        f"shores did not run the same models, so the byte comparison above proves nothing")
    if refusal_free:
        assert c_refusals == 0, (
            f"{c_refusals} refused os_* call(s) — the TOS model declined to serve the candidate, so "
            f"neither side was tested. {kit_harness.refusal_hints()}")
    return run


# ============================================================ the game, played

@pytest.mark.parametrize("section", range(frame.SECTION_COUNT))
def test_the_twin_plays_the_game(section):
    """The stage, frame by frame, over each of the sixteen sections the game ships.

    THIS IS THE COMPOSITION TEST. Each frame runs the twin's seven hundred instructions and nine or
    ten door calls over the whole 512 KB the game owns, against the C that `test_frame.py` has
    already proved equal to the original on these exact worlds — so a pass that ran a loop once too
    often, took a branch the other way or reloaded a base inside a loop differs on real pixels.

    The sections are not interchangeable: four are asteroid fields with no map, and which alien bank
    and which ground target a section loads is the level designer's choice.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for _ in range(frame.WORLD_FRAMES):
        leaves_the_image_where_the_c_does(image)
        image = frame.advance_one_frame(image)


@pytest.mark.parametrize("section", frame.FUZZ_SECTIONS)
def test_the_twin_fuzz(section):
    """`test_frame.py`'s own 96-case generator, replayed against the twin.

    What it reaches that the sweep above does not is the COMBINATION: six shot slots each alive or
    dead and of five kinds, eight enemy slots each of ten types with a real collision row — which is
    the 6x8 double loop at 0x122f4 and the two pairwise dispatches under it, the largest single
    piece of the twin and the one no dozen frames of one section can walk.

    Sharded by section for `test_frame.py`'s reason: a case's cost is dominated by building its
    world, which `frame.world` caches per worker.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for case in frame.fuzz_cases_for(section):
        leaves_the_image_where_the_c_does(
            image, frame.fuzz_pokes(random.Random(0x11d30 + case), image))


# ============================================================ the five exit arms

def test_the_twin_leaves_through_the_ordinary_exit():
    """FRAME_EXIT_NEXT_FRAME, the arm every frame of the sweep above takes: `bra.w $10f4e` at
    0x1296a, the last instruction of the transcribed span."""
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START),
                                      expect=FRAME_EXIT_NEXT_FRAME)


@pytest.mark.parametrize("lives,other_lives,other_section,expect",
                         ((3, 2, 0, FRAME_EXIT_RESTART_SECTION),
                          (3, 2, 5, FRAME_EXIT_RELOAD_SECTION),
                          (0xff, 1, 0x0f, FRAME_EXIT_RELOAD_SECTION)))
def test_the_twin_leaves_through_the_two_player_swap(lives, other_lives, other_section, expect):
    """The ship-death arm, on `test_frame.py`'s own pokes: spend a life, save this player's fourteen
    bytes, swap and read the other player's back — then leave through whichever address the resumed
    section decided. Same section restarts in place (0x10b6e), a different one reloads (0x1083a)."""
    image = frame.world(0, frame.WORLD_START)
    leaves_the_image_where_the_c_does(
        image, frame.ship_death_pokes(image, lives, other_lives, other_section), expect=expect)


# The swap loop leaves through 0x10500 on its THIRD pass, and reaching a third pass means every
# player record it read held a zero life count — which the loop itself wrote, from the byte
# `subi.b #$1,$1991a` had just decremented. So the arm needs the life count to hit zero, and that is
# the run `beq 0x12786` sends through `game_over_screen` first.
#
# WHICH IS WHY `test_frame.py` CANNOT DRIVE IT AND THIS FILE CAN, and the difference is which shores
# a case has to satisfy. `test_frame.py` compares the C against the ORACLE, so both sides run the
# high-score entry — eight distinct busy-wait sites where `os.h`'s OS_SCHED_SITE_MAX carries four,
# with the frame's own two already spent. This file compares the C against the TWIN, and both of
# them reach that routine through the SAME door into the SAME host C: the polls it makes at
# undeclared sites are refused identically on both shores, which is what `refusal_free=False` says
# and what the refusal-equality assertion turns into the control. What the case still pins is
# everything the twin owns — the swap loop's own instructions, `cmp.b #$3,%d7` and the enum
# 0x10500 answers with.
TITLE_EXIT_LIVES = 1        # decrements to zero, which is the only entry state the third swap has


def test_the_twin_leaves_through_the_title_exit():
    """FRAME_EXIT_TITLE — three swaps with nobody alive. See the paragraph above for why this case
    lives here rather than in `test_frame.py`, and why it is not refusal-free."""
    image = frame.world(0, frame.WORLD_START)
    leaves_the_image_where_the_c_does(
        image, frame.ship_death_pokes(image, TITLE_EXIT_LIVES, 0, 0),
        expect=FRAME_EXIT_TITLE, refusal_free=False)


@pytest.mark.parametrize("counter,expect", ((1, FRAME_EXIT_ADVANCE_SECTION),
                                            (2, FRAME_EXIT_NEXT_FRAME)))
def test_the_twin_advances_when_the_section_end_delay_runs_out(counter, expect):
    """Explosion group 0 finished, then `subi.b #$1,$19ac0` + `beq 0x10814`: the section advances on
    the frame the delay reaches zero and on no other, so both sides of that edge are driven."""
    image = frame.world(0, frame.WORLD_START)
    extra = frame.explosion_group_done(image, 0)
    extra[frame.A_SECTION_END_DELAY_COUNTER] = bytes([counter])
    leaves_the_image_where_the_c_does(image, extra, expect=expect)


@pytest.mark.parametrize("timer,offscreen,expect",
                         ((frame.MOTHERSHIP_LEAVE_FRAME, 0, FRAME_EXIT_ADVANCE_SECTION),
                          (frame.MOTHERSHIP_LEAVE_FRAME - 1, 1, FRAME_EXIT_ADVANCE_SECTION),
                          (frame.MOTHERSHIP_LEAVE_FRAME - 1, 0, FRAME_EXIT_NEXT_FRAME)))
def test_the_twin_advances_on_the_mothership_timer_or_escape(timer, offscreen, expect):
    """The OTHER route to 0x10814, and the frame that takes neither: the encounter's phase timer
    reaching MOTHERSHIP_LEAVE_FRAME, or the mothership going off screen. The `st`/`sf` pair on
    0x19ce5 brackets both, and the byte is seeded so the two stores are diffed."""
    extra = {frame.A_MOTHERSHIP_PHASE_TIMER: timer.to_bytes(4, "big"),
             frame.A_MOTHERSHIP_OFFSCREEN: bytes([offscreen]),
             frame.A_MOTHERSHIP_READY: b"\x00", frame.A_UNUSED_SECTION_END_FLAG: b"\x5a",
             frame.A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra, expect=expect)


# ============================================================ arms no played frame reaches

def test_the_twin_respawns_a_star_that_ran_off_the_left_edge():
    """The starfield's `bmi` arm, on `test_frame.py`'s own table poke — the one branch of the three
    layer loops that a dozen played frames cannot reach (its docstring says why)."""
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START),
                                      frame.starfield_respawn_pokes())


@pytest.mark.parametrize("layer2,layer3", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_the_twin_steps_each_starfield_layer_at_its_own_rate(layer2, layer3):
    """Layer 1 steps every frame, layer 2 only while its phase byte is clear and layer 3 only while
    its countdown is — four combinations, four different sets of stars moved, and the two `lea
    2(%a1),%a1` arms that stand a layer still are only in two of them."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_STARFIELD_LAYER2_PHASE: bytes([layer2]),
         frame.A_STARFIELD_LAYER3_COUNTDOWN: bytes([layer3])})


@pytest.mark.parametrize("timer,level", ((frame.A_SHIELD_DECAY_TIMER, frame.A_SHIELD_LEVEL),
                                         (frame.A_WEAPON_DECAY_TIMER,
                                          frame.A_WEAPON_POWER_LEVEL),
                                         (frame.A_SPEED_DECAY_TIMER, frame.A_SHIP_SPEED_LEVEL)))
@pytest.mark.parametrize("level_value", (0, 1, 3))
def test_the_twin_decays_each_power_up_to_its_own_floor(timer, level, level_value):
    """Three 1000-frame timers due on this frame, each with its own floor and only the shield's
    mirroring itself into the HUD gauge. The level is swept across and below its floor, because a
    level already under an EQUALITY floor keeps decaying."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {timer: (1).to_bytes(2, "big"), level: bytes([level_value]),
         frame.A_POWER_GAUGE_DISPLAY: b"\x5a", frame.A_PANEL_REDRAW_MASK: b"\x00"})


@pytest.mark.parametrize("page,column", ((0, 0), (frame.MAP_PAGES - 1, 0),
                                         (frame.MAP_PAGES - 1, frame.SCROLL_PHASES - 1)))
def test_the_twin_wraps_both_scroll_counters(page, column):
    """`addq.b #1` + `cmpi.b #$8` on the map page and `#$14` on the column phase, the second reached
    only when the first wraps."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_MAP_PAGE: bytes([page]), frame.A_MAP_COLUMN: bytes([column]),
         frame.A_SCROLL_FROZEN: b"\x00"})


# TWO AWARDS IN ONE PASS, which is the only shape that can see a stub's `X_OUT`.
#
# `score_add_bcd` opens with four `abcd -(a1),-(a0)` and `abcd` ADDS the 68000's X, so the flag
# reaching one award is whatever the previous award LEFT. The C carries it as the core's
# `extend_in` argument and its return value; the STUB is what turns those back into a real CCR bit,
# and off target the door makes the omission worse than "unmarshalled" — the harness resumes a
# serviced callback with every condition code SET (`osh_bench_door_return`), so a stub that dropped
# its `X_OUT` hands the next chain a carry of 1 rather than the 0 the core answered.
#
# ONE award cannot show it, because the flag is only read by the NEXT chain — and almost every award
# site in this stage is followed by `door_sound_start`, which sets X deliberately and erases the
# question. The small-explosion pass is the exception: a capsule the chain walk explains as a
# LANDING is cleared without a tune (0x12084's `bne 0x12092`), so two such records one slot apart
# award twice with nothing between them that touches X.
CAPSULE_SLOTS = (0, 1)             # two of the eight wave slots, walked in this order
CAPSULE_SQUADRONS = (2, 3)         # ...each the last member of its own squadron
SQUADRON_COUNTER_COUNT = 6
CAPSULE_ON_TERRAIN = 1             # the record's pixel-hit byte: what makes the walk answer "yes"
CARRY_START_SCORE = 0x00000100     # far from any digit boundary, so only a stray carry moves it
# The pass is gated on `not.b $198ad` + `bne`, so it runs on the frame the byte TOGGLES TO ZERO —
# which means seeding it all ones, not one.
EXPLOSION_PHASE_EVEN_DUE = 0xff


def test_the_twin_carries_one_awards_flag_into_the_next():
    """Two capsule spawns in one small-explosion pass, so `score_add_bcd` runs twice and the second
    chain starts on the flag the first one answered with.

    Each record is on its explosion's last frame, carries a credit tag that is not the no-credit
    one, is the last mark of its own squadron, and has its pixel-hit byte set over an EMPTY
    collision row — which is `test_frame.py`'s own recipe for making `collision_chain_walk` answer
    "the landscape" and so take the silent arm.

    **AND IT DOES NOT YET PIN THE CARRY — MEASURED, so read this before trusting the name.** Deleting
    `X_OUT` from `door_score_add_bcd` (and from the three `shot_retire_*` stubs) leaves this case, and
    all 146 in this file, GREEN. So the staging above does not in fact reach two awards with nothing
    between them that touches X: either only one capsule takes the silent arm, or something on the
    path rewrites the flag before the second chain reads it. What the case DOES hold is everything
    else about a two-capsule pass — the twin's image against the C's, byte for byte.

    THE HOLE IS THE X WRITE-BACK ITSELF, and STATUS.md carries it as an unpinned residual with what
    would close it: a staged world proven to reach two `abcd` chains in a row, or a direct assertion
    on the flag the trampoline leaves, which needs the bench runner to report the CCR the twin
    returned with. Do not delete this case to "fix" the hole — it is a real differential; it is only
    its NAME that promises more than it delivers.
    """
    counters = bytearray([0x5a] * SQUADRON_COUNTER_COUNT)
    extra = {frame.A_PLAYER_SCORE_BCD: CARRY_START_SCORE.to_bytes(frame.SCORE_BCD_BYTES, "big"),
             frame.A_EXPLOSION_PHASE_EVEN: bytes([EXPLOSION_PHASE_EVEN_DUE])}
    for slot, squadron in zip(CAPSULE_SLOTS, CAPSULE_SQUADRONS):
        record = frame.A_ENEMY_SLOTS + frame.ENTITY_STRIDE * slot
        counters[squadron] = 1
        extra.update({
            record + frame.ENTITY_TYPE: bytes([frame.EXPLOSION_PART_TYPE]),
            record + frame.ENTITY_ALIVE: bytes([0x80 | (frame.EXPLOSION_LAST_FRAME - 1)]),
            record + frame.EXPLOSION_CREDIT_TAG_OFFSET: b"\x00",
            record + frame.ENTITY_SQUADRON: bytes([squadron]),
            record + frame.ENTITY_PIXEL_HIT: bytes([CAPSULE_ON_TERRAIN]),
            frame.collision_row(frame.ENEMY_SLOT_FIRST + slot): bytes(frame.COLLISION_ROW_BYTES),
        })
    extra[frame.A_SQUADRON_KILL_COUNTERS] = bytes(counters)
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra)


@pytest.mark.parametrize("index", (4, 5))
def test_the_twin_turns_the_mothership_in_both_shapes(index):
    """At MOTHERSHIP_TURN_FRAME the encounter turns. Below the segmented index a mothership owns two
    ADJACENT records and both are turned unconditionally; at or above it, four records
    MOTHERSHIP_PAIR_BYTES apart of which only the live ones turn — two different loops."""
    extra = {frame.A_MOTHERSHIP_READY: b"\x01", frame.A_MOTHERSHIP_INDEX: bytes([index]),
             frame.A_MOTHERSHIP_PHASE_TIMER: frame.MOTHERSHIP_TURN_FRAME.to_bytes(4, "big"),
             frame.A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    for slot in range(frame.ENEMY_SLOT_COUNT):
        record = frame.A_ENEMY_SLOTS + frame.ENTITY_STRIDE * slot
        extra[record + frame.ENTITY_ALIVE] = bytes([slot % 2])
        extra[record + frame.MOTHERSHIP_TURN_SPEED_OFF] = b"\x5a\xa5"
        extra[record + frame.MOTHERSHIP_TURN_FLAG_OFF] = b"\x5a\x5a\x5a"
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra)


# ============================================================ reading frame.S back

def _frame_source():
    """`frame.S` with its `|` comments stripped, for the operand scans below."""
    return "\n".join(line.split("|", 1)[0] for line in FRAME_S.read_text().splitlines())


@functools.lru_cache(maxsize=None)
def _frame_equates():
    """{name: value} for every `.equ` in frame.S, as the ASSEMBLER computed it.

    Read out of the object rather than parsed out of the source: an `.equ` is an absolute symbol
    ('a' in `nm`), so this is the value the displacements below were really assembled with, and a
    scraper that misread one cannot make the window pin agree with itself. Which value each name
    OUGHT to hold is `test_constants.py::test_asm_twin_equates_match_the_headers`'s question.
    """
    assert FRAME_OBJ.exists(), (
        f"{FRAME_OBJ} is missing — build the twins with `make asm` (which `make test` runs first)")
    return {name: value for name, (value, kind) in elf_symbols(FRAME_OBJ).items() if kind == "a"}


# One `NAME-FGB(%a5)` operand, with the whitespace around `+` and `*` closed up first so the
# expression is one token and the mnemonic before it is not part of it.
_WINDOWED = re.compile(r"([^\s,]+)-FGB\(%a5\)")


@functools.lru_cache(maxsize=None)
def _windowed_operands():
    """Every distinct expression frame.S addresses through the %a5 window, as written."""
    tightened = re.sub(r"\s*([+*])\s*", r"\1", _frame_source())
    return sorted({match.group(1).split(",")[-1] for match in _WINDOWED.finditer(tightened)})


def _windowed_value(expression, equates):
    """One such expression's image address.

    `eval` over a table with no builtins, which is the whole grammar frame.S uses in these operands:
    `.equ` names joined by `+` and `*` (`A_score_award_table_bcd+2*SCORE_BCD_BYTES`). A parser of our
    own would be four more lines that could be wrong, over text this file also asserts the shape of.
    """
    return eval(expression, {"__builtins__": {}}, equates)      # noqa: S307


# frame.S's own count, from its header: "the sixty-six globals this stage names". Asserted so a
# parse that matched nothing — a renamed macro, a changed operand shape — cannot pass this whole
# section vacuously.
WINDOWED_OPERAND_COUNT = 66
DISPLACEMENT_MIN, DISPLACEMENT_MAX = -0x8000, 0x7fff


def test_every_windowed_global_was_found():
    assert len(_windowed_operands()) == WINDOWED_OPERAND_COUNT, (
        f"frame.S addresses {len(_windowed_operands())} distinct expressions through the %a5 "
        f"window, not the {WINDOWED_OPERAND_COUNT} its header names. If a global was legitimately "
        f"added or dropped, move this number; if the scan found nothing like the right count, the "
        f"operand shape changed and the window pin below is testing an empty list")


@pytest.mark.parametrize("expression", _windowed_operands())
def test_every_windowed_global_is_inside_the_signed_displacement(expression):
    """THE WHOLE OF WHAT MAKES `%a5 = image + FGB` LEGAL.

    frame.S reserves one address register for the stage's sixty-six globals and reaches every one of
    them as `NAME-FGB(%a5)`, which is a 68000 `d16(An)` — a SIGNED 16-BIT displacement. The globals
    that exist today span 0x1797e..0x19f44, comfortably inside it, and nothing in the file says so:
    gas would assemble a global outside the window into a truncated displacement and the twin would
    read or write a wild address, which the differential would report as a pixel diff a long way
    from its cause. frame.S's header asks for this test by name.
    """
    equates = _frame_equates()
    displacement = _windowed_value(expression, equates) - equates["FGB"]
    assert DISPLACEMENT_MIN <= displacement <= DISPLACEMENT_MAX, (
        f"{expression} is at {_windowed_value(expression, equates):#x}, which is {displacement:#x} "
        f"from FGB ({equates['FGB']:#x}) — outside the signed 16-bit window a `d16(An)` carries. "
        f"gas will truncate it silently. Give it its own base register, or move FGB")


# ---- the exit enum, which is a C enum and so is spelt twice ---------------------------------

_ENUM_BODY = re.compile(r"typedef enum \{(.*?)\} frame_exit;", re.S)
_ENUM_NAME = re.compile(r"^\s*(FRAME_EXIT_\w+)", re.M)


@functools.lru_cache(maxsize=None)
def _header_exit_enum():
    """{name: value} for include/frame.h's `frame_exit`, counting the implicit increments."""
    body = _ENUM_BODY.search((REC / "include" / "frame.h").read_text())
    assert body, "include/frame.h no longer declares a `typedef enum { ... } frame_exit;`"
    names = _ENUM_NAME.findall(body.group(1))
    assert names, "the frame_exit enum has no FRAME_EXIT_* members"
    return dict(zip(names, range(len(names))))


@pytest.mark.parametrize("name", sorted(_header_exit_enum()))
def test_the_exit_enum_is_the_headers(name):
    """frame.S spells the five answers as `.equ` because they are a C ENUM and not `#define`s, so
    `test_constants.py`'s header scraper cannot see them and nothing else pins them.

    Both spellings are checked against the header — the assembly's, which is what the twin returns,
    and this file's mirror, which is what every case above declares its arm with.
    """
    expected = _header_exit_enum()[name]
    assert _frame_equates()[name] == expected, (
        f"frame.S's `.equ {name}` is {_frame_equates()[name]}, include/frame.h's enum {expected} — "
        f"the twin would answer a value its own header does not mean")
    assert globals()[name] == expected, (
        f"this suite's mirror of {name} is {globals()[name]}, the header's {expected}")


# ---- the door slots -------------------------------------------------------------------------

@pytest.mark.parametrize("slot", sorted(DOOR_TABLE))
def test_the_door_slots_are_the_ones_the_twin_jumps_to(slot):
    """DOOR_TABLE's numbering against frame.S's `.equ ZY_DOOR_*`.

    The two are the two halves of one address: the stub jumps to `DOOR_BASE + slot * STRIDE` and
    `AsmTwins._service_door` looks that slot up in the table. Renumber one and every case would call
    the WRONG HOST FUNCTION with the arguments meant for another — which off target is a diff, and
    on target is a real `jsr` to a real core with nothing here to say the table drifted.
    """
    name = f"ZY_DOOR_{DOOR_TABLE[slot].name}"
    equates = _frame_equates()
    assert name in equates, (
        f"frame.S declares no `.equ {name}`, so slot {slot} of DOOR_TABLE names a callee the twin "
        f"does not reach through the door")
    assert equates[name] == slot, (
        f"frame.S puts {name} in slot {equates[name]} and DOOR_TABLE in slot {slot} — the table and "
        f"the assembly disagree about which host function that door address means")


def test_the_door_table_declares_every_slot_the_twin_uses():
    """...and the other direction: no `.equ ZY_DOOR_*` may be missing from DOOR_TABLE. A stub added
    to frame.S with no table row would jump into the band, find nothing declared and fail as a
    refusal — loud, but naming the slot rather than the omission."""
    declared = {name for name in _frame_equates() if name.startswith("ZY_DOOR_")}
    tabled = {f"ZY_DOOR_{callback.name}" for callback in DOOR_TABLE.values()}
    assert declared == tabled, (
        f"frame.S and DOOR_TABLE name different door callees: only in frame.S "
        f"{sorted(declared - tabled)}, only in the table {sorted(tabled - declared)}")


# ---- the transcription pin, which here is about ORDER rather than about bytes ----------------

_DIS_LINE = re.compile(r"^([0-9a-f]{6}): ")
# The address comment frame.S puts on every transcribed instruction: `| 011d30 ...`. Six hex digits
# at the head of the comment, which no other comment in the file starts with — the prose ones spell
# an address `0x11d30` or `$19aad`, and neither matches.
_ASM_ADDRESS = re.compile(r"\s+(0[0-9a-f]{5})\b")


def _original_instruction_addresses():
    """Every instruction address of the original in [ORIGINAL_ENTRY, ORIGINAL_END), from the
    disassembly the transcription was made from."""
    assert PRG_DIS.exists(), f"{PRG_DIS} is missing — it is what the twin was transcribed from"
    found = [int(match.group(1), 16)
             for match in map(_DIS_LINE.match, PRG_DIS.read_text().splitlines()) if match]
    return [address for address in found if ORIGINAL_ENTRY <= address < ORIGINAL_END]


def _transcribed_addresses():
    """The same list as frame.S claims it: the `| 0xxxxx` comment on each transcribed instruction.

    Read from the FILE'S TEXT and not from a build, on purpose. FIVE of the stage's instructions are
    inside `#ifdef`s — the two spin COMPARES at 0x126ee and 0x1270c, their back-branches at 0x126f6
    and 0x12712, and the `bset` at 0x12714 — and the off-target assembly the differential runs
    contains only one arm. Scanning the text sees BOTH, which is the only way this pin can ask for
    all 703.

    AND IT PINS THEIR PRESENCE AND ORDER, NOT THEIR OPERANDS. Those five are the one span in this
    twin with no off-target surface at all: a wrong bit in the `bset`, a wrong `HW_MFP_IERB`, or the
    wrong polled byte assembles only in the target build and passes everything here. The surface is
    `atari/smoke.py game`, and STATUS.md records it as such rather than leaving it implied.
    """
    comments = (line.split("|", 1)[1] for line in FRAME_S.read_text().splitlines() if "|" in line)
    return [int(match.group(1), 16)
            for match in map(_ASM_ADDRESS.match, comments) if match]


def test_the_twin_transcribes_the_original_instruction_for_instruction():
    """EVERY INSTRUCTION OF THE ORIGINAL, ONCE, IN ORDER — and this stands where the byte pin stands
    for the leaf twins.

    A byte pin is not available here (this file's header says why: almost every instruction of the
    stage names a global, and position-independence re-encodes all of them). What survives that
    translation untouched is the SEQUENCE, so this compares the two address lists whole: the
    original's, scraped out of ../../out/prg_dis.txt, against frame.S's own `| address` comments.

    It catches what a differential cannot: an instruction dropped on a path the game's own data
    never takes, one transcribed twice, a pass moved in front of another, a comment left naming an
    address the line no longer transcribes. A twin that stopped being the original's instruction
    sequence is a twin whose cost bars and whose fidelity claim have nothing behind them.
    """
    original = _original_instruction_addresses()
    transcribed = _transcribed_addresses()
    assert transcribed == original, (
        f"frame.S is no longer the original's instruction sequence over "
        f"[{ORIGINAL_ENTRY:#x}, {ORIGINAL_END:#x}): it claims {len(transcribed)} instructions and "
        f"the original has {len(original)}. Missing "
        f"{[hex(a) for a in sorted(set(original) - set(transcribed))][:10]}, extra "
        f"{[hex(a) for a in sorted(set(transcribed) - set(original))][:10]}, out of order at "
        f"{next((hex(a) for a, b in zip(transcribed, original) if a != b), 'nowhere')}")


# ============================================================ what the twin COSTS

# READ THIS BEFORE READING A RATIO HERE, because it is not the reading the other twin suites take.
#
# THE DOOR CHARGES NOTHING FOR A C BODY. `bench_loop` stops at the door address, the harness calls
# the host function and resumes: the stub's `jsr` and `rts` really execute and are charged, the
# core's body does not exist on this side and costs nothing. The ORIGINAL, clocked over the same
# span, executes its sixteen callees in full. So `twin / original` here is NOT the like-for-like
# reading `test_asm_sprite.py` takes over a leaf, and it must not be read as a fidelity claim:
#
#   the twin's number   = the twin's OWN instructions, C-ABI frame and nineteen trampolines included
#   the original's      = its own instructions AND everything its `bsr`s reach
#
# WHAT THE PIN IS FOR is what a pin is always for: a deterministic number that moves when the twin's
# own instruction stream does. Both sides are Musashi cycle counts over one fixed staged world, so
# each reading is exact and repeatable, and the margins below are a handful of CYCLES — one extra
# register in the prologue's `movem` is 16 cycles round trip and reddens every band.
#
# AND THE NUMBERS ARE ABOVE 1.00x, which is worth saying because frame.S's header predicts the
# opposite. Its prediction is about the GLOBALS and is correct as far as it goes — `tst.b d16(An)`
# is 12 cycles against `tst.b abs.l`'s 14, `move.b #imm,d16(An)` 16 against 20, `lea d16(An),An` 8
# against 12 — but the stage makes nine or ten door calls a frame, and a trampoline (a four-register
# `movem` pair, the `suba.l` pointer-to-offset conversions, the pushes and the `lea` unwind) costs
# far more than the `bsr` the original has there. The two effects together leave the twin 240-360
# cycles OVER on every band. The bars are set from the measurement, not from either prediction.
#
#   band                    original   twin   excess   measured      bar   slack
#   the ordinary frame          9,756 10,116    +360    1.03690   1.0376   6.8 cyc
#   the swap, restarting       10,848 11,090    +242    1.02231   1.0230   7.5 cyc
#   the swap, reloading        10,836 11,078    +242    1.02233   1.0230   7.2 cyc
#   the section-end advance    10,546 10,866    +320    1.03034   1.0310   6.9 cyc
#
# THE SLACK IS SEVEN CYCLES, which is what makes these bars a gate rather than a restatement of
# today's number: one more register in the prologue's `movem` pair is 16 cycles and reddens all
# four. The measurement is deterministic — Musashi counts cycles and `frame.world` is the oracle's
# own output — so the margin is for a legitimate re-translation, not for noise.
#
# The title exit has NO cost pin and cannot have one: clocking the original over that arm means
# running the shipped `game_over_screen` under the oracle, whose high-score entry holds eight busy-
# wait sites where the model carries four.
COST_BARS = {"ordinary": 1.0376, "swap_restart": 1.0230, "swap_reload": 1.0230,
             "advance": 1.0310}

# The five addresses the original leaves through, by the enum value the twin answers with. The stop
# PC is what `emu.run` needs and what makes a wrong exit fail as "did not reach checkpoint".
EXIT_ADDRESS = frame.FRAME_EXIT_ADDRESS


def _cost_case(extra, expect, band):
    """Clock the ORIGINAL and the twin over one staged world, and hold the twin to that band's bar.

    The twin goes through the differential on the way, so a cost reading can never be taken from a
    call that computed the wrong thing.
    """
    world = frame.world(0, frame.WORLD_START)
    run = leaves_the_image_where_the_c_does(world, extra, expect=expect)
    image = harness.make_image(frame.world_pokes(world, extra))
    _final, _writes, regs = emu.run(bytearray(image), ORIGINAL_ENTRY, {"d0": SOUND_CHANNEL},
                                    stop_pc=EXIT_ADDRESS[expect], max_insns=frame.FRAME_MAX_INSNS,
                                    schedule=list(frame.FRAME_SCHED),
                                    wait_sites=list(frame.WAIT_SITES))
    # The shared assertion, not a local restatement of it: `ceiling_for`'s docstring names this
    # exact case ("a suite whose bar varies by CASE rather than by twin"), and four twin suites
    # reading one phrasing is the point of it living in asm_twins.py.
    asm_twins.assert_within_the_bar(f"{TWIN} ({band})", regs["cycles"], run.cycles, COST_BARS[band])


def test_the_twin_costs_what_it_costs_on_an_ordinary_frame():
    """The band every frame of the game takes: the whole stage, nine door calls, out at 0x1296a."""
    _cost_case(None, FRAME_EXIT_NEXT_FRAME, "ordinary")


@pytest.mark.parametrize("band,other_section,expect",
                         (("swap_restart", 0, FRAME_EXIT_RESTART_SECTION),
                          ("swap_reload", 5, FRAME_EXIT_RELOAD_SECTION)))
def test_the_twin_costs_what_it_costs_through_the_swap(band, other_section, expect):
    """The ship-death band: the same tail plus `powerup_downgrade_on_death` and the swap loop's two
    fourteen-byte copies. Its own bar, because it is 1,100 cycles longer than the ordinary one and a
    shared bar would have to be the loosest of the two."""
    world = frame.world(0, frame.WORLD_START)
    _cost_case(frame.ship_death_pokes(world, 3, 2, other_section), expect, band)


def test_the_twin_costs_what_it_costs_ending_a_section():
    """The section-end band, which leaves through 0x10814 without ever reaching the swap."""
    world = frame.world(0, frame.WORLD_START)
    extra = frame.explosion_group_done(world, 0)
    extra[frame.A_SECTION_END_DELAY_COUNTER] = bytes([1])
    _cost_case(extra, FRAME_EXIT_ADVANCE_SECTION, "advance")
