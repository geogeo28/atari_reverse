"""The DESKTOP.INF field helpers — `src/aes/infscan.c`: hex_dig $fdaf20, uhex_dig $fdaf5c, scan_2 $fdaf92, save_2
$fdafca, shared by the AES's `#E` reader (gem_read_inf_E $fda408) and the desk's INF parser and writer.

    hex_dig(c)          '0'-'9' -> 0-9, 'A'-'F' -> 10-15, else 0     (a SIGNED BYTE: `cmp.b`)
    uhex_dig(d)         0-9 -> '0'-'9', 10-15 -> 'A'-'F', else ' '   (a SIGNED WORD)
    scan_2(p, &v)       v = hex_dig(p[0]) << 4 | hex_dig(p[1]), "ff" as -1; D0.l = p + 3 (the separator skipped unread)
    save_2(p, v)        p[0..2] = the low byte's two digits and ' '; D0.l = p + 3

Alcyon C (masked Line-F returns: d7 alone, d7/a4/a5 — the mask word is stored, dropped by name). Seeded with the
snapshot's own INF text — the shell's copy of DESKTOP.INF, whose `#E` line gem_read_inf_E reads with scan_2 and
writes back with save_2, and whose `#M` lines carry the unset field "FF".
"""
import pytest

from harness import BASE_IMAGE

import aes
import case
import vdi
from case import merge_pokes

HEX_DIG, UHEX_DIG = "AES_ROM_HEX_DIG", "AES_ROM_UHEX_DIG"
SCAN_2, SAVE_2 = "AES_ROM_SCAN_2", "AES_ROM_SAVE_2"
aes.declare_alcyon(HEX_DIG, aes.WORD_ANSWER, (vdi.WORD_ARG,))
aes.declare_alcyon(UHEX_DIG, aes.WORD_ANSWER, (vdi.WORD_ARG,))
aes.declare_alcyon(SCAN_2, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG))
aes.declare_alcyon(SAVE_2, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG))

# THE SNAPSHOT'S INF TEXT: the shell's copy of DESKTOP.INF. Its `#E` line's first field ("1B") and a `#M` line's
# fourth ("FF", the unset field).
INF_TEXT = BASE_IMAGE.find(b"#a000000", case.long_in(BASE_IMAGE, aes.AES_SHELL_BUFFER))
E_FIELD = BASE_IMAGE.find(b"#E ", INF_TEXT) + len(b"#E ")
UNSET_FIELD = BASE_IMAGE.find(b"FF ", BASE_IMAGE.find(b"#M ", INF_TEXT))
FIELD_BYTES = 3                                  # two digits and the separator
TEXT_AT = aes.BLOCKS_AT                          # a staged field
VALUE_AT = aes.RECTS_AT                          # scan_2's answer word, staged STALE
STALE_VALUE = aes.field_pokes("GRECT", VALUE_AT, X=aes.STALE_WORD)


def hex_value(character):
    byte = int.from_bytes(bytes([character & 0xFF]), "big", signed=True)
    if ord("0") <= byte <= ord("9"):
        return byte - ord("0")
    if ord("A") <= byte <= ord("F"):
        return byte - ord("A") + 10
    return 0


def hex_digit(value):
    value = aes.signed(value)
    return ord("0123456789ABCDEF"[value]) if 0 <= value <= 15 else ord(" ")


# ---- the digits ---------------------------------------------------------------------------------------------------
# Both sides of every range edge, lower case (not a digit here), and the high byte / sign cases.
CHARACTERS = (ord("0"), ord("9"), ord("0") - 1, ord("9") + 1, ord("A"), ord("F"), ord("A") - 1, ord("G"), ord("a"),
              ord("f"), 0x00, 0xB0, 0x7F, 0x0141, 0xFF39)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("character", CHARACTERS, ids=hex)
def test_hex_dig(character, through_line_f):
    """Only the LOW BYTE counts ($0141 is 'A'), compared signed: $b0 is negative, not a digit."""
    result = aes.run_function(HEX_DIG, (character,), aes.leaf_machine(), through_line_f=through_line_f)
    assert result.answer() == hex_value(character)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("digit", (0, 9, 10, 15, 16, -1, 0x7FFF, -0x8000, 0x0105), ids=hex)
def test_uhex_dig(digit, through_line_f):
    """A signed WORD: -1 and $8000 are no digit, and $0105 is not 5."""
    result = aes.run_function(UHEX_DIG, (digit,), aes.leaf_machine(), through_line_f=through_line_f)
    assert result.answer() == hex_digit(digit)


# ---- scan_2 -------------------------------------------------------------------------------------------------------

