/* tos.h — the TOS traps FLYSHARK.PRG makes, and the ONE address that turns the harness's flat
 * image into the machine's memory.
 *
 * Every routine declared here is written in `../flyshark_os.s`, where the register rule that makes
 * a trap wrapper safe lives (docs/on-target-execution.md class 3: TOS preserves only %d3-%d7 and
 * %a3-%a6, GCC caches live values in %d2/%a2).
 *
 * ================================================================================================
 * THE IMAGE BASE, AND WHY EVERY ADDRESS THIS BUILD HANDS THE MACHINE GOES THROUGH IT
 * ================================================================================================
 *
 * The verified cores address the game as `image + <Ghidra address>` — a flat byte array whose
 * offset 0x10000 is the program's first byte. On target that array is a `.bss` object inside a
 * GEMDOS TPA, so an image address A is the machine address `fs_image_base + A`, and the difference
 * between the two spaces is a constant this file names once.
 *
 * IT IS NOT ZERO AND CANNOT BE. Making it zero — the original's own arrangement, where an image
 * address IS a machine address — would put the game's world at 0x10000..0x87600 and leave this
 * program the 21,930 bytes below it, which is a tenth of what the compiled cores need.
 * ../atari/README.md's "The load-address budget" has the arithmetic and what it replaces the
 * original's `AUTO\`-only 0xd922 ceiling with.
 *
 * THREE ADDRESSES THE TRANSLATION CANNOT REACH, and each is handled where it happens rather than
 * here: the 68000's own vectors $70 and $118 (the cores store into the image's vector page and
 * `flyshark_os.s`'s two entries DISPATCH on what they find there), and TOS's KBDVBASE struct
 * (`fs_kbdvbase()` answers the real pointer expressed in image space, so the core's `image + it`
 * lands back on the real struct). ../flyshark_main.c carries both arguments.
 */
#ifndef FS_SHIM_TOS_H
#define FS_SHIM_TOS_H

#include <stdint.h>

/* The aligned base of the image array, published by `flyshark_main.c` before any core runs. An
 * image address A is `fs_image_base + A`; the ONE place that arithmetic is spelt is
 * `fs_machine_address` below and the doors that call it. */
extern uint8_t *fs_image_base;

/* XBIOS Setscreen's "leave this one alone", which the game passes for the logical base of every
 * frame it publishes and for the resolution. It is NOT an image address and must not be
 * translated — a -1 that had the image base added to it would point the shifter at the array's
 * last 256 bytes. */
#define FS_SETSCREEN_UNCHANGED 0xffffffffu

/* One image address in the form the machine needs. */
static inline void *fs_machine_address(uint32_t image_addr) {
    if (image_addr == FS_SETSCREEN_UNCHANGED)
        return (void *)(uintptr_t)FS_SETSCREEN_UNCHANGED;
    return fs_image_base + image_addr;
}

/* ---- GEMDOS (trap #1) ------------------------------------------------------------------------ */
long Fopen(const char *name, short mode);
long Fread(short handle, long count, void *buf);
long Fclose(short handle);
/* The two the CORES never call: a smoke build writes its record with them and the play build does
 * not, which is the whole of the difference between the two on the disc's own contents. */
long Fcreate(const char *name, short attr);
long Fwrite(short handle, long count, const void *buf);
long Cconout(short ch);
long Super(void *stack);
/* The RETURN half of Super, which is not `Super(ssp)` — docs/on-target-execution.md class 9, and
 * `../flyshark_os.s` carries the instruction that makes it safe. */
long fs_leave_supervisor(void *ssp);

/* ---- BIOS (trap #13) ------------------------------------------------------------------------- */
long Bconout(short device, short ch);
/* `move.w #$4,-(a7)` @ 0x14cd8 — BIOS device 4 is the IKBD, and a byte written to it is a command
 * to the 6301 rather than a character. It is the device number the ONE command this program sends
 * ($14, report joystick events) goes to. */
#define FS_BCONOUT_IKBD 4

/* ---- XBIOS (trap #14) ------------------------------------------------------------------------ */
void Setscreen(void *log, void *phys, short rez);
long Physbase(void);
long Logbase(void);
short Getrez(void);
void Setpalette(void *table);
void Vsync(void);
void *Kbdvbase(void);

/* ---- the machine primitives the C cannot write ----------------------------------------------- */
unsigned short fs_irq_disable(void);   /* answer the SR, then mask every level */
void fs_irq_restore(unsigned short sr);

/* The two exception entries, installed at the REAL $70 and $118. Each is the `movem` pair and the
 * `rte` a C function cannot write; the handler it runs is chosen by `flyshark_main.c` from the
 * longword the cores stored into the IMAGE's vector page. */
void fs_vbl_entry(void);
void fs_acia_entry(void);

/* ...and the C halves they call. */
void fs_vbl_tick(void);
void fs_acia_tick(void);

/* Where `fs_vbl_entry` goes when the reconstruction's handler has run: `vbl_handler` ends
 * `jmp $1164e.l`, whose operand at `A_vbl_chain_vector` the boot fills from TOS's own $70
 * (../include/init.h). The entry reads that operand out of the image and jumps through it, so the
 * chain is the program's own self-modified `jmp` rather than a pointer this shim keeps. */
extern volatile uint32_t fs_vbl_chain;

#endif /* FS_SHIM_TOS_H */
