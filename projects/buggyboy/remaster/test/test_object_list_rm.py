"""test_object_list.py — remaster draw_object_list pixel-equivalence vs recreate's g_draw_object_list.

draw_object_list is the roadside-object display-list dispatcher: two nested loops walk the per-frame
object list and dispatch each object through obj_type_jumptable to a fine-x blit engine / handler.
Each case stages a mid-race frame, runs recreate's g_draw_object_list for each of draw_game_objects'
real passes (the two sprite passes split at the active-slot count, then the fixed-object pass) as the
reference and the remaster dispatcher on the same background, and asserts the whole framebuffer is
byte-identical.

The remaster dispatcher is pointer-independent (arena pointers + arena-relative cursors); the harness
drives it on a view of recreate's flat image (every arena pointer = the image base) so the exact
per-frame streams/records/jump-table are exercised — see equiv.compare_object_list.
"""
import equiv
import pytest

# Frames spanning the legs / warmups where the object passes draw a variety of handlers (probed to
# each contribute hundreds-to-thousands of object-list bytes).
CASES = [(0, 60), (1, 90), (2, 120), (3, 120), (4, 60), (4, 90)]


@pytest.mark.parametrize("leg,warmup", CASES)
def test_draw_object_list_matches(leg, warmup, capsys):
    lib = equiv._lib()
    image = equiv.object_background(leg=leg, warmup=warmup)
    diff, footprint = equiv.compare_object_list(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup}: footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_object_list drew nothing (leg={leg}, warmup={warmup})"
    assert diff == 0, f"draw_object_list differs from recreate in {diff} bytes (leg={leg}, warmup={warmup})"
