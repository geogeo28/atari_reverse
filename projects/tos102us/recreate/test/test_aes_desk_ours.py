r"""THE HANDS' CAMPAIGN ON OUR SHORE (band 6 slice H, slice B's) — `test/aes_desk.py`'s our-shore block, held.

THE BINDING (slice B0) lays OUR Line-F call table at `$cc24` on every machine of ours, so the ROM's desk — each of its
routines until that routine flips — runs over OUR AES. Every chain of the hands' campaign (`aes_desk.CHAINS`, held on
the ROM's machine by `test_aes_desk_rom.py`) is walked again ON THE OUR-BOOT MACHINE of its capture — the shipped blob
laid at the pre-init stop and the run entered at its own gem_entry (ruling W4-R1's labelled staging) — by the same
hands, every point read off THAT machine's trees. Per chain (a case a chain: the campaign shards over xdist's workers):

  * EACH STEP ENDS AT OUR IDLE, or at the named stop's address ON OUR SHORE (`aes_desk.our_stop`: the rubber box's poll
    is band 3's C gr_stilldn's entry);
  * THE THREE INVARIANTS (the design's §4, ruling W6-R5): THE SCREEN byte-equal WHERE EVERY STEP ENDS (and the
    desk's block, its code addresses given the ROM's names); THE OS's cycles (the BIOS, GEMDOS, the VDI) EQUAL ON EVERY STEP;
    and, the converse, EVERY ROM DESK ROUTINE'S OWN CYCLES EQUAL ON EVERY STEP — each PC charged to its routine by
    EVERY start of the AES map's inventory (`aes_desk.charged`) — but for the routines a routine of bands 0-5 runs on
    the ROM's shore (`RUN_UNDER_BANDS_0_TO_5`: ours on ours), short by EXACTLY one pass for each time that routine
    ran, counted off the ROM's own step profile at its call site;
  * WHO RAN (W6-R5): every cycle of the ROM's GEM text on our shore lies in a DECLARED span — band 6's routines still
    the ROM's (`aes_desk.still_the_rom_s`, shrinking with each flip) and the ROM's text of bands 0-5 they reach
    otherwise than through the table (`aes_desk.ROM_TEXT_UNDER_ROM_CALLERS`, each with a chain it ran in);
  * THE FOUR STACKS' DEPTHS (`DEPTHS`, off the write ledgers as `aes_desk.depths` reads them) — PD0's under W6-R4's
    HARD GATE (`pd0_gate`, the user's ruling: it binds every flip that deepens a path).

W6-R8's TWO CHAINS ARE REFUSED ON OUR SHORE, each a NAMED, LABELLED CLASS (the user's ruling: the launch and the disk
copy stay the ROM's shore's): the ROM's own walk of each stores over the span our blob lies in.

AND N6: every run of `aes_boot`'s — a boot's too — surfaces what its devices left (`aes_boot.surfaced`).

THE NUMBERS ARE THE SHIPPED BLOB'S over these hands and these captures, measured with units O and D flipped (band 6
slice F1: 56 routines, the table's entry of each ours; appl_exit, evnt_multi and objc_draw held): each flip slice moves its rows (its routines leave
`still_the_rom_s`, its depths move) — and says so.
"""
import functools
import importlib.util
import inspect
import re
import sys
from collections import namedtuple

import pytest

from harness import addrs

import aes
import aes_boot
import aes_desk as desk
import aes_stack
import derived
import transcription
from aes_boot import OURS, Refused

BUS = aes_boot.BUS
BOUND_TABLE = transcription.LINEF_TABLE_SYMBOL
STACKS = (desk.PD0_STACK, desk.PD1_STACK, desk.DISPATCHER_STACK, desk.USERDEF_STACK)

# ---- W6-R8: THE TWO CHAINS REFUSED ON OUR SHORE, each a named class ---------------------------------------------------------------
LAUNCHED = "files: the program double-clicked — launched"
A_LAUNCH_OVER_THE_BLOB = "W6-R8: A LAUNCH — the shell's Pexec loads the program over free memory, where our blob lies"
A_COPY_OVER_THE_BLOB = "W6-R8: THE DISK COPY — its buffer, all free memory but a kilobyte, read full of tracks where our blob lies"
REFUSED_ON_OUR_SHORE = {   # `{chain: (its class, the step refused, what the refusal reads)}`
    LAUNCHED: (A_LAUNCH_OVER_THE_BLOB, 0, "the run did not reach an idle within 6000000 instructions"),
    desk.COPIED: (A_COPY_OVER_THE_BLOB, 4, "Rwabs of drive 254: the model holds drive A: alone")}


def _goes_on_from_a_refused(name):
    after = desk.CHAINS[name].after
    return after in REFUSED_ON_OUR_SHORE or (after in desk.CHAINS and _goes_on_from_a_refused(after))


WALKED_ON_OUR_SHORE = [name for name in desk.CHAINS if name not in REFUSED_ON_OUR_SHORE and not _goes_on_from_a_refused(name)]


def _stored_over(name, span):
    """How many bytes of `span` (`(lo, hi)`) THE ROM'S OWN WALK of the chain `name` stores into, all its steps told."""
    lo, hi = span
    runs = sorted((max(start, lo), min(start + length, hi)) for stepped in desk.walked(name).steps
                  for start, length in stepped.boot.stored if start < hi and start + length > lo)
    covered, reach = 0, lo
    for start, end in runs:
        covered += max(0, end - max(start, reach))
        reach = max(reach, end)
    return covered


def _the_blob_s_span():
    ours = aes_boot.ours_of(desk.our_blob())
    return ours.base, ours.end


# THE LAUNCH STORES OVER ALL OF IT (the program's memory cleared and loaded where the blob lies), the copy over most.
STORES_OVER_ALL_THE_BLOB = {LAUNCHED: True, desk.COPIED: False}


@pytest.mark.parametrize("name", REFUSED_ON_OUR_SHORE)
def test_w6_r8_s_two_chains_are_refused_on_our_shore_by_name_and_the_rom_s_own_walk_stores_over_the_blob(name):
    """THE LABELLED CLASS, AND WHY: the chain's step is refused on our machine as measured, every step before it
    walked — and the ROM's own walk of the chain (its machine holds no blob) STORES INTO THE SPAN OUR BLOB LIES IN: the
    program's memory cleared and loaded (the whole span: as large as the blob is today, read off it), the copy's buffer
    read full. On our machine those stores land on our code."""
    labelled, step, reads = REFUSED_ON_OUR_SHORE[name]
    with pytest.raises(Refused, match=f"step {step} of .* on our shore .*{reads}"):
        desk.walked_ours(name)
    lo, hi = _the_blob_s_span()
    over = _stored_over(name, (lo, hi))
    assert over == hi - lo if STORES_OVER_ALL_THE_BLOB[name] else 0 < over < hi - lo, (
        f"{labelled}: the ROM's walk of {name!r} stores {over} bytes over [{lo:#x}, {hi:#x})")


