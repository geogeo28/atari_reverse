/* TOS's KEYBOARD — $fc2b5c (the shift machine) and $fc2c42 (a scancode into the IOREC).
 *
 * `src/bios/acia_service.c` decides a byte out of the IKBD's 6850 is a scancode and falls in here.
 * What the ROM does with it is two routines in one straight run of code:
 *
 *   $fc2b5c  a chain of nine `cmpi.b` — the four modifier keys' makes and breaks, and CapsLock —
 *            each of which only touches `KBSHIFT` and returns. Anything else is a key: its MAKE
 *            arms the auto-repeat (or silences it, if another key is already held) and its BREAK
 *            disarms it and returns — except for the two breaks that ALT turns into mouse buttons.
 *   $fc2c42  the key path: the click, the three `Keytbl` tables, the CONTROL and ALTERNATE
 *            rewrites, and the four-byte record.
 *
 * WHY $fc2c42 IS ITS OWN ENTRY AND ITS OWN FUNCTION: TIMER C calls it. `$fc310c` is a `bsr` into it
 * with the held scancode in D0 and `$c76` in A0, which is how a key repeats — so the IOREC is a
 * PARAMETER here and not a constant, and the routine is the one place a key becomes a record
 * whether it came from the 6301 or from a countdown.
 *
 * THE ALTERNATE ARM DOES NOT ALWAYS QUEUE ANYTHING. ALT+Help bumps `_dumpflg` and returns; ALT with
 * Home, Insert or an arrow key drives the EMULATED MOUSE — it builds a three-byte relative-mouse
 * packet of its own at `$e5e` (not the 6301's at `$e44`) and calls `mousevec` with it. Those paths
 * leave the ring untouched, which is what `Bconin` would otherwise be waiting on.
 *
 * KBSHIFT IS RE-READ AT EVERY TEST, exactly as the ROM's separate `btst #n,$e61` instructions are.
 * That is not caution about a caller: the mouse-button arm WRITES it and the packet header is built
 * from what it wrote, so a reconstruction that had read it once would build the previous header.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "bios/iorec.h"
#include "bios/keyboard.h"
#include "sound.h"
#include "staged_call.h"

/* `btst #0,conterm / move.l #$fc31e0,snd_list / clr.b snd_delay` — the click, which is a Dosound
 * list handed to the 200 Hz driver rather than a sound made here. The ROM spells it twice, at the
 * CapsLock arm and at the head of the key path; both are this. */
static void kbd_key_click(uint8_t *image)
{
    if (!(image[SYSVAR_CONTERM] & (1u << CONTERM_CLICK_BIT)))
        return;
    sound_start_list(image, KEYCLICK_SOUND_LIST);
}

/* ---- the record, and the ring it goes in -------------------------------------------------------- */

/* `$fc2dee` — the scancode word and the ASCII word packed into one longword and stored at the IKBD
 * IOREC's tail. `code` is the scancode the arms above may have rewritten; `ascii` is what the key
 * table produced, or 0 where an arm dropped it. */
static void kbd_queue_record(uint8_t *image, uint32_t iorec, uint16_t code, uint16_t ascii)
{
    uint16_t key = (uint16_t)((uint16_t)(code << 8) + ascii);
    /* The step and the wrap are `include/bios/iorec.h`'s — the ROM's own `$fc28ea` — and the FULL rule is
     * this writer's own: the key is DROPPED. Nothing moves, not the tail and not the head, so a full
     * ring loses the newest key rather than the oldest. */
    uint16_t next = iorec_index_after(image, iorec, be16(image + iorec + IOREC_TAIL),
                                      IOREC_KEY_BYTES);
    uint32_t record;

    if (next == be16(image + iorec + IOREC_HEAD))
        return;
    record = ((uint32_t)image[KBSHIFT] << KEY_RECORD_KBSHIFT_SHIFT)
             | ((uint32_t)(key >> 8) << KEY_RECORD_SCANCODE_SHIFT)
             | ((uint32_t)(uint8_t)key << KEY_RECORD_ASCII_SHIFT);
    /* `btst #3,conterm` — off, which is how a stock machine boots, the shift state is not reported
     * and the record's top byte is zero. */
    if (!(image[SYSVAR_CONTERM] & (1u << CONTERM_KBSHIFT_BIT)))
        record &= KEY_RECORD_WITHOUT_KBSHIFT;
    wr32(image + iorec_record_at(image, iorec, next), record);
    wr16(image + iorec + IOREC_TAIL, next);
}

