/* GEMDOS's character devices — trap #1 selectors $01..$0b and $10..$13.
 *
 * Fifteen leaves and eight routines under them, and the whole file is one idea: GEMDOS does NOT
 * talk to a device, it talks to a STANDARD HANDLE. Every leaf opens by reading one byte out of the
 * running process's basepage (`GEMDOS_P_RUN` -> `BASEPAGE_HANDLES`), sign-extending it to a word and
 * ADDING THREE — so the three standard handle values -1, -2 and -3 become the BIOS device numbers
 * 2 (CON:), 1 (AUX:) and 0 (PRT:) — and then reaches the BIOS with that number.
 *
 * WHAT SITS BETWEEN THE LEAF AND THE BIOS is GEMDOS's own console, and it is four things:
 *
 *   * a TYPEAHEAD QUEUE per device: 80 four-byte records, filled by the poll every output makes
 *     before it writes and drained by every read. It is what makes `Cconis` answer yes for a key
 *     the program has not asked for yet.
 *   * a COLUMN COUNTER per device, maintained by that same output routine, which is what TAB
 *     expansion and the line editor's erase both measure against.
 *   * TAB EXPANSION and the `^X` echo, two layers of "how does this character print".
 *   * the `Cconrs` LINE EDITOR, whose whole key set is two nine-entry tables in the ROM.
 *
 * ---------------------------------------------------------------------------------------------
 * FIVE THINGS THE DISASSEMBLY SAYS AND A READING OF THE API WOULD NOT.
 *
 * *THE STATE IS SIZED FOR EXACTLY THREE DEVICES, IN STRAIGHT-LINE CODE.* `GEMDOS_CONSOLE_INIT`
 * ($fc9356) writes p_uft[0..3] = -1,-1,-2,-3 and then clears three typeahead counts and stores three
 * read pointers and three write pointers, one instruction each — $83c0, $8500, $8640, which is
 * `GEMDOS_TYPEAHEAD_BUFFER` stepped by `GEMDOS_TYPEAHEAD_BUFFER_BYTES`. Nothing here bounds the
 * device number, so a standard handle outside -3..-1 indexes OFF all of it: off the column table
 * into `GEMDOS_CALL_DEPTH`, off the typeahead counts into whatever follows them, and BACKWARDS for a
 * handle below -3. `per_device` refuses that, and three facts are why it can:
 *
 *   * the dispatcher REDIRECTS every handle ABOVE 0 — its `ble` at $fc979e sends selectors
 *     `GEMDOS_REDIRECT_FIRST`..`_LAST` and the second run to `Fread`/`Fwrite` instead — so an open
 *     file's handle never reaches a leaf here;
 *   * a handle of exactly 0 does pass that `ble`, and is UNREACHABLE for another reason: `Fforce`
 *     ($fc52de) answers `GEMDOS_EIHNDL` for any new handle in 0..5, so nothing can store one;
 *   * what a program CAN store is any NEGATIVE byte, `Fforce`'s own `tst.w / bge` arm, and only
 *     -1/-2/-3 name a device GEMDOS has state for. That is the case this file refuses rather than
 *     reproducing the ROM's walk off the end of six tables.
 *
 * *THE ECHO IS NOT ONE ROUTINE.* `Cconin` echoes through `device_put` — the character exactly as it
 * came, a TAB printing as a TAB — while the line editor echoes through `put_echoing_controls`, where
 * a control code prints as `^` and a letter and a TAB is expanded. Two different pictures of the
 * same keystroke, and which one a program sees depends on which call it made.
 *
 * *THE ECHO GOES TO THE INPUT DEVICE, NOT TO STDOUT.* `Cconin` reads stdin's device and echoes to
 * THAT device, so a program that redirected stdout alone still sees its keystrokes on the console.
 *
 * *`Cconws` SIGN-EXTENDS EACH BYTE AND `Cconout` DOES NOT.* The string loop is `move.b (a0),d0 /
 * ext.w d0`, so a byte with bit 7 set arrives as $ff80..$ffff — which is NEGATIVE, so `device_put`'s
 * `cmp.w #32 / bge` sends it down the control-code arm and the column counter is NOT advanced.
 * `Cconout` passes the caller's whole word, so the same byte as $0080 advances it. The character
 * reaching the BIOS is the same either way (`Bconout` sends the low byte); what differs is GEMDOS's
 * idea of where the cursor now is, and therefore where a later TAB stops.
 *
 * *THE LINE EDITOR'S NINTH KEY IS 0 AND ITS ARM IS THE DEFAULT ARM.* The search is
 * `cmp.l (a0)+,d0` under a `dbeq` over `GEMDOS_LINE_EDITOR_KEY_COUNT` entries, and the arm is read
 * at `32(a0)` from wherever that search stopped — so "matched the ninth" and "matched nothing" leave
 * A0 at the same place and take the same branch. A key whose ASCII half is 0 (a cursor key, say) is
 * therefore an ordinary character, stored and echoed as `^@`, and the table's ninth entry is what
 * makes the two answers agree rather than an arm of its own.
 *
 * ---------------------------------------------------------------------------------------------
 * HOW THE BIOS IS REACHED, AND THE ONE LONGWORD THAT PROVES IT WAS.
 *
 * The ROM does not call `Bconout`; it calls `GEMDOS_BIOS_TRAMPOLINE` ($fc4eac), whose whole body is
 *
 *      move.l  (sp)+,GEMDOS_BIOS_RETURN_SLOT   ; park its own return address...
 *      trap    #13                             ; ...so the BIOS frame is at (sp)
 *      move.l  GEMDOS_BIOS_RETURN_SLOT,-(sp)
 *      rts
 *
 * ON TARGET this reconstruction takes that trap too: the four wrappers below push the trampoline's
 * own frame and `trap #13` (`include/bcon.h`), so a GEMDOS leaf pays the dispatcher the original
 * pays and `bench/tier3.py`'s numerator is our leaf over the ROM's own BIOS — the bench blob's
 * vector $b4 holds `$fc07f8` — while our `bios_*` cores are priced in their own rows alone. OFF
 * TARGET there is no 68000 to take it, so the same wrapper calls the BIOS core directly, which is
 * what ROM mode asks of a reconstruction (`tools/recreate_kit/TRAP_MODEL.md`): the direct call is
 * the HOST's stand-in for the trampoline's trap, not a decision about the routine.
 *
 * WHAT NEITHER BUILD SKIPS is the trampoline's store. `GEMDOS_BIOS_RETURN_SLOT` is ordinary RAM,
 * and after any GEMDOS console call it holds the address of the instruction after whichever
 * `jsr $fc4eac` ran last. The trampoline is not transcribed, so each wrapper below parks that
 * longword itself, ON BOTH BUILDS — the value is the ROM's own call site either way, and the
 * `BIOS_RETURN_*` constants are those thirteen addresses. Every one of them is the six bytes after
 * a `jsr GEMDOS_BIOS_TRAMPOLINE` in the ROM, which `test_gemdos_console_output.py` checks by
 * reading the opcode back out of the image.
 *
 * WHAT THE HOST BUILD STILL CANNOT LEAVE is the register-save frame the ROM's trap dispatcher
 * pushes below `savptr` on the way into the BIOS. That frame is machine scratch — pushed, popped,
 * and `savptr` restored — and the batteries put it inside the band the differential already drops
 * by poking `savptr` into it (`test/gemdos.py`, `machine`), which is an honest declaration about
 * the machine rather than a band excluded from the comparison.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "bcon.h"
#include "gemdos.h"
#include "gemdos_console.h"

/* WHERE EACH BIOS CALL RETURNS TO — the longword `GEMDOS_BIOS_TRAMPOLINE` parks, and therefore an
 * output of this layer rather than a detail of it (see the header note). Thirteen call sites, each
 * named for the routine that makes it; the value is the address six bytes past that routine's
 * `jsr GEMDOS_BIOS_TRAMPOLINE`. */
