"""THE BOOT-CHAIN INVENTORY, machine-checked: what the boot runs, how big it is, what is ported.

The game plays from a STAGED post-boot dump (recreate/atari/gen_image.py), so everything between the
PRG entry and the `jmp $4a0` that starts the frame loop is territory the reconstruction has never
had to enter. This module walks it from bytes and states what is there, so the batch notes' table is
a derived fact rather than a reading. ../STATUS.md's batch 44 phase A carries the table it prints.

HOW THE WALK WORKS. Recursive descent over the RELOCATED image from two roots, decoding with
tools/prg_dis.py. `bsr`/`jsr` to an address operand is a CALL edge; `bra`/`Bcc`/`dbcc`/`jmp` is a
transfer inside the flow. The walk does not stop at a `jmp`, because this program's boot is one long
FALL-THROUGH CHAIN — `$217d8` jumps to `$400`, which jumps to `$e482`, which falls into `$f8bc`,
which jumps to `$e48c`, which branches to `$e4e6` — and treating those as routine boundaries would
invent five routines the original does not have.

THE TRIPWIRE IS THE POINT, and it is what makes this an inventory rather than an estimate. A walk
that silently skipped a transfer it could not resolve would under-report the chain and every byte
count below it. So:

  * every transfer whose target is NOT in its operand must be declared in INDIRECT, with the
    instructions that load the register written beside it. An undeclared one fails the walk;
  * every address the walk stops at must be declared in BOUNDARIES, with what it is;
  * no reached instruction may decode to `dc.w`. That is the check that would have caught this
    phase's own find — prg_dis decoded `move.w #$2700,sr` as two bytes instead of four, which is a
    LENGTH bug, so the walk desynced on the boot's very first instruction. Fixed in the tool and
    pinned in tools/recreate_kit/test/test_prg_dis.py; this assertion is what keeps it fixed HERE,
    where a silent desync would corrupt every number this file reports.

WHAT THE INVENTORY IS NOT. Reachability is not coverage: the walk follows every edge it can see, so
a routine it lists is one the boot CAN enter, not one every boot does. And the Copylock's 1,970
bytes of ciphertext are not walked at all — there is no source text to walk — so every count here is
a statement about the plaintext boot chain.
"""
import bisect

import pytest

import harness
import leaf
from layout import wb

import prg_dis                                                # noqa: E402  (harness put tools/ on
                                                              #              sys.path)

LOAD_BASE = 0x3f8
PROGRAM_END = 0x218d0
GEMDOS_HEADER_LEN = 28                 # prg_dis.decode takes a FILE offset, not an image one

# The relocated image, wrapped so prg_dis can decode it: the loader has already applied the three
# fixups, so this is the byte stream the 68000 executes and not the file's.
BLOB = bytes(GEMDOS_HEADER_LEN) + bytes(harness.BASE_IMAGE[LOAD_BASE:PROGRAM_END])

GAME_MAIN_LOOP = 0x4a0
COPYLOCK_ENTRY = 0xecca
SND_STUB_TABLE = 0x17adc
SND_STUB_STOP = SND_STUB_TABLE + 28
TILE_INSTALL_FALLTHROUGH = wb("TILE_INSTALL_FALLTHROUGH")

# The two roots. The first is where the PRG entry's relocated `jmp` lands; the second is entered by
# `jmp $e494.l` from $700e (and from the frame loop's own quit arms), never by falling into it, so a
# walk from the entry alone would miss the data-disk prompt entirely.
ROOTS = {0x217d8: "the PRG entry's relocator",
         0xe494: "show_data_disk_prompt, reached by `jmp $e494.l` from $700e"}

