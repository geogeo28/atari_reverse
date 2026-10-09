"""gemdosif's DRIVE CALLS (`src/aes/gemdosif.c`): dos_gdrv `$fe3c02`, dos_chdir `$fe3c0e`, dos_sdrv `$fe3c12` — three
more entries into the `$fe3c28` tail dos_free takes — and isdrive `$fe39a6`, built on two of them.

    dos_gdrv():       moveq #$19,d1 / bra $fe3c28      Dgetdrv
    dos_chdir(path):  moveq #$3b,d1 / bra $fe3c28      Dsetpath
    dos_sdrv(drive):  moveq #$0e,d1 / bra $fe3c28      Dsetdrv — which answers the DRIVE MAP
        $fe3c28:      its caller's return parked in AES_DOS_RETURN; the function word pushed over the caller's frame;
                      `__DOS` (its own return in AES_TRAP1_RETURN, the trap, DOS_AX = D0.w, DOS_ERR = D0 < 0)
    isdrive():        bsr dos_gdrv / move.w d0,-(sp) / bsr dos_sdrv / addq.w #2,sp — the drive map

THE THREE ENTRIES PARK THEIR CALLER'S RETURN ADDRESS, which no frame carries: their C takes it as a host argument
(dos_free's precedent) and they are verified, UNPRICED. isdrive's two sites are the glue's own — constants — so
its C is priced like any routine's.

EVERY CASE OVER THE RECORDING, SCRIPTED TRAP (`test/aes_gemdosif.py`): the whole ordered call list with each frame's
own bytes, both parked returns and the verdict. AND OVER REAL GEMDOS — the ROM's glue into the ROM's GEMDOS, our C
into the reconstructed dispatcher and leaves — where the machine's own answers are the claim: the drive map and
current drive of the captured machine, a path on the staged disk.

WHAT REACHES THEM TODAY: any process of the post-boot machine may call them (the desk's own code does: 21 Line-F
sites) — the snapshot's AES_DOS_RETURN still holds isdrive's second site from the boot's last call.
"""
import pytest

from harness import BASE_IMAGE, addrs, emu

import aes
import aes_gemdosif as gd
import aes_shell as shell
import case
import gemdos
import vdi
from case import merge_pokes
from opcodes import DROP_STACK_LONG

DOS_GDRV, DOS_CHDIR, DOS_SDRV, ISDRIVE = gd.DOS_GDRV, gd.DOS_CHDIR, gd.DOS_SDRV, gd.ISDRIVE
DGETDRV, DSETDRV, DSETPATH = gd.DGETDRV, gd.DSETDRV, gd.DSETPATH
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
# What an entry through $fe3c28 parks: the run's own sentinel entered directly, the word after the call word in the
# Line-F caller.
LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES
GEMDOS_OK = 0
EDRIVE, EPTHNF = -46, -34               # GEMDOS's "invalid drive" and "path not found"
A_MAP = 0x0000_0007                     # a drive map: A:, B: and C:
A_PATH = b"\\SUBDIR\0"
PATH = merge_pokes(shell.text(gd.PATH_AT, A_PATH[:-1], gd.PATH_BYTES))


def return_site(through_line_f):
    return LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL


def entry(name, arguments, answers, *, through_line_f=False, pokes=None):
    """One of the three entries over the scripted trap, handed the return site its ROM run parks."""
    return gd.run_scripted(name, arguments, answers, pokes, through_line_f=through_line_f,
                           host_arguments=(return_site(through_line_f),))


def verdict(result):
    return [result.field("AES", name) for name in gd.DOS_FIELDS]


# ---- the three entries: (the routine, its arguments, the call the ledger records) ------------------------------------
ENTRIES = {
    "dos_gdrv": (DOS_GDRV, (), gd.call(DGETDRV)),
    "dos_sdrv, drive C:": (DOS_SDRV, (2,), gd.call(DSETDRV, ("w", 2))),
    "dos_sdrv, a word with a high byte": (DOS_SDRV, (0x1202,), gd.call(DSETDRV, ("w", 0x1202))),
    "dos_chdir": (DOS_CHDIR, (gd.PATH_AT,), gd.call(DSETPATH, ("l", gd.PATH_AT))),
    "dos_chdir, a path with a top byte": (DOS_CHDIR, (gd.PATH_AT | aes.BUS_TAG,), gd.call(DSETPATH, ("l", gd.PATH_AT | aes.BUS_TAG))),
}
# (GEMDOS's answer, AES_DOS_ERR): the error is the LONG's sign, AES_DOS_AX its low word.
ANSWERS = {"done": (GEMDOS_OK, 0), "a drive map": (A_MAP, 0), "an error": (EPTHNF, 1),
           "a positive long whose word is negative": (0x0000_8000, 0), "the least long": (0x8000_0000, 1)}


