# CLAUDE.md — Atari ST Reverse-Engineering Workspace

This workspace turns an Atari ST program/game binary back into readable, named,
decompiled code. It is **tool + knowledge**, reusable for **any** GEMDOS `.PRG`.
The `buggyboy` project is the worked reference example (fully solved).

## What you are doing

Recovering lost source from an Atari ST binary: parse the executable, disassemble
the 68000 code, drive Ghidra to decompile it, then iteratively **name** functions
and variables until the program reads like source.

## Golden path

1. **Orient** — read [`docs/00-overview.md`](docs/00-overview.md) (the end-to-end
   workflow + a decision tree for "what kind of file is this?").
2. **Pick the domain doc(s)** you need — see [`docs/README.md`](docs/README.md).
   Each doc is written for one area of expertise (formats, 68k, Ghidra, OS, hardware,
   graphics, sound, methodology) and is grounded in real BuggyBoy evidence but
   written as general procedure.
3. **Scaffold a project**: `bash tools/new_project.sh <name> <path/to.PRG>`.
4. **Bootstrap**: `bash projects/<name>/run.sh` → analyzed Ghidra project + `decomp.c`.
5. **Name loop**: read `decomp.c` → append `fn/var/cmt` lines to `names.txt` →
   `bash projects/<name>/reapply.sh` → re-read. Repeat until named.

## Layout

```
reverse/
├── CLAUDE.md                 # this file
├── docs/                     # transferable knowledge, one file per expertise domain
├── tools/                    # game-agnostic tooling
│   ├── prg_dis.py            # stdlib GEMDOS .PRG analyzer + 68000 first-pass disassembler (prints entropy)
│   ├── extract_graphics.py   # ST 4-plane / RLE graphics -> PNG
│   ├── depack_gamex.py       # static depacker for the Gamex/"PP" LZSS cruncher (.CTE -> .PRG)
│   ├── ghidra_scripts/       # PrgLoader, AtariOsTrapAnnotate, ExportDecompC, ApplyNames, DumpNames, LoadDump
│   ├── headless.sh           # bootstrap: import->load->analyze->annotate->export
│   ├── reapply.sh            # fast naming loop: apply names.txt -> re-export
│   ├── dump_names.sh         # reverse: export DB names -> names.txt format (recover GUI edits)
│   ├── hatari_run.sh         # launch a game in Hatari (run depacker, then dump memory)
│   ├── load_dump.sh          # analyze a raw memory dump (depacked game) — see docs/packed-executables.md
│   └── new_project.sh        # scaffold projects/<name>/
└── projects/<name>/          # per-game: bin/ names.txt decomp.c ghidra_proj/ out/ run.sh reapply.sh
```

## Conventions

- **Name map format** (`names.txt`), one directive per line:
  - `fn 0x<addr> <name>` — name/define a function
  - `var 0x<addr> <name>` — label a data address (renames Ghidra `DAT_*`)
  - `cmt 0x<addr> <text>` — plate comment
  - `param 0x<addr> <ordinal> <name>` — rename a recovered function parameter (safe; no
    storage/convention change). For register-glue functions, put the register→role map in a `cmt`.
  - `proto 0x<addr> <name@loc> …` — commit a signature with explicit storage when Ghidra
    never recovered params. `loc` = stack `off:size` (e.g. `dst@4:4`) or a register (e.g. `n@D0`).
    Verify the storage against the asm first — wrong storage breaks the decompile.
  - Addresses are **Ghidra addresses** = image offset + load base (default `0x10000`).
  - **Confidence tag**: a trailing `# ctx` on an `fn`/`var` line marks a name inferred
    from call-context, not a confirmed body read (refinable). `ApplyNames` strips it.
- **GUI ↔ names.txt sync**: `names.txt` is the source of truth. If you rename in the GUI,
  run `dump_names.sh` (→ `out/names_dump.txt`), diff against `names.txt`, and merge — so
  a later re-import doesn't lose GUI edits.
- **Verify before you name.** Read the decompiled body; don't name from position or a
  hunch (see `docs/methodology.md` — several first-guess names were wrong until read).
- **Anchors → outward.** Start from ground truth (OS traps, symbols, hardware regs,
  strings), then propagate along the call graph.

## Gotchas (learned the hard way)

- **Ghidra 12 dropped Jython** — scripts must be **Java**, not `.py` (PyGhidra needed
  otherwise). All `tools/ghidra_scripts/*.java` run out of the box.
- **JAVA_HOME**: Homebrew Ghidra ships `openjdk@21` but keg-only; the shell scripts set
  `JAVA_HOME` themselves. Some sandboxes block a Bash call that sets env vars — if so,
  run the `.sh` yourself with the `!` prefix.