#define BIOS_RETURN_INPUT_STATUS   0xfc8b6a     /* device_input_status' Bconstat */
#define BIOS_RETURN_CCONOS         0xfc8ba8
#define BIOS_RETURN_CPRNOS         0xfc8bcc
#define BIOS_RETURN_CAUXOS         0xfc8c0c
#define BIOS_RETURN_DRAIN_STATUS   0xfc8c2a     /* drain_typeahead's three, in the order it makes */
#define BIOS_RETURN_DRAIN_INPUT    0xfc8c40
#define BIOS_RETURN_DRAIN_BELL     0xfc8d3c     /* ...the bell a full queue answers with */
#define BIOS_RETURN_DEVICE_PUT     0xfc8dba
#define BIOS_RETURN_CAUXOUT        0xfc8ef4
#define BIOS_RETURN_CPRNOUT        0xfc8f1c
#define BIOS_RETURN_DEVICE_GET     0xfc8f9e
#define BIOS_RETURN_CAUXIN         0xfc905c
#define BIOS_RETURN_CRAWIO         0xfc90b6

/* How far a character moves this device's column counter, for the two arms of `device_put` that
 * move it at all: a printable character forward, a backspace back. */
#define COLUMN_FORWARD   1
#define COLUMN_BACK     (-1)

