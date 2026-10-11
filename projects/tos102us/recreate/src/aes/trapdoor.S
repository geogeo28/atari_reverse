/* trapdoor.S — THE TRAP DOOR as the ROM spells it (`aes/trapdoor.h`): `trap #2`'s handler, its way out and the
 * desk's G_USERDEF door, `$fe3ea6..$fe3f5d`, BYTE FOR BYTE — and aes_entry, `$fe65aa..$fe65c1`, as the ROM's own
 * INSTRUCTION STREAM with its three Line-F call words made `jsr`s.
 *
 * A KIND OF ITS OWN (`atari/target.mk`: TRAPDOOR_SOURCES), the switch's sibling (`switch.S`): the ROM's bytes, no C
 * twin a build could link instead, no row of `include/transcribed.h` and no bar it was measured over. C FIRST still
 * holds for everything behind it that can be C: the marshal and the opcode switch are C (`gemsuper.c`), `jsr`ed from
 * aes_entry through the thunk at the end of this file.
 *
 * WHY EACH IS ASSEMBLY, read from its body:
 *   the handler   an exception's entry: it switches on D0 before any register may be touched; its VDI arm leaves by
 *                 an `rts` through a pushed vector, its Pterm arm by a `trap` that never comes back; its AES arm
 *                 parks D1-A6 on the USER stack (`move.l usp,a0`), leaves the stack the exception came in on for
 *                 the process's own (the UDA's) and calls with nothing saved;
 *   the way out   is entered by a call it never returns from: it drops the whole chain of frames above it BY A
 *                 CONSTANT, stores the stack that leaves as the process's, takes the trap's stack back and `rte`s;
 *   aes_entry     is the function whose frame that constant counts: Alcyon's `link a6,#-4` and one longword of
 *                 local are the contract, and no compiler is held to it;
 *   ub_trampoline moves to another stack round a call and back, a register its only local.
 *
 * TWO PINS (`test/test_aes_trapdoor.py`). The region is BYTE-EXACT but for FIVE longwords: the four `jsr`s of the
 * mask brackets go to `switch.S`'s two, the `movea.l #` of aes_entry to the stream below. aes_entry is held
 * INSTRUCTION BY INSTRUCTION under the stream kind (`test/transcription.py`, `assert_stream`): every instruction the
 * ROM's but the three Line-F call words, each NAMED, and the one short branch across the first.
 *
 * ONE WORD STILL NAMES THE ROM: ub_trampoline's `jsr $fde844` — the desk's own draw code, band 6's. It is the ROM's
 * byte, a census entry (`test_aes_rom_data.py`) and the one declared `jsr` of a build into the AES's ROM text
 * (`bench/tier3.py`: ROM_CALLS_OWED_TO_A_LATER_BAND) — owed the day that routine has a body of ours.
 *
 * WHAT A `jsr` CHANGES FOR THE CALLEE, AND WHY IT IS RIGHT (as for disp, `switch.S`): the Line-F handler enters a
 * routine with the return address on the stack, as a `jsr` does — so the way out's constant counts the same bytes —
 * and with A0, D1 and D2 its own leavings. The dispatcher saves the caller's whole context, so the ROM's parked
 * context holds the handler's three where ours holds aes_entry's own: bytes of a UDA that differ BY NATURE between
 * the builds, and dead the moment the call is over (the way out reloads D1-A6 from the user stack).
 *
 * D0'S HIGH WORD. The way out gives a program D0.w = 0 (the word aes_entry cleared) and reloads D1-A6; D0's HIGH
 * word nothing sets. In the ROM it is the high word of the last LONGWORD Alcyon's code moved into D0 on the calling
 * process's path — the high half of an address of the machine's layout — or, where the opcode's arm moves none
 * (appl_init), the program's own, still there from its trap. In a build it is GCC's last longword. A DECLARED
 * DIVERGENCE (`test_aes_trapdoor_rows.py` holds what both leave, case by case and blob by blob): no instruction here
 * can reproduce it — once the routine under the arm has returned the value is in no register and no byte.
 *
 * THE DEAD TAIL. aes_entry's Line-F return ($fe65c2) is not here: the way out ends in `rte` on every path
 * (`test_aes_trapdoor.py` proves it from the bytes), so nothing ever executes it. Nor does the handler's `jsr (a0)`
 * ever return: the way out is the instruction after it only by the ROM's layout, which the region keeps.
 *
 * REGISTERS AND STACKS. The handler is entered in supervisor state on whatever stack the trap was taken on, the
 * program's frame {SR, PC} under SP. The C aes_entry `jsr`s runs on THE RUNNING PROCESS'S UDA STACK (a static
 * process's 1,196 to 1,792 bytes, an allocated accessory's 1,788: `test/aes_stack.py` reads how deep our build goes).
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/trapdoor.h"

/* The registers parked on the program's stack round its AES call, in `movem`'s list ($fe3ed2, $fe3f30: mask $7ffe).
 * A0 is in the list and is NOT the program's: it holds the user stack pointer by then, and the reload's `(a0)+`
 * leaves it that pointer again. */
#define PROGRAM_S_REGISTERS   %d1-%d7/%a0-%a6

    .text

/* ==== $fe3ea6..$fe3f5d: the handler, the way out, ub_trampoline ====================================================== */

/* ---- trap #2's handler, $fe3ea6: D0.w 0 -> Pterm(0); 200, 201 -> the AES; anything else -> the handler GEM found --- */
    .globl  aes_rom_trap2
    .type   aes_rom_trap2,@function
