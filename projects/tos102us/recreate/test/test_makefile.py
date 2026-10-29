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
import glob
import os
import re
import subprocess
import sys
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
# THE SCRIPT THAT VETS A FRESH SNAPSHOT before it is kept: it imports test modules but not the registry, and reads the
# capture it is handed and the one pre-init machine the ROM's own boot is run from (measured: `aes_boot.CAPTURES_READ`
# after a vet) — `{script: what its rule must have}`.
VETS_A_CAPTURE = {"tools/vet_snapshot.py": ("build/preinit.bin",)}
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
    """The targets whose recipe runs Python over the registry and lack a capture: `{target: the missing files}` — and
    those that run a capture's vet and lack what it reads."""
    lacking = {}
    for target, (prerequisites, recipe) in rules_of(texts).items():
        text = "\n".join(recipe)
        scripts = set(_SCRIPT.findall(text)) - MAKE_THE_CAPTURES
        vets = scripts & set(VETS_A_CAPTURE)
        if scripts - vets or _PYTEST.search(text):
            wanted = CAPTURES
        elif vets:
            wanted = [read for vet in sorted(vets) for read in VETS_A_CAPTURE[vet]]
        else:
            continue
        missing = [capture for capture in wanted if capture not in prerequisites]
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
    reader's file arm), AND THE FILES ONE since band 6 slice F1 (the flipped desk routines' rows at its arrivals). RED,
    on the list a registered row of the seven-accessory machine would make: that capture is named as lacking; and each
    of the four, dropped from the rule, is named too."""
    assert READ_BY_THE_REGISTRY_S_IMPORT == ("build/preinit.bin", "build/preinit_acc.bin", "build/preinit_files.bin",
                                             "build/preinit_inf.bin")
    assert not_among_the_registry_s_reads(CAPTURES, _texts()) == []
    seven = str(preinit_snapshot.seven_accessory_path().relative_to(RECREATE))
    assert not_among_the_registry_s_reads((*CAPTURES, seven), _texts()) == [seven]
    makefile, kit = _texts()
    rule = "REGISTRY_READS := $(SNAPSHOT) $(PREINIT) $(PREINIT_ACC) $(PREINIT_INF) $(PREINIT_FILES)"
    assert makefile.count(rule) == 1
    for dropped, lacking in ((" $(PREINIT_ACC)", "build/preinit_acc.bin"), (" $(PREINIT_INF)", "build/preinit_inf.bin"),
                             (" $(PREINIT_FILES)", "build/preinit_files.bin")):
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
    # ONE CAPTURE TOOL'S RUN EACH, wherever the recipe puts them — the five side by side are one shell line
    twice = [run for line in recipe for run in line.split(CAPTURE_TOOL)[1:]]
    assert len(twice) == len(PREINIT_CAPTURES) and all(run.lstrip().startswith("--twice") for run in twice)
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
             if set(_SCRIPT.findall("\n".join(recipe))) - MAKE_THE_CAPTURES - set(VETS_A_CAPTURE) or _PYTEST.search("\n".join(recipe))}
    assert found == EVERY_PYTHON_TARGET


def test_the_snapshot_s_vet_has_what_it_reads():
    """The vet's rule (the snapshot's) has the pre-init machine the vet boots the ROM from — AS MAKE READS IT (its own
    database: a rule's prerequisites are expanded where the rule is read, so a variable defined below it is empty
    there, which this file's parse cannot see); RED, the text without it."""
    makefile, kit = _texts()
    rule = "| tools/vet_snapshot.py $(PREINIT) $(CAND) $(ORACLE)"
    assert makefile.count(rule) == 1 and without_the_captures([makefile, kit]) == {}
    assert without_the_captures([makefile.replace(rule, "| tools/vet_snapshot.py $(CAND) $(ORACLE)"), kit]) == {SNAPSHOT: ["build/preinit.bin"]}
    database = _make("-p", "-q", SNAPSHOT, check=False)
    ruled, = (line for line in database.splitlines() if line.startswith(f"{SNAPSHOT}:"))
    assert "build/preinit.bin" in ruled.partition("|")[2].split()


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


# ---- THE GATE: THE GUARDED SUITE ALONE (the user's ruling (a'), 2026-10-15) ----------------------------------------------
_GATE_SUITE = re.compile(r"cache_dir=\S+/(test|guarded)\.cache (.*?) (?:-p recreate_kit\.guarded_image )?test >")
_PYTEST_RUN = re.compile(r"-m pytest\b")
# What a make AROUND this process hands every make below it: a gate's command-line variables (`FRESH=1`,
# `GUARDED_PYTEST_ARGS=...`) reach its sub-makes through MAKEFLAGS, `FRESH` exports the derivations' root, and make
# exports every command-line variable into its recipes' environment — so a gate run as `make gates
# GUARDED_PYTEST_ARGS="-n 8"` (or `make test PYTEST_ARGS=...`) hands it to this process. Each would answer for the
# defaults asked here.
_MAKE_S_OWN = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "FRESH", "AES_DERIVED_ROOT", "GUARDED_PYTEST_ARGS", "PYTEST_ARGS")