/* ================================================================================================
 * The state: three devices' worth of typeahead queue and column counter.
 * ============================================================================================= */

/* One entry of one per-device table — and the ONE bound in this file.
 *
 * The ROM has no such bound: it computes `table + device * entry_bytes` in an address register and
 * reads whatever is there. What makes refusing right rather than convenient is that GEMDOS's own
 * initialisation (`GEMDOS_CONSOLE_INIT`) sets up exactly `GEMDOS_CONSOLE_DEVICES` entries of each of
 * these tables, in straight-line code, and the only device numbers that reach here through the trap
 * are `handle + 3` over the three standard handle values it writes. `device` is unsigned, so a
 * handle below -3 — which would index BACKWARDS off the table — is caught by the same compare. */
static uint32_t per_device(uint16_t device, uint32_t table, uint32_t entry_bytes)
{
    if (device >= GEMDOS_CONSOLE_DEVICES)
        recreate_not_reconstructed(
            "GEMDOS console: a standard handle outside -3..-1, which indexes off every per-device "
            "table GEMDOS initialises — settable only through Fforce ($fc52de), which takes any "
            "NEGATIVE byte");
    return addr_add(table, device * entry_bytes);
}

static uint32_t device_column_slot(uint16_t device)
{
    return per_device(device, GEMDOS_DEVICE_COLUMN, GEMDOS_DEVICE_COLUMN_BYTES);
}

static uint32_t typeahead_count_slot(uint16_t device)
{
    return per_device(device, GEMDOS_TYPEAHEAD_COUNT, GEMDOS_TYPEAHEAD_COUNT_BYTES);
}

static uint32_t typeahead_read_slot(uint16_t device)
{
    return per_device(device, GEMDOS_TYPEAHEAD_READ, GEMDOS_TYPEAHEAD_POINTER_BYTES);
}

static uint32_t typeahead_write_slot(uint16_t device)
{
    return per_device(device, GEMDOS_TYPEAHEAD_WRITE, GEMDOS_TYPEAHEAD_POINTER_BYTES);
}

/* `muls.w #320,d0 / add.l #$83c0,d0` — where this device's queue starts. */
static uint32_t typeahead_buffer(uint16_t device)
{
    return addr_add(GEMDOS_TYPEAHEAD_BUFFER,
                    (uint32_t)((int32_t)(int16_t)device * GEMDOS_TYPEAHEAD_BUFFER_BYTES));
}

/* A record's address, checked before it is dereferenced. HOST-ONLY, the way the kit prescribes
 * (kit.mk: "asserted where there is a process to abort"): both pointers are ordinary longwords of
 * RAM a case may stage anywhere, so a queue pointing outside the machine walks off the image here
 * where the original walks its own address space. */
static uint8_t *typeahead_record(uint8_t *image, uint32_t at)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at + GEMDOS_TYPEAHEAD_RECORD_BYTES <= ST_RAM_BYTES);
#endif
    return image + at;
}

/* Both pointers back to the top of the queue. The ROM writes the WRITE pointer first, and `$fc8f66`
 * — the reader's own "the queue just went empty" arm — is these same two stores without the count
 * clear above them, which is why this is its own routine. */
static void typeahead_rewind(uint8_t *image, uint16_t device)
{
    uint32_t buffer = typeahead_buffer(device);

    wr32(image + typeahead_write_slot(device), buffer);
    wr32(image + typeahead_read_slot(device), buffer);
}

/* $fc8d4e — the whole queue emptied: ^C and ^X both do this before doing anything else. */
static void typeahead_reset(uint8_t *image, uint16_t device)
{
    image[typeahead_count_slot(device)] = 0;
    typeahead_rewind(image, device);
}

/* One `Bconin` longword onto the end of the queue, scancode half and all. The ROM re-reads the
 * write pointer for its `addq.l #4,(a1)`, and its count bump is `addq.b #1` over a read whose value
 * it throws away — both are the same memory as this. */
