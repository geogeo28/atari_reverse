/* aes/pdpipe.h — PROCESSES AND THEIR PIPES (`src/aes/pdpipe.c`): a process descriptor found by name or by id
 * (pd_match, fpdnm; ap_find, appl_find's arm), the next one handed out and started (getpd, pstart, with gemdosif's two
 * hand-written leaves under them: uda_insuper and psetup), and a message moved into or out of a process's pipe (doq)
 * by the event a process queues for it (aqueue, iasync's arms 1 and 2).
 *
 * All Alcyon C in the ROM, entered by a Line-F call over the frame its caller pushed, but uda_insuper and psetup:
 * hand 68000, entered by Line-F all the same and left by `rts` — the two a target build ships as the ROM's own
 * instructions (`src/aes/pdpipe.S`, `include/transcribed.h`), their C here what Tier 1 proves.
 */
#ifndef TOS102US_AES_PDPIPE_H
#define TOS102US_AES_PDPIPE_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- what a pipe's caller hands in: GEM's QPB, three fields read in place through the pointer ---------------------- */
#define QPB_PID               0          /* word: the process whose pipe it is  ($fe5998 move.w (a3),(sp))      */
#define QPB_COUNT             2          /* word: the bytes to move             ($fe58d0 move.w 2(a0),d7)       */
#define QPB_BUFFER            4          /* long: from where, or to where       ($fe58e2 move.l 4(a0),-(sp))    */
#define QPB_BYTES             8          /* the three fields' extent: no C reads it (a QPB is read field by field) — the
                                          * battery reads one whole out of iasync's frame by it (`test/aes_pdpipe.py`) */

/* ---- the answers ----------------------------------------------------------------------------------------------- */
#define FPDNM_BY_PID          0          /* fpdnm's name: none, the process looked for by its id ($fe5708 tst.l) */
#define FPDNM_NONE            0          /* no process of that name or id       ($fe57dc clr.l d0)              */
#define AP_FIND_NONE          (-1)       /* ap_find's answer for no such name   ($fe660c moveq #-1,d0)          */
/* The id fpdnm is handed with a name: ap_find's `clr.w (sp)` ($fe65f2), which pd_match never reads on that arm. */
#define AP_FIND_UNREAD_PID    0

/* ---- the frames whose address the routine hands on (`host_slot.h`) ------------------------------------------------- */
/* pd_match (`link a6,#-10`): the PD's eight name bytes copied to -10(a6), the NUL that ends them at -2(a6)
 * ($fe5704 clr.b), -1(a6) unused. */
#define PD_MATCH_FRAME_BYTES  10
#define PD_MATCH_NAME_END     8          /* ($fe5704 clr.b -2(a6))                                             */
/* ap_find (`link a6,#-10`): the name copied to -10(a6) by lstcpy, which stops at the name's NUL and nowhere else — a
 * name of nine characters fills the frame, and a longer one runs on over the caller's saved A6: its TOP byte first,
 * which no access through A6 reads (the 24-bit bus drops it), then the byte under it, bits 16..23. So the ROM serves
 * TEN characters (the NUL on the top byte) and ELEVEN (the eleventh there, the NUL on bits 16..23 — a 0 where a 0
 * already is, ON THE PREMISE BELOW) and is lost from twelve: a live byte of its caller's A6, then the return address.
 * Both builds halt by name from twelve, exactly where the ROM stops returning (`src/aes/shell_find.c`'s convention).
 *
 * THE PREMISE: the caller's frame lies below 64 KB, so its A6's bits 16..23 are 0. True of every caller of the three
 * static processes — the `trap #2` handler runs the AES on the PD's own UDA stack ($fe3eee `movea.l 62(a6),sp`), and
 * the three UDAs are at $9c58, $a3a2 and $a89c. CAVEAT (band 5): an accessory's PD and UDA are the loader's, wherever
 * it allocates them; above 64 KB eleven characters DO zero a live byte of the caller's A6 on the ROM, and this slot's
 * second byte is then no longer "a 0 where a 0 is".
 * The slot is the frame and those two bytes of the saved A6. */
#define AP_FIND_FRAME_BYTES   10
#define AP_FIND_SAVED_A6_BYTES 2         /* the two the ROM serves a name over: the top byte, then bits 16..23    */
#define AP_FIND_SLOT_BYTES    (AP_FIND_FRAME_BYTES + AP_FIND_SAVED_A6_BYTES)
/* The last byte a served name's NUL may land on: one past it is where both builds halt. */
#define AP_FIND_LAST_SERVED   (AP_FIND_SLOT_BYTES - 1)

/* ---- uda_insuper's mark: what `aes/aes.h`'s UDA_IN_SUPER holds for a process inside the AES ----------------------------- */
#define UDA_INSIDE_THE_AES    1          /* ($fe3974 move.w #1,(a1); the trap's own $fe3ee2)                   */

/* ---- psetup's frame on the new process's stack: what switchto's `rte` pops ----------------------------------------- */
/* Its SR is `addrs.h`'s SR_SUPERVISOR alone: supervisor state, no interrupt masked ($fe3996 move.w #$2000,-(a2)). */
#define PSETUP_FRAME_BYTES    6          /* the SR's word under the PC's longword                              */

/* doq's and aqueue's first argument: the pipe's end the caller is at. */
#define PIPE_READING          0          /* ($fe4158 clr.w -(sp): iasync's read)                               */
#define PIPE_WRITING          1          /* ($fe4164 move.w #1,-(sp): its write)                               */

#ifndef __ASSEMBLER__
int16_t aes_pd_match(uint8_t *image, uint32_t name, int16_t pid, uint32_t pd);                      /* $fe56f6 */
uint32_t aes_fpdnm(uint8_t *image, uint32_t name, int16_t pid);                                     /* $fe5750 */
uint32_t aes_getpd(uint8_t *image);                                                                 /* $fe57e0 */
void aes_uda_insuper(uint8_t *image, uint32_t uda);                                                 /* $fe3970 */
void aes_psetup(uint8_t *image, uint32_t pd, uint32_t pc);                                          /* $fe397a */
uint32_t aes_pstart(uint8_t *image, uint32_t code, uint32_t name, uint32_t load_address);           /* $fe5886 */
void aes_doq(uint8_t *image, int16_t writing, uint32_t pd, uint32_t qpb);                           /* $fe58c0 */
void aes_aqueue(uint8_t *image, int16_t writing, uint32_t evb, uint32_t qpb);                       /* $fe5988 */
int16_t aes_ap_find(uint8_t *image, uint32_t name);                                                 /* $fe65da */
#endif

#endif /* TOS102US_AES_PDPIPE_H */
