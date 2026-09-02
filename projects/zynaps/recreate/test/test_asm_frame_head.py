"""The ASM-TWIN differential for the frame loop's FIRST STAGE: `../src/asm/frame_head.S` must leave
the image byte-for-byte where its C core in `../src/frame.c` leaves it, and answer with the same
exit flag.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_frame.py` pins the C core against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_frame.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_frame.py`'S, IMPORTED RATHER THAN RESTATED — its world staging (`world`, which
has the ORACLE play a section for four frames before a case starts), its poke recipes and its fuzz
generator. Importing it also installs this battery's `ctypes` signature for the head glue, which is
why nothing here declares it again. Everything shared with the other three frame twins — the door
table, the candidate arming, the differential itself and the source scrapers — is
`asm_frame_common.py`'s, and that module's header says why.

WHAT IS THIS SLICE'S OWN, over and above wave C's `test_asm_frame.py`:

**1. TWO EXITS, AND THE ANSWER IS THE ONLY THING THAT SEPARATES THEM ON SOME FRAMES.** The stage
falls through into 0x113c0 or branches past it to 0x1167c, and the three gates that divert
(0x111c4, 0x111d6, 0x111de) come AFTER every byte the stage writes. So a twin that took the wrong
arm can leave a perfect image; `expect` is what catches it, and it is DERIVED here the way
`test_frame.py::_stage_head_falls_through` derives it, from the same three bytes.

**2. THE PAUSE IS THE ONE SPAN WITH A BUILD-DEPENDENT BODY.** Three spins on `A_key_scancode` go
through the kit off target (`sched_wait8` twice, `sched_poll8` in the middle loop) and are the
original's own instructions on target. `test_the_twin_pauses_and_restarts_the_palette_counters`
drives the off-target arm on `test_frame.py`'s own schedule; the ON-TARGET arm has NO surface here
at all, and `atari/smoke.py game` is the only thing that reads it. `frame_head.S`'s header says so
in the same words.

**3. IT CALLS TWENTY TWINS THAT ARE NOT DOORS.** The playfield blit dispatches through a table of
this file's own into wave A's `scroll_page_to_screen_pNN_asm`, in the same blob, in both builds — so
every case below runs wave A's assembly inside wave D's, against a C shore that runs the C blits.
`test_asm_scroll.py` is what makes those two the same thing.

**4. THERE IS NO BYTE PIN**, for `frame.S`'s reason: the twenty-nine globals this stage names are
absolute in the original and base-relative here, so almost nothing in it can be byte-equal. What
stands in its place is the differential below, the cost bars, and
`test_the_twin_transcribes_the_original_instruction_for_instruction`.

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
HEAD_S = common.ASM_DIR / "frame_head.S"
HEAD_OBJ = common.BUILD_ASM / "frame_head.o"
FRAME_C = REC / "src" / "frame.c"
KIT_OS_H = REC.parents[2] / "tools" / "recreate_kit" / "include" / "os.h"

TWIN = "frame_panel_scroll_and_ship_stage_asm"
# The span of the original this twin transcribes. It takes NO register on entry — `_check_head`
# passes none either — and its two exits are the next two slices' entry PCs.
ORIGINAL_ENTRY = frame.ENTRY_FRAME_HEAD               # 0x10f4e
ORIGINAL_END = frame.ENTRY_DRONE_AND_FIRE             # 0x113c0, one past the last transcribed insn

# The stage's own answer, mirrored from `../src/frame.c`'s two `return`s and pinned against
# `frame_head.S`'s `.equ`s by `test_the_exit_flags_are_the_cs`.
HEAD_EXIT_PLAYER_GATED = 0            # one of the three gates branched to 0x1167c
HEAD_EXIT_FELL_THROUGH = 1            # control ran on into 0x113c0

# The two underscore-private helpers this suite borrows from `test_frame.py` to decide which exit a
# staged world takes. Checked at import for `test_frame.py`'s own reason (its guard over
# `test_init`'s privates): a rename over there would otherwise fail HERE as an AttributeError inside
# a case named for something else.
for _borrowed in ("_stage_head_falls_through", "_poked"):
    assert hasattr(frame, _borrowed), (
        f"test_asm_frame_head.py derives each case's exit arm from test_frame.{_borrowed}, so that "
        f"the twin's expected answer and the C battery's are one statement; that name is gone, so "
        f"either restore it or give this suite its own derivation")


# THE CALLBACK DOOR IS THE FAMILY'S, table and blob alike, and lives in `asm_frame_common.py`: four
# frame twins assemble into ONE blob and jump into ONE band, so a slot number names a host C function
# for all of them. `test_asm_frame_doors.py` is what pins this file's `.equ ZY_DOOR_*` against that
# table, and `common.leaves_the_image_where_the_c_does` is what reaches the blob — so nothing here
# names either of them directly.


# ============================================================ the differential

def _exit_the_world_takes(world, extra):
    """Which of the stage's two exits this staged image takes, by the original's own three gates.

    `test_frame.py::_stage_head_falls_through` IS that predicate — the same three bytes, read once —
    and borrowing it is what stops this suite and the C battery disagreeing about what a case stages.
    """
    return (HEAD_EXIT_FELL_THROUGH if frame._stage_head_falls_through(frame._poked(world, extra))
            else HEAD_EXIT_PLAYER_GATED)


def leaves_the_image_where_the_c_does(world, extra=None, expect=None):
    """This stage's arguments to the family's differential (`asm_frame_common`, which says what its
    three assertions are and what each one closes).

    What is THIS suite's own is the pair of shores — the C glue for `[0x10f4e, 0x113c0)`, entered
    with no register at all, and the twin entered the same way — and the ANSWER, which for this
    stage is which of two exits control left through. Since the three gates that divert sit after
    every byte the stage writes, an arm taken the wrong way can leave a PERFECT image, and this
    return value is the only thing between that and a green run.

    `expect` is DERIVED from the staged world rather than read back from either shore, so a case
    that poked the wrong bytes fails saying which arm it wanted. A case may still DECLARE it, and
    then the declaration is checked against the derivation first — which is what makes a case like
    `test_the_twin_takes_both_of_its_exits` an assertion about the staging and not just about the
    twin.
    """
    derived = _exit_the_world_takes(world, extra)
    if expect is not None:
        assert derived == expect, (
            f"this case says the head slice returns {expect}, but the three gates over the world it "
            f"stages answer {derived} — the pokes do not reach the arm the case is named for")
    return common.leaves_the_image_where_the_c_does(
        TWIN, world, extra,
        c_call=lambda lib, buf: lib.g_frame_panel_scroll_and_ship_stage(buf),
        twin_args=(), expect_ret=derived, refusal_free=True)


# ============================================================ the game, played

@pytest.mark.parametrize("section", range(frame.SECTION_COUNT))
def test_the_twin_plays_the_game(section):
    """The stage, frame by frame, over each of the sixteen sections the game ships.

    THIS IS THE COMPOSITION TEST. Each frame runs the twin's 240 instructions and its fifteen calls
    over the whole 512 KB the game owns, against the C that `test_frame.py` has already proved equal
    to the original on these exact worlds — so a pass that took a branch the other way, dispatched
    the wrong column blit or handed an emitter the wrong cursor differs on real pixels.

    The sections are not interchangeable: four are asteroid fields with no map at all, which is the
    only way the played game reaches 0x11024's derived cursor rather than the tile emitter.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    rng = random.Random(0xf4a3e + section)
    for _ in range(frame.WORLD_FRAMES):
        image[frame.A_JOYSTICK_STATE] = rng.choice(frame.JOYSTICK_BYTES)
        leaves_the_image_where_the_c_does(image)
        image = frame.advance_one_frame(image)


