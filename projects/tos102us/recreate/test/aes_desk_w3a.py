"""BAND 6 W3a, THE CYCLE — the desk's one strongly connected component (seventeen routines) and hndl_button, the band's
last routines but deskmain (W3b). HELD TARGET-ONLY on the bound machine, the user's R3: no host twin, no Tier 1 case.
This module is the cycle's one home before its C exists (the prep, `test_desk_w3a.py`):

  * THE EIGHTEEN, by the C file each goes to (the orchestrator's split): their DECLARED ALCYON FRAMES, read off the ROM's
    call sites and bodies (the W3a cut's `dis/`), declared TARGET-ONLY (`vdi.TARGET_ONLY`, ruling O1: the C is compiled
    for the target alone, so the host library has no core — one there is refused by name);
  * THE SPLIT, S2 (rulings U3 / O4): three flip stages, leaf-up — and THE ONE BACK-EDGE, inf_show -> hndl_msg, made
    THROUGH THE TABLE until hndl_msg flipped (`BACK_EDGES`, the desk door's kind) and RETIRED AT STAGE 3: since then
    inf_show's C calls hndl_msg's C, and no call is made through the table (`CALLS_THROUGH_THE_TABLE` is empty);
  * THE TARGET-ONLY ROW KIND (ruling U1 / O2): a priced row with NO COMPANION, held by Tier 3's own differential on the
    bound machine — both blobs — and by the our-shore campaign's invariants; its own census (`TARGET_ONLY_ROWS`, by
    name), never ROWS_THAT_SWITCH. A NAMED ROW MAY DECLARE A BUDGET (the user's ruling of 2026-10-24): F4's plain rule,
    its run its own (no Tier 1 case supplies the value) — held where it is registered (`aes.register`);
  * ...AND ITS SWITCHING KIND (the orchestrator's B2): a target-only row that switches, whose by-nature drops are
    vouched for by THE ROM RUN'S OWN WRITE LEDGER, not by a companion (`register_target_only_switching`).
"""
from collections import namedtuple

import aes
import aes_event
import case
import routines
import vdi
from harness import _lib, addrs, make_image

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG

# ---- THE EIGHTEEN, BY FILE: `{file: {routine: (the core's answer, its frame in push order)}}` ------------------------------
# Every answer a word but inf_finish's (its D0 an address computation's leftover, read by no caller: `$fde9cc`).
DESKTOP, DESKSUPP, DESKINF, DESKINS = "desk/desktop.c", "desk/desksupp.c", "desk/deskinf.c", "desk/deskins.c"
HNDL_MSG, HNDL_MENU, HNDL_BUTTON = "AES_ROM_HNDL_MSG", "AES_ROM_HNDL_MENU", "AES_ROM_HNDL_BUTTON"
DO_FILEMENU, DO_OPTNMENU, DO_DESKMENU = "AES_ROM_DO_FILEMENU", "AES_ROM_DO_OPTNMENU", "AES_ROM_DO_DESKMENU"
DO_OPEN, DO_AOPEN, DO_INFO = "AES_ROM_DO_OPEN", "AES_ROM_DO_AOPEN", "AES_ROM_DO_INFO"
INF_SHOW, INF_FINISH, INF_FILE = "AES_ROM_DESK_INF_SHOW", "AES_ROM_DESK_INF_FINISH", "AES_ROM_DESK_INF_FILE"
INF_FOLDER_DLG, INF_DISK, INF_PREF = "AES_ROM_DESK_INF_FOLDER_DLG", "AES_ROM_DESK_INF_DISK", "AES_ROM_DESK_INF_PREF"
OPN_APPL, INS_DISK, INS_APP = "AES_ROM_DESK_OPN_APPL", "AES_ROM_DESK_INS_DISK", "AES_ROM_DESK_INS_APP"
SIGNATURES_BY_FILE = {
    DESKTOP: {
        HNDL_MSG: (aes.WORD_ANSWER, ()),                                    # deskmain reads it: $fe29f0 move.w d0,d5
        HNDL_MENU: (aes.WORD_ANSWER, (WORD, WORD)),                         # msg[3..4] pushed as one long: $fe238e
        HNDL_BUTTON: (aes.WORD_ANSWER, (WORD, WORD, WORD, WORD, WORD)),     # deskmain reads it: $fe2a22 move.w d0,d5
        DO_FILEMENU: (aes.WORD_ANSWER, (WORD,)),
        DO_OPTNMENU: (aes.WORD_ANSWER, (WORD,)),
        DO_DESKMENU: (aes.WORD_ANSWER, (WORD,)),
    },
    DESKSUPP: {
        DO_OPEN: (aes.WORD_ANSWER, (WORD,)),
        DO_AOPEN: (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD, LONG, LONG)),  # do_open's call: $fe160e..$fe162c
        DO_INFO: (aes.WORD_ANSWER, (WORD,)),
    },
    DESKINF: {
        INF_SHOW: (aes.WORD_ANSWER, (LONG, WORD)),                          # 1, always: $fde9a4 moveq #1,d0
        INF_FINISH: (None, (LONG, WORD)),
        INF_FILE: (aes.WORD_ANSWER, (LONG, LONG)),
        INF_FOLDER_DLG: (aes.WORD_ANSWER, (LONG, LONG)),
        INF_DISK: (aes.WORD_ANSWER, (WORD,)),                               # its low byte read: $fdedf0.. move.b 9(a6)
        INF_PREF: (aes.WORD_ANSWER, ()),
        OPN_APPL: (aes.WORD_ANSWER, (LONG, LONG, LONG, LONG)),              # do_aopen's call: $fe12d2..$fe12e2
    },
    DESKINS: {
        INS_DISK: (aes.WORD_ANSWER, (LONG,)),
        INS_APP: (aes.WORD_ANSWER, (LONG, LONG)),
    },
}
SIGNATURES = {name: signature for file in SIGNATURES_BY_FILE.values() for name, signature in file.items()}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame), target_only=True)
W3A = tuple(SIGNATURES)
FILE_OF = {name: file for file, signatures in SIGNATURES_BY_FILE.items() for name in signatures}

