/* fdc.c — the WD1772 + ST DMA, zero-time (TRAP_MODEL.md, "Phase 17"). include/fdc.h says what it is
 * and what it is not; this file is the chip's semantics, and every rule in it names its source: the WD1772
 * datasheet, Hatari's fdc.c where the datasheet is silent and Hatari was checked on a real STF, or the
 * ruling (R-D4-1) where the model had to choose — whose standing rule is that an arm the model does not
 * describe is REFUSED BY NAME, never answered with an invented status. */
#include <string.h>

#include "fdc.h"

/* ---- command bytes ------------------------------------------------------------------------------ */
#define CMD_TYPE_2_OR_3   0x80u     /* bit 7 clear: a type I command */
#define CMD_KIND_MASK     0xf0u
#define CMD_RESTORE       0x00u
#define CMD_SEEK          0x10u
#define CMD_FORCE         0xd0u
#define CMD_TYPE2_MASK    0xe0u
#define CMD_READ_SECTOR   0x80u
#define CMD_WRITE_SECTOR  0xa0u
#define CMD_WRITE_TRACK   0xf0u
#define CMD_NO_SPIN_UP    0x08u     /* h: the motor is taken as already up to speed */
#define CMD_VERIFY        0x04u     /* V (type I): read an ID field to verify the track */
#define CMD_MULTIPLE      0x10u     /* m (type II): multi-sector — never issued, refused */
#define CMD_FORCE_COND    0x0fu     /* force-interrupt conditions: any set one is an INTRQ condition */

/* ---- what Write Track writes for a byte (WD1772 datasheet, "Write Track") ------------------------- */
#define WT_SYNC           0xf5u     /* writes $A1 with a missing clock and presets the CRC */
#define WT_SPECIAL_FIRST  0xf5u     /* $F5..$F7 are never data: a sector holding one cannot be written so */
#define WT_SPECIAL_LAST   0xf7u
#define MARK_ID           0xfeu
#define MARK_DATA         0xfbu
#define MARK_BYTES        2u        /* `$F5 $FE` or `$F5 $FB` */
#define ID_FIELD_BYTES    4u        /* track, side, sector, size code */
#define SIZE_CODE_512     2u
#define ALL_SECTORS       ((1u << (FDC_SECTORS + 1)) - 2u)   /* bits 1..9: the found-mask of a whole track */
#define REFUSAL_TRACK_SHIFT 16
#define REFUSAL_SIDE_SHIFT  8
#define NO_ID             FDC_ADDR_MASK                     /* a refusal detail when the ID itself is cut off */

/* ---- the ledger, and the run's refusal ----------------------------------------------------------- */
static void refuse(fdc_device *dev, uint32_t why, uint32_t detail) {
    if (!dev->refused) {
        dev->refused = why;
        dev->refused_at = detail;
    }
}

static void refuse_access(fdc_device *dev, uint32_t a, unsigned width) {
    refuse(dev, FDC_REFUSE_ACCESS, (uint32_t)width << FDC_ACCESS_WIDTH_SHIFT | a);
}

void fdc_refuse_gpip_wide(fdc_device *dev, uint32_t a, unsigned width) {
    refuse(dev, FDC_REFUSE_GPIP_WIDE, (uint32_t)width << FDC_ACCESS_WIDTH_SHIFT | a);
}

static void ledger(fdc_device *dev, uint8_t kind, uint32_t a, uint32_t b) {
    if (dev->log_n >= FDC_LOG_MAX) {
        dev->log_dropped++;          /* counted, never silent: a truncated ledger is a refused run */
        return;
    }
    dev->log_kind[dev->log_n] = kind;
    dev->log_a[dev->log_n] = a;
    dev->log_b[dev->log_n] = b;
    dev->log_n++;
}

/* A poll that answers what the one before it answered is the same entry, counted (R-D4-3): one timeout
 * is 262,143 identical polls, and listing them would overflow any ledger for nothing a reader can use. */
static void ledger_poll(fdc_device *dev, uint8_t served) {
    uint32_t last = dev->log_n - 1;
    if (dev->log_n && dev->log_kind[last] == FDC_EV_POLL && dev->log_a[last] == served) {
        dev->log_b[last]++;
        return;
    }
    ledger(dev, FDC_EV_POLL, served, 1);
}

