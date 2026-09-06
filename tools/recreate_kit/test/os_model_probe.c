/* os_model_probe.c — the fixture behind test_os_model.py.
 *
 * The model surfaces of TRAP_MODEL.md's Phases 11-13 — the raster core, the VDI/AES opcodes, the
 * off-image OS event ledger, GEMDOS's console and Fseek, and the candidate's Malloc arena — each
 * have a side on each shore: the
 * ORACLE reaches it from `oracle/shim.c`'s `trap #2` dispatch, and a RECONSTRUCTION reaches it
 * through `os.h`'s `os_vdi()` / `os_gem_trap()` wrappers. Both call the same `src/gem.c`, so the
 * property worth pinning is not that two transcriptions agree but that the two DOORS do: the trap
 * decode, the refusal routing and the two ledgers are per-side code, and only a probe driving both
 * in one process can compare them. Same obstacle as psg_model_probe.c — this directory binds no
 * project, so `harness`/`emu` are unreachable here.
 *
 * It also prints raw raster BYTES for the raster cases rather than pixel colours, because the
 * interleaved plane addressing is half of what the model is: a self-consistently WRONG addressing
 * would reproduce its own pixels perfectly and only the bytes give the Python reference something
 * independent to disagree with.
 *
 * Output is the three line kinds probe_build.run_probe parses, all owned by the Python side (a case
 * printed without a claim there fails loudly):
 *   K <case> <key> <value>       a scalar (an output word, a tally, a state field)
 *   L <case> <index> <kind> <val> one ordered OS event ledger entry
 *   F <case> <index> <byte>      one byte of a raster window, in address order
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "os.h"
#include "raster.h"
#include "probe_common.h"   /* osh_run and the code planters; see its header for what it pins */

/* oracle/shim.c ships no header (Python binds it by ctypes); its ledger accessors are declared here
 * exactly as psg_model_probe.c declares the ones it reads. */
uint32_t        osh_event_count(void);
const uint16_t *osh_event_kinds(void);
const uint32_t *osh_event_values(void);
uint32_t        osh_unmodeled(void);
uint32_t        osh_poked_input_calls(void);

/* ...and the CANDIDATE's ledger accessors (src/os_log.c). os.h declares only the recording side,
 * because the harness reads these three by ctypes and no C caller has ever needed them. */
void            g_os_event_reset(void);
uint32_t        g_os_event_count(void);
const uint16_t *g_os_event_kinds(void);
const uint32_t *g_os_event_values(void);

/* ---- the probe's own image geometry ----------------------------------------------------------
 * NOT probe_common.h's: the model bounds its copies against OS_IMAGE_SIZE, so the image must be
 * that long or an in-range address would run off a shorter buffer; and OS_SCREEN_BASE is 0x8000,
 * which is exactly where probe_common.h puts its stack. */
#define PROBE_STACK      0x7000u    /* below the screen, above the poked block, grows down */
#define PROBE_MAX_INSNS  64u        /* every planted routine is a handful of instructions */

/* The two off-screen rasters the raster cases copy between: 16x16, four planes, one word per row. */
#define RASTER_SIDE      16
#define RASTER_WDW       1
#define RASTER_ROW_BYTES (RASTER_WDW * 2 * OS_SCREEN_PLANES)
#define RASTER_TOTAL     (RASTER_SIDE * RASTER_ROW_BYTES)
#define SRC_RASTER       0x20000u
#define DST_RASTER       0x21000u

/* The VDI parameter block and its five arrays, and the AES's own — the two subsystems index their
 * blocks differently (VDI ptsin and AES intin are both slot 2), so one block cannot serve both. */
#define PBLK    0x30000u
#define APBLK   0x30d00u
#define CONTRL  0x30100u
#define INTIN   0x30200u
#define PTSIN   0x30400u
#define INTOUT  0x30600u
#define PTSOUT  0x30800u
#define MFDB_SRC 0x30a00u
#define MFDB_DST 0x30a40u
#define CCONWS_STRING 0x30b00u
#define CCONWS_TAIL_BYTES 8u   /* the unterminated string, laid at the image's end */

/* The framebuffer's length, and the CANARY bands either side of it. A fill whose rectangle runs off
 * the top or the bottom of the screen writes OUTSIDE the framebuffer — still inside the image, so
 * nothing faults and no window of the screen would ever show it. The bands are sized for the worst
 * case the cases below ask for (a rectangle reaching y = 250 lands 8,160 bytes past the end). */
#define SCREEN_BYTES   (OS_SCREEN_W * OS_SCREEN_H * OS_SCREEN_PLANES / 8)
#define CANARY_BEFORE  1024u
#define CANARY_AFTER   16384u
#define CANARY_FILL    0x5a

/* contrl is eleven words; the arrays are sized well past anything the model writes. */
#define CONTRL_WORDS 11

/* The v_opnvwk work_out entry the model fills in besides the two extents (gem.c's own name for it),
 * one it does NOT fill, and the byte both arrays are pre-filled with so that "left as the caller
 * had it" and "written as zero" are different answers. */
#define WORK_OUT_COLOURS  13
#define WORK_OUT_UNFILLED  5
#define WORK_OUT_CANARY 0x5a

/* 68000 encodings the trap cases plant. */
#define OP_MOVE_W_IMM_PUSH 0x3f3cu   /* move.w #imm,-(sp)   */
#define OP_MOVE_L_IMM_PUSH 0x2f3cu   /* move.l #imm32,-(sp) */
#define OP_MOVE_L_IMM_D1   0x223cu   /* move.l #imm32,d1    */
#define OP_MOVE_W_IMM_D0   0x303cu   /* move.w #imm,d0      */
#define OP_ADDA_W_IMM_SP   0xdefcu   /* adda.w #imm,sp      */
#define OP_TRAP_GEMDOS     0x4e41u   /* trap #1  */
#define OP_TRAP_GEM        0x4e42u   /* trap #2  */
#define OP_TRAP_BIOS       0x4e4du   /* trap #13 */

/* GEMDOS/BIOS selectors the trap cases use. */
#define GEMDOS_CCONOUT 0x02
#define GEMDOS_CRAWCIN 0x07
#define GEMDOS_CNECIN  0x08
#define GEMDOS_CCONWS  0x09
#define GEMDOS_CCONIS  0x0b
#define GEMDOS_CRAWIO  0x06
#define CRAWIO_WRITE_CHAR 'Z'        /* any word but OS_CRAWIO_READ is a character to print */
/* The staged keystrokes, in TOS's scancode << 16 | ascii shape. */
#define CONSOLE_KEY_A  0x00230061u
#define CONSOLE_WALK_0 0x00110071u   /* 'q' */
#define CONSOLE_WALK_1 0x00120077u   /* 'w' */
#define CONSOLE_WALK_2 0x00130065u   /* 'e' */
#define GEMDOS_FSEEK   0x42
#define BIOS_BCONOUT   0x03
#define GEMDOS_MALLOC  0x48
/* An ODD size and an even one, so the round-up to a word is visible in the second block's address. */
#define MALLOC_FIRST_SIZE  5u
#define MALLOC_SECOND_SIZE 8u
#define MALLOC_MOVED_BASE  0x40000u  /* a base nothing else here uses, for the rewind case */

/* A parameter-block pointer near the top of the address space: `base + index * 2` WRAPS in 32-bit
 * arithmetic and lands back in low memory. The canary is the band it would land in. */
#define WRAPPING_POINTER   0xfffffffeu
#define WRAP_CANARY        0x3c
#define WRAP_CANARY_BYTES  32u
#define BIOS_DEV_CONSOLE 2           /* a device Bconout does NOT model: the refusal case */

/* The staged file the Fseek case seeks in. */
#define FS_NAME_ADDR  0x30c00u
#define FS_FILE_BYTES 8u
#define FS_CAPACITY   16u

static uint32_t g_out_regs[OUT_REGS];

