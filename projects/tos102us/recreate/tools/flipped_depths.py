"""usage: flipped_depths.py <private dir> [--from <workspace>] [--patch <diff>]... [--unflipped] [--jobs N] [--json <out>]
[chain ...]

W6-R4's GATE ON THE FLIPPED STATE (band 6 slice D): PD0's depth, per chain of the hands' campaign, on a PRIVATE build
of a tree with EVERY LINKED ROUTINE OF BAND 6 FLIPPED — the shape slice B's cut measured as its prototype B, and the one
each flip slice (F1..F4) and deskmain's (W3b) must fit before it lands. The shared tree is only READ.

  1. COPY: the workspace's `projects/tos102us/` (but its Ghidra project) and `tools/` into `<private dir>` (rsync;
     recreate's build/ and kept/ are copied without deletion, so a second run is cheap) — `--from` names another
     workspace, by default the one this file lies in; each `--patch` (a unified diff against `recreate/`, a diet lever)
     is then applied to the copy — so a lever is measured without touching any tree but the private one.
  2. FLIP (skipped by `--unflipped`, which measures the tree as it is): `bench/linef_table.py`'s LINKED_AND_NOT_FLIPPED
     emptied and `src/aes/lineftable.S` generated again — every linked routine's entry ours, through its thunk — and
     sh_cmd's four built-ins (`src/aes/shell.c`) entered at their thunks on target (the desk door's `jsr`s; the host
     library keeps the ROM's addresses; the thunks are copied into a source of the flip's own). `$fde844` stays the
     ROM's (no table entry: its operand is F3's). Each step's anchor is held by `test_aes_desk_ours.py`.
  3. BUILD, FORCED: the private tree's blobs and library are removed and made again (`make` after an rsync can see a
     source older than its product: the mutation-testing rebuild trap) — the shipped blob is the one measured.
  4. THE BLOB IS FLIPPED, READ OFF ITS OWN BOUND TABLE (not with `--unflipped`): every band-6 routine with a C core and
     an entry of the table must be ours there (`aes_desk.still_the_rom_s`, who-ran's reading) — else the tool refuses
     before it walks: a flip step lost or broken would measure the unflipped blob under the flipped state's name.
  5. WALK every chain of `aes_desk.CHAINS` on our shore (`aes_desk.walked_ours`, `--jobs` processes) and print, per
     chain, PD0's depth by the write ledgers (`aes_desk.depth_stored`: the lowest store, the measure
     `test_aes_desk_ours.py` holds), the gate (`aes_desk.PD0_BYTES` less the interrupt nest MEASURED on that blob) and
     the margin. A step whose write ledger saturated is a refusal by name (`aes_desk.depths`' rule: what it stored is
     not known). The chains refused ON PURPOSE are DECLARED below, each with its reason.

Exits non-zero if the blob is not flipped (step 4), if a walked chain is over the gate, if a chain is refused that is
not declared (or for another reason than its declaration reads), or if a declared refusal walks. Run from anywhere:
`.venv/bin/python tools/flipped_depths.py $TMPDIR/flip --jobs 6`. The campaign is 115 chains (113 walked unflipped, 107
on the flipped state); a whole run is minutes (~10-15 at `--jobs 6`, build included); the first copy is ~700 MB.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve()
WORKSPACE = HERE.parents[4]
PROJECT = Path("projects") / "tos102us"
RECREATE = PROJECT / "recreate"
COPIED = (PROJECT, Path("tools"))      # the project's names.txt and aes_map/ are read too
KEPT_WITHOUT_DELETION = ("build", "kept")    # recreate/'s: copied, never deleted (the captures and the derivations)
REBUILT = ("build/bench", "build/bench_shipped", "build/libtos102us.so")
SHIPPED_BLOB = "build/bench_shipped/bench.bin"
GENERATOR = "bench/linef_table.py"
TABLE = "src/aes/lineftable.S"
DOOR_THUNKS = "src/aes/flipped_door.S"   # the flip's own source, in the private tree alone
EMPTIED = "\nLINKED_AND_NOT_FLIPPED.clear()   # flipped_depths.py: every linked routine flipped\n"
EMPTIED_BEFORE = "\ndef thunk_symbol("
# sh_cmd's four built-ins: the ROM's routine the door `jsr`s today -> the thunk the flip enters it through.
BUILT_INS = {"AES_ROM_DESK_SHOW_FILE": "linef_to_aes_desk_show_file", "AES_ROM_DESK_PRINT_FILE": "linef_to_aes_desk_print_file",
             "AES_ROM_DESK_FORMAT": "linef_to_aes_desk_format", "AES_ROM_DESK_COPY_DISK": "linef_to_aes_desk_copy_disk"}
SHELL = "src/aes/shell.c"
FLIPPED_PREFIX = "FLIPPED_"
REFUSAL_KEPT, REFUSAL_SHOWN = 300, 160      # characters of a refusal's text: in the JSON, on the printed line

# ---- THE CHAINS REFUSED ON PURPOSE, `{chain: (why, what its refusal reads)}` ----
# W6-R8's two, on either state (the user's ruling: a launch and the disk copy store over our blob, so they stay the
# ROM's shore's — `test_aes_desk_ours.REFUSED_ON_OUR_SHORE`, which a test holds these to)...
NO_IDLE_REACHED = "the run did not reach an idle within"
REFUSED_ON_EITHER_STATE = {
    "files: the program double-clicked — launched": ("W6-R8: the launch loads the program over our blob", NO_IDLE_REACHED),
    "a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)": (
        "W6-R8: the disk copy reads its tracks over our blob", "Rwabs of drive 254: the model holds drive A: alone")}
# ...and N4's on the flipped state alone: the viewer's two key waits are named stops at the ROM's addresses inside the
# show engine's body, which is ours once unit M flips, so the walk never stops there — F4 declares their C-side stops
# (`aes_desk.OUR_STOPS`) and takes these out. The last chain goes on from the fifth's machine.
VIEWER_STOPS_THE_ROM_S = "N4: the viewer's key waits are the ROM's stops, inside the show engine's body (F4's)"
REFUSED_ON_THE_FLIPPED_STATE = {name: (VIEWER_STOPS_THE_ROM_S, NO_IDLE_REACHED) for name in (
    "files: the right arrow clicked, then the long file shown",
    "files: the long file shown, a blank at each page's end and at its end",
    "files: View > Sort by Size, then the long file shown",
    "files: View > Show as Text, then the long file's line shown",
    "file: shown, a key at its end")}
REFUSED_ON_THE_FLIPPED_STATE["file: shown, a key at its end — the file clicked, File > Open, shown again"] = (
    "N4: walked from 'file: shown, a key at its end', refused before it", NO_IDLE_REACHED)
LEDGER_SATURATED = "a step saturated its write ledger: what it stored is not known"


def run(command, cwd, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=cwd, check=True, **kwargs)


def copy_tree(source, private):
    kept_under = f"/{RECREATE.relative_to(PROJECT)}"
    excluded = [f"--exclude={kept_under}/{kept}/" for kept in KEPT_WITHOUT_DELETION] + ["--exclude=__pycache__",
                                                                                         "--exclude=/ghidra_proj/"]
    for part in COPIED:
        (private / part).mkdir(parents=True, exist_ok=True)
        run(["rsync", "-a", "--delete", *excluded, f"{source / part}/", f"{private / part}/"], cwd=private)
    for kept in KEPT_WITHOUT_DELETION:
        run(["rsync", "-a", "--exclude=__pycache__", f"{source / RECREATE / kept}", f"{private / RECREATE}/"], cwd=private)


def emptied(generator):
    """The generator's text with LINKED_AND_NOT_FLIPPED emptied: every linked routine's entry ours, through its thunk."""
    assert generator.count(EMPTIED_BEFORE) == 1, f"{GENERATOR}: no single `def thunk_symbol(` to empty the list before"
    return generator.replace(EMPTIED_BEFORE, EMPTIED + EMPTIED_BEFORE)


def door_thunks(table):
    """A source of sh_cmd's four thunks, COPIED out of the generated table's text and made global: the table's own are
    file-local, and its source may define no other `.globl` (a pin of the registry's)."""
    copies = ["    .text"]
    for thunk in BUILT_INS.values():
        body = re.search(rf"^    \.type   {thunk},@function\n.*?^    \.size   {thunk},.*?$", table, re.M | re.S)
        assert body, f"{TABLE}: no thunk {thunk}"
        copies += [f"    .globl {FLIPPED_PREFIX}{thunk}", body.group(0).replace(thunk, FLIPPED_PREFIX + thunk)]
    return "\n".join(copies) + "\n"


def sh_cmd_flipped(shell):
    """shell.c's text with sh_cmd's four built-ins entered at the copied thunks on target (the host keeps the ROM's)."""
    defines = ["#ifdef RECREATE_HOST_DIFFERENTIAL"] + [f"#define {FLIPPED_PREFIX}{rom} {rom}" for rom in BUILT_INS]
    defines += ["#else"] + [f"#define {FLIPPED_PREFIX}{rom} {FLIPPED_PREFIX}{thunk}" for rom, thunk in BUILT_INS.items()]
    defines += ["#endif"]
    for rom in BUILT_INS:
        site = f"(image, {rom}, AES_SH_TAIL_TEXT"
        assert shell.count(site) == 1, f"{SHELL}: sh_cmd's site of {rom} moved (F4 retires this step)"
        shell = shell.replace(site, f"(image, {FLIPPED_PREFIX}{rom}, AES_SH_TAIL_TEXT")
    last_include = max(match.end() for match in re.finditer(r"^#include .*$", shell, re.M))
    return shell[:last_include] + "\n" + "\n".join(defines) + shell[last_include:]


def flip(recreate):
    generator = recreate / GENERATOR
    generator.write_text(emptied(generator.read_text()))
    run([".venv/bin/python", GENERATOR], cwd=recreate, env=dict(os.environ, PYTHONPATH=str(recreate.parents[2] / "tools")))
    (recreate / DOOR_THUNKS).write_text(door_thunks((recreate / TABLE).read_text()))
    (recreate / SHELL).write_text(sh_cmd_flipped((recreate / SHELL).read_text()))


def build(recreate):
    for product in REBUILT:
        run(["rm", "-rf", product], cwd=recreate)
    run(["make", SHIPPED_BLOB], cwd=recreate)


def declared_refusals(unflipped):
    """`{chain: (why, what its refusal reads)}` of the chains refused on purpose on the state measured."""
    return REFUSED_ON_EITHER_STATE if unflipped else REFUSED_ON_EITHER_STATE | REFUSED_ON_THE_FLIPPED_STATE


def misrefused(found, declared):
    """`(refused and not declared, declared and walked)`, chain names of `found` (`{chain: row}`): a refusal outside
    `declared`, or one whose text does not read what its declaration says, and a declared refusal that now walks."""
    undeclared = [name for name, row in found.items()
                  if "refused" in row and (name not in declared or declared[name][1] not in row["refused"])]
    walks = [name for name, row in found.items() if name in declared and "refused" not in row]
    return undeclared, walks


def measured(steps, lo, hi):
    """A walked chain's row, `{"pd0": bytes, "blob_cycles": our blob's own cycles over its steps}` — PD0 `[lo, hi)` —
    or `{"refused": why}` where a step's write ledger saturated."""
    import aes_desk as desk
    if any(step.boot.writes_truncated for step in steps):
        return {"refused": LEDGER_SATURATED}
    return {"pd0": max(desk.depth_stored(step.boot.stored, lo, hi) for step in steps),
            "blob_cycles": sum(step.blob for step in steps)}


def _private_imports(recreate):
    """A worker's imports from the private tree, run from it."""
    os.chdir(recreate)
    sys.path[:0] = [str(recreate / "test"), str(recreate / "bench"), str(recreate.parents[2] / "tools")]


def _walk(recreate, names):
    """In a worker: `{chain: measured(...) | {"refused": why}}` over `names`, on the private tree's shipped blob."""
    _private_imports(recreate)
    import aes_desk as desk
    from aes_boot import Refused
    found = {}
    for name in names:
        try:
            walk = desk.walked_ours(name)
        except Refused as refused:
            found[name] = {"refused": str(refused)[:REFUSAL_KEPT]}
            continue
        found[name] = measured(walk.steps, *desk.stacks(walk.machine)[desk.PD0_STACK])
    return found


def linked_still_the_rom_s(desk, generator):
    """Band 6's routines with a C core and an entry of the ROM's table that the blob's OWN bound table still leaves the
    ROM's (`desk.still_the_rom_s`), in order: none once the blob is flipped."""
    with_an_entry = set(generator.rom_table()) & set(generator.declared_cores())
    return sorted(with_an_entry & desk.still_the_rom_s())


def _gate(recreate):
    """In a worker: `(the gate, every chain, the linked routines the blob leaves the ROM's)`."""
    _private_imports(recreate)
    import aes_desk as desk
    import aes_stack
    import linef_table
    gate = desk.PD0_BYTES - aes_stack.nest_on_the_first_stack(desk.OUR_BLOB)
    return gate, list(desk.CHAINS), linked_still_the_rom_s(desk, linef_table)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("private", type=Path)
    parser.add_argument("--from", dest="source", type=Path, default=WORKSPACE)
    parser.add_argument("--patch", type=Path, action="append", default=[])
    parser.add_argument("--unflipped", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--json", type=Path)
    parser.add_argument("chains", nargs="*")
    asked = parser.parse_intermixed_args(argv[1:])
    private, recreate = asked.private.resolve(), asked.private.resolve() / RECREATE
    copy_tree(asked.source.resolve(), private)
    for patch in asked.patch:
        run(["patch", "-p1", "--forward", "--input", str(patch.resolve())], cwd=recreate)
    if not asked.unflipped:
        flip(recreate)
    build(recreate)
    with ProcessPoolExecutor(1) as one:
        gate, every, not_flipped = one.submit(_gate, recreate).result()
    if not_flipped and not asked.unflipped:
        print(f"\nREFUSED: the blob is NOT FLIPPED — its bound table leaves {len(not_flipped)} linked routine(s) the "
              f"ROM's: {', '.join(f'${rom:x}' for rom in not_flipped)}")
        return 1
    declared = declared_refusals(asked.unflipped)
    unknown = sorted(set(declared) - set(every))
    if unknown:
        print(f"\nREFUSED: a declared refusal names no chain of the campaign: {unknown}")
        return 1
    names = asked.chains or every
    shares = [names[nth::asked.jobs] for nth in range(asked.jobs)]
    found = {}
    with ProcessPoolExecutor(asked.jobs) as pool:
        for part in pool.map(_walk, [recreate] * len(shares), shares):
            found.update(part)
    over = 0
    print(f"\nW6-R4's gate on {'the tree as it is' if asked.unflipped else 'the flipped state'}: {gate} B "
          f"(PD0's span less the nest measured on its shipped blob)")
    for name in names:
        row = found[name]
        if "refused" in row:
            print(f"{'refused':>8}  {'':>6}  {name}  -- {row['refused'][:REFUSAL_SHOWN]}")
            continue
        over += row["pd0"] > gate
        print(f"{row['pd0']:8}  {row['pd0'] - gate:+6}  {name}")
    if asked.json:
        asked.json.write_text(json.dumps({"gate": gate, "flipped": not asked.unflipped, "chains": found}, indent=1))
    undeclared, walks = misrefused({name: found[name] for name in names}, declared)
    print(f"\n{over} chain(s) over the gate; {len(undeclared)} refused and not declared {undeclared}; "
          f"{len(walks)} declared refused and walked {walks}")
    return 1 if over or undeclared or walks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
