"""What the polygon and fill batteries share (`src/vdi/fill.c`): the contracts, the Alcyon call door, the
SEEDABORT hook and its staged stub, and the fill attributes as the dispatcher leaves them.

THE CONTRACTS. `$a006` and `$a00f` are Line-A primitives reading only the Line-A variables, declared with
`vdi.declare_primitive` (no register argument, no answer). The Alcyon helpers — clip_line, polyline,
plygn, and the contour fill's fill_span / end_pts / crunch_queue / get_seed — are entered by `jsr` over
the frame their Alcyon caller pushes: WORD coordinates, LONG addresses, a WORD answer in D0. `vdi.declare_alcyon`
is the one statement of each core's C signature; `run_call` stages the frame for the ROM and hands the
same values to the core, and `bench/tier3.py` derives each Tier 3 call from the same table.

SEEDABORT (`LINEA_SEEDABORT`) is a RAM vector the contour fill calls once a pass. The snapshot holds 0
there — a `jsr` to the vector table — so every `$a00f` case stages it: the ROM's never-abort routine
(`LINEA_ROM_SEEDABORT_DEFAULT`, which the core answers itself), or `countdown_stub`, a routine of this
module's that answers nonzero on its Nth call. The candidate reaches a staged routine through `staged_call.h`'s
register-carrying hook (`isr.REGISTERS_HOOK`), bound here to the same effect in Python.
"""
import ctypes
import struct
import sys
from pathlib import Path

from harness import _lib, addrs

import abi
import case
import isr
import routines
import transcription
import vdi
import vdi_raster
from vdi import IMAGE_ARG, LONG_ARG, LONG_BYTES, WORD_ARG, WORD_BYTES, WORD_RESULT
from case import merge_pokes
from opcodes import DROP_STACK_BYTES, EXT_W_D0, PUSH_RETURN_PC, PUSH_STACK_LONG, RTS, SEQ_D0, SUBQ_W_1_ABSOLUTE_LONG

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/fill.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
sys.modules[__name__].__dict__.update(HEADER)

# The contour fill's queue runs on past the PTSIN copy — to the word one record past its last, which a
# full queue's QTOP names ($fd0f68) — and that tail is declared to the snapshot's mask test with the rest.
QUEUE_END = VDI_FILL_QUEUE + (VDI_FILL_QUEUE_LAST + VDI_FILL_RECORD_WORDS) * vdi.WORD_BYTES
_PTSIN_COPY_END = vdi.VDI_PTSIN_COPY + vdi.VDI_PTSIN_COPY_BYTES
vdi.declare_case_field(_PTSIN_COPY_END, QUEUE_END - _PTSIN_COPY_END, "the contour fill's queue past the PTSIN copy")

vdi.declare_primitive("LINEA_ROM_FILLED_POLY")
vdi.declare_primitive("LINEA_ROM_CONTOUR_FILL")

# ---- the Alcyon calls ---------------------------------------------------------------------------------
# The image first, then the frame's arguments in push order (`vdi.declare_alcyon`, the one registry).
for _name, _restype, _argtypes in (
        ("VDI_ROM_CLIP_LINE", ctypes.c_uint16, (IMAGE_ARG,)),
        ("VDI_ROM_POLYLINE", None, (IMAGE_ARG,)),
        ("VDI_ROM_PLYGN", None, (IMAGE_ARG,)),
        ("LINEA_ROM_FILL_SPAN", None, (IMAGE_ARG, WORD_ARG, WORD_ARG, WORD_ARG)),
        ("LINEA_ROM_END_PTS", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG, LONG_ARG, LONG_ARG)),
        ("LINEA_ROM_CRUNCH_QUEUE", None, (IMAGE_ARG,)),
        ("LINEA_ROM_GET_SEED", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG, LONG_ARG, LONG_ARG, LONG_ARG))):
    vdi.declare_alcyon(_name, _restype, _argtypes)
# The frame of an Alcyon call, and its words as the signed words they are: `test/vdi.py`'s, which the AES shares.
as_signed = vdi.as_signed
frame = vdi.alcyon_frame


