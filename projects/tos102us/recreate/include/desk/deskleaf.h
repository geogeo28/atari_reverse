/* desk/deskleaf.h — THE DESK'S LEAVES FILED IN AES MODULES (`src/desk/deskleaf.c`): eighteen routines only the desk
 * calls, lying in the DOS glue's, gemgraf's, gsxif's and the BIOS door's text.
 *
 *   THE DOS GLUE, thirteen entries. Hand 68000, each entered over the frame its caller pushed; D0 as its tail leaves it.
 *     $fe3a7c dos_write(handle.w, count.w, buffer)   Fwrite — `moveq #$40,d1` and dos_read's own body from its second
 *                                                    instruction on: the count a WORD, zero-extended
 *     $fe3ab0 dos_gdir(drive.w, path)                Dgetpath
 *     $fe3ac4 dos_mkdir(path)                        Dcreate; EACCDN -> AES_DOS_AX 5; D0.w 1 done, 0 failed
 *     $fe3ae8 dos_setdt(handle.w, stamp)             Fdatime, SETTING the file's stamp from the caller's own two
 *                                                    argument words (the time, then the date), handed BY ADDRESS
 *     $fe3b02 dos_label(drive.w, name_out)           the DTA set to its own frame, Fsfirst("X:\*.*", volume label);
 *                                                    1 and the name copied out, else 0 with AES_DOS_ERR / AX 1
 *     $fe3b6a dos_space(drive.w, &total, &avail)     Dfree into its own frame; both in bytes, by 16-bit multiplies; 1
 *     $fe3ba0 dos_rename(old, new)                   Frename, its reserved word 0 — through `__DOS` with its caller's
 *                                                    return parked, as $fe3c28 does
 *     $fe3be8 dos_avail()                            Malloc(-1): the largest free block. Nothing parked, no verdict
 *     $fe3bfa dos_rawcio(character.w)                Crawio            } through $fe3c28, dos_free's tail: the
 *     $fe3c16 dos_chmod(name, set.w, attributes.w)   Fattrib           } function word pushed over the caller's own
 *     $fe3c1a dos_delete(name)                       Fdelete           } frame, both returns parked, `__DOS`'s
 *     $fe3c1e dos_rmdir(path)                        Ddelete           } verdict, the trap's whole D0
 *     $fe3c22 dos_create(name, attributes.w)         Fcreate           }
 *   GEMGRAF'S THREE.
 *     $fda8a8 gsx_pline(x.w, y.w, count.w, points)   `count` points moved by (x, y) into ptsin, then gsx_xline over
 *                                                    them: the outline a drag carries
 *     $fdae96 app_alloc(to_head.w)                   an ANODE off the desk's free list, linked at the head of its
 *                                                    list in use (or at its tail); the node, or 0 where none is free
 *     $fdaee2 app_free(node)                         ...unlinked from the list in use and pushed on the free list
 *   $fe8862 gsx_hardcopy()                           VDI escape 17 (v_hardcopy: XBIOS Scrdmp, the screen's dump to
 *                                                    the printer) through gsx_escapes' register entry
 *   $fee478 trp13(function.w, ...)                   THE AES's BIOS DOOR, trp14's sibling: its own return address
 *                                                    parked in AES_BIOS_RETURN so that the trap finds its caller's frame.
 *                                                    SHIPS AS ITS SIXTEEN ROM BYTES (`src/desk/trp13.S`); the C here is
 *                                                    its Tier-1 twin, 214 cycles a call over the ROM's
 *
 * WHAT IS HAND 68000 AND WHAT IS ALCYON C: the glue, gsx_pline, gsx_hardcopy and trp13 are hand 68000 (they `rts`);
 * app_alloc and app_free are Alcyon C (a `link`, a Line-F return). All are Line-F callees of the desk.
 *
 * THE HOST ARGUMENT (dos_free's precedent, `aes/gemdosif.h`): the entries through $fe3c28, dos_rename and trp13 PARK
 * THEIR CALLER's return address — the machine's, carried by no frame — so each core is handed it (`return_site`).
 *
 * NAMES: the published GEM desktop's (DOSIF, DESKAPP, the GSX interface), each read from its body.
 */
#ifndef TOS102US_DESK_DESKLEAF_H
#define TOS102US_DESK_DESKLEAF_H

#include "desk/deskglobals.h"

/* ---- the DOS glue ----------------------------------------------------------------------------------------------------- */
/* What dos_mkdir leaves in AES_DOS_AX where Dcreate answers EACCDN: the MS-DOS number GEM was written against. */
#define DOS_AX_ACCESS_DENIED  5          /* ($fe3ad8 move.w #5,$c918)                                          */
/* dos_mkdir's answer, the verdict turned round (`move.w d1,d0 / eori.w #1,d0`: a WORD — D0's high word is Dcreate's). */
#define DOS_MKDIR_DONE        1
#define DOS_MKDIR_FAILED      0
/* Fdatime's last word as dos_setdt pushes it: the stamp is SET, not asked for. */
#define FDATIME_SET           1          /* ($fe3ae8 move.w #1,-(sp))                                          */
#define DOS_STAMP_BYTES       4          /* the time word, then the date word: Fdatime's buffer                */

/* dos_label's frame (`link a6,#-52`): the search path it builds, then the DTA it hands GEMDOS — the frame's own
 * layout, so the path's unused eighth byte lies under the DTA as the ROM's does. */
