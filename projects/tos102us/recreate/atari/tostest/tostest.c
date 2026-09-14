/* tostest.c — TOSTEST.PRG, the conformance ledger.
 *
 * It calls a fixed set of TOS entry points with fixed arguments, records what each one answered
 * into the ledger at LEDGER_ADDR (../prg/ledger.h), publishes the ledger's magic and stops. The
 * host driver (../tostest.py) reads the block out of the machine and diffs it against the same
 * program's ledger under the ORIGINAL ROM. Tier 2 of the charter is that diff being empty.
 *
 * THE RECORD FIELDS, for this program: `v0` is the call's return value, `v1` and `v2` are whatever
 * second and third answer the call has (a pointer it filled in, a paired call's result, an index),
 * `blob` is up to eight bytes of a buffer it wrote, and `name` is the call. The per-call comments
 * below say which is which; nothing else needs to.
 *
 * IDS ARE STABLE AND GROUPED BY COMPONENT — 0x01xx BIOS, 0x02xx XBIOS, 0x03xx GEMDOS, and 0x04xx /
 * 0x05xx reserved for the VDI and the AES when those components land. An id is never reused for a
 * different call, so a ledger from today and one from a hundred calls hence line up row by row on
 * the ids they share. A repeated row (a directory walk) keeps ONE id and counts in `v2`.
 *
 * WHAT IS MASKED, and it is one thing: Tgetdate. Hatari seeds the emulated clock from the host, so
 * the date is a property of the day the capture was taken and not of the ROM. Everything else here
 * is required to be identical between two runs, which ../tostest.py proves before it is trusted as
 * a golden.
 *
 * THE CURSOR IS TURNED OFF BEFORE ANYTHING IS DRAWN, and that is not cosmetic: TOS's VT52 cursor
 * BLINKS off the vertical blank, so a CRC of the screen taken with it enabled is a coin flip on
 * where in the blink phase the capture lands. `console_cursor_off` (../prg/console.h) removes it.
 */
#include <stdint.h>
#include "console.h"
#include "ledger.h"
#include "st_screen.h"
#include "tosapi.h"

/* ---- the calls this ledger covers, by id ---------------------------------------------------- */
#define ID_KBSHIFT      0x0101
#define ID_DRVMAP       0x0102
#define ID_BCONOUT      0x0103
#define ID_PHYSBASE     0x0201
#define ID_LOGBASE      0x0202
#define ID_GETREZ       0x0203
#define ID_SCREEN_CRC   0x0204
#define ID_SVERSION     0x0301
#define ID_GETMPB       0x0302
#define ID_TGETDATE     0x0303
#define ID_MALLOC_MAX   0x0304
#define ID_MALLOC_BLOCK 0x0305      /* repeated: v2 is the block index */
#define ID_FSFIRST      0x0306
#define ID_DIRENTRY     0x0307      /* repeated: v2 is the entry index */

/* ---- fixed arguments ------------------------------------------------------------------------ */
#define KBSHIFT_READ_ONLY   (-1)            /* Kbshift's "report, do not set" mode */
#define MALLOC_LARGEST      (-1L)           /* Malloc's "how big is the biggest free block" */
#define MALLOC_BLOCKS       4
#define DIR_ENTRIES_MAX     16              /* a floppy root this project builds never has more */
static const char ROOT_PATTERN[] = "\\*.*";
static const char BANNER[] = "TOSTEST conformance ledger\r\n";

/* GEMDOS's memory parameter block: three pointers into the OS's own free/allocated lists. */
typedef struct { uint32_t mp_mfl, mp_mal, mp_rover; } Mpb;

/* The DTA a Fsfirst/Fsnext walk fills. Only the tail is documented data; the first 21 bytes are
 * GEMDOS's own scratch and are deliberately not recorded — they are not a conformance answer. */
typedef struct {
    uint8_t  d_reserved[21];
    uint8_t  d_attrib;
    uint16_t d_time;
    uint16_t d_date;
    uint32_t d_length;
    char     d_fname[14];
} Dta;

/* The host driver reads these two through the ledger's fields, and GEMDOS writes them by absolute
 * offset, so a padding byte GCC inserted would be a silent misread rather than a compile error. */
_Static_assert(sizeof(Dta) == 44, "the DTA is not GEMDOS's 44 bytes");
_Static_assert(sizeof(Mpb) == 12, "the MPB is not GEMDOS's three pointers");

static Dta dta;
static Mpb mpb;

/* ---- the screen ------------------------------------------------------------------------------ */
/* SCREEN_BYTES is ../st_screen.h's, the same number the ROM build paints into: a CRC taken over a
 * span that disagreed with the painter's would be a conformance failure with nothing wrong in
 * either program. */

static void console_string(const char *text)
{
    while (*text)
        Bconout(BCON_DEV_CON, (int16_t)(uint8_t)*text++);
}

/* ---- the ledger ------------------------------------------------------------------------------ */

