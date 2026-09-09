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

/* ---- GEM (trap #2) is NOT declared here --------------------------------------------------------
 * `bubble_os.s`'s `bg_gem_trap` takes its selector and its parameter block in `d0`/`d1` — exactly
 * as the game's own `gem_aes` @ 0x149b6 and `vdi_call` @ 0x168d4 do — and is reached only from the
 * door in that same file, so it has no C calling convention to declare. What C DOES call is
 * `bg_gem_dispatch`, and `os.h` declares it beside the two doors that are one call to it. */

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

/* ...AND THE ONE PATH THAT DOES NOT NEED IT — WHICH NO LONGER READS THIS FLAG AT ALL.
 *
 * A 68000 exception handler already runs in supervisor mode, and `bg_timer_c_entry` never lowers the
 * mask the exception raised — so inside the sound ISR both of the things the gate provides are
 * already true: the privilege for $ff8800, and a select-then-data pair no MFP interrupt can land
 * inside (the mask is at the interrupt's own level 6, and the MFP is level 6). That is why the flag
 * below exists. Since wave 5b nothing C runs inside the interrupt — the 200 Hz handler is
 * `../src/asm/sound_tick.S`, which writes the two ports with the original's own bare `move.b`
 * pairs — so NOTHING SETS THE FLAG any more, and `psg.h`'s door reads 0 on every call it ever sees.
 *
 * THAT IS ALSO WHAT THE ORIGINAL'S ISR DOES, which is how this was found rather than guessed: over a
 * 1,000-vblank window its `psg_gate` @ 0x14940 carries 0.7 cycles a tick, because the handler writes
 * the ports itself and only USER-mode callers trap. What the two paths cost a write is ONE
 * measurement and it is kept in ONE place, atari/README.md's "Performance" table, which also carries
 * how many writes a tick makes.
 *
 * IF THE ISR IS EVER MADE FAITHFUL ABOUT ITS OWN IPL, THE PROTECTION HAS TO COME BACK. The
 * original's handler drops IPL 6 -> 5 so that other MFP channels can nest (`../../names.txt`,
 * `cmt 0x1459a`), and ours has never done it — first because C cannot touch `%sr`, and now, the
 * handler being assembly, as a decision recorded in `../src/asm/sound_tick.S`'s own header. A
 * build that lowered it would put an IKBD interrupt between the select and the data write, and the
 * byte would go to whatever register that path left selected; what would have to come back with the
 * drop is either this gate or a raise of the flag below.
 *
 * NOTHING SETS THE FLAG, so a door reached from user code always reads 0, and the branch it arms is
 * dead by construction rather than by argument. It is kept rather than deleted because it is what
 * the seam would need back the day the IPL drop is made faithful — and because a flag wrongly left
 * set is not a quiet wrong answer either: the next user-mode write to $ff8800 would be a bus error,
 * which `smoke.py`'s fault scan is. What has NO surface on target is the byte pair itself — see
 * ../STATUS.md, "Performance".
 *
 * WHAT THE FLAG SELECTS is `psg.h`'s own two stores rather than a routine here: an untrapped write
 * is a `move.b` pair and nothing else, and a `jsr` around it was 90 of its 100 cycles. */
extern volatile uint8_t bg_in_timer_c;

/* ---- machine primitives the C cannot spell ---------------------------------------------------- */

/* Read and write a 68000 exception vector. Both are supervisor-only, so both are Supexec'd from
 * `bubble_main.c` rather than called directly; they take and answer plain longwords. */
uint32_t bg_read_long(uint32_t address);
void     bg_write_long(uint32_t address, uint32_t value);
void     bg_write_byte(uint32_t address, uint8_t value);

/* The two exception entries this build installs. The Timer C one is the WHOLE 200 Hz tick — the
 * count, the handler and the $484 mirror — and it is NOT IN `bubble_os.s`: it is the head of
 * `../src/asm/sound_tick.S`, so the vector falls straight into the transcribed handler instead
 * of `jsr`ing to it. Two waves of glue went that way (428 cycles a tick to ~280 in wave 4, 356 to
 * 260 in wave 6a); `atari/build.sh` reads the folded routine back out of the linked disassembly.
 *
 * `bg_timer_c_entry` does NOT `rte`. The original's handler chains: it pushes TOS's own saved $114
 * vector and `rts`es, leaving the exception frame for TOS's handler to return from, so the 200 Hz
 * work TOS still wants done still happens. This stub does the same, taking the saved vector out of
 * the image longword `install_sound_vectors` parked it in. */
void bg_timer_c_entry(void);
void bg_super_gate_entry(void);

#endif /* BUBBLEGHOST_SHIM_TOS_H */
