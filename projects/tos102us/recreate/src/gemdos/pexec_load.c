/* pexec_load.c — `Pexec`'s PROGRAM LOADER and RELOCATOR ($fc85ea), and the span clear it ends with
 * ($fc4b7c). A file of its own rather than more of `src/gemdos/process.c`: that file is the process
 * group (what a process owns and how it is given back), and this one is a FILE-SYSTEM client — five
 * `Fread`s, an `Fseek`, an `Fopen` and an `Fclose` — whose only link to the group is the basepage it is
 * handed. The file format is `include/gemdos/pexec_load.h`'s.
 *
 * WHAT THE LOADER CHECKS, which is less than a reader expects, and every omission is a ROM fact the
 * cases pin:
 *
 *   * the MAGIC, and nothing else about the header. No `Fread` result is looked at anywhere: a file
 *     shorter than its header claims loads what there is and relocates from wherever the cursor stops.
 *   * that the BSS fits what TEXT and DATA leave of the TPA — a SIGNED compare, before anything is read.
 *   * the fixup cursor against TEXT+DATA only at the FIRST fixup and at each CHUNK boundary of the
 *     relocation stream. The fixups inside a chunk are applied wherever the cursor has got to,
 *     inside the TPA or not.
 *
 * AND WHAT IT LEAVES BEHIND ON FAILURE: every error arm after the open returns with the FILE STILL
 * OPEN — the handle charged to the caller, which `Pexec`'s release of the CHILD does not reach. So is
 * the ABSOLUTE arm, which returns success without relocating, clearing or closing anything.
 */
#include <stdint.h>

#include "gemdos/fs_io.h"
#include "gemdos/fs_open.h"
#include "gemdos/gemdos.h"
#include "gemdos/pexec_load.h"
#include "gemdos/process.h"
#include "m68k_idioms.h"
#include "machine.h"

_Static_assert(GEMDOS_HOST_SLOT_PEXEC_LOCALS_BYTES == LOAD_LOCALS_BYTES,
               "a host slot narrower or wider than the frame locals it stands in for");
_Static_assert(LOAD_SLEN + PRG_LENGTH_BYTES == LOAD_LENGTHS + PRG_LENGTHS_BYTES,
               "the four lengths are not the one sixteen-byte read");

/* ---- $fc4b7c, the span clear ------------------------------------------------------------------------
 *
 * The BIOS's own `bzero(from, to)` — hand assembly, and GEMDOS's one caller of it is the loader (the
 * other, $fca666, is outside GEMDOS). Its three steps are the three below: one byte if `from` is odd,
 * then the whole 256-byte blocks — eight `movem.l` of eight zero registers, DOWNWARDS from the top of
 * the blocks, which leaves the same bytes as upwards — then single bytes up to `to`.
 *
 * THE ODD BYTE AND THE BLOCK SIZE ARE THE 68000'S, not the result's: any split of the span clears the
 * same bytes, in any order, so no image compare can tell them apart (the mutation sweep records both as
 * equivalent). What the odd byte buys on target is alignment — a longword store at an odd address is an
 * address error — and what the blocks buy is speed, which is why they are kept rather than folded into
 * the byte loop: the clear runs over the whole TPA past DATA. Each longword goes through `wr32`, the
 * image's own accessor — one `move.l` on target, four byte stores on the host, whose image is a byte
 * array with no longword alignment to rely on.
 *
 * `to` IS COMPARED FOR EQUALITY, never order: a span whose odd first byte already reaches `to` steps
 * past it, and a `to` BELOW `from` makes the block count a huge unsigned one — either way the clear runs
 * on through the address space. Transcribed. The loader reaches the second: TEXT+DATA longer than the
 * TPA leave a NEGATIVE room, a header BSS length of $80000000 or more is negative too and passes the
 * SIGNED check against it (`load` below), and the loader then reads TEXT past `p_hitpa`, asks `Fread`
 * for a ~4 GB relocation chunk, and hands this a span that ends below where it starts. Not staged — on
 * the machine it clears RAM below the TPA until something faults — and the host bound stops it at the
 * image's end.
 */
#define CLEAR_BLOCK_MASK     0xffffff00u        /* `andl #-256,d0` */
#define CLEAR_LONG_BYTES     4                  /* `movem.l` of zero registers: a longword each */

