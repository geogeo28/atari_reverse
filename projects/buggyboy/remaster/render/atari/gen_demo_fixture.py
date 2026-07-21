#!/usr/bin/env python3
"""gen_demo_fixture.py — bake the inputs for the interactive road + HUD demo.

The demo renders remaster's own pipeline on a real 68000: each frame it runs rm_build_road_geometry
(from the current pose), rm_render_road, then rm_draw_hud, and blits. Arrow keys nudge the pose
(curve / view bank / near-slope). This bakes, from one captured mid-race frame:

  build/demo_fixture.h  — the HUD asset arrays (shared with the HUD demo) + the render_road static
                          tables (param / edge / edge_const / texture) + the const geometry source
                          tables + the initial pose + the HudState scalars + the palette.
  build/golden.bin      — recreate's g_build_road_geometry + g_render_road + g_draw_hud on a BLANK
                          screen with the SAME pose: the byte-for-byte target for the demo's first
                          frame (before any key), so run_demo.py can prove the on-target pipeline.
  build/palette.bin     — the 16 ST palette words (index 0 black), for the PNG.

Only what remaster's C implements is drawn (road + HUD); there is no captured recreate game frame.
"""
import ctypes
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
sys.path.insert(0, str(REMASTER / "test"))

import adapter                                    # noqa: E402
import equiv                                      # noqa: E402
import gen_hud_fixture as hud                      # noqa: E402  reuse the HUD asset/define/palette baking

# A visually busy HUD over the road (same spirit as the HUD demo).
CONTROLS = {adapter.A_flag_seq_count: 3, adapter.A_crash_lap: 4,
            adapter.A_speed: 120, adapter.A_time_left: 45,
            adapter.A_crash_active: 0, adapter.A_hud_crash_timer: 0, adapter.A_dsp_toggle: 0}
DEMO_START_SEGMENT = 40                            # skip leg 1's uniform-slope opening straight

# draw_game_objects arena windows (see gen_demo_fixture's object baking). buf_a holds the per-type +
# special object records; buf_c is the sprite/graphics arena the object + buggy blits index (absolute
# offsets, so baked from 0); OBJ_LOW is the STATIC+bss table region draw_game_objects reads (jump
# table, colour/edge tables, object streams, sprite piece tables, ground tables, anim tables).
OBJ_BUF_A_BYTES = 0x3400
OBJ_BUF_C_BYTES = 0x3b000
OBJ_LOW_BASE = 0x13000
OBJ_LOW_END = 0x19100


def staged_image():
    """The demo's starting leg-1 image: geometry built, a valid view bank, HUD scalars poked, and the
    course advanced past leg 1's uniform-slope opening. Shared by the fixture baking and the perf
    bench so both measure the SAME frame. Screen is left as staged (caller blanks if needed)."""
    # mid_race staging leaves view_flags at the section-12 trigger value 0x10, which is not a real
    # 0/2/4/6 view; build_road_geometry needs a real bank.
    img = equiv.road_background(leg=1, warmup=60)
    equiv._w16(img, adapter.A_view_flags, 0)
    for addr, val in CONTROLS.items():
        equiv._w16(img, addr, val & 0xffff)

    # Skip ahead (via the verified course advance) to where the segment profile varies, so the road
    # visibly bends/straightens from the first throttle instead of after an unchanging opening.
    lib = equiv._lib()
    pose, cs = adapter.road_pose(img), adapter.course_state(img)
    stream, _k = adapter.course_stream(img)
    for _ in range(DEMO_START_SEGMENT):
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), stream)
    for i in range(13):
        equiv._w16(img, adapter.A_road_seg_data + i * 2, pose.seg_data[i] & 0xffff)
    equiv._w16(img, adapter.A_course_row_ctr, cs.row_ctr)
    equiv._w16(img, adapter.A_course_read_pos, cs.read_pos)
    return img