def test_no_walked_chain_s_rom_walk_stores_over_the_blob():
    """...AND THE REASON TELLS THE TWO APART (reviewer B's F4): no chain walked on our shore has a ROM walk that stores
    a byte where our blob lies — the refusal covers W6-R8's two alone."""
    span = _the_blob_s_span()
    assert not [name for name in WALKED_ON_OUR_SHORE if _stored_over(name, span)]


def test_no_chain_goes_on_from_a_refused_one_and_the_rest_are_walked():
    assert not [name for name in desk.CHAINS if _goes_on_from_a_refused(name)]
    assert len(WALKED_ON_OUR_SHORE) == len(desk.CHAINS) - len(REFUSED_ON_OUR_SHORE) == len(DEPTHS)
    assert set(DEPTHS) == set(WALKED_ON_OUR_SHORE)


# ---- THE MACHINES AND THE STOPS OF OUR SHORE --------------------------------------------------------------------------------------------
LINE_F_TABLE_SLOT = aes.AES_LINEF_COPY + aes.LINEF_TABLE_OPERAND     # `$cc24`: the table the handler's copy indexes


def test_our_machines_are_the_rom_s_captures_booted_by_our_gem_entry_at_our_idle_over_our_table():
    """One machine of ours for each of `MACHINES`; the three captures' booted by OUR gem_entry (an our-boot of the
    shipped blob), at OUR dispatcher's idle, over the disk the ROM's machine of that capture holds — and THE BOUND
    TABLE: the Line-F handler's copy indexes OUR table (`$cc24`), where the ROM's machine's indexes the ROM's."""
    assert set(desk.OUR_MACHINES) == set(desk.MACHINES)
    for name in (desk.INF_ICONS, desk.INF_TEXT, desk.FILES):
        ours, rom = desk.OUR_MACHINES[name](), desk.MACHINES[name]()
        assert ours.our_boot is not None and ours.ours == aes_boot.ours_of(desk.our_blob()) and rom.ours is None
        assert ours.idle == OURS and ours.boot.disk == rom.boot.disk
        assert (ours.long(LINE_F_TABLE_SLOT), rom.long(LINE_F_TABLE_SLOT)) == (desk.our_blob().entry(BOUND_TABLE), aes.AES_LINEF_TABLE)


def test_a_step_of_ours_refuses_the_rom_s_machine_and_the_rom_s_step_refuses_ours():
    rom, ours = aes_boot.inf_machine().boot, desk.OUR_MACHINES[desk.INF_ICONS]().boot
    with pytest.raises(Refused, match="this is the ROM's machine"):
        desk.stepped_ours.derive(rom, ())
    with pytest.raises(Refused, match="THE ROM'S MACHINE'S: this one holds a blob"):
        desk.stepped.derive(ours, ())


THE_BOXES = ("a rubber box on the desktop, round the trash", "a rubber box on the desktop, round drive B: and the trash")


def test_each_named_stop_has_its_address_on_our_shore():
    """N4: THE RUBBER BOX'S POLL IS OUR gr_stilldn's ENTRY (band 3's C), the viewer's two key waits the ROM's own
    (the show engine is the ROM's on our machine until unit M flips) — and each rubber box chain stands there twice,
    at no idle, before OUR idle."""
    blob = desk.our_blob()
    assert desk.our_stop(desk.RUBBER_BOX_POLL) == blob.entry("aes_gr_stilldn") != desk.STOPS[desk.RUBBER_BOX_POLL]
    for stop in (desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_THE_FILE_S_END):
        assert desk.our_stop(stop) == desk.STOPS[stop]
    for name in THE_BOXES:
        first, second, last = desk.walked_ours(name).steps
        for stepped in (first, second):
            assert stepped.boot.idle is None and stepped.boot.registers["pc"] & BUS == desk.our_stop(desk.RUBBER_BOX_POLL)
        assert last.boot.idle == OURS


# ---- WHO RAN: the declared spans -------------------------------------------------------------------------------------------------------
# A chain each of `aes_desk.ROM_TEXT_UNDER_ROM_CALLERS` runs in on our shore: no span is declared that nothing runs.
RAN_IN = {desk.LMUL: "file: shown, a key at its end"}      # (unit O's five spans went with its flip: `aes_desk`'s note)
# band 6's routines whose entry of the shipped blob's table is ours: slice F1's 56 (O + D, three held) and, since slice
# F2, each group's own count on a line inside its own block (no two authors edit one line; the pin is the sum)
BAND_6_FLIPPED_AT_F2 = {
    # ---- band 6 slice F2, group G1 (units I, L) ----
    "G1": 29,               # the 33 but do_wredraw, win_icalc, win_bldview, win_shwall
    # ---- end of group G1's ----
    # ---- band 6 slice F2, group G2 (units A, K, J) ----
    "G2": 0,
    # ---- end of group G2's ----
    # ---- band 6 slice F2, group G3 (units B, G) ----
    "G3": 0,
    # ---- end of group G3's ----
    # ---- band 6 slice F2, group G4 (units C, H, E, F) ----
    "G4": 19,                           # unit C's ten, units H, E, F (eight), and unit D's appl_exit (⚠️ unpriced)
    # ---- end of group G4's ----
}
BAND_6_FLIPPED = 56 + sum(BAND_6_FLIPPED_AT_F2.values())


def test_the_declared_spans_are_band_6_s_routines_not_flipped_and_the_rom_s_text_they_reach_each_run():
    """THE DECLARED SPANS (W6-R5): band 6's 244 less those flipped — units O and D since slice F1 —, and the ROM's text
    of bands 0-5 they reach by a `bsr`, `jsr`, `jmp` or branch: each a start the inventory lists, none of band
    6's, each run on our shore in the chain named."""
    assert len(desk.flipped()) == BAND_6_FLIPPED and desk.still_the_rom_s() == frozenset(desk.routines()) - desk.flipped()
    assert set(RAN_IN) == set(desk.ROM_TEXT_UNDER_ROM_CALLERS)
    assert set(RAN_IN) <= set(desk.inventoried()) and not set(RAN_IN) & set(desk.routines())
    for start, name in RAN_IN.items():
        ran = set().union(*(desk.charged(stepped.profile.text) for stepped in desk.walked_ours(name).steps))
        assert start in ran, f"{start:#x} ran in no step of {name!r} on our shore"


