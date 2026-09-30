"""What the bit-block batteries share (`src/vdi/blit.c`): the register contracts, the forms a blit reads
and writes, the BITBLT block as $a007 is handed it, and the MFDB call as $a00e and the VDI stage it.

THE CONTRACTS, declared once here for every entry the batteries run: $a007 takes its block in A6; the
engine D0/D2/D4/D6 = source x min, destination x min, source x max, destination x max and A6 = the
block's FRAME (block + 76, the `link` frame the engine reads it as); $a00e reads everything through the
Line-A pointers. None answers in a register the C models — the transcription relation holds the `.S`
to the whole file.

THE FORMS. The screen, as the canvas every raster battery draws on (`vdi_raster.CANVAS`: every plane of
every group its own pseudo-random word, so one pixel too many, one too few, or the wrong plane is a
changed bit); and two OFF-SCREEN forms of their own, also pseudo-random, for the depths and strides the
screen does not have — in the free RAM above the stack band, claimed there and held dead below.
"""
import random
from collections import namedtuple

from harness import addrs

import routines
import staging
import transcription
import vdi
import vdi_raster
from case import merge_pokes

vdi.declare_primitive("LINEA_ROM_CPU_BLIT", arguments=("d0", "d2", "d4", "d6", "a6"))
vdi.declare_primitive("LINEA_ROM_BITBLT", arguments=("a6",))
vdi.declare_primitive("LINEA_ROM_COPY_RASTER")

HEADER = addrs.parse(vdi._INCLUDE / "vdi" / "blit.h", known={**addrs.ADDRS, **vdi.CONSTANTS})
OPS = range(HEADER["BLIT_OP_COUNT"])
OP_S = HEADER["BLIT_OP_S"]
OP_D = HEADER["BLIT_OP_D"]
MODES = {"replace": HEADER["BLIT_MODE_REPLACE"], "transparent": HEADER["BLIT_MODE_TRANSPARENT"],
         "xor": HEADER["BLIT_MODE_XOR"], "reverse": HEADER["BLIT_MODE_REVERSE"]}
PATTERN_MODE = 1 << HEADER["BLIT_PATTERN_MODE_BIT"]
FRAME_BYTES = vdi.BITBLT_BYTES
PIXELS_PER_GROUP = vdi.PIXELS_PER_GROUP
WORD_BYTES = vdi.WORD_BYTES
SCREEN = vdi.SCREEN

# ---- the forms ----------------------------------------------------------------------------------------
# (base, planes, bytes per line): a form as a blit addresses it — planes interleaved word by word, as
# the screen is. `next_word` is the planes' words, `next_plane` one word.
Form = namedtuple("Form", "base planes line_bytes")
SCREEN_FORM = Form(SCREEN.base, SCREEN.planes, SCREEN.bytes_per_line)
FORMS_BYTES = 0x2000
FORMS_BASE = 0xD4000                    # in the free RAM above the stack band, clear of every other claim
FORMS_AT = staging.HIGH_BANDS.claim(FORMS_BASE, FORMS_BYTES, "test/vdi_blit.py: two off-screen forms")
FORM_BYTES = FORMS_BYTES // 2
FORMS_SEED = 0xB117_A007
FORMS = {FORMS_AT: random.Random(FORMS_SEED).randbytes(FORMS_BYTES)}
# Two forms of 160 bytes a line, 25 lines: 80 words wide at one plane, 40 at two, 20 at four.
FORM_LINE_BYTES = 160


def off_screen(which, planes):
    """Off-screen form `which` (0 or 1), `planes` deep."""
    return Form(FORMS_AT + which * FORM_BYTES, planes, FORM_LINE_BYTES)


def canvas(extra=None):
    """The screen canvas and both off-screen forms: what every blit case starts from."""
    return merge_pokes(vdi_raster.CANVAS, FORMS, extra)