- **Load base `0x10000`** keeps the image clear of the 68k vector page; it's arbitrary
  (PRGs are position-independent via their reloc table). Override: `run.sh` arg / PrgLoader arg 2.
- **`run.sh` re-imports and wipes names** — only for first bootstrap. Iterate with `reapply.sh`.

## Working conventions (code + commit hygiene)

Adapted from `research_ops/CLAUDE.md`. Same bar; the docs gate points at this workspace's
surfaces (`names.txt` / `STATUS.md` / `docs/`) instead of a handbook.

### Branch workflow
- **`main`** — canonical history.
- **`ganneheim/dev`** — daily WIP; all work happens here. Merge into `main` (fast-forward
  when possible) to promote. Local-only repo today; push once a remote is added.

### Commit cadence
Default to smaller commits. **Propose a commit at every logical boundary without being
asked** — one verified function, a naming sweep, a docs pass, ~10 meaningful edits. One
giant end-of-session commit is a smell; split it retroactively before promoting.

### Pre-commit code-review gate
Review the change for quality *before* the docs. Audit the diff against the bar of *code a
human or agent can read and safely extend months from now*, then fix what you find (or
justify leaving it):
- **Correctness** — re-check edge cases and every call site the diff touches. A reconstructed
  function must be **green under `make test`** (differential vs the Musashi oracle) before it
  is committed — that is the success criterion, not "looks right".
- **Test coupling** — a reconstructed function and its differential test
  (`recreate/test/test_*.py`) move together in the *same* commit; a new function ships with
  its test. A behaviour change with no matching test movement is the smell. A big fuzz test
  (thousands of iterations) should be **shardable across xdist workers** — split case
  generation from checking and parametrize by `chunk` so `make test` (`-n auto`) stays fast;
  see the "Writing a fuzz test so it parallelizes" recipe in `recreate/README.md`.
- **Low complexity / no duplication / readability** — simplest form that works; logic that
  appears twice collapses into one named helper; intention-revealing names; comment the
  *why*. No raw register names (`a1`, `d0`–`d7`) or terse locals (`m`, `p`, `rd`) — use
  semantic names with the register map in a one-line comment (see `recreate/README.md`).
- **Line length ≤160 chars** — wrap past that (one arg per line / idiomatic multi-line);
  don't split a clean 161-char line awkwardly, and follow any project autoformatter over this.
- **No magic numbers** — name any non-trivial literal with a `#define`/const: addresses
  (`0x1bc56`), struct/field offsets (`0xa`, `0x1c`), sizes, table strides, bit masks
  (`0xff00`). This matters doubly in reconstructed code, where a bare hex offset hides which
  struct field or address it is. Name it even when the field's *meaning* is only partly known
  (offset+role, e.g. `SND_VC_ENABLE`). Genuinely self-evident values are fine inline — `0`/`1`,
  a `<< 3` shift, a loop's `+ 2` step, `& 0xff` on a byte — don't over-name to the point of noise.
- `/code-review` automates the diff sweep — run it at the change's scale, fix the real
  findings, and **keep out-of-scope findings out of the commit** (note them, don't fold them in).

### Pre-commit docs gate
Docs are part of the change, not a follow-up. Before staging, update every surface that
applies, in the *same* commit:
- **`names.txt`** — the name map is the source of truth; new/renamed functions or globals land here.
- **`recreate/STATUS.md`** — per-function progress (verified count + row) when a function is ported.
- **`docs/<area>.md`** — when a mechanism, binary format, or gotcha is discovered.
- **README** (`projects/<name>/README.md`, `recreate/README.md`) — when the approach or layout moves.

### Commit message style
- **No `Co-Authored-By: Claude` footer.** The researcher commits as themselves.
- Title ≤70 chars.
- Body grouped by category where useful (Reconstruction / Harness / Docs / Deferred).

### Git safety rails
- Never `--no-verify`, `--force`, or `--amend` a shared/merged commit — create new commits.
- **Prefer `git add <paths>` over `git add -A`** — this workspace has concurrent work in
  other projects (`projects/joust/`, `tools/`); `-A` sweeps their changes into your commit.
  Verify `git diff --cached --stat` before committing.
- Confirm before destructive ops (`reset --hard`, `checkout --`, `clean -f`).

### Edit / topic-switch hygiene
- Extend `old_string` through the closing brace / end-of-block, so a mismatch fails loudly
  rather than silently corrupting mid-function.
- Verify every tool / command / symbol exists before using it — grep the repo, read the
  disassembly; don't invent names.
- Announce "switching from X to Y"; offer to commit the previous topic first. Don't let
  unrelated changes pile up in one working tree.