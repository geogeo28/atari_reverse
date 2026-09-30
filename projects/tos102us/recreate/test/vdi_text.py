"""What the text raster's batteries share (`src/vdi/text_raster.c`): the register contracts, the three ROM
fonts' REAL glyphs staged as v_gtext stages them, the effects and scaling a text call carries, and the
transcription callers the CPU bodies are entered through.

THE GLYPHS ARE THE ROM'S. A case names a font and a character; the source rectangle, the form and its width
are read out of that font's header and offset table exactly as v_gtext reads them ($fcdbbe..$fcdc2a), and
the effects' parameters out of the same header ($fcd79c..$fcd7ee). A Line-A program stages TextBlt's
variables itself, and its cases go further on the same forms — a DELX spanning several characters of the
form, which is what reaches the multi-word row loops, and the BitBlt write modes 4..19.
"""
import ctypes
import random
import struct
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu

import abi
import case
import transcription
import vdi
import vdi_helpers
import vdi_raster
from case import merge_pokes
from opcodes import CLEAR_ADDRESS_REGISTER, PUSH_RETURN_PC, PUSH_STACK_LONG, RTS

vdi.declare_primitive("LINEA_ROM_TEXTBLT")
vdi.declare_primitive("LINEA_ROM_FAST_TEXT", results=("d0",))

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/text_raster.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
QUARTER_TURN, HALF_TURN, THREE_QUARTER_TURN = (HEADER["TEXT_ROTATION_90"], HEADER["TEXT_ROTATION_180"],
                                               HEADER["TEXT_ROTATION_270"])
ROTATIONS = (0, QUARTER_TURN, HALF_TURN, THREE_QUARTER_TURN)
FULL_TURN = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/helpers.h",
                        known={**addrs.ADDRS, **vdi.CONSTANTS})["VDI_TENTHS_PER_TURN"]
FAST_GLYPH_PIXELS = 1 << HEADER["TEXT_FAST_GLYPH_SHIFT"]

# ---- the fonts ---------------------------------------------------------------------------------------------
FONTS = {"6x6": vdi.FONT_ROM_6X6, "8x8": vdi.FONT_ROM_8X8, "8x16": vdi.FONT_ROM_8X16}


def font_field(font, name):
    """A field of a ROM font's header, as the capture holds it."""
    return vdi.read_field(BASE_IMAGE, "FONT", name, FONTS[font])


def glyph(font, character):
    """(SOURCEX, DELX) of `character` in `font`: its entry of the offset table and the next one's."""
    at = font_field(font, "OFF_TABLE") + (character - font_field(font, "FIRST_ADE")) * vdi.WORD_BYTES
    left = case.word_in(BASE_IMAGE, at)
    return left, case.word_in(BASE_IMAGE, at + vdi.WORD_BYTES) - left


# ---- the effects: LINEA_STYLE's bits, and what v_gtext stores for each ---------------------------------------
THICKEN = vdi.VDI_STYLE_THICKEN_MASK
LIGHTEN = vdi.VDI_STYLE_LIGHTEN_MASK
SKEW = vdi.VDI_STYLE_SKEW_MASK
OUTLINE = vdi.VDI_STYLE_OUTLINE_MASK
UNDERLINE = 0x0008              # the bit TextBlt never reads: v_gtext draws the underline itself


def effect_pokes(font, style):
    """STYLE and the parameters v_gtext takes from the font for it: WEIGHT, LITEMASK, and for italics the
    two offsets and SKEWMASK — which it clears to 0 otherwise ($fcd7e4)."""
    values = {"STYLE": style, "MONO_STATUS": font_field(font, "FLAGS") & vdi.FONT_FLAG_MONOSPACE_MASK}
    if style & THICKEN:
        values["WEIGHT"] = font_field(font, "THICKEN")
    if style & LIGHTEN:
        values["LITEMASK"] = font_field(font, "LIGHTEN")
    if style & SKEW:
        values.update(L_OFF=font_field(font, "LEFT_OFFSET"), R_OFF=font_field(font, "RIGHT_OFFSET"),
                      SKEWMASK=font_field(font, "SKEW"))
    else:
        values.update(L_OFF=0, R_OFF=0)
    return vdi.linea_pokes(**values)


