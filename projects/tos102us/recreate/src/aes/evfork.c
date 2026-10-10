/* evfork.c — THE FORK QUEUE and what runs off it (`aes/evfork.h`): gemdisp's forkq, forker and chkkbd, geminput's
 * four fork functions (kchange, bchange, mchange, tchange) and the call of the saved cursor routine mchange makes
 * (drawrat). Alcyon C in the ROM but drawrat, four hand instructions; ported over its own order.
 *
 * Every read is where the ROM makes it: the queue's head, tail and count are counted IN MEMORY, one instruction each
 * on target (`m68k_idioms.h`, `add_word_in_memory`: an interrupt's forkq lands between forker's and forkq's own
 * instructions on the machine — and forkq's own race with it, the tail read ($fe4b2c) six instruction boundaries
 * before it is counted ($fe4b44), is the ROM's, kept); an index is a WORD shifted and then sign-extended; a global the ROM reads again after a call is
 * read again here, and one an interrupt writes is read again wherever the ROM does (`word_read_again`).
 * `test/test_aes_evfork_interrupted.py` holds both: which instruction changes each shared word (forkq, forker, mchange
 * here; b_click and b_delay in evinput.c), and the ROM's interrupts taken at every instruction boundary of those five
 * — NOT of chkkbd, kchange, bchange or tchange, which count no word of the interrupts' (tchange's two stores are
 * inside its spl7 bracket: the mask's, no sweep's).
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/evasync.h"
#include "aes/evfork.h"
#include "aes/evinput.h"
#include "aes/fmlib.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/switch.h"
#include "aes/wmupdate.h"

/* The queue entry a head or tail index names: `asl.w #3` — the WORD shifted — then `ext.l`, added to the queue's
 * address ($fe4b32, $fe4bf6). */
static inline uint32_t fork_entry(uint16_t index)
{
    return AES_FORK_QUEUE + (uint32_t)(int32_t)(int16_t)(uint16_t)(index * FORK_ENTRY_BYTES);
}

/* A head or tail index moved on one entry, round the ring — counted in memory, as the ROM counts it. */
static inline void advance(uint8_t *image, uint32_t index_at)
{
    add_word_in_memory(image, index_at, 1);
    if (be16(image + index_at) == AES_FORK_ENTRIES)
        wr16(image + index_at, 0);
}

/* $fe4b1a — forkq: a fork function and its data at the queue's tail, for forker — or, with the queue full, NOTHING:
 * the entry is dropped and its caller never told. */
void aes_forkq(uint8_t *image, uint32_t code, uint32_t data)
{
    uint32_t entry;

    if (global_word(image, AES_FORK_COUNT) >= AES_FORK_ENTRIES)
        return;
    entry = fork_entry(be16(image + AES_FORK_TAIL));
    advance(image, AES_FORK_TAIL);
    set_bus_long(image, entry + FORK_CODE, code);
    set_bus_long(image, entry + FORK_DATA, data);
    add_word_in_memory(image, AES_FORK_COUNT, 1);
    image[AES_FORK_POSTED] = 1;
}

/* appl_trecord's recorder ($fe4c1e..$fe4cb2): the entry forker is about to run, copied to the record's cursor — a
 * tick's elapsed time added to the tick recorded just before it instead — until the records run out or Control-\ is
 * typed (which is not recorded). The cursor is read from memory for every use. */
