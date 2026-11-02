/* fdc_model_probe.c — the fixture behind test_fdc_model.py (TRAP_MODEL.md, "Phase 17").
 *
 * Two layers, because the model has two:
 *   - THE CHIP (`model_*` cases): src/fdc.c driven DIRECTLY, register access by register access, over a
 *     bus of this probe's own (a RAM, a port A the case sets) — every command, every status bit, the
 *     DMA's address, count and status, every refusal, the ledger. No CPU: what is pinned is the device.
 *   - THE WIRING (`oracle_*` cases): ../oracle/shim.c running a minimal 68000 floppy driver of this
 *     probe's own (`DRIVER` below, not any ROM's: the kit is project-agnostic) through `osh_run` — the
 *     arming, GPIP's composition with the Phase-7 declaration, the DMA's stores joining the write-set,
 *     a timeout reached by the driver's own count-down, the conflicts, the save/load of the chip, and
 *     UNARMED = the path every access took before the model existed.
 *
 * Output is the line protocol probe_build.run_probe parses:
 *   K <case> <key> <value>             a scalar
 *   L <case> <index> <kind> <a> <b>    one FDC ledger entry, in order (fdc.h's FDC_EV_*)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fdc.h"
#include "os.h"
#include "probe_common.h"

/* ../oracle/shim.c's exports this probe reads (probe_common.h says what such a declaration pins). */
void            osh_fdc_arm(int on);
void            osh_fdc_declare(const uint8_t *chip);
void            osh_fdc_chip_now(uint8_t *out);
uint32_t        osh_fdc_drive(uint32_t drive, uint8_t *image, uint32_t bytes, uint32_t present,
                              uint32_t inserted, uint32_t write_protected, uint32_t read_only);
uint32_t        osh_fdc_log_count(void);
const uint8_t  *osh_fdc_log_kinds(void);
const uint32_t *osh_fdc_log_a(void);
const uint32_t *osh_fdc_log_b(void);
uint32_t        osh_fdc_refused(void);
uint32_t        osh_fdc_refused_at(void);
uint32_t        osh_fdc_conflicts(void);
uint32_t        osh_fdc_conflict_first(void);
void            osh_hw_seed(const uint8_t *values, uint32_t known);
uint32_t        osh_hw_unseeded(void);
uint32_t        osh_hw_stale(void);
void            osh_io_seq(const uint32_t *addrs, const uint32_t *offsets, const uint32_t *lengths,
                           const uint8_t *pool, uint32_t n, uint32_t pool_len);
uint32_t        osh_hw_count(void);
uint32_t        osh_hw_write_count(void);
const uint32_t *osh_hw_write_addrs(void);
void            osh_io_seed(const uint32_t *addrs, const uint8_t *values, const uint8_t *writeback, uint32_t n);
uint32_t        osh_io_unmodeled_reads(void);
uint32_t        osh_io_unmodeled_first(void);
uint32_t        osh_num_writes(void);
const uint32_t *osh_write_addrs(void);

/* ---- the probe's machine ----------------------------------------------------------------------- */
#define RAM_BYTES        0x10000u   /* the chip layer's own RAM: the DMA's whole reach */
#define DMA_BUFFER       0x4000u    /* where a transfer lands, in either layer's RAM */
#define DMA_WRAP_BUFFER  0xfe00u    /* a sector here carries the address into the next 64 KiB */
#define TRACK_BUFFER     0x6000u    /* where the Write Track stream is built */
#define PORT_A_DRIVE_A_SIDE_0 0x05u /* both select lines high but A's; side 0 (bit 0 high) */
#define PORT_A_DRIVE_A_SIDE_1 0x04u
#define PORT_A_DRIVE_B_SIDE_0 0x03u
#define PORT_A_NO_DRIVE       0x07u
#define MODE_COMMAND     0x80u
#define MODE_TRACK       0x82u
#define MODE_SECTOR      0x84u
#define MODE_DATA        0x86u
#define MODE_COUNT       0x90u
#define MODE_HDC_COMMAND 0x88u
#define CMD_RESTORE      0x00u
#define CMD_SEEK         0x10u
#define CMD_SEEK_VERIFY  0x14u
#define CMD_STEP         0x20u
#define CMD_READ         0x80u
#define CMD_READ_MULTI   0x90u
#define CMD_WRITE        0xa0u
#define CMD_READ_ADDRESS 0xc0u
#define CMD_FORCE        0xd0u
#define CMD_FORCE_INDEX  0xd4u      /* a force-interrupt WITH a condition: INTRQ at once */
#define CMD_READ_TRACK   0xe0u
#define CMD_WRITE_TRACK  0xf0u
#define FILL_SEED        0x3bu      /* every image byte is (offset * 7 + FILL_SEED): no two sectors alike */
#define FILL_STRIDE      7u
#define VIRGIN           0xe5u      /* a formatted sector's fill */
#define GAP_BYTE         0x4eu
#define SYNC_PRESET      0xf5u
#define ID_MARK          0xfeu
#define DATA_MARK        0xfbu
#define CRC_BYTES        0xf7u
#define FORMAT_TRACK     3u
#define READ_TRACK       5u
#define READ_SIDE        1u
#define READ_SECTOR      7u
#define GPIP_DECLARED    0xffu      /* what the case declares the other GPIP bits hold */
#define LEDGER_FLOOD     (FDC_LOG_MAX + 1u)
#define TIMEOUT_COUNT    100u       /* the wait's count-down: 99 polls, then the timeout arm */
#define WAIT_COUNT       1000u      /* a wait the chip ends long before its count runs out */
#define MAX_INSNS        2000000u
#define SHORT_TRACK_COUNT 12u       /* 12 x 512 = 6,144 bytes: less than one revolution */
#define FORMAT_COUNT     31u        /* a count comfortably over one revolution (the ROM formatters' own) */
#define ID_WITHOUT_DATA  4          /* the fifth ID is written with no data field after it */
#define BLOCK_ADDR_MID_WORD 0xff860cu   /* a word store here is a store to the address's LOW byte on a 68000 */
#define BLOCK_ADDR_HI_WORD  0xff8608u
#define BLOCK_PROBE_VALUE   0x1234u
#define GPIP_WORD           0xfffa00u

