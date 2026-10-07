/* aes/evwait.h — A WAIT QUEUED, AND WAITED FOR (`src/aes/evwait.c`): gemasync's iasync and mwait, geminput's five
 * kinds of wait (akbin, adelay, abutton, amouse, amutex) and the semaphore's release (unsync).
 *
 *   $fe40ec iasync(code, parameter)  an EVB taken for the running process, a free event bit given it, and the wait
 *                                    of `code` queued over `parameter` — D0.w the event bit
 *   $fe40b2 mwait(mask)              the running process waits for any event of `mask`: none come yet → WAITING,
 *                                    and the dispatcher (dsptch) — D0.w the events that came
 *   $fe5520 akbin(evb)               a key: one queued is taken at once (dq), else the EVB waits on the CDA's list
 *   $fe5566 adelay(evb, ticks)       a delay: the tick countdown re-armed, the EVB placed in the DELTA list
 *   $fe55f8 abutton(evb, wanted)     the buttons: as wanted now (downorup) → completed, else waits
 *   $fe5666 amouse(evb, moblk)       the mouse entering or leaving a rectangle: so already → completed, else waits
 *   $fe4e8e amutex(evb, spb)         a semaphore: taken (tak_flag) → completed, else waits on the semaphore's list
 *   $fe4eb8 unsync(spb)              a semaphore given up once; at 0 it goes to its first waiter, and the caller
 *                                    YIELDS (dsptch) — or to nobody
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame. A wait that is satisfied where it is
 * queued is COMPLETED at once (azombie: its event posted to the running process itself), so the mwait that follows
 * finds it and does not switch; any other is left on a WAIT LIST (`aes/evasync.h`) for a fork function's post
 * (`aes/evinput.h`) or another process's call to complete.
 */
#ifndef TOS102US_AES_EVWAIT_H
#define TOS102US_AES_EVWAIT_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/aes.h"

/* ---- iasync's CODES: the kind of wait, the index (less one) of its jump table $fef7a2 ($fe41a0 subq.w #1,
 * $fe41a2 cmp.w #6 / bhi: any other code queues nothing — the EVB is left on its process's list, on no wait list). */
#define IASYNC_READ           1          /* aqueue(0): a read of a pipe         ($fe4154)                      */
#define IASYNC_WRITE          2          /* aqueue(1): a write                  ($fe4160)                      */
#define IASYNC_DELAY          3          /* adelay                              ($fe416e)                      */
#define IASYNC_MUTEX          4          /* amutex                              ($fe4178)                      */
#define IASYNC_KEYBOARD       5          /* akbin                               ($fe4182)                      */
#define IASYNC_MOUSE          6          /* amouse                              ($fe418c)                      */
#define IASYNC_BUTTON         7          /* abutton                             ($fe4196)                      */
/* The first event bit iasync tries; it shifts left past every bit the process's EVBs hold ($fe4124, $fe412c). */
#define IASYNC_FIRST_EVENT    0x0001

/* ---- adelay ------------------------------------------------------------------------------------------------------ */
#define ADELAY_LEAST_TICKS    1          /* a delay of no tick waits for one    ($fe557a moveq #1,d7)          */

/* ---- unsync's answer where it has one: the semaphore given up with nobody waiting leaves D0 the empty wait list's
 * head (`move.l a4,d0`, $fe4ece). On its two other paths D0 is not unsync's — still held: the D0 it was entered
 * with; handed over: what the scheduler brings back — and no caller's C reads it (`aes/wmupdate.h`). */
#define UNSYNC_NOBODY_WAITS   0

#ifndef __ASSEMBLER__
uint16_t aes_iasync(uint8_t *image, int16_t code, uint32_t parameter);                              /* $fe40ec */
uint16_t aes_ev_mwait(uint8_t *image, int16_t mask);                                                /* $fe40b2 */
void aes_akbin(uint8_t *image, uint32_t evb);                                                       /* $fe5520 */
void aes_adelay(uint8_t *image, uint32_t evb, int32_t ticks);                                       /* $fe5566 */
void aes_abutton(uint8_t *image, uint32_t evb, uint32_t wanted);                                    /* $fe55f8 */
void aes_amouse(uint8_t *image, uint32_t evb, uint32_t moblk);                                      /* $fe5666 */
void aes_amutex(uint8_t *image, uint32_t evb, uint32_t semaphore);                                  /* $fe4e8e */
uint16_t aes_unsync(uint8_t *image, uint32_t semaphore);                                            /* $fe4eb8 */
#endif

#endif /* TOS102US_AES_EVWAIT_H */
