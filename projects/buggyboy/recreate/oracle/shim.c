/* shim.c — Musashi (MAME 68000 core) backing the differential oracle.
 *
 * Musashi calls back into these m68k_read/write_memory_* functions for every access;
 * we service them from a flat big-endian image supplied by Python and log every written
 * address (the write-set). osh_run() sets registers, runs a function to its return
 * (detected via a sentinel return address), and leaves final memory in the shared buffer.
 */
#include <stdint.h>
#include "m68k.h"
#include "os.h"

static uint8_t *g_mem;
static uint32_t g_size;

#define MAX_WRITES (1u << 20)
static uint32_t g_waddr[MAX_WRITES];
static uint32_t g_wn;

/* --- IKBD 6850 ACIA (keyboard/joystick), $fffffc00/02 -> 24-bit bus alias $fffc00/02 -----
 * read_joystick busy-waits on the status TDRE bit then sends a command; the joystick reply
 * arrives via an interrupt we don't run (input state is instead scripted as an image global —
 * see HARNESS.md). We model only what the traced code touches: the status reads back as "ready
 * to send" so the wait loop terminates. The command byte written to IKBD_DATA lands above the
 * image and is dropped by the bounds check like any other hardware write. */
#define IKBD_STATUS 0xfffc00
#define IKBD_TX_RDY 0x02        /* TDRE: transmit register empty */

/* --- memory callbacks: big-endian, bounds-checked to the image --- */
unsigned int m68k_read_memory_8(unsigned int a) {
    if (a < g_size) return g_mem[a];
    if ((a & 0xffffff) == IKBD_STATUS) return IKBD_TX_RDY;
    return 0;
}
unsigned int m68k_read_memory_16(unsigned int a) {
    return a + 1 < g_size ? (unsigned)(g_mem[a] << 8 | g_mem[a + 1]) : 0;
}
unsigned int m68k_read_memory_32(unsigned int a) {
    if (a + 3 >= g_size) return 0;
    return (unsigned)(g_mem[a] << 24 | g_mem[a + 1] << 16 | g_mem[a + 2] << 8 | g_mem[a + 3]);
}

static void logw(uint32_t a) { if (g_wn < MAX_WRITES) g_waddr[g_wn++] = a; }

/* --- PSG (YM2149) capture -----------------------------------------------------------
 * The sound driver talks to the PSG by writing a register number to $ff8800 (select
 * latch) then the value to $ff8802 (data). Those addresses sit above the 1 MiB image, so
 * the writes would otherwise vanish. Tap them here into an ordered (reg,val) log the sound
 * tools read after each REFRESH run — the register stream that drives a Python YM2149. */
#define PSG_SELECT 0xff8800   /* register-select latch (68000's 24-bit bus aliases $ffff8800) */
#define PSG_DATA   0xff8802   /* data port */
#define MAX_PSG    4096
static uint8_t  g_psg_reg[MAX_PSG];
static uint8_t  g_psg_val[MAX_PSG];
static uint32_t g_psgn;        /* captured (reg,val) writes this run */
static uint8_t  g_psg_latch;   /* register selected by the last $ff8800 write */

void m68k_write_memory_8(unsigned int a, unsigned int v) {
    switch (a & 0xffffff) {                        /* mask to the 68000's 24-bit address bus */
        case PSG_SELECT: g_psg_latch = (uint8_t)v & 0x0f; return;
        case PSG_DATA:
            if (g_psgn < MAX_PSG) {
                g_psg_reg[g_psgn] = g_psg_latch;
                g_psg_val[g_psgn] = (uint8_t)v;
                g_psgn++;
            }
            return;
    }
    if (a < g_size) { g_mem[a] = (uint8_t)v; logw(a); }
}
void m68k_write_memory_16(unsigned int a, unsigned int v) {
    if (a + 1 < g_size) { g_mem[a] = (uint8_t)(v >> 8); g_mem[a + 1] = (uint8_t)v; logw(a); logw(a + 1); }
}
void m68k_write_memory_32(unsigned int a, unsigned int v) {
    if (a + 3 >= g_size) return;
    g_mem[a] = (uint8_t)(v >> 24); g_mem[a + 1] = (uint8_t)(v >> 16);
    g_mem[a + 2] = (uint8_t)(v >> 8); g_mem[a + 3] = (uint8_t)v;
    logw(a); logw(a + 1); logw(a + 2); logw(a + 3);
}

/* --- TOS trap dispatch (GEMDOS #1 / BIOS #13 / XBIOS #14, GEM #2) ------------------
 * Real code enters the OS via `trap #N`. We point each trap vector at a magic PC the run
 * loop detects; on a hit we read the 68000 exception frame (SR word + return PC long) plus
 * the function number/args from the caller's stack, apply a deterministic effect (os.h),
 * set D0, pop the frame, and resume at the caller. Vectors are installed transiently and
 * restored after the run, so the final image matches a reconstruction that never traps. */
