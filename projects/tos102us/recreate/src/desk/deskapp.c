/* deskapp.c — UNIT A, THE DESK'S APPLICATION LIST (`desk/deskapp.h`): the INF's fields read and written, the list of
 * ANODEs, the desktop's grid and the current path kept — Alcyon C in the ROM, each ported over its own order.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/cart.h"
#include "aes/deskleaf.h"
#include "aes/gemdosif.h"
#include "aes/geminit.h"
#include "aes/gemgraf.h"
#include "aes/gsxif.h"
#include "aes/infscan.h"
#include "aes/objects.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "aes/trp14.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskdir.h"
#include "desk/deskfun.h"
#include "desk/deskleaf.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

_Static_assert(APP_TRAN_BITBLK_BYTES == HOST_SLOT_AES_APP_TRAN_BITBLK_BYTES, "app_tran's answer word and its host slot");

/* $fdb014 — scan_str: the cursor past its blanks; the text from there TO ITS `@` copied into the desk's string
 * buffer at g_pbuff, NUL-ended, its address stored through `string_out` and g_pbuff moved past the NUL; the cursor
 * past the `@`. (No bound: a text with no `@` runs on, as the ROM's does.) */
uint32_t aes_scan_str(uint8_t *image, uint32_t cursor, uint32_t string_out)
{
    uint32_t desk = desk_globals(image);
    uint32_t kept;

    while (bus_byte(image, cursor) == INF_FIELD_SEPARATOR)
        cursor++;
    kept = bus_long(image, desk + DESK_STRING_CURSOR);
    set_bus_long(image, string_out, kept);
    while (bus_byte(image, cursor) != INF_TEXT_END)
        set_bus_byte(image, kept++, bus_byte(image, cursor++));
    set_bus_byte(image, kept++, STRING_NUL);
    set_bus_long(image, desk + DESK_STRING_CURSOR, kept);
    return cursor + 1;
}

/* $fdb05a — save_str: the text written at the cursor — a NULL `string` ends it too, tested AFTER the byte it points
 * at (`tst.b (a4) / move.l a4,d0 / bne`) — then `@` and a blank; the cursor past them. */
uint32_t aes_save_str(uint8_t *image, uint32_t cursor, uint32_t string)
{
    while (bus_byte(image, string) != STRING_NUL && string != 0)
        set_bus_byte(image, cursor++, bus_byte(image, string++));
    set_bus_byte(image, cursor++, INF_TEXT_END);
    set_bus_byte(image, cursor++, INF_FIELD_SEPARATOR);
    return cursor;
}

/* app_parse's type letter: a_type, and a_flags where its arm stores them — a folder's arm the type alone, a letter
 * outside the table's 'C'..'T' (or a hole in it) neither. */
static void set_type(uint8_t *image, uint32_t anode, int16_t letter)
{
    switch (letter) {
    case INF_TYPE_TRASH:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISTRSH);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_ON_DESK_FLAGS);
        break;
    case INF_TYPE_DISK:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISDISK);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_ON_DESK_FLAGS);
        break;
    case INF_TYPE_CARTRIDGE:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISCART);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_ON_DESK_FLAGS);
        break;
    case INF_TYPE_GEM_APP:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISFILE);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_GEM_APP_FLAGS);
        break;
    case INF_TYPE_TOS_APP:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISFILE);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_TOS_APP_FLAGS);
        break;
    case INF_TYPE_TTP_APP:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISFILE);
        set_bus_word(image, anode + ANODE_FLAGS, ANODE_TTP_APP_FLAGS);
        break;
    case INF_TYPE_FOLDER:
        set_bus_word(image, anode + ANODE_TYPE, AT_ISFOLD);
        break;
    }
}

/* $fdb082 — app_parse: one INF line from its type letter (a signed byte) — the type; an icon ON THE DESKTOP (the
 * flags as they stand after the letter) its spot's two fields; its two icons' fields; its letter (0 for a blank);
 * its two texts. The cursor past them. */
uint32_t aes_app_parse(uint8_t *image, uint32_t cursor, uint32_t anode)
{
    int8_t letter;

    set_type(image, anode, (int8_t)bus_byte(image, cursor));
    cursor += INF_TYPE_FIELD_BYTES;
    if (bus_word(image, anode + ANODE_FLAGS) & ANODE_ON_THE_DESKTOP) {
        cursor = aes_scan_2(image, cursor, anode + ANODE_XSPOT);
        cursor = aes_scan_2(image, cursor, anode + ANODE_YSPOT);
    }
    cursor = aes_scan_2(image, cursor, anode + ANODE_AICON);
    cursor = aes_scan_2(image, cursor, anode + ANODE_DICON);
    letter = (int8_t)bus_byte(image, cursor);
    set_bus_word(image, anode + ANODE_LETTER, (uint16_t)(letter == INF_FIELD_SEPARATOR ? INF_NO_LETTER : letter));
    cursor += INF_LETTER_FIELD_BYTES;
    cursor = aes_scan_str(image, cursor, anode + ANODE_PAPPL);
    return aes_scan_str(image, cursor, anode + ANODE_PDATA);
}

/* $fdb186 — app_tran: the desk resource's BITBLK `index` (rs_gaddr through the desk's binding, its answer word handed
 * BY ADDRESS and read after the binding's yield) turned to the device's form IN PLACE — gsx_trans from its image to
 * its image. The ROM copies the BITBLK into its frame first (lbcopy) and reads the copy: the same words, as nothing
 * between writes the block. gsx_trans's word, as the ROM's D0. */
uint16_t aes_app_tran(uint8_t *image, int16_t index)
{
    uint32_t bitblk_local;
    uint32_t answer = host_slot_claim(AES_APP_TRAN_BITBLK, &bitblk_local);
    uint32_t bitblk, form;
    int16_t form_bytes;

    (void)aes_desk_rsrc_gaddr(image, R_BITBLK, index, answer);
    bitblk = be32(image + answer);
    host_slot_release(AES_APP_TRAN_BITBLK);
    form = bus_long(image, bitblk + BI_PDATA);
    form_bytes = (int16_t)bus_word(image, bitblk + BI_WB);
    return aes_gsx_trans(image, form, form_bytes, form, form_bytes, (int16_t)bus_word(image, bitblk + BI_HL));
}

