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
    each belongs to the routine that uses it, and is named (`LINEA_GDP_*`) once a reconstructed one does;
  * MFDB +4 (`fd_w`) and the reserved +14..+19: nothing in the ROM reads them;
  * FONT_HEADER +88, the 45th word TOS copies: 0 in all three ROM fonts and never read;
  * $fd3664..$fd36eb, between INQ_TAB's defaults and MAP_COL: no access found.
"""
import ctypes
import importlib
import re
import struct
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import abi
import case
import staging
from case import merge_pokes
from isr import blob as bench     # the cross-compiled blob, loaded once per process (`isr.blob`)
from opcodes import CLEAR_ADDRESS_REGISTER, LINE_A, PUSH_RETURN_PC, PUSH_STACK_LONG, RTS

# ---- the headers' constants, out of the C the cores compile against ------------------------------
# One namespace for every VDI battery. Parsed IN INCLUDE ORDER with what came before as `known`,
# because `linea.h` spells fields as ALIASES of `addrs.h`'s console names rather than as second numbers.
_INCLUDE = Path(__file__).resolve().parents[1] / "include"
VDI_HEADERS = tuple(_INCLUDE / name for name in ("vdi/linea.h", "vdi/vdi.h", "vdi/font.h"))
CONSTANTS = {}
for _header in VDI_HEADERS:
    CONSTANTS.update(addrs.parse(_header, known={**addrs.ADDRS, **CONSTANTS}))
sys.modules[__name__].__dict__.update(CONSTANTS)

WORD_BYTES = 2
LONG_BYTES = 4
POINTER_VARIABLES = ("CONTRL", "INTIN", "PTSIN", "INTOUT", "PTSOUT")    # the order $fc9fb2.. stores
FILL = case.SLACK_FILL

# ---- the FIELDS: every tagged `#define`, by record -------------------------------------------------
# A record is a constant-name prefix: LINEA (absolute addresses), WS, FONT, BITBLT, MFDB, PB, CONTRL (offsets).
Field = namedtuple("Field", "at width count")       # count None: a scalar; otherwise an array of `width`s
_WIDTHS = {"byte": 1, "word": WORD_BYTES, "long": LONG_BYTES}
_TAGGED = re.compile(r"^\s*#define\s+(?P<name>[A-Z][A-Z0-9_]*)\s+\S+\s*/\*\s*(?P<kind>byte|word|long)"
                     r"(?P<plural>s\[(?P<count>\w+)\])?(?=[\s:*])")
RECORDS = ("LINEA", "WS", "FONT", "BITBLT", "MFDB", "PB", "CONTRL")


def _fields():
    """`{record: {short name: Field}}` out of the headers' width tags."""
    fields = {record: {} for record in RECORDS}
    for header in VDI_HEADERS:
        for line in header.read_text().splitlines():
            match = _TAGGED.match(line)
            if not match:
                continue
            record, _, short = match["name"].partition("_")
            if record not in fields:
                continue
            count = match["count"]
            if count is not None:
                count = int(count, 0) if count[0].isdigit() else CONSTANTS[count]
            fields[record][short] = Field(CONSTANTS[match["name"]], _WIDTHS[match["kind"]], count)
    return fields


FIELDS = _fields()
RECORD_BYTES = {"WS": WS_BYTES, "FONT": FONT_HEADER_BYTES, "BITBLT": BITBLT_BYTES, "PB": PB_BYTES}


def field(record, name):
    """`record`'s field `name` (`"INTIN"` or `"LINEA_INTIN"` alike) — a KeyError naming it when the
    header has no FIELD of that name, which includes every count, mask and ROM table it defines."""
    short = name[len(record) + 1:] if name.startswith(record + "_") else name
    if short not in FIELDS[record]:
        raise KeyError(f"{record}_{short} is not a {record} field the headers tag with a width "
                       f"(`vdi/linea.h`, THE WIDTH TAG) — known: {', '.join(sorted(FIELDS[record]))}")
    return FIELDS[record][short]


def _encode(record, name, spec, value):
    """One field's bytes: a scalar in range for its width (a negative is its two's complement), or an
    array no longer than its count, given as `bytes` or as a sequence of elements."""
    def one(element):
        bits = 8 * spec.width
        if not -(1 << (bits - 1)) <= element < (1 << bits):
            raise ValueError(f"{record}_{name} is {spec.width} byte(s) wide; {element:#x} does not fit")
        return (element & ((1 << bits) - 1)).to_bytes(spec.width, "big")
    if spec.count is None:
        return one(value)
    data = bytes(value) if isinstance(value, (bytes, bytearray)) else b"".join(one(v) for v in value)
    if len(data) > spec.count * spec.width:
        raise ValueError(f"{record}_{name} holds {spec.count} x {spec.width} bytes; {len(data)} given")
    return data