@pytest.mark.parametrize("section", frame.FUZZ_SECTIONS)
def test_the_twin_fuzz(section):
    """`test_frame.py`'s own 96-case generator, replayed against the twin.

    What it reaches that the sweep above does not is the COMBINATION: a map page and column phase
    drawn independently of the scroll freeze, a tilt frame and countdown drawn independently of the
    stick, a speed level drawn independently of both — which is the whole of bands 3 and 5 crossed
    against each other rather than walked one frame at a time.

    Sharded by section for `test_frame.py`'s reason: a case's cost is dominated by building its
    world, which `frame.world` caches per worker.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for case in frame.fuzz_cases_for(section):
        leaves_the_image_where_the_c_does(
            image, frame.fuzz_pokes(random.Random(0x10f4e + case), image))


# ============================================================ the two exit arms

# `test_frame.py::test_the_head_slice_takes_both_of_its_exits`' own four cases: the three gates that
# divert to 0x1167c and the state that falls through. The world sweep above reaches only the
# fall-through — a ship dies rarely and never in the dozen frames a section is played for — so the
# diverting arm exists only here.
EXIT_GATES = (
    ("the ship's death explosion is running",
     {frame.A_EXPLOSION_GROUP_ACTIVE_BITS: bytes([1 << 1])}, HEAD_EXIT_PLAYER_GATED),
    ("the ship's record is dead",
     {frame.A_PLAYER_RECORD + frame.ENTITY_ALIVE: b"\x00"}, HEAD_EXIT_PLAYER_GATED),
    ("the ship's record is exploding",
     {frame.A_PLAYER_RECORD + frame.ENTITY_ALIVE: b"\x80"}, HEAD_EXIT_PLAYER_GATED),
    ("the ship is alive and flying",
     {frame.A_PLAYER_RECORD + frame.ENTITY_ALIVE: b"\x01",
      frame.A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}, HEAD_EXIT_FELL_THROUGH),
)


@pytest.mark.parametrize("gate,extra,expect", EXIT_GATES, ids=[case[0] for case in EXIT_GATES])
def test_the_twin_takes_both_of_its_exits(gate, extra, expect):
    """Each of the three gates that skips the player-control block, and the state that does not.

    All four leave the same bytes up to 0x111c4 and only two of them run band 5 at all, so what
    separates the arms is the twin's %d0. `expect` is declared here as well as derived, which makes
    the case an assertion about the poke reaching its gate.
    """
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra, expect=expect)


# ============================================================ the pause

# `test_frame.py::test_the_pause_key_holds_the_frame_and_restarts_the_palette_counters`' own three
# arrival patterns, reused verbatim. The counters are seeded to a value neither the pause nor
# anything else produces, so a pass that skipped the reload differs.
PAUSE_ARRIVALS = ((1, 1), (2, 3), (4, 2))
PAUSE_SITES = (frame.PAUSE_RELEASE_WAIT_PC, frame.PAUSE_PRESS_WAIT_PC,
               frame.PAUSE_SECOND_RELEASE_WAIT_PC)
PAUSE_COUNTER_SEED = b"\x5a"


@pytest.mark.parametrize("release_nth,press_nth", PAUSE_ARRIVALS)
def test_the_twin_pauses_and_restarts_the_palette_counters(release_nth, press_nth, monkeypatch):
    """Space bar: wait for the release, restart both palette-cycle counters, wait for the next press
    and for ITS release — with the arrivals pushed out so the middle loop really turns.

    THE STAGING IS `test_frame.py`'S OWN, pokes and schedule alike, because the two suites have to
    release the spins at the same polls or their images cannot be compared. That battery's docstring
    carries the rest of the reasoning, including why the pause is driven on this slice alone
    (`os.h`'s OS_SCHED_SITE_MAX carries four sites and the pause holds three).

    THE SCHEDULE IS PATCHED IN RATHER THAN PASSED, and that is the one thing this case cannot borrow.
    `asm_frame_common.leaves_the_image_where_the_c_does` arms the candidate ITSELF, once per shore,
    from the module's own SCHEDULE/WAIT_SITES — which are the frame TAIL's two waits and no use to
    the pause. Both are read at call time, so patching them for this case arms both shores with the
    pause's three sites and nothing else changes.

    OFF TARGET ONLY, and that is not a gap this file can close: on target the three spins are the
    original's own instructions inside an `#ifdef`, and nothing in a host differential can execute
    them. `atari/smoke.py game` is their surface.
    """
    schedule = ({"pc": frame.PAUSE_RELEASE_WAIT_PC, "nth": release_nth,
                 "addr": frame.A_KEY_SCANCODE, "width": 1, "value": 0},
                {"pc": frame.PAUSE_PRESS_WAIT_PC, "nth": press_nth,
                 "addr": frame.A_KEY_SCANCODE, "width": 1, "value": frame.KEY_SCANCODE_SPACE},
                {"pc": frame.PAUSE_SECOND_RELEASE_WAIT_PC, "nth": release_nth,
                 "addr": frame.A_KEY_SCANCODE, "width": 1, "value": 0})
    monkeypatch.setattr(common, "SCHEDULE", emu.schedule_entries(list(schedule)))
    monkeypatch.setattr(common, "WAIT_SITES", emu.wait_site_pcs(list(schedule), list(PAUSE_SITES)))
    extra = {frame.A_KEY_SCANCODE: bytes([frame.KEY_SCANCODE_SPACE]),
             frame.A_PALETTE_SWAP_COUNTDOWN: PAUSE_COUNTER_SEED,
             frame.A_PALETTE_ROTATE_COUNTDOWN: PAUSE_COUNTER_SEED}
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra,
                                      expect=HEAD_EXIT_FELL_THROUGH)


# ============================================================ arms no played frame reaches

# include/hud.h's PANEL_REDRAW_{POWERUP,WEAPON,GAUGE,LIVES}_BIT. Bit 3 is not tested by the stage
# at all (nothing sets it) and is left out for that reason rather than forgotten.
PANEL_REDRAW_BITS = (0, 1, 2, 4)
# include/player.h — the top of the tilt bank, which `ship_move_down`'s `cmpi.b #$6` stops at.
SHIP_TILT_MAX = 6


@pytest.mark.parametrize("bit", PANEL_REDRAW_BITS)
def test_the_twin_repaints_each_panel_element(bit):
    """One bit of `A_panel_redraw_mask` at a time. Three of the four run a repaint and then CLEAR
    themselves; bit 4 (the lives strip) has no `bclr` and stands, which is the asymmetry a
    reconstruction is most likely to tidy away. The section start leaves the mask at 7, so the
    gauge and the lives strip are the only ones a played frame ever reaches."""
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START),
                                      {frame.A_PANEL_REDRAW_MASK: bytes([1 << bit])})


@pytest.mark.parametrize("countdown", (1, 2, frame.PANEL_LOGO_PERIOD))
def test_the_twin_runs_the_logo_only_on_an_idle_panel(countdown):
    """`tst.b` on the WHOLE mask and then a 500-frame countdown: the animated logo is drawn only on a
    frame with nothing else pending, and only on the frame the countdown reaches zero — where it is
    reloaded with PANEL_LOGO_PERIOD. `test_frame.py`'s own three counts, one either side of the
    wrap and one at the reload's value."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_PANEL_REDRAW_MASK: b"\x00",
         frame.A_PANEL_LOGO_COUNTDOWN: countdown.to_bytes(2, "big")})


