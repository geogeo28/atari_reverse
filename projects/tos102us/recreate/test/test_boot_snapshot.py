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
import struct
import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import boot_snapshot                                      # noqa: E402

import test_bios_bconin as bconin                          # noqa: E402
import test_bios_bconstat as bconstat                      # noqa: E402
import test_bios_bcostat as bcostat                        # noqa: E402
import test_bios_getmpb as getmpb                          # noqa: E402
import test_bios_kbshift as kbshift                        # noqa: E402
import test_bios_setexc as setexc                          # noqa: E402
import test_xbios_getrez as getrez                         # noqa: E402
import test_xbios_giaccess as giaccess                     # noqa: E402
import test_xbios_iorec as xbios_iorec                     # noqa: E402
import test_xbios_kbrate as kbrate                         # noqa: E402
import test_xbios_keytbl as keytbl                         # noqa: E402
import test_xbios_protobt as protobt                       # noqa: E402
import test_xbios_random as xbios_random                   # noqa: E402
import test_xbios_supexec as supexec                       # noqa: E402

# The XBIOS screen and sound leaves (BIOS wave 2). `Vsync` is deliberately absent: its case needs a
# `schedule` and an entry here carries none — see test_xbios_vsync.py's docstring.
import test_xbios_dosound as dosound                        # noqa: E402
import test_xbios_offgibit as offgibit                      # noqa: E402
import test_xbios_ongibit as ongibit                        # noqa: E402
import test_xbios_physbase as physbase                      # noqa: E402
import test_xbios_setcolor as setcolor                      # noqa: E402
import test_xbios_setpalette as setpalette                  # noqa: E402
import test_xbios_setprt as setprt                          # noqa: E402
import test_xbios_setscreen as setscreen                    # noqa: E402
# The MFP / timer / IKBD / serial leaves (BIOS wave 2). `Mfpint` and `Xbtimer` are deliberately
# absent: each reads an MFP register back after storing to it, so neither can be run to its `rts`
# under the declared I/O map and both are proved as SLICES — an entry here carries no `stop_pc`.
# See test_xbios_mfpint.py and test_xbios_xbtimer.py, which measure both refusals.
import test_xbios_ikbdws as ikbdws                          # noqa: E402
import test_xbios_initmous as initmous                      # noqa: E402
import test_xbios_mfpint as mfpint                          # noqa: E402
import test_xbios_rsconf as rsconf                          # noqa: E402
import mfp                                                  # noqa: E402
# ...and the TRAP DISPATCHER's case-shape module, which is not a battery: its cases are proved
# through the transcription differential rather than through `harness.differential`, so what
# this file needs from it is the SPANS they read and poke (below), not a row in VERIFIED_CASES.
import trap                                                 # noqa: E402
# ...and the INTERRUPT HANDLERS (BIOS wave 2). `isr` is their shared case shape — the staged
# exception frame, the trampoline that enters one, and the spans below — rather than a battery.
import test_bios_hbl as hbl                                 # noqa: E402
import test_bios_ikbd as ikbd                               # noqa: E402
import test_bios_timerc as timerc                           # noqa: E402
import test_bios_vbl as vbl                                 # noqa: E402
import isr                                                  # noqa: E402

import abi                                                 # noqa: E402
import case                                                # noqa: E402
import iorec                                               # noqa: E402
import staging                                             # noqa: E402
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


def test_the_case_staging_band_is_dead_memory_in_this_snapshot():
    """`staging.SCRATCH` is where a case puts a buffer for a routine that takes a pointer — Getmpb's
    parameter block, Protobt's boot sector, Supexec's stub. Unlike the oracle's stack band it IS
    compared, so live bytes there would not be hidden; what they would do is make every such case a
    statement about the desktop's leftovers as well as about the routine. It shares the free TPA with
    Tier 3's bench blob at `bench_base`, and this is also where an overlap between the two would
    first be visible."""
    band = bytes(BASE_IMAGE[staging.SCRATCH:staging.SCRATCH + staging.SCRATCH_BYTES])
    assert band == bytes(len(band)), (
        f"the snapshot is not empty in [{staging.SCRATCH:#x}, "
        f"{staging.SCRATCH + staging.SCRATCH_BYTES:#x}) — move `staging.SCRATCH` to a band this "
        f"capture leaves clear, keeping it clear of `bench_base` and of the oracle's stack band")
    assert staging.SCRATCH + staging.SCRATCH_BYTES <= emu.STACK_GUARD_LO, (
        "the staging band runs into the oracle's stack band, whose bytes no case can see")


