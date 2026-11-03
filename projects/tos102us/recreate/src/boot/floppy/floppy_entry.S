/* floppy_entry.S — where the floppy's lower driver in C (`floppy.c`) is entered and left, and the settle it waits in:
 * the three things C cannot say.
 *
 * THE ENTRY (`floppy_probe_entry`, reached by the `jmp` laid at the ROM's $fc173a, R-P4-2): the CALLER's D3-D7 / A3-A6
 * saved to $a28 by the ROM's own `movem` — the common entry's first instruction ($fc1c48); the 36 bytes are the
 * caller's registers, which the B6 end surface reads (D6's low byte at $a37, hdv_boot's A6 at $a48) — then the C,
 * the caller's arguments at A0.
 *
 * THE TAIL (`floppy_leave`, the ROM's $fc1cf2..$fc1d26 with the C's result in D0): the drive's last-access long stamped
 * with `_hz_200` (drive B:'s too on a single-drive machine), the caller's registers restored FROM $a28, `flock`
 * cleared. A0 is left at $9fc and the flags as the ROM leaves them: X the `lsl.w`'s last bit out, then `clr.w`'s Z.
 *
 * THE SETTLE (`floppy_settle`, the ROM's $fc1eac byte for byte): 33 `dbf`s around every access of the FDC's registers.
 */
#include "addrs.h"
#include "boot/sysvars.h"
#include "boot/floppy.h"

#define LAST_ACCESS_SHIFT 2     /* `lsl.w #2,d0`: a drive's long in the last-access table */
#define DRIVE_B_LAST_ACCESS 4   /* `move.l ...,4(a0)`: drive B:'s long, stamped too where one drive was counted */

    .text
    .globl  floppy_probe_entry
    .type   floppy_probe_entry,@function
floppy_probe_entry:
    movem.l %d3-%d7/%a3-%a6,(FLOPPY_SAVE_AREA).l
    lea     4(%sp),%a0                  /* the caller's arguments, past its return */
    bsr.w   floppy_probe            /* ...and on into the tail: D0 the result */
    .size   floppy_probe_entry,.-floppy_probe_entry

    .globl  floppy_leave
    .type   floppy_leave,@function
floppy_leave:
    move.l  %d0,-(%sp)
    move.w  (FLOPPY_DRIVE).l,%d0
    lsl.w   #LAST_ACCESS_SHIFT,%d0
    lea     (FLOPPY_LAST_ACCESS).l,%a0
    move.l  (SYSVAR_HZ_200).w,(0,%a0,%d0.w)
    cmpi.w  #1,(SYSVAR_NFLOPS).l
    bne.s   1f
    move.l  (SYSVAR_HZ_200).w,DRIVE_B_LAST_ACCESS(%a0)
1:  move.l  (%sp)+,%d0
    movem.l (FLOPPY_SAVE_AREA).l,%d3-%d7/%a3-%a6
    clr.w   (SYSVAR_FLOCK).l
    rts
    .size   floppy_leave,.-floppy_leave

    .globl  floppy_settle
    .type   floppy_settle,@function
floppy_settle:
    move.w  %sr,-(%sp)
    move.w  %d7,-(%sp)
    move.w  #FDC_SETTLE_DBF,%d7
1:  dbf     %d7,1b
    move.w  (%sp)+,%d7
    move.w  (%sp)+,%sr
    rts
    .size   floppy_settle,.-floppy_settle