static void clear_span(uint8_t *image, uint32_t from, uint32_t to)
{
    uint32_t blocks;

    if (from & 1)
        *gemdos_image_byte(image, from++) = 0;
    blocks = (to - from) & CLEAR_BLOCK_MASK;
    if (blocks != 0) {
        uint8_t *longs = gemdos_image_bytes(image, from, blocks);
        uint32_t count;

        for (count = blocks / CLEAR_LONG_BYTES; count != 0; count--, longs += CLEAR_LONG_BYTES)
            wr32(longs, 0);
        from += blocks;
    }
    while (from != to)
        *gemdos_image_byte(image, from++) = 0;
}

/* ---- the loader's locals, read out of the slot `Fread` wrote them into -------------------------------- */

static uint32_t local_long(const uint8_t *image, uint32_t locals, uint32_t field)
{
    return be32(image + locals + field);
}

static uint16_t local_word(const uint8_t *image, uint32_t locals, uint32_t field)
{
    return be16(image + locals + field);
}

/* `count` bytes of the file into the image at `at`. What `Fread` answers is dropped: THE LOADER NEVER
 * LOOKS, which is the first fact in the file header. */
static void read_into(uint8_t *image, int16_t handle, uint32_t count, uint32_t at)
{
    (void)gemdos_fread(image, handle, count, at);
}

/* The header after the magic: the four lengths, the reserved longword and the program flags — both
 * read into the ONE local, so the flags overwrite the reserved word and neither is read again — and
 * the absolute flag. */
static void read_header_tail(uint8_t *image, int16_t handle, uint32_t locals)
{
    read_into(image, handle, PRG_LENGTHS_BYTES, locals + LOAD_LENGTHS);
    read_into(image, handle, PRG_SKIPPED_BYTES, locals + LOAD_SKIPPED);
    read_into(image, handle, PRG_SKIPPED_BYTES, locals + LOAD_SKIPPED);
    read_into(image, handle, PRG_ABSFLAG_BYTES, locals + LOAD_ABSFLAG);
}

/* p_tbase/p_tlen, p_dbase/p_dlen, p_bbase/p_blen: each base the one before plus its length, starting
 * from TEXT's ($fc8712..$fc874e — one loop over the three lengths the header read). */
static void publish_segments(uint8_t *image, uint32_t basepage, uint32_t locals, uint32_t text)
{
    uint32_t field = addr_add(basepage, BASEPAGE_TBASE);
    uint32_t base = text;
    int16_t segment;

    for (segment = 0; segment < PRG_SEGMENTS; segment++) {
        uint32_t length = local_long(image, locals, LOAD_LENGTHS + (uint32_t)segment * PRG_LENGTH_BYTES);

        wr32(gemdos_image_bytes(image, field, PRG_LENGTH_BYTES), base);
        field += PRG_LENGTH_BYTES;
        wr32(gemdos_image_bytes(image, field, PRG_LENGTH_BYTES), length);
        field += PRG_LENGTH_BYTES;
        base += length;
    }
}

/* ---- relocation ------------------------------------------------------------------------------------ */

/* THE TEXT BASE added to the longword at `at` — `addl d0,(a1)`. On the 68000 an ODD `at` is an address
 * error, and a stream whose distances are all even from an even first offset never makes one. */
static void fix_up(uint8_t *image, uint32_t at, uint32_t text)
{
    uint8_t *longword = gemdos_image_bytes(image, at, PRG_FIXUP_BYTES);

    wr32(longword, be32(longword) + text);
}

/* The cursor inside TEXT+DATA — `blt` against the TEXT base (SIGNED) and `bcs` against the end
 * (UNSIGNED), the two compares at $fc87b8/$fc87be and again at $fc87d2/$fc87d8. */
static int inside_the_image(uint32_t cursor, uint32_t text, uint32_t end)
{
    return (int32_t)cursor >= (int32_t)text && cursor < end;
}

/* One CHUNK of the stream, `count` bytes read into the buffer at `buffer`: 1 once its 0 byte is met,
 * 0 when the chunk runs out first. The cursor is carried in and out. No bound is applied to a fixup
 * inside a chunk — the check is the caller's, between chunks. */
static int relocate_chunk(uint8_t *image, uint32_t buffer, int32_t count, uint32_t *cursor, uint32_t text)
{
    for (; count != 0; count--) {
        uint8_t distance = *gemdos_image_byte(image, buffer++);

        if (distance == PRG_RELOCATION_END)
            return 1;
        if (distance == PRG_RELOCATION_SKIP) {
            *cursor += PRG_SKIP_DISTANCE;
            continue;
        }
        *cursor += distance;
        fix_up(image, *cursor, text);
    }
    return 0;
}

