"""BAND 6 W3a, STAGE 3 — THE DESK'S THREE DISPATCHERS AND THE FILE MENU, IN C AND FLIPPED (`src/desk/desktop.c`'s four:
hndl_msg, hndl_menu, do_filemenu, hndl_button), HELD TARGET-ONLY (the user's R3: no host twin, no Tier 1 case) — THE
CYCLE WHOLE, AND ITS ONE BACK-EDGE RETIRED (inf_show's C calls hndl_msg's C: `aes_desk_w3a.BACK_EDGES`):

  * THE FLIP: each one's Line-F table entry its thunk, on both blobs (`aes_deskarrive.flipped`). Their ROM caller deskmain
    (W3b) enters hndl_msg and hndl_button through the table and reads their D0 word: the thunk hands back the C's answer.
  * THE ROWS: ONE PER ARRIVAL CLASS (the W3a cut's §2.2 key, re-measured over every chain: hndl_msg's message type,
    hndl_menu's title and item, do_filemenu's and hndl_button's first four frame words) — a row that switches over the
    ROM's own arrival machine, its waits ended by the hands its chain gave there, registered TARGET-ONLY
    (`aes_desk_w3a.register_target_only_switching`). A class's row stands at the first of its arrivals a row can hold;
    where that is not its first, the reason is said beside it (`REPRESENTED_BY`).
  * THE HANDS: stage 1's and stage 2's; THE CHAIN'S OWN HANDS after the arrival's step (`the_chain_s_hands`: a drag
    carried and let go, a dialog answered — each step's receptions read off the machine the step before left, one
    interrupt an idle); a rubber box's poll, which never idles, woken at its door calls (the chain's own point).
  * THE STAGINGS, each stage 1's or stage 2's, said in the row's name: GEMDOS REPLAYED (a window redrawn, rebuilt or
    closed reaches pro_chdir), the floppy beside it, GETREZ STAGED, Save Desktop's own recorder, the disk's Show Info's
    — and THE SAME REPLAY TOLD Dcreate's AND Fclose's OWN FRAMES, a handler of its own (`FRAMED`: the orchestrator's
    call on the recorder's bytes past a frame — a harness artifact, fixed by a precise recorder, no drop).
  * THE DESK'S G_USERDEF STACK on the text view's two rows (THE USER'S RULING of 2026-10-26, quoted at
    `aes_switching.USERDEF_STACK_WHY`): a window by address for a row whose ROM run enters ub_trampoline, its standing
    filler-byte pin and its crafted refusals below.
  * THE CLASSES NO ROW HOLDS, BY NAME (`REFUSED`, the standing rulings): Print Screen (stage 2's: its alert raised and
    not answered, its OK prints — R-H-2's ledger not authorized).
  * A NAMED ROW'S BUDGET: stage 2's ROW_INSNS and stage 1's DIALOG_ROW_INSNS, each on the rows whose own run it fits.
"""
import functools
import re
import struct
from collections import namedtuple

import pytest
from harness import addrs, bench_tier3, make_image

import abi
import aes
import aes_boot
import aes_desk
import aes_deskarrive as da
import aes_deskbind as db
import aes_deskfun as fun
import aes_desksupp as ds
import aes_desk_w3a as w3a
import aes_event
import aes_fslib as fsl
import aes_shell as sh
import aes_switch
import aes_switching
import case
import isr
import routines
import vdi
import test_desk_w3a_stage1 as stage_1
import test_desk_w3a_stage2 as stage_2
from test_aes_desk_ours import LAUNCHED

STAGE_3 = w3a.STAGES[3]
HNDL_MSG, HNDL_MENU, DO_FILEMENU, HNDL_BUTTON = w3a.HNDL_MSG, w3a.HNDL_MENU, w3a.DO_FILEMENU, w3a.HNDL_BUTTON

# ---- THE HANDS: stage 1's and 2's, and THE CHAIN'S OWN after the arrival's step ---------------------------------------------
RETURN_TYPED, CANCEL_CLICKED, IN_PLACE = stage_2.RETURN_TYPED, stage_2.CANCEL_CLICKED, stage_2.IN_PLACE


def _interrupts(receptions):
    """The interrupts a step's receptions stand for, in order: the mouse moved, the button pressed or let go, a key
    pressed (its break code the same key's); a click's ticks none."""
    found = []
    for each in receptions:
        if each[0] == aes_boot.MOUSE_TO:
            found.append(aes_event.move_to(each[1], each[2]))
        elif each == aes_desk.BUTTON_DOWN:
            found.append(aes_event.press)
        elif each == aes_desk.BUTTON_UP:
            found.append(aes_event.release)
        elif each[0] == aes_boot.IKBD_BYTES and len(each[1]) == 1:
            if not each[1][0] & aes_desk.KEY_RELEASED:
                found.append(aes_event.key(each[1][0]))
        elif each != aes_boot.CLICK_TICKS:
            raise AssertionError(f"a reception no interrupt stands for: {each!r}")
    return found


def the_chain_s_hands(first):
    """THE CHAIN'S OWN HANDS from its step `first` on: each step's receptions read off the machine the step before
    left — taken in at an idle each by the ROM's run in place (a staging's), one interrupt an idle by the row."""
    def receptions(chain):
        steps, walked = aes_desk.CHAINS[chain].steps, aes_desk.walked(chain)
        return tuple(tuple(steps[k].hand(aes_boot.Machine(walked.steps[k - 1].boot))) for k in range(first, len(steps)))

    def at_idle(chain):
        return dict(enumerate(interrupt for step in receptions(chain) for interrupt in _interrupts(step)))
    return fun.Wake(at_idle, receptions)