def main():
    build = HERE / "build"
    build.mkdir(exist_ok=True)
    sb, nb = adapter.SCREEN_BASE, adapter.SCREEN_BYTES

    img = staged_image()
    img[sb:sb + nb] = bytes(nb)                   # blank screen: draw only remaster's own pipeline

    # golden = recreate's full ported pipeline on the same pose + blank screen (byte-for-byte target).
    ref = bytearray(img)
    equiv._run_pipeline(ref, ("g_build_road_geometry", "g_render_road", "g_blit_road_scroll",
                              "g_draw_game_objects", "g_draw_hud"))
    (build / "golden.bin").write_bytes(bytes(ref[sb:sb + nb]))

    palette = hud.race_palette(img)
    (build / "palette.bin").write_bytes(palette)

    # ---- render_road static tables + the geometry const sources + the initial pose ----
    buf_b = int.from_bytes(img[adapter.A_buf_b:adapter.A_buf_b + 4], "big")
    buf_c = int.from_bytes(img[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
    buf_a = int.from_bytes(img[adapter.A_buf_a:adapter.A_buf_a + 4], "big")
    leg = (img[adapter.A_leg_index] << 8) | img[adapter.A_leg_index + 1]
    edge_sel = adapter._i16(img, adapter.A_road_edge_sel)
    play_off = buf_c + adapter._i16(img, adapter.A_screen_offset)
    course_base = buf_a + leg * adapter.COURSE_LEG_STRIDE + adapter.COURSE_STREAM_OFF

    def win(addr, n):
        return bytes(img[addr:addr + n])

    road_arrays = [
        ("fixture_road_param", win(adapter.A_road_param, adapter.ROAD_PARAM_BYTES)),
        ("fixture_road_edge",  win(adapter.A_road_edge_base + edge_sel - adapter.ROAD_EDGE_PAD,
                                   adapter.ROAD_EDGE_WINDOW_BYTES)),
        ("fixture_road_edge_const", win(adapter.A_road_edge_const, adapter.ROAD_CONST_BYTES)),
        ("fixture_road_tex",   win(buf_b - adapter.ROAD_TEX_PAD_LO, adapter.ROAD_TEX_WINDOW_BYTES)),
        ("fixture_road_persp_seg", win(adapter.A_persp_seg_tbl, adapter.ROAD_PERSP_SEG_BYTES)),
        ("fixture_road_width_src", win(adapter.A_road_width_src, adapter.ROAD_WIDTH_SRC_BYTES)),
        ("fixture_road_width_count", win(adapter.A_width_count_tbl, adapter.ROAD_WIDTH_COUNT_BYTES)),
        ("fixture_road_play", win(play_off, adapter.SCROLL_PLAY_BYTES)),   # buf_c + screen_offset window
        ("fixture_course_stream", win(course_base - adapter.COURSE_STREAM_PAD,
                                      adapter.COURSE_STREAM_BYTES)),        # records grow downward
    ]

    # ---- draw_game_objects arenas: the record arena (buf_a), the sprite/graphics arena (buf_c), and
    # the STATIC+bss table region the dispatcher / sub-draws read (jump table, colour/edge tables,
    # object streams, sprite piece tables, ground tables, anim tables). All indexed at their arena
    # base, so the demo points the object structs at these blobs with the same offsets recreate uses.
    obj_arrays = [
        ("fixture_buf_a", win(buf_a, OBJ_BUF_A_BYTES)),
        ("fixture_buf_c", win(buf_c, OBJ_BUF_C_BYTES)),
        ("fixture_obj_low", win(OBJ_LOW_BASE, OBJ_LOW_END - OBJ_LOW_BASE)),
    ]

    sp = adapter.sprite_state(img)
    gr = adapter.ground_state(img)
    obj_shade = adapter._i16(img, adapter.A_obj_shade)
    view_parity = (img[adapter.A_view_parity] << 8) | img[adapter.A_view_parity + 1]
    p24_flag = img[adapter.A_p24_flag]
    pfx = equiv._gobj_prefix_state(img)              # the prefix's initial state for this frame

    def low(addr):                                 # offset of a STATIC/bss table within fixture_obj_low
        assert OBJ_LOW_BASE <= addr < OBJ_LOW_END, f"{addr:#x} outside the obj-low blob"
        return addr - OBJ_LOW_BASE

    pose = adapter.road_pose(img)
    seg = ", ".join(str(pose.seg_data[i]) for i in range(13))
    scroll = adapter.scroll_state(img)
    course = adapter.course_state(img)

    st = adapter.hud_state(img)
    out = ["/* Generated by gen_demo_fixture.py — do not edit. Inputs for the interactive road + HUD",
           " * demo: HUD assets, render_road static tables, geometry const sources, the initial pose,",
           " * the HudState scalars, and the palette. */",
           "#ifndef RM_DEMO_FIXTURE_H", "#define RM_DEMO_FIXTURE_H", "#include <stdint.h>", ""]
    for name, data in hud.hud_asset_arrays(img):
        out.append(hud._c_array(name, data))
    for name, data in road_arrays:
        out.append(hud._c_array(name, data))
    for name, data in obj_arrays:
        out.append(hud._c_array(name, data))
    out.append(hud._c_array("fixture_palette", palette))
    out.append("")
    out += hud.hud_state_defines(st)
    out += ["",
            f"#define ROAD_EDGE_PAD        {adapter.ROAD_EDGE_PAD}",
            f"#define ROAD_TEX_PAD_LO      {adapter.ROAD_TEX_PAD_LO}",
            f"#define ROAD_CURVE_INIT      {pose.curve}",
            f"#define ROAD_VIEW_FLAGS_INIT {pose.view_flags}",
            "#define ROAD_SEG_DATA_INIT   { " + seg + " }",
            f"#define SCROLL_SPEED_INIT    {scroll.scroll_speed}",
            f"#define HSCROLL_POS_INIT     {scroll.hscroll_pos}",
            f"#define COURSE_STREAM_PAD    {adapter.COURSE_STREAM_PAD}",
            f"#define COURSE_ROW_CTR_INIT  {course.row_ctr}",
            f"#define COURSE_READ_POS_INIT {course.read_pos}",
            ""]

    # ---- draw_game_objects: the table offsets within fixture_obj_low + the object scalar inits.
    out += [
        f"#define OBJ_LOW_JUMPTABLE     {low(adapter.A_obj_type_jumptable)}",
        f"#define OBJ_LOW_COLOR_PAIRS   {low(adapter.A_color_pairs)}",
        f"#define OBJ_LOW_VIEW_XFORM    {low(adapter.A_obj_view_xform)}",
        f"#define OBJ_LOW_OBJSH2P_TBL   {low(adapter.A_objsh2p_tbl)}",
        f"#define OBJ_LOW_XOFF_TBL      {low(adapter.A_obj_xoff_tbl)}",
        f"#define OBJ_LOW_LIST_BASE     {low(adapter.A_obj_list_base)}",
        f"#define OBJ_LOW_FLAGS         {low(adapter.A_obj_flags)}",
        f"#define OBJ_LOW_SPRITE_DISP   {low(adapter.A_obj_sprite_disp)}",
        f"#define OBJ_LOW_SPRITE_FLAGS  {low(adapter.A_obj_sprite_flags)}",
        f"#define OBJ_LOW_SPRITE_LIST_BASE {low(adapter.A_sprite_list_base)}",
        f"#define OBJ_LOW_BLIT_MASK_L   {low(adapter.A_blit_mask_l)}",
        f"#define OBJ_LOW_BLIT_MASK_R   {low(adapter.A_blit_mask_r)}",
        f"#define OBJ_LOW_GROUND_COL    {low(adapter.A_ground_col_tbl)}",
        f"#define OBJ_LOW_GROUND_BAND   {low(adapter.A_ground_band_records)}",
        f"#define OBJ_LOW_GROUND_SCAN   {low(adapter.A_ground_scan_tbl)}",
        f"#define OBJ_LOW_FG_ANIM_TBL   {low(adapter.A_fg_anim_tbl)}",
        f"#define OBJ_LOW_BODY_TBL      {low(adapter.A_body_tbl)}",
        f"#define OBJ_LOW_HI_TBL        {low(adapter.A_hi_tbl)}",
        f"#define OBJ_LOW_LO_PIECE_TBL  {low(adapter.A_lo_piece_tbl)}",
        f"#define OBJ_LOW_LO_PIECE_IDX  {low(adapter.A_lo_piece_idx)}",
        f"#define OBJ_LOW_ANIM_WORD_TBL {low(adapter.A_anim_word_tbl)}",
        f"#define OBJ_LOW_ANIM_COLORIDX {low(adapter.A_anim_coloridx_tbl)}",
        "",
        f"#define OBJ_SHADE_INIT        {obj_shade}",
        f"#define OBJ_VIEW_PARITY_INIT  {view_parity}",
        f"#define OBJ_P24_FLAG_INIT     {p24_flag}",
        f"#define OBJ_GROUND_VIEW_INIT  {gr.view}",
        "",
        f"#define PFX_MARKER_ACTIVE_INIT {pfx.marker_active}",
        f"#define PFX_MARKER_OFF_INIT    {pfx.marker_off}",
        f"#define PFX_MARKER_CD_INIT     {pfx.marker_countdown}",
        f"#define PFX_ANIM_COUNTER_INIT  {pfx.anim_counter}",
        f"#define PFX_ANIM_WORD_INIT     {pfx.anim_word}",
        f"#define PFX_BONUS_TIMER_INIT   {pfx.bonus_timer}",
        f"#define PFX_DSP_SCROLL_INIT    {pfx.dsp_color_scroll}",
        f"#define PFX_FLAG_SEQ_OFF_INIT  {pfx.flag_seq_off}",
        f"#define PFX_FLAG_SEQ_CNT_INIT  {pfx.flag_seq_count}",
        "",
        f"#define SP_LEAN_INIT          {sp.lean}",
        f"#define SP_PITCH_INIT         {sp.pitch}",
        f"#define SP_SKID_INIT          {sp.skid}",
        f"#define SP_CRASH_DISP_INIT    {sp.crash_disp}",
        f"#define SP_WHEEL_POS_INIT     {sp.wheel_pos}",
        f"#define SP_SPIN_STATE_INIT    {sp.spin_state}",
        f"#define SP_SPRITE_SUPPRESS_INIT {sp.sprite_suppress}",
        f"#define SP_FG_GATE_INIT       {sp.fg_gate}",
        f"#define SP_ANIM_FRAME_INIT    {sp.anim_frame}",
        f"#define SP_SPIN_RESET_INIT    {sp.spin_reset}",
        f"#define SP_BUGGY_DRAW_FLAG_INIT {sp.buggy_draw_flag}",
        f"#define SP_BUGGY_GATE_INIT    {sp.buggy_gate}",
        f"#define SP_COLLISION_LOCK_INIT {sp.collision_lock}",
        f"#define SP_SPEED_RAW_INIT     {sp.speed_raw}",
        f"#define SP_LEAN_ACCUM_INIT    {sp.lean_accum}",
        f"#define SP_LEAN_FRAME_INIT    {sp.lean_frame}",
        "", "#endif /* RM_DEMO_FIXTURE_H */", ""]
    (build / "demo_fixture.h").write_text("\n".join(out))
    print(f"wrote {build/'demo_fixture.h'}, golden.bin, palette.bin "
          f"(leg={leg} curve={pose.curve} view_flags={pose.view_flags} seg0={pose.seg_data[0]} "
          f"row_ctr=0x{course.row_ctr:x} read_pos=0x{course.read_pos:x} buf_b=0x{buf_b:x})")


if __name__ == "__main__":
    main()
