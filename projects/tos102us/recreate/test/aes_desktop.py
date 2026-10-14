"""UNIT K, THE DESK'S MAIN LOOP'S HELPERS, AT THEIR ARRIVALS — band 6 wave 1b, group G2 (`src/desk/desktop.c`,
`test_desk_top.py`). The group's arrivals and cases are `aes_deskapp`'s: every routine of this unit reaches the
dispatcher through unit D's bindings, so every case is a row that switches (`aes_deskapp.row_of`). HELD AT TIER 1,
NOTHING BOUND."""
import aes
import aes_event
import aes_gemdosif as gd
import vdi

LONG, WORD, IMAGE = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG

# ---- THE SIGNATURES: `{routine: (the C core's answer, its frame's arguments in push order)}` ---------------------------------
SIGNATURES = {
    "AES_ROM_I_FIND": (aes.LONG_ANSWER, (WORD, WORD, LONG, LONG)),
    "AES_ROM_MEN_LIST": (None, (LONG, LONG, WORD)),
    "AES_ROM_MEN_UPDATE": (None, (LONG,)),
    "AES_ROM_DO_VIEWMENU": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_CNX_PUT": (None, ()),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_K = tuple(SIGNATURES)
# men_update both SWITCHES (menu_ienable) and, where a window is on top, TRAPS (G1's win_ontop makes its drive and path
# current: Dsetdrv, Dsetpath through the glue): its C's child binds band 5's scripted trap's twins.
aes_event.declare_child_doors("AES_ROM_MEN_UPDATE", gd.CHILD_DOORS)
