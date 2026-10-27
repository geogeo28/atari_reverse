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

from harness import BASE_IMAGE, addrs

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
    """N4: THE RUBBER BOX'S POLL IS OUR gr_stilldn's ENTRY (band 3's C), the viewer's two key waits OUR C's
    `key_awaited` (the show engine ours since band 6 slice F4: `aes_desk.OUR_STOPS_ONCE_FLIPPED`), never the ROM's own
    — and each rubber box chain stands there twice, at no idle, before OUR idle."""
    blob = desk.our_blob()
    assert desk.our_stop(desk.RUBBER_BOX_POLL) == blob.entry("aes_gr_stilldn") != desk.STOPS[desk.RUBBER_BOX_POLL]
    for stop in (desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_THE_FILE_S_END):
        assert desk.our_stop(stop) == blob.entry("key_awaited") != desk.STOPS[stop]
    for name in THE_BOXES:
        first, second, last = desk.walked_ours(name).steps
        for stepped in (first, second):
            assert stepped.boot.idle is None and stepped.boot.registers["pc"] & BUS == desk.our_stop(desk.RUBBER_BOX_POLL)
        assert last.boot.idle == OURS


# ---- WHO RAN: the declared spans -------------------------------------------------------------------------------------------------------
# A chain each of `aes_desk.ROM_TEXT_UNDER_ROM_CALLERS` runs in on our shore: no span is declared that nothing runs.
RAN_IN = {}         # (unit O's five spans went with its flip, lmul with app_rdicon's at slice F2: `aes_desk`'s note)
# band 6's routines whose entry of the shipped blob's table is ours: slice F1's 56 (O + D, three held) and, since slice
# F2, each group's own count on a line inside its own block (no two authors edit one line; the pin is the sum)
BAND_6_FLIPPED_AT_F2 = {
    # ---- band 6 slice F2, group G1 (units I, L) ----
    "G1": 29,               # the 33 but do_wredraw, win_icalc, win_bldview, win_shwall
    # ---- end of group G1's ----
    # ---- band 6 slice F2, group G2 (units A, K, J) ----
    "G2": 15,               # the 17 but i_find, men_update
    # ---- end of group G2's ----
    # ---- band 6 slice F2, group G3 (units B, G) ----
    "G3": 23,               # unit G's sixteen, unit B's seven (gr_isdown, gr_bwait, act_chg, act_allchg, move_drvicon held)
    # ---- end of group G3's ----
    # ---- band 6 slice F2, group G4 (units C, H, E, F) ----
    "G4": 19,                           # unit C's ten, units H, E, F (eight), and unit D's appl_exit (⚠️ unpriced)
    # ---- end of group G4's ----
    # ---- band 6 slice F2b (the five stage artifacts) ----
    "F2b": 4,               # win_icalc, win_bldview, win_shwall, i_find (men_update held: `aes_desktop.HELD_AT_F2`)
    # ---- end of slice F2b's ----
    # ---- band 6 slice F2c (wave 1b's last thirteen) ----
    "F2c": 13,              # objc_draw, evnt_multi, men_update; do_wredraw; gr_isdown, gr_bwait, act_chg, act_allchg,
                            # move_drvicon; draw_dial, show_dial, draw_fld, do_namecon
    # ---- end of slice F2c's ----
}
# ...and since slice F3 (wave 2's forty-four, in stages — its cut), each stage-author's count on a line of its own
BAND_6_FLIPPED_AT_F3 = {
    # ---- band 6 slice F3, stage 1, author A ----
    "S1-A": 10,             # d_dofcopy, d_doop, dir_op, inf_folder, dr_code, pn_close, pn_active, cart_sfirst, cart_snext
                            # by their table entries; `$fde844` by ub_trampoline's operand (N18: `aes_desk.BY_VALUE_CALLERS`)
    # ---- end of stage 1 A's ----
    # ---- band 6 slice F3, stage 1, author B ----
    "S1B": 11,              # unit L's wave-2 five, unit B's wave-2 three, desk_clear, desk_verify, app_start
    # ---- end of stage 1 B's ----
    # ---- band 6 slice F3, stage 2, author A ----
    "S2-A": 10,             # unit H's nine but fun_d2desk, fun_drag (stage 3); app_save
    # ---- end of stage 2 A's ----
    # ---- band 6 slice F3, stage 2, author B ----
    "S2B": 10,              # unit J's seven, pro_run, do_wopen, cnx_get
    # ---- end of stage 2 B's ----
    # ---- band 6 slice F3, stage 3 ----
    "S3": 3,                # fun_d2desk, fun_drag, hndl_kbd
    # ---- end of stage 3's ----
}
# ...and slice F4 (wave 4): unit M's two built-ins and unit N's ten by their table entries (the built-ins by sh_cmd's
# door too), the engine's eight `bsr`-only parts with their built-ins (`aes_desk.parts_flipped`)
BAND_6_FLIPPED_AT_F4 = 12 + 8
# ...and band 6 W3a's stage 1 (the cycle's leaf-up split S2): deskinf.c's seven and deskins.c's two by their table entries
BAND_6_FLIPPED_AT_W3A_STAGE_1 = 9
# ...and its stage 2: desksupp.c's three, do_optnmenu and do_deskmenu by their table entries
BAND_6_FLIPPED_AT_W3A_STAGE_2 = 5
# ...and its stage 3: hndl_msg, hndl_menu, do_filemenu and hndl_button — the cycle whole
BAND_6_FLIPPED_AT_W3A_STAGE_3 = 4
BAND_6_FLIPPED = (56 + sum(BAND_6_FLIPPED_AT_F2.values()) + sum(BAND_6_FLIPPED_AT_F3.values()) + BAND_6_FLIPPED_AT_F4
                  + BAND_6_FLIPPED_AT_W3A_STAGE_1 + BAND_6_FLIPPED_AT_W3A_STAGE_2 + BAND_6_FLIPPED_AT_W3A_STAGE_3)


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


# ---- THE ENGINE'S PARTS AND SH_CMD'S DOOR, READ AS THEIR BUILT-INS ARE (band 6 slice F4's prep, rulings O2 / O4) ----------
ENGINE_SPAN = (addrs.AES_ROM_DESK_SHOW_FILE, addrs.AES_ROM_DESK_UTIL_OPEN)     # the two built-ins' entries to the next routine
SHOWN, PRINTED = addrs.AES_ROM_DESK_SHOW_FILE, addrs.AES_ROM_DESK_PRINT_FILE
VIEWER_S_FIVE = {addrs.AES_ROM_DESK_VIEWER_LOOP, addrs.AES_ROM_DESK_VIEWER_MORE, addrs.AES_ROM_DESK_VIEWER_PAGE,
                 addrs.AES_ROM_DESK_VIEWER_LINE, addrs.AES_ROM_DESK_RAWCIO_STRING}


