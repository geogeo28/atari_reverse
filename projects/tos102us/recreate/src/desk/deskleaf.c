/* deskleaf.c — THE DESK'S LEAVES FILED IN AES MODULES (`desk/deskleaf.h`): thirteen entries of the DOS glue
 * (`$fe3a7c..$fe3c25`), gemgraf's gsx_pline, app_alloc and app_free, gsx_hardcopy and the BIOS door trp13 — each
 * ported over the ROM's own order. (THE DOOR SHIPS AS ITS SIXTEEN ROM BYTES, `src/desk/trp13.S`: its C here is the
 * twin Tier 1 proves, as `src/aes/trp14.c` is trp14's.)
 *
 * THE GLUE'S OWN STEPS ARE SPELT HERE A SECOND TIME — FOUR STATICS (`dos_verdict`, `dos_answered`,
 * `park_both_returns`, `dos_through_with_a_long`), and dos_rawcio is `dos_through_with_a_word` again:
 * `src/aes/gemdosif.c` keeps them `static`, and that file is band 5's — its object is held byte-identical while these
 * entries are linked and not bound. One home for both is owed when the entries are bound.
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsxif.h"
#include "bios/bcon.h"
#include "desk/deskleaf.h"
#include "gemdos/fs.h"
#include "gemdos/gemdos.h"
#include "vdi/escape.h"
#include "vdi/vdi.h"

/* ---- `__DOS` ($fe3c3e) as an entry of this file reaches it ------------------------------------------------------------ */

/* Its tail ($fe3c46): the answer's word in AES_DOS_AX, its LONG's sign in AES_DOS_ERR — which is also what it leaves
 * in D1, and dos_mkdir answers from. */
static int16_t dos_verdict(uint8_t *image, uint32_t answer)
{
    int16_t failed = (int32_t)answer < 0;

    wr16(image + AES_DOS_AX, (uint16_t)answer);
    wr16(image + AES_DOS_ERR, (uint16_t)failed);
    return failed;
}

/* ...and what every entry but dos_mkdir and dos_label answers once the trap is back: the verdict taken, the trap's
 * whole D0. */
static inline uint32_t dos_answered(uint8_t *image, uint32_t answer)
{
    (void)dos_verdict(image, answer);
    return answer;
}

/* An entry that reaches `__DOS` by its own `bsr`: the site inside the glue that `bsr` returns to, parked. */
static inline void park_the_glue_s_return(uint8_t *image, uint32_t glue_site)
{
    wr32(image + AES_TRAP1_RETURN, glue_site);
}

/* ...and one that first pops ITS CALLER's return address into AES_DOS_RETURN ($fe3c28, $fe3ba0): both parked, before
 * the trap. */
static inline void park_both_returns(uint8_t *image, uint32_t return_site, uint32_t glue_site)
{
    wr32(image + AES_DOS_RETURN, return_site);
    park_the_glue_s_return(image, glue_site);
}

/* THE ONE `trap #1` SHAPE `gemdos/gemdos.h` DOES NOT HAVE: the function over a longword and two words — Fattrib's
 * (the name, whether to set, the attributes) and Fdatime's (the stamp's address, the handle, whether to set). The two
 * builds take it two ways, as that header's shapes do. */
#define LONG_WORD_WORD_FRAME_BYTES (GEMDOS_ARGUMENT_WORD + GEMDOS_FRAME_LONG + 2 * GEMDOS_FRAME_WORD)

static inline uint32_t trap_word_long_word_word(uint8_t *image, uint16_t function, uint32_t first, uint16_t second,
                                                uint16_t third)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[LONG_WORD_WORD_FRAME_BYTES];

    wr16(frame, function);
    wr32(frame + GEMDOS_ARGUMENT_WORD, first);
    wr16(frame + GEMDOS_ARGUMENT_WORD + GEMDOS_FRAME_LONG, second);
    wr16(frame + GEMDOS_ARGUMENT_WORD + GEMDOS_FRAME_LONG + GEMDOS_FRAME_WORD, third);
    return gemdos_host_trap(image, frame, sizeof frame);
