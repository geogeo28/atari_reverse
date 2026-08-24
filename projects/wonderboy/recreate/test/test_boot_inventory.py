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
import pathlib
import re

import pytest

import harness
import leaf
from layout import wb

import prg_dis                                                # noqa: E402  (harness put tools/ on
                                                              #              sys.path)

HERE = pathlib.Path(__file__).resolve().parent.parent   # projects/<game>/recreate
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
BOOT_CHAIN_PORTED_BYTES = 2086
BOOT_CHAIN_UNPORTED_BYTES = 2512
# ...and the figure the split UNDER-REPORTS, because a segment is ported or not as a whole, and this
# is the segment it under-reports MOST. Everything below sits INSIDE show_data_disk_prompt's 632-byte
# segment, which is unported because no `src/` symbol carries the name at $e494, so every byte of it
# is counted on the unported side above: `bg_tile_install`'s 72 bytes; batch 44 phase B's three
# pieces of the per-stage dispatcher; batch 44 phase C's three composed slices, whose own composed
# bytes nothing derives yet; and batch 44 phase E's `boot_prompt_screen`, which is $e494..$e4d4 —
# the segment's own first 66 bytes. Stated rather than smoothed over: the two numbers answer
# different questions and only the second is about a phase's own work, and DERIVING the composed
# count is queued in ../STATUS.md rather than typed here.
BOOT_CHAIN_BYTES_RECONSTRUCTED_THIS_PHASE = 362                 # batch 44 phase A
BOOT_CHAIN_BYTES_RECONSTRUCTED_PHASE_B = 218                    # ...and phase B, in whole segments
# The dispatcher's three pieces, which own no segment because they live inside an unported one. Their
# extents are the gaps between their own entries and the boundaries the walk gives, so they are
# DERIVED below rather than typed: 314 = 218 + 96 is what this phase reconstructed altogether.
DISPATCHER_PIECES = ("stage_sequence_advance", "stage_sequence_resource", "stage_sequence_apply_row")
PHASE_B_DISPATCHER_BYTES = 96
PHASE_B_BYTES = BOOT_CHAIN_BYTES_RECONSTRUCTED_PHASE_B + PHASE_B_DISPATCHER_BYTES  # 314


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
                        0x6488, 0x64ea, 0xf89e)
# TWELVE, and it was fourteen through batch 44 phase A: $e710 and $e768 came off it because phase B
# read their extents and gave them names (`stage_actors_init`, `actor_apply_stage_side`). ELEVEN OF
# THE TWELVE ARE INSIDE THE DISK BOUNDARY, which is the queue's own headline now — see the seam
# section at the foot of this file. Naming them is no longer the next phase's work but the boundary's
# content, and a boundary's content is what a boundary exists to leave unread.
# `$17af8` is NOT on that list, and the distinction is the point: it has no name either, but it is
# `SND_STUB_TABLE + 28` — a declared BOUNDARY, an entry of the sound module's stub table whose extent
# ../names.txt's `cmt 0x17adc` documents and whose body (`snd_stop`, `$17f24`) has been ported since
# batch 21b. Calling it "a routine whose extent this phase did not read" would be false, so the queue
# excludes every declared boundary. It was fourteen-not-fifteen when phase A wrote that; phase B
# named two of them and the list is TWELVE, which is what UNNAMED_CALL_TARGETS above asserts.


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
# ...and the three phase B gave an `fn` to. The dispatcher's three pieces are deliberately NOT here
# for `bg_tile_install`'s reason: they carry `var` directives, because they lie inside
# show_data_disk_prompt's Ghidra body and an `fn` there would truncate it.
RECONSTRUCTED_PHASE_B = ("load_resource_by_index", "stage_actors_init", "actor_apply_stage_side")


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


def test_phase_b_reconstructed_the_bytes_it_claims():
    """The same derivation for phase B's three whole segments, and it is also the case that says the
    218 in ../STATUS.md is the WHOLE of the split's movement: the dispatcher's three pieces are real
    reconstruction that the segment arithmetic cannot see, because they live inside an unported
    segment. A reader who subtracted 2,730 - 2,512 and called it phase B's output would be right by
    arithmetic and wrong about the work."""
    ported_here = 0
    for name in RECONSTRUCTED_PHASE_B:
        entry = leaf.entry_of(name)
        assert entry in PORTED, f"{name} is not in the built library"
        assert entry in SEGMENTS, f"{name} @ {entry:#x} owns no segment of the boot chain"
        ported_here += SEGMENTS[entry]
    assert ported_here == BOOT_CHAIN_BYTES_RECONSTRUCTED_PHASE_B
    for name in DISPATCHER_PIECES:
        entry = leaf.entry_of(name)
        assert entry in PORTED, f"{name} is not in the built library"
        assert entry not in SEGMENTS, (
            f"{name} @ {entry:#x} owns a segment, so it IS a call target and should carry an `fn` "
            f"rather than the `var` cmt 0xe5ba's rule gives it")
    # ...and the 96 the split cannot see, DERIVED from the pieces' own boundaries. The advance runs
    # from its entry to the load's `bsr`, MINUS the index computation nested inside it; the apply runs
    # from its entry to the first instruction past it.
    advance, resource, apply_row = (leaf.entry_of(name) for name in DISPATCHER_PIECES)
    assert (resource, apply_row) == (wb("SEQ_RESOURCE_AT"), wb("SEQ_APPLY_AT")), (
        "the header's cuts and ../names.txt disagree about where the dispatcher's pieces start")
    resource_span = wb("SEQ_RESOURCE_END") - resource
    # The advance's own bytes are its run to the load's argument setup MINUS the index computation
    # nested inside it — the one piece that is not a contiguous extent.
    advance_span = (wb("SEQ_ADVANCE_END") - advance) - resource_span
    apply_span = wb("SEQ_APPLY_END") - apply_row
    dispatcher = advance_span + resource_span + apply_span
    assert advance < resource < wb("SEQ_ADVANCE_END") < apply_row < wb("SEQ_APPLY_END"), (
        "the dispatcher's three pieces no longer lie in the order this derivation assumes")
    assert dispatcher == PHASE_B_DISPATCHER_BYTES, (
        f"the dispatcher's three pieces span {dispatcher} bytes, not the recorded "
        f"{PHASE_B_DISPATCHER_BYTES}")
    assert ported_here + dispatcher == PHASE_B_BYTES, (
        f"phase B reconstructed {ported_here + dispatcher} boot-chain bytes altogether, not the "
        f"{PHASE_B_BYTES} ../STATUS.md reports")


