"""The machinery under the AES's recorded and replayed GEMDOS, held on itself.

`aes_shell.Table`: the two tables a recording `trap #1` handler walks — its ledger and its script — as every battery's
host twin stages, bounds, records, steps and reads them back (`aes_shell`'s scripted trap, `aes_fslib`'s GEMDOS
replay): over a candidate image as a twin is handed one, a C pointer. Then what `aes_fslib` keeps of a run's memory
(its RAM, the rest held unchanged by name), and the budget its in-process runs are capped at and held to."""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, make_image

import aes_event
import aes_fslib as fsl
import aes_shell as sh
import vdi

LONG_BYTES, WORD_BYTES = sh.LONG_BYTES, sh.WORD_BYTES
TABLES = {"the scripted trap's ledger": sh.LEDGER, "the scripted trap's script": sh.SCRIPT,
          "the replay's ledger": fsl.LEDGER, "the replay's script": fsl.SCRIPT}
FRAME_AT = sh.BAND_AT                   # where a call's frame is staged for the twin to record from
FUNCTION = 0x4E


def _candidate(pokes):
    """`pokes` over the snapshot as a host twin is handed the candidate's image: a C pointer to its bytes."""
    staged = bytes(make_image(pokes))
    image = (ctypes.c_uint8 * len(staged)).from_buffer_copy(staged)
    return ctypes.cast(image, ctypes.POINTER(ctypes.c_uint8)), image


@pytest.mark.parametrize("table", TABLES.values(), ids=TABLES)
def test_a_table_is_staged_with_its_pointer_at_its_first_entry_and_filled_to_its_end(table):
    content = bytes(range(1, table.stride + 1))
    (at, staged), = table.staged(content).items()
    assert at == table.pointer_at and table.first == at + LONG_BYTES
    assert staged[:LONG_BYTES] == struct.pack(">I", table.first)
    assert staged[LONG_BYTES:] == content + bytes([vdi.FILL]) * ((table.entries - 1) * table.stride)
    with pytest.raises(AssertionError, match="too few"):
        table.staged(bytes(table.entries * table.stride + 1))


@pytest.mark.parametrize("table", TABLES.values(), ids=TABLES)
def test_a_twin_refuses_a_pointer_outside_its_table_and_steps_one_inside_it(table):
    """THE BOUND, both ends, to the entry: the last entry is taken and stepped past; a pointer one entry past it, one
    byte below the first, or one byte inside it (between two entries) is refused by name before anything is stored
    through it."""
    last = table.first + (table.entries - 1) * table.stride
    buf, image = _candidate({table.pointer_at: struct.pack(">I", last)})
    assert table.next(buf) == last
    table.step(buf, last)
    assert bytes(image[table.pointer_at:table.pointer_at + LONG_BYTES]) == struct.pack(">I", last + table.stride)
    with pytest.raises(AssertionError, match=rf"the {table.what}'s pointer {last + table.stride:#x} is outside it"):
        table.next(buf)
    below, _image = _candidate({table.pointer_at: struct.pack(">I", table.first - 1)})
    with pytest.raises(AssertionError, match="is outside it: the twin refuses it"):
        table.next(below)
    inside, _image = _candidate({table.pointer_at: struct.pack(">I", table.first + 1)})
    with pytest.raises(AssertionError, match=rf"the {table.what}'s pointer {table.first + 1:#x} is between two of its "
                                             rf"entries: the twin refuses it"):
        table.next(inside)
    first, _image = _candidate(table.staged())
    assert table.next(first) == table.first