# ---- scaling: what vst_height leaves the dispatcher to copy --------------------------------------------------
_CLC_DDA_IMAGE = (ctypes.c_uint8 * (vdi.LINEA_T_SCLSTS + vdi.WORD_BYTES))()


def scale_pokes(font, requested):
    """SCALE on, and the DDA vst_height computes for a font of FORM_HEIGHT drawn `requested` high — the
    reconstructed `clc_dda` (`src/vdi/helpers.c`, verified against the ROM), whose answer and direction are
    what the dispatcher copies into DDA_INC and T_SCLSTS; XACC_DDA starts half full, as v_gtext sets it
    ($fcdbae)."""
    increment = vdi_helpers.core("VDI_ROM_CLC_DDA")(_CLC_DDA_IMAGE, font_field(font, "FORM_HEIGHT"), requested)
    direction = int.from_bytes(bytes(_CLC_DDA_IMAGE[vdi.LINEA_T_SCLSTS:vdi.LINEA_T_SCLSTS + 2]), "big")
    return vdi.linea_pokes(SCALE=1, DDA_INC=increment, T_SCLSTS=direction,
                           XACC_DDA=vdi_helpers.CONSTANTS["VDI_DDA_ACCUMULATOR_START"])


# ---- the scratch buffer --------------------------------------------------------------------------------------
# The workstation's effects buffer, where the snapshot's dispatcher left SCRTCHP / SCRPT2: two halves the
# transforms take in turn. Staged STALE — pseudo-random, as a previous glyph would leave it — so a byte the
# reconstruction writes and the ROM does not, or the reverse, is a byte that differs.
SCRATCH_AT = vdi.linea(BASE_IMAGE, "SCRTCHP")
SCRATCH_HALF = vdi.linea(BASE_IMAGE, "SCRPT2")
SCRATCH_BYTES = 2 * SCRATCH_HALF
SCRATCH_SEED = 0x7E47_B17
SCRATCH = {SCRATCH_AT: random.Random(SCRATCH_SEED).randbytes(SCRATCH_BYTES)}
assert vdi.VDI_SCRATCH <= SCRATCH_AT and SCRATCH_AT + SCRATCH_BYTES <= vdi.VDI_PTSIN_COPY, (
    "the effects buffer is inside the VDI scratch every case may stage")

# ---- the write modes -------------------------------------------------------------------------------------------
MODES = dict(vdi_raster.MODES)
BITBLT_MODES = range(len(MODES), len(MODES) + HEADER["TEXT_OP_COUNT"])    # WRT_MODE 4..19: the logic ops


def mode_number(mode):
    return MODES[mode] if isinstance(mode, str) else mode


def _op_fragments():
    """Every fragment offset the two op tables list — what a chain of fragments ends in."""
    tables = (HEADER["TEXT_OP_MASKED_TABLE"], HEADER["TEXT_OP_WHOLE_TABLE"])
    return {case.word_in(BASE_IMAGE, table + op * vdi.WORD_BYTES) for table in tables
            for op in range(HEADER["TEXT_OP_COUNT"])}


# The largest WRT_MODE whose index, mode * 4 + 3, is still a word; and the part of the index the table's
# byte does not replace.
LAST_WORD_MODE = 0x3FFF
INDEX_HIGH_BYTE = 0xFF00
# The ROM region `text_raster.S` transcribes whole — the CPU bodies with every table TextBlt reads — which
# `test_vdi_text_raster_transcription.py` byte-pins.
BODIES_REGION = (0xFD1CC4, 0xFD2D32)


def op_slots(mode, colour_bit, background_bit):
    """($fd233c..$fd2360) the op index a plane of `mode` takes — WRT_MODE * 4 + fg * 2 + bg, sign-extended
    into the byte table's address, its low byte replaced by the byte found there — and the two words it
    names in the masked and the whole fragment table, or None for both when the index is ODD (the ROM's
    address error: the words are never read). Answers (index, byte table address, masked, whole)."""
    word = mode * 4 + colour_bit * 2 + background_bit
    byte_at = HEADER["TEXT_OP_INDEX_TABLE"] + vdi.signed_word(word)
    index = vdi.signed_word((word & INDEX_HIGH_BYTE) | BASE_IMAGE[byte_at])
    if index % 2:
        return index, byte_at, None, None
    return (index, byte_at, case.word_in(BASE_IMAGE, HEADER["TEXT_OP_MASKED_TABLE"] + index),
            case.word_in(BASE_IMAGE, HEADER["TEXT_OP_WHOLE_TABLE"] + index))