# --- the disk wall -------------------------------------------------------------------------------
# ../STATUS.md §7 and ../PORTABILITY.md §0q both headline this: 1,644 of the 2,730 unported
# boot-chain bytes — sixty per cent — are the raw WD1772/DMA driver and the FAT12 layer above it.
# It is the number that says WHY the .PRG cannot yet boot from its own entry, and it sat in two
# living prose surfaces with nothing asserting it. DERIVED here, which is the discipline this
# phase's own gate taught it: the band's bounds come from ../../notes/architecture.md §2.2, and
# everything else is summed out of the walk.
# The band's bounds come from ../include/wonderboy.h, which is where PORTABILITY.md and
# architecture.md quote them from. An earlier revision of this phase spelt them a THIRD time here
# (and a fourth as `AIM_VELOCITY`), so a re-measured bound could have been right in the header and
# stale in the case that "measures rather than asserts" it.
DISK_DRIVER_LO = wb("DISK_BAND_LO")    # disk_check_signature, the driver's first byte
DISK_DRIVER_HI = wb("DISK_BAND_HI")    # the end of its state block, and where rad_depack's callers
                                       # stop being disk code
DISK_WALL_BYTES = 1644
# THE SHARE MOVES WHEN THE DENOMINATOR DOES, and it just did: phase A measured 1,644 of 2,730 and
# wrote "sixty per cent"; phase B ported 218 of the remainder, so the same 1,644 is now 65 % of
# 2,512. The floor is re-pinned rather than left slack — a floor five points under the truth stops
# being the check that keeps a prose number honest, which is the whole reason this case exists.
DISK_WALL_PERCENT_FLOOR = 65           # what ../STATUS.md's batch 44 phase B claims in words


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


# =================================================================================================
# THE SEAM (batch 44 phase B)
#
# The band above is not merely "the part that is hardware": it is a BOUNDARY, declared the way the
# Copylock is, and a boundary is only worth the name if its edges are enumerated. These cases are
# that enumeration, and they are what the phase's decision rests on:
#
#   * the boot chain crosses into the band EXACTLY ONCE, at `jsr disk_load_file.w` ($e79c);
#   * the whole IMAGE has four encoded transfers into it, and each of the other three is named;
#   * the band transfers OUT nowhere at all — it is a closed subgraph that leaves by `rts`;
#   * and the seam's inputs are FILE-SHAPED, which is the fact that lets a GEMDOS substitution stand
#     in for a WD1772 driver without a name having to be built or a sector having to be modelled.
#
# WHY A CENSUS OVER ENCODINGS AND NOT OVER A LISTING. A linear sweep of a 136 KB image decodes its
# data as instructions, so a grep for "$5e7c" in a listing answers with dozens of coincidences. What
# is decidable instead is: scan every even offset for the ENCODING of a transfer, then classify each
# hit by whether its address is an instruction START in a decode anchored at a NAMED routine. A hit
# that is not one is an operand fragment, and saying which fragment is the difference between an
# enumerated set and a hand-wave.
# =================================================================================================

DISK_SEAM_CALL = wb("DISK_SEAM_CALL")
DISK_SEAM_VBL_CALL = wb("DISK_SEAM_VBL_CALL")
FLOPPY_DESELECT_ALL = wb("FLOPPY_DESELECT_ALL")
DISK_LOAD_FILE = wb("DISK_LOAD_FILE")
LOAD_RESOURCE_BY_INDEX = 0xe782      # the anchor the seam's own edge is decoded from
FDC_RESTORE = 0x6408                   # the Copylock failure arm's target; ../names.txt names it
COPYLOCK_KEY_CHECK = 0xf552            # ../names.txt cmt 0xf552 — the plaintext tail of the blob
AIM_VELOCITY = DISK_DRIVER_HI          # actor_aim_velocity IS the first byte past the band
VBL_HANDLER = 0x716                    # what the boot installs at vector $70 ($f8c6 / $e506)
# fat_find_dir_entry compares a directory entry's eleven name bytes against a0's TWELVE, skipping
# the dot at [8] — which is the whole evidence that the seam's a0 is a filename and not a sector.
FAT_FIND_DIR_ENTRY_BYTES = 138
FAT_NAME_OFFSETS = [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11]

