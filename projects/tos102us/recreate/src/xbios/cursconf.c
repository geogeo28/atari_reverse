/* XBIOS Cursconf (function 21) — $fc4698.
 *
 * Configures the BIOS console's alpha cursor. It is the one XBIOS call implemented inside the
 * console driver rather than beside the rest of the XBIOS, because the state it edits is the block
 * the driver and the VDI escape share at $2994.
 *
 *      lea     CON_STATE_FLAGS,a4
 *      move.w  4(sp),d0            ; the function
 *      cmp.w   #7,d0
 *      bhi.s   .return             ; ...and out of range is a plain `rts`, not an error
 *      add.w   d0,d0
 *      move.w  TABLE(pc,d0.w),d0   ; an eight-entry table of signed WORD displacements
 *      jmp     TABLE(pc,d0.w)
 *
 *   2 blink:      bset #0,(a4)                        ; $fc46c2
 *   3 steady:     bclr #0,(a4)                        ; $fc46c8
 *   4 set rate:   move.b 7(sp),-18(a4)                ; $fc46ce — the LOW BYTE of the rate word
 *   5 get rate:   moveq #0,d0 / move.b -18(a4),d0     ; $fc46d6
 *   6 set spare:  move.b 7(sp),d0 / move.b d0,1(a4)   ; $fc46de
 *   7 get spare:  moveq #0,d0 / move.b 1(a4),d0       ; $fc46e8
 *
 * FUNCTIONS 0 AND 1 — hide and show — ARE THE CONSOLE DRIVER'S OWN, and the table sends them
 * straight into it: $fc45d8 and $fc45be keep a hide-DEPTH counter at $2840 and, when it reaches
 * zero, XOR the cursor cell into the screen through the console's line and plane geometry. They
 * halted here until `Bconout(CON:)` landed and are `console_hide_cursor` / `console_show_cursor` in
 * `src/bios/vt52.c` now — one definition, called from the two entries the ROM calls it from, rather
 * than a second copy of the renderer in this file.
 *
 * WHAT EACH ARM LEAVES IN D0 is the other reason to read this carefully, and the one that is not
 * guessable from the arm alone. The dispatch itself overwrites D0 — `move.w TABLE(pc,d0.w),d0` puts
 * the arm's own DISPLACEMENT WORD there before jumping — so an arm that sets no result returns a
 * number out of the jump table: $0010 for `blink`, $0016 for `steady`, $001c for `set rate`. Only
 * the two `get` arms set a result of their own (`moveq #0,d0`), and `set spare` overwrites D0's low
 * BYTE alone, over a displacement whose high byte is zero. An out-of-range function is the one arm
 * that escapes before the overwrite, so it comes back as itself.
 *
 * The displacements are therefore READ OUT OF THE ROM rather than written down: they are the same
 * bytes the ORIGINAL jumps through, and a table that moved would move both sides together.
 *
 * THE RESULT IS A WHOLE 32-BIT D0 AND ONLY SOMETIMES A WORD OF IT, which is why the C takes the D0
 * the dispatcher left and returns one. Every arm but the two `get`s writes D0's LOW WORD alone
 * (`move.w`) or its low BYTE alone (`move.b`, arm 6), so the caller's high half comes back; the two
 * `get` arms open with `moveq #0,d0`, which clears all 32 bits. A `uint16_t` result could not tell
 * those apart — it would report the same number for `moveq #0,d0 / move.b` as for a `move.w` over a
 * caller's dirty D0 — so the width of the return value IS one of the claims here.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "vt52.h"

#define CURSCONF_JUMP_TABLE_ENTRY_BYTES 2   /* signed WORD displacements */

/* D0's low word once the dispatch has jumped: the arm's own DISPLACEMENT out of the ROM's jump
 * table, which `move.w TABLE(pc,d0.w),d0` put there on the way in.
 *
 * READ WHERE AN ARM USES IT rather than once above the switch. The ROM reads it for every arm, and
 * so may a reconstruction — the table is in ROM and the read has no surface at all — but writing it
 * once at the top makes the two `get` arms, which open with `moveq #0,d0` and throw the word away,
 * pay for the table walk anyway. Measured when the two drawing arms below landed and turned this
 * routine into one GCC hoists for: `xbios_cursconf / get rate` went 94 -> 200 cycles. */
static uint16_t arm_displacement(const uint8_t *image, uint16_t function)
{
    return be16(image + CURSCONF_JUMP_TABLE + function * CURSCONF_JUMP_TABLE_ENTRY_BYTES);
}

/* ...and what an arm that sets NO result of its own hands back: that displacement over the caller's
 * own high half. */
static uint32_t arm_result(const uint8_t *image, uint32_t entry_d0, uint16_t function)
{
    return set_low_word(entry_d0, arm_displacement(image, function));
}

uint32_t xbios_cursconf(uint8_t *image, uint32_t entry_d0, uint16_t function, uint16_t rate)
{
    /* The `bhi` is taken before D0 is overwritten, so the function number the dispatch's `move.w`
     * put in D0's low word is still there — over the caller's own high half. */
    if (function > CURSCONF_MAX_FUNCTION)
        return set_low_word(entry_d0, function);

    switch (function) {
    /* The two that DRAW. Neither writes D0 — the renderer's own arms end on an `rts` with the
     * dispatch's displacement still in it — so both fall through to the same result as `blink` and
     * `steady` beside them. */
    case CURSCONF_HIDE:
        console_hide_cursor(image);
        return arm_result(image, entry_d0, function);
    case CURSCONF_SHOW:
        console_show_cursor(image);
        return arm_result(image, entry_d0, function);
    case CURSCONF_BLINK:
        image[CON_STATE_FLAGS] |= (uint8_t)(1u << CON_FLAG_BLINKS);
        return arm_result(image, entry_d0, function);
    case CURSCONF_STEADY:
        image[CON_STATE_FLAGS] &= (uint8_t)~(1u << CON_FLAG_BLINKS);
        return arm_result(image, entry_d0, function);
    case CURSCONF_SET_RATE:
        image[CON_BLINK_RATE] = (uint8_t)rate;
        return arm_result(image, entry_d0, function);
    case CURSCONF_GET_RATE:
        return image[CON_BLINK_RATE];       /* `moveq #0,d0` first: the WHOLE register */
    case CURSCONF_SET_SPARE:
        image[CON_STATE_SPARE] = (uint8_t)rate;
        /* `move.b 7(sp),d0` overwrites D0's low BYTE only, over the displacement the dispatch left
         * in its low word — so that displacement's high byte survives, and is 0 for this arm. */
        return set_low_word(entry_d0,
                            set_low_byte(arm_displacement(image, function), (uint8_t)rate));
    case CURSCONF_GET_SPARE:
        return image[CON_STATE_SPARE];
    }
    /* UNREACHABLE: the `bhi` above admits 0..7 and all eight are arms. It is spelt as the halt
     * rather than as a value because a value here would be this file's own invention, which is what
     * `recreate.h` exists to refuse — and because nothing about a `switch` over a `uint16_t` lets
     * the compiler say so. */
    recreate_not_reconstructed("XBIOS Cursconf: a function number past the eight-entry jump table, "
                               "which the bounds check above does not let through");
}
