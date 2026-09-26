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

/* ---- a frame local whose ADDRESS a core hands on ---------------------------------------------------
 * The ROM's file system passes the address of a word in its own stack frame as a transfer's buffer
 * (`$fc6038` and `$fc5f44`'s `-2(a6)`). On target the C local IS such a word and its address is the
 * one passed. Off target a C local is host memory the image cannot reach, so the word goes to
 * `GEMDOS_HOST_FRAME_WORD` instead: inside the oracle's stack band, which the differential drops on
 * both shores — exactly where the ROM's own copy of the word lives — and below the deepest frame the
 * kit calls legitimate (`test_gemdos_fs_fat.py` pins both).
 *
 * ONE WORD, so only one such local may be live at a time. The host build makes that a FACT rather
 * than a claim: a claim while the word is held is an assert, and every claim is released by the
 * helper that made it. (The FAT routines are the only users today, and they never nest: the FAT
 * OFD's clusters are negative, so a transfer through it never reaches `$fc6038` again.) */
#define GEMDOS_HOST_FRAME_WORD 0x7f200

#ifdef RECREATE_HOST_DIFFERENTIAL
extern int gemdos_host_frame_word_held;     /* defined with its user, `src/gemdos/fs_io.c` */
#endif

static inline uint32_t gemdos_frame_word_claim(uint16_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    (void)local;
    assert(!gemdos_host_frame_word_held);
    gemdos_host_frame_word_held = 1;
    return GEMDOS_HOST_FRAME_WORD;
#else
    return (uint32_t)(uintptr_t)local;
#endif
}

static inline void gemdos_frame_word_release(void)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    gemdos_host_frame_word_held = 0;
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
