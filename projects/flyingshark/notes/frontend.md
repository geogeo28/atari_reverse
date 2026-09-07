# Flying Shark — boot, front end, I/O and interrupts

Everything below was read out of `out/prg_dis.txt` (linear 68000 disassembly, load base
`0x10000`) and the raw `bin/FLYSHARK.PRG`.  `decomp.c` was used only as a map: Ghidra renders
most of this program's register-argument routines as bare `return;`, and several of the
interesting sites (the self-modifying `jmp`, the patched branches, the string that
disassembles as `trap #4`) are invisible in the C.  Proposed names live in
`out/names_init.txt`; this file is the reasoning behind them.

Character encoding used throughout the front end: **`0xab`..`0xc4` = `A`..`Z`,
`0xc5`..`0xce` = `0`..`9`, `0xcf` = space, `0xd0`+ = HUD glyphs.**  `bcd3_to_chars6`
(`0x10b04`) adds `0xc5` to a BCD nibble, which is what pins `'0' == 0xc5`; the rest follows
from the hall-of-fame text and the cheat table both decoding cleanly under it.


## 1. The boot chain, `0x10000` → `main`

`0x10000` is a single `bra.w $14bee`; the 44 bytes behind it are the plaintext banner
`PROGRAMMING BY PRIME SOFTWARE & IMAGES DESIGN`.

`0x14bee` `boot_init`, step by step:

| addr | what |
| --- | --- |
| `0x14bee` | `movea.l #$19094,a7` — the program's own supervisor stack, growing **down**. |
| `0x14bf4` | GEMDOS `Super(0)`; the old SSP goes to `0x19014` and is **never read back** — the program never returns to user mode and never returns to the desktop. |
| `0x14c04` | XBIOS `Setscreen(log=0x70000, phys=0x78000, rez=0)` — forces low resolution with absolute addresses, i.e. it assumes where TOS put the screen. |
| `0x14c20` | XBIOS `Physbase` → `d0`. |
| `0x14c26` | `screen_ring_base_raw` (`0x163fa`) `= d0 - 0x1f900`. |
| `0x14c34` | `screen_ring_base` (`0x16422`) `= (raw + 0x100) & ~0xff` — `addi.l #$100 / clr.b d0`, i.e. round **up** to a 256-byte boundary. |
| `0x14c48` | ring[0] `0x16406 = base + 0x7800`, also seeded into `screen_prev1` (`0x1641a`). |
| `0x14c5c` | ring[1] `0x1640a = base + 0xfa00`, also seeded into `screen_draw` (`0x16416`). |
| `0x14c74` | ring[2] `0x1640e = base + 0x17700`. |
| `0x14c86` | ring[3] `0x16412 = base + 0x1f400`, also seeded into `screen_prev2` (`0x1641e`). |
| `0x14c9e` | `load_file(file_rec_module_bak)` — `A\MODULE.BAK` to `0x58928`. The **only** file boot loads. |
| `0x14ca8` | `sr = 0x2700` (IPL 7). |
| `0x14cac` | `move.l $70.l,$11650.l` — see §4; `$11650` is the operand of a `jmp`. |
| `0x14cb6` | install `vbl_handler` (`0x11636`) at `$70`. |
| `0x14cc2` | install `acia_ikbd_isr` (`0x14218`) at `$118` = 68000 vector 70 = MFP channel 6 = IKBD/MIDI ACIA. |
| `0x14cce` | `sr = 0x2300` (IPL 3 — MFP interrupts on). |
| `0x14cd2` | BIOS `Bconout(dev=4, 0x14)`: IKBD command **`$14` = set joystick event reporting**. This is what makes the ACIA deliver `$FE`/`$FF`-prefixed joystick packets, and therefore what the ISR's first two comparisons are for. |
| `0x14ce4` | XBIOS `Kbdvbase` → `a0`; `a0 += 0x18` = **`joyvec`**; old value → `0x19098`, `tos_joyvec_handler` (`0x141fa`) installed. |
| `0x14d00` | `clr.w $176d4`. |
| `0x14d06` | `bra.w $15750` = `main`. |

`main` (`0x15750`) calls `init_load_assets` (`0x11212`), `init_new_game` (`0x112fa`),
`init_stage_state` (`0x1139a`), then falls into an endless 45-call frame loop
`0x1575c`..`0x1580c` that ends `clr.w level_restarting; bra $1575c`.

**Neither of the last two init calls returns.**  `init_new_game` ends `bra.w $1030e`
(`enter_title`), and `init_stage_state` tail-calls `start_level`.  So `main`'s three "calls"
are really a chain, and the front end runs off `main`'s stack frame.  The two re-entry
labels the front end uses are:

