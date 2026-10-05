/* shell_find.c — the shell's FILE FINDING (`aes/shell.h`): sh_find and the helpers it walks the environment's PATH
 * with. A Line-F call in the ROM is a plain call here (`aes/aes.h`, "LINE-F"); every pointer a caller hands in is put
 * on the 24-bit bus where it is dereferenced (`m68k_idioms.h`).
 *
 * THE TWO FRAMES. sh_envrn and sh_find each hand the ADDRESS of a frame string to another routine, so the C keeps the
 * ROM's frame whole, as bytes in the ROM's layout (`aes/shell.h`), reached through `host_slot.h` — a C local on
 * target, a fixed slot of the dropped stack band off it — and every local the ROM keeps in its frame is read and
 * written there at the ROM's points: a string longer than its buffer then runs into the locals after it, and is read
 * back with them, as on the machine. Past the frame lies the top byte of the caller's saved A6, 0 on a 24-bit bus: the
 * C keeps it too, and a 0 stored there is served as the ROM serves it. Anything else, or further, the ROM runs on
 * over — it restores the A6 its stores left — but whether that still works depends on the caller's whole A6, which
 * no C can see: both builds halt there by name, a conservative choice (`aes/shell.h`).
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "aes/objects.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/strings.h"
#include "gemdos/fs.h"
#include "gemdos/fs_drive.h"

/* The ROM's immediates, which are GEMDOS's values: `aes/shell.h` spells them as the ROM does, these pin them equal. */
_Static_assert(SH_FIND_ATTRIBUTES == (GEMDOS_ATTR_READ_ONLY | GEMDOS_ATTR_SYSTEM), "sh_find's search is not F_RDONLY|F_SYSTEM");
_Static_assert(SH_DIRECTORY_SEPARATOR == PATH_SEPARATOR, "sh_name's `\\` is not GEMDOS's");
_Static_assert(SH_DRIVE_SEPARATOR == DRIVE_LETTER_SEPARATOR, "sh_name's `:` is not GEMDOS's");
_Static_assert(HOST_SLOT_AES_SH_ENVRN_FRAME_BYTES == SH_ENVRN_SLOT_BYTES, "sh_envrn's host slot is not its frame's");
_Static_assert(HOST_SLOT_AES_SH_FIND_FRAME_BYTES == SH_FIND_SLOT_BYTES, "sh_find's host slot is not its frame's");

/* What both builds halt with where the ROM's string runs past its frame. */
#define PAST_THE_FRAME(what)  what " past its frame (the ROM runs on over its caller's saved A6, which the C cannot see)"

/* A frame's slot as `link` leaves it: the locals, then the caller's saved A6, whose top byte is 0 (`aes/shell.h`). */
static void link_frame(uint8_t *locals, uint32_t frame_bytes)
{
    locals[frame_bytes] = 0;
}

/* Whether the ROM's frame survived what was stored in it: the saved A6's top byte still 0. */
static int saved_a6_intact(const uint8_t *locals, uint32_t frame_bytes)
{
    return !locals[frame_bytes];
}

/* ================================================================================================
 * sh_name.
 * ============================================================================================= */

/* $feae04 — sh_name: the name part of `path` — past its last `\` or `:`, scanning back from its NUL (the length's
 * `ext.l`, a SIGNED word) and stopping below its start by an UNSIGNED compare (`cmpa.l; bcs`). */
uint32_t aes_sh_name(uint8_t *image, uint32_t path)
{
    uint32_t at = path + (uint32_t)(int32_t)aes_strlen(image, path);

    for (; at >= path; at--) {
        uint8_t byte = bus_byte(image, at);

        if (byte == SH_DIRECTORY_SEPARATOR || byte == SH_DRIVE_SEPARATOR)
            break;
    }
    return at + 1;
}

/* ================================================================================================
 * sh_envrn.
 * ============================================================================================= */

/* The longest name the search can be handed: the compare buffer's terminator, stored at the name's length less one
 * past the buffer ($feae68 clr.b), lands on the saved A6's top byte for a name this long — a 0 where a 0 is. It is
 * also the most a compare may copy into the buffer, if what lands there is a 0 (`aes/shell.h`). */
#define ENVRN_LONGEST_SEARCH  (SH_ENVRN_SLOT_BYTES - SH_ENVRN_COMPARE)
/* What a NUL ending a string that did not match is turned into, so the scan goes on ($feaeb0 move.b #-1). */
#define ENVRN_GO_ON           0xff

