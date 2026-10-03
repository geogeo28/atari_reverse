"""`src/vdi/escape.S` — the VDI escape's own code as the ROM spells it, which the target build ships because its C
measures over Tier 3's 1.10 bar (`include/transcribed.h`), and the thunks through which it reaches the console.

Two claims hold it. Its WORDS are the ROM's, span by span, save the references that measure to where escape.S is
linked — the table's twenty displacements, the `beq.w` to v_fontinit, and the branches into the VT52 console —
each relocated to its exact value: the arm of another span it names, or the THUNK that reaches the console's C
body the ROM's code there is. And it BEHAVES as the ROM over every row Tier 3 prices, through the transcription
relation: the same image and the same register file, less what the layout or the C decides —

* D0, where an arm ends without writing it: the dispatch leaves the table's own displacement there, which is a
  distance between two of escape.S's labels (the CODE-POINTER CALLER's rule, `transcription.code_pointer_stub`: a register
  is cleared only where it holds a fact about the layout — a code address there, a code distance here);
* the registers a console arm's C body leaves, where the ROM's body left its own (the ROM's moves and clears use
  D0-D7/A0-A3/A5 as scratch; the C keeps what the GCC ABI keeps). What the escape's own instructions leave is
  still compared — A4, the console block, and A6 — and the body's work is the image, compared byte for byte.

Each ARM's mask is MEASURED (`test_each_arm_s_mask_is_what_the_two_measurably_disagree_in`): the union, over that
arm's cases, of the registers the ROM and escape.S leave different, and nothing more — so the arms that are the
escape's own code alone (the inquiries, v_hardcopy, v_fontinit) clear nothing at all.
"""
import re
import sys
from pathlib import Path

import pytest

from harness import addrs, bench_tier3, make_image

import test_vdi_escape as escape_cases
import transcription
import vdi
import vdi_escape as escape
from opcodes import RTS_WORD

BENCH_ELF = Path(__file__).resolve().parents[1] / "build" / "bench" / "bench.elf"

# ---- the spans ---------------------------------------------------------------------------------------------------
JMP_ABSOLUTE_LONG_BYTES = 6


def table_entry(table, index):
    """The address a word table of displacements from itself names at `index` — the escape's, and ESC's two."""
    return table + vdi.signed_word(vdi.rom_word(table + index * vdi.WORD_BYTES))


def through_rts(at):
    """One past the first `rts` from `at`: a span that ends with its routine's own return."""
    while vdi.rom_word(at) != RTS_WORD:
        at += vdi.WORD_BYTES
    return at + vdi.WORD_BYTES


ESC_E_BODY = table_entry(addrs.CON_ESCAPE_UPPER_TABLE, ord("E") - addrs.CON_ESCAPE_UPPER_FIRST)
V_RMCUR = table_entry(vdi.VDI_ESCAPE_TABLE, escape.ARMS["V_RMCUR"])
REGIONS = (
    transcription.pinned_region(addrs.VDI_ROM_ESCAPE, addrs.XCONOUT_RAW, "VDI_ROM_ESCAPE"),
    transcription.pinned_region(addrs.VDI_ROM_VQ_CHCELLS, ESC_E_BODY, "VDI_ROM_VQ_CHCELLS"),
    transcription.pinned_region(addrs.VDI_ROM_VS_CURADDRESS, V_RMCUR + JMP_ABSOLUTE_LONG_BYTES, "VDI_ROM_VS_CURADDRESS"),
    transcription.pinned_region(addrs.VDI_ROM_V_FONTINIT, through_rts(addrs.VDI_ROM_V_FONTINIT), "VDI_ROM_V_FONTINIT"),
)

# THE CONSOLE's ROUTINES the spans reach, and the C each ships as (`bios/vt52.h`): ESC's own bodies, which ESC's
# table names, and the five the arms branch to, which `addrs.h` names for their C bodies (`CON_<name>` ships as
# `console_<name>`).
ESC_LETTER_BODIES = {"A": "console_cursor_up", "B": "console_cursor_down", "C": "console_cursor_right",
                     "D": "console_cursor_left", "E": "console_clear_screen_and_home", "H": "console_cursor_home",
                     "J": "console_clear_to_end_of_screen", "K": "console_clear_to_end_of_line"}
