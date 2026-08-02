"""How SWB.PRG becomes a running image — held against the original 68000 code.

This is the project's foundation battery: nothing is reconstructed yet, so every case here runs the
ORIGINAL machine code under the Musashi oracle (or reads the loaded image the oracle runs on) and
pins what it does. Four things are established:

  * the loader places the file image where project.toml says and applies exactly the three
    relocations the header declares;
  * the entry trampoline and the relocator at the end of the text really do copy the program's body
    to the absolute address 0x400 and jump there — and at load_base 0x3f8 that copy is an IDENTITY
    copy, which is what makes the loaded image the runtime image (see include/wonderboy.h);
  * the addresses so obtained are the ones ../names.txt is written at — the kit reads that file for
    its diff labels, so a load base that disagreed with it would mislabel every future diff;
  * the game issues exactly one TOS trap in its whole image, GEMDOS Super — which is the evidence
    behind BOTH of project.toml's waivers, and also the kit's first blocker here, since the trap
    model refuses this game's Super argument.

Every constant comes from include/wonderboy.h through layout.wb(); the expected body bytes come
from the .PRG file itself, so a case fails on a wrong or corrupted image rather than comparing the
image against itself. test_the_body_copy_check_is_load_bearing measures exactly that.

IMPORT ORDER IS LOAD-BEARING: `harness` must be imported first (it calls project.load(), which binds
loader.LOAD_BASE/IMAGE_SIZE and puts the kit's oracle/ and tools/ on sys.path). `emu` raises at
import time otherwise, and `loader`/`prg_dis` are not importable at all. An import sorter would break
collection.
"""
from pathlib import Path

import pytest

import harness  # noqa: F401  — binds the kit; the three imports below only work afterwards
import emu
import loader
import prg_dis
from layout import wb

PRG_BYTES = Path(harness.PRG).read_bytes()
HEADER = prg_dis.parse_header(PRG_BYTES)
RELOC_OFFSETS = prg_dis.parse_reloc(PRG_BYTES, HEADER)
TEXT = PRG_BYTES[loader.HEADER:loader.HEADER + HEADER["tlen"]]

LONGWORD = 4                   # a 68000 longword, the width of every relocation fixup
LOAD_BASE = loader.LOAD_BASE
RUNTIME_BASE = wb("RUNTIME_BASE")
BODY_SRC_OFF = wb("BODY_SRC_OFF")
BODY_LEN = wb("BODY_LEN")

# The same text as the 68000 actually sees it — relocated, at LOAD_BASE. TEXT is what the file says;
# this is what runs, and the two differ in exactly the three fixed-up longwords (proved by
# test_the_loader_changed_exactly_the_three_relocated_longwords).
RELOCATED_TEXT = bytes(harness.BASE_IMAGE[LOAD_BASE:LOAD_BASE + HEADER["tlen"]])

# What the relocator must leave at RUNTIME_BASE, taken from the FILE rather than from the image the
# run itself started with. No relocation fixup lands inside the copied body (asserted below), so the
# runtime bytes are the raw file bytes — independent of load_base.
EXPECTED_BODY = TEXT[BODY_SRC_OFF:BODY_SRC_OFF + BODY_LEN]

# `emu.run` reports one MORE loop pass than the instructions the program retired: the oracle's run
# loop spends its first pass on Musashi's reset sequence without retiring anything (shim.c's osh_run
# counts passes, not instructions). CAVEAT for later batteries — a SERVICED TRAP is also a pass that
# retires no instruction, so a run that traps costs one extra per trap on top of this. Neither run
# below traps, and the pin measures the trap-free case only.
ORACLE_RUN_LOOP_OVERHEAD_INSNS = 1

# The relocator's cost, derived from its own encoding.
RELOCATOR_SETUP_INSNS = 4    # move.w #$2700,sr ; lea ; lea ; move.l #count,d0
RELOCATOR_LOOP_INSNS = 3     # move.l (a0)+,(a1)+ ; subq.l #1,d0 ; bne
RELOCATOR_TAIL_INSNS = 1     # jmp $400.l, the instruction the checkpoint stops in front of
EXPECTED_RELOCATOR_INSNS = (RELOCATOR_SETUP_INSNS
                            + RELOCATOR_LOOP_INSNS * wb("BODY_LONGS")
                            + RELOCATOR_TAIL_INSNS)
