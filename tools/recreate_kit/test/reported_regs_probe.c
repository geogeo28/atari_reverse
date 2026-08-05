/* reported_regs_probe.c — the fixture behind test_reported_regs.py.
 *
 * `osh_run` reports the full `movem` register set back to its caller: D0..D7 then A0..A6, in that
 * order, and nothing past them (A7 is the harness's own stack pointer — see OSH_OUT_REGS in
 * ../oracle/shim.c and TRAP_MODEL.md, "What a run reports back"). A routine whose outputs live in
 * registers the oracle does not report cannot be pinned by a differential at all, so this set IS the
 * observability window every project's cases see through.
 *
 * The same obstacle as entry_state_probe.c: `harness`/`emu` bind a project's candidate .so at
 * import and this directory deliberately binds no project, so the oracle is unreachable from Python
 * here. This drives `osh_run` in C instead.
 *
 * Two runs, because "the window is open" is two claims:
 *   - `written`: one `movem.l (table).l,d0-d7/a0-a6` loads a DISTINCT mark into every reported
 *     register, over entry values from a different range. A register that came back holding its
 *     entry value was never read out of the CPU; one holding its neighbour's mark says the slot
 *     order is wrong.
 *   - `passthrough`: a bare `rts` over the same distinct entry values, which pins the report against
 *     the live register file rather than against whatever that one `movem` happens to do.
 * Plus a canary one slot past the reported set, to catch a run that writes more than it declares.
 *
 * Output is one line per register per run (`<run> <reg> <expected> <reported>`) and one `canary`
 * line. The Python side owns the claims, so a run added here without one there fails loudly.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ../oracle/shim.c ships no header — Python binds it by ctypes — so the entry points this probe
 * uses are declared here. They must match shim.c's definitions; a drift is a compile error, since
 * both translation units are linked together by the test's own build. */
int osh_run(uint8_t *mem, uint32_t size, uint32_t entry,
            const uint32_t *dregs, const uint32_t *aregs,
            uint32_t sp, uint32_t sentinel, uint32_t stop_pc, uint32_t max_insns,
            uint32_t *out_regs);
uint32_t osh_out_regs(void);

#define PROBE_IMAGE_SIZE 0x10000u  /* room for the routine, its table, the stack and the vector page */
#define PROBE_ENTRY      0x1000u   /* even, clear of the vector page and of shim.c's magic trap PCs */
#define PROBE_TABLE      0x1400u   /* the 15 longwords the movem loads (above the routine) */
#define PROBE_SP         0x8000u   /* the machine stack, well above the routine and its table */
#define PROBE_SENTINEL   0x2000u   /* the return address osh_run stops at */
#define PROBE_MAX_INSNS  8u        /* the routines are two instructions; an overrun is a bug */

#define MOVEM_L_ABSL_TO_REGS 0x4cf9u /* movem.l (xxx).l,<mask> */
#define MOVEM_MASK_D0_A6     0x7fffu /* bit 0 = d0 .. bit 7 = d7, bit 8 = a0 .. bit 14 = a6 */
#define OPCODE_RTS           0x4e75u

#define NREGS    8                 /* D0..D7 / A0..A7, as osh_run takes them */
#define OUT_REGS 15                /* what shim.c's OSH_OUT_REGS must be; checked against it below */
#define CANARY   0xdeadbeefu       /* parked one slot past the reported set */

/* Two ranges wide apart, so a reported value says WHICH of the two it is at a glance and a register
 * that was never read out of the CPU cannot masquerade as one that was. */
#define MARK_BASE  0xa5a50000u
#define ENTRY_BASE 0x5a5a0000u
#define VALUE_STEP 0x1111u         /* per-register spacing: every value in a run is distinct */

/* The order osh_run claims to report. The Python side asserts this IS d0..d7 then a0..a6. */
static const char *const REG_NAMES[OUT_REGS] = {
    "d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7",
    "a0", "a1", "a2", "a3", "a4", "a5", "a6",
};

static uint8_t *g_image;

static uint32_t mark_for(int slot)  { return MARK_BASE + (uint32_t)(slot + 1) * VALUE_STEP; }
static uint32_t entry_for(int slot) { return ENTRY_BASE + (uint32_t)(slot + 1) * VALUE_STEP; }

static void plant_word(uint32_t addr, uint16_t opcode) {
    g_image[addr] = (uint8_t)(opcode >> 8);
    g_image[addr + 1] = (uint8_t)opcode;
}

static void plant_long(uint32_t addr, uint32_t value) {
    plant_word(addr, (uint16_t)(value >> 16));
    plant_word(addr + 2, (uint16_t)value);
}

/* Run one planted routine over entry values from entry_for(), and print what came back. `expected`
 * gives the value each slot must hold afterwards. */
static void report_run(const char *name, uint32_t *canary_out, const uint32_t *expected) {
    uint32_t dregs[NREGS], aregs[NREGS];
    for (int i = 0; i < NREGS; i++) {
        dregs[i] = entry_for(i);
        aregs[i] = entry_for(NREGS + i);   /* a7's is ignored: osh_run forces it to sp */
    }

    uint32_t out[OUT_REGS + 1];
    for (int i = 0; i <= OUT_REGS; i++) out[i] = CANARY;
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "%s: the probe's routine did not return to the sentinel\n", name);
        exit(1);
    }
    for (int i = 0; i < OUT_REGS; i++)
        printf("%s %s %u %u\n", name, REG_NAMES[i], expected[i], out[i]);
    *canary_out = out[OUT_REGS];
}

int main(void) {
    if (osh_out_regs() != OUT_REGS) {
        fprintf(stderr, "shim.c reports %u registers, this probe is built for %d\n",
                osh_out_regs(), OUT_REGS);
        return 1;
    }
    g_image = calloc(PROBE_IMAGE_SIZE, 1);
    if (!g_image) return 1;

    uint32_t expected[OUT_REGS], canary_written = 0, canary_passthrough = 0;

    /* One movem loads all 15 from the table, in the mask's own order (d0..d7 then a0..a6). */
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVEM_L_ABSL_TO_REGS);
    plant_word(PROBE_ENTRY + 2, MOVEM_MASK_D0_A6);
    plant_long(PROBE_ENTRY + 4, PROBE_TABLE);
    plant_word(PROBE_ENTRY + 8, OPCODE_RTS);
    for (int i = 0; i < OUT_REGS; i++) {
        expected[i] = mark_for(i);
        plant_long(PROBE_TABLE + 4u * (uint32_t)i, expected[i]);
    }
    report_run("written", &canary_written, expected);

    /* A routine that touches nothing: every reported register must be the one the caller set. */
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, OPCODE_RTS);
    for (int i = 0; i < OUT_REGS; i++) expected[i] = entry_for(i);
    report_run("passthrough", &canary_passthrough, expected);

    printf("canary %u %u\n", canary_written, canary_passthrough);

    free(g_image);
    return 0;
}
