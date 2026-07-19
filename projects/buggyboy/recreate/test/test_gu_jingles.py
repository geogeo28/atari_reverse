"""Directed differential tests for game_update's course-advance jingles (improvement #3).

The three play_event_tune calls in sections G/H/I — checkpoint (tune 5, 0x119ca), leg-end (tune 1,
0x11a8c) and collision-marker (tune 6, 0x11a9c) — sit in branches the section-12 fuzz never reaches:
the full-frame path recomputes event_type from the course stream, clobbering any staged value before
the branch is read. So they were only read-verified (coverage_gap_allow.txt).

Here we enter the oracle directly at the sections-G/H/I tail (0x118b6, which loads its own a1/a5, so
no register staging is needed) and stage event_type / score_str / ground_scan so each jingle branch is
taken, with the sound guard open (game_over=0, mzflag=0, cur_tune!=6) so play_event_tune's INITTUNE
lands in the image. The whole-image diff then verifies the tune id: play_event_tune writes cur_tune_id
= id and INITTUNE lays down that tune's voice records, so a wrong reconstructed id diverges.

Sections G/H are inert here — obj_flags/horizon_row are BSS-zero, so the fx-block rebuild produces
zeros and the horizon-event dispatch fires nothing — leaving section I as the sole variable.
"""
import ctypes

import harness
from harness import differential, report

FX_ENTRY = 0x118b6                 # game_update_fx_and_events (sections G/H/I)

A_EVENT_TYPE = 0x18eca             # w: 0x1a=checkpoint, 0x1d=collision
A_SCORE_STR1 = 0x18231             # score_str+1: '5' at a checkpoint ends the leg
A_GROUND_SCAN1 = 0x18d49           # ground_scan_tbl+1: 0x1d marks a collision-marker frame
A_GROUND_SCAN0 = 0x18d48           # ground_scan_tbl[0]: 0x1a would trigger draw_checkpoint_anim
A_LEG_INDEX = 0x18c38              # leg 0 also runs init_leg_dash/draw_leg_labels — pick !=0 to skip
A_GAME_OVER = 0x18c34
A_CUR_TUNE = 0x18cfa
A_MZFLAG = 0x1b07a

EVENT_CKPT, EVENT_COLLIDE = 0x1a, 0x1d

harness._lib.g_game_update_fx_and_events.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_update_fx_and_events.restype = None


def _w(v):
    return (v & 0xffff).to_bytes(2, "big")


def _guard_open():
    """game_over=0, mzflag=0, cur_tune=0 -> play_event_tune runs INITTUNE (id lands in the image)."""
    return {A_GAME_OVER: _w(0), A_MZFLAG: bytes([0]), A_CUR_TUNE: _w(0)}


def _run(pokes, label):
    diffs, info = differential(FX_ENTRY, {"_pokes": {**_guard_open(), **pokes}},
                               lambda l, b: l.g_game_update_fx_and_events(b), poison=True)
    assert not diffs, f"{label}\n{report(diffs[:16])}"
    return info


def test_checkpoint_jingle():
    """event_type==0x1a, score_str[1]!='5', leg!=0, no collision marker -> play_event_tune(5) @0x119ca."""
    _run({A_EVENT_TYPE: _w(EVENT_CKPT), A_SCORE_STR1: b"4", A_LEG_INDEX: _w(1),
          A_GROUND_SCAN0: bytes([0]), A_GROUND_SCAN1: bytes([0])}, "checkpoint tune 5")


def test_leg_end_jingle():
    """event_type==0x1a and score_str[1]=='5' -> play_event_tune(5) then play_event_tune(1) @0x11a8c."""
    _run({A_EVENT_TYPE: _w(EVENT_CKPT), A_SCORE_STR1: b"5", A_LEG_INDEX: _w(1)},
         "leg-end tune 1")


def test_collision_marker_jingle():
    """ground_scan[1]==0x1d (no checkpoint/collision event) -> bonus armed + play_event_tune(6) @0x11a9c."""
    _run({A_EVENT_TYPE: _w(0), A_GROUND_SCAN1: bytes([EVENT_COLLIDE])}, "collision-marker tune 6")


# The checkpoint-anim gate reads the marker byte at ground_scan_tbl+3 (0x18d4b), not +0 — exercise
# it by staging that byte (with buf_c for draw_checkpoint_anim's banner scroll) so the +3 read matters.
A_BUF_C = 0x18c08
BUF_C = 0x30000
_ANIM_ARENA_LO, _ANIM_ARENA_HI = BUF_C + 0x7000, BUF_C + 0xc800   # draw_checkpoint_anim's window


def test_checkpoint_anim_marker():
    """ground_scan[3]==0x1a, [1]!=0x1d, score_str[1]!='1' -> ckpt-scroll + draw_checkpoint_anim + add_score."""
    import random
    rng = random.Random(0xCA1a)
    pokes = {A_GROUND_SCAN1: bytes([0]), A_GROUND_SCAN0 + 3: bytes([EVENT_CKPT]),
             A_SCORE_STR1: b"4", A_EVENT_TYPE: _w(0), A_BUF_C: BUF_C.to_bytes(4, "big"),
             _ANIM_ARENA_LO: bytes(rng.randrange(256) for _ in range(_ANIM_ARENA_HI - _ANIM_ARENA_LO))}
    _run(pokes, "checkpoint-anim +3 marker")

