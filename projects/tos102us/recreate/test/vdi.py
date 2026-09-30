"""THE VDI AND LINE-A STAGING DOOR — how every VDI/Line-A battery stages a call and reads it back.

HOW A FUNCTION IS ENTERED. The ROM's own path is `trap #2` -> `$fc9f9e` (copies the parameter block's
five pointers into the Line-A variables, PTSIN replaced by a copy at `VDI_PTSIN_COPY`) -> `$fca9f6`
(finds the workstation, makes it `LINEA_CUR_WORK`, and COPIES twenty of its fields into Line-A and VDI
RAM) -> the function. A case enters the FUNCTION DIRECTLY, with the machine as the dispatcher leaves
it — and that means the COPIES as well as the record: the rasterizers read `LINEA_WRT_MODE`, not
`WS_WRT_MODE`, so a case that staged only the record would test the snapshot's write mode on both
shores and pass. `dispatched_pokes()` stages the record AND every copy (`DISPATCH_COPIES`, pinned
against the ROM's own dispatcher by `test_vdi_staging.py`), and `call_pokes()` always goes through it.

A LINE-A PRIMITIVE is entered by `jsr` too — the VDI calls them that way ($fcb5d4 -> $a00e) — with a
REGISTER CONTRACT of its own, declared ONCE with `declare_primitive()`: which registers are its C
arguments and which carry its answer. `run_primitive()` and `bench/tier3.py` both read that
declaration, so the two cannot disagree. `run_through_exception()` is the same case entered through
the `$Axxx` exception itself, for the claims only that path makes.

WHAT THE SNAPSHOT MUST NOT BE TRUSTED FOR. Its `LINEA_CONTRL` points at the AES's arrays at `$c7e0`,
which overlap the capture MASK (`$c7e1` +7) — so every case stages its OWN arrays, in this module's
window. And USER_TIM/BUT/MOT/CUR point into the AES: `vdi/linea.h` says how a case that reaches one
is served.

---- STAGING RULES ---------------------------------------------------------------------------------
* EVERYTHING IS MERGED BYTE BY BYTE (`case.merge_pokes`): a helper's pokes laid over another's mean the
  later bytes where they overlap and the earlier ones everywhere else, whatever the dict keys were.
* FIELDS ARE STAGED BY NAME AT THE WIDTH THE HEADER DECLARES (`vdi/linea.h`, "THE WIDTH TAG"): a name
  that is not a field — a count, a mask, a ROM table — is refused, as is a value that does not fit.
* A POKE INTO THE WINDOW MUST LIE INSIDE ONE CLAIMED BAND, and PTSIN inside the copy it names: the
  Registry refuses overlapping CLAIMS, this refuses a poke that runs out of its own.

---- WHERE IT LIVES --------------------------------------------------------------------------------
The declared 4 KB case band is claimed to its last byte (`test/staging.py`), so the VDI takes a span
of the captured machine's free window the way the file system's RAM disk did: `WINDOW_AT`, above the
file system's user buffer and below the stack guard, held by `test_vdi_staging.py` to dead RAM in the
snapshot and clear of every other tenant. A battery that needs another buffer claims it with
`SPAN.claim(...)`.

---- WHAT THE HEADERS DO NOT NAME, AND WHY ----------------------------------------------------------
`include/vdi/*.h` carries only fields a ROM instruction was found reading or writing. Left out:
  * the published byte at $283f between CUR_MS_STAT and V_HID_CNT;
  * the individual words of `LINEA_GDP_SCRATCH` ($2614..$2641) and of `VDI_SCRATCH` ($16da..$1701) —
    each belongs to the routine that uses it, and is named (`LINEA_GDP_*`) once a reconstructed one does.
    The arc scratch does not start at LINEA_GDP_SCRATCH: two of its words lie below LINEA_CUR_FONT
    (LINEA_GDP_ANGLE $260c, LINEA_GDP_BEG_ANG $260e), named in `vdi/linea.h` and declared by `test/vdi_arcs.py`;
  * MFDB +4 (`fd_w`) and the reserved +14..+19: nothing in the ROM reads them;
  * FONT_HEADER +88, the 45th word TOS copies: 0 in all three ROM fonts and never read;
  * $fd3664..$fd36eb, between INQ_TAB's defaults and MAP_COL: v_pmarker's six shapes, reached only through
    the pointers at VDI_MARKER_SHAPES (`vdi/lines.h` says their layout).
"""
import ctypes
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, make_image

import abi
import case
import layouts
import routines
import staging
from case import merge_pokes
from opcodes import LINE_A, RTS

# ---- the headers' constants, out of the C the cores compile against ------------------------------
# One namespace for every VDI battery. Parsed IN INCLUDE ORDER with what came before as `known`,
# because `linea.h` spells fields as ALIASES of `addrs.h`'s console names rather than as second numbers.
_INCLUDE = Path(__file__).resolve().parents[1] / "include"
VDI_HEADERS = tuple(_INCLUDE / name for name in ("vdi/linea.h", "vdi/vdi.h", "vdi/font.h"))
CONSTANTS = layouts.parse_constants(VDI_HEADERS)
sys.modules[__name__].__dict__.update(CONSTANTS)

