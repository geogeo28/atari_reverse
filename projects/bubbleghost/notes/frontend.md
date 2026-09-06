# Bubble Ghost — the front end and the C library

Everything reachable from `main` (`0x100dc`) that is not the in-room simulation and not the sound
engine: the boot path, the title/menu state machine, the demo player, the hall of fame, the screen
and palette scheme, and the whole Alcyon/DRI C runtime the program was linked against.

Read out of `decomp.c` and `out/prg_dis.txt` at the project's load base `0x10000`. Ghidra addresses
are run-time addresses; globals are `a4`-relative with `a4 = 0x24f1a` (see
[`anchors.md`](anchors.md)). Every name used below is the one in [`names.txt`](../names.txt),
which is the source of truth for this project; the proposals this pass generated are in
`out/names_frontend.txt` and have been merged.

Two names that used to be in `names.txt` were wrong and were corrected by this pass:

* **`0x10f20` is not `attract_and_menu`.** It is `reset_world_state` — 174 straight-line
  stores and no control flow. The menu is **`0x115d6`** (`title_menu_loop`).
* **`0x16a06` is not `set_screen_mode`.** It is **`v_clrwk`**, and the `a4-7212` it is handed is the
  **VDI workstation handle**, not a `Getrez` result.

---

## 1. The program is a GEM application

This is the fact that reorganises the whole slice, and nothing in `anchors.md` had it: Bubble Ghost
**opens a GEM virtual workstation and draws its text, its bonus bar and its 32×32 tiles through the
VDI**. `anchors.md` counted "nine `trap` opcodes" and one `trap #2` that Ghidra had annotated
`gem_aes`; that `trap #2` is the AES, and there is a *second* `trap #2` — inside `vdi_call` at
`0x168d4`, with `d0 = 0x73` — that is the VDI. It does not show up as a distinct trap because both
go through the same opcode.

The binding is the standard DRI one:

| what | address | opcode |
|---|---|---|
| `vdi_call` — save a1/a2, `d1 = &pblock`, `d0 = 0x73`, `trap #2` | `0x168d4` | — |
| `v_opnvwk(work_in, &handle, work_out)` | `0x169a0` | 100 |
| `v_clrwk(handle)` | `0x16a06` | 3 |
| `v_gtext(handle, x, y, str)` | `0x16a86` | 8 |
| `vst_height(handle, h, &cw, &ch, &bw, &bh)` | `0x168fc` | 12 |
| `vst_color(handle, idx)` | `0x16948` | 22 |
| `vsf_color(handle, idx)` | `0x16974` | 25 |
| `vro_cpyfm(handle, mode, pxy, src_mfdb, dst_mfdb)` | `0x16b12` | 109 |
| `vr_recfl(handle, pxy)` | `0x16ae2` | 114 |
| `vq_mouse(handle, &buttons, &x, &y)` | `0x16a26` | 124 |
| `vq_key_s(handle, &state)` | `0x16a5e` | 128 |
| `vdi_set_src_mfdb` / `vdi_set_dst_mfdb` (contrl[7..8] / [9..10]) | `0x16890` / `0x168b2` | — |

and the AES side is `aes_crysif` (`0x14b2e`, control block built from the 3-byte-per-opcode table at
`0x149d2`), `appl_init` (`0x14b94`), `graf_handle` (`0x14be8`) and `graf_mouse` (`0x14c1e`).

The VDI parameter block sits at the **very first bytes of BSS**: `vdi_pblock` at `0x1e8ca` is the
five pointers, and the arrays are `contrl 0x236f0`, `intin 0x235f0`, `ptsin 0x234f0`,
`intout 0x233f0`, `ptsout 0x232f0`, with the workstation handle immediately below `ptsout` at
`0x232ee`.

**The seven `vro_cpyfm` call sites are the game's tile blitter** (`0x133ce`, `0x1348a`, `0x134ea`,
`0x1355c`, `0x135c6`, `0x1362e`, `0x1368e` — all in the gameplay slice). That answers
`assets_survey.md`'s transparency question in outline: the tiles are moved with the VDI raster copy
and a *mode* argument, not with a hand-written masked blit.

