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
 * THE DECLARED I/O MAP (TRAP_MODEL.md, "Phase 15"). What it is for is in ../include/hw.h; this is
 * the candidate's half of it, and it mirrors shim.c's g_io_* exactly. The map is address-keyed
 * rather than slot-keyed, which is the ONE way it differs from the named set above.
 * ============================================================================================= */
static uint32_t g_io_addr[OS_IO_SEED_MAX];   /* the declared addresses, 24-bit bus form */
static uint8_t  g_io_writeback[OS_IO_SEED_MAX];  /* ...and which of them LATCH a store (os.h) */
/* ...and what a read of each is served NOW. The oracle keeps the declaration and this live copy
 * apart, because a run there may be resumed and a bench segment must not re-seed; this side has no
 * such split — `g_io_reset` runs before EVERY candidate run and re-installs the declaration into
 * these bytes, so a previous run's write-through store cannot survive into the next one. */
static uint8_t  g_io_live[OS_IO_SEED_MAX];
static uint32_t g_io_n;
/* The ordered ledger of SERVED reads, (address, width, value), mirroring shim.c's. A REFUSED read
 * is not an entry, because the oracle has none for it either: its callback counts the byte as an
 * unmodeled I/O read and answers 0, so an entry here would diverge the streams for a reason that is
 * not about this read. */
static uint32_t g_io_log_addr[OS_IO_LOG_MAX];
static uint8_t  g_io_log_width[OS_IO_LOG_MAX];
static uint32_t g_io_log_val[OS_IO_LOG_MAX];
static uint32_t g_io_log_n;

/* Install the case's declared map and clear the ledger. The harness calls this before EACH candidate
 * run, the poison re-run included, exactly as it calls g_hw_reset.
 *
 * The install is os.h's, shared verbatim with shim.c's osh_io_seed, so the two implementations
 * cannot hold two different ideas of which addresses are declarable. A declaration os.h's rule
 * REJECTED — a Phase-7 named slot, a YM2149 port, an address below the I/O page — is a refusal
 * rather than a silent shortfall: the case declared a byte this model will never serve, and a run
 * that went on to read it would refuse anyway, one layer down and with a less useful message. */
void g_io_reset(const uint32_t *addrs, const uint8_t *values, const uint8_t *writeback,
                uint32_t n) {
    g_io_log_n = 0;
    /* Installed STRAIGHT INTO the live bytes: this runs before every candidate run, so re-installing
     * the declaration IS what stops a write-through store made by the previous run from reaching
     * this one, and a second array holding the declaration would be state nothing else reads. */
    g_io_n = os_io_install_seed(g_io_addr, g_io_live, g_io_writeback, addrs, values, writeback, n);
    if (g_io_n != n)
        os_refused(0);
}

uint32_t        g_io_seed_count(void)  { return g_io_n; }

/* How many installed entries this run's case marked WRITE-THROUGH. The harness compares it against
 * the oracle's own count of the same declaration, which is the one surface that says the candidate
 * built the writeback COLUMN — a candidate that installed the addresses and the values and dropped
 * the column serves every read from a byte no store can ever change, and every case whose seed has
 * no write-through byte in it stays green. It is also the newest symbol in `_HW_LEDGER_ABI`, which
 * is what makes a STALE .so predating `g_io_reset`'s writeback argument fail the presence probe
 * instead of being called with an argument it does not take. */
uint32_t        g_io_writeback_count(void) {
    uint32_t marked = 0;
    for (uint32_t i = 0; i < g_io_n; i++)
        marked += g_io_writeback[i] == OS_IO_WRITE_THROUGH;
    return marked;
}

uint32_t        g_io_log_count(void)   { return g_io_log_n; }
const uint32_t *g_io_log_addrs(void)   { return g_io_log_addr; }
const uint8_t  *g_io_log_widths(void)  { return g_io_log_width; }
const uint32_t *g_io_log_vals(void)    { return g_io_log_val; }

/* Serve `width` bytes at `addr` from the declared map, or refuse. ALL OR NOTHING, which is hw.h's
 * contract and whose argument is in TRAP_MODEL.md, "Phase 15": a wide read is N declared bytes, and
 * one missing byte refuses the whole access rather than fabricating that half — the oracle's
 * callback refuses the same access for the same reason.
 *
 * Entries past the cap are dropped exactly as the oracle's are, so a run longer than the cap still
 * compares like for like; the harness refuses a comparison at the cap rather than trust a truncated
 * one. */
