"""The ASM-TWIN differential for the frame loop's DRONE-AND-FIRE STAGE: `../src/asm/frame_fire.S`
must leave the image byte-for-byte where its C core in `../src/frame.c` leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_frame.py` pins the C core against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_frame.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_frame.py`'S STAGING, IMPORTED RATHER THAN RESTATED — its `world` (which has the
ORACLE play a section for four frames before a case starts), its poke builders and its fuzz
generator. Importing it also installs this battery's `ctypes` signatures for the five frame glues,
which is why nothing here declares them again. The door table, the candidate arming and the three
source-reading pins are the FAMILY's and live in `asm_frame_common.py`, whose header says why.

WHAT IS THIS TWIN'S OWN, against its three wave-C/wave-D siblings.

**1. TWO ENTRY REGISTERS, and both stay parameters.** `../../include/frame.h` says why: the range
has its own entry point and a case drives it with values the globals do not hold. `ship` is %a2,
which the head slice loaded with `A_player_record`, and it travels as an image OFFSET; `joystick` is
%d0, which the head slice read out of `A_joystick_state`, and it travels as a value. Every case
below reads the joystick byte back OUT of the staged image exactly as
`test_frame.py::_check_drone_and_fire` does, so the two shores are entered with the same byte the
oracle would have.

**2. THE STAGE IS `void`, so there is no answer to compare** and `expect_ret=common.VOID_STAGE` says so: %d0 is
undefined on return and comparing it would pin a value the target does not promise. What that costs
is real — this suite has one fewer surface than `test_asm_frame.py` — and what stands in its place
is that every launcher case asserts the SHOT RECORD the door was supposed to write.

**3. ALMOST EVERY CASE STAGES THE TRAIL DRONE FLYING**, and that is load-bearing rather than
decorative. The family differential asserts the C *wrote something* (two untouched images compare
equal and would read as a pass), and this stage has real arms that write NOTHING AT ALL — a
held-and-already-charged button leaves at 0x114ae, and an unknown weapon at 0x115fc. With the
gunsight record alive the per-frame half of the drone runs first and always steps
`A_ship_pos_history_index`, so those arms can be driven at all. The two exceptions are the cases
about the drone's own gate at 0x113c8, which have to stage the gunsight DEAD and pay for it by
guaranteeing a write some other way.

**4. THERE IS NO BYTE PIN**, for `frame.S`'s reason and `frame_fire.S`'s header repeats it: the
slice names eighteen globals base-relative and position-independence re-encodes every instruction
that mentions one. What stands in its place is
`test_the_twin_transcribes_the_original_instruction_for_instruction`, which is about ORDER and
COMPLETENESS rather than encoding, plus the cost pins and the differential.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import random

import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import asm_twins
import asm_frame_common as common
import test_frame as frame

FIRE_S = common.ASM_DIR / "frame_fire.S"
FIRE_OBJ = common.BUILD_ASM / "frame_fire.o"

TWIN = "frame_drone_and_fire_stage_asm"
# The span of the original this twin transcribes. Its end is the next slice's entry, which is also
# every arm's `bra` target — the stage has no `rts` of its own.
ORIGINAL_ENTRY = frame.ENTRY_DRONE_AND_FIRE           # 0x113c0
ORIGINAL_END = frame.ENTRY_SPAWN_AND_MOVE             # 0x1167c

# `test_frame.py::_stage_head_falls_through` decides, by the original's own three player gates,
# whether the head slice runs INTO this one or branches past it to 0x1167c. Checked at import so a
# rename over there fails HERE with a sentence rather than as an AttributeError inside a case named
# for a fire arm — the same guard, for the same reason, as `test_frame.py`'s own over `test_init`.
assert hasattr(frame, "_stage_head_falls_through"), (
    "test_asm_frame_fire.py reuses test_frame._stage_head_falls_through to skip the frames the head "
    "slice does not fall through on; that name is gone, so either restore it or give this suite its "
    "own copy of the three gates at 0x111c4/0x111da/0x111e2")

# The gunsight record is entity slot 19 and doubles as the trail drone's own record
# (`include/weapon.h` names both roles). Alive, the drone's per-frame half at 0x11428 runs and
# always steps the history cursor — which is what guarantees the C wrote something. See the module
# header, point 3.
DRONE_FLYING = {frame.A_ENTITY_GUNSIGHT + frame.ENTITY_ALIVE: b"\x01"}


def _extra(*overlays):
    """One case's pokes: the flying drone, then whatever the case wants over it."""
    extra = dict(DRONE_FLYING)
    for overlay in overlays:
        extra.update(overlay)
    return extra


