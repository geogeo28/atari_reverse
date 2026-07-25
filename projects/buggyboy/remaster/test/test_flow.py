"""test_flow.py — pixel-equivalence for the between-legs flow's draw surfaces (slice A) vs recreate.

Four cores, all validated against recreate's verified g_* exports on the same staged background:
  rm_intermission_poll  the 9-entry table-driven block copy         (whole draw-buffer, leaf)
  rm_draw_leg_results   the per-leg results screen                  (whole draw-buffer)
  rm_fade_step          one between-legs backdrop frame             (whole draw-buffer)
  rm_draw_intermission  the scrolling hi-score/credits screen       (footprint coverage + no-wrong-pixel)

The scroll sweep exercises draw_intermission's clip regimes: at a high scroll the rows sit below the
band (clipped against its bottom); at a low scroll they scroll up off the top (top-clipped, source
advanced). Both flip parities are staged where the draw buffer derives from flip_idx (the adapter must
read physbase_tbl[flip_idx]). leg_results runs all five legs (per-leg palette + digits).
"""
import adapter
import equiv
import pytest

# draw_intermission's scroll range the attract loop produces: INT_SCROLL_INIT 0x63 down through 0.
SCROLL_SWEEP = [0x63, 0x50, 0x40, 0x30, 0x20, 0x13, 0x10, 8, 4, 0]

# (results_mode, hiscore_pos, leg) for the race-end / name-entry results screen: the made path (mode 0,
# a ranked position) at several ranks/legs, and the missed path (mode 2, no rank).
RESULTS_SCREEN_CASES = [(0, 1, 0), (0, 5, 2), (0, 9, 4), (2, 0, 0), (2, 0, 3)]