CONSOLE_ENTRIES = ("HIDE_CURSOR", "UNLOCK_CURSOR", "SHOW_CURSOR", "PLACE_CURSOR", "OUTPUT")
CONSOLE_BODIES = {
    **{table_entry(addrs.CON_ESCAPE_UPPER_TABLE, ord(letter) - addrs.CON_ESCAPE_UPPER_FIRST): body
       for letter, body in ESC_LETTER_BODIES.items()},
    **{getattr(addrs, f"CON_{entry}"): f"console_{entry.lower()}" for entry in CONSOLE_ENTRIES},
}
THUNK_PREFIX = "escape_to_"


def _anchor_of(rom_address):
    anchors = [region.anchor for region in REGIONS if region.lo <= rom_address < region.hi]
    assert len(anchors) == 1, f"${rom_address:x} lies in {len(anchors)} of the escape's spans"
    return anchors[0]


def _target(at, base=None):
    """Where the ROM's PC-relative word at `at` points: a displacement from itself, or from `base`, its table."""
    return (at if base is None else base) + vdi.signed_word(vdi.rom_word(at))


def _reference(at, why, base=None):
    """The relocation of the ROM's PC-relative reference at `at`: to the span that holds its target, or to the thunk
    of the console body it names."""
    target = _target(at, base)
    if target in CONSOLE_BODIES:
        return transcription.Relocated(transcription.PC_RELATIVE, None, f"{why}: the console's ${target:x}, which ships as "
                                       f"{CONSOLE_BODIES[target]}", base, THUNK_PREFIX + CONSOLE_BODIES[target])
    return transcription.Relocated(transcription.PC_RELATIVE, _anchor_of(target), why, base)


TABLE_WORDS = range(vdi.VDI_ESCAPE_TABLE, vdi.VDI_ESCAPE_TABLE + (vdi.VDI_ESCAPE_LAST + 1) * vdi.WORD_BYTES,
                    vdi.WORD_BYTES)
# A word-displacement branch — `bra.w`, `bsr.w`, `b<cc>.w` — is `$6<cc>00`, its displacement the next word.
WORD_BRANCH_MASK = 0xF0FF
WORD_BRANCH = 0x6000


def _branches_out_of(region):
    """The extension word of every word branch in `region` that LEAVES it — the ones whose displacement measures to
    where another span or a thunk is linked. Read off the ROM, not listed: a word this takes for a branch that is not
    one would be relocated to a value the byte pin then refuses, and one it missed would be pinned as the ROM's."""
    return [at for at in range(region.lo + vdi.WORD_BYTES, region.hi, vdi.WORD_BYTES)
            if vdi.rom_word(at - vdi.WORD_BYTES) & WORD_BRANCH_MASK == WORD_BRANCH
            and not region.lo <= _target(at) < region.hi]


RELOCATED = {
    **{at: _reference(at, f"the table's word {index}", base=vdi.VDI_ESCAPE_TABLE)
       for index, at in enumerate(TABLE_WORDS)},
    **{at: _reference(at, f"the branch at ${at - vdi.WORD_BYTES:x}") for region in REGIONS for at in _branches_out_of(region)},
}


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_span_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


def test_esc_e_s_thunk_is_where_the_rom_has_the_body():
    """v_exit_cur FALLS into ESC E's body and v_enter_cur reaches it by `bsr.s`, whose byte is the ROM's: the thunk
    must be laid exactly where the ROM has the body, at the end of the span before it."""
    thunk = THUNK_PREFIX + CONSOLE_BODIES[ESC_E_BODY]
    assert transcription.bench().entry(thunk) == transcription.transcribed_address(REGIONS[1].anchor, ESC_E_BODY)


def _reachable(graph, start):
    seen, stack = set(), [start]
    while stack:
        for callee in graph.get(stack.pop(), ()):
            if callee not in seen:
                seen.add(callee)
                stack.append(callee)
    return seen


