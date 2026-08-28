/* dma_sfx.c — the STE DMA sample voice. See dma_sfx.h for the contract, mk_samples.py for the blob.
 */
#include "dma_sfx.h"

/* ------------------------------------------------------- STE DMA sound registers ($ffff89xx) --- */

/* Every address register is a BYTE at an ODD address: the chip presents its 24-bit pointers as
 * three bytes with a gap, so a `move.l` would write the wrong three. */
#define DMA_CONTROL_REG     ((volatile uint8_t *)0xFFFF8901UL)
#define DMA_START_HIGH_REG  ((volatile uint8_t *)0xFFFF8903UL)
#define DMA_START_MID_REG   ((volatile uint8_t *)0xFFFF8905UL)
#define DMA_START_LOW_REG   ((volatile uint8_t *)0xFFFF8907UL)
#define DMA_END_HIGH_REG    ((volatile uint8_t *)0xFFFF890FUL)
#define DMA_END_MID_REG     ((volatile uint8_t *)0xFFFF8911UL)
#define DMA_END_LOW_REG     ((volatile uint8_t *)0xFFFF8913UL)
#define DMA_MODE_REG        ((volatile uint8_t *)0xFFFF8921UL)

#define DMA_CONTROL_PLAY    0x01   /* set to start; the chip clears it at the end of a one-shot */
#define DMA_CONTROL_STOP    0x00

#define DMA_MODE_RATE_12KHZ 0x01   /* 00 = 6258 Hz, 01 = 12517, 10 = 25033, 11 = 50066 */
#define DMA_MODE_MONO       0x80   /* clear = stereo, which would eat two bytes per output sample */

#define DMA_ADDRESS_HIGH_SHIFT 16
#define DMA_ADDRESS_MID_SHIFT   8
#define DMA_ADDRESS_BYTE_MASK  0xFF

/* -------------------------------------------- the LMC1992 volume/tone/mixer chip (MicroWire) --- */

#define MICROWIRE_DATA_REG  ((volatile uint16_t *)0xFFFF8922UL)
#define MICROWIRE_MASK_REG  ((volatile uint16_t *)0xFFFF8924UL)

/* The mask says which of the 16 shifted bits the LMC1992 is to latch. The bottom 11 are the word:
 * two device-address bits, three command bits, six data bits. */
#define MICROWIRE_MASK      0x07FF
#define LMC_DEVICE_ADDRESS  (0x2 << 9)   /* %10 — the LMC1992's address on the STE's MicroWire bus */
#define LMC_COMMAND_SHIFT   6

#define LMC_CMD_MIXER       0
#define LMC_CMD_BASS        1
#define LMC_CMD_TREBLE      2
#define LMC_CMD_MASTER      3
#define LMC_CMD_RIGHT       4
#define LMC_CMD_LEFT        5

/* THE MIXER FIELD, AND THE ONE VALUE THAT LETS THE YM THROUGH. It is two bits, and the value that
 * routes BOTH the DMA voice and the YM2149 to the output is 1 — measured, by building this file
 * four times and recording each in Hatari (REPORT.md has the table): at 0, 2 and 3 the music
 * vanishes from the recording and only the samples are left. EmuTOS's own boot writes 1 here for
 * the same reason, which is the corroboration that this is the chip and not the emulator. Getting
 * it wrong is silent in every other way: the register writes all look right, the samples still
 * play, and the game simply ships with no music. */
#define LMC_MIXER_DMA_AND_YM  1
#define LMC_TONE_FLAT         6    /* bass and treble are 0..12 with 6 as the flat setting */
#define LMC_MASTER_0DB       40    /* master is 0..40 */
#define LMC_CHANNEL_0DB      20    /* per-side is 0..20 */

/* The MicroWire shifts one bit per bus cycle and rotates the mask as it goes, so the mask reads
 * back as itself only when the 16-bit frame has gone out. Bounded, because a machine whose
 * MicroWire never completes must not hang the boot — a stuck one just gets its writes ignored. */
#define MICROWIRE_SPIN_LIMIT 1000

/* --------------------------------------------------------------------------- the cookie jar --- */

