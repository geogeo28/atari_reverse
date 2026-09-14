/* ledger.h — the block of RAM TOSTEST.PRG and TOSBENCH.PRG leave behind, and the only definition of
 * its shape. The host drivers (../tostest.py, ../tosbench.py) parse it from this file's numbers.
 *
 * ONE FORMAT FOR BOTH PROGRAMS. A conformance answer and a timing are the same shape — an
 * identified call, a name, and three longwords — so they share a record and differ only in what the
 * three longwords mean (`kind` says which, and each program's header comment names its own fields).
 * That is what lets one parser, one masking rule and one comparator serve both, and it is what the
 * format has to survive when the conformance side grows from ten calls to the hundreds the charter's
 * Tier 2 asks for: a record is fixed-width and self-describing, so a new call is a new id and a new
 * row, never a new parser.
 *
 * THE MAGIC IS WRITTEN LAST AND THAT IS THE WHOLE SYNCHRONISATION. The host arms a Hatari
 * breakpoint on the longword at LEDGER_ADDR becoming LEDGER_MAGIC; when it reads the magic every
 * record behind it has already landed, so the `savebin` cannot catch a half-written table. Nothing
 * else in either driver would notice if it did.
 *
 * A FIXED ABSOLUTE ADDRESS, because the debugger has to name it in a breakpoint before the program
 * is loaded, and GEMDOS decides where the program goes. 0xC0000 is 768 KB up a 1 MB machine: above
 * anything an AUTO-folder program is loaded at, and below phystop with room to spare.
 */
#ifndef TOS102US_LEDGER_H
#define TOS102US_LEDGER_H

#include <stdint.h>

#define LEDGER_ADDR         0xC0000L
#define LEDGER_MAGIC        0x544F534CL     /* 'TOSL' */
#define LEDGER_VERSION      1

/* `kind`: which program wrote this ledger, so a driver refuses the other one's rather than
 * rendering timings as return values. */
#define LEDGER_KIND_TEST    0x54455354L     /* 'TEST' */
#define LEDGER_KIND_BENCH   0x424E4348L     /* 'BNCH' */

/* How much of the block a driver reads back. Generous on purpose: the conformance ledger is meant
 * to grow to hundreds of records, and a window that has to be widened in three files the day it
 * does is a window that will disagree with itself. 512 records is 16 KB. */
#define LEDGER_MAX_RECORDS  512
#define LEDGER_NAME_BYTES   8
#define LEDGER_BLOB_BYTES   8

/* Per-record flags. */
#define LEDGER_FLAG_MASKED  0x0001          /* v0..v2 vary run to run — the comparator ignores them */
#define LEDGER_FLAG_FAILED  0x0002          /* the call did not do what the program asked           */
#define LEDGER_FLAG_BLOB    0x0004          /* `blob` carries meaning; otherwise it reads zero      */

typedef struct {
    uint16_t id;                            /* stable across versions; never reused for another call */
    uint16_t flags;
    uint32_t v0, v1, v2;                    /* meaning is per program — see each program's header    */
    char     name[LEDGER_NAME_BYTES];       /* NUL-padded, so the ledger renders without a side table */
    uint8_t  blob[LEDGER_BLOB_BYTES];       /* the first bytes of a buffer the call filled            */
} LedgerRecord;

typedef struct {
    uint32_t magic;                         /* LEDGER_MAGIC — WRITTEN LAST                          */
    uint32_t version;
    uint32_t kind;
    uint32_t record_count;
    uint32_t record_bytes;                  /* sizeof(LedgerRecord), so a parser can check itself   */
    uint32_t status;                        /* 0 = every call did what was asked; else the first
                                             * failing record's index + 1                           */
    uint32_t rom_version;                   /* the version word at ROM_BASE+2, read by the program  */
    uint32_t reserved;
    LedgerRecord records[LEDGER_MAX_RECORDS];
} Ledger;

#define LEDGER_HEADER_BYTES 32              /* the eight longwords above; asserted in ledger.c      */
#define LEDGER_RECORD_BYTES 32              /* ...and the record, likewise                          */

/* The ROM header word every ledger records, so a capture says which ROM produced it. */
#define ROM_VERSION_ADDR    0xFC0002L

/* ---- the fingerprint a record carries -------------------------------------------------------
 * A record holds three longwords and eight blob bytes, and the things worth proving are far bigger
 * than that: a 32,000-byte screen, a 64 KB file. A CRC32 is how such a thing becomes one longword
 * a driver can diff, so it lives here beside the record rather than in whichever program needed it
 * first — TOSTEST checksums the screen, TOSBENCH the bytes a Fread delivered.
 *
 * INCREMENTAL, because a 64 KB file is read through an 8 KB buffer: start at LEDGER_CRC32_INIT,
 * fold each chunk in with ledger_crc32_update, and finish with ledger_crc32_final. */
#define LEDGER_CRC32_INIT   0xFFFFFFFFUL

uint32_t ledger_crc32_update(uint32_t crc, const void *data, uint32_t length);
static inline uint32_t ledger_crc32_final(uint32_t crc) { return ~crc; }

/* The whole-buffer case, which is the common one. */
static inline uint32_t ledger_crc32(const void *data, uint32_t length)
{
    return ledger_crc32_final(ledger_crc32_update(LEDGER_CRC32_INIT, data, length));
}

void ledger_begin(uint32_t kind);
/* One record. `name` is truncated/padded to LEDGER_NAME_BYTES; `blob` may be NULL. */
void ledger_add(uint16_t id, const char *name, uint16_t flags,
                uint32_t v0, uint32_t v1, uint32_t v2, const void *blob, int blob_bytes);
void ledger_fail(void);                     /* mark the record just added as the run's first failure */
void ledger_publish(void);                  /* write the magic; after this the host may read         */

#endif /* TOS102US_LEDGER_H */
