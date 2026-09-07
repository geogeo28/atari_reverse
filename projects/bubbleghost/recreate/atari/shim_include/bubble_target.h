/* bubble_target.h — the shim's own cross-translation-unit surface.
 *
 * Three files make up the shim — `bubble_os.s`, `bubble_main.c`, `bubble_backend.c` — and this is
 * everything they hand each other. NOTHING HERE EXISTS OFF TARGET, and no core reaches this file
 * by any path: not directly, and not through the three shadowing headers beside it, which is why
 * `bg_file_opens`, `bg_hw_writes` and `bg_gem_dispatch` are declared in `os.h`/`hw.h` — the headers
 * whose doors keep them — rather than here. `build.sh`'s containment gate reads the cores' include
 * CLOSURE, not their `#include` lines, so a dependency added the other way round would be caught;
 * this comment is why it never has to be.
 *
 * `tos.h` is the neighbouring header and the split is by WHO IMPLEMENTS: tos.h is what
 * `bubble_os.s` provides (traps and machine primitives), this is what the two C files provide.
 */
#ifndef BUBBLEGHOST_TARGET_H
#define BUBBLEGHOST_TARGET_H

#include <stdint.h>

/* ---- the image base is NOT declared here -------------------------------------------------------
 * `bg_image_base` is `os.h`'s, for this file's own rule: a name a DOOR keeps is declared in the
 * header that keeps the door. Four of os.h's doors (the XBIOS video group) and the GEM door both
 * turn an image offset into a machine address through it, so it is declared there and both C files
 * reach it by including `os.h` — which they do already. */

/* ---- bubble_main.c, for bubble_os.s ------------------------------------------------------------ */

/* `_start` calls this, and its `rts` is followed by Pterm0. */
void bubble_main(void);

/* The basepage GEMDOS handed `_start` and the stack pointer it was entered with, both latched
 * before anything else runs. They are the measured memory budget — `record_memory_budget` floors
 * the TPA's ceiling at the LOWER of p_hitpa and this SP. */
extern uint8_t *bg_basepage;
extern uint8_t *bg_initial_sp;

/* What `_start`'s `Mshrink` did: the new top of the program's block, and GEMDOS's answer (0 =
 * accepted). BOTH ARE RECORD FIELDS, because a shrink that did not happen has no symptom of its
 * own — it shows up as TOS's VDI answering workstation handle 0 for want of 308 bytes, and every
 * drawing call the game makes after that silently does nothing (bubble_os.s says what that cost). */
extern uint8_t *bg_kept_top;
extern uint32_t bg_mshrink_result;

/* The C half of the Timer C entry: bumps the count and runs the verified `timer_c_sound_isr`. */
void bg_timer_c_tick(void);

/* Timer C interrupts this run has taken, at 200 Hz. `volatile` because the anchor's hold reads it
 * from a spin whose only way out is the interrupt itself. */
extern volatile uint32_t bg_timer_c_ticks;

/* Where `bg_timer_c_entry` chains to — TOS's own $114, read off the machine before the install and
 * cross-checked against the longword the verified `install_sound_vectors` parked in the image. The
 * handler does not `rte`; it leaves the frame for TOS's handler, exactly as the original's does. */
extern uint32_t bg_timer_c_chain;

/* ---- bubble_backend.c, for bubble_main.c -------------------------------------------------------
 *
 * The three libc functions it also defines are declared in `string.h` beside this file, not here:
 * the kit's own `os.h` includes <string.h>, so the shadow has to exist anyway and a second
 * declaration would be a second contract for one name.
 */

/* How many `trap #2` calls the GEM door made, split by binding. STATE.BIN publishes both: a VDI
 * count of zero is a menu that drew nothing, which no screenshot of a black page can tell from a
 * palette fault. */
extern volatile uint32_t bg_vdi_calls;
extern volatile uint32_t bg_aes_calls;

/* ...and how many of the VDI's calls were the raster copy whose MFDB chain the door has to walk.
 * It is the one translation with more than one level of indirection, so it is the one whose
 * absence would show as sprites drawn from the 68000's vector page rather than as nothing at all. */
extern volatile uint32_t bg_vdi_raster_copies;

#endif /* BUBBLEGHOST_TARGET_H */