#else
    /* Each operand pinned to a register the trap restores (`gemdos/gemdos.h` says why). */
    register uint32_t result __asm__("d0") = function;
    register uint32_t longword __asm__("d1") = first;
    register uint16_t word __asm__("a0") = second;
    register uint16_t last __asm__("a1") = third;

    (void)image;
    __asm__ volatile ("move.w %3,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.w %0,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "lea %c4(%%sp),%%sp"
                      : "+d"(result)
                      : "d"(longword), "a"(word), "a"(last), "i"(LONG_WORD_WORD_FRAME_BYTES)
                      : "memory", "cc");
    return result;
#endif
}

/* Fattrib's frame FOR dos_chmod: on target the two words are ONE longword in a data register and the name in an
 * address register — three operands, so the image stays where GCC has it and no register is saved round the trap
 * (the general shape above takes four: measured 1.129 at dos_chmod's arrival against this one's figure,
 * `test/test_desk_leaves.py`'s probe note). The frame GEMDOS reads is the same ten bytes. */
static inline uint32_t trap_fattrib(uint8_t *image, uint32_t name, int16_t set, int16_t attributes)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return trap_word_long_word_word(image, GEMDOS_FATTRIB_FN, name, (uint16_t)set, (uint16_t)attributes);
#else
    register uint32_t result __asm__("d0") = GEMDOS_FATTRIB_FN;
    register uint32_t both_words __asm__("d1") = words_long(set, attributes);
    register uint32_t file_name __asm__("a0") = name;

    (void)image;
    __asm__ volatile ("move.l %1,-(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      "move.w %0,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "lea %c3(%%sp),%%sp"
                      : "+d"(result)
                      : "d"(both_words), "a"(file_name), "i"(LONG_WORD_WORD_FRAME_BYTES)
                      : "memory", "cc");
    return result;
#endif
}

/* Frename's frame AS THE ROM LAYS IT: the function and its reserved word ONE longword over the caller's two names
 * (`$fe3ba6 move.l #$00560000,-(sp)`) — three operands on target, for trap_fattrib's reason. */
#define FRENAME_FRAME_BYTES (3 * GEMDOS_FRAME_LONG)

static inline uint32_t trap_frename(uint8_t *image, uint32_t old_name, uint32_t new_name)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return gemdos_trap_word_word_long_long(image, GEMDOS_FRENAME_FN, FRENAME_RESERVED, old_name, new_name);
#else
    register uint32_t result __asm__("d0") = (uint32_t)GEMDOS_FRENAME_FN << M68K_WORD_BITS | FRENAME_RESERVED;
    register uint32_t first __asm__("d1") = old_name;
    register uint32_t second __asm__("a0") = new_name;

    (void)image;
    __asm__ volatile ("move.l %2,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.l %0,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "lea %c3(%%sp),%%sp"
                      : "+d"(result)
                      : "d"(first), "a"(second), "i"(FRENAME_FRAME_BYTES)
                      : "memory", "cc");
    return result;
#endif
}

/* ---- the entries that reach `__DOS` by their own `bsr` ----------------------------------------------------------------- */

/* $fe3a7c — dos_write: Fwrite(handle, count, buffer). `moveq #$40,d1` and then dos_read's own instructions from its
 * second on — the count a WORD zero-extended to the call's longword, and the site parked dos_read's own. */
uint32_t aes_dos_write(uint8_t *image, int16_t handle, int16_t count, uint32_t buffer)
{
    park_the_glue_s_return(image, AES_DOS_READ_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_word_long_long(image, GEMDOS_FWRITE_FN, (uint16_t)handle, (uint16_t)count, buffer));
}

/* $fe3ab0 — dos_gdir: Dgetpath(path, drive) — its caller pushes them the other way round. */
uint32_t aes_dos_gdir(uint8_t *image, int16_t drive, uint32_t path)
{
    park_the_glue_s_return(image, AES_DOS_GDIR_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_long_word(image, GEMDOS_DGETPATH_FN, path, (uint16_t)drive));
}

/* $fe3ac4 — dos_mkdir: Dcreate(path); EACCDN (a word compare) is AES_DOS_AX 5. It answers `__DOS`'s verdict turned
 * round — a WORD: the high word of the ROM's D0 is still Dcreate's. */
int16_t aes_dos_mkdir(uint8_t *image, uint32_t path)
{
    uint32_t answer;
    int16_t failed;

    park_the_glue_s_return(image, AES_DOS_MKDIR_TRAP_RETURN);
    answer = gemdos_trap_word_long(image, GEMDOS_DCREATE_FN, path);
    failed = dos_verdict(image, answer);
    if ((uint16_t)answer == (uint16_t)GEMDOS_EACCDN)
        wr16(image + AES_DOS_AX, DOS_AX_ACCESS_DENIED);
    return failed ? DOS_MKDIR_FAILED : DOS_MKDIR_DONE;
}

