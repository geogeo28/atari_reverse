# Bubble Ghost — first anchors from `decomp.c`

Ground truth read out of `GHOST_PLAIN.PRG` (the decrypted image — see
[`loader.md`](loader.md)) at the project's load base `0x10000`, in the run-time layout `run.sh`
builds (below). Everything here was read from a body; anything inferred only from call context is
tagged as such, here and in `out/names_proposals.txt`.

## Shape of the image

**The Ghidra image is the RUN-TIME image, not the file.** `run.sh` rewrites `bin/GHOST_PLAIN.PRG`
into `bin/GHOST_RT.PRG` with `tools/prg_relayout.py`, which reproduces the segment move the crt0
performs (next section) — so the project holds `[ TEXT ][ BSS ][ DATA ]`, and a **Ghidra address
is the address the instruction really touches**. No conversion, in either direction.

| region | Ghidra = run-time address | size | contents |
|---|---|---:|---|
| jump table | `0x10000`–`0x10035` | 54 | nine `jmp $xxxx.l` — the program's **only nine relocations** |
| code | `0x10036`–`0x171d2` | 29 KB | 134 functions |
| graphics/tables | `0x171d2`–`0x1e8ca` | 30 KB | inside TEXT: entropy 3.35, no `link a6` anywhere |
| bss | `0x1e8ca`–`0x24f1a` | 26 KB (`0x6650`) | the game's variables — zeroed by the crt0 |
| data | `0x24f1a`–`0x2520e` | 756 | all the program's strings |

`a4` = **`0x24f1a`**, the BSS/DATA boundary. `run.sh` pins it as a tracked register value
(`ghidra_scripts/SetRegisterValue.java`) before analysis, so a global that the linear listing
shows as `n(a4)` decompiles as `DAT_<that same address>` — `0x24f1a + n`, signed. That is the one
arithmetic rule you need: `-26170(a4)` is `DAT_0001e8e0`, `664(a4)` is `0x251b2`.

**Ghidra found 134 functions** (123 decompiled, 11 failed — all in the C library: `0x14c1e`,
`0x14fb0`, `0x150ee`, `0x153fe`, `0x159dc`, `0x1667c`, `0x16a26`, `0x16a5e`, `0x16a86`,
`0x16ae2`, `0x16c04`). That is the whole code segment: the 30 KB after `0x171d2` is data, not
undiscovered code. The 134th is `FUN_000237bc` — an artefact worth keeping, not a function in the
image: it is the `jsr a4-5982` target, i.e. where `GHOST.LOA`'s own text lands *inside the BSS*
once the game has read the file there (see the file table below), and with `a4` known Ghidra now
resolves that call to a real address.

The C startup reaches the global-data initialiser at `0x16d8e` only through `jsr 48(a5)` with
`a5 = p_tbase`, so flow analysis never disassembles it; `run.sh` seeds that one address as a
pre-script so auto-analysis follows it. Two jump-table targets, `0x15136` and `0x15190`, land
*inside* `FUN_00015132` and `FUN_0001518c` rather than starting functions of their own; worth
re-checking when those are named.

## The compiler's memory model — read this before naming any global

This is **Alcyon/DRI C, small model**, and its `a4` convention explains every `<off>(a4)` in
`decomp.c`. From the startup at `0x10036`:

```
movea.l 24(a5),a0 / movea.l 24(a5),a1 / adda.l 28(a5),a1   ; a0=p_bbase, a1=p_bbase+p_blen
move.b -(a0),-(a1)  …                                      ; move the DATA segment ABOVE the BSS
movea.l 16(a5),a0 / clr.b (a0)+  …                         ; clear p_blen bytes from p_dbase
movea.l 16(a5),a4 / adda.l 28(a5),a4                       ; a4 = p_dbase + p_blen
```

DATA moves **up** by `p_blen`, the copy running backwards so the overlap is safe; the clear
then zeroes `p_blen` bytes from `p_dbase`, i.e. the whole BSS in its new home. Nothing else is
copied — every non-zero global is written one `move` at a time by `init_globals` (`0x16d8e`).
`Mshrink` keeps `p_tlen + p_dlen + p_blen + 0x2100` bytes from the basepage, so the stack
(`0x2000` bytes of it) sits above DATA, from `0x2720e` down.

So at run time the layout is `[ TEXT ][ BSS ][ DATA ]` with **`a4` sitting on the boundary**,
`a4 = 0x10000 + 0xe8ca + 0x6650 = 0x24f1a`:

* `a4 + n` (positive) → **initialised data**, at Ghidra address `0x24f1a + n`.
  `pea 664(a4)` is `0x251b2` = `"A:GHOST.DAT"`.
* `a4 - n` (negative) → **BSS**, i.e. the game's variables, at `0x24f1a - n`. These are the ones
  to name, and `var 0x<that address> <name>` is how.
