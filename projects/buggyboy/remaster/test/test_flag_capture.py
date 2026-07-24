"""test_flag_capture.py — the flag-sequence pickup, end to end.

The playtest bug: driving into a flag "did nothing". The flag STATE path (the §H horizon dispatch of a
flag_gate event, the flag-order match, the score, the object consumption) was correct and already
tracked by the leg drives — but the shell never fanned the flag-sequence counters (GobjPrefixState's
flag_seq_count / flag_seq_off / dsp_color_scroll) into the HUD view, so the phase-4 flag-sequence bars
never drew: the capture was invisible. This pins the whole chain:

  1. rm_gobj_hud_view fans the three flag fields into HudState (the shell's draw_frame runs it after
     rm_gobj_prefix, before rm_draw_hud). Pinned by rendering the HUD from the FANNED view and matching
     recreate's g_draw_hud — with the flag fields ZEROED first, so a dropped fan makes the bars vanish.
  2. A directed drive actually CAPTURES flags in order, asserted non-vacuously on BOTH sides.
  3. The flag_gate branches the dispatch fuzz never reaches (flag_seq_count at the 5-in-a-row bonus, the
     wrap past the window, and the bonus_timer forced-match) are staged and compared to recreate.
"""
import ctypes

import adapter
import equiv
import pytest

ACCEL = 0x01


# ---- 1. the HUD fan-out (the fix) ------------------------------------------------------------------
# (flag_seq_count, flag_seq_off, dsp_color_scroll): flag_seq_count > 0 draws bars, so a dropped fan
# (flag fields left 0) loses them. The zero case guards that the fan does not INVENT bars.
FAN_CONFIGS = [(0, 0, 0), (1, 0, 0), (3, 0, 0), (5, 8, 0), (2, 0, 8)]


@pytest.mark.parametrize("cfg", FAN_CONFIGS)
def test_hud_flag_bars_are_fanned_in(cfg, capsys):
    """The HUD drawn from a HudState whose flag fields come ONLY from rm_gobj_hud_view (zeroed first,
    then fanned from the GobjPrefixState) must match recreate's g_draw_hud byte-for-byte. This is the
    shell seam compare_hud bypasses (it stages the flag fields straight from the image)."""
    seq, off, scroll = cfg
    lib = equiv._lib()
    image = equiv.hud_background(leg=0, controls={
        adapter.A_flag_seq_count: seq, adapter.A_flag_seq_off: off,
        adapter.A_dsp_color_scroll: scroll, adapter.A_crash_lap: 0})
    coverage, wrong = equiv.compare_hud_flag_fan(lib, image)
    with capsys.disabled():
        print(f"  cfg={cfg}: coverage={coverage:.1%} wrong_bytes={wrong}")
    assert wrong == 0, f"candidate painted {wrong} pixels recreate does not (cfg={cfg})"
    assert coverage == 1.0, f"HUD footprint only {coverage:.1%} covered (cfg={cfg})"


def test_hud_flag_fan_is_nonvacuous(capsys):
    """The pin above is only meaningful if the flag bars are actually part of the footprint — i.e. a
    HudState with the flag fields left ZERO (the un-fanned bug) really does draw fewer bytes than one
    with them fanned in. Confirm a captured sequence adds pixels the empty one does not."""
    lib = equiv._lib()
    base = equiv.hud_background(leg=0, controls={adapter.A_flag_seq_count: 0, adapter.A_crash_lap: 0})
    ref_empty = bytearray(base)
    equiv._run_pipeline(ref_empty, ("g_draw_hud",))
    captured = equiv.hud_background(leg=0, controls={adapter.A_flag_seq_count: 5, adapter.A_crash_lap: 0})
    ref_bars = bytearray(captured)
    equiv._run_pipeline(ref_bars, ("g_draw_hud",))
    lo, n = adapter.SCREEN_BASE, adapter.SCREEN_BYTES
    added = sum(a != b for a, b in zip(ref_empty[lo:lo + n], ref_bars[lo:lo + n]))
    with capsys.disabled():
        print(f"  flag bars add {added} framebuffer bytes vs an empty sequence")
    assert added > 0, "flag_seq_count made no visible difference — the fan pin would be vacuous"


# ---- 2. a directed capture drive -------------------------------------------------------------------
# leg 2's flat-out drive captures the first two flags in order (frames ~57/~90) while the candidate runs
# its own event engine; every owned surface (incl. gobj.flag_seq_count and the HUD-text score digits) is
# compared strictly each frame. The old leg drives capture flags only incidentally on other legs — this
# one asserts a capture HAPPENED (non-vacuous, both sides) so the whole pickup path stays exercised.
CAPTURE_FRAMES = 300