def _make(*arguments, environment=None, probe=None, check=True):
    """`make *arguments` in this directory, outside any make — and, with `probe` (a makefile's path), over this
    Makefile AND that one (make 3.81 has no `--eval`)."""
    inherited = {name: value for name, value in os.environ.items() if name not in _MAKE_S_OWN}
    files = ["-f", "Makefile", "-f", str(probe)] if probe else []
    return subprocess.run(["make", *files, *arguments], cwd=RECREATE, capture_output=True, text=True, check=check,
                          env={**inherited, **(environment or {})}).stdout


def make_value(name, tmp_path, *assignments):
    """The value make gives `name` (this Makefile's), with `assignments` on the command line."""
    probe = tmp_path / "value.mk"
    probe.write_text(f"print-value:\n\t@echo '$({name})'\n")
    return _make("-s", "print-value", *assignments, probe=probe).strip()


def gate_suite_arguments(*assignments, environment=None):
    """`{suite: its pytest arguments}` as `make -n gates` spells them, with `assignments` on the command line and
    `environment` added to make's (`make -n` runs no recipe of this makefile: its recursive make is not spelt `$(MAKE)`),
    and how many pytest runs it spells."""
    shown = _make("-n", "gates", *assignments, environment=environment)
    return dict(_GATE_SUITE.findall(shown)), len(_PYTEST_RUN.findall(shown))


def test_the_gate_runs_the_guarded_suite_alone_on_gate_workers_unless_its_arguments_are_named(tmp_path):
    """ONE pytest run, the guarded one — `make test`'s plain run is not the gate's — on GATE_WORKERS by default
    (a worker per core, as many as the memory holds at GATE_WORKER_BYTES each, at least one), and GUARDED_PYTEST_ARGS
    named on the command line or in the environment wins; PYTEST_ARGS, `make test`'s, adds no run."""
    workers = int(make_value("GATE_WORKERS", tmp_path))
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    held = memory // int(_definitions(_texts())["GATE_WORKER_BYTES"])
    assert workers == max(1, min(os.cpu_count(), held))
    default = {"guarded": f"-n {workers}"}
    assert gate_suite_arguments() == (default, 1)
    assert gate_suite_arguments("PYTEST_ARGS=-n 3 -k fuzz") == (default, 1)
    assert gate_suite_arguments("GUARDED_PYTEST_ARGS=-n 3 -k fuzz") == ({"guarded": "-n 3 -k fuzz"}, 1)
    assert gate_suite_arguments(environment={"GUARDED_PYTEST_ARGS": "-n 2"}) == ({"guarded": "-n 2"}, 1)


# ---- THE STORE: CAPTURES AND DERIVATIONS KEPT ACROSS FROM-EMPTY BUILDS (the user's ruling (b), 2026-10-15) ------------
THE_HATARI_CAPTURES = (SNAPSHOT, *PREINIT_CAPTURES)
CAPTURE_TOOLS = ("tools/boot_snapshot.py", CAPTURE_TOOL)
WORKSPACE_TOOLS = RECREATE.parents[2] / "tools"


def _definitions(texts):
    return {name: value for line in (line for text in texts for line in _joined(text)) for name, value in _DEFINITION.findall(line)}


def captures_not_through_the_store(texts):
    """The Hatari captures whose recipe is not `$(FROM_THE_STORE) || <the capture tool> ... --out $@` followed by
    `$(INTO_THE_STORE)` and nothing else, over makefile `texts` — the snapshot's `$(FROM_THE_STORE) && <its vet> || ...`
    (a served snapshot is vetted too)."""
    rules, variables = rules_of(texts), _definitions(texts)
    served, kept = (_expanded(f"\t@$({name})", variables) for name in ("FROM_THE_STORE", "INTO_THE_STORE"))
    vetted = _expanded("$(VET_SNAPSHOT)", variables)
    lacking = []
    for capture in THE_HATARI_CAPTURES:
        recipe = rules.get(capture, (set(), []))[1]
        made = [at for at, line in enumerate(recipe) if any(tool in line for tool in CAPTURE_TOOLS) and "--out $@" in line]
        opening = f"{served} && {vetted} || " if capture == SNAPSHOT else f"{served} || "
        if not (len(made) == 1 and recipe[made[0]].startswith(opening) and recipe[made[0] + 1:] == [kept]):
            lacking.append(capture)
    return lacking


