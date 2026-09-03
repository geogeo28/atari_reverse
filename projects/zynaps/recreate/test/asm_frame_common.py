"""What every asm twin of the FRAME LOOP shares: the callback door's table, the candidate arming,
and the three source-reading pins that stand where a byte pin cannot.

WHY THIS MODULE EXISTS. The frame loop is one `bra` chain with no `rts` in it, cut into five slices
(`include/frame.h`), and ALL FIVE now have twins in `../src/asm/`:

    frame_head.S    [0x10f4e, 0x113c0)  frame_panel_scroll_and_ship_stage   wave D
    frame_fire.S    [0x113c0, 0x1167c)  frame_drone_and_fire_stage          wave D
    frame_spawn.S   [0x1167c, 0x11c00)  frame_spawn_and_move_stage          wave D
    frame_draw.S    [0x11c00, 0x11d30)  frame_draw_objects_and_collide      wave E
    frame.S         [0x11d30, 0x1296e)  frame_resolve_hits_and_game_state   wave C

All five slices are now twinned, and the two that SHIP are wave C's and wave E's.

They assemble into ONE blob (`kit.mk`'s `$(ASM_ELF)` globs `src/asm/*.S`), so they share one door
slot namespace and one set of harness models — and five copies of the machinery below would be five
places for those to drift. Each suite keeps what is its own: its cases, its byte spans, its cost
bars, its exit contract.

THE DOOR TABLE IS THE FAMILY'S, NOT ONE FILE'S, and `test_asm_frame_doors.py` is what pins it: the
union of every `.equ ZY_DOOR_*` across the five files must be exactly this table, with no slot
naming two callees. A per-file table would let `frame_head.S` and `frame_spawn.S` each claim slot 18
for a different core and stay green until the day one of them called the other's stub.
"""
import collections
import contextlib
import functools
import re
from pathlib import Path

import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import loader
import test_frame as frame
from recreate_kit import harness as kit_harness
from recreate_kit.asm_twin import AsmTwins, DoorCallback, elf_symbols

REC = Path(__file__).resolve().parents[1]
ASM_DIR = REC / "src" / "asm"
BUILD_ASM = REC / "build" / "asm"
PRG_DIS = REC.parent / "out" / "prg_dis.txt"


# ============================================================ the callback door