def test_directed_flag_capture_drive(capsys):
    lib = equiv._lib()
    image = equiv.leg_start_background(2)
    state = bytearray(image)
    buf = (ctypes.c_uint8 * equiv.bench_frame.IMAGE_SIZE).from_buffer(state)
    gu = equiv._bind("g_game_update")
    cand = equiv._Candidate(lib, state)
    equiv._sound_reset(lib)                     # fresh Dosound ledgers (this drive compares sound too)
    mismatches, ref_max, cand_max = [], 0, 0
    for f in range(CAPTURE_FRAMES):
        equiv._drive_frame(cand, state, buf, gu, ACCEL)
        mismatches.extend(equiv._drive_mismatches(f, cand, state))
        ref_max = max(ref_max, equiv._s16(state, adapter.A_flag_seq_count))
        cand_max = max(cand_max, cand.gobj.flag_seq_count)
        if mismatches:
            break
    with capsys.disabled():
        print(f"  leg 2 flat-out: ref_max_seq={ref_max} cand_max_seq={cand_max} "
              f"mismatches={len(mismatches)}")
    assert not mismatches, "flag-capture drive diverged from recreate: " + "; ".join(
        f"frame {fr} {name}: candidate {c} != recreate {r}" for fr, name, c, r in mismatches[:8])
    assert ref_max >= 1 and cand_max >= 1, \
        f"no flag was captured on both sides — the pickup path went untested (ref={ref_max}, cand={cand_max})"


# ---- 3. the flag_gate branches the dispatch fuzz never reaches --------------------------------------
# The per-handler fuzz (test_events) stages flag_seq_count at its leg-start default (0), so it only ever
# exercises the "advance from 0" branch. Stage it AT the window boundaries to reach: the 5-in-a-row
# bonus (seq 4 -> 5 arms bonus_timer 0x3c), the wrap past the window (seq >= 5 -> 1), the bonus_timer
# forced-match (a wrong type still advances while the bonus window is open), and the plain out-of-order
# miss (no advance, gate score only). Every case is compared scalar-for-scalar to recreate.
_SEQS = (0, 1, 3, 4, 5, 6)
_BONUS = (0, 0x3c)
_FLAG_IDX = tuple(range(1, 13))   # idx 1-12: the flag_gate + forced-gate entries


def test_flag_gate_branches_match_recreate(capsys):
    lib = equiv._lib()
    gu = equiv._gu_dispatch_fn()
    bad = []
    saw = {"bonus_armed": 0, "wrapped": 0, "forced_match": 0, "out_of_order_miss": 0}
    for seq in _SEQS:
        for bonus in _BONUS:
            for idx in _FLAG_IDX:
                pokes = {adapter.A_flag_seq_count: seq, adapter.A_bonus_timer: bonus,
                         adapter.A_collision_lock: 0}
                image = equiv.event_background(1, 40, pokes=pokes)
                diffs = equiv.compare_event_dispatch(lib, image, idx, 3, 0, 0)
                if diffs:
                    bad.append((seq, bonus, idx, diffs[:3]))
                # observe the reference branch reached (ground truth for the non-vacuous coverage).
                ref = bytearray(equiv.event_background(1, 40, pokes=pokes))
                rbuf = (ctypes.c_uint8 * equiv.bench_frame.IMAGE_SIZE).from_buffer(ref)
                gu(rbuf, idx, 3, 0, 0)
                post_seq = equiv._s16(ref, adapter.A_flag_seq_count)
                post_bonus = equiv._r16(ref, adapter.A_bonus_timer)
                if post_seq == 5 and seq == 4 and post_bonus == 0x3c:
                    saw["bonus_armed"] += 1
                if seq >= 5 and post_seq == 1:
                    saw["wrapped"] += 1
                if bonus != 0 and post_seq == seq + 1 and idx <= 5:
                    saw["forced_match"] += 1
                if bonus == 0 and seq == 0 and post_seq == 0 and idx <= 5:
                    saw["out_of_order_miss"] += 1
    with capsys.disabled():
        print(f"  branch coverage on the reference: {saw}; diverging cases: {len(bad)}")
    assert not bad, "flag_gate diverged from recreate:\n" + "\n".join(
        f"  seq={s} bonus={b:#x} idx={i}: {d}" for s, b, i, d in bad[:8])
    for branch, n in saw.items():
        assert n > 0, f"the {branch!r} flag_gate branch was never reached — coverage is vacuous ({saw})"