/* $fdb1c8 — app_getfh: `name` copied into g_tmppth, which is opened read-write — or, `open` 0, created as a plain
 * file: the third argument is READ AND NEVER USED (`$fdb1d4 move.w 14(a6),d7`; Fcreate is handed 0). The handle's
 * word; 0 where the glue says GEMDOS failed. */
int16_t aes_app_getfh(uint8_t *image, int16_t open, uint32_t name, int16_t unused)
{
    uint32_t path = desk_globals(image) + DESK_G_TMPPTH;
    int16_t handle;

    (void)unused;
    (void)aes_strcpy(image, name, path);
    if (open)
        handle = (int16_t)aes_dos_open(image, path, APP_OPEN_READ_WRITE);
    else
        handle = (int16_t)aes_dos_create(image, AES_APP_GETFH_CREATE_RETURN, path, APP_CREATE_PLAIN);
    return be16(image + AES_DOS_ERR) ? 0 : handle;
}

/* A word of an ICONBLK of g_iblist (its first's size is every icon's). */
static inline int16_t iconblk_word(const uint8_t *image, uint32_t iconblk, uint32_t field)
{
    return (int16_t)bus_word(image, iconblk + field);
}

/* The word of g_image_kinds for the image whose index `index` is — an ICONBLK's longword, doubled as a LONG
 * (`movea.l / adda.l a1,a1`), or a loop's word. */
static inline uint32_t image_kind(uint32_t desk, uint32_t index)
{
    return desk + DESK_IMAGE_KINDS + 2 * index;
}

/* An image's address in its block: the block's longword plus `index` images — WHERE app_rdicon WRITES AN ICONBLK
 * IT KEEPS ONLY THE PRODUCT'S LOW WORD, zero-extended (Alcyon's `lmul`, then `swap / clr.w / swap`): the low word of
 * a product is the low words' product's, so one `muls.w` makes it. */
static inline uint32_t image_at_low_word(const uint8_t *image, uint32_t block, uint32_t index, int16_t image_bytes)
{
    return bus_long(image, block) + (uint16_t)m68k_muls_w((uint16_t)index, (uint16_t)image_bytes);
}

/* $fdb220 — app_rdicon: THE DESK'S ICONS FROM THE ROM. The six ICONBLKs copied into g_iblist and again beside it (the
 * copy will point at the masks); the images counted (one past the largest index either field names, up to the
 * ICONBLK whose ib_pmask is -1) and laid in a block of their own (Malloc; rom_ram's part past the ICONBLKs); every
 * image that is some icon's mask numbered in the order of the indices and copied into a block of masks; each
 * ICONBLK's two indices made addresses (the copy's ib_pmask its mask's); every image — the mask block's copy of a mask
 * — turned to the device's form; then app_tran(0). WORD ARITHMETIC as the ROM's: the sizes `muls.w`, the two
 * blocks' lengths zero-extended words. 1. */
int16_t aes_app_rdicon(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t iconblks = desk + DESK_G_IBLIST, masks_list = desk + DESK_MASK_ICONBLKS, iconblk, form;
    int16_t icons, images = 0, masks = 0, words, image_bytes, index, kind, form_bytes, height;

    (void)aes_rom_ram(image, ROM_RSC_DESK_ICONS, iconblks, APP_ICONBLKS_BYTES);
    aes_movs(image, APP_ICONBLKS_BYTES, iconblks, masks_list);
    for (icons = 0; bus_long(image, iconblks + (uint32_t)icons * ICONBLK_BYTES + IB_PMASK) != ICONBLK_LIST_END; icons++) {
        iconblk = iconblks + (uint32_t)icons * ICONBLK_BYTES;
        images = aes_max(images, aes_max((int16_t)bus_long(image, iconblk + IB_PMASK), (int16_t)bus_long(image, iconblk + IB_PDATA)));
    }
    images = (int16_t)(images + 1);
    words = (int16_t)((int16_t)m68k_muls_w((uint16_t)iconblk_word(image, iconblks, ICONBLK_WIDTH),
                                            (uint16_t)iconblk_word(image, iconblks, ICONBLK_HEIGHT)) / ICON_PIXELS_A_WORD);
    image_bytes = (int16_t)((uint16_t)words << 1);
    set_bus_long(image, desk + DESK_ICON_IMAGES, aes_dos_alloc(image, (uint16_t)m68k_muls_w((uint16_t)images, (uint16_t)image_bytes)));
    (void)aes_rom_ram(image, ROM_RSC_DESK_ICONS_TAIL, bus_long(image, desk + DESK_ICON_IMAGES), APP_ICONBLKS_BYTES);
    for (index = 0; index < icons; index++) {
        iconblk = iconblks + (uint32_t)index * ICONBLK_BYTES;
        set_bus_word(image, image_kind(desk, bus_long(image, iconblk + IB_PMASK)), IMAGE_IS_A_MASK);
        set_bus_word(image, image_kind(desk, bus_long(image, iconblk + IB_PDATA)), IMAGE_IS_DATA);
    }
    for (index = 0; index < images; index++) {
        uint32_t at = image_kind(desk, (uint32_t)(int32_t)index);

        if (bus_word(image, at))
            set_bus_word(image, at, (uint16_t)masks++);
        else
            set_bus_word(image, at, (uint16_t)IMAGE_NOT_A_MASK);
    }
    set_bus_long(image, desk + DESK_ICON_MASKS, aes_dos_alloc(image, (uint16_t)m68k_muls_w((uint16_t)masks, (uint16_t)image_bytes)));
    for (index = 0; index < icons; index++) {
        iconblk = iconblks + (uint32_t)index * ICONBLK_BYTES;
        set_bus_long(image, masks_list + (uint32_t)index * ICONBLK_BYTES + IB_PMASK,
                     image_at_low_word(image, desk + DESK_ICON_MASKS,
                                       bus_word(image, image_kind(desk, bus_long(image, iconblk + IB_PMASK))), image_bytes));
        set_bus_long(image, iconblk + IB_PMASK,
                     image_at_low_word(image, desk + DESK_ICON_IMAGES, bus_long(image, iconblk + IB_PMASK), image_bytes));
        form = image_at_low_word(image, desk + DESK_ICON_IMAGES, bus_long(image, iconblk + IB_PDATA), image_bytes);
        set_bus_long(image, iconblk + IB_PDATA, form);
        set_bus_long(image, masks_list + (uint32_t)index * ICONBLK_BYTES + IB_PDATA, form);
    }
    form_bytes = (int16_t)(iconblk_word(image, iconblks, ICONBLK_WIDTH) / ICON_PIXELS_A_BYTE);
    height = iconblk_word(image, iconblks, ICONBLK_HEIGHT);
    for (index = 0; index < images; index++) {
        kind = (int16_t)bus_word(image, image_kind(desk, (uint32_t)(int32_t)index));
        form = bus_long(image, desk + DESK_ICON_IMAGES) + (uint32_t)m68k_muls_w((uint16_t)index, (uint16_t)image_bytes);
        if (kind != IMAGE_NOT_A_MASK) {
            uint32_t mask = bus_long(image, desk + DESK_ICON_MASKS) + (uint32_t)m68k_muls_w((uint16_t)kind, (uint16_t)image_bytes);

            aes_wcopy(image, mask, form, words);
            form = mask;
        }
        (void)aes_gsx_trans(image, form, form_bytes, form, form_bytes, height);
    }
    (void)aes_app_tran(image, APP_TRAN_FIRST_BITBLK);
    return APP_RDICON_DONE;
}

