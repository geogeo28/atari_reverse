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


def test_hud_dashboard_fallback_matches():
    """The phase-7 dashboard has two paths: the prebuilt bulk-copy (dash_pristine set) and the on-the-fly
    masked blit (dash_pristine NULL). rm_draw_hud picks the fallback when no pristine is supplied; pin it
    byte-exact too, so a regression to the fallback branch (wrong dst, dropped return) can't ship green."""
    lib = equiv._lib()
    image = equiv.hud_background(leg=0)
    coverage, wrong = equiv.compare_hud(lib, image, prebuild=False)
    assert wrong == 0 and coverage == 1.0, f"fallback dashboard blit diverged: wrong={wrong} cov={coverage}"


def test_hud_dashboard_is_opaque():
    """The dashboard bulk-copy is byte-exact ONLY because every dashboard group is fully opaque (mask==0):
    then cell_dashboard writes ink independent of the background, so a prebuilt snapshot equals the
    on-the-fly blit. Enforce that invariant on the actual per-leg art — a transparent group would make the
    prebuild composite over its own (zero/stale) buffer instead of the live top-fill, silently diverging."""
    DASH_GROUPS, ROW, DASH_ROWS = 8, 160, 40
    for leg in range(5):
        image = equiv.hud_background(leg=leg)
        buf_c = int.from_bytes(image[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
        src = buf_c + adapter.DASH_SRC_OFF
        for row in range(DASH_ROWS):
            for g in range(DASH_GROUPS):
                off = src + row * ROW + g * 8
                mask = (image[off] << 8) | image[off + 1]
                assert mask == 0, (f"leg{leg} dashboard group (row{row},g{g}) is NOT opaque (mask={mask:#06x})"
                                   " — the dash_pristine bulk-copy is unsafe; use the masked-blit fallback")


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


# Phase 6b (blinking small gauge) runs when no bonus units remain (crash_lap == 0). It draws only on
# the lit blink phase: bit1 of (gauge_blink - 1) set. (gauge_blink, gauge_blink_on) per case.
SMALL_GAUGE = [(3, 1), (3, 0), (7, 1), (1, 1), (0, 1)]   # last two: dark phase / wrapped -> no draw


@pytest.mark.parametrize("blink,blink_on", SMALL_GAUGE)
def test_hud_small_gauge(blink, blink_on):
    lib = equiv._lib()
    image = equiv.hud_background(leg=0, controls={adapter.A_crash_lap: 0,
                                                  adapter.A_gauge_blink: blink,
                                                  adapter.A_gauge_blink_on: blink_on})
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0, f"gauge_blink={blink} on={blink_on}: {wrong} wrong pixels"
    assert coverage == 1.0, f"gauge_blink={blink} on={blink_on}: only {coverage:.1%} covered"


# Phase 8 (crash / bonus tally) runs once the crash-arm timer is negative and crash_active is set.
# (crash_frame, crash_bars, time_left, crash_lap) drive the drain path + bar count.
CRASH = [
    (0x20, 3, 0, 0),    # rollover-drain path (time & lap exhausted), 3 bars
    (0x20, 5, 0, 0),    # 5 bars (extra bar5 pair)
    (0x20, 3, 50, 0),   # time-drain path
    (0x20, 3, 0, 4),    # lap-drain path
    (0x05, 3, 0, 0),    # frame < 0xa: no drain, just draw
    (0x20, 0, 0, 0),    # no bars
]


@pytest.mark.parametrize("frame,bars,time,lap", CRASH)
def test_hud_crash_fx(frame, bars, time, lap):
    lib = equiv._lib()
    image = equiv.hud_background(leg=0, controls={
        adapter.A_crash_active: 1, adapter.A_hud_crash_timer: 0xffff,   # timer < 0 -> draw_crash_fx
        adapter.A_crash_frame: frame, adapter.A_crash_bars: bars,
        adapter.A_time_left: time, adapter.A_crash_lap: lap})
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0, f"crash frame={frame:#x} bars={bars} t={time} lap={lap}: {wrong} wrong pixels"
    assert coverage == 1.0, f"crash frame={frame:#x} bars={bars}: only {coverage:.1%} covered"
