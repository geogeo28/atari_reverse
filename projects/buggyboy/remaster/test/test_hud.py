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