# ---- BAND 6 W3b: deskmain `$fe272e`, the cycle's one ROM caller (the W3b cut; its prep) ----------------------------------
# DECLARED HERE, beside the routines it calls, TARGET-ONLY as they are (the orchestrator's O1, reading the user's R3 to
# cover W3b): `() -> word` — no argument (sh_main's bare call `$feb1dc`), its word read by sh_main (`$feb1de move.w
# d0,-6(a6)`). The kind's rows (`register_target_only`, `register_target_only_switching`) take it as a W3a routine's.
# Its entry stays THE ROM'S BY DECLARATION until its flip (`bench/linef_table.py`'s DECLARED_NOT_LINKED); its arrivals,
# return sites and the harness's reading of it are `aes_desk_w3b.py`'s.
DESKMAIN = "AES_ROM_DESKMAIN"
W3B_SIGNATURES = {DESKMAIN: (aes.WORD_ANSWER, ())}
for _name, (_restype, _frame) in W3B_SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame), target_only=True)
W3B = tuple(W3B_SIGNATURES)
TARGET_ONLY_ROUTINES = W3A + W3B        # the kind's routines: the cycle and hndl_button, and deskmain

# ---- THE SPLIT, S2: three flip stages, leaf-up (rulings U3 / O4) -------------------------------------------------------
# A routine flips once every C callee of it is flipped (F3's rule) — so the cycle flips leaf-up, each stage a DAG once
# its one back-edge is made through the table. THE STAGES ARE BY ROUTINE, NOT BY FILE (the orchestrator's B3): stage 1
# deskinf.c's seven and deskins.c's two; stage 2 desksupp.c's three, do_optnmenu and do_deskmenu; stage 3 hndl_msg,
# hndl_menu, do_filemenu and hndl_button — desktop.c's six span stages 2 and 3, written by sequential authors.
STAGES = {
    1: (INF_SHOW, INF_FINISH, INF_FILE, INF_FOLDER_DLG, INF_DISK, INF_PREF, OPN_APPL, INS_DISK, INS_APP),
    2: (DO_OPEN, DO_AOPEN, DO_INFO, DO_OPTNMENU, DO_DESKMENU),
    3: (HNDL_MSG, HNDL_MENU, DO_FILEMENU, HNDL_BUTTON),
}
STAGE_OF = {name: stage for stage, names in STAGES.items() for name in names}

