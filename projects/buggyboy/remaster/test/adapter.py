"""adapter.py — bridge recreate's flat image to remaster's native structs.

Phase A validates the remaster renderer from real captured state: this maps the recreate globals
and static asset tables a renderer reads out of the flat image into the ctypes structs remaster's C
takes. It is test-only scaffolding — the seam that lets one captured snapshot drive both sides so
their framebuffers can be diffed (see ../README.md). The shipped remaster game shares none of it.
"""
import ctypes
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
for p in ("oracle", "test", "render", "tools"):
    sys.path.insert(0, str(RECREATE / p))

import harness                                    # noqa: E402  recreate's image accessors / .so
import render_screen as R                         # noqa: E402  SCREEN_BASE + buffer layout

SCREEN_BASE = R.SCREEN_BASE
SCREEN_BYTES = R.ROW_STRIDE * R.H                 # 32000

# ---- recreate globals the HUD reads (mirror recreate/include/addrs.h) ----
A_flag_seq_count, A_flag_seq_off = 0x18c48, 0x18c40
A_dsp_color_scroll, A_crash_lap = 0x18d06, 0x18c4a
A_dsp_toggle, A_crash_active, A_hud_crash_timer = 0x18c7c, 0x18c7a, 0x18c4c
A_speed, A_time_left, A_game_over_flag = 0x18cf6, 0x18cfc, 0x18c34
A_dsp_variant_idx = 0x18c7e
A_gauge_blink, A_gauge_blink_on = 0x18d02, 0x18d04
A_crash_frame, A_crash_bars = 0x18c78, 0x18d00

# ---- render_road globals + geometry tables (mirror recreate/include/road_bands.h + addrs.h) ----
A_road_width_tbl = 0x18f24                        # per-scanline control longs (reset per band group)
A_road_param = 0x1623a                            # monotonic perspective/edge-seed/count word stream
A_road_edge_base = 0x15c3a                        # edge-run word table base (road_edge_sel added)
A_road_edge_sel = 0x18c5a                         # signed word added to the edge-table base
A_road_edge_const = 0x15b7a                       # three const edge-texture strips (STATIC region)
A_buf_b = 0x18c04                                 # pointer: road-texture (buf_b) base

# ---- build_road_geometry globals + const source tables (mirror recreate/include/addrs.h) ----
A_road_seg_data = 0x18d1c                          # per-leg segment slopes: [0] + [1..12] (13 shorts)
A_view_flags = 0x18c56                             # view/leg selector (0,2,4,6)
A_road_curve = 0x18c6a                             # signed road curvature (steering)
A_horizon = 0x1905e                                # horizon position input
A_road_seg_head = 0x18cb6                          # out: cached seg_data[0]
A_horizon_row = 0x18c6c                            # out: clamped horizon scanline
A_horizon_frac = 0x18c6e                           # out: horizon sub-row parity
A_persp_seg_tbl = 0x17156                          # const: per-segment run lengths
A_road_width_src = 0x18d5a                         # const-ish: width source shorts, stride 0x20
A_width_count_tbl = 0x1718a                        # const: per-row width run counts (4 banks of 16)
A_road_curve_tbl = 0x18efc                          # builder output region (== render_road width_tbl base)

# render_road control-table geometry (mirror include/game.h RM_CTRL_* — pinned by test_geometry)
RM_CTRL_LONGS = 106
RM_CTRL_BYTES = RM_CTRL_LONGS * 4
RM_CTRL_WIDTH_OFF = 0x28
RM_SCANLINE_BYTES = 0x80
ROAD_PERSP_SEG_BYTES = 0x31                         # persp_seg_tbl length (PERSP_SEGMENTS + 1)
ROAD_WIDTH_SRC_BYTES = 14 * 0x20                    # 14 rows at stride 0x20
ROAD_WIDTH_COUNT_BYTES = 0x40                       # 4 view banks of 16 run counts

# ---- blit_road_scroll globals (mirror recreate/include/addrs.h) ----
A_hscroll_step2 = 0x18cac                           # out: seg_head * scroll_speed * 2
A_scroll_speed = 0x18cb4                            # signed horizontal scroll speed
A_hscroll_pos = 0x18cb8                             # in/out: fine-scroll position, wrapped [0,0x280)
A_screen_offset = 0x18d18                           # road-scroll offset into buf_c
SCROLL_PLAY_BYTES = 0x1b00                          # playfield window from buf_c+screen_offset (>= reads)