static void typeahead_queue(uint8_t *image, uint16_t device, uint32_t record)
{
    uint32_t write_at = typeahead_write_slot(device);

    wr32(typeahead_record(image, be32(image + write_at)), record);
    wr32(image + write_at, addr_add(be32(image + write_at), GEMDOS_TYPEAHEAD_RECORD_BYTES));
    image[typeahead_count_slot(device)]++;
}

/* ================================================================================================
 * The BIOS, reached the way the ROM reaches it (see the header note on the trampoline).
 * ============================================================================================= */

static void park_bios_return(uint8_t *image, uint32_t return_site)
{
    wr32(image + GEMDOS_BIOS_RETURN_SLOT, return_site);
}

/* Each of the four is the ROM's own call, one build at a time (the header note): the trampoline's
 * frame and a real `trap #13` on target, the BIOS core called directly off it.
 *
 * `entry_d0` FOR THE DIRECT CALL is the ROUTINE'S OWN ADDRESS: the trap dispatcher's
 * `move.l 0(a0,d0.w),d0` loads the table entry in order to jump through it and leaves it there, and
 * a driver that writes no D0 hands exactly that back (`include/bcon.h`). The target build needs no
 * such argument — the machine's own dispatcher leaves it there for real. */
static uint32_t bios_input_status(uint8_t *image, uint32_t return_site, uint16_t device)
{
    park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bconstat(image, BIOS_BCONSTAT, device);
#else
    return bios_trap_device(BIOS_BCONSTAT_FN, device);
#endif
}

static uint32_t bios_input(uint8_t *image, uint32_t return_site, uint16_t device)
{
    park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bconin(image, BIOS_BCONIN, device);
#else
    return bios_trap_device(BIOS_BCONIN_FN, device);
#endif
}

static uint32_t bios_output(uint8_t *image, uint32_t return_site, uint16_t device,
                            uint16_t character)
{
    park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bconout(image, BIOS_BCONOUT, device, character);
#else
    return bios_trap_device_char(BIOS_BCONOUT_FN, device, character);
#endif
}

static uint32_t bios_output_status(uint8_t *image, uint32_t return_site, uint16_t device)
{
    park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bcostat(image, BIOS_BCOSTAT, device);
#else
    return bios_trap_device(BIOS_BCOSTAT_FN, device);
#endif
}

/* ================================================================================================
 * The standard handles.
 * ============================================================================================= */

/* `move.b <which>(a0),d0 / ext.w d0`: `gemdos.h`'s accessor — the one signed basepage byte the
 * dispatcher's redirection reads too — widened here to the WORD the `ext.w` leaves.
 *
 * IT IS READ INTO D0, and that is not only bookkeeping: the `ext.w` leaves the handle in D0's LOW
 * WORD, and a leaf that can return without any further call writing D0 hands it to its caller.
 * `Cconws` over an empty string is the one that does, which is why the two halves below are
 * separate — every other leaf ends in a call that overwrites the register. */
static uint16_t standard_handle(const uint8_t *image, unsigned which)
{
    return (uint16_t)(int16_t)gemdos_standard_handle(image, which);
}

/* ...and `addq.w #3,(sp)`, which is made on the STACK WORD and not on the register. */
static uint16_t device_of_handle(uint16_t handle)
{
    return (uint16_t)(handle + GEMDOS_HANDLE_TO_DEVICE);
}

static uint16_t standard_device(const uint8_t *image, unsigned which)
{
    return device_of_handle(standard_handle(image, which));
}

/* ================================================================================================
 * Output: $fc8d96, $fc8e3c, $fc8e88, and the three leaves that skip all of them.
 * ============================================================================================= */

static void drain_typeahead(uint8_t *image, uint16_t device);

/* The column counter moved by one, with the value it HAD returned — which is what the ROM leaves in
 * D0's low word after a printable character and after a backspace alike. */
static uint16_t step_column(uint8_t *image, uint16_t device, int step)
{
    uint32_t at = device_column_slot(device);
    uint16_t column = be16(image + at);

    wr16(image + at, (uint16_t)(column + step));
    return column;
}

/* $fc8d96 — the routine every character this layer prints goes through: poll the keyboard, hand the
 * byte to the BIOS, then move this device's column counter.
 *
 * THE COLUMN TEST IS SIGNED AND THE CHARACTER IS A WORD (`cmp.w #32,d6 / blt`), which is the whole
 * of the `Cconws` finding in the header note. CR resets the column and writes no D0; LF does not
 * touch either, so a console driver's own line feed and GEMDOS's idea of the column are only in step
 * because the CR always comes first. */
