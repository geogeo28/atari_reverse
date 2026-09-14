"""The image a ROM differential starts from: the post-boot RAM snapshot, and the ROM over it.

Everything this project proves rests on that image being the machine it claims to be, so the claims
are here rather than in a comment: where the ROM sits, where RAM ends, that the boot really reached
the desktop, that the band the oracle uses as a stack is dead memory, and — the one with teeth —
that no verified function depends on a byte the capture does not reproduce.

`tools/boot_snapshot.py` measured that last set over three independent boots: 1,929 bytes of AES and
desktop idle scratch, listed there as `MASK`. Rather than trust the list, the case below fills every
masked region with pseudo-random bytes and asks whether the ORIGINAL still does the same thing.

IT IS THE ORACLE ALONE THAT IS RE-RUN, and that is the whole design of it. A differential hands the
SAME image to both cores, so a function that reads a masked byte reads the same noise on both sides
and the case comes back green — the dependence cancels exactly where it would have shown. What
cannot cancel is the ORIGINAL compared against ITSELF over two different snapshots: its registers,
its write set, the bytes it wrote and its PSG ledger all move the moment it reads one of those
bytes, whatever any reconstruction does.
"""
import random
import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import boot_snapshot                                      # noqa: E402

import test_xbios_giaccess as giaccess                     # noqa: E402
import test_xbios_random as xbios_random                   # noqa: E402

import abi                                                 # noqa: E402
from harness import BASE_IMAGE, addrs, emu, make_image, set_base_image   # noqa: E402
from recreate_kit.harness import _vet_rom_io_reads_are_modelled          # noqa: E402

ROM_BYTES = Path(boot_snapshot.ROM).stat().st_size


def long_at(address, image=None):
    """The big-endian longword at `address` in the snapshot (or in `image`)."""
    image = BASE_IMAGE if image is None else image
    return int.from_bytes(bytes(image[address:address + 4]), "big")


# ---- the image's shape ---------------------------------------------------------------------------

def test_the_rom_is_mapped_at_its_own_base():
    """Byte for byte, and at $fc0000 — a ROM is linked for the address it answers at."""
    assert ROM_BYTES == addrs.ROM_BYTES
    assert bytes(BASE_IMAGE[addrs.ROM_BASE:addrs.ROM_BASE + ROM_BYTES]) == \
        Path(boot_snapshot.ROM).read_bytes()


def test_the_machine_is_the_one_the_snapshot_was_taken_on():
    """`_sysbase` points at the ROM, `phystop` at the top of a 1 MB machine, and the screen sits
    where `_memtop` leaves it. A capture from another configuration fails here, not later."""
    assert long_at(addrs.SYSVAR_SYSBASE) == addrs.ROM_BASE
    assert long_at(addrs.SYSVAR_PHYSTOP) == addrs.ST_RAM_BYTES
    assert long_at(addrs.SYSVAR_MEMBOT) < long_at(addrs.SYSVAR_MEMTOP) <= addrs.ST_RAM_BYTES
    assert long_at(addrs.SYSVAR_V_BAS_AD) == long_at(addrs.SYSVAR_MEMTOP)


@pytest.mark.parametrize("vector", ("VECTOR_TRAP_GEMDOS", "VECTOR_TRAP_GEM",
                                    "VECTOR_TRAP_BIOS", "VECTOR_TRAP_XBIOS"))
def test_every_os_trap_vector_points_into_the_rom(vector):
    """ROM mode installs no trap model: a `trap #13` is taken through THESE longwords. If the boot
    had not finished installing them, every such run would execute whatever is at address 0."""
    handler = long_at(getattr(addrs, vector))
    assert addrs.ROM_BASE <= handler < addrs.ROM_BASE + ROM_BYTES, (
        f"{vector} points at {handler:#x}, outside the ROM")


def test_the_kit_is_bound_in_rom_mode_over_this_machine():
    """The binding the whole project hangs off, asserted rather than assumed."""
    assert emu.ROM_MODE and emu.ROM_BASE == addrs.ROM_BASE
    assert emu.RAM_END == addrs.ST_RAM_BYTES
    assert emu.ROM_END == addrs.ROM_BASE + ROM_BYTES


