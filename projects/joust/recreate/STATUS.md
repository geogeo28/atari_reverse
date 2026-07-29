# Reconstruction status — Joust

Human-readable C reconstruction of Joust's 75 functions, each **verified byte-for-byte against
the original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi
oracle running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 28/75.** The 75 are the functions in `../decomp.c`'s inventory; `../names.txt` is the
source of truth for every name.

## Method per function
1. Read the target in `../decomp.c` **and** the disassembly (`../out/joust_dis.txt`) — Ghidra
   renders Joust's register-argument routines as a bare `return;`, so the listing is not optional.
2. Write the idiomatic core in `src/<subsystem>.c` plus its glue `g_<name>` (the I/O contract).
3. Add address constants to `include/addrs.h`, prototypes to `include/joust.h`.
4. Add edge + fuzz cases in `test/test_<subsystem>.py`; `make test` must be green.
5. Mark the row below verified, with what the verification actually covered.

## Ordering
Leaf/pure functions first (no OS traps, simple contracts), then their callers, then the
trap-bound ones. The seven traps that used to block the sound, input and high-score-save layers —
`Super`, `Giaccess`, `Fcreate`, `Fwrite`, `Random`, `Bconstat`, `Bconin` — are modelled by the kit
now (`tools/recreate_kit/TRAP_MODEL.md`, pinned by `test/test_os_traps.py`). Two GEMDOS selectors
Joust also uses stay unmodelled on purpose and still raise: `Pterm` (0x4c) never returns, so there
is no post-state to diff, and `Dgetdrv` (0x19) asks about a machine the harness does not have.

## Off the list: the raw-floppy routine at `0x152dc`

