/* bios/vt52.h — the BIOS console, for the two other files that reach into it.
 *
 * `src/bios/vt52.c` is the driver `Bconout(CON:)` and `Bconout(RAW:)` jump into, and
 * `src/bios/conout_glyph.c` is the four screen routines it reaches through the RAM vectors at
 * `CON_VECTOR_*`. They are two files because they are two layers of the ROM: everything here reads
 * and writes the console's own state block, and everything there writes SCREEN MEMORY and nothing
 * else.
 *
 * Deliberately not an inventory of either: what is declared is what ANOTHER translation unit calls,
 * so the compiler checks the calls the ROM itself makes across this seam — plus the cursor cell
 * inversion at the bottom, which is INLINE because `src/bios/vbl.c`'s 200 Hz blink is its other
 * caller and the note beside it has the measurement.
 */
#ifndef TOS102US_VT52_H
#define TOS102US_VT52_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"

/* ---- the driver ($fc42f2 and $fc42e6), for `src/bios/bcon.c`'s Bconout dispatch ---------------- */

/* $fc42f2 — one character through the VT52 state machine. `entry_d0` is the D0 the trap dispatcher
 * left, because most of the driver's arms never write D0 at all and the ones that do write only its
 * low word; the result is what `Bconout` hands back. */
uint32_t console_output(uint8_t *image, uint32_t entry_d0, uint16_t character);

/* $fc42e6 — the RAW console: the same glyph renderer with no state machine in front of it, so a
 * control code is drawn rather than obeyed. */
uint32_t console_output_raw(uint8_t *image, uint32_t entry_d0, uint16_t character);

/* ---- the cursor's lock, which is also XBIOS `Cursconf`'s two drawing arms --------------------- */

/* $fc45d8 — one more level of "do not draw the cursor", and the cell inverted back off the screen
 * if it is on it. `ESC f` and `Cursconf(0)` are both this routine, and the driver itself brackets
 * every screen change in it. */
void console_hide_cursor(uint8_t *image);

/* $fc45be — and back on, whatever depth the lock had reached: `ESC e` and `Cursconf(1)`. */
void console_show_cursor(uint8_t *image);

/* ---- the four screen routines ($fd141c / $fd149a / $fd14de / $fd1542) --------------------------
 *
 * Each is reached through a LONGWORD OF RAM (`CON_VECTOR_GLYPH` and its three neighbours), which is
 * what lets TOS 1.02 install its BLITTER variants on a machine that has one. Each function below
 * reads its own vector and HALTS on anything but the CPU routine the captured machine holds, the
 * same way `src/bios/bcon.c` reads the device tables rather than assuming them. */

/* The glyph's column in the font form and the screen cell it goes to, with the two colours as one
 * bit per plane (LSB first) — which is what the ROM has in A0/A1/D6/D7 at its `jsr (a5)`. */
void console_draw_glyph(uint8_t *image, uint32_t glyph, uint32_t cell,
                        uint16_t foreground, uint16_t background);

/* Everything from `row` down moves up one text row, and the LAST row is then cleared. */
void console_scroll_up(uint8_t *image, uint16_t row);

/* ...and the mirror: everything from `row` down moves down one, and `row` itself is cleared. */
void console_scroll_down(uint8_t *image, uint16_t row);

/* One rectangle of character cells, inclusive at both ends, filled with the background colour. */
void console_clear_cells(uint8_t *image, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2);

/* ---- the two pieces that are INLINE, because one of them is on the vertical blank --------------
 *
 * `$fc4a1e` has two callers — the console driver here and the cursor blink the VBL handler makes in
 * `src/bios/vbl.c` — and it is small, so it lives in the header rather than in one of the two `.c`
 * files. A definition in either would make the other pay a cross-file call for it, and that call is
 * NOT invisible: moving it out of `src/bios/vbl.c` cost the `isr_vbl / a frame with everything
 * queued` row 2400 -> 2552 cycles (measured 2026-09-19, `make bench`), which is a pinned row on the
 * handler that runs fifty times a second. One definition, no call. */

/* The bound on where a console screen write may land. Every address these routines compute comes out
 * of RAM the driver keeps, so a block holding nonsense walks off the image here — where the original
 * walks its own address space. HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there
 * is a process to abort"); on the machine there is nothing to assert against. */
static inline uint8_t *console_screen_byte(uint8_t *image, uint32_t at)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at < ST_RAM_BYTES);
#endif
    return image + at;
}

/* $fc4a1e — `not.b` down one column of every bit plane: the cursor cell, inverted in place.
 *
 * Two nested `dbf`s, so both counts are "the register plus one" and a zero count is a full 65,536
 * passes rather than none (`loop_passes`). The inner step is a SIGN-EXTENDED word add and the outer
 * is `addq.w #2,a1`, which on an address register is 32 bits wide whatever its suffix says — two
 * bytes because that is how far apart an ST's bit planes are, the words of one 16-pixel cell
 * sitting side by side. */
static inline void console_invert_cursor_cell(uint8_t *image, uint32_t cursor)
{
    uint16_t line_bytes = be16(image + CON_LINE_BYTES);
    unsigned rows = loop_passes(be16(image + CON_CELL_HEIGHT), COUNT_MASK_WORD);
    unsigned planes = loop_passes(be16(image + CON_PLANES), COUNT_MASK_WORD);

    while (planes-- != 0) {
        uint32_t at = cursor;
        unsigned row = rows;

        while (row-- != 0) {
            uint8_t *byte = console_screen_byte(image, at);

            *byte = (uint8_t)~*byte;
            at = addr_add(at, sign_ext16(line_bytes));
        }
        cursor = addr_add(cursor, SCREEN_PLANE_WORD_BYTES);
    }
}

#endif /* TOS102US_VT52_H */
