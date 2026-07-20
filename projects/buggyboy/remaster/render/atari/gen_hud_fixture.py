#!/usr/bin/env python3
"""gen_hud_fixture.py — bake the remaster HUD's inputs into the on-target demo.

remaster only renders the HUD so far, and the HUD reads a set of assets (font, colour-fill table,
mask/cursor tables, the gauge string, the dashboard graphic and the variant sprites from buf_c) plus
a HudState — all of which normally come from the recreate loaders. Rather than run those on-target,
we capture them once on the host (same adapter the equivalence tests use) and emit:

  build/hud_fixture.h  — C arrays (assets + palette) and the HudState values main.c uses
  build/golden.bin     — recreate's g_draw_hud on a BLANK screen (the byte-for-byte reference:
                         remaster's on-target frame must equal this)
  build/palette.bin    — the 16 ST palette words (index 0 forced black), for the PNG

The demo draws only what remaster's C implements — the HUD, over a blank screen (no captured recreate
game frame). A byte-match of the on-target dump against golden.bin proves the remaster C is correct
compiled+run on a real 68000. (recreate's HUD is itself verified vs the Musashi oracle.)
"""
import ctypes
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]                       # remaster/
sys.path.insert(0, str(REMASTER / "test"))

import adapter                                    # noqa: E402  flat-image -> struct extraction
import equiv                                      # noqa: E402  mid-race staging + recreate pipeline

RACE_PALETTE = 0x17fa2                            # in-race palette (A_race_palette; loaded before the
                                                  # leg starts, reloaded by sprite-mode 4) — 16 ST words
PALETTE_BYTES = 32
# A visually busy mid-race HUD: a few flag bars + fuel columns, a plausible speed/time.
CONTROLS = {adapter.A_flag_seq_count: 3, adapter.A_crash_lap: 4,
            adapter.A_speed: 120, adapter.A_time_left: 45}


def _c_array(name, data):
    # aligned(2): the cores read these tables with be16/be32 (word/long moves), which fault on an odd
    # address on the 68000. A plain uint8_t[] has no alignment guarantee, so pin it to an even base.
    lines = [f"static const uint8_t {name}[{len(data)}] __attribute__((aligned(2))) = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + "".join(f"0x{b:02x}," for b in data[i:i + 16]))
    lines.append("};")
    return "\n".join(lines)


def hud_asset_arrays(img):
    """The HUD's static asset tables (font, fill/mask/cursor tables, gauge strings, dashboard + digit
    graphics from buf_c) as a list of (name, bytes). Shared by the HUD demo and the road+HUD demo."""
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
        ("fixture_dashboard_src",   win(buf_c + adapter.DASH_SRC_OFF, adapter.DASH_SRC_BYTES)),
        ("fixture_num_sprites",     win(buf_c + adapter.NUM_GLYPH_BUF_OFF, adapter.NUM_SPRITES_BYTES)),
    ]
    dsp_table, dsp_src = adapter._dsp_table_and_src(img, buf_c)   # phase-3 records (rebased) + sprites
    items.append(("fixture_dsp_table", dsp_table))
    items.append(("fixture_dsp_src", dsp_src))
    return items


def hud_state_defines(st):
    """The HudState scalar values as `#define` lines (main.c stages them into a native HudState)."""
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


def main():
    build = HERE / "build"
    build.mkdir(exist_ok=True)

    img = equiv.hud_background(leg=0, controls=CONTROLS)
    sb, nb = adapter.SCREEN_BASE, adapter.SCREEN_BYTES

    # Render only what remaster's C implements — the HUD, over a BLANK screen (no captured recreate
    # game frame). Zero the screen so both sides draw the HUD on the same empty background.
    img[sb:sb + nb] = bytes(nb)

    # recreate's HUD on that blank screen = the golden reference (byte-for-byte target).
    ref = bytearray(img)
    equiv._run_pipeline(ref, ("g_draw_hud",))
    (build / "golden.bin").write_bytes(bytes(ref[sb:sb + nb]))

    palette = race_palette(img)
    (build / "palette.bin").write_bytes(palette)

    st = adapter.hud_state(img)
    out = ["/* Generated by gen_hud_fixture.py — do not edit. Captured HUD inputs for the on-target",
           " * demo: the static asset tables, the dashboard + digit graphics, the palette, and the",
           " * HudState scalars. */",
           "#ifndef RM_HUD_FIXTURE_H", "#define RM_HUD_FIXTURE_H", "#include <stdint.h>", ""]
    for name, data in hud_asset_arrays(img):
        out.append(_c_array(name, data))
    out.append(_c_array("fixture_palette", palette))
    out.append("")
    out += hud_state_defines(st)
    out += ["", "#endif /* RM_HUD_FIXTURE_H */", ""]
    (build / "hud_fixture.h").write_text("\n".join(out))
    print(f"wrote {build/'hud_fixture.h'}, golden.bin, palette.bin "
          f"(flag={st.flag_seq_count} lap={st.crash_lap} speed={st.speed} time={st.time_left} "
          f"dsp_toggle={st.dsp_toggle} dsp_idx={st.dsp_variant_idx})")


if __name__ == "__main__":
    main()
