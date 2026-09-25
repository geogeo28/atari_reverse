"""XBIOS Supexec (function 38) @ $fc097e — run the caller's routine in supervisor mode.

    movea.l 4(sp),a0
    jmp     (a0)

Two instructions, because by the time the trap dispatcher has reached here the processor already IS
supervisor — the trap put it there. So Supexec adds NOTHING: no register saved, no frame built, and
a `jmp` rather than a `jsr`, so the routine returns straight past Supexec to the caller and its D0
is the XBIOS call's result.

THE ARGUMENT IS AN ADDRESS, and the core's signature is `(image, routine_address)` for that reason.
On target the body is the tail jump itself; off target the routine is 68000 code the candidate
cannot execute, so the core transfers control through `recreate_call_routine`, a hook this file
binds. Each case therefore stages a PAIR: the 68000 stub the ORACLE jumps to, and a Python function
with the same effect on the image for the candidate to reach. The hook is keyed BY ADDRESS, which is
what makes the decoy case mean something on the candidate's side as well as on the oracle's.

WHICH CLAIMS ARE ORACLE-ONLY, stated plainly because the shape of this file hides it:

* that the stub's D0 and its writes pass through untouched IS a differential claim — both sides run
  their half of the same routine and the images and results are compared;
* that the ROUTINE THE CALL NAMES is the one that runs is likewise a differential claim, now that
  the hook dispatches on the address: a candidate with a baked-in address reaches the decoy;
* but THE STACK FRAME ITSELF — that the routine sees the caller's own (sp) with nothing pushed over
  it — is the ORACLE's claim alone. The host hook has no 68000 stack to inspect, so
  `test_the_routine_sees_the_caller_s_own_stack_with_nothing_pushed_over_it` says what the ORIGINAL
  does and nothing about the reconstruction. What carries it on the reconstruction's side is the
  TARGET build, whose body is the `jmp` and not a call; Tier 3's second differential is what will
  pin that (`../README.md`, "How a row is made") once Supexec has a bench row.

Each stub is assembled here as bytes with its instructions spelt out, so the 68000 half and the
Python half are visibly the same routine.
"""
import ctypes
import struct

import pytest

from harness import _lib, addrs, emu

import abi
import case
import staging
from address_hook import AddressHook

_lib.xbios_supexec.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.xbios_supexec.restype = ctypes.c_uint32

STUB_AT = staging.SCRATCH
MARKER_AT = staging.SCRATCH + 0x100
# Where the NAMED stub goes when a case plants a decoy at the default address — far enough above
# `STUB_AT` that the two are unmistakably different routines. Module-level rather than spelt inside
# the parametrize because the other tenants of the staging band have to be able to say they are
# CLEAR of these: `test/isr.py` asserts its own band starts past the last of them.
DECOY_ALTERNATIVES = (0x800, 0xA00, 0xC00)
MARKER = 0x5A
A_RESULT = 0x1234_5678

RTS = b"\x4e\x75"

# The candidate's half of the tail jump: `uint32_t (*)(uint8_t *image, uint32_t routine_address)`.
CALL_ROUTINE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32)

# Keyed by routine address — the decoy is staged alongside the named stub and the hook has to tell
# them apart — and an effect `effect(buf)` returns the routine's D0.
HOOK = AddressHook("recreate_call_routine", CALL_ROUTINE)


def move_byte_immediate(value, address):
    """`move.b #value,(address).l` — 0x13fc, the immediate as a word, then the long address."""
    return struct.pack(">HHI", 0x13FC, value, address)


def move_long_immediate_to_d0(value):
    """`move.l #value,d0` — 0x203c and the longword."""
    return struct.pack(">HI", 0x203C, value)


# ...and how far past the last of `DECOY_ALTERNATIVES` this battery's staging reaches, which is what
# a neighbouring tenant of the band asserts it is clear of. Derived from the stub itself, so a
# longer decoy moves the bound rather than silently overrunning it.
DECOY_STUB_BYTES = len(move_long_immediate_to_d0(0) + RTS)


