"""test_game_objects.py — remaster draw_game_objects composite equivalence vs g_draw_game_objects.

draw_game_objects is the per-frame object/scene draw orchestrator: it advances the off-frame prefix
state, then draws the ground, the foreground buggy sprite, the roadside objects (two sprite-list
passes split around the scaled draw_object), and the player buggy — the last object pass ordered
against the buggy by the view. This test sequences the remaster sub-draws in that exact order on a
staged frame and asserts the whole framebuffer is byte-identical to recreate's g_draw_game_objects.

Every sub-draw is already verified individually (test_sprite / test_ground / test_object /
test_object_list_rm); this proves they compose in the right order into the same frame.
"""
import equiv
import pytest

CASES = [(0, 60), (1, 90), (2, 120), (3, 120), (4, 60), (4, 90)]


@pytest.mark.parametrize("leg,warmup", CASES)
def test_draw_game_objects_matches(leg, warmup, capsys):
    lib = equiv._lib()
    image = equiv.object_background(leg=leg, warmup=warmup)
    diff, footprint = equiv.compare_game_objects(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup}: footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_game_objects drew nothing (leg={leg}, warmup={warmup})"
    assert diff == 0, f"draw_game_objects differs from recreate in {diff} bytes (leg={leg}, warmup={warmup})"
