/* input.h — the on-screen keyboard's hit test in src/input.c. Subsystem: input.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * The other routine here, `ikbd_send_cmd` @ 0x14444, was this project's oldest KIT wall: it
 * busy-waits on the IKBD ACIA status at $fffc00 and then writes $fffc02, and the harness could
 * model neither. Both halves exist now — the status byte is a SEEDED READ slot (`OS_HW_ACIA_STATUS`)
 * and the command byte goes through the hardware WRITE ledger (`hw_write8`), kit TRAP_MODEL.md
 * Phases 7 and 10 — so the routine is reconstructed and verified below.
 */
#ifndef ZYNAPS_INPUT_H
#define ZYNAPS_INPUT_H

#include <stdint.h>

/* ================================================================================================
 * The globals this subsystem owns.
 * ============================================================================================= */
/* Where the name-entry screen's gunsight cursor sits, in playfield pixels. */
#define A_osk_cursor_x 0x19d44u
#define A_osk_cursor_y 0x19d46u

/* One byte per screen column of the on-screen keyboard, three rows of them, sitting as PC-relative
 * data inside the text segment. Ten keys per row at a three-column stride, and the two bytes
 * between neighbouring keys are 0 — so the cursor only picks a key when it is on the key's own
 * column. Read off the image: the rows spell A..J, K..T and U..Z plus space, Delete, Esc, Return
 * (scancodes 0x1e/0x30/0x2e/0x20/0x12/0x21/0x22/0x23/0x17/0x24, then 0x25..0x14, then
 * 0x16/0x2f/0x11/0x2d/0x15/0x2c/0x39/0x53/0x01/0x1c). */
#define A_osk_row_top 0x132e2u
#define A_osk_row_middle 0x132feu
#define A_osk_row_bottom 0x1331au

/* ================================================================================================
 * The grid, in the coordinates the routine works in.
 * ============================================================================================= */
/* Both cursor coordinates are first biased by the grid's own origin (`sub.w #$38` / `sub.w #$20`).
 * The x bias is undone again by OSK_COLUMN_FIRST below — the two together are names.txt's
 * "column = (X-0x68)>>3" — but they are spelt separately because the instructions are. */
#define OSK_X_ORIGIN 0x38
#define OSK_Y_ORIGIN 0x20

/* The three row bands, as biased y. They are closed at the top and inclusive at the bottom, and
 * they SHARE their boundaries: a biased y of exactly 0x70 belongs to the top row, because that
 * row's `ble` is tested first. */
#define OSK_ROW_BAND_TOP 0x60
#define OSK_ROW_TOP_MAX 0x70
#define OSK_ROW_MIDDLE_MAX 0x80
#define OSK_ROW_BOTTOM_MAX 0x90

/* The column band, as biased x, and the shift from pixels to columns. */
#define OSK_COLUMN_FIRST 0x30
#define OSK_COLUMN_LAST 0x110
#define OSK_COLUMN_SHIFT 3

/* ================================================================================================
 * ikbd_send_cmd @ 0x14444 — the four instructions that hand the keyboard controller one byte.
 *
 * `btst #1,$fffc00 / beq.s *-8 / move.b d0,$fffc02 / rts`. The two addresses are the kit's
 * (`OS_HW_ACIA_STATUS`, `OS_ACIA_TX_RDY` and `OS_HW_ACIA_DATA` in tools/recreate_kit/include/os.h)
 * because both models need to spell them; only the poll cap below is this routine's own.
 * ============================================================================================= */

/* WHY A CAP, WHEN THE ORIGINAL HAS NONE — src/sched.c's argument, one register over. The status byte
 * is STATIC in the kit's seeded read model: one declaration describes every read of it, so a run
 * that declares TDRE clear spins for ever on BOTH sides. The oracle's own instruction cap ends its
 * spin and the run is thrown away; the candidate has no such cap, and a hung suite is worse evidence
 * than a red one. So the loop gives up and tallies a refusal, which `harness.differential` turns
 * into a named failure. The number is small on purpose: under any declaration the model can serve,
 * the loop leaves on its FIRST poll, so anything above one is already unreachable — and a low cap
 * keeps the read ledger a run of this shape can produce short enough to read.
 *
 * AND WHY IT MUST NOT BIND ON TARGET. The cap is a fact about the MODEL, not about the ACIA: a real
 * 6850 at 7812.5 baud takes on the order of ten thousand cycles to empty its transmitter, and a
 * dozen polls is a few hundred — so a build for the real Atari that kept sixteen would silently drop
 * every command issued behind another one, with nothing off target able to see it. The split is the
 * kit's own `OS_NO_REFUSAL_TALLY`, which `os.h` documents as "any on-target build": src/input.c
 * compiles the give-up arm only when that is NOT set, so the loop this constant bounds is the
 * original's unbounded spin on target and a capped one off it. The constant itself is unconditional
 * — one `#define` per name is the project's rule (test_constants.py) — and simply has no reader in
 * a target build. */
#define IKBD_TX_POLL_MAX 16u

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
uint32_t onscreen_keyboard_hit_test(const uint8_t *image, uint32_t scratch);
void ikbd_send_cmd(uint8_t command);

#endif /* ZYNAPS_INPUT_H */