@pytest.mark.parametrize("flip", [0, 4])
def test_intermission_poll_matches(flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, flip=flip)
    diff, footprint = equiv.compare_intermission_poll(lib, image)
    with capsys.disabled():
        print(f"  poll flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, "intermission_poll drew nothing"
    assert diff == 0, f"intermission_poll differs from recreate in {diff} bytes (flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
@pytest.mark.parametrize("leg", [0, 1, 2, 3, 4])
def test_leg_results_matches(leg, flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=leg, warmup=60, flip=flip)
    diff, footprint = equiv.compare_leg_results(lib, image)
    with capsys.disabled():
        print(f"  leg_results leg={leg} flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_leg_results drew nothing (leg={leg}, flip={flip})"
    assert diff == 0, f"draw_leg_results differs from recreate in {diff} bytes (leg={leg}, flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
def test_divider_matches(flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, flip=flip)
    diff, footprint = equiv.compare_divider(lib, image)
    with capsys.disabled():
        print(f"  divider flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, "draw_divider drew nothing"
    assert diff == 0, f"draw_divider differs from recreate in {diff} bytes (flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
def test_panel5_matches(flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, flip=flip)
    diff, footprint = equiv.compare_panel5(lib, image)
    with capsys.disabled():
        print(f"  panel5 flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, "draw_panel5 drew nothing"
    assert diff == 0, f"draw_panel5 differs from recreate in {diff} bytes (flip={flip})"


# The F10 reload-menu panels (draw_panel3 = the "insert disk / press RETURN" prompt, draw_panel2 = the
# "loading / please wait" confirmation), byte-exact vs recreate — same divider + chained-label body as
# panel5, their own label strings and dst offsets.
@pytest.mark.parametrize("compare,name", [(equiv.compare_panel3, "panel3"), (equiv.compare_panel2, "panel2")])
@pytest.mark.parametrize("flip", [0, 4])
def test_reload_panels_match(compare, name, flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, flip=flip)
    diff, footprint = compare(lib, image)
    with capsys.disabled():
        print(f"  {name} flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_{name} drew nothing"
    assert diff == 0, f"draw_{name} differs from recreate in {diff} bytes (flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
@pytest.mark.parametrize("mode,pos,leg", RESULTS_SCREEN_CASES)
def test_results_screen_matches(mode, pos, leg, flip, capsys):
    """The race-end / name-entry results screen (rm_draw_results_screen) whole draw-buffer byte-exact vs
    recreate's g_draw_results_screen, over the made (mode 0, ranked) and missed (mode 2) paths and both
    flip parities. mode/pos are poked into the image; the candidate reads them as arguments."""
    lib = equiv._lib()
    image = equiv.flow_background(leg=leg, warmup=60, flip=flip)
    equiv._w16(image, adapter.A_results_mode, mode)
    equiv._w16(image, adapter.A_hiscore_pos, pos)
    diff, footprint = equiv.compare_results_screen(lib, image)
    with capsys.disabled():
        print(f"  results_screen mode={mode} pos={pos} leg={leg} flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, "draw_results_screen drew nothing"
    assert diff == 0, f"draw_results_screen differs from recreate in {diff} bytes (mode={mode}, pos={pos}, leg={leg}, flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
def test_fade_step_matches(flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, scroll=0x30, flip=flip)
    diff, footprint = equiv.compare_fade_step(lib, image)
    with capsys.disabled():
        print(f"  fade_step flip={flip}: footprint={footprint} diff={diff}")
    assert footprint > 0, "fade_step drew nothing"
    assert diff == 0, f"fade_step differs from recreate in {diff} bytes (flip={flip})"


@pytest.mark.parametrize("flip", [0, 4])
@pytest.mark.parametrize("scroll", SCROLL_SWEEP)
def test_draw_intermission_matches(scroll, flip, capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60, scroll=scroll, flip=flip)
    coverage, wrong = equiv.compare_draw_intermission(lib, image)
    with capsys.disabled():
        print(f"  intermission scroll={scroll:#x} flip={flip}: coverage={coverage:.4f} wrong={wrong}")
    assert wrong == 0, f"draw_intermission painted {wrong} wrong pixels (scroll={scroll:#x}, flip={flip})"
    assert coverage == 1.0, \
        f"draw_intermission coverage {coverage:.4f} < 1.0 (scroll={scroll:#x}, flip={flip})"


# ---- the name-entry CHARACTER RANGE, drawn ----
# The results screen is the surface the initials are drawn on, and test_results_screen_matches above
# already byte-compares it — but only over the DEFAULT hi-score table, whose names are "...". The
# name-entry alphabet ('A'..'`') therefore never reached the glyph blitter from here, which is why a
# font window one glyph short of '`' shipped and drew a BLACK BOX on target (STATUS.md's play-test
# table). These cases seed the alphabet into the table's initials fields so the screen actually draws it.
from test_game_fixture import _define                      # noqa: E402  shared #define reader

_FLOW_C = (adapter.REMASTER / "src/flow.c").read_text()
_FLOW_H = (adapter.REMASTER / "include/flow.h").read_text()
NAME_CHAR_LO = _define(_FLOW_C, "HS_CHAR_LO")              # 'A'
NAME_CHAR_HI = _define(_FLOW_C, "HS_CHAR_DEL")             # '`' — the delete sentinel, the top of the range
NAME_FIELD_OFF = _define(_FLOW_H, "HS_NAME_FIELD_OFF")
NAME_INITIALS = _define(_FLOW_C, "HS_INITIALS")
NAME_SLOTS = adapter.HIGHSCORE_ROWS * NAME_INITIALS        # initials fields in one leg's table
# Two windows tile the alphabet across the table's slots (the range is wider than one table holds).
NAME_WINDOWS = [NAME_CHAR_LO, NAME_CHAR_HI - NAME_SLOTS + 1]


def _seed_name_alphabet(image, leg, first):
    """Write consecutive name-entry characters into every initials field of `leg`'s table, low row
    first, so `first + NAME_SLOTS - 1` (the top of the window) lands in the LAST row."""
    table = adapter.A_highscore_table + leg * adapter.HIGHSCORE_LEG_STRIDE
    for slot in range(NAME_SLOTS):
        row, ch_i = divmod(slot, NAME_INITIALS)
        image[table + row * adapter.HIGHSCORE_ROW + NAME_FIELD_OFF + ch_i] = first + slot


@pytest.mark.parametrize("first", NAME_WINDOWS)
@pytest.mark.parametrize("leg", [0, 2])
def test_results_screen_draws_the_name_entry_alphabet(first, leg, capsys):
    """Every character the initials entry can produce, actually drawn and byte-compared against
    recreate. The two windows together cover 'A'..'`' inclusive; the top one ends ON the delete
    sentinel, the glyph whose absence from the font window was invisible to every other test.

    Mutation-verified: shrinking FONT_BYTES back to 0x600 reddens the window that draws '`'."""
    # Gap-freeness, not "the last window ends at the top char" — that is true BY CONSTRUCTION of
    # NAME_WINDOWS and would still hold with a hole in the middle (e.g. if the table shrank to 5 rows).
    assert NAME_WINDOWS[0] + NAME_SLOTS >= NAME_WINDOWS[1], "the windows no longer tile the alphabet"
    last = first + NAME_SLOTS - 1
    lib = equiv._lib()

    def staged(top_char):
        img = equiv.flow_background(leg=leg, warmup=60, flip=0)
        equiv._w16(img, adapter.A_results_mode, 0)         # the made-the-table layout draws the names
        equiv._w16(img, adapter.A_hiscore_pos, 1)
        _seed_name_alphabet(img, leg, first)
        # overwrite just the final initial, so the two images differ ONLY in the window's top character
        table = adapter.A_highscore_table + leg * adapter.HIGHSCORE_LEG_STRIDE
        img[table + (adapter.HIGHSCORE_ROWS - 1) * adapter.HIGHSCORE_ROW
            + NAME_FIELD_OFF + NAME_INITIALS - 1] = top_char
        return img

    image = staged(last)
    diff, footprint = equiv.compare_results_screen(lib, image)
    with capsys.disabled():
        print(f"  results name alphabet leg={leg} {first:#04x}..{last:#04x}: "
              f"footprint={footprint} diff={diff}")
    assert diff == 0, (f"results screen differs from recreate in {diff} bytes while drawing "
                       f"{first:#04x}..{last:#04x}")

    # NON-VACUITY: `diff == 0` alone cannot show the alphabet reached the screen — both sides read the
    # same seeded table, and the initials are ~250 bytes of a ~9600-byte footprint dominated by the
    # background fill, so a screen that never blitted the LAST row (results.c's RS_MAX_ROWS is not
    # pinned to HS_ROWS) would agree with the reference and pass. Prove the row carrying the window's
    # TOP character is really drawn: change only that character and the reference output must move.
    _, ref_top = equiv._flow_ref(image, "g_draw_results_screen")
    _, ref_alt = equiv._flow_ref(staged(NAME_CHAR_LO), "g_draw_results_screen")
    assert bytes(ref_top) != bytes(ref_alt), (
        f"changing the last initial ({last:#04x}) did not change the drawn screen — the row carrying "
        f"the top of the alphabet is never blitted, so this case proves nothing about it")