@pytest.mark.parametrize("page", range(frame.MAP_PAGES))
@pytest.mark.parametrize("frozen", (0, 1))
def test_the_twin_emits_from_every_page_of_the_ring(page, frozen):
    """Page 0 decodes a fresh tile column and republishes the map cursor the emitter answers with;
    pages 1..7 re-emit page 0's workspace. The freeze byte picks `_shift0` over `_shift2` on
    1..7 and, on page 0, steps the cursor BACK a column instead of republishing the offset — so all
    four combinations of the two gates are here, and the cursor the trampoline delivers in %a4 is
    only exercised by the page-0 half."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_MAP_PAGE: bytes([page]), frame.A_SCROLL_FROZEN: bytes([frozen])})


@pytest.mark.parametrize("column", range(frame.SCROLL_PHASES))
def test_the_twin_dispatches_every_column_phase(column):
    """All twenty entries of this twin's OWN blit table, one per case.

    It is the table `frame_head.S` builds rather than the original's at 0x179aa, and each entry is a
    trampoline into wave A's twin — so a table transposed by one, or a trampoline that pushed the
    page and the screen the wrong way round, copies the playfield at the wrong offset: 23 KB of
    diff. Twenty cases rather than `test_frame.py`'s five, because here the table is ours."""
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START),
                                      {frame.A_MAP_COLUMN: bytes([column])})


