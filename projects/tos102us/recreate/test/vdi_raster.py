"""What the pixel / scanline batteries share (`src/vdi/raster.c`): the register contracts, a canvas whose
every plane differs from its neighbours, the colour as the VDI stages it, and the real fill patterns.

THE CONTRACTS ARE DECLARED HERE, ONCE, for every entry these batteries run — the three primitives a
program reaches through `$Axxx`, the two mid-function entries of `$a004` other routines jump into, and
the three CPU bodies behind drawing vectors 6..8, which the front ends' C calls by name. `bench/tier3.py`
builds each Tier 3 call from the same declaration. Two inputs are REGISTERS no core takes (`raster.h`):
A4 (A2 for the rectangle body) is the Line-A base, and the vertical body's D0 is 2 — so every case of
those entries stages them from `BASE_REGISTERS` rather than leaving them to the snapshot.
"""
import random
from pathlib import Path

from harness import BASE_IMAGE, addrs

import case
import vdi
from case import merge_pokes

vdi.declare_primitive("LINEA_ROM_CONCAT", arguments=("d0", "d1"), results=("d0", "d1"))
vdi.declare_primitive("LINEA_ROM_PUT_PIXEL")
vdi.declare_primitive("LINEA_ROM_GET_PIXEL", results=("d0",))
vdi.declare_primitive("LINEA_ROM_HLINE")
vdi.declare_primitive("LINEA_ROM_HLINE_PATTERNED", arguments=("d4", "d5", "d6"))
vdi.declare_primitive("LINEA_ROM_HLINE_SPAN", arguments=("d4", "d5", "d6", "a0", "d0"))
vdi.declare_primitive("LINEA_ROM_CPU_HLINE", arguments=("d0", "d1", "d2", "d4", "d5", "d6", "a0"))
vdi.declare_primitive("LINEA_ROM_FILLED_RECT")
vdi.declare_primitive("LINEA_ROM_CPU_RECT_FILL", arguments=("d0", "d1", "d4", "d5", "d6", "d7"))
vdi.declare_primitive("LINEA_ROM_LINE")
vdi.declare_primitive("LINEA_ROM_CPU_VLINE", arguments=("d4", "d5", "d6", "d7"))
vdi.declare_primitive("LINEA_ROM_LINE_PLANE_WORDS", arguments=("d3", "a2"))

# The hidden register inputs (`raster.h`): the base every caller loads, and the vertical body's D0 —
# the XOR mode number `$fca1f0` loads, which that body compares WRT_MODE against.
XOR_MODE_REGISTER = 2
BASE_REGISTERS = {"a4": vdi.LINEA_BASE}
RECT_BODY_REGISTERS = {"a2": vdi.LINEA_BASE}
VLINE_BODY_REGISTERS = {**BASE_REGISTERS, "d0": XOR_MODE_REGISTER}

# ---- this module's band of the VDI window ----------------------------------------------------------------
# At +$1800 of the VDI's window, above `test/vdi_helpers.py`'s kilobyte at +$1000 — `vdi.SPAN` refuses an
# overlap either way.
BAND_OFFSET = 0x1800
BAND_BYTES = 0x100
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_raster.py: plane words and transcription callers")

# ---- the four write modes, by `raster.h`'s names ------------------------------------------------------
HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/raster.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
MODES = {"replace": HEADER["RASTER_MODE_REPLACE"], "transparent": HEADER["RASTER_MODE_TRANSPARENT"],
         "xor": HEADER["RASTER_MODE_XOR"], "reverse": HEADER["RASTER_MODE_REVERSE"]}
MULTIFILL_PLANE_WORDS = HEADER["RASTER_MULTIFILL_PLANE_BYTES"] // vdi.WORD_BYTES
LINE_PLANES_MAX = HEADER["RASTER_LINE_PLANES_MAX"]
# `$fca3f4`'s buffer: one word a plane, at most LINE_PLANES_MAX, and the `jmp`.
PLANE_WORDS_AT = BAND_AT
PLANE_WORDS_BYTES = (LINE_PLANES_MAX + 1) * vdi.WORD_BYTES
PIXELS_PER_GROUP = vdi.PIXELS_PER_GROUP
LAST_PIXEL_IN_GROUP = PIXELS_PER_GROUP - 1