#define COOKIE_JAR_POINTER  ((const uint32_t *const *)0x000005A0UL)  /* _p_cookies */
#define PHYSTOP_POINTER     ((const uint8_t *const *)0x0000042EUL)   /* _phystop: past the last
                                                                      * byte of ST RAM */
#define COOKIE_ID_MACHINE   0x5F4D4348UL   /* '_MCH' */
#define COOKIE_END          0UL
#define COOKIE_FIELDS       2              /* each entry is (id, value) */
#define COOKIE_ENTRY_BYTES  (COOKIE_FIELDS * (uint32_t)sizeof(uint32_t))
#define MACHINE_TYPE_SHIFT  16             /* the machine is the cookie value's HIGH word */

/* The system variables end here; a jar pointer below this is not a jar. */
#define OS_VARIABLE_END     0x00000600UL
/* And a jar longer than this is not one either. TOS's own is a handful of entries and the longest
 * anyone stacks up is a few dozen; the cap is what stops an unterminated or circular list — which
 * is what junk at $5a0 usually decodes to — spinning the boot for ever. */
#define COOKIE_SCAN_LIMIT   64

/* The _MCH high word. 0 is a plain ST, 3 a TT and 4 a Falcon: none of those has this chip at these
 * addresses, so only the two below answer yes. */
#define MACHINE_STE         1
#define MACHINE_MEGA_STE    2

/* ------------------------------------------------------------------------ the sample bank ----- */

#define BANK_MAGIC          0x53465831UL   /* 'SFX1' */
#define BANK_OFF_MAGIC      0
#define BANK_OFF_COUNT      4              /* u16 */
#define BANK_HEADER_BYTES   8              /* magic, count, and two reserved bytes */
#define BANK_ENTRY_BYTES    8              /* u32 offset, u32 length — both from the blob's start */
#define BANK_ENTRY_OFF_DATA 0
#define BANK_ENTRY_OFF_LEN  4

/* ---------------------------------------------------------------------------- driver state ---- */

static const uint8_t *bank;
static uint16_t bank_count;
static uint8_t  voice_priority;
static uint8_t  machine_has_dma;
static uint8_t  machine_probed;

static uint32_t blob_long(const uint8_t *at)
{
    return ((uint32_t)at[0] << 24) | ((uint32_t)at[1] << 16) | ((uint32_t)at[2] << 8) | at[3];
}

static uint16_t blob_word(const uint8_t *at)
{
    return (uint16_t)(((uint16_t)at[0] << 8) | at[1]);
}

/* ------------------------------------------------------------------------ machine detection --- */

/* THE COOKIE JAR IS THE WHOLE TEST, and a machine without one is an ST. The jar arrived with TOS
 * 1.06, which is the oldest ROM any STE shipped with (and EmuTOS always builds one), so "no jar"
 * cannot be an STE — which is why this needs no bus-error probe of $ffff8901 and installs no
 * exception vector of its own. The read of $5a0 is supervisor-only, hence the contract in the
 * header.
 *
 * ...AND THE POINTER IT FINDS IS NOT TRUSTED. TOS 1.00-1.04 never defined $5a0, so on exactly the
 * machines this test is FOR it holds whatever the last program left there. Following an odd or wild
 * value is a bus error during boot on a plain ST — a crash caused by the code whose job was to
 * notice the machine has no DMA sound. So the pointer has to be even (a longword read from an odd
 * address is an address error on a 68000), above the system variables, and inside RAM for the whole
 * of the walk; and the walk itself is capped, because junk usually decodes to a list with no end.
 *
 * The suppression below is deliberate and is scoped to these two reads: to GCC, dereferencing $5a0
 * or $42e is an array subscript far outside any object it knows about, which is exactly right on a
 * host and exactly wrong on a machine whose OS publishes its state in page zero. Everywhere else in
 * this file -Warray-bounds stays an error. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"

static const uint32_t *cookie_jar(void)
{
    return *COOKIE_JAR_POINTER;
}

static const uint8_t *ram_top(void)
{
    return *PHYSTOP_POINTER;
}

#pragma GCC diagnostic pop

/* Is the whole of one (id, value) entry at `cookie` inside RAM and above the system variables? */
static int cookie_entry_is_readable(const uint32_t *cookie, const uint8_t *top)
{
    const uint8_t *entry = (const uint8_t *)cookie;

    return ((uint32_t)entry & 1) == 0
        && (uint32_t)entry >= OS_VARIABLE_END
        && entry <= top
        && (uint32_t)(top - entry) >= COOKIE_ENTRY_BYTES;
}

