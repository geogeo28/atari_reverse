"""What the mouse, cursor and input batteries share (`src/vdi/mouse.c`): the register contracts, a band of the
VDI window, sprite forms, and the USER VECTORS the mouse ISR calls.

THE CONTRACTS are declared here, once, for every register routine these batteries run — `bench/tier3.py`
builds each Tier 3 call from the same declaration. Every one of the mouse routines answers nothing in a
register a caller reads, except the three polls (D0).

THE USER VECTORS. `$fcfe28` calls USER_BUT, USER_MOT and USER_CUR with D0/D1 IN AND OUT, and in the captured
machine the first two point into the AES. So a case repoints each at a routine it stages: a 68000 stub for
the ORACLE, planted in this module's band, and the same effect in Python for the CANDIDATE, which reaches it
through `staged_call.h`'s register-carrying hook (`isr.REGISTERS_HOOK`, D0/D1/A0 in and out) — keyed by address, so a stub staged beside the named
one means something on both sides. A routine staged at a ROM ADDRESS plants nothing and runs our own C for it:
the snapshot's USER_CUR is `$fcff0a` itself, and a case may leave it there.
"""
import ctypes
import random
import struct
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs

import case
import iorec
import isr
import vdi
import vdi_raster
from case import merge_pokes
from opcodes import LOAD_IMMEDIATE, RTS, STORE_LONG_REGISTER

MOUSE_H = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "mouse.h",
                      known={**addrs.ADDRS, **vdi.CONSTANTS})

# ---- the register contracts ------------------------------------------------------------------------
CONTRACTS = {
    "LINEA_ROM_DRAW_SPRITE": {"arguments": ("a0", "a2", "d0", "d1")},
    "LINEA_ROM_UNDRAW_SPRITE": {"arguments": ("a2",)},
    "LINEA_ROM_HIDE_MOUSE": {},
    "VDI_ROM_SHOW_CURSOR": {},
    "VDI_ROM_MOUSE_ISR": {"arguments": ("a0", "d0", "d1")},
    "VDI_ROM_DEFAULT_USER_CUR": {"arguments": ("d0", "d1")},
    "VDI_ROM_VBL_DRAW_CURSOR": {},
    "VDI_ROM_MOUSE_INIT": {},
    "VDI_ROM_MOUSE_OFF": {},
    "VDI_ROM_POLL_LOCATOR": {"results": ("d0",)},
    "VDI_ROM_POLL_CHOICE": {"arguments": ("d0",), "results": ("d0",)},
    "VDI_ROM_POLL_KEY": {"results": ("d0",)},
}
# The C signatures follow: a register argument is a longword, which ctypes must be told — its default is a
# signed `int`, which refuses a register with bit 31 set.
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
_LONG = ctypes.c_uint32
for _name, _contract in CONTRACTS.items():
    vdi.declare_primitive(_name, **_contract)
    getattr(_lib, vdi.core_symbol(_name)).argtypes = [_IMAGE] + [_LONG] * len(_contract.get("arguments", ()))

# ---- this module's band of the VDI window -----------------------------------------------------------
BAND_OFFSET = 0x1E00
BAND_BYTES = 0x200
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_mouse.py: user-vector stubs, a packet, a form, a save block")
STUBS_AT = BAND_AT                          # the user-vector stubs, STUB_STRIDE apart
STUB_STRIDE = 0x20
STUB_SLOTS = 3
MARKS_AT = STUBS_AT + STUB_SLOTS * STUB_STRIDE      # the registers each stub was handed, two longwords a stub
MARK_BYTES = 8
PACKET_AT = MARKS_AT + STUB_SLOTS * MARK_BYTES      # a staged IKBD packet
PACKET_BYTES = 8
FORM_AT = PACKET_AT + PACKET_BYTES                  # a Line-A caller's own sprite form
FORM_BYTES = MOUSE_H["SPRITE_FORM_ROWS"] + MOUSE_H["SPRITE_ROWS"] * MOUSE_H["SPRITE_FORM_ROW_BYTES"]
# A save block's fields as offsets, the way the pair reaches any block through A2 (`vdi/mouse.h` spells them
# as the same differences, which its parser here cannot evaluate).
SAVE_LEN = vdi.LINEA_SAVE_LEN - vdi.LINEA_SAVE_BLOCK
SAVE_ADDR = vdi.LINEA_SAVE_ADDR - vdi.LINEA_SAVE_BLOCK
SAVE_STAT = vdi.LINEA_SAVE_STAT - vdi.LINEA_SAVE_BLOCK
SAVE_AREA = vdi.LINEA_SAVE_AREA - vdi.LINEA_SAVE_BLOCK
SAVE_BLOCK_AT = BAND_AT + BAND_BYTES - vdi.LINEA_SAVE_BLOCK_BYTES   # ...and its own save block
CALLERS_AT = FORM_AT + FORM_BYTES                   # the transcription callers below
CALLER_BYTES = 0x14

