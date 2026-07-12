# Ghidra Pipeline

Ghidra does the heavy lifting: with relocations applied it discovers functions and its
68000 decompiler emits readable C. The scripts in `tools/ghidra_scripts/` (all **Java** —
Ghidra 12 dropped bundled Jython) automate load, annotate, export, and naming. For
interactive exploration in the GUI, see [`ghidra-gui.md`](ghidra-gui.md).

## Install / launch (macOS, Homebrew)

- GUI: `ghidraRun`. Headless: `.../libexec/support/analyzeHeadless`.
- Homebrew ships `openjdk@21` keg-only; the shell scripts set `JAVA_HOME` to it. If your
  sandbox blocks a Bash call that sets env vars, run the `.sh` yourself with `!`.

## The four scripts

| Script | Role |
|--------|------|
| `PrgLoader.java` | Rebuild memory: create TEXT at base (arg 2, default `0x10000`), apply **all** relocations in place, import DRI symbols as labels, set entry, disassemble. Args: `<prg-path> [base_hex]`. GUI: prompts for the file. |
| `AtariOsTrapAnnotate.java` | Comment every `trap` with its call name (GEMDOS/BIOS/XBIOS from the pushed selector; GEM AES/VDI from `d0`), and rename thin single-trap wrappers. |
| `ExportDecompC.java` | Decompile every function to a text file (arg 1), with a function index. This is your reading material. |
| `ApplyNames.java` | Apply a `names.txt` map (`fn`/`var`/`cmt`) back into the DB; disassembles+creates functions for jump-only handler stubs. Strips a trailing `# ctx` confidence tag on `fn`/`var` lines. |
| `DumpNames.java` | The reverse: export the DB's current non-default function names, data labels, and plate comments **back** to `names.txt` format — use it to recover names made/edited in the GUI. |

## Bootstrap (once per game)

```bash
bash projects/<name>/run.sh          # wraps tools/headless.sh
```
This raw-imports the PRG (`68000:BE:32:default`, BinaryLoader base 0), runs `PrgLoader`
**as a pre-script** (before analysis, so analysis sees the correct memory), then
auto-analysis, then trap annotation, then `ExportDecompC` → `decomp.c`. The Ghidra
project is left in `projects/<name>/ghidra_proj/` — openable in the GUI.

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

## Gotchas

- `run.sh` **re-imports and wipes names** — only for the first bootstrap; iterate with `reapply.sh`.
- If `ApplyNames` reports fewer applied than expected, an `fn` address may be data or an
  unreached jump target; it disassembles+creates then, but verify it landed.
- One program per project keeps `-process <PROG.PRG>` unambiguous.

→ Next: [`methodology.md`](methodology.md) for how to choose names.