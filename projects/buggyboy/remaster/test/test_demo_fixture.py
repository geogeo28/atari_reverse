"""test_demo_fixture.py — pin the demo fixture's buffer windows to the cores' real reach.

The demo bakes fixed-size copies of regions the cores index dynamically; a window sized by "what
the staged frame happened to reach" fails silently on other frames — the reads land in the BSS
beyond the copy and the draw becomes a noop. That exact failure shipped once: buf_a_ram was 0x3400
bytes while the leg-0 start gate's type codes (0x3a/0x3b) index the per-type record table past it,
so the demo silently dropped the whole gate (the frame-0 golden DIFF of 1110 bytes).
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

    gen = (adapter.REMASTER / "render/atari/gen_demo_fixture.py").read_text()
    found = re.search(r"^OBJ_BUF_A_BYTES = (0x[0-9a-fA-F]+|\d+)", gen, re.M)
    assert found, "OBJ_BUF_A_BYTES not found in gen_demo_fixture.py"
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
    the first draw once ran before apply_player ever copied ground_view_off in. make test never runs
    demo_main.c, so this source pin plus the on-target run_demo MATCH are the only guards."""
    demo = (adapter.REMASTER / "render/atari/demo_main.c").read_text()
    # apply_player copies the physics ground_view_off into the object-list cursor + the ground view.
    assert re.search(r"objlist->obj_scan_off\s*=\s*p->ground_view_off", demo), (
        "apply_player no longer copies ground_view_off into obj_scan_off")
    # start_leg (which runs apply_player + ring_views_refresh) must precede the frame-0 draw.
    assert "apply_player(player, pose, road, scroll, sprite, hud, ground, objlist, ev)" in demo, (
        "start_leg no longer derives the frame-0 views via apply_player")
    start_pos = demo.index("start_leg(&player")
    draw_pos = demo.index("draw_frame(screen_buf(shown)")
    assert start_pos < draw_pos, (
        "start_leg (which derives the frame-0 views) must run before the frame-0 draw — else frame 0's "
        "object passes read their display records at the wrong cursor (the 1110-byte golden DIFF)")