static uint32_t device_put(uint8_t *image, uint16_t device, uint16_t character)
{
    uint32_t result;

    drain_typeahead(image, device);
    result = bios_output(image, BIOS_RETURN_DEVICE_PUT, device, character);
    if ((int16_t)character >= CON_FIRST_PRINTABLE)
        return set_low_word(result, step_column(image, device, COLUMN_FORWARD));
    if (character == CON_CR) {
        wr16(image + device_column_slot(device), 0);
        return result;
    }
    if (character == CON_BS)
        return set_low_word(result, step_column(image, device, COLUMN_BACK));
    return result;
}

/* $fc8e3c — the same with TAB expanded: spaces until the column is a multiple of eight. The loop
 * always runs at least once, so a TAB in column 8 costs eight spaces and not none, and what it ends
 * on is the column counter masked to its phase — which is also what it leaves in D0's low word. */
static uint32_t device_put_expanding_tabs(uint8_t *image, uint16_t device, uint16_t character)
{
    uint32_t result;

    if (character != CON_TAB)
        return device_put(image, device, character);
    do {
        result = device_put(image, device, CON_SPACE);
        result = set_low_word(result, (uint16_t)(be16(image + device_column_slot(device))
                                                 & CON_TAB_PHASE_MASK));
    } while ((uint16_t)result != 0);
    return result;
}

/* $fc8e88 — and the line editor's echo on top of that: a control code prints as `^` and the letter
 * `code | $40`, so ^U shows as `^U` and takes two columns. TAB is the exception and goes to the
 * expander above; a DEL ($7f) is not a control code to this test and prints as itself. */
static uint32_t device_put_echoing_controls(uint8_t *image, uint16_t device, uint16_t character)
{
    if (character == CON_TAB)
        return device_put_expanding_tabs(image, device, character);
    if ((int16_t)character < CON_FIRST_PRINTABLE) {
        device_put(image, device, CON_CARET);
        character = (uint16_t)(character | CON_CONTROL_LETTER);
    }
    return device_put(image, device, character);
}

/* $fc90e2 — `Cconws`' loop. `move.b (a0),d0 / ext.w d0` is the sign extension the header note is
 * about; `entry_d0` is what an EMPTY string answers, because then nothing here runs at all.
 *
 * NOT INLINED, which is the ROM's own shape rather than a preference: `$fc90c2` `bsr`s to this
 * ($fc90da) and the two routines have separate frames. Inlined, its whole register file lands in
 * the leaf's prologue and every `Cconws` pays it — the empty string worst, since it pays it for no
 * passes at all (`bench/tier3.py`, "the empty string": 380 cycles inlined against 182). */
__attribute__((noinline))
static uint32_t device_put_string(uint8_t *image, uint32_t entry_d0, uint16_t device, uint32_t at)
{
    uint32_t result = entry_d0;

    while (image[at] != 0) {
        result = device_put_expanding_tabs(image, device, (uint16_t)sign_ext8(image[at]));
        at = addr_add(at, 1);
    }
    return result;
}

uint32_t gemdos_cconout(uint8_t *image, uint16_t character)
{
    return device_put_expanding_tabs(image, standard_device(image, GEMDOS_STDOUT), character);
}

/* The two that go STRAIGHT to the BIOS: no typeahead poll, no tab expansion, no column. A `Cprnout`
 * therefore leaves GEMDOS's idea of the printer's column exactly where it was. */
uint32_t gemdos_cauxout(uint8_t *image, uint16_t character)
{
    return bios_output(image, BIOS_RETURN_CAUXOUT, standard_device(image, GEMDOS_STDAUX), character);
}

uint32_t gemdos_cprnout(uint8_t *image, uint16_t character)
{
    return bios_output(image, BIOS_RETURN_CPRNOUT, standard_device(image, GEMDOS_STDPRN), character);
}

/* The only leaf whose D0 carries the `ext.w` above (see `standard_handle`): over an empty string
 * nothing else writes the register, so the caller gets its own high half over the SIGN-EXTENDED
 * standard handle — $ffff for a console, not 0 and not the device number. */
