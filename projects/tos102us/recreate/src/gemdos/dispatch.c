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
 * WHAT THIS FILE RECONSTRUCTS IS 1, 2, 4, 5 and 6, and the three arms 5 and 6 hide:
 *
 *   * THE REDIRECTED ARMS — a standard handle `Fforce` has pointed at a FILE, so that `Cconin`
 *     becomes an `Fread` of one byte and `Cconws` a loop of one-byte `Fwrite`s ($fd328a's 19-entry
 *     table). They call `Fread`/`Fwrite` BY ADDRESS, not through the table, and so does this file.
 *   * THE DEVICE ARM under the handle resolution ($fc9924): an `Fread`/`Fwrite` whose handle names a
 *     CHARACTER DEVICE is served here, out of `src/gemdos/console.c`'s layer, and no handler is called.
 *   * THE DEVICE-NAME ARM ($fc9aca): `Fopen`/`Fcreate` of "CON:", "AUX:" or "PRN:" answers the
 *     device's handle and never reaches the file system.
 *
 * ONE THING IS OMITTED, and it is a whole component of GEMDOS rather than a branch:
 *
 *   * THE TERMINATION RECORD (3) and everything the longjmp comes back to ($fc94f4..$fc973d) — the
 *     record is the 68000 frame of the `jsr` that armed it, which a C core has no counterpart for,
 *     and behind it is process teardown and the media-change recovery ($fc951e: the drive's DNDs,
 *     OFDs and DMD freed and the drive logged in again). It is omitted rather than halted because
 *     the ROM writes it BEFORE any arm this file reconstructs and a halt there would stop every
 *     case; what stands in for it is `test_gemdos_dispatch.py::test_the_termination_record_is_the_
 *     callers_own_frame`, which measures the twelve bytes the ROM leaves and says which frame they
 *     are. The longjmps INTO it are halted where they are thrown (`src/gemdos/fs_disk.c`).
 *
 * THREE ROM BUGS the redirected arms carry, transcribed rather than fixed (each has its case):
 *
 *   * a redirected `Cconout`/`Cauxout`/`Cprnout` writes the WRONG BYTE: its buffer pointer is the
 *     character word in the HIGH half of a longword whose low half is left over from the `setjmp`
 *     call ($7ef4), so `Cconout('\n')` writes the byte at $0a7ef4, and any printable character one
 *     from $207ef4 up — past the end of a 1 MB machine (`redirected_write_character`);
 *   * a redirected `Cconrs` reads its maximum SIGNED, so a buffer asking for 128..255 characters
 *     takes up to 65,408..65,535 — in practice, to the next CR or the end of the file, past the end
 *     of the caller's buffer (`redirected_read_line`);
 *   * a redirected `Cconin` at the end of its file answers whatever byte the frame already held: the
 *     `Fread`'s own answer is never looked at (`redirected_read_character`).
 *
 * WHY THE HANDLER IS CALLED THROUGH A HOOK OFF TARGET. The table's handler longwords are ROM
 * addresses; the candidate is host code over a byte array and cannot execute one. So the host build
 * transfers control through `recreate_call_gemdos_handler`, which the CASE binds to the
 * reconstruction of the handler that selector names — the arrangement `src/xbios/supexec.c` and
 * `include/staged_call.h` already make for a routine a RAM vector names. On target it is the ROM's
 * own `jsr` through the table longword, with the caller's words pushed in front of it.
 */
#include <stdint.h>

#include "gemdos/console.h"
#include "gemdos/fs.h"
#include "gemdos/fs_drive.h"
#include "gemdos/fs_io.h"
#include "gemdos/gemdos.h"
#include "gemdos/memory.h"
#include "gemdos/process.h"
#include "m68k_idioms.h"
#include "machine.h"
#include "os.h"
#include "recreate.h"

/* An `Fread`/`Fwrite` frame, from the caller's function number: the handle word, the count longword —
 * whose HIGH half the device arm tests alone (`tst.w 4(a0)`) and whose LOW half is the whole count it
 * uses (`6(a0)`) — and the buffer (`addq.l #8` at $fc99c8). `$fc5078`'s frame is the same four fields. */
#define IO_HANDLE       GEMDOS_ARGUMENT_WORD
#define IO_COUNT        4
#define IO_COUNT_LOW    6
#define IO_BUFFER       8
_Static_assert(GEMDOS_HOST_SLOT_C_ENTRY_ARGUMENTS_BYTES == IO_BUFFER + 4,
               "the C entry's host slot is not the four words `$fc5078`'s caller pushes");