def run_call(name, arguments, pokes, **kwargs):
    """The Alcyon routine `addrs.<name>` entered by `jsr` over its frame, against its core called with the
    same `arguments`; a word answer compared at 16 bits. Answers a `vdi.Result`."""
    restype = vdi.ALCYON[name].restype
    core = getattr(_lib, routines.core_symbol(name))
    arguments = as_signed(name, arguments)
    staged = merge_pokes(pokes, frame(name, *arguments))
    info = hooked_run(getattr(addrs, name), staged, lambda _lib_, buf: core(buf, *arguments),
                      width=WORD_RESULT if restype is not None else case.NO_RESULT, **kwargs)
    return vdi.Result(info, staged)


def register_call(label, name, arguments, pokes):
    """One Tier 3 row of an Alcyon call: its frame staged as `run_call` stages it."""
    vdi.register(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), merge_pokes(pokes, frame(name, *arguments)))


def answer(result):
    """The word an Alcyon routine answered, signed."""
    return vdi.signed_word(result.info["regs"]["d0"] & 0xFFFF)


# ---- this module's band of the VDI window: the SEEDABORT stubs ---------------------------------------
BAND_OFFSET = 0x1D40
BAND_BYTES = 0x40
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_fill.py: SEEDABORT stubs and their counter")
COUNTER_AT = BAND_AT
SLOT_BYTES = 0x10                       # the band in three slots: the counter, the stub, the frame caller
STUB_AT = COUNTER_AT + SLOT_BYTES
# `subq.w #1,<counter>.l / seq d0 / ext.w d0 / rts`: D0.w = -1 (abort) on the call that takes the counter to
# 0, 0 on every other.
ABORT_ANSWER = 0xFFFF
CARRY_ON_ANSWER = 0

HOOK = isr.REGISTERS_HOOK
ANSWER = isr.STAGED_REGISTERS.index("d0")


def _countdown(buf, registers):
    """The stub's effect, over the candidate's image: its D0.w answer, in the register file handed back."""
    left = (buf[COUNTER_AT] << 8 | buf[COUNTER_AT + 1]) - 1 & 0xFFFF
    buf[COUNTER_AT], buf[COUNTER_AT + 1] = left >> 8, left & 0xFF
    registers[ANSWER] = ABORT_ANSWER if left == 0 else CARRY_ON_ANSWER


COUNTDOWN_CODE = struct.pack(">HIHH", SUBQ_W_1_ABSOLUTE_LONG, COUNTER_AT, SEQ_D0, EXT_W_D0) + RTS
FRAME_CALLER_AT = STUB_AT + SLOT_BYTES
assert STUB_AT + len(COUNTDOWN_CODE) <= FRAME_CALLER_AT


def countdown_pokes(calls):
    """SEEDABORT at the countdown stub, which aborts on its `calls`th call."""
    return merge_pokes({STUB_AT: COUNTDOWN_CODE, COUNTER_AT: calls.to_bytes(WORD_BYTES, "big")},
                       vdi.linea_pokes(SEEDABORT=STUB_AT))


def default_seedabort_pokes():
    """SEEDABORT at the ROM's `moveq #0,d0 / rts`, as v_contourfill leaves it."""
    return vdi.linea_pokes(SEEDABORT=addrs.LINEA_ROM_SEEDABORT_DEFAULT)


def hooked_run(entry, pokes, glue, **kwargs):
    """`case.run` with the countdown stub bound for the candidate, keyed by its address: a call through
    SEEDABORT to anything else is refused, and so is one made outside the run."""
    with HOOK.staged_routines({STUB_AT: (COUNTDOWN_CODE, _countdown)}):
        return case.run(entry, {"_pokes": pokes}, HOOK.recording(glue), **kwargs)


def contour_core():
    core = getattr(_lib, routines.core_symbol("LINEA_ROM_CONTOUR_FILL"))
    core.restype = None
    return core


def run_contour(pokes, **kwargs):
    """$a00f entered by `jsr` over `pokes` — a Line-A primitive with no register contract."""
    core = contour_core()
    info = hooked_run(addrs.LINEA_ROM_CONTOUR_FILL, pokes, lambda _lib_, buf: core(buf), width=case.NO_RESULT,
                      **kwargs)
    return vdi.Result(info, pokes)


