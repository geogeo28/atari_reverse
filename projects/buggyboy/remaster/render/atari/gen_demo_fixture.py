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
import assets_load as al                          # noqa: E402  remaster's own COURSES/GRAPHICS loader
import equiv                                      # noqa: E402
import render_screen as R                         # noqa: E402  MEM_BASE (where the arena sits)
import gen_hud_fixture as hud                      # noqa: E402  reuse the HUD asset/define/palette baking

# A visually busy HUD over the road (same spirit as the HUD demo).
DEMO_LEG = 0                                       # the demo starts where the player does: leg 0...
DEMO_START_SEGMENT = 0                             # ...at its first segment, with nothing skipped

# buf_a's record region, copied into demo RAM because the prefix mutates it (anim-word mirrors).
# OBJ_LOW is the STATIC+bss table region draw_game_objects reads (jump table, colour/edge tables,
# object streams, sprite piece tables, ground tables, anim tables) — program data, not file content,
# so it stays baked. Everything that IS file content now comes from the arena the demo loads itself.
OBJ_BUF_A_BYTES = 0x3400
OBJ_LOW_BASE = 0x13000
OBJ_LOW_END = 0x19100


def _c_ring(ring):
    """The course ring as a brace initializer for game.h's CourseRing — native words, not ST bytes,
    because the ring is native game state. Emitted as a #define rather than a typed object so the
    fixture header stays self-contained (stdint only) and each consumer names the type itself."""
    lines = ["#define COURSE_RING_INIT { {  \\"]
    for band in range(adapter.RM_RING_ROWS):
        row = ring.row[band]
        slots = ", ".join(f"0x{row.slot[s]:04x}" for s in range(adapter.RM_RING_SLOTS))
        lines.append(f"    {{ {{{slots}}}, 0x{row.marker:04x} }},  \\")
    lines.append("} }")
    return "\n".join(lines)