# A run that goes wrong should fail on its own terms rather than on the cap, so leave wide margin.
INSN_CAP_MARGIN = 4
RELOCATOR_INSN_CAP = INSN_CAP_MARGIN * EXPECTED_RELOCATOR_INSNS


def _insns_retired(out_regs):
    """Instructions the program actually executed, net of the oracle's run-loop overhead."""
    return out_regs["ninsns"] - ORACLE_RUN_LOOP_OVERHEAD_INSNS


def _run_relocator(pokes=None):
    """Run the relocator's copy loop under the oracle, stopping where it jumps into the body.

    Entry is WB_RELOCATOR_COPY_OFF — one instruction past the `trap #1` the kit's trap model
    refuses (test_the_games_only_trap_is_a_super_the_kit_refuses pins that refusal). Skipping it
    costs nothing: Musashi runs the whole program in supervisor mode already, and the trap's only
    other effect is to set a supervisor stack the harness does not use.
    """
    img = harness.make_image(pokes)
    return emu.run(img, LOAD_BASE + wb("RELOCATOR_COPY_OFF"),
                   stop_pc=RUNTIME_BASE, max_insns=RELOCATOR_INSN_CAP)


# ---------------------------------------------------------------------------------------------
# The loaded image
# ---------------------------------------------------------------------------------------------

def test_the_header_is_the_one_the_layout_constants_were_read_from():
    """include/wonderboy.h's view of the .PRG, against the file's own header and reloc table."""
    assert HEADER["tlen"] == wb("TEXT_LEN")
    assert HEADER["dlen"] == 0 and HEADER["blen"] == 0, "the layout assumes text-only: no data, no bss"
    assert len(RELOC_OFFSETS) == wb("RELOC_COUNT")
    assert wb("ENTRY_JMP_OPERAND_OFF") in RELOC_OFFSETS
    assert BODY_LEN == wb("BODY_LONGS") * LONGWORD, "the header's two spellings of the body size"
    assert BODY_SRC_OFF + BODY_LEN == wb("RELOCATOR_OFF"), "the body runs up to the relocator"
    assert loader.PROGRAM_END == LOAD_BASE + wb("TEXT_LEN")


def test_the_load_base_makes_the_loaded_image_the_runtime_image():
    """`load_base + WB_BODY_SRC_OFF == WB_RUNTIME_BASE` — the whole reason the base is 0x3f8.

    With that identity the relocator's source and destination coincide, so the program's own
    absolute operands address the loaded image directly and no staging step is needed. Losing it
    (a load base moved back to the workspace default) is the single change that would invalidate
    every future differential case here, so it is asserted rather than left implicit.
    """
    assert LOAD_BASE + BODY_SRC_OFF == RUNTIME_BASE


def test_the_loader_changed_exactly_the_three_relocated_longwords():
    """The image is the file's text verbatim apart from the three fixups, each += load_base.

    This is what makes EXPECTED_BODY legitimate: it also proves no fixup lands inside the copied
    body, so the runtime bytes are the raw file bytes.
    """
    expected = bytearray(TEXT)
    for off in RELOC_OFFSETS:
        raw = int.from_bytes(TEXT[off:off + LONGWORD], "big")
        expected[off:off + LONGWORD] = ((raw + LOAD_BASE) & 0xFFFFFFFF).to_bytes(LONGWORD, "big")
    assert bytes(harness.BASE_IMAGE[LOAD_BASE:LOAD_BASE + wb("TEXT_LEN")]) == bytes(expected)

    fixed_up = {off + i for off in RELOC_OFFSETS for i in range(LONGWORD)}
    body = set(range(BODY_SRC_OFF, BODY_SRC_OFF + BODY_LEN))
    assert not (fixed_up & body), "a relocation lands inside the body the relocator copies"


