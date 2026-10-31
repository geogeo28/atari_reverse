"""BOOT B3 HELD (`test/boot_hwinit.py`, `src/boot/hwinit.c`): the BIOS's hardware init `$fc2408` and the boot's stretch
around its call, `[$fc03b6, $fc03e0)` — the ROM's own against our C, on the WARM and COLD machines (ruling D8, each A
LABELLED STAGING), our side on the bench blob laid in RAM (B2's staging).

Three differentials: `$fc2408` as a FUNCTION ROW on the post-boot snapshot (host C against the ROM's routine in place,
poisoned, every chip ledger compared — and the ROM's own ledgers against the MFP / ACIA / port A sequence composed
independently out of the disassembly, `mfp.Chip`); the stretch's host C against the ROM's megabyte; and the m68k build
on the oracle against the ROM's, both rows (the function and the stretch) on both arms, every observable surface held
but what is named (`boot_hwinit.NOT_HELD`, the stack residue, the blob's span) — each name proved here: the scratch by
the registers that differ, the residue and the scratch dead by noise through the ROM's own continuation, the two linked
handlers by their mapping alone. Each surface's negative is here; the price is the table's (ruling D9)."""
import re
import struct

import pytest

import harness
from harness import BASE_IMAGE, OS_PSG_EVENT_READ, OS_PSG_EVENT_WRITE, addrs, emu

import boot
import boot_hwinit as bh
import boot_sysvars
import case
import isr
import mfp
import rom_data
from test_boot_sysvars import BOOT_FLOPPY_BOOT, BOOT_LAUNCH_STRINGS

ARMS, KINDS = tuple(bh.ARMS), bh.KINDS
C = bh.CONSTANTS
LONG_BYTES = bh.LONG_BYTES
NOISE_SEEDS = (0, 1, 2)
BAR = 1.10
# THE SCRATCH, pinned literally (a name added to `NOT_HELD` would loosen the compare in silence).
SCRATCH = {bh.FUNCTION: {"d1", "a0", "a1", "a2", "a3", "sr"}, bh.STRETCH_KIND: {"d1", "a1", "d2", "d3", "a2", "a3"}}
# ...and what the noise leaves differing at the horizon: carried past `move #$2300,sr`, unpinned by name.
CARRIED = {bh.FUNCTION: {"a3"}, bh.STRETCH_KIND: {"a3", "d3"}}
# The two read-modify-writes of port A the init calls, each entered where its constant lies.
OFFGIBIT_CLEAR_BIT4 = 0xfc2ed8          # `moveq #-17,d2 / bra` into Offgibit's body (names.txt `offgibit_clear_bit4`)
RS232_RTS_CLEAR, RS232_RTS_CLEAR_END = 0xfc28ae, 0xfc28cc   # `$fc28ae`, to the RTS-raising twin after it
ABSOLUTE_IO_PAGE = 0xff000000           # objdump's spelling of an `abs.l` I/O address: the 32-bit sign-extended form


# ---- THE ROM'S TEXT: every constant the C is spelt in, read off the instruction that uses it ------------------------------
def texts(lo, hi):
    return [text for _at, text in rom_data.instructions(lo, hi) if text]


INIT_TEXT = texts(addrs.BIOS_HARDWARE_INIT, C["ROM_HWINIT_RTS"] + boot.WORD_BYTES)


