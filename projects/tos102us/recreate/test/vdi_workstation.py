"""What the WORKSTATION batteries share (`src/vdi/workstation.c`): init_wk's contract, the open call's intin, the
machine v_opnwk opens over, and the GEMDOS side the virtual workstations reach.

INIT_WK is an Alcyon call with no arguments (`vdi.declare_alcyon`, as text_init is): it reads the open call through
the Line-A pointers and fills the CURRENT record.

V_OPNWK OPENS OVER A STALE MACHINE. Everything it writes — the three device tables, the two RAM font headers, the
physical record, REQ_COL, the input modes, the mouse's hide count and position — is FILLed first, so a store the
reconstruction skipped reads as a byte no arm of it produces; LINEA_CUR_WORK is left naming the virtual record's
band, so an init_wk that ran over the wrong record writes somewhere the compare sees. It takes BIOS and XBIOS traps
(setres, init_timer_mouse), so it is staged the way `test/vdi_screen.py`'s trap-taking cases are; it does not poison
(`vdi.READS_A_POINTER_IT_WRITES`: it stores pointers it then follows — the ring's slot 1 text_init walks, the three
call pointers vq_color reads through — and poisoned, the ROM's run does not reach its `rts` within the oracle's
200,000 instructions, measured); and it READS THE PALETTE — vq_color's realized arm, once per colour — so every register it reads is
declared (`palette_io`), a word no two colours share.

THE VIRTUAL WORKSTATIONS REACH GEMDOS through the VDI's own door, gemdos_call, and every case of them is staged as
`test_vdi_helpers_gemdos.py` stages the door's: the ORACLE takes the real `trap #1` into the ROM's GEMDOS, the
CANDIDATE hands the same words to the reconstructed dispatcher bound to the reconstructed memory manager, and what
the ROM stores in the door's three documented windows is dropped (`vdi_helpers.GEMDOS_DOOR_WINDOWS`). A LIST OF
SEVERAL is never fabricated: it is BUILT, by real opens and closes chained one run into the next (`case.continued`),
so every record on it is a block GEMDOS handed out.

TIER 3 PRICES THEM OVER A STAGED `trap #1` instead (`through_staged_trap`): the ROM's GEMDOS in both columns would
pull every ratio towards 1, and its trap entry writes a return PC and the registers into spans that differ by nature.
The door's `.S` traps into `vdi_helpers`' recording handler on both sides, answering what the real GEMDOS answered,
and the one span left different — LINEA_RETSAV, where each build parks its own caller's return — is dropped from the
Tier 3 row alone: the differential here compares it, the host build parking the ROM's own return site.
"""
import struct
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import case
import gemdos
import gemdos_memory as mem
import vdi
import vdi_helpers
import vdi_mouse
import vdi_screen as screen
from case import merge_pokes

WORKSTATION_H = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "workstation.h",
                            known={**addrs.ADDRS, **vdi.CONSTANTS})

INIT_WK = "VDI_ROM_INIT_WK"
vdi.declare_alcyon(INIT_WK, None, (vdi.IMAGE_ARG,))
OPNWK, CLSWK, OPNVWK, CLSVWK = "VDI_ROM_V_OPNWK", "VDI_ROM_V_CLSWK", "VDI_ROM_V_OPNVWK", "VDI_ROM_V_CLSVWK"
for _name in (OPNWK, CLSWK, OPNVWK, CLSVWK):
    getattr(_lib, vdi.core_symbol(_name)).argtypes = [vdi.IMAGE_ARG]
    getattr(_lib, vdi.core_symbol(_name)).restype = None

# ---- the open call's intin: [0] the device (setres's), [1..10] the attributes init_wk takes ----------------------
INTIN_WORDS = WORKSTATION_H["VDI_OPEN_XFM_MODE"] + 1
# What GEM's desktop hands v_opnwk: the current resolution, and every attribute its first.
GEM_INTIN = (1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 2)
assert len(GEM_INTIN) == INTIN_WORDS


def open_intin(device=1, **attributes):
    """intin for an open: GEM's, with `attributes` by `vdi/workstation.h` name less `VDI_OPEN_` (LINE_TYPE=0)."""
    words = list(GEM_INTIN)
    words[0] = device
    for name, value in attributes.items():
        words[WORKSTATION_H["VDI_OPEN_" + name]] = value
    return tuple(words)