def _reads_inside(mode, lo, hi):
    """Whether every table read `mode`'s planes make — the byte, and for an even index both words — is in
    [lo, hi)."""
    for colour_bit in (0, 1):
        for background_bit in (0, 1):
            index, byte_at, masked, _whole = op_slots(mode, colour_bit, background_bit)
            reads = [(byte_at, 1)]
            if masked is not None:
                reads += [(HEADER[table] + index, vdi.WORD_BYTES) for table in ("TEXT_OP_MASKED_TABLE", "TEXT_OP_WHOLE_TABLE")]
            if not all(lo <= at and at + size <= hi for at, size in reads):
                return False
    return True


def _last_mode_inside_the_tables():
    mode = len(MODES) + len(BITBLT_MODES)
    while _reads_inside(mode, *BODIES_REGION):
        mode += 1
    return mode - 1


# The last WRT_MODE whose every table read stays inside the region `text_raster.S` transcribes (576: the byte
# table walks the rest of TextBlt's own code). Past it the ROM's PC-relative reads walk into its font data,
# and a transcription linked anywhere else reads whatever follows it: the `.S` is held to the ROM up to here.
LAST_MODE_INSIDE_THE_TABLES = _last_mode_inside_the_tables()


def _stray(accept):
    """(WRT_MODE, colour bit, background bit) past 19 with an EVEN op index whose two slots `accept(masked is
    an op, whole is an op)`."""
    fragments = _op_fragments()
    stray = []
    for mode in range(len(MODES) + len(BITBLT_MODES), LAST_WORD_MODE + 1):
        for colour_bit in (0, 1):
            for background_bit in (0, 1):
                _index, _byte_at, masked, whole = op_slots(mode, colour_bit, background_bit)
                if masked is not None and accept(masked in fragments, whole in fragments):
                    stray.append((mode, colour_bit, background_bit))
    return stray


def stray_modes():
    """The modes past 19 TextBlt draws with an op, any row: both slots (`op_slots`) name ops. The byte
    table's neighbours — the easter egg — give some between 20 and 63; past 63 the index's high byte walks
    the tables through TextBlt's own code, and past 1,000 into the ROM font's data, whose words happen to be
    op offsets for a handful more."""
    return _stray(lambda masked, whole: masked and whole)


def masked_only_modes():
    """The modes past 19 whose MASKED slot names an op and whose whole slot does not: a one- or two-word row
    runs the masked fragment alone and draws; a wider row reaches the whole slot, and halts."""
    return _stray(lambda masked, whole: masked and not whole)


def refusal(pokes):
    """What vector 9's C body says over `pokes` in a CHILD process (`vdi_helpers.refusal_over`), where its halt
    can end the run without ending pytest's — or its spin be timed out. Answers (returncode, stderr)."""
    returncode, stderr, _image = vdi_helpers.refusal_over("linea_cpu_textblt", pokes, read_back=False)
    return returncode, stderr


# ---- the window ----------------------------------------------------------------------------------------------
# (xmin, ymin, xmax, ymax), inclusive — the snapshot's is the desktop below its menu bar.
WINDOW = (vdi.linea(BASE_IMAGE, "XMINCL"), vdi.linea(BASE_IMAGE, "YMINCL"),
          vdi.linea(BASE_IMAGE, "XMAXCL"), vdi.linea(BASE_IMAGE, "YMAXCL"))
TIGHT = (97, 51, 170, 80)


def clip_pokes(window):
    """CLIP on over `window`, or off for None."""
    if window is None:
        return vdi.linea_pokes(CLIP=0)
    xmin, ymin, xmax, ymax = window
    return vdi.linea_pokes(CLIP=1, XMINCL=xmin, YMINCL=ymin, XMAXCL=xmax, YMAXCL=ymax)


