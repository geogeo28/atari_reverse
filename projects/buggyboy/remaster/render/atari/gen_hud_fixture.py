#!/usr/bin/env python3
"""gen_hud_fixture.py — bake the remaster HUD's inputs for the on-target build. A LIBRARY MODULE.

The HUD reads a set of assets (font, colour-fill table, mask/cursor tables, the gauge string, the
dashboard graphic and the variant sprites from buf_c) plus a HudState, all of which normally come from
the recreate loaders. Rather than run those on-target, we capture them once on the host (same adapter
the equivalence tests use). This module owns that capture — the asset windows, the HudState `#define`s
and the race palette — and gen_game_fixture.py calls it while emitting build/game_fixture.h.

It used to be a generator in its own right, writing build/hud_fixture.h + golden.bin + palette.bin for
the standalone HUD-only demo; that demo is retired (see render/atari/README.md) and the frame-0 golden
harness (run_golden.py) pins the whole pipeline instead.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]                       # remaster/
sys.path.insert(0, str(REMASTER / "test"))

import adapter                                    # noqa: E402  flat-image -> struct extraction

RACE_PALETTE = adapter.A_race_palette            # in-race palette (loaded before the leg starts, reloaded
                                                  # by sprite-mode 4) — the adapter owns this address,
                                                  # pinned vs game.h, so this stays one source of truth
PALETTE_BYTES = adapter.RACE_PAL_BYTES            # one ST palette (16 words)


def hud_asset_arrays(img, from_arena=False):
    """The HUD's static asset tables (font, fill/mask/cursor tables, gauge strings, dashboard + digit
    graphics from buf_c) as a list of (name, bytes).

    `from_arena=True` means the caller loads GRAPHICS.GRA itself at runtime (see include/assets.h),
    so the three tables that are graphics-file content — the dashboard graphic, the digit sprites and
    the phase-3 sprite pixels — are dropped, and `fixture_dsp_table` keeps its ORIGINAL src offsets
    (absolute within the graphics arena) instead of being rebased onto a compact extracted window.
    """
    buf_c = int.from_bytes(img[adapter.A_buf_c:adapter.A_buf_c + 4], "big")

    def win(addr, n):
        return bytes(img[addr:addr + n])

    items = [
        ("fixture_font",            win(adapter.A_font_glyphs, adapter.FONT_BYTES)),
        ("fixture_color_pairs",     win(adapter.A_color_pairs, adapter.COLOR_PAIRS_BYTES)),
        ("fixture_color_bar_mask",  win(adapter.A_color_bar_mask, adapter.COLOR_BAR_MASK_BYTES)),
        ("fixture_color_bar_cidx",  win(adapter.A_color_bar_cidx - adapter.CIDX_ZERO_OFF,
                                        adapter.CIDX_WINDOW_BYTES)),
        ("fixture_fuel_mask",       win(adapter.A_fuel_mask, adapter.FUEL_MASK_BYTES)),
        ("fixture_hud_text",        win(adapter.A_hud_text, adapter.HUD_TEXT_BYTES)),
        ("fixture_small_gauge_str", win(adapter.A_small_gauge_str, adapter.SMALL_GAUGE_STR_BYTES)),
        ("fixture_num_glyph_tbl",   win(adapter.A_num_glyph_tbl, adapter.NUM_TBL_BYTES)),
        ("fixture_crash_color_tbl", win(adapter.A_crash_color_tbl, adapter.CRASH_COLOR_TBL_BYTES)),
        ("fixture_score_delta_time", win(adapter.A_score_delta_time, adapter.SCORE_DELTA_BYTES)),
        ("fixture_score_delta_roll", win(adapter.A_score_delta_roll, adapter.SCORE_DELTA_BYTES)),
    ]
    if from_arena:
        items.append(("fixture_dsp_table", win(adapter.A_dsp_table, adapter.DSP_TABLE_BYTES)))
        return items

    items += [
        ("fixture_dashboard_src",   win(buf_c + adapter.DASH_SRC_OFF, adapter.DASH_SRC_BYTES)),
        ("fixture_num_sprites",     win(buf_c + adapter.NUM_GLYPH_BUF_OFF, adapter.NUM_SPRITES_BYTES)),
    ]
    dsp_table, dsp_src = adapter._dsp_table_and_src(img, buf_c)   # phase-3 records (rebased) + sprites
    items.append(("fixture_dsp_table", dsp_table))
    items.append(("fixture_dsp_src", dsp_src))
    return items


def hud_state_defines(st):
    """The HudState scalar values as `#define` lines (game_main.c stages them into a native HudState)."""
    return [
        f"#define CIDX_ZERO_OFF        {adapter.CIDX_ZERO_OFF}",
        f"#define HUD_FLAG_SEQ_COUNT   {st.flag_seq_count}",
        f"#define HUD_FLAG_SEQ_OFF     {st.flag_seq_off}",
        f"#define HUD_DSP_COLOR_SCROLL {st.dsp_color_scroll}",
        f"#define HUD_CRASH_LAP        {st.crash_lap}",
        f"#define HUD_SPEED            {st.speed}",
        f"#define HUD_TIME_LEFT        {st.time_left}",
        f"#define HUD_GAME_OVER        {int(st.game_over)}",
        f"#define HUD_DSP_TOGGLE       {int(st.dsp_toggle)}",
        f"#define HUD_DSP_VARIANT_IDX  {st.dsp_variant_idx}",
        f"#define HUD_GAUGE_BLINK      {st.gauge_blink}",
        f"#define HUD_GAUGE_BLINK_ON   {int(st.gauge_blink_on)}",
        f"#define HUD_CRASH_ACTIVE     {int(st.crash_active)}",
        f"#define HUD_CRASH_FRAME      {st.crash_frame}",
        f"#define HUD_CRASH_BARS       {st.crash_bars}",
        f"#define HUD_CRASH_TIMER      {st.hud_crash_timer}",
    ]


def race_palette(img):
    """The 16 ST palette words for the on-target display, index 0 forced black (so 'not drawn' reads
    as black rather than the background colour)."""
    palette = bytearray(img[RACE_PALETTE:RACE_PALETTE + PALETTE_BYTES])
    palette[0:2] = b"\x00\x00"
    return bytes(palette)


if __name__ == "__main__":
    sys.exit("gen_hud_fixture is a library module, not a generator — the on-target fixture is emitted by "
             "gen_game_fixture.py (run via render/atari/build_game.sh).")
