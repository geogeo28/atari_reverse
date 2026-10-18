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
# ---- band 6 slice F2 (group G2) ---- FLIPPED but two at stage 2: i_find, held only because the groups flipped in
# parallel (its C callees app_afind and fpd_ofind flipped beside it) — FLIPPED at slice F2b —, and men_update, HELD at
# slice F2b by a measured reason (`linef_table.LINKED_AND_NOT_FLIPPED` says it): flipped, ctlmgr's two desk-turn rows are
# refused by the desk's live-frames vet, its C's dead bytes in the held evnt_multi binding's frame not the ROM's — the
# binding's unwritten locals, out of the compare once the binding flips (slice H2's pieces): it flips with it at F2c.
HELD_AT_F2 = ("AES_ROM_MEN_UPDATE",)
# ---- band 6 wave 2, group G3 (unit K) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_K (and its count) stays as it is
SIGNATURES_WAVE_2 = {
    "AES_ROM_HNDL_KBD": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_CNX_GET": (None, ()),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_K_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# ---- end of group G3's wave-2 ----
# men_update both SWITCHES (menu_ienable) and, where a window is on top, TRAPS (G1's win_ontop makes its drive and path
# current: Dsetdrv, Dsetpath through the glue): its C's child binds band 5's scripted trap's twins.
aes_event.declare_child_doors("AES_ROM_MEN_UPDATE", gd.CHILD_DOORS)
