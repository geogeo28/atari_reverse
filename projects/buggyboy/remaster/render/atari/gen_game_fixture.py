#!/usr/bin/env python3
"""gen_game_fixture.py — bake the on-target BuggyBoy game's non-asset-file inputs into build/game_fixture.h.

The game (BUGGYBOY.PRG) renders remaster's own pipeline on a real 68000 and loads COURSES.DAT /
GRAPHICS.GRA off disk at boot, so only what is NOT file content is baked here: the original program's
own data-segment tables (fonts, colour pairs, road param/edge tables, the geometry const sources, the
STATIC+bss blob the object dispatcher reads, the between-legs flow's program-data arrays), the palette,
and the offsets at which the arena-resident assets live. The per-leg leg-start STATE is produced
natively by rm_init_leg at boot, not baked here (a bench-only static HudState block is the one residual).

With GEN_GOLDEN=1 (set by run_golden.py) it ALSO writes the golden-harness reference for the leg-0 boot
frame: build/golden.bin — recreate's full five-stage pipeline (g_build_road_geometry, g_render_road,
g_blit_road_scroll, g_draw_game_objects, g_draw_hud) on a blank screen — and build/palette.bin for the
PNG. Only run_golden.py consumes those, so the shipping + bench builds skip that heavy render by default.
"""
import ctypes
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
sys.path.insert(0, str(REMASTER / "test"))

import adapter                                    # noqa: E402
import assets_load as al                          # noqa: E402  remaster's own COURSES/GRAPHICS loader
import equiv                                      # noqa: E402
import render_screen as R                         # noqa: E402  MEM_BASE (where the arena sits)
import gen_hud_fixture as hud                      # noqa: E402  reuse the HUD asset/define/palette baking

# A visually busy HUD over the road (same spirit as the HUD demo).
GAME_LEG = 0                                       # the game starts where the player does: leg 0...
GAME_START_SEGMENT = 0                             # ...at its first segment, with nothing skipped

# buf_a's record region, copied into game RAM because the prefix mutates it (anim-word mirrors).
# OBJ_LOW is the STATIC+bss table region draw_game_objects reads (jump table, colour/edge tables,
# object streams, sprite piece tables, ground tables, anim tables) — program data, not file content,
# so it stays baked. Everything that IS file content now comes from the arena the game loads itself.
# The window must cover the dispatcher's whole per-type record table: OBJ_TYPE_BASE (0x8a0) +
# 64 types (the 0x3f flag mask + 1) * OBJ_TYPE_STRIDE (0xd0) = 0x3ca0. It was 0x3400, sized by
# what the old mid-race build happened to reach — the leg-0 start gate's codes (0x3a/0x3b) index
# past that, so the game read zeros beyond its copy and silently dropped the whole gate (the
# frame-0 golden DIFF). Pinned against src/object_list.c's constants by test_game_fixture.
OBJ_BUF_A_BYTES = 0x3ca0
OBJ_LOW_BASE = 0x13000
OBJ_LOW_END = 0x19100


