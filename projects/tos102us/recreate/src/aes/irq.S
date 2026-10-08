/* irq.S — THE INTERRUPTS' GLUE as the ROM spells it (`aes/evdisp.h`): `$fed3be..$fed477`, hand 68000 — the three
 * routines the AES hands the VDI as its button, motion and tick vectors, with drawrat and the bare `rts` between
 * them — BYTE FOR BYTE but for the six words that name code (`test/test_aes_irq.py` pins every other).
 *
 * THE SWITCH'S KIND (`atari/target.mk`: SWITCH_SOURCES; `switch.S` says what that is): the ROM's bytes, no row of
 * `include/transcribed.h`. The three glues have no C spelling — each is entered by the VDI's interrupt code with its
 * own register contract, parks the interrupted stack pointer in a global and runs on a PRIVATE STACK. drawrat and
 * justretf lie between them in the ROM's layout and ship in it: justretf is an `rts` whose ADDRESS is data (what
 * AES_DRWADDR holds while no cursor routine is saved; ap_tplay hands it to the VDI), and drawrat is four
 * instructions over two registers (its C twin, `evfork.c`'s aes_drawrat, is what mchange's C calls; this is the
 * entry a ROM-shaped caller's `jsr` reaches).
 *
 * THE SIX WORDS THAT NAME CODE — each the ROM's own reference followed to what our build links in its place:
 *   - three `jsr`s into C: b_click (the button glue), forkq (the motion and the tick glue) and b_delay (the tick).
 *     The glue pushes WORD arguments (`move.w d0,-(sp)`), which no m68k C function takes: each `jsr` goes to an
 *     ALCYON ENTRY below — a local thunk that takes the routine's Alcyon frame into the C call (the image base, then
 *     a longword slot per argument, a word sign-extended into its slot);
 *   - two fork functions pushed BY VALUE for forkq (`move.l #mchange,-(sp)`, `#tchange`): CODE ADDRESSES, which a
 *     queue entry holds and forker `jsr`s — our own entries on target (`aes/evfork.h`: aes_mchange_fork,
 *     aes_tchange_fork), as every C caller of forkq queues its own.
 *
 * REGISTERS. The button and motion glue save D0-D2/A0-A2 round their one call — Alcyon's scratch, a superset of what
 * a GCC function changes (D0-D1/A0-A1). The tick glue saves NOTHING, in the ROM too: the VDI's tick code, its only
 * caller, brackets the call itself ($fca78a `movem.l d0-a6,-(sp)`); our C changes fewer registers than Alcyon's.
 * AN ISR'S OWN COUNTS ARE THE ROM'S INSTRUCTIONS HERE: the tick's `addq.l #1` / `subq.l #1` on memory, as pinned.
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/evdisp.h"
#include "aes/gsxif.h"

/* An Alcyon frame's first argument, and the longword two pushed words make. */
#define ALCYON_WORD           ALCYON_FIRST_ARGUMENT
#define ALCYON_LONG_PAIR      ALCYON_FIRST_ARGUMENT
/* The C calls' argument slots after the image: b_click's and b_delay's one word; forkq's code and data. */
#define ONE_ARGUMENT_SLOT     1
#define TWO_ARGUMENT_SLOTS    2

    .text

/* ---- the button glue, $fed3be: the VDI's button vector — D0.w the buttons — b_click(buttons) ----------------------- */
    .globl  aes_rom_button_glue
    .type   aes_rom_button_glue,@function
aes_rom_button_glue:
    move.l  %sp,AES_GLUE_SAVED_SP
    lea     AES_GLUE_STACK_TOP,%sp
    movem.l %d0-%d2/%a0-%a2,-(%sp)
    move.w  %d0,-(%sp)
    M68K_JSR_LONG(aes_b_click_alcyon)               /* $fed3d0: jsr b_click */
    addq.l  #2,%sp
    movem.l (%sp)+,%d0-%d2/%a0-%a2
    movea.l AES_GLUE_SAVED_SP,%sp
    rts
    .size   aes_rom_button_glue,.-aes_rom_button_glue

/* ---- the motion glue, $fed3e4: the VDI's motion vector — D0.w x, D1.w y — forkq(mchange, x, y) ---------------------- */
    .globl  aes_rom_motion_glue
    .type   aes_rom_motion_glue,@function
