/* process.c — the GEMDOS PROCESS group: `Pterm` ($fc8028), `Pterm0` ($fc8086), `Ptermres`
 * ($fc7fd8), `Pexec` ($fc817a), and the release routine all four reach ($fc8092).
 *
 * WHAT A PROCESS OWNS, which is the whole subject of this file: a basepage, the memory descriptors
 * whose `m_own` names it, its six standard handles, the open-file descriptors whose owner names it,
 * and up to sixteen current directories it holds references on. Ending a process is giving all five
 * back; starting one is taking the first and inheriting the last three from its parent.
 *
 * `Pterm` DOES NOT RETURN TO ITS CALLER, and this is not a figure of speech — it is the shape of
 * every case in `test/gemdos_process.py`. The ROM's last act is
 *
 *      move.l  p_run,a0            ; the PARENT's basepage, which it has just installed
 *      move.l  d0,$68(a0)          ; the exit code, into the parent's own D0 SAVE SLOT
 *      jsr     $fc4fe8             ; the trap entry's EPILOGUE
 *
 * ...and that epilogue unwinds the PARENT's process frame and `rte`s, so what resumes is whoever
 * called the parent's own GEMDOS call, with the child's exit code in D0. The target build does
 * exactly that, through `gemdos_trap1_epilogue` (`src/gemdos/trap1.S` exports it for this caller).
 * The host build has no 68000 and no epilogue, so it RETURNS the exit code instead, and the case is
 * a CHECKPOINT differential stopped at the ROM's own `jsr`.
 *
 * WHAT `Pterm` DOES NOT DO, because it is the thing everyone expects it to: it does not longjmp.
 * `$fc4f54` is a real longjmp and `$fc4f38` a real setjmp, and the record at `$7ef4` the dispatcher
 * arms IS jumped to — but by the FILE SYSTEM's critical-error abort, which the dispatcher answers at
 * `$fc9526` by comparing the returned value against `E_CHNG` and killing the process there.
 * `Pterm`'s own unwind is the epilogue above and nothing else. (`recreate/STATUS.md`'s wave-7 note
 * says "the termination record longjmp"; the record is real, the caller is not `Pterm`.)
 *
 * THE FOUR HALTS IN THIS FILE, each a component rather than a branch:
 *
 *   * `gemdos_release_process` and `Pterm` reach `Fclose`, which halts on a handle that names an
 *     open FILE (`src/gemdos/handles.c`). Every DEVICE arm runs.
 *   * `gemdos_resync_clock` has NO halt, but it has a limit the case has to carry: the probe writes
 *     two registers and reads them back, and the kit's declared I/O map has exactly two forms for
 *     that — a CONSTANT, which a store makes stale and the harness refuses, and WRITE-THROUGH,
 *     which is what a chip that is really there does. So every case here declares a machine WITH a
 *     Mega ST clock, and the `bcs` that skips the whole routine on a plain ST is driven by an
 *     ORACLE claim alone (`recreate/STATUS.md`, "Not reconstructed").
 *   * `Pexec` modes 0 and 3 LOAD a program — `$fc6d14` looks the file up and `$fc85ea` is the
 *     loader and the relocator — and both halt for want of the file system.
 *   * `Pexec` mode 4 and mode 0's tail END IN THE EPILOGUE, like `Pterm`, and are checkpoints for
 *     the same reason.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "bcon.h"
#include "gemdos.h"
#include "gemdos_memory.h"
#include "gemdos_process.h"
#include "hw.h"
#include "ipl.h"
#include "machine.h"
#include "recreate.h"
#include "staged_call.h"

/* ---- the Mega ST battery clock, which is the one piece of hardware GEMDOS itself touches --------
 *
 * `$fc4c0c` is the BIOS's probe for an RP5C15 at $fffc20 — the Mega ST's clock, absent on every
 * plain ST including the machine the snapshot was captured on. It is written here rather than in
 * `src/bios/` because `gemdos_resync_clock` is its only reconstructed caller; the ROM has four more
 * ($fc0eb0, $fc4be8, $fc4c44, $fc4d02), and the day one of those is ported this moves to a file of
 * its own.
 *
 * THE PROBE IS A WRITE AND A READ-BACK: put the chip in its probe mode, write a pattern into two of
 * its registers and read them back masked. A chip that is not there answers something else and the
 * ROM reports ABSENCE THROUGH THE CARRY FLAG (`ori #1,ccr`), which is why this returns a flag of its
 * own rather than the D0 the ROM leaves — D0 holds the pattern either way and says nothing.
 */
