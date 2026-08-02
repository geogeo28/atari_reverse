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
 * against 1..6 as an icon variant. The fourth slot, $bbc4, is untouched by the handlers in
 * src/effects.c; the slot pass draws it like the other five, which is why it has a constant.
 */
#define WB_HUD_SLOT_BBBE     0xbbbeu  /* counted down at $69fe: the damage path spends it */
#define WB_HUD_SLOT_BBC0     0xbbc0u  /* counted down at $6b46, likewise */
#define WB_HUD_SLOT_BBC2     0xbbc2u  /* the one slot set to $80 rather than a small count */
#define WB_HUD_SLOT_BBC4     0xbbc4u  /* no writer among the ported handlers (../names.txt) */
#define WB_HUD_SLOT_BBC6     0xbbc6u
#define WB_HUD_SLOT_BBC8     0xbbc8u  /* read as a 1..6 icon variant at $b8f0, not as a count */
#define WB_HUD_SLOTS         6u       /* how many the pass at $b8f0 walks */
#define WB_HUD_SLOT_REQUEST  1u       /* byte +1 of a slot: "redraw me", tested then cleared */

/* The meter drawn in four-unit cells by `FUN_0000b61e` ($b61e): `value/4` filled cells then
 * `max/4 - value/4` empty ones, so both are consumed as counts and not as flags. `max` is set to
 * $18..$28 from thresholds on $bd70 ($b74a); `value` is spent by the damage path, ticked by $e032,
 * and — by the three handlers ported here — raised by 4 or 2 (clamped) or restored to `max`. */
#define WB_HUD_METER_VALUE   0xb6fau
#define WB_HUD_METER_MAX     0xb6f8u

/* Three state words the handlers set to a small ordinal (1..4, 1..5, 1..3 respectively), and one
 * more the three $bd68 handlers stamp with 2 on the way. All four are cleared together by the
 * new-game reset at $fe4a; only $bd66 has a reader in the recovered code ($69fe, which turns it
 * into `12 - 2*value`), so what the ordinals select is open. */
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
#define WB_DIGIT_GLYPHS_ALT       0x145bcu /* ...and the ones for font_select == 1 ($1d0a leas it
                                            * too, so this table has a second, unrecovered user) */
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

#endif /* WONDERBOY_H */