def test_the_engine_s_parts_are_its_routines_no_table_entry_names_each_reached_by_the_built_ins_declared():
    """`aes_desk.ENGINE_PARTS` is exactly band 6's routines in the engine's span that no entry of the ROM's table names
    (`bsr`-only: ruling R-W4-5), each reached by the show or the print built-in or both — and those flipped on our blob
    are exactly the ones its two built-ins' bindings make so (none while both are held)."""
    table = set(desk._table_of(BASE_IMAGE, aes.AES_LINEF_TABLE))     # the ROM's own table's longwords
    lo, hi = ENGINE_SPAN
    assert set(desk.ENGINE_PARTS) == {start for start in desk.routines() if lo <= start < hi and start not in table}
    assert all(built_ins and set(built_ins) <= {SHOWN, PRINTED} for built_ins in desk.ENGINE_PARTS.values())
    assert set(desk.ENGINE_PARTS) & desk.flipped() == desk.parts_flipped(desk.flipped() & {SHOWN, PRINTED})


def test_a_part_reads_as_flipped_where_every_built_in_reaching_it_is_and_as_the_rom_s_where_one_is_held():
    """THE PARTS' READING, BOTH WAYS: the show flipped alone flips the viewer's five and not the engine nor its next byte
    (the print, which reaches them too, is held), nor the printer's character; the print alone, that character alone;
    both, all eight."""
    assert desk.parts_flipped(frozenset({SHOWN})) == VIEWER_S_FIVE
    assert desk.parts_flipped(frozenset({PRINTED})) == {addrs.AES_ROM_DESK_PRINT_CHAR}
    assert desk.parts_flipped(frozenset({SHOWN, PRINTED})) == set(desk.ENGINE_PARTS)
    assert desk.parts_flipped(frozenset()) == frozenset()


def test_sh_cmd_s_door_is_a_by_value_caller_and_a_routine_bound_two_ways_unalike_is_refused(monkeypatch):
    """sh_cmd's desk door is read as a by-value caller (its four built-ins, each where the blob's `jsr` names it — the
    ROM's routine while it is held), and a built-in whose door and table entry disagree — ours by one, the ROM's by the other — is
    refused by name rather than read either way."""
    blob = desk.our_blob()
    bound = desk.bound_by_value(blob)
    door = {getattr(addrs, name) for name in transcription.DESK_DOOR_BUILT_INS}
    assert door <= set(bound) and all(bound[rom] == rom for rom in door if rom not in desk.flipped())
    torn = {**bound, SHOWN: SHOWN if SHOWN in desk.flipped() else blob.entry(BOUND_TABLE)}     # unlike its table entry
    monkeypatch.setattr(desk, "bound_by_value", lambda _blob: torn)
    with pytest.raises(Refused, match="bound two ways"):
        desk._bound(blob)


