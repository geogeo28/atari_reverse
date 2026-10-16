"""THE CAPTURE'S VET (`tools/vet_snapshot.py`): what the Makefile asks before a fresh boot snapshot is kept.

It keeps the build's own snapshot (the suite's premise, `test_aes_takeover.py`'s first test, says that one is good), and
refuses one whose screen manager's live frames carry another start-up's residue — each of the two dead slots seen to
move in a real capture (snapflake, 2026-10-15): the QPB its main wait's ev_multi never writes, and the slot over its
parked `rte` frame.
"""
import pytest

from harness import BASE_IMAGE

import aes_takeover as takeover
import vet_snapshot                  # tools/: on the path through harness

EV_MULTI_QPB_FROM_PARKED = 0x38      # $a85a - $a822: ev_multi's -8(a6) QPB, under the frame at $a862
OVER_THE_RTE_FRAME = 6               # $a828 - $a822: the slot above the SR and PC switchto's `rte` pops


def test_the_build_s_snapshot_is_kept():
    assert vet_snapshot.screen_manager_as_booted(bytes(BASE_IMAGE))


@pytest.mark.parametrize("past_parked", (EV_MULTI_QPB_FROM_PARKED, OVER_THE_RTE_FRAME))
def test_another_residue_in_a_live_dead_slot_is_refused(past_parked):
    image = bytearray(BASE_IMAGE)
    image[takeover.spans_of(image).parked + past_parked] ^= 0xff
    assert not vet_snapshot.screen_manager_as_booted(bytes(image))
