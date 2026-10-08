/* switch.S — THE PROCESS SWITCH as the ROM spells it (`aes/switch.h`, `aes/evdisp.h`): gemdosif's hand 68000,
 * `$fe387c..$fe395b` — dsptch, the interrupt-mask brackets, gotopgm, savestate and switchto, BYTE FOR BYTE — and
 * gemdisp's disp, `$fe4d9e..$fe4dff`, as the ROM's own INSTRUCTION STREAM with its six Line-F call words made `jsr`s.
 *
 * A KIND OF ITS OWN (`atari/target.mk`: SWITCH_SOURCES; `include/transcribed.h` says why it is no row of the table):
 * not a transcription — there is no C twin a build could link instead, and no Tier 3 bar it was measured over: a
 * context switch has no C spelling — and not glue: these ARE the ROM's bytes. C FIRST still holds for all
 * that can be C: disp_act, mwait_act, idle and forker are C (`evdisp.c`, `evfork.c`), `jsr`ed from disp below
 * through the thunks at the end of this file.
 *
 * WHY EACH IS ASSEMBLY, read from its body:
 *   dsptch       builds an `rte` frame out of ITS OWN RETURN ADDRESS (the SR and A0 pushed under it) and jumps;
 *   spl7_save /  the status register parked in a word and the interrupt mask raised, and back — supervisor
 *   spl_restore, instructions (the event layer's C spells the same two inline, `aes/switch.h`; these are the entries
 *   cli, sti     gem_main and the trap handler call);
 *   gotopgm      an `rte` into a process's FIRST instruction, in USER state;
 *   savestate    stores D0-A5 into the UDA, then reads its caller's caller's frame THROUGH DISP'S A6 — the A6, the
 *                A0, the address of the {SR, PC} frame dsptch built — and USP; and RETURNS ON ANOTHER STACK
 *                (`lea $8c1a,sp / jmp (a0)`), A0 and A5 changed;
 *   switchto     loads all of it back, rewrites the frame's SR from its own save word, and `rte`s: it never returns;
 *   disp         is the function whose A6 frame savestate reads, and which goes on running after its stack was
 *                taken from under it: Alcyon's `link a6` frame is the contract, and no compiler is held to it.
 *
 * TWO PINS (`test/test_aes_switch.py`). The gemdosif region is BYTE-EXACT but for ONE word: dsptch's `jmp` goes to
 * the disp below, where the ROM's goes to its own. disp is held INSTRUCTION BY INSTRUCTION under the stream kind
 * (`test/transcription.py`, `assert_stream`): every instruction the ROM's, but the six Line-F call words — each
 * NAMED, with the ROM routine its table entry reaches and the entry it became a `jsr` of — and the short branches
 * across them, whose displacements follow (a `jsr` is four bytes longer than the word it stands for).
 *
 * WHAT A `jsr` CHANGES FOR THE CALLEE, AND WHY IT IS RIGHT. The Line-F handler enters a routine with the return
 * address on the stack, as a `jsr` does, and with THREE registers of its own leavings: A0 the routine's address, D1
 * the call word's offset, D2 the caller's status register ($fee8c2..$fee8e0). savestate stores D1 and D2 in the UDA
 * (A0's slot it overwrites with dsptch's), so the ROM's saved context holds the handler's two; ours holds the
 * caller's own D1 and D2 — which is what makes the switch keep D2 for a C caller, as the GCC ABI has it. Those
 * eight bytes of a UDA are a difference BY NATURE between the two builds (`test/aes_switch.py`, the context drops).
 *
 * THE DEAD TAIL. disp's Line-F return ($fe4e00) is not here: switchto ends in `rte` on every path (`test_aes_switch`
 * proves it from the bytes), so nothing ever executes it.
 *
 * REGISTERS AND STACKS. Every routine here is supervisor code. dsptch is entered by `jsr` with its caller's return
 * address on the stack — the PC the process resumes at; the image pointer a C caller pushed is above it and is the
 * caller's to drop when, a process switch later, the call returns. The C that disp `jsr`s runs on THE DISPATCHER'S
 * STACK ($899a..$8c1a, 640 bytes — `test_aes_evdisp` measures how deep our build goes on it).
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/evdisp.h"
#include "aes/switch.h"

/* savestate addresses the UDA from its register block's first longword, the `movem`'s last store ($fe38fe). */
#define FROM_UDA_REGS(field)  ((field) - UDA_REGS)
#define UDA_A0                (UDA_REGS + 8 * 4)      /* after D0..D7                       ($fe3908 move.l 4(a5),32(a6)) */
/* disp's frame, as dsptch and its own `link` leave it: the caller's A6, dsptch's A0, then the {SR, PC} frame. */
#define DISP_FRAME_A0         4
#define DISP_FRAME_RTE        8
#define DISP_LOCAL_BYTES      4          /* ($fe4d9e link a6,#-4: the one argument slot its calls share)       */
#define UNMASKED_SR           (~SR_IPL_MASK & 0xffff)    /* ($fe38aa andi.w #$f8ff,sr)                            */

    .text

