/* init.h — the TWO UNDOORED XBIOS CALLS, answered by the machine instead of by the model.
 *
 * This is the ONE place a shim header shadows a CORE header rather than a kit one, and
 * `../include/init.h` asks for it in those words: "an on-target build replaces these two bodies
 * with the real XBIOS calls and whatever it is that turns their answers into something a core may
 * index through". ../STATUS.md's "Follow-ups the kit should absorb" carries both rows — the kit has
 * no `os_physbase()` or `os_kbdvbase()` door, so the project put one inline each in its own header
 * for a target build to swap, and this is the swap.
 *
 * Everything else in the core header is pulled in unchanged through `#include_next`, and the
 * `_Static_assert` at the bottom is what says so: it reads a constant only the real header defines,
 * so a shadow that had stopped reaching it fails at compile time rather than compiling a header
 * with two inlines and nothing else in it.
 *
 * ================================================================================================
 * PHYSBASE — WHY THIS ANSWERS A CONSTANT AND NOT `Physbase()`
 * ================================================================================================
 *
 * `boot_init` builds the screen ring DOWNWARDS from whatever Physbase answers: `- 0x1f900`, rounded
 * up to 256. So the answer decides where 161,280 bytes of framebuffer land, and in IMAGE space the
 * only legal answers are the ones that put the ring clear of the program, which ends at 0x5aede:
 * anything below 0x7a3de overlaps it. The original's own `Setscreen(0x70000, 0x78000)` is BELOW
 * that — its ring lands at 0x58800, and it fits only because the original loads at 0xaa56 and its
 * whole image space is shifted down by 0x55aa. A reconstruction inside a TPA has no such shift to
 * spend (../README.md, "The load-address budget"), so it chooses its Physbase, and the choice is
 * `test/abi.py`'s `SCREEN_RING_PHYSBASE`: the SAME number every differential case in the project
 * ran with, which makes the ring pointers on target byte-identical to the verified ones.
 *
 * WHAT STILL READS THE MACHINE BACK. `flyshark_main.c` calls the real `Physbase()` after its own
 * `Setscreen`, and again at the end of the run when the game has been publishing a moving base for
 * every frame, and puts both beside the shifter's own two bytes in the record — the class-8
 * read-back (docs/on-target-execution.md), which is the only instrument that catches a video base
 * the shifter truncated. `smoke.py` is what compares them; the program itself does not refuse,
 * because a program that stopped here would have no way to say why. So the constant is a decision
 * the machine is asked about every boot rather than a number nobody reads back — and in a build
 * with no record (the play build) the numbers are in RAM and nothing reads them, which
 * ../STATUS.md carries.
 *
 * ================================================================================================
 * KBDVBASE — WHY THIS ONE REALLY IS THE TRAP
 * ================================================================================================
 *
 * `boot_init` writes TOS's own joystick-packet vector, at `Kbdvbase() + 0x18`, through
 * `image + joyvec_slot`. Off target `OS_KBDVBASE` is a small number INSIDE the modelled image so
 * that indexing works; on the machine the struct is in ROM-owned RAM and is not an image offset at
 * all. So this answers the REAL pointer EXPRESSED IN IMAGE SPACE — subtract the image base here,
 * and the core's `image +` adds it back, landing on the real struct. The core is unchanged and
 * reads and writes TOS's own longword.
 *
 * The value it WRITES there is `FN_TOS_JOYVEC_HANDLER` = 0x141fa, an image address that means
 * nothing to TOS's parser — which never runs, because `acia_ikbd_isr` has taken the ACIA vector
 * (../src/irq.c: "DEAD ON THE MACHINE"). What makes that safe rather than lucky is the teardown:
 * `flyshark_main.c` puts `A_saved_tos_joyvec` back before it returns to GEMDOS, because a vector
 * left pointing into a freed TPA halts the machine about a second after `Pterm`
 * (docs/on-target-execution.md class 7).
 */
#ifndef FS_SHIM_INIT_H
#define FS_SHIM_INIT_H

#include <stdint.h>

/* `<tos.h>`, not `"tos.h"`: this file is IN shim_include, so a quoted include would be resolved by
 * this file's own directory and would leave a later `#include_next` with no search position to
 * resume from (docs/on-target-execution.md class 12b). */
#include <tos.h>

#define fs_physbase fs_model_physbase
#define fs_kbdvbase fs_model_kbdvbase
#include_next "init.h"
#undef fs_physbase
#undef fs_kbdvbase

/* The image-space screen address this build hands the shifter — `test/abi.py`'s
 * `SCREEN_RING_PHYSBASE`, from which `boot_init`'s own arithmetic derives the ring at 0x60000. Spelt
 * here because this is the file that answers with it. */
#define FS_TARGET_PHYSBASE 0x7f800u

_Static_assert(FS_TARGET_PHYSBASE - SCREEN_RING_BYTES >= FS_PROGRAM_END,
               "the screen ring would land inside the program: Physbase - 0x1f900 must clear "
               "0x5aede, which is why the original's own 0x78000 cannot be used here");

static inline uint32_t fs_physbase(void) { return FS_TARGET_PHYSBASE; }

/* The real trap, expressed in image space so that the core's `image + it` lands back on TOS's own
 * struct. The subtraction is between two unrelated objects and is exactly what the image model is:
 * one flat address space that this build maps onto the machine's by a constant. */
static inline uint32_t fs_kbdvbase(void) {
    return (uint32_t)((uint8_t *)Kbdvbase() - fs_image_base);
}

_Static_assert(BOOT_SETSCREEN_PHYS == 0x78000u,
               "this shadow did not reach ../include/init.h — see the header comment");

#endif /* FS_SHIM_INIT_H */
