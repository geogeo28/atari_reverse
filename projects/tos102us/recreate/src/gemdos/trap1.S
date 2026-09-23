/* trap1.S — the GEMDOS entry: `trap #1` ($fc4f6e) and the OS's own C-callable door ($fc5078).
 *
 * WHY THIS IS ASSEMBLY, which `src/bios/trap.S` argues in full and this file inherits: the routine
 * is an EXCEPTION HANDLER. It is entered with a group-2 frame on the supervisor stack, it leaves
 * through `rte`, it moves the stack pointer between the supervisor and user stacks — twice, because
 * `Super` is the business of doing exactly that — and the register file it hands back is its
 * contract. No C compiler owes any of that and none can say it.
 *
 * WHAT MAKES THIS ONE DIFFERENT FROM THE BIOS ENTRY is where the caller's registers go. The BIOS
 * dispatcher frames them in the OS's own save area at `savptr`; GEMDOS frames them in the CALLING
 * PROCESS'S BASEPAGE and on the caller's own stack, because GEMDOS calls are the ones a process can
 * be terminated inside of — `Pterm` longjmps out through the dispatcher and the register state a
 * dead process is abandoned in has to belong to that process rather than to a shared stack.
 *
 * THE TRANSCRIPTION IS THE ROM'S BYTES, ALL OF THEM, with nothing spliced. `src/bios/trap.S` needs
 * three opcode words changed because it reaches its dispatch tables PC-relatively; every external
 * reference here is already absolute or immediate in the ROM — `$87ce`, `#$16ce`, `jsr $fc94e4` —
 * so a transcription linked anywhere assembles the same 292 bytes.
 * `test_gemdos_trap1.py::test_the_transcription_is_the_roms_bytes_exactly` compares them.
 *
 * THE REGISTER MAP, which the instructions cannot carry in their operand names:
 *
 *   a6   the current basepage (`p_run`), then the walking frame pointer on the way back out
 *   a5   the frame being built on the caller's stack, then `p_run` again for the epilogue
 *   a4   the exception frame's return PC on the way in; the OTHER stack pointer on the way out
 *   a3   the return PC on the way out
 *   a0   the ARGUMENT LIST — the caller's own words, which is the dispatcher's one parameter
 *   d0   the exception frame's SR word throughout, and the dispatcher's RESULT at the end
 *
 * WHAT THE PROCESS FRAME IS, and it is two pieces in two places:
 *
 *   basepage +$68  D0, A3, A4, A5      — saved before there is a stack to save them on
 *   basepage +$78  A6                  — pushed first, so that A6 could become `p_run`
 *   basepage +$7c  -> the frame below, which is on the CALLER's stack:
 *                     +$00  the OTHER stack pointer (SSP for a user caller, USP for a supervisor
 *                           one) — one field, because the entry always saves the one it is not on
 *                     +$04  the SR word
 *                     +$06  the return PC
 *                     +$0a  D1-D7/A0-A2
 *                     +$32  the caller's own words: the function number, then the arguments
 *
 * ...so `lea 50(frame),a0` IS the argument list, and the frame's length and that displacement are
 * one number (`GEMDOS_SAVED_FRAME_BYTES`).
 *
 * WHAT THE CALLER GETS BACK is EVERY register: D0 is the result and the other fifteen are restored
 * from the two halves of the frame. That is the opposite of the BIOS entry, which gives back nine —
 * and it is a ROM FACT to reproduce rather than improve on, because a program written against it is
 * right on the machine (`test_gemdos_trap1.py`, which compares the whole file on both sides).
 *
 * `Super` IS SERVED INLINE, before any of that, and it has to be: it is the one call whose whole
 * job is to change the mode the `rte` returns in, so it never reaches the dispatcher and never
 * builds a frame. Three arms, and which one runs depends on the CALLER's mode as much as on the
 * argument — the entry tests the frame's S bit first and only then looks at the function number:
 *
 *   a USER caller     Super(0)     -> supervisor, on the caller's OWN stack; D0 = the old SSP
 *                     Super(1)     -> the query arm below
 *                     Super(ssp)   -> supervisor, on `ssp`; D0 = the old SSP
 *   a SUPERVISOR one  Super(0)     -> user, with USP planted just past the exception frame
 *                     Super(1)     -> the query arm below
 *                     Super(ssp)   -> user, on `ssp`, and D0's low word comes back holding the SR
 *   either            Super(1)     -> -1 if the caller was supervisor, 0 if it was not, and the
 *                                     mode is left exactly as it was
 *
 * The two quirks in there are transcribed as they stand and pinned by the battery: a supervisor
 * caller's `Super(ssp)` leaves the SR in D0's low word because the arm pops it there on its way to
 * rebuilding the frame, and its `Super(0)` does not write D0 at all.
 */