WORD_BYTES = layouts.WORD_BYTES
LONG_BYTES = layouts.LONG_BYTES
POINTER_VARIABLES = ("CONTRL", "INTIN", "PTSIN", "INTOUT", "PTSOUT")    # the order $fc9fb2.. stores
FILL = case.SLACK_FILL
FILL_LONG = FILL * 0x01010101          # ...a longword of it, which a skipped long store leaves
# A word a case stages where the routine should store and the ROM does (or should not, and does not): any
# value the answer cannot be, $5a5a, so a store one side makes and the other does not is a changed word.
STALE_WORD = 0x5A5A
# ...and a long of it, for a pointer or a long field staged the same way.
STALE_LONG = STALE_WORD << 16 | STALE_WORD

# ---- the FIELDS: every tagged `#define`, by record (`test/layouts.py`, the one reader of the width tags) --------
# A record is a constant-name prefix: LINEA (absolute addresses), WS, FONT, BITBLT, MFDB, PB, CONTRL (offsets).
RECORDS = ("LINEA", "WS", "FONT", "BITBLT", "MFDB", "PB", "CONTRL")
# A staged field is held to the window's placement rule (`require_claimed`, below), looked up when it is staged.
LAYOUTS = layouts.Layouts(VDI_HEADERS, RECORDS, CONSTANTS, require=lambda at, size: require_claimed(at, size))
FIELDS = LAYOUTS.fields
RECORD_BYTES = {"WS": WS_BYTES, "FONT": FONT_HEADER_BYTES, "BITBLT": BITBLT_BYTES, "PB": PB_BYTES}


def field(record, name):
    """`record`'s field `name` (`"INTIN"` or `"LINEA_INTIN"` alike) — a KeyError naming it when the
    header has no FIELD of that name, which includes every count, mask and ROM table it defines."""
    return LAYOUTS.field(record, name)


def field_pokes(record, base=0, **values):
    """Fields of `record` at `base`, by name — `field_pokes("WS", at, WRT_MODE=2)`. LINEA's fields are
    absolute, so its base is 0."""
    return LAYOUTS.pokes(record, base, **values)


def read_field(image, record, name, base=0):
    """A field back out of `image`: an int, or a list of elements for an array."""
    return LAYOUTS.read(image, record, name, base)


# ---- the window, and the bands in it -------------------------------------------------------------
WINDOW_AT = 0x76000
WINDOW_BYTES = 0x2000
SPAN = staging.Registry(WINDOW_AT, WINDOW_AT + WINDOW_BYTES, "the VDI's staged window")

ARRAY_BYTES = 0x100                     # 128 words: every intin/intout a function here answers
PTSIN_BYTES = 0x200                     # the CALLER's ptsin, which only a trap-entry case reads
CONTRL_BYTES = CONTRL_POINTER_B + LONG_BYTES    # seven words and the two longwords after them
RECORDS_BYTES = 0x100                   # two MFDBs and a BITBLT block
FONT_BAND_BYTES = 0x400                 # a staged font header and its form
STUB_BYTES = 0x10                       # a Line-A exception stub
PARAMETER_BLOCK_AT = SPAN.claim(WINDOW_AT, PB_BYTES, "the VDI parameter block D1 points at")
CONTRL_AT = SPAN.claim(PARAMETER_BLOCK_AT + PB_BYTES, CONTRL_BYTES, "contrl[]")
INTIN_AT = SPAN.claim(CONTRL_AT + CONTRL_BYTES, ARRAY_BYTES, "intin[]")
INTOUT_AT = SPAN.claim(INTIN_AT + ARRAY_BYTES, ARRAY_BYTES, "intout[]")
PTSOUT_AT = SPAN.claim(INTOUT_AT + ARRAY_BYTES, ARRAY_BYTES, "ptsout[]")
PTSIN_AT = SPAN.claim(PTSOUT_AT + ARRAY_BYTES, PTSIN_BYTES, "the caller's ptsin[]")
VIRTUAL_WORK_AT = SPAN.claim(PTSIN_AT + PTSIN_BYTES, WS_BYTES, "a virtual workstation")
RECORDS_AT = SPAN.claim(VIRTUAL_WORK_AT + WS_BYTES, RECORDS_BYTES, "staged MFDBs and a BITBLT block")
FONT_AT = SPAN.claim(RECORDS_AT + RECORDS_BYTES, FONT_BAND_BYTES, "a staged font header and form")
STUB_AT = SPAN.claim(FONT_AT + FONT_BAND_BYTES, STUB_BYTES, "a Line-A exception stub")
TRANSCRIPTION_CALLER_BYTES = 0x8        # `move.l 4(sp),-(sp) / rts`
TRANSCRIPTION_CALLER_AT = SPAN.claim(STUB_AT + STUB_BYTES, TRANSCRIPTION_CALLER_BYTES,
                                     "the staged caller a transcription is entered through")
SOURCE_MFDB_AT = RECORDS_AT
DESTINATION_MFDB_AT = RECORDS_AT + 0x20
BITBLT_AT = RECORDS_AT + 0x40


