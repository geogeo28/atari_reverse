"""test_assets.py — remaster loads the original data files itself, byte-for-byte.

Every other remaster test is fed assets by the adapter, which slices named windows out of a staged
recreate image. This one closes that loop: the remaster reads the *unmodified* `COURSES.DAT` and
`GRAPHICS.GRA` into its own arena and unpacks them with its own C, and we assert the resulting
arena is byte-identical to what recreate's verified `g_unpack_graphics` produces from the same two
files. Green here means the shipped game needs no baked asset blob — the files ARE the assets.

The comparison surface is the whole 0x5ee08-byte arena, not a sampled region, so a divergence in
any phase (RLE decode, screen de-interleave, compaction, the tail slide, either sprite pre-shift
table build) fails it.
"""
import assets_load as al
import pytest
import render_screen as R                          # recreate's staging + arena layout constants


def _recreate_arena():
    """recreate's verified g_unpack_graphics over the same two files — the reference."""
    image, _ = R._prepared_image({})
    return bytes(image[R.MEM_BASE:R.MEM_BASE + al.RM_ARENA_BYTES])


def test_arena_layout_matches_recreate():
    """The arena offsets are dictated by the data files; pin ours to recreate's."""
    assert al.RM_COURSE_OFF == 0
    assert al.RM_TABLES_OFF == R.BUF_A - R.MEM_BASE
    assert al.RM_SCRATCH_OFF == R.BUF_B - R.MEM_BASE
    assert al.RM_GFX_OFF == R.BUF_C - R.MEM_BASE
    assert al.RM_AUX_OFF == R.BUF_AUX - R.MEM_BASE
    assert al.RM_GFX_LOAD_OFF == R.GFX_LOAD_OFFSET


def test_course_file_loads_verbatim():
    """COURSES.DAT needs no unpacking, and nothing in the graphics unpack may tread on it."""
    courses = (al.DATA_DIR / "COURSES.DAT").read_bytes()
    assert al.fresh_arena()[:len(courses)] == courses


def test_unpacked_arena_is_byte_identical(capsys):
    candidate = al.fresh_arena()
    reference = _recreate_arena()
    assert len(candidate) == len(reference) == al.RM_ARENA_BYTES

    wrong = sum(1 for a, b in zip(candidate, reference) if a != b)
    # Guard against a vacuous pass: the unpack must actually fill the arena.
    filled = sum(1 for b in reference if b)
    with capsys.disabled():
        print(f"  arena {al.RM_ARENA_BYTES} bytes, {filled} non-zero, {wrong} differing")
    assert filled > al.RM_ARENA_BYTES // 2, "reference arena looks empty — staging is broken"
    assert wrong == 0, f"remaster's unpack diverges from recreate on {wrong} bytes"


@pytest.mark.parametrize("region,off,length", [
    ("graphics", al.RM_GFX_OFF, 0x3B000),            # the sprite arena the object blits index
    ("sprite shift tables", al.RM_SCRATCH_OFF, 0xD000),   # 208 sprites x 16 shifts x 16 bytes
    ("course tables", al.RM_TABLES_OFF, 0x2000),     # scroll/object selectors + record descriptors
])
def test_region_matches_recreate(region, off, length):
    """Spot the named regions individually, so a failure names the phase that broke it."""
    assert al.fresh_arena()[off:off + length] == _recreate_arena()[off:off + length], \
        f"{region} region differs"