# ---- the $a007 block ----------------------------------------------------------------------------------
BLOCK_AT = vdi.BITBLT_AT
FRAME_AT = BLOCK_AT + FRAME_BYTES
SPACE_BYTES = vdi.field("BITBLT", "SPACE").count


def block_pokes(*, size, source, destination, source_form=SCREEN_FORM, destination_form=SCREEN_FORM,
                planes=None, ops=(OP_S,), foreground=0, background=0, pattern=None, source_next_plane=None,
                at=BLOCK_AT, **fields):
    """A BITBLT block copying `size` = (width, height) from `source` = (x, y) of `source_form` to
    `destination` of `destination_form`, `planes` of them (the destination's by default), OP_TAB =
    `ops` (up to four bytes), the two colours, and — `pattern` = (address, next line, next plane, mask)
    — a pattern. `fields` override anything by name, the engine's scratch included."""
    (width, height), (source_x, source_y), (destination_x, destination_y) = size, source, destination
    op_table = bytes(ops) + bytes([vdi.FILL]) * (vdi.BITBLT_OP_TAB_BYTES - len(ops))
    values = dict(B_WD=width, B_HT=height, PLANE_CT=destination_form.planes if planes is None else planes,
                  FG_COL=foreground, BG_COL=background, OP_TAB=op_table,
                  S_XMIN=source_x, S_YMIN=source_y, S_FORM=source_form.base,
                  S_NXWD=source_form.planes * WORD_BYTES, S_NXLN=source_form.line_bytes,
                  S_NXPL=WORD_BYTES if source_next_plane is None else source_next_plane,
                  D_XMIN=destination_x, D_YMIN=destination_y, D_FORM=destination_form.base,
                  D_NXWD=destination_form.planes * WORD_BYTES, D_NXLN=destination_form.line_bytes,
                  D_NXPL=WORD_BYTES, SPACE=bytes([vdi.FILL]) * SPACE_BYTES)
    if pattern is None:
        # The pattern fields a case without one does not use, staged stale so a store the reconstruction
        # makes and the ROM does not (or the reverse) is a changed word — the pattern's row step is negated
        # going backwards whether or not there is a pattern.
        values.update(P_ADDR=0, P_NXLN=vdi.STALE_WORD, P_NXPL=vdi.STALE_WORD, P_MASK=vdi.STALE_WORD)
    else:
        values.update(zip(("P_ADDR", "P_NXLN", "P_NXPL", "P_MASK"), pattern))
    # the named fields laid OVER the scratch they sit in, as a second layer
    return merge_pokes(vdi.bitblt_pokes(at, **values), vdi.bitblt_pokes(at, **fields))


def far_corners(size, source, destination):
    """What $a007 computes and the engine's direct entry is handed: (sx2, sy2, dx2, dy2)."""
    (width, height), (source_x, source_y), (destination_x, destination_y) = size, source, destination
    return (source_x + width - 1, source_y + height - 1, destination_x + width - 1, destination_y + height - 1)


def engine_registers(size, source, destination, frame=FRAME_AT):
    """The engine entered as the front ends enter it: the x edges in registers, A6 the frame."""
    source_x_max, _sy, destination_x_max, _dy = far_corners(size, source, destination)
    return {"d0": source[0], "d2": destination[0], "d4": source_x_max, "d6": destination_x_max, "a6": frame}


def engine_block_pokes(size, source, destination, **kwargs):
    """A block with its far corners already stored, as the engine finds it after a front end."""
    source_x_max, source_y_max, destination_x_max, destination_y_max = far_corners(size, source, destination)
    return block_pokes(size=size, source=source, destination=destination, S_XMAX=source_x_max,
                       S_YMAX=source_y_max, D_XMAX=destination_x_max, D_YMAX=destination_y_max, **kwargs)


# ---- the $a00e / VDI call --------------------------------------------------------------------------------
SOURCE_MFDB = vdi.SOURCE_MFDB_AT
DESTINATION_MFDB = vdi.DESTINATION_MFDB_AT


