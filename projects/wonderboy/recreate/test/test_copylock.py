"""The Copylock stub, its witness, and the domain each mechanism is valid over.

`test/copylock.py` offers two ways past the protection and defaults to applying both. This battery
exists because the difference between them is a correctness question, not a preference:

  * the DISARM poke is undone by the game's own `move.w #$ffff,copylock_arm_flag`, so it is useless
    for any run that crosses an arming site — DEMONSTRATED here (a run really does re-arm the flag,
    and the guard on that memory really does enter the blob) rather than argued;
  * the ENTRY_RTS poke patches code, which an arming site does not write, so it survives;
  * and neither is trusted after the fact: every stubbed run is checked against the memory it
    actually left behind, with negative controls proving the check fires on an unstubbed run and
    does NOT fire on the relocator's identity copy of the whole image.

WHAT AN UNSTUBBED RUN DOES, measured below: it enters the blob, saves its registers, takes its two
anti-trace `illegal` exceptions, reaches the decryptor at `$ee02` — and never returns. The reason is
worth knowing before anyone proposes modelling the protection instead: the decryptor works by
setting the trace bit in the exception frame's SR and decrypting one longword per single-step
exception, and the kit's Musashi is built with `M68K_EMULATE_TRACE` OFF, so the trace exception
never fires. Past the second `illegal` the CPU is executing 1,970 bytes of ciphertext as if it were
instructions. `../notes/architecture.md` §2.5's "Musashi can do this" is true of Musashi and false
of this build of it.

IMPORT ORDER IS LOAD-BEARING: `harness` binds the kit (project.load()), and `emu`/`loader` are not
importable before it. An import sorter would break collection.
"""
import pytest

import harness  # noqa: F401  — binds the kit; the imports below only work afterwards
import emu
import loader
import copylock
from leaf import jsr_abs_l, pc_coverage   # the one 68000 encoding this file BUILDS, and the
                                          # arm/reset/disarm of the oracle's PC coverage
from copylock import ARM_FLAG, ARM_FLAG_LEN, ARM_INSN_LEN, ARM_SITES, ARMED, DISARMED, Stub
from copylock import CALL, CODE_END, ENTRY, GUARD, REG_SAVE, REG_SAVE_LEN, REGS_SAVED, SKIPPED
from copylock import DECRYPT_CURSOR, VECTORS, VECTORS_INSTALLED
from layout import wb

WORD = 2                    # a 68000 word: the arm flag's width, and a branch displacement's
LONGWORD = 4                # ...and a longword: an abs.l operand, a saved register, a vector
SCANLINE_COUNT = 200        # the PAL screen the four wipe tables at CODE_END each permute
ABS_L_INSN_LEN = 6          # <opcode word><32-bit absolute operand>
ABS_L_OPERAND_OFF = 2       # ...where that operand sits
BRANCH_W_LEN = 4            # <opcode word><16-bit displacement>
BRANCH_W_BASE_OFF = 2       # a bcc.w displacement is relative to the address of its own extension word
MOVE_W_IMM_OPERAND_OFF = 4  # `move.w #imm,abs.l`: opcode word, immediate word, then the operand

# The 68000 encodings the two mechanisms assume. Every one is checked against the loaded image, with
# the addresses supplied by include/wonderboy.h rather than spelled again here — so a constant that
# drifts fails as a mismatched instruction naming its own address.
TST_W_ABS_L = b"\x4a\x79"
BEQ_W = b"\x67\x00"
CLR_W_ABS_L = b"\x42\x79"
MOVE_W_IMM_ABS_L = b"\x33\xfc"
JMP_ABS_W = b"\x4e\xf8"                           # the blob's last instruction, `jmp $6bb8.w`
MOVEM_L_TO_A6 = b"\x48\xd6"                       # `movem.l <mask>,(a6)`: both of the blob's saves
ALL_REGISTERS_MASK = 0xFFFF                       # ...the first one's mask, d0-a7
SAVED_VECTOR_COUNT = 8                            # ...and what the second one copies: $8..$27
MOVEA_L_POSTINC_A7_A0_RTS = b"\x20\x5f\x4e\x75"   # the guard's two arms rejoin here

# A d0 the protection could never have returned, for the case that shows nothing reads it.
GARBAGE_D0 = 0xDEADBEEF
# A stubbed crossing of the guard retires 2 instructions (DISARM: `tst.w`, `beq`) or 5 (ENTRY_RTS:
# `tst.w`, `beq`, `jsr`, `rts`, `clr.w`). This is the budget the unstubbed control is allowed before
# "it never came back" is called: ~200,000x the honest cost, and about a quarter-second of oracle
# time.
UNSTUBBED_INSN_BUDGET = 1_000_000
# A DISARM run entered at an arming site does come back, in 184,997 instructions. This is that with
# headroom — an allowance for a run that must COMPLETE, which is the opposite of the cap above and
# so deliberately not the same constant: tightening one must not starve the other.
SCRAMBLED_RETURN_INSN_BUDGET = 400_000
# The relocator's copy loop is 3 instructions per longword over WB_BODY_LONGS of them; this is that
# with room to spare, so a run that goes wrong fails on its own terms rather than on the cap.
RELOCATOR_INSN_BUDGET = 400_000

# `movem.l d0-a7,(a6)` stores d0 first, so the saved d1 is the second longword of the save area. It
# is the one field of it the blob loads ITSELF (`move.l #$ffffffff,d1` at $eccc), which is why the
# witness controls below key on it rather than on a register the caller happens to supply.
SAVED_D1 = REG_SAVE + LONGWORD

