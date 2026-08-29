/* sched.h — the ON-TARGET busy-wait header, shadowing the kit's for the PRG build only.
 *
 * It REPLACES rather than extends, which is why there is no `#include_next` here (hw.h and os.h in
 * this directory do have one). The kit's `sched.h` declares three functions that
 * `tools/recreate_kit/src/sched.c` defines, and build.sh excludes the kit's whole `src/` from a
 * target build — so on the real machine those symbols would simply not exist. The kit's own header
 * says what to put in their place:
 *
 *   "ON TARGET this file IS EXCLUDED FROM THE BUILD, exactly like src/hw.c and src/psg.c: a build
 *    for the real machine spins on the address itself, because the interrupt really does write it,
 *    and supplies its own `sched_wait8`/`sched_poll16` that loop without a cap."
 *
 * That is this file, as `static inline` bodies rather than as prototypes plus a definition in
 * `zynaps_backend.c`: there is nothing here a backend could do better than a `volatile` read, and a
 * header that is complete on its own cannot get out of step with a definition elsewhere.
 *
 * THE CAP IS THE WHOLE DIFFERENCE, and dropping it is not a liberty — it is the point. Off target
 * the byte a wait spins on is supplied by the case's declared schedule, so a wait the case never
 * releases must give up rather than hang a pytest worker; on target the VBL and the IKBD ACIA
 * really do write these bytes, and a bounded spin would give up on a slow frame and carry on as
 * though the key had arrived. `site_pc` goes the same way: it is how the off-target model tells one
 * wait from another when it compares poll counts, and a real 68000 has no use for it.
 *
 * `volatile` is what the bodies turn on. The bytes are written by an interrupt handler and read
 * here in a loop with nothing else in it, so without it GCC hoists the read out and the loop never
 * ends — the one way this file can be wrong that the compiler will not say anything about.
 */
#ifndef ZYNAPS_TARGET_SCHED_H
#define ZYNAPS_TARGET_SCHED_H

#include <stdint.h>

/* Read the byte at `addr` as one iteration of a busy-wait. `site_pc` is ignored; see above. */
static inline uint8_t sched_poll8(uint8_t *image, uint32_t addr, uint32_t site_pc) {
    (void)site_pc;
    return *(volatile uint8_t *)(image + addr);
}

/* Spin until that byte reads `until`. Always answers 1: on the real machine the wait ends when the
 * interrupt says so, and the 0 the off-target version can answer has no counterpart here. */
static inline int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc) {
    while (sched_poll8(image, addr, site_pc) != until)
        ;
    return 1;
}

/* THE KIT'S THIRD PRIMITIVE, `sched_poll16`, IS DELIBERATELY ABSENT. No Zynaps core calls it, and a
 * hand-written body here could not be exercised by anything — nothing off target links this file and
 * nothing on target calls it — so it would be an untested word read in the one build with no oracle
 * behind it. It also has a real trap waiting for whoever writes it: two byte reads with the ACIA or
 * VBL handler free to run between them can TEAR (0x00ff -> 0x0100 read as 0x0000), which `volatile`
 * does nothing about, so the target form wants one aligned word load. Add it with its first caller.
 */

#endif /* ZYNAPS_TARGET_SCHED_H */