def staged_image():
    """The demo's starting image: the START OF LEG 0, exactly as the player meets it — the oracle's
    init_leg with no warmup frames and no course skipping, so the buggy is stationary on the grid with
    the leg's own clock, and driving forward covers the leg from its first segment.

    (It used to start mid-race — leg 1, 60 warmup frames, 40 segments in — which was fine for
    validating the renderer against a busy frame but meant you could never drive a leg from the
    beginning. Nothing here needs the old staging fixups: those cleared artefacts the warmup drive
    left behind, and a leg start has none of them.)

    The asset arena is replaced by a freshly-loaded one (see the note at the end — the demo loads its
    assets off disk, so the reference must too). Shared by the fixture baking and the perf bench so
    both measure the SAME frame. Screen is left as staged (caller blanks if needed)."""
    img = equiv.leg_start_background(DEMO_LEG)

    # Kept as a loop over the verified course advance so that raising DEMO_START_SEGMENT is all it
    # takes to start further into the leg again (the perf bench wants a busier frame than segment 0).
    lib = equiv._lib()
    pose, cs = adapter.road_pose(img), adapter.course_state(img)
    ring = adapter.course_ring(img)
    stream, _k = adapter.course_stream(img)
    for _ in range(DEMO_START_SEGMENT):
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), ctypes.byref(ring), stream)
    for i in range(13):
        equiv._w16(img, adapter.A_road_seg_data + i * 2, pose.seg_data[i] & 0xffff)
    equiv._w16(img, adapter.A_course_row_ctr, cs.row_ctr)
    equiv._w16(img, adapter.A_course_read_pos, cs.read_pos)
    # The ring is state the advance owns, so write it back into the image too — otherwise the golden
    # frame would be rendered from a ring DEMO_START_SEGMENT steps behind the pose.
    for band in range(adapter.RM_RING_ROWS):
        row = adapter.A_ring_base + band * adapter.RING_ROW_BYTES
        for slot in range(adapter.RM_RING_SLOTS):
            equiv._w16(img, row + slot * 2, ring.row[band].slot[slot])
        equiv._w16(img, row + adapter.RM_RING_SLOTS * 2, ring.row[band].marker)

    # The demo loads COURSES.DAT + GRAPHICS.GRA off disk at boot, so the reference must render from
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

    # golden = recreate's full ported pipeline on the same pose + blank screen (byte-for-byte target).
    ref = bytearray(img)
    equiv._run_pipeline(ref, ("g_build_road_geometry", "g_render_road", "g_blit_road_scroll",
                              "g_draw_game_objects", "g_draw_hud"))
    (build / "golden.bin").write_bytes(bytes(ref[sb:sb + nb]))

    palette = hud.race_palette(img)
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
    # data-file content, so the demo reads them out of the arena it loads at boot (see assets.h).
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
    # demo points the object structs at it with the same offsets recreate uses.
    obj_arrays = [
        ("fixture_obj_low", win(OBJ_LOW_BASE, OBJ_LOW_END - OBJ_LOW_BASE)),
    ]

    # Where each arena-resident asset sits, so demo_main.c can point at the loaded arena. All are
    # offsets from a named region base in include/assets.h, never absolute addresses.
    arena_defines = [
        f"#define ARENA_BUF_A_BYTES     {OBJ_BUF_A_BYTES}",         # mutable copy the prefix writes
        f"#define ARENA_SCROLL_PLAY_OFF {play_off - buf_c}",        # gfx + this: the scroll playfield
        f"#define ARENA_COURSE_STREAM_OFF {course_base - buf_a}",   # tables + this: the leg's records
        f"#define ARENA_DASH_SRC_OFF    {adapter.DASH_SRC_OFF}",    # gfx + this: dashboard graphic
        f"#define ARENA_NUM_SPRITES_OFF {adapter.NUM_GLYPH_BUF_OFF}",  # gfx + this: digit sprites
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
    ring = adapter.course_ring(img)
    scroll = adapter.scroll_state(img)
    course = adapter.course_state(img)

    st = adapter.hud_state(img)
    pl = adapter.player_state(img)
    out = ["/* Generated by gen_demo_fixture.py — do not edit. Inputs for the interactive road + HUD",
           " * demo that are NOT asset-file content: the original program's own data-segment tables,",
           " * the geometry const sources, the initial pose/HudState scalars, the palette, and the",
           " * offsets at which the arena-resident assets live. Everything from COURSES.DAT and",
           " * GRAPHICS.GRA the demo loads itself at boot (see include/assets.h). */",
           "#ifndef RM_DEMO_FIXTURE_H", "#define RM_DEMO_FIXTURE_H", "#include <stdint.h>", ""]
    for name, data in hud.hud_asset_arrays(img, from_arena=True):
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
            f"#define ROAD_CURVE_INIT      {pose.curve}",
            f"#define ROAD_VIEW_FLAGS_INIT {pose.view_flags}",
            "#define ROAD_SEG_DATA_INIT   { " + seg + " }",
            f"#define SCROLL_SPEED_INIT    {scroll.scroll_speed}",
            f"#define HSCROLL_POS_INIT     {scroll.hscroll_pos}",
            f"#define COURSE_ROW_CTR_INIT  {course.row_ctr}",
            f"#define COURSE_READ_POS_INIT {course.read_pos}",
            "", _c_ring(ring),
            ""] + arena_defines + [""]

    # ---- draw_game_objects: the table offsets within fixture_obj_low + the object scalar inits.
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
        f"#define SP_ANIM_FRAME_INIT    {sp.anim_frame}",
        f"#define SP_SPIN_RESET_INIT    {sp.spin_reset}",
        f"#define SP_BUGGY_DRAW_FLAG_INIT {sp.buggy_draw_flag}",
        f"#define SP_COLLISION_LOCK_INIT {sp.collision_lock}",
        f"#define SP_SPEED_RAW_INIT     {sp.speed_raw}",
        f"#define SP_LEAN_ACCUM_INIT    {sp.lean_accum}",
        f"#define SP_LEAN_FRAME_INIT    {sp.lean_frame}",
        "",
        # ---- player physics: the const tables (all inside the obj-low blob) + the starting state.
        f"#define OBJ_LOW_LEAN_ANIM_TBL {low(adapter.A_lean_anim_tbl)}",
        f"#define OBJ_LOW_SCROLL_SPEED_TBL {low(adapter.A_scroll_speed_tbl)}",
        f"#define OBJ_LOW_SPEED_JITTER_TBL {low(adapter.A_speed_jitter_tbl)}",
        f"#define OBJ_LOW_STEER_CURVE_TBL {low(adapter.A_steer_curve_tbl)}",
        f"#define OBJ_LOW_LEGFLAG_TBL   {low(adapter.A_legflag_tbl)}",
        f"#define OBJ_LOW_CRASH_ANIM_TBL {low(adapter.A_crash_anim_tbl)}",
        "",
        f"#define PL_ENGINE_RPM_INIT    {pl.engine_rpm}",
        f"#define PL_RPM_CAP_INIT       {pl.rpm_cap}",
        f"#define PL_RPM_ADD_INIT       {pl.rpm_add}",
        f"#define PL_SPEED_RAW_INIT     {pl.speed_raw}",
        f"#define PL_SPEED_INIT         {pl.speed}",
        f"#define PL_SPEED_JITTER_PH_INIT {pl.speed_jitter_ph}",
        f"#define PL_SCROLL_PHASE_INIT  {pl.scroll_phase}",
        f"#define PL_VIEW_BANK_INIT     {pl.view_bank}",
        f"#define PL_GROUND_VIEW_OFF_INIT {pl.ground_view_off}",
        f"#define PL_ROAD_EDGE_SEL_INIT {pl.road_edge_sel}",
        f"#define PL_WHEEL_POS_INIT     {pl.wheel_pos}",
        f"#define PL_STEER_HOLD_INIT    {pl.steer_hold}",
        f"#define PL_LEAN_PHASE_INIT    {pl.lean_phase}",
        f"#define PL_FIRE_HOLD_INIT     {pl.fire_hold}",
        f"#define PL_LEG_FLAGS_SEL_INIT {pl.leg_flags_sel}",
        f"#define PL_TIME_SUBCTR_INIT   {pl.time_subctr}",
        f"#define PL_TIMEOUT_GATE_INIT  {int(pl.timeout_gate)}",
        "", "#endif /* RM_DEMO_FIXTURE_H */", ""]
    (build / "demo_fixture.h").write_text("\n".join(out))
    print(f"wrote {build/'demo_fixture.h'}, golden.bin, palette.bin "
          f"(leg={leg} curve={pose.curve} view_flags={pose.view_flags} seg0={pose.seg_data[0]} "
          f"row_ctr=0x{course.row_ctr:x} read_pos=0x{course.read_pos:x})")


if __name__ == "__main__":
    main()
