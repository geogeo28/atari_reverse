/* overlay.c — see overlay.h. Planar text, straight into the screen, no shifting anywhere. */
#include "overlay.h"

#include "assets.h"
#include "plat.h"
#include "tos.h"

#include "game_consts.h"

/* 16 pixels are four interleaved plane words; an 8-pixel-aligned x picks a group, a half, and
 * nothing else. The shifts are shifts and not divisions for the reason hud.c's copy records: on
 * this compiler a signed `/ 16` is a call to libgcc's __divsi3, and the Makefile's libgcc gate
 * refuses the build over it. */
#define PIXELS_PER_GROUP_SHIFT  4
#define PIXELS_PER_BYTE         8
#define PIXELS_PER_BYTE_SHIFT   3
#define SECONDS_PER_MINUTE      60
#define NUMBER_RADIX            10

static uint8_t *overlay_byte(uint8_t *screen, int x, int y)
{
    unsigned column = (unsigned)x;

    return screen + mul16((int16_t)y, (int16_t)SCREEN_BYTES_PER_LINE)
                  + (column >> PIXELS_PER_GROUP_SHIFT) * SCREEN_GROUP_BYTES
                  + ((column >> PIXELS_PER_BYTE_SHIFT) & 1u);
}

static void draw_byte_at(uint8_t *at, uint8_t bits, uint8_t pen)
{
    int plane;

    for (plane = 0; plane < SCREEN_PLANES; ++plane, at += 2) {
        *at = (uint8_t)((*at & (uint8_t)~bits) | (((pen >> plane) & 1) ? bits : 0));
    }
}

void overlay_clear(uint8_t *screen)
{
    /* The HUD strip is left standing: the trace meter and the integrity bar are still true while a
     * SECTOR CLEAR overlay is up, and blanking them would be a lie about the run. */
    bi_fill(screen, (long)SCREEN_WINDOW_LINES * SCREEN_BYTES_PER_LINE, 0UL, 0UL);
}

int overlay_text(uint8_t *screen, int x, int y, const char *text, uint8_t pen)
{
    while (*text && x + PIXELS_PER_BYTE <= SCREEN_W) {
        unsigned char c = (unsigned char)*text++;

        if (c >= FONT_FIRST_CHAR && c < FONT_FIRST_CHAR + FONT_GLYPH_COUNT) {
            const uint8_t *glyph = g_font + (c - FONT_FIRST_CHAR) * FONT_GLYPH_BYTES;
            int row;

            for (row = 0; row < FONT_GLYPH_BYTES; ++row) {
                draw_byte_at(overlay_byte(screen, x, y + row), glyph[row], pen);
            }
        }
        x += PIXELS_PER_BYTE;
    }
    return x;
}

void overlay_centre(uint8_t *screen, int y, const char *text, uint8_t pen)
{
    int glyphs = 0;
    int x;

    while (text[glyphs]) {
        ++glyphs;
    }
    /* Snapped DOWN to a byte boundary: every write in this file is a whole byte of each plane, and
     * a centred string that landed on an odd pixel would need the shifting blitter there is not. */
    x = (SCREEN_W - glyphs * PIXELS_PER_BYTE) / 2;
    x &= ~(PIXELS_PER_BYTE - 1);
    if (x < 0) {
        x = 0;
    }
    overlay_text(screen, x, y, text, pen);
}

void overlay_format_number(char *out, uint16_t value, int digits)
{
    int i;

    for (i = digits - 1; i >= 0; --i) {
        uint16_t next = divu16(value, NUMBER_RADIX);

        out[i] = (char)('0' + (value - next * NUMBER_RADIX));
        value = next;
    }
    for (i = 0; i < digits - 1 && out[i] == '0'; ++i) {
        out[i] = ' ';
    }
    out[digits] = '\0';
}

void overlay_format_clock(char *out, uint16_t ticks)
{
    uint16_t seconds = divu16(ticks, SIM_HZ);
    uint16_t minutes = divu16(seconds, SECONDS_PER_MINUTE);
    int at = 0;

    out[at++] = (char)('0' + divu16(minutes, NUMBER_RADIX));
    out[at++] = (char)('0' + (minutes - divu16(minutes, NUMBER_RADIX) * NUMBER_RADIX));
    out[at++] = ':';
    seconds = (uint16_t)(seconds - minutes * SECONDS_PER_MINUTE);
    out[at++] = (char)('0' + divu16(seconds, NUMBER_RADIX));
    out[at++] = (char)('0' + (seconds - divu16(seconds, NUMBER_RADIX) * NUMBER_RADIX));
    out[at] = '\0';
}