# ---- the canvas ----------------------------------------------------------------------------------------
# A screen of pseudo-random bytes: every plane of every group differs from its neighbours, so a span
# that touches one pixel too many or too few, or the wrong plane, changes a bit the ROM left alone. The
# seed is fixed so a failure reproduces.
CANVAS_SEED = 0x1D5_A003
CANVAS = {vdi.SCREEN.base: random.Random(CANVAS_SEED).randbytes(vdi.SCREEN.bytes)}
CANVAS_IMAGE = vdi.make_image(CANVAS)

# ---- the colour, as the VDI stages it --------------------------------------------------------------------
# Every VDI caller of a rasterizer stores COLBITn = colour & (1 << n) — 0, 1, 2, 4, 8, not 0/1 ($fcb638..).
COLBITS = tuple(f"COLBIT{plane}" for plane in range(vdi.SCREEN.planes))
# Colours whose planes DIFFER from each other, both ways round, and the two extremes.
COLOURS = (0b0101, 0b1010, 0, 0b1111)


def colour_pokes(colour):
    return vdi.linea_pokes(**{name: colour & (1 << plane) for plane, name in enumerate(COLBITS)})


# ---- the fill patterns the ROM really has (`vdi/vdi.h`) --------------------------------------------------
# (PATPTR, PATMSK): the one-row SOLID, an 8-row pattern style and a 16-row hatch style — each the first
# row of its table, which starts one mask word in.
SOLID = (vdi.VDI_PATTERN_SOLID, 0)
PATTERN_8_ROWS = (vdi.VDI_PATTERNS_UPPER + vdi.VDI_PATTERN_TABLE_HEADER_BYTES,
                  case.word_in(BASE_IMAGE, vdi.VDI_PATTERNS_UPPER))
HATCH_16_ROWS = (vdi.VDI_HATCHES_UPPER + vdi.VDI_PATTERN_TABLE_HEADER_BYTES,
                 case.word_in(BASE_IMAGE, vdi.VDI_HATCHES_UPPER))
PATTERNS = {"solid": SOLID, "8 rows": PATTERN_8_ROWS, "16-row hatch": HATCH_16_ROWS}
# A MULTI-PLANE user pattern where `vsf_udpat` keeps it — the physical workstation's UD_PATRN, 16 rows a
# plane — with rows that differ per plane and per row, so a wrong plane stride or row reads another word.
USER_PATTERN_AT = vdi.VDI_PHYS_WORK + vdi.field("WS", "UD_PATRN").at
USER_PATTERN_SEED = CANVAS_SEED + 1
_USER_PATTERN_WORDS = random.Random(USER_PATTERN_SEED)
USER_PATTERN_ROWS = tuple(_USER_PATTERN_WORDS.getrandbits(16) for _ in range(vdi.SCREEN.planes * MULTIFILL_PLANE_WORDS))
assert len(set(USER_PATTERN_ROWS)) == len(USER_PATTERN_ROWS), "every row of every plane its own word"
USER_PATTERN_MASK = MULTIFILL_PLANE_WORDS - 1
# The real line styles ($fd32f6): solid, long dash, dot, dash-dot, dash, dash-dot-dot.
LINE_STYLES = tuple(case.word_in(BASE_IMAGE, vdi.VDI_LINE_STYLES + index * vdi.WORD_BYTES) for index in range(6))


def pattern_pokes(name):
    """PATPTR / PATMSK for a named ROM pattern, single-plane."""
    at, mask = PATTERNS[name]
    return vdi.linea_pokes(PATPTR=at, PATMSK=mask, MULTIFILL=0)


def user_pattern_pokes():
    """The workstation's user pattern, multi-plane, as `vsf_udpat` + `vsf_interior(4)` leave it."""
    return merge_pokes(vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, UD_PATRN=USER_PATTERN_ROWS),
                       vdi.linea_pokes(PATPTR=USER_PATTERN_AT, PATMSK=USER_PATTERN_MASK, MULTIFILL=1))


# ---- the other screen shapes the ROM knows ----------------------------------------------------------------
# (planes, bytes per line) of the three ST resolutions, which concat's shift table and every plane loop
# serve; the captured machine is the first.
LOW = (4, 160)
MEDIUM = (2, 160)
HIGH = (1, 80)


def fringe_mask(index):
    """The ROM's own fringe table ($fca55c)."""
    return case.word_in(BASE_IMAGE, HEADER["RASTER_FRINGE_MASK_TABLE"] + index * vdi.WORD_BYTES)