def test_each_thunk_calls_the_c_its_console_routine_ships_as_and_nothing_else():
    """Read out of the m68k build's call graph: every thunk makes one call, to its body — which the escape's C twin
    reaches too, so Tier 1's proof of that twin against the ROM covers every body a thunk enters."""
    graph = transcription.call_graph(BENCH_ELF)
    for body in set(CONSOLE_BODIES.values()):
        assert graph[THUNK_PREFIX + body] == {body}, body
    assert set(CONSOLE_BODIES.values()) <= _reachable(graph, escape.CORE)


def test_the_references_that_stay_the_rom_s_are_the_graphic_cursor_s_two_jumps():
    """v_dspcur's and v_rmcur's `jmp` name v_show_c and v_hide_c, whose C ships: ROM addresses as CODE values
    (`test_vdi_rom_data.py`), the one reference no pin relocates."""
    assert vdi.rom_word(V_RMCUR + vdi.WORD_BYTES) << 16 | vdi.rom_word(V_RMCUR + 2 * vdi.WORD_BYTES) == \
        addrs.VDI_ROM_V_HIDE_C
    dspcur_jump = V_RMCUR - JMP_ABSOLUTE_LONG_BYTES
    assert vdi.rom_word(dspcur_jump + vdi.WORD_BYTES) << 16 | vdi.rom_word(dspcur_jump + 2 * vdi.WORD_BYTES) == \
        addrs.VDI_ROM_V_SHOW_C


# ---- the behaviour ------------------------------------------------------------------------------------------------
def _registers(names):
    return tuple(names.split())


# Which registers each ARM's cases clear on both sides (the module's docstring says why), measured per arm: the
# console's C leaves different scratch behind each body, and an arm that is the escape's own code clears nothing.
MASKS = {
    "NOTHING": _registers("d0"),                    # the table's own `rts`, the displacement still in D0
    "VQ_CHCELLS": (), "VQ_CURADDRESS": (), "VQ_TABSTATUS": (), "V_HARDCOPY": (), "V_FONTINIT": (),
    "V_RVON": _registers("d0"), "V_RVOFF": _registers("d0"), "V_DSPCUR": _registers("d0"), "V_RMCUR": _registers("d0"),
    **dict.fromkeys(("V_EXIT_CUR", "V_ENTER_CUR", "V_EEOS", "V_EEOL"),
                    _registers("d0 d1 d2 d3 d4 d5 d6 d7 a0 a1 a2 a3 a5")),       # the rectangle clear's
    **dict.fromkeys(("V_CURUP", "V_CURDOWN", "V_CURRIGHT", "V_CURLEFT", "V_CURHOME", "VS_CURADDRESS"),
                    _registers("d0 d1 d2 d3 d4 d5 d6 d7 a0 a1 a2")),             # the placement's
    "V_CURTEXT": _registers("d1 d2 d3 d4 d5 d6 d7 a1 a2 a3 a5"),     # the character entry's; D0/A0 are the loop's
    "V_OFFSET": _registers("d0 d1 d4 d5 d6 d7 a0 a1 a2"),            # the lock's and the unlock's
}
MASK_OF_ARM = {escape.ARMS[arm]: mask for arm, mask in MASKS.items()}
DISTINCT_MASKS = tuple(dict.fromkeys(mask for mask in MASKS.values() if mask))
CALLERS_OFFSET = 0xC00
CALLER_STRIDE = 0x40
CALLERS_BYTES = CALLER_STRIDE * len(DISTINCT_MASKS)
CALLERS_AT = vdi.SPAN.band(CALLERS_OFFSET, CALLERS_BYTES, "test_vdi_escape_transcription.py: the masking callers")
POOL = transcription.CallerPool(CALLERS_AT, CALLERS_AT + CALLERS_BYTES, CALLER_STRIDE, built=DISTINCT_MASKS)


def subfunction_of(pokes):
    """contrl[5] as the case stages it."""
    at = vdi.CONTRL_AT + vdi.CONTRL_SUBFUNCTION
    return int.from_bytes(bytes(make_image(pokes)[at:at + vdi.WORD_BYTES]), "big")


