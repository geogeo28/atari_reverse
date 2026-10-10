/* pdpipe.c — PROCESSES AND THEIR PIPES (`aes/pdpipe.h`): a process found by its name or its id (pd_match, fpdnm,
 * ap_find), the next one handed out and started (getpd, pstart, over gemdosif's uda_insuper and psetup), and a message
 * moved into or out of a process's pipe (doq) by the event block a process queues for it (aqueue). Alcyon C in the ROM
 * but for uda_insuper and psetup, hand 68000; ported over its own order.
 *
 * Every read is where the ROM makes it: a count or an index is a SIGNED word, a PD's fields are read through the
 * pointer the routine holds (a register in the ROM, on the 24-bit bus), and a field the ROM reads again after a
 * callee's stores is read again here.
 *
 * uda_insuper and psetup SHIP AS THE ROM's OWN INSTRUCTIONS on target (`pdpipe.S`): each C body's floor is the image
 * pointer the ROM never loads, and each measures over Tier 3's bar (1.50 and 1.24). Their C is what Tier 1 proves.
 *
 * THE FRAMES ARE THE ROM's where an address escapes: pd_match's copy of a PD's name and ap_find's copy of the name it
 * is asked for stand in through `host_slot.h` off target, each laid out as the ROM's `link` lays it.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "stack_diet.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evasync.h"
#include "aes/mnlib.h"
#include "aes/pdpipe.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/switch.h"
#include "aes/wmupdate.h"

_Static_assert(HOST_SLOT_AES_PD_MATCH_NAME_BYTES == PD_MATCH_FRAME_BYTES, "pd_match's frame and its host slot");
_Static_assert(HOST_SLOT_AES_AP_FIND_NAME_BYTES == AP_FIND_SLOT_BYTES, "ap_find's frame and its host slot");
_Static_assert(PD_MATCH_NAME_END == PD_NAME_BYTES, "pd_match's NUL ends the eight name bytes it copies");

/* A redraw message's own words, which doq merges by: the window's handle, then its rectangle ($fe5920 6(a3),
 * $fe592c `addq.l #8`). */
#define REDRAW_HANDLE         AP_MSG_WORDS
#define REDRAW_RECT           (AP_MSG_WORDS + (uint32_t)sizeof(uint16_t))

/* $fe56f6 — pd_match: whether the PD at `pd` is the one looked for — by `name`, compared with the PD's eight name
 * bytes copied into the frame and ended there (so a name matches only blank-filled to eight, as pd_nameit left the
 * PD's), or with no name by `pid`. */
int16_t aes_pd_match(uint8_t *image, uint32_t name, int16_t pid, uint32_t pd)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(PD_MATCH_FRAME_BYTES)];
    uint32_t frame;
    int16_t matched;

    if (name == FPDNM_BY_PID)
        return signed_field(image, pd, PD_PID) == pid;
    frame = host_slot_claim(AES_PD_MATCH_NAME, frame_local);
    image[frame + PD_MATCH_NAME_END] = STRING_NUL;
    aes_movs(image, PD_NAME_BYTES, pd + PD_NAME, frame);
    matched = aes_streq(image, name, frame);
    host_slot_release(AES_PD_MATCH_NAME);
    return matched;
}

/* $fe5750 — fpdnm: the PD pd_match finds, or FPDNM_NONE: the three static ones in turn, then each accessory's — its
 * address out of AES_ACCESSORY_PDS — up to AES_ACCESSORY_COUNT (a signed compare: none for a count of 0 or less). */
FRAME_DIET("no-defer-pop", "no-function-cse", "no-move-loop-invariants")
uint32_t aes_fpdnm(uint8_t *image, uint32_t name, int16_t pid)
{
    int16_t index;

    for (index = 0; index < AES_PD_COUNT; index++) {
        uint32_t pd = table_entry(AES_PD_TABLE, index, PD_BYTES);

        if (aes_pd_match(image, name, pid, pd))
            return pd;
    }
    for (index = 0; index < global_word(image, AES_ACCESSORY_COUNT); index++) {
        uint32_t pd = be32(image + table_entry(AES_ACCESSORY_PDS, index, sizeof(uint32_t)));

        if (aes_pd_match(image, name, pid, pd))
            return pd;
    }
    return FPDNM_NONE;
}