/* ==== gemdosif's switch, $fe387c..$fe395b ============================================================================ */

/* ---- dsptch, $fe387c: under the guard a bare `rts`; else an `rte` frame from its own return address, and disp ------ */
    .globl  aes_dsptch
    .type   aes_dsptch,@function
aes_dsptch:
    tst.b   AES_INDISP
    beq.s   1f
    rts
1:  move.w  %sr,-(%sp)
    move.l  %a0,-(%sp)
    .word   M68K_JMP_ABSOLUTE_LONG      /* jmp aes_rom_disp.l — gas would shorten it to (pc) */
    .long   aes_rom_disp
    .size   aes_dsptch,.-aes_dsptch

/* ---- spl7_save, $fe3890 / spl_restore, $fe389c: the SR parked and every interrupt masked — and back ---------------- */
    .globl  aes_rom_spl7_save
    .type   aes_rom_spl7_save,@function
aes_rom_spl7_save:
    move.w  %sr,AES_SR_SPL
    ori.w   #SR_IPL_MASK,%sr
    rts
    .size   aes_rom_spl7_save,.-aes_rom_spl7_save

    .globl  aes_rom_spl_restore
    .type   aes_rom_spl_restore,@function
aes_rom_spl_restore:
    move.w  AES_SR_SPL,%sr
    rts
    .size   aes_rom_spl_restore,.-aes_rom_spl_restore

/* ---- cli, $fe38a4 / sti, $fe38aa: every interrupt masked, nothing parked — and every one let in -------------------- */
    .globl  aes_rom_cli
    .type   aes_rom_cli,@function
aes_rom_cli:
    ori.w   #SR_IPL_MASK,%sr
    rts
    .size   aes_rom_cli,.-aes_rom_cli

    .globl  aes_rom_sti
    .type   aes_rom_sti,@function
aes_rom_sti:
    andi.w  #UNMASKED_SR,%sr
    rts
    .size   aes_rom_sti,.-aes_rom_sti

/* ---- gotopgm, $fe38b0: the running process's program entered at its text, in USER state, the mask as it was -------- */
    .globl  aes_rom_gotopgm
    .type   aes_rom_gotopgm,@function
aes_rom_gotopgm:
    move.w  %sr,AES_SR_SPL
    ori.w   #SR_IPL_MASK,%sr
    movea.l AES_RLR,%a0
    movea.l PD_LDADDR(%a0),%a0
    move.l  BASEPAGE_TBASE(%a0),-(%sp)
    move.w  AES_SR_SPL,-(%sp)
    eori.w  #SR_SUPERVISOR,(%sp)
    rte
    .size   aes_rom_gotopgm,.-aes_rom_gotopgm

/* ---- savestate, $fe38d4: (uda), called by disp alone — the caller's context into the UDA, and back to disp on the
 * dispatcher's stack. Under the guard (a state no machine reaches: nothing calls disp with it set) it would unwind
 * disp's frame and `rte` at once. */
    .globl  aes_rom_savestate
    .type   aes_rom_savestate,@function
aes_rom_savestate:
    move.w  %sr,AES_SR_DISPATCH
    ori.w   #SR_IPL_MASK,%sr
    tst.b   AES_INDISP
    beq.s   1f
    unlk    %a6
    movea.l (%sp)+,%a0
    rte
1:  link.w  %a6,#0
    addq.b  #1,AES_INDISP
    movea.l 8(%a6),%a6                              /* the UDA */
    lea     UDA_A6(%a6),%a6
    movem.l %d0-%d7/%a0-%a5,-(%a6)                  /* ...its register block, down to UDA_REGS */
    movea.l (%sp),%a5                               /* disp's frame pointer, as this routine's `link` saved it */
    move.l  (%a5),FROM_UDA_REGS(UDA_A6)(%a6)        /* the caller's A6 */
    move.l  DISP_FRAME_A0(%a5),FROM_UDA_REGS(UDA_A0)(%a6)
    lea     DISP_FRAME_RTE(%a5),%a5
    move.l  %a5,FROM_UDA_REGS(UDA_SUPER_SP)(%a6)    /* where the {SR, PC} frame lies */
    move.l  %usp,%a5
    move.l  %a5,FROM_UDA_REGS(UDA_USER_SP)(%a6)
    movea.l %sp,%a6
    unlk    %a6
    movea.l (%sp),%a0
    lea     AES_DISPATCHER_STACK_TOP,%sp
    move.w  AES_SR_DISPATCH,%sr
    jmp     (%a0)
    .size   aes_rom_savestate,.-aes_rom_savestate