# ---- sprite forms ---------------------------------------------------------------------------------------
FORM_WORDS = MOUSE_H["SPRITE_ROWS"] * 2
SPRITE_ROWS = MOUSE_H["SPRITE_ROWS"]
# A form whose every mask and data word differs from the others, so a row drawn from the wrong place or
# shifted by the wrong amount changes a bit the ROM left alone. The seed is fixed so a failure reproduces.
FORM_SEED = 0x1D_A00D
_FORM_WORDS = random.Random(FORM_SEED)
RANDOM_ROWS = tuple(_FORM_WORDS.getrandbits(16) for _ in range(FORM_WORDS))
assert len(set(RANDOM_ROWS)) == len(RANDOM_ROWS), "every mask and data word its own"
# The captured machine's own form: the arrow vsc_form stored at boot, and the one the ROM's callers draw.
M_POS_HX = vdi.LINEA_M_POS_HX


def form_bytes(hot_x=0, hot_y=0, planes=1, bg=0, fg=1, rows=RANDOM_ROWS):
    """A sprite form in `$a00d`'s layout (`vdi/mouse.h`): hot spot, planes word, colours, then 16 x
    (mask, data)."""
    return vdi.pack_words(hot_x, hot_y, planes, bg, fg, *rows)


def form_pokes(at=FORM_AT, **fields):
    return {at: form_bytes(**fields)}


def save_block_pokes(at=SAVE_BLOCK_AT, fill=vdi.FILL):
    """A save block FILLed, so a word the reconstruction did not save reads as one no arm produces."""
    return {at: bytes([fill]) * vdi.LINEA_SAVE_BLOCK_BYTES}


def sprite_registers(x, y, form=FORM_AT, save_block=SAVE_BLOCK_AT):
    return {"a0": form, "a2": save_block, "d0": x & 0xFFFF_FFFF, "d1": y & 0xFFFF_FFFF}


# The three screen shapes, with the DEV_TAB bounds each resolution has.
LOW = {"shape": vdi_raster.LOW, "last": (319, 199)}
MEDIUM = {"shape": vdi_raster.MEDIUM, "last": (639, 199)}
HIGH = {"shape": vdi_raster.HIGH, "last": (639, 399)}
RESOLUTIONS = {"low": LOW, "medium": MEDIUM, "high": HIGH}


def resolution_pokes(resolution):
    return merge_pokes(vdi_raster.geometry_pokes(resolution["shape"]),
                       vdi.linea_pokes(DEV_TAB=list(resolution["last"])))


def canvas_pokes(resolution=LOW):
    """The pseudo-random screen `vdi_raster` draws on, in `resolution`'s shape."""
    return merge_pokes(vdi_raster.CANVAS, resolution_pokes(resolution))


# ---- the USER VECTORS ------------------------------------------------------------------------------------
HOOK = isr.REGISTERS_HOOK
CALLS = HOOK.calls
REGISTERS = ("d0", "d1")                                          # what a stub records it was handed


def _long(value):
    return struct.pack(">I", value & 0xFFFF_FFFF)


def user_routine(slot, answers=None):
    """A staged user routine in stub slot `slot`: it records the D0/D1 it was handed at `mark(slot)` and
    answers `answers` — `{"d0": value, "d1": value, "a0": value}`, whole longwords — in place of any register
    named, A0 included: the ISR goes on reading its packet through the A0 a routine hands back.

    Returns `(address, (68000 stub, Python effect))`, the pair `HOOK.staged_routines` takes."""
    answers = answers or {}
    at, mark = STUBS_AT + slot * STUB_STRIDE, mark_at(slot)
    code = b"".join(STORE_LONG_REGISTER[name] + _long(mark + index * 4) for index, name in enumerate(REGISTERS))
    code += b"".join(LOAD_IMMEDIATE[name] + _long(value) for name, value in answers.items()) + RTS
    assert len(code) <= STUB_STRIDE

    def effect(buf, registers):
        for index in range(len(REGISTERS)):
            for offset, byte in enumerate(_long(registers[index])):
                buf[mark + index * 4 + offset] = byte
        for index, name in enumerate(isr.STAGED_REGISTERS):
            if name in answers:
                registers[index] = answers[name] & 0xFFFF_FFFF
    return at, (code, effect)