/* The chip's geometry is `include/gemdos_process.h`'s, because the CASES declare the same registers
 * to the harness and must not spell them a second time. What is here is what only this file has: */
#define RTC_NO_CLOCK          0xffffffffu /* `moveq #-1,d0` at $fc4cfe — what a read with no chip is */

static int mega_st_clock_answers(void)
{
    uint8_t high, low;
    uint16_t read_back;

    hw_write8(RTC_BASE + RTC_MODE, RTC_MODE_PROBE);
    /* `movep.w #$0a05,5(a0)` — one instruction, two BYTE stores two addresses apart, because the
     * chip sits on every other byte of the bus. The ordered write ledger compares them one at a
     * time (`hw.h`, Phase 10), so the reconstruction spells both. */
    hw_write8(RTC_BASE + RTC_PROBE_HIGH, RTC_PROBE_PATTERN >> 8);
    hw_write8(RTC_BASE + RTC_PROBE_LOW, RTC_PROBE_PATTERN & 0xff);

    /* TWO SEQUENCED STATEMENTS, not one expression: `movep.w 5(a0),d1` reads +5 and THEN +7, and
     * the ordered read ledger compares the stream in that order — where C leaves the evaluation
     * order of two calls in one expression unspecified, so the compiler is free to swap them and
     * make the differential red on a machine nobody changed. `read_clock_digits` is a loop for the
     * same reason. */
    high = io_read8(RTC_BASE + RTC_PROBE_HIGH);
    low = io_read8(RTC_BASE + RTC_PROBE_LOW);
    read_back = (uint16_t)((high << 8) | low);
    if ((read_back & RTC_PROBE_MASK) != RTC_PROBE_PATTERN)
        return 0;

    hw_write8(RTC_BASE + RTC_RESET, RTC_RESET_VALUE);
    hw_write8(RTC_BASE + RTC_MODE, RTC_MODE_RUN);
    hw_write8(RTC_BASE + RTC_TEST, 0);
    return 1;
}

/* $fc4ce6 — the chip's thirteen BCD digits into a thirteen-byte buffer, HIGHEST register first.
 *
 * The RP5C15 sits on every other byte of the bus and holds one BCD digit per register, four bits
 * wide. The ROM reads registers 1, 3, 5 ... 25 and files them at buffer[12], [11] ... [0] — so the
 * buffer runs year-tens, year-units, month-tens, ... seconds-units, which is what makes the
 * conversion below a straight walk up it.
 */
static void read_clock_digits(uint8_t *buffer)
{
    unsigned index, reg = RTC_FIRST_DIGIT;

    for (index = RTC_DIGITS; index-- > 0; reg += RTC_REGISTER_STEP)
        buffer[index] = io_read8(RTC_BASE + reg) & RTC_DIGIT_MASK;
}

/* Where the two buffers are. The ROM reads the chip TWICE and compares, because the clock can tick
 * between two register reads and leave a time that never existed; two passes that agree digit for
 * digit are the only ones it accepts. */
#define RTC_BUFFER_A         0x0e94
#define RTC_BUFFER_B         0x0ea1

/* Which pair of digits each field of the DOS date and time word is, as offsets into that buffer,
 * and how far each field is shifted once the two digits are a number. `asr.w #1` on the seconds is
 * not a shift left of -1: the DOS time word counts TWO-SECOND units. */
#define RTC_YEAR_AT          0
#define RTC_MONTH_AT         2
#define RTC_DAY_AT           4
#define RTC_HOUR_AT          7
#define RTC_MINUTE_AT        9
#define RTC_SECOND_AT        11
#define RTC_BCD_TENS         10

static uint16_t two_digits(const uint8_t *buffer, unsigned at)
{
    return (uint16_t)(buffer[at] * RTC_BCD_TENS + buffer[at + 1]);
}

/* $fc4c44 — the whole clock as one longword, the DOS date in the high half and the time in the low.
 *
 * `-1` if no chip answered, which is unreachable from the one caller below: it has already asked.
 *
 * THE FIELDS ARE ADDED AND NOT OR-ED, which is the ROM's own `add.w` and matters: two BCD digits
 * can spell a number wider than the field they go in (a minute of 99 is $63, and $63 << 5 reaches
 * into the hour), and a reconstruction that OR-ed would differ from the original on exactly the
 * malformed clock a dying battery produces.
 */