#define TRAP_VEC_GEMDOS 0x84    /* trap #1  */
#define TRAP_VEC_GEM    0x88    /* trap #2  (AES/VDI — modeled via os_gem_trap) */
#define TRAP_VEC_BIOS   0xb4    /* trap #13 */
#define TRAP_VEC_XBIOS  0xb8    /* trap #14 */
#define MAGIC_GEMDOS 0x120      /* unused vector-page slots, even, never real code (>= 0x10000) */
#define MAGIC_GEM    0x124
#define MAGIC_BIOS   0x128
#define MAGIC_XBIOS  0x12c

static uint32_t g_heap;         /* Malloc bump pointer */
static uint32_t g_unmodeled;    /* count of traps whose real effect we do NOT model (fabricated D0) */
static uint32_t g_min_a7;       /* lowest A7 (deepest stack pointer) reached this run */

/* Service the trap the CPU jumped to (vec = 1/2/13/14). Reads the exception frame at A7,
 * services the OS call, and returns control to the caller with D0 set. Calls we faithfully
 * model set `modeled`; anything else (Super, BIOS, an unmodeled GEM opcode, an unstaged file,
 * unknown fn) is counted in g_unmodeled so the run can be rejected rather than trusted against
 * a fabricated result. */
static void handle_trap(int vec) {
    uint32_t sp     = m68k_get_reg(0, M68K_REG_A7);
    uint32_t sr     = m68k_read_memory_16(sp);       /* pushed status register */
    uint32_t retpc  = m68k_read_memory_32(sp + 2);   /* return address (past the trap) */
    uint32_t caller = sp + 6;                         /* caller's stack: fn word, then args */
    uint16_t fn     = (uint16_t)m68k_read_memory_16(caller);
    uint32_t arg1   = caller + 2;
    uint32_t d0 = 0;                                  /* default: success / no image effect */
    int modeled = 1;

    if (vec == 14 && fn == 0x26) {                    /* XBIOS Supexec: run the routine nested */
        uint32_t routine = m68k_read_memory_32(arg1); /* pea'd routine address */
        m68k_write_memory_32(caller - 4, retpc);      /* routine's rts returns to the caller */
        m68k_set_reg(M68K_REG_SR, sr);                /* restore SR first (may reselect SSP) */
        m68k_set_reg(M68K_REG_A7, caller - 4);
        m68k_set_reg(M68K_REG_PC, routine);           /* D0 (Supexec's result) is set by the routine */
        return;
    }

    if (vec == 1) {                                   /* GEMDOS */
        switch (fn) {
        case 0x48:                                    /* Malloc: bump-allocate a block */
            d0 = g_heap; g_heap += (m68k_read_memory_32(arg1) + 1u) & ~1u; break;
        case 0x3d: {                                  /* Fopen(fname, mode) -> handle */
            int32_t h = os_fopen(g_mem, m68k_read_memory_32(caller + 2));
            if (h < 0) modeled = 0; else d0 = (uint32_t)h;
            break;
        }
        case 0x3f: {                                  /* Fread(handle, count, buf) -> bytes read */
            int32_t nread = os_fread(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                                     m68k_read_memory_32(caller + 4),
                                     m68k_read_memory_32(caller + 8));
            if (nread < 0) modeled = 0; else d0 = (uint32_t)nread;
            break;
        }
        case 0x3e:                                    /* Fclose(handle) */
            if (os_fclose(g_mem, (uint16_t)m68k_read_memory_16(caller + 2)) < 0) modeled = 0;
            break;
        case 0x49: case 0x4a:                         /* Mfree / Mshrink -> success */
        case 0x02: case 0x09: break;                  /* Cconout / Cconws -> no image effect */
        case 0x06: d0 = OS_CRAWIO_RESULT; break;      /* Crawio: raw non-blocking console I/O */
        default: modeled = 0; break;                  /* Super, Pexec, unknown */
        }
    } else if (vec == 14) {                           /* XBIOS */
        switch (fn) {
        case 0x02: case 0x03: d0 = OS_SCREEN_BASE; break;   /* Physbase / Logbase */
        case 0x22: d0 = OS_KBDVBASE; break;           /* Kbdvbase -> fixed in-image KBDVBASE struct */
        case 0x04:                                    /* Getrez -> low-res */
        case 0x05: case 0x06: case 0x07:              /* Setscreen / Setpalette / Setcolor */
        case 0x19:                                    /* Ikbdws: serial write to the IKBD, no image effect */
        case 0x20:                                    /* Dosound: writes the YM2149, no image effect */
        case 0x25: case 0x28: case 0x2a: break;       /* Vsync / other no-image-effect XBIOS calls */
        default: modeled = 0; break;                  /* unknown */
        }
    } else if (vec == 2) {                            /* GEM: AES/VDI parameter-block calls */
        uint32_t reg_d0 = m68k_get_reg(0, M68K_REG_D0);   /* subsystem: AES 0xc8 / VDI 0x73 */
        uint32_t reg_d1 = m68k_get_reg(0, M68K_REG_D1);   /* -> parameter block */
        modeled = os_gem_trap(g_mem, reg_d0, reg_d1);     /* results land in the param block */
    } else {                                          /* BIOS(13): not modeled */
        modeled = 0;
    }
    if (!modeled) g_unmodeled++;

    m68k_set_reg(M68K_REG_SR, sr);                    /* restore SR first (may reselect SSP) */
    m68k_set_reg(M68K_REG_A7, caller);                /* then pop the 6-byte exception frame */
    m68k_set_reg(M68K_REG_PC, retpc);
    m68k_set_reg(M68K_REG_D0, d0);
}