/* One axis of snap_disk, WORD ARITHMETIC throughout: `at` to the grid's multiple below it — the one above where the
 * remainder is past half the grid —, held at most `span` less one grid (min), and where that lies past the span's
 * middle moved on by what the span leaves over the grid. */
static int16_t snapped(int16_t at, int16_t grid, int16_t span)
{
    uint32_t divided = m68k_divs_w((uint32_t)(int32_t)at, (uint16_t)grid);
    int16_t cells = quotient_word(divided);
    int16_t snapped_at;

    if (remainder_word(divided) > grid / 2)
        cells = (int16_t)(cells + 1);
    snapped_at = aes_min((int16_t)m68k_muls_w((uint16_t)cells, (uint16_t)grid), (int16_t)(span - grid));
    if (snapped_at > span / 2)
        snapped_at = (int16_t)(snapped_at + remainder_word(m68k_divs_w((uint32_t)(int32_t)span, (uint16_t)grid)));
    return snapped_at;
}

/* $fdb508 — snap_disk: a point of the desktop snapped to the icons' grid — across over the screen's width, down over
 * the desktop's height measured from its top. Each answer stored through its pointer. (The ROM's also writes its own
 * argument word in its caller's frame, `subw d0,fp@(10)` at $fdb58c — y less g_ydesk, in place; its three callers
 * $fdba04, $fdc314, $fdf2f4 pop it with `addq.l #8` unread. No C can.) */
void aes_snap_disk(uint8_t *image, int16_t x, int16_t y, uint32_t x_out, uint32_t y_out)
{
    uint32_t desk = desk_globals(image);
    int16_t top;

    set_bus_word(image, x_out, (uint16_t)snapped(x, (int16_t)bus_word(image, desk + DESK_GRID_W),
                                                 (int16_t)be16(image + AES_GL_WIDTH)));
    top = (int16_t)bus_word(image, desk + DESK_AREA_Y);
    set_bus_word(image, y_out, (uint16_t)(snapped((int16_t)(y - top), (int16_t)bus_word(image, desk + DESK_GRID_H),
                                                  (int16_t)bus_word(image, desk + DESK_AREA_H)) + top));
}

/* $fdbb0a — app_revit: the list in use turned round, node by node pushed on a list begun empty. */
void aes_app_revit(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t node = bus_long(image, desk + DESK_ANODES_IN_USE);
    uint32_t next;

    set_bus_long(image, desk + DESK_ANODES_IN_USE, ANODE_NONE);
    while (node != ANODE_NONE) {
        next = bus_long(image, node + ANODE_NEXT);
        set_bus_long(image, node + ANODE_NEXT, bus_long(image, desk + DESK_ANODES_IN_USE));
        set_bus_long(image, desk + DESK_ANODES_IN_USE, node);
        node = next;
    }
}

/* $fdbe7e — app_path_save: the current drive (Dgetdrv's word) and its path (Dgetpath, the drive counted from 1)
 * kept; the boot drive made current — C: where set_defdrv found it, else A: (set_defdrv has made it so already:
 * the ROM sets it again) — and its root. Dsetpath's answer. */
uint32_t aes_app_path_save(uint8_t *image)
{
    wr16(image + AES_DESK_KEPT_DRIVE, (uint16_t)aes_dos_gdrv(image, AES_APP_PATH_SAVE_GDRV_RETURN));
    (void)aes_dos_gdir(image, (int16_t)(be16(image + AES_DESK_KEPT_DRIVE) + DGETPATH_DRIVE_BASE), AES_DESK_KEPT_PATH);
    (void)aes_dos_sdrv(image, AES_APP_PATH_SAVE_SDRV_RETURN, aes_set_defdrv(image) ? DRIVE_C : DRIVE_A);
    return aes_dos_chdir(image, AES_APP_PATH_SAVE_CHDIR_RETURN, AES_DESK_ROOT_PATH);
}

/* $fdbeb6 — app_path_restore: the kept drive and path made current again. Dsetpath's answer. */
uint32_t aes_app_path_restore(uint8_t *image)
{
    (void)aes_dos_sdrv(image, AES_APP_PATH_RESTORE_SDRV_RETURN, (int16_t)be16(image + AES_DESK_KEPT_DRIVE));
    return aes_dos_chdir(image, AES_APP_PATH_RESTORE_CHDIR_RETURN, AES_DESK_KEPT_PATH);
}