def field_pokes(record, base=0, **values):
    """Fields of `record` at `base`, by name — `field_pokes("WS", at, WRT_MODE=2)`. LINEA's fields are
    absolute, so its base is 0."""
    pokes = {}
    for name, value in values.items():
        spec = field(record, name)
        pokes[base + spec.at] = _encode(record, name, spec, value)
    for at, data in pokes.items():
        require_claimed(at, len(data))
    return pokes


def read_field(image, record, name, base=0):
    """A field back out of `image`: an int, or a list of elements for an array."""
    spec = field(record, name)
    at = base + spec.at
    count = spec.count or 1
    elements = [int.from_bytes(bytes(image[at + i * spec.width:at + (i + 1) * spec.width]), "big")
                for i in range(count)]
    return elements if spec.count else elements[0]


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
    """A poke into the window must lie inside ONE claimed band — the Registry refuses overlapping
    claims, this refuses a poke that runs out of its own. Outside the window it is the caller's."""
    if at + size <= WINDOW_AT or at >= WINDOW_AT + WINDOW_BYTES:
        return
    for claim_at, claim_size, _owner in SPAN.claims:
        if claim_at <= at and at + size <= claim_at + claim_size:
            return
    raise AssertionError(f"a {size}-byte poke at {at:#x} is not inside one band of {SPAN.label}: "
                         f"{[(hex(a), hex(s), o) for a, s, o in SPAN.claims]}")


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
# `$fca9f6`'s copies of the record into Line-A and VDI RAM ($fcaa40..$fcab14), in the ROM's order:
# (where the copy goes, the workstation field it is copied from). Widths are the field's own.
DISPATCH_COPIES = (
    (LINEA_CLIP, "CLIP"),
    (LINEA_INQ_TAB + VDI_INQ_TAB_CLIP_INDEX * WORD_BYTES, "CLIP"),
    (LINEA_XMINCL, "XMN_CLIP"),
    (LINEA_YMINCL, "YMN_CLIP"),
    (LINEA_XMAXCL, "XMX_CLIP"),
    (LINEA_YMAXCL, "YMX_CLIP"),
    (LINEA_WRT_MODE, "WRT_MODE"),
    (LINEA_PATPTR, "PATPTR"),
    (LINEA_PATMSK, "PATMSK"),
    (LINEA_FONT_RING + LINEA_FONT_RING_LOADED * LONG_BYTES, "LOADED_FONTS"),
    (LINEA_DEV_TAB + VDI_DEV_TAB_FACES_INDEX * WORD_BYTES, "NUM_FONTS"),
    (LINEA_DDA_INC, "DDA_INC"),
    (LINEA_T_SCLSTS, "T_SCLSTS"),
    (LINEA_SCALE, "SCALED"),
    (LINEA_CUR_FONT, "CUR_FONT"),
    (LINEA_SCRPT2, "SCRPT2"),
    (LINEA_SCRTCHP, "SCRTCHP"),
    (LINEA_STYLE, "STYLE"),
    (VDI_TEXT_H_ALIGN, "H_ALIGN"),
    (VDI_TEXT_V_ALIGN, "V_ALIGN"),
    (LINEA_CHUP, "CHUP"),
)


def dispatcher_copies(image, at):
    """What `$fca9f6` stores before `jsr`ing a function, for the workstation at `at` in `image`: the
    plain copies above, the two computed ones — MULTIFILL only for the user interior ($fcaa8e), and
    MONO_STATUS from the font the record names ($fcaade) — and CUR_WORK and a cleared VDI_RESULT."""
    pokes = {}
    for destination, name in DISPATCH_COPIES:
        spec = field("WS", name)
        pokes[destination] = bytes(image[at + spec.at:at + spec.at + spec.width])
    user_interior = read_field(image, "WS", "FILL_STYLE", at) == VDI_INTERIOR_USER
    multifill = read_field(image, "WS", "MULTIFILL", at) if user_interior else 0
    font = read_field(image, "WS", "CUR_FONT", at)
    mono = read_field(image, "FONT", "FLAGS", font) & FONT_FLAG_MONOSPACE_MASK
    return merge_pokes(pokes, linea_pokes(MULTIFILL=multifill, MONO_STATUS=mono, CUR_WORK=at),
                       {VDI_RESULT: bytes(WORD_BYTES)})


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