def textblt_pokes(font="8x16", character=ord("A"), *, x=101, y=60, style=0, mode="replace", colour=0b1010,
                  background=0b0101, window=WINDOW, chup=0, scale=None, width=None, extra=None):
    """One glyph as v_gtext hands it to $a008, over the canvas and a stale scratch buffer: `width` widens
    DELX past the character (a Line-A caller's run of the form); `scale` is a requested height."""
    source_x, glyph_width = glyph(font, character)
    staged = vdi.linea_pokes(FBASE=font_field(font, "DAT_TABLE"), FWIDTH=font_field(font, "FORM_WIDTH"),
                             SOURCEX=source_x, SOURCEY=0, DELX=glyph_width if width is None else width,
                             DELY=font_field(font, "FORM_HEIGHT"), DESTX=x, DESTY=y, WRT_MODE=mode_number(mode),
                             TEXT_FG=colour, TEXT_BG=background, CHUP=chup, SCALE=0)
    scaled = scale_pokes(font, scale) if scale is not None else None
    return merge_pokes(vdi_raster.CANVAS, SCRATCH, staged, effect_pokes(font, style), clip_pokes(window), scaled, extra)


# NOT POISONED: the attribution pass inverts every byte the ROM wrote, and TextBlt writes back its own
# inputs — DESTX/DESTY/DELX/DELY, STYLE, WRT_MODE, SKEWMASK, SOURCEX/SOURCEY — so the pass would hand both
# cores a glyph 65,000 rows high. What that pass is for, a store the reconstruction skipped where the byte
# already held the answer, is pinned instead by cases that CHANGE each of those fields before it is
# restored (a pre-pass, a rotation, a clip, a WEIGHT of 0) and by the stale scratch buffer.
TEXTBLT_UNPOISONED = dict(poison=False)


def run_textblt(pokes, **kwargs):
    return vdi.run_primitive("LINEA_ROM_TEXTBLT", {}, pokes, **{**TEXTBLT_UNPOISONED, **kwargs})


# ---- the fast path -----------------------------------------------------------------------------------------------

GTEXT_OPCODE = 8               # v_gtext's contrl[0] — which the fast path does not read; contrl[3] it does


def codes(text):
    """A string's intin words: each character's code, or the code itself where the string gives a number."""
    return tuple(ord(character) if isinstance(character, str) else character for character in text)


def fast_text_pokes(text, *, font="8x16", x=96, y=60, mode="replace", colour=0b1010, window=WINDOW, extra=None):
    """A string as v_gtext stages it before `jsr $fcf96a`: the characters in intin and their count in
    contrl[3], DESTX/DESTY/DELY, the form, and the colour."""
    characters = codes(text)
    arrays = {vdi.CONTRL_AT: vdi.contrl(GTEXT_OPCODE, 0, len(characters))}
    if characters:
        arrays[vdi.INTIN_AT] = vdi.pack_words(*characters)
    staged = vdi.linea_pokes(FBASE=font_field(font, "DAT_TABLE"), FWIDTH=font_field(font, "FORM_WIDTH"),
                             DELY=font_field(font, "FORM_HEIGHT"), DESTX=x, DESTY=y, WRT_MODE=mode_number(mode),
                             TEXT_FG=colour)
    return merge_pokes(vdi_raster.CANVAS, vdi.pointer_pokes(), arrays, staged, clip_pokes(window), extra)


def run_fast_text(pokes, **kwargs):
    return vdi.run_primitive("LINEA_ROM_FAST_TEXT", {}, pokes, **kwargs)


# ---- the TRANSCRIPTION's callers: `src/vdi/text_raster.S` ---------------------------------------------------
# The front ends are entered through the plain caller and jump through their vectors into the ROM's bodies on
# BOTH sides. The BODIES are entered below the frame their front ends build — TextBlt's A5/A6 under the return
# address, the fast path's A5 — so each has a caller that builds it and jumps through the routine slot, and is
# measured over its body's own epilogue (`transcription.staged_caller`'s stand-in). TextBlt's body leaves A3 at its
# fragment base — a code address, the ROM's or the blob's — which its caller clears on the way out on both
# sides; every other register is compared.
BAND_OFFSET = 0x1A00
BAND_BYTES = 0x40
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_text.py: the CPU bodies' transcription callers")

