"""What the VDI's PURE-HELPER batteries share (`src/vdi/helpers.c`): the Alcyon call door and a band.

AN ALCYON C CALL is what most of these helpers are: the caller pushes WORD arguments (an Alcyon `int`
is 16 bits) and reads the answer out of D0's LOW WORD — every call site moves D0.w on, and none reads
the high word (`vdi/helpers.h`). So `run_call` stages the words where `jsr` leaves them for the ROM
(`case.word_args`), calls the C core with the same values as C arguments, and compares D0 at
`WORD_RESULT` bits. The THREE REGISTER ROUTINES (`sort_words`, `clamp_mouse`, `get_kbshift`) go through
`vdi.declare_primitive` / `vdi.run_primitive` instead, which is the one register map `bench/tier3.py`
reads too.

`bench/tier3.py` DERIVES its `CALL` entries for the Alcyon calls from the signatures below (`vdi.ALCYON`),
decoding each argument out of the same frame at the offset the widths before it add up to — so the two
halves of the one fact are stated once.
"""
import ctypes
import struct
import subprocess
import sys
from pathlib import Path

from harness import BASE_IMAGE, LIB, _lib, addrs

import abi
import case
import vdi
from vdi import IMAGE_ARG, LONG_ARG, LONG_BYTES, WORD_ARG, WORD_BYTES, WORD_RESULT
from opcodes import DROP_STACK_BYTES, LOAD_IMMEDIATE, PUSH_RETURN_PC, PUSH_STACK_LONG, RTE, RTS

# `vdi/helpers.h`'s own constants — the scaler's markers — parsed as `test/vdi.py` parses its headers.
CONSTANTS = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "helpers.h",
                        known={**addrs.ADDRS, **vdi.CONSTANTS})
sys.modules[__name__].__dict__.update(CONSTANTS)

