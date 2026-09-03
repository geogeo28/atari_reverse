# Agent playbook — reverse-engineering efficiently

The other docs teach *mechanics* (parse a `.PRG`, drive Ghidra, read 68000, decode graphics).
This one is the **meta**: how an agent turns an arbitrary binary into named, **provably-correct**
source *fast*, and the traps that waste hours. It is distilled from the BuggyBoy project (91/91
functions reconstructed and verified byte-for-byte) but written as general procedure.

**The one idea:** speed in RE is not typing — it is (1) anchoring on ground truth instead of
reading linearly, (2) **verifying by execution instead of by eye**, (3) attacking functions in
dependency order, and (4) keeping a tight edit→verify loop. Everything below serves those four.

---

## 1. Orient before you touch (minutes, not hours)

1. Run `prg_dis.py` on the file. It prints the header, symbol/reloc counts, and **text entropy** —
   your first fork in the road (see the decision tree in [`00-overview.md`](00-overview.md)).
2. Classify the file: plain executable, **loader/launcher** (tiny, `Fopen`s another file),
   **packed** (entropy > ~6.7 → depack via Hatari first, [`packed-executables.md`](packed-executables.md)),
   or **data/bitmap**. Don't analyze a packed entry point; you'll disassemble the decompressor.
3. Read *only* the 1–2 domain docs you need next ([`README.md`](README.md) routes by expertise).
   **Never read the binary top-to-bottom** — a 48 KB image is 90% code you'll reach by call graph.

## 2. Anchor on ground truth, propagate outward

Full method in [`methodology.md`](methodology.md). The hierarchy, strongest first: **OS traps**
(annotated for free) → **hardware registers** (`$ffff8240` palette, `$ffff8800` sound, …;
[`hardware-map.md`](hardware-map.md)) → **imported symbols** → **strings** → **interrupt installs**
→ **call graph**. Two facts that shape everything: honor the **relocation table** on load (or every
absolute pointer is garbage and Ghidra finds nothing), and expect games to **bypass the OS** (file
I/O via GEMDOS, everything else direct hardware). Name `main` + the frame loop early — it hands you
the whole architecture.

**Verify a name from the body, never from position/size.** Wrong sticky names are worse than
`FUN_`; several first guesses in BuggyBoy were wrong until read (a "read_input" was `flip_screen`).
Tag a name inferred from call-context (not a full read) with a trailing `# ctx` in `names.txt` so it
reads as refinable, not fact.

## 3. Verify by execution, not by eye — stand up an oracle early

This is the biggest lever and the practice most worth adopting up front. Reading assembly and
"deciding it looks right" does not scale and silently accumulates errors. Instead prove **behavioral
equivalence**: run the *real* machine code and your reconstruction on identical memory + registers
and **diff the result**. The emulator is ground truth, so correctness never rests on a human reading
being right — and once the harness exists you can refactor a dense routine into clean C fearlessly,
because a regression turns a test red instantly.

Set this up as `recreate/` (see [`../projects/buggyboy/recreate/README.md`](../projects/buggyboy/recreate/README.md)
for the reference implementation):

- **Oracle** = a faithful CPU core over a flat memory image whose indices are the binary's real
  addresses (globals sit where the program expects them). **Pick a core faithful to the target
  ISA** — for 68000, Musashi (MAME); Unicorn/QEMU's ColdFire-derived m68k was *rejected* because it
  raises spurious exceptions on byte memory read-modify-write, which pervade hand-written asm.
- **Cross-validate the oracle against a second independent core** on a battery of instruction
  snippets (BuggyBoy runs 277 across the opcode classes it uses, comparing result + *defined* CCR
  bits). This certifies "verified against Musashi" actually means "verified against a real CPU," so
  an emulator quirk can't masquerade as verified.
- **Candidate** = your reconstruction compiled to a shared lib, driven on a copy of the same image.
- Diff the whole image (minus a stack-guard band). Green = byte-for-byte identical.

## 4. Reconstruct each function as **core + glue**

- **Core**: the readable, idiomatic C — real types, named locals, comments on the *why*. No raw
  register names (`a1`, `d0`), no terse `m`/`p` locals.
