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


# Two spellings of a constant value: an integer literal, and the single-bit shift the flag-bit
# macros use. The shift form was invisible until OBJ_FLAG_REMOVED was found defined as `(1u << 12)`
# in world.h and `(1u << 13)` in egg.h — same name, different bits, and neither the duplicate pin
# below nor the compiler (no translation unit includes both headers) could see it.
# The trailing lookahead makes the value the WHOLE definition: a compound expression that merely
# starts with one of these two forms — `(1u << 6) | (1u << 11)`, `0x10 + BAR` — stays invisible
# rather than being half-read into a plausible wrong number.
_DEFINE_RE = re.compile(r"^#define\s+(?P<name>\w+)\s+(?:"
                        r"(?P<literal>0[xX][0-9a-fA-F]+|\d+)[uU]?"
                        r"|\(\s*1[uU]?\s*<<\s*(?P<bit>\d+)\s*\)"
                        r")(?=\s*(?:/[/*]|$))", re.M)


def _iter_defines(path):
    """(name, value, is_shift) for every define `_DEFINE_RE` can read, in file order.

    `is_shift` tells the `(1u << N)` spelling from the literal one, which is how the value-collision
    pin below recognises a flag bit that carries no `_FLAG_` in its name.
    """
    text = (REC / path).read_text()
    for m in _DEFINE_RE.finditer(text):
        yield (m["name"],
               int(m["literal"], 0) if m["literal"] else 1 << int(m["bit"]),
               m["bit"] is not None)


def _defines(path):
    """{name: value} for every `#define NAME <integer literal>` or `#define NAME (1u << N)`.

    Still out of reach, deliberately: a value built from other macros or from arithmetic
    (`RNG_PTR_RESET IMAGE_LOAD_BASE`, `TROLL_X_WRAP (SCREEN_ROW_BYTES / CELL_BYTES * CELL_PIXELS)`,
    `PTERO_SPOT_X_NEAR ((int16_t)8)`). Evaluating those would mean resolving one header's macros
    against another's, which is a C preprocessor, not a scraper — the tests that mirror them pin
    the derivation instead (see test_world.py's TROLL_X_WRAP assertion).

    Include guards need no exclusion list and never will: `#define JOUST_DRAW_H` has no value, so
    neither branch matches it.
    """
    return {name: value for name, value, _ in _iter_defines(path)}


def _all_sources():
    """This reconstruction's headers and translation units, relative to its root.

    Globbed, not enumerated, so a file added after this was written is covered the moment it exists.
    Not the kit's own headers (`tools/recreate_kit/include/`), which every TU also compiles against;
    test_input.py scrapes those by path where it needs them.
    """
    return [str(path.relative_to(REC))
            for path in sorted(list((REC / "include").glob("*.h")) + list((REC / "src").glob("*.c")))]