# ---- static asset tables the HUD reads (STATIC.BIN region) ----
A_color_pairs = 0x15afa                           # 16 colours x 8-byte fill
A_color_bar_mask = 0x17d14                        # phase-5 {mask,ink} stream (5 cols x 12 rows x 4B)
A_color_bar_cidx = 0x17e40                        # phase-5 colour-index cursor (signed-offset window)
A_fuel_mask = 0x17f08                             # phase-6a two mask longs
A_font_glyphs = 0x176a8                           # phase-7 1bpp glyph table (16 bytes/char)
A_gauge_str = 0x18218                             # phase-7 gauge-cluster label/bar string
A_hud_text = 0x18172                               # base of the shared HUD-text working region
A_small_gauge_str = 0x18206                       # phase-6b blinking small-gauge string
A_dsp_table = 0x1854c                             # phase-3 records {src_off:long, dst_off:word, rows-1:word}
A_buf_c = 0x18c08                                 # pointer: base of the unpacked-graphics buffer
A_num_glyph_tbl = 0x17c5e                          # phase-8 per-digit word offset into the num sprites
A_crash_color_tbl = 0x17f5a                        # phase-8 per-frame colour index (indexed frame&7)
A_score_delta_time, A_score_delta_roll = 0x1737c, 0x17382   # phase-8 6-byte add_score deltas
DASH_SRC_OFF = 0x11c20                            # phase-7 dashboard graphic at buf_c + this
NUM_GLYPH_BUF_OFF = 0xbb80                          # phase-8 digit sprites at buf_c + this
COLOR_PAIRS_BYTES = 16 * 8
COLOR_BAR_MASK_BYTES = 5 * 12 * 4
FUEL_MASK_BYTES = 8
FONT_BYTES = 0x600                                # glyphs 0..0x5f (all the gauge string uses)
GAUGE_STR_BYTES = 64                              # covers the 6 phase-7 substrings (indices 0..52)
HUD_TEXT_BYTES = 0xe6                              # shared HUD-text region [0x18172, 0x18258)
SMALL_GAUGE_STR_BYTES = 32                         # phase-6b gauge0 + optional bar substrings
DASH_SRC_BYTES = 40 * 160                         # 40 rows at the screen stride
DSP_RECORDS = 8                                   # phase-3 variant records
DSP_TABLE_BYTES = DSP_RECORDS * 8
NUM_TBL_BYTES = 0xc0                               # phase-8 num_glyph_tbl (glyphs up to 0x5f; letters too)
NUM_SPRITES_BYTES = 0xb300                         # phase-8 num/label sprites (covers digits + "-BONUS-")
CRASH_COLOR_TBL_BYTES = 8
SCORE_DELTA_BYTES = 6
CIDX_ZERO_OFF = 0x200                             # window is [-0x200, +0x200) around the cursor base
CIDX_WINDOW_BYTES = 2 * CIDX_ZERO_OFF

# ---- render_road window sizes (see road_input) ----
ROAD_WIDTH_TBL_BYTES = 0x200                       # >= the 96 control longs any one band group reads
ROAD_PARAM_BYTES = 0x2000                          # >= the words the monotonic param cursor consumes
ROAD_EDGE_PAD = 0x400                              # edge cursor walks +/- this around base+sel
ROAD_EDGE_WINDOW_BYTES = 2 * ROAD_EDGE_PAD
ROAD_CONST_BYTES = 0x60                            # covers the three const strips + their longs
ROAD_TEX_PAD_LO = 0x4000                           # slack below buf_b for negative perspective seeds
ROAD_TEX_HI = 0x10000                              # above buf_b: group steps + src deltas + edge masks
ROAD_TEX_WINDOW_BYTES = ROAD_TEX_PAD_LO + ROAD_TEX_HI



