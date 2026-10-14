"""THE COPY ENGINE'S HELPERS — unit C of band 6 wave 1b, group G4 (`src/desk/deskdir.c`, `test/test_desk_dir.py`): the
dialogs' drawing, the path editors, the DOS verdict and the delete, the check that a folder is not copied into itself
— their declared Alcyon frames and the unit's list."""
from pathlib import Path

import aes
import layouts
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
PREFIX = "AES_ROM_DESK_"
HEADER = Path(__file__).resolve().parents[1] / "include" / "desk" / "deskdir.h"
CONSTANTS = layouts.parse_constants((HEADER.parent / "deskglobals.h", HEADER), known={**vdi.CONSTANTS, **aes.CONSTANTS})
# `{routine: (the core's answer, its frame in push order)}` — None where the core answers nothing
SIGNATURES = {
    PREFIX + "DRAW_DIAL": (None, (LONG,)),
    PREFIX + "DO_NAMECON": (None, ()),
    PREFIX + "HIDE_DIAL": (aes.WORD_ANSWER, (LONG,)),
    PREFIX + "SHOW_DIAL": (None, (LONG,)),
    PREFIX + "DRAW_FLD": (None, (LONG, WORD)),
    PREFIX + "ADD_PATH": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "SUB_PATH": (aes.LONG_ANSWER, (LONG,)),
    PREFIX + "ADD_FNAME": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "DEL_FNAME": (aes.LONG_ANSWER, (LONG,)),
    PREFIX + "GET_FNAME": (None, (LONG, LONG)),
    PREFIX + "D_ERRMSG": (aes.WORD_ANSWER, ()),
    PREFIX + "D_DOFDEL": (aes.WORD_ANSWER, (LONG,)),
    PREFIX + "PATH_PART": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "PAR_CHK": (aes.WORD_ANSWER, (LONG, LONG, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_C = tuple(SIGNATURES)
