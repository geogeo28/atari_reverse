/* gemdos/pexec_load.h — `Pexec`'s PROGRAM LOADER and RELOCATOR (`$fc85ea`, `src/gemdos/pexec_load.c`):
 * a GEMDOS `.PRG` read into a basepage `Pexec` has already cut, its segments published in the basepage,
 * its absolute longwords relocated, and the rest of the TPA cleared.
 *
 * THE FILE, as the loader reads it — five `Fread`s, one per field group, into its own frame:
 *
 *      +0   magic.w      $601a, or EPLFMT
 *      +2   tlen.l  dlen.l  blen.l  slen.l            one read of sixteen bytes
 *      +18  reserved.l                                read ...
 *      +22  prgflags.l                                ...and read again OVER it: neither is looked at
 *      +26  absflag.w    non-zero: loaded and NOT relocated
 *      +28  TEXT, DATA, the symbol table (skipped by `Fseek`), then the RELOCATION stream
 *
 * THE RELOCATION STREAM is a longword — the first fixup's offset from TEXT, 0 for "none" — then one
 * byte per fixup: 0 ends the stream, 1 moves the cursor 254 bytes on without a fixup, anything else
 * moves it that far and fixes the longword there. A fixup ADDS the TEXT base to the longword.
 */
#ifndef TOS102US_GEMDOS_PEXEC_LOAD_H
#define TOS102US_GEMDOS_PEXEC_LOAD_H

#include <stdint.h>

/* ---- the file ------------------------------------------------------------------------------------ */
#define PRG_MAGIC            0x601a     /* `cmpi.w #$601a,-8(a6)` at $fc8626: a 68000 `bra.s` over the header */
#define PRG_MAGIC_BYTES      2
#define PRG_LENGTH_BYTES     4          /* each of them a longword */
#define PRG_LENGTHS_BYTES    16         /* tlen, dlen, blen, slen — one `Fread` at $fc8646 */
#define PRG_SKIPPED_BYTES    4          /* the reserved long and the program flags, read into ONE local */
#define PRG_ABSFLAG_BYTES    2
#define PRG_HEADER_BYTES     28         /* `addi.l #28` at $fc8780: where TEXT starts in the file */
#define PRG_SEGMENTS         3          /* `cmp.l #3,d5` at $fc8748: TEXT, DATA and BSS are published */
#define PRG_FIXUP_BYTES      4          /* the first offset is a longword, and every fixup adds one */
#define PRG_RELOCATION_END   0          /* `beq` at $fc880c */
#define PRG_RELOCATION_SKIP  1          /* `cmpw #1,d7` at $fc8812 ... */
#define PRG_SKIP_DISTANCE    254        /* ...and `addl #254,d6`: the one byte that moves without fixing */
#define PRG_RELOCATION_BYTE  0xff       /* `andw #255,d7` — every other byte is an UNSIGNED distance */

/* -66: not a program — a bad magic, or a first fixup outside TEXT+DATA. */
#define GEMDOS_EPLFMT        0xffffffbeu

/* ---- the loader's frame locals, as ONE host slot ----------------------------------------------------
 * Every field the loader reads the file into is a frame local whose ADDRESS it hands `Fread`, so off
 * target they are one host slot (`include/gemdos/gemdos.h`), laid out here. The ROM's own frame has
 * them apart (-8, -66, -30, -10, -38); what matters is only that each is where `Fread` put it. */
#define LOAD_MAGIC           0
#define LOAD_LENGTHS         (LOAD_MAGIC + PRG_MAGIC_BYTES)
#define LOAD_TLEN            LOAD_LENGTHS
#define LOAD_DLEN            (LOAD_TLEN + PRG_LENGTH_BYTES)
#define LOAD_BLEN            (LOAD_DLEN + PRG_LENGTH_BYTES)
#define LOAD_SLEN            (LOAD_BLEN + PRG_LENGTH_BYTES)
#define LOAD_SKIPPED         (LOAD_LENGTHS + PRG_LENGTHS_BYTES)
#define LOAD_ABSFLAG         (LOAD_SKIPPED + PRG_SKIPPED_BYTES)
#define LOAD_FIRST_FIXUP     (LOAD_ABSFLAG + PRG_ABSFLAG_BYTES)
#define LOAD_LOCALS_BYTES    (LOAD_FIRST_FIXUP + PRG_FIXUP_BYTES)

/* ---- where the open mode comes from ------------------------------------------------------------------
 * The loader opens the file with a mode word it never set: the ROM's `Fopen` call pushes only the name,
 * so the mode `Fopen` reads is the next word up the stack — the HIGH HALF OF THE SAVED D5 the loader's
 * own `movem.l d4-d7/a5` put there. Nothing between the trap entry and the loader touches D5, so that
 * is the trapping caller's D5, which the trap entry saved in its frame (`GEMDOS_SAVED_FRAME_D5`,
 * `include/addrs.h`). */

/* $fc85ea — load `name` into the TPA of `basepage`: 0, EPLFMT, ENSMEM, or what `Fopen` answered.
 * `caller_d5` is the D5 the loader runs with, whose high half is its `Fopen` mode (above). */
uint32_t gemdos_pexec_load(uint8_t *image, uint32_t name, uint32_t basepage, uint32_t caller_d5);

#endif /* TOS102US_GEMDOS_PEXEC_LOAD_H */