/* $fe3ae8 — dos_setdt: Fdatime(&stamp, handle, 1) — the file's time and date SET from the caller's own two words,
 * which the ROM hands GEMDOS WHERE THEY LIE (`pea 10(sp)`): so does this — the argument's own slot on target, a host
 * slot holding its value off it. (GEMDOS turns the two words to the disk's byte order in place and leaves them so.) */
uint32_t aes_dos_setdt(uint8_t *image, int16_t handle, uint32_t stamp)
{
    uint32_t stamp_at = host_slot_claim(AES_DOS_SETDT_STAMP, &stamp);
    uint32_t answer;

    host_slot_store_long(image, stamp_at, &stamp);
    park_the_glue_s_return(image, AES_DOS_SETDT_TRAP_RETURN);
    answer = dos_answered(image, trap_word_long_word_word(image, GEMDOS_FDATIME_FN, stamp_at, (uint16_t)handle, FDATIME_SET));
    host_slot_release(AES_DOS_SETDT_STAMP);
    return answer;
}

_Static_assert(DOS_STAMP_BYTES == HOST_SLOT_AES_DOS_SETDT_STAMP_BYTES, "dos_setdt's stamp and its host slot");
_Static_assert(LABEL_FRAME_BYTES == HOST_SLOT_AES_DOS_LABEL_FRAME_BYTES, "dos_label's frame and its host slot");
_Static_assert(DFREE_BYTES == HOST_SLOT_AES_DOS_SPACE_DFREE_BYTES, "dos_space's Dfree answers and their host slot");
_Static_assert(LABEL_FRAME_BYTES == LABEL_PATH_BYTES + LABEL_DTA_BYTES, "dos_label's frame is its path and its DTA");
_Static_assert(TRP13_FRAME_BYTES == GEMDOS_ARGUMENT_WORD + TRP13_ARGUMENT_WORDS * GEMDOS_FRAME_WORD,
               "the door's frame as its trap drops it (`lea 14(sp),sp`): the function word and its six");

/* What dos_label's search path ends on, after the drive's letter ($fe3b64): every name of the root. */
static const char label_pattern[] = ":\\*.*";

/* A NUL-ended text copied byte by byte, its NUL with it (`move.b (a1)+,(a0)+ / bne`), from the image to wherever its
 * caller's pointer leads. */
static void copy_text_out(uint8_t *image, uint32_t to, uint32_t from)
{
    uint8_t character;

    do {
        character = image[from++];
        set_bus_byte(image, to++, character);
    } while (character);
}

/* $fe3b02 — dos_label: drive `drive`'s volume label (1 is A:). The DTA is set to ITS OWN FRAME — by `trap #1` itself,
 * nothing parked, and never set back: the process's DTA is left naming a dead frame — then Fsfirst("X:\*.*", the
 * volume-label attribute) through `__DOS`. Found (the answer's WORD 0): the DTA's name copied out through `name_out`
 * and 1. Else 0, with AES_DOS_ERR and AES_DOS_AX both 1 whatever GEMDOS answered. */
uint32_t aes_dos_label(uint8_t *image, int16_t drive, uint32_t name_out)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(LABEL_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DOS_LABEL_FRAME, frame_local);
    uint32_t path = frame + LABEL_PATH, dta = frame + LABEL_DTA, answer;
    const char *from = label_pattern;
    uint8_t *to = image + path + 1;
    char character;

    (void)gemdos_trap_word_long(image, GEMDOS_FSETDTA_FN, dta);
    image[path] = (uint8_t)((uint8_t)drive + DRIVE_LETTER_BASE);
    /* The pattern copied TO ITS NUL, as the ROM's `move.b (a1)+,(a0)+ / bne` does: a counted loop is the same bytes
     * and 60 cycles more (GCC ends it on a `cmpa.l #`). */
    do {
        character = *from++;
        *to++ = (uint8_t)character;
    } while (character);
    park_the_glue_s_return(image, AES_DOS_LABEL_TRAP_RETURN);
    answer = gemdos_trap_word_long_word(image, GEMDOS_FSFIRST_FN, path, FA_VOLUME_LABEL);
    (void)dos_verdict(image, answer);
    if (!(uint16_t)answer) {
        copy_text_out(image, name_out, dta + DTA_NAME);
        host_slot_release(AES_DOS_LABEL_FRAME);
        return DOS_LABEL_FOUND;
    }
    wr16(image + AES_DOS_ERR, DOS_LABEL_FAILED);
    wr16(image + AES_DOS_AX, DOS_LABEL_FAILED);
    host_slot_release(AES_DOS_LABEL_FRAME);
    return DOS_LABEL_NONE;
}