# ---- WHO RAN, PER FLIPPED ROUTINE (band 6 slice F1, ruling W6-R5): its ROM span not a cycle on any walked chain, its entry ours run ----
# A flipped routine's entry of the bound table is OURS (its thunk, or its `.S`): on our shore the ROM's desk's own call
# words land there, and the ROM's span of the routine runs NOT ONE CYCLE on any walked chain. Its entry RAN on one chain
# at least — the proof a thunk no kit call can enter has (`test_aes_lineftable.UNENTERED`: the yielding bindings) — but
# for the routines NO WALKED CHAIN REACHES ON OUR SHORE, by name with why (exact both ways).
NOT_ENTERED_ON_OUR_SHORE = {
    "AES_ROM_GSX_HARDCOPY": "unit O's: no chain answers Print Screen's alert (its chain raises it and stops), so nothing calls "
                            "the hardcopy — Tier 1 holds it over an argument class (`test_desk_leaves.py`)",
    # ---- band 6 slice F2, group G1 (units I, L) ---- EVERY ROM CALLER OF EACH FLIPPED (read off the GEM text:
    # `aes_deskbind.calls_of`), so on our shore it is called by our C alone, never through the table — three of the
    # group's own and seven of unit D's bindings, whose last ROM callers were the group's
    **{name: f"its every ROM caller flipped at band 6 slice F2 (group G1: {callers}): called by our C alone on our shore" for name, callers in {
        "AES_ROM_OBJ_INIT": "win_start", "AES_ROM_OBJ_WALLOC": "win_alloc", "AES_ROM_WIN_CNT": "win_ith",
        "AES_ROM_DESK_GRAF_SHRINKBOX": "zoom_closed, do_wfull", "AES_ROM_DESK_OBJC_ADD": "obj_init, obj_ialloc",
        "AES_ROM_DESK_OBJC_ORDER": "win_free, win_top", "AES_ROM_DESK_SHEL_WRITE": "pro_exec",
        "AES_ROM_DESK_WIND_CLOSE": "zoom_closed", "AES_ROM_DESK_WIND_CREATE": "win_alloc",
        "AES_ROM_DESK_WIND_DELETE": "win_free"}.items()},
    # ---- end of group G1's ----
    # ---- band 6 slice F2, group G2 (units A, K, J) ----
    # ---- end of group G2's ----
    # ---- band 6 slice F2, group G3 (units B, G) ----
    # ---- end of group G3's ----
    # ---- band 6 slice F2, group G4 (units C, H, E, F) ----
    # ...CALLED BY OUR C ALONE: every Line-F call word of the routine in the ROM's GEM text lies in a routine G4 flipped at
    # slice F2 (read off the image), and a C caller calls the core, not the table's thunk. Tier 1 and the rows hold each.
    **{f"AES_ROM_{routine}": f"its every call word in the ROM's text lies in {callers}, flipped at slice F2 (group G4): only "
                             f"our C calls it" for routine, callers in (
        ("DESK_MY_ITOA", "fmt_time and fmt_date"), ("DESK_FMT_TIME", "ob_sfcb and inf_dttmsz"),
        ("DESK_FMT_DATE", "ob_sfcb and inf_dttmsz"), ("DESK_PATH_PART", "par_chk"),
        ("DESK_APPL_WRITE", "fun_msg (unit D's binding: no kit call enters its thunk either, `test_aes_lineftable.UNENTERED`)"),
        ("DESK_FORM_ERROR", "d_errmsg (unit D's binding: no kit call enters its thunk either, `test_aes_lineftable.UNENTERED`)"),
        ("DOS_DELETE", "d_dofdel (unit O's glue entry: its verified rows enter its thunk through the table, N15)"))},
    # ---- end of group G4's ----
}


@functools.cache
def _entered_on_our_shore():
    """`({a flipped routine's start: the walked chains whose steps entered its entry of ours}, {its start: the chains in
    which its ROM span ran a cycle})`."""
    entries, entered, its_span_ran = desk.our_entries(), {}, {}
    for name in WALKED_ON_OUR_SHORE:
        steps = desk.walked_ours(name).steps
        ran = {at for stepped in steps for at, _cycles in stepped.entered}
        charged = {routine for stepped in steps for routine, cycles in desk.charged(stepped.profile.text).items() if cycles}
        for routine, ours in entries.items():
            if ours in ran:
                entered.setdefault(routine, []).append(name)
            if routine in charged:
                its_span_ran.setdefault(routine, []).append(name)
    return entered, its_span_ran


def test_every_flipped_routine_s_rom_span_ran_no_cycle_and_its_entry_of_ours_ran():
    """...AND THE ROUTINES THE BLOB'S OWN TABLE FLIPS ARE THOSE THE GENERATOR SAYS ARE OURS: an entry left (or put back)
    the ROM's in the built table under a verdict of ours is no flip, and reds here before any count does."""
    generator = _the_generator()
    ours = {entry.target for entry in generator.entries() if entry.verdict != generator.THE_ROM_S}
    assert desk.flipped() == ours & frozenset(desk.routines()), "the blob's table and the generator's verdicts disagree"
    entered, its_span_ran = _entered_on_our_shore()
    assert not its_span_ran, f"a flipped routine's ROM span ran on our shore: {({f'{at:#x}': names[:2] for at, names in its_span_ran.items()})}"
    names = {getattr(addrs, name): name for name in dir(addrs) if name.startswith("AES_ROM_")}
    never = {names[routine] for routine in desk.flipped() if routine not in entered}
    assert never == set(NOT_ENTERED_ON_OUR_SHORE), f"flipped, and entered on no walked chain of our shore: {sorted(never)}"


