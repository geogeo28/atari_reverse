"""THE FLOPPY'S LOWER DRIVER HELD (D4 P4a, `test/boot_floppy.py`): our probe `$fc173a` and the primitives it runs on,
against the ROM's own, each call B6 makes priced at its arrival (R-P4-3, the new tier-3 row kind), reached through the
6-byte `jmp` laid at the ROM's entry (R-P4-2). Held here: the names spelt in the ROM's own operands; the glue's settle the
ROM's bytes and its tail the ROM's exit but for the A5-relative operands; the product's place; the jump's bytes; the ROM's
run unchanged with our body laid; a run of ours that enters the ROM's ported text refused by name; every arrival held on
every surface (the polls counted, the `$a28` image, every register, the stack above the chain's floor) and priced under
the bar; and each surface changed alone named."""
import struct

import pytest

import harness
from harness import BASE_IMAGE

import boot
import boot_floppy as bf
import boot_late
from harness import emu

BAR = 1.10
C = bf.CONSTANTS
ROM_PROBE_RETURN = 0xfc0f88             # hdv_init's `addal #14,sp` after its `jsr $fc173a`
LEA_ABSOLUTE_LONG_A1 = 0x43f9
SPIN_UP_POLLS = 0x60000 - 1             # the motor-off count down, decremented before each poll
CHAIN_FLOOR = 0x74ff                    # the chain holds the BIOS stack byte for byte below it (`boot_chain`), spelt here
                                        # as a literal so a floor moved in the harness is seen (review RP4a's N2)
# THE COMMON ENTRY'S UNKNOWN-TRACK RECOVERY, NOT PORTED IN P4a (review RP4a's R1): `tst.w (a1)` at $fc1ca4, its `bpl.s`
# at $fc1ca8 past it to $fc1cca — the arm between, which P4b's Floprd reaches first.
ROM_RECORD_TRACK_TEST, ROM_RECOVERY = 0xfc1ca4, (0xfc1caa, 0xfc1cca)
TRAP_7 = 0x4e47                         # `trap #7`: `recreate_not_reconstructed` on the 68000 (m68k_encodings.h)
NAMES = tuple(bf.ARRIVALS)


def _rom_word(at):
    return struct.unpack_from(">H", BASE_IMAGE, at)[0]


def _rom_long(at):
    return struct.unpack_from(">I", BASE_IMAGE, at)[0]


# ---- THE NAMES, SPELT IN THE ROM'S OWN OPERANDS ------------------------------------------------------------------------------
def test_the_probe_s_first_instruction_is_the_six_bytes_the_jump_replaces():
    assert _rom_word(bf.PROBE) == LEA_ABSOLUTE_LONG_A1 and _rom_long(bf.PROBE + 2) == C["FLOPPY_RECORD_A"]
    assert bf.STUB_BYTES == 6 and _rom_long(0xfc1748) == C["FLOPPY_RECORD_B"]


def test_the_driver_s_span_ends_past_its_last_rts():
    assert _rom_word(C["ROM_FLOPPY_LOWER_END"] - 2) == 0x4e75        # $fc1ef6's `rts`
    assert C["ROM_FLOPPY_FLOPRD"] == 0xfc1782 and _rom_word(C["ROM_FLOPPY_FLOPRD"]) == 0x6100      # Floprd's `bsr.w`


@pytest.mark.parametrize("at, value", [
    (0xfc1dc2, "FDC_WAIT_MOTOR_ON"), (0xfc1dd6, "FDC_WAIT_MOTOR_OFF"),          # `move.l #imm,d7`
])
def test_the_waits_are_the_rom_s_counts(at, value):
    assert _rom_long(at) == C[value]


def test_the_settle_and_the_force_s_delay_are_the_rom_s_counts():
    assert _rom_word(0xfc1eb0) == 0x3e3c and _rom_word(0xfc1eb2) == C["FDC_SETTLE_DBF"]
    assert _rom_word(0xfc1e06) == 0x3e3c and _rom_word(0xfc1e08) == C["FDC_FORCE_DBF"]


def test_the_save_area_is_the_common_entry_s():
    assert _rom_word(0xfc1c48) == 0x48f9 and _rom_long(0xfc1c4c) == C["FLOPPY_SAVE_AREA"]


def _symbol_code(name):
    product = bf.product()
    lo = product.symbols[name]
    hi = min(at for at in (*product.symbols.values(), product.base + len(product.code)) if at > lo)
    return product.code[lo - product.base:hi - product.base]


def test_the_glue_s_settle_is_the_rom_s_bytes():
    rom = bytes(BASE_IMAGE[0xfc1eac:0xfc1ebe])
    assert _symbol_code("floppy_settle").rstrip(b"\x4e\x71")[:len(rom)] == rom