/* $fe3970 — uda_insuper (hand 68000): the UDA marked as inside the AES, as the `trap #2` handler marks a caller's. */
TRANSCRIBED_CORE
void aes_uda_insuper(uint8_t *image, uint32_t uda)
{
    set_bus_word(image, uda + UDA_IN_SUPER, UDA_INSIDE_THE_AES);
}

/* $fe57e0 — getpd: the next process descriptor — a static one while AES_STATIC_PIDS has not counted all three, its
 * id that count; after them the next accessory's, out of AES_ACCESSORY_PDS, its id the accessory's index past the
 * static ones — each counter one more, the PD's UDA marked (uda_insuper). */
uint32_t aes_getpd(uint8_t *image)
{
    uint32_t pd;

    if (global_word(image, AES_STATIC_PIDS) < AES_PD_COUNT) {
        pd = table_entry(AES_PD_TABLE, global_word(image, AES_STATIC_PIDS), PD_BYTES);
        set_bus_word(image, pd + PD_PID, be16(image + AES_STATIC_PIDS));
        wr16(image + AES_STATIC_PIDS, (uint16_t)(be16(image + AES_STATIC_PIDS) + 1));
    } else {
        pd = bus_long(image, table_entry(AES_ACCESSORY_PDS, global_word(image, AES_ACCESSORY_COUNT), sizeof(uint32_t)));
        set_bus_word(image, pd + PD_PID, (uint16_t)(be16(image + AES_ACCESSORY_COUNT) + AES_PD_COUNT));
        wr16(image + AES_ACCESSORY_COUNT, (uint16_t)(be16(image + AES_ACCESSORY_COUNT) + 1));
    }
    aes_uda_insuper(image, bus_long(image, pd + PD_UDA));
    return pd;
}

/* $fe397a — psetup (hand 68000): the frame switchto's `rte` pops — `pc`, under a supervisor SR — pushed on the stack
 * the PD's UDA saved, the saved pointer moved down over it; with every interrupt masked from the first read to the
 * last store (the bracket over its own save word, `aes/switch.h`). The pointer is loaded once and stored back as it
 * is, top byte and all. */
TRANSCRIBED_CORE
void aes_psetup(uint8_t *image, uint32_t pd, uint32_t pc)
{
    uint32_t uda, stack;

    sr_mask_saving(image, AES_SR_PSETUP);
    uda = bus_long(image, pd + PD_UDA);
    stack = bus_long(image, uda + UDA_SUPER_SP);
    stack -= (uint32_t)sizeof(uint32_t);
    set_bus_long(image, stack, pc);
    stack -= (uint32_t)sizeof(uint16_t);
    set_bus_word(image, stack, SR_SUPERVISOR);
    set_bus_long(image, uda + UDA_SUPER_SP, stack);
    sr_restore_from(image, AES_SR_PSETUP);
}

_Static_assert(PSETUP_FRAME_BYTES == sizeof(uint32_t) + sizeof(uint16_t), "psetup's frame: the PC under the SR");

/* $fe5886 — pstart: a process made — the next PD (getpd), the program it was loaded as, its name (pd_nameit), its
 * first frame (psetup: `code` is where it starts) — ready, and put at the head of the woken list for the dispatcher's
 * next pass. Answers the PD. */
uint32_t aes_pstart(uint8_t *image, uint32_t code, uint32_t name, uint32_t load_address)
{
    uint32_t pd = aes_getpd(image);

    set_bus_long(image, pd + PD_LDADDR, load_address);
    aes_pd_nameit(image, pd, name);
    aes_psetup(image, pd, code);
    set_bus_word(image, pd + PD_STAT, PD_STAT_READY);
    onto_the_woken_list(image, pd);
    return pd;
}

/* A WM_REDRAW just written at `message` merged into one already queued for the same window, if there is one: the
 * pipe walked from its head, message by message (each sixteen bytes and the extra its third word counts), up to the
 * index BEFORE the write; the first match's rectangle becomes the union of the two. Answers the bytes the write adds
 * to the pipe: none when it was merged. */
static int16_t redraw_merged(uint8_t *image, uint32_t pd, uint32_t message, int16_t count)
{
    int16_t at = 0;

    while (at < signed_field(image, pd, PD_QUEUE_INDEX) && count) {
        uint32_t queued = offset_by(pd, at) + PD_QUEUE;

        if (bus_word(image, queued + AP_MSG_TYPE) == WM_REDRAW
            && bus_word(image, message + REDRAW_HANDLE) == bus_word(image, queued + REDRAW_HANDLE)) {
            aes_rc_union(image, message + REDRAW_RECT, queued + REDRAW_RECT);
            count = 0;
        } else {
            at = (int16_t)(at + (int16_t)(bus_word(image, queued + AP_MSG_EXTRA) + AP_MSG_BYTES));
        }
    }
    return count;
}