def test_the_viewer_s_stops_are_ours_once_the_show_engine_is_and_refused_by_name_where_the_blob_has_no_symbol(monkeypatch):
    """THE STOPS THAT MOVE WITH A FLIP (ruling O3): while the show engine is the ROM's on our machine, the viewer's key
    waits are the ROM's addresses (`our_stops` is `OUR_STOPS`); once it is flipped they are our C's `key_awaited` —
    refused by name where the blob holds no such symbol (an inlined key wait has no entry to stop at)."""
    blob = desk.our_blob()
    viewer = set(desk.OUR_STOPS_ONCE_FLIPPED)
    if SHOWN not in desk.flipped(blob):
        assert desk.our_stops(blob) == desk.OUR_STOPS
    monkeypatch.setattr(desk, "flipped", lambda _blob=None: frozenset({SHOWN}))
    assert set(desk.our_stops(blob)) == set(desk.OUR_STOPS) | viewer
    refused = set()
    for stop in viewer:
        symbol = desk.our_stops(blob)[stop]
        if symbol in blob.symbols:
            assert desk.our_stop(stop, blob) == blob.entry(symbol)
        else:
            with pytest.raises(Refused, match=desk.A_STOP_NOT_IN_THE_BLOB):
                desk.our_stop(stop, blob)
            refused.add(stop)
    assert _the_tool().stops_our_stop_refuses(desk, blob) == refused      # ...the tool's reading of the flipped blob


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
    # ---- band 6 slice F2, group G2 (units A, K, J) ---- (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`)
    # EVERY ROM CALLER FLIPPED at slice F2 (group G2) — called by our C alone on our shore: two of the group's own, a binding
    # of unit D's and a glue leaf of unit O's, whose last ROM callers were the group's...
    **{name: f"its every ROM caller flipped at band 6 slice F2 (group G2: {callers}): called by our C alone on our shore" for name, callers in {
        "AES_ROM_APP_TRAN": "app_rdicon", "AES_ROM_DESK_APPL_BVSET": "app_blddesk", "AES_ROM_DOS_GDIR": "app_path_save"}.items()},
    # ...and one whose ROM callers still the ROM's reach it on NO WALKED CHAIN (measured here) — its flipped callers'
    # calls are our C's (scan_str's, the Install Application dialog's, reached since band 6 W3a's diet landed opn_appl's chain)
    "AES_ROM_WIN_VIEW": "its ROM callers but do_viewmenu and win_start (flipped at slice F2) are do_dopen's (the ROM's, wave 2), "
                        "which reaches it on no walked chain",
    # ---- end of group G2's ----
    # ---- band 6 slice F2, group G3 (units B, G) ---- ...CALLED BY OUR C ALONE: every Line-F call word of the routine in the
    # ROM's GEM text lies in a routine G3 flipped at slice F2 (read off the image: `test_desk_act.CALLED_BY_G3_ALONE`) —
    # five of unit G's own, unit D's objc_find binding and band 4's gsx_pline
    **{f"AES_ROM_{routine}": f"its every call word in the ROM's text lies in {caller}, flipped at slice F2 (group G3): only "
                             f"our C calls it" for routine, caller in (
        ("FN_INIT", "fpd_start"), ("PN_INIT", "fpd_start"), ("FPD_BLDSPEC", "pn_open"), ("PN_ALLOC", "pn_open"),
        ("FPD_ELIST", "fl_free"), ("PN_COMP", "pn_sort"), ("PN_FCOMP", "pn_comp"),
        ("DESK_OBJC_FIND", "gr_obfind (unit D's binding: no kit call enters its thunk either, `test_aes_lineftable.UNENTERED`)"),
        ("GSX_PLINE", "gr_plns"))},
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
    # ---- band 6 slice F2b ---- EVERY ROM CALLER FLIPPED, the last at slice F2b (i_find, win_bldview): called by our C
    # alone on our shore (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`)
    **{name: f"its every ROM caller flipped (the last at band 6 slice F2b: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_FPD_OFIND": "i_find",
           "AES_ROM_WIN_ICALC": "win_bldview", "AES_ROM_WIN_OCALC": "win_bldview", "AES_ROM_OBJ_IALLOC": "app_blddesk, win_bldview",
           "AES_ROM_OBJ_WFREE": "app_blddesk, win_free, win_bldview"}.items()},
    # ---- end of slice F2b's ----
    # ---- band 6 slice F2c ---- EVERY ROM CALLER FLIPPED, the last at slice F2c: called by our C alone on our shore (each
    # one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`; MEASURED by who-ran, which named exactly these)
    **{name: f"its every ROM caller flipped (the last at band 6 slice F2c: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_MEN_LIST": "men_update", "AES_ROM_DESK_MENU_IENABLE": "men_list, men_update",
           "AES_ROM_GR_ISDOWN": "gr_bwait", "AES_ROM_GR_PLNS": "gr_bwait", "AES_ROM_DESK_OBJC_CHANGE": "act_chg",
           "AES_ROM_ACT_CHKOBJ": "gr_obfind, act_allchg", "AES_ROM_DESK_DRAW_DIAL": "do_namecon",
           "AES_ROM_DESK_OBJC_OFFSET": "draw_fld"}.items()},
    # ---- end of slice F2c's ----
    # ---- band 6 slice F3, stage 1, author A ---- EVERY ROM CALLER FLIPPED, the last at slice F3's stage 1 (author A):
    # called by our C alone on our shore (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`;
    # MEASURED by who-ran, which named exactly these) — dr_code's by `$fde844`, flipped by its operand (N18) — and the
    # cartridge's pair: its one ROM caller pn_active, flipped too, so the labelled chain that reaches it (the fix pass:
    # `aes_desk.CARTRIDGE_OPENED`) enters our C pn_active, which calls their cores, never their thunks
    **{name: f"its every ROM caller flipped (the last at band 6 slice F3, stage 1: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_DESK_D_DOFCOPY": "d_doop, dir_op", "AES_ROM_DESK_D_DOOP": "dir_op, inf_folder",
           "AES_ROM_DESK_DR_CODE": "the userdef draw `$fde844`", "AES_ROM_DESK_OB_SFCB": "dr_code",
           "AES_ROM_DESK_ADD_PATH": "d_doop, dir_op", "AES_ROM_DESK_SUB_PATH": "d_doop", "AES_ROM_DESK_GET_FNAME": "d_dofcopy",
           "AES_ROM_DESK_DO_NAMECON": "d_dofcopy, dir_op", "AES_ROM_DESK_DRAW_FLD": "d_doop, dir_op",
           "AES_ROM_DESK_D_DOFDEL": "d_dofcopy, d_doop, dir_op", "AES_ROM_DOS_CREATE": "app_getfh, d_dofcopy",
           "AES_ROM_DOS_RMDIR": "d_doop", "AES_ROM_DOS_SETDT": "d_dofcopy", "AES_ROM_PN_FREE": "pn_close",
           "AES_ROM_FL_FREE": "pn_free, pn_active", "AES_ROM_FN_ALLOC": "pn_active", "AES_ROM_FN_FREE": "pn_active"}.items()},
    **{name: "its every ROM caller flipped (the last at band 6 slice F3, stage 1: pn_active): called by our C alone on our "
             "shore — on the labelled chain that opens drive 'c' (`aes_desk.CARTRIDGE_OPENED`, `test_desk_util.py`)"
       for name in ("AES_ROM_CART_SFIRST", "AES_ROM_CART_SNEXT")},
    # ---- end of stage 1 A's ----
    # ---- band 6 slice F3, stage 1, author B ---- EVERY ROM CALLER FLIPPED, the last at slice F3's stage 1 (author B):
    # called by our C alone on our shore (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`;
    # MEASURED by who-ran, which named exactly these)
    **{name: f"its every ROM caller flipped (the last at band 6 slice F3, stage 1: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_WIN_BLT": "win_slide, win_arrow", "AES_ROM_WIN_BLDVIEW": "desk_verify, win_blt, win_bdall",
           "AES_ROM_APP_PARSE": "app_start", "AES_ROM_APP_RDICON": "app_start",
           "AES_ROM_GR_DRGPLNS": "act_bdown", "AES_ROM_GR_ACCOBS": "act_bdown", "AES_ROM_MOVE_DRVICON": "act_bdown",
           "AES_ROM_DESK_EVNT_BUTTON": "act_bdown", "AES_ROM_DESK_GRAF_RUBBOX": "act_bdown",
           "AES_ROM_GR_BWAIT": "gr_drgplns", "AES_ROM_GR_EXTENT": "gr_drgplns", "AES_ROM_GR_OBALIGN": "gr_drgplns",
           "AES_ROM_GR_OBFIND": "gr_drgplns, act_bsclick, act_bdown",
           "AES_ROM_ACT_ALLCHG": "act_bsclick, act_bdown, desk_clear"}.items()},
    # ...and the one STAGE 1 WHOLE names (the integration's, who-ran's): its two ROM callers flipped one by each author
    "AES_ROM_PN_SORT": "its every ROM caller flipped (the last at band 6 slice F3, stage 1: pn_active, win_srtall): called by "
                       "our C alone on our shore",
    # ---- end of stage 1 B's ----
    # ---- band 6 slice F3, stage 2, author A ---- EVERY ROM CALLER FLIPPED, the last at slice F3's stage 2 (author A):
    # called by our C alone on our shore (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`;
    # MEASURED by who-ran, which named exactly these) — and fun_msg, whose third ROM caller, unit N's desk_util_error (held,
    # wave 4), is on no walked chain
    **{name: f"its every ROM caller flipped (the last at band 6 slice F3, stage 2: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_APP_GETFH": "app_start, app_save", "AES_ROM_APP_PATH_RESTORE": "app_save", "AES_ROM_APP_PATH_SAVE": "app_save",
           "AES_ROM_APP_REVIT": "app_save", "AES_ROM_SAVE_STR": "app_save", "AES_ROM_DOS_WRITE": "app_save",
           "AES_ROM_DESK_SHEL_GET": "app_start, app_save", "AES_ROM_DESK_SHEL_PUT": "app_save",
           "AES_ROM_DESK_ADD_FNAME": "d_dofcopy, d_doop, dir_op, fun_mkdir", "AES_ROM_DESK_DEL_FNAME": "d_dofcopy, d_doop, dir_op, fun_mkdir",
           "AES_ROM_DESK_HIDE_DIAL": "dir_op, fun_mkdir", "AES_ROM_DESK_SHOW_DIAL": "do_namecon, dir_op, fun_mkdir",
           "AES_ROM_DOS_MKDIR": "d_doop, dir_op, fun_mkdir", "AES_ROM_DESK_DIR_OP": "fun_op", "AES_ROM_DESK_PAR_CHK": "fun_op",
           "AES_ROM_WIN_ITH": "fun_rebld, cnx_put, win_shwall",
           "AES_ROM_DESK_FUN_OP": "fun_ddst, fun_wdst", "AES_ROM_DESK_FUN_DDST": "fun_win2desk, fun_disk",
           "AES_ROM_DESK_FUN_WDST": "fun_win2win, fun_disk", "AES_ROM_DESK_FUN_DISK": "fun_desk2win"}.items()},
    "AES_ROM_DESK_FUN_MSG": "its every ROM caller on a walked chain flipped (the last at band 6 slice F3, stage 2: fun_rebld; "
                            "win_shwall before it): unit N's desk_util_error, held, is on no walked chain",
    # ---- end of stage 2 A's ----
    # ---- band 6 slice F3, stage 2, author B ---- EVERY ROM CALLER FLIPPED, the last at slice F3's stage 2 (author B):
    # called by our C alone on our shore (each one's ROM callers read off the GEM text: `aes_deskarrive.rom_callers`;
    # MEASURED by who-ran, which named exactly these)
    **{name: f"its every ROM caller flipped (the last at band 6 slice F3, stage 2: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_ACT_CHG": "do_wopen", "AES_ROM_CLOSE_FOLDER": "fun_close", "AES_ROM_CLOSE_WINDOW": "fun_close",
           "AES_ROM_DESK_GRAF_GROWBOX": "do_wopen", "AES_ROM_DESK_WIND_OPEN": "do_wopen", "AES_ROM_DO_WOPEN": "do_diropen, pro_run",
           "AES_ROM_PRO_EXEC": "pro_run", "AES_ROM_WIN_INAME": "desk_do_format", "AES_ROM_WIN_SNAME": "do_diropen",
           "AES_ROM_ZOOM_CLOSED": "close_folder, close_window"}.items()},
    "AES_ROM_WIN_FREE": "its every ROM caller flipped (the last at band 6 slice F3, stage 2: close_window, cnx_get, do_dopen): "
                        "called by our C alone on our shore",
    "AES_ROM_DESK_EVNT_DCLICK": "its every ROM caller flipped (the last at band 6 slice F3, stage 2: cnx_get): called by our C "
                                "alone on our shore",
    "AES_ROM_WIN_ALLOC": "its every ROM caller flipped (the last at band 6 slice F3, stage 2: cnx_get, do_dopen): called by our "
                         "C alone on our shore",
    # ...and STAGE 2 WHOLE's (the merge's, who-ran's on the tree of both stage-2 authors — the pn_sort class): ROM callers
    # flipped one or more by each author
    **{name: f"its every ROM caller flipped (the last at band 6 slice F3, stage 2, by both authors: {callers}): called by our C "
             "alone on our shore"
       for name, callers in {
           "AES_ROM_DO_DIROPEN": "fun_ddst; cnx_get, do_dopen, do_fopen", "AES_ROM_PN_ACTIVE": "fun_rebld, fun_disk; do_diropen",
           "AES_ROM_PN_CLOSE": "fun_disk; do_fopen, close_window", "AES_ROM_PN_OPEN": "fun_disk; do_diropen",
           "AES_ROM_WIN_SINFO": "fun_rebld; do_diropen"}.items()},
    # (win_top `$fe2cf4` — its last ROM caller hndl_msg `$fe2344`, held, whose walked runs never reached its call — LEFT THE
    # LIST at band 6 W3a's prep: the WM_TOPPED chain's hndl_msg calls it on our shore)
    # ---- end of stage 2 B's ----
    # ---- band 6 slice F3, stage 3 ---- (who-ran's on the stage's tree: fun_drag's four drivers, called by its C alone now,
    # and app_afind, whose last ROM caller was fun_d2desk)
    **{f"AES_ROM_DESK_FUN_{driver}": "its every ROM caller flipped (the last at band 6 slice F3, stage 3: fun_drag): called by "
                                     "our C alone on our shore"
       for driver in ("D2DESK", "DESK2WIN", "WIN2DESK", "WIN2WIN")},
    "AES_ROM_APP_AFIND": "its every ROM caller flipped (the last at band 6 slice F3, stage 3: fun_d2desk): called by our C alone "
                         "on our shore",
    # ---- end of stage 3's ----
    # ---- band 6 slice F4 ---- (who-ran's on the slice's tree; each one's ROM callers read off the GEM text:
    # `aes_deskarrive.rom_callers`) — unit N's helpers, called by Format's and the copy's C alone now; the four built-ins
    # are entered by sh_cmd's door (`aes_desk.BY_VALUE_CALLERS`)...
    **{name: f"its every ROM caller flipped (the last at band 6 slice F4: {callers}): called by our C alone on our shore"
       for name, callers in {
           "AES_ROM_DESK_UTIL_OPEN": "desk_format, desk_copy_disk",
           "AES_ROM_DESK_UTIL_SHOW": "desk_format, desk_copy_disk, util_bars, copy_tracks",
           "AES_ROM_DESK_UTIL_REDRAW": "desk_format, util_error", "AES_ROM_DESK_UTIL_BARS": "desk_format, desk_copy_disk",
           "AES_ROM_DESK_UTIL_ERROR": "desk_format, desk_copy_disk, copy_tracks", "AES_ROM_DESK_COPY_TRACKS": "desk_copy_disk",
           "AES_ROM_DOS_AVAIL": "desk_copy_disk, viewer_line; dir_op at slice F3",
           "AES_ROM_DOS_RAWCIO": "the engine's parts show_or_print, viewer_loop, viewer_more, viewer_line, rawcio_string"}.items()},
    # ...two no run reaches at all: Format's bad-sector arm, which no disk of the device model takes (Flopfmt answers 0)
    "AES_ROM_DESK_FAT_MARK": "its one ROM caller, desk_format (flipped at band 6 slice F4), calls it in its bad-sector arm alone, "
                             "which no run of the device model reaches (Tier 1 holds it over argument classes)",
    "AES_ROM_DESK_FAT_SWAP": "its one ROM caller, fat_mark (flipped at band 6 slice F4), is reached by no run (above)",
    # ...one whose ROM callers but one are flipped, and that one reaches it on no walked chain
    "AES_ROM_DESK_RSRC_GADDR": "its ROM callers flipped (the last on a walked chain at band 6 slice F4: util_open) but desk_open "
                               "`$fe1568`'s (the ROM's), whose walked runs never reach its call: called by our C alone on our shore",
    # ...and THE ENGINE'S EIGHT `bsr`-ONLY PARTS (R-W4-5): static C inside the two built-ins, flipped with them
    # (`aes_desk.parts_flipped`) — no table entry, so no entry of ours to enter: their ROM spans running no cycle is the hold
    **{f"AES_ROM_DESK_{part}": "a `bsr`-only part of the show / print engine (no table entry: R-W4-5), flipped with its "
                               "built-ins at band 6 slice F4: static C inside them, no entry of ours to enter"
       for part in ("SHOW_OR_PRINT", "SHOW_NEXT_BYTE", "VIEWER_LOOP", "VIEWER_MORE", "VIEWER_PAGE", "VIEWER_LINE",
                    "RAWCIO_STRING", "PRINT_CHAR")},
    # ---- end of slice F4's ----
    # ---- band 6 W3a, stage 1 ---- (who-ran's on the stage's tree, MEASURED): THE NINE DIALOGS' CALLEES whose every
    # call on a walked chain was a dialog's — the dialog bindings inf_show runs (form_center, form_dial, form_do,
    # objc_draw, graf_mouse), Show Info's fields, counts and glue (inf_field, inf_dttmsz, inf_folder, inf_finish,
    # d_errmsg, dos_rename, dos_chmod, dos_label, dos_space), the install dialogs' ANODE leaves (app_alloc, app_free,
    # snap_disk, scan_str): called by our C alone on our shore since the stage
    **{f"AES_ROM_{routine}": "its every call on a walked chain is one of the nine dialogs' (flipped at band 6 W3a's stage "
                             "1): called by our C alone on our shore"
       for routine in ("DESK_FORM_CENTER", "DESK_FORM_DIAL", "DESK_FORM_DO", "DESK_OBJC_DRAW", "DESK_GRAF_MOUSE",
                       "DESK_INF_FIELD", "DESK_INF_DTTMSZ", "DESK_INF_FOLDER", "DESK_INF_FINISH", "DESK_D_ERRMSG",
                       "DOS_RENAME", "DOS_CHMOD", "DOS_LABEL", "DOS_SPACE", "APP_ALLOC", "APP_FREE", "SNAP_DISK",
                       "SCAN_STR")},
    # ---- end of W3a stage 1's ----
    # ---- band 6 W3a, stage 2 ---- (who-ran's on the stage's tree, MEASURED): THE CALLEES WHOSE EVERY CALL ON A WALKED
    # CHAIN WAS ONE OF THE FIVE'S — stage 1's nine dialogs (do_info's, do_optnmenu's, do_deskmenu's, opn_appl under
    # do_aopen), the openers (do_aopen, do_dopen, do_fopen, drive_check), and what the five ask (i_find, fpd_parse,
    # get_spec, get_xywh, pro_chdir, ini_str, pro_cmd, pro_run, fun_alert, fun_rebld, form_alert): called by our C alone
    **{f"AES_ROM_{routine}": "its every call on a walked chain is one of stage 2's five's (flipped at band 6 W3a's "
                             "stage 2): called by our C alone on our shore"
       for routine in ("DESK_INF_SHOW", "DESK_INF_FILE", "DESK_INF_FOLDER_DLG", "DESK_INF_DISK", "DESK_INF_PREF",
                       "DESK_OPN_APPL", "DESK_INS_DISK", "DESK_INS_APP", "DO_AOPEN", "DO_DOPEN", "DO_FOPEN", "DRIVE_CHECK",
                       "I_FIND", "FPD_PARSE", "GET_SPEC", "GET_XYWH", "PRO_CHDIR", "INI_STR", "PRO_CMD", "PRO_RUN",
                       "DESK_FUN_ALERT", "DESK_FUN_REBLD", "DESK_FORM_ALERT")},
    # ---- end of W3a stage 2's ----
    # ---- band 6 W3a, stage 3 ---- (who-ran's on the stage's tree, MEASURED): THE CALLEES WHOSE EVERY CALL ON A WALKED
    # CHAIN WAS ONE OF THE FOUR'S — hndl_menu and do_filemenu themselves, the menus' handlers (do_deskmenu, do_viewmenu,
    # do_optnmenu, do_open, do_info, Format's do_format), the window messages' acts (do_wfull, do_xyfix, win_arrow,
    # win_slide, win_top, fun_close, fun_mkdir) and the button's (wind_find, act_bsclick, graf_mkstate, act_bdown,
    # fun_drag), the View arm's (win_srtall, win_bdall, win_shwall), and what the four ask (win_ontop, win_isel,
    # win_find, desk_clear, menu_tnormal): called by our C alone — deskmain still enters hndl_msg and hndl_button
    **{f"AES_ROM_{routine}": "its every call on a walked chain is one of stage 3's four's (flipped at band 6 W3a's "
                             "stage 3): called by our C alone on our shore"
       for routine in ("HNDL_MENU", "DO_FILEMENU", "DO_DESKMENU", "DO_VIEWMENU", "DO_OPTNMENU", "DO_OPEN", "DO_INFO",
                       "DESK_DO_FORMAT", "DO_WFULL", "DO_XYFIX", "WIN_ARROW", "WIN_SLIDE", "WIN_TOP", "FUN_CLOSE",
                       "DESK_FUN_MKDIR", "DESK_WIND_FIND", "ACT_BSCLICK", "DESK_GRAF_MKSTATE", "ACT_BDOWN", "DESK_FUN_DRAG",
                       "WIN_SRTALL", "WIN_BDALL", "WIN_SHWALL", "WIN_ONTOP", "WIN_ISEL", "WIN_FIND", "DESK_CLEAR",
                       "DESK_MENU_TNORMAL")},
    # ---- end of W3a stage 3's ----
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
    the ROM's in the built table under a verdict of ours is no flip, and reds here before any count does — and (band 6
    slice F3, N18) the routines bound BY VALUE (`aes_desk.bound_by_value`: ub_trampoline's, and since slice F4's prep
    sh_cmd's desk door) are flipped exactly where the generator holds none of them back (`LINKED_HELD_NO_TABLE_ENTRY`,
    `LINKED_AND_NOT_FLIPPED`) — and the engine's parts exactly where their built-ins are (`aes_desk.parts_flipped`)."""
    generator = _the_generator()
    ours = {entry.target for entry in generator.entries() if entry.verdict != generator.THE_ROM_S}
    held = {getattr(addrs, name) for name in (*generator.LINKED_HELD_NO_TABLE_ENTRY, *generator.LINKED_AND_NOT_FLIPPED)}
    bound_ours = frozenset(ours | (set(desk.bound_by_value(desk.our_blob())) - held)) & frozenset(desk.routines())
    assert desk.flipped() == bound_ours | desk.parts_flipped(bound_ours), "the blob's binding and the generator's verdicts disagree"
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
DEEPEST_PD0 = ("A: opened", 1500)     # (File > Open 1,534 before band 6 W3a's stage 3, 1,536 before its stage 2; 1,504 before slice F1)


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