def read_long_from_stack_into_d0():
    """`move.l (sp),d0` — 0x2017. The sentinel return address, if nothing was pushed over it."""
    return b"\x20\x17"


def run(stubs, named=STUB_AT, poison=True, entry_d0=0):
    """One differential over `stubs` — {address: (68000 bytes, the same effect in Python)}.

    `named` is the address the call's 4(sp) argument points at; every stub in the map is planted in
    the image and bound to the hook, so a stub the call does NOT name is a decoy on both sides.
    """
    def glue(lib, buf):
        return lib.xbios_supexec(buf, named)

    pokes = {abi.FIRST_ARG: struct.pack(">I", named),
             **{at: code for at, (code, _effect) in stubs.items()}}
    with HOOK.staged_routines(stubs):
        return case.run(addrs.XBIOS_SUPEXEC, {"a5": 0, "d0": entry_d0, "_pokes": pokes},
                        HOOK.recording(glue), poison=poison)


def test_a_bare_rts_passes_the_caller_s_d0_straight_back():
    """Supexec pushes nothing, so a routine that does nothing returns to the CALLER, not to Supexec,
    and D0 is untouched all the way through. A reconstruction that wrapped the call in a frame — or
    that set a result of its own — differs here and nowhere else."""
    info = run({STUB_AT: (RTS, lambda buf: 0xBEEF_0000)}, entry_d0=0xBEEF_0000)
    assert info["regs"]["d0"] == 0xBEEF_0000
    assert not info["writes"], "Supexec wrote to memory on a routine that did nothing"


@pytest.mark.parametrize("value", (0, 1, A_RESULT, 0xFFFF_FFFF, 0x8000_0000))
def test_the_routine_s_d0_is_the_call_s_result(value):
    stub = (move_long_immediate_to_d0(value) + RTS, lambda buf: value)
    assert run({STUB_AT: stub})["regs"]["d0"] == value


def test_the_routine_s_writes_are_the_call_s_writes():
    """The image effect passes through as well as the register one — Supexec neither saves nor
    restores anything around it."""
    def effect(buf):
        buf[MARKER_AT] = MARKER
        return A_RESULT

    code = move_byte_immediate(MARKER, MARKER_AT) + move_long_immediate_to_d0(A_RESULT) + RTS
    info = run({STUB_AT: (code, effect)})
    assert info["writes"][MARKER_AT] == MARKER
    assert info["regs"]["d0"] == A_RESULT


def test_the_routine_sees_the_caller_s_own_stack_with_nothing_pushed_over_it():
    """THE CLAIM THAT `jmp` RATHER THAN `jsr` MAKES, and the ORACLE's alone (see the module
    docstring). The stub reads the longword at (sp) and finds the harness's sentinel return address
    — the one `emu.run` planted for Supexec itself. A `jsr` would have put Supexec's own return
    address there instead. The host hook has no 68000 stack to look at, so it simply reports the
    same value; what holds the reconstruction to it is the target build's `jmp`."""
    stub = (read_long_from_stack_into_d0() + RTS, lambda buf: emu.SENTINEL)
    assert run({STUB_AT: stub})["regs"]["d0"] == emu.SENTINEL


@pytest.mark.parametrize("offset", DECOY_ALTERNATIVES)
def test_the_routine_run_is_the_one_4_sp_names_and_not_another(offset):
    """The staged stub is an INPUT, and a DECOY is planted at the default address on every case —
    for BOTH sides now, since the hook dispatches on the address the core passes it. A
    reconstruction, or an oracle entry, that jumped to a baked-in address would return the decoy's
    2 rather than the named stub's 1."""
    named = STUB_AT + offset
    stubs = {STUB_AT: (move_long_immediate_to_d0(2) + RTS, lambda buf: 2),
             named: (move_long_immediate_to_d0(1) + RTS, lambda buf: 1)}
    assert run(stubs, named=named)["regs"]["d0"] == 1
