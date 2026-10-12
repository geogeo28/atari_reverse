/* aes/gemstart.h — GEMSTART: how the AES is entered and what it lays before any C of it runs (`src/aes/gemstart.S`).
 *
 *   $fd9eca gem_entry          the program the BIOS starts (`exec_os`, the AES basepage's p_tbase): ENTERED BY NO CALL
 *                              AND NEVER RETURNING. It takes a stack of its own, gives GEMDOS back all the TPA but the
 *                              program, goes to supervisor state for good, lays its words, copies the Line-F handler
 *                              into a Malloc block where vector $2c's high byte says the vector is still the BIOS's,
 *                              has the ROM's resources copied (rom_rsc_init) — and then, FOR EVER: THEGLO cleared,
 *                              three routines stored by value, the stack moved to UDA0's top, gem_main called
 *   $fd9fc6 gem_gemdos_call    a `trap #1` over the frame its caller pushed, the call's return address parked in a
 *                              word of RAM round it; the glue's verdict words set from D0 (the shell utilities', band 6)
 *   $fee8c2 the Line-F handler what gem_entry copies, with the 38 bytes behind it: DATA to this build
 *
 * NO C SPELLING (the user's rule is C first: this is what is left when C cannot say it). gem_entry SETS UP THE FIRST
 * STACK — it is the program's entry, with no caller and no return, loads the stack pointer three times (`#$898e`,
 * Super's own switch, UDA0's top) and is the caller whose `jsr` puts gem_main on the process's stack; gem_gemdos_call
 * pops its own return address so that the frame GEMDOS reads is its caller's.
 *
 * THE FIRST STACK is 134 bytes, `[$890e, $8994)`: directly ABOVE gem_entry's own live words ($8904..$890d, read by
 * the reader, gsx_init and the desk long after) and directly UNDER the three status-register save words
 * (AES_SR_DISPATCH and its two neighbours). rom_rsc_init — C, with its Malloc and its 17 KB copy — size_theglo and
 * three GEMDOS traps run on it (`test/aes_stack.py` reads how deep this build goes).
 */
#ifndef TOS102US_AES_GEMSTART_H
#define TOS102US_AES_GEMSTART_H

#include "addrs.h"
#include "aes/aes.h"

/* ---- the first stack, and the words under it ---------------------------------------------------------------------- */
#define GEM_FIRST_STACK       0x898e     /* the USER stack gem_entry takes first ($fd9ecc movea.l #$898e,sp); Super
                                          * hands it on as the supervisor's and `addq #6` leaves that at $8994        */
#define GEM_START_LONG_8904   0x8904     /* long := 0: nothing in the AES's text reads it ($fd9f24)                   */
#define GEM_START_WORD_890C   0x890c     /* word := 1: the desk's, which stores it again ($fdf068, $fe265e): band 6's
                                          * to name                              ($fd9f1c)                            */
#define GEM_NO_RESCHANGE      0          /* AES_GL_RSCHANGE: no change asked     ($fd9f0c move.w #0,$890a)            */
#define GEM_FIRST_DEVICE      1          /* AES_GL_RESTYPE until the INF or the workstation says ($fd9f14)            */
#define GEM_START_WORD_890C_SET 1        /* ($fd9f1c move.w #1,$890c)                                                 */
/* AES_DISK_USABLE := 1 ($fd9f64) — AND THE 1 DOES NOT LAST: `$8992` is the first stack's TOP WORD, and the next `jsr`
 * gem_entry makes there (size_theglo's, the loop's first instruction) pushes its return address over it. What the INF
 * reader and the loader then test is THAT ADDRESS'S LOW WORD: `$9f78` in the ROM, wherever the instruction is linked
 * in a build — or, where an interrupt is taken on the first stack before `movea.l a6,sp` leaves it, the low word of
 * the PC it interrupted (its frame lies on the same bytes: the machine's own boots leave `$9f80` / `$9f82`, the clear
 * loop's). Non-zero by layout, which `test/test_aes_gemstart.py` holds for the whole stretch on both blobs. */
#define GEM_DISK_USABLE       1          /* ($fd9f64 move.w #1,$8992)                                                 */

/* ---- what gem_entry asks GEMDOS -------------------------------------------------------------------------------------- */
/* Mshrink(0, basepage, text + data + BSS + the basepage): the TPA but the program given back. */
#define GEM_BASEPAGE_BYTES    0x100      /* ($fd9ee2 add.l #256,d0)                                                   */
#define GEM_BASEPAGE_ARGUMENT 4          /* the basepage, above the stack pointer the program starts on ($fd9ed2)     */
#define GEM_MSHRINK_FRAME_BYTES 12       /* function.w, 0.w, block.l, bytes.l    ($fd9ef4 adda.l #12,sp)              */
/* Super(sp): the user stack made the supervisor's — the frame is dropped with `addq.w`, the ROM's own word. */
#define GEM_SUPER_FRAME_BYTES 6          /* function.w, stack.l                  ($fd9f02 addq.w #6,sp)               */
#define GEM_MALLOC_FRAME_BYTES 6         /* function.w, bytes.l                  ($fd9f42 addq.l #6,sp)               */

/* ---- the three routines stored by value, and the stack gem_main runs on ----------------------------------------------- */
/* The tick glue's address, kept for gem_main to hand vex_timv (gsx_tick, $fda2ca). */
#define AES_TICK_ROUTINE      0x947e     /* long                                 ($fd9f98 move.l a0,$947e)            */
/* UDA0 — THEGLO's first 1,866 bytes: the shell's saved state, then its stack, whose top is UDA1. */
#define AES_UDA0_BYTES        (AES_UDA1 - AES_THEGLO)                           /* ($fd9fb2 adda.l #1866,a6)           */

/* ---- gem_gemdos_call's verdict ------------------------------------------------------------------------------------- */
#define GEM_DOS_NO_ERROR      0          /* AES_DOS_ERR and AES_DOS_AX before the trap ($fd9fcc, $fd9fd4)             */
#define GEM_DOS_FAILED        1          /* AES_DOS_ERR where D0.l < 0           ($fd9fec move.w #1,$98ec)            */

#endif /* TOS102US_AES_GEMSTART_H */