/* ---- the emulated mouse ------------------------------------------------------------------------- */

/* `$fc2e7a` — the three-byte relative-mouse packet ALT builds, and `mousevec` called with it.
 *
 * THE HEADER IS KBSHIFT'S TOP BITS: `lsr.b #5` puts the two emulated button flags where a real
 * $f8..$fb header's button bits are, and `addi.b #-8` biases them into that range. So pressing
 * ALT+Home changes the header of every subsequent move as well as sending a packet of its own. */
static void kbd_emulated_mouse(uint8_t *image, uint8_t dx, uint8_t dy)
{
    uint32_t routine = be32(image + KBDVECS + KBDVECS_MOUSEVEC);

    image[KBD_MOUSE_PACKET] = (uint8_t)((image[KBSHIFT] >> KBSHIFT_BUTTON_SHIFT)
                                        + KBD_MOUSE_HEADER_BIAS);
    image[KBD_MOUSE_PACKET + 1] = dx;
    image[KBD_MOUSE_PACKET + 2] = dy;
    call_vector_packet(image, routine, KBD_MOUSE_PACKET);
}

/* `move.b kbshift,d0 / andi.b #3,d0 / beq` — either SHIFT key turns the eight-pixel step into one.
 * The MAGNITUDE only: the ROM's four arrow arms each negate it for themselves where they need to,
 * and so does each of the four below. */
static uint8_t kbd_mouse_step(const uint8_t *image)
{
    return (image[KBSHIFT] & KBSHIFT_EITHER_SHIFT) ? KBD_MOUSE_FINE_STEP : KBD_MOUSE_STEP;
}

/* ---- the two modifier arms ---------------------------------------------------------------------- */

/* `$fc2d08` onwards — ALTERNATE. Four outcomes, and only the last of them reaches the ring. */
static void kbd_alternate_key(uint8_t *image, uint32_t iorec, uint16_t code, uint16_t ascii)
{
    uint8_t scancode = (uint8_t)code;
    int index;

    if (scancode == SCANCODE_HELP) {
        wr16(image + SYSVAR_DUMPFLG, (uint16_t)(be16(image + SYSVAR_DUMPFLG) + 1));
        return;
    }
    /* The four mouse-button keys, walked from the END by the ROM's `dbf`: Home and Insert, each
     * make and break. Which BUTTON is bit 4 of the scancode, added to the first button's bit. */
    for (index = ALT_MOUSE_BUTTON_KEY_COUNT - 1; index >= 0; index--) {
        unsigned bit;

        if (scancode != image[addr_add(ALT_MOUSE_BUTTON_KEYS, (uint32_t)index)])
            continue;
        bit = (scancode & (1u << ALT_MOUSE_BUTTON_SELECT_BIT))
              ? KBSHIFT_LEFT_BUTTON_BIT : KBSHIFT_RIGHT_BUTTON_BIT;
        if (scancode & (1u << SCANCODE_BREAK_BIT))
            image[KBSHIFT] = (uint8_t)(image[KBSHIFT] & ~(1u << bit));
        else
            image[KBSHIFT] = (uint8_t)(image[KBSHIFT] | (1u << bit));
        kbd_emulated_mouse(image, 0, 0);
        return;
    }
    if (scancode == SCANCODE_CURSOR_UP) {
        kbd_emulated_mouse(image, 0, (uint8_t)-kbd_mouse_step(image));
        return;
    }
    if (scancode == SCANCODE_CURSOR_LEFT) {
        kbd_emulated_mouse(image, (uint8_t)-kbd_mouse_step(image), 0);
        return;
    }
    if (scancode == SCANCODE_CURSOR_RIGHT) {
        kbd_emulated_mouse(image, kbd_mouse_step(image), 0);
        return;
    }
    if (scancode == SCANCODE_CURSOR_DOWN) {
        kbd_emulated_mouse(image, 0, kbd_mouse_step(image));
        return;
    }
    /* ALT+a number-row key gets a scancode of its own — `addi.b #118`, a BYTE add — and every
     * LETTER key loses its ASCII, so a program reading the ring sees the scancode alone. */
    if (scancode >= SCANCODE_DIGIT_FIRST && scancode <= SCANCODE_DIGIT_LAST) {
        code = set_low_byte(code, (uint8_t)(scancode + ALT_DIGIT_OFFSET));
        ascii = 0;
    } else if ((ascii >= ASCII_UPPER_FIRST && ascii <= ASCII_UPPER_LAST)
               || (ascii >= ASCII_LOWER_FIRST && ascii <= ASCII_LOWER_LAST)) {
        ascii = 0;
    }
    kbd_queue_record(image, iorec, code, ascii);
}