/* `lsr.w Dn,Dm`: the count taken modulo 64, a word shifted to nothing from 16 on — `asl_word_by`'s (m68k_idioms.h)
 * other direction, kept here while app_blddesk is its one user. */
static inline uint16_t lsr_word_by(uint16_t value, uint16_t count)
{
    unsigned bits = count & M68K_SHIFT_COUNT_MASK;

    return bits < M68K_WORD_BITS ? (uint16_t)(value >> bits) : 0;
}

/* An object of the screen's tree, by its index: the objects inline in the desk's block (DESK_G_SCREEN_OBJECTS — what
 * g_screen, DESK_G_SCREEN, points at). */
static inline uint32_t screen_object(uint32_t desk, int16_t object)
{
    return desk + DESK_G_SCREEN_OBJECTS + (uint32_t)m68k_muls_w((uint16_t)object, OB_BYTES);
}

/* An icon object's ICONBLK in g_icons, by its object's index. */
static inline uint32_t desk_iconblk(uint32_t desk, int16_t object)
{
    return desk + DESK_G_ICONS + (uint32_t)m68k_muls_w((uint16_t)object, ICONBLK_BYTES);
}

/* One ANODE on the desktop made an icon object: the first free object under the desktop at its spot, g_wicon by
 * g_hicon (obj_ialloc: 0 where none is free — and the ROM then makes object 0 over, as this does); a G_ICON of no
 * flags or state; its ICONBLK the mask list's for its icon, its image centred across g_wicon, its text the ANODE's
 * name and its letter ORed into ib_char. */
static void icon_object(uint8_t *image, uint32_t desk, uint32_t anode)
{
    int16_t object = aes_obj_ialloc(image, DESKTOP_ROOT, (int16_t)bus_word(image, anode + ANODE_XSPOT),
                                    (int16_t)bus_word(image, anode + ANODE_YSPOT), (int16_t)bus_word(image, desk + DESK_G_WICON),
                                    (int16_t)bus_word(image, desk + DESK_G_HICON));
    uint32_t tree_object = screen_object(desk, object), iconblk = desk_iconblk(desk, object);

    set_bus_word(image, anode + ANODE_OBID, (uint16_t)object);
    set_bus_word(image, tree_object + OB_STATE, 0);
    set_bus_word(image, tree_object + OB_FLAGS, 0);
    set_bus_word(image, tree_object + OB_TYPE, G_ICON);
    set_bus_word(image, desk + DESK_G_INDEX + 2 * (uint32_t)(int32_t)object, bus_word(image, anode + ANODE_AICON));
    set_bus_long(image, tree_object + OB_SPEC, iconblk);
    aes_movs(image, ICONBLK_BYTES, desk + DESK_MASK_ICONBLKS
             + (uint32_t)m68k_muls_w(bus_word(image, anode + ANODE_AICON), ICONBLK_BYTES), iconblk);
    set_bus_word(image, iconblk + IB_XICON, (uint16_t)((int16_t)(bus_word(image, desk + DESK_G_WICON)
                                                                 - bus_word(image, iconblk + ICONBLK_WIDTH)) / 2));
    set_bus_long(image, iconblk + IB_PTEXT, bus_long(image, anode + ANODE_PAPPL));
    set_bus_word(image, iconblk + IB_CHAR, bus_word(image, iconblk + IB_CHAR) | (bus_word(image, anode + ANODE_LETTER) & ICON_LETTER_BYTE));
}

/* $fdbeec — app_blddesk: the desktop's root (object 1) rebuilt over the whole screen (obj_wfree); its pattern by the
 * resolution (Getrez through the XBIOS door); an icon object for each ANODE on the desktop, in the list's order, a
 * disk's letter setting its drive's bit (A: the top one; a letter past 'P' shifts it out); appl_bvset of the disks'
 * vector and of hard disks none. appl_bvset's answer. */
int16_t aes_app_blddesk(uint8_t *image)
{
    uint32_t desk = desk_globals(image), anode;
    uint16_t disks = 0;
    int16_t rez;

    aes_obj_wfree(image, DESKTOP_ROOT, 0, 0, (int16_t)be16(image + AES_GL_WIDTH), (int16_t)be16(image + AES_GL_HEIGHT));
    rez = (int16_t)aes_trp14(image, AES_APP_BLDDESK_GETREZ_RETURN, XBIOS_GETREZ_FN);
    set_bus_long(image, screen_object(desk, DESKTOP_ROOT) + OB_SPEC,
                 rez == REZ_MONO || rez == REZ_TT_MONO ? DESKTOP_PATTERN_MONO : DESKTOP_PATTERN_COLOUR);
    for (anode = bus_long(image, desk + DESK_ANODES_IN_USE); anode != ANODE_NONE; anode = bus_long(image, anode + ANODE_NEXT)) {
        if (!(bus_word(image, anode + ANODE_FLAGS) & ANODE_ON_THE_DESKTOP))
            continue;
        if (bus_word(image, anode + ANODE_TYPE) == AT_ISDISK)
            disks |= lsr_word_by(DRIVE_A_BIT, (uint16_t)(bus_word(image, anode + ANODE_LETTER) - DRIVE_LETTER_FIRST));
        icon_object(image, desk, anode);
    }
    return aes_desk_appl_bvset(image, (int16_t)disks, 0);
}

/* ---- band 6 wave 2, group G4: DESKTOP.INF read and parsed ---------------------------------------------------------- */
_Static_assert(APP_START_ENVIRONMENT_BYTES == HOST_SLOT_AES_APP_START_ENVIRONMENT_BYTES, "app_start's #E word and its host slot");

static inline uint32_t pool_anode(uint32_t desk, int16_t nth)
{
    return desk + DESK_G_ALIST + (uint32_t)(nth * ANODE_BYTES);
}

/* The INF into g_afile: the shell's buffer as it stands where it begins a line (the INF this desk wrote last), else —
 * a drive in the map — DESKTOP.INF read from the current drive, else the ROM's own; that one NUL-ended at its length
 * (a sign-extended word). */
