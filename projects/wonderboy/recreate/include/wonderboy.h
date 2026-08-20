/* wonderboy.h — how SWB.PRG becomes a running image, as constants.
 *
 * Values are FILE OFFSETS into the .PRG's text segment down to WB_BODY_LEN (the exception being
 * WB_RUNTIME_BASE, the absolute address the program runs at); from the Copylock block onwards they
 * are RUNTIME addresses, and each block says which. Each one is read out of the binary and pinned
 * by a case in test/, which scrapes this header through test/layout.py rather than restating the
 * numbers — one source of truth across the language boundary (CLAUDE.md §5).
 *
 * WHY THE LOAD BASE IS 0x3f8. SWB.PRG is not position-independent: 0x214d8 bytes of text carry
 * three relocation entries, and the body addresses itself with absolute long operands nothing fixes
 * up. The entry point is a trampoline into a relocator at the end of the text which copies the body
 * from `load_base + WB_BODY_SRC_OFF` to the fixed absolute address WB_RUNTIME_BASE and jumps there.
 * At load_base 0x3f8 those two are the same address, so the loaded image IS the runtime image and
 * the copy is an identity copy — which is why an image address here equals `0x3f8 + file offset`
 * and equals the game's own absolute operands, and why ../names.txt is written at that base.
 * project.toml carries the full argument.
 *
 * It is Python's canonical source (through test/layout.py) and the reconstruction's: the depacker
 * block, and the game-state blocks after it, are consumed by src/ and by test/ alike. The rule for
 * what lands here rather than in a module header is exactly that — BOTH languages need it. A value
 * only the C needs stays in its module's own header (include/rad.h, effects.h, input.h), none of
 * which include this one; rad.h's comment states that split for the container constants.
 */
#ifndef WONDERBOY_H
#define WONDERBOY_H

/* ---- the .PRG header, as the loader reads it ---------------------------------------------- */
#define WB_TEXT_LEN          0x214d8u  /* text segment; data and bss are both zero-length */
#define WB_RELOC_COUNT       3u        /* relocation entries for the whole 136 KiB program */

/* ---- the entry trampoline (file offset 0) ------------------------------------------------- */
#define WB_ENTRY_OFF         0x0u      /* `move.w d0,d0` then `jmp WB_RELOCATOR_OFF.l` */
#define WB_ENTRY_JMP_OPERAND_OFF 0x4u  /* the jmp's target longword — one of the three fixups */

/* ---- the relocator (file offset 0x213e0), which ends the text ----------------------------- */
#define WB_RELOCATOR_OFF     0x213e0u  /* `move.l #WB_SUPER_STACK_OPERAND,-(a7); move.w #$20,-(a7)`.
                                        * names.txt calls the routine startup_relocate_and_run */
#define WB_SUPER_TRAP_OFF    0x213eau  /* the one and only `trap #1` in the image: GEMDOS Super */
#define WB_SUPER_STACK_OPERAND 0x214d8u /* Super's argument AS ENCODED — a fixup, so the value the
                                        * trap actually sees is this PLUS the load base. It is the
                                        * first byte past the program (== WB_TEXT_LEN): the game
                                        * enters supervisor mode with a fresh SSP there */
#define WB_RELOCATOR_COPY_OFF 0x213ecu /* past the Super: `move.w #$2700,sr` and the copy loop.
                                        * The kit's trap model refuses this game's Super argument
                                        * (TRAP_MODEL.md Phase 2 accepts only 0, 1 and its own
                                        * token), so an oracle run enters HERE — which costs
                                        * nothing, since Musashi is already in supervisor mode */

/* ---- what the relocator does -------------------------------------------------------------- */
#define WB_BODY_SRC_OFF      0x8u      /* source: file offset 8, i.e. past the entry trampoline */
#define WB_RUNTIME_BASE      0x400u    /* destination: an ABSOLUTE address, not relocated */
#define WB_BODY_LONGS        0x84f6u   /* the copy loop's counter, in longwords */
#define WB_BODY_LEN          0x213d8u  /* == WB_BODY_LONGS * 4 (pinned); the runtime body spans
                                        * [WB_RUNTIME_BASE, WB_RUNTIME_BASE + WB_BODY_LEN) */

/* ---- the Copylock, and the two ways a harness run gets past it --------------------------------
 *
 * EVERY ADDRESS BELOW IS A RUNTIME ADDRESS, not a file offset — the spelling ../names.txt and
 * ../notes/architecture.md §2.5 use, and (because load_base is 0x3f8 == WB_RUNTIME_BASE minus
 * WB_BODY_SRC_OFF) the address the game's own absolute operands carry. The `_LEN` values are not
 * addresses at all; they are byte counts.
 *
 * The protection is a Rob Northen-style trace-decrypting blob whose body only ever exists as
 * plaintext one longword at a time. `load_resource_by_index` calls it on the FIRST resource load
 * of the boot and disarms it afterwards, so a harness must get past it before anything on the boot
 * path can run. test/copylock.py is the stub; test/test_copylock.py pins every address here
 * against the loaded image or against ../names.txt, so a wrong constant fails loudly rather than
 * silently stubbing nothing.
 */
#define WB_COPYLOCK_ARM_FLAG      0xe7ccu  /* copylock_arm_flag: nonzero -> the guard calls the blob */
#define WB_COPYLOCK_ARM_FLAG_LEN  2u       /* it is a WORD (`tst.w` / `clr.w` / `move.w #$ffff`) */
#define WB_COPYLOCK_ARM_TITLESCR  0xe51eu  /* `move.w #$ffff,copylock_arm_flag` before TITLESCR.RAD */
#define WB_COPYLOCK_ARM_SPRITES   0xe6dcu  /* ...and the same instruction before SPRITES.CRU */
#define WB_COPYLOCK_ARM_INSN_LEN  8u       /* both arming sites are `move.w #imm,abs.l` = 8 bytes */
#define WB_COPYLOCK_GUARD         0xe7b2u  /* `tst.w copylock_arm_flag` inside load_resource_by_index */
#define WB_COPYLOCK_CALL          0xe7bcu  /* `jsr copylock_entry.l` — the image's ONLY reference */
#define WB_COPYLOCK_SKIPPED       0xe7c8u  /* where both guard arms rejoin: `movea.l (a7)+,a0; rts` */

/* Not part of the protection, but needed to reach it: the one call load_resource_by_index makes
 * BEFORE the guard, and a hard reject for the oracle (it reaches psg_set_drive_select's read of
 * $ff8800 — PORTABILITY.md §3, T4). A case that needs an arming site and the guard in ONE run pokes
 * an `rts` here to elide the disk access. */
#define WB_DISK_LOAD_FILE         0x5e7cu

#define WB_COPYLOCK_ENTRY         0xeccau  /* copylock_entry; the entry stub pokes an `rts` here */
#define WB_COPYLOCK_REG_SAVE      0xecd4u  /* `movem.l d0-a7,(a6)` lands here — the blob's FIRST write */
#define WB_COPYLOCK_REG_SAVE_LEN  0x60u    /* 64 B of d0-a7 then 32 B of vectors $8..$27 */
#define WB_COPYLOCK_REGS_SAVED    0xed50u  /* the PC one instruction past that `movem` */
#define WB_COPYLOCK_DECRYPT_CURSOR 0xed3eu /* `move.l a0,(a0)` primes the trace decryptor's cursor */
#define WB_COPYLOCK_VECTORS_INSTALLED 0xee1au /* the PC past the decryptor's `move.l a0,$24/$20` pair */
#define WB_COPYLOCK_CODE_END      0xf576u  /* end (exclusive): `jmp $6bb8.w` at $f572 is the last
                                            * instruction, and $f576 starts the four plaintext
                                            * scanline-order tables. The witness stops HERE and not
                                            * at the blob's $f89e end because plaintext code writes
                                            * copylock_flag_a/b ($f89a/$f89c) at $fb8a/$fb90 */

/* The three exception vectors the blob installs (../notes/architecture.md §2.5). A write to any of
 * them is the second half of the witness: only the Copylock touches them. */
#define WB_COPYLOCK_VEC_ILLEGAL   0x10u
#define WB_COPYLOCK_VEC_PRIVILEGE 0x20u
#define WB_COPYLOCK_VEC_TRACE     0x24u
#define WB_EXCEPTION_VECTOR_LEN   4u

/* ---- the .RAD/.CRU resource depacker (RUNTIME addresses; ../notes/rad_depacker.asm) -----------
 *
 * Reconstructed in src/rad.c. The three values below are what BOTH languages need: C to build the
 * routine, test/test_rad_depack.py to enter it under the oracle and to read its verdict. */
#define WB_RAD_DEPACK        0x5d62u  /* rad_depack(a0 = packed file, a1 = destination) */
#define WB_RAD_SAVED_SP      0x5e3au  /* `move.l a7,$5e3a.l`: where it parks the entry stack
                                       * pointer, to restore on the success path only */
#define WB_RAD_SAVED_SP_LEN  4u
#define WB_RAD_BAD_CHECKSUM  0xffffffffu /* the ONE defined status: `moveq #$ff,d0` SIGN-EXTENDS, so
                                          * the failure value is the whole longword, not $ff. On
                                          * success d0 is only the spent bit buffer */

/* ---- the joystick edge pipeline (RUNTIME addresses; src/input.c) ------------------------------
 *
 * Three bytes, one per stage. The IKBD interrupt handler (`ikbd_joy1_byte_handler`, $858) drops the
 * raw joystick-1 report into WB_JOY1_STATE; once a frame `joy1_latch_edge` ($88c) shifts it one
 * stage down, and `joy1_newly_pressed` ($682) diffs the last two stages into a rising-edge mask.
 * The two live stages sit on the NUL terminators of two filler strings — see ../names.txt.
 */
/* The 68000's operand widths, where a reconstruction needs one as a NUMBER — a table stride, a
 * pointer step. Two modules had their own `LONGWORD_BYTES` (src/stage.c's resource walk and, since
 * batch 40, src/player.c's record copy), which is one copy more than this workspace allows. */
#define WB_LONGWORD_BYTES    4u
#define WB_WORD_BYTES        2u       /* ...and the WORD, which batch 40 phase C needed for a
                                       * different reason: `lea <cursor>.l,a1 / move.w (a1)+,d0`
                                       * puts a table's base exactly one word above its own cursor,
                                       * four times over in player_stage_transition */

#define WB_JOY1_STATE        0x877u   /* what the IKBD handler last stored; bit 7 = fire */
#define WB_JOY1_PREV         0x8b3u   /* the byte as of the PREVIOUS frame */
#define WB_JOY1_CURRENT      0x8cfu   /* ...and as of this one */

/* ---- game state the effect handlers write (RUNTIME addresses; src/effects.c) ------------------
 *
 * The 23 handlers of `effect_handler_table` ($1023a) and the six `set_state_*` stubs above it are
 * one-instruction-deep writers of the globals below. What the effects MEAN is not established —
 * ../names.txt says so and names them for their mechanism — so the names here describe the SHAPE
 * each global is written and read with, and carry the address for the part that is still unknown.
 *
 * THE HUD SLOT ARRAY. $bbbe..$bbc9 is six 2-byte slots, each `{value, request}`. The pass at
 * $b8f0 (`hud_refresh_dirty_slots`, src/hud.c) walks the six request bytes every frame: a nonzero
 * one is cleared, a per-slot flag in the $dbb6.. block is raised, the slot's cell is cleared
 * ($bb8a) and an icon is OR-blitted over it ($bba0). So the setters' single `move.w #$Nff,slot.l`
 * means "value := N, and redraw me". The value's own meaning differs slot by slot and is NOT
 * identified: $bbbe and $bbc0 are counted DOWN one per use by the damage paths at $69fe/$6b46
 * (which, on reaching zero, rearm the slot as $00ff and post a message), while $bbc8 is tested
 * against 1..6 as an icon variant. $bbc4 is written by ONE handler in src/effects.c
 * (`pickup_effect_grant_bbc4`), which posts no message and so names nothing; the slot pass draws it
 * like the other five, which is why it has a constant. This block said $bbc4 was untouched by that
 * file until batch 38 reconstructed the handler that touches it.
 *
 * TWO OF THE SIX ARE IDENTIFIED AS OF BATCH 38, by the method batch 17 used for $bbbe and $bbc0 —
 * the message a slot's own writer posts. See each constant. The names here are NOT changed with the
 * identification: renaming them touches src/effects.c, test_effects.py and every other reader, so
 * ../STATUS.md queues it and the evidence sits on the symbols rather than only in a batch section.
 */
#define WB_HUD_SLOT_BBBE     0xbbbeu  /* counted down at $69fe: the damage path spends it */
#define WB_HUD_SLOT_BBC0     0xbbc0u  /* counted down at $6b46, likewise */
#define WB_HUD_SLOT_BBC2     0xbbc2u  /* the one slot set to $80 rather than a small count — and the
                                       * WING BOOTS: `pickup_effect_grant_wing_boots` writes $feff
                                       * here and posts WB_TEXT_MESSAGE_WING_BOOTS in the same
                                       * routine. RENAME QUEUED (../STATUS.md) */
#define WB_HUD_SLOT_BBC4     0xbbc4u  /* ONE writer among the ported handlers,
                                       * `pickup_effect_grant_bbc4` — which posts no message, so
                                       * this is the one slot of the six nothing names */
#define WB_HUD_SLOT_BBC6     0xbbc6u  /* the REVIVAL MEDICINE: `pickup_effect_grant_revival` writes
                                       * $01ff here and posts WB_TEXT_MESSAGE_REVIVAL in the same
                                       * routine. RENAME QUEUED (../STATUS.md) */
#define WB_HUD_SLOT_BBC8     0xbbc8u  /* read as a 1..6 icon variant at $b8f0, not as a count */
#define WB_HUD_SLOTS         6u       /* how many the pass at $b8f0 walks */
#define WB_HUD_SLOT_REQUEST  1u       /* byte +1 of a slot: "redraw me", tested then cleared */
#define WB_HUD_SLOT_REARM    0x00ffu  /* `move.w #$ff,slot.l` — the whole WORD the two damage paths
                                       * and (batch 40) the player's own two spenders write on the
                                       * frame a slot's last charge is spent: the
                                       * value back to zero and the request byte below it raised.
                                       * The setters in src/effects.c write the same word with a
                                       * value above it, so this word's LOW BYTE is that file's
                                       * WB_HUD_SLOT_CHANGED under another name. Neither can derive
                                       * from the other (test/layout.py scrapes plain literals only,
                                       * so a computed #define would vanish from the Python side);
                                       * test_effects.py's
                                       * `test_the_two_headers_spell_one_slot_byte` is the pin that
                                       * stands in for the derivation */

/* The meter drawn in four-unit cells by `FUN_0000b61e` ($b61e): `value/4` filled cells then
 * `max/4 - value/4` empty ones, so both are consumed as counts and not as flags. `max` is set to
 * $18..$28 from thresholds on $bd70 ($b74a); `value` is spent by the damage path, ticked by $e032,
 * and — by the three handlers ported here — raised by 4 or 2 (clamped) or restored to `max`. */
#define WB_HUD_METER_VALUE   0xb6fau
#define WB_HUD_METER_MAX     0xb6f8u

/* Three state words the handlers set to a small ordinal (1..4, 1..5, 1..3 respectively), and one
 * more the three $bd68 handlers stamp with 2 on the way. All four are cleared together by the
 * new-game reset at $fe4a. TWO of them now have a reader in the recovered code, and both turn the
 * ordinal into the same shape — `n - 2*value` stamped into a record byte: $bd66 at $69fe
 * (`12 - 2*value` into WB_ACTOR_FIELD_31) and $bd68 at $6796 (WB_ACTOR_STUN_STEPS_BASE minus twice
 * it, into WB_ACTOR_FIELD_29). What the ordinals SELECT is still open — only what they cost is
 * known.
 *
 * CORRECTION (batch 40): $bd6a is NOT unread. It has THREE readers and all of them are the player's,
 * which is why they were invisible while that tier was unported — $e12 and $109a add
 * WB_PLAYER_JUMP_STRENGTH_BIAS to its low byte for the jump's height, and $fde/$1048 add
 * 4 to the WHOLE WORD for the walk's top speed (a word add where the jump's is
 * a byte one). So it is the word that says how high the player jumps and how fast he runs, and the
 * three effect handlers that stamp it are setting those.
 *
 * CORRECTION (batch 40 phase C): "$21e4 is still unread" is RETRACTED TOO, by the same tier and for
 * the same reason. It has FIVE readers ($1f6e, $2018, $205e, $2072, $20d4) and every one of them is
 * inside `player_stage_transition` — it picks which of two transition frame tables plays, which of
 * the three WB_PLAYER_POSTURE_TABLE_* records the player's sprite comes out of, which of two hurt
 * sprite pairs a hurt airborne player shows, and whether the swing runs at all.
 *
 * AND THE SHIPPED BYTES SAY WHAT IT MEANS. The three posture records hold three CONSECUTIVE sprite
 * families — $104.. , $10e.. and $11e.. , each with its own idle pair, jump pair, fall pair and
 * four-frame walk cycle — so the word is WHICH OF THREE PLAYER APPEARANCES IS DRAWN.
 *
 * SIX WRITERS, and the sixth is the one an encoding-blind census misses — which is the same class
 * of miss that made this whole plate wrong for three batches, so it is enumerated rather than
 * summarised. `move.w #$1,$21e4.l` at $c06 is the ONLY absolute-LONG site of the eleven, and it is
 * load-bearing: it sits between `jsr $fe8c.l` (the life restart) and `lea 4(a7),a7 / jmp $e5ba.l`,
 * so `player_pending_event_gate` FORCES THE PLAYER'S FORM BACK TO 1 ON A STACK-UNWINDING EXIT. The
 * other five are `move.w #$1,$21e4.w` at $101c6 (`scene_exit_action_select_a30_table`),
 * `move.w #$2,$21e4.w` at $10350/$10360/$10370 (src/effects.c's three $bd68 handlers), and the
 * `clr.w $21e4.w` at $fe56 — the new-game reset, which is what puts a fresh game in form 0.
 * test/test_player.py rebuilds the whole census from the image and asserts it, near-misses
 * included. */
#define WB_EFFECT_STATE_BD66 0xbd66u
#define WB_EFFECT_STATE_BD68 0xbd68u
#define WB_EFFECT_STATE_BD6A 0xbd6au
#define WB_EFFECT_STATE_21E4 0x21e4u

/* $6f9c has no reader and no other writer among the 252 recovered functions — the
 * `set_state_6f9c_ffff` stub stores the game's usual all-ones "true" there. It is read outside them:
 * $6f84 tests it, clears it and stamps $36 into an object field, i.e. consumes it as a ONE-SHOT
 * flag (see ../names.txt). What that $36 selects is unknown, so the name stays at the mechanism. */
#define WB_STATE_WORD_6F9C   0x6f9cu

/* Every global in the two blocks above is written a WORD at a time (`move.w`), including the HUD
 * slots — whose two bytes one `move.w` covers. */
#define WB_STATE_WORD_LEN    2u

/* The record list: a LONGWORD write pointer, advanced BEFORE the store, so the list grows upward
 * and the pointer addresses the newest record. The reset at $fe4a points it at $b444 (whose own
 * word it sets to $ffff), i.e. at the base of the 0x102 bytes that run up to the pointer itself. */
#define WB_EFFECT_RECORD_LIST      0xb444u
#define WB_EFFECT_RECORD_WRITE_PTR 0xb546u
#define WB_EFFECT_RECORD_PTR_LEN   4u
#define WB_EFFECT_RECORD_LEN       2u   /* one record is one word; its two byte fields are unknown */

/* ---- the status panel and its leaves (RUNTIME addresses; src/hud.c) ---------------------------
 *
 * `FUN_0000b346` ($b346) is the game loop's once-a-frame panel pass: nine `bsr`s that redraw the
 * record list, the four-digit counter, the score, the high score, the meter, the six HUD slots and
 * the panel's animation frame, then select a table and tick a counter. The eleven reconstructed
 * leaves below sit under it (and under the score/counter accumulators its display consumes). Every
 * name is at the MECHANISM, the same rule the effect handlers above follow.
 *
 * All the drawing goes through `screen_back`, a LONGWORD in memory rather than an operand — so a
 * blit's destination comes out of the image, and src/hud.c inherits the off-image divergence class
 * src/rad.c's comment registers. Every case in test/test_hud.py seeds it inside the image.
 */
#define WB_SCREEN_BACK       0x750u   /* longword: the buffer being drawn into (../names.txt) */
#define WB_SCREEN_FRONT      0x74cu   /* longword: the buffer being displayed — the region restore
                                       * at $d93a is the one routine here that reads it */
#define WB_SCREEN_LINE       160u     /* ST low-res scanline: 320 px over 4 planes, 8 B per 16 px */
#define WB_SCREEN_SCANLINES  200u     /* ST low-res height, so a buffer HOLDS 32,000 bytes — 768
                                       * fewer than the $8000 screen_back and screen_front are
                                       * spaced by, which is what clear_both_screens' $70000..$7fd00
                                       * measures out (../names.txt) */
#define WB_PLANE_STRIDE      2u       /* so one 8-px column's four plane bytes are +0/+2/+4/+6 */
#define WB_PLANES            4u

/* $b372: `$21e8c := ($a32 ? $21e6a : $21c60)`, then `addq.w #1,$b39a`. $a32 is a word flag (three
 * writers in the image, thirteen `tst.w` readers); $21e8c is a longword pointer seven other sites
 * load into an address register; $b39a is the tick `rng_next` mixes into its entropy. */
#define WB_STATE_FLAG_A32    0xa32u
#define WB_TABLE_PTR_21E8C   0x21e8cu
#define WB_TABLE_PTR_LEN     4u
#define WB_TABLE_A32_CLEAR   0x21c60u /* the table published while the flag is zero */
#define WB_TABLE_A32_SET     0x21e6au /* ...and while it is not */
#define WB_FRAME_TICK_B39A   0xb39au

/* $b410: the FIRST BYTE of a record selects a 0x400-byte bitmap, which lands at a fixed spot in
 * `screen_back`. 32 bytes per row and 32 rows is 64 x 32 pixels in the ST's four planes. */
#define WB_RECORD_BITMAP_TABLE  0x1079cu
#define WB_RECORD_BITMAP_LEN    0x400u
#define WB_RECORD_BITMAP_ORIGIN 0x2800u  /* byte offset into screen_back: row 64, column 0 */
#define WB_RECORD_BITMAP_BYTES  32u
#define WB_RECORD_BITMAP_ROWS   32u

/* $b562/$b582/$b5a2/$b5c6: packed-BCD accumulators. The addend is staged at $bd78 (a scratch NO
 * other instruction in the image reads or writes) and folded in from the lowest byte up. The
 * counter is drawn as four digits by $b54c, the score as eight by $b74a — which also thresholds it
 * to set hud_meter_max — and $b7c6 draws max(score, high score). */
#define WB_BCD_COUNTER       0xbd6eu
#define WB_BCD_COUNTER_LEN   2u
#define WB_BCD_SCORE         0xbd70u
#define WB_BCD_SCORE_LEN     4u
#define WB_BCD_HISCORE       0xbd74u  /* the field immediately above the score, and NOT written by
                                       * the four-byte accumulators: the case that proves it */
#define WB_BCD_ADDEND        0xbd78u

/* $b6c2: one meter cell — 8 rows of one 8-px column, its screen offset taken from a word table the
 * caller walks with `(a1)+`. WB_METER_CELL_ENTRIES is the one constant in this header the C does not
 * consume: the routine is handed a cursor and never bounds it, so the table's LENGTH is a fact only
 * a case that walks it needs — and it is a layout fact, which is what this header is for. */
#define WB_METER_CELL_TABLE  0xb6e4u
#define WB_METER_CELL_ENTRIES 10u     /* the ten cell positions $b61e draws, ending at $b6f8 */
#define WB_METER_CELL_OFFSET_LEN 2u
#define WB_METER_CELL_ROWS   8u

/* $b61e: the meter's own pass. It draws `value / 4` full cells, then ONE partial cell chosen by the
 * remainder, then `max / 4 - (cells drawn)` empty ones, walking meter_cell_offsets with the cursor
 * hud_blit_meter_cell returns. The five bitmaps are consecutive 32-byte blocks, named individually
 * because the original `lea`s each address rather than indexing a base. */
#define WB_METER_CELL_UNITS      4u        /* `divu.w #4,d6` — one cell is four meter units */
#define WB_METER_CELL_FULL       0x146fcu
#define WB_METER_CELL_PARTIAL_3  0x1471cu  /* remainder 3 */
#define WB_METER_CELL_PARTIAL_2  0x1473cu  /* remainder 2 */
#define WB_METER_CELL_PARTIAL_1  0x1475cu  /* remainder 1 */
#define WB_METER_CELL_EMPTY      0x1477cu

/* The byte $b61e raises before it draws. It is one entry of the flag array at $dbb0 that $d93a —
 * panel_refresh_frame's FIRST call — walks with `tst.b (a6)+ / clr.b -1(a6)`, restoring one screen
 * region from screen_front to screen_back per raised flag. `st` writes $ff. */
#define WB_PANEL_RESTORE_FLAG_DBB3 0xdbb3u
#define WB_PANEL_RESTORE_FLAG_SET  0xffu

/* $bb8a/$bba0: one HUD-slot cell, 16 bytes over 14 rows (32 x 14 px). $b8f0 calls the copying form
 * with a blank source to clear a cell and the OR-ing form to lay an icon over it. */
#define WB_HUD_CELL_BYTES    16u
#define WB_HUD_CELL_ROWS     14u

/* $bcd6: the panel's animation frame, 24 bytes over 32 rows (48 x 32 px), selected by a word index
 * $bbca cycles 0..12 off its own timers. */
#define WB_PANEL_FRAME_INDEX  0xbd2cu
#define WB_PANEL_FRAME_TABLE  0x153dcu
#define WB_PANEL_FRAME_LEN    0x300u
#define WB_PANEL_FRAME_ORIGIN 0x5b40u  /* byte offset into screen_back: row 146, column 0 */
#define WB_PANEL_FRAME_BYTES  24u
#define WB_PANEL_FRAME_ROWS   32u

/* $bbca: the timers that cycle that index, and the two immediates the animation spends elsewhere.
 * The five words themselves are named with the reset that clears them, further down. The pass runs
 * in three arms — rewind the delay, measure the index off it, or step the index on a dwell — and
 * every number below is one arm's own immediate. */
#define WB_PANEL_FRAME_REWIND_STEP  0x14u  /* `addi.w #$14,$bd28` while WB_PANEL_FRAME_REWIND is up */
#define WB_PANEL_FRAME_INDEX_SHIFT  7u     /* `asr.w #7,d0` — ($500 - delay) >> 7 gives 0..$a */
#define WB_PANEL_FRAME_INDEX_START  0xau   /* `move.w #$a,$bd2c` where the stepping arm takes over */
#define WB_PANEL_FRAME_INDEX_LAST   0xcu   /* `cmpi.w #$c,$bd2c` — the index the cycle ends on */
#define WB_PANEL_FRAME_DWELL_RELOAD 4u     /* `move.w #$4,$bd2e` — frames held per index step */
#define WB_PANEL_FRAME_PHASE_ACTIVE 0xffffu /* `move.w #$ffff,$bd2a` — the stepping arm is running */
#define WB_PANEL_FRAME_METER_COST   4u     /* `subq.w #4,d0` off WB_HUD_METER_VALUE when it starts */
#define WB_PANEL_FRAME_SFX          0xfu   /* `move.w #$f,d0` — the SFX id the step arm triggers */

/* ---- $b850 and the four digit fields it draws (RUNTIME addresses; src/hud.c) ------------------
 *
 * `$b850` plots ONE packed-BCD digit: it rotates the digit register left by a nibble and draws the
 * nibble that lands on top, 8 rows of one 8-px column (four plane bytes at +0/+2/+4/+6, one 160-byte
 * scanline apart). Sixteen call sites in the image, every one inside a routine that walks a field of
 * digits left to right: four in $b5ea (bcd_counter_bd6e), eight in $b7ea (bcd_score_bd70 and
 * bcd_hiscore_bd74), two in $bd4a (stage_number) and two in $b3da, which is NOT reconstructed.
 */
#define WB_DIGIT_SIGNIFICANT_SEEN 0xb84eu  /* word: the leading-zero latch (see src/hud.c) */
#define WB_DIGIT_SIGNIFICANT_SET  0xffffu  /* the `move.w #$ffff` that forces a digit to print */
#define WB_DIGIT_GLYPHS           0x1447cu /* the glyphs for every font_select EXCEPT 1 */
#define WB_DIGIT_GLYPHS_ALT       0x145bcu /* ...and the ones for font_select == 1. Its SECOND user
                                            * is the `lea $145bc.l,a1` at $1d0a inside
                                            * shop_render_price_digits, RECOVERED in batch 41 phase
                                            * B — so the two users are the panel's digit plotter and
                                            * the shop's price plates, and this comment's earlier
                                            * "unrecovered" is retracted */
#define WB_DIGIT_FONT_ALT         1u       /* the `cmpi.w #1,d0` that chooses between them */
#define WB_DIGIT_FONT_DEFAULT     0u       /* the `moveq #0,d0` $b5ea and $b7ea force */
#define WB_DIGIT_GLYPH_LEN        32u      /* `asl.w #5,d6`: WB_DIGIT_ROWS rows x WB_PLANES planes */
#define WB_DIGIT_ROWS             8u
#define WB_DIGIT_NIBBLE_MASK      0xfu     /* `andi.l #$f,d6` */
#define WB_DIGIT_BLANK_PLANE      1u       /* a suppressed zero fills THIS plane... */
#define WB_DIGIT_BLANK_FILL       0xffu    /* ...with `st`, but only under the default glyphs */

/* The two `suba.l` immediates every caller steps the cursor with. $b850 leaves it eight scanlines
 * below where it started (WB_DIGIT_ROWS * WB_SCREEN_LINE = 1280), so each of these is that minus a
 * net column step: +1 byte to the right half of the same 16-px group, or +7 to the next group's
 * left half. test/test_hud.py derives the two net steps rather than restating them. */
#define WB_DIGIT_REWIND_RIGHT_HALF 0x4ffu
#define WB_DIGIT_REWIND_NEXT_GROUP 0x4f9u

/* Where each field lands in screen_back. The counter's and the score's are `adda.w #imm,a0`; the
 * high score's is a `lea 2633(a0),a0` — a different instruction for the same kind of offset. */
#define WB_COUNTER_ORIGIN 0x1e08u  /* $b54c: four digits of bcd_counter_bd6e */
#define WB_SCORE_ORIGIN   0xa21u   /* $b74a: eight digits of bcd_score_bd70 */
#define WB_HISCORE_ORIGIN 0xa49u   /* $b7c6: eight digits of max(score, hiscore) */
#define WB_STAGE_ORIGIN   0x7311u  /* $bd32: two digits of stage_number's LOW byte */

#define WB_STAGE_NUMBER   0xbd88u  /* the word $bd32 draws; set from level_seq_table[3] at $e61a */

/* The five (score threshold, hud_meter_max) steps $b74a applies after drawing the score, LOWEST
 * first — the original tests them highest first and returns on the first match, which is the same
 * table read the other way. The compare is `cmp.l #imm,d7 / blt`, i.e. SIGNED, so a score at or
 * above $80000000 matches none of them and leaves the maximum alone (test/test_hud.py pins that). */
#define WB_METER_SIZE_STEPS   5u
#define WB_METER_SIZE_SCORE_1 0x30000u
#define WB_METER_SIZE_MAX_1   0x18u
#define WB_METER_SIZE_SCORE_2 0x100000u
#define WB_METER_SIZE_MAX_2   0x1cu
#define WB_METER_SIZE_SCORE_3 0x200000u
#define WB_METER_SIZE_MAX_3   0x20u
#define WB_METER_SIZE_SCORE_4 0x300000u
#define WB_METER_SIZE_MAX_4   0x24u
#define WB_METER_SIZE_SCORE_5 0x400000u
#define WB_METER_SIZE_MAX_5   0x28u

/* ---- $b39c / $b3da: the newest record's display (RUNTIME addresses; src/hud.c) ----------------
 *
 * panel_refresh_frame's second call. `tst.w effect_record_list / bpl` is the empty test — the reset
 * at $fe4a leaves $ffff in that first word — and everything after it works on the record
 * `effect_record_write_ptr` points at, i.e. the newest one. Two things can come of it: the bitmap
 * $b410 draws for the record's HIGH byte, gated on a fresh-record flag, and the two digits $b3da
 * draws for its LOW byte, gated on that byte not being the $ff sentinel.
 */
#define WB_RECORD_FRESH_FLAG    0xb54au  /* `tst.b`: a byte one `st` in the image raises ($1262) */
#define WB_PANEL_RESTORE_FLAG_DBB5 0xdbb5u /* the $2800 region's flag, which the bitmap arm raises */
#define WB_RECORD_LOW_BYTE      1u       /* offset of the byte the digits and the sentinel read */
#define WB_RECORD_NO_DIGITS     0xffu    /* `cmpi.b #$ff,1(a0)`: this record draws no digits */
#define WB_RECORD_DIGITS_ORIGIN 0x3490u  /* row 84, byte 16 — INSIDE the record bitmap's own
                                          * rectangle, so the digits are stamped over it */
#define WB_RECORD_DIGITS        2u       /* `bsr $b850` twice, with one step between them. Like
                                          * WB_METER_CELL_ENTRIES it is a layout fact only a CASE
                                          * consumes — the C writes the two plots out */

/* ---- $b8f0: the six HUD slots (RUNTIME addresses; src/hud.c) ----------------------------------
 *
 * One shape per slot: clear the request byte, raise the slot's restore flag, COPY a blank cell over
 * the slot's 32 x 14 px and then OR an icon on top of it. The six cells sit in two columns of three
 * rows (byte offsets 0 and 16 of screen rows 97, 112 and 127), which is why the two blanks and the
 * two zero-value icons come in a LEFT and a RIGHT form. Every address below is `lea`d individually
 * by the original — the fourteen cells are consecutive 224-byte blocks, but nothing indexes them.
 */
#define WB_HUD_SLOT_ORIGIN_BBBE 0x3ca0u  /* row 97, column 0 */
#define WB_HUD_SLOT_ORIGIN_BBC0 0x4600u  /* row 112, column 0 */
#define WB_HUD_SLOT_ORIGIN_BBC2 0x4f60u  /* row 127, column 0 */
#define WB_HUD_SLOT_ORIGIN_BBC4 0x3cb0u  /* row 97, column 32 px */
#define WB_HUD_SLOT_ORIGIN_BBC6 0x4610u  /* row 112, column 32 px */
#define WB_HUD_SLOT_ORIGIN_BBC8 0x4f70u  /* row 127, column 32 px */

#define WB_HUD_CELL_BLANK_LEFT  0x1479cu /* the COPY's source for the three left-column slots... */
#define WB_HUD_CELL_ZERO_LEFT   0x1487cu /* ...and the icon their `value == 0` arm ORs over it */
#define WB_HUD_CELL_ICON_BBBE   0x1495cu /* the `value != 0` icon, one per slot */
#define WB_HUD_CELL_ICON_BBC0   0x14a3cu
#define WB_HUD_CELL_ICON_BBC2   0x14b1cu
#define WB_HUD_CELL_BLANK_RIGHT 0x14bfcu /* the same pair for the three right-column slots */
#define WB_HUD_CELL_ZERO_RIGHT  0x14cdcu
#define WB_HUD_CELL_ICON_BBC4   0x14dbcu
#define WB_HUD_CELL_ICON_BBC6   0x14e9cu

/* The sixth slot's value is an icon VARIANT matched by a `cmpi.b #1..#6` chain, not a two-way test.
 * Arms 5 and 6 both `lea $152fc` — one icon under two values — so there are six arms and five
 * addresses; a value outside 0..6 matches nothing and leaves the blanked cell alone. */
#define WB_HUD_SLOT_BBC8_VARIANTS 6u
#define WB_HUD_CELL_BBC8_1      0x14f7cu
#define WB_HUD_CELL_BBC8_2      0x1505cu
#define WB_HUD_CELL_BBC8_3      0x1513cu
#define WB_HUD_CELL_BBC8_4      0x1521cu
#define WB_HUD_CELL_BBC8_5      0x152fcu /* ...and the #6 arm's, which is the same address */

/* One restore flag per slot, consecutive in the $dbb0 array $d93a walks (see the block below). */
#define WB_PANEL_RESTORE_FLAG_DBB6 0xdbb6u
#define WB_PANEL_RESTORE_FLAG_DBB7 0xdbb7u
#define WB_PANEL_RESTORE_FLAG_DBB8 0xdbb8u
#define WB_PANEL_RESTORE_FLAG_DBB9 0xdbb9u
#define WB_PANEL_RESTORE_FLAG_DBBA 0xdbbau
#define WB_PANEL_RESTORE_FLAG_DBBB 0xdbbbu

/* ---- $d93a: the region restore (RUNTIME addresses; src/hud.c) ---------------------------------
 *
 * panel_refresh_frame's FIRST call, and the other half of every `st $dbbN` above: fifteen flag
 * bytes walked with `tst.b (a6)+ / clr.b -1(a6)`, each one naming a screen offset and (for eleven
 * of them) a blit that copies that region from screen_front to screen_back. So a routine that drew
 * into the back buffer last frame raises its flag, and this pass puts the FRONT buffer's pixels
 * back before the frame's drawing starts.
 *
 * ELEVEN of the fifteen offsets are constants this header already carries, which is the evidence
 * that the entries pair up with the draws: the score, the high score, the counter, the record
 * bitmap, the six slot cells and the panel frame. The other four have no draw in the recovered
 * code and are named for their offset. THE PAIRING IS NOT EXACT, and the C reproduces the original rather than
 * the intent: the $2800 entry restores 29 rows where the record bitmap draws 32, and the $1e08
 * entry (the counter's) `bsr`s a bare `rts`.
 */
#define WB_PANEL_RESTORE_FLAGS      0xdbb0u /* `lea $dbb0.l,a6` — the array's base */
#define WB_PANEL_RESTORE_FLAG_COUNT 15u     /* ...and how many entries the walk has */
#define WB_PANEL_REGION_A71 0xa71u  /* row 16, byte 113 (an ODD byte, so the right half of the
                                     * 16-px group at 224) — no draw in the recovered code */
#define WB_PANEL_REGION_AA0 0xaa0u  /* row 17, column 0 — the entry panel_restore_flag_dbb3 drives */
#define WB_PANEL_REGION_520 0x520u  /* row 8, column 64 px */
#define WB_PANEL_REGION_570 0x570u  /* row 8, column 224 px */

/* The five geometries the eleven live entries blit in: `rows` rows of `row_bytes` with BOTH cursors
 * stepping one scanline (unlike every blit above, whose source is a contiguous bitmap). Two of the
 * five are geometries this header already names — the HUD-slot cell (16 x 14) and the panel frame
 * (24 x 32) — and are reused rather than restated, which is itself part of the pairing evidence. */
#define WB_RESTORE_ROW_BYTES_32    32u
#define WB_RESTORE_ROWS_20         20u  /* $db12, the $aa0 entry */
#define WB_RESTORE_ROWS_29         29u  /* $db36, the $2800 entry */
#define WB_RESTORE_ROW_BYTES_44    44u  /* $daf8, the $520 and $570 entries */
#define WB_RESTORE_ROWS_8           8u
#define WB_RESTORE_MOVEM_REGISTERS 11u  /* == WB_RESTORE_ROW_BYTES_44 / 4: $daf8 moves its row as
                                         * one `movem.l` pair over d1-d7/a2-a5, not eight `move.l`.
                                         * The C consumes only the byte count; this is what the
                                         * entry pin builds that count's register mask from */

/* ---- the background scroll engine, $7522..$8228 (RUNTIME addresses; src/scroll.c) -------------
 *
 * The cluster keeps EIGHT pre-shifted copies of the level's background, $5800 bytes each, tiling
 * $44000..$70000 — the map project.toml records. Copy N holds the map drawn two pixels further
 * left than copy N-1, so a two-pixel horizontal scroll is a change of buffer and not a redraw;
 * `bg_scroll_blit` ($82f8, the block at the end of this section) is what copies the chosen one to
 * the screen.
 *
 * Each buffer is 176 scanlines of WB_BG_BUFFER_LINE bytes, addressed as a RING: the visible window
 * starts at WB_BG_SCROLL_Y_COARSE tile-rows down and wraps at the end, which is why every routine
 * here draws in two halves whose lengths come out of a table. Horizontally the same trick runs on
 * WB_BG_SCROLL_X, a tile column 0..15 that names where the ring's seam sits within a 128-byte row.
 *
 * The position words come in two pairs, one per axis: an absolute scroll stepped +/-2 and bounded
 * by a limit (WB_BG_SCROLL_POS_X / _LIMIT_X here; $83b0 / $83b4 for the vertical half), and the two
 * nibbles of it the drawing actually reads — WB_BG_SCROLL_PHASE is POS_X's low nibble and
 * WB_BG_SCROLL_X the next one up.
 *
 * THE VERTICAL HALF SCROLLS BY MOVING POINTERS, not by moving pixels. Its own ring position is a
 * ROW INDEX (WB_BG_SCROLL_Y, 0..WB_BG_SCROLL_Y_LAST in steps of WB_BG_SCROLL_STEP) plus sixteen
 * cached row pointers at WB_BG_BUFFER_ROWS that a step keeps equal to
 * `buffer + row * WB_BG_BUFFER_LINE`. There are TWO such cursors — the window's top scanline pair
 * and its bottom one, WB_BG_SCROLL_Y and WB_BG_SCROLL_Y_BOTTOM — each with its own wrap test, and
 * the eight pointers each owns are interleaved $8 apart. A step therefore uncovers one buffer ROW
 * rather than one tile column, and the fill that follows copies a tile row into copy 0 unrotated;
 * `bg_scroll_preshift_rows` then walks that row through the other seven, `rol.l #2` at a time.
 */
#define WB_SCROLL_FOLLOW_FROZEN  0xd76u   /* word: while nonzero the scroll neither refreshes the two
                                           * words below nor raises a request. NINE operand references
                                           * in the image — five `move.w #$ffff`, two `clr.w` and two
                                           * `tst.w`; `bg_scroll_run_queue` ($7522) and $f9a6 are the
                                           * only two that TEST it, and the name is read off those.
                                           * ../names.txt's `cmt 0xd76` itemizes all nine */
#define WB_SCROLL_FOLLOW_FROZEN_SET 0xffffu /* what all five of those `move.w #$ffff` sites write */
#define WB_SCROLL_FOLLOW_X       0x9934u  /* word pair: the followed object's position ON SCREEN.
                                           * $f9ae computes them as `object.x - $20 - POS_X` and
                                           * `object.y - $40 - POS_Y`, which is what makes the two
                                           * centres below screen coordinates rather than map ones */
#define WB_SCROLL_FOLLOW_Y       0x9936u
#define WB_SCROLL_CENTRE_X       0x5au    /* `subi.w #$5a,d1` / `subi.w #$30,d0` — where
                                           * bg_scroll_raise_requests wants the followed object */
#define WB_SCROLL_CENTRE_Y       0x30u
#define WB_BG_QUEUE_H_COUNT      0x7592u  /* word: two-pixel HORIZONTAL steps bg_scroll_run_queue
                                           * still owes. $7594 (the vertical one, below) is the
                                           * second half of the `clr.l $7592` that ends the drain */
#define WB_BG_QUEUE_V_COUNT      0x7594u
#define WB_BG_RAISED_V           0x7596u  /* byte PAIR: what bg_scroll_raise_requests sets and
                                           * bg_scroll_run_queue copies AS A WORD into
                                           * WB_BG_REQUEST_UP. $7597/$7599 have no writer of their
                                           * own anywhere in the image, so that word move is how
                                           * down and right are raised at all */
#define WB_BG_RAISED_V_UP        0x7596u
#define WB_BG_RAISED_V_DOWN      0x7597u
#define WB_BG_RAISED_H           0x7598u  /* the same pair for the horizontal axis */
#define WB_BG_RAISED_H_LEFT      0x7598u
#define WB_BG_RAISED_H_RIGHT     0x7599u
#define WB_BG_RAISED_SET         0xffu    /* `st` — what raises one of those four bytes */
#define WB_BG_SCROLL_PENDING     0x7a3cu  /* word: the half-rate latch the two steps share. A step
                                           * SETS it and moves nothing; the next one moves. The
                                           * opposite direction CLEARS it, cancelling the half-step */
#define WB_BG_FILL_COUNTS        0x7eaeu  /* longword scratch inside the code, between $7c08's rts
                                           * and $7eb2's entry: the two halves' `dbf` counts, copied
                                           * whole out of WB_BG_COL_SPLIT_TABLE */
#define WB_BG_FILL_COUNT_SECOND  0x7eb0u  /* == WB_BG_FILL_COUNTS + 2, read on its own as the
                                           * second half's count (negative => no second half) */
#define WB_BG_PRESHIFT_CARRY     0x8228u  /* WB_PLANES words, written and read only by
                                           * bg_scroll_preshift_rows: the plane bits that rotate off
                                           * the end of a buffer row and back round to its start */
#define WB_BG_REQUEST_UP         0x8230u  /* the four request bytes $759a dispatches on, in the order
                                           * it tests them: up, down, right ($8233), left ($8232).
                                           * Each handler clears its own before doing anything */
#define WB_BG_REQUEST_DOWN       0x8231u
#define WB_BG_REQUEST_LEFT       0x8232u
#define WB_BG_REQUEST_RIGHT      0x8233u
#define WB_BG_TILE_ROW           0x8234u  /* word: byte offset into a 128-byte tile bitmap, 0..$7f in
                                           * steps of WB_BG_TILE_ROW_STEP — the two scanlines a
                                           * vertical step redraws. Both column fills add it to their
                                           * tile pointer too */
#define WB_BG_ROW_SPLIT_TABLE    0x8236u  /* 16 x two words indexed by WB_BG_SCROLL_X * 4. Entry k is
                                           * (15-k, k-1), so a row fill's two halves always sum to
                                           * WB_BG_ROW_CELLS cells and entry 0's second count is -1 =
                                           * no second half. The horizontal counterpart of
                                           * WB_BG_COL_SPLIT_TABLE */
#define WB_BG_ROW_SPLIT_ENTRIES  16u      /* == WB_BG_ROW_CELLS: WB_BG_SCROLL_X's whole range */
#define WB_BG_SCROLL_Y_COARSE    0x8276u  /* word: bg_scroll_y ($83a8) >> 4, i.e. the tile row
                                           * the visible window starts at. The vertical half
                                           * publishes it; the column fills below only read it */
#define WB_BG_COL_SPLIT_TABLE    0x8278u  /* == WB_BG_SCROLL_Y_COARSE + 2, and reached only that
                                           * way (`lea $8276,a5 / move.w (a5)+,d0`): 11 x two words
                                           * indexed by Y_COARSE * 4. Entry k is (10-k, k-1), so the
                                           * two counts always sum to WB_BG_BUFFER_TILE_ROWS - 2 */
#define WB_BG_COL_SPLIT_ENTRIES  11u      /* == WB_BG_BUFFER_TILE_ROWS: Y_COARSE's whole range */
#define WB_BG_ROW_BYTE_OFFSET    0x82a4u  /* word: byte offset of the seam within a 128-byte buffer
                                           * row, 0..120 in steps of WB_BG_CELL_BYTES */
#define WB_BG_BUFFER_ROWS        0x82a6u  /* WB_BG_BUFFERS PAIRS of longwords, WB_BG_BUFFER_ROW_PAIR
                                           * apart, one pair per pre-shifted copy: the two buffer
                                           * rows the vertical half draws into and
                                           * bg_scroll_preshift_rows propagates. A vertical step
                                           * keeps pair member m equal to
                                           * `WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + row_m *
                                           * WB_BG_BUFFER_LINE`, which is why it moves all sixteen */
#define WB_BG_BUFFER_ROW_TOP     0u       /* the pair member WB_BG_SCROLL_Y owns... */
#define WB_BG_BUFFER_ROW_BOTTOM  4u       /* ...and the one WB_BG_SCROLL_Y_BOTTOM owns */
#define WB_BG_BUFFER_ROW_PAIR    8u       /* == both members: the stride from one copy to the next */
#define WB_BG_BUFFERS            8u       /* == the pre-shifted copies, WB_BG_BUFFER_LEN apart */
#define WB_BG_MAP_CURSOR         0x82e6u  /* word: byte offset into the map of the visible window's
                                           * top-left cell. A horizontal step moves it by 1, a
                                           * vertical one by WB_MAP_ROW_STRIDE */
#define WB_BG_EDGE_MASK_TABLE    0x82e8u  /* 8 words indexed by WB_BG_SCROLL_PHASE (a BYTE index, so
                                           * the phase's own 0/2/../14): $0000 $fffc $fff0 $ffc0
                                           * $ff00 $fc00 $f000 $c000 — that is `0xffff << phase`
                                           * for every entry but the first, which is $0000 and not
                                           * the $ffff the rule would give, so phase 0 clears the
                                           * whole cell and redraws it */
#define WB_BG_SCROLL_X           0x83a6u  /* tile column 0..15 (../names.txt: bg_scroll_x) */
#define WB_BG_SCROLL_Y           0x83a8u  /* row index of the window's TOP scanline pair within the
                                           * 176-row ring, 0..WB_BG_SCROLL_Y_LAST step 2 */
#define WB_BG_SCROLL_Y_BOTTOM    0x83aau  /* the same for its BOTTOM pair, wrapped independently.
                                           * $fb96 starts it at $9e = WB_BG_SCROLL_Y + 158 rows, and
                                           * only WB_BG_SCROLL_Y feeds WB_BG_SCROLL_Y_COARSE */
#define WB_BG_SCROLL_PHASE       0x83acu  /* which pre-shifted buffer: 0..14, step 2 */
#define WB_BG_SCROLL_POS_X       0x83aeu  /* absolute horizontal scroll, step 2 */
#define WB_BG_SCROLL_POS_Y       0x83b0u  /* the vertical counterpart, bounded by 0 and _LIMIT_Y */
#define WB_BG_SCROLL_LIMIT_X     0x83b2u  /* POS_X stops HERE, by `cmp.w` — the level's right edge */
#define WB_BG_SCROLL_LIMIT_BIAS  0xf0u    /* what separates WB_BG_SCROLL_LIMIT_X from the level's
                                           * right edge IN PIXELS, and the only two operand sites
                                           * the word has besides the scroll's own compare go one
                                           * each way: $fb18 SUBTRACTS it from `(cells << 4)` to
                                           * build the limit, and $11ca ADDS it back to get the
                                           * pixel x $1170 will not let a right edge pass. What the
                                           * 240 measures beyond that (the scrolled window's own
                                           * width) is not established */
#define WB_BG_SCROLL_LIMIT_Y     0x83b4u
#define WB_BG_STATE_WORD_LEN     2u       /* every scroll variable above is a word */

/* The map and the tiles it names. Both live past the end of the program ($218d0) except the tile
 * bitmaps, which are shipped in the .PRG — so a differential case seeds the first two and gets the
 * third for free. */
#define WB_TILE_BITMAPS          0x1d43eu /* tile N's bitmap is here + N * WB_TILE_BITMAP_LEN */
#define WB_TILE_BITMAP_LEN       128u     /* `lsl.l #7`: WB_BG_TILE_ROWS rows of WB_BG_CELL_BYTES */
#define WB_TILE_SHIPPED_FIRST    120u     /* the region holds 148 tiles and only these sixteen are
                                           * in the .PRG: tiles 0..119 and 136..147 are zero in the
                                           * file and filled at runtime, like the map above them.
                                           * A differential case draws from THESE, so its source is
                                           * the game's own pixels (test/test_scroll.py pins the
                                           * split, which is where the two numbers come from) */
#define WB_TILE_SHIPPED_COUNT    16u
#define WB_TILE_INDEX_TABLE      0x21e90u /* map byte -> tile number, as words (`add.w d0,d0`) */
#define WB_TILE_INDEX_ENTRIES    256u     /* the index is a BYTE out of the map, so this is its full
                                           * range; the table ends exactly at WB_MAP_ROW_STRIDE */
#define WB_MAP_ROW_STRIDE        0x22090u /* word: bytes per map row, added to walk down a column */
#define WB_MAP_DATA              0x22092u /* the map itself, one byte per cell */
#define WB_MAP_DATA_ROW          0x22094u /* == WB_MAP_DATA + 2. The same array as the column fills
                                           * read, indexed from its THIRD byte: the two row fills
                                           * spell their base this way and add the bare map cursor,
                                           * where the left column fill spells WB_MAP_DATA and adds
                                           * WB_BG_FILL_LEFT_MAP_OFF to the cursor */

/* The eight pre-shifted buffers. */
#define WB_BG_BUFFER_BASE        0x44000u
#define WB_BG_BUFFER_LEN         0x5800u  /* one buffer: WB_BG_BUFFER_TILE_ROWS tile rows */
#define WB_BG_BUFFER_PHASE_STRIDE 0x2c00u /* == WB_BG_BUFFER_LEN / 2, because PHASE steps by 2 */
#define WB_BG_BUFFER_LINE        128u     /* one buffer scanline: 256 px over WB_PLANES planes */
#define WB_BG_CELL_BYTES         8u       /* one 16-px tile column of one scanline, 4 planes */
#define WB_BG_TILE_ROWS          16u      /* scanlines per tile, and tile columns per buffer row */
#define WB_BG_TILE_BLOCK_LEN     2048u    /* == WB_BG_TILE_ROWS * WB_BG_BUFFER_LINE */
#define WB_BG_BUFFER_TILE_ROWS   11u      /* == WB_BG_BUFFER_LEN / WB_BG_TILE_BLOCK_LEN */
#define WB_BG_SCROLL_STEP        2u       /* what one horizontal step moves POS_X and PHASE */
#define WB_BG_PHASE_MASK         0xfu     /* PHASE and SCROLL_X both wrap in a nibble */
#define WB_BG_PHASE_LAST         0xeu     /* the highest phase, which the LEFT step writes outright
                                           * (`move.w #$e`) where the right one lets the mask wrap */
#define WB_BG_PENDING_SET        0xffffu  /* what the RIGHT step arms WB_BG_SCROLL_PENDING with */
#define WB_BG_ROW_OFFSET_MASK    0x7fu    /* ...and ROW_BYTE_OFFSET in seven bits, one step short of
                                           * WB_BG_BUFFER_LINE (only the LEFT step masks it) */
#define WB_BG_ROW_CELLS          16u      /* == WB_BG_BUFFER_LINE / WB_BG_CELL_BYTES */
#define WB_BG_SCROLL_Y_LAST      0xaeu    /* the highest ring row: the UP step reloads it there when
                                           * the row hits 0, the DOWN step wraps it back to 0 from
                                           * here. $ae * WB_BG_BUFFER_LINE = $5700, two scanlines
                                           * short of WB_BG_BUFFER_LEN */
#define WB_BG_Y_COARSE_SHIFT     4u       /* `asr.w #4`: WB_BG_SCROLL_Y -> WB_BG_SCROLL_Y_COARSE */

/* The two ROW fills' own operands — the vertical counterparts of the column fills' below. */
#define WB_BG_ROW_FILL_SCANLINES 2u       /* what one vertical step uncovers, and so what a row fill
                                           * copies per cell: `move.l (a0)+,(a1)+` twice for the
                                           * first, `move.l (a0)+,120(a1)` twice for the second */
#define WB_BG_TILE_ROW_STEP      0x10u    /* == WB_BG_ROW_FILL_SCANLINES * WB_BG_CELL_BYTES, what a
                                           * fill moves WB_BG_TILE_ROW by */
#define WB_BG_TILE_ROW_MASK      0x7fu    /* ...wrapping inside one WB_TILE_BITMAP_LEN bitmap */
#define WB_BG_BOTTOM_ROW_STRIDES 0xau     /* `mulu.w #$a,d1`: how many WB_MAP_ROW_STRIDE below the
                                           * map cursor the BOTTOM row's map row sits */
#define WB_BG_ROW_DRAWN_TOP      0u       /* `clr.w d0` / `move.w #$ffff,d0` — the low word each row
                                           * fill returns, and the only thing
                                           * bg_scroll_preshift_rows tests to pick its source row */
#define WB_BG_ROW_DRAWN_BOTTOM   0xffffu

/* bg_scroll_preshift_rows' own geometry: it walks the freshly drawn row pair through the seven
 * copies above the one it was drawn into, two pixels further left each time. */
#define WB_BG_PRESHIFT_COPIES    7u       /* == WB_BG_BUFFERS - 1: every copy but the drawn one */
#define WB_BG_PRESHIFT_ROWS      2u       /* == WB_BG_ROW_FILL_SCANLINES: the pair just drawn */
#define WB_BG_PRESHIFT_BITS      2u       /* `rol.l #2`: the two pixels one copy is ahead of the last */

/* The two column fills' own operands: which map cell the fill starts from, and (for the right edge)
 * the bias applied to WB_BG_SCROLL_X before it becomes a byte offset. The offsets differ by 15 tile
 * columns, which is what makes one the left edge of the window and the other the right. */
#define WB_BG_FILL_LEFT_MAP_OFF  2u       /* $7eb2: `addq.w #2,d0` on the map cursor */
#define WB_BG_FILL_RIGHT_MAP_OFF 0x11u    /* $7c08: `addi.w #$11,d0` */
#define WB_BG_FILL_RIGHT_X_BIAS  0xeu     /* $7c08: `addi.w #$e,d0` before the nibble mask */

/* ---- $82f8..$8dfe: the CONSUMER of those buffers (RUNTIME addresses; src/scroll.c) ------------
 *
 * Everything above produces the eight pre-shifted buffers; `bg_scroll_blit` reads one. Once a frame
 * it copies WB_BG_BLIT_SCANLINES scanlines of WB_BG_BLIT_ROW_BYTES out of the buffer
 * WB_BG_SCROLL_PHASE names into WB_SCREEN_BACK, and BOTH of the rings the engine maintains surface
 * here as a split rather than as arithmetic: the window may run off the buffer's 176th scanline
 * (two halves, `lea -$5800(a0),a0` between them), and each source ROW is a 128-byte ring whose seam
 * sits at WB_BG_SCROLL_X (two runs of `move.l`, `lea -128(a0),a0` between them).
 *
 * That second split is the ONLY thing separating the sixteen unrolled copy routines at
 * $83b6..$8dfe, which the jump table below names and two `jmp (a2)` enter. So the reconstruction
 * takes the column as a parameter and the table collapses into it — the claim test/test_scroll.py
 * makes good by assembling all sixteen bodies from one pattern and pinning each against the image.
 */
#define WB_BG_BLIT_TABLE          0x8366u /* 16 longwords, the variants' entry addresses. A
                                           * whole-image abs.l scan gives it ONE operand reference,
                                           * the `lea $8366.l,a2` at $832e, and each variant address
                                           * exactly one — its own entry here */
#define WB_BG_BLIT_VARIANTS       16u     /* == WB_BG_SCROLL_X's whole range, which is also the
                                           * table's whole extent: $8366..$83a6 runs into
                                           * WB_BG_SCROLL_X itself */
#define WB_BG_BLIT_SCREEN_ORIGIN  0x1420u /* `adda.w #$1420,a1`: byte offset into WB_SCREEN_BACK of
                                           * the window's top-left corner — row 32, byte 32 */
#define WB_BG_BLIT_SCANLINES      160u    /* `move.w #$9f,d7` plus one: the window's height */
#define WB_BG_BLIT_LONGWORDS      30u     /* `move.l (a0)+,(a1)+` per scanline, in every variant */
#define WB_BG_BLIT_ROW_BYTES      120u    /* == WB_BG_BLIT_LONGWORDS * 4: 240 px of the 320 */
#define WB_BG_BUFFER_SCANLINES    176u    /* == WB_BG_BUFFER_LEN / WB_BG_BUFFER_LINE, and the `#$b0`
                                           * the wrapping arm counts the first half down from */
#define WB_BG_BLIT_WRAP_ROW       0x10u   /* == WB_BG_BUFFER_SCANLINES - WB_BG_BLIT_SCANLINES: the
                                           * ring row at or above which the window runs off the
                                           * buffer's end. `subi.w #$10,d6 / bpl` and `bpl` reads N
                                           * ALONE — unlike the `bgt`/`blt` pair in
                                           * bg_scroll_raise_requests, this one really is the
                                           * wrapped difference's own sign */
#define WB_BG_BLIT_NO_SECOND_HALF 0xffffu /* `move.w #$ffff,d6` — what the non-wrapping arm loads,
                                           * and what the `tst.w d6 / bpl` after the first half
                                           * reads as "there is no second half" */
#define WB_BG_BLIT_ROW_SHIFT      7u      /* `asl.w #7`: WB_BG_SCROLL_Y into a byte offset, i.e. by
                                           * WB_BG_BUFFER_LINE */
#define WB_BG_ROW_LONGWORDS       32u     /* == WB_BG_BUFFER_LINE / 4 */
#define WB_BG_CELL_LONGWORDS      2u      /* == WB_BG_CELL_BYTES / 4: what one tile column of one
                                           * scanline costs the copy, and so how much further into
                                           * the row each successive variant's seam falls */

/* ---- the actor records and their screen projection (RUNTIME addresses; src/actor.c) -----------
 *
 * The game keeps its moving objects as WB_ACTOR_SCREEN_RECORD_COUNT records of
 * WB_ACTOR_RECORD_BYTES, in one of THREE tables picked by the two mode flags, and once a frame it
 * projects that table into a parallel array of WB_ACTOR_SCREEN_RECORD_BYTES records at
 * WB_ACTOR_SCREEN_RECORDS: map position minus the scroll, plus the sprite to draw. $8f02 (the
 * sprite pass, reconstructed in src/blit.c as sprite_draw_pass) is what reads the result.
 *
 * WHERE THE SCROLL'S OWN INPUT COMES FROM. WB_SCROLL_FOLLOW_X above IS screen record
 * WB_ACTOR_FOLLOWED_SLOT — `WB_ACTOR_SCREEN_RECORDS + 12 * 6`, asserted in test/test_actor.py
 * rather than restated here — so "the followed object" is that slot of the actor table, and $8dfe
 * exists to refresh exactly that one record BEFORE bg_scroll_run_queue reads it. $8e66 then
 * refreshes all nineteen (slot 12 included) after the scroll has moved.
 */
#define WB_STATE_FLAG_A34            0xa34u   /* the THIRD word of the same band, and the least
                                               * established: eleven operand sites (one abs.l at
                                               * $8d8, ten abs.w), none of them read by a routine
                                               * reconstructed so far. stage_reset_state clears it
                                               * beside A30 and A32, which is all this project
                                               * knows about it — the name carries the address */
#define WB_STATE_FLAG_A30            0xa30u   /* the second mode flag, read like WB_STATE_FLAG_A32
                                               * ($a32: thirteen `tst.w` readers, three writers).
                                               * Ten operand sites of its own: five `tst.w` readers
                                               * ($4ec, $8dfe, $8e66, $dbc0, $ff42) against two
                                               * `clr.w` and three `move.w #$ffff` writers, so it
                                               * only ever holds $0000 or $ffff */
#define WB_STATE_FLAG_SET            0xffffu  /* the one nonzero value any of the three is written
                                               * with — every writer of all three is a
                                               * `move.w #$ffff` or a `clr.w` */
#define WB_ACTOR_TABLE_A30           0x9bd0u  /* the table $8e66 projects while A30 is negative */
#define WB_ACTOR_TABLE_A32           0x9e34u  /* ...while A30 is not and A32 is */
#define WB_ACTOR_TABLE_DEFAULT       0x996cu  /* ...and while neither is */
#define WB_ACTOR_TABLE_SELECTED      0xa098u  /* longword: whichever of the three $8e66 published */
#define WB_ACTOR_RECORD_BYTES        32u      /* `lea 32(a0),a0` between records */
#define WB_ACTOR_FOLLOWED_DEFAULT    0x9aecu  /* $67e0's a1 while WB_STATE_FLAG_A32 is zero. It is
                                               * WB_ACTOR_TABLE_DEFAULT + 12 * 32, i.e. slot
                                               * WB_ACTOR_FOLLOWED_SLOT of that table */
#define WB_ACTOR_FOLLOWED_A32        0x9fb4u  /* ...and slot 12 of WB_ACTOR_TABLE_A32 while it is
                                               * not. There is no A30 form: $8dfe's `bpl` gate is
                                               * what keeps $67e0 out of the A30 mode entirely */
#define WB_ACTOR_X                   0u       /* word: map position */
#define WB_ACTOR_Y                   2u
#define WB_ACTOR_SPRITE              6u       /* word: what the sprite pass draws for this record */
#define WB_ACTOR_FLAGS               8u       /* byte */
#define WB_ACTOR_FLAG_SIDE_BIT       3u       /* $67c2 raises it while the followed actor is to the
                                               * LEFT. AN EARLIER PLATE SAID "its only reader in the
                                               * image is the `btst #3,8(a1)` at $51e" — true only of
                                               * the a1 FORM, which is what that routine ($50a) uses
                                               * to read it on the FOLLOWED record. The census over
                                               * immediate bit-ops on d16(An) finds 139 operand
                                               * sites for this bit: 85 `btst` (83 on a0, one on a1
                                               * at $51e, one on a5), 30 `bchg`, 12 `bclr` and 12
                                               * `bset`. It is the tier's own facing flag and half
                                               * the behaviour handlers read it; batch 40 phase B
                                               * added two more readers ($ed6, the walk's
                                               * knock-back, and $12e6, the fireball's) and gave the
                                               * claim the census its WB_ACTOR_FLAG_MOVED_BIT
                                               * sibling already had */
#define WB_ACTOR_FLAG_FLICKER_BIT    6u       /* set -> the projection publishes no sprite on the
                                               * frames WB_FRAME_TOGGLE is nonzero, i.e. the record
                                               * is drawn every other frame */
#define WB_ACTOR_OUT_OF_REACH        0xffffu  /* `move.w #$ffff,d0` — $67f8's "farther than d0" */

/* $6528's table (actor.h). Sixteen SIGNED BYTE PAIRS per row, one row per speed, indexed by a
 * direction code the routine builds out of the signs and the ratio of the two deltas. Its ONE
 * `lea $6586.l` is inside $6528 itself; the table's own extent past row 6 is not established here,
 * because only rows the two callers name are read. */
#define WB_ACTOR_AIM_TABLE           0x6586u
#define WB_ACTOR_AIM_ROW_BYTES       0x20u    /* `asl.w #5,d4` */
#define WB_ACTOR_AIM_PAIR_BYTES      2u       /* `asl.w #1,d4` on the direction code */
#define WB_ACTOR_AIM_CODE_BASE       4u       /* `move.w #$4,d4` before the two sign tests */
#define WB_ACTOR_AIM_CODE_DX_EOR     0xcu     /* `eori.w #$c,d4` when the x delta is negative */
#define WB_ACTOR_AIM_CODE_DY_EOR     4u       /* `eori.w #$4,d4` when the y delta is negative */
#define WB_ACTOR_AIM_CODE_SWAP_BIT   3u       /* `btst #3,d4 / bne` — clear means the two deltas are
                                               * exchanged before the ratio is measured */
#define WB_ACTOR_SCREEN_RECORDS      0x98ecu  /* the projection's destination array */
#define WB_ACTOR_SCREEN_RECORDS_END  0x995eu  /* `cmpa.l #$995e,a1` — one past the last record */
#define WB_ACTOR_SCREEN_RECORD_BYTES 6u
#define WB_ACTOR_SCREEN_RECORD_COUNT 19u      /* == (END - RECORDS) / RECORD_BYTES (pinned). The
                                               * ACTOR tables are read as 19 records as well, but
                                               * only because the projection walks 19 of them —
                                               * nothing bounds those tables independently */
#define WB_ACTOR_FOLLOWED_SLOT       12u      /* the slot the scroll follows and $8dfe refreshes */
#define WB_ACTOR_SCREEN_X            0u
#define WB_ACTOR_SCREEN_Y            2u
#define WB_ACTOR_SCREEN_SPRITE       4u
#define WB_ACTOR_SCREEN_X_BIAS       0x20u    /* `subi.w #$20,d2` before the scroll is subtracted */
#define WB_ACTOR_SCREEN_Y_BIAS       0x40u    /* `subi.w #$40,d2` */
#define WB_ACTOR_SPRITE_HIDDEN       0u       /* `move.w #$0,(a1)` — the flicker arm's sprite word */
#define WB_FRAME_TOGGLE              0x712u   /* word, inverted every frame by flip_screen
                                               * (../names.txt) — read here as a boolean */

/* ---- the actor table's LIFECYCLE, and the rest of a record's fields (src/actor.c) -------------
 *
 * The projection above reads four fields of a record. These are the rest, and the routines that
 * create and destroy records: a table is reset to WB_ACTOR_FREE_MARKER records, a run of slots is
 * marked free again, an allocator hands back the first free slot of ONE OF TWO POOLS, and a spawn
 * fills that slot in from a 32-byte template.
 *
 * THE TWO POOLS ARE WHAT EXPLAINS SLOT WB_ACTOR_FOLLOWED_SLOT. $1b68 searches
 * WB_ACTOR_ALLOC_LOW_FIRST..+WB_ACTOR_ALLOC_LOW_SLOTS and $1b8e
 * WB_ACTOR_ALLOC_HIGH_FIRST..+WB_ACTOR_ALLOC_HIGH_SLOTS, and the two runs meet EXACTLY either side
 * of slot 12 — 3..11 and 13..18 — so the followed actor's slot is the one gap no allocator can
 * hand out. Slots 0..2 are below both pools and are equally reserved. The arithmetic is
 * test/test_actor.py's, not a remark here.
 */
#define WB_ACTOR_FREE_MARKER         0xffbeu  /* word at WB_ACTOR_X: "this slot holds no actor".
                                               * $1f36 stamps it, $df9e stamps it, and both
                                               * allocators `cmpi.w #$ffbe,(a1)` for it */
#define WB_ACTOR_TYPE                4u       /* word: what the record IS. $ffe4 copies it out of
                                               * the template and the map probes compare it
                                               * against WB_ACTOR_TYPE_PLAYER */
#define WB_ACTOR_TYPE_UNSCORED       0x26u    /* `cmpi.w #$26,4(a0)` at $6c0a — the one type whose
                                               * defeat pays no score, does not count a kill and
                                               * never respawns; it goes straight to freeing the
                                               * slot. WHICH creature it is is not established, and
                                               * it is outside the 0..31 range both the damage and
                                               * the hit-point tables cover */
#define WB_ACTOR_TYPE_PLAYER         1u       /* `cmpi.w #$1,4(a0)` — the only value anything
                                               * reconstructed here tests for */
#define WB_ACTOR_FLAGS2              9u       /* the SECOND flag byte; `bset`/`bclr` reach it with
                                               * their own bit numbers, and `clr.w 8(a1)` clears
                                               * WB_ACTOR_FLAGS and this one together */
#define WB_ACTOR_FIELD_10            10u      /* byte: a per-record COUNTDOWN. Ten operand sites in
                                               * the image, of which $5092's `subq.b #1,10(a0)` is
                                               * the decrement and $e16's `move.b d0,10(a0)` a
                                               * second seeding; two sites ($1e1a, $1801e) read it
                                               * as a WORD, i.e. together with WB_ACTOR_SPEED —
                                               * which $dbc0's fragment arm and $6d24's respawn both
                                               * write immediately after it, from the same
                                               * parameter byte in the fragment arm's case. What it
                                               * counts is not established */
#define WB_ACTOR_SPEED               11u      /* byte: the fall step $14d6 accelerates, $2af2 sets
                                               * from d0 and the landing arm of $1400 clears */
#define WB_ACTOR_FIELD_12            12u      /* byte: a second COUNTDOWN, and the busier of the
                                               * pair — eighteen operand sites, seeded $14 or $ff
                                               * and decremented by both `subq.b #1,12(a0)` and
                                               * `subq.w #1,12(a0)` at different sites, so the WORD
                                               * at 12 is read as one value too. Not established
                                               * either */
#define WB_ACTOR_FIELD_18            18u      /* byte, cleared by the spawn: the ANIMATION CURSOR.
                                               * Five routines in src/behavior.c index a frame table
                                               * with it and step it on ($698a, $3006, $5a3c, $6872
                                               * and $2f86's clear), each with its own wrap — it is
                                               * a BYTE OFFSET into a word table, not an index. The
                                               * name is kept because batches before 29 read it as
                                               * an unread field and nothing else has renamed it */
#define WB_ACTOR_TEMPLATE_SLOT       19u      /* byte: which template of WB_TABLE_PTR_21E8C's table
                                               * spawned this record — `(a0 - table) asr.l #5`, so
                                               * a SIGNED shift of the whole longword */
#define WB_ACTOR_FLICKER_COUNTDOWN   21u      /* byte: how many frames of
                                               * WB_ACTOR_FLAG_FLICKER_BIT are left. FIVE operand
                                               * sites in the image and only one reader — $f14's
                                               * `subq.b #1,21(a0) / bne`, which on reaching zero
                                               * clears the flicker bit AND
                                               * WB_ACTOR_FLAGS2_INVULNERABLE_BIT. $69fe seeds it
                                               * with WB_ACTOR_DAMAGE_FLICKER_FRAMES */
#define WB_ACTOR_KIND                20u      /* byte: WHICH CREATURE this slot currently is, as an
                                               * index into WB_ACTOR_KIND_TABLE. $6d0e is its one
                                               * writer in the image — the respawn continuation,
                                               * storing the low byte of a stage_random_kind draw */
#define WB_ACTOR_FIELD_21            21u      /* byte: behaviour slot 23 stamps
                                               * WB_ACTOR_TYPE23_STUN_FRAMES into it on the record it
                                               * has just robbed the player for. WHAT READS IT is not
                                               * established — this is the only writer read so far */
#define WB_ACTOR_FIELD_22            22u      /* byte, cleared by $10a2's player arm. The behaviour
                                               * tier writes it three ways: $6d70 raises
                                               * WB_ACTOR_FIELD_22_RIDING_BIT in it, $6dd8 lowers
                                               * that bit, and $701c forces the whole byte to
                                               * WB_ACTOR_FIELD_22_HOLD while it is nonzero. FOR THE
                                               * PLAYER it is the WALK SPEED in pixels a frame:
                                               * $ec8's accelerator raises it, spends it and clamps
                                               * it, and the probe's own clear above is what
                                               * a blocked step does to it (see "THE WALK") */
#define WB_ACTOR_FIELD_23            23u      /* byte: behaviour slot 7's own FRAME CURSOR, stepped
                                               * `addq.b #1` and wrapped by a SIGNED `cmpi.b #$c`
                                               * against WB_ACTOR_TYPE07_FRAME_COUNT. Distinct from
                                               * WB_ACTOR_FIELD_18, which the damage arm clears.
                                               * FOR THE PLAYER it is which way the walk is
                                               * TRAVELLING — zero LEFT, WB_ACTOR_ST_BYTE right —
                                               * and $ec8's turn arms are its only writers */
#define WB_ACTOR_FIELD_26            26u      /* word: the swoop's LAUNCH Y — the y a record was at
                                               * when actor_swoop_state0_acquire committed, which
                                               * actor_swoop_state3_descend rises back to. The
                                               * dropper shot at $7200 writes the same offset for
                                               * behaviour slot 57's own meaning, which batch 39
                                               * read: it is that shot's dy, ADDED to the y every
                                               * frame. The dropper writes it only while
                                               * WB_ACTOR_FLAG_SIDE_BIT is set, so a right-facing
                                               * dropper's shot flies on whatever the freed slot
                                               * left there */
#define WB_ACTOR_FIELD_30            30u      /* two bytes the spawn clears; $ff42 reads 30 as a
                                               * flag and counts 31 down. In the behaviour tier 30
                                               * is a COUNTDOWN of its own — $2f86 and $6872 tick it
                                               * and $23b6 stamps WB_ACTOR_SHOT_HIT_MARK into the
                                               * one it hits */
#define WB_ACTOR_FIELD_31            31u
#define WB_ACTOR_HALF_WIDTH          14u      /* word: half the footprint, in pixels. The map probes
                                               * measure from `x - half_width` and $13c8 hands
                                               * $1400 twice this as the span to scan */
#define WB_ACTOR_SIZE_SECOND         16u      /* word: the other half of the longword the spawn
                                               * stamps at WB_ACTOR_HALF_WIDTH, and the behaviour
                                               * tier reads it as the VERTICAL extent — $5c6e's box
                                               * is `y - 16(a0) .. y` and $23b6 sums the two records'
                                               * words the same way it sums their half widths */
#define WB_ACTOR_FLAG_MOVING_BIT     0u       /* $2af2 raises both of these; the `btst #0,8(a0) /
                                               * bne / rts` at $1376 is bit 0's one reader in the
                                               * tier above, and $1400's landing arm clears bit 1 */
#define WB_ACTOR_FLAG_LAUNCHED_BIT   1u
#define WB_ACTOR_FLAG_SUPPORTED_BIT  2u       /* raised by $1400's landing arm; $2af2 and $14d6
                                               * clear it, and $1400 reads it to decide whether to
                                               * start a fall */
#define WB_ACTOR_FLAG_FALLING_BIT    4u       /* raised by $14d6 and by $1400's unsupported arm,
                                               * cleared by the landing */
#define WB_ACTOR_FLAGS2_BIT_0        0u       /* the busiest bit in the image — 49 `bset`, 36 `bclr`
                                               * and 33 `btst` sites against 9(An), the 49th being
                                               * $6a22, the `bset #0,9(a1)` inside $69fe (every
                                               * other site is on a0). WHAT IT GATES IS NOT
                                               * ESTABLISHED, hence offset+role rather than a
                                               * meaning: $69fe raises it on the record it damages,
                                               * which alone would read as "struck" — but $6b46's
                                               * one `bsr` caller raises it at $7090, calls, and
                                               * CLEARS it at $709e on return, which is the shape of
                                               * a guard or a re-entry lock and is evidence against
                                               * that reading */
#define WB_ACTOR_FLAGS2_LANDED_BIT   1u       /* $1400 raises it on the landing arm and clears it on
                                               * both unsupported ones */
#define WB_ACTOR_FLAGS2_SPAWNED_BIT  2u       /* the one bit the spawn raises, and it has exactly
                                               * TWO operand sites in the whole image: `bset #2,
                                               * 9(a1)` at $10044 inside the spawn, and `bclr #2,
                                               * 9(a0)` at $69b0 inside actor_spawn_anim_step. So
                                               * the spawn raises it and the animation lowers it —
                                               * which is what says that animation is the record
                                               * APPEARING and not a death (25 handlers open by
                                               * branching there while it is up) */
#define WB_ACTOR_FLAGS2_DEFEATED_BIT 3u       /* $6b46's `bset #3,9(a0)` is its ONE writer in the
                                               * image, on the frame the template's hit-point pool
                                               * reaches zero or goes negative. 35 `btst #3,9(a0)`
                                               * read it and four routines clear it */
#define WB_ACTOR_FLAGS2_INVULNERABLE_BIT 4u   /* raised at $10782 beside a flicker of $ff frames,
                                               * cleared at $f22 when WB_ACTOR_FLICKER_COUNTDOWN
                                               * runs out, and read at $6a16 and $6dfa. $69fe
                                               * returns without writing anything at all while a
                                               * record carries it */
#define WB_ACTOR_FALL_SPEED_MAX      8u       /* `cmpi.b #$8,d0 / beq` — $14d6 stops accelerating
                                               * ON this value, so it is reached and never passed */
#define WB_ACTOR_ALLOC_LOW_FIRST     3u       /* `lea 96(a1),a1` == 3 * WB_ACTOR_RECORD_BYTES */
#define WB_ACTOR_ALLOC_LOW_SLOTS     9u       /* `move.w #$8,d0` + `dbf` */
#define WB_ACTOR_ALLOC_HIGH_FIRST    13u      /* `lea 416(a1),a1` */
#define WB_ACTOR_ALLOC_HIGH_SLOTS    6u       /* `move.w #$5,d0` + `dbf` */
#define WB_ACTOR_ALLOC_NONE          0u       /* `movea.l #$0,a1` — the allocators' "table full".
                                               * $ffe4's two call sites do NOT test it */

/* The spawn template: 32-byte records in the table WB_TABLE_PTR_21E8C points at, terminated by
 * WB_SPAWN_TERMINATOR in their first word. $ffe4 turns one into an actor record. */
#define WB_SPAWN_RECORD_BYTES        32u
#define WB_SPAWN_TERMINATOR          0xffffu  /* `cmpi.w #$ffff,(a0)` closes $ff42's walk */
#define WB_SPAWN_TYPE                12u      /* word: becomes WB_ACTOR_TYPE, and selects the size */
#define WB_SPAWN_SIZE                14u      /* the two words $ffe4 copies for the five types that
                                               * carry their own, at 14 and 16 */
#define WB_SPAWN_X                   24u      /* word: becomes WB_ACTOR_X */
#define WB_SPAWN_Y                   26u      /* ...and 26 becomes WB_ACTOR_Y */
#define WB_ACTOR_SIZE_TABLE          0x1009au /* longword per type: the {half width, second word}
                                               * pair the spawn stamps for every type that does not
                                               * carry its own. Indexed `lsl.w #2` on the type, so
                                               * the index is a WORD and wraps at 0x4000 */
#define WB_ACTOR_TEMPLATE_SLOT_SHIFT 5u       /* `asr.l #5` == log2(WB_SPAWN_RECORD_BYTES) */

/* ---- the per-frame spawn pass ($ff42) and the rest of a TEMPLATE's fields (src/actor.c) -------
 *
 * THE TEMPLATE TABLE HAS A FOUR-WORD HEADER, immediately BELOW the pointer WB_TABLE_PTR_21E8C
 * holds: $ff42 reads it as `-8(a6)`..`-2(a6)`, so the header base is the table minus
 * WB_SPAWN_HEADER_BYTES. What each word is comes from the pair of routines that move it — $ff42
 * raises WB_SPAWN_HEADER_LIVE on every spawn and $6c38 lowers it on every death, and $ff42's own
 * `move.w -8(a6),d0 / cmp.w -6(a6),d0 / beq` is the capacity test that pairs with it.
 *
 * WB_SPAWN_ARMED / WB_SPAWN_COUNTDOWN sit at the same two offsets as WB_ACTOR_FIELD_30 / _31, and
 * both records are WB_SPAWN_RECORD_BYTES long — but they are fields of DIFFERENT records: $ffe4
 * clears the ACTOR's pair while $ff42 walks the TEMPLATE's, and $6c4e re-arms the template's with
 * $ff each. That the two layouts agree here is not established by anything.
 */
#define WB_SPAWN_HEADER_BYTES        8u       /* four words below the table pointer */
#define WB_SPAWN_HEADER_MAX_LIVE     0u       /* -8(a6): what the live count is compared against */
#define WB_SPAWN_HEADER_LIVE         2u       /* -6(a6): raised per spawn here, lowered at $6c38 */
#define WB_SPAWN_HEADER_CURSOR       4u       /* -4(a6): the next template, post-incremented */
#define WB_SPAWN_HEADER_WRAPPED      6u       /* -2(a6): once the cursor has reached the last record
                                               * — after which spawns come from the sweep */
#define WB_SPAWN_WRAPPED_SET         0xffffu  /* `move.w #$ffff,-2(a6)`, and the `cmpi.w #$ffff` that
                                               * reads it. Numerically WB_SPAWN_TERMINATOR, but a
                                               * different field of a different record */
#define WB_SPAWN_ARMED               30u      /* byte: nonzero -> this template is counting down */
#define WB_SPAWN_COUNTDOWN           31u      /* byte, decremented once a frame while armed */
#define WB_SPAWN_HITPOINTS           4u       /* word: the pool $6b46's `sub.w d0,4(a1)` spends, and
                                               * on whose zero-or-negative it raises bit 3 of the
                                               * actor's WB_ACTOR_FLAGS2. $1006a seeds it */
#define WB_SPAWN_KILL_COUNT          6u       /* word: `addq.w #1,6(a1)` at $6c2a, and the template
                                               * retires once `cmpi.w #$2,6(a1)` stops being `ble`.
                                               * (This comment used to say $6bfa, which is the
                                               * `movea.l` that loads the record — batch 21b read
                                               * the routine and moved it to the `addq` itself) */
#define WB_SPAWN_KILL_RESPAWN_LIMIT  2u       /* `cmpi.w #$2,6(a1) / ble` — at or below this the
                                               * defeat RESPAWNS the slot instead of freeing it */
#define WB_SPAWN_REARM               0xffu    /* `move.b #$ff` into BOTH WB_SPAWN_ARMED and
                                               * WB_SPAWN_COUNTDOWN, the longest countdown a byte
                                               * holds */
#define WB_SPAWN_RESPAWN_KIND        8u       /* word: the kind the slot is FORCED to come back as
                                               * on a respawn before the last (`move.w 8(a1),d0` at
                                               * $6ce8). Zero means "draw one", which is
                                               * stage_random_kind32's one call site */
#define WB_SPAWN_FINAL_KIND          10u      /* word: the same, for the respawn whose kill count is
                                               * exactly WB_SPAWN_KILL_RESPAWN_LIMIT (`move.w
                                               * 10(a1),d0` at $6cfa). Zero draws through
                                               * stage_random_kind8 instead — the 8-wide table, not
                                               * the 32-wide one. NEITHER field has shipped bytes to
                                               * read: the template table is loaded from disk and
                                               * only $b372 publishes WB_TABLE_PTR_21E8C */
#define WB_SPAWN_SCORE_TABLE         0x6c5cu  /* one packed-BCD LONGWORD per WB_SPAWN_TYPE, the score
                                               * a defeat pays. It sits inside $6bb8's own bytes,
                                               * between that routine's `rts` and the continuation
                                               * at $6cdc, and is `lea $6c5c.l,a2`'s only reference
                                               * in the image */
#define WB_SPAWN_SCORE_TABLE_ENTRIES 32u      /* == ($6cdc - $6c5c) / WB_SPAWN_SCORE_LEN, the same
                                               * 32 types WB_SPAWN_HITPOINT_TABLE_ENTRIES has. The
                                               * CODE bounds the index at NEITHER end: the type is
                                               * scaled by a `lsl.w`, so it wraps at $10000 and can
                                               * name any longword in the 64 KiB above the table */
#define WB_SPAWN_SCORE_LEN           4u
#define WB_SPAWN_SCORE_SHIFT         2u       /* `lsl.w #2,d2` == log2(WB_SPAWN_SCORE_LEN) */
#define WB_SPAWN_SCORE_EXTEND_BIT    14u      /* == 16 - WB_SPAWN_SCORE_SHIFT: the LAST bit that
                                               * `lsl.w #2,d2` pushes out of the WORD, and so the X
                                               * it leaves. `bcd_add_score_bd70`'s first `abcd`
                                               * folds that bit into the score's lowest digit, which
                                               * makes a type with bit 14 set pay one extra unit */

/* WHAT A RESPAWNED SLOT COMES BACK AS ($6cdc..$6d59). The continuation picks a KIND — the template's
 * own forced one, or a stage_random_kind draw when that is zero — stores it at WB_ACTOR_KIND and
 * reads the record's new WB_ACTOR_TYPE and WB_ACTOR_SPRITE out of the 16-byte table below. Every
 * other field it writes is a LITERAL, which is why they are all named here.
 *
 * THE INDEX IS BOUNDED BY ITS OWN ARITHMETIC AND BY NOTHING ELSE. `tst.w d0 / bmi` has already
 * refused a negative kind, `lsl.w #4,d0` scales it INSIDE the word (so a kind at or above $1000
 * wraps) and `lea 0(a2,d0.w),a2` then SIGN-EXTENDS that word — so the read lands anywhere in
 * [table - $8000, table + $7ff0], which is inside the image at both ends and can never reach the
 * 24-bit bus wrap. A kind drawn by either stage_random_kind is 0..31 and stays inside the 22 rows. */
#define WB_ACTOR_KIND_TABLE          0x1044cu /* TWO references, by a whole-image scan of both
                                               * absolute encodings (batch 34): `lea $1044c.l,a2` at
                                               * $6d3c and `lea $1044c.l,a1` at $5476, inside
                                               * `actor_behavior_type38_pickup`. The "one reference"
                                               * this line used to claim was never swept; batch 38
                                               * re-ran the scan and cited the INSTRUCTIONS, where
                                               * batch 34 had cited their longword operands */
#define WB_ACTOR_KIND_RECORD_BYTES   16u
#define WB_ACTOR_KIND_RECORD_SHIFT   4u       /* `lsl.w #4,d0` == log2(WB_ACTOR_KIND_RECORD_BYTES) */
#define WB_ACTOR_KIND_TABLE_ROWS     22u      /* == (0x105ac - 0x1044c) / WB_ACTOR_KIND_RECORD_BYTES.
                                               * Bounded ABOVE by the FOURTEEN longword code
                                               * pointers of WB_PICKUP_EFFECT_TABLE at 0x105ac (the
                                               * first is 0x105e4, the code just past them). Of the
                                               * two readers, `actor_respawn_as_new_kind` bounds the
                                               * index at neither end and slot 38's `cmpi.b #$2 /
                                               * bge` bounds it at 2..127. Rows 0..20 all carry
                                               * WB_ACTOR_TYPE_UNSCORED in
                                               * their type word — so a slot that has respawned once
                                               * pays no score the next time it dies — and row 21
                                               * carries $3d */
#define WB_ACTOR_KIND_TYPE           0u       /* word: `move.w (a2)+,4(a0)` -> WB_ACTOR_TYPE */
#define WB_ACTOR_KIND_SPRITE         2u       /* word: `move.w (a2)+,6(a0)` -> WB_ACTOR_SPRITE */
#define WB_ACTOR_RESPAWN_FIELD_10    0x0au    /* `move.b #$a,10(a0)` */
#define WB_ACTOR_RESPAWN_SPEED       0x08u    /* `move.b #$8,11(a0)` — numerically
                                               * WB_ACTOR_FALL_SPEED_MAX, but a seeding rather than
                                               * a limit */
#define WB_ACTOR_RESPAWN_FIELD_12    0xc8u    /* `move.b #$c8,12(a0)` */
#define WB_ACTOR_RESPAWN_FIELD_30    0x08u    /* `move.b #$8,30(a0)` — WB_ACTOR_FIELD_30 alone; the
                                               * spawn clears the PAIR, this writes only the flag */
#define WB_ACTOR_RESPAWN_SIZE        0x40006u /* `move.l #$40006,14(a0)`: WB_ACTOR_HALF_WIDTH 4 and
                                               * WB_ACTOR_SIZE_SECOND 6, spelt inline where $ffe4
                                               * reads them out of WB_ACTOR_SIZE_TABLE */
#define WB_SPAWN_HITPOINT_TABLE      0x1011au /* word per type, immediately after WB_ACTOR_SIZE_TABLE
                                               * and the same 32 types wide. Indexed `add.w d1,d1`
                                               * on a zero-extended type, then `adda.l` — so the
                                               * index is a word and the ADD is a longword */
#define WB_SPAWN_HITPOINT_TABLE_ENTRIES 32u   /* == (0x1011a - 0x1009a) / 4: what pins the count is
                                               * the SIZE table BELOW, whose 32 longwords end where
                                               * this table starts. Above it there is room for 33 —
                                               * the next table's 4-byte records begin at 0x1015c
                                               * (`lea $1015c.l,a0` at $1a82), so the zero word at
                                               * 0x1015a belongs to neither table. The CODE bounds
                                               * the index at neither end */
#define WB_SPAWN_HITPOINT_TYPE_FIXED 0x3bu    /* `cmp.w #$3b,d1 / bne`: the one type that skips the
                                               * table for a constant */
#define WB_SPAWN_HITPOINT_FIXED_BASE 0x1eu    /* `addi.w #$1e,d0` on that arm */

/* ---- the per-actor BEHAVIOUR tier ($8d0, $928, $938; src/behavior.c) ---------------------------
 *
 * The whole tier hangs off four instructions. `actor_dispatch_behavior` reads WB_ACTOR_TYPE out of
 * the record, scales it `lsl.w #2` and tail-jumps through the longword table at
 * WB_ACTOR_BEHAVIOR_TABLE — a `lea (0x938,PC,d1.w),a1` whose base exists nowhere in the image as an
 * operand, which is why PORTABILITY.md §0k found 18,068 bytes behind it. `actor_behavior_pass` is
 * the walk that feeds it.
 */
#define WB_ACTOR_BEHAVIOR_TABLE      0x938u   /* 62 longwords, $938..$a2f, bounded above by its own
                                               * first target: slot 0 holds $a36 and the three
                                               * WB_STATE_FLAG_A30/A32/A34 words sit between */
#define WB_ACTOR_BEHAVIOR_SLOTS      62u      /* == (0xa30 - 0x938) / 4 */
#define WB_ACTOR_BEHAVIOR_ENTRY      4u       /* `lsl.w #2,d1` — a longword per slot */
#define WB_ACTOR_BEHAVIOR_NULL       0xa36u   /* slots 0 and 58 both hold it: a bare `rts`, and the
                                               * two bytes that bound the table */
/* The other reconstructed targets, as ADDRESSES — which is what src/behavior.c's dispatcher matches
 * on, because `movea.l (a1),a1` fetches the longword and a poked table entry is still followed. Each
 * is the entry ../names.txt gives the slot of the same number, and test/test_behavior.py pins all
 * sixty-two against the image rather than against this list. */
#define WB_ACTOR_BEHAVIOR_TYPE02     0x2462u
#define WB_ACTOR_BEHAVIOR_TYPE03     0x25c0u
#define WB_ACTOR_BEHAVIOR_TYPE04     0x2796u
#define WB_ACTOR_BEHAVIOR_TYPE05     0x29ecu
#define WB_ACTOR_BEHAVIOR_TYPE06     0x2bc8u
#define WB_ACTOR_BEHAVIOR_TYPE28     0x4e38u
#define WB_ACTOR_BEHAVIOR_TYPE29     0x4ec8u  /* TWO BYTES, a bare `rts` — the third slot in the
                                               * table that holds one, and the only one of the
                                               * three at an address of its own (slots 0 and 58
                                               * share WB_ACTOR_BEHAVIOR_NULL's $a36) */
#define WB_ACTOR_BEHAVIOR_TYPE30     0x4ecau
#define WB_ACTOR_BEHAVIOR_TYPE31     0x4f9cu  /* 78 bytes, NOT the 146 a scan that ran to the next
                                               * `rts` gives it: its last branch leaves the body for
                                               * actor_select_sprite_by_flag ($4fea), a routine of
                                               * its own with a second caller at $54d6 */
#define WB_ACTOR_BEHAVIOR_TYPE47     0x5928u
#define WB_ACTOR_BEHAVIOR_TYPE48     0x5972u
#define WB_ACTOR_BEHAVIOR_TYPE49     0x59d0u
#define WB_ACTOR_BEHAVIOR_TYPE50     0x5a6eu
#define WB_ACTOR_BEHAVIOR_TYPE51     0x5ab2u
#define WB_ACTOR_BEHAVIOR_TYPE52     0x5b3cu
#define WB_ACTOR_BEHAVIOR_TYPE53     0x5be4u
#define WB_ACTOR_BEHAVIOR_TYPE54     0x6e1cu
#define WB_ACTOR_BEHAVIOR_TYPE55     0x6ef4u
#define WB_ACTOR_BEHAVIOR_TYPE56     0x6f3eu
#define WB_ACTOR_BEHAVIOR_TYPE60     0x6f7eu
#define WB_ACTOR_BEHAVIOR_TYPE61     0x6f9eu
#define WB_ACTOR_BEHAVIOR_TYPE59     0x7044u
#define WB_ACTOR_BEHAVIOR_TYPE08     0x705au
#define WB_ACTOR_BEHAVIOR_TYPE07     0x7060u  /* the body slots 59 and 8 RUN INTO — behavior.c */
#define WB_ACTOR_TABLE_END           0xffffffffu /* `cmpi.l #$ffffffff,(a0)` — a LONGWORD test over
                                               * WB_ACTOR_X and WB_ACTOR_TYPE together, which is
                                               * what makes it distinct from WB_ACTOR_FREE_MARKER */
#define WB_ACTOR_BEHAVIOR_FIXED_SKIP 352u     /* `lea 352(a0),a0` == 11 * WB_ACTOR_RECORD_BYTES, the
                                               * jump from slot 1 to WB_ACTOR_FOLLOWED_SLOT that the
                                               * WB_STATE_FLAG_A34 arm makes */
#define WB_ACTOR_WALK_BUS_CYCLE      524288u  /* == (WB_BUS_ADDR_MASK + 1) / WB_ACTOR_RECORD_BYTES,
                                               * pinned equal in test/test_behavior.py. Not the
                                               * original's — see src/behavior.c's walk */

/* ---- the SPAWN animation ($698a, $69be; src/behavior.c) ---------------------------------------
 *
 * WB_ACTOR_FLAGS2_SPAWNED_BIT has exactly two operand sites in the whole image: the spawn raises it
 * and $698a clears it. Twenty-five handlers open by branching here while it is up, so a record that
 * has just been spawned plays this animation and does nothing else until it wraps.
 */
#define WB_ACTOR_SPAWN_ANIM_FRAMES   0x69beu  /* `lea $69be.l,a1` at $6994, the ONLY reference to any
                                               * address in the table anywhere in the image */
#define WB_ACTOR_SPAWN_ANIM_MASK     0x1fu    /* `andi.w #$1f,d0` on a BYTE OFFSET, so the cursor
                                               * reaches words 0..15 and the 32 bytes above them
                                               * ($69de..$69fd) have no reader at all */
#define WB_ACTOR_ANIM_FRAME_BYTES    2u       /* `addq.b #2,18(a0)` — one word per frame, and the
                                               * step every animation cursor in the tier takes */

/* ---- the shared leaves the handlers call (src/behavior.c) --------------------------------------
 *
 * Small routines with two to fourteen `bsr` sites each, spread across the 61 handlers. Every one is
 * entered with the actor record in a0 and several with a frame list in a1 or a band record in a2.
 */
#define WB_ACTOR_TIMER30_RELOAD      0x32u    /* `move.b #$32,30(a0)` — $2f86's reload */
#define WB_ACTOR_TIMER30_SPEED       0xau     /* `move.b #$a,11(a0)` on the frame it relaunches */
#define WB_ACTOR_TIMER30_RNG_BIT     2u       /* `btst #2,d0` on rng_next's word: SET vetoes the
                                               * relaunch, so it fires on about half the reloads */
#define WB_ACTOR_ANIM_LIST_ENTRY     4u       /* $3006's a1 is TWO longwords, one frame list per
                                               * facing: `movea.l (a1),a1` or `movea.l 4(a1),a1` */
#define WB_ACTOR_STEP_AWAY_PIXELS    4u       /* `move.w #$4,d7` — $2fe8's step, spelt inline */
#define WB_ACTOR_ANIM16_MASK         0xfu     /* `andi.b #$f,d0` — $5a3c's 16-byte wrap */
#define WB_ACTOR_ANIM_5160_FRAMES    0x5160u  /* THREE readers, by a whole-image scan of BOTH
                                               * absolute encodings: `lea $5160.w,a1` at $6872 and
                                               * at $58f8 (actor_behavior_type46, UNPORTED) and
                                               * `lea $5160.l,a1` at $5136 (slot 32). An earlier
                                               * revision said "its one reference" */
#define WB_ACTOR_ANIM_5160_END       0xffffu  /* `cmpi.w #$ffff,(a1)` after the post-increment */
#define WB_ACTOR_ANIM_5160_HOLD      1u       /* `cmpi.b #$1,30(a0) / beq` — the countdown stops on
                                               * this value rather than on zero */
#define WB_ACTOR_SPRITE_SUPPORTED    0x15au   /* $4fea's three sprite ids, by the two flag bits it */
#define WB_ACTOR_SPRITE_MOVING       0x158u   /* reads: WB_ACTOR_FLAG_SUPPORTED_BIT first, then */
#define WB_ACTOR_SPRITE_IDLE         0x157u   /* WB_ACTOR_FLAG_MOVING_BIT, else this one */
#define WB_ACTOR_SPRITE_TABLE_6ED8   0x6ed8u  /* `lea $6ed8.l,a2` at $6d60, its one reference —
                                               * VERIFIED by a whole-image scan of both absolute
                                               * encodings (batch 34): one long operand and no
                                               * word-aligned short one */
#define WB_ACTOR_SPRITE_6ED8_STRIDE  8u       /* `lsl.w #3,d0` on WB_ACTOR_HALF_WIDTH */
#define WB_ACTOR_FIELD_22_HOLD       3u       /* `move.b #$3,22(a0)` — $701c, on a NONZERO byte */

/* ---- the moving platform ($6d70, $6dd8; src/behavior.c) ----------------------------------------
 *
 * a0 is the platform's record, a1 the followed one and a2 a BAND record the caller supplies: 4(a2)
 * is how far left of the platform's x the band starts and 6(a2) how wide it is. $6d70 catches the
 * followed record onto the platform, $6dd8 lets it go again.
 */
#define WB_ACTOR_PLATFORM_RIDDEN     0x6ef0u  /* word: 1 while the followed record is being carried,
                                               * cleared when it leaves. Read at $6f42 */
#define WB_ACTOR_PLATFORM_TOP        0x10u    /* `subi.w #$10,d1` — the ride height above the y */
#define WB_ACTOR_PLATFORM_CATCH      0xau     /* `cmp.w #$a,d0 / bgt` — how far BELOW the top the
                                               * followed record may be and still be caught */
#define WB_ACTOR_BAND_LEFT           4u       /* word: the band's left edge, as a distance back */
#define WB_ACTOR_BAND_WIDTH          6u       /* word: added to it for the right edge */
#define WB_ACTOR_FIELD_22_RIDING_BIT 1u       /* `bset #1,22(a0)` while carrying, `bclr` on release */
#define WB_ACTOR_FLAG_MOVED_BIT      5u       /* "SOMETHING MOVED THIS RECORD ALONG x THIS FRAME",
                                               * which is the reading batch 40 replaced
                                               * WB_ACTOR_FLAG_CARRIED_BIT with. The platform's
                                               * `bset #5,8(a1)` at $6dcc is the only site in the
                                               * BEHAVIOUR tier, which is what the old name was read
                                               * off; the whole image has four more, all in the
                                               * player's own walk — `bset` on each of the two
                                               * direction arms ($fbc, $1028) and `bclr` on the
                                               * frame neither is held ($f7e). Its ONE reader is the
                                               * `btst #5,8(a0)` at $2184, inside code this port
                                               * does not have, so what the bit BUYS is still open */

/* ---- the two tests 42 and 25 handlers run every frame ($5c6e, $23b6; src/behavior.c) ----------
 *
 * $5c6e reports how the actor's box overlaps the FOLLOWED record's, as a three-bit mask in d0, and
 * $23b6 reports whether something the player threw has landed on it, as $ffff or 0 in d7. Between
 * them they are the whole of "did I hit, or was I hit" for the monster tier.
 */
#define WB_ACTOR_OVERLAP_STRIKE_BIT  0u       /* `bset #0,d0`: the small box in front of the followed
                                               * record, live only while its sprite is in the band */
#define WB_ACTOR_OVERLAP_BODY_BIT    1u       /* `bset #1,d0`: the two footprints overlap */
#define WB_ACTOR_OVERLAP_POINT_BIT   2u       /* `bset #2,d0`: one POINT off the followed record is
                                               * inside the actor's box, for two sprite ids only */
#define WB_FOLLOWED_SPRITE_STRIKE_LO 0x11eu   /* `cmp.w #$11e,d7 / blt` — the strike box's band, */
#define WB_FOLLOWED_SPRITE_STRIKE_HI 0x125u   /* `cmp.w #$125,d7 / bgt` — inclusive at both ends */
#define WB_FOLLOWED_SPRITE_STRIKE_FLIP 0x121u /* `cmp.w #$121,d7 / ble` — ABOVE this the box moves */
#define WB_ACTOR_STRIKE_BOX_NEAR     7u       /* `addq.w #7,d5` — the box's near edge off the x */
#define WB_ACTOR_STRIKE_BOX_FAR      0xdu     /* `addi.w #$d,d6` — and its far one */
#define WB_ACTOR_STRIKE_BOX_FLIP     0x14u    /* `subi.w #$14` off both, above the FLIP sprite */
#define WB_ACTOR_STRIKE_BOX_TOP      0xcu     /* `subi.w #$c,d5` off the followed y */
#define WB_ACTOR_STRIKE_BOX_DEPTH    6u       /* `addq.w #6,d5` back down for the box's bottom */
#define WB_FOLLOWED_SPRITE_POINT_LO  0x117u   /* the two sprite ids the POINT test runs for, and the
                                               * only two: `beq` on this one, `bne` out on the next */
#define WB_FOLLOWED_SPRITE_POINT_HI  0x118u
#define WB_ACTOR_POINT_RIGHT         0x16u    /* `addi.w #$16,d5` off the followed x... */
#define WB_ACTOR_POINT_FLIP          0x2cu    /* ...and `subi.w #$2c,d5` for POINT_HI, i.e. 22 the
                                               * other side */
#define WB_ACTOR_POINT_UP            9u       /* `subi.w #$9,d6` off the followed y */
#define WB_FLASH_TIMER               0x714u   /* word countdown flip_screen decrements; while it is
                                               * nonzero colour 0 is forced to $777. $23b8's
                                               * `tst.w $714.w` is its one reader outside that */
#define WB_ACTOR_FLASH_REACH         0x8cu    /* `move.w #$8c,d0 / bsr $67f8` — how close the
                                               * followed record must be while WB_FLASH_TIMER runs */
#define WB_ACTOR_SHOT_TYPE_LO        0x30u    /* `cmpi.w #$30,4(a1) / blt` — the WB_ACTOR_TYPE band */
#define WB_ACTOR_SHOT_TYPE_HI        0x32u    /* `cmpi.w #$32,4(a1) / bgt` — searched in the HIGH */
#define WB_ACTOR_SHOT_TYPE_KEPT      0x31u    /* alloc pool. This one is MARKED instead of freed */
#define WB_ACTOR_SHOT_HIT_MARK       1u       /* `move.b #$1,30(a1)` — the mark it gets instead */
#define WB_ACTOR_HIT                 0xffffu  /* `move.w #$ffff,d7` — $23b6's answer, in d7 */
#define WB_ACTOR_NOT_HIT             0u       /* `moveq #0,d7` — and its other one */

/* ---- what an actor does when a map step reports back ($2b5a, $2b82, $2b8e; src/actor.c) -------
 *
 * All three are entered with the two registers actor_step_left_against_map / _right leave: d0's low
 * BYTE is the step's outcome and d1's low word the ground flags. They differ only in which flag
 * they read and what they do about it, and all three share the `bchg #3,8(a0)` tail at $2b7a.
 */
#define WB_ACTOR_STEP_BLOCKED        0u       /* `tst.b d0`: the outcome byte is $0 when the step was
                                               * blocked and $ff when the first probe was clear */
#define WB_ACTOR_GROUND_STEP_UP_BIT  0u       /* $1 — the cell ahead is a block, the one above is not */
#define WB_ACTOR_GROUND_DROP_TWO_BIT 1u       /* $2 — two rows down is neither $1 nor $2 */
#define WB_ACTOR_GROUND_DROP_ONE_BIT 2u       /* $4 — one row down is neither */
#define WB_ACTOR_HOP_SPEED           4u       /* `move.w #$4,d0 / bsr $2af2` — $2b5a's step-up arm */
#define WB_ACTOR_TURN_LAUNCH_SPEED   7u       /* `move.b #$7,11(a0)` — $2b8e's, written inline */

/* ---- the two damage paths ($69fe, $6b46; src/actor.c) -----------------------------------------
 *
 * $69fe spends the hit ON the followed record: a charge off WB_HUD_SLOT_BBBE if it has one, else
 * WB_HUD_METER_VALUE. $6b46 spends it on the TEMPLATE's WB_SPAWN_HITPOINTS pool, doubled while
 * WB_HUD_SLOT_BBC0 has a charge. The two messages the emptied slots post name both slots — see
 * WB_TEXT_MSG_HELMET_BROKEN.
 */
#define WB_ACTOR_DAMAGE_TABLE        0x6b08u  /* `lea $6b08.l,a2` at $6a60: one word per spawn type,
                                               * how much the attacker takes off. It sits between
                                               * the two damage paths' bodies, and that `lea` is its
                                               * ONLY reference in the image */
#define WB_ACTOR_DAMAGE_TABLE_ENTRIES 31u     /* == ($6b46 - $6b08) / 2: the table runs from its own
                                               * `lea` to the first byte of $6b46, which 25 control
                                               * -flow sites enter. The CODE bounds the index at
                                               * neither end */
#define WB_ACTOR_DAMAGE_INLINE_MASK  0x7fu    /* `bclr #7,d0`: a WB_ACTOR_TEMPLATE_SLOT byte with its
                                               * sign bit set carries the damage in these bits
                                               * itself, and no table is read at all */
#define WB_ACTOR_DAMAGE_FIELD_31_BASE 0xcu    /* `move.w #$c,d1 / sub.w d0,d1` — WB_ACTOR_FIELD_31
                                               * becomes this minus twice WB_EFFECT_STATE_BD66 */
#define WB_ACTOR_DAMAGE_FLICKER_FRAMES 0x64u  /* into WB_ACTOR_FLICKER_COUNTDOWN, and only on the arm
                                               * that spends the meter */
#define WB_ACTOR_DAMAGE_FIELD_30_SET 0xffu    /* into WB_ACTOR_FIELD_30 on the side the x compare
                                               * raises WB_ACTOR_FLAG_SIDE_BIT for; the other arm
                                               * clears the byte */
#define WB_ACTOR_DAMAGE_KNOCKBACK_SPEED 5u    /* `move.b #$5,11(a1)` — the speed the hit launches the
                                               * record at, spelt inline as $2b8e's is */
#define WB_ACTOR_DAMAGE_FOLLOWED_SFX 0xbu     /* `move.w #$b,d0 / clr.w d1` */
#define WB_ACTOR_DAMAGE_TEMPLATE_SFX 0x13u    /* `move.w #$13,d0 / move.w #$1,d1` — and that d1 is
                                               * WB_SND_CHANNEL_B */

/* ---- the STUN ($6796; src/behavior.c) ---------------------------------------------------------
 *
 * Eleven behaviour handlers reach it by `bsr.w`. It fires one sound effect and then stamps a step
 * count into the FOLLOWED record — the same `n - 2 * <state word>` shape $69fe uses on
 * WB_ACTOR_FIELD_31, over the other state word.
 */
#define WB_ACTOR_ST_BYTE             0xffu    /* `st d16(a0)` — the 68000's own "set true" byte, and
                                               * what slots 51 and 6 stamp their two flag bytes with */
#define WB_ACTOR_STUN_SFX            8u       /* `move.w #$8,d0 / clr.w d1` — channel A */
#define WB_ACTOR_REQUEST9_SFX        9u       /* `move.w #$9,d0 / clr.w d1` — $6786's, the same
                                               * four instructions one request higher */
#define WB_ACTOR_STUN_STEPS_BASE     0xau     /* `move.w #$a,d1 / sub.w d0,d1` over twice
                                               * WB_EFFECT_STATE_BD68, into WB_ACTOR_FIELD_29 */
#define WB_ACTOR_FIELD_29            29u      /* byte: a STEP COUNT. $ec8 runs it down one map step
                                               * at a time on the player's record; $6796 seeds it and
                                               * behaviour slot 6 uses it as a one-frame save slot
                                               * for WB_ACTOR_FLAGS */

/* ---- the moving-platform handlers (slots 54, 55, 56; src/behavior.c) --------------------------
 *
 * All three open with $6d5a, so their a2 is the WB_ACTOR_SPRITE_TABLE_6ED8 row
 * WB_ACTOR_HALF_WIDTH names — the band record $6d70/$6dd8 read is that same row's second and third
 * words, which is what makes 14(a0) a PLATFORM SIZE rather than a footprint here. 16(a0) is the
 * travel LIMIT and 24(a0) the cursor against it.
 */
#define WB_ACTOR_FIELD_24            24u      /* word: how far along its travel the platform is —
                                               * and, at the same offset for a different tier, the
                                               * swoop's PATH CURSOR (an offset from
                                               * WB_ACTOR_SWOOP_PATHS, not an address). A THIRD
                                               * TIER READS IT AS A BYTE: $ec8's walk accelerator
                                               * counts `addq.b #1 / andi.b #$3` in it, so a port
                                               * that modelled a word here would take the mask
                                               * across the high half (see "THE WALK") */
#define WB_ACTOR_FIELD_22_DIRECTION_BIT 0u    /* `btst #0,22(a0)`: set = the platform is travelling
                                               * back (up for slot 54, left for slot 55) */
#define WB_ACTOR_PLATFORM_STEP       2u       /* `subq.w #2` / `addq.w #2` — pixels a frame, and the
                                               * same 2 the travel cursor counts in */
#define WB_ACTOR_PLATFORM_SINK_TICK  1u       /* slot 56 counts its cursor in ONES while moving the
                                               * same 2 pixels, so 24(a0) is a frame count there */

/* ---- the first monster handlers (slots 2..6, 50, 51; src/behavior.c) --------------------------
 *
 * Slots 2..6 share a shape: the spawn-animation gate, then "was I hit", then a per-monster move,
 * then a frame published out of a PC-relative or absolute word table. Bit 0 of WB_ACTOR_FLAGS2 is
 * the switch between the live body and the death animation each of them ends with.
 *
 * EVERY TABLE BELOW IS WORD DATA INSIDE ITS OWN HANDLER'S EXTENT, and each is named for the slot
 * that reads it and the facing it is read for. A cursor is WB_ACTOR_FIELD_18 (or WB_ACTOR_FIELD_30
 * for the hover), stepped WB_ACTOR_ANIM_FRAME_BYTES at a time and wrapped by the mask beside it.
 */
/* The eight-word tables wrap on WB_ACTOR_ANIM16_MASK — the same 16 BYTES $5a3c's own step names,
 * which is why no second `#define` of $f appears here. The sixteen-word ones wrap on: */
#define WB_ACTOR_ANIM32_MASK         0x1fu    /* `andi #$1f` — a 32-byte, sixteen-word table */

#define WB_ACTOR_TYPE02_WALK_LEFT    0x25a0u  /* 8 words each. The LEFT pair is chosen when the */
#define WB_ACTOR_TYPE02_WALK_RIGHT   0x25b0u  /* followed record's x is not above the actor's */
#define WB_ACTOR_TYPE02_DEAD_LEFT    0x2560u  /* 16 words each, and the only two tables in these */
#define WB_ACTOR_TYPE02_DEAD_RIGHT   0x2580u  /* five handlers reached by `lea d8(PC,Dn.w)` */
#define WB_ACTOR_TYPE02_DEAD_STEP    3u       /* `move.w #$3,d7` — the recoil, in pixels */

#define WB_ACTOR_TYPE03_WALK_LEFT    0x2736u  /* 8 words each */
#define WB_ACTOR_TYPE03_WALK_RIGHT   0x2746u
#define WB_ACTOR_TYPE03_DEAD_RIGHT   0x2756u  /* 8 words each, and FOUR of them: the arm that is */
#define WB_ACTOR_TYPE03_DEAD_LEFT    0x2766u  /* still stepping has its own pair, the one already */
#define WB_ACTOR_TYPE03_HELD_LEFT    0x2776u  /* defeated another */
#define WB_ACTOR_TYPE03_HELD_RIGHT   0x2786u
#define WB_ACTOR_TYPE03_TURN_FRAMES  0x46u    /* `move.b #$46,30(a0)` — frames between turns */
#define WB_ACTOR_TYPE03_WALK_STEP    2u       /* `move.w #$2,d7`, and `move.b #$2,d7` on the left */
#define WB_ACTOR_TYPE03_DEAD_STEP    4u

#define WB_ACTOR_TYPE04_DEAD_RIGHT   0x28ecu  /* 16 words each, reached by `lea d8(PC,Dn.w)` */
#define WB_ACTOR_TYPE04_DEAD_LEFT    0x290cu
#define WB_ACTOR_TYPE04_FLY_LEFT     0x292cu  /* 16 words each */
#define WB_ACTOR_TYPE04_FLY_RIGHT    0x294cu
#define WB_ACTOR_TYPE04_HOVER        0x296cu  /* 64 SIGNED words added to the y, one a frame — the
                                               * only table in these handlers that is not a sprite
                                               * list, and the only one WB_ACTOR_FIELD_30 indexes */
#define WB_ACTOR_TYPE04_HOVER_MASK   0x7fu    /* `andi.b #$7f` — 128 bytes, so the whole table */
#define WB_ACTOR_TYPE04_FLY_PUBLISH  0x2840u  /* INSIDE slot 4's body: the publish-and-hover tail
                                               * slot 23's `bra.w $2840` at $46fe enters, so these
                                               * instructions are not slot 4's alone */
#define WB_ACTOR_CHASE_REACH         0xc8u    /* `move.w #$c8,d0 / bsr $67f8` — how close the
                                               * followed record must be before a monster reacts.
                                               * TWO slots spell the same $c8 — slot 4 chases inside
                                               * it and slot 6 charges — so it is named for the test
                                               * and not for either handler */
#define WB_ACTOR_TYPE04_FLY_STEP     1u
#define WB_ACTOR_TYPE04_DEAD_STEP    4u

#define WB_ACTOR_TYPE05_HOP_LEFT     0x2b0au  /* 16 words each */
#define WB_ACTOR_TYPE05_HOP_RIGHT    0x2b2au
#define WB_ACTOR_TYPE05_DEAD         0x2b4au  /* 8 words, and ONE table for both facings */
#define WB_ACTOR_TYPE05_HOP_STEP     1u
#define WB_ACTOR_TYPE05_DEAD_STEP    4u

#define WB_ACTOR_TYPE06_WALK_LEFT    0x2db2u  /* 16 words each */
#define WB_ACTOR_TYPE06_WALK_RIGHT   0x2dd2u
#define WB_ACTOR_TYPE06_DEAD_RIGHT   0x2df2u  /* 8 words each */
#define WB_ACTOR_TYPE06_DEAD_LEFT    0x2e02u
#define WB_ACTOR_TYPE06_SPRITE_LEFT  0x66u    /* the two frames it holds while AIRBORNE (bit 2 of */
#define WB_ACTOR_TYPE06_SPRITE_RIGHT 0x6bu    /* the flag byte down), published straight rather than
                                               * out of a table. It throws on the frame it lands */
#define WB_ACTOR_TYPE06_CHARGE_SPEED 6u       /* `move.w #$6,d0 / bsr $2af2` */
#define WB_ACTOR_TYPE06_RELOAD       0x46u    /* `move.b #$46,30(a0)` — frames before it may throw */
#define WB_ACTOR_TYPE06_WALK_STEP    2u
#define WB_ACTOR_TYPE06_DEAD_STEP    4u
#define WB_ACTOR_TYPE06_SHOT_TYPE    0x28u    /* `move.w #$28,4(a1)` — what it spawns */
#define WB_ACTOR_TYPE06_SHOT_UP      6u       /* `subq.w #6,2(a1)` off the copied y */
#define WB_ACTOR_TYPE06_SHOT_AHEAD   0xau     /* `move.w #$a,d0` / `#$fff6` — and to its left */
#define WB_ACTOR_TYPE06_SHOT_BEHIND  0xfff6u
#define WB_ACTOR_TYPE06_SHOT_SIZE    0xc0002u /* `move.l #$c0002,14(a1)`: WB_ACTOR_HALF_WIDTH $c and
                                               * WB_ACTOR_SIZE_SECOND $2 in one store */

/* ---- the MONSTER-PROLOGUE family, dispatch rows 9..13 (batch 35; src/behavior.c) ---------------
 *
 * Slots 2..6's grammar with five more middles: the same spawn gate, the same contact enum, the same
 * `bset #0,9(a0) / clr.b 18(a0)` before the tail jump, and a HURT animation that ends
 * `bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8`.
 *
 * EVERY TABLE BELOW HAS EXACTLY ONE OPERAND SITE IN THE WHOLE IMAGE, by a scan of both absolute
 * encodings AND of the `lea d8(PC,Dn.w)` displacement, run for every address here — the census
 * discipline the $5160 miss bought. Two addresses inside the band have NO site at all and are
 * therefore unreachable duplicates: $338c and $33ac each repeat the sixteen bytes below
 * WB_ACTOR_TYPE11_HURT_MARKED / _PLAIN, whose cursor never leaves WB_ACTOR_ANIM16_MASK.
 */
#define WB_ACTOR_BEHAVIOR_TYPE09     0x2e12u  /* 152 bytes of code, $2e12..$2ea9 */
#define WB_ACTOR_BEHAVIOR_TYPE10     0x303au  /* 350, $303a..$3197 */
#define WB_ACTOR_BEHAVIOR_TYPE11     0x3218u  /* 324, $3218..$335b */
#define WB_ACTOR_BEHAVIOR_TYPE12     0x33bcu  /* 174, $33bc..$3469 */
#define WB_ACTOR_BEHAVIOR_TYPE13     0x34d2u  /* 246, $34d2..$35c7 */

/* $2f46, the family's own leaf: ONE `bsr` caller, slot 9's walk. */
#define WB_ACTOR_RANDOM_HOP_RNG_BIT  2u       /* `btst #2,d0` on rng_next's word: CLEAR faces LEFT
                                               * (`bset #3,8(a0)`), SET faces right */
#define WB_ACTOR_RANDOM_HOP_SPEED    0xau     /* `move.b #$a,11(a0)`. The same byte
                                               * WB_ACTOR_TIMER30_SPEED names at $2fc2 — two names
                                               * because they are two ADDRESSES */

/* $3006 list PAIRS: two longwords each, the LEFT list first (bit 3 of 8(a0) set picks it). */
#define WB_ACTOR_TYPE09_WALK_LISTS   0x2eaau  /* -> $2eba / $2edc, 16 words + a $ffff terminator */
#define WB_ACTOR_TYPE09_HURT_LISTS   0x2eb2u  /* -> $2efe / $2f10, 8 words + a terminator */
#define WB_ACTOR_TYPE09_WALK_STEP    3u       /* `move.w #$3,d7` into actor_step_facing */

#define WB_ACTOR_TYPE10_HOVER        0x31d8u  /* 32 SIGNED words added to the y, one a frame —
                                               * $fffe..$0002 and back, indexed by
                                               * WB_ACTOR_FIELD_31 */
#define WB_ACTOR_TYPE10_HOVER_MASK   0x3fu    /* `andi.b #$3f` — 64 bytes, so the whole table */
#define WB_ACTOR_TYPE10_CLOSE_STEP   2u       /* `move.w #$2,d0` / `neg.w d0` — the vertical close
                                               * taken ONCE per hover cycle */
#define WB_ACTOR_TYPE10_DRIFT_STEP   1u       /* `addq.w #1,(a0)` / `subq.w #1,(a0)` every frame */
#define WB_ACTOR_TYPE10_TURN_FRAMES  0x64u    /* `move.b #$64,30(a0)` — frames between turns */
#define WB_ACTOR_TYPE10_HOME_STEP    1u       /* `move.w #$1,d7 / bsr $6840` on the turn frame */
#define WB_ACTOR_TYPE10_WALK_LEFT    0x3198u  /* 8 words each, wrapped by WB_ACTOR_ANIM16_MASK */
#define WB_ACTOR_TYPE10_WALK_RIGHT   0x31a8u
#define WB_ACTOR_TYPE10_HURT_LEFT    0x31b8u
#define WB_ACTOR_TYPE10_HURT_RIGHT   0x31c8u
#define WB_ACTOR_TYPE10_HURT_STEP    4u       /* `move.w #$4,d7`, and the step is AWAY */

#define WB_ACTOR_TYPE11_RELOAD       0x19u    /* `move.b #$19,30(a0)` — frames between decisions */
#define WB_ACTOR_TYPE11_HOP_SPEED    9u       /* `move.w #$9,d0 / bra.w $2af2` */
#define WB_ACTOR_TYPE11_FACE_RNG_BIT 2u       /* `btst #2,d0`: SET faces LEFT, which is the OPPOSITE
                                               * reading to WB_ACTOR_RANDOM_HOP_RNG_BIT's */
#define WB_ACTOR_TYPE11_HOP_RNG_BIT  1u       /* `btst #1,d0`: SET vetoes the hop */
#define WB_ACTOR_TYPE11_WALK_STEP    2u       /* `move.w #$2,d7`, spelt in BOTH arms */
#define WB_ACTOR_TYPE11_WALK_LEFT    0x335cu  /* 8 words each, wrapped by WB_ACTOR_ANIM16_MASK */
#define WB_ACTOR_TYPE11_WALK_RIGHT   0x336cu
#define WB_ACTOR_TYPE11_HURT_MARKED  0x337cu  /* the hurt pair, and the ONE table select in the
                                               * family that reads WB_ACTOR_FIELD_30 rather than */
#define WB_ACTOR_TYPE11_HURT_PLAIN   0x339cu  /* WB_ACTOR_FLAG_SIDE_BIT */
#define WB_ACTOR_TYPE11_HURT_BIT     3u       /* `btst #3,30(a0)` — bit 3 of the countdown byte the
                                               * live arm reloads with WB_ACTOR_TYPE11_RELOAD */

#define WB_ACTOR_TYPE12_WALK_STEP    2u       /* `move.w #$2,d7` into actor_face_and_step_toward */
#define WB_ACTOR_TYPE12_GROUND_LISTS 0x346au  /* $3482/$3494, 8 words + a terminator each: the walk,
                                               * played while WB_ACTOR_FLAG_SUPPORTED_BIT is up */
#define WB_ACTOR_TYPE12_AIR_LISTS    0x3472u  /* $34a6/$34aa, ONE word + a terminator each: the
                                               * single frame it holds while airborne */
#define WB_ACTOR_TYPE12_HURT_LISTS   0x347au  /* $34ae/$34c0, 8 words + a terminator each */

#define WB_ACTOR_TYPE13_FRAMES       0x35c8u  /* 8 words, and the whole of this handler's data */
#define WB_ACTOR_TYPE13_HOP_SPEED    0xcu     /* `move.b #$c,11(a0)` — relaunched on EVERY frame it
                                               * is supported, with no countdown and no draw */
#define WB_ACTOR_TYPE13_DEATH_FRAMES 0x19u    /* `move.b #$19,31(a0)` — how long the throe runs */
#define WB_ACTOR_TYPE13_DEATH_SPEED  6u       /* `move.b #$6,11(a0)` on the throe's first frame */
#define WB_ACTOR_TYPE13_HURT_STEP    2u       /* `move.w #$2,d7`, and the step is AWAY */
#define WB_ACTOR_TYPE13_HURT_SPRITE  0x37u    /* `move.w #$37,6(a0)` — published straight, every
                                               * frame of the throe */
#define WB_ACTOR_TYPE13_DYING        0xffu    /* `st 30(a0)` — the byte the throe's own head tests,
                                               * so the setup runs on its FIRST frame only */

/* ---- the family CONTINUES, dispatch rows 14..19 (batch 36; src/behavior.c) ----------------------
 *
 * Six more middles inside the same grammar, and three things the first block did not have.
 *
 *   * THE HURT TAIL COMES IN THREE ORDERS. Slots 14, 17, 18 lower WB_ACTOR_FLAGS2_BIT_0 and TEST
 *     the defeated bit (batch 35's `monster_hurt_wrap_clear_then_test`); slots 15 and 16 test FIRST and
 *     lower bit 0 only when the mark is down, so a record that transfers keeps BOTH marks. Slot 19
 *     transfers unconditionally, as slot 13 does.
 *   * FIVE OF THE SIX SPAWN. Each takes a record from actor_alloc_slot_high, fills it from its own
 *     x/y longword and a type, and ends its frame there whether the pool answered or not.
 *   * TWO OF THEM SPLIT THE STRUCK ARM. Slots 18 and 19 call actor_set_side_flag on the overlap
 *     POINT arm and NOT on the shot's — which is why src/behavior.c's `monster_contact` reports
 *     WHICH test struck. Batch 37 found four more (20, 21, 25 and 27), so the split is a third of
 *     the family rather than these two handlers' peculiarity.
 *
 * EVERY TABLE BELOW HAS EXACTLY ONE OPERAND SITE IN THE WHOLE IMAGE, by a scan of both absolute
 * encodings AND of the `lea d8(PC,Dn.w)` displacement; the four lists behind slot 17's two PAIRS
 * ($3b78, $3b8a, $3b9c, $3bae) have NONE, because a pair is two longwords and $3006 dereferences
 * them. WB_ACTOR_TYPE17_DX_CURSOR and _DY_CURSOR have TWO sites each — one read, one write.
 */
#define WB_ACTOR_BEHAVIOR_TYPE14     0x35d8u  /* 316 bytes of code, $35d8..$3713 */
#define WB_ACTOR_BEHAVIOR_TYPE15     0x3764u  /* 234, $3764..$384d */
#define WB_ACTOR_BEHAVIOR_TYPE16     0x38aeu  /* 312, $38ae..$39e5 */
#define WB_ACTOR_BEHAVIOR_TYPE17     0x3a46u  /* 290, $3a46..$3b67 */
#define WB_ACTOR_BEHAVIOR_TYPE18     0x3c84u  /* 424, $3c84..$3e2b */
#define WB_ACTOR_BEHAVIOR_TYPE19     0x3e8cu  /* 364, $3e8c..$3ff7 */

/* `move.l #$60006,14(a1)` — WB_ACTOR_HALF_WIDTH 6 and WB_ACTOR_SIZE_SECOND 6 in ONE store, the
 * shape WB_ACTOR_TYPE06_SHOT_SIZE also has. Three of this batch's five spawners write it. */
#define WB_ACTOR_MINION_SIZE     0x60006u
#define WB_ACTOR_MINION_SPEED        9u       /* `move.b #$9,11(a1)` — slots 16 and 18 */

#define WB_ACTOR_TYPE14_WALK_LEFT    0x3714u  /* 16 words each, wrapped by WB_ACTOR_ANIM32_MASK */
#define WB_ACTOR_TYPE14_WALK_RIGHT   0x3734u
#define WB_ACTOR_TYPE14_HURT         0x3754u  /* 8 words, ONE table for both facings */
#define WB_ACTOR_TYPE14_WALK_STEP    1u       /* `move.b #$1,d7` on the LEFT arm, `move.w` right */
#define WB_ACTOR_TYPE14_TURN_FRAMES  0x46u    /* `move.b #$46,30(a0)` on the turn frame */
#define WB_ACTOR_TYPE14_SPAWN_GAP    0x1eu    /* `move.b #$1e,31(a0)` — walking frames between drops,
                                               * written only when the pool answered */
#define WB_ACTOR_TYPE14_MINION_TYPE  0x2du
#define WB_ACTOR_TYPE14_MINION_TIMER 0x32u    /* `move.b #$32,30(a1)` — the drop's own countdown */

#define WB_ACTOR_TYPE15_WALK_RIGHT   0x384eu  /* 8 words each, wrapped by WB_ACTOR_ANIM16_MASK and
                                               * stepped IN MEMORY (`addq.b`/`andi.b` on 18(a0)) */
#define WB_ACTOR_TYPE15_WALK_LEFT    0x385eu
#define WB_ACTOR_TYPE15_HURT_RIGHT   0x386eu  /* 16 words each, wrapped by WB_ACTOR_ANIM32_MASK and
                                               * stepped in a REGISTER — the two arms differ */
#define WB_ACTOR_TYPE15_HURT_LEFT    0x388eu
#define WB_ACTOR_TYPE15_WALK_STEP    4u       /* `move.w #$4,d7` in BOTH arms */

#define WB_ACTOR_TYPE16_WALK_LEFT    0x39e6u  /* 8 words each, wrapped by WB_ACTOR_ANIM16_MASK */
#define WB_ACTOR_TYPE16_WALK_RIGHT   0x39f6u
#define WB_ACTOR_TYPE16_HURT_LEFT    0x3a06u  /* 16 words each */
#define WB_ACTOR_TYPE16_HURT_RIGHT   0x3a26u
#define WB_ACTOR_TYPE16_RELOAD       0x32u    /* `move.b #$32,30(a0)` — frames between hops */
#define WB_ACTOR_TYPE16_HOP_SPEED    9u       /* `move.b #$9,11(a0)`, spelt inline */
#define WB_ACTOR_TYPE16_MINION_TYPE  0x27u    /* the record the hop drops */

#define WB_ACTOR_TYPE17_LIVE_LISTS   0x3b68u  /* $3006 PAIRS: -> $3b78 / $3b8a, 8 words each plus a
                                               * $ffff terminator */
#define WB_ACTOR_TYPE17_HURT_LISTS   0x3b70u  /* -> $3b9c / $3bae, same shape */
#define WB_ACTOR_TYPE17_DX_CURSOR    0x3bc0u  /* GLOBAL words, not record fields: every live type-17
                                               * record steps the same pair, so two of them drift in
                                               * lockstep. WB_ACTOR_TYPE30_CURSOR and
                                               * WB_ACTOR_TYPE32_CURSOR are the tier's two */
#define WB_ACTOR_TYPE17_DY_CURSOR    0x3bc2u  /* others */
#define WB_ACTOR_TYPE17_DX           0x3bc4u  /* 64 SIGNED words added to the x, one a frame */
#define WB_ACTOR_TYPE17_DX_MASK      0x7fu    /* `andi.w #$7f` — the whole 128-byte table */
#define WB_ACTOR_TYPE17_DY           0x3c44u  /* 32 SIGNED words added to the y */
#define WB_ACTOR_TYPE17_DY_MASK      0x3fu    /* ...so the y cycle is HALF the x one, and the seeding
                                               * below fires on the frame it wraps */
#define WB_ACTOR_TYPE17_SEED_BURST   0x3ae6u  /* INSIDE slot 17's body: the seeding block slot 24's
                                               * `bra.w $3ae6` at $48b2 enters as its own tail */
#define WB_ACTOR_TYPE17_SEED_ODDS_MASK 7u     /* `andi.w #$7,d0 / bne` on rng_next's word */
#define WB_ACTOR_TYPE17_SEED_DBF_COUNT 4u    /* `move.w #$4,d7` — a `dbf` counter, which runs its
                                               * body COUNT + 1 times, so FIVE records */
#define WB_ACTOR_TYPE17_SEED_FIRST   5u       /* `move.w #$5,d6`, stored into 30(a1) and counted
                                               * DOWN, so the five carry 5, 4, 3, 2, 1 */
#define WB_ACTOR_TYPE17_SEED_TYPE    0x34u
#define WB_ACTOR_TYPE17_SEED_SIZE    0x60008u /* WB_ACTOR_HALF_WIDTH 6, WB_ACTOR_SIZE_SECOND 8 */
#define WB_ACTOR_TYPE17_SEED_SPEED   8u

#define WB_ACTOR_TYPE18_WALK_LEFT    0x3e2cu  /* 16 words each */
#define WB_ACTOR_TYPE18_WALK_RIGHT   0x3e4cu
#define WB_ACTOR_TYPE18_HURT_LEFT    0x3e6cu  /* 8 words each */
#define WB_ACTOR_TYPE18_HURT_RIGHT   0x3e7cu
#define WB_ACTOR_TYPE18_WALK_STEP    2u       /* `move.b #$2,d7` left, `move.w #$2,d7` right */
#define WB_ACTOR_TYPE18_HURT_STEP    4u       /* `move.w #$4,d7`, and the step is AWAY */
#define WB_ACTOR_TYPE18_CHARGING     0xffu    /* `move.b #$ff,31(a0)` — the latch that says the
                                               * record is mid-charge, cleared when it lands */
#define WB_ACTOR_TYPE18_HOP_SPEED    9u       /* `move.w #$9,d0 / bsr $2af2` */
#define WB_ACTOR_TYPE18_MINION_TYPE  0x29u
#define WB_ACTOR_TYPE18_TURN_FRAMES  0x46u    /* `move.b #$46,30(a0)` when the charge ends */

#define WB_ACTOR_TYPE19_DRIFT        0x3ff8u  /* 64 SIGNED words added to the x while the record
                                               * glides, indexed by WB_ACTOR_FIELD_30 */
#define WB_ACTOR_TYPE19_DRIFT_MASK   0x7fu
#define WB_ACTOR_TYPE19_GLIDE_SPRITE 0xa2u    /* `move.w #$a2,6(a0)` — one frame for the whole
                                               * glide, published every frame of it */
#define WB_ACTOR_TYPE19_GLIDE_HEIGHT 8u       /* WB_ACTOR_SIZE_SECOND while gliding... */
#define WB_ACTOR_TYPE19_ATTACK_HEIGHT 0x10u   /* ...and once the record drops into its attack */
#define WB_ACTOR_TYPE19_PHASE2       0xffu    /* `st 31(a0)` on the frame the drift cursor wraps */
#define WB_ACTOR_TYPE19_FRAMES_RIGHT 0x4078u  /* 32 words each, wrapped by WB_ACTOR_TYPE19_FRAME_MASK */
#define WB_ACTOR_TYPE19_FRAMES_LEFT  0x40b8u
#define WB_ACTOR_TYPE19_FRAME_MASK   0x3fu
#define WB_ACTOR_TYPE19_DEATH        0x40f8u  /* 16 words, ONE table for both facings */
#define WB_ACTOR_TYPE19_SHOT_CURSOR  0x14u    /* `cmp.w #$14,d7` — the ONE cursor value that fires */
#define WB_ACTOR_TYPE19_SHOT_TYPE    0x2bu
#define WB_ACTOR_TYPE19_SHOT_RISE    6u       /* `subq.w #6,2(a1)` off the parent's y */
#define WB_ACTOR_TYPE19_SHOT_DX_RIGHT 0xau    /* ...and `add.w d0,(a1)` on the x, the side flag */
#define WB_ACTOR_TYPE19_SHOT_DX_LEFT 0xfff6u  /* picking which */
#define WB_ACTOR_TYPE19_SHOT_SIZE    0xc0002u /* WB_ACTOR_HALF_WIDTH $c, WB_ACTOR_SIZE_SECOND $2 */

/* ---- the family CLOSES, dispatch rows 20..27 (batch 37; src/behavior.c) -------------------------
 *
 * The last eight middles of the monster family, and what they add is REUSE rather than grammar:
 *
 *   * SLOT 20 AND SLOT 27 ARE THE SAME 378 BYTES TWICE. Every instruction of $4118..$4291 is
 *     repeated at $4c5e..$4dd7 with four table addresses and two airborne sprite ids changed, so
 *     one C body serves both rows and a `WB_ACTOR_TYPE20_TABLES`-shaped argument carries the six.
 *   * SLOT 23 IS SLOT 4 WITH A DIFFERENT CONTACT ARM, and it does not merely resemble it: the
 *     `bra.w $2840` at $46fe LEAVES this band and lands INSIDE actor_behavior_type04's body, so one
 *     of slot 23's own live-arm paths executes slot 4's publish-and-hover tail. It also reads slot
 *     4's hover table through the SHORT absolute encoding (`lea $296c.w` at $4746) where slot 4
 *     uses the long one — the second operand site of an address whose plate said it had one.
 *   * SLOT 25 IS SLOT 18's CHARGE, and slot 26 is slot 12's chase, each with its own tables.
 *   * SLOT 24 LEAVES FOR SLOT 17 (`bra.w $3ae6` at $48b2, type17_seed_burst) and slot 25 borrows
 *     slot 18's `rts` (`bne.w $3e2a` at $4aa8) — the two inbound edges batch 36 pinned from the
 *     other side.
 *   * FOUR MORE HANDLERS SPLIT THE STRUCK ARM (20, 21, 25, 27), so the split is no longer two
 *     handlers' peculiarity but a third of the family.
 *
 * EVERY TABLE BELOW HAS EXACTLY ONE OPERAND SITE IN THE WHOLE IMAGE, by a scan of both absolute
 * encodings AND of both PC-relative `lea` forms — except slot 23's, which shares slot 4's hover and
 * whose two dead-frame tables are named by `lea d16(PC,Dn.w)` out of slot 23's own body.
 */
#define WB_ACTOR_BEHAVIOR_TYPE20     0x4118u  /* 378 bytes of code, $4118..$4291 */
#define WB_ACTOR_BEHAVIOR_TYPE21     0x42f2u  /* 362, $42f2..$445b */
#define WB_ACTOR_BEHAVIOR_TYPE22     0x44bcu  /* 264, $44bc..$45c3 */
#define WB_ACTOR_BEHAVIOR_TYPE23     0x461cu  /* 432, $461c..$47cb */
#define WB_ACTOR_BEHAVIOR_TYPE24     0x484cu  /* 150, $484c..$48e1 */
#define WB_ACTOR_BEHAVIOR_TYPE25     0x4916u  /* 424, $4916..$4abd */
#define WB_ACTOR_BEHAVIOR_TYPE26     0x4b1eu  /* 216, $4b1e..$4bf5 */
#define WB_ACTOR_BEHAVIOR_TYPE27     0x4c5eu  /* 378, $4c5e..$4dd7 — slot 20's body again */

/* Slots 20 and 27, whose ONE body reads six of these twelve at a time. LEFT is the table the
 * `btst #3,8(a0) / bne` arm reaches, i.e. the one played while WB_ACTOR_FLAG_SIDE_BIT is SET. */
#define WB_ACTOR_TYPE20_WALK_LEFT    0x4292u  /* 8 words each, wrapped by WB_ACTOR_ANIM16_MASK */
#define WB_ACTOR_TYPE20_WALK_RIGHT   0x42a2u
#define WB_ACTOR_TYPE20_HURT_LEFT    0x42b2u  /* 16 words each, WB_ACTOR_ANIM32_MASK */
#define WB_ACTOR_TYPE20_HURT_RIGHT   0x42d2u
#define WB_ACTOR_TYPE20_AIR_LEFT     0x30u    /* `move.w #$30,6(a0)` — an AIRBORNE record publishes
                                               * one constant instead of animating */
#define WB_ACTOR_TYPE20_AIR_RIGHT    0x34u
#define WB_ACTOR_TYPE27_WALK_LEFT    0x4dd8u  /* ...and the same six for slot 27 */
#define WB_ACTOR_TYPE27_WALK_RIGHT   0x4de8u
#define WB_ACTOR_TYPE27_HURT_LEFT    0x4df8u
#define WB_ACTOR_TYPE27_HURT_RIGHT   0x4e18u
#define WB_ACTOR_TYPE27_AIR_LEFT     0x1au
#define WB_ACTOR_TYPE27_AIR_RIGHT    0x1eu
/* The seven values the shared body spells inline. They are ONE set because the two bodies are byte
 * for byte the same everywhere but the twelve addresses above and the two sprite ids. */
#define WB_ACTOR_TYPE20_WALK_STEP    2u       /* `move.w #$2,d7`, a WORD in BOTH arms */
#define WB_ACTOR_TYPE20_HURT_STEP    4u       /* `move.w #$4,d7`, and the step is AWAY */
#define WB_ACTOR_TYPE20_HOP_RELOAD   0x32u    /* `move.b #$32,30(a0)` the frame the countdown goes
                                               * negative */
#define WB_ACTOR_TYPE20_HOP_RNG_BIT  2u       /* `btst #2,d0 / bne` on rng_next's word VETOES the
                                               * launch, so it fires on half the reloads */
#define WB_ACTOR_TYPE20_HOP_SPEED    0xau     /* `move.w #$a,d0 / bra.w $2af2` — a TAIL jump */
#define WB_ACTOR_TYPE20_RECOVER      0xffu    /* `st 30(a0)` on the hurt animation's wrap, so the
                                               * first live frame after a recovery goes straight to
                                               * the reload rather than counting $32 frames down */

/* Slot 21: the shooter that stands still. It never falls, never hops and never steps. */
#define WB_ACTOR_TYPE21_WALK_LEFT    0x445cu  /* 16 words each, WB_ACTOR_ANIM32_MASK */
#define WB_ACTOR_TYPE21_WALK_RIGHT   0x447cu
#define WB_ACTOR_TYPE21_HURT_LEFT    0x449cu  /* 8 words each, WB_ACTOR_ANIM16_MASK */
#define WB_ACTOR_TYPE21_HURT_RIGHT   0x44acu
#define WB_ACTOR_TYPE21_AIMING       0xffu    /* `st 30(a0)` when the idle animation wraps: the byte
                                               * is a FLAG here, not a countdown — nothing steps it */
#define WB_ACTOR_TYPE21_REACH        0x96u    /* `move.w #$96,d0 / bsr $67f8` */
#define WB_ACTOR_TYPE21_SHOT_ODDS_MASK 0x1fu  /* `andi.w #$1f,d0 / bne` on rng_next's word */
#define WB_ACTOR_TYPE21_SHOT_TYPE    0x2cu
#define WB_ACTOR_TYPE21_SHOT_RISE    6u       /* `subq.w #6,2(a1)` off the parent's y */
#define WB_ACTOR_TYPE21_SHOT_SIZE    0x60006u
#define WB_ACTOR_TYPE21_SHOT_LIFE    0x32u    /* `move.b #$32,29(a1)` */
#define WB_ACTOR_TYPE21_AIM_ROW      6u       /* `move.w #$6,d4` — which row of the aim table the
                                               * velocity pair comes out of (actor.h, $6528) */

/* Slot 22: the launcher. It walks nowhere; WB_ACTOR_FIELD_30 counts down and the frame it reaches
 * zero the record LAUNCHES ITSELF and then, one frame in eight, drops a minion. */
#define WB_ACTOR_TYPE22_LIVE_LISTS   0x45c4u  /* $3006 PAIRS -> $45d4 / $45e6, 8 words + terminator */
#define WB_ACTOR_TYPE22_HURT_LISTS   0x45ccu  /* -> $45f8 / $460a, same shape */
#define WB_ACTOR_TYPE22_RELOAD       0x64u    /* `move.b #$64,30(a0)` on the launch frame */
#define WB_ACTOR_TYPE22_LAUNCH_SPEED 0xcu     /* `move.b #$c,11(a0)`, written inline rather than
                                               * through actor_start_motion_at_speed */
#define WB_ACTOR_TYPE22_SEED_ODDS_MASK 7u     /* `andi.b #$7,d0 / bne` */
#define WB_ACTOR_TYPE22_MINION_TYPE  0x35u
#define WB_ACTOR_TYPE22_MINION_RISE  0x10u    /* `subi.w #$10,2(a1)` */
#define WB_ACTOR_TYPE22_MINION_TIMER 0x32u    /* into the minion's WB_ACTOR_FIELD_30 */
#define WB_ACTOR_TYPE22_MINION_SIZE  0xc000cu

/* Slot 23: the GOLD THIEF, and slot 4's body with a different contact arm. Its live arm and its
 * hurt arm are actor_behavior_type04's instruction for instruction — including the hover, which it
 * takes off slot 4's own WB_ACTOR_TYPE04_HOVER. */
#define WB_ACTOR_TYPE23_DEAD_RIGHT   0x47ecu  /* 16 words each, reached by `lea d8(PC,Dn.w)` */
#define WB_ACTOR_TYPE23_DEAD_LEFT    0x47ccu
#define WB_ACTOR_TYPE23_FLY_LEFT     0x480cu  /* 16 words each */
#define WB_ACTOR_TYPE23_FLY_RIGHT    0x482cu
#define WB_ACTOR_TYPE23_FLY_STEP     1u       /* `move.w #$1,d7` — slot 4's value, named apart so a
                                               * re-read of either survives */
#define WB_ACTOR_TYPE23_DEAD_STEP    4u
#define WB_ACTOR_TYPE23_STEAL_MAX    0x10u    /* `cmpi.w #$10,$bd6e.l / bgt`: a purse ABOVE this is
                                               * charged exactly this much, one at or below it is
                                               * emptied by `clr.w` — so the two arms are not one
                                               * subtraction with a clamp */
#define WB_ACTOR_TYPE23_LOOT_TYPE    0x2eu
#define WB_ACTOR_TYPE23_LOOT_TIMER   0x50u    /* into the loot record's WB_ACTOR_FIELD_30 */
#define WB_ACTOR_TYPE23_STUN_FRAMES  0x64u    /* `move.b #$64,21(a1)` — written BELOW the failed
                                               * allocation branch, so it lands at address
                                               * WB_ACTOR_FIELD_21 of record ZERO on a full pool */

/* Slot 24: the drifter's twin. Six instructions of live arm, and then it LEAVES for slot 17. */
#define WB_ACTOR_TYPE24_LIVE_LISTS   0x48e2u  /* a PAIR whose two longwords are the SAME list */
#define WB_ACTOR_TYPE24_HURT_LISTS   0x48eau  /* ...and so are these */
#define WB_ACTOR_TYPE24_WALK_STEP    1u       /* `move.w #$1,d7 / bsr $2f22` */

/* Slot 25: slot 18's charge, one minion type over. Every value here is slot 18's today; they are
 * separate names so that a later re-read of either survives. */
#define WB_ACTOR_TYPE25_WALK_LEFT    0x4abeu  /* 16 words each */
#define WB_ACTOR_TYPE25_WALK_RIGHT   0x4adeu
#define WB_ACTOR_TYPE25_HURT_LEFT    0x4afeu  /* 8 words each */
#define WB_ACTOR_TYPE25_HURT_RIGHT   0x4b0eu
#define WB_ACTOR_TYPE25_WALK_STEP    2u       /* `move.b #$2,d7` left, `move.w #$2,d7` right */
#define WB_ACTOR_TYPE25_HURT_STEP    4u
#define WB_ACTOR_TYPE25_CHARGING     0xffu
#define WB_ACTOR_TYPE25_HOP_SPEED    9u
#define WB_ACTOR_TYPE25_MINION_TYPE  0x2au
#define WB_ACTOR_TYPE25_TURN_FRAMES  0x46u

/* Slot 26: slot 12's chase — actor_face_and_step_toward then actor_tick_timer30 — with the frame
 * list chosen by WB_ACTOR_FLAG_MOVING_BIT rather than by the supported one, and a shot on the arm
 * that bit picks. */
#define WB_ACTOR_TYPE26_MOVING_LISTS 0x4bfeu  /* -> $4c32 / $4c36, ONE word and a terminator each */
#define WB_ACTOR_TYPE26_STILL_LISTS  0x4bf6u  /* -> $4c0e / $4c20, 8 words + terminator */
#define WB_ACTOR_TYPE26_HURT_LISTS   0x4c06u  /* -> $4c3a / $4c4c, 8 words + terminator */
#define WB_ACTOR_TYPE26_STEP         2u       /* `move.w #$2,d7`, handed to $2fce and then to $2f86 */
#define WB_ACTOR_TYPE26_SHOT_TYPE    0x33u
#define WB_ACTOR_TYPE26_SHOT_RISE    0x10u    /* `subi.w #$10,2(a1)` */
#define WB_ACTOR_TYPE26_SHOT_SIZE    0x400006u /* WB_ACTOR_HALF_WIDTH $40 — the widest box any
                                                * spawner in this tier writes */

/* The $5a band's last three tables. Each sits INSIDE its own handler's extent and is reached only
 * from it — $5952 by the one `lea $5952.l` at $5928, the other three by `lea d8(PC,Dn.w)` — so no
 * second reader exists anywhere in the image. */
#define WB_ACTOR_TYPE47_FRAMES       0x5952u  /* SIXTEEN words, $5952..$5971, wrapped by
                                               * WB_ACTOR_ANIM32_MASK: $1c3 $1c3 $1c4 $1c4 $1c5 $1c5
                                               * $1c6 $1c6 $1c5 $1c5 $1c4 $1c4 $1c3 $1c3 $1c4 $1c4 */

#define WB_ACTOR_TYPE48_FRAMES       0x59c8u  /* FOUR words, $59c8..$59cf, bounded by slot 49's own
                                               * entry: $1d7 $1d7 $1d8 $1d8 */
#define WB_ACTOR_TYPE48_MASK         0x7u     /* `andi.b #$7` — 8 bytes, so all four */
#define WB_ACTOR_TYPE48_STEP         3u       /* `move.w #$3,d7` */

/* Slot 49 animates out of TWO tables over ONE cursor, chosen by WB_ACTOR_FIELD_31. Both wrap on
 * WB_ACTOR_ANIM16_MASK, which is actor_advance_anim16's own $f and not a mask this handler spells. */
#define WB_ACTOR_TYPE49_FRAMES_PHASE1 0x5a4eu  /* EIGHT words, $5a4e..$5a5d, played while
                                               * WB_ACTOR_FIELD_31 is CLEAR: $1ce $1cf $1d0 $1d1
                                               * $1ce $1cf $1d0 $1d1 */
#define WB_ACTOR_TYPE49_FRAMES_PHASE2 0x5a5eu  /* EIGHT words, $5a5e..$5a6d, played while it is SET
                                               * and bounded by slot 50's own entry: $1bc $1bc $1bd
                                               * $1bd $1be $1be $1bd $1bc */
#define WB_ACTOR_TYPE49_STEP         3u       /* `move.w #$3,d7`, as slot 48's */

#define WB_ACTOR_TYPE50_FRAMES       0x5aaeu  /* TWO words, and the whole of this handler's data */
#define WB_ACTOR_TYPE50_MASK         3u       /* `andi.w #$3` — 4 bytes, so both of them */
#define WB_ACTOR_TYPE50_STEP         8u       /* `addq.w #8,(a0)` / `subq.w #8,(a0)` */

#define WB_ACTOR_TYPE51_SPRITE       0x1e1u   /* `move.w #$1e1,6(a0)` — published, not tabled */
#define WB_ACTOR_TYPE51_STEP         6u       /* `move.w #$6,d7` */
/* `move.b #$84,19(a0)` before $69fe, spelt identically by slots 51, 52 and 53: the sign bit is
 * WB_ACTOR_DAMAGE_INLINE_MASK's flag, so the cost is the 4 left in the low seven bits. */
#define WB_ACTOR_CONTACT_DAMAGE_INLINE 0x84u

#define WB_ACTOR_TYPE52_FRAMES       0x5bd4u  /* EIGHT words, $5bd4..$5be3, bounded by slot 53's own
                                               * entry: $1b1 $1b1 $1b2 $1b2 $1b3 $1b3 $1b2 $1b2 */
#define WB_ACTOR_TYPE52_MASK         0xfu     /* `andi.w #$f` — 16 bytes, so all eight */

#define WB_ACTOR_TYPE53_SPRITE       0x1d6u   /* `move.w #$1d6,6(a0)` — one frame, never a table */
#define WB_ACTOR_TYPE53_STEP         8u       /* `moveq #$8,d7`, added to or subtracted from (a0) */
#define WB_ACTOR_TYPE53_ALIVE        0x5c6cu  /* word, the two bytes between this handler's last
                                               * `rts` and actor_followed_overlap_mask's entry.
                                               * Raised on EVERY frame slot 53 runs and cleared on
                                               * the frame it frees its slot, so it is "a type-53
                                               * record is live". Three operand sites: the two
                                               * writes here and the `tst.w` at $454c, which is
                                               * inside behaviour slot 22, whose spawn it vetoes */
#define WB_ACTOR_TYPE53_ALIVE_SET    0xffffu  /* `move.w #$ffff,$5c6c.l` */

/* --- behaviour slot 7 ($7060) and the SWOOP state machine below it -------------------------------
 *
 * Slot 7 is the only handler in the table with THREE entrances: its own row, and the two prologues
 * at $7044 and $705a that raise a bit of WB_ACTOR_FIELD_30 and run into it. Those two bits are what
 * one shared body uses to know which row was dispatched — WB_ACTOR_TYPE08_MARK_BIT arms the burst
 * and WB_ACTOR_TYPE59_MARK_BIT the dropper AND the constant sprite pair.
 */
#define WB_ACTOR_SWOOP_STATE_TABLE   0x7490u  /* FOUR longwords, $7490..$749f. One reference in the
                                               * image, the `lea $7490.l,a1` at $7130 */
#define WB_ACTOR_SWOOP_STATE_ENTRY   4u       /* `lsl.w #2,d0` — a longword per state */
#define WB_ACTOR_SWOOP_STATE0        0x72c2u
#define WB_ACTOR_SWOOP_STATE1        0x7328u
#define WB_ACTOR_SWOOP_STATE2        0x7366u
#define WB_ACTOR_SWOOP_STATE3        0x739eu
#define WB_ACTOR_SWOOP_ACQUIRE       0u       /* `clr.b 22(a0)` — state 3's ending, and the byte a
                                               * fresh record starts on */
#define WB_ACTOR_SWOOP_RUN_PATH      1u       /* `move.b #$1,22(a0)` — state 0's commit */
#define WB_ACTOR_SWOOP_HOME_X        2u       /* `move.b #$2,22(a0)` */
#define WB_ACTOR_SWOOP_DESCEND       3u       /* `move.b #$3,22(a0)`, and $701c's own forced value */

#define WB_ACTOR_SWOOP_PATH_TABLE    0x73ceu  /* FOUR longwords, $73ce..$73dd: $73de $73f8 $7412
                                               * $742c. One reference, the `lea` at $7302 */
#define WB_ACTOR_SWOOP_PATHS         0x73deu  /* the base every cursor is an OFFSET from
                                               * (`suba.l #$73de,a1` at $7310 and $7352), and the
                                               * first path's own first word */
#define WB_ACTOR_SWOOP_PATH_FAR      0x745eu  /* `movea.l #$745e,a1` — the path a record over
                                               * WB_ACTOR_SWOOP_Y_NEAR below takes, offset $80 */
#define WB_ACTOR_SWOOP_X_REACH       0x40u    /* `cmp.w #$ffc0` / `cmp.w #$40` — the window the
                                               * followed record's x must be inside, either side */
#define WB_ACTOR_SWOOP_Y_NEAR        0x40u    /* `cmp.w #$40,d0 / ble` — a drop past this takes the
                                               * fixed path instead of the table */
#define WB_ACTOR_SWOOP_Y_FLOOR       8u       /* `subq.w #8,d0 / bmi` — a drop under this is refused
                                               * outright, which is also what makes the shift's
                                               * index non-negative */
#define WB_ACTOR_SWOOP_Y_SHIFT       4u       /* `lsr.w #4,d0` — 16 pixels of drop per path */
#define WB_ACTOR_SWOOP_PATH_ENTRY    4u       /* `lsl.w #2,d0` — a longword per path */
#define WB_ACTOR_SWOOP_PATH_DY       2u       /* `move.w (a1)+` twice: dy is the word after dx */
#define WB_ACTOR_SWOOP_PATH_STEP     4u       /* ...and that PAIR is what one frame consumes */
#define WB_ACTOR_SWOOP_HOME_STEP     4u       /* `subq.w #4,(a0)` / `addq.w #4,(a0)` */
#define WB_ACTOR_SWOOP_DESCEND_STEP  2u       /* `move.w #$2,d7` — the horizontal probe's step */
#define WB_ACTOR_SWOOP_RISE          2u       /* `subq.w #2,2(a0)` — and the vertical one, upward */

#define WB_ACTOR_TYPE07_SPRITE_LEFT  0x21u    /* `move.w #$21,6(a0)` and `move.w #$24,6(a0)`: the */
#define WB_ACTOR_TYPE07_SPRITE_RIGHT 0x24u    /* two frames a MARKED record holds instead of an
                                               * animation, published straight. The $21 is kept
                                               * while WB_ACTOR_FLAG_SIDE_BIT is SET */
#define WB_ACTOR_TYPE07_FRAME_COUNT  0xcu     /* `cmpi.b #$c,23(a0) / blt` — a SIGNED byte compare,
                                               * so a cursor of $80..$ff is negative and NOT wrapped
                                               * (the game's own flow cannot reach one: the spawn
                                               * clears the byte and nothing else writes it) */
/* FOUR frame lists of twelve words each, chosen by WB_ACTOR_FLAG_SIDE_BIT and
 * WB_ACTOR_TYPE08_MARK_BIT. Each is followed by a $ffff sentinel that is NEVER READ — the cursor
 * wraps at WB_ACTOR_TYPE07_FRAME_COUNT before the `move.w 0(a1,d0.w)` — so the sentinels exist only
 * to bound one list from the next. */
#define WB_ACTOR_TYPE07_FRAMES_LEFT  0x74a0u  /* $8e $8e $8f $8f $90 $90 $91 $91 $90 $90 $8f $8f */
#define WB_ACTOR_TYPE07_FRAMES_RIGHT 0x74bau  /* $94 $94 $95 $95 $96 $96 $97 $97 $96 $96 $95 $95 */
#define WB_ACTOR_TYPE07_FRAMES_MARKED_LEFT  0x74eeu  /* $1 $1 $1 $2 $2 $2 $1 $1 $1 $2 $2 $2 */
#define WB_ACTOR_TYPE07_FRAMES_MARKED_RIGHT 0x7508u  /* $4 $4 $4 $5 $5 $5 $4 $4 $4 $5 $5 $5 */
/* ...and a FIFTH list of the same shape at $74d4 that NOTHING IN THE IMAGE REFERENCES. It sits
 * between the two above it, so the two `lea`s that bracket it are what bound it; no `lea`, `movea`
 * or computed address anywhere reaches it, and the cursor's wrap means no live path could. */
#define WB_ACTOR_TYPE07_FRAMES_UNREFERENCED 0x74d4u /* $92 $92 $93 $93 $92 $92 $93 $93 $92 $92 $93 $93 */

#define WB_ACTOR_TYPE07_BURST_MASK   0x7fu    /* `andi.b #$7f,31(a0)` — one burst every 128 frames */
#define WB_ACTOR_TYPE07_BURST_LAST   4u       /* `move.w #$4,d1` + `dbf` — FIVE shots */
#define WB_ACTOR_TYPE07_BURST_LEFT   0x7208u  /* FIVE dx,dy longwords each, mirrored: $7208 is
                                               * (-7,-2) (-7,2) (-5,5) (-2,7) (2,7) and $721c the */
#define WB_ACTOR_TYPE07_BURST_RIGHT  0x721cu  /* same five with dx negated. $7208 is taken while
                                               * WB_ACTOR_FLAG_SIDE_BIT is SET */
#define WB_ACTOR_TYPE07_BURST_ENTRY  4u       /* `move.l (a2)+,24(a1)` — a dx,dy LONGWORD a shot */
#define WB_ACTOR_TYPE07_BURST_SPRITE 0x1bbu   /* `move.w #$1bb,6(a1)`, and the shot's sprite for
                                               * its whole life: behaviour slot 57 publishes
                                               * none. Numerically WB_ACTOR_TYPE39_SPRITE, which
                                               * is as far as the evidence for "one projectile
                                               * graphic" goes */
#define WB_ACTOR_TYPE07_DROP_MASK    0x1fu    /* `andi.b #$1f,31(a0)` — one dropper every 32 */
#define WB_ACTOR_TYPE07_DROP_SPRITE  0x1b4u   /* `move.w #$1b4,6(a1)` */
#define WB_ACTOR_TYPE07_DROP_RISE    0x20u    /* `subi.w #$20,2(a1)` — the shot starts that far
                                               * ABOVE the record that dropped it */
#define WB_ACTOR_TYPE07_DROP_VELOCITY 0xfffbu /* `move.w #$fffb,24(a1)` — a WORD, where the burst
                                               * writes a longword over the same offset */
#define WB_ACTOR_TYPE07_DROP_FIELD_26 5u      /* `move.w #$5,26(a1)`, only while the side bit is
                                               * SET — the one asymmetry between the two facings,
                                               * and since batch 39 a READABLE one: 26(a1) is
                                               * behaviour slot 57's dy, so the arm that does not
                                               * write it leaves the shot's vertical speed as
                                               * whatever the freed slot held */
#define WB_ACTOR_TYPE07_SHOT_TYPE    0x39u    /* `move.w #$39,4(a1)` — WB_ACTOR_TYPE, i.e. behaviour
                                               * slot 57, reconstructed in batch 39 */
#define WB_ACTOR_TYPE07_SHOT_SIZE    0xc0002u /* `move.l #$c0002,14(a1)`: WB_ACTOR_HALF_WIDTH $c and
                                               * WB_ACTOR_SIZE_SECOND $2 in one store, the same
                                               * longword WB_ACTOR_TYPE06_SHOT_SIZE spells */

#define WB_ACTOR_SPRITE_NONE         0xffffu  /* `move.w #$ffff,6(a0)`: slot 60 publishes no sprite
                                               * at all while it waits */
#define WB_ACTOR_TYPE60_BECOMES      0x36u    /* `move.w #$36,4(a0)` — WB_ACTOR_TYPE, so the record
                                               * RETYPES itself into slot 54, the vertical moving
                                               * platform. test/test_behavior.py pins that against
                                               * the image's own table rather than this comment */

#define WB_ACTOR_TYPE61_ACTIVE       0x7014u  /* byte, between this handler's `jmp` and its message
                                               * table: raised on the frame the sequence starts and
                                               * cleared on the frame it ends. Three operand sites,
                                               * all inside slot 61 */
#define WB_ACTOR_TYPE61_ACTIVE_SET   0xffu    /* `move.b #$ff,$7014.l` */
#define WB_ACTOR_TYPE61_MESSAGES     0x7016u  /* FIVE bytes, $7016..$701a: $72 $73 $74 $75 $ff, the
                                               * four highest WB_TEXT_REQUEST ids in the game and
                                               * their terminator. Entry 0 is never READ — the
                                               * cursor is pre-incremented — and duplicates the
                                               * immediate the opening frame posts */
#define WB_ACTOR_TYPE61_MESSAGE_END  0xffu    /* `cmp.b #$ff,d0` — the end of the sequence */
#define WB_ACTOR_TYPE61_FIRST_MESSAGE 0x72u   /* `move.b #$72,d0` on the opening frame */
#define WB_ACTOR_TYPE61_SONG         0xeu     /* `move.l #$e,d0` into stub +0 (snd_play_song) */
#define WB_ACTOR_TYPE61_FIRE_BIT     7u       /* `tst.b d0 / bpl` on joy1_newly_pressed's byte */

#define WB_ACTOR_TYPE59_RESPAWN_KIND 0x15u    /* `move.w #$15,8(a1)` over WB_TABLE_A32_SET's FIRST
                                               * template — WB_SPAWN_RESPAWN_KIND, written to the
                                               * A32 table DIRECTLY and not through
                                               * WB_TABLE_PTR_21E8C, so which table is selected does
                                               * not steer it */
#define WB_ACTOR_TYPE59_MARK_BIT     2u       /* `bset #2,30(a0)` — how slot 7's body is told it was
                                               * entered through slot 59 */
#define WB_ACTOR_TYPE08_MARK_BIT     1u       /* ...and `bset #1,30(a0)` for slot 8 */

/* --- the COLLECTABLES at the foot of the $4e38 band (slots 28, 30, 31) ---------------------------
 *
 * Three handlers that PAY OUT when the followed record walks into them, and the cluster at
 * $517a..$5207 two of them pay through. What they share is the shape: `bsr $5c6e / btst #1,d0` for
 * contact, WB_ACTOR_REQUEST9_SFX for the sound, WB_ACTOR_FLAG_FLICKER_BIT raised as the record's
 * time runs out, and WB_ACTOR_FREE_MARKER over its own x at the end. What they pay differs — slot
 * 28 a fixed WB_ACTOR_TYPE28_GOLD, slot 30 the meter, slot 31 the scene descriptor's own award.
 */
#define WB_ACTOR_COLLECT_SCORE       0x20u    /* `move.l #$20,d0 / bsr $b5a2` at $4e5e, $5190 and
                                               * $5228 — one longword addend, three collect arms */
#define WB_ACTOR_FLICKER_AT_FIELD_12 0x14u    /* `cmpi.w #$14,12(a0) / bne` at $4f2e and $4fa4: the
                                               * WORD countdown value on which WB_ACTOR_FIELD_12's
                                               * owner starts flickering. Slots 30 and 31 spell it
                                               * identically; slot 28 counts the same field as a
                                               * BYTE and reloads it instead (below) */

#define WB_ACTOR_TYPE28_GOLD         5u       /* `move.w #$5,d0 / bsr $b562` — added to
                                               * WB_BCD_COUNTER, the gold the shop spends */
#define WB_ACTOR_TYPE28_FIELD_12_RELOAD 0x14u /* `move.b #$14,12(a0)` — the BYTE countdown reloaded
                                               * the FIRST time it expires. Numerically
                                               * WB_ACTOR_FLICKER_AT_FIELD_12 and a different
                                               * operand: this one is written, that one compared */

#define WB_ACTOR_TYPE30_COLLECT_MIN  0xau     /* `cmpi.b #$a,30(a0) / blt` — a SIGNED byte compare,
                                               * so a record whose countdown has not reached ten
                                               * cannot be collected at all */
#define WB_ACTOR_TYPE30_METER_STEP   4u       /* `addq.w #4,d0` on WB_HUD_METER_VALUE — and see
                                               * src/behavior.c: the sum is DISCARDED unless it
                                               * reaches WB_HUD_METER_MAX, which is a shipped bug */
#define WB_ACTOR_TYPE30_CURSOR       0x4f5au  /* word: this handler's animation cursor, and a GLOBAL
                                               * rather than a record field — the two bytes between
                                               * its body's $0000 pad and its drift table. Two live
                                               * type-30 records therefore share one phase. Three
                                               * operand sites, all inside slot 30 */
#define WB_ACTOR_TYPE30_DRIFT        0x4f5cu  /* THIRTY-TWO signed words, $4f5c..$4f9b, bounded by
                                               * slot 31's own entry and reached by the one
                                               * `lea $4f5c(pc,d0.w),a1` at $4f1a: +8 down to -8 and
                                               * back to +7, a triangle whose 32 steps sum to ZERO,
                                               * added straight to WB_ACTOR_X one a frame */
#define WB_ACTOR_TYPE30_DRIFT_STRIDE 2u       /* `addq.w #2,d0` — one word per frame, and a WORD add
                                               * on a GLOBAL. Numerically WB_ACTOR_ANIM_FRAME_BYTES
                                               * and a different operand: that one is `addq.b #2,
                                               * 18(a0)`, a BYTE step of a RECORD field, so sharing
                                               * the name here would rest on a coincidence */
#define WB_ACTOR_TYPE30_DRIFT_MASK   0x3fu    /* `andi.w #$3f,d0` on a BYTE OFFSET stepped by
                                               * WB_ACTOR_TYPE30_DRIFT_STRIDE — 64 bytes, all 32 */

/* --- $517a..$5207: what a collected record pays out ---------------------------------------------
 *
 * The scene descriptor carries the award, `bcd_add_random_1_to_4` jitters it, and the two
 * characters at WB_TEXT_GOLD_DIGITS are the digits inside message WB_TEXT_MESSAGE_GOLD_GET's own
 * shipped string — so the box the payout posts reads back the amount it just paid.
 */
#define WB_RECORD_PTR_10424          0x10424u /* longword: WB_RECORD_PTR_10420's neighbour, the copy
                                               * six `move.l $10420.l,$10424.l` sites make, so it
                                               * names the same 32-byte SCENE DESCRIPTOR — and all
                                               * SIX are inside player_run_map_cell ($1684, $170e,
                                               * $1772, $17a4, $17f4, $18f6), i.e. six of its eight
                                               * scene-trigger arms */
#define WB_SCENE_GOLD_AWARD          12u      /* word: the packed-BCD amount `move.w 12(a1),d0` at
                                               * $5180 reads out of that descriptor. The shipped
                                               * bytes of the table are zeros (the rest is loaded
                                               * from disk), so no shipped datum names an amount */
#define WB_BCD_RANDOM_MASK           3u       /* `andi.b #$3,d1` — the draw is 0..3, then `addq.b
                                               * #1` makes it 1..4 */
#define WB_TEXT_GOLD_DIGITS          0xa2acu  /* the TENS character; the units is the byte after it.
                                               * Both sit inside WB_TEXT_MESSAGE_TABLE's record 2 —
                                               * "        gold get." at $a2a7 — so the write patches
                                               * a shipped string in place. Message ids are 1-based,
                                               * which is why record 2 is id 3 below */
#define WB_TEXT_MESSAGE_GOLD_GET     3u       /* `move.b #$3,$c030.l` — the id posted right after */
#define WB_BCD_DIGIT_MASK            0xfu     /* `andi.w #$f` — one packed-BCD digit */
#define WB_BCD_DIGIT_BITS            4u       /* `ror.w #4,d0` — and how far the tens digit is up */
#define WB_TEXT_DIGIT_ZERO           0x30u    /* `addi.b #$30` — ASCII '0' */
#define WB_TEXT_DIGIT_BLANK          0x20u    /* `move.b #$20,$a2ac.l` — ASCII ' ', which is what a
                                               * ZERO tens digit is drawn as */

/* --- slots 32..37, the rest of the $4e38..$5407 band (batch 34) ---------------------------------
 *
 * TWO MORE COLLECTABLES AND FOUR SCENE ACTORS. Slot 32 is slot 31's payout with a HOP MACHINE in
 * front of it and slot 33 pays the panel's own clock; slots 34..37 are not collectables at all —
 * 34 is the shop's item CURSOR, and 35..37 are the actors the two arms of
 * `player_pending_event_gate` ($b1a) spawn and then wait on.
 */
#define WB_ACTOR_BEHAVIOR_TYPE32     0x5046u
#define WB_ACTOR_BEHAVIOR_TYPE33     0x5208u
#define WB_ACTOR_BEHAVIOR_TYPE34     0x525au
#define WB_ACTOR_BEHAVIOR_TYPE35     0x5336u
#define WB_ACTOR_BEHAVIOR_TYPE36     0x53bcu
#define WB_ACTOR_BEHAVIOR_TYPE37     0x53e2u

/* Slot 32's THREE globals, the two latch bytes and the animation cursor, packed into the six bytes
 * between its own `rts` and WB_ACTOR_ANIM_5160_FRAMES. All three are GLOBAL and not record fields,
 * so two live type-32 records share one hop machine and one animation phase — WB_ACTOR_TYPE30_CURSOR's
 * property, here over three bytes instead of one word. */
#define WB_ACTOR_TYPE32_WALKING      0x515cu  /* byte: `st` on the record's FIRST landing. It opens
                                               * the contact test for a record that is mid-hop and
                                               * it is the walk's own gate. The free arm clears it
                                               * with a `clr.w`, which covers _HOPS_SPENT below as
                                               * well — so the pair is cleared as one word and set
                                               * one byte at a time */
#define WB_ACTOR_TYPE32_HOPS_SPENT   0x515du  /* byte: `st` when WB_ACTOR_FIELD_10 runs out, after
                                               * which no landing relaunches anything */
#define WB_ACTOR_TYPE32_LATCH_SET    0xffu    /* what `st $515c.l` / `st $515d.l` write */
#define WB_ACTOR_TYPE32_CURSOR       0x515eu  /* word: a BYTE OFFSET into WB_ACTOR_ANIM_5160_FRAMES,
                                               * read `move.w` and indexed SIGN-EXTENDED, where
                                               * $6872's cursor is a zero-extended record byte */
#define WB_ACTOR_TYPE32_WALK_STEP    1u       /* `move.w #$1,d7` in BOTH probe arms — a word write,
                                               * so unlike slots 3 and 6 the step really is one */

/* Slot 33's pair: the two panel words it raises together, one instruction apart. Between them they
 * wind WB_PANEL_FRAME_DELAY back up and freeze it while it climbs, which is what makes this
 * collectable the game's clock. */
#define WB_PANEL_FRAME_REWIND_SET    0xffffu  /* `move.w #$ffff,$bd30.l` at $5218 */
#define WB_PANEL_FRAME_HOLD_SET      0xffffu  /* ...and `$bd26.l` at $5220, the instruction after */

/* Slot 34 — the shop's item cursor. Its own WB_ACTOR_X is the selection, and the three values it
 * can hold are the three items; each is planted together with a y as ONE `move.l #imm,(a0)`, which
 * is why the y's are here beside them rather than being folded into a longword literal. */
#define WB_ACTOR_TYPE34_ITEM1_X      0x33u    /* `cmpi.w #$33,(a0)` — the LEFT item */
#define WB_ACTOR_TYPE34_MIDDLE_X     0x78u    /* ...the middle, which is the FAREWELL */
#define WB_ACTOR_TYPE34_ITEM2_X      0xbeu    /* ...and the RIGHT item */
#define WB_ACTOR_TYPE34_MIDDLE_Y     0x30u    /* the middle sits sixteen pixels ABOVE the two ends */
#define WB_ACTOR_TYPE34_ITEM_Y       0x40u
#define WB_JOY1_UP_BIT               0u       /* the player's own tier reads these two: `btst #0,
                                               * $8cf.w` climbs and `btst #1` descends ($d84), and */
#define WB_JOY1_DOWN_BIT             1u       /* the JUMP is a rising edge of bit 0 ($e7a) */
#define WB_JOY1_LEFT_BIT             2u       /* `btst #2,d0` on joy1_newly_pressed's byte — the */
#define WB_JOY1_RIGHT_BIT            3u       /* Atari joystick's own bit order, up/down/left/right */
#define WB_JOY1_FIRE_BIT             7u       /* ...and bit 7. WB_ACTOR_TYPE61_FIRE_BIT is the SAME
                                               * bit under slot 61's own name, because the ORIGINALS
                                               * differ — slot 61 reads it as a SIGN (`tst.b d0 /
                                               * bpl`) and this handler as a `btst #7`. layout.py
                                               * scrapes plain literals only, so neither can derive
                                               * from the other; test_behavior.py pins them EQUAL
                                               * instead, which is this project's substitute */

/* Slots 35 and 36 — ONE animation over ONE global cursor, played by two different table rows. The
 * frames are the four sprites $1a4..$1a7 held four frames each, and the cursor is shared, so a live
 * type-35 record and a live type-36 record step each other's phase. */
#define WB_ACTOR_EVENT_ANIM_CURSOR   0x535cu  /* word: `lea $535c,a1 / move.w (a1)+,d0`, so the
                                               * cursor and the table below are ONE cursor read
                                               * followed by the table it indexes */
#define WB_ACTOR_EVENT_ANIM_FRAMES   0x535eu  /* == _CURSOR + 2, the word the post-increment leaves
                                               * a1 on: SIXTEEN words, $535e..$537d */
#define WB_ACTOR_EVENT_ANIM_MASK     0x1fu    /* `andi.w #$1f,d0` — 32 bytes, i.e. all sixteen */
#define WB_ACTOR_TYPE35_TEMPLATE     0x537eu  /* the 32 bytes `player_pending_event_gate` hands
                                               * `scene_copy_record_fields` (`lea $537e.l,a1 /
                                               * bsr $539e` at $c58). Its FIRST longword is never
                                               * read — see WB_SPAWN_TEMPLATE_UNREAD — and the type
                                               * word above it is the only shipped datum in the
                                               * image that names a behaviour slot by number */

/* $b12 and $b16 — two of the nine WORDS inside WB_STAGE_RESET_BLOCK (and NOT two of the five
 * writes that reset makes: each is the low half of one of its `clr.l`s), and what these three
 * handlers are FOR: `player_pending_event_gate` spawns an event actor, waits for the flag its
 * handler raises, and only then runs the script or the second half of the scene. */
#define WB_EVENT_ANIM_DONE_B12       0xb12u   /* word: raised by slot 35's cursor wrap. $c2e reads
                                               * it and $c6e clears it after running $19ac */
#define WB_EVENT_ANIM_DONE_B16       0xb16u   /* word: raised by slot 36's wrap AND by slot 37's
                                               * arrival — the two alternative second-half actors,
                                               * chosen at $cd8. TWO readers: $c76, and an
                                               * animation step at $1fa2 of slots 35/36's exact
                                               * shape over its own cursor at $2394, which runs only
                                               * while this flag is UP. THAT ONE IS NOT A ROUTINE —
                                               * batch 40 phase B's census found exactly one
                                               * instruction naming $1fa2, the `beq.w` at $1f62, so
                                               * it is `player_stage_transition`'s second ARM and
                                               * the earlier "a THIRD animation stepper ... unnamed
                                               * and unported" reading is retracted (../names.txt,
                                               * cmt 0x1fa2). Still unported, as all of $1f54 is */
#define WB_EVENT_DONE_SET            0xffffu  /* `move.w #$ffff` at $5354, $53d6 and $5400 */

/* Slot 37 — the riser. It has no animation at all: it lifts one pixel a frame until its y is
 * exactly WB_ACTOR_TYPE37_RISE above the y it was spawned at, which is the scene descriptor's own
 * WB_SCENE_VARIANT word. That word is the record's spawn y as well as the fragment selector — one
 * field, THREE readings, and the reason no fourth name for offset 4 is added here. */
#define WB_ACTOR_TYPE37_RISE         0x20u    /* `subi.w #$20,d0` — 32 pixels, and an EQUALITY test
                                               * against the record's y rather than a `ble`, so a
                                               * record seeded BELOW its target counts down through
                                               * the whole 16-bit range before it arrives */

/* --- slot 38, and the PICKUP TIER behind it ($5408..$54f3; $105ac..$10799) ----------------------
 *
 * THE ROW IS A COLLECTABLE WHOSE PAYOUT IS A TABLE LOOKUP, which is what makes it a tier rather
 * than a handler. WB_ACTOR_KIND names a 16-byte row of WB_ACTOR_KIND_TABLE, and the row carries
 * both halves of what the pickup is worth: a packed-BCD score LONGWORD at WB_ACTOR_KIND_SCORE and,
 * at WB_ACTOR_KIND_PICKUP_EFFECT, a word that indexes WB_PICKUP_EFFECT_TABLE — fourteen longwords
 * whose handlers are src/effects.c's, the SIBLING of WB_EFFECT_HANDLER_TABLE and bounded the same
 * way (slot 0 holds the byte past the table).
 *
 * WHICH ARM A COLLECTED RECORD TAKES IS THE KIND BYTE, compared SIGNED against
 * WB_ACTOR_PICKUP_KIND_FIRST: below it the record pays GOLD (the same five instructions
 * `hud_award_gold_from_descriptor` spells, with WB_STAGE_NUMBER as the amount instead of the scene
 * descriptor's award), at or above it the kind row decides. A kind byte of $80..$ff is NEGATIVE and
 * takes the gold arm too, which is what bounds the row index at 2..127 — this site bounds it where
 * `actor_respawn_as_new_kind`'s does not.
 */
#define WB_ACTOR_BEHAVIOR_TYPE38     0x5408u
#define WB_ACTOR_PICKUP_KIND_FIRST   2u       /* `cmpi.b #$2,20(a0) / bge.w $5476` — SIGNED */
#define WB_ACTOR_KIND_SCORE          4u       /* longword: `move.l 4(a1),d0`, packed BCD. Zero on
                                               * fifteen of the 22 shipped rows, and a zero SKIPS
                                               * both the accumulator and the digits */
#define WB_ACTOR_KIND_PICKUP_EFFECT  10u      /* word: `move.w 10(a1),d0`, the table index */
#define WB_ACTOR_TYPE38_FLASH        0xffu    /* `move.b #$ff,12(a0)` — the countdown a waiting
                                               * record is given while WB_STATE_FLAG_A32 is set */
#define WB_ACTOR_TYPE38_FIELD_12_RELOAD 0x14u /* `move.b #$14,12(a0)` on the FIRST expiry, exactly
                                               * WB_ACTOR_TYPE28_FIELD_12_RELOAD's shape one band on
                                               * — and, like slot 28's, a BYTE countdown that
                                               * expires TWICE */

/* The dispatch itself, and it is UNBOUNDED AT BOTH ENDS: `move.w 10(a1),d0 / add.w d0,d0 /
 * add.w d0,d0 / movea.l 0(a1,d0.w),a1 / jsr (a1)`. The two `add.w`s wrap in SIXTEEN BITS and the
 * extension word then sign-extends, so the read lands in [table - $8000, table + $7ffc] and the
 * index ALIASES: an entry is reached by four index values, `s`, `s + $4000`, `s + $8000` and
 * `s + $c000`. That is `actor_dispatch_behavior`'s wrapped offset at a smaller table. */
#define WB_PICKUP_EFFECT_TABLE       0x105acu /* ONE `lea` in the whole image, at $5496, by a scan
                                               * of both absolute encodings and both PC-relative
                                               * forms */
#define WB_PICKUP_EFFECT_ENTRY       4u       /* one longword per entry */
#define WB_PICKUP_EFFECT_ENTRIES     14u      /* == (0x105e4 - 0x105ac) / WB_PICKUP_EFFECT_ENTRY,
                                               * i.e. bounded by its own slot 0 */

/* The fourteen handlers, in table order. Each is a leaf of src/effects.c; each but the first ends
 * by writing a message id into WB_TEXT_REQUEST and WB_TEXT_LIFETIME_DEFAULT into
 * WB_TEXT_LIFETIME_REQUEST, and the id is what NAMES it —
 * batch 17's method (the helmet and the gauntlet were identified from the messages their own paths
 * post) applied to twelve more slots. */
#define WB_PICKUP_EFFECT_NONE        0x105e4u /* a bare `rts`, and the byte that bounds the table */
#define WB_PICKUP_EFFECT_BBC4        0x105e6u
#define WB_PICKUP_EFFECT_WING_BOOTS  0x10600u
#define WB_PICKUP_EFFECT_HELMET      0x1061au
#define WB_PICKUP_EFFECT_GAUNTLET    0x10634u
#define WB_PICKUP_EFFECT_REVIVAL     0x1064eu
#define WB_PICKUP_EFFECT_FIRE_BALLS  0x10668u
#define WB_PICKUP_EFFECT_BOMBS       0x1068au
#define WB_PICKUP_EFFECT_WIND_SPOUTS 0x106acu
#define WB_PICKUP_EFFECT_LIGHTNING   0x106ceu
#define WB_PICKUP_EFFECT_REFILL      0x106f0u
#define WB_PICKUP_EFFECT_ADD4        0x10714u
#define WB_PICKUP_EFFECT_ATTACK      0x10746u
#define WB_PICKUP_EFFECT_VANISH      0x10772u

/* What each grant WRITES. The five HUD slots take the `move.w #$Nff,slot.l` form every other slot
 * writer in the game uses (WB_HUD_SLOT_CHANGED below the value), so only the value is named. */
#define WB_PICKUP_SLOT_BBC4_VALUE        0x01u
#define WB_PICKUP_SLOT_WING_BOOTS_VALUE  0xfeu /* the only grant whose value is not a small count */
#define WB_PICKUP_SLOT_HELMET_VALUE      0x05u
#define WB_PICKUP_SLOT_GAUNTLET_VALUE    0x02u
#define WB_PICKUP_SLOT_REVIVAL_VALUE     0x01u

/* The four RECORDS the append grants push onto WB_EFFECT_RECORD_LIST, named for the message each
 * handler posts beside its own push. They are the SAME four words `effect_push_record_*` pushes
 * from WB_EFFECT_HANDLER_TABLE, which is why both spellings read these constants: the two dispatch
 * tables grant the same four items. Each word's HIGH byte is distinct across the four and its LOW
 * byte is not, which is as far as the evidence for "{item, count}" goes. */
#define WB_PICKUP_RECORD_FIRE_BALLS  0x0605u
#define WB_PICKUP_RECORD_BOMBS       0x0508u
#define WB_PICKUP_RECORD_WIND_SPOUTS 0x0705u
#define WB_PICKUP_RECORD_LIGHTNING   0x0803u

#define WB_PICKUP_METER_STEP         4u       /* `addq.w #4,d0` on WB_HUD_METER_VALUE — and see
                                               * src/effects.c: past WB_HUD_METER_MAX the store is
                                               * SKIPPED rather than clamped, so this raise is not
                                               * `effect_add4_clamped_b6fa` under another address */
#define WB_ATTACK_LEVEL_MAX          3u       /* `cmpi.b #$3,$b444.l / bgt` — SIGNED, and the byte
                                               * is bumped afterwards, so the level tops out at 4.
                                               * The address is WB_EFFECT_RECORD_LIST's own first
                                               * byte (../names.txt records the collision) */
#define WB_SCENE_EXIT_REQUESTED      0xffffu  /* `move.w #$ffff,$1079a.l` at $10768, UNCONDITIONAL —
                                               * it runs on the refused arm as well */
#define WB_PICKUP_VANISH_FLICKER     0xffu    /* `move.b #$ff,21(a1)` into WB_ACTOR_FLICKER_COUNTDOWN
                                               * on the FOLLOWED record, with WB_ACTOR_FLAG_FLICKER_BIT
                                               * and WB_ACTOR_FLAGS2_INVULNERABLE_BIT raised beside
                                               * it — the state $f14 ticks down and $69fe refuses to
                                               * damage. The message is "Vanished !" */

/* The MESSAGE each handler posts. Ids are 1-based into WB_TEXT_MESSAGE_TABLE; the three that post
 * zero post NOTHING (`text_run_message_box`'s first arm needs a nonzero request) and, because the
 * score arm has already posted WB_TEXT_MESSAGE_BONUS_POINTS by the time the handler runs, they
 * CANCEL that box rather than merely declining to open one. */
#define WB_TEXT_REQUEST_NONE         0u
#define WB_TEXT_MESSAGE_WING_BOOTS   0x52u    /* "    Wing Boots." */
#define WB_TEXT_MESSAGE_HELMET       0x58u    /* "    A Helmet." */
#define WB_TEXT_MESSAGE_GAUNTLET     0x5cu    /* "   A Gauntlet." */
#define WB_TEXT_MESSAGE_REVIVAL      0x5du    /* "Revival Medicine" */
#define WB_TEXT_MESSAGE_FIRE_BALLS   0x5eu    /* "   Fire Balls." */
#define WB_TEXT_MESSAGE_BOMBS        0x5fu    /* "       Bombs." */
#define WB_TEXT_MESSAGE_WIND_SPOUTS  0x60u    /* "     Wind Spouts." */
#define WB_TEXT_MESSAGE_LIGHTNING    0x61u    /* "    Lightning." */
#define WB_TEXT_MESSAGE_ATTACK_UP    0x63u    /* " Offensive Power \n    Increased.   " */
#define WB_TEXT_MESSAGE_VANISHED     0x64u    /* "    Vanished !   " */

/* $6938 — the score arm's own digits, and the LONGWORD sibling of WB_TEXT_GOLD_DIGITS: five packed
 * BCD digits patched into the front of message WB_TEXT_MESSAGE_BONUS_POINTS's shipped string, whose
 * first SIX characters are spaces — so a five-digit amount leaves exactly one of them before the
 * word "Bonus". `swap d0` then `rol.l #4` five times walks nibbles 4..0 of the
 * addend, so the digits drawn are its LOW FIVE and everything above them is invisible. */
#define WB_TEXT_BONUS_DIGITS         0xa4beu  /* the first character of WB_TEXT_MESSAGE_TABLE record
                                               * 15's string, "      Bonus Points." at $a4be —
                                               * SIX leading spaces, of which the patch overwrites
                                               * five. ONE
                                               * `lea` names it, at $6938 */
#define WB_TEXT_BONUS_DIGIT_COUNT    5u       /* `move.w #$5,d7`, counted down by `subi.w #1` */
#define WB_TEXT_MESSAGE_BONUS_POINTS 0x10u    /* `move.b #$10,$c030.l` at $6978 */

/* ---- the LAST NON-PLAYER dispatch rows (slots 39..46 and 57; src/behavior.c) -------------------
 *
 * NINE HANDLERS, AND THEY ARE THE TIER'S OWN AMMUNITION. Every one of the nine is the record some
 * ALREADY-RECONSTRUCTED handler spawns, one parent each: slot 16 throws slot 39
 * (WB_ACTOR_TYPE16_MINION_TYPE == $27), slot 6 slot 40, slot 18 slot 41, slot 25 slot 42, slot 19
 * slot 43, slot 21 slot 44, slot 14 slot 45, slot 23 slot 46 and slot 7 slot 57. So the FIELDS each
 * spawner writes are exactly the fields the matching handler reads — which is what identifies these
 * rows rather than a guess from their sprite ids, and what test/test_behavior.py's three THREADED
 * cases drive end to end (21 -> 44, 7 -> 57 and 23 -> 46, each a second differential seeded from
 * the parent's own write ledger).
 *
 * IT IS NOT A BIJECTION OVER THE TIER'S SPAWNS, which an earlier revision of this block claimed.
 * THREE more spawn constants name behaviour rows outside these nine —
 * WB_ACTOR_TYPE17_SEED_TYPE ($34, slot 52), WB_ACTOR_TYPE22_MINION_TYPE ($35, slot 53) and
 * WB_ACTOR_TYPE26_SHOT_TYPE ($33, slot 51) — all reconstructed in batches 31 and 32. The claim that
 * survives, and that a case makes by SCRAPING this header rather than reading a list, is: every
 * WB_ACTOR_TYPEnn_*_TYPE constant names a row this port has, and nine of the twelve are these.
 * (WB_ACTOR_SHOT_TYPE_LO/_HI/_KEPT are deliberately not of that shape: they are the range
 * actor_hit_by_player_shot SEARCHES, not a type any handler writes.)
 *
 * ONE FIELD NO SPAWNER WRITES: WB_ACTOR_FLAGS2. `spawn_minion` copies the parent's x/y longword and
 * the type word and nothing at offset 9, so a fresh record inherits whichever mode bit the freed
 * slot was left holding — and for six of these nine that bit is what chooses the frame's arm. The
 * threaded cases state it rather than inherit it, and it is reproduced rather than repaired.
 *
 * NONE OF THEM OPENS ON THE SPAWN GATE. This is the $5a band's grammar, not the monster family's:
 * WB_ACTOR_FLAGS2_BIT_0 is the mode byte, the contact test is `actor_followed_overlap_mask`'s bits
 * 0 and 1 with bit 2 unread, and no `actor_hit_by_player_shot` runs in front of it anywhere — these
 * records cannot be shot down.
 *
 * FOUR SHAPES ACROSS THE NINE:
 *   * the SHATTERERS (39, 41), which fall, drift while airborne, and play an eight-word break-up
 *     the moment WB_ACTOR_FLAG_SUPPORTED_BIT goes up or WB_ACTOR_FIELD_30 is latched. Slot 41 is
 *     slot 39 with one sprite id changed and `bra.w`s INTO slot 39's own tail at $5534;
 *   * the WALKERS that die where they stop (40, 42, 43) — a blocked probe raises the mode bit, and
 *     what the bit then buys is a fall that frees the slot on landing (40, 43) or the same break-up
 *     the shatterers play (42);
 *   * the SHOTS (44, 45, 57), which carry their own velocity: 44 in the signed byte pair
 *     WB_ACTOR_FIELD_30/_31 its spawner aimed for it, 45 re-aimed at the followed record EVERY
 *     FRAME through `actor_aim_velocity`, and 57 in the word pair WB_ACTOR_FIELD_24/_26 slot 7's
 *     burst copied in as one longword;
 *   * and the RISER (46), which is slot 23's stolen gold floating away: it steps
 *     WB_ACTOR_ANIM_5160_FRAMES with the same publish/look-ahead `actor_relaunch_and_anim_5160`
 *     has, rises WB_ACTOR_TYPE46_RISE a frame, and frees itself when its countdown reaches zero.
 */
#define WB_ACTOR_BEHAVIOR_TYPE39     0x54f4u  /* 164 bytes of code, $54f4..$5597, then its own table */
#define WB_ACTOR_BEHAVIOR_TYPE40     0x55a8u  /* 148, $55a8..$563b — no data at all */
#define WB_ACTOR_BEHAVIOR_TYPE41     0x563cu  /* 64, $563c..$567b, ending in slot 39's tail */
#define WB_ACTOR_BEHAVIOR_TYPE42     0x567cu  /* 158, $567c..$5719, then its own table */
#define WB_ACTOR_BEHAVIOR_TYPE43     0x572au  /* 148, $572a..$57bd */
#define WB_ACTOR_BEHAVIOR_TYPE44     0x57beu  /* 148, $57be..$5851 */
#define WB_ACTOR_BEHAVIOR_TYPE45     0x5852u  /* 160, $5852..$58f1 */
#define WB_ACTOR_BEHAVIOR_TYPE46     0x58f2u  /* 54, $58f2..$5927, bounded by slot 47's entry */
#define WB_ACTOR_BEHAVIOR_TYPE57     0x7260u  /* 98, $7260..$72c1, bounded by the swoop's state 0 */

#define WB_ACTOR_FIELD_28            28u      /* word: slot 57's own FRAME COUNT, stepped `addq.w #1`
                                               * and compared against WB_ACTOR_TYPE57_LIFETIME. It
                                               * is the last word of the eight bytes that handler's
                                               * two `clr.l`s cover — and it is the one of the four
                                               * that is NOT the swoop's: that machine's state is
                                               * 22, 24 and 26, ending at offset 27, so the second
                                               * `clr.l` reaches two bytes past it into this
                                               * field. Nothing else in the tier reads offset 28 */

/* Slot 39's break-up table, and the ONE table in this batch with more than one reader: three
 * instructions name it, by a whole-image scan of both absolute encodings and both PC-relative forms
 * — `move.w $5598(pc,d0.w),6(a0)` at $557e (slot 39's own) and `lea $5598.w,a1` at $5826 and $58c6
 * (slots 44 and 45). Those two are the SHORT absolute form, the encoding a scan for the longword
 * misses. Slot 42's table below has exactly one. */
#define WB_ACTOR_TYPE39_FRAMES       0x5598u  /* EIGHT words, $5598..$55a7: $1c0 $1c0 $1c1 $1c1 $1c2
                                               * $1c2 $000 $1c2 — and the SEVENTH really is zero,
                                               * which is a blank frame and not a terminator */
#define WB_ACTOR_TYPE39_SPRITE       0x1bbu   /* `move.w #$1bb,6(a0)` — published every live frame */
#define WB_ACTOR_TYPE39_STEP         3u       /* `move.w #$3,d7` in BOTH arms of the drift */
#define WB_ACTOR_TYPE41_SPRITE       0x1d5u   /* ...and the only thing that makes slot 41 not 39 */

#define WB_ACTOR_TYPE40_SPRITE_LEFT  0x1c8u   /* the arm WB_ACTOR_FLAG_SIDE_BIT SET reaches */
#define WB_ACTOR_TYPE40_SPRITE_RIGHT 0x1c7u
#define WB_ACTOR_TYPE40_STEP         4u       /* `move.w #$4,d7`, spelt once per arm */

#define WB_ACTOR_TYPE42_FRAMES       0x571au  /* EIGHT words, $571a..$5729: $1da $1da $1db $1db $1dc
                                               * $1dc $1dd $1dd. ONE `lea d8(PC,Dn.w)` names it,
                                               * at $56f6 */
#define WB_ACTOR_TYPE42_SPRITE       0x1d9u   /* published ABOVE the direction test, so one id */
#define WB_ACTOR_TYPE42_STEP         4u

#define WB_ACTOR_TYPE43_SPRITE       0x1e0u   /* spelt TWICE, once per arm, and the same both times */
#define WB_ACTOR_TYPE43_STEP         4u

#define WB_ACTOR_TYPE44_SPRITE       0x1cbu
#define WB_ACTOR_TYPE44_LIFE_STEP    2u       /* `subq.b #2,29(a0)` over the WB_ACTOR_TYPE21_SHOT_LIFE
                                               * its spawner stamped — $32, an EVEN value, so the
                                               * countdown lands on zero rather than stepping past it */

#define WB_ACTOR_TYPE45_SPRITE       0x1bfu
#define WB_ACTOR_TYPE45_AIM_ROW      1u       /* `move.w #$1,d4` — which row of WB_ACTOR_AIM_TABLE
                                               * the re-aim reads, where slot 21 reads
                                               * WB_ACTOR_TYPE21_AIM_ROW */

#define WB_ACTOR_TYPE46_RISE         4u       /* `subq.w #4,2(a0)` — the ONLY thing this handler does
                                               * to its position, and only while the countdown runs */

#define WB_ACTOR_TYPE57_LIFETIME     0x28u    /* `cmpi.w #$28,28(a0) / bne` — an EQUALITY test, so a
                                               * counter seeded past it runs the 16-bit way round */

/* The one address OUTSIDE this tier that a reconstructed handler transfers to and stops at.
 * behavior.h's boundary is how it is reported. WB_PLAYER_STEP_BODY was the other until batch 40
 * reconstructed the body behind it (src/player.c); it is a plain call now, and the constant lives
 * with the rest of the player's tier below. */
#define WB_SHOW_DATA_DISK_PROMPT     0xe494u  /* `jmp $e494.l` at slot 61's foot */
#define WB_ST_MEMORY_TOP             0x80000u /* `movea.l #$80000,a7` — the top of a 512 KB ST, the
                                               * stack the game gives itself at boot
                                               * (../names.txt, hw_init_vectors) and sets AGAIN
                                               * immediately before that `jmp`, which is what makes
                                               * the transfer a RESTART rather than a call. It is a
                                               * register, so no differential can see it */

/* ---- THE PLAYER'S OWN FRAME (RUNTIME addresses; src/player.c) ---------------------------------
 *
 * Behaviour slot 1 is not a handler like the other sixty-one: `actor_behavior_type01_player` ($a38)
 * is NINE `bsr`s in a row and every one of them is a routine of its own (one being the shared
 * `actor_fall_and_settle`). These are the constants of the FIVE batch 40 reconstructed — four of
 * those calls plus the spawn helper the second one reaches. See player.h.
 */
#define WB_PLAYER_STEP_BODY          0xe06u   /* `beq.w $e06` inside player_gate_on_1516 — the JUMP
                                               * MACHINE's entry, and the one instruction in the
                                               * image that names it. It was a reported BOUNDARY
                                               * through batch 39 and is a call now; the constant
                                               * survives because test_behavior.py's entry pin for
                                               * $d78 spells that branch's own target */
#define WB_KEY_SEQUENCE_MATCHED      0x604u   /* word, raised $ffff at $5fa when the key sequence at
                                               * $608 has been walked to its $ff terminator against
                                               * WB_KEY_LAST_SCANCODE. FIVE readers, all bare
                                               * `tst.w`: $556, $59e and $5d0 (which gate three more
                                               * scancode actions, one of them a `bchg` on $bd6b)
                                               * and TWO inside player_meter_empty_check, where a
                                               * raised word makes the death arm unreachable. So it
                                               * is the game's own cheat enable; the sequence bytes
                                               * 61 30 13 1e are the IKBD scancodes for UNDO, B, R,
                                               * A -- the cheat is typed as Undo then "BRA" */
#define WB_KEY_SEQUENCE_MATCHED_SET  0xffffu
#define WB_KEY_LAST_SCANCODE         0x879u   /* byte: ../names.txt's key_last_scancode, the word the
                                               * sequence above is walked against. Its one reader in
                                               * the reconstruction is $151a's boss-defeat arm */

#define WB_PLAYER_DEATH_SFX          0x16u    /* `move.w #$16,d0 / clr.w d1` — channel A */
#define WB_PLAYER_DEATH_SONG         0x10u    /* `move.w #$10,d0 / jsr (a1)` on stub +0 */
#define WB_PLAYER_METER_REVIVE       0x14u    /* what the revival arm refills WB_HUD_METER_VALUE to,
                                               * which is NOT WB_HUD_METER_MAX — a revived player
                                               * comes back on twenty units whatever the maximum */
#define WB_PLAYER_JUMP_SFX           0u       /* `move.w #$0,d0 / move.w #$0,d1` — effect 0, and the
                                               * only site in the image that spells the id with a
                                               * `move.w #imm` rather than a `moveq`/`clr` */
#define WB_PLAYER_JUMP_STRENGTH_BIAS 8u       /* `addi.b #$8,d0` at $e12 and `addq.b #8,d0` at
                                               * $109a, both over WB_EFFECT_STATE_BD6A's low byte:
                                               * two spellings of one number, and the two sites that
                                               * give that state word its first readers */
#define WB_PLAYER_SPEED_AFTER_JUMP   1u       /* `move.b #$1,11(a0)`: what the ascent reloads
                                               * WB_ACTOR_SPEED with when it ends, and what the wing
                                               * boots force it back to every frame they are spent */

/* The ladder ($d84). The two modes are two different nonzero words for one flag every reader tests
 * with a bare `tst.w`, which is why both are named rather than folded into one. */
#define WB_TILE_33_MODE_UP           0x00ffu  /* `move.w #$ff,$1516.l` at $db2 */
#define WB_TILE_33_MODE_DOWN         0xffffu  /* `move.w #$ffff,$1516.l` at $dea */
#define WB_TILE_33_STEP_RAISED       0xffffu  /* what both arms write to WB_TILE_33_STEP */
#define WB_PLAYER_LADDER_STEP        2u       /* `subq.w #2,2(a0)` / `addq.w #2,2(a0)` */
#define WB_PLAYER_LADDER_X_MASK      0xfff1u  /* `andi.w #$fff1,(a0)` — bits 1..3 cleared and bit 0
                                               * KEPT, so an odd x stays odd across the snap */
#define WB_PLAYER_LADDER_X_BIAS      8u       /* `addq.w #8,(a0)` — the cell's centre */
#define WB_PLAYER_LADDER_Y_MASK      0xfffeu  /* `andi.w #$fffe,2(a0)` — the y forced even */

#define WB_PLAYER_DEATH_FLAG_SET     0xffffu  /* the four `move.w #$ffff` the death arm ends in, over
                                               * WB_STATE_FLAG_A34, WB_STAGE_RESET_BLOCK,
                                               * WB_SCROLL_FOLLOW_FROZEN and WB_PANEL_FRAME_HOLD —
                                               * one immediate, four addresses, one name */

/* The messages the player's own tier posts, both of them naming a HUD slot the frame has just spent
 * (WB_HUD_SLOT_BBC6 and WB_HUD_SLOT_BBC2). Ids are 1-based into WB_TEXT_MESSAGE_TABLE. */
#define WB_TEXT_MESSAGE_REVIVAL_USED    0x16u /* "  Used the revival\n\n      medicine." */
#define WB_TEXT_MESSAGE_WING_BOOTS_LOST 0x13u /* "You lost wing boots." */
/* ...and the two the GATE posts, which are the same sentence with and without a way out of it. Both
 * are read back off WB_TEXT_MESSAGE_TABLE by test_player.py rather than trusted from here. */
#define WB_TEXT_MESSAGE_GAME_OVER       0x17u /* "     GAME OVER." — WB_LIVES is ZERO */
#define WB_TEXT_MESSAGE_CONTINUE        0x40u /* "     GAME OVER.\n\n   Press fire to\n     continue"
                                               * — the DEFAULT is the other one: `move.b #$17,d0`
                                               * runs first and only a nonzero count replaces it */

/* ---- $b1a: THE PENDING-EVENT GATE (batch 41 phase C) --------------------------------------------
 *
 * Three words of WB_STAGE_RESET_BLOCK tested in the order the block holds them — its own first word
 * (the DEATH request `player_meter_empty_check` raises), WB_STAGE_ANIM_REQUEST_B0E and
 * WB_SCENE_ALIGN_REQUEST_B14 — with an arm each. Everything each arm needs beyond the words already
 * named above is here; see include/player.h for the five endings.
 */
#define WB_EVENT_GATE_FLAG_SET       0xffffu  /* the `move.w #$ffff` over the four words below whose
                                               * RAISE is this routine's. Only two of the four are
                                               * its outright — WB_DEATH_MESSAGE_POSTED_B0A and
                                               * WB_DEATH_BOX_EXPIRED_B0C, whose every operand site
                                               * is inside $b1a. The other two are raised here and
                                               * SPENT ELSEWHERE: WB_LIFE_RESTART_ENTRY_C26 is read
                                               * and cleared in show_data_disk_prompt's band, and
                                               * WB_EVENT_FINISHED_E1BE is read at $e032.
                                               * WB_STATE_FLAG_SET and WB_PLAYER_DEATH_FLAG_SET are
                                               * the same immediate against words other routines
                                               * own, and are spelt there rather than folded in */
#define WB_DEATH_MESSAGE_POSTED_B0A  0xb0au   /* word: TWO operand sites and BOTH are this routine's
                                               * — the `tst.w $b0a.w` at $b36 that routes the death
                                               * arm into its prompt, and the `move.w #$ffff` at
                                               * $b62 that latches it the frame the ascent tops out.
                                               * So the whole life of the word is one routine's, and
                                               * only the block reset ever puts it back down */
#define WB_DEATH_BOX_EXPIRED_B0C     0xb0cu   /* ...and the second such word, on the same two
                                               * instructions' pattern: `tst.w` at $bbe and
                                               * `move.w #$ffff` at $bd0, raised on the frame
                                               * WB_TEXT_BOX_ACTIVE is found DOWN again and read the
                                               * frame after, to leave for the data-disk prompt */
#define WB_DEATH_ASCENT_TOP_Y        0xffc0u  /* `cmpi.w #$ffc0,$9936.l` — where the dying player's
                                               * rise stops. It is a WB_SCROLL_FOLLOW_Y, i.e. a
                                               * SCREEN coordinate, not the record's own y */
#define WB_DEATH_ASCENT_RISE         1u       /* `subq.w #1,2(a0)` — one pixel of WB_ACTOR_Y a frame */
#define WB_DEATH_DRIFT_CURSOR        0x4f58u  /* word: the SECOND cursor over WB_ACTOR_TYPE30_DRIFT,
                                               * two bytes below slot 30's own
                                               * (WB_ACTOR_TYPE30_CURSOR, $4f5a). Two operand sites,
                                               * both in this ascent ($b7e, $b98), so the drift
                                               * table carries two independent phases and this is
                                               * the one a dying player sways on */
#define WB_DEATH_MESSAGE_LIFETIME    0x12cu   /* `move.w #$12c,$c034.l` — 300 frames, against the
                                               * WB_TEXT_LIFETIME_DEFAULT every other poster uses */
#define WB_EVENT_SPAWN_SFX            5u       /* `move.w #$5,d0 / clr.w d1` — BOTH spawning arms */
#define WB_LIFE_RESTART_ENTRY_C26    0xc26u   /* word, and it lies INSIDE this routine's own code:
                                               * the two bytes between the `jmp $e5ba.l` at $c20 and
                                               * the `tst.w $b10.w` at $c28, which is why a linear
                                               * sweep desyncs there. THREE operand sites — raised
                                               * $ffff at $c14, one instruction before the restart
                                               * unwind, and read + cleared inside
                                               * show_data_disk_prompt's band (`tst.w $c26.w` at
                                               * $e5e4, `clr.w $c26.w` at $e6ec), where a raised
                                               * word makes the level entry SKIP
                                               * `move.b 1(a0),$e70c.l` */
#define WB_EVENT_FINISHED_E1BE       0xe1beu  /* word: raised $ffff at $d1a — the third arm's ending
                                               * when the finished event asked for no stage advance.
                                               * TWO operand sites, that raise and the
                                               * `tst.w $e1be.l` at $e032, which is the first
                                               * instruction of a routine that returns at once while
                                               * it is clear. NOTHING IN THE IMAGE NAMES A CLEAR of
                                               * it (the census below covers the absolute forms
                                               * only, so a block clear through an address register
                                               * would not appear) */
#define WB_EVENT_PAIR_POSITION       2u       /* `move.l 2(a1),(a2)` off WB_RECORD_PTR_10420 — the
                                               * descriptor's WB_SCENE_TRIGGER_X and _SPAWN_Y as one
                                               * longword, over the new record's own x and y, and
                                               * RE-READ for the second record rather than kept */
#define WB_EVENT_PAIR_SPRITE_INERT   0x1a9u   /* slot 0's, over the type word the `clr.w 4(a2)`
                                               * above it has just zeroed: a record no behaviour
                                               * row runs, which is only ever drawn */
#define WB_EVENT_PAIR_TYPE_RISER     0x25u    /* slot 1's DEFAULT — actor_behavior_type37 */
#define WB_EVENT_PAIR_SPRITE_RISER   0x1a8u
#define WB_EVENT_PAIR_TYPE_ANIMATOR  0x24u    /* ...both overwritten IN PLACE with
                                               * actor_behavior_type36's pair when the descriptor's
                                               * WB_SCENE_TRIGGER_SPAWN_TYPE is nonzero, so the
                                               * frame that takes this arm stores each of those two
                                               * words twice */
#define WB_EVENT_PAIR_SPRITE_ANIMATOR 0x1a4u

/* The 32-byte record `scene_copy_record_fields` ($539e) builds, and the one field of the scene
 * descriptor it takes: 20(a3) off WB_RECORD_PTR_10420, written over the new record's x and y before
 * a single byte of the template is read. */
#define WB_SCENE_SPAWN_POSITION      20u      /* longword: the x,y the event actor is spawned at.
                                               * `move.l 20(a3),(a2)+` is its only reader among the
                                               * recovered functions */
#define WB_SPAWN_TEMPLATE_UNREAD     4u       /* `lea 4(a1),a1` — the template's FIRST longword is
                                               * skipped, because the position above has already
                                               * taken its place */

/* ---- THE WALK ($ec8, batch 40 phase B) --------------------------------------------------------
 *
 * Five sections in a row, each falling into the next: the knock-back that spends the stun's step
 * count (WB_ACTOR_FIELD_29), the fire edge, the flicker countdown, the hurt drift that spends
 * WB_ACTOR_FIELD_31, and the WALK ACCELERATOR proper. The accelerator's own three record bytes are
 * WB_ACTOR_FIELD_22 (the speed, in pixels a frame), WB_ACTOR_FIELD_23 (which way it is travelling —
 * zero LEFT, nonzero RIGHT) and WB_ACTOR_FIELD_24 (a sub-frame counter).
 */
#define WB_ACTOR_FLAG_FIRED_BIT      7u       /* `bset #7,8(a0)` at $efa, on the frame FIRE is newly
                                               * pressed. THREE immediate bit-operand sites over
                                               * 8(An) in the whole image: this `bset`, the `bclr
                                               * #7,8(a0)` at $212a and its ONE reader, the `btst
                                               * #7,8(a0)` at $20ca — and BOTH of those lie inside
                                               * player_stage_transition ($1f54..$21e3), code this
                                               * port does not have. So what the bit BUYS is as open
                                               * as WB_ACTOR_FLAG_MOVED_BIT's, whose reader is
                                               * $2184 in the same routine */
#define WB_PLAYER_WALK_SUBFRAME_MASK 3u       /* `addq.b #1,24(a0) / andi.b #$3,24(a0) / bne` — the
                                               * accelerator raises the speed on one frame in four */
#define WB_PLAYER_WALK_SPEED_BIAS    4u       /* `addq.w #4,d0` over WB_EFFECT_STATE_BD6A at $fde and
                                               * $1048, and then `cmp.b 22(a0),d0`: a WORD add whose
                                               * LOW BYTE is the ceiling. Where the jump's
                                               * WB_PLAYER_JUMP_STRENGTH_BIAS is a BYTE add on the
                                               * same state word — so a state word of $00fc leaves
                                               * the walk ceiling at 0 and the jump strength at 4 */
#define WB_PLAYER_TURN_DECEL_RIGHT   2u       /* `subq.b #2,22(a0)` at $1002 — the frame RIGHT is
                                               * held and WB_ACTOR_FIELD_23 still says LEFT... */
#define WB_PLAYER_TURN_DECEL_LEFT    1u       /* ...and `subq.b #1,22(a0)` at $106a for the other
                                               * way round. The walk's two turns are NOT symmetric:
                                               * turning to face right sheds speed twice as fast */
#define WB_PLAYER_DRIFT_SPEND        2u       /* `subq.b #2,31(a0)` at $f52 — the hurt drift spends
                                               * two of actor_damage_followed's
                                               * WB_ACTOR_DAMAGE_FIELD_31_BASE per frame, and steps
                                               * by the count as it was BEFORE the spend */

/* ---- THE WEAPON ($1208, batch 40 phase B) ------------------------------------------------------
 *
 * DOWN + a FIRE edge spends one packed-BCD unit off the newest WB_EFFECT_RECORD_LIST record and
 * spawns what that record's HIGH byte names. The four items are the four WB_PICKUP_RECORD_* words
 * the grants push, read here by their high byte alone.
 */
#define WB_PLAYER_FIRE_EDGE_EXACT    0x80u    /* `cmp.b #$80,d0` on joy1_newly_pressed's byte — an
                                               * EQUALITY, so FIRE and nothing else may be newly
                                               * pressed this frame. WB_JOY1_FIRE_BIT is the bit;
                                               * this is the whole byte the compare wants */
#define WB_PLAYER_WEAPON_LIGHTNING   8u       /* == WB_PICKUP_RECORD_LIGHTNING >> 8 */
#define WB_PLAYER_WEAPON_WIND_SPOUTS 7u       /* == WB_PICKUP_RECORD_WIND_SPOUTS >> 8 */
#define WB_PLAYER_WEAPON_FIRE_BALLS  6u       /* == WB_PICKUP_RECORD_FIRE_BALLS >> 8. The fourth
                                               * item, WB_PICKUP_RECORD_BOMBS, has no `cmpi` of its
                                               * own — it is what the `bra.w` at $1254 falls to */
#define WB_PLAYER_LIGHTNING_FLASH    2u       /* `move.w #$2,$714.w` — WB_FLASH_TIMER, and the WHOLE
                                               * of the lightning arm: it spawns nothing */
#define WB_PLAYER_SHOT_TYPE_WIND     0x30u    /* `move.w #$30,4(a1)` — behaviour slot 48 */
#define WB_PLAYER_SHOT_TYPE_BOMB     0x31u    /* `move.w #$31,4(a1)` — slot 49 */
#define WB_PLAYER_SHOT_TYPE_FIREBALL 0x32u    /* `move.w #$32,4(a1)` — slot 50 */
#define WB_PLAYER_SHOT_LIFETIME_WIND 0xc8u    /* `move.b #$c8,30(a1)` at $128c — WB_ACTOR_FIELD_30
                                               * on the WIND SPOUT, and the one field it does not
                                               * share with the other two shots */
#define WB_PLAYER_SHOT_LIFETIME      0x32u    /* `move.b #$32,30(a1)` at $12da (the fireball) and
                                               * $1318 (the bomb) — the same field, four times
                                               * shorter */
#define WB_PLAYER_SHOT_SPEED         8u       /* `move.b #$8,11(a1)` — WB_ACTOR_SPEED, on the two
                                               * shots that run the shared arming block */
#define WB_PLAYER_SHOT_HALF_WIDTH    6u       /* the HIGH word of the `move.l #$60008,14(a1)` at
                                               * $12ba, i.e. WB_ACTOR_HALF_WIDTH */
#define WB_PLAYER_SHOT_SIZE_SECOND   8u       /* ...and its LOW word, WB_ACTOR_SIZE_SECOND. One
                                               * store, two fields, so the halves are named and
                                               * composed rather than the literal being spelt —
                                               * the same rule slot 34's item x,y pairs follow */
#define WB_PLAYER_FIREBALL_Y_RISE    8u       /* `subq.w #8,2(a1)` — the fireball leaves eight pixels
                                               * above the player's own y, and it is the ONLY
                                               * arithmetic instruction on any path to the `sbcd`
                                               * below, so the borrow it leaves IS that instruction's
                                               * entry X (see player.h) */
#define WB_PLAYER_WEAPON_SPEND_BCD   0x1332u  /* `lea $1333.l,a2 / sbcd -(a2),-(a6)` reads the byte
                                               * BELOW that address: a packed-BCD 1 held INSIDE
                                               * player_weapon_fire's own 300 bytes, at $1332, with
                                               * $1333 unread padding to the routine's end */

/* ---- $1f54, the frame's LAST call: THE STAGE TRANSITION and the POSTURE SELECTOR ----------------
 *
 * FOUR FLAG ARMS IN ONE FLOW GRAPH ($1f54 / $1fa2 / $1fd6 / $1ffc, with $205c and $205e as the
 * shared tails), and the 466 bytes above the routine ($21e4..$23b5) are its DATA. That block
 * DIVIDES EXACTLY, which is why the layout is stated as arithmetic rather than as prose — the flag
 * word, THREE 88-byte posture records, and four cursor-plus-table animations, the last of which
 * ends on actor_hit_by_player_shot's first instruction. In memory order, with each cursor counted
 * with the table it sits below:
 *
 *   WB_EFFECT_STATE_21E4        2
 *   three posture records     264   == 3 * WB_PLAYER_POSTURE_BYTES
 *   the DEATH animation        34   == 2 + 32
 *   the TRANSITION animation   98   == 2 + 2 * WB_PLAYER_TRANSITION_TABLE_BYTES
 *   the ATTACK animation       34   == 2 + 2 * 16
 *   the EVENT animation        34   == 2 + 32
 *                            ----
 *                             466
 *
 * A CURSOR HERE IS A BYTE OFFSET HELD IN THE WORD IMMEDIATELY BELOW ITS OWN TABLE, which is what
 * `lea <cursor>.l,a1 / move.w (a1)+,d0 / move.w 0(a1,d0.w),6(a0)` means, and the index is
 * SIGN-EXTENDED — the same shape as the behaviour tier's frame lists one tier over. */
#define WB_STAGE_ANIM_REQUEST_B0E    0xb0eu   /* word inside WB_STAGE_RESET_BLOCK, and the fourth of
                                               * its nine to be read rather than merely reset. FOUR
                                               * operand sites, all absolute SHORT: the raise
                                               * `move.w #$ffff,$b0e.w` at $19a4 (inside the SCENE
                                               * KIND 4 arm of player_run_map_cell — the boss
                                               * defeat), two readers `tst.w $b0e.w` at $b22
                                               * (player_pending_event_gate) and $1f5e (here), and
                                               * the `clr.l $b0e.w` at $c6a, which clears
                                               * WB_STAGE_ANIM_DONE_B10 with it as the longword's
                                               * low half without naming it */
#define WB_STAGE_ANIM_DONE_B10       0xb10u   /* ...and the LATCH that arm raises when its cursor
                                               * wraps. THREE operand sites, all absolute short:
                                               * `tst.w` at $c28 (the gate) and $1f54 (this
                                               * routine's own first instruction, so a raised word
                                               * makes the whole routine an `rts`), and the
                                               * `move.w #$ffff` at $1f9a. Cleared only as the low
                                               * half of $c6a's `clr.l` above */
#define WB_STAGE_ANIM_DONE_B18       0xb18u   /* the same latch for the arm WB_EVENT_ANIM_DONE_B16
                                               * gates. THREE operand sites, all absolute short:
                                               * `tst.w $b18.w` at $cf0 and `clr.w $b18.w` at $d02
                                               * (both the gate's), and the `move.w #$ffff` at
                                               * $1fc8 here */

#define WB_PLAYER_POSTURE_TABLE_0    0x21e6u  /* the record $205e picks while WB_EFFECT_STATE_21E4 */
#define WB_PLAYER_POSTURE_TABLE_1    0x223eu  /* is zero, exactly one, and anything else. Three */
#define WB_PLAYER_POSTURE_TABLE_2    0x2296u  /* `lea`s, and their only operand sites in the image */
#define WB_PLAYER_POSTURE_BYTES      0x58u    /* == WB_PLAYER_POSTURE_TABLE_1 - _TABLE_0, and again
                                               * _TABLE_2 - _TABLE_1; _TABLE_2 + this is
                                               * WB_PLAYER_DEATH_ANIM_CURSOR, so the run of three is
                                               * bounded at both ends by its neighbours */
/* The record's fields, by the `btst #3,8(a0)` arm that reads each: SET is FACING LEFT (the walk's
 * `bset` arm is the one holding LEFT). FOUR of its forty-four words have no reader in the image —
 * offsets 2, 4, 8 and 10, i.e. the two words above each of the idle pair. */
#define WB_PLAYER_POSTURE_IDLE_RIGHT 0u       /* `move.w (a6),6(a0)`   at $21a0 */
#define WB_PLAYER_POSTURE_IDLE_LEFT  6u       /* `move.w 6(a6),6(a0)`  at $2198 */
#define WB_PLAYER_POSTURE_JUMP_LEFT  12u      /* `move.w 12(a6),6(a0)` at $2150 */
#define WB_PLAYER_POSTURE_JUMP_RIGHT 14u      /* ...and the ORDER FLIPS here: idle is (right, left)
                                               * where jump, fall and walk are all (left, right) */
#define WB_PLAYER_POSTURE_FALL_LEFT  16u
#define WB_PLAYER_POSTURE_FALL_RIGHT 18u
#define WB_PLAYER_POSTURE_WALK_RIGHT 20u      /* `lea 20(a6),a5` — a CURSOR, with its sixteen-word */
#define WB_PLAYER_POSTURE_WALK_LEFT  54u      /* table at +2 and wrapped by WB_ACTOR_ANIM32_MASK.
                                               * 54 + 2 + 32 == WB_PLAYER_POSTURE_BYTES, which is
                                               * the third reading of that length */

#define WB_PLAYER_TRANSITION_CURSOR  0x2310u  /* arm 1's ($b0e), and the one animation here with TWO
                                               * tables: `lea 48(a1),a1` picks the second while
                                               * WB_EFFECT_STATE_21E4 is nonzero */
#define WB_PLAYER_TRANSITION_TABLE_BYTES 0x30u /* ONE number spelt by TWO instructions, and they
                                               * agree because they are the same fact: `lea 48(a1)`
                                               * steps over the first table to reach the second, and
                                               * `cmp.w #$30,d0` wraps the cursor at that table's
                                               * end. Twenty-four words each. The wrap is an
                                               * EQUALITY, so a cursor that never lands on it never
                                               * wraps and walks straight on into the second table */
#define WB_PLAYER_EVENT_ANIM_CURSOR  0x2394u  /* arm 2's ($b16), sixteen words, WB_ACTOR_ANIM32_MASK */
#define WB_PLAYER_DEATH_ANIM_CURSOR  0x22eeu  /* arm 3's ($b08, the death handshake), the same */
#define WB_PLAYER_ATTACK_CURSOR      0x2372u  /* the FIRED arm's, and the only one of the four read
                                               * with `move.w <abs>,d0` instead of `(a1)+` */
#define WB_PLAYER_ATTACK_TABLE_RIGHT 0x2374u  /* eight words each, wrapped by WB_PLAYER_ATTACK_MASK; */
#define WB_PLAYER_ATTACK_TABLE_LEFT  0x2384u  /* _LEFT is the WB_ACTOR_FLAG_SIDE_BIT SET arm */
#define WB_PLAYER_ATTACK_MASK        0xfu     /* `andi.w #$f,d0` — numerically WB_ACTOR_ANIM16_MASK */
#define WB_PLAYER_ATTACK_SFX         6u       /* `move.w #$6,d0 / clr.w d1` on the frame the cursor
                                               * is found at zero, i.e. once per swing — AND, on
                                               * that same frame, the FRAME INDEX, because the stub
                                               * it is passed in restores d0 and the `move.w
                                               * 0(a1,d0.w),6(a0)` below indexes with it. One
                                               * constant, two jobs, and the second is a defect
                                               * rather than a design: it makes entries 0, 2 and 4
                                               * of both attack tables unreachable */
#define WB_PLAYER_LADDER_SPRITES     0x20c2u  /* EIGHT BYTES OF DATA INSIDE THE BODY, $20c2..$20c9:
                                               * $014e $014e $014f $014f, the climbing frames. Its
                                               * one operand site is the `lea $20c2.l,a1` at $2096 */
#define WB_PLAYER_LADDER_SPRITE_MASK 7u       /* `andi.b #$7,d0` on WB_ACTOR_FIELD_18, a BYTE offset
                                               * into the four words above — so an ODD cursor would
                                               * fetch a word across two of them */
#define WB_PLAYER_HURT_SPRITE_RIGHT  0x11cu   /* the WB_EFFECT_STATE_21E4 == 1 pair at $2038/$202e, */
#define WB_PLAYER_HURT_SPRITE_LEFT   0x11du   /* by WB_ACTOR_FLAG_SIDE_BIT */
#define WB_PLAYER_HURT2_SPRITE_RIGHT 0x12cu   /* ...and the pair every other state takes, at */
#define WB_PLAYER_HURT2_SPRITE_LEFT  0x12du   /* $2056/$204c */
#define WB_PLAYER_POSTURE_STATE_ONE  1u       /* `cmpi.w #$1,$21e4.l`, spelt THREE times in this one
                                               * routine ($2018, $2072 and the hurt pair's own) */

/* ---- the collision map the actors walk on (RUNTIME addresses; src/map.c) ----------------------
 *
 * A SECOND map, laid out exactly like the background one (WB_MAP_ROW_STRIDE): a word of bytes per
 * row, then one byte per cell, and a cell is WB_MAP_CELL_PIXELS square. WB_STATE_FLAG_A32 picks
 * between two of them — the same flag that picks the actor table — and both probes spell the same
 * five instructions to turn an actor's pixel position into a cell pointer.
 *
 * WHICH MAP IS WHICH, AND THE ONE PLACE THE PAIR IS NOT SYMMETRIC. WB_COLLISION_MAP_A32 lies
 * INSIDE the image (it is zero there and filled at run time); WB_COLLISION_MAP_DEFAULT lies past
 * the program's last byte and is loaded from disk. $10a2 selects between them for the cell lookup
 * and then reads its ROW STRIDE from WB_COLLISION_MAP_DEFAULT unconditionally — see src/map.c.
 */
#define WB_COLLISION_MAP_A32         0x1d338u /* the map while WB_STATE_FLAG_A32 is NONZERO — a
                                               * `beq` over it, so this is the `bne` reading $67e0
                                               * uses and not $8e66's `bpl` */
#define WB_COLLISION_MAP_DEFAULT     0x23494u /* ...and while it is zero */
#define WB_COLLISION_MAP_CELLS       4u       /* `lea 2(a6,d3.w),a6` AFTER `move.w (a6)+,d3`: the
                                               * stride word plus two, so cell 0 is base + 4 —
                                               * WB_MAP_DATA_ROW's own bias off WB_MAP_ROW_STRIDE */
#define WB_MAP_CELL_SHIFT            4u       /* `asr.w #4` — a SIGNED shift of the pixel position */
#define WB_MAP_CELL_PIXELS           16u      /* == 1 << WB_MAP_CELL_SHIFT; `cmpi.w #$10,d7` and
                                               * `subi.w #$10,d7` walk the footprint by whole cells */
#define WB_MAP_CELL_MASK             0xfu     /* `andi.w #$f` — the position WITHIN a cell */
#define WB_MAP_NEIGHBOUR_CELL        1u       /* one cell either side is one BYTE, which is what
                                               * makes `1(a6)` and `-1(a6)` the marker cell's two
                                               * horizontal neighbours ($1b46, $de94) */
#define WB_MAP_TILE_BLOCK            1u       /* the tile code $10a2 refuses to walk into */
#define WB_MAP_TILE_LEDGE            2u       /* ...and the second code its ground test accepts */
#define WB_MAP_TILE_PLATFORM         0x23u    /* the tile code $1400 scans the footprint for */
#define WB_MAP_TILE_33               0x33u    /* the tile code $1334 tests the PLAYER's own cell
                                               * against, and the only other `cmpi.b #$33` on a map
                                               * byte in the image is $1554's, inside $151a — both
                                               * of them raise WB_TILE_33_FLAG and nothing else in
                                               * the image compares a cell against it. WHAT THE
                                               * TILE IS is not established, so the name carries
                                               * the code, exactly as $1/$2/$23's do */
#define WB_MAP_STEP_CLEAR            0xffu    /* `move.b #$ff,d6` — $10a2's d0 when the very first
                                               * probe was already clear */
#define WB_MAP_STEP_BLOCKED          0u       /* ...and when it had to back off, or ran off the
                                               * left edge */
#define WB_MAP_GROUND_HEAD_BIT       0x1u     /* $10a2's d1: the cell IS a block and the one above
                                               * it is not */
#define WB_MAP_GROUND_NEAR_BIT       0x4u     /* one row down is neither block nor ledge */
#define WB_MAP_GROUND_FAR_BIT        0x2u     /* ...and nor is two rows down */

/* $1400's platform: the word it lands the actor on, and the three constants around it. */
#define WB_PLATFORM_Y                0x9a6eu  /* word, exactly two operand sites in the image and
                                               * both are $1400's. It is WB_ACTOR_TABLE_DEFAULT +
                                               * 8 * WB_ACTOR_RECORD_BYTES + WB_ACTOR_Y, i.e. slot
                                               * 8's own y — asserted in test/test_map.py */
#define WB_PLATFORM_Y_ABOVE          0x12u    /* `subi.w #$12,d0`: how far ABOVE the platform the
                                               * actor may already be and still land on it */
#define WB_PLATFORM_Y_BAND           6u       /* `addq.w #6,d0`: ...and the band's other end */
#define WB_PLATFORM_STAND_OFFSET     0x10u    /* `subi.w #$10,2(a0)` — where the actor is parked */

/* $1334's three globals — the words immediately above $1492's last byte, and the only state the
 * fall pass keeps outside the actor record. Named for what the code DOES with them; what the mode
 * they gate IS is not established, so each name carries the tile code that raises it.
 *
 * The ledger is a whole-image operand scan (test/test_map.py runs it): every site that names one of
 * the three does so as a four-byte abs.l operand or as the two-byte abs.w form, and the only other
 * byte pairs in the image that spell $1514/$1516/$1518 lie in the graphics data past $18000.
 */
#define WB_TILE_33_FLAG              0x1514u  /* word. RAISED while the player's own map cell holds
                                               * WB_MAP_TILE_33: `move.w #$ffff` at $1350 and `st`
                                               * (a BYTE) at $155c; cleared by `clr.w` at $1370,
                                               * `clr.b` at $179e and the `clr.l` at $ff00 that
                                               * takes WB_TILE_33_MODE with it. Two readers, both
                                               * bare `tst.w`: $d84 and $1208 */
#define WB_TILE_33_MODE              0x1516u  /* word. Raised only by the two arms below $d84's
                                               * WB_TILE_33_FLAG test, which write DIFFERENT
                                               * nonzero values ($ff at $db2, $ffff at $dea);
                                               * cleared at $107c, at $1364 and by $ff00's `clr.l`.
                                               * All five readers ($d78, $fa8, $1014, $1358, $208e)
                                               * are bare `tst.w`, so nothing in the image can tell
                                               * its two nonzero values apart. While it is set,
                                               * $1334 returns before touching the record at all */
#define WB_TILE_33_STEP              0x1518u  /* word. Raised $ffff by those same two arms ($da4,
                                               * $ddc), cleared at $dfe, $e06 and $136a. ONE
                                               * reader, the bare `tst.w` at $20ae, which uses it
                                               * to step an animation phase byte */
#define WB_TILE_33_FLAG_RAISED       0xffffu  /* `move.w #$ffff,$1514.l` — the value $1334 raises */

/* $1af0: four map cells stamped as one 2x2 block, out of the record WB_RECORD_PTR_10420 names. */
#define WB_RECORD_PTR_10420          0x10420u /* longword pointer, written once in the image
                                               * (`move.l a1,$10420.l` at $163a) and read by twenty
                                               * sites: fourteen `movea.l` and six that copy it to
                                               * its neighbour $10424 */
#define WB_RECORD_10420_CELL         24u      /* word: the map cell the block is stamped at */
/* The word at +2 that `cmpi.w #$4,2(a1)` reads to pick the second tile set is the SAME word the
 * scene driver branches on — one field, two readings: WB_SCENE_KIND below. The stamp is asking
 * whether this scene is a boss defeat (WB_SCENE_KIND_BOSS_DEFEAT), which is why there is no
 * WB_STAMP_VARIANT_* pair here: a second name for the same offset and the same value could drift
 * from this one, and layout.py's literal-only scrape cannot derive one from the other. */
#define WB_STAMP_CELL_BIAS           4u       /* `addi.w #$4,d0` — the same WB_COLLISION_MAP_CELLS
                                               * bias, applied to WB_MAP_ROW_STRIDE's own address */
#define WB_STAMP_TILES_FIRST         0x78u    /* $78,$79 on the top row and $7a,$7b below it */
#define WB_STAMP_TILES_SECOND        0x7cu    /* ...and $7c..$7f for the variant */

/* ---- $151a: what the PLAYER'S OWN CELL costs him (src/player.c) -------------------------------
 *
 * `player_run_map_cell` turns the record's x,y into ONE collision-map cell and branches on the
 * byte there. Three bands, in the order the original tests them: below WB_SCENE_TRIGGER_CODE_FIRST
 * nothing at all, up to WB_SCENE_TRIGGER_CODE_LAST a SCENE DESCRIPTOR, and above that the six
 * special tiles $34..$39 beside WB_MAP_TILE_33.
 *
 * TWO WAYS THIS LOOKUP DIFFERS FROM src/map.c's, and both are the original's rather than a
 * simplification. It reads its row stride from WB_MAP_ROW_STRIDE — the BACKGROUND map's word — where
 * both probes read WB_COLLISION_MAP_DEFAULT's own; and it names WB_COLLISION_MAP_DEFAULT
 * unconditionally where they pick on WB_STATE_FLAG_A32, which is sound only because the one caller
 * ($a6c) is itself behind a clear A32.
 */
#define WB_PLAYER_CELL_Y_BIAS        0x10u    /* `subi.w #$10,d1` before the row shift — one whole
                                               * WB_MAP_CELL_PIXELS above the record's own y */
#define WB_MAP_TILE_34               0x34u    /* while WB_ACTOR_FLAG_SUPPORTED_BIT is up: launch the
                                               * record at WB_PLAYER_TILE_34_SPEED and spawn a
                                               * WB_PLAYER_TILE_34_SPAWN_TYPE record on its x,y */
#define WB_MAP_TILE_35               0x35u    /* the pair that HURTS: one arm serves both */
#define WB_MAP_TILE_36               0x36u
#define WB_MAP_TILE_37               0x37u    /* while supported, the x moves
                                               * WB_PLAYER_TILE_37_X_STEP pixels left */
#define WB_MAP_TILE_38               0x38u    /* one off WB_PANEL_FRAME_DELAY, masked even */
#define WB_MAP_TILE_39               0x39u    /* the STACK UNWIND — see WB_PLAYER_COLLIDE_UNWIND */
#define WB_PLAYER_TILE_34_SPEED      0xfu     /* `move.b #$f,11(a0)` into WB_ACTOR_SPEED */
#define WB_PLAYER_TILE_34_SPAWN_TYPE 0x2fu    /* `move.w #$2f,4(a1)` into WB_ACTOR_TYPE, on a record
                                               * out of the HIGH pool whose x,y are one `move.l` of
                                               * the player's own */
#define WB_PLAYER_TILE_HURT_COST     4u       /* `subq.w #4,$b6fa.l` off WB_HUD_METER_VALUE, floored
                                               * by a `bpl` that reads the RESULT — the same
                                               * read-modify-write shape actor_charge_damage carries */
#define WB_PLAYER_TILE_37_X_STEP     6u       /* `subq.w #6,(a0)` */
#define WB_PANEL_FRAME_DELAY_EVEN    0xfffeu  /* `andi.w #$fffe,$bd28.l` — a SECOND store to the word
                                               * the `subq.w` above it just wrote */
#define WB_TILE_33_FLAG_RAISED_BYTE  0xffu    /* `st $1514.w` — Scc's true BYTE, against the
                                               * `move.w #$ffff` WB_TILE_33_FLAG_RAISED that
                                               * actor_fall_and_settle writes to the same word */
#define WB_SCENE_TRIGGER_FLAG_SET    0xffffu  /* the `move.w #$ffff` the boss-defeat and door arms
                                               * raise their handshake words with */

/* The 32-byte records cells WB_SCENE_TRIGGER_CODE_FIRST..WB_SCENE_TRIGGER_CODE_LAST select, and the
 * kind word at their FRONT.
 *
 * ONE RECORD, TWO KIND WORDS, and they are different fields rather than two readings of one. This
 * table is where WB_RECORD_PTR_10420 comes from — the `move.l a1,$10420.l` at $163a is its only
 * writer in the image — and the SCENE DRIVER then branches on WB_SCENE_KIND, the word at +2. The
 * player's own collision branches on the word at +0 instead, and for the four SPAWNING kinds below
 * that +2 word is the spawned record's X. So a cell whose kind word is none of the eight is NOT
 * inert: it publishes the descriptor and returns, which is how the driver is handed one at all.
 */
#define WB_SCENE_TRIGGER_TABLE        0x21828u /* `lea $21828.l,a1`; past the shipped image, so it is
                                                * loaded from disk and no shipped datum names one */
#define WB_SCENE_TRIGGER_CODE_FIRST   3u       /* `cmpi.b #$3,(a6) / blt` on the way in and
                                                * `subq.l #3,d0` on the way to the table: one fact */
#define WB_SCENE_TRIGGER_CODE_LAST    0x22u    /* `cmp.b #$22,d0 / ble` — a SIGNED byte test, though
                                                * the `blt` above has already taken every code from
                                                * $80 up, so the band it admits is 3..$22 */
#define WB_SCENE_TRIGGER_RECORD_SHIFT 5u       /* `lsl.w #5` — 32 bytes, as WB_SPAWN_RECORD_BYTES */
#define WB_SCENE_TRIGGER_KIND         0u       /* word: `move.w (a1)+,d0`, against WB_SCENE_KIND at
                                                * +2 (see above) */
#define WB_SCENE_TRIGGER_KIND_SPAWN_1 1u       /* sprite WB_SCENE_TRIGGER_SPRITE_1, SFX
                                                * WB_SCENE_TRIGGER_SFX_1, and the only arm that
                                                * copies the FOLLOWED actor's side bit */
#define WB_SCENE_TRIGGER_KIND_SPAWN_2 2u       /* sprite WB_SCENE_TRIGGER_SPRITE_2 */
#define WB_SCENE_TRIGGER_KIND_MESSAGE 3u       /* post the descriptor's own message id */
#define WB_SCENE_TRIGGER_KIND_BOSS_DEFEAT 4u   /* the arm that raises WB_STAGE_ANIM_REQUEST_B0E */
#define WB_SCENE_TRIGGER_KIND_SPAWN_5 5u       /* sprite WB_SCENE_TRIGGER_SPRITE_5 */
#define WB_SCENE_TRIGGER_KIND_SPAWN_6 6u       /* sprite WB_SCENE_TRIGGER_SPRITE_6, and the one
                                                * spawning arm that plays no effect */
#define WB_SCENE_TRIGGER_KIND_ALIGN   7u       /* the hidden door: stand within
                                                * WB_SCENE_TRIGGER_ALIGN_REACH of the descriptor's x
                                                * with the flute already played */
#define WB_SCENE_TRIGGER_KIND_TUNE    8u       /* play the flute, or read the view */

/* The four words each SPAWNING kind copies out of the descriptor, in the order the four
 * `move.w (a1)+` take them, and the visit counter below them. Offsets are from the descriptor's
 * own base, which is why the first is WB_SCENE_KIND's. */
#define WB_SCENE_TRIGGER_X            2u       /* the spawned record's x for kinds 1/2/5/6 and the
                                                * door's for kind 7 — one offset, one reading */
#define WB_SCENE_TRIGGER_SPAWN_Y      4u
#define WB_SCENE_TRIGGER_SPAWN_TYPE   6u
#define WB_SCENE_TRIGGER_SPAWN_FIELD  8u       /* into WB_ACTOR_FIELD_12, as a WORD */
#define WB_SCENE_TRIGGER_VISITS       10u      /* `subq.w #1,(a1)+`: spent on every spawn, and the
                                                * visit that empties it CLEARS THE MAP CELL, so the
                                                * trigger fires a fixed number of times */
#define WB_SCENE_TRIGGER_SPAWN_SLOT   0x99acu  /* WB_ACTOR_TABLE_DEFAULT slot 2, and all four arms
                                                * refuse unless its x is negative — the
                                                * WB_ACTOR_FREE_MARKER test, spelt `tst.w / bmi`.
                                                * The gate's own spawn takes slot 1 ($998c) */
#define WB_SCENE_TRIGGER_SPRITE_1     0x15bu
#define WB_SCENE_TRIGGER_SPRITE_2     0x157u
#define WB_SCENE_TRIGGER_SPRITE_5     0x1a0u
#define WB_SCENE_TRIGGER_SPRITE_6     0x19fu
#define WB_SCENE_TRIGGER_SFX_1        1u       /* `move.w #$1,d0 / clr.w d1` */
#define WB_SCENE_TRIGGER_SFX_2        3u       /* kinds 2 and 5 share it; kind 6 plays none */
#define WB_SCENE_TRIGGER_SPAWN_1_FIELD_10 0xau /* kind 1 alone writes WB_ACTOR_FIELD_10 */
#define WB_SCENE_TRIGGER_SPAWN_SPEED  8u       /* ...and kinds 1 and 2 write WB_ACTOR_SPEED */

/* kind 3 — the message, and its own `move.b #$ff` PRIMER: WB_TEXT_REQUEST is stamped $ff before the
 * id is read, so a descriptor holding zero leaves that $ff standing and posts no lifetime at all. */
#define WB_SCENE_TRIGGER_MESSAGE      2u       /* word: the id, `move.w (a1)+,d0` */
#define WB_TEXT_REQUEST_PRIMED        0xffu

/* kind 4 — the boss defeat. It runs only while the record is SUPPORTED and the last key pressed was
 * WB_SCENE_TRIGGER_BOSS_KEY, which is the one place in this routine a keyboard byte steers a
 * branch; the cell address is published to WB_SCENE_MARKER_CELL_PTR either way. */
#define WB_SCENE_TRIGGER_BOSS_KEY     0x39u    /* `cmpi.b #$39,$879.w` — WB_KEY_LAST_SCANCODE, and
                                                * the same $39 the tile ladder's last code is */
#define WB_SCENE_TRIGGER_BOSS_SFX     4u

/* kind 7 — the hidden door. */
#define WB_SCENE_TRIGGER_ALIGN_SUBKIND 8u      /* word: `cmpi.w #$2,6(a1)` through the a1 the kind
                                                * word's own post-increment has already advanced —
                                                * three sites, one field */
#define WB_SCENE_TRIGGER_ALIGN_SECOND  2u      /* the value that picks WB_STAGE_ADVANCE_REQUEST over
                                                * stepping WB_LEVEL_SEQ_INDEX */
#define WB_SCENE_TRIGGER_ALIGN_REACH   4u      /* `subq.w #4 / cmp / bgt` then `addq.w #8 / cmp /
                                                * blt`: the followed actor's x must lie within four
                                                * pixels of the descriptor's, INCLUSIVE both ends */
#define WB_HUD_SLOT_BBC4_ARMED         1u      /* `cmpi.b #$1,$bbc4.l` — the BYTE, where the write
                                                * below is a WORD */
#define WB_HUD_SLOT_BBC4_SPENT         0xffu   /* `move.w #$ff,$bbc4.l` */
#define WB_LEVEL_SEQ_DOOR_A            9u      /* the two `cmpi.w` values that let the door move the
                                                * sequence on at all */
#define WB_LEVEL_SEQ_DOOR_B            0x15u
#define WB_LEVEL_SEQ_DOOR_STEP         2u      /* `addq.w #2,$216be.l` */
#define WB_SCENE_FLUTE_PLAYED          0x1960u /* word INSIDE $151a's own body ($1960..$1961), and
                                                * all three of its operand sites are in it: kind 8
                                                * raises it once the flute has finished playing, and
                                                * kind 7 requires it and clears it. THE RAISE IS PAST
                                                * THE BUSY-WAIT (see WB_PLAYER_COLLIDE_SOUND_WAIT),
                                                * so the reconstruction CLEARS this word and reads
                                                * it, and never raises it */
#define WB_SCENE_FLUTE_PLAYED_SET      1u
#define WB_STAGE_ADVANCE_REQUEST       0x1962u /* the word beside it, and the OTHER half of the
                                                * unwind: kind 7's second sub-arm raises it, and
                                                * player_pending_event_gate's `tst.w` at $d06 then
                                                * clears it and takes `bra.w $1622` — this routine's
                                                * own triple pop, in another routine's frame */
#define WB_STAGE_ADVANCE_REQUEST_SET   1u
#define WB_SCENE_ALIGN_REQUEST_B14     0xb14u  /* word inside WB_STAGE_RESET_BLOCK: raised $ffff here
                                                * and read by the gate's `tst.w $b14.w` at $b2a. Its
                                                * only clear is the `clr.l $b14.w` at $cfe, which
                                                * takes WB_EVENT_ANIM_DONE_B16 with it */

/* kind 8 — the flute, or the view. */
#define WB_SCENE_TRIGGER_TUNE_MAX_Y   0x64u    /* `cmpi.w #$64,2(a0) / blt`: the arm runs only while
                                                * the record is ABOVE this y — the only gate of the
                                                * eight that reads the player's POSITION. Kind 4
                                                * reads the same record's flags (`btst #2,8(a0)`),
                                                * so "reads the player" alone would be two arms */
#define WB_HUD_SLOT_BBC8_FLUTE        2u       /* `cmpi.b #$2,$bbc8.l` — which item is held */
#define WB_TEXT_MESSAGE_PLAYED_FLUTE  0x4du    /* "  You tried playing \n      the flute. " */
#define WB_TEXT_MESSAGE_NICE_VIEW     0x4cu    /* "      Nice View.    " */
#define WB_SCENE_TRIGGER_FLUTE_SONG   0xfu     /* `move.w #$f,d0 / clr.w d1 / jsr (a5)` — stub +0,
                                                * and the LAST write `snd_play_song` makes is the
                                                * WB_SND_ENGINE_ENABLED byte the `tst.b` under it
                                                * then spins on. WB_STAGE_TUNE_LATCH, which the
                                                * unreachable tail restarts, is not read by the
                                                * reconstruction at all */

/* ---- the text subsystem, $bd8a..$c030 (RUNTIME addresses; src/text.c) -------------------------
 *
 * An 8x8 glyph goes into an OFF-SCREEN 4-plane buffer WB_TEXT_BUFFER_LINE bytes wide, one byte per
 * plane at +0/+2/+4/+6 and one WB_TEXT_BUFFER_LINE per row, and the plotter hands back the cursor
 * for the NEXT 8-pixel cell. Two cells share each 8-byte plane group, so that advance alternates:
 * one byte on from an even cursor and seven from an odd one.
 *
 * The buffer is the only thing that explains the 88: $bd8a clears exactly WB_TEXT_BUFFER_LEN bytes
 * there, composes a message into it with eight `bsr $bf5e` and a string loop through $bf4e, and
 * then blits it to WB_SCREEN_BACK as WB_TEXT_BUFFER_LINE bytes plus a WB_TEXT_BLIT_SKIP per
 * scanline — 88 + 72 being WB_SCREEN_LINE exactly. So the row advance is the BUFFER's line and not
 * the screen's, which ../names.txt used to record as unexplained.
 */
#define WB_TEXT_GLYPH_TABLE       0x12c9cu /* the font: 32 bytes per glyph from char $20 up. Two
                                            * abs.l references, $1cf6 and $bf4e's own `lea` */
#define WB_TEXT_FIRST_GLYPH_CHAR  0x20u    /* `subi.b #$20,d0` — and glyph 0 is 32 zero bytes,
                                            * which is what a space plots */
#define WB_TEXT_GLYPH_SHIFT       5u       /* `lsl.l #5,d0` */
#define WB_TEXT_GLYPH_BYTES       32u      /* == 1 << SHIFT == ROWS * WB_PLANES */
#define WB_TEXT_GLYPH_ROWS        8u
#define WB_TEXT_FRAME_GLYPHS      0x12b9cu /* the eight glyphs the eight `bsr $bf5e` sites pass
                                            * directly, immediately below the font: the message
                                            * box's corners, edges and fill */
#define WB_TEXT_FRAME_GLYPH_COUNT 8u       /* == (WB_TEXT_GLYPH_TABLE - WB_TEXT_FRAME_GLYPHS) / 32 */
#define WB_TEXT_STATE_BYTES       10u      /* $c030..$c039, the band between the plotter's last
                                            * byte and the buffer: the seven fields below, which
                                            * are the whole state $bd8a runs on. It is also where
                                            * the plotter's own battery stops seeding */
#define WB_TEXT_BUFFER            0xc03au  /* `lea $c03a.l,a1` in $bd8a. The plotter's own last
                                            * byte is $c02f — the WB_TEXT_STATE_BYTES sit between,
                                            * so this is NOT the byte after the plotter */
#define WB_TEXT_BUFFER_LEN        6400u    /* `move.w #$63f,d0 / clr.l (a0)+ / dbf` = $640 * 4. It
                                            * ends exactly at panel_restore_dirty_regions ($d93a) */
#define WB_TEXT_BUFFER_LINE       88u      /* `lea 82(a1),a1` after the row's fourth plane byte,
                                            * which has already walked (WB_PLANES - 1) * 2 */
#define WB_TEXT_CELL_ADVANCE_EVEN 1u       /* the low byte of the same plane group */
#define WB_TEXT_CELL_ADVANCE_ODD  7u       /* == WB_PLANES * WB_PLANE_STRIDE - 1: the high byte of
                                            * the next one */

/* The seven fields of WB_TEXT_STATE_BYTES. $c030/$c031 are the two flags the frame arms on; the
 * rest are latched FROM a message record or FROM $c034, and only $c030 and $c034 are ever written
 * from outside $bd8a. A whole-image scan of the operand sites, by INSTRUCTION address: $c030 has
 * 58, of which 52 are outside and every one of those a writer; $c034 has 44, of which 41 are
 * outside and every one a writer; $c031 has 11, of which seven are outside — three `tst.b` readers
 * ($bc6, $dc3e, $dc78) and four `clr.b` writers ($cf8, $6fce, $dc84, $dfd8) that take the box down
 * early. $c032, $c033, $c036 and $c038 have NO site outside $bd8a at all, which is why "armed"
 * below is a one-way latch. */
#define WB_TEXT_REQUEST            0xc030u /* byte: the message id to compose next frame, 1-based */
#define WB_TEXT_REQUEST_DISMISS    0xffu   /* ...or this, which takes the box down and composes
                                            * nothing (`cmpi.b #$ff,$c030.l`) */
#define WB_TEXT_BOX_ACTIVE         0xc031u /* byte: a composed box is up and is blitted every frame
                                            * until this is cleared (`st $c031.l` raises it) */
#define WB_TEXT_BOX_ACTIVE_SET     0xffu   /* what `st` writes */
#define WB_TEXT_BOX_ROWS           0xc032u /* byte: the box's height in 8-pixel cell rows, from the
                                            * record. Drives both the frame's interior loop and the
                                            * blit's scanline count */
#define WB_TEXT_BOX_TOP_LINE       0xc033u /* byte: the box's top SCANLINE on screen, from the
                                            * record (`mulu.w #$a0,d0` = WB_SCREEN_LINE) */
#define WB_TEXT_LIFETIME_REQUEST   0xc034u /* word: frames the next box should live for, posted
                                            * with the request; latched and cleared on compose */
#define WB_TEXT_LIFETIME_DEFAULT   0x32u   /* 50 frames — what almost every one of $c034's 41
                                            * outside writers posts, both damage paths included */
#define WB_TEXT_MSG_HELMET_BROKEN  0x18u   /* posted by $69fe when WB_HUD_SLOT_BBBE's last charge
                                            * goes. Message record $17 of the table below reads
                                            * "   Helmet is Broken", which is what identifies that
                                            * slot — see ../STATUS.md */
#define WB_TEXT_MSG_GAUNTLET_BROKEN 0x19u  /* ...and $6b46's, " Gauntlet is Broken" */
#define WB_TEXT_LIFETIME_ARMED     0xc036u /* word: nonzero once any timed message has been
                                            * composed. NOTHING in the image clears it */
#define WB_TEXT_LIFETIME_ARMED_SET 0xffffu /* what the one `move.w #$ffff,$c036.l` writes */
#define WB_TEXT_LIFETIME_LEFT      0xc038u /* word: frames still to run, `subq.w #1` per blit */

/* The message table: WB_TEXT_MESSAGE_COUNT longword pointers, then the records they point at, back
 * to back. One abs.l reference in the whole image — $bd8a's own `lea $a09c.l,a6` — so the table's
 * extent is not declared anywhere; it is read off the data, which is self-bounding (see
 * test/test_text.py: entry 0 points at the first byte PAST the pointers, the records are
 * contiguous, and the last one ends exactly at panel_refresh_frame). */
#define WB_TEXT_MESSAGE_TABLE      0xa09cu
#define WB_TEXT_MESSAGE_COUNT      117u
#define WB_TEXT_MESSAGE_PTR_SHIFT  2u      /* `lsl.w #2,d0`: a longword per entry */
#define WB_TEXT_MESSAGE_FIRST_ID   1u      /* `subi.b #$1,d0`: WB_TEXT_REQUEST is 1-based */
#define WB_TEXT_RECORD_ROWS        0u      /* record byte 0 -> WB_TEXT_BOX_ROWS */
#define WB_TEXT_RECORD_TOP_LINE    1u      /* record byte 1 -> WB_TEXT_BOX_TOP_LINE */
#define WB_TEXT_RECORD_STRING      2u      /* ...then the string, to WB_TEXT_STRING_END */
#define WB_TEXT_NEWLINE            0x0au   /* `cmp.b #$a,d0` — tested BEFORE the terminator */
#define WB_TEXT_STRING_END         0xffu   /* `cmp.b #$ff,d0` */

/* The box's own geometry. Only the HEIGHT varies: the width is the 22 cells the unrolled top row
 * spells, which is the whole of WB_TEXT_BUFFER_LINE, and the blit moves exactly that. */
#define WB_TEXT_BOX_CELLS          22u     /* == 2 * WB_TEXT_BUFFER_LINE / WB_TEXT_CELL_GROUP */
#define WB_TEXT_BOX_EDGE_CELLS     20u     /* == CELLS - 2: the `move.w #$13,d0 / dbf` runs */
#define WB_TEXT_BOX_MIN_ROWS       3u      /* `subq.w #3,d0`: a top row, one interior, a bottom */
#define WB_TEXT_CELL_GROUP         8u      /* == WB_PLANES * WB_PLANE_STRIDE, and it holds TWO
                                            * 8-pixel cells */
#define WB_TEXT_CELL_ROW_BYTES     704u    /* `mulu.w #$2c0,d1` == GLYPH_ROWS * BUFFER_LINE */
#define WB_TEXT_ROW_ADVANCE        616u    /* `lea 616(a1),a1` == CELL_ROW_BYTES - BUFFER_LINE: the
                                            * row's last glyph left the cursor at cell CELLS, i.e.
                                            * BUFFER_LINE into the row */
#define WB_TEXT_INTERIOR_SKIP      80u     /* `lea 80(a1),a1` == EDGE_CELLS / 2 * CELL_GROUP: from
                                            * the left edge's cell straight to the right edge's */
#define WB_TEXT_FIRST_TEXT_LINE    1u      /* `move.w #$1,d6`: line 0 is the frame's top row */
#define WB_TEXT_TEXT_ORIGIN        0xc03bu /* `lea $c03b.l,a1` == BUFFER + CELL_ADVANCE_EVEN, i.e.
                                            * cell 1 — one cell in, past the left edge */

/* The blit out of the buffer, WB_TEXT_BLIT_LONGWORDS at a time. */
#define WB_TEXT_BLIT_X_BYTES       48u     /* `lea 48(a1,d0.w),a1`: the box's left edge on screen */
#define WB_TEXT_BLIT_LONGWORDS     22u     /* the unrolled `move.l (a0)+,(a1)+` == BUFFER_LINE / 4 */
#define WB_TEXT_BLIT_SKIP          72u     /* `lea 72(a1),a1` == WB_SCREEN_LINE - BUFFER_LINE */
#define WB_TEXT_BLIT_ROW_SHIFT     3u      /* `lsl.l #3,d0`: GLYPH_ROWS scanlines per cell row */

/* ---- the stage loader, $fa30..$ff42 and $e110..$e19a (RUNTIME addresses; src/stage.c) ---------
 *
 * WHAT THIS TIER IS. Everything in the background-scroll block above MAINTAINS the eight
 * pre-shifted buffers one tile column or one row pair at a time, once a frame. This tier BUILDS
 * them, once a stage: `bg_build_buffer` draws the whole visible map into copy 0 out of the tile
 * bitmaps, `bg_build_preshifted_copies` derives the other seven from it two pixels at a time, and
 * `stage_publish_scroll_state` writes the position words and the sixteen row pointers the engine
 * then steps. The three run back to back from $f95c, which is this batch's one unported caller.
 *
 * The two `lea`s that name the buffers are the SAME numbers WB_BG_BUFFER_BASE / _LEN carry, and
 * the sixteen published pointers are `base + copy * LEN + row * LINE` for rows 0 and
 * WB_BG_SCROLL_Y_BOTTOM_INIT — so nothing here restates a buffer address; test_stage.py derives
 * all sixteen and requires the image's own longwords to equal them.
 *
 * THE MAP HEADER IS TWO WORDS, AND THAT IS THIS BATCH'S READING OF THE +4. WB_MAP_DATA_ROW sat
 * four bytes above WB_MAP_ROW_STRIDE with only "indexed from its THIRD byte" to explain it.
 * `stage_publish_scroll_state` reads BOTH header words off the level's own map (`move.w (a0)+,d0`
 * twice) and turns them into WB_BG_SCROLL_LIMIT_X / _LIMIT_Y, so the header is {cells across,
 * cells down} and the cell data starts at WB_MAP_HEADER_BYTES. It is the same bias
 * WB_COLLISION_MAP_CELLS and WB_STAMP_CELL_BIAS name on the other map.
 */
#define WB_MAP_HEADER_BYTES        4u      /* `lea 4(a0,d1.w),a0`: the two header words below */
#define WB_MAP_HEADER_WIDTH        0u      /* cells across — ALSO the row stride, one byte per cell,
                                            * which is why WB_MAP_ROW_STRIDE is the word at +0 */
#define WB_MAP_HEADER_HEIGHT       2u      /* cells down */

#define WB_STAGE_MAP_PTR           0xfe16u /* longword: the level's map, as $f95c latched a0. Two
                                            * operand sites — that `move.l` and the `movea.l` at
                                            * $fb06 that reads it back */
#define WB_STAGE_START_PTR         0xfe1au /* longword: the start-position record, as $f95c latched
                                            * a1. Its first two words are the map cell the window
                                            * opens on; 4/6 are the followed object's position and
                                            * 8/9 the palette and tune $f95c picks */
#define WB_STAGE_RAW_TILE_INDEX    0xfe14u /* word: NONZERO when the map's bytes ARE tile numbers.
                                            * $f95c raises it for any tile bank other than
                                            * WB_TILE_BITMAPS and clears it for that one, and
                                            * bg_build_buffer is its only reader — so the index
                                            * table is a property of the SHIPPED bank alone */
#define WB_STAGE_RAW_TILE_INDEX_SET 0xffffu /* `move.w #$ffff,$fe14.l` at $f966, the arm $f95c takes
                                             * for any bank but WB_TILE_BITMAPS; the other arm is a
                                             * `clr.w` */
#define WB_BG_BUILD_CARRY          0xfe0cu /* WB_PLANES words of scratch between $fd46's `rts` and
                                            * WB_STAGE_MAP_PTR: the first cell's shifted-out bits,
                                            * held until the row's LAST cell is written so the
                                            * 128-byte row closes as a ring. The band's four
                                            * addresses are the routine's only write outside the
                                            * buffers, and it is a SECOND scratch of the same shape
                                            * as WB_BG_PRESHIFT_CARRY, which the row-at-a-time
                                            * pre-shift uses */

/* ---- $f95c's own numbers: the START RECORD, the palette table and the shifter ------------------
 *
 * The record $f95c is handed in a1 is TEN BYTES, and that is settled three ways rather than read off
 * one routine's operands: WB_STAGE_START_TABLE's eight pointers step by ten; the five records the
 * .PRG ships sit ten apart; and the last of them ends exactly where WB_TILE_BITMAPS begins.
 */
#define WB_START_FOLLOW_X          4u       /* `move.w 4(a1),$9aec.l` — copied into the followed
                                             * record, and re-read at $f9ae for the screen position */
#define WB_START_FOLLOW_Y          6u
#define WB_START_TUNE              8u       /* `move.b 8(a0),d0 / bmi`: a SIGNED byte — negative
                                             * stops the module, otherwise it is a song id */
#define WB_START_TUNE_STOP         0x80u    /* ...and the bit the `bmi` reads. Of the five records
                                             * the .PRG ships, four carry song ids 1..4 and one
                                             * ($1d42a's) carries $ff, so both arms are shipped */
#define WB_START_PALETTE           9u       /* `move.b 9(a0),d0 / lsl.w #5` — a row of the table */
#define WB_START_RECORD_LEN        10u      /* the stride of both tables below */
/* Words 0/2 of the record are the map cell the window opens on; bg_build_buffer reads them itself
 * (it is handed the same a1), so they are WB_MAP_HEADER_WIDTH/_HEIGHT's counterparts and are not
 * respelt here. */

#define WB_STAGE_START_TABLE       0x1d3ecu /* eight longwords, `lea $1d3ec.l,a1` at $dff6 and
                                             * nowhere else. Entry 0 is WB_STAGE_START_RECORDS less
                                             * WB_STAGE_START_TABLE_ENTRIES * 4 away from it — the
                                             * table and the records are one block */
#define WB_STAGE_START_TABLE_ENTRIES 8u     /* == (WB_STAGE_START_RECORDS - WB_STAGE_START_TABLE) / 4
                                             * (pinned): the pointers run up to where the shipped
                                             * records begin. Nothing bounds the INDEX, which is
                                             * 28(WB_RECORD_PTR_10420) shifted left twice */
#define WB_STAGE_START_RECORDS     0x1d40cu /* the five records the .PRG ships, $1d40c..$1d43d, the
                                             * ones the five `lea $1d40c/$1d416/$1d420/$1d42a/$1d434`
                                             * call sites of $f95c hand it */
#define WB_STAGE_START_RECORD_COUNT 5u      /* == (WB_TILE_BITMAPS - WB_STAGE_START_RECORDS) /
                                             * WB_START_RECORD_LEN (pinned): the run ends exactly
                                             * where the tile bitmaps begin */

#define WB_PALETTE_TABLE           0xfc46u  /* `lea $fc46.l,a1`, its ONE reference in the image. The
                                             * rows run up to bg_build_preshifted_copies' first
                                             * instruction, which is what bounds them */
#define WB_PALETTE_ROWS            8u       /* == (0xfd46 - WB_PALETTE_TABLE) / WB_PALETTE_ROW_BYTES,
                                             * i.e. the table ends where $fd46 begins (pinned) */
#define WB_PALETTE_ROW_SHIFT       5u       /* `lsl.w #5,d0` on WB_START_PALETTE's byte */
#define WB_PALETTE_ROW_BYTES       32u      /* == 1 << WB_PALETTE_ROW_SHIFT == WB_PALETTE_COLOURS
                                             * words: one whole shifter palette */
#define WB_SHIFTER_PALETTE         0xff8240u /* `lea $ff8240.l,a1` — the ST's 16 colour registers.
                                              * OFF the image on the 24-bit bus, so every write to it
                                              * is DROPPED by the oracle and by the reconstruction
                                              * alike: what $f944 puts on the screen is not pinned by
                                              * anything (see set_palette in stage.h) */
#define WB_PALETTE_COLOURS         16u      /* `move.l (a0)+,(a1)+` x 8 == 16 words */

#define WB_SCROLL_FOLLOW_BIAS_X    0x20u    /* `subi.w #$20,d0` at $f9b2 before WB_BG_SCROLL_POS_X is
                                             * subtracted: half a WB_MAP_CELL_PIXELS cell over the
                                             * screen's left margin, and stated as the operand rather
                                             * than derived, since nothing else in the image spells
                                             * either half */
#define WB_SCROLL_FOLLOW_BIAS_Y    0x40u    /* `subi.w #$40,d0` at $f9c6 */

#define WB_BG_BUILD_TILE_COLUMNS   16u     /* `move.w #$f,d6` — == WB_BG_ROW_CELLS, one buffer row */
#define WB_BG_BUILD_TILE_ROWS      11u     /* `move.w #$a,d5` — == WB_BG_BUFFER_TILE_ROWS */
#define WB_BG_BUILD_ROW_SKIP       120u    /* `lea 120(a2),a2` after the row's two longwords, i.e.
                                            * WB_BG_BUFFER_LINE - WB_BG_CELL_BYTES */
#define WB_BG_BUILD_CELL_REWIND    1920u   /* what the SIXTEENTH row's `lea -1920(a2),a2` takes back
                                            * == (WB_BG_TILE_ROWS - 1) * WB_BG_BUFFER_LINE, leaving
                                            * the cursor one WB_BG_CELL_BYTES on */
#define WB_BG_BUILD_ROW_ADVANCE    1920u   /* ...and the `lea 1920(a2),a2` after the sixteenth CELL,
                                            * which with those cells' 128 bytes is one
                                            * WB_BG_TILE_BLOCK_LEN */
#define WB_BG_BUILD_MAP_SKIP       0x10u   /* `subi.w #$10,d7` on the stride before `adda.l d7,a0`:
                                            * the columns just walked. The subtraction is a WORD one
                                            * and the add a LONG one over a register whose high half
                                            * is zero, so a stride BELOW this advances the cursor by
                                            * ~64 KB instead of stepping back — reproduced, not
                                            * tidied */
#define WB_BG_BUILD_TILE_SHIFT     7u      /* `lsl.l #7,d7` == WB_TILE_BITMAP_LEN, and a LONG shift
                                            * over a 16-bit index, so the whole table range reaches */
#define WB_BG_BUILD_PASSES         7u      /* `move.w #$6,d0` — == WB_BG_PRESHIFT_COPIES: copy k+1 is
                                            * built from copy k, so a0/a1 are never reloaded */
#define WB_BG_BUILD_SCANLINES      176u    /* `move.w #$af,d1` — == WB_BG_BUFFER_LEN / _LINE, and
                                            * == WB_BG_BUILD_TILE_ROWS * WB_BG_TILE_ROWS */
#define WB_BG_BUILD_CELLS_AFTER    15u     /* `move.w #$e,d2` — the cells the OR/write loop covers,
                                            * == WB_BG_ROW_CELLS - 1, the first being the prologue's */

#define WB_BG_SCROLL_Y_BOTTOM_INIT 0x9eu   /* `move.w #$9e,$83aa.l`: 158 scanlines below the top
                                            * cursor, which is the visible window's other end */
#define WB_BG_LIMIT_X_BIAS         0xf0u   /* `subi.w #$f0,d0` on (cells << 4) at $fb18 — IS
                                            * WB_BG_SCROLL_LIMIT_BIAS, whose own note names this
                                            * site as one of its two. The literal is repeated only
                                            * because layout.py deliberately refuses a compound
                                            * #define; the identity is pinned in test_stage.py's
                                            * limits case instead of stated here */
#define WB_BG_LIMIT_Y_BIAS         0xa0u   /* `subi.w #$a0,d0`, the vertical counterpart: 160
                                            * scanlines, the scrolled window's own height */
/* The `lsl.w #4` that turns each header word, and each start cell, into pixels is WB_MAP_CELL_SHIFT
 * run the other way — one cell is WB_MAP_CELL_PIXELS square on both maps — so it is not respelt. */

/* The state $fed2 resets, in the order it writes it. Everything here is plain RAM; what each field
 * MEANS is mostly established elsewhere (../names.txt) or not at all, and the names say only what
 * this routine does with them. */
#define WB_STAGE_RESET_BLOCK       0xb08u  /* `lea $b08.w,a0` then four `clr.l (a0)+` and a
                                            * `clr.w (a0)+` — 18 bytes cleared as one run.
                                            * ITS OWN FIRST WORD IS THE DEATH REQUEST, which is why
                                            * the name reads oddly at most of its call sites: SIX
                                            * operand sites, of which FIVE name the death request
                                            * and only the SIXTH — the reset's own `lea $b08.w,a0`
                                            * at $fed2 — is about the block. The five are
                                            * `move.w #$ffff,$b08.l` at $aee, which raises it (the death
                                            * arm of player_meter_empty_check), `tst.w $b08.l` at
                                            * $ad2 is that arm's own guard, `tst.w $b08.w` at $b1a
                                            * is player_pending_event_gate's FIRST test, $baa
                                            * re-raises it inside that gate's ascent, and
                                            * `tst.w $b08.w` at $1fd6 is what picks the death
                                            * animation in player_stage_transition. test_player.py's
                                            * OPERAND_CENSUS holds all six */
#define WB_STAGE_RESET_BLOCK_LONGS 4u
#define WB_STAGE_RESET_BLOCK_WORDS 1u
/* The five words $bbca's timers run around panel_frame_index ($bd2c). Batch 16 read that body, so
 * each one is now named for what it DOES there rather than for being near the others; only $bd30 is
 * outside the run this reset clears. WB_PANEL_FRAME_HOLD was WB_PANEL_FRAME_TIMER and
 * WB_PANEL_FRAME_DWELL was WB_PANEL_FRAME_SPARE — the second was demonstrably wrong, since $bd2e is
 * the live frames-per-index countdown and not spare at all. */
#define WB_PANEL_FRAME_HOLD        0xbd26u /* nonzero freezes the delay countdown ($bc60's `tst.w`) */
#define WB_PANEL_FRAME_DELAY       0xbd28u /* ...and the one this reset seeds rather than clears */
#define WB_PANEL_FRAME_DELAY_INIT  0x500u  /* `move.w #$500,$bd28.l`, the same $500 $bc56 measures
                                            * panel_frame_index back off */
#define WB_PANEL_FRAME_PHASE       0xbd2au /* nonzero = the index is stepping, not being measured */
#define WB_PANEL_FRAME_DWELL       0xbd2eu /* frames left on the current index */
#define WB_PANEL_FRAME_REWIND      0xbd30u /* nonzero winds WB_PANEL_FRAME_DELAY back up to _INIT.
                                            * Raised at $5218 one instruction before _HOLD, and the
                                            * only word of the five this reset does NOT touch */

/* The two flags $fb06 writes and NOTHING in the plaintext image reads. A whole-image scan of both
 * absolute encodings gives each exactly ONE operand site — the `clr.w` at $fb8a and the `st` at
 * $fb90 below — which is the other side of PORTABILITY.md §6.1's note that their readers are
 * reachable only from inside the Copylock's ciphertext. */
#define WB_COPYLOCK_FLAG_A         0xf89au /* `clr.w` — a WORD */
#define WB_COPYLOCK_FLAG_B         0xf89cu /* `st` — a Scc, so ONE byte and not the word beside it */

/* The last eight entries of WB_TILE_INDEX_TABLE, written by the reset: `lea $21e90.l,a1 /
 * lea 496(a1),a1` then four `move.l #imm,(a1)+`. So map bytes $f8..$ff name tiles $46..$4b, $40 and
 * $4d. The .PRG ships NONE of that table — $21e90 lies past the program's last byte ($218d0), so
 * the whole 256 entries are loaded from disk at run time and this reset overwrites the last 8 of
 * them. What the DISK holds there before the overwrite is not established by anything here. */
#define WB_TILE_INDEX_TAIL         0x22080u /* == WB_TILE_INDEX_TABLE + 496 */
#define WB_TILE_INDEX_TAIL_LONGS   4u       /* four `move.l #imm,(a1)+` == 8 entries */

/* $fe1e: the one-time relocation of a table loaded past the program. Each record's FIRST longword
 * arrives as an offset from the table's own base and is turned into an absolute pointer in place,
 * which is why it must not run twice — hence the signature byte. */
#define WB_RESOURCE_HEADER         0x24898u /* the signature byte, and the base the count is read
                                            * from: `lea $24898.l,a6 / cmpi.b #$45,(a6)` */
#define WB_RESOURCE_RELOCATED      0x45u    /* 'E' — what the routine stamps once it has run */
#define WB_RESOURCE_COUNT_OFF      8u       /* `move.w 8(a6),d7`: a `dbf` count, so the table holds
                                             * that word plus one records. The word itself is past
                                             * the program and loaded from disk, so a case seeds it */
#define WB_RESOURCE_TABLE          0x248d8u /* `lea $248d8.l,a5`, and the base ADDED to each record's
                                            * first longword — the two are the same number */
#define WB_RESOURCE_RECORD_BYTES   20u      /* `lea 20(a5),a5` */

/* $e110..$e198: two banners plotted into buffer copy 0, out of a SECOND font — WB_BG_BANNER_FONT
 * below, which a whole-image scan reaches from $e156 alone and which is not the panel's
 * WB_TEXT_GLYPH_TABLE. Only the GLYPH GEOMETRY is shared with the message box's plotter.
 * A record is {word: byte offset into the buffer} followed by characters, ended by any byte with
 * bit 7 set. The glyph geometry is WB_TEXT_'s — 32 bytes, 8 rows, one byte per plane — over the
 * BACKGROUND buffer's 128-byte line rather than the message box's 88. */
#define WB_BG_BANNER_ROUND         0xe19au /* "ROUND BONUS" at buffer offset $c28 */
#define WB_BG_BANNER_PERFECT       0xe1a8u /* "PERFECT!  10000 PTS" at $1418, drawn only when the
                                           * meter is at its maximum */
#define WB_BG_BANNER_FONT          0x1387cu /* `lea $1387c.l,a0` — a SECOND 32-byte-per-glyph font,
                                            * not WB_TEXT_GLYPH_TABLE, and reached from here alone */
#define WB_BG_BANNER_END           0x80u   /* `tst.b (a6) / bpl` — the terminator is the SIGN BIT,
                                            * so any byte from $80 up ends the string */
#define WB_BG_BANNER_BONUS         0x10000u /* `move.l #$10000,d0 / bsr $b5a2`: packed BCD 10000 */

/* ---- the sound module's SFX trigger ($1a48a; src/sound.c) -------------------------------------
 *
 * The module ($17adc..$1abc8) is SELF-CONTAINED AND PC-RELATIVE: it reaches its own tables through
 * the base in a3, so the absolute addresses below are what those PC-relative operands resolve to in
 * the image the harness loads. Only the state `snd_trigger_effect` touches is named here; the rest
 * of the module's map is in ../notes/sound_module_recon.md and ../names.txt.
 *
 * WHERE a3 COMES FROM IS NOT UNIFORM, and an earlier reading of this that said it was cost a batch
 * an afternoon. Every routine reachable through the STUB TABLE opens with `lea $1738c(pc),a3` and
 * needs nothing from its caller. The two internal `bsr` targets ported so far — $1aaca
 * (snd_prng_step) and $18208 (snd_channel_period_and_volume) — do NOT: they inherit a3, and a
 * differential entering either directly must seed it or the routine writes at $375b instead of
 * $1aae6. Assume nothing about $18106 or the opcode handlers; read the first instruction.
 *
 * THREE CHANNELS, ONE BODY. $1a48a's arms at $1a494 (A), $1a504 (B) and $1a56e (C) are the same
 * fifteen instructions with the channel's own offsets, and all four of the blocks they address step
 * by a CONSTANT — which is why each is a base plus a stride here rather than three addresses. The
 * noise byte is the exception and really is shared: all three arms write the one address. */
#define WB_SND_MODULE_BASE         0x1738cu /* `lea $1738c(pc),a3` — the module's own base */
#define WB_SND_SFX_PTR_TABLE       0x1a830u /* WB_SND_SFX_IDS a3-relative WORDS -> the descriptors */
#define WB_SND_SFX_IDS             26u      /* self-proving: entry 0 resolves to the byte past the
                                             * table, and IDS * DESCRIPTOR_LEN lands exactly on
                                             * WB_SND_SFX_VOLUME_PTRS. The trigger BOUNDS-CHECKS
                                             * NOTHING, so this is the table's extent and not a
                                             * limit the code enforces */
#define WB_SND_SFX_DESCRIPTORS     0x1a864u
#define WB_SND_SFX_DESCRIPTOR_LEN  14u      /* `moveq #$d,d0` + `dbf` — the record the trigger copies */
#define WB_SND_SFX_VOLUME_PTRS     0x1a9d0u /* 10 a3-relative words -> the volume-envelope streams */
#define WB_SND_SFX_VOLUME_STREAMS  10u
#define WB_SND_TABLE_ENTRY_LEN     2u       /* both of the tables above hold a3-relative WORDS, which
                                             * is the `add.w d0,d0` an index goes through */

#define WB_SND_CHANNELS            3u
#define WB_SND_CHANNEL_A           0u       /* `clr.w d1` — what all but one call site passes */
#define WB_SND_CHANNEL_B           1u       /* `move.w #$1,d1` at $6b46, the ONE site in the image
                                             * that asks for a channel other than A. It is what
                                             * makes the trigger's B arm live code (../STATUS.md) */
#define WB_SND_SFX_ACTIVE_FLAGS    0x17c5au /* a3+2254: one byte per channel, polled by the tick */
#define WB_SND_SFX_ACTIVE          1u       /* `move.b #$1` at the end; `sf` clears it at the start */
#define WB_SND_SFX_STATE           0x1aa7cu /* a3+14064: three channel states, MUTABLE image bytes */
#define WB_SND_SFX_STATE_LEN       26u
#define WB_SND_SFX_MIX_PERIOD      0x18360u /* a3+4052: the channel's tone period, one WORD each */
#define WB_SND_SFX_MIX_PERIOD_LEN  2u
#define WB_SND_SFX_MIX_NOISE       0x18366u /* a3+4058: ONE byte, written by whichever arm ran */
#define WB_SND_SFX_MIX_VOLUME      0x18368u /* a3+4060: one byte per channel */

/* The descriptor's fields, as the trigger reads them (roles: ../notes/sound_module_recon.md). Each
 * is read back out of the COPY the trigger just made, not out of the descriptor. */
#define WB_SND_DESC_PERIOD_STEP    1u
#define WB_SND_DESC_TONE_PERIOD    2u  /* a word */
#define WB_SND_DESC_NOISE_PERIOD   3u  /* the tone period's LOW byte, read a second time as this */
#define WB_SND_DESC_MIXER_BITS     6u
#define WB_SND_DESC_VOLUME_INDEX   10u
#define WB_SND_DESC_VOLUME_STEP    11u
#define WB_SND_DESC_SECOND_RELOAD  13u
#define WB_SND_MIXER_NOISE_OFF     0x08u /* `btst #3` — PSG polarity: set means noise off, and then
                                          * the noise period is NOT written */

/* ...and the runtime fields past the copy that the trigger seeds. +17 is the one byte of the state
 * it never writes, which is what separates its two write bands. */
#define WB_SND_STATE_PERIOD_COUNT  14u
#define WB_SND_STATE_VOLUME_COUNT  15u
#define WB_SND_STATE_SECOND_COUNT  16u
#define WB_SND_STATE_STREAM_BASE   18u /* a long — the stream to loop back to */
#define WB_SND_STATE_STREAM_CURSOR 22u /* a long — and where it is now */

/* ---- the YM2149 as the DIRECT path names it ($ff8800 select, $ff8802 data) ---------------------
 *
 * REGISTER NUMBERS, not addresses. The reconstruction never writes the two ports: it calls
 * `psg_port_read`/`psg_port_write` from tools/recreate_kit/include/psg.h, which take the number the
 * `move.b #n,$ff8800` select carries, and both the oracle's ledger and the candidate's are keyed by
 * it (TRAP_MODEL.md, "Phase 6"). WB_SND_PSG_SHADOW below is indexed by exactly these numbers, which
 * is what makes the module's own shadow of the mixer and the chip's mixer the same register.
 */
#define WB_PSG_REG_MIXER           7u
#define WB_PSG_REG_VOLUME_A        8u
#define WB_PSG_REG_VOLUME_B        9u
#define WB_PSG_REG_VOLUME_C        10u
#define WB_PSG_VOLUME_SILENT       0u    /* `move.b #$0,$ff8802.l`, once per volume register */
#define WB_PSG_MIXER_ALL_OFF       0x3fu /* `ori.b #$3f,d1` — the six tone/noise enables, which are
                                          * ACTIVE LOW, so setting all six is silence. The `ori` is
                                          * what LEAVES bits 6-7 (the port A/B I/O direction lines,
                                          * which the floppy drive-select depends on) as the chip
                                          * held them — so the read-back at $17f3e is an INPUT of
                                          * the run, and a case must declare it with `psg_seed` */

/* The module's own state that snd_stop / snd_stop_all_sfx clear. The globals block is mapped in
 * ../names.txt (`snd_engine_enabled`); only what these two routines touch is named here. */
#define WB_SND_ENGINE_ENABLED      0x17c56u /* a3+2250, byte: `sf` here is snd_stop's whole state
                                             * change, `st` is snd_resume's. It does NOT clear the
                                             * "song loaded" byte at $17c63, which is why a stop is
                                             * a PAUSE and snd_resume can restart the same song */
#define WB_SND_ENGINE_DISABLED     0u       /* `sf 2250(a3)` — Scc's false byte */
#define WB_SND_ENGINE_RUNNING      0xffu    /* `st 2250(a3)` — snd_resume's and snd_play_song's */
#define WB_SND_SFX_ACTIVE_FLAGS_LEN 4u      /* `clr.l 2254(a3)` — the three WB_SND_SFX_ACTIVE_FLAGS
                                             * bytes AND the byte after them, which nothing else in
                                             * the module names. A `clr.l`, so all four go */
#define WB_SND_PSG_SHADOW          0x18352u /* a3+4038: the PSG registers 0..10 as the tick last
                                             * meant to write them, INDEXED BY REGISTER NUMBER — so
                                             * the mixer shadow is + WB_PSG_REG_MIXER and the three
                                             * volume shadows + WB_PSG_REG_VOLUME_A..C. That is why
                                             * snd_stop_all_sfx's four stores mirror
                                             * snd_psg_silence's four chip writes exactly */

/* ---- the module's TICK TIER: the PRNG ($1aaca), the SFX tick ($1a5da) and the music channel's
 *      period/volume pass ($18208) — src/sound.c ---------------------------------------------------
 *
 * EVERY BAND BELOW IS MUTABLE IMAGE, and the shipped .PRG carries LIVE RESIDUE in all of it: it was
 * saved after a run at a load base of about $2d360, so $17bc6+2 holds a stale pointer and $1aa7c
 * holds a copy of SFX descriptor 9 (../notes/sound_module_recon.md §6). Nothing may read an initial
 * value out of $17bc6..$17c71, $18352..$1836a, $1aa7c..$1aac9 or $1aae6..$1aae9 — a case seeds it,
 * or drives it through snd_play_song / snd_trigger_effect.
 */

/* The module's own PRNG, which is NOT src/rng.c's — that one is the game's ($68c6) and this one is
 * read by the SFX engine alone. `andi.b #$48 / addi.b #$38 / lsl.b #2` puts bit 3 XOR bit 6 of the
 * top byte into X, and two `roxl.w` on memory then chain that X through the low word and into the
 * high one — so it is a 32-bit shift left with the feedback bit entering at the bottom. The step
 * runs EVERY tick, unconditionally, and snd_play_song does not reset it. */
#define WB_SND_PRNG_STATE          0x1aae6u /* a3+14170, the HIGH word */
#define WB_SND_PRNG_STATE_LEN      4u
#define WB_SND_PRNG_LOW_WORD       2u       /* a3+14172, and the word the FIRST `roxl.w` turns */
#define WB_SND_PRNG_TAP_MASK       0x48u    /* `andi.b #$48,d0` — bits 3 and 6 of the top byte */
#define WB_SND_PRNG_TAP_BIAS       0x38u    /* `addi.b #$38,d0`, which is what turns those two bits
                                             * into their XOR in the bit the shift pushes out */
#define WB_SND_PRNG_FEEDBACK_BIT   6u       /* `lsl.b #2,d0` leaves the LAST bit shifted out in X,
                                             * which for a count of 2 on a byte is bit 6 */

/* The SFX tick's own view of the descriptor copy the trigger left in the channel state. The fields
 * WB_SND_DESC_PERIOD_STEP/_TONE_PERIOD/_MIXER_BITS/_VOLUME_STEP/_SECOND_RELOAD above are the same
 * bytes; these are the six the tick reads and the trigger does not. */
#define WB_SND_DESC_DURATION       0u  /* counted down every tick; zero with no sustain ends it */
#define WB_SND_DESC_SLIDE_AMOUNT   4u  /* a word, added to or subtracted from the mix period */
#define WB_SND_DESC_USE_PRNG       7u  /* non-zero: take the pitch delta from WB_SND_PRNG_STATE */
#define WB_SND_DESC_SLIDE_DIRECTION 8u /* `tst.b / beq / bpl` — 0 none, positive down, NEGATIVE up */
#define WB_SND_DESC_SLIDE_COUNT    9u  /* counted down by the pitch step */
#define WB_SND_DESC_SUSTAIN        12u /* non-zero: the effect holds past its duration */

#define WB_SND_SFX_INACTIVE        0u  /* `sf 2254(a3)` when an effect ends — Scc's false byte */
#define WB_SND_MIX_PERIOD_LOW      1u  /* the LOW byte of a channel's mix period word, which is what
                                        * the tick copies into the shared noise byte */
#define WB_SND_VOLUME_STREAM_LOOP  0x80u /* `cmp.b #-128,d0` — the one negative byte that means "go
                                          * back to WB_SND_STATE_STREAM_BASE"; any other negative
                                          * byte HOLDS, writing neither the cursor nor the volume */

/* ---- the MUSIC channel state ($17bc6, three of them) and the pass that reads it ($18208) --------
 *
 * $18208 is handed one channel's record in a0 and hands back a period in d0 and a volume in d1. It
 * is image-only — it drives no port — but it is not a pure function either: it steps the envelope,
 * the arpeggio, the portamento and the vibrato in place, and it publishes the noise period and the
 * module's shadow of the PSG mixer.
 */
#define WB_SND_MUSIC_CHANNEL_STATE 0x17bc6u /* A/B/C at $17bc6/$17bf6/$17c26. There are
                                             * WB_SND_CHANNELS of them and not a count of their own:
                                             * the music and the SFX engines keep separate state for
                                             * the SAME three PSG channels */
#define WB_SND_MUSIC_CHANNEL_LEN   48u      /* `adda.w #$30,a1` in snd_play_song */

#define WB_SND_CH_FLAGS            0u
#define WB_SND_CH_VIBRATO_ACC      14u /* a word */
#define WB_SND_CH_ARPEGGIO_BASE    16u /* a long — the stream to loop back to */
#define WB_SND_CH_ARPEGGIO_CURSOR  20u /* a long — and where it is now */
#define WB_SND_CH_VIBRATO_DEPTH    24u /* a SIGNED byte, added to the accumulator each step */
#define WB_SND_CH_VIBRATO_SPEED    25u
#define WB_SND_CH_ENVELOPE_SPEED   26u /* the byte the instrument's data is preceded by */
#define WB_SND_CH_NOTE             29u
#define WB_SND_CH_VOLUME           30u /* what the caller reads back out of d1 */
#define WB_SND_CH_ENVELOPE_COUNT   31u
#define WB_SND_CH_ENVELOPE_CURSOR  32u /* a long */
#define WB_SND_CH_ENVELOPE_LAST    40u /* the last value taken off the envelope, held at its end */
#define WB_SND_CH_PORTA_LIMIT      41u /* HALVED: the code `lsl.b #1`s it before every use */
#define WB_SND_CH_PORTA_STEP       42u
#define WB_SND_CH_PORTA_CURRENT    43u
#define WB_SND_CH_PORTA_CONTROL    44u
#define WB_SND_CH_YIELD            45u /* bit 7 set: this channel has been handed to the SFX engine */
#define WB_SND_CH_DETUNE           46u /* added to the note, like the global transpose */
#define WB_SND_CH_MIXER_MASK       47u /* CONSTANT per channel: $09 (A), $12 (B), $24 (C) */

#define WB_SND_CH_FLAG_TOGGLE      0x01u /* `eori.b #1,d7` — flipped on every call, so it is the
                                          * pass's own every-other-tick phase */
#define WB_SND_CH_FLAG_VIBRATO     0x04u /* bit 2 */
#define WB_SND_CH_FLAG_ENVELOPE    0x20u /* bit 5 */
#define WB_SND_CH_NOISE_ROUTE_FLAGS 0x03u /* `eori.b #$ff,d7 / andi.b #3,d7 / bne` — the noise arm
                                           * runs only when BOTH bit 0 and bit 1 are SET */
#define WB_SND_CH_PORTA_ENABLED    0x40u /* `btst #6` — what opcode $82 writes */
#define WB_SND_CH_PORTA_HELD       0x80u /* `btst #7`: with it set the slide advances only on the
                                          * ticks whose WB_SND_CH_FLAG_TOGGLE is clear */
#define WB_SND_CH_PORTA_AT_LIMIT   0x20u /* `bset/bclr #5` — which end the slide is running towards */
#define WB_SND_CH_YIELD_TAKEN      0x80u /* `move.b 45(a0),d1 / bpl` — the SIGN bit */
#define WB_SND_CH_YIELD_MASK       0x7fu /* `andi.b #$7f,45(a0)` — the hand-over happens once */

#define WB_SND_ARPEGGIO_END        0x80u /* `bclr #7,d1` — the terminator, cleared before the byte is
                                          * used, so the last entry's own offset is applied on the
                                          * tick that loops */

#define WB_SND_NOTE_PERIOD_TABLE   0x1836eu /* 96 words, equal temperament (../names.txt) */
#define WB_SND_NOTE_PERIOD_ENTRIES 96u      /* the table's extent; `add.b d0,d0` bounds the byte
                                             * index to 0..254 and NOTHING bounds it to this, so a
                                             * note from 96 up reads past the table's end */
#define WB_SND_GLOBAL_TRANSPOSE    0x17c64u /* a3+2264, added to every channel's note (opcode $89) */
#define WB_SND_NOISE_PERIOD_BASE   0x17c6bu /* a3+2271 */
#define WB_SND_NOISE_PERIOD_OUT    0x17c6cu /* a3+2272 — what the tick writes to PSG register 6 */
#define WB_SND_NOISE_ROUTE_MASK    0x17c6du /* a3+2273 */
#define WB_SND_NOISE_PERIOD_XOR    0x08u    /* `eori.b #8,d3` on the base before it is published */
#define WB_SND_NOISE_TONE_BITS     0x07u    /* `move.b #7,d3` — the three TONE enables, merged into
                                             * the shadow mixer when this channel drives the noise */
#define WB_SND_NOISE_ROUTE_YIELDED 0x01u    /* `move.b #1,2272(a3)` on the yield path */
#define WB_SND_MIXER_NOISE_BITS    0x38u    /* `andi.b #$38,d1` — the three NOISE enables, which a
                                             * yielded channel gives up for this tick */

#define WB_SND_PORTA_OCTAVE_BIAS   0xa0u /* `addi.b #-96,d5` — an ADD, so its CARRY says the note's
                                          * byte index has reached 96, i.e. the table entry the
                                          * slide's units are expressed in */
#define WB_SND_PORTA_OCTAVE_STEP   24u   /* `addi.b #24,d5` — twelve semitones of table, one octave;
                                          * the delta doubles once per octave because the period
                                          * table halves once per octave */

/* ---- the PATTERN STEPPER ($18106) and its 24 opcode handlers ($17fd4..$18105) — src/sound.c -----
 *
 * The rest of the music channel record: what the stepper walks rather than what the period/volume
 * pass reads. Every field here is MUTABLE image in the same dirty band as the ones above.
 */
#define WB_SND_CH_NOISE_TRACKS_NOTE 1u  /* `tst.b 1(a0)` — set, the note byte is ALSO published as
                                         * WB_SND_NOISE_PERIOD_BASE. Opcodes $8b/$8c set it, $8a
                                         * clears it */
#define WB_SND_CH_TRACKS_NOTE_SET  0xffu /* `st 1(a0)` — Scc's true byte, what $8b and $8c store */
#define WB_SND_CH_PATTERN_CURSOR   2u   /* a long — where in the pattern byte stream this channel is */
#define WB_SND_CH_SEQUENCE_OFFSET  6u   /* a WORD, a3-relative: the channel's sequence table */
#define WB_SND_CH_SEQUENCE_INDEX   10u  /* a WORD: the BYTE index into it, and 2 after a restart,
                                         * because entry 0 has already been taken */
#define WB_SND_CH_DURATION         27u  /* `subq.b #1,27(a0)` opens the stepper; a row runs while it
                                         * is non-zero */
#define WB_SND_CH_DURATION_RELOAD  28u  /* what opcode $e0+n writes and what +27 reloads from */
#define WB_SND_CH_ENVELOPE_BASE    36u  /* a long — the instrument stream, whose FIRST byte a new
                                         * note takes as both WB_SND_CH_ENVELOPE_LAST and the volume */

#define WB_SND_CH_FLAG_MARK        0x02u /* bit 1 — `bset #1,0(a0)`, opcodes $83 and $8d, which share
                                          * one handler. Nothing in the ported tier reads it */
#define WB_SND_CH_FLAG_SLIDE       0x08u /* bit 3 — `btst #3,0(a0)` off the row-step path: with it
                                          * clear the stepper returns without touching the note */
#define WB_SND_CH_FLAG_SLIDE_UP    0x80u /* bit 7 — set, the note is ADDED to; clear, subtracted from */
#define WB_SND_CH_YIELD_ASKED      0xffu /* `st 45(a0)` — Scc's true byte, which opcode $90 and the
                                          * hand-over at $18182 both store */

/* The opcode table and the RANGE DECODER at $181a6 that reaches it. The ranges are not a mask: a
 * `cmp.b` and then a chain of `addi.b`+`bcs`, each carry saying the byte was at or above that bias'
 * complement. $b8 is the one the `cmp.b` names, and it is BELOW the arpeggio range — so $b8..$bf
 * decode as an arpeggio with an index past the 16-word table. */
#define WB_SND_PATTERN_JUMP_TABLE  0x17fa4u /* 24 a3-relative WORDS, opcodes $80..$97 */
#define WB_SND_PATTERN_OPCODES     24u
#define WB_SND_PATTERN_NOTE_LIMIT  0x80u    /* `bmi` — $00..$7f is a note and everything else decodes */
#define WB_SND_PATTERN_CMD_LIMIT   0xb8u    /* `cmp.b #-72,d0 / bcs` — BELOW this is a jump-table
                                             * dispatch, and the table has only 24 entries, so
                                             * $98..$b7 index PAST it (see src/sound.c) */
#define WB_SND_PATTERN_CMD_INDEX_MASK 0x7fu /* `andi.w #$7f,d0` before the `add.w d0,d0` */
#define WB_SND_PATTERN_DURATION_BIAS 0x20u  /* `addi.b #32`: carry means the byte was $e0 or above */
#define WB_SND_PATTERN_INSTRUMENT_BIAS 0x10u/* `addi.b #16`: ...and then $d0 or above */
#define WB_SND_PATTERN_ARPEGGIO_BIAS 0x10u  /* `addi.b #16` once more, whose carry is NOT tested —
                                             * so $c0..$cf arrive as 0..15 and $b8..$bf as $f8..$ff */
#define WB_SND_PATTERN_DURATION_MIN 1u      /* `addq.b #1,d0` — a duration byte of $e0 means ONE row */

#define WB_SND_ARPEGGIO_PTR_TABLE  0x1842eu /* 16 a3-relative words, opcodes $c0..$cf */
#define WB_SND_INSTRUMENT_PTR_TABLE 0x1ab04u/* 16 a3-relative words, opcodes $d0..$df. The envelope
                                             * SPEED is the byte BEFORE the stream (`move.b -(a2)`) */

/* ---- snd_play_song ($17b3a): the SONG DIRECTORY and the arpeggio a fresh channel starts on ------
 *
 * `lea $18480(pc),a0` twice, indexed by `ext.w d0 / mulu.w #8,d0` and then by an `addq.w #2` per
 * channel — so the whole record is reached with one index, and a NEGATIVE id (the `ext.w` is what
 * makes one possible) indexes the directory backwards. Nothing bounds it.
 */
#define WB_SND_SONG_DIRECTORY      0x18480u /* ../names.txt: 17 records, the lowest sequence offset
                                             * being $18508 — which is where the records themselves
                                             * end, so the table bounds itself */
#define WB_SND_SONGS               17u      /* == (0x18508 - WB_SND_SONG_DIRECTORY) /
                                             * WB_SND_SONG_RECORD_LEN (pinned) */
#define WB_SND_SONG_RECORD_LEN     8u       /* `mulu.w #$8,d0` */
#define WB_SND_SONG_SPEED_OFF      1u       /* `move.b 1(a0,d0.w),2252(a3)` — byte +0 is unread by
                                             * this routine and by everything else in the module */
#define WB_SND_SONG_SEQUENCE_OFF   2u       /* `movea.w 2(a0,d0.w),a0` — words +2/+4/+6, one per
                                             * channel, each an a3-relative offset */
#define WB_SND_ARPEGGIO_NULL       0x1844eu /* `lea $1844e(pc),a0` — the stream every channel's
                                             * arpeggio base AND cursor start on. Its first byte is
                                             * WB_SND_ARPEGGIO_END, so it terminates immediately */
#define WB_SND_CH_DURATION_INITIAL 1u       /* `move.b #$1,27(a1)` — one row, so the first tick the
                                             * stepper runs steps the channel rather than counting */
#define WB_SND_CH_SEQUENCE_INDEX_INITIAL 2u /* `move.w #$2,10(a1)` — entry 0 has just been taken as
                                             * the pattern cursor, so the index already names entry 1 */
#define WB_SND_SPEED_ACC_INITIAL   0xffu    /* `st 2270(a3)` — the row accumulator starts SATURATED,
                                             * so the first tick to add a nonzero speed to it carries
                                             * and the song's first row steps immediately (src/sound.c
                                             * `step_rows`) rather than after a fraction of a row */

/* ---- the TICK ($17c74..$17f23) — src/sound.c -----------------------------------------------------
 *
 * The module globals the tick reads and writes that no routine below it names, the two PSG register
 * groups it drives, and the machine bits its 44-byte TEMPO SELECTOR ($17c74..$17c9f) branches on.
 * Batch 25 ported that head over the kit's seeded hardware read model, so a case DECLARES the two
 * bytes with `hw_seed=` instead of poking the drop byte and entering below them.
 */
#define WB_SND_MASTER_VOLUME       0x17c57u /* a3+2251, 0..15 */
#define WB_SND_SONG_SPEED          0x17c58u /* a3+2252, a FRACTIONAL row rate added to the
                                             * accumulator each tick; the channels step on its carry */
#define WB_SND_SONG_SPEED_COPY     0x17c59u /* a3+2253 — opcodes $94 and snd_play_song write both */
#define WB_SND_CHANNEL_LOCKS       0x17c5eu /* a3+2258: one byte per channel, "do not write this PSG
                                             * channel". Tested as a LONG first (all three plus the
                                             * unnamed fourth byte) to decide the NOISE register */
#define WB_SND_CHANNEL_LOCKS_LEN   4u       /* `tst.l 2258(a3)` — the fourth byte counts */
#define WB_SND_SONG_LOADED         0x17c63u /* a3+2263: `sf`d by the end-of-song tail at $18016 and by
                                             * nothing else in this tier, which is what makes a stop a
                                             * PAUSE and an END an unload */
#define WB_SND_SONG_UNLOADED       0u       /* `sf 2263(a3)` — Scc's false byte */
#define WB_SND_SONG_LOADED_SET     0xffu    /* `st 2263(a3)` — and its true byte, which is what
                                             * snd_play_song leaves. Every OTHER writer of this field
                                             * is an `sf`, so the pair is the whole of its range */
#define WB_SND_FADE_RATE           0x17c65u /* a3+2265, 0 = no fade */
#define WB_SND_FADE_COUNTDOWN      0x17c66u /* a3+2266, reloaded from the rate */
#define WB_SND_PERIOD_SCRATCH      0x17c68u /* a3+2268, a WORD: the period is stored here and its two
                                             * halves read back out of it one byte at a time */
#define WB_SND_SPEED_ACC           0x17c6au /* a3+2270 */
#define WB_SND_TICK_DROP_VALUE     0x17c6eu /* a3+2274: 0 (50 Hz), $2b (60 Hz) or $48 (mono) */
#define WB_SND_TICK_DROP_ACC       0x17c6fu /* a3+2275 — the whole tick is SKIPPED on its carry, so
                                             * the pair is a fractional tick DROPPER, not a scaler */

/* THE TEMPO SELECTOR'S THREE OUTCOMES, and the two machine bits that choose between them. The
 * fraction is out of 256: $2b drops 43 ticks in every 256 and $48 drops 72, which is what makes a
 * mono machine's music ~28 % slow and a 60 Hz one's ~17 %.
 *
 * BOTH TESTS ARE `btst`+`bne`, so the branch is taken when the bit is SET and the immediate below
 * names the bit's SET meaning — which is the opposite of the register's name in each case, and is
 * why a machine whose hardware reads answer 0 lands on the MONO branch:
 *
 *   $17c7e  btst #7,$fffa01 / bne  — GPIP bit 7 is the mono-monitor detect line and is ACTIVE LOW,
 *                                    so SET means a COLOUR monitor and the branch skips $48;
 *   $17c90  btst #1,$ff820a / bne  — sync bit 1 SET means 50 Hz and the branch skips $2b.
 */
#define WB_SND_TICK_DROP_50HZ      0x00u /* `move.b #0,2274(a3)` — a colour ST at 50 Hz drops none */
#define WB_SND_TICK_DROP_60HZ      0x2bu /* `move.b #$2b,2274(a3)` — 43/256 */
#define WB_SND_TICK_DROP_MONO      0x48u /* `move.b #$48,2274(a3)` — 72/256 */
/* The two MASKS the `btst`s carry. The ADDRESSES they are tested at are os.h's OS_HW_MFP_GPIP and
 * OS_HW_SHIFTER_SYNC — the kit owns those, since both sides of the model decode them; these are the
 * game's own operands, and test_sound.py pins them by running the selector on the kit's declared
 * 50 Hz colour profile, which either mask drifting would send down the wrong arm. */
#define WB_MFP_GPIP_COLOUR_MONITOR 0x80u /* bit 7 of the byte at OS_HW_MFP_GPIP */
#define WB_SHIFTER_SYNC_50HZ       0x02u /* bit 1 of the byte at OS_HW_SHIFTER_SYNC */

#define WB_SND_MASTER_VOLUME_MASK  0x0fu /* `andi.b #15,2251(a3)` after the fade has stepped it */
#define WB_SND_MASTER_VOLUME_FULL  15u   /* `eori.b #15,d0` turns the volume into the ATTENUATION the
                                          * channel's own volume is reduced by, so 15 subtracts 0 */
#define WB_SND_MIXER_CHANNEL_A_BITS 0x09u /* `ori.b #9,d2` — channel A's tone and noise enables. B and
                                           * C are this ROTATED left by their channel number ($12,
                                           * $24), which is also WB_SND_CH_MIXER_MASK's three values */

#define WB_PSG_REG_TONE_A          0u  /* registers 0/1 are channel A fine/coarse, and each channel's
                                        * pair is WB_PSG_REG_TONE_LEN further on */
#define WB_PSG_REG_TONE_LEN        2u
#define WB_PSG_REG_TONE_COARSE     1u  /* the second register of each channel's pair, and the byte
                                        * the module reads back out of WB_SND_PERIOD_SCRATCH */
#define WB_PSG_REG_NOISE_PERIOD    6u  /* written only when NO channel is locked */

/* ---- the game-restart reset ($fe4a) and the life it redraws ($e80c) ---------------------------
 *
 * $fe4a is entered by one `bsr` (from $e59e) and its TAIL by one `jsr $fe8c.l` (from $c00, the path
 * that has just decremented WB_LIVES). So the 136 bytes are two routines: the head clears what only
 * a NEW GAME clears — the level cursor, the lives count, the effect record list, the six HUD slots
 * — and the tail, which both entrants run, redraws the lives and reseeds the meter, the score and
 * the effect-record write pointer.
 */
#define WB_LIVES                   0xbe2u   /* word, and DATA INSIDE player_pending_event_gate's own
                                             * code — the two bytes between the data-disk `jmp` at
                                             * $bdc and the `tst.w` at $be4. FIVE operand sites, not
                                             * the four this plate had: `move.w #$3` here, the
                                             * `subq.w #1` at $bfc, `tst.w $be2.l` at $b4e (which
                                             * picks WHICH game-over message goes up), `tst.w
                                             * $be2.w` at $be4 (the continue prompt's own guard, a
                                             * DIFFERENT frame and a different arm) and the
                                             * `move.w $be2.w,d1` $e80c counts icons down from.
                                             * $be4 is exactly the site a linear sweep misses,
                                             * because this word is what it desyncs on */
#define WB_LIVES_ON_RESTART        3u       /* `move.w #$3,$be2.w` */
#define WB_LEVEL_SEQ_INDEX         0x216beu /* word: ../names.txt's level_seq_index, cleared here */
#define WB_EFFECT_STATE_BD6C       0xbd6cu  /* the fourth of the small state words, cleared with
                                             * WB_EFFECT_STATE_BD66/_BD68 and having no reader among
                                             * the recovered functions */
#define WB_EFFECT_RECORD_EMPTY     0xffffu  /* `move.w #$ffff,$b444.l` — the negative first word
                                             * panel_refresh_record returns on */
#define WB_HUD_METER_ON_RESTART    0x14u    /* `move.w #$14` into BOTH WB_HUD_METER_VALUE and _MAX */
#define WB_STAGE_TUNE_LATCH        0xfa2eu  /* byte inside the code, between $fa2c's `rts` and
                                             * bg_build_buffer. stage_load_window compares
                                             * 8(WB_STAGE_START_PTR) against it and returns without
                                             * calling the sound module when they match
                                             * (../names.txt: sound_last_tune) */
#define WB_STAGE_TUNE_LATCH_RESET  0x20u    /* `move.b #$20,$fa2e.l` */

/* $e80c: WB_LIVES_ICON_SLOTS cells drawn into BOTH screen buffers at once, at a fixed absolute
 * address in each rather than through WB_SCREEN_BACK. A slot below the lives count gets the bitmap;
 * the rest get WB_LIVES_ICON_BLANK. `tst.w d1 / bne` is a NONZERO test, not a sign one, so a
 * negative lives word fills every slot with the bitmap. */
#define WB_LIVES_ICON_BACK         0x704d8u /* `lea $704d8.l,a1` — screen 0 + 0x4d8 */
#define WB_LIVES_ICON_FRONT        0x784d8u /* `lea $784d8.l,a2` — screen 1, the same offset */
#define WB_LIVES_ICON_BITMAP       0xec38u  /* `lea $ec38.l,a0`, re-loaded for EVERY slot, so all
                                             * three draw the same cell */
#define WB_LIVES_ICON_SLOTS        3u       /* `move.w #$2,d0` + `dbf` */
#define WB_LIVES_ICON_ROWS         16u      /* `move.w #$f,d2` + `dbf` */
#define WB_LIVES_ICON_BYTES        8u       /* 16 px over WB_PLANES planes, as two longwords */
#define WB_LIVES_ICON_ROW_SKIP     156u     /* `lea 156(a1),a1` after ONE post-incremented longword:
                                             * 4 + 156 == WB_SCREEN_LINE */
#define WB_LIVES_ICON_REWIND       2552u    /* `lea -2552(a1),a1` — ROWS * WB_SCREEN_LINE less this
                                             * is WB_LIVES_ICON_BYTES, i.e. the next slot */
#define WB_LIVES_ICON_BLANK_HIGH   0xffffu  /* `move.l #$ffff,(a1)+`: plane 0 clear, plane 1 solid */
#define WB_LIVES_ICON_BLANK_LOW    0u       /* `move.l #$0,(a1)`: planes 2 and 3 clear, so the empty
                                             * slot is 16 pixels of colour 2 */

/* ---- the SCENE tier ($dbc0, $de80 — src/scene.c) -----------------------------------------------
 *
 * A SCENE DESCRIPTOR is the 32-byte record WB_RECORD_PTR_10420 points into (the table it is built
 * from lies past the shipped image and is loaded from disk, so nothing here is a shipped value).
 * Its word at WB_SCENE_KIND is what $dbc0 branches on.
 */
#define WB_SCENE_KIND              2u       /* word: `cmpi.w #$1,2(a0)` / `#$2` / `#$4`. src/map.c
                                             * reads the same word as the stamp's tile-set select
                                             * (`cmpi.w #$4,2(a1)` at $1af0) — one field, two
                                             * readings, and this is the canonical name for it */
#define WB_SCENE_KIND_SPEECH       1u       /* an NPC's script of message ids, advanced on fire */
#define WB_SCENE_KIND_SHOP         2u       /* the shop counter — the driver's largest arm */
#define WB_SCENE_KIND_BOSS_DEFEAT  4u       /* the arm WB_STATE_FLAG_A32 selects — and the value the
                                             * 2x2 stamp above tests for its second tile set */
#define WB_SCENE_VARIANT           4u       /* word: 0 = spawn nothing, else picks the fragment
                                             * type below */
#define WB_SCENE_GATE_INDEX        16u      /* byte: `moveq #0,d0 / move.b (a1)+,d0 / beq` — which
                                             * WB_SPAWN_GATE_TABLE entry the speech arm dispatches,
                                             * and zero dispatches none */
#define WB_SCENE_SPEECH_INDEX      17u      /* byte: which WB_SPEECH_SCRIPT_TABLE entry it then
                                             * posts — the byte a refused gate OVERWRITES with
                                             * WB_SPAWN_GATE_REFUSED_SCRIPT, one instruction before
                                             * this read */
#define WB_SCENE_EXIT_ACTION       18u      /* word: which WB_SCENE_EXIT_ACTION_TABLE entry $dfbe
                                             * dispatches on the way out (`move.w 18(a6),d0`) */
#define WB_SCENE_START_INDEX       28u      /* word: which WB_STAGE_START_TABLE entry $dfbe hands
                                             * stage_load_window (`move.w 28(a1),d0 / lsl.w #2`) */
#define WB_SCENE_EXIT_ACTION_TABLE 0x1019cu /* eight longwords, $1019c..$101bb, bounded by the first
                                             * of its own targets ($101bc, a bare `rts`). Entries
                                             * 2..7 are the six effects.h `set_state_*` stubs and
                                             * entry 1 is $101be, src/scene.c's
                                             * scene_exit_action_select_a30_table */
#define WB_SCENE_EXIT_ACTION_COUNT 8u
#define WB_SCENE_EXIT_ALLOC_COUNT  0x21c58u /* word: bumped by entry 1 whenever its allocation found
                                             * a free slot. It has exactly ONE operand site in the
                                             * image — the `lea $21c58.l` at $101f8 — so NOTHING
                                             * ever reads it, and it lies past the program's own end
                                             * ($218d0), so the .PRG ships no part of it */

/* The message the driver posts is always posted the same way: an id into WB_TEXT_REQUEST and a
 * lifetime into WB_TEXT_LIFETIME_REQUEST. The SPEECH arm posts a lifetime of zero (the box waits
 * for the player); every shop arm posts WB_TEXT_LIFETIME_DEFAULT. */
#define WB_SPEECH_LIFETIME         0u       /* `clr.w $c034.l` at $dc1c */

/* $1017c — a longword CURSOR into a script of one-byte message ids. $dc00 posts the byte under it
 * and advances by one; a byte with its SIGN BIT set ends the scene. The scripts are shipped:
 * WB_SPEECH_SCRIPT_TABLE holds eight pointers into WB_SPEECH_SCRIPTS, and the ids resolve through
 * the message table (script 0 = ids 4,5,6,7 = the opening "Hey brave man, listen carefully..."). */
#define WB_SPEECH_SCRIPT_CURSOR    0x1017cu
#define WB_SPEECH_SCRIPT_TABLE     0x1015cu /* eight longwords, $1015c..$1017b, bounded by the
                                             * cursor itself and by its own first target */
#define WB_SPEECH_SCRIPT_COUNT     8u
#define WB_SPEECH_SCRIPTS          0x10180u /* the id bytes the eight pointers name */

/* ---- the SHOP record ---------------------------------------------------------------------------
 *
 * WB_SHOP_RECORD_PTR holds one of the eight pointers in WB_SHOP_RECORD_TABLE; the eight are
 * WB_SHOP_RECORD_BYTES apart, which is what gives the record its length. They too lie past the
 * shipped image. Field roles below are read off the driver's own use of them.
 */
#define WB_SHOP_RECORD_PTR         0x10448u /* longword, planted at $1bcc from the table below */
#define WB_SHOP_RECORD_TABLE       0x10428u /* eight longwords, $10428..$10447, bounded by the
                                             * pointer itself */
#define WB_SHOP_RECORD_COUNT       8u
#define WB_SHOP_RECORD_BYTES       0x46u    /* the shipped pointers' stride: $21a28, $21a6e, ... */
#define WB_SHOP_ITEM1_MSG_FIRST    0u       /* word: the message id the first purchase of item 1
                                             * posts... */
#define WB_SHOP_ITEM1_MSG_REPEAT   2u       /* ...and every later one */
#define WB_SHOP_ITEM2_MSG_FIRST    4u
#define WB_SHOP_ITEM2_MSG_REPEAT   6u
#define WB_SHOP_GREET_MSG_FIRST    14u      /* the greeting arm's three ids, selected by
                                             * WB_SHOP_GREET_COUNT and by the vector-page word
                                             * below */
#define WB_SHOP_GREET_MSG_SECOND   16u
#define WB_SHOP_GREET_MSG_LATER    18u
/* Words 26, 28 and 30 are the three the farewell arm LOADS AND DISCARDS — it posts two hardcoded
 * ids instead (see WB_SHOP_FAREWELL_ID_FIRST). No #define: a register the next instruction
 * overwrites is not program output, so nothing here can read them; ../names.txt records them. */
#define WB_SHOP_VISIT_BUDGET       32u      /* word: `sub.w d0,32(a1)` — every message costs
                                             * WB_SHOP_MESSAGE_COST and every purchase
                                             * WB_SHOP_PURCHASE_COST, and the BORROW ends the visit */
#define WB_SHOP_ITEM1_COUNT        34u      /* word: purchases of item 1 so far */
#define WB_SHOP_ITEM2_COUNT        36u
#define WB_SHOP_GREET_COUNT        40u      /* word: greetings posted so far */
#define WB_SHOP_REFUSED_COUNT      42u      /* word: how many times this shop has turned the player
                                             * away for being broke. $1d52 posts
                                             * WB_SHOP_BROKE_MSG_* by it and bumps it; $dbc0 reads
                                             * the same word as "have you been refused before" —
                                             * `tst.w 42(a1)`, zero leaves the shop for nothing and
                                             * nonzero spends WB_SHOP_MESSAGE_COST first. THIS WORD
                                             * WAS NAMED FOR THAT $dbc0 CONSEQUENCE ALONE until
                                             * batch 41 phase B; the spawn tree's three message ids
                                             * are what say it is a COUNT, and the name is now what
                                             * the word holds rather than what one reader does
                                             * with it */
#define WB_SHOP_FAREWELL_COUNT     44u      /* word: farewells posted so far */
#define WB_SHOP_ITEM1_PRICE        58u      /* word, compared against WB_BCD_COUNTER and then
                                             * subtracted from it by bcd_sub_counter_bd6e */
#define WB_SHOP_ITEM2_PRICE        60u
#define WB_SHOP_ITEM1_EFFECT       62u      /* word: which WB_EFFECT_HANDLER_TABLE entry the
                                             * purchase runs */
#define WB_SHOP_ITEM2_EFFECT       64u
#define WB_SHOP_ITEM2_CURSOR_MSG   66u      /* word: the id actor_behavior_type34 posts when the
                                             * shop CURSOR arrives on the right-hand item — the one
                                             * a fire there buys as WB_SHOP_REQUEST_ITEM2 */
#define WB_SHOP_ITEM1_CURSOR_MSG   68u      /* ...and the left-hand item's. These two are the next
                                             * two words of the record after the effects above; the
                                             * fire mapping at the same x is what says which is
                                             * which (src/behavior.c) */
/* The fields the SPAWN TREE reads (batch 41 phase B) — everything $1bb4 builds the counter's
 * display out of, plus the three ids its tail posts. */
#define WB_SHOP_ENTER_MSG_FIRST     8u      /* word: the id posted the first time the player walks
                                             * in... */
#define WB_SHOP_ENTER_MSG_SECOND   10u      /* ...the second... */
#define WB_SHOP_ENTER_MSG_LATER    12u      /* ...and every later time, which is also the DEFAULT:
                                             * `cmpi.w #$2,38(a0) / beq` falls through to the FIRST
                                             * arm, so a count of 3 or more posts field 8 again */
#define WB_SHOP_ENTER_COUNT        38u      /* word: how many times the counter has been entered.
                                             * Bumped on BOTH of $1d52's paths, so a refusal counts
                                             * as an entry */
#define WB_SHOP_SIGN_SPRITE        48u      /* word: the sprite of the sign above the counter, and
                                             * the word $1d58 tests for WB_SHOP_SIGN_SPRITE_INTRO */
#define WB_SHOP_SIGN_SPRITE_INTRO  0x181u   /* `cmpi.w #$181,48(a0)` — the one sign whose shop can
                                             * refuse a broke player */
#define WB_SHOP_SIGN_XY            50u      /* longword: the sign's (x, y), copied straight into the
                                             * display record's WB_ACTOR_X / WB_ACTOR_Y */
#define WB_SHOP_ITEM1_SPRITE       54u      /* word: what stands at WB_SHOP_DISPLAY_ITEM1_XY — the
                                             * x a fire buys as WB_SHOP_REQUEST_ITEM1 */
#define WB_SHOP_ITEM2_SPRITE       56u
#define WB_SHOP_BROKE_MSG_FIRST    0x11u    /* "   Come back with / some money." */
#define WB_SHOP_BROKE_MSG_SECOND   0x12u    /* "  Never Come Back!!" — the same id the FAREWELL
                                             * arm repeats, WB_SHOP_FAREWELL_ID_REPEAT */
#define WB_SHOP_BROKE_MSG_THIRD    0x13u    /* "You lost wing boots." */
#define WB_SHOP_MESSAGE_COST       2u       /* `move.w #$2,d0` before three of the four `bsr $de80` */
#define WB_SHOP_PURCHASE_COST      3u       /* `move.w #$3,d0` — what a purchase costs instead */
#define WB_SHOP_FAREWELL_ID_FIRST  9u       /* `move.b #$9,$c030.l` — message 9, " Please come
                                             * again.", posted the first time */
#define WB_SHOP_FAREWELL_ID_REPEAT 0x12u    /* `move.b #$12,$c030.l` — message $12, "  Never Come
                                             * Back!!", posted by BOTH later arms */

/* The driver's own state words, all four of them cleared or seeded outside it. */
#define WB_SCENE_MESSAGE_PENDING   0xe026u  /* word: a message is up and the driver is waiting.
                                             * $ffff from every arm that posts one; $e020 (inside
                                             * $dfbe) and $1dc8 also write it */
#define WB_SCENE_MESSAGE_PENDING_SET 0xffffu
#define WB_SHOP_REQUEST            0xe028u  /* word: WHAT the player asked for — 1 = item 1,
                                             * 2 = item 2, 3 = leave. Set at $5308/$531a/$532c off
                                             * the spawn type of the record stood on ($33/$be/$78) */
#define WB_SHOP_REQUEST_ITEM1      1u
#define WB_SHOP_REQUEST_ITEM2      2u
#define WB_SHOP_REQUEST_FAREWELL   3u
#define WB_SCENE_ACK_WAIT          0xe02au  /* word: the driver is waiting for the player to
                                             * acknowledge the box before anything else runs */
#define WB_SHOP_GREET_COUNTDOWN    0xe02cu  /* word, `subq.w #1` per frame; the greeting fires when
                                             * it reaches zero. Seeded $fa at $1e9c */
#define WB_SCENE_MARKER_CELL_PTR   0xe02eu  /* longword: the collision-map cell the exhausted visit
                                             * clears, planted `move.l a6,$e02e.l` at $1964 */
#define WB_SCENE_EXIT_REQUEST      0x1079au /* word: raised $ffff at $10768, one instruction after
                                             * message $63 " Offensive Power Increased." — the
                                             * boss-defeat arm leaves the scene when it is set */

/* ---- $19ac: THE SCENE-SPAWN TREE (src/scene.c, batch 41 phase B) -------------------------------
 *
 * What ENTERS a scene, where $dbc0 above is what runs one once a frame. The same descriptor's
 * WB_SCENE_KIND picks the arm — 1 fills the A30 table with three display records and posts a speech
 * script, 2 builds the shop counter's eight, 4 arms the A32 table for the boss — and every arm ends
 * by handing stage_load_window a map and tile bank out of WB_SCENE_MAP_BANK_TABLE.
 */
#define WB_SCENE_SPAWN_GATE_SLOT   0x998cu  /* WB_ACTOR_TABLE_DEFAULT slot 1, marked free by the
                                             * tree's FIRST instruction whichever arm then runs.
                                             * It is the slot player_pending_event_gate spawns its
                                             * own event actor into (../names.txt, cmt 0x99ac) */

/* The FOURTH dispatch table in the program: four longwords, $e42e..$e43d, bounded by the first of
 * its own targets. Entry 0 holds WB_SPAWN_GATE_ENTRY_0_NOT_AN_ADDRESS and is never fetched, because
 * the caller's `beq.w` skips a script byte of zero before the `lsl.w #2`. */
#define WB_SPAWN_GATE_TABLE        0xe42eu
#define WB_SPAWN_GATE_COUNT        4u
#define WB_SPAWN_GATE_ENTRY_0_NOT_AN_ADDRESS 0x02140202u
#define WB_SPAWN_GATE_REFUSED_SCRIPT 7u     /* `move.b #$7,(a1)` — the speech script a gate whose
                                             * WB_HUD_SLOT_BBC8 does not match forces INSTEAD, by
                                             * overwriting the byte the caller reads next */

/* SEVEN 8-byte entries, $103e8..$1041f, bounded by WB_RECORD_PTR_10420 — the descriptor pointer
 * itself begins where the table ends, which is what says seven and not eight. Each entry is
 * (map pointer, tile bank pointer): a0 and a6 for stage_load_window. Unlike the descriptor and shop
 * tables these ARE shipped, and all seven are live — three distinct maps at $1abcc, $1b870 and
 * $1c894, each with its own bank $a4 bytes on. */
#define WB_SCENE_MAP_BANK_TABLE    0x103e8u
#define WB_SCENE_MAP_BANK_COUNT    7u
#define WB_SCENE_MAP_BANK_BYTES    8u
#define WB_SCENE_MAP_BANK_TILES    4u       /* the second longword of an entry */
#define WB_SCENE_MAP_BANK_INDEX    30u      /* word in the descriptor: `move.w 30(a1),d0 /
                                             * lsl.w #3`, added SIGN-EXTENDED, so nothing bounds it
                                             * and the read is reproduced wherever it lands */
#define WB_SCENE_BOSS_MAP_BANK_OFFSET 0x10u /* ...except on the boss arm, which `move.w #$10,d0`s
                                             * over the index it just shifted — entry 2, always */

/* Which WB_STAGE_START_RECORDS record each arm hands the hinge. */
#define WB_SCENE_START_RECORD_BOSS      0u  /* $1d40c */
#define WB_SCENE_START_RECORD_SHOP      1u  /* $1d416, when the descriptor's WB_SCENE_VARIANT is
                                             * nonzero... */
#define WB_SCENE_START_RECORD_SHOP_ALT  2u  /* ...and $1d420 when it is zero */
#define WB_SCENE_START_RECORD_SPEECH    3u  /* $1d42a, the one whose tune byte is NEGATIVE — so the
                                             * speech arm STOPS the sound module */

/* The three display records the speech arm builds, out of two triples of descriptor words. The
 * first triple is used TWICE: once as it stands and once with the sprite bumped by one and the x by
 * WB_SCENE_SPAWN_PAIR_DX, which is the same pairing the shop's sign gets. */
#define WB_SCENE_SPAWN_PAIR_DX     0x40u    /* `addi.w #$40,d1`, and the high word of the shop
                                             * sign's `addi.l #$400000,(a1)+` — one constant */
#define WB_SCENE_LATE_STAGE_FIRST  5u       /* `cmpi.w #$5,$bd88.l / blt` — SIGNED, on
                                             * WB_STAGE_NUMBER */
#define WB_SCENE_LATE_STAGE_SPRITE 0x175u   /* what the first sprite of a pair becomes from that
                                             * stage on, in BOTH the speech arm and the shop's */
#define WB_SCENE_SPEECH_LIFETIME_HELD 0xffffu /* `move.w #$ffff,$c034.l` — the box the speech arm
                                             * posts never expires on its own, where every arm of
                                             * $dbc0 posts WB_TEXT_LIFETIME_DEFAULT */

/* The eight records the shop arm builds into WB_ACTOR_TABLE_A30, as the longword (x, y) each one's
 * `move.l #imm,(a1)+` plants. Records 2 and 3 take theirs from WB_SHOP_SIGN_XY instead. */
#define WB_SHOP_DISPLAY_ITEM1_XY   0x00330020u /* x $33 — the cursor position a fire here buys as
                                                * WB_SHOP_REQUEST_ITEM1 */
#define WB_SHOP_DISPLAY_ITEM2_XY   0x00be0020u /* x $be — WB_SHOP_REQUEST_ITEM2 */
#define WB_SHOP_DISPLAY_LEAVE_XY   0x00780018u /* x $78 — WB_SHOP_REQUEST_FAREWELL */
#define WB_SHOP_DISPLAY_PRICE1_XY  0x0033002au /* the two price plates, one cell below their items */
#define WB_SHOP_DISPLAY_PRICE2_XY  0x00be002au
#define WB_SHOP_DISPLAY_EXTRA_XY   0x00780030u
#define WB_SHOP_DISPLAY_LEAVE_SPRITE  0x173u
#define WB_SHOP_DISPLAY_PRICE1_SPRITE 0x1a1u   /* ...and the resource shop_render_price_digits
                                                * draws WB_SHOP_ITEM1_PRICE into */
#define WB_SHOP_DISPLAY_PRICE2_SPRITE 0x1a2u
#define WB_SHOP_DISPLAY_EXTRA_SPRITE  0x164u
#define WB_SHOP_DISPLAY_EXTRA_TYPE 0x22u    /* the ONE record of the eight whose WB_ACTOR_TYPE is
                                             * not cleared */
#define WB_SHOP_GREET_COUNTDOWN_RESET 0xfau /* `move.w #$fa,$e02c.l` — 250 frames */

/* The boss arm's own followed record, written straight into WB_ACTOR_FOLLOWED_A32 after the table
 * it lives in has been reset. */
#define WB_SCENE_BOSS_FOLLOW_XY    0x00400080u
#define WB_SCENE_BOSS_FOLLOW_TYPE  1u       /* `move.w #$1,4(a1)` — WB_ACTOR_TYPE, the PLAYER's
                                             * behaviour slot */
#define WB_SCENE_BOSS_FOLLOW_SIZES 0x000a0014u /* `move.l #$a0014,14(a1)` — WB_ACTOR_HALF_WIDTH $a
                                                * over WB_ACTOR_SIZE_SECOND $14 */

/* $1cc0 / $1d1e — the shop's PRICE PLATES. `shop_render_price_digits` rotates a price word a nibble
 * at a time into `glyph_stamp_8_rows`, which is $b850's digit plotter one tier over: the same
 * WB_DIGIT_GLYPHS_ALT font, the same WB_DIGIT_GLYPH_LEN, the same leading-zero latch, but writing
 * into a SPRITE's own bitmap rather than onto the screen. */
#define WB_SHOP_PRICE_DIGITS       4u       /* `move.w #$3,d5` + the `dbf` */
#define WB_SHOP_PRICE_NIBBLE_BITS  4u       /* `rol.w #4,d0` — the digit is the word's TOP nibble */
#define WB_GLYPH_STAMP_MASK_BYTES  2u       /* `lea 2(a0),a0`: a masked sprite's group opens with a
                                             * mask word, and the four plane bytes follow it */
#define WB_GLYPH_STAMP_PLANE_STEP  2u       /* `addq.l #2,a0` between plane bytes */
#define WB_GLYPH_STAMP_ROW_SKIP    14u      /* `lea 14(a0),a0` after the fourth */
#define WB_GLYPH_STAMP_ROW_BYTES   20u      /* == (WB_PLANES - 1) * PLANE_STEP + ROW_SKIP, which
                                             * test/test_scene.py asserts rather than deriving here
                                             * (test/layout.py scrapes plain literals only). Two
                                             * 10-byte groups: a 32-pixel-wide masked sprite */
#define WB_GLYPH_STAMP_NEXT_EVEN   1u       /* an EVEN cursor's next 8-pixel cell is the odd byte of
                                             * its own group... */
#define WB_GLYPH_STAMP_NEXT_ODD    9u       /* ...and an odd one's is the next group's even byte,
                                             * which is what makes the group 10 bytes wide. The two
                                             * `lea -161`/`lea -153` rewinds are these two subtracted
                                             * from WB_DIGIT_ROWS * ROW_BYTES + MASK_BYTES */

/* ---- the eight fragments a defeated boss leaves ------------------------------------------------
 *
 * $6bd4 raises WB_BOSS_DEFEAT_FLAG when the record at WB_BOSS_FRAGMENT_ORIGIN dies while
 * WB_STATE_FLAG_A32 is up; the next frame this arm frees ten slots and, unless the descriptor's
 * variant is zero, fills eight of them in from WB_BOSS_FRAGMENT_PARAMS. The parameter pairs are
 * SYMMETRIC — (8,$f) ($a,$c) ($c,8) ($e,4) and then the same four backwards — and the loop raises
 * WB_ACTOR_FLAG_SIDE_BIT for the first four and clears it for the last four, so the eight leave in
 * mirrored pairs.
 */
#define WB_BOSS_DEFEAT_FLAG        0xdfacu  /* word, INSIDE the code: it sits between $df9e's `rts`
                                             * and the parameter table below */
#define WB_BOSS_DEFEAT_SET         0xffffu  /* `move.w #$ffff,$dfac.l` at $6bd4 — what actor_defeat
                                             * raises when the record at WB_BOSS_FRAGMENT_ORIGIN is
                                             * the one that died */
#define WB_BOSS_DEFEAT_SFX         0x19u    /* `move.w #$19,d0` beside a `clr.w d1`: SFX 25 on
                                             * WB_SND_CHANNEL_A, the highest id the table holds */
#define WB_BOSS_DEFEAT_METER_BONUS 4u       /* `move.w #$4,d0 / bsr $b6fe` — hud_meter_add_clamped's
                                             * ONE caller in the image */
#define WB_BOSS_FRAGMENT_PARAMS    0xdfaeu  /* 16 bytes, $dfae..$dfbd, ending exactly where $dfbe
                                             * begins — two per fragment */
#define WB_BOSS_FRAGMENT_PARAM_LEN 2u
#define WB_BOSS_FRAGMENT_SLOTS     0x9eb4u  /* == WB_ACTOR_TABLE_A32 + 4 records */
#define WB_BOSS_FRAGMENT_COUNT     8u       /* `move.w #$7,d6` + `dbf`, and `move.w #$7,d7` for the
                                             * free that precedes it */
#define WB_BOSS_HEAD_SLOT_COUNT    2u       /* `move.w #$1,d7` over WB_ACTOR_TABLE_A32 */
#define WB_BOSS_FRAGMENT_ORIGIN    0x9e94u  /* `move.l $9e94.l,d0` — slot 3's X/Y longword, copied
                                             * into all eight fragments, so they start where it did */
#define WB_BOSS_FRAGMENT_TYPE_1    0x1cu    /* WB_ACTOR_TYPE when the variant is 1... */
#define WB_BOSS_FRAGMENT_TYPE_2    0x1du    /* ...and for every other nonzero variant */
#define WB_BOSS_FRAGMENT_SIZE      0x80008u /* `move.l #$80008,14(a1)`: WB_ACTOR_HALF_WIDTH and
                                             * WB_ACTOR_SIZE_SECOND in one store */
#define WB_BOSS_FRAGMENT_FIELD_12  0xc8u    /* `move.b #$c8,12(a1)` — a byte field nothing
                                             * reconstructed here reads */
#define WB_BOSS_FRAGMENT_FIELD_30  8u       /* `move.b #$8,30(a1)` */
#define WB_BOSS_FRAGMENT_MIRROR_AT 3u       /* `cmp.w #$3,d6 / ble` — the counter at or below which
                                             * the side bit is CLEARED rather than set */
/* WB_ACTOR_FIELD_10 / _12 used to be defined here, where $dbc0's fragment arm needed them. Batch 22
 * made the respawn continuation a second writer of both, so they moved up into the actor record's
 * own field block with every other WB_ACTOR_* offset. */

/* ---- the effect handler table ------------------------------------------------------------------
 *
 * The 23 longwords at $1023a, indexed by WB_SHOP_ITEM1_EFFECT / WB_SHOP_ITEM2_EFFECT and holding
 * exactly the 23 effects.h handlers at $10296..$103dc. The count is bounded by the table's own
 * first target, the way WB_SCENE_EXIT_ACTION_TABLE's is; test/test_scene.py pins every entry.
 */
#define WB_EFFECT_HANDLER_TABLE    0x1023au
#define WB_EFFECT_HANDLER_COUNT    23u
#define WB_EFFECT_HANDLER_SHIFT    2u       /* `lsl.w #2,d0` — the index is scaled to a longword */
#define WB_EFFECT_HANDLER_PUSH_FIRST 18u    /* the four PUSH handlers, which are the only ones that
                                             * touch an ADDRESS register: `movea.l $b546,a1` leaves
                                             * a1 on the record they pushed, and the dispatcher's
                                             * next `sub.w d0,32(a1)` spends through THAT */
#define WB_EFFECT_HANDLER_PUSH_COUNT 4u

/* ---- two absolute operands that are NOT record fields -------------------------------------------
 *
 * `cmpi.w #$1,$2c.l` at $dcd4 and `cmpi.w #$1,$28.l` at $dd42 read the 68000 VECTOR PAGE — the
 * high words of the Line-F and Line-A exception vectors. Both sit exactly where the sibling test
 * one branch above them reads a RECORD field at the same displacement (`cmpi.w #$0,44(a1)` and
 * `cmpi.w #$0,40(a1)`), and the encodings differ only by the lost `(a1)`: `0c69 0001 002c` is what
 * was meant and `0c79 0001 0000002c` is what shipped. So these are one source-level slip, twice.
 * Under TOS both vectors point into ROM and neither word can be 1, which makes the middle arm of
 * each pair DEAD ON HARDWARE; test/test_scene.py reaches it by seeding the vector page, since that
 * is the only thing the instruction actually reads.
 */
#define WB_VECTOR_LINE_A           0x28u
#define WB_VECTOR_LINE_F           0x2cu
#define WB_VECTOR_ARM_SELECTOR     1u       /* the `#$1` both compare against */

/* ---- the game's PRNG ($68c6) and the one draw over it this batch ports ($e1f0; src/rng.c) ------
 *
 * Three free-running counters, each incremented and CLEARED WHEN IT REACHES its own limit. LIMIT
 * rather than modulus, and the difference is the whole reading: `addq.w #1 / cmpi.w #N / bne /
 * clr.w` tests for EQUALITY, so a counter seeded above N never meets it again and runs on to $ffff
 * instead of wrapping. The result is the three summed onto one entropy term.
 */
#define WB_RNG_COUNTER_A           0x6932u  /* three words immediately past rng_next's own `rts` */
#define WB_RNG_COUNTER_B           0x6934u
#define WB_RNG_COUNTER_C           0x6936u
#define WB_RNG_COUNTER_LEN         2u
#define WB_RNG_LIMIT_A             0x25u    /* `cmpi.w #$25,$6932.l / bne / clr.w` */
#define WB_RNG_LIMIT_B             0x17u
#define WB_RNG_LIMIT_C             0x11u
/* THE VIDEO COUNTER IS THE KIT'S CONSTANT NOW, not this header's. `move.b $ff8209.l,d0` at $68d0
 * (and $51ae/$51b6's pair in $51ac) reads the shifter's video-address counter, which the kit's
 * Phase 7 table models as OS_HW_SHIFTER_VCOUNT_LOW / _MID — src/rng.c calls hw_read8 with the kit's
 * name and there is no game-side C consumer left. Two unpinned names for one address is the drift
 * CLAUDE.md §5 forbids, so the game-side spelling lives in test/leaf.py beside MFP_GPIP (the
 * disassembly's operand, checkable against the bytes) and test_sound.py pins the whole tuple equal
 * to the model's own table. Nothing is defined here. */

/* $e1f0: the one consumer of rng_next this batch ports. WB_STAGE_NUMBER is PACKED BCD — which is
 * what `cmp.w #9 / ble / subq.w #6` is: subtracting 6 turns $10..$19 into 10..19, and
 * hud_draw_stage_number drawing that word's LOW BYTE as two digits is the other half of the reading.
 * The 0-based row then indexes WB_STAGE_KIND_ROW bytes, one of which an rng draw picks. */
#define WB_BUS_ADDR_MASK           0xffffffu /* The 68000's ADDRESS BUS is 24 bits wide: the top byte
                                             * of a computed effective address is not wired to
                                             * anything, so $0100e3a3 and $0000e3a3 are one location.
                                             * The indexed read below is the one place a
                                             * reconstruction here can compute an address that far up
                                             * (an entry d2 whose high half `add.l` folds into the
                                             * index), and the mask is what makes the C reach the
                                             * byte the 68000 does instead of falling through its
                                             * off-image guard. The kit's shim.c holds the same
                                             * constant as BUS_ADDR_MASK but does not export it; the
                                             * test/test_rng.py case that runs an address past the
                                             * bus IS the pin between the two spellings */
#define WB_STAGE_KIND_TABLE        0xe382u  /* `lea $e382.l,a2`, its only reference in the image */
#define WB_STAGE_KIND_TABLE_ROWS   22u      /* == ($e432 - $e382) / WB_STAGE_KIND_ROW. Self-bounding
                                             * at BOTH ends: $e222's sibling table (32 per stage,
                                             * $e1c8's) ends exactly on this one's base, and this one
                                             * ends exactly on the three longword handler pointers at
                                             * $e432, whose first entry is the code at $e43e. The
                                             * CODE bounds the row at neither end — a stage number of
                                             * 0 indexes row -1 */
#define WB_STAGE_KIND_ROW          8u       /* `lsl.w #3,d2` + `andi.l #$7,d0`: eight candidates per
                                             * stage, one drawn at random */
#define WB_STAGE_KIND_ROW_SHIFT    3u       /* == log2(WB_STAGE_KIND_ROW) */
#define WB_STAGE_KIND_DRAW_MASK    7u       /* `andi.l #$7,d0` — the whole LONGWORD is masked, so
                                             * rng_next's untouched high half cannot reach the sum */
#define WB_STAGE_KIND_MASK         0x1fu    /* `andi.l #$1f,d0` on the way out: five bits, so the
                                             * table's own $10..$14 bytes pass through unchanged.
                                             * SHARED with $e1c8, whose last fourteen bytes are
                                             * these */

/* $e1c8, the SIBLING DRAW: the same routine with three operands changed and a `bra.w` into the tail
 * above instead of a tail of its own. Its table ends exactly where WB_STAGE_KIND_TABLE begins and
 * BEGINS exactly where stage_random_kind8's body ends, so the two bound each other at both ends. */
#define WB_STAGE_KIND32_TABLE      0xe222u  /* `lea $e222.l,a2`, its only reference in the image */
#define WB_STAGE_KIND32_TABLE_ROWS 11u      /* == ($e382 - $e222) / WB_STAGE_KIND32_ROW — HALF the
                                             * rows the 8-wide table has, so a stage number past 11
                                             * indexes off the end of this one while still inside
                                             * the other. The code bounds it at neither end */
#define WB_STAGE_KIND32_ROW        32u      /* `lsl.w #5,d2` + `andi.l #$1f,d0`: 32 candidates */
#define WB_STAGE_KIND32_ROW_SHIFT  5u       /* == log2(WB_STAGE_KIND32_ROW) */
#define WB_STAGE_KIND32_DRAW_MASK  0x1fu    /* `andi.l #$1f,d0` on the DRAW — numerically
                                             * WB_STAGE_KIND_MASK, and a different instruction at a
                                             * different address doing a different job */
#define WB_STAGE_NUMBER_BCD_LIMIT  9u       /* `cmp.w #$9,d2 / ble` — at or below this the number is
                                             * already its own decimal value */
#define WB_STAGE_NUMBER_BCD_CARRY  6u       /* `subq.w #6,d2` — one BCD tens carry */

#endif /* WONDERBOY_H */
