"""THE VECTORS GEM TAKES (`src/aes/gemdosif.c`; hand 68000 in the ROM, `$fe3c62..$fe3cbd`): restore_trap2 `$fe3c62`,
install_trap2 `$fe3c6e`, retake `$fe3c84`, giveerr `$fe3ca4` and takeerr `$fe3cac` — the last three over one shared
tail, `$fe3c94`: Setexc($101, D0) through the BIOS.

    install_trap2():  VDI door ($8c2a) = vector $88;  vector $88 = the AES's trap #2 handler ($fe3ea6)
    restore_trap2():  vector $88 = $8c2a
    takeerr():        old critic ($8c26) = Setexc($101, -1);  Setexc($101, crit_err $fe3cbe)
    giveerr():        Setexc($101, $8c26)
    retake():         vector $88 = $fe3ea6;  Setexc($101, crit_err)        (nothing saved)

THE SURFACE OF A VECTOR TAKE is the vector's memory — `$88`, etv_critic `$404` — and the two longwords GEM keeps what
it displaced in, with D0 (Setexc's answer: the handler displaced) for the three that trap. The trap itself is the
machine's on the ROM's shore (the ROM's glue into the ROM's BIOS, its register save moved into the stack band:
`aes_event.savptr_in_the_band`, the bell's arrangement) and the BIOS's own C core on ours (`bios_setexc`).

WHAT REACHES EACH TODAY. gem_main calls install_trap2 and takeerr while GEM starts (`$fda074`, `$fda2bc`) and
restore_trap2 and giveerr once the shell has returned (`$fda3d0`, `$fda39e`); sh_tographic and sh_toalpha call retake
and giveerr round a launched program. The snapshot is GEM UP — both vectors GEM's — so:
  * `GEM_UP` is the capture: what giveerr and restore_trap2 are called over.
  * `GIVEN_BACK` is THE ROM'S OWN giveerr and restore_trap2 RUN OVER THE CAPTURE (each run's ledger laid over the
    last): both vectors their pre-GEM holders' again. It is what install_trap2 and takeerr find when GEM starts, as
    far as these four longwords go — AN ARGUMENT CLASS for those two (the rest of the machine is post-init, not
    gem_main's own at `$fda074`): OWED on the pre-init machine, both callers' own runs.
  * `A_PROGRAM_S_OWN` is the labelled staging of what retake exists for: a launched program that put handlers of
    its own in both vectors (two addresses of this battery's making — no program is run).
"""
import functools
import struct

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image

import aes
import aes_event
import aes_gemdosif as gd
import aes_trap_order as order
import case
import routines
import vdi
from case import merge_pokes

RESTORE_TRAP2, INSTALL_TRAP2, RETAKE, GIVEERR, TAKEERR = (
    "AES_ROM_RESTORE_TRAP2", "AES_ROM_INSTALL_TRAP2", "AES_ROM_RETAKE", "AES_ROM_GIVEERR", "AES_ROM_TAKEERR")
aes.declare_alcyon(RESTORE_TRAP2, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(INSTALL_TRAP2, None, (vdi.IMAGE_ARG,))
for _name in (RETAKE, GIVEERR, TAKEERR):
    aes.declare_alcyon(_name, aes.LONG_ANSWER, (vdi.IMAGE_ARG,))
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))

TRAP2, CRITIC = addrs.VECTOR_TRAP_GEM, 0x404        # the two vectors: `trap #2`'s, and etv_critic (Setexc's $101)
VDI_DOOR, OLD_CRITIC = addrs.SYSVAR_VDI_ENTRY, aes.AES_OLD_CRITIC
GEM_S_TRAP2, CRIT_ERR = addrs.GEM_TRAP2, addrs.AES_ROM_CRIT_ERR
SETEXC_CRITIC = aes.header_constants("gemdosif.h")["SETEXC_ETV_CRITIC"]
assert SETEXC_CRITIC * addrs.VECTOR_BYTES == CRITIC
FOUR = (TRAP2, VDI_DOOR, CRITIC, OLD_CRITIC)
for _at, _why in zip(FOUR, ("vector $88", "GEM's saved trap #2 holder", "etv_critic", "GEM's saved critical-error handler")):
    aes.declare_case_field(_at, aes.LONG_BYTES, f"the vectors GEM takes: {_why}")
ARGUMENT_CLASS = "ARGUMENT CLASS"

# What the capture holds: GEM up — and what its two vectors held before GEM (the BIOS's VDI door, the BIOS's own
# critical-error handler).
BIOS_VDI_DOOR, BIOS_CRITIC = addrs.GEM_TRAP2_VDI_DOOR, case.long_in(BASE_IMAGE, OLD_CRITIC)
# THE TRAP'S SAVE STEERS THE ATTRIBUTION PASS (the bell's reason: the BIOS dispatcher writes `savptr` itself), so the
# three that trap run without it; every longword they store is staged at another value instead (below).
SAVPTR_STEERS_THE_PASS = {"poison": False}
TRAPS = (RETAKE, GIVEERR, TAKEERR)