/* The environment scan's body, as the ROM runs it over its frame at `frame` (`locals` its bytes): a byte read from
 * the cursor; the NUL that ends a string that did not match skipped; a byte equal to the name's first compared as the
 * rest of the name (the name's length less one copied out of the environment, the compare buffer's terminator past
 * it); a match leaves the cursor past the name. Answers the word D0 holds where the ROM leaves the scan: the length on
 * a match, else the name's first byte sign-extended (`ext.w`), or streq's 0 after a compare that failed on a NUL. */
static int16_t envrn_scan(uint8_t *image, uint32_t frame, uint8_t *locals)
{
    int16_t answer = 0;

    do {
        uint32_t cursor = be32(locals + SH_ENVRN_CURSOR);

        locals[SH_ENVRN_CHARACTER] = bus_byte(image, cursor);
        wr32(locals + SH_ENVRN_CURSOR, cursor + 1);
        if (be16(locals + SH_ENVRN_SKIPPING) && locals[SH_ENVRN_CHARACTER] == STRING_NUL) {
            wr16(locals + SH_ENVRN_SKIPPING, 0);
            locals[SH_ENVRN_CHARACTER] = ENVRN_GO_ON;
            continue;
        }
        answer = (int8_t)locals[SH_ENVRN_SEARCH];
        if ((uint8_t)answer != locals[SH_ENVRN_CHARACTER]) {
            wr16(locals + SH_ENVRN_SKIPPING, 1);
            continue;
        }
        if (be16(locals + SH_ENVRN_LENGTH) > ENVRN_LONGEST_SEARCH)
            recreate_not_reconstructed(PAST_THE_FRAME("sh_envrn: a compare"));
        aes_lbcopy(image, frame + SH_ENVRN_COMPARE, be32(locals + SH_ENVRN_CURSOR),
                   (int16_t)be16(locals + SH_ENVRN_LENGTH));
        if (!saved_a6_intact(locals, SH_ENVRN_FRAME_BYTES))
            recreate_not_reconstructed(PAST_THE_FRAME("sh_envrn: a compare"));
        answer = aes_streq(image, frame + SH_ENVRN_COMPARE, frame + SH_ENVRN_SEARCH + SH_ENVRN_REST);
        if (answer) {
            answer = (int16_t)be16(locals + SH_ENVRN_LENGTH);
            wr32(locals + SH_ENVRN_CURSOR, be32(locals + SH_ENVRN_CURSOR) + (uint32_t)(int32_t)answer);
            break;
        }
    } while (locals[SH_ENVRN_CHARACTER] != STRING_NUL);
    return answer;
}

/* sh_envrn's body: where the value of `search` (a name with its `=`, "PATH=") starts in a copy of the environment, or
 * 0 — and, through `answer`, the word it leaves in D0. The copy is AES_SH_SCRATCH_BYTES of it, byte 5 made a `;`
 * (`aes/shell.h`); the match is not anchored to a string's start, only to a byte equal to the name's first. */
static uint32_t envrn_search(uint8_t *image, uint32_t search, int16_t *answer)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SH_ENVRN_SLOT_BYTES)];
    _Static_assert(sizeof frame_local >= SH_ENVRN_SLOT_BYTES, "the frame and the saved A6's top byte");
    uint32_t frame = host_slot_claim(AES_SH_ENVRN_FRAME, frame_local);
    uint8_t *locals = image + frame;
    uint32_t found;
    uint16_t copied;

    link_frame(locals, SH_ENVRN_FRAME_BYTES);

    /* lstcpy counts in a BYTE: a name of 256 bytes or more answers its length modulo 256, at which its own byte is
     * not its NUL — so the two tests together catch every name past the frame, after the copy that overran it. */
    copied = (uint16_t)aes_lstcpy(image, frame + SH_ENVRN_SEARCH, search);
    if (copied > ENVRN_LONGEST_SEARCH || locals[SH_ENVRN_SEARCH + copied] != STRING_NUL)
        recreate_not_reconstructed(PAST_THE_FRAME("sh_envrn: a name"));
    wr16(locals + SH_ENVRN_LENGTH, (uint16_t)(copied - 1));
    wr32(locals + SH_ENVRN_COMPARE_AT, frame + SH_ENVRN_COMPARE);
    locals[SH_ENVRN_COMPARE + (int16_t)be16(locals + SH_ENVRN_LENGTH)] = STRING_NUL;
    aes_lbcopy(image, AES_SH_SCRATCH, be32(image + AES_SH_ENVIRONMENT), AES_SH_SCRATCH_BYTES);
    image[AES_SH_SCRATCH + SH_ENVRN_PATCHED_BYTE] = SH_PATH_SEPARATOR;
    wr32(locals + SH_ENVRN_CURSOR, AES_SH_SCRATCH);
    wr16(locals + SH_ENVRN_SKIPPING, 0);
    *answer = envrn_scan(image, frame, locals);
    if (locals[SH_ENVRN_CHARACTER] == STRING_NUL)
        wr32(locals + SH_ENVRN_CURSOR, 0);
    found = be32(locals + SH_ENVRN_CURSOR);
    host_slot_release(AES_SH_ENVRN_FRAME);
    return found;
}

