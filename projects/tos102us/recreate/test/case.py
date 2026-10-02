"""One ROM case, spelt once: what every battery in this project does around `harness.differential`.

A case is always the same four steps — run both cores over the same image, refuse any byte that
differs, check the candidate's return value against the D0 the ROM left, and hand the oracle's report
back for the battery's own claims. Sixteen batteries kept a private copy of those four lines, and the
copies had already started to differ: one compared `ret` against the whole of D0 where the core
returned a word, another did not compare it at all. The check belongs where it cannot drift.

WHAT STAYS IN THE BATTERY is everything that is a claim about the routine — which registers it is
entered with, what its arguments are, and what the result should be. This module only removes the
staging that is the same for all of them.
"""
import struct

import abi
from harness import differential, emu, make_image, report
from recreate_kit.drops import Dropped

# The width of a result, as the C signature declares it. A core that returns nothing (`void` — the
# ROM routine sets no result, or reports only through memory) says so with `None`, which is a claim
# too: the case then requires the candidate glue to return nothing rather than skipping the check.
FULL_D0 = 32
NO_RESULT = None


def run(entry, regs, glue, *, width=FULL_D0, poison=True, dropped=(), dropped_windows=(), **seeds):
    """One differential at `entry`. Returns the oracle's `info` once everything always-checked holds.

    `regs` are the oracle's input registers plus the case's `_pokes`; `glue(lib, buf)` runs the
    candidate over the same image. `width` is the result width — see `assert_result_is_d0`. `poison`
    runs the attribution pass, which is what makes a store the candidate SKIPPED visible when the
    byte already held the right value; it is on by default because these are leaf routines, and a
    battery that turns it off says why.

    `dropped` is `((lo, hi, why), ...)`: a span the ORIGINAL writes and the reconstruction deliberately
    does not, left out of the compare with the reason beside it. It is for a divergence the project
    documents, never for scratch — the kit's own `exclude` is that, and refuses any band that is not
    the stack's. `dropped_windows` is the same shape, for a divergence whose EXTENT the run decides: a
    machine stack the ROM's frames land in (with the holes a `link` reserves), a record armed only on
    the path that nests. Both go to the kit as DATA (`recreate_kit.drops.Dropped`, which says how each is
    cut and vetted — the ONE rule Tier 3's drops are held to too): every dropped byte is one the original's
    run stores, and the rest of a window is compared like any other byte. The kit leaves the drops out
    BEFORE it decides whether to run the attribution pass, and that pass poisons none of the plain run's
    drops and compares none of the UNION of both runs' drops — so `poison` keeps its meaning for every
    other byte of a case that drops.

    `seeds` are `harness.differential`'s remaining keyword arguments — `io_seed`, `psg_seed`,
    `schedule`, `wait_sites` — forwarded rather than enumerated. Every one of them is a DECLARATION
    the case makes about the machine, and the four steps around it are the same whichever is
    present, so naming them here would be a second list to keep level with the kit's.
    """
    diffs, info = differential(entry, regs, glue, poison=poison, dropped=Dropped(dropped, dropped_windows), **seeds)
    assert not diffs, report(diffs)
    assert_result_is_d0(info, width)
    return info


def assert_result_is_d0(info, width=FULL_D0):
    """The candidate's return value against the D0 the ORIGINAL left, at the declared width.

    The image diff says nothing about a register, so this is the only thing that compares the two
    results at all. At `FULL_D0` it is the whole of D0, which is the honest width for every core
    here: a routine that writes only D0's low word takes the caller's D0 as an argument and returns
    the whole register, so that the high half it did NOT write is compared too. A narrower width
    would agree with a reconstruction that cleared what the ROM left alone.
    """
    if width is NO_RESULT:
        assert info["ret"] is None, (
            f"the candidate returned {info['ret']!r} where the ROM routine sets no result — either "
            f"the glue is returning something it should not, or the core is not `void`")
        return
    mask = (1 << width) - 1
    assert info["ret"] == (info["regs"]["d0"] & mask), (
        f"the candidate returned {info['ret']:#x} where the ROM left {info['regs']['d0']:#x} in D0")


def written(info, address, size):
    """The `size`-byte big-endian value the ORACLE left at `address`, out of its own write ledger.

    Deliberately not a read of the final image: a field the routine never stored is then a KeyError
    naming it, rather than a stale byte that happens to read right.
    """
    return int.from_bytes(bytes(info["writes"][address + i] for i in range(size)), "big")


def written_long(info, address):
    """...the longword, which is what most of these routines store."""
    return written(info, address, 4)


def hardware_reads(info):
    """The ORACLE's two ordered read streams as one list, `[(address, value), ...]`.

    WHICH of them a byte lands in is the kit's bookkeeping — a Phase-7 NAMED slot goes through
    `hw_read8` and an ordinary declared byte through `io_read8` — and a case declares both through
    the one `io_seed` door, so a battery that cared which would be asserting the kit's routing
    rather than the routine's traffic.
    """
    return (list(info["regs"]["hw_events"])
            + [(address, value) for address, _width, value in info["regs"]["io_events"]])