static int machine_dma_sound_present(void)
{
    const uint32_t *cookie = cookie_jar();
    const uint8_t *top = ram_top();
    uint16_t scanned;

    for (scanned = 0; scanned < COOKIE_SCAN_LIMIT; scanned++) {
        if (!cookie_entry_is_readable(cookie, top) || cookie[0] == COOKIE_END) {
            return 0;
        }
        if (cookie[0] == COOKIE_ID_MACHINE) {
            uint32_t machine = cookie[1] >> MACHINE_TYPE_SHIFT;

            return machine == MACHINE_STE || machine == MACHINE_MEGA_STE;
        }
        cookie += COOKIE_FIELDS;
    }
    /* Ran off the cap: whatever that list is, it is not a jar this driver will believe. */
    return 0;
}

int dma_sfx_available(void)
{
    if (!machine_probed) {
        machine_has_dma = (uint8_t)machine_dma_sound_present();
        machine_probed = 1;
    }
    return machine_has_dma;
}

/* -------------------------------------------------------------------------------- MicroWire --- */

static void microwire_write(uint16_t word)
{
    uint16_t spin;

    *MICROWIRE_MASK_REG = MICROWIRE_MASK;
    *MICROWIRE_DATA_REG = word;
    for (spin = 0; spin < MICROWIRE_SPIN_LIMIT; spin++) {
        if (*MICROWIRE_MASK_REG == MICROWIRE_MASK) {
            break;
        }
    }
}

static void lmc1992_write(uint8_t command, uint8_t value)
{
    microwire_write((uint16_t)(LMC_DEVICE_ADDRESS | (command << LMC_COMMAND_SHIFT) | value));
}

/* Put the analogue side into a known state. It is not optional and it is not cosmetic: TOS leaves
 * the LMC1992 wherever the last program left it, so without this the DMA output can be routed away
 * or attenuated to nothing and the game would ship silent on a machine that works. */
static void lmc1992_route_dma_and_ym(void)
{
    lmc1992_write(LMC_CMD_MIXER, LMC_MIXER_DMA_AND_YM);
    lmc1992_write(LMC_CMD_BASS, LMC_TONE_FLAT);
    lmc1992_write(LMC_CMD_TREBLE, LMC_TONE_FLAT);
    lmc1992_write(LMC_CMD_MASTER, LMC_MASTER_0DB);
    lmc1992_write(LMC_CMD_LEFT, LMC_CHANNEL_0DB);
    lmc1992_write(LMC_CMD_RIGHT, LMC_CHANNEL_0DB);
}

/* ------------------------------------------------------------------------------- the voice ---- */

static void dma_set_frame(uint32_t start, uint32_t end)
{
    *DMA_START_HIGH_REG = (uint8_t)((start >> DMA_ADDRESS_HIGH_SHIFT) & DMA_ADDRESS_BYTE_MASK);
    *DMA_START_MID_REG  = (uint8_t)((start >> DMA_ADDRESS_MID_SHIFT) & DMA_ADDRESS_BYTE_MASK);
    *DMA_START_LOW_REG  = (uint8_t)(start & DMA_ADDRESS_BYTE_MASK);
    *DMA_END_HIGH_REG   = (uint8_t)((end >> DMA_ADDRESS_HIGH_SHIFT) & DMA_ADDRESS_BYTE_MASK);
    *DMA_END_MID_REG    = (uint8_t)((end >> DMA_ADDRESS_MID_SHIFT) & DMA_ADDRESS_BYTE_MASK);
    *DMA_END_LOW_REG    = (uint8_t)(end & DMA_ADDRESS_BYTE_MASK);
}

