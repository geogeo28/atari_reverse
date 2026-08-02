/* shim.c — Musashi (MAME 68000 core) backing the differential oracle.
 *
 * Musashi calls back into these m68k_read/write_memory_* functions for every access;
 * we service them from a flat big-endian image supplied by Python and log every written
 * address (the write-set). osh_run() sets registers, runs a function to its return
 * (detected via a sentinel return address), and leaves final memory in the shared buffer.
 */
#include <stdint.h>
#include "m68k.h"
/* The oracle keeps its own refusal tally — g_unmodeled, below — so os.h must give it the no-op
 * os_refused() rather than the candidate-side counter in ../src/os_refusal.c, which the oracle does
 * not link. Declared here rather than as a -D in kit.mk because this is the only oracle translation
 * unit that includes os.h, and a build flag can be forgotten where an adjacent #define cannot. */
#define OS_NO_REFUSAL_TALLY 1
#include "os.h"

static uint8_t *g_mem;
static uint32_t g_size;

#define MAX_WRITES (1u << 20)
static uint32_t g_waddr[MAX_WRITES];
static uint32_t g_wn;

/* --- optional executed-PC coverage (off by default; osh_cov_enable turns it on) --------------
 * A bit per image byte address, accumulated ACROSS osh_run calls (reset with osh_cov_reset), so a
 * whole test session's oracle execution can be queried. tools/coverage_gap.py uses it to flag
 * side-effecting call sites (Dosound/INITTUNE/INITFX/stop_music/... bsr sites) that no test ever
 * executes — i.e. sound/OS triggers whose effect is off-image and thus invisible to the diff.
 * Gated so it adds nothing to a normal `make test`. */
#define COV_SIZE (1u << 20)                 /* one bit per address in [0, 1 MiB) */
static uint8_t g_cov[COV_SIZE / 8];
static int     g_cov_on;
void osh_cov_enable(int on) { g_cov_on = on; }
void osh_cov_reset(void)    { for (uint32_t i = 0; i < sizeof g_cov; i++) g_cov[i] = 0; }
int  osh_cov_visited(uint32_t pc) { return pc < COV_SIZE && ((g_cov[pc >> 3] >> (pc & 7)) & 1); }

/* --- optional cycle-per-PC profile (off by default; osh_prof_enable turns it on) -------------
 * One uint32 cycle tally per even PC in [0, PROF_SIZE), accumulated across osh_run_bench calls
 * (reset with osh_prof_reset). Sized for the cross-compiled recon/remaster ELFs, which link at
 * base 0 and stay well under 1 MiB of text. remaster's tools/profile.py maps the tallies back to
 * symbols. Gated so it adds nothing to a normal bench run. */
#define PROF_SIZE (1u << 20)                /* PCs covered: [0, 1 MiB) */
static uint32_t g_prof[PROF_SIZE / 2];      /* tally per even PC */
static int      g_prof_on;
void osh_prof_enable(int on) { g_prof_on = on; }
void osh_prof_reset(void)    { for (uint32_t i = 0; i < PROF_SIZE / 2; i++) g_prof[i] = 0; }
const uint32_t *osh_prof_data(void)  { return g_prof; }
uint32_t        osh_prof_slots(void) { return PROF_SIZE / 2; }

/* The 68000 has a 24-bit address bus, so the top byte of an address is ignored: $ffff8800 and
 * $fffffc00 reach the same hardware as $ff8800 and $fffc00. Every hardware-address comparison below
 * masks with this first, so the idiom a game uses to reach a register cannot decide whether the
 * guard sees it. */
#define BUS_ADDR_MASK 0xffffffu

/* --- IKBD 6850 ACIA (keyboard/joystick), $fffffc00/02 -> 24-bit bus alias $fffc00/02 -----
 * read_joystick busy-waits on the status TDRE bit then sends a command; the joystick reply
 * arrives via an interrupt we don't run (input state is instead scripted as an image global —
 * see HARNESS.md). We model only what the traced code touches: the status reads back as "ready
 * to send" so the wait loop terminates. The command byte written to IKBD_DATA lands above the
 * image and is dropped by the bounds check like any other hardware write. */