static inline void record(uint8_t *image, uint32_t entry)
{
    if (bus_long(image, entry + FORK_CODE) == fork_kchange()
        && (bus_long(image, entry + FORK_DATA) & RECORD_KEY_MASK) == (uint32_t)RECORD_END_KEY << HIGH_WORD_SHIFT)
        wr16(image + AES_GL_RECD, 0);
    if (!be16(image + AES_GL_RECD))
        return;
    if (bus_long(image, entry + FORK_CODE) == fork_tchange()
        && bus_long(image, be32(image + AES_RECORD_CURSOR) - FORK_ENTRY_BYTES + FORK_CODE) == fork_tchange()) {
        uint32_t ticks = bus_long(image, be32(image + AES_RECORD_CURSOR) - FORK_ENTRY_BYTES + FORK_DATA)
                         + bus_long(image, entry + FORK_DATA);

        set_bus_long(image, be32(image + AES_RECORD_CURSOR) - FORK_ENTRY_BYTES + FORK_DATA, ticks);
        return;
    }
    aes_lbcopy(image, be32(image + AES_RECORD_CURSOR), entry, FORK_ENTRY_BYTES);
    wr32(image + AES_RECORD_CURSOR, be32(image + AES_RECORD_CURSOR) + FORK_ENTRY_BYTES);
    wr16(image + AES_RECORD_LEFT, (uint16_t)(be16(image + AES_RECORD_LEFT) - 1));
    wr16(image + AES_GL_RECD, be16(image + AES_RECORD_LEFT));
}

/* VDI 33 (vsin_mode): the input `device` put in SAMPLE mode — chkkbd's keyboard, mchange's locator while a
 * recording plays. */
static inline void sampled(uint8_t *image, uint16_t device)
{
    wr16(image + GSX_INTIN_WORD(0), device);
    wr16(image + GSX_INTIN_WORD(1), VSIN_SAMPLE_MODE);
    aes_gsx_ncode(image, VDI_ROM_VSIN_MODE_OPCODE, GSX_NO_POINTS, VSIN_MODE_WORDS);
}

/* $fe4bc6 — forker: the queue run dry — each entry counted out, its index moved on, recorded while a recording
 * runs, and its fork function CALLED over its data (`staged_call.h`, THE FORK HOOK) — with no process running
 * (`rlr` -1, put back after) and AES_FORKER_BUSY set. A fork function that queues more is served in the same run. */
void aes_forker(uint8_t *image)
{
    uint32_t interrupted = be32(image + AES_RLR);

    image[AES_FORKER_BUSY] = 1;
    wr32(image + AES_RLR, AES_RLR_IN_FORKER);
    while (be16(image + AES_FORK_COUNT)) {
        uint32_t entry;

        sub_word_in_memory(image, AES_FORK_COUNT, 1);
        entry = fork_entry(be16(image + AES_FORK_HEAD));
        advance(image, AES_FORK_HEAD);
        if (be16(image + AES_GL_RECD))
            record(image, entry);
        (void)call_alcyon_pointer(image, bus_long(image, entry + FORK_CODE), bus_long(image, entry + FORK_DATA));
    }
    wr32(image + AES_RLR, interrupted);
    image[AES_FORKER_BUSY] = 0;
}

/* $fe4cd6 — chkkbd: the keyboard POLLED through the VDI. The shift keys (vq_key_s); then, only while the keyboard's
 * owner's key queue has room, one key sampled (vsin_mode: the string device, sample; vsm_string: one key, no echo —
 * a key came if the VDI answered a word). A key, or shift keys that changed, is queued for kchange. */