def hardware_writes(info):
    """...and the ordered WRITE ledger (Phase 10), which is the whole of what a data port leaves."""
    return [(address, value) for address, _width, value in info["regs"]["hw_writes"]]


def long_in(image, address):
    """The big-endian LONGWORD `image` holds at `address` — a snapshot, a staged image or a run's
    final one, all of which are byte sequences a battery indexes.

    The GEMDOS wave alone had six private copies of this and its word twin, under three names and
    two argument orders. It is not about any routine, so it belongs where a battery can reach it
    without importing another battery's module; the spelling is `test/isr.py`'s `long_in_snapshot`,
    which is this function with `BASE_IMAGE` bound.
    """
    return int.from_bytes(bytes(image[address:address + 4]), "big")


def word_in(image, address):
    """...and the word."""
    return int.from_bytes(bytes(image[address:address + 2]), "big")


def args(fmt, *values):
    """The argument frame a case stages, as `struct` spells it — for the shapes the three helpers
    below do not cover (`Mshrink`'s reserved word and then two longwords is the one).

    `abi.FIRST_ARG` is 4(A7) — one longword of return address above the stack pointer `emu.run`
    plants, which is the frame a `jsr` leaves and therefore the frame every BIOS/XBIOS/GEMDOS
    routine reads its arguments out of.
    """
    return {abi.FIRST_ARG: struct.pack(fmt, *values)}


def word_args(*values):
    """The argument WORDS a case stages, where the dispatcher's caller would have left them."""
    return args(f">{len(values)}H", *(value & 0xFFFF for value in values))


def word_arg(value):
    """...and the single-word case, which is most of them."""
    return word_args(value)


def long_args(*values):
    """The argument LONGWORDS, which is what GEMDOS takes where the BIOS takes words — a DTA
    pointer, a block address, the MPB the allocator core is handed beside its own argument."""
    return args(f">{len(values)}I", *(value & 0xFFFF_FFFF for value in values))


def final_image(info, pokes):
    """The image the ORACLE ended with: the staged one, with its own write ledger laid over it.

    `harness.differential` hands a battery the write LEDGER rather than the final image, which is the
    sharper thing for a field the routine stores — a `KeyError` names a field nothing wrote — but a
    case that asserts about a LIST, a queue or a whole sector is mostly reading bytes it poked and
    the routine left alone. The ledger IS the final value at every address it names, so the two
    layers together are the run's last state.

    A run that overflowed the ledger would make that false SILENTLY, so it is refused here rather
    than quietly reconstructed from a partial list. Six batteries had a private copy of these four
    lines and only one of them carried that refusal.
    """
    assert not info["regs"].get("writes_truncated"), (
        "the oracle's write ledger overflowed, so the image rebuilt from it would be missing stores "
        "— shorten the run or read the fields this case needs out of `info[\"writes\"]` directly")
    image = make_image(pokes)
    for at, value in info["writes"].items():
        image[at] = value
    return image


# ---- what every staging module shares ----------------------------------------------------------------

# The byte an output buffer is pre-filled with before a run: one no routine here leaves in a field it
# answers, so a store the reconstruction SKIPPED reads as something no arm produces. It is
# `vt52.CANARY`'s value for the same reason; GEMDOS, the file system and the VDI all stage with it.
SLACK_FILL = 0xA5


def merge_pokes(*layers):
    """Poke dicts laid over each other BYTE BY BYTE, later layers winning, as one dict of runs.

    `{**a, **b}` merges by KEY: a one-word poke at an address that is also the start of a staged
    record REPLACES the whole record, and a poke inside a record but at a different key is applied in
    whatever order `make_image` happens to walk them. Flattening onto bytes makes an overlap mean what
    it says — the later layer's bytes, the earlier layer's everywhere else — whatever the keys were.
    """
    flat = {}
    for layer in layers:
        for at, data in (layer or {}).items():
            for offset, value in enumerate(data):
                flat[at + offset] = value
    runs, start, run = {}, None, bytearray()
    for address in sorted(flat):
        if start is not None and address == start + len(run):
            run.append(flat[address])
            continue
        if start is not None:
            runs[start] = bytes(run)
        start, run = address, bytearray([flat[address]])
    if start is not None:
        runs[start] = bytes(run)
    return runs


def verified_row(name, entry, regs, pokes, psg_seed=None, io_seed=None, schedule=()):
    """One `test_boot_snapshot.VERIFIED_CASES` row in its seven-field shape — the ONE builder every
    component's `register` uses, so the shape cannot drift between them."""
    return (name, entry, dict(regs), dict(pokes), psg_seed, io_seed, schedule)


# ---- a component's REGISTER of verified rows ------------------------------------------------------
# Every registry this process built, so the consumers that read ALL rows (`bench/tier3.py`'s drops, `test_tier3.py`'s
# companions) ask one place rather than naming each component.
ROW_REGISTRIES = []


