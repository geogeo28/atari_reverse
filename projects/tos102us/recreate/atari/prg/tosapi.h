/* tosapi.h — the TOS entry points TOSTEST.PRG and TOSBENCH.PRG call, and the system addresses they
 * read. Every function here is a wrapper in os.S; nothing in this directory traps from C.
 *
 * THE PROGRAMS RUN IN SUPERVISOR MODE FROM `_start` TO THE END, and never leave it. Two reasons:
 * `_hz_200` and the vector page are supervisor-only reads, and bug class 9 — `Super(0)` /
 * `Super(ssp)` is not a balanced pair, because TOS returns to user mode on the USP it froze — can
 * only bite a program that goes back. One entry, no exit, no unwind to get wrong. That is also why
 * there is no `Super` wrapper below: `_start` issues the one `Super(0)` itself, and a wrapper
 * callable from C would be an invitation to the round trip this design refuses to make.
 */
#ifndef TOS102US_TOSAPI_H
#define TOS102US_TOSAPI_H

#include <stdint.h>

/* ---- GEMDOS (trap #1) ----------------------------------------------------------------------- */
int32_t Sversion(void);                             /* 0x30 */
int32_t Tgetdate(void);                             /* 0x2a */
int32_t Getmpb(void *mpb);                          /* 0x14 */
int32_t Malloc(int32_t bytes);                      /* 0x48 */
int32_t Mfree(void *block);                         /* 0x49 */
int32_t Fsetdta(void *dta);                         /* 0x1a */
int32_t Fsfirst(const char *pattern, int16_t attr); /* 0x4e */
int32_t Fsnext(void);                               /* 0x4f */
int32_t Fopen(const char *name, int16_t mode);      /* 0x3d */
int32_t Fread(int16_t handle, int32_t count, void *buffer);     /* 0x3f */
int32_t Fclose(int16_t handle);                     /* 0x3e */

/* ---- BIOS (trap #13) ------------------------------------------------------------------------ */
int32_t Bconout(int16_t device, int16_t character); /* 0x03 */
int32_t Drvmap(void);                               /* 0x0a */
int32_t Kbshift(int16_t mode);                      /* 0x0b — mode -1 reads without setting */

/* ---- XBIOS (trap #14) ----------------------------------------------------------------------- */
int32_t Physbase(void);                             /* 0x02 */
int32_t Logbase(void);                              /* 0x03 */
int32_t Getrez(void);                               /* 0x04 */

/* ---- the system variables the programs read --------------------------------------------------
 * Both are supervisor-only, which is the other reason the programs stay in supervisor mode. */
#define SYSVAR_FRCLOCK  0x466L      /* _frclock: the VBL counter TOS's own handler increments */
#define SYSVAR_HZ200    0x4BAL      /* _hz_200:  the 200 Hz timer-C counter                   */

static inline uint32_t read_frclock(void) { return *(volatile uint32_t *)SYSVAR_FRCLOCK; }
static inline uint32_t read_hz200(void)   { return *(volatile uint32_t *)SYSVAR_HZ200; }

/* Bconout's device numbers; 2 is the VT52 console, i.e. the screen. */
#define BCON_DEV_CON    2

/* Fsfirst's attribute word: the ordinary files of a directory, no volume label, no subdirectories. */
#define FA_NORMAL       0x00

/* Fopen's mode word. */
#define FO_READ         0

/* Malloc's block size, shared: TOSTEST records four of these allocated and freed, TOSBENCH churns
 * one in a loop. Held to ONE size so a conformance answer and a timing are about the same request
 * — a bench that asked for a different size would be measuring a different path through GEMDOS's
 * free list than the one the ledger's addresses describe. */
#define MALLOC_BLOCK_BYTES  1024L

#endif /* TOS102US_TOSAPI_H */
