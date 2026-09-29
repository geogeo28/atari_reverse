"""What the screen-plumbing batteries share (`src/vdi/screen.c`): the contracts, a band of the VDI window, the
etv_timer routines a tick case stages, and the machine a trap-taking case declares.

THE CONTRACTS are declared here, once. The BIOS's span clear is an Alcyon call (two longwords), v_clrwk a VDI
function (opcode 3, `addrs.h`); setres answers D0; init_timer_mouse and restore_timer_mouse take and answer
nothing in a register. timer_tick is an ALCYON-shaped call — timer C pushes `_timr_ms` as a WORD in front of its
`jsr` — so it is declared through `vdi.declare_alcyon` and its case stages that word where a frame argument goes.

THE TIMER VECTORS. timer_tick calls USER_TIM and chains to NEXT_TIM, which in the captured machine point into
the AES and at GEMDOS's own tick ($fc4ef6). So a tick case repoints both at routines it stages here — a 68000 stub
for the ORACLE and the same effect in Python for the CANDIDATE, which reaches it through `staged_call.h`'s hook
(`isr.staged_routines`), keyed by address. Every USER_TIM stub CLOBBERS D0-D7/A0-A5 (all a staged routine may,
`staged_call.h`), so the ROM's `movem` bracket round it is what gives the registers back. The chained NEXT_TIM
touches none in a C case — the C calls it and comes back, where the ROM chains, and Tier 3 holds the C to the
ROM's callee-saved file — and clobbers the vector set D2-D7/A2-A5 in a TRANSCRIPTION case, where the `.S` chains
as the ROM does and what the handler changed must reach the caller on both sides.

THE TICK'S TRANSCRIPTION is entered as timer C enters etv_timer: ONE word pushed under the return address
(`WORD_CALLER`), where every other Alcyon caller here pushes longwords.

THE TRAPS. setres takes three XBIOS calls and the two timer routines BIOS Setexc (and, through mouse_init and
mouse_off, XBIOS Initmous), each through the ROM's own `trap` on the oracle, so `savptr` is declared in the
dropped stack band (`gemdos.machine`) and those cases do not poison — the attribution pass would invert `savptr`
itself (`test_vdi_attr_vectors.py`'s arrangement). Every store such a case is about is made over a FILLed byte
instead, so a skipped store still reads as a difference.
"""
import struct
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu

import abi
import case
import gemdos
import isr
import vdi
import vdi_mouse
from case import merge_pokes
from opcodes import DROP_STACK_BYTES, MOVEM_L_ABSOLUTE_TO_REGISTERS, PUSH_RETURN_PC, PUSH_STACK_LONG, PUSH_STACK_WORD, RTS

SCREEN_H = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "screen.h",
                       known={**addrs.ADDRS, **vdi.CONSTANTS})

# ---- the contracts ----------------------------------------------------------------------------------------------
REGISTER_CONTRACTS = {
    "VDI_ROM_SETRES": {"results": ("d0",)},
    "VDI_ROM_INIT_TIMER_MOUSE": {},
    "VDI_ROM_RESTORE_TIMER_MOUSE": {},
}
for _name, _contract in REGISTER_CONTRACTS.items():
    vdi.declare_primitive(_name, **_contract)
    getattr(_lib, vdi.core_symbol(_name)).argtypes = [vdi.IMAGE_ARG]
TICK = "VDI_ROM_TIMER_TICK"
vdi.declare_alcyon(TICK, None, (vdi.IMAGE_ARG, vdi.WORD_ARG))
CLEAR = "VDI_ROM_CLEAR_SPAN"
vdi.declare_alcyon(CLEAR, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG))

