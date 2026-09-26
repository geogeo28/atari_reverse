/* gemdos/gemdos.h — what the GEMDOS cores share: the basepage view, the dispatch table's records, and the
 * two doors a reconstruction needs that a ROM routine reaches through a trap.
 *
 * The ADDRESSES are all in `addrs.h`, which both this header and the cases read; what is here is the
 * STRUCTURE over them — the accessors that turn `p_run` into a field, and the four call shapes the
 * dispatcher's argument descriptor selects between.
 */
#ifndef TOS102US_GEMDOS_H
#define TOS102US_GEMDOS_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "addrs.h"
#include "machine.h"

/* ---- HOST SLOTS: a frame local whose ADDRESS a core hands on ---------------------------------------
 * The ROM's file system passes the address of a local in its own stack frame to a routine that reaches
 * memory through the image: `$fc6038`/`$fc5f44` hand the engine `-2(a6)` as a FAT transfer's buffer,
 * `$fc663c` hands its pattern `-24(a6)` to `$fc5d28`, `$fc5672` and `$fc5c9a`, `$fc696c` its component
 * FCB `-24(a6)` and its path cursor `-4(a6)` (to `$fc68dc`, which reads AND writes it), and `$fc7824`
 * the byte `-4(a6)` its `$e5` mark is written from, and `$fc71b6` its free-slot search name `-10(a6)`
 * (to `$fc663c`) and the new entry's FCB name `-22(a6)` (built by `$fc5d28`, written by `$fc5f1c`), and
 * `$fc7678` (`Fattrib`) the low byte of its own attribute ARGUMENT `15(a6)`, read or written in place.
 * ON TARGET the C local IS that frame slot and its address is the one passed. OFF TARGET a C local is
 * host memory the image cannot reach, so each role has a fixed address instead: inside the oracle's
 * stack band, which the differential drops on both shores — exactly where the ROM's own copy of the
 * local lives — and below the deepest frame the kit calls legitimate. ONE TABLE, here, of every such address and its width; `test_gemdos_host_slots.py`
 * reads it and pins every span inside that band and apart from every other.
 *
 * A SLOT IS CLAIMED FOR ITS LIVE RANGE AND RELEASED AFTER IT, and the host build makes "never two
 * users at once" a fact rather than a comment: a claim of a slot that is held is an assert. So the
 * nestings that do happen (a walk holding its name and cursor while it searches, a search holding its
 * pattern while the FAT routines take the frame word underneath it) are checked on every run, and the
 * one that must not (a routine re-entering itself) cannot pass silently. */
#define GEMDOS_HOST_SLOT_SEARCH_PATTERN        0x7f1e0  /* $fc663c's pattern: the FCB name, then the attribute */
#define GEMDOS_HOST_SLOT_SEARCH_PATTERN_BYTES  12       /* `link #-24` less the two words and two longs beside it */
#define GEMDOS_HOST_SLOT_WALK_NAME             0x7f1ec  /* $fc696c's component FCB, the same twelve bytes */
#define GEMDOS_HOST_SLOT_WALK_NAME_BYTES       GEMDOS_HOST_SLOT_SEARCH_PATTERN_BYTES
#define GEMDOS_HOST_SLOT_WALK_CURSOR           0x7f1f8  /* $fc696c's path cursor, carried in AND out */
#define GEMDOS_HOST_SLOT_WALK_CURSOR_BYTES     4
#define GEMDOS_HOST_SLOT_DELETE_MARK           0x7f1fe  /* $fc7824's `$e5`, the byte its write moves */
#define GEMDOS_HOST_SLOT_DELETE_MARK_BYTES     1
#define GEMDOS_HOST_SLOT_ATTRIBUTE             0x7f1ff  /* $fc7678's attribute byte, moved by a one-byte transfer */
#define GEMDOS_HOST_SLOT_ATTRIBUTE_BYTES       1
#define GEMDOS_HOST_SLOT_FRAME_WORD            0x7f200  /* $fc6038/$fc5f44's FAT word */
#define GEMDOS_HOST_SLOT_FRAME_WORD_BYTES      2
#define GEMDOS_HOST_SLOT_CREATE_FREE_NAME      0x7f240  /* $fc71b6's "\xe5", the name a free slot is searched by */
#define GEMDOS_HOST_SLOT_CREATE_FREE_NAME_BYTES 2
#define GEMDOS_HOST_SLOT_CREATE_FCB            0x7f244  /* $fc71b6's new entry's FCB name, written into it */
#define GEMDOS_HOST_SLOT_CREATE_FCB_BYTES      11

