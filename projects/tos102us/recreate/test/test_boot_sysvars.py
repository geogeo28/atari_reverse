"""BOOT B2 HELD (`test/boot_sysvars.py`, `src/boot/sysvars.c`): the system variables and the vector table — the ROM's
own `[$fc02cc, $fc03b6)` and `$fc0eba` against our C, on the WARM and COLD machines (ruling D8, each A LABELLED
STAGING), our side on the bench blob laid in RAM (A LABELLED STAGING too).

Three differentials: `$fc0eba` as a function (the row, host C against the ROM's routine in place); the slice's host C
against the ROM's slice; and the slice's m68k build on the oracle against the ROM's, every observable surface held but
what is named (`boot_sysvars.NOT_HELD`, the stack residue, the blob's own span) — each name proved here: the residue
and the scratch registers by noise through the ROM's own continuation, the blob's span by the ROM's run with and
without it, the five linked handlers by their mapping alone. Each surface's negative is here; the price is the
table's (ruling D9)."""
import ctypes
import re
import struct

import pytest

import harness
from harness import BASE_IMAGE, _lib, addrs, emu

import boot
import boot_head
import boot_sysvars as bs
import case
import isr
import rom_data
import transcription
import trap

ARMS = tuple(bs.ARMS)
LONG_BYTES, WORD_BYTES = bs.LONG_BYTES, boot.WORD_BYTES
NOISE_SEEDS = (0, 1, 2)
BAR = 1.10
# THE SCRATCH, pinned literally (a name added to `NOT_HELD` would loosen the compare in silence): GCC's call-clobbered
# registers, and the two the ROM's vector loop holds its bare `rte` and `rts` in.
GCC_SCRATCH = {"d0", "d1", "a0", "a1"}
THE_ROM_S_WORKING = {"a3", "a4"}
CARRIED = "a4"                          # the one the ROM's hardware init neither writes nor needs dead: it carries it


# ---- THE ROM'S SPANS, read off the ROM -----------------------------------------------------------------------------------
def test_the_span_runs_from_the_head_s_end_to_the_hardware_init_s_call():
    assert bs.SPAN == (boot.HEAD_ENDS, bs.CONSTANTS["ROM_BOOT_HARDWARE_INIT_CALL"])
    assert struct.unpack_from(">H", BASE_IMAGE, bs.SPAN[1])[0] == bs.BSR_W
    assert bs.HARDWARE_INIT_RETURNS == bs.SPAN[1] + bs.BSR_W_BYTES


def test_the_span_calls_the_header_routine_and_it_ends_at_its_first_rts():
    calls = [text for _at, text in rom_data.instructions(*bs.SPAN) if text and text.startswith("bsr")]
    assert calls == [f"bsrw {addrs.BOOT_OS_HEADER_TO_RAM:#x}"]
    lo, hi = bs.HEADER_ROUTINE
    assert lo == addrs.BOOT_OS_HEADER_TO_RAM and struct.unpack_from(">H", BASE_IMAGE, hi - WORD_BYTES)[0] == bs.RTS
    assert all(text != "rts" for _at, text in rom_data.instructions(lo, hi - WORD_BYTES))


# ---- $fc0eba, A FUNCTION ROW: the host C against the ROM's routine in place -----------------------------------------------
_lib.boot_os_header_to_ram.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.boot_os_header_to_ram.restype = None
OS_HEADER_RAM = bs.CONSTANTS["OS_HEADER_RAM"]


def run_header(poison=True):
    def glue(lib, buf):
        return lib.boot_os_header_to_ram(buf)

    return case.run(addrs.BOOT_OS_HEADER_TO_RAM, {"a5": 0}, glue, width=case.NO_RESULT, poison=poison)


