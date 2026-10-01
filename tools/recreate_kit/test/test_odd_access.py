"""Pin the ODD-ACCESS COUNTER the shim keeps in place of a 68000's address error (TRAP_MODEL.md, "Odd
word and long accesses — counted, not taken").

Musashi is built with address errors off, so a word or long access at an odd address completes here
and a run that bombs on the machine reports the right answer. `rom_bench` compares what the shim
counts — the total and the first `ODD_LEDGER_CAP` addresses — between the original and the build, and
names the instruction that made the first. These pin the instrument itself, over hand-assembled probes:
the ledger keeps the addresses in order and saturates while the count goes on, and the PC it names is
the instruction that MADE the access — for a data access that instruction itself, for an instruction
fetch at an odd PC the jmp/jsr that went there (by then Musashi's previous-PC is the odd target).
"""
import struct

import kit_smoke_project

kit_smoke_project.bind()

import emu           # noqa: E402  (importable only once a project is bound)

PROBE_AT = 0x20000                    # the probe's code, above the vector page and the poked block
PROBE_TARGET = PROBE_AT + 0x100       # the data or the jump target it addresses
RTS = struct.pack(">H", 0x4E75)
ABSOLUTE_ACCESS_BYTES = 6             # an opcode word and a long address


def _absolute(opcode, target):
    return struct.pack(">HI", opcode, target)


MOVE_W_D0_ABSOLUTE = 0x33C0           # move.w d0,<xxx>.l
JMP_ABSOLUTE = 0x4EF9                 # jmp <xxx>.l
JSR_ABSOLUTE = 0x4EB9                 # jsr <xxx>.l


def _odd_accesses_of(program, extra=None):
    """What the shim counted over a bench run of `program` at PROBE_AT, with `extra` {address: bytes} staged."""
    image = bytearray(kit_smoke_project.IMAGE_SIZE)
    image[PROBE_AT:PROBE_AT + len(program)] = program
    for address, data in (extra or {}).items():
        image[address:address + len(data)] = data
    emu.run_bench(image, PROBE_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL)
    return emu.odd_accesses()


def _stores_at(*targets):
    return b"".join(_absolute(MOVE_W_D0_ABSOLUTE, target) for target in targets) + RTS


def test_a_data_access_names_its_own_instruction_and_keeps_the_addresses_in_order():
    odd = _odd_accesses_of(_stores_at(PROBE_TARGET, PROBE_TARGET + 1, PROBE_TARGET + 3))
    assert odd == {"odd_accesses": 2, "odd_addresses": (PROBE_TARGET + 1, PROBE_TARGET + 3),
                   "odd_first_pc": PROBE_AT + ABSOLUTE_ACCESS_BYTES}


def test_the_ledger_saturates_and_the_count_goes_on():
    beyond = 3
    targets = [PROBE_TARGET + 1 + 2 * i for i in range(emu.ODD_LEDGER_CAP + beyond)]
    odd = _odd_accesses_of(_stores_at(*targets))
    assert odd["odd_accesses"] == emu.ODD_LEDGER_CAP + beyond
    assert odd["odd_addresses"] == tuple(targets[:emu.ODD_LEDGER_CAP])


def test_a_fetch_at_an_odd_pc_names_the_jump_that_went_there():
    for opcode in (JMP_ABSOLUTE, JSR_ABSOLUTE):
        odd = _odd_accesses_of(_absolute(opcode, PROBE_TARGET + 1) + RTS, {PROBE_TARGET + 1: RTS})
        assert odd["odd_addresses"][0] == PROBE_TARGET + 1
        assert odd["odd_first_pc"] == PROBE_AT, f"{opcode:#06x}: named {odd['odd_first_pc']:#x}, not the jump"


def test_every_run_starts_from_none():
    _odd_accesses_of(_stores_at(PROBE_TARGET + 1))
    assert _odd_accesses_of(_stores_at(PROBE_TARGET)) == {"odd_accesses": 0, "odd_addresses": (), "odd_first_pc": 0}
