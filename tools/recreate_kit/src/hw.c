/* hw.c — the candidate side of the seeded hardware read model. WHY it exists and what it must agree
 * with is in ../include/hw.h and TRAP_MODEL.md ("Phase 7"); the contract the harness reads it
 * through is in ../README.md, "What the candidate .so must export".
 *
 * It lives in the kit, beside src/psg.c and the refusal tally, because the contract is kit-wide and
 * kit.mk sweeps every kit source into every project's candidate — so both surfaces are one
 * implementation shared by every game rather than a copy per project.
 *
 * The two surfaces mirror the oracle's (oracle/shim.c) deliberately: the LEDGER is the ordered
 * (slot, value) read stream, which is what catches a read that is missing, extra, out of order or
 * aimed at the wrong modeled address; the FILE is what those reads are served from, compared as a
 * cross-check that the two model implementations have not drifted. Neither is in the image, so
 * neither is covered by the byte diff — that is exactly why both are exported and compared.
 *
 * ON-TARGET builds do not compile this file: a reconstruction running on real hardware reads the
 * address itself. Off target it IS compiled, into every candidate by kit.mk. One that did compile
 * it on target would also need OS_NO_REFUSAL_TALLY, since hw_read8 routes a refusal through
 * os_refused(). (The first clause read "Off-target" until batch 42 phase A, which contradicted the
 * rest of the sentence and the build it describes.)
 */
#include <stdint.h>

#include "os.h"
#include "hw.h"

static uint8_t  g_hw_bytes[OS_HW_NSLOTS];   /* the declared bytes a read is served from */
static uint32_t g_hw_bytes_known;           /* bit S = slot S's contents were declared */
/* The ordered read stream. Two parallel arrays rather than an array of structs so the harness can
 * cast each one straight through ctypes, the way it already does the oracle's. */
static uint8_t  g_hw_slot[OS_HW_LOG_MAX];
static uint8_t  g_hw_val[OS_HW_LOG_MAX];
static uint32_t g_hw_n;
/* ...and the WRITE ledger's, whose surfaces are at the bottom of this file. Its LENGTH is declared
 * here because `g_hw_reset` clears it: one reset per candidate run, not two, so a run cannot be
 * given a fresh read stream and the previous run's stores. */
static uint32_t g_hw_write_addr[OS_HW_WRITE_LOG_MAX];
static uint8_t  g_hw_write_width[OS_HW_WRITE_LOG_MAX];
static uint32_t g_hw_write_val[OS_HW_WRITE_LOG_MAX];
static uint32_t g_hw_write_n;

/* Clear the ledger and install the run's seed — the bytes the case declares the machine held on
 * entry. The harness calls this before EACH candidate run, the poison re-run included, so a run
 * always starts from the case's own state and never from the previous run's, exactly as the oracle's
 * file is re-seeded per osh_run. `seed` is read only where `known` declares a slot, so a caller with
 * nothing to declare may pass NULL. */
void g_hw_reset(const uint8_t *seed, uint32_t known) {
    g_hw_n = 0;
    g_hw_write_n = 0;      /* the WRITE ledger is this run's stores only; see hw_log_write below */
    /* The install is os.h's, shared verbatim with shim.c's hw_enter_run, so the two implementations
     * cannot hold two different ideas of what an undeclared ACIA status reads. */
    g_hw_bytes_known = os_hw_install_seed(g_hw_bytes, seed, known);
}

uint32_t        g_hw_log_count(void)  { return g_hw_n; }
const uint8_t  *g_hw_log_slots(void)  { return g_hw_slot; }
const uint8_t  *g_hw_log_vals(void)   { return g_hw_val; }
const uint8_t  *g_hw_file(void)       { return g_hw_bytes; }
uint32_t        g_hw_file_known(void) { return g_hw_bytes_known; }

/* Append one read. Entries past the cap are dropped exactly as the oracle's ledger drops them, so a
 * run longer than the cap still compares like for like; the harness refuses a comparison at the cap
 * rather than trust a truncated one. */
static void hw_log(int slot, uint8_t value) {
    if (g_hw_n >= OS_HW_LOG_MAX)
        return;
    g_hw_slot[g_hw_n] = (uint8_t)slot;
    g_hw_val[g_hw_n] = value;
    g_hw_n++;
}

uint8_t hw_read8(uint32_t addr) {
    int slot = os_hw_slot(addr);
    /* An address the model does not name is refused WITHOUT a ledger entry: the oracle has no entry
     * for it either (its callback answers such an address 0 and records nothing), so logging one
     * here would diverge the streams for a reason that is not about this read. */
    if (slot < 0)
        return (uint8_t)os_refused(0);
    /* A declared byte is served; an undeclared one is refused — and the event is logged EITHER WAY,
     * because a refused read still HAPPENED and the oracle logs its own (see shim.c's hw_read). */
    uint8_t served = (g_hw_bytes_known & (1u << slot))
                     ? g_hw_bytes[slot]
                     : (uint8_t)os_refused(0);     /* see hw.h: an undeclared byte is an input */
    hw_log(slot, served);
    return served;
}


/* ================================================================================================
 * THE HARDWARE WRITE MODEL (TRAP_MODEL.md, "Phase 10"). What it is for and what it pins are in
 * ../include/hw.h; this is the ledger behind it, and it mirrors shim.c's g_hw_write_* exactly.
 * Its arrays are declared at the top of this file, with g_hw_reset, which is the ONE reset both
 * ledgers get.
 * ============================================================================================= */
uint32_t        g_hw_write_count(void)   { return g_hw_write_n; }
const uint32_t *g_hw_write_addrs(void)   { return g_hw_write_addr; }
const uint8_t  *g_hw_write_widths(void)  { return g_hw_write_width; }
const uint32_t *g_hw_write_vals(void)    { return g_hw_write_val; }

static void hw_log_write(uint32_t addr, uint32_t width, uint32_t value) {
    /* Only one of the three DECODED I/O blocks belongs here, and anything else is a REFUSAL rather
     * than an entry — hw.h lists both shapes this rejects and why neither can be a ledger entry.
     * The test is deliberately unmasked, so the untranslated `$ffff8240` is refused too rather than
     * silently equated with `$ff8240`: os_hw_is_io's own header has that argument. Note this covers
     * an IMAGE address by construction, since every block starts far above OS_IMAGE_SIZE. */
    if (!os_hw_is_io(addr)) {
        os_refused(0);
        return;
    }
    /* Entries past the cap are dropped exactly as the oracle's are, so a run longer than the cap
     * still compares like for like; the harness refuses a comparison at the cap rather than trust a
     * truncated one. */
    if (g_hw_write_n >= OS_HW_WRITE_LOG_MAX)
        return;
    g_hw_write_addr[g_hw_write_n] = addr;
    g_hw_write_width[g_hw_write_n] = (uint8_t)width;
    g_hw_write_val[g_hw_write_n] = value & os_hw_write_mask(width);
    g_hw_write_n++;
}

void hw_write8(uint32_t addr, uint32_t value)  { hw_log_write(addr, OS_HW_WRITE_WIDTH_8, value); }
void hw_write16(uint32_t addr, uint32_t value) { hw_log_write(addr, OS_HW_WRITE_WIDTH_16, value); }
void hw_write32(uint32_t addr, uint32_t value) { hw_log_write(addr, OS_HW_WRITE_WIDTH_32, value); }