@THROUGH
@pytest.mark.parametrize("answered", ANSWERS)
@pytest.mark.parametrize("which", ENTRIES)
def test_an_entry_parks_both_returns_traps_with_its_frame_alone_and_answers_the_trap(which, answered, through_line_f):
    """The caller's return in AES_DOS_RETURN, `__DOS`'s own in AES_TRAP1_RETURN; ONE trap, its function over the
    frame its caller pushed and nothing of the stack above it (Dgetdrv's: the function word alone); D0 the trap's
    whole longword; the verdict."""
    (name, arguments, recorded), (answer, failed) = ENTRIES[which], ANSWERS[answered]
    result = entry(name, arguments, [answer], through_line_f=through_line_f, pokes=PATH)
    assert gd.calls(result.final) == [recorded]
    assert gd.sites_parked_at(result.final) == [(return_site(through_line_f), addrs.AES_DOS_TRAP_RETURN)], "parked BEFORE the trap"
    assert result.long_answer() == answer & aes.LONG_MASK
    assert verdict(result) == [return_site(through_line_f), addrs.AES_DOS_TRAP_RETURN, failed, answer & aes.WORD_MASK]


def test_the_recording_handler_records_what_the_rom_s_glue_traps_with():
    """The handler under the ROM's own glue: what it records and answers is the handler's, not a claim about the C —
    Dgetdrv's entry is the function and zeros though the stack above it holds the run's sentinel."""
    final, _writes, regs = emu.run(vdi.make_image(gd.scripted_machine([5])), addrs.AES_ROM_DOS_GDRV, {})
    assert gd.calls(final) == [gd.call(DGETDRV)] and regs["d0"] == 5
    pokes = merge_pokes(gd.scripted_machine([A_MAP]), vdi.alcyon_frame(DOS_SDRV, 2))
    final, _writes, regs = emu.run(vdi.make_image(pokes), addrs.AES_ROM_DOS_SDRV, {})
    assert gd.calls(final) == [gd.call(DSETDRV, ("w", 2))] and regs["d0"] == A_MAP


# ---- isdrive -------------------------------------------------------------------------------------------------------------
# (what Dgetdrv answers, the drive WORD Dsetdrv is then handed)
CURRENT_DRIVES = {"A:": (0, 0), "C:": (2, 2), "a long whose word is C:": (0x1234_0002, 2),
                  "an error: its low word all the same": (EDRIVE, EDRIVE & aes.WORD_MASK)}


@THROUGH
@pytest.mark.parametrize("current", CURRENT_DRIVES)
def test_isdrive_sets_the_drive_dgetdrv_answers_and_answers_dsetdrv_s_map(current, through_line_f):
    """Two traps in order — Dgetdrv, then Dsetdrv over the LOW WORD of what it answered (`move.w d0,-(sp)`) — and D0
    Dsetdrv's whole longword. What is left parked is the SECOND call's: isdrive's own site after its `bsr dos_sdrv`
    and `__DOS`'s; the verdict Dsetdrv's (Dgetdrv's error is overwritten, never tested)."""
    answer, word = CURRENT_DRIVES[current]
    result = gd.run_scripted(ISDRIVE, (), [answer, A_MAP], through_line_f=through_line_f)
    assert gd.calls(result.final) == [gd.call(DGETDRV), gd.call(DSETDRV, ("w", word))]
    assert gd.sites_parked_at(result.final) == [(addrs.AES_ISDRIVE_GDRV_RETURN, addrs.AES_DOS_TRAP_RETURN),
                                                (addrs.AES_ISDRIVE_SDRV_RETURN, addrs.AES_DOS_TRAP_RETURN)], (
        "each call parks its own site: the ledger holds the first, which the second overwrites")
    assert result.long_answer() == A_MAP
    assert verdict(result) == [addrs.AES_ISDRIVE_SDRV_RETURN, addrs.AES_DOS_TRAP_RETURN, 0, A_MAP]


def test_isdrive_s_verdict_is_dsetdrv_s():
    result = gd.run_scripted(ISDRIVE, (), [0, EDRIVE])
    assert result.long_answer() == EDRIVE & aes.LONG_MASK
    assert verdict(result)[2:] == [1, EDRIVE & aes.WORD_MASK]


def test_isdrive_parks_its_first_site_before_its_second():
    """THE FIRST PARK, which the second overwrites: seen in the ledger's order alone — so the ROM's own run is
    stopped before isdrive's second `bsr`, where AES_DOS_RETURN holds the site after the first."""
    image = vdi.make_image(gd.scripted_machine([2, A_MAP]))
    final, _writes, _regs = emu.run(image, addrs.AES_ROM_ISDRIVE, {}, stop_pc=addrs.AES_ISDRIVE_GDRV_RETURN)
    assert case.long_in(final, aes.AES_DOS_RETURN) == addrs.AES_ISDRIVE_GDRV_RETURN
    assert addrs.AES_ISDRIVE_GDRV_RETURN < addrs.AES_ISDRIVE_SDRV_RETURN < addrs.AES_ROM_PGMLD