def test_the_os_header_lies_in_ram_behind_a_jump_to_the_reset():
    """The differential (poisoned: a store the C skipped over a byte that already held it is seen), and what it
    stores, read off the ROM's own run: `jmp <reset>` below the copy — the two template words the routine keeps behind
    its `rts`, a `jmp` and a `bra.s` — the copy's `bra.s` back to it, `_sysbase`."""
    info = run_header()
    jump_word, branch_word = struct.unpack_from(">H4xH", BASE_IMAGE, bs.HEADER_ROUTINE[1])
    assert (jump_word, branch_word) == (bs.CONSTANTS["M68K_JMP_ABSOLUTE_LONG"], bs.CONSTANTS["OS_HEADER_BRANCH_TO_JUMP"])
    reset = struct.unpack_from(">I", BASE_IMAGE, bs.CONSTANTS["ROM_OS_HEADER"] + bs.CONSTANTS["OS_HEADER_RESET"])[0]
    jump_at = OS_HEADER_RAM - WORD_BYTES - LONG_BYTES
    assert case.written(info, jump_at, WORD_BYTES) == jump_word
    assert case.written_long(info, jump_at + WORD_BYTES) == reset
    assert case.written(info, OS_HEADER_RAM, WORD_BYTES) == branch_word
    assert OS_HEADER_RAM + WORD_BYTES + struct.unpack(">b", branch_word.to_bytes(WORD_BYTES, "big")[1:])[0] == jump_at
    assert case.written_long(info, addrs.SYSVAR_SYSBASE) == OS_HEADER_RAM


# ---- THE SLICE'S HOST C: every vector the ROM's address, the stack untouched ---------------------------------------------
@pytest.mark.parametrize("arm", ARMS)
def test_the_host_c_leaves_the_rom_s_megabyte_but_its_call_s_return_address(arm):
    """The host C over the ROM's machine at `$fc02cc` leaves its megabyte — the ROM's slice's, but for the one store
    the ROM makes under its stack top (`bsr $fc0eba`'s return address), which no C frame is."""
    the_rom_s = bs.the_rom_s(arm)
    top = the_rom_s.machine.registers["isp"]
    pushed = [(start, length) for start, length in the_rom_s.stored if start + length == top]
    assert pushed == [(top - LONG_BYTES, LONG_BYTES)]
    ours = bytearray(bs.host_run(bs.start_of(arm)))
    ours[top - LONG_BYTES:top] = the_rom_s.machine.ram[top - LONG_BYTES:top]
    assert bytes(ours) == the_rom_s.machine.ram


# ---- THE SLICE ON THE ORACLE: both shores, every held surface -------------------------------------------------------------
@pytest.fixture(scope="module", params=ARMS)
def a_pair(request):
    arm = request.param
    return arm, bs.the_rom_s(arm), bs.our_side(arm)


def _differences(the_rom_s, ours, arm, **overrides):
    blob = bs.product()
    return bs.differences(the_rom_s, ours, blob.symbols, bs.residue_class(arm), (blob.base, blob.end), **overrides)


def test_ours_is_the_rom_s_on_every_held_surface(a_pair):
    arm, the_rom_s, ours = a_pair
    assert _differences(the_rom_s, ours, arm) == []
    assert ours.stop == bs.SPAN[1] and ours.machine.registers["isp"] == the_rom_s.machine.registers["isp"]


def test_the_surfaces_and_the_scratch_are_pinned_literally():
    assert bs.SURFACES == ("stop", "registers", "ram", "stored", "hardware_writes", "io_reads", "hardware_reads",
                           "psg_events", "faults")
    assert bs.LEDGERS == bs.SURFACES[4:]
    assert set(bs.NOT_HELD) == GCC_SCRATCH | THE_ROM_S_WORKING


def test_the_registers_not_held_are_the_ones_that_differ_and_the_rom_s_two_do(a_pair):
    """Held otherwise, the registers differ in the scratch alone — and in BOTH of the ROM's working registers (the
    name is earned: the C leaves the caller's there)."""
    arm, the_rom_s, ours = a_pair
    found = _differences(the_rom_s, ours, arm, not_held={})
    assert len(found) == 1 and found[0].startswith("registers")
    differing = {name for name in bs.NOT_HELD if f"'{name}'" in found[0]}
    assert THE_ROM_S_WORKING <= differing and differing <= set(bs.NOT_HELD)


