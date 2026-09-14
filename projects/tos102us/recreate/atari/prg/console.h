/* console.h — the VT52 console the two conformance programs write through, and the one escape
 * sequence they both have to send before they draw or time anything.
 *
 * THE CURSOR IS TURNED OFF FIRST, IN BOTH PROGRAMS, FOR TWO DIFFERENT REASONS — which is exactly
 * why the sequence lives here and not in either of them. TOS's VT52 cursor BLINKS off the vertical
 * blank, so for TOSTEST a screen CRC taken with it enabled is a coin flip on where in the blink
 * phase the capture landed, and for TOSBENCH the blink is per-character work whose amount depends
 * on when the workload started. One `ESC f` removes both; two copies of it would be two things to
 * get right the day a third program is added.
 */
#ifndef TOS102US_CONSOLE_H
#define TOS102US_CONSOLE_H

#include "tosapi.h"

#define VT52_ESC        27
#define VT52_CURSOR_OFF 'f'

static inline void console_cursor_off(void)
{
    Bconout(BCON_DEV_CON, VT52_ESC);
    Bconout(BCON_DEV_CON, VT52_CURSOR_OFF);
}

#endif /* TOS102US_CONSOLE_H */
