/* shim.c — Musashi (MAME 68000 core) backing the differential oracle.
 *
 * Musashi calls back into these m68k_read/write_memory_* functions for every access;
 * we service them from a flat big-endian image supplied by Python and log every written
 * address (the write-set). osh_run() sets registers, runs a function to its return
 * (detected via a sentinel return address), and leaves final memory in the shared buffer.
 */
#include <stdint.h>
#include "m68k.h"

static uint8_t *g_mem;
static uint32_t g_size;

#define MAX_WRITES (1u << 20)
static uint32_t g_waddr[MAX_WRITES];
static uint32_t g_wn;

/* --- memory callbacks: big-endian, bounds-checked to the image --- */
unsigned int m68k_read_memory_8(unsigned int a)  { return a < g_size ? g_mem[a] : 0; }
unsigned int m68k_read_memory_16(unsigned int a) {
    return a + 1 < g_size ? (unsigned)(g_mem[a] << 8 | g_mem[a + 1]) : 0;
}
unsigned int m68k_read_memory_32(unsigned int a) {
    if (a + 3 >= g_size) return 0;
    return (unsigned)(g_mem[a] << 24 | g_mem[a + 1] << 16 | g_mem[a + 2] << 8 | g_mem[a + 3]);
}

static void logw(uint32_t a) { if (g_wn < MAX_WRITES) g_waddr[g_wn++] = a; }

void m68k_write_memory_8(unsigned int a, unsigned int v) {
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

/* Run `entry` to its rts. dregs/aregs are D0..D7 / A0..A7 inputs (aregs[7] overridden by sp).
 * Returns the instruction count executed; out_regs receives {D0, D1, A0, A1}. */
int osh_run(uint8_t *mem, uint32_t size, uint32_t entry,
            const uint32_t *dregs, const uint32_t *aregs,
            uint32_t sp, uint32_t sentinel, uint32_t max_insns, uint32_t *out_regs) {
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

    g_wn = 0;                             /* write-set = the function's writes only */
    uint32_t n = 0;
    while (n < max_insns && m68k_get_reg(0, M68K_REG_PC) != sentinel) {
        m68k_execute(1);
        n++;
    }
    out_regs[0] = m68k_get_reg(0, M68K_REG_D0);
    out_regs[1] = m68k_get_reg(0, M68K_REG_D1);
    out_regs[2] = m68k_get_reg(0, M68K_REG_A0);
    out_regs[3] = m68k_get_reg(0, M68K_REG_A1);
    return (int)n;
}

uint32_t        osh_num_writes(void)  { return g_wn; }
const uint32_t *osh_write_addrs(void) { return g_waddr; }