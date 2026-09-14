/* tosbench.c — TOSBENCH.PRG, the performance ledger.
 *
 * Three workloads, each timed twice off the machine's own clocks, written into the same ledger
 * block TOSTEST uses (../prg/ledger.h) and read back by ../tosbench.py. The charter's Tier 3
 * on-target bar is `recreate / original <= 1.05` per workload; this program produces the two
 * numbers that ratio is made of, and the driver produces the spread that says how much of a
 * difference is real.
 *
 * THE RECORD FIELDS, for this program: `v0` is the elapsed `_hz_200` ticks, `v1` the iteration
 * count the workload ran, `v2` the elapsed `_frclock` (vertical blanks). Every record carries
 * LEDGER_FLAG_MASKED, because a timing is not a value two runs must agree on — the driver reports
 * it rather than diffing it. The Fread record's `blob` is the one field here that IS diffed; the
 * paragraph below says why it has to exist.
 *
 * TWO CLOCKS, NOT ONE, AND THEY ARE NOT REDUNDANT. `_hz_200` is timer C, 200 a second: fine
 * resolution, and it is the clock the charter names. `_frclock` counts vertical blanks: coarse, but
 * it comes from a completely different interrupt, so a workload whose cost moved in one and not the
 * other is a finding about the TIMER rather than about the workload. A rebuilt ROM that programs
 * timer C differently would otherwise report every workload faster or slower by the same ratio and
 * look like a uniform performance change.
 *
 * WHAT EACH WORKLOAD IS AIMED AT
 *   BCONOUT  the BIOS console and the VT52 driver behind it — per-character cost, plus whatever a
 *            scroll costs, since 2,000 characters overflow the screen many times.
 *   MALLOC   GEMDOS's memory manager: the allocate/free round trip on a pool with one hole in it.
 *   FREAD    the whole file-system stack — FAT walk, sector cache, the floppy driver and the DMA.
 *            8 KB chunks are 16 sectors, so the read crosses cluster and track boundaries.
 *
 * A TIMING IS NOT A PROOF THAT THE WORK HAPPENED, which is why the Fread record carries a CRC of
 * every byte it read (its blob). Without it the workload is timing a byte count GEMDOS reported,
 * and a rebuilt ROM that returned the right count from the wrong sectors — or from a cache it
 * never refilled — would post a timing that looks like a win. The fixture's bytes are a counter
 * whose period is coprime with both the sector and the cluster (../prg/fixtures.h), so a chunk
 * delivered from the wrong place moves the CRC.
 */
#include <stdint.h>
#include "console.h"
#include "fixtures.h"
#include "ledger.h"
#include "tosapi.h"

#define ID_BCONOUT      0x1001
#define ID_MALLOC       0x1002
#define ID_FREAD        0x1003

#define BCONOUT_CHARACTERS  2000
#define BCONOUT_FILLER      '.'          /* one glyph, so the cost is the driver and not the font */

#define MALLOC_ITERATIONS   1000

/* The file ../mkdata.py writes onto the bench floppy, named and sized by ../prg/fixtures.h so the
 * host that writes it and the target that reads it cannot disagree; the root-directory backslash is
 * this program's, since the fixture spec says nothing about where a disk puts the file. */
static const char DATA_FILE[] = "\\" FIXTURE_DATA_NAME;
#define DATA_FILE_BYTES     ((int32_t)FIXTURE_DATA_BYTES)
#define READ_CHUNK_BYTES    8192L
#define READ_CHUNKS         (DATA_FILE_BYTES / READ_CHUNK_BYTES)

static uint8_t read_buffer[READ_CHUNK_BYTES];

/* A workload's two clocks — a reading of both, or an elapsed span between two readings. Sampled in
 * this order every time so that the fine-grained clock brackets the coarse one identically on entry
 * and exit. */
typedef struct { uint32_t ticks, vbls; } Clocks;

static Clocks now(void)
{
    Clocks clocks;

    clocks.ticks = read_hz200();
    clocks.vbls = read_frclock();
    return clocks;
}

