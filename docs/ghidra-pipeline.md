# Ghidra Pipeline

Ghidra does the heavy lifting: with relocations applied it discovers functions and its
68000 decompiler emits readable C. The scripts in `tools/ghidra_scripts/` (all **Java** —
Ghidra 12 dropped bundled Jython) automate load, annotate, export, and naming. For
interactive exploration in the GUI, see [`ghidra-gui.md`](ghidra-gui.md).

## Install / launch (macOS, Homebrew)

- GUI: `ghidraRun`. Headless: `.../libexec/support/analyzeHeadless`.
- Homebrew ships `openjdk@21` keg-only; the shell scripts set `JAVA_HOME` to it. If your
  sandbox blocks a Bash call that sets env vars, run the `.sh` yourself with `!`.

## The scripts

| Script | Role |
|--------|------|
| `PrgLoader.java` | Rebuild memory: create TEXT at base (arg 2, default `0x10000`), apply **all** relocations in place (the DRI `1` byte is a 254-byte SPAN, not a fixup — getting that wrong corrupts one longword every 254 bytes, see [`binary-formats.md`](binary-formats.md)), import DRI symbols as labels, set entry, disassemble. Args: `<prg-path> [base_hex]`. GUI: prompts for the file. |
| `LineAResolve.java` | Resolve Line-A (`$aXXX`) opcodes so disassembly does not stop at them: define the word as data with a naming comment, fall-through-override past it, resume disassembly, re-body the host function. Arg `reanalyze` re-runs analysis over its changes. See "Line-A opcodes" below. |
| `SeedFunctions.java` | Create a function at the start of every run of disassembled code that belongs to none — branch-only entry points and jump-table arms Ghidra reached but never attributed, which `ExportDecompC` would otherwise skip. Never seeds from a linear sweep. |
| `AtariOsTrapAnnotate.java` | Comment every `trap` with its call name (GEMDOS/BIOS/XBIOS from the pushed selector; GEM AES/VDI from `d0`), and rename thin single-trap wrappers. |
| `ExportDecompC.java` | Decompile every function to a text file (arg 1), with a function index. This is your reading material. |
| `ApplyNames.java` | Apply a `names.txt` map (`fn`/`var`/`cmt`) back into the DB; disassembles+creates functions for jump-only handler stubs. Strips a trailing `# ctx` confidence tag on `fn`/`var` lines. |
| `DumpNames.java` | The reverse: export the DB's current non-default function names, data labels, and plate comments **back** to `names.txt` format — use it to recover names made/edited in the GUI. |
| `HwPortabilityScan.java` | Dump function bodies, the call graph, and every hardware/off-image memory access (with direction, size, and whether the read steers a branch) to a TSV. Args: `<out.tsv> [image_size_hex]`. Drive it with `tools/hw_scan.sh`; classify with `tools/hw_portability.py` — see [`on-target-execution.md`](on-target-execution.md), "Measure the blindness". |

> ### If your DB predates the `PrgLoader` relocation fix, RE-BOOTSTRAP IT
>
> `PrgLoader` used to treat the DRI relocation table's `1` byte as a fixup instead of a 254-byte
> span, corrupting one longword every 254 bytes of every program it loaded. Measured spurious
> fixups: **BuggyBoy 93, Joust 44, Wonder Boy 536** (against 3 real ones). `reapply.sh` does *not*
> re-import, so a DB built before the fix stays corrupt however many times you re-apply names, and
> the corruption is silent — it deletes hardware operands, invents others, and shifts immediates.
> Reconstructions are unaffected (the differential oracle always used `prg_dis.parse_reloc`, which
> was correct), but every `decomp.c`, every disassembly read out of the GUI, and any name derived
> from a corrupted operand are suspect. `ghidra_proj/` and `decomp.c` are gitignored, so the fix
> costs only time: `bash projects/<name>/run.sh` then `bash projects/<name>/reapply.sh`.

## Bootstrap (once per game)

```bash
bash projects/<name>/run.sh          # wraps tools/headless.sh
```
This raw-imports the PRG (`68000:BE:32:default`, BinaryLoader base 0), runs `PrgLoader`
**as a pre-script** (before analysis, so analysis sees the correct memory), then
`LineAResolve`, auto-analysis, `LineAResolve reanalyze` + `SeedFunctions`, then trap
annotation, then `ExportDecompC` → `decomp.c`. The Ghidra project is left in
`projects/<name>/ghidra_proj/` — openable in the GUI.

`LineAResolve` runs twice on purpose: before analysis it unblocks the entry path, and
after analysis it catches Line-A words in code only auto-analysis reached.

Why raw import + pre-script (not a custom Ghidra Loader)? A real Loader needs a Gradle
build against your Ghidra install; the pre-script approach is zero-build and equivalent.

**Processor** defaults to `68000:BE:32:default`. For programs that use 68010/020/030
instructions (`movec`, `moves`, extended addressing), pass `68000:BE:32:MC68030` as the
6th arg to `headless.sh` (or `new_project.sh <name> <prg> <base> 68000:BE:32:MC68030`) so
the decompiler decodes them instead of flagging "unable to resolve constructor". Base
68000 is right for the vast majority of ST games.

## The naming loop (the actual work)

