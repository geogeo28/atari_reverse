"""A REGISTERED ROW THAT SWITCHES IS HELD THREE WAYS (T6) — read off the batteries, not left to each one's habit:

  * its PREMISE, on the ROM's own run (`aes_switching.vet_the_premise`);
  * the SECOND DIFFERENTIAL OF THE REAL SWITCH on a blob, its whole run's cycles pinned (`vet_on_a_blob`);
  * WHAT THE TABLE PRICES of it, pinned (`vet_the_table_s_price`).

A battery registers a row through the one registrar (`aes_switching.register_row`) and then writes three tests over
it; nothing but habit made it write all three, for every row. HOW IT IS READ, off the batteries as imported (so a run
of one file, or of a `-k` selection, reads the same): a test function HOLDS a row one of the three ways when it calls
that vetter and one of its `parametrize` values NAMES the row — the row's label, its registered name, or a name it
is registered under. So a row added to a battery's table and left out of one of its three parametrised tests reds
here, by name.

ITS SCOPE, AND WHAT IS OWED. That reading holds a battery whose tests are parametrised BY THE ROW'S OWN LABEL OR NAME
— measured over the registry as it stands: 29 of 141 rows (this wave's three batteries, the tapes', the switch's
lifted rows). The other 112 are held by tests keyed otherwise (a scenario's key, a wake's name, a session's), which
no static reading ties to a row. THE GENERAL RULE — every registered row, whatever its battery's keys — needs the
vetters themselves to note what they held and the suite to sum it across its workers (`conftest.py`'s end-of-run
hook): OWED, reported, not done here (a shared hook, and a rule that can only be asked of a whole-suite run). Until
then this file holds the batteries it names, and a battery added to BATTERIES is held from the day it is.
"""
import inspect
import sys

import pytest

import test_aes_all_run
import test_aes_deskleaf
import test_aes_deskmem
import aes_event
import aes_switching as switching

VETTERS = ("vet_the_premise", "vet_on_a_blob", "vet_the_table_s_price")
BATTERIES = (test_aes_all_run, test_aes_deskleaf, test_aes_deskmem)


def _names_of(registered_as, held):
    """What a test's parameter may call the registered row: its label, its own name, the name it is registered under."""
    return {held.row.label, switching.row_name(held.row), registered_as}


def _vetters_called_by(function):
    source = inspect.getsource(function)
    return {vetter for vetter in VETTERS if f"{vetter}(" in source}


def _strings_in(value):
    """Every string in a parametrize argument: a value, a tuple of values, a `pytest.param`'s, a mapping's keys."""
    if isinstance(value, str):
        yield value
    elif hasattr(value, "values") and not isinstance(value, dict):      # a `pytest.param`
        yield from _strings_in(value.values)
    elif isinstance(value, (tuple, list, set, frozenset, dict)) or hasattr(value, "__iter__"):
        for each in value:
            yield from _strings_in(each)


def _parametrized_over(function):
    marks = [mark for mark in getattr(function, "pytestmark", ()) if mark.name == "parametrize"]
    return {string for mark in marks for string in _strings_in(mark.args[1])}


def held_by_the_batteries():
    """`{vetter: every string a test function that calls it is parametrized over}`, over every test module imported."""
    held = {vetter: set() for vetter in VETTERS}
    for name, module in list(sys.modules.items()):
        if not name.startswith("test_"):
            continue
        for function in (value for key, value in vars(module).items() if key.startswith("test_") and inspect.isfunction(value)):
            for vetter in _vetters_called_by(function):
                held[vetter] |= _parametrized_over(function)
    return held


def _registered_by(module):
    """The registered names of the rows `module` registers: every `SwitchingRow` in a dict of its own."""
    rows = [value for table in vars(module).values() if isinstance(table, dict) for value in table.values()
            if isinstance(value, switching.SwitchingRow)]
    return {switching.row_name(row) for row in rows}


@pytest.mark.parametrize("battery", BATTERIES, ids=lambda module: module.__name__)
def test_every_row_a_battery_registers_has_a_premise_a_blob_and_a_table_pin(battery):
    held, registered = held_by_the_batteries(), _registered_by(battery)
    assert registered and registered <= set(aes_event.SWITCHING_ROWS), f"{battery.__name__}: rows it tables and never registers"
    missing = sorted((name, vetter) for name in registered for vetter in VETTERS
                     if not _names_of(name, aes_event.SWITCHING_ROWS[name]) & held[vetter])
    assert not missing, "\n".join(f"{name}: no test holds it by {vetter}" for name, vetter in missing)


def test_a_row_left_out_of_one_of_the_three_is_named(monkeypatch):
    """THE RED: a row a battery tables — in a table of its own that no test is parametrised over — and vets by
    nothing is refused by name."""
    unheld = switching.SwitchingRow("a row no test is parametrised over", test_aes_deskleaf.DESK_RSRC_FREE, (), None, {})
    name = switching.row_name(unheld)
    monkeypatch.setattr(test_aes_deskleaf, "ROWS_ADDED_LATER", {unheld.label: unheld}, raising=False)
    monkeypatch.setitem(aes_event.SWITCHING_ROWS, name, switching.Registered(unheld, {}, (), None, (), None, {}))
    with pytest.raises(AssertionError, match="no test holds it by vet_on_a_blob"):
        test_every_row_a_battery_registers_has_a_premise_a_blob_and_a_table_pin(test_aes_deskleaf)