aes_rom_motion_glue:
    move.l  %sp,AES_GLUE_SAVED_SP
    lea     AES_GLUE_STACK_TOP,%sp
    movem.l %d0-%d2/%a0-%a2,-(%sp)
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.l  #aes_mchange_fork,-(%sp)                /* $fed3f8: the fork function, by value */
    M68K_JSR_LONG(aes_forkq_alcyon)                 /* $fed3fe: jsr forkq */
    addq.l  #8,%sp
    movem.l (%sp)+,%d0-%d2/%a0-%a2
    movea.l AES_GLUE_SAVED_SP,%sp
    rts
    .size   aes_rom_motion_glue,.-aes_rom_motion_glue

/* ---- drawrat, $fed412: (x, y) — the saved cursor routine called as the VDI calls one, the words in D0 and D1 ------- */
    .globl  aes_rom_drawrat
    .type   aes_rom_drawrat,@function
aes_rom_drawrat:
    move.w  4(%sp),%d0
    move.w  6(%sp),%d1
    movea.l AES_DRWADDR,%a0
    jsr     (%a0)
    rts
    .size   aes_rom_drawrat,.-aes_rom_drawrat

/* ---- justretf, $fed424: the routine that draws nothing ---------------------------------------------------------------- */
    .globl  aes_rom_justretf
    .type   aes_rom_justretf,@function
aes_rom_justretf:
    rts
    .size   aes_rom_justretf,.-aes_rom_justretf

/* ---- the tick glue, $fed426: the VDI's tick vector. While a delay is armed its ticks are counted, and the one that
 * runs it out queues tchange with the ticks elapsed; the click delay is counted down by one, always; then the tick
 * routine the AES displaced, on the interrupted stack. */
    .globl  aes_rom_tick_glue
    .type   aes_rom_tick_glue,@function
aes_rom_tick_glue:
    move.l  %sp,AES_TICK_SAVED_SP
    lea     AES_TICK_STACK_TOP,%sp
    tst.l   AES_TIMER_COUNTDOWN
    beq.s   1f
    addq.l  #1,AES_TIMER_ELAPSED
    subq.l  #1,AES_TIMER_COUNTDOWN
    bne.s   1f
    move.l  AES_TIMER_ELAPSED,-(%sp)
    move.l  #aes_tchange_fork,-(%sp)                /* $fed44e: the fork function, by value */
    M68K_JSR_LONG(aes_forkq_alcyon)                 /* $fed454: jsr forkq */
    addq.l  #8,%sp
1:  move.w  #B_DELAY_ONE_TICK,-(%sp)
    M68K_JSR_LONG(aes_b_delay_alcyon)               /* $fed460: jsr b_delay */
    addq.l  #2,%sp
    movea.l AES_TICK_SAVED_SP,%sp
    movea.l AES_TICK_CHAIN,%a0
    jsr     (%a0)
    rts
    .size   aes_rom_tick_glue,.-aes_rom_tick_glue

/* ==== THE ALCYON ENTRIES of the three C routines the glue calls: local thunks, no ROM bytes ========================== */

/* b_click(buttons.w) and b_delay(ticks.w): the one word sign-extended into its slot, as a C caller promotes it. */
#define WORD_ARGUMENT_THUNK(thunk, body)                                                                               \
    .type   thunk,@function;                                                                                           \
thunk:                                                                                                                 \
    move.w  ALCYON_WORD(%sp),%d0;                                                                                      \
    ext.l   %d0;                                                                                                       \
    move.l  %d0,-(%sp);                                                                                                \
    pea     (0).w;                                                                                                     \
    jsr     body;                                                                                                      \
    addq.l  #(IMAGE_ARGUMENT_BYTES + ONE_ARGUMENT_SLOT * SLOT_BYTES),%sp;                                              \
    rts;                                                                                                               \
    .size   thunk,.-thunk

WORD_ARGUMENT_THUNK(aes_b_click_alcyon, aes_b_click)
WORD_ARGUMENT_THUNK(aes_b_delay_alcyon, aes_b_delay)

/* forkq(code.l, data.l): the data is the longword the glue's two words — or its one long — already make. */
    .type   aes_forkq_alcyon,@function
aes_forkq_alcyon:
    move.l  (ALCYON_LONG_PAIR + SLOT_BYTES)(%sp),-(%sp)
    move.l  (ALCYON_LONG_PAIR + SLOT_BYTES)(%sp),-(%sp)     /* the code, the stack one slot deeper */
    pea     (0).w
    jsr     aes_forkq
    lea     (IMAGE_ARGUMENT_BYTES + TWO_ARGUMENT_SLOTS * SLOT_BYTES)(%sp),%sp
    rts
    .size   aes_forkq_alcyon,.-aes_forkq_alcyon