def test_the_stack_band_is_dead_memory_in_this_snapshot():
    """`stack_top` in project.toml puts the oracle's machine stack in the free TPA. The band is
    dropped from the diff, so anything the desktop had left there would be invisible to every
    case — and the oracle would be running its stack over live data while the candidate was not."""
    band = bytes(BASE_IMAGE[emu.STACK_GUARD_LO:emu.STACK_BAND_HI])
    assert band == bytes(len(band)), (
        f"the snapshot is not empty in [{emu.STACK_GUARD_LO:#x}, {emu.STACK_BAND_HI:#x}) — move "
        f"`stack_top` in project.toml to a band this capture leaves clear")


def test_the_diff_covers_everything_but_that_band():
    """A ROM project's image continues above the stack, unlike a .PRG's — so the comparison has to
    resume past it rather than stop, and the ROM has to be inside what it compares."""
    from harness import diff_spans, in_diff
    assert diff_spans() == ((0, emu.STACK_GUARD_LO), (emu.STACK_BAND_HI, len(BASE_IMAGE)))
    assert in_diff(addrs.ROM_BASE) and in_diff(addrs.RANDOM_SEED)
    assert not in_diff(emu.STACK_TOP)


# ---- the dispatch tables: which function each reconstruction actually IS ---------------------------

def _trap_table(base):
    """``(count, [entry, ...])`` for a BIOS/XBIOS dispatch table in the mapped ROM."""
    count = int.from_bytes(bytes(BASE_IMAGE[base:base + addrs.TRAP_TABLE_COUNT_BYTES]), "big")
    entries = base + addrs.TRAP_TABLE_COUNT_BYTES
    return count, [int.from_bytes(bytes(BASE_IMAGE[at:at + addrs.TRAP_TABLE_ENTRY_BYTES]), "big")
                   for at in range(entries, entries + count * addrs.TRAP_TABLE_ENTRY_BYTES,
                                   addrs.TRAP_TABLE_ENTRY_BYTES)]


def test_the_xbios_dispatcher_reaches_the_two_reconstructed_functions():
    """WHICH FUNCTION each reconstruction is, read out of the ROM rather than asserted in a comment.

    `$fc1510` is XBIOS Random only because the XBIOS table's entry $11 says so, and every name and
    cycle count in this project's docs rests on that. Read from the mapped ROM, so a wrong address
    in `addrs.h` is a red here instead of a differential that proves some other routine correct.
    """
    count, entries = _trap_table(addrs.XBIOS_FUNCTION_TABLE)
    assert entries[addrs.XBIOS_RANDOM_FN] == addrs.XBIOS_RANDOM
    assert entries[addrs.XBIOS_GIACCESS_FN] == addrs.XBIOS_GIACCESS
    assert count > max(addrs.XBIOS_RANDOM_FN, addrs.XBIOS_GIACCESS_FN)


@pytest.mark.parametrize("table,vector", ((addrs.BIOS_FUNCTION_TABLE, "VECTOR_TRAP_BIOS"),
                                          (addrs.XBIOS_FUNCTION_TABLE, "VECTOR_TRAP_XBIOS")))
def test_a_dispatch_table_holds_entries_that_are_routines(table, vector):
    """The shape the dispatcher at `$fc07fc` reads: a count, then that many longwords, each either a
    ROM address or (bit 31 set) the address of a longword holding one — which is how Rwabs, Getbpb
    and Mediach reach a hard-disk driver in RAM. An entry that is neither means `addrs.h`'s table
    address is wrong, and every function number derived from it with it."""
    del vector                      # named in the parameter list so a failure says which table
    count, entries = _trap_table(table)
    assert 0 < count < 0x100, f"a {count}-entry dispatch table is not a dispatch table"
    for number, entry in enumerate(entries):
        if entry & addrs.TRAP_TABLE_INDIRECT:
            assert (entry & ~addrs.TRAP_TABLE_INDIRECT) < addrs.ST_RAM_BYTES, \
                f"entry {number:#x} is an indirect vector outside RAM"
        else:
            assert addrs.ROM_BASE <= entry < addrs.ROM_BASE + ROM_BYTES, \
                f"entry {number:#x} = {entry:#x} is neither a ROM routine nor an indirect vector"


# ---- the refusal that guards the mode itself -------------------------------------------------------