Two oddities worth carrying:

* `init_gem_and_screens` calls `graf_handle` into **one scratch local four times over** and throws
  the return value away, so the physical handle it passes to `v_opnvwk` is the BSS zero sitting in
  `0x232ee`. TOS's `v_opnvwk` tolerates it; a reconstruction must reproduce it, not "fix" it.
* Both `graf_mouse` call sites push only 4 bytes for a `(short, long)` signature, so the callee
  reads its `addr_in` long off the caller's own return address. Harmless for `M_OFF`/`M_ON`.

---

## 2. Boot → menu → game → hall of fame

```
crt0 0x10036
  └ main 0x100dc
      ├ XBIOS Getrez != 0  ->  c_printf("\n\n Please reboot in LOW REZ... \n") ; for(;;) ;
      ├ init_gem_and_screens 0x10118
      │     appl_init ; graf_handle ; v_opnvwk
      │     Getrez -> boot_rez            (0x23146)
      │     Logbase - 0x7d00 -> screen_back (0x2314c)
      │     Logbase          -> screen_phys (0x23148)
      │     Super ; *(char*)0x484 = 0 ; Super back
      └ game_top_loop 0x101e6
            graf_mouse(M_OFF)
            load GHOST.LOA + GHOST.VOI ; load A:GHOST.PRE
            v_clrwk ; Bconout(dev 4, $12)          <- IKBD mouse off
            Setscreen(log=screen_back, phys=screen_phys)
            show_presentation 0x10eb8 ; play_voice
            load A:GHOST.DAT ; load_hiscores
            Bconout(dev 4, $08) ; free the voice buffer ; sound_start
            load_demo
            for (;;) {                              <- one whole GAME per pass
                p1_alive = p2_alive = 1
                reset_world_state 0x10f20
                bonus_bar = 0x13e ; lives = 5
                hiscore_candidate = score
                title_menu_loop 0x115d6             <- the entire front end lives here
                do {                                <- one ROOM per pass
                    optional "PLAYER ONE/TWO" card + per-player state swap
                    room_number = room_grid[grid_row][grid_col]
                    ... the gameplay slice's room loop ...
                    room exit: bump grid_row/grid_col, or the win path
                } while (p1_alive || p2_alive)
                "G A M E    O V E R"
            }
```

`title_menu_loop` returns only when a game has been chosen (`[G]` with a player count, or a valid
`[P]` level); `[D]` and `[H]` fall back to redrawing the menu.

### The menu

`vst_height(handle, 6)`, `vst_color(handle, 1)`, four `v_gtext` lines at `x = 0x18`:

| y | text |
|---:|---|
| `0x48` | `Press [G] .......to play the Game` |
| `0x58` | `Press [P] ....to practice a LEVEL` |
| `0x68` | `Press [D] ........to see the Demo` |
| `0x78` | `Press [H] to see the Hall of FAME` |

The key read is the same three-call idiom everywhere in this program:

