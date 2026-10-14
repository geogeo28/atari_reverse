/* desk/deskfpd.h — THE DESK'S PATH AND FILE NODES, unit G (`src/desk/deskfpd.c`): the routines `$fdf6d0..$fdfc3b` of
 * band 6 wave 1b — the two node pools and their free lists, a path's spec built and taken apart, a file of a list by
 * its object, the sort of a directory's files.
 *
 * NAMES: the published GEM desktop's (DESKFPD), each read from its body.
 */
#ifndef TOS102US_DESK_DESKFPD_H
#define TOS102US_DESK_DESKFPD_H

#include "desk/deskglobals.h"

/* ---- FNODE: a file of a window's directory ---------------------------------------------------------------------------- */
#define FNODE_NEXT            0          /* long: f_next                        ($fdf8e2 movea.l (a5),a5)      */
#define FNODE_ATTR            9          /* byte: the DTA's attributes          ($fdfafe move.b 9(a5),d0)      */
#define FNODE_TIME            10         /* word                                ($fdfac2 move.w 10(a4),d0)     */
#define FNODE_DATE            12         /* word                                ($fdfab0 move.w 12(a4),d7)     */
#define FNODE_SIZE            14         /* long                                ($fdfa50 move.l 14(a4),d0)     */
#define FNODE_NAME            18         /* bytes: the name, NUL-ended          ($fdfa3c lea 18(a5),a3)        */
#define FNODE_OBID            32         /* word: the object it is shown by     ($fdf8d8 cmp.w 32(a5),d7)      */
#define FNODE_BYTES           40         /* ($fdf6f0 muls.w #40)                                               */
#define FNODE_ATTR_SUBDIR     0x10       /* a folder                            ($fdfb0c and.w #16,d0)         */
#define FNODE_NONE            0
#define FILE_NODES            400        /* the pool's nodes: fn_init links 0..398, clears 399's ($fdf6e4 #398) */
#define FNODE_TIME_SECONDS_BITS 5        /* a time's two-second field, dropped by the date sort ($fdfac6 lsr.w #5) */

/* ---- PNODE: an open path, a window's ------------------------------------------------------------------------------ */
#define PNODE_NEXT            0          /* long: p_next                        ($fdf9ca cmpa.l (a4),a5)       */
#define PNODE_FLAGS           4          /* word                                ($fdf99a clr.w 4(a5))          */
#define PNODE_ATTR            6          /* word: the attributes it is read with ($fdfa0a move.w 22(a6),6(a5))  */
#define PNODE_SPEC            8          /* bytes: "D:\path\*.*"                ($fdf9ec addq.l #8,(sp))       */
#define PNODE_FLIST           130        /* long: its files                     ($fdf99e clr.l 130(a5))        */
#define PNODE_BYTES           140        /* ($fdf728 muls.w #140)                                              */
#define PNODE_NONE            0
#define PATH_NODES            5          /* pn_init links 0..4 — the last ONE PAST the pool (below) ($fdf71e moveq #4) */

/* (The desk's globals these routines keep — the two pools' heads, the DTA, g_isort, ml_pfndx: `desk/deskglobals.h`.) */

/* ---- a path's spec ------------------------------------------------------------------------------------------------- */
#define SPEC_BYTES            121        /* LEN_ZFPATH: a spec's room           ($fdf79a cmp.w #121,d0)        */
#define SPEC_ROOM_BESIDE_THE_PATH 13     /* "D:\", a name's 8.3 and its NUL, beside the path ($fdf796 add.w #13) */
#define SPEC_DRIVE_MARK       ':'        /* ($fdf7a6 move.b #58)                                               */
#define SPEC_SEPARATOR        '\\'       /* ($fdf7aa move.b #92)                                               */
#define SPEC_EXT_MARK         '.'        /* ($fdf7d6 move.b #46)                                               */
#define FPD_BLDSPEC_DONE      1          /* ($fdf7f0 moveq #1,d0)                                              */
#define FPD_BLDSPEC_TOO_LONG  0          /* ($fdf7a0 clr.w d0)                                                 */

/* ---- the sort (its keys: `desk/deskglobals.h`'s SORT_BY_*) ------------------------------------------------------------ */
#define PN_FCOMP_FIRST        1          /* ...the second file first: a larger size ($fdfa5a moveq #1,d0)      */
#define PN_FCOMP_SECOND      (-1)        /* ($fdfa6a moveq #-1,d0)                                             */
#define PN_SORT_COUNT_THEM    (-1)       /* pn_sort's count: index the list first ($fdfb46 cmpi.w #-1,8(a6))   */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_fn_init(uint8_t *image);                                                                     /* $fdf6d0 */
void aes_pn_init(uint8_t *image);                                                                     /* $fdf710 */
void aes_fpd_start(uint8_t *image);                                                                   /* $fdf756 */
int16_t aes_fpd_bldspec(uint8_t *image, int16_t drive, uint32_t path, uint32_t name, uint32_t ext,
                        uint32_t spec);                                                               /* $fdf77a */
void aes_fpd_parse(uint8_t *image, uint32_t spec, uint32_t drive_out, uint32_t path_out, uint32_t name_out,
                   uint32_t ext_out);                                                                 /* $fdf7f4 */
uint32_t aes_fpd_ofind(uint8_t *image, uint32_t files, int16_t obj);                                  /* $fdf8c6 */
uint32_t aes_fpd_elist(uint8_t *image, uint32_t files, uint32_t stop);                                /* $fdf8ec */
void aes_fn_free(uint8_t *image, uint32_t file);                                                      /* $fdf908 */
void aes_fl_free(uint8_t *image, uint32_t files);                                                     /* $fdf926 */
uint32_t aes_fn_alloc(uint8_t *image);                                                                /* $fdf952 */
uint32_t aes_pn_alloc(uint8_t *image);                                                                /* $fdf972 */
void aes_pn_free(uint8_t *image, uint32_t path);                                                      /* $fdf9aa */
uint32_t aes_pn_open(uint8_t *image, int16_t drive, uint32_t path, uint32_t name, uint32_t ext,
                     int16_t attributes);                                                             /* $fdf9da */
int16_t aes_pn_fcomp(uint8_t *image, uint32_t first, uint32_t second, int16_t key);                   /* $fdfa2c */
int16_t aes_pn_comp(uint8_t *image, uint32_t first, uint32_t second);                                 /* $fdfaee */
uint32_t aes_pn_sort(uint8_t *image, int16_t count, uint32_t files);                                  /* $fdfb38 */
#endif

#endif /* TOS102US_DESK_DESKFPD_H */
