/* hud.c — the live fields of the 320x40 status strip, drawn straight into planar memory.
 *
 * THE GEOMETRY IS art/hud.py's, and it has to be: the backdrop this draws over is that script's
 * output, so a panel edge spelled differently here would show as a field sitting off its well. The
 * constants below name the same rows and columns art/hud.py does, and the one thing they add is
 * that every field is snapped to an 8-pixel boundary — which is what lets a glyph be one byte of
 * each plane word and a fill be whole bytes, with no shifting anywhere in this file (DESIGN 15.1).
 *
 * THE BACKDROP CARRIES art/hud.py's DEMO VALUES. It was rendered from that script's DEMO_STATE, so
 * it has a sector name, a clock and three lit bars baked into it. Every live field therefore
 * CLEARS its own rectangle to the well pen before drawing, rather than trusting the art underneath
 * to be empty. That costs a fill per field per frame and removes a whole class of "the old value
 * is still showing through" bug; the fields are small (the widest is 126 px by 27 rows) and the
 * measured cost is in README.md's frame-time table.
 */
#include "hud.h"

#include "assets.h"
#include "mem.h"
#include "plat.h"
#include "tos.h"

/* ---- planar geometry ------------------------------------------------------------------------
 * 16 pixels are four interleaved plane words, 8 bytes; bit 7 of a byte is its leftmost pixel. An
 * 8-pixel-aligned x therefore picks a group, a half (high or low byte) and nothing else. */
#define PIXELS_PER_GROUP_SHIFT  4       /* 16 pixels are one group of four plane words */
#define PIXELS_PER_BYTE         8
#define PIXELS_PER_BYTE_SHIFT   3
#define HUD_TOP_LINE            SCREEN_WINDOW_LINES

/*
 * A screen line, then a byte inside it. THE MULTIPLY IS PER ROW AND NOT PER BYTE, and the shifts
 * are shifts and not divisions, because both were measured: the first version of this file wrote
 * `x / 16` on a signed int and recomputed `y * SCREEN_BYTES_PER_LINE` for every byte it touched.
 * That is two calls to libgcc's __divsi3 and one to __mulsi3 per eight pixels, and the whole HUD
 * stage cost 170 ms a frame — more than the raycast, the wall drawer and the c2p together. The
 * before-and-after is in README.md's frame-time table.
 */
static uint8_t *hud_row(uint8_t *screen, int y)
{
    /* Both operands are well inside a word, so this is the 68000's own muls.w. */
    return screen + mul16((int16_t)y, (int16_t)SCREEN_BYTES_PER_LINE);
}

static uint8_t *hud_byte(uint8_t *row, int x)
{
    unsigned column = (unsigned)x;

    return row + (column >> PIXELS_PER_GROUP_SHIFT) * SCREEN_GROUP_BYTES
               + ((column >> PIXELS_PER_BYTE_SHIFT) & 1u);
}

/* Set the eight pixels whose bit is set in `bits` to `pen`, leaving the rest of the byte alone. */
static void draw_byte_at(uint8_t *at, uint8_t bits, uint8_t pen)
{
    int plane;

    for (plane = 0; plane < SCREEN_PLANES; ++plane, at += 2) {
        *at = (uint8_t)((*at & (uint8_t)~bits) | (((pen >> plane) & 1) ? bits : 0));
    }
}

/* All eight pixels to `pen`. A solid fill overwrites the byte, so it needs no read. */
static void fill_byte_at(uint8_t *at, uint8_t pen)
{
    int plane;

    for (plane = 0; plane < SCREEN_PLANES; ++plane, at += 2) {
        *at = ((pen >> plane) & 1) ? 0xff : 0x00;
    }
}

/* A rectangle of one pen. `x` and `width` are in whole bytes of 8 pixels. */
static void fill_rect(uint8_t *screen, int x, int y, int width, int height, uint8_t pen)
{
    uint8_t *row = hud_row(screen, y);
    int line;

    for (line = 0; line < height; ++line, row += SCREEN_BYTES_PER_LINE) {
        int column;

        for (column = 0; column < width; column += PIXELS_PER_BYTE) {
            fill_byte_at(hud_byte(row, x + column), pen);
        }
    }
}

/* ---- text ------------------------------------------------------------------------------------ */