static void inf_read(uint8_t *image, uint32_t desk)
{
    uint32_t afile = desk + DESK_G_AFILE;
    int16_t handle;

    (void)aes_desk_shel_get(image, afile, INF_BUFFER_BYTES);
    if (bus_byte(image, afile) == INF_LINE_START)
        return;
    if ((uint16_t)aes_isdrive(image) && (handle = aes_app_getfh(image, 1, AES_INF_NAME_READ, 0)) != 0) {
        set_bus_word(image, desk + DESK_G_AFSIZE, (uint16_t)aes_dos_read(image, handle, INF_BUFFER_BYTES, afile));
        (void)aes_dos_close(image, AES_APP_START_CLOSE_RETURN, handle);
    } else {
        set_bus_word(image, desk + DESK_G_AFSIZE, (uint16_t)aes_rom_ram(image, ROM_RSC_DESKTOP_INF, afile, 0));
    }
    set_bus_byte(image, afile + (uint32_t)(int32_t)(int16_t)bus_word(image, desk + DESK_G_AFSIZE), STRING_NUL);
}

/* An icon's line: a node taken (app_alloc, to the list's head) and the line parsed into it. */
static uint32_t icon_line(uint8_t *image, uint32_t cursor)
{
    return aes_app_parse(image, cursor, aes_app_alloc(image, 1));
}

/* A drive's or the trash's line, kept where the map has a drive — drive C:'s only where the map has C:. */
static int drive_line_kept(uint8_t *image, uint32_t cursor)
{
    uint16_t drives = (uint16_t)aes_isdrive(image);

    if (!drives)
        return 0;
    return bus_byte(image, cursor + INF_DRIVE_LETTER_AT) != INF_DRIVE_C || (drives & DRIVE_C_BIT);
}

/* The #E line: the view, the sort and the preferences kept for cnx_get — the two fields scanned into the frame's word
 * (the ROM's then stores (field & 6) + 1 there, GEM's gl_restype, read by none: not reproduced) — and the resolution
 * the AES runs in. The cursor past the second field. */
static uint32_t environment_line(uint8_t *image, uint32_t desk, uint32_t cursor)
{
    uint16_t word_local[FRAME_LOCAL_WORDS(APP_START_ENVIRONMENT_BYTES)];
    uint32_t field = host_slot_claim(AES_APP_START_ENVIRONMENT, word_local);
    uint16_t bits;

    cursor = aes_scan_2(image, cursor + INF_TYPE_FIELD_BYTES, field);
    bits = bus_word(image, field);
    set_bus_word(image, desk + DESK_CNX_VIEW, (bits & INF_E_VIEW_BIT) != 0);
    set_bus_word(image, desk + DESK_CNX_SORT, (uint16_t)((bits & INF_E_SORT_MASK) >> INF_E_SORT_SHIFT));
    set_bus_word(image, desk + DESK_CNX_PREFERENCES + 2, (bits & INF_E_PREFERENCE_1_BIT) != 0);
    set_bus_word(image, desk + DESK_CNX_PREFERENCES, (bits & INF_E_PREFERENCE_0_BIT) != 0);
    cursor = aes_scan_2(image, cursor, field);
    set_bus_word(image, desk + DESK_CNX_PREFERENCES + 4,
                 (uint16_t)((bus_word(image, field) & INF_E_PREFERENCE_2_MASK) >> INF_E_PREFERENCE_2_SHIFT));
    set_bus_word(image, desk + DESK_CNX_RESOLUTION, (uint16_t)(be16(image + AES_GL_RESTYPE) - 1));
    host_slot_release(AES_APP_START_ENVIRONMENT);
    return cursor;
}

/* One word of a #W line's rectangle scanned and made pixels: halved where it is `past` the screen's columns, times
 * the cell's `pixels`, at least `least` (none: 0 and below). */
static uint32_t window_measure(uint8_t *image, uint32_t cursor, uint32_t at, int across, int past_only, int16_t pixels,
                               int16_t least)
{
    int16_t value;

    cursor = aes_scan_2(image, cursor, at);
    value = (int16_t)bus_word(image, at);
    if (across && (past_only ? value > (int16_t)be16(image + AES_GL_NCOLS) : value >= (int16_t)be16(image + AES_GL_NCOLS)))
        value = (int16_t)(value / 2);
    value = (int16_t)(value * pixels);
    if (least > value)
        value = least;
    set_bus_word(image, at, (uint16_t)value);
    return cursor;
}

/* A #W line into the next of g_cnxsave's entries (counted from 0 over the parse, with no bound): its scroll, its
 * rectangle from cells to pixels, its icon, and its path to the `@` — the cursor left AT the `@`. */
static uint32_t window_line(uint8_t *image, uint32_t desk, uint32_t cursor, int16_t *saved)
{
    uint32_t entry = desk + DESK_G_WINDOW_SAVES + (uint32_t)m68k_muls_w((uint16_t)(*saved)++, WINDOW_SAVE_BYTES);
    int16_t wchar = (int16_t)be16(image + AES_GL_WCHAR), hchar = (int16_t)be16(image + AES_GL_HCHAR);
    int16_t no_least = INT16_MIN;
    uint32_t path;

    cursor = aes_scan_2(image, cursor + INF_TYPE_FIELD_BYTES, entry + SAVE_CVCOL);
    cursor = aes_scan_2(image, cursor, entry + SAVE_CVROW);
    cursor = window_measure(image, cursor, entry + SAVE_X, 1, 0, wchar, no_least);
    cursor = window_measure(image, cursor, entry + SAVE_Y, 0, 0, hchar, no_least);
    cursor = window_measure(image, cursor, entry + SAVE_W, 1, 1, wchar,
                            (int16_t)(be16(image + AES_GL_WBOX) * WINDOW_LEAST_BOXES));
    cursor = window_measure(image, cursor, entry + SAVE_H, 0, 0, hchar,
                            (int16_t)(be16(image + AES_GL_HBOX) * WINDOW_LEAST_BOXES));
    cursor = aes_scan_2(image, cursor, entry + SAVE_OBID);
    for (path = entry + SAVE_PATH; bus_byte(image, cursor) != INF_TEXT_END; )
        set_bus_byte(image, path++, bus_byte(image, cursor++));
    set_bus_byte(image, path, STRING_NUL);
    return cursor;
}