/* Each slot's bit in the held mask. */
enum gemdos_host_slot {
    GEMDOS_HOST_SLOT_ID_SEARCH_PATTERN,
    GEMDOS_HOST_SLOT_ID_WALK_NAME,
    GEMDOS_HOST_SLOT_ID_WALK_CURSOR,
    GEMDOS_HOST_SLOT_ID_DELETE_MARK,
    GEMDOS_HOST_SLOT_ID_ATTRIBUTE,
    GEMDOS_HOST_SLOT_ID_FRAME_WORD,
    GEMDOS_HOST_SLOT_ID_CREATE_FREE_NAME,
    GEMDOS_HOST_SLOT_ID_CREATE_FCB,
};

#ifdef RECREATE_HOST_DIFFERENTIAL
extern unsigned gemdos_host_slots_held;     /* one bit per slot; defined in `src/gemdos/dispatch.c` */

static inline uint32_t gemdos_host_slot_take(enum gemdos_host_slot slot, uint32_t host_at)
{
    assert(!(gemdos_host_slots_held & 1u << slot));
    gemdos_host_slots_held |= 1u << slot;
    return host_at;
}

static inline void gemdos_host_slot_give_back(enum gemdos_host_slot slot)
{
    gemdos_host_slots_held &= ~(1u << slot);
}