# Every transfer in the boot chain whose target is not in its operand, resolved by reading the
# instructions that load the register. THE WALK REFUSES AN UNDECLARED ONE.
INDIRECT = {
    0xe550: ((SND_STUB_TABLE,),
             "`move.w #$8,d0 / lea $17adc.l,a0 / jsr (a0)` at $e546 — the sound module's stub 0"),
    0xe8fc: ((0xe92c, 0xe938, 0xe948, 0xe95e),
             "`lea $e91c,a1 / lsl.w #2,d0 / movea.l 0(a1,d0.w),a1 / jsr (a1)` at $e8f0 — the four "
             "longwords of sprite_cru_copy_table, and test_boot.py pins the table's contents"),
    0xfa1e: ((SND_STUB_TABLE,),
             "`lea $17adc.l,a1 / jsr (a1)` in stage_load_window's tail — snd_play_song"),
    0xfa28: ((SND_STUB_STOP,),
             "`jsr 28(a1)` on the same a1 — snd_stop (see cmt 0xf95c)"),
}

# Where the walk stops, and why each is a boundary rather than something it failed to follow.
BOUNDARIES = {
    GAME_MAIN_LOOP: "the SPINE. game_main_loop and its fifteen calls are whole since batch 42 "
                    "phase C; this inventory is about what runs BEFORE it",
    COPYLOCK_ENTRY: "THE COPYLOCK. A Rob Northen trace decryptor: 1,970 of its bytes exist as "
                    "plaintext only one longword at a time, so there is no source text to walk or "
                    "to port. recreate/test/copylock.py holds the stub and its witness",
    SND_STUB_TABLE: "the sound module's stub table, ported over batches 21b-25",
    SND_STUB_STOP: "the same table's snd_stop entry",
}

TRANSFER_PREFIXES = ("jmp", "jsr", "bra", "bsr", "db")
TERMINALS = ("rts", "rte", "rtr", "illegal")


def _decode(addr):
    return prg_dis.decode(BLOB, addr - LOAD_BASE + GEMDOS_HEADER_LEN, LOAD_BASE)


def _target_of(text):
    """The absolute address in a transfer's operand, or None when it is a register transfer."""
    _, _, operands = text.partition(" ")
    for piece in operands.replace(",", " ").split():
        if piece.startswith("$"):
            return int(piece.lstrip("$").rstrip(".lw"), 16)
    return None


def _is_transfer(mnemonic):
    return mnemonic.startswith(TRANSFER_PREFIXES) or (mnemonic[0] == "b" and "." in mnemonic)


def walk():
    """Return (reached, calls, targets, undecoded, unresolved) — the inventory in one pass."""
    reached, calls, targets, undecoded, unresolved = {}, {}, set(), [], []
    work = list(ROOTS)
    while work:
        addr = work.pop()
        if addr in reached or addr in BOUNDARIES:
            continue
        length, text = _decode(addr)
        reached[addr] = length
        mnemonic = text.split()[0]
        if mnemonic.startswith("dc.w"):
            undecoded.append((addr, text))
        if mnemonic in TERMINALS:
            continue
        if _is_transfer(mnemonic):
            operand = _target_of(text)
            if operand is not None:
                edges = (operand,)
            elif addr in INDIRECT:
                edges = INDIRECT[addr][0]
            else:
                edges = ()
                unresolved.append((addr, text))
            for target in edges:
                if mnemonic.startswith(("jsr", "bsr")) or addr in INDIRECT:
                    calls.setdefault(target, []).append(addr)
                # EVERY edge, call or not: a BOUNDARY can be arrived at by a plain `jmp`, which is
                # how game_main_loop is entered ($f8b4), so `calls` alone would call it unreached.
                targets.add(target)
                work.append(target)
            if mnemonic.startswith(("jmp", "bra")):
                continue
        work.append(addr + length)
    return reached, calls, targets, undecoded, unresolved


REACHED, CALLS, TARGETS, UNDECODED, UNRESOLVED = walk()


# --- the tripwires ---------------------------------------------------------------------------

def test_no_transfer_in_the_boot_chain_is_unresolved():
    """The claim every byte count below rests on. A register transfer the walk could not follow
    would silently truncate the chain — which is how batches 28 and 31 lost operand-hiding forms."""
    assert not UNRESOLVED, (
        "the walk met %d transfer(s) with no declared target:\n%s"
        % (len(UNRESOLVED), "\n".join(f"  {a:#x}: {t}" for a, t in UNRESOLVED)))


