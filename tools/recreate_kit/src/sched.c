/* sched.c — the candidate side of the scheduled-write model. WHY it exists and what a
 * reconstruction may poll is in ../include/sched.h; the encoding both sides share, and the reason
 * there are two sides at all, is in ../include/os.h ("SCHEDULED WRITES").
 *
 * It lives in the kit beside src/hw.c and src/psg.c, and for the same reason: kit.mk sweeps every
 * kit source into every project's candidate, so one implementation serves every game rather than a
 * copy per project.
 *
 * The oracle's half is oracle/shim.c's g_sched_* block. The two are deliberately symmetrical — the
 * same flattened entry array, the same os_sched_store — so that the only thing that can differ
 * between them is WHEN the store lands, which is exactly what the poll/arrival comparison measures.
 *
 * ON-TARGET builds exclude this file — a reconstruction on the real machine spins on the address
 * and the interrupt writes it — and supply their own uncapped `sched_wait8`. Off target it is
 * compiled into every candidate by kit.mk, which is what the harness checks for.
 */
#include <stdint.h>

#include "os.h"
#include "sched.h"

static uint32_t g_sched[OS_SCHED_MAX][OS_SCHED_FIELDS];
static uint32_t g_sched_n;
static uint32_t g_sched_polls_n;
static uint32_t g_sched_applied_n;
static uint32_t g_sched_refused_n;
static uint8_t  g_sched_fired[OS_SCHED_MAX];
static uint32_t g_sched_exhausted_n;

void g_sched_reset(const uint32_t *entries, uint32_t n) {
    g_sched_n = os_sched_install(g_sched, entries, n);
    g_sched_polls_n = 0;
    g_sched_applied_n = 0;
    g_sched_refused_n = 0;
    g_sched_exhausted_n = 0;
    for (uint32_t i = 0; i < OS_SCHED_MAX; i++)
        g_sched_fired[i] = 0;
}

uint32_t g_sched_count(void)     { return g_sched_n; }
uint32_t g_sched_polls(void)     { return g_sched_polls_n; }
uint32_t g_sched_applied(void)   { return g_sched_applied_n; }
uint32_t g_sched_refused(void)   { return g_sched_refused_n; }
uint32_t g_sched_exhausted(void) { return g_sched_exhausted_n; }

uint8_t sched_poll8(uint8_t *image, uint32_t addr) {
    uint32_t poll = ++g_sched_polls_n;
    for (uint32_t i = 0; i < g_sched_n; i++) {
        /* OS_SCHED_F_KIND and OS_SCHED_F_TRIGGER name a program counter, which this side does not
         * have; harness.differential refuses a differential carrying an AT_INSN entry for exactly
         * that reason, so every entry that reaches here is an AT_PC one whose NTH is a poll index. */
        if (g_sched_fired[i] || poll != g_sched[i][OS_SCHED_F_NTH])
            continue;
        g_sched_fired[i] = 1;
        /* OS_IMAGE_SIZE, because a reconstruction is handed the whole image and no length — the
         * same bound bus.h's os_in_image applies to every other guarded access on this side. */
        if (os_sched_store(image, OS_IMAGE_SIZE, g_sched[i][OS_SCHED_F_ADDR],
                           g_sched[i][OS_SCHED_F_WIDTH], g_sched[i][OS_SCHED_F_VALUE]))
            g_sched_applied_n++;
        else
            g_sched_refused_n++;
    }
    return os_in_image(addr, 1) ? image[addr] : (uint8_t)0;
}

int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until) {
    /* One poll per iteration, which is what makes each one the original's own arrival at its
     * compare — see sched.h. The cap is a property of the HARNESS and not of the routine: on target
     * this function is a bare `while` and the interrupt ends it. */
    for (uint32_t polled = 0; polled < OS_SCHED_POLL_MAX; polled++)
        if (sched_poll8(image, addr) == until)
            return 1;
    g_sched_exhausted_n++;
    /* Routed through os_refused() so it lands in the ONE tally harness.differential already reads
     * after every candidate run: an exhausted wait means the case's schedule never released it, and
     * a case that tested nothing must not come back green. g_sched_exhausted() is what says it was
     * THIS and not a missing Bconstat gate, since the tally is shared by every refusing helper. */
    (void)os_refused(0);
    return 0;
}