def mfdb_pokes(at, form):
    """An MFDB for `form`, or a NULL base (the screen) for None."""
    if form is None:
        return vdi.mfdb_pokes(at, ADDR=0, WDWIDTH=vdi.FILL, NPLANES=vdi.FILL)
    return vdi.mfdb_pokes(at, ADDR=form.base, WDWIDTH=form.line_bytes // WORD_BYTES // form.planes,
                          NPLANES=form.planes)


def raster_call_pokes(opcode, corners, *, mode, source_form=None, destination_form=None, colours=(),
                      transparent=0, clip=None, workstation_pokes=None, extra=None):
    """A raster copy as the dispatcher leaves it: the two MFDBs at contrl[7..10] (None = the screen by
    a null base), ptsin = `corners` (sx1, sy1, sx2, sy2, dx1, dy1, dx2, dy2), intin = the mode and the
    colours, COPY_TRAN, and CLIP with its rectangle (the workstation's, dispatched) — over the canvas."""
    xmin, ymin, xmax, ymax = clip or (0, 0, SCREEN.width - 1, SCREEN.height - 1)
    work = workstation_pokes if workstation_pokes is not None else vdi.dispatched_pokes(
        onto=canvas(), CLIP=int(clip is not None), XMN_CLIP=xmin, YMN_CLIP=ymin, XMX_CLIP=xmax, YMX_CLIP=ymax)
    return merge_pokes(
        vdi.call_pokes(opcode, (mode, *colours), corners, workstation_pokes=work,
                       pointers=(SOURCE_MFDB, DESTINATION_MFDB)),
        mfdb_pokes(SOURCE_MFDB, source_form), mfdb_pokes(DESTINATION_MFDB, destination_form),
        vdi.linea_pokes(COPY_TRAN=transparent), extra)



# ---- the TRANSCRIPTION: `src/vdi/blit.S` -----------------------------------------------------------------
# Every case a battery here registers for Tier 3 is registered twice, as `vdi_raster.register` does: the
# C row, and the `.S` row through the transcription relation (the whole register file).
#
# THE CODE POINTERS, measured as `vdi_raster.py` measured its own: the engine returns with its op entry in
# A2 and its aligner's fragments in A3 / A4 on every path but the fast copy — the no-source rows restore
# A3 / A4 from the stack, to the aligner's pair — and with a pattern, the aligner's first fragment in A5.
# The front ends run the ROM's engine through vector 4 on BOTH sides, and $a00e restores everything, so
# they leave nothing to mask. Each caller that clears them is a `transcription.CallerPool`'s, staged in this
# module's own band.
ENGINE_CODE_POINTERS = ("a2", "a3", "a4")
PATTERN_CODE_POINTERS = ("a2", "a3", "a4", "a5")
BAND_OFFSET = 0x1C00
BAND_BYTES = 0x40
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_blit.py: the engine's code-pointer callers")
CALLER_BYTES = 0x14                     # room for the longest, which clears four
CALLERS = transcription.CallerPool(BAND_AT, BAND_AT + BAND_BYTES, CALLER_BYTES,
                                   built=(ENGINE_CODE_POINTERS, PATTERN_CODE_POINTERS))
code_pointer_caller = CALLERS.caller


def run_transcription(name, pokes, regs=None, *, code_pointers=()):
    """`blit.S`'s `name` against the ROM routine over `pokes` (the canvas under them)."""
    return CALLERS.run_transcription(name, canvas(pokes), regs, code_pointers=code_pointers)


def register(label, name, pokes, *, regs=None, code_pointers=()):
    """One case as the C row (`vdi.register`) and the `.S` row, over the canvas."""
    vdi.register(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), canvas(pokes), regs=regs)
    CALLERS.register_transcription(name, label, canvas(pokes), regs, code_pointers=code_pointers)