@pytest.mark.parametrize("scroll_pos", (0, 0x8, 0xfffff8, 0x7fff8, 0x80000, 0x80008, 0xabcdef8))
def test_the_twin_folds_the_asteroid_cursor_at_sixteen_bits(scroll_pos):
    """The asteroid arm at 0x11024: `lsr.l #3` then `mulu.w #$24`, a 16x16 multiply, so only the
    shifted longword's LOW WORD is a factor. `test_frame.py`'s own sweep, either side of the fold —
    the game reaches 0x80000 after about three hours in one section, so no world sweep drives it."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_SCROLL_POS: scroll_pos.to_bytes(4, "big"),
         frame.A_ASTEROID_SECTION_FLAG: b"\x01", frame.A_BOSS_SEQUENCE_ACTIVE: b"\x00",
         frame.A_MAP_OFFSET: b"\x5a\xa5\x5a\xa5", frame.A_MAP_PTR: b"\x5a\xa5\x5a\xa5"})


def test_the_twin_clears_the_playfield_for_a_boss():
    """With the boss flag up the stage skips the scroller entirely and clears the playfield instead
    of blitting a page — one whole pass replaced by another, and the only case that reaches
    `playfield_clear`'s door at all from a non-asteroid section."""
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START),
                                      {frame.A_BOSS_SEQUENCE_ACTIVE: b"\x01"})