def test_the_glue_s_tail_is_the_rom_s_exit_but_for_the_a5_operands():
    """`$fc1cf2..$fc1d28` (the stamp, the result popped, the restore, `flock`, `rts`), its two `d16(a5)` source operands
    spelt `abs.w` (A5 is the caller's in the glue: the same 8 cycles), after our push of the result (the ROM's at
    `$fc1cdc`, before its last seek, which the C makes)."""
    rom = bytearray(BASE_IMAGE[0xfc1cf2:0xfc1d28])
    for at, ours in ((0xfc1d00, 0x21b8), (0xfc1d10, 0x2178)):
        assert struct.unpack_from(">H", rom, at - 0xfc1cf2)[0] in (0x21ad, 0x216d)
        struct.pack_into(">H", rom, at - 0xfc1cf2, ours)
    assert _symbol_code("floppy_leave")[:2 + len(rom)] == bytes.fromhex("2f00") + bytes(rom)


# ---- THE PRODUCT AND ITS STAGING ---------------------------------------------------------------------------------------------
def test_the_body_lies_past_b6_s_late_slice_inside_prtblk_s_text():
    late = boot_late.product()
    product = bf.product()
    assert product.base == C["FLOPPY_LAID_AT"] >= late.base + len(late.code)
    assert product.base + len(product.code) <= C["FLOPPY_LAID_LIMIT"]


def test_the_jump_at_each_ported_entry_is_a_jmp_to_its_glue():
    for entry, symbol in bf.PORTED.items():
        assert bf.stub(entry) == struct.pack(">HI", bf.JMP_ABSOLUTE_LONG, bf.product().symbols[symbol])
        assert len(bf.stub(entry)) == bf.STUB_BYTES
    assert bf.NEVER_RUN == ((bf.PROBE + bf.STUB_BYTES, C["ROM_FLOPPY_FLOPRD"]),)
    assert bf.ROM_TEXT_STILL_RUN == ((bf.PROBE + bf.STUB_BYTES, C["ROM_FLOPPY_LOWER_END"]),)


@pytest.mark.parametrize("machine", boot_late.MACHINES)
def test_the_rom_s_run_is_the_same_with_our_body_laid(machine):
    body = bf.pieces()[0]
    plain, with_it = boot_late.the_rom_s(machine), boot_late.the_rom_s(machine, laid=body)
    assert with_it.slice.machine == plain.slice.machine and with_it.slice.stored == plain.slice.stored
    assert (with_it.slice.instructions, with_it.slice.cycles) == (plain.slice.instructions, plain.slice.cycles)
    assert all(getattr(with_it.slice, ledger) == getattr(plain.slice, ledger) for ledger in boot_late.LEDGERS)


def test_overlapping_overlays_are_refused():
    body = bf.pieces()[0]
    with pytest.raises(boot.Refused, match="two overlays overlap"):
        boot.overlays(body, boot.overlaid(body.at + 2, b"\x4e\x71\x4e\x71"))


def test_a_call_of_ours_that_runs_the_rom_s_ported_text_is_refused_by_name():
    jump_in = struct.pack(">HI", bf.JMP_ABSOLUTE_LONG, bf.NEVER_RUN[0][0])
    with pytest.raises(boot.Refused, match=r"executed the ROM's ported text \[0xfc1740, 0xfc1782\)"):
        bf.ours(NAMES[0], code=jump_in)


# ---- THE ARRIVALS --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm", boot_late.DRIVE_ARMS)
def test_b6_calls_the_probe_twice_from_hdv_init_drive_a_then_b(arm):
    calls = bf.b6_calls(boot.COLD, arm)
    assert [arrival.returns_to for arrival, _ in calls] == [ROM_PROBE_RETURN] * 2
    assert [struct.unpack_from(">H", arrival.machine.ram, arrival.machine.registers["isp"] + 12)[0]
            for arrival, _ in calls] == [0, 1]


@pytest.fixture(scope="module", params=NAMES)
def a_call(request):
    name = request.param
    return name, bf.the_rom_s(name), bf.ours(name)


def test_ours_is_the_rom_s_on_every_held_surface(a_call):
    name, rom, mine = a_call
    assert bf.differences(name, rom, mine) == []
    assert mine.slice.stop == rom.slice.stop == ROM_PROBE_RETURN


def test_our_call_spends_every_cycle_in_our_driver_and_is_under_the_bar(a_call):
    _name, rom, mine = a_call
    assert mine.own == mine.slice.cycles and rom.own == rom.slice.cycles
    assert mine.own / rom.own <= BAR