# EVERY STATICALLY-RESOLVABLE TRANSFER FORM, and the scan is only as wide as this list. That is the
# operand-hiding class this binary has bitten on seven times before (batches 28, 31, 33, 34, 38, 39),
# and a census that misses a form does not report a gap — it reports a smaller SET and reads as proof.
JSR_JMP_ABS_L = (0x4eb9, 0x4ef9)
JSR_JMP_ABS_W = (0x4eb8, 0x4ef8)
JSR_JMP_D16_PC = (0x4eba, 0x4efa)               # `jsr/jmp d16(pc)` — resolvable, and invisible to an
                                                # absolute-operand scan because it holds no address
BCC_OPCODE_LO, BCC_OPCODE_HI = 0x6000, 0x7000   # bra/bsr/Bcc all live in this quarter of the space
BCC_WORD_FORM = 0x00                            # a displacement byte of 0 means a 16-bit one follows
BCC_LONG_FORM = 0xff                            # ...and $ff a 32-bit one (68020+, absent here)
DBCC_MASK, DBCC_FORM = 0xf0f8, 0x50c8           # `DBcc Dn,<d16>` — it lives INSIDE addq/subq's
                                                # quarter ($5xxx), so it needs its own mask rather
                                                # than a range, and it always takes a word
WORD_EXTENSION = 2

# The forms that DO transfer and CANNOT be resolved from the bytes, named so the census's silence
# about them is a declared exclusion rather than an oversight. Each is checked absent from the band
# by `test_the_disk_band_uses_no_unresolvable_transfer_form`.
JSR_JMP_PC_INDEXED = (0x4ebb, 0x4efb)           # `jsr/jmp d8(pc,Xn)` — an index register decides it
JMP_JSR_INDIRECT_LO, JMP_JSR_INDIRECT_HI = 0x4e90, 0x4eb8   # `jsr (An)` / `jmp (An)` and friends


def _word_at(addr, image=None):
    image = harness.BASE_IMAGE if image is None else image
    return int.from_bytes(image[addr:addr + 2], "big")


def _transfer_target(addr, image=None):
    """The absolute target of a transfer ENCODED at `addr`, or None if no transfer is encoded there.

    Encodings only — this makes no claim that `addr` is an instruction. Classifying that is
    `_fragment_of` below, and keeping the two apart is what makes the census decidable.

    `image` is for the PLANTED-ENCODING case: a scan is only as wide as its form list, so the list is
    RED-checked by building each form into a scratch buffer and requiring the scan to resolve it.
    """
    image = harness.BASE_IMAGE if image is None else image
    word = _word_at(addr, image)
    if word in JSR_JMP_ABS_L:
        return int.from_bytes(image[addr + 2:addr + 6], "big")
    if word in JSR_JMP_ABS_W:
        return _word_at(addr + 2, image)
    # PC-RELATIVE CALL AND JUMP, and `DBcc`'s loop displacement. Both resolve statically and neither
    # holds an address, so an absolute-operand scan cannot see them. Their displacement counts from
    # the EXTENSION WORD, i.e. from addr + 2, exactly as a `Bcc.w`'s does.
    if word in JSR_JMP_D16_PC or (word & DBCC_MASK) == DBCC_FORM:
        return addr + WORD_EXTENSION + int.from_bytes(
            image[addr + 2:addr + 4], "big", signed=True)
    if not BCC_OPCODE_LO <= word < BCC_OPCODE_HI:
        return None
    displacement = word & 0xff
    if displacement == BCC_WORD_FORM:
        return addr + WORD_EXTENSION + int.from_bytes(image[addr + 2:addr + 4], "big", signed=True)
    if displacement == BCC_LONG_FORM:
        return None
    return addr + 2 + int.from_bytes(bytes([displacement]), "big", signed=True)


def _is_instruction_start(addr, anchor):
    """Whether `addr` falls on an instruction boundary of the decode that starts at `anchor`.

    The anchor must be a routine start this project has read, so the decode is over real code and the
    answer means something. An address that is NOT a boundary is inside some instruction's operand —
    which is what every false positive of the census below turns out to be.
    """
    at = anchor
    while at < addr:
        at += _decode(at)[0]
    return at == addr


# Anchors for the parts of the disk band the WALK DOES NOT REACH. The boot chain enters the band
# through the seam, so it covers 1,626 of the band's 1,770 bytes; the remaining 144 are
# `disk_check_signature` (unreachable except from the Copylock — cmt 0x5e3e), `floppy_deselect_drives`
# (reached only from the vblank vector) and the driver's state block. A hit in one of those is
# invisible to `REACHED` and needs a decode of its own.
UNWALKED_BAND_ANCHORS = (0x5e3e, 0x6268)        # disk_check_signature, floppy_deselect_drives


