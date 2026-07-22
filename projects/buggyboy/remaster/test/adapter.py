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
LIBREMASTER = REMASTER / "build" / "libremaster.so"   # the candidate .so; one definition for all callers
for p in ("oracle", "test", "render", "tools"):
    sys.path.insert(0, str(RECREATE / p))

import harness                                    # noqa: E402  recreate's image accessors / .so
import render_screen as R                         # noqa: E402  SCREEN_BASE + buffer layout

SCREEN_BASE = R.SCREEN_BASE
SCREEN_BYTES = R.ROW_STRIDE * R.H                 # 32000

# draw-buffer selection: physbase_tbl indexed by the (word) flip_idx (mirror recreate/draw.h).
A_flip_idx = 0x18bf2
A_physbase_tbl = 0x18bf4

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
A_width_count_tbl = 0x1718a                        # const: per-row width run counts (4 banks of 16)
A_road_curve_tbl = 0x18efc                          # builder output region (== render_road width_tbl base)

# render_road control-table geometry (mirror include/game.h RM_CTRL_* — the copies are pinned equal
# by test_course_ring.test_python_constants_match_the_c; the spill pad is additionally pinned to the
# stamp loop's measured write extent by test_geometry)
RM_CTRL_LONGS = 106
RM_CTRL_BYTES = RM_CTRL_LONGS * 4
RM_CTRL_STAMP_SPILL = 8                                # stage 4's band stamp spills past the table; alloc covers it
RM_CTRL_ALLOC_BYTES = RM_CTRL_BYTES + RM_CTRL_STAMP_SPILL
RM_CTRL_WIDTH_OFF = 0x28
RM_SCANLINE_BYTES = 0x80
ROAD_PERSP_SEG_BYTES = 0x31                         # persp_seg_tbl length (PERSP_SEGMENTS + 1)
ROAD_WIDTH_COUNT_BYTES = 0x40                       # 4 view banks of 16 run counts

# ---- blit_road_scroll globals (mirror recreate/include/addrs.h) ----
A_hscroll_step2 = 0x18cac                           # out: seg_head * scroll_speed * 2
A_scroll_speed = 0x18cb4                            # signed horizontal scroll speed
A_hscroll_pos = 0x18cb8                             # in/out: fine-scroll position, wrapped [0,0x280)
A_screen_offset = 0x18d18                           # road-scroll offset into buf_c
SCROLL_PLAY_BYTES = 0x1b00                          # playfield window from buf_c+screen_offset (>= reads)
RM_SCROLL_SHIFTS = 16                               # mirror include/game.h
RM_SCROLL_WINDOW = 0x1a00

# ---- course advance (game_update section 12 geometry) globals + stream (mirror addrs.h) ----
A_buf_a = 0x18c00                                   # pointer: buffer a (holds the packed course streams)
A_leg_index = 0x18c38                               # current leg (0-4)
A_course_row_ctr = 0x18c52                          # course-record row countdown
A_course_read_pos = 0x18c50                         # byte offset into the packed course stream
COURSE_STREAM_OFF = 0x5ce0                          # leg_base + this: packed course record stream base
COURSE_LEG_STRIDE = 0x2000                          # per-leg stride in buf_a
COURSE_STREAM_PAD = 0x2000                          # window reaches this far BELOW the base (records grow down)
COURSE_STREAM_BYTES = COURSE_STREAM_PAD + 0x10      # headroom above the base. Structural bound, not a
                                                    # data survey: a record can select all 15 slots, so
                                                    # the code run reads rec+3..rec+17, and read_pos >= 8
                                                    # keeps rec <= base-8 -> last byte < base+0x10.

# The course object/marker ring: RM_RING_ROWS bands of RM_RING_SLOTS type-code words plus a marker
# word, contiguous in the image below road_curve_tbl. The named globals are columns of this grid —
# road_width_src/sprite_list_base is row 0's marker, ground_scan_tbl row i's slot 6, obj_flags row
# 12's slot 0 — and road_seg_data is its row -1. Mirror include/game.h.
A_ring_base = 0x18d3c
RM_RING_ROWS = 14
RM_RING_SLOTS = 15
RING_ROW_BYTES = (RM_RING_SLOTS + 1) * 2            # 0x20 — one band


# ---- player buggy / foreground sprite globals + const piece tables (mirror addrs.h) ----
A_sp_lean = 0x18cc2                                 # body lean; body_tbl index + hi-overlay gate + variant
A_sp_pitch = 0x18cbe                               # vertical buggy position offset (road pitch)
A_sp_skid = 0x18cbc                                # horizontal buggy skid offset (+/-8)
A_sp_crash_disp = 0x18c68                          # vertical crash displacement
A_sp_wheel_pos = 0x18cc0                           # wheel/steer position; lower-body list selector
A_sp_variant = 0x18cc6                             # scratch: lean * 8 (draw_buggy_hi reads it back)
A_sp_spin_state = 0x18caa                          # <0 while spinning after a crash (byte)
A_sp_road_curve = 0x18c6a                          # signed road curvature
A_sp_sprite_suppress = 0x18cd0                     # nonzero suppresses the foreground sprite
A_sp_fg_gate = 0x18ebb                             # bit7 set suppresses the foreground sprite (byte)
A_sp_anim_frame = 0x18d0c                          # word byte-offset into fg_anim_tbl
A_sp_spin_counter = 0x18d0a                        # frames the buggy spins (out; lower-body index)
A_sp_spin_reset = 0x18cc8                          # longword; nonzero suppresses the lower body
A_sp_buggy_draw_flag = 0x18d0e                     # nonzero enables the lower-body draw
A_sp_buggy_gate = 0x18eba                          # OR'd with fg_gate; bit7 suppresses the lower body (byte)
A_sp_collision_lock = 0x18c84                      # nonzero suppresses the lower body
A_sp_speed_raw = 0x18cf8                           # raw speed; drives the lean-animation rate
A_sp_lean_accum = 0x18d10                          # in/out: lean-anim rate accumulator
A_sp_lean_frame = 0x18d12                          # in/out: lean-anim frame offset into hi piece table
A_fg_anim_tbl = 0x177a0                            # foreground frames: {rows-1:w, dst:w, src:l} x8
A_body_tbl = 0x177b8                               # per-lean body sprite: {src:l, flag:b, rows-1:b, pos:w}
A_hi_tbl = 0x17554                                 # rate bytes at [speed>>5], then lean-overlay pieces
A_lo_piece_tbl = 0x17746                           # lower-body piece lists
A_lo_piece_idx = 0x1773c                           # per-wheel_pos word offset into lo_piece_tbl
# The four const piece tables lie in one contiguous STATIC span; extract it whole so cross-table
# offsets stay faithful, and index each pointer from its own base.
SP_TBL_BASE = A_hi_tbl                             # lowest of the four tables
SP_TBL_BYTES = 0x400                               # covers hi/lo/fg/body tables (0x17554..0x17938)
SP_GFX_BYTES = 0x3b000                             # buf_c graphics arena span the sprites index into


