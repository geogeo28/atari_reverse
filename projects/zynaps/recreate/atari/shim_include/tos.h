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

/* `ikbd_send_cmd` @ 0x14444, which is unported (../STATUS.md, "Not reconstructed": the kit models
 * no read for the ACIA status at $fffc00, so the oracle spins there for ever). Spin on bit 1 of
 * $fffc00 and store the byte to $fffc02, exactly as the original does — but BOUNDED, and the
 * bound's verdict is the return value: 1 = the transmitter went ready and the byte was stored,
 * 0 = the wait spun out and NOTHING was stored. The original has no bound and would hang; a
 * headless check that hangs decides nothing (the kit's own `sched_wait8` makes the same trade).
 *
 * A 0 here is a record field, not an exception: zynaps_main.c publishes it and smoke.py asserts
 * it. Supervisor-only — $fffc00 is I/O space. */
int zy_ikbd_send_cmd(uint8_t command);

/* The two exception entries. Each is the `movem` pair the C cannot write plus an `rte`; the body
 * is the verified handler in ../src/irq.c, reached through zy_vbl_tick / zy_timer_b_tick in
 * zynaps_main.c. Installed at the REAL vectors $70 and $120, which is where the original's boot
 * puts them — the game owns the machine for the length of its run, and so does this. */
void zy_vbl_entry(void);
void zy_timer_b_entry(void);

#endif /* ZYNAPS_SHIM_TOS_H */