static uint8_t     g_ram[RAM_BYTES];
static uint8_t     g_disk[FDC_IMAGE_BYTES];
static uint8_t     g_pins = PORT_A_DRIVE_A_SIDE_0;
static int         g_pins_known = 1;
static uint32_t    g_stored;
static fdc_device  g_dev;

static void count_store(uint32_t addr) { (void)addr; g_stored++; }
static int pins(uint8_t *value) { *value = g_pins; return g_pins_known; }
static const fdc_bus BUS = { g_ram, RAM_BYTES, count_store, pins };

static long sector_at(unsigned track, unsigned side, unsigned sector) {
    return (long)(((track * FDC_SIDES + side) * FDC_SECTORS + sector - 1) * FDC_SECTOR_BYTES);
}

static void fill_disk(void) {
    for (uint32_t i = 0; i < FDC_IMAGE_BYTES; i++)
        g_disk[i] = (uint8_t)(i * FILL_STRIDE + FILL_SEED);
}

/* The chip layer's fresh device: MR's chip, drive A holding the filled disk, drive B absent. */
static void fresh(void) {
    memset(&g_dev, 0, sizeof g_dev);
    memset(g_ram, 0, sizeof g_ram);
    fill_disk();
    fdc_chip chip;
    fdc_power_on(&chip);
    fdc_enter_run(&g_dev, &chip);
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 0);
    fdc_insert(&g_dev, 1, 0, 0, 0, 0, 0, 0);
    g_pins = PORT_A_DRIVE_A_SIDE_0;
    g_pins_known = 1;
    g_stored = 0;
}

static void wr(uint32_t addr, uint32_t value) { fdc_write(&g_dev, &BUS, addr, 2, value); }
static uint32_t rd(uint32_t addr) { return fdc_read(&g_dev, &BUS, addr, 2); }
static void set_register(uint32_t mode, uint32_t value) { wr(FDC_DMA_MODE, mode); wr(FDC_DMA_DATA, value); }
static void issue(uint32_t command) { set_register(MODE_COMMAND, command); }

/* The DMA set-up every transfer makes, the ST drivers' own shape: the address bytes (lo, mid, hi), the
 * direction toggled twice (the reset), the count; then the sector register and the command. */
static void transfer(uint32_t addr, uint32_t write, uint32_t count, uint32_t sector, uint32_t command) {
    fdc_write(&g_dev, &BUS, FDC_DMA_ADDR_LO, 1, addr);
    fdc_write(&g_dev, &BUS, FDC_DMA_ADDR_MID, 1, addr >> 8);
    fdc_write(&g_dev, &BUS, FDC_DMA_ADDR_HI, 1, addr >> 16);
    uint32_t direction = write ? FDC_MODE_WRITE : 0;
    wr(FDC_DMA_MODE, MODE_COUNT | direction);
    wr(FDC_DMA_MODE, MODE_COUNT | (direction ^ FDC_MODE_WRITE));
    wr(FDC_DMA_MODE, MODE_COUNT | direction);
    wr(FDC_DMA_DATA, count);
    set_register(MODE_SECTOR | direction, sector);
    set_register(MODE_COMMAND | direction, command);
}

/* Move drive A's head (and TR) to `track` by a plain seek. */
static void seek_to(uint32_t track) {
    set_register(MODE_DATA, track);
    issue(CMD_SEEK);
}

static void report_ledger(const char *name, uint32_t n, const uint8_t *kinds, const uint32_t *a, const uint32_t *b) {
    printf("K %s nlog %u\n", name, n);
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u %u\n", name, i, kinds[i], a[i], b[i]);
}

/* Everything the chip layer leaves, after a case. `status` is read LAST and through the bus, so a case
 * that cares about INTRQ before the read reports `intrq` first. */
static void report_model(const char *name) {
    fdc_chip *chip = &g_dev.chip;
    printf("K %s intrq %u\n", name, chip->intrq);
    printf("K %s gpip %u\n", name, chip->intrq ? GPIP_DECLARED & ~FDC_GPIP_INTRQ : GPIP_DECLARED);
    printf("K %s busy %u\n", name, chip->busy_forever);
    printf("K %s track %u\n", name, chip->track);
    printf("K %s sector %u\n", name, chip->sector);
    printf("K %s head_a %u\n", name, chip->head[0]);
    printf("K %s count %u\n", name, chip->count);
    printf("K %s addr %u\n", name, chip->addr);
    printf("K %s stored %u\n", name, g_stored);
    printf("K %s refused %u\n", name, g_dev.refused);
    printf("K %s refused_at %u\n", name, g_dev.refused_at);
    printf("K %s dropped %u\n", name, g_dev.log_dropped);
    report_ledger(name, g_dev.log_n, g_dev.log_kind, g_dev.log_a, g_dev.log_b);
}

/* The status register as the next read sees it, reported after the rest (the read itself clears INTRQ
 * and joins the ledger, which report_model has already printed). */
static void report_status(const char *name) {
    wr(FDC_DMA_MODE, MODE_COMMAND);
    printf("K %s status %u\n", name, rd(FDC_DMA_DATA));
    printf("K %s intrq_after_read %u\n", name, g_dev.chip.intrq);
}

static int disk_sector_is(unsigned track, unsigned side, unsigned sector, const uint8_t *bytes) {
    return memcmp(g_disk + sector_at(track, side, sector), bytes, FDC_SECTOR_BYTES) == 0;
}

static int disk_is_filled(void) {
    for (uint32_t i = 0; i < FDC_IMAGE_BYTES; i++)
        if (g_disk[i] != (uint8_t)(i * FILL_STRIDE + FILL_SEED)) return 0;
    return 1;
}

