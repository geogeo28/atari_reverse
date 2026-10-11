/* aes/trapdoor.h — THE TRAP DOOR: how a program's `trap #2` gets into the AES and back out (`src/aes/trapdoor.S`).
 *
 *   $fe3ea6 trap #2's handler     D0.w picks one of three arms: 0 ends the program (`Pterm(0)` by `trap #1`, never
 *                                 back); 200 and 201 enter the AES; anything else goes on to the handler GEM found in
 *                                 the vector (SYSVAR_VDI_ENTRY: the BIOS's VDI door)
 *   $fe3f08 the way out           the AES arm's other half, reached by aes_entry's last call and by nothing else
 *   $fe65aa aes_entry(selector.w, 0.w, parameter block)
 *                                 the marshal for selector 200 alone, then a dispatch, then the way out
 *   $fe3f3e ub_trampoline(parmblk) the desk's G_USERDEF draw code called on the desk's own 1 KB stack
 *
 * NO C SPELLING, and no C twin (the user's rule is C first: this is what is left when C cannot say it). The handler
 * is an exception's entry that parks the program's registers ON THE PROGRAM'S OWN USER STACK, moves to the running
 * process's supervisor stack (its UDA's) and calls the AES there; the way out undoes it and `rte`s. aes_entry is
 * Alcyon C in the ROM, but its frame IS the handler's contract: the way out drops EXACT_FRAME bytes — everything
 * between the stack pointer it is entered on and the stack the handler took — and stores what is left as the
 * process's stack for its next trap. A frame of any other size (GCC's) would store a wrong one.
 *
 * THE AES ARM'S FRAMES, from the stack pointer the way out is entered on up to the UDA's stack as the handler found it
 * (TRAP2_EXIT_FRAME_BYTES, the ROM's `adda.l #24,sp` at $fe3f12):
 *      0  the return address aes_entry's call of the way out pushed (never returned to)
 *      4  aes_entry's one local, a longword every call of its three shares as an argument slot; its first WORD is
 *         cleared before the last call and is what the way out hands the program as D0.w: always 0
 *      8  aes_entry's saved A6 (`link`)
 *     12  the handler's return address (`jsr (a0)`; never returned to)
 *     16  the selector, a word; 18 a zero word; 20 the parameter block, a longword — aes_entry's arguments
 *
 * WHAT A PROGRAM GETS BACK: D1-D7 and A1-A6 as it had them (parked on its user stack round the call), the user stack
 * pointer, the status register of its own frame — and two registers it does NOT get back. A0 COMES BACK HOLDING ITS
 * USER STACK POINTER: the handler takes that pointer into A0 before it parks the registers, so A0's own value is
 * never parked. D0: THE LOW WORD 0, THE HIGH WORD WHATEVER THE AES'S CODE LEFT THERE (nothing restores it). See
 * `src/aes/trapdoor.S`, "D0'S HIGH WORD".
 */
#ifndef TOS102US_AES_TRAPDOOR_H
#define TOS102US_AES_TRAPDOOR_H

#include "addrs.h"
#include "aes/aes.h"
#include "aes/pdpipe.h"

/* ---- the handler's frame for aes_entry, and aes_entry's own ------------------------------------------------------- */
#define TRAP2_PTERM_STATUS        0          /* what selector 0 ends the program with: Pterm(0)  ($fe3ec0 move.w #0,-(sp)) */
#define TRAP2_NO_SECOND_WORD      0          /* the word between the selector and the block ($fe3efa move.w #0,-(sp)) */
#define AES_ENTRY_LOCAL_BYTES     4          /* ($fe65aa link a6,#-4)                                                  */
#define AES_ENTRY_SELECTOR        8          /* word, from aes_entry's A6          ($fe65ae cmpi.w #200,8(a6))         */
#define AES_ENTRY_PARAMETER_BLOCK 12         /* long                               ($fe65b6 move.l 12(a6),(sp))        */
/* What the way out drops: its own return address, aes_entry's local and saved A6, the handler's return address and
 * the three arguments (the comment above lays them out). */
#define TRAP2_EXIT_RETURN_BYTES   4
#define TRAP2_SAVED_A6_BYTES      4
#define TRAP2_HANDLER_RETURN_BYTES 4
#define TRAP2_ARGUMENT_BYTES      8
#define TRAP2_EXIT_FRAME_BYTES    (TRAP2_EXIT_RETURN_BYTES + AES_ENTRY_LOCAL_BYTES + TRAP2_SAVED_A6_BYTES               \
                                   + TRAP2_HANDLER_RETURN_BYTES + TRAP2_ARGUMENT_BYTES)
/* The answer word the way out reads: aes_entry's local, above the way out's own return address ($fe3f08). */
#define TRAP2_EXIT_ANSWER         TRAP2_EXIT_RETURN_BYTES

/* ---- ub_trampoline's one argument ------------------------------------------------------------------------------- */
#define UB_PARMBLK                4          /* long: the PARMBLK's address, past the return address ($fe3f3e)         */

#endif /* TOS102US_AES_TRAPDOOR_H */