# ---- this module's band of the VDI window -----------------------------------------------------------------------
# Between `test/vdi_text.py`'s ($1a00) and `test/vdi_blit.py`'s ($1c00); `vdi.SPAN` refuses an overlap.
BAND_OFFSET = 0x1B00
BAND_BYTES = 0x100
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_screen.py: etv_timer stubs, their marks, a cursor cell")
STUB_BYTES = 0x20
USER_TIM_STUB_AT = BAND_AT                          # marks USER_TIM_MARK_AT
REPOINTING_STUB_AT = USER_TIM_STUB_AT + STUB_BYTES  # marks, and repoints NEXT_TIM at OTHER_NEXT_TIM_STUB_AT
NEXT_TIM_STUB_AT = REPOINTING_STUB_AT + STUB_BYTES  # records the word under its return address
OTHER_NEXT_TIM_STUB_AT = NEXT_TIM_STUB_AT + STUB_BYTES
MARKS_AT = OTHER_NEXT_TIM_STUB_AT + STUB_BYTES
USER_TIM_MARK_AT = MARKS_AT                         # a byte
NEXT_TIM_WORD_AT = MARKS_AT + 2                     # the tick word NEXT_TIM found
OTHER_NEXT_TIM_WORD_AT = MARKS_AT + 4               # ...and the one the repointed handler found
MARKS_BYTES = 8
CURSOR_CELL_AT = MARKS_AT + 0x10                    # a console cursor cell off the screen (below)
CURSOR_CELL_BYTES = 0x10
CLOBBERS_AT = CURSOR_CELL_AT + CURSOR_CELL_BYTES    # the values the stubs load into the registers they clobber
WORD_CALLER_AT = CLOBBERS_AT + 0x40                 # the tick transcription's staged caller (below)
WORD_CALLER_BYTES = 0x20
assert WORD_CALLER_AT + WORD_CALLER_BYTES <= BAND_AT + BAND_BYTES

# ---- the timer routines ------------------------------------------------------------------------------------------
WORD = struct.Struct(">H")
LONG = struct.Struct(">I")

# `movem.l CLOBBERS_AT,<list>`: the register masks (bit 0 = D0 .. bit 15 = A7). USER_TIM takes every register a
# staged routine may change (A6 is `staged_call.h`'s toolchain exception); a chained NEXT_TIM the vector set.
USER_TIM_CLOBBERS = ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "a0", "a1", "a2", "a3", "a4", "a5")
CHAIN_CLOBBERS = ("d2", "d3", "d4", "d5", "d6", "d7", "a2", "a3", "a4", "a5")
MOVEM_ORDER = ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7")
CLOBBER_VALUES = tuple(0x5C00_0000 + index * 0x0101 for index in range(len(USER_TIM_CLOBBERS)))
assert len(CLOBBER_VALUES) * LONG.size <= WORD_CALLER_AT - CLOBBERS_AT


def clobbering(registers):
    """`movem.l (CLOBBERS_AT).l,<registers>`: each loaded with a value no case enters with."""
    mask = sum(1 << MOVEM_ORDER.index(name) for name in registers)
    return MOVEM_L_ABSOLUTE_TO_REGISTERS + struct.pack(">HI", mask, CLOBBERS_AT)


def clobbered(registers):
    """{register: the value `clobbering(registers)` leaves in it} — `movem` loads them in MOVEM_ORDER."""
    ordered = [name for name in MOVEM_ORDER if name in registers]
    return dict(zip(ordered, CLOBBER_VALUES))


def marking_routine():
    """USER_TIM: its byte at USER_TIM_MARK_AT, and every register it may change changed."""
    def effect(buf, _argument):
        buf[USER_TIM_MARK_AT] = isr.MARK
    return isr.store_byte(isr.MARK, USER_TIM_MARK_AT) + clobbering(USER_TIM_CLOBBERS) + RTS, effect


def repointing_routine():
    """USER_TIM that marks AND repoints NEXT_TIM — so which handler the chain reaches says when it was read."""
    def effect(buf, _argument):
        buf[USER_TIM_MARK_AT] = isr.MARK
        isr.poke(buf, vdi.LINEA_NEXT_TIM, LONG.pack(OTHER_NEXT_TIM_STUB_AT))
    return (isr.store_byte(isr.MARK, USER_TIM_MARK_AT) + isr.store_long(OTHER_NEXT_TIM_STUB_AT, vdi.LINEA_NEXT_TIM)
            + clobbering(USER_TIM_CLOBBERS) + RTS), effect


