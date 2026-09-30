"""The INPUT polls and functions (`src/vdi/mouse.c`):

    $fca7ca poll_key       $fca7c0 poll_choice      $fca88a poll_locator
    $fcb002 vdi_locator (28)      $fcb1a0 vdi_choice (30)      $fcb22a vdi_string (31)

Every poll that reaches the keyboard takes BIOS Bconstat/Bconin on device 2 through the ROM's own `trap #13`
on the oracle and the BIOS core directly on the host, so each case stages `savptr` in the dropped band
(`gemdos.machine`) and does not poison — the attribution pass would invert `savptr` itself. A key is staged
in the IKBD ring (`vdi_mouse.keys_pokes`), which is what the keyboard interrupt would have done: a REQUEST
spins until a poll answers, and nothing else in a run can end it. Each spin goes through the kit's
scheduled-write door at its WAIT SITE (`addrs.h`'s VDI_*_WAIT_SITE, `mouse.c`'s `request_pass`), so a request
case DECLARES that site — both shores then count the passes and must agree — and the arms that come round
the loop AGAIN (a poll that found nothing, the locator's motion) are reached by SCHEDULING the interrupt: a
key's tail store (`vdi_mouse.keys_arriving`) or a button's CUR_MS_STAT byte landing before a later pass.

THE CHOICE "DEVICE" IS NOT THERE. `$fca7c0` stores TERM_CH = 1 and never writes D0, so what vdi_choice reads
back as the poll's answer is the D0 the DISPATCHER left: the MONO_STATUS word it stored last, 0 or 8
(`$fcaae6`). Request mode waits for a 1 and so SPINS FOR EVER; sample mode answers 0 or 8 words and writes
none. Each case enters with D0 = MONO_STATUS — the machine the dispatcher leaves — and the arms for 1 and 2,
which no dispatched call reaches, are pinned with a MONO_STATUS staged to match (ROM-unreachable, pinned
anyway). The spin itself is pinned twice: the ROM alone, still spinning a million instructions in, and the
reconstruction alone, running its wait site to the door's cap.
"""
import ctypes
from pathlib import Path

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import gemdos
import routines
import vdi
import vdi_mouse as mouse
from case import merge_pokes

A_KEY = mouse.key(0x1E, ord("a"))
B_KEY = mouse.key(0x30, ord("B"))
RETURN_KEY = mouse.key(0x1C, 13)
SHIFTED = 0x0800_0000               # Bconin's kbshift byte, with conterm bit 3: shifted out of TERM_CH
MONO = vdi.linea(BASE_IMAGE, "MONO_STATUS")
# The scheduled-write door's cap on one wait site, read from the kit's own header.
SCHED_POLL_MAX = addrs.parse(Path(__file__).resolve().parents[4] / "tools/recreate_kit/include/os.h")["OS_SCHED_POLL_MAX"]


def machine(pokes=None):
    return merge_pokes(gemdos.machine(), vdi.linea_pokes(TERM_CH=0x5A5A), pokes)


def run_poll(name, pokes, registers=None):
    return vdi.run_primitive(name, registers or {}, machine(pokes), poison=False)


# ---- the polls -----------------------------------------------------------------------------------------

def test_poll_key_answers_nothing_on_an_empty_ring():
    result = run_poll("VDI_ROM_POLL_KEY", mouse.keys_pokes())
    assert result.info["regs"]["d0"] == 0 and result.linea("TERM_CH") == 0x5A5A


@pytest.mark.parametrize("key", (A_KEY, RETURN_KEY, SHIFTED | A_KEY, 0xFFFF_FFFF, 0x0048_0000, 0x00FF_1234))
def test_poll_key_answers_the_scancode_over_the_ascii_word(key):
    """`swap` / `lsl.w #8` / `or.w`: the scancode byte into the high byte, OR-ed over the whole ASCII WORD."""
    result = run_poll("VDI_ROM_POLL_KEY", mouse.keys_pokes(key))
    assert result.info["regs"]["d0"] == 1
    assert result.linea("TERM_CH") == (key & 0xFFFF | (key >> 16 & 0xFF) << 8)


@pytest.mark.parametrize("entry", (0, 1, 0xDEAD_BEEF))
def test_poll_choice_stores_one_and_leaves_d0(entry):
    result = run_poll("VDI_ROM_POLL_CHOICE", {}, {"d0": entry})
    assert result.info["regs"]["d0"] == entry and result.linea("TERM_CH") == 1


