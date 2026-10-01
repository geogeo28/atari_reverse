/* resource.c — the RESOURCE layer: rsrc_gaddr's address switch (get_addr), the relocation a load runs over a
 * resource file (fix_*), and the character-cell fix-up every resource coordinate takes (rs_obfix).
 *
 * A resource file is a header of section OFFSETS (`aes/objects.h`, RSH_*) followed by its sections; a load turns
 * every offset the file holds into an ADDRESS by adding the header's, and every object's four coordinates from
 * character cells into pixels. Every routine reaches the resource through two globals in RAM, AES_RS_GLOBAL (the
 * caller's global[]) and AES_RS_HDR (the header), as the ROM does: a C core re-reads them where the ROM does,
 * because a store the relocation makes may land on one. A Line-F call in the ROM is a plain call here (`aes/aes.h`,
 * "LINE-F"). Every pointer the ROM forms is put on the 24-bit bus where it is dereferenced (`m68k_idioms.h`, `bus_word`).
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "aes/objects.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/strings.h"

/* get_sub's SECTION is the index of the header word holding its offset — the byte offset halved. */
#define SECTION(field)        ((field) / M68K_WORD_BYTES)

static inline uint32_t resource_header(const uint8_t *image)
{
    return be32(image + AES_RS_HDR);
}

/* ================================================================================================
 * The character-cell fix-up.
 * ============================================================================================= */

/* A coordinate's two bytes: the LOW byte a count of character cells, the HIGH byte a pixel offset added to it. */
#define CELLS_MASK            0x00ff
#define OFFSET_SHIFT          8
/* An x or a width of 80 cells is the SCREEN's width, whatever the cell ($fea648 cmpi.w #80). */
#define FULL_WIDTH_CELLS      80
/* The offset byte is SIGNED above 128 only: `cmpi.w #128; ble` keeps 128 itself positive ($fea678), so the
 * offsets run -127..128 and not -128..127. */
#define OFFSET_POSITIVE_LIMIT 128
#define OFFSET_WRAP           256
#define OBJECT_COORDINATES    4          /* ob_x, ob_y, ob_width, ob_height, the x-like ones even */

/* $fea622 — one coordinate from cells to pixels: its low byte times the cell's width (an x or a width) or height,
 * a full-width 80 the screen's width instead, plus its high byte as a signed pixel offset. Read once, stored once. */
void aes_fix_chpos(uint8_t *image, uint32_t coordinate, int16_t is_x)
{
    uint16_t coordinate_word = bus_word(image, coordinate);
    uint16_t cells = coordinate_word & CELLS_MASK;
    int16_t offset = (int16_t)(coordinate_word >> OFFSET_SHIFT);
    uint16_t pixels;

    if (is_x && cells == FULL_WIDTH_CELLS)
        pixels = be16(image + AES_GL_WIDTH);
    else
        pixels = (uint16_t)m68k_muls_w(cells, be16(image + (is_x ? AES_GL_WCHAR : AES_GL_HCHAR)));
    if (offset > OFFSET_POSITIVE_LIMIT)
        offset -= OFFSET_WRAP;
    set_bus_word(image, coordinate, (uint16_t)(pixels + (uint16_t)offset));
}

/* $fea69c — rsrc_obfix: the four coordinates of `object`, x-like and y-like alternately. The answer is D0 as the
 * toggle's last `moveq #1` left it, which the dispatcher's arm hands back as intout[0]. */
#define OBFIX_ANSWER          1

int16_t aes_rs_obfix(uint8_t *image, uint32_t tree, int16_t object)
{
    uint32_t coordinates = table_entry(tree, object, OB_BYTES) + OB_X;
    int16_t index, is_x = 1;

    for (index = 0; index < OBJECT_COORDINATES; index++) {
        aes_fix_chpos(image, coordinates + (uint32_t)index * M68K_WORD_BYTES, is_x);
        is_x = !is_x;
    }
    return OBFIX_ANSWER;
}

/* ================================================================================================
 * Addresses in the resource.
 * ============================================================================================= */

/* $fea716 — get_sub: element `index` of `size` bytes of the header's section `section` — the header plus the
 * section's UNSIGNED offset word plus the SIGNED product (`muls.w`). */