def test_the_tool_s_flip_is_the_generator_s_and_moves_sh_cmd_s_door_with_the_table(monkeypatch):
    """THE DESK DOOR MOVES WITH THE TABLE (band 6 slice F4's prep, ruling O2): the generator over an empty held list
    makes the four built-ins' thunks — the table's own — the table's only other `.globl`s, and binds sh_cmd's door to
    them (`include/aes/lineftable.h`); the tool's flip is that generator and copies no thunk. On the tree as it is, the
    blob's door `jsr`s each built-in where the generator binds it: its thunk if it is thunked, else the ROM's routine."""
    tool, generator = _the_tool(), _the_generator()
    door, thunked, blob = transcription.DESK_DOOR_THUNKS, set(generator.thunked_routines()), desk.our_blob()
    assert not hasattr(tool, "door_thunks") and not hasattr(tool, "sh_cmd_flipped")
    assert transcription.desk_door_bindings(blob.elf) == {getattr(addrs, name): blob.entry(thunk) if name in thunked else getattr(addrs, name)
                                                      for thunk, name in door.items()}
    monkeypatch.setattr(generator, "LINKED_AND_NOT_FLIPPED", {})
    globls = set(transcription.GLOBL.findall(generator.text()))
    assert globls == {BOUND_TABLE, *door}
    transcription.vet_the_table_s_globls(globls)
    flipped_door = generator.door_text()
    assert all(f"{generator.DOOR_BOUND_PREFIX}{name} {thunk} " in flipped_door for thunk, name in door.items())


