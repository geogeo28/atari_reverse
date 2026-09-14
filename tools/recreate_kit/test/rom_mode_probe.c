/* rom_mode_probe.c — the fixture behind test_rom_mode.py.
 *
 * ROM MODE is the map `osh_rom_window()` installs: RAM at the bottom, the decoded I/O blocks at
 * $ff0000, a read-only ROM window above them, and NO TOS trap model — a `trap #13` is taken through
 * the image's own vector table by Musashi's exception processing, into whatever the image says is
 * there (shim.c, "THE MEMORY MAP"; TRAP_MODEL.md, "ROM mode"). Nothing in the kit's own suite can
 * see any of that from Python: `harness`/`emu` bind a project's candidate .so at import and this
 * directory deliberately binds no project, so this drives `osh_run` directly.
 *
 * WHY THE LAST TWO CASES ARE A PAIR. `trap_in_rom_mode` and `trap_off_rom_mode` run the IDENTICAL
 * image and routine, differing only in whether the window is installed. The first must reach the
 * handler the image's vector table names; the second must NOT, because the shim patches that vector
 * and serves the trap from the model. Either one alone would pass against a shim that had lost the
 * distinction in the other direction.
 *
 * Output is one `<name> <value>` line per claim; the Python side owns the expectations, so a claim
 * added here without one there fails loudly rather than passing silently.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "os.h"             /* OS_PSG_PORT_SELECT — the address the shim's own decode uses */
#include "probe_common.h"   /* the oracle's entry points, NREGS/OUT_REGS, plant_word/plant_long */

/* ---- the geometry, which is a MACHINE's rather than a scratch buffer's --------------------------
 * The I/O page's address is fixed by os.h ($ff0000), so a probe that wants the I/O decode to be a
 * question at all has to span the whole 24-bit bus. RAM is deliberately much smaller than the image:
 * that gap is exactly where a byte can be "inside the image" and yet not RAM, which is the whole
 * thing ROM mode has to get right. */
#define ROM_IMAGE_SIZE 0x1000000u      /* the 24-bit address space */
#define ROM_RAM_END    0x0010000u      /* ...of which this much is RAM */
#define ROM_LO         0x0fc0000u
#define ROM_HI         0x0fd0000u
#define ROM_ENTRY      (ROM_LO + 0x100u)   /* the routine under test, executing IN the ROM */
#define ROM_HANDLER    (ROM_LO + 0x200u)   /* ...and the trap handler the image's vector names */
#define ROM_TARGET     (ROM_LO + 0x010u)   /* a ROM address a store aims at */
#define RAM_SOURCE     0x3000u             /* a RAM byte the routine reads */
#define RAM_MARKER     0x3004u             /* ...and one the trap handler writes */
#define VECTOR_TRAP_13 0xb4u

#define PROBE_MAX_INSNS 32u

/* The bytes each case plants, so "did the model serve this?" is answerable: a decoy in the image at
 * a hardware address must never be what a read of it returns. */
#define RAM_SOURCE_BYTE   0x5au
#define IO_DECOY_BYTE     0x99u
#define PSG_REGISTER      4u
#define PSG_SEEDED_BYTE   0x3cu
#define SHIFTER_PEN0      0xff8240u
#define PEN0_BYTE         0x77u
#define ROM_STORE_BYTE    0x5au
#define MARKER_BYTE       0x77u
/* The shifter's resolution byte: an I/O address inside the decoded page that NO Phase-7 slot names,
 * which is what XBIOS Getrez reads. The pair of claims below is what says the shim can tell "served
 * by a model" from "answered 0 because nothing models it" — see g_io_unmodeled_reads in shim.c. */
#define SHIFTER_RESOLUTION 0xff8260u
/* os.h's, not a literal: the shim decodes THAT constant, so a probe planting its decoy at its own
 * copy would keep reporting the model green after the address moved (psg_model_probe.c's rule). */
#define PSG_PORT_SELECT   OS_PSG_PORT_SELECT