uint32_t aes_get_sub(uint8_t *image, int16_t index, int16_t section, int16_t size)
{
    uint32_t header = resource_header(image);
    uint16_t offset = bus_word(image, table_entry(header, section, M68K_WORD_BYTES));

    return header + offset + (uint32_t)m68k_muls_w((uint16_t)size, (uint16_t)index);
}

/* A tree's address: the caller's global[] tree table's entry. The byte offset is STORED to AES_RS_INDEX and read
 * back with `movea.w` ($fea762..$fea76a): a word, sign-extended — an index of $2000 or more reads below the table. */
static uint32_t tree_address(uint8_t *image, int16_t index)
{
    uint32_t table;

    wr16(image + AES_RS_INDEX, (uint16_t)(index * M68K_LONG_BYTES));
    table = bus_long(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_PTREE);
    return bus_long(image, table + (uint32_t)(int32_t)(int16_t)be16(image + AES_RS_INDEX));
}

/* A block of a TEDINFO or an ICONBLK the type names a pointer field of: the block's address plus that field's. */
static uint32_t field_of(uint8_t *image, int16_t block_type, int16_t index, uint32_t field)
{
    return aes_get_addr(image, block_type, index) + field;
}

/* $fea742 — get_addr (rsrc_gaddr's switch): the address of element `index` of resource type `type`. The blocks
 * are get_sub's elements; a block's POINTER field its block's address plus the field; a free string or image (R_STRING,
 * R_IMAGEDATA) the pointer its table holds, where R_FRSTR/R_FRIMG are the table entry's own address. A type past
 * R_LAST_TYPE — the word UNSIGNED, so a negative one too — answers RS_NO_ADDRESS. */
uint32_t aes_get_addr(uint8_t *image, int16_t type, int16_t index)
{
    switch ((uint16_t)type) {
    case R_TREE:
        return tree_address(image, index);
    case R_OBJECT:
        return aes_get_sub(image, index, SECTION(RSH_OBJECT), OB_BYTES);
    case R_TEDINFO:
    case R_TEPTEXT:
        return aes_get_sub(image, index, SECTION(RSH_TEDINFO), TE_BYTES);
    case R_ICONBLK:
    case R_IBPMASK:
        return aes_get_sub(image, index, SECTION(RSH_ICONBLK), IB_BYTES);
    case R_BITBLK:
    case R_BIPDATA:
        return aes_get_sub(image, index, SECTION(RSH_BITBLK), BI_BYTES);
    case R_STRING:
        return bus_long(image, aes_get_sub(image, index, SECTION(RSH_FRSTR), M68K_LONG_BYTES));
    case R_IMAGEDATA:
        return bus_long(image, aes_get_sub(image, index, SECTION(RSH_FRIMG), M68K_LONG_BYTES));
    case R_OBSPEC:
        return field_of(image, R_OBJECT, index, OB_SPEC);
    case R_TEPTMPLT:
        return field_of(image, R_TEDINFO, index, TE_PTMPLT);
    case R_TEPVALID:
        return field_of(image, R_TEDINFO, index, TE_PVALID);
    case R_IBPDATA:
        return field_of(image, R_ICONBLK, index, IB_PDATA);
    case R_IBPTEXT:
        return field_of(image, R_ICONBLK, index, IB_PTEXT);
    case R_FRSTR:
        return aes_get_sub(image, index, SECTION(RSH_FRSTR), M68K_LONG_BYTES);
    case R_FRIMG:
        return aes_get_sub(image, index, SECTION(RSH_FRIMG), M68K_LONG_BYTES);
    default:
        return RS_NO_ADDRESS;
    }
}

/* ================================================================================================
 * The relocation.
 * ============================================================================================= */

/* $feaa0a — fix_long: the offset at `pointer` made an address by adding the header's; RS_NO_ADDRESS stays, and
 * answers 0. */
int16_t aes_fix_long(uint8_t *image, uint32_t pointer)
{
    uint32_t offset = bus_long(image, pointer);

    if (offset == RS_NO_ADDRESS)
        return 0;
    set_bus_long(image, pointer, offset + resource_header(image));
    return 1;
}

/* $fea9f8 — fix_ptr: the pointer get_addr names, fixed. */
int16_t aes_fix_ptr(uint8_t *image, int16_t type, int16_t index)
{
    return aes_fix_long(image, aes_get_addr(image, type, index));
}

/* $fea9d4 — fix_nptrs: the pointers of elements `last` down to 0, the last first. */
void aes_fix_nptrs(uint8_t *image, int16_t last, int16_t type)
{
    int16_t index;

    for (index = last; index >= 0; index--)
        (void)aes_fix_ptr(image, type, index);
}