# ---- THE ONE BACK-EDGE, DECLARED: a C -> ROM call through the table, the desk door's kind -------------------------------
# `{(caller, callee): (the ROM's own call word, its site in the caller's ROM body, the stage that retires it)}`: THE
# CYCLE'S BACK-EDGES as the split declared them. While its callee was the ROM's, the caller's C made the call by that
# word; RETIRED at its stage — the callee flipped, the call is the C's own (stage 3: inf_show's C calls `aes_hndl_msg`).
# The calls still made through the table are the back-edges whose stage is not yet flipped: none since stage 3. A call
# declared there whose callee is flipped is RED BY NAME (`test_desk_w3a.py`).
TableCall = namedtuple("TableCall", "word site retired_at")
BACK_EDGES = {(INF_SHOW, HNDL_MSG): TableCall(0xF558, 0xFDE99A, 3)}
FLIPPED_THROUGH_STAGE = 3               # band 6 W3a's stage 3: the cycle whole (stage 1 the F file's nine, stage 2 five)
CALLS_THROUGH_THE_TABLE = {edge: call for edge, call in BACK_EDGES.items() if call.retired_at > FLIPPED_THROUGH_STAGE}
OUTLIVED_ITS_STAGE = "a call declared through the table outlived its stage: its callee is flipped — make it the C's own call"


# ...AND WHAT A ROW WHOSE RUN MAKES ONE SPENDS IN THE AES's ROM (Tier 3's general guard, `bench/tier3.py`): the callee's
# own body — the ROM's instructions over the same machine, THE ROM'S OWN RUN's cycles there to the cycle — and the
# Line-F handler's RAM copy under the calls and returns that ROM code makes. DECLARED BY ROW, measured and pinned by the
# battery that registers it: `{registered row: ThroughTheTable(cycles in the callee's body, cycles in the handler's
# copy)}` (stage 1's and stage 2's rows over a window, until stage 3); a row absent here spends none — every row since
# stage 3, which retired the one call (`test_desk_w3a_stage1.py` holds it empty).
ThroughTheTable = namedtuple("ThroughTheTable", "body handler")
ROWS_THROUGH_THE_TABLE = {}


def back_edge_spans():
    """The ROM text each declared call through the table enters: its callee's body, `(entry, the next routine the AES
    map's inventory lists)`."""
    import aes_desk
    starts = aes_desk.inventoried()
    entries = sorted({getattr(addrs, callee) for _caller, callee in CALLS_THROUGH_THE_TABLE})
    return tuple((entry, min(start for start in starts if start > entry)) for entry in entries)


def calls_outliving_their_stage(flipped, calls=None):
    """The calls through the table (`calls`: CALLS_THROUGH_THE_TABLE by default) whose callee is FLIPPED (its ROM
    address in `flipped`), by name."""
    calls = CALLS_THROUGH_THE_TABLE if calls is None else calls
    return sorted(f"{caller} -> {callee}" for caller, callee in calls if getattr(addrs, callee) in flipped)


# ---- THE TARGET-ONLY ROW KIND (the user's R3; the orchestrator's U1, O1, O2) -----------------------------------------------
# `{registered name: TargetOnlyRow}`: THE KIND'S OWN CENSUS (not ROWS_THAT_SWITCH, not the named budgets' census).
TargetOnlyRow = namedtuple("TargetOnlyRow", "label name arguments machine answered budget")
TARGET_ONLY_ROWS = {}
OUTSIDE_W3A = "a target-only row of a routine outside W3a's and W3b's declared set"
A_TIER_1_OF_W3A = "a W3a routine with a Tier 1 of its own — a host core, or a row registered with a companion"
A_TARGET_ONLY_ROW_IN_SWITCHING_ROWS = "a target-only row in SWITCHING_ROWS, the register of the rows with a companion"
NOT_REGISTERED_COMPANION_FREE = "a target-only row registered with a companion, or not at all"
NOT_THE_KIND_S = "a companion-free row that is no target-only row of W3a's"
# A NAMED TARGET-ONLY ROW'S BUDGET (the user's ruling of 2026-10-24): the 2026-10-21 / 10-23 rule — NEEDED, FITTED (5 N
# <= B), NOT STALE (B <= 10 N), N the row's OWN run — refused by the row's name where it is registered (F4's
# `aes.vet_a_plain_row_s_budget` and `aes.refused_past_its_cap_by_name`, through `aes.register`); its value ONE NAMED
# CONSTANT of the row's battery, and the very object every run of the row's original reads (`case.row_cap`):
NOT_ITS_OWN_BUDGET = "a target-only row whose runs read another budget than the one its registration declared"


