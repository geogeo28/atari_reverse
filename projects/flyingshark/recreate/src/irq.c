/* src/irq.c — Flying Shark's two interrupt handlers, and the TOS callback one of them displaced.
 *
 * `include/irq.h` argues the ENTRY MODEL these four cores are written against: the handlers are
 * entered by the 68000's exception sequence and leave through `rte`, each balancing its own pushes
 * first, so a reconstruction sliced at the `rte` never has to fabricate an exception frame.
 *
 * WHAT THE DIFFERENTIAL CANNOT SEE HERE, in one place rather than at each site:
 *   * `vbl_handler` ends `jmp $1164e.l`, whose operand `boot_init` fills from the OLD $70 vector.
 *     The TOS model has no vector there, so the slice ENDS at that `jmp` — chaining into TOS is a
 *     target-only surface and is a row in STATUS.md's "Unpinned on target".
 *   * every path clears MFP channel 6's in-service bit, which is off-image; `hw_bclr8` is what puts
 *     it in the ordered hardware WRITE ledger the harness compares, and spelling it as a plain
 *     store would be a defect the moment the code was cross-compiled (kit `include/hw.h`).
 *   * the byte the ACIA hands over is off-image too, and is a DECLARED input of every case
 *     (`hw_read8(OS_HW_ACIA_DATA)`, `hw_seed=`). The port is VOLATILE in the model — each read pops
 *     the receive register — which is exactly right here: every one of these three routines reads
 *     it once per entry.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "os.h"

#include "irq.h"       /* this subsystem's own: the vectors, the counter and the four input bytes */
#include "sound.h"    /* sound_vbl_tick, the module entry the VBL calls */

/* ================================================================================================
 * vbl_handler @ 0x11636 — SLICE [0x11636, 0x1164e).
 *
 * The level-4 handler, installed straight into vector $70 rather than into a `_vblqueue` slot. It
 * bumps the frame counter the frame pacer waits on and gives the loaded sound module its tick, and
 * then chains: `jmp $1164e.l` reads its own operand at 0x11650, which the image ships pointing at
 * the `jmp` itself and `boot_init` overwrites with TOS's old $70. The slice stops AT that `jmp`.
 * ============================================================================================= */
void vbl_handler(uint8_t *image) {
    /* `addq.l #1,$17720` — a full 32-bit increment, wrapping like the instruction. */
    wr32(image + A_vbl_tick, be32(image + A_vbl_tick) + 1u);
    /* `lea $58944,a0 / jsr 38(a0)` — SND_ENTRY_VBL_TICK into the module loaded off A\MODULE.BAK. */
    sound_vbl_tick(image);
}

/* ================================================================================================
 * acia_ikbd_isr @ 0x14218 and its two joystick continuations.
 *
 * The game OWNS the ACIA vector: TOS's own IKBD packet parser never runs, which is why
 * `tos_joyvec_handler` below is dead on the real machine. A joystick report arrives as a header
 * byte and then the stick's state, one interrupt each, so the handler re-points $118 at the
 * continuation that reads the second byte and the continuation puts $118 back — a two-state
 * machine held in the vector itself.
 * ============================================================================================= */

/* `bclr #6,$fffffa11` — the end-of-interrupt every one of the four `rte` paths performs. */
static void acia_end_of_interrupt(void) {
    hw_bclr8(MFP_ISRB, MFP_ISRB_ACIA_BIT);
}

/* The KEY path @ 0x14258: keep the raw byte, then set or clear one bit of `key_bits` per watched
 * scancode that matches.
 *
 * `bclr #7,d1` @ 0x1426a does two things in one instruction and both matter: it sets Z from the
 * ORIGINAL bit 7 — which is what picks the `bset` ladder over the `bclr` one — and it leaves the
 * MAKE code in d1, so the eight comparisons are against a scancode with the break bit stripped.
 *
 * ALL EIGHT COMPARISONS ALWAYS RUN. The ladder is unrolled with no early exit, so a scancode listed
 * twice would move two bits; the shipped table lists 0x00 twice (bit 3 and bit 7), which is why a
 * received 0x00 is not a no-op but sets or clears both of those bits at once.
 */
