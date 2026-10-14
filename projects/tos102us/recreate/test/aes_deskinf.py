"""AN INFO DIALOG'S FIELDS — unit F of band 6 wave 1b, group G4 (`src/desk/deskinf.c`, `test/test_desk_inf.py`):
inf_field and inf_dttmsz — their declared Alcyon frames and the unit's list. Neither yields: every case is a plain
differential."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
INF_FIELD, INF_DTTMSZ = "AES_ROM_DESK_INF_FIELD", "AES_ROM_DESK_INF_DTTMSZ"
SIGNATURES = {
    INF_FIELD: (None, (LONG, LONG, LONG, WORD, WORD)),
    INF_DTTMSZ: (None, (LONG, LONG, WORD, WORD, WORD, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_F = tuple(SIGNATURES)
# ---- band 6 wave 2, group G1 (unit F) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_F (and its count) stays as it is
INF_FOLDER = "AES_ROM_DESK_INF_FOLDER"
SIGNATURES_WAVE_2 = {INF_FOLDER: (aes.WORD_ANSWER, (LONG, WORD, WORD, LONG))}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_F_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# ---- end of group G1's wave-2 ----