/* The low word of one of Dfree's four longwords: all dos_space reads of it. */
static inline uint16_t dfree_low_word(const uint8_t *image, uint32_t answers, uint32_t field)
{
    return be16(image + answers + field + LOW_WORD_OF_A_LONG);
}

/* $fe3b6a — dos_space: Dfree(drive) into its own frame — by `trap #1` itself: nothing parked, NO VERDICT, and Dfree's
 * answer never read — then the drive's size and its free space in bytes through the two pointers. THE ROM'S
 * ARITHMETIC IS 16-BIT (`mulu.w`): the LOW WORD of sectors-a-cluster times the low word of the sector's bytes, and
 * the LOW WORD OF THAT PRODUCT times the low word of each cluster count — reproduced. Always 1. */
uint32_t aes_dos_space(uint8_t *image, int16_t drive, uint32_t total_out, uint32_t avail_out)
{
    uint16_t answers_local[FRAME_LOCAL_WORDS(DFREE_BYTES)];
    uint32_t answers = host_slot_claim(AES_DOS_SPACE_DFREE, answers_local);
    uint16_t cluster_bytes;

    (void)gemdos_trap_word_long_word(image, GEMDOS_DFREE_FN, answers, (uint16_t)drive);
    cluster_bytes = (uint16_t)((uint32_t)dfree_low_word(image, answers, DFREE_CLUSTER_SECTORS)
                               * dfree_low_word(image, answers, DFREE_SECTOR_BYTES));
    set_bus_long(image, total_out, (uint32_t)cluster_bytes * dfree_low_word(image, answers, DFREE_TOTAL_CLUSTERS));
    set_bus_long(image, avail_out, (uint32_t)cluster_bytes * dfree_low_word(image, answers, DFREE_FREE_CLUSTERS));
    host_slot_release(AES_DOS_SPACE_DFREE);
    return DOS_SPACE_DONE;
}

/* $fe3be8 — dos_avail: Malloc(-1), the largest free block — by `trap #1` itself: nothing parked, no verdict. */
uint32_t aes_dos_avail(uint8_t *image)
{
    return gemdos_trap_word_long(image, GEMDOS_MALLOC_FN, MALLOC_LARGEST);
}

/* ---- the entries that park THEIR CALLER's return too ------------------------------------------------------------------- */

/* $fe3ba0 — dos_rename: Frename(0, old, new). Its caller's return popped into AES_DOS_RETURN, the function and the
 * reserved word pushed as ONE longword over the caller's two, then `__DOS` by its own `bsr`. */
uint32_t aes_dos_rename(uint8_t *image, uint32_t return_site, uint32_t old_name, uint32_t new_name)
{
    park_both_returns(image, return_site, AES_DOS_RENAME_TRAP_RETURN);
    return dos_answered(image, trap_frename(image, old_name, new_name));
}

/* $fe3bfa — dos_rawcio: Crawio through $fe3c28, over the character WORD its caller pushed ($ff asks for a key). */
uint32_t aes_dos_rawcio(uint8_t *image, uint32_t return_site, int16_t character)
{
    park_both_returns(image, return_site, AES_DOS_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_word(image, GEMDOS_CRAWIO_FN, (uint16_t)character));
}

/* $fe3c16 — dos_chmod: Fattrib through $fe3c28, over the name and the two words its caller pushed. */
uint32_t aes_dos_chmod(uint8_t *image, uint32_t return_site, uint32_t name, int16_t set, int16_t attributes)
{
    park_both_returns(image, return_site, AES_DOS_TRAP_RETURN);
    return dos_answered(image, trap_fattrib(image, name, set, attributes));
}