@pytest.mark.parametrize("scroll_pos,index",
                         ((frame.MOTHERSHIP_TRIGGER_SCROLL_POS - 1, 0),
                          (frame.MOTHERSHIP_TRIGGER_SCROLL_POS, 0),
                          (frame.MOTHERSHIP_TRIGGER_SCROLL_POS + 1, 4),
                          (frame.MOTHERSHIP_TRIGGER_SCROLL_POS, 5),
                          (frame.MOTHERSHIP_TRIGGER_SCROLL_POS, 0x0f),
                          (frame.MOTHERSHIP_TRIGGER_SCROLL_POS, 0x80)))
def test_the_twin_arms_the_mothership_at_its_own_scroll_position(scroll_pos, index):
    """`cmpi.l #$c80,$195cc` + `blt` one step either side, and both arms of the `cmp.w #$5` that
    picks `mothership_begin` over `mothership_segments_respawn`. The index is driven at 0x80 as
    well, which holds the SIGN: the trigger compares a sign-extended WORD, so 0x80 reads as -128."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_SCROLL_POS: scroll_pos.to_bytes(4, "big"),
         frame.A_MOTHERSHIP_INDEX: bytes([index]), frame.A_MOTHERSHIP_READY: b"\x00",
         frame.A_BOSS_SEQUENCE_ACTIVE: b"\x00"})


@pytest.mark.parametrize("index", (0, 4, 5, 0x7f, 0x80, 0xff))
def test_the_twin_reads_the_build_step_index_as_a_byte(index):
    """The build gate at 0x1116e is `cmp.b #$5` on a byte the instruction before SIGN-EXTENDED into
    a word — not the word compare the trigger above makes of the same global. 0x80 and 0xff are what
    separate the two, and they pick between `mothership_spawn_head` and
    `mothership_sprite_build_step`."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_MOTHERSHIP_PREP_STAGE: b"\x01", frame.A_MOTHERSHIP_INDEX: bytes([index])})


@pytest.mark.parametrize("tilt", range(7))
def test_the_twin_recentres_the_ship_tilt_from_every_frame(tilt):
    """With neither up nor down pressed the tilt bank rolls back towards its middle frame, and which
    way is a SIGNED compare against 3 — so the two arms move the ship in opposite directions and
    clamp against opposite bounds. The countdown is 1 so the roll is due on this very frame, and
    tilt 3 is the arm that returns having done nothing."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_JOYSTICK_STATE: b"\x00", frame.A_SHIP_TILT: bytes([tilt]),
         frame.A_SHIP_TILT_COUNTDOWN: b"\x01"})


@pytest.mark.parametrize("joystick", frame.JOYSTICK_BYTES)
@pytest.mark.parametrize("tilt", (0, SHIP_TILT_MAX))
def test_the_twin_moves_the_ship_in_every_direction(joystick, tilt):
    """All ten stick shapes, at both ends of the tilt bank.

    The stick drives the four movement arms, both internal `bsr`s (`ship_move_up` at 0x11318 and
    `ship_move_down` at 0x1135a, which are transcribed in place rather than doored) and the sprite
    bank selection; the tilt end-stops are what make `ship_move_up`'s `tst.b`/`beq` and
    `ship_move_down`'s `cmpi.b #$6`/`beq` take their other arm."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_JOYSTICK_STATE: bytes([joystick]), frame.A_SHIP_TILT: bytes([tilt]),
         frame.A_SHIP_TILT_COUNTDOWN: b"\x01"})


@pytest.mark.parametrize("x", (0x30, 0x41, 0x42, 0x43, 0x14f, 0x150, 0x151))
@pytest.mark.parametrize("joystick", (1 << 2, 1 << 3))
def test_the_twin_clamps_both_horizontal_arms(x, joystick):
    """The left arm's `cmpi.w #$42` + `ble` parks the pair at its home column; the right arm's
    `cmpi.w #$150` + `bge` simply stops stepping, because the two stores that would clamp it are
    UNREACHABLE. `test_frame.py`'s own sweep, one step either side of both edges on both arms.

    These are also the six instructions where gas shortens the original's `0(a2)` to `(a2)`
    (`frame_head.S`'s header names them), so if that substitution had changed a MEANING rather than
    an encoding it would show here."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_JOYSTICK_STATE: bytes([joystick]),
         frame.A_PLAYER_RECORD + frame.ENTITY_X: x.to_bytes(2, "big")})


@pytest.mark.parametrize("level", (0, 1, 2, 3))
def test_the_twin_indexes_the_speed_table_from_every_level(level):
    """`ext.w` + `lsl.l #3` into `A_ship_speed_table`, read twice (0x11216 for the recentre and
    0x11298 for the stick) and dereferenced at four different field offsets. A level that indexed
    the wrong entry moves the ship by the wrong step, which is two words of diff and nothing else —
    the smallest divergence this slice can produce."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_SHIP_SPEED_LEVEL: bytes([level]), frame.A_JOYSTICK_STATE: b"\x03"})


