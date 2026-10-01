/* aes/shell.h — the shell's FILE FINDING (`src/aes/shell_find.c`): sh_find, which looks a file up as given, then at the
 * root, then down the environment's PATH, and the three helpers it walks with — sh_name, sh_envrn, sh_path.
 *
 * ALCYON C, entered by a Line-F call over the frame its caller pushed (a pointer a LONGWORD, every other argument a
 * WORD). Every GEMDOS call goes through the AES's own glue (`aes/gemdosif.h`), which leaves its verdict in AES_DOS_ERR
 * and AES_DOS_AX — what sh_find tests, not the glue's answer. Two of the routines keep a string in a FRAME LOCAL whose
 * address they hand on (sh_find its name to sh_path, sh_envrn its two buffers to the string helpers): the C keeps the
 * ROM's whole frame as bytes laid out as the ROM's (`SH_FIND_*`, `SH_ENVRN_*` below), in a host slot off target, so a
 * string longer than its buffer overruns into the neighbouring locals exactly as the ROM's does. Past the frame lie the
 * caller's saved A6 and the return address: the ROM stores on over them and RUNS ON, restoring whatever its stores
 * left. The C serves the one byte of that a C can (SH_SAVED_A6_TOP_BYTES) and halts by name past it — a conservative
 * choice, not the ROM's behaviour.
 */
#ifndef TOS102US_AES_SHELL_H
#define TOS102US_AES_SHELL_H

#include <stdint.h>

/* The bytes the walk tests. */
#define SH_DIRECTORY_SEPARATOR 0x5c      /* `\` ($feae24 cmpi.b #92; $feb03a the root's)                         */
#define SH_DRIVE_SEPARATOR    0x3a       /* `:` ($feae2a cmpi.b #58)                                             */
#define SH_PATH_SEPARATOR     0x3b       /* `;` between PATH's elements ($feaf48 move.b #59)                     */

/* sh_envrn copies AES_SH_SCRATCH_BYTES of the environment into AES_SH_SCRATCH and turns its byte 5 into a `;`
 * ($feae80 move.b #59,$9b75): the NUL the AES's own environment ("PATH=\0A:\\\0") has there, so its value reads as one
 * more PATH element — an EMPTY first one, which sh_path's first request skips. */
#define SH_ENVRN_PATCHED_BYTE 5

/* THE BYTE PAST EACH FRAME is the top byte of the caller's A6, which `link` saved there: a supervisor-stack address, so
 * 0 on a 24-bit bus. A 0 the ROM stores there changes nothing and it returns normally (sh_find's strcpy putting a
 * 22-byte name part's NUL there, sh_envrn's `clr.b` ending a 31-byte name's compare buffer), so the C keeps that byte
 * too, staged 0. Further than that the ROM does not stop either: it restores an A6 made of what it stored, and with
 * its caller's A6 below $10000 a 23-byte name part's NUL, or a 32-byte name's `clr.b`, writes 0 over 0 and leaves the
 * same frame on the bus. The C HALTS there all the same, when a NONZERO byte or anything further would land: whether
 * the A6 the ROM restores still works depends on the rest of its caller's A6, which no C can see — a conservative
 * halt, by name. Each frame's slot is its bytes and this one. */
#define SH_SAVED_A6_TOP_BYTES 1

/* sh_envrn's FRAME (`link #-46`), from -46(a6): its copy of the name searched for, a buffer the environment is
 * compared through, then its locals. */
#define SH_ENVRN_SEARCH       0          /* bytes[16]: the name searched for, lstcpy'd ($feae4c)                 */
#define SH_ENVRN_COMPARE      16         /* bytes[16]: the environment's bytes after a first match ($feaed4)     */
#define SH_ENVRN_CHARACTER    32         /* byte: the environment byte read  ($feae98 -14(a6))                   */
#define SH_ENVRN_SKIPPING     34         /* word: inside a string that did not match ($feaefe -12(a6))           */
#define SH_ENVRN_LENGTH       36         /* word: the name's length less one ($feae54 -10(a6))                   */
#define SH_ENVRN_COMPARE_AT   38         /* long: the compare buffer's address, stored and never read ($feae5c)  */
#define SH_ENVRN_CURSOR       42         /* long: where in the environment ($feae88 -4(a6))                      */
#define SH_ENVRN_FRAME_BYTES  46
#define SH_ENVRN_SLOT_BYTES   (SH_ENVRN_FRAME_BYTES + SH_SAVED_A6_TOP_BYTES)
/* What the search is handed: the name's first byte is matched alone, and the rest compared as a string. */
#define SH_ENVRN_REST         1

/* sh_find's FRAME (`link #-26`: four bytes of Alcyon's argument slot below) from -22(a6). */
#define SH_FIND_NAME          0          /* bytes[14]: the spec's name part, strcpy'd ($feafe6)                  */
#define SH_FIND_NAME_POINTER  14         /* long: sh_name's answer, stored and re-read once before the copy      */
#define SH_FIND_FIRST_TRY     18         /* word: the root is still to be tried ($feaff8 move.w #1,-4(a6))       */
#define SH_FIND_PATH          20         /* word: the PATH element next tried ($feaff4 clr.w -2(a6))             */
#define SH_FIND_FRAME_BYTES   22
#define SH_FIND_SLOT_BYTES    (SH_FIND_FRAME_BYTES + SH_SAVED_A6_TOP_BYTES)

/* sh_find's search: read-only and system files too ($feaffe move.w #5) — F_RDONLY | F_SYSTEM. */
#define SH_FIND_ATTRIBUTES    5
/* What a caller passes for "no routine" ($feab00 rs_readit's `clr.l (sp)`; $feb0c2 `tst.l`). */
#define SH_FIND_NO_ROUTINE    0

#ifndef __ASSEMBLER__
uint32_t aes_sh_name(uint8_t *image, uint32_t path);                                                  /* $feae04 */
int16_t aes_sh_envrn(uint8_t *image, uint32_t answer, uint32_t search);                              /* $feae36 */
int16_t aes_sh_path(uint8_t *image, int16_t which, uint32_t path, uint32_t name);                   /* $feaf1e */
int16_t aes_sh_find(uint8_t *image, uint32_t spec, uint32_t routine);                                 /* $feafbe */
#endif

#endif /* TOS102US_AES_SHELL_H */