# THE BLIND WINDOW: every PC from the `jsr`'s destination up to and including the
# `movem.l d0-a7,(a6)` whose completion is the witness's earliest evidence. A run stopped at any of
# them has entered the protection and left the IMAGE untouched, which is the false negative the
# stop_pc guard closes. The window is in TWO pieces — the entry falls through a `bra.s` into a body
# 0x74 bytes further on — and both are walked from a header address (ENTRY forwards, REGS_SAVED
# back) rather than pasted, with the branch that joins them resolved below.
MOVEQ_0_D0 = b"\x70\x00"                          # `moveq #0,d0`, the entry's first instruction
MOVE_L_IMM_D1 = b"\x22\x3c"
MINUS_ONE_L = b"\xff" * LONGWORD                  # the `#$ffffffff` the blob loads into d1 ITSELF
BRA_S = b"\x60"                                   # ...then an 8-bit displacement, resolved below
MOVE_L_A6_PREDEC_A7 = b"\x2f\x0e"                 # a STACK write, and so outside the witness
LEA_PCREL_A6 = b"\x4d\xfa"                        # ...then a 16-bit displacement, resolved below

BRA_AT = ENTRY + len(MOVEQ_0_D0 + MOVE_L_IMM_D1 + MINUS_ONE_L)
MOVEM_AT = REGS_SAVED - (len(MOVEM_L_TO_A6) + WORD)          # opcode word + register mask
LEA_AT = MOVEM_AT - (len(LEA_PCREL_A6) + WORD)               # opcode word + displacement
PUSH_AT = LEA_AT - len(MOVE_L_A6_PREDEC_A7)
BLIND_WINDOW_PCS = (ENTRY, ENTRY + len(MOVEQ_0_D0), BRA_AT, PUSH_AT, LEA_AT, MOVEM_AT)

# What the blob HAS left in the image by REGS_SAVED, one instruction later: the saved d1 (4 B),
# a0 (3 B — its top byte is 0 in a zero-filled save area), a6 (2 B) and a7 (3 B). Twelve bytes is
# the whole durable delta, and handing exactly those back as pokes is how the witness was blinded.
BLOB_DURABLE_DELTA_BYTES = 12


def _image_writes(writes):
    """The run's writes to the program's own address space — what a memory differential compares.

    The oracle's log includes the call frame it pushes for us and the return address the guard's own
    `jsr` pushes, neither of which is output; the kit excludes the same band when it diffs.
    """
    return {a for a in writes if a < emu.STACK_GUARD_LO}


def _run_reaching(entry, witness_pc, **kwargs):
    """`copylock.run` with PC coverage on, plus whether execution reached `witness_pc`.

    The stubbed runs below turn on absences — no writes, no protection — and an absence is also what
    a run that never got started produces, so each one carries the instruction that proves the body
    really ran. It ASKS whether the witness fired rather than requiring it (two cases below expect
    the answer to be no), which is why this is not `leaf.run_reaching`; the arming and resetting the
    two share is `leaf.pc_coverage`.
    """
    with pc_coverage():
        mem, writes, out = copylock.run(entry, **kwargs)
    return mem, writes, out, emu.cov_visited(witness_pc)


def _pcrel_target(opcode_at, disp_at, length):
    """Where the pc-relative instruction at ``opcode_at`` points, from a displacement at ``disp_at``.

    On a 68000 the base is always the word FOLLOWING the opcode word, whichever form is used — so
    one helper serves both the `bra.s` (8-bit displacement inside the opcode word) and the
    pc-relative `lea` (16-bit extension word) that bracket the blind window.
    """
    displacement = int.from_bytes(harness.BASE_IMAGE[disp_at:disp_at + length], "big", signed=True)
    return opcode_at + WORD + displacement


def _flag(image):
    """`copylock_arm_flag`'s two bytes, the one word every case here turns on."""
    return bytes(image[ARM_FLAG:ARM_FLAG + ARM_FLAG_LEN])


def _flag_write_set():
    """The write set of an instruction that stores the flag, and of nothing else."""
    return set(range(ARM_FLAG, ARM_FLAG + ARM_FLAG_LEN))


# The protection armed, as the boot path leaves it before its first resource load.
ARMED_POKES = {ARM_FLAG: ARMED}


def _disarm_run_into_the_blob(site):
    """(before, after) for a DISARM run entered at ``site``, stopped one instruction past the movem.

    The shape three cases need: the disarm poke is undone by the run's own first instruction, so the
    run really does enter the protection, and `REGS_SAVED` is the earliest checkpoint at which the
    witness has anything to see. Taken through `emu.run` because `copylock.run` refuses a checkpoint
    inside the blob — which is the point of that guard, not a limitation to work around.
    """
    before = copylock.stubbed_image(Stub.DISARM, BOOT_PATH_POKES)
    after, _, _ = emu.run(before, site, stop_pc=REGS_SAVED)
    return before, after


def _unstubbed_armed_image():
    """An armed image with NO stub on it — what the negative controls need and nothing else does."""
    return harness.make_image(ARMED_POKES)

# What lets ONE run cross an arming site AND the guard, the way the boot really does.
# `load_resource_by_index` calls `disk_load_file` in between, and that call reaches
# `psg_set_drive_select`, whose read of $ff8800 the oracle refuses outright (PORTABILITY.md §3, T4).
# An `rts` poked over it elides the disk access and nothing else: the loader's `tst.w d0` then sees
# the d0 the run was entered with (0, so the success arm) and falls through to the guard. Eliding it
# is sound for this battery because the only thing it does to `copylock_arm_flag` is nothing — the
# four references to that word are pinned below, and `disk_load_file` is not one of them.
BOOT_PATH_POKES = {copylock.DISK_LOAD_FILE: copylock.RTS}


