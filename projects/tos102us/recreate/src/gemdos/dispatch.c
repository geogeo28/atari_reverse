/* dispatch.c — GEMDOS's C dispatcher, $fc94e4: the one routine every `trap #1` passes through.
 *
 * `src/gemdos/trap1.S` has done everything a 68000 has to do by the time control arrives here — the
 * process is framed, the stack is the OS's, `Super` has already been answered — and what is left is
 * ordinary C over ONE argument: the address of the caller's own words, the function number first.
 *
 * WHAT THE ROUTINE IS, in the order it does it:
 *
 *   1. bump the CALL COUNTER at $68fa (cleared, then incremented, which is two stores)
 *   2. bound the selector from ABOVE — `> $57` answers EINVFN, and no record is read
 *   3. arm the PROCESS-TERMINATION record at $7ef4, which `Pterm` longjmps back to
 *   4. index the table at $fd307a: 88 SIX-byte records, a handler and a DESCRIPTOR word
 *   5. resolve the descriptor into an argument-frame width — and, for the character-device calls,
 *      into whichever handle `Fforce` has redirected their standard handle to
 *   6. copy that many bytes of the caller's words onto the stack and `jsr` the handler
 *
 * WHAT THIS FILE RECONSTRUCTS IS 1, 2, 4, 5's decision and 6. Three arms halt, and each is a whole
 * component of GEMDOS rather than a branch:
 *
 *   * THE TERMINATION RECORD (3) and everything the longjmp comes back to ($fc94f4..$fc973d) — the
 *     record is the 68000 frame of the `jsr` that armed it, which a C core has no counterpart for,
 *     and behind it is process teardown: the open-file table, the two process tables at $8380 and
 *     $8066, and the memory the process owned. It is omitted rather than halted because the ROM
 *     writes it BEFORE any arm this file reconstructs and a halt there would stop every case; what
 *     stands in for it is `test_gemdos_dispatch.py::test_the_termination_record_is_the_callers_own
 *     _frame`, which measures the twelve bytes the ROM leaves and says which frame they are.
 *   * THE REDIRECTED ARMS (5) — a standard handle `Fforce` has pointed at a FILE, so that
 *     `Cconin` becomes an `Fread` and `Cconws` a loop of `Fwrite`s ($fd328a's 19-entry table).
 *   * THE HANDLE-RESOLUTION ARM — a `$80..$83` descriptor on a call whose argument IS a handle
 *     (`Fread`, `Fwrite`, `Fseek`), which walks the open-file descriptors at $8092 and routes a
 *     character device to the console driver.
 *
 * All three need the file system or the character-device group, and neither is reconstructed yet.
 *
 * WHY THE HANDLER IS CALLED THROUGH A HOOK OFF TARGET. The table's handler longwords are ROM
 * addresses; the candidate is host code over a byte array and cannot execute one. So the host build
 * transfers control through `recreate_call_gemdos_handler`, which the CASE binds to the
 * reconstruction of the handler that selector names — the arrangement `src/xbios/supexec.c` and
 * `include/staged_call.h` already make for a routine a RAM vector names. On target it is the ROM's
 * own `jsr` through the table longword, with the caller's words pushed in front of it.
 */
#include <stdint.h>

#include "gemdos.h"
#include "machine.h"
#include "recreate.h"

/* How many BYTES of the caller's words the dispatcher copies for each of the four argument classes,
 * indexed by `descriptor & GEMDOS_DESC_ARGUMENT_MASK`. Not a formula: the widest is 14, which is
 * `Pexec`'s mode word and three longwords, where a fourth long would have made it 16.
 *
 * THE CLASS IS A FRAME WIDTH AND NOT AN ARGUMENT COUNT, which is why a routine taking one word
 * (`Dsetdrv`) and one taking one longword (`Fsetdta`) sit in different classes and why every class
 * pushes MORE than some of its members read — the dispatcher copies a fixed span and the handler
 * takes what it wants of it.
 */
static const uint16_t ARGUMENT_BYTES[GEMDOS_ARGUMENT_CLASSES] = {
    GEMDOS_ARGUMENT_BYTES_0, GEMDOS_ARGUMENT_BYTES_1,
    GEMDOS_ARGUMENT_BYTES_2, GEMDOS_ARGUMENT_BYTES_3,
};