def staged_image():
    """The game's starting image: the START OF LEG 0, exactly as the player meets it — the oracle's
    init_leg with no warmup frames and no course skipping, so the buggy is stationary on the grid with
    the leg's own clock, and driving forward covers the leg from its first segment.

    (It used to start mid-race — leg 1, 60 warmup frames, 40 segments in — which was fine for
    validating the renderer against a busy frame but meant you could never drive a leg from the
    beginning. Nothing here needs the old staging fixups: those cleared artefacts the warmup drive
    left behind, and a leg start has none of them.)

    The asset arena is replaced by a freshly-loaded one (see the note at the end — the game loads its
    assets off disk, so the reference must too). Shared by the fixture baking and the perf bench so
    both measure the SAME frame. Screen is left as staged (caller blanks if needed)."""
    img = equiv.leg_start_background(GAME_LEG)

    # Kept as a loop over the verified course advance so that raising GAME_START_SEGMENT is all it
    # takes to start further into the leg again (the perf bench wants a busier frame than segment 0).
    lib = equiv._lib()
    pose, cs = adapter.road_pose(img), adapter.course_state(img)
    ring = adapter.course_ring(img)
    stream, _k = adapter.course_stream(img)
    for _ in range(GAME_START_SEGMENT):
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), ctypes.byref(ring), stream)
    for i in range(13):
        equiv._w16(img, adapter.A_road_seg_data + i * 2, pose.seg_data[i] & 0xffff)
    equiv._w16(img, adapter.A_course_row_ctr, cs.row_ctr)
    equiv._w16(img, adapter.A_course_read_pos, cs.read_pos)
    # The ring is state the advance owns, so write it back into the image too — otherwise the golden
    # frame would be rendered from a ring GAME_START_SEGMENT steps behind the pose.
    for band in range(adapter.RM_RING_ROWS):
        row = adapter.A_ring_base + band * adapter.RING_ROW_BYTES
        for slot in range(adapter.RM_RING_SLOTS):
            equiv._w16(img, row + slot * 2, ring.row[band].slot[slot])
        equiv._w16(img, row + adapter.RM_RING_SLOTS * 2, ring.row[band].marker)

    # The game loads COURSES.DAT + GRAPHICS.GRA off disk at boot, so the reference must render from
    # a freshly-loaded arena too — otherwise golden carries state the staged run wrote into its own
    # assets and no on-target frame could ever match it. Of the arena's 388616 bytes exactly 347
    # differ after 60 staged frames, all in the graphics region, and exactly one of them (the
    # dashboard graphic's 4th byte, which the running game clears a bit in) reaches the framebuffer.
    # That bit returns on its own once the systems that write it are ported.
    img[R.MEM_BASE:R.MEM_BASE + al.RM_ARENA_BYTES] = al.fresh_arena()
    return img