def test_the_diff_covers_everything_but_that_band():
    """A ROM project's image continues above the stack, unlike a .PRG's — so the comparison has to
    resume past it rather than stop, and the ROM has to be inside what it compares."""
    from harness import diff_spans, in_diff
    assert diff_spans() == ((0, emu.STACK_GUARD_LO), (emu.STACK_BAND_HI, len(BASE_IMAGE)))
    assert in_diff(addrs.ROM_BASE) and in_diff(addrs.RANDOM_SEED)
    assert not in_diff(emu.STACK_TOP)


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
# the shifter's resolution byte — what XBIOS Getrez reads, and an address NO Phase-7 slot names — so
# without a declaration the oracle answers it 0 and both sides of a differential would agree about a
# byte the model invented. The routine is what makes both halves of that reachable from a case
# rather than only from a fixture, and it is planted in RAM rather than found in the ROM because
# what is being pinned is the MODEL: `test_xbios_getrez.py` is where the real function is held to it.
UNMODELLED_READ_AT = 0x70000            # clear of the desktop and of the oracle's stack band
UNMODELLED_READ_CODE = (b"\x10\x39" + addrs.SHIFTER_RESOLUTION.to_bytes(4, "big")  # move.b ..,d0
                        + b"\x4e\x75")                                            # rts
DECLARED_RESOLUTION = 0x02              # not 0: the fabrication's own byte would prove nothing


def _run_the_planted_read(io_seed=None):
    """Run the planted `move.b $ff8260,d0` and return the oracle's report."""
    image = make_image({UNMODELLED_READ_AT: UNMODELLED_READ_CODE})
    _final, _writes, o_regs = emu.run(image, UNMODELLED_READ_AT, {"a5": 0}, io_seed=io_seed)
    return o_regs


def test_a_read_of_an_io_byte_no_model_serves_is_refused_by_name():
    """THE MODE'S SHARPEST LIMIT, and the first half of the pair: an UNDECLARED I/O read refuses
    instead of answering 0.

    Driven by a real run rather than a fabricated result — the shim's tally, the two exported
    counters, `emu.run`'s report of them and the harness's refusal are one path, and only a run
    exercises all four. The refusal must also PRESCRIBE the declaration that answers it: before the
    declared I/O map existed the only remedy was "a Phase-7 slot's worth of work", which is not
    something a reader can do inside the case they are writing.
    """
    o_regs = _run_the_planted_read()
    assert (o_regs["io_unmodeled_reads"],
            o_regs["io_unmodeled_first"]) == (1, addrs.SHIFTER_RESOLUTION), (
        "the oracle did not report the read of $ff8260 — a differential over a function that reads "
        "it would be verified against the 0 the shim fabricated")
    assert o_regs["d0"] == 0, "an undeclared read no longer answers the 0 every off-image read does"
    with pytest.raises(AssertionError, match=f"{addrs.SHIFTER_RESOLUTION:#x}") as raised:
        _vet_rom_io_reads_are_modelled(UNMODELLED_READ_AT, o_regs)
    assert "io_seed=" in str(raised.value), (
        "the refusal names no declaration that would answer it, so a reader who hits it has no move "
        "inside their own case")


def test_declaring_the_same_byte_serves_it_and_the_refusal_falls_silent():
    """...and the second half, over the IDENTICAL routine: declared, the byte is served, ledgered,
    and the refusal has nothing to fire on.

    The pair is what says the model is a model rather than a veto. Either half alone is compatible
    with a defect the other catches: a refusal nothing can satisfy would stop the BIOS wave dead,
    and a declaration nothing refuses would leave the fabricated 0 reachable by forgetting to write
    one (TRAP_MODEL.md, Phase 15).
    """
    o_regs = _run_the_planted_read({addrs.SHIFTER_RESOLUTION: DECLARED_RESOLUTION})
    assert o_regs["d0"] == DECLARED_RESOLUTION, (
        "the declared byte did not reach the instruction — the run read something else")
    assert o_regs["io_unmodeled_reads"] == 0, "a DECLARED read was still counted as unmodelled"
    assert o_regs["io_events"] == [(addrs.SHIFTER_RESOLUTION, 1, DECLARED_RESOLUTION)], (
        "the served read was not ledgered, so a reconstruction that skipped it would compare equal")
    _vet_rom_io_reads_are_modelled(UNMODELLED_READ_AT, o_regs)   # ...and the refusal stays silent