def test_every_hatari_capture_is_served_from_the_store_and_kept_into_it():
    """All six captures go through the store, a served snapshot vetted; RED, one capture whose recipe no longer keeps
    what it made, and the snapshot served unvetted."""
    makefile, kit = _texts()
    assert captures_not_through_the_store([makefile, kit]) == []
    files_rule = "build/preinit_files_snapshot --out $@\n\t@$(INTO_THE_STORE)"
    assert makefile.count(files_rule) == 1
    assert captures_not_through_the_store([makefile.replace(files_rule, files_rule.split("\n")[0]), kit]) == ["build/preinit_files.bin"]
    snapshot_rule = "@$(FROM_THE_STORE) && $(VET_SNAPSHOT) || ($(CAPTURE_VETTED))"
    assert makefile.count(snapshot_rule) == 1
    unvetted = makefile.replace(snapshot_rule, "@$(FROM_THE_STORE) || ($(CAPTURE_VETTED))")
    assert captures_not_through_the_store([unvetted, kit]) == [SNAPSHOT]


def capture_key_lacks(texts):
    """What the captures' key does not read, over makefile `texts`: of the workspace modules a capture tool imports (a
    file of this project's tools/ or the workspace's), the oracle and the Hatari — each named by the key's own list or
    by a capture's prerequisites, which the key reads (`$^`)."""
    variables, rules = _definitions(texts), rules_of(texts)
    assert "$^" in variables["CAPTURE_KEY"] and "$(CAPTURES_MADE_BY)" in variables["CAPTURE_KEY"]
    named = set(variables["CAPTURES_MADE_BY"].split()) | {needed for capture in THE_HATARI_CAPTURES for needed in rules[capture][0]}
    imported = {name for tool in CAPTURE_TOOLS for name in re.findall(r"^(?:import|from)\s+(\w+)", (RECREATE / tool).read_text(), re.M)}
    wanted = {f"tools/{name}.py" for name in imported if (RECREATE / "tools" / f"{name}.py").exists()}
    wanted |= {f"../../../tools/{name}.py" for name in imported if (WORKSPACE_TOOLS / f"{name}.py").exists()}
    return sorted(wanted - named) + [each for each in ("$(ORACLE)", "$(HATARI)") if each not in named]


def test_the_captures_key_reads_what_the_capture_tools_import_the_oracle_and_the_hatari():
    """DERIVED from the tools' own imports, not declared; RED, the key's list without st_build."""
    makefile, kit = _texts()
    assert capture_key_lacks([makefile, kit]) == []
    rule = "CAPTURES_MADE_BY := ../../../tools/st_build.py "
    assert makefile.count(rule) == 1
    assert capture_key_lacks([makefile.replace(rule, "CAPTURES_MADE_BY := "), kit]) == ["../../../tools/st_build.py"]


HATARI_CONFIG = Path.home() / "Library" / "Application Support" / "Hatari" / "hatari.cfg"


def test_the_captures_key_reads_the_emulator_itself_and_the_user_s_hatari_configuration(tmp_path):
    """The key's Hatari is the PROGRAM, not Homebrew's two-line script that execs it; and the user's own hatari.cfg
    — which no capture tool overrides — is keyed where it exists (its word a glob: the directory's name has a space)."""
    keyed = make_value("CAPTURES_MADE_BY", tmp_path).split()
    emulator = make_value("HATARI", tmp_path)
    assert emulator in keyed and not Path(emulator).read_bytes().startswith(b"#!")
    assert (str(HATARI_CONFIG) in {found for word in keyed for found in glob.glob(word)}) == HATARI_CONFIG.exists()


def stand_in_capture(tmp_path, made_by="echo made by $$$$ > $@"):
    """A capture over this Makefile's own store macros, `made_by` a recipe (by default a line of text no two runs
    write alike), out of `tmp_path/part` into `tmp_path/out/capture.bin`, kept in `tmp_path/store`:
    `capture(the part's content, *assignments, out_left=False, check=True)` -> (what build holds or None, served)."""
    out, part, store = tmp_path / "out" / "capture.bin", tmp_path / "part", tmp_path / "store"
    out.parent.mkdir(exist_ok=True)
    probe = tmp_path / f"capture{len(list(tmp_path.glob('capture*.mk')))}.mk"
    probe.write_text(f"{out}: {part}\n\t@$(FROM_THE_STORE) || {made_by}\n\t@$(INTO_THE_STORE)\n")

    def capture(content, *assignments, out_left=False, check=True):
        if not part.exists() or part.read_text() != content:     # ...an unchanged part keeps its date
            part.write_text(content)
        if not out_left:
            out.unlink(missing_ok=True)
        said = _make(str(out), f"STORE={store}", *assignments, probe=probe, check=check)
        return (out.read_text() if out.exists() else None), ": kept, " in said
    capture.out, capture.entries = out, lambda: sorted(store.rglob(out.name))
    return capture


