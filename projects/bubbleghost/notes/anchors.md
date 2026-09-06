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
| code | `0x10036`–`0x16d8e` | 27 KB | 134 functions |
| `init_globals` | `0x16d8e`–`0x1e8ca` | 31 KB | inside TEXT and **instructions, not data** — the BSS initialiser stream (below) |
| bss | `0x1e8ca`–`0x24f1a` | 26 KB (`0x6650`) | the game's variables — zeroed by the crt0 |
| data | `0x24f1a`–`0x2520e` | 756 | all the program's strings |

`a4` = **`0x24f1a`**, the BSS/DATA boundary. `run.sh` pins it as a tracked register value
(`ghidra_scripts/SetRegisterValue.java`) before analysis, so a global that the linear listing
shows as `n(a4)` decompiles as `DAT_<that same address>` — `0x24f1a + n`, signed. That is the one
arithmetic rule you need: `-26170(a4)` is `DAT_0001e8e0`, `664(a4)` is `0x251b2`.

**Ghidra found 134 functions** (123 decompiled, 11 failed — all in the C library: `0x14c1e`,
`0x14fb0`, `0x150ee`, `0x153fe`, `0x159dc`, `0x1667c`, `0x16a26`, `0x16a5e`, `0x16a86`,
`0x16ae2`, `0x16c04`). That is the whole code segment, and there is no data island inside it:
the 31 KB running up to `0x1e8ca` is `init_globals`' own instruction stream — **7,787
`move.w #imm,(a1)+` plus nine `adda.w #n,a1` skips over the zero runs**, one contiguous stream
from `0x16d92` to the `rts` at `0x1e8c8`. **Replaying that stream reconstructs the initialised
BSS image**, which is how every table in [`gameplay.md`](gameplay.md) and
[`sound_engine.md`](sound_engine.md) was dumped — and the only way to read them at all, since
they live in BSS and so are not in the file.

The 134th function is `FUN_000237bc` — an artefact worth keeping, not a function in the image:
it is the `jsr a4-5982` target, i.e. where `GHOST.LOA`'s own text lands *inside the BSS*
once the game has read the file there (see the file table below), and with `a4` known Ghidra now
resolves that call to a real address.

The C startup reaches the global-data initialiser at `0x16d8e` only through `jsr 48(a5)` with
`a5 = p_tbase`, so flow analysis never disassembles it; `run.sh` seeds that one address as a
pre-script so auto-analysis follows it. Two jump-table targets, `0x15136` and `0x15190`, land
*inside* `fp_pack_float` (`0x15132`) and `fp_cmp` (`0x1518c`) rather than starting functions of
their own — they are the **register-argument entry points**, one instruction past a `link a6`
stub, and they are what `fp_op_table` holds ([`frontend.md`](frontend.md) §6).

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

`game_top_loop` (`0x101e6`) is the outer loop and calls, in order:

| call | what it does |
|---|---|
| `0x14c1e(0x100, 0)` | AES `graf_mouse(M_OFF)` — hide the GEM pointer |
| `0x13c6c` | load `GHOST.LOA` + `GHOST.VOI` |
| `0x10e44` | load `A:GHOST.PRE` |
| `0x16a06(-7212(a4))` | **`v_clrwk(handle)`** — a VDI call, and `a4-7212` (`0x232ee`) is the **VDI workstation handle**, not a `Getrez` result |
| BIOS `Bconout(dev 4, $12)` | **IKBD command $12 — disable the mouse** |
| XBIOS `Setscreen(log, phys, 0)` | low res, the two buffers from `0x10118` |
| `0x10eb8`, `0x13cea` | show the presentation screen, **play the digitised voice** |
| `0x1396c` | load `A:GHOST.DAT` |
| `0x121a0` | load `A:GHOST.SCR` (hall of fame) |
| BIOS `Bconout(dev 4, $08)` | **IKBD command $08 — relative mouse reporting back on** |
| `0x15bfe(-6014(a4))` | `free()` the voice buffer |
| `0x132ec`, `0x14982`, `0x14576` | `build_sprite_bank` **grabs the sprites off the screen** (below); then `0x14982` **starts the sound** |
| `0x10dea` | load `A:GHOST.DEM` |
| `0x10f20` | `reset_world_state` — 174 stores of the "all candles lit" defaults into the live tables and both world blocks. The menu is `0x115d6` |

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

**How the six `GHOST.DAT` buffers are addressed, and where the sprites come from.** The six
30,720-byte buffers are one 360-tile bank read in six pieces: the game fetches tile *n* as
`dat_bank[n / 60] + (n % 60) * 512`. Immediately after the load, `build_sprite_bank` (`0x132ec`)
**grabs the moving sprites off the screen**: it draws bank 0 (tiles 0..59) as a 10×6 grid into the
work buffer with a raw `move.l` loop, then `vro_cpyfm`s each 32×32 cell out into its own
`malloc`ed buffer — `ghost_sprite[0..46]` (pointer array at `0x23028`), `bubble_sprite[0..12]`
(`0x22ff4`), and the two 32×32 save patches `bubble_bg` (`0x230e4`) and `ghost_bg` (`0x230e8`).
So the bitmaps the game blits every frame are *screen* copies, not pointers into the loaded file
([`gameplay.md`](gameplay.md) §7).

