"""Pin the `tos_poked_input_unused` waiver and the three kit guards that enforce it.

Wonder Boy's program starts at `0x3f8` — it must, because the game runs at the fixed absolute
address `0x400` and everything below that is the 68000 vector page — so the kit's harness-poked
input block (`OS_CON_PENDING`/`OS_CON_CHAR`/`OS_RANDOM_VALUE`/`OS_PSG_REGS`, `0x600..0x61f`, plus
`OS_KBDVBASE` at `0x500`) lies inside its own code. `project.toml` waives the kit's import-time
`load_base >= OS_POKE_BLOCK_END` check by declaring that the game reads none of that state, which
its single-trap image establishes (`test_bootstrap.py`).

If that declaration were ever wrong, the failure mode is the same silent one the heap waiver has:
the block would be read and rewritten over the game's own instructions on both sides, and the
differential would compare two identically corrupted runs. So the flag buys the layout and nothing
else. Three guards enforce it, and they cover the two directions the hazard has:

  * a TEST stages poked input. `harness.console_key()` / `harness.psg_regs()` refuse to build it
    (the friendly early error), and `harness.make_image()` refuses to APPLY any poke landing in the
    block however it was built — which is the layer that matters, because the block holds three
    kinds of state and the kit ships two builders: a hand-written `{OS_RANDOM_VALUE: ...}` dict is
    the only way any project stages an XBIOS Random, and that idiom is in use in Joust's suite.
  * the GAME's own code reads the block. `emu._vet_no_poked_input_read()` reddens any run in which
    a trap did — the half a stage-time check cannot see, and the dangerous half: a `Bconin` in code
    that only exists after a depack reads this program's own (nonzero) instruction bytes, is told a
    keystroke is pending, gets four bytes of code back as the key, and has four more bytes of code
    ZEROED. Both sides do that identically from the same `os.h`, so the diff stays clean.

All three key on the OVERLAP, never on the flag — a project loading clear of the block keeps its
builders whatever its project.toml says. This is the only project the overlap exists for (BuggyBoy
and Joust both load at `0x10000`), so it is the only place the wiring can be exercised — hence a
Wonder Boy test for a kit behaviour, exactly as `projects/joust/recreate/test/test_heap_guard.py` is
for the Malloc one. The pure geometry underneath is pinned kit-side, in
`tools/recreate_kit/test/test_os_map.py`.
"""
import pytest

import harness
import emu
import loader
from recreate_kit import harness as kit_harness   # the guard's internals aren't re-exported by `*`

# A word-aligned longword of poked state, and a poke of one: what every case below stages.
POKE_LEN = 4
STAGED_LONGWORD = (0x12345678).to_bytes(POKE_LEN, "big")

