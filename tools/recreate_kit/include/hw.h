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

/* ---- THE DECLARED I/O MAP: reading a byte the CASE declared by address (Phase 15) --------------
 *
 * `hw_read8` above serves the NAMED SET, one os.h slot at a time, because a game touches few
 * registers. An OPERATING SYSTEM touches the whole machine — the shifter's resolution byte, the
 * video base, the palette, the MFP's interrupt registers — and a slot apiece is the wrong shape for
 * it. A reconstruction of such a routine reads through these instead, and the case declares what
 * the machine held with `differential(..., io_seed={0xff8260: 0x02})`.
 *
 * `addr` is the 24-BIT BUS FORM, exactly as for hw_read8/hw_write8, and everything the case did not
 * declare — an address in no declaration, one below the I/O page, one the os.h models own — is a
 * REFUSAL rather than a zero. It tallies through `os_refused()`, so `harness.differential`'s
 * unconditional `_vet_no_os_refusal` throws the case away; the oracle's side of the same read is
 * counted as an unmodeled I/O read and refused by `harness._vet_rom_io_reads_are_modelled`, so the
 * fabrication is closed on BOTH shores.
 *
 * A WIDE READ IS N DECLARED BYTES, not a width of its own: `io_read16(0xff8240)` is served only
 * when the case declared `0xff8240` AND `0xff8241`, and `io_read32` only when all four were
 * declared. TRAP_MODEL.md, "Phase 15" ("a 16- or 32-bit read") carries that argument in full; the
 * one line of it that matters at the call site is that a half-declared access refuses WHOLE, and
 * names the byte that is missing rather than the access that straddled it.
 *
 * Both are LEDGERED, address and width and value, and `harness` compares the stream against the
 * oracle's. That is the whole comparison for a read whose result the routine discards — clearing a
 * status flag by reading it, which is most of what an MFP or ACIA handler does with one — since
 * such a read touches no image byte and leaves no register behind.
 *
 * A WRITE-THROUGH DECLARATION IS WHAT LETS A CORE READ BACK WHAT IT JUST STORED. A case may mark an
 * address (`emu.write_through(byte)` in its `io_seed`), and a `hw_write8` to it then REPLACES what
 * the next `io_read8` of it is served — which is how `write the timer's data register and re-read
 * it until the chip agrees` becomes an ordinary differential rather than a refusal. It is the CASE's
 * claim about the register, true of a latch and false of a write-to-clear or a live counter;
 * TRAP_MODEL.md, "Phase 15" ("The write-through arm") says which is which and why.
 *
 * ON TARGET the build supplies all three as the real volatile access, exactly as it supplies psg.h's
 * ports and hw_write8/16/32: `*(volatile uint8_t *)addr`, `*(volatile uint16_t *)addr` and
 * `*(volatile uint32_t *)addr`. It does not compile src/hw.c, so there is no map and no declaration
 * in the chain — the machine answers, which is the behaviour a write-through claim is claiming.
 */
uint8_t  io_read8(uint32_t addr);
uint16_t io_read16(uint32_t addr);
uint32_t io_read32(uint32_t addr);

/* ---- POLLING one of those addresses: the read, plus whether the model could still answer it -----
 *
 * `hw_poll8` reads a NAMED SLOT and `io_poll8` a declared I/O byte, each exactly as its `read`
 * neighbour above does — same ledger entry, same sequence cursor, same refusal — and each hands the
 * byte back through `seen` and returns whether THAT read was SERVED: 1 to go round again, 0 for a
 * read the model refused. `sched.h`'s `sched_poll16`/`sched_poll32` have the same iterator contract
 * and exist for the same reason.
 *
 * THEY EXIST BECAUSE A REFUSAL HANDS THIS SHORE 0, AND 0 IS "STILL BUSY" TO MOST POLL LOOPS. A core
 * that spins on a status bit until it clears, or on the MFP's GPIP until a line goes idle, reads a
 * refused byte as "not yet" and spins for ever — so an under-declared case would HANG the pytest
 * worker while the oracle came back with its own refusal, and a hung suite decides nothing. The
 * loop's own condition is what ends it:
 *
 *     uint8_t status;
 *     while (io_poll8(FDC_STATUS, &status) && !(status & FDC_BUSY))
 *         ;                          // the model refused, or the bit cleared; the case is already void
 *
 * A CAP WOULD BE THE WRONG SHAPE for it. A bound ("stop after N reads") is a number nothing derives
 * and a behaviour the target build does not have; this is the model's own answer, asked once per
 * read, so the loop ends exactly when the case's declaration runs out and the differential reports
 * the refusal rather than the timeout.
 *
 * ON TARGET the build supplies each as the plain volatile read of its width, returning 1 — there is
 * no model to refuse, so the loop is the machine's own, exactly as it is for `hw_read8` above.
 */