/* WHICH SELECTORS CONSULT A STANDARD HANDLE: the character-device group, 1..11 and 16..19, which is
 * what the ROM's four compares at $fc9762..$fc9784 carve out of the table.
 *
 * A NEGATIVE SELECTOR LANDS HERE TOO, and that is the ROM's shape rather than an oversight of this
 * transcription: the bound at the top of `gemdos_dispatch` is signed and bounds from above only, so
 * `Gemdos(-1)` indexes a record BEFORE the table, and whatever descriptor those bytes spell then
 * arrives at a `< 12` compare that a negative number passes. `<= GEMDOS_REDIRECT_LAST` is that
 * compare. (Selector 0 is excluded first, as the ROM excludes it — though nothing distinguishes it:
 * `Pterm0`'s own descriptor is 0 and the test above this one has already let it past.)
 */
static int selector_consults_a_standard_handle(int selector)
{
    if (selector == 0)
        return 0;
    if (selector <= GEMDOS_REDIRECT_LAST)
        return 1;
    return selector >= GEMDOS_REDIRECT_SECOND_FIRST && selector <= GEMDOS_REDIRECT_SECOND_LAST;
}

/* What a character-device call's descriptor becomes once its standard handle turns out to be a
 * DEVICE after all — i.e. nothing redirected it. The handler is about to be called directly, so the
 * only thing left to say is how wide its argument frame is: the two console calls that take a
 * string get one pointer, and the rest take nothing. The table's own $80..$83 is discarded here,
 * which is why a `Cconin` record says $80 and a `Cconin` call pushes four bytes. */
static uint16_t descriptor_for_a_device(int selector)
{
    return (selector == GEMDOS_CCONWS_FN || selector == GEMDOS_CCONRS_FN) ? 1 : 0;
}

/* The `jsr` through the table's handler longword, with `argument_bytes` of the caller's own words
 * copied in front of it.
 *
 * `arguments` is the FIRST argument word — one word past the function number — so the span pushed is
 * `[arguments, arguments + argument_bytes)`, and it is pushed from the TOP DOWN so that the first
 * word ends up nearest the return address. That is what the ROM's four arms do: each is a
 * straight-line `move.w` chain from the highest word to the lowest, and they differ in nothing but
 * their length, so the copy is one loop here. The COST differs from the ROM's for that reason and
 * the Tier 3 row says by how much; what is pushed does not.
 *
 * OFF TARGET the handler is a ROM address, so the hook stands in; the case binds it to the
 * reconstruction of the handler that selector names.
 *
 * THE POP COUNT LIVES IN D3 ACROSS THE `jsr`, AND THAT IS A CORRECTNESS CHOICE. The handler is a
 * whole GEMDOS leaf: a `Cauxout` reaches `xconout_rs232`, whose `move.b $fffc00,d2` writes D2, and
 * so do `Cprnout` and a `Cconout` of BEL. D2 is scratch in both ABIs, so a count parked there would
 * come back changed and the `adda.l` would unwind the wrong span. D3 is callee-saved in both and is
 * restored by the trap on the way out. "d2" is in the clobber list for the other half of the same
 * fact: GCC uses D2 in this function and must not believe it survived the call.
 *
 * NO SURFACE PINS IT TODAY, and that is said here rather than left to be discovered. Off target the
 * handler is the hook, which is C and writes no 68000 register; the only place the `jsr` reaches a
 * real driver is the BENCH BLOB, and every dispatcher row registered so far names a handler whose
 * whole body is a `moveq`. The row that WOULD pin it is a dispatcher-slice case on a
 * character-device selector — `Cauxout` reaching `xconout_rs232` — and `recreate/STATUS.md` carries
 * it as an unpinned item rather than as a case nobody wrote.
 */
static uint32_t call_handler(uint8_t *image, uint32_t handler, uint32_t arguments,
                             uint16_t argument_bytes)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return (uint32_t)recreate_call_gemdos_handler(image, handler, arguments, argument_bytes);
#else
    register uint32_t target __asm__("a0") = handler;
    register uint32_t word __asm__("a1") = arguments + argument_bytes;
    register uint32_t remaining __asm__("d1") = argument_bytes;
    register uint32_t pushed __asm__("d3") = argument_bytes;
    /* Pinned to D0 because that is where the `jsr` leaves it: the handler's result is the whole of
     * what the dispatcher returns, and an output GCC allocated elsewhere would never be written. */
    register uint32_t result __asm__("d0");

    (void)image;
    __asm__ volatile ("1:\tmove.w -(%[word]),-(%%sp)\n\t"
                      "subq.l #2,%[remaining]\n\t"
                      "bne.s 1b\n\t"
                      "jsr (%[target])\n\t"
                      "adda.l %[pushed],%%sp"
                      : "=d"(result), [target] "+a"(target), [word] "+a"(word),
                        [remaining] "+d"(remaining), [pushed] "+d"(pushed)
                      :
                      : "d2", "a2", "memory", "cc");
    return result;