@pytest.mark.parametrize("status,term", ((0x40, 0x20), (0x80, 0x21), (0xC0, 0x20), (0xFF, 0x20), (0xA3, 0x21)))
def test_poll_locator_answers_a_changed_button_first(status, term):
    """Bit 6 is the left button's change and bit 7 the right's; the left wins, and CUR_MS_STAT keeps the
    buttons and the moved bit only. A key waiting is not read."""
    result = run_poll("VDI_ROM_POLL_LOCATOR", merge_pokes(mouse.keys_pokes(A_KEY), vdi.linea_pokes(CUR_MS_STAT=status)))
    assert result.info["regs"]["d0"] == 1 and result.linea("TERM_CH") == term
    assert result.linea("CUR_MS_STAT") == status & 0x23


@pytest.mark.parametrize("status", (0x00, 0x20, 0x23))
def test_poll_locator_answers_a_key_before_motion(status):
    result = run_poll("VDI_ROM_POLL_LOCATOR", merge_pokes(mouse.keys_pokes(B_KEY), vdi.linea_pokes(CUR_MS_STAT=status)))
    assert result.info["regs"]["d0"] == 1 and result.linea("CUR_MS_STAT") == status


@pytest.mark.parametrize("status", (0x20, 0x3F, 0x21))
def test_poll_locator_answers_motion_with_the_cursor_in_x1_y1(status):
    """The status byte is the one read BEFORE the keyboard poll — the ROM keeps it in D1 across the trap."""
    pokes = merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=status, GCURX=123, GCURY=45, X1=-1, Y1=-1))
    result = run_poll("VDI_ROM_POLL_LOCATOR", pokes)
    assert result.info["regs"]["d0"] == 2 and (result.linea("X1"), result.linea("Y1")) == (123, 45)
    assert result.linea("CUR_MS_STAT") == status & ~0x20


@pytest.mark.parametrize("status", (0x00, 0x03, 0x1F))
def test_poll_locator_answers_nothing(status):
    result = run_poll("VDI_ROM_POLL_LOCATOR", merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=status)))
    assert result.info["regs"]["d0"] == 0


# ---- vdi_locator -----------------------------------------------------------------------------------------

def locator_pokes(mode, point=(200, 120), pokes=None):
    return machine(merge_pokes(vdi.function_pokes("VDI_ROM_LOCATOR", (0x5A5A,), point),
                               vdi.linea_pokes(LOC_MODE=mode, X1=0x1111, Y1=0x2222), pokes))


WAIT_SITES = {"VDI_ROM_LOCATOR": addrs.VDI_LOCATOR_WAIT_SITE, "VDI_ROM_CHOICE": addrs.VDI_CHOICE_WAIT_SITE,
              "VDI_ROM_STRING": addrs.VDI_STRING_WAIT_SITE}


def run_function(name, pokes, registers=None, schedule=()):
    """`vdi.run_function`, entered with `registers` as well — vdi_choice's D0 is the dispatcher's — and
    unpoisoned (the module docstring); its request spin's wait site declared, and `schedule` the interrupts
    that land there."""
    core = getattr(_lib, routines.core_symbol(name))
    core.restype = None
    return vdi.Result(case.run(getattr(addrs, name), {**(registers or {}), "_pokes": pokes},
                               lambda _lib_, buf: core(buf), width=case.NO_RESULT, poison=False,
                               schedule=list(schedule), wait_sites=(WAIT_SITES[name],)), pokes)


@pytest.mark.parametrize("ending", ("key", "left button", "right button"))
def test_a_requested_locator_shows_the_cursor_waits_and_hides_it(ending):
    """The depth FORCED to 1 and shown — the arrow drawn at ptsin[0] — then the answer, then hidden again.
    The capture's own arrow stays on the screen: it was showing, and the forced depth skips its removal."""
    extra = mouse.keys_pokes(A_KEY) if ending == "key" else merge_pokes(
        mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x40 if ending == "left button" else 0x80))
    result = run_function("VDI_ROM_LOCATOR", locator_pokes(0, pokes=extra))
    assert (result.contrl(vdi.CONTRL_N_INTOUT), result.contrl(vdi.CONTRL_N_PTSOUT)) == (1, 1)
    assert result.word(vdi.INTIN_AT) == 1
    assert result.linea("M_HID_CT") == 1