/* 68000 encodings this probe plants. `move.b #imm,(xxx).l` and `move.b (xxx).l,d1` are the two
 * shapes every case is built from; the trap pair is the last case's. */
#define OPCODE_MOVE_B_IMM_ABSL 0x13fcu
#define OPCODE_TRAP_13         0x4e4du
#define OPCODE_RTE             0x4e73u

/* ---- the oracle entry points probe_common.h does not declare ---- */
void     osh_rom_window(uint32_t ram_end, uint32_t rom_lo, uint32_t rom_hi);
int      osh_rom_mode(void);
uint32_t osh_rom_stores(void);
void     osh_psg_seed(const uint8_t *values, uint32_t known);
uint32_t osh_psg_nregs(void);
uint32_t osh_hw_write_count(void);
const uint32_t *osh_hw_write_addrs(void);
const uint32_t *osh_hw_write_vals(void);
void     osh_schedule(const uint32_t *entries, uint32_t n, const uint32_t *sites, uint32_t site_n);
uint32_t osh_io_unmodeled_reads(void);
uint32_t osh_io_unmodeled_first(void);

/* `move.b #value,(addr).l` at `at`; returns the address after it. */
static uint32_t plant_store_byte(uint32_t at, uint8_t value, uint32_t addr) {
    plant_word(at, OPCODE_MOVE_B_IMM_ABSL);
    plant_word(at + 2, value);
    return plant_long(at + 4, addr);
}

/* `move.b (addr).l,d1` at `at`; returns the address after it. */
static uint32_t plant_load_byte_d1(uint32_t at, uint32_t addr) {
    plant_word(at, MOVE_B_ABSL_TO_D1);
    return plant_long(at + 2, addr);
}

/* Run the planted routine from ROM_ENTRY and return D1 (out_regs[1]). Dies rather than reporting a
 * run that never reached its rts: every routine here is a handful of instructions. */
static uint32_t run_from_rom(const char *what) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, ROM_IMAGE_SIZE, ROM_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the probe's %s routine did not return to the sentinel\n", what);
        exit(1);
    }
    return out[1];
}

/* Clear everything a case can leave behind and put the window back, so cases cannot interact. */
static void begin_case(void) {
    memset(g_image, 0, ROM_IMAGE_SIZE);
    osh_rom_window(ROM_RAM_END, ROM_LO, ROM_HI);
}

