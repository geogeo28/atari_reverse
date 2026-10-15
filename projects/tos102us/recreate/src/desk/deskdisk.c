/* deskdisk.c — THE DESK'S DISK UTILITIES (`desk/deskdisk.h`), unit N: band 6 wave 4 lays it for group G2's ten
 * routines — Format, the disk copy and their helpers. Alcyon C in the ROM, ported over its own order.
 */
#include "desk/deskdisk.h"

/* ---- band 6 wave 4, group G2 (unit N) ----
 * THREE THINGS THE ROM DOES THAT THIS C REPRODUCES, AND ONE IT CANNOT:
 *   - the copy's second Malloc failing returns with the FIRST BLOCK STILL HELD (`$fede26`: no dos_free) — kept;
 *   - copy_tracks over no track answers ITS CALLER'S D4 (`$fee360 move.w d4,d0`, D4 never written): at the ROM's one
 *     call site that register is the copy's track count, the word it pushes as `first` — so the C answers `first`.
 *     A last pass of no track (the tracks a whole number of bufferfuls) so reads as a failure: the copy stops after
 *     that side, with no alert;
 *   - fat_mark's 12-bit arm STORES its mask's complement INTO ITS OWN ARGUMENT SLOT 10(a6) — a word of its CALLER's
 *     frame, which Format pops (`addq.l #8,sp`) unread; the C's argument is a parameter, never read either;
 *   - Format's two Flopwr's hand as their filler longword `-4(a6)`, a local of its frame nothing writes (Flopwr reads
 *     none of it): no C has that word, and FORMAT_FLOPWR_FILLER is handed instead — named, and dropped where a case
 *     holds the call's frame (`test/aes_deskdisk.py`). */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "aes/aes.h"
#include "aes/deskleaf.h"
#include "aes/fmdo.h"
#include "aes/gemdosif.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/resource.h"
#include "aes/shlib.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskglobals.h"
#include "desk/deskleaf.h"
#include "desk/desksupp.h"
#include "gemdos/fs.h"

#define FORMAT_FLOPWR_FILLER  0          /* in place of the ROM's unwritten -4(a6) (above)                       */

_Static_assert(UTIL_OPEN_RECT_BYTES == HOST_SLOT_AES_DESK_UTIL_OPEN_RECT_BYTES, "util_open's rectangle and its host slot");
_Static_assert(UTIL_FRAME_BYTES == HOST_SLOT_AES_DESK_UTIL_FRAME_BYTES, "Format's and the copy's frame and its host slot");
_Static_assert(FAT_MARK_WORD_BYTES == HOST_SLOT_AES_DESK_FAT_MARK_WORD_BYTES, "fat_mark's word and its host slot");
_Static_assert(BPB_BFLAGS_LOW_BYTE == BPB_BFLAGS + 1, "the BPB's flags word's low byte (`gemdos/fs.h`)");

#ifdef RECREATE_HOST_DIFFERENTIAL
int32_t (*desk_disk_xbios_door)(uint8_t *image, const uint16_t *frame, uint16_t words);
#endif

/* ---- the doors -------------------------------------------------------------------------------------------------------- */

/* THE XBIOS, as the ROM's trp14 door takes it (`desk/deskleaf.h`): the caller's return parked in AES_XBIOS_RETURN,
 * `trap #14` over the frame (`words`, the function first). ON TARGET the trap; OFF TARGET the hook a case binds,
 * refused by name where none is. The XBIOS's long answer. */
