# Reconstruction status — Joust

Human-readable C reconstruction of Joust's 75 functions, each **verified byte-for-byte against
the original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi
oracle running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 59/75.** The 75 are the functions in `../decomp.c`'s inventory; `../names.txt` is the
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
| `0x1052e` | `draw_platforms` | 148 | ✅ verified | signed present byte incl. the -1 latch, pairs 2/3 + 6/7 forced to the larger, the present POINTER indirection pinned with a permuted map, subq.b extents (0 = 256); poison on 3, 4 screen bases |
| `0x105c2` | `rng_advance` | 46 | ✅ verified | 12 edge cursors (wrap threshold, longword wrap, signed-negative) x 10 mixes with poison + hi-garbage mixes + 600-case fuzz; D0 preserved |
| `0x105f0` | `init_game` | 272 | ⬜ pending | |
| `0x10700` | `draw_string` | 622 | ✅ verified | both fonts x all 236 non-control glyphs, 16 shifts/colours/bg, all 6 control bytes, backspace cell-borrow, text drawn onto its own state block (per-plane re-read), 200-case sharded fuzz |
| `0x1096e` | `snd_tone_sweep` | 232 | ✅ verified | 10 staged mixer values pinning the read-modify-write (bits 6-7 survive or.l #$3f + bclr #0/#1), whole register file staged to noise to pin exactly WHICH 8 registers it writes, both counters' residues (0xfffe/0xffff) pinning subq.w + SIGNED bge; poison. LIMITS: the intra-pass ORDER of the 7 register writes is INVISIBLE (Giaccess is a register file, not an ordered ledger — TRAP_MODEL.md Phase 3); shipped order checked by hand at 0x10990..0x10a3a. The volume start (0xf) is unobservable and the pitch start's MAGNITUDE among non-negative even values is too — both pinned against the ORIGINAL'S instruction encodings at 0x10980/0x10988 (opcode + immediate + target). The differential does pin the pitch start's parity and sign |
| `0x10a56` | `play_sound` | 52 | ✅ verified | signed cmp.w gate over 96 index x priority pairs incl. 0x7fff/0x8000/0xffff, the SIGN-EXTENDED word table index over 12 wrapping indices (0x4000 reads entry 0, bit 13 flips direction), a staged distinct-pointer table asserted through the kit's Dosound ledger, the game's own 16 entries, 300-case sharded fuzz; poison on the negative indices — the only ones where a poisoned priority still admits the sound. Cannot use abi.stack_call_pokes: its 60-byte movem save area would land in diffed memory, so a word-arg stub keeps all stack traffic inside the guard band (no exclude band needed) |
| `0x10a8a` | `snd_poll_done` | 36 | ✅ verified | ALL 256 mixer bytes (the andi.b #$3f masking of bits 6-7 is exhaustive, not sampled), 7 priorities incl. 0x7fff/0x8000/0xffff, release is unconditional; only register 7 is consulted, proven with the other 15 staged to noise; poison on both branches |
| `0x10aae` | `title_screen` | 408 | ⬜ pending | |
| `0x10c46` | `xbios_setpalette` | 16 | ⬜ pending | |
| `0x10c56` | `cycle_palette` | 124 | ⬜ pending | |
| `0x11c24` | `poll_quit_key` | 114 | ✅ verified | no-key / ordinary-key / 251-key sharded fuzz over ASCII x scancode; R/r at stop_pc=0x10006 and Ctrl-C at stop_pc=0x11d4c, EACH PAIRED with a proof the run does not reach rts (a stop_pc run that fell through would stop at the sentinel and pass silently); quit path covers the Dosound ledger, the hiscore_dirty gate, Fopen/Fwrite(0x1a)/Fclose into a staged HIGH.SCO, conterm and both KBDVBASE vectors; a 9-call battery reads Setscreen/Ikbdws x2/Kbdvbase/Super/Setpalette's arguments back out of the oracle's stack, since those traps change no memory; poison. LIMITS: the P/p pause needs a SECOND keystroke, which the console model cannot deliver (one key per run) — its loop is verified separately entered at 0x11d64; the Fopen->Fcreate fallback is UNREACHABLE by construction (os_fcreate = os_fopen + truncate, so both succeed or both refuse) and is reproduced unverified |
| `0x11d9a` | `read_joysticks` | 60 | ⬜ blocked | blocked twice: it clears ikbd_packet then spins for a reply an IKBD INTERRUPT delivers, which the oracle never runs — so no poked packet survives the clr and no run leaves the loop (pinned by test_input.py::test_ikbd_wait_never_ends_from_the_routines_own_entry); and its whole body is two calls to control_player @0x11dd6 — now ported (its restart path checkpointed), so the IKBD blockage stands alone. A checkpoint at the loop head would prove one clr.l and nothing else |
| `0x11dd6` | `control_player` | 338 | ✅ verified | steer: 9 stick shapes x 6 flag shapes incl. one with only ONE flap bit set, target vx as a whole-word copy over 0/1/0x7fff/0x8000/0xfffc/0xffff, respawn zeroing, right-beats-left. Dead rider: the exit window over 12 x values x both facings (NOT mirrored — 0x134..0x13b hovers facing left), 0x8000/0xffff pinning the SIGNED cmpi.w; hover ladder over 16 y x 5 vy incl. negatives; the flap TOGGLE from all four states of the pair INCLUDING y exactly on its band's target — a mutation sweep found that hole, since from a set start a toggle and a clear are the same word. RESTART PATH CHECKPOINTED at 0x11e44 (the first of three unported calls): proves both guards route there and that game_over_flag := 1 is the ONLY write on this side; proves nothing past it. PAIRED with a never-returns proof over the SAME registers — which is what caught that pair being staged wrong. Its tail (0x11e50, restart_reset_players) is verified separately at its own entry, likewise paired, over all three two_player_mode arms, and is deliberately NOT called from control_player since check_highscore and init_game sit between. poison only where the poisoned bytes are not also the branch selector (MEASURED: inverting the flags word flips dead<->live) |
| `0x11f28` | `player_death` | 236 | ✅ verified | the cmpa.l/bls bound straddled by one WORD — full-width pinned, unsignedness NOT provable here (bls and ble differ only outside the image, stated in the test); all 12 enemy slots; lives 1/2/3/0x7f/0x80/0xfe x 4 flag shapes; the 0-vs-1 byte wrap; players_alive 1/2/0 — the 0 wraps to 0xff and gets a per-player banner, reproduced not guarded; p1/p2/neither wording+colour by a full cmpa.l; message slot at 0/1/5/23; FULL TABLE -> find_free_message returns 0 and the record lands over addresses 0..0xb (original bug, pinned); 240-case sharded fuzz; poison |
| `0x12014` | `update_objects` | 1512 | ⬜ pending | |
| `0x12606` | `update_eggs` | 590 | ✅ verified | all 14 slots (loop stride + bound), the lava sink at 5 row counts, the hatchable wait over 7 live counts incl. the SIGNED 0x80 and 4 timer residues, all 27 animation states the game can produce, the bounce-up frame, the hatch (6 launch x, 10 altitude bands, 8 rider types, 6 speeds), gravity/terminal speed/x wrap/y clamp incl. the add.w N==V overflow pairs, multi-slot passes, 320-case sharded fuzz. State 4 excluded on purpose — its jump-table record is null and nothing writes that state |
| `0x1285c` | `update_egg_draw` | 184 | ✅ verified | both entries (head + the 0x128c0 tail), each of the four record fields forcing the erase, the never-drawn bchg, 8 x-values across the wrap column, 4 row counts, the empty slot that still commits, the lava rewrite at every row, and the `jmp 0x12612` continuation driving two later slots |
| `0x12914` | `draw_egg_sprite` | 160 | ✅ verified | 4 egg states x 9 shifts x 3 x-values (poisoned), lava line at every row incl. draw_rows=0 -> 256 wrap rows, signed cmpa.l over 6 bounds, 200-case fuzz x 2 shards |
| `0x129b4` | `erase_egg_sprite` | 118 | ✅ verified | 13 shifts x 4 x-values, wrap column either side of 0x130, subq.b 0 = 256 rows, 200-case fuzz x 2 shards, poison on the wrap battery |
| `0x12a2a` | `update_egg_physics` | 640 | ✅ verified | BOTH EXITS. Landing box edges on all 4 sides x every platform slot x every present byte, still-rising/roll-friction/bounce/settle/stuck-spot branches (poisoned), the pixel pass incl. hit_box_a staged before the present test and a staged divu.w overflow, and the platform-edge TAIL JUMP — which discards its own return address, so it is diffed with a second sentinel poked one longword past emu.STACK_TOP and proved by a PAIRED negative (no rts without it) and positive (draw_dst in the write set). 4 edge cases x 11 roll speeds, plus the continuation into a later slot and from the last slot |
| `0x12caa` | `render_objects` | 8 | ⬜ pending | |
| `0x12cb2` | `render_objects_next` | 16 | ⬜ pending | |
| `0x12cc2` | `render_object_body` | 2232 | ⬜ pending | |
| `0x13300` | `check_platform` | 118 | ✅ verified | all 4 box edges inclusive x 36 positions, per-slot platform_present indexing, first-match-wins on overlapping boxes, flap-frame nudge, walk reset on leaving, signed coords; poison on 5 |
| `0x135f4` | `select_sprite_base` | 52 | ✅ verified | both identities +/-1 byte (full-longword cmpa.l), bit-15 facing incl. bit-31 noise, 200-case fuzz; register result (D1) compared, not memory |
| `0x13628` | `flash_spawn_pad` | 116 | ✅ verified | phase = step_timer mod 4 + the phase-1/flags-bit-2 substitution, all 16 plane selects, 11 shifts across LSR.L mod 64, all 4 spawn records, BOTH adda.w sign extensions, 200-case fuzz; poison, 4 screen bases |
| `0x1369c` | `blit_pattern_rows` | 76 | ✅ verified | all 16 plane selects, high bits of d2 ignored, word-sized masks (hi_garbage), the 12-word write set, poison, fuzz |
| `0x136e8` | `draw_object_data` | 212 | ✅ verified | shifts x row counts (0 = 256) x wrap column across x=0x130 signed x half_select; playfield_bottom re-read EVERY row; lava row count from a FRESH draw_rows read (sub.b/neg.b); poison, fuzz |
| `0x137bc` | `draw_object_mask` | 134 | ✅ verified | shifts, row counts, prev_x wrap; erase pass aimed at the record's own fields pins that the wrap column re-reads prev_rows/prev_src but NOT prev_dst/prev_shift; poison, fuzz |
| `0x13842` | `collision_check` | 1712 | ⬜ pending | |
| `0x13ef2` | `test_overlap` | 244 | ✅ verified | exg ordering by screen address, add.b y-band byte-wrap, divu.w #$a0 incl. overflow, both column-alignment branches over all 20 cell gaps, signed-byte row clamp, hit ends the sweep, 300-case fuzz x 4 shards |
| `0x13fe6` | `pixel_collision` | 178 | ✅ verified | per-row hit position, spill gated on cursor+shift, 13 wide shifts (LSR.L mod 64) x 2 orderings, subq.b 0 = 256 rows, adda.w sign-extended stride, 400-case fuzz x 4 shards; poison on 3 |
| `0x14098` | `start_death_anim` | 102 | ✅ verified | player-1 identity +/-1 byte (cmpa.l), the 0x280 rise and its SIGNED clamp incl. bit-31 screen bases, bset #13/#12 over 9 flag words, addq.b score wrap; D0 compared via a store stub; poison |
| `0x140fe` | `joust_bounce` | 96 | ✅ verified | 14 gaps across both thresholds (unsigned bcc / signed bge) x 9 velocity pairs, neg.w 0x8000, flags high half not stored, already-correct velocity left untouched; poison on 2 |
| `0x14160` | `score_update` | 6 | ✅ verified | the A0 entry of the alias family; see score_update_p1 |
| `0x14166` | `score_update_p2` | 12 | ✅ verified | the player-2 entry, A0 ignored; same battery |
| `0x14172` | `score_update_p1` | 212 | ✅ verified | the shared body: the promotion sweep's blank skip + SIGNED `< '0'` test over 10 bytes and its stop one short of the units digit (pinned by a string that RUNS the sweep to that bound, not just an all-blank one); the carry sweep at all 7 columns with the UNSIGNED `> '9'` repeat over 0x3a..0xff, the blank->'0' promotion, and the overflow into the string's own colour byte; the extra life for all 11 ten-thousands values, none from any other column, several in one call, the life-count wrap, the sound through play_sound's SIGNED gate (asserted on the Dosound ledger); 200-case sharded fuzz. Every case checked against a Python model of both sweeps, so a vacuous pass fails |
| `0x14246` | `draw_lives` | 8 | ✅ verified | dispatch only: full `cmpa.l` against player2 over 7 A0 values (+/-1 byte, enemies, 0, 0xffffffff). NOTE both bodies reload A0 from a constant, so draw_lives(enemy) draws PLAYER 1's row |
| `0x1424e` | `draw_lives_p1` | 18 | ✅ verified | counts 0..6/0x7f and the SIGNED 0x80/0xfe/0xff, 7 shifts incl. the addi.b byte wrap, 4 caller flag states, 4 screen pointers, A0 ignored, count re-read every position (row painted over its own record), 120-case sharded fuzz; poison |
| `0x14260` | `draw_lives_p2` | 126 | ✅ verified | the shared body through the p2 entry: its own record and glyph string, same battery |
| `0x142de` | `draw_messages` | 126 | ✅ verified | all 24 slots, subq.b timer (0 -> 255), expiry frees the slot AND STILL DRAWS IT in colour 0 (that draw is the erase), players_alive cut-short over 6 counts with the kind-3 exemption, game-over cmpi.l probed on 3 bytes, distinct glyph per slot, 60-case fuzz; poison |
| `0x1435c` | `find_free_message` | 30 | ✅ verified | first-free at slots 0/1/12/23, full table -> 0 (suba.l), every non-zero kind incl. 0x80, 200-case fuzz; A0 compared — it writes nothing, so an image diff proves nothing |
| `0x1437a` | `check_highscore` | 310 | ⬜ blocked | blocked twice over: calls hiscore_key_input/hiscore_joystick_input (unported), AND its main path never returns (0x448e -> 0x44ae -> 0x448e is infinite), so there is no rts to diff at — needs a stop_pc checkpoint |
| `0x144b0` | `flash_hiscore_color` | 36 | ✅ verified | counters 0/1/6/7/8/0x7fff/0x8000/0xffff, addq.w wrap pinned by a sentinel in the next word; the Setcolor pen and colour word read back out of the oracle's own trap arguments (the palette write is off-image); poison |
| `0x144d4` | `hiscore_key_input` | 100 | ✅ verified | backspace at columns 1/2/8/15 plus the 0x8000 subq OVERFLOW (bge is N==V, so it clamps) and the column-0 clamp; RETURN ignored untouched and at stop_pc=0x10006 for 3 non-zero draw_rows values, with a never-returns companion; all 26 upper-case, all 26 lower-case folded, space; 19 rejected bytes separating the UNSIGNED fold threshold from the SIGNED range tests; the last-column clamp and the 0xffff-wraps-to-0 UNSIGNED clamp; 256-key sharded fuzz; poison |
| `0x14538` | `hiscore_joystick_input` | 288 | ✅ verified | VERIFIED FROM 0x1454e — entered at the IKBD wait loop with the reply staged. The prologue (clr.l ikbd_packet, the Ikbdws interrogate, the blocking wait) is NOT verified and cannot be: the routine clears the packet before waiting, so no poked constant survives it. From the packet read on: stick owner over 6 values incl. player2|0xffff0000 (the full cmpi.l), fire gated on draw_rows and set AFTER the test, centred stick clearing the counter, the subq.b repeat counter incl. 0x80's overflow into blt, both letter wraps in both directions with the second test RE-READING the byte, left/right into the shared cursor tails, direction priority, 256-stick sharded fuzz; poison |
| `0x14658` | `draw_hiscore_cursor` | 78 | ✅ verified | all 16 columns x both parities, the 8-cell rule with noise past its end, sign-extended column offset, 4 screen bases, 200-case fuzz; poison |
| `0x146a6` | `draw_hiscore_entry` | 80 | ✅ verified | 16 columns, letters incl. 0x00 and 0xff, the string really starting at draw_dst_off, BOTH sign-extensions (raw-cursor name index, and the bit-0-cleared screen offset), 200-case fuzz; poison |
| `0x146f6` | `lava_troll` | 706 | ✅ verified | signed wave gate, subq.b+bge step timer (0 and 0x80 both reload); scan rejection by flags/signed reach row/the two-ended pit band, first-match-wins, all 14 slots; the raise BUILDS the state word; the tracking window measured BOTH ways round the 320-px screen; the UNSIGNED contact window with the grab sound as witness; climb, retract with subq.w #8+bge at 0x8000/0xfff8/0xffff; the hold block's signed escape line paying only a PLAYER (proved by the carry score_update leaves), and the respawn/in-lava drop whose clr.w troll_state is DEAD; 4 screen bases; 200-case fuzz x 4 shards |
| `0x149b8` | `troll_erase_hand` | 122 | ✅ verified | early-out needs ALL THREE of src/dst/shift, ror.l mod 32, signed-word rows (0/0x8000 draw nothing), playfield_bottom re-read EVERY row (pinned by a blit that overwrites the surface mid-run), self-overlap read-before-write, 200-case fuzz; poison |
| `0x14a32` | `troll_draw_hand` | 136 | ✅ verified | bit-0 gate on the whole longword, LSR.L mod 64, lava clip re-read per row, all four planes read before any write over 6 overlap deltas, 200-case fuzz; poison |
| `0x14ada` | `update_pterodactyl` | 1470 | ⬜ pending | |
| `0x15098` | `blit_mask_wide` | 116 | ✅ verified | shift counts around 0/16/32/0x3f, non-positive counts incl. 0x8000 (BGE = N==V), sign-extended dst_off, middle cell masked twice per row; record-overlap case pins read-once; poison, fuzz |
| `0x1510c` | `blit_sprite_planes` | 202 | ✅ verified | shifts x all 8 clip combinations x row counts; read/write phase order over 7 source deltas x 5 shifts — the trailing cell's 4 words are RE-READ after the first two passes write; suppressors re-tested per row; poison, fuzz |
| `0x15226` | `ptero_avoid_platform` | 80 | ✅ verified | x band +/-1 over 9 values, row band swept 28 rows, D1 high half survives on all 3 exits (records carry a non-zero divu remainder), absent platforms, divu overflow; poison on 3 |
| `0x15276` | `ptero_spot_player` | 72 | ✅ verified | row band both signs, 26 x-gaps straddling both thresholds from both directions, sound priority incl. the drop path, word-wrap coords, other flag bits ignored; poison on 2 |
| `0x17438` | `dissolve_platforms` | 322 | ✅ verified | 1-based kind incl. its sign-extended word truncation (base is 0x119c4, one record BELOW platform_sprites), setup sweep vs running slot, subq.b extents on both, all-zero noise -> all-ones, rng cursor across the signed wrap, 4 slots threading one cursor, all THREE re-read semantics; 120-case fuzz, 4 screen bases |
| `0x1757a` | `raise_floor` | 64 | ✅ verified | rows-left is a zero test not a sign test, subq.b timer (0 = 0xff), and the two strips at cells 0-4 / 15-19 — the second call's address is where the FIRST left a1 (+0x28) plus 0x50, not 'the two halves' |
| `0x175ba` | `paint_floor_row` | 36 | ✅ verified | uniform + noise cells, poison, write set pinned to exactly the 5 plane-3 words |
| `0x175de` | `animate_ground_shrink` | 372 | ✅ verified | signed latch gate, 3-frame timer, flame-frame wrap, sink gate as a FULL-WORD compare, sink-outranks-climb, the climb's deliberate non-refresh of the latch, ground-edge wrap, SIGNED rollover at 0x7fff/0x8000 (subq.w+bge is N==V; the left flame is NOT symmetric), 150-case fuzz, 4 screen bases |
| `0x17752` | `blit_sprite_mask` | 80 | ✅ verified | shared battery with blit_sprite: shifts, signed low-byte cell select with the high byte swept, row counts, hi_garbage on d7, full-longword dst_off, self-overdraw read-before-write, poison, sharded fuzz |
| `0x177a2` | `blit_sprite` | 154 | ✅ verified | as blit_sprite_mask plus the colour data ORed behind the mask (shifted, not rotated); same battery |
| `0x1783c` | `wave_manager` | 2660 | ⬜ blocked | blocked: 2660 bytes calling find_free_message x20 plus score_update_p1/p2 |
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