def _fragment_of(addr):
    """The address of the instruction that CONTAINS `addr`, or None if `addr` starts one.

    POSITIVE CLASSIFICATION, and the reason it has to be positive: an earlier revision of the
    closed-subgraph case asked only `addr in REACHED` and treated every miss as a fragment. All seven
    of its hits are outside REACHED — one of them inside `disk_check_signature`, which the walk never
    enters — so the test passed while establishing NOTHING about any of them. "Not a walked
    instruction start" and "an operand fragment" are different claims, and 144 unwalked bytes is
    where they come apart.

    Two sources, in order, because the strong one does not cover the whole band:
      * the WALK — if a reached instruction SPANS `addr`, that is the enclosing instruction, decided
        by a decode this file already guards (`test_no_reached_instruction_is_undecoded`);
      * failing that, a linear decode from the nearest declared anchor at or below `addr`, which is
        the discipline the in-edge census uses.
    """
    for at, length in REACHED.items():
        if at < addr < at + length:
            return at
    if addr in REACHED:
        return None
    anchors = [a for a in UNWALKED_BAND_ANCHORS if a <= addr]
    assert anchors, (
        f"{addr:#x} is neither walked nor below a declared anchor, so nothing can say what it is")
    at = max(anchors)
    while at < addr:
        at += _decode(at)[0]
    return None if at == addr else _decode_start_before(at, addr)


def _decode_start_before(overshot, addr):
    """The instruction the decode STEPPED OVER to land past `addr` — its start, re-derived."""
    at = max(a for a in UNWALKED_BAND_ANCHORS if a <= addr)
    previous = at
    while at <= addr:
        previous, at = at, at + _decode(at)[0]
    assert previous < addr < at, f"{addr:#x} was not stepped over by the instruction at {previous:#x}"
    return previous


def _encoded_transfers(source_inside, target_inside):
    """Every even address in the image where a transfer is ENCODED with the given inside-ness."""
    return [addr for addr in range(LOAD_BASE, PROGRAM_END - 6, 2)
            if source_inside(addr)
            and (target := _transfer_target(addr)) is not None and target_inside(target)]


def _in_band(addr):
    return DISK_DRIVER_LO <= addr < DISK_DRIVER_HI


# The four sites in the whole image that encode a transfer from OUTSIDE the disk band to inside it,
# each with the anchor its instruction-boundary question is decided from and what it is. The set is
# the claim; a fifth entry appearing is the claim breaking.
EDGES_INTO_THE_BAND = {
    # THE SEAM. `jsr $5e7c.w` inside load_resource_by_index — the boot chain's one crossing.
    DISK_SEAM_CALL: (LOAD_RESOURCE_BY_INDEX, DISK_LOAD_FILE),
    # THE SECOND EDGE, and it is an INTERRUPT: the level-4 handler's `jsr $6268.l` when the floppy
    # idle timer expires. No walk over CALL edges can find it, because a vector is not a call.
    DISK_SEAM_VBL_CALL: (VBL_HANDLER, FLOPPY_DESELECT_ALL),
    # The Copylock's failure arm, `jsr fdc_restore.w` — inside a boundary this project already counts
    # (../names.txt cmt 0xf552) and reached only when the protection's key check fails.
    0xf56a: (COPYLOCK_KEY_CHECK, FDC_RESTORE),
    # ...and one that is NOT an instruction at all: the low word of `lea $6586.l,a1`'s operand inside
    # actor_aim_velocity. $6586 reads as `bmi.s`, which is the whole reason the census classifies by
    # decode rather than by encoding alone.
    0x6532: (AIM_VELOCITY, None),
}


def test_the_boot_chain_crosses_the_disk_seam_exactly_once():
    """THE PHASE'S CENTRAL CLAIM, over the walk's own reached instructions rather than over an
    encoding scan — so it is about code that RUNS and not about bytes that decode.

    What it licenses is the boundary: everything the seam reaches can be excluded, and the load path
    above it ported, without a second crossing left unaccounted for."""
    def crosses(addr):
        # FROM OUTSIDE ONLY. The walk descends THROUGH the seam and reaches all 1,644 bytes of the
        # driver, so its own internal `bsr`s are not crossings — an earlier draft counted 120 of them
        # and reported the band as riddled with edges, which is what the word "crossing" has to mean
        # precisely for the boundary claim to say anything.
        if _in_band(addr):
            return False
        text = _decode(addr)[1]
        if not _is_transfer(text.split()[0]):
            return False                      # `_target_of` reads ANY instruction's first $ operand
        target = _target_of(text)
        return target is not None and _in_band(target)

    crossings = sorted(addr for addr in REACHED if crosses(addr))
    assert crossings == [DISK_SEAM_CALL], (
        "the boot chain crosses into [%#x,%#x) at %s, not only at the seam %#x"
        % (DISK_DRIVER_LO, DISK_DRIVER_HI, [hex(a) for a in crossings], DISK_SEAM_CALL))
    assert _target_of(_decode(DISK_SEAM_CALL)[1]) == wb("DISK_LOAD_FILE"), (
        f"the crossing at {DISK_SEAM_CALL:#x} does not aim at disk_load_file")
    assert CALLS[wb("DISK_LOAD_FILE")] == [DISK_SEAM_CALL], (
        f"disk_load_file has callers {CALLS[wb('DISK_LOAD_FILE')]} on the boot chain, not the one "
        f"the boundary's single-edge claim needs")


