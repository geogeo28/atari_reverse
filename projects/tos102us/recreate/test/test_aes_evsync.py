"""The scheduler's SEMAPHORE — `src/aes/evsync.c` (`aes/evsync.h`).

    tak_flag(spb)    spb->count++; if (spb->owner == rlr || spb->count == 1) { spb->owner = rlr; return 1; }
                     spb->count--; return 0;                                        ($fe4e5a)

EVERY LOCK STATE IS THE ROM'S OWN — but for the two cases SAID, in their docstrings, to stage a field (below) —
(`test_aes_wm_update.py`'s machines, each the scheduler's and wind_update's runs):
free; held by the running process, once and twice; held by it WITH A PROCESS QUEUED ON IT (the screen manager parked on
the lock's wait list — the one real state whose SPB_WAIT is not zero: tak_flag leaves the list alone); held by ANOTHER
process (PD0 takes the screen lock and parks for a key, the mouse onto the menu bar wakes the screen manager: the lock
it then asks for is PD0's); released once too often (the count -1: what the next BEG_UPDATE finds, a ROM finding of
that battery's). The only semaphore the ROM keeps is the screen lock (`wind_spb`); the pointer is its caller's all the
same, and is taken through the 24-bit bus. UNPINNED: a REFUSAL with a process already queued — it needs a third
process (a staged application, `aes_pdpipe`), which amutex's own battery brings (wave 1).

TWO ARGUMENT-CLASS CASES OVER A POKED FIELD, labelled where they stand: the owner, and `rlr`, named by a pointer WITH A
TOP BYTE. No ROM run makes either — the scheduler stores its PDs' own addresses — so neither is a lock state, and
neither is cited as one: what they pin is the routine's own width (`cmp.l`, `move.l 2(a5),d0`), which every state the
ROM makes satisfies whichever width a C compared at.

THE C RUNS FIRST IN A CHILD, as every battery of the event layer's does — every run of it in a fork of the worker
(`aes_event.run_core_guarded`: tak_flag reaches no hook): it has no loop today, but a twin that spun would hang the
worker in process — a crash, no failure.

THE ORDER the ROM reads and writes in is pinned by semaphores laid OVER `rlr` itself (the long the routine compares
the owner with and stores): the count is stored BEFORE `rlr` is loaded. No machine holds such a semaphore; a C that
read `rlr` first would pass every real state. (The ROM loads `rlr` a second time for the store; nothing is stored
between its two loads, so a C that loaded it once is the same function — unpinned, equivalent.)

D0's HIGH WORD on a refusal is the owner's (`move.l 2(a5),d0` then `clr.w d0`): the answer is a WORD, and compared as
one.
"""
import functools
import struct

import pytest

import aes
import aes_event
import case
import test_aes_wm_update as wm_update
import vdi
from aes_gsx import THROUGH
from case import merge_pokes
from harness import addrs, make_image

EVSYNC = aes.header_constants("evsync.h")
TAKEN, REFUSED = EVSYNC["TAK_FLAG_TAKEN"], EVSYNC["TAK_FLAG_REFUSED"]
TAK_FLAG = "AES_ROM_TAK_FLAG"
aes.declare_alcyon(TAK_FLAG, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG))
WIND_SPB, SPB_COUNT, SPB_OWNER = wm_update.WIND_SPB, wm_update.SPB_COUNT, wm_update.SPB_OWNER
SPB_WAIT = wm_update.WU["SPB_WAIT"]
running, locked, spb_of = wm_update.running, wm_update.locked, wm_update.spb_of


@functools.cache
def held_by_another():
    """The screen lock PD0's, the SCREEN MANAGER running: PD0 took it and parked in an evnt_multi for a key (an
    application holding the screen while it waits), and the mouse onto the menu bar woke PD1 — `waited_on`'s first two
    steps, stopped before the screen manager asks for the lock."""
    pokes = aes_event.woken_onto_the_menu_bar(aes_event.parked(addrs.AES_ROM_EV_MULTI, wm_update.KEY_WAIT, locked()))
    assert spb_of(make_image(pokes)) == (1, aes.SHELL_PD), "the premise: the lock is PD0's"
    assert aes.list_of(make_image(pokes), aes.AES_RLR) == [aes.SCREEN_MANAGER_PD], "...and PD1 runs"
    return pokes


def tak_flag(pokes, semaphore=WIND_SPB, **kwargs):
    """The differential of tak_flag(`semaphore`) over `pokes`: every run of its C first in a fork."""
    return aes_event.run_core_guarded(TAK_FLAG, (semaphore,), pokes, **kwargs)


def spb(result, at=WIND_SPB):
    return aes.signed(result.word(at + SPB_COUNT)), result.long(at + SPB_OWNER)


@THROUGH
def test_a_free_semaphore_is_taken(through_line_f):
    result = tak_flag(running(), through_line_f=through_line_f)
    assert result.answer() == TAKEN and spb(result) == (1, aes.SHELL_PD)