/* ---- planting and reading words -------------------------------------------------------------- */
static void put16(uint32_t addr, uint16_t value) { wr16(g_image + addr, value); }
static void put32(uint32_t addr, uint32_t value) { wr32(g_image + addr, value); }
static uint16_t get16(uint32_t addr) { return be16(g_image + addr); }

static void contrl_word(int index, uint16_t value) { put16(CONTRL + (uint32_t)index * 2, value); }
static uint16_t contrl_read(int index) { return get16(CONTRL + (uint32_t)index * 2); }
static void intin_word(int index, uint16_t value) { put16(INTIN + (uint32_t)index * 2, value); }
static void ptsin_word(int index, uint16_t value) { put16(PTSIN + (uint32_t)index * 2, value); }
static uint16_t intout_read(int index) { return get16(INTOUT + (uint32_t)index * 2); }
static uint16_t ptsout_read(int index) { return get16(PTSOUT + (uint32_t)index * 2); }
static uint16_t vdi_state_read(int field) { return get16(OS_VDI_STATE + (uint32_t)field); }

/* ---- reporting ------------------------------------------------------------------------------- */
static void report_scalar(const char *name, const char *key, uint32_t value) {
    printf("K %s %s %u\n", name, key, value);
}

/* The candidate's ledger (src/os_log.c) or the oracle's (shim.c), by whichever accessor the caller
 * hands over — one printer, so the two sides cannot be reported in different shapes. */
static void report_ledger(const char *name, uint32_t count,
                          const uint16_t *kinds, const uint32_t *values) {
    report_scalar(name, "events", count);
    for (uint32_t i = 0; i < count; i++)
        printf("L %s %u %u %u\n", name, i, kinds[i], values[i]);
}

static void report_candidate_ledger(const char *name) {
    report_ledger(name, g_os_event_count(), g_os_event_kinds(), g_os_event_values());
}

/* A rectangular WORD window of a raster, in address order: `nrows` rows starting at `row0`, each
 * `nwords` interleaved 16-pixel columns starting at `word0`. */
static void report_window(const char *name, uint32_t base, int wdwidth, int nplanes,
                          int row0, int nrows, int word0, int nwords) {
    int row_bytes = wdwidth * 2 * nplanes, word_bytes = 2 * nplanes, index = 0;
    for (int row = 0; row < nrows; row++)
        for (int byte = 0; byte < nwords * word_bytes; byte++)
            printf("F %s %d %u\n", name, index++,
                   g_image[base + (uint32_t)((row0 + row) * row_bytes + word0 * word_bytes + byte)]);
}

static void report_raster(const char *name, uint32_t base) {
    report_window(name, base, RASTER_WDW, OS_SCREEN_PLANES, 0, RASTER_SIDE, 0, RASTER_WDW);
}

/* ---- the image every case starts from --------------------------------------------------------- */

/* A deterministic, documented fill: byte i of the raster at `base` is (i * step + seed) & 0xff. The
 * Python side never reproduces it — every case PRINTS the bytes it used — so this only has to be
 * varied enough that a wrong plane or a wrong row shows up. */
static void fill_raster(uint32_t base, uint8_t seed, uint8_t step) {
    for (int i = 0; i < RASTER_TOTAL; i++)
        g_image[base + (uint32_t)i] = (uint8_t)(i * step + seed);
}

static void image_reset(void) {
    memset(g_image, 0, OS_IMAGE_SIZE);
    put32(PBLK + VDI_PB_CONTRL * 4, CONTRL);
    put32(PBLK + VDI_PB_INTIN * 4, INTIN);
    put32(PBLK + VDI_PB_PTSIN * 4, PTSIN);
    put32(PBLK + VDI_PB_INTOUT * 4, INTOUT);
    put32(PBLK + VDI_PB_PTSOUT * 4, PTSOUT);
    put32(APBLK + AES_PB_CONTRL * 4, CONTRL);
    put32(APBLK + AES_PB_INTIN * 4, INTIN);
    put32(APBLK + AES_PB_INTOUT * 4, INTOUT);
    g_os_event_reset();
    g_os_refusal_reset();
}

/* v_opnvwk's work_in: eleven words, of which the model keeps intin[6..9]. Every entry is 1 —
 * Bubble Ghost's own call, the only real one in this workspace — but for [10], which selects raster
 * coordinates, and the four the caller names. */
#define WORK_IN_ENTRIES     11
#define WORK_IN_COORD_TYPE  10
#define WORK_IN_RASTER_COORDS 2
#define WORK_IN_DEFAULT      1

static void write_work_in(uint16_t text_colour, uint16_t interior, uint16_t style,
                          uint16_t fill_colour) {
    for (int i = 0; i < WORK_IN_ENTRIES; i++) intin_word(i, WORK_IN_DEFAULT);
    intin_word(WORK_IN_COORD_TYPE, WORK_IN_RASTER_COORDS);
    intin_word(VDI_WORK_IN_TEXT_COLOR, text_colour);
    intin_word(VDI_WORK_IN_FILL_INTERIOR, interior);
    intin_word(VDI_WORK_IN_FILL_STYLE, style);
    intin_word(VDI_WORK_IN_FILL_COLOR, fill_colour);
    contrl_word(VDI_CONTRL_INTIN_N, WORK_IN_ENTRIES);
}

/* ...and the workstation an attribute or drawing case runs against. SOLID, because every drawing
 * case below means to paint in the fill colour, and a hollow interior paints colour 0. */
static void open_workstation(void) {
    write_work_in(OS_VDI_DEFAULT_TEXT_COLOR, VDI_FILL_SOLID, OS_VDI_DEFAULT_FILL_STYLE,
                  OS_VDI_DEFAULT_FILL_COLOR);
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_OPNVWK);
    os_vdi(g_image, PBLK);
    memset(g_image + CONTRL, 0, CONTRL_WORDS * 2);
    memset(g_image + INTIN, 0, WORK_IN_ENTRIES * 2);
}

static void set_canaries(void) {
    memset(g_image + OS_SCREEN_BASE - CANARY_BEFORE, CANARY_FILL, CANARY_BEFORE);
    memset(g_image + OS_SCREEN_BASE + SCREEN_BYTES, CANARY_FILL, CANARY_AFTER);
}

static uint32_t canary_damage(void) {
    uint32_t damaged = 0;
    for (uint32_t i = 0; i < CANARY_BEFORE; i++)
        damaged += g_image[OS_SCREEN_BASE - CANARY_BEFORE + i] != CANARY_FILL;
    for (uint32_t i = 0; i < CANARY_AFTER; i++)
        damaged += g_image[OS_SCREEN_BASE + SCREEN_BYTES + i] != CANARY_FILL;
    return damaged;
}

/* Set one attribute through the VDI and clear the parameter block behind it. */
static void set_attribute(uint16_t opcode, uint16_t value) {
    contrl_word(VDI_CONTRL_OPCODE, opcode);
    contrl_word(VDI_CONTRL_INTIN_N, 1);
    intin_word(0, value);
    os_vdi(g_image, PBLK);
    memset(g_image + CONTRL, 0, CONTRL_WORDS * 2);
}

/* Fill ptsin[0..3], reporting whether the model served the call. */
static int recfl(int x1, int y1, int x2, int y2) {
    contrl_word(VDI_CONTRL_OPCODE, VDI_VR_RECFL);
    contrl_word(VDI_CONTRL_PTSIN_N, 2);
    ptsin_word(0, (uint16_t)x1); ptsin_word(1, (uint16_t)y1);
    ptsin_word(2, (uint16_t)x2); ptsin_word(3, (uint16_t)y2);
    return os_vdi(g_image, PBLK);
}

/* How many pixels of the whole screen are not colour 0. */
static uint32_t screen_pixels_set(void) {
    raster_t screen = {OS_SCREEN_BASE, OS_SCREEN_W, OS_SCREEN_H, OS_SCREEN_WDWIDTH,
                       OS_SCREEN_PLANES};
    uint32_t set = 0;
    for (int32_t y = 0; y < OS_SCREEN_H; y++)
        for (int32_t x = 0; x < OS_SCREEN_W; x++)
            set += raster_pixel(g_image, &screen, x, y) != 0;
    return set;
}

