"""The SCREEN AND WORKSTATION PLUMBING (`src/vdi/screen.c`).

    $fca654 v_clrwk (3)          jsr $fc4b7c(_v_bas_ad, _v_bas_ad + 32000)
    $fca6d4 setres               Getrez; mono -> Setpalette($fca762), 3; else intin[0]: 1 keeps the mode,
                                 3 asks medium, anything else low; Setscreen(-1, -1, mode) if it differs;
                                 Setpalette($fca762 medium / $fca76a low); 2 / 1
    $fca670 init_timer_mouse     USER_TIM = $fca652; masked: NEXT_TIM = Setexc($100, $fca78a); mouse_init;
                                 the console cursor locked; bra v_clrwk
    $fca78a timer_tick           movem.l d0-a6; jsr (USER_TIM); movem.l back; move.l NEXT_TIM,-(sp) / rts
    $fca7a2 restore_timer_mouse  Setexc($100, NEXT_TIM); mouse_off; v_clrwk; bra $fc45be (the cursor on)

THE CLEAR is the BIOS's span clear, whose three steps — the odd first byte, 256-byte blocks, the byte tail —
an even `_v_bas_ad` reaches one of (32000 is 125 blocks exactly) and an odd one all three.

SETRES' TWO SWITCHING ARMS HALT, inside XBIOS Setscreen (`src/xbios/setscreen.c`: its resolution arm is the
console re-initialisation, not reconstructed). They are pinned as halts, in a child process over a SHARED image,
with the shifter byte declared: the MODE asked for (the halt names it; the ROM, stopped at the same arm, has it
on its stack) and that nothing — Setpalette's `colorptr` above all — was stored before the switch. Every arm that
keeps the mode it finds is a differential.

THE TICK is entered as timer C enters it, the tick word under its return address and the interrupted program's
registers dirty; `isr.assert_registers_survived` holds the ORIGINAL to its `movem` bracket (USER_TIM clobbers
every register it may, NEXT_TIM none). It SHIPS as the ROM's own 24 bytes (`screen.S`: etv_timer holds its
address), pinned byte for byte and through the transcription relation with a CHAINED NEXT_TIM that clobbers the
vector set — which the chain hands the caller on both sides.

THE INIT'S INTERRUPT MASK has no image to show in (the kit's host `os_ipl_raise` is a no-op, and both builds are
entered at IPL 7), so it is pinned on the SHIPPED build's own instructions.
"""
import re
import signal
import struct
import subprocess

import pytest

from harness import BASE_IMAGE, addrs, emu

import case
import isr
import transcription
import vdi
import vdi_helpers
import vdi_mouse
import vdi_screen as screen
from vdi_screen import CELL, CURSOR_DRAWN, SNAPSHOT_NEXT_TIM, cursor, restore_pokes
from case import merge_pokes
from opcodes import RTS

CLRWK = "VDI_ROM_V_CLRWK"
SETRES = "VDI_ROM_SETRES"
INIT = "VDI_ROM_INIT_TIMER_MOUSE"
RESTORE = "VDI_ROM_RESTORE_TIMER_MOUSE"
H = screen.SCREEN_H
BASE = screen.SCREEN_BASE
LOW, MEDIUM = H["VDI_PALETTE_LOW"], H["VDI_PALETTE_MEDIUM"]
TOP_BYTE = 0xFF00_0000                                  # an address register's bits the 68000's bus drops


def test_the_captured_machine_is_what_the_cases_assume():
    assert BASE == vdi.SCREEN.base
    assert case.long_in(BASE_IMAGE, addrs.SYSVAR_ETV_TIMER) == addrs.VDI_ROM_TIMER_TICK
    assert H["VDI_TIMER_VECTOR"] * addrs.VECTOR_BYTES == addrs.SYSVAR_ETV_TIMER


def test_the_two_palettes_are_one_table_read_at_two_starts():
    medium = [vdi.rom_word(MEDIUM + 2 * index) for index in range(addrs.SHIFTER_PALETTE_ENTRIES)]
    low = [vdi.rom_word(LOW + 2 * index) for index in range(addrs.SHIFTER_PALETTE_ENTRIES)]
    assert medium[:4] == [0x777, 0x700, 0x070, 0x000]
    assert medium[4:] == low[:12]
    assert LOW + 2 * addrs.SHIFTER_PALETTE_ENTRIES == addrs.VDI_ROM_TIMER_TICK, "the low palette ends at the tick"


