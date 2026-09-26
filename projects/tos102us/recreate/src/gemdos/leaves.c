/* The GEMDOS calls whose whole body is RAM — the ones that need no file system, no allocator and no
 * console driver, and are therefore the first of the 88 selectors a recreate can hold to the ROM.
 *
 * Eight routines, in four pairs, and each pair is one piece of process or system state:
 *
 *   Sversion  ($fc9348)   a constant
 *   <stub>    ($fc933e)   ...and its twin: the handler every UNDEFINED selector's record names
 *   Fgetdta   ($fc6c9a)   the DTA pointer, in the running process's basepage
 *   Fsetdta   ($fc6cac)
 *   Dgetdrv   ($fc6ce0)   the current drive, one byte further along the same basepage
 *   Dsetdrv   ($fc6cc0)   ...and it answers with the DRIVE MAP, through a BIOS call
 *   Tgetdate  ($fc9e1a)   GEMDOS's own date and time words, which it keeps in RAM rather than
 *   Tgettime  ($fc9ea2)   asking the clock — the VBL and Tsetdate/Tsettime are what move them
 *   Tsetdate  ($fc9e2a)   ...and the two setters, which BOUND each field before storing it
 *   Tsettime  ($fc9eb2)
 *
 * THE RESULT REGISTER IS PART OF EACH ONE'S CONTRACT, and the four shapes here are all different.
 * Most write the whole of D0. `Fsetdta` writes NONE of it — Alcyon emitted no result for a `void`
 * function, so the caller gets its own D0 back through the trap entry's save area — which is why it
 * is the one routine here that takes the entry D0 as an argument and hands it back.
 *
 * WHAT IS NOT HERE is the process group (`Pterm0` $fc8086, `Pterm` $fc8028, `Ptermres` $fc7fd8).
 * None of the three is RAM-only in any reachable arm: each releases the process's memory through the
 * allocator and then LONGJMPs out through the dispatcher's own frame record, so the reachable half
 * is the memory manager's and the rest is a control transfer a C core has no way to make. See
 * `recreate/STATUS.md`, "Not reconstructed".
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "bios/bcon.h"
#include "gemdos/gemdos.h"
#include "machine.h"

/* ---- the two constants --------------------------------------------------------------------- */

/* GEMDOS $30 `Sversion` — `move.l #$1300,d0`. The version is byte-swapped by convention: the ROM
 * answers $1300, which reads as "0.13". */
uint32_t gemdos_sversion(void)
{
    return GEMDOS_VERSION;
}

/* The handler the dispatch table names for every selector the ABI leaves undefined — 38 of the 88
 * records point at these three instructions. It is NOT the dispatcher's own bound check: a selector
 * past $57 never reaches a record at all, and this one is reached, framed and called like any other.
 */
uint32_t gemdos_unimplemented(void)
{
    return GEMDOS_EINVFN;
}

/* ---- the DTA, in the basepage ---------------------------------------------------------------- */

/* GEMDOS $2f `Fgetdta` — the whole longword, as the directory search left it. */
uint32_t gemdos_fgetdta(const uint8_t *image)
{
    return be32(image + gemdos_basepage(image) + BASEPAGE_DTA);
}

/* GEMDOS $1a `Fsetdta`. `entry_d0` is the caller's own D0, which this routine does not write: the
 * ROM stores the pointer and returns, so what the caller reads as the call's result is whatever it
 * had in D0 when it trapped. */
uint32_t gemdos_fsetdta(uint8_t *image, uint32_t entry_d0, uint32_t dta)
{
    wr32(image + gemdos_basepage(image) + BASEPAGE_DTA, dta);
    return entry_d0;
}

/* ---- the current drive ------------------------------------------------------------------------ */

/* GEMDOS $19 `Dgetdrv` — a SIGNED byte widened to the whole of D0 (`move.b` / `ext.w` / `ext.l`), so
 * a basepage holding $ff answers -1 rather than 255. */
uint32_t gemdos_dgetdrv(const uint8_t *image)
{
    return sign_ext8(image[gemdos_basepage(image) + BASEPAGE_CURDRV]);
}