def test_the_init_is_spelt_in_the_rom_s_own_operands():
    """Each constant of `boot/hwinit.h` the init uses, as the instruction that uses it reads in the ROM's listing: the
    MFP's vector base, the AER's bit, the divider, timr_ms, both timers' control and data, the USART's longword, the
    templates and their lengths, the error vectors, the ACIAs' bytes, conterm, the key repeat, the RS232 handlers'
    table and count, the three channels and their handlers — and the routine ends at its own `rts`, which three of
    KBDVECS' vectors are stored."""
    expected = [
        f"moveb #{C['HWINIT_MFP_VECTOR_BASE']},%a0@(22)", f"bset #{C['MFP_AER_CTS_BIT']},%a0@(2)",
        f"movew #{C['HWINIT_TIMER_C_DIVIDER']},%a5@({addrs.SYSVAR_TIMER_C_DIVIDER})",
        f"movew #{C['HWINIT_TIMR_MS']},%a5@({addrs.SYSVAR_TIMR_MS})",
        f"moveq #{addrs.MFP_TIMER_C},%d0", f"moveq #{C['HWINIT_TIMER_C_CONTROL']},%d1",
        f"movew #{C['HWINIT_TIMER_C_DATA']},%d2", f"moveq #{addrs.MFP_TIMER_D},%d0",
        f"moveq #{C['HWINIT_TIMER_D_CONTROL']},%d1", f"moveq #{C['HWINIT_TIMER_D_DATA']},%d2",
        f"movel #{C['HWINIT_USART']},%d0", f"movepl %d0,%a0@({addrs.MFP_SCR - addrs.MFP_GPIP})",
        f"lea {C['ROM_IOREC_RS232_TEMPLATE']:#x},%a1", f"moveq #{C['IOREC_RS232_TEMPLATE_BYTES'] - 1},%d0",
        f"lea {C['ROM_IOREC_MIDI_TEMPLATE']:#x},%a1", f"lea {C['ROM_IOREC_IKBD_TEMPLATE']:#x},%a1",
        f"moveq #{C['IOREC_TEMPLATE_BYTES'] - 1},%d0", f"movel #{addrs.ACIA_SERVICE_RTS},%d0",
        f"movel #{addrs.MIDI_QUEUE_BYTE},%a5@({addrs.KBDVECS + addrs.KBDVECS_MIDIVEC})",
        f"movel #{addrs.MIDI_ACIA_SERVICE},%a5@({addrs.KBDVECS + addrs.KBDVECS_MIDISYS})",
        f"movel #{addrs.IKBD_ACIA_SERVICE},%a5@({addrs.KBDVECS + addrs.KBDVECS_IKBDSYS})",
        f"moveb #{C['ACIA_MASTER_RESET']},{addrs.MIDI_ACIA_STATUS | ABSOLUTE_IO_PAGE:#x}",
        f"moveb #{C['MIDI_ACIA_CONFIGURATION'] - 0x100},{addrs.MIDI_ACIA_STATUS | ABSOLUTE_IO_PAGE:#x}",
        f"moveb #{C['HWINIT_CONTERM']},%a5@({addrs.SYSVAR_CONTERM})",
        f"movel #{C['ROM_IKBD_CLOCK_PACKET']},%a5@({addrs.KBDVECS + addrs.KBDVECS_CLOCKVEC})",
        f"movel #{C['ROM_HWINIT_RTS']},%d0",
        f"moveb #{C['HWINIT_KBRATE_DELAY']},%a5@({addrs.KBRATE_DELAY})",
        f"moveb #{C['HWINIT_KBRATE_REPEAT']},%a5@({addrs.KBRATE_REPEAT})",
        f"moveb #{C['ACIA_MASTER_RESET']},{addrs.IKBD_ACIA_STATUS | ABSOLUTE_IO_PAGE:#x}",
        f"moveb #{C['IKBD_ACIA_CONFIGURATION'] - 0x100},{addrs.IKBD_ACIA_STATUS | ABSOLUTE_IO_PAGE:#x}",
        f"moveal #{C['ROM_RS232_HANDLER_TABLE']},%a3", f"moveq #{C['RS232_HANDLERS'] - 1},%d1",
        f"addib #{C['MFP_CHANNEL_RS232_FIRST']},%d0",
        f"lea {addrs.ISR_TIMER_C:#x},%a2", f"moveq #{C['MFP_CHANNEL_TIMER_C']},%d0",
        f"lea {addrs.ISR_ACIA:#x},%a2", f"moveq #{C['MFP_CHANNEL_ACIA']},%d0",
        f"lea {C['ROM_RS232_CTS_HANDLER']:#x},%a2", f"moveq #{C['MFP_CHANNEL_RS232_CTS']},%d0",
    ]
    assert [text for text in expected if text not in INIT_TEXT] == []
    assert INIT_TEXT[-1] == "rts" and INIT_TEXT.count("rts") == 1
    assert C["MFP_REGISTER_STEP"] == addrs.MFP_UCR - addrs.MFP_SCR == addrs.MFP_AER - addrs.MFP_GPIP


def test_the_port_a_masks_are_the_two_routines_own():
    """DTR: `$fc2ed8` is `moveq #-17,d2` into Offgibit's body (the low byte the mask kept); RTS: `$fc28ae`'s `andi.b`."""
    keep = struct.unpack(">h", struct.pack(">H", C["PORT_A_DTR_CLEAR_MASK"]))[0]
    assert texts(OFFGIBIT_CLEAR_BIT4, OFFGIBIT_CLEAR_BIT4 + boot.WORD_BYTES)[0] == f"moveq #{keep},%d2"
    assert f"andb #{~C['PSG_PORT_A_RTS']},%d1" in texts(RS232_RTS_CLEAR, RS232_RTS_CLEAR_END)


def test_the_stretch_is_the_call_the_ikbd_reset_the_pause_and_the_hook():
    """`[$fc03b6, $fc03e0)` read off the ROM: the init's `bsr`, Ikbdws over the reset command (two bytes, `$80 $01`), the
    32,768 passes of a `bsr` to an `rts`, the hooks with D0 = 2 — and the way on is `$fc03e0`."""
    assert texts(*bh.STRETCH) == [
        f"bsrw {addrs.BIOS_HARDWARE_INIT:#x}", f"movel #{C['ROM_IKBD_RESET_COMMAND']},%sp@-",
        f"movew #{C['IKBD_RESET_COMMAND_COUNT']},%sp@-", f"jsr {addrs.XBIOS_IKBDWS:#x}", "addql #6,%sp",
        f"movel #{C['BOOT_IKBD_RESET_DBF_COUNT']},%d0", "bsrw 0xfc0556", "dbf %d0,0xfc03d2",
        f"moveq #{C['CARTRIDGE_HOOK_IKBD_RESET']},%d0", f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}"]
    assert BASE_IMAGE[C["ROM_IKBD_RESET_COMMAND"]:C["ROM_IKBD_RESET_COMMAND"] + C["IKBD_RESET_COMMAND_COUNT"] + 1] == b"\x80\x01"
    assert bh.STRETCH[1] == C["ROM_BOOT_IKBD_RESET_DONE"] and bh.HOOKS == (C["ROM_CARTRIDGE_HOOKS"], addrs.ROM_BARE_RTS)


