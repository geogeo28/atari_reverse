"""THE FREE WINDOW'S CUT (band 6, slice W): where the blob may grow, and what refuses it when it grows too far.

The captured machine's free TPA holds the blob at `bench_base`, growing upward with the reconstruction, and above it
every span a battery stages in. `project.toml` declares THREE of the tenants — the blob's base, the case staging band,
the oracle's stack — and `RomBench._vet_tenancy` (the kit's) refuses an overlap between those three, by name, each
time a blob is loaded. It knows none of the others: the VDI's and the AES's staged windows, the file system's RAM
disk, a battery's arena. A blob linked over one of THOSE would be overwritten by a case's own pokes, or overwrite
them, and every differential would still be two runs of one machine.

So the cut is made such that ONE refusal covers all of it, and this file holds the two halves:

  * THE DECLARED STAGING BAND IS THE LOWEST TENANT ABOVE THE BLOB — no span any battery registers
    (`staging.Registry.ALL`) starts below it, so a blob that reaches any of them has crossed the band first;
  * A BLOB LINKED PAST THE BAND IS REFUSED BY NAME WHERE IT IS LOADED — driven, not read: a blob really linked from
    `bench_base` to two bytes past the band's floor, handed to the constructor every blob user goes through.

What is NOT held here is a number of bytes of room: the blob's end is the build's, and pinning it would red on every
routine landed.
"""
import subprocess

import pytest

from harness import BASE_IMAGE, emu, project
from recreate_kit import rom_bench

import aes
import gemdos_fs
import staging
import vdi

THE_BAND_S_NAME_IN_THE_KIT = "the case staging band (`staging_base`)"
PAD_SOURCE = "\t.text\n\t.globl\tpad\npad:\t.space\t{bytes}\n"
BYTES_PAST_THE_FLOOR = 2            # the least a 68000's blob can cross it by: a word


def _linked(directory, end):
    """A blob REALLY LINKED at `bench_base` that ends at `end`, as kit.mk links one: `directory` with its ELF and its
    flat binary. All padding — the constructor refuses on the span before it runs an instruction of it."""
    base = project.current().bench_base
    directory.mkdir()
    source, elf = directory / "pad.S", directory / rom_bench.BENCH_ELF
    source.write_text(PAD_SOURCE.format(bytes=end - base))
    subprocess.run(["m68k-elf-gcc", "-nostdlib", "-Wl,--build-id=none", "-Wl,-e0", f"-Wl,-Ttext={base:#x}", str(source), "-o", str(elf)],
                   check=True, capture_output=True)
    subprocess.run(["m68k-elf-objcopy", "-O", "binary", str(elf), str(directory / rom_bench.BENCH_BIN)], check=True)
    return directory


def test_the_declared_band_is_the_lowest_tenant_above_the_blob():
    """Every registered span starts at or above the declared band's floor — this module imports the three windows'
    modules itself, and under a whole collection `Registry.ALL` holds every battery's."""
    config = project.current()
    assert {staging.SCRATCH_BANDS, staging.HIGH_BANDS, vdi.SPAN, aes.SPAN, gemdos_fs.SPAN} <= set(staging.Registry.ALL)
    assert config.bench_base < config.staging_base == staging.SCRATCH_BANDS.lo
    below = [f"{span.label} [{span.lo:#x}, {span.hi:#x})" for span in staging.Registry.ALL if span.lo < config.staging_base]
    assert not below, (f"{below} start(s) below the declared staging band at {config.staging_base:#x}: a blob may grow "
                       f"over a span the kit's tenancy vet does not know, and nothing would refuse it")


def test_the_blob_s_whole_room_is_dead_memory_in_this_snapshot():
    """From `bench_base` to the band's floor: the blob may take any of it, and `_vet_snapshot_is_empty` would refuse
    the first routine linked over a live byte — here it is said of the room, before a build finds it."""
    config = project.current()
    assert not any(BASE_IMAGE[config.bench_base:config.staging_base])


def test_a_blob_linked_past_the_staging_band_is_refused_by_name_where_it_is_loaded(tmp_path):
    config = project.current()
    over = _linked(tmp_path / "over", config.staging_base + BYTES_PAST_THE_FLOOR)
    assert rom_bench._allocated_span(over / rom_bench.BENCH_ELF) == (config.bench_base, config.staging_base + BYTES_PAST_THE_FLOOR)
    with pytest.raises(AssertionError) as refused:
        rom_bench.RomBench(over)
    said = str(refused.value)
    assert said.startswith("the blob [") and "overlaps " + THE_BAND_S_NAME_IN_THE_KIT in said, said


def test_a_blob_linked_to_the_band_s_floor_is_a_tenant(tmp_path):
    """THE CONTROL: the same link, two bytes shorter, passes the vet that refused — the refusal is the band's."""
    config = project.current()
    full = _linked(tmp_path / "full", config.staging_base)
    span = rom_bench._allocated_span(full / rom_bench.BENCH_ELF)
    assert span == (config.bench_base, config.staging_base)
    rom_bench._vet_tenancy(config, *span)


def test_the_band_is_below_the_stack_band_and_the_high_spans_above_it():
    """The order the two tests above lean on: blob, the declared band (with the VDI's and the AES's windows over it),
    the stack band, and `staging.HIGH_BANDS` — the file system's window and the desk's arena among its claims."""
    assert staging.SCRATCH + staging.SCRATCH_BYTES <= vdi.SPAN.lo < vdi.SPAN.hi <= aes.SPAN.lo < aes.SPAN.hi <= emu.STACK_GUARD_LO
    # ...AND DIRECTLY UNDER THE VDI'S WINDOW, no hole between: a band laid lower costs the blob that much of its room
    # for nothing (reviewer B's surviving mutant: the band a page lower, every other test green).
    assert staging.SCRATCH + staging.SCRATCH_BYTES == vdi.SPAN.lo, "the declared band does not end where the VDI's window begins"
    assert emu.STACK_BAND_HI == staging.HIGH_BANDS.lo <= gemdos_fs.SPAN.lo
    assert (gemdos_fs.SPAN.lo, gemdos_fs.SPAN.hi - gemdos_fs.SPAN.lo) in [(at, size) for at, size, _owner in staging.HIGH_BANDS.claims]