static void record(uint16_t id, const char *name, uint32_t v0, uint32_t v1, uint32_t v2)
{
    ledger_add(id, name, 0, v0, v1, v2, 0, 0);
}

static void record_blob(uint16_t id, const char *name, uint16_t flags,
                        uint32_t v0, uint32_t v1, uint32_t v2, const void *blob, int blob_bytes)
{
    ledger_add(id, name, (uint16_t)(flags | LEDGER_FLAG_BLOB), v0, v1, v2, blob, blob_bytes);
}

static void probe_gemdos_identity(void)
{
    int32_t answer;

    record(ID_SVERSION, "Sversion", (uint32_t)Sversion(), 0, 0);

    /* Getmpb fills three pointers into the OS's memory lists; the return value is documented as
     * meaningless, so the answer IS the block. */
    answer = Getmpb(&mpb);
    record(ID_GETMPB, "Getmpb", (uint32_t)answer, mpb.mp_mfl, mpb.mp_mal);

    /* Masked: Hatari seeds the emulated clock from the host, so this is the day of the capture. */
    ledger_add(ID_TGETDATE, "Tgetdat", LEDGER_FLAG_MASKED, (uint32_t)Tgetdate(), 0, 0, 0, 0);
}

static void probe_bios(void)
{
    record(ID_KBSHIFT, "Kbshift", (uint32_t)Kbshift(KBSHIFT_READ_ONLY), 0, 0);
    record(ID_DRVMAP, "Drvmap", (uint32_t)Drvmap(), 0, 0);
}

/* Malloc's answers are addresses, and addresses are exactly what a composition test is for: they
 * say where the OS's free pool starts and how it hands blocks out. Every block is freed again, and
 * the Mfree result is recorded beside the address that produced it. */
static void probe_memory(void)
{
    int32_t blocks[MALLOC_BLOCKS];
    int block;

    record(ID_MALLOC_MAX, "MallocX", (uint32_t)Malloc(MALLOC_LARGEST), 0, 0);

    for (block = 0; block < MALLOC_BLOCKS; block++)
        blocks[block] = Malloc(MALLOC_BLOCK_BYTES);
    for (block = 0; block < MALLOC_BLOCKS; block++) {
        int32_t freed = blocks[block] ? Mfree((void *)blocks[block]) : 0;
        record(ID_MALLOC_BLOCK, "Malloc", (uint32_t)blocks[block], (uint32_t)freed, (uint32_t)block);
        if (blocks[block] == 0)
            ledger_fail();
    }
}

static void probe_directory(void)
{
    int32_t answer;
    int index;

    Fsetdta(&dta);
    answer = Fsfirst(ROOT_PATTERN, FA_NORMAL);
    record(ID_FSFIRST, "Fsfirst", (uint32_t)answer, 0, 0);
    if (answer != 0) {
        ledger_fail();
        return;
    }
    for (index = 0; index < DIR_ENTRIES_MAX && answer == 0; index++) {
        /* The disk's own file names are chosen distinct in their first LEDGER_BLOB_BYTES
         * characters, which is what the blob holds. */
        record_blob(ID_DIRENTRY, "DirEnt", 0, dta.d_length,
                    ((uint32_t)dta.d_time << 16) | dta.d_date, (uint32_t)index,
                    dta.d_fname, LEDGER_BLOB_BYTES);
        answer = Fsnext();
    }
}

/* The screen answers two ways: where the OS put it, and what is in it after the console driver has
 * been made to draw. The CRC is the drawing test — a VT52 that scrolls differently, or a font that
 * differs by one pixel, moves it. */
static void probe_screen(void)
{
    int32_t physical, logical;

    record(ID_GETREZ, "Getrez", (uint32_t)Getrez(), 0, 0);
    physical = Physbase();
    logical = Logbase();
    record(ID_PHYSBASE, "Physbas", (uint32_t)physical, 0, 0);
    record(ID_LOGBASE, "Logbase", (uint32_t)logical, 0, 0);

    console_string(BANNER);
    record(ID_BCONOUT, "Bconout", (uint32_t)(sizeof BANNER - 1), 0, 0);
    record(ID_SCREEN_CRC, "ScrnCRC", ledger_crc32((const void *)physical, SCREEN_BYTES),
           SCREEN_BYTES, 0);
}

int prg_main(void)
{
    console_cursor_off();

    ledger_begin(LEDGER_KIND_TEST);
    probe_gemdos_identity();
    probe_bios();
    probe_memory();
    probe_directory();
    probe_screen();
    ledger_publish();

    /* THE PROGRAM DOES NOT TERMINATE, and that is the design. The host stops the machine on the
     * ledger's magic and reads the block out of a machine that is still standing exactly where the
     * last record was written; a Pterm would hand control to the desktop, which would redraw the
     * screen the CRC above just measured and reuse the memory the ledger sits in. `_start` still
     * carries the Pterm for the day a mode wants it. */
    for (;;)
        ;
}