/* ---- the chip's two small decodes ------------------------------------------------------------ */
static unsigned register_of(const fdc_chip *chip) {
    return chip->mode >> FDC_MODE_REG_SHIFT & FDC_MODE_REG_MASK;
}

/* The byte an FDC register access leaves on the data bus, which the DMA status reads back above bit 2.
 * Hatari keeps the low byte of the last FDC access (verified on an STF for bits 3-7); whether bits 8-15
 * hold anything is UNCONFIRMED and they are kept 0. No driver modelled reads more than bit 0. */
static void note_residue(fdc_chip *chip, uint8_t byte) {
    chip->residue = (uint16_t)((chip->residue & ~FDC_BYTE_MASK) | byte);
}

/* ---- the device's life ------------------------------------------------------------------------- */
/* MR (power-on): the command and status registers clear, a 1 in the sector register (datasheet, "MR");
 * the DMA's error flag clear and its count zero (Hatari's FDC_Reset, STF). The heads' power-on position is
 * the model's DECLARATION, 0 — Hatari's too; every driver restores before it relies on it. */
void fdc_power_on(fdc_chip *chip) {
    memset(chip, 0, sizeof *chip);
    chip->sector = 1;
    chip->type1 = 1;
    chip->dma_ok = 1;
}

void fdc_enter_run(fdc_device *dev, const fdc_chip *declared) {
    dev->chip = *declared;
    dev->refused = FDC_REFUSE_NONE;
    dev->refused_at = 0;
    dev->log_n = 0;
    dev->log_dropped = 0;
}

uint32_t fdc_insert(fdc_device *dev, uint32_t drive, uint8_t *image, uint32_t bytes, uint32_t present,
                    uint32_t inserted, uint32_t write_protected, uint32_t read_only) {
    if (drive >= FDC_DRIVES || (inserted && (!image || bytes != FDC_IMAGE_BYTES)))
        return FDC_REFUSE_GEOMETRY;
    fdc_drive *bay = &dev->drive[drive];
    bay->image = inserted ? image : 0;
    bay->present = present != 0;
    bay->inserted = present && inserted;
    bay->write_protected = write_protected != 0;
    bay->read_only = read_only != 0;
    return FDC_REFUSE_NONE;
}

int fdc_owns(uint32_t a, unsigned width) {
    return a < FDC_BLOCK_HI && a + width > FDC_BLOCK_LO;
}

int fdc_covers_gpip(uint32_t a, unsigned width) {
    return width > 1 && a <= FDC_MFP_GPIP && FDC_MFP_GPIP < a + width;
}

/* ---- the drive and side the pins select --------------------------------------------------------- */
typedef struct {
    int drive;                    /* FDC_NO_DRIVE, or 0 / 1 */
    unsigned side;
} selection;

/* Port A's pins, or 0 (refused) when the run never knew port A. Both select lines low is drive A —
 * the lower line wins, as the ST's own decode does nothing to prevent; TOS never drives both. */
static int selected(fdc_device *dev, const fdc_bus *bus, selection *sel) {
    uint8_t pins;
    if (!bus->port_a(&pins)) {
        refuse(dev, FDC_REFUSE_PORT_A_UNKNOWN, FDC_PSG_PORT_A);
        return 0;
    }
    sel->side = (pins & FDC_PORT_A_SIDE_0) ? 0u : 1u;
    sel->drive = !(pins & FDC_PORT_A_DRIVE_A) ? 0 : !(pins & FDC_PORT_A_DRIVE_B) ? 1 : FDC_NO_DRIVE;
    return 1;
}

static const fdc_drive *bay_of(const fdc_device *dev, int drive) {
    return drive == FDC_NO_DRIVE ? 0 : &dev->drive[drive];
}

/* A drive that sends index pulses: present, with a disk turning in it. Spin-up and every ID search
 * count those pulses, so without one they never end. */
static int turning(const fdc_drive *bay) {
    return bay && bay->present && bay->inserted;
}

/* The type I status as a read sees it: TR00 and WPRT are the SELECTED drive's lines at the moment of
 * the read (datasheet; Hatari updates WPRT after a type I too). No drive: both lines off. An empty bay
 * reads write-protected — the drive cannot tell no disk from a protected one (Hatari, STF). INDEX
 * (bit 1) is always 0: no time, no pulse (unpinned). */