/* Is [offset, offset + length) inside a blob of `bytes`? A subtraction, so a large offset or length
 * cannot wrap the comparison into agreeing. */
static int span_is_inside_the_bank(uint32_t offset, uint32_t length, uint32_t bytes)
{
    return offset <= bytes && length <= bytes - offset;
}

/* Every entry in the table, checked once so that dma_sfx_play never has to.
 *
 * BOTH ENDS MUST BE EVEN. The chip is handed a start and an end address and walks WORDS between
 * them: an odd start makes it read one byte early and an odd length one byte late, and both come
 * out of the speaker as a click with nothing in any register to say why. mk_samples.py pads for
 * exactly this, which makes the check here a check on the pipeline rather than a guess. */
static int bank_entries_are_inside_the_blob(const uint8_t *blob, uint16_t count, uint32_t bytes)
{
    uint16_t index;

    if (!span_is_inside_the_bank(BANK_HEADER_BYTES,
                                 (uint32_t)count * BANK_ENTRY_BYTES, bytes)) {
        return 0;
    }
    for (index = 0; index < count; index++) {
        const uint8_t *entry = blob + BANK_HEADER_BYTES + (uint32_t)index * BANK_ENTRY_BYTES;
        uint32_t offset = blob_long(entry + BANK_ENTRY_OFF_DATA);
        uint32_t length = blob_long(entry + BANK_ENTRY_OFF_LEN);

        if (((offset | length) & 1) != 0 || !span_is_inside_the_bank(offset, length, bytes)) {
            return 0;
        }
    }
    return 1;
}

int dma_sfx_init(const void *bank_blob, uint32_t bytes)
{
    const uint8_t *blob = (const uint8_t *)bank_blob;
    uint16_t count;

    bank = 0;
    bank_count = 0;
    voice_priority = 0;
    /* The blob's own address has to be even too: an even offset inside an odd blob is still an odd
     * address for the chip to start at. */
    if (!dma_sfx_available() || blob == 0 || (((uint32_t)blob) & 1) != 0
        || bytes < BANK_HEADER_BYTES || blob_long(blob + BANK_OFF_MAGIC) != BANK_MAGIC) {
        return 0;
    }
    count = blob_word(blob + BANK_OFF_COUNT);
    if (!bank_entries_are_inside_the_blob(blob, count, bytes)) {
        return 0;
    }
    bank = blob;
    bank_count = count;

    *DMA_CONTROL_REG = DMA_CONTROL_STOP;
    *DMA_MODE_REG = DMA_MODE_MONO | DMA_MODE_RATE_12KHZ;
    lmc1992_route_dma_and_ym();
    return 1;
}

int dma_sfx_busy(void)
{
    if (bank == 0) {
        return 0;
    }
    return (*DMA_CONTROL_REG & DMA_CONTROL_PLAY) != 0;
}

int dma_sfx_play(uint8_t index, uint8_t priority)
{
    const uint8_t *entry;
    uint32_t start;
    uint32_t length;

    if (bank == 0 || index >= bank_count) {
        return 0;
    }
    if (dma_sfx_busy() && priority < voice_priority) {
        return 0;
    }
    entry = bank + BANK_HEADER_BYTES + (uint32_t)index * BANK_ENTRY_BYTES;
    start = (uint32_t)bank + blob_long(entry + BANK_ENTRY_OFF_DATA);
    length = blob_long(entry + BANK_ENTRY_OFF_LEN);
    if (length == 0) {
        return 0;
    }

    /* Stop before re-pointing the frame: the address registers are latched at the start of each
     * frame, and moving them under a running voice is what makes a sample play from halfway. */
    *DMA_CONTROL_REG = DMA_CONTROL_STOP;
    dma_set_frame(start, start + length);
    *DMA_CONTROL_REG = DMA_CONTROL_PLAY;
    voice_priority = priority;
    return 1;
}

void dma_sfx_stop(void)
{
    if (!dma_sfx_available()) {
        return;
    }
    *DMA_CONTROL_REG = DMA_CONTROL_STOP;
    voice_priority = 0;
}