def test_the_whole_image_has_four_encoded_edges_into_the_band_and_each_is_named():
    """THE SET, over the whole image and not only the boot chain — because the claim above is about
    the boot chain, and the program is bigger than the boot chain.

    Three of the four are real transfers and the fourth is an operand fragment; each is classified by
    decoding forward from a routine start ../names.txt names, so "that one is data" is a measurement
    and not an excuse. The `nth` entry is what makes this a SET claim: a fifth edge appearing —
    someone finding a new caller, or a decoder fix changing a boundary — fails here."""
    found = _encoded_transfers(lambda a: not _in_band(a), _in_band)
    assert sorted(found) == sorted(EDGES_INTO_THE_BAND), (
        "the image encodes transfers into [%#x,%#x) at %s, not the recorded %s"
        % (DISK_DRIVER_LO, DISK_DRIVER_HI, [hex(a) for a in sorted(found)],
           [hex(a) for a in sorted(EDGES_INTO_THE_BAND)]))
    for addr, (anchor, target) in EDGES_INTO_THE_BAND.items():
        real = _is_instruction_start(addr, anchor)
        assert real == (target is not None), (
            f"{addr:#x} is {'' if real else 'not '}an instruction start in the decode from "
            f"{anchor:#x}, which is the opposite of what this census records")
        if target is not None:
            assert _transfer_target(addr) == target, (
                f"the transfer at {addr:#x} now aims at {_transfer_target(addr):#x}, not {target:#x}")


# Each form the scan claims to resolve, as (name, encoder). The encoder takes the address the
# instruction sits at and the address it must aim at, and returns the bytes — so the case below can
# PLANT one and require the scan to find it.
def _plant_abs_l(opcode):
    return lambda _at, target: opcode.to_bytes(2, "big") + target.to_bytes(4, "big")


def _plant_abs_w(opcode):
    return lambda _at, target: opcode.to_bytes(2, "big") + target.to_bytes(2, "big")


def _plant_d16(opcode):
    return lambda at, target: (opcode.to_bytes(2, "big")
                               + (target - at - WORD_EXTENSION).to_bytes(2, "big", signed=True))


def _plant_bcc_w():
    return _plant_d16(BCC_OPCODE_LO)                 # `bra.w` — displacement byte 0, then a word


def _plant_dbf():
    return _plant_d16(DBCC_FORM | 0x0100)            # `dbf d0,<d16>` (condition F), the loop form


TRANSFER_FORMS = (
    ("jsr <abs>.l", _plant_abs_l(JSR_JMP_ABS_L[0])),
    ("jmp <abs>.l", _plant_abs_l(JSR_JMP_ABS_L[1])),
    ("jsr <abs>.w", _plant_abs_w(JSR_JMP_ABS_W[0])),
    ("jmp <abs>.w", _plant_abs_w(JSR_JMP_ABS_W[1])),
    ("jsr d16(pc)", _plant_d16(JSR_JMP_D16_PC[0])),
    ("jmp d16(pc)", _plant_d16(JSR_JMP_D16_PC[1])),
    ("bra.w", _plant_bcc_w()),
    ("dbf Dn,<d16>", _plant_dbf()),
)

# Somewhere inside the band with room for six bytes, and a target outside it. Both are asserted.
PLANT_AT = 0x6000
PLANT_TARGET = 0x400                                  # cold_start — outside the band, and a real
                                                      # address rather than a made-up one


@pytest.mark.parametrize("name,encode", TRANSFER_FORMS, ids=[n for n, _ in TRANSFER_FORMS])
def test_the_transfer_scanner_resolves_every_form_it_claims_to(name, encode):
    """A CENSUS IS ONLY AS WIDE AS ITS FORM LIST, and this binary has hidden an operand from a scan
    seven times before. So every form the scan claims to resolve is PLANTED into a scratch image and
    the scan is required to find it aiming where it was told.

    `jsr/jmp d16(pc)` and `DBcc` are the two this phase added: both resolve statically, neither holds
    an address, and an absolute-operand scan is blind to both. Planting them is what makes their
    absence from the real image a MEASUREMENT rather than a silence.
    """
    assert _in_band(PLANT_AT) and not _in_band(PLANT_TARGET), (
        "the plant site and its target are not on opposite sides of the band, so a hit would prove "
        "nothing about an out-edge")
    scratch = bytearray(harness.BASE_IMAGE)
    planted = encode(PLANT_AT, PLANT_TARGET)
    scratch[PLANT_AT:PLANT_AT + len(planted)] = planted
    assert _transfer_target(PLANT_AT, scratch) == PLANT_TARGET, (
        f"a planted `{name}` at {PLANT_AT:#x} aimed at {PLANT_TARGET:#x} resolves to "
        f"{_transfer_target(PLANT_AT, scratch)} — the scan cannot see this form, so its census of "
        f"the band's edges is narrower than it reads")
    # ...and the control: the SAME bytes must NOT resolve to the target once the opcode is gone, so
    # the case cannot pass on the operand alone.
    scratch[PLANT_AT:PLANT_AT + 2] = b"\x4e\x71"      # nop
    assert _transfer_target(PLANT_AT, scratch) != PLANT_TARGET, (
        f"`{name}`'s operand still resolves to {PLANT_TARGET:#x} with the opcode replaced by a nop, "
        f"so this case is reading the operand and not the form")