- **Glue** `g_<name>(image, …)`: unpacks the core's inputs from the image at their real addresses,
  calls the core, writes results back. The glue **is** the function's I/O contract. For a routine
  that takes arguments in registers, the glue takes those registers as parameters and a one-line
  comment maps register→role.
- **Name every non-trivial literal** — addresses, struct/field offsets, table strides, bit masks —
  with a `#define`/const. In reconstructed code a bare `0x1c` hides *which* palette entry or field
  it is; name it even when the meaning is only partly known (`SND_VC_ENABLE`, offset+role).
- **Poison / attribution pass**: after a clean diff, re-run with every oracle-written byte
  pre-inverted. A candidate that "matched" only because its output landed in a region that already
  held the right value (e.g. a zero) now diverges — catching a *coincidental* pass. Opt-in, because
  poisoning an output that also steers control flow can perturb a complex function (see §5's caveat).

## 5. Make hard functions tractable — the techniques that unblock

Most functions run to `rts` on a staged image. The rest need one of these (all proven in BuggyBoy):

| Situation | Technique |
|-----------|-----------|
| Normal function | **Run to `rts`**, diff the final image. Fuzz inputs across seeds. |
| Never returns (infinite game loop, `_start`) | **Checkpoint PC** — run the oracle to a chosen address and diff *there* (`stop_pc=`). Verifies the prefix; the unreachable tail is read-verified. |
| Loops forever / returns only on an event (menu, attract loop) | **Mid-entry slices** — expose each loop body as its own `g_*` helper and enter the oracle at *its* PC; diff each slice. Compose them in the top-level function. |
| Input-driven (keyboard/joystick) | **Model input as data** — the IRQ-set state (`input_state`, …) becomes a harness-poked constant, identical on both sides. One constant per run is a valid differential test; different constants exercise different branches. Model the input hardware registers (status-ready, swallow writes) so busy-waits terminate. |
| OS-bound (GEMDOS/BIOS/XBIOS/GEM) | **Deterministic trap model** — service each trap in the oracle shim with a fixed result (Malloc bump-allocates, Fread serves staged file bytes, palette/sound calls are no-ops). Anything *not* modeled must **raise**, so a function can't be falsely "verified" while hitting an unmodeled call. |
| Orchestrator calling many verified leaves | **World-staging** — stage the *union* of what every callee reads (screen buffers, sprite arenas, per-item records), then run to `rts`. The whole-image diff proves the composition. |

**World-staging's own trap: the SCRATCH REGISTERS an orchestrator carries across a verified leaf's
`rts`.** A leaf's differential compares memory, so its C is typically `void` and promises nothing
about the registers it leaves behind — but hand-written assembly reuses them freely, and a caller
three `bsr`s later may read one as a table index, a bitmask or a sound channel. The composition then
cannot derive it. Three shapes, in increasing order of how much they cost:

* **Derivable.** The value comes from the orchestrator's own instructions (a loop counter the pass
  always runs to its bound). Transcribe it and say where it came from.
* **A parameter.** The value is a callee's leftover. Make it an explicit argument of the slice, with
  the register and the consuming PC named in the comment, and have the case take it FROM THE ORACLE
  at that PC. Everything else stays pinned by the whole-image diff; record the parameter as a
  residual, and name the change that would close it (the callee reporting the register).
* **A flag.** `abcd`/`addx`/`subx` read the X flag, which survives the `movem`/`lea` most call sites
  reach the `bsr` through — so "no caller sets it" is a claim about two instructions and not about
  the register. A leaf that consumes X needs it as a parameter exactly as a register does. Zynaps's
  `score_add_bcd` is the worked case: its own battery entered with X clear and was green, and the
  frame loop then scored one BCD unit high whenever a `subi.b` borrow preceded an award.

The tell for all three is a composition that diverges on a *data-dependent* subset of frames while
every leaf's own battery stays green. Bisect by running the oracle to each block boundary and
diffing the one record that moved.

