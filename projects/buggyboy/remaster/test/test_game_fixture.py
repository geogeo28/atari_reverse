"""test_game_fixture.py — pin the game fixture's buffer windows to the cores' real reach.

The game bakes fixed-size copies of regions the cores index dynamically; a window sized by "what
the staged frame happened to reach" fails silently on other frames — the reads land in the BSS
beyond the copy and the draw becomes a noop. That exact failure shipped once: buf_a_ram was 0x3400
bytes while the leg-0 start gate's type codes (0x3a/0x3b) index the per-type record table past it,
so the game silently dropped the whole gate (the frame-0 golden DIFF of 1110 bytes).
"""
import re

import adapter


def _define(text, name):
    found = re.search(rf"^#define\s+{name}\s+(0x[0-9a-fA-F]+|\d+)", text, re.M)
    assert found, f"{name} not found"
    return int(found.group(1), 0)


def test_buf_a_window_covers_the_type_record_table():
    """OBJ_BUF_A_BYTES must reach past the last per-type record the dispatcher can index:
    OBJ_TYPE_BASE + (type mask + 1) * OBJ_TYPE_STRIDE, for any type code the flag mask admits.

    The special pass's reach (OBJ_SPECIAL_BASE + rec_off + record fields, ~0x2290 with rec_off
    capped at GOBJ_D6_INIT) sits well inside the type-table end, so this one bound covers it
    transitively — no separate assert, which could only ever pass vacuously today."""
    disp = (adapter.REMASTER / "src/object_list.c").read_text()
    base = _define(disp, "OBJ_TYPE_BASE")
    stride = _define(disp, "OBJ_TYPE_STRIDE")
    mask = _define(disp, "OBJ_ROWS_ONLY")

    gen = (adapter.REMASTER / "render/atari/gen_game_fixture.py").read_text()
    found = re.search(r"^OBJ_BUF_A_BYTES = (0x[0-9a-fA-F]+|\d+)", gen, re.M)
    assert found, "OBJ_BUF_A_BYTES not found in gen_game_fixture.py"
    window = int(found.group(1), 0)

    table_end = base + (mask + 1) * stride
    assert window >= table_end, (
        f"buf_a window {window:#x} stops short of the per-type record table end {table_end:#x} — "
        f"types above {(window - base) // stride:#x} silently draw nothing")


def test_frame0_views_derived_before_first_draw():
    """rm_init_leg produces the leg-start OWNER state; the render VIEWS (obj_scan_off / ground.view /
    the HUD / the sprite gates) are DERIVED from it by start_leg's apply_player + ring_views_refresh,
    which MUST run before the frame-0 draw. Seeding obj_scan_off 0 was half of the old frame-0 golden
    DIFF — the list-cursor offset and the ground's view column are ONE original global (0x18c58), and
    the first draw once ran before apply_player ever copied ground_view_off in. The DERIVATION itself
    is hoisted to rm_apply_player (src/gameplay.c) and now host-tested (test_leg_drive's fan-out check);
    this pins the derivation's home and that the shell WIRES it before the frame-0 draw."""
    fanout = (adapter.REMASTER / "src/gameplay.c").read_text()
    # rm_apply_player copies the physics ground_view_off into the object-list cursor + the ground view.
    assert re.search(r"objlist->obj_scan_off\s*=\s*p->ground_view_off", fanout), (
        "rm_apply_player no longer copies ground_view_off into obj_scan_off")
    game = (adapter.REMASTER / "render/atari/game_main.c").read_text()
    # start_leg derives the frame-0 views: apply_player then ring_views_refresh, in that order over the
    # Shell handle (intervening lines allowed — e.g. the race-palette set start_leg now ends with).
    assert re.search(r"apply_player\(s\);[\s\S]{0,400}?ring_views_refresh\(", game), (
        "start_leg no longer derives the frame-0 views via apply_player + ring_views_refresh")
    # The boot fast path starts leg BOOT_FAST_LEG (which runs start_leg's view derivation) before the
    # frame-0 draw — else frame 0's object passes read their display records at the wrong cursor.
    start_pos = game.index("start_leg(s, BOOT_FAST_LEG)")
    draw_pos = game.index("draw_frame(s, screen_buf(s->shown))")
    assert start_pos < draw_pos, (
        "start_leg (which derives the frame-0 views) must run before the frame-0 draw — else frame 0's "
        "object passes read their display records at the wrong cursor (the 1110-byte golden DIFF)")