uint32_t gemdos_cconws(uint8_t *image, uint32_t entry_d0, uint32_t string)
{
    uint16_t handle = standard_handle(image, GEMDOS_STDOUT);
    uint32_t result = set_low_word(entry_d0, handle);

    /* THE EMPTY STRING ANSWERS WITHOUT ENTERING THE LOOP, and the test is spelt twice on purpose.
     * The ROM `bsr`s in either way ($fc90da) and its loop's `link a6,#-4` costs nothing; ours saves
     * the register file a `trap #13` clobbers, which the empty string would then pay for no passes
     * at all — 276 cycles against 528, measured. Behaviour is the loop's own first test either way;
     * what this buys is the row (`bench/tier3.py`, "the empty string"). */
    if (image[string] == 0)
        return result;
    return device_put_string(image, result, device_of_handle(handle), string);
}

/* ================================================================================================
 * Input: the typeahead queue ($fc8c12, $fc8f22) and the four leaves over it.
 * ============================================================================================= */

/* $fc8c12 — THE POLL EVERY OUTPUT MAKES BEFORE IT WRITES A BYTE, and the only place flow control
 * lives. It asks the BIOS once whether anything is waiting; if something is, it reads keys and
 * classifies them until it reaches one that is not ^S:
 *
 *   ^C  the queue is emptied and the process ENDS (`GEMDOS_PTERM`, `GEMDOS_CTRLC_STATUS`)
 *   ^S  hold: go round again, which means BLOCKING in `Bconin` until a key arrives
 *   ^Q  release: stop reading and let the output through
 *   ^X  the queue is emptied and the ^X itself is queued, for the line editor to find
 *   else queued if there is room, and answered with a BEL if there is not
 *
 * THE KEY IS THE LOW BYTE of the whole `Bconin` longword (`and.l #255,d0`), but what is QUEUED is
 * the longword — so the scancode half survives the queue and a later `Cconin` gets it back. */
static void drain_typeahead(uint8_t *image, uint16_t device)
{
    uint16_t paused = 0;

    if (bios_input_status(image, BIOS_RETURN_DRAIN_STATUS, device) == 0)
        return;
    do {
        uint32_t record = bios_input(image, BIOS_RETURN_DRAIN_INPUT, device);
        uint16_t key = (uint16_t)(record & 0xff);

        if (key == CON_ETX) {
            typeahead_reset(image, device);
            recreate_not_reconstructed(
                "GEMDOS console: ^C ends the process through Pterm ($fc8028), which this wave does "
                "not reconstruct");
        } else if (key == CON_DC3) {
            paused = 1;
        } else if (key == CON_DC1) {
            paused = 0;
        } else if (key == CON_CAN) {
            typeahead_reset(image, device);
            typeahead_queue(image, device, record);
        } else if ((int8_t)image[typeahead_count_slot(device)] < GEMDOS_TYPEAHEAD_MAX) {
            typeahead_queue(image, device, record);
        } else {
            bios_output(image, BIOS_RETURN_DRAIN_BELL, device, CON_BEL);
        }
    } while (paused != 0);
}

/* $fc8f22 — one record out: the queue first, and the BIOS (which BLOCKS) only when the queue is
 * empty. Emptying the queue rewinds both pointers, so the 81st character after a drain is not
 * refused for want of room at the end of the buffer. */
static uint32_t device_get(uint8_t *image, uint16_t device)
{
    uint32_t count_at = typeahead_count_slot(device);
    uint32_t read_at;
    uint32_t record;

    if (image[count_at] == 0)
        return bios_input(image, BIOS_RETURN_DEVICE_GET, device);

    read_at = typeahead_read_slot(device);
    record = be32(typeahead_record(image, be32(image + read_at)));
    wr32(image + read_at, addr_add(be32(image + read_at), GEMDOS_TYPEAHEAD_RECORD_BYTES));
    if (--image[count_at] == 0)
        typeahead_rewind(image, device);
    return record;
}

/* $fc8fc6 — `Cconin`'s read: the record, then its LOW WORD echoed back to the SAME device, RAW.
 * What comes back is the record and not the echo's answer. */
static uint32_t device_get_echoing(uint8_t *image, uint16_t device)
{
    uint32_t record = device_get(image, device);

    device_put(image, device, (uint16_t)record);
    return record;
}

uint32_t gemdos_cconin(uint8_t *image)
{
    return device_get_echoing(image, standard_device(image, GEMDOS_STDIN));
}

uint32_t gemdos_crawcin(uint8_t *image)
{
    return device_get(image, standard_device(image, GEMDOS_STDIN));
}

/* Cnecin: no echo, but the poll AFTERWARDS — so a ^C typed while the program was busy still ends it,
 * one call later than `Cconin` would. */