* `a4 - 4` (`0x24f16`) holds the basepage pointer; `a5` stays `p_tbase` in the startup only.

**None of the nine relocations is affected by the move**: all nine sit in the jump table at
`0x10000` and all nine target TEXT. That matters because this crt0 re-fixes nothing after moving
DATA — a fixup pointing into DATA or BSS would be relocated by TOS against the *file* layout and
then left aiming at where the segment used to be. The small model is built so that cannot happen:
data is reached through `a4`, never through an absolute pointer.

`main` is **not** `0x16d8e` (that is the global initialiser, which builds every non-zero BSS
value one `move` at a time, and is why `strings` finds "GHOST.LOA" nowhere in the file). `main`
is `0x100dc`.

## Entry → main → frame loop

```
0x10000  jmp 0x10036
0x10036  crt0: Mshrink, relocate DATA above BSS, clear BSS, set a4
         jsr 48(a5)  -> 0x16d8e  init_globals
         jsr 0x10116 -> rts      (argv setup, stubbed out)
         jsr 0x100dc -> main(argc, argv)
         jsr 0x14d2c(0)          exit(0)
0x100dc  main:   XBIOS Getrez; if != 0 -> printf(" Please reboot in LOW REZ... ") and hang
                 jsr 0x10118    video/memory init
                 jsr 0x101e6    the game
0x10118  init:   XBIOS Getrez, XBIOS Logbase, Logbase-0x7d00 (the back buffer),
                 GEMDOS Super in/out, clear $484 (conterm: no key click/bell)
0x101e6  game:   load, install, then `do { … } while (true)` — menu, play, hall of fame
```

`FUN_000101e6` is the outer loop and calls, in order:

| call | what it does |
|---|---|
| `0x14c1e(0x100, 0)` | ? |
| `0x13c6c` | load `GHOST.LOA` + `GHOST.VOI` |
| `0x10e44` | load `A:GHOST.PRE` |
| `0x16a06(-7212(a4))` | ? (screen/mode state) |
| BIOS `Bconout(dev 4, $12)` | **IKBD command $12 — disable the mouse** |
| XBIOS `Setscreen(log, phys, 0)` | low res, the two buffers from `0x10118` |
| `0x10eb8`, `0x13cea` | show the presentation screen, **play the digitised voice** |
| `0x1396c` | load `A:GHOST.DAT` |
| `0x121a0` | load `A:GHOST.SCR` (hall of fame) |
| BIOS `Bconout(dev 4, $08)` | **IKBD command $08 — relative mouse reporting back on** |
| `0x15bfe(-6014(a4))` | `free()` the voice buffer |
| `0x132ec`, `0x14982`, `0x14576` | … then `0x14982` **starts the sound** |
| `0x10dea` | load `A:GHOST.DEM` |
| `0x10f20` | the attract/menu body |

## Files: what is opened, in what order, into where

All names carry an explicit **`A:` drive prefix**, so the game always reads its data from the
floppy no matter where the executable itself came from.

| where | file | routine | buffer | size |
|---|---|---|---|---|
| data `0x251b2` | `A:GHOST.DAT` | `0x1396c` | six `malloc(0x7800)` into `a4-7664[i]`, then one `0x20` | 6 × 30,720 + 32 |
| data `0x24fec` | `A:GHOST.PRE` | `0x10e44` | `malloc(0x7800)` → `a4-7640`, then `0x20` → `a4-7668` | 30,720 + 32 |
| data `0x24fe0` | `A:GHOST.DEM` | `0x10dea` | `malloc(0x1770)` → `a4-7606` | 6,000 |
| data `0x25176` | `A:GHOST.SCR` | `0x121a0` | hall of fame, read | — |
| data `0x25156` | `A:GHOST.SCR` | `0x1207a` | hall of fame, **created and written** | — |
| bss `a4-8130` | `GHOST.LOA` | `0x13c6c` | `fread` 2,703 bytes into `a4-6010`, then `jsr a4-5982` | 2,703 |
| bss `a4-8140` | `GHOST.VOI` | `0x13c6c` | `malloc(0x7594)` → `a4-6014` | 30,100 |

`0x7800` = 30,720 = a **320×192 low-res bitmap**; the trailing `0x20` is a 16-entry ST palette.
`GHOST.LOA` and `GHOST.VOI` are the only two names built at run time (byte by byte, in
`init_globals`), and they carry **no `A:`** — they load from the current drive.

The C file layer, all confirmed from bodies: `0x156e2` `fopen`, `0x15878` `fread`, `0x14d72`
`fclose`, `0x15d64` `open`, `0x1667c` `read`, `0x14c3c` `close`, `0x14c7a` `creat`, `0x15b54`
`malloc` (a real free-list allocator rooted at `a4-25770`), `0x15bfe` `free`, `0x164c2` `printf`.