DRAGGED_ON = the_chain_s_hands(1)          # a drag pressed at the chain's first step: carried, let go, its dialog answered
ITEM_ANSWERED = the_chain_s_hands(3)       # a menu item chosen at the chain's third step: its dialog typed into and answered
WAKE_NAMED = {**stage_2.WAKE_NAMED, DRAGGED_ON: "the chain's own hands after the press",
              ITEM_ANSWERED: "the chain's own hands after the item"}
BOX_CARRIED = "the box carried and let go at its door calls"
BOX_CARRIED_AT, BOX_LET_GO_AT = 0, 2       # the door calls of the box's poll the hand lands at: carried at the first, let go at the third


def box_carried_and_let_go(chain):
    """A RUBBER BOX'S HAND, its chain's: the mouse carried to the chain's own point at the box's first door call, the
    button let go at its third (its poll never idles: `aes_desk.RUBBER_BOX_POLL`)."""
    steps, walked = aes_desk.CHAINS[chain].steps, aes_desk.walked(chain)
    ((_mouse_to, x, y),) = steps[1].hand(aes_boot.Machine(walked.steps[0].boot))
    return {BOX_CARRIED_AT: aes_event.move_to(x, y), BOX_LET_GO_AT: aes_event.release}


# ---- THE STAGINGS: stage 2's ------------------------------------------------------------------------------------------------
REPLAYED, GETREZ_STAGED, FLOPPY = stage_2.REPLAYED, stage_2.GETREZ_STAGED, stage_2.FLOPPY
DISK_FLOPPY, SCRIPTED = stage_2.DISK_FLOPPY, stage_2.SCRIPTED
PARKED = stage_2.PARKED

# ...AND GEMDOS REPLAYED WITH Dcreate's AND Fclose's OWN FRAMES TOLD (the orchestrator's call on stage 3's stop, S3CLS's
# option A): fslib's replay records six bytes of every call it does not tell, and past a shorter frame that is the
# caller's stack — the ROM's glue's return there, ours here (stage 2's Save Desktop met it). A HANDLER OF ITS OWN, fslib's
# tables, its own span (the shared one, `aes_desksupp.REPLAY_HANDLER_AT`, is left as it is: no row priced over it moves),
# telling the two functions these rows reach by THE SCRIPTED TRAP'S OWN FRAME SIZES (`aes_shell.FRAME_BYTES`: one source,
# pinned below) — registered as a recorder (`aes_shell.GEMDOS_LEDGERS`), so a frame address it records is read as every
# recorder's is.
DCREATE, FCLOSE = addrs.GEMDOS_DCREATE_FN, addrs.GEMDOS_FCLOSE_FN
FRAMES_TOLD = (DCREATE, FCLOSE)
FRAMED_ARGUMENT_BYTES = {**ds.REPLAY_ARGUMENT_BYTES, **{function: sh.FRAME_BYTES[function] for function in FRAMES_TOLD}}
FRAMED_HANDLER_OFFSET, FRAMED_HANDLER_BYTES = 0x3940, 0xC0      # between test_aes_grdrag.py's band and test_aes_fmdo.py's
FRAMED_HANDLER_AT = aes.SPAN.claim(aes.WINDOW_AT + FRAMED_HANDLER_OFFSET, FRAMED_HANDLER_BYTES,
                                   "test/test_desk_w3a_stage3.py: GEMDOS replayed, Dcreate's and Fclose's own frames told")
FRAMED_HANDLER = fsl.replay_handler(FRAMED_ARGUMENT_BYTES)
assert len(FRAMED_HANDLER) <= FRAMED_HANDLER_BYTES
sh.GEMDOS_LEDGERS.append(functools.partial(sh.GemdosLedger, FRAMED_HANDLER_AT, FRAMED_HANDLER, fsl.LEDGER,
                                           FRAMED_ARGUMENT_BYTES, fsl.RECORDED_ARGUMENT_BYTES, fsl.DTA_CELL_AT))
FRAMED = f"{REPLAYED}; Dcreate's and Fclose's own frames told"


def gemdos_replayed_framed(arrived, wake):
    """Stage 1's replay (the ROM's own run in place's script) through THE FRAME-TELLING HANDLER (above)."""
    return ds.replay_pokes(stage_1.replay_script(arrived, wake), FRAMED_HANDLER_AT, FRAMED_ARGUMENT_BYTES)


STAGINGS = {**stage_2.STAGINGS, FRAMED: gemdos_replayed_framed}

# ---- A NAMED ROW'S BUDGET: stage 2's and stage 1's constants, each on the rows whose own run it fits -------------------------
ROW_INSNS = stage_2.ROW_INSNS               # 3,700,000: its rows' own runs here 453,292 .. 692,107 (measured)
DIALOG_ROW_INSNS = stage_1.DIALOG_ROW_INSNS     # 3,000,000: its rows' own runs here 322,419 .. 357,383 (measured)