/* ---- THE CHIP, case by case ------------------------------------------------------------------- */
static void model_power_on(void) {
    fresh();
    report_model("model_power_on");
    printf("K model_power_on dma_status %u\n", rd(FDC_DMA_MODE));
    report_status("model_power_on");
}

static void model_restore(void) {
    fresh();
    g_dev.chip.head[0] = 12;
    g_dev.chip.track = 12;
    issue(CMD_RESTORE);
    report_model("model_restore");
    report_status("model_restore");
}

static void model_restore_absent_motor_on(void) {
    fresh();
    g_dev.chip.motor = 1;
    g_dev.chip.track = 7;
    g_pins = PORT_A_DRIVE_B_SIDE_0;
    issue(CMD_RESTORE);
    report_model("model_restore_absent_motor_on");
    report_status("model_restore_absent_motor_on");
}

static void model_restore_absent_motor_off(void) {
    fresh();
    g_pins = PORT_A_DRIVE_B_SIDE_0;
    issue(CMD_RESTORE);
    set_register(MODE_TRACK, 9);                  /* ignored while busy */
    issue(CMD_SEEK);                              /* ...and so is any command but a force */
    report_model("model_restore_absent_motor_off");
    report_status("model_restore_absent_motor_off");
    issue(CMD_FORCE);
    report_model("model_restore_absent_forced");
    report_status("model_restore_absent_forced");
}

static void model_no_drive_selected(void) {
    fresh();
    g_dev.chip.motor = 1;
    g_pins = PORT_A_NO_DRIVE;
    issue(CMD_RESTORE);
    report_model("model_no_drive_selected");
    report_status("model_no_drive_selected");
}

static void model_empty_drive(void) {
    fresh();
    fdc_insert(&g_dev, 0, 0, 0, 1, 0, 0, 0);         /* drive A present, no disk: no index pulse */
    issue(CMD_RESTORE);
    report_model("model_empty_spin_up");
    issue(CMD_FORCE);
    issue(CMD_RESTORE);                           /* the motor is on now: a restore needs no index */
    report_model("model_empty_restore");
    report_status("model_empty_restore");         /* an empty bay reads write-protected */
    issue(CMD_SEEK_VERIFY);                       /* ...but an ID search does */
    report_model("model_empty_verify");
}

static void model_seek(void) {
    fresh();
    seek_to(READ_TRACK);
    report_model("model_seek");
    report_status("model_seek");
    set_register(MODE_DATA, READ_TRACK);
    issue(CMD_SEEK_VERIFY);
    report_model("model_seek_verify");
    report_status("model_seek_verify");
    set_register(MODE_TRACK, READ_TRACK - 2);     /* TR disagrees with the head: the verify finds no ID */
    set_register(MODE_DATA, READ_TRACK - 2);
    issue(CMD_SEEK_VERIFY);
    report_model("model_seek_verify_mismatch");
    report_status("model_seek_verify_mismatch");
}

static void model_seek_clamped(void) {
    fresh();
    set_register(MODE_DATA, 200);
    issue(CMD_SEEK_VERIFY);                       /* the head stops at 85; no track 85 on the medium */
    report_model("model_seek_clamped");
    report_status("model_seek_clamped");
}

static void model_read_sector(void) {
    fresh();
    seek_to(READ_TRACK);
    g_pins = PORT_A_DRIVE_A_SIDE_1;
    g_dev.log_n = 0;
    transfer(DMA_BUFFER, 0, 2, READ_SECTOR, CMD_READ);
    report_model("model_read_sector");
    printf("K model_read_sector same_bytes %d\n",
           memcmp(g_ram + DMA_BUFFER, g_disk + sector_at(READ_TRACK, READ_SIDE, READ_SECTOR), FDC_SECTOR_BYTES) == 0);
    printf("K model_read_sector dma_status %u\n", rd(FDC_DMA_MODE));
    report_status("model_read_sector");
    printf("K model_read_sector dma_status_after_status %u\n", rd(FDC_DMA_MODE));
}

static void model_read_rnf(void) {
    fresh();
    transfer(DMA_BUFFER, 0, 1, FDC_SECTORS + 1, CMD_READ);
    report_model("model_read_rnf");
    report_status("model_read_rnf");
}

static void model_read_zero_count(void) {
    fresh();
    transfer(DMA_BUFFER, 0, 0, 1, CMD_READ);
    report_model("model_read_zero_count");
    printf("K model_read_zero_count dma_status %u\n", rd(FDC_DMA_MODE));
    wr(FDC_DMA_MODE, MODE_COUNT | FDC_MODE_WRITE);   /* the toggle resets the DMA's error */
    printf("K model_read_zero_count dma_status_after_toggle %u\n", rd(FDC_DMA_MODE));
}

static void model_read_address_wraps(void) {
    fresh();
    transfer(DMA_WRAP_BUFFER, 0, 1, 1, CMD_READ);
    printf("K model_read_address_wraps hi %u\n", fdc_read(&g_dev, &BUS, FDC_DMA_ADDR_HI, 1));
    printf("K model_read_address_wraps mid %u\n", fdc_read(&g_dev, &BUS, FDC_DMA_ADDR_MID, 1));
    printf("K model_read_address_wraps lo %u\n", fdc_read(&g_dev, &BUS, FDC_DMA_ADDR_LO, 1));
    report_model("model_read_address_wraps");
}

static void model_read_odd_address(void) {
    fresh();
    transfer(DMA_BUFFER + 1, 0, 1, 1, CMD_READ);     /* bit 0 of the low byte is not wired */
    report_model("model_read_odd_address");
}

static void model_read_refusals(void) {
    fresh();
    transfer(DMA_BUFFER, 1, 1, 1, CMD_READ);         /* a read with the DMA set to write */
    report_model("model_read_wrong_direction");
    fresh();
    transfer(RAM_BYTES - FDC_SECTOR_BYTES / 2, 0, 1, 1, CMD_READ);
    report_model("model_read_off_ram");
}