static uint8_t type1_status(fdc_device *dev, const fdc_bus *bus) {
    selection sel;
    uint8_t status = dev->chip.status & (FDC_ST_MOTOR | FDC_ST_SPUN_UP | FDC_ST_RNF | FDC_ST_BUSY);
    if (!selected(dev, bus, &sel) || sel.drive == FDC_NO_DRIVE || !dev->drive[sel.drive].present)
        return status;
    const fdc_drive *bay = &dev->drive[sel.drive];
    if (dev->chip.head[sel.drive] == 0)
        status |= FDC_ST_TR00;
    if (!bay->inserted || bay->write_protected)
        status |= FDC_ST_WPRT;
    return status;
}

/* ---- completing, or never completing --------------------------------------------------------- */
static void complete(fdc_device *dev, uint8_t status) {
    dev->chip.status = status;
    dev->chip.intrq = 1;
    ledger(dev, FDC_EV_DONE, status, 0);
}

/* The command waits for index pulses that never come: busy, the motor line on, no INTRQ — until a
 * force-interrupt, which is what a driver's own timeout sends. */
static void hang(fdc_device *dev) {
    dev->chip.status = FDC_ST_MOTOR | FDC_ST_BUSY;
    dev->chip.busy_forever = 1;
    ledger(dev, FDC_EV_HANG, dev->chip.command, 0);
}

/* ---- type I: restore and seek, with or without verify ------------------------------------------ */
/* Restore: a drive steps out until TR00, and TR := 0. With NO drive the chip gives up after 255 step
 * pulses with TR00 never seen — a SEEK ERROR, TR 0 (datasheet; Hatari, R-D4-1). Seek: the head moves by
 * DR - TR (clamped to the mechanical stops), and TR := DR; with no drive TR still becomes DR. */
static void type1(fdc_device *dev, int drive) {
    fdc_chip *chip = &dev->chip;
    const fdc_drive *bay = bay_of(dev, drive);
    int present = bay && bay->present;
    uint8_t error = 0;
    switch (chip->command & CMD_KIND_MASK) {
    case CMD_RESTORE:
        if (present) chip->head[drive] = 0;
        else         error = FDC_ST_RNF;
        chip->track = 0;
        break;
    case CMD_SEEK:
        if (present) {
            int to = (int)chip->head[drive] + (int)chip->data - (int)chip->track;
            chip->head[drive] = (uint8_t)(to < 0 ? 0 : to > (int)FDC_LAST_HEAD_STOP ? (int)FDC_LAST_HEAD_STOP : to);
        }
        chip->track = chip->data;
        break;
    default:                      /* step / step-in / step-out: never issued by the drivers modelled */
        refuse(dev, FDC_REFUSE_COMMAND, chip->command);
        return;
    }
    if (chip->command & CMD_VERIFY) {
        if (!turning(bay)) {      /* the ID search counts revolutions */
            hang(dev);
            return;
        }
        if (chip->head[drive] >= FDC_TRACKS || chip->track != chip->head[drive])
            error = FDC_ST_RNF;   /* a .ST's ID fields carry the physical track */
    }
    complete(dev, (uint8_t)(FDC_ST_MOTOR | FDC_ST_SPUN_UP | error));
}

/* ---- type II / III: sector and track transfers, through the DMA ------------------------------- */
static long sector_offset(unsigned head, unsigned side, unsigned sector) {
    return (long)(((head * FDC_SIDES + side) * FDC_SECTORS + sector - 1) * FDC_SECTOR_BYTES);
}

/* Where (TR, SR) lies under the selected head, or -1: record not found. The ID field the chip matches
 * holds the PHYSICAL track, so a track register that disagrees with the head finds nothing. */
static long sector_found(const fdc_chip *chip, int drive, unsigned side) {
    unsigned head = chip->head[drive];
    if (head >= FDC_TRACKS || chip->track != head || chip->sector < 1 || chip->sector > FDC_SECTORS)
        return -1;
    return sector_offset(head, side, chip->sector);
}