def longs(**values):
    at = {"trap2": TRAP2, "vdi_door": VDI_DOOR, "critic": CRITIC, "old_critic": OLD_CRITIC}
    return merge_pokes(*({at[name]: struct.pack(">I", value)} for name, value in values.items()))


def four(image):
    """`(vector $88, the saved holder, etv_critic, the saved handler)` in `image`."""
    return tuple(case.long_in(image, at) for at in FOUR)


def gem_up():
    """THE CAPTURE: GEM's handlers in both vectors, the BIOS's two saved."""
    return aes_event.savptr_in_the_band()


@functools.cache
def given_back():
    """THE ROM'S OWN giveerr, then its own restore_trap2, over the capture: both vectors their pre-GEM holders'."""
    pokes = gem_up()
    for entry in (addrs.AES_ROM_GIVEERR, addrs.AES_ROM_RESTORE_TRAP2):
        delta, _final, _regs = aes_event.derived(entry, pokes)
        pokes = merge_pokes(pokes, delta)
    return pokes


# A program's own two handlers (the staged class): addresses in this battery's band, nothing at them.
PROGRAM_S_TRAP2, PROGRAM_S_CRITIC = gd.BAND_END, gd.BAND_END + 8
assert PROGRAM_S_CRITIC + 8 <= gd.BAND_AT + gd.BAND_BYTES


def a_program_s_own(onto=None):
    return merge_pokes(onto or gem_up(), longs(trap2=PROGRAM_S_TRAP2, critic=PROGRAM_S_CRITIC))


def run(name, machine, **kwargs):
    passes = SAVPTR_STEERS_THE_PASS if name in TRAPS else {}
    return aes.run_function(name, (), aes.leaf_machine(onto=machine), **passes, **kwargs)


def test_the_machines_are_what_their_names_say():
    assert four(make_image(gem_up())) == (GEM_S_TRAP2, BIOS_VDI_DOOR, CRIT_ERR, BIOS_CRITIC) == four(BASE_IMAGE)
    assert four(make_image(given_back())) == (BIOS_VDI_DOOR, BIOS_VDI_DOOR, BIOS_CRITIC, BIOS_CRITIC)
    assert BIOS_CRITIC == case.long_in(BASE_IMAGE, addrs.ROM_BASE + 4) or BIOS_CRITIC >> 16 == 0xFC, "a BIOS routine"


# ---- the trap #2 pair ---------------------------------------------------------------------------------------------------
STALE = vdi.STALE_LONG


@THROUGH
def test_install_trap2_saves_the_vector_s_holder_then_stores_gem_s_handler(through_line_f):
    """ARGUMENT CLASS (`GIVEN_BACK`: gem_main's own call is the pre-init machine's). The holder — the BIOS's VDI door
    — into the longword the handler's VDI arm jumps through (staged stale), GEM's handler into the vector."""
    result = run(INSTALL_TRAP2, merge_pokes(given_back(), longs(vdi_door=STALE)), through_line_f=through_line_f)
    assert four(result.final) == (GEM_S_TRAP2, BIOS_VDI_DOOR, BIOS_CRITIC, BIOS_CRITIC)


def test_install_trap2_over_a_program_s_handler_saves_that():
    """ARGUMENT CLASS (a staged holder). Whatever holds the vector is what is saved — the save comes FIRST."""
    result = run(INSTALL_TRAP2, a_program_s_own(longs(vdi_door=STALE)))
    assert four(result.final)[:2] == (GEM_S_TRAP2, PROGRAM_S_TRAP2)


def test_install_trap2_a_second_time_saves_gem_s_own_handler_as_the_vdi_s_door():
    """A ROM BEHAVIOUR, KEPT: nothing guards a second install. Over GEM UP it saves GEM's own handler as the place
    its VDI arm jumps to — a VDI call would then loop in the handler for ever. (No ROM caller installs twice.)"""
    result = run(INSTALL_TRAP2, gem_up())
    assert four(result.final)[:2] == (GEM_S_TRAP2, GEM_S_TRAP2)


@THROUGH
def test_restore_trap2_puts_the_saved_holder_back(through_line_f):
    """Over GEM UP (gem_main's own call, `$fda3d0`, is made with GEM up): the vector the BIOS's VDI door again, the
    saved longword left."""
    result = run(RESTORE_TRAP2, gem_up(), through_line_f=through_line_f)
    assert four(result.final) == (BIOS_VDI_DOOR, BIOS_VDI_DOOR, CRIT_ERR, BIOS_CRITIC)