void aes_chkkbd(uint8_t *image)
{
    int16_t shift_keys, key = 0;

    aes_gsx_ncode(image, VDI_ROM_VQ_KEY_S_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    shift_keys = global_word(image, AES_GSX_INTOUT);
    if (signed_field(image, bus_long(image, be32(image + AES_GL_KOWNER) + PD_CDA), CDA_KEY_COUNT) < CQUEUE_ENTRIES) {
        sampled(image, VSIN_STRING_DEVICE);
        wr16(image + GSX_INTIN_WORD(0), (uint16_t)VSM_STRING_NO_ECHO);
        wr16(image + GSX_INTIN_WORD(1), 0);
        aes_gsx_ncode(image, VDI_ROM_STRING_OPCODE, GSX_NO_POINTS, VSM_STRING_WORDS);
        if (be16(image + AES_GSX_N_INTOUT))
            key = global_word(image, AES_GSX_INTOUT);
    }
    if (key || shift_keys != global_word(image, AES_KSTATE))
        aes_forkq(image, fork_kchange(), words_long(key, shift_keys));
}

/* $fe5180 — kchange: the shift keys noted, and a key (if one came with them) posted to the keyboard's owner. */
void aes_kchange(uint8_t *image, int16_t key, int16_t shift_keys)
{
    wr16(image + AES_KSTATE, (uint16_t)shift_keys);
    if (key)
        aes_post_keybd(image, be32(image + AES_GL_KOWNER), key);
}

/* $fe51d8 — bchange: the buttons are now `buttons`, after `clicks` clicks. A FIRST PRESS (the left button alone,
 * none down before) while the mouse is not the screen manager's re-decides whose the mouse is by where it is
 * (mowner): the control rectangle's owner's, the screen manager's, or the desktop window's owner's. Then the click
 * record — what the buttons, the clicks and the mouse WERE — and the event posted to the mouse's owner. */
void aes_bchange(uint8_t *image, int16_t buttons, int16_t clicks)
{
    if (be32(image + AES_GL_MOWNER) != be32(image + AES_CTL_PD) && buttons == BCHANGE_FIRST_PRESS
        && !be16(image + AES_BUTTON)) {
        int16_t where = aes_mowner(image, global_word(image, AES_XRAT), global_word(image, AES_YRAT));

        if (where == MOWNER_IN_CONTROL)
            wr32(image + AES_GL_MOWNER, be32(image + AES_GL_COWNER));
        else
            wr32(image + AES_GL_MOWNER, be32(image + (where == MOWNER_SCREEN_MANAGER ? AES_CTL_PD : AES_DESKTOP_OWNER)));
    }
    wr16(image + AES_MTRANS, (uint16_t)(be16(image + AES_MTRANS) + 1));
    wr16(image + AES_PR_BUTTON, be16(image + AES_BUTTON));
    wr16(image + AES_PR_MCLICK, be16(image + AES_MCLICK));
    wr16(image + AES_PR_XRAT, be16(image + AES_XRAT));
    wr16(image + AES_PR_YRAT, be16(image + AES_YRAT));
    wr16(image + AES_BUTTON, (uint16_t)buttons);
    wr16(image + AES_MCLICK, (uint16_t)clicks);
    aes_post_button(image, be32(image + AES_GL_MOWNER), global_word(image, AES_BUTTON), clicks);
}

/* $fed412 — drawrat: the cursor routine the AES saved (AES_DRWADDR) called as the VDI's mouse interrupt calls a
 * cursor routine — x in D0, y in D1, the words alone. A0 is the routine itself, as the ROM's `movea.l $947a,a0`
 * leaves it. */
void aes_drawrat(uint8_t *image, int16_t x, int16_t y)
{
    uint32_t registers[STAGED_REGISTERS];

    registers[STAGED_D0] = (uint16_t)x;
    registers[STAGED_D1] = (uint16_t)y;
    registers[STAGED_A0] = be32(image + AES_DRWADDR);
    call_vector_registers(image, registers[STAGED_A0], registers);
}

/* Whether the mouse has left the slop round (x, y) on one axis: the WORD difference, compared signed both ways. */
static inline int beyond_the_slop(uint16_t was, uint16_t is)
{
    int16_t moved = (int16_t)(uint16_t)(was - is);

    return moved > CLICK_SLOP || moved < -CLICK_SLOP;
}

/* $fe534c — mchange: the mouse moved. Where it is now is ASKED of the VDI (vq_mouse), not taken from the event; a
 * move beyond the slop ends an open click count at once (b_delay of all its ticks). While a recording is played
 * back the mouse is PUT at the event's point instead (vsin_mode: the locator, sample; the cursor routine; vsm_locator).
 * With no button down and a menu bar, the mouse crossing the screen manager's own rectangle hands it the mouse. Then
 * the mouse's owner is told (post_mouse). */
void aes_mchange(uint8_t *image, int16_t x, int16_t y)
{
    uint16_t now_x, now_y;

    aes_gsx_ncode(image, VDI_ROM_VQ_MOUSE_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    now_x = be16(image + AES_GSX_PTSOUT);
    now_y = be16(image + AES_GSX_PTSOUT + VDI_WORD_BYTES);
    if (be16(image + AES_GL_CLICK_TICKS)
        && (beyond_the_slop(be16(image + AES_XRAT), now_x) || beyond_the_slop(be16(image + AES_YRAT), now_y)))
        aes_b_delay(image, (int16_t)word_read_again(image, AES_GL_CLICK_TICKS));     /* $fe53be: the count as it is NOW */
    wr16(image + AES_XRAT, now_x);
    wr16(image + AES_YRAT, now_y);
    if (be16(image + AES_GL_PLAY)) {
        sampled(image, VSIN_LOCATOR_DEVICE);
        aes_drawrat(image, x, y);
        wr16(image + GSX_PTSIN_WORD(0), (uint16_t)x);
        wr16(image + GSX_PTSIN_WORD(1), (uint16_t)y);
        aes_gsx_ncode(image, VDI_ROM_LOCATOR_OPCODE, VSM_LOCATOR_POINTS, GSX_NO_WORDS);
        wr16(image + AES_XRAT, (uint16_t)x);
        wr16(image + AES_YRAT, (uint16_t)y);
    }
    if (!be16(image + AES_BUTTON) && be32(image + AES_GL_MNTREE)
        && aes_inside(image, global_word(image, AES_XRAT), global_word(image, AES_YRAT), AES_GL_RMNACTV)
           != global_word(image, AES_GL_CTWAIT_LEAVE))
        wr32(image + AES_GL_MOWNER, be32(image + AES_CTL_PD));
    aes_post_mouse(image, be32(image + AES_GL_MOWNER), global_word(image, AES_XRAT), global_word(image, AES_YRAT));
}

/* $fe4e02 — tchange: `elapsed` ticks have passed. The delay list holds DIFFERENCES: the first delay is counted down
 * by what is left of the ticks (which then carry on into the next); one run out — at or below 0, SIGNED — is cleared
 * and completed (evremove, answered 0), and the list read again from its head. Then, the interrupts masked, the tick
 * is re-armed with the first delay still waiting. */
void aes_tchange(uint8_t *image, uint32_t elapsed)
{
    uint32_t evb = be32(image + AES_DELAY_LIST);

    while (evb) {
        uint32_t carried = elapsed - bus_long(image, evb + EVB_PARM);

        set_bus_long(image, evb + EVB_PARM, bus_long(image, evb + EVB_PARM) - elapsed);
        elapsed = carried;
        if ((int32_t)bus_long(image, evb + EVB_PARM) > 0)
            break;
        set_bus_long(image, evb + EVB_PARM, 0);
        aes_evremove(image, evb, 0);
        evb = be32(image + AES_DELAY_LIST);
    }
    aes_spl7_save(image);
    if (evb)
        arm_the_tick(image, bus_long(image, evb + EVB_PARM));
    aes_spl_restore(image);
}

#ifndef RECREATE_HOST_DIFFERENTIAL
/* THE FORK FUNCTIONS' ENTRIES (`aes/evfork.h`): forker's pushed longword taken apart as the ROM's function reads its
 * frame — two words, the first the high — over the target's image base, 0, handed through a register GCC cannot see
 * into (`staged_call.h`'s `target_image`). */
void aes_kchange_fork(uint32_t data)
{
    aes_kchange(target_image(), pair_high(data), pair_low(data));
}

void aes_bchange_fork(uint32_t data)
{
    aes_bchange(target_image(), pair_high(data), pair_low(data));
}

void aes_mchange_fork(uint32_t data)
{
    aes_mchange(target_image(), pair_high(data), pair_low(data));
}

void aes_tchange_fork(uint32_t data)
{
    aes_tchange(target_image(), data);
}
#endif