def test_the_table_s_globls_are_the_table_and_the_door_s_thunks_alone():
    """THE NAMED EXCEPTION, HELD BOTH WAYS: a `.globl` of the table's source other than the table and the desk door's
    four thunks is refused, and the table is required."""
    transcription.vet_the_table_s_globls({BOUND_TABLE, *transcription.DESK_DOOR_THUNKS})
    for refused in ({BOUND_TABLE, "linef_to_aes_desk_util_open"}, set(transcription.DESK_DOOR_THUNKS)):
        with pytest.raises(AssertionError, match="other `.globl`s"):
            transcription.vet_the_table_s_globls(refused)


# ...AND ITS THREE SELF-CHECKS (slice D's fix pass: the review's F1-F3), each held where it can be without a flipped build.
def test_the_tool_reads_every_held_routine_with_an_entry_as_the_rom_s_off_today_s_unflipped_blob():
    """THE FLIPPED CHECK reads the blob's OWN bound table: on today's shipped blob — units O and D flipped, the rest held
    (band 6 slice F1) — it reports exactly the routines the generator still holds back that have an entry of the table,
    so a flip step lost in a private tree (the review's T1) is refused before a walk. (The routines held with no entry
    of the table — `$fde844` alone, until band 6 slice F3's N18 flipped it by its operand — are none now.)"""
    tool, generator = _the_tool(), _the_generator()
    with_no_entry = {getattr(addrs, name) for name in generator.LINKED_HELD_NO_TABLE_ENTRY}
    held = {getattr(addrs, name) for name in generator.LINKED_AND_NOT_FLIPPED}
    assert not with_no_entry
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