def leaves_the_image_where_the_c_does(world, extra, refusal_free=True):
    """This stage's arguments to the family's differential (`asm_frame_common`, which says what its
    three assertions are and what each one closes).

    What is THIS suite's own is the pair of shores. Both are entered with the head slice's two exit
    registers: `A_player_record` as %a2 — as an image OFFSET, which the twin's prologue rebases —
    and the joystick byte as %d0, read back out of the staged image exactly as
    `test_frame.py::_check_drone_and_fire` reads it, so a case that pokes the stick drives both
    sides with what it poked. There is no `expect_ret`: the stage is `void`.

    `extra` is taken AS GIVEN rather than having `_extra` folded in here, so the two cases about the
    drone's own gate — which need the gunsight DEAD — go through this one entry point like every
    other case instead of restating the pair of shores for themselves.
    """
    joystick = frame._poked(world, extra)[frame.A_JOYSTICK_STATE]
    return common.leaves_the_image_where_the_c_does(
        TWIN, world, extra,
        c_call=lambda lib, buf: lib.g_frame_drone_and_fire_stage(
            buf, frame.A_PLAYER_RECORD, joystick),
        twin_args=(frame.A_PLAYER_RECORD, joystick), expect_ret=common.VOID_STAGE, refusal_free=refusal_free)


# ============================================================ the game, played

# THE JOYSTICK IS ALTERNATED RATHER THAN DRAWN AT RANDOM, and the reason is this stage's shape: the
# button's three arms are chosen by the CHANGE in the fire bit, not by its value, so a stream that
# happened to hold fire for eight frames running would charge the shot and then take the
# already-charged arm for the rest of the sweep. Alternating walks the release arm and the fresh
# press on every other frame, and each of the ten stick shapes `test_frame.py` names is still used.
NO_FIRE = (0x00, 0x01, 0x02, 0x04, 0x08)
WITH_FIRE = (0x80, 0x81, 0x82, 0x84, 0x88)


def _played_joystick(index):
    bank = WITH_FIRE if index % 2 else NO_FIRE
    return bank[index % len(bank)]


def _played_extra(index):
    """The flying drone, plus the ring cursor walked one step per frame.

    THE CURSOR HAS TO BE DRIVEN OR THE SWEEP LEAVES IT AT ZERO, and a cursor of zero is the one
    value that hides the `ext.w` + `lsl.w #2` scaling at 0x11434 — MEASURED: with the cursor left
    where the world put it, mutating the shift to `#1` passes all sixteen sections. It is a byte the
    game itself steps every frame the drone flies, so stepping it here is the world the sweep would
    have had if this section's player had launched one.
    """
    return _extra({frame.A_SHIP_POS_HISTORY_INDEX:
                   bytes([index % frame.SHIP_POS_HISTORY_ENTRIES])})


@pytest.mark.parametrize("section", range(frame.SECTION_COUNT))
def test_the_twin_plays_the_game(section):
    """The stage, frame by frame, over each of the sixteen sections the game ships.

    THIS IS THE COMPOSITION TEST. Each frame runs the twin's 148 instructions over the whole 512 KB
    the game owns, against the C that `test_frame.py` has already proved equal to the original on
    these exact worlds — so a pass that ran a slot scan once too often, took a dispatch arm the
    other way or stepped the history ring by the wrong stride differs on real bytes.

    ONLY THE FRAMES THIS SLICE IS REACHED ON. The head slice has two exits, and on a frame where the
    ship is dead, exploding, or its death explosion is running it branches straight past this stage
    to 0x1167c — so the case is skipped there, exactly as `test_frame.py::_check_every_slice` skips
    it. Running it anyway would compare two shores over a world the game never enters here with.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for index in range(frame.WORLD_FRAMES):
        image[frame.A_JOYSTICK_STATE] = _played_joystick(index)
        extra = _played_extra(index)
        if frame._stage_head_falls_through(frame._poked(image, extra)):
            leaves_the_image_where_the_c_does(image, extra)
        image = frame.advance_one_frame(image)


@pytest.mark.parametrize("section", frame.FUZZ_SECTIONS)
def test_the_twin_fuzz(section):
    """`test_frame.py`'s own 96-case generator, replayed against the twin.

    What it reaches that the sweep above does not is the COMBINATION: the stick, the selected
    weapon, the shield's allowance, the three in-flight counters and six shot slots each alive or
    dead — which is the whole dispatch and all four slot scans, and which no dozen frames of one
    section selecting weapon 3 can walk.

    Sharded by section for `test_frame.py`'s reason: a case's cost is dominated by building its
    world, which `frame.world` caches per worker.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for case in frame.fuzz_cases_for(section):
        leaves_the_image_where_the_c_does(
            image, _extra(frame.fuzz_pokes(random.Random(ORIGINAL_ENTRY + case), image)))


