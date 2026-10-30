"""THE BOOT HARNESS HELD (boot B0, `test/boot.py`): the machines' premises, the runner's stops and refusals, the
bus-error facility, the mid-boot capture against its own mask — and a smoke of the ROM's own boot from the reset
vector on the WARM machine, which says how far the oracle takes it today. No row is made here: each test holds the
instrument B1 and the slices after it are measured with. Every machine named is A LABELLED STAGING (ruling D8)."""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu

import midboot_snapshot
import preinit_snapshot

import aes_boot
import boot
import bus_error
import case

WORD_BYTES, LONG_BYTES = boot.WORD_BYTES, boot.LONG_BYTES
MOVE_TO_SR = 0x46fc
TST_W_ABSOLUTE_LONG = 0x4a79
BSR_W = 0x6100
FC2408_BIOS_HARDWARE_INIT = 0xfc2408
LEA_ABSOLUTE_LONG_SP = 0x4ff9
SYSVAR_MEMCTRL = 0x424                  # byte: the memory controller's configuration (`$fc0056 move.b $424,$ff8001`)
MEMORY_CONTROLLER = 0xff8001            # ...the register it is restored to, as the hardware write ledger names it
SYSVAR_CMDLOAD = struct.unpack_from(">I", midboot_snapshot.STOP_INSTRUCTION, WORD_BYTES)[0]    # `tst.w _cmdload`'s operand
SR_SYSTEM_BYTE, SR_INTERRUPT_MASK = 0xff00, 0x0700
SR_TRACE = bus_error.stopped_cpu.SR_TRACE
MEMCTRL_SIZED_FLAT = 0x08               # measured: what the cold arm writes to `memctrl` on the oracle's flat megabyte
MEMCTRL_OF_THE_SNAPSHOT = 0x05          # ...and what the post-boot snapshot's machine holds (a 1 MB ST's, as Hatari sized it)
PALETTE_WRITES = range(addrs.SHIFTER_PALETTE, addrs.SHIFTER_PALETTE + addrs.SHIFTER_PALETTE_ENTRIES * WORD_BYTES, WORD_BYTES)
STATUS_LOW_BITS = 0x1f                  # a group-0 frame's status word: R/W, I/N, the function code
STATUS_READ_BIT = 0x10                  # ...R/W set: a read (the 68000 manual's layout, not the facility's constant)
FUNCTION_CODE_SUPERVISOR_DATA = 0b101   # FC2 FC1 FC0 of a supervisor data access


def rom_words(at, count):
    return struct.unpack_from(f">{count}H", BASE_IMAGE, at)


# ---- THE ADDRESSES THE HARNESS STANDS ON ARE THE ROM'S OWN -------------------------------------------------------------------
def test_the_reset_vector_is_the_rom_s_first_two_longwords_and_leads_to_the_boot():
    """An ST maps $0..$7 to the ROM's first two longwords: the SSP and the PC a reset loads. The PC is the boot's first
    instruction, `move #$2700,sr` — the SR a reset forces, entered as such."""
    assert (boot.RESET_SSP, boot.RESET_PC) == struct.unpack_from(">2I", BASE_IMAGE, emu.ROM_BASE)
    assert boot.RESET_PC == addrs.ROM_BASE + 0x30
    assert rom_words(boot.RESET_PC, 2) == (MOVE_TO_SR, boot.RESET_SR)
    registers = boot.reset_registers()
    assert (registers["pc"], registers["isp"], registers["sr"]) == (boot.RESET_PC, boot.RESET_SSP, boot.RESET_SR)
    assert not any(value for name, value in registers.items() if name not in ("pc", "isp", "sr"))


def test_the_magics_are_read_off_the_boot_s_own_compares():
    """DERIVED, then pinned: the three memory-valid longs `$fc0688` compares, and the reset-resident hook's — TOS's own
    `memvalid`, `memval2`, `memval3` and `resvalid`."""
    assert boot.memvalid_magics() == ((0x420, 0x752019f3), (0x43a, 0x237698aa), (0x51a, 0x5555aaaa))
    assert boot.resvalid_magic() == (0x426, 0x31415926)


def test_the_cut_s_addresses_are_the_rom_s_own():
    """The warm and cold arms off `$fc00ec`'s `beq.w`; the head's end after `lea $755a,sp` (the BIOS's stack top every
    capture's ISP stands at); the hardware init's `bsr`; the interrupts opened; the mid-boot stop's `tst.w _cmdload`."""
    assert (boot.WARM_ARM, boot.COLD_ARM) == (0xfc0206, 0xfc00f0)
    assert rom_words(boot.LEA_STACK, 3) == boot.LEA_STACK_WORDS
    assert boot.LEA_STACK_WORDS[0] == LEA_ABSOLUTE_LONG_SP
    assert case.long_in(BASE_IMAGE, boot.LEA_STACK + WORD_BYTES) == preinit_snapshot.BIOS_STACK_TOP == midboot_snapshot.BIOS_STACK_TOP
    opcode, displacement = struct.unpack_from(">Hh", BASE_IMAGE, boot.HARDWARE_INIT_CALLED)
    assert opcode == BSR_W and boot.HARDWARE_INIT_CALLED + WORD_BYTES + displacement == FC2408_BIOS_HARDWARE_INIT
    assert rom_words(boot.INTERRUPTS_OPENED, 2) == boot.MOVE_SR_2300
    assert bytes(BASE_IMAGE[boot.MIDBOOT:boot.MIDBOOT + 6]) == midboot_snapshot.STOP_INSTRUCTION
    assert rom_words(boot.MIDBOOT, 3) == (TST_W_ABSOLUTE_LONG, 0, SYSVAR_CMDLOAD) and SYSVAR_CMDLOAD == 0x482
    assert list(boot.THE_CUT) == sorted(boot.THE_CUT)


