/* tos.h — the real TOS entry points and machine primitives the on-target build calls.
 *
 * Every one of these is a hand-written wrapper in zynaps_os.s; none is exercised by the
 * differential harness (the oracle services traps directly and runs no interrupt at all), so this
 * file and that one are the project's one wholly UNVERIFIED surface — docs/on-target-execution.md
 * §3. What stands in for a test is the record: every write this file makes is read back in
 * zynaps_main.c and published in STATE.BIN, and smoke.py asserts on the read-backs.
 *
 * The C ABI passes every scalar in a 4-byte stack slot, so a `short` argument is the LOW word of
 * its slot on this big-endian machine; the wrappers all read the longword and push its low word.
 */
#ifndef ZYNAPS_SHIM_TOS_H
#define ZYNAPS_SHIM_TOS_H

#include <stdint.h>

/* ---- GEMDOS (trap #1) ------------------------------------------------------------------------ */
long Fcreate(const char *name, short attr);               /* 0x3c */
long Fopen(const char *name, short mode);                 /* 0x3d */
long Fclose(short handle);                                /* 0x3e */
long Fread(short handle, long count, void *buf);          /* 0x3f */
long Fwrite(short handle, long count, const void *buf);   /* 0x40 */
long Super(void *stack);                                  /* 0x20 */

/* The RETURN half of Super, made safe — docs/on-target-execution.md class 9. TOS goes back to user
 * mode on the USP it FROZE at `Super(0)`, not on one it reloads from the supervisor stack, so a
 * plain `Super(ssp)` is correct only while the compiler leaves %sp at the same depth at both call
 * sites. This one plants the USP itself, one instruction before the trap. Supervisor-only by
 * construction: nothing else has a supervisor stack pointer to hand back. */
long zy_leave_supervisor(void *ssp);

/* ---- XBIOS (trap #14) ------------------------------------------------------------------------ */
long Physbase(void);                                      /* 0x02 */
long Logbase(void);                                       /* 0x03 */
void Setscreen(void *log, void *phys, short rez);         /* 0x05 */
short Getrez(void);                                       /* 0x04 */

/* ---- machine primitives the C cannot spell ---------------------------------------------------- */

/* The interrupt mask, for the ONE critical section this shim has: installing the two exception
 * vectors, which the original brackets with `move.w #$2700,sr` / `move.w #$2300,sr` at 0x1005e and
 * 0x10076. A vertical blank landing between the two stores would enter a handler through a vector
 * whose other half still points at TOS. */
uint16_t zy_irq_disable(void);
void     zy_irq_restore(uint16_t sr);

/* `dc.w $a00a` — Line A "hide mouse pointer", the opcode at 0x10010 the oracle takes as an
 * exception and ../src/init.c therefore models as a no-op. Here it is the real thing. */
void zy_line_a_hide_mouse(void);

/* THERE IS NO `zy_ikbd_send_cmd` HERE ANY MORE, and its absence is the point. `ikbd_send_cmd`
 * @ 0x14444 was the shim's own bounded copy while the kit modelled no read for the ACIA status at
 * $fffc00 and the oracle spun there for ever. $fffc00 is a seeded READ slot now
 * (kit os.h, `OS_HW_ACIA_STATUS`), the routine is VERIFIED in ../src/input.c, and this build calls
 * that one — through the kit's `hw_read8`/`hw_write8`, which zynaps_backend.c answers with the real
 * 6850.
 *
 * SO THE SPIN IS UNBOUNDED HERE, exactly as the original's is. `IKBD_TX_POLL_MAX`, the core's own
 * give-up arm, is inside `#ifndef OS_NO_REFUSAL_TALLY` and build.sh defines that macro — so a
 * target build compiles the original's four instructions and no cap. What a dead transmitter costs
 * is a boot that never reaches the record: STATE.BIN is missing and smoke.py reports the run as a
 * crash, which is a louder finding than the 0 the bounded copy used to publish.
 */

/* The two exception entries. Each is the `movem` pair the C cannot write plus an `rte`; the body
 * is the verified handler in ../src/irq.c, reached through zy_vbl_tick / zy_timer_b_tick in
 * zynaps_main.c. Installed at the REAL vectors $70 and $120, which is where the original's boot
 * puts them — the game owns the machine for the length of its run, and so does this. */
void zy_vbl_entry(void);
void zy_timer_b_entry(void);
/* The third, and the one that makes the game playable: MFP channel 6, the keyboard ACIA, whose
 * vector number puts it at $118. Every wait the front end and the section start spell reads a byte
 * only `ikbd_acia_isr` writes. */
void zy_acia_entry(void);

#endif /* ZYNAPS_SHIM_TOS_H */
