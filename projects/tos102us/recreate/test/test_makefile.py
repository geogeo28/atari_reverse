"""THE MAKEFILE'S OWN PREMISE, held: EVERY RECIPE THAT RUNS PYTHON OVER THE REGISTRY HAS THE CAPTURES IT READS AS
PREREQUISITES.

The registry (`test_boot_snapshot`, and through it every battery) is imported by the suites, by `bench/shipped_glue.py`,
by `test/derived.py` and by `bench/tier3.py`; since band 5 its import reads THREE captured machines — the boot
snapshot and the two pre-init ones (the screen manager's rows are registered from machines the ROM booted). A
target whose recipe imports it without those files among its prerequisites works in every tree that already has
them and dies in an empty one: `make gates` did, in `shipped-glue` (band 5 wave 1, slice C's gate) — and no suite
run can see that, since a suite only ever runs in a tree that was built.

So the rule is held from the makefiles' text, and held the CONSERVATIVE way round: every recipe that runs a Python
script or pytest must have the three, EXCEPT the tools named here that MAKE them — and those are held never to
import a test module."""
import re
from pathlib import Path

import pytest

from harness import project

RECREATE = Path(__file__).resolve().parent.parent
MAKEFILES = (RECREATE / "Makefile", project.KIT / "kit.mk")
CAPTURES = ("build/boot_ram.bin", "build/preinit.bin", "build/preinit_acc.bin")
# The scripts that MAKE the captures (and the stamp of the constants they read): run before any capture exists.
MAKE_THE_CAPTURES = {"tools/addrs.py", "tools/boot_snapshot.py", "tools/preinit_snapshot.py", "tools/accessory_disk.py"}
EVERY_PYTHON_TARGET = {"shipped-glue", "derived", "build/bench/tier3.txt", "test", "guarded", "gates"}

_DEFINITION = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\s*(?::=|\?=|=)\s*(.*)$")
_RULE = re.compile(r"^([^\t#:=][^:=]*):(?!=)([^#]*)")
_REFERENCE = re.compile(r"\$\((?:call\s+)?([A-Za-z_][A-Za-z_0-9]*)[^()]*\)")
_SCRIPT = re.compile(r"\.venv/bin/python\s+(?:-\S+\s+)*?([\w/]+\.py)")
_PYTEST = re.compile(r"\.venv/bin/python\s+-m\s+pytest")


def _joined(text):
    return text.replace("\\\n", " ").split("\n")


def _expanded(text, variables, depth=12):
    for _ in range(depth):
        text, found = _REFERENCE.subn(lambda match: variables.get(match.group(1), ""), text)
        if not found:
            break
    return text


def rules_of(texts):
    """`{target: (its prerequisites over every rule naming it, its recipe)}`, variables expanded, from makefile `texts`."""
    variables, rules, current = {}, {}, ()
    lines = [line for text in texts for line in _joined(text)]
    for line in lines:
        defined = _DEFINITION.match(line)
        if defined:
            variables[defined.group(1)] = defined.group(2)
    for line in lines:
        if line.startswith("\t"):
            for target in current:
                rules[target][1].append(_expanded(line, variables))
            continue
        ruled = None if _DEFINITION.match(line) else _RULE.match(line)
        if not ruled:
            current = () if line.strip() and not line.startswith("#") else current
            continue
        current = _expanded(ruled.group(1), variables).split()
        for target in current:
            rules.setdefault(target, (set(), []))[0].update(_expanded(ruled.group(2), variables).replace("|", " ").split())
    return rules


def without_the_captures(texts):
    """The targets whose recipe runs Python over the registry and lack a capture: `{target: the missing files}`."""
    lacking = {}
    for target, (prerequisites, recipe) in rules_of(texts).items():
        text = "\n".join(recipe)
        scripts = set(_SCRIPT.findall(text))
        if not (scripts - MAKE_THE_CAPTURES or _PYTEST.search(text)):
            continue
        missing = [capture for capture in CAPTURES if capture not in prerequisites]
        if missing:
            lacking[target] = missing
    return lacking


def _texts():
    return [path.read_text() for path in MAKEFILES]


def test_every_recipe_that_imports_the_registry_has_the_three_captures_as_prerequisites():
    assert without_the_captures(_texts()) == {}


def test_the_recipes_found_are_the_ones_there_are():
    """The parse is not vacuous: it finds the six targets that run Python over the registry, by name."""
    found = {target for target, (_needs, recipe) in rules_of(_texts()).items()
             if set(_SCRIPT.findall("\n".join(recipe))) - MAKE_THE_CAPTURES or _PYTEST.search("\n".join(recipe))}
    assert found == EVERY_PYTHON_TARGET


@pytest.mark.parametrize("target, rule, without", [
    ("shipped-glue", "shipped-glue: $(CAND) $(ORACLE) $(REGISTRY_READS)", "shipped-glue: $(CAND) $(SNAPSHOT)"),
    ("derived", "derived: $(CAND) $(ORACLE) $(REGISTRY_READS) $(BENCH_BIN)", "derived: $(CAND) $(ORACLE) $(SNAPSHOT) $(BENCH_BIN)"),
    ("build/bench/tier3.txt", "$(ORACLE) $(REGISTRY_READS) | derived", "$(ORACLE) $(SNAPSHOT) | derived"),
    ("gates", "test guarded gates: $(PREINIT) $(PREINIT_ACC)", "test guarded: $(PREINIT) $(PREINIT_ACC)"),
])
def test_a_registry_importer_without_the_captures_is_named(target, rule, without):
    """RED, each rule as it stood before the gate that failed (and the suites' own, were it dropped): named."""
    makefile, kit = _texts()
    assert makefile.count(rule) == 1
    lacking = without_the_captures([makefile.replace(rule, without), kit])
    assert target in lacking and "build/preinit_acc.bin" in lacking[target]


def test_the_tools_that_make_the_captures_import_no_test_module():
    """...AND THE EXCEPTION IS ONE: a capture tool that imported the registry would need the capture it makes. AT
    MODULE LEVEL — `preinit_snapshot.py`'s compare mode imports `aes_boot` inside its own function, a mode no
    recipe runs and one that reads the captures by design."""
    tests = {path.stem for path in (RECREATE / "test").glob("*.py")}
    for script in sorted(MAKE_THE_CAPTURES):
        imported = set(re.findall(r"^(?:import|from)\s+([A-Za-z_][\w]*)", (RECREATE / script).read_text(), re.M))
        assert not imported & tests, f"{script} imports {sorted(imported & tests)}"
