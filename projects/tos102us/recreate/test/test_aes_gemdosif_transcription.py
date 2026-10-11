"""gemdosif's HAND 68000 as the target build ships it (`src/aes/gemdosif.S`): pgmld with the hop it reaches `__DOS`
by (`$fe39b4..$fe3a0b`), `__DOS` itself and THE VECTORS GEM TAKES — restore_trap2, install_trap2, retake, giveerr and
takeerr (`$fe3c3e..$fe3cbd`) — the ROM's own instructions; and, pinned in the same region, THE CRITICAL-ERROR HANDLER
and dos_exec (`$fe3cbe..$fe3db3`, crit_err's table `$fef790..$fef7a1`), whose behaviour is their own batteries'
(`test_aes_crit_err.py`, `test_aes_dos_exec.py`).

Their C (`src/aes/gemdosif.c`) is what every Tier 1 case proves (`test_aes_vectors.py`, `test_aes_pgmld.py`); it
measures over the 1.10 bar — restore_trap2 1.42, install_trap2 1.23, giveerr 1.13, retake 1.13 (1.68 on its own cycles), takeerr 1.04 with the
BIOS's Setexc in both columns (the image pointer's floor on two to six instructions), pgmld 1.11 on the arm where
Pexec fails — and none is a C function's shape (retake falls into the Setexc tail, giveerr branches into it, takeerr
calls it and branches into it; pgmld's command tail is a word of its own text and its two calls `bsr` a hop). So by
the user's rule the target carries the ROM's code. Two claims hold it: its BYTES are the ROM's, every one of the
three regions but ELEVEN LONGS RELOCATED (the hop's `jmp` to `__DOS`, where the `.S` lays it out; crit_err's address in
retake and takeerr; the six `jsr`s of spl7_save / spl_restore; crit_err's table and its `jsr` of eralert); and it
BEHAVES as the ROM — the image and the WHOLE REGISTER FILE — through Tier 3's transcription relation, over the C
battery's own machines. THE HANDLER retake AND takeerr INSTALL IS THE BUILD'S OWN: etv_critic and the recorder's
ledger hold `aes_rom_crit_err` on our shore — and D1, where the BIOS's Setexc leaves what it was handed — MAPPED
through Tier 3's relocation registry (`aes_event.CRITICAL_ERROR_HANDLER`) and compared exactly — no drop.

TWO SURFACES, as a vector take has two:
  * THE VECTORS' MEMORY, over the machine's own BIOS: both shores take the real `trap #13` into the ROM's Setexc (its
    register save in the stack band, where the trap's return PC — inside the `.S` on one shore, inside the ROM on the
    other — is not compared);
  * THE SETEXC LEDGER, over a recording `trap #13` (`aes_gemdosif.BIOS`: vector `$b4` pointed at a staged handler):
    every call's function, vector number and handler in order, and what the routine makes of the answer it is
    scripted — the order of takeerr's two calls, and that it asks before it installs.

pgmld's ONE: the recording, scripted `trap #1` (`test_aes_pgmld.py`'s machines) — and THE THREE ADDRESSES OF ITS OWN
TEXT IT LEAVES IN RAM (the two sites `__DOS` parks, the command tail's): the ROM's on one shore, the `.S`'s own on
the other, MAPPED through Tier 3's relocation registry (`aes_event.TEXT_SITES`) and compared exactly — no drop.

THE CALLER is the VDI binding's frame caller (`test_aes_gsx_transcription.entered`).
"""
import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_gemdosif as gd
import aes_event
import aes_switch
import case
import test_aes_gsx_transcription as frames
import test_aes_pgmld as battery_pgmld
import test_aes_vectors as battery
import transcription
from transcription import ABSOLUTE, Relocated
from case import merge_pokes
from opcodes import RTS

RESTORE_TRAP2, INSTALL_TRAP2, RETAKE, GIVEERR, TAKEERR = (
    battery.RESTORE_TRAP2, battery.INSTALL_TRAP2, battery.RETAKE, battery.GIVEERR, battery.TAKEERR)