static Clocks since(Clocks started)
{
    Clocks ended = now(), elapsed;

    elapsed.ticks = ended.ticks - started.ticks;
    elapsed.vbls = ended.vbls - started.vbls;
    return elapsed;
}

/* `blob` is what the workload PRODUCED, for the workloads that produce something checkable; the
 * timings themselves are masked, so it is the only field of such a record two runs must agree on. */
static void record_workload(uint16_t id, const char *name, Clocks elapsed, uint32_t iterations,
                            const void *blob, int blob_bytes)
{
    uint16_t flags = (uint16_t)(LEDGER_FLAG_MASKED | (blob ? LEDGER_FLAG_BLOB : 0));

    ledger_add(id, name, flags, elapsed.ticks, iterations, elapsed.vbls, blob, blob_bytes);
}

static void bench_console(void)
{
    Clocks started = now();
    int index;

    for (index = 0; index < BCONOUT_CHARACTERS; index++)
        Bconout(BCON_DEV_CON, BCONOUT_FILLER);
    record_workload(ID_BCONOUT, "Bconout", since(started), BCONOUT_CHARACTERS, 0, 0);
}

static void bench_memory(void)
{
    Clocks started = now();
    uint32_t completed = 0;
    int index;

    for (index = 0; index < MALLOC_ITERATIONS; index++) {
        int32_t block = Malloc(MALLOC_BLOCK_BYTES);
        if (block == 0)
            break;                      /* the count in the record says how far it got */
        Mfree((void *)block);
        completed++;
    }
    record_workload(ID_MALLOC, "Malloc", since(started), completed, 0, 0);
    if (completed != MALLOC_ITERATIONS)
        ledger_fail();
}

/* THE CLOCK RUNS ONLY ACROSS THE Fread CALLS, so the workload is timed one chunk at a time and the
 * pieces are added up. Two things happen in this loop that are not the file system: the open (a
 * directory search — a different workload, and it would swamp the first chunk) is hoisted out
 * entirely, and the CRC of each chunk has to happen before the next read overwrites the buffer.
 * The CRC is a bitwise fold over 64 KB — hundreds of milliseconds on an 8 MHz 68000, comparable to
 * the read itself — so leaving it inside the span would not merely inflate the number: it would add
 * the SAME cost to both ROMs and drag every ratio toward 1.00, which is the one direction a bar of
 * "≤ 1.05" cannot survive being dragged in. */
static void bench_file(void)
{
    Clocks elapsed = {0, 0};
    int32_t handle, read_bytes = 0;
    uint32_t crc = LEDGER_CRC32_INIT;
    int chunk;

    handle = Fopen(DATA_FILE, FO_READ);
    if (handle < 0) {
        ledger_add(ID_FREAD, "Fread", LEDGER_FLAG_MASKED, 0, 0, (uint32_t)handle, 0, 0);
        ledger_fail();
        return;
    }
    for (chunk = 0; chunk < READ_CHUNKS; chunk++) {
        Clocks started = now();
        int32_t got = Fread((int16_t)handle, READ_CHUNK_BYTES, read_buffer);
        Clocks chunk_time = since(started);

        elapsed.ticks += chunk_time.ticks;
        elapsed.vbls += chunk_time.vbls;
        if (got <= 0)
            break;
        crc = ledger_crc32_update(crc, read_buffer, (uint32_t)got);
        read_bytes += got;
    }
    crc = ledger_crc32_final(crc);
    record_workload(ID_FREAD, "Fread", elapsed, (uint32_t)read_bytes, &crc, sizeof crc);
    Fclose((int16_t)handle);
    if (read_bytes != DATA_FILE_BYTES)
        ledger_fail();
}

int prg_main(void)
{
    console_cursor_off();

    ledger_begin(LEDGER_KIND_BENCH);
    bench_console();
    bench_memory();
    bench_file();
    ledger_publish();

    /* Stops rather than terminating, for TOSTEST's reason: the host reads the block out of a
     * machine standing where the last record was written. */
    for (;;)
        ;
}
