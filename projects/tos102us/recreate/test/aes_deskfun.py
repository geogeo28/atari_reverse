"""THE DESK'S ALERT AND ITS MESSAGE TO ITSELF — unit H of band 6 wave 1b, group G4 (`src/desk/deskfun.c`,
`test/test_desk_fun.py`): fun_alert `$fdfd58` and fun_msg `$fdfda6`, their declared Alcyon frames and the unit's list.
Both end on a binding of unit D: every case is a row that switches (`aes_deskarrive`)."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
FUN_ALERT, FUN_MSG = "AES_ROM_DESK_FUN_ALERT", "AES_ROM_DESK_FUN_MSG"
# `{routine: (the core's answer, its frame in push order)}`
SIGNATURES = {
    FUN_ALERT: (aes.WORD_ANSWER, (WORD, WORD, LONG)),
    FUN_MSG: (aes.WORD_ANSWER, (WORD,) * 7),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_H = tuple(SIGNATURES)
