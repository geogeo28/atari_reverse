"""`project._bool_flag()` is the last line of defence in front of every safety waiver.

The waiver flags in a project's ``project.toml`` switch off a check that exists to stop a
differential from coming back green while proving nothing. Every non-empty string is truthy in
Python, so a quoted ``tos_malloc_unused = "false"`` — a plausible hand-edit — would *enable* the very
waiver it was written to disable, silently. ``_bool_flag`` refuses anything that is not a real TOML
boolean instead of interpreting it, and these cases pin that.

Every case runs against BOTH flags. One is not a stand-in for the other: they waive different checks
(the modeled Malloc heap; the harness-poked input block) and are read by separate lines of
``project.load``, so a flag added to the config namespace but wired past ``_bool_flag`` would be
invisible to a suite that only ever tested its sibling.

No project binding is needed: the helper is pure, so it is tested directly on a dict.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # reverse/tools, so `recreate_kit` imports
from recreate_kit import project   # noqa: E402  (only importable after the path insert)

RECREATE_DIR = Path("/nowhere/projects/example/recreate")   # only ever formatted into the message

# Every waiver flag project.load() reads. A flag added there and not added here is caught by
# test_every_waiver_flag_is_covered below.
FLAGS = ("tos_malloc_unused", "tos_poked_input_unused")

# Values that are NOT TOML booleans. The two quoted ones are the dangerous pair: both are truthy in
# Python, so "false" would read as an enabled waiver. 1/0 are rejected too — `isinstance(1, bool)`
# is False, and silently accepting int truthiness would re-open the same door for `0`.
NON_BOOLEANS = ("false", "true", 1, 0)


def test_every_waiver_flag_is_covered():
    """FLAGS must list every ``_bool_flag`` key in project.py, or a new waiver ships untested.

    Two assertions, because the name scan is syntax-bound: it reads the quoted key out of each call,
    so a keyword or oddly-wrapped call could hide from it. Counting the calls independently catches
    that — a `_bool_flag(` this file cannot attribute to a flag still moves the total.
    """
    source = Path(project.__file__).read_text()
    assert "def _bool_flag(" in source, "the helper was renamed; this whole case is looking at air"
    definitions = 1                     # `def _bool_flag(` is an occurrence but not a call
    calls = source.count("_bool_flag(") - definitions
    assert calls == len(FLAGS), (
        f"project.py makes {calls} _bool_flag calls but this file tests {len(FLAGS)} flags")
    named = set(re.findall(r"_bool_flag\(\s*raw\s*,\s*(?:key\s*=\s*)?[\"'](\w+)[\"']", source))
    assert named == set(FLAGS), (
        f"project.load() reads {sorted(named)} through _bool_flag but this file tests "
        f"{sorted(FLAGS)} — add the new waiver flag to FLAGS")


@pytest.mark.parametrize("flag", FLAGS)
def test_absent_flag_is_false(flag):
    assert project._bool_flag({}, flag, RECREATE_DIR) is False


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", (True, False))
def test_a_real_toml_boolean_passes_through(flag, value):
    assert project._bool_flag({flag: value}, flag, RECREATE_DIR) is value


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", NON_BOOLEANS)
def test_a_non_boolean_is_refused_and_names_the_file(flag, value):
    with pytest.raises(TypeError) as excinfo:
        project._bool_flag({flag: value}, flag, RECREATE_DIR)
    message = str(excinfo.value)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in message, (
        "the diagnostic must name the file to edit, not just the flag")
    assert flag in message