/* One vr_recfl under a named fill INTERIOR, reported as the number of non-zero PIXELS the whole
 * screen ends up holding plus the canary damage either side of it — the two halves of "the fill
 * covered exactly the part of the rectangle that fits". */
static void recfl_case(const char *name, int x1, int y1, int x2, int y2, uint16_t colour,
                       uint16_t interior) {
    image_reset();
    open_workstation();
    set_attribute(VDI_VSF_COLOR, colour);
    set_attribute(VDI_VSF_INTERIOR, interior);
    set_canaries();
    report_scalar(name, "modeled", (uint32_t)recfl(x1, y1, x2, y2));
    report_scalar(name, "pixels_set", screen_pixels_set());
    report_scalar(name, "canary_damage", canary_damage());
}

static void mfdb_write(uint32_t mfdb, uint32_t addr, uint16_t stand) {
    put32(mfdb + MFDB_ADDR, addr);
    put16(mfdb + MFDB_W, RASTER_SIDE);
    put16(mfdb + MFDB_H, RASTER_SIDE);
    put16(mfdb + MFDB_WDWIDTH, RASTER_WDW);
    put16(mfdb + MFDB_STAND, stand);
    put16(mfdb + MFDB_NPLANES, OS_SCREEN_PLANES);
}

/* ---- the raster cases ------------------------------------------------------------------------- */

/* One vro_cpyfm: source rectangle (sx1,sy1)-(sx2,sy2) onto the destination anchor (dx,dy) under
 * `op`. Prints the source, the destination BEFORE and the destination AFTER, so the Python
 * reference works from the bytes the model actually saw. */
static void cpyfm_case(const char *name, uint32_t src_raster, int op, int sx1, int sy1,
                       int sx2, int sy2, int dx, int dy) {
    char label[64];
    image_reset();
    open_workstation();
    fill_raster(SRC_RASTER, (uint8_t)(0x37 + op), 0x51);
    fill_raster(DST_RASTER, (uint8_t)(0x11 * op + 5), 0x2f);
    mfdb_write(MFDB_SRC, src_raster, 0);
    mfdb_write(MFDB_DST, DST_RASTER, 0);
    snprintf(label, sizeof label, "%s_src", name);
    report_raster(label, src_raster);
    snprintf(label, sizeof label, "%s_in", name);
    report_raster(label, DST_RASTER);

    contrl_word(VDI_CONTRL_OPCODE, VDI_VRO_CPYFM);
    contrl_word(VDI_CONTRL_PTSIN_N, 4);
    contrl_word(VDI_CONTRL_INTIN_N, 1);
    contrl_word(VDI_CONTRL_SRC_MFDB, (uint16_t)(MFDB_SRC >> 16));
    contrl_word(VDI_CONTRL_SRC_MFDB + 1, (uint16_t)MFDB_SRC);
    contrl_word(VDI_CONTRL_DST_MFDB, (uint16_t)(MFDB_DST >> 16));
    contrl_word(VDI_CONTRL_DST_MFDB + 1, (uint16_t)MFDB_DST);
    intin_word(0, (uint16_t)op);
    ptsin_word(0, (uint16_t)sx1); ptsin_word(1, (uint16_t)sy1);
    ptsin_word(2, (uint16_t)sx2); ptsin_word(3, (uint16_t)sy2);
    ptsin_word(4, (uint16_t)dx);  ptsin_word(5, (uint16_t)dy);

    report_scalar(name, "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar(name, "op", (uint32_t)op);
    report_scalar(name, "refusals", g_os_refusal_count());
    snprintf(label, sizeof label, "%s_out", name);
    report_raster(label, DST_RASTER);
}

/* ---- the text and fill cases ------------------------------------------------------------------
 * Both draw on the SCREEN, whose 32,000 bytes are far too many to print, so each reports a window
 * around what it drew — before and after, so the reference has the same starting bytes. */
#define TEXT_X 16                 /* word-aligned, so the window is one 16-pixel column wide */
#define TEXT_BASELINE 40
#define TEXT_WINDOW_WORDS 2       /* two characters, eight pixels each */
#define TEXT_WINDOW_ROWS RASTER_FONT_H
#define TEXT_COLOUR 5

/* The rectangle the fill-interior cases paint, inside the reported window. */
#define RECFL_X1 18
#define RECFL_Y1 (TEXT_BASELINE + 1)
#define RECFL_X2 40
#define RECFL_Y2 (TEXT_BASELINE + 4)

static void report_screen_window(const char *name, int row0, int nrows, int word0, int nwords) {
    report_window(name, OS_SCREEN_BASE, OS_SCREEN_WDWIDTH, OS_SCREEN_PLANES,
                  row0, nrows, word0, nwords);
}

static void gtext(const char *text, int x, int baseline) {
    int n = 0;
    for (const char *c = text; *c; c++) intin_word(n++, (uint8_t)*c);
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_GTEXT);
    contrl_word(VDI_CONTRL_PTSIN_N, 1);
    contrl_word(VDI_CONTRL_INTIN_N, (uint16_t)n);
    ptsin_word(0, (uint16_t)x);
    ptsin_word(1, (uint16_t)baseline);
    os_vdi(g_image, PBLK);
}

/* ---- the trap cases ---------------------------------------------------------------------------
 * Each plants `<pushes> trap #N ; adda.w #<pushed>,sp ; rts` at PROBE_ENTRY and runs it through the
 * oracle, so what is exercised is shim.c's own decode of the stack frame — the half of the model
 * that os.h's wrappers do not share. */
static uint32_t plant_push_word(uint32_t pc, uint16_t value) {
    plant_word(pc, OP_MOVE_W_IMM_PUSH);
    plant_word(pc + 2, value);
    return pc + 4;
}

static uint32_t plant_push_long(uint32_t pc, uint32_t value) {
    plant_word(pc, OP_MOVE_L_IMM_PUSH);
    return plant_long(pc + 2, value);
}

static uint32_t plant_trap(uint32_t pc, uint16_t trap_opcode, uint16_t pushed_bytes) {
    plant_word(pc, trap_opcode);
    plant_word(pc + 2, OP_ADDA_W_IMM_SP);
    plant_word(pc + 4, pushed_bytes);
    plant_rts(pc + 6);
    return pc + 8;
}

/* Run whatever was planted, and report D0 plus the oracle's unmodeled tally and event ledger. */
static void run_trap_case(const char *name) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0};
    int reached = osh_run(g_image, OS_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs, PROBE_STACK,
                          PROBE_SENTINEL, 0, PROBE_MAX_INSNS, g_out_regs);
    report_scalar(name, "reached", (uint32_t)reached);
    report_scalar(name, "d0", g_out_regs[0]);
    report_scalar(name, "unmodeled", osh_unmodeled());
    /* Every serviced VDI call reaches the VDI state block, which lives in the harness-poked region,
     * so shim.c tallies it exactly as it tallies a Bconin. Nothing else pins that bump: a
     * differential can only see it through a project's own layout waiver. */
    report_scalar(name, "poked_input_calls", osh_poked_input_calls());
    report_ledger(name, osh_event_count(), osh_event_kinds(), osh_event_values());
}

/* `move.l #pblk,d1 ; move.w #subsys,d0 ; trap #2 ; rts` at PROBE_ENTRY — the glue a GEM binding
 * emits, so what the trap cases exercise is shim.c's own decode of D0/D1. */
static void plant_gem_trap(uint32_t pblk, uint16_t subsystem) {
    plant_word(PROBE_ENTRY, OP_MOVE_L_IMM_D1);
    uint32_t pc = plant_long(PROBE_ENTRY + 2, pblk);
    plant_word(pc, OP_MOVE_W_IMM_D0);
    plant_word(pc + 2, subsystem);
    plant_trap(pc + 4, OP_TRAP_GEM, 0);
}

