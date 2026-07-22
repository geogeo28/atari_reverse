"""test_crash_fx.py — the crash / end-of-race tally's STATE side (rm_crash_fx_update).

hud.c's hud_crash_fx renders the tally each frame off a throwaway HUD-text copy (verified pixel-exact
by test_hud). rm_crash_fx_update is its persistent counterpart: HUD phase 8's timer decay plus
draw_crash_fx's mutations — crash_frame, the bonus drain (time_left / crash_lap / the score-digit
rollover records), the score, and the abort_flag countdown that ends the leg. Each directed case here
stages one branch and compares every scalar the update owns, plus the whole HUD-text window, against
recreate's own HUD phase 8 (decay, or g_draw_crash_fx once the timer is negative) — see
equiv.compare_crash_fx / _ref_crash_fx.
"""
import adapter
import equiv
import pytest

# The crash-fx state globals the cases poke (word writes via event_background's pokes).
TIMER, ACTIVE, FRAME = adapter.A_hud_crash_timer, adapter.A_crash_active, adapter.A_crash_frame
LAP, BARS, TIME_LEFT, ABORT = (adapter.A_crash_lap, adapter.A_crash_bars,
                               adapter.A_time_left, adapter.A_abort_flag)

# A crash_frame past which frame (== crash_frame + 1) clears CRASH_FRAME_MIN so the drain body runs.
FRAME_DRAINING = 0x20
TIMER_NEG = 0xffff          # any negative hud_crash_timer runs the tally
ROLL_BASE = adapter.RM_CRASH_ROLLOVER_OFF    # rollover records within the HUD-text region
ROLL_STRIDE = adapter.RM_CRASH_ROLL_STRIDE
ROLL_DONE_SUM = adapter.RM_CRASH_ROLL_TARGET # a record with tens + ones == this is already drained (skipped)


def _record_off(image_off, rec):
    """Image address of rollover record `rec`'s ones digit (its tens digit is the byte before)."""
    return image_off + ROLL_BASE + rec * ROLL_STRIDE


def _poke_record(state, rec, tens, ones):
    """Stage rollover record `rec`: tens digit at off-1, ones digit at off (recreate's digit[-1]/digit)."""
    off = _record_off(adapter.A_hud_text, rec)
    state[off - 1] = tens & 0xff
    state[off] = ones & 0xff


def _run(pokes, records=None):
    """Stage a crash-fx frame (word pokes + optional rollover records) and compare the update against
    recreate. Returns the mismatch list."""
    lib = equiv._lib()
    state = equiv.event_background(1, 40, pokes)
    for rec, (tens, ones) in (records or {}).items():
        _poke_record(state, rec, tens, ones)
    return equiv.compare_crash_fx(lib, state)


def _assert_ok(mismatches, label):
    assert not mismatches, f"{label} diverged from recreate: " + "; ".join(
        f"{n}: candidate {c} != recreate {r}" for n, c, r in mismatches[:8])


def test_timer_decays_while_positive():
    """A positive hud_crash_timer just counts down by RM_HUD_CRASH_DECAY — no tally yet."""
    _assert_ok(_run({TIMER: 0x40}), "positive-decay")


def test_timer_decays_across_zero_to_negative():
    """A small positive timer decays straight past zero into the negative range (the frame the tally
    is about to take over) — the sign transition, in one step."""
    _assert_ok(_run({TIMER: 0x1}), "decay-to-negative")


def test_game_over_arms_abort_when_no_crash_active():
    """Timer negative with crash_active == 0: there is nothing to tally, so abort_flag arms 0xffff at
    once (game over) and the drain never runs."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 0}), "game-over-arm")


def test_frame_below_min_advances_without_draining():
    """Timer negative, crash_active set, but crash_frame + 1 has not reached CRASH_FRAME_MIN yet: the
    frame counter advances and the score/lap lines refresh, but nothing drains."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: 0x2, TIME_LEFT: 0x30}), "frame-below-min")


def test_time_left_drains_first():
    """With bonus time remaining, the tally drains time_left (and scores it) before anything else."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0x30}),
               "time-drain")


def test_crash_lap_drains_after_time():
    """Once time_left is exhausted, the tally drains the bonus-unit count (crash_lap)."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 3}),
               "lap-drain")


def test_rollover_carry_branch():
    """Time and laps done: a rollover record whose ones digit isn't the tens-reset value steps the
    ones by 5 and carries one out of the tens (recreate's digit += 5; digit[-1] -= 1)."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 0, BARS: 1},
                    records={0: (0x20, 0x20)}), "rollover-carry")


def test_rollover_tens_reset_branch():
    """The 0x35 tens-reset branch: a ones digit of 0x35 resets by -5 instead of carrying."""
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 0, BARS: 1},
                    records={0: (0x10, 0x35)}), "rollover-tens-reset")


def test_rollover_walks_to_first_undone_record():
    """The drain walks records 0..crash_bars-1 and steps the FIRST one not already at its target: here
    records 0-2 are done (tens + ones == 0x60) and record 3 is stepped, over a crash_bars-5 span."""
    done = (0x30, 0x30)
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 0, BARS: 5},
                    records={0: done, 1: done, 2: done, 3: (0x20, 0x20), 4: done}),
               "rollover-multi-walk")


def test_nothing_left_arms_abort_0x33():
    """Everything drained (time 0, lap 0, all records at target) and abort_flag still 0: the tally arms
    the 0x33 abort countdown."""
    done = (0x30, 0x30)
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 0, BARS: 2},
                    records={0: done, 1: done}), "arm-0x33")


def test_abort_flag_decays_each_frame():
    """An already-armed abort_flag (0x33) is not re-armed; it decays by 2 toward zero every tally
    frame (and past it, ending the leg)."""
    done = (0x30, 0x30)
    _assert_ok(_run({TIMER: TIMER_NEG, ACTIVE: 1, FRAME: FRAME_DRAINING, TIME_LEFT: 0, LAP: 0,
                     BARS: 2, ABORT: 0x33}, records={0: done, 1: done}), "abort-decay")


def test_timer_zero_is_inert():
    """hud_crash_timer == 0 does nothing at all (the tally is neither counting down nor running)."""
    _assert_ok(_run({TIMER: 0, ACTIVE: 1}), "timer-zero")