# ---- THE CONVERSE INVARIANT'S ONE CLASS: band 6's text a routine of bands 0-5 runs on the ROM's shore ----------------------------------
# On the ROM's machine the ROM's own routine of bands 0-5 runs THESE SPANS — it calls them, or branches into their
# body; on ours that routine is OURS and calls OUR twin, or runs its own body: the ROM's shore runs each span ONE PASS
# MORE THAN OURS FOR EVERY TIME THAT CALLER RAN — EXACTLY (the fix pass, reviewer B's F1: a deficit of any whole number
# of passes hid a pass of the desk's own). How many times the caller ran in a step is read off THE ROM'S OWN STEP
# PROFILE at an instruction of the caller's that runs once a pass (`site`, whose cycles are `site_cycles` a pass); our
# shore runs that instruction never. `{the span's start: Under(who runs it, the cycles of one pass, site, site_cycles)}`.
Under = namedtuple("Under", "who a_pass site site_cycles")
INI_TREE = 0xfe0b6e
ROM_RAM_S_ARM_RETURN = 0xfee74a         # rom_ram's desk arm, past its Line-F call of ini_tree: `addq.l #4,sp` (8 cycles)
ADDQ_L_AN_CYCLES = 8
RUN_UNDER_BANDS_0_TO_5 = {
    # ---- band 6 slice F2, group G1 (units I, L): ini_tree `$fe0b6e` LEFT THE CLASS AT ITS FLIP (rom_ram's desk arm called it
    # on the ROM's shore alone, 158 a pass; ours now through the table on both: held by who-ran) ----
    # ---- end of group G1's ----
}
# TWO LEFT THE CLASS AT THEIR FLIP (band 6 slice F1): dos_write `$fe3a7c`, unit O's — band 5's dos_read `$fe3a78` entered
# its body by `moveq #$3f,d1; bra`, 124 a pass, on the ROM's shore alone — and unit D's rsrc_gaddr binding `$fde354`,
# 218 a pass under ini_tree's. A routine no longer the ROM's is held by who-ran (no cycle of its ROM span on our shore).


def test_the_class_s_spans_are_band_6_s_still_the_rom_s():
    """Each span of the class is a band-6 routine STILL THE ROM'S (`still_the_rom_s`): a flip that takes one out
    (units O and D, at F1) reds here, and the class's entry goes with it."""
    assert set(RUN_UNDER_BANDS_0_TO_5) <= desk.still_the_rom_s()


# ---- THE FOUR STACKS' DEPTHS ON OUR SHORE, per chain — and W6-R4's gate ---------------------------------------------------------------
# W6-R4, THE USER'S: a hard gate, binding every flip that deepens a path — PD0's span (`aes_desk.PD0_BYTES`, its one
# home; each machine of ours asserted to have it) less THE INTERRUPT NEST band 5 charges, MEASURED on our shore
# (`aes_stack.nest_on_the_first_stack`: a vertical blank with the MFP inside it, the shipped blob's handlers — 244).
# WHAT A DEPTH IS HERE (reviewer B's item 4): THE LOWEST STORE of a chain's write ledgers (`aes_desk.depth_stored`),
# NOT the lowest SP — a local allocated and never written is not counted. The hard gate of the later slices (D, W3b)
# reads the same measure, with `aes_stack`'s bound on how far SP can stand below a lowest store (`unstored_under`,
# what band 5's verdict charges our own code beside it) said beside it — reported here as not charged.
@functools.cache
def pd0_gate():
    return desk.PD0_BYTES - aes_stack.nest_on_the_first_stack(desk.OUR_BLOB)


def test_the_gate_is_pd0_s_span_less_the_nest_measured_on_our_shore():
    assert aes_stack.nest_on_the_first_stack(desk.OUR_BLOB) == aes_stack.nest_on_the_first_stack() and pd0_gate() == 1548
# THE CUT'S §4 ROWS, the ROM's own PD0 beside ours (`DEPTHS`): what W6-R4 is read on.
THE_ROM_S_PD0 = {"folder: File > Close": 1398, "folder: opened": 1410, "file: File > Open, Print clicked (the printer not ready)": 1438,
                 "A: File > Open": 1460, "A: opened": 1446, "two windows: File > Close Window (one left on top)": 1364,
                 desk.FORMAT_UP: 1218, desk.FORMATTED: 816, "A: File > Format, OK, EXIT clicked": 886, desk.COPY_UP: 1212,
                 "file: shown, a key at its end": 1438}
DEEPEST_PD0 = ("A: File > Open", 1532)     # (1,504 before units O and D flipped: band 6 slice F1)


def test_the_cut_s_depth_rows_the_rom_s_beside_ours_and_the_deepest_under_the_gate():
    """MEASURED BY THE WRITE LEDGERS: the ROM's own desk on the ROM's AES beside the ROM's desk over OURS (`DEPTHS`) —
    File > Open on drive A: the deepest of ours, 1,532 of W6-R4's 1,548 since units O and D flipped (1,504 before)."""
    assert {name: desk.depths(name)[desk.PD0_STACK] for name in THE_ROM_S_PD0} == THE_ROM_S_PD0
    assert max(((name, depths[0]) for name, depths in DEPTHS.items()), key=lambda found: found[1]) == DEEPEST_PD0
    assert DEEPEST_PD0[1] <= pd0_gate()


