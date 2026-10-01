/* aes/resource.h — the RESOURCE layer (`src/aes/resource.c`): rsrc_gaddr's address switch and the relocation that
 * turns a resource file's offsets into addresses, over `aes/objects.h`'s header and globals.
 *
 * All ALCYON C, entered by a Line-F call over the frame its caller pushed — a pointer a LONGWORD, every other
 * argument a WORD (an Alcyon `int`) — but rom_rsc_init, which gem_entry `jsr`s. Every routine reaches THE resource
 * through two globals, AES_RS_GLOBAL (the caller's global[]) and AES_RS_HDR (its header), which rs_sglobal sets and
 * the rest read; a C core takes them as the ROM does, from RAM, never as an argument. What they answer is what their
 * callers read: a WORD (`tst.w d0`, `move.w d0,d6` into intout[0]), get_sub's and get_addr's LONG address, rs_str's
 * buffer — and, for fix_objects, rs_fixit and rom_ram's resource arms, D0 as their last step left it, which only
 * rom_ram hands on and none of its callers reads.
 *
 * Also here, the ROM's OWN resources (rom_rsc_init, rom_ram): one bundle in the ROM, copied at start-up, its
 * resources relocated in place on their first request. And the layer's GEMDOS calls, through the AES's own glue: the
 * start-up's Malloc, rsrc_free's Mfree, and the load (rs_readit, rs_load) — a file found by the shell's sh_find
 * (`aes/shell.h`), read whole into a Malloc block and relocated.
 */
#ifndef TOS102US_AES_RESOURCE_H
#define TOS102US_AES_RESOURCE_H

#include <stdint.h>

/* rsrc_gaddr's TYPES: get_addr's switch ($fea83e: `cmp.w #16; bhi` the default, an unsigned word; table $fefbf8). */
#define R_TREE                0
#define R_OBJECT              1
#define R_TEDINFO             2
#define R_ICONBLK             3
#define R_BITBLK              4
#define R_STRING              5          /* a free string's ADDRESS: the pointer the table holds  */
#define R_IMAGEDATA           6          /* a free image's address, the same way                  */
#define R_OBSPEC              7
#define R_TEPTEXT             8
#define R_TEPTMPLT            9
#define R_TEPVALID            10
#define R_IBPMASK             11
#define R_IBPDATA             12
#define R_IBPTEXT             13
#define R_BIPDATA             14
#define R_FRSTR               15         /* the address of a free string's POINTER in the table   */
#define R_FRIMG               16
#define R_LAST_TYPE           R_FRIMG
/* What get_addr answers for a type out of range, and what fix_long leaves alone: `moveq #-1` ($fea866, $feaa1a). */
#define RS_NO_ADDRESS         0xffffffffu

/* The ROM's OWN resources: one bundle of 17,218 bytes behind a table of five word offsets — the AES's resource after
 * the table, then the desk's, the desk's icon data, the default DESKTOP.INF and the format dialogs' resource — which
 * start-up copies whole into a Malloc block ($fee4de) and relocates each part of in place on its first use. */
#define AES_RSC_BUNDLE        0xfd5b88   /* ($fee4f4 move.l #$fd5b88)                                          */
#define AES_RSC_BUNDLE_BYTES  0x4342     /* ($fee4e6 move.l #17218, the Malloc; $fee4f0 the copy)               */

/* rom_ram's PARTS of the bundle ($fee5c8's first argument), each an entry of AES_RSC_TABLE (`aes/aes.h`): the AES's
 * and the desk's resources and the format dialogs', relocated on their first request; the desk's icons, copied
 * `size` bytes of, or (4) all but the first `size`; the default DESKTOP.INF, copied whole. */
#define ROM_RSC_AES           0
#define ROM_RSC_DESK          1
#define ROM_RSC_DESK_ICONS    2
#define ROM_RSC_DESKTOP_INF   3
#define ROM_RSC_DESK_ICONS_TAIL 4
#define ROM_RSC_FORMAT        5
#define ROM_RSC_PARTS         6
#define ROM_RSC_ADDRESS       0          /* long: the part's address in the RAM copy ($fee5ea)                 */
#define ROM_RSC_BYTES         4          /* word: its length                    ($fee5fa move.w 4(a0),d3)      */
#define ROM_RSC_ENTRY_BYTES   6          /* ($fee5de muls.w #6)                                                */

void aes_fix_chpos(uint8_t *image, uint32_t coordinate, int16_t is_x);                                /* $fea622 */
int16_t aes_rs_obfix(uint8_t *image, uint32_t tree, int16_t object);                                  /* $fea69c */
uint32_t aes_get_sub(uint8_t *image, int16_t index, int16_t section, int16_t size);                    /* $fea716 */
uint32_t aes_get_addr(uint8_t *image, int16_t type, int16_t index);                                   /* $fea742 */
void aes_fix_trindex(uint8_t *image);                                                                  /* $fea86a */
int16_t aes_fix_objects(uint8_t *image);                                                               /* $fea8bc */
void aes_fix_tedinfo(uint8_t *image);                                                                  /* $fea918 */
void aes_fix_nptrs(uint8_t *image, int16_t last, int16_t type);                                       /* $fea9d4 */
int16_t aes_fix_ptr(uint8_t *image, int16_t type, int16_t index);                                     /* $fea9f8 */
int16_t aes_fix_long(uint8_t *image, uint32_t pointer);                                               /* $feaa0a */
void aes_rs_sglobal(uint8_t *image, uint32_t global);                                                  /* $feaa38 */
int16_t aes_rs_gaddr(uint8_t *image, uint32_t global, int16_t type, int16_t index, uint32_t answer);  /* $feaa86 */
int16_t aes_rs_saddr(uint8_t *image, uint32_t global, int16_t type, int16_t index, uint32_t value);   /* $feaab2 */
void aes_do_rsfix(uint8_t *image, uint32_t header, int16_t bytes);                                     /* $feaba4 */
int16_t aes_rs_fixit(uint8_t *image, uint32_t global);                                                 /* $feac4e */
uint32_t aes_rs_str(uint8_t *image, int16_t string);                                                   /* $fea6e6 */
int16_t aes_rom_ram(uint8_t *image, int16_t part, uint32_t pointer, int16_t size);                    /* $fee5c8 */
int16_t aes_rs_free(uint8_t *image, uint32_t global);                                                  /* $feaa58 */
void aes_rom_rsc_init(uint8_t *image);                                                                 /* $fee4de */
int16_t aes_rs_readit(uint8_t *image, uint32_t global, uint32_t name);                                /* $feaae2 */
int16_t aes_rs_load(uint8_t *image, uint32_t global, uint32_t name);                                  /* $feac5c */

#endif /* TOS102US_AES_RESOURCE_H */