/* The DMA's two refusals any transfer may meet. 1 when `n` bytes may move in the asked direction. */
static int dma_may_move(fdc_device *dev, const fdc_bus *bus, int to_disk, uint32_t n) {
    fdc_chip *chip = &dev->chip;
    if (!(chip->mode & FDC_MODE_WRITE) != !to_disk) {
        refuse(dev, FDC_REFUSE_DIRECTION, chip->command);
        return 0;
    }
    if (chip->addr + n > bus->ram_end) {
        refuse(dev, FDC_REFUSE_DMA_OFF_RAM, chip->addr);
        return 0;
    }
    return 1;
}

/* Each transferred byte is the DMA's STORE: it lands in RAM and joins the run's write-set, so a diff of
 * what the run stored sees it as it sees the CPU's. 0 on a refusal (the command then never completes:
 * a refused run has no next state to describe). */
static int dma_in(fdc_device *dev, const fdc_bus *bus, const uint8_t *from) {
    fdc_chip *chip = &dev->chip;
    if ((chip->mode & FDC_MODE_WRITE) == 0 && !chip->count) {
        chip->dma_ok = 0;         /* a DRQ the DMA may not serve: its error bit (Hatari, STF) */
        return 1;
    }
    if (!dma_may_move(dev, bus, 0, FDC_SECTOR_BYTES))
        return 0;
    for (uint32_t i = 0; i < FDC_SECTOR_BYTES; i++) {
        bus->ram[chip->addr + i] = from[i];
        bus->stored(chip->addr + i);
    }
    ledger(dev, FDC_EV_DMA_IN, chip->addr, FDC_SECTOR_BYTES);
    chip->addr += FDC_SECTOR_BYTES;
    chip->count--;
    return 1;
}

/* One sector from RAM onto the disk. 0 on a refusal, as dma_in. */
static int dma_out(fdc_device *dev, const fdc_bus *bus, uint8_t *to) {
    fdc_chip *chip = &dev->chip;
    if (!dma_may_move(dev, bus, 1, FDC_SECTOR_BYTES))
        return 0;
    if (!chip->count) {
        refuse(dev, FDC_REFUSE_WRITE_NO_COUNT, chip->command);
        return 0;
    }
    memcpy(to, bus->ram + chip->addr, FDC_SECTOR_BYTES);
    ledger(dev, FDC_EV_DMA_OUT, chip->addr, FDC_SECTOR_BYTES);
    chip->addr += FDC_SECTOR_BYTES;
    chip->count--;
    return 1;
}

static int is_special(uint8_t byte) {
    return byte >= WT_SPECIAL_FIRST && byte <= WT_SPECIAL_LAST;
}

static int mark_at(const uint8_t *stream, uint32_t at, uint8_t mark) {
    return stream[at] == WT_SYNC && stream[at + 1] == mark;
}

/* The ID field at `id` is one an 80x2x9 .ST holds at (head, side) and has not been seen on this track. */
static int id_holds(const uint8_t *id, unsigned head, unsigned side, uint32_t found) {
    return id[0] == head && id[1] == side && id[3] == SIZE_CODE_512 && id[2] >= 1 && id[2] <= FDC_SECTORS
        && !(found & 1u << id[2]);
}

static uint32_t id_detail(const uint8_t *id) {
    return (uint32_t)id[0] << REFUSAL_TRACK_SHIFT | (uint32_t)id[1] << REFUSAL_SIDE_SHIFT | id[2];
}

/* Decode one revolution of a Write Track stream (`stream`, FDC_TRACK_BYTES) into where each sector's data
 * lies (`data_at[n]`), or refuse: an 80x2x9 .ST holds a track of EXACTLY sectors 1..9, each ID followed by
 * its own data field before the next ID, the data holding no byte the chip writes as a mark. 1 = decoded. */
