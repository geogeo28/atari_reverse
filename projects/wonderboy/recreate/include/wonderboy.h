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
 * THE HUD SLOT ARRAY. $bbbe..$bbc9 is six 2-byte slots, each `{value, changed}`. `FUN_0000b8f0`
 * ($b8f0) walks the six `changed` bytes every frame: a nonzero one is cleared, a per-slot flag in
 * the $dbb6.. block is raised, the slot's cell is cleared ($bb8a) and — when `value` is nonzero —
 * an icon is OR-blitted over it ($bba0). So the setters' single `move.w #$Nff,slot.l` means "value
 * := N, and redraw me". The value's own meaning differs slot by slot and is NOT identified: $bbbe
 * and $bbc0 are counted DOWN one per use by the damage paths at $69fe/$6b46 (which, on reaching
 * zero, rearm the slot as $00ff and post a message), while $bbc8 is tested against 1..6 as an icon
 * variant. The sixth slot, $bbc4, is untouched by the handlers ported here — ../names.txt names it
 * and records its readers, but no reconstruction needs its address, so it gets no constant here.
 */
#define WB_HUD_SLOT_BBBE     0xbbbeu  /* counted down at $69fe: the damage path spends it */
#define WB_HUD_SLOT_BBC0     0xbbc0u  /* counted down at $6b46, likewise */
#define WB_HUD_SLOT_BBC2     0xbbc2u  /* the one slot set to $80 rather than a small count */
#define WB_HUD_SLOT_BBC6     0xbbc6u
#define WB_HUD_SLOT_BBC8     0xbbc8u  /* read as a 1..6 icon variant at $b8f0, not as a count */

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
#define WB_EFFECT_RECORD_WRITE_PTR 0xb546u
#define WB_EFFECT_RECORD_PTR_LEN   4u
#define WB_EFFECT_RECORD_LEN       2u   /* one record is one word; its two byte fields are unknown */

#endif /* WONDERBOY_H */
