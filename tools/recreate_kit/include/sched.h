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
 * EVERY POLL NAMES ITS WAIT SITE, and that is not bookkeeping — it is what makes the comparison
 * mean anything in a run with more than one wait. `site_pc` is the address of the instruction the
 * ORIGINAL's wait RE-READS THE POLLED BYTE at, which is the same address the case's schedule entry
 * names as its trigger. It is the READ and not just any instruction in the loop: the store lands
 * just before the site's instruction on both shores, so a site naming the compare below the read
 * would apply it one instruction too late; os.h's "WAIT SITES" has the arithmetic of what a run TOTAL loses (two waits can cancel,
 * and a port that deleted one of them passes). A poll naming a site the run did not declare is a
 * REFUSAL — it tallies through `os_refused()` and the harness throws the case away — because an
 * uncounted poll is exactly the hole the sites exist to close.
 *
 * WHAT IT IS NOT. It is not a general memory read: an ordinary field read stays a `bus_read_byte`.
 * Poll only the byte the wait is ON, and poll it exactly where the original's compare reads it —
 * a guard that reads the same address BEFORE the loop (Wonder Boy's `$638` tests the press code at
 * `$642` before spinning on the release at `$64e`) is not a poll and must not consume one.
 *
 * THE WIDTH: A BYTE POLL IS THE CLOCK, AND A WORD WAIT IS THAT CLOCK PLUS A WIDER READ. A wait whose
 * compare is a WORD is spelt with `sched_poll16` below: ONE `sched_poll8` per iteration ticks the
 * clock and applies the due store, and the word the caller compares is read at full width from the
 * same address. One poll per arrival, so none of the aliasing `test/test_sched_model.py` documents.
 * What a hand-rolled `sched_poll8`-plus-read loop would lose is the CAP, which is why the wrapper
 * exists at all. A word compare must NEVER be spelt as two byte polls: two polls per arrival is
 * precisely that aliasing mutant, invisible at any `nth` that is a multiple of the polling rate.
 *
 * ON TARGET this file IS EXCLUDED FROM THE BUILD, exactly like src/hw.c and src/psg.c: a build for
 * the real machine spins on the address itself, because the interrupt really does write it, and
 * supplies its own `sched_wait8`/`sched_poll16` that loop without a cap. Off target it must be
 * compiled — the harness refuses a case that declares a schedule against a candidate lacking these
 * symbols.
 */
#ifndef RECREATE_KIT_SCHED_H
#define RECREATE_KIT_SCHED_H

#include <stdint.h>

/* Read the byte at `addr` as ONE iteration of the busy-wait at `site_pc`: count the poll against
 * that site, apply any scheduled store this poll brings due, then read. The store lands BEFORE the
 * read, so a case whose entry says `nth = 1` has the very first poll see the new byte — the oracle's
 * first arrival at the compare sees it too.
 *
 * A poll of an address outside the image reads 0, the answer bus.h and the oracle's callbacks both
 * give; it is not a refusal, because the address is the reconstruction's own constant and a wait on
 * an unmapped byte would hang identically on both sides. A poll at an UNDECLARED SITE is a refusal —
 * see the header comment. */
uint8_t sched_poll8(uint8_t *image, uint32_t addr, uint32_t site_pc);

/* THE PRODUCTION SHAPE FOR A BYTE WAIT, and the one a reconstruction should reach for: poll `addr`
 * at `site_pc` until it reads `until`, and give up after `OS_SCHED_POLL_MAX` polls. Returns 1 when
 * the byte arrived, 0 when the cap was exhausted — and an exhausted wait tallies through
 * `os_refused()`, so `harness.differential` throws the case away with a name on it.
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
int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc);

/* ...AND THE WORD WAIT, as ONE CAPPED ITERATION rather than as a `sched_wait16(until)`.
 *
 * Ticks the wait's clock with a single `sched_poll8` at `site_pc`, then hands back the WORD at
 * `addr` through `seen` (big-endian, guarded like every other access on this side: an address
 * outside the image reads 0). Returns 1 while the caller should go round again and 0 once the site
 * has spent `OS_SCHED_POLL_MAX` polls — at which point it has already tallied the refusal, exactly
 * as `sched_wait8` does, so the caller's own `return` is all that is left to do.
 *
 * WHY AN ITERATOR AND NOT AN EQUALITY WAIT. `sched_wait8` can own its predicate because a byte wait
 * in this project spins until the byte EQUALS a release code. The two word waits that motivated this
 * (Wonder Boy's `flip_screen`, `$6aa` and `$6d0`) do not: one is a signed threshold and the other
 * compares against a copy the routine took an instruction earlier. An equality wrapper would fit
 * NEITHER, and a predicate enumeration would put the two callers' arithmetic inside the kit. So the
 * kit keeps the part that is game-agnostic — the poll, the store, the per-site count and the cap —
 * and the caller keeps its own compare:
 *
 *     uint16_t counter;
 *     while (sched_poll16(image, WB_VBL_COUNTER, FLIP_READY_WAIT_PC, &counter))
 *         if ((int16_t)counter >= WB_FLIP_VBL_READY)
 *             return 1;
 *     return 0;                     // the cap; sched_poll16 has already tallied the refusal
 */
int sched_poll16(uint8_t *image, uint32_t addr, uint32_t site_pc, uint16_t *seen);

/* ---- what the harness drives (see README.md, "What the candidate .so must export") ---- */
/* Install the run's schedule and clear the counters. `entries` is the flattened OS_SCHED_FIELDS-wide
 * array os.h describes and `sites` the wait-site PCs its triggers name, both IDENTICAL to the ones
 * the oracle was given, so the two cannot describe different stores or key their counts differently.
 * Entries past OS_SCHED_MAX and sites past OS_SCHED_SITE_MAX are dropped and reported by
 * g_sched_count()/g_sched_site_count(). The harness calls this before EVERY candidate run, an empty
 * schedule included, so one case's agent cannot fire inside the next. */
void     g_sched_reset(const uint32_t *entries, uint32_t n, const uint32_t *sites, uint32_t site_n);
uint32_t g_sched_count(void);    /* entries this run carries (what reset kept, not what it was given) */
uint32_t g_sched_polls(void);    /* POLLS this run, over every site — a sched_poll8 or a
                                  * sched_poll16, counted whether the site was declared or
                                  * not, so the two primitives tally one event one way */
uint32_t g_sched_applied(void);  /* stores actually made */
uint32_t g_sched_refused(void);  /* ...and entries whose store os_sched_store would not make */
uint32_t g_sched_exhausted(void); /* waits that hit OS_SCHED_POLL_MAX (each also tallies os_refused) */
uint32_t g_sched_site_count(void);       /* declared sites this run carries */
uint32_t g_sched_site_polls(uint32_t i); /* polls at the ith — compared against the oracle's arrivals */
uint32_t g_sched_undeclared(void);       /* polls naming no declared site (each tallies os_refused) */

#endif /* RECREATE_KIT_SCHED_H */
