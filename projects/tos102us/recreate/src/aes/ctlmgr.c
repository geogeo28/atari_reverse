/* ctlmgr.c — the SCREEN MANAGER's process (`aes/gemctrl.h`): ctlmgr, its main loop, and ictlmgr, which makes it. Alcyon C
 * in the ROM (gemctrl's last two routines), ported over its own order; every callee is its C core, the main wait
 * reached through the event door (`aes/evdoor.h`) as every wait above the event layer is.
 *
 * WHY A FILE OF ITS OWN, beside `gemctrl.c`. In one translation unit GCC splits hctl_rect for its new caller (a
 * `.part.0`: the test of the menu inlined into the loop) and inlines hctl_button into it — the handlers' own code
 * and every cycle pinned on their rows would move with a caller's arrival. Here they are calls, as the ROM's are.
 *
 * ctlmgr NEVER RETURNS, AND IS ENTERED BY NO CALL: psetup lays a frame on the process's empty stack and switchto's
 * `rte` pops it — no return address under the entry, no argument, nothing in any register.
 *   ON TARGET it is one function, `aes_rom_ctlmgr`, the address ictlmgr hands pstart. ITS FRAME IS WHAT THE PROCESS
 *   PAYS FOR EVER — everything the screen manager does is stacked under it, on a stack of 1,196 usable bytes — so it
 *   is held to the ROM's own 24 (`link a6,#-12` + two registers; `test_aes_gemctrl.py` reads ours off both blobs):
 *     - no thunk and no parameter: the image base comes through a register (`target_image`), as the fork functions'
 *       entries take theirs — a pushed 0 and a `jsr` would be eight bytes more, for good;
 *     - the answers are read as the locals they are (`host_slot_load_words`): read back through the image they cost
 *       two address registers kept across the loop, and a function that never returns still saves what it uses;
 *     - the multi-click count is stepped by a routine of its own (not inlined: the word's address would be a third);
 *     - `no-function-cse`: at -O2 GCC keeps every callee's address in a call-saved register across the loop — six
 *       saved registers and 36 bytes with it, three and 24 without (measured, GCC 16.1).
 *     - `no-defer-pop` (`stack_diet.h`, where both marks are spelt and guarded): at -O2 a call's arguments stay on
 *       the stack under the next call — eight dead bytes under hctl_button and hctl_rect, so under every chain of
 *       the process: 44 held over a handler with them, 36 without (the frame diet, 2026-10-10).
 *   OFF TARGET there is no stack to enter and nothing to come back from a loop: the same two parts are two calls that
 *   return — `aes_ctlmgr_begins`, and `aes_ctlmgr_turn`, one turn from the loop's top to the next arrival there.
 *
 * THE HOST RUNS ONE PROCESS'S C (`host_slot.h`, THE AUDIT): its caller's. The model's scheduler enters any other
 * process as the ROM's own code, so the screen manager's C runs on the host only where the screen manager IS the
 * caller. An entry made INSIDE THE DISPATCHER — the model's process hook bound to "resume" the screen manager in C
 * while another process's C sits parked under it — is refused by name here, where it would begin.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "host_slot.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/evasync.h"
#include "aes/evdoor.h"
#include "aes/evinput.h"
#include "aes/gemctrl.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/pdpipe.h"
#include "aes/rect.h"
#include "aes/wmupdate.h"

_Static_assert(CTL_WAIT_EVENTS == (EV_MU_KEYBD | EV_MU_BUTTON | EV_MU_M1), "the main wait: a key, a button, the bar");
_Static_assert(HOST_SLOT_AES_CTLMGR_ANSWERS_BYTES == EV_MULTI_ANSWER_WORDS * sizeof(uint16_t), "the answers, their slot");

/* The main wait's button ($fe49fe): one click of the left button going down, no other held. */
#define CTL_WAIT_BUTTON       EV_BUTTON_PARAMETER(CTL_WAIT_CLICKS, CTL_WAIT_BUTTON_MASK, CTL_WAIT_BUTTON_STATE)

/* $fe4a2c / $fe4a4a — one multi-click wait counted off, never the last: gl_bpend one lower while it is above one (a
 * signed word, as the ROM's `ble` reads it). NOT INLINED: the frame above (this file's head). */
static __attribute__((noinline)) void a_pending_click_wait_counted_off(uint8_t *image)
{
    if (global_word(image, AES_GL_BPEND) > CTL_BPEND_KEPT)
        wr16(image + AES_GL_BPEND, (uint16_t)(be16(image + AES_GL_BPEND) - 1));
}

/* $fe49da..$fe49ea — THE ONCE-ONLY PART: the menu bar's rectangle is the active one until a menu says otherwise, and
 * the screen manager waits for the mouse to ENTER it — the copy first, then the word. */
static inline __attribute__((always_inline)) void ctlmgr_begins(uint8_t *image)
{
    aes_rc_copy(image, AES_GL_RMENU, AES_GL_RMNACTV);
    wr16(image + AES_GL_CTWAIT_LEAVE, 0);
}

/* $fe49f2..$fe4a66 — ONE TURN. `answers`: where the six answer words are, as an image address — `answers_local`
 * itself on target. The button's handler runs before the bar's, each over the mouse the wait answered; with neither
 * (a key) the lock is taken and let go round nothing. */
