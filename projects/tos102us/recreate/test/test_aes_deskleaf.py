"""THREE LEAVES OF THE DESK'S RANGE band 5's code calls (`src/aes/deskleaf.c`): app_reschange `$fdbae0`, set_defdrv
`$fdbecc` and the desk's rsrc_free binding `$fde33c`.

    app_reschange(device):  if (device == gl_restype) return 0;  gl_restype = device; gl_rschange = 1; return 1
    set_defdrv():           if (isdrive() & 4) { dos_sdrv(2); return 1; }  dos_sdrv(0); return 0
    desk_rsrc_free():       ret = rs_free(&desk's global[]);  dsptch();  return ret

WHAT REACHES EACH TODAY:
  * app_reschange — the desk's Set Preferences (`$fdf074`) calls it on the post-boot machine, which the snapshot IS;
    gem_main's read of DESKTOP.INF (`$fda53c`) calls it while GEM starts: OWED on the pre-init machine.
  * set_defdrv — the desk's own code (`$fdbe9c`, `$fe2a48`) on the post-boot machine; gem_main (`$fda246`): OWED on
    the pre-init machine. Over REAL GEMDOS the captured machine has A: and B: — the A: arm. The C: arm is reached
    by the scripted trap's answer and, on real GEMDOS, by AN ARGUMENT CLASS, labelled: `_drvbits` staged with a
    third drive (the machine has no hard disk; a boot with one would hold the bit).
  * desk_rsrc_free — LEAVES BY THE DISPATCHER (its yield): a row that switches, over a running desk
    (`aes_event.machine`) with GEMDOS scripted. Its callers are desk_free (`$fee88c`, `test_aes_deskmem.py`) and two
    of the shell's post-exit utilities (band 6).
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs
from recreate_kit import rom_bench

import aes
import aes_event
import aes_gemdosif as gd
import aes_resource as rs
import aes_switching as switching
import case
import gemdos
import vdi

APP_RESCHANGE, SET_DEFDRV, DESK_RSRC_FREE = "AES_ROM_APP_RESCHANGE", "AES_ROM_SET_DEFDRV", "AES_ROM_DESK_RSRC_FREE"
aes.declare_alcyon(APP_RESCHANGE, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG))
aes.declare_alcyon(SET_DEFDRV, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
aes.declare_alcyon(DESK_RSRC_FREE, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
LEAF = aes.header_constants("deskleaf.h")
GSXIF = aes.header_constants("gsxif.h")
RESTYPE, RSCHANGE = GSXIF["AES_GL_RESTYPE"], GSXIF["AES_GL_RSCHANGE"]
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
DGETDRV, DSETDRV, MFREE = gd.DGETDRV, gd.DSETDRV, gd.MFREE
SHELL = aes.SHELL_PD
Premise, Priced = switching.Premise, switching.Priced
BENCH, SHIPPED = "bench", "bench_shipped"

# ---- app_reschange ---------------------------------------------------------------------------------------------------
SNAPSHOT_DEVICE = case.word_in(BASE_IMAGE, RESTYPE)     # the device in use: 2 (640 x 200)
NO_CHANGE_ASKED = aes.field_pokes("AES", GL_RSCHANGE=0)


def reschange(device, pokes=None, **kwargs):
    return aes.run_function(APP_RESCHANGE, (device,), aes.leaf_machine(onto=pokes or NO_CHANGE_ASKED), **kwargs)


@THROUGH
def test_the_device_in_use_changes_nothing_and_answers_0(through_line_f):
    result = reschange(SNAPSHOT_DEVICE, through_line_f=through_line_f)
    assert (result.answer(), result.word(RESTYPE), result.word(RSCHANGE)) == (0, SNAPSHOT_DEVICE, 0)
    assert aes.stored_nothing(result)


@THROUGH
@pytest.mark.parametrize("device", (1, 3, 4, 0, -1, 0x0102), ids=lambda value: f"device {value}")
def test_another_device_is_kept_and_the_change_flagged(device, through_line_f):
    assert device & aes.WORD_MASK != SNAPSHOT_DEVICE
    result = reschange(device, through_line_f=through_line_f)
    assert (result.answer(), result.word(RESTYPE), result.word(RSCHANGE)) == (1, device & aes.WORD_MASK, 1)


def test_a_change_already_asked_for_is_left_asked_when_the_device_comes_back():
    """The flag is only ever SET: asked back to the device in use (after a change was flagged), nothing is stored
    and the flag stays."""
    result = reschange(SNAPSHOT_DEVICE, aes.field_pokes("AES", GL_RSCHANGE=1))
    assert (result.answer(), result.word(RSCHANGE)) == (0, 1)


# ---- set_defdrv -------------------------------------------------------------------------------------------------------
DRIVE_A, DRIVE_C, C_BIT = LEAF["DRIVE_A"], LEAF["DRIVE_C"], LEAF["DRIVE_C_BIT"]
# (the drive map Dsetdrv answers isdrive, the drive then made current, its return site, set_defdrv's answer)
MAPS = {
    "A: and B: (the captured machine's)": (0x0003, DRIVE_A, addrs.AES_SET_DEFDRV_A_RETURN, 0),
    "A:, B: and C:": (0x0007, DRIVE_C, addrs.AES_SET_DEFDRV_C_RETURN, 1),
    "C: alone": (0x0004, DRIVE_C, addrs.AES_SET_DEFDRV_C_RETURN, 1),
    "every drive but C:": (0xFFFF_FFFB, DRIVE_A, addrs.AES_SET_DEFDRV_A_RETURN, 0),
    "bit 2 of the high word alone: the map is tested as a WORD": (0x0004_0000, DRIVE_A, addrs.AES_SET_DEFDRV_A_RETURN, 0),
}
CURRENT, LAST_MAP = 1, 0x0000_0123      # Dgetdrv's answer (B:), and what the last Dsetdrv answers: left in DOS_AX


@THROUGH
@pytest.mark.parametrize("which", MAPS)
def test_set_defdrv_makes_c_current_when_the_map_has_it_else_a(which, through_line_f):
    """Three traps: isdrive's two (Dgetdrv; Dsetdrv of the drive it answered), then Dsetdrv(2) or Dsetdrv(0) by bit 2
    of the map's WORD. The site parked is the arm's own; the verdict the last trap's."""
    drive_map, drive, site, answer = MAPS[which]
    result = gd.run_scripted(SET_DEFDRV, (), [CURRENT, drive_map, LAST_MAP], through_line_f=through_line_f)
    assert gd.calls(result.final) == [gd.call(DGETDRV), gd.call(DSETDRV, ("w", CURRENT)), gd.call(DSETDRV, ("w", drive))]
    assert [parked for parked, _dos in gd.sites_parked_at(result.final)] == [
        addrs.AES_ISDRIVE_GDRV_RETURN, addrs.AES_ISDRIVE_SDRV_RETURN, site]
    assert result.answer() == answer
    assert [result.field("AES", name) for name in gd.DOS_FIELDS] == [site, addrs.AES_DOS_TRAP_RETURN, 0, LAST_MAP]