def host_twin_of(name):
    """THE HOST CORE of `name`, or None: what a Tier 1 case of it would run — none for a target-only routine."""
    return getattr(_lib, routines.core_symbol(name), None)


def tier_1_of(name, registered, companion_free):
    """What gives `name` a Tier 1 of its own: its host core, and every row of its core in `registered` (names) that is
    not companion-free — a row with a companion, a row that switches, a battery's plain case."""
    core = routines.core_symbol(name)
    rows = sorted(row for row in registered if row.split(",")[0] == core and row not in companion_free)
    return (["its host core"] if host_twin_of(name) is not None else []) + rows


def vet_a_target_only_row(name, row_name):
    """THE KIND'S REFUSALS, each by the row's name, BEFORE anything is registered: a routine outside W3a and W3b, one
    of theirs with a Tier 1 of its own."""
    assert name in TARGET_ONLY_ROUTINES, f"{row_name}: {OUTSIDE_W3A} ({name})"
    found = tier_1_of(name, registered_rows(), case.tier3_companion_free())
    assert not found, f"{row_name}: {A_TIER_1_OF_W3A}: {found}"


def register_target_only(label, name, arguments, machine, *, answered=True, budget=None):
    """ONE TARGET-ONLY ROW, registered: a PLAIN priced row of the W3a routine `name` over `machine` (an arrival's) with
    the frame of `arguments` — `aes.register`'s, COMPANION-FREE (its mask word dropped at Tier 3 with no companion:
    `case.Rows.register`'s) — and listed in the kind's census. `budget`: a NAMED ROW's, past the oracle's own cap
    (the user's ruling of 2026-10-24) — ONE NAMED CONSTANT of the battery, handed here as itself: `aes.register` holds
    it to the row's own run (unneeded, not fitted, stale; a run past its cap, undeclared or declared below it — each
    refused by the row's name) and records it where every run of the original reads it (`case.row_cap`). The row."""
    row_name = f"{routines.core_symbol(name)}, {label}"
    vet_a_target_only_row(name, row_name)
    row = aes.register(label, name, arguments, machine, answer_compared=answered, budget=budget, companion_free=True)
    TARGET_ONLY_ROWS[row_name] = TargetOnlyRow(label, name, tuple(arguments), machine, answered, budget)
    return row


# ---- ...AND ITS SWITCHING KIND (the orchestrator's B2): vouched for by THE ROM RUN'S OWN WRITE LEDGER ---------------------------
# A row that switches drops what differs between two builds by nature (the caller's saved context, the dispatcher's
# stack, ...); every other such row is made safe by its companion, the C through the host's scheduler with nothing
# dropped — which R3 removes. In its place, the precedent of F3 stage 2's ruling (a) / slice P7 (`test_aes_event.py`'s
# switching census: stores, not changes): EVERY BYTE OF EVERY DROP is one THE ROM'S RUN STORED, read off its replay's
# write ledger over the row's settled machine — AND either stored UNCHANGED (the machine already holds the value the run
# leaves: the settling staged it) or INSIDE THE WINDOW OF A BY-NATURE CLASS, BY ADDRESS (the orchestrator's ruling on
# review RW3aP's F1: never by its reason, never by the row's own hand). The windows are those THE SETTLING DERIVED off
# the ROM's run (`aes_switching._settled`: each class's window — the mask word, the caller's context, the dispatcher's
# stack and its brackets' words, a QPB's or a parked wait's parameter, a frame address handed to GEMDOS — the user's
# ruling of 2026-10-25, `aes_switching.frame_addresses_handed` —, the screen manager's, the desk's and another
# process's spans — cut to the bytes the run stored) and A DOOR'S PARK THE RUN STORES INTO (R9's kind, the orchestrator's
# ruling at W3a stage 2: `aes_switching.door_park_windows`, the park longword off the run's own write ledger), and what
# the row names by its own hand (its own spans, its declared X flag: `aes_switching.own_drops`) is none of them. A drop
# of neither is refused by the row's name before anything is registered; THE SWITCHING CENSUS binds every class to its
# window again, independently, off the ROM's scheduled run (`test_aes_event.py`, which reads this kind's register too).
# The rows land in `aes_event.TARGET_ONLY_SWITCHING_ROWS` (never `SWITCHING_ROWS`, whose rows each have a companion).
A_DROP_NO_STORE_VOUCHES_FOR = ("a drop of a target-only row that switches which the ROM's run does not store, or stores "
                               "changed outside every by-nature window the settling derived off that run")
