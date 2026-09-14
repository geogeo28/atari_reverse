/* st_screen.h — the ST's screen geometry, defined once for everything built in this directory.
 *
 * TWO BUILDS READ IT AND THEY ARE NOT THE SAME PROGRAM: the ROM (romdefs.h, which includes this
 * file) paints a picture into a framebuffer it chose itself, and the conformance programs
 * (tostest/tosbench, through PRG_CFLAGS' include path) checksum the framebuffer TOS chose. Both are
 * talking about the same 32,000 bytes, so the number is stated here rather than spelled once per
 * build — a screen CRC taken over a SCREEN_BYTES that disagreed with the painter's row stride would
 * be a conformance failure with nothing wrong in either program.
 *
 * THE BYTE COUNT IS THE SAME IN BOTH COLOUR RESOLUTIONS an ST monitor boots into: low is 320x200
 * over four bitplanes, medium 640x200 over two, and 320*200*4/8 == 640*200*2/8 == 32,000. The
 * pixel-level constants below therefore describe LOW resolution specifically (which is what the
 * boot stub paints); SCREEN_BYTES is resolution-independent and is the one a program that only
 * wants to read the framebuffer should use.
 */
#ifndef TOS102US_ST_SCREEN_H
#define TOS102US_ST_SCREEN_H

#define SCREEN_WIDTH        320
#define SCREEN_HEIGHT       200
#define SCREEN_PLANES       4
#define SCREEN_PIXELS_PER_GROUP 16          /* one word per plane covers sixteen pixels           */
#define SCREEN_GROUPS_PER_ROW (SCREEN_WIDTH / SCREEN_PIXELS_PER_GROUP)      /* 20                 */
#define SCREEN_ROW_BYTES    (SCREEN_GROUPS_PER_ROW * SCREEN_PLANES * 2)     /* 160                */
#define SCREEN_BYTES        (SCREEN_ROW_BYTES * SCREEN_HEIGHT)              /* 32,000             */

#endif /* TOS102US_ST_SCREEN_H */
