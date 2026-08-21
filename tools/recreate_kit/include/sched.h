/* sched.h — the candidate side of the SCHEDULED WRITE model (os.h, "Phase 8"; TRAP_MODEL.md).
 *
 * A reconstruction of a routine that BUSY-WAITS on a memory byte reads that byte through
 * `sched_poll8` instead of straight out of the image. Nothing else in an off-target differential can
 * change memory while the candidate is running, so a plain `while (image[addr] != want) ;` never
 * ends — and the loop is not a defect to be ported around: the original really does spin, and the
 * byte really is written by something outside the routine (an ACIA interrupt storing a release
 * scancode, the VBL bumping a frame counter).
 *
 * WHAT THE POLL IS FOR, precisely. It is the candidate's clock. The oracle counts ARRIVALS at the
 * original's compare instruction and fires the case's declared store before the Nth of them
 * (oracle/shim.c); this side counts POLLS and fires the same store before the Nth of those. A
 * reconstruction whose loop polls once per iteration therefore sees the byte change at the same
 * iteration the original does — and `harness.differential` compares the two counts, so a port that
 * polls a different number of times fails rather than quietly agreeing.
 *
 * WHAT IT IS NOT. It is not a general memory read: an ordinary field read stays a `bus_read_byte`.
 * Poll only the byte the wait is ON, and poll it exactly where the original's compare reads it —
 * a guard that reads the same address BEFORE the loop (Wonder Boy's `$638` tests the press code at
 * `$642` before spinning on the release at `$64e`) is not a poll and must not consume one.
 *
 * THE WIDTH CONTRACT: A POLL IS A BYTE. The model carries one byte per poll and nothing wider. A
 * wait whose compare is a WORD needs a `sched_poll16` ADDED to the model — on both shores, with the
 * oracle counting one arrival for that compare — and must NEVER be spelt as two byte polls: two
 * polls per arrival is precisely the aliasing mutant `test/test_sched_model.py` documents, which is
 * invisible at any `nth` that is a multiple of the polling rate. Wonder Boy's two waits are both
 * `cmpi.b`, so nothing needs it yet.
 *
 * ON TARGET this file IS EXCLUDED FROM THE BUILD, exactly like src/hw.c and src/psg.c: a build for
 * the real machine spins on the address itself, because the interrupt really does write it, and
 * supplies its own `sched_wait8` that loops without a cap. Off target it must be compiled — the
 * harness refuses a case that declares a schedule against a candidate lacking these symbols.
 */
#ifndef RECREATE_KIT_SCHED_H
#define RECREATE_KIT_SCHED_H

#include <stdint.h>

/* Read the byte at `addr` as ONE iteration of a busy-wait: apply any scheduled store that this poll
 * brings due, then read. The store lands BEFORE the read, so a case whose entry says `nth = 1` has
 * the very first poll see the new byte — the oracle's first arrival at the compare sees it too.
 *
 * A poll of an address outside the image reads 0, the answer bus.h and the oracle's callbacks both
 * give; it is not a refusal, because the address is the reconstruction's own constant and a wait on
 * an unmapped byte would hang identically on both sides. */
uint8_t sched_poll8(uint8_t *image, uint32_t addr);

/* THE PRODUCTION SHAPE, and the one a reconstruction should reach for: poll `addr` until it reads
 * `until`, and give up after `OS_SCHED_POLL_MAX` polls. Returns 1 when the byte arrived, 0 when the
 * cap was exhausted — and an exhausted wait tallies through `os_refused()`, so `harness.differential`
 * throws the case away with a name on it.
 *
 * WHY A CAP AT ALL, when the original has none: a wait the case's schedule never releases is an
 * INFINITE LOOP in the candidate, and a hung suite is worse evidence than a red one — it decides
 * nothing, and it looks identical to a broken machine. With the cap, a port that waits for the wrong
 * byte, or a guard removed above the wait, fails as an ordinary refused case. Six mutants in this
 * model's first sweep could only hang; five of them are caught by this.
 *
 * A CALLER MUST HONOUR THE 0. The routine's own behaviour past a refused wait is undefined — the
 * case is already void — so the shortest correct thing is to return, which is what
 * projects/wonderboy/recreate/src/game.c does. Do not carry on as though the byte had arrived. */
int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until);

/* ---- what the harness drives (see README.md, "What the candidate .so must export") ---- */
/* Install the run's schedule and clear the counters. `entries` is the flattened OS_SCHED_FIELDS-wide
 * array os.h describes, IDENTICAL to the one the oracle was given, so the two cannot describe
 * different stores. Entries past OS_SCHED_MAX are dropped and reported by g_sched_count().
 * The harness calls this before EVERY candidate run, an empty schedule included, so one case's
 * agent cannot fire inside the next. */
void     g_sched_reset(const uint32_t *entries, uint32_t n);
uint32_t g_sched_count(void);    /* entries this run carries (what reset kept, not what it was given) */
uint32_t g_sched_polls(void);    /* sched_poll8 calls this run — compared against the oracle's arrivals */
uint32_t g_sched_applied(void);  /* stores actually made */
uint32_t g_sched_refused(void);  /* ...and entries whose store os_sched_store would not make */
uint32_t g_sched_exhausted(void); /* waits that hit OS_SCHED_POLL_MAX (each also tallies os_refused) */

#endif /* RECREATE_KIT_SCHED_H */