static int decode_track(fdc_device *dev, const uint8_t *stream, unsigned head, unsigned side,
                        uint32_t data_at[FDC_SECTORS + 1]) {
    uint32_t found = 0, n = FDC_TRACK_BYTES;
    for (uint32_t i = 0; i + 1 < n; i++) {
        if (!mark_at(stream, i, MARK_ID))
            continue;
        if (i + MARK_BYTES + ID_FIELD_BYTES > n) {
            refuse(dev, FDC_REFUSE_UNREPRESENTABLE, NO_ID);       /* an ID the revolution cuts off */
            return 0;
        }
        const uint8_t *id = stream + i + MARK_BYTES;
        if (!id_holds(id, head, side, found)) {
            refuse(dev, FDC_REFUSE_UNREPRESENTABLE, id_detail(id));
            return 0;
        }
        uint32_t data = i + MARK_BYTES + ID_FIELD_BYTES;
        while (data + 1 < n && !mark_at(stream, data, MARK_DATA) && !mark_at(stream, data, MARK_ID))
            data++;
        if (data + 1 >= n || !mark_at(stream, data, MARK_DATA) || data + MARK_BYTES + FDC_SECTOR_BYTES > n) {
            refuse(dev, FDC_REFUSE_UNREPRESENTABLE, id_detail(id));   /* an ID with no data field of its own */
            return 0;
        }
        data += MARK_BYTES;
        for (uint32_t k = 0; k < FDC_SECTOR_BYTES; k++)
            if (is_special(stream[data + k])) {
                refuse(dev, FDC_REFUSE_UNREPRESENTABLE, id_detail(id));
                return 0;
            }
        data_at[id[2]] = data;
        found |= 1u << id[2];
        i = data + FDC_SECTOR_BYTES - 1;
    }
    if (found != ALL_SECTORS) {
        refuse(dev, FDC_REFUSE_TRACK_SECTORS, found);
        return 0;
    }
    return 1;
}

/* Write Track: one whole revolution (6,250 bytes) out of RAM, decoded back into the nine sectors of the
 * track. Everything is checked BEFORE the DMA moves, so a refused track leaves the RAM, the image and the
 * DMA where they were: a count holding less than a revolution (the chip would write on with lost data,
 * which the model does not invent — R-D4-1), and any track the .ST layout cannot hold. The DMA's FIFO
 * prefetch is not modelled: the address advances by the revolution, the count by the sectors it started. */
static void write_track(fdc_device *dev, const fdc_bus *bus, int drive, unsigned side) {
    fdc_chip *chip = &dev->chip;
    uint32_t data_at[FDC_SECTORS + 1];
    unsigned head = chip->head[drive];
    if (!dma_may_move(dev, bus, 1, FDC_TRACK_BYTES))
        return;
    if ((uint32_t)chip->count * FDC_SECTOR_BYTES < FDC_TRACK_BYTES) {
        refuse(dev, FDC_REFUSE_TRACK_SHORT_COUNT, chip->count);
        return;
    }
    if (head >= FDC_TRACKS) {
        refuse(dev, FDC_REFUSE_UNREPRESENTABLE, NO_ID);
        return;
    }
    const uint8_t *stream = bus->ram + chip->addr;
    if (!decode_track(dev, stream, head, side, data_at))
        return;
    uint8_t *image = dev->drive[drive].image;
    for (unsigned sector = 1; sector <= FDC_SECTORS; sector++)
        memcpy(image + sector_offset(head, side, sector), stream + data_at[sector], FDC_SECTOR_BYTES);
    ledger(dev, FDC_EV_DMA_OUT, chip->addr, FDC_TRACK_BYTES);
    chip->addr += FDC_TRACK_BYTES;
    chip->count = (uint8_t)(chip->count - (FDC_TRACK_BYTES + FDC_SECTOR_BYTES - 1) / FDC_SECTOR_BYTES);
    complete(dev, FDC_ST_MOTOR);
}

static void type2_or_3(fdc_device *dev, const fdc_bus *bus, int drive, unsigned side) {
    fdc_chip *chip = &dev->chip;
    const fdc_drive *bay = &dev->drive[drive];
    uint8_t kind = chip->command & CMD_TYPE2_MASK;
    int writes = (chip->command & CMD_KIND_MASK) == CMD_WRITE_TRACK || kind == CMD_WRITE_SECTOR;
    if ((chip->command & CMD_KIND_MASK) != CMD_WRITE_TRACK
        && ((chip->command & CMD_MULTIPLE) || (kind != CMD_READ_SECTOR && kind != CMD_WRITE_SECTOR))) {
        refuse(dev, FDC_REFUSE_COMMAND, chip->command);   /* read address / read track / the m bit */
        return;
    }
    if (writes && bay->write_protected) {
        complete(dev, FDC_ST_MOTOR | FDC_ST_WPRT);        /* before any transfer (datasheet) */
        return;
    }
    if (writes && bay->read_only) {
        refuse(dev, FDC_REFUSE_READ_ONLY, chip->command); /* the case lent the image to be read */
        return;
    }
    if ((chip->command & CMD_KIND_MASK) == CMD_WRITE_TRACK) {
        write_track(dev, bus, drive, side);
        return;
    }
    long at = sector_found(chip, drive, side);
    if (at < 0) {
        complete(dev, FDC_ST_MOTOR | FDC_ST_RNF);         /* after five revolutions, in zero time */
        return;
    }
    int moved = kind == CMD_READ_SECTOR ? dma_in(dev, bus, bay->image + at) : dma_out(dev, bus, bay->image + at);
    if (moved)
        complete(dev, FDC_ST_MOTOR);
}

