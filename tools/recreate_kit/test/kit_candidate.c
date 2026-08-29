/* kit_candidate.c — the reconstruction side of test_psg_differential.py's miniature project.
 *
 * The kit binds no game, so it has no candidate .so and therefore no way to exercise
 * harness.differential() itself — the code that COMPARES the two sides of the PSG model. This is the
 * smallest thing that fixes that: three glue functions over ../include/psg.h, built into a .so with
 * the rest of $(KIT)/src, and bound as a one-function "project" whose .PRG holds the same
 * read-modify-write in 68000 code. What it pins is the harness plumbing, not the model — the model's
 * own pins are psg_model_probe.c next door, which drives both implementations directly.
 *
 * Every function takes the image pointer, because that is the shape harness's `glue(lib, buf)` hands
 * a candidate. None of them touches it: the whole point is that this routine's effect is entirely
 * off-image, so the byte diff sees nothing and only the ledger comparison can judge it.
 */
#include <stdint.h>

#include "hw.h"
#include "os.h"
#include "psg.h"

/* The mixer's two top bits are the PSG's port A/B I/O DIRECTION lines, which `ori.b #$3f` leaves
 * alone — so they are exactly what the read-back exists to preserve, and what a fabricated 0 would
 * destroy. Same routine as the .PRG's, instruction for instruction. */
#define MIXER_REG    7
#define SILENCE_MASK 0x3f

/* The faithful reconstruction: read the mixer, merge the silence mask, write it back. */
void g_psg_rmw(uint8_t *image) {
    (void)image;
    uint8_t mixer = psg_port_read(MIXER_REG);
    psg_port_write(MIXER_REG, (uint8_t)(mixer | SILENCE_MASK));
}

/* MUTANT: reads the mixer and never writes it back. It touches no image byte — neither does the
 * correct one — so the differential's byte diff is blind to it and only _vet_psg_state can red. */
void g_psg_rmw_skips_the_write(uint8_t *image) {
    (void)image;
    psg_port_read(MIXER_REG);
}

/* A candidate that does not reach the chip at all, for the cases about what happens when the ORACLE
 * uses the path and the candidate cannot answer for it. */
void g_psg_untouched(uint8_t *image) {
    (void)image;
}

/* ---- the Phase 7 side: the tempo selector's two hardware reads (see test_hw_differential.py) ----
 * Same shape as the PSG glue above and for the same reason: the routine's whole effect is off-image,
 * so the byte diff sees nothing and only the ordered read stream can judge it. */

/* The faithful reconstruction of the .PRG's read of the tempo pair, in the order it makes them. */
void g_hw_reads_the_pair(uint8_t *image) {
    (void)image;
    hw_read8(OS_HW_MFP_GPIP);
    hw_read8(OS_HW_SHIFTER_SYNC);
}

/* MUTANT: the same two reads in the OTHER order. Given a case that declares both addresses to the
 * same byte, every surface a differential has agrees with a correct run — the values, the declared
 * file, the untouched image — and the ordered stream is the only thing left. */
void g_hw_reads_the_pair_backwards(uint8_t *image) {
    (void)image;
    hw_read8(OS_HW_SHIFTER_SYNC);
    hw_read8(OS_HW_MFP_GPIP);
}

/* Reads the sync byte alone — the counterpart of the .PRG routine a case uses to show that
 * declaring an address the run never reads is ORDINARY rather than an error. */
void g_hw_reads_the_sync(uint8_t *image) {
    (void)image;
    hw_read8(OS_HW_SHIFTER_SYNC);
}

/* Reads the VOLATILE counter byte twice, faithfully — which is the point: this candidate matches the
 * .PRG entry for entry, so with the harness's volatile refusal removed the differential comes back
 * GREEN about a counter that never moved. That false green is what the refusal exists to close, and
 * a candidate that read the byte only once would red for the wrong reason. */
void g_hw_reads_the_vcount_twice(uint8_t *image) {
    (void)image;
    hw_read8(OS_HW_SHIFTER_VCOUNT_LOW);
    hw_read8(OS_HW_SHIFTER_VCOUNT_LOW);
}

/* Reads the STATIC GPIP byte twice, which is a correct run rather than a mutant: the machine really
 * does answer the same byte every time, so one declaration describes both reads. */
void g_hw_reads_the_gpip_twice(uint8_t *image) {
    (void)image;
    hw_read8(OS_HW_MFP_GPIP);
    hw_read8(OS_HW_MFP_GPIP);
}

/* A candidate that reads no hardware at all: for the ABI case, and for the mutant that hardcodes
 * what it should have read. */
void g_hw_untouched(uint8_t *image) {
    (void)image;
}