# ---- the span clear, $fc4b7c ---------------------------------------------------------------------------------------
# Its ROM extent: to the `rts` at $fc4be6, before the BIOS code that follows.
CLEAR_BYTES = 0x6C
CLEAR_REGION = transcription.pinned_region(addrs.VDI_ROM_CLEAR_SPAN, addrs.VDI_ROM_CLEAR_SPAN + CLEAR_BYTES, screen.CLEAR)
BLOCK = 0x100


# ...and the tick's: from its entry, exactly where the low palette ends, to restore_timer_mouse's.
TICK_BYTES = 0x18
TICK_REGION = transcription.pinned_region(addrs.VDI_ROM_TIMER_TICK, addrs.VDI_ROM_TIMER_TICK + TICK_BYTES, screen.TICK)
REGIONS = {"the clear": CLEAR_REGION, "the tick": TICK_REGION}


@pytest.mark.parametrize("region", REGIONS.values(), ids=REGIONS.keys())
def test_each_transcription_is_the_rom_s_bytes_exactly(region):
    transcription.assert_transcribed(region)


@pytest.mark.parametrize("region", REGIONS.values(), ids=REGIONS.keys())
def test_each_transcription_s_extent_ends_at_its_rts(region):
    rts_at = region.hi - len(RTS)
    assert bytes(BASE_IMAGE[rts_at:region.hi]) == RTS


def test_the_tick_s_region_is_the_bytes_between_the_low_palette_and_restore():
    assert TICK_REGION.lo == LOW + 2 * addrs.SHIFTER_PALETTE_ENTRIES
    assert TICK_REGION.hi == addrs.VDI_ROM_RESTORE_TIMER_MOUSE


def clear_pokes():
    return screen.filled_screen()


def clear(start, end):
    """The clear of [BASE + start, BASE + end), both shores, over a FILLed screen."""
    frame = case.long_args(BASE + start, BASE + end)
    return vdi_helpers.run_call(screen.CLEAR, frame, (BASE + start, BASE + end), clear_pokes())


# (start, end) from the screen's base: nothing; one byte even and odd; an odd byte that is the whole span;
# a tail alone (under a block); one block exactly, even and after an odd byte; a block and a tail; two blocks.
SPANS = ((0, 0), (0, 1), (1, 2), (3, 4), (0, 0xFF), (0, BLOCK), (1, BLOCK + 2), (1, BLOCK + 0x81),
         (2, 2 * BLOCK + 2), (0x10, 0x10 + 3 * BLOCK + 0x7F))


@pytest.mark.parametrize("start,end", SPANS)
def test_the_clear_zeroes_exactly_its_span(start, end):
    result = clear(start, end)
    assert result.after(BASE + start, end - start) == bytes(end - start)
    assert result.after(BASE + end, 1) == bytes([screen.SCREEN_FILL])
    if start:
        assert result.after(BASE + start - 1, 1) == bytes([screen.SCREEN_FILL])


@pytest.mark.parametrize("start,end", SPANS)
def test_the_clear_s_transcription_behaves_as_the_rom(start, end):
    vdi_helpers.run_transcription(screen.CLEAR, clear_pokes(), frame=case.long_args(BASE + start, BASE + end))


def test_a_span_ending_below_its_start_is_refused_on_the_host():
    """`to` below `from` makes a near-4 GB block count (the loader's negative room). The machine clears on until
    something faults; the host core must ABORT on its bound, before it stores past the image — a bound spelt as
    a sum wraps and lets the stores run off the end (a SIGBUS/SIGSEGV, not this)."""
    returncode, stderr = vdi_helpers.refusal("vdi_clear_span", ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_uint32"],
                                             f"buf, {BASE + BLOCK}, {BASE}")
    assert returncode == -signal.SIGABRT, (returncode, stderr)
    assert "span_bytes" in stderr, stderr


# ---- v_clrwk -----------------------------------------------------------------------------------------------------

def clrwk(base):
    pokes = merge_pokes(vdi.function_pokes(CLRWK), screen.filled_screen(),
                        {addrs.SYSVAR_V_BAS_AD: struct.pack(">I", base)})
    return vdi.run_function(CLRWK, pokes)