```c
while (Cconis())  Crawcin();      /* GEMDOS 0x0b, 0x07 — flush anything pending  */
c = Cnecin();                     /* GEMDOS 0x08       — blocking, no echo       */
if (c > '`') c -= 0x20;           /* fold lowercase                              */
```

| key | effect |
|---|---|
| `G` | ask `Press [1] for ONE player  game` / `Press [2] for TWO players game` at `x=0x28`, `y=0x58/0x68`; spin on the same read until the key minus `'0'` is 1 or 2; set `player_count`; **return** |
| `P` | `Enter level number:   01 to 35   ?` at `(0x18,0x60)`; read two digits, `n = tens*10 + units`; accept `0 < n < 36`; scan the 6×6 `room_grid` for `n` and set `grid_row`/`grid_col`; `practice_mode = 1`; **return**. Score and both players' scores are zeroed first, `player_count = 1`. |
| `D` | play the demo (below), then a random room slideshow, then the title picture, then idle — all abortable |
| `H` | `draw_hall_of_fame` then 857 polling iterations |
| anything else | loop: redraw the menu |

`practice_mode` is also what makes the game end after one room — `game_top_loop` forces
`lives = -1` on the room-exit path when it is set.

### `room_grid` — the 36 rooms are one serpentine path

`init_globals` fills the 6×6 word table at `0x2328e` (row stride `0xc`) with `0..35`, **each value
exactly once**, laid out boustrophedon:

| row \ col | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 30 | 31 | 32 | 33 | 34 | 35 |
| 1 | 29 | 28 | 27 | 26 | 25 | 24 |
| 2 | 18 | 19 | 20 | 21 | 22 | 23 |
| 3 | 17 | 16 | 15 | 14 | 13 | 12 |
| 4 |  6 |  7 |  8 |  9 | 10 | 11 |
| 5 |  5 |  4 |  3 |  2 |  1 |  0 |

`game_top_loop` starts a new game at `grid_row = 5, grid_col = 4`, i.e. **room 1**, and the room
loop walks the grid by bumping `grid_col` on a right/left exit and `grid_row` on a bottom/top exit
— so the numbering *is* the walk, and the whole game is one lap of that path from room 1 up to
room 35. Room 0 sits behind the start at (5,5); `draw_hall_of_fame` draws it as the hall-of-fame
backdrop, and the `[P]` check (`0 < n < 36`) is what stops a player selecting it. Because no value
repeats, the search's "keep the last match" has no observable effect.

### The `[D]` attract sequence

Three phases, each polling `vq_mouse` every iteration and bailing out the moment
`mouse_buttons == 1`:

1. **`GHOST.DEM` replay** — `room_number = 1`, draw the room, then **980** records (`0x3d4`, of the
   1,000 in the file) fed one per iteration into the ghost/bubble state, with the five-call frame
   renderer after each. **There is no `Vsync` in this loop** — it runs as fast as the renderer does,
   so the 20 s figure in `assets_survey.md` ("1,000 records at 50 Hz") is an assumption the code
   does not support.
2. **A room slideshow** — `n = Random()/16794009.0 * 11.0 + 5.0` rooms, each
   `room_number = Random()/16794009.0 * 34.0 + 1.0`, each shown for 30 frames with **three**
   `Vsync`s per frame. **The ranges are 5..15 and 1..34**, and both are truncated, not rounded:
   XBIOS `Random` is 24-bit, so its largest value is `0xffffff` = 16,777,215 and
   `16777215 / 16794009 = 0.99900…` < 1; the product therefore never reaches 11 or 34, and
   `fp_acc_to_long` (`0x154c0`) → `fp_double_to_long` (`0x1550a`) converts with a bare
   `lsr.l d0,d1` on the mantissa — a logical shift with no rounding term, so the fraction is
   discarded toward zero. **The attract mode can never show room 35.**
3. **The title picture** — `show_presentation()`, then 37,000 `vq_mouse` polls.

---

## 3. `GHOST.DEM` — settled from the consuming code

`assets_survey.md` had the record shape right and the field assignment as a hypothesis. The demo
player at `0x11992` reads **six bytes**, advances the cursor by **6**, and settles both the fields
and, crucially, **the coordinate unit**:

| byte | scale | global | meaning |
|---:|---:|---|---|
| 0 | ×3 | `0x22ff2` `ghost_x` | ghost x |
| 1 | ×2 | `0x22ff0` `ghost_y` | ghost y |
| 2 | ×1 | `0x22fea` `ghost_tile` | ghost animation frame, a `GHOST.DAT` tile index |
| 3 | ×3 | `0x22fee` `bubble_x` | bubble x |
| 4 | ×2 | `0x22fec` `bubble_y` | bubble y |
| 5 | ×1 | `0x22fe8` `bubble_frame` | bubble frame |

**The unit is 3 pixels in x and 2 pixels in y, origin at the top-left of the play area.** That
closes question 4 of the survey, and it corroborates question 1's screen-layout hypothesis by an
independent route: the room loop leaves a room when `bubble_x > 0x120` (288) or `bubble_y > 0x80`
(128) or either goes negative. A 320×160 play area with a 32×32 sprite anchored at its top-left has
exactly `320-32 = 288` and `160-32 = 128` of travel. So the survey's "top 10×5 tiles are the room,
the bottom 10×1 row is the HUD" is **confirmed** — and the HUD coordinates below land in
`y = 160..191`, which is the same statement from the other side.

The ghost/bubble assignment is fixed by the game-over animation in `game_top_loop`, which pops the
bubble (`bubble_frame = 3`), parks it at (0xa0, 0x40) and then walks `ghost_tile` down in steps of 5
— so `0x22fea` is the ghost's frame and `0x22fe8` the bubble's, which forces the rest.

---

## 4. `GHOST.SCR` — the hall of fame file

**40 bytes, pure ASCII, no header, no separators.** Written by `save_hiscores` (`0x1207a`) and read
by `load_hiscores` (`0x121a0`):

| offset | bytes | field |
|---:|---:|---|
| 0 | 6 | entry 0 score, decimal, zero-padded to 6 digits |
| 6 | 2 | entry 0 room reached, zero-padded to 2 digits |
| 8 | 6 | entry 1 score |
| 14 | 2 | entry 1 room |
| … | | … 5 entries in all |
| 32 | 6 | entry 4 score |
| 38 | 2 | entry 4 room |

Both fields go through `itoa_padded` (`0x114ee`) on the way out and a hand-rolled
`v = c_lmul(v,10) + digit - '0'` loop on the way in, stopping at the first non-digit. The file is
created with `c_creat` and written with `c_write`, which for a text-mode handle would expand `\n` —
there are none, so the file is byte-exact.

In memory the two halves are separate arrays: `hall_scores` (five longs at `0x22f8c`) and
`hall_rooms` (five longs at `0x22f78`), kept in step. **They are sorted ASCENDING**: slot 0 is the
worst and slot 4 (`0x22f9c`) is the best, which is why `game_top_loop` seeds the displayed
`hi_score` from `0x22f9c` and why `draw_hall_of_fame` walks `i = 4` down to `0` to put the best
entry on the `SCORE 1:` row. If the file is missing, every score is 0 and every room is 1.

`hiscore_insert_and_save` (`0x11f84`) compares the candidate against **`hall_scores[0]`** — the
lowest — overwrites slot 0 and then bubble-sorts (five passes of four adjacent compares). There is
**no name entry** anywhere in this program: the hall of fame is score plus room number only, and
the only strings on that screen are the five fixed `SCORE n:` labels and `HALL:`.

Hall-of-fame screen layout (`draw_hall_of_fame`, `0x11dbc`), `vst_height(6)`, room 0 as backdrop:

| element | x | y | colour |
|---|---:|---:|---:|
| `SCORE 1:` … `SCORE 5:` | 56 | 54, 69, 84, 99, 114 | 13 |
| `HALL:` (one per row) | 200 | `114 - i*15` | 13 |
| score, 6 digits | 128 | `114 - i*15` | 5 |
| room, 2 digits | 248 | `114 - i*15` | 5 |

---

## 5. The screen scheme

Two 32,000-byte low-res screens and **no page flipping**:

* `screen_phys` = `Logbase` — the screen TOS was already showing. It never moves.
* `screen_back` = `Logbase - 0x7d00` (32,000) — a scratch buffer carved out *below* it.

`Setscreen` is only ever called with `phys = screen_phys`. What changes is the **logical** base,
i.e. where the VDI draws:

| `Setscreen(log, phys)` | where | why |
|---|---|---|
| `(screen_back, screen_phys)` | game_top_loop start, after each text card, after saving scores | normal play — draw off-screen |
| `(screen_phys, screen_phys)` | the menu, the `PLAYER ONE/TWO` and `GAME OVER` cards, `save_hiscores` | draw text straight onto the visible screen |

Getting a finished picture onto the visible screen is a **hand-written `move.l (a2)+,(a3)+` copy**,
never a base swap, and always exactly as much as changed:

* `show_presentation` — 30,720 bytes, the whole 320×192 picture.
* `clear_physical_screen` (`0x10efe`) — 30,720 bytes of zero, into `screen_phys` only.
* `hud_bonus_bar_fill` / `hud_bonus_bar_shrink` — **40 longs (160 bytes)** at offset `0x7620` =
  **scanline 189**, the bonus bar's row, once per bar step. (`moveq #$27,d` then a `dbf` over one
  `move.l`, so 0x27 + 1 = 40 iterations — one scanline of a 160-byte row, not 41 longs.)