# The transfer forms that CANNOT be resolved from the bytes. The census says nothing about them by
# construction, so what it owes the reader is that the band contains NONE of them.
def test_the_disk_band_uses_no_unresolvable_transfer_form():
    """`jsr/jmp d8(pc,Xn)` and `jsr/jmp (An)` decide their target at run time, so no static scan can
    follow one and a band containing one would have an edge the closed-subgraph claim cannot see.

    Asked of the WALK'S OWN instructions rather than of an encoding scan, because here the question
    is about instructions and not about byte patterns — and the walk, which stops at nothing inside
    the band, would itself have reported such a transfer as UNRESOLVED
    (`test_no_transfer_in_the_boot_chain_is_unresolved`). This is that guarantee restated for the
    band's 144 unwalked bytes as well, over a decode from their declared anchors."""
    suspect = []
    for anchor in UNWALKED_BAND_ANCHORS:
        at = anchor
        while at < DISK_DRIVER_HI:
            word = _word_at(at)
            if word in JSR_JMP_PC_INDEXED or JMP_JSR_INDIRECT_LO <= word < JMP_JSR_INDIRECT_HI:
                suspect.append(at)
            length, text = _decode(at)
            if text.split()[0] in TERMINALS:
                break
            at += length
    assert not suspect, (
        "the disk band's unwalked code contains an unresolvable transfer at %s, so nothing static "
        "can say where it goes" % [hex(a) for a in suspect])


def test_the_disk_band_transfers_out_nowhere():
    """THE OTHER HALF OF THE BOUNDARY, and the stronger fact: the band is a CLOSED SUBGRAPH. Nothing
    inside it branches or calls out — it leaves only by `rts`, back through the seam.

    That is what makes excluding it safe. A boundary whose interior called back into ported code
    would need every such call modelled, and the exclusion would be a hole rather than an edge.

    EVERY HIT IS CLASSIFIED POSITIVELY, and that is a correction. Two earlier revisions asked a
    NEGATIVE question — first "is this an instruction start in a decode from the band's first byte",
    then "is this in REACHED" — and both are satisfied by ignorance. All seven hits are outside
    REACHED, so the second revision's answer was the same whether the address was an operand fragment
    or a real transfer in the 144 band bytes the walk never enters. Each hit now has to NAME the
    instruction that contains it."""
    found = _encoded_transfers(_in_band, lambda a: not _in_band(a))
    assert found, (
        "the encoding scan found nothing at all inside the band, so this case would pass on an empty "
        "set and prove nothing about the classifier")
    stray = [addr for addr in found if _fragment_of(addr) is None]
    assert not stray, (
        "the disk band transfers OUT of itself at %s, so it is not the closed subgraph the boundary "
        "claim needs" % [hex(a) for a in stray])
    # ...and the classification is REPORTED, so a reader can check the enclosing instruction rather
    # than trust that one was found.
    enclosing = {addr: _fragment_of(addr) for addr in found}
    assert all(_decode(at)[1] for at in enclosing.values()), (
        f"an enclosing instruction did not decode: "
        f"{ {hex(a): hex(v) for a, v in enclosing.items()} }")


def test_the_seam_s_inputs_are_file_shaped():
    """WHY THE BOUNDARY FALLS HERE AND NOT A ROUTINE LOWER. `disk_load_file` is entered with a NAME
    and a DESTINATION; everything it calls is entered with tracks, sides and sector counts. The
    evidence is `fat_find_dir_entry`'s comparison — eleven `cmp.b` against a directory entry, taken
    from a0 at offsets 0..7 and 9..11, i.e. the twelve-character name with its dot skipped.

    Derived from the bytes: the case reads the comparison's own displacements out of the image."""
    entry = leaf.entry_of("fat_find_dir_entry")
    compared, at = [], entry
    while at < entry + FAT_FIND_DIR_ENTRY_BYTES:
        length, text = _decode(at)
        if text.startswith("cmp.b") and "(a0)" in text:
            compared.append(0 if text.startswith("cmp.b (a0)") else int(text.split("(a0)")[0]
                                                                        .split()[-1]))
        at += length
    assert compared == FAT_NAME_OFFSETS, (
        f"fat_find_dir_entry compares a0's bytes {compared}, not the 8.3 name's {FAT_NAME_OFFSETS} — "
        f"so the seam's a0 is not a twelve-character DOS name and the substitution's premise is gone")


def test_the_one_reconstructed_routine_inside_the_band_is_not_in_the_excluded_bytes():
    """`floppy_deselect_drives` ($6268) is inside the band's ADDRESS RANGE and is reconstructed —
    batch 42 phase B ported it, because the vblank handler calls it. It is not among the 1,644,
    because the boot chain never reaches it and the sum is over the boot walk's segments.

    Two counts that are both right about different questions, asserted so a reader cannot take
    "1,644 unported bytes in [$5e3e,$6528)" for "every byte in that range is unported"."""
    assert _in_band(FLOPPY_DESELECT_ALL)
    assert FLOPPY_DESELECT_ALL in leaf.ported_entries(), (
        "floppy_deselect_drives is no longer in the built library, so the exception this case is "
        "about has gone and the band really would be wholly unported")
    assert FLOPPY_DESELECT_ALL not in SEGMENTS, (
        f"{FLOPPY_DESELECT_ALL:#x} owns a boot-chain segment, so its bytes ARE in the 1,644 and the "
        f"disk-wall figure double-counts ported code")