@pytest.mark.parametrize("offset", (0, 1, 0x81))
def test_v_clrwk_clears_32000_bytes_from_v_bas_ad(offset):
    """Even: the blocks alone. Odd: the first byte alone, 124 blocks, and a tail of 255 bytes."""
    result = clrwk(BASE + offset)
    assert result.after(BASE + offset, screen.SCREEN_BYTES) == bytes(screen.SCREEN_BYTES)
    assert result.after(BASE + offset + screen.SCREEN_BYTES, 1) == bytes([screen.SCREEN_FILL])
    if offset:
        assert result.after(BASE + offset - 1, 1) == bytes([screen.SCREEN_FILL])


def test_v_clrwk_counts_in_32_bits_and_stores_in_24():
    """A `_v_bas_ad` with its top byte set clears the screen the bus reaches: the sum and the equality test are
    whole registers, the stores drop bits 24..31."""
    result = clrwk(TOP_BYTE | BASE)
    assert result.after(BASE, screen.SCREEN_BYTES) == bytes(screen.SCREEN_BYTES)


# ---- setres ------------------------------------------------------------------------------------------------------

def setres_pokes(asked):
    """v_opnwk's intin[0] = `asked`, and the trap machine."""
    return screen.trap_pokes(vdi.function_pokes("VDI_ROM_V_OPNWK", (asked,)))


def setres(mode_byte, asked):
    return vdi.run_primitive(SETRES, {}, setres_pokes(asked), poison=False, io_seed=screen.io_shifter(mode_byte))


# (shifter byte, intin[0], answer, palette). Mono answers high whatever is asked, and the byte's six high bits
# are Getrez's to mask. A colour mode kept: 1 keeps either, 3 keeps medium, and every other word — 0, 2, GEM's
# 4 for "high", -1, and $0101/$8001, which match 1 in the low byte only — keeps low. Mode 3, which no ST shows,
# is "not low" to the keep arm.
KEPT = (
    (2, 1, 3, MEDIUM), (2, 3, 3, MEDIUM), (2, 0, 3, MEDIUM), (0xFE, 4, 3, MEDIUM),
    (0, 1, 1, LOW), (0, 0, 1, LOW), (0, 2, 1, LOW), (0, 4, 1, LOW), (0, -1, 1, LOW), (0, 0x0101, 1, LOW),
    (0, 0x8001, 1, LOW), (0, 0x0103, 1, LOW), (0xFC, 2, 1, LOW),
    (1, 1, 2, MEDIUM), (1, 3, 2, MEDIUM), (0x7D, 3, 2, MEDIUM),
    (3, 1, 2, MEDIUM),
)


@pytest.mark.parametrize("mode_byte,asked,answer,palette", KEPT)
def test_setres_answers_the_mode_kept_and_queues_its_palette(mode_byte, asked, answer, palette):
    result = setres(mode_byte, asked)
    assert result.info["regs"]["d0"] == answer
    assert result.long(addrs.SYSVAR_COLORPTR) == palette
    assert result.info["regs"]["io_events"] == [(addrs.SHIFTER_RESOLUTION, 1, mode_byte)]


# The arms that CHANGE the mode, with the mode each asks Setscreen for: medium asked in low (or in mode 3), and
# anything but 1 and 3 asked in medium (or 3) — $0101 and $0103 among them, whose LOW BYTES are 1 and 3: the two
# asks are word compares.
SWITCHING = ((0, 3, addrs.SHIFTER_MODE_MEDIUM), (3, 3, addrs.SHIFTER_MODE_MEDIUM), (1, 2, addrs.SHIFTER_MODE_LOW),
             (1, 4, addrs.SHIFTER_MODE_LOW), (1, 0, addrs.SHIFTER_MODE_LOW), (3, 0, addrs.SHIFTER_MODE_LOW),
             (1, 0x0101, addrs.SHIFTER_MODE_LOW), (1, 0x0103, addrs.SHIFTER_MODE_LOW),
             (1, 0x8001, addrs.SHIFTER_MODE_LOW))
# Where the ROM's Setscreen reads the mode at its arm (`tst.w 12(sp)`, then `move.b 13(sp),$44c`): the FIRST word
# setres pushes, straight under the sentinel it was entered over — the XBIOS dispatcher runs the routine on the
# caller's own frame, and setres saves nothing before it pushes.
SETSCREEN_MODE_AT = emu.STACK_TOP - struct.calcsize(">H")