/* ---- a command byte written ------------------------------------------------------------------- */
static void force_interrupt(fdc_device *dev, uint8_t byte) {
    fdc_chip *chip = &dev->chip;
    chip->busy_forever = 0;
    chip->status &= (uint8_t)~FDC_ST_BUSY;
    chip->type1 = 1;              /* after a force the status register reports type I (datasheet) */
    /* $D0 terminates with no interrupt. Any condition bit is an INTRQ condition; the immediate one is
     * the only one with no index pulse in it, and the drivers modelled send none — it is asserted at
     * once for all of them rather than modelled per condition (unpinned). */
    chip->intrq = (byte & CMD_FORCE_COND) != 0;
    ledger(dev, FDC_EV_FORCED, byte, 0);
}

static void command(fdc_device *dev, const fdc_bus *bus, uint8_t byte) {
    fdc_chip *chip = &dev->chip;
    selection sel;
    chip->intrq = 0;              /* writing the command register clears INTRQ (datasheet) */
    if ((byte & CMD_KIND_MASK) == CMD_FORCE) {
        force_interrupt(dev, byte);
        return;
    }
    if (chip->busy_forever)
        return;                   /* while busy the chip takes no command but a force-interrupt */
    chip->command = byte;
    if (!selected(dev, bus, &sel))
        return;
    ledger(dev, FDC_EV_COMMAND, byte, ((uint32_t)sel.drive & FDC_EV_DRIVE_MASK) << FDC_EV_DRIVE_SHIFT | sel.side);
    const fdc_drive *bay = bay_of(dev, sel.drive);
    chip->type1 = !(byte & CMD_TYPE_2_OR_3);
    if (!(byte & CMD_NO_SPIN_UP) && !chip->motor && !turning(bay)) {
        chip->motor = 1;          /* the motor line goes on; the six index pulses never come */
        hang(dev);
        return;
    }
    chip->motor = 1;
    if (chip->type1) {
        type1(dev, sel.drive);
        return;
    }
    if (!turning(bay)) {          /* every type II / III command starts by counting index pulses */
        hang(dev);
        return;
    }
    type2_or_3(dev, bus, sel.drive, sel.side);
}

/* ---- the bus ------------------------------------------------------------------------------------ */
static uint32_t read_register(fdc_device *dev, const fdc_bus *bus, uint32_t a) {
    fdc_chip *chip = &dev->chip;
    if (a == FDC_DMA_MODE)
        return (uint32_t)(chip->residue & FDC_DMA_RESIDUE) | (chip->count ? FDC_DMA_COUNT_NZ : 0u)
             | (chip->dma_ok ? FDC_DMA_OK : 0u);
    if (chip->mode & FDC_MODE_COUNT) {
        refuse(dev, FDC_REFUSE_COUNT_READ, a);
        return 0;
    }
    if (chip->mode & FDC_MODE_HDC) {
        refuse(dev, FDC_REFUSE_HDC_READ, a);
        return 0;
    }
    uint8_t byte;
    switch (register_of(chip)) {
    case FDC_REG_COMMAND:
        byte = chip->type1 ? type1_status(dev, bus) : chip->status;
        chip->intrq = 0;          /* reading the status clears INTRQ (datasheet) */
        break;
    case FDC_REG_TRACK:  byte = chip->track; break;
    case FDC_REG_SECTOR: byte = chip->sector; break;
    default:             byte = chip->data; break;
    }
    note_residue(chip, byte);
    return byte;                  /* the upper byte of an FDC register read is 0 (Hatari) */
}