/* `$fc2ca0` onwards — CONTROL, which rewrites the ASCII and, for three keys, the scancode too.
 *
 * THE CARRIAGE-RETURN SUBSTITUTION COMES FIRST and survives the three scancode arms, so CTRL+Home
 * carries whatever the table gave it. The ROM's `beq` after `moveq #10,d0` can never be taken — a
 * `moveq` of 10 clears Z — so it is a fall-through and is transcribed as one. */
static void kbd_control_key(uint8_t *image, uint32_t iorec, uint16_t code, uint16_t ascii)
{
    uint8_t scancode = (uint8_t)code;

    if (ascii == ASCII_CARRIAGE_RETURN)
        ascii = ASCII_LINE_FEED;
    if (scancode == SCANCODE_HOME) {
        kbd_queue_record(image, iorec, (uint16_t)(code + CONTROL_HOME_OFFSET), ascii);
        return;
    }
    if (scancode == SCANCODE_CURSOR_LEFT) {
        kbd_queue_record(image, iorec, CONTROL_CURSOR_LEFT, 0);
        return;
    }
    if (scancode == SCANCODE_CURSOR_RIGHT) {
        kbd_queue_record(image, iorec, CONTROL_CURSOR_RIGHT, 0);
        return;
    }
    if (ascii == ASCII_DIGIT_TWO)
        ascii = CONTROL_DIGIT_TWO;
    else if (ascii == ASCII_DIGIT_SIX)
        ascii = CONTROL_DIGIT_SIX;
    else if (ascii == ASCII_MINUS)
        ascii = CONTROL_MINUS;
    else
        ascii = (uint16_t)(ascii & CONTROL_MASK);
    kbd_queue_record(image, iorec, code, ascii);
}

/* ---- the routines ------------------------------------------------------------------------------- */

void kbd_queue_key(uint8_t *image, uint8_t scancode, uint32_t iorec)
{
    uint16_t code = scancode;
    uint32_t index = scancode & SCANCODE_INDEX_MASK;
    uint32_t table = be32(image + KEYTBL_STRUCT + KEYTBL_FIELD_UNSHIFTED);
    uint16_t ascii;

    kbd_key_click(image);
    /* CapsLock picks the third table and either SHIFT then overrides it — which is why holding
     * shift with CapsLock on gives the shifted table and not the capslocked one. */
    if (image[KBSHIFT] & (1u << KBSHIFT_CAPSLOCK_BIT))
        table = be32(image + KEYTBL_STRUCT + KEYTBL_FIELD_CAPSLOCK);
    if (image[KBSHIFT] & KBSHIFT_EITHER_SHIFT) {
        /* SHIFT+F1..F10 never reaches a table at all: the scancode moves up by ten keys and the
         * record carries no ASCII. The test is on the MASKED index, so a shifted F-key RELEASE is
         * renumbered too. */
        if (index >= SCANCODE_FUNCTION_FIRST && index <= SCANCODE_FUNCTION_LAST) {
            kbd_queue_record(image, iorec, (uint16_t)(code + SCANCODE_FUNCTION_SHIFTED), 0);
            return;
        }
        table = be32(image + KEYTBL_STRUCT + KEYTBL_FIELD_SHIFTED);
    }
    ascii = image[addr_add(table, index)];
    if (image[KBSHIFT] & (1u << KBSHIFT_CONTROL_BIT)) {
        kbd_control_key(image, iorec, code, ascii);
        return;
    }
    if (image[KBSHIFT] & (1u << KBSHIFT_ALTERNATE_BIT)) {
        kbd_alternate_key(image, iorec, code, ascii);
        return;
    }
    kbd_queue_record(image, iorec, code, ascii);
}

