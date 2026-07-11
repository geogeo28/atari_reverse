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
`0x05` Setscreen, `0x06` Setpalette, `0x07` Setcolor, `0x1F` Vsync, `0x20`/`0x26` Supexec,
`0x28` Xbtimer, `0x2A` Dosound.

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

→ Direct hardware access (the other 90% of a game): [`hardware-map.md`](hardware-map.md).