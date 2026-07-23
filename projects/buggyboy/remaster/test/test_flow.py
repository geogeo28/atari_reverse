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
import equiv
import pytest

# draw_intermission's scroll range the attract loop produces: INT_SCROLL_INIT 0x63 down through 0.
SCROLL_SWEEP = [0x63, 0x50, 0x40, 0x30, 0x20, 0x13, 0x10, 8, 4, 0]


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