def test_a_rom_without_the_boot_s_instruction_is_refused_by_name(monkeypatch):
    """RED: the derivations refuse a ROM that does not hold the instruction they read (a `cmpi.l`, a `beq.w`)."""
    with pytest.raises(boot.Refused, match="cmpi.l"):
        boot._cmpi_at(boot.RESVALID_CHECK + WORD_BYTES)
    with pytest.raises(boot.Refused, match="beq.w"):
        boot._beq_w_target(boot.MEMVALID_BRANCH + WORD_BYTES)


# ---- THE MACHINES' PREMISES, PINNED BY THE BOOT'S OWN BRANCH ---------------------------------------------------------------
ARMS = {boot.WARM_ARM, boot.COLD_ARM}


def test_the_warm_machine_takes_the_warm_arm_and_the_cold_the_cold():
    """The premise each machine is labelled with, held by the ROM's own test of it: from the reset vector the WARM
    machine arrives at the warm arm (memory valid: the sizing skipped), the COLD machine at the cold arm."""
    assert boot.run(boot.warm_machine(), ARMS).stop == boot.WARM_ARM
    assert boot.run(boot.cold_machine(), ARMS).stop == boot.COLD_ARM
    assert boot.warm_machine().label == boot.WARM_LABEL and boot.cold_machine().label == boot.COLD_LABEL


@pytest.mark.parametrize("broken", [address for address, _magic in boot.memvalid_magics()], ids=hex)
def test_any_one_magic_broken_takes_the_cold_arm(broken):
    """NEGATIVE, each magic in turn: the warm machine with that one long broken is a cold machine to the boot."""
    warm = boot.warm_machine()
    ram = bytearray(warm.ram)
    ram[broken] ^= 0xff
    assert boot.run(warm._replace(ram=bytes(ram)), ARMS).stop == boot.COLD_ARM


def test_the_cold_machine_differs_from_the_warm_in_its_magics_alone():
    """What the cold machine lays beyond the warm one: the three magics, zeroed — nothing else."""
    warm, cold = boot.warm_machine(), boot.cold_machine()
    differing = {at for at in range(boot.RAM_BYTES) if warm.ram[at] != cold.ram[at]}
    magic_bytes = {at for address, _ in boot.memvalid_magics() for at in range(address, address + LONG_BYTES)}
    assert differing and differing <= magic_bytes
    assert all(case.long_in(cold.ram, address) == 0 for address, _ in boot.memvalid_magics())
    assert cold.registers == warm.registers


@pytest.mark.parametrize("staged", ["a magic broken", "the reset-resident hook valid"])
def test_a_snapshot_that_is_no_warm_machine_is_refused_by_name(staged):
    """NEGATIVE: the WARM vet refuses a snapshot whose memory is not valid, and one with a reset-resident hook (an arm
    of foreign code, D12 open)."""
    ram = bytearray(BASE_IMAGE[:boot.RAM_BYTES])
    if staged == "a magic broken":
        address, _ = boot.memvalid_magics()[1]
        ram[address] ^= 1
        match = "memory is not valid"
    else:
        address, magic = boot.resvalid_magic()
        ram[address:address + LONG_BYTES] = magic.to_bytes(LONG_BYTES, "big")
        match = "reset-resident magic"
    with pytest.raises(boot.Refused, match=match):
        boot._vet_warm(bytes(ram))


@pytest.mark.parametrize("magic", [boot.DIAGNOSTIC_CARTRIDGE_MAGIC, boot.APPLICATION_CARTRIDGE_MAGIC], ids=hex)
def test_a_cartridge_at_the_port_is_no_warm_machine(monkeypatch, magic):
    """NEGATIVE (D2 open): an image whose cartridge port holds either cartridge's magic is refused by name — the
    image here always reads 0 there, so the port is staged in a copy of it."""
    image = bytearray(BASE_IMAGE)
    image[boot.CARTRIDGE:boot.CARTRIDGE + LONG_BYTES] = magic.to_bytes(LONG_BYTES, "big")
    monkeypatch.setattr(boot, "BASE_IMAGE", image)
    with pytest.raises(boot.Refused, match="cartridge"):
        boot.warm_machine()


def test_the_cold_arm_sizes_the_oracle_s_flat_memory_and_answers_its_own_memctrl():
    """WHERE D1 BITES (open, the user's): the cold arm on the oracle's FLAT megabyte — no aliasing, no bus error at its
    end — arrives where both arms join having sized ONE MEGABYTE (register d5, stored as `phystop`) and chosen the
    memory controller's byte `$08` (register d6, stored as `memctrl`), where the post-boot snapshot's machine holds
    `$05`. Deterministic, and NOT an ST's answer: what the cold slices compare is labelled with it. Every store of the
    slice lies in the megabyte (the sizing's patterns past it are dropped by the oracle, as the bus drops them)."""
    cold = boot.run(boot.run(boot.cold_machine(), ARMS).machine, {boot.WARM_ARM})
    assert cold.machine.registers["d5"] == boot.RAM_BYTES == case.long_in(cold.machine.ram, addrs.SYSVAR_PHYSTOP)
    assert cold.machine.registers["d6"] & 0xff == cold.machine.ram[SYSVAR_MEMCTRL] == MEMCTRL_SIZED_FLAT
    assert BASE_IMAGE[SYSVAR_MEMCTRL] == MEMCTRL_OF_THE_SNAPSHOT
    assert cold.stored and all(start + length <= boot.RAM_BYTES for start, length in cold.stored)