static void model_write_sector(void) {
    fresh();
    for (uint32_t i = 0; i < FDC_SECTOR_BYTES; i++)
        g_ram[DMA_BUFFER + i] = (uint8_t)(i ^ VIRGIN);
    transfer(DMA_BUFFER, 1, 1, 4, CMD_WRITE);
    report_model("model_write_sector");
    printf("K model_write_sector written %d\n", disk_sector_is(0, 0, 4, g_ram + DMA_BUFFER));
    report_status("model_write_sector");
}

static void model_write_protected(void) {
    fresh();
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 1, 0);
    transfer(DMA_BUFFER, 1, 1, 4, CMD_WRITE);
    report_model("model_write_protected");
    printf("K model_write_protected disk_untouched %d\n", disk_is_filled());
    report_status("model_write_protected");
}

static void model_write_refusals(void) {
    fresh();
    transfer(DMA_BUFFER, 1, 0, 4, CMD_WRITE);
    report_model("model_write_no_count");
    printf("K model_write_no_count disk_untouched %d\n", disk_is_filled());
    fresh();
    transfer(DMA_BUFFER, 0, 1, 4, CMD_WRITE);
    report_model("model_write_wrong_direction");
}

/* A track in the ROM drivers' own layout: gap, then per ID an ID field and (unless `no_data_at` names its
 * index) a data field. `ids` are the sector numbers in the order written. */
static uint32_t build_ids(const uint8_t *ids, unsigned n_ids, uint8_t id_track, uint8_t id_side, uint8_t fill,
                          int no_data_at) {
    uint8_t *at = g_ram + TRACK_BUFFER;
    uint32_t n = 0;
    memset(at, GAP_BYTE, FDC_TRACK_BYTES);
    #define PUT(byte, times) do { for (uint32_t k = 0; k < (times); k++) at[n++] = (uint8_t)(byte); } while (0)
    PUT(GAP_BYTE, 60);
    for (unsigned i = 0; i < n_ids; i++) {
        PUT(0, 12); PUT(SYNC_PRESET, 3); PUT(ID_MARK, 1);
        PUT(id_track, 1); PUT(id_side, 1); PUT(ids[i], 1); PUT(2, 1); PUT(CRC_BYTES, 1);
        PUT(GAP_BYTE, 22);
        if ((int)i != no_data_at) {
            PUT(0, 12); PUT(SYNC_PRESET, 3); PUT(DATA_MARK, 1);
            PUT(fill, FDC_SECTOR_BYTES); PUT(CRC_BYTES, 1);
        }
        PUT(GAP_BYTE, 40);
    }
    #undef PUT
    return n;
}

static const uint8_t NINE[] = { 1, 2, 3, 4, 5, 6, 7, 8, 9 };
static const uint8_t NINE_AND_A_REPEAT[] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 1 };
#define NO_MISSING_DATA (-1)

static uint32_t build_track(uint8_t id_track, uint8_t id_side, uint8_t fill) {
    return build_ids(NINE, FDC_SECTORS, id_track, id_side, fill, NO_MISSING_DATA);
}

static int track_is(unsigned track, uint8_t fill) {
    for (unsigned sector = 1; sector <= FDC_SECTORS; sector++)
        for (uint32_t i = 0; i < FDC_SECTOR_BYTES; i++)
            if (g_disk[sector_at(track, 0, sector) + i] != fill) return 0;
    return 1;
}

