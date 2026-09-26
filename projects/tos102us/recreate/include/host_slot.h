/* host_slot.h — the HOST SLOTS every component shares: fixed image addresses that stand in, off
 * target, for a ROM frame local whose ADDRESS a routine hands on to another.
 *
 * GEMDOS needed them first, and the table began in `gemdos/gemdos.h`; it is here because the VDI needs
 * the same thing (`v_opnwk` points LINEA_CONTRL/INTIN/INTOUT at locals of its own frame and calls
 * vq_color over them), and two components keeping two tables in one band could hand out one address
 * twice with nothing to refuse it. ONE table, one held mask, one test (`test/test_host_slots.py`).
 */
#ifndef TOS102US_HOST_SLOT_H
#define TOS102US_HOST_SLOT_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"

/* ---- HOST SLOTS: a frame local whose ADDRESS a core hands on ---------------------------------------
 * The ROM's file system passes the address of a local in its own stack frame to a routine that reaches
 * memory through the image: `$fc6038`/`$fc5f44` hand the engine `-2(a6)` as a FAT transfer's buffer,
 * `$fc663c` hands its pattern `-24(a6)` to `$fc5d28`, `$fc5672` and `$fc5c9a`, `$fc696c` its component
 * FCB `-24(a6)` and its path cursor `-4(a6)` (to `$fc68dc`, which reads AND writes it), and `$fc7824`
 * the byte `-4(a6)` its `$e5` mark is written from, and `$fc71b6` its free-slot search name `-10(a6)`
 * (to `$fc663c`) and the new entry's FCB name `-22(a6)` (built by `$fc5d28`, written by `$fc5f1c`), and
 * `$fc7af0` (`Frename`) its entry buffer `-20(a6)` (a `$e5` mark, an entry's ten tail bytes, a new FCB name), and
 * `$fc7678` (`Fattrib`) the low byte of its own attribute ARGUMENT `15(a6)`, read or written in place, and the
 * dispatcher `$fc94e4` the byte `-14(a6)` a redirected read lands in and — through `$fc5078` — the argument words of
 * its own nested `Fwrite`, pushed on its stack, and `Pexec`'s loader `$fc85ea` the five locals it `Fread`s the
 * program's header and first relocation offset into (`-8`, `-66`, `-30`, `-10`, `-38(a6)`), laid out as one slot.
 * ON TARGET the C local IS that frame slot and its address is the one passed. OFF TARGET a C local is
 * host memory the image cannot reach, so each role has a fixed address instead: inside the oracle's
 * stack band, which the differential drops on both shores — exactly where the ROM's own copy of the
 * local lives — and below the deepest frame the kit calls legitimate. ONE TABLE, here, of every such address and its width; `test_host_slots.py`
 * reads it and pins every span inside that band and apart from every other.
 *
 * A SLOT IS CLAIMED FOR ITS LIVE RANGE AND RELEASED AFTER IT, and the host build makes "never two
 * users at once" a fact rather than a comment: a claim of a slot that is held is an assert. So the
 * nestings that do happen (a walk holding its name and cursor while it searches, a search holding its
 * pattern while the FAT routines take the frame word underneath it) are checked on every run, and the
 * one that must not (a routine re-entering itself) cannot pass silently. */