@pytest.mark.parametrize("arm", ("nothing", "key", "button", "motion"))
def test_a_sampled_locator_answers_its_poll_s_arm(arm):
    extra = {"nothing": mouse.keys_pokes(), "key": mouse.keys_pokes(B_KEY),
             "button": merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x80)),
             "motion": merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x21))}[arm]
    result = run_function("VDI_ROM_LOCATOR", locator_pokes(1, pokes=extra))
    counts = {"nothing": (0, 0), "key": (1, 0), "button": (1, 0), "motion": (0, 1)}[arm]
    assert (result.contrl(vdi.CONTRL_N_INTOUT), result.contrl(vdi.CONTRL_N_PTSOUT)) == counts
    assert (result.linea("GCURX"), result.linea("GCURY")) == (200, 120)


def button_arriving(nth, status):
    """The mouse ISR's CUR_MS_STAT byte landing before the locator's `nth` pass."""
    return {"pc": addrs.VDI_LOCATOR_WAIT_SITE, "nth": nth, "addr": vdi.LINEA_CUR_MS_STAT, "width": 1, "value": status}


@pytest.mark.parametrize("passes", (2, 5))
def test_a_requested_locator_goes_round_until_a_button(passes):
    """Nothing to find until the button's change lands: the loop goes round `passes` - 1 times first."""
    result = run_function("VDI_ROM_LOCATOR", locator_pokes(0, pokes=mouse.keys_pokes()),
                          schedule=[button_arriving(passes, 0x80)])
    assert result.linea("TERM_CH") == 0x21


def test_a_requested_locator_takes_motion_and_goes_round_to_a_key():
    """Motion first — X1/Y1 from GCURX/GCURY, the moved bit taken, and round again — then a key on pass 3."""
    keys, schedule = mouse.keys_arriving(addrs.VDI_LOCATOR_WAIT_SITE, (3, B_KEY))
    result = run_function("VDI_ROM_LOCATOR", locator_pokes(0, pokes=merge_pokes(keys, vdi.linea_pokes(CUR_MS_STAT=0x21))),
                          schedule=schedule)
    assert result.ptsout(2) == [200, 120] and result.linea("CUR_MS_STAT") == 0x01


def test_the_locator_writes_intin_before_reading_ptsin():
    """intin[0] = 1 is stored into the CALLER'S array first: laid over ptsin[0], it becomes the x."""
    pokes = merge_pokes(locator_pokes(1, pokes=mouse.keys_pokes()), vdi.linea_pokes(INTIN=vdi.VDI_PTSIN_COPY))
    result = run_function("VDI_ROM_LOCATOR", pokes)
    assert result.linea("GCURX") == 1


# ---- vdi_choice -------------------------------------------------------------------------------------------

def choice_pokes(mode, mono=MONO):
    return machine(merge_pokes(vdi.function_pokes("VDI_ROM_CHOICE"), vdi.linea_pokes(CHC_MODE=mode, MONO_STATUS=mono)))


@pytest.mark.parametrize("mono", (0, 8))
def test_a_sampled_choice_answers_the_dispatcher_s_d0_as_its_count(mono):
    result = run_function("VDI_ROM_CHOICE", choice_pokes(1, mono), {"d0": mono})
    assert result.contrl(vdi.CONTRL_N_INTOUT) == mono and result.intout(2) == [vdi.FILL * 0x0101] * 2


@pytest.mark.parametrize("arm", (1, 2))
def test_the_choice_arms_no_dispatched_call_reaches(arm):
    result = run_function("VDI_ROM_CHOICE", choice_pokes(1, arm), {"d0": arm})
    assert result.intout(2)[arm - 1] == 1


def test_a_requested_choice_ends_only_on_a_d0_of_one():
    result = run_function("VDI_ROM_CHOICE", choice_pokes(0, 1), {"d0": 1})
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1 and result.intout(1) == [1]


def test_a_requested_choice_through_the_dispatcher_never_returns():
    """The ROM alone, over the machine a dispatched call leaves: it is still spinning a million
    instructions in. (Not a differential: neither side returns.)"""
    from harness import emu, make_image

    with pytest.raises(RuntimeError, match="did not reach"):
        emu.run(make_image(choice_pokes(0)), addrs.VDI_ROM_CHOICE, {"d0": MONO}, max_insns=1_000_000)


def test_the_reconstruction_s_requested_choice_spins_to_the_cap():
    """...and the reconstruction alone: with its wait site declared and no store scheduled, it polls there
    until the door's cap (`sched.h`) refuses the case — every pass a poll, none of them ending it."""
    from harness import arm_candidate, make_image

    arm_candidate(sites=(addrs.VDI_CHOICE_WAIT_SITE,))
    image = make_image(choice_pokes(0))
    _lib.vdi_choice((ctypes.c_uint8 * len(image)).from_buffer(image))
    assert _lib.g_sched_exhausted() == 1
    assert _lib.g_sched_site_polls(0) == SCHED_POLL_MAX