# 68000 snippets that reach the poked block through a trap, assembled by hand: ONE PER TRAP the
# oracle's g_poked_input_calls tally counts, so that deleting any single increment in shim.c fails a
# named case here. Each is poked over the program's own entry (make_image hands out a throwaway copy)
# and run from there. `3f3c iiii` is `move.w #iiii,-(a7)`; `4e4d`/`4e4e` are trap #13/#14 (BIOS /
# XBIOS) and `4e41` is trap #1 (GEMDOS); `548f`/`588f`/`5c8f` pop 2/4/6 bytes; `4e75` is rts.
CRAWIO_READ = 0x00ff                # os.h OS_CRAWIO_READ; any other argument is a char to WRITE
TRAPS_READING_THE_BLOCK = {
    "bconstat": b"\x3f\x3c\x00\x02\x3f\x3c\x00\x01\x4e\x4d\x58\x8f\x4e\x75",  # Bconstat(CON)
    "bconin":   b"\x3f\x3c\x00\x02\x3f\x3c\x00\x02\x4e\x4d\x58\x8f\x4e\x75",  # Bconin(CON)
    "crawio":   b"\x3f\x3c\x00\xff\x3f\x3c\x00\x06\x4e\x41\x58\x8f\x4e\x75",  # Crawio(READ)
    "random":   b"\x3f\x3c\x00\x11\x4e\x4e\x54\x8f\x4e\x75",                  # XBIOS Random
    "giaccess": b"\x3f\x3c\x00\x00\x3f\x3c\x00\x00\x3f\x3c\x00\x1c"           # Giaccess(0, reg 0)
                b"\x4e\x4e\x5c\x8f\x4e\x75",
    "kbdvbase": b"\x3f\x3c\x00\x22\x4e\x4e\x54\x8f\x4e\x75",                  # XBIOS Kbdvbase
}
BIOS_BCONIN = TRAPS_READING_THE_BLOCK["bconin"]
# The one console trap that reads NOTHING: Crawio with any argument but OS_CRAWIO_READ writes a
# character to the screen. Tallying it would redden a run for printing.
GEMDOS_CRAWIO_WRITE = b"\x3f\x3c\x00\x41\x3f\x3c\x00\x06\x4e\x41\x58\x8f\x4e\x75"   # Crawio('A')
TRAP_SNIPPET_INSN_CAP = 64          # any of these retires under ten instructions


def test_the_waiver_is_armed_for_this_project():
    """Without the overlap the cases below would pass for the wrong reason (nothing to waive)."""
    assert loader.LOAD_BASE < harness.OS_POKE_BLOCK_END, (
        "the poked-input block now sits below Wonder Boy's program — the waiver in project.toml is "
        "unnecessary, and this file no longer tests anything")
    assert kit_harness._CFG.tos_poked_input_unused is True


def test_without_the_waiver_the_kit_refuses_to_bind_this_project():
    """The import-time check is real, not merely satisfied: turn the flag off and it fires.

    `_vet_os_memory_map()` runs once at import, so re-running it by hand is the only way to see
    what the unwaived project would have got.
    """
    kit_harness._CFG.tos_poked_input_unused = False
    try:
        with pytest.raises(RuntimeError, match="harness-poked input block"):
            kit_harness._vet_os_memory_map()
    finally:
        kit_harness._CFG.tos_poked_input_unused = True


@pytest.mark.parametrize("build_poke, what", (
    (lambda: harness.console_key("A", 0x1e), "a console keystroke"),
    (lambda: harness.psg_regs({7: 0x3f}), "the YM2149 register file"),
))
def test_staging_poked_input_is_refused(build_poke, what):
    """Both builders refuse while the block lies in the program, naming what was staged."""
    with pytest.raises(RuntimeError, match="tos_poked_input_unused"):
        build_poke()
    with pytest.raises(RuntimeError, match=what):
        build_poke()


# ---------------------------------------------------------------------------------------------
# A poke that never goes through a builder — the layer the builders cannot cover
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("addr", (harness.OS_CON_PENDING, harness.OS_CON_CHAR,
                                  harness.OS_RANDOM_VALUE, harness.OS_PSG_REGS))
def test_a_hand_written_poke_into_the_block_is_refused_when_applied(addr):
    """The three kinds of staged state, written straight into a poke dict.

    `OS_RANDOM_VALUE` is the load-bearing one: the kit ships no `random_value()` builder, so this is
    the ONLY way to stage an XBIOS Random and the builder-level check could never see it. Before
    make_image() checked, this call silently overwrote four bytes of the game's own code.
    """
    with pytest.raises(RuntimeError, match="harness-poked input block"):
        harness.make_image({addr: STAGED_LONGWORD})


def test_a_poke_into_the_program_away_from_the_block_is_still_allowed():
    """The guard is scoped to the block, not to the program.

    Poking the program's own bytes is ordinary and deliberate here — `test_bootstrap.py` pokes an
    `rts` over the entry and a corrupted byte into the relocator's source — so a check that refused
    every poke overlapping the program would refuse legitimate cases. It is the kit's model state
    landing on the game's code that is the hazard.
    """
    img = harness.make_image({loader.LOAD_BASE: STAGED_LONGWORD})
    assert bytes(img[loader.LOAD_BASE:loader.LOAD_BASE + POKE_LEN]) == STAGED_LONGWORD