def require_claimed(at, size):
    """A poke into the window must lie inside ONE claimed band (`staging.Registry.require_claimed`)."""
    SPAN.require_claimed(at, size)


# ---- (a) the Line-A variables and the records, by name -------------------------------------------

def linea_pokes(**values):
    """Line-A variables by name, at their declared width — `linea_pokes(WRT_MODE=2, PATPTR=0x7000)`."""
    return field_pokes("LINEA", 0, **values)


def linea(image, name):
    """A Line-A variable back out of `image`."""
    return read_field(image, "LINEA", name)


def mfdb_pokes(at, **values):
    """An MFDB at `at` (`SOURCE_MFDB_AT` / `DESTINATION_MFDB_AT`), by field."""
    return field_pokes("MFDB", at, **values)


def bitblt_pokes(at=None, **values):
    """A $a007 BITBLT block at `at` (default `BITBLT_AT`), by field."""
    return field_pokes("BITBLT", BITBLT_AT if at is None else at, **values)


def font_pokes(at=None, form=b"", offsets=(), **values):
    """A font header at `at` (default `FONT_AT`), its offset table and form laid after it, and
    FONT_OFF_TABLE / FONT_DAT_TABLE pointed at them unless the case names its own."""
    at = FONT_AT if at is None else at
    offsets_at = at + FONT_HEADER_BYTES
    form_at = offsets_at + len(offsets) * WORD_BYTES
    tables = {"OFF_TABLE": offsets_at, "DAT_TABLE": form_at}
    extra = {}
    if offsets:
        require_claimed(offsets_at, len(offsets) * WORD_BYTES)
        extra[offsets_at] = pack_words(*offsets)
    if form:
        require_claimed(form_at, len(form))
        extra[form_at] = bytes(form)
    return merge_pokes(field_pokes("FONT", at, **{**tables, **values}), extra)


def fill_pattern_pokes(at, rows):
    """A fill pattern — `rows` as words, one per scan line (and plane) — at `at`, for LINEA_PATPTR."""
    data = pack_words(*rows)
    require_claimed(at, len(data))
    return {at: data}


# ---- (b) the workstation, as the dispatcher leaves it ----------------------------------------------
# `$fca9f6`'s stores after the lookup ($fcaa40..$fcab14), IN THE ROM's ORDER — ONE list, which every mirror folds:
# `dispatcher_copies` (what every battery stages), `test/vdi_entry.py`'s order model and its stale stores. Each step
# is where the store goes, how wide, and how its value is had: `copied` the WS field it copies, or `compute(memory,
# at)` for the three the ROM computes, answering (value, the record offset it was copied from or None). A step reads
# memory AS THE STORES BEFORE IT LEFT IT, which is the ROM's (and `src/vdi/entry.c` `make_current`'s) sequence:
# `test_vdi_entry.py` holds this ORDER to the ROM's own stores, and every byte the ROM stores to a step.
DispatchStep = namedtuple("DispatchStep", "destination width copied compute", defaults=(None, None))


def memory_value(memory, at, width):
    """`width` bytes at `at` of `memory` — an image, or a dict of the bytes that matter — as an unsigned int."""
    return int.from_bytes(bytes(memory[at + index] for index in range(width)), "big")


def _record_address(_memory, at):
    """CUR_WORK: the record's own address."""
    return at, None


def _multifill_of(memory, at):
    """MULTIFILL ($fcaa8e): the record's, for the user interior alone — a COPY then — else 0."""
    if memory_value(memory, at + field("WS", "FILL_STYLE").at, WORD_BYTES) != VDI_INTERIOR_USER:
        return 0, None
    offset = field("WS", "MULTIFILL").at
    return memory_value(memory, at + offset, WORD_BYTES), offset


def _mono_of(memory, _at):
    """MONO_STATUS ($fcaade): the monospace bit of the font LINEA_CUR_FONT names — read back, after its copy."""
    font = memory_value(memory, LINEA_CUR_FONT, LONG_BYTES)
    return memory_value(memory, font + field("FONT", "FLAGS").at, WORD_BYTES) & FONT_FLAG_MONOSPACE_MASK, None


def _copy(destination, name):
    return DispatchStep(destination, field("WS", name).width, copied=name)


def _computed(name, compute):
    return DispatchStep(field("LINEA", name).at, field("LINEA", name).width, compute=compute)


