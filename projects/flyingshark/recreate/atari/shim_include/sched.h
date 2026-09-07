/* sched.h — the SHIM'S busy-wait doors, shadowing `tools/recreate_kit/include/sched.h`.
 *
 * The kit's header names this file before it exists: "ON TARGET this file IS EXCLUDED FROM THE
 * BUILD, exactly like src/hw.c and src/psg.c: a build for the real machine spins on the address
 * itself, because the interrupt really does write it, and supplies its own `sched_wait8`/
 * `sched_poll16` that loop without a cap."
 *
 * THE CAP IS THE WHOLE DIFFERENCE, and dropping it is not an optimisation — it is the seam's
 * reason to exist (docs/on-target-execution.md, "Two ways a seam leaks the harness into the shipped
 * program"). Off target a wait no case releases has to end, or the suite hangs instead of failing;
 * `OS_SCHED_POLL_MAX` is what makes it a named refusal. On the machine the byte really is written
 * by an interrupt, so a bounded wait would abandon a player who had not touched the stick for 4,096
 * polls — the sibling project shipped exactly that at a high-score prompt before it was found.
 *
 * FOUR CALL SITES REACH THIS BUILD, all four spinning on a byte only `acia_ikbd_isr` writes or on
 * the longword only `vbl_handler` writes:
 *
 *   ../src/sprite.c   `render_frame`'s frame pacer          — `A_vbl_tick`, the VBL's counter
 *   ../src/player.c   the pause key                         — `A_joy1_state`
 *   ../src/hud.c      the cheat arm and the fire release    — `A_key_bits` / `A_joy1_state`
 *   ../src/frontend.c `debug_wait_for_keypad4`              — `A_key_bits` (no caller in the image)
 *
 * EVERY READ IS `volatile`, which off target it need not be. The kit's own bodies are opaque to the
 * caller's optimiser — they are in another translation unit — so a core may spin on `sched_poll8`
 * without saying anything about re-reading. Here the body is visible and the value is changed by an
 * interrupt, so without `volatile` GCC is free to hoist the load out of the loop and spin for ever
 * on a byte it read once. (../src/sprite.c's `vbl_tick_now` makes the same argument for its own
 * longword read, in the core, where it is true on both shores.)
 *
 * THE KIT'S HEADER IS NOT `#include_next`ed: its `sched_poll8`/`sched_wait8`/`sched_poll16` are
 * declared `extern` and C forbids a `static inline` definition of a name already declared without
 * `static`. Its other names are the harness's `g_sched_*` accessors, which exist only off target.
 */
#ifndef FS_SHIM_SCHED_H
#define FS_SHIM_SCHED_H

#include <stdint.h>

/* One poll of a byte an interrupt writes. `site_pc` is the wait site's own address, which off
 * target keys the per-site poll count the harness compares against the oracle's arrivals; here
 * there is no oracle and nothing to key, and the parameter stays so that the cores compile
 * unchanged. */
static inline uint8_t sched_poll8(uint8_t *image, uint32_t addr, uint32_t site_pc) {
    (void)site_pc;
    return *(volatile uint8_t *)(image + addr);
}

/* The byte wait, uncapped: spin until the interrupt writes `until`. Answers 1 — "the byte arrived"
 * — always, because the only other answer the kit has is the cap this build does not carry. */
static inline int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc) {
    while (sched_poll8(image, addr, site_pc) != until)
        ;
    return 1;
}

/* ONE iteration of a word wait, and the caller keeps its own compare (the kit's header argues why).
 * Answers 1 — "go round again" — always: the loop is left by the caller's own test, which is what
 * `render_frame`'s pacer does with the LONGWORD at `A_vbl_tick`. */
static inline int sched_poll16(uint8_t *image, uint32_t addr, uint32_t site_pc, uint16_t *seen) {
    const volatile uint8_t *word = image + addr;

    (void)site_pc;
    *seen = (uint16_t)(((uint16_t)word[0] << 8) | word[1]);
    return 1;
}

#endif /* FS_SHIM_SCHED_H */
