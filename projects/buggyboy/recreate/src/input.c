/* input.c — keyboard/joystick input logic (read_input @ 0x120b0, check_abort @ 0x128ea).
 *
 * read_joystick (os.c) sends the IKBD joystick-interrogate command; the reply is delivered by an
 * interrupt that sets input_state/last_key, which the oracle doesn't run — so those globals are
 * treated as inputs here (scripted by the harness; see HARNESS.md). These two functions are then
 * pure logic over them.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "os.h"

/* input_state bits (joystick or mapped key): fire 0x80, up 1, down 2, left 4, right 8. */
#define INPUT_ACTIVE_MASK 0x8f     /* the "any real input" bits read_input tests */

/* keyboard scancodes the fallback maps to input_state bits. */
#define KEY_SPACE 0x39
#define KEY_UP    0x48
#define KEY_LEFT  0x4b
#define KEY_RIGHT 0x4d
#define KEY_DOWN  0x50

#define ABORT_CODE 0x0d            /* check_abort's return when a new input aborts the wait */

/* read_input @ 0x120b0 — poll the joystick; if it reports no active bits, synthesize input_state
 * from the last keyboard scancode (arrows + space). If the joystick IS active, keep input_state
 * and just clear last_key. (input_state/last_key are one adjacent word pair; the 68k walks a1
 * across them, which is why the two branches touch different words.) */
void g_read_input(uint8_t *image) {
    g_read_joystick(image);                          /* IKBD poll; no image effect */
    uint16_t input_state = be16(image + A_input_state);
    if ((input_state & INPUT_ACTIVE_MASK) != 0) {
        wr16(image + A_last_key, 0);
        return;
    }
    uint16_t key = be16(image + A_last_key);
    uint16_t bits = 0;
    if (key == KEY_SPACE) bits |= 0x80;
    if (key == KEY_UP)    bits |= 0x01;
    if (key == KEY_LEFT)  bits |= 0x04;
    if (key == KEY_RIGHT) bits |= 0x08;
    if (key == KEY_DOWN)  bits |= 0x02;
    wr16(image + A_input_state, bits);
}

/* check_abort @ 0x128ea — returns ABORT_CODE when the live input (input_state low byte) is both
 * present and differs from the baseline snapshot (input_prev low byte); otherwise returns a raw
 * non-blocking console read (GEMDOS Crawio(0xff)) with its result word swapped into the high half.
 * The only output is the return value (no image effect), so the differential test checks d0. */
uint32_t g_check_abort(uint8_t *image) {
    g_read_joystick(image);
    uint8_t live = image[A_input_state + 1];         /* low byte of the input_state word */
    uint8_t baseline = image[A_input_prev + 1];      /* low byte of the baseline word */
    if (live != 0 && live != baseline)
        return ABORT_CODE;
    uint32_t key = OS_CRAWIO_RESULT;                 /* Crawio(0xff): no key pending -> 0 */
    return (key << 16) | (key >> 16);                /* swap d0 */
}
