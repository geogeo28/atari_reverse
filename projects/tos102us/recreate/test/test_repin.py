"""`tools/repin.py` — the re-pin of the rows that switch from a recorded run (`tools/pin_recorder.py`): what it
rewrites, and WHAT IT REFUSES (a ROM-side count that moved; a pair two rows move two ways; a pair neither the
recording file nor its imports spell; a pair spelt for more rows than recorded its move). Over crafted records and a
crafted test file: nothing of the tree is read."""
import json
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


# ---- THE SCREEN MANAGER'S TURNS: one data file, a line a row's blob (`test/aes_turns_pinned.py`; FLIP 4) ---------------------
THE_TURNS_TEXT = '''"""A docstring the tool leaves alone."""
PINNED = {
    "aes_a_routine, a wait, blocked and woken": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
}
'''


def _turn(row, blob, held, measured):
    return {"kind": repin.TURN, "who": [row, blob], "old": held, "new": measured, "file": A_FILE.name}


def test_a_turn_s_record_rewrites_its_row_s_line_for_its_blob_and_adds_a_row_s():
    """A TURN'S RECORD IS ITS ROW'S LINE FOR ITS BLOB — written from the run: OUR member and our thunks' moved, a row
    the file did not hold added (a quote in its name spelt) — and every other line, and everything outside the
    table, as it was; no record of that kind is a pair's move or a hand's."""
    quoted = 'aes_a_routine, the screen manager\'s "menu"'
    records = [_turn(A_ROW, "bench_shipped", [[175400, 278034, 12148]], [[175000, 278034, 12000]]),
               _turn(quoted, "bench", [], [[10, 20, 0], [30, 40, 2]])]
    text, written, refused = repin.turns_repinned(records, THE_TURNS_TEXT)
    assert (written, refused) == (2, []) and text.startswith('"""A docstring the tool leaves alone."""\nPINNED = {\n') and text.endswith("}\n")
    held = {}
    exec(text, held)                                    # the file is Python: a table
    assert held["PINNED"] == {A_ROW: {"bench": ((198044, 278034, 1376),), "bench_shipped": ((175000, 278034, 12000),)},
                              quoted: {"bench": ((10, 20, 0), (30, 40, 2))}}
    assert repin.turns_repinned([], text) == (text, 0, []), "written twice, the file is the file"
    assert repin.moves_of(records) == ([], [])


def test_a_turn_whose_rom_side_count_moved_is_refused_and_its_line_left():
    """...AND THE ROM'S MEMBER OF A TURN IS THE ROM'S RUN'S: a record in which it moved — or in which the run makes
    another number of turns than the line holds — is refused by the row's name, its line left as it was."""
    for measured in ([[175400, 278040, 12148]], [[175400, 278034, 12148], [1, 2, 0]], []):
        text, written, refused = repin.turns_repinned([_turn(A_ROW, "bench_shipped", [[175400, 278034, 12148]], measured)], THE_TURNS_TEXT)
        assert (text, written) == (THE_TURNS_TEXT, 0) and "THE ROM'S OWN COUNT MOVED" in refused[0] and A_ROW in refused[0]


def test_a_turn_s_record_is_held_to_what_the_file_holds_not_to_what_it_says_was_held():
    """A RECORD MADE AGAINST ANOTHER FILE WRITES NOTHING (the review's three crafted cases, FLIP 4 pass 2): one whose
    `old` is not the file's line — its ROM member "unmoved" between its own two halves, and another number than the
    file's — is refused, the file's ROM member kept; one with no `old` over a row the file holds is refused whatever
    it brings; one with an `old` for a row the file does not hold is refused too. And a record that changes nothing
    is no line written."""
    held = [[175400, 278034, 12148]]
    for record, why in ((_turn(A_ROW, "bench_shipped", [[170000, 278036, 12148]], [[170001, 278036, 12148]]), "NOT MADE AGAINST THIS FILE"),
                        (_turn(A_ROW, "bench_shipped", [], [[175400, 999999, 12148]]), "NOT MADE AGAINST THIS FILE"),
                        (_turn("aes_a_routine, another row", "bench", [[1, 2, 3]], [[1, 2, 4]]), "the file holds no line for it"),
                        (_turn(A_ROW, "bench_shipped", held, [[175400, 278036, 12148]]), "THE ROM'S OWN COUNT MOVED")):
        text, written, refused = repin.turns_repinned([record], THE_TURNS_TEXT)
        assert (text, written) == (THE_TURNS_TEXT, 0) and len(refused) == 1 and why in refused[0], refused
    assert repin.turns_repinned([_turn(A_ROW, "bench_shipped", held, held)], THE_TURNS_TEXT) == (THE_TURNS_TEXT, 0, [])


