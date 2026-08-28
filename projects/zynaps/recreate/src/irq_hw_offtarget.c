/* irq_hw_offtarget.c — the shifter and MFP stores src/irq.c's handlers make, OFF TARGET ONLY.
 *
 * A BUILD FOR THE REAL ATARI DOES NOT COMPILE THIS FILE. It writes the ports itself, from a sibling
 * that spells out the eight `move.l`s and the `bclr`. That is the shape the kit already uses for
 * the one hardware surface it does model — see `tools/recreate_kit/src/psg.c`'s header, "Off-target
 * only ... a build for the real Atari writes the ports itself and does not compile src/psg.c" — and
 * it is why these bodies are a file of their own rather than empty functions sitting in the middle
 * of `irq.c`. An empty body there would be indistinguishable from a routine somebody forgot to
 * finish, and `kit.mk`'s wildcard over `src/` would carry it into a target build unnoticed.
 *
 * WHY THEY ARE EMPTY HERE, rather than writing something. `$ff8240..$ff825c` (the shifter's sixteen
 * colour registers) and `$fffa0f` (the MFP's in-service register B) are outside the 1 MiB memory
 * image: `shim.c`'s memory callbacks DROP an off-image write on the oracle side, and a
 * reconstruction that computed `image + 0xff8240` would index past the end of the buffer. So the
 * two sides agree by doing the same nothing, and this half of every handler is UNPINNED — recorded
 * per row in STATUS.md.
 *
 * THE SURFACE THAT WOULD CATCH IT is a kit-level hardware-write ledger mirroring `psg.h`'s: one
 * write feeding an ordered ledger that `harness.differential` compares on both sides. The oracle
 * half already exists (`shim.c` decodes every off-image write through `hw_note_write`); what is
 * missing is the ledger and the candidate-side `hw_write*`, which `hw.h` deliberately does not
 * export today. On target, the surface is a Hatari register snapshot — docs/on-target-execution.md.
 *
 * Until one of those lands, this file is the single seam to bind, which is the other reason it is a
 * file: the arguments say WHICH pens and WHICH shadow at every call site, so a future ledger has
 * the whole contract already written down.
 */
#include "irq.h"

/* Upload `pens` colour words from the shadow at `shadow` to the shifter, starting at `first_pen`. */
void shifter_write_palette(const uint8_t *image, unsigned first_pen, unsigned pens,
                           uint32_t shadow) {
    (void)image;
    (void)first_pen;
    (void)pens;
    (void)shadow;
}

/* `clr.w $ff8240` — force pen 0 to black. */
void shifter_clear_pen0(void) {
}

/* `bclr #0,$fffa0f` — acknowledge Timer B in the MFP's in-service register B. Unlike the palette
 * this one has no shadow at all, so nothing about it is visible in the image even in principle. */
void mfp_ack_timer_b(void) {
}