static void acia_key_byte(uint8_t *image, uint8_t received) {
    image[A_key_last_scancode] = received;               /* `move.b d1,(a0)+` @ 0x14268, RAW */

    uint8_t scancode = (uint8_t)(received & (uint8_t)~(1u << SCANCODE_BREAK_BIT));
    int pressed = (received & (1u << SCANCODE_BREAK_BIT)) == 0;

    for (unsigned bit = 0; bit < KEY_WATCH_SCANCODES; bit++) {
        if (image[A_key_watch_scancodes + bit] != scancode)
            continue;
        if (pressed)
            image[A_key_bits] |= (uint8_t)(1u << bit);    /* `bset d0,(a1)` @ 0x14274 and seven more */
        else
            image[A_key_bits] &= (uint8_t)~(1u << bit);   /* `bclr d0,(a1)` @ 0x142c2 and seven more */
    }
}

void acia_ikbd_isr(uint8_t *image) {
    uint8_t received = hw_read8(OS_HW_ACIA_DATA);        /* `move.b $fffffc02,d1` @ 0x1421a */

    if (received == IKBD_JOY0_PACKET_HEADER) {
        wr32(image + VECTOR_ACIA, FN_ACIA_JOY0_BYTE);
        acia_end_of_interrupt();
        return;
    }
    if (received == IKBD_JOY1_PACKET_HEADER) {
        wr32(image + VECTOR_ACIA, FN_ACIA_JOY1_BYTE);
        acia_end_of_interrupt();
        return;
    }
    acia_key_byte(image, received);
    acia_end_of_interrupt();       /* the key path clears the bit AFTER the ladder, @ 0x142b4/0x14302 */
}

/* The two continuations. They differ in ONE address — which state byte the received byte lands in —
 * and are written out rather than shared because that is one line each and the original is two
 * routines the vector names by address (`FN_ACIA_JOY0_BYTE`, `FN_ACIA_JOY1_BYTE`).
 */
static void acia_joystick_byte(uint8_t *image, uint32_t state) {
    image[state] = hw_read8(OS_HW_ACIA_DATA);
    acia_end_of_interrupt();
    wr32(image + VECTOR_ACIA, FN_ACIA_IKBD_ISR);   /* the store comes AFTER the bclr on both paths */
}

void acia_joy0_byte(uint8_t *image) { acia_joystick_byte(image, A_joy0_state); }
void acia_joy1_byte(uint8_t *image) { acia_joystick_byte(image, A_joy1_state); }

/* ================================================================================================
 * tos_joyvec_handler @ 0x141fa — DEAD ON THE MACHINE, and verifiable anyway.
 *
 * `boot_init` installs it in the KBDVBASE joyvec slot, where TOS's own IKBD parser would call it
 * with A0 on a three-byte joystick packet. Nothing ever does: `acia_ikbd_isr` has taken the ACIA
 * vector, so TOS's parser never sees a byte. It ends in `rts`, not `rte` — it is a callback, not a
 * handler — and its `lea $1777e(pc),a1` @ 0x141fe loads an address nothing then uses.
 * ============================================================================================= */
void tos_joyvec_handler(uint8_t *image, uint32_t packet) {
    image[A_joy0_state] = image[addr_add(packet, IKBD_JOY_PACKET_JOY0)];
    image[A_joy1_state] = image[addr_add(packet, IKBD_JOY_PACKET_JOY1)];
}

/* ================================================================================================
 * The glue. Each takes the original's registers; the comment maps register -> role.
 * ============================================================================================= */

/* No arguments: all three interrupt paths read their input from the ACIA, not from a register. */
void g_vbl_handler(uint8_t *image) { vbl_handler(image); }
void g_acia_ikbd_isr(uint8_t *image) { acia_ikbd_isr(image); }
void g_acia_joy0_byte(uint8_t *image) { acia_joy0_byte(image); }
void g_acia_joy1_byte(uint8_t *image) { acia_joy1_byte(image); }

/* A0 = TOS's three-byte joystick packet. */
void g_tos_joyvec_handler(uint8_t *image, uint32_t packet) { tos_joyvec_handler(image, packet); }