static uint32_t io_read(uint32_t addr, uint32_t width) {
    uint32_t served = 0;
    for (uint32_t i = 0; i < width; i++) {
        int entry = os_io_find(g_io_addr, g_io_n, addr + i);
        if (entry < 0)
            return os_refused(0);        /* see hw.h: an undeclared I/O byte is an input, not a 0 */
        served = served << 8 | g_io_live[entry];
    }
    if (g_io_log_n < OS_IO_LOG_MAX) {
        g_io_log_addr[g_io_log_n] = addr;
        g_io_log_width[g_io_log_n] = (uint8_t)width;
        g_io_log_val[g_io_log_n] = served;
        g_io_log_n++;
    }
    return served;
}

uint8_t  io_read8(uint32_t addr)  { return (uint8_t)io_read(addr, OS_HW_WRITE_WIDTH_8); }
uint16_t io_read16(uint32_t addr) { return (uint16_t)io_read(addr, OS_HW_WRITE_WIDTH_16); }
uint32_t io_read32(uint32_t addr) { return io_read(addr, OS_HW_WRITE_WIDTH_32); }

/* Apply a store to the declared map — the candidate's half of the WRITE-THROUGH arm, and the mirror
 * of shim.c's `io_note_written`. A marked byte LATCHES the store, so the next `io_read8` of it is
 * served what this core wrote; an unmarked or undeclared one is untouched here, which is what keeps
 * every case that declares no write-through byte byte-identical.
 *
 * The STALENESS column is the oracle's alone (os.h's os_io_store takes NULL for it here): that tally
 * feeds `harness._vet_io_reads_are_declared`, which reads the ORACLE's report, so a second copy on
 * this side would be state nothing consults. */
static void io_note_written(uint32_t addr, uint32_t width, uint32_t value) {
    os_io_store(g_io_addr, g_io_n, g_io_writeback, g_io_live, (uint8_t *)0, addr, width, value);
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

/* EVERY store this file makes goes through here, so that a write-through declaration cannot be
 * latched by one spelling of a store and not by another — the oracle sees one bus access whichever
 * C a reconstruction wrote. The Phase 10 ledger is unchanged and still second: `io_note_written`
 * decides what a later READ answers, `hw_log_write` records the store itself, and the shim's write
 * callbacks call its two counterparts in this order. */
static void hw_write(uint32_t addr, uint32_t width, uint32_t value) {
    io_note_written(addr, width, value);      /* Phase 15's write-through arm */
    hw_log_write(addr, width, value);         /* ...and Phase 10's ledger, exactly as it was */
}

void hw_write8(uint32_t addr, uint32_t value)  { hw_write(addr, OS_HW_WRITE_WIDTH_8, value); }
void hw_write16(uint32_t addr, uint32_t value) { hw_write(addr, OS_HW_WRITE_WIDTH_16, value); }
void hw_write32(uint32_t addr, uint32_t value) { hw_write(addr, OS_HW_WRITE_WIDTH_32, value); }

/* The three READ-MODIFY-WRITE operations, off target. ../include/hw.h has the whole contract; the
 * one line that matters here is that the read half these stand for is of an address the seeded READ
 * model does not name, and the ORACLE'S read of such an address answers a fabricated 0 — so the
 * byte the oracle's own `bset`/`bclr`/`andi.b` computes and ledgers is `0 | bit`, `0 & ~bit` and
 * `0 & mask`. These reproduce exactly that, which is why introducing them changed no ledger
 * comparison. A build for the real Atari does not compile this file and supplies each as the
 * genuine instruction on the register, where the read half is the byte the chip really holds.
 *
 * THEY ARE STILL NOT FOR A DECLARED ADDRESS, and the write-through arm does not change that: the
 * READ half is fabricated here and served from the map on the oracle, so a core that reached for one
 * of these on a declared register would store a byte the original did not and red on the Phase 10
 * ledger's VALUE. The store goes through `hw_write` all the same, so a declared byte cannot be
 * latched by one spelling of a store and missed by another. `include/hw.h` names the remedy: read
 * the register with `io_read8` and store the result. */
#define HW_RMW_FABRICATED_READ 0u   /* the byte the oracle serves for an unmodeled register */

void hw_bset8(uint32_t addr, uint32_t bit) {
    hw_write(addr, OS_HW_WRITE_WIDTH_8, HW_RMW_FABRICATED_READ | (1u << bit));
}

void hw_bclr8(uint32_t addr, uint32_t bit) {
    hw_write(addr, OS_HW_WRITE_WIDTH_8, HW_RMW_FABRICATED_READ & ~(1u << bit));
}

void hw_and8(uint32_t addr, uint32_t mask) {
    hw_write(addr, OS_HW_WRITE_WIDTH_8, HW_RMW_FABRICATED_READ & mask);
}