#define IKBD_STATUS 0xfffc00
#define IKBD_TX_RDY 0x02        /* TDRE: transmit register empty */

/* --- PSG (YM2149) capture -----------------------------------------------------------
 * The sound driver talks to the PSG by writing a register number to $ff8800 (select
 * latch) then the value to $ff8802 (data). Those addresses sit above the 1 MiB image, so
 * the writes would otherwise vanish. Tap them here into an ordered (reg,val) log the sound
 * tools read after each REFRESH run — the register stream that drives a Python YM2149. */
#define PSG_SELECT 0xff8800   /* register-select latch (68000's 24-bit bus aliases $ffff8800) */
#define PSG_DATA   0xff8802   /* data port */
/* The ST decodes the YM2149 incompletely: it answers across the whole $ff8800..$ff88ff block, of
 * which the two addresses above are the canonical pair. The guards below cover the BLOCK, not the
 * pair — a driver reaching the chip through a mirror is using the direct path just as much, and
 * guarding only the pair would let it disarm the mixed-path check. */
#define PSG_BLOCK_END 0xff8900
#define MAX_PSG    4096
static uint8_t  g_psg_reg[MAX_PSG];
static uint8_t  g_psg_val[MAX_PSG];
static uint32_t g_psgn;        /* captured (reg,val) writes this run */
static uint8_t  g_psg_latch;   /* register selected by the last $ff8800 write */

/* Which of the two PSG paths this run used. The readable register file (os.h OS_PSG_REGS) is fed
 * by XBIOS Giaccess only — a direct $ff8800/$ff8802 access goes to the off-image ledger above (or,
 * for a read, is not modeled at all) and leaves the file stale — so a run that uses BOTH cannot be
 * served a correct Giaccess read. Rather than answer from a register file we know is out of date,
 * count the run unmodeled and let emu.run reject it with the diagnostic osh_psg_mixed_paths backs.
 * Joust reaches both (its sound driver calls Giaccess; its floppy routine at image 0x1553c selects
 * and rewrites PSG port A directly), so this is a live guard, not a hypothetical one. */
static uint32_t g_psg_direct;          /* direct $ff8800/$ff8802 accesses this run (any width) */
static uint32_t g_psg_giaccess_calls;  /* XBIOS Giaccess traps served this run */
int osh_psg_mixed_paths(void) { return g_psg_direct && g_psg_giaccess_calls; }

/* Direct PSG accesses the model cannot serve at all (counted separately from g_psg_direct, which
 * merely arms the mixed-path guard). osh_run rejects the whole run on either, rather than let it be
 * verified against a fabricated value. Two kinds:
 *   - ANY read of either port. Reading $ff8800 reads back the selected register on real hardware,
 *     and the ledger records writes only, so there is nothing correct to return: serving 0 forces a
 *     read-modify-write's preserved bits to zero (Joust's drive-select at image 0x15544 does
 *     exactly `move.b $ff8800,d1; move.b d1,d2; and.b #$f8,d1`) and a reconstruction of it could be
 *     "verified" against that fabricated 0. That rejection stands ALONE, so the enclosing floppy
 *     routine at 0x152dc can never be differentially verified — see TRAP_MODEL.md.
 *   - ANY OTHER access to the chip's address block. Only the BYTE protocol on the canonical pair
 *     (select latch, then data) is modeled — not the odd-address decoding a `move.w #$0e00,$ff8800`
 *     relies on, and not the mirrors. Tallying these is also what stops such an idiom from slipping
 *     past the byte callback's equality test and silently DISARMING the mixed-path guard. Neither
 *     game does it (Joust's three direct accesses are byte-sized and port-aligned; BuggyBoy reaches
 *     the ports by `lea` + byte ops), so the guard no longer rests on that property of the inputs. */
static uint32_t g_psg_unmodeled;

/* Does an access of `n` bytes at `a` fall in the YM2149's address block? */
static int psg_block_touched(uint32_t a, uint32_t n) {
    uint32_t lo = a & BUS_ADDR_MASK;               /* the 68000 aliases $ffff88xx to $ff88xx */
    return lo < PSG_BLOCK_END && lo + n > PSG_SELECT;
}

