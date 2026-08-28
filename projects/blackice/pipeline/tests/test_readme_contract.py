"""README.md is the contract the C engine is written against, so its byte tables are tested
like code. Hand-typed tables go stale silently; these assertions make staleness a failure."""
import re
from pathlib import Path

import pytest

from stepix.demo_assets import build_demo_assets, build_demo_palette
from stepix.font import FONT_BYTES
from stepix.pack import (METHOD_LZSS, METHOD_STORED, PAK_ALIGNMENT, PAK_ENTRY_BYTES,
                         PAK_FORMAT_VERSION, PAK_HEADER_BYTES, PAK_MAGIC, PAK_NAME_BYTES)
from stepix.palette import PALETTE_SIZE, ste_word
from stepix.planar import PI1_BYTES, SCREEN_BYTES, SCREEN_ROW_BYTES
from stepix.sprite import (SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST, SPRITE_RECORD_BYTES,
                           TRANSPARENT_INDEX)
from stepix.texture import TEXTURE_BYTES, TEXTURE_ENTRY_BYTES, TEXTURE_HEADER_BYTES

PIPELINE_DIR = Path(__file__).resolve().parent.parent
ENGINE_INCLUDE_DIR = PIPELINE_DIR.parent / "include"
README = (PIPELINE_DIR / "README.md").read_text()

DEFINE = re.compile(r"^#define\s+(\w+)\s+(\S+)", re.MULTILINE)


def _defines(path: Path) -> dict[str, str]:
    """Object-like `#define NAME value` pairs from a C header, as raw text."""
    return dict(DEFINE.findall(path.read_text()))

# The swizzle examples quoted in section 1, re-derived here from the documented rule.
QUOTED_SWIZZLE = {(15, 15, 15): "$0FFF", (14, 14, 14): "$0777", (8, 8, 8): "$0444",
                  (1, 0, 0): "$0800", (7, 0, 0): "$0B00", (2, 4, 6): "$0123", (0, 0, 0): "$0000"}


@pytest.mark.parametrize("rgb,quoted", sorted(QUOTED_SWIZZLE.items()))
def test_quoted_palette_words_are_correct_and_present(rgb, quoted):
    assert f"`{quoted}`" in README, f"README no longer quotes {quoted}"
    assert ste_word(*rgb) == int(quoted.lstrip("$"), 16)


# Section 8 lays two (index, word) pairs per row: "| 0 | `$0008` | ... | 8 | `$0E7F` | ...".
PALETTE_TABLE_CELL = re.compile(r"\|\s*(\d{1,2})\s*\|\s*`\$([0-9A-F]{4})`")


def test_quoted_demo_palette_table_matches_the_generated_palette():
    """Parsed as (index, word) rows: checking only that each word appears SOMEWHERE let two
    entries swap rows, or land under the wrong index, without the test noticing."""
    documented = {int(index): int(word, 16) for index, word in PALETTE_TABLE_CELL.findall(README)}
    assert sorted(documented) == list(range(PALETTE_SIZE)), sorted(documented)
    assert [documented[index] for index in range(PALETTE_SIZE)] == build_demo_palette().to_words()


def test_quoted_shade_table_matches_the_generated_one():
    quoted = re.search(r"^((?:[0-9a-f]{2} ){15}[0-9a-f]{2})$", README, re.MULTILINE)
    assert quoted, "README no longer carries the demo shade table"
    assert bytes(int(byte, 16) for byte in quoted.group(1).split()) == build_demo_assets().shade_table


# Each size the engine allocates against, tied to the sentence or table cell that documents
# it. A bare `str(value) in README` cannot fail for a small number -- "16" and "160" appear
# all over the document, so that form passed no matter what the constants said.
SIZE_ANCHORS = [
    (SCREEN_ROW_BYTES, "**{value} bytes per row"),
    (SCREEN_BYTES, "{value:,} bytes per screen**"),
    (PI1_BYTES, "uncompressed) — {value:,} bytes"),
    (TEXTURE_BYTES, "`offset + {value}`"),
    (SPRITE_RECORD_BYTES, "Record ({value:,} bytes)"),
    (FONT_BYTES, "`FONT`, {value} bytes"),
    (PALETTE_SIZE, "| {value} palette words"),
]


@pytest.mark.parametrize("value,anchor", SIZE_ANCHORS)
def test_documented_sizes_are_in_the_cell_that_documents_them(value, anchor):
    quoted = anchor.format(value=value)
    assert quoted in README, f"README no longer documents {value} as {quoted!r}"


def test_quoted_header_and_entry_sizes():
    assert "| 12     | 12·n |" in README                      # texture entry table
    assert "| 8      | 24·n | directory" in README            # pak directory
    assert TEXTURE_HEADER_BYTES == 12 and TEXTURE_ENTRY_BYTES == 12
    assert PAK_HEADER_BYTES == 8 and PAK_ENTRY_BYTES == 24


# ---- the C side of the contract ------------------------------------------------------
# depack.h restates the PAK layout for the engine. Restated constants drift; these pin them.
PAK_CONSTANTS = {
    "PAK_MAGIC": PAK_MAGIC,
    "PAK_FORMAT_VERSION": PAK_FORMAT_VERSION,
    "PAK_NAME_BYTES": PAK_NAME_BYTES,
    "PAK_HEADER_BYTES": PAK_HEADER_BYTES,
    "PAK_ENTRY_BYTES": PAK_ENTRY_BYTES,
    "PAK_ALIGNMENT": PAK_ALIGNMENT,
    "PAK_METHOD_STORED": METHOD_STORED,
    "PAK_METHOD_LZSS": METHOD_LZSS,
}
DEPACK_H_DEFINES = _defines(PIPELINE_DIR / "depack.h")


@pytest.mark.parametrize("name,expected", sorted(PAK_CONSTANTS.items()))
def test_depack_h_pak_constants_match_stepix_pack(name, expected):
    assert name in DEPACK_H_DEFINES, f"depack.h no longer defines {name}"
    literal = DEPACK_H_DEFINES[name]
    value = literal.strip('"').encode("ascii") if literal.startswith('"') else int(literal, 0)
    assert value == expected


def test_every_pak_constant_in_depack_h_is_pinned():
    """A new PAK_* define on the C side must be added to PAK_CONSTANTS, not left unchecked."""
    assert {name for name in DEPACK_H_DEFINES if name.startswith("PAK_")} == set(PAK_CONSTANTS)


# The engine's own headers restate the sprite conventions this pipeline writes. The pipeline
# is the producer, so these are pinned here rather than left to agree by inspection.
ENGINE_SPRITE_CONSTANTS = {
    "SPRITE_SPAN_EMPTY_FIRST": SPAN_EMPTY_FIRST,
    "SPRITE_SPAN_EMPTY_LAST": SPAN_EMPTY_LAST,
    "SPRITE_TRANSPARENT": TRANSPARENT_INDEX,
}
ENGINE_HEADERS = ("sprite.h", "game_consts.h")


@pytest.mark.parametrize("name,expected", sorted(ENGINE_SPRITE_CONSTANTS.items()))
def test_engine_headers_agree_with_the_sprite_codec(name, expected):
    missing = [header for header in ENGINE_HEADERS if not (ENGINE_INCLUDE_DIR / header).is_file()]
    if missing:
        pytest.xfail(f"engine headers not present yet: {', '.join(missing)}")
    defined: dict[str, str] = {}
    for header in ENGINE_HEADERS:
        defined.update(_defines(ENGINE_INCLUDE_DIR / header))
    assert name in defined, f"the engine headers no longer define {name}"
    assert int(defined[name], 0) == expected