# ---- vdi_string ---------------------------------------------------------------------------------------------

def string_pokes(mode, count, *keys):
    return machine(merge_pokes(vdi.function_pokes("VDI_ROM_STRING", (count & 0xFFFF,)),
                               vdi.linea_pokes(STR_MODE=mode), mouse.keys_pokes(*keys)))


@pytest.mark.parametrize("count,keys,stored", (
    (3, (A_KEY, B_KEY, A_KEY), 3),
    (2, (A_KEY, B_KEY, A_KEY), 2),
    (5, (A_KEY, RETURN_KEY), 1),
    (1, (RETURN_KEY,), 0),
    (0, (), 0),
))
def test_a_requested_string_reads_to_its_count_or_a_return(count, keys, stored):
    result = run_function("VDI_ROM_STRING", string_pokes(0, count, *keys))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == stored


@pytest.mark.parametrize("arrivals", (((2, A_KEY),), ((1, A_KEY), (4, B_KEY)), ((3, RETURN_KEY),)),
                         ids=("one late key", "a key, then one three passes on", "a late RETURN"))
def test_a_requested_string_goes_round_until_each_key(arrivals):
    """Each empty poll goes round the inner spin again; the key landing at a later pass ends it."""
    keys, schedule = mouse.keys_arriving(addrs.VDI_STRING_WAIT_SITE, *arrivals)
    pokes = machine(merge_pokes(vdi.function_pokes("VDI_ROM_STRING", (len(arrivals),)), vdi.linea_pokes(STR_MODE=0),
                                keys))
    run_function("VDI_ROM_STRING", pokes, schedule=schedule)


def test_a_negative_count_reads_whole_words_past_a_return():
    """Masked with $ffff, a RETURN is $1c0d — never 13 — so it is read, stored and COUNTED like any key."""
    result = run_function("VDI_ROM_STRING", string_pokes(0, -2, RETURN_KEY, SHIFTED | B_KEY))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 2 and result.intout(2) == [0x1C0D, 0x3042]


def test_a_count_of_minus_32768_reads_nothing():
    """`neg.w` of $8000 is $8000: still negative, so no index is below it."""
    result = run_function("VDI_ROM_STRING", string_pokes(0, -32768, A_KEY))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0 and result.linea("TERM_CH") == 0


@pytest.mark.parametrize("count,keys", ((5, (A_KEY, B_KEY)), (1, (A_KEY, B_KEY)), (3, ()), (-4, (RETURN_KEY, A_KEY))))
def test_a_sampled_string_stops_at_the_first_empty_poll(count, keys):
    result = run_function("VDI_ROM_STRING", string_pokes(1, count, *keys))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == min(abs(count), len(keys))


# ---- the rows Tier 3 prices -------------------------------------------------------------------------------
vdi.register("vdi_poll_key, a key", addrs.VDI_ROM_POLL_KEY, machine(mouse.keys_pokes(A_KEY)))
vdi.register("vdi_poll_key, none", addrs.VDI_ROM_POLL_KEY, machine(mouse.keys_pokes()))
vdi.register("vdi_poll_choice, the stub", addrs.VDI_ROM_POLL_CHOICE, machine(), regs={"d0": MONO})
vdi.register("vdi_poll_locator, motion", addrs.VDI_ROM_POLL_LOCATOR,
             machine(merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x21))))
vdi.register("vdi_poll_locator, a button", addrs.VDI_ROM_POLL_LOCATOR, machine(vdi.linea_pokes(CUR_MS_STAT=0x40)))
vdi.register("vdi_locator, requested, a key", addrs.VDI_ROM_LOCATOR, locator_pokes(0, pokes=mouse.keys_pokes(A_KEY)))
vdi.register("vdi_locator, sampled, motion", addrs.VDI_ROM_LOCATOR,
             locator_pokes(1, pokes=merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x21))))
vdi.register("vdi_choice, sampled", addrs.VDI_ROM_CHOICE, choice_pokes(1), regs={"d0": MONO})
vdi.register("vdi_string, requested, three keys", addrs.VDI_ROM_STRING, string_pokes(0, 3, A_KEY, B_KEY, A_KEY))
vdi.register("vdi_string, sampled, two keys", addrs.VDI_ROM_STRING, string_pokes(1, 5, A_KEY, B_KEY))