**Read-verified honesty.** When a path is genuinely unreachable under the model (a debug menu behind
a keyboard read that the model reports as "no key"; the terminal exit after an infinite loop),
reconstruct it faithfully from the disassembly and **document it as read-verified** — don't fake a
test or quietly drop it. State the residual in `STATUS.md`.

**The harness can't see off-image effects.** The differential test proves *image correctness*; it is
blind to anything the oracle models as a no-op — hardware timing (`Vsync`), endianness/codegen cost,
and the trap wrappers themselves. A read-verified path can be byte-perfect and still misbehave when
you compile it to a real `.PRG` (the "no-key" debug menu above actually *does* get keys on hardware).
That whole bug class, its seam pattern, and the on-hardware diagnostic toolkit live in
[`on-target-execution.md`](on-target-execution.md) — read it before shipping a playable build.

**Vet every shortcut.** An `exclude` band that drops bytes from the diff must be provably stack
scratch (not program output). A cap/sample/no-retry in a fuzz must be **logged**, not silent —
silent truncation reads as "covered everything" when it didn't.

## 6. Order of attack

Leaf/pure functions first (no traps, simple contracts) → the callers that compose them → trap-bound
and interactive functions last, once the deterministic trap stubs and input model exist. Port
fall-through/alias entries (a 2–4 byte "function" that falls into the next) together with their
target. This ordering means each function you tackle is built from already-verified pieces, so a new
diff failure is almost always in the new code.

## 7. Keep the loop tight

- **Iterate with `reapply.sh`, not `run.sh`** — re-import wipes names; only bootstrap once.
- **Shard fuzz tests** so no single test item gates the wall clock: split case-generation from
  checking and parametrize by chunk, so `-n auto` spreads thousands of iterations across workers
  with byte-identical coverage.
- **Commit at every logical boundary** (one verified function + its test, a naming sweep, a docs
  pass) — a reconstructed function and its differential test move in the **same** commit. Update the
  docs surfaces (`names.txt`, `STATUS.md`, the relevant `docs/*.md`) in that same commit, not later.
- **Self-review before committing.** Run a review pass over the diff at its scale, fix the real
  findings, keep out-of-scope findings out of the commit (note them). In a byte-exact project this
  catches ISA-faithfulness slips (e.g. a `dbf` loop written as `< 0` instead of `== -1`) that pass
  today's tests but aren't exact.

## 8. Pitfalls that cost hours (learned the hard way)

- **Naming from position/size** → wrong sticky names. Read the body first (§2).
- **Loading a `.PRG` as a flat blob** → no relocations → Ghidra finds nothing. Honor the reloc table.
- **Analyzing a packed entry point** → you disassemble the depacker. Check entropy first.
- **Trusting an emulator with ISA quirks** → phantom bugs / false greens. Use a faithful core and
  cross-validate it (§3).
- **Sweep desync in a linear disassembler** → one bad instruction length garbles everything after.
  Anchor the disassembly on known function starts.
- **Poison on a control-flow-affecting output** → the inverted input diverts the run. Use poison for
  leaves; skip it where an output is also a branch input (read-modify-write counters).
- **Assuming a "one-liner" is trivial** → deferred entries, register side effects, and shared
  fall-through bodies hide in small functions.

## 9. When is a function — and the program — done?

A function is done when it is **green under the differential harness** (byte-for-byte, ideally with
the poison pass), not when it "looks right." The program is done when `main` and the frame loop read
as pseudocode, every function has a meaningful name, the key globals/tables/buffers are labelled,
jump tables and asset formats are documented, and every function is verified (or its residual is
explicitly read-verified in `STATUS.md`).

## 10. When the checker is the thing that is broken

The checks whose whole job is to be loud are the ones that fail quietly, and every form below was
measured in this workspace rather than imagined.

- **The artifact you measured is not the one you built.** Three shapes of one class: `make` relinks
  nothing and a mutation sweep reports phantom survivors unless `rm build/*.so` comes first; a build
  that *fails* leaves the previous mode's `.PRG` on disk, and the smoke run then reports OK against a
  stale binary (fixed by having the build delete its own artifacts before it starts —
  `projects/zynaps/recreate/atari/build.sh`, commit `222ee2d`); and a Python sweep lies the same way
  through `__pycache__`, where restoring a mutated constant within the same mtime second left pytest
  running the cached bytecode and two unrelated cases stayed red after the file on disk was already
  correct (`14da1cd`) — `find . -name __pycache__ -exec rm -rf {} +` is that case's `rm build/*.so`.
  **Force the inputs to be rebuilt before you trust a green or a red.**