def test_a_run_that_reached_the_trap_model_is_refused_by_name():
    """Two of the three guards that let `_vet_os_memory_map` stop checking the TOS model's regions.

    No ordinary case can make either fire — the shim serves no traps in ROM mode and no verified
    function stores into the ROM, which is exactly what `recreate_kit/test/test_rom_mode.py` pins
    from C. So their own logic is exercised here instead, on a fabricated result: a guard that fires
    on nothing reachable is still a guard whose message and condition can rot.

    They are the ORACLE's rather than the differential's, because they hold of ANY run — a bare
    `emu.run` driving a boot included — and a run served by the model describes nothing about the
    ROM whoever made it. The third guard, the I/O-read refusal, is a differential's for Phase 7's
    reason and is driven by a real run below.
    """
    with pytest.raises(AssertionError, match="3 modelled TOS trap"):
        emu._vet_rom_mode_is_modelless(addrs.XBIOS_RANDOM, 3)
    emu._vet_rom_mode_is_modelless(addrs.XBIOS_RANDOM, 0)
    with pytest.raises(AssertionError, match="ROM window"):
        emu._vet_no_store_into_rom(addrs.XBIOS_RANDOM, 1)
    emu._vet_no_store_into_rom(addrs.XBIOS_RANDOM, 0)


def test_the_asm_twin_runner_refuses_this_project_by_name():
    """The kit's asm-twin runner is the one surface ROM mode is INCOMPATIBLE with rather than merely
    unused by: it stages the image at a non-zero base so that a twin addressing it absolutely is
    caught, and a transcription of ROM code is absolute by construction. Refused at construction,
    which is why nothing here needs an assembled blob."""
    from recreate_kit.asm_twin import AsmTwins
    with pytest.raises(RuntimeError, match="ROM MODE"):
        AsmTwins(Path(__file__).resolve().parents[1] / "build" / "asm", len(BASE_IMAGE))


# A two-instruction routine, planted in the free TPA: `move.b $ffff8260,d0` then `rts`. $ff8260 is
# the shifter's resolution byte — what XBIOS Getrez reads, and an address NO Phase-7 slot declares,
# so the oracle answers it 0 and both sides of a differential would agree about a byte the model
# invented. The routine is what makes that reachable from a case rather than only from a fixture.
SHIFTER_RESOLUTION = 0xFF8260
UNMODELLED_READ_AT = 0x70000            # clear of the desktop and of the oracle's stack band
UNMODELLED_READ_CODE = (b"\x10\x39" + SHIFTER_RESOLUTION.to_bytes(4, "big")   # move.b $ff8260,d0
                        + b"\x4e\x75")                                       # rts


def test_a_read_of_an_io_byte_no_model_serves_is_refused_by_name():
    """THE MODE'S SHARPEST LIMIT, closed: an undeclared I/O read refuses instead of answering 0.

    Driven by a real run rather than a fabricated result — the shim's tally, the two exported
    counters, `emu.run`'s report of them and the harness's refusal are one path, and only a run
    exercises all four. The routine is planted in RAM rather than found in the ROM because what is
    being pinned is the MODEL, not any particular TOS function: `Getrez` at $fc1b4c reads this same
    byte and will refuse the same way the day someone reconstructs it.
    """
    image = make_image({UNMODELLED_READ_AT: UNMODELLED_READ_CODE})
    _final, _writes, o_regs = emu.run(image, UNMODELLED_READ_AT, {"a5": 0})
    assert (o_regs["io_unmodeled_reads"], o_regs["io_unmodeled_first"]) == (1, SHIFTER_RESOLUTION), (
        "the oracle did not report the read of $ff8260 — a differential over a function that reads "
        "it would be verified against the 0 the shim fabricated")
    with pytest.raises(AssertionError, match=f"{SHIFTER_RESOLUTION:#x}"):
        _vet_rom_io_reads_are_modelled(UNMODELLED_READ_AT, o_regs)


def test_a_verified_function_reads_no_io_byte_the_model_does_not_serve():
    """...and the other direction, which is what makes the refusal above worth having: the two
    reconstructed functions reach only modelled addresses, so neither is verified against a
    fabrication. Random touches no hardware at all; Giaccess is served by the PSG model, which sits
    in front of the tally."""
    for name, entry, regs, pokes, psg_seed in VERIFIED_CASES:
        _final, _writes, o_regs = emu.run(make_image(pokes), entry, regs, psg_seed=psg_seed)
        assert o_regs["io_unmodeled_reads"] == 0, (
            f"{name} read {o_regs['io_unmodeled_reads']} unmodelled I/O byte(s), the first at "
            f"{o_regs['io_unmodeled_first']:#x}")


# ---- the mask, and what it is worth ---------------------------------------------------------------

