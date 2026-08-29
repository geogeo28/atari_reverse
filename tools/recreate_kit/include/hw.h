/* hw.h — the candidate side of the SEEDED HARDWARE READ model (TRAP_MODEL.md, "Phase 7").
 *
 * A reconstruction of a routine that branches on a hardware byte calls hw_read8() instead of
 * inventing one. The addresses live outside the memory image, so a read of one is invisible to the
 * image diff — and worse than invisible: the byte STEERS A BRANCH, so a fabricated 0 makes both
 * sides take the same wrong path and the differential agrees with itself. That is the `$ffff820a`
 * defect BuggyBoy shipped, green all the way to real hardware.
 *
 * WHAT IS MODELED is a small named set, os.h's OS_HW_MFP_GPIP, OS_HW_SHIFTER_SYNC, the two
 * video-counter bytes OS_HW_SHIFTER_VCOUNT_MID/_LOW and the IKBD ACIA's two ports —
 * OS_HW_ACIA_STATUS and OS_HW_ACIA_DATA — and nothing
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
 * A WRITE is a SEPARATE MODEL with a wider address set — see hw_write8/16/32 at the bottom of this
 * header (TRAP_MODEL.md, "Phase 10"). The two do not feed each other: a store to a modeled READ
 * address does not change what a later read is served, it makes the seed STALE and the run refused,
 * because the seed describes the byte the chip held on ENTRY and after the run's own store it
 * describes nothing. The write is ledgered as well, and being comparable does not make it honest to
 * read the seed back.
 *
 * Off-target only, exactly like src/psg.c and src/dosound_log.c: a build for the real Atari reads
 * the address itself and does not compile src/hw.c.
 */
#ifndef RECREATE_KIT_HW_H
#define RECREATE_KIT_HW_H

#include <stdint.h>

/* Clear BOTH ledgers and install the run's declared bytes. The write ledger has no reset of its
 * own on purpose: a candidate run gets exactly one, so a path that resets the read stream cannot
 * leave the previous run's stores in place for this run's comparison. */
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
void            g_hw_reset(const uint8_t *seed, uint32_t known);  /* clear BOTH ledgers, install the seed */
/* The ordered READ stream — every hw_read8 of a modeled address, in the order it happened, refused
 * reads included. It is the whole comparison: these reads leave no trace in the image, so a
 * reconstruction that skipped one, added one, or read the WRONG modeled address is separable from a
 * correct one by nothing else. */
uint32_t        g_hw_log_count(void);   /* modeled-address reads logged this run */
const uint8_t  *g_hw_log_slots(void);   /* ...their os.h OS_HW_SLOT_* numbers, in order */
const uint8_t  *g_hw_log_vals(void);    /* ...and the byte each was served */
const uint8_t  *g_hw_file(void);        /* the declared bytes the reads are served from, by slot */
uint32_t        g_hw_file_known(void);  /* bit S = slot S's contents were declared */

/* ---- THE HARDWARE WRITE MODEL (TRAP_MODEL.md, "Phase 10") ------------------------------------
 *
 * A reconstruction of a routine that STORES to a hardware register — the shifter's colour row at
 * $ff8240, its screen base at $ff8201/$ff8203, the MFP's in-service registers, the IKBD ACIA's data
 * port — calls these instead of storing. The addresses are outside the memory image, so the oracle
 * DROPS such a store and a reconstruction that made NO store at all is byte-for-byte identical to
 * one that made every store the original makes. Both sides keep an ordered ledger of (address,
 * width, value) and harness.differential compares them exactly: a missing, extra, reordered,
 * mis-addressed, wrong-width or wrong-value store fails the case.
 *
 * `addr` MUST BE THE 24-BIT BUS FORM of a DECODED I/O register (os.h's three OS_HW_IO_* blocks),
 * and everything else is a REFUSAL rather than a ledger entry. Three shapes are rejected, for three
 * different reasons:
 *
 *   - an address the IMAGE covers — a reconstruction reaching image memory through this door has
 *     stored where the byte diff should have seen it;
 *   - an address above the image but outside the blocks ($570000, $ff9000) — that is a runaway
 *     pointer rather than a device, and the oracle drops it with no ledger entry, so an entry here
 *     would diverge the streams for a reason that is not about a device;
 *   - the UNTRANSLATED form, `$ffff8240` for `$ff8240` — hw_read8's contract, restated. The oracle
 *     folds an access the way the 68000's bus does before it decodes; a reconstruction spells the
 *     address itself, and masking here would let the two sides ledger two spellings of one register
 *     (and would defeat an address-keyed hw_waiver, which could then match one side only).
 *
 * A refusal tallies through os_refused() and harness.differential throws the case away — with the
 * refusal tally's generic message, which names no address, so this list is where a reader lands.
 *
 * `value` is masked to the width, so handing hw_write8 a longword records the byte the 68000 would
 * have stored rather than a value no store made.
 *
 * WHAT THE LEDGER PINS, AND WHAT IT DOES NOT. For a plain store it pins the whole of it. For a
 * READ-MODIFY-WRITE of an address the read model does not name — `bclr #0,$fffa0f`, `andi.b
 * #$fc,$ff8260`, which go through hw_bclr8/hw_and8 below — the oracle's read answers a fabricated
 * 0, so both sides compute their value from that same 0 and the ledger holds the address, the width
 * and the fact that the store happened while the BIT or the MASK the instruction applied stays
 * unpinned. That is a real gain (deleting the store is now a red) and an honest residual, and a
 * routine that needs the mask held wants a sink of its own or the address in the READ model.
 *
 * ON TARGET these three names are supplied by the build itself, exactly as psg.h's ports and
 * sched.h's poll are: an Atari build does not compile src/hw.c and defines each as the real store
 * OF ITS OWN WIDTH — `*(volatile uint8_t *)addr = value` for hw_write8, `uint16_t` for hw_write16,
 * `uint32_t` for hw_write32. The width is not decoration: a byte store widened to a word clobbers
 * the register next door (the MFP's timer-A data byte sits beside its in-service register B), and
 * the ledger compares the width a reconstruction DECLARED, not what a target build does with it.
 *
 * A READ-MODIFY-WRITE IS NOT A STORE, AND MUST NOT BE SPELT AS ONE — see hw_bset8/hw_bclr8/hw_and8
 * below, which are what a reconstruction of `bset`/`bclr`/`andi.b` on a register calls instead.
 */