static void draw_glyph(uint8_t *screen, int x, int y, char c, uint8_t pen)
{
    const uint8_t *glyph;
    uint8_t *line;
    int row;

    if ((unsigned char)c < FONT_FIRST_CHAR || (unsigned char)c >= FONT_FIRST_CHAR + FONT_GLYPH_COUNT) {
        return;
    }
    glyph = g_font + ((unsigned char)c - FONT_FIRST_CHAR) * FONT_GLYPH_BYTES;
    line = hud_row(screen, y);
    for (row = 0; row < FONT_GLYPH_BYTES; ++row, line += SCREEN_BYTES_PER_LINE) {
        /* A blank glyph row writes nothing, which is what keeps the strip's row 8 uniform for
         * atari/verify.py's screen registration (see HUD_TITLE_HEIGHT). */
        draw_byte_at(hud_byte(line, x), glyph[row], pen);
    }
}

/*
 * Returns the pen x after the string, clipped at `limit`. THE LIMIT IS THE FIELD'S RIGHT EDGE AND
 * NOT THE SCREEN'S: the fields tile the strip, so a string longer than its field would draw over
 * the next field's well and sit there until that field's own value happened to change.
 */
static int draw_text(uint8_t *screen, int x, int y, int limit, const char *text, uint8_t pen)
{
    while (*text && x + FONT_GLYPH_WIDTH <= limit) {
        draw_glyph(screen, x, y, *text++, pen);
        x += FONT_GLYPH_WIDTH;
    }
    return x;
}

/* ---- numbers ---------------------------------------------------------------------------------
 * No libc: the platform formats its own. The width is fixed so a field never changes width and
 * never needs its tail cleared separately; `pad` is a space for a readout (a leading zero reads as
 * part of the number) and '0' for a clock, where it does not.
 *
 * THE VALUE IS A WORD AND THE DIVIDE IS DIVU. Written against `unsigned long` this loop compiled to
 * a call to libgcc's __udivsi3 AND __umodsi3 per digit — sixteen subroutine calls a frame in the
 * game build, in the one file whose cost already had to be measured twice. Every field the strip
 * shows is under 1,000, so a word is the honest type and plat.h's divu16 is the honest divide. */
#define NUMBER_MAX_DIGITS   6
#define NUMBER_RADIX        10
#define PAD_BLANK           ' '
#define PAD_ZERO            '0'

static void format_number(char *out, uint16_t value, int digits, char pad)
{
    int i;

    for (i = digits - 1; i >= 0; --i) {
        uint16_t next = divu16(value, NUMBER_RADIX);

        out[i] = (char)('0' + (value - next * NUMBER_RADIX));
        value = next;
    }
    for (i = 0; i < digits - 1 && out[i] == '0'; ++i) {
        out[i] = pad;
    }
    out[digits] = '\0';
}

/* ---- the strip's layout, from art/hud.py ------------------------------------------------------ */

#define HUD_TITLE_Y             (HUD_TOP_LINE + 1)      /* art/hud.py TITLE_BAR_TOP */
/*
 * SEVEN ROWS, NOT THE ART'S EIGHT, AND atari/verify.py DEPENDS ON IT. The strip's rows 0 and 8 are
 * the only two lines of the screen that are one uniform colour across all 320 columns, which is
 * how verify.py finds the 320x200 screen inside Hatari's bordered screenshot. Row 0 is above this
 * field; row 8 survives because the fill stops one row short of it and the font's glyphs are 5x7
 * inside an 8x8 cell, so their eighth row is blank and draw_byte leaves the pixels underneath
 * alone. A font with ink on its last row would break the registration, not the picture.
 */
#define HUD_TITLE_HEIGHT        7
#define HUD_PANEL_TOP           (HUD_TOP_LINE + 10)     /* art/hud.py PANEL_TOP */
#define HUD_PANEL_BOTTOM        (HUD_TOP_LINE + SCREEN_HUD_LINES - 2)
#define HUD_LABEL_Y             (HUD_PANEL_TOP + 1)
#define HUD_VALUE_Y             (HUD_LABEL_Y + FONT_GLYPH_BYTES + 1)
#define HUD_BAR_HEIGHT          12

/*
 * The five fields TILE the strip: together they cover all 320 pixels of rows HUD_LABEL_Y upward,
 * with no art showing between them.
 *
 * That is not the same as art/hud.py's panels, and the difference is the price of shift-free
 * drawing. Its Panel(x0, x1) pairs start at 2, 130, 204, 258 and 286 — none of them on an 8-pixel
 * boundary — so a field snapped out to the nearest boundary either leaves a sliver of the panel
 * underneath showing (which read as stray glyphs from the art's demo values: a lone "T" beside the
 * cycles readout, "KAB" beside the tokens) or covers it. Covering it is the honest one: the strip
 * loses the recessed well borders in these rows and gains a readout that means what it says.
 * Restoring the wells needs either a redraw of the art on 8-pixel boundaries or a shifting
 * blitter, and both belong to whoever owns the art next.
 */