The C file layer, all confirmed from bodies: `0x156e2` `fopen`, `0x15878` `fread`, `0x14d72`
`fclose`, `0x15d64` `open`, `0x1667c` `read`, `0x14c3c` `close`, `0x14c7a` `creat`, `0x15b54`
`malloc` (a real free-list allocator rooted at `a4-25770`), `0x15bfe` `free`, `0x164c2` `printf`.

## OS traps

There are only **nine `trap` opcodes in the whole 59 KB image**, and **two of them are `trap #2`**
— which is why the opcode count reads as fewer OS entry points than the program really has (the
AES and the VDI share one opcode; next section). Every GEMDOS and XBIOS call funnels through two
trampolines that pop the return address so the caller's pushed arguments line up:

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

Read that as the architecture: **the screen base and the colours through XBIOS** (`Setscreen` to
point the VDI at the work buffer, `Setpalette`/`Setcolor` for colour, `Vsync` at only three sites
and none of them in the play loop), **the menu keyboard through the GEMDOS raw console**
(`Cconis` to poll, `Crawcin`/`Cnecin` to fetch — which is exactly what the menu screen
"Press [G] … [P] … [D] … [H]" needs), and files through GEMDOS. There is **no Line-A** anywhere
(`LineAResolve` resolved 0 sites) — but there *is* VDI, and it does most of the drawing.

Outside the trampolines: `trap #13` (BIOS `Bconout`) twice, both sending IKBD commands as above;
**two** `trap #2` sites — `0x149b6` with `d0 = 200` is the AES (Ghidra's own annotator named it
`gem_aes`), and `0x168d4` with `d0 = 0x73` is the **VDI** (`vdi_call`, next section); and
`trap #9`, which is the game's own (below).

## GEM: the program draws through the VDI

Bubble Ghost is a **GEM application**. The init routine at `0x10118` calls `appl_init`
(`0x14b94`), `graf_handle` (`0x14be8`) and `v_opnvwk` (`0x169a0`), and from then on **all text,
the bonus bar and every 32×32 sprite blit go through the VDI**; only the full-screen and
tile-grid copies are hand-written `move.l` loops.

`vdi_call` at **`0x168d4`** is the binding: save `a1`/`a2`, point `d1` at the parameter block,
`d0 = 0x73`, `trap #2`. The **VDI parameter block is the first 20 bytes of BSS** — `vdi_pblock`
at `0x1e8ca`, five pointers at `contrl 0x236f0`, `intin 0x235f0`, `ptsin 0x234f0`,
`intout 0x233f0`, `ptsout 0x232f0`, with the workstation handle just below `ptsout` at `0x232ee`.

| routine | `contrl[0]` | VDI call | what it draws |
|---|---:|---|---|
| `0x168fc` | 12 | `vst_height` | text size — 6 for the menu and hall of fame, 4 for the HUD |
| `0x16948` | 22 | `vst_color` | text colour |
| `0x16974` | 25 | `vsf_color` | fill colour |
| `0x169a0` | 100 | `v_opnvwk` | open the workstation (fills the handle at `0x232ee`) |
| `0x16a06` | 3 | `v_clrwk` | clear it |
| `0x16a26` | 124 | `vq_mouse` | **the game's input** — pointer position and buttons |
| `0x16a5e` | 128 | `vq_key_s` | the shift state — **blow** |
| `0x16a86` | 8 | `v_gtext` | every string on screen: the menu, the HUD counters, the hall of fame |
| `0x16ae2` | 114 | `vr_recfl` | the BONUS bar on scanline 189 |
| `0x16b12` | 109 | `vro_cpyfm` | the 32×32 sprite blits (seven call sites) |

**The input is the MOUSE, not the keyboard and not a joystick.** `vq_mouse` gives the ghost's
position (scaled by a software-float divide: `mouse_x/1.115`, `mouse_y/1.577`) and its facing —
one step per button press, left button `+1`, right button `−1`, mod 8 — and `vq_key_s` gives the
**blow**, held while the shift state is neither `0` nor `4`, i.e. either Shift key. The GEMDOS
raw console is only the menu's key reader plus a per-frame `Crawio(0xff)` poll for `^P` pause,
`^S` sound toggle and `^R` abort. The `Bconout(dev 4, $12)` / `$08` pair above turns IKBD mouse
*reporting* off across the loading and the presentation and back on before play.