DISPATCH_STEPS = (
    _computed("CUR_WORK", _record_address),
    _copy(LINEA_CLIP, "CLIP"),
    _copy(LINEA_INQ_TAB + VDI_INQ_TAB_CLIP_INDEX * WORD_BYTES, "CLIP"),
    _copy(LINEA_XMINCL, "XMN_CLIP"),
    _copy(LINEA_YMINCL, "YMN_CLIP"),
    _copy(LINEA_XMAXCL, "XMX_CLIP"),
    _copy(LINEA_YMAXCL, "YMX_CLIP"),
    _copy(LINEA_WRT_MODE, "WRT_MODE"),
    _copy(LINEA_PATPTR, "PATPTR"),
    _copy(LINEA_PATMSK, "PATMSK"),
    _computed("MULTIFILL", _multifill_of),
    _copy(LINEA_FONT_RING + LINEA_FONT_RING_LOADED * LONG_BYTES, "LOADED_FONTS"),
    _copy(LINEA_DEV_TAB + VDI_DEV_TAB_FACES_INDEX * WORD_BYTES, "NUM_FONTS"),
    _copy(LINEA_DDA_INC, "DDA_INC"),
    _copy(LINEA_T_SCLSTS, "T_SCLSTS"),
    _copy(LINEA_SCALE, "SCALED"),
    _copy(LINEA_CUR_FONT, "CUR_FONT"),
    _computed("MONO_STATUS", _mono_of),
    _copy(LINEA_SCRPT2, "SCRPT2"),
    _copy(LINEA_SCRTCHP, "SCRTCHP"),
    _copy(LINEA_STYLE, "STYLE"),
    _copy(VDI_TEXT_H_ALIGN, "H_ALIGN"),
    _copy(VDI_TEXT_V_ALIGN, "V_ALIGN"),
    _copy(LINEA_CHUP, "CHUP"),
)
# ...its plain copies alone, as (where the copy goes, the workstation field): a view of the list, not a second one.
DISPATCH_COPIES = tuple((step.destination, step.copied) for step in DISPATCH_STEPS if step.copied)


def dispatch_stores(memory, at, steps=DISPATCH_STEPS):
    """`steps` run over `memory` (mutable: a bytearray or a dict of the bytes that matter) for the record at `at`,
    each value STORED before the next step reads: yields (step, value, the record offset it was copied from or None).
    A read off a dict's bytes is its KeyError."""
    for step in steps:
        if step.copied:
            offset = field("WS", step.copied).at
            value = memory_value(memory, at + offset, step.width)
        else:
            value, offset = step.compute(memory, at)
        for index, byte in enumerate(value.to_bytes(step.width, "big")):
            memory[step.destination + index] = byte
        yield step, value, offset


def dispatcher_copies(image, at):
    """What `$fca9f6` stores before `jsr`ing a function, for the workstation at `at` in `image`: every step of
    DISPATCH_STEPS, folded in order, and the VDI_RESULT it cleared before the lookup."""
    pokes = {step.destination: value.to_bytes(step.width, "big")
             for step, value, _offset in dispatch_stores(bytearray(image), at)}
    return merge_pokes(pokes, {VDI_RESULT: bytes(WORD_BYTES)})


def dispatched_pokes(at=VDI_PHYS_WORK, *, onto=None, **values):
    """The workstation at `at` — the physical one by default — with `values` staged into its record
    BY FIELD, and every copy the dispatcher makes of it: the machine a function is `jsr`ed into.

    The copies are computed over `onto` too, so stage there anything they READ — a font the record's
    CUR_FONT names decides MONO_STATUS — rather than merging it in afterwards."""
    staged = merge_pokes(onto, field_pokes("WS", at, **values))
    return merge_pokes(staged, dispatcher_copies(make_image(staged), at))


def virtual_workstation(handle, *, onto=None, **values):
    """A VIRTUAL workstation at `VIRTUAL_WORK_AT`, dispatched (over `onto`, as `dispatched_pokes`): the
    physical record's bytes as the snapshot has them, its own handle, NEXT 0, and `values`. It is not
    linked into the list — a direct-entry function never walks it; a dispatcher case links it through
    WS_NEXT itself."""
    record = {VIRTUAL_WORK_AT: bytes(BASE_IMAGE[VDI_PHYS_WORK:VDI_PHYS_WORK + WS_BYTES])}
    return dispatched_pokes(VIRTUAL_WORK_AT, onto=merge_pokes(onto, record), HANDLE=handle, NEXT=0, **values)


def workstation(image, name, at=VDI_PHYS_WORK):
    """A workstation field back out of `image`."""
    return read_field(image, "WS", name, at)


# ---- (c) a call: the arrays, the five pointers and the dispatched workstation ---------------------

def pack_words(*values):
    """Big-endian words, each masked to 16 bits — a negative coordinate is its two's complement."""
    return struct.pack(f">{len(values)}H", *(value & 0xFFFF for value in values))


def contrl(opcode, n_ptsin=0, n_intin=0, *, subfunction=0, handle=VDI_PHYS_HANDLE, pointers=None):
    """contrl[] as the dispatcher leaves it: contrl[2] and contrl[4] CLEARED ($fcaa0a, $fcaa0e).
    `pointers` is the `(a, b)` longword pair at contrl[7..10] (two MFDBs, a vex_* exchange)."""
    staged = pack_words(opcode, n_ptsin, 0, n_intin, 0, subfunction, handle)
    if pointers is not None:
        staged += struct.pack(">II", *pointers)
    return staged


def _ptsin_room(ptsin_at):
    """How many bytes the PTSIN array at `ptsin_at` may hold: the entry's copy, or the band it is in."""
    if ptsin_at == VDI_PTSIN_COPY:
        return VDI_PTSIN_COPY_BYTES
    for claim_at, claim_size, _owner in SPAN.claims:
        if claim_at <= ptsin_at < claim_at + claim_size:
            return claim_at + claim_size - ptsin_at
    raise AssertionError(f"ptsin at {ptsin_at:#x} is neither VDI_PTSIN_COPY nor inside a band of {SPAN.label}")