/* What both builds halt with where a read takes more than the pipe holds — reached through aqueue's service of a
 * waiting reader, which asks nothing of the pipe (a writer of fewer bytes than the reader waits for). The ROM's index
 * goes negative and its move of "what is left" is lbcopy of that count as an unsigned word: some 64 KB of GEMBSS moved
 * down over itself by the bytes read — THE LINE-F HANDLER'S RAM COPY ($cc0e) among it. doq's own Line-F return is
 * then taken through the moved bytes: the middle of the handler, or what lay behind it. Measured: on a read of 32, 40
 * or 48 bytes that lands on an instruction of it which still reaches `unlk; rts` (16 held, 32 read: back in 196,732
 * instructions) — over an AES whose every later call goes through the broken handler, its caller's saved registers
 * and SR not restored; on a read of 20 it returns over a rewritten vector page; on every other count tried it never
 * returns.
 * WHY THE C DOES NOT FOLLOW IT, where it returns: without this halt the image equals the ROM's but for ONE WORD —
 * the moved handler's self-modifying store of its mask word ($cc44 less the bytes read; for 48, wherever lbcopy left
 * A0) — which is 68000 code executed from the wrong offset, not reconstructed (the Line-F copy is the ROM's own
 * machinery), and the register file the caller gets back is the broken handler's. So the halt stands for every
 * count: at the ROM's boundary (an index below 0), after the ROM's stores up to it. */
#define READ_PAST_THE_PIPE  "doq: a read of more bytes than the pipe holds (the ROM moves 64 KB of its own RAM down " \
                            "over itself, its Line-F handler's copy with it: on a few counts it returns through the " \
                            "moved handler over a destroyed AES, on the rest never)"
/* ...and where aqueue is handed a process id no PD has: fpdnm answers none, and the ROM reads the vector page as that
 * process's descriptor and writes its pipe through a vector — measured: its run never returns. */
#define NO_SUCH_PROCESS     "aqueue: a pipe of a process id no PD has (the ROM takes the vector page for its PD and " \
                            "never returns)"

/* $fe58c0 — doq: the QPB's bytes moved between its buffer and the pipe of the PD at `pd`.
 * WRITING: copied in at the pipe's index (through PD_QUEUE_ADDRESS), then read back where the PD itself holds its
 * pipe (PD_QUEUE): a WM_REDRAW is merged into one queued for the same window (`redraw_merged`), any other message —
 * or a redraw with none to merge into — stays, the index past it.
 * READING: copied out from the pipe's head, the index that much less, what is left moved down to the head. */
FRAME_DIET("no-caller-saves")
void aes_doq(uint8_t *image, int16_t writing, uint32_t pd, uint32_t qpb)
{
    int16_t count = signed_field(image, qpb, QPB_COUNT);

    if (writing) {
        uint32_t message;

        aes_lbcopy(image, offset_by(bus_long(image, pd + PD_QUEUE_ADDRESS), signed_field(image, pd, PD_QUEUE_INDEX)),
                   bus_long(image, qpb + QPB_BUFFER), count);
        message = offset_by(pd, signed_field(image, pd, PD_QUEUE_INDEX)) + PD_QUEUE;
        if (bus_word(image, message + AP_MSG_TYPE) == WM_REDRAW)
            count = redraw_merged(image, pd, message, count);
        set_bus_word(image, pd + PD_QUEUE_INDEX, (uint16_t)(bus_word(image, pd + PD_QUEUE_INDEX) + count));
        return;
    }
    aes_lbcopy(image, bus_long(image, qpb + QPB_BUFFER), bus_long(image, pd + PD_QUEUE_ADDRESS), count);
    set_bus_word(image, pd + PD_QUEUE_INDEX, (uint16_t)(bus_word(image, pd + PD_QUEUE_INDEX) - count));
    if (signed_field(image, pd, PD_QUEUE_INDEX) < 0)
        recreate_not_reconstructed(READ_PAST_THE_PIPE);
    if (bus_word(image, pd + PD_QUEUE_INDEX))
        aes_lbcopy(image, bus_long(image, pd + PD_QUEUE_ADDRESS),
                   offset_by(bus_long(image, pd + PD_QUEUE_ADDRESS), count), signed_field(image, pd, PD_QUEUE_INDEX));
}

