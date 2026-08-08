/* entry_state_probe.c — the fixture behind test_entry_state.py.
 *
 * `osh_run` forces SR = ENTRY_SR after the CPU reset, so every run enters with the condition codes
 * clear (see ENTRY_SR in ../oracle/shim.c and TRAP_MODEL.md, "The CPU configuration"). Nothing in
 * the kit's own suite can see that through Python: `harness`/`emu` bind a project's candidate .so at
 * import, and this directory deliberately binds no project. So this drives `osh_run` directly.
 *
 * The routine it runs is one `abcd`, which folds in the entry X flag and nothing else, three times
 * in ONE process — with a middle run that wraps $99 + $01 and so leaves X SET. Remove the force and
 * the third run answers 1 where the first answered 0, which is the whole defect: a differential over
 * any routine reading a condition code on entry becomes order-dependent, and so flaky under
 * `pytest -n auto` in a way no case could attribute.
 *
 * Output is one line per run: `<run-name> <d0 as decimal>`. The Python side owns the expectations,
 * so a run added here without a claim there fails loudly rather than silently.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "probe_common.h"   /* the oracle's entry points, the image geometry, plant_word */

#define PROBE_MAX_INSNS  8u        /* the routine is two instructions; a run that overruns is a bug */
#define ABCD_D1_D0 0xc101u         /* abcd d1,d0 — the one 68000 op whose result IS the entry X */

/* Run `abcd d1,d0` once and return the byte it left in d0. */
static uint32_t abcd_run(uint8_t accumulator, uint8_t addend) {
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, ABCD_D1_D0);
    plant_rts(PROBE_ENTRY + 2);

    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    dregs[0] = accumulator;
    dregs[1] = addend;
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the probe's routine did not return to the sentinel\n");
        exit(1);
    }
    return out[0] & 0xffu;
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    /* $00 + $00 is 0 with X clear on entry and 1 with X set, so the first and third runs are the
     * same question asked either side of a run that answers it differently. */
    printf("first_zero_add %u\n", abcd_run(0x00, 0x00));
    printf("arming_wrap %u\n", abcd_run(0x99, 0x01));   /* wraps to $00 and leaves X SET */
    printf("second_zero_add %u\n", abcd_run(0x00, 0x00));

    free(g_image);
    return 0;
}
