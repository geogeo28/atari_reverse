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


def main():
    build = HERE / "build"
    build.mkdir(exist_ok=True)
    sb, nb = adapter.SCREEN_BASE, adapter.SCREEN_BYTES

    # A real mid-race frame on leg 1: geometry tables built, a plausible pose. Poke the HUD scalars,
    # and force a valid view bank (mid_race staging leaves view_flags at the section-12 trigger
    # value 0x10, which is not a real 0/2/4/6 view; build_road_geometry needs a real bank).
    img = equiv.road_background(leg=1, warmup=60)
    equiv._w16(img, adapter.A_view_flags, 0)
    for addr, val in CONTROLS.items():
        equiv._w16(img, addr, val & 0xffff)

    # Leg 1 opens with a long uniform-slope straight, so skip ahead (via the verified course advance)
    # to where the segment profile varies — the road then visibly bends/straightens as you drive from
    # the very first throttle instead of after several seconds of an unchanging opening.
    lib = equiv._lib()
    pose, cs = adapter.road_pose(img), adapter.course_state(img)
    stream, _k = adapter.course_stream(img)
    for _ in range(DEMO_START_SEGMENT):
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), stream)
    for i in range(13):
        equiv._w16(img, adapter.A_road_seg_data + i * 2, pose.seg_data[i] & 0xffff)
    equiv._w16(img, adapter.A_course_row_ctr, cs.row_ctr)
    equiv._w16(img, adapter.A_course_read_pos, cs.read_pos)

    img[sb:sb + nb] = bytes(nb)                   # blank screen: draw only remaster's own pipeline

    # golden = recreate's full ported pipeline on the same pose + blank screen (byte-for-byte target).
    ref = bytearray(img)
    equiv._run_pipeline(ref, ("g_build_road_geometry", "g_render_road",
                              "g_blit_road_scroll", "g_draw_hud"))
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
            "", "#endif /* RM_DEMO_FIXTURE_H */", ""]
    (build / "demo_fixture.h").write_text("\n".join(out))
    print(f"wrote {build/'demo_fixture.h'}, golden.bin, palette.bin "
          f"(leg={leg} curve={pose.curve} view_flags={pose.view_flags} seg0={pose.seg_data[0]} "
          f"row_ctr=0x{course.row_ctr:x} read_pos=0x{course.read_pos:x} buf_b=0x{buf_b:x})")


if __name__ == "__main__":
    main()
