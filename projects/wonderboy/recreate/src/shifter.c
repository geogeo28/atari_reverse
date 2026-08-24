/* shifter.c — the ON-TARGET half of the port's one shifter sink. Why it is a module of its own,
 * what it can and cannot be pinned by, and why the OFF-target half is `static inline` in
 * ../include/shifter.h instead of here, are all in that header.
 *
 * There is no logic here and there is not meant to be: every routine is one write, and the file
 * exists so that the `WB_ON_TARGET` arm is written ONCE. WB_ON_TARGET is defined only by
 * ../atari/build.sh, so off target this file compiles to nothing at all and the sink's empties come
 * from the header — which `assert_the_differential_build_is_unchanged` and
 * `assert_the_sink_arm_lives_in_one_place` measure at the source rather than asserting in prose.
 *
 * THE SINK IS WRITTEN AS CALLS RATHER THAN AS NO CODE AT ALL, which is the decision the empty arm
 * invites a reader to question. What the callers READ in order to make each write — `set_palette`'s
 * row, `flip_screen`'s two front-buffer bytes, `boot_prompt_screen`'s two immediates — and the ORDER
 * they make them in are real reconstruction, and they stay where a reader meets them. Compiling the
 * sink out of the CALLERS would have taken the reads with it and left the one place the claim is
 * untested unstated.
 */
#include "shifter.h"

#ifdef WB_ON_TARGET
#include "wonderboy.h"

/* The on-target arm ../include/shifter.h has promised since batch 12. `wonderboy_target.h` lives in
 * ../atari/shim_include and is on the include path only for that build; the store itself, and the
 * translation from the game's own 512 KB map onto the array GEMDOS placed, are
 * ../atari/wonderboy_backend.c's. */
#include "wonderboy_target.h"

static void shifter_write_byte(uint32_t reg, uint8_t value) { wb_target_shifter_byte(reg, value); }

/* STATIC, and it is the whole reason `shifter_palette_write` takes an INDEX. A public raw-address
 * word write is an invitation to name a shifter register anywhere in the port, which is the second
 * copy of this arm by another route; every word this port writes to the chip goes to a colour
 * register, so the only public spelling is the one that says which pen. */
static void shifter_write_word(uint32_t reg, uint16_t value) { wb_target_shifter_word(reg, value); }

void shifter_screen_base_write(uint8_t high, uint8_t mid) {
    shifter_write_byte(WB_SHIFTER_SCREEN_BASE_HIGH, high);
    shifter_write_byte(WB_SHIFTER_SCREEN_BASE_MID, mid);
}

void shifter_palette_write(unsigned index, uint16_t colour) {
    shifter_write_word(WB_SHIFTER_PALETTE + index * WB_SHIFTER_PALETTE_STRIDE, colour);
}
#endif /* WB_ON_TARGET */