@pytest.mark.parametrize("mode_byte,asked,mode", SWITCHING)
def test_setres_halts_inside_setscreen_asking_for_the_mode_before_it_stores_a_byte(mode_byte, asked, mode):
    """The candidate halts in Setscreen asking for `mode`, over an image it left EXACTLY as staged — so the
    switch comes before Setpalette's store, not after. The ORIGINAL, run alone to a checkpoint at the same arm,
    stops there with the same mode on its stack and D0 the routine the XBIOS dispatcher jumped through, where a
    run that returned would hold 1, 2 or 3."""
    pokes = setres_pokes(asked)
    staged = bytes(vdi.make_image(pokes))
    returncode, stderr, image = vdi_helpers.refusal_over("vdi_setres", pokes, screen.io_shifter(mode_byte))
    assert returncode != 0
    assert f"Setscreen's resolution change to {mode}:" in stderr, stderr
    assert image == staged, "setres stored before Setscreen's resolution change"
    final, _writes, left = emu.run(bytearray(staged), addrs.VDI_ROM_SETRES,
                                   stop_pc=addrs.XBIOS_SETSCREEN_RESOLUTION_ARM, io_seed=screen.io_shifter(mode_byte))
    assert left["d0"] == addrs.XBIOS_SETSCREEN, "the ROM did not stop inside Setscreen's resolution arm"
    assert bytes(final[SETSCREEN_MODE_AT:emu.STACK_TOP]) == struct.pack(">H", mode), "the ROM asked for another mode"


# ---- init_timer_mouse / restore_timer_mouse --------------------------------------------------------------------
INIT_DEPTH = 2


def init_pokes(depth=INIT_DEPTH, flags=CURSOR_DRAWN | 1, etv_timer=SNAPSHOT_NEXT_TIM):
    """The workstation opening: the call arrays mouse_init lends vsc_form, every field it and this write FILLed,
    etv_timer holding what v_opnwk finds there, and a cursor cell off the screen."""
    return screen.trap_pokes(merge_pokes(
        vdi.function_pokes("VDI_ROM_VSC_FORM"), screen.filled_screen(), CELL, cursor(depth, flags),
        vdi.linea_pokes(USER_TIM=vdi.FILL_LONG, NEXT_TIM=vdi.FILL_LONG),
        {addrs.SYSVAR_ETV_TIMER: struct.pack(">I", etv_timer), vdi_mouse.VBL_QUEUE: bytes([vdi.FILL]) * 4}))


def run_init(pokes):
    return vdi.run_primitive(INIT, {}, pokes, poison=False)


@pytest.mark.parametrize("flags", (CURSOR_DRAWN | 1, 1, 0))
def test_init_takes_the_timer_and_the_mouse_and_locks_the_cursor(flags):
    result = run_init(init_pokes(flags=flags))
    assert result.linea("USER_TIM") == addrs.VDI_ROM_NOP
    assert result.linea("NEXT_TIM") == SNAPSHOT_NEXT_TIM
    assert result.long(addrs.SYSVAR_ETV_TIMER) == addrs.VDI_ROM_TIMER_TICK
    assert result.long(vdi_mouse.VBL_QUEUE) == addrs.VDI_ROM_VBL_DRAW_CURSOR
    assert result.word(addrs.CON_CURSOR_DISABLE) == INIT_DEPTH + 1
    assert result.after(BASE, screen.SCREEN_BYTES) == bytes(screen.SCREEN_BYTES)
    inverted = result.after(screen.CURSOR_CELL_AT, 1) != CELL[screen.CURSOR_CELL_AT][:1]
    assert inverted == bool(flags & CURSOR_DRAWN)


def test_init_keeps_whatever_etv_timer_held():
    """Its own tick included: re-opening over an open workstation chains the tick to itself."""
    result = run_init(init_pokes(etv_timer=addrs.VDI_ROM_TIMER_TICK))
    assert result.linea("NEXT_TIM") == addrs.VDI_ROM_TIMER_TICK


def run_restore(pokes):
    return vdi.run_primitive(RESTORE, {}, pokes, poison=False)


CURSOR_AT = case.long_in(BASE_IMAGE, addrs.CON_CURSOR_ADDRESS)


