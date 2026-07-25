"""test_hud.py — remaster HUD pixel-equivalence vs recreate's verified g_draw_hud.

Each case stages a realistic mid-race frame, pokes the HUD control scalars to exercise the ported
phases (4 flag-bars, 5 colour-bars, 6a fuel-gauge), then asserts the remaster candidate draws NO
wrong pixel (every byte it paints matches recreate). Footprint coverage is reported for progress.
"""
import adapter
import assets_load
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


@pytest.mark.parametrize("leg", range(5))
def test_hud_dashboard_transparent_composites_over_frame(leg):
    """The RUNTIME per-leg mini-map (the course map init_leg_dash builds from the leg's block) is
    TRANSPARENT — cell_dashboard keeps the framebuffer background wherever a group's mask word is 0xffff,
    so only the course-outline groups are opaque. Phase 7 must therefore composite it over the LIVE frame
    (the road's sky behind the top-left panel), exactly as recreate's g_draw_hud does.

    This drives the real init_leg_dash (the shell's op_rebuild_dash path) over a fully rendered mid-race
    frame, then pins the remaster's HUD byte-exact to recreate. It is the coverage the baked-fixture path
    (test_hud_ported_phases / hud_background) never reaches: that stages the leg-independent OPAQUE atlas,
    so a prebuilt bulk-copy of it happened to equal the masked blit. On this transparent art a bulk-copy
    composites over its own background-less buffer and paints a BLACK box over the sky — the mini-map bug
    (STATUS.md). Here the masked blit keeps the sky and only draws the outline; a regression back to a
    background-baked copy reddens this test."""
    lib = equiv._lib()
    image = equiv.hud_background(leg=leg)              # road/sky drawn into the frame; opaque baked dash in buf_c
    # Point init_leg_dash at the loaded arena: mem_base (its per-leg block source) = the arena base, which
    # mid_race_state leaves NULL in the image (it inits natively) — recover it from buf_c (= base+RM_GFX_OFF).
    buf_c = int.from_bytes(image[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
    mem_base = buf_c - assets_load.RM_GFX_OFF
    image[adapter.A_mem_base:adapter.A_mem_base + 4] = mem_base.to_bytes(4, "big")
    image[adapter.A_leg_index:adapter.A_leg_index + 2] = leg.to_bytes(2, "big")
    equiv._run_pipeline(image, ("g_init_leg_dash",))  # -> the per-leg TRANSPARENT course map at buf_c+DASH_SRC_OFF
    off = buf_c + adapter.DASH_SRC_OFF
    mask0 = (image[off] << 8) | image[off + 1]
    assert mask0 == 0xffff, (f"leg{leg}: init_leg_dash did not yield a transparent dashboard (group-0 mask="
                             f"{mask0:#06x}); this pin would not be exercising the transparent path")
    coverage, wrong = equiv.compare_hud(lib, image)
    assert wrong == 0, f"leg{leg}: transparent dashboard HUD diverged from recreate (wrong={wrong})"
    assert coverage == 1.0, f"leg{leg}: HUD footprint only {coverage:.1%} covered"


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