# ============================================================ reading frame_head.S back

# The scrapers are the family's (`asm_frame_common`): four twins ask the same questions of their own
# `.S` and `.o`. What stays here is what is THIS file's — which object, which span, and the counts.
def _head_equates():
    return common.equates(HEAD_OBJ)


# THE %a5 GLOBAL WINDOW. Both checks are `asm_frame_common`'s — one phrasing, because all four
# frame suites ask the same question of their own `.S`, and the four hand-copies this replaced had
# already started to drift in their failure text. What stays here is what is THIS twin's: which
# file, and how many globals it reaches.
WINDOWED_OPERAND_COUNT = 29


def test_the_window_scan_reads_every_global_this_twin_names():
    """The scan's positive control. `window_pin_failures` is vacuous over an empty operand list, so
    a twin whose operand shape stopped matching — a different window register, a differently named
    origin — would pass the pin below by reaching no globals at all."""
    failure = common.window_scan_failure(HEAD_S, WINDOWED_OPERAND_COUNT)
    assert failure is None, failure


def test_every_windowed_global_is_inside_the_signed_displacement():
    """THE WHOLE OF WHAT MAKES `%a5 = image + FGB` LEGAL for this twin: gas assembles a global
    outside the signed 16-bit window into a TRUNCATED displacement with no diagnostic, and the twin
    then reads or writes a wild address that the differential reports as a pixel diff a long way
    from its cause."""
    failures = common.window_pin_failures(HEAD_S)
    assert not failures, "\n".join(failures)


# ---- the constants no header owns, which test_constants.py therefore cannot pin ---------------

_C_DEFINE = re.compile(r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)u?\s*$", re.M)

# Every `.equ` in frame_head.S whose only other spelling is a `#define` in ../src/frame.c. They are
# the ones `test_constants.py` walks past — its scraper reads include/*.h — so a drift between the
# twin and its own C reference would go unnoticed there. Named explicitly rather than intersected,
# so that dropping one from the assembly fails here instead of shrinking the check.
FRAME_C_PINNED = ("JOYSTICK_UP_BIT", "JOYSTICK_DOWN_BIT", "JOYSTICK_LEFT_BIT", "JOYSTICK_RIGHT_BIT",
                  "JOYSTICK_UP_DOWN_MASK", "SHIP_TILT_CENTRE", "SHIP_X_HOME", "SHIP_X_HOME_EDGE",
                  "SHIP_X_MAX", "SHIP_X_SHADOW_HOME", "SHIP_MIRROR_X", "SHIP_MIRROR_SPRITE")


@functools.lru_cache(maxsize=None)
def _frame_c_defines():
    """{name: value} for every literal `#define` in ../src/frame.c."""
    return {name: int(value, 0) for name, value in _C_DEFINE.findall(FRAME_C.read_text())}


@pytest.mark.parametrize("name", FRAME_C_PINNED)
def test_the_constants_only_the_c_owns_match_it(name):
    """A dozen of this twin's `.equ`s name values `src/frame.c` defines for itself rather than in a
    header, so `test_constants.py::test_asm_twin_equates_match_the_headers` never looks at them —
    it reads `include/*.h`. This is the other half of that pin, over the file that IS their owner."""
    defines = _frame_c_defines()
    assert name in defines, (
        f"src/frame.c no longer defines {name}, which frame_head.S restates — either the C renamed "
        f"it (rename the `.equ` too) or this list is stale")
    assert _head_equates()[name] == defines[name], (
        f"frame_head.S's {name} assembles to {_head_equates()[name]:#x}, src/frame.c defines it as "
        f"{defines[name]:#x}")