# EVERY C CORE ANY FRAME TWIN CALLS, plus the kit seams that can only ever be host code.
#
# `nargs` INCLUDES the image pointer wherever `takes_image` is true, and every row is the core's own
# C prototype in ../include or in tools/recreate_kit/include. The SLOT NUMBERS are the `.equ
# ZY_DOOR_*` in `src/asm/frame*.S` and are pinned against them by `test_asm_frame_doors.py`, so this
# table and the assembly cannot drift apart in silence: a table that renumbered would send every case
# to the wrong host function with nothing but a diff to say so.
#
# `returns=False` is a core declared `void`. The door then POISONS D0 rather than publishing the
# host's arbitrary return register, so a stub that branched on a value the machine leaves undefined
# fails here instead of flaking on target.
#
# `takes_image=False` is the cores that touch HARDWARE or a device rather than the image: their
# argument 0 is a register address or a command byte, and substituting a host pointer over it would
# corrupt exactly the value they need.
#
# SLOTS 0-17 ARE WAVE C'S and are not renumbered — `frame.S` spells them and four of its stubs are
# reused verbatim by the wave-D twins (a slot names a HOST FUNCTION, so two twins calling the same
# core name the same slot). 18 up are wave D's, grouped by the file that introduced them.
DOOR_TABLE = {
    # ---- wave C: frame.S, [0x11d30, 0x1296e) ----
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
    # ---- wave D: frame_head.S, [0x10f4e, 0x113c0) ----
    18: DoorCallback("draw_score_panel", 2, returns=False),
    19: DoorCallback("draw_lives_icons", 1, returns=False),
    20: DoorCallback("hud_draw_logo_anim", 1, returns=False),
    21: DoorCallback("hud_draw_powerup_icon", 1, returns=False),
    22: DoorCallback("hud_draw_weapon_icon", 2, returns=False),
    23: DoorCallback("draw_power_gauge", 1, returns=False),
    24: DoorCallback("scroll_emit_tile_column", 4),
    25: DoorCallback("scroll_emit_column_shift2", 4, returns=False),
    26: DoorCallback("scroll_emit_column_shift0", 4, returns=False),
    27: DoorCallback("mothership_begin", 1, returns=False),
    28: DoorCallback("mothership_segments_respawn", 1, returns=False),
    29: DoorCallback("mothership_spawn_head", 1, returns=False),
    30: DoorCallback("mothership_sprite_build_step", 1, returns=False),
    31: DoorCallback("playfield_clear", 1, returns=False),
    32: DoorCallback("sched_poll8", 3),
    33: DoorCallback("os_refused", 1, takes_image=False),
    # ---- wave D: frame_fire.S, [0x113c0, 0x1167c) ----
    34: DoorCallback("fire_seeker", 4, returns=False),
    35: DoorCallback("fire_homing_missile", 2, returns=False),
    36: DoorCallback("fire_bomb", 3, returns=False),
    # ---- wave D: frame_spawn.S, [0x1167c, 0x11c00) ----
    37: DoorCallback("explosion_animate_all", 1, returns=False),
    38: DoorCallback("anim_ground_objects", 1, returns=False),
    39: DoorCallback("rand16", 1),
    40: DoorCallback("wavescript_spawn_wave", 6, returns=False),
    41: DoorCallback("wavescript_spawn_trio_type0e", 2, returns=False),
    42: DoorCallback("groundscript_spawn_type10", 3, returns=False),
    43: DoorCallback("groundscript_spawn_type0f", 3, returns=False),
    44: DoorCallback("enemies_animate_all", 1, returns=False),
    45: DoorCallback("enemies_move_all", 1, returns=False),
    46: DoorCallback("seeker_update", 2, returns=False),
    47: DoorCallback("homing_missile_update", 2, returns=False),
    48: DoorCallback("player_shot_update_all", 1, returns=False),
    49: DoorCallback("squadron_spawn_tick", 1, returns=False),
    50: DoorCallback("asteroids_move", 1, returns=False),
    51: DoorCallback("asteroids_animate", 1, returns=False),
    52: DoorCallback("mothership_move_and_place", 1, returns=False),
    53: DoorCallback("mothership_draw", 1, returns=False),
    54: DoorCallback("entity_type_in_mask", 3),
    55: DoorCallback("entity_apply_velocity", 2, returns=False),
    56: DoorCallback("entity_kill_if_offscreen", 2, returns=False),
    57: DoorCallback("angle_to_target", 3),
    58: DoorCallback("entity_set_velocity_from_angle", 4, returns=False),
    59: DoorCallback("entity_steer_toward_target", 2, returns=False),
    # ---- wave E: frame_draw.S, [0x11c00, 0x11d30) ----
    60: DoorCallback("asteroids_draw", 1, returns=False),
    61: DoorCallback("mothership_segments_update", 1, returns=False),
}

_TWINS = None


def twins():
    """The assembled blob with the FAMILY's door table, loaded once per worker.

    Its own instance rather than `asm_twins.twins()`: that one is shared by the leaf suites and is
    built with no table at all, so a frame case run through it would jump into the band, execute the
    zeros there and die as a sentinel timeout naming neither the door nor the callee.
    `AsmTwins.require()` raises with the build command if the twins were never assembled — LOUD
    rather than skipped, since a skip would look like coverage.
    """
    global _TWINS
    if _TWINS is None:
        _TWINS = AsmTwins(BUILD_ASM, loader.IMAGE_SIZE, callbacks=DOOR_TABLE, lib=harness._lib)
    return _TWINS