#define LABEL_PATH            0          /* bytes[LABEL_PATH_BYTES]: "X:\*.*"   ($fe3b12 lea -52(a6),a0)        */
#define LABEL_PATH_BYTES      8
#define LABEL_DTA             8          /* bytes[LABEL_DTA_BYTES]              ($fe3b06 pea -44(a6))           */
#define LABEL_DTA_BYTES       44
#define LABEL_FRAME_BYTES     52         /* the path, then the DTA              ($fe3b02 link a6,#-52)          */
#define DTA_NAME              30         /* the name GEMDOS found, in a DTA     ($fe3b3e lea -14(a6),a1)        */
#define DRIVE_LETTER_BASE     0x40       /* drive 1 is 'A': a BYTE sum          ($fe3b1a add.b #64,d0)          */
#define FA_VOLUME_LABEL       8          /* Fsfirst's attribute                 ($fe3b28 move.w #8,-(sp))       */
#define DOS_LABEL_FOUND       1          /* ($fe3a08 moveq #1,d0: dos_sfirst's own tail, branched into)        */
#define DOS_LABEL_NONE        0          /* ($fe3a04 moveq #0,d0)                                              */
#define DOS_LABEL_FAILED      1          /* ...and what it then leaves in AES_DOS_ERR AND AES_DOS_AX ($fe3b50)  */

/* dos_space's frame (`link a6,#-16`): Dfree's four longwords, of which it reads the LOW WORD of each. */
#define DFREE_FREE_CLUSTERS   0          /* long                                ($fe3b94 mulu.w -14(a6),d1)     */
#define DFREE_TOTAL_CLUSTERS  4          /* long                                ($fe3b8e mulu.w -10(a6),d0)     */
#define DFREE_SECTOR_BYTES    8          /* long                                ($fe3b82 mulu.w -6(a6),d0)      */
#define DFREE_CLUSTER_SECTORS 12         /* long                                ($fe3b7e move.w -2(a6),d0)      */
#define DFREE_BYTES           16
#define LOW_WORD_OF_A_LONG    2          /* where a longword's low word lies                                   */
#define DOS_SPACE_DONE        1          /* ($fe3b9a moveq #1,d0)                                              */

#define FRENAME_RESERVED      0          /* Frename's first word                ($fe3ba6 move.l #$00560000,-(sp)) */
#define MALLOC_LARGEST        0xffffffffu /* Malloc(-1): the largest free block ($fe3be8 moveq #-1,d0)          */

/* ---- gemgraf's three --------------------------------------------------------------------------------------------------- */
/* The desk's ANODE lists, in its global block (AES_DESK_GLOBALS): the nodes free and the nodes in use, each a chain
 * through a node's first longword — DESK_ANODES_FREE, DESK_ANODES_IN_USE, ANODE_NEXT, ANODE_NONE (`desk/deskglobals.h`,
 * their one home since wave 1b's fix pass). */

/* ---- the BIOS door ----------------------------------------------------------------------------------------------------- */
/* The widest frame a ROM caller pushes for it, in words past the function: Rwabs's (rwflag, buffer.l, count, recno,
 * dev). The door itself reads none of it — the trap does, as many as the function takes. */
#define TRP13_ARGUMENT_WORDS  6          /* ($fe1b9a..$fe1bac, $fedcd8..$fedce6)                               */
#define TRP13_FRAME_BYTES     14         /* the function word and they: Rwabs's own frame                      */

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t aes_dos_write(uint8_t *image, int16_t handle, int16_t count, uint32_t buffer);             /* $fe3a7c */
uint32_t aes_dos_gdir(uint8_t *image, int16_t drive, uint32_t path);                                /* $fe3ab0 */
int16_t aes_dos_mkdir(uint8_t *image, uint32_t path);                                               /* $fe3ac4 */
uint32_t aes_dos_setdt(uint8_t *image, int16_t handle, uint32_t stamp);                             /* $fe3ae8 */
uint32_t aes_dos_label(uint8_t *image, int16_t drive, uint32_t name_out);                           /* $fe3b02 */
uint32_t aes_dos_space(uint8_t *image, int16_t drive, uint32_t total_out, uint32_t avail_out);      /* $fe3b6a */
uint32_t aes_dos_rename(uint8_t *image, uint32_t return_site, uint32_t old_name, uint32_t new_name); /* $fe3ba0 */
uint32_t aes_dos_avail(uint8_t *image);                                                             /* $fe3be8 */
uint32_t aes_dos_rawcio(uint8_t *image, uint32_t return_site, int16_t character);                   /* $fe3bfa */
uint32_t aes_dos_chmod(uint8_t *image, uint32_t return_site, uint32_t name, int16_t set, int16_t attributes); /* $fe3c16 */
uint32_t aes_dos_delete(uint8_t *image, uint32_t return_site, uint32_t name);                       /* $fe3c1a */
uint32_t aes_dos_rmdir(uint8_t *image, uint32_t return_site, uint32_t path);                        /* $fe3c1e */
uint32_t aes_dos_create(uint8_t *image, uint32_t return_site, uint32_t name, int16_t attributes);   /* $fe3c22 */

uint16_t aes_gsx_pline(uint8_t *image, int16_t x, int16_t y, int16_t count, uint32_t points);       /* $fda8a8 */
uint32_t aes_app_alloc(uint8_t *image, int16_t to_head);                                            /* $fdae96 */
void aes_app_free(uint8_t *image, uint32_t node);                                                   /* $fdaee2 */
void aes_gsx_hardcopy(uint8_t *image);                                                              /* $fe8862 */

/* The six argument words of the caller's frame past the function, in the order they lie on the stack — a caller
 * that pushed fewer hands whatever its stack holds above them, as the ROM's door leaves them there. */
uint32_t aes_trp13(uint8_t *image, uint32_t return_site, int16_t function, int16_t first, int16_t second,
                   int16_t third, int16_t fourth, int16_t fifth, int16_t sixth);                    /* $fee478 */
#endif

#endif /* TOS102US_DESK_DESKLEAF_H */