/* Whether the pipe of the PD at `pd` can serve the QPB now: a write, when the room left holds its bytes; a read, when
 * the pipe holds any — signed words both. */
static inline int16_t pipe_ready(const uint8_t *image, int16_t writing, uint32_t pd, uint32_t qpb)
{
    if (writing)
        return (int16_t)(PD_QUEUE_BYTES - bus_word(image, pd + PD_QUEUE_INDEX)) >= signed_field(image, qpb, QPB_COUNT);
    return signed_field(image, pd, PD_QUEUE_INDEX) > 0;
}

/* $fe5988 — aqueue (iasync's arms 1 and 2): the event block `evb` of a process that reads (`writing` 0) or writes its
 * QPB's process's pipe. If the pipe can serve it now: the bytes moved (doq) and the EVB completed (azombie) — and THE
 * FIRST EVB WAITING AT THE OTHER END, if any, served at once: marked NOCANCEL, taken off its list, ITS QPB (its
 * EVB_PARM) moved the other way with no test that the pipe can serve it, and completed. If it cannot: the QPB's
 * address kept in the EVB, the EVB put on this end's wait list. The list is chosen by `writing` XOR ready, as words. */
FRAME_DIET("no-defer-pop", "no-optimize-sibling-calls", "no-caller-saves")
void aes_aqueue(uint8_t *image, int16_t writing, uint32_t evb, uint32_t qpb)
{
    uint32_t pd = aes_fpdnm(image, FPDNM_BY_PID, signed_field(image, qpb, QPB_PID));
    int16_t ready;
    uint32_t waits, waiting;

    if (pd == FPDNM_NONE)
        recreate_not_reconstructed(NO_SUCH_PROCESS);
    ready = pipe_ready(image, writing, pd, qpb);
    waits = pd + ((writing ^ ready) ? PD_QUEUE_WRITERS : PD_QUEUE_READERS);
    if (!ready) {
        set_bus_long(image, evb + EVB_PARM, qpb);
        aes_evinsert(image, evb, waits);
        return;
    }
    aes_doq(image, writing, pd, qpb);
    aes_azombie(image, evb);
    waiting = bus_long(image, waits);
    if (!waiting)
        return;
    set_bus_word(image, waiting + EVB_FLAG, bus_word(image, waiting + EVB_FLAG) | EVB_FLAG_NOCANCEL);
    set_bus_long(image, waits, bus_long(image, waiting + EVB_LINK));
    if (bus_long(image, waiting + EVB_LINK))
        set_bus_long(image, bus_long(image, waiting + EVB_LINK) + EVB_PRED, bus_long(image, waiting + EVB_PRED));
    aes_doq(image, !writing, pd, bus_long(image, waiting + EVB_PARM));
    aes_azombie(image, waiting);
}

/* $fe65da — ap_find (appl_find): the id of the process named `name` — copied into the frame first, to its NUL and no
 * shorter — or AP_FIND_NONE. The copy may run on over the top two bytes of the caller's saved A6; the second stands
 * here as the caller of a static process leaves it: 0 (`aes/pdpipe.h`, THE PREMISE — an accessory's caller, band 5,
 * may not). A name whose NUL lands past them is where the ROM stops returning and both builds halt. */
int16_t aes_ap_find(uint8_t *image, uint32_t name)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(AP_FIND_SLOT_BYTES)];
    uint32_t frame = host_slot_claim(AES_AP_FIND_NAME, frame_local);
    uint32_t pd;

    image[frame + AP_FIND_LAST_SERVED] = 0;        /* the saved A6's bits 16..23: THE PREMISE (its top byte is not read) */
    (void)aes_lstcpy(image, frame, name);
    if (image[frame + AP_FIND_LAST_SERVED])
        recreate_not_reconstructed("ap_find: a name of twelve characters or more (the ROM runs on over a live byte of "
                                   "its caller's saved A6, then its own return address, which the C cannot see)");
    pd = aes_fpdnm(image, frame, AP_FIND_UNREAD_PID);
    host_slot_release(AES_AP_FIND_NAME);
    return pd ? signed_field(image, pd, PD_PID) : AP_FIND_NONE;
}
