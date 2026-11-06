/* fdc.h — the FDC/DMA TRANSACTION MODEL (TRAP_MODEL.md, "Phase 17"): the ST's WD1772 floppy controller
 * and its DMA chip, as a ZERO-TIME device. Ruling D4 (2026-11-01): R-D4-1 "Instant 'done', shared kit C".
 *
 * WHAT IT IS. One device record (`fdc_device`), functions over it and nothing else (no static state), and
 * a BUS the caller hands in: the RAM the DMA reads and writes, a hook through which every byte the DMA
 * stores joins the run's write-set, and PSG port A as the chip's drive/side pins see it. It is a SHARED
 * SOURCE, compiled into the oracle (oracle/shim.c, where it is wired) and swept into every candidate by
 * kit.mk's SRC (where it is not wired yet: no reconstruction drives the floppy from host C, so the wiring
 * arrives with the first row that needs it — and until then harness.differential refuses an armed run).
 *
 * ARMED ONLY. shim.c routes the DMA block `$ff8600`..`$ff860f` and GPIP bit 5 here only while a case has
 * ARMED the model (`osh_fdc_arm`); unarmed, every access takes exactly the path it took before this file
 * existed. Armed, the model owns the WHOLE block: an access it does not model (another width, an offset
 * that is not a register) is refused by name rather than passed through.
 *
 * TIME: NONE PASSES. A command the chip can complete completes INSIDE the store that issues it, so the
 * first GPIP poll after it sees INTRQ. A command the chip can never complete without index pulses — a
 * spin-up, or an ID search, with no drive or no disk — HANGS (busy, no INTRQ) until a force-interrupt;
 * which is exactly how a driver's own count-down timeout reaches its timeout arm. Measured on TOS 1.02's
 * floppy driver: every wait it makes is an instruction-count loop on GPIP bit 5 (`move.l #$40000,d7`,
 * `#$60000` with the motor off, then `subq.l / beq / btst #5,$fffa01 / bne`), none an `_hz_200` one, so
 * this needs no time source; delaying INTRQ by N polls instead was measured to change only cycles and a
 * countdown residue in dead stack. What DOES need time is not modelled and is UNPINNED by name: the motor
 * turning off (9 index pulses), the INDEX status bit, a disk inserted or ejected mid-run (the WPRT
 * transitions), rotational latency, CRC errors and protection tracks, and any ACSI (HDC) device.
 *
 * THE MEDIUM. A `.ST` image of 80 tracks x 2 sides x 9 sectors of 512 bytes, ID fields carrying the
 * physical track — the only geometry ruled (R-D4-1); any other is refused by name at insertion. An image
 * may be lent READ-ONLY: then any command that would write it is refused by name.
 *
 * THE STATE IS SPLIT IN TWO, deliberately. `fdc_chip` is the chip's and the drives' MECHANICAL state
 * (registers, INTRQ, motor, the heads' positions): plain data, no pointers, no padding, saved and loaded
 * WHOLE — what a harness carries from one slice to the next (R-D4-2 "Carry both, from ROM runs"). After a
 * REFUSED run it describes nothing (a refusal may come after the DMA advanced): a refused run is not
 * carried. `fdc_drive` is the CASE's declaration of what is in each drive bay: never carried by the chip.
 */
#ifndef RECREATE_FDC_H
#define RECREATE_FDC_H

#include <stdint.h>