NOT_ITS_VOUCHED_DROPS = "a target-only row that switches whose registered drops are not the ones its ROM run vouched for"


def by_nature_windows(row, held):
    """THE BY-NATURE WINDOWS of the settled row `row` (`held`: its `aes_switching.Registered`), as `(lo, hi, why)`: every
    drop its settling DERIVED off the ROM's run — all of `held.drops` but what the row names by its own hand
    (`aes_switching.own_drops`: its own spans and its declared X flag)."""
    import aes_switching
    own = aes_switching.own_drops(row)
    return tuple(drop for drop in held.drops if drop not in own)


def drops_unvouched(drops, staged, final, writes, windows):
    """The drops of `drops` (`(lo, hi, why)` each) the ROM's run does NOT vouch for — over the settled machine's image
    `staged`, the run's `final` memory and its write ledger `writes` (addresses): a byte outside the ledger, or a byte
    whose value the run changed in a drop that lies inside none of `windows` (`(lo, hi, why)` each, by address alone).
    Each as `"lo..hi: why"`, in order."""
    unvouched = []
    for lo, hi, why in drops:
        stored = all(at in writes for at in range(lo, hi))
        unchanged = all(staged[at] == final[at] for at in range(lo, hi))
        in_a_window = any(low <= lo and hi <= high for low, high, _why in windows)
        if not (stored and (unchanged or in_a_window)):
            unvouched.append(f"{lo:#x}..{hi:#x}: {why}")
    return unvouched


def vouched_for(row, held, ran=None):
    """THE VOUCH (above), of the row `row` as settled (`held`: its `aes_switching.Registered`): its drops' refusals. Its
    windows: the settling's (`by_nature_windows`), A DOOR'S PARK the run stores into (`aes_switching.door_park_windows`:
    R9's kind, the orchestrator's ruling at W3a stage 2 — the park longword only, read off this run's write ledger) and
    THE DESK'S G_USERDEF STACK where the run enters ub_trampoline (`aes_switching.userdef_stack_windows`: the user's
    ruling of 2026-10-26 — the block under the top the arrival machine holds, and the park, by address). `ran`: the ROM
    run's replay `(final, writes)` where the caller has made it."""
    import aes_switching
    final, writes = ran or aes_switching._replayed(row, held.pokes)[2:]
    staged = make_image(held.pokes)
    windows = (by_nature_windows(row, held) + aes_switching.door_park_windows(writes)
               + aes_switching.userdef_stack_windows(staged, writes))
    return drops_unvouched(held.drops, staged, final, writes, windows)


# THE TARGET-ONLY ROWS THAT SWITCH WHOSE ROM RUN ENTERS ub_trampoline (its write ledger stores the park, read where each
# is registered): the only rows the G_USERDEF stack's windows can admit a drop on — by name, held by the stage's battery.
ENTERS_THE_TRAMPOLINE = set()


