"""What the inquiry batteries share (`test_vdi_inquire.py`, `test_vdi_inquire_text.py`): the colour
index a mapped pen answers as, and the staging of a case whose answers rewrite a Line-A pointer. The
ROM reads, the call by `addrs.h` name and the store-order overlap are `test/vdi.py`'s (`rom_word`, `function_pokes`, `intout_over`)."""
import vdi


def vdi_index_of_pen(pen):
    """REV_MAP_COL through a SIGN-EXTENDED pen doubled in 32 bits (`movea.w` / `adda.l a0,a0`)."""
    return vdi.rom_word(vdi.VDI_REV_MAP_COL + vdi.WORD_BYTES * vdi.signed_word(pen))


# NO ATTRIBUTION PASS where the answers rewrite a Line-A POINTER — the cases that show when the ROM loads
# one, by laying intout over it. That pass poisons every byte the ROM wrote, the pointer included, and
# both cores would then follow it to an address no image holds.
POINTERS_REWRITTEN = dict(poison=False)


# THE PTSOUT POINTER IS LOADED AFTER THE INTOUT STORES in every inquiry that answers both (`movea.l
# $29ae,a5` behind them), which intout laid over the Line-A pointers shows: one answer lands on
# LINEA_PTSOUT's high word, staged one step below the ptsout band — so the points land in the band only
# if the pointer is read after that store, and a case makes that answer the band's own high word.
POINTER_HIGH_WORD_STEP = 1 << 16
RELOADED_HIGH_WORD = vdi.PTSOUT_AT >> 16


def ptsout_reloaded(pokes, intout_word):
    """`pokes` with intout[`intout_word`] on LINEA_PTSOUT's high word, and that pointer staged a step low."""
    return vdi.merge_pokes(pokes, vdi.linea_pokes(INTOUT=vdi.LINEA_PTSOUT - intout_word * vdi.WORD_BYTES,
                                                  PTSOUT=vdi.PTSOUT_AT - POINTER_HIGH_WORD_STEP))
