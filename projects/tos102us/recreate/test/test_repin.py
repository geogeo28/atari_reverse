"""`tools/repin.py` — the re-pin of the rows that switch from a recorded run (`tools/pin_recorder.py`): what it
rewrites, and WHAT IT REFUSES (a ROM-side count that moved; a pair two rows move two ways; a pair neither the
recording file nor its imports spell; a pair spelt for more rows than recorded its move). Over crafted records and a
crafted test file: nothing of the tree is read."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import repin                                              # noqa: E402

A_FILE = pathlib.Path("test_a_battery.py")
A_ROW, ANOTHER_ROW = "aes_a_routine, a wait, blocked and woken", "aes_a_routine, a second wait"
THE_FILE_S_TEXT = '''WHOLE_RUN = {
    "a wait, blocked and woken": {BENCH: (14024, 11526), SHIPPED: (14024, 11646)},
    "a second wait": {BENCH: (14024, 11526), SHIPPED: (9000, 8000)},
}
PRICED = {
    "a wait, blocked and woken": Priced((4608, 7262), (4174, 6512), 2, (0, 0, 0)),   # 0.63 / 0.64
}
'''


def _whole(row, blob, held, measured, file=A_FILE.name):
    return {"kind": repin.WHOLE, "who": [row, blob], "old": list(held), "new": list(measured), "file": file}


def _priced(row, held, measured, file=A_FILE.name):
    return {"kind": repin.PRICED, "who": row, "old": held, "new": measured, "file": file}


def test_our_member_of_a_recorded_pair_is_rewritten_and_the_ratio_its_line_quotes_made_again():
    records = [_whole(A_ROW, "bench_shipped", (14024, 11646), (14024, 11582)),
               _priced(A_ROW, [[4608, 7262], [4174, 6512], 2, [0, 0, 0]], [[4544, 7262], [4110, 6512], 2, [0, 0, 0]])]
    outcome = repin.repinned(records, {A_FILE: THE_FILE_S_TEXT})
    text = outcome.texts[A_FILE]
    assert not outcome.refused and not outcome.by_hand and outcome.rewritten == {A_FILE.name: 3}      # a whole run's pair, a price's two
    assert "SHIPPED: (14024, 11582)" in text and "(14024, 11526)" in text, "the pairs it did not record are as they were"
    assert "Priced((4544, 7262), (4110, 6512), 2, (0, 0, 0)),   # 0.63 / 0.63" in text


@pytest.mark.parametrize("record", (
    _whole(A_ROW, "bench_shipped", (14024, 11646), (14030, 11646)),
    _priced(A_ROW, [[4608, 7262], [4174, 6512], 2, [0, 0, 0]], [[4608, 7270], [4174, 6512], 2, [0, 0, 0]]),
), ids=("a whole run's ROM count", "a price's ROM count"))
def test_a_record_whose_rom_side_count_moved_is_refused_by_the_row_s_name_and_nothing_is_written(record):
    """THE REGRESSION A RE-PIN MUST NEVER ABSORB: the ROM's own count of a row is the row's machine and deliveries."""
    outcome = repin.repinned([record], {A_FILE: THE_FILE_S_TEXT})
    (why, _move), = outcome.refused
    assert "THE ROM'S OWN COUNT MOVED" in why and A_ROW in why
    assert outcome.texts[A_FILE] == THE_FILE_S_TEXT and not outcome.rewritten
    with pytest.raises(repin.RomSideMoved, match="no re-pin absorbs that"):
        repin.vet(repin.moves_of([record])[0][0])


def test_a_pair_two_rows_share_is_rewritten_only_when_both_recorded_its_move():
    """THE CRAFTED FILE'S OWN SHAPE: two rows spell `(14024, 11526)`. ONE of them moving is refused, by both rows'
    pair and the count — the other line is a row nobody recorded, and a blind replace would re-pin it; BOTH moving
    the same way is two spellings for two recorders, and both are rewritten."""
    one = repin.repinned([_whole(A_ROW, "bench", (14024, 11526), (14024, 11462))], {A_FILE: THE_FILE_S_TEXT})
    (why, _move), = one.refused
    assert "spelt 2 times" in why and "1 row(s) recorded its move" in why and A_ROW in why
    assert one.texts[A_FILE] == THE_FILE_S_TEXT and not one.rewritten
    both = repin.repinned([_whole(A_ROW, "bench", (14024, 11526), (14024, 11462)),
                           _whole(ANOTHER_ROW, "bench", (14024, 11526), (14024, 11462))], {A_FILE: THE_FILE_S_TEXT})
    assert not both.refused and both.rewritten == {A_FILE.name: 2} and "(14024, 11526)" not in both.texts[A_FILE]


def test_a_pair_two_rows_move_two_ways_is_refused():
    records = [_whole(A_ROW, "bench", (14024, 11526), (14024, 11462)), _whole(ANOTHER_ROW, "bench", (14024, 11526), (14024, 11400))]
    outcome = repin.repinned(records, {A_FILE: THE_FILE_S_TEXT})
    assert ["moved two ways" in why for why, _move in outcome.refused] == [True]
    assert outcome.texts[A_FILE] == THE_FILE_S_TEXT


def test_a_pair_is_rewritten_in_the_recording_test_s_file_or_a_test_module_it_imports_and_nowhere_else():
    """A file that spells the same pair for a row no test of it recorded is left alone; a pin its recording test
    imports from its own battery is found there; one neither spells is refused, by the row."""
    registry, elsewhere = pathlib.Path("test_a_registry.py"), pathlib.Path("test_another_battery.py")
    texts = {A_FILE: THE_FILE_S_TEXT, registry: "import test_a_battery\n", elsewhere: "X = (9000, 8000)\n"}
    imported = repin.repinned([_whole(ANOTHER_ROW, "bench_shipped", (9000, 8000), (9000, 7900), registry.name)], texts)
    assert imported.rewritten == {A_FILE.name: 1} and imported.texts[elsewhere] == texts[elsewhere]
    unspelt = repin.repinned([_whole(ANOTHER_ROW, "bench_shipped", (9000, 8000), (9000, 7900), "test_a_third.py")], texts)
    (why, _move), = unspelt.refused
    assert "nor a test module it imports spells" in why and ANOTHER_ROW in why and unspelt.texts == texts


def test_a_price_whose_calls_or_windows_moved_is_for_a_hand():
    record = _priced(A_ROW, [[4608, 7262], [4174, 6512], 2, [0, 0, 0]], [[4608, 7262], [4174, 6512], 3, [0, 0, 0]])
    outcome = repin.repinned([record], {A_FILE: THE_FILE_S_TEXT})
    assert outcome.by_hand == [record] and not outcome.rewritten and not outcome.refused