/* Run `entry` until it returns to the sentinel (its rts) or reaches `stop_pc` — a checkpoint
 * PC that lets a never-returning function (e.g. _start, whose call to the game loop never
 * comes back) be diffed at a chosen point instead of at rts. Pass stop_pc = 0 to disable.
 * dregs/aregs are D0..D7 / A0..A7 inputs (aregs[7] overridden by sp). Returns 1 if it stopped
 * at the sentinel or the checkpoint, 0 if it hit the instruction cap first (a truncated run
 * whose memory must NOT be trusted as final). out_regs receives {D0, D1, A0, A1}. */
int osh_run(uint8_t *mem, uint32_t size, uint32_t entry,
            const uint32_t *dregs, const uint32_t *aregs,
            uint32_t sp, uint32_t sentinel, uint32_t stop_pc, uint32_t max_insns,
            uint32_t *out_regs) {
    g_mem = mem; g_size = size;

    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_pulse_reset();
    for (int i = 0; i < 8; i++) {
        m68k_set_reg((m68k_register_t)(M68K_REG_D0 + i), dregs[i]);
        m68k_set_reg((m68k_register_t)(M68K_REG_A0 + i), aregs[i]);
    }
    m68k_set_reg(M68K_REG_A7, sp);
    m68k_set_reg(M68K_REG_PC, entry);
    m68k_write_memory_32(sp, sentinel);   /* return address: rts -> sentinel */

    /* Install trap vectors transiently (restored below so the final image is trap-free). */
    uint32_t save_g = m68k_read_memory_32(TRAP_VEC_GEMDOS), save_x = m68k_read_memory_32(TRAP_VEC_XBIOS);
    uint32_t save_b = m68k_read_memory_32(TRAP_VEC_BIOS),   save_a = m68k_read_memory_32(TRAP_VEC_GEM);
    m68k_write_memory_32(TRAP_VEC_GEMDOS, MAGIC_GEMDOS);
    m68k_write_memory_32(TRAP_VEC_XBIOS, MAGIC_XBIOS);
    m68k_write_memory_32(TRAP_VEC_BIOS, MAGIC_BIOS);
    m68k_write_memory_32(TRAP_VEC_GEM, MAGIC_GEM);
    g_heap = OS_HEAP_BASE;
    g_unmodeled = 0;

    g_wn = 0;                             /* write-set = the function's writes only */
    g_psgn = 0;                           /* PSG capture = this run's register writes only */
    g_min_a7 = sp;                        /* deepest stack pointer (for exclude-band sanity checks) */
    uint32_t n = 0;
    for (; n < max_insns; n++) {
        uint32_t pc = m68k_get_reg(0, M68K_REG_PC);
        if (pc == sentinel || (stop_pc && pc == stop_pc)) break;
        uint32_t cur_a7 = m68k_get_reg(0, M68K_REG_A7);
        if (cur_a7 < g_min_a7) g_min_a7 = cur_a7;
        if      (pc == MAGIC_GEMDOS) handle_trap(1);
        else if (pc == MAGIC_XBIOS)  handle_trap(14);
        else if (pc == MAGIC_BIOS)   handle_trap(13);
        else if (pc == MAGIC_GEM)    handle_trap(2);
        else                         m68k_execute(1);
    }
    out_regs[0] = m68k_get_reg(0, M68K_REG_D0);
    out_regs[1] = m68k_get_reg(0, M68K_REG_D1);
    out_regs[2] = m68k_get_reg(0, M68K_REG_A0);
    out_regs[3] = m68k_get_reg(0, M68K_REG_A1);

    uint32_t wn = g_wn;                              /* keep the restore writes out of the write-set */
    m68k_write_memory_32(TRAP_VEC_GEMDOS, save_g);   /* restore vectors */
    m68k_write_memory_32(TRAP_VEC_XBIOS, save_x);
    m68k_write_memory_32(TRAP_VEC_BIOS, save_b);
    m68k_write_memory_32(TRAP_VEC_GEM, save_a);
    g_wn = wn;
    uint32_t final_pc = m68k_get_reg(0, M68K_REG_PC);  /* reached rts or the checkpoint? */
    return final_pc == sentinel || (stop_pc && final_pc == stop_pc);
}

uint32_t        osh_num_writes(void)  { return g_wn; }
const uint32_t *osh_write_addrs(void) { return g_waddr; }
uint32_t        osh_unmodeled(void)   { return g_unmodeled; }
uint32_t        osh_min_a7(void)      { return g_min_a7; }
uint32_t        osh_psg_count(void)   { return g_psgn; }
const uint8_t  *osh_psg_regs(void)    { return g_psg_reg; }
const uint8_t  *osh_psg_vals(void)    { return g_psg_val; }