/* One GEMDOS call with the given word arguments, pushed right to left as a C binding does. */
static void gemdos_trap_case(const char *name, uint16_t selector, const uint16_t *args, int nargs) {
    uint32_t pc = PROBE_ENTRY;
    for (int i = nargs - 1; i >= 0; i--) pc = plant_push_word(pc, args[i]);
    pc = plant_push_word(pc, selector);
    plant_trap(pc, OP_TRAP_GEMDOS, (uint16_t)(2 + nargs * 2));
    run_trap_case(name);
}

/* ---- THE TWO DOORS ONTO ONE MODEL, opcode by opcode -------------------------------------------
 * `src/gem.c` is one implementation, so what can differ between the oracle and a reconstruction is
 * the DOOR: shim.c's `trap #2` decode against os.h's `os_gem_trap()` wrapper, plus each side's own
 * refusal routing and its own event ledger. Every modeled opcode is run through both, from the same
 * starting state, and what each wrote is compared.
 *
 * The whole image cannot be compared — the trap door plants 68000 code and pushes a stack frame —
 * so the comparison is over every band the MODEL may write, named here. */
static const struct { uint32_t addr; uint32_t bytes; } DOOR_BANDS[] = {
    {CONTRL, CONTRL_WORDS * 2},
    {INTOUT, OS_VDI_WORK_OUT_INTS * 2},
    {PTSOUT, OS_VDI_WORK_OUT_POINTS * 2 * 2},
    {OS_VDI_STATE, OS_VDI_STATE_BYTES},
    {OS_SCREEN_BASE, SCREEN_BYTES},
    {SRC_RASTER, RASTER_TOTAL},
    {DST_RASTER, RASTER_TOTAL},
};
#define DOOR_BAND_COUNT (sizeof DOOR_BANDS / sizeof DOOR_BANDS[0])

static uint32_t door_band_bytes(void) {
    uint32_t total = 0;
    for (unsigned i = 0; i < DOOR_BAND_COUNT; i++) total += DOOR_BANDS[i].bytes;
    return total;
}

static void door_snapshot(uint8_t *into) {
    for (unsigned i = 0; i < DOOR_BAND_COUNT; i++) {
        memcpy(into, g_image + DOOR_BANDS[i].addr, DOOR_BANDS[i].bytes);
        into += DOOR_BANDS[i].bytes;
    }
}

static uint32_t door_bytes_differing(const uint8_t *from) {
    uint32_t differing = 0;
    for (unsigned i = 0; i < DOOR_BAND_COUNT; i++) {
        for (uint32_t byte = 0; byte < DOOR_BANDS[i].bytes; byte++)
            differing += g_image[DOOR_BANDS[i].addr + byte] != *from++;
    }
    return differing;
}

/* One opcode's whole parameter block, as a table row rather than as a setup function: every modeled
 * call is at most a handful of intin and ptsin words, and a row per opcode is what makes "run the
 * WHOLE table through both doors" a loop instead of a list somebody can forget to extend. */
#define DOOR_MAX_INTIN 11        /* v_opnvwk's work_in is the longest */
#define DOOR_MAX_PTSIN 6         /* vro_cpyfm's two rectangles */
struct door_case {
    const char *name;
    uint32_t subsystem;                       /* GEM_VDI or GEM_AES */
    uint16_t opcode;
    int n_intin, n_ptsin;
    uint16_t intin[DOOR_MAX_INTIN];
    int16_t  ptsin[DOOR_MAX_PTSIN];
    int wants_mfdb;                           /* vro_cpyfm names two rasters in contrl[7..10] */
};

/* Lay one row into the block, on an image already reset and a workstation already open. */
static void door_setup(const struct door_case *door) {
    contrl_word(VDI_CONTRL_OPCODE, door->opcode);
    contrl_word(VDI_CONTRL_INTIN_N, (uint16_t)door->n_intin);
    contrl_word(VDI_CONTRL_PTSIN_N, (uint16_t)(door->n_ptsin / 2));
    for (int i = 0; i < door->n_intin; i++) intin_word(i, door->intin[i]);
    for (int i = 0; i < door->n_ptsin; i++) ptsin_word(i, (uint16_t)door->ptsin[i]);
    if (!door->wants_mfdb) return;
    fill_raster(SRC_RASTER, 0x37, 0x51);
    fill_raster(DST_RASTER, 0x05, 0x2f);
    mfdb_write(MFDB_SRC, SRC_RASTER, 0);
    mfdb_write(MFDB_DST, DST_RASTER, 0);
    contrl_word(VDI_CONTRL_SRC_MFDB, (uint16_t)(MFDB_SRC >> 16));
    contrl_word(VDI_CONTRL_SRC_MFDB + 1, (uint16_t)MFDB_SRC);
    contrl_word(VDI_CONTRL_DST_MFDB, (uint16_t)(MFDB_DST >> 16));
    contrl_word(VDI_CONTRL_DST_MFDB + 1, (uint16_t)MFDB_DST);
}

static void door_case(const struct door_case *door, uint8_t *snapshot) {
    char label[64];
    uint32_t pblk = door->subsystem == GEM_VDI ? PBLK : APBLK;

    /* Door one: the oracle's `trap #2`. */
    image_reset();
    open_workstation();
    door_setup(door);
    plant_gem_trap(pblk, (uint16_t)door->subsystem);
    snprintf(label, sizeof label, "%s_trap", door->name);
    run_trap_case(label);
    door_snapshot(snapshot);

    /* Door two: os.h's wrapper, on the same starting state. */
    image_reset();
    open_workstation();
    door_setup(door);
    snprintf(label, sizeof label, "%s_direct", door->name);
    report_scalar(label, "modeled", (uint32_t)os_gem_trap(g_image, door->subsystem, pblk));
    report_scalar(label, "refusals", g_os_refusal_count());
    report_scalar(label, "differing_bytes", door_bytes_differing(snapshot));
    report_candidate_ledger(label);
}

static const struct door_case DOOR_CASES[] = {
    {"door_v_clrwk",      GEM_VDI, VDI_V_CLRWK,      0, 0, {0}, {0}, 0},
    {"door_v_gtext",      GEM_VDI, VDI_V_GTEXT,      2, 2, {'H', 'i'}, {TEXT_X, TEXT_BASELINE}, 0},
    {"door_vst_height",   GEM_VDI, VDI_VST_HEIGHT,   0, 2, {0}, {0, 6}, 0},
    {"door_vst_color",    GEM_VDI, VDI_VST_COLOR,    1, 0, {13}, {0}, 0},
    {"door_vsf_interior", GEM_VDI, VDI_VSF_INTERIOR, 1, 0, {VDI_FILL_SOLID}, {0}, 0},
    {"door_vsf_style",    GEM_VDI, VDI_VSF_STYLE,    1, 0, {4}, {0}, 0},
    {"door_vsf_color",    GEM_VDI, VDI_VSF_COLOR,    1, 0, {9}, {0}, 0},
    {"door_vswr_mode",    GEM_VDI, VDI_VSWR_MODE,    1, 0, {2}, {0}, 0},
    {"door_v_opnvwk",     GEM_VDI, VDI_V_OPNVWK,     11, 0, {1, 1, 1, 1, 1, 1, 4, 0, 3, 7, 2},
                                                     {0}, 0},
    {"door_v_clsvwk",     GEM_VDI, VDI_V_CLSVWK,     0, 0, {0}, {0}, 0},
    {"door_vro_cpyfm",    GEM_VDI, VDI_VRO_CPYFM,    1, 6, {RASTER_OP_S_ONLY},
                                                     {0, 0, 7, 7, 3, 5}, 1},
    {"door_vr_recfl",     GEM_VDI, VDI_VR_RECFL,     0, 4, {0},
                                                     {RECFL_X1, RECFL_Y1, RECFL_X2, RECFL_Y2}, 0},
    {"door_v_show_c",     GEM_VDI, VDI_V_SHOW_C,     0, 0, {0}, {0}, 0},
    {"door_v_hide_c",     GEM_VDI, VDI_V_HIDE_C,     0, 0, {0}, {0}, 0},
    {"door_vq_mouse",     GEM_VDI, VDI_VQ_MOUSE,     0, 0, {0}, {0}, 0},
    {"door_vq_key_s",     GEM_VDI, VDI_VQ_KEY_S,     0, 0, {0}, {0}, 0},
    {"door_vs_clip",      GEM_VDI, VDI_VS_CLIP,      1, 4, {1}, {60, 30, 10, 20}, 0},
    {"door_appl_init",    GEM_AES, AES_APPL_INIT,    0, 0, {0}, {0}, 0},
    {"door_appl_exit",    GEM_AES, AES_APPL_EXIT,    0, 0, {0}, {0}, 0},
    {"door_graf_handle",  GEM_AES, AES_GRAF_HANDLE,  0, 0, {0}, {0}, 0},
    {"door_graf_mouse",   GEM_AES, AES_GRAF_MOUSE,   1, 0, {AES_M_OFF}, {0}, 0},
};

