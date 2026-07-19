"""test_hud.py — remaster HUD pixel-equivalence vs recreate's verified g_draw_hud.

Each case stages a realistic mid-race frame, pokes the HUD control scalars to exercise the ported
phases (4 flag-bars, 5 colour-bars, 6a fuel-gauge), then asserts the remaster candidate draws NO
wrong pixel (every byte it paints matches recreate). Footprint coverage is reported for progress.
"""
import adapter
import equiv
import pytest

# (flag_seq_count, crash_lap, flag_seq_off, dsp_color_scroll) — exercise each ported phase's inputs.
CONFIGS = [
    (0, 0, 0, 0),      # phase 5 only (flag bars off, fuel gauge off)
    (1, 1, 0, 0),      # one flag bar + one fuel column
    (3, 4, 0, 0),      # several bars + several fuel columns
    (5, 5, 8, 0),      # max-ish bars/columns + a colour-cursor offset
    (2, 3, 0, 8),      # colour-cursor scrolled the other way
]


def _controls(flag_seq_count, crash_lap, flag_seq_off, dsp_color_scroll):
    return {adapter.A_flag_seq_count: flag_seq_count, adapter.A_crash_lap: crash_lap,
            adapter.A_flag_seq_off: flag_seq_off, adapter.A_dsp_color_scroll: dsp_color_scroll}


@pytest.mark.parametrize("cfg", CONFIGS)
def test_hud_ported_phases_no_wrong_pixel(cfg, capsys):
    lib = equiv._lib()
    image = equiv.hud_background(leg=0, controls=_controls(*cfg))
    coverage, wrong = equiv.compare_hud(lib, image)
    with capsys.disabled():
        print(f"  cfg={cfg}: coverage={coverage:.1%} wrong_bytes={wrong}")
    assert wrong == 0, f"candidate painted {wrong} pixels recreate does not (cfg={cfg})"
    # phases 1,2,4,5,6a,7 are ported; phase 3 (dsp_toggle) and phase 8 (crash) are gated off in
    # hud_background, so the candidate must reproduce the ENTIRE remaining footprint.
    assert coverage == 1.0, f"HUD footprint only {coverage:.1%} covered (cfg={cfg})"


# (speed, time) — exercise the phase-1/2 digit formatting across the real domain: every speedometer
# prefix branch (<100 "//", 100-199 "/1", >=200 "/2") and leading-blank vs. leading-zero tens, and
# the 2-digit timer 0..99. Speed is a byte (0..255); the timer field is 2 digits (0..99).
SPEED_TIME = [(0, 0), (7, 5), (45, 42), (99, 99), (100, 10), (150, 0), (199, 60), (200, 88), (255, 90)]


@pytest.mark.parametrize("speed,time", SPEED_TIME)
def test_hud_speed_time_digits(speed, time):
    lib = equiv._lib()
    controls = {adapter.A_speed: speed, adapter.A_time_left: time,
                adapter.A_flag_seq_count: 1, adapter.A_crash_lap: 2}
    image = equiv.hud_background(leg=0, controls=controls)
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0, f"speed={speed} time={time}: {wrong} wrong pixels"
    assert coverage == 1.0, f"speed={speed} time={time}: only {coverage:.1%} covered"


# Phase 3 selects one of 8 dashboard-variant records via dsp_variant_idx (a byte offset, step 8).
DSP_VARIANTS = [0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38]


@pytest.mark.parametrize("idx", DSP_VARIANTS)
def test_hud_dsp_variant(idx):
    lib = equiv._lib()
    # dsp_toggle defaults to 0 (phase 3 on) in hud_background; pick each variant sprite.
    image = equiv.hud_background(leg=0, controls={adapter.A_dsp_variant_idx: idx})
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0, f"dsp_variant_idx={idx:#x}: {wrong} wrong pixels"
    assert coverage == 1.0, f"dsp_variant_idx={idx:#x}: only {coverage:.1%} covered"


def test_hud_dsp_toggle_off():
    """dsp_toggle set -> phase 3 draws nothing on both sides (gate respected)."""
    lib = equiv._lib()
    image = equiv.hud_background(leg=0, controls={adapter.A_dsp_toggle: 1})
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0 and coverage == 1.0
