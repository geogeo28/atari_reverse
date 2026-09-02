/* The host C "cores" the CALLBACK DOOR probe twins call (test_callback_door.py).
 *
 * A real project's callees are its verified cores, reached out of its candidate `.so`. These stand
 * in for them so the kit's own suite pins the door without depending on any game's `src/asm/`.
 *
 * Both take the image as argument 0 and WRITE THROUGH IT: the door's whole job on that argument is
 * to substitute a host pointer for the emulated base, and a callee that only computed a return value
 * would leave that substitution unmeasured — the image is where it shows.
 */
#include <stdint.h>

/* Where a callback marks the image, and with what. Mirrored by the Python side, which asserts the
 * mark landed at exactly this offset — the check that the substituted pointer was the image's. */
#define DOOR_PROBE_MARK_AT 0x40
#define DOOR_PROBE_MARK    0xA5

/* What door_probe_mark_host answers: a value with a bit set in every byte, so a result that failed
 * to reach D0 whole is visible rather than plausible. */
#define DOOR_PROBE_MARK_RESULT 0x0BADF00Du

/* A WEIGHTED sum, not a plain one: each argument's weight is distinct, so an argument dropped,
 * duplicated or read from the wrong stack slot changes the answer instead of cancelling out. */
uint32_t door_probe_sum_host(uint8_t *image, uint32_t a, uint32_t b, uint32_t c) {
    image[DOOR_PROBE_MARK_AT] = DOOR_PROBE_MARK;
    return a + 2u * b + 4u * c;
}

uint32_t door_probe_mark_host(uint8_t *image) {
    image[DOOR_PROBE_MARK_AT] = DOOR_PROBE_MARK;
    return DOOR_PROBE_MARK_RESULT;
}

/* A core that takes NO IMAGE — the shape of a hardware seam (`hw_bset8(addr, bit)`) or a device
 * command (`ikbd_send_cmd(cmd)`). Weighted like the sum above, so an argument the door substituted
 * a pointer over, or read from the wrong slot, changes the answer. */
uint32_t door_probe_no_image_host(uint32_t a, uint32_t b) {
    return a + 2u * b;
}

/* ...and one declared `void`, whose D0 on the machine is whatever the callee left. Its `return`
 * register is deliberately given a value the test would notice, to show the door does not use it. */
uint32_t door_probe_void_host(uint8_t *image) {
    image[DOOR_PROBE_MARK_AT] = DOOR_PROBE_MARK;
    return DOOR_PROBE_MARK_RESULT;
}