def test_our_vectors_hold_our_linked_entries_and_differ_there_alone(a_pair):
    """Unmapped, the megabyte differs at the five vectors and nowhere else: each holds OUR entry, in the blob."""
    arm, the_rom_s, ours = a_pair
    blob = bs.product()
    lo, hi = bs.residue_class(arm)
    differing = {at - at % LONG_BYTES for at, (one, other) in enumerate(zip(the_rom_s.machine.ram, ours.machine.ram))
                 if one != other and not lo <= at < hi and not blob.base <= at < blob.end}
    assert differing == set(bs.LINKED)
    for vector, (symbol, rom) in bs.LINKED.items():
        held = struct.unpack_from(">I", ours.machine.ram, vector)[0]
        assert held == blob.symbols[symbol] and blob.base <= held < blob.end
        assert struct.unpack_from(">I", the_rom_s.machine.ram, vector)[0] == rom


def test_each_linked_entry_is_the_one_its_own_battery_pins():
    """The HBL and VBL entries are `src/bios/isr.S`'s for the handlers at those vectors, the trap entries
    `src/bios/trap.S`'s, the Line-A dispatcher the transcribed table's — so a mapping back names the ROM's routine."""
    handlers = {handler.vector: (isr.stub_symbol(handler.constant), handler.entry) for handler in isr.HANDLERS}
    for vector in (addrs.VECTOR_HBL, addrs.VECTOR_VBL):
        assert bs.LINKED[vector] == handlers[vector]
    assert {bs.LINKED[addrs.VECTOR_TRAP_BIOS][0], bs.LINKED[addrs.VECTOR_TRAP_XBIOS][0]} == set(trap.LABELS)
    symbol, rom = bs.LINKED[addrs.VECTOR_LINE_A]
    assert symbol == transcription.transcription_symbol("LINEA_ROM_DISPATCH") and symbol in transcription.TRANSCRIBED
    assert rom == addrs.LINEA_ROM_DISPATCH


# ---- THE STAGING'S PREMISES ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm", ARMS)
def test_the_rom_s_slice_neither_reads_nor_stores_the_blob_s_span(arm):
    """The ROM's own slice with the blob laid is the same run as without it, outside the span: the bench blob may
    lie there for ours."""
    blob = bs.product()
    plain, with_the_blob = bs.the_rom_s(arm), bs.the_rom_s(arm, with_the_blob=True)
    assert (with_the_blob.stop, with_the_blob.instructions, with_the_blob.cycles) == (plain.stop, plain.instructions,
                                                                                      plain.cycles)
    assert with_the_blob.machine.registers == plain.machine.registers and with_the_blob.stored == plain.stored
    assert all(getattr(with_the_blob, ledger) == getattr(plain, ledger) for ledger in bs.LEDGERS)
    span = slice(blob.base, blob.end)
    kept = bytearray(with_the_blob.machine.ram)
    kept[span] = plain.machine.ram[span]
    assert bytes(kept) == plain.machine.ram


class _EnteredAtTheRom:
    """A blob whose entry is the ROM's own `$fc02cc`: a run of "ours" that is the ROM's."""

    def __init__(self, bench):
        self._bench = bench

    def __getattr__(self, name):
        return getattr(self._bench, name)

    @staticmethod
    def entry(_symbol):
        return bs.SPAN[0]


def test_a_run_of_ours_that_runs_the_rom_s_span_is_refused_by_name():
    """THE FALSE GREEN: entered at the ROM's own span, "ours" would be held equal on the ROM's instructions."""
    with pytest.raises(boot.Refused, match="our run executed the ROM's own B2 spans"):
        bs.our_side(boot.WARM, blob=_EnteredAtTheRom(bs.product()))