/* Tally a PSG access the model cannot serve (see g_psg_unmodeled). Callers reach this only after
 * the in-image fast path has missed, so it costs nothing on a normal access. */
static void psg_note_unmodeled(uint32_t a, uint32_t n) {
    if (!psg_block_touched(a, n)) return;
    g_psg_direct++;                                /* it is still a use of the direct path */
    g_psg_unmodeled++;
}

/* --- memory callbacks: big-endian, bounds-checked to the image --- */
unsigned int m68k_read_memory_8(unsigned int a) {
    if (a < g_size) return g_mem[a];
    if ((a & BUS_ADDR_MASK) == IKBD_STATUS) return IKBD_TX_RDY;
    psg_note_unmodeled(a, 1);
    return 0;                                      /* off-image, like any unmapped address */
}
unsigned int m68k_read_memory_16(unsigned int a) {
    if (a + 1 < g_size) return (unsigned)(g_mem[a] << 8 | g_mem[a + 1]);
    psg_note_unmodeled(a, 2);
    return 0;
}
unsigned int m68k_read_memory_32(unsigned int a) {
    if (a + 3 >= g_size) { psg_note_unmodeled(a, 4); return 0; }
    return (unsigned)(g_mem[a] << 24 | g_mem[a + 1] << 16 | g_mem[a + 2] << 8 | g_mem[a + 3]);
}

static void logw(uint32_t a) { if (g_wn < MAX_WRITES) g_waddr[g_wn++] = a; }

/* --- XBIOS Dosound (fn 0x20) side-effect ledger -------------------------------------------
 * Dosound hands the YM2149 a command list via A0; that pointer touches no RAM, so a wrong or
 * missing list is invisible to the image diff even when the call runs. Record each Dosound's
 * list pointer (the runtime A0 == a Ghidra image address) in an ordered ledger, reset per run
 * like the PSG tap. harness.differential compares it against the candidate's g_dosound ledger,
 * making the off-image A0 argument diff-verifiable (improvement #2). The cap is os.h's
 * OS_DOSOUND_LOG_MAX — the same one the candidate's ledger uses, so both truncate identically. */
static uint32_t g_dosound_arg[OS_DOSOUND_LOG_MAX];
static uint32_t g_dosound_n;
uint32_t        osh_dosound_count(void) { return g_dosound_n; }
const uint32_t *osh_dosound_args(void)  { return g_dosound_arg; }