# ---- THE FUNCTION ROW: the host C against the ROM's routine in place (the post-boot snapshot) ------------------------------
def run_init(poison=True):
    def glue(lib, buf):
        return lib.bios_hardware_init(buf)

    return case.run(addrs.BIOS_HARDWARE_INIT, {"a5": 0}, glue, width=case.NO_RESULT, poison=poison,
                    io_seed=bh.io_seed(), psg_seed=dict(bh.PSG_SEED))


@pytest.fixture(scope="module")
def init_run():
    return run_init()


def the_chip_as_the_init_drives_it():
    """THE MFP AND THE ACIAs AS THE DISASSEMBLY DRIVES THEM, composed out of `mfp.Chip` over the rows' declaration — not the
    reconstruction's arithmetic: the three `movep.l` clears, VR, the AER's `bset`, timer C and its handler, timer D, the
    USART's `movep.l`, the two 6850s reset and configured, then the six handlers through `Mfpint`'s body, in order."""
    chip = mfp.Chip({**mfp.ENTRY_BYTES, addrs.MFP_AER: bh.AER_ENTRY})
    for register in range(addrs.MFP_GPIP, addrs.MFP_VR + 1, C["MFP_REGISTER_STEP"]):
        chip.write(register, 0)
    chip.held[addrs.MFP_AER] = 0        # ...the AER declared WRITE-THROUGH by the rows (`boot_hwinit.io_seed`)
    chip.write(addrs.MFP_VR, C["HWINIT_MFP_VECTOR_BASE"])
    chip.change_bit(addrs.MFP_AER, C["MFP_AER_CTS_BIT"], set_it=True)
    chip.program_timer(addrs.MFP_TIMER_C, C["HWINIT_TIMER_C_CONTROL"], C["HWINIT_TIMER_C_DATA"])
    install = lambda channel: (chip.disable_channel(channel), chip.enable_channel(channel))   # noqa: E731
    install(C["MFP_CHANNEL_TIMER_C"])
    chip.program_timer(addrs.MFP_TIMER_D, C["HWINIT_TIMER_D_CONTROL"], C["HWINIT_TIMER_D_DATA"])
    for register, byte in zip((addrs.MFP_SCR, addrs.MFP_UCR, addrs.MFP_RSR, addrs.MFP_TSR),
                              C["HWINIT_USART"].to_bytes(LONG_BYTES, "big")):
        chip.write(register, byte)
    for status, configuration in ((addrs.MIDI_ACIA_STATUS, C["MIDI_ACIA_CONFIGURATION"]),
                                  (addrs.IKBD_ACIA_STATUS, C["IKBD_ACIA_CONFIGURATION"])):
        chip.write(status, C["ACIA_MASTER_RESET"])
        chip.write(status, configuration)
    for channel in (*range(C["MFP_CHANNEL_RS232_FIRST"] + C["RS232_HANDLERS"] - 1, C["MFP_CHANNEL_RS232_FIRST"] - 1, -1),
                    C["MFP_CHANNEL_ACIA"], C["MFP_CHANNEL_RS232_CTS"]):
        install(channel)
    return chip


def port_a_as_the_init_drives_it():
    """...and port A's ordered accesses: Offgibit's body (read, write, Giaccess's read back), `$fc28ae`'s direct read and
    write, Ongibit's body — DTR (bit 4) and RTS (bit 3) cleared, the strobe (bit 5) set, from the declared entry byte."""
    read, write, port = OS_PSG_EVENT_READ, OS_PSG_EVENT_WRITE, addrs.PSG_PORT_A
    entry = bh.PORT_A_ENTRY
    dtr = entry & C["PORT_A_DTR_CLEAR_MASK"] & 0xff
    rts = dtr & ~C["PSG_PORT_A_RTS"] & 0xff
    strobe = rts | addrs.PRINTER_STROBE_SET_MASK
    return [(read, port, entry), (write, port, dtr), (read, port, dtr), (read, port, dtr), (write, port, rts),
            (read, port, rts), (write, port, strobe), (read, port, strobe)]