def test_the_addresses_agree_with_the_name_map():
    """../names.txt is the source of truth for names, and the kit labels every diff from it.

    A load base that disagreed with it would still run — the harness only reads the file for labels
    and for its exclude-band vetting — and would mislabel every future report. So the two anchors
    the name map and this header both describe are checked equal.
    """
    assert harness.NAME_MAP[LOAD_BASE + wb("RELOCATOR_OFF")] == "startup_relocate_and_run"
    assert harness.NAME_MAP[RUNTIME_BASE] == "cold_start"


# ---------------------------------------------------------------------------------------------
# The original code, under the oracle
# ---------------------------------------------------------------------------------------------

def test_the_oracle_reports_one_pass_more_than_it_retires():
    """Pin ORACLE_RUN_LOOP_OVERHEAD_INSNS against a program whose length is not in doubt.

    A bare `rts` retires one instruction; anything the two instruction-count assertions below
    inherit from the harness is measured here instead of assumed there. It is poked over the
    program's own entry, which costs nothing: make_image() hands out a throwaway copy.
    """
    rts, rts_insns = b"\x4e\x75", 1
    _, _, out = emu.run(harness.make_image({LOAD_BASE: rts}), LOAD_BASE,
                        max_insns=INSN_CAP_MARGIN * rts_insns)
    assert _insns_retired(out) == rts_insns


def test_the_entry_trampoline_reaches_the_relocator():
    """`move.w d0,d0` + `jmp $213e0.l` — and the jmp's target is a relocated longword.

    Reaching the checkpoint at all is the assertion: the oracle raises when it does not, and it
    could only get there through the fixup applied at WB_ENTRY_JMP_OPERAND_OFF.
    """
    entry_insns = 2
    _, writes, out = emu.run(harness.make_image(), LOAD_BASE + wb("ENTRY_OFF"),
                             stop_pc=LOAD_BASE + wb("RELOCATOR_OFF"),
                             max_insns=INSN_CAP_MARGIN * entry_insns)
    assert _insns_retired(out) == entry_insns
    assert not writes, "the trampoline stores nothing"


def test_the_relocator_copies_the_body_to_its_runtime_base():
    """The program moves itself to the ABSOLUTE address 0x400 and jumps there.

    Checked three ways: the destination holds the file's own body bytes; the neighbouring bytes on
    both sides are UNTOUCHED (compared against the pre-run image, not against zero — at this load
    base both neighbours are program bytes); and the write set is exactly the destination range.

    At load_base 0x3f8 source and destination coincide, so this is an identity copy. That does not
    weaken the case — the write set and the instruction count still pin the length and the trip
    count, and the negative control below shows the byte comparison is live.
    """
    final, writes, out = _run_relocator()

    assert bytes(final[RUNTIME_BASE:RUNTIME_BASE + BODY_LEN]) == EXPECTED_BODY
    assert final[RUNTIME_BASE - 1] == harness.BASE_IMAGE[RUNTIME_BASE - 1], "wrote below the destination"
    body_end = RUNTIME_BASE + BODY_LEN
    assert final[body_end] == harness.BASE_IMAGE[body_end], "wrote past the destination"
    assert set(writes) == set(range(RUNTIME_BASE, body_end))
    assert _insns_retired(out) == EXPECTED_RELOCATOR_INSNS


def test_the_body_copy_check_is_load_bearing():
    """A negative control: corrupt one source byte and the copy check must notice.

    Without this the case above could be comparing the image with itself. The corrupted byte is
    poked into the image, so the run copies it faithfully and the comparison against the FILE's
    bytes is the only thing that can catch it — which is the property being proved.
    """
    corrupt_off = BODY_SRC_OFF + BODY_LEN // 2
    corrupt_at = LOAD_BASE + corrupt_off
    flipped = bytes([harness.BASE_IMAGE[corrupt_at] ^ 0xFF])

    final, _, _ = _run_relocator({corrupt_at: flipped})

    copied = bytes(final[RUNTIME_BASE:RUNTIME_BASE + BODY_LEN])
    assert copied != EXPECTED_BODY, "a corrupted source produced the expected body — the check is vacuous"
    differing = [i for i in range(BODY_LEN) if copied[i] != EXPECTED_BODY[i]]
    assert differing == [corrupt_off - BODY_SRC_OFF]