# ---- W6-R4 ON THE FLIPPED STATE: THE MEASURING TOOL'S STEPS, held to today's sources (band 6 slice D) ----------------------
# `tools/flipped_depths.py` builds the shipped blob with every linked routine of band 6 flipped, in a private tree, and
# walks every chain there — the gate each flip slice (F1..F4) and deskmain's (W3b) is measured on before it lands (its
# numbers are STATUS's). Each text step it takes is held here to the source it edits, so a slice that moves an
# anchor reds here and not in the middle of a measuring run.
@functools.cache
def _the_tool():
    spec = importlib.util.spec_from_file_location("flipped_depths", derived.RECREATE / "tools" / "flipped_depths.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def _the_generator():
    """`bench/linef_table.py` — imported here, not at the top (it imports every battery's registry), with bench/ on
    the path for that import alone."""
    bench = str(derived.RECREATE / "bench")
    sys.path.insert(0, bench)
    try:
        import linef_table
    finally:
        sys.path.remove(bench)
    return linef_table


def test_the_tool_empties_the_generator_s_held_list_before_its_thunks_are_named():
    tool = _the_tool()
    source = (derived.RECREATE / tool.GENERATOR).read_text()
    emptied = tool.emptied(source)
    assert emptied.count(tool.EMPTIED) == 1 and emptied.index(tool.EMPTIED) < emptied.index("def thunk_symbol(")
    assert emptied.replace(tool.EMPTIED, "", 1) == source


def test_the_tool_copies_sh_cmd_s_four_thunks_out_of_the_flipped_table(monkeypatch):
    """The flipped table (the generator over an empty held list) has a thunk for each of sh_cmd's four built-ins, each
    entering its core; the tool's copies are those bodies, global. Today's table has none of them (units M and N held)."""
    tool, generator = _the_tool(), _the_generator()
    with pytest.raises(AssertionError, match="no thunk"):
        tool.door_thunks((derived.RECREATE / tool.TABLE).read_text())
    monkeypatch.setattr(generator, "LINKED_AND_NOT_FLIPPED", {})
    copies = tool.door_thunks(generator.text())
    for thunk in tool.BUILT_INS.values():
        copy = tool.FLIPPED_PREFIX + thunk
        assert f"    .globl {copy}\n" in copies and f"\n{copy}:\n" in copies
        assert f"jsr     {thunk.removeprefix(transcription.LINEF_THUNK_PREFIX)}\n" in copies


def test_the_tool_enters_sh_cmd_s_four_built_ins_at_the_copies_on_target_alone():
    tool = _the_tool()
    flipped = tool.sh_cmd_flipped((derived.RECREATE / tool.SHELL).read_text())
    host, target = flipped.split("#ifdef RECREATE_HOST_DIFFERENTIAL\n", 1)[1].split("#else\n", 1)
    for rom, thunk in tool.BUILT_INS.items():
        assert flipped.count(f"(image, {tool.FLIPPED_PREFIX}{rom}, AES_SH_TAIL_TEXT") == 1 and f"(image, {rom}," not in flipped
        assert f"#define {tool.FLIPPED_PREFIX}{rom} {rom}\n" in host
        assert f"#define {tool.FLIPPED_PREFIX}{rom} {tool.FLIPPED_PREFIX}{thunk}\n" in target


# ...AND ITS THREE SELF-CHECKS (slice D's fix pass: the review's F1-F3), each held where it can be without a flipped build.
def test_the_tool_reads_every_held_routine_with_an_entry_as_the_rom_s_off_today_s_unflipped_blob():
    """THE FLIPPED CHECK reads the blob's OWN bound table: on today's shipped blob — units O and D flipped, the rest held
    (band 6 slice F1) — it reports exactly the routines the generator still holds back that have an entry of the table,
    so a flip step lost in a private tree (the review's T1) is refused before a walk."""
    tool, generator = _the_tool(), _the_generator()
    with_no_entry = {getattr(addrs, name) for name in generator.LINKED_HELD_NO_TABLE_ENTRY}
    held = {getattr(addrs, name) for name in generator.LINKED_AND_NOT_FLIPPED}
    assert with_no_entry and not with_no_entry & set(generator.rom_table())
    assert tool.linked_still_the_rom_s(desk, generator) == sorted(held)


OurBoot = namedtuple("OurBoot", "stored writes_truncated")     # what the tool reads of a step of ours
OurStep = namedtuple("OurStep", "boot blob")


def test_the_tool_refuses_a_walk_whose_write_ledger_saturated_and_measures_the_lowest_store_otherwise():
    tool = _the_tool()
    lo, hi, stored_at, cycles = 0x1000, 0x1800, 0x1200, 7
    steps = [OurStep(OurBoot(((stored_at, 2),), False), cycles), OurStep(OurBoot((), False), cycles)]
    assert tool.measured(steps, lo, hi) == {"pd0": hi - stored_at, "blob_cycles": 2 * cycles}
    steps.append(OurStep(OurBoot((), True), cycles))
    assert tool.measured(steps, lo, hi) == {"refused": tool.LEDGER_SATURATED}



def test_the_tool_s_refusals_are_held_to_its_declared_list_each_way():
    """A refusal outside the list, or reading other than its declaration, and a declared refusal that walks, are each
    the tool's non-zero exit; a declared refusal as declared is not."""
    tool = _the_tool()
    declared = tool.declared_refusals(unflipped=False)
    launched, copied = tool.REFUSED_ON_EITHER_STATE
    found = {launched: {"refused": f"step 0: {tool.NO_IDLE_REACHED} 6000000 instructions"}, copied: {"pd0": 1}}
    assert tool.misrefused(found, declared) == ([], [copied])
    found = {launched: {"refused": "Rwabs of drive 254"}, "a chain": {"refused": tool.NO_IDLE_REACHED}}
    assert tool.misrefused(found, declared) == ([launched, "a chain"], [])
    assert set(tool.declared_refusals(unflipped=True)) == {launched, copied}


def test_the_tool_s_declared_refusals_are_w6_r8_s_two_and_every_chain_that_stops_at_the_viewer():
    """W6-R8's two are this battery's (`REFUSED_ON_OUR_SHORE`, reading what it reads); the flipped state's are EVERY
    chain with a step at the viewer's key waits (the ROM's stops, N4) — a viewer chain added and not declared reds here."""
    tool = _the_tool()
    assert set(tool.REFUSED_ON_EITHER_STATE) == set(REFUSED_ON_OUR_SHORE)
    assert all(reads in REFUSED_ON_OUR_SHORE[name][2] for name, (_why, reads) in tool.REFUSED_ON_EITHER_STATE.items())
    viewer = {desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_THE_FILE_S_END}
    assert not viewer & set(desk.OUR_STOPS)
    stopping = {name for name, chain in desk.CHAINS.items() if any(step.until in viewer for step in chain.steps)}
    assert set(tool.REFUSED_ON_THE_FLIPPED_STATE) == stopping


# ---- W6-R4's DIET, ON THE SHIPPED ELF (slice D): the split helpers stay routines of their own -----------------------------
# The diet's PD0 numbers are the tool's (a flipped build: minutes); what makes them is held here in seconds — each
# helper a routine of the shipped ELF (inlined back, its frame or its arguments stand under a deep draw again: the
# review measured +16..+68 B over the gate), act_redrawn_inside none (called, +20), and win_bldview leaving to its
# sliders by a JUMP (a call would stand its frame under the sliders' redraw). `include/stack_diet.h` lists them.
PD0_SPLIT_HELPERS = ("lay_the_items", "the_sliders_set", "zoom_onto_the_middle", "get_rect_called", "the_rectangles_read",
                     "the_command_run", "the_window_s_path_named", "the_window_redrawn")
PD0_INLINED = "act_redrawn_inside"
SLIDERS_LEFT_TO = ("aes_win_bldview", "the_sliders_set")      # `(the routine, the one it ends by jumping to)`
A_JUMP_TO = re.compile(r"(?:jmp|bra[swl]?) (?:0x)?[0-9a-f]+ <(\w+)>")


def _shipped_functions():
    """The function names of the shipped ELF, a name GCC split or specialised (`name.isra.0`) read as its own."""
    return {symbol.name.split(".")[0] for symbol in transcription.symbol_table(transcription.SHIPPED_ELF) if symbol.kind in "Tt"}


def test_the_diet_s_helpers_are_routines_of_the_shipped_elf_and_act_redrawn_inside_is_none():
    functions = _shipped_functions()
    assert [helper for helper in PD0_SPLIT_HELPERS if helper not in functions] == []
    assert PD0_INLINED not in functions


def test_win_bldview_leaves_to_its_sliders_by_a_jump():
    routine, jumped_to = SLIDERS_LEFT_TO
    body = transcription.listing(transcription.SHIPPED_ELF).split(f"<{routine}>:\n", 1)[1].split("\n\n", 1)[0]
    last = body.splitlines()[-1].split("\t")[-1].strip()
    assert (found := A_JUMP_TO.fullmatch(last)) and found.group(1) == jumped_to, f"{routine} ends in {last!r}"


# ---- THE CAMPAIGN ON OUR SHORE: a case a chain -----------------------------------------------------------------------------------------
def _short_by_its_caller_s_passes(routine, ours, rom, our_text, its_text):
    """Is `ours` the ROM's `rom` cycles of `routine` less EXACTLY one pass for each time its caller of bands 0-5 ran
    in the step (its class: the caller's `site` counted off the ROM's step profile `its_text`, never run on ours)?"""
    under = RUN_UNDER_BANDS_0_TO_5[routine]
    times, odd = divmod(dict(its_text).get(under.site, 0), under.site_cycles)
    return not odd and not dict(our_text).get(under.site, 0) and rom - ours == times * under.a_pass


def converse_broken(ours, rom):
    """`[(routine, ours, the ROM's)]`: each band-6 routine still the ROM's whose own cycles in one step's profiles
    (`ours`, `rom`) differ — but by its class, exactly, where it has one."""
    mine, theirs, broken = desk.charged(ours.text), desk.charged(rom.text), []
    for routine in sorted(desk.still_the_rom_s() & (set(mine) | set(theirs))):
        here, there = mine.get(routine, 0), theirs.get(routine, 0)
        if here != there and not (routine in RUN_UNDER_BANDS_0_TO_5
                                  and _short_by_its_caller_s_passes(routine, here, there, ours.text, rom.text)):
            broken.append((f"{routine:#x}", here, there))
    return broken


# THE READER'S OWN PROBE: the class's last entry, ini_tree's under rom_ram's desk arm (it LEFT the class at its flip,
# band 6 slice F2) — laid back into the class, and ini_tree made still the ROM's, for the reader's test alone.
INI_TREE_UNDER_ROM_RAM = Under("rom_ram's desk arm (the desktop sized, deskmain's second pass): ini_tree, the desk's tree 0",
                               158, ROM_RAM_S_ARM_RETURN, ADDQ_L_AN_CYCLES)


def test_the_converse_reader_holds_a_differing_routine_and_the_class_one_pass_a_caller_s_run_exactly(monkeypatch):
    monkeypatch.setitem(RUN_UNDER_BANDS_0_TO_5, INI_TREE, INI_TREE_UNDER_ROM_RAM)
    still = desk.still_the_rom_s() | {INI_TREE}
    monkeypatch.setattr(desk, "still_the_rom_s", lambda blob=None: still)
    one, two = desk.Profile(((0xfdb014, 10),), 0, 0), desk.Profile(((0xfdb014, 12),), 0, 0)
    assert converse_broken(one, one) == [] and converse_broken(one, two) == [("0xfdb014", 10, 12)]
    caller = (ROM_RAM_S_ARM_RETURN, ADDQ_L_AN_CYCLES)
    once = desk.Profile(((INI_TREE, 2 * 158), caller), 0, 0)
    assert converse_broken(desk.Profile(((INI_TREE, 158),), 0, 0), once) == []
    for short in (0, 1, 158 - 1):       # ...no pass, a stray cycle, ONE PASS TOO FEW (two short where the caller ran once)
        assert converse_broken(desk.Profile(((INI_TREE, short),), 0, 0), once) == [(f"{INI_TREE:#x}", short, 2 * 158)]
    assert converse_broken(desk.Profile(((INI_TREE, 158), caller), 0, 0), once) == [(f"{INI_TREE:#x}", 158, 2 * 158)]
    no_caller = desk.Profile(((INI_TREE, 2 * 158),), 0, 0)
    assert converse_broken(desk.Profile(((INI_TREE, 158),), 0, 0), no_caller) == [(f"{INI_TREE:#x}", 158, 2 * 158)]


@pytest.mark.parametrize("name", WALKED_ON_OUR_SHORE)
def test_the_chain_on_our_shore_is_the_rom_s_to_the_screen_the_os_and_each_rom_routine(name):
    """EACH CHAIN ON OUR SHORE (the module's docstring): every step at OUR idle or its stop of ours, its ledger whole;
    our blob ran; the screen and the desk's block the ROM's where every step ends; per step the OS's cycles and each ROM
    desk routine's own the ROM's (the converse, `converse_broken`); no cycle of the ROM's GEM text outside the
    declared spans; the four depths `DEPTHS`', PD0 under the gate."""
    declared, rom, ours = desk.CHAINS[name], desk.walked(name), desk.walked_ours(name)
    for step, stepped in zip(declared.steps, ours.steps, strict=True):
        boot = stepped.boot
        assert not boot.writes_truncated and aes_boot.blob_of(boot) is not None
        if step.until is None:
            assert boot.idle == OURS, step.what
        else:
            assert boot.idle is None and boot.registers["pc"] & BUS == desk.our_stop(step.until), step.what
    assert sum(stepped.blob for stepped in ours.steps) > 0
    for nth, (mine, theirs) in enumerate(zip(ours.steps, rom.steps)):      # ...AT EVERY STEP'S END (reviewer B's F2)
        assert desk.screen_of(mine.boot) == desk.screen_of(theirs.boot), f"the screens differ where step {nth} ends"
        assert desk.our_desk_block(mine.boot) == desk.desk_block(theirs.boot.ram), f"the desk's blocks differ where step {nth} ends"
    assert (ours.machine.ram, rom.machine.ram) == (ours.steps[-1].boot.ram, rom.steps[-1].boot.ram)
    assert [stepped.profile.os for stepped in ours.steps] == [stepped.profile.os for stepped in rom.steps]
    broken = {nth: converse_broken(mine.profile, theirs.profile) for nth, (mine, theirs) in enumerate(zip(ours.steps, rom.steps))}
    assert not any(broken.values()), f"ROM desk routines whose own cycles differ, by step: {broken}"
    declared_spans = desk.still_the_rom_s() | set(desk.ROM_TEXT_UNDER_ROM_CALLERS)
    outside = sorted({routine for stepped in ours.steps for routine in desk.charged(stepped.profile.text)} - declared_spans)
    assert not outside, f"the ROM's GEM text ran on our shore outside the declared spans: {[f'{at:#x}' for at in outside]}"
    short_of = [f"{pc:#x}" for stepped in ours.steps for pc, cycles in stepped.profile.text
                if cycles and any(start <= pc < past for start, past in desk.ENTERED_PAST_ITS_START.items())]
    assert not short_of, f"a declared span ran on our shore from before where its callers enter it: {short_of}"
    spans = desk.stacks(ours.machine)
    assert spans[desk.PD0_STACK][1] - spans[desk.PD0_STACK][0] == desk.PD0_BYTES, "our machine's PD0 is not UDA0's span"
    depths = tuple(max(desk.depth_stored(stepped.boot.stored, *spans[which]) for stepped in ours.steps) for which in STACKS)
    assert depths == DEPTHS[name], f"ours {depths}, the ROM's {tuple(desk.depths(name)[which] for which in STACKS)}"
    assert depths[0] <= pd0_gate()


# ---- band 6 slice F1: A FLIPPED ROUTINE'S ROW — its machine (`aes_desk.arrival_s_machine`) ----------------------------------------
def test_a_row_s_machine_is_the_arrival_whole_but_the_harness_s_window_and_refused_where_the_window_holds_anything():
    """A ROW AT AN ARRIVAL pokes the arrival's megabyte whole BUT the harness's window — the blobs, the staging band,
    the run's stack band — which it must hold as the snapshot does (then the cut machine IS the arrival's); a byte of
    the machine's own there is refused by name (a row would lay the blob, the staging or the run's stack over it)."""
    lo, hi = desk.HARNESS_WINDOW
    ram = bytearray(aes_boot.inf_machine().boot.ram)
    pokes = desk.arrival_s_machine(ram)
    assert sorted(pokes) == [0, hi] and pokes[0] == bytes(ram[:lo]) and pokes[hi] == bytes(ram[hi:])
    ram[lo + (hi - lo) // 2] ^= 0xFF
    with pytest.raises(Refused, match="not the snapshot's inside the harness's window"):
        desk.arrival_s_machine(ram)


# ---- N6: EVERY RUN OF `aes_boot`'s SURFACES ITS DEVICES ------------------------------------------------------------------------------
@pytest.mark.parametrize("run", (aes_boot.booted, aes_boot.continued.derive, aes_boot.served))
def test_every_run_of_aes_boot_returns_what_its_devices_left(run):
    """The three runs of the module that make a `Boot` (`_Run`'s callers there): each returns `surfaced`'s fields."""
    source = inspect.getsource(getattr(run, "__wrapped__", run))
    assert "_Run(" in source and "**surfaced(floppy, streams[1], run.printed)" in source


def test_a_boot_s_devices_are_vetted_as_a_continuation_s():
    """A BOOT'S RUN IS HELD AS EVERY OTHER: our-boot's and the ROM's surface no device and print nothing — and a GPIP
    read that is no printer's poll, in a boot's streams, is refused by name as a continuation's is."""
    for machine in (aes_boot.inf_machine(), desk.OUR_MACHINES[desk.INF_ICONS]()):
        assert (machine.boot.drive_b, machine.boot.devices, machine.boot.printed) == (None, (), b"")
    floppy = aes_boot.Floppy(aes_boot.inf_machine().image(), aes_boot.inf_disk_of())
    with pytest.raises(Refused, match="read the MFP's GPIP .* 1 time"):
        aes_boot.surfaced(floppy, ((addrs.MFP_GPIP, 0),), b"")


# ---- THE DEPTHS, PER CHAIN: `{chain: (PD0's, PD1's, the dispatcher's, the userdef stack's)}` in bytes, our shore ---------------------------
# (BAND 6 SLICE F2: a flip moves chains of every group at once, so DEPTHS — and DEEPEST_PD0 — are NOT per-group
# lines: a group's author hands back its partial flip's rows, and the ORCHESTRATOR'S INTEGRATION re-derives the
# table over the merged flip, as tier3.txt and lineftable.S are made again, never hand-merged.)
DEPTHS = {
    'Desk > Desktop Info, Return': (1104, 668, 254, 0),
    'Options > Set Preferences, Return': (1170, 668, 254, 0),
    'Options > Save Desktop, Return': (998, 668, 254, 0),
    'Options > Print Screen (its alert raised, not answered)': (998, 668, 254, 0),
    "a key typed at the desk's idle": (570, 0, 240, 0),
    'drive A: selected': (1072, 0, 254, 0),
    'A: File > Show Info, Return': (1272, 668, 254, 0),
    'A: Options > Install Disk Drive, Return': (1206, 668, 254, 0),
    'A: Options > Install Disk Drive, Remove pressed': (1206, 668, 254, 0),
    "A: Options > Install Disk Drive, 'C' typed, Install pressed": (1206, 668, 254, 0),
    'A: File > Open': (1532, 668, 254, 0),
    'A: File > Format, Return (the warning answered)': (1054, 668, 254, 0),
    'drive A: dragged to the trash, Return': (1216, 0, 254, 0),
    'a rubber box on the desktop, round the trash': (1110, 0, 254, 0),
    'A: opened': (1518, 0, 254, 0),
    'window: View > Show as Text': (1064, 750, 254, 458),
    'window: View > Sort by Size': (1064, 750, 254, 0),
    'window: File > Close Window': (1414, 668, 254, 0),
    'window: its closer clicked': (1382, 520, 260, 0),
    'window: its fuller clicked': (1180, 520, 260, 0),
    'window: A: opened again (two windows)': (1518, 0, 260, 0),
    'file: selected': (1072, 0, 254, 0),
    'file: File > Show Info, Return': (1318, 668, 254, 0),
    "file: File > Show Info, Backspace, 'A', Return (renamed)": (1318, 668, 254, 0),
    'file: File > Show Info, Read-Only pressed, Return': (1318, 668, 254, 0),
    'file: read-only, dragged to the trash, OK — access denied, Return': (1280, 0, 254, 0),
    'file: File > Open (the Show / Print / Cancel alert)': (1274, 668, 254, 0),
    'file: shown, a key at its end': (1442, 308, 240, 0),
    'file: double-clicked (the alert)': (1260, 0, 254, 0),
    "file: dragged to the trash, Return (Cancel, the dialog's default)": (1280, 0, 254, 0),
    'file: dragged to the trash, OK': (1280, 0, 254, 0),
    "folder: File > New Folder, 'A', Return": (1228, 668, 254, 0),
    'folder: the file dragged onto it, Return': (1304, 0, 254, 0),
    'folder: opened': (1414, 0, 254, 0),
    'folder: File > Close': (1458, 668, 254, 0),
    'folder: selected, File > Show Info, Return': (1354, 668, 254, 0),
    'folder: dragged to the trash, OK': (1280, 0, 254, 0),
    'text view: A: opened': (1518, 0, 254, 458),
    'text view: Options > Save Desktop, Return': (1210, 668, 254, 458),
    'files: A: opened': (1518, 0, 254, 0),
    "files: the window's down arrow clicked": (570, 706, 260, 0),
    "files: the window's vertical bar clicked under its slider (a page)": (570, 706, 260, 0),
    "files: the window's right arrow clicked": (1102, 404, 260, 0),
    "files: the long file shown, a blank at each page's end and at its end": (1442, 668, 254, 0),
    'files: the long file dragged onto the folder, Return': (1304, 0, 254, 0),
    'files: the folder (not empty) dragged to the trash, OK': (1280, 0, 254, 0),
    'files: the window made full': (1180, 520, 260, 0),
    'files: the program selected, File > Show Info, Return': (1318, 668, 254, 0),
    'files: the program selected, Options > Install Application, Return': (1294, 668, 254, 0),
    'files: View > Show as Text': (1064, 750, 254, 458),
    'window: its fuller clicked again (back to its size)': (1180, 520, 260, 0),
    'files: the right arrow clicked, then the window made full': (1180, 520, 260, 0),
    'files: the right arrow clicked, then View > Sort by Size': (1064, 750, 254, 0),
    'window: View > Show as Icons (the view it has)': (1064, 750, 254, 0),
    'window: Options > Save Desktop, Return': (1210, 668, 254, 0),
    'files: the right arrow clicked, then Options > Save Desktop, Return': (1210, 668, 254, 0),
    'a rubber box on the desktop, round drive B: and the trash': (1110, 0, 254, 0),
    'drive A: dragged to a bare spot of the desktop': (1080, 0, 254, 0),
    "drive A:'s object clicked at its corner, outside its image and its label": (570, 0, 254, 0),
    'files: View > Sort by Size': (1064, 750, 254, 0),
    'files: View > Sort by Date': (1064, 750, 254, 0),
    'files: View > Sort by Type': (1064, 750, 254, 0),
    'folder: the file dragged onto it again, Return — the name conflict, Return': (1304, 0, 254, 0),
    "folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)": (1280, 0, 254, 0),
    'folders: B dragged onto A, Return': (1304, 0, 254, 0),
    'folders: A (holding B) dragged to the trash, OK': (1280, 0, 254, 0),
    'folder: Options > Set Preferences, copies unconfirmed (the lower No), Return': (1174, 668, 254, 0),
    'folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return': (1304, 0, 254, 0),
    "files: View > Show as Text, the long file's line clicked": (924, 0, 254, 458),
    'folder: Options > Set Preferences, deletes unconfirmed (the upper No), Return': (1174, 668, 254, 0),
    'folder: deletes unconfirmed — the file dragged to the trash': (1216, 0, 254, 0),
    'folder: deletes unconfirmed — the folder dragged to the trash': (1216, 0, 254, 0),
    "files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB)": (1280, 0, 254, 0),
    'file: dragged to the trash, OK — then drive A: selected, File > Show Info, Return': (1342, 668, 260, 0),
    "file: read-only — File > New Folder, 'A', Return, the file dragged onto it, Return": (1304, 668, 254, 0),
    'A: opened, drive A: dragged into its window, Return': (1168, 0, 260, 0),
    'A: opened, the trash dragged into its window, Return': (1072, 0, 260, 0),
    'drive A: dragged onto drive B:, Return': (1216, 0, 254, 0),
    'the trash dragged onto drive A:, Return': (1216, 0, 254, 0),
    "file: dragged onto drive A:'s icon, Return — the name conflict, Return": (1280, 0, 254, 0),
    "folder: File > New Folder again, 'A', Return — the name taken, Return": (1218, 668, 254, 0),
    'file: dragged to the trash, OK — then drive A: dragged into its window': (1184, 0, 260, 0),
    'files: the right arrow clicked, then the left arrow clicked': (1102, 404, 260, 0),
    "files: the window's sizer pulled up and left (smaller)": (1074, 650, 260, 0),
    'files: the right arrow clicked, then the horizontal bar left of its slider (a page)': (1102, 404, 260, 0),
    "files: the window's right arrow gadget itself clicked (a column)": (1102, 404, 260, 0),
    "files: the window's down arrow gadget itself clicked (a row)": (570, 404, 260, 0),
    "files: the window's up arrow gadget clicked (a row)": (570, 404, 260, 0),
    "files: the window's horizontal slider dragged right": (1110, 706, 260, 0),
    'window: Esc typed (the top window read again)': (1048, 0, 240, 0),
    'two windows: File > Close Window (one left on top)': (1418, 668, 254, 0),
    'files: the window sized smaller, then its right arrow clicked': (1102, 404, 260, 0),
    'files: the right arrow clicked, then the long file shown': (1442, 668, 254, 0),
    'files: View > Sort by Size, then the long file shown': (1442, 668, 254, 0),
    "files: View > Show as Text, then the long file's line shown": (1290, 668, 254, 458),
    "files: File > New Folder, 'A', Return (a fifth entry: a second row)": (1228, 668, 254, 0),
    'two windows: View > Show as Text': (1064, 750, 254, 458),
    'files: a fifth entry, then the down arrow gadget clicked (a row)': (570, 404, 260, 0),
    "text view: A: opened, the file's line dragged to the trash, Return (Cancel)": (1280, 0, 254, 458),
    'text view: drive A: dragged to a bare spot of the desktop': (1080, 0, 254, 0),
    "A: File > Format, the warning's OK (the FORMAT dialog)": (1222, 668, 254, 0),
    'A: File > Format, OK, EXIT clicked': (890, 308, 254, 0),
    'A: File > Format, OK, FORMAT clicked (formatted)': (880, 0, 254, 0),
    "A: formatted, the alert's OK, EXIT clicked": (890, 308, 254, 0),
    "drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)": (1216, 308, 254, 0),
    'drive A: onto drive B:, OK, then Return (EXIT, the default)': (890, 308, 240, 0),
    'file: File > Open, Print clicked (the printer not ready)': (1442, 308, 254, 0),
    'file: the printer not ready, Cancel': (1234, 308, 254, 0),
    'file: the printer not ready, Retry (not ready again)': (822, 0, 254, 0),
    'file: the printer not ready, five seconds, Retry (printed)': (1234, 308, 254, 0),
    'file: File > Open, five seconds, Print clicked (printed)': (1442, 308, 254, 0),
    'file: shown, a key at its end — the file clicked, File > Open, shown again': (1442, 668, 254, 0),
    'a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type)': (1216, 308, 254, 0),
}