static uint32_t mega_st_clock_now(uint8_t *image)
{
    /* THE TWO BUFFERS ARE POINTERS AND NOT IMAGE OFFSETS, which is a codegen choice and nothing
     * else: the ledgers see the same thirteen reads of the same registers in the same order either
     * way (the differential is what pins that), but an offset swapped each pass makes the compiler
     * recompute `image + offset` per digit and pass the pair to an out-of-line `read_clock_digits`.
     * Spelt as pointers, the compare is `move.b -(a2),d3 / cmp.b -(a0),d3` and the reader inlines.
     * The host-only bound is taken ONCE here, where the two addresses are, rather than per byte. */
    uint8_t *reading = gemdos_image_bytes(image, RTC_BUFFER_A, RTC_DIGITS);
    uint8_t *previous = gemdos_image_bytes(image, RTC_BUFFER_B, RTC_DIGITS);
    uint16_t date, time;
    int agreed;

    if (!mega_st_clock_answers())
        return RTC_NO_CLOCK;

    read_clock_digits(reading);
    do {
        uint8_t *swap = reading;
        unsigned digit;

        reading = previous;
        previous = swap;
        read_clock_digits(reading);
        agreed = 1;
        for (digit = RTC_DIGITS; digit-- > 0; )
            if (reading[digit] != previous[digit]) {
                agreed = 0;             /* the clock ticked mid-read: take the whole chip again */
                break;
            }
    } while (!agreed);

    time = (uint16_t)(two_digits(reading, RTC_SECOND_AT) >> 1);
    time = (uint16_t)(time + (two_digits(reading, RTC_MINUTE_AT) << GEMDOS_TIME_MINUTE_SHIFT));
    time = (uint16_t)(time + (two_digits(reading, RTC_HOUR_AT) << GEMDOS_TIME_HOUR_SHIFT));
    date = two_digits(reading, RTC_DAY_AT);
    date = (uint16_t)(date + (two_digits(reading, RTC_MONTH_AT) << GEMDOS_DATE_MONTH_SHIFT));
    date = (uint16_t)(date + (two_digits(reading, RTC_YEAR_AT) << GEMDOS_DATE_YEAR_SHIFT));
    return ((uint32_t)date << 16) | time;
}

/* $fc5092 — GEMDOS's own date and time words re-seeded from that clock, under an interrupt mask so
 * that the 200 Hz tick cannot roll the halves apart between the two stores.
 *
 * `Pterm` is its only caller in the ROM, which is a design fact worth stating: TOS 1.02 re-reads the
 * battery clock exactly once per process that ends, and never on a machine that has no battery.
 */
void gemdos_resync_clock(uint8_t *image)
{
    uint32_t clock;
    os_ipl_t mask;

    if (!mega_st_clock_answers())
        return;
    clock = mega_st_clock_now(image);

    mask = os_ipl_raise();
    wr16(image + GEMDOS_TIME, (uint16_t)clock);
    wr16(image + GEMDOS_DATE, (uint16_t)(clock >> 16));
    os_ipl_restore(mask);
}

/* ---- the terminate vector ------------------------------------------------------------------------
 *
 * `Setexc($102, -1)` reads the GEMDOS TERMINATE VECTOR without replacing it, and `Pterm` then calls
 * whatever is there. On the captured machine that is `$fc0670`, a bare `rts`; a program that wants
 * to be told it is dying puts its own routine there.
 *
 * THE CALL GOES THROUGH `$fc4f0a`, which is two instructions — `move.l 4(sp),-(sp) / rts` — and so
 * enters the routine with the VECTOR'S OWN VALUE as its first argument. That is an Alcyon artefact
 * of `(*f)()` compiled against a first-argument stack slot, and it is reproduced rather than
 * simplified: a staged routine that reads `4(sp)` finds it. Off target the hook `staged_call.h`
 * declares stands in, with the vector passed as the argument it really is.
 */
static void call_terminate_vector(uint8_t *image, uint32_t routine)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, routine);
#else
    register uint32_t target __asm__("a0") = routine;

    (void)image;
    /* A5 is NOT pinned here, where `staged_call.h`'s handler shapes pin it to zero: those are
     * interrupt handlers whose own `lea 0,a5` the ROM opens, and GEMDOS's compiled C reaches its
     * globals by absolute address instead. It is clobbered, because the routine owes nothing. */
    __asm__ volatile ("move.l %[target],-(%%sp)\n\t"
                      "jsr (%[target])\n\t"
                      "addq.l #4,%%sp"
                      : [target] "+a"(target)
                      :
                      : STAGED_CALL_CLOBBERS_D1_D7, "d0", "a1", STAGED_CALL_CLOBBERS_A2_A4,
                        "a5", "memory", "cc");
#endif
}

/* `Setexc` through the BIOS, exactly as `src/gemdos/console.c` reaches `Bconout`: the trampoline's
 * own parked return address on both builds, then a real `trap #13` on target and the core called
 * directly off it. `$fc8044` is the instruction after `Pterm`'s own `jsr $fc4eac`. */