# ============================================================ the fire button, every arm

# What a case has to say to reach a launcher at all: the button not yet held, fire on the stick.
FRESH_PRESS = {frame.A_FIRE_BUTTON_HELD: b"\x00",
               frame.A_JOYSTICK_STATE: bytes([frame.JOYSTICK_FIRE])}
# ...and every in-flight counter under its allowance, so the press reaches the launcher rather than
# the `bge` that falls through to the plain bullet. Which slots are free is `_shot_slots`'.
LAUNCHABLE = {frame.A_ACTIVE_COUNT_SEEKERS: b"\x00", frame.A_ACTIVE_COUNT_TYPE32: b"\x00",
              frame.A_ACTIVE_COUNT_BOMBS: b"\x00", frame.A_ACTIVE_COUNT_TYPE34: b"\x00",
              frame.A_WEAPON_POWER_LEVEL: b"\x03"}
FIRST_SHOT_SLOT = frame.A_ENTITY_TABLE
SLOT_FREE, SLOT_BUSY = 0, 1         # what a shot record's ENTITY_ALIVE holds, for `_shot_slots`

# The kind each launcher stamps into the record it takes, which is what says the DOOR WAS REACHED
# rather than the arm having quietly refused. `include/weapon.h`'s four, via `test_frame.py`.
LAUNCHED_TYPE = {frame.WEAPON_KIND_SEEKER: frame.SHOT_TYPE_SEEKER,
                 frame.WEAPON_KIND_MISSILE: frame.SHOT_TYPE_MISSILE,
                 frame.WEAPON_KIND_BOMB: frame.SHOT_TYPE_BOMB,
                 frame.WEAPON_BULLET: frame.BULLET_TYPE}


def _shot_slots(alive):
    """All six of entity slots 0..5 dead (so a scan stops at the first) or alive (so none does)."""
    return {FIRST_SHOT_SLOT + frame.ENTITY_STRIDE * slot + frame.ENTITY_ALIVE: bytes([alive])
            for slot in range(frame.PLAYER_SHOT_SLOTS)}


def _press_pokes(weapon, alive):
    """A fresh press of `weapon` with every counter under its allowance, over six shot records
    staged `alive`. Shared by the launcher cases and by their cost bands."""
    return _extra(FRESH_PRESS, LAUNCHABLE, _shot_slots(alive),
                  {frame.A_SELECTED_WEAPON: bytes([weapon])})


@pytest.mark.parametrize("weapon", (frame.WEAPON_KIND_SEEKER, frame.WEAPON_KIND_MISSILE,
                                    frame.WEAPON_KIND_BOMB, frame.WEAPON_BULLET))
