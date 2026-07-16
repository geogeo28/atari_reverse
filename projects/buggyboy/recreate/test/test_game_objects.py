"""Differential test for draw_game_objects @ 0x12ef6 — the per-frame scene/object draw orchestrator.

draw_game_objects advances three pieces of per-frame state (the marker-decay slot, the road-colour
animation counters, the bonus-window flag animation), then calls draw_ground, draw_fg_sprite,
draw_object, draw_buggy, and draw_object_list (up to 3 passes split around the active-sprite list),
ordering the last object pass against the buggy by the view. a6 is the current draw buffer.

Two-part verification (whole-image diff vs the Musashi oracle, poisoned):
- PREFIX (the novel logic): verified rigorously at the 0x12fc0 checkpoint (before the first draw),
  where g_draw_game_objects_prefix reproduces the marker/anim/bonus writes. Fuzzed hard. The
  marker-decay slot shares the scanline table with draw_ground, so exercising it here (draw_ground
  does not run) is both isolated and complete.
- ORCHESTRATION: verified at rts with draw_buggy drawing (confirms the derived a6 + that control
  reaches the buggy on both view branches), the other sub-draws quiesced, and the three
  draw_object_list passes walking zeroed streams (type 0 -> no dispatch). The sub-functions and
  their register setups are each independently verified; this confirms they are invoked in order.
"""
import ctypes
import random

import harness
from harness import differential, report
import test_buggy

ENTRY = 0x12ef6
CHECKPOINT = 0x12fc0              # bsr draw_ground: the prefix is complete here

BUFFER = 0x8000
BUF_SPAN = 0x8000                 # 0x8000..0x10000 — must NOT reach the program code at 0x10000+
BUF_A = 0x60000
BUF_C = 0x20000                   # matches test_buggy's buf_c arena

A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4
A_BUF_A_PTR, A_BUF_C_PTR = 0x18c00, 0x18c08
A_MARKER_DECAY, A_MARKER_BASE = 0x18cf0, 0x18d34
A_VIEW_PARITY, A_ANIM_COUNTER = 0x18c60, 0x17f10
A_BONUS_TIMER, A_DSP_SCROLL = 0x18d08, 0x18d06
A_FLAG_SEQ_OFF, A_FLAG_SEQ_COUNT = 0x18c40, 0x18c48
A_VIEW_FLAGS, A_OBJ_SCAN_OFF = 0x18c56, 0x18c58
A_SPRITE_SUPPRESS = 0x18cd0       # draw_fg_sprite early-return gate
A_ROAD_WIDTH_TBL = 0x18f24        # draw_object: all 0 -> no visible object
A_GROUND_SCAN_TBL = 0x18d48       # draw_ground: neutral markers -> no draw
A_OBJ_SPRITE_DISP = 0x16a90       # passes 1/2 a5 stream


def _w(v): return (v & 0xffff).to_bytes(2, "big")
def _l(v): return (v & 0xffffffff).to_bytes(4, "big")


# ---- prefix (marker / anim / bonus), verified at the 0x12fc0 checkpoint -----------------------

def _prefix_pokes(seed, marker_active, marker_off, marker_cd, counter, bonus, dsp,
                  seq_off, seq_count, view_parity):
    rng = random.Random(seed)
    return {
        A_BUF_A_PTR: _l(BUF_A),
        BUF_A: bytes(rng.randrange(256) for _ in range(0x2400)),   # anim mirrors land at +0xd70/+0x1250
        A_MARKER_DECAY: _w(marker_active) + _w(marker_off) + _w(marker_cd),
        A_MARKER_BASE: bytes(rng.randrange(256) for _ in range(0x340)),  # decay clears/decrements here
        A_ANIM_COUNTER: _w(counter),
        A_VIEW_PARITY: _w(view_parity),
        A_BONUS_TIMER: _w(bonus),
        A_DSP_SCROLL: _w(dsp),
        A_FLAG_SEQ_OFF: _w(seq_off),
        A_FLAG_SEQ_COUNT: _w(seq_count),
    }


def _check_prefix(label, seed, **kw):
    p = _prefix_pokes(seed, kw.get("marker_active", 0), kw.get("marker_off", 0x40),
                      kw.get("marker_cd", 0x60), kw.get("counter", 0), kw.get("bonus", 0),
                      kw.get("dsp", 0), kw.get("seq_off", 0), kw.get("seq_count", 0),
                      kw.get("view_parity", 0))
    regs = {"_pokes": p}
    diffs, _ = differential(ENTRY, regs, lambda lib, buf: lib.g_draw_game_objects_prefix(buf),
                            stop_pc=CHECKPOINT, poison=True)
    assert not diffs, f"prefix {label} seed={seed} {kw}\n{report(diffs[:16])}"