int main(void) {
    probe_require_out_regs();
    g_image = calloc(ROM_IMAGE_SIZE, 1);
    if (!g_image) {
        fprintf(stderr, "probe: could not allocate the %u-byte image\n", ROM_IMAGE_SIZE);
        exit(1);
    }
    /* A C caller inherits whatever schedule the last install left (shim.c's osh_schedule), and this
     * binary makes none — install an empty one so no stray entry can fire inside a case. */
    osh_schedule(NULL, 0, NULL, 0);

    begin_case();
    printf("rom_mode_armed %u\n", (unsigned)osh_rom_mode());

    /* (1) RAM below ram_end is still served out of the image, and the ROM executes in place. */
    g_image[RAM_SOURCE] = RAM_SOURCE_BYTE;
    plant_rts(plant_load_byte_d1(ROM_ENTRY, RAM_SOURCE));
    printf("ram_byte %u\n", run_from_rom("ram_byte"));

    /* (2) A hardware address INSIDE the image is not image: the select write must reach the PSG
     * model's latch rather than the image's byte, and the read-back must answer the seeded register
     * rather than the decoy planted at that very address. */
    begin_case();
    g_image[PSG_PORT_SELECT] = IO_DECOY_BYTE;
    {
        uint8_t seed[16] = {0};
        uint32_t nregs = osh_psg_nregs();
        if (nregs > sizeof seed) {
            fprintf(stderr, "probe: the PSG file is %u registers, this probe seeds %zu\n",
                    nregs, sizeof seed);
            exit(1);
        }
        seed[PSG_REGISTER] = PSG_SEEDED_BYTE;
        osh_psg_seed(seed, 1u << PSG_REGISTER);
    }
    {
        uint32_t at = plant_store_byte(ROM_ENTRY, PSG_REGISTER, PSG_PORT_SELECT);
        plant_rts(plant_load_byte_d1(at, PSG_PORT_SELECT));
    }
    printf("psg_readback %u\n", run_from_rom("psg_readback"));
    printf("psg_select_did_not_reach_the_image %u\n", g_image[PSG_PORT_SELECT]);
    /* ...and a MODELLED port is not counted as an unmodelled I/O read. The control for case (7). */
    printf("modelled_io_unmodeled_reads %u\n", osh_io_unmodeled_reads());

    /* (3) A store to a hardware register is ledgered and dropped, not written into the image. */
    begin_case();
    plant_rts(plant_store_byte(ROM_ENTRY, PEN0_BYTE, SHIFTER_PEN0));
    run_from_rom("hw_write");
    printf("hw_write_count %u\n", osh_hw_write_count());
    printf("hw_write_addr %u\n", osh_hw_write_count() ? osh_hw_write_addrs()[0] : 0u);
    printf("hw_write_value %u\n", osh_hw_write_count() ? osh_hw_write_vals()[0] : 0u);
    printf("hw_write_did_not_reach_the_image %u\n", g_image[SHIFTER_PEN0]);

    /* (4) The ROM is read-only: a store into the window changes nothing and is counted. */
    begin_case();
    plant_rts(plant_store_byte(ROM_ENTRY, ROM_STORE_BYTE, ROM_TARGET));
    run_from_rom("rom_store");
    printf("rom_stores %u\n", osh_rom_stores());
    printf("rom_store_did_not_reach_the_image %u\n", g_image[ROM_TARGET]);

    /* (7) An I/O read NOTHING models is COUNTED, with its address — the tally a differential
     * refuses on. It is still answered 0, as it always was: refusing is the harness's to do, so a
     * bootstrap driven straight through osh_run is not sunk by it. */
    begin_case();
    plant_rts(plant_load_byte_d1(ROM_ENTRY, SHIFTER_RESOLUTION));
    printf("unmodeled_io_value %u\n", run_from_rom("unmodeled_io"));
    printf("unmodeled_io_reads %u\n", osh_io_unmodeled_reads());
    printf("unmodeled_io_first %u\n", osh_io_unmodeled_first());

    /* (5) and (6) — the pair. The same image, the same routine; only the window differs. */
    for (int armed = 1; armed >= 0; armed--) {
        begin_case();
        if (!armed)
            osh_rom_window(0, 0, 0);        /* .PRG mode: the whole image is RAM, and traps are modelled */
        plant_long(VECTOR_TRAP_13, ROM_HANDLER);
        plant_word(ROM_ENTRY, OPCODE_TRAP_13);
        plant_rts(ROM_ENTRY + 2);
        plant_word(plant_store_byte(ROM_HANDLER, MARKER_BYTE, RAM_MARKER), OPCODE_RTE);
        run_from_rom(armed ? "trap_in_rom_mode" : "trap_off_rom_mode");
        printf("%s %u\n", armed ? "trap_in_rom_mode_marker" : "trap_off_rom_mode_marker",
               g_image[RAM_MARKER]);
        if (armed) {
            /* ...and the image's own vector is untouched: ROM mode installs nothing to restore. */
            uint32_t vector = (uint32_t)g_image[VECTOR_TRAP_13] << 24
                            | (uint32_t)g_image[VECTOR_TRAP_13 + 1] << 16
                            | (uint32_t)g_image[VECTOR_TRAP_13 + 2] << 8
                            | g_image[VECTOR_TRAP_13 + 3];
            printf("trap_vector_untouched %u\n", (unsigned)(vector == ROM_HANDLER));
        }
    }

    free(g_image);
    return 0;
}