CURDRV_AT = gemdos.BASEPAGE + addrs.BASEPAGE_CURDRV
SNAPSHOT_MAP = case.long_in(BASE_IMAGE, addrs.SYSVAR_DRVBITS)
ARGUMENT_CLASS = "ARGUMENT CLASS (the drive map staged with a third drive)"
WITH_DRIVE_C = {addrs.SYSVAR_DRVBITS: (SNAPSHOT_MAP | C_BIT).to_bytes(aes.LONG_BYTES, "big")}


def test_set_defdrv_through_real_gemdos_on_the_captured_machine_makes_a_current():
    """The ROM's glue into the ROM's GEMDOS and BIOS, our C into the reconstructed leaves: the machine has A: and
    B: — the current drive (staged B:) becomes A:, and 0 is answered."""
    assert not SNAPSHOT_MAP & C_BIT
    result = gd.run_real(SET_DEFDRV, (), {CURDRV_AT: bytes([1])})
    assert (result.answer(), result.final[CURDRV_AT]) == (0, DRIVE_A)


def test_set_defdrv_through_real_gemdos_with_a_third_drive_makes_c_current():
    """ARGUMENT CLASS: `_drvbits` staged with bit 2 — a hard disk's bit, which the captured floppy machine has not."""
    result = gd.run_real(SET_DEFDRV, (), WITH_DRIVE_C)
    assert (result.answer(), result.final[CURDRV_AT]) == (1, DRIVE_C)


# ---- the desk's rsrc_free binding: a row that switches ---------------------------------------------------------------------
GEMDOS_OK, EIMBA = 0, -40 & aes.LONG_MASK
FREED = "the desk's resource freed, then a yield back to the desk"
REFUSED = "GEMDOS refuses the block (EIMBA): 0 answered after the same yield"


def _desk_running(answer):
    return functools.cache(lambda: gd.scripted_over(aes_event.machine(), [answer]))