static void model_write_track(void) {
    fresh();
    seek_to(FORMAT_TRACK);
    g_dev.log_n = 0;
    build_track(FORMAT_TRACK, 0, VIRGIN);
    transfer(TRACK_BUFFER, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_write_track");
    printf("K model_write_track formatted %d\n", track_is(FORMAT_TRACK, VIRGIN));
    printf("K model_write_track side_1_untouched %d\n",
           g_disk[sector_at(FORMAT_TRACK, 1, 1)] == (uint8_t)(sector_at(FORMAT_TRACK, 1, 1) * FILL_STRIDE + FILL_SEED));
    report_status("model_write_track");

    fresh();
    seek_to(FORMAT_TRACK);
    build_track(FORMAT_TRACK + 4, 0, VIRGIN);        /* an ID naming another track */
    transfer(TRACK_BUFFER, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_write_track_other_track");
    printf("K model_write_track_other_track disk_untouched %d\n", disk_is_filled());

    fresh();
    seek_to(FORMAT_TRACK);
    build_track(FORMAT_TRACK, 0, SYNC_PRESET);       /* data the chip would write as marks */
    transfer(TRACK_BUFFER, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_write_track_special_data");
    printf("K model_write_track_special_data disk_untouched %d\n", disk_is_filled());

    fresh();
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 1, 0);
    build_track(0, 0, VIRGIN);
    transfer(TRACK_BUFFER, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_write_track_protected");
    printf("K model_write_track_protected disk_untouched %d\n", disk_is_filled());
}

static void model_unmodelled_commands(void) {
    static const struct { const char *name; uint32_t command; } cases[] = {
        { "model_step", CMD_STEP }, { "model_read_multi", CMD_READ_MULTI },
        { "model_read_address", CMD_READ_ADDRESS }, { "model_read_track", CMD_READ_TRACK },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        fresh();
        g_dev.chip.motor = 1;
        issue(cases[i].command);
        report_model(cases[i].name);
    }
}

static void model_access_refusals(void) {
    fresh();
    fdc_read(&g_dev, &BUS, FDC_DMA_DATA, 1);
    report_model("model_byte_read");
    fresh();
    fdc_write(&g_dev, &BUS, FDC_DMA_MODE, 1, MODE_COMMAND);
    report_model("model_byte_write");
    fresh();
    fdc_read(&g_dev, &BUS, FDC_DMA_DATA, 4);
    report_model("model_long_read");
    fresh();
    wr(FDC_DMA_MODE, MODE_COUNT);
    rd(FDC_DMA_DATA);
    report_model("model_count_read");
    fresh();
    wr(FDC_DMA_MODE, MODE_HDC_COMMAND);
    rd(FDC_DMA_DATA);
    report_model("model_hdc_read");
    fresh();
    g_pins_known = 0;
    issue(CMD_RESTORE);
    report_model("model_port_a_unknown");
}

static void model_hdc_write_and_long(void) {
    fresh();
    wr(FDC_DMA_MODE, MODE_HDC_COMMAND);
    fdc_write(&g_dev, &BUS, FDC_DMA_DATA, 4, 0x0008008au);   /* move.l: the data word, then the mode */
    report_model("model_hdc_long_write");
    printf("K model_hdc_long_write mode %u\n", g_dev.chip.mode);
    fresh();
    wr(FDC_DMA_MODE, MODE_DATA);
    fdc_write(&g_dev, &BUS, FDC_DMA_DATA, 4, 0x00120080u);   /* data := $12, then the command register */
    printf("K model_fdc_long_write data %u\n", g_dev.chip.data);
    printf("K model_fdc_long_write mode %u\n", g_dev.chip.mode);
}

static void model_registers_and_residue(void) {
    fresh();
    set_register(MODE_TRACK, 0x2a);
    set_register(MODE_SECTOR, 0x07);
    set_register(MODE_DATA, 0x99);
    wr(FDC_DMA_MODE, MODE_TRACK);
    printf("K model_registers track %u\n", rd(FDC_DMA_DATA));
    wr(FDC_DMA_MODE, MODE_SECTOR);
    printf("K model_registers sector %u\n", rd(FDC_DMA_DATA));
    wr(FDC_DMA_MODE, MODE_DATA);
    printf("K model_registers data %u\n", rd(FDC_DMA_DATA));
    printf("K model_registers dma_status %u\n", rd(FDC_DMA_MODE));   /* the residue: the last byte, $99 */
    report_model("model_registers");
}

static void model_force_with_condition(void) {
    fresh();
    issue(CMD_FORCE_INDEX);
    report_model("model_force_with_condition");
}

static void model_polls(void) {
    fresh();
    fdc_gpip(&g_dev, GPIP_DECLARED);
    fdc_gpip(&g_dev, GPIP_DECLARED);
    fdc_gpip(&g_dev, GPIP_DECLARED);
    seek_to(1);
    fdc_gpip(&g_dev, GPIP_DECLARED);
    fdc_gpip(&g_dev, 0);
    report_model("model_polls");
}

static void model_ledger_overflow(void) {
    fresh();
    wr(FDC_DMA_MODE, MODE_TRACK);
    for (uint32_t i = 0; i < LEDGER_FLOOD; i++)
        rd(FDC_DMA_DATA);
    printf("K model_ledger_overflow nlog %u\n", g_dev.log_n);
    printf("K model_ledger_overflow dropped %u\n", g_dev.log_dropped);
}

static void model_geometry(void) {
    fresh();
    printf("K model_geometry short %u\n", fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES - 1, 1, 1, 0, 0));
    printf("K model_geometry long %u\n", fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES + 1, 1, 1, 0, 0));
    printf("K model_geometry no_image %u\n", fdc_insert(&g_dev, 0, 0, FDC_IMAGE_BYTES, 1, 1, 0, 0));
    printf("K model_geometry third_drive %u\n", fdc_insert(&g_dev, FDC_DRIVES, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 0));
    printf("K model_geometry empty_bay %u\n", fdc_insert(&g_dev, 0, 0, 0, 1, 0, 0, 0));
    printf("K model_geometry the_disk %u\n", fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 0));
}

/* ---- the fix pass's rows: every Write Track a .ST cannot hold, the block's other accesses, the rest --- */
static void track_case(const char *name, const uint8_t *ids, unsigned n_ids, uint8_t id_side, int no_data_at,
                       uint32_t count) {
    fresh();
    seek_to(FORMAT_TRACK);
    g_dev.log_n = 0;
    build_ids(ids, n_ids, FORMAT_TRACK, id_side, VIRGIN, no_data_at);
    transfer(TRACK_BUFFER, 1, count, 1, CMD_WRITE_TRACK);
    report_model(name);
    printf("K %s disk_untouched %d\n", name, disk_is_filled());
}

static void model_write_track_refusals(void) {
    track_case("model_write_track_short_count", NINE, FDC_SECTORS, 0, NO_MISSING_DATA, SHORT_TRACK_COUNT);
    track_case("model_write_track_eight_sectors", NINE, FDC_SECTORS - 1, 0, NO_MISSING_DATA, FORMAT_COUNT);
    track_case("model_write_track_duplicate_id", NINE_AND_A_REPEAT, FDC_SECTORS + 1, 0, NO_MISSING_DATA, FORMAT_COUNT);
    track_case("model_write_track_other_side", NINE, FDC_SECTORS, 1, NO_MISSING_DATA, FORMAT_COUNT);
    track_case("model_write_track_id_without_data", NINE, FDC_SECTORS, 0, ID_WITHOUT_DATA, FORMAT_COUNT);
    fresh();
    seek_to(FORMAT_TRACK);
    g_dev.log_n = 0;
    transfer(RAM_BYTES - FDC_TRACK_BYTES / 2, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_write_track_off_ram");
}

static void model_write_off_ram(void) {
    fresh();
    transfer(RAM_BYTES - FDC_SECTOR_BYTES / 2, 1, 1, 4, CMD_WRITE);
    report_model("model_write_off_ram");
    printf("K model_write_off_ram disk_untouched %d\n", disk_is_filled());
}

static void model_read_only(void) {
    fresh();
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 1);
    transfer(DMA_BUFFER, 0, 1, 1, CMD_READ);                     /* a read is served */
    printf("K model_read_only_read same_bytes %d\n",
           memcmp(g_ram + DMA_BUFFER, g_disk + sector_at(0, 0, 1), FDC_SECTOR_BYTES) == 0);
    report_model("model_read_only_read");
    fresh();
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 1);
    transfer(DMA_BUFFER, 1, 1, 4, CMD_WRITE);
    report_model("model_read_only_write");
    printf("K model_read_only_write disk_untouched %d\n", disk_is_filled());
    fresh();
    fdc_insert(&g_dev, 0, g_disk, FDC_IMAGE_BYTES, 1, 1, 0, 1);
    build_track(0, 0, VIRGIN);
    transfer(TRACK_BUFFER, 1, FORMAT_COUNT, 1, CMD_WRITE_TRACK);
    report_model("model_read_only_track");
    printf("K model_read_only_track disk_untouched %d\n", disk_is_filled());
}