**Unverifiable under the current oracle — not pending work.** It is not one of the 75 rows below
(it is absent from `../decomp.c`'s inventory), and it must stay unreconstructed. Its drive-select
subroutine reads the PSG select port directly (`move.b $ff8800,d1` at `0x15544`), and the kit
rejects **any** direct PSG read *on its own* — independently of the mixed-path guard — because the
ledger records writes only and there is nothing correct to return. So no `emu.run` reaching that
instruction can ever be green, and reconstructing the routine cannot be verified. It unblocks only
when the oracle gains a real PSG read model. Narrowing a guard to make it pass would restore the
fabricated `0` read the guard exists to prevent (`tools/recreate_kit/TRAP_MODEL.md`, Phase 3).

## Functions (by address)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10000` | `_start` | 128 | ⬜ pending | |
| `0x10080` | `init_system` | 488 | ⬜ pending | |
| `0x102e2` | `fill_screen` | 28 | ✅ verified | 32008 bytes from screen_base — 8 PAST the framebuffer, reproduced; colour words incl. 0x100/0x101; poison |
| `0x102fe` | `make_fill_pattern` | 54 | ✅ verified | colour bytes 0..0xff exhaustively + long-D0 edges + 400-case fuzz; D1/D2 captured via a store stub, poison on 10 shapes |
| `0x10334` | `fill_pattern_n` | 10 | ✅ verified | counts 1/2/3/0xff/0x100/0x101/0x1000/0xfffe/0xffff x 4 patterns, count 0 = 65536 cells, hi-garbage counts, 400-case fuzz; end pointer == oracle A0 |
| `0x1033e` | `count_objects_and_pad` | 236 | ✅ verified | live/egg counts over all 8 slot shapes incl. the respawn+prev_dst rule, player-1 egg window, message-char walk + 0x23 cap, game_phase selection; poison on 5. The 3 pad loops touch no memory |
| `0x1042a` | `blit_copy` | 44 | ✅ verified | 18 shapes (row overlap, 0 = 256, low-byte-only counts) + 300-case fuzz, noise src/dst, poison on 5, plus a rectangle laid over its own argument block to pin the per-row `cols` re-read |
| `0x10456` | `blit_or` | 44 | ✅ verified | same battery as blit_copy |
| `0x10482` | `blit_andnot` | 48 | ✅ verified | same battery as blit_copy |
| `0x104b2` | `init_video` | 124 | ⬜ pending | |
| `0x1052e` | `draw_platforms` | 148 | ⬜ pending | |
| `0x105c2` | `rng_advance` | 46 | ✅ verified | 12 edge cursors (wrap threshold, longword wrap, signed-negative) x 10 mixes with poison + hi-garbage mixes + 600-case fuzz; D0 preserved |
| `0x105f0` | `init_game` | 272 | ⬜ pending | |
| `0x10700` | `draw_string` | 622 | ✅ verified | both fonts x all 236 non-control glyphs, 16 shifts/colours/bg, all 6 control bytes, backspace cell-borrow, text drawn onto its own state block (per-plane re-read), 200-case sharded fuzz |
| `0x1096e` | `snd_tone_sweep` | 232 | ⬜ pending | |
| `0x10a56` | `play_sound` | 52 | ⬜ pending | |
| `0x10a8a` | `snd_poll_done` | 36 | ⬜ pending | |
| `0x10aae` | `title_screen` | 408 | ⬜ pending | |
| `0x10c46` | `xbios_setpalette` | 16 | ⬜ pending | |
| `0x10c56` | `cycle_palette` | 124 | ⬜ pending | |
| `0x11c24` | `poll_quit_key` | 114 | ⬜ pending | |
| `0x11d9a` | `read_joysticks` | 60 | ⬜ pending | |
| `0x11dd6` | `control_player` | 338 | ⬜ pending | |
| `0x11f28` | `player_death` | 236 | ⬜ pending | |
| `0x12014` | `update_objects` | 1512 | ⬜ pending | |
| `0x12606` | `update_eggs` | 590 | ⬜ pending | |
| `0x1285c` | `update_egg_draw` | 184 | ⬜ pending | |
| `0x12914` | `draw_egg_sprite` | 160 | ✅ verified | 4 egg states x 9 shifts x 3 x-values (poisoned), lava line at every row incl. draw_rows=0 -> 256 wrap rows, signed cmpa.l over 6 bounds, 200-case fuzz x 2 shards |
| `0x129b4` | `erase_egg_sprite` | 118 | ✅ verified | 13 shifts x 4 x-values, wrap column either side of 0x130, subq.b 0 = 256 rows, 200-case fuzz x 2 shards, poison on the wrap battery |
| `0x12a2a` | `update_egg_physics` | 640 | ⬜ pending | |
| `0x12caa` | `render_objects` | 8 | ⬜ pending | |
| `0x12cb2` | `render_objects_next` | 16 | ⬜ pending | |
| `0x12cc2` | `render_object_body` | 2232 | ⬜ pending | |
| `0x13300` | `check_platform` | 118 | ✅ verified | all 4 box edges inclusive x 36 positions, per-slot platform_present indexing, first-match-wins on overlapping boxes, flap-frame nudge, walk reset on leaving, signed coords; poison on 5 |
| `0x135f4` | `select_sprite_base` | 52 | ✅ verified | both identities +/-1 byte (full-longword cmpa.l), bit-15 facing incl. bit-31 noise, 200-case fuzz; register result (D1) compared, not memory |
| `0x13628` | `draw_spawn_sparkle` | 116 | ⬜ pending | |
| `0x1369c` | `blit_pattern_rows` | 76 | ✅ verified | all 16 plane selects, high bits of d2 ignored, word-sized masks (hi_garbage), the 12-word write set, poison, fuzz |
| `0x136e8` | `draw_object_data` | 212 | ✅ verified | shifts x row counts (0 = 256) x wrap column across x=0x130 signed x half_select; playfield_bottom re-read EVERY row; lava row count from a FRESH draw_rows read (sub.b/neg.b); poison, fuzz |
| `0x137bc` | `draw_object_mask` | 134 | ✅ verified | shifts, row counts, prev_x wrap; erase pass aimed at the record's own fields pins that the wrap column re-reads prev_rows/prev_src but NOT prev_dst/prev_shift; poison, fuzz |
| `0x13842` | `collision_check` | 1712 | ⬜ pending | |
| `0x13ef2` | `test_overlap` | 244 | ✅ verified | exg ordering by screen address, add.b y-band byte-wrap, divu.w #$a0 incl. overflow, both column-alignment branches over all 20 cell gaps, signed-byte row clamp, hit ends the sweep, 300-case fuzz x 4 shards |
| `0x13fe6` | `pixel_collision` | 178 | ✅ verified | per-row hit position, spill gated on cursor+shift, 13 wide shifts (LSR.L mod 64) x 2 orderings, subq.b 0 = 256 rows, adda.w sign-extended stride, 400-case fuzz x 4 shards; poison on 3 |
| `0x14098` | `start_death_anim` | 102 | ⬜ pending | |
| `0x140fe` | `joust_bounce` | 96 | ✅ verified | 14 gaps across both thresholds (unsigned bcc / signed bge) x 9 velocity pairs, neg.w 0x8000, flags high half not stored, already-correct velocity left untouched; poison on 2 |
| `0x14160` | `score_update` | 6 | ⬜ pending | |
| `0x14166` | `score_update_p2` | 12 | ⬜ pending | |
| `0x14172` | `score_update_p1` | 212 | ⬜ pending | |
| `0x14246` | `draw_lives` | 8 | ⬜ pending | |
| `0x1424e` | `draw_lives_p1` | 18 | ⬜ pending | |
| `0x14260` | `draw_lives_p2` | 126 | ⬜ pending | |
| `0x142de` | `draw_messages` | 126 | ⬜ pending | |
| `0x1435c` | `find_free_message` | 30 | ⬜ pending | |
| `0x1437a` | `check_highscore` | 310 | ⬜ pending | |
| `0x144b0` | `flash_hiscore_color` | 36 | ⬜ pending | |
| `0x144d4` | `hiscore_key_input` | 100 | ⬜ pending | |
| `0x14538` | `hiscore_joystick_input` | 288 | ⬜ pending | |
| `0x14658` | `draw_hiscore_cursor` | 78 | ⬜ pending | |
| `0x146a6` | `draw_hiscore_entry` | 80 | ⬜ pending | |
| `0x146f6` | `lava_troll` | 706 | ⬜ pending | |
| `0x149b8` | `troll_erase_hand` | 122 | ⬜ pending | |
| `0x14a32` | `troll_draw_hand` | 136 | ⬜ pending | |
| `0x14ada` | `update_pterodactyl` | 1470 | ⬜ pending | |
| `0x15098` | `blit_mask_wide` | 116 | ✅ verified | shift counts around 0/16/32/0x3f, non-positive counts incl. 0x8000 (BGE = N==V), sign-extended dst_off, middle cell masked twice per row; record-overlap case pins read-once; poison, fuzz |
| `0x1510c` | `blit_sprite_planes` | 202 | ✅ verified | shifts x all 8 clip combinations x row counts; read/write phase order over 7 source deltas x 5 shifts — the trailing cell's 4 words are RE-READ after the first two passes write; suppressors re-tested per row; poison, fuzz |
| `0x15226` | `ptero_avoid_platform` | 80 | ✅ verified | x band +/-1 over 9 values, row band swept 28 rows, D1 high half survives on all 3 exits (records carry a non-zero divu remainder), absent platforms, divu overflow; poison on 3 |
| `0x15276` | `ptero_spot_player` | 72 | ✅ verified | row band both signs, 26 x-gaps straddling both thresholds from both directions, sound priority incl. the drop path, word-wrap coords, other flag bits ignored; poison on 2 |
| `0x17438` | `dissolve_platforms` | 322 | ⬜ pending | |
| `0x1757a` | `raise_floor` | 64 | ⬜ pending | |
| `0x175ba` | `paint_floor_row` | 36 | ✅ verified | uniform + noise cells, poison, write set pinned to exactly the 5 plane-3 words |
| `0x175de` | `animate_ground_shrink` | 372 | ⬜ pending | |
| `0x17752` | `blit_sprite_mask` | 80 | ✅ verified | shared battery with blit_sprite: shifts, signed low-byte cell select with the high byte swept, row counts, hi_garbage on d7, full-longword dst_off, self-overdraw read-before-write, poison, sharded fuzz |
| `0x177a2` | `blit_sprite` | 154 | ✅ verified | as blit_sprite_mask plus the colour data ORed behind the mask (shifted, not rotated); same battery |
| `0x1783c` | `wave_manager` | 2660 | ⬜ pending | |
| `0x182a2` | `pos_to_screen` | 52 | ✅ verified | 5 screen bases x 14 x-values x 14 y-values (incl. the y>=205 adda.w sign flip) + 800-case fuzz, poison on 5 |
| `0x182d6` | `screen_to_pos` | 42 | ✅ verified | 5 screen bases x 18 offsets (incl. divu.w overflow) x 9 shifts + 800-case fuzz, poison on 4; the x22 scale bug pinned explicitly |

## Notes on what the verified eight turned up

- **`make_fill_pattern`** is degenerate in the shipped binary: four byte-identical `btst #0,d0 /
  or.l #$ffff0000,d1` blocks, and a `d2` that is cleared and never written. Only bit 0 of the
  colour has any effect. Reproduced exactly — see the comment in `src/fill.c` and the `cmt` in
  `../names.txt`.
- **`screen_to_pos`** carries an original bug: it scales the recovered cell index by `mulu.w #$16`
  (22) where inverting `pos_to_screen` needs 16, so it does not round-trip for any x >= 16. The
  routine is unreferenced in the whole image. Reproduced, not fixed.
- **`rng_advance`**'s two constants are *relocated* longwords: the listing's raw `#$7832` / `#$0`
  are really `0x17832` and `0x10000` at the 0x10000 load base. The compare is signed.
- **`pos_to_screen`** folds both offsets in with `adda.w` — the low word only, sign-extended — so
  the address runs backwards from y = 205. Off-screen, but reproduced.
- **The three blits** count their columns and rows with `subq.b`: only the low byte of each word
  argument is the count, and 0 means 256 passes. They also re-read `cols` from the caller's frame
  on **every** row (the row branch targets the `move.w 12(a7),d0`), while `rows` is read once — so
  a rectangle that overwrites its own argument block changes width mid-blit. `blit_from_args` in
  `src/blit.c` models that; `test_cols_is_reread_every_row` fails if it is hoisted.
- **`fill_pattern_n`** counts with `subq.w`: a count of 0 fills 65536 cells (512 KiB).
