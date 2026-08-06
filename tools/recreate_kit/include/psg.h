/* psg.h — the candidate side of the DIRECT YM2149 path ($ff8800 select / $ff8802 data).
 *
 * A reconstruction of a routine that drives the chip through those two ports calls these instead of
 * writing them: the ports live outside the memory image, so a wrong or missing register write is
 * invisible to the image diff, and the chip's prior contents — which every read-modify-write
 * preserves bits of — have no home in the image either. src/psg.c keeps both surfaces the oracle
 * keeps (an ordered write ledger and a register file), harness.differential() seeds them from the
 * case and compares them against the oracle's, and TRAP_MODEL.md ("Phase 6") is the contract.
 *
 * NOT the XBIOS Giaccess path. That one is os_giaccess() in os.h, reads and writes a register file
 * that lives IN the image, and is shared by both sides by construction. One chip, two modeled
 * files: a run that touches both is refused (shim.c's mixed-path guard), which is why these are
 * named for the ports rather than for the chip.
 *
 * Off-target only, exactly like src/dosound_log.c: a build for the real Atari writes the ports
 * itself and does not compile src/psg.c.
 */
#ifndef RECREATE_KIT_PSG_H
#define RECREATE_KIT_PSG_H

#include <stdint.h>

/* Write `value` to register `reg` (select, then data). Lands in BOTH the ledger and the file, so a
 * later read of the same register hands back what this wrote — as the chip does.
 *
 * `reg` is a register NUMBER, 0..OS_PSG_NREGS-1. A number outside that is a REFUSAL rather than a
 * masked-down write: the ST's select latch decodes four bits, so a driver that put anything in the
 * upper nibble meant something the chip does not do (the oracle refuses the same write from the
 * 68000 side, so masking here would leave the two sides disagreeing about the same instruction). */
void psg_port_write(unsigned reg, uint8_t value);

/* Read register `reg` back (select, then read $ff8800).
 *
 * Served only for a register whose contents are KNOWN: declared by the case's seed or written
 * earlier in the same run. A read of anything else is a REFUSAL — it tallies through os_refused()
 * and hands back 0, and harness.differential() throws the case away — because the value the chip
 * held on entry is an input of the run, and inventing it is how a reconstruction gets "verified"
 * against a bit pattern no machine ever holds. An out-of-range `reg` is refused as above. */
uint8_t psg_port_read(unsigned reg);

/* ---- what the harness drives (see README.md, "What the candidate .so must export") ---- */
void            g_psg_reset(const uint8_t *seed, uint32_t known);  /* clear the ledger, install the seed */
/* The ordered event stream: every psg_port_write AND every psg_port_read, in the order they
 * happened. The read entries are what catch a reconstruction that reads the WRONG register — its
 * writes, and the file they leave, can be identical to a correct one's. */
uint32_t        g_psg_log_count(void);      /* direct register accesses logged this run */
const uint8_t  *g_psg_log_kinds(void);      /* OS_PSG_EVENT_WRITE / OS_PSG_EVENT_READ per entry */
const uint8_t  *g_psg_log_regs(void);       /* ...their register numbers, in order */
const uint8_t  *g_psg_log_vals(void);       /* ...and the value written, or the value served back */
const uint8_t  *g_psg_file(void);           /* the register file the reads are served from */
uint32_t        g_psg_file_known(void);     /* bit R = register R's contents are known */

#endif /* RECREATE_KIT_PSG_H */