class Rows:
    """One component's verified rows: `cases` (priced — `test_boot_snapshot.VERIFIED_CASES` splats them), `unpriced`
    (verified and swept, no Tier 3 row: a case entered at a stub rather than the routine), and, by case name, a
    priced row's Tier 3 DROPS (`RomBench.measure`'s `dropped`, vetted per byte: a difference BY NATURE between the ROM
    and a build linked elsewhere, never scratch) with each drop's COMPANION — the battery's differential of the same
    machine with nothing dropped (`test_tier3.py` runs each)."""

    def __init__(self, component):
        self.component = component
        self.cases, self.unpriced = [], []
        self.tier3_dropped, self.tier3_undropped = {}, {}
        ROW_REGISTRIES.append(self)

    def register(self, name, entry, pokes, *, regs=None, psg_seed=None, io_seed=None, schedule=(), priced=True,
                 dropped=(), undropped=None):
        """One `VERIFIED_CASES` row (`verified_row`), recorded and returned so the battery drives the same tuple.
        `dropped` is `((lo, hi, why), ...)` for its Tier 3 row alone, and `undropped` — required with it — the
        zero-argument differential that still compares those bytes over the row's machine (a `Result`), which is
        what makes dropping them at Tier 3 safe."""
        row = verified_row(name, entry, regs or {}, pokes, psg_seed, io_seed, schedule)
        (self.cases if priced else self.unpriced).append(row)
        if dropped:
            assert priced and name not in tier3_dropped(), f"{name}: a Tier 3 drop is for one priced row"
            assert callable(undropped), f"{name}: a Tier 3 drop needs the differential that drops nothing"
            self.tier3_dropped[name] = tuple(dropped)
            self.tier3_undropped[name] = undropped
        return row


def tier3_dropped():
    """`{row name: its Tier 3 drops}` over every component's registry."""
    return {name: spans for rows in ROW_REGISTRIES for name, spans in rows.tier3_dropped.items()}


def tier3_undropped():
    """...and `{row name: its companion differential}`."""
    return {name: companion for rows in ROW_REGISTRIES for name, companion in rows.tier3_undropped.items()}


def registered_case(name):
    """The one PRICED row named `name`, whichever component registered it."""
    row, = (row for rows in ROW_REGISTRIES for row in rows.cases if row[0] == name)
    return row


class Result:
    """A run, and what the machine held AFTER it: the snapshot, the case's pokes, then the ORACLE's
    writes (`final_image`), composed once per run rather than per read."""

    def __init__(self, info, pokes):
        self.info = info
        self.staged = pokes
        self.final = final_image(info, pokes)

    def after(self, at, length):
        return bytes(self.final[at:at + length])

    def long(self, at):
        return int.from_bytes(self.after(at, 4), "big")

    def word(self, at):
        return int.from_bytes(self.after(at, 2), "big")

    def words(self, at, count):
        """`count` big-endian words from `at`, as a list."""
        return list(struct.unpack(f">{count}H", self.after(at, 2 * count)))


# ---- one run's end, as the next run's start ------------------------------------------------------
# A SEQUENCE a program makes — `Fsfirst` then `Fsnext`, `v_opnwk` then a drawing call — is proved one
# routine at a time, each run starting from the machine the one before it ENDED in. That is a real
# differential rather than a replay: the end state carried is the ORACLE's, and BOTH shores start the
# next run from it — a candidate that had ended anywhere else failed the previous run's compare.
#
# WHAT IS CARRIED: every staged poke re-read from the run's final memory, and each byte the oracle
# wrote that no poke covered. WHAT IS NOT: the stack band, which the differential drops and every run
# re-stages with its own arguments, and `refilled` — the addresses a component's own machine staging
# fills afresh on every run, so that the next run's stores to them are still changes.
# The oracle's stack band: every run's frames, which no differential compares.
STACK_BAND = range(emu.STACK_GUARD_LO, emu.STACK_BAND_HI)


def continued(result, refilled=()):
    """The pokes the run after `result` (a `Result`) starts from — its end state, as above."""
    return continued_from(result.staged, result.final, result.info["writes"], refilled)


def continued_from(staged, final, writes, refilled=()):
    """...out of a run's parts: the pokes it `staged`, the `final` memory and the `writes` ledger it ended with —
    for a run made by the oracle alone (`emu.run`), which has no `Result`."""
    refilled = set(refilled)
    covered = {address for at, data in staged.items() for address in range(at, at + len(data))}
    pokes = {at: bytes(final[at:at + len(data)]) for at, data in staged.items()
             if at not in STACK_BAND and at not in refilled}
    pokes.update({at: data for at, data in written_by(writes).items() if at not in covered})
    return pokes


def written_by(writes):
    """Only what a run WROTE (its `writes` ledger), the stack band out — the run's change as a DELTA, to lay over a
    machine other than the one it ran on without restoring that machine's own pokes."""
    return {at: bytes([value]) for at, value in writes.items() if at not in STACK_BAND}