def test_the_init_is_the_rom_s_on_the_snapshot_and_its_ledgers_are_the_disassembly_s(init_run):
    """The differential (poisoned, every ledger both shores) — and the ROM's own ledgers against the sequences composed
    out of the disassembly: the ordered MFP / ACIA writes, the declared reads the latches serve, port A's accesses."""
    chip = the_chip_as_the_init_drives_it()
    regs = init_run["regs"]
    assert list(regs["hw_writes"]) == chip.writes
    assert list(regs["io_events"]) == chip.reads and not list(regs["hw_events"])
    assert list(regs["psg_events"]) == port_a_as_the_init_drives_it()


def test_the_init_lays_the_rings_kbdvecs_and_the_handlers(init_run):
    """What it stores, read off the ROM's own run: the three rings' records as the templates hold them, KBDVECS' nine,
    the six MFP vectors (the ROM's handlers on the host), conterm, the key repeat, the sound list and the strobe stamp."""
    for ring, template, length in ((addrs.IOREC_RS232, "ROM_IOREC_RS232_TEMPLATE", "IOREC_RS232_TEMPLATE_BYTES"),
                                   (addrs.IOREC_MIDI, "ROM_IOREC_MIDI_TEMPLATE", "IOREC_TEMPLATE_BYTES"),
                                   (addrs.IOREC_IKBD, "ROM_IOREC_IKBD_TEMPLATE", "IOREC_TEMPLATE_BYTES")):
        assert bytes(case.written(info=init_run, address=ring + at, size=1) for at in range(C[length])) == \
            BASE_IMAGE[C[template]:C[template] + C[length]]
    vector = lambda channel: addrs.MFP_VECTOR_TABLE + channel * addrs.VECTOR_BYTES           # noqa: E731
    table = struct.unpack_from(">4I", BASE_IMAGE, C["ROM_RS232_HANDLER_TABLE"])
    handlers = {vector(C["MFP_CHANNEL_TIMER_C"]): addrs.ISR_TIMER_C, vector(C["MFP_CHANNEL_ACIA"]): addrs.ISR_ACIA,
                vector(C["MFP_CHANNEL_RS232_CTS"]): C["ROM_RS232_CTS_HANDLER"],
                **{vector(C["MFP_CHANNEL_RS232_FIRST"] + index): handler for index, handler in enumerate(table)}}
    assert {at: case.written_long(init_run, at) for at in handlers} == handlers
    assert vector(C["MFP_CHANNEL_TIMER_C"]) == addrs.VECTOR_TIMER_C and vector(C["MFP_CHANNEL_ACIA"]) == addrs.VECTOR_ACIA
    kbdvecs = {addrs.KBDVECS_MIDIVEC: addrs.MIDI_QUEUE_BYTE, addrs.KBDVECS_VKBDERR: addrs.ACIA_SERVICE_RTS,
               addrs.KBDVECS_VMIDERR: addrs.ACIA_SERVICE_RTS, addrs.KBDVECS_STATVEC: C["ROM_HWINIT_RTS"],
               addrs.KBDVECS_MOUSEVEC: C["ROM_HWINIT_RTS"], addrs.KBDVECS_CLOCKVEC: C["ROM_IKBD_CLOCK_PACKET"],
               addrs.KBDVECS_JOYVEC: C["ROM_HWINIT_RTS"], addrs.KBDVECS_MIDISYS: addrs.MIDI_ACIA_SERVICE,
               addrs.KBDVECS_IKBDSYS: addrs.IKBD_ACIA_SERVICE}
    assert {field: case.written_long(init_run, addrs.KBDVECS + field) for field in kbdvecs} == kbdvecs
    assert len(kbdvecs) == addrs.KBDVECS_LONGWORDS
    assert (case.written(init_run, addrs.SYSVAR_CONTERM, 1), case.written(init_run, addrs.KBRATE_DELAY, 1),
            case.written(init_run, addrs.KBRATE_REPEAT, 1)) == (C["HWINIT_CONTERM"], C["HWINIT_KBRATE_DELAY"],
                                                               C["HWINIT_KBRATE_REPEAT"])
    assert (case.written_long(init_run, addrs.SOUND_LIST_POINTER), case.written_long(init_run, addrs.PRINTER_RETRY_AT),
            case.written(init_run, addrs.SOUND_LIST_DELAY, 1), case.written(init_run, addrs.SOUND_RAMP_VALUE, 1)) == (0,) * 4
    assert (case.written(init_run, addrs.SYSVAR_TIMER_C_DIVIDER, 2), case.written(init_run, addrs.SYSVAR_TIMR_MS, 2)) == (
        C["HWINIT_TIMER_C_DIVIDER"], C["HWINIT_TIMR_MS"])


# ---- THE STRETCH's HOST C: every vector the ROM's address, the stack the ROM's frames alone ---------------------------------
@pytest.mark.parametrize("arm", ARMS)
def test_the_host_c_leaves_the_rom_s_megabyte_but_the_rom_s_own_frames(arm):
    the_rom_s = bh.the_rom_s(arm, bh.STRETCH_KIND)
    frames = bh.stack_frames(the_rom_s, bh.start_of(arm, bh.STRETCH_KIND).registers["isp"])
    differing = [at for at, (one, other) in enumerate(zip(bh.host_run(bh.start_of(arm, bh.STRETCH_KIND)),
                                                          the_rom_s.machine.ram)) if one != other]
    assert differing and all(frames[0] <= at < frames[1] for at in differing)