# ---------------------------------------------------------------------------------------------
# The constants, against the image they describe
# ---------------------------------------------------------------------------------------------

def test_the_guard_is_the_instruction_sequence_both_mechanisms_assume():
    """`tst.w / beq.w / jsr / clr.w`, rebuilt from include/wonderboy.h and matched byte for byte.

    Both mechanisms rest on this shape: DISARM on the `tst.w` reading the address it pokes, and
    ENTRY_RTS on the `jsr` going where it thinks. Rebuilding the encodings from the header's
    addresses (rather than pasting the bytes) is what makes a mistyped constant fail here instead of
    stubbing some other address silently.
    """
    beq_at = GUARD + ABS_L_INSN_LEN
    assert CALL == beq_at + BRANCH_W_LEN, "the guard's jsr is not where the header puts it"
    disarm_at = CALL + ABS_L_INSN_LEN
    assert SKIPPED == disarm_at + ABS_L_INSN_LEN, "the guard's two arms do not rejoin at SKIPPED"

    flag = ARM_FLAG.to_bytes(LONGWORD, "big")
    skip_disp = (SKIPPED - (beq_at + BRANCH_W_BASE_OFF)).to_bytes(WORD, "big")
    for addr, encoding in ((GUARD, TST_W_ABS_L + flag),
                           (beq_at, BEQ_W + skip_disp),
                           (CALL, jsr_abs_l(ENTRY)),
                           (disarm_at, CLR_W_ABS_L + flag),
                           (SKIPPED, MOVEA_L_POSTINC_A7_A0_RTS)):
        assert bytes(harness.BASE_IMAGE[addr:addr + len(encoding)]) == encoding, (
            f"the instruction at {addr:#x} is not the one include/wonderboy.h describes")


def test_both_arming_sites_are_the_same_instruction_writing_the_same_flag():
    """`move.w #$ffff,copylock_arm_flag` at each of the two sites — the reason DISARM has a domain."""
    encoding = MOVE_W_IMM_ABS_L + ARMED + ARM_FLAG.to_bytes(LONGWORD, "big")
    assert len(encoding) == ARM_INSN_LEN
    for site in ARM_SITES:
        assert bytes(harness.BASE_IMAGE[site:site + ARM_INSN_LEN]) == encoding, (
            f"{site:#x} is not the arming instruction include/wonderboy.h describes")


def test_the_flag_and_the_entry_have_exactly_the_references_the_domains_assume():
    """Four writers/readers of the flag, one call to the entry — scanned, not counted by eye.

    DISARM's domain is "no arming site is reachable", which is a statement about the WHOLE image: a
    third arming site anywhere would make the mechanism unsound in a run this battery never tries.
    So the loaded image is swept for every even-aligned occurrence of each address as a 32-bit
    absolute operand.

    Two limits, stated rather than papered over. `abs.w` cannot reach either address (both are above
    $8000, so a word operand would sign-extend into $ffffxxxx) and pc-relative addressing is
    source-only on a 68000, so no pc-relative instruction can WRITE the flag — between them that
    makes `abs.l` the only encoding that can arm it. A register-indirect write (`lea` + `move.w`)
    would still be invisible, exactly as it is to every other operand scan in this project
    (PORTABILITY.md §2).
    """
    expected = {
        ARM_FLAG: {ARM_SITES[0] + MOVE_W_IMM_OPERAND_OFF, ARM_SITES[1] + MOVE_W_IMM_OPERAND_OFF,
                   GUARD + ABS_L_OPERAND_OFF, CALL + ABS_L_INSN_LEN + ABS_L_OPERAND_OFF},
        ENTRY: {CALL + ABS_L_OPERAND_OFF},
    }
    for target, sites in expected.items():
        pattern, found, at = target.to_bytes(LONGWORD, "big"), set(), 0
        while (at := harness.BASE_IMAGE.find(pattern, at)) >= 0:
            if at % 2 == 0:
                found.add(at)
            at += 1
        assert found == sites, (
            f"{target:#x} is referenced as an abs.l operand at {sorted(hex(a) for a in found)}, "
            f"not at the {len(sites)} site(s) the stub's domain analysis assumes")


def test_the_save_area_is_as_long_as_the_two_movems_that_fill_it():
    """`WB_COPYLOCK_REG_SAVE_LEN` = the registers the blob saves, plus the vectors it saves after.

    The first half is pinned from the image: the `movem.l <mask>,(a6)` just before
    `WB_COPYLOCK_REGS_SAVED` must carry the all-registers mask, and its popcount is where 64 of the
    96 bytes come from. The other 32 are the eight exception vectors `$8..$27` that the blob's
    SECOND `movem` copies in, and no run can pin those: they are zeros in a fresh image, so copying
    them changes nothing and the difference witness cannot see it.
    """
    assert bytes(harness.BASE_IMAGE[MOVEM_AT:MOVEM_AT + len(MOVEM_L_TO_A6)]) == MOVEM_L_TO_A6
    mask_at = MOVEM_AT + len(MOVEM_L_TO_A6)
    mask = int.from_bytes(harness.BASE_IMAGE[mask_at:mask_at + WORD], "big")
    assert mask == ALL_REGISTERS_MASK, "the blob no longer saves every register at REGS_SAVED"
    assert REG_SAVE_LEN == LONGWORD * (bin(mask).count("1") + SAVED_VECTOR_COUNT)