@pytest.mark.parametrize("times", (1, 2), ids=("held once", "held twice"))
def test_the_running_process_takes_its_own_again(times):
    result = tak_flag(locked(times=times))
    assert result.answer() == TAKEN and spb(result) == (times + 1, aes.SHELL_PD)


def test_the_running_process_takes_its_own_again_and_leaves_the_process_queued_on_it():
    """The lock PD0's with the SCREEN MANAGER queued on it (`waited_on`: its EVB on the lock's wait list, PD0 running
    again): taken a second time, and the wait list is not tak_flag's to touch — the waiter still queued, by the same
    EVB. (A twin that cleared or rewrote SPB_WAIT is red HERE: every other state's list is empty.)"""
    pokes = wm_update.waited_on()
    waiting = case.long_in(make_image(pokes), WIND_SPB + SPB_WAIT)
    assert waiting and wm_update.lock_waiter(make_image(pokes)) == aes.SCREEN_MANAGER_PD, "the premise: a waiter queued"
    result = tak_flag(pokes)
    assert result.answer() == TAKEN and spb(result) == (2, aes.SHELL_PD)
    assert result.long(WIND_SPB + SPB_WAIT) == waiting


@THROUGH
def test_another_process_s_semaphore_is_refused_and_the_count_taken_back(through_line_f):
    result = tak_flag(held_by_another(), through_line_f=through_line_f)
    assert result.answer() == REFUSED and spb(result) == (1, aes.SHELL_PD)


def test_a_refusal_leaves_the_owner_s_high_word_in_d0():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the owner, staged with a top byte: no ROM run stores one). The
    refusal clears D0's WORD over the owner it loaded: with an owner whose high word is not zero, D0 is that high
    word over a zero. The answer compared is the word."""
    tagged = merge_pokes(held_by_another(), {WIND_SPB + SPB_OWNER: struct.pack(">I", aes.SHELL_PD | aes.BUS_TAG)})
    result = tak_flag(tagged)
    assert result.answer() == REFUSED and result.info["regs"]["d0"] == aes.BUS_TAG


def test_a_semaphore_released_once_too_often_is_refused():
    """The count -1 (the ROM's own END_UPDATE with nothing held): counted in it is 0, not the first hold's 1, and no
    process owns it — refused, the count back at -1."""
    result = tak_flag(wm_update.released_unbalanced())
    assert result.answer() == REFUSED and spb(result) == (-1, 0)


def test_the_owner_is_compared_as_the_long_it_is():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (`rlr`, staged with a top byte: no ROM run stores one). `cmp.l`: the
    lock held by PD0 through an untagged pointer, the running process named by a tagged one — the same PD on the bus,
    another long: refused."""
    tagged = merge_pokes(locked(), aes.field_pokes("AES", RLR=aes.SHELL_PD | aes.BUS_TAG))
    result = tak_flag(tagged)
    assert result.answer() == REFUSED and spb(result) == (1, aes.SHELL_PD)


def test_the_semaphore_is_put_on_the_bus():
    result = tak_flag(running(), WIND_SPB | aes.BUS_TAG)
    assert result.answer() == TAKEN and spb(result) == (1, aes.SHELL_PD)


# ---- the order of the reads and the stores: a semaphore laid over `rlr` -------------------------------------------------
OWNER_OVER_RLR = aes.AES_RLR - SPB_OWNER    # its owner IS rlr: the compare finds them equal whatever the count
COUNT_OVER_RLR = aes.AES_RLR                # its count is rlr's high word: counted in BEFORE rlr is compared, and stored
ONE_IN_THE_HIGH_WORD = 1 << 8 * aes.WORD_BYTES      # ...what counting one in adds to the long `rlr` is


def test_a_semaphore_whose_owner_is_rlr_itself_is_always_the_caller_s():
    result = tak_flag(held_by_another(), OWNER_OVER_RLR)
    assert result.answer() == TAKEN and result.long(aes.AES_RLR) == aes.SCREEN_MANAGER_PD


def test_the_count_is_stored_before_rlr_is_read():
    """The count over rlr's high word: the increment makes `rlr` another long before the owner is compared with it, and
    the owner stored is `rlr` as it stands THEN — over its own low word."""
    result = tak_flag(running(), COUNT_OVER_RLR)
    counted = aes.SHELL_PD + ONE_IN_THE_HIGH_WORD
    assert result.answer() == TAKEN
    assert result.long(COUNT_OVER_RLR + SPB_OWNER) == counted


# ---- Tier 3 ----------------------------------------------------------------------------------------------------------------
# Every arm, the refusal the dearest (two stores of the count): each a state of the lock the scheduler made.
ROWS = {"free: taken": running, "the caller's own: taken again": locked, "another process's: refused": held_by_another}
for _label, _machine in ROWS.items():
    aes.register(_label, TAK_FLAG, (WIND_SPB,), _machine())