def test_a_verified_function_reads_no_io_byte_the_model_does_not_serve():
    """...and the other direction, which is what makes the refusal above worth having: the two
    reconstructed functions reach only modelled addresses, so neither is verified against a
    fabrication. Random touches no hardware at all; Giaccess is served by the PSG model, which sits
    in front of the tally."""
    for name, entry, regs, pokes, psg_seed, io_seed in VERIFIED_CASES:
        _final, _writes, o_regs = emu.run(make_image(pokes), entry, regs, psg_seed=psg_seed,
                                          io_seed=io_seed)
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
               (abi.FIRST_ARG, 12, "the argument words a case stages (Protobt's frame is widest)"),
               (addrs.SYSVAR_TIMR_MS, 2, "the system-timer calibration Tickcal reports"),
               (addrs.SYSVAR_DRVBITS, 4, "the drive bitmap Drvmap reports"),
               (addrs.SYSVAR_V_BAS_AD, 4, "the screen base Logbase reports"),
               (addrs.SYSVAR_MEMBOT, 8, "_membot and _memtop, the TPA Getmpb describes"),
               (addrs.OS_MEMORY_DESCRIPTOR, 16, "the memory descriptor Getmpb rebuilds"),
               (addrs.KBSHIFT, 1, "the keyboard shift state"),
               (addrs.KEYTBL_STRUCT, 12, "the three keyboard-table pointers"),
               (addrs.KBRATE_DELAY, 2, "the auto-repeat delay and interval"),
               (addrs.CON_BLINK_RATE, 1, "the cursor blink rate Cursconf reports"),
               (addrs.CON_STATE_FLAGS, 2, "the console flags and spare byte Cursconf edits"),
               (addrs.XCONSTAT_TABLE, 4 * 4 * addrs.XCON_TABLE_DEVICES,
                "the four BIOS character-device vector tables"),
               (addrs.IOREC_RS232, 14, "the RS232 IOREC Bconstat walks"),
               (addrs.IOREC_IKBD, 14, "the IKBD IOREC Bconstat and Bconin walk"),
               (iorec.buffer_of(addrs.IOREC_IKBD), iorec.size_of(addrs.IOREC_IKBD),
                "the IKBD ring a Bconin case stages a key in"),
               (addrs.IOREC_MIDI, 14, "the MIDI IOREC Bconstat and Bconin walk"),
               (iorec.buffer_of(addrs.IOREC_MIDI), iorec.size_of(addrs.IOREC_MIDI),
                "the MIDI ring a Bconin case stages a byte in"),
               (getmpb.ALIASED_MPB, getmpb.MPB_BYTES,
                "the MPB a Getmpb case lays over the system variables"),
               (staging.SCRATCH, staging.SCRATCH_BYTES, "the band a case stages buffers in"),
               (addrs.MFP_VECTOR_TABLE, (addrs.MFP_CHANNEL_MASK + 1) * addrs.VECTOR_BYTES,
                "the MFP's sixteen interrupt vectors Mfpint installs into"),
               (addrs.KBDVECS, addrs.KBDVECS_LONGWORDS * addrs.VECTOR_BYTES,
                "KBDVECS, which Kbdvbase reports and Initmous installs `mousevec` into"),
               (addrs.INITMOUS_PACKET, addrs.INITMOUS_ABSOLUTE_COUNT + 1,
                "the IKBD command buffer Initmous builds its packet in"),
               (addrs.RSCONF_FLOW_CONTROL, 1, "the RS232 handshake byte Rsconf keeps"),
               # The vector table AND each individual slot the out-of-range cases reach, declared by
               # the battery itself: they are scattered from $400 to $7ffc with masked regions in
               # between, so one span over the lot would claim bytes no case here touches.
               # The XBIOS screen and sound leaves (BIOS wave 2).
               (addrs.SYSVAR_COLORPTR, 4, "the palette pointer Setpalette hands the VBL"),
               (addrs.SYSVAR_FRCLOCK, 4, "the frame clock Vsync spins on"),
               (addrs.SOUND_LIST_POINTER, 5, "the 200 Hz driver's cursor and tick countdown"),
               (addrs.PRINTER_CONFIG, 2, "the printer configuration Setprt keeps"),
               *setexc.CASE_SPANS,
               # ...and the trap dispatcher's, which are the machine's own rather than a buffer a
               # case owns: savptr, the frame the dispatcher pushes below it, and the RAM vector the
               # dispatch table's INDIRECT entry reaches (`test/trap.py`).
               (addrs.SYSVAR_SAVPTR, 4, "savptr, the top of the BIOS's register-save area"),
               (trap.FRAME_AT, addrs.TRAP_SAVE_FRAME_BYTES,
                "the frame the trap dispatcher pushes into that area"),
               (addrs.HDV_RWABS, 4, "hdv_rw, the vector the INDIRECT dispatch-table entry follows"),
               # ...and the interrupt handlers', which `test/isr.py` owns because the four share
               # most of them (its CASE_SPANS says which are already declared above).
               *isr.CASE_SPANS)


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
# entry, the input registers, the pokes that stage its arguments, the chip state it declares and the
# I/O bytes it declares. The LIST is the point — a function added without a line here is one the
# mask stops covering — and it is a table rather than a call apiece because the case below runs each
# of them twice.
VERIFIED_CASES = (
    ("xbios_random, seeding branch", addrs.XBIOS_RANDOM, {"a5": 0}, {}, None, None),
    ("xbios_random, advance branch", addrs.XBIOS_RANDOM, {"a5": 0},
     xbios_random.seed_poke(0x1234_5678), None, None),
    ("xbios_giaccess, read", addrs.XBIOS_GIACCESS, {"a5": 0},
     giaccess.argument_poke(0, 3), giaccess.ENTRY_FILE, None),
    ("xbios_giaccess, write", addrs.XBIOS_GIACCESS, {"a5": 0},
     giaccess.argument_poke(0x5A, addrs.GIACCESS_WRITE_FLAG | 3), None, None),
    ("xbios_getrez", addrs.XBIOS_GETREZ, {"a5": 0}, {}, None,
     {addrs.SHIFTER_RESOLUTION: getrez.ST_HIGH}),
    ("bios_drvmap", addrs.BIOS_DRVMAP, {"a5": 0}, {}, None, None),
    ("bios_tickcal", addrs.BIOS_TICKCAL, {"a5": 0}, {}, None, None),
    ("xbios_logbase", addrs.XBIOS_LOGBASE, {"a5": 0}, {}, None, None),
    ("bios_kbshift, read", addrs.BIOS_KBSHIFT, {"a5": 0}, kbshift.argument_poke(-1), None, None),
    ("bios_kbshift, write", addrs.BIOS_KBSHIFT, {"a5": 0},
     kbshift.argument_poke(kbshift.CONTROL), None, None),
    ("bios_getmpb", addrs.BIOS_GETMPB, {"a5": 0}, getmpb.argument_poke(getmpb.MPB_AT), None, None),
    ("bios_setexc, read", addrs.BIOS_SETEXC, {"a5": 0},
     setexc.argument_poke(2, setexc.READ_ONLY), None, None),
    ("bios_setexc, install", addrs.BIOS_SETEXC, {"a5": 0},
     setexc.argument_poke(2, setexc.A_HANDLER), None, None),
    ("bios_bconstat, console ring empty", addrs.BIOS_BCONSTAT,
     {"a5": 0, "d0": bconstat.ENTRY_D0}, case.word_arg(bconstat.DEVICE_CONSOLE),
     None, None),
    ("bios_bconstat, console ring ready", addrs.BIOS_BCONSTAT,
     {"a5": 0, "d0": bconstat.ENTRY_D0},
     {**case.word_arg(bconstat.DEVICE_CONSOLE),
      **iorec.staged(addrs.IOREC_IKBD, 0, addrs.IOREC_KEY_BYTES)}, None, None),
    ("bios_bconstat, no driver", addrs.BIOS_BCONSTAT, {"a5": 0, "d0": bconstat.ENTRY_D0},
     case.word_arg(4), None, None),
    ("bios_bconin, console", addrs.BIOS_BCONIN, {"a5": 0, "d0": bconin.ENTRY_D0},
     {**case.word_arg(bconin.DEVICE_CONSOLE),
      **iorec.staged(addrs.IOREC_IKBD, 0, addrs.IOREC_KEY_BYTES,
                     [(addrs.IOREC_KEY_BYTES, struct.pack(">I", bconin.A_KEY))])}, None, None),
    ("bios_bconin, midi", addrs.BIOS_BCONIN, {"a5": 0, "d0": bconin.ENTRY_D0},
     {**case.word_arg(bconin.DEVICE_MIDI),
      **iorec.staged(addrs.IOREC_MIDI, 0, addrs.IOREC_MIDI_BYTES,
                     [(addrs.IOREC_MIDI_BYTES, b"\x42")])}, None, None),
    ("bios_bcostat, console", addrs.BIOS_BCOSTAT, {"a5": 0, "d0": bcostat.ENTRY_D0},
     case.word_arg(bcostat.DEVICE_CONSOLE), None, None),
    ("xbios_iorec", addrs.XBIOS_IOREC, {"a5": 0},
     case.word_arg(xbios_iorec.DEVICE_IKBD), None, None),
    ("xbios_keytbl, install", addrs.XBIOS_KEYTBL, {"a5": 0},
     keytbl.argument_poke(keytbl.STAGED), None, None),
    ("xbios_bioskeys", addrs.XBIOS_BIOSKEYS, {"a5": 0}, {}, None, None),
    ("xbios_kbrate, read", addrs.XBIOS_KBRATE, {"a5": 0},
     case.word_args(kbrate.KEEP, kbrate.KEEP), None, None),
    ("xbios_kbrate, write", addrs.XBIOS_KBRATE, {"a5": 0},
     case.word_args(0x20, 0x03), None, None),
    ("xbios_cursconf, blink", addrs.XBIOS_CURSCONF, {"a5": 0},
     case.word_args(addrs.CURSCONF_BLINK, 0), None, None),
    ("xbios_cursconf, get rate", addrs.XBIOS_CURSCONF, {"a5": 0},
     case.word_args(addrs.CURSCONF_GET_RATE, 0), None, None),
    ("xbios_supexec", addrs.XBIOS_SUPEXEC, {"a5": 0},
     {abi.FIRST_ARG: struct.pack(">I", supexec.STUB_AT),
      supexec.STUB_AT: supexec.move_long_immediate_to_d0(supexec.A_RESULT) + supexec.RTS},
     None, None),
    ("xbios_protobt, format", addrs.XBIOS_PROTOBT, {"a5": 0},
     {**protobt.argument_poke(protobt.BUFFER_AT, 0x00ABCDEF, 3, 1),
      protobt.BUFFER_AT: bytes(addrs.BOOT_SECTOR_BYTES)}, None, None),
    ("xbios_protobt, random serial", addrs.XBIOS_PROTOBT, {"a5": 0},
     {**protobt.argument_poke(protobt.BUFFER_AT, 0x01000000, 0, 1),
      protobt.BUFFER_AT: bytes(addrs.BOOT_SECTOR_BYTES)}, None, None),

    # ---- the XBIOS screen and sound leaves (BIOS wave 2) ----
    ("xbios_physbase", addrs.XBIOS_PHYSBASE, {"a5": 0}, {}, None,
     physbase.register_pair(physbase.SNAPSHOT_BASE)),
    # The four `"d0": 0` below are the entering D0 these routines hand BACK (`bench/tier3.py`'s
    # ENTRY_D0 reads it from here): none of them writes the register, so the value is part of the
    # case rather than a default.
    ("xbios_setscreen, both bases", addrs.XBIOS_SETSCREEN, {"a5": 0, "d0": 0},
     setscreen.argument_poke(setscreen.ANOTHER_BASE, 0x00ABCDEF, setscreen.KEEP_WORD), None, None),
    ("xbios_setscreen, keep everything", addrs.XBIOS_SETSCREEN, {"a5": 0, "d0": 0},
     setscreen.argument_poke(setscreen.KEEP_LONG, setscreen.KEEP_LONG, setscreen.KEEP_WORD),
     None, None),
    ("xbios_setpalette", addrs.XBIOS_SETPALETTE, {"a5": 0, "d0": 0},
     setpalette.argument_poke(0x000A_0000), None, None),
    ("xbios_setcolor, read", addrs.XBIOS_SETCOLOR, {"a5": 0, "d0": 0},
     case.word_args(3, setcolor.KEEP), None,
     setcolor.declared(setcolor.register_of(3), setcolor.ENTRY_ROW[setcolor.register_of(3)])),
    ("xbios_setcolor, write", addrs.XBIOS_SETCOLOR, {"a5": 0, "d0": 0},
     case.word_args(3, 0x0246), None,
     setcolor.declared(setcolor.register_of(3), setcolor.ENTRY_ROW[setcolor.register_of(3)])),
    ("xbios_ongibit", addrs.XBIOS_ONGIBIT, {"a5": 0, "d0": 0}, case.word_arg(0x04),
     ongibit.ENTRY_FILE, None),
    ("xbios_offgibit", addrs.XBIOS_OFFGIBIT, {"a5": 0, "d0": 0}, case.word_arg(0xEF),
     offgibit.ENTRY_FILE, None),
    ("xbios_dosound, play", addrs.XBIOS_DOSOUND, {"a5": 0},
     {**dosound.argument_poke(0x000A_1234),
      **dosound.state_poke(dosound.SNAPSHOT_LIST, dosound.A_PENDING_DELAY)}, None, None),
    ("xbios_dosound, report only", addrs.XBIOS_DOSOUND, {"a5": 0},
     {**dosound.argument_poke(dosound.KEEP),
      **dosound.state_poke(dosound.SNAPSHOT_LIST, dosound.A_PENDING_DELAY)}, None, None),
    ("xbios_setprt, write", addrs.XBIOS_SETPRT, {"a5": 0, "d0": 0},
     {**case.word_arg(0x0055), **setprt.config_poke(setprt.SNAPSHOT_CONFIG)}, None, None),
    ("xbios_setprt, report only", addrs.XBIOS_SETPRT, {"a5": 0, "d0": 0},
     {**case.word_arg(setprt.KEEP), **setprt.config_poke(setprt.SNAPSHOT_CONFIG)}, None, None),
    ("xbios_jdisint", addrs.XBIOS_JDISINT, {"a5": 0},
     mfpint.channel_arg(mfpint.CHANNEL_TIMER_C), None, mfp.seed()),
    ("xbios_jenabint", addrs.XBIOS_JENABINT, {"a5": 0},
     mfpint.channel_arg(mfpint.CHANNEL_TIMER_C), None, mfp.seed()),
    ("xbios_ikbdws", addrs.XBIOS_IKBDWS, {"a5": 0},
     {**ikbdws.frame(1, ikbdws.BYTES_AT), ikbdws.BYTES_AT: b"\x80\x01"}, None, ikbdws.ready(addrs.XBIOS_IKBDWS)),
    ("xbios_midiws", addrs.XBIOS_MIDIWS, {"a5": 0},
     {**ikbdws.frame(1, ikbdws.BYTES_AT), ikbdws.BYTES_AT: b"\x90\x40"}, None, ikbdws.ready(addrs.XBIOS_MIDIWS)),
    ("xbios_kbdvbase", addrs.XBIOS_KBDVBASE, {"a5": 0}, {}, None, None),
    ("xbios_initmous, disable", addrs.XBIOS_INITMOUS, {"a5": 0},
     {**initmous.frame(addrs.INITMOUS_DISABLE), initmous.PARAM_AT: initmous.PARAM}, None,
     dict(initmous.READY)),
    ("xbios_initmous, absolute", addrs.XBIOS_INITMOUS, {"a5": 0},
     {**initmous.frame(addrs.INITMOUS_ABSOLUTE), initmous.PARAM_AT: initmous.PARAM}, None,
     dict(initmous.READY)),
    ("xbios_rsconf, report", addrs.XBIOS_RSCONF, {"a5": 0}, rsconf.frame(), None,
     dict(rsconf.USART_ENTRY)),
    ("xbios_rsconf, store four", addrs.XBIOS_RSCONF, {"a5": 0},
     rsconf.frame(ucr=0x11, rsr=0x22, tsr=0x33, scr=0x44), None, dict(rsconf.USART_ENTRY)),
    # THE INTERRUPT HANDLERS (BIOS wave 2), whose rows their own batteries build: each is a case
    # SPEC (`isr.registered`) that the battery also runs as a differential, so a row here cannot
    # come to describe a run nobody verified. Their `entry` is a TRAMPOLINE in the staging band
    # rather than a ROM address — nothing calls a handler, so a case has to stage the exception
    # frame its `rte` returns through (`test/isr.py`).
    *hbl.VERIFIED_CASES,
    *vbl.VERIFIED_CASES,
    *timerc.VERIFIED_CASES,
    *ikbd.VERIFIED_CASES,
)


