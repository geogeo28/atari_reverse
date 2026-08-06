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
#define WB_HUD_SLOT_REARM    0x00ffu  /* `move.w #$ff,slot.l` — the whole WORD both damage paths
                                       * write on the frame a slot's last charge is spent: the
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
                                               * LEFT. Its only reader in the image is the
                                               * `btst #3,8(a1)` at $51e, inside the routine at
                                               * $50a, which reads it on the FOLLOWED record */
#define WB_ACTOR_FLAG_FLICKER_BIT    6u       /* set -> the projection publishes no sprite on the
                                               * frames WB_FRAME_TOGGLE is nonzero, i.e. the record
                                               * is drawn every other frame */
#define WB_ACTOR_OUT_OF_REACH        0xffffu  /* `move.w #$ffff,d0` — $67f8's "farther than d0" */
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
#define WB_ACTOR_TYPE_PLAYER         1u       /* `cmpi.w #$1,4(a0)` — the only value anything
                                               * reconstructed here tests for */
#define WB_ACTOR_FLAGS2              9u       /* the SECOND flag byte; `bset`/`bclr` reach it with
                                               * their own bit numbers, and `clr.w 8(a1)` clears
                                               * WB_ACTOR_FLAGS and this one together */
#define WB_ACTOR_SPEED               11u      /* byte: the fall step $14d6 accelerates, $2af2 sets
                                               * from d0 and the landing arm of $1400 clears */
#define WB_ACTOR_FIELD_18            18u      /* byte, cleared by the spawn; no reader in anything
                                               * reconstructed here */
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
#define WB_ACTOR_FIELD_22            22u      /* byte, cleared by $10a2's player arm */
#define WB_ACTOR_FIELD_30            30u      /* two bytes the spawn clears; $ff42 reads 30 as a
                                               * flag and counts 31 down */
#define WB_ACTOR_FIELD_31            31u
#define WB_ACTOR_HALF_WIDTH          14u      /* word: half the footprint, in pixels. The map probes
                                               * measure from `x - half_width` and $13c8 hands
                                               * $1400 twice this as the span to scan */
#define WB_ACTOR_SIZE_SECOND         16u      /* word: the other half of the longword the spawn
                                               * stamps at WB_ACTOR_HALF_WIDTH. Nothing
                                               * reconstructed here reads it */
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
#define WB_ACTOR_FLAGS2_SPAWNED_BIT  2u       /* the one bit the spawn raises */
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
#define WB_SPAWN_KILL_COUNT          6u       /* word: `addq.w #1,6(a1)` at $6bfa, and the template
                                               * retires once `cmpi.w #$2,6(a1)` stops being `ble` */
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
#define WB_BG_BUILD_CARRY          0xfe0cu /* WB_PLANES words of scratch between $fd46's `rts` and
                                            * WB_STAGE_MAP_PTR: the first cell's shifted-out bits,
                                            * held until the row's LAST cell is written so the
                                            * 128-byte row closes as a ring. The band's four
                                            * addresses are the routine's only write outside the
                                            * buffers, and it is a SECOND scratch of the same shape
                                            * as WB_BG_PRESHIFT_CARRY, which the row-at-a-time
                                            * pre-shift uses */

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
                                            * `clr.w (a0)+` — 18 bytes cleared as one run */
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
 * The module ($17adc..$1abc8) is SELF-CONTAINED AND PC-RELATIVE: every routine in it opens with
 * `lea $1738c(pc),a3` and reaches its own tables through that base, so the absolute addresses below
 * are what those PC-relative operands resolve to in the image the harness loads. Only the state
 * `snd_trigger_effect` touches is named here; the rest of the module's map is in
 * ../notes/sound_module_recon.md and ../names.txt.
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

/* ---- the game-restart reset ($fe4a) and the life it redraws ($e80c) ---------------------------
 *
 * $fe4a is entered by one `bsr` (from $e59e) and its TAIL by one `jsr $fe8c.l` (from $c00, the path
 * that has just decremented WB_LIVES). So the 136 bytes are two routines: the head clears what only
 * a NEW GAME clears — the level cursor, the lives count, the effect record list, the six HUD slots
 * — and the tail, which both entrants run, redraws the lives and reseeds the meter, the score and
 * the effect-record write pointer.
 */
#define WB_LIVES                   0xbe2u   /* word. FOUR operand sites: `move.w #$3` here, the
                                             * `subq.w #1` at $bfc, `tst.w` at $b4e and the
                                             * `move.w $be2.w,d1` $e80c counts icons down from */
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
/* The descriptor's word 18 is which WB_SCENE_EXIT_ACTION_TABLE entry $dfbe calls on the way out.
 * It has no #define: $dfbe is not ported, so nothing here reads it; ../names.txt records it. */
#define WB_SCENE_EXIT_ACTION_TABLE 0x1019cu /* eight longwords, $1019c..$101bb, bounded by the first
                                             * of its own targets ($101bc, a bare `rts`). Entries
                                             * 2..7 are the six effects.h `set_state_*` stubs;
                                             * entry 1 ($101be) is a routine nothing has read */
#define WB_SCENE_EXIT_ACTION_COUNT 8u

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
#define WB_SHOP_LEAVE_CHARGED      42u      /* word: `tst.w 42(a1)` — zero leaves the shop for
                                             * nothing, nonzero spends WB_SHOP_MESSAGE_COST first */
#define WB_SHOP_FAREWELL_COUNT     44u      /* word: farewells posted so far */
#define WB_SHOP_ITEM1_PRICE        58u      /* word, compared against WB_BCD_COUNTER and then
                                             * subtracted from it by bcd_sub_counter_bd6e */
#define WB_SHOP_ITEM2_PRICE        60u
#define WB_SHOP_ITEM1_EFFECT       62u      /* word: which WB_EFFECT_HANDLER_TABLE entry the
                                             * purchase runs */
#define WB_SHOP_ITEM2_EFFECT       64u
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
#define WB_ACTOR_FIELD_10          10u      /* byte: takes the SAME parameter byte as
                                             * WB_ACTOR_SPEED, which is written immediately after it */
#define WB_ACTOR_FIELD_12          12u

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

#endif /* WONDERBOY_H */
