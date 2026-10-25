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
     emptied and `src/aes/lineftable.S` generated again — every linked routine's entry ours, through its thunk — with
     `include/aes/lineftable.h`, the desk door's bindings: sh_cmd's four built-ins entered at the very thunks the table
     names, on target (band 6 slice F4's prep: the generator's own, no copy). `$fde844` (no table entry) is ours
     already: `trapdoor.S`'s operand, relocated at band 6 slice F3 (N18). The step's anchor is held by
     `test_aes_desk_ours.py`.
  3. BUILD, FORCED: the private tree's blobs and library are removed and made again (`make` after an rsync can see a
     source older than its product: the mutation-testing rebuild trap) — the shipped blob is the one measured.
  4. THE BLOB IS FLIPPED, READ OFF ITS OWN BOUND TABLE (not with `--unflipped`): every band-6 routine with a C core and
     an entry of the table must be ours there (`aes_desk.still_the_rom_s`, who-ran's reading) — else the tool refuses
     before it walks: a flip step lost or broken would measure the unflipped blob under the flipped state's name.
  5. WALK every chain of `aes_desk.CHAINS` on our shore (`aes_desk.walked_ours`, `--jobs` processes) and print, per
     chain, PD0's depth by the write ledgers (`aes_desk.depth_stored`: the lowest store, the measure
     `test_aes_desk_ours.py` holds), the gate (`aes_desk.PD0_BYTES` less the interrupt nest MEASURED on that blob) and
     the margin. A step whose write ledger saturated is a refusal by name (`aes_desk.depths`' rule: what it stored is
     not known). The chains refused ON PURPOSE are DECLARED below, each with its reason — and on the flipped state,
     every chain with a step at a named stop the flipped blob has no C-side stop for (`aes_desk.our_stop`'s refusal),
     read off that blob.

Exits non-zero if the blob is not flipped (step 4), if a walked chain is over the gate, if a chain is refused that is
not declared (or for another reason than its declaration reads), or if a declared refusal walks. Run from anywhere:
`.venv/bin/python tools/flipped_depths.py $TMPDIR/flip --jobs 6`. The campaign is 123 chains (121 walked on either state
since band 6 W3a's diet landed opn_appl's chain, the viewer's eight at our `key_awaited`); a whole run is minutes (~10-15 at `--jobs 6`, build
included); the first copy is ~700 MB.
"""
import argparse
import json
import os
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
EMPTIED = "\nLINKED_AND_NOT_FLIPPED.clear()   # flipped_depths.py: every linked routine flipped\n"
EMPTIED_BEFORE = "\ndef thunk_symbol("
REFUSAL_KEPT, REFUSAL_SHOWN = 300, 160      # characters of a refusal's text: in the JSON, on the printed line

# ---- THE CHAINS REFUSED ON PURPOSE, `{chain: (why, what its refusal reads)}` ----
# W6-R8's two, on either state (the user's ruling: a launch and the disk copy store over our blob, so they stay the
# ROM's shore's — `test_aes_desk_ours.REFUSED_ON_OUR_SHORE`, which a test holds these to)...
NO_IDLE_REACHED = "the run did not reach an idle within"
REFUSED_ON_EITHER_STATE = {
    "files: the program double-clicked — launched": ("W6-R8: the launch loads the program over our blob", NO_IDLE_REACHED),
    "a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)": (
        "W6-R8: the disk copy reads its tracks over our blob", "Rwabs of drive 254: the model holds drive A: alone")}
# ...and N4's on the flipped state alone, DERIVED (band 6 slice F4's prep, ruling O3): a named stop that moves with a
# flip (`aes_desk.OUR_STOPS_ONCE_FLIPPED` — the viewer's two key waits, inside the show engine's body) is our C's stop
# on the flipped state, and a chain with a step at one is refused by name while the flipped blob has no symbol to stop
# at (`aes_desk.our_stop`: `key_awaited` inlined) — `refused_on_the_flipped_state`, read off that blob.
NO_C_SIDE_STOP = "N4: a named stop is ours on the flipped state and its C-side stop is no symbol of the flipped blob"
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


def flip(recreate):
    generator = recreate / GENERATOR
    generator.write_text(emptied(generator.read_text()))
    run([".venv/bin/python", GENERATOR], cwd=recreate, env=dict(os.environ, PYTHONPATH=str(recreate.parents[2] / "tools")))


def build(recreate):
    for product in REBUILT:
        run(["rm", "-rf", product], cwd=recreate)
    run(["make", SHIPPED_BLOB], cwd=recreate)


def refused_on_the_flipped_state(chains, stops_not_in_the_blob):
    """`{chain: (why, what its refusal reads)}` of `chains` (`{name: aes_desk.Chain}`) with a step at a named stop of
    `stops_not_in_the_blob` — those ours on the flipped state with no C-side stop there (a chain walked from one is
    refused by its predecessor's refusal, which reads the same)."""
    import aes_desk as desk
    return {name: (NO_C_SIDE_STOP, desk.A_STOP_NOT_IN_THE_BLOB) for name, chain in chains.items()
            if any(step.until in stops_not_in_the_blob for step in chain.steps)}


def declared_refusals(unflipped, on_the_flipped_state=None):
    """`{chain: (why, what its refusal reads)}` of the chains refused on purpose on the state measured:
    `on_the_flipped_state` (`refused_on_the_flipped_state`'s) added where it is the flipped one."""
    return REFUSED_ON_EITHER_STATE if unflipped else REFUSED_ON_EITHER_STATE | (on_the_flipped_state or {})


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
    """Band 6's routines with a C core LINKED IN THE BLOB and an entry of the ROM's table that the blob's OWN bound
    table still leaves the ROM's (`desk.still_the_rom_s`), in order: none once the blob is flipped. (A routine declared
    and not yet linked — band 6 W3a's, `DECLARED_NOT_LINKED` — has no core to flip: read off the blob's symbols.)"""
    import routines
    import transcription
    linked = {symbol.name for symbol in transcription.symbol_table(desk.our_blob().elf)}
    cores = {address for address, name in generator.declared_cores().items() if routines.core_symbol(name) in linked}
    return sorted(set(generator.rom_table()) & cores & desk.still_the_rom_s())


def _gate(recreate):
    """In a worker: `(the gate, every chain, the linked routines the blob leaves the ROM's, the chains refused on the
    flipped state for a C-side stop the blob has no symbol for)`."""
    _private_imports(recreate)
    import aes_desk as desk
    import aes_stack
    import linef_table
    gate = desk.PD0_BYTES - aes_stack.nest_on_the_first_stack(desk.OUR_BLOB)
    missing = stops_our_stop_refuses(desk, desk.our_blob())
    return gate, list(desk.CHAINS), linked_still_the_rom_s(desk, linef_table), refused_on_the_flipped_state(desk.CHAINS, missing)


def stops_our_stop_refuses(desk, blob):
    """The named stops ours on `blob` that `aes_desk.our_stop` refuses there — its rule, asked, never restated."""
    refused = set()
    for stop in desk.our_stops(blob):
        try:
            desk.our_stop(stop, blob)
        except desk.Refused:
            refused.add(stop)
    return refused


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
        gate, every, not_flipped, on_the_flipped_state = one.submit(_gate, recreate).result()
    if not_flipped and not asked.unflipped:
        print(f"\nREFUSED: the blob is NOT FLIPPED — its bound table leaves {len(not_flipped)} linked routine(s) the "
              f"ROM's: {', '.join(f'${rom:x}' for rom in not_flipped)}")
        return 1
    declared = declared_refusals(asked.unflipped, on_the_flipped_state)
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