def _oracle_outputs(base, case):
    """Everything the ORIGINAL leaves behind for one case run over `base`.

    Its registers at rts, the set of addresses it wrote, the bytes it left at them, and its ordered
    PSG access ledger — i.e. every surface a differential compares, gathered from the oracle alone.
    """
    _name, entry, regs, pokes, psg_seed, io_seed = case
    previous = set_base_image(base)
    try:
        final, writes, out_regs = emu.run(make_image(pokes), entry, regs, psg_seed=psg_seed,
                                          io_seed=io_seed)
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


# ---- the dispatch tables: which function each reconstruction actually IS ---------------------------
# Below VERIFIED_CASES because it is DERIVED from it: every function a case here enters must be the
# dispatch-table entry `addrs.h` says it is, and that set is the table above rather than a copy.

def _trap_table(base):
    """``(count, [entry, ...])`` for a BIOS/XBIOS dispatch table in the mapped ROM."""
    count = int.from_bytes(bytes(BASE_IMAGE[base:base + addrs.TRAP_TABLE_COUNT_BYTES]), "big")
    entries = base + addrs.TRAP_TABLE_COUNT_BYTES
    return count, [int.from_bytes(bytes(BASE_IMAGE[at:at + addrs.TRAP_TABLE_ENTRY_BYTES]), "big")
                   for at in range(entries, entries + count * addrs.TRAP_TABLE_ENTRY_BYTES,
                                   addrs.TRAP_TABLE_ENTRY_BYTES)]