def _row(label, answer):
    """A row that switches and traps: no door user (it makes no door call) — its Tier 1 fork binds the scripted
    GEMDOS by the row's own `child_doors`. THE ROW WHERE GEMDOS FREES THE BLOCK DECLARES ITS X FLAG: its yield follows
    GCC's `seq` / `neg` over rs_free's answer (Alcyon's code there leaves X clear)."""
    return switching.SwitchingRow(label, DESK_RSRC_FREE, (), _desk_running(answer), {}, child_doors=gd.CHILD_DOORS,
                                  x_flag_differs=answer == GEMDOS_OK)


ROWS = {FREED: _row(FREED, GEMDOS_OK), REFUSED: _row(REFUSED, EIMBA)}
PREMISES = {FREED: Premise((), 0, SHELL, (SHELL,), 1), REFUSED: Premise((), 0, SHELL, (SHELL,), 0)}
# BOTH ROWS ARE REGISTERED (`aes_switching.register_row`), the freed one with the X flag it declares
# (`aes_switching.THE_X_FLAG_ALONE`: one bit excused, nothing left out of the compare).
REGISTERED = {switching.row_name(row): row for row in map(switching.register_row, ROWS.values())}
# @PINS-BEGIN (measured: scratch `b5/H/pins.py`)
WHOLE_RUN = {
    "the desk's resource freed, then a yield back to the desk":
        {BENCH: (13172, 11560), SHIPPED: (13172, 11680)},
    'GEMDOS refuses the block (EIMBA): 0 answered after the same yield':
        {BENCH: (13182, 11558), SHIPPED: (13182, 11678)},
}
PRICED = {
    "the desk's resource freed, then a yield back to the desk":
        Priced((4220, 5988), None, None, (0, 0, 0)),   # 0.70
    'GEMDOS refuses the block (EIMBA): 0 answered after the same yield':
        Priced((4218, 5998), None, None, (0, 0, 0)),   # 0.70
}
# @PINS-END


@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_of_the_binding_is_what_its_name_says(label):
    """THE PREMISE: one trap — Mfree of the desk's resource header, global[7..8] of the desk's own global[] — then
    the dispatcher entered and the desk resumed; rs_free's answer handed back across the yield."""
    the_rom_s = switching.vet_the_premise(ROWS[label], PREMISES[label])
    assert gd.calls(the_rom_s.memory) == [gd.call(MFREE, ("l", rs.DESK_HEADER))]
    assert case.long_in(the_rom_s.memory, aes.AES_RS_GLOBAL) == aes.AES_DESK_APP_GLOBAL
    assert rs.header_of(aes.AES_DESK_APP_GLOBAL) == rs.DESK_HEADER, "the desk's global[] names the desk's resource"