# --- the boot's dead tail -------------------------------------------------------------------------

BOOT_TAIL = 0xf89e                     # `lea $22090.l,a0` — the last routine the boot chain calls
BOOT_TAIL_END = 0xf8b8                 # exclusive: `$f8b8` holds the saved a7, not code
BOOT_TAIL_JMP = 0xf8b4                 # `jmp $4a0.w` — its ONLY exit
BOOT_TAIL_CALL = 0xe6fc                # `bsr.w $f89e`, and the `bsr` that never comes back
DEAD_TAIL = (0xe700, 0xe708)           # what follows it, and cannot run
DEAD_TAIL_BYTES = 12


def test_the_boot_s_last_call_never_returns_so_two_instructions_after_it_are_dead():
    """`$f89e` HAS NO `rts`. It sets up three registers, calls `stage_load_window` and then
    `jmp $4a0.w` — so `bsr.w $f89e` at $e6fc pushes a return address nothing ever pops, and the two
    instructions after it never execute.

    ONE OF THEM IS A WRITE. `move.b #$ff,text_request` at $e700 is "dismiss the message box", and it
    is one of the fifty-two writers ../names.txt's `cmt 0xc030` censuses — a writer that cannot fire.
    The other is a second `jmp $4a0.w`, which is why nothing ever noticed: the dead path's
    destination is where control goes anyway.

    IT ALSO SAYS SOMETHING ABOUT THE INVENTORY. The walk is a recursive descent and continues past
    every `bsr`, because deciding otherwise means deciding whether a callee returns. So these twelve
    bytes ARE in the 4,598 — the count is a MAY-EXECUTE inventory and this is what that means in
    practice. Stated here rather than deducted, because the alternative is a walk that has to prove
    non-return for every call it follows."""
    terminals = [addr for addr in range(BOOT_TAIL, BOOT_TAIL_END)
                 if addr in REACHED and _decode(addr)[1].split()[0] in TERMINALS]
    assert not terminals, (
        f"$f89e contains {[hex(a) for a in terminals]}, so it CAN return and the two instructions "
        f"after {BOOT_TAIL_CALL:#x} are not dead after all")
    exits = [addr for addr in range(BOOT_TAIL, BOOT_TAIL_END)
             if addr in REACHED and _decode(addr)[1].startswith(("jmp", "bra"))]
    assert exits == [BOOT_TAIL_JMP], (
        f"$f89e leaves at {[hex(a) for a in exits]}, not only by the `jmp` at {BOOT_TAIL_JMP:#x}")
    assert _decode(BOOT_TAIL_CALL)[1].startswith("bsr"), (
        f"{BOOT_TAIL_CALL:#x} is not the `bsr` this case is about")
    assert all(addr in REACHED for addr in DEAD_TAIL), (
        "the walk no longer continues past the non-returning `bsr`, so this case's point about the "
        "inventory being a may-execute count is stale")
    assert sum(REACHED[addr] for addr in DEAD_TAIL) == DEAD_TAIL_BYTES