* `0x15754` — after `init_load_assets`, i.e. "restart the game".  Reached by
  `game_over_hiscore_check` (`bra.w $15754`, twice).
* `0x1575c` — the frame-loop top.  Reached by `restart_level_at_checkpoint`.

Both are reached by `bra`, after a hand-rolled stack unwind (`adda.l #$40,a7` in
`read_player_input`, `addq.l #4,a7` at `0x13c62`/`0x13c8e`) rather than by returning.


## 2. The screen / framebuffer model

The game does **not** double-buffer in the usual sense.  It builds a **circular framebuffer
of 0x1f900 bytes = 808 scanlines** immediately below `Physbase`, keeps **four** screen bases
inside it, and scrolls vertically by **moving a base**, not by moving pixels.

```
screen_ring_base   = round_up_256(Physbase - 0x1f900)
ring[0] 0x16406    = base + 0x7800    (row 192)
ring[1] 0x1640a    = base + 0xfa00    (row 400)
ring[2] 0x1640e    = base + 0x17700   (row 600)
ring[3] 0x16412    = base + 0x1f400   (row 800)
```

Row spacings: 208, 200, 200, and 200 from ring[3] back around to ring[0]
(`(0x7800 + 0x1f900 - 0x1f400)/160 = 200`), summing to exactly the 808-row ring.

Once per **displayed** frame, at `0x147ec`..`0x1481e`:

```
screen_ring_index = (screen_ring_index + 1) & 3
slot = &ring[screen_ring_index]
*slot -= 0x500                       ; 1280 bytes = 8 scanlines -- THE SCROLL
if (*slot < screen_ring_base) *slot += 0x1f900   ; wrap by 808 rows
screen_prev2 = screen_prev1
screen_prev1 = screen_draw
screen_draw  = *slot
```