/* A call through $fe3c28 over the ONE LONGWORD its caller pushed: a name, a path. */
static inline uint32_t dos_through_with_a_long(uint8_t *image, uint32_t return_site, uint16_t function, uint32_t argument)
{
    park_both_returns(image, return_site, AES_DOS_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_long(image, function, argument));
}

/* $fe3c1a — dos_delete: Fdelete through $fe3c28. */
uint32_t aes_dos_delete(uint8_t *image, uint32_t return_site, uint32_t name)
{
    return dos_through_with_a_long(image, return_site, GEMDOS_FDELETE_FN, name);
}

/* $fe3c1e — dos_rmdir: Ddelete through $fe3c28. */
uint32_t aes_dos_rmdir(uint8_t *image, uint32_t return_site, uint32_t path)
{
    return dos_through_with_a_long(image, return_site, GEMDOS_DDELETE_FN, path);
}

/* $fe3c22 — dos_create: Fcreate through $fe3c28, over the name and the attribute WORD its caller pushed. */
uint32_t aes_dos_create(uint8_t *image, uint32_t return_site, uint32_t name, int16_t attributes)
{
    park_both_returns(image, return_site, AES_DOS_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_long_word(image, GEMDOS_FCREATE_FN, name, (uint16_t)attributes));
}

/* ---- gemgraf's three ---------------------------------------------------------------------------------------------------- */

/* $fda8a8 — gsx_pline: `count` points copied into ptsin — each a longword, then its x and its y moved by (x, y), WORD
 * sums — and gsx_xline over them. `count` is a signed word (none for 0 or less); nothing bounds it by ptsin's size.
 * It answers what gsx_xline leaves. */
uint16_t aes_gsx_pline(uint8_t *image, int16_t x, int16_t y, int16_t count, uint32_t points)
{
    uint32_t ptsin = AES_GSX_PTSIN;
    int16_t left;

    for (left = count; left > 0; left--) {
        wr32(image + ptsin, bus_long(image, points));
        add_ram_word(image, ptsin, (uint16_t)x);
        add_ram_word(image, ptsin + VDI_WORD_BYTES, (uint16_t)y);
        points += VDI_POINT_BYTES;
        ptsin += VDI_POINT_BYTES;
    }
    return aes_gsx_xline(image, count, AES_GSX_PTSIN);
}

/* $fdae96 — app_alloc: the first ANODE of the desk's free list, taken off it and linked into the list in use — at its
 * head where `to_head` is set or the list is empty, else behind its last node (the node's own link cleared). The
 * node; 0, and nothing touched, where none is free. */
uint32_t aes_app_alloc(uint8_t *image, int16_t to_head)
{
    uint32_t desk = be32(image + AES_DESK_GLOBALS);
    uint32_t node = bus_long(image, desk + DESK_ANODES_FREE);
    uint32_t last;

    if (node == ANODE_NONE)
        return ANODE_NONE;
    set_bus_long(image, desk + DESK_ANODES_FREE, bus_long(image, node + ANODE_NEXT));
    if (to_head || bus_long(image, desk + DESK_ANODES_IN_USE) == ANODE_NONE) {
        set_bus_long(image, node + ANODE_NEXT, bus_long(image, desk + DESK_ANODES_IN_USE));
        set_bus_long(image, desk + DESK_ANODES_IN_USE, node);
        return node;
    }
    last = bus_long(image, desk + DESK_ANODES_IN_USE);
    while (bus_long(image, last + ANODE_NEXT) != ANODE_NONE)
        last = bus_long(image, last + ANODE_NEXT);
    set_bus_long(image, last + ANODE_NEXT, node);
    set_bus_long(image, node + ANODE_NEXT, ANODE_NONE);
    return node;
}

/* $fdaee2 — app_free: `node` unlinked from the list in use — the head moved on where it IS the head, else the node
 * before it found by its link (a node that is on no list unlinks nothing) — and pushed on the free list. */