def call_pokes(opcode, intin=(), ptsin=(), *, workstation_pokes=None, ptsin_at=VDI_PTSIN_COPY,
               subfunction=0, pointers=None):
    """One call staged as the dispatcher leaves it, for a direct-entry case.

    `workstation_pokes` is `dispatched_pokes(...)` or `virtual_workstation(...)` — the physical
    workstation, dispatched, by default — and contrl[6] is ITS handle. The five Line-A pointers name
    this module's arrays (PTSIN names `ptsin_at`, the entry's own copy by default, which is where a
    trapped call's points are), and intout/ptsout are FILLed so an answer the reconstruction skipped
    reads as a byte no function writes. `ptsin` is the flat word list `(x0, y0, x1, y1, ...)`.
    """
    assert len(ptsin) % 2 == 0, "ptsin is (x, y) pairs"
    assert len(intin) * WORD_BYTES <= ARRAY_BYTES, "more intin words than its band holds"
    assert len(ptsin) * WORD_BYTES <= _ptsin_room(ptsin_at), "more ptsin words than the array holds"
    staged_work = workstation_pokes if workstation_pokes is not None else dispatched_pokes()
    work_image = make_image(staged_work)
    handle = read_field(work_image, "WS", "HANDLE", linea(work_image, "CUR_WORK"))
    arrays = {CONTRL_AT: contrl(opcode, len(ptsin) // 2, len(intin), subfunction=subfunction,
                                handle=handle, pointers=pointers),
              INTOUT_AT: bytes([FILL]) * ARRAY_BYTES,
              PTSOUT_AT: bytes([FILL]) * ARRAY_BYTES}
    if intin:
        arrays[INTIN_AT] = pack_words(*intin)
    if ptsin:
        arrays[ptsin_at] = pack_words(*ptsin)
    return merge_pokes(staged_work, pointer_pokes(ptsin=ptsin_at), arrays)


def function_pokes(name, intin=(), ptsin=(), **kwargs):
    """`call_pokes` for the VDI FUNCTION `addrs.<name>` (a `VDI_ROM_<FN>`), by its `_OPCODE`."""
    return call_pokes(getattr(addrs, name + "_OPCODE"), intin, ptsin, **kwargs)


# THE OVERLAP A STORE ORDER SHOWS ON: intout laid over contrl[4], so the word left there says whether the
# count or the first answer was stored last. Every VDI function that answers is held to it.
COUNT_OVERLAP = CONTRL_AT + CONTRL_N_INTOUT


def intout_over(pokes, at=COUNT_OVERLAP):
    """`pokes` with LINEA_INTOUT pointed at `at` — over contrl[4] by default."""
    return merge_pokes(pokes, linea_pokes(INTOUT=at))


def pointer_pokes(*, ptsin=VDI_PTSIN_COPY):
    """The five Line-A array pointers, at this module's arrays."""
    return linea_pokes(**dict(zip(POINTER_VARIABLES, (CONTRL_AT, INTIN_AT, ptsin, INTOUT_AT, PTSOUT_AT))))


def parameter_block_pokes():
    """...and the PARAMETER BLOCK a trap-entry case hands `$fc9f9e` in D1 (`PARAMETER_BLOCK_AT`):
    the same arrays, with the CALLER's ptsin at `PTSIN_AT`, which the entry copies from."""
    return field_pokes("PB", PARAMETER_BLOCK_AT, CONTRL=CONTRL_AT, INTIN=INTIN_AT, PTSIN=PTSIN_AT,
                       INTOUT=INTOUT_AT, PTSOUT=PTSOUT_AT)


# ---- (d) reading a run back: `case.Result`, with the VDI's readers ---------------------------------

def rom_word(at):
    """A word of the ROM (or of the snapshot's RAM) as the capture holds it."""
    return case.word_in(BASE_IMAGE, at)


def signed_word(word):
    """A 16-bit word as the signed Alcyon `int` it is."""
    return word - 0x10000 if word & 0x8000 else word


def rom_table_entry(table, index):
    """The address a ROM table of WORD displacements from itself names at `index` — the escape's, and ESC's two."""
    return table + signed_word(rom_word(table + index * WORD_BYTES))



class Result(case.Result):
    """A run and the machine after it (`case.Result`), read as the VDI's arrays and records."""

    def intout(self, count):
        return self.words(INTOUT_AT, count)

    def ptsout(self, count):
        """`count` WORDS (two per point)."""
        return self.words(PTSOUT_AT, count)

    def contrl(self, offset):
        """A word of contrl — `CONTRL_N_INTOUT` and `CONTRL_N_PTSOUT` are the answers."""
        return self.word(CONTRL_AT + offset)

    def linea(self, name):
        return linea(self.final, name)

    def workstation(self, name, at=VDI_PHYS_WORK):
        return workstation(self.final, name, at)

    def pixel(self, x, y):
        return read_pixel(self.final, x, y)


