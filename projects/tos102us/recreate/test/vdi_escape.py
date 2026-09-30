"""What the ESCAPE batteries share (`src/vdi/escape.c`): the call, the console it drives, and the stubs.

THE CALL is `vdi.function_pokes` for opcode 5 with contrl[5] the arm (`vdi/escape.h`, parsed here), over the
physical workstation dispatched — every arm reads its arrays through the Line-A pointers the dispatcher left.

THE CONSOLE is the BIOS's, staged the way its own battery stages it (`test/vt52.py`: the cursor's cell, the
flag byte and the lock depth — a PROGRAM's console, cursor unlocked and on screen, unless a case says the
captured desktop's), over `vdi_raster.CANVAS`: a pseudo-random screen, so every byte a clear, a glyph or a
cursor inversion writes differs from what was there and a store the candidate skipped is a plain diff.

THE ATTRIBUTION PASS IS OFF for every arm that drives the console, for `test_bios_vt52.py`'s reason: the bytes
those arms write ARE the console's control state — the cursor's screen ADDRESS and the state VECTOR at $4a8 — so
the poisoned run is a different routine, not this one over a different image. The canvas stands in for it. The
arms that only ANSWER (the three inquiries, the dispatch's empty arms) keep the pass.

V_HARDCOPY traps to XBIOS Scrdmp, which calls whatever `scr_dump` names: the ROM's own printer dump in the
captured machine, not reconstructed. So its cases stage a routine there, as the VBL's battery does for the same
call — one that REPORTS `_dumpflg` as it finds it and counts its calls (`isr.flag_recorder`), which is what pins
Scrdmp's call-then-flag order and its one call; the stub for the ORACLE, the same effect for the CANDIDATE through
`staged_call.h`'s hook (`isr.staged_routines`) — and declare `savptr` in the dropped band for the ROM's own trap
(`gemdos.machine`).
"""
import struct
from pathlib import Path

from harness import addrs

import gemdos
import isr
import routines
import vdi
import vdi_raster
import vt52
from case import merge_pokes

ESCAPE = "VDI_ROM_ESCAPE"
CORE = routines.core_symbol(ESCAPE)             # vdi_escape, the C twin Tier 1 proves
ESCAPE_H = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "escape.h",
                       known={**addrs.ADDRS, **vdi.CONSTANTS})
# Every `VDI_ESCAPE_<ARM>` is an arm but the `VDI_ESCAPE_ANSWER_*` constants — a rule of the header's, which
# `test_vdi_escape.py` holds to the ROM (the arms are the table's twenty numbers and its two compares, once each).
ARM_PREFIX, ANSWER_PREFIX = "VDI_ESCAPE_", "VDI_ESCAPE_ANSWER_"
ARMS = {name[len(ARM_PREFIX):]: value for name, value in ESCAPE_H.items()
        if name.startswith(ARM_PREFIX) and not name.startswith(ANSWER_PREFIX)}
CELLS_WORDS = ESCAPE_H[ANSWER_PREFIX + "CELLS_WORDS"]
TABLET_WORDS = ESCAPE_H[ANSWER_PREFIX + "TABLET_WORDS"]
TABLET = ESCAPE_H[ANSWER_PREFIX + "TABLET"]

# The escape's arms that ARE the console's escape bodies, by the letter ESC reaches the same address with.
CONSOLE_LETTERS = {"V_CURUP": "A", "V_CURDOWN": "B", "V_CURRIGHT": "C", "V_CURLEFT": "D", "V_CURHOME": "H",
                   "V_EEOS": "J", "V_EEOL": "K", "V_RVON": "p", "V_RVOFF": "q"}
# The console as the screen: the canvas, and the three things `vt52.staged` says about the cursor.
SCREEN = vdi_raster.CANVAS


def console(column=0, row=0, **kwargs):
    """`vt52.staged` over the pseudo-random canvas — a program's console by default."""
    return merge_pokes(SCREEN, vt52.staged(column, row, **kwargs))


def call(arm, intin=(), onto=None):
    """Escape `arm` (a name of `ARMS`, or a number) with `intin`, over `onto`."""
    subfunction = ARMS[arm] if isinstance(arm, str) else arm
    return merge_pokes(onto, vdi.function_pokes(ESCAPE, intin, subfunction=subfunction))


def run(pokes, **kwargs):
    """The escape over `pokes`. A console arm passes `poison=False` (this module's header says why)."""
    return vdi.run_function(ESCAPE, pokes, **kwargs)


def run_console(pokes, **kwargs):
    return run(pokes, poison=False, **kwargs)


# ---- v_hardcopy's routine -----------------------------------------------------------------------------------
BAND_OFFSET = 0x1D80
BAND_BYTES = 0x40
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_escape.py: the scr_dump routine and a decoy")
DUMP_STUB = BAND_AT
DECOY_STUB = BAND_AT + 0x20           # a routine `scr_dump` does NOT name, so a call of the wrong one shows
DUMP_REPORT = BAND_AT + 0x30          # _dumpflg as the dump routine found it, then its call count
DECOY_MARK = 1


def dump_routines():
    """The routine `scr_dump` names — it REPORTS `_dumpflg` as it finds it and counts its calls
    (`isr.flag_recorder`) — and a decoy beside it (`isr.marker_routine`)."""
    return {DUMP_STUB: isr.flag_recorder(addrs.SYSVAR_DUMPFLG, DUMP_REPORT), DECOY_STUB: isr.marker_routine(DECOY_MARK)}


def hardcopy_pokes(dumpflg=0):
    """v_hardcopy's machine: `scr_dump` at the staged routine, `_dumpflg` as the case says, savptr for the trap,
    and the routine's report stale with no call counted."""
    return merge_pokes(gemdos.machine(), isr.routine_pokes(dump_routines()),
                       {addrs.SYSVAR_SCR_DUMP: struct.pack(">I", DUMP_STUB),
                        addrs.SYSVAR_DUMPFLG: struct.pack(">H", dumpflg),
                        DUMP_REPORT: struct.pack(">HB", vdi.STALE_WORD, 0)},
                       call("V_HARDCOPY"))


def run_hardcopy(pokes, **kwargs):
    """The escape with the dump routines bound for the candidate; the oracle's trap needs no poison pass."""
    with isr.staged_routines(dump_routines()):
        return run(pokes, poison=False, recording=isr.recording, **kwargs)