void m68k_write_memory_8(unsigned int a, unsigned int v) {
    switch (a & BUS_ADDR_MASK) {                   /* mask to the 68000's 24-bit address bus */
        case PSG_SELECT: g_psg_direct++; g_psg_latch = (uint8_t)v & 0x0f; return;
        case PSG_DATA:
            g_psg_direct++;                            /* see the mixed-path guard in osh_run */
            if (g_psgn < MAX_PSG) {
                g_psg_reg[g_psgn] = g_psg_latch;
                g_psg_val[g_psgn] = (uint8_t)v;
                g_psgn++;
            }
            return;
    }
    if (a < g_size) { g_mem[a] = (uint8_t)v; logw(a); return; }
    psg_note_unmodeled(a, 1);   /* the odd aliases $ff8801/$ff8803, whose decoding is not modeled */
}
void m68k_write_memory_16(unsigned int a, unsigned int v) {
    if (a + 1 < g_size) { g_mem[a] = (uint8_t)(v >> 8); g_mem[a + 1] = (uint8_t)v; logw(a); logw(a + 1); return; }
    psg_note_unmodeled(a, 2);                      /* only the byte PSG protocol is modeled */
}
void m68k_write_memory_32(unsigned int a, unsigned int v) {
    if (a + 3 >= g_size) { psg_note_unmodeled(a, 4); return; }
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
static uint32_t g_malloc_n;     /* GEMDOS Malloc calls serviced this run (see osh_malloc_count) */
static uint32_t g_unmodeled;    /* count of traps whose real effect we do NOT model (fabricated D0) */
/* Traps serviced this run that REACH the harness-poked model state (see osh_poked_input_calls). The
 * six the project.toml waiver `tos_poked_input_unused` names: Bconstat, Bconin, Crawio, Random,
 * Giaccess, Kbdvbase. Reaching it, not reading it: a Giaccess WRITE stores into the register file
 * and Bconin clears the pending flag, and under the overlap those are writes over the game's own
 * code — worse than a read, not better. Sibling of g_malloc_n: it is the per-run witness that lets
 * emu.run() re-test a layout waiver's claim about the GAME instead of trusting it once at import. */
static uint32_t g_poked_input_calls;
static uint32_t g_min_a7;       /* lowest A7 (deepest stack pointer) reached this run */
static uint32_t g_ninsns;       /* instructions executed in the last osh_run (perf profiling) */
static uint64_t g_ncycles;      /* 68000 clock cycles executed in the last osh_run (perf profiling) */

/* Service the trap the CPU jumped to (vec = 1/2/13/14). Reads the exception frame at A7,
 * services the OS call, and returns control to the caller with D0 set. Calls we faithfully
 * model set `modeled`; anything else (an unmodeled GEM opcode, a non-console BIOS device, an
 * unstaged file, an unknown fn) is counted in g_unmodeled so the run can be rejected rather
 * than trusted against a fabricated result. */
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
            /* Count the CALL, not the bump: a zero/rounds-to-zero size (Malloc(-1), the "largest
             * free block?" query) is still fully serviced — it returns OS_HEAP_BASE — yet leaves
             * g_heap where it was. See osh_malloc_count. */
            g_malloc_n++;
            d0 = g_heap; g_heap += (m68k_read_memory_32(arg1) + 1u) & ~1u; break;
        case 0x20:                                    /* Super(stack): supervisor-mode token model */
            modeled = os_super(m68k_read_memory_32(arg1), &d0);
            break;
        case 0x3c: {                                  /* Fcreate(fname, attr) -> handle */
            int32_t h = os_fcreate(g_mem, m68k_read_memory_32(caller + 2));
            if (h < 0) modeled = 0; else d0 = (uint32_t)h;
            break;
        }
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
        case 0x40: {                                  /* Fwrite(handle, count, buf) -> bytes written */
            int32_t nwrote = os_fwrite(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                                       m68k_read_memory_32(caller + 4),
                                       m68k_read_memory_32(caller + 8));
            if (nwrote < 0) modeled = 0; else d0 = (uint32_t)nwrote;
            break;
        }
        case 0x3e:                                    /* Fclose(handle) */
            if (os_fclose(g_mem, (uint16_t)m68k_read_memory_16(caller + 2)) < 0) modeled = 0;
            break;
        case 0x49: case 0x4a:                         /* Mfree / Mshrink -> success */
        case 0x02: case 0x09: break;                  /* Cconout / Cconws -> no image effect */
        case 0x06: {                                  /* Crawio(w): raw console I/O, either way */
            uint16_t w = (uint16_t)m68k_read_memory_16(caller + 2);
            /* Only the READ direction looks at the poked console state; the write direction is a
             * character bound for the screen and touches nothing (os.h). Tallying it too would
             * redden a legitimate run for printing a character. */
            if (w == OS_CRAWIO_READ) g_poked_input_calls++;
            d0 = os_crawio(g_mem, w);
            break;
        }
        default: modeled = 0; break;                  /* Pterm, Dgetdrv, Pexec, unknown */
        }
    } else if (vec == 14) {                           /* XBIOS */
        switch (fn) {
        case 0x02: case 0x03: d0 = OS_SCREEN_BASE; break;   /* Physbase / Logbase */
        /* Kbdvbase hands the program a POINTER to poked state rather than reading it, but the claim
         * the tally serves is the same one: nothing in the game may reach that block. */
        case 0x22: g_poked_input_calls++; d0 = OS_KBDVBASE; break;   /* -> in-image KBDVBASE struct */
        case 0x11:                                    /* Random -> the harness-poked 24-bit value */
            g_poked_input_calls++;
            d0 = os_random(g_mem);
            break;
        case 0x1c:                                    /* Giaccess(data, reg): YM2149 read/write */
            g_psg_giaccess_calls++;
            g_poked_input_calls++;
            d0 = os_giaccess(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                             (uint16_t)m68k_read_memory_16(caller + 4));
            break;
        case 0x04:                                    /* Getrez -> low-res */
        case 0x05: case 0x06: case 0x07:              /* Setscreen / Setpalette / Setcolor */
        case 0x19:                                    /* Ikbdws: serial write to the IKBD, no image effect */
            break;
        case 0x20:                                    /* Dosound: writes the YM2149, no image effect */
            if (g_dosound_n < OS_DOSOUND_LOG_MAX)    /* log A0 (the command-list pointer) into the ledger */
                g_dosound_arg[g_dosound_n++] = m68k_read_memory_32(arg1);
            break;
        case 0x25: break;                             /* Vsync: waits for the VBL, no image effect */
        default: modeled = 0; break;                  /* unknown */
        }
    } else if (vec == 2) {                            /* GEM: AES/VDI parameter-block calls */
        uint32_t reg_d0 = m68k_get_reg(0, M68K_REG_D0);   /* subsystem: AES 0xc8 / VDI 0x73 */
        uint32_t reg_d1 = m68k_get_reg(0, M68K_REG_D1);   /* -> parameter block */
        modeled = os_gem_trap(g_mem, reg_d0, reg_d1);     /* results land in the param block */
    } else if (vec == 13) {                           /* BIOS: console input only (os.h) */
        uint16_t dev = (uint16_t)m68k_read_memory_16(caller + 2);
        switch (fn) {
        case 0x01: g_poked_input_calls++; modeled = os_bconstat(g_mem, dev, &d0); break;  /* Bconstat */
        case 0x02: g_poked_input_calls++; modeled = os_bconin(g_mem, dev, &d0); break;    /* Bconin */
        default: modeled = 0; break;                  /* Bconout, Setexc, Kbshift, unknown */
        }
    } else {
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
    g_malloc_n = 0;
    g_unmodeled = 0;
    g_poked_input_calls = 0;

    g_wn = 0;                             /* write-set = the function's writes only */
    g_psgn = 0;                           /* PSG capture = this run's register writes only */
    g_psg_latch = 0;                      /* ... and its select latch, or run N's (reg,val) pairs
                                           * would be attributed to run N-1's last selected
                                           * register, making a -n auto suite order-dependent */
    g_psg_direct = 0;                     /* all three PSG tallies are per-run (the guards below) */
    g_psg_giaccess_calls = 0;
    g_psg_unmodeled = 0;
    g_dosound_n = 0;                      /* Dosound ledger = this run's XBIOS Dosound calls only */
    g_min_a7 = sp;                        /* deepest stack pointer (for exclude-band sanity checks) */
    uint32_t n = 0;
    g_ncycles = 0;                                  /* 68000 cycle tally = this run's game code only */
    for (; n < max_insns; n++) {
        uint32_t pc = m68k_get_reg(0, M68K_REG_PC);
        if (pc == sentinel || (stop_pc && pc == stop_pc)) break;
        if (g_cov_on && pc < COV_SIZE) g_cov[pc >> 3] |= (uint8_t)(1u << (pc & 7));   /* coverage */
        uint32_t cur_a7 = m68k_get_reg(0, M68K_REG_A7);
        if (cur_a7 < g_min_a7) g_min_a7 = cur_a7;
        if      (pc == MAGIC_GEMDOS) handle_trap(1);
        else if (pc == MAGIC_XBIOS)  handle_trap(14);
        else if (pc == MAGIC_BIOS)   handle_trap(13);
        else if (pc == MAGIC_GEM)    handle_trap(2);
        else                         g_ncycles += (uint32_t)m68k_execute(1);   /* one insn; tally its cycles */
    }
    g_ninsns = n;                                   /* instruction count for perf profiling */
    /* The two PSG rejections are NOT folded into g_unmodeled: emu.run tests all three counters and
     * names every cause that applies, so a run that both mixes the PSG paths and makes an unmodeled
     * OS call reports both rather than sending the reader after one of them twice. */
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

/* Benchmark a cross-compiled C function (our reconstruction, built to m68k and loaded into `mem` at
 * its link addresses) — for comparing the reconstruction's on-target cycle cost against the original
 * (osh_run). Unlike osh_run this installs NO OS-trap vectors: the target is pure computation over the
 * image pointer, and those vectors sit inside the reconstruction's own .text (linked at base 0), so
 * writing them would corrupt code. `arg0` is the single 32-bit C argument, placed at 4(sp) per the
 * m68k SysV ABI; `sentinel` is the return address (an even PC outside the loaded code). Reports cycles
 * + instructions via the shared osh_num_* getters. Returns 1 if it returned to the sentinel. */
int osh_run_bench(uint8_t *mem, uint32_t size, uint32_t entry, uint32_t arg0,
                  uint32_t sp, uint32_t sentinel, uint32_t max_insns, uint32_t *out_regs) {
    g_mem = mem; g_size = size;
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_pulse_reset();
    m68k_set_reg(M68K_REG_A7, sp);
    m68k_set_reg(M68K_REG_PC, entry);
    m68k_write_memory_32(sp, sentinel);       /* return address: rts -> sentinel */
    m68k_write_memory_32(sp + 4, arg0);       /* first C argument (the image pointer) */
    g_min_a7 = sp;

    uint32_t n = 0;
    g_ncycles = 0;
    for (; n < max_insns; n++) {
        uint32_t pc = m68k_get_reg(0, M68K_REG_PC);
        if (pc == sentinel) break;
        uint32_t cur_a7 = m68k_get_reg(0, M68K_REG_A7);
        if (cur_a7 < g_min_a7) g_min_a7 = cur_a7;
        uint32_t cyc = (uint32_t)m68k_execute(1);
        g_ncycles += cyc;
        if (g_prof_on && pc < PROF_SIZE) g_prof[pc >> 1] += cyc;
    }
    g_ninsns = n;
    out_regs[0] = m68k_get_reg(0, M68K_REG_D0);
    return m68k_get_reg(0, M68K_REG_PC) == sentinel;
}

uint32_t        osh_num_writes(void)  { return g_wn; }
const uint32_t *osh_write_addrs(void) { return g_waddr; }
uint32_t        osh_unmodeled(void)   { return g_unmodeled; }
uint32_t        osh_min_a7(void)      { return g_min_a7; }
/* The Malloc bump pointer left by the last osh_run — diagnostics only (how far the heap grew). */
uint32_t        osh_heap(void)        { return g_heap; }
/* How many GEMDOS Malloc calls the last osh_run serviced. This, NOT the bump pointer, is what
 * "did this run allocate?" means: a serviced Malloc whose rounded size is 0 hands back a block at
 * OS_HEAP_BASE without moving g_heap, so a pointer comparison would miss it. emu.run() keys the
 * heap-over-program guard on this count (see emu._vet_no_malloc_over_program). */
uint32_t        osh_malloc_count(void) { return g_malloc_n; }
/* How many traps the last osh_run serviced that reached the harness-poked model state. emu.run() keys
 * the poked-input-over-program guard on this count (see emu._vet_no_poked_input_read), the same way
 * it keys the heap guard on osh_malloc_count: both waivers claim something about the GAME, so both
 * are re-tested per run rather than trusted once. */
uint32_t        osh_poked_input_calls(void) { return g_poked_input_calls; }
uint32_t        osh_num_insns(void)   { return g_ninsns; }
uint64_t        osh_num_cycles(void)  { return g_ncycles; }
uint32_t        osh_psg_count(void)   { return g_psgn; }
/* Direct PSG accesses the model refused this run — emu.run names them in its diagnostic. */
uint32_t        osh_psg_unmodeled(void) { return g_psg_unmodeled; }
const uint8_t  *osh_psg_regs(void)    { return g_psg_reg; }
const uint8_t  *osh_psg_vals(void)    { return g_psg_val; }
const uint8_t  *osh_cov_data(void)    { return g_cov; }          /* the visited-PC bitset (for merge) */
uint32_t        osh_cov_bytes(void)   { return sizeof g_cov; }
