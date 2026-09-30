"""`src/aes/optimize.S` — the utility layer's memory and string helpers (and its rectangle helpers, whose relation
`test_aes_rect_transcription.py` runs), and the Alcyon runtime's lmul/ldiv, as the target build ships them: the ROM's
own instructions, where `strings.c` / `rect.c` are what Tier 1's host differential proves.

Every C core measures over Tier 3's 1.10 bar against the ROM's tight loops (`test_aes_strings*.py` register the C
rows), so the user's rule ships these. Two claims hold them: their BYTES are the ROM's, every one of two regions
(below), and they BEHAVE as the ROM — the image and the WHOLE register file, through Tier 3's transcription relation —
over the Tier 1 batteries' own shapes, entered through a staged caller that pushes a twelve-byte Alcyon frame.

The regions, and why each is one: `$fecb6e..$fed18d` (the optimize layer from mul_div to wildcmp, one span because
rc_equal, streq and strlen — and inside and rc_intersect, laid out though their C ships — leave through the shared
return tails at `$fed066..$fed06f`, which must lie in their users' region; the unreached code between mul_div and
set_contrl_ptr and the object-text helpers are laid out too, the latter's Line-F words as bytes no row executes), and
`$fe3db4..$fe3ea5` (lmul and ldiv, which merge_str's two `jsr`s reach: the only RELOCATED words, each pinned to the
exact address its target is linked at).
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import abi
import aes
import aes_strings as strings
import test_aes_strings as copies
import test_aes_strings_text as texts
import transcription
from aes_strings import DESTINATION_AT, SOURCE_AT, buffers, stale, text
from case import merge_pokes
from opcodes import DROP_STACK_BYTES, PUSH_RETURN_PC, PUSH_STACK_LONG, RTS
from transcription import ABSOLUTE, Relocated

# ---- the byte pin ---------------------------------------------------------------------------------------------------
OPTIMIZE_REGION = transcription.pinned_region(
    addrs.AES_ROM_MUL_DIV, addrs.AES_ROM_OB_ADDR, "AES_ROM_MUL_DIV",
    ("AES_ROM_SET_CONTRL_PTR", "AES_ROM_GET_CONTRL_PTR2", "AES_ROM_LSTCPY", "AES_ROM_XSTRPIX", "AES_ROM_WSET",
     "AES_ROM_XSTRPIX_N", "AES_ROM_WCOPY", "AES_ROM_WFILL", "AES_ROM_LSTRLEN", "AES_ROM_LBCOPY",
     "AES_ROM_R_GET", "AES_ROM_R_SET", "AES_ROM_RC_COPY", "AES_ROM_RC_EQUAL", "AES_ROM_RC_UNION", "AES_ROM_RC_CONSTRAIN",
     "AES_ROM_MOVS", "AES_ROM_MIN", "AES_ROM_MAX", "AES_ROM_BFILL", "AES_ROM_TOUPPER", "AES_ROM_STRLEN", "AES_ROM_STREQ",
     "AES_ROM_STRCPY", "AES_ROM_STRSCN", "AES_ROM_STRCAT", "AES_ROM_SCASB", "AES_ROM_STRCHK", "AES_ROM_FMT_STR",
     "AES_ROM_UNFMT_STR", "AES_ROM_MERGE_STR", "AES_ROM_WILDCMP"))
RUNTIME_REGION = transcription.pinned_region(addrs.AES_ROM_LMUL, addrs.GEM_TRAP2, "AES_ROM_LMUL",
                                             ("AES_ROM_LDIV",))
REGIONS = {"mul_div to wildcmp": OPTIMIZE_REGION, "lmul and ldiv": RUNTIME_REGION}

MERGE_STR_CALLS_LDIV = 0xFED0E8         # the operand of merge_str's `jsr $fe3e08.l`
MERGE_STR_CALLS_LMUL = 0xFED0F2         # ...and of its `jsr $fe3db4.l`
RELOCATED = {
    MERGE_STR_CALLS_LDIV: Relocated(ABSOLUTE, "AES_ROM_LMUL", "merge_str's call of ldiv, where the .S links it"),
    MERGE_STR_CALLS_LMUL: Relocated(ABSOLUTE, "AES_ROM_LMUL", "merge_str's call of lmul, where the .S links it"),
}


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_the_transcription_is_the_rom_s_bytes_exactly(region):
    """THE BYTE PIN: every word the ROM's but merge_str's two call operands, each the address its target is linked
    at — where GNU as would choose another encoding, `optimize.S` spells the ROM's words (`m68k_encodings.h`)."""
    transcription.assert_transcribed(REGIONS[region], relocated=RELOCATED)


def test_the_regions_end_on_the_rom_s_own_rts():
    """ldiv's last `rts` is the word before the `trap #2` handler, wildcmp's the word before OB_ADDR — where the
    optimize region stops."""
    for region in (OPTIMIZE_REGION, RUNTIME_REGION):
        assert bytes(BASE_IMAGE[region.hi - len(RTS):region.hi]) == RTS
    assert OPTIMIZE_REGION.hi == addrs.AES_ROM_OB_ADDR


