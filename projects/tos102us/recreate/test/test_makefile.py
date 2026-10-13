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
import a test module.

WHICH ONES IS DERIVED, NOT DECLARED (band 5 wave 4's fix pass): `aes_boot.CAPTURES_READ` as this module's own import
of the registry ends is what the import READ — so the day a row is registered from the seven-accessory machine, the
registry's import reads one more file and this battery says REGISTRY_READS lacks it. (It did for the DESKTOP.INF
machine the day slice B registered the build's own start-up over it: the fourth capture is among them since.)

AND THE SUITES' OWN PRE-INIT CAPTURES ARE FIVE: `test`, `guarded` and `gates` need every pre-init machine a test boots
from (the seven-accessory, the DESKTOP.INF and — band 6 wave 0 — the files ones too), each made from ITS OWN disk by
the capture tool, and `gates` holds the mask to them (`make preinit-twice`). A DISK WHOSE CONTENT IS CUT OUT OF THE
ROM (the two that carry the ROM's own DESKTOP.INF) has the ROM image among its own rule's prerequisites."""
import re
from pathlib import Path

import pytest

from harness import project

import accessory_disk
import aes_boot
import preinit_snapshot
import test_boot_snapshot          # noqa: F401  (THE REGISTRY: what its import reads is read off `aes_boot` just below)

RECREATE = Path(__file__).resolve().parent.parent
MAKEFILES = (RECREATE / "Makefile", project.KIT / "kit.mk")
SNAPSHOT = "build/boot_ram.bin"
# Read HERE, at collection: every test module is imported before any test runs, and no module reads a capture at
# its import but through the registry — so this is what the registry's import read (a module that does would add its
# file here, and redden the test below: the conservative way round).
READ_BY_THE_REGISTRY_S_IMPORT = tuple(sorted({str(path.relative_to(RECREATE)) for path in aes_boot.CAPTURES_READ}))
CAPTURES = (SNAPSHOT, *READ_BY_THE_REGISTRY_S_IMPORT)
# EVERY PRE-INIT MACHINE A SUITE BOOTS FROM: `{its file: the disk it is captured with, None for the blank one}`.
PREINIT_CAPTURES = {str(path().relative_to(RECREATE)): disk for path, disk in (
    (preinit_snapshot.preinit_path, None), (preinit_snapshot.accessory_path, "build/acc/ACCDISK.ST"),
    (preinit_snapshot.seven_accessory_path, "build/acc/ACC7DISK.ST"), (preinit_snapshot.inf_path, "build/acc/INFDISK.ST"),
    # (band 6 wave 0, slice H: THE FIFTH — the files disk's, `make preinit-files`)
    (accessory_disk.files_capture_path, "build/acc/FILESDISK.ST"))}
DISKS_CUT_FROM_THE_ROM = ("build/acc/INFDISK.ST", "build/acc/FILESDISK.ST")    # each carries the ROM's default DESKTOP.INF
THE_SUITES = ("test", "guarded", "gates")
CAPTURE_TOOL, ROM_IMAGE = "tools/preinit_snapshot.py", "../../../tools/hatari/TOS102US.img"
TWICE = "preinit-twice"
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


def not_among_the_registry_s_reads(read, texts):
    """The captures of `read` (what an import of the registry read) that the makefiles' REGISTRY_READS does not name."""
    named = set(_expanded("$(REGISTRY_READS)", {name: value for line in (line for text in texts for line in _joined(text))
                                                 for name, value in _DEFINITION.findall(line)}).split())
    return sorted(set(read) - named)


def test_what_the_registry_s_import_reads_is_what_registry_reads_names():
    """DERIVED: the captures this process read while the registry was imported are the Makefile's REGISTRY_READS, with
    the snapshot — no fewer and no more: the two pre-init machines the screen manager's rows are registered from, AND
    THE DESKTOP.INF ONE since band 5 wave 4's slice B registered rows made of it (the build's own start-up: the
    reader's file arm). RED, on the list a registered row of the seven-accessory machine would make: that capture is
    named as lacking; and each of the three, dropped from the rule, is named too."""
    assert READ_BY_THE_REGISTRY_S_IMPORT == ("build/preinit.bin", "build/preinit_acc.bin", "build/preinit_inf.bin")
    assert not_among_the_registry_s_reads(CAPTURES, _texts()) == []
    seven = str(preinit_snapshot.seven_accessory_path().relative_to(RECREATE))
    assert not_among_the_registry_s_reads((*CAPTURES, seven), _texts()) == [seven]
    makefile, kit = _texts()
    rule = "REGISTRY_READS := $(SNAPSHOT) $(PREINIT) $(PREINIT_ACC) $(PREINIT_INF)"
    assert makefile.count(rule) == 1
    for dropped, lacking in ((" $(PREINIT_ACC)", "build/preinit_acc.bin"), (" $(PREINIT_INF)", "build/preinit_inf.bin")):
        assert not_among_the_registry_s_reads(CAPTURES, [makefile.replace(rule, rule.replace(dropped, "")), kit]) == [lacking]


def suites_without_a_capture(texts):
    """`{suite target: the pre-init captures it lacks}`, and `{capture: what its own rule lacks}` — its disk, the
    capture tool, the ROM image — over makefile `texts`."""
    rules = rules_of(texts)
    lacking = {suite: sorted(set(PREINIT_CAPTURES) - rules[suite][0]) for suite in THE_SUITES}
    for capture, disk in PREINIT_CAPTURES.items():
        needs, recipe = rules.get(capture, (set(), []))
        wanted = {CAPTURE_TOOL, ROM_IMAGE} | ({disk} if disk else set())
        asked = [line for line in (line.replace("$@", capture) for line in recipe) if CAPTURE_TOOL in line and f"--out {capture}" in line]
        said = bool(asked) and all((f"--disk {disk}" in line) if disk else ("--disk" not in line) for line in asked)
        lacking[capture] = sorted(wanted - needs) + ([] if said else ["a recipe that captures it from its own disk"])
    for disk in DISKS_CUT_FROM_THE_ROM:
        if ROM_IMAGE not in rules.get(disk, (set(), []))[0]:
            lacking[disk] = [ROM_IMAGE]
    return {target: missing for target, missing in lacking.items() if missing}


def test_the_suites_have_every_pre_init_capture_and_each_capture_its_own_disk():
    """THE FIVE PRE-INIT MACHINES: `test`, `guarded` and `gates` have each as a prerequisite, and each is made by the
    capture tool from ITS OWN disk, the ROM image and the tool among its prerequisites — so a changed disk captures
    again; a disk cut out of the ROM is made again by a changed ROM image. And `gates` holds the mask to all five:
    `preinit-twice` among its prerequisites, its recipe `--twice` over each disk, into a directory that is none of
    the captures'."""
    assert suites_without_a_capture(_texts()) == {}
    assert set(DISKS_CUT_FROM_THE_ROM) <= set(PREINIT_CAPTURES.values())
    needs, recipe = rules_of(_texts())[TWICE]
    assert TWICE in rules_of(_texts())["gates"][0] and TWICE not in rules_of(_texts())["test"][0]
    assert {disk for disk in PREINIT_CAPTURES.values() if disk} <= needs
    twice = [line for line in recipe if CAPTURE_TOOL in line]
    assert len(twice) == len(PREINIT_CAPTURES) and all("--twice" in line for line in twice)
    assert sorted(disk for line in twice for disk in re.findall(r"--disk (\S+)", line)) == sorted(filter(None, PREINIT_CAPTURES.values()))
    assert not any(f"--out {capture}" in line for line in twice for capture in PREINIT_CAPTURES)


@pytest.mark.parametrize("named, rule, without", [
    ("gates", "test guarded gates: $(PREINIT) $(PREINIT_ACC) $(PREINIT_ACC7) $(PREINIT_INF)",
     "test guarded gates: $(PREINIT) $(PREINIT_ACC) $(PREINIT_ACC7)"),
    ("test", "test guarded gates: $(PREINIT) $(PREINIT_ACC) $(PREINIT_ACC7) $(PREINIT_INF)",
     "test guarded gates: $(PREINIT) $(PREINIT_ACC) $(PREINIT_INF)"),
    ("build/preinit_inf.bin", "$(PREINIT_INF): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(INF_DISK)",
     "$(PREINIT_INF): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE)"),
    ("build/preinit_acc7.bin", "$(PREINIT_ACC7): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(ACC7_DISK)",
     "$(PREINIT_ACC7): $(PREINIT_INPUTS) $(ROM_IMAGE) $(ACC7_DISK)"),
    ("build/preinit_inf.bin", "--disk $(INF_DISK) --work build/preinit_inf_snapshot --out $@",
     "--disk $(ACC_DISK) --work build/preinit_inf_snapshot --out $@"),
    ("build/acc/FILESDISK.ST", "atari/mkprg.py include/gemdos/pexec_load.h $(ROM_IMAGE)\n\t$(PY) tools/accessory_disk.py --files",
     "atari/mkprg.py include/gemdos/pexec_load.h\n\t$(PY) tools/accessory_disk.py --files"),
    ("build/acc/INFDISK.ST", "$(INF_DISK): tools/accessory_disk.py $(ROM_IMAGE)", "$(INF_DISK): tools/accessory_disk.py"),
])
def test_a_suite_without_a_capture_or_a_capture_without_its_disk_is_named(named, rule, without):
    """RED: the fourth capture dropped from the suites' prerequisites (the third likewise), a capture's rule without
    its disk or without the tool, a capture taken from another machine's disk, and a disk cut out of the ROM whose
    rule lacks the ROM image — each named."""
    makefile, kit = _texts()
    assert makefile.count(rule) == 1
    assert named in suites_without_a_capture([makefile.replace(rule, without), kit])


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