/* `subq.w #1 / asl.w #2` at $fc98e8: the redirection table is longwords indexed from `Cconin`. */
#define REDIRECT_ENTRY_BYTES 4

#ifdef RECREATE_HOST_DIFFERENTIAL
/* `include/gemdos/gemdos.h`'s host-slot guard: defined in the dispatcher, the one core every GEMDOS
 * routine sits under, rather than beside any one of the slots' users. */
unsigned gemdos_host_slots_held;
#endif

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

/* ================================================================================================
 * The REDIRECTED arms: a character-device call whose standard handle names a FILE ($fd328a).
 *
 * EACH GROUP OF ARMS IS BEHIND ONE CALL out of `gemdos_dispatch_selector` — the character-device
 * group (`character_call`, these arms inlined into it but the two READS kept out of line, so that their
 * frame locals do not widen it), the handle arm (`call_on_a_handle`, the resolution and the device arm
 * inlined into it) and the device-name arm (`open_or_create`) — and that is for the call every program
 * makes rather than for them: inlined, their registers land in `gemdos_dispatch_selector`'s own prologue
 * and every dispatch pays for them. The `Sversion` slice measures 490 cycles this way, 506 with the
 * character group inline and 544 with every arm inline (`bench/tier3.py`). Only the status calls'
 * constant is answered in the dispatcher itself: behind the call, `Cconis` measured 1.46x.
 * ============================================================================================= */

/* $fc5078 — GEMDOS called from INSIDE GEMDOS: `Fwrite(handle, count, buffer)` pushed as a caller's
 * four words and their ADDRESS handed to the whole dispatcher, exactly as a `trap #1` would hand it
 * a program's. So the call is dispatched afresh — counter, bound, table, handle resolution — and a
 * `handle` that is a STANDARD handle is resolved through the running process's own `p_uft`.
 *
 * WRITTEN IN C ON BOTH BUILDS, and not through `src/gemdos/trap1.S`'s transcription of the same door
 * (`gemdos_entry_c`), for two reasons. That door's `jsr` is to the ABSOLUTE $fc94e4, which is the ROM's
 * own dispatcher until this one is linked there — through it, the target build's echo would run the
 * ROM's nested dispatch and not this file's. And the host build has no 68000 to run it at all, so the
 * C would exist anyway: the door on target alone would make the two builds run different code for one
 * arm. The words are the door's own frame, laid in the host slot off target and in this local on it. */
static uint32_t nested_fwrite(uint8_t *image, int16_t handle, uint32_t count, uint32_t buffer)
{
    uint8_t words_local[GEMDOS_HOST_SLOT_C_ENTRY_ARGUMENTS_BYTES];
    uint32_t words = gemdos_host_slot_claim(C_ENTRY_ARGUMENTS, words_local);
    uint32_t result;

    wr16(image + words, GEMDOS_FWRITE_FN);
    wr16(image + words + IO_HANDLE, (uint16_t)handle);
    wr32(image + words + IO_COUNT, count);
    wr32(image + words + IO_BUFFER, buffer);
    result = gemdos_dispatch(image, words);
    gemdos_host_slot_release(C_ENTRY_ARGUMENTS);
    return result;
}

/* $fc97b6 — `Cconin`, `Cauxin`, `Crawcin` and `Cnecin` over a file: `Fread` one byte into the frame
 * (`-14(a6)`, `GEMDOS_DISPATCH_REDIRECTED_BYTE_LOCAL`) and answer it SIGN-EXTENDED. What `Fread` answered
 * is never looked at, so at the end of the file the answer is whatever that frame byte already held.
 *
 * THAT STALE BYTE IS PINNED OFF TARGET ONLY. There the byte is the host slot, a fixed address a case
 * stages with the same stale value as the ROM's `-14(a6)`, and the two agree. ON TARGET it is `byte_local`
 * — an uninitialised local of THIS function's frame, not a byte of the dispatcher's — so at the end of
 * the file the target answers whatever its own stack held there: a divergence no host case can see (the
 * bench's second differential of that case answers 0 where the ROM leaves $FFFFFF9C), and
 * `recreate/STATUS.md` lists it. No host slot could close it: the ROM's byte lives in a frame the target
 * build does not have. */