# ---- ground / horizon band globals + const tables (mirror addrs.h + src/road.c) ----
A_ground_scan_tbl = 0x18d48                         # 13 descriptors, stride 0x20; marker byte at +3
A_ground_view_off = 0x18c58                         # signed view column into the ground offset table
A_ground_col_tbl = 0x16a6e                          # per-entry buffer offset words (stride 0x22) + view
A_ground_band_records = 0x172ea                     # 0x1a gradient records, stride 8
GROUND_SCAN_ENTRIES = 13
GROUND_SCAN_STRIDE = 0x20
GROUND_MARKER_OFF = 3                               # marker byte within each descriptor
GROUND_COL_TBL_BYTES = 0x800                        # covers 13 entries (stride 0x22) + max view (6*0xdd)
GROUND_BAND_RECORDS_BYTES = 0x40                   # 7 gradient records; rec6 (bands=7) reads 8 colours,
#                                                    past its 8-byte slot into the following bytes


# ---- scaled roadside object (draw_object) globals + const edge-mask tables (mirror addrs.h) ----
A_obj_shade = 0x18c5e                               # sign selects the centre-band / near fill pattern
A_blit_mask_l = 0x15bba                             # left-edge antialias masks, indexed (x&0xf)<<2
A_blit_mask_r = 0x15bfa                             # right-edge antialias masks
OBJ_MASK_BYTES = 0x40                               # 16 entries * 4 bytes (index (x&0xf)<<2 -> 0..0x3c)
# draw_object reads the road control table from A_road_width_tbl (already defined for render_road) and
# scans up to ~96 rows of it; ROAD_WIDTH_TBL_BYTES (0x200) already covers that.


# ---- roadside-object display-list dispatcher (draw_object_list) globals + tables (mirror addrs.h) ----
A_obj_list_base = 0x16c06                           # a5 base: fixed-object-list pass display stream
A_obj_flags = 0x18ebc                               # a3 base: fixed-object-list pass flag stream
A_obj_sprite_disp = 0x16a90                         # a5 base: sprite-driven passes display stream
A_obj_sprite_flags = 0x18d5c                        # a3 base: sprite-driven passes flag stream
A_obj_xoff_tbl = 0x18f26                            # a4 base: per-row shared x-offset word
A_obj_type_jumptable = 0x13144                      # word offset per jumpidx -> handler label
A_obj_view_xform = 0x1722a                          # per-view sprite transform records
A_objsh2p_tbl = 0x171ca                             # per-scanline dst-offset table (objshift2 P-prefix)
A_view_parity = 0x18c60                             # per-view parity word (handler_lo reads &2)
A_bonus_timer = 0x18d08                             # nonzero clamps low object types up to the minimum
A_obj_scan_off = 0x18c58                            # signed word added to the list cursor (== ground_view_off)
A_sprite_list_base = 0x18d5a                        # sprite-count loop base (== ring row 0's marker)
A_p24_flag = 0x18231                                # global byte gating the P24 three-stage path
GOBJ_SPRITE_SLOTS = 0xa                             # up to 11 sprite slots counted after the base
GOBJ_MARKER_STRIDE = 0x20
GOBJ_SPRITE_LAST = 10
GOBJ_ROW_A3_STRIDE = 0x20
GOBJ_ROW_A5_STRIDE = 0x22
GOBJ_D6_INIT = 0xb0
GOBJ_D6_ROW_STEP = 0x10
GOBJ_VIEW_REAR = 4

# ---- gobj_prefix (draw_game_objects prefix) globals + tables (mirror addrs.h) ----
A_marker_decay = 0x18cf0                            # [0]=active word, [2]=record byte-offset, [4]=countdown
A_marker_decay_base = 0x18d34                       # base of the 14 decay records (stride 0x20)
A_anim_counter = 0x17f10                            # frame counter (+=2/frame); &0x1e indexes anim tables
A_anim_word_tbl = 0x17ec8                           # word table -> anim_word, indexed (counter & 0x1e)
A_anim_word = 0x18c74                               # current anim word (mirrored into buf_a)
A_anim_coloridx_tbl = 0x17ee8                       # word table -> color_pairs offset (<<3)
A_anim_color = 0x17f08                              # current 8-byte (2-long) animated colour pair
GOBJ_ANIM_BUF_OFF1 = 0xd70                          # buf_a + this = anim_word mirror 1
GOBJ_ANIM_BUF_OFF2 = 0x1250                         # buf_a + this = anim_word mirror 2
MARKER_RECS_BYTES = 0x340                           # covers the 14-record decay slot (+ signed offset window)