void aes_app_free(uint8_t *image, uint32_t node)
{
    uint32_t desk = be32(image + AES_DESK_GLOBALS);
    uint32_t before;

    if (node == bus_long(image, desk + DESK_ANODES_IN_USE)) {
        set_bus_long(image, desk + DESK_ANODES_IN_USE, bus_long(image, node + ANODE_NEXT));
    } else {
        before = bus_long(image, desk + DESK_ANODES_IN_USE);
        while (before != ANODE_NONE && bus_long(image, before + ANODE_NEXT) != node)
            before = bus_long(image, before + ANODE_NEXT);
        if (before != ANODE_NONE)
            set_bus_long(image, before + ANODE_NEXT, bus_long(image, node + ANODE_NEXT));
    }
    set_bus_long(image, node + ANODE_NEXT, bus_long(image, desk + DESK_ANODES_FREE));
    set_bus_long(image, desk + DESK_ANODES_FREE, node);
}

/* ---- the hardcopy leaf and the BIOS door ---------------------------------------------------------------------------------- */

/* $fe8862 — gsx_hardcopy: `moveq #17,d0` into gsx_escapes' register entry — the VDI's v_hardcopy, which is XBIOS
 * Scrdmp: the screen dumped to the printer by whatever routine `scr_dump` names. */
void aes_gsx_hardcopy(uint8_t *image)
{
    aes_gsx_escapes(image, VDI_ESCAPE_V_HARDCOPY);
}

/* $fee478 — trp13: THE AES's BIOS DOOR — THE C TWIN; WHAT A TARGET BUILD SHIPS IS `trp13.S`, the ROM's sixteen
 * bytes (trp14's kind). In the ROM four instructions — its own return address popped into AES_BIOS_RETURN,
 * `trap #13` over WHATEVER FRAME ITS CALLER PUSHED, the return pushed back, `rts`. A C function is handed arguments,
 * not a frame: this one takes the function and the six words the widest caller pushes (Rwabs's) and lays them again
 * for the trap, which reads as many as its function takes — 214 cycles more a call than the ROM's four instructions
 * (1.355 at Drvmap's arrival, 1.253 at the forced media change's, 1.053 at Bconout's: the measurement the `.S`
 * answers). Its target arm is kept and run on both blobs (`test/test_desk_leaves.py`), as trp14's twin's is.
 *
 * OFF TARGET the trap is the BIOS routine the function names, for the four the desk asks: Drvmap and Bconout the
 * routines' own C cores, Getbpb and Rwabs the disk vectors' door a case binds (`gemdos/fs.h`). Any other halts by name. */
uint32_t aes_trp13(uint8_t *image, uint32_t return_site, int16_t function, int16_t first, int16_t second,
                   int16_t third, int16_t fourth, int16_t fifth, int16_t sixth)
{
    wr32(image + AES_BIOS_RETURN, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    switch (function) {
    case BIOS_DRVMAP_FN:
        return bios_drvmap(image);
    case BIOS_BCONOUT_FN:
        return bios_bconout(image, BIOS_BCONOUT, (uint16_t)first, (uint16_t)second);
    case BIOS_GETBPB_FN:
        return (uint32_t)recreate_call_disk_vector(image, BIOS_GETBPB_FN, 0, 0, 0, 0, (uint16_t)first);
    case BIOS_RWABS_FN:
        return (uint32_t)recreate_call_disk_vector(image, BIOS_RWABS_FN, (uint16_t)first, words_long(second, third),
                                                   (uint16_t)fourth, (uint16_t)fifth, (uint16_t)sixth);
    default:
        recreate_not_reconstructed("trp13: the AES's BIOS door, over a function other than Drvmap, Bconout, Getbpb "
                                   "and Rwabs — the four the desk asks");
    }
#else
    {
        /* The frame as three longwords and a word, each in a register the trap does not keep (so none is saved round
         * the call): the function over the first word, then the pairs, as the caller's own words lie. */
        register uint32_t answer __asm__("d0") = words_long(function, first);
        register uint32_t second_pair __asm__("d1") = words_long(second, third);
        register uint32_t third_pair __asm__("a0") = words_long(fourth, fifth);
        register uint16_t last __asm__("a1") = (uint16_t)sixth;

        __asm__ volatile ("move.w %3,-(%%sp)\n\t"
                          "move.l %2,-(%%sp)\n\t"
                          "move.l %1,-(%%sp)\n\t"
                          "move.l %0,-(%%sp)\n\t"
                          "trap #13\n\t"
                          "lea %c4(%%sp),%%sp"
                          : "+d"(answer), "+d"(second_pair), "+a"(third_pair), "+a"(last)
                          : "i"(TRP13_FRAME_BYTES)
                          : "d2", "a2", "memory", "cc");
        return answer;
    }
#endif
}