# ---- (e) the screen --------------------------------------------------------------------------------
# Read out of the captured machine rather than spelt: the base `v_bas_ad` holds and the geometry the
# console re-init stored from its resolution table ($fca9b8). One 16-pixel group is `planes`
# consecutive words, plane 0 first — `$fca1b8` (concat) is the ROM's own address arithmetic.
PIXELS_PER_GROUP = 16
LEFTMOST_PIXEL_BIT = 0x8000
Screen = namedtuple("Screen", "base planes bytes_per_line width height bytes")


def screen(image=BASE_IMAGE):
    """The framebuffer `image` describes: in the snapshot, $f8000, 4 planes, 320 x 200, 32,000 B."""
    bytes_per_line = linea(image, "BYTES_LIN")
    height = linea(image, "V_REZ_VT")
    return Screen(case.long_in(image, addrs.SYSVAR_V_BAS_AD), linea(image, "PLANES"),
                  bytes_per_line, linea(image, "V_REZ_HZ"), height, bytes_per_line * height)


SCREEN = screen()


def pixel_word(x, y, plane, geometry=SCREEN):
    """The address of the word holding plane `plane` of pixel (x, y), and the pixel's bit in it."""
    group = x // PIXELS_PER_GROUP
    at = geometry.base + y * geometry.bytes_per_line + (group * geometry.planes + plane) * WORD_BYTES
    return at, LEFTMOST_PIXEL_BIT >> (x % PIXELS_PER_GROUP)


def read_pixel(image, x, y, geometry=SCREEN):
    """The colour index at (x, y): plane p's bit is bit p of the index."""
    colour = 0
    for plane in range(geometry.planes):
        at, bit = pixel_word(x, y, plane, geometry)
        colour |= bool(case.word_in(image, at) & bit) << plane
    return colour


def clear_screen_pokes(geometry=SCREEN):
    """The whole screen at colour 0 — a known canvas for a drawing case."""
    return {geometry.base: bytes(geometry.bytes)}


def pixel_pokes(pixels, *, onto=None, geometry=SCREEN):
    """`{(x, y): colour}` drawn ONTO the screen `onto` stages (the snapshot's when None), merged over it:
    the other pixels of every word a staged pixel shares keep the colours `onto` gave them."""
    image = make_image(onto or {})
    words = {}
    for (x, y), colour in pixels.items():
        for plane in range(geometry.planes):
            at, bit = pixel_word(x, y, plane, geometry)
            word = int.from_bytes(words.get(at, bytes(image[at:at + WORD_BYTES])), "big")
            word = word | bit if colour >> plane & 1 else word & ~bit
            words[at] = word.to_bytes(WORD_BYTES, "big")
    return merge_pokes(onto, words)


def screen_pixels(image, geometry=SCREEN):
    """The whole screen as rows of colour indexes."""
    return [[read_pixel(image, x, y, geometry) for x in range(geometry.width)]
            for y in range(geometry.height)]


def screen_diff(expected, actual, *, limit=8, geometry=SCREEN):
    """A failure message's worth of two screens' difference: how many pixels differ, the bounding box,
    and the first `limit` as (x, y): expected -> actual — not 32,000 bytes of hex."""
    base, end = geometry.base, geometry.base + geometry.bytes
    if bytes(expected[base:end]) == bytes(actual[base:end]):
        return "the screens are identical"
    differing = [(x, y) for y in range(geometry.height) for x in range(geometry.width)
                 if read_pixel(expected, x, y, geometry) != read_pixel(actual, x, y, geometry)]
    xs, ys = [x for x, _ in differing], [y for _, y in differing]
    shown = ", ".join(f"({x},{y}): {read_pixel(expected, x, y, geometry)}->{read_pixel(actual, x, y, geometry)}"
                      for x, y in differing[:limit])
    return (f"{len(differing)} pixel(s) differ in x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}; "
            f"first: {shown}")


# ---- (f) the run doors -------------------------------------------------------------------------------

def _core(symbol, restype):
    core = getattr(_lib, symbol)
    core.restype = restype
    return core


def recorded(glue, recording):
    """`glue` run inside `recording`'s pass (an `AddressHook.recording`, or `gemdos.recording`) when a case names
    one — a core that calls out through a hook the case staged — and as it is otherwise."""
    return recording(glue) if recording else glue


def run_function(name, pokes, *, recording=None, **kwargs):
    """The VDI FUNCTION `addrs.<name>` (a `VDI_ROM_<FN>`), entered as the dispatcher's `jsr` leaves the
    machine — so `pokes` should come from `call_pokes`, which stages the dispatched workstation —
    against the core `void vdi_<fn>(uint8_t *image)`. Answers a `Result`; `kwargs` are `case.run`'s.
    `recording` is `_run_primitive_at`'s, for a function that calls out through a hook the case staged."""
    core = _core(routines.core_symbol(name), None)

    def glue(_lib_, buf):
        return core(buf)

    info = case.run(getattr(addrs, name), {"_pokes": pokes}, recorded(glue, recording),
                    width=case.NO_RESULT, **kwargs)
    return Result(info, pokes)


