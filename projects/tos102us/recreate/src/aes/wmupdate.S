/* wmupdate.S — TARGET ONLY: the ALCYON ENTRIES of the two window-tree walkers' routines — newrect, which the target
 * draw_change hands everyobj (`wmupdate.c`), and mkrect, which the target newrect hands it in turn (`wrect.c`), each
 * spelt at the call by `staged_call.h`'s ALCYON_ROUTINE. GLUE, NOT A TRANSCRIPTION: the ROM has no such bytes, so neither has a row of
 * `include/transcribed.h`, and `atari/target.mk` lists the file apart (ALCYON_ENTRY_SOURCES), as `obdraw.S`.
 *
 * WHY THEY EXIST. draw_change hands everyobj newrect BY VALUE ($fec146 `move.l #$fe5cee,-(sp)`) and newrect hands it
 * mkrect ($fe5d68 `move.l #$fe5c9a,-(sp)`); everyobj calls each as Alcyon calls anything (`staged_call.h`,
 * call_alcyon_object): a TEN-byte frame — the tree a longword, the object, x and y words — under the return address.
 * A target C handing the ROM addresses would run the ROM's routines inside our build, which Tier 3's (V) rule refuses
 * by name (`bench/tier3.py`, `_measure_through_the_os`), and a rebuilt ROM owes everyobj its OWN routines
 * (`test/test_aes_rom_data.py`). Each entry repacks the frame into the GCC m68k call the C core takes — the image base
 * 0 (`c_call_glue.h`), then the tree and the window (the object; neither core takes x or y), the window SIGN-extended
 * into its slot as a C caller promotes an `int16_t` — and enters it. Tier 3 counts their cycles as glue
 * (`bench/tier3.py`, ALCYON_ENTRIES).
 *
 * REGISTERS: the entry's own instructions change D0 and A0; with the C core it calls, D0-D1/A0-A1 (GCC's to lose; the
 * core keeps D2-D7/A2-A6 itself) — inside Alcyon's contract, under which everyobj keeps nothing in D0-D2/A0-A2 across
 * the call (`staged_call.h`'s call_alcyon_object).
 */
#include "c_call_glue.h"

/* What the C call pushes after the image: the tree and the window. */
#define C_ARGUMENT_SLOTS      2

/* ENTRY, the Alcyon entry of CORE: the window promoted, the tree, the image base, the call, the slots dropped. Each
 * entry's `.globl` is spelt out below, where `test/transcription.py` reads the ALCYON ENTRIES from. */
.macro walker_entry entry, core
    .type   \entry,@function
\entry:
    lea     ALCYON_FIRST_ARGUMENT(%sp),%a0
    move.w  ALCYON_OBJECT(%a0),%d0
    ext.l   %d0
    move.l  %d0,-(%sp)
    move.l  ALCYON_TREE(%a0),-(%sp)
    pea     (0).w                       /* the image base */
    jsr     \core
    lea     (IMAGE_ARGUMENT_BYTES + C_ARGUMENT_SLOTS * SLOT_BYTES)(%sp),%sp
    rts
    .size   \entry,.-\entry
.endm

    .text

    .globl  aes_newrect_alcyon
    .globl  aes_mkrect_alcyon
    walker_entry aes_newrect_alcyon, aes_newrect
    walker_entry aes_mkrect_alcyon, aes_mkrect
