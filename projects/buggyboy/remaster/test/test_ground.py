"""test_ground.py — remaster draw_ground pixel-equivalence vs recreate's verified g_draw_ground.

draw_ground fills the first ground/horizon band whose descriptor carries a draw marker: 0x1a a
colour gradient (1-3 solid-colour scanlines from a band record) or 0x1c a solid fill (1 scanline, 2
for the nearest entry). The staged frames usually carry no marker, so — as recreate's own test does —
each case pokes a marker into one descriptor so the function fires, then runs recreate's g_draw_ground
as the reference and remaster's rm_draw_ground on the same background and asserts the whole framebuffer
is byte-identical.

Entry i selects band (13-1 - i), so sweeping the entry index exercises the gradient's band-clamp
branches (band>=9 -> rec 0, band 5..8 -> rec 1, band 0..4 -> rec 6-band) and the solid fill's
lit/near-band cases (band>=9 lit, band==0 two scanlines).
"""
import adapter
import equiv
import pytest

CASES = [(0, 60), (2, 120), (4, 60)]

# (entry, marker): 0x1a = gradient, 0x1c = solid. Entry 0 -> band 12 (distant/lit), entry 12 -> band 0
# (nearest, two scanlines). The spread hits every gradient clamp bucket and both solid branches.
GROUND_POKES = [
    (0, 0x1a),    # band 12 -> gradient rec 0
    (5, 0x1a),    # band 7  -> gradient rec 1
    (8, 0x1a),    # band 4  -> gradient rec 2
    (12, 0x1a),   # band 0  -> gradient rec 6
    (0, 0x1c),    # band 12 -> solid, lit
    (8, 0x1c),    # band 4  -> solid, black
    (12, 0x1c),   # band 0  -> solid, two scanlines
]


@pytest.mark.parametrize("leg,warmup", CASES)
@pytest.mark.parametrize("entry,marker", GROUND_POKES)
def test_draw_ground_matches(leg, warmup, entry, marker, capsys):
    lib = equiv._lib()
    image = equiv.ground_background(leg=leg, warmup=warmup, entry=entry, marker=marker)
    diff, footprint = equiv.compare_ground(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} entry={entry} marker={marker:#x}: "
              f"footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_ground drew nothing (entry={entry}, marker={marker:#x})"
    assert diff == 0, f"draw_ground differs in {diff} bytes (entry={entry}, marker={marker:#x})"