def mask_of(pokes):
    """The case's arm's mask — none for a number past the table, which only the dispatch's compares see."""
    return MASK_OF_ARM.get(subfunction_of(pokes), ())


# Every row the C twin is priced on, and the cases the battery drives each arm's edges with besides.
ROWS = escape_cases.ROWS
EXTRA = (
    *((f"nothing, {number:#x}", escape.call(number, onto=escape.console(*escape_cases.MIDDLE)))
      for number in escape_cases.NOTHING),
    *((f"vs_curaddress of row {row}, the cursor drawn",
       escape.call("VS_CURADDRESS", (row, escape_cases.MIDDLE[0] + 1), escape.console(*escape_cases.MIDDLE)))
      for row in escape_cases.WRAPPING_ROWS),
    *((f"v_fontinit, the {name}", escape_cases.fontinit(font, escape.console(*escape_cases.MIDDLE)))
      for name, font in escape_cases.FONTS.items()),
    *((f"v_offset of {lines}", escape.call("V_OFFSET", (lines,), escape.console(*escape_cases.MIDDLE)))
      for lines in (0, 0x8000, 0xFFFF)),
)
CASES = (*ROWS, *EXTRA)


@pytest.mark.parametrize("label,pokes", CASES, ids=[case[0] for case in CASES])
def test_the_transcription_behaves_as_the_rom(label, pokes):
    POOL.run_transcription(escape.ESCAPE, pokes, code_pointers=mask_of(pokes))


# How the kit's transcription relation names a register it found different (`rom_bench._vet_register_file`):
# "<name> <was> -> <now>".
_REGISTER_IN_MESSAGE = re.compile(r"\b([ad][0-7]) 0x")


def _registers_that_differ(pokes):
    """Through the PLAIN caller: which registers the transcription relation finds different, none if it holds."""
    try:
        transcription.run_transcription(escape.ESCAPE, pokes)
    except AssertionError as refused:
        return set(_REGISTER_IN_MESSAGE.findall(str(refused)))
    return set()


@pytest.mark.parametrize("arm", [*MASKS, None], ids=[*MASKS, "past the table"])
def test_each_arm_s_mask_is_what_the_two_measurably_disagree_in(arm):
    """The union, over the cases of `arm` (None: every number past the table), of the registers the unmasked relation
    finds different — exactly the arm's mask."""
    arm_of = {number: name for name, number in escape.ARMS.items()}
    cases = [pokes for _label, pokes in CASES if arm_of.get(subfunction_of(pokes)) == arm]
    assert cases, f"no case drives {arm or 'a number past the table'}"
    differing = set().union(*(_registers_that_differ(pokes) for pokes in cases))
    assert differing == set(MASKS.get(arm, ()))


def test_every_arm_has_a_measured_mask():
    assert set(MASKS) == set(escape.ARMS)


# ---- the rows Tier 3 prices: the C twin's own, each as the `.S` ships it -------------------------------------------
for _label, _pokes in ROWS:
    POOL.register_transcription(escape.ESCAPE, _label, _pokes, code_pointers=mask_of(_pokes))


def test_tier3_splits_the_rows_by_exactly_these_thunks_and_the_c_they_reach():
    """Mechanism (T←) (`bench/tier3.py`) reads escape.S's rows as its own instructions plus the thunks plus the C
    behind them: the thunks it finds must be one per console body, and the C it counts must hold every body."""
    tier3 = bench_tier3()                           # here: tier3 imports this battery through its registry

    split = tier3.CALLS_INTO_C[addrs.VDI_ROM_ESCAPE]
    assert split.thunk_prefix == THUNK_PREFIX and split.spans == tuple((region.lo, region.hi) for region in REGIONS)
    thunks, callees = tier3.into_c_ranges(BENCH_ELF, THUNK_PREFIX)
    bodies = set(CONSOLE_BODIES.values())
    assert len(thunks) == len(bodies)
    starts = {symbol.start for symbol in transcription.symbol_table(BENCH_ELF) if symbol.name in bodies}
    assert starts <= {start for start, _end in callees}