# ---- ON THE ORACLE: both shores, both rows, both arms -----------------------------------------------------------------
@pytest.fixture(scope="module", params=[(arm, kind) for arm in ARMS for kind in KINDS], ids=lambda p: f"{p[0]}-{p[1]}")
def a_pair(request):
    arm, kind = request.param
    return arm, kind, bh.the_rom_s(arm, kind), bh.our_side(arm, kind)


def _differences(the_rom_s, ours, arm, kind, **overrides):
    blob = bh.product()
    return bh.differences(the_rom_s, ours, kind, blob.symbols, bh.residue_class(arm, kind), (blob.base, blob.end),
                          **overrides)


def test_ours_is_the_rom_s_on_every_held_surface(a_pair):
    arm, kind, the_rom_s, ours = a_pair
    assert _differences(the_rom_s, ours, arm, kind) == []
    assert ours.stop == bh.stop_of(kind) and ours.machine.registers["isp"] == the_rom_s.machine.registers["isp"]
    assert ours.hardware_writes and ours.io_reads and ours.psg_events


def test_the_scratch_is_pinned_literally_and_is_what_differs(a_pair):
    """`NOT_HELD` is the literal set, and EXACTLY the registers that differ (SR in its condition codes alone)."""
    arm, kind, the_rom_s, ours = a_pair
    assert set(bh.NOT_HELD[kind]) == SCRATCH[kind]
    theirs, mine = the_rom_s.machine.registers, ours.machine.registers
    assert {name for name in theirs if theirs[name] != mine[name]} == SCRATCH[kind]
    assert (theirs["sr"] ^ mine["sr"]) & ~bh.CCR_SET_AT_THE_RETURN == 0


def test_the_function_s_flags_are_set_by_its_return_site():
    """The return site `$fc03ba` is `move.l #imm,-(sp)` — N Z V C set, none read; X and the system byte are held."""
    assert struct.unpack_from(">H", BASE_IMAGE, bh.RETURNED)[0] == bh.MOVE_L_IMMEDIATE_TO_PREDECREMENT_SP
    assert texts(bh.RETURNED, bh.RETURNED + 6)[0].startswith("movel #") and bh.CCR_SET_AT_THE_RETURN == 0x0f


def test_the_stretch_s_end_holds_d0_and_a0_through_the_hook(a_pair):
    """The hook both shores run leaves D0 (its init bit) and A0 (past the port's magic) as the ROM's: held, not scratch."""
    arm, kind, the_rom_s, ours = a_pair
    if kind == bh.STRETCH_KIND:
        assert ours.machine.registers["d0"] == C["CARTRIDGE_HOOK_IKBD_RESET"]
        assert {"d0", "a0"}.isdisjoint(bh.NOT_HELD[kind])


def test_our_vectors_hold_our_linked_entries_and_differ_there_alone(a_pair):
    arm, kind, the_rom_s, ours = a_pair
    blob = bh.product()
    lo, hi = bh.residue_class(arm, kind)
    differing = {at - at % LONG_BYTES for at, (one, other) in enumerate(zip(the_rom_s.machine.ram, ours.machine.ram))
                 if one != other and not lo <= at < hi and not blob.base <= at < blob.end}
    assert differing == set(bh.LINKED) == {addrs.VECTOR_TIMER_C, addrs.VECTOR_ACIA}
    for vector, (symbol, rom) in bh.LINKED.items():
        held = struct.unpack_from(">I", ours.machine.ram, vector)[0]
        assert held == blob.symbols[symbol] and blob.base <= held < blob.end
        assert struct.unpack_from(">I", the_rom_s.machine.ram, vector)[0] == rom


def test_each_linked_entry_is_the_one_its_own_battery_pins():
    handlers = {handler.vector: (isr.stub_symbol(handler.constant), handler.entry) for handler in isr.HANDLERS}
    assert all(bh.LINKED[vector] == handlers[vector] for vector in bh.LINKED)


# ---- THE STAGING'S PREMISES, AND THE CUT ---------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("arm", ARMS)
def test_the_rom_s_run_neither_reads_nor_stores_the_blob_s_span(arm, kind):
    blob = bh.product()
    plain, with_the_blob = bh.the_rom_s(arm, kind), bh.the_rom_s(arm, kind, with_the_blob=True)
    assert (with_the_blob.stop, with_the_blob.instructions, with_the_blob.cycles) == (plain.stop, plain.instructions,
                                                                                      plain.cycles)
    assert with_the_blob.machine.registers == plain.machine.registers and with_the_blob.stored == plain.stored
    assert all(getattr(with_the_blob, ledger) == getattr(plain, ledger) for ledger in bh.LEDGERS)
    kept = bytearray(with_the_blob.machine.ram)
    kept[blob.base:blob.end] = plain.machine.ram[blob.base:blob.end]
    assert bytes(kept) == plain.machine.ram