def test_no_reached_instruction_is_undecoded():
    """A `dc.w` in the reached stream is a DESYNC, not a curiosity: prg_dis reports a length for
    every instruction and the walk steps by it, so a form it does not know puts the walk on the
    wrong byte and everything after it is fiction.

    THIS ASSERTION IS THE ONE THAT FIRED. `move.w #$2700,sr` — the first instruction of cold_start
    at $400 — decoded as two bytes rather than four, so the walk read the $2700 immediate as an
    instruction of its own. Eight sites in the boot chain, six `move to SR` and two `move to CCR`.
    Fixed in tools/prg_dis.py and pinned by encoding in tools/recreate_kit/test/test_prg_dis.py.
    """
    assert not UNDECODED, (
        "the walk decoded %d reached word(s) as data:\n%s"
        % (len(UNDECODED), "\n".join(f"  {a:#x}: {t}" for a, t in UNDECODED)))


def test_every_declared_indirect_transfer_is_actually_reached():
    """The other direction, so INDIRECT cannot rot into a list of addresses nothing executes: a
    declaration for a transfer the walk never meets is a claim with nothing behind it."""
    missing = sorted(a for a in INDIRECT if a not in REACHED)
    assert not missing, (
        "INDIRECT declares %s, which the walk never reaches — stale entries"
        % [hex(a) for a in missing])


def test_every_boundary_is_actually_reached():
    """Same rule for the stops. A boundary nothing arrives at is not a boundary."""
    unreached = sorted(b for b in BOUNDARIES if b not in TARGETS)
    assert not unreached, (
        "BOUNDARIES declares %s, which nothing in the boot chain transfers to"
        % [hex(b) for b in unreached])


# --- the inventory itself ---------------------------------------------------------------------
# The numbers ../STATUS.md quotes. Recorded here so that porting a routine, or discovering an edge
# the walk did not have, moves them LOUDLY.

BOOT_CHAIN_INSNS = 1185
BOOT_CHAIN_BYTES = 4598

# TWO DIFFERENT 57s THAT HAPPEN TO COINCIDE, and both are pinned because the coincidence is not a
# fact about the program — it is arithmetic that a single new edge would break in one set only.
#
#   BOOT_CHAIN_SEGMENTS   = the TABLE's rows: 54 routines the walk both calls and walks, plus
#                           `cold_start` (entered by the relocator's `jmp` and by nothing else) and
#                           the two ROOTS. Boundaries are NOT rows — the walk stops at them, so they
#                           own no bytes.
#   BOOT_CHAIN_CALL_TARGETS = the CALL graph's targets: the same 54, plus the three boundaries that
#                           are reached by a call (`copylock_entry` and the sound module's two stub
#                           entries). `game_main_loop` is the fourth boundary and is NOT here,
#                           because it is arrived at by `jmp $4a0.w` and never called.
#
# Intersection 54, and each set has three members the other lacks. ../STATUS.md quotes both numbers
# and says which is which; `test_the_two_fifty_sevens_are_different_sets` is what stops a reader —
# or a later edit — treating them as one.
BOOT_CHAIN_SEGMENTS = 57
BOOT_CHAIN_CALL_TARGETS = 57
BOOT_CHAIN_SHARED = 54


def test_the_boot_chain_is_the_size_this_phase_measured():
    assert len(REACHED) == BOOT_CHAIN_INSNS
    assert sum(REACHED.values()) == BOOT_CHAIN_BYTES
    assert len(CALLS) == BOOT_CHAIN_CALL_TARGETS
    assert len(SEGMENTS) == BOOT_CHAIN_SEGMENTS