@pytest.mark.parametrize("label", ROWS)
def test_the_binding_taken_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1 (`aes_switching.companion`, nothing dropped; the scripted trap bound in the same child): the same
    ledger, both returns parked (rs_free's own site), the verdict, the answer kept across the yield, every byte
    outside the run's own stack. (No separate compare AT the dispatcher: nothing is stored after the yield, so the
    run's end holds every store made before it.)"""
    ran = switching.companion(ROWS[label])
    assert ran.entered == (SHELL,) and ran.answer & aes.WORD_MASK == PREMISES[label].answer
    assert case.long_in(ran.image, aes.AES_DOS_RETURN) == addrs.AES_RS_FREE_MFREE_RETURN


def test_every_row_is_registered_and_pinned():
    assert set(REGISTERED) <= set(aes_event.SWITCHING_ROWS)
    assert ROWS.keys() == WHOLE_RUN.keys() == PRICED.keys()
    assert not any(aes_event.SWITCHING_ROWS[name].row.door for name in REGISTERED), "no door user: it makes no door call"


X_FLAG_AT, X_FLAG, C_FLAG = switching.X_FLAG_AT, switching.X_FLAG, 0x01
SUPERVISOR_BIT_OF_THE_SYSTEM_BYTE = 0x20


def test_only_the_freed_row_declares_its_x_flag_and_no_span_of_the_save_word_is_dropped():
    """The declaration is the freed row's alone, named among its drops — and NOTHING the kit is handed for either
    row covers a byte of the dispatcher's save word (the bit is flipped, the byte compared)."""
    drops = {label: aes_event.SWITCHING_ROWS[switching.row_name(row)].drops for label, row in ROWS.items()}
    assert [drop in drops[FREED] for drop in switching.THE_X_FLAG_ALONE] == [True]
    assert not [drop for drop in drops[REFUSED] if drop[0] <= X_FLAG_AT < drop[1]]
    assert not [drop for label in ROWS for drop in drops[label]
                if drop not in switching.THE_X_FLAG_ALONE and drop[0] < aes.AES_SR_DISPATCH + aes.WORD_BYTES and drop[1] > aes.AES_SR_DISPATCH]


def _with_our_image(blob, monkeypatch, change):
    """`blob`'s runs with `change(image)` laid into the image OUR run leaves, before Tier 3's own handling of it."""
    made = rom_bench.RomBench._call

    def changed(self, image, symbol, *args, **kwargs):
        ours = made(self, image, symbol, *args, **kwargs)
        change(ours.image)
        return ours
    monkeypatch.setattr(rom_bench.RomBench, "_call", changed)


def _undeclared(row):
    return row._replace(x_flag_differs=False)


def test_the_two_shores_differ_in_the_x_flag_alone_on_the_freed_row(blob):
    """THE MEASUREMENT the declaration stands on: the same row with nothing declared is refused at `$8995` alone,
    `$00` on the ROM's shore and `$10` on ours."""
    with pytest.raises(AssertionError, match=r"1 byte\(s\), first 0x8995 \(0x00 -> 0x10\)"):
        switching.measured_on(blob, _undeclared(ROWS[FREED]))


def test_a_wrong_c_bit_beside_the_x_flag_is_refused_on_the_declaring_row(blob, monkeypatch):
    """RED 1: the declaration excuses ONE bit — our run's carry laid wrong beside it is refused at the byte."""
    _with_our_image(blob, monkeypatch, lambda image: image.__setitem__(X_FLAG_AT, image[X_FLAG_AT] ^ C_FLAG))
    with pytest.raises(AssertionError, match=rf"first {X_FLAG_AT:#x} "):
        switching.measured_on(blob, ROWS[FREED])


def test_a_row_that_declares_nothing_is_refused_where_its_x_flag_differs(blob, monkeypatch):
    """RED 2: the refused row declares nothing — its X flag made to differ is a difference like any other."""
    switching.measured_on(blob, ROWS[REFUSED])
    _with_our_image(blob, monkeypatch, lambda image: image.__setitem__(X_FLAG_AT, image[X_FLAG_AT] ^ X_FLAG))
    with pytest.raises(AssertionError, match=rf"first {X_FLAG_AT:#x} "):
        switching.measured_on(blob, ROWS[REFUSED])


def test_a_row_that_declares_a_flag_it_does_not_need_is_refused(blob):
    """RED 3: the refused row's two shores hold the byte EQUAL — declared all the same, it is refused at that byte
    (the flip makes the difference the declaration promised and the run does not have)."""
    with pytest.raises(AssertionError, match=rf"first {X_FLAG_AT:#x} "):
        switching.measured_on(blob, ROWS[REFUSED]._replace(x_flag_differs=True))


def test_a_wrong_system_byte_of_that_word_is_still_refused(blob, monkeypatch):
    """...and the SYSTEM byte (`$8994`) of the same word, its supervisor bit lost on our side, is refused by name."""
    _with_our_image(blob, monkeypatch, lambda image: image.__setitem__(
        aes.AES_SR_DISPATCH, image[aes.AES_SR_DISPATCH] ^ SUPERVISOR_BIT_OF_THE_SYSTEM_BYTE))
    with pytest.raises(AssertionError, match=rf"first {aes.AES_SR_DISPATCH:#x} "):
        switching.measured_on(blob, ROWS[FREED])


@pytest.mark.parametrize("label", ROWS)
def test_a_row_really_switches_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH, whole: the image, the answer, the registers back after the wake,
    the idles and the cycles pinned — the arm where GEMDOS freed the block among them."""
    switching.vet_on_a_blob(blob, ROWS[label], PREMISES[label], switching.NO_WINDOW, WHOLE_RUN[label])


@pytest.mark.parametrize("label", ROWS)
def test_the_table_prices_a_row(label):
    switching.vet_the_table_s_price(ROWS[label], PRICED[label])


# ---- the registry -----------------------------------------------------------------------------------------------------------
aes.register("the device in use", APP_RESCHANGE, (SNAPSHOT_DEVICE,), aes.leaf_machine(onto=NO_CHANGE_ASKED))
aes.register("another device", APP_RESCHANGE, (3,), aes.leaf_machine(onto=NO_CHANGE_ASKED))
gd.register_scripted("no drive C:, A: made current", SET_DEFDRV, (), [CURRENT, 0x0003, LAST_MAP])
gd.register_scripted("a drive C:, made current", SET_DEFDRV, (), [CURRENT, 0x0007, LAST_MAP])