class _EnteredAt:
    """A blob whose entry is an address of the ROM's: a run of "ours" that is the ROM's."""

    def __init__(self, bench, at):
        self._bench, self._at = bench, at

    def __getattr__(self, name):
        return getattr(self._bench, name)

    def entry(self, symbol):
        rom = {**dict.fromkeys(bh.ENTRY_SYMBOL.values(), self._at), bh.RETURNED_SYMBOL: bh.RETURNED}
        return rom[symbol] if symbol in rom else self._bench.entry(symbol)


@pytest.mark.parametrize("kind", KINDS)
def test_a_run_of_ours_that_runs_the_rom_s_code_is_refused_by_name(kind):
    """THE FALSE GREEN: entered at the ROM's own code, "ours" would be held equal on the ROM's instructions."""
    rom_entry = bh.CALLED if kind == bh.FUNCTION else bh.STRETCH[0]
    with pytest.raises(boot.Refused, match="our run executed the ROM's own code outside the hooks"):
        bh.our_side(boot.WARM, kind, blob=_EnteredAt(bh.product(), rom_entry))


def test_the_stretch_in_one_run_is_refused_at_the_6850_s_shared_address():
    """WHY THE STRETCH IS TWO RUNS: in one, the init's write of the IKBD ACIA's control register and Ikbdws's read of its
    status register are one modelled byte written and read back — refused by name, at `$fffc00`."""
    with pytest.raises(boot.Refused, match=r"wrote modelled hardware byte\(s\) and then read them back \(0xfffc00\)"):
        boot.run(bh.start_of(boot.WARM, bh.STRETCH_KIND), {bh.STRETCH[1]}, **bh.declared())


@pytest.mark.parametrize("arm", ARMS)
def test_the_stretch_s_first_leg_is_the_function_row_s_run(arm):
    """The ROM's stretch, cut at the init's return, is its `bsr` and then the function row's own run, to the byte."""
    first, _second = bh.legs(bh.start_of(arm, bh.STRETCH_KIND), bh.RETURNED)
    function = bh.the_rom_s(arm, bh.FUNCTION)
    assert first.machine == function.machine and first.instructions == function.instructions + 1
    assert all(getattr(first, ledger) == getattr(function, ledger) for ledger in bh.LEDGERS)


@pytest.mark.parametrize("arm", ARMS)
def test_the_joined_stretch_carries_both_legs_ledgers(arm):
    """The join keeps each leg's ledgers in order: the init's (the function row's) and then the IKBD reset's — its two
    bytes to the 6850's data port, each after a poll of its status register."""
    the_rom_s, function = bh.the_rom_s(arm, bh.STRETCH_KIND), bh.the_rom_s(arm, bh.FUNCTION)
    reset = bytes(BASE_IMAGE[C["ROM_IKBD_RESET_COMMAND"]:C["ROM_IKBD_RESET_COMMAND"] + C["IKBD_RESET_COMMAND_COUNT"] + 1])
    assert the_rom_s.hardware_writes == (*function.hardware_writes, *((addrs.IKBD_ACIA_DATA, 1, byte) for byte in reset))
    assert [address for address, _value in the_rom_s.hardware_reads] == [addrs.IKBD_ACIA_STATUS] * len(reset)
    assert the_rom_s.io_reads == function.io_reads and the_rom_s.psg_events == function.psg_events


# ---- THE PAUSE: a FLOOR the 6301 is owed, on no surface but the cycles ------------------------------------------------------
# Our second leg spends this many cycles more than the ROM's, measured: +18 the IKBD send loop's own (Ikbdws's row, 83,976
# -> 83,994: the `bra.s` over each byte's settle `rts` and its loop's shape), +108 our entry's call into `boot_ikbd_reset`
# (the image argument pushed and dropped), that C's own call frame for Ikbdws and its one `bra.s` over its pause's `rts`.
PAUSE_LEG_OVERHEAD = 18 + 108


def _second_legs(arm, blob):
    """Each shore's second leg (the IKBD reset, the pause, the hook), each PROFILED: `(the ROM's, its passes, ours, ours)`."""
    start = bh.start_of(arm, bh.STRETCH_KIND)
    first, _ = bh.legs(start, bh.RETURNED)
    emu.prof_enable(True)
    try:
        emu.prof_reset()
        the_rom_s = boot.run(first.machine, {bh.STRETCH[1]}, **bh.declared())
        the_rom_s_passes = bh.the_rom_s_pause()
        machine = boot.entered_at(boot_sysvars.laid(start, blob), blob.entry(bh.ENTRY_SYMBOL[bh.STRETCH_KIND]))
        ours_first = boot.run(machine, {blob.entry(bh.RETURNED_SYMBOL)}, **bh.declared())
        emu.prof_reset()
        ours = boot.run(ours_first.machine, {bh.STRETCH[1]}, **bh.declared())
        our_passes = bh.our_pause(blob)
    finally:
        emu.prof_enable(False)
    return the_rom_s, the_rom_s_passes, ours, our_passes