/* $fc87b0..$fc883c — the relocation stream after its first offset: the first fixup, then the stream
 * read in chunks into the TPA just past DATA — `room` bytes at a time, as much as the TPA has left.
 * 0, or EPLFMT for a cursor outside TEXT+DATA at the first fixup or at a chunk boundary.
 *
 * A CHUNK IS FOLLOWED BY ANOTHER only when `Fread` filled it EXACTLY — compared after the ROM has
 * truncated the count to a WORD and sign-extended it (`ext.l` at $fc87f8). So a TPA with 32 KB or
 * more left over never reads a second chunk, whatever the stream still holds: one chunk is all the
 * stream there is. */
static uint32_t relocate(uint8_t *image, int16_t handle, uint32_t first, uint32_t text, uint32_t end,
                         int32_t room)
{
    uint32_t cursor = text + first;
    int32_t read;

    if (!inside_the_image(cursor, text, end))
        return GEMDOS_EPLFMT;
    fix_up(image, cursor, text);
    do {
        if (!inside_the_image(cursor, text, end))
            return GEMDOS_EPLFMT;
        read = (int16_t)gemdos_fread(image, handle, (uint32_t)room, end);
        if (relocate_chunk(image, end, read, &cursor, text))
            return 0;
    } while (read == room);
    return 0;
}

/* ---- $fc85ea ------------------------------------------------------------------------------------------ */

/* The loader over its frame locals at `locals`, once the file is open as `handle`.
 *
 * TEXT goes at the basepage's end, DATA straight after it, and the relocation stream is read into
 * whatever is left of the TPA past DATA — which is also where the BSS will be, so the clear at the end
 * wipes the stream as well as clearing the BSS. It clears ALL the TPA past DATA, not `blen` bytes. */
static uint32_t load(uint8_t *image, uint32_t basepage, int16_t handle, uint32_t locals)
{
    uint32_t text, end, image_bytes, first;
    int32_t room;

    read_into(image, handle, PRG_MAGIC_BYTES, locals + LOAD_MAGIC);
    if (local_word(image, locals, LOAD_MAGIC) != PRG_MAGIC)
        return GEMDOS_EPLFMT;
    read_header_tail(image, handle, locals);

    image_bytes = local_long(image, locals, LOAD_DLEN) + local_long(image, locals, LOAD_TLEN);
    text = addr_add(basepage, BASEPAGE_BYTES);
    end = text + image_bytes;
    room = (int32_t)(gemdos_basepage_field(image, basepage, BASEPAGE_HITPA)
                     - gemdos_basepage_field(image, basepage, BASEPAGE_LOWTPA) - BASEPAGE_BYTES - image_bytes);
    if ((int32_t)local_long(image, locals, LOAD_BLEN) > room)
        return GEMDOS_ENSMEM;

    publish_segments(image, basepage, locals, text);
    read_into(image, handle, image_bytes, text);
    if (local_word(image, locals, LOAD_ABSFLAG) != 0)
        return 0;

    (void)gemdos_fseek(image, local_long(image, locals, LOAD_SLEN) + image_bytes + PRG_HEADER_BYTES, handle,
                       GEMDOS_SEEK_FROM_START);
    read_into(image, handle, PRG_FIXUP_BYTES, locals + LOAD_FIRST_FIXUP);
    first = local_long(image, locals, LOAD_FIRST_FIXUP);
    if (first != 0) {
        uint32_t refused = relocate(image, handle, first, text, end, room);

        if (refused != 0)
            return refused;
    }
    clear_span(image, end, end + (uint32_t)room);
    (void)gemdos_fclose(image, handle);
    return 0;
}

/* $fc85ea — `name` loaded into `basepage`'s TPA. The handle `Fopen` answers is a WORD, sign-extended
 * (`ext.l` at $fc85fc), and a negative one is the loader's answer as it stands. */
uint32_t gemdos_pexec_load(uint8_t *image, uint32_t name, uint32_t basepage, uint32_t caller_d5)
{
    uint16_t frame[LOAD_LOCALS_BYTES / sizeof(uint16_t)];
    int16_t handle = (int16_t)gemdos_fopen(image, name, (uint16_t)(caller_d5 >> M68K_WORD_BITS));
    uint32_t locals, result;

    if (handle < 0)
        return (uint32_t)(int32_t)handle;
    locals = gemdos_host_slot_claim(PEXEC_LOCALS, frame);
    result = load(image, basepage, handle, locals);
    gemdos_host_slot_release(PEXEC_LOCALS);
    return result;
}