/* $fea86a — fix_trindex: the tree table's address into the caller's global[] (global[5..6]), then every tree
 * pointer in it fixed, the last first. The count is read AFTER that store, and each entry's byte offset is a word
 * ZERO-extended (`swap; clr.w; swap`, $fea8a8). */
void aes_fix_trindex(uint8_t *image)
{
    uint32_t table = aes_get_sub(image, 0, SECTION(RSH_TRINDEX), M68K_LONG_BYTES);
    int16_t tree;

    set_bus_long(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_PTREE, table);
    for (tree = (int16_t)(bus_word(image, resource_header(image) + RSH_NTREE) - 1); tree >= 0; tree--)
        (void)aes_fix_long(image, table + (uint16_t)(tree * M68K_LONG_BYTES));
}

/* $fea8bc — fix_objects: every object, the last first — its coordinates from cells to pixels, then its ob_spec
 * fixed unless its type holds a colour word there. D0 is left as object 0's last step left it: fix_long's answer,
 * or rs_obfix's 1 for a colour type — which only rom_ram passes on, and none of its callers reads. A resource of no
 * objects leaves the CALLER's D0, which a C function cannot see: the port answers 0 there, what rom_ram's wcopy
 * leaves before its one call (no ROM resource is empty). */
int16_t aes_fix_objects(uint8_t *image)
{
    int16_t index, answer = 0;

    for (index = (int16_t)(bus_word(image, resource_header(image) + RSH_NOBS) - 1); index >= 0; index--) {
        uint32_t object = aes_get_addr(image, R_OBJECT, index);
        uint16_t type;

        answer = aes_rs_obfix(image, object, OB_ROOT);
        type = bus_word(image, object + OB_TYPE) & OB_TYPE_MASK;
        if (type != G_BOX && type != G_IBOX && type != G_BOXCHAR)
            answer = aes_fix_long(image, object + OB_SPEC);
    }
    return answer;
}

/* $fea918 — fix_tedinfo: every TEDINFO, the last first — its text and template pointers fixed, and each one fixed
 * given its length (its string's, plus one: the NUL) in te_txtlen / te_tmplen; then its validation pointer. The
 * lengths are counted only AFTER both pointers are fixed, each through the pointer as stored. */
#define TEDINFO_STRINGS       2          /* the text and the template ($fea9ba cmp.w #2)                       */

void aes_fix_tedinfo(uint8_t *image)
{
    int16_t index;

    for (index = (int16_t)(bus_word(image, resource_header(image) + RSH_NTED) - 1); index >= 0; index--) {
        uint32_t tedinfo = aes_get_addr(image, R_TEDINFO, index);
        uint32_t length_at[TEDINFO_STRINGS] = {0, 0}, string_at[TEDINFO_STRINGS];
        int16_t which;

        if (aes_fix_ptr(image, R_TEPTEXT, index)) {
            length_at[0] = tedinfo + TE_TXTLEN;
            string_at[0] = tedinfo + TE_PTEXT;
        }
        if (aes_fix_ptr(image, R_TEPTMPLT, index)) {
            length_at[1] = tedinfo + TE_TMPLEN;
            string_at[1] = tedinfo + TE_PTMPLT;
        }
        for (which = 0; which < TEDINFO_STRINGS; which++)
            if (length_at[which])
                set_bus_word(image, length_at[which], (uint16_t)(aes_lstrlen(image, bus_long(image, string_at[which])) + 1));
        (void)aes_fix_ptr(image, R_TEPVALID, index);
    }
}

/* $feaba4 — do_rsfix: a resource read at `header`, `bytes` long, relocated — the header and length into the
 * caller's global[] (global[7..8], global[9]); the trees, TEDINFOs, ICONBLKs' three pointers, BITBLKs' data, the free
 * strings and images, each count read from the CURRENT header (AES_RS_HDR, which the caller set — not `header`)
 * right before its pass. The OBJECTS are not: rs_fixit fixes those, after. */