def test_the_rom_s_pause_loop_is_where_the_counter_reads_it():
    assert texts(*bh.ROM_PAUSE_LOOP) == [f"bsrw {bh.ROM_PAUSE_RTS:#x}", f"dbf %d0,{bh.ROM_PAUSE_LOOP[0]:#x}"]
    assert texts(bh.ROM_PAUSE_RTS, bh.ROM_PAUSE_RTS + boot.WORD_BYTES) == ["rts"]


@pytest.mark.parametrize("arm", ARMS)
def test_the_pause_after_the_ikbd_reset_is_the_rom_s_32768_passes_exactly(arm):
    """The pause COUNTED on both shores — 32,768 passes of a `bsr` to an `rts` each, read off each run's profile — and
    the second leg's cycles: ours never fewer than the ROM's (the elapsed time the 6301 is owed: the FLOOR, the contract)
    and over it by exactly `PAUSE_LEG_OVERHEAD`, accounted above."""
    the_rom_s, the_rom_s_passes, ours, our_passes = _second_legs(arm, bh.product())
    assert the_rom_s_passes == our_passes == C["BOOT_IKBD_RESET_DBF_COUNT"] + 1
    assert ours.cycles >= the_rom_s.cycles and ours.cycles - the_rom_s.cycles == PAUSE_LEG_OVERHEAD


# ---- THE DEAD CLASSES, PROVED TO THE HORIZON ------------------------------------------------------------------------------
# THE RESIDUE, PINNED LITERALLY (as the scratch is): derived from both shores' frames, ours 36 bytes the deeper — a frame of
# ours deeper still would widen what is left out of the compare in silence, so it reds here and is re-pinned on purpose.
THE_ROM_S_FRAMES_FLOOR = 0x7522
RESIDUE = {bh.FUNCTION: (0x74fe, 0x7556), bh.STRETCH_KIND: (0x74fe, 0x755a)}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("arm", ARMS)
def test_the_residue_is_both_shores_frames_ours_the_deeper_and_pinned(arm, kind):
    lo, hi = bh.residue_class(arm, kind)
    top = bh.start_of(arm, kind).registers["isp"]
    the_rom_s = bh.stack_frames(bh.the_rom_s(arm, kind), top)
    ours = bh.stack_frames(bh.our_side(arm, kind), top)
    assert hi == top and lo == ours[0] < the_rom_s[0] and the_rom_s[1] == ours[1] == top
    assert (lo, hi) == RESIDUE[kind] and the_rom_s[0] == THE_ROM_S_FRAMES_FLOOR


@pytest.mark.parametrize("seed", NOISE_SEEDS)
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("arm", ARMS)
def test_the_residue_and_the_scratch_are_dead_to_the_horizon(arm, kind, seed):
    """NOISE in the residue and in every register not held, on the ROM's own machine where `kind` ends: its continuation
    to `move #$2300,sr` (the proof's own declarations) leaves the same machine OUTSIDE THE RESIDUE, the same ledgers,
    instructions and cycles, and every register but the ones it CARRIES past the horizon (unpinned, by name)."""
    lo, hi = bh.residue_class(arm, kind)
    end = bh.the_rom_s(arm, kind).machine
    plain, noisy = bh.continued(end), bh.continued(bh.noised(end, lo, hi, tuple(bh.NOT_HELD[kind]), seed=seed))
    assert plain.stop == noisy.stop == boot.INTERRUPTS_OPENED
    kept = bytearray(noisy.machine.ram)
    kept[lo:hi] = plain.machine.ram[lo:hi]
    assert bytes(kept) == plain.machine.ram
    assert all(getattr(noisy, ledger) == getattr(plain, ledger) for ledger in bh.LEDGERS)
    assert (noisy.instructions, noisy.cycles) == (plain.instructions, plain.cycles)
    differing = {name for name, value in plain.machine.registers.items() if noisy.machine.registers[name] != value}
    assert differing == CARRIED[kind]


# B2's spans (its names), from the stretch's end.
BOOT_TEXT_AFTER = ((bh.STRETCH[1], BOOT_LAUNCH_STRINGS), (BOOT_FLOPPY_BOOT, addrs.ROM_BARE_RTS))
NAMES_A_CARRIED = re.compile(r"%(?:d3|a3|a4)\b")


def test_the_boot_s_own_text_after_the_stretch_never_names_what_is_carried():
    """WHAT THE NOISE CANNOT REACH, held statically: no instruction of the boot's own text after `$fc03e0` names D3, A3 or
    A4 (the cartridge hook's `movem` range saves and restores them). Past the horizon they are CARRIED, unpinned."""
    for lo, hi in BOOT_TEXT_AFTER:
        found = texts(lo, hi)
        assert found and not [text for text in found if NAMES_A_CARRIED.search(text)]