def test_the_caller_s_registers_are_saved_at_a28_and_given_back(a_call):
    """The 36 bytes at `$a28` are the caller's D3-D7 / A3-A6, on both shores; and each comes back."""
    name, rom, mine = a_call
    arrival, _ = bf.arrival_of(name)
    saved = b"".join(struct.pack(">I", arrival.machine.registers[r]) for r in
                     ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6"))
    at = C["FLOPPY_SAVE_AREA"]
    for shore in (rom, mine):
        assert shore.slice.machine.ram[at:at + len(saved)] == saved
        assert all(shore.slice.machine.registers[r] == arrival.machine.registers[r]
                   for r in ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6"))


def test_d1_and_d2_keep_the_caller_s_upper_bytes_a0_and_a1_are_the_rom_s(a_call):
    name, rom, mine = a_call
    arrival, _ = bf.arrival_of(name)
    for shore in (rom, mine):
        registers = shore.slice.machine.registers
        for register in ("d1", "d2"):
            assert registers[register] >> 8 == arrival.machine.registers[register] >> 8
        assert registers["a0"] == C["FLOPPY_LAST_ACCESS"]
        drive = struct.unpack_from(">H", arrival.machine.ram, arrival.machine.registers["isp"] + 12)[0]
        assert registers["a1"] == (C["FLOPPY_RECORD_B"] if drive else C["FLOPPY_RECORD_A"])


def test_our_frames_lie_at_the_rom_s_depth_above_the_chain_s_floor(a_call):
    """THE STACK BOUND (decision 10, the orchestrator's: the C made to fit): nothing of ours stored under the call's SP
    deeper than the ROM's own 20 bytes — the chain's floor `$74ff` well clear."""
    name, rom, mine = a_call
    sp = bf.arrival_of(name)[0].machine.registers["isp"]
    floor = bf.frames(sp)[0]

    def below(shore):
        return {at for start, length in shore.slice.stored for at in range(start, start + length) if floor <= at < sp}
    assert min(below(mine)) >= min(below(rom)) >= sp - bf.ROM_TIMEOUT_FRAME_BYTES
    if not any(event[0] == "poll" and event[2] > 1 for event in rom.slice.fdc_events):     # no wait timed out
        assert min(below(rom)) == min(below(mine)) == sp - bf.ROM_PROBE_FRAME_BYTES


@pytest.mark.parametrize("name", [name for name in NAMES if "drive A:," in name and boot_late.A_ABSENT in name])
def test_the_spin_up_timeout_counts_the_rom_s_polls(name):
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    for shore in (rom, mine):
        polls = [event for event in shore.slice.fdc_events if event[0] == "poll" and event[2] > 1]
        assert [event[2] for event in polls] == [SPIN_UP_POLLS]


# ---- EACH SURFACE CHANGED ALONE IS NAMED ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cold_call():
    name = NAMES[0]
    return name, bf.the_rom_s(name), bf.ours(name)


def _with_ram(shore, at, value):
    ram = bytearray(shore.slice.machine.ram)
    ram[at] = value
    return shore._replace(slice=shore.slice._replace(machine=shore.slice.machine._replace(ram=bytes(ram))))


def _with_registers(shore, **registers):
    machine = shore.slice.machine
    return shore._replace(slice=shore.slice._replace(machine=machine._replace(registers={**machine.registers, **registers})))


@pytest.mark.parametrize("surface", ("save area", "d1", "x flag", "stop", "below the floor", "stored", "fdc_events",
                                     "psg_events", "hardware_writes", "fdc_chip"))
def test_each_held_surface_changed_alone_is_named(cold_call, surface):
    name, rom, mine = cold_call
    sp = bf.arrival_of(name)[0].machine.registers["isp"]
    if surface == "save area":
        changed, said = _with_ram(mine, 0xa37, mine.slice.machine.ram[0xa37] ^ 1), "ram, first at 0xa37"
    elif surface == "d1":
        changed, said = _with_registers(mine, d1=mine.slice.machine.registers["d1"] ^ 1), "registers"
    elif surface == "x flag":
        changed, said = _with_registers(mine, sr=mine.slice.machine.registers["sr"] ^ 0x10), "registers"
    elif surface == "stop":
        changed, said = mine._replace(slice=mine.slice._replace(stop=0)), "stop"
    elif surface == "below the floor":
        floor = CHAIN_FLOOR - 1
        changed, said = _with_ram(mine, floor, mine.slice.machine.ram[floor] ^ 1), f"ram, first at {floor:#x}"
    elif surface == "stored":
        changed = mine._replace(slice=mine.slice._replace(stored=(*mine.slice.stored, (0x20000, 1))))
        said = "stored"
    elif surface == "fdc_chip":
        changed, said = mine._replace(slice=mine.slice._replace(fdc_chip=b"")), "fdc_chip"
    else:
        ledger = getattr(mine.slice, surface)
        changed = mine._replace(slice=mine.slice._replace(**{surface: ledger[:-1]}))
        said = surface
    found = bf.differences(name, rom, changed)
    assert len(found) == 1 and found[0].startswith(said)


def test_the_call_s_own_frames_alone_are_not_held(cold_call):
    name, rom, mine = cold_call
    sp = bf.arrival_of(name)[0].machine.registers["isp"]
    assert bf.differences(name, rom, _with_ram(mine, sp - 1, mine.slice.machine.ram[sp - 1] ^ 1)) == []


# ---- ITS PRICE (R-P4-3: the new row kind) --------------------------------------------------------------------------------------
# Each call's OWN cycles, pinned EXACTLY: (ours, the ROM's). Both drives' probes on COLD's four drive arms and WARM's capture
# drives; the two timeouts (the spin-up of no drive / of an empty drive A:) cost the ROM's own count down on both shores.
OWN = {
    "the probe of drive A:, the capture's drives, COLD": (9252, 9456),
    "the probe of drive B:, the capture's drives, COLD": (9250, 9488),
    "the probe of drive A:, drive B: absent, COLD": (9252, 9456),
    "the probe of drive B:, drive B: absent, COLD": (15686, 16114),
    "the probe of drive A:, no drive at all, COLD": (18104580, 18105004),
    "the probe of drive B:, no drive at all, COLD": (15660, 16088),
    "the probe of drive A:, drive A: empty, COLD": (18104536, 18104898),
    "the probe of drive B:, drive A: empty, COLD": (15686, 16114),
    "the probe of drive A:, the capture's drives, WARM": (9252, 9456),
    "the probe of drive B:, the capture's drives, WARM": (9250, 9488),
}


def test_every_call_is_priced_and_pinned():
    assert list(OWN) == list(NAMES)
    for name in NAMES:
        assert bf.priced(name).own == OWN[name], name


def test_the_table_prices_every_call_on_each_shore_s_whole_call_under_the_bar():
    """R-P4-3's new row kind in the table: one row a call, its costs the call's, the verdict ok."""
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_floppy_call(row)]
    assert [row.registered for row in rows] == list(bf.ARRIVALS) == list(OWN)
    bench = tier3.RomBench()
    for row in rows:
        priced, measured = bf.priced(row.registered), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == 0 and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


# ---- THE FLOOR, INDEPENDENT OF THE HARNESS (review RP4a's N2) --------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_the_arrival_rows_hold_the_bios_stack_from_the_chain_s_floor(name):
    sp = bf.arrival_of(name)[0].machine.registers["isp"]
    assert bf.frames(sp) == (CHAIN_FLOOR, sp)


# ---- THE RECOVERY ARM: A HALT IN P4a, AND NO P4a CALL REACHES IT (review RP4a's R1) ------------------------------------------
def test_the_recovery_arm_is_the_rom_s_text_past_its_bpl():
    assert _rom_word(ROM_RECORD_TRACK_TEST) == 0x4a69 and _rom_word(ROM_RECORD_TRACK_TEST + 2) == 0
    branch = BASE_IMAGE[ROM_RECORD_TRACK_TEST + 4:ROM_RECORD_TRACK_TEST + 6]
    assert branch[0] == 0x6a and ROM_RECORD_TRACK_TEST + 6 + branch[1] == ROM_RECOVERY[1] == ROM_RECOVERY[0] + 0x20


def test_ours_halts_where_the_recovery_would_run():
    """Our product holds exactly one `trap #7` — the recovery's halt (`recreate_not_reconstructed`): ported in P4b."""
    code = bf.product().code
    assert [at for at in range(0, len(code), 2) if code[at:at + 2] == TRAP_7.to_bytes(2, "big")] == [_trap_offset()]


def _trap_offset():
    code = bf.product().code
    return next(at for at in range(0, len(code), 2) if code[at:at + 2] == TRAP_7.to_bytes(2, "big"))


@pytest.mark.parametrize("name", NAMES)
def test_no_p4a_call_reaches_the_recovery_the_probe_clears_the_track_first(name):
    """HOW P4a IS HELD CLEAR OF IT: on every call B6 makes, the ROM's own run spends no cycle in the recovery's text —
    hdv_init's probe clears the record's track (`clr.w (a1)` at $fc1756) before its common entry reads it — and ours
    none at the halt (the record it reads is the one the probe cleared: the request's drive word both times)."""
    arrival, _called = bf.arrival_of(name)
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        bf._call(arrival)
        rom_spent = emu.prof_cycles(*ROM_RECOVERY)
    finally:
        emu.prof_enable(False)
    assert rom_spent == 0
    bf.ours(name)
    trap = bf.product().base + _trap_offset()
    assert emu.prof_cycles(trap, trap + 2) == 0
