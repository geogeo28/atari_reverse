/* evdisp.c — THE DISPATCHER'S C (`aes/evdisp.h`): gemdisp's disp_act, mwait_act and idle — Alcyon C in the ROM, C on
 * both builds — and, OFF TARGET ONLY, the model of what has no C spelling: disp over savestate and switchto.
 *
 * Every read is where the ROM makes it. The three lists are walked through the 32 bits the ROM carries (a link is
 * tested as a longword, `move.l a4,d0`), a list's head is read again for every use (`movea.l $9c16,a5`, then
 * `move.l (a5),$9c16`), and idle tests the ready list BEFORE the fork queue's count ($fe4d8c, $fe4d94) — the count
 * is a word the interrupts count too (`aes/evfork.h`), read once a turn, in memory.
 *
 * THE MODEL keeps the ROM's structure: disp's own statements in its own order, savestate and
 * switchto as two functions that do to the IMAGE what the ROM's do, less what is the CPU's — the status register
 * words, the second stack, and the calling process's register block, which for a C caller is the host's own state
 * and is left as it was (a named drop of every case that runs the model, `test/aes_switch.py`). What disp itself
 * leaves it leaves: its one argument slot, which savestate's change of stack puts AT the dispatcher's stack top —
 * as its LAST call left it (the UDA entered); the PD it passed disp_act there first is overwritten before anything
 * can read it, and is not stored.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/evdisp.h"
#include "aes/evfork.h"
#include "aes/switch.h"

/* $fe4b74 — disp_act: `pd` READY, and at the TAIL of the ready list — the walk starts at the list's own head word,
 * a link like any other (a PD's link is its first longword). */
void aes_disp_act(uint8_t *image, uint32_t pd)
{
    uint32_t last = AES_RLR, next;

    set_bus_word(image, pd + PD_STAT, PD_STAT_READY);
    while ((next = bus_long(image, last + PD_LINK)) != 0)
        last = next;
    set_bus_long(image, pd + PD_LINK, next);
    set_bus_long(image, last + PD_LINK, pd);
}

/* $fe4b9c — mwait_act: `pd`, which asked to wait: an event it waits for has come meanwhile → ready after all
 * (disp_act); else it goes to the HEAD of the not-ready list. */
void aes_mwait_act(uint8_t *image, uint32_t pd)
{
    if (bus_word(image, pd + PD_EVWAIT) & bus_word(image, pd + PD_EVFLG)) {
        aes_disp_act(image, pd);
        return;
    }
    set_bus_long(image, pd + PD_LINK, be32(image + AES_NRL));
    wr32(image + AES_NRL, pd);
}

#ifdef RECREATE_HOST_DIFFERENTIAL
uint32_t (*recreate_idle)(uint8_t *image);
uint32_t (*recreate_process)(uint8_t *image, uint32_t uda, uint32_t caller_s_uda);

/* Where the machine WAITS FOR AN INTERRUPT: idle about to poll with nothing ready, nothing woken and nothing queued
 * ($fe4d70). The case's hook lays the interrupt it delivers there; with none left the wait would never end. */
static void waits_for_an_interrupt(uint8_t *image)
{
    if (be32(image + AES_RLR) || be32(image + AES_DRL) || be16(image + AES_FORK_COUNT))
        return;
    if (!recreate_idle(image))
        recreate_not_reconstructed("the dispatcher idles — no process ready, none woken, no fork queued — and the "
                                   "case's hook delivers no interrupt there: the call would block, and the machine "
                                   "would wait for ever");
}
#else
#define waits_for_an_interrupt(image) ((void)(image))
#endif

/* $fe4d68 — idle: the keyboard polled (chkkbd) and every process an event woke moved to the ready list, turn after
 * turn, until a process is ready or a fork is queued. */
void aes_idle(uint8_t *image)
{
    do {
        waits_for_an_interrupt(image);
        aes_chkkbd(image);
        while (be32(image + AES_DRL)) {
            uint32_t woken = be32(image + AES_DRL);

            wr32(image + AES_DRL, bus_long(image, woken + PD_LINK));
            aes_disp_act(image, woken);
        }
    } while (!be32(image + AES_RLR) && !be16(image + AES_FORK_COUNT));
}

#ifdef RECREATE_HOST_DIFFERENTIAL
/* savestate's model ($fe38d4): the dispatcher's guard counted. WHAT IT DOES NOT STORE is the process's register
 * block, its A6 and its two stack pointers (UDA_REGS..UDA_TRAP_SSP): the CPU state of whoever called dsptch — the
 * host's own, for a C caller — and its SR save word. */
static void savestate_model(uint8_t *image)
{
    image[AES_INDISP] = (uint8_t)(image[AES_INDISP] + 1);
}

/* switchto's model ($fe3930): the guard cleared. WHAT IT DOES NOT LOAD is the context the UDA holds — the registers,
 * the two stack pointers, the frame's PC: a host core has no CPU to load them into (its caller's state is the
 * host's own), and the frame's status register word, which the ROM rewrites from its own save word, is no host
 * core's to store. The load itself is held where it is real: `switch.S`'s switchto, byte for byte, entered with one
 * register file on both shores. */
static void leave_the_dispatcher(uint8_t *image)
{
    image[AES_INDISP] = 0;
}

/* $fe4d9e — disp, as a host core can run it: entered from dsptch for the running process. Nonzero once the call has
 * come back to that process. Under the dispatcher's own guard it is a state no machine reaches — nothing runs with
 * the guard set — refused by name rather than answered. */
uint32_t aes_disp(uint8_t *image)
{
    uint32_t caller_s_uda, pd, entered;
    uint16_t status;

    if (image[AES_INDISP])
        recreate_not_reconstructed("dsptch reached with the dispatcher's guard set (AES_INDISP): the ROM's is a bare "
                                   "`rts` there, a state no process runs in");
    caller_s_uda = bus_long(image, running(image, PD_UDA));
    savestate_model(image);
    pd = be32(image + AES_RLR);
    wr32(image + AES_RLR, bus_long(image, pd + PD_LINK));
    status = bus_word(image, pd + PD_STAT);
    if (status == PD_STAT_READY)
        aes_disp_act(image, pd);
    else if (status == PD_STAT_WAITING)
        aes_mwait_act(image, pd);
    do {
        aes_forker(image);
        aes_idle(image);
    } while (be16(image + AES_FORK_COUNT));
    wr32(image + AES_GL_CDA, bus_long(image, running(image, PD_CDA)));
    entered = bus_long(image, running(image, PD_UDA));
    wr32(image + AES_DISP_ARGUMENT, entered);
    if (entered != caller_s_uda && !recreate_process(image, entered, caller_s_uda))
        recreate_not_reconstructed("the dispatcher would enter another process than the one that called it, and the "
                                   "case's hook does not run it: the call would switch away");
    leave_the_dispatcher(image);
    return 1;
}
#endif