static int32_t xbios(uint8_t *image, uint32_t return_site, const uint16_t *frame, uint16_t words)
{
    desk_xbios_parked(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (!desk_disk_xbios_door)
        recreate_not_reconstructed("the disk utilities' XBIOS: the host has no floppy, and no case bound its door");
    return desk_disk_xbios_door(image, frame, words);
#else
    return desk_xbios_trap(frame, words);
#endif
}

static inline uint16_t high_word(uint32_t value)
{
    return (uint16_t)(value >> 16);
}

/* Floprd / Flopwr (`op`): `count` sectors from `sector` of `track`, `side` of `device`, into or out of `buffer`. */
static int16_t floprw(uint8_t *image, uint32_t return_site, int16_t op, uint32_t buffer, uint32_t filler, int16_t device,
                      int16_t sector, int16_t track, int16_t side, int16_t count)
{
    const uint16_t frame[XBIOS_FLOPRW_WORDS] = {(uint16_t)op, high_word(buffer), (uint16_t)buffer, high_word(filler),
                                                (uint16_t)filler, (uint16_t)device, (uint16_t)sector, (uint16_t)track,
                                                (uint16_t)side, (uint16_t)count};

    return (int16_t)xbios(image, return_site, frame, XBIOS_FLOPRW_WORDS);
}

/* The boot sector alone: sector 1 of track 0, side 0. */
static int16_t boot_sector(uint8_t *image, uint32_t return_site, int16_t op, uint32_t buffer, uint32_t filler,
                           int16_t device)
{
    return floprw(image, return_site, op, buffer, filler, device, FLOPPY_FIRST_SECTOR, FLOPPY_BOOT_TRACK,
                  FLOPPY_BOOT_SIDE, FLOPPY_ONE_SECTOR);
}

/* Flopfmt: one side of one track of `device`, its nine sectors in the order of the table at `skew`, the buffer the
 * driver's. */
static int16_t flopfmt(uint8_t *image, uint32_t buffer, uint32_t skew, int16_t device, int16_t track, int16_t side)
{
    const uint16_t frame[XBIOS_FLOPFMT_WORDS] = {XBIOS_FLOPFMT_FN, high_word(buffer), (uint16_t)buffer, high_word(skew),
                                                 (uint16_t)skew, (uint16_t)device, FLOPPY_SECTORS, (uint16_t)track,
                                                 (uint16_t)side, (uint16_t)FLOPFMT_BY_THE_SKEW,
                                                 high_word(FLOPFMT_MAGIC), (uint16_t)FLOPFMT_MAGIC, FLOPFMT_VIRGIN};

    return (int16_t)xbios(image, AES_FORMAT_FLOPFMT_RETURN, frame, XBIOS_FLOPFMT_WORDS);
}

/* Protobt: the boot sector in `buffer` made a prototype's (its answer read by neither caller). */
static void protobt(uint8_t *image, uint32_t return_site, uint32_t buffer, int16_t type, int16_t executable)
{
    const uint16_t frame[XBIOS_PROTOBT_WORDS] = {XBIOS_PROTOBT_FN, high_word(buffer), (uint16_t)buffer,
                                                 high_word(PROTOBT_NEW_SERIAL), (uint16_t)PROTOBT_NEW_SERIAL,
                                                 (uint16_t)type, (uint16_t)executable};

    (void)xbios(image, return_site, frame, XBIOS_PROTOBT_WORDS);
}

/* XBIOS 11 of `device` (this ROM's stub). */
static uint32_t xbios_stub_11(uint8_t *image, uint32_t return_site, int16_t device)
{
    const uint16_t frame[XBIOS_STUB_11_WORDS] = {XBIOS_STUB_11_FN, (uint16_t)device};

    return (uint32_t)xbios(image, return_site, frame, XBIOS_STUB_11_WORDS);
}

/* The BIOS's Getbpb (its record of `device`'s disk, or 0) and Rwabs' write of `count` records from `record`, through
 * trp13's door. */
static uint32_t getbpb(uint8_t *image, uint32_t return_site, int16_t device)
{
    return aes_trp13(image, return_site, BIOS_GETBPB_FN, device, 0, 0, 0, 0, 0);
}

static void rwabs_write(uint8_t *image, uint32_t return_site, uint32_t buffer, int16_t count, int16_t record,
                        int16_t device)
{
    (void)aes_trp13(image, return_site, BIOS_RWABS_FN, BIOS_RWABS_WRITE_NO_MEDIA_CHECK, (int16_t)high_word(buffer),
                    (int16_t)buffer, count, record, device);
}

/* ---- the utility tree, read again at each use as the ROM reads AES_DESK_UTIL_TREE ------------------------------------- */

static uint32_t util_tree(const uint8_t *image)
{
    return be32(image + AES_DESK_UTIL_TREE);
}

static uint32_t util_object(const uint8_t *image, int16_t object)
{
    return util_tree(image) + (uint32_t)object * OB_BYTES;
}

static uint32_t util_ted(const uint8_t *image, int16_t ted)
{
    return be32(image + AES_DESK_UTIL_TEDINFOS) + (uint32_t)ted * TE_BYTES;
}

/* A dialog's button pressed (its state word not 0) is taken: its state cleared, and so its verdict. */
static int pressed(uint8_t *image, int16_t button)
{
    uint32_t state = util_object(image, button) + OB_STATE;

    if (!bus_word(image, state))
        return 0;
    set_bus_word(image, state, 0);
    return 1;
}

/* A tail's letter `at` as a drive: the byte sign-extended, less 'A' ($fed9f0 addw #-65,d0). */
static int16_t drive_of(const uint8_t *image, uint32_t at)
{
    return (int16_t)((int8_t)bus_byte(image, at) - DRIVE_LETTER_FIRST);
}

/* ---- the dialog and its helpers ------------------------------------------------------------------------------------ */

/* $fed888 — util_open (`desk/deskdisk.h`). */
void aes_desk_util_open(uint8_t *image)
{
    uint16_t rect_local[FRAME_LOCAL_WORDS(UTIL_OPEN_RECT_BYTES)];
    uint32_t rect = host_slot_claim(AES_DESK_UTIL_OPEN_RECT, rect_local);

    (void)aes_desk_appl_init(image);
    (void)aes_rom_ram(image, ROM_RSC_FORMAT, AES_DESK_APP_GLOBAL, 0);
    (void)aes_desk_rsrc_gaddr(image, R_TREE, 0, AES_DESK_UTIL_TREE);
    (void)aes_desk_rsrc_gaddr(image, R_TEDINFO, 0, AES_DESK_UTIL_TEDINFOS);
    wr16(image + AES_DESK_UTIL_BAR_X, bus_word(image, util_object(image, UTIL_WRITE_FRAME) + OB_X));
    wr16(image + AES_DESK_UTIL_BAR_Y, bus_word(image, util_object(image, UTIL_WRITE_FRAME) + OB_Y));
    aes_ob_center(image, util_object(image, UTIL_FORMAT_DIALOG), rect);
    aes_ob_center(image, util_object(image, UTIL_COPY_DIALOG), rect);
    aes_ob_center(image, util_object(image, UTIL_PROGRESS), rect);
    host_slot_release(AES_DESK_UTIL_OPEN_RECT);
    aes_desk_wait(image, DESK_WAIT_DONE);
}

/* $fee236 — util_show (`desk/deskdisk.h`): the clip is the utility tree's ROOT box, whatever `tree` is drawn. */
void aes_desk_util_show(uint8_t *image, uint32_t tree, int16_t depth, int16_t run, int16_t start)
{
    uint32_t root = util_tree(image);

    aes_desk_objc_draw(image, tree, OB_ROOT, depth, (int16_t)(bus_word(image, root + OB_X) - UTIL_DIALOG_MARGIN),
                       (int16_t)(bus_word(image, root + OB_Y) - UTIL_DIALOG_MARGIN),
                       (int16_t)(bus_word(image, root + OB_WIDTH) + 2 * UTIL_DIALOG_MARGIN),
                       (int16_t)(bus_word(image, root + OB_HEIGHT) + 2 * UTIL_DIALOG_MARGIN));
    if (run)
        (void)aes_fm_do(image, tree, start);
}

/* $fee450 — util_redraw (`desk/deskdisk.h`). */
void aes_desk_util_redraw(uint8_t *image)
{
    aes_sh_draw(image, be32(image + AES_DESK_UTIL_COMMAND), UTIL_REDRAW_OBJECT, UTIL_REDRAW_DEPTH);
}

/* $fee466 — fat_swap (`desk/deskdisk.h`). */
uint16_t aes_desk_fat_swap(uint8_t *image, uint32_t word)
{
    uint16_t value = bus_word(image, word);

    value = (uint16_t)(value >> FAT_SWAP_BITS | value << FAT_SWAP_BITS);
    set_bus_word(image, word, value);
    return value;
}

/* $fee166 — util_bars (`desk/deskdisk.h`): each answer stored, then read again from where it was stored. */
void aes_desk_util_bars(uint8_t *image, uint32_t step, uint32_t width, int16_t tracks)
{
    uint32_t box = util_object(image, UTIL_PROGRESS);
    int16_t box_x = (int16_t)bus_word(image, box + OB_X), box_y = (int16_t)bus_word(image, box + OB_Y);
    uint32_t frame_width = util_object(image, UTIL_WRITE_FRAME) + OB_WIDTH;

    set_bus_word(image, step, (uint16_t)quotient_word(m68k_divs_w((uint32_t)(int32_t)(int16_t)bus_word(image, frame_width),
                                                                   UTIL_BAR_TRACKS)));
    set_bus_word(image, width, (uint16_t)m68k_muls_w(bus_word(image, step), UTIL_BAR_TRACKS));
    set_bus_word(image, frame_width, bus_word(image, width));
    set_bus_word(image, util_object(image, UTIL_READ_FRAME) + OB_WIDTH, bus_word(image, width));
    aes_desk_util_show(image, util_object(image, UTIL_PROGRESS), UTIL_DRAW_DEPTH_BOX, UTIL_DRAW_ONLY, UTIL_NO_START);
    set_bus_word(image, util_object(image, UTIL_WRITE_BAR) + OB_X, (uint16_t)(box_x + be16(image + AES_DESK_UTIL_BAR_X)));
    set_bus_word(image, util_object(image, UTIL_WRITE_BAR) + OB_Y, (uint16_t)(box_y + be16(image + AES_DESK_UTIL_BAR_Y)));
    set_bus_word(image, util_object(image, UTIL_READ_BAR) + OB_X,
                 (uint16_t)(box_x + bus_word(image, util_object(image, UTIL_READ_FRAME) + OB_X)));
    set_bus_word(image, util_object(image, UTIL_READ_BAR) + OB_Y,
                 (uint16_t)(box_y + bus_word(image, util_object(image, UTIL_READ_FRAME) + OB_Y)));
    if (tracks == UTIL_BAR_HALF_TRACKS)
        add_word_in_memory(image, step, bus_word(image, step));
    aes_desk_wait(image, UTIL_BAR_HOURGLASS);
}

/* $fee364 — util_error (`desk/deskdisk.h`). NOT INLINED: its five call sites are one routine's in the ROM, and GCC
 * copied it into Format three times and into the copy once (128 B more text) — and crit_err keeps its one C caller. */
__attribute__((noinline)) void aes_desk_util_error(uint8_t *image, int16_t error, int16_t drive)
{
    aes_desk_util_redraw(image);
    aes_desk_wait(image, DESK_WAIT_DONE);
    if (error < 0)
        (void)aes_crit_err(image, error, drive);
    else
        (void)aes_fm_alert(image, FORMAT_ALERT_DEFAULT, error ? UTIL_ALERT_ERROR : UTIL_ALERT_NOT_THE_SAME_TYPE);
}

/* $fee3a4 — fat_mark (`desk/deskdisk.h`): the 12-bit entry's two bytes copied out, swapped, masked, swapped back. */
void aes_desk_fat_mark(uint8_t *image, int16_t cluster, int16_t unread, uint32_t bpb, uint32_t fat)
{
    uint16_t word_local[FRAME_LOCAL_WORDS(FAT_MARK_WORD_BYTES)];
    uint32_t word = host_slot_claim(AES_DESK_FAT_MARK_WORD, word_local);
    int odd = cluster & 1;
    uint32_t at;

    (void)unread;
    if (bus_byte(image, bpb + BPB_BFLAGS_LOW_BYTE) & 1u << BPB_FAT16_BIT) {
        set_bus_word(image, fat + (uint32_t)(int32_t)(int16_t)((uint16_t)cluster << 1), FAT16_BAD);
    } else {
        at = fat + (uint32_t)(int32_t)(int16_t)((cluster >> 1) + cluster);
        set_bus_byte(image, word, bus_byte(image, at));
        set_bus_byte(image, word + 1, bus_byte(image, at + 1));
        (void)aes_desk_fat_swap(image, word);
        set_bus_word(image, word, (uint16_t)((bus_word(image, word) & (odd ? FAT12_KEEP_ODD : FAT12_KEEP_EVEN))
                                             | (odd ? FAT12_BAD_ODD : FAT12_BAD_EVEN)));
        (void)aes_desk_fat_swap(image, word);
        set_bus_byte(image, at, bus_byte(image, word));
        set_bus_byte(image, at + 1, bus_byte(image, word + 1));
    }
    host_slot_release(AES_DESK_FAT_MARK_WORD);
}

/* $fee294 — copy_tracks (`desk/deskdisk.h`). */
int16_t aes_desk_copy_tracks(uint8_t *image, int16_t op, uint32_t buffer, uint32_t filler, int16_t device,
                             int16_t side, int16_t step, int16_t first, int16_t count)
{
    int16_t answer = first;             /* the caller's D4 (the file's header)                                    */

    for (int16_t track = first; track < (int16_t)(count + first); track++) {
        uint32_t bar = util_object(image, op == XBIOS_FLOPWR_FN ? UTIL_WRITE_BAR : UTIL_READ_BAR);

        add_word_in_memory(image, bar + OB_WIDTH, (uint16_t)step);
        aes_desk_util_show(image, bar, UTIL_DRAW_DEPTH_BAR, UTIL_DRAW_ONLY, UTIL_NO_START);
        answer = floprw(image, AES_COPY_TRACKS_RETURN, op, buffer, filler, device, FLOPPY_FIRST_SECTOR, track, side,
                        FLOPPY_SECTORS);
        if (op == XBIOS_FLOPWR_FN && !answer)
            answer = floprw(image, AES_COPY_TRACKS_VERIFY_RETURN, XBIOS_FLOPRD_FN, buffer, filler, device,
                            FLOPPY_FIRST_SECTOR, track, side, FLOPPY_SECTORS);
        if (answer) {
            aes_desk_util_error(image, answer, device);
            break;
        }
        buffer += FLOPPY_TRACK_BYTES;
    }
    return answer;
}

/* ---- Format ------------------------------------------------------------------------------------------------------ */

/* The disk Format's dialog asked for: its sides, the skew a side and the prototype boot sector's type. */
typedef struct {
    int16_t sides, skew, type;
} Formatted;

/* The skew table turned on by `skew` for the next side (the ROM's -70(a6), turned through -52(a6) — the table
 * Flopfmt is handed — and copied back). */
static void turn_the_skew(uint8_t *image, int16_t *order, uint32_t turned, int16_t skew)
{
    for (int16_t at = 0; at < FLOPPY_SECTORS; at++)
        set_bus_word(image, turned + (uint32_t)at * M68K_WORD_BYTES,
                     (uint16_t)order[at >= skew ? at - skew : FLOPPY_SECTORS - skew + at]);
    for (int16_t at = 0; at < FLOPPY_SECTORS; at++)
        order[at] = (int16_t)bus_word(image, turned + (uint32_t)at * M68K_WORD_BYTES);
}

/* Flopfmt's bad sectors (its list at the buffer's head, a zero word ending it) added to the format's list as records
 * of the disk: each the sector's own number past the track's first record, less one. The verdict 0 once one was
 * added — and as Flopfmt answered (-16) where the list was empty. */
static int16_t listed(uint8_t *image, uint32_t buffer, uint32_t bad_list, int16_t *bad, int16_t track, int16_t side,
                      int16_t sides, int16_t verdict)
{
    for (int16_t at = 0; bus_word(image, buffer + (uint32_t)(int32_t)at * M68K_WORD_BYTES); at++, (*bad)++) {
        int16_t record = (int16_t)(track * sides * FLOPPY_SECTORS + (int16_t)bus_word(image, buffer + (uint32_t)(int32_t)at * M68K_WORD_BYTES)
                                   + side * FLOPPY_SECTORS - 1);

        set_bus_word(image, bad_list + (uint32_t)(int32_t)*bad * M68K_WORD_BYTES, (uint16_t)record);
        verdict = 0;
    }
    return verdict;
}

/* One side of one track formatted, its bad sectors listed, track 0 read back: the verdict — 0 done, a failure's
 * otherwise (util_error'd here but for Flopfmt's own -16 with an empty list). FORMAT_FAILED where a bad sector is
 * fatal: the caller stops at once. */
static int16_t format_side(uint8_t *image, uint32_t buffer, uint32_t bad_list, uint32_t turned, int16_t *bad,
                           int16_t drive, int16_t track, int16_t side, int16_t sides)
{
    int16_t verdict = flopfmt(image, buffer, turned, drive, track, side);

    if (verdict < 0 && verdict > FLOPFMT_BAD_SECTORS)
        aes_desk_util_error(image, verdict, drive);
    if (verdict == FLOPFMT_BAD_SECTORS) {
        if (track < FORMAT_GOOD_TRACKS || *bad + FLOPPY_SECTORS >= FORMAT_BAD_ROOM) {
            aes_desk_util_error(image, FORMAT_FAILED, drive);
            return FORMAT_FAILED;
        }
        verdict = listed(image, buffer, bad_list, bad, track, side, sides, verdict);
    }
    if (track == FLOPPY_BOOT_TRACK && !verdict)
        verdict = boot_sector(image, AES_FORMAT_FLOPRD_RETURN, XBIOS_FLOPRD_FN, buffer, FLOPPY_NO_FILLER, drive);
    if (verdict < 0)
        aes_desk_util_error(image, FORMAT_FAILED, drive);
    return verdict;
}

/* Every track of every side formatted, the write bar stepped after each track: the verdict (0 done). */
static int16_t format_tracks(uint8_t *image, uint32_t frame, uint32_t buffer, uint32_t bad_list, int16_t *bad,
                             int16_t drive, Formatted disk)
{
    int16_t order[FLOPPY_SECTORS], verdict = 0;

    for (int16_t at = 0; at < FLOPPY_SECTORS; at++)
        order[at] = (int16_t)bus_word(image, FORMAT_SKEW_TABLE + (uint32_t)at * M68K_WORD_BYTES);
    for (int16_t track = 0; track < FORMAT_TRACKS && !verdict; track++) {
        for (int16_t side = 0; side < disk.sides && !verdict; side++) {
            turn_the_skew(image, order, frame + UTIL_FRAME_SKEW, disk.skew);
            verdict = format_side(image, buffer, bad_list, frame + UTIL_FRAME_SKEW, bad, drive, track, side, disk.sides);
        }
        if (!verdict) {
            add_word_in_memory(image, util_object(image, UTIL_WRITE_BAR) + OB_WIDTH, bus_word(image, frame + UTIL_FRAME_BAR_STEP));
            aes_desk_util_show(image, util_object(image, UTIL_WRITE_BAR), UTIL_DRAW_DEPTH_BAR, UTIL_DRAW_ONLY, UTIL_NO_START);
        }
    }
    return verdict;
}

/* `words` words of `buffer` cleared. */
static void cleared(uint8_t *image, uint32_t buffer, int16_t words)
{
    for (int16_t at = 0; at < words; at++)
        set_bus_word(image, buffer + (uint32_t)(int32_t)at * M68K_WORD_BYTES, 0);
}

/* The formatted disk made a disk: the boot sector (Protobt, written twice round Getbpb), the root holding the label,
 * both FATs with each bad sector's cluster marked. */
static void format_layout(uint8_t *image, uint32_t buffer, uint32_t bad_list, int16_t bad, int16_t drive, int16_t type)
{
    uint32_t bpb;
    int16_t words;

    protobt(image, AES_FORMAT_PROTOBT_RETURN, buffer, type, PROTOBT_NOT_EXECUTABLE);
    (void)boot_sector(image, AES_FORMAT_FLOPWR_RETURN, XBIOS_FLOPWR_FN, buffer, FORMAT_FLOPWR_FILLER, drive);
    bpb = getbpb(image, AES_FORMAT_GETBPB_RETURN, drive);
    (void)boot_sector(image, AES_FORMAT_FLOPWR_AGAIN_RETURN, XBIOS_FLOPWR_FN, buffer, FORMAT_FLOPWR_FILLER, drive);
    words = (int16_t)((int16_t)(uint16_t)((uint16_t)aes_max((int16_t)bus_word(image, bpb + BPB_FSIZ),
                                                            (int16_t)bus_word(image, bpb + BPB_RDLEN))
                                          << FLOPPY_SECTOR_SHIFT) / M68K_WORD_BYTES);
    cleared(image, buffer, words);
    set_bus_word(image, buffer + FORMAT_LABEL_ATTRIBUTE_AT, FORMAT_LABEL_ATTRIBUTE_WORD);
    aes_lbcopy(image, buffer, bus_long(image, util_ted(image, UTIL_TED_LABEL) + TE_PTEXT), FORMAT_LABEL_BYTES);
    rwabs_write(image, AES_FORMAT_ROOT_RWABS_RETURN, buffer, (int16_t)bus_word(image, bpb + BPB_RDLEN),
                (int16_t)(bus_word(image, bpb + BPB_FSIZ) * 2 + 1), drive);
    cleared(image, buffer, words);
    set_bus_word(image, buffer, FAT_MEDIA_WORD_0);
    set_bus_word(image, buffer + M68K_WORD_BYTES, FAT_MEDIA_WORD_1);
    for (int16_t at = 0; at < bad; at++) {
        int16_t record = (int16_t)(bus_word(image, bad_list + (uint32_t)(int32_t)at * M68K_WORD_BYTES)
                                   - bus_word(image, bpb + BPB_DATREC));

        aes_desk_fat_mark(image, (int16_t)(quotient_word(m68k_divs_w((uint32_t)(int32_t)record, bus_word(image, bpb + BPB_CLSIZ)))
                                           + FAT_FIRST_CLUSTER), -1, bpb, buffer);
    }
    rwabs_write(image, AES_FORMAT_FAT_RWABS_RETURN, buffer, (int16_t)bus_word(image, bpb + BPB_FSIZ), FAT_FIRST_RECORD,
                drive);
    rwabs_write(image, AES_FORMAT_FAT2_RWABS_RETURN, buffer, (int16_t)bus_word(image, bpb + BPB_FSIZ),
                (int16_t)(bus_word(image, bpb + BPB_FSIZ) + FAT_FIRST_RECORD), drive);
}

/* One FORMAT clicked: the disk asked for, the bars laid, every track formatted, the disk laid out, the space alerted. */
static void format_once(uint8_t *image, uint32_t frame, uint32_t tail, uint32_t command, uint32_t buffer,
                        uint32_t bad_list)
{
    Formatted disk = {FORMAT_SIDES_SINGLE, FORMAT_SKEW_SINGLE, FORMAT_TYPE_SINGLE};
    int16_t drive, bad = 0, verdict;

    if (bus_word(image, util_object(image, UTIL_DOUBLE_SIDED) + OB_STATE))
        disk = (Formatted){FORMAT_SIDES_DOUBLE, FORMAT_SKEW_DOUBLE, FORMAT_TYPE_DOUBLE};
    set_bus_long(image, util_object(image, UTIL_PROGRESS_TEXT) + OB_SPEC, command);
    aes_desk_util_bars(image, frame + UTIL_FRAME_BAR_STEP, frame + UTIL_FRAME_BAR_WIDTH, FORMAT_TRACKS);
    set_bus_word(image, util_object(image, UTIL_WRITE_BAR) + OB_WIDTH, 0);
    drive = drive_of(image, tail);
    verdict = format_tracks(image, frame, buffer, bad_list, &bad, drive, disk);
    if (!verdict)
        format_layout(image, buffer, bad_list, bad, drive, disk.type);
    aes_desk_wait(image, DESK_WAIT_DONE);
    if (verdict)
        return;
    (void)aes_dos_space(image, (int16_t)(drive + 1), frame + UTIL_FRAME_SPACE_TOTAL, frame + UTIL_FRAME_SPACE_FREE);
    aes_merge_str(image, buffer, UTIL_ALERT_SPACE, frame + UTIL_FRAME_SPACE_FREE);
    aes_desk_util_redraw(image);
    (void)aes_fm_alert(image, FORMAT_ALERT_DEFAULT, buffer);
}

/* $fed912 — desk_format (`desk/deskdisk.h`). Its answer: desk_rsrc_free's. */
int16_t aes_desk_format(uint8_t *image, uint32_t tail, uint32_t command)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(UTIL_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_UTIL_FRAME, frame_local);
    uint32_t buffer = aes_dos_alloc(image, FORMAT_BUFFER_BYTES);
    uint32_t bad_list = aes_dos_alloc(image, FORMAT_BUFFER_BYTES);
    int16_t answer;

    aes_desk_util_open(image);
    set_bus_long(image, util_ted(image, UTIL_TED_FORMAT_DRIVE) + TE_PTEXT, tail);
    wr32(image + AES_DESK_UTIL_COMMAND, command);
    for (;;) {
        set_bus_word(image, util_ted(image, UTIL_TED_LABEL) + TE_TXTLEN, UTIL_LABEL_TXTLEN);
        aes_desk_util_show(image, util_tree(image), UTIL_DRAW_DEPTH_DIALOG, UTIL_RUN, UTIL_FORMAT_START);
        if (pressed(image, UTIL_FORMAT_EXIT))
            break;
        set_bus_word(image, util_object(image, UTIL_FORMAT_GO) + OB_STATE, 0);
        format_once(image, frame, tail, command, buffer, bad_list);
    }
    (void)aes_dos_free(image, AES_FORMAT_FREE_RETURN, buffer);
    (void)aes_dos_free(image, AES_FORMAT_FREE_TREE_RETURN, util_tree(image));
    (void)aes_dos_free(image, AES_FORMAT_FREE_LIST_RETURN, bad_list);
    answer = aes_desk_rsrc_free(image);
    host_slot_release(AES_DESK_UTIL_FRAME);
    return answer;
}