# The handle the first virtual workstation over the snapshot's list (the physical record alone) is given.
FIRST_VIRTUAL_HANDLE = vdi.VDI_PHYS_HANDLE + 1


# ---- the stale machine ---------------------------------------------------------------------------------------------
def stale_record(at):
    """Every byte of the 308-byte record at `at` FILLed."""
    return {at: bytes([vdi.FILL]) * vdi.WS_BYTES}


def stale_tables():
    """What v_opnwk rebuilds, FILLed: the three device tables, REQ_COL, the RAM font headers, the input modes, the
    mouse's hide count and position, the ring's slot 1 and the quarter circle's width."""
    return merge_pokes(
        vdi.linea_pokes(DEV_TAB=[vdi.STALE_WORD] * vdi.VDI_DEV_TAB_WORDS, INQ_TAB=[vdi.STALE_WORD] * vdi.VDI_INQ_TAB_WORDS,
                        SIZ_TAB=[vdi.STALE_WORD] * vdi.VDI_SIZ_TAB_WORDS, REQ_COL=[vdi.STALE_WORD] * vdi.VDI_REQ_COL_WORDS,
                        LOC_MODE=1, VAL_MODE=1, CHC_MODE=1, STR_MODE=1, M_HID_CT=5, GCURX=7, GCURY=9, LINE_CW=3),
        {vdi.FONT_RAM_8X8: bytes([vdi.FILL]) * vdi.FONT_HEADER_BYTES,
         vdi.FONT_RAM_8X16: bytes([vdi.FILL]) * vdi.FONT_HEADER_BYTES,
         vdi.LINEA_FONT_RING + vdi.LINEA_FONT_RING_BUILTIN * vdi.LONG_BYTES: struct.pack(">I", vdi.FILL_LONG)})


# ---- the palette v_opnwk reads back -------------------------------------------------------------------------------
PALETTE_REGISTERS = addrs.SHIFTER_PALETTE_ENTRIES


def palette_word(register):
    """A 3-bit level a gun, no two registers alike, every level of every gun reached across the sixteen."""
    return ((register * 3) & 7) << 8 | ((register * 5 + 2) & 7) << 4 | ((register * 7 + 5) & 7)


def palette_io():
    """Every palette register, declared as `palette_word` — both bytes of each (`test_vdi_color.py`'s rule)."""
    declared = {}
    for register in range(PALETTE_REGISTERS):
        at = addrs.SHIFTER_PALETTE + register * addrs.PALETTE_ENTRY_BYTES
        declared.update({at: palette_word(register) >> 8, at + 1: palette_word(register) & 0xFF})
    return declared


# ---- v_opnwk ------------------------------------------------------------------------------------------------------
CURSOR_DEPTH = 2


def opnwk_pokes(intin=GEM_INTIN, planes=None, pokes=None):
    """v_opnwk's call over the stale machine, with init_timer_mouse's world staged as `test_vdi_screen.py`'s
    open stages it (the screen and a cursor cell, the timer vectors, the VBL slot), and LINEA_PLANES `planes`
    where the case says what the console was set up for."""
    call = merge_pokes(vdi.function_pokes(OPNWK, intin),
                       {vdi.CONTRL_AT + vdi.CONTRL_HANDLE: vdi.pack_words(vdi.STALE_WORD)})    # the handle it answers
    machine = merge_pokes(
        screen.filled_screen(), screen.CELL, screen.cursor(CURSOR_DEPTH, screen.CURSOR_DRAWN | 1),
        vdi.linea_pokes(USER_TIM=vdi.FILL_LONG, NEXT_TIM=vdi.FILL_LONG, CUR_WORK=vdi.VIRTUAL_WORK_AT),
        {addrs.SYSVAR_ETV_TIMER: struct.pack(">I", screen.SNAPSHOT_NEXT_TIM),
         vdi_mouse.VBL_QUEUE: bytes([vdi.FILL]) * vdi.LONG_BYTES},
        stale_tables(), stale_record(vdi.VDI_PHYS_WORK), stale_record(vdi.VIRTUAL_WORK_AT),
        vdi.linea_pokes(PLANES=planes) if planes is not None else None)
    return screen.trap_pokes(merge_pokes(call, machine, pokes))


def opnwk_io(mode_byte):
    return {**screen.io_shifter(mode_byte), **palette_io()}