Palettes are XBIOS `Setpalette` with one of the two 32-byte blocks read off the tail of the picture
files: `pre_palette` (`0x23126`, from `GHOST.PRE`) before the presentation, `dat_palette`
(`0x23122`, from `GHOST.DAT`) at the top of the menu. `Setcolor` (opcode 7) is used separately to
force entry 15 to `$777` on the two end-of-room animations. That answers `assets_survey.md`'s
palette question: **two palettes, both from the data files, no per-room palette in the PRG.**

### The HUD

`hud_draw_counters` (`0x113d2`), `vst_height(4)`, `vst_color(5)`, four `itoa_padded` + `v_gtext`:

| value | digits | x | y |
|---|---:|---:|---:|
| `score` | 6 | 230 | 173 |
| `hi_score` | 6 | 230 | 183 |
| `hud_room_number` (`= room_number`) | 2 | 307 | 173 |
| `lives` | 1 | 313 | 183 |

`lives` is drawn as `0` while the real value is the `-1` end-of-game sentinel — the routine
zeroes it, formats, and puts `-1` back.

The **bonus bar** is a filled rectangle on scanline 189 running from `x = 0x23` (35) to
`bonus_bar` (`0x22fb4`), which starts each room at `0x13e` (318) and floors at `0x23`.
`hud_bonus_bar_shrink(n)` erases the last `n` columns in colour 0; `hud_bonus_bar_fill` repaints it
column by column in colour 11. `bonus_tick` (`0x22f76`) makes it tick once every **three** frames:
it is reloaded with 2 and the bar steps on the frame whose pre-decrement value is already 0, so
the sequence is 2, 1, 0 → step.