uint32_t gemdos_cnecin(uint8_t *image)
{
    uint16_t device = standard_device(image, GEMDOS_STDIN);
    uint32_t record = device_get(image, device);

    drain_typeahead(image, device);
    return record;
}

uint32_t gemdos_cauxin(uint8_t *image)
{
    return bios_input(image, BIOS_RETURN_CAUXIN, standard_device(image, GEMDOS_STDAUX));
}

/* ================================================================================================
 * The status calls, and `Crawio`, which is both directions in one selector.
 * ============================================================================================= */

/* $fc8b44 — a queued record counts as input, which is what `Cconis` has over `Bconstat`: the poll
 * above may have taken the key off the BIOS's ring and put it here. `moveq #-1` either way. */
static uint32_t device_input_status(uint8_t *image, uint16_t device)
{
    if (image[typeahead_count_slot(device)] != 0)
        return GEMDOS_TYPEAHEAD_READY;
    return bios_input_status(image, BIOS_RETURN_INPUT_STATUS, device);
}

uint32_t gemdos_cconis(uint8_t *image)
{
    return device_input_status(image, standard_device(image, GEMDOS_STDIN));
}

uint32_t gemdos_cauxis(uint8_t *image)
{
    return device_input_status(image, standard_device(image, GEMDOS_STDAUX));
}

uint32_t gemdos_cconos(uint8_t *image)
{
    return bios_output_status(image, BIOS_RETURN_CCONOS, standard_device(image, GEMDOS_STDOUT));
}

uint32_t gemdos_cprnos(uint8_t *image)
{
    return bios_output_status(image, BIOS_RETURN_CPRNOS, standard_device(image, GEMDOS_STDPRN));
}

uint32_t gemdos_cauxos(uint8_t *image)
{
    return bios_output_status(image, BIOS_RETURN_CAUXOS, standard_device(image, GEMDOS_STDAUX));
}

/* $fc9062 — `Crawio`. The read arm is the WHOLE argument word being `$00ff` and not just its low
 * byte, so `Crawio($40ff)` writes $ff to stdout. It reads through the typeahead queue but never
 * polls it, and it answers a plain 0 — not the queue's `$ffffffff` — when nothing is waiting. */
uint32_t gemdos_crawio(uint8_t *image, uint16_t character)
{
    uint16_t device;

    if (character != GEMDOS_CRAWIO_READ)
        return bios_output(image, BIOS_RETURN_CRAWIO, standard_device(image, GEMDOS_STDOUT),
                           character);
    device = standard_device(image, GEMDOS_STDIN);
    if (device_input_status(image, device) == 0)
        return 0;
    return device_get(image, device);
}

/* ================================================================================================
 * `Cconrs` ($fc91ea) and the line editor under it ($fc9226, $fc910c, $fc9152).
 * ============================================================================================= */

/* $fc910c — CR, LF, then `columns` spaces: how ^U and ^R get back to where the line began. */
static uint32_t device_new_line(uint8_t *image, uint16_t device, uint16_t columns)
{
    uint32_t result;

    result = device_put(image, device, CON_CR);
    result = device_put(image, device, CON_LF);
    while (columns != 0) {
        result = device_put(image, device, CON_SPACE);
        columns--;
    }
    return result;
}

/* $fc9152 — one character rubbed out, and the only routine here that MEASURES the line.
 *
 * It re-walks the first `length - 1` characters adding up how wide each one PRINTS — a TAB to the
 * next multiple of eight, a control code two columns, anything else one — and then backspaces over
 * spaces until this device's column counter has come back to that width. So an erase after a TAB
 * takes back the whole tab, and an erase after ^U takes back both of its columns.
 *
 * `entry_d0` is what it answers when the line was already empty and the backspace loop never ran:
 * the ROM's `move.w 14(a6),d0` writes the low word only. `column` is the caller's own word, changed
 * here and never read back by it. */