def test_the_blind_window_is_the_blobs_entrance_walked_back_from_its_first_image_write():
    """The five PCs the stop_pc guard exists for, each matched against the instruction there.

    `BLIND_WINDOW_PCS` is walked back from `REGS_SAVED` by instruction lengths rather than pasted,
    so a header address that drifted would land the walk on other opcodes and fail here. The `lea`'s
    displacement is resolved too: it is what points `a6` at `copylock_reg_save`, and so what makes
    the `movem` after it the blob's first IMAGE write rather than its first write of anything.
    """
    walk = ((ENTRY, MOVEQ_0_D0),
            (ENTRY + len(MOVEQ_0_D0), MOVE_L_IMM_D1 + MINUS_ONE_L),
            (BRA_AT, BRA_S),
            (PUSH_AT, MOVE_L_A6_PREDEC_A7),
            (LEA_AT, LEA_PCREL_A6),
            (MOVEM_AT, MOVEM_L_TO_A6))
    assert tuple(addr for addr, _ in walk) == BLIND_WINDOW_PCS, (
        "BLIND_WINDOW_PCS is not the set of instructions this case decodes, so the stop_pc guard's "
        "parametrized case is exercising a different window from the one pinned here")
    for addr, encoding in walk:
        assert bytes(harness.BASE_IMAGE[addr:addr + len(encoding)]) == encoding, (
            f"{addr:#x} is not the instruction the blind window walks to")

    bra_target = _pcrel_target(BRA_AT, BRA_AT + len(BRA_S), len(BRA_S))
    assert bra_target == PUSH_AT, (
        f"the bra.s at {BRA_AT:#x} goes to {bra_target:#x}, not to {PUSH_AT:#x} — so the two halves "
        f"of the blind window are not one run of execution and the walk back from REGS_SAVED is "
        f"describing some other code")

    lea_target = _pcrel_target(LEA_AT, LEA_AT + len(LEA_PCREL_A6), WORD)
    assert lea_target == REG_SAVE, (
        "the lea no longer points a6 at copylock_reg_save, so the movem after it writes elsewhere "
        "and the witness is watching the wrong bytes")


def test_an_empty_stub_is_refused_rather_than_applying_nothing():
    """`Stub.DISARM & Stub.ENTRY_RTS` — an `&`-for-`|` typo — must not quietly stub nothing.

    `enum.Flag` answers it with `Stub(0)`, which would otherwise produce an empty poke dict that is
    indistinguishable from a real one at the call site: a run reported as stubbed, unstubbed.
    """
    with pytest.raises(AssertionError, match="applies no poke"):
        copylock.stub_pokes(Stub.DISARM & Stub.ENTRY_RTS)


def test_the_witness_span_ends_where_the_blob_stops_being_code():
    """`CODE_END` is a bound the runs cannot pin, so pin it structurally: code below, tables above.

    Below it, the blob's last instruction is the failure path's `jmp abs.w`; at it, the first of the
    four wipe tables starts, and each of those is a permutation of the 200 scanlines
    (`../notes/architecture.md` §2.5). A permutation is an exact, self-describing signature, so a
    `CODE_END` that drifted in either direction fails here rather than quietly widening or narrowing
    the witness.

    The span deliberately stops short of the blob's `$f89e` end, and this is why: those tables also
    hold `copylock_flag_a`/`copylock_flag_b`, which PLAINTEXT code writes (`clr.w $f89a` at `$fb8a`,
    `st $f89c` at `$fb90`). A witness reaching that far would fire on any run that crossed them.
    """
    assert bytes(harness.BASE_IMAGE[CODE_END - LONGWORD:CODE_END - WORD]) == JMP_ABS_W
    first_table = harness.BASE_IMAGE[CODE_END:CODE_END + SCANLINE_COUNT]
    assert sorted(first_table) == list(range(SCANLINE_COUNT))


def test_the_headers_addresses_are_the_ones_the_name_map_gives():
    """`../names.txt` is this program's source of truth for addresses; the header is a second copy.

    Pinning the two equal is what stops a rename or a correction in the name map from leaving the
    header quietly stale — and it is the ONLY check holding `WB_DISK_LOAD_FILE`, which no encoding
    and no run in this file touches: it is a poke target, so a value that drifted would drop an
    `rts` into the middle of the FDC driver with no diagnostic at all. Measured: moving it six bytes
    on left the whole battery green before this case existed.
    """
    named = {copylock.DISK_LOAD_FILE: "disk_load_file",
             ARM_FLAG: "copylock_arm_flag",
             ENTRY: "copylock_entry",
             REG_SAVE: "copylock_reg_save",
             DECRYPT_CURSOR: "copylock_decrypt_cursor",
             CODE_END: "screen_wipe_order_even_odd"}
    for addr, name in named.items():
        assert harness.NAME_MAP.get(addr) == name, (
            f"include/wonderboy.h puts {name} at {addr:#x}, but ../names.txt calls that address "
            f"{harness.NAME_MAP.get(addr)!r}")


def test_the_shipped_image_ships_the_copylock_disarmed():
    """`copylock_arm_flag` is 0 in the .PRG, so a run entered below an arming site never calls it.

    That makes the DISARM poke a no-op on a fresh image — which is the point of poking it anyway: it
    turns an accident of the shipped bytes into a stated precondition that `copylock.run`'s witness
    then re-checks on every run.
    """
    assert _flag(harness.BASE_IMAGE) == DISARMED


# ---------------------------------------------------------------------------------------------
# The two mechanisms, each over its own domain
# ---------------------------------------------------------------------------------------------