#define PTERM_BIOS_RETURN_SITE 0xfc8044

static uint32_t read_terminate_vector(uint8_t *image)
{
    wr32(image + GEMDOS_BIOS_RETURN_SLOT, PTERM_BIOS_RETURN_SITE);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_setexc(image, GEMDOS_TERM_VECTOR, SETEXC_INQUIRE);
#else
    return bios_trap_vector(BIOS_SETEXC_FN, GEMDOS_TERM_VECTOR, SETEXC_INQUIRE);
#endif
}

/* ---- the current-directory reference counts ------------------------------------------------------
 *
 * Every `p_curdir` byte is an INDEX into a shared table of directory nodes, and `GEMDOS_CURDIR_
 * REFCOUNTS` is how many basepages are holding each one. `gemdos_inherit_curdir` bumps a count and
 * `gemdos_release_process` drops it, which is the whole of what this group knows about the table:
 * what an entry POINTS AT is the file system's ($7dee, walked by the dispatcher's media-change arm).
 *
 * THE INDEX IS A SIGNED WORD, widened from the basepage's signed byte by the ROM's own `ext.w` and
 * then used as an address displacement (`movea.w d7,a0 / adda.l #$8066,a0`), so a negative entry
 * addresses BEFORE the table. No bound is applied there and none is applied here.
 */
static uint8_t *directory_refcount(uint8_t *image, int16_t node)
{
    uint32_t at = addr_add(GEMDOS_CURDIR_REFCOUNTS, (uint32_t)(int32_t)node);

#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at < ST_RAM_BYTES);
#endif
    return image + at;
}

/* $fc51de — one of a parent's sixteen current directories, given to a child.
 *
 * The byte stored is the LOW BYTE of the word; the count bumped is indexed by the whole SIGNED word,
 * which is the same value because the caller read it through `ext.w` off a signed byte. The ROM also
 * READS the count into D0 and throws the value away before the `addq.b` — Alcyon's `p[i]++` — which
 * is no memory effect and is not spelt here.
 */
void gemdos_inherit_curdir(uint8_t *image, int16_t entry, int16_t node, uint32_t basepage)
{
    *gemdos_basepage_byte(image, basepage, BASEPAGE_CURDIR + (uint32_t)(int32_t)entry) = (uint8_t)node;
    (*directory_refcount(image, node))++;
}

/* ---- giving a process's memory back ------------------------------------------------------------
 *
 * The two loops below are ONE walk of the allocated list under two names, because the ROM has them
 * twice and they differ in exactly one call: `Pterm` puts the block on the FREE list, `Ptermres`
 * hands the descriptor back to the pool and leaves the memory allocated to nobody — which is the
 * whole of "terminate and stay resident".
 *
 * THE WALK KEEPS A POINTER TO THE LINK IT CAME THROUGH rather than to the previous descriptor, which
 * is what lets the head be unlinked without a special case: `a3` starts at `mp_mal` itself, so the
 * first store goes into the MPB. Transcribed as the ROM has it.
 */
typedef void (*release_block)(uint8_t *image, uint32_t md);

static void free_the_block(uint8_t *image, uint32_t md)
{
    gemdos_md_free_insert(image, md, GEMDOS_MPB);
}

static void keep_the_block(uint8_t *image, uint32_t md)
{
    gemdos_pool_free(image, md);
}

static void unlink_every_block_of(uint8_t *image, uint32_t owner, release_block release)
{
    uint32_t link = GEMDOS_MPB + MPB_ALLOCATED_LIST;
    uint32_t md = be32(image + link);

    while (md != 0) {
        if (be32(image + md + MD_OWNER) == owner) {
            wr32(image + link, be32(image + md + MD_LINK));
            release(image, md);
        } else {
            link = md;
        }
        md = be32(image + link);
    }
}

/* $fc8092 — everything a process owns, given back, in the ROM's own order.
 *
 * FOUR LOOPS, and the order is the order the stores happen in:
 *
 *   1. the six STANDARD HANDLES. `Fclose` is called on the handle the slot HOLDS, not on the slot —
 *      and only when it is strictly POSITIVE, so a device (negative) needs no close and an unused
 *      slot (0) is not one either.
 *   2. the 75 HANDLE RECORDS, by owner. `Fclose(slot + 6)` on each, which is the reference
 *      count and — on the last holder — the slot itself.
 *   3. the sixteen CURRENT DIRECTORIES, whose bytes index a shared table of reference counts at
 *      `GEMDOS_CURDIR_REFCOUNTS`. A zero byte is "no directory" and is skipped; anything else is
 *      decremented, INCLUDING a negative one, which indexes before the table. The ROM applies no
 *      bound and neither does this.
 *   4. the MEMORY, onto the free list.
 */