#define HOST_SLOT_SEARCH_PATTERN        0x7f1e0  /* $fc663c's pattern: the FCB name, then the attribute */
#define HOST_SLOT_SEARCH_PATTERN_BYTES  12       /* `link #-24` less the two words and two longs beside it */
#define HOST_SLOT_WALK_NAME             0x7f1ec  /* $fc696c's component FCB, the same twelve bytes */
#define HOST_SLOT_WALK_NAME_BYTES       HOST_SLOT_SEARCH_PATTERN_BYTES
#define HOST_SLOT_WALK_CURSOR           0x7f1f8  /* $fc696c's path cursor, carried in AND out */
#define HOST_SLOT_WALK_CURSOR_BYTES     4
#define HOST_SLOT_DELETE_MARK           0x7f1fe  /* $fc7824's `$e5`, the byte its write moves */
#define HOST_SLOT_DELETE_MARK_BYTES     1
#define HOST_SLOT_ATTRIBUTE             0x7f1ff  /* $fc7678's attribute byte, moved by a one-byte transfer */
#define HOST_SLOT_ATTRIBUTE_BYTES       1
#define HOST_SLOT_FRAME_WORD            0x7f200  /* $fc6038/$fc5f44's FAT word */
#define HOST_SLOT_FRAME_WORD_BYTES      2
#define HOST_SLOT_CREATE_FREE_NAME      0x7f240  /* $fc71b6's "\xe5", the name a free slot is searched by */
#define HOST_SLOT_CREATE_FREE_NAME_BYTES 2
#define HOST_SLOT_CREATE_FCB            0x7f244  /* $fc71b6's new entry's FCB name, written into it */
#define HOST_SLOT_CREATE_FCB_BYTES      11
#define HOST_SLOT_RENAME_ENTRY          0x7f250  /* $fc7af0's `-20(a6)`: `$e5`, an entry's tail, or the new FCB name */
#define HOST_SLOT_RENAME_ENTRY_BYTES    11
#define HOST_SLOT_PEXEC_LOCALS         0x7f280  /* $fc85ea's header fields and first fixup, each read by `Fread` */
#define HOST_SLOT_PEXEC_LOCALS_BYTES   28       /* `LOAD_LOCALS_BYTES` (`gemdos/pexec_load.h`) */
#define HOST_SLOT_C_ENTRY_ARGUMENTS     0x7f300  /* $fc5078's caller's words: the dispatcher's own nested `Fwrite` */
#define HOST_SLOT_C_ENTRY_ARGUMENTS_BYTES 12     /* selector.w, handle.w, count.l, buffer.l */
#define HOST_SLOT_REDIRECTED_BYTE       0x7f310  /* $fc94e4's `-14(a6)`: the byte a redirected read lands in */
#define HOST_SLOT_REDIRECTED_BYTE_BYTES 1

/* Each slot's bit in the held mask. */
enum host_slot {
    HOST_SLOT_ID_SEARCH_PATTERN,
    HOST_SLOT_ID_WALK_NAME,
    HOST_SLOT_ID_WALK_CURSOR,
    HOST_SLOT_ID_DELETE_MARK,
    HOST_SLOT_ID_ATTRIBUTE,
    HOST_SLOT_ID_FRAME_WORD,
    HOST_SLOT_ID_CREATE_FREE_NAME,
    HOST_SLOT_ID_CREATE_FCB,
    HOST_SLOT_ID_RENAME_ENTRY,
    HOST_SLOT_ID_PEXEC_LOCALS,
    HOST_SLOT_ID_C_ENTRY_ARGUMENTS,
    HOST_SLOT_ID_REDIRECTED_BYTE,
};

#ifdef RECREATE_HOST_DIFFERENTIAL
extern unsigned host_slots_held;     /* one bit per slot; defined in `src/host_slot.c` */

static inline uint32_t host_slot_take(enum host_slot slot, uint32_t host_at)
{
    assert(!(host_slots_held & 1u << slot));
    host_slots_held |= 1u << slot;
    return host_at;
}

static inline void host_slot_give_back(enum host_slot slot)
{
    host_slots_held &= ~(1u << slot);
}

/* The image address a frame local of role ROLE is handed on at: its slot, claimed, off target... */
#define host_slot_claim(ROLE, local) \
    ((void)(local), host_slot_take(HOST_SLOT_ID_##ROLE, HOST_SLOT_##ROLE))
#define host_slot_release(ROLE) host_slot_give_back(HOST_SLOT_ID_##ROLE)
#else
/* ...and the local's own address on target, where nothing is held. */
#define host_slot_claim(ROLE, local) ((uint32_t)(uintptr_t)(local))
#define host_slot_release(ROLE) ((void)0)
#endif

/* A slot that carries a LONGWORD IN and OUT of the call it is handed to (the walk's cursor): off target
 * the local's value is copied into the slot before and back out after; on target the slot is the local
 * and there is nothing to copy. */
static inline void host_slot_store_long(uint8_t *image, uint32_t slot_at, const uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    wr32(image + slot_at, *local);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

static inline void host_slot_load_long(const uint8_t *image, uint32_t slot_at, uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    *local = be32(image + slot_at);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

#endif /* TOS102US_HOST_SLOT_H */
