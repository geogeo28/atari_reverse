"""test_game_fixture.py — pin the game fixture's buffer windows to the cores' real reach.

The game bakes fixed-size copies of regions the cores index dynamically; a window sized by "what
the staged frame happened to reach" fails silently on other frames — the reads land in the BSS
beyond the copy and the draw becomes a noop. That exact failure shipped once: buf_a_ram was 0x3400
bytes while the leg-0 start gate's type codes (0x3a/0x3b) index the per-type record table past it,
so the game silently dropped the whole gate (the frame-0 golden DIFF of 1110 bytes).
"""
import re

import pytest

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


def test_font_window_covers_the_name_entry_character_range():
    """FONT_BYTES must reach past the HIGHEST glyph the game can ask for, which is NOT a HUD glyph:
    the high-score initials cycle 'A'..'`' (src/flow.c), so the delete sentinel HS_CHAR_DEL tops the
    range. Sized to what the gauge strings alone need (0x600) it stopped exactly one glyph short, and
    on target the blitter read the array declared after fixture_font as glyph pixels — an all-zero
    (mask, ink) row REPLACES the cell with colour 0, so name entry drew a black box for '`'.

    Three pins: the window covers the range, the glyph stride agrees with the C blitter across the
    language boundary, and the SHIPPED fixture is at least as long (a stale generated header)."""
    flow = (adapter.REMASTER / "src/flow.c").read_text()
    top_char = _define(flow, "HS_CHAR_DEL")
    assert adapter.FONT_MAX_GLYPH >= top_char, (
        f"FONT_MAX_GLYPH {adapter.FONT_MAX_GLYPH:#x} is below the name-entry top char {top_char:#x}")

    text_h = (adapter.REMASTER / "include/text.h").read_text()
    assert adapter.FONT_GLYPH_STRIDE == _define(text_h, "GLYPH_BYTES"), \
        "adapter's glyph stride disagrees with the C blitter's GLYPH_BYTES"

    need = (top_char + 1) * adapter.FONT_GLYPH_STRIDE
    assert adapter.FONT_BYTES >= need, (
        f"font window {adapter.FONT_BYTES:#x} stops short of glyph {top_char:#x} (needs {need:#x}) — "
        f"the blitter reads past the fixture and draws a black box")

    # The shipped fixture is a GENERATED, gitignored artifact of the m68k build (render/atari/build/),
    # so it is absent on a fresh checkout and this leg only applies once it has been baked.
    fixture_h = adapter.REMASTER / "render/atari/build/game_fixture.h"
    if not fixture_h.exists():
        pytest.skip("game_fixture.h not built yet (run render/atari/gen_game_fixture.py)")
    found = re.search(r"fixture_font\[(\d+)\]", fixture_h.read_text())
    assert found, "fixture_font not found in the generated game_fixture.h"
    assert int(found.group(1)) >= need, (
        f"shipped fixture_font is {int(found.group(1)):#x} bytes, short of {need:#x} — "
        f"re-run gen_game_fixture.py")