def test_the_two_fifty_sevens_are_different_sets():
    """The table's 57 rows and the call graph's 57 targets are not the same 57.

    Asserted as SET MEMBERSHIP and not as two equal integers, so that an edge added to one side
    fires here instead of leaving the two totals quietly equal for a new reason. Every member of
    each difference is named, because each is named for a structural reason the walk depends on:
    the three rows that are not call targets are the fall-through head and the two roots, and the
    three targets that are not rows are the called boundaries.
    """
    rows, targets = set(SEGMENTS), set(CALLS)
    assert len(rows & targets) == BOOT_CHAIN_SHARED
    assert rows - targets == {min(REACHED)} | set(ROOTS), (
        "the rows that are not call targets should be cold_start and the two roots, not "
        f"{[hex(a) for a in sorted(rows - targets)]}")
    called_boundaries = {b for b in BOUNDARIES if b in CALLS}
    assert targets - rows == called_boundaries, (
        "the call targets that are not rows should be exactly the CALLED boundaries, not "
        f"{[hex(a) for a in sorted(targets - rows)]}")
    assert GAME_MAIN_LOOP not in called_boundaries and GAME_MAIN_LOOP in TARGETS, (
        "game_main_loop is entered by `jmp` and must be a transfer target but never a call target — "
        "if that changed, the spine is being CALLED from the boot chain and the walk's stop is wrong")


def _segments():
    """The reached bytes partitioned by CALL TARGET — the honest routine boundary, since a name in
    ../names.txt may sit inside another routine's body (`var 0xe67e`) or be absent entirely.

    `min(REACHED)` joins the starts because `cold_start` ($400) is entered by the relocator's `jmp`
    and by nothing else: it is neither a root nor a call target, and without it its 18 bytes fall
    below the lowest boundary and are silently dropped. That is exactly the shape this partition
    exists to make impossible, so `test_the_partition_loses_no_byte` checks the sum.
    """
    starts = sorted(set(CALLS) | set(ROOTS) | {min(REACHED)})
    rows = {}
    for addr, length in REACHED.items():
        owner = starts[bisect.bisect_right(starts, addr) - 1]
        rows[owner] = rows.get(owner, 0) + length
    return rows


SEGMENTS = _segments()
PORTED = leaf.ported_entries()

# What the boot chain's own bytes are worth, by whether a reconstruction exists for the routine that
# owns them. Both move when a routine is ported, which is the point of recording them.
BOOT_CHAIN_PORTED_BYTES = 1868
BOOT_CHAIN_UNPORTED_BYTES = 2730
# ...and the figure the split UNDER-REPORTS, because a segment is ported or not as a whole:
# `bg_tile_install`'s 72 reconstructed bytes sit INSIDE show_data_disk_prompt's 632-byte segment,
# which is unported, so they are counted on the unported side above. Stated rather than smoothed
# over — the two numbers answer different questions and only this one is about this phase's work.
BOOT_CHAIN_BYTES_RECONSTRUCTED_THIS_PHASE = 362


def test_the_ported_and_unported_split_is_what_this_phase_reports():
    ported = sum(n for owner, n in SEGMENTS.items() if owner in PORTED)
    unported = sum(n for owner, n in SEGMENTS.items() if owner not in PORTED)
    assert (ported, unported) == (BOOT_CHAIN_PORTED_BYTES, BOOT_CHAIN_UNPORTED_BYTES), (
        f"the boot chain is now {ported} ported / {unported} unported bytes, not the recorded "
        f"{BOOT_CHAIN_PORTED_BYTES} / {BOOT_CHAIN_UNPORTED_BYTES}")


# The routines the boot chain calls that ../names.txt does not name. Recorded rather than fixed:
# an `fn` directive is a claim about a routine's START, and these are call targets inside the raw
# FDC/DMA driver and the boot's own tail whose extents this phase did not read. Naming them is the
# next phase's work, and this list is what says how much of it there is.
UNNAMED_CALL_TARGETS = (0x5f76, 0x5fc4, 0x604a, 0x6068, 0x6092, 0x60da, 0x6118, 0x637e, 0x63c0,
                        0x6488, 0x64ea, 0xe710, 0xe768, 0xf89e)
# `$17af8` is NOT on that list, and the distinction is the point: it has no name either, but it is
# `SND_STUB_TABLE + 28` — a declared BOUNDARY, an entry of the sound module's stub table whose extent
# ../names.txt's `cmt 0x17adc` documents and whose body (`snd_stop`, `$17f24`) has been ported since
# batch 21b. Calling it "a routine whose extent this phase did not read" would be false, so the queue
# excludes every declared boundary and is fourteen, not fifteen.