def test_a_capture_is_served_by_its_key_and_fresh_makes_it_again(tmp_path):
    """THE STORE'S BEHAVIOUR, over this Makefile's own recipe macros and a stand-in capture: made and kept the first
    time; SERVED, the same bytes, the second; made again under FRESH=1, and that one kept in place of the first; made
    again when a prerequisite's CONTENT changes (another key); served again under the first key."""
    capture = stand_in_capture(tmp_path)
    first, served = capture("one")
    assert not served and first.startswith("made by")
    assert capture("one") == (first, True)
    fresh, served = capture("one", "FRESH=1")
    assert not served and fresh != first
    assert capture("one") == (fresh, True)
    other, served = capture("two")
    assert not served and other not in (first, fresh)
    assert capture("one") == (fresh, True)


def test_fresh_makes_every_capture_again_whatever_build_holds_and_fresh_0_is_not_fresh(tmp_path):
    """FRESH=1 makes a capture build/ holds up to date again (HATARI_CAPTURES are phony then: every Hatari capture of
    this Makefile, named here by the stand-in's own); FRESH=0 is a default make, served."""
    assert sorted(make_value("HATARI_CAPTURES", tmp_path).split()) == sorted(THE_HATARI_CAPTURES)
    capture = stand_in_capture(tmp_path)
    first, _ = capture("one")
    assert capture("one", "FRESH=0") == (first, True)
    listed = f"HATARI_CAPTURES={capture.out}"
    assert capture("one", listed, out_left=True) == (first, False)
    fresh, served = capture("one", "FRESH=1", listed, out_left=True)
    assert not served and fresh != first


def test_a_capture_whose_key_moved_while_it_was_made_is_neither_kept_nor_left(tmp_path):
    """THE KEY IS READ BEFORE THE CAPTURE: a capture whose prerequisite is edited while it is made (here by the
    capture itself, after reading it) fails, keeps nothing and leaves nothing in build/ — and the edited content is
    made, never served the capture of the old one (the gate-speed review's race, F1)."""
    racing = stand_in_capture(tmp_path, made_by="{ cat $< > $@; echo two > $<; }")
    assert racing("one", check=False) == (None, False) and racing.entries() == []
    made, served = stand_in_capture(tmp_path)("two")
    assert not served and made.startswith("made by")


def test_a_served_capture_is_not_copied_back_and_a_kept_one_is_replaced_never_written_over(tmp_path):
    """Served, the entry is left as it is (the same file); a capture made in its place is RENAMED over it, so a reader
    holding the old entry (here a second link to it) still has the whole of the old bytes (review M3)."""
    capture = stand_in_capture(tmp_path)
    first, _ = capture("one")
    entry, = capture.entries()
    identity = entry.stat().st_ino
    assert capture("one") == (first, True) and entry.stat().st_ino == identity
    held = tmp_path / "held"
    os.link(entry, held)
    fresh, _ = capture("one", "FRESH=1")
    assert held.read_text() == first and entry.read_text() == fresh != first


def test_an_entry_its_digest_does_not_match_is_made_again(tmp_path):
    """Each entry's digest is kept beside it (`.sha256`) and checked before it is served: a damaged entry is made
    again and replaced, and the new one served after."""
    capture = stand_in_capture(tmp_path)
    first, _ = capture("one")
    entry, = capture.entries()
    assert entry.with_name(entry.name + ".sha256").exists()
    entry.write_text(first.upper())
    made, served = capture("one")
    assert not served and made not in (first, first.upper())
    assert capture("one") == (made, True)


def test_the_derivations_are_kept_in_the_store_and_fresh_makes_them_in_build(tmp_path):
    """test/derived.py's ROOT is the store's `derived/` (the Makefile's STORE, one spelling held to the other) unless
    the environment names another; `make ... FRESH=1` names build/derived for every recipe, and a default make none."""
    store = _definitions(_texts())["STORE"]
    root_of = ("import sys; sys.path.insert(0, 'test'); import derived; print(derived.ROOT)")
    inherited = {name: value for name, value in os.environ.items() if name != "AES_DERIVED_ROOT"}
    roots = [subprocess.run([sys.executable, "-c", root_of], cwd=RECREATE, capture_output=True, text=True, check=True,
                            env={**inherited, **named}).stdout.strip() for named in ({}, {"AES_DERIVED_ROOT": str(tmp_path)})]
    assert roots == [str(RECREATE / store / "derived"), str(tmp_path)]
    probe = tmp_path / "root.mk"
    probe.write_text("print-root:\n\t@echo \"[$$AES_DERIVED_ROOT]\"\n")
    assert _make("-s", "print-root", probe=probe).strip() == "[]"
    assert _make("-s", "print-root", "FRESH=1", probe=probe).strip() == f"[{RECREATE / 'build' / 'derived'}]"
    assert _make("-s", "print-root", "FRESH=0", probe=probe).strip() == "[]"