# The C signature of every ALCYON core `src/vdi/helpers.c` reconstructs, declared through `vdi.declare_alcyon`
# (the one registry `bench/tier3.py` and the shipped build's glue read). The words are declared SIGNED where
# the C is `int16_t` — Apple's arm64 ABI leaves a caller to extend a short argument, so a value passed
# without its declared type would reach the core as the wrong word.
for _name, _restype, _argtypes in (
        ("VDI_ROM_VEC_LEN", ctypes.c_uint16, (WORD_ARG, WORD_ARG)),
        ("VDI_ROM_SMUL_DIV", ctypes.c_uint16, (WORD_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_ISIN", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_ICOS", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_CLIP_CODE", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_CLC_NSTEPS", None, (IMAGE_ARG,)),
        ("VDI_ROM_QUAD_XFORM", None, (IMAGE_ARG, WORD_ARG, WORD_ARG, WORD_ARG, LONG_ARG, LONG_ARG)),
        ("VDI_ROM_CLC_DDA", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_ACT_SIZ", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_COPY_NAME", None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
        ("VDI_ROM_FONT_BYTESWAP", None, (IMAGE_ARG,)),
        ("VDI_ROM_S_FA_ATTR", None, (IMAGE_ARG,)),
        ("VDI_ROM_R_FA_ATTR", None, (IMAGE_ARG,))):
    vdi.declare_alcyon(_name, _restype, _argtypes)

# ...and the host signatures of the cores that are NOT Alcyon calls: the three REGISTER ROUTINES, whose
# contracts are declared below and held to these by `test_tier3.py`, and `gemdos_call`, whose C takes the
# return site its Alcyon frame cannot carry.
REGISTER_SIGNATURES = {
    "vdi_sort_words": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "vdi_clamp_mouse": (LONG_ARG, (IMAGE_ARG, LONG_ARG, LONG_ARG, ctypes.POINTER(LONG_ARG))),
    "vdi_get_kbshift": (LONG_ARG, (IMAGE_ARG, LONG_ARG)),
    "vdi_gemdos_call": (LONG_ARG, (IMAGE_ARG, LONG_ARG, ctypes.c_uint16, LONG_ARG)),
}
for _symbol, (_restype, _argtypes) in REGISTER_SIGNATURES.items():
    getattr(_lib, _symbol).restype = _restype
    getattr(_lib, _symbol).argtypes = list(_argtypes)

# THE REGISTER ROUTINES' CONTRACTS, declared in this SHARED module rather than in the battery that runs
# each, so `bench/tier3.py` — which builds its calls from `vdi.PRIMITIVES` — sees them whichever battery
# was imported first.
vdi.declare_primitive("VDI_ROM_SORT_WORDS", arguments=("d0", "a0"))
vdi.declare_primitive("VDI_ROM_CLAMP_MOUSE", arguments=("d0", "d1"), results=("d0", "d1"))
vdi.declare_primitive("VDI_ROM_GET_KBSHIFT", arguments=("d0",), results=("d0",))
# ...and the one core with no Tier 3 C row: `vdi_gemdos_call`'s cases are registered UNPRICED
# (`test_vdi_helpers_gemdos.py` says why).
UNPRICED_CORES = ("vdi_gemdos_call",)


def core(name):
    """The C core of `addrs.<name>`: `VDI_ROM_SMUL_DIV` -> `vdi_smul_div` (`vdi.core_symbol`, which is how
    `bench/tier3.py` derives the symbol too)."""
    return getattr(_lib, vdi.core_symbol(name))


def uses_image(name):
    """Whether the core's first argument is the image (every one but the two pure arithmetic ones)."""
    return vdi.ALCYON[name].argtypes[:1] == (IMAGE_ARG,)


def run_call(name, frame, arguments=(), pokes=None, **kwargs):
    """The Alcyon helper `addrs.<name>`, entered by `jsr` with the argument `frame` (`case.args`-style
    pokes at `abi.FIRST_ARG`) over `pokes`, against its core called with `arguments` — the same values
    as C arguments. Answers a `vdi.Result`; `kwargs` are `case.run`'s."""
    function = core(name)
    returns = vdi.ALCYON[name].restype
    staged = vdi.merge_pokes(pokes, frame)

    def glue(_lib_, buf):
        return function(buf, *arguments) if uses_image(name) else function(*arguments)

    info = case.run(getattr(addrs, name), {"_pokes": staged}, glue,
                    width=WORD_RESULT if returns is not None else case.NO_RESULT, **kwargs)
    return vdi.Result(info, staged)


def answer(result):
    """The word a helper answered, as the signed Alcyon `int` its caller reads."""
    return struct.unpack(">h", struct.pack(">H", result.info["regs"]["d0"] & 0xFFFF))[0]


IMAGE_BYTES = len(BASE_IMAGE)


def refusal(symbol, argtypes, arguments):
    """What the host core `symbol` says when called with `arguments` in a CHILD process, where its
    refusal — `recreate_not_reconstructed`, an `abort()` — can end the run without ending pytest's.
    `arguments` is Python source; `buf` names a fresh image. Answers `(returncode, stderr)`."""
    probe = (f"import ctypes; lib = ctypes.CDLL({str(LIB)!r}); buf = (ctypes.c_uint8 * {IMAGE_BYTES})(); "
             f"lib.{symbol}.argtypes = [{', '.join(argtypes)}]; lib.{symbol}({arguments})")
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60)
    return run.returncode, run.stderr



# ---- the band these batteries stage buffers in ----------------------------------------------------
# A kilobyte at +$1000 of the VDI's window: above the bands `test/vdi.py` lays from its base, below
# `test/vdi_raster.py`'s at +$1800 — `vdi.SPAN` refuses an overlap either way — and laid out as below.
BAND_OFFSET = 0x1000
BAND_BYTES = 0x400
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_helpers.py: words, names and forms")
SORT_AT = BAND_AT                               # sort_words' array, 16 words
ANSWERS_AT = BAND_AT + 0x20                     # quad_xform's two answer words
NAME_AT = BAND_AT + 0x40                        # a font name and room to copy it to, 0x80
FONT_FORM_AT = BAND_AT + 0xC0                   # a font form to byte-swap, 0x40
FRAME_CALLER_AT = BAND_AT + 0x100               # the Alcyon transcriptions' staged caller (below)
TRAP_HANDLER_AT = BAND_AT + 0x120               # ...and gemdos_call's staged `trap #1` handler
TRAP_LEDGER_AT = BAND_AT + 0x140                # ...and the words it records
RASTER_FORM_BYTES = 0x100
SOURCE_FORM_AT = BAND_AT + 0x200                # vr_trnfm's two raster forms
DESTINATION_FORM_AT = SOURCE_FORM_AT + RASTER_FORM_BYTES


# ---- the TRANSCRIPTIONS (`src/vdi/helpers.S`) ------------------------------------------------------
# `vdi.run_transcription` enters both sides at a staged caller that jumps through the routine longword
# at `abi.FIRST_ARG` with the sentinel under it — which is a register routine's `jsr`, but leaves an
# ALCYON routine reading the routine's own address where its first argument should be. So the Alcyon
# helpers get a caller of their own: the argument words are staged ABOVE that longword
# (`FRAME_ARGUMENTS_AT`) and the caller pushes two longwords of them, calls, and drops them — a `jsr`
# with an eight-byte frame, which is every one of these routines' (three words at most). It touches no
# register, and what it costs comes off both columns.
FRAME_ARGUMENTS_AT = abi.FIRST_ARG + LONG_BYTES
FRAME_ARGUMENT_BYTES = 2 * LONG_BYTES
_FROM_ENTRY_SP = 12        # the second argument longword, from the caller's entry SP: sentinel, routine, first
_TO_RETURN = 8             # `pea` to the `lea` after the `rts`, from the `pea`'s own extension word
_TO_ROUTINE = 16           # the routine longword once the two arguments and the return are pushed
FRAME_CALLER_STUB = (PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP)      # the second longword
                     + PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP)    # ...then the first, now as far up
                     + PUSH_RETURN_PC + struct.pack(">h", _TO_RETURN)
                     + PUSH_STACK_LONG + struct.pack(">h", _TO_ROUTINE)
                     + RTS                                                   # into the routine
                     + DROP_STACK_BYTES + struct.pack(">h", FRAME_ARGUMENT_BYTES)
                     + RTS)
