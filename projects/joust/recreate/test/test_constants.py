"""Pin the test suite's mirrored constants to their single sources of truth.

The differential tests restate values that really live somewhere else — entry and global addresses
that belong to `../names.txt`, and screen geometry / stack-frame offsets that belong to the C in
`include/` and `src/`. Python cannot import either, so CLAUDE.md's rule applies: pick one canonical
definition and pin the copy equal with a test. A drift on either side fails with the name of the
constant, instead of quietly weakening a battery.

This file covers the small batteries (test_blit / test_fill / test_rng / test_screen). test_draw.py
and test_object.py mirror far more and each carries its OWN pin section, next to the constants it
restates, importing `_defines` from here rather than copying it. So this file is not the whole
inventory — check those two as well before adding a pin.
"""
import re
from pathlib import Path

import harness
import test_blit
import test_fill
import test_rng
import test_screen

REC = Path(__file__).resolve().parents[1]


def _defines(path):
    """{name: value} for every simple `#define NAME <integer literal>` in a C source or header."""
    text = (REC / path).read_text()
    return {m.group(1): int(m.group(2), 0)
            for m in re.finditer(r"^#define\s+(\w+)\s+(0[xX][0-9a-fA-F]+|\d+)u?\b", text, re.M)}


def test_entry_addresses_match_names_txt():
    """The entries THESE batteries use are the addresses names.txt gives those functions.

    Not every entry in the suite: test_draw.py and test_object.py pin their own (see the module
    docstring), so adding one here for a function they cover would be a second copy, not a check.
    """
    expected = {
        test_fill.ENTRY_MAKE_FILL_PATTERN: "make_fill_pattern",
        test_fill.ENTRY_FILL_PATTERN_N: "fill_pattern_n",
        test_rng.ENTRY_RNG_ADVANCE: "rng_advance",
        test_screen.ENTRY_POS_TO_SCREEN: "pos_to_screen",
        test_screen.ENTRY_SCREEN_TO_POS: "screen_to_pos",
        **{addr: name for name, addr in test_blit.BLITS.items()},
    }
    for addr, name in expected.items():
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_global_addresses_match_names_txt_and_addrs_h():
    """screen_base / rng_ptr: the tests, include/addrs.h and names.txt must all agree."""
    addrs_h = _defines("include/addrs.h")
    for c_name, txt_name, from_test in (("A_screen_base", "screen_base", test_screen.A_SCREEN_BASE),
                                        ("A_rng_ptr", "rng_ptr", test_rng.A_RNG_PTR)):
        assert addrs_h[c_name] == from_test, f"{c_name} differs from the test's mirror"
        assert harness.NAME_MAP.get(from_test) == txt_name, f"names.txt has no `{txt_name}`"


def test_screen_geometry_matches_the_c():
    joust_h = _defines("include/joust.h")
    assert joust_h["CELL_BYTES"] == test_blit.CELL_BYTES == test_fill.CELL_BYTES
    assert joust_h["CELL_BYTES"] == test_screen.CELL_BYTES
    assert joust_h["SCREEN_ROW_BYTES"] == test_blit.SCREEN_ROW_BYTES


def test_argument_block_offsets_match_the_glue():
    """The frames the tests pack must be the frames the glue unpacks (and the original reads)."""
    blit_c, screen_c = _defines("src/blit.c"), _defines("src/screen.c")
    assert (blit_c["BLIT_ARG_DST"], blit_c["BLIT_ARG_SRC"],
            blit_c["BLIT_ARG_COLS"], blit_c["BLIT_ARG_ROWS"]) == (0, 4, 8, 10), \
        "test_blit packs the argument block as `>IIHH` at these offsets"
    assert (screen_c["POS_ARG_ADDR"], screen_c["POS_ARG_SHIFT"],
            screen_c["POS_ARG_X"], screen_c["POS_ARG_Y"]) == \
        (test_screen.ARG_ADDR, test_screen.ARG_SHIFT, test_screen.ARG_X, test_screen.ARG_Y)


def test_rng_constants_match_the_c():
    rng_c = _defines("src/rng.c")
    assert rng_c["RNG_PTR_LIMIT"] == test_rng.RNG_LIMIT
    assert _defines("include/addrs.h")["IMAGE_LOAD_BASE"] == test_rng.RNG_RESET


def test_screen_to_pos_x_scale_is_still_the_original_wrong_one():
    """The reconstruction must keep the shipped `mulu.w #$16` (22), not the 16 the inverse needs."""
    scale = _defines("src/screen.c")["SCREEN_TO_POS_X_SCALE"]
    assert scale == test_screen.ORIGINAL_X_SCALE == 0x16, f"x scale is {scale}, not the original 22"


def test_no_constant_is_defined_in_two_files():
    """Every `#define` name belongs to exactly one file across include/ and src/.

    draw.h and object.h once each defined the same nine addresses. No translation unit included
    both, so the compiler stayed silent — and would have stayed silent had one copy drifted. The
    values now live once in addrs.h / joust.h; this pin is what keeps them there as new headers land.

    The file list is globbed, not enumerated, so a header added after this was written is covered
    the moment it exists.

    Reach: `_defines` only sees `#define NAME <integer literal>`, so this cannot catch a duplicated
    macro whose value is an expression or another macro (`OBJ_FLAG_RESPAWN (1u << 7)`,
    `RNG_PTR_RESET IMAGE_LOAD_BASE`, `PTERO_SPOT_X_NEAR ((int16_t)8)`). That same restriction is
    why include guards need no exclusion list: `#define JOUST_DRAW_H` has no value and is never
    scraped. Nothing here is suppressed — a hit is always a real duplicate.
    """
    files_by_constant = {}
    for path in sorted(list((REC / "include").glob("*.h")) + list((REC / "src").glob("*.c"))):
        rel = path.relative_to(REC)
        for name in _defines(rel):
            files_by_constant.setdefault(name, []).append(str(rel))

    duplicated = {name: files for name, files in files_by_constant.items() if len(files) > 1}
    assert not duplicated, "constants defined in more than one file — hoist each to a shared header:\n" + \
        "\n".join(f"  {name}: {', '.join(files)}" for name, files in sorted(duplicated.items()))
