/* aes/evdisp.h — THE DISPATCHER (`src/aes/evdisp.c`, gemdisp's disp_act, mwait_act and idle; `src/aes/switch.S`,
 * disp itself and gemdosif's switch; `src/aes/irq.S`, the interrupts' glue): what runs between two processes.
 *
 *   disp()                 the running process saved (savestate) and taken off the ready list; put back at its tail
 *                          (disp_act) or, if it waits, on the not-ready list (mwait_act); then `do { forker(); idle(); }
 *                          while (the fork queue holds anything)`; the first ready process entered (switchto)
 *                                                                                                 ($fe4d9e, by dsptch's `jmp`)
 *   disp_act(pd)           pd READY, at the ready list's TAIL                                     ($fe4b74)
 *   mwait_act(pd)          an event pd waits for has come → disp_act; else the not-ready list's HEAD   ($fe4b9c)
 *   idle()                 `do { chkkbd(); every woken process → disp_act } while (nothing ready and nothing queued)`:
 *                          where the machine WAITS FOR AN INTERRUPT                               ($fe4d68)
 *
 * WHAT IS C AND WHAT IS NOT (`atari/target.mk`, SWITCH_SOURCES). disp_act, mwait_act and idle are Alcyon C
 * in the ROM and C here, on both builds. disp is Alcyon C in the ROM and ASSEMBLY here — the ROM's own instruction
 * stream, its six Line-F call words made `jsr`s — because savestate reads disp's caller's frame THROUGH DISP'S A6,
 * returns to it on another stack and changes A0 and A5 under it: a contract no compiled function keeps (the target is
 * `-fomit-frame-pointer`). On target disp `jsr`s the three C routines, and forker, through local thunks of its own
 * `.S` that take each one's Alcyon frame — one longword, or nothing — into the C call (the image base pushed first).
 *
 * OFF TARGET there is no second stack and no `rte`, so disp is a MODEL (`aes_disp`): the C of its
 * own loop over a savestate model (the guard counted; the context block NOT written — the caller's CPU state, by
 * nature another's for any C caller) and a switchto model: the process the scheduler comes back to is the CALLER →
 * the guard cleared, and the call RETURNS; ANOTHER process → the process hook, which runs it as the ROM's own code
 * from switchto until the machine is about to enter the caller again. Where the machine would wait for an interrupt
 * (idle, with nothing ready, woken or queued) the idle hook lays the one its case delivers there, or refuses. A case
 * turns the model ON by binding `recreate_dispatch` (`aes/switch.h`) to `aes_disp`; every other case's binding still
 * refuses at dsptch.
 */
#ifndef TOS102US_AES_EVDISP_H
#define TOS102US_AES_EVDISP_H

#include "addrs.h"
#include "aes/aes.h"

/* ---- THE INTERRUPTS' GLUE (`src/aes/irq.S`, $fed3be..$fed477): the routines the AES hands the VDI as its button,
 * motion and tick vectors. Each parks the interrupted stack pointer and runs on a stack of the AES's own. */
#define AES_GLUE_SAVED_SP     0x9482     /* long: the button and motion glue's interrupted SP ($fed3be move.l sp) */
#define AES_GLUE_STACK_TOP    0x94f2     /* ...and their stack, growing down                   ($fed3c4 lea)       */
#define AES_TICK_SAVED_SP     0x9486     /* long: the tick glue's interrupted SP               ($fed426 move.l sp) */
#define AES_TICK_STACK_TOP    0x9552     /* ...and its stack                                   ($fed42c lea)       */
#define AES_TICK_CHAIN        0x948a     /* long: the tick routine the AES displaced, called last ($fed46e movea.l) */
#define B_DELAY_ONE_TICK      1          /* what the tick counts the click delay down by       ($fed45c move.w #1) */

/* ---- THE DISPATCHER'S STACK ($fe3922 `lea $8c1a,sp`): from the three SR save words up to its top. disp's own
 * argument slot — the longword at its SP, which every call of its shares (`move.l a5,(sp)`) — is then the longword
 * AT the top, above the stack: the PD it queues, and last the UDA it hands switchto. */
#define AES_DISPATCHER_STACK_BOTTOM 0x899a     /* the first byte above psetup's save word, the last of the three */
#define AES_DISPATCHER_STACK_BYTES  (AES_DISPATCHER_STACK_TOP - AES_DISPATCHER_STACK_BOTTOM)
#if AES_DISPATCHER_STACK_BOTTOM != AES_SR_PSETUP + 2
#error "the dispatcher's stack begins where the SR save words end"
#endif
#define AES_DISP_ARGUMENT           AES_DISPATCHER_STACK_TOP /* long ($fe4dc4, $fe4dca move.l a5,(sp); $fe4dfa) */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_disp_act(uint8_t *image, uint32_t pd);                                                       /* $fe4b74 */
void aes_mwait_act(uint8_t *image, uint32_t pd);                                                      /* $fe4b9c */
void aes_idle(uint8_t *image);                                                                        /* $fe4d68 */

#ifndef RECREATE_HOST_DIFFERENTIAL
/* THE GLUE'S ENTRIES on target (`src/aes/irq.S`): what gsx_setmb_aes hands the VDI as its button and motion vectors
 * (`aes/gsxif.h`), by address — entered by the VDI's interrupt code with its own register contract, never called
 * from C. */
void aes_rom_button_glue(void);                                                                       /* $fed3be */
void aes_rom_motion_glue(void);                                                                       /* $fed3e4 */
#endif

#ifdef RECREATE_HOST_DIFFERENTIAL
/* disp's host model: nonzero once the call has come back to its caller — `recreate_dispatch`'s own answer, so a case
 * binds the hook to this function itself. */
uint32_t aes_disp(uint8_t *image);                                                                    /* $fe4d9e */

/* THE IDLE HOOK: the machine waits for an interrupt — nothing ready, nothing woken, nothing queued. Nonzero once the
 * case has laid the interrupt it delivers there; zero REFUSES (nothing to deliver: the wait would never end). */
extern uint32_t (*recreate_idle)(uint8_t *image);
/* THE PROCESS HOOK: the scheduler enters ANOTHER process than the one that called it, by `uda`. Nonzero once that
 * process — and every other the ROM's own dispatcher entered after it — has run and the machine is about to enter
 * the caller (by `caller_s_uda`) again; zero REFUSES. */
extern uint32_t (*recreate_process)(uint8_t *image, uint32_t uda, uint32_t caller_s_uda);
#endif
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_AES_EVDISP_H */