# ---- player physics (game_update sections 3,4,5,7,8,9,10) globals + tables (mirror addrs.h) ----
A_input_state, A_input_prev = 0x18c44, 0x18c42
A_engine_rpm, A_leg_flags_c90 = 0x18c8c, 0x18c90    # rpm; the {rpm_cap, rpm_add} pair
A_speed_raw, A_speed_jitter_ph = 0x18cf8, 0x18c94
A_scroll_phase, A_view_bank, A_view_wrap_flag = 0x18c8e, 0x18c54, 0x18c9a
A_wheel_pos, A_steer_hold, A_lean_phase = 0x18cc0, 0x18ccc, 0x18cce
A_lean_state, A_buggy_draw_flag = 0x18cc2, 0x18d0e
A_curve_clamp_flag, A_buggy_skid_off, A_crash_disp = 0x18d1a, 0x18cbc, 0x18c68
A_sprite_suppress = 0x18cd0                         # holds the PREVIOUS frame's buggy_skid_off
A_fire_hold, A_leg_flags_sel = 0x18c98, 0x18c96
A_time_subctr, A_timeout_gate = 0x18cfe, 0x18c3e
A_collision_lock, A_event_pending = 0x18c84, 0x18c82  # crash-script cursor; event_pending must stay 0
A_crash_phase, A_spin_reset, A_curve_freeze = 0x18c86, 0x18cc8, 0x18d16
A_turn_flags = 0x18c80                              # auto/view turn flag bits (crash script input)
A_curve_window = 0x18c88                            # long: the {lo, hi} road_curve skip window
A_steer_delta, A_buggy_pitch_off = 0x18cae, 0x18cbe  # crash-script curve kick; body pitch
A_anim_frame, A_marker_pending = 0x18d0c, 0x18d14   # the script writes anim_frame's SECOND byte
A_crash_anim_tbl = 0x18690                          # 8-byte crash-script records at collision_lock
A_lean_anim_tbl = 0x173ac                           # byte: lean at lean_phase + (rpm & 0x70)
A_scroll_speed_tbl = 0x1742c                        # word: scroll rate at scroll_phase + (rpm & 0x70)
A_speed_jitter_tbl = 0x17394                        # word: speedometer jitter at jitter_ph & 0xe
A_steer_curve_tbl = 0x174ec                         # byte: curvature delta (signed row index)
A_legflag_tbl = 0x173a4                             # long records {rpm_cap, rpm_add}
LEAN_ANIM_TBL_BYTES = 0x80                          # lean_phase 0..0xf + rpm band 0..0x70
SCROLL_SPEED_TBL_BYTES = 0x80                       # same index range, as words
SPEED_JITTER_TBL_BYTES = 0x10                       # jitter_ph & 0xe
LEGFLAG_TBL_BYTES = 8                               # the two selectable records
# The whole record region, up to the next global (0x18b68). Sizing this to the crash records alone is
# wrong: the finish/bonus display events also park collision_lock in here, at indices past 0x400, and
# an undersized window reads zeros — which walks the script forever instead of terminating.
CRASH_ANIM_TBL_BYTES = 0x4d8
STEER_CURVE_ZERO_OFF = 0x40                         # (skid + wheel) << 3 reaches -0x40
STEER_CURVE_WINDOW_BYTES = STEER_CURVE_ZERO_OFF + 0x80   # ...and +0x60 + the rpm column





# ---- course-event engine (game_update §12 tail + the jump-table dispatch) globals + assets ----
A_course_flag_bit = 0x18c70                        # collision-probe bit cursor (byte)
A_dash_marker = 0x18c3a                            # dashboard progress marker: {y:b, bit:b, x:w}
A_ckpt_scroll = 0x18c72                            # checkpoint-banner scroll position
A_spin_state = 0x18caa                             # the fx<<8 word §G writes (word)
A_event_type = 0x18eca                             # ring row 12 slot 7 word; low byte = the §I event code
A_score_str = 0x18230                              # HUD score string (live digits at +4)
A_score_bcd = 0x1824c                              # 6 ASCII score digits
A_score_overlay_dig = 0x18215                      # bonus score-overlay digit
A_fx_type_tbl = 0x18640                            # spin/collision fx records, idx from the gate bits
A_evt_obj_type_tbl = 0x18b68                       # word[8] collision-object type per rpm band
A_score_deltas = 0x1736a                           # 7 x 6-byte BCD add_score deltas
A_score_label = 0x18540                            # "SCORE/" header; checkpoint char = [7 + crash_bars]
A_flag_seq_table = 0x17e3a                         # expected roadside-object type sequence
A_probe_deltas = 0x17e7a                           # 8 x {delta_bit:w, delta_x:w} neighbour probes
A_ckpt_anim_tbl = 0x17324                          # checkpoint-banner scroll control records
A_mem_base = 0x18bfc                               # raw per-leg dashboard block base (init_leg_dash source)
COURSE_MASK_OFF = 0x5d48                           # leg_base + this: per-course collision-flag longs
RM_EVENT_TABLE_ENTRIES = 65                        # mirror include/game.h (event idx 0..64)
RM_HUD_TIMER_LEG_END = 0x65                        # mirror include/game.h: §I's leg-complete sentinel
# Asset window sizes. Where the indexed range exceeds the next global, the range wins (correctness
# over the next-global heuristic) — see the fx_type_tbl note.
FX_TYPE_TBL_BYTES = 0x100                           # sel 0..7 -> a code fx in 1..0x7f, then read [fx..fx+0x17]
EVT_OBJ_TYPE_TBL_BYTES = 0x10                       # word[8], indexed by rpm band 0..0xe
SCORE_DELTAS_BYTES = 7 * 6                          # 7 contiguous 6-byte BCD records
SCORE_LABEL_BYTES = 0x20                            # score_label[7 + crash_bars]; crash_bars is the small
#                                                    checkpoint counter (0..5), so the deepest read is
#                                                    offset 0xc — well within score_label's own span (the
#                                                    next addrs.h global is fx_type_tbl at 0x18640, +0x100)
FLAG_SEQ_TABLE_BYTES = 0x40                         # expected[flag_seq_off + flag_seq_count]: 0x40 is the
#                                                    full span to the next global, probe_deltas at 0x17e7a
PROBE_DELTAS_BYTES = 8 * 4
CKPT_ANIM_TBL_BYTES = 0x50                          # 7 + 4 + 1 groups of control words
COLL_MASK_BYTES = 0x20                              # crash_bars << 2 (0..0x18) + a long
DASH_RAW_BYTES = 5 * 0x500                          # 5 legs of raw dashboard block (leg*0x500 stride)
BUF_A_DASH_BYTES = 0xa00                            # covers the leg-dash label/clear/marker-seed tables
FONT_GLYPH_BYTES = 0x600                            # glyphs 0..0x5f (16 bytes each)
GFX_EVENT_BYTES = 0x14000                           # buf_c window: banner (0x9c40) + dashboard (..0x13520)


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
# A live drive re-picks the edge bank every frame (road_edge_sel = (view_flags + view_bank) * 0x60,
# so 0..0xe * 0x60), which a single-bank window can't serve — the on-target demo bakes all of them.
ROAD_EDGE_SEL_MAX = 0xe * 0x60
ROAD_EDGE_ALL_BANKS_BYTES = ROAD_EDGE_PAD + ROAD_EDGE_SEL_MAX + ROAD_EDGE_PAD
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
                ("width_count", ctypes.POINTER(ctypes.c_uint8))]