def _comparable_group(name, is_shift):
    """What this constant's VALUE may be compared against, or None to leave it out of the pin.

    Only two families are unambiguous enough that a shared value is always a defect:

    * ADDRESSES — `A_*` is this reconstruction's spelling for an absolute Ghidra address, and one
      address is one global, so a second `A_*` name for it is a second spelling of the same
      variable. `A_..._END` is the exception, and a structural one rather than a suppressed case: an
      exclusive bound's value is BY CONSTRUCTION whatever sits next in memory, which the headers
      already document (`A_object_table_END` == `A_effect_table`, `A_spawn_points_END` ==
      `A_egg_bonus_table`). Bounds are therefore compared only against other bounds, where a shared
      value would again be two names for one thing.
    * FLAG BITS — a `(1u << N)`, or a `_FLAG_` name that spells its bit as a literal
      (`OBJ_FLAG_IN_LAVA 0x0100u`). These must be unique within the WORD they live in, and the first
      two name components say which word that is: `OBJ_FLAG_*` the object record's flags,
      `PT_FLAG_*` the pterodactyl's, `EGG_SPAWN_*` the egg's spawn byte, `PSG_MIXER_*` one
      sound-chip register. TWO components, not one, because a record can own more than one bitfield
      — `PSG_MIXER_TONE_A` and a later `PSG_ENV_HOLD` are both bit 0 of DIFFERENT registers, and
      grouping on `PSG_` alone would report that as a defect. The cost is one admitted miss: a
      second spelling that also drops the field component (`OBJ_BUMP_PLATFORM` beside
      `OBJ_FLAG_PLATFORM_BUMP`) lands in a group of its own — but that name is already
      off-convention, which review catches.

    Everything else — record offsets, timers, speeds, sprite geometry — is out of reach on purpose,
    because for those a shared value carries no information: `OBJ_FLAGS` and `PT_FLAGS` are both
    offset 0 and both right, and within EGG_ alone seven unrelated constants are legitimately 2 (a
    spawn type, a sweep's first slot, a hit-box width, three x/y biases and a mount bias).

    So there is no exclusion list and nothing to exclude: a constant is either in one of the two
    families or invisible here.
    """
    if name.startswith("A_"):                       # ../../names.txt's globals, as Ghidra addresses
        return "an exclusive bound" if name.endswith("_END") else "an absolute address"
    if is_shift or "_FLAG_" in name:
        return f"a bit of {'_'.join(name.split('_')[:2])}"
    return None


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

    It catches a same-name/same-value duplicate and a same-name/DIFFERENT-value one alike, which is
    the case that matters: OBJ_FLAG_REMOVED was `(1u << 12)` in world.h and `(1u << 13)` in egg.h,
    two different bits under one name, and each file compiled happily against its own.

    Reach: whatever `_defines` cannot read, this cannot check — a macro whose value is arithmetic or
    another macro is still invisible here (see that function's docstring). Include guards fall out
    for free rather than by an exclusion list, so nothing is suppressed: a hit is a real duplicate.

    Blind, BY CONSTRUCTION, to the inverse defect — one value under two names — because it keys on
    the name. test_no_value_has_two_spellings below is that half.
    """
    files_by_constant = {}
    for rel in _all_sources():
        for name in _defines(rel):
            files_by_constant.setdefault(name, []).append(rel)

    duplicated = {name: files for name, files in files_by_constant.items() if len(files) > 1}
    assert not duplicated, "constants defined in more than one file — hoist each to a shared header:\n" + \
        "\n".join(f"  {name}: {', '.join(files)}" for name, files in sorted(duplicated.items()))


def test_no_value_has_two_spellings():
    """The inverse of the pin above: one address, or one flag bit, under two names.

    Nothing else can see this class. The compiler cannot, because no translation unit includes both
    headers of any pair; the name-keyed pin cannot, because the names differ by definition. Four
    instances had accumulated by the time it was written — `A_respawn_lock` (render.h) and
    `A_spawn_in_progress` (wave.h) both 0x10d13; `A_chasers_p1` (objects.h) and `A_hunter_counts`
    (wave.h) both 0x10d5e; bits 0-1 of the object flags word spelled `OBJ_FLAG_TYPE_LO`/`_HI` in
    collide.h and `OBJ_FLAG_TYPE_BIT0`/`_BIT1` in render.h; and bit 14 spelled
    `OBJ_FLAG_PLATFORM_BUMP` by the routine that sets it and `OBJ_FLAG_EDGE_BUMP` by the one that
    reads it. Each was one layer inventing a name for something another layer had already named.

    `_comparable_group` is where the judgement lives: it decides which constants are even comparable
    by value, and its docstring says what is out of scope and why.
    """
    names_by_value = {}
    for rel in _all_sources():
        for name, value, is_shift in _iter_defines(rel):
            group = _comparable_group(name, is_shift)
            if group is None:
                continue
            names_by_value.setdefault((group, value), []).append(f"{name} ({rel})")

    collisions = {key: names for key, names in names_by_value.items() if len(names) > 1}
    assert not collisions, \
        "one value under two names — keep the spelling the instructions justify, hoist it to the " \
        "header both layers include, and delete the other:\n" + \
        "\n".join(f"  {value:#x} as {group}: {', '.join(sorted(names))}"
                  for (group, value), names in sorted(collisions.items()))