__attribute__((noinline))
static uint32_t redirected_read_character(uint8_t *image, int16_t handle)
{
    uint8_t byte_local;
    uint32_t byte = gemdos_host_slot_claim(REDIRECTED_BYTE, &byte_local);
    uint32_t result;

    gemdos_fread(image, handle, 1, byte);
    result = sign_ext8(image[byte]);
    gemdos_host_slot_release(REDIRECTED_BYTE);
    return result;
}

/* $fc97dc — `Cconout`, `Cauxout` and `Cprnout` over a file, and a ROM BUG: `move.w 2(a0),(sp)` puts
 * the character word in the HIGH half of the stack slot the `Fwrite` takes as its BUFFER POINTER,
 * whose low half still holds what the `setjmp` call left there — `move.l #$7ef4,(sp)`, the record's
 * address. So one byte is written from `(character << 16) | $7ef4`, and it is not the character.
 *
 * THE POINTER IS FOLDED ONTO THE 24-BIT BUS here, where it is formed: the character word's high byte
 * lands above A23, which the 68000 does not have, so `Cconout($010a)` reads the byte at $0a7ef4. The
 * host indexes its image with the pointer as it stands and would read 16 MB past it instead.
 *
 * ONLY A CHARACTER BELOW $10 NAMES A BYTE OF THE 1 MB MACHINE: from $107ef4 up the pointer is past the
 * RAM — the image's end on the host — and a low byte of $ff is the I/O page ($ff7ef4), which the oracle
 * decodes and the host image does not have. The host bound refuses both by name rather than reading
 * past the array; neither shore can be staged, and `recreate/STATUS.md` lists the arm as unpinned. */
static uint32_t redirected_write_character(uint8_t *image, int16_t handle, uint16_t character)
{
    uint32_t buffer = (((uint32_t)character << M68K_WORD_BITS) | (uint16_t)GEMDOS_TERMINATION_JMPBUF)
                      & OS_BUS_ADDR_MASK;

    gemdos_assert_inside_ram(buffer, 1);
    return gemdos_fwrite(image, handle, 1, buffer);
}

/* $fc97fa — `Cconws` over a file: one `Fwrite` of one byte per character, the NUL not written. The
 * answer is the last `Fwrite`'s — or, for an empty string, `entry_d0`: nothing in the arm writes D0. */
static uint32_t redirected_write_string(uint8_t *image, uint32_t entry_d0, int16_t handle, uint32_t string)
{
    uint32_t result = entry_d0;

    for (; image[string] != 0; string = addr_add(string, 1))
        result = gemdos_fwrite(image, handle, 1, string);
    return result;
}

/* $fc982c — `Cconrs` over a file: one byte at a time into the line, each ECHOED to stdout through a
 * nested `Fwrite` ($fc5078), until the maximum, the end of the file or a CR — which is echoed, left in
 * the buffer uncounted, and followed by one more `Fread` to swallow its LF. Answers 0.
 *
 * THE MAXIMUM IS READ SIGNED (`move.b (a0),d0 / ext.w d0`), and the count-down is a word tested
 * BEFORE it is decremented: a maximum of 128 counts down from $ff80, so it bounds nothing a line
 * would reach. The console leaf's own `Cconrs` masks the same byte to 0..255 (`src/gemdos/console.c`).
 *
 * A DIVERGENCE, and the one this file's omission of the termination record makes visible: each echo is
 * a whole nested dispatch, which in the ROM re-arms the record at $7ef4 with its own frame — so after an
 * echoing `Cconrs` the record points into a nested frame that is dead once the echo returns. The C arms
 * no record, nested or not, and leaves those twelve bytes as they were. The cases drop the span from
 * their compare by name (`test/dispatch_io.py`, `NESTED_RECORD`). */
__attribute__((noinline))
static uint32_t redirected_read_line(uint8_t *image, int16_t handle, uint32_t buffer)
{
    uint16_t left = (uint16_t)sign_ext8(image[addr_add(buffer, GEMDOS_CCONRS_MAX)]);
    uint32_t at = addr_add(buffer, GEMDOS_CCONRS_TEXT);
    uint16_t length = 0;

    while (left-- != 0) {
        if (gemdos_fread(image, handle, 1, at) != 1)
            break;
        nested_fwrite(image, GEMDOS_STDOUT, 1, at);
        if (image[at] == CON_CR) {
            uint8_t byte_local;

            gemdos_fread(image, handle, 1, gemdos_host_slot_claim(REDIRECTED_BYTE, &byte_local));
            gemdos_host_slot_release(REDIRECTED_BYTE);
            break;
        }
        length++;
        at = addr_add(at, 1);
    }
    image[addr_add(buffer, GEMDOS_CCONRS_LENGTH)] = (uint8_t)length;
    return 0;
}