#define HUD_FIELD_INSET         8       /* text and bars sit this far inside their field */
#define HUD_TRACE_X             0       /* art TRACE_PANEL     (2, 127)   */
#define HUD_TRACE_W             112
/* Wider than art/hud.py's 72-pixel panel, and it has to be: a ten-segment bar of one byte each is
 * 80 pixels, and with the inset that needs 96. Drawn in a 72-pixel field the last two segments
 * landed inside the CYCLES well and stayed there until the cycle count next changed. */
#define HUD_INTEGRITY_X         112     /* art INTEGRITY_PANEL (130, 201) */
#define HUD_INTEGRITY_W         96
#define HUD_CYCLES_X            208     /* art CYCLES_PANEL    (204, 255) */
#define HUD_CYCLES_W            48
#define HUD_TOKEN_X             256     /* art TOKEN_PANEL     (258, 283) */
#define HUD_TOKEN_W             32
#define HUD_CLOCK_X             288     /* art WEAPON_PANEL    (286, 317) */
#define HUD_CLOCK_W             32

/* DESIGN 3's colour contract, which art/palette.py owns and src/tables.c's g_palette_rgb is
 * generated from. Indices 12 (white) and 13 (orange) are the two RESERVED accents a wall may not
 * use, which is exactly why the HUD may: nothing in the 3D window can be confused with them. */
#define HUD_PEN_WELL            5       /* #113366, cyan 5 — the recessed panel face */
#define HUD_PEN_LABEL           3       /* #2299CC, cyan 3 */
#define HUD_PEN_DATA            11      /* #FFEE44, data yellow */
#define HUD_PEN_TEXT            12      /* #FFFFFF, the reserved rim/HUD white */
#define HUD_PEN_ALERT           13      /* #FF7722, the reserved hostile accent */
#define HUD_PEN_GOOD            14      /* #33CC66, integrity green */
#define HUD_PEN_TRIM            15      /* #333355, slate — the unlit segment */

/* DESIGN 9's thresholds: the trace bar turns hostile at the last one. */
#define TRACE_ALERT_PERCENT     75
/* DESIGN 15.1 / art/hud.py: below this the integrity bar borrows the enemy accent. */
#define INTEGRITY_CRITICAL      34

#define BAR_SEGMENTS            10
#define PERCENT_DIGITS          3
#define COUNT_DIGITS            3
#define CLOCK_DIGITS            2
/* Segments are one byte wide and contiguous: art/hud.py leaves a 1-pixel gap between them, which
 * this cannot reproduce without a shift, so the bar reads as ten blocks rather than ten pips. */
#define BAR_SEGMENT_PITCH       PIXELS_PER_BYTE
#define PERCENT_FULL            100

/* ---- fields ----------------------------------------------------------------------------------- */

/*
 * A segmented bar: BAR_SEGMENTS contiguous blocks of one byte each, so the whole thing is
 * byte-aligned and needs no shifting. Segments rather than a smooth fill because a segment count
 * reads at a glance (art/hud.py says the same thing about the same bar).
 */
static void draw_bar(uint8_t *screen, int x, int y, int width, uint8_t percent, uint8_t pen)
{
    /* However many whole segments the field has room for: the caller's width is the authority, so
     * a bar can never paint into its neighbour's well. */
    int segments = width / BAR_SEGMENT_PITCH;
    int lit;
    int segment;

    if (segments > BAR_SEGMENTS) {
        segments = BAR_SEGMENTS;
    }
    /* A word divide: percent is at most 100 and segments at most BAR_SEGMENTS, so the rounded
     * numerator is under 1,100. Written in `int` this was a call to libgcc's __divsi3 —
     * the 68000 has no 32x32 high multiply, so GCC cannot turn /100 into a reciprocal. */
    lit = divu16((uint32_t)percent * segments + PERCENT_FULL / 2, PERCENT_FULL);
    for (segment = 0; segment < segments; ++segment) {
        uint8_t ink = (segment < lit) ? pen : HUD_PEN_TRIM;

        fill_rect(screen, x + segment * BAR_SEGMENT_PITCH, y, PIXELS_PER_BYTE, HUD_BAR_HEIGHT, ink);
    }
}

