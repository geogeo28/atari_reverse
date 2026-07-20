"""test_gobj_prefix.py — remaster gobj_prefix equivalence vs recreate's g_draw_game_objects_prefix.

The prefix is the deterministic per-frame state advance draw_game_objects runs before drawing: the
marker-decay slot, the road-colour animation counters, and the bonus-window flag animation. It writes
no framebuffer pixels, so it's validated by state: run recreate's g_draw_game_objects_prefix and the
remaster rm_gobj_prefix on the same image and compare every location the prefix writes (the scalar
globals, the 8-byte animated colour, the marker records, the two buf_a anim-word mirrors).

The staged frames carry inactive marker/bonus state, so cases poke those on to exercise the
marker-decay clear/retire branches and the bonus-window flag advance.
"""
import equiv
import pytest

# (pokes): each dict pokes prefix state on. marker_decay is [active, offset, countdown]; bonus_timer
# at 0x28 triggers the flag-sequence advance; the retire branch fires when countdown - 0x20 < 0.
POKES = [
    {},                                                                    # captured (inactive) state
    {equiv.adapter.A_marker_decay: 1, equiv.adapter.A_marker_decay + 2: 0x40,
     equiv.adapter.A_marker_decay + 4: 0x60},                             # marker decay, decrement path
    {equiv.adapter.A_marker_decay: 1, equiv.adapter.A_marker_decay + 2: 0x40,
     equiv.adapter.A_marker_decay + 4: 0x00},                             # marker decay, retire path
    {equiv.adapter.A_bonus_timer: 0x50},                                  # bonus window open, scroll cycle
    {equiv.adapter.A_bonus_timer: 0x29},                                  # bonus -> 0x28: flag advance
    {equiv.adapter.A_bonus_timer: 0x01},                                  # bonus -> 0: window closes
]


@pytest.mark.parametrize("leg,warmup", [(0, 60), (2, 120), (4, 90)])
@pytest.mark.parametrize("pokes", POKES)
def test_gobj_prefix_matches(leg, warmup, pokes, capsys):
    lib = equiv._lib()
    image = equiv.object_background(leg=leg, warmup=warmup)
    for addr, val in pokes.items():
        equiv._w16(image, addr, val & 0xffff)
    bad = equiv.compare_gobj_prefix(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} pokes={pokes}: {len(bad)} state mismatches")
    assert not bad, f"gobj_prefix state differs (leg={leg}, pokes={pokes}): {bad}"