def span_fringes(x1, x2):
    """(left group, groups past it, left mask, right mask) of x1..x2, as `$fca5a2` / `$fcfc9c` compute
    them — the registers a body case is entered with."""
    left_group = x1 // PIXELS_PER_GROUP
    words = x2 // PIXELS_PER_GROUP - left_group
    left = fringe_mask(x1 % PIXELS_PER_GROUP)
    right = ~fringe_mask(x2 % PIXELS_PER_GROUP + 1) & 0xFFFF
    return left_group, words, left & right if words == 0 else left, right


def geometry_pokes(shape):
    planes, bytes_per_line = shape
    return vdi.linea_pokes(PLANES=planes, WIDTH=bytes_per_line, BYTES_LIN=bytes_per_line)


# WIDTH one low-res group off BYTES_LIN, either way: the two fields a line's bytes are held in, made to
# disagree, so a routine that reads the wrong one lands on another row (or shears).
WIDTH_SKEWS = (-vdi.SCREEN.planes * vdi.WORD_BYTES, vdi.SCREEN.planes * vdi.WORD_BYTES)


def width_skew_pokes(skew):
    return vdi.linea_pokes(WIDTH=vdi.SCREEN.bytes_per_line + skew)


def drawing_pokes(*, mode, colour, extra=None):
    """The canvas, a write mode and a colour: what every drawing case starts from."""
    return merge_pokes(CANVAS, colour_pokes(colour), vdi.linea_pokes(WRT_MODE=MODES[mode]), extra)


# ---- the TRANSCRIPTION: `src/vdi/raster.S`, the ROM's own instructions -----------------------------------
# Every case a battery here registers for Tier 3 is registered TWICE: the C core against the ROM (the
# C row), and the `.S` the target build ships against the ROM through Tier 3's transcription relation
# (`vdi.register_transcription`) — the same image, the WHOLE register file both are entered with
# (`vdi.DIRTY`, then the case's own registers), and the same chip traffic.
#
# THE CODE POINTERS. Some routines return with an address INSIDE THEMSELVES in a register — the one
# thing a transcription linked anywhere else must differ in. Which registers, per routine, was MEASURED
# rather than read: every case entered through the plain caller, the registers that then differ are
# exactly these (everything else is equal, so it is data):
#   * the span bodies leave the write-mode arm they `jmp (a5)`ed into in A5 — A3 is the COLBIT walker
#     and A4 the last screen word, both data;
#   * the vertical body leaves its (loop, return point) pair in A3/A4 — A5 walks the column, data;
#   * `$a003`'s DIAGONAL arm leaves the same pair in A3/A4, and in A5 the octant arm's own address until
#     a pixel sets it to a screen pointer. Its vertical and horizontal arms jump through a drawing vector,
#     which is the ROM's body on BOTH sides, and leave nothing to mask.
# Each such case is entered through one of `vdi.CallerPool`'s callers, which zeroes exactly those registers
# on BOTH sides, so every other register — and these, in every routine that holds data in them — is still
# compared.
CODE_POINTERS = {"LINEA_ROM_CPU_HLINE": ("a5",), "LINEA_ROM_CPU_RECT_FILL": ("a5",), "LINEA_ROM_CPU_VLINE": ("a3", "a4")}
DIAGONAL_CODE_POINTERS = ("a3", "a4", "a5")
CODE_POINTER_CALLER_BYTES = 0x12        # room for the longest, which clears three
CALLERS = vdi.CallerPool(PLANE_WORDS_AT + PLANE_WORDS_BYTES, BAND_AT + BAND_BYTES, CODE_POINTER_CALLER_BYTES,
                         CODE_POINTERS, built=(DIAGONAL_CODE_POINTERS,))
code_pointer_caller = CALLERS.caller
caller_for = CALLERS.caller_for
run_transcription = CALLERS.run_transcription


def register(label, name, pokes, *, regs=None, c_row=True, code_pointers=None):
    """One case, registered as the C row (`vdi.register`) and as the `.S` row — `c_row=False` for a
    body whose C signature is past what a Tier 3 call can pass, which the transcription row alone
    prices."""
    if c_row:
        vdi.register(f"{vdi.core_symbol(name)}, {label}", getattr(addrs, name), pokes, regs=regs)
    vdi.register_transcription(name, label, pokes, regs, caller=caller_for(name, code_pointers))