def register_target_only_switching(row):
    """ONE TARGET-ONLY ROW THAT SWITCHES (`row`: an `aes_switching.SwitchingRow` of a W3a routine) registered: settled
    as every row that switches is (`aes_switching.held_of`: from the ROM's own runs, refused where its run dispatches
    nothing), its drops VOUCHED FOR by the ROM run's write ledger (`vouched_for`) — the kind's refusals and that one by
    the row's name, before anything is registered — priced COMPANION-FREE (`aes.ROWS`), held in
    `aes_event.TARGET_ONLY_SWITCHING_ROWS`. Its budget is the row's derivation budget (`SwitchingRow.budget`: the
    2026-10-21 rule, held by every derivation of it). The row."""
    import aes_switching
    row_name = aes_switching.row_name(row)
    vet_a_target_only_row(row.name, row_name)
    row, held = aes_switching.held_of(row)
    final, writes = aes_switching._replayed(row, held.pokes)[2:]
    unvouched = vouched_for(row, held, (final, writes))
    assert not unvouched, f"{row_name}: {A_DROP_NO_STORE_VOUCHES_FOR}: {unvouched}"
    if aes_switching.USERDEF_SP_PARK in writes:
        ENTERS_THE_TRAMPOLINE.add(row_name)
    aes_event.TARGET_ONLY_SWITCHING_ROWS[row_name] = held
    aes.ROWS.register(row_name, getattr(addrs, row.name), held.pokes, dropped=held.drops, delivered=held.switches,
                      answered=row.answered, companion_free=True)
    return row


def named_budgets():
    """`{row name: its declared budget}` of THE TARGET-ONLY ROWS THAT DECLARE ONE: a plain row's (`TargetOnlyRow.budget`)
    and a switching row's (its derivation budget)."""
    return {**{name: row.budget for name, row in TARGET_ONLY_ROWS.items() if row.budget is not None},
            **{name: held.row.budget for name, held in aes_event.TARGET_ONLY_SWITCHING_ROWS.items() if held.row.budget}}


def registered_rows():
    """Every row name the registries hold: each component's priced and unpriced rows, and the rows that switch."""
    return {*(row[0] for rows in case.ROW_REGISTRIES for row in (*rows.cases, *rows.unpriced)), *aes_event.SWITCHING_ROWS}


Registries = namedtuple("Registries", "target_only switching_target_only registered companion_free switching budgets dropped")
Registries.__doc__ = """What the kind's census reads: `target_only` (`{name: TargetOnlyRow}`), `switching_target_only`
(`{name: aes_switching.Registered}`), `registered` (every row name), `companion_free`, `switching` (the rows that switch,
`SWITCHING_ROWS`), `budgets` (`case.row_budgets`) and `dropped` (`case.tier3_dropped`)."""


def the_registries():
    """The `Registries` as this process holds them."""
    return Registries(TARGET_ONLY_ROWS, aes_event.TARGET_ONLY_SWITCHING_ROWS, registered_rows(), case.tier3_companion_free(),
                      set(aes_event.SWITCHING_ROWS), case.row_budgets(), case.tier3_dropped())


def census_refusals(registries):
    """THE KIND'S CENSUS over `registries` (a `Registries`) — as the refusals it reads, each by the row's or the
    routine's name: a target-only row (either kind) outside W3a's declared set, not registered companion-free, or in
    SWITCHING_ROWS; a plain one whose runs read another budget than its own; a switching one whose registered drops
    are not its vouched ones; a companion-free row of neither kind; a W3a routine with a Tier 1 of its own. Empty:
    the census holds."""
    r, refused = registries, []
    rows = {**{name: row.name for name, row in r.target_only.items()},
            **{name: held.row.name for name, held in r.switching_target_only.items()}}
    for name, routine in sorted(rows.items()):
        if routine not in TARGET_ONLY_ROUTINES:
            refused.append(f"{name}: {OUTSIDE_W3A} ({routine})")
        if name not in r.companion_free:
            refused.append(f"{name}: {NOT_REGISTERED_COMPANION_FREE}")
        if name in r.switching:
            refused.append(f"{name}: {A_TARGET_ONLY_ROW_IN_SWITCHING_ROWS}")
    for name, row in sorted(r.target_only.items()):
        if r.budgets.get(name) is not row.budget:
            refused.append(f"{name}: {NOT_ITS_OWN_BUDGET}")
    for name, held in sorted(r.switching_target_only.items()):
        if tuple(r.dropped.get(name, ())) != tuple(held.drops):
            refused.append(f"{name}: {NOT_ITS_VOUCHED_DROPS}")
    refused += [f"{name}: {NOT_THE_KIND_S}" for name in sorted(r.companion_free) if name not in rows]
    for routine in TARGET_ONLY_ROUTINES:
        found = tier_1_of(routine, r.registered, r.companion_free)
        if found:
            refused.append(f"{routine}: {A_TIER_1_OF_W3A}: {found}")
    return refused