# THE ATTRIBUTION PASS OFF (`case.run`'s poison), for a routine that READS A POINTER IT ALSO WRITES. The pass
# inverts every byte the ROM wrote and re-runs both shores over that image, so a pointer the routine reads and
# then stores back (even unchanged) is inverted BEFORE its first read: the poisoned run follows it to $ffxxxx and
# reads the I/O page, which no model serves. One knob for every layer; each battery that uses it names the
# pointer, and the staging (stale fields, a pseudo-random canvas) that stands in for the pass.
READS_A_POINTER_IT_WRITES = {"poison": False}


# A PRIMITIVE's register contract, declared once: the registers that are its C arguments, in order,
# and the registers its answer is in. `bench/tier3.py` builds the Tier 3 call from the same entry.
Primitive = namedtuple("Primitive", "arguments results")
PRIMITIVES = {}
# Room for every register a primitive may answer in: D0-D2/A0-A2, the six the Line-A exception does
# not restore ($fc9f28 saves D3-D7/A3-A5 only).
RESULTS_MAX = 6
RESULTS_ARRAY = ctypes.c_uint32 * RESULTS_MAX


def declare_primitive(name, *, arguments=(), results=()):
    """Declare `addrs.<name>`'s contract. The C core is `<routines.core_symbol(name)>(image, *arguments)`,
    RETURNING D0 when "d0" is among `results` (`void` otherwise) and, when `results` names more than one
    register, taking a last `uint32_t *results` parameter it fills in `results` order. Tier 1 compares
    every declared register; Tier 3's second column compares D0 (`bench/tier3.py`)."""
    PRIMITIVES[name] = Primitive(tuple(arguments), tuple(results))
    return PRIMITIVES[name]


def _run_primitive_at(entry, name, registers, pokes, *, recording=None, **kwargs):
    """`recording` is an `AddressHook.recording` for a primitive that calls out through a hook the case
    staged (`test/vdi_mouse.py`'s user vectors): it opens the hook's pass round each candidate run."""
    contract = PRIMITIVES[name]
    values = [registers[register] for register in contract.arguments]
    several = len(contract.results) > 1
    answers_d0 = "d0" in contract.results
    assert several or answers_d0 or not contract.results, "a lone answer in a register but D0 is not modelled"
    core = _core(routines.core_symbol(name), ctypes.c_uint32 if answers_d0 else None)
    answers = []

    def glue(_lib_, buf):
        if not several:
            return core(buf, *values)
        out = RESULTS_ARRAY()
        returned = core(buf, *values, out)
        answers.append(list(out)[:len(contract.results)])
        return returned

    info = case.run(entry, {**registers, "_pokes": pokes}, recorded(glue, recording),
                    width=case.FULL_D0 if answers_d0 else case.NO_RESULT, **kwargs)
    if several:
        # The FIRST candidate call is the differential's own; the attribution pass re-runs it over a
        # poisoned image, where an answer read out of memory may rightly differ.
        expected = [info["regs"][register] for register in contract.results]
        assert answers[0] == expected, (
            f"{name} answered {dict(zip(contract.results, map(hex, answers[0])))} where the ROM left "
            f"{dict(zip(contract.results, map(hex, expected)))}")
    return Result(info, pokes)


def run_primitive(name, registers, pokes, **kwargs):
    """The LINE-A PRIMITIVE `addrs.<name>`, entered by `jsr` with `registers` — its contract, declared
    by `declare_primitive` — its C arguments taken from those registers BY NAME and its answer compared
    register by register on both shores."""
    return _run_primitive_at(getattr(addrs, name), name, registers, pokes, **kwargs)


def exception_stub_pokes(opcode):
    """`dc.w $A00n / rts` at `STUB_AT`: a caller that reaches a primitive THROUGH the Line-A exception."""
    return {STUB_AT: pack_words(LINE_A | opcode) + RTS}


def run_through_exception(name, opcode, registers, pokes, **kwargs):
    """`run_primitive` entered through `$fc9f0c` by a staged `$A00n`, which is what a program does.

    WHAT THE PATH HIDES: the handler saves and restores D3-D7/A3-A5 around the primitive and returns
    by `rte` past the opcode word, so a clobber of those registers is invisible here and visible only to
    a direct `jsr` case. A row entered this way is not priced — its entry is the stub, not the routine
    (`register(..., priced=False)`)."""
    return _run_primitive_at(STUB_AT, name, registers, merge_pokes(pokes, exception_stub_pokes(opcode)),
                             **kwargs)


# ---- (g) the registry, and what the snapshot mask is checked against ------------------------------
# `test_boot_snapshot.VERIFIED_CASES` splats `CASES`; `UNPRICED` is verified and swept like the rest but
# has no Tier 3 row (a case entered at the Line-A exception stub rather than the routine). ONE shape for every
# component's rows (`case.Rows`), which also gathers the priced rows' Tier 3 drops and their companions
# (`case.ROW_REGISTRIES`), bound here under the VDI's own names.
ROWS = case.Rows("the VDI")
CASES = ROWS.cases
UNPRICED = ROWS.unpriced
register = ROWS.register