# --- the retraction scan --------------------------------------------------------------------------
# THE GREP-TO-ZERO RULE, AS A CASE. Batch 36 made it a rule: a correction is landed when the old
# phrase greps to zero. Batch 44 phase B then broke it three times in one round — every retraction
# NAMED its target by quoting it, so the retired phrase was still in the tree in the very edit that
# retired it — and asserted in ../STATUS.md that the greps were clean. Nobody had run them.
#
# One of the three would have survived a careful grep anyway: the Joust retraction wrapped its
# quotation across an assembler comment prefix, so the phrase existed in two pieces and matched
# nothing. Hence NORMALISED: whitespace and comment furniture (`*`, `|`, `/`) collapse to one space
# before the search, which is what makes a wrapped quotation visible.
RETRACTED_PHRASES = {
    "cmt 0xe5d8's wrap": "wraps to 1 rather than naming a row past the table",
    "cmt 0xe5ba's opener": "UNPORTED, and named from its first six instructions rather than from a "
                           "body read",
    "tos.h's file-call claim": "the reconstruction makes no file call at all",
    "joust_os.s's Super note": "Balanced pairs only",
    # Batch 44 phase C's own two, both caught by the review gate and both retired the same round.
    # The prologue one is the shape this rule is about: the correction was written INTO the same
    # paragraph as the claim, quoting it, so the phrase survived its own retraction twice over.
    "the boot-chain banner's prologue claim": "in the boot's order",
    "the resource-table park's unit": "3,200 LONGWORDS",
    # Batch 44 phase F: PORTABILITY.md's order-mutant row called the mutant a structural
    # on-target survivor; smoke.py m6flash measured it dying. The row's first correction
    # QUOTED the retired verdict inside its own retraction (the rule's oldest failure mode)
    # and was rewritten as a description at the commit gate.
    "PORTABILITY's order-mutant verdict": "SURVIVES ON TARGET TOO, and structurally",
    # Batch 44 phase E's three, all of them the SLICE COUNT: `boot_prompt_screen` made the composed
    # set four, and three surfaces said three. The third is a forward-looking note that came true —
    # ../atari/ now names WB_BOOT_PROMPT_* and calls all four slices — and a note about what a
    # future phase will want is exactly the kind that outlives the phase and stops being read.
    "src/boot.c's slice count": "The three below are the boot ITSELF",
    "include/boot.h's slice count": "ALL THREE RETURN ONE OF THE WB_LOAD_* CODES",
    "include/boot.h's on-target note": "does not name them yet",
    # ...AND THE PHASE-E GATE'S OWN THREE, all of them the prompt's ENTRANCE CENSUS — which was
    # wrong in two different ways across five surfaces (src/boot.c, include/boot.h,
    # include/wonderboy.h, test/test_boot_chain.py and ../names.txt). It counted ONE entrance where
    # the shipped image holds three `jmp $e494.l`, and it identified the one it named ($700e, slot
    # 61's message terminator) as the tail of ESC's music fade — which is $598, three sites away.
    # Two spellings of the second are registered because two surfaces phrased it differently.
    "the prompt's entrance count": "has one entrance",
    "the prompt's entrance identity": "the tail of the music fade",
    "the prompt's entrance identity, wonderboy.h's spelling": "ending's music fade ($700e)",
}
# NOT REGISTERED, AND THE FIRST REASON IS THAT A SCAN CANNOT BE RUN AGAINST A HISTORY. Phase E's
# opening paragraph quoted three of phase D's §7 queue entries verbatim — the play build's staged
# dump, the unported prompt arm, the still-capped fire waits — and the phase-E gate found it. The
# OPENER is rewritten to describe them (that is the defect, and it is fixed), but the phrases
# themselves are registered nowhere: ../STATUS.md is an APPEND-ONLY batch history and phase D's own
# §7 still contains them, where they were true when written. Making those greps reach zero would
# mean editing a closed phase's record of what it knew, which is a worse failure than the one the
# rule prevents. THE HISTORICAL HITS ARE NAMED HERE INSTEAD, which is what the rule asks of a
# correction it cannot enforce: phase D §7, three entries, retired by phase E.
#
# ...AND THE SECOND. Phase C also retired two
# IDENTIFIER spellings — the shim's private title depack destination and palette source, now
# `WB_`-prefixed in include/wonderboy.h. A scan cannot enforce those: the new spelling CONTAINS the
# old one as a substring, so the grep would match every correct use. The rule reaches phrases, not
# renames; the rename's own protection is that the shim no longer defines them (build.sh compiles it).
RETRACTION_SURFACES = (
    "../names.txt", "STATUS.md", "PORTABILITY.md", "src/boot.c", "include/boot.h",
    "include/wonderboy.h", "atari/shim_include/tos.h", "atari/wonderboy_backend.c",
    "atari/README.md", "atari/gen_image.py", "atari/wonderboy_main.c", "../notes/architecture.md",
    "../../../docs/on-target-execution.md", "../../../docs/methodology.md",
    "../../../tools/recreate_kit/TRAP_MODEL.md",
    "../../../projects/joust/recreate/atari/joust_os.s",
)
COMMENT_FURNITURE = re.compile(r"[\s|*/]+")


def _normalised(path):
    """A surface's text with whitespace and comment furniture collapsed, so a phrase broken across
    two lines of a `/* */` or `|` comment still reads as one phrase."""
    return COMMENT_FURNITURE.sub(" ", (HERE / path).read_text())


@pytest.mark.parametrize("what", sorted(RETRACTED_PHRASES))
def test_a_retracted_phrase_is_gone_from_every_surface(what):
    """A retraction that quotes its target has not retired the phrase — it has moved it. Every
    surface this phase writes to is scanned, including the two docs and the sibling project's
    assembler, because a correction landed in one file and re-quoted in another is the shape that
    made ../STATUS.md's own compliance sentence false."""
    phrase = RETRACTED_PHRASES[what]
    present = [path for path in RETRACTION_SURFACES if phrase in _normalised(path)]
    assert not present, (
        f"the retracted phrase for {what} is still present in {present} — a retraction DESCRIBES "
        f"what it corrects, it does not quote it, or the grep the rule asks for cannot reach zero")


def test_the_retraction_scan_can_actually_find_a_phrase():
    """The control. A scan whose surfaces did not exist, or whose normaliser ate the text, would
    report every phrase absent and pass forever — which is the failure mode this whole block is
    about. Plant a phrase that IS in one of the surfaces and require the scan to see it."""
    planted = "the retracted phrase for"          # this file's own diagnostic, three lines up
    hits = [path for path in RETRACTION_SURFACES
            if planted in _normalised("../../../projects/wonderboy/recreate/test/"
                                      "test_boot_inventory.py")]
    assert hits, "the normalised scan cannot find a phrase that is demonstrably present"
    assert len(_normalised(RETRACTION_SURFACES[0])) > 1000, (
        f"{RETRACTION_SURFACES[0]} normalised to almost nothing, so the scan is reading an empty "
        f"surface and every phrase would look absent")
