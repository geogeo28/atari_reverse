/* tos.h — the real TOS entry points and machine primitives the on-target build calls.
 *
 * Every one of these is a hand-written wrapper in `bubble_os.s`; none is exercised by the
 * differential harness (the oracle services traps directly and runs no interrupt at all), so this
 * file and that one are this project's one wholly UNVERIFIED surface —
 * docs/on-target-execution.md §3. What stands in for a test is the record: every write made
 * through here is read back in `bubble_main.c` and published in STATE.BIN, and `smoke.py` asserts
 * on the read-backs.
 *
 * THE C ABI PASSES EVERY SCALAR IN A 4-BYTE STACK SLOT, so a `short` argument is the LOW word of
 * its slot on this big-endian machine; the wrappers all read the longword and push its low word.
 * Reading `4(%sp)` instead of the whole slot is class 3 of the taxonomy, and it is silent.
 *
 * THIS BUILD RUNS IN USER MODE, which is the difference from `projects/zynaps/recreate/atari`'s
 * shim and is not a style choice. Bubble Ghost is a GEM application: it makes `trap #2` AES and VDI
 * calls throughout, and the AES is entered from user mode by every program TOS was written for.
 * The original takes supervisor exactly twice — around the one byte it pokes at $484 — and this
 * build reproduces that (`os_super` in `os.h` is the REAL trap here, unlike Zynaps' no-op). What
 * that costs is that the three supervisor-only stores the cores make — the two PSG ports and the
 * MFP vector register — cannot be plain stores, and they are not: they go through the trap #9 gate
 * below, which is the very mechanism the original uses for the same reason.
 */
#ifndef BUBBLEGHOST_SHIM_TOS_H
#define BUBBLEGHOST_SHIM_TOS_H

#include <stdint.h>

/* ---- GEMDOS (trap #1) ------------------------------------------------------------------------ */
long Cconout(short ch);                                   /* 0x02 */
long Cauxout(short ch);                                   /* 0x04 */
long Cprnout(short ch);                                   /* 0x05 */
long Crawio(short w);                                     /* 0x06 */
long Crawcin(void);                                       /* 0x07 */
long Cnecin(void);                                        /* 0x08 */
long Cconis(void);                                        /* 0x0b */
long Super(void *stack);                                  /* 0x20 */
long Fcreate(const char *name, short attr);               /* 0x3c */
long Fopen(const char *name, short mode);                 /* 0x3d */
long Fclose(short handle);                                /* 0x3e */
long Fread(short handle, long count, void *buf);          /* 0x3f */
long Fwrite(short handle, long count, const void *buf);   /* 0x40 */
long Fdelete(const char *name);                           /* 0x41 */
long Fseek(long offset, short handle, short mode);        /* 0x42 */
void Pterm(short code);                                   /* 0x4c — does not return */

/* The RETURN half of Super, made safe — docs/on-target-execution.md class 9. TOS goes back to user
 * mode on the USP it FROZE at `Super(0)`, not on one it reloads from the supervisor stack, so a
 * plain `Super(ssp)` is correct only while the compiler leaves %sp at the same depth at both call
 * sites. This one plants the USP itself, one instruction before the trap. */
long bg_leave_supervisor(void *ssp);

/* ---- BIOS (trap #13) -------------------------------------------------------------------------- */
long Bconout(short dev, short ch);                        /* 0x03 */

/* ---- XBIOS (trap #14) ------------------------------------------------------------------------- */
long  Physbase(void);                                     /* 0x02 */
long  Logbase(void);                                      /* 0x03 */
short Getrez(void);                                       /* 0x04 */
void  Setscreen(void *log, void *phys, short rez);        /* 0x05 */
void  Setpalette(const void *palette);                    /* 0x06 */
short Setcolor(short index, short value);                 /* 0x07 */
long  Random(void);                                       /* 0x11 */
void  Vsync(void);                                        /* 0x25 */
long  Supexec(void (*routine)(void));                     /* 0x26 */

/* ---- GEM (trap #2): the one call both bindings make ------------------------------------------- */
/* `d0` selects the AES (0xc8) or the VDI (0x73) and `d1` is the parameter block — which is exactly
 * what the game's own `gem_aes` @ 0x149b6 and `vdi_call` @ 0x168d4 do. The POINTER TRANSLATION that
 * has to happen around it is `os.h`'s, not this file's: this is the trap and nothing else. */
long bg_gem_trap(long d0, void *pblock);

/* ---- the trap #9 supervisor gate --------------------------------------------------------------
 * THE ORIGINAL'S OWN MECHANISM, and this build needs it for the original's own reason. A user-mode
 * program cannot store to $ffff8800 or $fffffa17, so Bubble Ghost reaches the YM2149 through
 * `psg_access` @ 0x14940 — three argument words and a `trap #9` into its own supervisor handler at
 * $a4. The reconstruction cannot trap (STATUS.md's "Model gaps"), so `psg_gate` calls
 * `trap9_psg_handler` directly and the two PSG ports are the kit's `psg.h` doors; here those doors
 * are these three operations, which run in supervisor because a trap handler does.
 *
 * The handler raises to IPL 7 across the select-and-access pair, exactly as the original's does: a
 * 200 Hz Timer C interrupt landing between a register select and its data write would write the
 * wrong register.
 *
 * WHAT IS ON THE VECTOR IS OURS, NOT THE GAME'S. `install_sound_vectors` writes the original's
 * handler address into image[$a4] — an image byte — and the shim installs `bg_super_gate_entry` at
 * the machine's $a4 instead. Nothing in this build ever executes the original's handler, so the
 * two never disagree about anything but the number stored in that longword. */
#define BG_GATE_PSG_WRITE 0u   /* select `reg`, store `value` at $ff8802, read the register back */
#define BG_GATE_PSG_READ  1u   /* select `reg` and read it back, storing nothing */
#define BG_GATE_STORE8    2u   /* store `value` at the 24-bit address `reg` — the MFP vector byte */

uint32_t bg_super_gate(uint32_t operation, uint32_t operand, uint32_t value);

/* ---- machine primitives the C cannot spell ---------------------------------------------------- */

/* Read and write a 68000 exception vector. Both are supervisor-only, so both are Supexec'd from
 * `bubble_main.c` rather than called directly; they take and answer plain longwords. */
uint32_t bg_read_long(uint32_t address);
void     bg_write_long(uint32_t address, uint32_t value);
void     bg_write_byte(uint32_t address, uint8_t value);

/* The two exception entries this build installs. Each is the `movem` pair the C cannot write; the
 * BODY of the Timer C one is the verified `timer_c_sound_isr` in ../src/sound.c, reached through
 * `bg_timer_c_tick` in `bubble_main.c`.
 *
 * `bg_timer_c_entry` does NOT `rte`. The original's handler chains: it pushes TOS's own saved $114
 * vector and `rts`es, leaving the exception frame for TOS's handler to return from, so the 200 Hz
 * work TOS still wants done still happens. This stub does the same, taking the saved vector out of
 * the image longword `install_sound_vectors` parked it in. */
void bg_timer_c_entry(void);
void bg_super_gate_entry(void);

#endif /* BUBBLEGHOST_SHIM_TOS_H */