VIEWER_CHAINS = 8                       # the chains with a step at the viewer's key waits (N4's: the F4 cut)


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


def test_the_tool_s_declared_refusals_are_w6_r8_s_two_and_every_chain_that_stops_where_the_flipped_blob_has_no_stop():
    """W6-R8's two are this battery's (`REFUSED_ON_OUR_SHORE`, reading what it reads); the flipped state's are DERIVED
    (band 6 slice F4's prep, ruling O3): every chain with a step at a named stop the flipped blob has no C-side stop
    for — the viewer's key waits while `key_awaited` is inlined — reading `our_stop`'s refusal, and none once it is not."""
    tool = _the_tool()
    assert set(tool.REFUSED_ON_EITHER_STATE) == set(REFUSED_ON_OUR_SHORE)
    assert all(reads in REFUSED_ON_OUR_SHORE[name][2] for name, (_why, reads) in tool.REFUSED_ON_EITHER_STATE.items())
    viewer = set(desk.OUR_STOPS_ONCE_FLIPPED)
    stopping = {name for name, chain in desk.CHAINS.items() if any(step.until in viewer for step in chain.steps)}
    refused = tool.refused_on_the_flipped_state(desk.CHAINS, viewer)
    assert set(refused) == stopping and len(stopping) == VIEWER_CHAINS
    assert all(reads == desk.A_STOP_NOT_IN_THE_BLOB for _why, reads in refused.values())
    assert tool.refused_on_the_flipped_state(desk.CHAINS, set()) == {}
    assert tool.declared_refusals(unflipped=False, on_the_flipped_state=refused) == tool.REFUSED_ON_EITHER_STATE | refused
    assert tool.declared_refusals(unflipped=True, on_the_flipped_state=refused) == tool.REFUSED_ON_EITHER_STATE


