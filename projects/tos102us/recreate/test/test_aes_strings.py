"""AES utility layer, the ARITHMETIC and the COPIES AND FILLS (`src/aes/strings.c`): mul_div $fecb6e, the contrl[]
pointer slots $fecbc6 / $fecbda, min/max $fece42 / $fece4e, toupper $fece74, and lstcpy $fecbe6, xstrpix $fecbfa,
wset $fecc12, xstrpix_n $fecc28, wcopy $fecc40, wfill $fecc56, lstrlen $fecc6c, lbcopy $fecc7e, movs $fece2e and
bfill $fece5e.

Hand 68000, each over its own loop shape: `subq.w; bne` (a zero count is 65536 unless guarded), `dbf` (a zero count is
none, the count unsigned), `subq.w; bpl` (lbcopy's backward loop, a SIGNED count) and the two BYTE counters (lstcpy's
answer and xstrpix's) — every one staged across its wrap. Copies are run over themselves in both directions, and every
pointer is also handed in with a top byte (`aes.BUS_TAG`). Three of these routines no ROM code calls (wset, xstrpix_n,
wfill): no Line-F word names them, so they are run direct only.
"""
import pytest

import aes
import aes_strings as strings
import vdi_helpers
from aes import signed
from aes_strings import (DESTINATION_AT, SOURCE_AT, STALE_BYTE, WHOLE_BANK_AT, WHOLE_BANK_BYTES,
                         buffers, run, stale, text)
from case import merge_pokes

TAG = aes.BUS_TAG
WORD_MASK = 0xFFFF
LONG_RUN = {"max_insns": 0x80000}      # a 64K-pass loop and its differential: 3-4 instructions a pass
OVER_ITSELF = 0x10          # where a copy over itself is staged in the source buffer, room below it for a shift down


def ramp(length, start=1):
    """`length` bytes that differ from their neighbours and from the stale byte: a copy one byte off shows."""
    return bytes((start + index) % 251 + 1 for index in range(length))


# ---- mul_div $fecb6e ------------------------------------------------------------------------------------------------
def mul_div_model(multiplicand, multiplier, divisor):
    """The ROM's rounding, over its own widths: the doubled multiplier a WORD, one `divs.w`, the step and the `asr.w`
    on the low word.

    ORACLE-DEFINED ON OVERFLOW: a quotient that does not fit a word leaves the product in the register, and `bmi` then
    reads the N the divide left — which the 68000's manual calls UNDEFINED. Musashi, the oracle, leaves N as `muls.w`
    set it (the PRODUCT's sign), and so does this model and the C; Hatari's 68000 (WinUAE's core, the machine the user
    plays on) SETS N, so there a positive product steps DOWN: mul_div(1000, 1000, 1) is -15808 here and -15809 on the
    machine. The negative product agrees on both. What ships is the ROM's own `divs.w; bmi` (`optimize.S`), so the
    target does what the machine does; only this differential's answer on that arm is the oracle's."""
    doubled = signed(multiplier * 2)
    product = multiplicand * doubled
    quotient = int(product / divisor)
    if -0x8000 <= quotient <= 0x7FFF:
        low, negative = quotient & WORD_MASK, quotient < 0
    else:
        low, negative = product & WORD_MASK, product < 0
    return signed(low + (-1 if negative else 1)) >> 1


MUL_DIV = {
    "a third of 200 at 100": (100, 200, 300),
    "rounded up at the half": (7, 1, 2),
    "a negative product rounded away from zero": (-7, 1, 2),
    "over a negative divisor": (100, 200, -300),
    "a zero product": (0, 5, 3),
    "the doubled multiplier wraps negative": (1, 20000, 1),
    "the quotient overflows, a positive product (N as Musashi leaves it: the machine's answer is -15809)": (1000, 1000, 1),
    "the quotient overflows, a negative product (N as Musashi leaves it, as the machine's)": (-1000, 1000, 1),
    "a slider: 37 of 480 over 1000": (37, 1000, 480),
}