/* ---- the DMA block and its registers (24-bit bus form; shim.c folds an access first) ------------- */
#define FDC_BLOCK_LO       0xff8600u  /* the DMA chip's decode: the model owns [LO, HI) while armed */
#define FDC_BLOCK_HI       0xff8610u
#define FDC_DMA_DATA       0xff8604u  /* word: an FDC register, the sector count, or an HDC byte — by the mode */
#define FDC_DMA_MODE       0xff8606u  /* word: write = the mode; read = the DMA status */
#define FDC_DMA_ADDR_HI    0xff8609u  /* byte: the DMA address, bits 16-23 */
#define FDC_DMA_ADDR_MID   0xff860bu  /* byte: bits 8-15 */
#define FDC_DMA_ADDR_LO    0xff860du  /* byte: bits 0-7 (bit 0 not wired: the DMA moves words) */
#define FDC_ADDR_HI_SHIFT  16
#define FDC_ADDR_MID_SHIFT 8
#define FDC_ADDR_BYTE      0xffu
#define FDC_ADDR_LO_WIRED  0xfeu
#define FDC_ADDR_MASK      0xffffffu  /* 24 bits */
#define FDC_MFP_GPIP       0xfffa01u  /* MFP GPIP: bit 5 is the FDC/HDC interrupt line, ACTIVE LOW */
#define FDC_GPIP_INTRQ     0x20u
#define FDC_ACCESS_WIDTH_SHIFT 24     /* an access refusal's detail: width << 24 | address */

/* ---- the mode word ---------------------------------------------------------------------------- */
#define FDC_MODE_REG_SHIFT 1
#define FDC_MODE_REG_MASK  0x3u       /* A1 A0: which FDC register $ff8604 reaches */
#define FDC_REG_COMMAND    0u         /* write: the command; read: the status */
#define FDC_REG_TRACK      1u
#define FDC_REG_SECTOR     2u
#define FDC_REG_DATA       3u
#define FDC_MODE_HDC       0x08u      /* $ff8604 reaches the ACSI bus instead of the FDC */
#define FDC_MODE_COUNT     0x10u      /* $ff8604 reaches the DMA sector count (write-only) */
#define FDC_MODE_WRITE     0x100u     /* direction RAM -> disk; TOGGLING it resets the DMA */

/* ---- the DMA status word ($ff8606 read) --------------------------------------------------------- */
#define FDC_DMA_OK         0x01u      /* bit 0: 1 = no DMA error */
#define FDC_DMA_COUNT_NZ   0x02u      /* bit 1: the sector count is not zero */
#define FDC_DMA_RESIDUE    0xfff8u    /* bits 3-15: the bus residue of the last FDC byte (see `residue`) */
#define FDC_BYTE_MASK      0xffu

/* ---- the WD1772's status bits ------------------------------------------------------------------- */
#define FDC_ST_BUSY        0x01u
#define FDC_ST_TR00        0x04u      /* type I: the head is on track 0 */
#define FDC_ST_LOST_DATA   0x04u      /* type II/III (never produced: see the refusals) */
#define FDC_ST_RNF         0x10u      /* type II/III: record not found; type I: seek error */
#define FDC_ST_SPUN_UP     0x20u      /* type I: the spin-up sequence completed */
#define FDC_ST_WPRT        0x40u      /* write protect (type I: live from the selected drive) */
#define FDC_ST_MOTOR       0x80u

/* ---- PSG port A, the chip's drive and side pins (YM2149 register 14) ---------------------------- */
#define FDC_PSG_PORT_A     14u
#define FDC_PORT_A_SIDE_0  0x01u      /* active low: CLEAR selects side 1 */
#define FDC_PORT_A_DRIVE_A 0x02u      /* active low */
#define FDC_PORT_A_DRIVE_B 0x04u      /* active low */

/* ---- the medium (R-D4-1: 80 x 2 x 9 only) -------------------------------------------------------- */
#define FDC_DRIVES         2
#define FDC_TRACKS         80u
#define FDC_SIDES          2u
#define FDC_SECTORS        9u         /* per track */
#define FDC_SECTOR_BYTES   512u
#define FDC_IMAGE_BYTES    (FDC_TRACKS * FDC_SIDES * FDC_SECTORS * FDC_SECTOR_BYTES)   /* 737,280 */
#define FDC_TRACK_BYTES    6250u      /* one DD revolution at 300 rpm: what one Write Track writes */
#define FDC_LAST_HEAD_STOP 85u        /* the head's mechanical stop, a seek's upper clamp */
#define FDC_NO_DRIVE       (-1)

