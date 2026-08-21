/* psg.c — the candidate side of the direct YM2149 path. WHY it exists and what it must agree with
 * is in ../include/psg.h and TRAP_MODEL.md ("Phase 6"); the contract the harness reads it through is
 * in ../README.md, "What the candidate .so must export".
 *
 * It lives in the kit for the same reason the Dosound ledger and the refusal tally next door do —
 * the contract is kit-wide, and kit.mk sweeps every kit source into every project's candidate, so
 * both surfaces are one implementation shared by every game rather than a copy per project.
 *
 * The two surfaces mirror the oracle's (oracle/shim.c) deliberately: the LEDGER is the ordered
 * (kind, reg, value) stream — every write AND every read — which is what catches an access that is
 * missing, extra, out of order or aimed at the wrong register; the FILE is what those writes left
 * behind, which is what a read-modify-write reads back and what a later run of the same driver would
 * build on. Neither is in the image, so neither is covered by the byte diff — that is exactly why
 * both are exported and compared.
 *
 * ON-TARGET builds do not compile this file: a reconstruction running on real hardware writes
 * $ff8800/$ff8802 itself (see src/dosound_log.c for the same split). Off target it IS compiled,
 * into every candidate by kit.mk. One that did compile it on
 * target would also need OS_NO_REFUSAL_TALLY, since psg_port_read routes a refusal through
 * os_refused().
 */
#include <stdint.h>

#include "os.h"
#include "psg.h"

static uint8_t  g_psg_regs[OS_PSG_NREGS];   /* the register file a read is served from */
static uint16_t g_psg_regs_known;           /* bit R = register R's contents are known */
/* The ordered event stream — reads included, see psg.h. Three parallel arrays rather than a struct
 * array so the harness can cast each one straight through ctypes, the way it already does the
 * oracle's. */
static uint8_t  g_psg_log_kind[OS_PSG_LOG_MAX];
static uint8_t  g_psg_log_reg[OS_PSG_LOG_MAX];
static uint8_t  g_psg_log_val[OS_PSG_LOG_MAX];
static uint32_t g_psg_log_n;

/* Clear the ledger and install the run's seed — the register contents the case declares the chip
 * held on entry. The harness calls this before EACH candidate run, the poison re-run included, so a
 * run always starts from the case's own state and never from the previous run's, exactly as the
 * oracle's file is re-seeded per osh_run. `seed` is read only where `known` declares a register, so
 * a caller with nothing to declare may pass NULL. */
void g_psg_reset(const uint8_t *seed, uint32_t known) {
    g_psg_log_n = 0;
    g_psg_regs_known = (uint16_t)known;
    for (unsigned reg = 0; reg < OS_PSG_NREGS; reg++)
        g_psg_regs[reg] = (known & (1u << reg)) ? seed[reg] : 0;
}

uint32_t        g_psg_log_count(void)  { return g_psg_log_n; }
const uint8_t  *g_psg_log_kinds(void)  { return g_psg_log_kind; }
const uint8_t  *g_psg_log_regs(void)   { return g_psg_log_reg; }
const uint8_t  *g_psg_log_vals(void)   { return g_psg_log_val; }
const uint8_t  *g_psg_file(void)       { return g_psg_regs; }
uint32_t        g_psg_file_known(void) { return g_psg_regs_known; }

/* Append one event. Entries past the cap are dropped exactly as the oracle's ledger drops them, so a
 * run longer than the cap still compares like for like; the harness refuses a comparison at the cap
 * rather than trust a truncated one. */
static void psg_log(uint8_t kind, unsigned reg, uint8_t value) {
    if (g_psg_log_n >= OS_PSG_LOG_MAX)
        return;
    g_psg_log_kind[g_psg_log_n] = kind;
    g_psg_log_reg[g_psg_log_n] = (uint8_t)reg;
    g_psg_log_val[g_psg_log_n] = value;
    g_psg_log_n++;
}

/* Is `reg` a register this chip has? See psg.h: out of range is refused, not masked. */
static int psg_reg_in_range(unsigned reg) { return reg < OS_PSG_NREGS; }

void psg_port_write(unsigned reg, uint8_t value) {
    if (!psg_reg_in_range(reg)) {
        os_refused(0);
        return;
    }
    g_psg_regs[reg] = value;
    g_psg_regs_known |= (uint16_t)(1u << reg);
    psg_log(OS_PSG_EVENT_WRITE, reg, value);
}

uint8_t psg_port_read(unsigned reg) {
    if (!psg_reg_in_range(reg))
        return (uint8_t)os_refused(0);
    /* The event is logged either way — a refused read still HAPPENED, and the oracle logs its own
     * refused read too, so a stream that dropped it here would diverge for the wrong reason. */
    uint8_t served = (g_psg_regs_known & (1u << reg))
                     ? g_psg_regs[reg]
                     : (uint8_t)os_refused(0);     /* see psg.h: an undeclared register is an input */
    psg_log(OS_PSG_EVENT_READ, reg, served);
    return served;
}