/* ---- the disk copy ----------------------------------------------------------------------------------------------- */

/* The copy's two drives and the blocks it holds. */
typedef struct {
    int16_t source, destination;
    uint32_t free_at_start, tracks_block, boot_block;
} Copying;

/* Each bar blanked, drawn, given its colour back: a side copied. */
static void bars_blanked(uint8_t *image)
{
    for (int16_t bar = COPY_FIRST_BAR; bar < COPY_LAST_BAR_BOUND; bar += COPY_BAR_STRIDE) {
        set_bus_long(image, util_object(image, bar) + OB_SPEC, UTIL_BAR_SPEC_BLANK);
        aes_desk_util_show(image, util_object(image, bar), UTIL_DRAW_DEPTH_BAR, UTIL_DRAW_ONLY, UTIL_NO_START);
        set_bus_long(image, util_object(image, bar) + OB_SPEC, UTIL_BAR_SPEC_FILLED);
    }
}

/* One side copied: the tracks a bufferful at a time (`per`, as many as the free memory at the start holds), then the
 * rest in one more pass; the boot sector read, re-serialled and written with the first chunk of a pass once
 * `boot_due`. 1 where a read or a write failed. */
static int16_t copy_side(uint8_t *image, const Copying *copy, uint32_t fillers[2], int16_t step, int16_t tracks,
                         int16_t side, int16_t *boot_due)
{
    int16_t first = 0;
    int16_t per = (int16_t)aes_ldiv(image, (int32_t)copy->free_at_start, FLOPPY_TRACK_BYTES);
    int16_t chunks = quotient_word(m68k_divs_w((uint32_t)(int32_t)tracks, (uint16_t)per));

    for (int16_t pass = 0; pass < COPY_PASSES; pass++) {
        for (int16_t chunk = 0; chunk < chunks; chunk++) {
            if (aes_desk_copy_tracks(image, XBIOS_FLOPRD_FN, copy->tracks_block, fillers[0], copy->source, side, step,
                                     first, per))
                return 1;
            if (*boot_due) {
                (void)boot_sector(image, AES_COPY_FLOPRD_RETURN, XBIOS_FLOPRD_FN, copy->boot_block, fillers[0], copy->source);
                protobt(image, AES_COPY_PROTOBT_RETURN, copy->boot_block, PROTOBT_KEEP, PROTOBT_KEEP);
            }
            if (aes_desk_copy_tracks(image, XBIOS_FLOPWR_FN, copy->tracks_block, fillers[1], copy->destination, side,
                                     step, first, per))
                return 1;
            if (*boot_due) {
                (void)boot_sector(image, AES_COPY_FLOPWR_RETURN, XBIOS_FLOPWR_FN, copy->boot_block, fillers[1],
                                  copy->destination);
                *boot_due = 0;
            }
            first = (int16_t)(first + per);
        }
        if (side == 0)
            *boot_due = 1;
        per = remainder_word(m68k_divs_w((uint32_t)(int32_t)tracks, (uint16_t)per));
        chunks = 1;
    }
    return 0;
}