#include "addrs.h"

    .text

    .globl  gemdos_trap1
gemdos_trap1:
    btst    #SR_SUPERVISOR_HIGH_BYTE_BIT,(%sp)  /* the frame's SR: was the caller supervisor? */
    bne.s   .Lsupervisor_caller
    move.l  %usp,%a0                    /* no: its words are on the user stack... */
    cmpi.w  #GEMDOS_SUPER_FN,(%a0)      /* ...and the function number is the first of them */
    beq.w   .Lsuper_from_user
    bra.s   .Lframe
.Lsupervisor_caller:
    cmpi.w  #GEMDOS_SUPER_FN,EXCEPTION_FRAME_BYTES(%sp) /* yes: they are under the frame */
    beq.w   .Lsuper_from_supervisor

/* ...everything that is not `Super`: frame the caller into its basepage and call the dispatcher. */
.Lframe:
    move.l  %a6,-(%sp)                  /* park A6, the only register there is nowhere to put yet */
    movea.l (GEMDOS_P_RUN).l,%a6        /* ...so that it can become the current basepage */
    movem.l %d0/%a3-%a5,BASEPAGE_SAVED_D0(%a6)
    move.l  (%sp)+,BASEPAGE_SAVED_A6(%a6)   /* ...and A6 joins them from where it was parked */
    move.w  (%sp)+,%d0                  /* the exception frame: the SR... */
    movea.l (%sp)+,%a4                  /* ...and the return PC */
    btst    #SR_SUPERVISOR_BIT,%d0
    bne.s   .Lcaller_was_supervisor

    move.l  %usp,%a5                    /* a USER caller: its frame goes on ITS stack */
    movem.l %d1-%a2,-(%a5)
    move.l  %a4,-(%a5)
    move.w  %d0,-(%a5)
    movea.l %sp,%a0                     /* ...and the stack pointer saved beside it is the SSP */
    move.l  %a0,-(%a5)
    move.l  %a5,BASEPAGE_SAVED_FRAME(%a6)
    movea.l #GEMDOS_SUPERVISOR_STACK,%sp    /* the OS's own stack, whoever called */
    lea     GEMDOS_SAVED_FRAME_BYTES(%a5),%a0   /* ...and the argument list is just above the frame */
    bra.s   .Lcall

.Lcaller_was_supervisor:
    movem.l %d1-%a2,-(%sp)              /* the same frame, on the supervisor stack it arrived on */
    move.l  %a4,-(%sp)
    move.w  %d0,-(%sp)
    move.l  %usp,%a0                    /* ...and the stack pointer saved beside it is the USP */
    move.l  %a0,-(%sp)
    move.l  %sp,BASEPAGE_SAVED_FRAME(%a6)
    lea     GEMDOS_SAVED_FRAME_BYTES(%sp),%a0   /* ...taken BEFORE the stack moves, not after */
    movea.l #GEMDOS_SUPERVISOR_STACK,%sp

.Lcall:
    move.l  %a0,-(%sp)                  /* the dispatcher's one argument: the caller's own words */
    jsr     (GEMDOS_DISPATCH).l
    addq.l  #4,%sp

/* THE EPILOGUE IS A SECOND ENTRY POINT, and `Pterm` uses it as one. A process that ends does not
 * return through its own call: `$fc8076` reassigns `p_run` to the parent, plants the exit code in
 * the PARENT's saved-D0 slot, and `jsr`s here — so the frame unwound below is the parent's, and the
 * `rte` at the end of it resumes whoever called the parent's own GEMDOS call. Nothing in this file
 * jumps here; the label is so that a rebuilt ROM's `Pterm` can. */
    .globl  gemdos_trap1_epilogue
gemdos_trap1_epilogue:
    movea.l (GEMDOS_P_RUN).l,%a5        /* RE-READ: a Pexec or a Pterm has changed which process */
    move.l  %d0,BASEPAGE_SAVED_D0(%a5)  /* the result, into the slot D0 is restored from below */
    movea.l BASEPAGE_SAVED_FRAME(%a5),%a6
    movea.l (%a6)+,%a4                  /* the other stack pointer... */
    move.w  (%a6)+,%d0                  /* ...the SR... */
    movea.l (%a6)+,%a3                  /* ...the return PC... */
    movem.l (%a6)+,%d1-%a2              /* ...and the ten registers, leaving A6 past the frame */
    btst    #SR_SUPERVISOR_BIT,%d0
    bne.s   .Lreturn_to_supervisor
    movea.l %a4,%sp                     /* to a USER caller: the supervisor stack was the saved one */
    move.l  %a6,%usp                    /* ...and its own stack is where the frame ended */
