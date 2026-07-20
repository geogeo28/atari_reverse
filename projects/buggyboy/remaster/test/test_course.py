"""test_course.py — remaster course-advance equivalence vs recreate's game_update (section 12).

Driving forward scrolls the road segment window and pulls new slopes from the leg's packed course
stream, so the road's hills/curves follow the authored track. This drives several legs a number of
course-advance steps and asserts the remaster course-advance keeps the segment window + row_ctr /
read_pos byte-identical to recreate's g_game_update every frame — i.e. the geometry the renderer
consumes evolves identically as you drive. (The rendered frame equivalence for any given segment
window is covered by test_geometry / test_road.)
"""
import equiv
import pytest


@pytest.mark.parametrize("leg", [0, 1, 2, 4])
def test_course_advance_tracks_recreate(leg, capsys):
    lib = equiv._lib()
    image = equiv.road_background(leg=leg, warmup=30)
    mismatches = equiv.compare_course_drive(lib, image, frames=40)
    with capsys.disabled():
        print(f"  leg={leg}: {mismatches} mismatching frames / 40")
    assert mismatches == 0, f"course-advance diverged from recreate on {mismatches} frames (leg={leg})"