/* One line from its type letter (a signed byte; the ROM's switch over 'C'..'W'): the cursor where the parse goes on —
 * at the letter itself where the line is not kept (the next `#` is looked for from there). */
static uint32_t inf_line(uint8_t *image, uint32_t desk, uint32_t cursor, int16_t *saved)
{
    switch ((int8_t)bus_byte(image, cursor)) {
    case INF_TYPE_CARTRIDGE:
        return aes_cart_init(image) ? icon_line(image, cursor) : cursor;
    case INF_TYPE_DISK:
    case INF_TYPE_TRASH:
        return drive_line_kept(image, cursor) ? icon_line(image, cursor) : cursor;
    case INF_TYPE_FOLDER:
    case INF_TYPE_TOS_APP:
    case INF_TYPE_GEM_APP:
    case INF_TYPE_TTP_APP:
        return icon_line(image, cursor);
    case INF_TYPE_ENVIRONMENT:
        return environment_line(image, desk, cursor);
    case INF_TYPE_WINDOW:
        return window_line(image, desk, cursor, saved);
    default:
        return cursor;
    }
}

/* `total` shared over its whole multiples of `cell`: the cell grown by the leftover over their count (DIVS twice). */
static int16_t grid_pitch(int16_t total, int16_t cell)
{
    int16_t count = quotient_word(m68k_divs_w((uint32_t)(int32_t)total, (uint16_t)cell));
    int16_t leftover = remainder_word(m68k_divs_w((uint32_t)(int32_t)total, (uint16_t)cell));

    return (int16_t)(cell + quotient_word(m68k_divs_w((uint32_t)(int32_t)leftover, (uint16_t)count)));
}

/* A point pair's word of an outline: point `nth`'s x (`y` 0) or y. */
static inline void set_outline_word(uint8_t *image, uint32_t outline, int nth, int y, int16_t value)
{
    set_bus_word(image, outline + (uint32_t)(2 * nth + y) * M68K_WORD_BYTES, (uint16_t)value);
}

/* The icons' grid from the first ICONBLK, every node's spot snapped to it, and the drag outlines of both views — the
 * icon's (its image's frame over its label's) and a text line's. */
static void desktop_grid(uint8_t *image, uint32_t desk)
{
    uint32_t iconblk = desk + DESK_G_IBLIST, xyicon = desk + DESK_G_XYICON, xytext = desk + DESK_G_XYTEXT, anode;
    int16_t wicon, hicon, top, small = (int16_t)be16(image + AES_GL_WSCHAR);
    int16_t width = (int16_t)be16(image + AES_GL_WIDTH), height = (int16_t)be16(image + AES_GL_HEIGHT);

    wicon = (int16_t)(2 * iconblk_word(image, iconblk, IB_XTEXT) + iconblk_word(image, iconblk, ICONBLK_WTEXT));
    hicon = (int16_t)(iconblk_word(image, iconblk, ICONBLK_HEIGHT) + iconblk_word(image, iconblk, ICONBLK_HTEXT));
    set_bus_word(image, desk + DESK_G_WICON, (uint16_t)wicon);
    set_bus_word(image, desk + DESK_G_HICON, (uint16_t)hicon);
    set_bus_word(image, desk + DESK_GRID_W,
                 (uint16_t)grid_pitch(width, (int16_t)((height > TALL_SCREEN_LINES ? ICON_SPACE_TALL : 0) + wicon)));
    set_bus_word(image, desk + DESK_GRID_H, (uint16_t)grid_pitch((int16_t)(height - (int16_t)be16(image + AES_GL_HBOX)),
                                                                 (int16_t)(hicon + ICON_SPACE_UNDER)));
    for (anode = bus_long(image, desk + DESK_ANODES_IN_USE); anode != ANODE_NONE; anode = bus_long(image, anode + ANODE_NEXT))
        aes_snap_disk(image, (int16_t)((int16_t)bus_word(image, anode + ANODE_XSPOT) * (int16_t)bus_word(image, desk + DESK_GRID_W)),
                      (int16_t)((int16_t)bus_word(image, anode + ANODE_YSPOT) * (int16_t)bus_word(image, desk + DESK_GRID_H)
                                + (int16_t)bus_word(image, desk + DESK_AREA_Y)),
                      anode + ANODE_XSPOT, anode + ANODE_YSPOT);
    set_bus_word(image, desk + DESK_G_NMICON, ICON_OUTLINE_POINTS);
    set_bus_word(image, desk + DESK_G_NMTEXT, TEXT_OUTLINE_POINTS);
    aes_bfill(image, ICON_OUTLINE_CLEARED, 0, xyicon);
    top = (int16_t)(hicon - small - ICON_OUTLINE_LABEL_GAP);
    set_outline_word(image, xyicon, 0, 0, (int16_t)(small << 2));
    set_outline_word(image, xyicon, 1, 0, (int16_t)(small << 2));
    set_outline_word(image, xyicon, 1, 1, top);
    set_outline_word(image, xyicon, 2, 1, top);
    set_outline_word(image, xyicon, 3, 1, hicon);
    set_outline_word(image, xyicon, 4, 0, wicon);
    set_outline_word(image, xyicon, 4, 1, hicon);
    set_outline_word(image, xyicon, 5, 0, wicon);
    set_outline_word(image, xyicon, 5, 1, top);
    set_outline_word(image, xyicon, 6, 0, (int16_t)(small << 3));
    set_outline_word(image, xyicon, 6, 1, top);
    set_outline_word(image, xyicon, 7, 0, (int16_t)(small << 3));
    set_outline_word(image, xyicon, 8, 0, (int16_t)(small << 2));
    aes_bfill(image, TEXT_OUTLINE_CLEARED, 0, xytext);
    set_outline_word(image, xytext, 1, 0, (int16_t)((int16_t)be16(image + AES_GL_WCHAR) * TEXT_OUTLINE_CELLS));
    set_outline_word(image, xytext, 2, 0, (int16_t)((int16_t)be16(image + AES_GL_WCHAR) * TEXT_OUTLINE_CELLS));
    set_outline_word(image, xytext, 2, 1, (int16_t)be16(image + AES_GL_HCHAR));
    set_outline_word(image, xytext, 3, 1, (int16_t)be16(image + AES_GL_HCHAR));
}