def test_the_games_only_trap_is_a_super_the_kit_refuses():
    """Entering one instruction earlier runs the `trap #1`, and the trap model rejects the run.

    The argument is the program's own end address (a relocated operand), which real GEMDOS takes as
    "enter supervisor mode with THIS supervisor stack". The kit's Super is a token model that
    accepts only 0, 1 and its own cookie (TRAP_MODEL.md Phase 2), so it refuses — correctly, since
    fabricating a result is the one thing the model must not do. This is a KIT limitation and the
    first blocker for this project; it is pinned here so that a change to the model shows up as a
    failing case rather than as a silently different run.
    """
    with pytest.raises(RuntimeError, match="unmodeled OS behaviour"):
        emu.run(harness.make_image(), LOAD_BASE + wb("RELOCATOR_OFF"),
                stop_pc=RUNTIME_BASE, max_insns=RELOCATOR_INSN_CAP)


# ---------------------------------------------------------------------------------------------
# The evidence behind project.toml's two waivers
# ---------------------------------------------------------------------------------------------

TRAP_OPCODE_BASE = 0x4E40      # `trap #N` encodes as 0x4e40 + N, N in 0..15
TRAP_VECTOR_COUNT = 16
GEMDOS_TRAP = 1                # the trap vector GEMDOS is reached through
GEMDOS_SUPER = 0x20
# `move.w #<selector>,-(a7)` — the in-line push every GEMDOS call site here uses.
PUSH_SELECTOR_W = b"\x3f\x3c"
SELECTOR_BYTES = 2             # the GEMDOS selector is the word that immediate pushes
MEMORY_SELECTORS = {"Malloc": 0x48, "Mfree": 0x49, "Mshrink": 0x4A}
PRINTABLE = range(0x20, 0x7F)
# Every even-aligned `trap #N` byte pattern in the image, pinned BY OFFSET. A `trap #N` encoding
# always reads as two printable letters ('N' plus '@'..'O'), so it turns up inside the game's message
# tables; classifying purely by a printable-run heuristic would leave every long text run a blind
# window in which a real trap could hide. Listing the hits instead means a second trap anywhere —
# including inside a string — fails this case.
EVEN_ALIGNED_TRAP_PATTERNS = {
    wb("SUPER_TRAP_OFF"): GEMDOS_TRAP,   # the real one: GEMDOS Super
    0xA40A: 9,     # "MYCO-NI-D MASTER!"
    0xA492: 9,     # "RED K-NI-GHT!"
    0xADAC: 9,     # " THE RED K-NI-GHT"
    0xA668: 7,     # "GIANT CO-NG-!"
}
# ...and the run length that separates the four text hits (12..16 bytes) from the real trap (4:
# " NAF", bounded below by the 0x00 of its own `move.w #$20,-(a7)` and above by the 0xfc of the
# following `move.w #$2700,sr`). Both tests are applied, so neither the list nor the rule stands
# alone.
MIN_TEXT_RUN = 8


def _even_aligned(haystack, pattern):
    """Offsets of ``pattern`` in ``haystack`` that a 68000 could actually execute (word-aligned)."""
    found, at = [], haystack.find(pattern)
    while at >= 0:
        if at % 2 == 0:
            found.append(at)
        at = haystack.find(pattern, at + 1)
    return found


def _trap_hits(haystack):
    """{offset: vector} for every ``trap #N`` encoding a 68000 could execute in ``haystack``."""
    return {at: vector
            for vector in range(TRAP_VECTOR_COUNT)
            for at in _even_aligned(haystack, (TRAP_OPCODE_BASE + vector).to_bytes(2, "big"))}