def test_marker_decay_arena_padding_covers_the_prefix_walk():
    """The prefix's marker-decay base sits BELOW the object grid: in the original the decay base is
    `A_obj_markers - 8` and the walk runs
    `marker_off + i * stride` for 14 records, so it reaches below row 0 and past the last row. Both pads
    must therefore be derived quantities, not two coincidental 8s — under-size either and the prefix
    writes outside the block (or, worse, lands 8 bytes off and silently animates nothing, which is the
    bug this padding was added to fix).

    The geometry now lives in include/game.h (not the shell), so the harness allocates its grid the
    same way — this pins the shared constants against the addresses in adapter.py and the walk in
    src/gameplay.c, and pins adapter.py's mirror of them equal across the language boundary."""
    game_h = (adapter.REMASTER / "include/game.h").read_text()
    bias = _define(game_h, "RM_RING_DECAY_BIAS")
    spill = _define(game_h, "RM_RING_DECAY_SPILL")
    assert (bias, spill) == (adapter.RM_RING_DECAY_BIAS, adapter.RM_RING_DECAY_SPILL), \
        "adapter.py's ring-block mirror disagrees with game.h"
    # ...and the C macro's own body, which nothing else reads: comparing adapter's derived value to
    # adapter's own definition would be tautological, and dropping a term from game.h's expression
    # (e.g. the spill) would silently under-size the shell's block by the walk's overrun.
    macro = re.search(r"#define\s+RM_RING_ST_BLOCK_BYTES\s*\\\s*\n\s*(.+)", game_h)
    assert macro, "RM_RING_ST_BLOCK_BYTES not found in game.h"
    for term in ("RM_RING_DECAY_BIAS", "RM_RING_ROWS", "RM_RING_ROW_BYTES", "RM_RING_DECAY_SPILL"):
        assert term in macro.group(1), f"RM_RING_ST_BLOCK_BYTES no longer includes {term}"

    assert bias == adapter.A_ring_base - adapter.A_marker_decay_base, (
        f"RM_RING_DECAY_BIAS {bias:#x} != the original's grid-to-decay-base gap "
        f"{adapter.A_ring_base - adapter.A_marker_decay_base:#x}")

    prefix = (adapter.REMASTER / "src/gameplay.c").read_text()
    records = _define(prefix, "GOBJ_MARKER_RECS") + 1          # the loop runs 0..GOBJ_MARKER_RECS
    stride = _define(prefix, "GOBJ_MARKER_STRIDE")
    events = (adapter.REMASTER / "src/events.c").read_text()
    # §H dispatches at horizon_row and horizon_row + 2, and marker_decay_spawn takes that as marker_off.
    # RM_MAX_HORIZON_ROW is RM_HORIZON_DIV * 2 (game.h), so derive it from the one source of truth.
    max_off = _define(game_h, "RM_HORIZON_DIV") * 2 + 2
    assert "rm_event_dispatch(c, event, (uint16_t)(horizon_row + 2)" in events, \
        "the §H slot expression moved — re-derive max_off before trusting this bound"

    reach = max_off + (records - 1) * stride                    # deepest byte the clear loop touches
    block = bias + adapter.RING_ROW_BYTES * adapter.RM_RING_ROWS + spill
    assert reach < block, (
        f"the decay walk reaches {reach:#x} but the ring block is only {block:#x} bytes — "
        f"raise RM_RING_DECAY_SPILL")

    # The SHELL's own allocation. game_main.c is never compiled by `make test`, so without this a build
    # that drops the bias (or re-points marker_recs at scratch — the bug that shipped) keeps the whole
    # suite green: the harness allocates correctly on its own and would never notice.
    game = (adapter.REMASTER / "render/atari/game_main.c").read_text()
    assert re.search(r"ring_st_block\[RM_RING_ST_BLOCK_BYTES\]", game), \
        "game_main.c no longer sizes the ring block with RM_RING_ST_BLOCK_BYTES"
    assert re.search(r"\*const ring_st = ring_st_block \+ RM_RING_DECAY_BIAS", game), \
        "game_main.c no longer places the grid at the decay bias"
    # The shell must not hand-build this bundle at all: rm_bind_gobj_prefix_assets (src/gameplay.c) owns
    # every alias in it, and the equivalence harness calls the SAME binder, so the two cannot diverge.
    # Pin the ARGUMENTS, not just the call: the binder derives marker_recs and the mirrors, but
    # anim_color is a pass-through, so a shell that handed the prefix a private colour buffer would
    # still "use the binder" while silently breaking the HUD fuel-mask alias on hardware.
    assert re.search(r"rm_bind_gobj_prefix_assets\(&pfx_assets,[\s\S]{0,240}?"
                     r"ring_st,\s*buf_a_ram,\s*hud_assets\.fuel_mask\)", game), \
        ("game_main.c must bind the prefix assets through rm_bind_gobj_prefix_assets, passing the "
         "dispatcher's grid, buf_a, and the HUD's own fuel_mask (the animated-colour alias)")
    assert not re.search(r"\.marker_recs\s*=", game), \
        "game_main.c binds marker_recs by hand again — it must go through rm_bind_gobj_prefix_assets"

    # The binder applies the two anim-word mirror offsets; adapter.py mirrors them for the prefix-slice
    # comparator, so pin the pair across the language boundary (CLAUDE.md §5).
    assert adapter.GOBJ_ANIM_BUF_OFF1 == _define(game_h, "RM_GOBJ_ANIM_MIRROR1_OFF")
    assert adapter.GOBJ_ANIM_BUF_OFF2 == _define(game_h, "RM_GOBJ_ANIM_MIRROR2_OFF")