/* $fdb5fc — app_start: THE DESK'S INF. The text buffer begun, the ANODE pool linked free and none in use; the INF read
 * (`inf_read`) and parsed line by line from each `#` (`inf_line`); the icons read from the ROM (app_rdicon — its 0 is
 * this one's); the grid and the outlines (`desktop_grid`). APP_START_DONE. */
int16_t aes_app_start(uint8_t *image)
{
    uint32_t desk = desk_globals(image), cursor;
    int16_t nth, saved = 0;

    set_bus_long(image, desk + DESK_STRING_CURSOR, desk + DESK_G_BUFFER);
    for (nth = DESK_ANODES - 2; nth >= 0; nth--)
        set_bus_long(image, pool_anode(desk, nth) + ANODE_NEXT, pool_anode(desk, (int16_t)(nth + 1)));
    set_bus_long(image, desk + DESK_ANODES_IN_USE, ANODE_NONE);
    set_bus_long(image, desk + DESK_ANODES_FREE, desk + DESK_G_ALIST);
    set_bus_long(image, pool_anode(desk, DESK_ANODES - 1) + ANODE_NEXT, ANODE_NONE);
    inf_read(image, desk);
    for (cursor = desk + DESK_G_AFILE; bus_byte(image, cursor); )
        cursor = bus_byte(image, cursor) == INF_LINE_START ? inf_line(image, desk, cursor + 1, &saved) : cursor + 1;
    if (!aes_app_rdicon(image))
        return APP_START_NO_ICONS;
    desktop_grid(image, desk);
    return APP_START_DONE;
}

/* ---- band 6 wave 2, group G4: DESKTOP.INF written --------------------------------------------------------------------- */
static inline uint32_t put_byte(uint8_t *image, uint32_t cursor, uint8_t byte)
{
    set_bus_byte(image, cursor, byte);
    return cursor + 1;
}

static inline uint32_t line_ended(uint8_t *image, uint32_t cursor)
{
    return put_byte(image, put_byte(image, cursor, INF_CR), INF_LF);
}

/* `#`, the line's letter and its blank. */
static uint32_t line_begun(uint8_t *image, uint32_t cursor, uint8_t letter)
{
    cursor = put_byte(image, cursor, INF_LINE_START);
    cursor = put_byte(image, cursor, letter);
    return put_byte(image, cursor, INF_FIELD_SEPARATOR);
}

/* A word of the desk's globals; a word divided (DIVS: the quotient). */
static inline int16_t desk_word_at(const uint8_t *image, uint32_t at)
{
    return (int16_t)bus_word(image, at);
}

static inline int16_t over(int16_t value, int16_t by)
{
    return quotient_word(m68k_divs_w((uint32_t)(int32_t)value, (uint16_t)by));
}

/* The #E line: the view, the sort and two preferences in the first field; the third preference over the resolution in
 * the second. */
static uint32_t environment_written(uint8_t *image, uint32_t desk, uint32_t cursor)
{
    uint16_t bits = 0;

    cursor = line_begun(image, cursor, INF_TYPE_ENVIRONMENT);
    bits |= desk_word_at(image, desk + DESK_CNX_VIEW) ? INF_E_VIEW_BIT : 0;
    bits |= (uint16_t)(bus_word(image, desk + DESK_CNX_SORT) << INF_E_SORT_SHIFT) & INF_E_SORT_MASK;
    bits |= desk_word_at(image, desk + DESK_CNX_PREFERENCES + 2) ? INF_E_PREFERENCE_1_BIT : 0;
    bits |= desk_word_at(image, desk + DESK_CNX_PREFERENCES) ? INF_E_PREFERENCE_0_BIT : 0;
    cursor = aes_save_2(image, cursor, (int16_t)bits);
    bits = (uint16_t)(bus_word(image, desk + DESK_CNX_RESOLUTION)
                      | (uint16_t)(bus_word(image, desk + DESK_CNX_PREFERENCES + 4) << INF_E_PREFERENCE_2_SHIFT));
    cursor = aes_save_2(image, cursor, (int16_t)bits);
    return line_ended(image, cursor);
}

/* The four #W lines: each g_cnxsave entry's scroll, its rectangle in cells, its icon and its path to its NUL. */
static uint32_t windows_written(uint8_t *image, uint32_t desk, uint32_t cursor)
{
    int16_t wchar = (int16_t)be16(image + AES_GL_WCHAR), hchar = (int16_t)be16(image + AES_GL_HCHAR);

    for (int16_t saved = 0; saved < DESK_WINDOWS; saved++) {
        uint32_t entry = desk + DESK_G_WINDOW_SAVES + (uint32_t)m68k_muls_w((uint16_t)saved, WINDOW_SAVE_BYTES), path;

        cursor = line_begun(image, cursor, INF_TYPE_WINDOW);
        cursor = aes_save_2(image, cursor, desk_word_at(image, entry + SAVE_CVCOL));
        cursor = aes_save_2(image, cursor, desk_word_at(image, entry + SAVE_CVROW));
        cursor = aes_save_2(image, cursor, over(desk_word_at(image, entry + SAVE_X), wchar));
        cursor = aes_save_2(image, cursor, over(desk_word_at(image, entry + SAVE_Y), hchar));
        cursor = aes_save_2(image, cursor, over(desk_word_at(image, entry + SAVE_W), wchar));
        cursor = aes_save_2(image, cursor, over(desk_word_at(image, entry + SAVE_H), hchar));
        cursor = aes_save_2(image, cursor, desk_word_at(image, entry + SAVE_OBID));
        for (path = entry + SAVE_PATH; bus_byte(image, path) != STRING_NUL; path++)
            cursor = put_byte(image, cursor, bus_byte(image, path));
        cursor = put_byte(image, cursor, INF_TEXT_END);
        cursor = line_ended(image, cursor);
    }
    return cursor;
}