def word_recording_routine(mark_at, chained=False):
    """A NEXT_TIM: the word under its return address stored at `mark_at` — the tick, where the chain passes it —
    and, `chained`, the vector set clobbered on the way back to whoever the chain returns to."""
    def effect(buf, argument):
        assert argument != isr.NO_ARGUMENT, "the chained handler was called with no word pushed"
        isr.poke(buf, mark_at, WORD.pack(argument & 0xFFFF))
    return isr.store_frame_word(mark_at) + (clobbering(CHAIN_CLOBBERS) if chained else b"") + RTS, effect


def nop_routine():
    """USER_TIM's default, the ROM's own `rts` at VDI_ROM_NOP: nothing planted, nothing done."""
    return b"", lambda _buf, _argument: None


def tick_routines(user_tim=USER_TIM_STUB_AT, chained=False):
    """{address: routine}: USER_TIM at `user_tim` and both chained handlers."""
    user = {USER_TIM_STUB_AT: marking_routine(), REPOINTING_STUB_AT: repointing_routine(),
            addrs.VDI_ROM_NOP: nop_routine()}[user_tim]
    routines = {user_tim: user, NEXT_TIM_STUB_AT: word_recording_routine(NEXT_TIM_WORD_AT, chained),
                OTHER_NEXT_TIM_STUB_AT: word_recording_routine(OTHER_NEXT_TIM_WORD_AT, chained)}
    assert all(len(code) <= STUB_BYTES for code, _effect in routines.values()), "a stub overruns its slot"
    return routines


def tick_stage(user_tim=USER_TIM_STUB_AT, chained=False):
    """Both vectors pointed at the staged routines, the marks FILLed, the clobber values and the routines planted."""
    return merge_pokes(vdi.linea_pokes(USER_TIM=user_tim, NEXT_TIM=NEXT_TIM_STUB_AT),
                       {MARKS_AT: bytes([vdi.FILL]) * MARKS_BYTES,
                        CLOBBERS_AT: b"".join(LONG.pack(value) for value in CLOBBER_VALUES)},
                       isr.routine_pokes(tick_routines(user_tim, chained)))


def tick_pokes(tick, user_tim=USER_TIM_STUB_AT, pokes=None):
    """A tick of `tick` ms entered at the routine: the word under the return address, and `tick_stage`."""
    return merge_pokes(tick_stage(user_tim), case.word_arg(tick), pokes)


def run_tick(tick, user_tim=USER_TIM_STUB_AT, pokes=None):
    """One differential of timer_tick, entered with `isr.DIRTY_REGISTERS` as the interrupted program left them."""
    staged = tick_pokes(tick, user_tim, pokes)
    core = _lib.vdi_timer_tick
    with isr.staged_routines(tick_routines(user_tim)):
        info = case.run(getattr(addrs, TICK), {**isr.DIRTY_REGISTERS, "_pokes": staged},
                        isr.recording(lambda _lib_, buf: core(buf, vdi.signed_word(tick & 0xFFFF))),
                        width=case.NO_RESULT)
    return vdi.Result(info, staged)


# THE TICK TRANSCRIPTION'S CALLER: timer C's `move.w _timr_ms,-(sp) / jsr` — one WORD under the return address —
# with the word staged at TICK_FRAME_AT above the routine longword, and the routine entered as `vdi`'s own caller
# enters one, through the longword at `abi.FIRST_ARG` rather than a register (A0 would hold a code address, which
# differs between the ROM and the blob). It touches no register, and what it costs comes off both columns.
#
#     move.w  TICK(sp),-(sp) / pea back(pc) / move.l ROUTINE(sp),-(sp) / rts / back: lea 2(sp),sp / rts
TICK_FRAME_AT = abi.FIRST_ARG + LONG.size
_TICK_FROM_ENTRY_SP = TICK_FRAME_AT - emu.STACK_TOP
_TO_BACK = 8                # the `pea`'s extension word to `back`: itself, the `move.l` (4) and the `rts`
_ROUTINE_FROM_PUSHED = abi.FIRST_ARG - emu.STACK_TOP + WORD.size + LONG.size     # past the word and the return
WORD_CALLER_STUB = (PUSH_STACK_WORD + WORD.pack(_TICK_FROM_ENTRY_SP)
                    + PUSH_RETURN_PC + WORD.pack(_TO_BACK)
                    + PUSH_STACK_LONG + WORD.pack(_ROUTINE_FROM_PUSHED)
                    + RTS
                    + DROP_STACK_BYTES + WORD.pack(WORD.size)
                    + RTS)