# ---- the frame caller: a `jsr` with a twelve-byte Alcyon frame ------------------------------------------------------
# `transcription.run_transcription` enters both sides at a staged caller that jumps through the routine longword at
# `abi.FIRST_ARG`; an Alcyon routine would read that longword as its first argument, so the frame is staged ABOVE it
# (`FRAME_ARGUMENTS_AT`) and the caller pushes three longwords of it — merge_str's twelve bytes, the widest of these
# frames — calls, and drops them. It touches no register, and what it costs comes off both columns.
FRAME_ARGUMENTS_AT = abi.FIRST_ARG + aes.LONG_BYTES
FRAME_LONGS = 3
FRAME_ARGUMENT_BYTES = FRAME_LONGS * aes.LONG_BYTES
_FROM_ENTRY_SP = 16         # the third frame longword from the caller's entry SP: sentinel, routine, first, second
_TO_RETURN = 8              # `pea` to the `lea` after the `rts`, from the `pea`'s own extension word
_TO_ROUTINE = 20            # the routine longword once the frame and the return are pushed
FRAME_CALLER_STUB = (FRAME_LONGS * (PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP))
                     + PUSH_RETURN_PC + struct.pack(">h", _TO_RETURN)
                     + PUSH_STACK_LONG + struct.pack(">h", _TO_ROUTINE)
                     + RTS                                                        # into the routine
                     + DROP_STACK_BYTES + struct.pack(">h", FRAME_ARGUMENT_BYTES)
                     + RTS)
FRAME_CALLER_COST = (8, 152)
FRAME_CALLER = transcription.staged_caller(strings.CALLERS_AT, FRAME_CALLER_STUB, FRAME_CALLER_COST)


def framed(name, arguments, pokes):
    """`pokes` with `name`'s Alcyon frame of `arguments` where the frame caller reads it."""
    (_at, frame), = aes.alcyon_frame(name, *arguments).items()
    assert len(frame) <= FRAME_ARGUMENT_BYTES
    return merge_pokes(pokes, {FRAME_ARGUMENTS_AT: frame})


def run_transcription(name, arguments, pokes=None):
    return transcription.run_transcription(name, framed(name, arguments, pokes), caller=FRAME_CALLER)


def register_transcription(label, name, arguments, pokes=None):
    return transcription.register_transcription(name, label, framed(name, arguments, pokes), caller=FRAME_CALLER)