harness._lib.g_draw_game_objects_prefix.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_game_objects_prefix.restype = None


def test_prefix_anim():
    for counter in (0, 2, 0x1e, 0x20, 0xfffe):     # sweeps the &0x1e table index + wrap
        _check_prefix("anim", seed=counter, counter=counter, view_parity=counter)


def test_prefix_marker_decay():
    for cd in (0x40, 0x20, 0x10, 0x30, 0):          # 0x10 -> underflow < 0 (retire the slot)
        for off in (0, 0x20, 0x40):
            _check_prefix("marker", seed=cd * 8 + off, marker_active=1, marker_off=off, marker_cd=cd)
    _check_prefix("marker_inactive", seed=99, marker_active=0)


def test_prefix_bonus():
    for bonus in (1, 2, 0x28, 0x29, 0x100):         # 1 -> hits 0; 0x29 -> decays to 0x28 (flag advance)
        for dsp in (0, 3, 4):
            for seq_count in (0, 4, 5):
                _check_prefix("bonus", seed=bonus * 64 + dsp * 8 + seq_count, bonus=bonus,
                              dsp=dsp, seq_count=seq_count, seq_off=0x10)


def test_prefix_fuzz():
    rng = random.Random(0x6081EC7)
    for i in range(300):
        _check_prefix("fuzz", seed=i,
                      marker_active=rng.choice([0, 0, 1]),
                      marker_off=rng.randrange(0, 0x100) & ~1,
                      marker_cd=rng.choice([0, 0x10, 0x20, 0x40, 0x80, rng.randrange(0x200)]),
                      counter=rng.randrange(0x10000),
                      bonus=rng.choice([0, 0, 1, 2, 0x28, 0x29, rng.randrange(0x100)]),
                      dsp=rng.randrange(0, 6),
                      seq_off=rng.randrange(0, 0x40) & ~0xf,
                      seq_count=rng.randrange(0, 8),
                      view_parity=rng.randrange(0x10000))


# ---- orchestration (full rts): buggy draws, others quiesced, object lists no-op ----------------

def _orch_pokes(seed, view_flags):
    rng = random.Random(seed)
    p = dict(test_buggy._pokes(seed, lean=0, crash=0, pitch=0, skid=0, overlays=False))
    p.pop(test_buggy.BUFFER, None)
    p[BUFFER] = bytes(rng.randrange(256) for _ in range(BUF_SPAN))
    p[A_FLIP_IDX] = _w(0)
    p[A_PHYSBASE] = _l(BUFFER)
    p[A_BUF_A_PTR] = _l(BUF_A)
    p[A_BUF_C_PTR] = _l(BUF_C)
    p[BUF_A] = bytes(rng.randrange(256) for _ in range(0x2400))
    p[A_VIEW_FLAGS] = _w(view_flags)
    p[A_OBJ_SCAN_OFF] = _w(0)                       # a5 += 0; also draw_ground view offset = 0
    p[A_SPRITE_SUPPRESS] = _w(1)                    # draw_fg_sprite early-returns (no blit)
    p[A_ROAD_WIDTH_TBL] = bytes(96 * 4)             # draw_object: no visible object -> early return
    for i in range(13):                             # draw_ground: neutral markers -> no draw
        p[A_GROUND_SCAN_TBL + i * 0x20 + 3] = bytes([0])
    # draw_object_list passes: display stream zeroed (dst/xoff/x words = 0). The a3 flag stream is
    # the scanline table (BSS 0 at rest) -> every object type 0, no dispatch. count = 11 (all sprite
    # words 0 = non-negative) -> pass 1 runs 11 no-op rows, pass 2 is skipped, pass 3 one no-op row.
    p[A_OBJ_SPRITE_DISP] = bytes(0x400)
    return p


def _check_orch(label, seed, view_flags):
    regs = {"a6": BUFFER, "_pokes": _orch_pokes(seed, view_flags)}
    diffs, _ = differential(ENTRY, regs, lambda lib, buf: lib.g_draw_game_objects(buf),
                            poison=True, max_insns=4_000_000)
    assert not diffs, f"orch {label} seed={seed} view={view_flags}\n{report(diffs[:16])}"


harness._lib.g_draw_game_objects.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_game_objects.restype = None


def test_orchestration():
    for view in (0, 2, 4, 6):        # view & 4 selects the buggy/object-list draw order
        _check_orch("view", seed=view + 1, view_flags=view)


def test_orchestration_fuzz():
    rng = random.Random(0x60B1EC7)
    for i in range(20):
        _check_orch("fuzz", seed=0x500 + i, view_flags=rng.choice([0, 2, 4, 6]))