def test_the_tilt_bank_stride_is_two_sprites():
    """`mulu.w #$c80` at 0x112ca. `src/frame.c` spells it as an EXPRESSION over
    `include/sprite.h`'s SHIP_SPRITE_GAP — one tilt frame is the ship and its shadow — so neither
    scraper above can read it, and the derivation is recomputed here instead of the value being
    restated."""
    equates = _head_equates()
    assert equates["SHIP_TILT_BANK_BYTES"] == 2 * equates["SHIP_SPRITE_GAP"]


# The one immediate in the span that NOTHING else names: the shadow's column in the right-hand
# clamp, which is dead code and which `src/frame.c` therefore does not transcribe at all. Its only
# other spelling is the original's own instruction word, so that is what it is pinned against.
SHADOW_MAX_IMMEDIATE_AT = 0x113bc


def test_the_dead_clamps_shadow_column_is_the_originals():
    """`move.w #$160,44(a2)` at 0x113ba — unreachable, transcribed anyway because the transcription
    pin asks for all 240 addresses, and pinned against the shipped binary because there is no other
    copy of the number in this workspace."""
    immediate = int.from_bytes(harness.BASE_IMAGE[SHADOW_MAX_IMMEDIATE_AT:
                                                  SHADOW_MAX_IMMEDIATE_AT + 2], "big")
    assert _head_equates()["SHIP_X_SHADOW_MAX"] == immediate


@pytest.mark.parametrize("name,value", (("HEAD_EXIT_PLAYER_GATED", HEAD_EXIT_PLAYER_GATED),
                                        ("HEAD_EXIT_FELL_THROUGH", HEAD_EXIT_FELL_THROUGH)))
def test_the_exit_flags_are_the_cs(name, value):
    """`frame_panel_scroll_and_ship_stage` returns bare 0 and 1 rather than an enum, so there is no
    header spelling for the twin's `.equ`s to be pinned against — and every case above declares its
    arm with this file's mirror of them. Both spellings are held equal here, so the two cannot
    drift apart and leave the whole exit-arm section agreeing with itself."""
    assert _head_equates()[name] == value


def test_the_pause_poll_cap_is_the_kits():
    """The middle spin carries its own cap because it is spelt out rather than wrapped in
    `sched_wait8` (`frame_head.S`, band 2). The number belongs to the kit's `os.h`, which
    `test_constants.py` does not read, so a cap that drifted would silently stop matching the C's."""
    declared = re.search(r"^#define\s+OS_SCHED_POLL_MAX\s+(\d+)u?\s*$", KIT_OS_H.read_text(), re.M)
    assert declared, f"{KIT_OS_H} no longer defines OS_SCHED_POLL_MAX"
    assert _head_equates()["OS_SCHED_POLL_MAX"] == int(declared.group(1))


# ---- the transcription pin, which here is about ORDER rather than about bytes ----------------

def test_the_twin_transcribes_the_original_instruction_for_instruction():
    """EVERY INSTRUCTION OF THE ORIGINAL, ONCE, IN ORDER — and this stands where the byte pin stands
    for the leaf twins.

    A byte pin is not available here (this file's header says why). What survives that translation
    untouched is the SEQUENCE, so this compares the two address lists whole: the original's, scraped
    out of ../../out/prg_dis.txt, against frame_head.S's own `| address` comments.

    It reads the FILE'S TEXT, so it sees BOTH arms of the pause's `#ifdef` — the six instructions
    that exist only in the target build, and which nothing else in this workspace looks at.
    """
    failure = common.transcription_failure(HEAD_S, ORIGINAL_ENTRY, ORIGINAL_END)
    assert failure is None, failure


# ============================================================ what the twin COSTS