**Sprites are save / OR / restore — three `vro_cpyfm` pairs per frame.** Mode 3 (`S_ONLY`) copies
the 32×32 background out, mode 7 (`S_OR_D`) ORs the sprite in, mode 3 puts the background back.
There is no mask: the ghost and bubble tiles use only colour 0 and colour 15, so the OR sets all
four planes where the sprite is white and leaves the background elsewhere. `vro_cpyfm` also does
the clipping. That is the answer to [`assets_survey.md`](assets_survey.md)'s transparency
question. Full detail: [`frontend.md`](frontend.md) §1 and [`gameplay.md`](gameplay.md) §7.

## Hardware and interrupts

The game touches the hardware in exactly one place, and installs **two** vectors — `$114`
(MFP Timer C, the 200 Hz sound tick) and `$a4` (`trap #9`, its own PSG supervisor gate).

```
0x14982  sound_start:  XBIOS Supexec(0x148ea) ; then 0x14576
0x148ea  (supervisor)  save $114 and $484 into 0x14932…
                       move.l #(a4-8768),… / #(a4-8280),…   ; -> snd_volume_scale 0x22cda,
                                                          ;    snd_voice[2]      0x22ec2
                       move.l #0x14950,$a4        ; trap #9 vector
                       move.l #0x1459a,$114       ; MFP channel 5 = TIMER C (200 Hz)
                       move.b #$40,$fffffa17      ; MFP VR: vector base $40, automatic EOI
0x1499c  sound_stop:   XBIOS Supexec(0x1491c) -> restore $114 and $484, VR := $48
```

* **`0x1459a` is the Timer C interrupt handler** — the sound engine's 200 Hz tick. It points `a1`
  at `$ffff8800` (PSG), drops to IPL 5 so other MFP channels can nest inside it, walks the
  **three `0x8c`-byte voice records at `0x22daa`** (`a4-8560`), and **exits by pushing TOS's
  saved `$114` vector and `rts`** — i.e. it chains to the original 200 Hz handler rather than
  `rte`ing.
* **Conterm.** The ISR writes 0 to `$484` **unconditionally on entry, every tick**, and restores
  the saved byte at the *end* of the tick only when all three voices' duration counters are zero.
  The net effect is that TOS's key click and bell — which also drive the PSG — are muted for as
  long as anything is sounding, but the mechanism is a per-tick clear plus a conditional restore,
  and the restore is the half a reconstruction has to get right.
* **`0x14950` is the second installed vector, on `$a4`** — a `trap #9` handler the game puts
  there itself, and a supervisor gate for the PSG (`movea.l #$ffff8800,a0`, select register
  `d1 & 15`, write `d0`, read back, leave register `$b` selected). `0x14940` is its user-mode stub — three words of arguments, then
  `trap #9`. Every PSG access from ordinary code goes through it.
* `$fffffa17` (MFP vector register) and `$ffff8800` (PSG) are the **only** hardware addresses in
  the image. No `$ff8240` palette writes, no `$ff8201/3` video base writes, no MFP timer
  programming beyond Timer C, no DMA/FDC, no direct ACIA, no VBL (`$70`) or HBL (`$68`) install.
  The `Floprd` on track 79 belongs to the protection wrapper, not to the game.

**The sound engine is a three-voice software ADSR + LFO synthesiser for the YM2149, and there is
no music in the program.** No sequencer, no note stream, no tempo counter: every sound is one
one-shot voice record, filled from a 56-word definition by a single trigger call, `sound_play`
(`0x142bc`). What it plays is **11 fixed effects** (`snd_def_fx`, `0x201ca`) and **36 per-level
tones** (`snd_def_level`, `0x1f20a`), with each room's candle effect picked by
`room_candle_sfx` (`0x21abe`). The one thing that *sounds* like a melody — the end-of-room
bonus tally — is the frame loop re-triggering `fx8` at a rising note. Voice-record layout, the ISR algorithm, the
`trap #9` PSG gate and all 15 call sites: [`sound_engine.md`](sound_engine.md).

## Odd things worth knowing

* **The game is remarkably OS-friendly for 1987** — it is a GEM application: VDI drawing, VDI
  mouse and shift-key input, XBIOS for the screen base and the palette, GEMDOS for files and the
  menu keys, and two installed vectors for sound (Timer C plus its own `trap #9` PSG gate).
  Expect the recreate to be dominated by the drawing code, not by hardware banging.
* **Self-modifying code exists but only in the wrapper** (`loader.md`); the decrypted program has
  none, and no second stage is loaded later — every file it reads is data.
* `0x148ea`'s save area at `0x14932` is *written* by the installer and *read* by the ISR, so
  those seven `nop`s in the listing are data, not code.
* The PSG volume table inside `GHOST.LOA` addresses three channels but the player only emits two
  register writes (see `loader.md`); do not "fix" that if the recreate has to match.
