"""The header scraper (``test/layout.py``) that every other case here reads its constants through.

``include/wonderboy.h`` is the canonical definition of this project's layout constants and
``layout.py`` scrapes it so Python restates none of them (CLAUDE.md §5). Everything the rest of the
suite asserts is therefore only as good as the scrape, and until now nothing tested it: a constant
misread as a plausible wrong number would make a whole battery agree with itself.

The cases run ``_scrape`` on synthetic header text rather than on the real header, so they pin what
the scraper DOES rather than what this game's header happens to contain.
"""
import pytest

import layout
from layout import wb


def test_it_reads_the_forms_the_header_uses():
    """Hex and decimal, with and without the C unsigned suffix, with and without a comment."""
    scraped = layout._scrape(
        "#define WB_HEX     0x214d8u  /* a trailing block comment */\n"
        "#define WB_DEC     16\n"
        "#define WB_SUFFIX  3u\n"
        "#define WB_LINE_COMMENT 0x400 // a trailing line comment\n")
    assert scraped == {"WB_HEX": 0x214d8, "WB_DEC": 16, "WB_SUFFIX": 3, "WB_LINE_COMMENT": 0x400}


def test_a_compound_definition_is_skipped_rather_than_half_read():
    """`WB_BODY_LEN 0x84f6 * 4` must not come back as 0x84f6 — the whole point of the lookahead."""
    assert layout._scrape("#define WB_COMPOUND 0x84f6 * 4\n") == {}


def test_a_duplicate_define_is_refused_and_names_the_header():
    """Taking the last silently would make "which value is canonical" depend on file order."""
    with pytest.raises(ValueError) as excinfo:
        layout._scrape("#define WB_TWICE 1\n#define WB_TWICE 2\n")
    message = str(excinfo.value)
    assert str(layout._HEADER) in message, "the diagnostic must name the file to edit"
    assert "WB_TWICE" in message


def test_a_leading_zero_decimal_is_refused_and_names_the_header():
    """C reads `010` as octal 8 and Python's int(_, 0) refuses it — so the two cannot agree, and
    the old scraper died on it with a bare ValueError naming neither the header nor the constant."""
    with pytest.raises(ValueError) as excinfo:
        layout._scrape("#define WB_OCTALISH 010\n")
    message = str(excinfo.value)
    assert str(layout._HEADER) in message, "the diagnostic must name the file to edit"
    assert "WB_OCTALISH" in message


def test_wb_names_the_constant_it_could_not_find():
    with pytest.raises(AssertionError, match="WB_NOT_A_REAL_CONSTANT"):
        wb("NOT_A_REAL_CONSTANT")


def test_the_real_header_scrapes_and_wb_reaches_it():
    """One case against include/wonderboy.h itself, so a header that stopped parsing fails here
    rather than as a puzzling missing key in test_bootstrap.py."""
    assert layout.DEFINES, f"nothing scraped out of {layout._HEADER}"
    assert wb("RUNTIME_BASE") == 0x400
