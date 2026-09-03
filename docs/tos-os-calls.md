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

### Line-A (`$aXXX`) — the other OS entry, and it is not a `trap`

The 68000 defines no instruction in the `$Axxx` opcode row: executing one takes the
**Line-A exception** (vector 10, `$28`), which TOS points at its **Line-A graphics API**.
So a Line-A call is a bare opcode word inline in the code — no selector push, no `trap`,
and `AtariOsTrapAnnotate` never sees it. Registers, not the stack, carry the arguments.

| Opcode | Call | Opcode | Call |
|--------|------|--------|------|
| `$a000` | Init | `$a008` | TextBlt |
| `$a001` | Put pixel | `$a009` | Show mouse |
| `$a002` | Get pixel | `$a00a` | Hide mouse |
| `$a003` | Line | `$a00b` | Transform mouse |
| `$a004` | Horizontal line | `$a00c` | Undraw sprite |
| `$a005` | Filled rectangle | `$a00d` | Draw sprite |
| `$a006` | Line-by-line filled polygon | `$a00e` | Copy raster form |
| `$a007` | BitBlt | `$a00f` | Contour fill |

`$a000` Init is the one with a return value: it hands back the **Line-A variable block**
in `a0` (screen base, resolution, font and table pointers; `a1`/`a2` get the font header
and the function tables), and must be called before any other Line-A call. Games that
drive the hardware directly still use a couple of these, most often `$a000` and
`$a009`/`$a00a` to show/hide the TOS mouse pointer at startup. Zynaps' `_start` hides the
mouse with `$a00a` four instructions in.

A Line-A word **stops Ghidra's 68000 disassembler dead** (there is no SLEIGH constructor
for it), which can hide most of a program — see
[`ghidra-pipeline.md`](ghidra-pipeline.md), "Line-A opcodes".

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

## Which machine is this? The cookie jar

An STE has hardware an ST does not (DMA sound, the LMC1992 mixer, a hardware scroll), and a program
that wants it has to ask rather than assume. The answer is the **cookie jar**: `_p_cookies` at
**`$5a0`** points at a list of `(id, value)` longword pairs terminated by a zero id, and the
`'_MCH'` cookie (`0x5F4D4348`) carries the machine in the **high word** of its value — `0` plain ST,
`1` STE, `2` Mega STE, `3` TT, `4` Falcon. Reading `$5a0` is **supervisor-only**, so the walk goes
inside `Supexec` or after `Super`.

The walk itself is a short loop; the **hardening around it is the part worth copying**, because the
machines the test exists for are exactly the ones that break it (BLACK ICE's is
`projects/blackice/audio/dma_sfx.c`):

- **"No jar" means "not an STE", and that is the whole test.** The jar arrived with TOS 1.06, which
  is the oldest ROM any STE shipped with (and EmuTOS always builds one), so a machine without a jar
  cannot be an STE. That reasoning is what lets you skip a bus-error probe entirely.
- **TOS 1.00–1.04 never defined `$5a0`**, so on precisely those machines it holds whatever the last
  program left there. Following an odd or wild pointer is a bus error *during boot on a plain ST* —
  a crash caused by the code whose job was to notice the machine has no DMA sound. Validate every
  entry before dereferencing it: the pointer even, at or above `$600` (the system variables end
  there), the whole entry inside `_phystop` (`$42e`), and the scan **capped** (64 entries) so an
  unterminated or circular list — which is what junk at `$5a0` usually decodes to — cannot spin the
  boot for ever.
- A host-compiler note that comes with reading page zero at all: dereferencing a literal address is
  an array subscript far outside any object GCC knows about, so `-Warray-bounds` has to be suppressed
  **scoped to those two reads** rather than switched off for the file.

*(Hatari 2.6.1 + EmuTOS and TOS 1.04; the "no jar ⇒ not an STE" arm has only been exercised on
1.04, where `$5a0` happened to be readable — `projects/blackice/audio/REPORT.md`, "What is
unverified".)*

## `Setscreen` does three things, and two of them surprise people

XBIOS `Setscreen(log, phys, rez)` is the call a game uses to point the shifter at its own buffers,
and each of its side effects has been a bug in this workspace:

- **It CLEARS the screen it is given** when handed a real resolution. Switch the mode *first* and
  draw *after*: BLACK ICE blitted its HUD backdrop and then switched, and TOS wiped the strip on the
  way — which the pixel surface reported as "the HUD's rules are not at lines 160 and 168", i.e. as
  a geometry bug (`projects/blackice/atari/main.c`, `enter_game_video`).
- **It sets `_v_bas_ad`**, which is what you want: TOS's own vertical blank then keeps writing *your*
  base every frame instead of restoring the desktop's.
- **SET the resolution; do not merely save it.** Saving the old rez and passing "keep" is the shape
  of a bug that only appears when the program is launched from a medium-res desktop: 320×200
  four-plane data read 640 pixels wide in two planes is nonsense, and it looks like a renderer fault.
  The matching refusal is a **mono monitor** — the shifter has exactly one resolution there, so a
  program that needs low-res has nothing to draw on and should say so in text rather than switch
  anyway and leave the user at a black screen with no way back.

Restore all three on the way out (`Setscreen(saved_log, saved_phys, saved_rez)`), and prove it —
[`on-target-execution.md`](on-target-execution.md), "The observable surfaces", has the control-boot
rule that makes such a check measure your program rather than the OS.

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

**This recipe needs TOS 1.04 or later.** Hatari refuses GEMDOS directory emulation on older ROMs,
says so once, and then boots normally with no C: at all:

```
Please use at least TOS v1.04 for the HD directory emulation (all required GEMDOS functionality
isn't completely emulated for this TOS version).
```

The `--auto` program therefore never runs and the probe's output file is *missing* rather than wrong
— a symptom that reads like a broken probe. Check for that line before believing an empty result, and
to exercise TOS 1.00/1.02 put the program on a floppy image instead of in a directory.

Gotchas: a freshly-run program owns the whole TPA, so **`Mshrink` first** or `Malloc` returns
nothing; `--monitor rgb` (not mono) keeps `Getrez` in low-res. Machine-dependent results (Malloc
base, Physbase) won't equal a fixed model — assert the *invariant* (even-aligned, non-overlapping,
size rounded up), and reserve byte-equality for machine-independent calls (Getrez, `Fread` data +
cursor/EOF counts). Worked example: `tools/recreate_kit/oracle/tos_probe.py`.

→ Direct hardware access (the other 90% of a game): [`hardware-map.md`](hardware-map.md).