# ---- W6-R4's DIET, ON THE SHIPPED ELF (slice D): the split helpers stay routines of their own -----------------------------
# The diet's PD0 numbers are the tool's (a flipped build: minutes); what makes them is held here in seconds — each
# helper a routine of the shipped ELF (inlined back, its frame or its arguments stand under a deep draw again: the
# review measured +16..+68 B over the gate), act_redrawn_inside none (called, +20), and win_bldview leaving to its
# sliders by a JUMP (a call would stand its frame under the sliders' redraw). `include/stack_diet.h` lists them.
PD0_SPLIT_HELPERS = ("lay_the_items", "the_sliders_set", "zoom_onto_the_middle", "get_rect_called", "the_rectangles_read",
                     "the_command_run", "the_window_s_path_named", "the_window_redrawn",
                     "allchg_walked",     # band 6 W3a's diet: inlined, act_allchg's walk saves 11 registers under its redraw
                     # band 6 W3a's stage 1 (opn_appl's Cancel, hndl_msg's redraws under inf_show): the dialog's run, its
                     # message question, and opn_appl's three parts round its dialog — no frame of theirs under hndl_msg
                     "dialog_run", "messages_asked", "appl_fields_set", "appl_dialog_run", "appl_fields_read",
                     # band 6 W3a's stage 2 (do_open's frame the ROM's 146 bytes over a drive's window; do_aopen's under
                     # opn_appl's dialog): what do_open's window, folder and trash arms keep, and do_aopen's two boxes
                     "the_window_s_spec_parsed", "folder_joined", "the_trash_refused", "the_boxes_read",
                     # band 6 W3a's stage 3: hndl_msg's two window arms that keep a box (TOPPED, SIZED / MOVED) and
                     # hndl_button's one click and two — no box of theirs under MN_SELECTED's menus or the opener
                     "window_topped", "window_placed", "one_click", "two_clicks")
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
# ...and a probe OUTSIDE the class (F2 stage 2's fix pass, reviewer B's F1): with the class empty, a routine outside it
# is the reader's ONLY live branch on every real chain — scan_str's entry, laid back as still the ROM's for this test
# alone (it is flipped since stage 2), so the probe holds whatever flips next.
OUTSIDE_THE_CLASS = 0xfdb014