/* What D0 holds when the table's `jmp (a0)` lands ($fc98fc): the record address the lookup computed
 * (`muls.w #6 / add.l #$fd307a`) under the jump's own byte index (`subq.w #1 / asl.w #2` rewrite its
 * low word only). The empty `Cconws` is the one arm that hands it back. */
static uint32_t redirect_jump_d0(int selector)
{
    return set_low_word(gemdos_record(selector),
                        (uint16_t)((selector - GEMDOS_REDIRECT_FIRST) * REDIRECT_ENTRY_BYTES));
}

/* The five STATUS calls' entry ($fc98dc): `Cconis`, and all four of the second run. */
static int is_a_status_call(int selector)
{
    return selector == GEMDOS_CCONIS_FN || selector >= GEMDOS_REDIRECT_SECOND_FIRST;
}

/* The table's other arms, by selector — the status calls' constant is answered before this is reached
 * (`gemdos_dispatch_selector`), so that the cheapest arm pays for no call at all. `Crawio`'s
 * entry ($fc97aa: read on `$00ff`, write otherwise) is NOT here because nothing can reach it: its
 * descriptor is 0, so the dispatcher never consults its standard handle (`test_gemdos_dispatch.py`).
 * Entries 12..15 name the device arm, which is where the group test already sends those selectors. Both
 * are HALTED rather than folded into another arm: a selector that did arrive would be a table this
 * reconstruction does not describe. */
__attribute__((always_inline))
static inline uint32_t redirected_call(uint8_t *image, uint32_t arguments, int selector, int16_t handle)
{
    uint32_t argument = addr_add(arguments, GEMDOS_ARGUMENT_WORD);

    switch (selector) {
    case GEMDOS_CCONIN_FN:
    case GEMDOS_CAUXIN_FN:
    case GEMDOS_CRAWCIN_FN:
    case GEMDOS_CNECIN_FN:
        return redirected_read_character(image, handle);
    case GEMDOS_CCONOUT_FN:
    case GEMDOS_CAUXOUT_FN:
    case GEMDOS_CPRNOUT_FN:
        return redirected_write_character(image, handle, be16(image + argument));
    case GEMDOS_CCONWS_FN:
        return redirected_write_string(image, redirect_jump_d0(selector), handle, be32(image + argument));
    case GEMDOS_CCONRS_FN:
        return redirected_read_line(image, handle, be32(image + argument));
    default:
        recreate_not_reconstructed("GEMDOS: a redirection-table entry no selector reaches — Crawio's "
                                   "($fc97aa, descriptor 0) or 12..15's (outside the character group)");
    }
}

/* ================================================================================================
 * The DEVICE arm: an `Fread`/`Fwrite` whose handle argument resolved to a character device ($fc99bc).
 * ============================================================================================= */

/* One record off the device and its low byte stored, answering 1 — or, for any other count, the line
 * editor into the buffer, answering the length it left (`ext.l`). The record is echoed either way. */
static uint32_t device_read(uint8_t *image, uint16_t device, uint16_t count, uint32_t buffer)
{
    if (count == 1) {
        image[buffer] = (uint8_t)gemdos_device_get_echoing(image, device);
        return 1;
    }
    return sign_ext16(gemdos_device_read_line(image, 0, device, count, buffer));
}

/* Each byte SIGN-EXTENDED to the device — the console through its TAB expander, AUX: and PRN: straight
 * to `Bconout` — and the count answered as the SIGNED word it was compared as: a count of $8000..$ffff
 * writes nothing and answers a negative number. */
static uint32_t device_write(uint8_t *image, uint16_t device, uint16_t count, uint32_t buffer)
{
    int16_t written;

    for (written = 0; (int16_t)count > written; written++) {
        uint16_t character = (uint16_t)sign_ext8(image[addr_add(buffer, (uint32_t)written)]);

        if (device == GEMDOS_CONSOLE_DEVICE)
            gemdos_device_put_expanding_tabs(image, device, character);
        else
            gemdos_device_bconout(image, BIOS_RETURN_DEVICE_WRITE, device, character);
    }
    return sign_ext16(count);
}