# ---- the TRANSCRIPTIONS' caller (`src/vdi/fill.S`) ---------------------------------------------------
# `test/vdi_helpers.py`'s frame caller, one longword wider: end_pts takes TWELVE bytes of Alcyon frame (two
# words, two addresses) where every pure helper takes eight. The frame is staged ABOVE the routine longword
# `transcription.run_transcription` plants at `abi.FIRST_ARG`, and the caller pushes it — three longwords, each now
# as far up as the last — calls through that longword, and drops the frame: a `jsr` with the ROM's frame.
FRAME_LONGWORDS = 3
FRAME_ARGUMENTS_AT = abi.FIRST_ARG + LONG_BYTES
_FROM_ENTRY_SP = 16        # the last argument longword, from the caller's entry SP: sentinel, routine, two more
_TO_RETURN = 8             # `pea` to the `lea` after the `rts`, from the `pea`'s own extension word
_TO_ROUTINE = 20           # the routine longword once the three arguments and the return are pushed
FRAME_CALLER_STUB = (FRAME_LONGWORDS * (PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP))
                     + PUSH_RETURN_PC + struct.pack(">h", _TO_RETURN)
                     + PUSH_STACK_LONG + struct.pack(">h", _TO_ROUTINE)
                     + RTS
                     + DROP_STACK_BYTES + struct.pack(">h", FRAME_LONGWORDS * LONG_BYTES)
                     + RTS)
assert FRAME_CALLER_AT + len(FRAME_CALLER_STUB) <= BAND_AT + BAND_BYTES
FRAME_CALLER = transcription.staged_caller(FRAME_CALLER_AT, FRAME_CALLER_STUB, (8, 152))


def transcription_frame_pokes(name, arguments):
    """`name`'s Alcyon frame where the frame caller reads it, above the routine longword."""
    return {FRAME_ARGUMENTS_AT: frame(name, *arguments)[abi.FIRST_ARG]}


def run_transcription(name, pokes, arguments=None):
    """`fill.S`'s `name` against the ROM routine over `pokes`: a Line-A primitive through `transcription`'s plain
    caller, an Alcyon routine through the frame caller with `arguments` staged."""
    if arguments is None:
        return transcription.run_transcription(name, pokes)
    return transcription.run_transcription(name, merge_pokes(pokes, transcription_frame_pokes(name, arguments)),
                                           caller=FRAME_CALLER)


def register_transcription(label, name, pokes, arguments=None):
    """...and the same as a Tier 3 row."""
    if arguments is None:
        return transcription.register_transcription(name, label, pokes)
    return transcription.register_transcription(name, label, merge_pokes(pokes, transcription_frame_pokes(name, arguments)),
                                                caller=FRAME_CALLER)


# ---- the fill attributes, as the dispatcher leaves them ------------------------------------------------
# The captured desktop's clip (the menu bar excluded) and a tight one; the fill pattern is PATPTR/PATMSK.
DESKTOP_CLIP = (0, 11, 319, 199)
WHOLE_SCREEN_CLIP = (0, 0, vdi.SCREEN.width - 1, vdi.SCREEN.height - 1)


def clip_values(clip):
    if clip is None:
        return {"CLIP": 0}
    xmin, ymin, xmax, ymax = clip
    return {"CLIP": 1, "XMN_CLIP": xmin, "YMN_CLIP": ymin, "XMX_CLIP": xmax, "YMX_CLIP": ymax}


def fill_workstation(*, colour, mode="replace", pattern="solid", clip=DESKTOP_CLIP, perimeter=0, onto=None,
                     **values):
    """The physical workstation, dispatched, with a fill colour, write mode, pattern, clip and perimeter
    — every field the fill routines read through the record or the dispatcher's copies."""
    patptr, patmsk = vdi_raster.PATTERNS[pattern]
    fields = {"FILL_COLOR": colour, "WRT_MODE": vdi_raster.MODES[mode], "PATPTR": patptr, "PATMSK": patmsk,
              "FILL_PER": perimeter, **clip_values(clip)}
    return vdi.dispatched_pokes(onto=onto, **{**fields, **values})


def points_pokes(points, at=vdi.VDI_PTSIN_COPY, count=None):
    """`points` [(x, y), ...] at `at` as PTSIN, with contrl[1] = `count` (the number of points by default)."""
    flat = [coordinate for point in points for coordinate in point]
    contrl = vdi.contrl(0, len(points) if count is None else count)
    return merge_pokes({at: vdi.pack_words(*flat), vdi.CONTRL_AT: contrl},
                       vdi.pointer_pokes(ptsin=at))
