"""AES utility layer, the STRINGS (`src/aes/strings.c`): strlen $fece8c, streq $fece9c, strcpy $feceb8, strscn $fecec4,
strcat $feceda, scasb $feceee, strchk $fecf02, fmt_str $fecf24 / unfmt_str $fecf58 (the 8.3 forms), merge_str $fed070
(the `%`-template) and wildcmp $fed12e.

Hand 68000 walking NUL-ended strings byte by byte; every string pointer is also handed in with a top byte
(`aes.BUS_TAG`), and every pointer a routine ANSWERS keeps it. The shapes are the directory names and the templates
the desk hands them, and each quirk of the ROM's own loops: fmt_str's unpadded dotless name and skipped ninth byte,
unfmt_str's bare dot, merge_str's slot per code (%W reads a slot's FIRST word), its signed %L through the Alcyon
runtime's ldiv — which leaves its last remainder in RAM ($8c3e) and answers $80000000 as "0" — and the read past a
template's NUL after a trailing `%`.
"""
import struct

import pytest

import aes
import aes_strings as strings
from aes import signed
from aes_strings import (ARGUMENT_STRINGS_AT, DESTINATION_AT, PARAMETERS_AT, SOURCE_AT, STALE_BYTE, TEMPLATE_AT, buffers,
                         run, stale, string_in, text)
from case import merge_pokes

TAG = aes.BUS_TAG
BYTE_BITS = 8


# ---- strlen $fece8c -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("string", (b"", b"A", b"DESKTOP.INF", bytes(range(1, 256)) * 2), ids=("empty", "one", "a name", "510"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_strlen_counts_to_the_nul(string, through_line_f):
    assert run("AES_ROM_STRLEN", (SOURCE_AT,), text(SOURCE_AT, string), through_line_f=through_line_f).answer() == len(string)


def test_strlen_on_the_24_bit_bus():
    assert run("AES_ROM_STRLEN", (SOURCE_AT | TAG,), text(SOURCE_AT, "four")).answer() == 4


# ---- streq $fece9c, strchk $fecf02 ---------------------------------------------------------------------------------
PAIRS = {
    "equal": (b"DESK.ACC", b"DESK.ACC"),
    "both empty": (b"", b""),
    "the first a prefix": (b"DESK", b"DESK.ACC"),
    "the second a prefix": (b"DESK.ACC", b"DESK"),
    "one byte differs": (b"DESK.ACC", b"DESK.ACD"),
    "the first empty": (b"", b"A"),
    "a byte from $80 up against a letter": (b"\x80", b"a"),
    "a letter against a byte from $80 up": (b"a", b"\xff"),
}


def pair_pokes(left, right):
    return merge_pokes(text(SOURCE_AT, left), text(DESTINATION_AT, right))


def strchk_model(left, right):
    for index, byte in enumerate(left + b"\0"):
        other = (right + b"\0")[index]
        if byte != other:
            return signed(byte, BYTE_BITS) - signed(other, BYTE_BITS)
        if byte == 0:
            return 0


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_streq_answers_equality(pair):
    left, right = PAIRS[pair]
    assert run("AES_ROM_STREQ", (SOURCE_AT, DESTINATION_AT), pair_pokes(left, right)).answer() == int(left == right)


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_strchk_answers_the_signed_byte_difference(pair):
    left, right = PAIRS[pair]
    assert run("AES_ROM_STRCHK", (SOURCE_AT, DESTINATION_AT), pair_pokes(left, right)).answer() == strchk_model(left, right)


