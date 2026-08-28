/* tos.h — the TOS traps and the hand-written routines the platform layer calls.
 *
 * Every function here is defined in os.S or render.S. They are declared in one place so the
 * argument shapes (the m68k SysV four-byte slots the wrappers read at +12) cannot drift between
 * two callers.
 *
 * SUPERVISOR. Everything that touches $ffff8xxx — the palette, the video base, the PSG — is
 * supervisor-only, and BLACK ICE runs its whole game loop inside one Super(0) rather than paying
 * a trap per frame. The GEMDOS file calls are made before that and after it, which is also why
 * os.S puts the file-I/O wrappers first (see its header for the handle-0 trap that ordering fixes).
 */
#ifndef BLACKICE_TOS_H
#define BLACKICE_TOS_H

#include <stdint.h>

/* ---- GEMDOS (trap #1) --------------------------------------------------------------------- */

#define FOPEN_READ          0
#define FCREATE_NORMAL      0
#define FSEEK_FROM_START    0

long Fcreate(const char *name, short attr);
long Fopen(const char *name, short mode);
long Fclose(short handle);
long Fread(short handle, long count, void *buf);
long Fwrite(short handle, long count, const void *buf);
long Fseek(long offset, short handle, short mode);
void Cconws(const char *text);
long Super(void *stack);

/* The return half of Super(0). os.S explains why it is not a second call to Super. */
long bi_leave_supervisor(void *ssp);

/* ---- BIOS (trap #13) ---------------------------------------------------------------------- */

#define BCON_DEVICE_KEYBOARD    2
#define KBSHIFT_READ            (-1)
/* Kbshift's bitmap. Only the two Shift bits are read: TOS consumes Alt+arrow for its own keyboard
 * mouse emulation, so an Alt-modified arrow never reaches Bconin at all (main.c, and QA.md's
 * defect 5 measured it). */
#define KBSHIFT_RIGHT_SHIFT     0x01
#define KBSHIFT_LEFT_SHIFT      0x02

long Bconstat(short device);
long Bconin(short device);
long Kbshift(short mode);

/* ---- XBIOS (trap #14) --------------------------------------------------------------------- */

#define SETSCREEN_KEEP      (-1)    /* leave this field of Setscreen alone */

long Physbase(void);
long Logbase(void);
long Getrez(void);
void Setscreen(void *logical, void *physical, short rez);
void Ikbdws(short count_minus_one, const char *bytes);
void *Kbdvbase(void);

/* KBDVECS, from Kbdvbase(). The joystick vector is the only slot this program replaces; it is at
 * a byte offset because the struct's other members are of no interest and naming them would be
 * inventing a type the program never uses. */
#define KBDVECS_JOYVEC_OFFSET   24

/* ---- the interrupt entries (os.S) ---------------------------------------------------------- */

void bi_vbl_entry(void);            /* installed in a free slot of TOS's _vblqueue */
void bi_vbl_vector_entry(void);     /* the fallback: the level-4 autovector, chained */
void bi_joy_entry(void);            /* installed on KBDVECS.joyvec */

/* Written by main.c before installing bi_vbl_vector_entry; read by os.S to chain the old handler. */
extern void *bi_vbl_chain;

/* Deselect both floppy drives (BRIEF.md's gotcha). Supervisor only; see os.S for the bit map. */
void bi_floppy_deselect(void);

/* The page-zero addresses this file's callers need are plat.h's — that file's header states it is
 * the one definition of the hardware and OS addresses, and two headers naming $454 would be exactly
 * the drift it exists to prevent. */

/* Written by bi_joy_entry from interrupt context. PORT 1 ONLY — os.S says why port 0 is not read. */
extern volatile uint8_t bi_joy_port1;
/* Called by bi_vbl_entry once per vertical blank; defined in main.c. */
void bi_vbl_tick(void);

/* ---- the clock (os.S) ---------------------------------------------------------------------- */

/* TOS's 200 Hz counter combined with the MFP timer-C down-counter: one unit is TIMER_TICK_NS.
 * SUPERVISOR ONLY — it reads _hz_200 in page zero. */
unsigned long bi_ticks(void);
/* The raw down-counter, for the run's own check that TIMER_C_RELOAD is what this TOS programmed. */
unsigned long bi_timer_c_read(void);

/* ---- the drawers (render.S) ---------------------------------------------------------------- */

void bi_render_cast(const void *job);
void bi_draw_columns(const void *job);
void bi_draw_sprites(const void *job);
void bi_c2p_high(const uint16_t *chunky, uint8_t *screen, long rows);
void bi_c2p_low(const uint16_t *chunky, uint8_t *screen, long rows);
void bi_fill(void *dst, long bytes, unsigned long plane01, unsigned long plane23);

/* render.S reaches these by name; main.c owns the storage and builds them at boot. */
extern uint16_t bi_chunky_row_offset[];
extern unsigned long bi_c2p_table_high[];
extern unsigned long bi_c2p_table_low[];

#endif /* BLACKICE_TOS_H */