@pytest.mark.parametrize("shape", sorted(MUL_DIV))
def test_mul_div_rounds_as_the_rom_does(shape):
    result = run("AES_ROM_MUL_DIV", MUL_DIV[shape])
    assert result.answer() == mul_div_model(*MUL_DIV[shape])


def test_mul_div_through_line_f():
    assert run("AES_ROM_MUL_DIV", MUL_DIV["a slider: 37 of 480 over 1000"], through_line_f=True).answer() == 77


def test_mul_div_by_zero_is_refused_by_name_on_the_host():
    """A zero divisor takes vector 5 on the machine; the host has none to take, and refuses by name."""
    returncode, stderr = vdi_helpers.refusal("aes_mul_div", ["ctypes.c_int16"] * 3, "1, 1, 0")
    assert returncode != 0 and "zero divide" in stderr, stderr


# ---- the contrl[] pointer slots $fecbc6 / $fecbda --------------------------------------------------------------------
@pytest.mark.parametrize("pointer", (0x00012345, 0x5A0789AB), ids=("plain", "a top byte, stored as it is"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_set_contrl_ptr_stores_the_whole_longword(pointer, through_line_f):
    result = run("AES_ROM_SET_CONTRL_PTR", (pointer,), through_line_f=through_line_f)
    assert result.long(aes.AES_GSX_CONTRL_PTR) == pointer


CONTRL_PTR2 = 0x00FE_DCBA


@pytest.mark.parametrize("answer_at", (strings.ANSWER_AT, strings.ANSWER_AT | TAG), ids=("plain", "on the 24-bit bus"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_get_contrl_ptr2_answers_contrl_9_and_10(answer_at, through_line_f):
    pokes = merge_pokes(aes.field_pokes("AES", GSX_CONTRL_PTR2=CONTRL_PTR2), stale(strings.ANSWER_AT, 4))
    result = run("AES_ROM_GET_CONTRL_PTR2", (answer_at,), pokes, through_line_f=through_line_f)
    assert result.long(strings.ANSWER_AT) == CONTRL_PTR2


# ---- min / max $fece42 / $fece4e --------------------------------------------------------------------------------------
PAIRS = {"ascending": (3, 9), "descending": (9, 3), "equal": (5, 5), "signed": (-2, 1), "the extremes": (-0x8000, 0x7FFF)}


@pytest.mark.parametrize("pair", sorted(PAIRS))
@pytest.mark.parametrize("name,pick", (("AES_ROM_MIN", min), ("AES_ROM_MAX", max)))
def test_min_and_max_compare_signed_words(name, pick, pair):
    assert run(name, PAIRS[pair]).answer() == pick(PAIRS[pair])


@pytest.mark.parametrize("name", ("AES_ROM_MIN", "AES_ROM_MAX"))
def test_min_and_max_through_line_f(name):
    assert run(name, (4, -4), through_line_f=True).answer() == (-4 if name == "AES_ROM_MIN" else 4)


# ---- toupper $fece74 ------------------------------------------------------------------------------------------------
TOUPPER = {"a": (0x61, 0x41), "z": (0x7A, 0x5A), "already upper": (0x41, 0x41), "the byte below a": (0x60, 0x60),
           "the byte above z": (0x7B, 0x7B), "a byte from $80 up, sign-extended": (0xE9, -0x17),
           "the argument's high byte ignored": (0x1262, 0x42)}


@pytest.mark.parametrize("shape", sorted(TOUPPER))
def test_toupper_raises_a_to_z_only(shape):
    character, expected = TOUPPER[shape]
    assert run("AES_ROM_TOUPPER", (character,)).answer() == expected


def test_toupper_through_line_f():
    assert run("AES_ROM_TOUPPER", (0x71,), through_line_f=True).answer() == 0x51


# ---- the Alcyon runtime merge_str calls: lmul $fe3db4 and ldiv $fe3e08 ------------------------------------------------
# Compiled C (`link`/`unlk`, no Line-F): entered by `jsr` alone — no Line-F word names either, so no door case.
LONG_MASK = 0xFFFFFFFF
LONG_BITS = 32


LMUL = {"small": (1234, 567), "a negative factor": (-1234, 567), "both negative": (-1234, -567),
        "the low longword of a large product": (0x12345, 0x6789A), "$80000000 by -1": (-0x80000000, -1),
        "by zero": (77, 0)}


@pytest.mark.parametrize("shape", sorted(LMUL))
def test_lmul_answers_the_product_s_low_longword(shape):
    left, right = LMUL[shape]
    result = run("AES_ROM_LMUL", (left & LONG_MASK, right & LONG_MASK))
    assert result.info["regs"]["d0"] == (left * right) & LONG_MASK


def ldiv_model(dividend, divisor):
    """(quotient, remainder) as ldiv leaves them: over the magnitudes (each `neg.l`'d, $80000000 staying itself), a
    divisor larger as a SIGNED long answering 0, the signs put back only when exactly one operand was negative."""
    magnitude, by = signed(abs(dividend), LONG_BITS), signed(abs(divisor), LONG_BITS)
    if by > magnitude:
        quotient, remainder = 0, magnitude & LONG_MASK
    elif by == magnitude:
        quotient, remainder = 1, 0
    else:
        quotient, remainder = (magnitude & LONG_MASK) // (by & LONG_MASK), (magnitude & LONG_MASK) % (by & LONG_MASK)
    if (dividend < 0) != (divisor < 0):
        quotient, remainder = -quotient, -remainder
    return quotient & LONG_MASK, remainder & LONG_MASK


LDIV = {
    "a small dividend: one divu.w": (1234, 10),
    "a large dividend: bit by bit": (123456789, 10),
    "65536, the first dividend divided bit by bit": (0x10000, 1),
    "a large divisor too": (0x7FFFFFFF, 0x12345),
    "the divisor larger": (7, 10),
    "equal": (10, 10),
    "a negative dividend": (-1234, 10),
    "a negative divisor": (1234, -10),
    "both negative: the remainder stays positive": (-7, -2),
    "$80000000 taken for smaller than ten": (-0x80000000, 10),
    "$80000000 by itself": (-0x80000000, -0x80000000),
    "by $80000000, a large dividend": (0x123456, -0x80000000),
    "zero": (0, 10),
    "368640 / 4608: $fedf86's divide by a track": (368640, 4608),
    "100000 / 30000: $fe667a's x*100 over a word": (100000, 30000),
}


@pytest.mark.parametrize("shape", sorted(LDIV))
def test_ldiv_answers_the_quotient_and_leaves_the_remainder(shape):
    dividend, divisor = LDIV[shape]
    result = run("AES_ROM_LDIV", (dividend & LONG_MASK, divisor & LONG_MASK), stale(aes.AES_LDIV_REMAINDER, 4))
    quotient, remainder = ldiv_model(dividend, divisor)
    assert result.info["regs"]["d0"] == quotient
    assert result.long(aes.AES_LDIV_REMAINDER) == remainder


@pytest.mark.parametrize("dividend,divisor", ((5, 0), (5, -0x80000000)), ids=("by zero", "a small dividend by $80000000"))
def test_ldiv_s_zero_divides_are_refused_by_name_on_the_host(dividend, divisor):
    """`divs.w #0` (a zero divisor) and `divu.w` by the low word of $80000000 (a dividend below 65536 against it)
    take vector 5 on the machine; the host has none to take."""
    returncode, stderr = vdi_helpers.refusal("aes_ldiv", ["ctypes.c_void_p", "ctypes.c_int32", "ctypes.c_int32"],
                                             f"buf, {dividend}, {signed(divisor, LONG_BITS)}")
    assert returncode != 0 and "zero divide" in stderr, stderr


# ---- lstcpy $fecbe6: the copy that counts in a BYTE --------------------------------------------------------------------
def byte_counted(length):
    """lstcpy's answer: `addq.b` per byte moved (the NUL too), then `subq.w #1`."""
    return signed(((length + 1) & 0xFF) - 1)


LSTCPY = {"empty": b"", "a name": b"DESKTOP.INF", "254 bytes": ramp(254), "255 bytes: the byte counter at 0": ramp(255),
          "256 bytes": ramp(256), "300 bytes": ramp(300)}


@pytest.mark.parametrize("shape", sorted(LSTCPY))
def test_lstcpy_copies_the_nul_and_counts_in_a_byte(shape):
    source = LSTCPY[shape]
    result = run("AES_ROM_LSTCPY", (DESTINATION_AT, SOURCE_AT), buffers(source))
    assert result.after(DESTINATION_AT, len(source) + 2) == source + b"\0" + bytes([STALE_BYTE])
    assert result.answer() == byte_counted(len(source))


def test_lstcpy_over_itself_two_bytes_down():
    """The ORDER: a destination two bytes below the source, so each store lands on a byte already read."""
    source = SOURCE_AT + OVER_ITSELF
    result = run("AES_ROM_LSTCPY", (source - 2, source), text(source, "ABCDEF"))
    assert result.after(source - 2, 9) == b"ABCDEF\0F\0"


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_lstcpy_on_the_24_bit_bus(through_line_f):
    result = run("AES_ROM_LSTCPY", (DESTINATION_AT | TAG, SOURCE_AT | TAG), buffers(b"TAGGED"),
                 through_line_f=through_line_f)
    assert strings.string_in(result.final, DESTINATION_AT) == b"TAGGED"


# ---- xstrpix $fecbfa: bytes to words, counted in a BYTE -------------------------------------------------------------
XSTRPIX = {"empty": b"", "a label": b"Hello", "a byte from $80 up": b"\xe9t\xe9", "255 bytes": ramp(255),
           "256 bytes: the byte counter at 0": ramp(256)}


@pytest.mark.parametrize("shape", sorted(XSTRPIX))
def test_xstrpix_widens_each_byte_and_stores_no_nul(shape):
    source = XSTRPIX[shape]
    pokes = merge_pokes(text(SOURCE_AT, source), stale(DESTINATION_AT, strings.BUFFER_BYTES))
    result = run("AES_ROM_XSTRPIX", (DESTINATION_AT, SOURCE_AT), pokes)
    assert result.words(DESTINATION_AT, len(source)) == list(source)
    if len(source) < strings.BUFFER_BYTES // 2:
        assert result.after(DESTINATION_AT + 2 * len(source), 2) == bytes([STALE_BYTE] * 2)
    assert result.answer() == len(source) & 0xFF


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_xstrpix_on_the_24_bit_bus(through_line_f):
    pokes = merge_pokes(text(SOURCE_AT, "Tag"), stale(DESTINATION_AT, 8))
    result = run("AES_ROM_XSTRPIX", (DESTINATION_AT | TAG, SOURCE_AT | TAG), pokes, through_line_f=through_line_f)
    assert result.words(DESTINATION_AT, 3) == list(b"Tag")


# ---- the word fills and copies: wset $fecc12, xstrpix_n $fecc28, wcopy $fecc40, wfill $fecc56 --------------------------
@pytest.mark.parametrize("count", (0, 1, 5))
@pytest.mark.parametrize("tagged", (False, True), ids=("plain", "on the 24-bit bus"))
def test_wset_stores_count_words_and_none_for_zero(count, tagged):
    result = run("AES_ROM_WSET", (DESTINATION_AT | (TAG if tagged else 0), count, 0x1234), stale(DESTINATION_AT, 16))
    assert result.words(DESTINATION_AT, count) == [0x1234] * count
    assert result.after(DESTINATION_AT + 2 * count, 2) == bytes([STALE_BYTE] * 2)


@pytest.mark.parametrize("count,value", ((3, 7), (1, 0xFFFF), (5, 0)), ids=("three", "one", "a zero value stores none"))
@pytest.mark.parametrize("tagged", (False, True), ids=("plain", "on the 24-bit bus"))
def test_wfill_is_guarded_by_its_value_not_its_count(count, value, tagged):
    result = run("AES_ROM_WFILL", (DESTINATION_AT | (TAG if tagged else 0), count, value), stale(DESTINATION_AT, 16))
    stored = count if value else 0
    assert result.words(DESTINATION_AT, stored) == [value] * stored
    assert result.after(DESTINATION_AT + 2 * stored, 2) == bytes([STALE_BYTE] * 2)


def test_wfill_with_a_zero_count_stores_65536_words():
    result = run("AES_ROM_WFILL", (WHOLE_BANK_AT, 0, 0x5A5A), **LONG_RUN)
    assert result.after(WHOLE_BANK_AT, WHOLE_BANK_BYTES) == b"\x5a" * WHOLE_BANK_BYTES


@pytest.mark.parametrize("tagged", (False, True), ids=("plain", "on the 24-bit bus"))
def test_xstrpix_n_widens_count_bytes_nuls_and_all(tagged):
    source = b"a\0b\xfe"
    pokes = merge_pokes({SOURCE_AT: source}, stale(DESTINATION_AT, 16))
    tag = TAG if tagged else 0
    result = run("AES_ROM_XSTRPIX_N", (DESTINATION_AT | tag, SOURCE_AT | tag, len(source)), pokes)
    assert result.words(DESTINATION_AT, len(source)) == list(source)
    assert result.after(DESTINATION_AT + 2 * len(source), 2) == bytes([STALE_BYTE] * 2)


def test_xstrpix_n_with_a_zero_count_widens_65536_bytes():
    """No guard: the `subq.w; bne` of a zero count runs 65536 passes — the ramp read from the bank's upper half, which
    the words stored from its base reach only as the last byte is read."""
    source = ramp(0x10000)
    upper_half = WHOLE_BANK_AT + len(source)
    result = run("AES_ROM_XSTRPIX_N", (WHOLE_BANK_AT, upper_half, 0), {upper_half: source}, **LONG_RUN)
    assert result.words(WHOLE_BANK_AT, 0x10000) == list(source)


WCOPY_WORDS = (0x1111, 0x2222, 0x3333, 0x4444, 0x5555)


def words_pokes(at, words):
    return {at: b"".join(word.to_bytes(2, "big") for word in words)}


@pytest.mark.parametrize("count", (0, 1, 5))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_wcopy_copies_count_words_and_none_for_zero(count, through_line_f):
    pokes = merge_pokes(words_pokes(SOURCE_AT, WCOPY_WORDS), stale(DESTINATION_AT, 16))
    result = run("AES_ROM_WCOPY", (DESTINATION_AT, SOURCE_AT, count), pokes, through_line_f=through_line_f)
    assert result.words(DESTINATION_AT, count) == list(WCOPY_WORDS[:count])
    assert result.after(DESTINATION_AT + 2 * count, 2) == bytes([STALE_BYTE] * 2)


@pytest.mark.parametrize("offset", (2, -2), ids=("one word up: the first word smeared", "one word down: shifted"))
def test_wcopy_over_itself_ascending(offset):
    source = SOURCE_AT + OVER_ITSELF
    result = run("AES_ROM_WCOPY", (source + offset, source, 4), words_pokes(source, WCOPY_WORDS))
    expected = [0x1111] * 5 if offset > 0 else [0x1111, 0x2222, 0x3333, 0x4444, 0x4444, 0x5555]
    assert result.words(min(source, source + offset), len(expected)) == expected


def test_wcopy_on_the_24_bit_bus():
    pokes = merge_pokes(words_pokes(SOURCE_AT, WCOPY_WORDS), stale(DESTINATION_AT, 16))
    result = run("AES_ROM_WCOPY", (DESTINATION_AT | TAG, SOURCE_AT | TAG, 3), pokes)
    assert result.words(DESTINATION_AT, 3) == list(WCOPY_WORDS[:3])


# ---- lstrlen $fecc6c --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("string", (b"", b"A", ramp(300)), ids=("empty", "one", "300 bytes"))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_lstrlen_counts_to_the_nul(string, through_line_f):
    assert run("AES_ROM_LSTRLEN", (SOURCE_AT,), text(SOURCE_AT, string), through_line_f=through_line_f).answer() == len(string)


def test_lstrlen_on_the_24_bit_bus():
    assert run("AES_ROM_LSTRLEN", (SOURCE_AT | TAG,), text(SOURCE_AT, "four")).answer() == 4


def test_lstrlen_wraps_at_65536():
    """The word count: a string of 65537 bytes (a ramp, no NUL inside) answers 1."""
    long_band = ramp(0x10001)
    assert run("AES_ROM_LSTRLEN", (WHOLE_BANK_AT,), {WHOLE_BANK_AT: long_band + b"\0"}, **LONG_RUN).answer() == 1


# ---- lbcopy $fecc7e: memmove, its direction a SIGNED compare ------------------------------------------------------------
def memmove_model(image, destination, source, count):
    data = bytes(image[source:source + count])
    image[destination:destination + count] = data


def lbcopy(destination, source, count, pokes, **kwargs):
    return run("AES_ROM_LBCOPY", (destination, source, count), pokes, **kwargs)


LBCOPY_SPAN = 0x40
LBCOPY_SHAPES = {                                     # (destination offset, source offset, count) inside the span
    "disjoint, forward": (0x30, 0x00, 7),
    "disjoint, backward": (0x00, 0x30, 7),
    "overlapping, the destination below": (0x02, 0x05, 20),
    "overlapping, the destination above": (0x05, 0x02, 20),
    "one byte": (0x10, 0x11, 1),
    "odd to even": (0x20, 0x03, 9),
    "a zero count moves nothing": (0x00, 0x10, 0),
}


@pytest.mark.parametrize("shape", sorted(LBCOPY_SHAPES))
def test_lbcopy_moves_as_memmove(shape):
    destination, source, count = LBCOPY_SHAPES[shape]
    pokes = {SOURCE_AT: ramp(LBCOPY_SPAN)}
    result = lbcopy(SOURCE_AT + destination, SOURCE_AT + source, count, pokes)
    expected = bytearray(ramp(LBCOPY_SPAN))
    memmove_model(expected, destination, source, count)
    assert result.after(SOURCE_AT, LBCOPY_SPAN) == bytes(expected)


def test_lbcopy_s_direction_is_a_signed_compare_of_the_whole_longwords():
    """A source whose top byte is $ff reads as BELOW the destination, so the copy runs BACKWARD — and a source above
    an overlapping destination, copied backward, reads bytes the copy already stored."""
    pokes = {SOURCE_AT: ramp(LBCOPY_SPAN)}
    result = lbcopy(SOURCE_AT, (SOURCE_AT + 2) | 0xFF000000, 6, pokes)
    expected = bytearray(ramp(LBCOPY_SPAN))
    for index in reversed(range(6)):
        expected[index] = expected[index + 2]
    assert result.after(SOURCE_AT, LBCOPY_SPAN) == bytes(expected)


@pytest.mark.parametrize("tags", ((TAG, TAG), (TAG, 0), (0, TAG)), ids=("both", "the destination", "the source"))
def test_lbcopy_on_the_24_bit_bus(tags):
    """Tagged, the compare still decides: a positive tag on the source alone makes it the larger, so the copy runs
    FORWARD over a destination above it and smears — where the others, untagged or tagged alike, run backward."""
    pokes = {SOURCE_AT: ramp(LBCOPY_SPAN)}
    result = lbcopy((SOURCE_AT + 4) | tags[0], (SOURCE_AT + 1) | tags[1], 9, pokes)
    assert result.after(SOURCE_AT, 4) == ramp(LBCOPY_SPAN)[:4]


def test_lbcopy_through_line_f():
    result = lbcopy(SOURCE_AT + 0x30, SOURCE_AT, 7, {SOURCE_AT: ramp(LBCOPY_SPAN)}, through_line_f=True)
    assert result.after(SOURCE_AT + 0x30, 7) == ramp(LBCOPY_SPAN)[:7]


LONG_COPY = 0x8001          # the last count the backward loop's signed word carries whole


def test_lbcopy_backward_moves_32769_bytes_whole():
    source = ramp(LONG_COPY + 2)
    result = lbcopy(WHOLE_BANK_AT + 2, WHOLE_BANK_AT, LONG_COPY, {WHOLE_BANK_AT: source}, **LONG_RUN)
    assert result.after(WHOLE_BANK_AT, LONG_COPY + 2) == source[:2] + source[:LONG_COPY]


@pytest.mark.parametrize("count", (LONG_COPY + 1, 0xFFFF), ids=("32770", "65535"))
def test_lbcopy_backward_from_32770_bytes_moves_only_the_last(count):
    """`subq.w #1` leaves the count negative before the first pass, so `bpl` ends the loop after ONE byte."""
    source = ramp(count + 1)
    result = lbcopy(WHOLE_BANK_AT + 1, WHOLE_BANK_AT, count, {WHOLE_BANK_AT: source})
    assert result.after(WHOLE_BANK_AT, count + 1) == source[:count] + source[count - 1:count]


def test_lbcopy_forward_moves_65535_bytes():
    source = ramp(0xFFFF + 1)
    result = lbcopy(WHOLE_BANK_AT, WHOLE_BANK_AT + 1, 0xFFFF, {WHOLE_BANK_AT: source}, **LONG_RUN)
    assert result.after(WHOLE_BANK_AT, 0xFFFF + 1) == source[1:] + source[-1:]


# ---- movs $fece2e and bfill $fece5e: `dbf` counts ------------------------------------------------------------------------
@pytest.mark.parametrize("count", (0, 1, 7))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_movs_moves_count_bytes_forward(count, through_line_f):
    pokes = merge_pokes({SOURCE_AT: ramp(16)}, stale(DESTINATION_AT, 16))
    result = run("AES_ROM_MOVS", (count, SOURCE_AT, DESTINATION_AT), pokes, through_line_f=through_line_f)
    assert result.after(DESTINATION_AT, count + 1) == ramp(16)[:count] + bytes([STALE_BYTE])


def test_movs_over_itself_one_byte_up_smears_the_first():
    result = run("AES_ROM_MOVS", (5, SOURCE_AT, SOURCE_AT + 1), {SOURCE_AT: ramp(8)})
    assert result.after(SOURCE_AT, 8) == ramp(8)[:1] * 6 + ramp(8)[6:]


def test_movs_counts_unsigned():
    """A word from $8000 up is that many bytes, not a negative none."""
    count = 0x9000
    source = ramp(count)
    result = run("AES_ROM_MOVS", (count, WHOLE_BANK_AT, WHOLE_BANK_AT + count), {WHOLE_BANK_AT: source}, **LONG_RUN)
    assert result.after(WHOLE_BANK_AT + count, count) == source


def test_movs_on_the_24_bit_bus():
    pokes = merge_pokes({SOURCE_AT: ramp(16)}, stale(DESTINATION_AT, 16))
    result = run("AES_ROM_MOVS", (3, SOURCE_AT | TAG, DESTINATION_AT | TAG), pokes)
    assert result.after(DESTINATION_AT, 3) == ramp(16)[:3]


@pytest.mark.parametrize("count", (0, 1, 7))
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_bfill_fills_with_the_value_s_low_byte(count, through_line_f):
    result = run("AES_ROM_BFILL", (count, 0x1234, DESTINATION_AT), stale(DESTINATION_AT, 16), through_line_f=through_line_f)
    assert result.after(DESTINATION_AT, count + 1) == b"\x34" * count + bytes([STALE_BYTE])


def test_bfill_counts_unsigned_and_rides_the_bus():
    count = 0x8800
    result = run("AES_ROM_BFILL", (count, 0x00EE, WHOLE_BANK_AT | TAG), **LONG_RUN)
    assert result.after(WHOLE_BANK_AT, count + 1) == b"\xee" * count + b"\0"


# ---- the registry: the C rows Tier 3 prices. Every one is over the bar — the reason these ship as `optimize.S`
# (`test_aes_strings_asm.py`, whose rows carry them by mechanism (T)) — so they are the shapes the ROM's callers
# hand in: the empty or zero count (the C's frame and image cost against a handful of ROM instructions) and the
# realistic long one (its loop against the ROM's two-instruction loops) ----
_ROWS = [
    *((f"mul_div {label}", "AES_ROM_MUL_DIV", MUL_DIV[label], None)
      for label in ("a slider: 37 of 480 over 1000", "a zero product")),
    ("a pointer", "AES_ROM_SET_CONTRL_PTR", (0x5A0789AB,), None),
    ("contrl[9..10]", "AES_ROM_GET_CONTRL_PTR2", (strings.ANSWER_AT,),
     merge_pokes(aes.field_pokes("AES", GSX_CONTRL_PTR2=CONTRL_PTR2), stale(strings.ANSWER_AT, 4))),
    *((label, name, PAIRS[label], None) for label in ("ascending", "descending") for name in ("AES_ROM_MIN", "AES_ROM_MAX")),
    *((label, "AES_ROM_TOUPPER", (TOUPPER[label][0],), None) for label in ("a", "already upper")),
    ("a negative factor", "AES_ROM_LMUL", tuple(value & LONG_MASK for value in LMUL["a negative factor"]), None),
    *((label, "AES_ROM_LDIV", tuple(value & LONG_MASK for value in LDIV[label]), stale(aes.AES_LDIV_REMAINDER, 4))
      for label in ("a small dividend: one divu.w", "a large dividend: bit by bit", "a negative dividend",
                    "368640 / 4608: $fedf86's divide by a track", "100000 / 30000: $fe667a's x*100 over a word")),
    *((label, "AES_ROM_LSTCPY", (DESTINATION_AT, SOURCE_AT), buffers(LSTCPY[label])) for label in ("empty", "a name", "254 bytes")),
    *((label, "AES_ROM_XSTRPIX", (DESTINATION_AT, SOURCE_AT),
       merge_pokes(text(SOURCE_AT, XSTRPIX[label]), stale(DESTINATION_AT, strings.BUFFER_BYTES))) for label in ("empty", "a label")),
    *((f"{count} words", "AES_ROM_WSET", (DESTINATION_AT, count, 0x1234), stale(DESTINATION_AT, 16)) for count in (0, 5)),
    ("a zero value", "AES_ROM_WFILL", (DESTINATION_AT, 5, 0), stale(DESTINATION_AT, 16)),
    ("3 words", "AES_ROM_WFILL", (DESTINATION_AT, 3, 7), stale(DESTINATION_AT, 16)),
    ("4 bytes", "AES_ROM_XSTRPIX_N", (DESTINATION_AT, SOURCE_AT, 4), merge_pokes({SOURCE_AT: b"a\0b\xfe"}, stale(DESTINATION_AT, 16))),
    *((f"{count} words", "AES_ROM_WCOPY", (DESTINATION_AT, SOURCE_AT, count),
       merge_pokes(words_pokes(SOURCE_AT, WCOPY_WORDS), stale(DESTINATION_AT, 16))) for count in (0, 5)),
    *((f"{len(string)} bytes", "AES_ROM_LSTRLEN", (SOURCE_AT,), text(SOURCE_AT, string)) for string in (b"", b"DESKTOP.INF")),
    *((label, "AES_ROM_LBCOPY", (SOURCE_AT + LBCOPY_SHAPES[label][0], SOURCE_AT + LBCOPY_SHAPES[label][1],
                                 LBCOPY_SHAPES[label][2]), {SOURCE_AT: ramp(LBCOPY_SPAN)})
      for label in ("a zero count moves nothing", "disjoint, forward", "overlapping, the destination above")),
    *((f"{count} bytes", "AES_ROM_MOVS", (count, SOURCE_AT, DESTINATION_AT),
       merge_pokes({SOURCE_AT: ramp(16)}, stale(DESTINATION_AT, 16))) for count in (0, 7)),
    *((f"{count} bytes", "AES_ROM_BFILL", (count, 0x1234, DESTINATION_AT), stale(DESTINATION_AT, 16)) for count in (0, 7)),
]
for _label, _name, _arguments, _pokes in _ROWS:
    strings.register(_label, _name, _arguments, _pokes)