# THE ONE NAMING RULE (`addrs.h`, the VDI block): every VDI routine address is `VDI_ROM_<X>` and every
# Line-A primitive's `LINEA_ROM_<X>` — a `VDI_`/`LINEA_` name without the `ROM_` is data or a field. The
# C core DROPS the `rom_` (`VDI_ROM_VSF_PERIMETER` -> `vdi_vsf_perimeter`, `LINEA_ROM_HLINE` ->
# `linea_hline`) and a `.S` transcription KEEPS it (`vdi_rom_vsf_perimeter`, `linea_rom_hline`), so both
# directions are a case change and nothing is guessed. `bench/tier3.py` derives its symbols from these.
ROUTINE_PREFIX = "VDI_ROM_"      # ...of which a VDI FUNCTION is the one with an `_OPCODE` sibling
LINEA_ROUTINE_PREFIX = "LINEA_ROM_"
ROUTINE_PREFIXES = (ROUTINE_PREFIX, LINEA_ROUTINE_PREFIX)
ROM_INFIX = "ROM_"


def is_routine(name):
    """Whether `name` is an `addrs.h` VDI or Line-A ROUTINE address, by the naming rule."""
    return name.startswith(ROUTINE_PREFIXES)


def core_symbol(name):
    """The C core an `addrs.h` routine name is reconstructed as: its name less the `ROM_`, lower-cased."""
    assert is_routine(name), f"{name} is not a `{ROUTINE_PREFIX}<X>` or `{LINEA_ROUTINE_PREFIX}<X>` routine name"
    return name.replace(ROM_INFIX, "", 1).lower()


def run_function(name, pokes, **kwargs):
    """The VDI FUNCTION `addrs.<name>` (a `VDI_ROM_<FN>`), entered as the dispatcher's `jsr` leaves the
    machine — so `pokes` should come from `call_pokes`, which stages the dispatched workstation —
    against the core `void vdi_<fn>(uint8_t *image)`. Answers a `Result`; `kwargs` are `case.run`'s."""
    core = _core(core_symbol(name), None)
    info = case.run(getattr(addrs, name), {"_pokes": pokes}, lambda lib, buf: core(buf),
                    width=case.NO_RESULT, **kwargs)
    return Result(info, pokes)


# A PRIMITIVE's register contract, declared once: the registers that are its C arguments, in order,
# and the registers its answer is in. `bench/tier3.py` builds the Tier 3 call from the same entry.
Primitive = namedtuple("Primitive", "arguments results")
PRIMITIVES = {}
# Room for every register a primitive may answer in: D0-D2/A0-A2, the six the Line-A exception does
# not restore ($fc9f28 saves D3-D7/A3-A5 only).
RESULTS_MAX = 6
RESULTS_ARRAY = ctypes.c_uint32 * RESULTS_MAX


