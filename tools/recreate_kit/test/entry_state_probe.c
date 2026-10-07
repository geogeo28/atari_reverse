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
 * THE USER STACK POINTER is the same defect in another register (the last six runs): a reset leaves
 * the inactive stack pointer as the previous run left it, every run here is entered in supervisor
 * mode, and the register file a caller hands a run is D0..A6 and the supervisor's A7 — so nothing
 * said what USP a run began with. A routine that READS it (`move.l usp,a0`: an operating system's
 * context save does, and what it saves is then part of the image) answered by run order. The force
 * is ENTRY_USP in ../oracle/shim.c.
 *
 * BOTH FORCES ARE HELD THROUGH BOTH DOORS, `osh_run` and `osh_run_bench`: each is READ through each
 * door straight after a run that leaves the other value behind. A force that lived in one door alone
 * — moved out of the shared `enter_from_reset`, or added to one entry point — reddens the read made
 * through the other (measured, on three variants of the shim: no force, `osh_run`'s alone,
 * `osh_run_bench`'s alone). Bench runs are where the USP defect surfaced, so a pin that read through
 * `osh_run` only would have held the wrong door.
 *
 * Output is one line per run: `<run-name> <the value as decimal>`. The Python side owns the
 * expectations, so a run added here without a claim there fails loudly rather than silently.
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

#define MOVEQ_0_D0 0x7000u           /* moveq #0,d0 — and moveq leaves X as it found it */
#define MOVEQ_0_D1 0x7200u           /* moveq #0,d1 */
#define NO_ARGUMENT 0u

/* The zero add through the OTHER door. `osh_run_bench` hands a run no D0 / D1, so the routine clears
 * them itself — without touching X — and what `abcd` then leaves in d0 is still the entry X alone. */
static uint32_t abcd_zero_add_through_the_bench(void) {
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVEQ_0_D0);
    plant_word(PROBE_ENTRY + 2, MOVEQ_0_D1);
    plant_word(PROBE_ENTRY + 4, ABCD_D1_D0);
    plant_rts(PROBE_ENTRY + 6);

    uint32_t out[OUT_REGS] = {0};
    if (!osh_run_bench(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, NO_ARGUMENT,
                       PROBE_SP, PROBE_SENTINEL, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the bench's zero add did not return to the sentinel\n");
        exit(1);
    }
    return out[0] & 0xffu;
}

#define MOVE_L_USP_A0 0x4e68u        /* move.l usp,a0 — privileged, and every run is a supervisor's */
#define MOVE_L_A0_USP 0x4e60u        /* move.l a0,usp */
#define MOVE_L_SP_A0_ARG 0x206fu     /* movea.l 4(sp),a0 — osh_run_bench's one argument, at 4(sp) */
#define FIRST_ARG_OFFSET 4u
#define A_USER_STACK 0x00123456u     /* a value no reset leaves in USP */
#define OUT_A0 8                     /* out_regs: D0..D7 then A0..A6 */

static void plant_the_usp_read(void) {
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVE_L_USP_A0);
    plant_rts(PROBE_ENTRY + 2);
}

/* Read USP as a run entered through `osh_run_bench` finds it. */
static uint32_t usp_on_bench_entry(void) {
    plant_the_usp_read();

    uint32_t out[OUT_REGS] = {0};
    if (!osh_run_bench(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, NO_ARGUMENT,
                       PROBE_SP, PROBE_SENTINEL, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the bench's USP read did not return to the sentinel\n");
        exit(1);
    }
    return out[OUT_A0];
}

/* Read USP as a run entered through `osh_run` finds it. */
static uint32_t usp_on_entry(void) {
    plant_the_usp_read();

    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the USP probe's routine did not return to the sentinel\n");
        exit(1);
    }
    return out[OUT_A0];
}

/* Leave A_USER_STACK in USP (a bench run: the door with a stack argument); returns the USP the run left. */
static uint32_t leave_a_user_stack(void) {
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVE_L_SP_A0_ARG);
    plant_word(PROBE_ENTRY + 2, FIRST_ARG_OFFSET);
    plant_word(PROBE_ENTRY + 4, MOVE_L_A0_USP);
    plant_word(PROBE_ENTRY + 6, MOVE_L_USP_A0);
    plant_rts(PROBE_ENTRY + 8);

    uint32_t out[OUT_REGS] = {0};
    if (!osh_run_bench(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, A_USER_STACK,
                       PROBE_SP, PROBE_SENTINEL, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the USP probe's arming routine did not return to the sentinel\n");
        exit(1);
    }
    return out[OUT_A0];
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    /* $00 + $00 is 0 with X clear on entry and 1 with X set, so the first and third runs are the
     * same question asked either side of a run that answers it differently. */
    printf("first_zero_add %u\n", abcd_run(0x00, 0x00));
    printf("arming_wrap %u\n", abcd_run(0x99, 0x01));   /* wraps to $00 and leaves X SET */
    printf("second_zero_add %u\n", abcd_run(0x00, 0x00));
    /* ...and asked through the other door, straight after a run that leaves X set again. */
    printf("bench_arming_wrap %u\n", abcd_run(0x99, 0x01));
    printf("bench_zero_add %u\n", abcd_zero_add_through_the_bench());

    /* The user stack pointer, read through EACH door straight after a run that leaves one behind. */
    printf("first_usp %u\n", usp_on_entry());
    printf("first_bench_usp %u\n", usp_on_bench_entry());
    printf("arming_usp %u\n", leave_a_user_stack());    /* the run really left it: A_USER_STACK */
    printf("second_bench_usp %u\n", usp_on_bench_entry());
    printf("rearming_usp %u\n", leave_a_user_stack());
    printf("second_usp %u\n", usp_on_entry());

    free(g_image);
    return 0;
}