class HudState(ctypes.Structure):
    _fields_ = [("flag_seq_count", ctypes.c_int16), ("flag_seq_off", ctypes.c_int16),
                ("dsp_color_scroll", ctypes.c_int16), ("crash_lap", ctypes.c_int16),
                ("speed", ctypes.c_uint16), ("time_left", ctypes.c_uint16),
                ("game_over", ctypes.c_bool), ("dsp_toggle", ctypes.c_bool),
                ("dsp_variant_idx", ctypes.c_uint16),
                ("gauge_blink", ctypes.c_uint16), ("gauge_blink_on", ctypes.c_bool),
                ("crash_active", ctypes.c_bool), ("crash_frame", ctypes.c_int16),
                ("crash_bars", ctypes.c_uint16), ("hud_crash_timer", ctypes.c_int16)]


class HudAssets(ctypes.Structure):
    _fields_ = [("color_pairs", ctypes.POINTER(ctypes.c_uint8)),
                ("color_bar_mask", ctypes.POINTER(ctypes.c_uint8)),
                ("color_bar_cidx", ctypes.POINTER(ctypes.c_uint8)),
                ("fuel_mask", ctypes.POINTER(ctypes.c_uint8)),
                ("font", ctypes.POINTER(ctypes.c_uint8)),
                ("hud_text", ctypes.POINTER(ctypes.c_uint8)),
                ("dashboard_src", ctypes.POINTER(ctypes.c_uint8)),
                ("dsp_table", ctypes.POINTER(ctypes.c_uint8)),
                ("dsp_src", ctypes.POINTER(ctypes.c_uint8)),
                ("small_gauge_str", ctypes.POINTER(ctypes.c_uint8)),
                ("num_sprites", ctypes.POINTER(ctypes.c_uint8)),
                ("num_glyph_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("crash_color_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("score_delta_time", ctypes.POINTER(ctypes.c_uint8)),
                ("score_delta_roll", ctypes.POINTER(ctypes.c_uint8))]


class Framebuffer(ctypes.Structure):
    _fields_ = [("px", ctypes.c_uint8 * SCREEN_BYTES)]


class RoadInput(ctypes.Structure):
    _fields_ = [("width_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("param", ctypes.POINTER(ctypes.c_uint8)),
                ("edge_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("tex", ctypes.POINTER(ctypes.c_uint8)),
                ("edge_const", ctypes.POINTER(ctypes.c_uint8))]


class RoadPose(ctypes.Structure):
    _fields_ = [("curve", ctypes.c_int16), ("view_flags", ctypes.c_uint16),
                ("seg_data", ctypes.c_int16 * 13),
                ("seg_head", ctypes.c_int16), ("horizon_row", ctypes.c_int16),
                ("horizon_frac", ctypes.c_int16)]


class RoadSource(ctypes.Structure):
    _fields_ = [("persp_seg", ctypes.POINTER(ctypes.c_int8)),
                ("width_src", ctypes.POINTER(ctypes.c_uint8)),
                ("width_count", ctypes.POINTER(ctypes.c_uint8))]


class ScrollState(ctypes.Structure):
    _fields_ = [("seg_head", ctypes.c_int16), ("scroll_speed", ctypes.c_int16),
                ("hscroll_pos", ctypes.c_uint16), ("hscroll_step2", ctypes.c_uint16)]


def _i16(image, addr):
    v = (image[addr] << 8) | image[addr + 1]
    return v - 0x10000 if v & 0x8000 else v


def hud_state(image):
    """The dynamic HUD scalars the ported phases read, as a native HudState."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    return HudState(_i16(image, A_flag_seq_count), _i16(image, A_flag_seq_off),
                    _i16(image, A_dsp_color_scroll), _i16(image, A_crash_lap),
                    u16(A_speed), u16(A_time_left), u16(A_game_over_flag) != 0,
                    u16(A_dsp_toggle) != 0, u16(A_dsp_variant_idx),
                    u16(A_gauge_blink), u16(A_gauge_blink_on) != 0,
                    u16(A_crash_active) != 0, _i16(image, A_crash_frame),
                    u16(A_crash_bars), _i16(image, A_hud_crash_timer))


def _dsp_table_and_src(image, buf_c):
    """Phase-3 assets: the record table with each src_off rebased to a compact buf_c window, and
    that window. recreate reads sprite pixels at buf_c + src_off; we extract only the span the 8
    records reference and rewrite src_off relative to it, so the candidate does dsp_src + src_off."""
    table = bytearray(image[A_dsp_table:A_dsp_table + DSP_TABLE_BYTES])
    recs = []
    for i in range(DSP_RECORDS):
        o = i * 8
        src_off = int.from_bytes(table[o:o + 4], "big")
        rows = int.from_bytes(table[o + 6:o + 8], "big")
        recs.append((o, src_off, rows))
    lo = min(src_off for _, src_off, _ in recs)
    hi = max(src_off + (rows + 1) * R.ROW_STRIDE + 8 for _, src_off, rows in recs)
    for o, src_off, _ in recs:
        table[o:o + 4] = (src_off - lo).to_bytes(4, "big")
    dsp_src = image[buf_c + lo:buf_c + hi]
    return bytes(table), bytes(dsp_src)


def hud_assets(image):
    """The static HUD asset tables as a native HudAssets. Returns (assets, keepalive) — the caller
    must hold `keepalive` for as long as `assets` is used (it owns the underlying buffers)."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    buf_c = int.from_bytes(image[A_buf_c:A_buf_c + 4], "big")
    color_pairs = buf(A_color_pairs, COLOR_PAIRS_BYTES)
    color_bar_mask = buf(A_color_bar_mask, COLOR_BAR_MASK_BYTES)
    fuel_mask = buf(A_fuel_mask, FUEL_MASK_BYTES)
    font = buf(A_font_glyphs, FONT_BYTES)
    hud_text = buf(A_hud_text, HUD_TEXT_BYTES)
    small_gauge_str = buf(A_small_gauge_str, SMALL_GAUGE_STR_BYTES)
    dashboard_src = buf(buf_c + DASH_SRC_OFF, DASH_SRC_BYTES)
    dsp_table_bytes, dsp_src_bytes = _dsp_table_and_src(image, buf_c)
    dsp_table = (ctypes.c_uint8 * len(dsp_table_bytes))(*dsp_table_bytes)
    dsp_src = (ctypes.c_uint8 * len(dsp_src_bytes))(*dsp_src_bytes)
    num_sprites = buf(buf_c + NUM_GLYPH_BUF_OFF, NUM_SPRITES_BYTES)
    num_glyph_tbl = buf(A_num_glyph_tbl, NUM_TBL_BYTES)
    crash_color_tbl = buf(A_crash_color_tbl, CRASH_COLOR_TBL_BYTES)
    score_delta_time = buf(A_score_delta_time, SCORE_DELTA_BYTES)
    score_delta_roll = buf(A_score_delta_roll, SCORE_DELTA_BYTES)
    # cidx is indexed by a signed cursor offset, so extract a window and point at its zero offset.
    cidx_window = buf(A_color_bar_cidx - CIDX_ZERO_OFF, CIDX_WINDOW_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    assets = HudAssets(
        ctypes.cast(color_pairs, p),
        ctypes.cast(color_bar_mask, p),
        ctypes.cast(ctypes.byref(cidx_window, CIDX_ZERO_OFF), p),
        ctypes.cast(fuel_mask, p),
        ctypes.cast(font, p),
        ctypes.cast(hud_text, p),
        ctypes.cast(dashboard_src, p),
        ctypes.cast(dsp_table, p),
        ctypes.cast(dsp_src, p),
        ctypes.cast(small_gauge_str, p),
        ctypes.cast(num_sprites, p),
        ctypes.cast(num_glyph_tbl, p),
        ctypes.cast(crash_color_tbl, p),
        ctypes.cast(score_delta_time, p),
        ctypes.cast(score_delta_roll, p),
    )
    return assets, (color_pairs, color_bar_mask, fuel_mask, font, hud_text, dashboard_src,
                    dsp_table, dsp_src, small_gauge_str, num_sprites, num_glyph_tbl,
                    crash_color_tbl, score_delta_time, score_delta_roll, cidx_window)


def framebuffer(image):
    """The current draw buffer (SCREEN_BASE..+32000) as a native Framebuffer."""
    return Framebuffer((ctypes.c_uint8 * SCREEN_BYTES)(*image[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES]))


def road_input(image):
    """The render_road geometry tables + texture as a native RoadInput. Returns (input, keepalive) —
    the caller must hold `keepalive` for as long as `input` is used (it owns the buffers).

    recreate threads one flat image and reads `image + offset`; here each table is its own buffer:
      - width_tbl / param   : extracted from their fixed bases (sized to the max the cursors consume);
      - edge_tbl            : a padded window pointed at base + road_edge_sel (the cursor walks +/-);
      - tex                 : a padded window around buf_b, pointed AT the buf_b origin (src deltas go
                              up, negative perspective seeds go into the pad below);
      - edge_const          : the three const edge-texture strips (STATIC region).
    """
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    buf_b = int.from_bytes(image[A_buf_b:A_buf_b + 4], "big")
    edge_sel = _i16(image, A_road_edge_sel)

    width_tbl = buf(A_road_width_tbl, ROAD_WIDTH_TBL_BYTES)
    param = buf(A_road_param, ROAD_PARAM_BYTES)
    edge_const = buf(A_road_edge_const, ROAD_CONST_BYTES)
    # edge cursor starts at base + sel and walks +/-, so window it with padding and point at the start.
    edge_window = buf(A_road_edge_base + edge_sel - ROAD_EDGE_PAD, ROAD_EDGE_WINDOW_BYTES)
    # texture: point at buf_b with slack below for negative seeds (cursor-zero window).
    tex_window = buf(buf_b - ROAD_TEX_PAD_LO, ROAD_TEX_WINDOW_BYTES)

    p = ctypes.POINTER(ctypes.c_uint8)
    inp = RoadInput(
        ctypes.cast(width_tbl, p),
        ctypes.cast(param, p),
        ctypes.cast(ctypes.byref(edge_window, ROAD_EDGE_PAD), p),
        ctypes.cast(ctypes.byref(tex_window, ROAD_TEX_PAD_LO), p),
        ctypes.cast(edge_const, p),
    )
    return inp, (width_tbl, param, edge_const, edge_window, tex_window)


def road_pose(image):
    """The dynamic road-geometry inputs the builder integrates, as a native RoadPose (outputs zeroed)."""
    seg = (ctypes.c_int16 * 13)(*(_i16(image, A_road_seg_data + i * 2) for i in range(13)))
    return RoadPose(_i16(image, A_road_curve),
                    (image[A_view_flags] << 8) | image[A_view_flags + 1], seg, 0, 0, 0)


def road_source(image):
    """The const source tables the builder reads, as a native RoadSource. Returns (source, keepalive)."""
    persp = (ctypes.c_int8 * ROAD_PERSP_SEG_BYTES)(
        *(_i16b(image[A_persp_seg_tbl + i]) for i in range(ROAD_PERSP_SEG_BYTES)))
    width_src = (ctypes.c_uint8 * ROAD_WIDTH_SRC_BYTES)(
        *image[A_road_width_src:A_road_width_src + ROAD_WIDTH_SRC_BYTES])
    width_count = (ctypes.c_uint8 * ROAD_WIDTH_COUNT_BYTES)(
        *image[A_width_count_tbl:A_width_count_tbl + ROAD_WIDTH_COUNT_BYTES])
    source = RoadSource(ctypes.cast(persp, ctypes.POINTER(ctypes.c_int8)),
                        ctypes.cast(width_src, ctypes.POINTER(ctypes.c_uint8)),
                        ctypes.cast(width_count, ctypes.POINTER(ctypes.c_uint8)))
    return source, (persp, width_src, width_count)


def _i16b(b):
    """Reinterpret an unsigned byte as a signed int8 (for the persp_seg run-length table)."""
    return b - 0x100 if b & 0x80 else b


def scroll_state(image):
    """The dynamic scroll scalars blit_road_scroll reads, as a native ScrollState (step2 output zeroed)."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    return ScrollState(_i16(image, A_road_seg_head), _i16(image, A_scroll_speed),
                       u16(A_hscroll_pos), 0)


def scroll_playfield(image):
    """The double-wide road playfield window blit_road_scroll samples (buf_c + screen_offset), as a
    ctypes array. Returns (ptr, keepalive)."""
    buf_c = int.from_bytes(image[A_buf_c:A_buf_c + 4], "big")
    off = buf_c + _i16(image, A_screen_offset)
    play = (ctypes.c_uint8 * SCROLL_PLAY_BYTES)(*image[off:off + SCROLL_PLAY_BYTES])
    return ctypes.cast(play, ctypes.POINTER(ctypes.c_uint8)), play