def test_the_unnamed_call_targets_are_the_ones_this_phase_recorded():
    """A call target with no name is a routine nothing can refer to — including a differential, since
    leaf.entry_of looks names up. So the list is a work queue, and it must not grow silently.

    BOUNDARIES are excluded rather than filtered out afterwards: a boundary is a place the walk
    deliberately stops, so its extent is not this walk's to read, and one of them (`$17af8`) is
    already-ported code that would have made the queue's honesty claim false.
    """
    unnamed = tuple(sorted(a for a in CALLS
                           if a not in harness.NAME_MAP and a not in BOUNDARIES))
    assert unnamed == UNNAMED_CALL_TARGETS, (
        "the boot chain's unnamed call targets are %s, not the recorded %s"
        % ([hex(a) for a in unnamed], [hex(a) for a in UNNAMED_CALL_TARGETS]))


def test_every_unnamed_boundary_is_a_boundary_and_not_an_oversight():
    """The complement, so the exclusion above cannot quietly hide a real gap: every call target this
    walk leaves nameless is EITHER on the queue OR a declared boundary, and nothing is in neither."""
    nameless = {a for a in CALLS if a not in harness.NAME_MAP}
    assert nameless - set(UNNAMED_CALL_TARGETS) - set(BOUNDARIES) == set()


@pytest.mark.parametrize("name", ["copy_longs", "copy_screen", "clear_both_screens",
                                  "clear_palette", "sprites_cru_install"])
def test_this_phase_s_ports_are_on_the_boot_chain(name):
    """Each routine test_boot.py verifies is one the boot actually calls — so the tranche is boot
    chain work and not a set of leaves that merely look like it. (`bg_tile_install` is NOT here: it
    is fallen into rather than called, which is exactly why it carries a `var` and not an `fn`.)"""
    entry = leaf.entry_of(name)
    assert entry in CALLS, f"{name} @ {entry:#x} is never called from the boot chain"


def test_the_tile_installer_is_reached_by_falling_into_it():
    """The complement of the case above, and the reason `bg_tile_install` is spelt as a label: no
    call edge reaches $e67e — the boot's `jsr rad_depack` at $e67a returns into it."""
    entry = leaf.entry_of("bg_tile_install")
    assert entry in REACHED, "the boot chain does not reach the tile installer at all"
    assert entry not in CALLS, (
        f"{entry:#x} IS a call target after all, so it is a routine and should carry an `fn`")


def test_the_partition_loses_no_byte():
    """Every reached byte belongs to exactly one segment. Without this the split above could look
    healthy while a whole routine fell through the boundary arithmetic — which it did: cold_start's
    18 bytes sit below the lowest call target and were dropped until `_segments` took them in."""
    assert sum(SEGMENTS.values()) == BOOT_CHAIN_BYTES, (
        f"the partition accounts for {sum(SEGMENTS.values())} of {BOOT_CHAIN_BYTES} reached bytes")


# The nine routines this phase gave an `fn` to. `bg_tile_install` is deliberately not among them:
# it has a `var`, because it is fallen into rather than called, so it owns no segment of its own.
RECONSTRUCTED_THIS_PHASE = ("copy_longs", "copy_screen", "clear_both_screens", "clear_palette",
                            "sprites_cru_install", "sprite_cru_copy_5w", "sprite_cru_copy_10w",
                            "sprite_cru_copy_15w", "sprite_cru_copy_20w")


def test_this_phase_reconstructed_the_bytes_it_claims():
    """The 362 in ../STATUS.md §3, DERIVED — each routine's extent is summed out of the walk's own
    segments and the tile installer's out of its entry and its fall-through, so a wrong extent fails
    here instead of agreeing with a second transcription of itself.

    An earlier revision of this case hand-typed the nine extents and called itself derived, which
    made it a check that one hand-typed sum equalled another. It could catch a typo in the total and
    nothing else.
    """
    ported_here = 0
    for name in RECONSTRUCTED_THIS_PHASE:
        entry = leaf.entry_of(name)
        assert entry in PORTED, f"{name} is not in the built library"
        assert entry in SEGMENTS, f"{name} @ {entry:#x} owns no segment of the boot chain"
        ported_here += SEGMENTS[entry]
    installer = leaf.entry_of("bg_tile_install")
    assert installer not in SEGMENTS, (
        f"bg_tile_install @ {installer:#x} owns a segment, so it IS a call target and this sum "
        f"would count its bytes twice")
    ported_here += TILE_INSTALL_FALLTHROUGH - installer
    assert ported_here == BOOT_CHAIN_BYTES_RECONSTRUCTED_THIS_PHASE, (
        f"this phase reconstructed {ported_here} boot-chain bytes, not the recorded "
        f"{BOOT_CHAIN_BYTES_RECONSTRUCTED_THIS_PHASE}")


