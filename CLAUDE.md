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
│   ├── prg_dis.py            # stdlib GEMDOS .PRG analyzer + 68000 first-pass disassembler
│   ├── extract_graphics.py   # ST 4-plane / RLE graphics -> PNG
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