@contextlib.contextmanager
def door_traffic():
    """Count every callback the twin makes, by name, for the duration of the block.

    THE ONLY WAY TO SEE THAT A CASE REACHED AN ARM AT ALL. Forty of this twin's forty-four calls go
    through the door, most of them behind a branch a played frame does not take, and a case that
    staged the wrong world would otherwise pass by comparing two images on which neither shore did
    the thing the case is named for. The image diff cannot report it: a door nobody reached leaves no
    trace to differ.

    THE FAMILY'S, NOT ONE SUITE'S. It uses nothing stage-specific, and the three other frame twins
    have the same problem — `frame_head.S` drives seventeen doors and `frame_fire.S` four, most
    behind a branch. Left in one suite it would be re-implemented rather than found, giving two
    monkeypatches of one private attribute.

    It WRAPS `AsmTwins._hosts` rather than replacing it — each entry still calls the same host C with
    the same arguments and returns the same answer — and puts the original mapping back on the way
    out, so nothing about the run changes but that the calls are tallied. Reaching into that
    attribute is the price: the kit has no public hook, and modelling the traffic from outside would
    be modelling exactly what is under test.
    """
    blob = twins()
    hits = collections.Counter()
    saved = dict(blob._hosts)

    def counted(name, host):
        def call(*args):
            hits[name] += 1
            return host(*args)
        return call

    blob._hosts = {slot: counted(DOOR_TABLE[slot].name, host) for slot, host in saved.items()}
    try:
        yield hits
    finally:
        blob._hosts = saved


# ============================================================ arming the candidate

# The frame's two busy-waits and the pause's three, flattened once into the pair of arrays both
# models take. Spelt from `test_frame.py`'s own FRAME_SCHED/WAIT_SITES so every twin's waits are
# released exactly where the C battery releases them.
SCHEDULE = emu.schedule_entries(list(frame.FRAME_SCHED))
WAIT_SITES = emu.wait_site_pcs(list(frame.FRAME_SCHED), list(frame.WAIT_SITES))


def arm_the_candidate():
    """Everything `harness.differential` installs before a candidate run, done here for BOTH runs.

    The models the frame stages reach are GLOBAL STATE in the candidate `.so`, and each is left
    consumed by the run that used it — the schedule's entries fired, the wait sites' poll counts
    spent, the ledgers full. Re-arming between the C run and the twin's is therefore not hygiene but
    the comparison itself: an unarmed second run would poll to `OS_SCHED_POLL_MAX`, skip whatever the
    wait guards and differ from the first for a reason that has nothing to do with the transcription.

    `_seed_candidate_hw(None)` inside it is the one that looks like a no-op and is not: `g_hw_reset`
    is what installs `os.h`'s model DEFAULTS, and the ACIA's "transmitter empty" is one of them.
    Never called, the byte reads undeclared, `ikbd_send_cmd` spins to `IKBD_TX_POLL_MAX` and tallies
    seventeen refusals — measured.

    `kit_harness.arm_candidate` IS `differential`'s own block, made public for this caller — so the
    day the kit grows another model to arm, every frame suite gets it. A hand copy here would stay
    green without it: both shores of the comparison would be armed by the same stale block,
    symmetric and wrong, and the byte diff would prove nothing while reporting success.
    """
    # READ AT CALL TIME, NOT BOUND AS DEFAULTS. `test_asm_frame_head.py`'s pause cases need a
    # schedule that releases three spins this module's default does not name, and they get it by
    # patching SCHEDULE/WAIT_SITES here. A default-argument binding would freeze the module's own
    # pair at import and ignore the patch, with no signature change to warn anyone; an earlier
    # revision took the pair as arguments instead, and no caller ever passed them.
    kit_harness.arm_candidate(scheduled=SCHEDULE, sites=WAIT_SITES)


# ============================================================ the shared differential

VOID_STAGE = object()   # `expect_ret` for a stage whose C is `void` — see the docstring below