void gemdos_release_process(uint8_t *image, uint32_t basepage)
{
    int16_t index;

    for (index = 0; index < BASEPAGE_STANDARD_HANDLES; index++) {
        int16_t handle = (int16_t)*(const int8_t *)gemdos_basepage_byte(image, basepage,
                                                                        BASEPAGE_HANDLES + index);

        if (handle > 0)
            gemdos_fclose(image, handle);
    }
    for (index = 0; index < GEMDOS_HANDLE_COUNT; index++)
        if (be32(image + GEMDOS_HANDLE_TABLE + (uint32_t)index * GEMDOS_HANDLE_STRIDE + HANDLE_OWNER)
            == basepage)
            gemdos_fclose(image, index + GEMDOS_FIRST_FILE_HANDLE);
    for (index = 0; index < BASEPAGE_CURDIR_ENTRIES; index++) {
        int16_t node = (int16_t)*(const int8_t *)gemdos_basepage_byte(image, basepage,
                                                                      BASEPAGE_CURDIR + index);

        if (node != 0)
            (*directory_refcount(image, node))--;
    }
    unlink_every_block_of(image, basepage, free_the_block);
}

/* ---- the three terminators ----------------------------------------------------------------------- */

/* $fc8028 ($4c). The order is load-bearing all the way through: the terminate vector runs while the
 * process is STILL the running one, `p_run` becomes the parent BEFORE the release (so a block the
 * release allocates could not be charged to the dead process), and the exit code is planted in the
 * PARENT's save slot after it.
 *
 * THE EXIT CODE IS ZERO-EXTENDED, not sign-extended: `clr.l d0 / move.w 8(a6),d0`. So `Pterm(-1)`
 * hands the parent $0000ffff and not $ffffffff, which is a ROM fact a program can depend on.
 *
 * ...AND IT MUST BE IN D0 AT THE `jsr`, which the store above does not make true on target: the
 * epilogue's first instruction ($fc4fee, `move.l d0,$68(a5)` — `trap1.S`) plants D0 in the same slot
 * a second time, over what this just wrote, and the ROM arrives there with the exit code in D0
 * ($fc806c `clr.l d0 / move.w 8(a6),d0`). So D0 is PINNED as an input of the `jsr` below; left to
 * the compiler it holds whatever the release loops last computed, and every parent on target would
 * resume with a corrupted result. NO SURFACE SEES IT: the host build returns instead of jumping, and
 * the Tier 3 / checkpoint cases stop the ORIGINAL at its own `jsr` — the honest record is
 * `recreate/STATUS.md`'s parked list, and the surface that would catch it is a transcription case
 * entered at a staged caller with the parent's `+$7c` frame, compared at the `rte`.
 */
uint32_t gemdos_pterm(uint8_t *image, uint16_t status)
{
    uint32_t basepage, exit_code;

    call_terminate_vector(image, read_terminate_vector(image));
    gemdos_resync_clock(image);

    basepage = gemdos_basepage(image);
    wr32(image + GEMDOS_P_RUN, gemdos_basepage_field(image, basepage, BASEPAGE_PARENT));
    gemdos_release_process(image, basepage);

    exit_code = status;
    gemdos_set_basepage_field(image, gemdos_basepage(image), BASEPAGE_SAVED_D0, exit_code);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return exit_code;
#else
    {
        register uint32_t exit_in_d0 __asm__("d0") = exit_code;

        __asm__ volatile ("jsr gemdos_trap1_epilogue" : : "d"(exit_in_d0) : "memory");
    }
    __builtin_unreachable();
#endif
}

/* $fc8086 ($00) — `Pterm(0)`, and nothing else at all. Its own selector is 0, which is also the
 * descriptor the dispatcher reads for it, so the argument word it is handed is the caller's
 * function number and is never looked at. */
uint32_t gemdos_pterm0(uint8_t *image)
{
    return gemdos_pterm(image, 0);
}

/* $fc7fd8 ($31) — terminate and STAY RESIDENT.
 *
 * `Mshrink(p_run, keep)` first, which trims the process's own TPA to the length the caller wants
 * kept and puts the remainder back on the free list; then every descriptor the process still owns is
 * unlinked from the ALLOCATED list and the descriptor RECORD — not the memory — is returned to the
 * pool. So the block survives with no owner and on no list, which is exactly what makes it resident:
 * nothing will ever free it, and `Malloc` cannot hand it out again.
 */