void aes_do_rsfix(uint8_t *image, uint32_t header, int16_t bytes)
{
    int16_t last_icon;

    set_bus_long(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_PMEM, header);
    set_bus_word(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_LMEM, (uint16_t)bytes);
    aes_fix_trindex(image);
    aes_fix_tedinfo(image);
    last_icon = (int16_t)(bus_word(image, resource_header(image) + RSH_NIB) - 1);
    aes_fix_nptrs(image, last_icon, R_IBPMASK);
    aes_fix_nptrs(image, last_icon, R_IBPDATA);
    aes_fix_nptrs(image, last_icon, R_IBPTEXT);
    aes_fix_nptrs(image, (int16_t)(bus_word(image, resource_header(image) + RSH_NBB) - 1), R_BIPDATA);
    aes_fix_nptrs(image, (int16_t)(bus_word(image, resource_header(image) + RSH_NSTRING) - 1), R_FRSTR);
    aes_fix_nptrs(image, (int16_t)(bus_word(image, resource_header(image) + RSH_NIMAGES) - 1), R_FRIMG);
}

/* ================================================================================================
 * The globals.
 * ============================================================================================= */

/* $feaa38 — rs_sglobal: `global` the caller's global[], and its header (global[7..8]) the resource's — read back
 * through the global just stored. */
void aes_rs_sglobal(uint8_t *image, uint32_t global)
{
    wr32(image + AES_RS_GLOBAL, global);
    wr32(image + AES_RS_HDR, bus_long(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_PMEM));
}

/* $feaa86 — rsrc_gaddr: get_addr's answer stored through `answer`, and whether the stored longword — read back —
 * is an address. */
int16_t aes_rs_gaddr(uint8_t *image, uint32_t global, int16_t type, int16_t index, uint32_t answer)
{
    uint8_t *slot = image + bus_span(answer, M68K_LONG_BYTES);    /* loaded ONCE, as the ROM holds A5 ($feaa8e)  */

    aes_rs_sglobal(image, global);
    wr32(slot, aes_get_addr(image, type, index));
    return (int16_t)(be32(slot) != RS_NO_ADDRESS);
}

/* $feaab2 — rsrc_saddr: `value` stored at the address get_addr names, unless it names none. */
int16_t aes_rs_saddr(uint8_t *image, uint32_t global, int16_t type, int16_t index, uint32_t value)
{
    uint32_t address;

    aes_rs_sglobal(image, global);
    address = aes_get_addr(image, type, index);
    if (address == RS_NO_ADDRESS)
        return 0;
    set_bus_long(image, address, value);
    return 1;
}

/* $feac4e — rs_fixit: the caller's resource made current, and its objects fixed; D0 as fix_objects left it. */
int16_t aes_rs_fixit(uint8_t *image, uint32_t global)
{
    aes_rs_sglobal(image, global);
    return aes_fix_objects(image);
}

/* $fea6e6 — rs_str: free string `string` of the AES's own resource, copied into AES_RS_STRING, which is the answer.
 * The ROM asks rsrc_gaddr for the string's address into a frame local and copies from the local; the local is the
 * stack's, which nothing compares, so the port takes the address rsrc_gaddr computes — its rs_sglobal and get_addr —
 * without the local. */
uint32_t aes_rs_str(uint8_t *image, int16_t string)
{
    aes_rs_sglobal(image, be32(image + AES_RS_SYSTEM_GLOBAL));
    (void)aes_lstcpy(image, AES_RS_STRING, aes_get_addr(image, R_STRING, string));
    return AES_RS_STRING;
}

/* ================================================================================================
 * The ROM's own resources: rom_ram.
 * ============================================================================================= */

#define FRESH                 1          /* a part's flag before its first request ($fee670 cmpi.w #1)        */
/* The desk's tree 0, the desktop itself, as rom_ram sizes it to the screen on every request after the first: the
 * root and object 1 the screen's width, the root 25 cell rows high, object 1 a cell and two pixels (the menu bar's),
 * object 7 the width and 24 rows ($fee74c..$fee7d2). */
#define DESKTOP_TREE          0
#define DESKTOP_BAR           1
#define DESKTOP_WORK          7
#define DESKTOP_ROWS          25
#define DESKTOP_WORK_ROWS     24
#define DESKTOP_BAR_EXTRA     2
#define DESKTOP_FULL_WIDTH_OBJECTS 2     /* the root and the bar ($fee77e cmpi.w #2)                          */

/* The desk's rsrc_gaddr BINDING ($fde354, through $fe0b6e) ends in `dsptch`, which is a bare `rts` inside the
 * dispatcher — the only machine a case stages (`aes.leaf_machine`). Outside it, dsptch enters disp, which is not
 * reconstructed: both builds halt there rather than one of them switching process. */