# Every BIOS/XBIOS routine `addrs.h` names, as {entry address: the constant that names it}. A trap
# routine is exactly a constant with a `<NAME>_FN` sibling, which is the pair the case below reads
# out of the ROM: a routine is "XBIOS Random" only because the XBIOS table's entry $11 says so, and
# every name, cycle count and STATUS row rests on that.
TRAP_ROUTINE_NAMES = {getattr(addrs, name): name
                      for name in dir(addrs) if hasattr(addrs, f"{name}_FN")}

# ...and the ones this project has VERIFIED, DERIVED from VERIFIED_CASES rather than listed beside
# it. The two lists had already drifted — Getrez is in that table and had no line here, so nothing
# checked that the routine it verifies is XBIOS function $04 — and a second list of the same set is
# exactly the shape that goes stale.
# An INTERRUPT HANDLER is not in either dispatch table and has no function number — nothing calls
# it, the machine dispatches it — so the entries `TRAP_ROUTINE_NAMES` does not name are skipped
# rather than looked up. What holds one to the right address is its VECTOR, which its own battery
# reads out of the captured table (`test_the_vector_table_still_points_at_this_handler`).
RECONSTRUCTED_TRAP_ROUTINES = sorted(
    {((addrs.XBIOS_FUNCTION_TABLE if TRAP_ROUTINE_NAMES[entry].startswith("XBIOS_")
       else addrs.BIOS_FUNCTION_TABLE), TRAP_ROUTINE_NAMES[entry])
     for _name, entry, *_rest in VERIFIED_CASES if entry in TRAP_ROUTINE_NAMES})


@pytest.mark.parametrize("table,name", RECONSTRUCTED_TRAP_ROUTINES)
def test_a_reconstruction_is_the_dispatch_table_entry_it_claims_to_be(table, name):
    """Read from the mapped ROM, so a wrong address in `addrs.h` is a red here instead of a
    differential that quietly proves some other routine correct."""
    number = getattr(addrs, f"{name}_FN")
    count, entries = _trap_table(table)
    assert count > number, f"{name}'s function number is past the table's own count"
    assert entries[number] == getattr(addrs, name)


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