# ---- THE ARRIVAL CLASSES (the cut's key, re-measured over every chain: `scratchpad/b6/W3a/S3/classes.json`) -------------------
Class = namedtuple("Class", "name key chain wake staging budget box draws", defaults=(IN_PLACE, None, None, False, False))
CLASSES = (
    # hndl_msg, by message type (msg[0])
    Class(HNDL_MSG, 10, "Desk > Desktop Info, Return", RETURN_TYPED),
    Class(HNDL_MSG, 20, "A: File > Open", IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 21, aes_desk.LOWER_WINDOW_TOPPED, IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 22, "window: its closer clicked", IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 23, "window: its fuller clicked", IN_PLACE, REPLAYED, ROW_INSNS),
    Class(HNDL_MSG, 24, "files: the window's right arrow clicked", IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 25, "files: the window's horizontal slider dragged right", IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 26, "files: the window's down arrow clicked", IN_PLACE, REPLAYED),
    Class(HNDL_MSG, 27, "files: the window's sizer pulled up and left (smaller)", IN_PLACE, REPLAYED, DIALOG_ROW_INSNS),
    Class(HNDL_MSG, 28, aes_desk.TOP_WINDOW_MOVED, IN_PLACE, REPLAYED),
    # hndl_menu, by (title, item)
    Class(HNDL_MENU, (3, 9), "Desk > Desktop Info, Return", RETURN_TYPED),
    Class(HNDL_MENU, (6, 40), "Options > Set Preferences, Return", RETURN_TYPED, GETREZ_STAGED),
    Class(HNDL_MENU, (6, 41), "Options > Save Desktop, Return", RETURN_TYPED, SCRIPTED),
    Class(HNDL_MENU, (4, 19), "A: File > Show Info, Return", RETURN_TYPED, DISK_FLOPPY),
    Class(HNDL_MENU, (6, 37), "A: Options > Install Disk Drive, Return", RETURN_TYPED),
    Class(HNDL_MENU, (4, 18), "A: File > Open", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(HNDL_MENU, (4, 25), "A: File > Format, Return (the warning answered)", RETURN_TYPED),
    Class(HNDL_MENU, (5, 30), "window: View > Show as Text"),
    Class(HNDL_MENU, (5, 34), "window: View > Sort by Size"),
    Class(HNDL_MENU, (4, 23), "window: File > Close Window", IN_PLACE, REPLAYED),
    Class(HNDL_MENU, (4, 22), "folder: File > Close", IN_PLACE, FLOPPY, DIALOG_ROW_INSNS),
    Class(HNDL_MENU, (6, 38), "files: the program selected, Options > Install Application, Return", RETURN_TYPED, REPLAYED,
          ROW_INSNS),
    Class(HNDL_MENU, (5, 29), "window: View > Show as Icons (the view it has)"),
    Class(HNDL_MENU, (5, 33), "files: View > Sort by Date"),
    Class(HNDL_MENU, (5, 35), "files: View > Sort by Type"),
    Class(HNDL_MENU, (4, 21), "folder: File > New Folder, 'A', Return", ITEM_ANSWERED, FRAMED, ROW_INSNS),
    # do_filemenu, by its first four frame words (its item, then what its caller left: hndl_msg's, hndl_button's)
    Class(DO_FILEMENU, (0x13, 0, 0, 0), "A: File > Show Info, Return", RETURN_TYPED, DISK_FLOPPY),
    Class(DO_FILEMENU, (0x12, 0, 0, 0), "A: File > Open", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(DO_FILEMENU, (0x19, 0, 0, 0), "A: File > Format, Return (the warning answered)", RETURN_TYPED),
    Class(DO_FILEMENU, (0x12, 0xA2E6, 0, 0x13), "A: opened", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(DO_FILEMENU, (0x17, 0, 0, 0), "window: File > Close Window", IN_PLACE, REPLAYED),
    Class(DO_FILEMENU, (0x16, 0x20, 0, 0x13), "window: its closer clicked", IN_PLACE, REPLAYED),
    Class(DO_FILEMENU, (0x16, 0, 0, 0), "folder: File > Close", IN_PLACE, FLOPPY, DIALOG_ROW_INSNS),
    Class(DO_FILEMENU, (0x15, 0, 0, 0), "folder: File > New Folder, 'A', Return", ITEM_ANSWERED, FRAMED, ROW_INSNS),
    # hndl_button, by its first four frame words (clicks, x, y, button)
    Class(HNDL_BUTTON, (1, 0x24, 0x1B, 1), "drive A: selected"),
    Class(HNDL_BUTTON, (1, 0, 0x94, 1), "a rubber box on the desktop, round the trash", box=True),
    Class(HNDL_BUTTON, (2, 0x24, 0x1B, 1), "A: opened", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(HNDL_BUTTON, (2, 0x18, 0x1B, 1), "window: A: opened again (two windows)", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(HNDL_BUTTON, (1, 0x48, 0x3F, 1), "file: selected", IN_PLACE, REPLAYED),
    Class(HNDL_BUTTON, (2, 0x48, 0x3F, 1), "folder: opened", IN_PLACE, FLOPPY, ROW_INSNS),
    Class(HNDL_BUTTON, (1, 0xD8, 0x3F, 1), "files: the long file shown, a blank at each page's end and at its end", IN_PLACE,
          REPLAYED),
    Class(HNDL_BUTTON, (1, 0x100, 0x32, 1), "files: the program selected, File > Show Info, Return", IN_PLACE, REPLAYED),
    Class(HNDL_BUTTON, (2, 0x100, 0x32, 1), aes_desk.TTP_INSTALLED_THEN_CANCELLED, CANCEL_CLICKED, REPLAYED, ROW_INSNS),
    Class(HNDL_BUTTON, (1, 0, 0x37, 1), "a rubber box on the desktop, round drive B: and the trash", box=True),
    Class(HNDL_BUTTON, (1, 1, 0xC, 1), "drive A:'s object clicked at its corner, outside its image and its label"),
    Class(HNDL_BUTTON, (1, 0x18, 0x1B, 1), "file: dragged to the trash, OK — then drive A: selected, File > Show Info, Return",
          IN_PLACE, REPLAYED),
    Class(HNDL_BUTTON, (1, 0x24, 0xAA, 1), "A: opened, the trash dragged into its window, Return", DRAGGED_ON, REPLAYED),
    Class(HNDL_BUTTON, (2, 0x74, 0xAA, 1), aes_desk.CARTRIDGE_OPENED, IN_PLACE, None, ROW_INSNS),
    Class(HNDL_BUTTON, (1, 0x90, 0x3F, 1), "folder: the file dragged onto it, Return", DRAGGED_ON, FRAMED, ROW_INSNS),
    Class(HNDL_BUTTON, (1, 0xCD, 0x47, 1), "files: View > Show as Text, the long file's line clicked", IN_PLACE, REPLAYED,
          draws=True),
    Class(HNDL_BUTTON, (1, 0xCD, 0x33, 1), "text view: A: opened, the file's line dragged to the trash, Return (Cancel)",
          DRAGGED_ON, REPLAYED, ROW_INSNS, draws=True),
)
CLASSES_BY_ROUTINE = {HNDL_MSG: 10, HNDL_MENU: 16, DO_FILEMENU: 8, HNDL_BUTTON: 17}
# ...where a class's row stands at another of its arrivals than its first: `{(routine, the chain held): (the first's, why)}`
REPRESENTED_BY = {
    (HNDL_BUTTON, "folder: opened"): ("file: double-clicked (the alert)", "the first's chain ends with the alert up: no hand ends it"),
    (HNDL_BUTTON, aes_desk.TTP_INSTALLED_THEN_CANCELLED): (LAUNCHED, "the first is W6-R8's launch"),
}
DESKTOP_MESSAGE = 7668                      # the desk's message buffer in its block (DESK_G_RMSG): msg[0] its type
FRAME_KEY_WORDS = 4                         # the cut's key of a frame: its first four words


def key_of(name, arrived):
    """The class key of the arrival `arrived` at `name`, as the cut reads it."""
    ram, sp = arrived.boot.ram, db.stack_pointer(arrived.boot)
    if name == HNDL_MSG:
        return case.word_in(ram, (case.long_in(ram, aes.AES_DESK_GLOBALS) & db.BUS) + DESKTOP_MESSAGE)
    words = tuple(case.word_in(ram, sp + aes.LONG_BYTES + aes.WORD_BYTES * at) for at in range(FRAME_KEY_WORDS))
    return words[:2] if name == HNDL_MENU else words


ARRIVALS_SEARCHED = 12                      # the arrivals of a chain at a routine read for the class's first


def nth_of(each):
    """The ordinal of the class's first arrival on its chain (`aes_deskarrive.arrivals`)."""
    for arrived in da.arrivals(each.name, each.chain, ARRIVALS_SEARCHED):
        if key_of(each.name, arrived) == each.key:
            return arrived.nth
    raise AssertionError(f"{each.chain!r}: no arrival of {each.name} keyed {each.key}")


def label_of(each, nth):
    said = f"arrival {nth} of {each.chain!r}; {BOX_CARRIED if each.box else WAKE_NAMED[each.wake]}"
    return said + (f" [{each.staging}]" if each.staging else "")


def row_of(each):
    """The class's row that switches: the arrival's machine (its staging laid over it), its waits ended by its hands
    (a rubber box's at its door calls), its answer compared, AES_BIOS_RETURN its own where its run reaches the BIOS
    door — and, on a row that draws the text view (`Class.draws`), the G_USERDEF stack's spans its ROM run stores."""
    nth = nth_of(each)
    arrived = da.arrival(each.name, each.chain, nth)
    machine = da.row_machine_of(arrived)
    if each.staging:
        machine = case.merge_pokes(machine, STAGINGS[each.staging](arrived, each.wake))
    row = aes_switching.SwitchingRow(label_of(each, nth), each.name, arrived.arguments, lambda: machine,
                                     {} if each.box else each.wake.at_idle(each.chain),
                                     vdi.ALCYON[each.name].restype is not None,
                                     at_calls=box_carried_and_let_go(each.chain) if each.box else None,
                                     budget=each.budget, also_dropped=PARKED.get(each.staging, ()))
    return claiming_the_userdef_stack(row) if each.draws else row


def claiming_the_userdef_stack(row):
    """`row` NAMING THE DESK'S G_USERDEF STACK as its own (the user's ruling of 2026-10-26): the block's bytes and the
    park its ROM run stores (`aes_switching.userdef_stack_drops`, off the run's replay over the row's own machine) —
    held where it is registered by the vouch's window, by address (`aes_desk_w3a.vouched_for`)."""
    staged = aes_switching._staged(row)
    writes = aes_switching._replayed(row, staged)[3]
    return row._replace(also_dropped=row.also_dropped + aes_switching.userdef_stack_drops(make_image(staged), writes))


ROWS = {aes_switching.row_name(row): row for row in map(w3a.register_target_only_switching, map(row_of, CLASSES))}

# ---- THE CLASSES NO ROW HOLDS, by name: `{(routine, the class's key, its arrivals' chains): why}` -------------------------------
REFUSED = {(HNDL_MENU, (6, 42), (aes_desk.PRINT_SCREEN_S_ALERT,)): stage_2.PRINT_SCREEN}
MEASURED_CLASSES = {HNDL_MSG: 10, HNDL_MENU: 17, DO_FILEMENU: 8, HNDL_BUTTON: 17}


# ---- THE FLIP ----------------------------------------------------------------------------------------------------------------
def test_the_four_are_flipped(blob):
    """THE FLIP PIN of stage 3's four (`aes_deskarrive.flipped`: each core called by its own thunk, each entry ours)."""
    da.flipped(blob, STAGE_3)


# ---- THE ROWS -----------------------------------------------------------------------------------------------------------------
def test_every_arrival_class_held_is_a_target_only_row_of_its_routine():
    """ONE ROW PER CLASS HELD, each registered target-only and switching; with the refused class, the classes measured
    over every chain (hndl_msg 10 — the cut's 8 and the two the prep's chains reach, TOPPED and MOVED, with the
    slider's and the sizer's chains' —, hndl_menu 17, do_filemenu 8, hndl_button 17) every one."""
    held = [each.name for each in CLASSES]
    assert {name: held.count(name) for name in STAGE_3} == CLASSES_BY_ROUTINE
    assert len(ROWS) == len(CLASSES) and set(ROWS) <= set(aes_event.TARGET_ONLY_SWITCHING_ROWS)
    unheld = [*REFUSED]
    every = [name for name, _key, _chains in unheld] + held
    assert {name: every.count(name) for name in STAGE_3} == MEASURED_CLASSES
    assert len({(each.name, each.key) for each in CLASSES} | {(name, key) for name, key, _chains in unheld}) == len(every)


def test_each_row_stands_on_an_arrival_of_its_class():
    """The arrival each row stands on is its class's: the key the cut reads (the message type, the frame's words)."""
    for name, each in zip(ROWS, CLASSES):
        assert key_of(each.name, da.arrival(each.name, each.chain, nth_of(each))) == each.key, name


def test_a_class_s_row_stands_at_its_first_arrival_but_where_said():
    """A CLASS'S ROW AT ITS FIRST ARRIVAL OVER EVERY CHAIN (the walk's order) — but those `REPRESENTED_BY` says, each
    standing at an arrival after the one it names (that one first in the walk's order, of the same key)."""
    for each in CLASSES:
        first = _first_arrival_s_chain(each.name, each.key)
        said = REPRESENTED_BY.get((each.name, each.chain))
        assert first == (said[0] if said else each.chain), (each.name, each.key)


def _first_arrival_s_chain(name, key):
    for chain in aes_desk.CHAINS:
        for arrived in da.arrivals(name, chain, ARRIVALS_SEARCHED):
            if key_of(name, arrived) == key:
                return chain
    return None


def test_the_rows_that_declare_a_budget_read_the_named_constants():
    """THE BUDGET each declaring row's derivation reads is one of the two named constants (`is`); the rows that declare
    none run inside the default margin (held at registration by the same rule)."""
    declaring = {name: row.budget for name, row in ROWS.items() if row.budget is not None}
    assert declaring == {name: each.budget for name, each in zip(ROWS, CLASSES) if each.budget is not None}
    assert all(budget is ROW_INSNS or budget is DIALOG_ROW_INSNS for budget in declaring.values())
    assert len(declaring) == DECLARING


DECLARING = 17


# ---- hndl_button's store into its own argument slot (ruling O5: do_fopen's, fat_mark's class) --------------------------------
BUTTON_ARGUMENT = 3                         # the button word's place among hndl_button's arguments (clicks, x, y, button, keys)
BUTTON_DOWN_AT_THE_ARRIVAL, BUTTON_UP_AT_MKSTATE = 1, 0


def test_hndl_button_s_argument_slot_takes_graf_mkstate_s_answer_on_the_row_that_reads_the_button_up():
    """THE ARGUMENT SLOT ON A ROW (MEASURED): where the click was let go before the handler asks (`drive A: selected`).
    The row's run is entered on THE KIT'S BAND, its arguments copied from `abi.FIRST_ARG` on (the arrival's frame,
    deskmain's, is a dead copy neither shore touches): the ROM's run finds the button word there down (1) and stores
    graf_mkstate's answer, up (0), into that slot — its `14(a6)` — the store in its write ledger. Our C stores the same
    answer into ITS copy (one_click's `button`, a frame slot of our own) — both in the kit's stack band, which the image
    compare leaves out (`harness.diff_spans`): why neither store needs a window. A C that read the argument instead would
    press on into act_bdown's drag, which this row refuses (the stage's mutant)."""
    name = next(name for name, each in zip(ROWS, CLASSES) if each.name == HNDL_BUTTON and each.chain == "drive A: selected")
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
    slot = abi.FIRST_ARG + BUTTON_ARGUMENT * aes.WORD_BYTES
    staged = make_image(held.pokes)
    assert held.row.arguments[BUTTON_ARGUMENT] == case.word_in(staged, slot) == BUTTON_DOWN_AT_THE_ARRIVAL, "the premise"
    _reference, _watch, final, writes = aes_switching._replayed(held.row, held.pokes)
    assert all(at in writes for at in (slot, slot + 1)) and case.word_in(final, slot) == BUTTON_UP_AT_MKSTATE
    assert slot in case.STACK_BAND


# ---- THE CLASSES NO ROW HOLDS --------------------------------------------------------------------------------------------------
def test_the_print_screen_class_is_stage_2_s_standing_refusal():
    assert set(REFUSED.values()) == {stage_2.PRINT_SCREEN}
    assert not stage_2._entered_by(aes_desk.PRINT_SCREEN_S_ALERT, "AES_ROM_GSX_HARDCOPY")


# ---- THE FRAME-TELLING REPLAY (the orchestrator's call on the recorder's bytes past a frame) --------------------------------
def test_the_framed_handler_tells_the_scripted_trap_s_own_frame_sizes():
    """ONE SOURCE OF A FRAME'S SIZE: every function the frame-telling handler tells that the scripted trap knows is told
    `aes_shell.FRAME_BYTES`'s size — Dcreate's and Fclose's among them, which the shared replay does not tell (and is
    left not telling: its handler's bytes are the ones every row priced over it was measured with)."""
    known = {function: size for function, size in FRAMED_ARGUMENT_BYTES.items() if function in sh.FRAME_BYTES}
    assert known == {function: sh.FRAME_BYTES[function] for function in known}
    assert set(FRAMES_TOLD) <= set(known) and not set(FRAMES_TOLD) & set(ds.REPLAY_ARGUMENT_BYTES)
    assert FRAMED_ARGUMENT_BYTES == {**ds.REPLAY_ARGUMENT_BYTES, DCREATE: sh.FRAME_BYTES[DCREATE], FCLOSE: sh.FRAME_BYTES[FCLOSE]}


FRAMED_ROWS = 3                             # New Folder (hndl_menu, do_filemenu), the file dragged onto the folder


def test_a_framed_row_s_ledger_records_each_call_s_own_frame_and_nothing_past_it():
    """THE RECORDER'S FIX, ON EACH ROW OVER IT (measured): its ROM run's ledger holds the told functions' calls (the
    premise: the rows reach Dcreate or Fclose); no call is recorded deeper than its own frame (an untold one six bytes,
    which no frame the scripted trap knows is shorter than, of those these runs make), and every byte past what is
    recorded is the pad's zero — the caller's stack, which no C build reproduces, never recorded."""
    framed = [name for name, each in zip(ROWS, CLASSES) if each.staging == FRAMED]
    assert len(framed) == FRAMED_ROWS
    for name in framed:
        held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
        final = aes_switching._replayed(held.row, held.pokes)[2]
        calls = fsl.replay_calls(final)
        assert {call.function for call in calls} & set(FRAMES_TOLD), name
        for call in calls:
            recorded = FRAMED_ARGUMENT_BYTES.get(call.function, fsl.RECORDED_ARGUMENT_BYTES)
            assert recorded <= sh.FRAME_BYTES.get(call.function, recorded), (name, call.function)
            assert not any(call.frame[recorded:]), (name, call.function)


# ---- THE DESK'S G_USERDEF STACK (the user's ruling of 2026-10-26: `aes_switching.USERDEF_STACK_WHY`) -------------------------
TOP_CELL, PARK, BLOCK_BYTES = aes_switching.USERDEF_STACK_TOP_CELL, aes_switching.USERDEF_SP_PARK, aes_switching.USERDEF_STACK_BYTES
MOVE_L_SP_TO_ABSOLUTE, MOVEA_L_ABSOLUTE_TO_SP, ADDI_L_TO_ABSOLUTE = 0x23CF, 0x2E79, 0x06B9
# `{ROM site: the instruction's bytes}` the three constants are read off: ub_trampoline's park, its stack, its way back;
# desk_alloc's top kept (`addi.l #1024,$8c3a`)
THE_ROM_S_SITES = {
    0xFE3F42: struct.pack(">HI", MOVE_L_SP_TO_ABSOLUTE, PARK),
    0xFE3F48: struct.pack(">HI", MOVEA_L_ABSOLUTE_TO_SP, TOP_CELL),
    0xFE3F56: struct.pack(">HI", MOVEA_L_ABSOLUTE_TO_SP, PARK),
    0xFEE864: struct.pack(">HII", ADDI_L_TO_ABSOLUTE, BLOCK_BYTES, TOP_CELL),
}


def test_the_userdef_stack_s_cells_and_size_are_the_rom_s():
    """THE WINDOW'S THREE CONSTANTS, READ OFF THE ROM: the park and the top ub_trampoline ($fe3f3e) moves through, and
    the 1 KB desk_alloc ($fee80a) adds to the top it keeps."""
    from harness import BASE_IMAGE
    assert {at: bytes(BASE_IMAGE[at:at + len(code)]) for at, code in THE_ROM_S_SITES.items()} == THE_ROM_S_SITES


DRAWING = {name for name, each in zip(ROWS, CLASSES) if each.draws}


def test_exactly_the_text_view_s_two_rows_enter_the_trampoline_and_name_the_userdef_stack():
    """ONLY A RUN THROUGH THE DRAWING TRAMPOLINE: of every target-only row that switches (stages 1, 2 and 3), exactly the
    text view's two rows have a ROM run that stores the park (read where each is registered) — and they, and no other,
    drop a span of the G_USERDEF stack."""
    import test_desk_w3a_stage1  # noqa: F401  (every target-only row registered)
    import test_desk_w3a_stage2  # noqa: F401
    rows = aes_event.TARGET_ONLY_SWITCHING_ROWS
    assert len(DRAWING) == DRAWING_ROWS
    assert w3a.ENTERS_THE_TRAMPOLINE & set(rows) == DRAWING
    assert {name for name, held in rows.items() if aes_switching.names_the_userdef_stack(held.drops)} == DRAWING
    assert all(any(why == aes_switching.USERDEF_PARK_WHY for _lo, _hi, why in rows[name].drops) for name in DRAWING)


DRAWING_ROWS = 2


@pytest.mark.parametrize("blob", tuple(aes_switch.BLOBS))
def test_the_text_view_s_userblks_name_our_trampoline_as_our_run_is_entered(blob):
    """THE TRAMPOLINE MAPPED AT OUR RUN'S ENTRY (the orchestrator's call on the class-3 stop, option (a):
    `aes_event.USERBLK_TRAMPOLINE_SLOT.at_entry`). Each drawing row's machine — the ROM booted it — holds THE ROM'S
    ub_trampoline in `$8c32` and in every USERBLK the desk filled (the premise); entered as our run is
    (`tier3.as_our_run_is_entered`) on `blob`, every one holds the blob's own `aes_rom_ub_trampoline`. Un-mapped, our
    run executes the ROM's trampoline and $fde844 through the row's USERBLK (Tier 3's general guard: 1,510 cycles at
    the AES's ROM PCs)."""
    tier3, elf = bench_tier3(), isr.blob_named(blob).elf
    what = aes_event.USERBLK_TRAMPOLINE_SLOT.what
    (rom, ours), = tier3.stored_by_gem_entry_relocation(elf, what).items()
    for name in sorted(DRAWING):
        held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
        image = bytearray(make_image(held.pokes))
        slots = aes_event.slots_over(aes_event.USERBLK_TRAMPOLINE_SLOT, image)
        assert len(slots) > 1 and {case.long_in(image, slot) for slot in slots} == {rom}, f"{name}: the premise"
        tier3.as_our_run_is_entered(image, elf, routines.core_symbol(held.row.name))
        assert {case.long_in(image, slot) for slot in slots} == {ours}, name


FILLS = ((0xA5, 0x5A), (0x5A, 0xA5))         # the filler bytes laid `(over the block, over the park)`: two, each other's complement


def _the_finals_on(blob, row):
    """THE TWO IMAGES THE SECOND DIFFERENTIAL COMPARES of `row` on `blob` (`aes_switch.BLOBS`' key): `((the ROM's,
    ours), the differential's refusal or None)` — the images kept where the compare refuses them, so the pin below
    names the bytes a leftover moved before it reports the refusal."""
    caught = {}

    class Catching(bench_tier3().RomBench):
        def _vet_image(self, entry, symbol, original, ours, dropped=()):
            caught["finals"] = bytes(original), bytes(ours)
            return super()._vet_image(entry, symbol, original, ours, dropped)
    try:
        aes_switching.measured_on(Catching(aes_switch.BLOBS[blob]), row)
    except AssertionError as refused:
        if "finals" not in caught:
            raise
        return caught["finals"], refused
    return caught["finals"], None


def _filled(row, block_filler, park_filler):
    """`row` with the block laid with `block_filler` and the park with `park_filler` in its machine."""
    machine = row.machine()
    lo, top = aes_switching.userdef_stack_block(make_image(machine))
    filled = case.merge_pokes(machine, {lo: bytes([block_filler]) * (top - lo),
                                        PARK: bytes([park_filler]) * aes.LONG_BYTES})
    return row._replace(machine=lambda: filled)


@pytest.mark.parametrize("blob", tuple(aes_switch.BLOBS))
@pytest.mark.parametrize("name", sorted(DRAWING))
def test_nothing_reads_the_userdef_stack_s_leftovers(name, blob):
    """THE STANDING FILLER-BYTE PIN (the ruling's): the row run again over its machine with the block and the park laid
    with filler bytes, TWICE — $A5 over the block and $5A over the park, then each other's complement, so a read whose
    outcome is the same for the arrival's leftovers and for one filler still differs under the other — on BOTH SHORES
    (the ROM's run and ours) and on both blobs, every byte outside the block and the park is what the unfilled run
    leaves. So no build's run reads what the block or the park held before it: the exemption hides dead bytes only."""
    row = ROWS[name]
    lo, top = aes_switching.userdef_stack_block(make_image(row.machine()))
    plain, plain_refused = _the_finals_on(blob, row)

    def outside(at):
        return not (lo <= at < top or PARK <= at < PARK + aes.LONG_BYTES)
    refusals = [plain_refused]
    for block_filler, park_filler in FILLS:
        filled, filled_refused = _the_finals_on(blob, _filled(row, block_filler, park_filler))
        for shore, unfilled, laid in zip(("the ROM's", "ours"), plain, filled):
            assert any(laid[at] == block_filler for at in range(lo, top)), f"{shore}: the premise — the filler {block_filler:#x} laid"
            moved = [f"{at:#x}" for at in range(len(unfilled)) if unfilled[at] != laid[at] and outside(at)]
            assert not moved, f"{name} on {blob}, {shore} run, block filler {block_filler:#x}: the filler bytes moved {moved[:8]}"
        refusals.append(filled_refused)
    assert refusals == [None] * len(refusals), refusals


# ...ITS CRAFTED REFUSALS, each for its stated reason: over a crafted machine whose top is TOP, every byte stored and changed
TOP = 0x1D662                               # the top the arrival machines hold (desk_alloc's block, measured)
CRAFTED_TOP = TOP + 0x200                   # ...and one a crafted machine moves it to


def _crafted(top=TOP, park_stored=True):
    """`(staged image, final, writes)`: the top cell holding `top`, every byte from below the block to past the cells
    stored and changed — the park stored or not (the trampoline entered or not)."""
    size = max(top, TOP_CELL) + 2 * BLOCK_BYTES
    staged, final = bytearray(size), bytearray(size)
    struct.pack_into(">I", staged, TOP_CELL, top)
    final[:] = staged
    stored = set(range(top - 2 * BLOCK_BYTES, top + BLOCK_BYTES)) | set(range(PARK - 4, TOP_CELL + 8))
    if not park_stored:
        stored -= set(range(PARK, PARK + aes.LONG_BYTES))
    for at in stored:
        final[at] ^= 1
    return bytes(staged), bytes(final), frozenset(stored)


def _refused(drops, top=TOP, park_stored=True):
    staged, final, writes = _crafted(top, park_stored)
    return w3a.drops_unvouched(drops, staged, final, writes, aes_switching.userdef_stack_windows(staged, writes))


WHY = aes_switching.USERDEF_STACK_WHY
THE_BLOCK, THE_PARK = (TOP - BLOCK_BYTES, TOP, WHY), (PARK, PARK + aes.LONG_BYTES, aes_switching.USERDEF_PARK_WHY)


def test_the_block_and_the_park_are_admitted_where_the_run_stores_the_park():
    """The premise of every refusal below: the block and the park, exactly, are admitted over the crafted run."""
    assert _refused((THE_BLOCK, THE_PARK)) == []


def test_a_row_whose_run_never_enters_the_trampoline_claiming_the_stack_is_refused():
    """(1) A CASE OUTSIDE THE TEXT VIEW CLAIMING IT: the same spans, every byte stored and changed, over a run that never
    stores the park — refused (the trampoline not entered is the one difference from the premise above). And on a REAL
    row ('file: selected', whose ROM run draws no text line): its run stores no park, and the text view's claim refused."""
    assert _refused((THE_BLOCK, THE_PARK), park_stored=False) == [f"{lo:#x}..{hi:#x}: {why}" for lo, hi, why in (THE_BLOCK, THE_PARK)]
    selected = next(name for name, each in zip(ROWS, CLASSES) if each.chain == "file: selected")
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[selected]
    assert PARK not in aes_switching._replayed(held.row, held.pokes)[3], "the premise: its run never enters the trampoline"
    claimed = ROWS[sorted(DRAWING)[0]].also_dropped
    row = held.row._replace(also_dropped=held.row.also_dropped + claimed)
    refused = w3a.vouched_for(row, held._replace(row=row, drops=held.drops + claimed))
    assert refused == [f"{lo:#x}..{hi:#x}: {why}" for lo, hi, why in claimed]


A_BYTE_WIDER = {"a byte below the block": (TOP - BLOCK_BYTES - 1, TOP), "a byte past the block": (TOP - BLOCK_BYTES, TOP + 1)}


@pytest.mark.parametrize("what", A_BYTE_WIDER)
def test_the_block_one_byte_wider_is_refused(what):
    """(2) ONE BYTE TOO WIDE, either side, every byte stored and changed: refused."""
    lo, hi = A_BYTE_WIDER[what]
    assert _refused(((lo, hi, WHY),)) == [f"{lo:#x}..{hi:#x}: {WHY}"]


TRAMPOLINE_SLOT = aes.AES_USERDEF_TRAMPOLINE     # $8c32: ub_trampoline's code slot, just below the park (live)


def test_the_park_one_byte_wider_below_onto_the_trampoline_slot_is_refused():
    """(2) THE PARK'S LOWER EDGE: a byte below it is the low byte of the trampoline's code slot (`$8c35`, a live code
    pointer) — the park one byte too wide that way, every byte stored and changed: refused."""
    assert PARK - 1 == TRAMPOLINE_SLOT + aes.LONG_BYTES - 1, "the premise: the slot's last byte just below the park"
    lo, hi = PARK - 1, PARK + aes.LONG_BYTES
    assert _refused(((lo, hi, aes_switching.USERDEF_PARK_WHY),)) == [f"{lo:#x}..{hi:#x}: {aes_switching.USERDEF_PARK_WHY}"]


TOUCHING_THE_TOP_POINTER = {
    "the top pointer itself": (TOP_CELL, TOP_CELL + aes.LONG_BYTES),
    "the park a byte wider, onto it": (PARK, PARK + aes.LONG_BYTES + 1),
    "its last byte": (TOP_CELL + aes.LONG_BYTES - 1, TOP_CELL + aes.LONG_BYTES),
}


@pytest.mark.parametrize("what", TOUCHING_THE_TOP_POINTER)
def test_a_span_touching_the_top_pointer_is_refused(what):
    """(3) ANY SPAN TOUCHING $8c3a..$8c3d (the top pointer: live), every byte stored and changed: refused — and a top
    whose block would cover the pointer refused by name before any window is made."""
    lo, hi = TOUCHING_THE_TOP_POINTER[what]
    assert _refused(((lo, hi, aes_switching.USERDEF_PARK_WHY),)) == [f"{lo:#x}..{hi:#x}: {aes_switching.USERDEF_PARK_WHY}"]
    with pytest.raises(AssertionError, match=re.escape(aes_switching.USERDEF_TOP_COVERED)):
        _refused((THE_PARK,), top=TOP_CELL + aes.LONG_BYTES + 1)


def test_the_window_moves_with_the_top_the_machine_holds():
    """(4) READ OFF THE ARRIVAL MACHINE: a crafted machine whose top is moved moves the block — the block at the old
    address refused, the one under the new top admitted."""
    moved = (CRAFTED_TOP - BLOCK_BYTES, CRAFTED_TOP, WHY)
    assert _refused((THE_BLOCK, moved, THE_PARK), top=CRAFTED_TOP) == [f"{THE_BLOCK[0]:#x}..{THE_BLOCK[1]:#x}: {WHY}"]

# ...ITS CENSUS HALF lives beside the census (`test_aes_event.py`: a span just outside the windows, a drop of no kind)