/* Where this routine's own BIOS call returns to — `$fc6cdc`, the `unlk` six bytes past its
 * `jsr GEMDOS_BIOS_TRAMPOLINE`. `src/gemdos/console.c` keeps the other thirteen of these and its
 * header note says what they are: the longword the trampoline parks, which is an output of the
 * layer rather than a detail of it. */
#define BIOS_RETURN_DSETDRV 0xfc6cdc

/* GEMDOS $0e `Dsetdrv`. Two halves that have nothing to do with each other: it stores the LOW BYTE
 * of the word argument as the process's current drive — no bound check, any byte — and then answers
 * with the BIOS's DRIVE MAP, which is what makes "set the drive" also "tell me which drives exist".
 *
 * THE ROM REACHES `Drvmap` THROUGH A REAL `trap #13` ($fc4eac's trampoline, which parks its own
 * return address at $eb0 so that the function number it left in its stack frame is what the BIOS
 * dispatcher pops). ON TARGET this takes the same trap; OFF TARGET there is none to take, so the
 * same call reaches our reconstruction of the routine behind it, which is what ROM mode asks of a
 * core (`tools/recreate_kit/TRAP_MODEL.md`). Either way the trampoline's store is made here, since
 * the trampoline itself is not transcribed — and the host build's residual is the trap's own image
 * effect, the 46-byte register frame the BIOS dispatcher pushes below `savptr`, which the battery
 * puts inside the band the differential already drops (`test/gemdos.py`, `machine`). */
uint32_t gemdos_dsetdrv(uint8_t *image, uint16_t drive)
{
    image[gemdos_basepage(image) + BASEPAGE_CURDRV] = (uint8_t)drive;
    wr32(image + GEMDOS_BIOS_RETURN_SLOT, BIOS_RETURN_DSETDRV);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_drvmap(image);
#else
    return bios_trap_plain(BIOS_DRVMAP_FN);
#endif
}

/* ---- the date and the time --------------------------------------------------------------------
 *
 * GEMDOS keeps both as DOS words of its own in RAM. Nothing here asks the hardware clock: the boot
 * seeds the date from the OS header's `os_dosdate` ($fc0460) and GEMDOS's own 200 Hz tick ($fc9cc0,
 * hooked onto `etv_timer`) advances both from then on, so the two words below ARE the system's idea
 * of the time and reading it is one `move.w`.
 */

/* GEMDOS $2a `Tgetdate` and $2c `Tgettime` — one word each, SIGN-EXTENDED into the whole of D0.
 * That is the ROM's `ext.l` and it matters: a time past noon has bit 15 set, so `Tgettime` answers a
 * negative long, and a caller storing the result in a `long` sees $ffffc000 rather than $0000c000. */
uint32_t gemdos_tgetdate(const uint8_t *image)
{
    return sign_ext16(be16(image + GEMDOS_DATE));
}

uint32_t gemdos_tgettime(const uint8_t *image)
{
    return sign_ext16(be16(image + GEMDOS_TIME));
}

/* What both setters do once the word passes: store it, and publish BOTH words to the hardware clock.
 * `$fc50b4` pushes the time, the date and XBIOS function 22 and traps — so setting either one
 * re-sends the other, and a caller that sets the date has also re-set the time. */
static void publish_clock(uint8_t *image)
{
    uint16_t date = be16(image + GEMDOS_DATE);
    uint16_t time = be16(image + GEMDOS_TIME);

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* Bound at `test/gemdos.py`'s import, which every battery that can reach this arm makes. The
     * check is `src/xbios/supexec.c`'s, for its reason: an unbound hook is a case that proved
     * nothing, and it should say so rather than jump through a null pointer. */
    assert(recreate_publish_clock != NULL &&
           "a case that reaches XBIOS Settime must bind recreate_publish_clock (test/gemdos.py)");
    recreate_publish_clock(image, date, time);
#else
    register uint16_t pushed_time __asm__("d0") = time;
    register uint16_t pushed_date __asm__("d1") = date;

    __asm__ volatile ("move.w %0,-(%%sp)\n\t"
                      "move.w %1,-(%%sp)\n\t"
                      "move.w #%c2,-(%%sp)\n\t"
                      "trap #14\n\t"
                      "addq.w #6,%%sp"
                      : "+d"(pushed_time), "+d"(pushed_date)
                      : "i"(XBIOS_SETTIME_FN)
                      : "d2", "a0", "a1", "a2", "memory", "cc");
#endif
}