static int is_address_byte(uint32_t a) {
    return a == FDC_DMA_ADDR_HI || a == FDC_DMA_ADDR_MID || a == FDC_DMA_ADDR_LO;
}

static int is_word_register(uint32_t a) {
    return a == FDC_DMA_DATA || a == FDC_DMA_MODE;
}

/* Where an address byte register sits in the 24-bit DMA address. */
static unsigned address_shift(uint32_t a) {
    return a == FDC_DMA_ADDR_HI ? FDC_ADDR_HI_SHIFT : a == FDC_DMA_ADDR_MID ? FDC_ADDR_MID_SHIFT : 0;
}

static uint32_t address_byte(const fdc_chip *chip, uint32_t a) {
    return chip->addr >> address_shift(a) & FDC_ADDR_BYTE;
}

/* Every access to the block lands here while armed: the address bytes by byte, the two word registers by
 * word; anything else — another width, an even address byte, an offset that is no register — is refused,
 * not passed through. */
uint32_t fdc_read(fdc_device *dev, const fdc_bus *bus, uint32_t a, unsigned width) {
    uint32_t value, reg = a;
    if (width == 1 && is_address_byte(a)) {
        value = address_byte(&dev->chip, a);
    } else if (width == 2 && is_word_register(a)) {
        if (a == FDC_DMA_DATA)
            reg = a | (uint32_t)register_of(&dev->chip) << FDC_EV_READ_REG_SHIFT;
        value = read_register(dev, bus, a);
    } else {
        refuse_access(dev, a, width);
        return 0;
    }
    ledger(dev, FDC_EV_READ, reg, value);
    return value;
}

static void write_word(fdc_device *dev, const fdc_bus *bus, uint32_t a, uint16_t value) {
    fdc_chip *chip = &dev->chip;
    if (a == FDC_DMA_MODE) {
        if ((chip->mode ^ value) & FDC_MODE_WRITE) {     /* the toggle resets the DMA (Hatari, STF) */
            chip->count = 0;
            chip->dma_ok = 1;
        }
        chip->mode = value;
        return;
    }
    if (chip->mode & FDC_MODE_COUNT) {
        chip->count = (uint8_t)value;
        return;
    }
    uint8_t byte = (uint8_t)value;
    if (chip->mode & FDC_MODE_HDC) {
        ledger(dev, FDC_EV_HDC, byte, chip->mode);       /* no ACSI device answers (unpinned) */
        return;
    }
    note_residue(chip, byte);
    switch (register_of(chip)) {
    case FDC_REG_COMMAND: command(dev, bus, byte); break;
    case FDC_REG_TRACK:   if (!chip->busy_forever) chip->track = byte; break;    /* ignored while busy */
    case FDC_REG_SECTOR:  if (!chip->busy_forever) chip->sector = byte; break;
    default:              chip->data = byte; break;
    }
}

static void write_address_byte(fdc_chip *chip, uint32_t a, uint32_t value) {
    unsigned shift = address_shift(a);
    uint32_t byte = value & (a == FDC_DMA_ADDR_LO ? FDC_ADDR_LO_WIRED : FDC_ADDR_BYTE);
    chip->addr = (chip->addr & ~(FDC_ADDR_BYTE << shift) & FDC_ADDR_MASK) | byte << shift;
}

void fdc_write(fdc_device *dev, const fdc_bus *bus, uint32_t a, unsigned width, uint32_t value) {
    if (width == 1 && is_address_byte(a)) {
        write_address_byte(&dev->chip, a, value);
    } else if (width == 4 && a == FDC_DMA_DATA) {        /* move.l to $ff8604: the data word, then the mode */
        write_word(dev, bus, FDC_DMA_DATA, (uint16_t)(value >> 16));
        write_word(dev, bus, FDC_DMA_MODE, (uint16_t)value);
    } else if (width == 2 && is_word_register(a)) {
        write_word(dev, bus, a, (uint16_t)value);
    } else {
        refuse_access(dev, a, width);
    }
}

uint8_t fdc_gpip(fdc_device *dev, uint8_t declared) {
    uint8_t served = (uint8_t)((declared & ~FDC_GPIP_INTRQ) | (dev->chip.intrq ? 0u : FDC_GPIP_INTRQ));
    ledger_poll(dev, served);
    return served;
}