def leaves_the_image_where_the_c_does(twin_symbol, image, extra, c_call, twin_args,
                                      expect_ret=VOID_STAGE, refusal_free=True):
    """The whole differential for one frame twin over one staged world, compared whole.

    Three assertions, and each closes a hole the other two leave:

      the IMAGE      all 1 MiB of it, so a byte the twin computes differently anywhere fails here.
                     The C is asserted to have CHANGED the image first — every frame stage writes
                     something, so a case in which it wrote nothing is a staging fault, and two
                     untouched images would compare equal.
      the ANSWER     `%d0` against the C's return, for the two stages that HAVE one (the head slice's
                     exit flag, the resolve stage's `frame_exit`). A stage whose C is `void` has no
                     answer — its D0 is undefined on target and must not be compared — and says so
                     by passing `expect_ret=VOID_STAGE` explicitly. It is NOT the default-by-omission
                     it used to be: this is the only surface an exit arm has (the head slice's three
                     gates sit after every byte it writes, so a twin taking the wrong arm leaves a
                     byte-identical image), and a caller that simply forgot the argument would lose
                     it with three green assertions. `None` is a legal expected value and is
                     compared like any other.
      the REFUSALS   both sides made the SAME number of refused `os_*` calls. A refused call means
                     the TOS model declined to serve the candidate and the run tested nothing —
                     `harness._vet_no_os_refusal`'s argument, one shore over. `refusal_free=False`
                     is for a case whose refusals are a shared C CORE's rather than the twin's; the
                     equality still holds and the count is then the control.

    `c_call` runs the C glue against a candidate buffer and answers what it returned; `twin_args`
    are the twin's own C arguments after the image. `expect_ret` is DECLARED rather than read back,
    so a case that staged the wrong world fails saying which arm it wanted instead of quietly
    agreeing with itself.
    """
    staged = harness.make_image(frame.world_pokes(image, extra))

    arm_the_candidate()
    buf = harness.candidate_image(staged)
    c_ret = c_call(harness._lib, buf)
    c_image, c_refusals = bytes(buf), harness._lib.g_os_refusal_count()
    assert c_image != bytes(staged), (
        "the C core wrote nothing, so comparing the twin against it tests nothing — the case is "
        "staged wrong or the glue was not called")
    if expect_ret is not VOID_STAGE:
        assert c_ret == expect_ret, (
            f"the C core answered {c_ret}, not the {expect_ret} this case says it stages")

    arm_the_candidate()
    run = twins().call(staged, twin_symbol, *twin_args)
    twin_refusals = harness._lib.g_os_refusal_count()

    if run.image != c_image:
        diffs = [(at, c_image[at], run.image[at])
                 for at in range(len(c_image)) if c_image[at] != run.image[at]]
        pytest.fail(f"{twin_symbol} diverges from the C core in {len(diffs)} bytes (C, then asm)\n"
                    f"{harness.report(diffs)}")
    if expect_ret is not VOID_STAGE:
        assert run.d0 == c_ret, (
            f"{twin_symbol} answered {run.d0}, the C core {c_ret} — the image is identical, so this "
            f"is an exit arm returning the wrong value and nothing else here can see it")
    assert twin_refusals == c_refusals, (
        f"the twin made {twin_refusals} refused os_* call(s) and the C core {c_refusals} — the two "
        f"shores did not run the same models, so the byte comparison above proves nothing")
    if refusal_free:
        assert c_refusals == 0, (
            f"{c_refusals} refused os_* call(s) — the TOS model declined to serve the candidate, so "
            f"neither side was tested. {kit_harness.refusal_hints()}")
    return run



# ============================================================ reading a twin's source back

def equates(obj_path):
    """{name: value} for every `.equ` in one twin's object, as the ASSEMBLER computed it.

    Read out of the object rather than parsed out of the source: an `.equ` is an absolute symbol
    ('a' in `nm`), so this is the value the displacements were really assembled with, and a scraper
    that misread one cannot make a window pin agree with itself. Which value each name OUGHT to hold
    is `test_constants.py::test_asm_twin_equates_match_the_headers`'s question.
    """
    obj_path = Path(obj_path)
    assert obj_path.exists(), (
        f"{obj_path} is missing — build the twins with `make asm` (which `make test` runs first)")
    return _equates_at(obj_path, obj_path.stat().st_mtime_ns)