# READ THIS BEFORE READING A RATIO HERE, because it is not a like-for-like fidelity reading.
#
# THE DOOR CHARGES NOTHING FOR A C BODY. `bench_loop` stops at the door address, the harness calls
# the host function and resumes: the stub's `jsr` and `rts` really execute and are charged, the
# core's body does not exist on this side and costs nothing. The ORIGINAL, clocked over the same
# span, executes its callees in full. So `twin / original` here is NOT the reading
# `test_asm_sprite.py` takes over a leaf, and it must not be read as a fidelity claim:
#
#   the twin's number   = the twin's OWN instructions, C-ABI frame and trampolines included, PLUS
#                         the twenty page blits (which are asm twins in this blob, not doors, so
#                         unlike every other callee here they ARE charged in full)
#   the original's      = its own instructions AND everything its `bsr`s reach
#
# WHICH IS WHY THESE BARS SIT FAR BELOW 1.00x AND wave C's DO NOT. Fourteen of this stage's fifteen
# calls are doors that cost nothing, and what they reach — the panel repaint, the column emitters,
# `playfield_clear` — is most of the original's number. So a ratio here measures what the door does
# not charge for, and NOT the fidelity of the transcription. What the pin is for is what a pin is
# always for: a deterministic number that moves when the twin's own instruction stream does. Both
# sides are Musashi cycle counts over one fixed staged world, so each reading is exact and
# repeatable, and the margins below are a handful of CYCLES.
#
#   band       original     twin    excess    measured      bar   slack
#   ordinary    154,694  108,512   -46,182   0.7014622   0.7015   5.8 cyc
#   gated       154,272  108,116   -46,156   0.7008141  0.70087   8.6 cyc
#   boss         68,102    1,320   -66,782   0.0193827   0.0195   8.0 cyc
#   asteroid     68,376    1,546   -66,830   0.0226103   0.0227   6.1 cyc
#
# THE TWO PAIRS MEASURE DIFFERENT THINGS, and the second pair is the sharper pin. `ordinary` and
# `gated` are dominated by the twenty page blits, which are asm twins in this same blob rather than
# doors and so ARE clocked in full — 107,000 of the twin's 108,500 cycles are wave A's. `boss` and
# `asteroid` reach `playfield_clear` instead, which IS a door, so their 1,320 and 1,546 cycles are
# almost exactly the twin's OWN 240 instructions and its trampolines: a 16-cycle change there is
# 1.2% of the reading rather than 0.015% of it.
#
# The bars are set from the measurement, in CYCLES and not in percent: one more register in the
# prologue's `movem` pair is 16 cycles round trip and has to redden them.
COST_BARS = {"ordinary": 0.7015, "gated": 0.70087, "boss": 0.0195, "asteroid": 0.0227}


def _cost_case(extra, expect, band):
    """Clock the ORIGINAL and the twin over one staged world, and hold the twin to that band's bar.

    The twin goes through the differential on the way, so a cost reading can never be taken from a
    call that computed the wrong thing.
    """
    world = frame.world(0, frame.WORLD_START)
    run = leaves_the_image_where_the_c_does(world, extra, expect=expect)
    stop = ORIGINAL_END if expect == HEAD_EXIT_FELL_THROUGH else frame.ENTRY_SPAWN_AND_MOVE
    image = harness.make_image(frame.world_pokes(world, extra))
    _final, _writes, regs = emu.run(bytearray(image), ORIGINAL_ENTRY, {}, stop_pc=stop,
                                    max_insns=frame.FRAME_MAX_INSNS)
    # The shared assertion, not a local restatement of it: four twin suites reading one phrasing is
    # the point of it living in asm_twins.py.
    asm_twins.assert_within_the_bar(f"{TWIN} ({band})", regs["cycles"], run.cycles, COST_BARS[band])


def test_the_twin_costs_what_it_costs_on_an_ordinary_frame():
    """The band every frame of a mapped section takes: the panel, one column emitted, one page
    blitted, the ship moved, out at 0x113c0."""
    _cost_case(None, HEAD_EXIT_FELL_THROUGH, "ordinary")


def test_the_twin_costs_what_it_costs_on_the_gated_arm():
    """The other exit: everything up to 0x111c4 and then straight out to 0x1167c, which is the whole
    of band 5 removed and is worth its own bar for it."""
    _cost_case({frame.A_EXPLOSION_GROUP_ACTIVE_BITS: bytes([1 << 1])},
               HEAD_EXIT_PLAYER_GATED, "gated")


def test_the_twin_costs_what_it_costs_clearing_the_playfield():
    """The boss band: the scroller skipped entirely and `playfield_clear` in the blit's place — the
    one band where the twenty-entry table is not reached at all."""
    _cost_case({frame.A_BOSS_SEQUENCE_ACTIVE: b"\x01"}, HEAD_EXIT_FELL_THROUGH, "boss")


def test_the_twin_costs_what_it_costs_in_an_asteroid_section():
    """The asteroid band: the derived cursor at 0x11024 instead of the tile emitter, and the
    playfield cleared rather than blitted."""
    _cost_case({frame.A_ASTEROID_SECTION_FLAG: b"\x01", frame.A_BOSS_SEQUENCE_ACTIVE: b"\x00"},
               HEAD_EXIT_FELL_THROUGH, "asteroid")