#endif
}

/* $fc973e — the dispatcher PAST its termination record: the table lookup, the descriptor and the
 * call. A routine of its own because that record is where the reconstruction stops being able to
 * enter at $fc94e4 (see the header), so this is what the battery enters as a slice. */
uint32_t gemdos_dispatch_selector(uint8_t *image, uint32_t arguments)
{
    int selector = (int16_t)be16(image + arguments);
    uint16_t descriptor = gemdos_descriptor(image, selector);

    if (descriptor != 0 && selector_consults_a_standard_handle(selector)) {
        if (gemdos_standard_handle(image, descriptor & GEMDOS_DESC_ARGUMENT_MASK) > 0)
            recreate_not_reconstructed("GEMDOS: a standard handle Fforce redirected to a file");
        descriptor = descriptor_for_a_device(selector);
    }
    if (descriptor & GEMDOS_DESC_HANDLE)
        recreate_not_reconstructed("GEMDOS: a call whose argument is an open-file handle");
    if (selector == GEMDOS_FOPEN_FN || selector == GEMDOS_FCREATE_FN)
        recreate_not_reconstructed("GEMDOS: Fopen/Fcreate's device-name arm");

    descriptor &= GEMDOS_DESC_ARGUMENT_MASK;
    /* THE ROM'S FOUR ARMS ARE FOUR COMPARES, not a table, so a class of 4 or more FALLS THROUGH
     * them ($fc9cb8) and returns the result it has accumulated — which is the zero cleared above,
     * since the only thing that sets it is the device-name arm that halts. Unreachable with this
     * ROM's own table (`test_gemdos_dispatch.py` checks every record and every record a negative
     * selector can reach), and written out because the alternative is an index off the end of
     * `ARGUMENT_BYTES`. */
    if (descriptor >= GEMDOS_ARGUMENT_CLASSES)
        return 0;
    return call_handler(image, gemdos_handler(image, selector), arguments + GEMDOS_ARGUMENT_WORD,
                        ARGUMENT_BYTES[descriptor]);
}

/* $fc94e4 — the dispatcher itself. `arguments` is the address of the caller's words, which is what
 * the trap entry's `lea 50(frame),a0` computed and pushed.
 *
 * THE BOUND IS SIGNED AND BOUNDS FROM ABOVE ONLY, which is the same shape the BIOS dispatcher has
 * (`src/bios/trap.S`): `Gemdos($58)` answers EINVFN having read no record, and `Gemdos(-1)` passes
 * and indexes six bytes BEFORE the table. The negative arm is transcribed rather than guarded
 * against, in `selector_consults_a_standard_handle` above and in the index arithmetic here.
 *
 * The termination record the ROM arms between the bound and the dispatch is NOT written here — the
 * header says why, and `test_gemdos_dispatch.py` is what holds the omission to its measured size.
 */
uint32_t gemdos_dispatch(uint8_t *image, uint32_t arguments)
{
    int selector = (int16_t)be16(image + arguments);

    /* Two stores, not one: the ROM clears the counter on entry and increments it at a label the
     * termination path branches BACK to, so a call that outlives a process restart counts twice. */
    wr16(image + GEMDOS_CALL_DEPTH, 0);
    wr16(image + GEMDOS_CALL_DEPTH, (uint16_t)(be16(image + GEMDOS_CALL_DEPTH) + 1));

    if (selector > GEMDOS_MAX_SELECTOR)
        return GEMDOS_EINVFN;
    return gemdos_dispatch_selector(image, arguments);
}

#ifdef RECREATE_HOST_DIFFERENTIAL
/* The one definition of the two hooks `include/gemdos.h` declares. On target this file's target
 * build has neither: the machine has a `jsr` and a `trap #14`. */
int32_t (*recreate_call_gemdos_handler)(uint8_t *image, uint32_t handler, uint32_t arguments,
                                        uint16_t argument_bytes);
void (*recreate_publish_clock)(uint8_t *image, uint16_t date, uint16_t time);
#endif