# --- the disk wall -------------------------------------------------------------------------------
# ../STATUS.md §7 and ../PORTABILITY.md §0q both headline this: 1,644 of the 2,730 unported
# boot-chain bytes — sixty per cent — are the raw WD1772/DMA driver and the FAT12 layer above it.
# It is the number that says WHY the .PRG cannot yet boot from its own entry, and it sat in two
# living prose surfaces with nothing asserting it. DERIVED here, which is the discipline this
# phase's own gate taught it: the band's bounds come from ../../notes/architecture.md §2.2, and
# everything else is summed out of the walk.
DISK_DRIVER_LO = 0x5e3e                # disk_check_signature, the driver's first byte
DISK_DRIVER_HI = 0x6528                # the end of its state block, and where rad_depack's callers
                                       # stop being disk code
DISK_WALL_BYTES = 1644
DISK_WALL_PERCENT_FLOOR = 60           # what the two docs claim in words


def test_the_disk_wall_is_the_share_of_the_remainder_the_docs_claim():
    """The headline both docs rest on, summed from the walk's own segments rather than estimated.

    An earlier draft of those docs carried a round estimate here, short by 144, which is what a
    number looks like when nobody makes it a case; the real figure is 1,644 and the correction only
    happened because it was measured on the way to writing this. A number in prose that no case holds
    is a number that drifts the next time a routine is ported.
    """
    unported = {addr: n for addr, n in SEGMENTS.items() if addr not in PORTED}
    disk = sum(n for addr, n in unported.items() if DISK_DRIVER_LO <= addr < DISK_DRIVER_HI)
    total = sum(unported.values())
    assert total == BOOT_CHAIN_UNPORTED_BYTES
    assert disk == DISK_WALL_BYTES, (
        f"the raw FDC/DMA + FAT12 band [{DISK_DRIVER_LO:#x},{DISK_DRIVER_HI:#x}) is now {disk} "
        f"unported bytes, not the recorded {DISK_WALL_BYTES}")
    assert disk * 100 // total >= DISK_WALL_PERCENT_FLOOR, (
        f"the disk path is {disk * 100 // total}% of the unported remainder, below the "
        f"{DISK_WALL_PERCENT_FLOOR}% both docs claim")


def test_the_disk_band_is_where_the_named_driver_routines_live():
    """The band's BOUNDS, so the sum above cannot be right about a wrong region. Every routine
    ../names.txt names with an FDC/FAT prefix must fall inside it, and the two neighbours that
    bracket it must fall outside — which is what fixes both ends."""
    inside = {a for a, name in harness.NAME_MAP.items()
              if name.startswith(("fdc_", "fat_", "floppy_", "disk_"))}
    stray = sorted(a for a in inside if not DISK_DRIVER_LO <= a < DISK_DRIVER_HI)
    assert not stray, (
        f"{[hex(a) for a in stray]} carry an FDC/FAT/floppy/disk name but lie outside "
        f"[{DISK_DRIVER_LO:#x},{DISK_DRIVER_HI:#x})")
    assert leaf.entry_of("rad_depack") < DISK_DRIVER_LO, "rad_depack should sit BELOW the driver"
    assert leaf.entry_of("game_main_loop") < DISK_DRIVER_LO
    assert DISK_DRIVER_HI <= leaf.entry_of("show_data_disk_prompt"), (
        "the prompt should sit ABOVE the driver, so the band's top bound is wrong")