def main():
    build = HERE / "build"
    build.mkdir(exist_ok=True)
    sb, nb = adapter.SCREEN_BASE, adapter.SCREEN_BYTES

    img = staged_image()
    img[sb:sb + nb] = bytes(nb)                   # blank screen: draw only remaster's own pipeline

    palette = hud.race_palette(img)               # needed unconditionally for fixture_palette below

    # The golden-harness reference (golden.bin + palette.bin) is opt-in — only run_golden.py compares
    # against it, so a plain shipping/bench build skips this heavy full-pipeline render (GEN_GOLDEN=1).
    gen_golden = bool(os.environ.get("GEN_GOLDEN"))
    if gen_golden:
        # golden = recreate's full ported pipeline on the same pose + blank screen (byte-for-byte target).
        ref = bytearray(img)
        equiv._run_pipeline(ref, ("g_build_road_geometry", "g_render_road", "g_blit_road_scroll",
                                  "g_draw_game_objects", "g_draw_hud"))
        (build / "golden.bin").write_bytes(bytes(ref[sb:sb + nb]))
        (build / "palette.bin").write_bytes(palette)

    # ---- render_road static tables + the geometry const sources + the initial pose ----
    buf_c = int.from_bytes(img[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
    buf_a = int.from_bytes(img[adapter.A_buf_a:adapter.A_buf_a + 4], "big")
    leg = (img[adapter.A_leg_index] << 8) | img[adapter.A_leg_index + 1]
    play_off = buf_c + adapter._i16(img, adapter.A_screen_offset)
    course_base = buf_a + leg * adapter.COURSE_LEG_STRIDE + adapter.COURSE_STREAM_OFF

    def win(addr, n):
        return bytes(img[addr:addr + n])

    # Only the original PROGRAM's own data-segment tables are baked. The road texture, the scroll
    # playfield, the course stream, the object record arena and the sprite/graphics arena are all
    # data-file content, so the game reads them out of the arena it loads at boot (see assets.h).
    road_arrays = [
        ("fixture_road_param", win(adapter.A_road_param, adapter.ROAD_PARAM_BYTES)),
        # every edge bank, not just the staged one: the drive re-picks it from view_flags each frame
        ("fixture_road_edge",  win(adapter.A_road_edge_base - adapter.ROAD_EDGE_PAD,
                                   adapter.ROAD_EDGE_ALL_BANKS_BYTES)),
        ("fixture_road_edge_const", win(adapter.A_road_edge_const, adapter.ROAD_CONST_BYTES)),
        ("fixture_road_persp_seg", win(adapter.A_persp_seg_tbl, adapter.ROAD_PERSP_SEG_BYTES)),
        ("fixture_road_width_count", win(adapter.A_width_count_tbl, adapter.ROAD_WIDTH_COUNT_BYTES)),
    ]

    # The STATIC+bss table region the dispatcher / sub-draws read (jump table, colour/edge tables,
    # object streams, sprite piece tables, ground tables, anim tables), indexed at its base so the
    # the game points the object structs at it with the same offsets recreate uses.
    obj_arrays = [
        ("fixture_obj_low", win(OBJ_LOW_BASE, OBJ_LOW_END - OBJ_LOW_BASE)),
        # The HUD bonus-time strings ("/2000/" ...) rm_init_leg's phase 4 copies into the HUD-text
        # region — program data-segment content (not asset-file), so it stays baked.
        ("fixture_legtime", win(adapter.A_legtime_src, adapter.IL_LEGTIME_BYTES)),
    ]

    # ---- between-legs flow (slice C): the two baked program-data arrays the shell needs that do NOT
    # live inside the obj-low blob. The intermission_poll control table sits inline in the program CODE
    # (below OBJ_LOW_BASE), and the default hi-score table is init_scoretable's deterministic output —
    # baked as a SEED the shell copies into RAM at boot (rm_update_highscore mutates it), exactly as
    # fixture_hud_text seeds hud_text_ram. Everything else the flow draws is either arena-resident (poll
    # source graphic, num sprites, buf_a strings) or already inside the obj-low blob (layout tables,
    # header/credit strings, per-row palette bytes, the phase palettes) — offsets below.
    hs_seed = bytearray(img)                            # init_scoretable writes only A_highscore_table
    equiv._run_pipeline(hs_seed, ("g_init_scoretable",))
    flow_arrays = [
        ("fixture_poll_blits", win(adapter.POLL_BLITS_OFF, adapter.FLOW_POLL_BLITS_BYTES)),
        ("fixture_highscore",  bytes(hs_seed[adapter.A_highscore_table:
                                             adapter.A_highscore_table + adapter.FLOW_HIGHSCORE_BYTES])),
        # The name-entry score-line region (score-line string + the "TIME nn" digits rm_hiscore_countdown
        # writes), seeded into RAM at boot like fixture_hud_text — it sits in the gap between hud_text and
        # the hi-score table, so it is not covered by either of those RAM windows.
        ("fixture_score_line", win(adapter.A_score_line, adapter.FLOW_SCORE_LINE_BYTES)),
    ]

    # Where each arena-resident asset sits, so game_main.c can point at the loaded arena. All are
    # offsets from a named region base in include/assets.h, never absolute addresses.
    course_mask_off = leg * adapter.COURSE_LEG_STRIDE + adapter.COURSE_MASK_OFF
    arena_defines = [
        f"#define ARENA_BUF_A_BYTES     {OBJ_BUF_A_BYTES}",         # mutable copy the prefix writes
        f"#define ARENA_SCROLL_PLAY_OFF {play_off - buf_c}",        # gfx + this: the scroll playfield
        f"#define ARENA_COURSE_STREAM_OFF {course_base - buf_a}",   # tables + this: the leg's records
        f"#define ARENA_COURSE_MASK_OFF {course_mask_off}",         # tables + this: per-leg collision-flag longs
        f"#define ARENA_DASH_SRC_OFF    {adapter.DASH_SRC_OFF}",    # gfx + this: dashboard graphic
        f"#define ARENA_NUM_SPRITES_OFF {adapter.NUM_GLYPH_BUF_OFF}",  # gfx + this: digit sprites
        f"#define GAME_LEG_INDEX        {leg}",                     # the fixture/bench leg (== the golden-harness boot leg)
        # The game shell (slice C) can start ANY leg the leg-select picks, so it computes the per-leg
        # stream / collision-mask pointers at runtime from these bases (the per-leg ARENA_COURSE_*_OFF
        # above stay for bench_main.c, which only ever stages leg GAME_LEG_INDEX).
        f"#define COURSE_LEG_STRIDE     {adapter.COURSE_LEG_STRIDE}",   # tables: per-leg stride in buf_a
        f"#define ARENA_COURSE_STREAM_BASE {adapter.COURSE_STREAM_OFF}",  # tables + leg*STRIDE + this
        f"#define ARENA_COURSE_MASK_BASE   {adapter.COURSE_MASK_OFF}",    # tables + leg*STRIDE + this
        # The between-legs flow's arena-resident asset offsets (poll source graphic + the two buf_a
        # string blocks). All are offsets from a named region base, never absolute addresses.
        f"#define ARENA_POLL_SRC_OFF    {adapter.POLL_SRC_OFF}",    # gfx + this: intermission_poll source
        f"#define ARENA_LEG_NAMES_OFF   {adapter.FLOW_LEG_STR_OFF}",  # tables + this: INT leg-times / results digits
        f"#define ARENA_ROW_NAMES_OFF   {adapter.FLOW_ROW_STR_OFF}",  # tables + this: results row-2 label strings
    ]

    def low(addr):                                 # offset of a STATIC/bss table within fixture_obj_low
        assert OBJ_LOW_BASE <= addr < OBJ_LOW_END, f"{addr:#x} outside the obj-low blob"
        return addr - OBJ_LOW_BASE

    # The between-legs flow's obj-low-resident program data: the intermission / results layout tables,
    # the header / credit strings, the per-row palette-byte cursor, and the four phase palettes (all
    # inside [OBJ_LOW_BASE, OBJ_LOW_END), so the shell points at fixture_obj_low + these). The palettes
    # are an off-image seam (the byte-compare is palette-agnostic); the addresses are recreate's addrs.h.
    A_INT_PAL_A, A_LEG_SELECT_PAL = 0x17fe2, 0x17f62   # INT_PAL_A ; INT_PAL_D == leg-select palette
    # The leg-start "get ready" flash source: the four animation tables and the palette it seeds from
    # (addrs.h A_leg_flash_tbl_a..d @0x17f12/0x17f1a/0x17f2a/0x17f3a, A_leg_start_pal @0x17f82).
    A_LEG_FLASH_A, A_LEG_FLASH_B, A_LEG_FLASH_C, A_LEG_FLASH_D = 0x17f12, 0x17f1a, 0x17f2a, 0x17f3a
    A_LEG_START_PAL = 0x17f82
    flow_defines = [
        f"#define OBJ_LOW_INT_HEADER    {low(adapter.A_int_header)}",   # fade_step copyright header string
        f"#define OBJ_LOW_INT_SEC1      {low(adapter.A_int_tbl1)}",     # draw_intermission section-1 layout
        f"#define OBJ_LOW_INT_SEC3      {low(adapter.A_int_tbl3)}",     # draw_intermission section-3 layout
        f"#define OBJ_LOW_INT_CREDITS   {low(adapter.A_int_credits)}",  # section-3 credit strings
        f"#define OBJ_LOW_LEG_TITLE     {low(adapter.A_leg_title)}",    # results row-1 concatenated labels
        f"#define OBJ_LOW_PANEL5_STR    {low(adapter.A_panel5_str)}",   # leg-name menu: 5 concatenated labels
        f"#define OBJ_LOW_LEG_ROW_PAL   {low(adapter.A_leg_row_palette)}",  # results row-2 palette cursor
        f"#define OBJ_LOW_PAL_INT_A     {low(A_INT_PAL_A)}",            # intermission prologue palette
        f"#define OBJ_LOW_PAL_LEG_SELECT {low(A_LEG_SELECT_PAL)}",      # leg-select / results-carousel palette
        # the race-end / name-entry results screen (slice F): title + palettes + missed-block strings, the
        # results-screen palette (off-image seam), and the name-entry colour-3 flash table.
        f"#define OBJ_LOW_RS_TITLE      {low(adapter.A_results_title)}",      # results title + row-1 labels
        f"#define OBJ_LOW_RS_PAL_A      {low(adapter.A_results_palette_a)}",  # results row-1 palette cursor
        f"#define OBJ_LOW_RS_PAL_B      {low(adapter.A_results_palette_b)}",  # results row-2 palette cursor
        f"#define OBJ_LOW_RS_MODE_STR   {low(adapter.A_results_mode_str)}",   # "missed the table" label block
        f"#define OBJ_LOW_PAL_RESULTS   {low(adapter.A_results_screen_pal)}", # results-screen palette (off-image seam)
        f"#define OBJ_LOW_NAME_ANIM_TBL {low(adapter.A_name_anim_tbl)}",      # name-entry colour-3 flash table
        f"#define OBJ_LOW_LEG_FLASH_A   {low(A_LEG_FLASH_A)}",          # leg-start flash tables (off-image palette)
        f"#define OBJ_LOW_LEG_FLASH_B   {low(A_LEG_FLASH_B)}",
        f"#define OBJ_LOW_LEG_FLASH_C   {low(A_LEG_FLASH_C)}",
        f"#define OBJ_LOW_LEG_FLASH_D   {low(A_LEG_FLASH_D)}",
        f"#define OBJ_LOW_LEG_START_PAL {low(A_LEG_START_PAL)}",        # baked seed for the flashed palette
    ]

    # pose / course are read only for the informational print below; rm_init_leg produces the game's
    # actual leg-start state at boot, so no per-leg scalar is baked here any more.
    pose = adapter.road_pose(img)
    course = adapter.course_state(img)
    # The leg-start HudState scalars. The game no longer uses these (its HUD is a per-frame VIEW that
    # apply_player derives), but the perf bench (render/atari/bench_main.c) still stages a static
    # HudState from them: bench_draw_hud must render the SAME leg-start HUD its recon oracle draws, so
    # the rm/rec cycle ratio reflects code, not HUD content. Kept as a bench-only residual.
    st = adapter.hud_state(img)

    out = ["/* Generated by gen_game_fixture.py — do not edit. The on-target BuggyBoy game's inputs",
           " * that are NOT asset-file content: the original program's own data-segment tables,",
           " * the geometry const sources, the render_road static tables, the palette, the program-data",
           " * bonus-time strings, and the offsets at which the arena-resident assets live. The per-leg",
           " * leg-start STATE is produced natively by rm_init_leg (see game_main.c), not baked here.",
           " * Everything from COURSES.DAT and GRAPHICS.GRA the game loads itself at boot (assets.h). */",
           "#ifndef RM_GAME_FIXTURE_H", "#define RM_GAME_FIXTURE_H", "#include <stdint.h>", ""]
    for name, data in hud.hud_asset_arrays(img, from_arena=True):
        out.append(hud._c_array(name, data))
    for name, data in road_arrays:
        out.append(hud._c_array(name, data))
    for name, data in obj_arrays:
        out.append(hud._c_array(name, data))
    for name, data in flow_arrays:
        out.append(hud._c_array(name, data))
    out.append(hud._c_array("fixture_palette", palette))
    out.append("")
    # The per-leg leg-start STATE is no longer baked: rm_init_leg (src/gameplay.c) produces it at game
    # boot and on every restart, seeded from the loaded arena — the pose/scroll/course scalars, the
    # ring, the physics/event/prefix/sprite state, obj_shade and the scroll offset (see game_main.c
    # start_leg). Only ROAD_EDGE_PAD (a window layout constant) and the arena-resident asset OFFSETS
    # stay here. Everything that WAS a `*_INIT` snapshot of the oracle's init_leg output is gone.
    out += ["",
            f"#define CIDX_ZERO_OFF        {adapter.CIDX_ZERO_OFF}",   # color_bar_cidx window zero offset
            f"#define ROAD_EDGE_PAD        {adapter.ROAD_EDGE_PAD}",
            ""]
    # The leg-start HudState scalars (HUD_*). BENCH-ONLY: render/atari/bench_main.c stages a static
    # HudState from these so bench_draw_hud renders the same leg-start HUD its recon oracle does (see
    # the `st` note above). The game does not use them — its HUD is derived by apply_player.
    out += hud.hud_state_defines(st)
    out += [""] + arena_defines + [""] + flow_defines + [""]

    # ---- draw_game_objects: the table OFFSETS within fixture_obj_low (program-data table locations,
    # not baked state). The per-leg object / prefix / sprite / player / event START scalars that used
    # to live here are gone — rm_init_leg produces them at boot + restart (see the note above).
    out += [
        f"#define OBJ_LOW_JUMPTABLE     {low(adapter.A_obj_type_jumptable)}",
        f"#define OBJ_LOW_COLOR_PAIRS   {low(adapter.A_color_pairs)}",
        f"#define OBJ_LOW_VIEW_XFORM    {low(adapter.A_obj_view_xform)}",
        f"#define OBJ_LOW_OBJSH2P_TBL   {low(adapter.A_objsh2p_tbl)}",
        f"#define OBJ_LOW_XOFF_TBL      {low(adapter.A_obj_xoff_tbl)}",
        f"#define OBJ_LOW_LIST_BASE     {low(adapter.A_obj_list_base)}",
        f"#define OBJ_LOW_SPRITE_DISP   {low(adapter.A_obj_sprite_disp)}",
        f"#define OBJ_LOW_BLIT_MASK_L   {low(adapter.A_blit_mask_l)}",
        f"#define OBJ_LOW_BLIT_MASK_R   {low(adapter.A_blit_mask_r)}",
        f"#define OBJ_LOW_GROUND_COL    {low(adapter.A_ground_col_tbl)}",
        f"#define OBJ_LOW_GROUND_BAND   {low(adapter.A_ground_band_records)}",
        f"#define OBJ_LOW_FG_ANIM_TBL   {low(adapter.A_fg_anim_tbl)}",
        f"#define OBJ_LOW_BODY_TBL      {low(adapter.A_body_tbl)}",
        f"#define OBJ_LOW_HI_TBL        {low(adapter.A_hi_tbl)}",
        f"#define OBJ_LOW_LO_PIECE_TBL  {low(adapter.A_lo_piece_tbl)}",
        f"#define OBJ_LOW_LO_PIECE_IDX  {low(adapter.A_lo_piece_idx)}",
        f"#define OBJ_LOW_ANIM_WORD_TBL {low(adapter.A_anim_word_tbl)}",
        f"#define OBJ_LOW_ANIM_COLORIDX {low(adapter.A_anim_coloridx_tbl)}",
        # ---- course-event engine tables (all program data-segment content, inside the obj-low blob).
        f"#define OBJ_LOW_FX_TYPE_TBL   {low(adapter.A_fx_type_tbl)}",
        f"#define OBJ_LOW_EVT_OBJ_TYPE  {low(adapter.A_evt_obj_type_tbl)}",
        f"#define OBJ_LOW_SCORE_DELTAS  {low(adapter.A_score_deltas)}",
        f"#define OBJ_LOW_SCORE_LABEL   {low(adapter.A_score_label)}",
        f"#define OBJ_LOW_FLAG_SEQ_TBL  {low(adapter.A_flag_seq_table)}",
        f"#define OBJ_LOW_PROBE_DELTAS  {low(adapter.A_probe_deltas)}",
        f"#define OBJ_LOW_CKPT_ANIM_TBL {low(adapter.A_ckpt_anim_tbl)}",
        "",
        # ---- player physics const tables (all inside the obj-low blob; program-data locations).
        f"#define OBJ_LOW_LEAN_ANIM_TBL {low(adapter.A_lean_anim_tbl)}",
        f"#define OBJ_LOW_SCROLL_SPEED_TBL {low(adapter.A_scroll_speed_tbl)}",
        f"#define OBJ_LOW_SPEED_JITTER_TBL {low(adapter.A_speed_jitter_tbl)}",
        f"#define OBJ_LOW_STEER_CURVE_TBL {low(adapter.A_steer_curve_tbl)}",
        f"#define OBJ_LOW_LEGFLAG_TBL   {low(adapter.A_legflag_tbl)}",
        f"#define OBJ_LOW_CRASH_ANIM_TBL {low(adapter.A_crash_anim_tbl)}",
        "", "#endif /* RM_GAME_FIXTURE_H */", ""]
    (build / "game_fixture.h").write_text("\n".join(out))
    also = ", golden.bin, palette.bin" if gen_golden else ""
    print(f"wrote {build/'game_fixture.h'}{also} "
          f"(leg={leg} curve={pose.curve} view_flags={pose.view_flags} seg0={pose.seg_data[0]} "
          f"row_ctr=0x{course.row_ctr:x} read_pos=0x{course.read_pos:x})")


if __name__ == "__main__":
    main()