def _printable_run_length(at):
    """Length of the maximal printable-ASCII run containing ``at``."""
    lo, hi = at, at
    while lo > 0 and TEXT[lo - 1] in PRINTABLE:
        lo -= 1
    while hi < len(TEXT) and TEXT[hi] in PRINTABLE:
        hi += 1
    return hi - lo


def test_the_image_contains_exactly_one_executable_trap_and_it_is_super():
    """The whole 136 KiB image issues ONE TOS call. Everything else is direct hardware access.

    A byte scan, not a disassembly listing: a linear sweep silently drops trap sites after
    desyncing on data (docs/m68k-disassembly.md). This is the evidence behind BOTH waivers in
    project.toml — a Malloc and a poked-input read alike need a trap, and there is only this one.
    """
    hits = _trap_hits(TEXT)
    assert hits == EVEN_ALIGNED_TRAP_PATTERNS, "the set of even-aligned trap encodings moved"

    executable = [at for at in hits if _printable_run_length(at) < MIN_TEXT_RUN]
    assert executable == [wb("SUPER_TRAP_OFF")]
    assert hits[wb("SUPER_TRAP_OFF")] == GEMDOS_TRAP

    at = wb("SUPER_TRAP_OFF")
    super_push = PUSH_SELECTOR_W + GEMDOS_SUPER.to_bytes(SELECTOR_BYTES, "big")
    assert TEXT[at - len(super_push):at] == super_push


def test_the_trap_inventory_survives_relocation():
    """The step that carries the case above from "the file" to "what the CPU runs".

    That scan reads the .PRG's bytes; the 68000 executes the RELOCATED image, in which three
    longwords have had load_base added to them (`0x213e0 -> 0x217d8` at the entry trampoline's jmp
    operand, `0x214d8 -> 0x218d0` at Super's argument, and `0x8 -> 0x400` at the relocator's source
    `lea`). A fixup rewrites four bytes, so it could in principle erase a `trap #N` encoding or
    manufacture one — and either would break both of project.toml's waivers, which rest on the count
    being exactly one. Re-running the identical scan over the loaded image settles it by
    measurement rather than by argument.
    """
    assert _trap_hits(RELOCATED_TEXT) == EVEN_ALIGNED_TRAP_PATTERNS, (
        "relocation created or destroyed a trap encoding — the trap inventory holds for the file "
        "but not for the image that actually runs")


def test_the_super_argument_is_the_first_byte_past_the_program():
    """`move.l #WB_SUPER_STACK_OPERAND,-(a7)` — encoded raw, seen by the trap as +load_base.

    The operand is one of the three relocation fixups, so the two spellings differ; both are pinned
    because a reconstruction reading only one of them would be off by the load base.
    """
    operand_off = wb("RELOCATOR_OFF") + 2        # past the `move.l #imm,-(a7)` opcode word
    assert operand_off in RELOC_OFFSETS
    encoded = int.from_bytes(TEXT[operand_off:operand_off + LONGWORD], "big")
    assert encoded == wb("SUPER_STACK_OPERAND") == wb("TEXT_LEN")

    at = LOAD_BASE + operand_off
    seen = int.from_bytes(bytes(harness.BASE_IMAGE[at:at + LONGWORD]), "big")
    assert seen == LOAD_BASE + wb("SUPER_STACK_OPERAND") == loader.PROGRAM_END


def test_the_image_never_asks_gemdos_for_memory():
    """No Malloc/Mfree/Mshrink selector push anywhere, at any alignment.

    CORROBORATION, not the waiver's evidence: the waiver rests on there being exactly one trap
    instruction in the image (above), which no selector encoding can get around. This scan sees only
    the in-line `move.w #sel,-(a7)` form and would miss a selector built in a register — but it is
    the form every GEMDOS site in this image uses, and it is cheap.
    """
    for name, selector in MEMORY_SELECTORS.items():
        pattern = PUSH_SELECTOR_W + selector.to_bytes(SELECTOR_BYTES, "big")
        assert pattern not in TEXT, f"a GEMDOS {name} selector push is present after all"