uint32_t gemdos_ptermres(uint8_t *image, uint32_t keep, uint16_t status)
{
    gemdos_mshrink(image, gemdos_basepage(image), keep);
    unlink_every_block_of(image, gemdos_basepage(image), keep_the_block);
    return gemdos_pterm(image, status);
}

/* ---- Pexec ---------------------------------------------------------------------------------------
 *
 * FOUR MODES AND THEY ARE NOT A RANGE: 0, 3, 4 and 5, which the two compares at $fc8184/$fc818c
 * carve out of every other word. What each one is, in the order this file reconstructs them:
 *
 *   5  CREATE BASEPAGE.  Cut a TPA out of the largest free block, cut and fill an environment,
 *                        fill the basepage, inherit the parent's handles and directories, copy the
 *                        command tail, and hand the basepage back. Nothing is loaded and nothing
 *                        runs.
 *   4  JUST GO.          Take a basepage somebody already filled, build the child's initial STACK
 *                        inside it, make it `p_run` and leave through the trap epilogue.
 *   3  LOAD.             5, and then read the program into it. HALTS at the loader.
 *   0  LOAD AND GO.      3 and then 4. HALTS at the same loader.
 *
 * THE SPLIT INTO TWO CORES IS THE DISPATCHER'S, for the dispatcher's reason. Between the mode check
 * and the work, `Pexec` saves the outer termination record and arms one of its OWN at $7ef4 — and
 * that record is the 68000 frame of the `jsr` that armed it, which a C core has no counterpart for
 * (`src/gemdos/dispatch.c`). So `gemdos_pexec` is a whole-function differential on the arm that
 * returns BEFORE the record — the refused mode — and everything past it is `gemdos_pexec_create`,
 * entered as a SLICE at $fc8242.
 *
 * WHAT THE RECORD IS FOR, since it is the one thing here that is omitted rather than halted: the
 * file system longjmps to it on a critical error, and `Pexec` then gives back the two descriptors it
 * had cut ($fc8210/$fc8220) and re-longjmps into the OUTER record it saved. Neither half of that is
 * reachable without the file system.
 */

/* $fc817a ($4b) — the mode check, the file lookup, and the record. See the note above for why
 * everything past `gemdos_pexec_create` is a routine of its own.
 *
 * The record ARMED at $fc81e0 is omitted, exactly as the dispatcher's is; the one SAVED at $fc81c2
 * is reproduced, and it is the ROM's own `$fc564a` byte copy — not reconstructed as a routine of its
 * own because thirteen of its fourteen callers are the file system's.
 */
uint32_t gemdos_pexec(uint8_t *image, uint16_t mode_word, uint32_t name, uint32_t tail, uint32_t env)
{
    int16_t mode = (int16_t)mode_word;
    uint32_t byte;

    /* The FILENAME is read by the two modes that load, and by nothing this file reconstructs. */
    (void)name;
    if (mode != PEXEC_LOAD_AND_GO && (mode < PEXEC_LOAD || mode > PEXEC_CREATE_BASEPAGE))
        return GEMDOS_EINVFN;
    if (mode == PEXEC_LOAD_AND_GO || mode == PEXEC_LOAD)
        recreate_not_reconstructed("GEMDOS: Pexec's file lookup ($fc6d14) — EFILNF or the load");
    for (byte = 0; byte < JMPBUF_BYTES; byte++)
        image[PEXEC_OUTER_JMPBUF + byte] = image[GEMDOS_TERMINATION_JMPBUF + byte];
    return gemdos_pexec_create(image, mode_word, name, tail, env);
}

/* How long the environment is: every byte up to and including the DOUBLE NUL that ends the block,
 * rounded up to a word.
 *
 * THE COUNTER IS A WORD AND THE ARITHMETIC IS THE ROM'S, which matters twice: the length is passed
 * to the allocator through `movea.w`, so it is SIGN-EXTENDED (an environment of 32 KB or more asks
 * for a negative number of bytes), and the odd-length test is `btst #0` on the counter's LOW BYTE.
 */
static uint16_t environment_bytes(const uint8_t *image, uint32_t env)
{
    uint16_t length = 0;

    for (;;) {
        if (image[env++] != 0) {
            length++;
            continue;
        }
        if (image[env++] == 0)
            break;
        /* the NUL that ended one string, and the first byte of the next */
        length += 2;
    }
    length += 2;                        /* ...and the pair that ended the block */
    if (length & 1)
        length++;
    return length;
}