/* A force after a type II command: the status reverts to TYPE I — live TR00 off the selected head. */
static void model_force_after_read(void) {
    fresh();
    transfer(DMA_BUFFER, 0, 1, 1, CMD_READ);
    issue(CMD_FORCE);
    report_model("model_force_after_read");
    report_status("model_force_after_read");
}

/* The rest of the DMA block: no register the model serves there, so every access is refused by name. */
static void model_block_accesses(void) {
    static const struct { const char *name; uint32_t addr; unsigned width; int write; } cases[] = {
        { "model_word_write_address_byte", BLOCK_ADDR_MID_WORD, 2, 1 },
        { "model_byte_write_data_low", FDC_DMA_DATA + 1, 1, 1 },
        { "model_word_read_address_hi_word", BLOCK_ADDR_HI_WORD, 2, 0 },
        { "model_byte_read_block_start", FDC_BLOCK_LO, 1, 0 },
        { "model_long_write_mode", FDC_DMA_MODE, 4, 1 },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        fresh();
        if (cases[i].write) fdc_write(&g_dev, &BUS, cases[i].addr, cases[i].width, BLOCK_PROBE_VALUE);
        else                fdc_read(&g_dev, &BUS, cases[i].addr, cases[i].width);
        report_model(cases[i].name);
    }
    printf("K model_block_ownership below %d\n", fdc_owns(FDC_BLOCK_LO - 1, 1));
    printf("K model_block_ownership straddle %d\n", fdc_owns(FDC_BLOCK_LO - 2, 4));
    printf("K model_block_ownership last %d\n", fdc_owns(FDC_BLOCK_HI - 1, 1));
    printf("K model_block_ownership above %d\n", fdc_owns(FDC_BLOCK_HI, 1));
    printf("K model_block_ownership gpip_word %d\n", fdc_covers_gpip(FDC_MFP_GPIP - 1, 2));
    printf("K model_block_ownership gpip_byte %d\n", fdc_covers_gpip(FDC_MFP_GPIP, 1));
}

/* ---- THE WIRING, through the oracle ----------------------------------------------------------- */
/* The probe's own minimal floppy driver, assembled from (m68k-elf-as -m68000):
 *         move.b  #14,$ff8800          ; select PSG port A ...
 *         move.b  d4,$ff8802           ; ... and drive the pins (d4)
 *         move.b  d5,$ff860d           ; the DMA address (d5), low byte first
 *         lsr.l   #8,d5
 *         move.b  d5,$ff860b
 *         lsr.l   #8,d5
 *         move.b  d5,$ff8609
 *         move.w  d2,$ff8606           ; the count register in the direction (d2: $90 / $190) ...
 *         eori.w  #$100,d2
 *         move.w  d2,$ff8606           ; ... toggled twice: the DMA reset
 *         eori.w  #$100,d2
 *         move.w  d2,$ff8606
 *         move.w  d3,$ff8604           ; the count (d3)
 *         andi.w  #$100,d2
 *         ori.w   #$84,d2
 *         move.w  d2,$ff8606
 *         move.w  d6,$ff8604           ; the sector register (d6)
 *         andi.w  #$100,d2
 *         ori.w   #$80,d2
 *         move.w  d2,$ff8606
 *         move.w  d0,$ff8604           ; the command (d0)
 * wait:   subq.l  #1,d7                ; the count-down (d7) ...
 *         beq.s   timeout
 *         btst    #5,$fffa01           ; ... on GPIP bit 5, active low
 *         bne.s   wait
 *         move.w  $ff8604,d1           ; the status
 *         rts
 * timeout: move.w #$d0,$ff8604         ; the driver's own timeout: force-interrupt
 *         move.w  $ff8604,d1
 *         moveq   #-1,d0
 *         rts
 */
static const uint16_t DRIVER[] = {
    0x13fc, 0x000e, 0x00ff, 0x8800, 0x13c4, 0x00ff, 0x8802, 0x13c5, 0x00ff, 0x860d, 0xe08d, 0x13c5,
    0x00ff, 0x860b, 0xe08d, 0x13c5, 0x00ff, 0x8609, 0x33c2, 0x00ff, 0x8606, 0x0a42, 0x0100, 0x33c2,
    0x00ff, 0x8606, 0x0a42, 0x0100, 0x33c2, 0x00ff, 0x8606, 0x33c3, 0x00ff, 0x8604, 0x0242, 0x0100,
    0x0042, 0x0084, 0x33c2, 0x00ff, 0x8606, 0x33c6, 0x00ff, 0x8604, 0x0242, 0x0100, 0x0042, 0x0080,
    0x33c2, 0x00ff, 0x8606, 0x33c0, 0x00ff, 0x8604, 0x5387, 0x6712, 0x0839, 0x0005, 0x00ff, 0xfa01,
    0x66f2, 0x3239, 0x00ff, 0x8604, 0x4e75, 0x33fc, 0x00d0, 0x00ff, 0x8604, 0x3239, 0x00ff, 0x8604,
    0x70ff, 0x4e75,
};

static void plant_driver(void) {
    for (uint32_t i = 0; i < sizeof DRIVER / sizeof DRIVER[0]; i++)
        plant_word(PROBE_ENTRY + 2 * i, DRIVER[i]);
}

