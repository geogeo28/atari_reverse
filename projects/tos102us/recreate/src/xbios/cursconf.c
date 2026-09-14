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
 * FUNCTIONS 0 AND 1 — hide and show — ARE NOT RECONSTRUCTED HERE. They are the cursor RENDERER
 * ($fc45d8 and $fc45be): they keep a hide-depth counter at $2840, and when it reaches zero they XOR
 * the cursor cell into the screen through the console's font and line tables. That is the console
 * driver's blit, a body of its own, and folding it into this file would be claiming a reconstruction
 * this wave did not make. The two arms HALT instead (`recreate.h`) — a value returned there would be
 * this file's invention and would look exactly like a reconstruction to every case.
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

#define CURSCONF_JUMP_TABLE_ENTRY_BYTES 2   /* signed WORD displacements */

uint32_t xbios_cursconf(uint8_t *image, uint32_t entry_d0, uint16_t function, uint16_t rate)
{
    /* D0's low word once the dispatch has jumped: the arm's displacement in the ROM's jump table. */
    uint16_t scratch;

    /* The `bhi` is taken before D0 is overwritten, so the function number the dispatch's `move.w`
     * put in D0's low word is still there — over the caller's own high half. */
    if (function > CURSCONF_MAX_FUNCTION)
        return set_low_word(entry_d0, function);
    scratch = be16(image + CURSCONF_JUMP_TABLE + function * CURSCONF_JUMP_TABLE_ENTRY_BYTES);

    switch (function) {
    case CURSCONF_BLINK:
        image[CON_STATE_FLAGS] |= (uint8_t)(1u << CON_FLAG_BLINKS);
        return set_low_word(entry_d0, scratch);
    case CURSCONF_STEADY:
        image[CON_STATE_FLAGS] &= (uint8_t)~(1u << CON_FLAG_BLINKS);
        return set_low_word(entry_d0, scratch);
    case CURSCONF_SET_RATE:
        image[CON_BLINK_RATE] = (uint8_t)rate;
        return set_low_word(entry_d0, scratch);
    case CURSCONF_GET_RATE:
        return image[CON_BLINK_RATE];       /* `moveq #0,d0` first: the WHOLE register */
    case CURSCONF_SET_SPARE:
        image[CON_STATE_SPARE] = (uint8_t)rate;
        /* `move.b 7(sp),d0` overwrites D0's low BYTE only, over the displacement the dispatch left
         * in its low word — so that displacement's high byte survives, and is 0 for this arm. */
        return set_low_word(entry_d0, set_low_byte(scratch, (uint8_t)rate));
    case CURSCONF_GET_SPARE:
        return image[CON_STATE_SPARE];
    default:
        break;
    }
    /* Only 0 and 1 are left, and they draw. */
    recreate_not_reconstructed("XBIOS Cursconf 0/1: the console's cursor renderer ($fc45d8/$fc45be)");
}