/* ---- why a run could not be described (the FIRST one is kept, with the detail it names) --------- */
enum {
    FDC_REFUSE_NONE = 0,
    FDC_REFUSE_ACCESS,            /* an access to the DMA block the model does not serve (detail: width << 24 | addr) —
                                     a byte access to a word register is a bus error on the ST; a long, an odd offset,
                                     a word to an address byte, are decodes the model does not claim */
    FDC_REFUSE_COMMAND,           /* a command outside the seven modelled: step, read address/track, the m bit */
    FDC_REFUSE_PORT_A_UNKNOWN,    /* PSG port A was never known to the run, so no drive/side is selected */
    FDC_REFUSE_DMA_OFF_RAM,       /* a transfer that leaves the RAM */
    FDC_REFUSE_DIRECTION,         /* a transfer against the DMA's direction bit */
    FDC_REFUSE_UNREPRESENTABLE,   /* a written track's ID or data field an 80x2x9 .ST cannot hold (detail t<<16|s<<8|n) */
    FDC_REFUSE_HDC_READ,          /* an HDC (ACSI) register read: no device is modelled */
    FDC_REFUSE_COUNT_READ,        /* a read of the sector count, which is write-only */
    FDC_REFUSE_WRITE_NO_COUNT,    /* a sector WRITTEN with a zero sector count: no data to send */
    FDC_REFUSE_GEOMETRY,          /* an image that is not 80x2x9 (osh_fdc_drive's answer) */
    FDC_REFUSE_TRACK_SHORT_COUNT, /* a Write Track whose DMA count holds less than one revolution (detail: the count) —
                                     the chip writes on, lost data, which the model does not invent */
    FDC_REFUSE_TRACK_SECTORS,     /* a written track that is not sectors 1..9 exactly once (detail: the found mask) */
    FDC_REFUSE_READ_ONLY,         /* a write to an image the case lent read-only */
    FDC_REFUSE_GPIP_WIDE,         /* a word or long read covering GPIP while armed: the model owns bit 5 of a byte */
};

/* ---- the ORDERED TRANSACTION LEDGER (R-D4-3), compared exactly ---------------------------------- */
enum {
    FDC_EV_COMMAND = 1,           /* a: the command byte; b: (drive & 0xff) << 8 | side, drive 0xff = none */
    FDC_EV_DONE,                  /* a: the status the command completed with */
    FDC_EV_HANG,                  /* a: the command that can never complete without index pulses */
    FDC_EV_FORCED,                /* a: the force-interrupt byte */
    FDC_EV_DMA_IN,                /* a: the RAM address; b: the bytes stored there from the disk */
    FDC_EV_DMA_OUT,               /* a: the RAM address; b: the bytes sent to the disk */
    FDC_EV_READ,                  /* a: the register (its bus address, or FDC_DMA_DATA | A1A0 << 24); b: the value */
    FDC_EV_POLL,                  /* a: the GPIP byte served; b: how many CONSECUTIVE polls were served it */
    FDC_EV_HDC,                   /* a: the byte written to the ACSI bus (no device answers); b: the mode */
};
#define FDC_EV_READ_REG_SHIFT 24
#define FDC_EV_DRIVE_SHIFT    8
#define FDC_EV_DRIVE_MASK     0xffu
/* THE LEDGER'S CAP (ruling R-KIT-1, 2026-11-05). Sized from the largest single run measured: the tos102us desk's disk
 * Copy, whose last step makes 29,374 entries in one run (its Format makes 5,977), through the model unanswered. 65,536 is
 * x2.23 that. The cost is static and paid only by the oracle, whose g_fdc (shim.c) is the one fdc_device at run time (the
 * C probe has its own): 9 bytes an entry, 576 KiB. Nothing clears or copies the arrays per run: entering a run zeroes log_n and log_dropped. Past the cap
 * an entry is DROPPED and counted, and the run is refused as truncated (emu.fdc_causes). */