PUSH_A5_A6 = b"\x48\xe7\x00\x06"            # movem.l a5-a6,-(sp)
POP_A5_A6 = b"\x4c\xdf\x60\x00"             # movem.l (sp)+,a5-a6
PUSH_A5 = b"\x2f\x0d"                       # move.l  a5,-(sp)
POP_A5 = b"\x2a\x5f"                        # movea.l (sp)+,a5
LOAD_A6_ABSOLUTE = b"\x4d\xf9"              # lea     <xxx>.l,a6
LOAD_A5_ABSOLUTE = b"\x4b\xf9"              # lea     <xxx>.l,a5
CLEAR_A3 = CLEAR_ADDRESS_REGISTER["a3"]
_JUMP_BYTES = len(PUSH_STACK_LONG) + vdi.WORD_BYTES + len(RTS)


def _body_caller(at, frame_code, pushed_bytes, back_code, cost, routine, routine_cost):
    """`pea back(pc)`, the front end's own pushes and loads, a jump through the routine slot (now
    `pushed_bytes` further up), and `back_code` + `rts` on the way out."""
    to_back = len(frame_code) + _JUMP_BYTES + vdi.WORD_BYTES
    slot = abi.FIRST_ARG - emu.STACK_TOP + vdi.LONG_BYTES + pushed_bytes
    stub = (PUSH_RETURN_PC + struct.pack(">h", to_back) + frame_code
            + PUSH_STACK_LONG + struct.pack(">h", slot) + RTS + back_code + RTS)
    return transcription.staged_caller(at, stub, cost, routine=routine, routine_cost=routine_cost)


# (instructions, cycles) of each caller and of its body's epilogue — declared, and measured against every
# declaration by `test_transcribed.py` (`transcription.assert_caller_cost`).
TEXTBLT_BODY_CALLER_COST = (7, 114)
TEXTBLT_EPILOGUE_COST = (2, 44)
FAST_BODY_CALLER_COST = (6, 96)
FAST_EPILOGUE_COST = (2, 28)
TEXTBLT_BODY_CALLER = _body_caller(
    BAND_AT, PUSH_A5_A6 + LOAD_A6_ABSOLUTE + struct.pack(">I", vdi.LINEA_BASE), 2 * vdi.LONG_BYTES, CLEAR_A3,
    TEXTBLT_BODY_CALLER_COST, POP_A5_A6 + RTS, TEXTBLT_EPILOGUE_COST)
FAST_BODY_CALLER = _body_caller(
    BAND_AT + BAND_BYTES // 2, PUSH_A5 + LOAD_A5_ABSOLUTE + struct.pack(">I", vdi.LINEA_FBASE), vdi.LONG_BYTES,
    b"", FAST_BODY_CALLER_COST, POP_A5 + RTS, FAST_EPILOGUE_COST)
BODY_CALLERS = {"LINEA_ROM_CPU_TEXTBLT": TEXTBLT_BODY_CALLER, "LINEA_ROM_CPU_FAST_TEXT": FAST_BODY_CALLER}
assert all(len(caller.stub) <= BAND_BYTES // 2 for caller in BODY_CALLERS.values())


def run_transcription(name, pokes, regs=None):
    """`text_raster.S`'s `name` against the ROM routine, through the transcription relation."""
    return transcription.run_transcription(name, pokes, regs, caller=BODY_CALLERS.get(name, transcription.PLAIN_CALLER))


def register_transcription(name, label, pokes, regs=None):
    transcription.register_transcription(name, label, pokes, regs, caller=BODY_CALLERS.get(name, transcription.PLAIN_CALLER))


def fast_body_registers(pokes):
    """What `$fcf9bc` hands vector 5: D0-D3 = DESTX, DESTY, contrl[3], DELY — read out of the staged pokes."""
    image = vdi.make_image(pokes)
    count = case.word_in(image, vdi.linea(image, "CONTRL") + vdi.CONTRL_N_INTIN)
    return {"d0": vdi.linea(image, "DESTX"), "d1": vdi.linea(image, "DESTY"), "d2": count, "d3": vdi.linea(image, "DELY")}