aes_rom_trap2:
    cmpi.w  #GEM_SELECTOR_PTERM,%d0
    beq.s   .Lpterm
    cmpi.w  #GEM_SELECTOR_AES,%d0
    beq.s   .Laes
    cmpi.w  #GEM_SELECTOR_AES_ALT,%d0
    beq.s   .Laes
    move.l  (SYSVAR_VDI_ENTRY).l,-(%sp)             /* the VDI arm: on, by an `rts` through the vector saved */
    rts
.Lpterm:
    move.w  #TRAP2_PTERM_STATUS,-(%sp)              /* Pterm(0) — and never back */
    move.w  #GEMDOS_PTERM_FN,-(%sp)
    trap    #1
.Laes:
    M68K_JSR_LONG(aes_rom_spl7_save)                /* $fe3eca */
    move.l  %usp,%a0
    movem.l PROGRAM_S_REGISTERS,-(%a0)              /* parked on the program's own stack */
    move.l  %a0,%usp
    movea.l (AES_RLR).l,%a6
    movea.l PD_UDA(%a6),%a6
    move.w  #UDA_INSIDE_THE_AES,(%a6)               /* UDA_IN_SUPER, the UDA's first word */
    move.l  %a0,UDA_USER_SP(%a6)
    move.l  %sp,UDA_TRAP_SSP(%a6)
    movea.l UDA_SUPER_SP(%a6),%sp                   /* the process's own stack from here on */
    M68K_JSR_LONG(aes_rom_spl_restore)              /* $fe3ef2 */
    move.l  %d1,-(%sp)                              /* the parameter block */
    move.w  #TRAP2_NO_SECOND_WORD,-(%sp)
    move.w  %d0,-(%sp)                              /* the selector */
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A0)         /* movea.l #aes_entry,a0 */
    .long   aes_rom_entry
    jsr     (%a0)
    .size   aes_rom_trap2,.-aes_rom_trap2

/* ---- the way out, $fe3f08: aes_entry's last call. The frames dropped, the process's stack stored, the program back - */
    .globl  aes_rom_trap2_exit
    .type   aes_rom_trap2_exit,@function
aes_rom_trap2_exit:
    move.w  TRAP2_EXIT_ANSWER(%sp),%d0              /* the word aes_entry cleared: 0 */
    M68K_JSR_LONG(aes_rom_spl7_save)                /* $fe3f0c */
    adda.l  #TRAP2_EXIT_FRAME_BYTES,%sp
    movea.l (AES_RLR).l,%a0
    movea.l PD_UDA(%a0),%a0
    clr.w   (%a0)                                   /* UDA_IN_SUPER: outside the AES again */
    move.l  %sp,UDA_SUPER_SP(%a0)
    movea.l UDA_TRAP_SSP(%a0),%sp                   /* the stack the trap came in on */
    movea.l UDA_USER_SP(%a0),%a0
    movem.l (%a0)+,PROGRAM_S_REGISTERS
    move.l  %a0,%usp
    M68K_JSR_LONG(aes_rom_spl_restore)              /* $fe3f36 */
    rte
    .size   aes_rom_trap2_exit,.-aes_rom_trap2_exit
#if UDA_IN_SUPER != 0
#error "the handler and the way out mark the UDA through (a6) and (a0) themselves: UDA_IN_SUPER is its first word"
#endif

/* ---- ub_trampoline, $fe3f3e: (parmblk) — the desk's draw code on the desk's own stack, and back -------------------- */
    .globl  aes_rom_ub_trampoline
    .type   aes_rom_ub_trampoline,@function
aes_rom_ub_trampoline:
    move.l  UB_PARMBLK(%sp),%d0
    move.l  %sp,(AES_USERDEF_SP_SAVE).l
    movea.l (AES_USERDEF_STACK).l,%sp
    move.l  %d0,-(%sp)
    M68K_JSR_LONG(AES_ROM_DESK_USERDEF)             /* $fe3f50: the ROM's own, until band 6 */
    movea.l (AES_USERDEF_SP_SAVE).l,%sp
    rts
    .size   aes_rom_ub_trampoline,.-aes_rom_ub_trampoline

/* ==== gemsuper's aes_entry, $fe65aa..$fe65c1: the ROM's stream, its three Line-F calls `jsr`s ========================= */

    .globl  aes_rom_entry
    .type   aes_rom_entry,@function
aes_rom_entry:
    link.w  %a6,#-AES_ENTRY_LOCAL_BYTES
    cmpi.w  #GEM_SELECTOR_AES,AES_ENTRY_SELECTOR(%a6)
    bne.s   1f                                      /* selector 201: a dispatch and nothing else */
    move.l  AES_ENTRY_PARAMETER_BLOCK(%a6),(%sp)
    M68K_JSR_LONG(aes_entry_to_aes_marshal)         /* $fe65ba: $f2b4 */
1:  M68K_JSR_LONG(aes_dsptch)                       /* $fe65bc: $f2b8 */
    clr.w   (%sp)                                   /* the program's D0.w */
    M68K_JSR_LONG(aes_rom_trap2_exit)               /* $fe65c0: $f2bc — and no instruction after it runs */
    .size   aes_rom_entry,.-aes_rom_entry

/* ==== THE THUNK aes_entry's `jsr` into C reaches: the marshal's Alcyon frame — one longword, the parameter block —
 * taken into the m68k C call (`c_call_glue.h`). Local, sized: no ROM bytes, and no entry of the build's. */
ONE_LONGWORD_THUNK(aes_entry_to_aes_marshal, aes_marshal)