assert len(WORD_CALLER_STUB) <= WORD_CALLER_BYTES
WORD_CALLER = vdi.staged_caller(WORD_CALLER_AT, WORD_CALLER_STUB, (6, 96))


def tick_transcription_pokes(tick, user_tim=USER_TIM_STUB_AT):
    """A tick of `tick` ms for the transcription relation: the word where WORD_CALLER pushes it from, and the
    CHAINED stubs, whose clobbers must reach the caller on both sides."""
    return merge_pokes(tick_stage(user_tim, chained=True), {TICK_FRAME_AT: WORD.pack(tick & 0xFFFF)})


# ---- the machine a trap-taking case declares ---------------------------------------------------------------------
def trap_pokes(pokes=None):
    """`savptr` in the dropped band for the ROM's own traps, and `colorptr` FILLed so Setpalette's store shows."""
    return merge_pokes(gemdos.machine(), {addrs.SYSVAR_COLORPTR: bytes([vdi.FILL]) * 4}, pokes)


def io_shifter(mode_byte):
    """The shifter's resolution byte, declared — the one I/O read setres makes (through Getrez)."""
    return {addrs.SHIFTER_RESOLUTION: mode_byte}


# ---- the screen, and the RAM past it an unaligned clear reaches --------------------------------------------------
SCREEN_BYTES = SCREEN_H["VDI_SCREEN_BYTES"]
SCREEN_BASE = case.long_in(BASE_IMAGE, addrs.SYSVAR_V_BAS_AD)
PAST_SCREEN_BYTES = 0x100
vdi.declare_case_field(SCREEN_BASE + SCREEN_BYTES, PAST_SCREEN_BYTES,
                       "the RAM past the screen a v_clrwk from an unaligned _v_bas_ad clears")
# A byte every screen byte is staged as, so the clear writes every one of them; not 0 and not what the
# poison pass would turn another fill into.
SCREEN_FILL = 0xA7


def filled_screen(base=SCREEN_BASE, extra=PAST_SCREEN_BYTES):
    """The whole screen at `base`, and `extra` bytes past it, FILLed."""
    return {base: bytes([SCREEN_FILL]) * (SCREEN_BYTES + extra)}


# ---- the timer and the mouse's world, as a workstation's open and close find it ------------------------------------
SNAPSHOT_NEXT_TIM = vdi.linea(BASE_IMAGE, "NEXT_TIM")     # GEMDOS's own tick, which v_opnwk displaced
CURSOR_DRAWN = 1 << addrs.CON_FLAG_DRAWN
# The console's cursor lock is called with a cursor CELL of one row placed in this module's band, so the
# hide's inversion lands where the clear that follows cannot erase it (four bytes, one a plane, two apart).
CELL = {addrs.CON_CELL_HEIGHT: struct.pack(">H", 1), addrs.CON_CURSOR_ADDRESS: struct.pack(">I", CURSOR_CELL_AT),
        CURSOR_CELL_AT: bytes(range(0x30, 0x30 + CURSOR_CELL_BYTES))}


def cursor(depth, flags):
    return {addrs.CON_CURSOR_DISABLE: struct.pack(">H", depth), addrs.CON_STATE_FLAGS: bytes([flags])}


def restore_pokes(next_tim=SNAPSHOT_NEXT_TIM, depth=2, flags=1):
    """The workstation closing: the tick installed, NEXT_TIM what it displaced, the mouse's VBL slot taken, and the
    console's cursor where the snapshot has it — ON the screen, so the cursor drawn after the clear shows."""
    return trap_pokes(merge_pokes(
        filled_screen(), cursor(depth, flags), vdi.linea_pokes(NEXT_TIM=next_tim),
        {addrs.SYSVAR_ETV_TIMER: struct.pack(">I", addrs.VDI_ROM_TIMER_TICK),
         vdi_mouse.VBL_QUEUE: struct.pack(">I", addrs.VDI_ROM_VBL_DRAW_CURSOR)}))

