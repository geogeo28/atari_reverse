/* hw.h — the candidate side of the SEEDED HARDWARE READ model (TRAP_MODEL.md, "Phase 7").
 *
 * A reconstruction of a routine that branches on a hardware byte calls hw_read8() instead of
 * inventing one. The addresses live outside the memory image, so a read of one is invisible to the
 * image diff — and worse than invisible: the byte STEERS A BRANCH, so a fabricated 0 makes both
 * sides take the same wrong path and the differential agrees with itself. That is the `$ffff820a`
 * defect BuggyBoy shipped, green all the way to real hardware.
 *
 * WHAT IS MODELED is a small named set, os.h's OS_HW_MFP_GPIP, OS_HW_SHIFTER_SYNC and the two
 * video-counter bytes OS_HW_SHIFTER_VCOUNT_MID/_LOW, and nothing
 * else. An address outside it is a REFUSAL, not a zero: the point of the model is that the byte is a
 * DECLARED input of the case, and quietly answering for an address nobody declared would be the
 * fabrication over again under a new name. (Adding one is a change to os.h's table, on both sides at
 * once, and it belongs with the evidence for what the address really answers.)
 *
 * The addresses are the 24-BIT bus forms — pass os.h's constants. The 68000 aliases $fffffa01 onto
 * $fffa01 and the oracle masks an access before it decodes it; this side does not mask, because a
 * reconstruction spells the address itself and the untranslated form is a mistake worth a refusal
 * rather than a silent equivalence.
 *
 * WHAT IS NOT MODELED, and deliberately: a WRITE to one of these addresses. The oracle drops such a
 * write exactly as it drops every other hardware write, so there is nothing for a reconstruction to
 * mirror and no hw_write8() here. Storing to the shifter's sync register on target is an ordinary
 * `*(volatile uint8_t *)0xffff820a = 2` in an on-target build. What the harness does refuse is a run
 * that WROTE a modeled address and then READ it back: the seed describes the byte the chip held on
 * ENTRY, and after the run's own store it describes nothing.
 *
 * Off-target only, exactly like src/psg.c and src/dosound_log.c: a build for the real Atari reads
 * the address itself and does not compile src/hw.c.
 */
#ifndef RECREATE_KIT_HW_H
#define RECREATE_KIT_HW_H

#include <stdint.h>

/* Read the modeled hardware byte at `addr` (an os.h OS_HW_* constant).
 *
 * Served only for an address whose contents this run's case DECLARED, through
 * harness.differential(..., hw_seed={addr: byte}). An undeclared one is a REFUSAL — it tallies
 * through os_refused() and hands back 0, and the harness throws the case away — for psg_port_read's
 * reason: the byte the machine holds is an input of the run, and inventing it is how a
 * reconstruction gets "verified" against a machine that does not exist. An address outside the
 * modeled set is refused too, and is not ledgered: the oracle does not model it either, so there is
 * nothing it could be compared against. */
uint8_t hw_read8(uint32_t addr);

/* ---- what the harness drives (see README.md, "What the candidate .so must export") ---- */
void            g_hw_reset(const uint8_t *seed, uint32_t known);  /* clear the ledger, install the seed */
/* The ordered READ stream — every hw_read8 of a modeled address, in the order it happened, refused
 * reads included. It is the whole comparison: these reads leave no trace in the image, so a
 * reconstruction that skipped one, added one, or read the WRONG modeled address is separable from a
 * correct one by nothing else. */
uint32_t        g_hw_log_count(void);   /* modeled-address reads logged this run */
const uint8_t  *g_hw_log_slots(void);   /* ...their os.h OS_HW_SLOT_* numbers, in order */
const uint8_t  *g_hw_log_vals(void);    /* ...and the byte each was served */
const uint8_t  *g_hw_file(void);        /* the declared bytes the reads are served from, by slot */
uint32_t        g_hw_file_known(void);  /* bit S = slot S's contents were declared */

#endif /* RECREATE_KIT_HW_H */