CRIT_ERR, DOS_EXEC, CRIT_ERR_ALERTS = "AES_ROM_CRIT_ERR", "AES_ROM_DOS_EXEC", "AES_ROM_CRIT_ERR_ALERTS"
TAKEERR_BYTES = 18                      # $fe3cac..$fe3cbd, to its `bra.s` into the tail: crit_err begins behind it
DOS_TRAP = addrs.AES_ROM_GEM_DOS_TRAP                     # `__DOS`: the park, the trap, the verdict, `jmp (a0)` — $fe3c3e..$fe3c61
REGION_END = addrs.AES_ROM_LMUL         # dos_exec's `rts` is the word before the Alcyon runtime's multiply
REGION = transcription.pinned_region(DOS_TRAP, REGION_END, RESTORE_TRAP2,
                                     (INSTALL_TRAP2, RETAKE, GIVEERR, TAKEERR, CRIT_ERR, DOS_EXEC))
# crit_err's table: eighteen bytes of the ROM's data, which the `.S` lays behind its text.
ALERT_ROWS = aes.header_constants("gemdosif.h")["CRIT_ERR_ALERT_ROWS"]
TABLE_REGION = transcription.pinned_region(addrs.AES_ROM_CRIT_ERR_ALERTS, addrs.AES_ROM_CRIT_ERR_ALERTS + ALERT_ROWS,
                                           CRIT_ERR_ALERTS)
# pgmld's: the zero word, the hop, the routine, and the two return tails behind it ($fe3a04 `moveq #0 / rts`,
# dos_sfirst's and dos_open's miss, carried as bytes; $fe3a08 `moveq #1 / rts`, shared with dos_sfirst).
PGMLD = battery_pgmld.PGMLD
DOS_HOP, PGMLD_END = 0xFE39B6, addrs.AES_ROM_BELL
JMP_OPERAND = DOS_HOP + aes.WORD_BYTES
PGMLD_REGION = transcription.pinned_region(addrs.AES_PGMLD_EMPTY_TAIL, PGMLD_END, PGMLD)
OPERAND = aes.WORD_BYTES                # an absolute operand lies one word past its instruction
# The six `jsr`s of the mask brackets (`switch.S`'s entries, laid out from spl7_save), by the instruction's address.
SPL_BRACKETS = {0xFE3CC6: "crit_err masks round its change of stack", 0xFE3CD8: "...and lets the interrupts back in",
                0xFE3D2E: "dos_exec masks round the UDA's SP parked", 0xFE3D52: "...and back",
                0xFE3D78: "dos_exec masks round the UDA's SP put back", 0xFE3D90: "...and back"}
INSTALLS_CRIT_ERR = {0xFE3C8E: "retake", 0xFE3CB6: "takeerr"}     # `move.l #$fe3cbe,d0`: rows of `test_aes_rom_data.py`
LOADS_THE_TABLE, CALLS_ERALERT = 0xFE3CE2, 0xFE3D08
ERALERT_THUNK = "gemdosif_to_aes_eralert"
RELOCATED = {
    JMP_OPERAND: Relocated(ABSOLUTE, RESTORE_TRAP2, "the hop's `jmp` to `__DOS`, where the .S lays it out"),
    **{at + OPERAND: Relocated(ABSOLUTE, RESTORE_TRAP2, f"{routine} hands Setexc crit_err, where the .S lays it out")
       for at, routine in INSTALLS_CRIT_ERR.items()},
    **{at + OPERAND: Relocated(ABSOLUTE, "AES_ROM_SPL7_SAVE", why) for at, why in SPL_BRACKETS.items()},
    LOADS_THE_TABLE + OPERAND: Relocated(ABSOLUTE, CRIT_ERR_ALERTS, "crit_err's table, where the .S lays it out"),
    CALLS_ERALERT + OPERAND: Relocated(ABSOLUTE, None, "crit_err's alert: eralert ships as C", thunk=ERALERT_THUNK),
}
SETEXC, CRITIC_NUMBER = addrs.BIOS_SETEXC_FN, battery.SETEXC_CRITIC
JMP_ABSOLUTE_LONG = b"\x4e\xf9"
JSR_ABSOLUTE_LONG, MOVE_L_IMMEDIATE_D0, MOVEA_L_IMMEDIATE_A1 = 0x4EB9, 0x203C, 0x227C
# The build's symbol for each ROM address a relocated operand names.
SYMBOL_OF = {addrs.AES_ROM_SPL7_SAVE: "aes_rom_spl7_save", addrs.AES_ROM_SPL_RESTORE: "aes_rom_spl_restore",
             addrs.AES_ROM_CRIT_ERR: "aes_rom_crit_err", addrs.AES_ROM_CRIT_ERR_ALERTS: "aes_rom_crit_err_alerts"}