def test_the_converse_reader_holds_a_differing_routine_and_the_class_one_pass_a_caller_s_run_exactly(monkeypatch):
    monkeypatch.setitem(RUN_UNDER_BANDS_0_TO_5, INI_TREE, INI_TREE_UNDER_ROM_RAM)
    still = desk.still_the_rom_s() | {INI_TREE, OUTSIDE_THE_CLASS}
    monkeypatch.setattr(desk, "still_the_rom_s", lambda blob=None: still)
    # (a differing routine: ini_tree itself, with no caller run; and one outside the class, reported plainly)
    one, two = desk.Profile(((INI_TREE, 10),), 0, 0), desk.Profile(((INI_TREE, 12),), 0, 0)
    assert converse_broken(one, one) == [] and converse_broken(one, two) == [(f"{INI_TREE:#x}", 10, 12)]
    plain, other = desk.Profile(((OUTSIDE_THE_CLASS, 10),), 0, 0), desk.Profile(((OUTSIDE_THE_CLASS, 12),), 0, 0)
    assert OUTSIDE_THE_CLASS not in RUN_UNDER_BANDS_0_TO_5
    assert converse_broken(plain, other) == [(f"{OUTSIDE_THE_CLASS:#x}", 10, 12)]
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
    'Desk > Desktop Info, Return': (1124, 668, 254, 0),
    'Options > Set Preferences, Return': (1232, 668, 254, 0),
    'Options > Save Desktop, Return': (1004, 668, 254, 0),
    'Options > Print Screen (its alert raised, not answered)': (1004, 668, 254, 0),
    "a key typed at the desk's idle": (658, 0, 240, 0),
    'drive A: selected': (1232, 0, 254, 0),
    'A: File > Show Info, Return': (1292, 668, 254, 0),
    'A: Options > Install Disk Drive, Return': (1268, 668, 254, 0),
    'A: Options > Install Disk Drive, Remove pressed': (1268, 668, 254, 0),
    "A: Options > Install Disk Drive, 'C' typed, Install pressed": (1268, 668, 254, 0),
    'A: File > Open': (1488, 668, 254, 0),
    'A: File > Format, Return (the warning answered)': (1020, 668, 254, 0),
    'drive A: dragged to the trash, Return': (1460, 0, 254, 0),
    'a rubber box on the desktop, round the trash': (1288, 0, 254, 0),
    'A: opened': (1500, 0, 254, 0),
    'window: View > Show as Text': (1156, 750, 254, 486),
    'window: View > Sort by Size': (1156, 750, 254, 0),
    'window: File > Close Window': (1444, 668, 254, 0),
    'window: its closer clicked': (1400, 520, 260, 0),
    'window: its fuller clicked': (1172, 520, 260, 0),
    'window: A: opened again (two windows)': (1500, 0, 260, 0),
    'file: selected': (1232, 0, 254, 0),
    'file: File > Show Info, Return': (1308, 668, 254, 0),
    "file: File > Show Info, Backspace, 'A', Return (renamed)": (1308, 668, 254, 0),
    'file: File > Show Info, Read-Only pressed, Return': (1308, 668, 254, 0),
    'file: read-only, dragged to the trash, OK — access denied, Return': (1460, 0, 254, 0),
    'file: File > Open (the Show / Print / Cancel alert)': (1208, 668, 254, 0),
    'file: shown, a key at its end': (1372, 308, 240, 0),
    'file: double-clicked (the alert)': (1220, 0, 254, 0),
    "file: dragged to the trash, Return (Cancel, the dialog's default)": (1460, 0, 254, 0),
    'file: dragged to the trash, OK': (1460, 0, 254, 0),
    "folder: File > New Folder, 'A', Return": (1336, 668, 254, 0),
    'folder: the file dragged onto it, Return': (1472, 0, 254, 0),
    'folder: opened': (1468, 0, 254, 0),
    'folder: File > Close': (1484, 668, 254, 0),
    'folder: selected, File > Show Info, Return': (1276, 668, 254, 0),
    'folder: dragged to the trash, OK': (1460, 0, 254, 0),
    'text view: A: opened': (1500, 0, 254, 486),
    'text view: Options > Save Desktop, Return': (1300, 668, 254, 486),
    'files: A: opened': (1500, 0, 254, 0),
    "files: the window's down arrow clicked": (658, 706, 260, 0),
    "files: the window's vertical bar clicked under its slider (a page)": (658, 706, 260, 0),
    "files: the window's right arrow clicked": (1140, 404, 260, 0),
    "files: the long file shown, a blank at each page's end and at its end": (1372, 668, 254, 0),
    'files: the long file dragged onto the folder, Return': (1472, 0, 254, 0),
    'files: the folder (not empty) dragged to the trash, OK': (1460, 0, 254, 0),
    'files: the window made full': (1172, 520, 260, 0),
    'files: the program selected, File > Show Info, Return': (1308, 668, 254, 0),
    'files: the program selected, Options > Install Application, Return': (1336, 668, 254, 0),
    'files: View > Show as Text': (1156, 750, 254, 486),
    'window: its fuller clicked again (back to its size)': (1172, 520, 260, 0),
    'files: the right arrow clicked, then the window made full': (1172, 520, 260, 0),
    'files: the right arrow clicked, then View > Sort by Size': (1156, 750, 254, 0),
    'window: View > Show as Icons (the view it has)': (1156, 750, 254, 0),
    'window: Options > Save Desktop, Return': (1300, 668, 254, 0),
    'files: the right arrow clicked, then Options > Save Desktop, Return': (1300, 668, 254, 0),
    'a rubber box on the desktop, round drive B: and the trash': (1288, 0, 254, 0),
    'drive A: dragged to a bare spot of the desktop': (1328, 0, 254, 0),
    "drive A:'s object clicked at its corner, outside its image and its label": (718, 0, 254, 0),
    'files: View > Sort by Size': (1156, 750, 254, 0),
    'files: View > Sort by Date': (1156, 750, 254, 0),
    'files: View > Sort by Type': (1156, 750, 254, 0),
    'folder: the file dragged onto it again, Return — the name conflict, Return': (1472, 0, 254, 0),
    "folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)": (1460, 0, 254, 0),
    'folders: B dragged onto A, Return': (1472, 0, 254, 0),
    'folders: A (holding B) dragged to the trash, OK': (1460, 0, 254, 0),
    'folder: Options > Set Preferences, copies unconfirmed (the lower No), Return': (1236, 668, 254, 0),
    'folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return': (1472, 0, 254, 0),
    "files: View > Show as Text, the long file's line clicked": (1084, 0, 254, 486),
    'folder: Options > Set Preferences, deletes unconfirmed (the upper No), Return': (1236, 668, 254, 0),
    'folder: deletes unconfirmed — the file dragged to the trash': (1460, 0, 254, 0),
    'folder: deletes unconfirmed — the folder dragged to the trash': (1460, 0, 254, 0),
    "files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB)": (1460, 0, 254, 0),
    'file: dragged to the trash, OK — then drive A: selected, File > Show Info, Return': (1336, 668, 260, 0),
    "file: read-only — File > New Folder, 'A', Return, the file dragged onto it, Return": (1472, 668, 254, 0),
    'A: opened, drive A: dragged into its window, Return': (1424, 0, 260, 0),
    'A: opened, the trash dragged into its window, Return': (1232, 0, 260, 0),
    'drive A: dragged onto drive B:, Return': (1460, 0, 254, 0),
    'the trash dragged onto drive A:, Return': (1460, 0, 254, 0),
    "file: dragged onto drive A:'s icon, Return — the name conflict, Return": (1460, 0, 254, 0),
    "folder: File > New Folder again, 'A', Return — the name taken, Return": (1212, 668, 254, 0),
    'file: dragged to the trash, OK — then drive A: dragged into its window': (1288, 0, 260, 0),
    'files: the right arrow clicked, then the left arrow clicked': (1140, 404, 260, 0),
    "files: the window's sizer pulled up and left (smaller)": (1152, 650, 260, 0),
    'files: the right arrow clicked, then the horizontal bar left of its slider (a page)': (1140, 404, 260, 0),
    "files: the window's right arrow gadget itself clicked (a column)": (1140, 404, 260, 0),
    "files: the window's down arrow gadget itself clicked (a row)": (658, 404, 260, 0),
    "files: the window's up arrow gadget clicked (a row)": (658, 404, 260, 0),
    "files: the window's horizontal slider dragged right": (1176, 706, 260, 0),
    'window: Esc typed (the top window read again)': (1164, 0, 240, 0),
    'two windows: File > Close Window (one left on top)': (1448, 668, 254, 0),
    'files: the window sized smaller, then its right arrow clicked': (1140, 404, 260, 0),
    'files: the right arrow clicked, then the long file shown': (1372, 668, 254, 0),
    'files: View > Sort by Size, then the long file shown': (1372, 668, 254, 0),
    "files: View > Show as Text, then the long file's line shown": (1268, 668, 254, 486),
    "files: File > New Folder, 'A', Return (a fifth entry: a second row)": (1336, 668, 254, 0),
    'two windows: View > Show as Text': (1156, 750, 254, 486),
    'files: a fifth entry, then the down arrow gadget clicked (a row)': (658, 404, 260, 0),
    "text view: A: opened, the file's line dragged to the trash, Return (Cancel)": (1460, 0, 254, 486),
    'text view: drive A: dragged to a bare spot of the desktop': (1328, 0, 254, 0),
    "A: File > Format, the warning's OK (the FORMAT dialog)": (1248, 668, 254, 0),
    'A: File > Format, OK, EXIT clicked': (936, 308, 254, 0),
    'A: File > Format, OK, FORMAT clicked (formatted)': (958, 0, 254, 0),      # 880 before band 6 slice F4
    "A: formatted, the alert's OK, EXIT clicked": (936, 308, 254, 0),
    "drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)": (1460, 308, 254, 0),
    'drive A: onto drive B:, OK, then Return (EXIT, the default)': (936, 308, 240, 0),
    'file: File > Open, Print clicked (the printer not ready)': (1372, 308, 254, 0),
    'file: the printer not ready, Cancel': (1268, 308, 254, 0),
    'file: the printer not ready, Retry (not ready again)': (898, 0, 254, 0),  # 822 before band 6 slice F4
    'file: the printer not ready, five seconds, Retry (printed)': (1268, 308, 254, 0),
    'file: File > Open, five seconds, Print clicked (printed)': (1372, 308, 254, 0),
    'file: shown, a key at its end — the file clicked, File > Open, shown again': (1372, 668, 254, 0),
    'a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type)': (1460, 308, 254, 0),
    "c: opened (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE)": (1500, 0, 254, 0),
    'files: the long file shown, then the folder AUTO double-clicked in the restored window': (1468, 668, 254, 0),
    'files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window': (1484, 668, 254, 0),
    "Esc typed at the desk's idle (no window open)": (658, 0, 240, 0),
    'drives A: and B: boxed, drive A: dragged onto drive B:, Return': (1288, 0, 254, 0),
    "two windows: the lower one's title clicked (WM_TOPPED)": (1116, 366, 260, 0),      # band 6 W3a's prep
    "two windows: the top one's title dragged lower (WM_MOVED)": (1128, 650, 260, 0),   # band 6 W3a's prep
    'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)':
        (1460, 668, 254, 0),      # band 6 W3a's stage 2 (do_open, do_aopen C); 1,524 at stage 1, 1,534 at its diet (the ROM's 1,504)
    # ---- band 6 W3a stage 1's fix pass ----
    desk.FILLED_FOLDER_INFO: (1276, 668, 254, 0),                # the ROM's 1,350
    desk.TTP_INSTALLED_THEN_ASKED_AGAIN: (1336, 668, 254, 0),    # the ROM's 1,290
    # ---- end of W3a stage 1's fix pass ----
}