/* One oracle run of whatever is planted, the driver's registers as given. */
typedef struct { uint32_t command, count_mode, count, pins, addr, sector, wait; } call;

static void run_planted(const char *name, const call *c, uint32_t *out) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0};
    if (c) {
        dregs[0] = c->command; dregs[2] = c->count_mode; dregs[3] = c->count; dregs[4] = c->pins;
        dregs[5] = c->addr; dregs[6] = c->sector; dregs[7] = c->wait;
    }
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs, PROBE_SP, PROBE_SENTINEL, 0, MAX_INSNS, out)) {
        fprintf(stderr, "%s: the planted routine did not return to the sentinel\n", name);
        exit(1);
    }
}

static void declare_gpip(int declared) {
    uint8_t values[OS_HW_NSLOTS] = {0};
    values[OS_HW_SLOT_MFP_GPIP] = GPIP_DECLARED;
    osh_hw_seed(values, declared ? 1u << OS_HW_SLOT_MFP_GPIP : 0u);
}

static void report_oracle(const char *name, const uint32_t *out) {
    printf("K %s d0 %u\n", name, out[0]);
    printf("K %s d1 %u\n", name, out[1] & 0xffffu);
    printf("K %s refused %u\n", name, osh_fdc_refused());
    printf("K %s refused_at %u\n", name, osh_fdc_refused_at());
    printf("K %s conflicts %u\n", name, osh_fdc_conflicts());
    printf("K %s conflict_first %u\n", name, osh_fdc_conflict_first());
    printf("K %s hw_unseeded %u\n", name, osh_hw_unseeded());
    printf("K %s hw_stale %u\n", name, osh_hw_stale());
    printf("K %s hw_nlog %u\n", name, osh_hw_count());
    printf("K %s io_unmodeled %u\n", name, osh_io_unmodeled_reads());
    printf("K %s io_unmodeled_first %u\n", name, osh_io_unmodeled_first());
    uint32_t in_buffer = 0, n = osh_num_writes();
    const uint32_t *writes = osh_write_addrs();
    for (uint32_t i = 0; i < n; i++)
        in_buffer += writes[i] >= DMA_BUFFER && writes[i] < DMA_BUFFER + FDC_SECTOR_BYTES;
    printf("K %s stored_in_buffer %u\n", name, in_buffer);
    printf("K %s hw_writes %u\n", name, osh_hw_write_count());
    report_ledger(name, osh_fdc_log_count(), osh_fdc_log_kinds(), osh_fdc_log_a(), osh_fdc_log_b());
}

/* UNARMED: the path every $ff8604 access took before Phase 17 — a read is an unmodeled 0, counted; a
 * write is dropped into the Phase-10 ledger; the FDC ledger is empty. Run before any arming, and again
 * after an arm/disarm, which must leave exactly that. */
static void oracle_unarmed(const char *read_case, const char *write_case) {
    uint32_t out[OUT_REGS] = {0};
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVE_W_ABSL_TO_D1);
    plant_long(PROBE_ENTRY + 2, FDC_DMA_DATA);
    plant_rts(PROBE_ENTRY + 6);
    run_planted(read_case, 0, out);
    report_oracle(read_case, out);
    emit_write_word(PROBE_ENTRY, MODE_COMMAND, FDC_DMA_MODE);
    plant_rts(PROBE_ENTRY + 8);
    run_planted(write_case, 0, out);
    report_oracle(write_case, out);
    printf("K %s first_hw_write %u\n", write_case, osh_hw_write_addrs()[0]);
}

/* Arm with drive A as given (present / holding the filled disk) and drive B absent. */
static void arm(int present_a, int inserted_a) {
    fill_disk();
    osh_fdc_arm(1);
    osh_fdc_drive(0, inserted_a ? g_disk : 0, inserted_a ? FDC_IMAGE_BYTES : 0, present_a, inserted_a, 0, 0);
    osh_fdc_drive(1, 0, 0, 0, 0, 0, 0);
}

static void oracle_driver_cases(void) {
    uint32_t out[OUT_REGS] = {0};
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_driver();
    declare_gpip(1);

    /* A sector read through the DMA: the bytes land in the probe's RAM and join the write-set. */
    arm(1, 1);
    call read = { CMD_READ, MODE_COUNT, 1, PORT_A_DRIVE_A_SIDE_0, DMA_BUFFER, 1, WAIT_COUNT };
    run_planted("oracle_read", &read, out);
    report_oracle("oracle_read", out);
    printf("K oracle_read same_bytes %d\n",
           memcmp(g_image + DMA_BUFFER, g_disk + sector_at(0, 0, 1), FDC_SECTOR_BYTES) == 0);

    /* A drive missing, the motor off: the spin-up never ends, the driver's count-down runs out, its
     * force-interrupt ends the command. */
    arm(0, 0);
    call absent = { CMD_RESTORE, MODE_COUNT, 0, PORT_A_DRIVE_A_SIDE_0, DMA_BUFFER, 1, TIMEOUT_COUNT };
    run_planted("oracle_absent_timeout", &absent, out);
    report_oracle("oracle_absent_timeout", out);

    /* ...the same restore from a chip whose motor a previous run left on — CARRIED by declaring that
     * run's chip: 255 steps with no TR00, the seek error, no timeout. */
    uint8_t chip[sizeof(fdc_chip)];
    osh_fdc_chip_now(chip);
    osh_fdc_declare(chip);
    run_planted("oracle_absent_carried_motor_on", &absent, out);
    report_oracle("oracle_absent_carried_motor_on", out);
    /* ...and the declaration is re-installed per run, not consumed: the same run again, the same answer. */
    run_planted("oracle_absent_carried_again", &absent, out);
    report_oracle("oracle_absent_carried_again", out);

    /* A drive present with no disk: the same timeout road. */
    arm(1, 0);
    run_planted("oracle_empty_timeout", &absent, out);
    report_oracle("oracle_empty_timeout", out);

    /* GPIP's other bits undeclared: Phase 7's refusal, kept for the declared half. */
    arm(1, 1);
    declare_gpip(0);
    run_planted("oracle_gpip_undeclared", &read, out);
    report_oracle("oracle_gpip_undeclared", out);
    declare_gpip(1);

    /* A declaration on a register the armed model owns: counted as a conflict, never silently bypassed. */
    uint32_t addr = FDC_DMA_DATA;
    uint8_t value = 0, writeback = 0;
    osh_io_seed(&addr, &value, &writeback, 1);
    run_planted("oracle_conflict", &read, out);
    report_oracle("oracle_conflict", out);
    osh_io_seed(&addr, &value, &writeback, 0);

    /* A byte access to $ff8604: the ST's bus error, refused. */
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVE_B_ABSL_TO_D1);
    plant_long(PROBE_ENTRY + 2, FDC_DMA_DATA);
    plant_rts(PROBE_ENTRY + 6);
    run_planted("oracle_byte_access", 0, out);
    report_oracle("oracle_byte_access", out);
    osh_fdc_arm(0);
}