int hw_poll8(uint32_t addr, uint8_t *seen);
int io_poll8(uint32_t addr, uint8_t *seen);

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

/* ...and the DECLARED I/O MAP's (Phase 15). `g_io_reset` installs the case's map and clears the
 * ledger, exactly as `g_hw_reset` does for the named set; it is a SEPARATE reset because the two
 * models are separate declarations, and the harness calls both before every candidate run.
 * `writeback` is the parallel WRITE-THROUGH column — os.h's OS_IO_DECLARED_CONSTANT or
 * OS_IO_WRITE_THROUGH per address, deciding whether a store to it LATCHES. */
void            g_io_reset(const uint32_t *addrs, const uint8_t *values, const uint8_t *writeback,
                           uint32_t n);
uint32_t        g_io_seed_count(void);  /* entries os.h's rule accepted — compared to the oracle's */
uint32_t        g_io_writeback_count(void);  /* ...of which this many were marked WRITE-THROUGH */
uint32_t        g_io_log_count(void);   /* served reads logged this run */
const uint32_t *g_io_log_addrs(void);   /* ...their 24-bit addresses, in order */
const uint8_t  *g_io_log_widths(void);  /* ...each read's width in bytes (1, 2 or 4) */
const uint32_t *g_io_log_vals(void);    /* ...and the value it was served */

/* ...and the DECLARED SEQUENCE's (TRAP_MODEL.md, "Phase 16"). A case declares a LIST for an address
 * and the Nth read of it is served the Nth byte — which is what makes a routine that drains a packet
 * out of one port, or loops until a status line changes, runnable at all. ONE table covers both
 * models' addresses, so a Phase-7 named slot's list is installed here too and `hw_read8` serves it;
 * which LEDGER the read lands in is still the owning model's.
 *
 * The wire form is a flat byte POOL plus one (address, offset, length) row per sequence, because a
 * C ABI has no ragged arrays; `os_io_seq_install` is the shared rule that decodes it. A read PAST
 * THE END of a declared list is a refusal on both shores — never a sticky last byte, never a 0.
 *
 * `g_io_seq_spent` is the NEWEST name in `harness._HW_LEDGER_ABI` and is what dates a build: a .so
 * predating it exports every other name there, so without a new one the probe would pass and the
 * harness would then drive a candidate whose over-read it could only report as a bare refusal
 * count. (`g_io_seq_reset` held that place for the table itself and is still probed.) */
void            g_io_seq_reset(const uint32_t *addrs, const uint32_t *offsets,
                               const uint32_t *lengths, const uint8_t *pool,
                               uint32_t n, uint32_t pool_len);
uint32_t        g_io_seq_count(void);   /* rows os.h's rule accepted — compared to the oracle's */
/* ...and this run's reads PAST THE END of one, the candidate's symmetric surface to the oracle's
 * `osh_io_seq_spent{,_addr,_index}`. Such a read charges the same shared `os_refused()` every other
 * candidate refusal does, so without these the harness could only report "the candidate refused N
 * calls" and send the reader to hunt for a missing Bconstat gate; with them `harness.refusal_hints`
 * names the ADDRESS and the READ INDEX as a fact rather than as a guess. Cleared by
 * `g_io_seq_reset`, so they describe this run alone. */
uint32_t        g_io_seq_spent(void);        /* reads past the end of a declared list, this run */
uint32_t        g_io_seq_spent_addr(void);   /* ...the address of the FIRST of them */
uint32_t        g_io_seq_spent_index(void);  /* ...and which read of it ran off the end */

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
