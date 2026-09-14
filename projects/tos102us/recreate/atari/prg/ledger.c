/* ledger.c — writing the ledger. See ledger.h for what it is and why the magic goes last. */
#include "ledger.h"

static Ledger *const LEDGER = (Ledger *)LEDGER_ADDR;

/* The host parsers read fixed offsets, so a padding byte the compiler inserts would silently
 * misalign every record. These fail the BUILD rather than the run. */
_Static_assert(sizeof(LedgerRecord) == LEDGER_RECORD_BYTES, "LedgerRecord is not 32 bytes");
_Static_assert(sizeof(Ledger) == LEDGER_HEADER_BYTES + LEDGER_MAX_RECORDS * LEDGER_RECORD_BYTES,
               "the Ledger header is not 32 bytes, or the record array is padded");

/* The standard reflected CRC32 (the one zlib and PKZIP use), bitwise rather than table-driven:
 * the largest thing either program checksums is 64 KB, which is a fraction of a second on an 8 MHz
 * 68000, and a 1 KB lookup table would be another 1 KB of .data in a .PRG and another thing to
 * keep identical between two builds. */
#define CRC32_POLYNOMIAL    0xEDB88320UL
#define CRC32_BITS_PER_BYTE 8

uint32_t ledger_crc32_update(uint32_t crc, const void *data, uint32_t length)
{
    const uint8_t *bytes = (const uint8_t *)data;
    uint32_t index;
    int bit;

    for (index = 0; index < length; index++) {
        crc ^= bytes[index];
        for (bit = 0; bit < CRC32_BITS_PER_BYTE; bit++)
            crc = (crc >> 1) ^ (crc & 1 ? CRC32_POLYNOMIAL : 0);
    }
    return crc;
}

void ledger_begin(uint32_t kind)
{
    uint32_t index;

    LEDGER->magic = 0;                      /* nothing is readable until ledger_publish            */
    LEDGER->version = LEDGER_VERSION;
    LEDGER->kind = kind;
    LEDGER->record_count = 0;
    LEDGER->record_bytes = LEDGER_RECORD_BYTES;
    LEDGER->status = 0;
    LEDGER->rom_version = *(volatile uint16_t *)ROM_VERSION_ADDR;
    LEDGER->reserved = 0;
    /* Cleared rather than left as whatever the machine had: a driver that reads more records than
     * were written should see zeroes it can name, not a previous run's bytes. */
    for (index = 0; index < LEDGER_MAX_RECORDS * (LEDGER_RECORD_BYTES / 4); index++)
        ((volatile uint32_t *)LEDGER->records)[index] = 0;
}

void ledger_add(uint16_t id, const char *name, uint16_t flags,
                uint32_t v0, uint32_t v1, uint32_t v2, const void *blob, int blob_bytes)
{
    LedgerRecord *record;
    int index, copying = 1;

    if (LEDGER->record_count >= LEDGER_MAX_RECORDS)
        return;                             /* the count stops growing; the driver sees the cap     */
    record = &LEDGER->records[LEDGER->record_count];
    record->id = id;
    record->flags = flags;
    record->v0 = v0;
    record->v1 = v1;
    record->v2 = v2;
    /* Copied by hand, and the `copying` latch is why: reading past a short name's terminator to
     * fill eight bytes would walk off the end of the string literal. */
    for (index = 0; index < LEDGER_NAME_BYTES; index++) {
        if (copying && name[index] == 0)
            copying = 0;
        record->name[index] = copying ? name[index] : 0;
    }
    for (index = 0; index < LEDGER_BLOB_BYTES; index++)
        record->blob[index] = (blob && index < blob_bytes) ? ((const uint8_t *)blob)[index] : 0;
    LEDGER->record_count++;
}

void ledger_fail(void)
{
    if (LEDGER->record_count == 0)
        return;
    LEDGER->records[LEDGER->record_count - 1].flags |= LEDGER_FLAG_FAILED;
    if (LEDGER->status == 0)
        LEDGER->status = LEDGER->record_count;      /* the first failure's index + 1 */
}

void ledger_publish(void)
{
    LEDGER->magic = LEDGER_MAGIC;
}
