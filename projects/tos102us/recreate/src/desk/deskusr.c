/* deskusr.c — THE TEXT VIEW'S LINE AND ITS FORMATTERS (`desk/deskusr.h`): my_itoa `$fde500`, fmt_time `$fde546`, fmt_date
 * `$fde5ba` and ob_sfcb `$fde610`. Alcyon C in the ROM, ported over its own order. None yields.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/strings.h"
#include "desk/deskusr.h"

_Static_assert(OB_SFCB_FRAME_BYTES == HOST_SLOT_AES_DESK_OB_SFCB_FRAME_BYTES, "ob_sfcb's frame and its host slot");
_Static_assert(sizeof(int16_t) == HOST_SLOT_AES_DESK_MY_ITOA_NUMBER_BYTES, "my_itoa's number and its host slot");

/* $fde500 — my_itoa: `number` as two digits at `text` — "00" laid and ended first, then merge_str's "%W" of it over
 * them, from the SECOND place where it is at most 9 (an UNSIGNED compare): a leading 0. merge_str is handed the
 * ADDRESS OF THE ARGUMENT WORD ITSELF as its parameters (`move.l a6,(sp) / addq.l #8,(sp)`): a host slot off target,
 * holding its value. */
void aes_desk_my_itoa(uint8_t *image, int16_t number, uint32_t text)
{
    uint32_t number_at = host_slot_claim(AES_DESK_MY_ITOA_NUMBER, &number);
    int16_t digit;

    host_slot_store_words(image, number_at, (const uint16_t *)&number, 1);
    for (digit = 0; digit < MY_ITOA_DIGITS; digit++)
        set_bus_byte(image, text + (uint32_t)digit, DIGIT_ZERO);
    set_bus_byte(image, text + MY_ITOA_DIGITS, STRING_NUL);
    aes_merge_str(image, (uint16_t)number <= MY_ITOA_ONE_DIGIT_MOST ? text + 1 : text, AES_DESK_MY_ITOA_TEMPLATE, number_at);
    host_slot_release(AES_DESK_MY_ITOA_NUMBER);
}

/* $fde546 — fmt_time: the DOS time `time` as "hhmm" and "am" / "pm" — the hour on a twelve-hour clock (noon on is the
 * afternoon, 12 o'clock and after less twelve; hour 0 is 12). Its answer is strcpy's. */
uint32_t aes_desk_fmt_time(uint8_t *image, int16_t time, uint32_t text)
{
    uint16_t packed = (uint16_t)time;
    int16_t hours = (int16_t)((packed & DOS_TIME_HOURS_MASK) >> DOS_TIME_HOURS_SHIFT & DOS_TIME_HOURS_FIELD);
    int afternoon;

    if (hours >= CLOCK_HALF_DAY_HOURS) {
        if (hours > CLOCK_HALF_DAY_HOURS)
            hours -= CLOCK_HALF_DAY_HOURS;
        afternoon = 1;
    } else {
        if (hours == 0)
            hours = CLOCK_HALF_DAY_HOURS;
        afternoon = 0;
    }
    aes_desk_my_itoa(image, hours, text);
    aes_desk_my_itoa(image, (int16_t)((packed & DOS_TIME_MINUTES_MASK) >> DOS_TIME_MINUTES_SHIFT & DOS_TIME_MINUTES_FIELD),
                     text + FMT_PAIR_BYTES);
    return aes_strcpy(image, afternoon ? AES_DESK_PM : AES_DESK_AM, text + FMT_TIME_SUFFIX);
}

/* $fde5ba — fmt_date: the DOS date `date` as "mmddyy" — the year's last two digits of 1980 on. */
void aes_desk_fmt_date(uint8_t *image, int16_t date, uint32_t text)
{
    uint16_t packed = (uint16_t)date;
    uint16_t year = (uint16_t)(((packed >> DOS_DATE_YEAR_SHIFT & DOS_DATE_YEAR_FIELD) + DOS_DATE_YEAR_BASE) % CENTURY_YEARS);

    aes_desk_my_itoa(image, (int16_t)((packed & DOS_DATE_MONTH_MASK) >> DOS_DATE_MONTH_SHIFT), text);
    aes_desk_my_itoa(image, (int16_t)(packed & DOS_DATE_DAY_FIELD), text + FMT_PAIR_BYTES);
    aes_desk_my_itoa(image, (int16_t)year, text + 2 * FMT_PAIR_BYTES);
}

/* ---- ob_sfcb: the line, laid character by character at `*line` ---------------------------------------------------- */

static inline void put(uint8_t *image, uint32_t *line, uint8_t character)
{
    set_bus_byte(image, (*line)++, character);
}