void hw_write8(uint32_t addr, uint32_t value);
void hw_write16(uint32_t addr, uint32_t value);
void hw_write32(uint32_t addr, uint32_t value);

/* ---- THE READ-MODIFY-WRITE OPERATIONS: `bset` / `bclr` / `andi.b` on an I/O register -----------
 *
 * `bset #6,$fffa09`, `bclr #0,$fffa0f`, `andi.b #$fc,$ff8260` do not STORE a value — they store a
 * FUNCTION of the byte the register already held. The read half is of an address the seeded READ
 * model does not name, so off target it has no answer and the oracle serves a fabricated 0.
 *
 * A reconstruction that computed the value FROM THAT 0 and called hw_write8 passed the ledger — both
 * sides compute from the same 0 — and was a DEFECT the moment it was cross-compiled, because the
 * target has no fabricated 0 and the store lands for real: `bset` becomes "write 0x40 and clear
 * every other bit TOS set in the MFP's IERB", `bclr` becomes "acknowledge every in-service channel
 * at once", `andi.b #$fc` becomes "write 0 to the resolution register". Green off target, wrong on
 * the machine, and invisible to every surface the differential has.
 *
 * These three names close that by SPELLING THE OPERATION rather than its off-target value. The
 * reconstruction says WHICH bit it sets, WHICH it clears, WHICH mask it applies; each shore then
 * supplies the read half it actually has:
 *
 *   OFF TARGET (src/hw.c) each ledgers the byte the ORACLE'S OWN read-modify-write produces from
 *   its fabricated 0 — `0 | bit`, `0 & ~bit`, `0 & mask` — which is exactly what shim.c logs for
 *   the same instruction, so the ledger comparison is unchanged and every existing case stays
 *   green. What the ledger holds is unchanged too: the address, the byte width, the fact of the
 *   store, and a value that both sides derive from the same 0. The BIT and the MASK remain
 *   unpinned by it — a routine that needs them held wants a sink of its own, or the address in the
 *   READ model.
 *
 *   ON TARGET the build supplies each as the REAL instruction on the real register —
 *   `*(volatile uint8_t *)addr |= 1u << bit`, `&= ~(1u << bit)`, `&= mask` — exactly as it supplies
 *   psg.h's ports, sched.h's poll and hw_write8/16/32 above. It does not compile src/hw.c, so there
 *   is no fabricated 0 anywhere in the chain and the five bits the original preserves are preserved.
 *
 * `hw_and8` IS ITS OWN OPERATION AND NOT TWO hw_bclr8 CALLS. `andi.b #$fc` clears two bits with ONE
 * store, and the ledger compares the ordered store STREAM: two calls would log two entries where
 * the oracle logs one, so the case would fail for a reason that is not about the register. One
 * instruction, one call, one entry.
 *
 * Width is BYTE for all three, because that is the width of every RMW instruction they stand for
 * (`bset`/`bclr` on memory are byte operations on the 68000, and `andi.b` says so). A wider RMW
 * wants a name of its own rather than one of these; none of the games in this workspace has one.
 *
 * The address rules are hw_write8's, unchanged and enforced through the same check: the 24-bit bus
 * form of a decoded I/O register, and everything else — an image address, an address above the
 * image but outside the blocks, the untranslated `$ffff8240` form — is a REFUSAL rather than a
 * ledger entry.
 */
void hw_bset8(uint32_t addr, uint32_t bit);    /* `bset #bit,addr`  — set bit `bit` (0..7) */
void hw_bclr8(uint32_t addr, uint32_t bit);    /* `bclr #bit,addr`  — clear it */
void hw_and8(uint32_t addr, uint32_t mask);    /* `andi.b #mask,addr` — keep the bits `mask` names */

/* ---- what the harness drives for the write model (see README.md); g_hw_reset clears it ---- */
uint32_t        g_hw_write_count(void);      /* stores logged this run */
const uint32_t *g_hw_write_addrs(void);      /* ...their 24-bit addresses, in order */
const uint8_t  *g_hw_write_widths(void);     /* ...each store's width in bytes (1, 2 or 4) */
const uint32_t *g_hw_write_vals(void);       /* ...and the value stored, masked to that width */

#endif /* RECREATE_KIT_HW_H */