@pytest.mark.parametrize("shield", (0, 1))
def test_the_twin_launches_every_weapon_from_a_fresh_press(weapon, shield):
    """THE FOUR LAUNCHERS, AND ALL FOUR DOOR SITES — one case each.

        weapon 4 (seeker)   -> 0x11536, door slot 34 `fire_seeker`
        weapon 2 (missile)  -> 0x11582, door slot 35 `fire_homing_missile`
        weapon 1 (bomb)     -> 0x115e0, door slot 36 `fire_bomb`
        weapon 3 (bullet)   -> 0x1166c, door slot 13 `sound_start` (wave C's stub, reused)

    Each at both shield levels, because the shield is what turns the allowance from one shot in
    flight into two (0x114f8 against 0x11500) and the section start leaves it at 0.

    THE ASSERTION AT THE FOOT IS THE POSITIVE CONTROL for the door: an arm that refused the press —
    a counter over its allowance, a slot scan that found nothing — leaves the record's type
    untouched, and the two shores would then agree about having done nothing. Reading the kind back
    says the launcher really ran.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = _press_pokes(weapon, SLOT_FREE)
    extra[frame.A_SHIELD_LEVEL] = bytes([shield])
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[FIRST_SHOT_SLOT + frame.ENTITY_TYPE] == LAUNCHED_TYPE[weapon], (
        f"weapon {weapon}'s press left shot slot 0 holding type "
        f"{run.image[FIRST_SHOT_SLOT + frame.ENTITY_TYPE]:#x}, not the "
        f"{LAUNCHED_TYPE[weapon]:#x} its launcher stamps — the arm refused the press, so this case "
        f"never reached the door it exists to drive")


@pytest.mark.parametrize("weapon", (frame.WEAPON_KIND_SEEKER, frame.WEAPON_KIND_MISSILE,
                                    frame.WEAPON_KIND_BOMB))
def test_the_twin_falls_through_to_the_plain_bullet(weapon):
    """`bge 0x11600` — the three counted weapons do not refuse when they are at their limit, they
    fall THROUGH to the ordinary bullet's arm, which is `test_frame.py`'s own finding.

    A twin that returned instead of falling through fires nothing here, and the bullet it should
    have launched is six stores and a tune. The counters are poked to the limit the shield level
    allows, and the bullet's own limit is opened so the fall-through is visible at all.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = _extra(FRESH_PRESS, _shot_slots(SLOT_FREE),
                   {frame.A_SELECTED_WEAPON: bytes([weapon]), frame.A_SHIELD_LEVEL: b"\x00",
                    frame.A_ACTIVE_COUNT_SEEKERS: b"\x05", frame.A_ACTIVE_COUNT_TYPE32: b"\x05",
                    frame.A_ACTIVE_COUNT_BOMBS: b"\x05", frame.A_ACTIVE_COUNT_TYPE34: b"\x00",
                    frame.A_WEAPON_POWER_LEVEL: b"\x03"})
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[FIRST_SHOT_SLOT + frame.ENTITY_TYPE] == frame.BULLET_TYPE, (
        f"weapon {weapon} at its limit left shot slot 0 holding type "
        f"{run.image[FIRST_SHOT_SLOT + frame.ENTITY_TYPE]:#x} — it did not fall through to the "
        f"plain bullet at 0x11600")


UNKNOWN_WEAPON = 7        # none of the four the dispatch compares against