static inline __attribute__((always_inline)) void ctlmgr_turn(uint8_t *image, uint32_t answers, uint16_t *answers_local)
{
    uint16_t events;

    aes_w_setactive(image);
    events = evdoor_ev_multi(image, CTL_WAIT_EVENTS, AES_GL_CTWAIT_LEAVE, AES_GL_CTWAIT_LEAVE, CTL_WAIT_NONE,
                             CTL_WAIT_BUTTON, CTL_WAIT_NONE, answers);
    host_slot_load_words(image, answers, answers_local, EV_MULTI_ANSWER_WORDS);
    (void)aes_wm_update(image, WM_BEG_UPDATE);
    if (events & EV_MU_BUTTON) {
        a_pending_click_wait_counted_off(image);
        aes_hctl_button(image, (int16_t)answers_local[CTL_ANSWER_MOUSE_X], (int16_t)answers_local[CTL_ANSWER_MOUSE_Y]);
    }
    if (events & EV_MU_M1) {
        a_pending_click_wait_counted_off(image);
        aes_hctl_rect(image, (int16_t)answers_local[CTL_ANSWER_MOUSE_X], (int16_t)answers_local[CTL_ANSWER_MOUSE_Y]);
    }
    (void)aes_wm_update(image, WM_END_UPDATE);
}

#ifdef RECREATE_HOST_DIFFERENTIAL
/* A host entry of the screen manager's C is its CALLER's, never a resume (this file's head). WHAT IS TESTED IS THE
 * DISPATCHER'S GUARD, and no more: it is set from savestate to switchto, where no process runs — and that is where the
 * model's process hook stands when it would "resume" one. (Who is running is not asked: the hook is called with the
 * process to enter already at the ready list's head.) */
static void refuse_an_entry_inside_the_dispatcher(const uint8_t *image)
{
    if (image[AES_INDISP])
        recreate_not_reconstructed("ctlmgr entered inside the dispatcher (its guard, AES_INDISP, is set): no process "
                                   "runs there — this is the screen manager's C entered from the model's process "
                                   "hook while the caller's C is parked under it, and the host runs ONE process's C "
                                   "(host_slot.h, THE AUDIT)");
}

void aes_ctlmgr_begins(uint8_t *image)
{
    refuse_an_entry_inside_the_dispatcher(image);
    ctlmgr_begins(image);
}

void aes_ctlmgr_turn(uint8_t *image)
{
    uint16_t answers_local[EV_MULTI_ANSWER_WORDS];
    uint32_t answers;

    refuse_an_entry_inside_the_dispatcher(image);
    answers = host_slot_claim(AES_CTLMGR_ANSWERS, answers_local);
    ctlmgr_turn(image, answers, answers_local);
    host_slot_release(AES_CTLMGR_ANSWERS);
}
#else
/* $fe49d2 — ctlmgr, over the target's image base (`staged_call.h`'s `target_image`). `no-function-cse`: the frame (this
 * file's head); `no-defer-pop`: what it holds over a handler. GCC documents `optimize` as a debugging aid, not for
 * production code — it is taken here for two flags that change no semantics, only which registers the loop keeps and
 * when a call's arguments are popped, and what they buy is HELD, not trusted: `test_aes_gemctrl.py`'s
 * `test_the_entry_s_own_frame_is_no_more_than_the_rom_s` reads the frame off both blobs and reds at 25 bytes (a GCC
 * that stops honouring the attribute builds 36), and `test_stack_diet.py` holds every mark of `stack_diet.h`. */
FRAME_DIET("no-function-cse", "no-defer-pop")
__attribute__((noreturn)) void aes_rom_ctlmgr(void)
{
    uint8_t *const image = target_image();
    uint16_t answers_local[EV_MULTI_ANSWER_WORDS];

    ctlmgr_begins(image);
    for (;;)
        ctlmgr_turn(image, host_slot_claim(AES_CTLMGR_ANSWERS, answers_local), answers_local);
}
#endif

/* The address the screen manager's process begins at, and is "loaded" at: the ROM's own ctlmgr off target — a code
 * address used as a value, twice (`test/test_aes_rom_data.py`, CODE) — and the build's entry on target. */
static inline uint32_t the_screen_manager_s_entry(void)
{
    return ALCYON_ROUTINE(AES_ROM_CTLMGR, aes_rom_ctlmgr);
}

/* $fe4a6a — ictlmgr: the desk menu has no accessory entry yet (gl_dacnt, gl_dafirst); the screen manager's process
 * made, to begin at ctlmgr. Answers its PD (pstart's: gem_main keeps it as ctl_pd, and as the first owner of the mouse
 * and of the keys — $fda1de..$fda1ea). */
uint32_t aes_ictlmgr(uint8_t *image, int16_t pid)
{
    (void)pid;                                  /* gem_main's push ($fda1d8): read by nothing */
    wr16(image + AES_GL_DACNT, 0);
    wr16(image + AES_GL_DAFIRST, 0);
    return aes_pstart(image, the_screen_manager_s_entry(), AES_SCRENMGR_NAME, the_screen_manager_s_entry());
}