static uint32_t device_erase_last_character(uint8_t *image, uint32_t entry_d0, uint16_t device,
                                            uint32_t line, uint16_t length, uint16_t column)
{
    uint32_t result = entry_d0;
    uint32_t at = line;
    uint16_t left;

    if (length != 0)
        length--;
    for (left = length; left != 0; left--) {
        uint8_t character = image[at];

        at = addr_add(at, 1);
        if (character == CON_TAB)
            column = (uint16_t)((column + CON_TAB_WIDTH) & CON_TAB_STOP_MASK);
        else if ((int8_t)character < CON_FIRST_PRINTABLE)
            column = (uint16_t)(column + CON_CONTROL_WIDTH);
        else
            column = (uint16_t)(column + 1);
    }
    while ((int16_t)be16(image + device_column_slot(device)) > (int16_t)column) {
        device_put(image, device, CON_BS);
        device_put(image, device, CON_SPACE);
        result = device_put(image, device, CON_BS);
    }
    return set_low_word(result, length);
}

/* $fc9226 — the editor itself. `maximum` bounds the line, `line` is where the characters go, and
 * what comes back is how many there are.
 *
 * THE KEY IS THE LOW WORD OF THE RECORD, SIGN-EXTENDED (`ext.l d0`) — so the IKBD's scancode half is
 * discarded before the comparison, and the whole key set is the eight codes below plus the default
 * arm the table's ninth (zero) entry shares with "no match" (see the header note). */
static uint32_t device_read_line(uint8_t *image, uint32_t entry_d0, uint16_t device,
                                 uint16_t maximum, uint32_t line)
{
    uint16_t start_column = be16(image + device_column_slot(device));
    uint32_t result = entry_d0;
    uint16_t length = 0;

    while ((int16_t)length < (int16_t)maximum) {
        uint32_t record = device_get(image, device);
        uint8_t character = (uint8_t)record;
        uint32_t key = sign_ext16(record);

        /* `ext.l d0` leaves the KEY in D0, so that is what every arm below is entered with — and
         * what the two that call the erase routine hand it as its own entering D0. */
        result = key;
        switch (key) {
        case CON_ETX:
            /* The ROM's arm is `Pterm(-32)` and then, unreachably, a fall-through into ^X's loop
             * below — dead code after a call that does not come back, and dead here too. */
            recreate_not_reconstructed(
                "GEMDOS Cconrs: ^C ends the process through Pterm ($fc8028), which this wave does "
                "not reconstruct");
        case CON_LF:
        case CON_CR:
            /* One CR and no LF: the line ends where the editor stops, and moving to the next row is
             * the caller's business. */
            result = device_put(image, device, CON_CR);
            return set_low_word(result, length);
        case CON_BS:
        case CON_DEL:
            result = device_erase_last_character(image, result, device, line, length, start_column);
            length = (uint16_t)result;
            break;
        case CON_CAN:
            /* ^X kills the line by RUBBING IT OUT — one erase per character, so the screen ends up
             * blank rather than redrawn. */
            do {
                result = device_erase_last_character(image, result, device, line, length,
                                                     start_column);
                length = (uint16_t)result;
            } while (length != 0);
            break;
        case CON_NAK:
            /* ^U kills it the other way: print `#`, start a fresh line indented to where this one
             * began, and forget the characters without touching them. */
            device_put(image, device, CON_HASH);
            result = device_new_line(image, device, start_column);
            length = 0;
            break;
        case CON_DC2:
            /* ^R retypes: the same fresh line, then every character echoed back onto it. */
            device_put(image, device, CON_HASH);
            result = device_new_line(image, device, start_column);
            for (uint16_t at = 0; (int16_t)length > (int16_t)at; at++)
                result = device_put_echoing_controls(image, device,
                                                     (uint16_t)sign_ext8(image[addr_add(line, at)]));
            break;
        default:
            /* The byte is stored, then echoed as the line editor echoes — `^` and a letter for a
             * control code — and only then counted, so the buffer never runs past `maximum`. */
            image[addr_add(line, length)] = character;
            result = device_put_echoing_controls(image, device, (uint16_t)sign_ext8(character));
            length++;
            break;
        }
    }
    return set_low_word(result, length);
}

/* $fc91ea — the leaf. The buffer's first byte is the caller's maximum, read UNSIGNED (`ext.w` then
 * `andi.w #255`), and its second is where the length goes back. */
uint32_t gemdos_cconrs(uint8_t *image, uint32_t entry_d0, uint32_t buffer)
{
    uint16_t maximum = image[addr_add(buffer, GEMDOS_CCONRS_MAX)];
    uint32_t result = device_read_line(image, entry_d0, standard_device(image, GEMDOS_STDIN),
                                       maximum, addr_add(buffer, GEMDOS_CCONRS_TEXT));

    image[addr_add(buffer, GEMDOS_CCONRS_LENGTH)] = (uint8_t)result;
    return result;
}
