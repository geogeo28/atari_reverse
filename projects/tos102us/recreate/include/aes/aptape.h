/* aes/aptape.h — THE EVENT TAPE (`src/aes/aptape.c`, gemaplib's ap_tplay and ap_trecd): appl_trecord has forker copy
 * the queue entries it runs into the caller's buffer, appl_tplay queues them again.
 *
 *   $fe6766 ap_trecd(records, count)        forker's recorder armed over `records`; ev_timer(100) until it stops
 *                                           (the records full, or Control-\); each record's fork function turned
 *                                           into its NUMBER — D0.w: the records made
 *   $fe6610 ap_tplay(records, count, scale) each record's number turned back into its fork function and queued, a
 *                                           yield after each; a timer record WAITED OUT (ev_timer) instead, its
 *                                           ticks scaled; the VDI's cursor and motion routines displaced from the
 *                                           first mouse record on, and put back at the end
 *
 * A RECORD is a fork-queue entry (`aes/aes.h`: FORK_CODE, FORK_DATA, FORK_ENTRY_BYTES). While a recording runs its
 * code is the fork function's ADDRESS, as forker copied it; ap_trecd leaves a NUMBER there — the format an
 * application sees, and the one ap_tplay reads.
 *
 * ALCYON C, each entered by a Line-F call over its caller's frame; their callers are the AES's own arms (band 5).
 */
#ifndef TOS102US_AES_APTAPE_H
#define TOS102US_AES_APTAPE_H

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "staged_call.h"
#endif
#include "addrs.h"
#include "aes/evfork.h"

/* ---- a record's NUMBER: what ap_trecd leaves for a fork function, and ap_tplay's switch reads ---------------------- */
#define TAPE_TIMER            0          /* tchange: its data the ticks         ($fe67de clr.l d4; $fe66f8 tst.w) */
#define TAPE_BUTTON           1          /* bchange                             ($fe6808 moveq #1; $fe66fe)     */
#define TAPE_MOUSE            2          /* mchange                             ($fe67ec moveq #2; $fe6704)     */
#define TAPE_KEY              3          /* kchange                             ($fe67fa moveq #3; $fe670a)     */

/* ---- ap_trecd -------------------------------------------------------------------------------------------------------- */
/* How long ap_trecd sleeps between two looks at the recorder's flag. */
#define TRECD_POLL_MS         100        /* ($fe6790 move.l #100,(sp))                                           */

/* ---- ap_tplay -------------------------------------------------------------------------------------------------------- */
/* A timer record's ticks are waited out as ticks * this / scale MILLISECONDS — the ROM's arithmetic, kept: at a scale
 * of 100 that is ONE millisecond a recorded tick, a twentieth of the tick's own 20 ms (AES_GL_TICK_MS), and only a
 * scale of 5 waits as long as was recorded. */
#define TPLAY_SCALE_UNIT      100        /* ($fe6666 move.l #100,-(sp))                                          */
/* The motion routine ap_tplay displaced from the VDI (vex_motv) for the length of a playback with a mouse record:
 * the cursor routine's twin is AES_DRWADDR (`aes/gsxif.h`), which drawrat calls. Written and read by ap_tplay alone. */
#define AES_PLAY_OLD_MOTION   0x9bbc     /* long                                ($fe66ca move.l #$9bbc,(sp))     */
/* Where the mouse was when a playback began (GEM's gl_mx, gl_my). Stored by ap_tplay, read by NOTHING in this ROM. */
#define AES_PLAY_FROM_X       0xc852     /* word                                ($fe662c move.w $9c0c,$c852)     */
#define AES_PLAY_FROM_Y       0xc854     /* word                                ($fe6636 move.w $9c0e,$c854)     */

#ifndef __ASSEMBLER__
void aes_ap_tplay(uint8_t *image, uint32_t records, int16_t count, int16_t scale);                    /* $fe6610 */
uint16_t aes_ap_trecd(uint8_t *image, uint32_t records, int16_t count);                               /* $fe6766 */

#ifndef RECREATE_HOST_DIFFERENTIAL
/* justretf on target (`src/aes/irq.S`): the routine that draws nothing, handed to the VDI by address. */
void aes_rom_justretf(void);                                                                          /* $fed424 */
#endif

/* mchange's CODE, as a queue entry holds it (`aes/evfork.h`: the other three). Only a playback queues it from C —
 * the motion glue queues it everywhere else. */
static inline uint32_t fork_mchange(void)
{
    return ALCYON_ROUTINE(AES_ROM_MCHANGE, aes_mchange_fork);
}

/* The routine a playback hands the VDI as its cursor and its motion routine: a bare `rts`. */
static inline uint32_t draws_nothing(void)
{
    return ALCYON_ROUTINE(AES_ROM_JUSTRETF, aes_rom_justretf);
}
#endif

#endif /* TOS102US_AES_APTAPE_H */