def test_the_disarm_skips_the_copylock_from_a_below_boot_entry():
    """Entered at the guard with the flag armed, DISARM takes the `beq` and the `jsr` never runs.

    The case arms the flag and then asks for DISARM, so the stub poke lands on top of the arming one
    — that collision IS the mechanism, and `stubbed_image` documents the ordering that makes it so.
    Coverage of `copylock_entry` is the control: "no writes" alone is also what a run that fell over
    at its first instruction produces, and here the absence of the call is the entire claim.
    """
    _, writes, _, called = _run_reaching(GUARD, ENTRY, mechanism=Stub.DISARM, pokes=ARMED_POKES,
                                         stop_pc=SKIPPED)
    assert not called, "the guard called copylock_entry despite the flag being poked to 0"
    assert not _image_writes(writes), (
        "the skipped arm of the guard stores nothing, not even the disarming clr.w")


def test_the_entry_stub_lets_the_real_jsr_run_and_the_game_disarm_the_flag():
    """ENTRY_RTS leaves the guard's `jsr` in place; only its destination changes.

    So the run executes `copylock_entry`, returns immediately, and goes on to the `clr.w` the game
    itself uses — i.e. the flag comes back DISARMED through the game's own instruction, and the two
    bytes it writes are the run's entire output. That is what "the protection passed" looks like.
    """
    mem, writes, _, called = _run_reaching(GUARD, ENTRY, mechanism=Stub.ENTRY_RTS,
                                           pokes=ARMED_POKES, stop_pc=SKIPPED)
    assert called, "the jsr did not reach copylock_entry, so the rts poked there proves nothing"
    assert _image_writes(writes) == _flag_write_set()
    assert _flag(mem) == DISARMED


def test_the_entry_stub_can_return_any_d0():
    """The real protection returns a key in d0; an `rts` returns whatever was already there.

    That is only safe because nothing between the `jsr` and the function's own `rts` reads d0 — the
    guard's remaining instructions are `clr.w`, `movea.l (a7)+,a0`, `rts`. Measured by running the
    same case twice with d0 poles apart and requiring the same memory effect. (The two arming call
    sites do not read it either: `$e52a` is a `lea` and `$e6e8` calls `$e87c`, whose first
    instruction pair overwrites d0 with `move.w #$979,d0`. Callers beyond those two are out of this
    case's scope and are recorded as a stub cost in PORTABILITY.md.)
    """
    results = []
    for returned_key in (0, GARBAGE_D0):
        mem, writes, _ = copylock.run(GUARD, mechanism=Stub.ENTRY_RTS, pokes=ARMED_POKES,
                                      regs={"d0": returned_key}, stop_pc=SKIPPED)
        results.append((_image_writes(writes), _flag(mem)))
    assert results[0] == results[1], "the guard's outcome depends on the d0 the stub hands back"


def test_an_arming_site_rewrites_the_flag_the_disarm_poked():
    """The mechanism behind the domain limit: one instruction, and those two bytes are all it writes.

    Run on a DISARM-poked image, so what the assertion measures is the poke being overwritten rather
    than the flag merely holding some value.
    """
    for site in ARM_SITES:
        disarmed = copylock.stubbed_image(Stub.DISARM)
        assert _flag(disarmed) == DISARMED
        mem, writes, _ = emu.run(disarmed, site, stop_pc=site + ARM_INSN_LEN)
        assert _image_writes(writes) == _flag_write_set()
        assert _flag(mem) == ARMED


def test_the_disarm_is_useless_once_a_run_crosses_an_arming_site():
    """The domain limit itself, in ONE run of the boot path's own shape — and it is caught twice.

    Entering at the arming site means the disarm poke is applied before the run and undone by the
    run's first instruction, which is exactly how it would fail in real use. Twice, because the two
    halves say different things:

      * stopped at `REGS_SAVED`, the run has entered the blob and left its register save area
        behind — the earliest point the witness has anything to see, taken through `emu.run` because
        `copylock.run` refuses a checkpoint inside the blob outright (see that guard's own case);
      * allowed to continue, it **comes back**. Unlike the unstubbed run entered at the guard, which
        never reaches the far side at all, this one returns to `SKIPPED` in ~185,000 instructions
        with 2,053 bytes of the protection scrambled behind it. That is a false green in the exact
        shape the witness exists for — a run that finishes and looks ordinary — and `copylock.run`
        refuses it on the memory, not on the diagnostic.
    """
    for site in ARM_SITES:
        before, after = _disarm_run_into_the_blob(site)
        with pytest.raises(AssertionError, match="the protection DID execute"):
            copylock.assert_did_not_execute(before, after, site)

        with pytest.raises(AssertionError, match="the protection DID execute"):
            copylock.run(site, mechanism=Stub.DISARM, pokes=BOOT_PATH_POKES, stop_pc=SKIPPED,
                         max_insns=SCRAMBLED_RETURN_INSN_BUDGET)


@pytest.mark.parametrize("mechanism", (Stub.ENTRY_RTS, Stub.BOTH),
                         ids=("entry_rts", "the default"))
def test_the_entry_stub_holds_where_the_disarm_does_not(mechanism):
    """The same run, past the same arming site, crossing the guard cleanly.

    An arming site writes `copylock_arm_flag`; it does not write `copylock_entry`. That is the whole
    reason one mechanism survives the boot path and the other does not — and the default is included
    as a case in its own right, because "BOTH covers the boot path" is a property of the default and
    not of either half. The flag coming back DISARMED is the positive control: only the guard's
    `jsr`-then-`clr.w` arm writes it, so a run that had skipped the call would leave it armed.
    """
    for site in ARM_SITES:
        mem, writes, _, called = _run_reaching(site, ENTRY, mechanism=mechanism,
                                               pokes=BOOT_PATH_POKES, stop_pc=SKIPPED)
        assert called, "the guard skipped the call, so the arming site did not re-arm the flag"
        assert _flag(mem) == DISARMED


