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