/* The basepage half of modes 0, 3 and 5 ($fc824c..$fc84b8). Answers the basepage, or `GEMDOS_ENSMEM`
 * — which is a longword error code in the same slot an address comes back in, exactly as `Malloc`'s
 * 0 is. */
static uint32_t create_basepage(uint8_t *image, int16_t mode, uint32_t tail, uint32_t env)
{
    uint32_t env_md, tpa_md, basepage, owner, cursor, largest;
    uint16_t env_bytes;
    int16_t index;

    if (env == 0)
        env = gemdos_basepage_field(image, gemdos_basepage(image), BASEPAGE_ENV);
    env_bytes = environment_bytes(image, env);

    env_md = gemdos_md_alloc(image, (uint32_t)(int32_t)(int16_t)env_bytes, GEMDOS_MPB);
    if (env_md == 0)
        return GEMDOS_ENSMEM;
    cursor = be32(image + env_md + MD_START);
    while (env_bytes--)
        *gemdos_image_byte(image, cursor++) = *gemdos_image_byte(image, env++);

    /* The TPA is cut in TWO calls: the first asks how big the largest free block is, the second asks
     * for exactly that — so a basepage that will not fit in what is left is refused BEFORE anything
     * is cut, and the environment just cut is given back. */
    largest = gemdos_md_alloc(image, MALLOC_LARGEST_FREE_BLOCK, GEMDOS_MPB);
    if ((int32_t)largest < BASEPAGE_BYTES) {
        gemdos_md_free_insert(image, env_md, GEMDOS_MPB);
        return GEMDOS_ENSMEM;
    }
    tpa_md = gemdos_md_alloc(image, largest, GEMDOS_MPB);
    basepage = be32(image + tpa_md + MD_START);

    /* WHO OWNS THE TWO BLOCKS: the CHILD for a mode that will run it, the CALLER for one that hands
     * the basepage back — so a `Pexec(3)` that is never run leaves the memory chargeable to, and
     * releasable by, the process that asked for it. The `mode == PEXEC_JUST_GO` half of the ROM's
     * own test ($fc8342) is DEAD CODE: mode 4 branched past this whole routine at $fc8248. */
    owner = (mode == PEXEC_LOAD_AND_GO || mode == PEXEC_JUST_GO) ? basepage
                                                                 : gemdos_basepage(image);
    wr32(image + env_md + MD_OWNER, owner);
    wr32(image + tpa_md + MD_OWNER, owner);

    gemdos_set_basepage_field(image, basepage, BASEPAGE_LOWTPA, basepage);
    gemdos_set_basepage_field(image, basepage, BASEPAGE_HITPA,
                              addr_add(basepage, be32(image + tpa_md + MD_LENGTH)));
    /* 256 bytes from +8, which is eight bytes PAST the end of the basepage — the ROM clears one
     * whole basepage starting after the two longwords it has just written. */
    for (index = 0; index < BASEPAGE_BYTES; index++)
        *gemdos_basepage_byte(image, basepage, BASEPAGE_TBASE + (uint32_t)index) = 0;
    gemdos_set_basepage_field(image, basepage, BASEPAGE_DTA,
                              addr_add(basepage, BASEPAGE_COMMAND_TAIL));
    gemdos_set_basepage_field(image, basepage, BASEPAGE_ENV, be32(image + env_md + MD_START));

    /* The parent's six standard handles. A handle naming a FILE is `Fforce`d, so the descriptor's
     * reference count counts the child too; a DEVICE is copied as the byte it is, because there is
     * nothing to take a reference on. */
    for (index = 0; index < BASEPAGE_STANDARD_HANDLES; index++) {
        int16_t handle = gemdos_standard_handle(image, (unsigned)index);

        if (handle > 0)
            gemdos_force_handle(image, index, handle, basepage);
        else
            *gemdos_basepage_byte(image, basepage, BASEPAGE_HANDLES + (uint32_t)index) = (uint8_t)handle;
    }
    /* ...and its sixteen current directories, every one of them, zero or not. */
    for (index = 0; index < BASEPAGE_CURDIR_ENTRIES; index++)
        gemdos_inherit_curdir(image, index,
                              *(const int8_t *)gemdos_basepage_byte(image, gemdos_basepage(image),
                                                                   BASEPAGE_CURDIR + (uint32_t)index),
                              basepage);
    *gemdos_basepage_byte(image, basepage, BASEPAGE_CURDRV) =
        *gemdos_basepage_byte(image, gemdos_basepage(image), BASEPAGE_CURDRV);

    /* The command tail, into the same 128 bytes `p_dta` now points at: up to 125 bytes, stopping at
     * the first NUL, and then a NUL of its own. The first byte copied is the tail's LENGTH byte —
     * this is a Pascal string and the loop does not know it. */
    cursor = addr_add(basepage, BASEPAGE_COMMAND_TAIL);
    for (index = 0; index < PEXEC_COMMAND_TAIL_MAX && *gemdos_image_byte(image, tail) != 0; index++)
        *gemdos_image_byte(image, cursor++) = *gemdos_image_byte(image, tail++);
    *gemdos_image_byte(image, cursor) = 0;
    return basepage;
}