static void dispatch_point(const uint8_t *image)
{
    if (!image[AES_INDISP])
        recreate_not_reconstructed("AES dsptch with AES_INDISP clear: disp and the process switch are not reconstructed");
}

/* The desktop sized to the screen: the desk's tree 0 through its binding (rs_sglobal of the desk's global[] and
 * get_addr — `pointer` is not the binding's argument, its own global[] is), then the five words. D0 is the last word
 * stored. */
static int16_t size_the_desktop(uint8_t *image)
{
    uint32_t desktop;
    int16_t width, work_height, object;

    aes_rs_sglobal(image, AES_DESK_APP_GLOBAL);
    desktop = aes_get_addr(image, R_TREE, DESKTOP_TREE);
    dispatch_point(image);
    width = (int16_t)m68k_muls_w(be16(image + AES_GL_NCOLS), be16(image + AES_GL_WCHAR));
    for (object = 0; object < DESKTOP_FULL_WIDTH_OBJECTS; object++)
        set_object_word(image, desktop, object, OB_WIDTH, width);
    set_object_word(image, desktop, OB_ROOT, OB_HEIGHT, (int16_t)m68k_muls_w(be16(image + AES_GL_HCHAR), DESKTOP_ROWS));
    set_object_word(image, desktop, DESKTOP_BAR, OB_HEIGHT, (int16_t)(be16(image + AES_GL_HCHAR) + DESKTOP_BAR_EXTRA));
    set_object_word(image, desktop, DESKTOP_WORK, OB_WIDTH, width);
    work_height = (int16_t)m68k_muls_w(be16(image + AES_GL_HCHAR), DESKTOP_WORK_ROWS);
    set_object_word(image, desktop, DESKTOP_WORK, OB_HEIGHT, work_height);
    return work_height;
}

/* The global[] each resource part keeps, and the flag that says it is not relocated yet. Every part but the desk's
 * and the format dialogs' — the AES's, and a part below 0 — is the AES's here: `blt` below the desk ($fee65e). */
static uint32_t kept_global(int16_t part)
{
    return part == ROM_RSC_DESK ? AES_RSC_DESK_GLOBAL : part == ROM_RSC_FORMAT ? AES_RSC_FORMAT_GLOBAL
                                                                              : AES_RSC_AES_GLOBAL;
}

/* A resource part's FIRST request, the flag cleared: whether this is one. The AES's flag only for part 0 itself. */
static int first_request(uint8_t *image, int16_t part)
{
    uint32_t flag = part == ROM_RSC_AES ? AES_RSC_AES_FRESH : part == ROM_RSC_DESK ? AES_RSC_DESK_FRESH
                  : part == ROM_RSC_FORMAT ? AES_RSC_FORMAT_FRESH : 0;

    if (!flag || be16(image + flag) != FRESH)
        return 0;
    wr16(image + flag, 0);
    return 1;
}

/* A resource part: on its first request made current and relocated IN PLACE — `pointer` the caller's global[] —
 * that global[] then kept, and (the desk's, the format dialogs') the objects fixed; on every request after, the kept
 * global[] handed back into `pointer`, and the desk's desktop sized to the screen. D0 is wcopy's count run down to
 * 0, rs_fixit's, or the desktop's last word. */
static int16_t resource_part(uint8_t *image, int16_t part, uint32_t pointer, uint32_t address, int16_t bytes)
{
    if (first_request(image, part)) {
        wr32(image + AES_RS_GLOBAL, pointer);
        wr32(image + AES_RS_HDR, address);
        aes_do_rsfix(image, address, bytes);
        aes_wcopy(image, kept_global(part), pointer, AES_GLOBAL_WORDS);
        return part == ROM_RSC_AES ? 0 : aes_rs_fixit(image, pointer);
    }
    aes_wcopy(image, pointer, kept_global(part), AES_GLOBAL_WORDS);
    return part == ROM_RSC_DESK ? size_the_desktop(image) : 0;
}

/* A part's entry in AES_RSC_TABLE: `muls.w #6`, a signed word — a part below 0 reads below the table. */
static uint32_t part_entry(int16_t part)
{
    return table_entry(AES_RSC_TABLE, part, ROM_RSC_ENTRY_BYTES);
}

