/* machine_probe.c — the fixture behind test_machine.py.
 *
 * `include/machine.h`'s extend helpers model the X (and C) bit an ordinary `add`/`sub` leaves, which
 * a reconstruction threads from a producing instruction to a consuming `addx`/`subx`/`roxl`. The bit
 * is not memory, so no differential over an image can see it: a candidate whose carry model is wrong
 * diverges only where the flag CHANGES a stored result, and a project that has one such site has no
 * pin for the helper itself.
 *
 * This is that pin for the LONGWORD pair. For each operand pair it plants
 *
 *     move.l #a,d0 / move.l #b,d1 / add.l d1,d0 / moveq #0,d2 / addx.l d2,d2 / rts
 *
 * (and the same with `sub.l`), which materialises the X the arithmetic left into D2 — a register
 * `osh_run` reports — and prints it beside what `long_add_extend`/`long_sub_extend` say. So the
 * helper is compared against the oracle's own 68000 rather than against a restatement of itself.
 *
 * Output is one line per case, `<op> <index> <left> <right> <helper> <cpu>`; the Python side owns
 * the claims — it carries the operands and the expected bit for every pair, so a case added or
 * edited here without the matching edit there fails loudly rather than silently widening.
 */
#include <stdint.h>

#include "machine.h"
#include "probe_common.h"

#define PROBE_MAX_INSNS 8u          /* six instructions; an overrun is a bug */

#define MOVE_L_IMM_TO_D0 0x203cu    /* move.l #imm32,d0 */
#define MOVE_L_IMM_TO_D1 0x223cu    /* move.l #imm32,d1 */
#define ADD_L_D1_TO_D0   0xd081u    /* add.l d1,d0 */
#define SUB_L_D1_FROM_D0 0x9081u    /* sub.l d1,d0 */
#define MOVEQ_0_TO_D2    0x7400u    /* moveq #0,d2 */
#define ADDX_L_D2_TO_D2  0xd582u    /* addx.l d2,d2 — d2 := 0 + 0 + X, i.e. the extend bit itself */

#define X_REPORT_REG 2              /* ...which is where the run leaves it, and out_regs' D2 slot */

/* The pairs. Chosen for the boundary rather than for the value: a sum that wraps exactly, one that
 * does not, both operands at the sign bit, and the zero cases where a borrow does and does not
 * happen. Mirrored case for case by test_machine.py's EXPECTED. */
static const uint32_t OPERANDS[][2] = {
    {0u, 0u},
    {0u, 1u},
    {1u, 0u},
    {1u, 0xffffffffu},
    {0xffffffffu, 1u},
    {0xffffffffu, 0xffffffffu},
    {0x80000000u, 0x80000000u},
    {0x7fffffffu, 1u},
    {0x12345678u, 0xedcba988u},
};
#define OPERAND_PAIRS (sizeof OPERANDS / sizeof OPERANDS[0])

/* Run one planted sequence and hand back the X bit it materialised into D2. */
static uint32_t extend_bit_from_the_cpu(uint16_t arithmetic, uint32_t left, uint32_t right) {
    uint32_t at = PROBE_ENTRY;

    plant_word(at, MOVE_L_IMM_TO_D0);
    at = plant_long(at + 2, left);
    plant_word(at, MOVE_L_IMM_TO_D1);
    at = plant_long(at + 2, right);
    plant_word(at, arithmetic);
    plant_word(at + 2, MOVEQ_0_TO_D2);
    plant_word(at + 4, ADDX_L_D2_TO_D2);
    plant_rts(at + 6);
    plant_rts(PROBE_SENTINEL);

    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "machine_probe: the planted routine did not reach the sentinel\n");
        exit(1);
    }
    return out[X_REPORT_REG];
}

int main(void) {
    probe_alloc_image();
    probe_require_out_regs();

    for (unsigned i = 0; i < OPERAND_PAIRS; i++) {
        uint32_t left = OPERANDS[i][0], right = OPERANDS[i][1];

        printf("add %u %u %u %u %u\n", i, left, right, long_add_extend(left, right),
               extend_bit_from_the_cpu(ADD_L_D1_TO_D0, left, right));
        printf("sub %u %u %u %u %u\n", i, left, right, long_sub_extend(left, right),
               extend_bit_from_the_cpu(SUB_L_D1_FROM_D0, left, right));
    }
    return 0;
}