#define FDC_LOG_MAX 65536

/* The chip's and the drives' MECHANICAL state: plain data, saved and loaded whole. Laid out widest first
 * with the tail spelled out, so the saved bytes are all fields: no compiler padding (asserted below). */
typedef struct {
    uint32_t addr;                /* the DMA address, 24 bits */
    uint16_t mode;
    uint16_t residue;             /* the last FDC byte on $ff8604; bits 8-15 stay 0 (see FDC_DMA_RESIDUE) */
    uint8_t  command, track, sector, data, status;
    uint8_t  intrq;               /* the interrupt line, before GPIP's inversion */
    uint8_t  busy_forever;        /* a command waiting for index pulses that never come */
    uint8_t  motor;               /* the motor line, once a command turned it on (no time turns it off) */
    uint8_t  type1;               /* the status register reports type I (live TR00/WPRT) */
    uint8_t  count;               /* the DMA sector count */
    uint8_t  dma_ok;
    uint8_t  head[FDC_DRIVES];    /* each drive's physical head */
    uint8_t  reserved[3];         /* always 0: the struct's tail, named so no padding byte is saved */
} fdc_chip;
_Static_assert(sizeof(fdc_chip) == 24, "fdc_chip must hold no compiler padding: its bytes are the saved state");

/* What is in a drive bay: the CASE's declaration, never the chip's state. */
typedef struct {
    uint8_t *image;               /* FDC_IMAGE_BYTES, written in place by a write / write track */
    uint8_t  present, inserted, write_protected;
    uint8_t  read_only;           /* the case lent the image read-only: a write is refused, not made */
} fdc_drive;

typedef struct {
    fdc_chip  chip;
    fdc_drive drive[FDC_DRIVES];
    uint32_t  refused, refused_at;    /* the run's first refusal and its detail */
    uint32_t  log_n, log_dropped;
    uint8_t   log_kind[FDC_LOG_MAX];
    uint32_t  log_a[FDC_LOG_MAX], log_b[FDC_LOG_MAX];
} fdc_device;

typedef struct {
    uint8_t *ram;
    uint32_t ram_end;
    void (*stored)(uint32_t addr);         /* a byte the DMA stored: the run's write-set */
    int (*port_a)(uint8_t *value);         /* PSG port A: 1 and the byte when known, 0 when not */
} fdc_bus;

int      fdc_owns(uint32_t bus_addr, unsigned width);   /* does [addr, addr + width) touch the DMA block? */
int      fdc_covers_gpip(uint32_t bus_addr, unsigned width);   /* a WIDE access over GPIP (refused while armed) */
uint32_t fdc_read(fdc_device *dev, const fdc_bus *bus, uint32_t bus_addr, unsigned width);
void     fdc_write(fdc_device *dev, const fdc_bus *bus, uint32_t bus_addr, unsigned width, uint32_t value);
uint8_t  fdc_gpip(fdc_device *dev, uint8_t declared);   /* the GPIP byte: `declared`'s bits, bit 5 the chip's */
void     fdc_refuse_gpip_wide(fdc_device *dev, uint32_t bus_addr, unsigned width);
void     fdc_power_on(fdc_chip *chip);                   /* the chip after MR: the boot's starting state */
void     fdc_enter_run(fdc_device *dev, const fdc_chip *declared);   /* the chip a run starts from; ledger cleared */
uint32_t fdc_insert(fdc_device *dev, uint32_t drive, uint8_t *image, uint32_t bytes, uint32_t present,
                    uint32_t inserted, uint32_t write_protected, uint32_t read_only);   /* FDC_REFUSE_* or 0 */
#endif
