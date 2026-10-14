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
# ---- band 6 wave 2, group G2 (unit G) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_G (and its count) stays as it is
SIGNATURES_WAVE_2 = {
    "AES_ROM_PN_CLOSE": (None, (LONG,)),
    "AES_ROM_PN_ACTIVE": (aes.WORD_ANSWER, (LONG,)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_G_WAVE_2 = tuple(SIGNATURES_WAVE_2)

# GEMDOS REPLAYED AT AN ARRIVAL (pn_active's searches, and every routine of the group whose run reaches them): the C
# cannot take a `trap #1` (the host build has no GEMDOS of the floppy's), so both shores run over `aes_fslib`'s REPLAY —
# the trap vector at a 68000 handler that records each call and answers the next entry of a script, D0 and for a search
# the 44 bytes it leaves in the DTA; the host twin the same over the C's image. THE SCRIPT IS THE ROM'S OWN RUN IN PLACE
# (`gemdos_script`): the arrival continued on the desk's own stack, stopped where each of its traps returns in `__DOS`
# (`aes_deskleaves.GEM_DOS_BACK`), the D0 and the DTA there kept — up to the run's return to its caller.
REPLAYED = "GEMDOS REPLAYED: the ROM's run in place's answers and DTAs"


def gemdos_script(arrived):
    """THE SCRIPT of an arrival's routine (above): `((D0, the 44 bytes of the DTA or none), ...)` for each `trap #1` its
    ROM run in place takes before it returns — the run's own instruction count to the return is where the walk ends
    (a routine that idles first has none: refused by name)."""
    import aes_boot
    import aes_deskact as da
    import aes_deskbind as db
    import aes_deskleaves as dl
    import aes_fslib as fsl
    import case
    back = da.returned_in_place(arrived)
    assert back is not None, f"{da.label_of(arrived)}: the run idles before it returns — no script of its traps is walked"
    desk = case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & da.BUS
    boot, stands_at, ran, script = arrived.boot, da.entry_of(arrived.name), 0, []
    while True:
        try:
            trapped = aes_boot.continued(boot, (), arrived.budget, dl.GEM_DOS_BACK, stands_at)
        except aes_boot.Refused:
            break
        if ran + trapped.instructions > back.instructions:
            break
        boot, stands_at, ran = trapped, dl.GEM_DOS_BACK, ran + trapped.instructions
        function = case.word_in(boot.ram, da.stack_pointer(boot))
        dta = case.long_in(boot.ram, desk + db.DESK_GLOBALS["DESK_DTA_POINTER"]) & da.BUS
        searched = bytes(boot.ram[dta:dta + fsl.DTA_BYTES]) if function in fsl.SEARCHES else fsl.NO_DTA
        script.append((boot.registers["d0"], searched))
    return tuple(script)


def replay_laid(script_of=gemdos_script, what=REPLAYED):
    """A case's `laid`: the replay of its arrival's script (`script_of(arrival)`), `what` in its id."""
    def laid(arrived):
        import aes_fslib as fsl
        return fsl.replay_pokes(script_of(arrived))
    return (what, laid)


def replay_hook():
    """The C's side of the replay, `run_function`'s `hook`: `aes_fslib`'s twins bound to GEMDOS's handlers."""
    import aes_fslib as fsl
    return fsl.replay_doors()()

# ---- end of group G2's wave-2 ----
