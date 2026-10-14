"""THE DESK'S PATH AND FILE NODES — unit G (`src/desk/deskfpd.c`, `test_desk_fpd.py`; band 6 wave 1b, group G3): the
signatures, over unit B's arrival layer (`aes_deskact`). None of the sixteen reaches the dispatcher: every case is
the kit's plain differential over an arrival's megabyte."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG

SIGNATURES = {
    "AES_ROM_FN_INIT": (None, ()),
    "AES_ROM_PN_INIT": (None, ()),
    "AES_ROM_FPD_START": (None, ()),
    "AES_ROM_FPD_BLDSPEC": (aes.WORD_ANSWER, (WORD, LONG, LONG, LONG, LONG)),
    "AES_ROM_FPD_PARSE": (None, (LONG, LONG, LONG, LONG, LONG)),
    "AES_ROM_FPD_OFIND": (aes.LONG_ANSWER, (LONG, WORD)),
    "AES_ROM_FPD_ELIST": (aes.LONG_ANSWER, (LONG, LONG)),
    "AES_ROM_FN_FREE": (None, (LONG,)),
    "AES_ROM_FL_FREE": (None, (LONG,)),
    "AES_ROM_FN_ALLOC": (aes.LONG_ANSWER, ()),
    "AES_ROM_PN_ALLOC": (aes.LONG_ANSWER, ()),
    "AES_ROM_PN_FREE": (None, (LONG,)),
    "AES_ROM_PN_OPEN": (aes.LONG_ANSWER, (WORD, LONG, LONG, LONG, WORD)),
    "AES_ROM_PN_FCOMP": (aes.WORD_ANSWER, (LONG, LONG, WORD)),
    "AES_ROM_PN_COMP": (aes.WORD_ANSWER, (LONG, LONG)),
    "AES_ROM_PN_SORT": (aes.LONG_ANSWER, (WORD, LONG)),
}
UNIT_G = tuple(SIGNATURES)
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