/* One COPY clicked: both disks' BPBs; none, or two of other tracks or sides, end the copy (0, the latter alerted);
 * else every side copied, its bars blanked — 1, the dialog again. */
static int copy_once(uint8_t *image, const Copying *copy, uint32_t frame, uint32_t command)
{
    uint32_t fillers[2], source_bpb, destination_bpb;
    int16_t tracks, sides, failed = 0, boot_due = 0;

    destination_bpb = getbpb(image, AES_COPY_DESTINATION_GETBPB_RETURN, copy->destination);
    fillers[1] = xbios_stub_11(image, AES_COPY_DESTINATION_STUB_RETURN, copy->destination);
    source_bpb = getbpb(image, AES_COPY_SOURCE_GETBPB_RETURN, copy->source);
    fillers[0] = xbios_stub_11(image, AES_COPY_SOURCE_STUB_RETURN, copy->source);
    aes_desk_wait(image, DESK_WAIT_DONE);
    if (!source_bpb || !destination_bpb)
        return 0;
    if (bus_word(image, source_bpb + FLOPPY_BPB_TRACKS) != bus_word(image, destination_bpb + FLOPPY_BPB_TRACKS)
        || bus_word(image, source_bpb + FLOPPY_BPB_SIDES) != bus_word(image, destination_bpb + FLOPPY_BPB_SIDES)) {
        aes_desk_util_error(image, UTIL_ERROR_NOT_THE_SAME_TYPE, copy->source);
        return 0;
    }
    tracks = (int16_t)bus_word(image, source_bpb + FLOPPY_BPB_TRACKS);
    sides = (int16_t)bus_word(image, source_bpb + FLOPPY_BPB_SIDES);
    set_bus_long(image, util_object(image, UTIL_PROGRESS_TEXT) + OB_SPEC, command);
    aes_desk_util_bars(image, frame + UTIL_FRAME_BAR_STEP, frame + UTIL_FRAME_BAR_WIDTH, tracks);
    for (int16_t side = 0; side < sides && !failed; side++) {
        set_bus_word(image, util_object(image, UTIL_WRITE_BAR) + OB_WIDTH, 0);
        set_bus_word(image, util_object(image, UTIL_READ_BAR) + OB_WIDTH, 0);
        failed = copy_side(image, copy, fillers, (int16_t)bus_word(image, frame + UTIL_FRAME_BAR_STEP), tracks, side,
                           &boot_due);
        if (!failed)
            bars_blanked(image);
    }
    aes_desk_wait(image, DESK_WAIT_DONE);
    return 1;
}