---

## 6. The C library inventory

The program was linked against the Alcyon/DRI runtime. Everything present, by area — the eleven
functions Ghidra could not decompile are marked ▲ and were read from `out/prg_dis.txt`.

**GEM binding** — `aes_crysif` `0x14b2e`, `appl_init` `0x14b94`, `graf_handle` `0x14be8`,
`graf_mouse` `0x14c1e`▲, `gem_aes` `0x149b6`, plus the twelve VDI entry points in §1.

**stdio** — `c_fopen` `0x156e2`, `c_fclose` `0x14d72`, `c_fread` `0x15878`, `c_fflush` `0x14dc4`,
`c_filbuf` `0x14e80`, `c_flsbuf` `0x14fb0`▲, `c_putc` `0x150ee`▲, `c_fputs` `0x164ee`,
`c_exit` `0x14d2c`, `c_exit_pterm` `0x14d16`.
`c_iob` is **73 `FILE` records of 20 bytes** at `0x1eb08..0x1f0bc`; `stdin` `0x1eb08`,
`stdout` `0x1eb1c`, `stderr` `0x1eb30`, all three bound to the pseudo-handle `0x8300` (CON:) with a
default buffer size of `0x200` (`c_bufsiz`, `0x1eb06`).

```
FILE (20 bytes)   +0  char *ptr      current position in the buffer
                  +4  short cnt      bytes left
                  +6  char *base     buffer
                  +10 short flags    1 read, 2 write, 4 append, 8 no-buffer, 0x10 malloc'd,
                                     0x20 EOF, 0x40 error, 0x80 dirty
                  +12 short fd
                  +14 long  offset
                  +18 short bufsize
```