# ---- THE ACCESSORIES' TURNS: the same shape, a data file of their own (`test/aes_accessory_turns_pinned.py`; the narrow door flip) ----
def _accessory_turn(row, blob, held, measured):
    return {"kind": repin.ACCESSORY_TURN, "who": [row, blob], "old": held, "new": measured, "file": A_FILE.name}


def _a_tree(tmp_path, records, files):
    """A crafted `recreate/` under `tmp_path` — `files`: `{name: text}` in its `test/` — and the recorder's file."""
    (tmp_path / "test").mkdir()
    for name, text in files.items():
        (tmp_path / "test" / name).write_text(text)
    record = tmp_path / "pins.jsonl"
    record.write_text("".join(json.dumps(each) + "\n" for each in records))
    return [str(record), str(tmp_path)]


def test_an_accessory_turn_s_record_is_its_own_data_file_s_and_no_other_kind_s(tmp_path, capsys):
    """THE NEW KIND, THROUGH `main`'s LOOP: an accessory turn's record rewrites the accessories' file and leaves the
    screen manager's — which holds the same row — as it was; a record of the OTHER kind over the same row rewrites
    the other file alone. Our member and our thunks' moved; the ROM's stood."""
    moved = [[175000, 278034, 12000]]
    arguments = _a_tree(tmp_path, [_accessory_turn(A_ROW, "bench_shipped", [[175400, 278034, 12148]], moved)],
                        {repin.TURNS_FILE: THE_TURNS_TEXT, repin.ACCESSORY_TURNS_FILE: THE_TURNS_TEXT})
    assert repin.main([*arguments, "--apply"]) == 0 and "1 line(s) of turns written" in capsys.readouterr().out
    assert (tmp_path / "test" / repin.TURNS_FILE).read_text() == THE_TURNS_TEXT
    held = {}
    exec((tmp_path / "test" / repin.ACCESSORY_TURNS_FILE).read_text(), held)
    assert held["PINNED"][A_ROW] == {"bench": ((198044, 278034, 1376),), "bench_shipped": ((175000, 278034, 12000),)}
    assert repin.turns_repinned([_turn(A_ROW, "bench_shipped", [[175400, 278034, 12148]], moved)], THE_TURNS_TEXT,
                                repin.ACCESSORY_TURN) == (THE_TURNS_TEXT, 0, []), "a record is its own kind's file's"


def test_an_accessory_turn_whose_rom_side_count_moved_fails_the_run_and_writes_nothing(tmp_path, capsys):
    arguments = _a_tree(tmp_path, [_accessory_turn(A_ROW, "bench_shipped", [[175400, 278034, 12148]], [[175400, 278035, 12148]])],
                        {repin.ACCESSORY_TURNS_FILE: THE_TURNS_TEXT})
    assert repin.main([*arguments, "--apply"]) == 1
    assert "THE ROM'S OWN COUNT MOVED in its turns (accessory turn)" in capsys.readouterr().out
    assert (tmp_path / "test" / repin.ACCESSORY_TURNS_FILE).read_text() == THE_TURNS_TEXT


@pytest.mark.parametrize("kind", repin.TURNS_FILES)
def test_a_turn_s_record_whose_data_file_is_missing_is_refused_by_name_and_fails_the_run(kind, tmp_path, capsys):
    """A RECORD IS NEVER DROPPED IN SILENCE (the fix pass, B-F5: with the accessories' file moved away a valid record
    printed "0 written, 0 refused" and ended 0): refused by the row's name, the run non-zero — and a tree that has
    neither the file nor a record of its kind is no failure."""
    other = next(name for each, name in repin.TURNS_FILES.items() if each != kind)
    record = {"kind": kind, "who": [A_ROW, "bench_shipped"], "old": [[175400, 278034, 12148]], "new": [[175000, 278034, 12000]],
              "file": A_FILE.name}
    arguments = _a_tree(tmp_path, [record], {other: THE_TURNS_TEXT})
    assert repin.main([*arguments, "--apply"]) == 1
    said = capsys.readouterr().out
    assert f"REFUSED: {A_ROW} on bench_shipped: {repin.THE_DATA_FILE_IS_MISSING}" in said and repin.TURNS_FILES[kind] in said
    assert "0 line(s) of turns written" in said and "1 refused" in said
    assert (tmp_path / "test" / other).read_text() == THE_TURNS_TEXT
    (tmp_path / "pins.jsonl").write_text("")
    assert repin.main(arguments) == 0