# ---------------------------------------------------------------------------------------------
# The two guards on the witness's INPUTS — each one a demonstrated false negative, closed
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("stop_pc", BLIND_WINDOW_PCS + (REGS_SAVED, CODE_END - WORD),
                         ids=lambda pc: f"{pc:#x}")
def test_a_checkpoint_inside_the_blob_is_refused_rather_than_answered(stop_pc):
    """The blind window at the blob's entrance: six instructions the witness cannot see.

    Every PC in `BLIND_WINDOW_PCS` used to return GREEN with an empty trespass list from a run that
    had executed the guard's `jsr` and up to five instructions of the protection — because the
    instructions before the `movem.l d0-a7,(a6)` write the STACK or nothing at all, and the witness
    watches the image. The two PCs past the window are here so the guard is pinned over the whole
    span and not just the hole that motivated it: `REGS_SAVED` is where the witness DOES fire, and
    `CODE_END - WORD` is the last word of the blob's code.
    """
    with pytest.raises(AssertionError, match="inside the protection itself"):
        copylock.run(ARM_SITES[0], mechanism=Stub.DISARM, pokes=BOOT_PATH_POKES, stop_pc=stop_pc)


def test_the_blobs_own_durable_delta_cannot_be_fed_back_as_pokes():
    """The witness's baseline is a fresh image — but `pokes` landed on BOTH sides of it.

    The reproducer, kept as the regression case: run the protection for real, take the exact bytes
    it durably changed, and hand them back as the case's own pokes. That made `copylock.run` return
    green with the `movem` executed. It is a small set — 12 bytes, the saved `d1`/`a0`/`a6`/`a7` —
    which is why blinding the witness this way was cheap enough to happen by accident.

    The count is asserted rather than assumed: if the blob's early writes ever changed shape, this
    case would silently stop being the reproducer it claims to be.
    """
    before, after = _disarm_run_into_the_blob(ARM_SITES[0])
    delta = copylock.trespasses(before, after)
    assert len(delta) == BLOB_DURABLE_DELTA_BYTES, (
        f"the blob durably changes {len(delta)} byte(s) by {REGS_SAVED:#x}, not "
        f"{BLOB_DURABLE_DELTA_BYTES} — this case no longer reproduces the false negative it pins")

    blinding = {addr: bytes([after[addr]]) for addr in delta}
    with pytest.raises(AssertionError, match="overlaps the witness range"):
        copylock.run(ARM_SITES[0], mechanism=Stub.DISARM, pokes={**BOOT_PATH_POKES, **blinding})


@pytest.mark.parametrize("addr,data", ((REG_SAVE, b"\xde\xad\xbe\xef"),
                                       (ENTRY + WORD, b"\x4e\x71"),
                                       (VECTORS[2], bytes(LONGWORD)),
                                       (ENTRY - WORD, bytes(LONGWORD)),
                                       (CODE_END - 1, bytes(WORD))),
                         ids=("reg_save", "entry_body", "trace_vector",
                              "straddling_the_bottom", "straddling_the_top"))
def test_a_poke_touching_the_witnesss_own_bytes_is_refused(addr, data):
    """...and the guard covers the whole watched span, not just the 12 bytes that exposed it.

    Both spans are represented, and the last two cases are what make this an OVERLAP test rather
    than a containment one: each starts outside the code span and runs into it (from the wipe-table
    pointers below `ENTRY`, and past `CODE_END` into the first wipe table). Written as containment,
    or keyed on the poke's start address alone, the guard passes every other case here and misses
    both of those — measured.
    """
    with pytest.raises(AssertionError, match="overlaps the witness range"):
        copylock.stubbed_image(pokes={addr: data})


def test_a_poke_just_past_the_watched_span_is_still_served():
    """The other side of the guard: it refuses an overlap, not everything near one.

    `CODE_END` itself is the first of the four wipe tables — outside the span by the deliberate
    choice `test_the_witness_span_ends_where_the_blob_stops_being_code` pins — so a poke there must
    still be applied. Without this a guard that refused every poke would pass every case above.
    """
    image = copylock.stubbed_image(pokes={CODE_END: b"\x5a"})
    assert image[CODE_END] == 0x5A


def test_a_poke_dict_passed_where_the_mechanism_goes_is_refused():
    """`mechanism` is the second POSITIONAL parameter, so `run(GUARD, ARMED_POKES)` lands here.

    Without the type check that call stubs NOTHING and still comes back green: `Stub.DISARM in
    <dict>` asks the dict, which answers False without raising, so both mechanisms are skipped and
    the caller's pokes — passed as the mechanism — are never applied either. On a fresh image whose
    flag already reads DISARMED the guard then takes the `beq`, the witness sees no trespass, and
    the run is reported as "armed and stubbed" having been neither.
    """
    with pytest.raises(AssertionError, match="must be a Stub"):
        copylock.stub_pokes(ARMED_POKES)


