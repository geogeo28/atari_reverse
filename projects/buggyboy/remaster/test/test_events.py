"""test_events.py — the course-event engine (game_update §12's tail + the event jump-table dispatch).

This is the system that decides to crash you and ends a leg. It is pure off-frame state + graphics-
arena work, so the equivalence surface is every scalar/counter/buffer the engine owns, diffed against
the verified recreate references (g_gu_dispatch_event / g_game_update_fx_and_events / g_probe_collision)
running in-image on the same staged frame — see equiv.compare_event_* for the compared locations.

Five things are pinned:
  1. the native jump table, against the image's own table at 0x11aa2 (idx -> resolved target -> kind);
  2. per-handler dispatch, fuzzed over every idx x the two gate flags x collision_lock x curve sign;
  3. the composite §G/§H/§I tail over legs 0-4 x warmups;
  4. directed §I cases: the checkpoint / leg-end / leg-0 dashboard-rebuild / collision-marker / banner
     paths a normal frame's event_type never carries;
  5. the collision-probe head, flag-bit walk + the dashboard marker walk.
"""
import ctypes

import adapter
import bench_frame
import equiv
import pytest

lib = equiv._lib()

A_EVENT_JUMPTABLE = 0x11aa2
FLAG_GATE_BASE = 0x11ba4
FLAG_GATE_TOP = 0x11bb4

# EventKind enum values (mirror src/events.c). rm_event_classify packs (kind<<24 | gate<<16 | arg).
(EV_NOOP, EV_FLAG_GATE, EV_FLAG_GATE_FORCED, EV_SCORE, EV_CKPT, EV_MARKER_DECAY, EV_SPIN_ARM,
 EV_RPM_COLLIDE, EV_CURVE_FREEZE, EV_RPM_PENALTY, EV_COMMON_COLLIDE, EV_DISP_FINISH,
 EV_DISP_BONUS) = range(13)

# resolved handler target -> (kind, gate, arg), from the disassembly (recreate game_update.c). The
# flag-gate targets (0x11ba4..0x11bb4) are handled by formula; everything else is here.
TARGET_MAP = {
    0x11c18: (EV_NOOP, 0, 0), 0x11c1a: (EV_FLAG_GATE_FORCED, 0, 0),
    0x11c5a: (EV_SCORE, 1, 0xc), 0x11c62: (EV_SCORE, 0, 0xc), 0x11c6a: (EV_SCORE, 2, 0xc),
    0x11cdc: (EV_SCORE, 1, 0x12), 0x11ce4: (EV_SCORE, 0, 0x12), 0x11cec: (EV_SCORE, 2, 0x12),
    0x11cf6: (EV_SCORE, 1, 0x18), 0x11cfe: (EV_SCORE, 0, 0x18), 0x11d08: (EV_SCORE, 2, 0x18),
    0x11d12: (EV_CKPT, 1, 0), 0x11d1a: (EV_CKPT, 0, 0), 0x11d2e: (EV_CKPT, 2, 0),
    0x11d38: (EV_NOOP, 0, 0), 0x11d62: (EV_NOOP, 0, 0),
    0x11d3a: (EV_MARKER_DECAY, 0, 0), 0x11d64: (EV_SPIN_ARM, 0, 0), 0x11d8e: (EV_RPM_COLLIDE, 0, 0),
    0x11dcc: (EV_CURVE_FREEZE, 0, 0), 0x11de2: (EV_RPM_PENALTY, 0, 0), 0x11e16: (EV_COMMON_COLLIDE, 0, 0),
    0x11e4e: (EV_DISP_FINISH, 0, 0x90), 0x11e5c: (EV_DISP_FINISH, 1, 0x1a8),
    0x11e8e: (EV_DISP_BONUS, 0, 0x29), 0x11e96: (EV_DISP_BONUS, 0, 0x3f),
    0x11e92: (EV_DISP_BONUS, 1, 0x2a), 0x11eaa: (EV_DISP_BONUS, 1, 0x40),
}


def _resolve_target(image, idx):
    off = equiv._r16(image, A_EVENT_JUMPTABLE + idx * 2)
    if off & 0x8000:
        off -= 0x10000
    return (A_EVENT_JUMPTABLE + off) & 0xffffffff


