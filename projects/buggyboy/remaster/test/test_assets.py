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
import re

import assets_load as al
import pytest
import render_screen as R                          # recreate's staging + arena layout constants

# Named arena regions, used to say WHERE a whole-arena mismatch landed. They are diagnostic only —
# a per-region assert could never fail independently of the whole-arena compare below.
REGIONS = [
    ("COURSES.DAT (loaded verbatim)", al.RM_COURSE_OFF, al.RM_TABLES_OFF),
    ("course tables", al.RM_TABLES_OFF, al.RM_SCRATCH_OFF),
    ("sprite shift tables (phases G/H)", al.RM_SCRATCH_OFF, al.RM_GFX_OFF),
    ("unpacked graphics (phases B-F)", al.RM_GFX_OFF, al.RM_AUX_OFF),
    ("header stash (phase A)", al.RM_AUX_OFF, al.RM_ARENA_BYTES),
]


def _region_of(off):
    return next((n for n, lo, hi in REGIONS if lo <= off < hi), "outside every named region")


@pytest.fixture(scope="module")
def candidate():
    """remaster's own loader over the unmodified data files — the candidate arena."""
    return al.fresh_arena()


@pytest.fixture(scope="module")
def reference():
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


def test_course_file_loads_verbatim(candidate):
    """COURSES.DAT needs no unpacking, and nothing in the graphics unpack may tread on it."""
    courses = (al.DATA_DIR / "COURSES.DAT").read_bytes()
    assert candidate[:len(courses)] == courses


def test_unpacked_arena_is_byte_identical(candidate, reference, capsys):
    assert len(candidate) == len(reference) == al.RM_ARENA_BYTES

    diff = [i for i, (a, b) in enumerate(zip(candidate, reference)) if a != b]
    # Guard against a vacuous pass: the unpack must actually fill the arena.
    filled = sum(1 for b in reference if b)
    with capsys.disabled():
        print(f"  arena {al.RM_ARENA_BYTES} bytes, {filled} non-zero, {len(diff)} differing")
    assert filled > al.RM_ARENA_BYTES // 2, "reference arena looks empty — staging is broken"
    if diff:
        first = diff[0]
        pytest.fail(f"unpack diverges from recreate on {len(diff)} bytes; first at {first:#x} "
                    f"in {_region_of(first)} "
                    f"(candidate {candidate[first]:#04x} vs reference {reference[first]:#04x})")


def test_python_constants_match_assets_h():
    """assets_load.py mirrors include/assets.h by hand; pin the copies equal (CLAUDE.md §5).

    RM_ARENA_BYTES especially: if the C grows and Python does not, the ctypes block under-allocates
    and rm_assets_unpack writes past it — heap corruption instead of a failed assert."""
    header = (al.adapter.REMASTER / "include" / "assets.h").read_text()
    defines = dict(re.findall(r"^#define\s+(RM_\w+)\s+(0x[0-9a-fA-F]+)\s*(?:/\*.*)?$", header, re.M))
    assert defines, "no RM_* literal defines found — has assets.h moved?"
    for name, literal in defines.items():
        mirrored = getattr(al, name, None)
        if mirrored is not None:
            assert mirrored == int(literal, 16), f"{name}: python {mirrored:#x} != assets.h {literal}"
    # RM_GFX_READ_MAX is computed in both places; check the arithmetic agrees.
    assert al.RM_GFX_READ_MAX == al.RM_ARENA_BYTES - al.RM_GFX_OFF - al.RM_GFX_LOAD_OFF
