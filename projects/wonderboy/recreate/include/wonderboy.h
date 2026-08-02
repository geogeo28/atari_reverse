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
 * Nothing includes this header yet: src/ is empty. It is Python's canonical source for now, and the
 * first reconstructed core's too.
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

#endif /* WONDERBOY_H */