@functools.lru_cache(maxsize=None)
def _equates_at(obj_path, mtime_ns):
    """`equates()` memoised on the object's CONTENT, not just its name.

    The mtime is in the key on purpose. Every door-slot and window pin is checked against these
    values, and a cache keyed on the path alone would go on answering with the symbols of a blob
    that has since been re-assembled — so `pytest --looponfail`, a session that shells out to
    `make asm`, or a REPL held open across a rebuild would validate the NEW stub addresses against
    the OLD slot numbers and pass. `elf_symbols` over four small objects is cheap; the correctness
    is not negotiable.
    """
    del mtime_ns                                    # in the key, not in the body
    return {name: value for name, (value, kind) in elf_symbols(obj_path).items() if kind == "a"}


def source_without_comments(s_path):
    """One `.S` with its `|` comments stripped, for the operand scans below."""
    return "\n".join(line.split("|", 1)[0] for line in Path(s_path).read_text().splitlines())


# THE FAMILY'S ONE CONVENTION FOR REACHING A GLOBAL, and this module is where it is spelt.
#
# Every frame twin reserves a base register holding `image + FGB` and writes each global as
# `NAME-FGB(<reg>)`, a 68000 `d16(An)`. The ORIGIN is the family's and is hardcoded; the REGISTER is
# per file, because it has to be: four twins reserve `%a5` and `frame_draw.S` reserves `%a0`, and
# not by preference — the slice it transcribes uses every address register the 68000 has, and the
# only one whose live range leaves a gap is `%a0`. Keeping the original's `%a5`/`%a6` unpermuted is
# what lets fifty bytes of that twin be byte-identical to the original's machine code, which is a
# check no other frame twin has.
#
# EACH SUITE DECLARES ITS TWIN'S REGISTER, and there is no default — deliberately. A default is a
# way for a suite to be silently wrong about the file it is checking: the scan would find no operand
# on the register it was told about, `window_pin_failures` would iterate an empty list, and every
# global in that twin would go displacement-unchecked with three green assertions to say so.
#
# THE SCAN IS REGISTER-AGNOSTIC AND THE CHECK IS THE COMPARISON, which is the second half of the
# same hole: scanning only the declared register cannot see a line that windows through a DIFFERENT
# one. `window_registers` reads every `-FGB(%aN)` in the file, and `window_scan_failure` refuses any
# register the suite did not declare — on a twin whose `%a5` holds an entity index rather than
# `image + FGB`, such a line is not a global read at all.
WINDOW_ORIGIN = "FGB"

DISPLACEMENT_MIN, DISPLACEMENT_MAX = -0x8000, 0x7fff

# The operand shape, over ANY address register. Scanning register-agnostically is what makes
# `window_registers` below able to answer "which registers does this file window through?" — and
# that question is the check: a per-register scan can only ever confirm the register it was told
# about, and is blind to a line using a different one.
_ANY_WINDOWED = re.compile(r"([^\s,]+)-" + WINDOW_ORIGIN + r"\((%a[0-7])\)")


@functools.lru_cache(maxsize=None)
def _windowed(s_path):
    """[(expression, register)] for every windowed operand in one twin, as written."""
    tightened = re.sub(r"\s*([+*])\s*", r"\1", source_without_comments(s_path))
    return tuple((match.group(1).split(",")[-1], match.group(2))
                 for match in _ANY_WINDOWED.finditer(tightened))


def window_registers(s_path):
    """Every address register this twin reaches a global through — normally exactly one."""
    return tuple(sorted({register for _expression, register in _windowed(s_path)}))


@functools.lru_cache(maxsize=None)
def windowed_operands(s_path, register):
    """Every distinct expression a twin addresses through `register`, as written."""
    return tuple(sorted({expression for expression, through in _windowed(s_path)
                         if through == register}))


def windowed_value(expression, table):
    """One such expression's image address.

    `eval` over a table with no builtins, which is the whole grammar these operands use: `.equ`
    names joined by `+` and `*` (`A_score_award_table_bcd+2*SCORE_BCD_BYTES`). A parser of our own
    would be four more lines that could be wrong, over text the suites also assert the shape of.
    """
    return eval(expression, {"__builtins__": {}}, table)        # noqa: S307


