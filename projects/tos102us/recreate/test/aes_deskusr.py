"""THE TEXT VIEW'S LINE AND ITS FORMATTERS — unit E of band 6 wave 1b, group G4 (`src/desk/deskusr.c`,
`test/test_desk_usr.py`): my_itoa, fmt_time, fmt_date and ob_sfcb — their declared Alcyon frames and the unit's list.
None yields: every case is a plain differential."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
MY_ITOA, FMT_TIME, FMT_DATE, OB_SFCB = "AES_ROM_DESK_MY_ITOA", "AES_ROM_DESK_FMT_TIME", "AES_ROM_DESK_FMT_DATE", "AES_ROM_DESK_OB_SFCB"
SIGNATURES = {
    MY_ITOA: (None, (WORD, LONG)),
    FMT_TIME: (aes.LONG_ANSWER, (WORD, LONG)),
    FMT_DATE: (None, (WORD, LONG)),
    OB_SFCB: (aes.LONG_ANSWER, (LONG, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_E = tuple(SIGNATURES)