/* ---- switchto, $fe3930: (uda) — the context loaded, the guard cleared, the frame's SR rewritten, `rte` -------------- */
    .globl  aes_rom_switchto
    .type   aes_rom_switchto,@function
aes_rom_switchto:
    move.w  %sr,AES_SR_DISPATCH
    ori.w   #SR_IPL_MASK,%sr
    addq.l  #4,%sp
    movea.l (%sp),%sp                               /* the UDA */
    addq.l  #UDA_REGS,%sp
    movem.l (%sp)+,%d0-%d7/%a0-%a5
    movea.l (UDA_USER_SP - UDA_A6)(%sp),%a6
    move.l  %a6,%usp
    movea.l (%sp)+,%a6
    movea.l (%sp),%sp                               /* the supervisor stack: the {SR, PC} frame */
    clr.b   AES_INDISP
    move.w  AES_SR_DISPATCH,(%sp)
    rte
    .size   aes_rom_switchto,.-aes_rom_switchto

/* ==== gemdisp's disp, $fe4d9e..$fe4dff: the ROM's stream, its six Line-F calls `jsr`s ================================= */

    .globl  aes_rom_disp
    .type   aes_rom_disp,@function
aes_rom_disp:
    link.w  %a6,#-DISP_LOCAL_BYTES
    movem.l %d7/%a5,-(%sp)
    movea.l AES_RLR,%a0
    move.l  PD_UDA(%a0),(%sp)
    M68K_JSR_LONG(aes_rom_savestate)                /* $fe4db0: $f7c8 */
    movea.l AES_RLR,%a5
    move.l  (%a5),AES_RLR                           /* the ready list's next: PD_LINK */
    move.w  PD_STAT(%a5),%d0
    bra.s   3f
1:  move.l  %a5,(%sp)
    M68K_JSR_LONG(disp_to_aes_disp_act)             /* $fe4dc6: $f7c0 */
    bra.s   4f
2:  move.l  %a5,(%sp)
    M68K_JSR_LONG(disp_to_aes_mwait_act)            /* $fe4dcc: $f7cc */
    bra.s   4f
3:  tst.w   %d0
    beq.s   1b
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), PD_STAT_WAITING      /* cmp.w #1,d0 */
    beq.s   2b
4:  M68K_JSR_LONG(disp_to_aes_forker)               /* $fe4dda: $f7d0 */
    M68K_JSR_LONG(disp_to_aes_idle)                 /* $fe4ddc: $f7d4 */
    tst.w   AES_FORK_COUNT
    bne.s   4b
    movea.l AES_RLR,%a0
    move.l  PD_CDA(%a0),AES_GL_CDA
    movea.l AES_RLR,%a0
    move.l  PD_UDA(%a0),(%sp)
    M68K_JSR_LONG(aes_rom_switchto)                 /* $fe4dfe: $f7d8 — and no instruction after it runs */
    .size   aes_rom_disp,.-aes_rom_disp
#if PD_LINK != 0
#error "disp takes the ready list's next through (a5) itself: a PD's link is its first longword"
#endif

/* ==== THE THUNKS disp's four `jsr`s into C reach: each routine's Alcyon frame — one longword, or nothing — taken
 * into the m68k C call (`c_call_glue.h`). Local, sized: no ROM bytes, and no entry of the build's. */
#define DISP_THUNK(body)        IMAGE_ONLY_THUNK(disp_to_##body, body)
/* (pd): the one longword pushed again under the image base. */
#define DISP_PD_THUNK(body)                                                                                            \
    .type   disp_to_##body,@function;                                                                                  \
disp_to_##body:                                                                                                        \
    move.l  ALCYON_FIRST_ARGUMENT(%sp),-(%sp);                                                                         \
    pea     (0).w;                                                                                                     \
    jsr     body;                                                                                                      \
    addq.l  #(IMAGE_ARGUMENT_BYTES + SLOT_BYTES),%sp;                                                                  \
    rts;                                                                                                               \
    .size   disp_to_##body,.-disp_to_##body

DISP_PD_THUNK(aes_disp_act)
DISP_PD_THUNK(aes_mwait_act)
DISP_THUNK(aes_forker)
DISP_THUNK(aes_idle)