/* $fee5c8 — rom_ram: part `part` of the ROM's resources (`aes/resource.h`, ROM_RSC_*) handed to the caller: the
 * desk's icons (`size` bytes, or all past the first `size`) and the DESKTOP.INF copied to `pointer`, answering how
 * many bytes; a resource relocated or its global[] handed back (`resource_part`). A part past the last reads past
 * the table and answers nothing but D0 as it was, the entry's address. */
int16_t aes_rom_ram(uint8_t *image, int16_t part, uint32_t pointer, int16_t size)
{
    uint32_t entry = part_entry(part);
    uint32_t address = bus_long(image, entry + ROM_RSC_ADDRESS);
    int16_t bytes = (int16_t)bus_word(image, entry + ROM_RSC_BYTES);

    switch (part) {
    case ROM_RSC_DESKTOP_INF:
        aes_lbcopy(image, pointer, address, bytes);
        return bytes;
    case ROM_RSC_DESK_ICONS:
        aes_lbcopy(image, pointer, address, size);
        return size;
    case ROM_RSC_DESK_ICONS_TAIL:
        aes_lbcopy(image, pointer, address + (uint16_t)size, (int16_t)(bytes - size));
        return (int16_t)(bytes - size);
    case ROM_RSC_AES:
    case ROM_RSC_DESK:
    case ROM_RSC_FORMAT:
        return resource_part(image, part, pointer, address, bytes);
    default:
        return part < ROM_RSC_AES ? resource_part(image, part, pointer, address, bytes) : (int16_t)entry;
    }
}

/* $feaa58 — rsrc_free: the caller's resource (global[7..8], read through the global just stored) Mfree'd, and whether
 * GEMDOS took it. rs_hdr is not touched. */
int16_t aes_rs_free(uint8_t *image, uint32_t global)
{
    wr32(image + AES_RS_GLOBAL, global);
    (void)aes_dos_free(image, AES_RS_FREE_MFREE_RETURN, bus_long(image, be32(image + AES_RS_GLOBAL) + AES_GLOBAL_PMEM));
    return (int16_t)!be16(image + AES_DOS_ERR);
}

/* ================================================================================================
 * Loading a resource file: rs_readit, rs_load.
 * ============================================================================================= */

#define RS_OPEN_READ          0          /* Fopen's mode ($feab16 clr.w (sp))                                  */
#define RS_SEEK_FROM_START    0          /* Fseek's mode and offset ($feab60 clr.l (sp); clr.w -(sp))          */
#define RS_SEEK_TO_START      0

/* The file, its header read: the whole of it (the header's rsh_rssize, a word) into a block of its own, AES_RS_HDR,
 * from the start — the seek's answer unchecked — and relocated in place. Each step only if the one before left
 * AES_DOS_ERR clear; AES_RS_HDR is re-read for the read and the relocation, as the ROM does. */
static void read_the_whole_file(uint8_t *image, int16_t handle)
{
    uint16_t bytes = be16(image + AES_RS_HEADER_COPY + RSH_RSSIZE);

    wr32(image + AES_RS_HDR, aes_dos_alloc(image, bytes));
    if (aes_dos_failed(image))
        return;
    (void)aes_dos_lseek(image, handle, RS_SEEK_FROM_START, RS_SEEK_TO_START);
    (void)aes_dos_read(image, handle, (int16_t)bytes, be32(image + AES_RS_HDR));
    if (aes_dos_failed(image))
        return;
    aes_do_rsfix(image, be32(image + AES_RS_HDR), (int16_t)bytes);
}

/* $feaae2 — rs_readit: the file `name` looked for by sh_find through the shell's buffer (AES_SHELL_BUFFER, re-read at
 * each use), and, found, `global` made the resource's caller, the file opened, its header read into
 * AES_RS_HEADER_COPY and the whole file read and relocated; then CLOSED whatever happened — on a failed open, handle
 * 0, which is what dos_open answers then. Answers whether AES_DOS_ERR came out clear; not found, 0 and nothing
 * opened. */
