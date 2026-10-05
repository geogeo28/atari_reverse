/* aes/switch.h — THE PROCESS SWITCH as the AES's C reaches it: the dispatcher's entry and the interrupt-mask brackets,
 * the hand 68000 of gemdosif (`$fe387c..$fe39a5`) that has no C spelling.
 *
 * WHAT IS HERE. Three things the event layer's C calls and cannot be:
 *   dsptch `$fe387c`          — `tst.b indisp / bne rts`, else an rte frame built from its own return address and a
 *                               `jmp` into disp: the running process is saved, another runs, and the call returns only
 *                               when the scheduler comes back to this one.
 *   spl7_save `$fe3890` /     — the status register parked in a save word (`move.w sr,$8996`) and the interrupt mask
 *   spl_restore `$fe389c`       raised to 7 (`ori.w #$700,sr`); ...and back (`move.w $8996,sr`).
 *   the same bracket INLINE   — psetup `$fe397a` spells it itself, over its own save word `$8998`.
 *
 * OFF TARGET there is no status register and no second stack, so each is a statement about what a case may reach:
 *   - `aes_dsptch` goes to `recreate_dispatch`, a hook the case binds (`test/aes_event.py`). It answers nonzero when
 *     the call RETURNED to its caller; zero REFUSES — the machine would switch away, which no host core can follow —
 *     and the core halts by name. The hook is asked BEFORE the guard: a process never runs with `indisp` set (the
 *     snapshot holds 1 because it was taken inside disp), so a call the guard would turn into a bare `rts` is a state
 *     no machine reaches, refused like the blocking one rather than answered "nothing happened".
 *   - the mask brackets store NOTHING: the word the ROM parks is its caller's SR — the condition codes of whatever
 *     instruction ran last — which is the caller's CPU state, by nature another's for any C caller. psetup's save
 *     word is a named, vetted drop of the cases that reach its bracket (`aes_event.SR_PSETUP_DROP`, used by
 *     `aes_pdpipe`'s); the dispatcher's and spl7_save's are named when a case first reaches theirs — none does yet.
 *
 * ON TARGET the brackets are the ROM's own two instructions each, inline (no call: the ROM's `spl7_save` is a Line-F
 * call round the same two, and psetup's is inline already). dsptch has no inline form — it needs the caller's return
 * address under an rte frame — and is the entry `aes_dsptch` of the switch's own `.S`, declared here.
 */
#ifndef TOS102US_AES_SWITCH_H
#define TOS102US_AES_SWITCH_H

#include <stdint.h>

#include "addrs.h"
#include "machine.h"
#include "aes/aes.h"

#ifdef RECREATE_HOST_DIFFERENTIAL
/* The hook: the dispatcher entered over `image`; nonzero once the call has returned to its caller, zero to refuse. */
extern uint32_t (*recreate_dispatch)(uint8_t *image);

static inline void aes_dsptch(uint8_t *image)
{
    if (!recreate_dispatch(image))
        recreate_not_reconstructed("the dispatcher: the case's hook refused the call — the process would block "
                                   "(nothing it waits for satisfied) or yield, and the machine would switch away");
}

/* The status register parked in `save_word` and the interrupt mask raised to 7; nothing a host core can store. */
static inline void sr_mask_saving(uint8_t *image, uint32_t save_word)
{
    (void)image;
    (void)save_word;
}

static inline void sr_restore_from(uint8_t *image, uint32_t save_word)
{
    (void)image;
    (void)save_word;
}
#else
/* The switch's own entry (`.S`): entered by `jsr`, its return address the PC of the frame it builds. */
void aes_dsptch(uint8_t *image);

/* `move.w sr,<save word> / ori.w #$700,sr` — and `move.w <save word>,sr`. Macros, as an "i" operand must be a constant
 * where it is spelt. Supervisor instructions: the AES runs in supervisor state wherever it reaches them. */
#define sr_mask_saving(image, save_word)                                                                                \
    do {                                                                                                                \
        (void)(image);                                                                                                  \
        __asm__ volatile ("move.w %%sr,%c0\n\t"                                                                         \
                          "ori.w %1,%%sr"                                                                               \
                          :                                                                                             \
                          : "i"(save_word), "i"(SR_IPL_MASK)                                                            \
                          : "memory", "cc");                                                                            \
    } while (0)
#define sr_restore_from(image, save_word)                                                                               \
    do {                                                                                                                \
        (void)(image);                                                                                                  \
        __asm__ volatile ("move.w %c0,%%sr" : : "i"(save_word) : "memory", "cc");                                       \
    } while (0)
#endif

/* spl7_save / spl_restore ($f740 / $f744): the bracket over the shared save word. NO C CALLS THEM YET — declared with
 * the protocol they belong to, for band 4's next waves: tchange ($fe4e02) and adelay ($fe5566) re-arm the tick under
 * this bracket, as ap_trecd does (band 5). */
#define aes_spl7_save(image)   sr_mask_saving((image), AES_SR_SPL)
#define aes_spl_restore(image) sr_restore_from((image), AES_SR_SPL)

#endif /* TOS102US_AES_SWITCH_H */