def test_bind_leg_course_bases_match_the_adapter():
    """game_main.c bind_leg points at leg L's course records via
    arena.tables + L*COURSE_LEG_STRIDE + ARENA_COURSE_{STREAM,MASK}_BASE. gen_game_fixture bakes those
    three constants straight from the adapter, and adapter.course_stream / coll_mask read each leg with
    the SAME L*STRIDE + OFF arithmetic — pin the two paths agree for every leg so a stride/offset drift
    can't send bind_leg to the wrong leg's stream or collision mask (a silent wrong-course race)."""
    gen = (adapter.REMASTER / "render/atari/gen_game_fixture.py").read_text()
    for define, attr in (("COURSE_LEG_STRIDE", "COURSE_LEG_STRIDE"),
                         ("ARENA_COURSE_STREAM_BASE", "COURSE_STREAM_OFF"),
                         ("ARENA_COURSE_MASK_BASE", "COURSE_MASK_OFF")):
        assert re.search(rf"#define {define} +\{{adapter\.{attr}\}}", gen), (
            f"{define} no longer emitted from adapter.{attr}")

    # bind_leg's own arithmetic, and the adapter's per-leg readers, must both be L*STRIDE + OFF.
    game = (adapter.REMASTER / "render/atari/game_main.c").read_text()
    assert re.search(r"leg_off\s*=\s*\(uint32_t\)leg\s*\*\s*COURSE_LEG_STRIDE", game)
    assert re.search(r"leg_off\s*\+\s*ARENA_COURSE_STREAM_BASE", game)
    assert re.search(r"leg_off\s*\+\s*ARENA_COURSE_MASK_BASE", game)
    src = (adapter.REMASTER / "test/adapter.py").read_text()
    assert re.search(r"leg \* COURSE_LEG_STRIDE \+ COURSE_STREAM_OFF", src)
    assert re.search(r"leg \* COURSE_LEG_STRIDE \+ COURSE_MASK_OFF", src)

    # The five per-leg bases bind_leg computes, spelled out — they must stay distinct (a zero stride
    # would overlap every leg onto leg 0's records) and match the adapter constant arithmetic.
    stride = adapter.COURSE_LEG_STRIDE
    stream_offs = [leg * stride + adapter.COURSE_STREAM_OFF for leg in range(5)]
    mask_offs = [leg * stride + adapter.COURSE_MASK_OFF for leg in range(5)]
    assert stream_offs == [0x5ce0, 0x7ce0, 0x9ce0, 0xbce0, 0xdce0], stream_offs
    assert mask_offs == [0x5d48, 0x7d48, 0x9d48, 0xbd48, 0xdd48], mask_offs


def test_golden_leg_count_matches_the_shell():
    """The golden harness pins one boot frame per leg; the leg it CAN boot is bounded by the shell's leg
    select. gen_game_fixture.NUM_LEGS (which bounds GOLDEN_LEG and, via run_golden.py's LEGS, the loop)
    must equal the shell's own leg count IP_LEG_COUNT (src/flow.c) — one source, so the harness can never
    loop a leg the game cannot start (or skip one it can)."""
    gen = (adapter.REMASTER / "render/atari/gen_game_fixture.py").read_text()
    found = re.search(r"^NUM_LEGS = (\d+)", gen, re.M)
    assert found, "NUM_LEGS not found in gen_game_fixture.py"
    num_legs = int(found.group(1))

    flow = (adapter.REMASTER / "src/flow.c").read_text()
    assert num_legs == _define(flow, "IP_LEG_COUNT"), (
        f"NUM_LEGS ({num_legs}) != the shell's IP_LEG_COUNT — the golden loop and the leg select disagree")