# ---- THE RUNNER: EVERY ARRIVAL STOPS, A RUN THAT NEVER ARRIVES IS REFUSED BY NAME --------------------------------------------
PALETTE_COPY_LOOP = 0xfc00c4            # `move.w (a0)+,(a1)+ / dbf d0`: sixteen colours
PALETTE_WORDS = 16


def test_an_arrival_stops_the_run_and_the_machine_stands_there():
    """The run from the reset vector stops at its FIRST arrival at a stop — the machine left there, its PC the stop,
    the next slice's start."""
    first = boot.run(boot.warm_machine(), {boot.HEAD_FIRST_ENDS})
    assert first.stop == first.machine.registers["pc"] == boot.HEAD_FIRST_ENDS
    assert first.machine.registers["sr"] & SR_SYSTEM_BYTE == boot.RESET_SR
    assert first.instructions > 0 and first.cycles > 0


def test_every_arrival_is_a_stop_and_a_run_standing_at_one_leaves_it():
    """The palette loop's head, arrived at sixteen times: each run from a machine standing there is ONE turn of the
    loop (the stop disarmed for the first instruction alone, then armed again), its counter one lower each time."""
    standing = boot.run(boot.warm_machine(), {PALETTE_COPY_LOOP}).machine
    counters = [standing.registers["d0"] & 0xffff]
    for _turn in range(PALETTE_WORDS - 1):
        turn = boot.run(standing, {PALETTE_COPY_LOOP})
        assert turn.stop == PALETTE_COPY_LOOP
        standing = turn.machine
        counters.append(standing.registers["d0"] & 0xffff)
    assert counters == list(range(PALETTE_WORDS - 1, -1, -1))
    with pytest.raises(boot.NeverArrived):              # ...and no seventeenth arrival: the loop is done
        boot.run(standing, {PALETTE_COPY_LOOP}, budget=boot.SLICE_INSNS // 4)


def test_a_run_that_never_arrives_is_refused_by_name_within_its_budget():
    """NEGATIVE: a stop past the budget — refused, the budget and the PC it stands at said; a stop the run never meets
    (the cold arm, from the warm machine, to the head's end) — refused the same way; no stop at all — refused."""
    with pytest.raises(boot.NeverArrived, match="within 1000 instructions") as spent:
        boot.run(boot.warm_machine(), {boot.HEAD_ENDS}, budget=1000)
    assert boot.WARM_ARM <= spent.value.standing < boot.HEAD_ENDS
    with pytest.raises(boot.NeverArrived, match=f"{boot.COLD_ARM:#x}"):
        boot.run(boot.run(boot.warm_machine(), {boot.HEAD_ENDS}).machine, {boot.COLD_ARM}, budget=200_000)
    with pytest.raises(boot.Refused, match="names no stop"):
        boot.run(boot.warm_machine(), ())


def test_a_run_that_never_leaves_the_stop_it_stands_at_is_refused(monkeypatch):
    """THE NO-PROGRESS GUARD: a run standing at a stop that the step-off does not move (here a step-off that only arms
    the stops — the defect that hung the B0 mutant) is refused by name, never looped on. NEGATIVE: the real step-off
    leaves the stop (the palette loop's turns above; here one)."""
    standing = boot.run(boot.warm_machine(), {PALETTE_COPY_LOOP}).machine
    assert boot.run(standing, {PALETTE_COPY_LOOP}).stop == PALETTE_COPY_LOOP
    monkeypatch.setattr(boot.stopped_cpu, "stepped_off", emu.bench_door_arm)
    with pytest.raises(boot.Refused, match=f"no progress at {PALETTE_COPY_LOOP:#x}"):
        boot.run(standing, {PALETTE_COPY_LOOP})


def test_a_saturated_write_ledger_is_refused(monkeypatch):
    """The kit's write ledger saturated (`emu.bench_writes`' second answer — a run storing past MAX_WRITES; staged
    here, no boot slice comes near it): what the run stored is not known, and the slice is refused by name."""
    monkeypatch.setattr(boot.emu, "bench_writes", lambda memory: ({}, True))
    with pytest.raises(boot.Refused, match="write ledger saturated"):
        boot.run(boot.warm_machine(), {boot.HEAD_FIRST_ENDS})


# ---- THE DECLARATIONS A CASE PASSES REACH THE RUN ----------------------------------------------------------------------------
REZ_READ, REZ_STORED = 0xfc03e0, 0xfc03f2       # `move.b $ff8260,d0 / andi / cmpi / bne` .. `move.b d0,$44c`
MONO_TEST, COLOUR_ARM, MONO_ARM = 0xfc03f8, 0xfc0418, 0xfc0400  # `move.b $fffa01,d0 / bmi`: GPIP bit 7, the monitor
ONGIBIT, ONGIBIT_RETURNS = 0xfc2edc, 0xfc2f00   # XBIOS Ongibit: PSG register 14 read, the bit ORed in, written back
GPIP_COLOUR_MONITOR = 0x80
PSG_PORT_A, PORT_A_HELD, BIT_ASKED = 14, 0x07, 0x10


def on_the_bios_stack(pc, *stacked_words):
    """The WARM machine entered at `pc` in supervisor mode on the BIOS's stack, `stacked_words` laid at the stack
    pointer (a return address, then arguments) — LAID: the entry, the stack, the SR."""
    machine = boot.warm_machine()
    sp = PROBE_STACK - WORD_BYTES * len(stacked_words)
    ram = bytearray(machine.ram)
    struct.pack_into(f">{len(stacked_words)}H", ram, sp, *stacked_words)
    return boot.entered_at(machine._replace(ram=bytes(ram)), pc, isp=sp, sr=boot.RESET_SR)


def test_a_declared_io_byte_is_served_to_the_run_and_ledgered():
    """`io_seed`: the boot's resolution read (`$fc03e0`) is served the declared shifter byte — D0 is it, the read is in
    `io_reads`. NEGATIVE: undeclared, the kit refuses the read by name."""
    rez = boot.run(on_the_bios_stack(REZ_READ), {REZ_STORED}, io_seed={addrs.SHIFTER_RESOLUTION: 1})
    assert rez.machine.registers["d0"] & 0xff == 1
    assert [(address, value) for address, _width, value in rez.io_reads] == [(addrs.SHIFTER_RESOLUTION & boot.BUS, 1)]
    with pytest.raises(boot.Refused, match=f"the first at {addrs.SHIFTER_RESOLUTION & boot.BUS:#x}"):
        boot.run(on_the_bios_stack(REZ_READ), {REZ_STORED})


@pytest.mark.parametrize("gpip, arm", [(GPIP_COLOUR_MONITOR, COLOUR_ARM), (0, MONO_ARM)], ids=["colour", "mono"])
def test_a_declared_hardware_byte_picks_the_boot_s_arm(gpip, arm):
    """`hw_seed`: the monitor detect (`$fc03f8`, GPIP bit 7) takes the arm the declared GPIP says, the read in
    `hardware_reads`. NEGATIVE: undeclared, refused by name."""
    detect = boot.run(on_the_bios_stack(MONO_TEST), {COLOUR_ARM, MONO_ARM}, hw_seed={addrs.MFP_GPIP: gpip})
    assert detect.stop == arm and detect.hardware_reads
    with pytest.raises(boot.Refused, match="nothing declared"):
        boot.run(on_the_bios_stack(MONO_TEST), {COLOUR_ARM, MONO_ARM})


def test_a_declared_psg_register_is_read_and_written_back():
    """`psg_seed`: XBIOS Ongibit reads port A as declared and writes it back with the bit asked ORed in — the last
    PSG event names the result. NEGATIVE: undeclared, the kit refuses the read of register 14 by name."""
    machine = on_the_bios_stack(ONGIBIT, 0, 0, BIT_ASKED)       # (a return address, then the word argument)
    ongibit = boot.run(machine, {ONGIBIT_RETURNS}, psg_seed={PSG_PORT_A: PORT_A_HELD})
    assert ongibit.psg_events and PORT_A_HELD | BIT_ASKED in [event[-1] for event in ongibit.psg_events]
    with pytest.raises(boot.Refused, match="read PSG register"):
        boot.run(machine, {ONGIBIT_RETURNS})


def test_the_slice_carries_its_ledgers_and_its_stores():
    """The warm head [reset, its first slice's end): the memory controller restored ($ff8001 := `memctrl`), the PSG
    deselecting the drives (registers 7 and 14), the boot palette's sixteen words and the video base — in the hardware
    write ledger, in order; no RAM stored (the warm arm writes none before the joint)."""
    first = boot.run(boot.warm_machine(), {boot.HEAD_FIRST_ENDS})
    written = [address for address, _width, _value in first.hardware_writes]
    assert written[0] == MEMORY_CONTROLLER and first.hardware_writes[0][2] == BASE_IMAGE[SYSVAR_MEMCTRL]
    assert [address for address in written if address in PALETTE_WRITES] == list(PALETTE_WRITES)
    assert first.psg_events
    assert first.stored == ()
    head = boot.run(first.machine, {boot.HEAD_ENDS})
    assert head.stored and head.machine.registers["isp"] == preinit_snapshot.BIOS_STACK_TOP


# ---- THE BUS-ERROR FACILITY (ruling D5) ----------------------------------------------------------------------------------------
PROBE_RETURNS = 0xfc0f42                # the probe's `rts`: D0 its answer (0 no blitter, 2 a blitter)
PROBE_STACK = preinit_snapshot.BIOS_STACK_TOP


def at_the_probe(**registers):
    """The WARM machine entered at the blitter probe (`$fc0f1a`) in supervisor mode on the BIOS's stack — LAID: the
    entry, the stack, the SR."""
    return boot.entered_at(boot.warm_machine(), aes_boot.BLITTER_PROBE, isp=PROBE_STACK, sr=boot.RESET_SR, **registers)


def test_a_declared_address_faults_to_the_vector():
    """The blitter probe with its touch DECLARED to fault: the run takes the bus error at the touch, enters the probe's
    tail through vector 2, and answers NO BLITTER (D0 0, the `moveq #2` skipped); the frame — a supervisor-data read
    of `$ffff8a00` by `tst.w`, the SR it ran at, a PC past the touch — is on the stack it ran on; vector 2 is the
    machine's own again."""
    probe = boot.run(at_the_probe(), {PROBE_RETURNS}, faults=(aes_boot.THE_BLITTER_PROBE,))
    assert probe.stop == PROBE_RETURNS == probe.machine.registers["pc"]
    assert probe.machine.registers["d0"] & 0xffff == 0
    (at, frame), = probe.faults.items()
    assert at == PROBE_STACK - bus_error.FRAME_BYTES
    status, access, opcode, stacked_sr, stacked_pc = bus_error.FRAME.unpack(frame)
    assert (access, opcode) == (aes_boot.BLITTER_REGISTERS, aes_boot.BLITTER_PROBE_TOUCH_WORDS[0])
    assert status & STATUS_LOW_BITS == STATUS_READ_BIT | FUNCTION_CODE_SUPERVISOR_DATA
    assert status & ~STATUS_LOW_BITS == opcode & bus_error.STATUS_FROM_THE_INSTRUCTION
    assert stacked_sr & SR_INTERRUPT_MASK == SR_INTERRUPT_MASK
    assert stacked_pc == aes_boot.BLITTER_PROBE_TOUCH + LONG_BYTES
    assert probe.machine.ram[at:at + bus_error.FRAME_BYTES] == frame
    stored = {address for start, length in probe.stored for address in range(start, start + length)}
    assert set(range(at, at + bus_error.FRAME_BYTES)) <= stored, "the frame the harness pushed is among the slice's stores"
    assert case.long_in(probe.machine.ram, bus_error.VECTOR_BUS_ERROR) == case.long_in(BASE_IMAGE, bus_error.VECTOR_BUS_ERROR)


def test_a_slice_through_a_fault_ends_at_its_own_stop():
    """`run_through` with a fault declared ends where it is asked (the slice's stop is the stop, never the frame's
    address) with no refusal."""
    slices, refusal = boot.run_through(at_the_probe(), (PROBE_RETURNS,), faults=(aes_boot.THE_BLITTER_PROBE,))
    assert refusal is None and [one.stop for one in slices] == [PROBE_RETURNS]


def test_the_handler_a_fault_enters_is_an_arrival_when_it_is_a_stop():
    """EVERY ARRIVAL A STOP, the handler too: with the probe's tail a stop the run stops THERE, one frame pushed, D0
    still the probe's 0. NEGATIVE: with the tail no stop it runs on to the return."""
    fault = aes_boot.THE_BLITTER_PROBE
    tail = boot.run(at_the_probe(), {fault.handler, PROBE_RETURNS}, faults=(fault,))
    assert tail.stop == fault.handler == tail.machine.registers["pc"] and len(tail.faults) == 1
    assert boot.run(at_the_probe(), {PROBE_RETURNS}, faults=(fault,)).stop == PROBE_RETURNS


def test_the_fault_clears_the_trace_bit_as_a_68000_does():
    """Taken with the trace bit SET (the machine entered at the touch, tracing), the frame keeps the SR it faulted
    at — T set — and the handler is entered with T CLEAR (stopped there: the one surface that shows it, since this
    Musashi takes no trace exception either way)."""
    traced = boot.RESET_SR | SR_TRACE
    fault = aes_boot.THE_BLITTER_PROBE
    tail = boot.run(at_the_touch(sr=traced), {fault.handler}, faults=(fault,))
    (_at, frame), = tail.faults.items()
    assert bus_error.FRAME.unpack(frame)[3] == traced and not tail.machine.registers["sr"] & SR_TRACE


def test_an_undeclared_address_does_not_fault():
    """NEGATIVE: the same probe with NOTHING declared — no fault is taken; the read goes to the bus, where the kit's
    own rule answers it 0 and refuses the run by name, at the blitter's address (on the 24-bit bus)."""
    with pytest.raises(boot.Refused, match=f"the first at {aes_boot.BLITTER_REGISTERS & boot.BUS:#x}"):
        boot.run(at_the_probe(), {PROBE_RETURNS})


@pytest.mark.parametrize("wrong", ["another address", "another instruction", "another vector", "A0 not 0", "user mode"])
def test_a_fault_that_is_not_the_one_declared_is_refused_by_name(wrong):
    """NEGATIVE, each half of a declaration held: the address the instruction drives (a declaration of another one, or
    A0 not 0 at the touch), the words at the PC, where vector 2 leads, and supervisor mode."""
    fault, machine = aes_boot.THE_BLITTER_PROBE, at_the_probe()
    match = {"another address": "not 0xffff8a02", "another instruction": "not the instruction declared",
             "another vector": "vector 2 holds", "A0 not 0": "drives 0xffff8a10", "user mode": "user mode"}[wrong]
    if wrong == "another address":
        fault = fault._replace(access=aes_boot.BLITTER_REGISTERS + WORD_BYTES)
    elif wrong == "another instruction":
        fault = fault._replace(words=(fault.words[0], fault.words[1] + WORD_BYTES))
    elif wrong == "another vector":
        fault = fault._replace(handler=fault.handler + WORD_BYTES)
    elif wrong == "A0 not 0":
        machine = at_the_touch(a0=0x10)
    else:
        machine = at_the_touch(sr=0x0000, usp=PROBE_STACK)
    with pytest.raises(boot.Refused, match=match):
        boot.run(machine, {PROBE_RETURNS}, faults=(fault,))


def at_the_touch(**registers):
    """The WARM machine entered AT the probe's touch, past the probe's own set-up — LAID as the probe leaves it: A0 0,
    the SR saved in D1 and SP in A2, vector 2 at the probe's tail; `registers` override."""
    fault = aes_boot.THE_BLITTER_PROBE
    machine = boot.entered_at(at_the_probe(), fault.at, **{"a0": 0, "a2": PROBE_STACK, "d1": boot.RESET_SR, **registers})
    ram = bytearray(machine.ram)
    ram[bus_error.VECTOR_BUS_ERROR:bus_error.VECTOR_BUS_ERROR + LONG_BYTES] = fault.handler.to_bytes(LONG_BYTES, "big")
    return machine._replace(ram=bytes(ram))


def test_a_machine_standing_at_a_declared_fault_takes_it_before_anything_runs():
    """A slice that starts AT the faulting instruction (a slice before it ended there) takes the fault first — it is
    never stepped over as an ordinary stop is: entered at the touch, the run arrives at the probe's return through the
    tail, one frame pushed. And with the tail a stop, it arrives THERE: the fault taken at entry, its handler an
    arrival."""
    fault = aes_boot.THE_BLITTER_PROBE
    probe = boot.run(at_the_touch(), {PROBE_RETURNS}, faults=(fault,))
    assert probe.stop == PROBE_RETURNS == probe.machine.registers["pc"]
    assert list(probe.faults) == [PROBE_STACK - bus_error.FRAME_BYTES] and probe.machine.registers["isp"] == PROBE_STACK
    tail = boot.run(at_the_touch(), {fault.handler}, faults=(fault,))
    assert tail.stop == fault.handler and tail.instructions == 0 and len(tail.faults) == 1


EA_CASES = {           # opcode (tst.w <ea>), its extension words, the registers laid, the address it drives
    "(a3)": ((0x4a53,), {"a3": 0x123456}, 0x123456),
    "d16(a0), negative": ((0x4a68, 0x8a00), {"a0": 0}, 0xffff8a00),
    "d16(a2), positive": ((0x4a6a, 0x0010), {"a2": 0x1000}, 0x1010),
    "abs.w, sign-extended": ((0x4a78, 0xfa01), {}, 0xfffffa01),
    "abs.l": ((0x4a79, 0x00fa, 0x0000), {}, 0xfa0000),
}


@pytest.mark.parametrize("mode", EA_CASES)
def test_the_effective_address_is_the_instruction_s_own(mode):
    """The facility's decoder over the modes a probe uses, each against the address the 68000 forms."""
    words, registers, driven = EA_CASES[mode]
    for name, value in registers.items():
        boot.stopped_cpu.set_register(name, value)
    assert bus_error.effective_address(words) == driven


def test_a_mode_the_decoder_does_not_hold_is_refused():
    """NEGATIVE: a data-register operand (`tst.w d0`) drives no address; a declaration over it is refused, not guessed."""
    with pytest.raises(bus_error.Refused, match="mode 0/0"):
        bus_error.effective_address((0x4a40,))
    with pytest.raises(bus_error.Refused, match="two faults declared"):
        bus_error.stops_of((aes_boot.THE_BLITTER_PROBE, aes_boot.THE_BLITTER_PROBE._replace(what="again")))


def test_a_fault_whose_handler_is_a_declared_fault_is_refused():
    """THE NO-PROGRESS GUARD, the facility's half: a fault leading into another declared fault would fault for ever.
    NEGATIVE: two faults whose handlers are no declared address are taken as declared."""
    probe = aes_boot.THE_BLITTER_PROBE
    into_itself = probe._replace(what="into the probe's touch", at=probe.handler, handler=probe.at)
    with pytest.raises(bus_error.Refused, match="is itself a declared fault"):
        bus_error.stops_of((probe, into_itself))
    elsewhere = probe._replace(what="elsewhere", at=PROBE_RETURNS)
    assert set(bus_error.stops_of((probe, elsewhere))) == {probe.at, PROBE_RETURNS}


def test_aes_boot_s_probe_is_one_declaration_of_the_facility():
    """`aes_boot`'s blitter probe, generalised (behaviour-neutral: its own tests unchanged): the declaration is its old
    constants, and its frame struct is the facility's."""
    probe = aes_boot.THE_BLITTER_PROBE
    assert (probe.at, probe.words, probe.access, probe.handler, probe.read) == (
        aes_boot.BLITTER_PROBE_TOUCH, aes_boot.BLITTER_PROBE_TOUCH_WORDS, aes_boot.BLITTER_REGISTERS,
        aes_boot.BLITTER_PROBE_FAULTED, True)
    assert aes_boot._BUS_ERROR_FRAME is bus_error.FRAME and aes_boot.Refused is bus_error.Refused


# ---- THE MID-BOOT CAPTURE (ruling D8), AGAINST ITS OWN MASK ---------------------------------------------------------------------
NOISE_SEED = 0x6f2c
AUTO_RUNNER, AUTO_PROCESS = 0xfc0c4a, 0xfc0cae      # the BIOS's AUTO runner, called; its process, entered by Pexec(4)


def test_the_mid_boot_capture_stands_where_it_says():
    """The kept capture: at `$fc047a` (`tst.w _cmdload`, read off the ROM), in supervisor mode, ISP at the BIOS's stack
    top as the ROM's `lea` loads it, the interrupts open (mask 3); the deepest frame the boot left on that stack lies
    inside the mask, and nothing was stored for as far again below its floor."""
    machine = boot.midboot_machine()
    registers, ram = machine.registers, machine.ram
    assert registers["pc"] == midboot_snapshot.STOP == boot.MIDBOOT
    assert registers["sr"] & preinit_snapshot.SR_SUPERVISOR and registers["sr"] & SR_INTERRUPT_MASK == 0x0300
    assert registers["isp"] == case.long_in(BASE_IMAGE, boot.LEA_STACK + WORD_BYTES)
    floor = registers["isp"] - midboot_snapshot.STACK_DEAD_BYTES
    assert (floor, midboot_snapshot.STACK_DEAD_BYTES, ) == next(
        (lo, size) for lo, size, _why in midboot_snapshot.MASK if lo + size == registers["isp"])
    assert any(ram[floor:registers["isp"]]), "the BIOS's stack holds the boot's frames"
    assert not any(ram[floor - midboot_snapshot.STACK_DEAD_BYTES:floor]), f"a frame lies below {floor:#x}"
    assert len(machine.io) == midboot_snapshot.IO_BYTES and machine.label == boot.MIDBOOT_LABEL


def test_a_file_that_is_no_mid_boot_machine_is_refused(tmp_path):
    """NEGATIVE: a pre-init machine's file is not a mid-boot one (its own magic), nor is a truncated one."""
    other = tmp_path / "other.bin"
    other.write_bytes(preinit_snapshot.packed(aes_boot.preinit()))
    with pytest.raises(ValueError, match="not a mid-boot machine"):
        midboot_snapshot.load(other)
    other.write_bytes(boot.midboot_machine().ram)
    with pytest.raises(ValueError, match="not a mid-boot machine"):
        midboot_snapshot.load(other)


def test_the_capture_tool_refuses_what_is_no_mid_boot_stop(tmp_path):
    """The tool's own vets, as `preinit_snapshot`'s are held: the kept capture passes; another PC, user mode, another
    ISP are refused; a ROM without `tst.w $482` at the stop is refused before a capture is taken; a tree with no
    capture says which target makes one."""
    kept = midboot_snapshot.load()
    midboot_snapshot._vet_stopped_at_the_boot_s_tail(kept)
    for wrong, said in (({"pc": midboot_snapshot.STOP + WORD_BYTES}, "stopped at PC"),
                        ({"sr": kept.registers["sr"] & ~preinit_snapshot.SR_SUPERVISOR}, "supervisor mode"),
                        ({"isp": midboot_snapshot.BIOS_STACK_TOP - LONG_BYTES}, "supervisor mode")):
        with pytest.raises(SystemExit, match=said):
            midboot_snapshot._vet_stopped_at_the_boot_s_tail(kept._replace(registers={**kept.registers, **wrong}))
    rom = bytearray(BASE_IMAGE[emu.ROM_BASE:emu.ROM_END])
    midboot_snapshot._vet_the_rom_stops_there(bytes(rom))
    rom[midboot_snapshot.STOP - addrs.ROM_BASE] ^= 0xff
    with pytest.raises(SystemExit, match="not the boot's tail"):
        midboot_snapshot._vet_the_rom_stops_there(bytes(rom))
    with pytest.raises(FileNotFoundError, match="make midboot"):
        midboot_snapshot.load(tmp_path / "midboot.bin")


def test_twice_says_every_disagreement_the_mask_does_not_excuse():
    """`--twice`'s verdict (`disagreements`): a capture agrees with itself and with itself noised IN the mask; a byte
    outside the mask, a register and the shifter bytes are each said."""
    kept = midboot_snapshot.load()
    assert midboot_snapshot.disagreements(kept, kept) == ()
    spans = [(lo, lo + size) for lo, size, _why in midboot_snapshot.MASK]
    assert midboot_snapshot.disagreements(kept, kept._replace(ram=aes_boot.noise_over(kept.ram, spans, NOISE_SEED))) == ()
    outside = kept._replace(ram=aes_boot.noise_over(kept.ram, [(boot.RAM_BYTES - UNTOUCHED_TAIL, boot.RAM_BYTES)], NOISE_SEED))
    register = kept._replace(registers={**kept.registers, "d3": kept.registers["d3"] ^ 1})
    shifter = kept._replace(io=bytes([kept.io[0] ^ 1]) + kept.io[1:])
    assert [midboot_snapshot.disagreements(kept, other) for other in (outside, register, shifter)] == [
        ("the RAM outside the mask",), ("the register d3",), ("the shifter bytes",)]


def test_the_mid_boot_mask_is_regions_of_ram_in_order_and_apart_each_field_its_own_width():
    """As the pre-init mask is held: regions of RAM, in order, apart, each said. AND EACH FIELD IS ITS OWN WIDTH: a
    region at an address the pre-init mask names (a clock, the floppy's words, a counter) is the pre-init region,
    byte for byte; the two stacks are masked to their tops (GEMDOS's own, the BIOS's at the capture's ISP)."""
    ends = 0
    for at, size, why in midboot_snapshot.MASK:
        assert ends <= at and size > 0 and at + size <= boot.RAM_BYTES and why
        ends = at + size
    preinit_fields = {at: size for at, size, _why in preinit_snapshot.MASK}
    stacks = {preinit_snapshot.GEMDOS_STACK_TOP, midboot_snapshot.BIOS_STACK_TOP}
    for at, size, _why in midboot_snapshot.MASK:
        assert at + size in stacks or preinit_fields.get(at) == size, f"the region at {at:#x} is not its field's width"
    assert stacks <= {at + size for at, size, _why in midboot_snapshot.MASK}


def floppy_entries(machine):
    """The floppy driver's three entries, as the machine's own vectors hold them."""
    return tuple(case.long_in(machine.ram, vector) & boot.BUS for vector in (addrs.HDV_BPB, addrs.HDV_MEDIACH, addrs.HDV_RWABS))


def to_the_floppy(machine):
    """The ROM run from the mid-boot machine to its first call of the floppy driver: the AUTO runner called, its process
    entered, GEMDOS asked to search `\\AUTO` — each arrival in turn."""
    slices, refusal = boot.run_through(machine, (AUTO_RUNNER, AUTO_PROCESS, *floppy_entries(machine)),
                                       final=floppy_entries(machine))
    assert refusal is None, refusal
    return slices


def test_the_capture_s_masked_bytes_are_read_by_no_run_from_it():
    """THE MASK'S RULE, AS A SURFACE: from the capture whose every masked byte is NOISE, the ROM takes the same road to
    the floppy driver — the same stops in the same order, the same instructions, the same registers — and leaves the
    same machine outside the mask. ITS REACH IS SHORTER THAN THE PRE-INIT RULE'S: only to the FIRST floppy call
    (`[$fc047a, Getbpb)`: the AUTO runner, its process, GEMDOS's first disk call) — this runner has no floppy device,
    so a masked byte read later in the launch is not exercised here. B4 carries the rule to `gem_entry`, where
    `aes_boot`'s device model serves the floppy."""
    plain = boot.midboot_machine()
    spans = [(lo, lo + size) for lo, size, _why in midboot_snapshot.MASK]
    noised = plain._replace(ram=aes_boot.noise_over(plain.ram, spans, NOISE_SEED))
    assert noised.ram != plain.ram
    ours, theirs = to_the_floppy(plain), to_the_floppy(noised)
    assert [one.stop for one in ours] == [one.stop for one in theirs]
    assert ours[-1].stop in floppy_entries(plain)
    for one, other in zip(ours, theirs):
        assert (one.instructions, one.machine.registers) == (other.instructions, other.machine.registers)
    assert midboot_snapshot.masked(ours[-1].machine.ram) == midboot_snapshot.masked(theirs[-1].machine.ram)


UNTOUCHED_TAIL = 16                     # the screen's last bytes: no run from the capture to the floppy writes there


def test_noise_outside_the_mask_is_seen():
    """NEGATIVE, the comparison's own: the same noise laid OUTSIDE the mask (the screen's last bytes, which the road
    does not write) is carried to the end and the two machines differ outside the mask — the rule above is no
    comparison of masked copies that could not differ."""
    plain = boot.midboot_machine()
    noised = plain._replace(ram=aes_boot.noise_over(plain.ram, [(boot.RAM_BYTES - UNTOUCHED_TAIL, boot.RAM_BYTES)], NOISE_SEED))
    ours, theirs = to_the_floppy(plain), to_the_floppy(noised)
    assert midboot_snapshot.masked(ours[-1].machine.ram) != midboot_snapshot.masked(theirs[-1].machine.ram)


# ---- THE SMOKE: THE ROM'S OWN BOOT FROM THE RESET VECTOR ON THE WARM MACHINE, THROUGH THE CUT ------------------------------------
TIMER_PROGRAMMER_READS_BACK = (0xfc260e, 0xfc2618)   # `move.b d2,(a0,d3) / cmp.b (a0,d3),d2 / bne`: the data register's echo


def test_the_smoke_the_warm_boot_reaches_the_hardware_init_and_spins_in_the_timer_programmer():
    """HOW FAR THE ORACLE TAKES THE ROM'S OWN BOOT TODAY, with nothing declared but the machine: from the reset vector
    on the WARM machine it arrives at every cut of the head and at the hardware init's call — [reset, $fc00da),
    [$fc00da, the warm arm $fc0206), [$fc0206, $fc02cc), [$fc02cc, $fc03b6), each with no refusal — and then NEVER
    ARRIVES at `$fc03e0`: the BIOS's hardware init (`$fc2408`) programs Timer C and spins in the timer programmer's
    read-back of the data register (`$fc260e`), which no declaration here echoes (B3's, by the MFP's write-through
    declarations — Xbtimer's precedent). Past it, with ad-hoc declarations (the B0 hand-back's measure, not a test):
    the floppy boot's count-down waits time out and the ACSI probe's `_hz_200` wait (`$fc062a`) spins for ever (D3)."""
    slices, refusal = boot.run_through(boot.warm_machine(), boot.THE_CUT)
    assert [one.stop for one in slices] == [boot.HEAD_FIRST_ENDS, boot.WARM_ARM, boot.HEAD_ENDS, boot.HARDWARE_INIT_CALLED]
    assert isinstance(refusal, boot.NeverArrived)
    assert TIMER_PROGRAMMER_READS_BACK[0] <= refusal.standing < TIMER_PROGRAMMER_READS_BACK[1]