class ScrollState(ctypes.Structure):
    _fields_ = [("seg_head", ctypes.c_int16), ("scroll_speed", ctypes.c_int16),
                ("hscroll_pos", ctypes.c_uint16), ("hscroll_step2", ctypes.c_uint16)]


class CourseState(ctypes.Structure):
    _fields_ = [("row_ctr", ctypes.c_uint16), ("read_pos", ctypes.c_uint16)]


class CourseRow(ctypes.Structure):
    _fields_ = [("slot", ctypes.c_uint16 * RM_RING_SLOTS), ("marker", ctypes.c_uint16)]


class CourseRing(ctypes.Structure):
    _fields_ = [("row", CourseRow * RM_RING_ROWS)]


class SpriteState(ctypes.Structure):
    _fields_ = [("lean", ctypes.c_uint16), ("pitch", ctypes.c_int16),
                ("skid", ctypes.c_int16), ("crash_disp", ctypes.c_int16),
                ("wheel_pos", ctypes.c_uint16), ("variant", ctypes.c_uint16),
                ("spin_state", ctypes.c_int8), ("road_curve", ctypes.c_int16),
                ("sprite_suppress", ctypes.c_uint16), ("fg_gate", ctypes.c_int8),
                ("anim_frame", ctypes.c_uint16), ("spin_counter", ctypes.c_uint16),
                ("spin_reset", ctypes.c_uint32), ("buggy_draw_flag", ctypes.c_uint16),
                ("buggy_gate", ctypes.c_uint8), ("collision_lock", ctypes.c_uint16),
                ("speed_raw", ctypes.c_uint16), ("lean_accum", ctypes.c_uint16),
                ("lean_frame", ctypes.c_uint16)]