/* The device is the resolved handle's low word plus three (`addq.w #3`), as in `src/gemdos/console.c`.
 * Only `Fread` and `Fwrite` are served — `Fseek` on a device answers 0 — and only a count whose high
 * word is 0: 64 KB or more answers 0 with nothing moved. */
__attribute__((always_inline))
static inline uint32_t device_io(uint8_t *image, uint32_t arguments, int selector, int32_t named)
{
    uint16_t device = (uint16_t)((uint16_t)named + GEMDOS_HANDLE_TO_DEVICE);
    uint16_t count = be16(image + arguments + IO_COUNT_LOW);
    uint32_t buffer = be32(image + arguments + IO_BUFFER);

    if (selector != GEMDOS_FREAD_FN && selector != GEMDOS_FWRITE_FN)
        return 0;
    if (be16(image + arguments + IO_COUNT) != 0)
        return 0;
    if (selector == GEMDOS_FREAD_FN)
        return device_read(image, device, count, buffer);
    return device_write(image, device, count, buffer);
}

/* ================================================================================================
 * The DEVICE-NAME arm: `Fopen` and `Fcreate` of a device ($fc9aca).
 * ============================================================================================= */

/* The handle a device NAME stands for, as the unsigned word the dispatcher answers — or 0 for any
 * other name, which goes on to the handler. Each device is spelt twice, upper case then lower, and
 * compared with its NUL (`GEMDOS_DEVICE_NAME_BYTES`), so "CON:" and "con:" match and "Con:",
 * "CON:X" and "A:CON:" do not. */
static uint32_t device_named(const uint8_t *image, uint32_t name)
{
    uint16_t device;

    for (device = 0; device < GEMDOS_DEVICE_NAME_COUNT; device++) {
        uint32_t upper = GEMDOS_DEVICE_NAMES + device * GEMDOS_DEVICE_NAME_SPELLINGS * GEMDOS_DEVICE_NAME_BYTES;
        uint32_t lower = upper + GEMDOS_DEVICE_NAME_BYTES;

        if ((uint16_t)gemdos_strneq(0, image, GEMDOS_DEVICE_NAME_BYTES, name, upper) != 0
            || (uint16_t)gemdos_strneq(0, image, GEMDOS_DEVICE_NAME_BYTES, name, lower) != 0)
            return (uint16_t)(GEMDOS_CON_HANDLE - device);
    }
    return 0;
}

/* ================================================================================================
 * The MEDIA-CHANGE RECOVERY's two helpers ($fc93f4, $fc9468).
 *
 * When a file-system call longjmps back with E_CHG, the dispatcher throws the drive's whole in-memory
 * picture away ($fc951e): the handle records' open files on it, the FAT's OFD, every directory node
 * that names its DMD, the DND tree from its root, the DMD — then asks `Getbpb` again and rebuilds
 * the drive ($fc53c0) before dispatching the call afresh. The recovery itself is behind the longjmp
 * this reconstruction does not have (the header), and so are its only calls to these two; they are
 * reconstructed and proved at their own addresses, ahead of it.
 * ============================================================================================= */

/* $fc93f4 — a DND and everything reachable from it given back to the pool, depth first: its first
 * child's tree, then its NEXT SIBLING's tree, then the OFD its directory is read through, then every
 * slot of the directory-node table still naming it (the reference counts beside them are left alone),
 * then the DND itself. Entered with a drive's root, whose sibling is 0, it frees the whole tree. */
void gemdos_free_dnd_tree(uint8_t *image, uint32_t dnd)
{
    int16_t node;

    if (be32(image + dnd + DND_CHILD) != 0)
        gemdos_free_dnd_tree(image, be32(image + dnd + DND_CHILD));
    if (be32(image + dnd + DND_SIBLING) != 0)
        gemdos_free_dnd_tree(image, be32(image + dnd + DND_SIBLING));
    if (be32(image + dnd + DND_OFD) != 0)
        gemdos_pool_free(image, be32(image + dnd + DND_OFD));
    for (node = 0; node < GEMDOS_DIRECTORY_NODE_COUNT; node++)
        if (be32(image + gemdos_node_slot(node)) == dnd)
            wr32(image + gemdos_node_slot(node), 0);
    gemdos_pool_free(image, dnd);
}