static void draw_percent_field(uint8_t *screen, int x, int width, uint8_t percent, uint8_t pen)
{
    char text[NUMBER_MAX_DIGITS];
    int label_x;

    fill_rect(screen, x, HUD_LABEL_Y, width, HUD_PANEL_BOTTOM - HUD_LABEL_Y, HUD_PEN_WELL);
    format_number(text, percent, PERCENT_DIGITS, PAD_BLANK);
    label_x = draw_text(screen, x + HUD_FIELD_INSET, HUD_LABEL_Y, x + width, text, pen);
    draw_text(screen, label_x, HUD_LABEL_Y, x + width, "%", HUD_PEN_LABEL);
    draw_bar(screen, x + HUD_FIELD_INSET, HUD_VALUE_Y, width - 2 * HUD_FIELD_INSET, percent, pen);
}

static void draw_count_field(uint8_t *screen, int x, int width, uint16_t value, uint8_t pen)
{
    char text[NUMBER_MAX_DIGITS];

    fill_rect(screen, x, HUD_LABEL_Y, width, HUD_PANEL_BOTTOM - HUD_LABEL_Y, HUD_PEN_WELL);
    format_number(text, value, COUNT_DIGITS, PAD_BLANK);
    draw_text(screen, x + HUD_FIELD_INSET, HUD_LABEL_Y, x + width, text, pen);
}

static void draw_tokens(uint8_t *screen, uint8_t held)
{
    int token;

    fill_rect(screen, HUD_TOKEN_X, HUD_LABEL_Y, HUD_TOKEN_W,
              HUD_PANEL_BOTTOM - HUD_LABEL_Y, HUD_PEN_WELL);
    for (token = 0; token < HUD_TOKEN_COUNT; ++token) {
        int x = HUD_TOKEN_X + HUD_FIELD_INSET + (token & 1) * PIXELS_PER_BYTE;
        int y = HUD_LABEL_Y + (token / 2) * (FONT_GLYPH_BYTES + 2);
        uint8_t pen = ((held >> token) & 1) ? HUD_PEN_DATA : HUD_PEN_TRIM;

        draw_glyph(screen, x, y, (char)('A' + token), pen);
    }
}

/* DESIGN 5's three-segment dial: the active clock in the text pen, the other two in trim. */
static void draw_clock_dial(uint8_t *screen, uint8_t throttle)
{
    int segment;

    fill_rect(screen, HUD_CLOCK_X, HUD_LABEL_Y, HUD_CLOCK_W,
              HUD_PANEL_BOTTOM - HUD_LABEL_Y, HUD_PEN_WELL);
    for (segment = 0; segment < THROTTLE_MODE_COUNT; ++segment) {
        uint8_t pen = (segment == throttle) ? HUD_PEN_TEXT : HUD_PEN_TRIM;

        fill_rect(screen, HUD_CLOCK_X + HUD_FIELD_INSET + segment * PIXELS_PER_BYTE, HUD_VALUE_Y,
                  PIXELS_PER_BYTE, HUD_BAR_HEIGHT, pen);
    }
}

/*
 * The title bar is TWO fields, not one. The left half carries the sector name or the live message
 * line (DESIGN 15.1 gives the message its own line; the strip has room for one line of text and
 * this is it) and changes rarely; the right half carries the run clock and the measured frame time
 * and changes almost every frame. Splitting them is what lets the redraw rule below leave 224
 * pixels of the strip alone on a normal frame.
 */
#define TITLE_NAME_X        0
#define TITLE_NAME_W        224
#define TITLE_CLOCK_X       224
#define TITLE_CLOCK_W       96
#define SECONDS_PER_MINUTE  60

static void draw_title_name(uint8_t *screen, const HudState *state)
{
    fill_rect(screen, TITLE_NAME_X, HUD_TITLE_Y, TITLE_NAME_W, HUD_TITLE_HEIGHT, HUD_PEN_TRIM);
    draw_text(screen, TITLE_NAME_X, HUD_TITLE_Y, TITLE_NAME_X + TITLE_NAME_W,
              state->message ? state->message : state->sector_name,
              state->message ? HUD_PEN_TEXT : HUD_PEN_LABEL);
}