def window_pin_failures(s_path, register):
    """Every global a twin reaches outside the signed 16-bit window, as messages; [] when all fit.

    ONE PHRASING because four suites ask it, the same reason `transcription_failure` is here.

    AND THIS PIN IS A BETTER ERROR, NOT THE ONLY SURFACE — measured, because the sentence it used to
    carry was wrong. Earlier revisions of this docstring (and of `frame.S`'s header) said gas would
    assemble an out-of-window global into a TRUNCATED displacement "silently". It does not: moving
    `frame_fire.S`'s `.equ FGB` to put its globals out of range gives
    "Error: displacement too large for this architecture; needs 68020 or higher -- statement
    `lea A_entity_gunsight-FGB(%a5),%a3' ignored", once per offending line, and the build fails.
    So the assembler is the real gate. What this adds is a message that names the WINDOW rather than
    the architecture, before the build, over every global at once — worth keeping, and worth not
    overstating.
    """
    table = equates(asm_object_for(s_path))
    origin = table[WINDOW_ORIGIN]
    failures = []
    for expression in windowed_operands(s_path, register):
        at = windowed_value(expression, table)
        displacement = at - origin
        if not DISPLACEMENT_MIN <= displacement <= DISPLACEMENT_MAX:
            failures.append(
                f"{s_path.name}: {expression} is at {at:#x}, which is {displacement:#x} from "
                f"{WINDOW_ORIGIN} ({origin:#x}) — outside the signed 16-bit window a `d16(An)` "
                f"carries. gas refuses it (\"displacement too large for this architecture\") and "
                f"the build fails; this says which global and how far out. Give it its own base "
                f"register, or "
                f"move {WINDOW_ORIGIN}")
    return failures


def window_scan_failure(s_path, expected, register):
    """The message for "this file's operand scan found the wrong number", or None.

    The scan's own positive control, and it is not optional: `window_pin_failures` is vacuous over an
    empty list, so a twin whose operand shape stopped matching `_WINDOWED` would pass the window pin
    by reaching no globals at all. Measured during wave D — a twin drafted with `%a4` as its window
    register produced ZERO matches here, and only this count said so.
    """
    registers = window_registers(s_path)
    if registers not in ((), (register,)):
        others = ", ".join(r for r in registers if r != register)
        return (f"{s_path.name} reaches a global through {others} as well as through the "
                f"{register} its suite declares. Only the declared register is displacement-checked, "
                f"so every global reached through {others} is UNCHECKED — and on a twin whose "
                f"{others} holds something other than image+{WINDOW_ORIGIN} it is not a global at "
                f"all, but a read near wherever that register points.")
    found = len(windowed_operands(s_path, register))
    if found == expected:
        return None
    return (f"{s_path.name} addresses {found} distinct expressions through the "
            f"{register} window, not the {expected} its header names. If a global was "
            f"legitimately added or dropped, move that number; if the count is 0 or nothing like "
            f"the right size, the operand shape changed — the twin is not reaching its globals as "
            f"`NAME-{WINDOW_ORIGIN}({register})` any more — and the window pin beside this "
            f"is testing an empty list")


# ---- the transcription pin, which for these twins is about ORDER rather than about bytes ----

_DIS_LINE = re.compile(r"^([0-9a-f]{6}): ")
# The address comment a twin puts on every transcribed instruction: `| 011d30 ...`. Six hex digits
# at the head of the comment, which no other comment starts with — the prose ones spell an address
# `0x11d30` or `$19aad`, and neither matches.
_ASM_ADDRESS = re.compile(r"\s+(0[0-9a-f]{5})\b")


@functools.lru_cache(maxsize=None)
def original_instruction_addresses(lo, hi):
    """Every instruction address of the original in [lo, hi), from the disassembly the transcription
    was made from."""
    assert PRG_DIS.exists(), f"{PRG_DIS} is missing — it is what the twins were transcribed from"
    found = [int(match.group(1), 16)
             for match in map(_DIS_LINE.match, PRG_DIS.read_text().splitlines()) if match]
    return [address for address in found if lo <= address < hi]