def declare_primitive(name, *, arguments=(), results=()):
    """Declare `addrs.<name>`'s contract. The C core is `<core_symbol(name)>(image, *arguments)`,
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
    core = _core(core_symbol(name), ctypes.c_uint32 if answers_d0 else None)
    answers = []

    def glue(_lib_, buf):
        if not several:
            return core(buf, *values)
        out = RESULTS_ARRAY()
        returned = core(buf, *values, out)
        answers.append(list(out)[:len(contract.results)])
        return returned

    info = case.run(entry, {**registers, "_pokes": pokes}, recording(glue) if recording else glue,
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
# has no Tier 3 row (a case entered at the Line-A exception stub rather than the routine).
CASES = []
UNPRICED = []


def register(name, entry, pokes, *, regs=None, psg_seed=None, io_seed=None, schedule=(), priced=True):
    """One `VERIFIED_CASES` row (`case.verified_row`), recorded and returned so the battery drives the
    same tuple."""
    row = case.verified_row(name, entry, regs or {}, pokes, psg_seed, io_seed, schedule)
    (CASES if priced else UNPRICED).append(row)
    return row


# ---- (h) a TRANSCRIPTION: a hand-68000 routine the target build ships as the ROM's own `.S` ---------
# The user's rule for the hand-written routines: C first (Tier 1 proves it), and where the C measures
# over the 1.10 bar, the ROM's own instructions in a `src/vdi/*.S`, byte-pinned and held by Tier 3's
# TRANSCRIPTION relation (`RomBench.measure_transcription`) to the same image, the WHOLE register file
# and the same chip traffic. The `.S` entry is the ROM routine's `addrs.h` name lower-cased
# (`VDI_ROM_VS_COLOR` -> `vdi_rom_vs_color`), which is how `bench/tier3.py` finds the address a row is
# about.
#
# ONE IMAGE SERVES BOTH SIDES (`test/trap.py`'s arrangement): both are entered at a staged CALLER that
# jumps through the longword at `abi.FIRST_ARG` — the ROM routine, as the case pokes it, or the blob's,
# which `run_bench` writes over that slot — with the sentinel still under it, so the routine sees the
# `jsr` frame the dispatcher leaves. The caller's own cost is in both columns and comes off both.
#
# A staged caller as a row carries it: where it is, its bytes, and what it costs (off both columns). A
# battery whose routine needs another shape stages its own in its own band through `staged_caller`, which
# REGISTERS it: `test_vdi_transcribed.py` measures every registered caller's cost against the one it
# declares (`assert_caller_cost`), so no caller's number is a literal nobody re-derives.
# A caller that enters a routine BELOW a frame the routine's front end would have built (a body whose own
# epilogue pops what that front end pushed) is measured over that epilogue instead of a bare `rts`: its
# `routine` stand-in and the stand-in's `routine_cost` (None: the bare `rts`, `RTS_COST`).
Caller = namedtuple("Caller", "at stub cost routine routine_cost", defaults=(RTS, None))
CALLERS = []


def staged_caller(at, stub, cost, *, routine=RTS, routine_cost=None):
    """A transcription caller at `at`, declared to cost `(instructions, cycles)` — and registered."""
    caller = Caller(at, stub, cost, routine, routine_cost)
    CALLERS.append(caller)
    return caller


def assert_caller_cost(caller, regs=None):
    """`caller` entered with a bare `rts` for the routine (or its declared stand-in) costs its declared `cost`
    and nothing else: the oracle's reset (`RomBench.overhead`, which `test_tier3.py` pins) and that `rts`
    (`RTS_COST`) are all the rest of the run. Answers the register file it left, for a caller that also
    promises what it does to one."""
    pokes = {caller.at: caller.stub, STUB_AT: caller.routine, abi.FIRST_ARG: struct.pack(">I", STUB_AT)}
    _final, _writes, left = emu.run(make_image(pokes), caller.at, {**DIRTY, **(regs or {})})
    reset, rts, cost = bench().overhead, caller.routine_cost or RTS_COST, caller.cost
    assert (left["ninsns"], left["cycles"]) == (reset[0] + cost[0] + rts[0], reset[1] + cost[1] + rts[1]), (
        f"the caller at {caller.at:#x} costs {left['ninsns']} / {left['cycles']} with the reset and its routine's "
        f"stand-in, not the declared {cost} over {reset} and {rts}")
    return left


RTS_COST = (1, 16)              # the bare `rts` a caller is measured over
# THE REGISTER FILE every transcription is entered with, under the case's own registers: every register
# different, so a register the `.S` left where the ROM changed it — or changed where the ROM left it —
# shows.
DIRTY = {name: 0x0D0D_0000 + index * 0x1111 for index, name in enumerate(emu.REPORTED_REGS)}
TRANSCRIPTION_CALLER = PUSH_STACK_LONG + struct.pack(">h", abi.FIRST_ARG - emu.STACK_TOP) + RTS
PLAIN_CALLER = staged_caller(TRANSCRIPTION_CALLER_AT, TRANSCRIPTION_CALLER, (2, 40))
TRANSCRIPTIONS = []
LABELS = {}
TRANSCRIPTION_ROLES = {"vdi_rom_": "VDI", "linea_rom_": "Line-A"}


# A CODE-POINTER CALLER: for a `.S` that returns with an address INSIDE ITSELF in a register — a fragment
# it reached through `jsr (a5)`, a loop it left in A3 — which is the one thing a transcription linked
# anywhere else must differ in. The case is entered through a caller that returns through itself and
# zeroes exactly those registers on BOTH sides, so every other register is still compared:
#
#     pea     back(pc) / move.l 8(sp),-(sp) / rts / back: suba.l An,An ... / rts
#
# Which registers, per routine, is MEASURED by each battery and declared to its `CallerPool`.
_ROUTINE_SLOT = abi.FIRST_ARG - emu.STACK_TOP + LONG_BYTES     # FIRST_ARG, past the pushed return
_JUMP_BYTES = len(PUSH_STACK_LONG) + WORD_BYTES + len(RTS)
# pea + move.l + rts in and an rts out, and one suba.l per register (6 cycles as Musashi counts it): the
# declared cost of each caller is their sum, and `test_vdi_transcribed.py` measures every one against it.
CODE_POINTER_CALLER_COST = (4, 72)
CLEAR_COST = (1, 6)


def code_pointer_stub(registers):
    """The bytes of a caller that clears `registers` on the way out, and the cost it declares — position
    independent, so each battery stages its own in its own band (`CallerPool`)."""
    clears = b"".join(CLEAR_ADDRESS_REGISTER[register] for register in registers)
    stub = (PUSH_RETURN_PC + struct.pack(">h", _JUMP_BYTES + WORD_BYTES)
            + PUSH_STACK_LONG + struct.pack(">h", _ROUTINE_SLOT) + RTS + clears + RTS)
    cost = tuple(base + len(registers) * each for base, each in zip(CODE_POINTER_CALLER_COST, CLEAR_COST))
    return stub, cost


class CallerPool:
    """One battery's CODE-POINTER CALLERS, staged in its own band `[at, end)` one `stride` apart: the
    caller that clears a register set is built on first ask and registered (`staged_caller`), and the
    plain caller answers for an empty set. `code_pointers` is the battery's MEASURED `{routine: registers}`
    — what `caller_for` enters a routine through when a case names none."""

    def __init__(self, at, end, stride, code_pointers=None, *, built=()):
        self.at, self.end, self.stride = at, end, stride
        self.code_pointers = dict(code_pointers or {})
        self._callers = {}
        # Built now, so each is registered — and its cost measured — before any case asks for it.
        for registers in (*self.code_pointers.values(), *built):
            self.caller(registers)

    def caller(self, registers):
        if not registers:
            return PLAIN_CALLER
        if registers not in self._callers:
            stub, cost = code_pointer_stub(registers)
            at = self.at + len(self._callers) * self.stride
            assert len(stub) <= self.stride and at + self.stride <= self.end, (
                f"no room for a caller clearing {registers} in [{self.at:#x}, {self.end:#x})")
            self._callers[registers] = staged_caller(at, stub, cost)
        return self._callers[registers]

    def caller_for(self, name, code_pointers=None):
        """The caller `name`'s transcription is entered through: `code_pointers` cleared, or the routine's
        own declared set when the case names none."""
        return self.caller(self.code_pointers.get(name, ()) if code_pointers is None else code_pointers)

    def run_transcription(self, name, pokes, regs=None, *, code_pointers=None, **kwargs):
        return run_transcription(name, pokes, regs, caller=self.caller_for(name, code_pointers), **kwargs)

    def register_transcription(self, name, label, pokes, regs=None, *, code_pointers=None, **kwargs):
        return register_transcription(name, label, pokes, regs, caller=self.caller_for(name, code_pointers),
                                      **kwargs)


def transcription_symbol(name):
    """The `.S` entry a `VDI_ROM_<X>` or `LINEA_ROM_<X>` routine is transcribed as: its name lower-cased."""
    assert is_routine(name), f"{name} is not a `{ROUTINE_PREFIX}<X>` or `{LINEA_ROUTINE_PREFIX}<X>` routine name"
    return name.lower()


def transcription_routine(symbol):
    """...and back: the `addrs.h` name of the routine a `.S` entry transcribes."""
    name = symbol.upper()
    assert is_routine(name) and hasattr(addrs, name), f"{symbol} transcribes no routine `addrs.h` names"
    return name


# THE BYTE PIN, one comparator for every `.S`. A transcription lays out a ROM REGION in the ROM's own
# order, so one entry in it (the `anchor` routine) places the whole region in the blob. The spelling
# policy (`include/m68k_encodings.h`) leaves exactly one kind of word that may differ: a reference that
# measures to where the `.S` itself is linked — a branch displacement from one region into another, or
# an absolute address of the transcription's own table. Each is RELOCATED: `width` says which (a word is
# a displacement from the extension word, a long an absolute address), and the comparator computes the
# EXACT value it must hold from the ROM's own reference and where `target_anchor`'s region is in the blob.
Relocated = namedtuple("Relocated", "width target_anchor why")
PC_RELATIVE = WORD_BYTES
ABSOLUTE = LONG_BYTES


def transcribed_address(anchor, rom_address):
    """Where the blob holds `rom_address` of the region the `.S` entry of routine `anchor` lays out."""
    return bench().entry(transcription_symbol(anchor)) + rom_address - getattr(addrs, anchor)


def _blob_bytes(address, size):
    blob = bench()
    return bytes(blob.blob[address - blob.base:address - blob.base + size])


def _relocation_target(at, relocation):
    """The ROM address the ROM's own reference at `at` names: a displacement from its extension word, or
    an absolute address."""
    pc_relative = relocation.width == PC_RELATIVE
    rom = int.from_bytes(bytes(BASE_IMAGE[at:at + relocation.width]), "big", signed=pc_relative)
    return at + rom if pc_relative else rom


def _relocated_value(at, placed_at, relocation):
    """The exact bytes the reference at ROM address `at`, placed at blob address `placed_at`, must hold:
    the ROM's own reference followed to its target, and that target's place in the blob."""
    target = transcribed_address(relocation.target_anchor, _relocation_target(at, relocation))
    if relocation.width == PC_RELATIVE:
        return (target - placed_at).to_bytes(WORD_BYTES, "big", signed=True)
    return target.to_bytes(LONG_BYTES, "big")


# THE REGIONS THE BATTERIES PIN, declared where each battery lays its own out (`pinned_region`). A
# relocation's value is computed from where its TARGET routine's region sits in the blob — sound only if the
# target, and the routine it is measured from, lie in ONE region some battery byte-pins: the `.S` lays a
# region out contiguously and the pin proves it did. A reference into bytes nobody pins would be a value
# computed against a layout nobody checked (`text_raster.S`'s `lea` of raster.S's fringe table is the case
# that asks it).
Region = namedtuple("Region", "lo hi anchor entries", defaults=((),))
PINNED_REGIONS = []
_DECLARES_A_REGION = "vdi.pinned_region("


def pinned_region(lo, hi, anchor, entries=()):
    """Declare the ROM bytes `lo`..`hi`, laid out from the `.S` entry of `anchor` (and holding `entries`'),
    as a region this battery byte-pins — at import, so every region is known before any pin runs."""
    region = Region(lo, hi, anchor, tuple(entries))
    PINNED_REGIONS.append(region)
    return region


def every_pinned_region():
    """Every battery's regions, whichever batteries this process has imported: each test module that
    declares one is imported here first (a no-op for one already loaded)."""
    for path in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        if _DECLARES_A_REGION in path.read_text():
            importlib.import_module(path.stem)
    return tuple(PINNED_REGIONS)


def _one_pinned_region_holds(*addresses):
    return any(all(region.lo <= address < region.hi for address in addresses) for region in every_pinned_region())


def assert_transcribed(anchor, lo, hi, *, entries=(), relocated=None):
    """The ROM's bytes `lo`..`hi` against the blob's, the region laid out from the `.S` entry of `anchor`:
    every other routine in `entries` where the ROM has it, and every word EQUAL but the references
    `relocated` names — `{ROM address: Relocated}` — which must hold exactly the value their target's
    place in the blob gives them. A relocation that happens to equal the ROM's word is refused too: it
    names a word that needs no excuse."""
    relocated = relocated or {}
    assert Region(lo, hi, anchor) in {region._replace(entries=()) for region in every_pinned_region()}, (
        f"${lo:x}..${hi:x} from {anchor} is pinned but no battery declares it (`vdi.pinned_region`)")
    for at, relocation in relocated.items():
        target = _relocation_target(at, relocation)
        assert _one_pinned_region_holds(target, getattr(addrs, relocation.target_anchor)), (
            f"${at:x} ({relocation.why}) is relocated to ${target:x} as measured from {relocation.target_anchor}, "
            f"but no byte-pinned region holds both — its value would be computed against a layout nobody checks")
    start = transcribed_address(anchor, lo)
    for name in entries:
        assert transcribed_address(anchor, getattr(addrs, name)) == bench().entry(transcription_symbol(name)), (
            f"{name} is not where the ROM has it in the region {anchor} lays out")
    at = lo
    while at < hi:
        relocation = relocated.get(at)
        size = relocation.width if relocation else WORD_BYTES
        placed_at = start + at - lo
        ours, theirs = _blob_bytes(placed_at, size), bytes(BASE_IMAGE[at:at + size])
        if relocation:
            expected = _relocated_value(at, placed_at, relocation)
            assert ours != theirs, f"${at:x} is relocated ({relocation.why}) and equals the ROM's — drop it"
            assert ours == expected, (f"${at:x} ({relocation.why}) holds {ours.hex()}, not the {expected.hex()} its "
                                      f"target's place in the blob gives")
        else:
            assert ours == theirs, f"the transcription of ${at:x} holds {ours.hex()} against the ROM's {theirs.hex()}"
        at += size
    assert not set(relocated) - set(range(lo, hi, WORD_BYTES)), "a relocation outside the region pinned"


def transcription_pokes(name, pokes, caller=PLAIN_CALLER):
    """`pokes` with the staged caller and the ROM routine it enters on the ORIGINAL's side."""
    return merge_pokes(pokes, {caller.at: caller.stub, abi.FIRST_ARG: struct.pack(">I", getattr(addrs, name))})


def run_transcription(name, pokes, regs=None, *, io_seed=None, caller=PLAIN_CALLER):
    """The `.S` of `addrs.<name>` against the ROM routine over `pokes`, through the transcription
    relation, entered with `regs` laid over `DIRTY` — the WHOLE register file. Answers the `Measurement`."""
    return bench().measure_transcription(caller.at, transcription_symbol(name), {**DIRTY, **(regs or {})},
                                         pokes=transcription_pokes(name, pokes, caller), io_seed=io_seed,
                                         shared_entry=caller.cost)


def register_transcription(name, label, pokes, regs=None, *, io_seed=None, caller=PLAIN_CALLER):
    """One Tier 3 TRANSCRIPTION row (`bench/tier3.py` reads `TRANSCRIPTIONS`), entered as
    `run_transcription` enters it: `label` is the case, and the function's own label is its `.S` entry's."""
    symbol = transcription_symbol(name)
    spelt = next(spelt for spelt in TRANSCRIPTION_ROLES if symbol.startswith(spelt))
    LABELS[symbol] = f"{TRANSCRIPTION_ROLES[spelt]} {symbol[len(spelt):]} (.S)"
    row = (label, symbol, caller.at, {**DIRTY, **(regs or {})}, transcription_pokes(name, pokes, caller), caller.cost,
           io_seed)
    TRANSCRIPTIONS.append(row)
    return row


# ---- (i) the TRANSCRIBED table: which routines SHIP as their `.S` (`include/vdi/transcribed.h`) --------
# `{`.S` entry: the GCC callee-saved registers it leaves changed}`, parsed out of the header's rows as
# `addrs.py` parses a `#define`: the one source Tier 3's (T) rule, the build contract and the C
# declarations all read. `test_vdi_transcribed.py` holds it to the `.S` sources, the makefile and the
# ROM's measured register file.
TRANSCRIBED_HEADER = _INCLUDE / "vdi" / "transcribed.h"
_TRANSCRIBED_ROW = re.compile(r'^\s*ENTRY\((?P<entry>[a-z0-9_]+),\s*"(?P<destroys>[^"]*)"\)')
TRANSCRIBED = {match["entry"]: tuple(match["destroys"].split())
               for match in map(_TRANSCRIBED_ROW.match, TRANSCRIBED_HEADER.read_text().splitlines()) if match}
assert TRANSCRIBED, f"{TRANSCRIBED_HEADER} has no `ENTRY(...)` row this parser reads"


def transcribed_core(entry):
    """The C core a `.S` entry is the transcription of: `linea_rom_hline` -> `linea_hline`."""
    return core_symbol(transcription_routine(entry))


TRANSCRIBED_CORES = {transcribed_core(entry): entry for entry in TRANSCRIBED}

# THE C THAT CALLS A TRANSCRIBED C CORE from outside the table, as `(caller, core)`: the one list of the
# calls a shipped build makes through glue (`bench/shipped_glue.py` generates a thunk per core named here).
# `test_vdi_transcribed.py` holds it to the calls the m68k build really makes (`call_graph`).
C_CALLERS_OF_TRANSCRIBED_CORES = {
    ("vdi_vq_key_s", "vdi_get_kbshift"),
    # the polygon and contour-fill layer (`src/vdi/fill.c`)
    ("vdi_clip_line", "vdi_smul_div"), ("vdi_polyline", "linea_line"), ("vdi_plygn", "linea_filled_poly"),
    ("vdi_v_get_pixel", "linea_get_pixel"),
    ("linea_get_seed", "linea_end_pts"), ("linea_get_seed", "linea_fill_span"),
    ("linea_contour_fill", "linea_end_pts"), ("linea_contour_fill", "linea_get_pixel"),
    ("linea_contour_fill", "linea_fill_span"),
    # the raster functions (`src/vdi/blit.c`)
    ("vdi_vro_cpyfm", "linea_copy_raster"), ("vdi_vrt_cpyfm", "linea_copy_raster"), ("vdi_vr_recfl", "linea_filled_rect"),
    # the mouse and input functions (`src/vdi/mouse.c`)
    ("vdi_v_show_c", "vdi_show_cursor"), ("vdi_v_hide_c", "linea_hide_mouse"),
    ("vdi_locator", "vdi_show_cursor"), ("vdi_locator", "vdi_poll_locator"), ("vdi_locator", "linea_hide_mouse"),
    ("vdi_choice", "vdi_poll_choice"), ("vdi_mouse_init", "vdi_vsc_form"),
}

# A function's name as `m68k-elf-objdump` labels it, the one GCC split off it (`name.part.0`, `.constprop.0`,
# `.isra.0`) folded back into it, and an offset into it (`name+0x12`) dropped.
_LISTED_FUNCTION = re.compile(r"^([0-9a-f]+) <([\w.]+)>:$")
_LISTED_INSTRUCTION = re.compile(r"^\s+([0-9a-f]+):")
_LISTED_REFERENCE = re.compile(r"<([\w.]+)(?:\+0x[0-9a-f]+)?>")


def _unsplit(name):
    return name.split(".")[0]


def _function_ends(elf):
    """`{address: end}` of every function the symbol table SIZES. A disassembly runs a function on to the
    next label, and in the shipped blob the next label is not always the next function: a weak C core the
    glue displaced keeps its body but loses its name, so its instructions would be read as its neighbour's."""
    table = subprocess.run(["m68k-elf-nm", "-S", "--defined-only", str(elf)], capture_output=True, text=True,
                           check=True).stdout
    return {int(fields[0], 16): int(fields[0], 16) + int(fields[1], 16)
            for fields in (line.split() for line in table.splitlines()) if len(fields) == 4}


def call_graph(elf):
    """`{function: every function its code references}` out of the m68k build at `elf` — a `jsr`, a
    branch, or a `lea` of an address GCC then calls through a register, which is how it calls one it
    names more than once. A function the symbol table sizes is read to its end and no further."""
    listing = subprocess.run(["m68k-elf-objdump", "-d", str(elf)], capture_output=True, text=True,
                             check=True).stdout
    ends = _function_ends(elf)
    graph, function, end = {}, None, None
    for line in listing.splitlines():
        start = _LISTED_FUNCTION.match(line)
        if start:
            function, end = _unsplit(start.group(2)), ends.get(int(start.group(1), 16))
            graph.setdefault(function, set())
            continue
        instruction = _LISTED_INSTRUCTION.match(line)
        if function and instruction and (end is None or int(instruction.group(1), 16) < end):
            graph[function] |= {_unsplit(target) for target in _LISTED_REFERENCE.findall(line)} - {function}
    return graph


def callers_of_transcribed_cores(graph):
    """The `(caller, core)` references to a transcribed C core from a function outside the table."""
    return {(function, target) for function, targets in graph.items() if function not in TRANSCRIBED_CORES
            for target in targets if target in TRANSCRIBED_CORES}


def reaching_transcribed_cores(graph):
    """Every function outside the table from which a transcribed C core is reachable: its direct callers
    and whatever calls them — the C whose cost, as shipped, includes a `.S`."""
    reaching = {function for function, _core in callers_of_transcribed_cores(graph)}
    grown = True
    while grown:
        more = {function for function, targets in graph.items()
                if function not in TRANSCRIBED_CORES and function not in reaching and targets & reaching}
        reaching |= more
        grown = bool(more)
    return reaching


# ---- (j) the ALCYON calls: the C signature a frame's words and longwords are decoded into ---------------
# An Alcyon C routine is entered by `jsr` over the frame its caller pushed — WORD arguments (an Alcyon `int`
# is 16 bits), LONG addresses — and answers a word in D0.w, which is all its callers read. `declare_alcyon`
# is the ONE statement of each such core's C signature: the batteries stage the frame from it, the host
# core's ctypes signature is set from it, `bench/tier3.py` decodes its Tier 3 call out of the same frame by
# it, and `bench/shipped_glue.py` repacks a GCC call into that frame by it.
IMAGE_ARG = ctypes.POINTER(ctypes.c_uint8)
WORD_ARG = ctypes.c_int16
LONG_ARG = ctypes.c_uint32
ARG_BYTES = {WORD_ARG: WORD_BYTES, LONG_ARG: LONG_BYTES}
WORD_RESULT = 16                # the bits of D0 an Alcyon `int` answer is compared at
Alcyon = namedtuple("Alcyon", "restype argtypes")
ALCYON = {}


def declare_alcyon(name, restype, argtypes):
    """`addrs.<name>`'s core is an Alcyon call `restype core(argtypes)` — the image first where it takes
    one, then the frame's arguments in push order; `restype` None for no answer."""
    ALCYON[name] = Alcyon(restype, tuple(argtypes))
    core = getattr(_lib, core_symbol(name))
    core.restype, core.argtypes = restype, list(argtypes)
    return ALCYON[name]


def frame_argtypes(name):
    """The argument types an Alcyon routine's FRAME carries: its signature less the image."""
    argtypes = ALCYON[name].argtypes
    return argtypes[1:] if argtypes[:1] == (IMAGE_ARG,) else argtypes


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