/* The progress box linked for both bars (`linked`), or for the write bar alone as Format shows it. */
static void progress_linked(uint8_t *image, int linked)
{
    set_bus_word(image, util_object(image, UTIL_WRITE_FRAME) + OB_NEXT,
                 linked ? PROGRESS_WRITE_FRAME_NEXT_COPY : PROGRESS_WRITE_FRAME_NEXT_FORMAT);
    set_bus_word(image, util_object(image, UTIL_PROGRESS) + OB_TAIL,
                 linked ? PROGRESS_LAST_CHILD_COPY : PROGRESS_LAST_CHILD_FORMAT);
}

/* $fedde4 — desk_copy_disk (`desk/deskdisk.h`). Its answer: the free memory less the kilobyte where that is less than
 * a track's (the ROM's D0 there), 0 where the second Malloc failed, else desk_rsrc_free's. */
int16_t aes_desk_copy_disk(uint8_t *image, uint32_t tail, uint32_t command)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(UTIL_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_UTIL_FRAME, frame_local);
    Copying copy;
    int16_t answer;

    copy.free_at_start = aes_dos_avail(image);
    if ((int32_t)(copy.free_at_start - COPY_HELD_BACK_BYTES) < FLOPPY_TRACK_BYTES) {
        host_slot_release(AES_DESK_UTIL_FRAME);
        return (int16_t)(copy.free_at_start - COPY_HELD_BACK_BYTES);
    }
    copy.tracks_block = aes_dos_alloc(image, copy.free_at_start - COPY_HELD_BACK_BYTES);
    copy.boot_block = aes_dos_alloc(image, COPY_BOOT_BYTES);
    if (!copy.boot_block) {
        host_slot_release(AES_DESK_UTIL_FRAME);
        return 0;
    }
    aes_desk_util_open(image);
    set_bus_long(image, util_ted(image, UTIL_TED_COPY_SOURCE) + TE_PTEXT, tail);
    set_bus_long(image, util_ted(image, UTIL_TED_COPY_DESTINATION) + TE_PTEXT, tail + COPY_DESTINATION_IN_THE_TAIL);
    copy.source = drive_of(image, tail);
    copy.destination = drive_of(image, tail + COPY_DESTINATION_IN_THE_TAIL);
    progress_linked(image, 1);
    wr32(image + AES_DESK_UTIL_COMMAND, command);
    do {
        aes_desk_util_show(image, util_object(image, UTIL_COPY_DIALOG), UTIL_DRAW_DEPTH_COPY, UTIL_RUN, UTIL_COPY_START);
        if (pressed(image, UTIL_COPY_EXIT))
            break;
        set_bus_word(image, util_object(image, UTIL_COPY_GO) + OB_STATE, 0);
    } while (copy_once(image, &copy, frame, command));
    progress_linked(image, 0);
    (void)aes_dos_free(image, AES_COPY_FREE_RETURN, copy.tracks_block);
    (void)aes_dos_free(image, AES_COPY_FREE_TREE_RETURN, util_tree(image));
    (void)aes_dos_free(image, AES_COPY_FREE_BOOT_RETURN, copy.boot_block);
    answer = aes_desk_rsrc_free(image);
    host_slot_release(AES_DESK_UTIL_FRAME);
    return answer;
}
/* ---- end of group G2's wave-4 ---- */