# ---------------------------------------------------------------------------------------------
# The other direction: the GAME's own code reading the block
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", TRAPS_READING_THE_BLOCK.values(),
                         ids=TRAPS_READING_THE_BLOCK.keys())
def test_a_trap_reading_the_block_reddens_the_run(code):
    """A run whose code reads poked input is thrown away, not diffed. The per-run half of the claim.

    Nothing a test stages is involved: the image is untouched apart from the snippet, and the trap
    reads the program's own bytes. Without this guard the run comes back clean and green.

    One case per counted trap — the six the waiver's claim names — because the oracle's tally is six
    separate increments in shim.c's three trap switches, and nothing else in any suite reaches four
    of them: BuggyBoy's and Joust's guard is disarmed by their layout, so deleting an increment would
    otherwise leave the whole tree green.
    """
    with pytest.raises(AssertionError, match="harness-poked input block"):
        emu.run(harness.make_image({loader.LOAD_BASE: code}), loader.LOAD_BASE,
                max_insns=TRAP_SNIPPET_INSN_CAP)


def test_writing_a_character_to_the_console_is_not_a_read():
    """Crawio's WRITE direction touches no poked state, so it must not redden the run.

    `os_crawio` returns at once for any argument but OS_CRAWIO_READ (os.h) — it neither reads the
    block nor consumes a staged key. Tallying the trap number rather than the direction would make
    the waiver un-holdable for a program that merely prints, and the diagnostic would accuse it of a
    read it never made.
    """
    _, _, out = emu.run(harness.make_image({loader.LOAD_BASE: GEMDOS_CRAWIO_WRITE}),
                        loader.LOAD_BASE, max_insns=TRAP_SNIPPET_INSN_CAP)
    assert out["poked_input_calls"] == 0
    assert out["d0"] == 0, "Crawio's write direction returns 0 and reports no keystroke"


def test_the_run_guard_is_load_bearing(monkeypatch):
    """The negative control: with the guard disarmed, that same Bconin run passes — and corrupts.

    This is the false green in full. `OS_CON_PENDING` holds the program's own instruction bytes,
    which are nonzero, so the model reports a keystroke pending, returns four bytes of the game's
    code as the key, and clears four bytes of code. The run is green and proves nothing; the
    assertions below measure exactly that, so the guard above cannot become decorative.
    """
    pending_before = bytes(harness.BASE_IMAGE[harness.OS_CON_PENDING:harness.OS_CON_CHAR])
    assert any(pending_before), (
        "OS_CON_PENDING reads as zero in this image, so the model would report 'no key' and refuse "
        "— the false green this case demonstrates depends on the program's bytes being nonzero")

    monkeypatch.setattr(emu, "poked_input_overlaps_program", lambda: False)
    final, _, _ = emu.run(harness.make_image({loader.LOAD_BASE: BIOS_BCONIN}), loader.LOAD_BASE,
                          max_insns=TRAP_SNIPPET_INSN_CAP)

    assert not any(final[harness.OS_CON_PENDING:harness.OS_CON_CHAR]), (
        "Bconin did not consume the pending flag — the demonstration no longer shows the hazard")


def test_a_run_that_touches_no_poked_input_stays_green():
    """The guard keys on a trap actually being served, so an ordinary run is unaffected.

    Without this the two cases above would pass for a project whose every run raised.
    """
    rts = b"\x4e\x75"
    _, _, out = emu.run(harness.make_image({loader.LOAD_BASE: rts}), loader.LOAD_BASE,
                        max_insns=TRAP_SNIPPET_INSN_CAP)
    assert out["poked_input_calls"] == 0