def test_restore_trap2_copies_whatever_was_saved():
    result = run(RESTORE_TRAP2, merge_pokes(gem_up(), longs(vdi_door=PROGRAM_S_TRAP2 | aes.BUS_TAG)))
    assert four(result.final)[:2] == (PROGRAM_S_TRAP2 | aes.BUS_TAG,) * 2


# ---- the critical-error handler: takeerr, giveerr -------------------------------------------------------------------------
@THROUGH
def test_takeerr_saves_the_handler_in_place_then_installs_crit_err(through_line_f):
    """ARGUMENT CLASS (`GIVEN_BACK`). Two Setexc: the first asks ($ffffffff: nothing stored) and its answer is kept
    (staged stale); the second installs crit_err — and D0 is the handler it displaced, the same BIOS routine."""
    result = run(TAKEERR, merge_pokes(given_back(), longs(old_critic=STALE)), through_line_f=through_line_f)
    assert four(result.final) == (BIOS_VDI_DOOR, BIOS_VDI_DOOR, CRIT_ERR, BIOS_CRITIC)
    assert result.long_answer() == BIOS_CRITIC


def test_takeerr_a_second_time_saves_crit_err_itself():
    """A ROM BEHAVIOUR, KEPT: over GEM UP the handler in place is GEM's own, and that is what is saved — giveerr
    would then give crit_err "back"."""
    result = run(TAKEERR, gem_up())
    assert four(result.final)[2:] == (CRIT_ERR, CRIT_ERR) and result.long_answer() == CRIT_ERR


@THROUGH
def test_giveerr_installs_the_saved_handler_and_answers_the_one_displaced(through_line_f):
    result = run(GIVEERR, gem_up(), through_line_f=through_line_f)
    assert four(result.final) == (GEM_S_TRAP2, BIOS_VDI_DOOR, BIOS_CRITIC, BIOS_CRITIC)
    assert result.long_answer() == CRIT_ERR


def test_giveerr_answers_the_displaced_handler_s_whole_longword():
    """ARGUMENT CLASS (a staged handler in place, with a top byte: `A_PROGRAM_S_OWN`'s, tagged). Setexc's answer is
    D0's whole longword and giveerr hands it on as it is — no bus mask."""
    in_place = PROGRAM_S_CRITIC | aes.BUS_TAG
    result = run(GIVEERR, merge_pokes(gem_up(), longs(critic=in_place)))
    assert result.long_answer() == in_place and four(result.final)[2] == BIOS_CRITIC


def test_giveerr_of_a_saved_longword_with_bit_31_set_installs_nothing():
    """ARGUMENT CLASS (a staged saved handler). Setexc tests its handler as a SIGNED LONG: a saved longword with
    bit 31 set is an inquiry — the vector stays crit_err's, and is answered."""
    result = run(GIVEERR, merge_pokes(gem_up(), longs(old_critic=0x8000_0000 | PROGRAM_S_CRITIC)))
    assert four(result.final)[2] == CRIT_ERR == result.long_answer()


# ---- retake ------------------------------------------------------------------------------------------------------------------
RETAKEN_OVER = {
    "a program's own handlers": (a_program_s_own, PROGRAM_S_CRITIC),
    "the vectors given back": (given_back, BIOS_CRITIC),
    "GEM up already": (gem_up, CRIT_ERR),
}


@THROUGH
@pytest.mark.parametrize("which", RETAKEN_OVER)
def test_retake_stores_both_of_gem_s_and_saves_neither(which, through_line_f):
    """Both vectors GEM's again; the two saved longwords UNTOUCHED (what a program left in the vectors is lost);
    D0 the critical-error handler displaced."""
    machine, displaced = RETAKEN_OVER[which]
    before = four(make_image(machine()))
    result = run(RETAKE, machine(), through_line_f=through_line_f)
    assert four(result.final) == (GEM_S_TRAP2, before[1], CRIT_ERR, before[3])
    assert result.long_answer() == displaced


def test_retake_stores_the_trap_2_vector_before_it_traps():
    """THE ORDER, on the ROM's own run stopped at the shared tail (`$fe3c94`): vector $88 is GEM's already, the
    critical-error vector not yet. (What our build does there is its `.S`'s bytes: `test_aes_gemdosif_transcription`.)"""
    image = make_image(aes.leaf_machine(onto=a_program_s_own()))
    final, _writes, _regs = emu.run(image, addrs.AES_ROM_RETAKE, {}, stop_pc=SETEXC_TAIL)
    assert four(final)[::2] == (GEM_S_TRAP2, PROGRAM_S_CRITIC)


SETEXC_TAIL = 0xFE3C94


