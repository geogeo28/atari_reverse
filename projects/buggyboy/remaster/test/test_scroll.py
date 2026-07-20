"""test_scroll.py — remaster blit_road_scroll equivalence vs recreate's g_blit_road_scroll.

blit_road_scroll fine-scrolls the double-wide road playfield onto rows 0..103 (disjoint from
render_road's 104..199) and advances the persistent scroll position. Since the on-target demo will
scroll by varying scroll_speed / hscroll_pos, the port must be byte-exact for arbitrary scroll
state — so each case perturbs those inputs and asserts the whole framebuffer matches recreate and the
updated hscroll_pos / hscroll_step2 outputs match too.
"""
import adapter
import equiv
import pytest

# (scroll_speed, hscroll_pos): sweep the fine shift (low nibble), the coarse offset, and the wrap /
# EDGE_THRESH tail. hscroll_pos wraps into [0, 0x280); values straddle the 0x140 edge threshold.
POKES = [
    {},                                                          # captured scroll state unchanged
    {adapter.A_scroll_speed: 0},                                 # no advance
    {adapter.A_scroll_speed: 4, adapter.A_hscroll_pos: 0x000},   # small fine shift near the start
    {adapter.A_scroll_speed: 1, adapter.A_hscroll_pos: 0x07f},   # fine shift, below the edge threshold
    {adapter.A_scroll_speed: 1, adapter.A_hscroll_pos: 0x141},   # just past EDGE_THRESH (one wrap col)
    {adapter.A_scroll_speed: 1, adapter.A_hscroll_pos: 0x1ff},   # deep into the wrap region
    {adapter.A_scroll_speed: 8, adapter.A_hscroll_pos: 0x278},   # near SCROLL_WRAP (wraps this frame)
    {adapter.A_scroll_speed: 0xfffe, adapter.A_hscroll_pos: 0x010},  # negative speed (scroll the other way)
]


@pytest.mark.parametrize("leg,warmup", [(0, 60), (1, 60), (2, 90), (3, 75), (4, 60)])
@pytest.mark.parametrize("pokes", POKES)
def test_blit_road_scroll_matches(leg, warmup, pokes, capsys):
    lib = equiv._lib()
    image = equiv.road_background(leg=leg, warmup=warmup)
    diff, scalars_ok = equiv.compare_scroll(lib, image, pokes)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} pokes={pokes}: diff={diff} scalars_ok={scalars_ok}")
    assert diff == 0, f"scrolled road differs in {diff} bytes (leg={leg}, pokes={pokes})"
    assert scalars_ok, f"hscroll_pos/hscroll_step2 outputs differ (leg={leg}, pokes={pokes})"