static void stage_file(void) {
    memcpy(g_image + FS_NAME_ADDR, "STAGED.DAT", 11);
    uint8_t *entry = os_fs_slot(g_image, 0);
    memcpy(entry, "STAGED.DAT", 11);
    wr32(entry + OS_FS_OFF_STAGING, OS_FS_STAGING);
    wr32(entry + OS_FS_OFF_SIZE, FS_FILE_BYTES);
    wr32(entry + OS_FS_OFF_CURSOR, 0);
    wr32(entry + OS_FS_OFF_OPEN, 1);
    wr32(entry + OS_FS_OFF_CAPACITY, FS_CAPACITY);
}

int main(void) {
    g_image = calloc(OS_IMAGE_SIZE, 1);
    if (!g_image) return 1;
    probe_require_out_regs();

    /* ---- the sixteen logic operations, aligned, then three geometries that are not ---- */
    for (int op = 0; op < RASTER_OP_COUNT; op++) {
        char name[32];
        snprintf(name, sizeof name, "op%d", op);
        cpyfm_case(name, SRC_RASTER, op, 0, 0, RASTER_SIDE - 1, RASTER_SIDE - 1, 0, 0);
    }
    cpyfm_case("shift3", SRC_RASTER, RASTER_OP_S_ONLY, 0, 0, 7, 7, 3, 5);
    cpyfm_case("shift13", SRC_RASTER, RASTER_OP_S_OR_D, 2, 1, 9, 8, 13, 2);
    cpyfm_case("clip_negative", SRC_RASTER, RASTER_OP_S_ONLY, 0, 0, 7, 7, -4, -4);
    cpyfm_case("clip_past_edge", SRC_RASTER, RASTER_OP_S_ONLY, 0, 0, 7, 7, 12, 12);
    /* ...and the reversed rectangle, which the VDI normalises rather than refuses. */
    cpyfm_case("reversed_rect", SRC_RASTER, RASTER_OP_S_ONLY, 7, 7, 0, 0, 0, 0);
    /* ...and a rectangle far larger than either raster. The four coordinates are signed words off
     * the emulated program's stack, so this is what a garbage MFDB call looks like: the model must
     * copy the part that fits and RETURN, which a per-pixel clip would not do in any useful time. */
    cpyfm_case("huge_rect", SRC_RASTER, RASTER_OP_S_ONLY, 0, 0, 30000, 30000, 0, 0);
    /* ...and the shape the copy DIRECTION exists for: source and destination in the SAME raster,
     * overlapping. A copy that always ran top-left to bottom-right would re-read pixels it had
     * already written and smear the source down (or across) the raster; the reference these are
     * checked against reads the whole source before writing anything, which is what a
     * direction-chosen copy of a plain S_ONLY produces. Three directions, so a model that always
     * ran backwards would fail the third. */
    cpyfm_case("overlap_down", DST_RASTER, RASTER_OP_S_ONLY, 0, 0, 15, 11, 0, 4);
    cpyfm_case("overlap_right", DST_RASTER, RASTER_OP_S_ONLY, 0, 0, 11, 15, 4, 0);
    cpyfm_case("overlap_up", DST_RASTER, RASTER_OP_S_ONLY, 0, 4, 15, 15, 0, 0);
    /* ...and a destination entirely off its raster, which narrows to an EMPTY range. The walk is a
     * count to an end rather than an ordering test, so an empty range has to return before it
     * starts — otherwise the copy steps past the end it is looking for and never stops. */
    cpyfm_case("clip_entirely_out", SRC_RASTER, RASTER_OP_S_ONLY, 0, 0, 7, 7, 20, 20);

    /* ---- v_opnvwk: the handle, the work_out fields, the counts, and the state work_in sets ----
     * Run twice with DIFFERENT work_in arrays, because the interesting failure is not "an attribute
     * was not installed" but "the wrong slot was". The first is Bubble Ghost's own call (every entry
     * 1); the second gives all four distinct values, so swapping two reddens. */
    {
        struct { const char *name; uint16_t text, interior, style, fill; } opens[] = {
            {"opnvwk", 1, 1, 1, 1},
            {"opnvwk_work_in", 4, VDI_FILL_HOLLOW, 3, 7},
        };
        for (unsigned i = 0; i < sizeof opens / sizeof opens[0]; i++) {
            const char *name = opens[i].name;
            image_reset();
            /* Both work_out arrays pre-filled, so "the model zeroed what it reports having
             * written" is visible: the call claims 45 ints and 6 pairs, and a caller walking them
             * would otherwise read its own leftovers back as workstation attributes. */
            memset(g_image + INTOUT, WORK_OUT_CANARY, OS_VDI_WORK_OUT_INTS * 2);
            memset(g_image + PTSOUT, WORK_OUT_CANARY, OS_VDI_WORK_OUT_POINTS * 2 * 2);
            write_work_in(opens[i].text, opens[i].interior, opens[i].style, opens[i].fill);
            contrl_word(VDI_CONTRL_OPCODE, VDI_V_OPNVWK);
            report_scalar(name, "modeled", (uint32_t)os_vdi(g_image, PBLK));
            report_scalar(name, "handle", contrl_read(VDI_CONTRL_HANDLE));
            report_scalar(name, "max_x", intout_read(0));
            report_scalar(name, "max_y", intout_read(1));
            report_scalar(name, "colours", intout_read(WORK_OUT_COLOURS));
            report_scalar(name, "ptsout_n", contrl_read(VDI_CONTRL_PTSOUT_N));
            report_scalar(name, "intout_n", contrl_read(VDI_CONTRL_INTOUT_N));
            /* One unfilled slot in the middle and the last of each array: the three the model does
             * fill are asserted above, and these are the 42 + 6 pairs it does not. */
            report_scalar(name, "intout_middle", intout_read(WORK_OUT_UNFILLED));
            report_scalar(name, "intout_last", intout_read(OS_VDI_WORK_OUT_INTS - 1));
            report_scalar(name, "ptsout_last", ptsout_read(OS_VDI_WORK_OUT_POINTS * 2 - 1));
            report_scalar(name, "state_handle", vdi_state_read(OS_VDI_OFF_HANDLE));
            report_scalar(name, "fill_colour", vdi_state_read(OS_VDI_OFF_FILL_COLOR));
            report_scalar(name, "text_colour", vdi_state_read(OS_VDI_OFF_TEXT_COLOR));
            report_scalar(name, "fill_interior", vdi_state_read(OS_VDI_OFF_FILL_INTERIOR));
            report_scalar(name, "fill_style", vdi_state_read(OS_VDI_OFF_FILL_STYLE));
            report_scalar(name, "write_mode", vdi_state_read(OS_VDI_OFF_WRITE_MODE));
            report_scalar(name, "text_height", vdi_state_read(OS_VDI_OFF_TEXT_HEIGHT));
            report_scalar(name, "clip_on", vdi_state_read(OS_VDI_OFF_CLIP_ON));
            report_scalar(name, "refusals", g_os_refusal_count());
        }
    }

    image_reset();
    open_workstation();
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_CLSVWK);
    report_scalar("clsvwk", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar("clsvwk", "state_handle", vdi_state_read(OS_VDI_OFF_HANDLE));

    /* ---- the attribute calls: what they store, what they echo, what they clamp ---- */
    struct { const char *name; uint16_t opcode; int field; int16_t asked; } attrs[] = {
        {"vsf_color", VDI_VSF_COLOR, OS_VDI_OFF_FILL_COLOR, 11},
        {"vsf_color_high", VDI_VSF_COLOR, OS_VDI_OFF_FILL_COLOR, 99},
        {"vsf_color_negative", VDI_VSF_COLOR, OS_VDI_OFF_FILL_COLOR, -3},
        {"vst_color", VDI_VST_COLOR, OS_VDI_OFF_TEXT_COLOR, 13},
        {"vswr_mode", VDI_VSWR_MODE, OS_VDI_OFF_WRITE_MODE, 2},
        {"vsf_interior", VDI_VSF_INTERIOR, OS_VDI_OFF_FILL_INTERIOR, 2},
        {"vsf_style", VDI_VSF_STYLE, OS_VDI_OFF_FILL_STYLE, 4},
    };
    for (unsigned i = 0; i < sizeof attrs / sizeof attrs[0]; i++) {
        image_reset();
        open_workstation();
        contrl_word(VDI_CONTRL_OPCODE, attrs[i].opcode);
        contrl_word(VDI_CONTRL_INTIN_N, 1);
        intin_word(0, (uint16_t)attrs[i].asked);
        report_scalar(attrs[i].name, "modeled", (uint32_t)os_vdi(g_image, PBLK));
        report_scalar(attrs[i].name, "stored", vdi_state_read(attrs[i].field));
        report_scalar(attrs[i].name, "echoed", intout_read(0));
        report_scalar(attrs[i].name, "intout_n", contrl_read(VDI_CONTRL_INTOUT_N));
    }

    /* ---- vst_height: one font, so the answer never changes ---- */
    image_reset();
    open_workstation();
    contrl_word(VDI_CONTRL_OPCODE, VDI_VST_HEIGHT);
    contrl_word(VDI_CONTRL_PTSIN_N, 1);
    ptsin_word(0, 0);
    ptsin_word(1, 6);
    report_scalar("vst_height", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar("vst_height", "char_w", ptsout_read(0));
    report_scalar("vst_height", "char_h", ptsout_read(1));
    report_scalar("vst_height", "cell_w", ptsout_read(2));
    report_scalar("vst_height", "cell_h", ptsout_read(3));
    report_scalar("vst_height", "ptsout_n", contrl_read(VDI_CONTRL_PTSOUT_N));
    report_scalar("vst_height", "requested", vdi_state_read(OS_VDI_OFF_TEXT_HEIGHT));

    /* ---- the two queries, over poked state ---- */
    image_reset();
    open_workstation();
    put16(OS_MOUSE + OS_MOUSE_OFF_X, 137);
    put16(OS_MOUSE + OS_MOUSE_OFF_Y, 88);
    put16(OS_MOUSE + OS_MOUSE_OFF_BUTTONS, 1);
    contrl_word(VDI_CONTRL_OPCODE, VDI_VQ_MOUSE);
    report_scalar("vq_mouse", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar("vq_mouse", "buttons", intout_read(0));
    report_scalar("vq_mouse", "x", ptsout_read(0));
    report_scalar("vq_mouse", "y", ptsout_read(1));
    report_scalar("vq_mouse", "ptsout_n", contrl_read(VDI_CONTRL_PTSOUT_N));
    report_scalar("vq_mouse", "intout_n", contrl_read(VDI_CONTRL_INTOUT_N));
    /* ...and again, to show the query does NOT consume what it read. */
    os_vdi(g_image, PBLK);
    report_scalar("vq_mouse", "x_again", ptsout_read(0));

    image_reset();
    open_workstation();
    put16(OS_KEY_SHIFT, 0x0003);
    contrl_word(VDI_CONTRL_OPCODE, VDI_VQ_KEY_S);
    report_scalar("vq_key_s", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar("vq_key_s", "state", intout_read(0));
    report_scalar("vq_key_s", "intout_n", contrl_read(VDI_CONTRL_INTOUT_N));

    /* ---- vs_clip: what it stores, normalised ---- */
    image_reset();
    open_workstation();
    contrl_word(VDI_CONTRL_OPCODE, VDI_VS_CLIP);
    contrl_word(VDI_CONTRL_PTSIN_N, 2);
    contrl_word(VDI_CONTRL_INTIN_N, 1);
    intin_word(0, 1);
    ptsin_word(0, 60); ptsin_word(1, 30);
    ptsin_word(2, 10); ptsin_word(3, 20);
    report_scalar("vs_clip", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    report_scalar("vs_clip", "on", vdi_state_read(OS_VDI_OFF_CLIP_ON));
    report_scalar("vs_clip", "x1", vdi_state_read(OS_VDI_OFF_CLIP_X1));
    report_scalar("vs_clip", "y1", vdi_state_read(OS_VDI_OFF_CLIP_Y1));
    report_scalar("vs_clip", "x2", vdi_state_read(OS_VDI_OFF_CLIP_X2));
    report_scalar("vs_clip", "y2", vdi_state_read(OS_VDI_OFF_CLIP_Y2));

    /* ---- v_clrwk: the whole screen goes to colour 0 ---- */
    image_reset();
    open_workstation();
    memset(g_image + OS_SCREEN_BASE, 0xa5, OS_SCREEN_W * OS_SCREEN_H * OS_SCREEN_PLANES / 8);
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_CLRWK);
    report_scalar("clrwk", "modeled", (uint32_t)os_vdi(g_image, PBLK));
    {
        uint32_t nonzero = 0;
        for (uint32_t i = 0; i < OS_SCREEN_W * OS_SCREEN_H * OS_SCREEN_PLANES / 8; i++)
            nonzero += g_image[OS_SCREEN_BASE + i] != 0;
        report_scalar("clrwk", "nonzero_bytes", nonzero);
    }

    /* ---- vr_recfl: the rectangle, and the clip rectangle cutting it down ---- */
    image_reset();
    open_workstation();
    set_attribute(VDI_VSF_COLOR, 6);
    report_screen_window("recfl_in", TEXT_BASELINE, TEXT_WINDOW_ROWS, 1, TEXT_WINDOW_WORDS);
    report_scalar("recfl", "modeled",
                  (uint32_t)recfl(18, TEXT_BASELINE + 1, 40, TEXT_BASELINE + 4));
    report_scalar("recfl", "colour", 6);
    report_screen_window("recfl_out", TEXT_BASELINE, TEXT_WINDOW_ROWS, 1, TEXT_WINDOW_WORDS);

    /* ...and two whose rectangles run off the screen: one past the right and bottom edges, one
     * before the left and top. Each is reported as a whole-screen pixel count plus canary damage —
     * a fill one column too generous wraps onto another row of the screen (which no window would
     * show), and one row too generous writes outside the framebuffer entirely. */
    recfl_case("recfl_off_bottom_right", -20, 195, 400, 250, 6, VDI_FILL_SOLID);
    recfl_case("recfl_off_top_left", -20, -5, 10, 3, 6, VDI_FILL_SOLID);

    /* ...and the FILL INTERIOR, which decides the colour before the fill colour does. Hollow paints
     * the BACKGROUND: the case fills solid first and then hollow over the same rectangle, so
     * "painted colour 0" is distinguishable from "did nothing at all". */
    image_reset();
    open_workstation();
    set_attribute(VDI_VSF_COLOR, 6);
    recfl(RECFL_X1, RECFL_Y1, RECFL_X2, RECFL_Y2);
    report_scalar("recfl_hollow", "pixels_before", screen_pixels_set());
    set_attribute(VDI_VSF_INTERIOR, VDI_FILL_HOLLOW);
    report_scalar("recfl_hollow", "modeled",
                  (uint32_t)recfl(RECFL_X1, RECFL_Y1, RECFL_X2, RECFL_Y2));
    report_scalar("recfl_hollow", "pixels_after", screen_pixels_set());

    /* ...and the three interiors that need a pattern table the model does not have. Refused by
     * name: filling them solid would draw pixels no real machine draws. */
    {
        struct { const char *name; uint16_t interior; } patterned[] = {
            {"recfl_pattern", VDI_FILL_PATTERN},
            {"recfl_hatch", VDI_FILL_HATCH},
            {"recfl_user", VDI_FILL_USER},
        };
        for (unsigned i = 0; i < sizeof patterned / sizeof patterned[0]; i++)
            recfl_case(patterned[i].name, RECFL_X1, RECFL_Y1, RECFL_X2, RECFL_Y2, 6,
                       patterned[i].interior);
    }

    /* ---- v_gtext: the synthetic font, and that drawing the same string twice changes nothing ---- */
    image_reset();
    open_workstation();
    contrl_word(VDI_CONTRL_OPCODE, VDI_VST_COLOR);
    contrl_word(VDI_CONTRL_INTIN_N, 1);
    intin_word(0, TEXT_COLOUR);
    os_vdi(g_image, PBLK);
    memset(g_image + CONTRL, 0, CONTRL_WORDS * 2);
    report_screen_window("gtext_in", TEXT_BASELINE - (RASTER_FONT_H - 1), TEXT_WINDOW_ROWS,
                         TEXT_X / 16, TEXT_WINDOW_WORDS);
    gtext("Hi", TEXT_X, TEXT_BASELINE);
    report_scalar("gtext", "colour", TEXT_COLOUR);
    report_screen_window("gtext_once", TEXT_BASELINE - (RASTER_FONT_H - 1), TEXT_WINDOW_ROWS,
                         TEXT_X / 16, TEXT_WINDOW_WORDS);
    gtext("Hi", TEXT_X, TEXT_BASELINE);
    report_screen_window("gtext_twice", TEXT_BASELINE - (RASTER_FONT_H - 1), TEXT_WINDOW_ROWS,
                         TEXT_X / 16, TEXT_WINDOW_WORDS);

    /* ---- the candidate side's ledger: the four kinds, in order ---- */
    image_reset();
    open_workstation();
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_HIDE_C);
    os_vdi(g_image, PBLK);
    contrl_word(VDI_CONTRL_OPCODE, VDI_V_SHOW_C);
    os_vdi(g_image, PBLK);
    os_cconout('H');
    os_cconout('i');
    os_ikbd_out(0x12);
    contrl_word(VDI_CONTRL_OPCODE, AES_GRAF_MOUSE);
    intin_word(0, AES_M_OFF);
    os_aes(g_image, APBLK);
    report_candidate_ledger("candidate_ledger");
    report_scalar("candidate_ledger", "refusals", g_os_refusal_count());

    /* ---- the ORACLE side: shim.c's own decode of each trap's stack frame ---- */
    image_reset();
    {
        uint16_t args[] = {'X'};
        gemdos_trap_case("trap_cconout", GEMDOS_CCONOUT, args, 1);
    }
    image_reset();
    memcpy(g_image + CCONWS_STRING, "Ok!", 4);
    {
        uint32_t pc = plant_push_long(PROBE_ENTRY, CCONWS_STRING);
        pc = plant_push_word(pc, GEMDOS_CCONWS);
        plant_trap(pc, OP_TRAP_GEMDOS, 2 + 4);
        run_trap_case("trap_cconws");
    }
    /* ...and a string with no terminator inside the image, which the model REFUSES rather than cut
     * off at the edge. Its ledger must be EMPTY: a refused call leaves no trace on either side, and
     * a walk that logged as it went would have pushed every byte it passed before finding out. */
    image_reset();
    memset(g_image + OS_IMAGE_SIZE - CCONWS_TAIL_BYTES, 'A', CCONWS_TAIL_BYTES);
    {
        uint32_t pc = plant_push_long(PROBE_ENTRY, OS_IMAGE_SIZE - CCONWS_TAIL_BYTES);
        pc = plant_push_word(pc, GEMDOS_CCONWS);
        plant_trap(pc, OP_TRAP_GEMDOS, 2 + 4);
        run_trap_case("trap_cconws_unterminated");
    }
    image_reset();
    gemdos_trap_case("trap_cconis_idle", GEMDOS_CCONIS, NULL, 0);
    image_reset();
    put32(OS_CON_PENDING, 1);
    put32(OS_CON_CHAR, 0x00230061);
    gemdos_trap_case("trap_cconis_key", GEMDOS_CCONIS, NULL, 0);
    image_reset();
    put32(OS_CON_PENDING, 1);
    put32(OS_CON_CHAR, 0x00230061);
    gemdos_trap_case("trap_crawcin", GEMDOS_CRAWCIN, NULL, 0);
    image_reset();
    gemdos_trap_case("trap_crawcin_idle", GEMDOS_CRAWCIN, NULL, 0);
    image_reset();
    put32(OS_CON_PENDING, 1);
    put32(OS_CON_CHAR, 0x00230061);
    gemdos_trap_case("trap_cnecin", GEMDOS_CNECIN, NULL, 0);

    /* Fseek(4, handle, FROM_START) on a staged file, then the same call to a device Bconout does
     * not model — the two shapes of the trap decode, served and refused. */
    image_reset();
    stage_file();
    {
        uint32_t pc = plant_push_word(PROBE_ENTRY, OS_FSEEK_FROM_START);
        pc = plant_push_word(pc, OS_FS_FIRST_HANDLE);
        pc = plant_push_long(pc, 4);
        pc = plant_push_word(pc, GEMDOS_FSEEK);
        plant_trap(pc, OP_TRAP_GEMDOS, 2 + 2 + 2 + 4);
        run_trap_case("trap_fseek");
        report_scalar("trap_fseek", "cursor", be32(os_fs_slot(g_image, 0) + OS_FS_OFF_CURSOR));
    }

    /* Crawio both ways. The WRITE direction is console output and takes a ledger entry; it must not
     * eat the staged key a later read is waiting for, which is the second case. */
    image_reset();
    {
        uint16_t args[] = {CRAWIO_WRITE_CHAR};
        gemdos_trap_case("trap_crawio_write", GEMDOS_CRAWIO, args, 1);
    }
    image_reset();
    put32(OS_CON_PENDING, 1);
    put32(OS_CON_CHAR, CONSOLE_KEY_A);
    {
        uint16_t args[] = {CRAWIO_WRITE_CHAR};
        gemdos_trap_case("trap_crawio_write_keeps_the_key", GEMDOS_CRAWIO, args, 1);
        report_scalar("trap_crawio_write_keeps_the_key", "still_pending", be32(g_image + OS_CON_PENDING));
    }
    image_reset();
    put32(OS_CON_PENDING, 1);
    put32(OS_CON_CHAR, CONSOLE_KEY_A);
    {
        uint16_t args[] = {OS_CRAWIO_READ};
        gemdos_trap_case("trap_crawio_read", GEMDOS_CRAWIO, args, 1);
    }

    /* ...and the staged WALK: three keys, taken oldest first by three blocking reads, then a fourth
     * read with the queue empty, which refuses exactly as an idle console always did. */
    image_reset();
    {
        uint32_t keys[] = {CONSOLE_WALK_0, CONSOLE_WALK_1, CONSOLE_WALK_2};
        uint32_t taken = 0;
        put32(OS_CON_PENDING, 3);
        put32(OS_CON_CHAR, keys[0]);
        put32(OS_CON_QUEUE, keys[1]);
        put32(OS_CON_QUEUE + 4, keys[2]);
        g_os_refusal_reset();
        for (int i = 0; i < 3; i++) {
            char key[32];
            snprintf(key, sizeof key, "key%d", i);
            report_scalar("console_walk", key, os_cnecin(g_image, &taken) ? taken : 0);
        }
        report_scalar("console_walk", "still_pending", be32(g_image + OS_CON_PENDING));
        report_scalar("console_walk", "exhausted", (uint32_t)os_cnecin(g_image, &taken));
        report_scalar("console_walk", "refusals", g_os_refusal_count());
    }

    /* ...and the OLDER SPELLING of the same field: a hand-poked FLAG rather than a count. A value
     * the queue cannot hold is one keystroke, and taking it clears the field exactly as it always
     * did — which is what keeps the one-key path writing one word under a program whose own code
     * covers this block. */
    image_reset();
    put32(OS_CON_PENDING, 0xffffffffu);
    put32(OS_CON_CHAR, CONSOLE_KEY_A);
    put32(OS_CON_QUEUE, CONSOLE_WALK_0);
    {
        uint32_t taken = 0;
        g_os_refusal_reset();
        report_scalar("console_flag_spelling", "key", os_cnecin(g_image, &taken) ? taken : 0);
        report_scalar("console_flag_spelling", "still_pending", be32(g_image + OS_CON_PENDING));
        report_scalar("console_flag_spelling", "exhausted", (uint32_t)os_cnecin(g_image, &taken));
        report_scalar("console_flag_spelling", "refusals", g_os_refusal_count());
    }

    image_reset();
    {
        uint32_t pc = plant_push_word(PROBE_ENTRY, 0x12);
        pc = plant_push_word(pc, OS_BIOS_DEV_IKBD);
        pc = plant_push_word(pc, BIOS_BCONOUT);
        plant_trap(pc, OP_TRAP_BIOS, 2 + 2 + 2);
        run_trap_case("trap_bconout_ikbd");
    }
    image_reset();
    {
        uint32_t pc = plant_push_word(PROBE_ENTRY, 0x12);
        pc = plant_push_word(pc, BIOS_DEV_CONSOLE);
        pc = plant_push_word(pc, BIOS_BCONOUT);
        plant_trap(pc, OP_TRAP_BIOS, 2 + 2 + 2);
        run_trap_case("trap_bconout_console");
    }

    /* ---- GEMDOS Malloc: the shim's arena and the candidate's must hand out the same blocks ----
     * They are two implementations of one bump allocator — os.h's declaration says why the
     * candidate has one at all — and only a case that runs both can say they agree. */
    image_reset();
    {
        uint32_t pc = plant_push_long(PROBE_ENTRY, MALLOC_FIRST_SIZE);
        pc = plant_push_word(pc, GEMDOS_MALLOC);
        plant_word(pc, OP_TRAP_GEMDOS);
        pc = plant_push_long(pc + 2, MALLOC_SECOND_SIZE);
        pc = plant_push_word(pc, GEMDOS_MALLOC);
        plant_trap(pc, OP_TRAP_GEMDOS, 2 * (2 + 4));
        run_trap_case("trap_malloc");
    }
    g_os_heap_reset();
    report_scalar("candidate_malloc", "first", os_malloc(MALLOC_FIRST_SIZE));
    report_scalar("candidate_malloc", "second", os_malloc(MALLOC_SECOND_SIZE));
    /* Malloc(-1) is GEMDOS's "how big is the largest free block?" query: it rounds to zero, so it
     * answers with the arena base and leaves the pointer where it was. */
    g_os_heap_reset();
    report_scalar("candidate_malloc", "query", os_malloc(0xffffffffu));
    report_scalar("candidate_malloc", "after_query", os_malloc(MALLOC_FIRST_SIZE));
    report_scalar("candidate_malloc", "base", OS_HEAP_BASE);
    /* ...and that the reset really rewinds it, which is what harness.arm_candidate relies on. */
    g_os_heap_reset();
    report_scalar("candidate_malloc", "after_reset", os_malloc(MALLOC_FIRST_SIZE));
    /* INSTALLING A BASE rewinds the pointer to it too. Without that a candidate whose project moved
     * its heap kept allocating from the default arena until the first reset — the wrong arena
     * entirely, for any caller outside a harness-armed run. */
    os_set_heap_base(MALLOC_MOVED_BASE);
    report_scalar("candidate_malloc", "after_move", os_malloc(0));
    os_set_heap_base(OS_HEAP_BASE_DEFAULT);
    /* ...and the CEILING. The window's last block is served and the next request is REFUSED, rather
     * than handed out over the staged-file table — where both sides would scribble the same bytes
     * and the two corrupted runs would compare equal. */
    g_os_heap_reset();
    g_os_refusal_reset();
    report_scalar("candidate_malloc", "fills_the_window", os_malloc(OS_HEAP_LIMIT - OS_HEAP_BASE));
    report_scalar("candidate_malloc", "at_the_ceiling", g_os_heap_pointer());
    report_scalar("candidate_malloc", "query_at_the_ceiling", os_malloc(OS_MALLOC_LARGEST_FREE));
    report_scalar("candidate_malloc", "past_the_ceiling", os_malloc(2));
    report_scalar("candidate_malloc", "ceiling_refusals", g_os_refusal_count());
    report_scalar("candidate_malloc", "limit", OS_HEAP_LIMIT);
    g_os_heap_reset();

    /* ---- a parameter block near the top of the address space ----
     * `base + index * 2` wraps in 32 bits, so an unwrapped bounds test finds the WRAPPED address
     * inside the image, serves the access and writes the harness's own low memory. The model takes
     * the sum in 64 bits, so every one of these faults and the whole call is refused. Each array is
     * driven by an opcode that WRITES it past index 0 — index 0 does not wrap, so an opcode that
     * only touches the first entry would be refused either way and prove nothing. */
    {
        struct { const char *name; int slot; uint16_t opcode; } wrapping[] = {
            {"wrapping_contrl", VDI_PB_CONTRL, VDI_VST_HEIGHT},   /* contrl[2] and contrl[4] */
            {"wrapping_ptsout", VDI_PB_PTSOUT, VDI_VST_HEIGHT},   /* ptsout[0..3] */
            {"wrapping_intout", VDI_PB_INTOUT, VDI_V_OPNVWK},     /* intout[0..44] */
        };
        for (unsigned i = 0; i < sizeof wrapping / sizeof wrapping[0]; i++) {
            uint32_t damaged = 0;
            image_reset();
            open_workstation();
            write_work_in(OS_VDI_DEFAULT_TEXT_COLOR, VDI_FILL_SOLID, OS_VDI_DEFAULT_FILL_STYLE,
                          OS_VDI_DEFAULT_FILL_COLOR);
            memset(g_image, WRAP_CANARY, WRAP_CANARY_BYTES);
            put32(PBLK + (uint32_t)wrapping[i].slot * 4, WRAPPING_POINTER);
            contrl_word(VDI_CONTRL_OPCODE, wrapping[i].opcode);
            contrl_word(VDI_CONTRL_PTSIN_N, 1);
            ptsin_word(0, 0);
            ptsin_word(1, 6);
            report_scalar(wrapping[i].name, "modeled", (uint32_t)os_vdi(g_image, PBLK));
            for (uint32_t byte = 0; byte < WRAP_CANARY_BYTES; byte++)
                damaged += g_image[byte] != WRAP_CANARY;
            report_scalar(wrapping[i].name, "low_memory_damage", damaged);
        }
    }

    /* ---- THE TWO DOORS ONTO ONE MODEL, one case per modeled opcode ---- */
    {
        uint8_t *snapshot = calloc(door_band_bytes(), 1);
        if (!snapshot) return 1;
        for (unsigned i = 0; i < sizeof DOOR_CASES / sizeof DOOR_CASES[0]; i++)
            door_case(&DOOR_CASES[i], snapshot);
        free(snapshot);
    }

    free(g_image);
    return 0;
}