class SpriteAssets(ctypes.Structure):
    _fields_ = [("gfx", ctypes.POINTER(ctypes.c_uint8)),
                ("fg_anim_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("body_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("hi_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("lo_piece_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("lo_piece_idx", ctypes.POINTER(ctypes.c_uint8))]


class GroundState(ctypes.Structure):
    _fields_ = [("markers", ctypes.c_uint8 * GROUND_SCAN_ENTRIES), ("view", ctypes.c_int16)]


class GroundAssets(ctypes.Structure):
    _fields_ = [("col_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("band_records", ctypes.POINTER(ctypes.c_uint8)),
                ("color_pairs", ctypes.POINTER(ctypes.c_uint8))]


class ObjectInput(ctypes.Structure):
    _fields_ = [("width_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("blit_mask_l", ctypes.POINTER(ctypes.c_uint8)),
                ("blit_mask_r", ctypes.POINTER(ctypes.c_uint8)),
                ("shade", ctypes.c_int16)]


class ObjListCtx(ctypes.Structure):
    _fields_ = [("px", ctypes.POINTER(ctypes.c_uint8)),
                ("draw_buf", ctypes.c_uint32),
                ("buf_a", ctypes.POINTER(ctypes.c_uint8)),
                ("buf_c", ctypes.POINTER(ctypes.c_uint8)),
                ("color_pairs", ctypes.POINTER(ctypes.c_uint8)),
                ("view_xform", ctypes.POINTER(ctypes.c_uint8)),
                ("objsh2p_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("jumptable", ctypes.POINTER(ctypes.c_uint8)),
                ("xoff_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("view_flags", ctypes.c_uint16),
                ("view_parity", ctypes.c_uint16),
                ("bonus_timer", ctypes.c_uint16),
                ("obj_scan_off", ctypes.c_int16),
                ("p24_flag", ctypes.c_uint8)]


class GobjPrefixState(ctypes.Structure):
    _fields_ = [("marker_active", ctypes.c_uint16), ("marker_off", ctypes.c_int16),
                ("marker_countdown", ctypes.c_int16), ("view_parity", ctypes.c_uint16),
                ("anim_counter", ctypes.c_uint16), ("anim_word", ctypes.c_uint16),
                ("bonus_timer", ctypes.c_uint16), ("dsp_color_scroll", ctypes.c_uint16),
                ("flag_seq_off", ctypes.c_uint16), ("flag_seq_count", ctypes.c_int16)]


class GobjPrefixAssets(ctypes.Structure):
    _fields_ = [("anim_word_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("anim_coloridx_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("color_pairs", ctypes.POINTER(ctypes.c_uint8)),
                ("marker_recs", ctypes.POINTER(ctypes.c_uint8)),
                ("anim_color", ctypes.POINTER(ctypes.c_uint8)),
                ("anim_mirror1", ctypes.POINTER(ctypes.c_uint8)),
                ("anim_mirror2", ctypes.POINTER(ctypes.c_uint8))]


class PlayerState(ctypes.Structure):
    _fields_ = [("input", ctypes.c_uint16), ("input_prev", ctypes.c_uint16),
                ("game_over", ctypes.c_bool), ("hscroll_step2", ctypes.c_int16),
                ("engine_rpm", ctypes.c_uint16), ("rpm_cap", ctypes.c_uint16),
                ("rpm_add", ctypes.c_uint16), ("speed_raw", ctypes.c_uint16),
                ("speed", ctypes.c_uint16), ("speed_jitter_ph", ctypes.c_uint16),
                ("scroll_phase", ctypes.c_uint16), ("scroll_speed", ctypes.c_int16),
                ("view_flags", ctypes.c_uint16), ("view_bank", ctypes.c_uint16),
                ("view_wrapped", ctypes.c_bool), ("ground_view_off", ctypes.c_int16),
                ("road_edge_sel", ctypes.c_int16),
                ("wheel_pos", ctypes.c_uint16), ("steer_hold", ctypes.c_uint16),
                ("lean_phase", ctypes.c_uint16), ("lean", ctypes.c_uint16),
                ("buggy_draw_flag", ctypes.c_uint16), ("road_curve", ctypes.c_int16),
                ("curve_clamp", ctypes.c_bool), ("skid", ctypes.c_int16),
                ("crash_disp", ctypes.c_int16),
                ("collision_lock", ctypes.c_uint16), ("crash_phase", ctypes.c_int16),
                ("turn_flags", ctypes.c_uint16), ("event_pending", ctypes.c_uint16),
                ("spin_reset", ctypes.c_uint16), ("spin_word2", ctypes.c_uint16),
                ("curve_window_lo", ctypes.c_uint16), ("curve_window_hi", ctypes.c_uint16),
                ("steer_delta", ctypes.c_int16), ("buggy_pitch_off", ctypes.c_int16),
                ("curve_freeze", ctypes.c_uint16),
                ("anim_frame_sel", ctypes.c_uint8), ("marker_pending", ctypes.c_uint8),
                ("fire_hold", ctypes.c_uint16), ("dsp_variant_idx", ctypes.c_uint16),
                ("leg_flags_sel", ctypes.c_uint16), ("time_subctr", ctypes.c_uint16),
                ("time_left", ctypes.c_int16), ("hud_crash_timer", ctypes.c_int16),
                ("timeout_gate", ctypes.c_bool)]


class PlayerAssets(ctypes.Structure):
    _fields_ = [("lean_anim_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("scroll_speed_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("speed_jitter_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("steer_curve_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("legflag_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("crash_anim_tbl", ctypes.POINTER(ctypes.c_uint8))]


class EventState(ctypes.Structure):
    _fields_ = [("course_flag_bit", ctypes.c_uint8), ("dash_y", ctypes.c_uint8),
                ("dash_bit", ctypes.c_uint8), ("dash_x", ctypes.c_uint16),
                ("crash_bars", ctypes.c_uint16), ("crash_active", ctypes.c_uint16),
                ("crash_lap", ctypes.c_uint16), ("gauge_blink", ctypes.c_uint16),
                ("gauge_blink_on", ctypes.c_uint16), ("ckpt_scroll", ctypes.c_uint16),
                ("spin_state", ctypes.c_uint16)]


class EventAssets(ctypes.Structure):
    _fields_ = [("fx_type_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("evt_obj_type_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("score_deltas", ctypes.POINTER(ctypes.c_uint8)),
                ("score_label", ctypes.POINTER(ctypes.c_uint8)),
                ("flag_seq_table", ctypes.POINTER(ctypes.c_uint8)),
                ("probe_deltas", ctypes.POINTER(ctypes.c_uint8)),
                ("ckpt_anim_tbl", ctypes.POINTER(ctypes.c_uint8)),
                ("coll_mask", ctypes.POINTER(ctypes.c_uint8)),
                ("buf_a", ctypes.POINTER(ctypes.c_uint8)),
                ("dash_raw", ctypes.POINTER(ctypes.c_uint8)),
                ("font", ctypes.POINTER(ctypes.c_uint8))]


class RmEventCtx(ctypes.Structure):
    _fields_ = [("player", ctypes.POINTER(PlayerState)),
                ("gobj", ctypes.POINTER(GobjPrefixState)),
                ("ring", ctypes.POINTER(CourseRing)),
                ("pose", ctypes.POINTER(RoadPose)),
                ("road_src", ctypes.POINTER(RoadSource)),
                ("ctrl", ctypes.POINTER(ctypes.c_uint8)),
                ("scanline", ctypes.POINTER(ctypes.c_uint8)),
                ("ev", ctypes.POINTER(EventState)),
                ("hud_text", ctypes.POINTER(ctypes.c_uint8)),
                ("gfx", ctypes.POINTER(ctypes.c_uint8)),
                ("assets", ctypes.POINTER(EventAssets)),
                ("leg", ctypes.c_uint16), ("game_over", ctypes.c_bool)]


def make_event_ctx(*, player, gobj, ring, pose, road_src, ctrl, scanline, ev, hud_text, gfx,
                   assets, leg, game_over):
    """Build an RmEventCtx from live structs/buffers by KEYWORD — wrapping each struct in a pointer
    and casting the byte buffers to uint8*. One builder so both the dispatch bundle (EventBundle) and
    the leg-drive candidate (equiv._Candidate) seed the ctx identically, without a positional field
    list either has to keep in sync with the struct."""
    u8 = ctypes.POINTER(ctypes.c_uint8)
    return RmEventCtx(
        player=ctypes.pointer(player), gobj=ctypes.pointer(gobj), ring=ctypes.pointer(ring),
        pose=ctypes.pointer(pose), road_src=ctypes.pointer(road_src),
        ctrl=ctypes.cast(ctrl, u8), scanline=ctypes.cast(scanline, u8), ev=ctypes.pointer(ev),
        hud_text=ctypes.cast(hud_text, u8), gfx=ctypes.cast(gfx, u8), assets=ctypes.pointer(assets),
        leg=leg, game_over=game_over)


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
    """The const source tables the builder reads, as a native RoadSource. Returns (source, keepalive).
    The road WIDTHS are not here — they are the ring's live marker column (see course_ring)."""
    persp = (ctypes.c_int8 * ROAD_PERSP_SEG_BYTES)(
        *(_i16b(image[A_persp_seg_tbl + i]) for i in range(ROAD_PERSP_SEG_BYTES)))
    width_count = (ctypes.c_uint8 * ROAD_WIDTH_COUNT_BYTES)(
        *image[A_width_count_tbl:A_width_count_tbl + ROAD_WIDTH_COUNT_BYTES])
    source = RoadSource(ctypes.cast(persp, ctypes.POINTER(ctypes.c_int8)),
                        ctypes.cast(width_count, ctypes.POINTER(ctypes.c_uint8)))
    return source, (persp, width_count)


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


def course_state(image):
    """The course-progress scalars (row_ctr / read_pos) as a native CourseState."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    return CourseState(u16(A_course_row_ctr), u16(A_course_read_pos))


def course_ring(image):
    """The course object/marker ring as a native CourseRing, read out of the image's row grid."""
    ring = CourseRing()
    for band in range(RM_RING_ROWS):
        row = A_ring_base + band * RING_ROW_BYTES
        for slot in range(RM_RING_SLOTS):
            ring.row[band].slot[slot] = (image[row + slot * 2] << 8) | image[row + slot * 2 + 1]
        ring.row[band].marker = (image[row + RM_RING_SLOTS * 2] << 8) | image[row + RM_RING_SLOTS * 2 + 1]
    return ring


def course_stream(image):
    """The current leg's packed course-record stream as a cursor-zero window: records live at
    NEGATIVE offsets from the stream base (rec = base - read_pos), so extract the span below the base
    and point at the base. Returns (ptr_at_base, keepalive)."""
    buf_a = int.from_bytes(image[A_buf_a:A_buf_a + 4], "big")
    leg = (image[A_leg_index] << 8) | image[A_leg_index + 1]
    base = buf_a + leg * COURSE_LEG_STRIDE + COURSE_STREAM_OFF
    window = (ctypes.c_uint8 * COURSE_STREAM_BYTES)(*image[base - COURSE_STREAM_PAD:base + 0x10])
    return ctypes.cast(ctypes.byref(window, COURSE_STREAM_PAD), ctypes.POINTER(ctypes.c_uint8)), window


def sprite_state(image):
    """The dynamic buggy/foreground-sprite scalars as a native SpriteState (variant/spin_counter and
    the lean-anim accum/frame get overwritten by the draws; seed them from the image regardless)."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    def i8(addr):
        return image[addr] - 0x100 if image[addr] & 0x80 else image[addr]
    return SpriteState(
        u16(A_sp_lean), _i16(image, A_sp_pitch), _i16(image, A_sp_skid),
        _i16(image, A_sp_crash_disp), u16(A_sp_wheel_pos), u16(A_sp_variant),
        i8(A_sp_spin_state), _i16(image, A_sp_road_curve), u16(A_sp_sprite_suppress),
        i8(A_sp_fg_gate), u16(A_sp_anim_frame), u16(A_sp_spin_counter),
        int.from_bytes(image[A_sp_spin_reset:A_sp_spin_reset + 4], "big"),
        u16(A_sp_buggy_draw_flag), image[A_sp_buggy_gate], u16(A_sp_collision_lock),
        u16(A_sp_speed_raw), u16(A_sp_lean_accum), u16(A_sp_lean_frame))


def sprite_assets(image):
    """The static buggy/foreground-sprite asset tables as a native SpriteAssets. Returns (assets,
    keepalive) — the caller must hold `keepalive` while `assets` is used. The four const piece tables
    are extracted as one contiguous STATIC window and each pointer is offset into it; `gfx` is the
    buf_c graphics arena the sprites index (src offsets are absolute within it)."""
    buf_c = int.from_bytes(image[A_buf_c:A_buf_c + 4], "big")
    gfx = (ctypes.c_uint8 * SP_GFX_BYTES)(*image[buf_c:buf_c + SP_GFX_BYTES])
    tbl = (ctypes.c_uint8 * SP_TBL_BYTES)(*image[SP_TBL_BASE:SP_TBL_BASE + SP_TBL_BYTES])
    p = ctypes.POINTER(ctypes.c_uint8)

    def at(addr):
        return ctypes.cast(ctypes.byref(tbl, addr - SP_TBL_BASE), p)

    assets = SpriteAssets(
        ctypes.cast(gfx, p),
        at(A_fg_anim_tbl), at(A_body_tbl), at(A_hi_tbl),
        at(A_lo_piece_tbl), at(A_lo_piece_idx))
    return assets, (gfx, tbl)


def ground_state(image):
    """The per-frame ground/horizon scalars as a native GroundState: the 13 descriptor markers
    (recreate reads the marker byte at +3 of each 0x20-stride descriptor) and the view column."""
    markers = (ctypes.c_uint8 * GROUND_SCAN_ENTRIES)(
        *(image[A_ground_scan_tbl + i * GROUND_SCAN_STRIDE + GROUND_MARKER_OFF]
          for i in range(GROUND_SCAN_ENTRIES)))
    return GroundState(markers, _i16(image, A_ground_view_off))


def ground_assets(image):
    """The static ground asset tables as a native GroundAssets. Returns (assets, keepalive)."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    col_tbl = buf(A_ground_col_tbl, GROUND_COL_TBL_BYTES)
    band_records = buf(A_ground_band_records, GROUND_BAND_RECORDS_BYTES)
    color_pairs = buf(A_color_pairs, COLOR_PAIRS_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    assets = GroundAssets(ctypes.cast(col_tbl, p), ctypes.cast(band_records, p),
                          ctypes.cast(color_pairs, p))
    return assets, (col_tbl, band_records, color_pairs)


def object_input(image):
    """The scaled-roadside-object inputs as a native ObjectInput. Returns (input, keepalive) — the
    caller must hold `keepalive` while `input` is used. width_tbl is the road control table (the same
    table render_road reads); the two edge-mask tables index by (x & 0xf) << 2."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    width_tbl = buf(A_road_width_tbl, ROAD_WIDTH_TBL_BYTES)
    mask_l = buf(A_blit_mask_l, OBJ_MASK_BYTES)
    mask_r = buf(A_blit_mask_r, OBJ_MASK_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    inp = ObjectInput(ctypes.cast(width_tbl, p), ctypes.cast(mask_l, p), ctypes.cast(mask_r, p),
                      _i16(image, A_obj_shade))
    return inp, (width_tbl, mask_l, mask_r)


def player_state(image, inputs=0):
    """The player-physics scalars as a native PlayerState, with `inputs` as this frame's input bits.
    skid is seeded from sprite_suppress — the original's dual-use global that carries the previous
    frame's off-road push into the steer-curve row (see game.h)."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]

    return PlayerState(
        inputs, u16(A_input_prev), u16(A_game_over_flag) != 0, _i16(image, A_hscroll_step2),
        u16(A_engine_rpm), u16(A_leg_flags_c90), u16(A_leg_flags_c90 + 2),
        u16(A_speed_raw), u16(A_speed), u16(A_speed_jitter_ph),
        u16(A_scroll_phase), _i16(image, A_scroll_speed),
        u16(A_view_flags), u16(A_view_bank), u16(A_view_wrap_flag) != 0,
        _i16(image, A_ground_view_off), _i16(image, A_road_edge_sel),
        u16(A_wheel_pos), u16(A_steer_hold), u16(A_lean_phase), u16(A_lean_state),
        u16(A_buggy_draw_flag), _i16(image, A_road_curve), u16(A_curve_clamp_flag) != 0,
        _i16(image, A_sprite_suppress), _i16(image, A_crash_disp),
        u16(A_collision_lock), _i16(image, A_crash_phase),
        u16(A_turn_flags), u16(A_event_pending),
        u16(A_spin_reset), u16(A_spin_reset + 2),
        u16(A_curve_window), u16(A_curve_window + 2),
        _i16(image, A_steer_delta), _i16(image, A_buggy_pitch_off), u16(A_curve_freeze),
        image[A_anim_frame + 1], image[A_marker_pending],
        u16(A_fire_hold), u16(A_dsp_variant_idx), u16(A_leg_flags_sel),
        u16(A_time_subctr), _i16(image, A_time_left), _i16(image, A_hud_crash_timer),
        u16(A_timeout_gate) != 0)


def player_assets(image):
    """The static tables the player physics indexes, as a native PlayerAssets. Returns (assets,
    keepalive). steer_curve_tbl is CURSOR-ZERO: its row index ((skid + wheel_pos) << 3) goes negative
    while the buggy is being pushed off the right shoulder, so the window extends below the base."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    lean_anim = buf(A_lean_anim_tbl, LEAN_ANIM_TBL_BYTES)
    scroll_speed = buf(A_scroll_speed_tbl, SCROLL_SPEED_TBL_BYTES)
    speed_jitter = buf(A_speed_jitter_tbl, SPEED_JITTER_TBL_BYTES)
    steer_curve = buf(A_steer_curve_tbl - STEER_CURVE_ZERO_OFF, STEER_CURVE_WINDOW_BYTES)
    legflag = buf(A_legflag_tbl, LEGFLAG_TBL_BYTES)
    crash_anim = buf(A_crash_anim_tbl, CRASH_ANIM_TBL_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    assets = PlayerAssets(
        ctypes.cast(lean_anim, p), ctypes.cast(scroll_speed, p), ctypes.cast(speed_jitter, p),
        ctypes.cast(ctypes.byref(steer_curve, STEER_CURVE_ZERO_OFF), p), ctypes.cast(legflag, p),
        ctypes.cast(crash_anim, p))
    return assets, (lean_anim, scroll_speed, speed_jitter, steer_curve, legflag, crash_anim)


def road_ctrl(image):
    """The road control table (build_road_geometry's output) as a ctypes buffer — rm_player_update
    reads its edge-flag rows. Returns (ptr, keepalive)."""
    ctrl = (ctypes.c_uint8 * RM_CTRL_BYTES)(*image[A_road_curve_tbl:A_road_curve_tbl + RM_CTRL_BYTES])
    return ctypes.cast(ctrl, ctypes.POINTER(ctypes.c_uint8)), ctrl


def event_state(image):
    """The dynamic event-engine scalars (recreate's globals) as a native EventState."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    return EventState(image[A_course_flag_bit], image[A_dash_marker], image[A_dash_marker + 1],
                      u16(A_dash_marker + 2), u16(A_crash_bars), u16(A_crash_active),
                      u16(A_crash_lap), u16(A_gauge_blink), u16(A_gauge_blink_on),
                      u16(A_ckpt_scroll), u16(A_spin_state))


def _gobj_state(image):
    """The GobjPrefixState the event engine's bonus / flag-sequence counters live in."""
    def u16(addr):
        return (image[addr] << 8) | image[addr + 1]
    return GobjPrefixState(
        u16(A_marker_decay), _i16(image, A_marker_decay + 2), _i16(image, A_marker_decay + 4),
        u16(A_view_parity), u16(A_anim_counter), u16(A_anim_word), u16(A_bonus_timer),
        u16(A_dsp_color_scroll), u16(A_flag_seq_off), _i16(image, A_flag_seq_count))


def event_assets(image):
    """The const asset windows the event engine reads, as a native EventAssets. Returns (assets,
    keepalive). coll_mask points at the current leg's collision-flag long table (buf_a + leg*0x2000 +
    0x5d48); buf_a / dash_raw / font feed the leg-0 dashboard rebuild."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n).from_buffer_copy(image[addr:addr + n])

    buf_a = int.from_bytes(image[A_buf_a:A_buf_a + 4], "big")
    mem_base = int.from_bytes(image[A_mem_base:A_mem_base + 4], "big")
    leg = (image[A_leg_index] << 8) | image[A_leg_index + 1]
    mask_base = buf_a + leg * COURSE_LEG_STRIDE + COURSE_MASK_OFF

    fx_type = buf(A_fx_type_tbl, FX_TYPE_TBL_BYTES)
    evt_obj = buf(A_evt_obj_type_tbl, EVT_OBJ_TYPE_TBL_BYTES)
    deltas = buf(A_score_deltas, SCORE_DELTAS_BYTES)
    label = buf(A_score_label, SCORE_LABEL_BYTES)
    flag_seq = buf(A_flag_seq_table, FLAG_SEQ_TABLE_BYTES)
    probe = buf(A_probe_deltas, PROBE_DELTAS_BYTES)
    ckpt = buf(A_ckpt_anim_tbl, CKPT_ANIM_TBL_BYTES)
    coll = buf(mask_base, COLL_MASK_BYTES)
    buf_a_win = buf(buf_a, BUF_A_DASH_BYTES)
    dash_raw = buf(mem_base, DASH_RAW_BYTES)
    font = buf(A_font_glyphs, FONT_GLYPH_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    assets = EventAssets(
        ctypes.cast(fx_type, p), ctypes.cast(evt_obj, p), ctypes.cast(deltas, p),
        ctypes.cast(label, p), ctypes.cast(flag_seq, p), ctypes.cast(probe, p),
        ctypes.cast(ckpt, p), ctypes.cast(coll, p), ctypes.cast(buf_a_win, p),
        ctypes.cast(dash_raw, p), ctypes.cast(font, p))
    return assets, (fx_type, evt_obj, deltas, label, flag_seq, probe, ckpt, coll,
                    buf_a_win, dash_raw, font)


class EventBundle:
    """Everything a course-event step owns, built from one flat image and held together so the ctypes
    buffers outlive the RmEventCtx that points into them. The mutated structs/buffers are read back
    after the C runs to compare against recreate's in-image writes."""

    def __init__(self, image, inputs=0):
        def u16(addr):
            return (image[addr] << 8) | image[addr + 1]
        self.player = player_state(image, inputs)
        self.gobj = _gobj_state(image)
        self.ring = course_ring(image)
        self.pose = road_pose(image)
        self.pose.horizon_row = _i16(image, A_horizon_row)   # §H reads these; road_pose zeroes them
        self.pose.horizon_frac = _i16(image, A_horizon_frac)
        self.source, self._k_src = road_source(image)
        self.ctrl = (ctypes.c_uint8 * RM_CTRL_ALLOC_BYTES)()
        self.ctrl[:RM_CTRL_BYTES] = image[A_road_curve_tbl:A_road_curve_tbl + RM_CTRL_BYTES]
        self.scan = (ctypes.c_uint8 * RM_SCANLINE_BYTES)()
        self.ev = event_state(image)
        self.hud_text = (ctypes.c_uint8 * HUD_TEXT_BYTES).from_buffer_copy(
            image[A_hud_text:A_hud_text + HUD_TEXT_BYTES])
        self.buf_c = int.from_bytes(image[A_buf_c:A_buf_c + 4], "big")
        self.gfx = (ctypes.c_uint8 * GFX_EVENT_BYTES).from_buffer_copy(
            image[self.buf_c:self.buf_c + GFX_EVENT_BYTES])
        self.assets, self._k_assets = event_assets(image)
        self.leg = u16(A_leg_index)
        self.ctx = make_event_ctx(
            player=self.player, gobj=self.gobj, ring=self.ring, pose=self.pose, road_src=self.source,
            ctrl=self.ctrl, scanline=self.scan, ev=self.ev, hud_text=self.hud_text, gfx=self.gfx,
            assets=self.assets, leg=self.leg, game_over=u16(A_game_over_flag) != 0)


def event_ctx(image, inputs=0):
    """Build an EventBundle for `image` (see EventBundle)."""
    return EventBundle(image, inputs)
