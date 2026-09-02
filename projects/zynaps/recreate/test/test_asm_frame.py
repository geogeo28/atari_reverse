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
zeros there and die as a sentinel timeout naming neither the door nor the callee. So the frame
family has its own blob-with-a-table and its own differential, both in `asm_frame_common.py`; that
module's header says why they are the FAMILY's rather than this file's, and what
`test_asm_frame_doors.py` pins about the slot namespace they share. `asm_twins.py` is left alone.

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

import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import asm_twins
import asm_frame_common as common
import test_frame as frame

REC = common.REC
FRAME_S = common.ASM_DIR / "frame.S"
FRAME_OBJ = common.BUILD_ASM / "frame.o"

TWIN = "frame_resolve_hits_and_game_state_asm"
# The span of the original this twin transcribes, and the register the frame loop enters it with.
ORIGINAL_ENTRY = frame.ENTRY_RESOLVE                  # 0x11d30
ORIGINAL_END = 0x1296e                                # one past the `bra.w $10f4e` at 0x1296a
SOUND_CHANNEL = frame.ENTITY_SLOTS                    # D0 on entry — src/frame.c's `sound_channel`


# ============================================================ the callback door

# THE TABLE IS THE FAMILY'S, and lives in `asm_frame_common.py`. Four frame twins assemble into ONE
# blob and jump into ONE band, so a slot number names a host C function for all of them and four
# private tables would be four places to drift. `test_asm_frame_doors.py` pins this file's
# `.equ ZY_DOOR_*` against it, and pins that no sibling twin claims one of its slots for another
# core — the cross-file defect no single suite can see.
#
# The arming and the schedule are the family's for the same reason: the models a frame case consumes
# are global state in the candidate `.so`, and every frame suite has to re-arm them between its two
# runs. `asm_frame_common.arm_the_candidate` says why at length.
#
# NOTHING IS RE-EXPORTED HERE ON PURPOSE. An earlier revision bound `twins`, `arm_the_candidate`,
# `SCHEDULE` and `WAIT_SITES` into this module as aliases, and none was ever used. Two of them were
# worse than clutter: `SCHEDULE`/`WAIT_SITES` would have been an IMPORT-TIME SNAPSHOT, so a case
# that patched the family's schedule (`test_asm_frame_head.py`'s pause cases do exactly that, and
# rely on `arm_the_candidate` re-reading the module global at call time) would have been silently
# ignored by anyone reaching for the local name. Reach through `common.` and the patch is seen.

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
    """This stage's arguments to the family's differential (`asm_frame_common`, which says what the
    three assertions are and what each one closes).

    What is this suite's own is the pair of shores: the C glue for `[0x11d30, 0x1296e)`, entered with
    D0 = the sound channel, and the twin entered with the same. And the ANSWER, which for this stage
    is control flow — the original `bra`s to one of five addresses and the twin returns
    `include/frame.h`'s enum for it, so an arm that returned the wrong value would leave a perfect
    image (`frame.S`, "THE EXITS"). `expect` is DECLARED rather than read back, so a case that staged
    the wrong world fails saying which arm it wanted instead of quietly agreeing with itself.
    """
    return common.leaves_the_image_where_the_c_does(
        TWIN, world, extra,
        c_call=lambda lib, buf: lib.g_frame_resolve_hits_and_game_state(buf, SOUND_CHANNEL),
        twin_args=(SOUND_CHANNEL,), expect_ret=expect, refusal_free=refusal_free)


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
# `extend_in` argument and its return value; the STUB is what turns those back into a real CCR bit.
#
# WHAT THE DOOR LEAVES IN X IS A SCHEDULE, NOT A CONSTANT — this comment used to say "every
# condition code SET" and that stopped being true. N/Z/V/C come back set; X ALTERNATES per callback
# (`osh_bench_door_extend`, `emu.door_extend`, and TRAP_MODEL.md's "The callback door"). The change
# was made precisely so that a stub which dropped its `X_OUT` could not go on agreeing with its core
# by coincidence.
#
# ONE award cannot show it, because the flag is only read by the NEXT chain — and almost every award
# site in this stage is followed by `door_sound_start`, which sets X deliberately and erases the
# question. The small-explosion pass looks like the exception: a capsule the chain walk explains as a
# LANDING is cleared without a tune (0x12084's `bne 0x12092`), so two such records one slot apart
# award twice. **IT IS NOT ONE, AND THE ALTERNATION IS WHAT PROVED IT.** `door_collision_chain_walk`
# sits at 0x1207c, between the award at 0x1206e and anything that could read the flag, and a door
# destroys the CCR on purpose — so X never survives from one award to the next on this arm either.
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

    **AND IT DOES NOT PIN THE CARRY — MEASURED TWICE, so read this before trusting the name.**
    Deleting `X_OUT` from `door_score_add_bcd` (or from the three `shot_retire_*` stubs) leaves this
    case, and every case in this file, GREEN — both before the door's X alternation and after it.
    Wave D re-ran the per-stub sweep both ways to find out which, and the answer is that the staging
    cannot reach two `abcd` chains with nothing between them: `door_collision_chain_walk` at 0x1207c
    destroys the CCR on the silent-capsule arm, exactly as `door_sound_start` does on every other
    award site. What the case DOES hold is everything else about a two-capsule pass — the twin's
    image against the C's, byte for byte.

    THE HOLE IS THE X WRITE-BACK ITSELF, and STATUS.md carries it as an unpinned residual. The
    closure wave C proposed (a staged world reaching two chains in a row) is now known NOT to be
    available; what is left is `run_bench` reporting the CCR the way it reports the register file, so
    a case can assert the flag the trampoline left instead of hoping a downstream `abcd` observes it.
    Do not delete this case to "fix" the hole — it is a real differential; it is only its NAME that
    promises more than it delivers.
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

# The scrapers are the family's (`asm_frame_common`): four twins ask the same three questions of
# their own `.S` and `.o`, and four copies of the parsing would be four ways to disagree about what
# an `.equ` or an `| 0xxxxx` comment is. What stays here is what is THIS file's: which object, which
# span of the original, and the counts below.
def _frame_equates():
    return common.equates(FRAME_OBJ)


# THE %a5 GLOBAL WINDOW. Both checks are `asm_frame_common`'s — one phrasing, because all four
# frame suites ask the same question of their own `.S`, and the four hand-copies this replaced had
# already started to drift in their failure text. What stays here is what is THIS twin's: which
# file, and how many globals it reaches.
WINDOWED_OPERAND_COUNT = 66


def test_the_window_scan_reads_every_global_this_twin_names():
    """The scan's positive control. `window_pin_failures` is vacuous over an empty operand list, so
    a twin whose operand shape stopped matching — a different window register, a differently named
    origin — would pass the pin below by reaching no globals at all."""
    failure = common.window_scan_failure(FRAME_S, WINDOWED_OPERAND_COUNT)
    assert failure is None, failure


def test_every_windowed_global_is_inside_the_signed_displacement():
    """THE WHOLE OF WHAT MAKES `%a5 = image + FGB` LEGAL for this twin: gas assembles a global
    outside the signed 16-bit window into a TRUNCATED displacement with no diagnostic, and the twin
    then reads or writes a wild address that the differential reports as a pixel diff a long way
    from its cause."""
    failures = common.window_pin_failures(FRAME_S)
    assert not failures, "\n".join(failures)


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


# ---- the transcription pin, which here is about ORDER rather than about bytes ----------------

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
    failure = common.transcription_failure(FRAME_S, ORIGINAL_ENTRY, ORIGINAL_END)
    assert failure is None, failure


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