/* Blanks until the line is `column` characters long (a SIGNED longword compare of the length). */
static inline void pad_to(uint8_t *image, uint32_t *line, uint32_t start, int16_t column)
{
    while ((int32_t)(*line - start) < column)
        put(image, line, STRING_SPACE);
}

/* The text at `from` copied until its NUL; the cursor left at the NUL. */
static inline uint32_t copy_out(uint8_t *image, uint32_t *line, uint32_t from)
{
    while (bus_byte(image, from))
        put(image, line, bus_byte(image, from++));
    return from;
}

/* `pairs` pairs of characters of `field` copied, `separator` between them ("mm-dd-yy", "hh:mm"). */
static inline void pairs_out(uint8_t *image, uint32_t *line, uint32_t field, uint16_t pairs, uint8_t separator)
{
    while (pairs--) {
        put(image, line, bus_byte(image, field++));
        put(image, line, bus_byte(image, field++));
        if (pairs)
            put(image, line, separator);
    }
}

/* $fde610 — ob_sfcb: THE LINE A FILE IS SHOWN BY IN A WINDOW'S TEXT VIEW, at `text`, from its SFCB `sfcb` (copied into
 * the frame first): a folder's glyph or a blank, the name, the extension from its column, the size right-aligned in
 * eight (none for a folder), "mm-dd-yy", "hh:mm" and "am" / "pm" — with a blank more between the fields on any
 * screen but low resolution's. Its answer is the line's length with its NUL. THE SIZE'S BLANKS ARE COUNTED IN A WORD
 * DOWN TO ZERO: a size of more than eight digits would loop round the word (no file of a floppy has one) — as the ROM. */
uint32_t aes_desk_ob_sfcb(uint8_t *image, uint32_t sfcb, uint32_t text)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(OB_SFCB_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_OB_SFCB_FRAME, frame_local);
    uint32_t copy = frame + OB_SFCB_COPY, line = text, from, size_text = frame + OB_SFCB_SIZE_TEXT;
    int wide = be16(image + AES_GL_WIDTH) != LOW_RESOLUTION_WIDTH;
    int folder;
    uint16_t blanks;

    aes_lbcopy(image, copy, sfcb, SFCB_BYTES);
    folder = bus_byte(image, copy + SFCB_ATTR) >> SFCB_ATTR_SUBDIR_BIT & 1;
    from = copy + SFCB_NAME;
    if (wide)
        put(image, &line, STRING_SPACE);
    put(image, &line, folder ? FOLDER_GLYPH : STRING_SPACE);
    if (wide)
        put(image, &line, STRING_SPACE);
    while (bus_byte(image, from) && bus_byte(image, from) != STRING_DOT)
        put(image, &line, bus_byte(image, from++));
    pad_to(image, &line, text, wide ? OB_SFCB_EXTENSION_AT : OB_SFCB_EXTENSION_AT_LOW);
    if (bus_byte(image, from))
        from++;
    (void)copy_out(image, &line, from);
    pad_to(image, &line, text, wide ? OB_SFCB_SIZE_AT : OB_SFCB_SIZE_AT_LOW);

    if (folder)
        set_bus_byte(image, size_text, STRING_NUL);
    else
        aes_merge_str(image, size_text, AES_DESK_SIZE_TEMPLATE, copy + SFCB_SIZE);
    blanks = (uint16_t)(OB_SFCB_SIZE_DIGITS - aes_strlen(image, size_text));
    while (blanks--)
        put(image, &line, STRING_SPACE);
    (void)copy_out(image, &line, size_text);
    put(image, &line, STRING_SPACE);
    if (wide)
        put(image, &line, STRING_SPACE);

    aes_desk_fmt_date(image, (int16_t)bus_word(image, copy + SFCB_DATE), frame + OB_SFCB_DATE_TEXT);
    pairs_out(image, &line, frame + OB_SFCB_DATE_TEXT, OB_SFCB_DATE_PAIRS, OB_SFCB_DATE_SEPARATOR);
    put(image, &line, STRING_SPACE);
    if (wide)
        put(image, &line, STRING_SPACE);

    aes_desk_fmt_time(image, (int16_t)bus_word(image, copy + SFCB_TIME), frame + OB_SFCB_TIME_TEXT);
    pairs_out(image, &line, frame + OB_SFCB_TIME_TEXT, OB_SFCB_TIME_PAIRS, OB_SFCB_TIME_SEPARATOR);
    if (wide)
        put(image, &line, STRING_SPACE);
    (void)aes_strcpy(image, frame + OB_SFCB_TIME_TEXT + FMT_TIME_SUFFIX, line);
    line += OB_SFCB_SUFFIX_STEP;
    host_slot_release(AES_DESK_OB_SFCB_FRAME);
    return line - text;
}