def test_a_poke_that_partially_overlaps_the_stub_is_refused():
    """An EXACT collision with a stub target is the wanted idiom; a partial overlap has no answer.

    `{ARM_FLAG: ARMED}` under DISARM is the documented case — the stub wins, and that is the point.
    A poke that covers the flag from a NEIGHBOURING address cannot be resolved that way: whichever
    of the two is written second wins, silently, and the run is reported as stubbed with the stub
    (or the case's own setup) partly overwritten. The positive control is the exact-key case, which
    must still be served and must still leave the flag DISARMED.
    """
    with pytest.raises(AssertionError, match="partially overlaps the stub"):
        copylock.stubbed_image(Stub.DISARM, {ARM_FLAG - WORD: ARMED + ARMED})

    assert _flag(copylock.stubbed_image(Stub.DISARM, ARMED_POKES)) == DISARMED


def test_the_stub_builds_its_image_through_the_kits_own_poke_vetting():
    """`stubbed_image` goes through `harness.make_image`, so the kit's guards see the stub's pokes.

    Stated in that function's docstring and, until this case, untested — a rewrite that poked a raw
    `bytearray(harness.BASE_IMAGE)` copy instead left the whole battery green. Wonder Boy is the one
    project whose program covers the harness-poked input block, so `make_image` refusing a poke
    there is a guard that genuinely exists to be bypassed.
    """
    with pytest.raises(RuntimeError, match="harness-poked input block"):
        copylock.stubbed_image(pokes={harness.OS_RANDOM_VALUE: bytes(LONGWORD)})


# ---------------------------------------------------------------------------------------------
# The witness, and the negative controls that make it mean something
# ---------------------------------------------------------------------------------------------

def _covers(hit, slot, length=LONGWORD):
    """Did the witness see any byte of the ``length``-byte field at ``slot`` change?"""
    return any(slot <= a < slot + length for a in hit)


def test_the_witness_fires_three_instructions_into_the_blobs_body():
    """The negative control, at the earliest point it can be taken.

    Three instructions into the body at `$ed46` comes `movem.l d0-a7,(a6)`, and stopping just past
    it shows the witness already has it. The assertion is on the SAVED d1 specifically, because that
    one is caller-independent: the blob executes `move.l #$ffffffff,d1` itself two instructions
    earlier, so those four bytes always differ from the zero-filled save area no matter what
    registers the run was entered with. Running the protection to completion is not an option — see
    the last case — so how early the witness catches on is what makes it usable at all.
    """
    before = _unstubbed_armed_image()
    after, _, _ = emu.run(before, GUARD, stop_pc=REGS_SAVED)

    hit = copylock.trespasses(before, after)
    assert _covers(hit, SAVED_D1), "the saved d1 did not change, so the movem did not happen"
    assert all(REG_SAVE <= a < REG_SAVE + REG_SAVE_LEN for a in hit), (
        "the run changed Copylock bytes outside copylock_reg_save before the movem was even done")
    with pytest.raises(AssertionError, match="the protection DID execute"):
        copylock.assert_did_not_execute(before, after, GUARD)


def test_the_witness_names_every_range_it_watches_once_the_decryptor_is_installed():
    """The same control run on to `$ee1a`, which exercises the OTHER half of the witness.

    By then the protection has finished its 96-byte save area, primed `copylock_decrypt_cursor`, and
    installed all three of its own vectors — `$10` (illegal), `$20` (privilege), `$24` (trace).
    Requiring EVERY range in `WITNESS_RANGES` to have contributed is what stops one from being
    silently dead: without this case the two vector ranges could be deleted outright, or
    `WB_EXCEPTION_VECTOR_LEN` halved, and every other case here would still pass. The per-field
    checks use this file's own `LONGWORD` rather than the header's vector length, so the two cannot
    cancel each other out.
    """
    before = _unstubbed_armed_image()
    after, _, _ = emu.run(before, GUARD, stop_pc=VECTORS_INSTALLED)

    hit = copylock.trespasses(before, after)
    for lo, hi in copylock.WITNESS_RANGES:
        assert any(lo <= a < hi for a in hit), (
            f"nothing in the witness range [{lo:#x},{hi:#x}) changed, so that range is watching "
            f"nothing this control can prove")
    for name, slot in (("the saved d1", SAVED_D1), ("the decrypt cursor", DECRYPT_CURSOR),
                       ("the illegal vector", VECTORS[0]), ("the privilege vector", VECTORS[1]),
                       ("the trace vector", VECTORS[2])):
        assert _covers(hit, slot), f"{name} at {slot:#x} did not change"


def test_the_witness_is_clean_on_the_same_run_stubbed():
    """...and the other half of the control: the identical entry, stubbed, trespasses nowhere.

    Without this the two cases above would only show that SOMETHING changes those bytes.
    `copylock.run` asserts the witness internally, so returning at all is already the result; it is
    restated here against a comparison this case builds itself, so a future change to `run()` cannot
    make the pair vacuous.
    """
    before = copylock.stubbed_image(pokes=ARMED_POKES)
    after, _, _ = copylock.run(GUARD, pokes=ARMED_POKES, stop_pc=SKIPPED)
    assert not copylock.trespasses(before, after)


def test_the_witness_is_not_fooled_by_the_relocators_identity_copy():
    """A memory difference, not a write set — and this is the run that forces the distinction.

    At `load_base = 0x3f8` the relocator's copy of the program body to `$400` is an IDENTITY copy
    (`test_bootstrap.py`), so it writes every byte of the image, all 2,220 of the Copylock's among
    them, 96 of those in `copylock_reg_save`. A write-set witness reports "the protection DID
    execute" for a `move.l (a0)+,(a1)+` loop — measured, before this case existed. The difference
    witness reports nothing, because nothing changed, and the two claims are checked side by side
    here so the distinction cannot quietly regress.
    """
    entry = loader.LOAD_BASE + wb("RELOCATOR_COPY_OFF")
    before = copylock.stubbed_image()
    after, writes, _ = copylock.run(entry, stop_pc=wb("RUNTIME_BASE"),
                                    max_insns=RELOCATOR_INSN_BUDGET)

    assert not copylock.trespasses(before, after)
    in_span = [a for a in writes if any(lo <= a < hi for lo, hi in copylock.WITNESS_RANGES)]
    assert len(in_span) == CODE_END - ENTRY, (
        "the relocator no longer copies over the Copylock, so this case no longer distinguishes a "
        "write-set witness from a difference one")