# Every field a case READS or POKES, as whole spans. A mask region covering one would mean the
# recorded set and the machine have drifted apart — and the spans are what is checked rather than
# their first bytes, because a region starting one byte into the seed would cover three of its four
# and pass a first-byte test while leaving the case resting on noise.
CASE_FIELDS = ((addrs.RANDOM_SEED, 4, "the OS's random state"),
               (addrs.SYSVAR_HZ_200, 4, "_hz_200, the seeding branch's entropy"),
               (abi.FIRST_ARG, 4, "the argument words a case stages"))


def test_the_mask_is_inside_ram_and_clear_of_what_the_cases_use():
    """A mask region above RAM, or over a field a case reads or pokes, would mean the recorded set
    and the machine have drifted apart."""
    for address, length, name in boot_snapshot.MASK:
        assert address + length <= addrs.ST_RAM_BYTES, f"{name} is not in RAM"
        for at, width, what in CASE_FIELDS:
            assert max(address, at) >= min(address + length, at + width), (
                f"{name} covers {what} at [{at:#x}, {at + width:#x}), which a case uses")


def _scrambled_base(seed):
    """The snapshot with every masked region filled with pseudo-random bytes."""
    rng = random.Random(seed)
    image = make_image()
    for address, length, _ in boot_snapshot.MASK:
        image[address:address + length] = bytes(rng.randrange(256) for _ in range(length))
    return image


# EVERY FUNCTION THIS PROJECT HAS VERIFIED, entered the way its own battery enters it: the name, the
# entry, the input registers, the pokes that stage its arguments and the chip state it declares. The
# LIST is the point — a function added without a line here is one the mask stops covering — and it
# is a table rather than four calls because the case below runs each of them twice.
VERIFIED_CASES = (
    ("xbios_random, seeding branch", addrs.XBIOS_RANDOM, {"a5": 0}, {}, None),
    ("xbios_random, advance branch", addrs.XBIOS_RANDOM, {"a5": 0},
     xbios_random.seed_poke(0x1234_5678), None),
    ("xbios_giaccess, read", addrs.XBIOS_GIACCESS, {"a5": 0},
     giaccess.argument_poke(0, 3), giaccess.ENTRY_FILE),
    ("xbios_giaccess, write", addrs.XBIOS_GIACCESS, {"a5": 0},
     giaccess.argument_poke(0x5A, addrs.GIACCESS_WRITE_FLAG | 3), None),
)


def _oracle_outputs(base, case):
    """Everything the ORIGINAL leaves behind for one case run over `base`.

    Its registers at rts, the set of addresses it wrote, the bytes it left at them, and its ordered
    PSG access ledger — i.e. every surface a differential compares, gathered from the oracle alone.
    """
    _name, entry, regs, pokes, psg_seed = case
    previous = set_base_image(base)
    try:
        final, writes, out_regs = emu.run(make_image(pokes), entry, regs, psg_seed=psg_seed)
    finally:
        set_base_image(previous)
    written = sorted(set(writes))
    return ({name: out_regs[name] for name in emu.REPORTED_REGS},
            written, [final[a] for a in written], out_regs["psg_events"])


@pytest.fixture(scope="module")
def pristine_outputs():
    """What each verified case leaves over the snapshot exactly as it was captured."""
    return {case[0]: _oracle_outputs(BASE_IMAGE, case) for case in VERIFIED_CASES}


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_no_verified_function_depends_on_a_byte_the_capture_does_not_reproduce(seed,
                                                                               pristine_outputs):
    """THE CASE THE MASK EXISTS FOR. Two captures of the same boot disagree in those regions, so a
    function that read one would be verified against one particular boot and would flake against the
    next. Running the ORIGINAL over the snapshot and over a snapshot whose masked regions hold noise,
    and requiring the two to be indistinguishable, is what says none of them does.

    A differential could not ask this: it hands the SAME image to both cores, so a masked-byte
    dependence is fed to the reconstruction too and cancels. The oracle against itself cannot cancel.
    """
    scrambled = _scrambled_base(seed)
    for case in VERIFIED_CASES:
        name = case[0]
        assert _oracle_outputs(scrambled, case) == pristine_outputs[name], (
            f"{name} behaves differently over a snapshot whose masked regions hold noise, so it "
            f"reads a byte two captures of the same boot disagree about — its differential is "
            f"verified against one particular boot and will flake against the next. Find the read: "
            f"either the case must declare that byte, or the region does not belong in MASK.")