def test_the_snapshot_still_holds_isdrive_s_second_site():
    """THE ROM-RUN STATE: the boot's last call through $fe3c28 was isdrive's Dsetdrv — the capture's AES_DOS_RETURN
    is the site this battery's runs leave."""
    assert case.long_in(BASE_IMAGE, aes.AES_DOS_RETURN) == addrs.AES_ISDRIVE_SDRV_RETURN
    assert case.long_in(BASE_IMAGE, aes.AES_TRAP1_RETURN) == addrs.AES_DOS_TRAP_RETURN


# ---- REAL GEMDOS ----------------------------------------------------------------------------------------------------------
SNAPSHOT_MAP = case.long_in(BASE_IMAGE, addrs.SYSVAR_DRVBITS)
CURDRV_AT = gemdos.BASEPAGE + addrs.BASEPAGE_CURDRV


def test_isdrive_through_real_gemdos_answers_the_machine_s_drive_map():
    """The ROM's glue into the ROM's GEMDOS and BIOS (Dsetdrv answers Drvmap's longword), our C into the
    reconstructed leaves: the captured machine's own map, its current drive stored back as it was."""
    result = gd.run_real(ISDRIVE, ())
    assert result.long_answer() == SNAPSHOT_MAP
    assert result.final[CURDRV_AT] == BASE_IMAGE[CURDRV_AT]
    assert verdict(result) == [addrs.AES_ISDRIVE_SDRV_RETURN, addrs.AES_DOS_TRAP_RETURN, 0, SNAPSHOT_MAP & aes.WORD_MASK]


@pytest.mark.parametrize("drive", (0, 1, 2, 15), ids=("A:", "B:", "C:, which the machine has not", "P:"))
def test_dos_sdrv_through_real_gemdos_stores_any_drive_and_answers_the_map(drive):
    """Dsetdrv checks nothing: the byte is the process's current drive, and the map is answered whatever it is."""
    result = gd.run_real(DOS_SDRV, (drive,), host_arguments=(emu.SENTINEL,))
    assert (result.final[CURDRV_AT], result.long_answer()) == (drive, SNAPSHOT_MAP)


def test_dos_gdrv_through_real_gemdos_answers_the_current_drive():
    result = gd.run_real(DOS_GDRV, (), {CURDRV_AT: bytes([1])}, host_arguments=(emu.SENTINEL,))
    assert result.long_answer() == 1 and verdict(result)[2:] == [0, 1]


@pytest.mark.parametrize("path, answer", ((b"\\SUBDIR", GEMDOS_OK), (b"\\NOWHERE", EPTHNF)), ids=("a directory", "none"))
def test_dos_chdir_through_real_gemdos_walks_the_staged_disk(path, answer):
    """Dsetpath over the staged drive: the directory made current (GEMDOS's own records, compared whole), or
    EPTHNF — AES_DOS_ERR 1, AES_DOS_AX its word."""
    result = gd.run_real(DOS_CHDIR, (gd.PATH_AT,), shell.text(gd.PATH_AT, path, gd.PATH_BYTES),
                         host_arguments=(emu.SENTINEL,))
    assert result.long_answer() == answer & aes.LONG_MASK
    assert verdict(result)[2:] == [int(answer < 0), answer & aes.WORD_MASK]


# ---- the registry ----------------------------------------------------------------------------------------------------------
# isdrive's rows over the scripted trap (real GEMDOS cannot be priced: `aes_shell`). The three entries take the return
# site no frame carries — a host argument: each is registered VERIFIED AND UNPRICED at its own entry (swept with the
# registry, listed in the census `test_tier3.UNPRICED_AT_A_ROM_ENTRY`), and priced inside isdrive's and set_defdrv's.
HOST_ARGUMENT = "a host argument: its caller's return site"
gd.register_unpriced(f"Dgetdrv ({HOST_ARGUMENT})", DOS_GDRV, (), gd.scripted_machine([2]))
gd.register_unpriced(f"Dsetpath ({HOST_ARGUMENT})", DOS_CHDIR, (gd.PATH_AT,), gd.scripted_machine([GEMDOS_OK], PATH))
gd.register_unpriced(f"Dsetdrv ({HOST_ARGUMENT})", DOS_SDRV, (2,), gd.scripted_machine([A_MAP]))
gd.register_scripted("drive A:, a map of three drives", ISDRIVE, (), [0, A_MAP])
gd.register_scripted("Dsetdrv refuses", ISDRIVE, (), [2, EDRIVE])
