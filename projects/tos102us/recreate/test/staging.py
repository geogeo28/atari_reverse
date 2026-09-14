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
