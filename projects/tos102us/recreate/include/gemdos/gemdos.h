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
#include "host_slot.h"
#include "machine.h"

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

/* ---- the dispatcher (`src/gemdos/dispatch.c`) --------------------------------------------------------
 * `arguments` is the address of a caller's words, the function number first. The dispatcher is also
 * called from INSIDE itself: a redirected `Cconrs` echoes each character through a whole nested
 * dispatch ($fc5078). */
uint32_t gemdos_dispatch(uint8_t *image, uint32_t arguments);            /* $fc94e4 */
uint32_t gemdos_dispatch_selector(uint8_t *image, uint32_t arguments);   /* $fc973e, past the record */

/* THE ONE `trap #1` SHAPE A ROM DOOR MAKES from another component — the function word over one longword (the VDI's
 * `$fcfa9c`, the AES's glue `$fe3bba` / `$fe3c26`). THE TWO BUILDS TAKE IT TWO WAYS, `src/gemdos/console.c`'s
 * arrangement: on target the machine's own trap over that frame; off target there is no trap to take, so the words go
 * into a host slot and the reconstructed dispatcher is called on them — its handler through the hook a case binds.
 * `static inline`, so each door's code is the one it had when it spelt this itself. */
#ifdef RECREATE_HOST_DIFFERENTIAL
static inline uint32_t gemdos_trap_word_long(uint8_t *image, uint16_t function, uint32_t argument)
{
    uint8_t words_local[HOST_SLOT_GEMDOS_WORDS_BYTES];
    uint32_t words = host_slot_claim(GEMDOS_WORDS, words_local);
    uint32_t result;

    wr16(image + words, function);
    wr32(image + words + GEMDOS_ARGUMENT_WORD, argument);
    result = gemdos_dispatch(image, words);
    host_slot_release(GEMDOS_WORDS);
    return result;
}
#else
/* The trap entry restores D1-A6 from the frame it builds (`src/gemdos/trap1.S`), so D0 is all it changes. */
static inline uint32_t gemdos_trap_word_long(uint8_t *image, uint16_t function, uint32_t argument)
{
    register uint32_t result __asm__("d0");

    (void)image;
    __asm__ volatile ("move.l %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "addq.l #6,%%sp"
                      : "=d"(result)
                      : "d"(argument), "d"(function)
                      : "memory", "cc");
    return result;
}
#endif

/* ...and the media-change recovery's two helpers, reconstructed ahead of the recovery that calls them.
 * $fc93f4 — a DND and every DND reachable from it given back to the pool. */
void gemdos_free_dnd_tree(uint8_t *image, uint32_t dnd);

/* $fc9468 — the open files whose OFD names the DMD in `caller_a4` released. THE ROM NEVER LOADS ITS
 * ARGUMENT (the core says so), so the drive compared is whatever A4 its caller left: a caller written
 * for the E_CHG recovery ($fc951e) must pass "whatever A4 the innermost file-system routine left" — NOT
 * the DMD the ROM pushes — or it silently fixes the ROM's bug. */
void gemdos_free_drive_ofds(uint8_t *image, uint32_t caller_a4);

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
