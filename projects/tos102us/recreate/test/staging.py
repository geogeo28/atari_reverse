"""Where a case puts memory of its own: a buffer to hand a ROM routine, or code for one to jump to.

Several routines in this project take a POINTER — Getmpb's parameter block, Protobt's boot sector,
Supexec's routine — so a case has to own a piece of the machine's RAM. It must be RAM the snapshot
leaves empty, or the case would be staging over the desktop's live data and the differential would
be comparing it as well.

`project.toml` records that band: the capture is zero from $1dde2 to $f7fa1. THREE tenants share it
and they must not overlap — the oracle's own stack around `stack_top`, Tier 3's cross-compiled blob
at `bench_base` (which grows with the reconstruction), and this one at `staging_base`. All three are
declared in that one file, with the addresses, so `RomBench._vet_tenancy` can refuse an overlap.

`test_boot_snapshot.py::test_the_case_staging_band_is_dead_memory_in_this_snapshot` is what keeps the
"dead RAM" half true — a future capture whose desktop grew into the band reddens there rather than
silently running these cases over live bytes.
"""
import harness      # binds the kit to this project, which is what makes the config readable

# The base of the band, and how much of it a case may use. One address rather than one per case, so
# the claim above is about a single span; cases that need two buffers take them at offsets from it.
#
# READ FROM `project.toml`, not spelt here: the band is one of THREE tenants of the same free window
# and `RomBench._vet_tenancy` refuses an overlap between them, which it can only do if all three are
# declared in the one file it reads. A second spelling here would be the one the vet never sees.
_CFG = harness.project.current()
SCRATCH = _CFG.staging_base
SCRATCH_BYTES = _CFG.staging_bytes
if SCRATCH is None:
    raise RuntimeError(f"{_CFG.name}'s project.toml declares no `staging_base`/`staging_bytes`, so "
                       f"there is no band a case may stage a buffer in — declare one beside "
                       f"`bench_base` and `stack_top`, in RAM the captured snapshot leaves empty")


# ---- the bands inside it, and the one thing that must be true of them -----------------------------
# A battery that needs several buffers at once takes a BAND of its own out of this span and names
# offsets inside it. Six modules do, and until this registry each asserted only against the ONE
# neighbour its author knew about — which is how `test_gemdos_fs_name.py`'s band came to start at
# +0x600, exactly on top of `test/gemdos_console.py`'s, with every hand-written assertion still
# passing. Claiming a band here refuses an overlap with EVERY band already claimed, whoever claimed
# it, so the check cannot be half-written again.
#
# The bands are claimed at IMPORT, so the pairs really checked are the ones a run imports; under
# `pytest` that is all of them, because collection imports every battery.
_BANDS = []


def band(offset, size, owner):
    """Claim `[SCRATCH + offset, + size)` for `owner`, and answer its address.

    `owner` is the module that stages there, for the failure message — the point of the assertion is
    to name BOTH sides of a collision, since the module reading the message is rarely the one that
    moved.
    """
    at = SCRATCH + offset
    assert 0 <= offset and offset + size <= SCRATCH_BYTES, (
        f"{owner}'s band [{at:#x}, {at + size:#x}) is not inside the staging band "
        f"[{SCRATCH:#x}, {SCRATCH + SCRATCH_BYTES:#x}) `project.toml` declares")
    for other_at, other_size, other_owner in _BANDS:
        assert at + size <= other_at or other_at + other_size <= at, (
            f"{owner}'s staging band [{at:#x}, {at + size:#x}) overlaps {other_owner}'s "
            f"[{other_at:#x}, {other_at + other_size:#x}) — two batteries staging over each other "
            f"read the same bytes back and prove nothing")
    _BANDS.append((at, size, owner))
    return at


# The bottom of the span, claimed here rather than by any one module: the SINGLE-BUFFER batteries
# (Getmpb's parameter block, Protobt's boot sector, Supexec's stub and marker, Initmous, Keytbl,
# Ikbdws) each stage at `SCRATCH` itself and deliberately share it — one buffer per case, never two
# at once. Claiming it keeps a band-owning module from reaching down into them.
#
# `test_xbios_supexec.py`'s DECOYS are the one thing this does not cover: they are planted at +0x800,
# +0xa00 and +0xc00 ON PURPOSE, inside other batteries' bands, to be unmistakably far from the named
# stub. That overlap is deliberate and is asserted where it matters, in `test/isr.py`.
POINTER_ARGUMENTS_BYTES = 0x400
POINTER_ARGUMENTS = band(0, POINTER_ARGUMENTS_BYTES, "the single-buffer batteries (staging.SCRATCH)")
