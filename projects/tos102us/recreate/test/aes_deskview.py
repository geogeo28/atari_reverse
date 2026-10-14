"""THE DESK'S WINDOWS — THE VIEW AND ITS LAYOUT LEAVES — AT THEIR ARRIVALS: unit L's signatures (`src/desk/deskview.c`;
band 6 wave 1b, group G1). How a case is taken, run and held is the group's, in `aes_deskwin.py`.
"""
import aes
import aes_deskwin as w
import vdi

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
RECT = w.RECT

# ---- UNIT L's SIGNATURES: `{routine: (the C core's answer, its frame's arguments in push order)}` --------------------
SIGNATURES = {
    "AES_ROM_WIN_VIEW": (None, (WORD, WORD)),
    "AES_ROM_WIN_START": (None, ()),
    "AES_ROM_WIN_ALLOC": (aes.LONG_ANSWER, (WORD,)),
    "AES_ROM_WIN_FREE": (None, (LONG,)),
    "AES_ROM_WIN_FIND": (aes.LONG_ANSWER, (WORD,)),
    "AES_ROM_WIN_TOP": (None, (LONG,)),
    "AES_ROM_WIN_ONTOP": (aes.LONG_ANSWER, ()),
    "AES_ROM_WIN_CNT": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_WIN_ITH": (aes.LONG_ANSWER, (WORD,)),
    "AES_ROM_WIN_OCALC": (None, (LONG, WORD, WORD, LONG)),
    "AES_ROM_WIN_ICALC": (None, (LONG,)),
    "AES_ROM_WIN_BLDVIEW": (None, (LONG, *RECT)),
    "AES_ROM_WIN_SHWALL": (None, ()),
    "AES_ROM_WIN_ISEL": (aes.WORD_ANSWER, (LONG, WORD, WORD)),
    "AES_ROM_WIN_INAME": (aes.LONG_ANSWER, (WORD,)),
    "AES_ROM_WIN_SINFO": (None, (LONG,)),
    "AES_ROM_WIN_SNAME": (None, (LONG,)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_L = tuple(SIGNATURES)
# The routines whose run reaches the dispatcher through a binding of unit D's on every arm a case takes.
YIELDS_L = frozenset({"AES_ROM_WIN_START", "AES_ROM_WIN_ALLOC", "AES_ROM_WIN_FREE", "AES_ROM_WIN_TOP", "AES_ROM_WIN_BLDVIEW",
                      "AES_ROM_WIN_SHWALL", "AES_ROM_WIN_SINFO"})
# ...and those that trap through the DOS glue (pro_chdir's, where the window is no cartridge's).
TRAPS_L = frozenset({"AES_ROM_WIN_TOP", "AES_ROM_WIN_ONTOP"})
w.declare_trapping_rows(YIELDS_L & TRAPS_L)