/* The oracle-side rows of the fix pass: the move.l hook, GPIP's stale rule and its sequence conflict, the
 * bays forgotten across a re-arm, a wide GPIP read, a word into the address bytes. */
static void plant_words(const uint16_t *words, size_t n) {
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    for (size_t i = 0; i < n; i++)
        plant_word(PROBE_ENTRY + 2 * (uint32_t)i, words[i]);
}

static void oracle_fix_cases(void) {
    uint32_t out[OUT_REGS] = {0};
    /* `move.w #$88,$ff8606 / move.l #$0008008a,$ff8604 / rts`: the ACSI idiom, through write_32. */
    static const uint16_t LONG_WRITE[] = { 0x33fc, 0x0088, 0x00ff, 0x8606, 0x23fc, 0x0008, 0x008a, 0x00ff, 0x8604,
                                           0x4e75 };
    /* `move.b #$ff,$fffa01 / btst #5,$fffa01 / rts`: GPIP read after the run stored to it. */
    static const uint16_t GPIP_STALE[] = { 0x13fc, 0x00ff, 0x00ff, 0xfa01, 0x0839, 0x0005, 0x00ff, 0xfa01, 0x4e75 };
    declare_gpip(1);
    arm(1, 1);
    plant_words(LONG_WRITE, sizeof LONG_WRITE / sizeof LONG_WRITE[0]);
    run_planted("oracle_long_write", 0, out);
    report_oracle("oracle_long_write", out);
    plant_words(GPIP_STALE, sizeof GPIP_STALE / sizeof GPIP_STALE[0]);
    run_planted("oracle_gpip_stale", 0, out);
    report_oracle("oracle_gpip_stale", out);

    /* A SEQUENCE on GPIP while armed: a conflict, named. */
    uint32_t addr = FDC_MFP_GPIP, offset = 0, length = 1;
    uint8_t pool = GPIP_DECLARED;
    osh_io_seq(&addr, &offset, &length, &pool, 1, 1);
    run_planted("oracle_gpip_sequence_conflict", 0, out);
    report_oracle("oracle_gpip_sequence_conflict", out);
    osh_io_seq(&addr, &offset, &length, &pool, 0, 0);

    /* `move.w $fffa00,d1`: a word over GPIP — refused, never a false INTRQ. */
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_word(PROBE_ENTRY, MOVE_W_ABSL_TO_D1);
    plant_long(PROBE_ENTRY + 2, GPIP_WORD);
    plant_rts(PROBE_ENTRY + 6);
    run_planted("oracle_gpip_word_read", 0, out);
    report_oracle("oracle_gpip_word_read", out);

    /* `move.w #$1234,$ff860c`: a word into the address bytes — refused, not dropped. */
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    emit_write_word(PROBE_ENTRY, BLOCK_PROBE_VALUE, BLOCK_ADDR_MID_WORD);
    plant_rts(PROBE_ENTRY + 8);
    run_planted("oracle_word_into_address_bytes", 0, out);
    report_oracle("oracle_word_into_address_bytes", out);

    /* Disarm and re-arm with no bay declared: the disk lent before is FORGOTTEN — the read hangs and the
     * driver's own count-down times out, where a kept bay would have read the old image. */
    osh_fdc_arm(0);
    osh_fdc_arm(1);
    memset(g_image, 0, PROBE_IMAGE_SIZE);
    plant_driver();
    call read = { CMD_READ, MODE_COUNT, 1, PORT_A_DRIVE_A_SIDE_0, DMA_BUFFER, 1, TIMEOUT_COUNT };
    run_planted("oracle_rearm_forgets_bays", &read, out);
    report_oracle("oracle_rearm_forgets_bays", out);
    osh_fdc_arm(0);
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    model_power_on();
    model_restore();
    model_restore_absent_motor_on();
    model_restore_absent_motor_off();
    model_no_drive_selected();
    model_empty_drive();
    model_seek();
    model_seek_clamped();
    model_read_sector();
    model_read_rnf();
    model_read_zero_count();
    model_read_address_wraps();
    model_read_odd_address();
    model_read_refusals();
    model_write_sector();
    model_write_protected();
    model_write_refusals();
    model_write_track();
    model_unmodelled_commands();
    model_access_refusals();
    model_hdc_write_and_long();
    model_registers_and_residue();
    model_force_with_condition();
    model_polls();
    model_ledger_overflow();
    model_geometry();
    model_write_track_refusals();
    model_write_off_ram();
    model_read_only();
    model_force_after_read();
    model_block_accesses();

    oracle_unarmed("oracle_unarmed_read", "oracle_unarmed_write");
    oracle_driver_cases();
    oracle_fix_cases();
    oracle_unarmed("oracle_disarmed_read", "oracle_disarmed_write");
    return 0;
}
