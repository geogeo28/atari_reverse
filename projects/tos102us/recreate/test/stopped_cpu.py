"""THE CPU, WHERE A RUN STANDS STOPPED — Musashi's own register accessors, for a harness that enters a machine with its
WHOLE register file or takes an exception at a stop (`aes_boot`, `bus_error`, `boot`).

The kit's door can set D0, PC and SP at a stop and wrecks the scratch registers as a C call does
(`emu.bench_door_return`): right for a callback, wrong for both things done here — entering a machine with its WHOLE
register file and its status register, and taking an exception that touches no data register. Musashi's own
accessors are exported by the oracle's library and are what the kit's door is written with; they are read here,
the kit's files untouched. (Named for the orchestrator: `emu` could offer this pair.)

Moved out of `aes_boot.py` unchanged (boot B0), so that the bus-error facility and the boot harness reach the CPU
without importing the AES's boot; `aes_boot` keeps every name it had. So is `stepped_off` (`aes_boot._Run`'s rule for
leaving a stop) and `address_runs`.
"""
import ctypes

from harness import emu

import preinit_snapshot

LONG_MASK = 0xFFFFFFFF
M68K_REGISTER = {**{f"d{n}": n for n in range(8)}, **{f"a{n}": 8 + n for n in range(8)},
                 "pc": 16, "sr": 17, "usp": 19, "isp": 20}          # m68k.h's `m68k_register_t`
CPU = emu._LIB
CPU.m68k_set_reg.argtypes, CPU.m68k_set_reg.restype = (ctypes.c_int, ctypes.c_uint), None
CPU.m68k_get_reg.argtypes, CPU.m68k_get_reg.restype = (ctypes.c_void_p, ctypes.c_int), ctypes.c_uint
CPU.m68k_set_irq.argtypes, CPU.m68k_set_irq.restype = (ctypes.c_uint,), None
REGISTER_NAMES = preinit_snapshot.REGISTER_NAMES
SR_SUPERVISOR = preinit_snapshot.SR_SUPERVISOR
SR_TRACE = 0x8000
ONE_INSTRUCTION = 1                     # the segment a run leaves a stop by (`stepped_off`)


def register(name):
    return CPU.m68k_get_reg(None, M68K_REGISTER[name])


def set_register(name, value):
    CPU.m68k_set_reg(M68K_REGISTER[name], value & LONG_MASK)


def enter(registers):
    """The stopped CPU given the whole register file of `registers`. THE STATUS REGISTER FIRST: it says which stack
    pointer A7 is, and each of the two is then set by its own name."""
    set_register("sr", registers["sr"])
    for name in REGISTER_NAMES:
        if name != "sr":
            set_register(name, registers[name])


def registers_now():
    return {name: register(name) for name in REGISTER_NAMES}


def stepped_off(stops):
    """The run, standing BEFORE the instruction at one of `stops`, taken ONE INSTRUCTION on with that PC alone
    disarmed — then every stop armed (`aes_boot._Run`'s note: EVERY ARRIVAL AT A STOP IS A STOP). Where it stands at
    none of them (a driver's call answered, the bus error taken: the PC moved) nothing is run."""
    at = register("pc")
    if at in stops:
        emu.bench_door_arm(stops - {at})
        CPU.osh_bench_resume(ONE_INSTRUCTION, (ctypes.c_uint32 * len(emu.REPORTED_REGS))())
        # THE RUN'S FIRST RESUMED SEGMENT RUNS NO INSTRUCTION (measured: the oracle counts one and the PC and A7
        # stand where the registers were laid). A run ENTERED AT A STOP — a machine continued from its idle's
        # poll — would stand there still, be stopped at once, and have its entry counted as an arrival: so that
        # one segment is taken again. (Slice L's finding; `test_a_run_entered_at_a_stop_does_not_count_its_entry`.)
        if CPU.osh_num_insns() == ONE_INSTRUCTION and register("pc") == at:
            CPU.osh_bench_resume(ONE_INSTRUCTION, (ctypes.c_uint32 * len(emu.REPORTED_REGS))())
    emu.bench_door_arm(stops)


def address_runs(addresses):
    """Sorted addresses as `(start, length)` runs."""
    runs = []
    for at in addresses:
        if runs and at == runs[-1][0] + runs[-1][1]:
            runs[-1][1] += 1
        else:
            runs.append([at, 1])
    return tuple((start, length) for start, length in runs)