/* $fc9468 — every handle record naming an open file on a drive, its OFD given back to the pool and
 * the record cleared (value, owner AND reference count). A record naming a device or nothing
 * (`ble`) is passed over.
 *
 * A ROM BUG, and the reason for the parameter: the routine NEVER LOADS ITS ARGUMENT. Its prologue
 * saves A4 (`movem.l d6-d7/a4-a5,-(sp)`) and nothing moves `8(a6)` into it, so the drive each OFD is
 * compared against is whatever its CALLER left in A4 — `$fc9558` pushes the DMD and the comparison
 * never sees it. The C therefore takes that register, as `caller_a4`, and not the pushed DMD. */
void gemdos_free_drive_ofds(uint8_t *image, uint32_t caller_a4)
{
    int16_t index;

    for (index = 0; index < GEMDOS_HANDLE_COUNT; index++) {
        uint32_t descriptor = gemdos_descriptor_at(index);
        int32_t ofd = (int32_t)be32(image + descriptor + HANDLE_VALUE);

        if (ofd <= 0 || be32(image + (uint32_t)ofd + OFD_DMD) != caller_a4)
            continue;
        gemdos_pool_free(image, (uint32_t)ofd);
        gemdos_release_descriptor(image, descriptor);
        wr16(image + descriptor + HANDLE_REFCOUNT, 0);
    }
}

/* ================================================================================================
 * The dispatch.
 * ============================================================================================= */

/* The `jsr` through the table, in the frame the descriptor's class names.
 *
 * THE ROM'S FOUR ARMS ARE FOUR COMPARES, not a table, so a class of 4 or more FALLS THROUGH them
 * ($fc9cb8) and returns the result it has accumulated — the zero `$fc9ac6` cleared, since the only
 * thing that sets it is the device-name arm, which has already answered. Unreachable with this ROM's
 * own table (`test_gemdos_dispatch.py` checks every record and every record a negative selector can
 * reach), and written out because the alternative is an index off the end of `ARGUMENT_BYTES`. */
__attribute__((always_inline))
static inline uint32_t call_the_handler(uint8_t *image, uint32_t arguments, int selector, uint16_t descriptor)
{
    descriptor &= GEMDOS_DESC_ARGUMENT_MASK;
    if (descriptor >= GEMDOS_ARGUMENT_CLASSES)
        return 0;
    return call_handler(image, gemdos_handler(image, selector), arguments + GEMDOS_ARGUMENT_WORD,
                        ARGUMENT_BYTES[descriptor]);
}

/* $fc9aca — `Fopen` and `Fcreate`: a device's handle for a device's name, the handler for any other. */
__attribute__((noinline))
static uint32_t open_or_create(uint8_t *image, uint32_t arguments, int selector, uint16_t descriptor)
{
    uint32_t device = device_named(image, be32(image + arguments + GEMDOS_ARGUMENT_WORD));

    if (device != 0)
        return device;
    return call_the_handler(image, arguments, selector, descriptor);
}

/* $fc9924 — which handle a call's arguments name, and what it resolves to.
 *
 * WHICH WORD holds the handle is the descriptor's to say, and it says it by being $81: that is
 * `Fseek`, whose first argument is a LONGWORD offset, so its handle is the third word. `Fread` and
 * `Fwrite` are $82 and take the handle first. No other selector reaches here — the character-device
 * group has had its descriptor rewritten by the time the `btst #7` runs (`gemdos_dispatch_selector`).
 *
 * The walk itself is `include/gemdos/process.h`'s three kinds, and what comes back is a LONGWORD rather than
 * a handle: 0 for a handle that names nothing, negative for a character device, and the file
 * system's own pointer otherwise.
 */
__attribute__((always_inline))
static inline int32_t resolve_handle(const uint8_t *image, uint32_t arguments, uint16_t descriptor)
{
    uint32_t at = arguments + (descriptor == GEMDOS_DESC_HANDLE_AT_THIRD_WORD
                               ? GEMDOS_ARGUMENT_THIRD_WORD : GEMDOS_ARGUMENT_WORD);
    int16_t handle = (int16_t)be16(image + at);

    if (handle >= GEMDOS_FIRST_FILE_HANDLE)
        return (int32_t)be32(image + gemdos_descriptor_of(handle) + HANDLE_VALUE);
    if (handle < 0)
        return handle;
    handle = gemdos_standard_handle(image, (unsigned)handle);
    if (handle > 0)
        return (int32_t)be32(image + gemdos_descriptor_of(handle) + HANDLE_VALUE);
    return handle;
}