@pytest.mark.parametrize("ledger", (sh.LEDGER, fsl.LEDGER), ids=("the scripted trap's", "the replay's"))
@pytest.mark.parametrize("frame_bytes", (0, WORD_BYTES, LONG_BYTES))
def test_a_ledger_records_a_call_padded_and_reads_it_back(ledger, frame_bytes):
    """A call recorded: the function word, `frame_bytes` of its frame, zeros to the entry's end — nothing of what lies
    above a shorter frame — the pointer stepped; two calls read back in order, as `frame` spells one."""
    above = bytes(range(0x11, 0x11 + ledger.stride))
    buf, image = _candidate({**ledger.staged(), FRAME_AT: above})
    kept = above[:frame_bytes].ljust(ledger.stride - WORD_BYTES, b"\0")
    assert ledger.record(buf, ledger.next(buf), FUNCTION, FRAME_AT, frame_bytes) == kept
    assert ledger.record(buf, ledger.next(buf), FUNCTION + 1, FRAME_AT, frame_bytes) == kept
    assert ledger.recorded(image) == [(FUNCTION, kept), (FUNCTION + 1, kept)]
    assert image[ledger.first + 2 * ledger.stride] == vdi.FILL, "the third entry is as staged"
    fields = {0: (), WORD_BYTES: (("w", 0x1112),), LONG_BYTES: (("l", 0x1112_1314),)}[frame_bytes]
    assert ledger.frame(*fields) == kept


@pytest.mark.parametrize("ledger", (sh.LEDGER, fsl.LEDGER), ids=("the scripted trap's", "the replay's"))
def test_a_ledger_whose_pointer_names_no_entry_is_not_read_back(ledger):
    """A run's ledger is read only off a pointer ON an entry, up to the one past the last: between two, or past that,
    it is refused in words."""
    _buf, image = _candidate({ledger.pointer_at: struct.pack(">I", ledger.first + 1)})
    with pytest.raises(AssertionError, match=rf"the {ledger.what}'s pointer {ledger.first + 1:#x} is between two of its "
                                             rf"entries: no ledger can be read off it"):
        ledger.recorded(image)
    past = ledger.first + (ledger.entries + 1) * ledger.stride
    _buf, image = _candidate({ledger.pointer_at: struct.pack(">I", past)})
    with pytest.raises(AssertionError, match=rf"the {ledger.what}'s pointer {past:#x} is outside it: no ledger"):
        ledger.recorded(image)
    _buf, image = _candidate({ledger.pointer_at: struct.pack(">I", past - ledger.stride)})
    assert len(ledger.recorded(image)) == ledger.entries


# ---- what is kept of a run's memory: its RAM (`aes_fslib.ram_in`) ------------------------------------------------------------
def test_a_run_s_ram_is_kept_and_the_whole_image_put_back():
    """A megabyte kept of sixteen, and the image whole again under the snapshot's ROM and hardware page."""
    image = make_image({fsl.PATH_AT: b"kept"})
    ram = fsl.ram_in(image)
    assert len(ram) == fsl.RAM_BYTES and ram == bytes(image[:fsl.RAM_BYTES]) and fsl.whole_image(ram) == image


@pytest.mark.parametrize("kept_as", (bytearray, bytes), ids=("a run's own buffer", "a run's final image"))
@pytest.mark.parametrize("at", (fsl.RAM_BYTES, len(BASE_IMAGE) - 1), ids=("the first byte above RAM", "the image's last"))
def test_a_run_that_changed_a_byte_above_its_ram_is_not_kept_short(at, kept_as):
    """THE RED: what is dropped must be the snapshot's — a memory that differs anywhere above RAM is refused by name,
    whichever way it is compared (in place, a run's own buffer; copied out, any other)."""
    image = make_image()
    assert fsl.ram_in(kept_as(image)) == bytes(image[:fsl.RAM_BYTES])
    image[at] ^= 0xFF
    with pytest.raises(AssertionError, match="the run changed memory above the machine's RAM"):
        fsl.ram_in(kept_as(image))


