/* profile_probe.c — the fixture behind test_profile.py.
 *
 * The cycle-per-PC profile keeps one tally per even PC: RAM PCs in [0, 1 MiB) in the first slots,
 * then — in ROM mode only — the ROM window's PCs [rom_lo, rom_lo + 1 MiB) in the slots after them,
 * with `osh_prof_slot` the one map from a PC to its slot (shim.c, "optional cycle-per-PC profile").
 * It counts in `osh_run` as well as in `osh_run_bench`. This probe drives `osh_run` directly, for
 * rom_mode_probe.c's reason: the kit binds no project, so the oracle is not reachable from Python.
 *
 * WHY THE TWO RUN CASES PLANT AT THE SAME OFFSET. The ROM routine sits at ROM_LO + ROUTINE_OFFSET and
 * the RAM one at ROUTINE_OFFSET, so a map that dropped the ROM slots' base — filing a ROM PC in the
 * RAM slot of the same offset — reports cycles where the other case must report none.
 *
 * Output is one `<name> <value>` line per claim; the Python side owns the expectations.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "probe_common.h"   /* the oracle's entry points, NREGS/OUT_REGS, plant_word/plant_rts */

/* ---- the geometry: rom_mode_probe.c's, a whole 24-bit bus with a small RAM and a ROM window ---- */
#define ROM_IMAGE_SIZE 0x1000000u
#define ROM_RAM_END    0x0010000u
#define ROM_LO         0x0fc0000u
#define ROM_HI         0x0fd0000u
#define ROUTINE_OFFSET 0x1000u              /* both routines' offset: RAM's from 0, ROM's from ROM_LO */
#define RAM_ENTRY      ROUTINE_OFFSET
#define ROM_ENTRY      (ROM_LO + ROUTINE_OFFSET)
#define IO_PC          0xff8240u            /* the I/O page: neither RAM nor the ROM window */

/* The profile's layout, mirrored: one slot per even PC, RAM's first, the ROM window's after them. */
#define PROF_RAM_BYTES  0x100000u
#define PROF_SLOT_BYTES 2u
#define RAM_ROUTINE_SLOT (RAM_ENTRY / PROF_SLOT_BYTES)
#define ROM_ROUTINE_SLOT ((PROF_RAM_BYTES + ROUTINE_OFFSET) / PROF_SLOT_BYTES)

/* The routine: ROUTINE_NOPS nops then an rts, all of whose PCs the tally sums are taken over. */
#define OPCODE_NOP     0x4e71u
#define ROUTINE_NOPS   3u
#define INSN_BYTES     2u
#define ROUTINE_BYTES  ((ROUTINE_NOPS + 1u) * INSN_BYTES)
#define PROBE_MAX_INSNS 8u

/* ---- the oracle entry points probe_common.h does not declare ---- */
void     osh_rom_window(uint32_t ram_end, uint32_t rom_lo, uint32_t rom_hi);
void     osh_schedule(const uint32_t *entries, uint32_t n, const uint32_t *sites, uint32_t site_n);
void     osh_prof_enable(int on);
void     osh_prof_reset(void);
const uint32_t *osh_prof_data(void);
uint32_t osh_prof_slots(void);
uint32_t osh_prof_slot(uint32_t pc);
uint64_t osh_num_cycles(void);

static void plant_routine(uint32_t at) {
    for (uint32_t i = 0; i < ROUTINE_NOPS; i++)
        plant_word(at + i * INSN_BYTES, OPCODE_NOP);
    plant_rts(at + ROUTINE_NOPS * INSN_BYTES);
}

/* The cycles tallied in the routine's slots, from `first_slot` on. Indexed from the probe's own
 * layout rather than through osh_prof_slot, so these claims do not lean on the map claim (1) pins. */
static uint32_t routine_tally(uint32_t first_slot) {
    uint32_t total = 0;
    for (uint32_t i = 0; i < ROUTINE_BYTES / PROF_SLOT_BYTES; i++) total += osh_prof_data()[first_slot + i];
    return total;
}

static uint32_t whole_tally(void) {
    uint32_t total = 0;
    for (uint32_t i = 0; i < osh_prof_slots(); i++) total += osh_prof_data()[i];
    return total;
}

/* Clear the image and the profile, put the window back, and plant the routine at `entry`. */
static void begin_case(uint32_t entry) {
    memset(g_image, 0, ROM_IMAGE_SIZE);
    osh_rom_window(ROM_RAM_END, ROM_LO, ROM_HI);
    osh_prof_reset();
    plant_routine(entry);
}

static void run(uint32_t entry, const char *what) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, ROM_IMAGE_SIZE, entry, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "the probe's %s routine did not return to the sentinel\n", what);
        exit(1);
    }
}

int main(void) {
    probe_require_out_regs();
    g_image = calloc(ROM_IMAGE_SIZE, 1);
    if (!g_image) {
        fprintf(stderr, "probe: could not allocate the %u-byte image\n", ROM_IMAGE_SIZE);
        exit(1);
    }
    osh_schedule(NULL, 0, NULL, 0);     /* rom_mode_probe.c's reason: no inherited schedule */

    /* (1) The map: a RAM PC, a ROM-window PC, and PCs no slot covers. */
    osh_rom_window(ROM_RAM_END, ROM_LO, ROM_HI);
    printf("prof_slots %u\n", osh_prof_slots());
    printf("slot_ram_pc %u\n", osh_prof_slot(RAM_ENTRY));
    printf("slot_rom_pc %u\n", osh_prof_slot(ROM_ENTRY));
    printf("slot_io_pc %u\n", osh_prof_slot(IO_PC));
    printf("slot_above_rom_hi %u\n", osh_prof_slot(ROM_HI));
    osh_rom_window(0, 0, 0);
    printf("slot_rom_pc_rom_mode_off %u\n", osh_prof_slot(ROM_ENTRY));

    /* (2) osh_run tallies a routine in its own slots, and nowhere at the other side's offset. */
    osh_prof_enable(1);
    begin_case(ROM_ENTRY);
    run(ROM_ENTRY, "rom");
    printf("rom_run_cycles %u\n", (unsigned)osh_num_cycles());
    printf("rom_run_rom_slots %u\n", routine_tally(ROM_ROUTINE_SLOT));
    printf("rom_run_ram_slots %u\n", routine_tally(RAM_ROUTINE_SLOT));

    /* (4) ...and a reset clears the ROM slots it filled. */
    osh_prof_reset();
    printf("rom_slots_after_reset %u\n", routine_tally(ROM_ROUTINE_SLOT));

    begin_case(RAM_ENTRY);
    run(RAM_ENTRY, "ram");
    printf("ram_run_cycles %u\n", (unsigned)osh_num_cycles());
    printf("ram_run_ram_slots %u\n", routine_tally(RAM_ROUTINE_SLOT));
    printf("ram_run_rom_slots %u\n", routine_tally(ROM_ROUTINE_SLOT));

    /* (3) Off, nothing is tallied anywhere — for either routine. */
    osh_prof_enable(0);
    begin_case(ROM_ENTRY);
    plant_routine(RAM_ENTRY);
    run(ROM_ENTRY, "rom_off");
    run(RAM_ENTRY, "ram_off");
    printf("off_run_cycles %u\n", (unsigned)osh_num_cycles());
    printf("off_whole_tally %u\n", whole_tally());

    free(g_image);
    return 0;
}