def test_the_twin_fires_nothing_for_an_unknown_weapon():
    """`cmpi.b #$3,$198b4` + `bne 0x1167c` at 0x115fc — the fourth compare is the one arm of the
    dispatch with no `bra` to the bullet, so a weapon byte that is none of the four leaves the press
    having launched nothing at all.

    A twin whose default fell into 0x11600 would fire a bullet here, which the six free slots and
    the opened power level below make a diff of a whole record.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = _press_pokes(UNKNOWN_WEAPON, SLOT_FREE)
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[FIRST_SHOT_SLOT + frame.ENTITY_ALIVE] == 0, (
        "an unknown weapon's press launched something into shot slot 0 — the dispatch's default "
        "arm fell through to the bullet at 0x11600 instead of leaving at 0x1167c")


@pytest.mark.parametrize("weapon", (frame.WEAPON_KIND_SEEKER, frame.WEAPON_KIND_MISSILE,
                                    frame.WEAPON_KIND_BOMB, frame.WEAPON_BULLET))
def test_the_twin_gives_up_a_press_when_every_shot_slot_is_busy(weapon):
    """The four exhausted `dbf` arms — 0x11524, 0x11592, 0x115f0 and 0x11678 — one per weapon.

    All six of entity slots 0..5 alive, so every scan walks its whole six records and leaves through
    the tail rather than through a launcher. THE FOUR SCANS ARE NOT ONE ROUTINE: the seeker's spells
    it with `beq` OUT of the loop and the other three with `bne` ROUND it, and the bomb's reloads
    `A_entity_table` at 0x115c6 that the loop already holds — so a twin that shared one scan between
    them would still walk six records and would still be caught by whichever arm it got wrong.

    No played frame reaches these: the sweep above always has a free shot slot.
    """
    world = frame.world(0, frame.WORLD_START)
    leaves_the_image_where_the_c_does(world, _press_pokes(weapon, SLOT_BUSY))


# The charge state a released button clears, seeded to values nothing else produces so all five
# stores are diffed rather than being no-ops over an already-zero world.
CHARGED_STATE = {frame.A_FIRE_BUTTON_HELD: b"\x01", frame.A_FIRE_CHARGE_COUNTER: b"\x05",
                 frame.A_FIRE_CHARGED: b"\x01", frame.A_PALETTE_HW_SHADOW: b"\x02\x22",
                 frame.A_CHARGE_FLASH_DIR: b"\x01"}


@pytest.mark.parametrize("joystick", NO_FIRE)
def test_the_twin_clears_the_charge_state_when_the_button_is_released(joystick):
    """`tst.b d0` + `bmi` at 0x11478 — bit 7 of the stick byte, and everything else on it is a
    DIRECTION this arm must ignore. Five stores follow, and all five are seeded non-zero above so a
    twin that dropped one differs by that byte."""
    world = frame.world(0, frame.WORLD_START)
    extra = _extra(CHARGED_STATE, {frame.A_JOYSTICK_STATE: bytes([joystick])})
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[frame.A_FIRE_BUTTON_HELD] == 0 and run.image[frame.A_FIRE_CHARGED] == 0, (
        "a released button left the charge state standing — the case staged the wrong arm")


@pytest.mark.parametrize("charge", (0, 1, frame.FIRE_CHARGE_FULL - 2, frame.FIRE_CHARGE_FULL - 1,
                                    frame.FIRE_CHARGE_FULL, 0xff))
def test_the_twin_counts_a_held_button_up_to_a_charged_shot(charge):
    """`addi.b #$1,$19901` + `cmpi.b #$8` at 0x114ba — an EQUALITY test on the stepped byte, so 7
    arms the charged weapon, 8 steps past it and keeps counting, and 0xff wraps to 0 rather than
    arming. The button is already HELD, which is the arm that runs the counter at all."""
    world = frame.world(0, frame.WORLD_START)
    extra = _extra({frame.A_FIRE_BUTTON_HELD: b"\x01", frame.A_FIRE_CHARGED: b"\x00",
                    frame.A_FIRE_CHARGE_COUNTER: bytes([charge]),
                    frame.A_JOYSTICK_STATE: bytes([frame.JOYSTICK_FIRE])})
    leaves_the_image_where_the_c_does(world, extra)


def test_the_twin_leaves_a_charged_button_alone():
    """`tst.b $19902` + `bne 0x1167c` at 0x114ae — held AND already charged, which is the stage's
    one arm that writes nothing of its own at all. Only the flying drone above it makes the case
    runnable; the module header, point 3, says why that matters."""
    world = frame.world(0, frame.WORLD_START)
    extra = _extra({frame.A_FIRE_BUTTON_HELD: b"\x01", frame.A_FIRE_CHARGED: b"\x01",
                    frame.A_FIRE_CHARGE_COUNTER: b"\x05",
                    frame.A_JOYSTICK_STATE: bytes([frame.JOYSTICK_FIRE])})
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[frame.A_FIRE_CHARGE_COUNTER] == 5, (
        "the already-charged arm stepped the charge counter — it did not leave at 0x114ae")


# ============================================================ the trail drone

HISTORY_BYTES = frame.SHIP_POS_HISTORY_ENTRIES * frame.SHIP_POS_HISTORY_ENTRY_BYTES
UNMOVED_CURSOR = 3      # a mid-ring cursor the skipped-drone case reads back unchanged


def _seeded_history(seed):
    """Ten {x, y} pairs of pseudorandom bytes, so a drone that read the ring before priming it flies
    somewhere the ship has never been."""
    return bytes(random.Random(seed).randbytes(HISTORY_BYTES))


def test_the_twin_launches_the_trail_drone():
    """THE LAUNCH HALF, 0x113dc..0x11426 — one of the two cases that stage the gunsight DEAD.

    Weapon 4 with the drone's slot dead: the launch stamps the record, primes all ten history pairs
    with the ship's own position, clears the cursor and the seeker count, and only THEN reads the
    oldest pair back. A twin that read the ring before priming it flies the drone to wherever the
    seeded history below points, which is a diff of tens of bytes.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = {frame.A_SELECTED_WEAPON: bytes([frame.WEAPON_KIND_SEEKER]),
             frame.A_ENTITY_GUNSIGHT + frame.ENTITY_ALIVE: b"\x00",
             frame.A_TRAIL_DRONE_ACTIVE: b"\x00",
             frame.A_SHIP_POS_HISTORY: _seeded_history(ORIGINAL_ENTRY),
             frame.A_SHIP_POS_HISTORY_INDEX: b"\x5a"}
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[frame.A_TRAIL_DRONE_ACTIVE] == 1, (
        "the drone was not launched — the case staged a gunsight the 0x113c8 gate skipped")