.Lrte:
    move.l  %a3,-(%sp)                  /* rebuild the exception frame the `rte` needs: PC... */
    move.w  %d0,-(%sp)                  /* ...and SR */
    movem.l BASEPAGE_SAVED_D0(%a5),%d0/%a3-%a6  /* ...and the basepage half of the frame */
    rte

.Lreturn_to_supervisor:
    movea.l %a6,%sp                     /* the frame was on this stack; A6 is past it */
    move.l  %a4,%usp                    /* ...and the saved one was the USP */
    bra.s   .Lrte

/* ---- `Super`, served inline ---------------------------------------------------------------------
 * A0 is the caller's words, so `2(a0)` is the LONG argument above the function number.
 */
.Lsuper_from_user:
    move.l  GEMDOS_ARGUMENT_WORD(%a0),%d1
    beq.s   .Luser_to_supervisor        /* Super(0): stay on the stack the caller is already on */
    subq.l  #1,%d1
    beq.s   .Lsuper_query
    movea.l GEMDOS_ARGUMENT_WORD(%a0),%a0   /* Super(ssp): go to supervisor on the named stack */
.Luser_to_supervisor:
    move.w  (%sp)+,%d0                  /* move the exception frame onto that stack... */
    move.l  (%sp)+,-(%a0)
    ori.w   #SR_SUPERVISOR,%d0          /* ...with the S bit set, which is the whole of the call */
    move.w  %d0,-(%a0)
    move.l  %sp,%d0                     /* D0 = the SSP the caller is being given custody of */
    movea.l %a0,%sp
    rte

.Lsuper_from_supervisor:
    move.l  GEMDOS_SUPERVISOR_ARGUMENT(%sp),%d1
    beq.s   .Lsupervisor_to_user
    subq.l  #1,%d1
    beq.s   .Lsuper_query
    movea.l GEMDOS_SUPERVISOR_ARGUMENT(%sp),%a1 /* Super(ssp): go to USER mode, on `ssp` */
    move.w  (%sp)+,%d0                  /* ...and D0 comes back holding the SR, which is a quirk */
    move.l  (%sp)+,-(%a1)
    move.w  %d0,-(%a1)
    move.l  %usp,%a0
    cmpa.l  %a0,%sp                     /* were the two stacks the same one? */
    beq.s   .Lstacks_were_one
    move.l  (%sp)+,-(%a0)               /* no: carry the caller's return address over with it */
    movea.l %a1,%sp
    bra.s   .Lplant_user_stack
.Lstacks_were_one:
    movea.l %a1,%sp
    bra.s   .Lleave_supervisor
.Lsupervisor_to_user:
    movea.l %sp,%a0                     /* Super(0) from supervisor: the user stack is this one, */
    addq.l  #EXCEPTION_FRAME_BYTES,%a0  /* ...just past the frame the `rte` is about to eat */
.Lplant_user_stack:
    move.l  %a0,%usp
.Lleave_supervisor:
    andi.w  #SR_USER_MASK,(%sp)         /* clear the frame's S bit: the `rte` returns in user mode */
    rte

.Lsuper_query:
    move.l  #SR_SUPERVISOR,%d0          /* Super(1): report the mode and change nothing */
    and.w   (%sp),%d0
    beq.s   .Lsuper_query_done
    moveq   #-1,%d0
.Lsuper_query_done:
    rte

/* ---- the OS's own door into GEMDOS --------------------------------------------------------------
 * The ROM calls GEMDOS from inside itself — the dispatcher's own redirection arms reach `Fwrite`
 * this way ($fc9886) — and it cannot use `trap #1` to do it, because that would frame the process
 * a second time over the frame it is already in. So there is a second entry whose only trick is
 * `lea 8(a6),a0`: it hands the dispatcher the address of ITS OWN caller's argument list.
 *
 * That is what keeps it out of C as well. A C function can read its arguments; it cannot take the
 * address of the list the caller pushed and pass it on, which is this routine's whole body.
 */
    .globl  gemdos_entry_c
gemdos_entry_c:
    link    %a6,#0
    move.l  %a0,-(%sp)                  /* A0 is caller-saved to GCC and callee-saved to Alcyon */
    lea     GEMDOS_C_ARGUMENTS(%a6),%a0
    move.l  %a0,-(%sp)
    jsr     (GEMDOS_DISPATCH).l
    addq.l  #4,%sp
    movea.l (%sp)+,%a0
    unlk    %a6
    rts
