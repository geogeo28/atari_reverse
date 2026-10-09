/* aptape.c — THE EVENT TAPE (`aes/aptape.h`): gemaplib's ap_tplay and ap_trecd. Alcyon C in the ROM, ported over its
 * own order.
 *
 * BOTH LEAVE BY THE DISPATCHER. ap_tplay YIELDS (a bare dsptch) once before its first record and once after each —
 * that yield is what runs the fork function it has just queued, forker's `jsr` — and WAITS a timer record out
 * (ev_timer). ap_trecd sleeps in ev_timer(100) for as long as forker's recorder is running: the recorder's three
 * words are forker's between two instructions of any process, so ap_trecd writes and reads them inside the mask
 * bracket, as the ROM does, and reads the flag again on every turn of its loop.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/aptape.h"
#include "aes/evfork.h"
#include "aes/evlib.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/strings.h"
#include "aes/switch.h"

/* A longword of a record AS ap_tplay TAKES IT: the ROM copies each record into a local a BYTE at a time (lbcopy,
 * $fe6650) before it reads it, so a recording at an odd address plays. */
static inline uint32_t record_long(const uint8_t *image, uint32_t at)
{
    return (uint32_t)bus_byte(image, at) << 24 | (uint32_t)bus_byte(image, at + 1) << 16
           | (uint32_t)bus_byte(image, at + 2) << 8 | bus_byte(image, at + 3);
}

/* One of the VDI's routines exchanged for `routine` (vex_curv, vex_motv): what it displaced is then contrl[9..10]. */
static inline void vex(uint8_t *image, int16_t opcode, uint32_t routine)
{
    aes_set_contrl_ptr(image, routine);
    (void)aes_gsx_ncode(image, opcode, GSX_NO_POINTS, GSX_NO_WORDS);
}

/* The first mouse record of a playback ($fe6696..$fe66d0): the VDI's cursor routine and its motion routine each
 * displaced by the one that draws nothing, and kept — the cursor routine where drawrat calls it (mchange MOVES the
 * mouse itself while a recording plays, `evfork.c`). */
static inline void take_the_mouse(uint8_t *image)
{
    vex(image, VDI_ROM_VEX_CURV_OPCODE, draws_nothing());
    aes_get_contrl_ptr2(image, AES_DRWADDR);
    vex(image, VDI_ROM_VEX_MOTV_OPCODE, draws_nothing());
    aes_get_contrl_ptr2(image, AES_PLAY_OLD_MOTION);
}

/* ...and both put back when the playback ends ($fe6736..$fe675a). */
static inline void give_the_mouse_back(uint8_t *image)
{
    vex(image, VDI_ROM_VEX_CURV_OPCODE, be32(image + AES_DRWADDR));
    vex(image, VDI_ROM_VEX_MOTV_OPCODE, be32(image + AES_PLAY_OLD_MOTION));
}

/* A timer record WAITED OUT: its ticks * 100 / `scale` milliseconds, the two longs through the Alcyon runtime
 * (lmul, then ldiv — whose remainder lands in AES_LDIV_REMAINDER; a `scale` of 0 is ldiv's own divide by zero). */
static inline void wait_out(uint8_t *image, uint32_t ticks, int16_t scale)
{
    (void)aes_ev_timer(image, aes_ldiv(image, aes_lmul((int32_t)ticks, TPLAY_SCALE_UNIT), scale));
}

/* The fork function a record's `number` stands for — what is queued for it — or 0 for a timer record, which is
 * waited out here instead and queues nothing. THE NUMBER IS THE CODE'S LOW WORD: the ROM switches on a `tst.w` and
 * three `cmp.w` of the longword ($fe66f8..$fe670a), so $00050002 is a mouse record, and a longword whose low word
 * is none of the four is QUEUED AS IT IS — a code address of the caller's making. */
static inline uint32_t played(uint8_t *image, uint32_t number, uint32_t data, int16_t scale)
{
    switch ((int16_t)number) {
    case TAPE_TIMER:
        wait_out(image, data, scale);
        return 0;
    case TAPE_BUTTON:
        return fork_bchange();
    case TAPE_MOUSE:
        if (!be16(image + AES_GL_PLAY))
            take_the_mouse(image);
        wr16(image + AES_GL_PLAY, 1);
        return fork_mchange();
    case TAPE_KEY:
        return fork_kchange();
    default:
        return number;
    }
}

/* $fe6610 — ap_tplay (appl_tplay): `count` records at `records` played back at `scale`. A yield first; where the
 * mouse is noted; then each record's fork function queued (forkq) and a yield, which runs it. A playback that met
 * a mouse record ends by handing the VDI its two routines back. A `count` of 0 or less plays nothing — after the
 * first yield. Sets no D0. */
void aes_ap_tplay(uint8_t *image, uint32_t records, int16_t count, int16_t scale)
{
    int16_t record;

    aes_dsptch(image);
    wr16(image + AES_GL_PLAY, 0);
    wr16(image + AES_PLAY_FROM_X, be16(image + AES_XRAT));
    wr16(image + AES_PLAY_FROM_Y, be16(image + AES_YRAT));
    for (record = 0; record < count; record++) {
        uint32_t number = record_long(image, records + FORK_CODE);
        uint32_t data = record_long(image, records + FORK_DATA);
        uint32_t code;

        records += FORK_ENTRY_BYTES;
        code = played(image, number, data, scale);
        if (code)
            aes_forkq(image, code, data);
        aes_dsptch(image);
    }
    if (be16(image + AES_GL_PLAY)) {
        give_the_mouse_back(image);
        wr16(image + AES_GL_PLAY, 0);
    }
}

/* A recorded fork function's NUMBER ($fe67ca..$fe6808: the ROM's four compares, tchange's first, over a number
 * cleared before them — so a code that is none of the four is a timer's too). */
static inline uint32_t tape_number(uint32_t code)
{
    if (code == fork_tchange())
        return TAPE_TIMER;
    if (code == fork_mchange())
        return TAPE_MOUSE;
    if (code == fork_kchange())
        return TAPE_KEY;
    if (code == fork_bchange())
        return TAPE_BUTTON;
    return TAPE_TIMER;
}

/* $fe6766 — ap_trecd (appl_trecord): forker's recorder armed over `count` records at `records`, the interrupts
 * masked; a sleep of 100 ms at a time until the recorder has stopped itself; then, masked again, the recorder
 * disarmed and the records it made counted — the cursor's distance as a WORD, a signed divide by a record's
 * bytes. Each record's code is then its fork function's number. Answers the count. */
uint16_t aes_ap_trecd(uint8_t *image, uint32_t records, int16_t count)
{
    int16_t recorded, record;

    aes_spl7_save(image);
    wr16(image + AES_GL_RECD, 1);
    wr16(image + AES_RECORD_LEFT, (uint16_t)count);
    wr32(image + AES_RECORD_CURSOR, records);
    aes_spl_restore(image);
    while (word_read_again(image, AES_GL_RECD))
        (void)aes_ev_timer(image, TRECD_POLL_MS);
    aes_spl7_save(image);
    wr16(image + AES_GL_RECD, 0);
    wr16(image + AES_RECORD_LEFT, 0);
    recorded = (int16_t)((int16_t)(uint16_t)(be32(image + AES_RECORD_CURSOR) - records) / FORK_ENTRY_BYTES);
    wr32(image + AES_RECORD_CURSOR, 0);
    aes_spl_restore(image);
    for (record = 0; record < recorded; record++) {
        set_bus_long(image, records, tape_number(bus_long(image, records)));
        records += FORK_ENTRY_BYTES;
    }
    return (uint16_t)recorded;
}