def test_the_twin_does_not_launch_the_drone_for_another_weapon():
    """`cmpi.b #$4,$198b4` + `bne 0x11474` at 0x113d8 — a dead gunsight and any weapon but the
    seeker skips the WHOLE drone, per-frame half included, and goes straight to the button. It is
    the arm the played sweep would take if it did not stage the drone flying."""
    world = frame.world(0, frame.WORLD_START)
    extra = {frame.A_SELECTED_WEAPON: bytes([frame.WEAPON_BULLET]),
             frame.A_ENTITY_GUNSIGHT + frame.ENTITY_ALIVE: b"\x00",
             frame.A_SHIP_POS_HISTORY: _seeded_history(ORIGINAL_END),
             frame.A_SHIP_POS_HISTORY_INDEX: bytes([UNMOVED_CURSOR]),
             # ...and the button RELEASED over a charge state that still stands, which is what makes
             # the case write anything at all with the whole drone half skipped.
             **CHARGED_STATE, frame.A_JOYSTICK_STATE: b"\x00"}
    run = leaves_the_image_where_the_c_does(world, extra)
    assert run.image[frame.A_SHIP_POS_HISTORY_INDEX] == UNMOVED_CURSOR, (
        "the history cursor moved with the drone dead and weapon 3 selected — 0x113d8 did not skip "
        "the per-frame half")


@pytest.mark.parametrize("index", (0, 1, frame.SHIP_POS_HISTORY_ENTRIES - 2,
                                   frame.SHIP_POS_HISTORY_ENTRIES - 1,
                                   frame.SHIP_POS_HISTORY_ENTRIES, 0xff))