static void draw_title_clock(uint8_t *screen, const HudState *state)
{
    char text[NUMBER_MAX_DIGITS];
    int x;

    fill_rect(screen, TITLE_CLOCK_X, HUD_TITLE_Y, TITLE_CLOCK_W, HUD_TITLE_HEIGHT, HUD_PEN_TRIM);
    format_number(text, divu16(state->run_seconds, SECONDS_PER_MINUTE), CLOCK_DIGITS, PAD_ZERO);
    x = draw_text(screen, TITLE_CLOCK_X, HUD_TITLE_Y, SCREEN_W, text, HUD_PEN_TEXT);
    x = draw_text(screen, x, HUD_TITLE_Y, SCREEN_W, ":", HUD_PEN_TEXT);
    format_number(text, (uint16_t)(state->run_seconds
                                  - divu16(state->run_seconds, SECONDS_PER_MINUTE) * SECONDS_PER_MINUTE),
                  CLOCK_DIGITS, PAD_ZERO);
    x = draw_text(screen, x, HUD_TITLE_Y, SCREEN_W, text, HUD_PEN_TEXT);
    format_number(text, state->frame_ms, COUNT_DIGITS, PAD_BLANK);
    x = draw_text(screen, x + FONT_GLYPH_WIDTH, HUD_TITLE_Y, SCREEN_W, text, HUD_PEN_DATA);
    draw_text(screen, x, HUD_TITLE_Y, SCREEN_W, "MS", HUD_PEN_LABEL);
}

/* ---- the strip --------------------------------------------------------------------------------- */

void hud_blit_backdrop(uint8_t *screen)
{
    memcpy(screen + (long)HUD_TOP_LINE * SCREEN_BYTES_PER_LINE, g_hud_backdrop, HUD_BACKDROP_BYTES);
}

/*
 * Values no field can hold — integrity and trace are percentages, the throttle is 0..2, the tokens
 * are three bits — so the first hud_draw against this record redraws everything. A sentinel rather
 * than a `force` flag because the two screen buffers are refreshed independently and a flag would
 * have to be cleared twice.
 */
#define HUD_UNSET_BYTE      0xff
#define HUD_UNSET_WORD      0xffff

void hud_reset(HudState *shown)
{
    shown->sector_name = 0;
    shown->message = 0;
    shown->run_seconds = HUD_UNSET_WORD;
    shown->frame_ms = HUD_UNSET_WORD;
    shown->trace_percent = HUD_UNSET_BYTE;
    shown->throttle = HUD_UNSET_BYTE;
    shown->integrity = HUD_UNSET_BYTE;
    shown->cycles = HUD_UNSET_WORD;
    shown->tokens = HUD_UNSET_BYTE;
    shown->weapon = HUD_UNSET_BYTE;
}

/*
 * DESIGN 15.1: only fields whose value changed are redrawn. `shown` is what is currently on THIS
 * screen buffer, so the caller keeps one record per buffer — a field that changes on one frame has
 * to be redrawn in both, and a single shared record would leave the other buffer a frame stale.
 *
 * The two string fields are compared by POINTER and that is exact, not a shortcut: a sector name is
 * the Level's own array and a message is one row of a constant table, so two different texts are
 * never the same pointer.
 */
void hud_draw(uint8_t *screen, const HudState *state, HudState *shown)
{
    if (state->sector_name != shown->sector_name || state->message != shown->message) {
        draw_title_name(screen, state);
    }
    if (state->run_seconds != shown->run_seconds || state->frame_ms != shown->frame_ms) {
        draw_title_clock(screen, state);
    }
    if (state->trace_percent != shown->trace_percent) {
        uint8_t pen = (state->trace_percent >= TRACE_ALERT_PERCENT) ? HUD_PEN_ALERT : HUD_PEN_DATA;

        draw_percent_field(screen, HUD_TRACE_X, HUD_TRACE_W, state->trace_percent, pen);
    }
    if (state->integrity != shown->integrity) {
        uint8_t pen = (state->integrity < INTEGRITY_CRITICAL) ? HUD_PEN_ALERT : HUD_PEN_GOOD;

        draw_percent_field(screen, HUD_INTEGRITY_X, HUD_INTEGRITY_W, state->integrity, pen);
    }
    if (state->cycles != shown->cycles) {
        draw_count_field(screen, HUD_CYCLES_X, HUD_CYCLES_W, state->cycles, HUD_PEN_DATA);
    }
    if (state->tokens != shown->tokens) {
        draw_tokens(screen, state->tokens);
    }
    if (state->throttle != shown->throttle) {
        draw_clock_dial(screen, state->throttle);
    }
    /* HOOK: the weapon icon arrives with the gameplay agent's weapon selection; DESIGN 18 defers
     * the Spike, so there is one weapon and nothing to draw yet. */
    *shown = *state;
}