/* `$fc2be6` — everything the nine-way modifier chain below did not claim: the auto-repeat state,
 * and then the key path.
 *
 * A MAKE arms the repeat only if no key is held; a second key held down silences the first rather
 * than replacing it, which is why both countdowns go to zero and the held scancode stays. A BREAK
 * disarms it and then RETURNS — the release of a key is not a key — with two exceptions, the two
 * codes ALT turns into mouse-button releases. */
static void kbd_key_or_repeat(uint8_t *image, uint8_t scancode, uint32_t iorec)
{
    if (!(scancode & (1u << SCANCODE_BREAK_BIT))) {
        if (image[SYSVAR_KB_REPEAT_KEY] == 0) {
            image[SYSVAR_KB_REPEAT_KEY] = scancode;
            image[SYSVAR_KB_REPEAT_DELAY] = image[KBRATE_DELAY];
            image[SYSVAR_KB_REPEAT_LEFT] = image[KBRATE_REPEAT];
        } else {
            image[SYSVAR_KB_REPEAT_DELAY] = 0;
            image[SYSVAR_KB_REPEAT_LEFT] = 0;
        }
    } else {
        if (image[SYSVAR_KB_REPEAT_KEY] != 0) {
            image[SYSVAR_KB_REPEAT_KEY] = 0;
            image[SYSVAR_KB_REPEAT_DELAY] = 0;
            image[SYSVAR_KB_REPEAT_LEFT] = 0;
        }
        if (scancode != SCANCODE_HOME_BREAK && scancode != SCANCODE_INSERT_BREAK)
            return;
        if (!(image[KBSHIFT] & (1u << KBSHIFT_ALTERNATE_BIT)))
            return;
    }
    kbd_queue_key(image, scancode, iorec);
}

void kbd_scancode(uint8_t *image, uint8_t scancode, uint32_t iorec)
{
    uint8_t shift = image[KBSHIFT];

    switch (scancode) {
    case SCANCODE_LEFT_SHIFT:
        shift |= 1u << KBSHIFT_LEFT_SHIFT_BIT;
        break;
    case SCANCODE_LEFT_SHIFT | SCANCODE_RELEASE:
        shift &= (uint8_t)~(1u << KBSHIFT_LEFT_SHIFT_BIT);
        break;
    case SCANCODE_RIGHT_SHIFT:
        shift |= 1u << KBSHIFT_RIGHT_SHIFT_BIT;
        break;
    case SCANCODE_RIGHT_SHIFT | SCANCODE_RELEASE:
        shift &= (uint8_t)~(1u << KBSHIFT_RIGHT_SHIFT_BIT);
        break;
    case SCANCODE_CONTROL:
        shift |= 1u << KBSHIFT_CONTROL_BIT;
        break;
    case SCANCODE_CONTROL | SCANCODE_RELEASE:
        shift &= (uint8_t)~(1u << KBSHIFT_CONTROL_BIT);
        break;
    case SCANCODE_ALTERNATE:
        shift |= 1u << KBSHIFT_ALTERNATE_BIT;
        break;
    case SCANCODE_ALTERNATE | SCANCODE_RELEASE:
        shift &= (uint8_t)~(1u << KBSHIFT_ALTERNATE_BIT);
        break;
    /* CapsLock TOGGLES, and only on its make — its release ($ba) is not in this chain at all and
     * goes down the key path like any other break. It is also the one modifier that clicks. */
    case SCANCODE_CAPSLOCK:
        kbd_key_click(image);
        shift ^= 1u << KBSHIFT_CAPSLOCK_BIT;
        break;
    default:
        kbd_key_or_repeat(image, scancode, iorec);
        return;
    }
    image[KBSHIFT] = shift;
}
