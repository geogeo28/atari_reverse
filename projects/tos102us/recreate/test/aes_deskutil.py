"""THE DESK'S UTILITIES — unit M (`src/desk/deskutil.c`; band 6 wave 2, group G2, ruling R-W2-1): the cartridge's
directory search `$fed522` / `$fed534` — their declared Alcyon frames and the unit's wave-2 list. The rest of the unit
is wave 4's."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG

# ---- band 6 wave 2, group G2 (unit M) ----
import aes_deskbind as _db
import layouts

UTIL = layouts.parse_constants((aes.INCLUDE / "desk" / "deskutil.h",), known=aes.CONSTANTS)
FPD = layouts.parse_constants((_db.GLOBALS_HEADER, aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)
# GROUP G2'S BAND of the AES's staged window (`$7ae80..$7b000`, the wave's G2 window): a laid cartridge chain.
BAND_OFFSET, BAND_BYTES = 0x2E80, 0x80
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_deskutil.py: group G2's laid cartridge chain")
# cart_sfirst's second word is the attribute word its caller hands as to dos_sfirst, read by nothing.
SIGNATURES_WAVE_2 = {
    "AES_ROM_CART_SFIRST": (aes.WORD_ANSWER, (LONG, WORD)),
    "AES_ROM_CART_SNEXT": (aes.WORD_ANSWER, ()),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_M_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# ---- end of group G2's wave-2 ----