@pytest.mark.parametrize("kept_as", (bytearray, bytes), ids=("a run's own buffer", "a run's final image"))
def test_a_memory_that_is_not_the_whole_image_is_not_kept_short(kept_as):
    """...and so is one of another LENGTH, every byte it has the snapshot's: a byte short, nothing says its last is."""
    pristine = make_image()
    with pytest.raises(AssertionError, match=rf"a memory of {len(pristine) - 1} bytes is not the whole image"):
        fsl.ram_in(kept_as(pristine[:-1]))


# ---- the cap the battery's in-process runs are under (`aes_fslib.RUN_CAP`) --------------------------------------------------
def _the_longest_run(**kwargs):
    """fs_newdir over the 101-name folder, the cursor shown: the run RUN_MEASURED_INSNS is the measure of."""
    machine, frame = fsl.entered(fsl.NEWDIR, "A:\\BIG\\*.*", shown=True)
    return fsl.run(fsl.NEWDIR, fsl.newdir_arguments(frame), machine, **kwargs)


def test_the_battery_s_run_cap_is_declared_from_its_longest_run_and_holds_it():
    """ONE BUDGET MECHANISM: RUN_CAP is a battery's cap as `aes_event` declares one — from the longest run measured,
    which needs it, five times that and no more than ten — and that run passes under it, spending what was measured."""
    assert fsl.RUN_CAP == aes_event.battery_cap(fsl.RUN_CAP.insns, deepest=fsl.RUN_MEASURED_INSNS)
    assert _the_longest_run().info["regs"]["ninsns"] == fsl.RUN_MEASURED_INSNS


def _a_battery_s_cap(insns):
    """A battery's cap of `insns` declared from a run as deep as it admits: what a battery holds once a deeper one comes."""
    return aes_event.battery_cap(insns, deepest=insns // aes_event.DERIVATION_MARGIN)


def test_a_run_inside_the_battery_s_cap_s_margin_is_refused_by_name(monkeypatch):
    """THE RED: the same run under a battery's cap one instruction short of five times its spend is refused in the
    battery's cap's own words."""
    short = fsl.RUN_MEASURED_INSNS * aes_event.DERIVATION_MARGIN - 1
    monkeypatch.setattr(fsl, "RUN_CAP", _a_battery_s_cap(short))
    with pytest.raises(AssertionError, match=rf"inside its battery's declared cap's \({short}\) margin of 5: raise the "
                                             rf"battery's cap to at least {short + 1}"):
        _the_longest_run()


def test_a_run_capped_by_its_own_case_is_held_to_that_number_both_ways():
    """...and capped by its own case at another number, THAT number is held, as any case's cap is (the door is one,
    whichever number comes through it): one instruction inside the margin is refused, and one past ten times the spend
    is stale; five times it passes."""
    least = fsl.RUN_MEASURED_INSNS * aes_event.DERIVATION_MARGIN
    assert _the_longest_run(cap=least).info["regs"]["ninsns"] == fsl.RUN_MEASURED_INSNS
    with pytest.raises(AssertionError, match=rf"inside its declared cap's \({least - 1}\) margin of 5: raise the case's cap"):
        _the_longest_run(cap=least - 1)
    most = least * aes_event.DERIVATION_STALE
    with pytest.raises(AssertionError, match=rf"declares a cap of {most + 1} instructions .*the declaration is stale"):
        _the_longest_run(cap=most + 1)


@pytest.mark.parametrize("run", (fsl.run, fsl.run_replayed), ids=("over real GEMDOS", "over GEMDOS replayed"))
def test_a_raw_instruction_cap_handed_past_the_door_is_refused_by_name(run):
    """THE DOOR IS ONE: `max_insns`, the oracle's own spelling, is no way round the cap's rules — refused before any run."""
    machine, frame = fsl.replayed(fsl.NEWDIR, "A:\\ONE\\*.*")
    with pytest.raises(AssertionError, match=r"a raw max_insns \(3000000\) was handed past the cap's door"):
        run(fsl.NEWDIR, fsl.newdir_arguments(frame), machine, max_insns=3_000_000)