def test_the_twin_wraps_the_drone_history_cursor(index):
    """`addi.b #$1,$198ff` + `cmpi.b #$a` at 0x11462 — an EQUALITY test, so a cursor already AT ten
    steps to eleven and is left there, and 0xff wraps to zero and is left there too.

    0xff also drives the `ext.w` at 0x11434, which is a SIGNED widen: the cursor is read as -1 and
    the ring is indexed four bytes BELOW its base. A twin that widened it unsigned would index
    0x3fc bytes above instead, and the whole read and write-back would land somewhere else.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = _extra({frame.A_SHIP_POS_HISTORY_INDEX: bytes([index]),
                    frame.A_SHIP_POS_HISTORY: _seeded_history(frame.A_SHIP_POS_HISTORY + index)})
    leaves_the_image_where_the_c_does(world, extra)


def test_the_twin_carries_the_drone_offset_across_the_word_boundary():
    """`add.l #$800005,d1` at 0x1143c on the packed {x, y} pair, so a y that overflows its word
    CARRIES INTO X. The pair is poked to a y one step below the wrap, which is the only input that
    tells the longword add apart from two word adds."""
    world = frame.world(0, frame.WORLD_START)
    carry_y = 0x10000 - (frame.TRAIL_DRONE_OFFSET_PACKED & 0xffff) + 1
    extra = _extra({frame.A_SHIP_POS_HISTORY_INDEX: b"\x00",
                    frame.A_SHIP_POS_HISTORY: (0x0040).to_bytes(2, "big")
                                              + carry_y.to_bytes(2, "big")})
    leaves_the_image_where_the_c_does(world, extra)


# ============================================================ reading frame_fire.S back

# The scrapers are the family's (`asm_frame_common`): four twins ask the same three questions of
# their own `.S` and `.o`, and four copies of the parsing would be four ways to disagree about what
# an `.equ` or an `| 0xxxxx` comment is. What stays here is what is THIS file's: which object, which
# span of the original, and the count below.
def _fire_equates():
    return common.equates(FIRE_OBJ)


# THE %a5 GLOBAL WINDOW. Both checks are `asm_frame_common`'s — one phrasing, because all four
# frame suites ask the same question of their own `.S`, and the four hand-copies this replaced had
# already started to drift in their failure text. What stays here is what is THIS twin's: which
# file, and how many globals it reaches.
WINDOWED_OPERAND_COUNT = 18


def test_the_window_scan_reads_every_global_this_twin_names():
    """The scan's positive control. `window_pin_failures` is vacuous over an empty operand list, so
    a twin whose operand shape stopped matching — a different window register, a differently named
    origin — would pass the pin below by reaching no globals at all."""
    failure = common.window_scan_failure(FIRE_S, WINDOWED_OPERAND_COUNT)
    assert failure is None, failure


def test_every_windowed_global_is_inside_the_signed_displacement():
    """THE WHOLE OF WHAT MAKES `%a5 = image + FGB` LEGAL for this twin: gas assembles a global
    outside the signed 16-bit window into a TRUNCATED displacement with no diagnostic, and the twin
    then reads or writes a wild address that the differential reports as a pixel diff a long way
    from its cause."""
    failures = common.window_pin_failures(FIRE_S)
    assert not failures, "\n".join(failures)


def test_the_twin_transcribes_the_original_instruction_for_instruction():
    """EVERY INSTRUCTION OF THE ORIGINAL, ONCE, IN ORDER — and this stands where the byte pin stands
    for the leaf twins.

    A byte pin is not available here (the module header says why: almost every instruction of the
    slice names a global, and position-independence re-encodes all of them). What survives that
    translation untouched is the SEQUENCE, so this compares the two address lists whole: the
    original's, scraped out of ../../out/prg_dis.txt, against frame_fire.S's own `| address`
    comments.

    It catches what a differential cannot: an instruction dropped on a path the game's own data
    never takes, one transcribed twice, an arm moved in front of another, a comment left naming an
    address the line no longer transcribes.
    """
    failure = common.transcription_failure(FIRE_S, ORIGINAL_ENTRY, ORIGINAL_END)
    assert failure is None, failure


# ============================================================ what the twin COSTS

# READ THIS BEFORE READING A RATIO HERE, because it is not the reading the leaf twin suites take.
#
# THE DOOR CHARGES NOTHING FOR A C BODY. `bench_loop` stops at the door address, the harness calls
# the host function and resumes: the stub's `jsr` and `rts` really execute and are charged, the
# core's body does not exist on this side and costs nothing. The ORIGINAL, clocked over the same
# span, executes `fire_seeker`, `fire_homing_missile`, `fire_bomb` and `sound_start` IN FULL. So
# `twin / original` here is NOT a like-for-like fidelity claim, and the two launcher bands below
# read far BELOW 1.00x for exactly that reason and for no other:
#
#   the twin's number   = the twin's OWN instructions, C-ABI frame and three trampolines included
#   the original's      = its own instructions AND everything its four `bsr`s reach
#
# WHAT THE PIN IS FOR is what a pin is always for: a deterministic number that moves when the twin's
# own instruction stream does. Both sides are Musashi cycle counts over one fixed staged world, so
# each reading is exact and repeatable, and the margins are a handful of CYCLES — one extra register
# in the prologue's `movem` is 16 cycles round trip and reddens every band.
#
# THE TWO CALL-FREE BANDS ARE THEREFORE THE FIDELITY READING, and they are the ones that matter:
# `released` and `busy_scan` reach no door at all, so both shores execute the same work.
#
#   band                        original   twin   excess   measured      bar   slack
#   the button released              428    598     +170    1.39720   1.4135   6.9 cyc
#   every shot slot busy             822    968     +146    1.17762   1.1861   7.0 cyc
#   the plain bullet, fired         1432   1152     -280    0.80447   0.8093   6.9 cyc
#   the seeker, launched            1206    922     -284    0.76451   0.7703   6.9 cyc
#
# THE FIRST TWO RATIOS ARE NOT A REGRESSION AND THE FIXED COST IS WHY. The excess on both is the
# SAME +146 to +170 cycles, and it is the C-ABI frame the original does not have: a seven-register
# `movem.l` pair is 64 + 68 = 132 cycles on its own, and the prologue's two `movea`/`adda` pairs and
# the `rts` are the rest. This slice's whole span is 428 cycles at its shortest, so that fixed cost
# is a THIRD of it — where wave A's page blits were 110,000 cycles a call and the same frame was a
# quarter of one percent. The base-relative globals do pull the other way (`tst.b d16(An)` is 12
# against `tst.b abs.l`'s 14, `move.b #imm,d16(An)` 16 against 20, `lea d16(An),An` 8 against 12) and
# that is what holds the excess to 146 on the longer of the two; they do not come close to paying
# for a `movem` pair. A bar quoted as a percentage would be meaningless here for the same reason —
# hence CYCLES, and hence a seven-cycle margin on every band rather than a proportional one.
#
# THE SLACK IS SEVEN CYCLES, which is what makes these bars a gate rather than a restatement of
# today's number: one more register in the prologue's `movem` pair is 16 cycles and reddens all
# four. The measurement is deterministic — Musashi counts cycles and `frame.world` is the oracle's
# own output — so the margin is for a legitimate re-translation, not for noise.
COST_BARS = {"released": 1.4135, "busy_scan": 1.1861, "bullet": 0.8093, "seeker": 0.7703}


def _cost_case(extra, band):
    """Clock the ORIGINAL and the twin over one staged world, and hold the twin to that band's bar.

    The twin goes through the differential on the way, so a cost reading can never be taken from a
    call that computed the wrong thing. The original is entered with the head slice's own two
    registers and stopped at 0x1167c, which is where every arm of the stage leaves.
    """
    world = frame.world(0, frame.WORLD_START)
    run = leaves_the_image_where_the_c_does(world, extra)
    joystick = frame._poked(world, extra)[frame.A_JOYSTICK_STATE]
    image = harness.make_image(frame.world_pokes(world, extra))
    _final, _writes, regs = emu.run(bytearray(image), ORIGINAL_ENTRY,
                                    {"d0": joystick, "a2": frame.A_PLAYER_RECORD},
                                    stop_pc=ORIGINAL_END, max_insns=frame.FRAME_MAX_INSNS)
    # The shared assertion, not a local restatement of it: four twin suites reading one phrasing is
    # the point of it living in asm_twins.py.
    asm_twins.assert_within_the_bar(f"{TWIN} ({band})", regs["cycles"], run.cycles,
                                    COST_BARS[band])


def test_the_twin_costs_what_it_costs_with_the_button_released():
    """The shortest band there is: the flying drone and the five clears, no door and no slot scan.
    It is where the C-ABI frame weighs most, and the table above says by how much."""
    _cost_case(_extra(CHARGED_STATE, {frame.A_JOYSTICK_STATE: b"\x00"}), "released")


def test_the_twin_costs_what_it_costs_scanning_every_shot_slot():
    """The longest CALL-FREE band: a press with all six records busy, so the bomb's scan walks its
    whole `dbf` and leaves through 0x115f0 without reaching a door. Both shores execute the same
    work here, which is what makes it the fidelity reading of the four."""
    _cost_case(_press_pokes(frame.WEAPON_KIND_BOMB, SLOT_BUSY), "busy_scan")


@pytest.mark.parametrize("band,weapon", (("bullet", frame.WEAPON_BULLET),
                                         ("seeker", frame.WEAPON_KIND_SEEKER)))
def test_the_twin_costs_what_it_costs_launching(band, weapon):
    """The two banded launcher paths, and the two readings BELOW 1.00x. The comment above says why
    that is not a fidelity claim: the original runs `sound_start` and `fire_seeker` in full and the
    door charges the emulated machine nothing for the C body. What they still pin is the twin's own
    instruction stream over the dispatch, the slot scan and the trampoline."""
    _cost_case(_press_pokes(weapon, SLOT_FREE), band)
