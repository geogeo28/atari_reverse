"""test_course_ring.py — the course object/marker ring (game_update §12), under a free-running drive.

The ring is the course window the game scrolls toward you: RM_RING_ROWS distance bands, refilled at
the far end from the leg's packed course records. It is what makes the scenery stream, and — through
its marker column, which is where each band's road width and shoulder flags live — what makes the
road control table evolve. Nothing about it is a per-frame function of the image, so the only honest
harness is the free-running leg drive: the candidate is seeded ONCE and then advances its own ring,
so a wrong shuffle or a mis-unpacked record accumulates instead of being erased.

equiv.compare_leg_drive does the comparing (band by band, plus the control table those bands feed).
What this file adds is legs and drives the leg-drive tests do not run, and the assertion that the
interesting branches were actually reached — an unpack whose records never select an animation run
would otherwise be green with the expansion dead.
"""
import ctypes
import re

import equiv
import pytest

ACCEL, BRAKE, LEFT, RIGHT = 0x01, 0x02, 0x04, 0x08
FRAMES = 600

DRIVES = {
    "flat_out": [ACCEL] * FRAMES,
    "slalom": [ACCEL | (LEFT if (f // 50) % 2 else RIGHT) for f in range(FRAMES)],
    "lift_and_brake": [ACCEL if f % 90 < 60 else BRAKE if f % 90 < 75 else 0 for f in range(FRAMES)],
}

@pytest.mark.parametrize("leg", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("drive", sorted(DRIVES))
def test_ring_tracks_recreate(leg, drive, capsys):
    """Every band of the ring, and the control table its marker column drives, identical to recreate
    for the whole drive with the candidate free-running."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES[drive])
    with capsys.disabled():
        print(f"  leg={leg} {drive}: {len(mismatches)} mismatches / "
              f"refills={stats['ring_refills']} ages={stats['ring_ages']} "
              f"echo={stats['ring_echoes']} edge={stats['ring_edge_bands']}")
    assert not mismatches, "the ring diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["ring_refills"] > 0, f"no course record was ever pulled: {stats}"


def test_ring_reaches_both_refill_and_age(capsys):
    """row_ctr paces the record stream, so most advances only AGE the far band and a minority refill
    it from a record. Both branches have to fire or half the unpack is untested."""
    lib = equiv._lib()
    totals = {"ring_refills": 0, "ring_ages": 0}
    for leg in range(5):
        image = equiv.leg_start_background(leg)
        mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES["flat_out"])
        assert not mismatches, f"leg {leg} diverged"
        for k in totals:
            totals[k] += stats[k]
    with capsys.disabled():
        print(f"  totals across legs 0-4: {totals}")
    assert totals["ring_refills"] > 0, f"the refill branch never ran: {totals}"
    assert totals["ring_ages"] > 0, f"the age branch never ran: {totals}"


def test_ring_unpack_branches_are_reached(capsys):
    """The slot-1 -> slot-13 echo and a marker word carrying EDGE_* shoulder flags must each be
    observed from a leg start, or they are green-but-dead. (The animation expansion and the
    'right shoulder' marker fixup are NOT reachable from a leg start — see
    test_ring_hard_to_reach_branches.)"""
    lib = equiv._lib()
    totals = {"ring_echoes": 0, "ring_edge_bands": 0}
    for leg in range(5):
        for drive in sorted(DRIVES):
            image = equiv.leg_start_background(leg)
            mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES[drive])
            assert not mismatches, f"leg {leg} {drive} diverged"
            for k in totals:
                totals[k] += stats[k]
    with capsys.disabled():
        print(f"  totals across legs 0-4 x {len(DRIVES)} drives: {totals}")
    assert totals["ring_echoes"] > 0, f"the slot-1 -> slot-13 echo never fired: {totals}"
    assert totals["ring_edge_bands"] > 0, f"no band ever carried a shoulder flag: {totals}"


COURSE_READ_STEP = 8         # read_pos advances by this per record pull, wrapping at 0x1ff8
COURSE_READ_WRAP = 0x1ff8
SEEK_FRAMES = 60             # long enough to pull the seeded record, short enough to stay clear of
                             # the unported checkpoint event a longer drive runs into on leg 1


def _first_record_where(image, predicate):
    """The leg's earliest read_pos whose record satisfies `predicate`, or None."""
    # read_pos cycles {0, 8, ... COURSE_READ_WRAP}; start at 8 so `target - COURSE_READ_STEP` cannot
    # underflow, and include the wrap value itself so the scan really is every record but one.
    return next((pos for pos in range(COURSE_READ_STEP, COURSE_READ_WRAP + COURSE_READ_STEP,
                                      COURSE_READ_STEP) if predicate(image, pos)), None)


# Two unpack branches that a drive from a leg start never reaches, each with the legs whose course
# data contains it at all. Both were found by mutation: deleting the branch left every other test in
# this file green. The leg lists are narrow because the data is — leg 1 has no observable animation
# expansion anywhere (every one of its animation codes is followed by two re-selected slots that
# overwrite it), and only leg 3 uses the 'right shoulder' marker layout, in 25 of its records.
#
# A third branch, the 'both shoulders' marker fixup (MARKER_KIND_SIDES), is deliberately NOT listed:
# it fires for 0 of the 5120 records across all five legs, so this game's data cannot pin it at all.
# It is ported faithfully from the disassembly and left honestly unpinned rather than pinned against
# a fabricated record — see STATUS.md.
HARD_TO_REACH = {
    "anim_expansion": (equiv._anim_expansion_is_visible, "ring_anim_visible", [0, 2, 3, 4]),
    "marker_kind_right": (equiv._marker_is_kind_right, "ring_marker_right", [3]),
}


@pytest.mark.parametrize("branch", sorted(HARD_TO_REACH))
def test_ring_hard_to_reach_branches(branch, capsys):
    """Pin the unpack branches the leg-start drives above CANNOT pin, by seeding read_pos onto the
    first record in the leg that exercises each — real course data, nothing synthetic."""
    predicate, stat, legs = HARD_TO_REACH[branch]
    lib = equiv._lib()
    reached = 0
    for leg in legs:
        image = equiv.leg_start_background(leg)
        target = _first_record_where(image, predicate)
        assert target is not None, f"leg {leg} has no record exercising {branch}"
        equiv._w16(image, equiv.adapter.A_course_read_pos, target - COURSE_READ_STEP)

        mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * SEEK_FRAMES)
        assert not mismatches, f"{branch} leg {leg} diverged: " + "; ".join(
            f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
        reached += stats[stat]
        with capsys.disabled():
            print(f"  {branch} leg={leg}: seeded read_pos {target - COURSE_READ_STEP:#x}, "
                  f"{stat}={stats[stat]}")
    assert reached > 0, f"{branch} was never actually exercised, so it stays untested"


def _defines(path, pattern):
    """The `#define NAME literal` pairs in a C source file, as {name: int}."""
    text = (equiv.adapter.REMASTER / path).read_text()
    return {name: int(literal, 0)
            for name, literal in re.findall(pattern, text, re.M)}


def test_python_constants_match_the_c():
    """adapter.py/equiv.py mirror the ring's geometry and record layout from the C by hand; pin the
    copies equal (CLAUDE.md §5).

    RM_RING_SLOTS especially: if the C grows and Python does not, ctypes allocates a CourseRing
    smaller than the C writes and rm_road_course_advance runs off the end of the Python buffer —
    interpreter heap corruption instead of a failed assert. The record offsets and the marker/echo
    constants matter differently: a drifted copy there does not crash, it makes the branch-coverage
    counters silently count the wrong branch, so the hard-to-reach tests above would assert on a
    stale predicate and report coverage that never happened."""
    game_h = _defines("include/game.h",
                      r"^#define\s+(RM_RING_\w+|EDGE_\w+|RM_CTRL_\w+|RM_SCANLINE_\w+|RM_HUD_TIMER_\w+"
                      r"|RM_HUD_CRASH_\w+|RM_CRASH_\w+|RM_REC_\w+)\s+(\w+)\s*(?:/\*.*)?$")
    assert {"RM_RING_ROWS", "RM_RING_SLOTS"} <= game_h.keys(), "ring geometry moved out of game.h"
    assert equiv.adapter.RM_RING_ROWS == game_h["RM_RING_ROWS"]
    assert equiv.adapter.RM_RING_SLOTS == game_h["RM_RING_SLOTS"]
    assert equiv.adapter.RING_ROW_BYTES == (game_h["RM_RING_SLOTS"] + 1) * 2
    assert equiv.EDGE_ANY == game_h["EDGE_OPEN"] | game_h["EDGE_LEFT"] | game_h["EDGE_RIGHT"]

    # The leg-complete sentinel §I stamps into hud_crash_timer, mirrored in adapter.py for the leg
    # drive's leg_end detector (equiv.compare_leg_drive) — pin the Python copy equal to the C.
    assert equiv.adapter.RM_HUD_TIMER_LEG_END == game_h["RM_HUD_TIMER_LEG_END"]

    # The crash-fx tally constants mirrored in adapter.py (RM_HUD_CRASH_DECAY for the leg-drive phase-8
    # reference, the rollover layout for test_crash_fx's directed cases) — pin each Python copy to the C.
    assert equiv.adapter.RM_HUD_CRASH_DECAY == game_h["RM_HUD_CRASH_DECAY"]
    assert equiv.adapter.RM_CRASH_ROLLOVER_OFF == game_h["RM_CRASH_ROLLOVER_OFF"]
    assert equiv.adapter.RM_CRASH_ROLL_STRIDE == game_h["RM_CRASH_ROLL_STRIDE"]
    assert equiv.adapter.RM_CRASH_ROLL_TARGET == game_h["RM_CRASH_ROLL_TARGET"]

    # The control-table geometry, incl. the ALLOC spill pad: a drifted copy here under-allocates the
    # ctypes ctrl buffer and the C spill corrupts the interpreter heap with the suite still green
    # (every ctrl comparison stops at RM_CTRL_BYTES, so nothing else can catch it).
    assert {"RM_CTRL_LONGS", "RM_CTRL_STAMP_SPILL"} <= game_h.keys(), "ctrl geometry moved out of game.h"
    assert equiv.adapter.RM_CTRL_LONGS == game_h["RM_CTRL_LONGS"]
    assert equiv.adapter.RM_CTRL_BYTES == game_h["RM_CTRL_LONGS"] * 4
    assert equiv.adapter.RM_CTRL_STAMP_SPILL == game_h["RM_CTRL_STAMP_SPILL"]
    assert equiv.adapter.RM_CTRL_ALLOC_BYTES == equiv.adapter.RM_CTRL_BYTES + game_h["RM_CTRL_STAMP_SPILL"]
    assert equiv.adapter.RM_CTRL_WIDTH_OFF == game_h["RM_CTRL_WIDTH_OFF"]
    assert equiv.adapter.RM_SCANLINE_BYTES == game_h["RM_SCANLINE_BYTES"]
    # ctypes must agree with the C struct byte for byte, or byref() hands C a short buffer.
    assert ctypes.sizeof(equiv.adapter.CourseRow) == equiv.adapter.RING_ROW_BYTES
    assert (ctypes.sizeof(equiv.adapter.CourseRing)
            == equiv.adapter.RING_ROW_BYTES * equiv.adapter.RM_RING_ROWS)
    assert equiv.adapter.CourseRow.marker.offset == equiv.adapter.RM_RING_SLOTS * 2

    # The packed-record wire layout now lives ONCE in game.h (RM_REC_*), shared by course.c and
    # gameplay.c's init_ring_seed; the marker/echo fixups stay file-static in course.c.
    assert equiv.RING_REC_SELECT_OFF == game_h["RM_REC_SELECT_OFF"]
    assert equiv.RING_REC_CODES_OFF == game_h["RM_REC_CODES_OFF"]
    assert equiv.RING_REC_MARKER_OFF == game_h["RM_REC_MARKER_OFF"]
    course_c = _defines("src/course.c", r"^#define\s+(MARKER_\w+|CODE_ECHO\w*)\s+(\w+)\s*(?:/\*.*)?$")
    assert equiv.RING_MARKER_RAW_FLAG == course_c["MARKER_RAW_FLAG"]
    assert equiv.RING_MARKER_KIND_MASK == course_c["MARKER_KIND_MASK"]
    assert equiv.RING_MARKER_KIND_RIGHT == course_c["MARKER_KIND_RIGHT"]
    assert equiv.RING_ECHOED_CODE == course_c["CODE_ECHOED"]
    assert equiv.RING_ECHO_FROM == course_c["CODE_ECHO_FROM_SLOT"]
    assert equiv.RING_ECHO_TO == course_c["CODE_ECHO_TO_SLOT"]

    # adapter.py's IL_LEGTIME_BYTES (the baked-strings window sizing for init_assets) must equal the
    # window rm_init_leg's phase-4 legtime copy actually reads: the leg-1 base offset plus the five
    # rows it copies (see src/gameplay.c). Pin the Python copy to the C so a re-sized copy loop can't
    # silently outrun the ctypes window.
    gameplay_c = _defines("src/gameplay.c", r"^#define\s+(IL_LEGTIME_\w+)\s+(\w+)\s*(?:/\*.*)?$")
    assert (equiv.adapter.IL_LEGTIME_BYTES
            == gameplay_c["IL_LEGTIME_LEG_OFF"] + gameplay_c["IL_LEGTIME_ROWS"] * gameplay_c["IL_LEGTIME_COPY"])

    # The between-legs poll table's shape is mirrored in adapter.py (POLL_ENTRIES/POLL_ENTRY_BYTES size
    # the poll_blits window and drive its slicing); pin each Python copy to src/intermission.c's #define.
    inter_c = _defines("src/intermission.c", r"^#define\s+(POLL_\w+)\s+(\w+)\s*(?:/\*.*)?$")
    assert equiv.adapter.POLL_ENTRIES == inter_c["POLL_ENTRIES"]
    assert equiv.adapter.POLL_ENTRY_BYTES == inter_c["POLL_ENTRY"]

    # The between-legs FLOW state machine's constant mirrors (adapter.py copies the high-score geometry
    # from src/flow.c and the return codes / attract-loop seeds from include/flow.h by hand). Pin each
    # equal to the C so a drifted copy can't make the flow differential (test_flow_machine) green against
    # a stale constant — in particular the INT_C_FRAMES 0x96 boundary, whose Phase-C mirror loop is a
    # boundary-count only and cannot itself catch a drift (see equiv.compare_attract_cycle).
    flow_c = _defines("src/flow.c", r"^#define\s+(HS_\w+|INT_TIMER_WRAP)\s+(\w+)\s*(?:/\*.*)?$")
    assert equiv.adapter.HIGHSCORE_ROWS == flow_c["HS_ROWS"]
    assert equiv.adapter.HIGHSCORE_ROW == flow_c["HS_ROW"]
    assert equiv.adapter.HIGHSCORE_LEG_STRIDE == flow_c["HS_LEG_STRIDE"]
    assert equiv.adapter.HS_SCORE_REC_BYTES == flow_c["HS_RECORD_BYTES"]
    assert equiv.adapter.INT_TIMER_WRAP == flow_c["INT_TIMER_WRAP"]   # test_flow_machine's fast-tuning seed
    flow_h = _defines("include/flow.h",
                      r"^#define\s+(RM_ABORT_CODE|RM_INT_A_\w+|RM_INT_D_\w+|INT_\w+|IP_IDLE_INIT)\s+(\w+)\s*(?:/\*.*)?$")
    assert equiv.adapter.RM_ABORT_CODE == flow_h["RM_ABORT_CODE"]
    assert equiv.adapter.RM_INT_A_CONTINUE == flow_h["RM_INT_A_CONTINUE"]
    assert equiv.adapter.RM_INT_A_ABORT == flow_h["RM_INT_A_ABORT"]
    assert equiv.adapter.RM_INT_A_BREAK == flow_h["RM_INT_A_BREAK"]
    assert equiv.adapter.RM_INT_D_DRAW == flow_h["RM_INT_D_DRAW"]
    assert equiv.adapter.RM_INT_D_ADVANCE == flow_h["RM_INT_D_ADVANCE"]
    assert equiv.adapter.RM_INT_D_RESTART == flow_h["RM_INT_D_RESTART"]
    assert equiv.adapter.INT_SCROLL_INIT == flow_h["INT_SCROLL_INIT"]
    assert equiv.adapter.INT_TIMER_INIT == flow_h["INT_TIMER_INIT"]
    assert equiv.adapter.INT_FRAME_INIT == flow_h["INT_FRAME_INIT"]
    assert equiv.adapter.INT_C_FRAMES == flow_h["INT_C_FRAMES"]
    assert equiv.adapter.IP_IDLE_INIT == flow_h["IP_IDLE_INIT"]   # the shipping leg-select idle reload