## OS traps

There are only **nine `trap` opcodes in the whole 59 KB image**, because every OS call funnels
through two trampolines that pop the return address so the caller's pushed arguments line up:

* `0x15e3c` — **`xbios()`**: stash `a1`/`a2`/return in `a4-26080…-26088`, `trap #14`, restore.
* `0x15e58` — **`gemdos()`**: the same for `trap #1`.

92 call sites go through them. Counted by the opcode immediate pushed at each site:

| XBIOS | n | GEMDOS | n |
|---|---:|---|---:|
| `Setscreen` (5) | 17 | `Cconout` (2) | 9 |
| `Setcolor` (7) | 5 | `Crawcin` (7) | 7 |
| `Random` (0x11) | 4 | `Cconis` (0xb) | 6 |
| `Setpalette` (6) | 3 | `Fseek` (0x42) | 5 |
| `Vsync` (0x25) | 3 | `Cnecin` (8) | 4 |
| `Logbase` (3) | 2 | `Fwrite` (0x40) | 4 |
| `Getrez` (4) | 2 | `Crawio` (6) | 2 |
| `Supexec` (0x26) | 2 | `Fcreate`/`Fclose`/`Fread`/`Malloc`/`Super` | 2 each |
| | | `Fopen`/`Fdelete`/`Mfree`/`Pterm` | 1 each |

Read that as the architecture: **all video through XBIOS** (`Setscreen` for the double buffer,
`Setpalette`/`Setcolor` for colour, `Vsync` for the frame), **all keyboard through GEMDOS raw
console** (`Cconis` to poll, `Crawcin`/`Cnecin` to fetch — which is exactly what the menu screen
"Press [G] … [P] … [D] … [H]" needs), and files through GEMDOS. There is **no Line-A** anywhere
(`LineAResolve` resolved 0 sites) and no VDI drawing.

Outside the trampolines: `trap #13` (BIOS `Bconout`) twice, both sending IKBD commands as above;
`trap #2` (`0x149b6`, `d0 = 200` = AES) — Ghidra's own annotator already named it `gem_aes`; and
`trap #9`, which is the game's own (below).

## Hardware and interrupts

The game touches the hardware in exactly one place, and installs exactly one vector.

```
0x14982  sound_start:  XBIOS Supexec(0x148ea) ; then 0x14576
0x148ea  (supervisor)  save $114 and $484 into 0x14932…
                       move.l #(a4-8768),… / #(a4-8280),…   ; the ISR's two state pointers
                       move.l #0x14950,$a4        ; trap #9 vector
                       move.l #0x1459a,$114       ; MFP channel 5 = TIMER C (200 Hz)
                       move.b #$40,$fffffa17      ; MFP VR: vector base $40, automatic EOI
0x1499c  sound_stop:   XBIOS Supexec(0x1491c) -> restore $114 and $484, VR := $48
```

* **`0x1459a` is the Timer C interrupt handler** — the sound/music player. It points `a1` at
  `$ffff8800` (PSG), masks to IPL 5, forces `$484` to 0 while a voice is active, walks three
  channel structures, and **exits by pushing TOS's saved `$114` vector and `rts`** — i.e. it
  chains to the original 200 Hz handler rather than `rte`ing.
* **`0x14950` is a `trap #9` handler** that the game installs itself: it is a supervisor gate for
  the PSG (`movea.l #$ffff8800,a0`, select register `d1 & 15`, write `d0`, read back, leave
  register `$b` selected). `0x14940` is its user-mode stub — three words of arguments, then
  `trap #9`. Every PSG access from ordinary code goes through it.
* `$fffffa17` (MFP vector register) and `$ffff8800` (PSG) are the **only** hardware addresses in
  the image. No `$ff8240` palette writes, no `$ff8201/3` video base writes, no MFP timer
  programming beyond Timer C, no DMA/FDC, no direct ACIA, no VBL (`$70`) or HBL (`$68`) install.
  The `Floprd` on track 79 belongs to the protection wrapper, not to the game.

## Odd things worth knowing

* **The game is remarkably OS-friendly for 1987** — XBIOS video, GEMDOS keyboard, one Timer C
  hook. Expect the recreate to be dominated by the drawing code, not by hardware banging.
* **Self-modifying code exists but only in the wrapper** (`loader.md`); the decrypted program has
  none, and no second stage is loaded later — every file it reads is data.
* `0x148ea`'s save area at `0x14932` is *written* by the installer and *read* by the ISR, so
  those seven `nop`s in the listing are data, not code.
* The PSG volume table inside `GHOST.LOA` addresses three channels but the player only emits two
  register writes (see `loader.md`); do not "fix" that if the recreate has to match.