def transcribed_addresses(s_path):
    """The same list as a `.S` claims it: the `| 0xxxxx` comment on each transcribed instruction.

    Read from the FILE'S TEXT and not from a build, on purpose. Some of these twins have
    instructions inside `#ifdef`s — the spins and the MFP `bset`, whose off-target arm goes through
    the kit — and the assembly the differential runs contains only one arm. Scanning the text sees
    BOTH, which is the only way this pin can ask for all of the original's instructions.

    AND IT PINS THEIR PRESENCE AND ORDER, NOT THEIR OPERANDS. The `#ifdef`-ed ones are the one span
    in these twins with no off-target surface at all: a wrong bit, a wrong register address or the
    wrong polled byte assembles only in the target build and passes everything here. The surface is
    `atari/smoke.py game`, and STATUS.md records it as such rather than leaving it implied.
    """
    comments = (line.split("|", 1)[1]
                for line in Path(s_path).read_text().splitlines() if "|" in line)
    return [int(match.group(1), 16)
            for match in map(_ASM_ADDRESS.match, comments) if match]


def transcription_failure(s_path, lo, hi):
    """The message `test_the_twin_transcribes_the_original_instruction_for_instruction` fails with,
    or None when the two address lists agree. One phrasing, because four suites ask the question."""
    original = original_instruction_addresses(lo, hi)
    claimed = transcribed_addresses(s_path)
    if claimed == original:
        return None
    return (f"{Path(s_path).name} is no longer the original's instruction sequence over "
            f"[{lo:#x}, {hi:#x}): it claims {len(claimed)} instructions and the original has "
            f"{len(original)}. Missing "
            f"{[hex(a) for a in sorted(set(original) - set(claimed))][:10]}, extra "
            f"{[hex(a) for a in sorted(set(claimed) - set(original))][:10]}, out of order at "
            f"{next((hex(a) for a, b in zip(claimed, original) if a != b), 'nowhere')}")


# ---- the door slots, across the whole family ----

_DOOR_PREFIX = "ZY_DOOR_"


def asm_object_for(source):
    """The object `kit.mk` assembles one `src/asm/*.S` into."""
    return BUILD_ASM / (source.stem + ".o")


def family_sources():
    """Every `.S` that lands in the twin blob, in a stable order.

    `*.S` AND NOT `frame*.S`, because the door band is the BLOB's and so is the slot namespace it
    guards — `kit.mk`'s `$(ASM_ELF)` globs `src/asm/*.S`, so a leaf twin that gained a
    `.equ ZY_DOOR_*` would link into the same blob and jump into the same band. Scoped to the frame
    files, the cross-file collision pin would never see it: the leaf's slot could already belong to
    a frame twin's callee, and off target the door would read that row's argument count off the
    stack for the wrong core. The other five files declare no door today, so widening the glob costs
    nothing and closes the hole by construction rather than by their continuing not to.
    """
    return sorted(ASM_DIR.glob("*.S"))


def door_equates_by_file():
    """{source path: {callee name: slot}} for every `ZY_DOOR_*` the frame family's twins jump to.

    READ OUT OF EACH OBJECT rather than parsed out of the source, for `equates()`'s reason and one
    more. An `.equ` is an absolute symbol, so this is the number the stub's `jsr` was really
    assembled with, and a scraper cannot make the pin agree with itself by misreading an operand.
    And a source regex has to pick a spelling: the first revision of this function matched
    `,\\s*(\\d+)`, so it saw a decimal literal and nothing else — `.equ ZY_DOOR_foo, 0x3c`, or any
    value the assembler computes, would have dropped out of the family's slot namespace SILENTLY.
    The twin would then jump at a slot no table declares and die as a refusal naming the slot rather
    than the omission, which is the exact outcome `test_asm_frame_doors.py` exists to prevent.

    Each `.S` has its own object, so the per-file attribution the cross-file collision pin needs
    survives the move.
    """
    return {source: {name[len(_DOOR_PREFIX):]: value
                     for name, value in equates(asm_object_for(source)).items()
                     if name.startswith(_DOOR_PREFIX)}
            for source in family_sources()}
