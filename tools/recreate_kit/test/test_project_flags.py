"""`project._bool_flag()` is the last line of defence in front of a safety waiver.

The waiver flags in a project's ``project.toml`` (today: ``tos_malloc_unused``) switch off a check
that exists to stop a differential from coming back green while proving nothing. Every non-empty
string is truthy in Python, so a quoted ``tos_malloc_unused = "false"`` — a plausible hand-edit —
would *enable* the very waiver it was written to disable, silently. ``_bool_flag`` refuses anything
that is not a real TOML boolean instead of interpreting it, and these cases pin that.

No project binding is needed: the helper is pure, so it is tested directly on a dict.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # reverse/tools, so `recreate_kit` imports
from recreate_kit import project   # noqa: E402  (only importable after the path insert)

RECREATE_DIR = Path("/nowhere/projects/example/recreate")   # only ever formatted into the message
FLAG = "tos_malloc_unused"

# Values that are NOT TOML booleans. The two quoted ones are the dangerous pair: both are truthy in
# Python, so "false" would read as an enabled waiver. 1/0 are rejected too — `isinstance(1, bool)`
# is False, and silently accepting int truthiness would re-open the same door for `0`.
NON_BOOLEANS = ("false", "true", 1, 0)


def test_absent_flag_is_false():
    assert project._bool_flag({}, FLAG, RECREATE_DIR) is False


@pytest.mark.parametrize("value", (True, False))
def test_a_real_toml_boolean_passes_through(value):
    assert project._bool_flag({FLAG: value}, FLAG, RECREATE_DIR) is value


@pytest.mark.parametrize("value", NON_BOOLEANS)
def test_a_non_boolean_is_refused_and_names_the_file(value):
    with pytest.raises(TypeError) as excinfo:
        project._bool_flag({FLAG: value}, FLAG, RECREATE_DIR)
    message = str(excinfo.value)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in message, (
        "the diagnostic must name the file to edit, not just the flag")
    assert FLAG in message