def test_an_unstubbed_run_never_comes_back():
    """What happens if the stub is simply left off: the run enters the blob and does not return.

    It saves its registers, takes both anti-trace `illegal` exceptions and reaches the decryptor at
    `$ee02` — and then stops being a program, because the decryptor's mechanism is a trace exception
    per instruction and this Musashi is built with trace emulation off (see the module docstring).
    So there is no "diverges quietly" failure mode to worry about here: an unstubbed run is loud.

    A Musashi built with `M68K_EMULATE_TRACE` on would change what this case measures — it would
    then be the fuzzy-sector read that stops the run, not the checkpoint — so it is matched on the
    specific diagnostic rather than on RuntimeError at large. The case below pins that flag itself.
    """
    with pytest.raises(RuntimeError, match="did not reach checkpoint"):
        emu.run(_unstubbed_armed_image(), GUARD, stop_pc=SKIPPED, max_insns=UNSTUBBED_INSN_BUDGET)


def test_the_oracles_cpu_takes_no_trace_exception():
    """`M68K_EMULATE_TRACE=0`, the kit-wide CPU decision this module rests on — RUN, not read.

    The case above measures what an unstubbed run does; this one measures why. Until `kit.mk` pinned
    it with a `-D`, the flag was Musashi's upstream default in a header that is gitignored and cloned
    from HEAD at build time — untracked, unpinned, and asserted nowhere. So it is asserted
    behaviourally: a hand-assembled probe sets the T bit and executes an instruction, with the trace
    vector pointed at a handler that marks the image and clears T on the stacked SR before its `rte`.
    Trace off, the marker stays clear; against a `liboracle.so` built `-DM68K_EMULATE_TRACE=1` it is
    set (measured), so this is a guard and not a tautology.

    It belongs with the Copylock, not only with the kit, because turning the flag on would do more
    than change the case above's diagnostic: it would let the blob self-decrypt, and a Rob Northen
    decryptor that ran to COMPLETION re-encrypts the code span and restores the vectors it saved —
    leaving the witness only the 96-byte save area to see. The stub's whole "forgetting it is loud"
    property rests on this flag.
    """
    SCRATCH = 0x30000                      # free image: above the program (ends 0x218d0) and far
                                           # below the staged-file table (0xbf000); asserted zero
    PROBE_RAN = SCRATCH                    # the two markers come FIRST, because the code that
    TRACE_TAKEN = SCRATCH + 1              # writes them has to name their addresses to assemble
    PROBE = SCRATCH + WORD                 # ...then the code, word-aligned after them
    TRACE_PROBE_INSN_BUDGET = 100          # the probe is 6 instructions; 8 if a trace fires
    ST_ABS_L = b"\x50\xf9"                 # `st addr.l` — stores $ff, the marker value below
    MARKER_SET = 0xFF
    MOVE_W_IMM_SR = b"\x46\xfc"            # privileged; the oracle's CPU starts in supervisor mode
    SR_SUPERVISOR_TRACING = b"\xa7\x00"    # T=1, S=1, interrupts masked
    SR_SUPERVISOR = b"\x27\x00"            # ...and the same with T cleared
    MOVE_W_IMM_A7_IND = b"\x3e\xbc"        # `move.w #imm,(a7)`: the exception frame's saved SR
    NOP, RTE = b"\x4e\x71", b"\x4e\x73"

    def store_marker(addr):
        return ST_ABS_L + addr.to_bytes(LONGWORD, "big")

    probe = (MOVE_W_IMM_SR + SR_SUPERVISOR_TRACING     # arm the trace bit...
             + NOP                                     # ...over one instruction that does nothing
             + MOVE_W_IMM_SR + SR_SUPERVISOR           # disarm it before anything else runs
             + store_marker(PROBE_RAN) + copylock.RTS)
    handler = store_marker(TRACE_TAKEN) + MOVE_W_IMM_A7_IND + SR_SUPERVISOR + RTE
    handler_at = PROBE + len(probe)                    # derived, so the probe cannot outgrow its slot
    scratch_span = handler_at + len(handler) - SCRATCH
    assert not any(harness.BASE_IMAGE[SCRATCH:SCRATCH + scratch_span]), (
        f"the probe's scratch span at {SCRATCH:#x} is no longer free image, so it would be running "
        f"over the game's own bytes")

    image = harness.make_image({PROBE: probe, handler_at: handler,
                                VECTORS[2]: handler_at.to_bytes(LONGWORD, "big")})
    final, _, _ = emu.run(image, PROBE, max_insns=TRACE_PROBE_INSN_BUDGET)

    assert final[PROBE_RAN] == MARKER_SET, "the probe never ran, so its silence proves nothing"
    assert final[TRACE_TAKEN] == 0, (
        "the oracle took a trace exception — its Musashi is built with M68K_EMULATE_TRACE ON. The "
        "kit sets it OFF in tools/recreate_kit/kit.mk's OCFLAGS as a stated modelling decision "
        "(TRAP_MODEL.md); with it on, this project's Copylock stub loses the guarantee its witness "
        "is built on, because a blob that runs to completion covers its own tracks.")