/* $feae36 — sh_envrn (shel_envrn): the search's answer stored through `answer`, last. D0 is what the scan left, which
 * the dispatcher's arm hands back as intout[0]. */
int16_t aes_sh_envrn(uint8_t *image, uint32_t answer, uint32_t search)
{
    int16_t left_in_d0;
    uint32_t found = envrn_search(image, search, &left_in_d0);

    set_bus_long(image, answer, found);
    return left_in_d0;
}

/* ================================================================================================
 * sh_path.
 * ============================================================================================= */

/* The AES's own free string 0, "PATH=" ($feaf2a clr.w; rs_str). */
#define PATH_STRING           0
/* sh_path's last byte copied is D6, which it never sets first: for an EMPTY element the ROM tests its CALLER's D6.
 * Every application path enters with the dispatcher's 1 ($fe5da8 moveq #1,d6; rsrc_load and shel_find reach sh_find
 * with no D6 set between), neither separator, so the `\` is added: the port takes that 1. Only sh_main's own sh_find
 * ($feb27e) inherits a D6 no C can see (STATUS: a documented divergence). */
#define PATH_NOTHING_COPIED   1

/* Past `which` elements of PATH: each to just past its `;`, or up to the NUL. Answers the byte that ended the last —
 * the `;` itself when nothing was skipped. */
static uint8_t skip_elements(uint8_t *image, uint32_t *cursor, int16_t which)
{
    uint8_t byte = SH_PATH_SEPARATOR;
    uint16_t left;

    for (left = (uint16_t)which; left; left--) {
        while ((byte = bus_byte(image, *cursor)) != STRING_NUL) {
            (*cursor)++;
            if (byte == SH_PATH_SEPARATOR)
                break;
        }
    }
    return byte;
}

/* $feaf1e — sh_path: element `which` of PATH copied to `path`, a `\` after it unless it ends in one or in `:`, then
 * `name`; answers `which` + 1, or 0 when there is no PATH or no such element. The skip counts a WORD down to 0, so a
 * negative `which` goes the long way round. */
int16_t aes_sh_path(uint8_t *image, int16_t which, uint32_t path, uint32_t name)
{
    int16_t unread;
    uint32_t cursor = envrn_search(image, aes_rs_str(image, PATH_STRING), &unread);
    uint8_t byte, last = PATH_NOTHING_COPIED;

    if (!cursor)
        return 0;
    if (skip_elements(image, &cursor, which) == STRING_NUL)
        return 0;
    while ((byte = bus_byte(image, cursor)) != STRING_NUL && byte != SH_PATH_SEPARATOR) {
        set_bus_byte(image, path++, byte);
        last = byte;
        cursor++;
    }
    if (last != SH_DIRECTORY_SEPARATOR && last != SH_DRIVE_SEPARATOR)
        set_bus_byte(image, path++, SH_DIRECTORY_SEPARATOR);
    (void)aes_lstcpy(image, path, name);
    return (int16_t)(which + 1);
}

/* ================================================================================================
 * sh_find.
 * ============================================================================================= */

/* The DTA every search lands in ($feafc2 move.l #$b89a): rs_str's buffer — so sh_path's rs_str writes "PATH=" over
 * what the last Fsfirst found. */
#define FIND_DTA              AES_RS_STRING
#define FIND_FIRST_ELEMENT    1          /* after the root, PATH's element 1: 0 is the empty one the patch makes */