@pytest.mark.parametrize("depth", (2, 1, 0))
def test_restore_gives_the_timer_back_clears_and_shows_the_cursor(depth):
    """The cell is drawn over the CLEARED screen — the show comes after the clear — unless nothing was locked."""
    result = run_restore(restore_pokes(depth=depth))
    assert result.long(addrs.SYSVAR_ETV_TIMER) == SNAPSHOT_NEXT_TIM
    assert result.long(vdi_mouse.VBL_QUEUE) == 0
    assert result.word(addrs.CON_CURSOR_DISABLE) == 0
    drawn = result.after(CURSOR_AT, 1)
    assert drawn == (b"\xff" if depth else b"\x00")


def test_restore_with_a_negative_next_tim_leaves_the_tick_installed():
    """Setexc reads a handler with bit 31 set as "report only": etv_timer keeps the VDI's tick."""
    result = run_restore(restore_pokes(next_tim=addrs.BIOS_SETEXC_REPORT_ONLY | SNAPSHOT_NEXT_TIM))
    assert result.long(addrs.SYSVAR_ETV_TIMER) == addrs.VDI_ROM_TIMER_TICK


# ---- the IPL bracket round init's exchange, on the shipped instructions -------------------------------------------
MASK_RAISED = re.compile(rf"\boriw #{addrs.SR_IPL_MASK},%sr$")
MASK_RESTORED = re.compile(r"\bmovew %d\d,%sr$")
SR_WRITTEN = re.compile(r",%sr$")
SETEXC_TRAP = re.compile(r"\btrap #13$")
NEXT_TIM_STORED = re.compile(rf"\bmovel %d\d,%a\d@\({vdi.field('LINEA', 'NEXT_TIM').at}\)$")


def instructions(symbol):
    """`symbol`'s instructions in the shipped build, as `m68k-elf-objdump` prints them, operand text only."""
    listing = subprocess.run(["m68k-elf-objdump", "-d", f"--disassemble={symbol}", str(transcription.SHIPPED_ELF)], capture_output=True,
                             text=True, check=True).stdout
    return [line.split("\t")[-1].strip() for line in listing.splitlines() if re.match(r"^\s+[0-9a-f]+:\t", line)]


def first(pattern, lines):
    return next(index for index, line in enumerate(lines) if pattern.search(line))


def assert_the_exchange_is_masked(init):
    """Mask raised < Setexc's trap < its answer stored in NEXT_TIM < mask restored ($fca692 store, $fca698
    `move.w (sp)+,sr`): a tick between the trap and the store would chain through a stale NEXT_TIM."""
    trap = first(SETEXC_TRAP, init)
    assert first(MASK_RAISED, init) < trap < first(NEXT_TIM_STORED, init) < first(MASK_RESTORED, init), init


def test_init_masks_the_etv_timer_exchange_and_restore_does_not():
    """init raises the mask to 7 before its Setexc and lowers it after NEXT_TIM is stored; restore writes SR
    nowhere — "given back UNMASKED". Read off the SHIPPED build: the host's mask is a no-op, and the oracle
    enters both builds at IPL 7, so no run shows it."""
    init = instructions("vdi_init_timer_mouse")
    assert_the_exchange_is_masked(init)
    restore = instructions("vdi_restore_timer_mouse")
    assert any(SETEXC_TRAP.search(line) for line in restore) and not any(SR_WRITTEN.search(line) for line in restore)


# ---- timer_tick ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tick", (20, 0, 0x8000, 0xFFFF))
def test_the_tick_calls_user_tim_then_chains_the_word(tick):
    result = screen.run_tick(tick)
    isr.assert_registers_survived(result.info)
    assert result.after(screen.USER_TIM_MARK_AT, 1) == bytes([isr.MARK])
    assert result.word(screen.NEXT_TIM_WORD_AT) == tick


def test_next_tim_is_read_after_user_tim_returns():
    """A USER_TIM that repoints NEXT_TIM is chained through the NEW handler."""
    result = screen.run_tick(20, user_tim=screen.REPOINTING_STUB_AT)
    assert result.word(screen.OTHER_NEXT_TIM_WORD_AT) == 20
    assert result.word(screen.NEXT_TIM_WORD_AT) == vdi.FILL * 0x0101