# ---- THE DEAD CLASSES, PROVED -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm", ARMS)
def test_the_residue_is_the_rom_s_own_frames_and_both_shores_store_under_the_top_inside_it(arm):
    lo, hi = bs.residue_class(arm)
    the_rom_s, ours = bs.the_rom_s(arm), bs.our_side(arm)
    assert hi == the_rom_s.machine.registers["isp"] == boot_head.CONSTANTS["HEAD_BIOS_STACK_TOP"]
    for shore in (the_rom_s, ours):
        frames = [(start, length) for start, length in shore.stored if start + length == hi]
        assert len(frames) == 1 and lo <= frames[0][0], f"a frame under {lo:#x}: {frames}"


@pytest.mark.parametrize("seed", NOISE_SEEDS)
@pytest.mark.parametrize("arm", ARMS)
def test_the_residue_and_the_scratch_are_dead_through_the_hardware_init(arm, seed):
    """NOISE in the residue and in every register not held, on the ROM's own machine at `$fc03b6`: its hardware init
    run to its return (the proof's declarations) leaves the same machine — RAM, ledgers, instructions, cycles and every
    register but A4, which it carries untouched."""
    lo, hi = bs.residue_class(arm)
    at_the_call = bs.the_rom_s(arm).machine
    plain, noisy = bs.continued(at_the_call), bs.continued(bs.noised(at_the_call, lo, hi, seed=seed))
    assert noisy.machine.ram == plain.machine.ram
    assert all(getattr(noisy, ledger) == getattr(plain, ledger) for ledger in bs.LEDGERS)
    assert (noisy.instructions, noisy.cycles) == (plain.instructions, plain.cycles)
    differing = {name for name, value in plain.machine.registers.items() if noisy.machine.registers[name] != value}
    assert differing == {CARRIED}


# The boot's own text after the hardware init's return, as code: the stretch to the strings the launch hands GEMDOS
# (the environment at `$fc0518`, the command lines, the IKBD reset bytes `$fc053a`), then from the floppy boot's call on.
BOOT_LAUNCH_STRINGS = 0xfc0518        # the environment `lea $fc0518(pc),a0` copies to $840: data from here ...
BOOT_FLOPPY_BOOT = 0xfc053c           # ...to the floppy boot's routine (the IKBD reset bytes $fc053a the last of it)
BOOT_TEXT_AFTER = ((bs.HARDWARE_INIT_RETURNS, BOOT_LAUNCH_STRINGS), (BOOT_FLOPPY_BOOT, addrs.ROM_BARE_RTS))
NAMES_A3_OR_A4 = re.compile(r"%a[34]\b")


def test_the_boot_s_own_text_after_the_hardware_init_never_names_a3_or_a4():
    """WHAT THE NOISE CANNOT REACH, held statically: no instruction of the boot's own text after `$fc03ba` names A3 or
    A4 (a `movem` range of the cartridge hook's saves and restores both). Beyond it — every routine the boot calls —
    is B3's and later's: A4's value is CARRIED there, unpinned (named in `boot_sysvars.NOT_HELD`)."""
    for lo, hi in BOOT_TEXT_AFTER:
        texts = [text for _at, text in rom_data.instructions(lo, hi) if text]
        assert texts and not [text for text in texts if NAMES_A3_OR_A4.search(text)]


# ---- EACH SURFACE'S NEGATIVE ----------------------------------------------------------------------------------------------
def _with(slice_, **changes):
    return slice_._replace(**changes)


def _ram_changed(slice_, at, value):
    ram = bytearray(slice_.machine.ram)
    ram[at] = value
    return slice_._replace(machine=slice_.machine._replace(ram=bytes(ram)))


@pytest.fixture(scope="module")
def warm_pair():
    return bs.the_rom_s(boot.WARM), bs.our_side(boot.WARM)