**Low-level I/O** — `c_open` `0x15d64`, `c_creat` `0x14c7a`, `c_close` `0x14c3c`,
`c_read` `0x1667c`▲, `c_write` `0x16c04`▲, `c_lseek` `0x159dc`▲, `c_unlink` `0x16868`,
`c_conin` `0x16518`, and the three device writers `c_conout_write` `0x16b5e`,
`c_auxout_write` `0x16ba8`, `c_prtout_write` `0x16bd6`.
The pseudo-files are `CON:` → `-32000`/`0x8300`, `AUX:` → `-0x7d01`/`0x82ff`, `PRT:` → `-0x7d02`/
`0x82fe` (the strings live at `0x251c6`/`0x251cc`/`0x251d2` and `0x251ec`/`0x251f2`/`0x251f8`).
Text-vs-binary is tracked out of band in `fd_mode_table` — 76 `(fd, mode)` word pairs at
`0x1e93e`, terminated by `c_errno` at `0x1ea6e` — via `c_setfdmode`/`c_getfdmode`/`c_clearfdmode`.
In text mode `c_write` splits at every `\n` and emits the `const_crlf` pair at `0x2520a`.

**printf** — `c_printf` `0x164c2`, `c_sprintf` `0x164d8`, `c_vfprintf` `0x16496`,
`c_doprnt` `0x1620c`, `c_fmt_integer` `0x15e74`, `c_fmt_float` `0x15fe0`, `c_fcvt` `0x15588`,
`c_fmt_getnum` `0x161b8`. `c_vfprintf` formats into a **256-byte stack buffer** before writing it.
The whole family has **exactly one live call site**: `main`'s LOW REZ message.

**string / arithmetic** — `c_strcmp` `0x167fc`, `c_strlen` `0x1683e`, `c_ldiv` `0x158fe`,
`c_lmul` `0x15970`. Both arithmetic helpers return through their **argument slots on the stack**,
which is why `itoa_padded` calls `c_ldiv` twice per digit (once popping the remainder, once the
quotient).

**memory** — `c_malloc` `0x15b54` (6-byte granules, free list at `0x1ea70`), `c_free` `0x15bfe`,
`c_morecore` `0x15af2` (rounds up to `0x418`-byte chunks), `gemdos_malloc_or_fail` `0x167c8`, plus
stdio's own `gemdos_malloc` `0x15c82` / `gemdos_mfree` `0x15c98`.

**software floating point** — a complete DRI FP package, and the reason the program has **exactly
nine relocations**: `fp_op_table` (`0x1ea7e`, seven longs written by `init_globals` as `a5 + n`)
points at the `jmp $xxxxxx.l` slots of the jump table at `0x10000`.

| op index | jump slot | routine | |
|---:|---|---|---|
| 0 | `0x10006` | `0x152fa` | `fp_add` |
| 1 | `0x1001e` | `0x152e0` | `fp_sub` (flips the sign word, falls into add) |
| 2 | `0x10018` | `0x1524e` | `fp_mul` |
| 3 | `0x10024` | `0x151d0` | `fp_div` |
| 4 | `0x1002a` | `0x15190` | `fp_cmp` (entry inside `fp_cmp` at `0x1518c`) |
| 5 | `0x10012` | `0x15394` | `fp_pack_double` |
| 6 | `0x1000c` | `0x15136` | `fp_pack_float` (entry inside `fp_pack_float` at `0x15132`) |

That resolves `anchors.md`'s note that `0x15136` and `0x15190` "land inside" two functions: they are
the **register-argument entry points**, one instruction past a `link a6` stub, and they are what the
op table holds.

`fp_dispatch` (`0x153fe`) is the ABI: `fp_dispatch(short op, double *dst, void *src)`, the high byte
of `op` widening `src` first (`0x2000` short, `0x2800` long, `0x1000` float, otherwise an in-place
double) and the low byte indexing the table. On exit it pops its own arguments and loads `fp_ccr`
(`0x1eaa4`) into the real CCR so a float compare can be followed by a `Bcc`. Everything operates on
one 8-byte accumulator, `fp_acc` at **`0x1ea9a`** — the address that appeared as
`DAT_0001ea9a` in every front-end random-number computation before it was named.

The front end's only use of floating point is scaling `XBIOS Random`:

```
ambient_sfx_countdown = (int)( Random() * 2.977e-06 + 20.0 )      /* 20..69 frames       */
count                 = (int)( Random() / 16794009.0 * 11.0 + 5.0 )  /* 5..15 rooms      */
room_number           = (int)( Random() / 16794009.0 * 34.0 + 1.0 )  /* 1..34            */
```

All three truncate: `fp_acc_to_long` calls `fp_double_to_long`, whose conversion is one
`lsr.l d0,d1` on the mantissa with no rounding term. `Random` is 24-bit (max `0xffffff` =
16,777,215), so `Random()/16794009 ≤ 0.99900`, `× 11 ≤ 10.989`, `× 34 ≤ 33.966`, and
`Random() × 2.977e-06 ≤ 49.945` — which is where the three upper bounds come from.

The constants are DATA-segment doubles at `0x24fbc`, `0x24fc4`, `0x250ec`, `0x250f4`, `0x250fc`,
`0x25104`, `0x2510c`, `0x25114`.

---

## 7. Overlap with the other slices

* **`0x10f20 reset_world_state`** was assigned to this slice under the wrong name. Its body is
  entirely *gameplay* state — the initial values of every animated room object, plus the two 58-word
  per-player snapshot arrays at `0x231a6..0x23218` and `0x2321a..0x2328c`. The name is right; the
  ownership of the individual object fields is the gameplay slice's.
* **`hud_bonus_bar_fill` (`0x112c8`) / `hud_bonus_bar_shrink` (`0x11346`) / `hud_draw_counters`
  (`0x113d2`)** are drawn by the front end's VDI bindings but are called from inside the room
  loop. Named here; the values they display belong to the gameplay slice.
* **`room_grid` (`0x2328e`)** is read here (the `[P]` level search) and written by `init_globals`;
  the room loop is its main consumer.
* **`ghost_x/y/tile` and `bubble_x/y/frame` (`0x22fe8..0x22ff2`)** are *written* by the demo player
  in this slice and read by the gameplay renderer. Proposed `# ctx` for the three ghost fields,
  because only the demo writes and the win/lose animations read them — the simulation's own writer
  is in the other slice.
* **Sound**: the demo and the end-of-room animations call `sound_play` (`0x142bc`),
  `sound_release_voice` (`0x14510`) and `sound_stop_voice` (`0x144c4`) with definitions out of
  `snd_def_fx` (`0x201ca`; the individual records at `0x2023a`, `0x2031a`, `0x2038a`, `0x2054a`
  are `fx1`, `fx3`, `fx4`, `fx8`) and a `sound_enabled` (`0x2315e`) multiplier on every volume.
  Decoded in [`sound_engine.md`](sound_engine.md), not here.

---

## 8. Questions this pass raised, and what closed them

1. **`ambient_sfx_countdown` (`0x22fc0`) — CLOSED by [`gameplay.md`](gameplay.md) §2.** It is the
   20..69-frame ambient-sfx countdown: set at the top of a room, decremented once per frame, and
   when it underflows the room's own ambience is triggered and the counter re-rolled.
2. **`show_presentation` sets `bank_index = 6` (`0x2311e`) — CLOSED.** It is not a row count: it
   selects which of the seven `dat_bank[]` pointers `draw_tile_bank_screen` (`0x1369a`) paints,
   and slot 6 is `dat_bank_pre` (`0x23142`), the `GHOST.PRE` title picture.
3. **The demo has no `Vsync`.** Still true, and still the one behavioural trap here: its playback
   rate is whatever the renderer costs, so the original's attract mode ran at a machine-dependent
   speed. Any reconstruction that adds a frame sync there is changing behaviour, not fixing it.
4. **`vq_key_s` (`0x16a5e`) has exactly one caller — CLOSED by [`gameplay.md`](gameplay.md) §3.**
   That caller is `game_frame_update` (`0x12322`) at `0x1235a`, and the modifier it reads is
   **the blow**: the ghost blows while `key_shift_state` (`0x23116`) is neither `0` nor `4`, i.e.
   while either Shift key is held. It is the one input in the program that is neither the mouse
   nor the GEMDOS raw console.