# ---- the relation, over the batteries' own shapes --------------------------------------------------------------------
def shapes():
    """(id, name, arguments, pokes): every routine over the shapes its Tier 1 battery proves the C over."""
    out = [(f"mul_div {label}", "AES_ROM_MUL_DIV", arguments, None) for label, arguments in copies.MUL_DIV.items()]
    out += [("set_contrl_ptr", "AES_ROM_SET_CONTRL_PTR", (0x5A0789AB,), None),
            ("get_contrl_ptr2", "AES_ROM_GET_CONTRL_PTR2", (strings.ANSWER_AT,),
             merge_pokes(aes.field_pokes("AES", GSX_CONTRL_PTR2=copies.CONTRL_PTR2), stale(strings.ANSWER_AT, 4)))]
    out += [(f"{name.lower()} {label}", name, pair, None) for label, pair in copies.PAIRS.items()
            for name in ("AES_ROM_MIN", "AES_ROM_MAX")]
    out += [(f"toupper {label}", "AES_ROM_TOUPPER", (character,), None) for label, (character, _) in copies.TOUPPER.items()]
    out += [(f"lmul {label}", "AES_ROM_LMUL", (left & copies.LONG_MASK, right & copies.LONG_MASK), None)
            for label, (left, right) in copies.LMUL.items()]
    out += [(f"ldiv {label}", "AES_ROM_LDIV", (dividend & copies.LONG_MASK, divisor & copies.LONG_MASK),
             stale(aes.AES_LDIV_REMAINDER, 4)) for label, (dividend, divisor) in copies.LDIV.items()]
    out += [(f"lstcpy {label}", "AES_ROM_LSTCPY", (DESTINATION_AT, SOURCE_AT), buffers(source))
            for label, source in copies.LSTCPY.items()]
    out += [(f"xstrpix {label}", "AES_ROM_XSTRPIX", (DESTINATION_AT, SOURCE_AT),
             merge_pokes(text(SOURCE_AT, source), stale(DESTINATION_AT, strings.BUFFER_BYTES)))
            for label, source in copies.XSTRPIX.items()]
    out += [(f"wset {count}", "AES_ROM_WSET", (DESTINATION_AT, count, 0x1234), stale(DESTINATION_AT, 16)) for count in (0, 1, 5)]
    out += [(f"wfill {count} of {value}", "AES_ROM_WFILL", (DESTINATION_AT, count, value), stale(DESTINATION_AT, 16))
            for count, value in ((3, 7), (5, 0))]
    out += [("xstrpix_n", "AES_ROM_XSTRPIX_N", (DESTINATION_AT, SOURCE_AT, 4), merge_pokes({SOURCE_AT: b"a\0b\xfe"},
                                                                                         stale(DESTINATION_AT, 16)))]
    out += [(f"wcopy {count}", "AES_ROM_WCOPY", (DESTINATION_AT, SOURCE_AT, count),
             merge_pokes(copies.words_pokes(SOURCE_AT, copies.WCOPY_WORDS), stale(DESTINATION_AT, 16))) for count in (0, 5)]
    out += [(f"lstrlen {len(string)}", "AES_ROM_LSTRLEN", (SOURCE_AT,), text(SOURCE_AT, string)) for string in (b"", b"abc")]
    out += [(f"lbcopy {label}", "AES_ROM_LBCOPY", (SOURCE_AT + destination, SOURCE_AT + source, count),
             {SOURCE_AT: copies.ramp(copies.LBCOPY_SPAN)})
            for label, (destination, source, count) in copies.LBCOPY_SHAPES.items()]
    out += [("lbcopy the signed compare", "AES_ROM_LBCOPY", (SOURCE_AT, (SOURCE_AT + 2) | 0xFF000000, 6),
             {SOURCE_AT: copies.ramp(copies.LBCOPY_SPAN)})]
    out += [(f"movs {count}", "AES_ROM_MOVS", (count, SOURCE_AT, DESTINATION_AT),
             merge_pokes({SOURCE_AT: copies.ramp(16)}, stale(DESTINATION_AT, 16))) for count in (0, 7)]
    out += [(f"bfill {count}", "AES_ROM_BFILL", (count, 0x1234, DESTINATION_AT), stale(DESTINATION_AT, 16)) for count in (0, 7)]
    out += [(f"strlen {len(string)}", "AES_ROM_STRLEN", (SOURCE_AT,), text(SOURCE_AT, string)) for string in (b"", b"abc")]
    out += [(f"{name.lower()} {label}", name, (SOURCE_AT, DESTINATION_AT), texts.pair_pokes(*pair))
            for label, pair in texts.PAIRS.items() for name in ("AES_ROM_STREQ", "AES_ROM_STRCHK")]
    out += [(f"strcpy {len(source)}", "AES_ROM_STRCPY", (SOURCE_AT, DESTINATION_AT), buffers(source))
            for source in (b"", b"A:\\DESKTOP.INF")]
    out += [(f"strcat onto {len(destination)}", "AES_ROM_STRCAT", (SOURCE_AT, DESTINATION_AT), buffers(b"*.*", destination))
            for destination in (b"", b"A:\\")]
    out += [(f"strscn {label}", "AES_ROM_STRSCN", (SOURCE_AT, DESTINATION_AT, stop), buffers(source))
            for label, (source, stop, _copied) in texts.STRSCN.items()]
    out += [(f"scasb {label}", "AES_ROM_SCASB", (SOURCE_AT, character), text(SOURCE_AT, string))
            for label, (string, character, _index) in texts.SCASB.items()]
    out += [(f"fmt_str {label}", "AES_ROM_FMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(name))
            for label, (name, _form) in texts.FMT_STR.items()]
    out += [(f"unfmt_str {label}", "AES_ROM_UNFMT_STR", (SOURCE_AT, DESTINATION_AT), buffers(form))
            for label, (form, _name) in texts.UNFMT_STR.items()]
    out += [(f"merge_str {label}", "AES_ROM_MERGE_STR", texts.MERGE_ARGUMENTS, texts.merge_pokes_of(*arguments))
            for label, (arguments, _merged) in texts.MERGE.items()]
    out += [(f"wildcmp {label}", "AES_ROM_WILDCMP", (SOURCE_AT, DESTINATION_AT), texts.pair_pokes(pattern, name))
            for label, (pattern, name, _matched) in texts.WILDCMP.items()]
    return out


SHAPES = {label: (name, arguments, pokes) for label, name, arguments, pokes in shapes()}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_transcription_behaves_as_the_rom(shape):
    name, arguments, pokes = SHAPES[shape]
    run_transcription(name, arguments, pokes)


# ---- Tier 3: the .S rows, each routine's dearest realistic shape ----------------------------------------------------
TIER3 = ("mul_div a slider: 37 of 480 over 1000", "set_contrl_ptr", "get_contrl_ptr2", "aes_rom_min descending",
         "aes_rom_max ascending", "toupper a", "lmul a negative factor", "ldiv a large dividend: bit by bit",
         "lstcpy a name", "xstrpix a label", "wset 5", "wfill 3 of 7", "xstrpix_n", "wcopy 5", "lstrlen 3",
         "lbcopy overlapping, the destination above", "movs 7", "bfill 7", "strlen 3", "aes_rom_streq equal",
         "aes_rom_strchk one byte differs", "strcpy 14", "strcat onto 3", "strscn up to the stop", "scasb found",
         "fmt_str a name and an extension", "unfmt_str a padded name", "merge_str the desk's info line",
         "wildcmp *.* against a name")
for _label in TIER3:
    register_transcription(_label, *SHAPES[_label])