def test_each_held_surface_changed_alone_is_named(warm_pair):
    the_rom_s, ours = warm_pair
    lo, _hi = bs.residue_class(boot.WARM)
    an_unused = (addrs.SYSVAR_NVBLS, 0x55)
    changed = {
        "stop": _with(ours, stop=bs.SPAN[0]),
        "registers": _with(ours, machine=ours.machine._replace(registers={**ours.machine.registers, "d2": 1})),
        "ram": _ram_changed(ours, *an_unused),
        "stored": _with(ours, stored=(*ours.stored, (lo - LONG_BYTES, LONG_BYTES))),
        **{ledger: _with(ours, **{ledger: (*getattr(ours, ledger), ("a staged entry",))}) for ledger in bs.LEDGERS},
    }
    assert set(changed) == set(bs.SURFACES)
    for surface, slice_ in changed.items():
        found = _differences(the_rom_s, slice_, boot.WARM)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


def test_a_vector_holding_another_of_our_entries_is_seen(warm_pair):
    the_rom_s, ours = warm_pair
    blob = bs.product()
    ram = bytearray(ours.machine.ram)
    struct.pack_into(">I", ram, addrs.VECTOR_VBL, blob.symbols[bs.LINKED[addrs.VECTOR_HBL][0]])
    found = _differences(the_rom_s, ours._replace(machine=ours.machine._replace(ram=bytes(ram))), boot.WARM)
    assert len(found) == 1 and found[0].startswith("ram")


def test_unmapped_the_linked_vectors_are_seen(warm_pair):
    the_rom_s, ours = warm_pair
    found = _differences(the_rom_s, ours, boot.WARM, linked={})
    assert len(found) == 1 and found[0].startswith("ram")


def test_a_byte_of_the_residue_or_of_the_blob_s_span_is_left_out_and_nothing_else(warm_pair):
    the_rom_s, ours = warm_pair
    blob = bs.product()
    lo, hi = bs.residue_class(boot.WARM)
    assert _differences(the_rom_s, _ram_changed(ours, lo, ours.machine.ram[lo] ^ 0xff), boot.WARM) == []
    assert _differences(the_rom_s, _ram_changed(ours, blob.base, ours.machine.ram[blob.base] ^ 0xff), boot.WARM) == []
    assert _differences(the_rom_s, _ram_changed(ours, lo - 1, ours.machine.ram[lo - 1] ^ 0xff), boot.WARM)
    assert _differences(the_rom_s, _ram_changed(ours, hi, ours.machine.ram[hi] ^ 0xff), boot.WARM)
    assert _differences(the_rom_s, _ram_changed(ours, blob.end, ours.machine.ram[blob.end] ^ 0xff), boot.WARM)


def test_a_store_of_ours_into_the_blob_s_span_is_seen(warm_pair):
    the_rom_s, ours = warm_pair
    blob = bs.product()
    found = _differences(the_rom_s, _with(ours, stored=(*ours.stored, (blob.base, LONG_BYTES))), boot.WARM)
    assert found == ["stored: the addresses stored outside the residue differ"]


# ---- ITS PRICE (ruling D9): the table's two rows -----------------------------------------------------------------------
def test_the_table_prices_b2_on_each_shore_s_own_cycles_under_the_bar():
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_c_slice(row)]
    assert [row.registered for row in rows] == list(bs.SLICES)
    bench = tier3.RomBench()
    for row in rows:
        priced, measured = bs.priced(bs.SLICES[row.registered]), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


class _OursOwnReadShort:
    """`emu` with our blob's own cycles read 4 short of what the run spent: the rest then differs by 4."""

    def __getattr__(self, name):
        return getattr(emu, name)

    @staticmethod
    def prof_cycles(lo, hi):
        return emu.prof_cycles(lo, hi) - (4 if lo == bs.product().base else 0)


def test_the_rest_beside_each_shore_s_own_is_held_equal_in_the_price(monkeypatch):
    monkeypatch.setattr(bs, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="beside its own, ours spent"):
        bs.priced(boot.WARM)
