# TOS / OS Calls

All of TOS (the ST OS) and GEM (its GUI) are reached through 68000 **trap** instructions.
There are no linked OS functions to rename — you identify *call sites* and annotate them,
then name the thin wrappers the game builds around them. `AtariOsTrapAnnotate.java` does
the annotation automatically; this doc is the reference + how to read the results.

## The trap vectors

| Instr | Layer | How the specific call is selected |
|-------|-------|-----------------------------------|
| `trap #1` | **GEMDOS** (files, memory, process) | function # pushed as a word just before: `move.w #sel,-(sp)` |
| `trap #13` | **BIOS** (devices) | selector pushed on stack |
| `trap #14` | **XBIOS** (hardware) | selector pushed on stack |
| `trap #2` | **GEM** | `d0 = 200` → AES, `d0 = 115` → VDI; params via a pointer block in `d1` |

Return value in `d0`. Caller cleans the stack (`addq`/`lea` after the trap).

## Selectors you'll meet most

**GEMDOS (trap #1):** `0x00` Pterm0, `0x09` Cconws, `0x20` Super, `0x2F` Fgetdta,
`0x3C` Fcreate, `0x3D` Fopen, `0x3E` Fclose, `0x3F` Fread, `0x40` Fwrite, `0x42` Fseek,
`0x48` Malloc, `0x4A` Mshrink, `0x4B` Pexec, `0x4C` Pterm.

**XBIOS (trap #14):** `0x00` Initmous, `0x02` Physbase, `0x03` Logbase, `0x04` Getrez,
`0x05` Setscreen, `0x06` Setpalette, `0x07` Setcolor, `0x11` Random, `0x18` Bioskeys,
`0x19` Ikbdws, `0x1C` Giaccess, `0x1F` Xbtimer, `0x20` Dosound, `0x21` Setprt,
`0x22` Kbdvbase, `0x25` Vsync, `0x26` Supexec, `0x27` Puntaes.

These lists are the *common* selectors, not the full tables — the canonical ones the tooling
actually annotates from are the `GEMDOS`/`BIOS`/`XBIOS` dicts in `tools/prg_dis.py` (mirrored in
`AtariOsTrapAnnotate.java`). A selector missing *here* is not evidence that an annotation is wrong.

> **Trap-table warning (learned on Joust, 2026-07-27):** XBIOS opcodes are usually written in
> DECIMAL in TOS references (Dosound = 32, Vsync = 37, Supexec = 38). An early version of this
> doc — and of `tools/prg_dis.py` + `AtariOsTrapAnnotate.java` — copied several decimal numbers
> as if they were hex (`0x20` labelled Supexec when XBIOS 0x20 = 32 = **Dosound**), which
> mislabelled every trap in Joust's sound layer and produced a whole family of wrong function
> names until body reads caught it. When a trap annotation drives a naming decision, check the
> selector against a decimal-keyed TOS reference first — an annotation is an anchor only if the
> table behind it is right.
>
> **The fix does not self-heal an existing project.** `AtariOsTrapAnnotate` runs only during the
> `run.sh` bootstrap; `reapply.sh` is `-noanalysis` and never re-runs it. So a Ghidra DB imported
> under the old table keeps its stale EOL trap comments and any `xbios_<wrongname>` symbol that
> `renameWrappers()` minted (BuggyBoy's DB still carries `xbios_supexec` on a wrapper at `0x12eec`
> that is really **Dosound**). `renameWrappers()` only touches functions still named `FUN_*`, so a
> re-run won't correct it either. `names.txt` overrides the display, which is why nothing downstream
> is mis-reported — but treat a pre-existing DB's trap comments as untrusted until re-imported.

**GEM:** AES opcode in `contrl[0]` (10 appl_init, 77 graf_handle, …); VDI opcode 100 =
v_opnvwk. Register `d0` only tells AES-vs-VDI; the specific function is in the parameter
block's control array, so trace the `contrl` setup to name it precisely.

## Startup patterns to recognize

- **Mshrink prologue**: read basepage at `4(sp)`, compute `tlen+dlen+blen+0x100`, `Mshrink`
  to free RAM above the program. Almost every game opens with this.
- **GEM init then bail to hardware**: `appl_init → graf_handle → v_opnvwk` to get a screen
  handle, then the game bangs hardware directly (BuggyBoy does exactly this).
- **Custom loader** (a small `.PRG` that runs the game): `Fopen`/`Fread` the payload,
  apply its relocation table by hand, fabricate a basepage, `jmp` into it — instead of
  `Pexec` — so it can show a title screen first. Recognize it by the filename string +
  a hand-rolled DRI relocation loop (`add.l base,(ptr)`, `+254` on byte `1`).

## Naming the wrappers

Games wrap common calls in helpers: `move.w #sel,-(sp); trap #1; addq; rts`. Name these
`gemdos_fopen`, `xbios_setpalette`, etc. `AtariOsTrapAnnotate` auto-renames single-trap
wrappers; multi-purpose ones you name by hand. Then callers read as `Fread(...)`,
`Setpalette(pal)` and the data flow becomes obvious.

## Validating a trap model against real TOS (headless)

If you model traps deterministically (e.g. to run code in an emulator without real TOS), you can
pin that model to a genuine ROM without a GUI. Hand-assemble a tiny GEMDOS program that runs the
calls and writes its results to a file, then auto-run it on a headless Hatari over a GEMDOS drive
and read the file back on the host — no debugger, breakpoint, or load address needed:

```bash
SDL_VIDEODRIVER=dummy hatari --sound off --fast-forward on --tos-res low \
  --tos <tos.img> --run-vbls 4000 --harddrive <dir> --auto 'C:\PROBE.TOS'
```

Gotchas: a freshly-run program owns the whole TPA, so **`Mshrink` first** or `Malloc` returns
nothing; `--monitor rgb` (not mono) keeps `Getrez` in low-res. Machine-dependent results (Malloc
base, Physbase) won't equal a fixed model — assert the *invariant* (even-aligned, non-overlapping,
size rounded up), and reserve byte-equality for machine-independent calls (Getrez, `Fread` data +
cursor/EOF counts). Worked example: `projects/buggyboy/recreate/oracle/tos_probe.py`.

→ Direct hardware access (the other 90% of a game): [`hardware-map.md`](hardware-map.md).