/* The image address a frame local of role ROLE is handed on at: its slot, claimed, off target... */
#define gemdos_host_slot_claim(ROLE, local) \
    ((void)(local), gemdos_host_slot_take(GEMDOS_HOST_SLOT_ID_##ROLE, GEMDOS_HOST_SLOT_##ROLE))
#define gemdos_host_slot_release(ROLE) gemdos_host_slot_give_back(GEMDOS_HOST_SLOT_ID_##ROLE)
#else
/* ...and the local's own address on target, where nothing is held. */
#define gemdos_host_slot_claim(ROLE, local) ((uint32_t)(uintptr_t)(local))
#define gemdos_host_slot_release(ROLE) ((void)0)
#endif

/* A slot that carries a LONGWORD IN and OUT of the call it is handed to (the walk's cursor): off target
 * the local's value is copied into the slot before and back out after; on target the slot is the local
 * and there is nothing to copy. */
static inline void gemdos_host_slot_store_long(uint8_t *image, uint32_t slot_at, const uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    wr32(image + slot_at, *local);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

static inline void gemdos_host_slot_load_long(const uint8_t *image, uint32_t slot_at, uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    *local = be32(image + slot_at);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

/* ---- the current process --------------------------------------------------------------------- */

/* `p_run` — GEMDOS's one pointer to the running process, published by the OS header at +$28 and
 * re-read by the trap entry after every dispatch (a `Pexec` or a `Pterm` moves it). */
static inline uint32_t gemdos_basepage(const uint8_t *image)
{
    return be32(image + GEMDOS_P_RUN);
}

/* ---- reaching a basepage, and THE host-only bound ------------------------------------------------
 *
 * THE BOUND IS HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to
 * abort"): `p_run`, a `Pexec` argument and a basepage field are ordinary longwords of RAM a case may
 * stage anywhere, so a basepage pointed outside the machine walks off the image array here where the
 * original walks its own address space. It is spelt ONCE, below, and every accessor in this header
 * and in the process group goes through it — six copies of the same `assert` across `process.c` and
 * `handles.c` were six places for the width to be written differently.
 */
static inline void gemdos_assert_inside_ram(uint32_t at, uint32_t width)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at + width <= ST_RAM_BYTES);
#else
    (void)at;
    (void)width;
#endif
}

/* `width` bytes of the image at `at` — the door every accessor below reaches the array through, and
 * what a core that indexes an arbitrary address (`Pexec` copying an environment, building the
 * child's stack) uses directly. */
static inline uint8_t *gemdos_image_bytes(uint8_t *image, uint32_t at, uint32_t width)
{
    gemdos_assert_inside_ram(at, width);
    return image + at;
}

static inline uint8_t *gemdos_image_byte(uint8_t *image, uint32_t at)
{
    return gemdos_image_bytes(image, at, 1);
}

/* One LONGWORD field of a basepage that is not necessarily `p_run`'s — the dying process's, or the
 * child `Pexec` has just cut. */
static inline uint32_t gemdos_basepage_field(const uint8_t *image, uint32_t basepage, uint32_t field)
{
    uint32_t at = addr_add(basepage, field);

    gemdos_assert_inside_ram(at, 4);
    return be32(image + at);
}

static inline void gemdos_set_basepage_field(uint8_t *image, uint32_t basepage, uint32_t field,
                                             uint32_t value)
{
    wr32(gemdos_image_bytes(image, addr_add(basepage, field), 4), value);
}

/* ...and one BYTE of it: a standard handle, a `p_curdir` entry, the command tail. */
static inline uint8_t *gemdos_basepage_byte(uint8_t *image, uint32_t basepage, uint32_t field)
{
    return gemdos_image_byte(image, addr_add(basepage, field));
}

/* The running process's current drive, `p_curdrv`, as the SIGNED byte every reader widens (`Dgetdrv`,
 * `$fc68dc`, the drive leaves' argument 0). */
static inline int8_t gemdos_current_drive(const uint8_t *image)
{
    uint32_t at = addr_add(gemdos_basepage(image), BASEPAGE_CURDRV);

    gemdos_assert_inside_ram(at, 1);
    return (int8_t)image[at];
}

/* One of the six STANDARD HANDLES of the RUNNING process, as the signed byte it is: 0..5 are the
 * process's own, and $ff/$fe/$fd are the console, AUX: and PRN: devices a fresh process starts
 * with. `handles.c` writes where this reads, through `gemdos_basepage_byte` above. */
static inline int8_t gemdos_standard_handle(const uint8_t *image, unsigned standard)
{
    uint32_t handle_at = addr_add(gemdos_basepage(image), BASEPAGE_HANDLES + standard);

    gemdos_assert_inside_ram(handle_at, 1);
    return (int8_t)image[handle_at];
}

/* ---- the dispatch table ------------------------------------------------------------------------
 * 88 six-byte records: the handler, then the ARGUMENT DESCRIPTOR the dispatcher reads at +4.
 */
/* SIGNED, because the dispatcher's bound is: it stops a selector above $57 and lets a negative one
 * through, so the ROM's `muls.w #6` really does index BACKWARDS out of the table. Spelt as an `int`
 * here so that the backwards index is the arithmetic rather than an unsigned wrap that happens to
 * land in the same place. */
static inline uint32_t gemdos_record(int selector)
{
    return GEMDOS_FUNCTION_TABLE + selector * GEMDOS_RECORD_BYTES;
}

static inline uint32_t gemdos_handler(const uint8_t *image, int selector)
{
    return be32(image + gemdos_record(selector));
}

static inline uint16_t gemdos_descriptor(const uint8_t *image, int selector)
{
    return be16(image + gemdos_record(selector) + GEMDOS_RECORD_DESCRIPTOR);
}

/* ---- the two doors out of a reconstructed GEMDOS routine ---------------------------------------
 *
 * A ROM routine here reaches the rest of the OS through a TRAP, and in ROM mode the oracle takes
 * that trap into the ROM's own handler. A reconstruction cannot: off target there is no 68000 to
 * take it, and on target taking it would frame the caller a second time. So each such call is a
 * named door, and what is behind it is a reconstruction of the routine the trap would have reached
 * (`tools/recreate_kit/TRAP_MODEL.md`, "ROM mode").
 */

/* The handler the dispatcher `jsr`s through, in the four shapes the argument classes give it. Off
 * target the handler is a ROM address the candidate cannot execute, so the CASE binds this hook to
 * the reconstruction of that handler — the same arrangement `src/xbios/supexec.c` and
 * `include/staged_call.h` make, and for the same reason. */
#ifdef RECREATE_HOST_DIFFERENTIAL
/* `arguments` is the address of the caller's first argument word (one word past the function
 * number) and `argument_bytes` how many of them the dispatcher copied — the two facts a host stub
 * needs to stand in for a call whose arguments are 68000 stack words. */
extern int32_t (*recreate_call_gemdos_handler)(uint8_t *image, uint32_t handler,
                                               uint32_t arguments, uint16_t argument_bytes);
#endif

/* XBIOS `Settime` — `$fc50b4`'s `trap #14`, which is how both clock setters publish the words they
 * have just stored. NOT RECONSTRUCTED: `Settime` writes the 6301's own clock over the IKBD ACIA, so
 * the door has nothing behind it yet and no case may reach it (`recreate/STATUS.md`, "Not
 * reconstructed"). The host build calls a hook the battery binds to a recorder, so a case that DID
 * reach it fails by naming the door rather than by diverging somewhere downstream. */
#ifdef RECREATE_HOST_DIFFERENTIAL
extern void (*recreate_publish_clock)(uint8_t *image, uint16_t date, uint16_t time);
#endif

#endif /* TOS102US_GEMDOS_H */