```
read decomp.c → decide names → append fn/var/cmt lines to names.txt → reapply.sh → re-read
```
```bash
bash projects/<name>/reapply.sh      # apply names.txt + re-export decomp.c (no re-analysis)
```
Names are `SourceType.USER_DEFINED` (sticky — a later re-analyze won't clobber them).
`names.txt` is the durable source of truth; the Ghidra DB is regenerable from bin + names.

`names.txt` directives (Ghidra addresses = image offset + base):
```
fn  0x10100 main
var 0x18bfc mem_base
cmt 0x10100 Game driver: never returns.
fn  0x15872 draw_crash_fx   # ctx   (named from call-context, not a body read; refinable)
```
A trailing `# ctx` tags a low-confidence, context-inferred name — `ApplyNames` ignores it.

**Recovering GUI edits.** If you rename in the CodeBrowser, run `dump_names.sh`
(→ `out/names_dump.txt`), diff against `names.txt`, and merge new/changed lines back —
`names.txt` stays the source of truth and survives a future re-import.

## Line-A opcodes (`$aXXX`) — one word can hide a whole program

**Symptom.** Auto-analysis finds a handful of functions in a 40 KB program, and the log
carries `WARN Decompiling <addr>, pcode error at <addr>: Unable to resolve constructor`.
On ZYNAPS17.PRG that was **44 functions** found, `_start` exported as 16 bytes, and 1 of
its 4 trap sites annotated.

**Mechanism.** The 68000 has no instruction in the `$Axxx` row — it takes the Line-A
exception, which TOS routes to its graphics API (`$a000` init, `$a00a` hide mouse, … see
[`tos-os-calls.md`](tos-os-calls.md), "Line-A"). Games call them inline, mid-function.
Ghidra's 68000 SLEIGH has no constructor for `$aXXX`, so **disassembly halts at that
word**. Zynaps' `_start` hides the mouse at `0x10010`, five instructions in; everything
reached through its ~150 `bsr.w` calls stayed undiscovered.

**What `LineAResolve` does.** For each instruction whose fall-through lands on an
undisassembled `$aXXX` word: define the word as 2-byte data with an EOL comment naming
the call, give the *preceding* instruction a fall-through override past it
(`Instruction.setFallThrough`), disassemble from the next word, and — after the fixed
point — recompute the body of the function the site sits in with
`CreateFunctionCmd.fixupFunctionBody` (a body is frozen when the function is created, so
without this `_start` still exports as 16 bytes). Repeated until no new sites appear.

**Limitation — the C can be positively WRONG, not merely incomplete.** The override
models the Line-A call as a **no-op**, but a Line-A call destroys `d0`–`d2`/`a0`–`a2`, and
`$a000` *returns* the Line-A variable block in `a0` (font header in `a1`, tables in `a2`).
So

```
lea   tbl,a0
dc.w  $a000        ; a0 := Line-A variable block
move.l 2(a0),d1
```
decompiles as a read of **`tbl+2`** when the hardware reads `Line-A_var_block+2`. Never
trust `d0`–`d2`/`a0`–`a2` across a site without reading the comment the script leaves
there — a pre-comment at the resume address, so it lands in `decomp.c`, not just in the
GUI listing (the decompiler's EOL-comment option is off by default). A site whose
registers are all reloaded before use — Zynaps' single `$a00a` — is unaffected. What you
get either way is a `_start` that decompiles end to end instead of truncating.

The script also reports any `$a00x` word it could **not** resolve: one that a branch or
call jumps straight to, which the fall-through detection does not cover. It requires an
incoming flow reference before reporting, because a value-only sweep is nearly all false
positives — on `JOUST.PRG` it flags 4 words, every one of them a sprite bitmap row.

**Result on Zynaps** (`bash projects/zynaps/run.sh`):

| | before | after |
|---|---|---|
| functions | 44 | 159 |
| trap sites annotated | 1 | 4 (every real one) |
| `decomp.c` lines | 1,416 | 8,273 |

The remaining trap sites a linear sweep reports are not misses: three are ASCII inside
string tables (`"CODING"` → `4e47` = `trap #7`), and the XBIOS `Xbtimer` at `0x16abe` sits
in a routine with **no reference anywhere in the image** — dead code no flow-based
analysis can reach. Chase those by hand in the GUI, not by seeding from a linear sweep.

## Gotchas

- `run.sh` **re-imports and wipes names** — only for the first bootstrap; iterate with `reapply.sh`.
- If `ApplyNames` reports fewer applied than expected, an `fn` address may be data or an
  unreached jump target; it disassembles+creates then, but verify it landed.
- **`ApplyNames` REPLACES, so a second `cmt` for one address DELETES the first.** The file is read
  strictly top to bottom and the `cmt` arm is `setPlateComment(addr, …)` — a set, with no dedup and
  no address index — so for any address carrying two `cmt` lines the **last one in the file wins**
  and the earlier prose is gone from the DB. `fn` and `var` are last-wins too, but a name overwrite
  is visible where a plate-comment overwrite silently deletes text that exists nowhere else. Check
  before and after every naming pass, and especially after merging a wave's proposals:

  ```bash
  awk '/^cmt /{print $2}' projects/<name>/names.txt | sort | uniq -d   # must print nothing
  ```
- One program per project keeps `-process <PROG.PRG>` unambiguous.
- "Unable to resolve constructor" has two causes: a Line-A `$aXXX` word (above), or a
  68010/020/030 instruction — for the latter, re-bootstrap with the `MC68030` processor.

→ Next: [`methodology.md`](methodology.md) for how to choose names.