# ---- THE ORDER OF A TWIN'S STORES ROUND ITS TRAPS (`aes_trap_order`), on the bench's blob -------------------------------------
# The twins' images at the end say nothing of it: retake's vector store and its Setexc commute in memory, and so do
# takeerr's save and its install. Watched at the BIOS's trap on both shores — the ROM's routine and the C twin as
# the bench's blob holds it — each Setexc is taken with the vectors as the ROM's found them.
PROGRAM_S_ROW, GIVEN_BACK_ROW = f"{ARGUMENT_CLASS}: a program's own handlers in both vectors", (
    f"{ARGUMENT_CLASS}: the vectors given back (the ROM's own giveerr and restore_trap2)")


def _watched(row):
    tier3 = bench_tier3()
    return order.on_both_shores(tier3, tier3.RomBench(), row)


def test_the_twin_of_retake_stores_the_trap_2_vector_before_its_setexc():
    """...over a program's own handlers: at the one Setexc, vector $88 is GEM's ALREADY (the program's before the
    call) and etv_critic still the program's — on both shores."""
    the_rom_s, ours = _watched(bench_tier3().row_named((routines.core_symbol(RETAKE), PROGRAM_S_ROW)))
    assert the_rom_s.names() == [(order.BIOS, addrs.BIOS_SETEXC_FN)] and ours.made == the_rom_s.made
    assert (the_rom_s.held(0, TRAP2), the_rom_s.held(0, CRITIC)) == (GEM_S_TRAP2, PROGRAM_S_CRITIC)


def test_the_twin_of_takeerr_saves_the_handler_in_place_before_it_installs_gem_s():
    """...over the vectors given back: two Setexcs, and at the SECOND — the install — AES_OLD_CRITIC holds what the
    first answered already (stale at the first), on both shores."""
    the_rom_s, ours = _watched(bench_tier3()._row(TAKEERR_S_C_ROW))
    assert the_rom_s.names() == 2 * [(order.BIOS, addrs.BIOS_SETEXC_FN)] and ours.made == the_rom_s.made
    assert [the_rom_s.held(nth, OLD_CRITIC) for nth in range(2)] == [STALE, BIOS_CRITIC]


def test_two_vectors_at_one_handler_are_refused_by_the_order_watch():
    """THE WATCH'S OWN RED: its handlers are read BY VECTOR — a machine with the BIOS's and the XBIOS's vectors at one
    address is refused by name at the arrival, where a map by address called it one trap's."""
    machine = make_image(merge_pokes(gem_up(), {addrs.VECTOR_TRAP_XBIOS: BASE_IMAGE[addrs.VECTOR_TRAP_BIOS:][:aes.LONG_BYTES]}))
    watch = order.TrapOrder(machine)
    shared = case.long_in(machine, addrs.VECTOR_TRAP_BIOS) & aes.OS_BUS_ADDR_MASK
    assert shared in watch.first and len(watch.first) == len(order.VECTORS) - 1
    with pytest.raises(AssertionError, match="one handler behind two vectors"):
        watch.stopped(shared, emu.STACK_TOP, machine)


# ---- the registry -------------------------------------------------------------------------------------------------------------
aes.register("GEM up: the BIOS's door put back", RESTORE_TRAP2, (), aes.leaf_machine(onto=gem_up()))
aes.register(GIVEN_BACK_ROW, INSTALL_TRAP2, (), aes.leaf_machine(onto=merge_pokes(given_back(), longs(vdi_door=STALE))))
# takeerr's C TWIN IS VERIFIED AND NOT IN THE TABLE (T2): the target ships its `.S`, whose rows the table prices
# (`test_aes_gemdosif_transcription.py`); the twin measures 1.04 only because the BIOS's whole Setexc — twice — is
# in both columns (on its own cycles some 1.15, over the bar as its four siblings are), and a row printed under the
# bar with no verdict beside four marked `transcribed` reads as a twin that ships. Listed with this reason in the
# census of unpriced rows (`test_tier3.py`, UNPRICED_AT_A_ROM_ENTRY).
TAKEERR_S_C_ROW = aes.ROWS.register(
    f"{routines.core_symbol(TAKEERR)}, {GIVEN_BACK_ROW}", addrs.AES_ROM_TAKEERR,
    aes.staged(TAKEERR, (), aes.leaf_machine(onto=merge_pokes(given_back(), longs(old_critic=STALE)))), priced=False)
aes.register("GEM up: the BIOS's handler installed again", GIVEERR, (), aes.leaf_machine(onto=gem_up()))
aes.register(PROGRAM_S_ROW, RETAKE, (), aes.leaf_machine(onto=a_program_s_own()))
aes.register("the vectors given back", RETAKE, (), aes.leaf_machine(onto=given_back()))