def _classify_target(target):
    if FLAG_GATE_BASE <= target <= FLAG_GATE_TOP and (target - FLAG_GATE_BASE) % 4 == 0:
        return (EV_FLAG_GATE, (target - FLAG_GATE_BASE) // 4 + 1, 0)
    return TARGET_MAP.get(target)


def test_jump_table_matches_the_image():
    """Pin the native event table against the image's own jump table at 0x11aa2: resolve each idx to
    its handler address, classify it from the disassembly, and require rm_event_classify to agree
    (like test_course_ring's constants pin). A mis-encoded entry — wrong gate, wrong score group,
    wrong bonus id — is caught here rather than only where the fuzz happens to stage that idx."""
    image = bench_frame.mid_race_state(0, 0)
    for idx in range(adapter.RM_EVENT_TABLE_ENTRIES):
        target = _resolve_target(image, idx)
        expected = _classify_target(target)
        assert expected is not None, f"idx {idx}: unmapped target {target:#x} (extend TARGET_MAP)"
        kind, gate, arg = expected
        want = (kind << 24) | (gate << 16) | arg
        got = lib.rm_event_classify(idx)
        assert got == want, (f"idx {idx} target {target:#x}: classify {got:#x} != {want:#x} "
                             f"(kind {(got >> 24) & 0xff}/{kind} gate {(got >> 16) & 0xff}/{gate} "
                             f"arg {got & 0xffff:#x}/{arg:#x})")


# ---- 2. per-handler dispatch fuzz ------------------------------------------------------------------

DISPATCH_LEG = 1
DISPATCH_WARMUP = 40
# Staged preconditions the handlers branch on. road_curve sign steers disp_bonus's type/curve pick;
# collision_lock 0/nonzero gates the collision/spin/bonus spawns; spin_state high byte 0x20 is
# disp_bonus's "fully spun out". event_pending / crash_phase feed the disp_bonus already-armed path.
_LOCKS = (0, 8)
_CURVES = (0x100, (-0x100) & 0xffff)
_SPINS = (0, 0x2000)               # spin_state word: high byte 0 vs 0x20
_FLAGS = (0, 1)


def _dispatch_cases():
    cases = []
    for idx in range(adapter.RM_EVENT_TABLE_ENTRIES):
        for lock in _LOCKS:
            for curve in _CURVES:
                for spin in _SPINS:
                    for fa in _FLAGS:
                        for fb in _FLAGS:
                            cases.append((idx, lock, curve, spin, fa, fb))
    return cases


DISPATCH_CASES = _dispatch_cases()
DISPATCH_CHUNKS = 8


@pytest.mark.parametrize("chunk", range(DISPATCH_CHUNKS))
def test_dispatch_matches_recreate(chunk, capsys):
    """Every jump-table index under every gate combination x collision_lock x road_curve sign x spin
    state, dispatched with slot 3, and compared scalar-for-scalar (incl. the ring pokes, the score
    string, and — for disp_bonus — the rebuilt road control table) against recreate."""
    cases = DISPATCH_CASES[chunk::DISPATCH_CHUNKS]
    bad = []
    for idx, lock, curve, spin, fa, fb in cases:
        image = equiv.event_background(DISPATCH_LEG, DISPATCH_WARMUP, pokes={
            adapter.A_collision_lock: lock,
            adapter.A_road_curve: curve,
            adapter.A_spin_state: spin,
            adapter.A_crash_phase: 2,          # non-negative: disp_bonus's already-armed id stays
            adapter.A_event_pending: 0,
        })
        diffs = equiv.compare_event_dispatch(lib, image, idx, 3, fa, fb)
        if diffs:
            bad.append((idx, lock, curve, spin, fa, fb, diffs[:4]))
    with capsys.disabled():
        print(f"  chunk {chunk}: {len(cases)} cases, {len(bad)} bad")
    assert not bad, "dispatch diverged from recreate:\n" + "\n".join(
        f"  idx={i} lock={lk} curve={cv:#x} spin={sp:#x} a={a} b={b}: {d}"
        for i, lk, cv, sp, a, b, d in bad[:8])


def test_dispatch_reaches_every_handler_kind():
    """A handler that no dispatch ever enters would pass vacuously. For every handler kind that has a
    body (all but EV_NOOP), confirm at least one dispatch produced an OBSERVABLE state change on the
    REFERENCE side — the recreate image differing from its pre-dispatch copy is the ground truth that
    the handler body ran (coverage derived from the record consumed, never the static table). A cheap
    directed sweep over one representative idx per kind: its gate is opened by trying every flag
    combination, collision_lock is cleared so the spin/collision spawns run, and speed is staged past
    the spin floor so spin_arm arms."""
    image = equiv.event_background(DISPATCH_LEG, DISPATCH_WARMUP, pokes={
        adapter.A_collision_lock: 0,
        adapter.A_event_pending: 0,
        adapter.A_crash_phase: 2,          # non-negative: disp_bonus's main path
        adapter.A_speed: 0x64,             # >= spin_arm's speed floor (0x1e)
    })
    dispatch = equiv._gu_dispatch_fn()

    kind_idx = {}                          # first idx of each kind
    for idx in range(adapter.RM_EVENT_TABLE_ENTRIES):
        kind_idx.setdefault((lib.rm_event_classify(idx) >> 24) & 0xff, idx)
    assert set(kind_idx) == set(range(13)), f"not every handler kind is in the table: {sorted(kind_idx)}"

    unreached = []
    for kind, idx in kind_idx.items():
        if kind == EV_NOOP:                # the do-nothing kind has no body to exercise
            continue
        changed = False
        for fa in (0, 1):
            for fb in (0, 1):
                ref = bytearray(image)
                dispatch((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref), idx, 3, fa, fb)
                if ref != image:
                    changed = True
                    break
            if changed:
                break
        if not changed:
            unreached.append((kind, idx))
    assert not unreached, f"handler kinds no dispatch exercised (kind, idx): {unreached}"


# ---- 3. composite (sections G/H/I) -----------------------------------------------------------------

@pytest.mark.parametrize("leg", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("warmup", [10, 40, 90])
def test_course_events_matches_recreate(leg, warmup):
    """The whole §G fx-block rebuild + §H horizon dispatch + §I markers, over legs 0-4 and several
    warmup depths, compared against recreate's g_game_update_fx_and_events including the graphics
    arena (spin_state, curve_freeze, ckpt_scroll, dash_marker, the crash counters, the dashboard /
    banner bitmaps)."""
    image = equiv.event_background(leg, warmup)
    diffs = equiv.compare_course_events(lib, image)
    assert not diffs, f"leg {leg} warmup {warmup} diverged: {diffs[:8]}"


# ---- 4. directed section-I cases -------------------------------------------------------------------
# A normal staged frame's event_type (ring row 12 slot 7 low byte, image 0x18eca) is not a marker, so
# §I's checkpoint / collision paths never run. Stage it directly. The ground-scan bytes the banner
# gate reads are ring row 0 slots 6/7 (image 0x18d48+1 / +3).

A_GROUND_SCAN = 0x18d48
A_SCORE_STR = adapter.A_score_str


def _stage_section_i(leg, warmup, event_type=None, ground6=None, ground7=None, score1=None):
    image = equiv.event_background(leg, warmup)
    if event_type is not None:
        equiv._w16(image, adapter.A_event_type, event_type)   # ring row 12 slot 7 low byte
    if ground6 is not None:
        image[A_GROUND_SCAN + 1] = ground6                    # ring row 0 slot 6 low byte
    if ground7 is not None:
        image[A_GROUND_SCAN + 3] = ground7                    # ring row 0 slot 7 low byte
    if score1 is not None:
        image[A_SCORE_STR + 1] = score1
    return image


DIRECTED = {
    "checkpoint":        dict(leg=1, event_type=0x1a),                       # bump counters + score char
    "checkpoint_legend": dict(leg=1, event_type=0x1a, score1=ord('5')),      # score_str[1]=='5' -> leg end
    "checkpoint_leg0":   dict(leg=0, event_type=0x1a),                       # leg 0 -> dashboard rebuild
    "collision":         dict(leg=1, event_type=0x1d),                       # probe_collision
    "banner":            dict(leg=1, ground7=0x1a, score1=ord('3')),         # checkpoint-anim scroll
    "banner_blocked":    dict(leg=1, ground6=0x1d, ground7=0x1a, score1=ord('3')),  # collision marker path
}


@pytest.mark.parametrize("case", sorted(DIRECTED))
def test_section_i_directed(case, capsys):
    """Stage each §I branch (checkpoint incl. leg-end + the leg-0 dashboard rebuild, the collision
    marker, and the checkpoint-banner scroll incl. the collision-marker override), and compare the
    whole tail against recreate."""
    kw = dict(DIRECTED[case])
    leg = kw.pop("leg")
    for warmup in (20, 60):
        image = _stage_section_i(leg, warmup, **kw)
        diffs = equiv.compare_course_events(lib, image)
        with capsys.disabled():
            print(f"  {case} leg={leg} warmup={warmup}: {len(diffs)} diffs")
        assert not diffs, f"{case} leg={leg} warmup={warmup} diverged: {diffs[:8]}"


# ---- 5. collision probe ----------------------------------------------------------------------------

# (mask long, starting course_flag_bit): a high byte >= the bit keeps the cursor; a low high byte with
# the bit past it resets to 0; the low bits decide whether the probe fires and walks the dash marker.
PROBE_CASES = [
    (0x7fffffff, 0x05),   # no reset, bit set -> fires, marker walks
    (0x7fffffff, 0x1f),   # no reset, high bit index -> fires
    (0x02000007, 0x05),   # byte0=2 < expected 6 -> reset to 0, bit 0 set -> fires from 0
    (0x7f000000, 0x05),   # no reset, no low bits -> does NOT fire (marker + bitmap untouched)
    (0x00000000, 0x05),   # byte0=0 -> reset to 0, no bits -> does NOT fire
]


@pytest.mark.parametrize("mask,start", PROBE_CASES)
def test_course_probe(mask, start, capsys):
    """The probe head: the flag-bit walk (increment + wrap) against a Python mirror of the C, and —
    when the probed bit fires — the dashboard progress-marker walk against recreate's g_probe_collision
    on the same dash state + bitmap."""
    image = equiv.event_background(0, 40)
    diffs, fired = equiv.compare_course_probe(lib, image, mask, start)
    with capsys.disabled():
        print(f"  mask={mask:#010x} start={start:#x}: fired={fired} diffs={len(diffs)}")
    assert not diffs, f"probe diverged (mask={mask:#x} start={start:#x}): {diffs[:8]}"


def test_course_probe_reaches_both_outcomes():
    """Fire and no-fire must both be exercised, or half the probe head is untested."""
    image = equiv.event_background(0, 40)
    outcomes = {equiv.compare_course_probe(lib, image, mask, start)[1] for mask, start in PROBE_CASES}
    assert outcomes == {True, False}, f"probe cases did not reach both outcomes: {outcomes}"


# The image's own progress marker sits at (0,0,0) in a warm leg-0 frame, so the erase clears bit 0 of
# byte 0 — a no-op that leaves the erase's y-offset term untested (a mutation dropping y0 survives).
# Point the marker at a real track cell in the real dashboard whose bit is set, so the erase is a
# genuine bit-clear and the walk moves; the differential vs recreate then pins the y-offset. Staging a
# marker position is staging state, not fabricating a course record.
PROBE_MARKER = (0x20, 0x03, 0x1040)   # (y, bit, x): a set bit in the leg-0 warmup=40 dashboard


def test_course_probe_marker_walk(capsys):
    """Seed the marker onto a real set track cell and pin the full erase + neighbour walk against
    recreate's g_probe_collision, with a coverage assertion that the erase was observable (so a
    dropped y-offset diverges instead of clearing bit 0 of byte 0)."""
    image = equiv.event_background(0, 40)
    # coverage: recreate's probe must actually change the dashboard here, or the pin is vacuous.
    ref = bytearray(image)
    ref[adapter.A_dash_marker] = PROBE_MARKER[0]
    ref[adapter.A_dash_marker + 1] = PROBE_MARKER[1]
    equiv._w16(ref, adapter.A_dash_marker + 2, PROBE_MARKER[2])
    buf_c = int.from_bytes(ref[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
    before = bytes(ref[buf_c:buf_c + adapter.GFX_EVENT_BYTES])
    equiv._bind("g_probe_collision")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    changed = sum(1 for a, b in zip(before, ref[buf_c:buf_c + adapter.GFX_EVENT_BYTES]) if a != b)
    with capsys.disabled():
        print(f"  marker walk: recreate changed {changed} dashboard bytes")
    assert changed > 0, "the seeded marker cell is no longer set — the erase pin went vacuous"

    diffs, fired = equiv.compare_course_probe(lib, image, 0x7fffffff, 5, dash=PROBE_MARKER)
    assert fired and not diffs, f"probe marker walk diverged: {diffs[:8]}"


# ---- 6. fx-block slot mapping ----------------------------------------------------------------------
# The fx block maps the near band's (ring row 12) slot words to fixed positions: slot 0 -> word +6,
# slots 1..13 -> +0xa..+0x22, slot 14 -> +0x26. §H then dispatches fx[horizon_row+1] (a slot's low
# byte), then fx[horizon_row+3]. A warm frame's band carries no dispatchable code there, so a wrong
# slot->position map is invisible; even a slot-independent event hides it (the code just shifts from
# §H's first dispatch to its second). Pin it with the marker-decay spawn (idx 30), whose marker_off =
# the DISPATCH SLOT (horizon_row for the first, horizon_row+2 for the second) and whose obj_active
# poke lands at a slot-dependent ring byte — so a mis-mapped slot changes marker_off / the ring, not
# just which dispatch fires.
A_OBJ_FLAGS = 0x18ebc      # ring row 12 slot words (obj_flags)
A_RING11_MARKER = 0x18eba  # ring row 11 marker (spin-fx gate bytes); zero it to skip the overlay
A_HORIZON_ROW = 0x18c6c
EVT_IDX_MARKER_DECAY = 30  # marker_decay spawn: sets marker_off = slot, pokes ring, bumps marker_active

# slot -> the even horizon_row whose fx[horizon_row+1] is that slot's low byte.
FX_SLOT_HORIZON = {0: 6, 1: 0xa, 7: 0xa + 6 * 2, 13: 0xa + 12 * 2, 14: 0x26}


@pytest.mark.parametrize("slot", sorted(FX_SLOT_HORIZON))
def test_fx_block_slot_mapping(slot, capsys):
    horizon = FX_SLOT_HORIZON[slot]
    image = equiv.event_background(1, 40)
    for s in range(adapter.RM_RING_SLOTS):
        equiv._w16(image, A_OBJ_FLAGS + s * 2, 0)          # clear the band...
    equiv._w16(image, A_OBJ_FLAGS + slot * 2, EVT_IDX_MARKER_DECAY)   # ...but this slot
    equiv._w16(image, A_RING11_MARKER, 0)                  # no spin-fx overlay
    equiv._w16(image, A_HORIZON_ROW, horizon)

    # coverage: the reference must dispatch marker-decay from THIS slot (marker_off == horizon_row).
    ref = bytearray(image)
    equiv._bind("g_game_update_fx_and_events")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    fired = equiv._r16(ref, adapter.A_marker_decay) != equiv._r16(image, adapter.A_marker_decay)
    marker_off = equiv._i16s(ref, adapter.A_marker_decay + 2)
    with capsys.disabled():
        print(f"  slot {slot} horizon {horizon:#x}: dispatched={fired} marker_off={marker_off:#x}")
    assert fired and marker_off == horizon, f"slot {slot}: expected dispatch from horizon {horizon:#x}"

    diffs = equiv.compare_course_events(lib, image)
    assert not diffs, f"fx slot {slot} (horizon {horizon:#x}) diverged: {diffs[:8]}"


# The 0x3d / 0x3e run-fills: fx[+6]==0x3d fills words +0..+0x13 with 0x3d, fx[+0x26]==0x3d fills
# +0x1a..+0x2f with 0x3e. Their only observable effect is redirecting §H's dispatch (the block is
# local scratch), so a warm frame never exercises them (mutation-verified: shortening either fill
# survives). Pin each by staging its trigger slot to 0x3d and aiming horizon_row at a byte the fill
# reaches but the (zeroed) band would leave 0 — so the fill turns a no-dispatch into a disp_finish.
# 0x3d -> idx 61 (finish A, collision_lock 0x90); 0x3e -> idx 62 (finish B, collision_lock 0x1a8).
FILL_CASES = {
    "run_3d": dict(slot=0, horizon=0x12, frac=1, lock=0x90),    # far end of the 0x3d fill -> fx[0x13]
    "run_3e": dict(slot=14, horizon=0x2c, frac=0, lock=0x1a8),  # far end of the 0x3e fill -> fx[0x2d]/[0x2f]
}


@pytest.mark.parametrize("case", sorted(FILL_CASES))
def test_fx_run_fills(case, capsys):
    kw = FILL_CASES[case]
    image = equiv.event_background(1, 40)
    for s in range(adapter.RM_RING_SLOTS):
        equiv._w16(image, A_OBJ_FLAGS + s * 2, 0)
    equiv._w16(image, A_OBJ_FLAGS + kw["slot"] * 2, FX_RUN_TRIGGER)   # 0x3d in the trigger slot
    equiv._w16(image, A_RING11_MARKER, 0)
    equiv._w16(image, A_HORIZON_ROW, kw["horizon"])
    equiv._w16(image, 0x18c6e, kw["frac"])          # horizon_frac (disp_finish A's a||b gate flag)
    equiv._w16(image, adapter.A_collision_lock, 0)  # so the finish record's write is unmistakable

    # coverage: the reference must dispatch the finish record (the fill reached that far byte).
    ref = bytearray(image)
    equiv._bind("g_game_update_fx_and_events")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    lock = equiv._r16(ref, adapter.A_collision_lock)
    with capsys.disabled():
        print(f"  {case}: reference collision_lock = {lock:#x} (want {kw['lock']:#x})")
    assert lock == kw["lock"], f"{case}: the run-fill did not dispatch the finish record"

    diffs = equiv.compare_course_events(lib, image)
    assert not diffs, f"{case} diverged: {diffs[:8]}"


FX_RUN_TRIGGER = 0x3d   # slot value that triggers a run-fill (fx[+6] / fx[+0x26] == 0x3d)