- **A shell gate under `set -euo pipefail` dies silently on a grep that matches nothing.** grep exits
  1, the pipeline inherits it, and the assignment aborts the script with no message at all. Measured:
  removing the last marker from a header killed the whole build at the gate's *first line* — the worst
  possible behaviour for the one check whose purpose is to be loud. `|| true` on the grep is
  load-bearing wherever "no matches" is a legal answer.
- **`grep` over several files prefixes every line with `filename:`**, so a `^anchor` pattern after it
  matches nothing, the category comes back empty and every item in it is silently mis-classified.
  `-h` is load-bearing (measured, same gate).
- **A scrape that reads prose scrapes prose.** A comment quoting a prototype was scraped as a
  declaration; a greedy `.*` took the *last* name on a line and inverted two categories. Strip
  comments first, anchor the pattern, and prove each arm on a synthetic input.
- **Make the gate fail closed and mutation-test it.** Count what you parsed against a loose count of
  what is there and refuse a mismatch, so an item written some other legal way is a refusal rather
  than something quietly outside the check. Then flip one thing and watch it redden: a gate nobody has
  seen fail is a gate nobody has tested.

## 11. Before a wave launches — the setup contract

§12 is about running and merging a wave. This one is about what has to be TRUE first, because every
seam failure below was cheap to prevent an hour before the agents started and expensive to unpick at
the merge. Zynaps' successive agent waves are the worked example, and
`projects/zynaps/recreate/README.md`'s "Adding a function" section is the contract itself — written
for the agents to read, not about them.

- **Ownership is by FILE, and the list has three tiers, not two.** Zynaps' table reads: `src/<yours>.c`,
  `include/<yours>.h`, `test/test_<yours>.py` — **you alone**; `include/<someone else's>.h` — **nobody
  but its owner**, include it to READ a global and never edit it; `test_constants.py`,
  `test_status.py`, `Makefile`, `project.toml`, `test/harness.py` — **nobody, in normal work**; and
  `test/abi.py` — shared, append-only, only for a new stub shape. The middle tier is the one a
  two-tier list loses: a file you may *depend on* and may not *touch* needs saying out loud, or the
  first agent that wants a neighbour's constant edits the neighbour's header.
- **Own the ledger by SECTION, not by file.** `STATUS.md` is one file every agent must write to, which
  makes it the worst conflict surface in the tree unless each agent owns a heading — Zynaps gives each
  its own `## Verified — <yours> (N)` section and its count. (The ONE suite-total line is the
  orchestrator's, and §12's first bullet is why.)
- **Decide where a global lives before anyone needs one, and make it a rule with no protocol.**
  Zynaps': *a global lives in the header of the subsystem that owns the data*, any subsystem may
  `#include` another's header to read it, and there is deliberately **no promotion protocol and no
  shared address file** — because either would make a routine edit somebody else's file, which is the
  thing the ownership table exists to prevent.
- **FREEZE the shared record layout, and give every field its provenance.** A record several agents
  port routines against cannot grow field by field during a wave. Zynaps writes the whole 0x2c-byte
  entity record out once, in `projects/zynaps/recreate/include/entity.h`, as a block nobody adds to: *"Freezing it is
  what lets several agents port entity routines at the same time: nobody has to add a field, so nobody
  edits this block, and the field a routine needs is already named."* Each field carries one of two
  tags — `pinned by <test>`, meaning a differential case would fail if the offset were wrong, or
  `names.txt, unpinned`, meaning a read that is believed and unexercised — and **the only permitted
  edit is upgrading a tag in the same change that ports the routine which pins it.** That is stronger
  than orchestrator gatekeeping *and* delegable: `ENTITY_STRIDE` went from `names.txt, unpinned (no
  ported routine steps by it yet)` at the bootstrap (`ab1f18e`) to a tag naming three tests and the
  instruction in each that pins it (`lea 44(a2),a2`, `mulu.w #$2c,d0`).
  **"Append-only in offset order" is the rule that looks right and is not**, because inserting at an
  offset is not appending — two agents appending in offset order write the same file at different
  lines and both are correct. (Zynaps' README records this as the rule it replaced before its first
  commit; that is the project's own account, with no diff behind it, and worth taking as reasoning
  rather than as measurement.)