/* The errors sh_find tries elsewhere on ($feb016): not found, as the glue words it. */
static int not_there(uint16_t dos_ax)
{
    return dos_ax == DOS_AX_FILE_NOT_FOUND || dos_ax == DOS_AX_NO_MORE_FILES || dos_ax == DOS_AX_PATH_NOT_FOUND;
}

/* The first retry: `\` + the working path, built in AES_SH_SCRATCH (two byte stores, then strcat), copied back. */
static void try_the_root(uint8_t *image, uint8_t *locals)
{
    image[AES_SH_SCRATCH] = SH_DIRECTORY_SEPARATOR;
    image[AES_SH_SCRATCH + 1] = STRING_NUL;
    (void)aes_strcat(image, be32(image + AES_SH_PATH_POINTER), AES_SH_SCRATCH);
    (void)aes_lstcpy(image, be32(image + AES_SH_PATH_POINTER), AES_SH_SCRATCH);
    wr16(locals + SH_FIND_FIRST_TRY, 0);
    wr16(locals + SH_FIND_PATH, FIND_FIRST_ELEMENT);
}

/* The search: Fsfirst on the working path; not there, the root once, then each PATH element with the name part, until
 * found, another error, or PATH runs out. Each retry leaves AES_DOS_ERR set — the root's because the Fsfirst did,
 * sh_path's by a store ($feb08e) — which is what the loop's test reads. */
static void search(uint8_t *image, uint32_t frame, uint8_t *locals)
{
    do {
        (void)aes_dos_sfirst(image, be32(image + AES_SH_PATH_POINTER), SH_FIND_ATTRIBUTES);
        if (!aes_dos_failed(image) || !not_there(be16(image + AES_DOS_AX))) {
            wr16(locals + SH_FIND_PATH, 0);
        } else if (be16(locals + SH_FIND_FIRST_TRY)) {
            try_the_root(image, locals);
        } else {
            wr16(locals + SH_FIND_PATH, (uint16_t)aes_sh_path(image, (int16_t)be16(locals + SH_FIND_PATH),
                                                               be32(image + AES_SH_PATH_POINTER), frame + SH_FIND_NAME));
            wr16(image + AES_DOS_ERR, 1);
        }
    } while (aes_dos_failed(image) && be16(locals + SH_FIND_PATH));
}

/* $feafbe — sh_find (shel_find): `spec` looked for (`aes/shell.h`); found, the path it was found by copied back into
 * `spec` and handed to `routine` if there is one (sh_main's), an Alcyon call over that one longword. Answers whether
 * AES_DOS_ERR is clear — read AFTER the routine, which may set it. The name part is copied from the working path's
 * buffer by its ADDRESS, AES_SH_PATH_BUFFER, not through AES_SH_PATH_POINTER. */
int16_t aes_sh_find(uint8_t *image, uint32_t spec, uint32_t routine)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SH_FIND_SLOT_BYTES)];
    _Static_assert(sizeof frame_local >= SH_FIND_SLOT_BYTES, "the frame and the saved A6's top byte");
    uint32_t frame = host_slot_claim(AES_SH_FIND_FRAME, frame_local);
    uint8_t *locals = image + frame;

    (void)aes_dos_sdta(image, AES_SH_FIND_SDTA_RETURN, FIND_DTA);
    (void)aes_lstcpy(image, be32(image + AES_SH_PATH_POINTER), spec);
    wr32(locals + SH_FIND_NAME_POINTER, aes_sh_name(image, AES_SH_PATH_BUFFER));
    /* strcpy answers past the NUL it stored last: a NUL on the saved A6's top byte is served, anything further not. */
    if (aes_strcpy(image, be32(locals + SH_FIND_NAME_POINTER), frame + SH_FIND_NAME) - frame > SH_FIND_SLOT_BYTES)
        recreate_not_reconstructed(PAST_THE_FRAME("sh_find: a name part"));
    wr16(locals + SH_FIND_PATH, 0);
    wr16(locals + SH_FIND_FIRST_TRY, 1);
    search(image, frame, locals);
    host_slot_release(AES_SH_FIND_FRAME);
    if (!aes_dos_failed(image)) {
        (void)aes_lstcpy(image, spec, be32(image + AES_SH_PATH_POINTER));
        if (routine != SH_FIND_NO_ROUTINE)
            call_alcyon_pointer(image, routine, be32(image + AES_SH_PATH_POINTER));
    }
    return !aes_dos_failed(image);
}