/* The child's initial stack, built downwards from `p_hitpa` ($fc8510..$fc8586), and the four save
 * slots that go with it. What a program entered this way finds is: the basepage at the top of its
 * stack, eleven zero longwords below it, its own entry point below those, a zero WORD, and the
 * return address at $755a. A4 and A5 are handed it as its BSS and DATA bases, which is the register
 * contract every Atari `.PRG` of the period was linked against. */
static void build_child_stack(uint8_t *image, uint32_t basepage)
{
    uint32_t sp = gemdos_basepage_field(image, basepage, BASEPAGE_HITPA);
    int16_t index;

    sp -= 4;
    wr32(gemdos_image_bytes(image, sp, 4), basepage);
    sp -= 4;
    wr32(gemdos_image_bytes(image, sp, 4), 0);
    for (index = 0; index < PEXEC_STACK_ZERO_LONGS; index++) {
        sp -= 4;
        wr32(gemdos_image_bytes(image, sp, 4), 0);
    }
    sp -= 4;
    wr32(gemdos_image_bytes(image, sp, 4), gemdos_basepage_field(image, basepage, BASEPAGE_TBASE));
    sp -= 2;
    wr16(gemdos_image_bytes(image, sp, 2), 0);
    sp -= 4;
    wr32(gemdos_image_bytes(image, sp, 4), PEXEC_RETURN_ADDRESS);

    gemdos_set_basepage_field(image, basepage, BASEPAGE_SAVED_FRAME, sp);
    gemdos_set_basepage_field(image, basepage, BASEPAGE_SAVED_A6, sp);
    gemdos_set_basepage_field(image, basepage, BASEPAGE_SAVED_A5,
                              gemdos_basepage_field(image, basepage, BASEPAGE_DBASE));
    gemdos_set_basepage_field(image, basepage, BASEPAGE_SAVED_A4,
                              gemdos_basepage_field(image, basepage, BASEPAGE_BBASE));
}

/* $fc8242 — `Pexec` past the record it armed, which is every mode that is not refused.
 *
 * MODE 4's `basepage` IS ITS SECOND POINTER ARGUMENT, where every other mode's is the one it has
 * just cut — which is why the ROM overwrites `14(a6)` with the new basepage at $fc84b4 and reads it
 * back at $fc85ce. One variable here, for the same reason.
 */
uint32_t gemdos_pexec_create(uint8_t *image, uint16_t mode_word, uint32_t name, uint32_t tail,
                             uint32_t env)
{
    int16_t mode = (int16_t)mode_word;
    uint32_t basepage = tail;

    (void)name;                         /* see `gemdos_pexec` */
    if (mode != PEXEC_JUST_GO) {
        /* An error code comes back in the same slot an address does, exactly as `Malloc`'s 0 does.
         * Not ambiguous on this machine: every basepage is an address inside a 1 MB TPA. */
        basepage = create_basepage(image, mode, tail, env);
        if (basepage == GEMDOS_ENSMEM)
            return GEMDOS_ENSMEM;
    }
    if (mode == PEXEC_LOAD_AND_GO || mode == PEXEC_LOAD)
        /* $fc85ea, and the release below it: a load that fails gives the whole child back
         * (`gemdos_release_process`) and answers the loader's own error. */
        recreate_not_reconstructed("GEMDOS: Pexec's program loader and relocator ($fc85ea)");
    if (mode != PEXEC_LOAD_AND_GO && mode != PEXEC_JUST_GO)
        return basepage;                /* modes 3 and 5 hand the basepage back and return */

    gemdos_set_basepage_field(image, basepage, BASEPAGE_PARENT, gemdos_basepage(image));
    build_child_stack(image, basepage);
    wr32(image + GEMDOS_P_RUN, basepage);
    /* $fc85c0's `cmpi.w #5` is DEAD CODE — only modes 0 and 4 reach it, both of which go. It is the
     * second such branch in this routine (the owner choice above is the first). */
#ifdef RECREATE_HOST_DIFFERENTIAL
    return basepage;
#else
    __asm__ volatile ("jsr gemdos_trap1_epilogue" : : : "memory");
    __builtin_unreachable();
#endif
}