- **Install the duplicate-definition pin BEFORE the wave, because the compiler cannot be it.** With
  per-subsystem headers **no translation unit includes every header**, so two spellings of one address
  never meet the compiler and nothing diagnoses them. `projects/zynaps/recreate/test/test_constants.py`
  is that diagnosis, in two tests: `test_no_constant_is_defined_in_two_files` — *"One NAME, one
  home"* — and `test_no_address_has_two_spellings`, which checks the `A_*` family only, on the
  reasoning that a shared *offset* carries no information (`ENTITY_X` and a future `SHOT_X` are both 0
  and both right) while a shared *address* is one variable under two names, *"which is how a subsystem
  ends up editing state it does not own."* Both descend from Joust's pair
  (`projects/joust/recreate/test/test_constants.py`), whose second is `test_no_value_has_two_spellings`
  and is **broader**: it compares by a `_comparable_group`, so it also caught one flag bit spelt
  `OBJ_FLAG_TYPE_LO`/`_HI` in one header and `_BIT0`/`_BIT1` in another. Four instances had
  accumulated in Joust before anyone wrote it — which is the argument for having it before the wave,
  not after.
- **Predict the collisions IN WRITING, and say whose diff will go red.** The tripwire tells you a
  clash happened; the ledger row tells the agent who trips it what to do, without reading anyone
  else's subsystem. Zynaps' borrowed-globals table (`projects/zynaps/recreate/STATUS.md`, "## Borrowed
  globals") carried, in `0f38af1`, a row that said so in advance: `A_joystick_state` (`0x19681`) defined in `include/highscore.h` because the routine that
  fills it in was unported, tagged **"THE ONE ROW HERE THAT IS LIKELY TO CLASH SOON"** and naming the
  outcome — *"test_constants.py's duplicate check is what will say so, in the OTHER agent's diff — this
  row is how they find the deletion to make"*, with the five joystick bit masks flagged as moving with
  it. It happened exactly that way: the integrating commit `1d930e7` ported the ACIA handler, the
  definition moved to `include/irq.h`, `highscore.h` kept only a pointer comment, and the row was
  rewritten in place to record it. A prediction that names the failing test, the other agent's diff
  and the edit to make is worth more than any amount of care at the merge.
- **Borrowed-global rows are a LOAN LEDGER, and a closed loan loses its row.** The contract is three
  parts: the **row** (address, name as spelt, owner per the globals census, where it is defined today,
  and why it is on loan), the **`#define` under a BORROWED note** in the borrowing header, and the
  **duplicate pin** as the automatic call-in notice. Zynaps states the payoff in one line — *"Deleting a
  row here and the `#define` it names is the whole of the migration"* — and a finished migration
  normally has its row **deleted rather than annotated**, so the table's length reads as outstanding
  debt rather than as history (two of Zynaps' are gone that way). Its `A_joystick_state` row is the
  deliberate exception, kept and rewritten in place *because* it had predicted its own clash in
  writing: the prediction is only worth anything if the record of it surviving is findable.
- **Declare the cross-file pins PER BATTERY, with a collector that discovers rather than lists.** A
  central registry of "constants the tests restate" is the one file every agent has to edit, so each
  Zynaps battery declares its own `MIRRORS` (a `(python name, C path, C name)` triple) and
  `ENTRY_PROLOGUES` (an entry address against the first bytes of the routine, read off the loaded
  image) at the bottom of its own file, and `test_constants.py` **discovers batteries by the existence
  of `src/<stem>.c`** — so a subsystem another agent adds is required to declare its pins from the
  moment its first function lands, with nobody editing a list. **It fails by NAME**: the message
  carries the battery filename, the Python symbol, the C path and the C symbol, so a red suite tells
  each agent which file *they* own to fix. And note what it replaced, which is §10's lesson in this
  setting: a suite-global "something was checked" assertion *"could never fail for the reason that
  mattered: it stayed green while any ONE battery still declared a pin."*
- **Agents PROPOSE names; they do not edit `names.txt`.** The name map is one file with no ownership
  seam in it at all, and the merge hazard is not a conflict — it is silent deletion. `ApplyNames`
  **sets** a plate comment rather than appending one, reading the file top to bottom with no dedup, so
  a second `cmt` for an address destroys the first, and a wave that appends its findings to the map
  can delete the prose an earlier wave wrote there ([`ghidra-pipeline.md`](ghidra-pipeline.md),
  "Gotchas", has the
  mechanism and the `uniq -d` check; it is live in this workspace — three addresses in
  `projects/zynaps/names.txt` carry two `cmt` lines today). So a wave's naming output goes to a
  **proposals file** the orchestrator merges by hand.
  The shape Zynaps' high-score wave used, which is worth copying: open with *"NOTHING HERE IS IN
  ../names.txt YET. Merge deliberately"*; section it into CORRECTIONS / NEW NAMES / COMMENT
  REFINEMENTS; cite the target line numbers a correction replaces or **deletes**; and record the
  addresses considered and deliberately **not** changed, so the merger knows they were looked at.
  Two honest limits on that example: the file is an untracked working artifact under the gitignored
  `out/`, so the convention is currently written nowhere a reader can chase — putting it in the
  project's own "Adding a function" contract is the fix — and not every pass used one, the later
  dead-code hunt having edited `names.txt` directly (`d833f14`).

## 12. Running a wave of agents

Reconstruction parallelises well — independent subsystems, one agent each, merged into one ledger —
and the failures are all in the seams rather than in the code.

- **Re-sum the ledger's ONE suite line at every merge.** Each wave reports its own count; if nobody
  adds them up the ledger's headline number stays at whichever wave last wrote it. Zynaps' sat
  stranded at wave A's 4,094 through four waves of growth until it was re-derived at 4,751
  (`0f18092`). Same for any "N verified" total the merge does not recompute.
- **After merging a checker, grep for the counterpart of every name you renamed.** A rename made in
  one branch outside the conflict hunks merges clean and fails at *runtime*: a smoke check's
  `PACING_OVERFLOW_SHARE` became `PACING_OVERFLOW_FRAMES` in one wave (`59786c7`) and the next wave's
  merge had to unify it by hand (`6155cc5`). Textual merge is not a type checker.
- **List the untracked files before every commit.** A path-scoped `git add` — which this workspace
  prefers, because `-A` sweeps up concurrent work — leaves an agent's *new* test file behind, and the
  commit then claims a test it does not contain. `git status --short` and read the `??` lines.
- **The same fact written on several prose surfaces drifts.** Zynaps' dead-code hunt found three of
  the project's own surfaces describing one key wrongly (`d833f14`) and, a commit later, a fourth
  disagreeing about how many boots had demonstrated it (`86ddb33`). When you correct one, correct the
  set: the rule is `methodology.md`'s — the correction is landed when the **old phrase greps to
  zero**.
- **An agent that has stopped can be resumed rather than replaced** — a property of the harness
  rather than a measurement here: messaging a stopped agent's id continues it with its context
  intact, so a wave halted by a rate limit does not have to be re-scoped and re-explained. Respawn
  only when you actually want a clean context.

## 13. Porting this to a new target

What transfers unchanged: the anchors→outward method, the oracle-vs-candidate loop, core+glue
modeling, the §5 techniques, the commit/review hygiene. What you swap per target: the **loader**
(header/reloc/segment layout), the **CPU core** (a faithful emulator for the target ISA, plus a
second for cross-validation), the **OS-trap model** (the platform's syscalls), and the **hardware
map** (video/sound/input registers). The methodology is platform-agnostic; only these four adapters
are platform-specific.