int16_t aes_rs_readit(uint8_t *image, uint32_t global, uint32_t name)
{
    int16_t handle, loaded;

    (void)aes_lstcpy(image, be32(image + AES_SHELL_BUFFER), name);
    if (!aes_sh_find(image, be32(image + AES_SHELL_BUFFER), SH_FIND_NO_ROUTINE))
        return 0;
    wr32(image + AES_RS_GLOBAL, global);
    handle = (int16_t)aes_dos_open(image, be32(image + AES_SHELL_BUFFER), RS_OPEN_READ);
    if (!aes_dos_failed(image))
        (void)aes_dos_read(image, handle, RSH_BYTES, AES_RS_HEADER_COPY);
    if (!aes_dos_failed(image))
        read_the_whole_file(image, handle);
    loaded = !aes_dos_failed(image);
    (void)aes_dos_close(image, AES_RS_READIT_CLOSE_RETURN, handle);
    return loaded;
}

/* $feac5c — rs_load (rsrc_load): rs_readit, and, if it read the file, the objects fixed too (rs_fixit). Answers
 * rs_readit's word. */
int16_t aes_rs_load(uint8_t *image, uint32_t global, uint32_t name)
{
    int16_t loaded = aes_rs_readit(image, global, name);

    if (loaded)
        (void)aes_rs_fixit(image, global);
    return loaded;
}

/* $fee4de — rom_rsc_init, at start-up: the ROM's whole resource bundle copied into a block of its own — NOT
 * checked: a Malloc that fails copies it to address 0 — and the six parts' table (`aes/resource.h`, ROM_RSC_*) formed
 * from the bundle's five offsets: the AES's resource from past them, its length the first offset less the table's
 * WORD count (five bytes long — the ROM subtracts words from bytes); parts 1..3 from each offset, even, to the next;
 * part 4 part 2 again; part 5 from the fourth offset to the fifth. Then the three resources' flags: fresh. */
#define BUNDLE_OFFSET_COUNT   5          /* the bundle's table of offsets  ($fee50c subq.w #5; the parts' ends)   */
#define LAST_OFFSET           (BUNDLE_OFFSET_COUNT - 1)
#define EVEN_MASK             0xfffeu    /* an offset made even: `lsr.w #1; lsl.w #1` ($fee526)                  */

static uint16_t bundle_offset(const uint8_t *image, uint32_t bundle, int16_t index)
{
    return bus_word(image, bundle + (uint32_t)index * M68K_WORD_BYTES);
}

/* Part `part` from bundle offset `from` (made even) to offset `to` — the address STORED before the length's offsets
 * are read, as the ROM orders it: a block Malloc'd over the table would show it. */
static void record_part(uint8_t *image, uint32_t bundle, int16_t part, int16_t from, int16_t to)
{
    wr32(image + part_entry(part) + ROM_RSC_ADDRESS, bundle + (bundle_offset(image, bundle, from) & EVEN_MASK));
    wr16(image + part_entry(part) + ROM_RSC_BYTES,
         (uint16_t)(bundle_offset(image, bundle, to) - bundle_offset(image, bundle, from)));
}

void aes_rom_rsc_init(uint8_t *image)
{
    uint32_t bundle = aes_dos_alloc(image, AES_RSC_BUNDLE_BYTES);
    int16_t part;

    aes_lbcopy(image, bundle, AES_RSC_BUNDLE, AES_RSC_BUNDLE_BYTES);
    wr32(image + part_entry(ROM_RSC_AES) + ROM_RSC_ADDRESS, bundle + BUNDLE_OFFSET_COUNT * M68K_WORD_BYTES);
    wr16(image + part_entry(ROM_RSC_AES) + ROM_RSC_BYTES,
         (uint16_t)(bundle_offset(image, bundle, 0) - BUNDLE_OFFSET_COUNT));
    for (part = ROM_RSC_DESK; part <= ROM_RSC_DESKTOP_INF; part++)
        record_part(image, bundle, part, (int16_t)(part - 1), part);
    wr32(image + part_entry(ROM_RSC_DESK_ICONS_TAIL) + ROM_RSC_ADDRESS,
         be32(image + part_entry(ROM_RSC_DESK_ICONS) + ROM_RSC_ADDRESS));
    wr16(image + part_entry(ROM_RSC_DESK_ICONS_TAIL) + ROM_RSC_BYTES,
         be16(image + part_entry(ROM_RSC_DESK_ICONS) + ROM_RSC_BYTES));
    record_part(image, bundle, ROM_RSC_FORMAT, LAST_OFFSET - 1, LAST_OFFSET);
    wr16(image + AES_RSC_DESK_FRESH, FRESH);
    wr16(image + AES_RSC_FORMAT_FRESH, FRESH);
    wr16(image + AES_RSC_AES_FRESH, FRESH);
}