/* An ANODE's type letter, as app_parse reads it back: a file's by its flags — a GEM program's both its low two bits,
 * else a TTP's its bit 3, else a TOS program's. A type past the cartridge's writes NO letter. */
static uint32_t type_letter_written(uint8_t *image, uint32_t cursor, uint32_t anode)
{
    uint8_t flags = bus_byte(image, anode + ANODE_FLAGS + OB_WORD_LOW_BYTE);

    switch (bus_word(image, anode + ANODE_TYPE)) {
    case AT_ISFILE:
        if ((flags & ANODE_GEM_APP_FLAGS) == ANODE_GEM_APP_FLAGS)
            return put_byte(image, cursor, INF_TYPE_GEM_APP);
        return put_byte(image, cursor, flags & ANODE_TTP_APP_FLAGS ? INF_TYPE_TTP_APP : INF_TYPE_TOS_APP);
    case AT_ISFOLD:
        return put_byte(image, cursor, INF_TYPE_FOLDER);
    case AT_ISDISK:
        return put_byte(image, cursor, INF_TYPE_DISK);
    case AT_ISTRSH:
        return put_byte(image, cursor, INF_TYPE_TRASH);
    case AT_ISCART:
        return put_byte(image, cursor, INF_TYPE_CARTRIDGE);
    default:
        return cursor;
    }
}

/* One ANODE's line: its letter; on the desktop its spot on the grid (down, from the desktop's top); its two icons; its
 * drive letter (a blank for none); its two texts. */
static uint32_t icon_written(uint8_t *image, uint32_t desk, uint32_t cursor, uint32_t anode)
{
    uint16_t letter = bus_word(image, anode + ANODE_LETTER);

    cursor = put_byte(image, cursor, INF_LINE_START);
    cursor = type_letter_written(image, cursor, anode);
    cursor = put_byte(image, cursor, INF_FIELD_SEPARATOR);
    if (bus_word(image, anode + ANODE_FLAGS) & ANODE_ON_THE_DESKTOP) {
        cursor = aes_save_2(image, cursor, over(desk_word_at(image, anode + ANODE_XSPOT), desk_word_at(image, desk + DESK_GRID_W)));
        cursor = aes_save_2(image, cursor, over((int16_t)(desk_word_at(image, anode + ANODE_YSPOT) - desk_word_at(image, desk + DESK_AREA_Y)),
                                                desk_word_at(image, desk + DESK_GRID_H)));
    }
    cursor = aes_save_2(image, cursor, desk_word_at(image, anode + ANODE_AICON));
    cursor = aes_save_2(image, cursor, desk_word_at(image, anode + ANODE_DICON));
    cursor = put_byte(image, cursor, letter ? (uint8_t)letter : INF_FIELD_SEPARATOR);
    cursor = put_byte(image, cursor, INF_FIELD_SEPARATOR);
    cursor = aes_save_str(image, cursor, bus_long(image, anode + ANODE_PAPPL));
    cursor = aes_save_str(image, cursor, bus_long(image, anode + ANODE_PDATA));
    return line_ended(image, cursor);
}

/* The INF to disk: DESKTOP.INF created on the boot drive's root (app_path_save), the INF written less its NUL, closed,
 * the path given back; the top window's directory read again (fun_rebld). Where GEMDOS refused the create, its alert
 * (d_errmsg) and the path given back. */
static void inf_to_disk(uint8_t *image, uint32_t desk)
{
    uint32_t afile = desk + DESK_G_AFILE, top;
    int16_t handle;

    set_bus_word(image, desk + DESK_G_AFSIZE, (uint16_t)(bus_word(image, desk + DESK_G_AFSIZE) - 1));
    (void)aes_app_path_save(image);
    handle = aes_app_getfh(image, 0, AES_INF_NAME_WRITE, 0);
    if (!handle) {
        (void)aes_desk_d_errmsg(image);
        (void)aes_app_path_restore(image);
        return;
    }
    set_bus_word(image, desk + DESK_G_AFSIZE,
                 (uint16_t)aes_dos_write(image, handle, (int16_t)bus_word(image, desk + DESK_G_AFSIZE), afile));
    (void)aes_dos_close(image, AES_APP_SAVE_CLOSE_RETURN, handle);
    (void)aes_app_path_restore(image);
    top = aes_win_ontop(image);
    if (top)
        aes_desk_fun_rebld(image, top);
}

/* $fdbb34 — app_save: THE DESK'S INF WRITTEN into g_afile past its first INF_KEPT_BYTES (those cleared on — the
 * shell's own lines put back there from its buffer): #E, the four #W, every ANODE in the list's order (turned round
 * for it, and back after) while less than INF_ICON_LINES_END is written, the end mark and a NUL; its length; the
 * shell's buffer given it (shel_put); and to disk where `to_disk` asks (`inf_to_disk`). */
void aes_app_save(uint8_t *image, int16_t to_disk)
{
    uint32_t desk = desk_globals(image), afile = desk + DESK_G_AFILE, cursor = afile + INF_KEPT_BYTES, anode;

    aes_bfill(image, INF_WRITTEN_BYTES, 0, cursor);
    cursor = environment_written(image, desk, cursor);
    cursor = windows_written(image, desk, cursor);
    aes_app_revit(image);
    for (anode = bus_long(image, desk + DESK_ANODES_IN_USE); anode != ANODE_NONE; anode = bus_long(image, anode + ANODE_NEXT)) {
        if ((int32_t)(cursor - afile) >= INF_ICON_LINES_END)
            break;
        cursor = icon_written(image, desk, cursor, anode);
    }
    cursor = put_byte(image, cursor, INF_FILE_END);
    cursor = put_byte(image, cursor, STRING_NUL);
    aes_app_revit(image);
    set_bus_word(image, desk + DESK_G_AFSIZE, (uint16_t)(cursor - afile));
    (void)aes_desk_shel_get(image, afile, INF_KEPT_BYTES);
    (void)aes_desk_shel_put(image, afile, INF_BUFFER_BYTES);
    if (to_disk)
        inf_to_disk(image, desk);
}
