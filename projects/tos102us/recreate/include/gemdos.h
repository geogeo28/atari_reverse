/* gemdos.h — what the GEMDOS cores share: the basepage view, the dispatch table's records, and the
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

/* ---- the current process --------------------------------------------------------------------- */

/* `p_run` — GEMDOS's one pointer to the running process, published by the OS header at +$28 and
 * re-read by the trap entry after every dispatch (a `Pexec` or a `Pterm` moves it). */
static inline uint32_t gemdos_basepage(const uint8_t *image)
{
    return be32(image + GEMDOS_P_RUN);
}

/* One of the six STANDARD HANDLES, as the signed byte it is: 0..5 are the process's own, and
 * $ff/$fe/$fd are the console, AUX: and PRN: devices a fresh process starts with.
 *
 * The bound is HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to
 * abort"): `p_run` is an ordinary longword of RAM a case may stage anywhere, so a basepage pointed
 * outside the machine walks off the image here where the original walks its own address space. */
static inline int8_t gemdos_standard_handle(const uint8_t *image, unsigned standard)
{
    uint32_t handle_at = addr_add(gemdos_basepage(image), BASEPAGE_HANDLES + standard);

#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(handle_at < ST_RAM_BYTES);
#endif
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