def run_opnwk(mode_byte, intin=GEM_INTIN, planes=None, pokes=None):
    staged = opnwk_pokes(intin, planes, pokes)
    return vdi.run_function(OPNWK, staged, io_seed=opnwk_io(mode_byte), **vdi.READS_A_POINTER_IT_WRITES)


# ---- the GEMDOS side: the door's own staging, and a run through it -------------------------------------------------
# The TPA block the snapshot's one free descriptor spans is where every Malloc here is answered from; its first
# records are declared as case fields, since the cases read them back.
TPA_AT = mem.SNAPSHOT_FREE_MD.start
TPA_RECORDS = 8
vdi.declare_case_field(TPA_AT, TPA_RECORDS * vdi.WS_BYTES, "the virtual workstations GEMDOS hands out from the TPA")


# NEITHER GEMDOS SIDE POISONS (`vdi.READS_A_POINTER_IT_WRITES`): the closes walk the WS_NEXT links and LINEA_CUR_WORK
# they rewrite, and poisoned, v_clswk's run (none open, and four) and v_clsvwk's over the staged trap do not reach
# their `rts` within the oracle's 200,000 instructions — measured. What stands in is staging: every record FILLed
# (`FRESH_TPA`), RETSAV stale.
UNPOISONED = vdi.READS_A_POINTER_IT_WRITES


def through_the_door(name, staged, handlers, **kwargs):
    """`addrs.<name>` over `staged`, the candidate's GEMDOS calls answered by `handlers` (`gemdos.bound_handlers`)."""
    core = getattr(_lib, vdi.core_symbol(name))
    with gemdos.bound_handlers(handlers):
        info = case.run(getattr(addrs, name), {"_pokes": staged}, gemdos.recording(lambda _lib_, buf: core(buf)),
                        width=case.NO_RESULT, **UNPOISONED, **kwargs)
    return vdi.Result(info, staged)


def through_gemdos(name, pokes, **seeds):
    """The workstation function `addrs.<name>` over `pokes`, its GEMDOS calls taken by the ROM's GEMDOS on one side
    and the reconstructed memory manager on the other (`test_vdi_helpers_gemdos.py`)."""
    return through_the_door(name, merge_pokes(pokes, vdi_helpers.RETSAV_STALE), vdi_helpers.GEMDOS_HANDLERS,
                            dropped_windows=vdi_helpers.GEMDOS_DOOR_WINDOWS, **seeds)


# ---- the STAGED side: the recording `trap #1` the Tier 3 rows are priced over ----------------------------------------
# The Tier 3 drop: the one span the two builds leave different over the staged trap, each parking its own return.
RETSAV_DROPPED = ((vdi.LINEA_RETSAV, vdi.LINEA_RETSAV + vdi.LONG_BYTES,
                   "LINEA_RETSAV: the GEMDOS door parks its own caller's return address, in the ROM or in our build"),)
GEMDOS_OK = 0                       # what GEMDOS answers an Mfree of a block it handed out


def through_staged_trap(name, pokes, answer):
    """`addrs.<name>` over `pokes`, every GEMDOS call it makes taken by the staged handler on the ROM's side and its
    host twin on ours — nothing dropped: RETSAV, the ledger of every call and D0's use are all compared."""
    return through_the_door(name, merge_pokes(pokes, vdi_helpers.staged_gemdos_trap_pokes(answer)),
                            vdi_helpers.staged_gemdos_handlers(answer))


def list_of(image):
    """The workstation list as `[(record, handle)]`, from the physical record on."""
    records, at = [], vdi.VDI_PHYS_WORK
    while at:
        records.append((at, vdi.workstation(image, "HANDLE", at)))
        assert len(records) <= TPA_RECORDS + 1, "the list does not end"
        at = vdi.workstation(image, "NEXT", at)
    return records


def handles(result):
    return [handle for _at, handle in list_of(result.final)]


def oracle_continued(name, pokes):
    """The machine the ORIGINAL leaves after `addrs.<name>` over `pokes`, in `case.continued`'s shape — from the
    oracle alone, for a REGISTERED row's staging: a battery is imported (by `bench/`'s scripts too) before any build
    a differential could run against, and each row is proved by the battery's own chain of differentials."""
    final, writes, _regs = emu.run(make_image(pokes), getattr(addrs, name), {})
    return case.continued_from(pokes, final, writes)