# ---- (h) the ALCYON calls: the C signature a frame's words and longwords are decoded into ---------------
# An Alcyon C routine is entered by `jsr` over the frame its caller pushed — WORD arguments (an Alcyon `int`
# is 16 bits), LONG addresses — and answers a word in D0.w, which is all its callers read. `declare_alcyon`
# is the ONE statement of each such core's C signature: the batteries stage the frame from it, the host
# core's ctypes signature is set from it, `bench/tier3.py` decodes its Tier 3 call out of the same frame by
# it, and `bench/shipped_glue.py` repacks a GCC call into that frame by it.
IMAGE_ARG = ctypes.POINTER(ctypes.c_uint8)
WORD_ARG = ctypes.c_int16
UWORD_ARG = ctypes.c_uint16     # ...where the C core takes the word as `uint16_t`
LONG_ARG = ctypes.c_uint32
ARG_BYTES = {WORD_ARG: WORD_BYTES, UWORD_ARG: WORD_BYTES, LONG_ARG: LONG_BYTES}
WORD_RESULT = 16                # the bits of D0 an Alcyon `int` answer is compared at
Alcyon = namedtuple("Alcyon", "restype argtypes host_arguments", defaults=(0,))
ALCYON = {}


def declare_alcyon(name, restype, argtypes, *, host_arguments=0):
    """`addrs.<name>`'s core is an Alcyon call `restype core(argtypes)` — the image first where it takes
    one, then the frame's arguments in push order; `restype` None for no answer. `host_arguments` counts
    the C arguments after the image that NO frame carries: what the machine holds elsewhere and the host
    build is handed instead (gemdos_call's return site, the address its caller's `jsr` pushed). The shipped
    glue drops them, and no frame could decode them for a Tier 3 call."""
    ALCYON[name] = Alcyon(restype, tuple(argtypes), host_arguments)
    core = getattr(_lib, routines.core_symbol(name))
    core.restype, core.argtypes = restype, list(argtypes)
    return ALCYON[name]


def takes_image(name):
    """Whether the Alcyon routine's core takes the image first — every one but a core over words alone (mul_div)."""
    return ALCYON[name].argtypes[:1] == (IMAGE_ARG,)


def frame_argtypes(name):
    """The argument types an Alcyon routine's FRAME carries: its signature less the image and the host's own."""
    signature = ALCYON[name]
    framed = signature.argtypes[1:] if takes_image(name) else signature.argtypes
    return framed[signature.host_arguments:]


# THE FRAME of an Alcyon call — its arguments pushed as the signature's words and longwords, where `jsr` leaves them
# (`abi.FIRST_ARG`) — and its WORD arguments as the signed words they are: a value a case writes $8000-up is
# negative to the frame and the core alike. The one builder the VDI's Alcyon batteries and the AES's door share.
FRAME_FORMATS = {WORD_ARG: "h", LONG_ARG: "I"}


def as_signed(name, arguments):
    """`arguments` with every WORD one as the signed word it is."""
    return tuple(signed_word(value & 0xFFFF) if argtype is WORD_ARG else value
                 for argtype, value in zip(frame_argtypes(name), arguments))


def alcyon_frame(name, *arguments):
    """The Alcyon frame of `name`'s arguments, where `jsr` leaves it (`abi.FIRST_ARG`)."""
    formats = "".join(FRAME_FORMATS[argtype] for argtype in frame_argtypes(name))
    return {abi.FIRST_ARG: struct.pack(">" + formats, *as_signed(name, arguments))}


# Every span a VDI case reads or pokes, in `test_boot_snapshot.CASE_FIELDS`' shape. The Line-A block
# is declared WHOLE, because a case overrides any field of it by name.
LINEA_BLOCK_START = LINEA_CUR_FONT
LINEA_BLOCK_END = LINEA_BLIT_MODE + WORD_BYTES
_CASE_FIELDS = [
    (LINEA_BLOCK_START, LINEA_BLOCK_END - LINEA_BLOCK_START, "the Line-A variables a case stages by name"),
    (VDI_PHYS_WORK, WS_BYTES, "the physical workstation"),
    (VDI_PTSIN_COPY, VDI_PTSIN_COPY_BYTES, "the entry's copy of ptsin"),
    (VDI_SCRATCH, VDI_PTSIN_COPY - VDI_SCRATCH, "the VDI's scratch in the disk buffer, and the text copies"),
    (FONT_RAM_8X8, FONT_HEADER_BYTES, "the RAM 8x8 font header"),
    (FONT_RAM_8X16, FONT_HEADER_BYTES, "the RAM 8x16 font header"),
    (SCREEN.base, SCREEN.bytes, "the screen a drawing case stages and reads pixels of"),
]


def declare_case_field(at, size, why):
    """A span a battery's cases reach OUTSIDE the window and the fields above — the one door for it."""
    _CASE_FIELDS.append((at, size, why))


def case_fields():
    """Every span a VDI case reads or pokes: the fields above, every battery's `declare_case_field`, and
    every band of the window AS CLAIMED WHEN ASKED — a battery claims its band after this module loads."""
    return (*_CASE_FIELDS, *SPAN.claims)
