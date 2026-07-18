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

## 10. Porting this to a new target

What transfers unchanged: the anchors→outward method, the oracle-vs-candidate loop, core+glue
modeling, the §5 techniques, the commit/review hygiene. What you swap per target: the **loader**
(header/reloc/segment layout), the **CPU core** (a faithful emulator for the target ISA, plus a
second for cross-validation), the **OS-trap model** (the platform's syscalls), and the **hardware
map** (video/sound/input registers). The methodology is platform-agnostic; only these four adapters
are platform-specific.
