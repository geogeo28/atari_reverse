# Ghidra GUI Usage

The headless pipeline ([`ghidra-pipeline.md`](ghidra-pipeline.md)) does batch load/analyze/
name. The **GUI is for exploration**: reading the decompiler interactively, chasing
cross-references, and spot-renaming. This doc covers driving it and keeping it in sync
with the reproducible `names.txt` loop.

## Launch & open the project

```
ghidraRun
```
(Homebrew's `ghidraRun` wrapper sets `JAVA_HOME` to `openjdk@21` itself — you don't need
to.) First launch may hit a macOS Gatekeeper prompt for a bundled native lib (unsigned
Homebrew build) → allow in System Settings → Privacy & Security.

In the **Project Manager**: `File → Open Project…` →
`reverse/projects/<name>/ghidra_proj/<Name>.gpr` → double-click the program
(`<GAME>.PRG`) to open the **CodeBrowser**.

## CodeBrowser layout

- **Listing** (center) — disassembly with addresses, xrefs, comments.
- **Decompiler** (right; `Window → Decompile` if hidden) — C-ish view of the current
  function. Your main reading surface.
- **Symbol Tree** (left) — Functions / Labels / Imports; the fastest way to jump to a
  named function (`main`, `game_update`, …).
- Handy windows: `Window → Defined Strings` (filenames, menu text, credits),
  `Window → Function Call Trees` (callers/callees), `Window → Bytes` (raw hex).

## Navigation & editing keys

| Key / action | Does |
|--------------|------|
| `G` | Go To an address or symbol (e.g. `0x10100`, `main`) |
| double-click a reference | follow it; toolbar ←/→ (or `Alt+Left/Right`) = back/forward |
| `L` | rename the label / function / variable under the cursor |
| `Ctrl+L` | retype a decompiler variable |
| `F` | edit function signature |
| `;` | set an EOL comment (right-click → Comments for pre/plate) |
| `Ctrl+Shift+F` | find references *to* the current item |

The decompiler and listing are linked — click in one, the other follows.

## Keeping GUI and `names.txt` in sync (important)

`names.txt` is the **reproducible source of truth**: the DB is regenerable from `bin/` +
`names.txt` via `reapply.sh`. The GUI writes directly into the DB, so the two can diverge.
Pick a discipline:

- **Recommended:** GUI = read-only exploration; do all naming in `names.txt` +
  `reapply.sh`. Reproducible, reviewable, survives a re-import.
- **If you rename in the GUI**, recover those edits with `dump_names.sh`
  (`projects/<name>/dump.sh` → `out/names_dump.txt`), then diff and merge new/changed
  lines into `names.txt`:
  ```bash
  bash projects/<name>/dump.sh
  diff <(grep -E '^(fn|var|cmt) ' projects/<name>/names.txt | sort) \
       <(grep -E '^(fn|var|cmt) ' projects/<name>/out/names_dump.txt | sort)
  ```
  GUI names are `USER_DEFINED` (sticky across re-analysis) but a fresh `run.sh` re-import
  starts clean — so always fold GUI edits back into `names.txt`.

**Lock collision:** an open project holds a lock, so `reapply.sh` (`-process`) will fail
while the GUI has the program open. Close the program tab (or the project) before running
the headless scripts, then reopen.

## Running the workspace scripts from the GUI

`Window → Script Manager` → the "Manage Script Directories" (bundle) icon → add
`reverse/tools/ghidra_scripts` → refresh. The scripts appear under category **Atari.ST**.

- `AtariOsTrapAnnotate` runs fine interactively (no args) — re-annotate traps + rename
  single-trap wrappers after more disassembly appears.
- `ApplyNames` / `ExportDecompC` expect a **script argument** (map path / output path),
  which the GUI doesn't pass conveniently — prefer running those **headless** via
  `reapply.sh`. Use the GUI for `Analysis → Auto Analyze` and interactive work.

## Typical GUI session

1. Open the project; jump to `main` (Symbol Tree) and read down the call graph in the
   decompiler.
2. Use `G` / double-click to chase an unknown `FUN_*`; confirm what it touches
   (hardware regs, traps).
3. Decide the name → add a `fn/var/cmt` line to `names.txt` (don't just rename in-GUI,
   per the sync rule).
4. When you've batched several: close the program, `bash reapply.sh`, reopen — the
   decompiler now reads with the new names, unlocking the next layer.

→ Batch mechanics: [`ghidra-pipeline.md`](ghidra-pipeline.md). Choosing names:
[`methodology.md`](methodology.md).