# ---- EACH SURFACE'S NEGATIVE ----------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def function_pair():
    return bh.the_rom_s(boot.WARM, bh.FUNCTION), bh.our_side(boot.WARM, bh.FUNCTION)


def _ram_changed(slice_, at, value):
    ram = bytearray(slice_.machine.ram)
    ram[at] = value
    return slice_._replace(machine=slice_.machine._replace(ram=bytes(ram)))


def _registers_changed(slice_, **changes):
    return slice_._replace(machine=slice_.machine._replace(registers={**slice_.machine.registers, **changes}))


def test_each_held_surface_changed_alone_is_named(function_pair):
    the_rom_s, ours = function_pair
    lo, _hi = bh.residue_class(boot.WARM, bh.FUNCTION)
    changed = {
        "stop": ours._replace(stop=bh.CALLED),
        "registers": _registers_changed(ours, d2=ours.machine.registers["d2"] ^ 1),
        "ram": _ram_changed(ours, addrs.SYSVAR_CONTERM, 0x55),
        "stored": ours._replace(stored=(*ours.stored, (lo - LONG_BYTES, LONG_BYTES))),
        **{ledger: ours._replace(**{ledger: (*getattr(ours, ledger), ("a staged entry",))}) for ledger in bh.LEDGERS},
    }
    assert set(changed) == set(bh.SURFACES)
    for surface, slice_ in changed.items():
        found = _differences(the_rom_s, slice_, boot.WARM, bh.FUNCTION)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


def test_sr_outside_its_condition_codes_is_seen(function_pair):
    the_rom_s, ours = function_pair
    for bit in (0x10, 0x0700, 0x2000):          # X, the interrupt mask, supervisor
        found = _differences(the_rom_s, _registers_changed(ours, sr=ours.machine.registers["sr"] ^ bit), boot.WARM,
                             bh.FUNCTION)
        assert len(found) == 1 and found[0].startswith("registers: sr outside"), (bit, found)


def test_unmapped_the_linked_vectors_are_seen(function_pair):
    the_rom_s, ours = function_pair
    found = _differences(the_rom_s, ours, boot.WARM, bh.FUNCTION, linked={})
    assert len(found) == 1 and found[0].startswith("ram")


def test_a_byte_just_outside_the_residue_is_seen_and_one_inside_is_not(function_pair):
    the_rom_s, ours = function_pair
    lo, hi = bh.residue_class(boot.WARM, bh.FUNCTION)
    assert _differences(the_rom_s, _ram_changed(ours, lo, ours.machine.ram[lo] ^ 0xff), boot.WARM, bh.FUNCTION) == []
    assert _differences(the_rom_s, _ram_changed(ours, lo - 1, ours.machine.ram[lo - 1] ^ 0xff), boot.WARM, bh.FUNCTION)
    assert _differences(the_rom_s, _ram_changed(ours, hi, ours.machine.ram[hi] ^ 0xff), boot.WARM, bh.FUNCTION)


# ---- ITS PRICE (ruling D9): the table's rows ------------------------------------------------------------------------------
def test_the_table_prices_both_rows_on_each_shore_s_own_cycles_under_the_bar():
    """Four rows: the function and the stretch, each on each arm — on the BOOT's machine rather than the snapshot's (the
    C stores this build's entries at $114 / $118, which the boot comparator alone maps back)."""
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_hwinit_slice(row)]
    assert [row.registered for row in rows] == list(bh.SLICES) and len(rows) == len(ARMS) * len(KINDS)
    bench = tier3.RomBench()
    for row in rows:
        arm, kind = bh.SLICES[row.registered]
        assert (row.entry, row.symbol) == (bh.start_pc(kind), bh.ENTRY_SYMBOL[kind])
        priced, measured = bh.priced(arm, kind), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


# OUR FUNCTION ROW's OWN COST, PINNED EXACTLY (the build is deterministic): it is what holds the interrupt bracket of
# `$fc28ae` (`rs232_rts_clear`), which no Tier 1 surface sees — no interrupt is delivered (D3) — and any codegen drift.
OUR_FUNCTION_COST = (731, 9090)


@pytest.mark.parametrize("arm", ARMS)
def test_our_function_row_s_own_cost_is_pinned(arm):
    priced = bh.priced(arm, bh.FUNCTION)
    assert (priced.ours.instructions, priced.own[0]) == OUR_FUNCTION_COST and priced.rest == 0


class _OursOwnReadShort:
    def __getattr__(self, name):
        return getattr(emu, name)

    @staticmethod
    def prof_cycles(lo, hi):
        return emu.prof_cycles(lo, hi) - (4 if lo == bh.product().base else 0)


def test_the_rest_beside_each_shore_s_own_is_held_equal_in_the_price(monkeypatch):
    monkeypatch.setattr(bh, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="beside its own, ours spent"):
        bh.priced(boot.WARM)