def mark_at(slot):
    return MARKS_AT + slot * MARK_BYTES


def handed(result, slot):
    """The (D0, D1) the routine in `slot` was handed, as the ORACLE's run left them."""
    return tuple(result.long(mark_at(slot) + index * 4) for index in range(len(REGISTERS)))


def rom_routine(core_symbol):
    """A ROM routine left in a user vector: nothing planted, our own C for it on the candidate's side."""
    core = getattr(_lib, core_symbol)

    def effect(buf, registers):
        core(buf, registers[0], registers[1])
    return b"", effect


def user_vector_pokes(**vectors):
    """USER_BUT / USER_MOT / USER_CUR pointed at routines — `user_vector_pokes(BUT=at, MOT=at)`."""
    return vdi.linea_pokes(**{f"USER_{name}": at for name, at in vectors.items()})


def staged(routines):
    """`routines` ({address: (stub, effect)}) planted in the image, for the ORACLE's side."""
    return {at: code for at, (code, _effect) in routines.items() if code}


def run_calling(name, registers, pokes, routines, **kwargs):
    """`vdi.run_primitive` for a routine that calls user vectors: the stubs planted, the hook bound."""
    with HOOK.staged_routines(routines):
        return vdi.run_primitive(name, registers, merge_pokes(pokes, staged(routines)),
                                 recording=HOOK.recording, **kwargs)


# ---- the keyboard, as the input polls read it ---------------------------------------------------------
KEY_BYTES = addrs.IOREC_KEY_BYTES


def keys_pokes(*keys, head=0):
    """The IKBD ring holding `keys` (scancode/ASCII longwords) after `head`, as the interrupt would leave it."""
    records = [(head + (index + 1) * KEY_BYTES, struct.pack(">I", key)) for index, key in enumerate(keys)]
    return iorec.staged(addrs.IOREC_IKBD, head, head + len(keys) * KEY_BYTES, records)


def key(scancode, ascii_code):
    return scancode << 16 | ascii_code


IKBD_TAIL = addrs.IOREC_IKBD + addrs.IOREC_TAIL
TAIL_BYTES = 2


def keys_arriving(site, *arrivals, head=0):
    """The IKBD ring EMPTY, its buffer already holding the keys, and the SCHEDULE of the keyboard interrupt
    that moves the tail past each one — `arrivals` is `(pass, key), ...`, the store landing at `site` (a
    request spin's wait site, `addrs.h`) before that pass's poll. Answers `(pokes, schedule)`."""
    keys = [key_ for _pass, key_ in arrivals]
    pokes = merge_pokes(keys_pokes(*keys, head=head), {IKBD_TAIL: struct.pack(">H", head)})
    schedule = [{"pc": site, "nth": nth, "addr": IKBD_TAIL, "width": TAIL_BYTES, "value": head + index * KEY_BYTES}
                for index, (nth, _key) in enumerate(arrivals, start=1)]
    return pokes, schedule


# ---- the spans these cases reach, for the snapshot-mask check -------------------------------------------
VBL_QUEUE = case.long_in(BASE_IMAGE, addrs.SYSVAR_VBLQUEUE)
vdi.declare_case_field(VBL_QUEUE, 4, "_vblqueue[0], which mouse_init and mouse_off write")


# ---- the TRANSCRIPTION's callers: the code pointers `mouse.S` leaves ---------------------------------------
# The sprite's fragments are reached through A3 (the spread), A4 (the combine), A5 (the store) and A6 (the
# row loop), so a routine that draws returns with four code addresses — the one thing a transcription linked
# anywhere else must differ in. MEASURED, not read: every other register a case leaves is equal. show_cursor
# keeps A6 round its draw, so it leaves three; the restore leaves only data. Each caller clears exactly those
# on BOTH sides (`vdi.CallerPool`, in this module's band), so everything else is still compared.
DRAWN_CODE_POINTERS = ("a3", "a4", "a5", "a6")
SHOWN_CODE_POINTERS = ("a3", "a4", "a5")
CODE_POINTERS = {"LINEA_ROM_DRAW_SPRITE": DRAWN_CODE_POINTERS, "VDI_ROM_VBL_DRAW_CURSOR": DRAWN_CODE_POINTERS,
                 "VDI_ROM_SHOW_CURSOR": SHOWN_CODE_POINTERS}
CALLERS = vdi.CallerPool(CALLERS_AT, SAVE_BLOCK_AT, CALLER_BYTES, CODE_POINTERS)
caller_for = CALLERS.caller_for
run_transcription = CALLERS.run_transcription
register_transcription = CALLERS.register_transcription
