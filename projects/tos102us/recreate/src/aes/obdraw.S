/* obdraw.S — TARGET ONLY: just_draw's ALCYON ENTRY, the routine the target ob_draw hands everyobj (`obdraw.c`, spelt
 * at the call by `staged_call.h`'s ALCYON_ROUTINE). GLUE, NOT A TRANSCRIPTION: the ROM has no such bytes, so it has no row of `include/transcribed.h`
 * and `atari/target.mk` lists it apart (ALCYON_ENTRY_SOURCES).
 *
 * WHY IT EXISTS. ob_draw hands everyobj just_draw BY VALUE ($fea08c `move.l #$fe9a88,-(sp)`), and everyobj calls it as
 * Alcyon calls anything (`staged_call.h`, call_alcyon_object): a TEN-byte frame — the tree a longword, the object, x
 * and y words — under the return address. A target ob_draw handing it $fe9a88 would run the ROM's just_draw inside our
 * build, which Tier 3's (V) rule refuses by name (`bench/tier3.py`, `_measure_through_the_os`), and a rebuilt ROM owes
 * everyobj its OWN just_draw ("a ported row names the file whose C now owes it", `test/test_aes_rom_data.py`). This
 * entry repacks the frame into the GCC m68k call the C core takes — the image base 0 (`c_call_glue.h`), then a
 * longword slot per argument, each word SIGN-extended into its slot as a C caller promotes an `int16_t` — and enters
 * it. Tier 3 counts its cycles as glue (`bench/tier3.py`, ALCYON_ENTRIES), as it counts the generated thunks'.
 *
 * REGISTERS: the entry's own instructions change D0 and A0; with the C core it calls, D0-D1/A0-A1 (GCC's to lose; the
 * core keeps D2-D7/A2-A6 itself) — all inside Alcyon's contract, under which everyobj keeps nothing in D0-D2/A0-A2
 * across the call (`staged_call.h`'s call_alcyon_object: D0-D2/A1-A2 clobbered, A0 an in-out operand).
 */
#include "c_call_glue.h"

/* What the C call pushes after the image: the tree, the object, x and y. */
#define C_ARGUMENT_SLOTS      4

    .text

    .globl  aes_just_draw_alcyon
    .type   aes_just_draw_alcyon,@function
aes_just_draw_alcyon:
    lea     ALCYON_FIRST_ARGUMENT(%sp),%a0
    move.w  ALCYON_Y(%a0),%d0
    ext.l   %d0
    move.l  %d0,-(%sp)
    move.w  ALCYON_X(%a0),%d0
    ext.l   %d0
    move.l  %d0,-(%sp)
    move.w  ALCYON_OBJECT(%a0),%d0
    ext.l   %d0
    move.l  %d0,-(%sp)
    move.l  ALCYON_TREE(%a0),-(%sp)
    pea     (0).w                       /* the image base */
    jsr     aes_just_draw
    lea     (IMAGE_ARGUMENT_BYTES + C_ARGUMENT_SLOTS * SLOT_BYTES)(%sp),%sp
    rts
    .size   aes_just_draw_alcyon,.-aes_just_draw_alcyon