def test_marker_decay_seed_matches_the_engine_constants():
    """test_composed_frame seeds an armed decay with its own copies of two C constants. Pin them, as
    CLAUDE.md §5 requires of a value duplicated across a language boundary — otherwise a change to
    either silently moves the seeded walk off the band the tests assume, and the binding pin fails with
    a message blaming the binding."""
    from test_composed_frame import DECAY_COUNTDOWN, DECAY_STRIDE

    events = (adapter.REMASTER / "src/events.c").read_text()
    prefix = (adapter.REMASTER / "src/gameplay.c").read_text()
    assert DECAY_COUNTDOWN == _define(events, "MARKER_DECAY_ARM"), \
        "the seeded countdown is not the arm value marker_decay_spawn writes"
    assert DECAY_STRIDE == _define(prefix, "GOBJ_MARKER_STRIDE"), \
        "the seeded stride is not the prefix's per-record stride"


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
    must equal the shell's own leg count IP_LEG_COUNT (include/flow.h) — one source, so the harness can
    never loop a leg the game cannot start (or skip one it can)."""
    gen = (adapter.REMASTER / "render/atari/gen_game_fixture.py").read_text()
    found = re.search(r"^NUM_LEGS = (\d+)", gen, re.M)
    assert found, "NUM_LEGS not found in gen_game_fixture.py"
    num_legs = int(found.group(1))

    flowh = (adapter.REMASTER / "include/flow.h").read_text()
    assert num_legs == _define(flowh, "IP_LEG_COUNT"), (
        f"NUM_LEGS ({num_legs}) != the shell's IP_LEG_COUNT — the golden loop and the leg select disagree")


def test_fkey_codes_match_the_header():
    """adapter's RM_FKEY_* / IP_LEG_COUNT mirrors (test scripts read_fkey answers with them) must equal
    include/flow.h — the one source the C shell and the flow share. The debug codes are laid out ABOVE the
    leg range (F6 == IP_LEG_COUNT, F10 == +1, RETURN == +2) so a leg pick and a debug key never collide;
    pin both the numeric agreement and that flow.h still defines them relative to IP_LEG_COUNT."""
    flowh = (adapter.REMASTER / "include/flow.h").read_text()
    ip = _define(flowh, "IP_LEG_COUNT")
    assert adapter.IP_LEG_COUNT == ip, (adapter.IP_LEG_COUNT, ip)
    assert (adapter.RM_FKEY_NONE, adapter.RM_FKEY_F6, adapter.RM_FKEY_F10, adapter.RM_FKEY_RETURN) \
        == (-1, ip, ip + 1, ip + 2), (adapter.RM_FKEY_F6, adapter.RM_FKEY_F10, adapter.RM_FKEY_RETURN)
    # the codes must stay STRUCTURALLY tied to IP_LEG_COUNT in the header, not hard-coded literals.
    assert re.search(r"#define\s+RM_FKEY_F6\s+IP_LEG_COUNT\b", flowh), "RM_FKEY_F6 not defined as IP_LEG_COUNT"
    assert re.search(r"#define\s+RM_FKEY_F10\s+\(IP_LEG_COUNT \+ 1\)", flowh), "RM_FKEY_F10 not IP_LEG_COUNT+1"
    assert re.search(r"#define\s+RM_FKEY_RETURN\s+\(IP_LEG_COUNT \+ 2\)", flowh), "RM_FKEY_RETURN not IP_LEG_COUNT+2"