and the frame is published at `0x1476e` with
`Setscreen(log = -1, phys = screen_draw, rez = -1)` — physical base only, resolution
untouched (so TOS does not clear anything; see `docs/tos-os-calls.md`, "`Setscreen` does
three things").

**Why the `& ~0xff`.**  The ST shifter's screen-base register (`$ffff8201/8203`) holds only
the high two bytes of the address, so the finest base the hardware can point at is a
256-byte boundary.  Rounding the ring base up guarantees every derived base — `base + k*160`
after repeated `-0x500` steps — stays legal, since 0x500 and 0x1f900 are both multiples of
256.

**Frame pacing** (`0x14786`): spin until the longword `vbl_tick` reaches 3, then XBIOS
`Vsync`, then `clr.l vbl_tick`.  **One displayed frame = three vertical blanks**, i.e. a
16.7 Hz game on a 50 Hz machine and a fixed 8-scanline scroll step per frame.

`scroll_phase` (`0x16430`, the debug overlay's "TCOUNT") advances by 2 each frame and is
masked with `0x1f`, so it cycles 0,2,…,30 over 16 frames; the wrap to 0 steps `map_ptr`
(`0x16402`) **back** `0x14` bytes — one map row — because the map is read from its end
towards its start.

Memory footprint: the ring occupies `Physbase-0x1f800` .. `Physbase`, and the topmost bases
read a further 200 rows above `Physbase`, so the whole scrolling surface is about 0x27600
bytes ending just under `Physbase + 0x7d00`.


## 3. The file-loading protocol

### The record format

`0x162ee` onward is a table of eight records, each `[dest.l][length.l]` followed by a
NUL-terminated DOS path.  **Both longwords carry relocation entries**, so the `0x0000be36`
in the file is `0x0001be36` at run time — the image's BSS start.

| record | dest | length | path |
| --- | --- | --- | --- |
| `0x162ee` | `0x1be36` | `0x7d80` | `A\FLY_SHK.NEO` |
| `0x16304` | `0x58928` | `0x1065` | `A\MODULE.BAK` |
| `0x1631a` | `0x1be36` | `0x1caf2` | `A\SPRITES.cru` |
| `0x16330` | `0x16432` | `0x1388` | `A\LEVEL1.MAP` |
| `0x16346` | `0x38928` | `0x8000` | `A\HSC_0.DAT` |
| `0x1635a` | `0x40928` | `0x8000` | `A\HSC_1.DAT` |
| `0x1636e` | `0x48928` | `0x8000` | `A\HSC_2.DAT` |
| `0x16382` | `0x50928` | `0x8000` | `A\HSC_3.DAT` |

Note `A\LEVEL1.MAP` loads to `0x16432`, i.e. **inside the DATA segment**, not BSS; its first
two words are the map's row width in words and its row count, and `map_data` starts at
`0x16436`.  Note also that `SPRITES.cru` loads **over** the title picture at `0x1be36`.

### `load_file` (`0x10bfa`)

`a0` → a record.  Copies the two longwords to `load_dest`/`load_len`, leaves `a0` on the
name, then `Fopen(name, 2)` → `load_file_handle`, `Fread(handle, load_len, load_dest)`,
`Fclose`.  **There is no error handling of any kind** — a missing file leaves a negative
handle and a failed read.

### `probe_disc` (`0x10c4c`) — the disc handshake

`probe_disc` ignores its caller's `a0`: it always `Fopen`s the name embedded in
`file_rec_sprites_cru` and stores the full longword result in `disc_probe_result`
(`0x17692`), closing the handle again if it opened.  Callers then test the sign:

* **"INSERT DISC A"** loops retry while the result is **negative** (disc A absent).
* **"INSERT DISC B"** loops retry while the result is **non-negative** — because disc A
  still being readable is how you know disc B has not been swapped in.

### `load_level_assets` (`0x10332`) — filename patching

`d0` = level (0..4).  Five bytes from `level_bank_digits` (`0x162d4`, the ASCII string
`"012314567289AB3013B48C375"`, 5 per level) are written into byte 6 of each of the four
`A\HSC_n.DAT` names (`0x16354`, `0x16368`, `0x1637c`, `0x16390`) and byte 7 of
`A\LEVEL1.MAP` (`0x1633f`).  One record set therefore serves every stage:

| level | HSC banks | map |
| --- | --- | --- |
| 0 | 0 1 2 3 | LEVEL1 |
| 1 | 4 5 6 7 | LEVEL2 |
| 2 | 8 9 A B | LEVEL3 |
| 3 | 0 1 3 B | LEVEL4 |
| 4 | 8 C 3 7 | LEVEL5 |

The four HSC slots are 32 KB each at `0x38928`/`0x40928`/`0x48928`/`0x50928` (the file table stores absolute, relocated destinations; the earlier draft of this note quoted them as program-relative).
Levels 3 and 4 deliberately reuse earlier banks — the digit list is not a mistake, it is how
the two-disc split was arranged.

### The disc prompts, and why you will not see them

**This `.PRG` is a patched single-disc build.**  Six sites have had their leading word or
byte overwritten so the game never asks for a swap.  In every case the *tail* of the
original instruction is still in the file and decodes exactly, which is what makes this a
finding rather than a hunch:

| addr | in the file now | the original, from the surviving bytes |
| --- | --- | --- |
| `0x1127e` | `602c` `bra.s $112ac` | `6100 f97a` = `bsr.w $10bfa` — the first `SPRITES.cru` load |
| `0x10390` | `601e` `bra.s $103b0` | `4df9 0000 4a24` = `lea text_insert_disc_a,a6` |
| `0x103ea` | `6000 0004` `bra.w $103f0` | `6a00 0004` = `bpl.w $103f0` (one byte, `6a`→`60`) |
| `0x10422` | `601e` `bra.s $10442` | `4df9 0000 4a24` = `lea text_insert_disc_a,a6` |
| `0x1044c` | `6022` `bra.s $10470` | `4df9 0000 4a4d` = `lea text_insert_disc_b,a6` |
| `0x10498` | `601e` `bra.s $104b8` | `4df9 0000 4a24` = `lea text_insert_disc_a,a6` |
| `0x104cc` | `6022` `bra.s $104f0` | `4df9 0000 4a4d` = `lea text_insert_disc_b,a6` |

Each prompt loop has the same shape, and the one at `0x103cc` — whose `lea` head survived,
only its branch-back was neutered — shows it intact:

```
lea <message>,a6
bsr.w console_show_message        ; prints and waits for FIRE to be RELEASED
btst #7,joy1_state / beq          ; wait for FIRE to be PRESSED
bsr.w probe_disc
tst.l disc_probe_result
bpl/bmi <continue>                ; sign test picks disc A vs disc B
bra   <retry>
```

The one oddity: at `0x103cc` the surviving `lea` names `0x16022`, which is not a string — it
is the middle of a signed word-pair table, and its first byte is `0xff`, so
`console_show_message` prints nothing and only waits for the fire button.  Either that site
was re-pointed too, or the third prompt was always a silent pause.  Recorded as an
observation, not a claim.

A seventh site is **suspected but unproven**: `0x147da` is a bare `nop` between
`cmpa.l #$16432,a0` and a `move.l $163fe,$16402` that the next instruction overwrites,
leaving the map-wrap store dead.  That is the shape of a patched-out conditional branch, but
no surviving operand confirms it.


## 4. The interrupt model

### VBL — `vbl_handler` (`0x11636`), vector `$70`

Taken **outright**, not via a `_vblqueue` slot (contrast `docs/hardware-map.md`, which
recommends the queue).  The handler is three things:

```
011636: movem.l d0-d7/a0-a6,-(a7)
01163a: addq.l #1,vbl_tick            ; 0x17720, longword
011640: lea $58944,a0 / jsr 38(a0)    ; the sound module's tick
01164a: movem.l (a7)+,...
01164e: jmp $1164e.l                  ; <-- SELF-MODIFYING
```

The `jmp`'s **operand longword lives at `0x11650`**, and the image ships it pointing at the
`jmp` itself (a self-loop).  `boot_init` overwrites it with the old `$70` vector
(`move.l $70.l,$11650.l`), so the handler **chains to TOS's own level-4 handler** instead of
`rte`-ing.  That is what keeps `_v_bas_ad`, `_frclock` and the rest of TOS's blank-time
housekeeping alive under a program that owns the vector.

`count_game_frame` (`0x11654`) is the loop's own counter, a separate longword at `0x17764`,
incremented once per *displayed* frame.

### The ACIA — `acia_ikbd_isr` (`0x14218`), vector `$118` (MFP channel 6)

The game takes the IKBD/MIDI ACIA vector away from TOS entirely.  The handler is a **tiny
state machine implemented by re-vectoring `$118`**:

```
d1 = $fffffc02                       ; ACIA data
if d1 == 0xFE:  $118 = acia_joy0_byte ; joystick-0 packet header
elif d1 == 0xFF: $118 = acia_joy1_byte ; joystick-1 packet header
else: <keyboard scancode, below>
bclr #6,$fffffa11                    ; clear the MFP in-service bit
rte
```

`acia_joy0_byte` (`0x1430c`) and `acia_joy1_byte` (`0x14330`) each read one more byte into
`joy0_state` / `joy1_state`, restore `$118` to `acia_ikbd_isr` and `rte`.  The `$FE`/`$FF`
packets exist because `boot_init` sent IKBD command **`$14`** (set joystick event
reporting).

Keyboard path: the raw byte is stored at `key_last_scancode` (`0x17781`); `bclr #7,d1`
separates make from break; then eight unrolled compares against
`key_watch_scancodes` (`0x17782`, initialised data) do `bset d0,key_bits` on a make and
`bclr d0,key_bits` on a break.  The watched set, in bit order:

| bit | scancode | key | used for |
| --- | --- | --- | --- |
| 0 | `0x6b` | keypad `4` | arms `check_cheat_name`; also `debug_wait_for_keypad4` |
| 1 | `0x19` | `P` | pause |
| 2 | `0x44` | `F10` | abort → game over |
| 3 | `0x00` | — | unused slot |
| 4 | `0x74` | keypad Enter | (no reader found) |
| 5 | `0x39` | Space | bomb / secondary fire |
| 6 | `0x62` | Help | (no reader found) |
| 7 | `0x00` | — | unused slot |

### `tos_joyvec_handler` (`0x141fa`) — dead

`boot_init` also installs this into `KBDVBASE + 0x18` (`joyvec`), saving the old pointer at
`0x19098`.  It copies packet bytes 1 and 2 to `joy0_state`/`joy1_state`.  **It can never
run**: the only caller of `joyvec` is TOS's own IKBD packet parser, which lives behind the
ACIA vector the game has already taken.  Its `lea $1777e(pc),a1` is loaded and never used,
which is the usual sign of a routine that was cut down but not removed.

*This is the correction the briefing needs*: `$18` here is a KBDVBASE field offset, not
68000 vector 6 (CHK).  There is no CHK handler, and the `trap #4` at `0x14a3c` is the `N`,`D`
of "AND" inside the `PLEASE INSERT DISC A` string.

### `read_player_input` (`0x14354`)

The frame loop's input step.  Picks `key_bits` when `use_keyboard_flag` (`0x1770e`) is
non-zero and `joy1_state` otherwise — but **`use_keyboard_flag` is read here and written
nowhere in the image**, swept in both the long and the short absolute encodings.  Keyboard
control is a dormant switch; the game always reads joystick 1.

While `level_restarting` is clear it services two system keys first:

* key bit 1 (`P`) — pause: spins while `joy1_state == 0`, so any joystick input resumes.
* key bit 2 (`F10`) — abort: `adda.l #$40,a7 / bra game_over_hiscore_check`.

Then key bit 5 or `joy0_state` bit 7 fires the bomb (`0x13d5c`), and `joy1_state` bits 0/1/2/3
and 7 drive `0x13da0`/`0x13db0`/`0x13dc2`/`0x13de8`/`0x13e12`.


## 5. Front-end flows

```
boot_init
  └─ main ─ init_load_assets ─ init_new_game ──bra──▶ enter_title
                                                        │
                                          title_attract_loop  ◀──┐
                                            │  fire + !new_hiscore
                                            ▼                    │
                                          rts to main ─ init_stage_state ─ start_level
                                            │                    │
                                            ▼                    │
                                          frame loop (0x1575c)   │
                                            ├ life lost ─▶ restart_level_at_checkpoint ─▶ 0x1575c
                                            ├ lives = 0 ─▶ game_over_hiscore_check
                                            └ F10       ─▶ game_over_hiscore_check
                                                             │
                                              beats rank 6? ──┴─▶ 0x15754 (new game)
                                                                     ▼
                                              new_hiscore_pending set → title_attract_loop
                                                    └─▶ hiscore_show_entry_screen
                                                          └─ hiscore_name_entry
                                                                └─ check_cheat_name
```

**Title / attract** (`title_attract_loop`, `0x104f2`).  Prescrolls the level-1 map with the
palette black, then runs the attract scroll while cycling three text pages on
`attract_page_timer`:

* `text_publisher` (`0x160de`) — "PROGRAMMED BY BRITISH TELECOM / COPYRIGHT TAITO CORP 1987"
* `text_credits` (`0x16146`) — "PROGRAMMING BY HENRY S CLARK AND KARL D JEFFERY / GRAPHICS BY
  JASON G LIHOU / SOUND BY J C BROOKE"
* `text_hall_of_fame` (`0x161ce`) — "HALL OF FAME" plus the six live hiscore rows

Joystick-1 left/right toggle `hard_mode` and copy `title_word_easy` / `title_word_hard` into
`title_mode_word` (`0x1612a`).  **The mode line is never drawn in this build**: the script at
`0x16120` is only ever `lea`d for its `+10` word field, is not one of the three pages passed
to `build_text_display_list`, and has no `0x09` terminator of its own.

**Text scripts** (`build_text_display_list`, `0x10698`).  `[x.b][y.b]` then a byte stream —
`0x00` space (x += 8), `0x04` x += 0x40, `0x05` newline, `0x06` x += the word **at address
`0x40`** (low memory; almost certainly a bug), `0x09` end, anything else a glyph.  Output is
6-byte display-list slots `{x.w, y.w, glyph.b, enable.b}`.

**Hall of fame** (`hiscore_table`, `0x161dd`).  Six 22-byte rows that are simultaneously part
of `text_hall_of_fame`'s script:

```
+0..2   05 05 04        newline newline tab
+3..7   five 0x00       spaces
+8      rank digit      '1'..'6'
+9..10  0x00 0x00       spaces
+11..13 name            3 characters   <- hiscore_name_entry writes here
+14..15 0x00 0x00       spaces
+16..21 score           6 digits       <- compare_score_chars reads here
```

Shipped defaults: `HSC 250000`, `KDJ 200000`, `JGL 175000`, `R H 150000`, `J H 100000`,
`R P 050000`.

**Game over → hi score** (`game_over_hiscore_check`, `0x10724`).  Compares the score against
row 6, walks up to find the rank, shifts the beaten rows down with
`hiscore_shift_entry_down` (13 bytes from `+9`, leaving the rank digit alone), writes the
score into `+16`, sets `new_hiscore_pending` and jumps to `0x15754`.  The *name* is entered
later, from the attract loop, by `hiscore_show_entry_screen` → `hiscore_name_entry`.

**Name entry** (`hiscore_name_entry`, `0x10916`).  Three characters, right/left to cycle
`0xab`..`0xcf` (A..Z, 0..9, space), fire to advance.  The third fire calls
`check_cheat_name` and starts a `name_entry_timeout` countdown back to the attract loop.

**"GAME OVER"** is `text_game_over` (`0x1613a`), drawn at x=124, y=96 by `0x13c6c`, held for
`game_over_timer` (`0x176aa`, 80) frames.


## 6. The cheat system

`check_cheat_name` (`0x10d92`) runs the moment the third hi-score initial is confirmed.  It
first spins up to 5000 iterations waiting for **key bit 0 (keypad `4`, scancode `0x6b`) to be
held** — so a cheat only arms with that key down.  Then the three characters are matched
against `cheat_name_table` (`0x191e4`): six 4-byte rows of three name codes plus a handler
index, terminated by `0x64`.  On a hit it `jsr`s `cheat_handler_table[index]` (`0x191cc`) and
copies `title_word_spam` over `title_word_easy`, so the title's left option becomes "MODE
SPAM".

| name | handler | flag | effect |
| --- | --- | --- | --- |
| `HSC` | `0x10e30` | `invuln_flag` `0x177c6` | both collision routines (`0x1101c`, `0x10f26`) return immediately. Entering it a **second** time sets `player_hit` instead — it kills you. |
| `KDJ` | `0x10e4c` | `infinite_lives_flag` `0x177c7` | `0x13c34` skips `lives -= 1` |
| `JGL` | `0x10e56` | `infinite_bombs_flag` `0x177c8` | `0x13d6c` skips `bombs -= 1` |
| `GCC` | `0x10e60` | `alt_bullet_glyph_flag` `0x177c9` | `0x1416a` swaps the projectile glyph `0x7f` → `0xe4` |
| `JML` | `0x10e6a` | — | `movea.l #0,a0 / jsr (a0)` — it deliberately **calls address 0**. A booby trap. |
| `J H` | `0x10e72` | `max_weapon_flag` `0x177ca` | `0x13ec2` forces `weapon_level = 4`; also survives a new game (`0x1134c`) and a checkpoint restart (`0x14b4e`) |

The names are the developers' initials, straight off the credits page and the shipped
hall-of-fame defaults — `HSC` = Henry S Clark, `KDJ` = Karl D Jeffery, `JGL` = Jason G Lihou.

Two loose ends in the same system, both **write-only or read-only**:

* `cheat_used_flag` (`0x176d4`) is set on any match and cleared once by `boot_init`, and
  **nothing ever reads it**.
* `keep_player_hit_flag` (`0x177cb`) is read at `0x113e6` and `0x14b40` to suppress the
  `player_hit = 0` on a stage reset, and **nothing ever writes it** — a seventh cheat with no
  handler behind it.
* `debug_overlay_flag` (`0x177cd`) gates `debug_show_counters` and is likewise never written.

There is one more piece of unreferenced initialised data: `easter_egg_scancodes` (`0x1778a`),
fourteen ST scancodes sitting immediately above the eight-entry `key_watch_scancodes`, which
spell a (rude) message about a colleague.  `acia_ikbd_isr` stops at eight entries and no
instruction anywhere names `0x1778a`, so nothing reads them.


## 7. Debug leftovers

| addr | what | reachable? |
| --- | --- | --- |
| `0x14960` `debug_show_counters` | formats `map_ptr - map_ptr_start` ("MPOINTER"), `scroll_y` ("MASTY") and `scroll_phase` ("TCOUNT") into `text_debug_counters` and falls through into `console_show_message` | called from `0x13e1a`, gated on `debug_overlay_flag`, **never written** → off |
| `0x14996` `console_show_message` | `Setscreen(log = screen_prev1)`, VT52 `ESC Y` to row 24 col 0, `Cconout` until a byte with bit 7 set, then wait for fire to be released | live (the disc prompts, when unpatched) |
| `0x14a76` `format_5_digits` | five `'0'`s forward, then digits written backwards with `move.b d0,-(a0)` | live |
| `0x11570` `debug_print_word_binary` | prints `d4` as 16 ASCII `0`/`1` plus CR via `Cconout` | **no caller** |
| `0x11ba2` `debug_wait_for_keypad4` | spins on key bit 0 | **no caller** |


## 8. Globals census (this slice)

Width `b`/`w`/`l` = byte/word/long.  "R/W" lists the routines this slice found; a routine in
the frame loop that is another agent's is given by address.

### Screen and scroll

| addr | name | w | role | written by | read by |
| --- | --- | --- | --- | --- | --- |
| `0x163fa` | `screen_ring_base_raw` | l | `Physbase - 0x1f900` | `boot_init` | `boot_init` only |
| `0x163fe` | `map_ptr_start` | l | map end = scroll origin | `0x104f2`, `0x11440` | `0x14960`, `0x14b9a` |
| `0x16402` | `map_ptr` | l | map read cursor ("MPOINTER") | `0x104f2`, `0x11440`, `0x147dc`, `0x14ba6` | `0x14960`, `0x1454a`, `0x147ca`, `0x1483a` |
| `0x16406`..`0x16412` | `screen_ring[0..3]` | l×4 | four rotating screen bases | `boot_init`, `0x14808` | `0x14834` |
| `0x16416` | `screen_draw` | l | frame being drawn / published | `boot_init`, `0x14834` | `0x14446`, `0x1476e`, `0x1492c`, `0x1582a` |
| `0x1641a` | `screen_prev1` | l | previous frame | `boot_init`, `0x1482a` | `console_show_message` |
| `0x1641e` | `screen_prev2` | l | frame before that | `boot_init`, `0x14820` | `0x14932` |
| `0x16422` | `screen_ring_base` | l | ring low limit + clean-row source | `boot_init` | `0x1444c`, `0x1480e` |
| `0x16426` | `sprite_plane_mask` | b | blitter plane/clip mask | `0x14de0`..`0x15220` | `0x14e40`..`0x15386` |
| `0x1642a` | `level_index` | w | current stage 0..4 | `0x11342`, `0x12504`, `0x1252e`, `0x12548`, `0x12562`, `0x12580` | `start_level`, `0x14ad2`, `0x10bc8` |
| `0x1642c` | `prescroll_flag` | b | set during a black prescroll | `0x1052a`, `0x11544`, `0x14bc0` | `0x14474` |
| `0x1642e` | `screen_ring_index` | w | 0..3 | `0x147f8` | `0x1448a`, `0x147ec`, `0x14918` |
| `0x16430` | `scroll_phase` | w | 0,2,…,30 ("TCOUNT") | `0x10500`, `0x113d0`, `0x147ba`, `0x14bb6` | `0x14960` and eight sites in `scroll_step` |
| `0x16432` | `map_width_words` | w | map header | `A\LEVELn.MAP` | `0x1050e`, `0x11524` |
| `0x16434` | `map_rows` | w | map header | `A\LEVELn.MAP` | `0x10508`, `0x1151e` |
| `0x16436` | `map_data` | — | tile rows, `0x14` bytes each | `A\LEVELn.MAP` | via `map_ptr` |

### Loader

| addr | name | w | role |
| --- | --- | --- | --- |
| `0x17692` | `disc_probe_result` | l | `Fopen` result from `probe_disc`; sign = disc A present |
| `0x17774` | `load_file_handle` | w | GEMDOS handle inside `load_file` |
| `0x17776` | `load_dest` | l | destination from the record |
| `0x1777a` | `load_len` | l | length from the record |

### Input

| addr | name | w | role | written | read |
| --- | --- | --- | --- | --- | --- |
| `0x1777e` | `joy0_state` | b | joystick 0 packet byte | `acia_joy0_byte`, (dead) `tos_joyvec_handler`, cleared `0x1139a`/`0x14aa8` | `0x143c8` (bit 7 only) |
| `0x1777f` | `joy1_state` | b | joystick 1 = the player | `acia_joy1_byte`, (dead) joyvec, cleared `0x1139a`/`0x14aa8` | `read_player_input`, all six prompt loops, `console_show_message`, `hiscore_name_entry`, title left/right |
| `0x17780` | `key_bits` | b | 8-key held mask | `acia_ikbd_isr` | `0x10d9a`, `0x1128a`, `0x11ba6`, `read_player_input` |
| `0x17781` | `key_last_scancode` | b | raw byte | `acia_ikbd_isr`, cleared `0x1139a`/`0x14aa8` | — |
| `0x17782` | `key_watch_scancodes` | b×8 | the eight watched codes | initialised data | `acia_ikbd_isr` |
| `0x1778a` | `easter_egg_scancodes` | b×14 | unreferenced message | initialised data | **nothing** |
| `0x1770e` | `use_keyboard_flag` | w | keyboard-vs-joystick select | **nothing** | `read_player_input` |

### Timing, vectors, stack

| addr | name | w | role |
| --- | --- | --- | --- |
| `0x17720` | `vbl_tick` | l | `+1` per VBL; frame pacer waits for 3 and clears |
| `0x17764` | `frame_counter` | l | `+1` per displayed frame (`count_game_frame`) |
| `0x11650` | `vbl_chain_vector` | l | **the `jmp` operand at `0x1164e`**; boot writes TOS's old `$70` here |
| `0x19014` | `saved_super_ssp` | l | `Super(0)` result; never read |
| `0x19094` | `stack_top` | — | initial `a7`; only 0x80 bytes above `saved_super_ssp` |
| `0x19098` | `saved_tos_joyvec` | l | old `KBDVBASE+0x18` |

### Front-end state

| addr | name | w | role |
| --- | --- | --- | --- |
| `0x17696` | `level_restarting` | w | set by `restart_level_at_checkpoint`, cleared at `0x15810` |
| `0x17698` | `title_just_entered` | w | set by `enter_title`, consumed by the title left handler |
| `0x176e6` | `attract_page_timer` | w | counts down; reloads from `attract_page_reload` |
| `0x1771e` | `attract_page_reload` | w | reload value, constant **750** (`0x2ee`) — read once, written nowhere |
| `0x176e8` | `new_hiscore_pending` | w | a name still has to be entered |
| `0x176ea` | `level0_assets_loaded` | w | guards the level-0 asset load |
| `0x176dc` | `name_entry_done` | w | third initial confirmed |
| `0x176de` | `name_entry_timeout` | w | frames left before the attract resumes |
| `0x176e0` | `hiscore_rank` | w | 0..5, the row being edited |
| `0x176e2` | `name_entry_cursor` | w | 0..2 |
| `0x176e4` | `beat_hiscore` | w | this game passed the displayed hi score |
| `0x176aa` | `game_over_timer` | w | `0x50`, the "GAME OVER" dwell |
| `0x1769a` | `game_over_flag` | w | set with the GAME OVER text |
| `0x17752` | `prescroll_count` | w | prescroll repeats, constant **107** (`0x6b`) — read at `0x10532`, `0x1154c`, `0x14bc8`, written nowhere |
| `0x17758` | `scroll_y` | w | distance scrolled ("MASTY"); attract restarts past `0xbb8` |
| `0x176ac` | `const_words` | w×10 | the constants 0..9 at `+2n`, used as memory-source immediates |
| `0x17706` | `player_hit` | w | player was hit / is dying |
| `0x17710` | `bombs` | w | init 3, max 6 |
| `0x17712` | `lives` | w | init 5 (`const_words[5]`), max 6 |
| `0x17714` | `weapon_level` | w | 0..4, indexes the dispatcher at `0x19232` |
| `0x176c6`..`0x176d2` | `extra_life_awarded[0..6]` | w×7 | one per threshold |
| `0x176d4` | `cheat_used_flag` | w | write-only |
| `0x177c6`..`0x177cd` | cheat flags | b×8 | see §6 |
| `0x177ce` | `display_list` | — | 223 slots of `{x.w,y.w,glyph.b,enable.b}`, `0x177ce`..`0x17d07` |

### Score data (all in DATA, all initialised)

| addr | name | shape |
| --- | --- | --- |
| `0x159f4` | `score_chars` | 6 glyph codes |
| `0x159fa` | `hiscore_chars` | 6 glyph codes |
| `0x15a00` | `extra_life_thresholds` | 7 × 6 glyphs: 050000, 200000, 350000, 500000, 650000, 800000, 950000 |
| `0x15a2a` | `score_bcd` | 3 packed-BCD bytes |
| `0x15a2d` | `hiscore_bcd` | 3 bytes, shipped `25 00 00` = 250000 |
| `0x15a30` | `score_award_values` | 9 × 3 BCD bytes: 50, 100, 200, 250, 500, 1000, 3000, 5000, 10000 |
| `0x15a4c` | `level_params` | 5 × 20 bytes → `0x1771c`, `0x1770a`, `0x1776e`, `0x17770` |
| `0x15ab0` | `checkpoint_tables` | 5 longword pointers, one per level |


## 9. Open questions

1. **`0x16022`** — the surviving `lea` operand at the third disc prompt points into a word
   table, not a string, so that prompt prints nothing.  Was that site re-pointed too, or was
   it always a silent "press fire"?  Answering it needs the original two-disc release to
   diff against.
2. **`0x147da`** — the bare `nop` that makes the map-wrap store dead.  A patch, or original?
   Nothing in the image settles it.
3. **The mode line.**  `hard_mode` is selectable and used, but `text_title_mode` has no draw
   site and no terminator.  Was the label lost in the same edit that removed the disc
   prompts?
4. **`key_watch_scancodes[4]` (keypad Enter) and `[6]` (Help)** set bits 4 and 6 of
   `key_bits`, and no `btst #4`/`btst #6` on `0x17780` exists anywhere in the image.  Two
   more dormant keys, or bits read through a mask I have not found?
5. **`0x1775e` `input_locked`** gates `read_player_input` off entirely.  It is set at
   `0x13a42`, `0x13ab2`, `0x13b26` and `0x13bf4` and cleared at `0x13b06` — all inside the
   death/respawn sequence, which is the gameplay agent's.  Named here only so the two slices
   agree on it.
6. **The `0x10698` opcode `0x06`** adds the word at absolute address `0x40` (low memory,
   inside `_etv_timer`) to the pen x.  No shipped script appears to use it; worth a scan of
   the three attract scripts before calling it dead.
7. **Levels 3 and 4 reuse HSC banks 0/1/3/B and 8/C/3/7.**  That implies `HSC_C.DAT` exists
   on the disc although no record names it directly — the data-format agent should confirm
   the disc's file list.