@pytest.mark.parametrize("name", ("AES_ROM_STREQ", "AES_ROM_STRCHK"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_compares_on_the_24_bit_bus(name, through_line_f):
    run(name, (SOURCE_AT | TAG, DESTINATION_AT | TAG), pair_pokes(b"ABC", b"ABD"), through_line_f=through_line_f)


def test_streq_of_a_string_with_itself():
    assert run("AES_ROM_STREQ", (SOURCE_AT, SOURCE_AT), text(SOURCE_AT, "SAME")).answer() == 1


# ---- strcpy $feceb8, strcat $feceda, strscn $fecec4, scasb $feceee: the answered pointers ---------------------------------
@pytest.mark.parametrize("source", (b"", b"A:\\DESKTOP.INF"), ids=("empty", "a path"))
@pytest.mark.parametrize("tag", (0, TAG), ids=("plain", "on the 24-bit bus"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_strcpy_answers_the_destination_past_the_nul(source, tag, through_line_f):
    result = run("AES_ROM_STRCPY", (SOURCE_AT | tag, DESTINATION_AT | tag), buffers(source), through_line_f=through_line_f)
    assert result.after(DESTINATION_AT, len(source) + 2) == source + b"\0" + bytes([STALE_BYTE])
    assert result.info["regs"]["d0"] == (DESTINATION_AT | tag) + len(source) + 1


def test_strcpy_over_itself_one_byte_down():
    """The ORDER: each byte stored one below the one just read — the shift a path edit makes in place."""
    source = SOURCE_AT + 0x10
    result = run("AES_ROM_STRCPY", (source, source - 1), text(source, "\\FOLDER"))
    assert result.after(source - 1, 9) == b"\\FOLDER\0\0"


@pytest.mark.parametrize("destination", (b"", b"A:\\"), ids=("onto an empty string", "onto a drive"))
@pytest.mark.parametrize("tag", (0, TAG), ids=("plain", "on the 24-bit bus"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_strcat_appends_over_the_nul(destination, tag, through_line_f):
    source = b"*.*"
    result = run("AES_ROM_STRCAT", (SOURCE_AT | tag, DESTINATION_AT | tag), buffers(source, destination),
                 through_line_f=through_line_f)
    joined = destination + source
    assert result.after(DESTINATION_AT, len(joined) + 2) == joined + b"\0" + bytes([STALE_BYTE])
    assert result.info["regs"]["d0"] == (DESTINATION_AT | tag) + len(joined) + 1


STRSCN = {"up to the stop": (b"A:\\FOLDER\\NAME", ord("\\"), 2), "no stop: up to the NUL": (b"NAME.EXT", ord("*"), 8),
          "the stop first": (b"\\NAME", ord("\\"), 0), "a NUL stop is the NUL": (b"NAME", 0, 4),
          "empty": (b"", ord("."), 0)}


@pytest.mark.parametrize("shape", sorted(STRSCN))
def test_strscn_copies_up_to_the_stop_and_terminates_nothing(shape):
    source, stop, copied = STRSCN[shape]
    result = run("AES_ROM_STRSCN", (SOURCE_AT, DESTINATION_AT, stop), buffers(source))
    assert result.after(DESTINATION_AT, copied + 1) == source[:copied] + bytes([STALE_BYTE])
    assert result.info["regs"]["d0"] == DESTINATION_AT + copied


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_strscn_on_the_24_bit_bus(through_line_f):
    """...and the stop word's HIGH byte ignored: `move.b 13(sp)` reads the low one."""
    result = run("AES_ROM_STRSCN", (SOURCE_AT | TAG, DESTINATION_AT | TAG, 0x7F2E), buffers(b"DESK.INF"),
                 through_line_f=through_line_f)
    assert result.info["regs"]["d0"] == (DESTINATION_AT | TAG) + 4


SCASB = {"found": (b"DESK.INF", ord("."), 4), "not found: the NUL": (b"DESK", ord("."), 4),
         "the first byte": (b".INF", ord("."), 0), "a NUL byte": (b"DESK", 0, 4), "empty": (b"", ord("A"), 0),
         "the word's high byte ignored": (b"A:B", 0x413A, 1)}


@pytest.mark.parametrize("shape", sorted(SCASB))
def test_scasb_answers_the_byte_s_place_or_the_nul_s(shape):
    string, character, index = SCASB[shape]
    result = run("AES_ROM_SCASB", (SOURCE_AT, character), text(SOURCE_AT, string))
    assert result.info["regs"]["d0"] == SOURCE_AT + index


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_scasb_on_the_24_bit_bus(through_line_f):
    result = run("AES_ROM_SCASB", (SOURCE_AT | TAG, ord(":")), text(SOURCE_AT, "A:B"), through_line_f=through_line_f)
    assert result.info["regs"]["d0"] == (SOURCE_AT | TAG) + 1


# ---- fmt_str $fecf24 / unfmt_str $fecf58: the 8.3 forms ---------------------------------------------------------------
FMT_STR = {
    "a name and an extension": (b"DESK.INF", b"DESK    INF"),
    "one and one": (b"A.B", b"A       B"),
    "eight and three": (b"ABCDEFGH.EXT", b"ABCDEFGHEXT"),
    "no dot: copied unpadded": (b"NODOT", b"NODOT"),
    "nine bytes, no dot: the ninth skipped": (b"ABCDEFGHIJ", b"ABCDEFGHJ"),
    "a dot first": (b".X", b"        X"),
    "a dot and nothing after": (b"NAME.", b"NAME    "),
    "a long extension, copied whole": (b"NAME.EXTENSION", b"NAME    EXTENSION"),
    "empty": (b"", b""),
    "exactly eight": (b"ABCDEFGH", b"ABCDEFGH"),
}


@pytest.mark.parametrize("shape", sorted(FMT_STR))
def test_fmt_str_makes_the_8_3_form(shape):
    name, form = FMT_STR[shape]
    result = run("AES_ROM_FMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(name))
    assert result.after(DESTINATION_AT, len(form) + 2) == form + b"\0" + bytes([STALE_BYTE])


UNFMT_STR = {
    "a padded name": (b"DESK    INF", b"DESK.INF"),
    "eight and three": (b"ABCDEFGHEXT", b"ABCDEFGH.EXT"),
    "eight and nothing: a bare dot": (b"ABCDEFGH", b"ABCDEFGH."),
    "a NUL inside the eight: no dot": (b"AB", b"AB"),
    "spaces anywhere in the eight dropped": (b"A B C   D", b"ABC.D"),
    "spaces after the eight kept": (b"A       B C", b"A.B C"),
    "empty": (b"", b""),
}


@pytest.mark.parametrize("shape", sorted(UNFMT_STR))
def test_unfmt_str_makes_the_name_back(shape):
    form, name = UNFMT_STR[shape]
    result = run("AES_ROM_UNFMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(form))
    assert result.after(DESTINATION_AT, len(name) + 2) == name + b"\0" + bytes([STALE_BYTE])


@pytest.mark.parametrize("name", ("AES_ROM_FMT_STR", "AES_ROM_UNFMT_STR"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_8_3_forms_on_the_24_bit_bus(name, through_line_f):
    run(name, (SOURCE_AT | TAG, DESTINATION_AT | TAG), buffers(b"DESK.INF"), through_line_f=through_line_f)


def test_unfmt_str_in_place():
    """The ORDER: the name written over the form it is read from, the writes never ahead of the reads."""
    result = run("AES_ROM_UNFMT_STR", (SOURCE_AT, SOURCE_AT), text(SOURCE_AT, "AB      CD"))
    assert result.after(SOURCE_AT, 11) == b"AB.CD\0  CD\0"


# ---- merge_str $fed070 ----------------------------------------------------------------------------------------------
def parameters_pokes(*slots):
    """The parameter slots: an int a LONGWORD, bytes a string staged in the argument strings and its pointer."""
    longs, strings_at, strings_pokes = [], ARGUMENT_STRINGS_AT, {}
    for slot in slots:
        if isinstance(slot, bytes):
            strings_pokes.update(text(strings_at, slot))
            longs.append(strings_at)
            strings_at += len(slot) + 1
        else:
            longs.append(slot & 0xFFFFFFFF)
    return merge_pokes({PARAMETERS_AT: struct.pack(f">{len(longs)}I", *longs)}, strings_pokes)


MERGE_ARGUMENTS = (DESTINATION_AT, TEMPLATE_AT, PARAMETERS_AT)


def merge_pokes_of(template, *slots):
    """A stale destination, `template` and its parameter slots."""
    return merge_pokes(stale(DESTINATION_AT, strings.BUFFER_BYTES), text(TEMPLATE_AT, template), parameters_pokes(*slots))


def merge(template, *slots, tag=0, **kwargs):
    arguments = tuple(argument | tag for argument in MERGE_ARGUMENTS)
    return run("AES_ROM_MERGE_STR", arguments, merge_pokes_of(template, *slots), **kwargs)


MERGE = {
    "the desk's info line": ((b"%L bytes used in %W items.", 123456, 0x00070000), b"123456 bytes used in 7 items."),
    "a string": ((b"Drive %S: %L", b"A", 9), b"Drive A: 9"),
    "a percent": ((b"100%% of %W", 0x00640000), b"100% of 100"),
    "an unknown code dropped": ((b"a%Xb%Lc", 5), b"ab5c"),
    "zero": ((b"[%L][%W]", 0, 0), b"[0][0]"),
    "%W reads the slot's first word": ((b"%W", 0x0001FFFF), b"1"),
    "the largest longword": ((b"%L", 0x7FFFFFFF), b"2147483647"),
    "a negative longword: its digits below '0'": ((b"%L", -1234), b"/.-,"),
    "$80000000: ldiv answers it 0": ((b"%L", 0x80000000), b"0"),
    "%W unsigned": ((b"%W", 0xFFFF0000), b"65535"),
    "no codes": ((b"plain",), b"plain"),
    "empty": ((b"",), b""),
    "an empty string parameter": ((b"<%S>", b""), b"<>"),
    "a lone %S": ((b"%S", b"A"), b"A"),
}


@pytest.mark.parametrize("shape", sorted(MERGE))
def test_merge_str_fills_the_template(shape):
    arguments, merged = MERGE[shape]
    result = merge(*arguments)
    assert result.after(DESTINATION_AT, len(merged) + 2) == merged + b"\0" + bytes([STALE_BYTE])


def test_merge_str_leaves_ldiv_s_last_remainder_in_ram():
    """The one trace the Alcyon runtime leaves: 123 divides by ten three times, the last remainder 1."""
    result = merge(b"%L", 123)
    assert result.long(aes.AES_LDIV_REMAINDER) == 1
    assert aes.AES_LDIV_REMAINDER in result.info["writes"]


def test_merge_str_after_a_trailing_percent_reads_past_the_nul():
    """A `%` as the last byte takes the NUL for its code, drops it, and goes on reading what follows it."""
    pokes = merge_pokes(stale(DESTINATION_AT, 16), {TEMPLATE_AT: b"ab%\0cd\0"})
    result = run("AES_ROM_MERGE_STR", (DESTINATION_AT, TEMPLATE_AT, PARAMETERS_AT), pokes)
    assert string_in(result.final, DESTINATION_AT) == b"abcd"


def test_merge_str_s_slot_offset_is_a_word_sign_extended():
    """The 8193rd slot's offset is $8000 — `movea.w d3,a0` makes it 32 KB BELOW the parameters. Staged in the bank
    (Tier 1 only): 8192 zero slots each printed "0", then the slot below the parameters, which holds 42."""
    slots = 0x8000 // strings.MERGE_SLOT_BYTES
    template_at = strings.WHOLE_BANK_AT
    parameters_at = strings.WHOLE_BANK_AT + 0x10000
    destination_at = parameters_at + 0x8000
    template = b"%W" * (slots + 1)
    pokes = merge_pokes({template_at: template + b"\0"}, {parameters_at: bytes(0x8000)},
                        {parameters_at - 0x8000: struct.pack(">H", 42)})
    result = run("AES_ROM_MERGE_STR", (destination_at, template_at, parameters_at), pokes, max_insns=0x100000)
    assert string_in(result.final, destination_at) == b"0" * slots + b"42"


@pytest.mark.parametrize("tag", (0, TAG), ids=("plain", "on the 24-bit bus"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_merge_str_through_the_door_and_the_bus(tag, through_line_f):
    result = merge(b"%S has %L bytes", b"DESK.ACC", 4096, tag=tag, through_line_f=through_line_f)
    assert string_in(result.final, DESTINATION_AT) == b"DESK.ACC has 4096 bytes"


def test_merge_str_s_string_pointer_on_the_24_bit_bus():
    pokes = merge_pokes(stale(DESTINATION_AT, 16), text(TEMPLATE_AT, "%S!"), text(ARGUMENT_STRINGS_AT, "ok"),
                        {PARAMETERS_AT: struct.pack(">I", ARGUMENT_STRINGS_AT | TAG)})
    result = run("AES_ROM_MERGE_STR", (DESTINATION_AT, TEMPLATE_AT, PARAMETERS_AT), pokes)
    assert string_in(result.final, DESTINATION_AT) == b"ok!"


# ---- wildcmp $fed12e ------------------------------------------------------------------------------------------------
WILDCMP = {
    "*.* against a name": (b"*.*", b"DESK.INF", 1),
    "*.PRG against an accessory": (b"*.PRG", b"CONTROL.ACC", 0),
    "*.ACC against an accessory": (b"*.ACC", b"CONTROL.ACC", 1),
    "? for one byte": (b"?ESK.INF", b"DESK.INF", 1),
    "? at the dot moves the pattern alone": (b"DES??.INF", b"DES.INF", 1),
    "a pattern shorter than the name": (b"DESK", b"DESK.INF", 0),
    "a name shorter than the pattern, the rest wild": (b"DESK*.*", b"DESK", 1),
    "a name shorter than the pattern, the rest ?": (b"DES??", b"DES", 1),
    "a name shorter than the pattern, the rest literal": (b"DESKTOP", b"DESK", 0),
    "* alone against a dotless name": (b"*", b"README", 1),
    "* alone against a dotted name": (b"*", b"README.TXT", 0),
    "both empty": (b"", b"", 1),
    "an exact name": (b"DESK.INF", b"DESK.INF", 1),
    "one byte off": (b"DESK.INF", b"DESK.INX", 0),
    "a literal pattern, the first byte differs": (b"X", b"Y", 0),
}


@pytest.mark.parametrize("shape", sorted(WILDCMP))
def test_wildcmp_matches_as_the_rom_does(shape):
    pattern, name, matched = WILDCMP[shape]
    assert run("AES_ROM_WILDCMP", (SOURCE_AT, DESTINATION_AT), pair_pokes(pattern, name)).answer() == matched


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_wildcmp_on_the_24_bit_bus(through_line_f):
    result = run("AES_ROM_WILDCMP", (SOURCE_AT | TAG, DESTINATION_AT | TAG), pair_pokes(b"*.INF", b"DESK.INF"),
                 through_line_f=through_line_f)
    assert result.answer() == 1


# ---- the registry: the C rows Tier 3 prices, each over the bar and carried by `optimize.S`'s rows (mechanism (T),
# `test_aes_strings_asm.py`): the empty string and the realistic name or path ----
_ROWS = [
    *((f"{len(string)} bytes", "AES_ROM_STRLEN", (SOURCE_AT,), text(SOURCE_AT, string)) for string in (b"", b"DESKTOP.INF")),
    *((label, name, (SOURCE_AT, DESTINATION_AT), pair_pokes(*PAIRS[label]))
      for label in ("both empty", "equal", "one byte differs") for name in ("AES_ROM_STREQ", "AES_ROM_STRCHK")),
    *((f"{len(source)} bytes", "AES_ROM_STRCPY", (SOURCE_AT, DESTINATION_AT), buffers(source)) for source in (b"", b"A:\\DESKTOP.INF")),
    *((f"onto {len(destination)} bytes", "AES_ROM_STRCAT", (SOURCE_AT, DESTINATION_AT), buffers(b"*.*", destination))
      for destination in (b"", b"A:\\")),
    *((label, "AES_ROM_STRSCN", (SOURCE_AT, DESTINATION_AT, STRSCN[label][1]), buffers(STRSCN[label][0]))
      for label in ("empty", "up to the stop")),
    *((label, "AES_ROM_SCASB", (SOURCE_AT, SCASB[label][1]), text(SOURCE_AT, SCASB[label][0])) for label in ("empty", "found")),
    *((label, "AES_ROM_FMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(FMT_STR[label][0]))
      for label in ("empty", "a name and an extension")),
    *((label, "AES_ROM_UNFMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(UNFMT_STR[label][0]))
      for label in ("empty", "a padded name")),
    *((label, "AES_ROM_MERGE_STR", MERGE_ARGUMENTS, merge_pokes_of(*MERGE[label][0]))
      for label in ("empty", "no codes", "the desk's info line", "a string", "a lone %S")),
    *((label, "AES_ROM_WILDCMP", (SOURCE_AT, DESTINATION_AT), pair_pokes(*WILDCMP[label][:2]))
      for label in ("both empty", "*.* against a name", "one byte off", "a literal pattern, the first byte differs")),
]
for _label, _name, _arguments, _pokes in _ROWS:
    strings.register(_label, _name, _arguments, _pokes)