/* The ROM's own bound on a DOS date word, field by field, and every one of its three quirks with it.
 *
 * The word is `(year - 1980) << 9 | month << 5 | day`, but the ROM does not decode it that way:
 *
 *  - the YEAR bound is DEAD CODE, for the same reason `time_is_in_range`'s hour bound is: `asr.w #9`
 *    on a word yields -64..63, so `<= 119` is true whichever year the word spells. `Tsetdate`
 *    accepts every one of the 128 the field can hold, 2044 onwards included.
 *  - the MONTH is four bits, not three (`asr.w #5` then `and #15`), so 13..15 are rejected by the
 *    `> 12` compare rather than by the field's width — and month 0 is accepted, with a length of 0
 *    in the table, so only day 0 goes with it.
 *  - FEBRUARY is the only month whose length is computed: the two year bits the mask picks out are
 *    `(year - 1980) & 3`, so a year divisible by four gets 29 days and every other February falls
 *    through to the table's 28.
 */
static int date_is_in_range(const uint8_t *image, uint16_t date)
{
    int year = (int16_t)date >> GEMDOS_DATE_YEAR_SHIFT;
    unsigned month = (date >> GEMDOS_DATE_MONTH_SHIFT) & GEMDOS_DATE_MONTH_MASK;
    unsigned day = date & GEMDOS_DATE_DAY_MASK;

    if (year > GEMDOS_DATE_MAX_YEAR || month > GEMDOS_DATE_MAX_MONTH)
        return 0;
    if (month == GEMDOS_DATE_FEBRUARY && (date & GEMDOS_DATE_LEAP_MASK) == 0)
        return day <= GEMDOS_DATE_LEAP_DAYS;
    return (int)day <= (int16_t)be16(image + GEMDOS_MONTH_LENGTHS + month * sizeof(uint16_t));
}

/* ...and the same for a DOS time word `hour << 11 | minute << 5 | second / 2`. The seconds and the
 * minutes are compared IN PLACE, without shifting the field down.
 *
 * THE HOUR CHECK IS DEAD CODE IN THE ROM, and that is a bug in TOS 1.02 rather than a reading of
 * one. `$fc9ee4` sign-extends the masked WORD to a long before comparing it against 24 << 11 as a
 * long — and a word whose only set bits are $f800 extends to at most $7800 and at least -$8000, so
 * it is below $c000 whichever way it goes. `Tsettime` therefore accepts every hour 0..31, including
 * the eight that do not exist. The transcription reproduces it, which is why the compiler's
 * "comparison is always true" is CORRECT here and is silenced rather than answered: answering it
 * would be writing a different operating system. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wtype-limits"
static int time_is_in_range(uint16_t time)
{
    if ((time & GEMDOS_TIME_SECOND_MASK) >= GEMDOS_TIME_MAX_SECOND)
        return 0;
    if ((time & GEMDOS_TIME_MINUTE_MASK) >= GEMDOS_TIME_MAX_MINUTE)
        return 0;
    return (int32_t)(int16_t)(time & GEMDOS_TIME_HOUR_MASK) < (int32_t)GEMDOS_TIME_MAX_HOUR;
}
#pragma GCC diagnostic pop

/* GEMDOS $2b `Tsetdate` and $2d `Tsettime` — -1 for a word out of range, 0 once it is stored. */
uint32_t gemdos_tsetdate(uint8_t *image, uint16_t date)
{
    if (!date_is_in_range(image, date))
        return GEMDOS_RANGE_ERROR;
    wr16(image + GEMDOS_DATE, date);
    publish_clock(image);
    return 0;
}

uint32_t gemdos_tsettime(uint8_t *image, uint16_t time)
{
    if (!time_is_in_range(time))
        return GEMDOS_RANGE_ERROR;
    wr16(image + GEMDOS_TIME, time);
    publish_clock(image);
    return 0;
}