def scan(cursor, pokes=None, *, value_at=VALUE_AT, **kwargs):
    return aes.run_function(SCAN_2, (cursor, value_at), aes.leaf_machine(onto=merge_pokes(STALE_VALUE, pokes)),
                            **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_scan_2_reads_the_snapshot_s_e_field(through_line_f):
    result = scan(E_FIELD, through_line_f=through_line_f)
    assert result.word(VALUE_AT) == int(bytes(BASE_IMAGE[E_FIELD:E_FIELD + 2]), 16)
    assert result.info["regs"]["d0"] == E_FIELD + FIELD_BYTES


def test_scan_2_answers_the_unset_field_as_minus_one():
    """A `#M` line's "FF": 255 is the unset marker, stored as -1."""
    assert scan(UNSET_FIELD).word(VALUE_AT) == 0xFFFF


@pytest.mark.parametrize("text", (b"fe ", b"0F ", b"F0 ", b"zz ", b"FE\x00"), ids=repr)
def test_scan_2_over_staged_fields(text):
    """Lower case reads as 0 digits ("fe" is 0), "FE" is 254 — one short of the unset marker."""
    result = scan(TEXT_AT, {TEXT_AT: text})
    value = hex_value(text[0]) << 4 | hex_value(text[1])
    assert result.word(VALUE_AT) == (0xFFFF if value == 0xFF else value)


def test_scan_2_s_answer_word_over_its_own_text():
    """The answer word laid over the field it reads: both digits are read before the store."""
    result = scan(TEXT_AT, {TEXT_AT: b"4C "}, value_at=TEXT_AT)
    assert result.word(TEXT_AT) == 0x4C


def test_scan_2_keeps_the_cursor_s_top_byte_and_puts_both_pointers_on_the_bus():
    """The answer is the cursor as the register holds it, top byte and all; the reads and the store go through 24
    bits."""
    result = scan(E_FIELD | aes.BUS_TAG, value_at=VALUE_AT | aes.BUS_TAG)
    assert result.word(VALUE_AT) == int(bytes(BASE_IMAGE[E_FIELD:E_FIELD + 2]), 16)
    assert result.info["regs"]["d0"] == (E_FIELD | aes.BUS_TAG) + FIELD_BYTES


# ---- save_2 -------------------------------------------------------------------------------------------------------

def save(cursor, value, pokes=None, **kwargs):
    stale = {TEXT_AT: bytes([0xA5] * FIELD_BYTES)}
    return aes.run_function(SAVE_2, (cursor, value), aes.leaf_machine(onto=merge_pokes(stale, pokes)), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("value", (0x1B, 0x00, 0xFF, 0xA9, 0x1234, 0xFFFF), ids=hex)
def test_save_2_writes_the_low_byte_s_two_digits_and_the_separator(value, through_line_f):
    result = save(TEXT_AT, value, through_line_f=through_line_f)
    assert result.after(TEXT_AT, FIELD_BYTES) == bytes((hex_digit(value >> 4 & 15), hex_digit(value & 15), ord(" ")))
    assert result.info["regs"]["d0"] == TEXT_AT + FIELD_BYTES


def test_save_2_writes_back_the_snapshot_s_e_field():
    """What gem_read_inf_E does with the `#E` field: its value written over it."""
    result = save(E_FIELD, 0x2A)
    assert result.after(E_FIELD, FIELD_BYTES) == b"2A "


def test_save_2_keeps_the_cursor_s_top_byte_and_puts_it_on_the_bus():
    result = save(TEXT_AT | aes.BUS_TAG, 0x5C)
    assert result.after(TEXT_AT, FIELD_BYTES) == b"5C "
    assert result.info["regs"]["d0"] == (TEXT_AT | aes.BUS_TAG) + FIELD_BYTES


# ---- the registry: the worst realistic rows (every arm's last compare) priced, one of each through Line-F ---------
for _character in (ord("F"), ord("9"), ord("a")):
    aes.register(f"{chr(_character)!r}", HEX_DIG, (_character,), aes.leaf_machine())
aes.register("'F'", HEX_DIG, (ord("F"),), aes.leaf_machine(), through_line_f=True)
for _digit in (9, 15, 16):
    aes.register(f"{_digit}", UHEX_DIG, (_digit,), aes.leaf_machine())
aes.register("15", UHEX_DIG, (15,), aes.leaf_machine(), through_line_f=True)
aes.register("the snapshot's #E field", SCAN_2, (E_FIELD, VALUE_AT), aes.leaf_machine(onto=STALE_VALUE))
aes.register("the unset field", SCAN_2, (UNSET_FIELD, VALUE_AT), aes.leaf_machine(onto=STALE_VALUE))
aes.register("the snapshot's #E field", SCAN_2, (E_FIELD, VALUE_AT), aes.leaf_machine(onto=STALE_VALUE),
             through_line_f=True)
aes.register("the #E field written back", SAVE_2, (E_FIELD, 0x2A), aes.leaf_machine())
aes.register("letter digits", SAVE_2, (TEXT_AT, 0xAF), aes.leaf_machine())
aes.register("letter digits", SAVE_2, (TEXT_AT, 0xAF), aes.leaf_machine(), through_line_f=True)
