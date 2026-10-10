"""A PYTEST PLUGIN THAT RECORDS EVERY CYCLE PIN A SWITCHING ROW ASSERTS, with what the run measured — the first half
of a RE-PIN (`tools/repin.py` is the second; recreate/README.md, "Re-pinning the rows that switch").

    PINREC_OUT=$PWD/build/pins.jsonl PYTHONPATH=../../../tools:tools .venv/bin/python -m pytest -q -p pin_recorder -n auto test

The suite's own assertions are untouched: a moved pin still FAILS, by its name. What the plugin adds is one JSON line
per moved pin — the whole run's cycles on a blob (`aes_switching.vet_on_a_blob`) and the table's price of a row
(`vet_the_table_s_price`), each with the pair the test holds — so that a build change that moves hundreds of rows
(a compiler flag, a frame) is re-pinned FROM THE RUN, never by hand and never by loosening. A pin asserted by other
code than those two helpers (`test_aes_evdisp_model.py`'s yield and wait, `test_aes_fs_input_woken.py`'s slices) is
not recorded: its own red names it. A row whose run itself is REFUSED (an assertion of the measurement, not of the
pin) is recorded as that, with the refusal's words.
"""
import fcntl
import json
import os

OUT = os.environ.get("PINREC_OUT")
WHOLE, PRICED, REFUSED = "whole", "priced", "refused"
A_REFUSAL_S_WORDS = 200


def _the_test_s_file():
    """The file of the test that is running (pytest's own word for it): where its pins are looked for first."""
    return os.environ.get("PYTEST_CURRENT_TEST", "").partition("::")[0].rpartition("/")[2]


def _record(kind, who, held, measured):
    """One line of the record: the pin `held` and what the run `measured` — nothing where they agree."""
    if not OUT or held == measured:
        return
    with open(OUT, "a") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(json.dumps({"kind": kind, "who": who, "old": held, "new": measured, "file": _the_test_s_file()}) + "\n")


def _recording_whole_runs(switching):
    """`vet_on_a_blob`, its verdict untouched, the whole run's cycles on the blob recorded after it."""
    vet, measured_on, row_name = switching.vet_on_a_blob, switching.measured_on, switching.row_name

    def vet_on_a_blob(blob, row, premise, windows, whole):
        try:
            return vet(blob, row, premise, windows, whole)
        finally:
            directory = blob.elf.parent.name
            try:
                measured, _watch, _foreign = measured_on(blob, row)
                _record(WHOLE, [row_name(row), directory], list(whole[directory]), [measured.original_net, measured.recreate_net])
            except AssertionError as refusal:
                _record(REFUSED, row_name(row), None, str(refusal)[:A_REFUSAL_S_WORDS])
    return vet_on_a_blob


def _recording_prices(switching):
    """`vet_the_table_s_price`, its verdict untouched, the table's price of the row recorded after it."""
    vet, priced_by, row_name = switching.vet_the_table_s_price, switching.priced_by_the_table, switching.row_name

    def vet_the_table_s_price(row, priced):
        try:
            return vet(row, priced)
        finally:
            try:
                _measured, read = priced_by(row)
                _record(PRICED, row_name(row), list(priced), list(read))
            except AssertionError as refusal:
                _record(REFUSED, row_name(row), None, str(refusal)[:A_REFUSAL_S_WORDS])
    return vet_the_table_s_price


def pytest_configure(config):
    del config
    import aes_switching

    aes_switching.vet_on_a_blob = _recording_whole_runs(aes_switching)
    aes_switching.vet_the_table_s_price = _recording_prices(aes_switching)