/* $fc9924 — the handle argument RESOLVED before the call is made at all, which is the one thing the
 * dispatcher does that a handler could not do for itself: an `Fread` on a handle that has been `Fforce`d
 * onto the console must become a console read, and only the dispatcher knows the descriptor said "this
 * argument is a handle".
 *
 * Three outcomes: 0 is a handle that names nothing and is EIHNDL, having made no call; a NEGATIVE
 * resolution is a character device, served by the device arm; and anything else is the file system's
 * own pointer, which goes on to the handler exactly as the ROM's `bge $fc9ac6` does — `Fread`, `Fwrite`
 * and `Fseek` are the only selectors whose descriptor names a handle, so the device-name test between
 * that branch and the call never matches one of them.
 *
 * ONE CALL HOLDING THE WHOLE ARM, the resolution and the device arm inlined into it, for the reason the
 * other arms are calls (above) — and inlined because the fixed cost was the calls: with the resolution
 * in another file and the device arm a call of its own, a one-byte `Fwrite` to AUX: measured 1.17x
 * and an `Fseek` on the console 1.37x, where they are now 1.07x each. */
__attribute__((noinline))
static uint32_t call_on_a_handle(uint8_t *image, uint32_t arguments, int selector, uint16_t descriptor)
{
    int32_t named = resolve_handle(image, arguments, descriptor);

    if (named == 0)
        return GEMDOS_EIHNDL;
    if (named < 0)
        return device_io(image, arguments, selector, named);
    return call_the_handler(image, arguments, selector, descriptor);
}

/* $fc9762..$fc98fe — a character-device call, whose standard handle decides everything: a FILE takes the
 * redirection table's arm, and a DEVICE — nothing redirected it — calls the handler directly, in the
 * argument frame `descriptor_for_a_device` rewrites. A negative selector passed the group test and misses
 * the table's own bound (`cmp.w #18 / bhi` on `selector - 1`), so it takes the device's. A call of its
 * own, like the arms under it. */
__attribute__((noinline))
static uint32_t character_call(uint8_t *image, uint32_t arguments, int selector, int8_t standard)
{
    if (standard > 0 && selector >= GEMDOS_REDIRECT_FIRST)
        return redirected_call(image, arguments, selector, standard);
    return call_the_handler(image, arguments, selector, descriptor_for_a_device(selector));
}

/* $fc973e — the dispatcher PAST its termination record: the table lookup, the descriptor and the
 * call. A routine of its own because that record is where the reconstruction stops being able to
 * enter at $fc94e4 (see the header), so this is what the battery enters as a slice. */
uint32_t gemdos_dispatch_selector(uint8_t *image, uint32_t arguments)
{
    int selector = (int16_t)be16(image + arguments);
    uint16_t descriptor = gemdos_descriptor(image, selector);

    if (descriptor != 0 && selector_consults_a_standard_handle(selector)) {
        int8_t standard = gemdos_standard_handle(image, descriptor & GEMDOS_DESC_ARGUMENT_MASK);

        if (standard > 0 && selector >= GEMDOS_REDIRECT_FIRST && is_a_status_call(selector))
            return GEMDOS_REDIRECTED_READY;
        return character_call(image, arguments, selector, standard);
    }
    if (descriptor & GEMDOS_DESC_HANDLE)
        return call_on_a_handle(image, arguments, selector, descriptor);
    if (selector == GEMDOS_FOPEN_FN || selector == GEMDOS_FCREATE_FN)
        return open_or_create(image, arguments, selector, descriptor);
    return call_the_handler(image, arguments, selector, descriptor);
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
/* The one definition of the two hooks `include/gemdos/gemdos.h` declares. On target this file's target
 * build has neither: the machine has a `jsr` and a `trap #14`. */
int32_t (*recreate_call_gemdos_handler)(uint8_t *image, uint32_t handler, uint32_t arguments,
                                        uint16_t argument_bytes);
void (*recreate_publish_clock)(uint8_t *image, uint16_t date, uint16_t time);
#endif