FRAME_CALLER = vdi.staged_caller(FRAME_CALLER_AT, FRAME_CALLER_STUB, (7, 128))


def frame_pokes(frame):
    """A `case.args`-style frame (at `abi.FIRST_ARG`) moved up to where the frame caller reads it."""
    (at, data), = frame.items()
    assert at == abi.FIRST_ARG and len(data) <= FRAME_ARGUMENT_BYTES
    return {FRAME_ARGUMENTS_AT: data}


def _entered(pokes, frame):
    """The caller a transcription goes through — the frame caller for an Alcyon `frame`, `vdi`'s own
    otherwise — and the pokes with that frame where it reads it."""
    if frame is None:
        return vdi.PLAIN_CALLER, pokes
    return FRAME_CALLER, vdi.merge_pokes(pokes, frame_pokes(frame))


def run_transcription(name, pokes, regs=None, frame=None, **kwargs):
    """`vdi.run_transcription`, entered through the frame caller when the routine takes an Alcyon `frame`."""
    caller, staged = _entered(pokes, frame)
    return vdi.run_transcription(name, staged, regs, caller=caller, **kwargs)


def register_transcription(name, label, pokes, regs=None, frame=None):
    """...and the same as a Tier 3 row."""
    caller, staged = _entered(pokes, frame)
    return vdi.register_transcription(name, label, staged, regs, caller=caller)


# ---- a RECORDING TRAP HANDLER, for the one transcription that takes a trap ---------------------------
# gemdos_call's `.S` cannot be compared with the ROM through the real GEMDOS (`test_vdi_helpers_gemdos.py`
# says why), so its rows point the trap's RAM vector at this instead: it copies the caller's function
# word and longword out of the exception frame into `TRAP_LEDGER_AT`, answers `TRAP_ANSWER` in D0 and
# returns — the same on both sides.
MOVE_L_STACK_TO_ABSOLUTE = b"\x23\xef"      # move.l  <d16>(sp),<xxx>.l
MOVE_W_STACK_TO_ABSOLUTE = b"\x33\xef"      # move.w  <d16>(sp),<xxx>.l
EXCEPTION_FRAME_BYTES = 6                   # the 68000's SR and PC, above the caller's words
TRAP_ANSWER = 0x0001_2340
TRAP_LEDGER_BYTES = WORD_BYTES + LONG_BYTES
TRAP_HANDLER_STUB = (MOVE_L_STACK_TO_ABSOLUTE + struct.pack(">hI", EXCEPTION_FRAME_BYTES, TRAP_LEDGER_AT)
                     + MOVE_W_STACK_TO_ABSOLUTE + struct.pack(">hI", EXCEPTION_FRAME_BYTES + LONG_BYTES,
                                                               TRAP_LEDGER_AT + LONG_BYTES)
                     + LOAD_IMMEDIATE["d0"] + struct.pack(">I", TRAP_ANSWER)
                     + RTE)


def recording_trap_pokes(vector):
    """`vector` pointed at the recording handler, which is staged with its ledger FILLed."""
    return {vector: struct.pack(">I", TRAP_HANDLER_AT), TRAP_HANDLER_AT: TRAP_HANDLER_STUB,
            TRAP_LEDGER_AT: bytes([vdi.FILL]) * TRAP_LEDGER_BYTES}