def test_the_default_user_tim_is_the_rom_s_own_rts():
    result = screen.run_tick(20, user_tim=addrs.VDI_ROM_NOP)
    assert result.word(screen.NEXT_TIM_WORD_AT) == 20


def test_what_init_installs_ships_as_its_own_entry():
    """etv_timer is handed VDI_ROM_TIMER_TICK as a CODE value: a rebuilt ROM owes it the address its entry is
    linked at, and there is one to link — the transcription, which has timer C's convention."""
    assert transcription.transcription_symbol(screen.TICK) in transcription.TRANSCRIBED


# The transcription's cases: every tick word, and each USER_TIM — the marking one, the one that repoints NEXT_TIM,
# and the ROM's own `rts`.
TICK_TRANSCRIPTIONS = ((20, screen.USER_TIM_STUB_AT), (0, screen.USER_TIM_STUB_AT), (0x8000, screen.USER_TIM_STUB_AT),
                       (0xFFFF, screen.USER_TIM_STUB_AT), (20, screen.REPOINTING_STUB_AT), (20, addrs.VDI_ROM_NOP))


@pytest.mark.parametrize("tick,user_tim", TICK_TRANSCRIPTIONS)
def test_the_tick_s_transcription_behaves_as_the_rom(tick, user_tim):
    transcription.run_transcription(screen.TICK, screen.tick_transcription_pokes(tick, user_tim), caller=screen.WORD_CALLER)


def test_the_rom_s_chain_hands_the_caller_what_the_handler_left():
    """What makes the relation above more than a register file handed through: on the ROM, USER_TIM's clobbers
    are gone again (the `movem` bracket) and NEXT_TIM's reach the caller (the chain) — with the tick word."""
    pokes = transcription.transcription_pokes(screen.TICK, screen.tick_transcription_pokes(20), screen.WORD_CALLER)
    final, _writes, left = emu.run(vdi.make_image(pokes), screen.WORD_CALLER.at, dict(transcription.DIRTY))
    chained = screen.clobbered(screen.CHAIN_CLOBBERS)
    assert {name: left[name] for name in emu.REPORTED_REGS} == {**transcription.DIRTY, **chained}
    assert bytes(final[screen.NEXT_TIM_WORD_AT:screen.NEXT_TIM_WORD_AT + 2]) == struct.pack(">H", 20)


# ---- the rows Tier 3 prices -----------------------------------------------------------------------------------------
# The span clear's C twin and its `.S` over v_clrwk's span — the worst realistic one — and the smallest with all three
# steps in it.
for _label, (_start, _end) in (("the screen", (0, screen.SCREEN_BYTES)), ("odd, a block and a tail", (1, BLOCK + 0x81))):
    _frame = case.long_args(BASE + _start, BASE + _end)
    vdi.register(f"vdi_clear_span, {_label}", addrs.VDI_ROM_CLEAR_SPAN, merge_pokes(clear_pokes(), _frame))
    vdi_helpers.register_transcription(screen.CLEAR, _label, clear_pokes(), frame=_frame)
vdi.register("vdi_v_clrwk, the screen", addrs.VDI_ROM_V_CLRWK,
             merge_pokes(vdi.function_pokes(CLRWK), screen.filled_screen()))
vdi.register("vdi_setres, low kept", addrs.VDI_ROM_SETRES, setres_pokes(1), io_seed=screen.io_shifter(0))
vdi.register("vdi_setres, mono", addrs.VDI_ROM_SETRES, setres_pokes(1), io_seed=screen.io_shifter(2))
vdi.register("vdi_setres, medium kept", addrs.VDI_ROM_SETRES, setres_pokes(3), io_seed=screen.io_shifter(1))
vdi.register("vdi_init_timer_mouse, the workstation opened", addrs.VDI_ROM_INIT_TIMER_MOUSE, init_pokes())
vdi.register("vdi_restore_timer_mouse, the workstation closed", addrs.VDI_ROM_RESTORE_TIMER_MOUSE, restore_pokes())
vdi.register("vdi_timer_tick, a tick chained", addrs.VDI_ROM_TIMER_TICK, screen.tick_pokes(20),
             regs=dict(isr.DIRTY_REGISTERS))
transcription.register_transcription(screen.TICK, "a tick chained", screen.tick_transcription_pokes(20), caller=screen.WORD_CALLER)