# The thunk's shape (`aes_switch.vet_a_thunk`): two words, the second pushed first, each sign-extended.
ERALERT_THUNK_SHAPE = ("movew %sp@(6),%d0", "extl %d0", "movel %d0,%sp@-", "movew %sp@(8),%d0", "extl %d0",
                       "movel %d0,%sp@-", "pea 0", "jsr {body}", "lea %sp@(12),%sp", "rts")


def test_the_transcription_is_the_rom_s_bytes_exactly():
    """THE BYTE PIN: every word the ROM's but the ten longwords that name where the build links a routine or a table
    of its own. The trap #2 handler install_trap2 and retake store is still the ROM's immediate (the door's flip
    moves it: `test_aes_rom_data.py` reds the day the build has an entry for it)."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_crit_err_s_table_is_the_rom_s_bytes_exactly():
    transcription.assert_transcribed(TABLE_REGION, relocated=RELOCATED)


def test_both_blobs_hold_the_region_with_each_operand_naming_its_own_routine(blob):
    """THE SHIPPED BLOB TOO, operand by operand (its absolute operands are its own layout's): every byte outside the
    ten the bench blob's, and each of the ten the address THAT blob links the routine, the table or the thunk at."""
    held = blob

    def laid(rom_address, size):
        return transcription.bytes_of(held, RESTORE_TRAP2, rom_address, size)
    operands = {at: relocation for at, relocation in RELOCATED.items() if REGION.lo <= at < REGION.hi}
    assert len(operands) == len(SPL_BRACKETS) + len(INSTALLS_CRIT_ERR) + 2
    at = REGION.lo
    while at < REGION.hi:
        if at not in operands:
            assert laid(at, aes.WORD_BYTES) == bytes(BASE_IMAGE[at:at + aes.WORD_BYTES]), f"${at:x}"
            at += aes.WORD_BYTES
            continue
        named = case.long_in(BASE_IMAGE, at)
        expected = held.entry(operands[at].thunk or SYMBOL_OF[named])
        assert int.from_bytes(laid(at, aes.LONG_BYTES), "big") == expected, f"${at:x} ({operands[at].why})"
        at += aes.LONG_BYTES
    table = held.entry(SYMBOL_OF[addrs.AES_ROM_CRIT_ERR_ALERTS]) - held.base
    assert bytes(held.blob[table:table + ALERT_ROWS]) == bytes(BASE_IMAGE[TABLE_REGION.lo:TABLE_REGION.hi])


def test_the_relocated_operands_are_the_instructions_the_rom_has_there():
    """Each site read off the ROM: a `jsr <abs>.l` of spl7_save or spl_restore, `move.l #crit_err,d0`,
    `movea.l #table,a1`, `jsr eralert` — so a relocation names the instruction it says it does."""
    def at_site(at):
        return case.word_in(BASE_IMAGE, at), case.long_in(BASE_IMAGE, at + OPERAND)
    assert {at_site(at) for at in SPL_BRACKETS} == {(JSR_ABSOLUTE_LONG, addrs.AES_ROM_SPL7_SAVE),
                                                    (JSR_ABSOLUTE_LONG, addrs.AES_ROM_SPL_RESTORE)}
    assert [at_site(at)[1] for at in sorted(SPL_BRACKETS)] == 3 * [addrs.AES_ROM_SPL7_SAVE, addrs.AES_ROM_SPL_RESTORE]
    assert {at_site(at) for at in INSTALLS_CRIT_ERR} == {(MOVE_L_IMMEDIATE_D0, addrs.AES_ROM_CRIT_ERR)}
    assert at_site(LOADS_THE_TABLE) == (MOVEA_L_IMMEDIATE_A1, addrs.AES_ROM_CRIT_ERR_ALERTS)
    assert at_site(CALLS_ERALERT) == (JSR_ABSOLUTE_LONG, addrs.AES_ROM_ERALERT)


def test_the_thunk_takes_eralert_s_two_words_into_the_c_call(blob):
    """WHAT THE PIN DOES NOT REACH: the thunk's own body, instruction for instruction — the drive then the alert, each
    word sign-extended into its slot, the image base, `aes_eralert`, the three slots dropped."""
    aes_switch.vet_a_thunk(blob, ERALERT_THUNK, ERALERT_THUNK_SHAPE, "aes_eralert")


def test_the_table_lies_behind_the_text_and_the_thunk_behind_the_table():
    """...and the file is laid end to end: dos_exec's `rts`, the eighteen bytes, the thunk — no instruction of no
    symbol between them (an `rts` after a `.size` passes every pin)."""
    blob = transcription.bench()
    assert blob.entry(SYMBOL_OF[addrs.AES_ROM_CRIT_ERR_ALERTS]) == transcription.transcribed_address(RESTORE_TRAP2, REGION_END)
    assert blob.entry(ERALERT_THUNK) == blob.entry(SYMBOL_OF[addrs.AES_ROM_CRIT_ERR_ALERTS]) + ALERT_ROWS
    aes_switch.vet_laid_end_to_end(blob, (ERALERT_THUNK,))


def test_pgmld_s_transcription_is_the_rom_s_bytes_but_the_hop_s_operand():
    """...and pgmld's region: every word the ROM's but ONE long — where the hop jumps."""
    transcription.assert_transcribed(PGMLD_REGION, relocated=RELOCATED)


def test_pgmld_s_region_is_the_tail_the_hop_the_routine_and_the_shared_returns():
    assert case.word_in(BASE_IMAGE, addrs.AES_PGMLD_EMPTY_TAIL) == 0 and DOS_HOP == addrs.AES_PGMLD_EMPTY_TAIL + aes.WORD_BYTES
    assert bytes(BASE_IMAGE[DOS_HOP:JMP_OPERAND]) == JMP_ABSOLUTE_LONG and case.long_in(BASE_IMAGE, JMP_OPERAND) == DOS_TRAP
    assert addrs.AES_ROM_PGMLD == JMP_OPERAND + aes.LONG_BYTES
    assert bytes(BASE_IMAGE[PGMLD_END - len(RTS):PGMLD_END]) == RTS
    # the two sites `__DOS` parks for it are the instructions after its two `bsr.s` of the hop
    for site in (addrs.AES_PGMLD_PEXEC_RETURN, addrs.AES_PGMLD_MSHRINK_RETURN):
        bsr, displacement = BASE_IMAGE[site - 2], BASE_IMAGE[site - 1]
        assert bsr == 0x61 and site + displacement - 0x100 == DOS_HOP


def test_the_region_is_dos_the_five_takes_crit_err_and_dos_exec_and_ends_on_dos_exec_s_rts():
    assert addrs.AES_ROM_TAKEERR + TAKEERR_BYTES == addrs.AES_ROM_CRIT_ERR, "takeerr's `bra.s`: crit_err begins behind it"
    assert bytes(BASE_IMAGE[addrs.AES_ROM_DOS_EXEC - len(RTS):addrs.AES_ROM_DOS_EXEC]) == RTS, "crit_err's own `rts`"
    assert bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS, "dos_exec's"
    assert bytes(BASE_IMAGE[addrs.AES_ROM_RESTORE_TRAP2 - len(RTS):addrs.AES_ROM_RESTORE_TRAP2]) != RTS, (
        "what precedes it is `__DOS`'s `jmp (a0)`: no routine falls into restore_trap2")
    assert bytes(BASE_IMAGE[addrs.AES_ROM_INSTALL_TRAP2 - len(RTS):addrs.AES_ROM_INSTALL_TRAP2]) == RTS
    assert bytes(BASE_IMAGE[addrs.AES_ROM_GIVEERR - len(RTS):addrs.AES_ROM_GIVEERR]) == RTS, "the shared tail's `rts`"


# ---- over the machine's own BIOS: the vectors' memory --------------------------------------------------------------------
STALE = battery.STALE
longs = battery.longs
OWN_BIOS = {
    (RESTORE_TRAP2, "GEM up: the BIOS's door put back"): battery.gem_up,
    (INSTALL_TRAP2, "the vectors given back"): lambda: merge_pokes(battery.given_back(), longs(vdi_door=STALE)),
    (INSTALL_TRAP2, "over a program's handler"): lambda: battery.a_program_s_own(longs(vdi_door=STALE)),
    (TAKEERR, "the vectors given back"): lambda: merge_pokes(battery.given_back(), longs(old_critic=STALE)),
    (TAKEERR, "GEM up already"): battery.gem_up,
    (GIVEERR, "GEM up: the BIOS's handler installed again"): battery.gem_up,
    (GIVEERR, "a saved longword with bit 31 set: nothing installed"):
        lambda: merge_pokes(battery.gem_up(), longs(old_critic=0x8000_0000 | battery.PROGRAM_S_CRITIC)),
    (RETAKE, "a program's own handlers in both vectors"): battery.a_program_s_own,
    (RETAKE, "the vectors given back"): battery.given_back,
}


def machine(pokes):
    return aes.leaf_machine(onto=pokes)


def held_on(blob, name, label):
    """The registered `.S` row `label` of `name` through Tier 3's transcription relation on `blob`: the image whole,
    the register file whole, the build's own crit_err MAPPED where a slot of the registry holds it — nothing dropped."""
    tier3 = bench_tier3()
    return tier3._measure_transcription(tier3.row_named((transcription.transcription_symbol(name), label)), blob)


def left_by_ours(blob, name, label):
    """What OUR run of that row leaves BEFORE anything is mapped back (the kit's own `_call`, past Tier 3's)."""
    row = bench_tier3().row_named((transcription.transcription_symbol(name), label))
    return rom_bench.RomBench._call(blob, make_image(row.pokes), row.symbol, args=(blob.entry(row.symbol),),
                                    entry_at=row.entry, seed_regs=[row.regs[each] for each in emu.REPORTED_REGS])


@pytest.mark.parametrize("name,shape", sorted(OWN_BIOS), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom_over_the_machine_s_own_bios(name, shape, blob):
    held_on(blob, name, shape)


# ---- THE HANDLER INSTALLED IS THE BUILD'S OWN, mapped and never dropped ---------------------------------------------------
INSTALLERS = sorted(key for key in OWN_BIOS if key[0] in (RETAKE, TAKEERR))


@pytest.mark.parametrize("name,shape", INSTALLERS, ids=lambda value: value)
def test_what_retake_and_takeerr_install_is_the_build_s_own_crit_err(name, shape, blob):
    """WHAT THE MAPPING STANDS ON, read off OUR run before it is mapped back: etv_critic holds the address THIS blob
    links crit_err at — where the ROM's run of the same row leaves `$fe3cbe` — so the mapping is not vacuous, and a
    critical error on a machine our takes ran on enters our handler."""
    ours = left_by_ours(blob, name, shape).image
    assert case.long_in(ours, aes_event.ETV_CRITIC) == blob.entry(SYMBOL_OF[addrs.AES_ROM_CRIT_ERR])
    the_rom_s, _writes, _regs = emu.run(make_image(machine(OWN_BIOS[(name, shape)]())), getattr(addrs, name), {})
    assert case.long_in(the_rom_s, aes_event.ETV_CRITIC) == addrs.AES_ROM_CRIT_ERR


def test_a_handler_left_unmapped_is_refused(blob, monkeypatch):
    """THE RED of the mapping: with crit_err's entry taken out of the registry the same row is refused at the first
    thing that holds it — D1, where the BIOS's Setexc left the handler it was handed (the register file is compared
    before the image, which holds it in etv_critic). The relation drops nothing."""
    tier3 = bench_tier3()
    monkeypatch.setattr(aes_event, "CRITICAL_ERROR_HANDLER", aes_event.CRITICAL_ERROR_HANDLER._replace(symbols={}))
    tier3.critical_error_handler_relocation.cache_clear()
    try:
        with pytest.raises(AssertionError, match=rf"register file than the original: d1 {addrs.AES_ROM_CRIT_ERR:#x} -> "):
            held_on(blob, TAKEERR, "the vectors given back")
    finally:
        tier3.critical_error_handler_relocation.cache_clear()


def test_a_build_that_installed_the_rom_s_crit_err_is_refused_by_name(blob, monkeypatch):
    """...AND THE OTHER WAY: a `.S` whose operand was left the ROM's would leave `$fe3cbe` in etv_critic — equal to the
    ROM's memory, so the compare alone would pass it. The registry's vet refuses it by name (the machine held the
    BIOS's handler there when the run was entered: our code stored the ROM's)."""
    made = rom_bench.RomBench._call

    def installing_the_rom_s(self, image, symbol, *args, **kwargs):
        ours = made(self, image, symbol, *args, **kwargs)
        ours.image[aes_event.ETV_CRITIC:aes_event.ETV_CRITIC + aes.LONG_BYTES] = addrs.AES_ROM_CRIT_ERR.to_bytes(aes.LONG_BYTES, "big")
        return ours
    monkeypatch.setattr(rom_bench.RomBench, "_call", installing_the_rom_s)
    with pytest.raises(AssertionError, match="THE ROM'S OWN address 0xfe3cbe in the critical-error handler GEM installs"):
        held_on(blob, TAKEERR, "the vectors given back")


# ---- over the recording trap: the Setexc ledger ---------------------------------------------------------------------------
PREVIOUS, DISPLACED = 0x0012_3450, 0x0065_4320      # what the scripted Setexc answers: handlers no machine holds
SETEXC_RECORDED = ", Setexc recorded"   # those rows' label, after the machine's


def setexc(handler):
    return gd.BIOS.call(SETEXC, ("w", CRITIC_NUMBER), ("l", handler))


# (the routine, the machine, the script's answers) -> the calls recorded, in order
RECORDED = {
    (RETAKE, "GEM up"): (battery.gem_up, [DISPLACED], [setexc(battery.CRIT_ERR)]),
    (GIVEERR, "GEM up"): (battery.gem_up, [DISPLACED], [setexc(battery.BIOS_CRITIC)]),
    (GIVEERR, "a staged saved handler"):
        (lambda: merge_pokes(battery.gem_up(), longs(old_critic=battery.PROGRAM_S_CRITIC | aes.BUS_TAG)), [DISPLACED],
         [setexc(battery.PROGRAM_S_CRITIC | aes.BUS_TAG)]),
    (TAKEERR, "GEM up"): (lambda: merge_pokes(battery.gem_up(), longs(old_critic=STALE)), [PREVIOUS, DISPLACED],
                          [setexc(0xFFFF_FFFF), setexc(battery.CRIT_ERR)]),
}


def recorded_machine(name, shape):
    pokes, answers, _calls = RECORDED[(name, shape)]
    return machine(merge_pokes(pokes(), gd.BIOS.pokes(answers)))


@pytest.mark.parametrize("name,shape", sorted(RECORDED), ids=lambda value: value)
def test_the_transcription_makes_the_rom_s_setexc_calls_in_order(name, shape, blob):
    """Both shores trap into the recording handler: the ledger — Setexc, vector number $101, the handler — and the
    script's pointers are compared image, the answers handed back register for register. And the ledger is WHAT THE
    ROUTINE'S NAME SAYS (read off the ORIGINAL's side of the measurement): takeerr asks ($ffffffff) BEFORE it
    installs, and keeps the first answer."""
    held_on(blob, name, f"{shape}{SETEXC_RECORDED}")
    _pokes, answers, calls = RECORDED[(name, shape)]
    image, _writes, regs = emu.run(make_image(recorded_machine(name, shape)), getattr(addrs, name), {})
    assert gd.BIOS.calls(image) == calls and regs["d0"] == answers[-1]
    if name == TAKEERR:
        assert case.long_in(image, aes.AES_OLD_CRITIC) == answers[0]
    # ...and OUR ledger, unmapped, holds this build's own crit_err wherever the ROM's holds `$fe3cbe`.
    ours = gd.BIOS.calls(left_by_ours(blob, name, f"{shape}{SETEXC_RECORDED}").image)
    crit_err = blob.entry(SYMBOL_OF[addrs.AES_ROM_CRIT_ERR])
    assert ours == [setexc(crit_err) if call == setexc(battery.CRIT_ERR) else call for call in calls]


# ---- Tier 3's rows ----------------------------------------------------------------------------------------------------------
for (_name, _shape), _pokes in sorted(OWN_BIOS.items()):
    frames.register(_shape, _name, (), machine(_pokes()))
for _name, _shape in sorted(RECORDED):
    frames.register(f"{_shape}{SETEXC_RECORDED}", _name, (), recorded_machine(_name, _shape))