/* ---- the Phase 10 side: stores to memory-mapped I/O registers (test_hw_write_differential.py) ----
 * Same shape as the two groups above and for the same reason: the oracle DROPS a store to one of
 * these addresses, so the byte diff is blind to every mutant below and only the ordered write
 * stream can judge them. The constants are the smoke .PRG's own — kit_smoke_project.py plants the
 * same three stores as 68000 code — and a drift between the two is what
 * test_the_smoke_prg_stores_to_the_addresses_the_candidate_does pins. */
#define SHIFTER_PEN0      0xff8240u
#define SHIFTER_PEN1      0xff8244u
#define PEN0_COLOUR       0x0777u
#define PEN_PAIR_COLOURS  0x01230456u
#define IKBD_COMMAND      0x16u
/* The ACIA's data port is os.h's, not a fourth literal: this file already reaches it by that name in
 * g_hw_acia_send below, and two spellings of one address in one translation unit is a reader asking
 * whether the difference is meaningful. The shifter pens above stay local — they are the smoke
 * .PRG's own operands, and test_the_smoke_prg_stores_to_the_addresses_the_candidate_does is what
 * pins them equal to it. */
#define ACIA_DATA         OS_HW_ACIA_DATA

/* The faithful reconstruction: a word, a longword and a byte, to three registers, in that order. */
void g_hw_writes_the_three(uint8_t *image) {
    (void)image;
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write32(SHIFTER_PEN1, PEN_PAIR_COLOURS);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: the palette longword is never stored — a port that dropped one instruction. */
void g_hw_writes_one_short(uint8_t *image) {
    (void)image;
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: an EXTRA store the original never makes, at an address it does touch — so the run's set
 * of addresses is unchanged and only the stream's length and order separate it. */
void g_hw_writes_one_extra(uint8_t *image) {
    (void)image;
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write32(SHIFTER_PEN1, PEN_PAIR_COLOURS);
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: the same three stores, reordered. Every address, width and value is a correct run's — the
 * ORDER is the only thing left, which is why the ledger is a stream and not a set. */
void g_hw_writes_reordered(uint8_t *image) {
    (void)image;
    hw_write32(SHIFTER_PEN1, PEN_PAIR_COLOURS);
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: the right value at the right address, stored a LONGWORD wide instead of a word. On the
 * machine that overwrites the neighbouring colour register; off it, only the ledger's width field
 * can tell the two apart. */
void g_hw_writes_the_wrong_width(uint8_t *image) {
    (void)image;
    hw_write32(SHIFTER_PEN0, PEN0_COLOUR);
    hw_write32(SHIFTER_PEN1, PEN_PAIR_COLOURS);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: one bit wrong in the colour — the shape a transcription slip has. */
void g_hw_writes_the_wrong_value(uint8_t *image) {
    (void)image;
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR ^ 1u);
    hw_write32(SHIFTER_PEN1, PEN_PAIR_COLOURS);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* MUTANT: the palette longword is not stored AND the colour word is wrong — the two halves of the
 * waiver cases. Waiving the longword's address leaves the wrong colour to be caught, which is what
 * says a waiver covers the address it names and not the run. */
void g_hw_writes_one_short_and_the_wrong_colour(uint8_t *image) {
    (void)image;
    hw_write16(SHIFTER_PEN0, PEN0_COLOUR ^ 1u);
    hw_write8(ACIA_DATA, IKBD_COMMAND);
}

/* A candidate that stores nothing at all: for the ABI case, and for the waiver cases. */
void g_hw_writes_nothing(uint8_t *image) {
    (void)image;
}

/* MUTANT: a store aimed at an address that is not a DECODED I/O register, which the write model
 * refuses rather than ledgers (hw.h lists the three shapes it rejects and why). This one is inside
 * the image — the modeled Physbase/Logbase region, so it is image on every project here — which is
 * the shape a reconstruction storing where the byte diff should have seen it has. */
void g_hw_writes_into_the_image(uint8_t *image) {
    (void)image;
    hw_write16(OS_SCREEN_BASE, PEN0_COLOUR);
}

/* ...and the OTHER refusal a reader is likely to meet: the untranslated 68000 form of a register
 * this model does name. It is refused rather than masked so that the two sides cannot ledger two
 * spellings of one address — os.h's os_hw_is_io has the argument. */
void g_hw_writes_the_untranslated_form(uint8_t *image) {
    (void)image;
    hw_write16(0xffff8240u, PEN0_COLOUR);
}

/* The IKBD send loop, `ikbd_send_cmd`'s own shape: poll the ACIA status until its transmit register
 * is empty, then store the command byte. It terminates on its FIRST poll because the status slot
 * carries a MODEL DEFAULT with TDRE set (os.h's os_hw_model_defaults) — a case that declares the bit
 * clear would spin here as the .PRG spins, which is the model's non-goal rather than a test. */
void g_hw_acia_send(uint8_t *image) {
    (void)image;
    while (!(hw_read8(OS_HW_ACIA_STATUS) & OS_ACIA_TX_RDY))
        ;
    hw_write8(OS_HW_ACIA_DATA, IKBD_COMMAND);
}
