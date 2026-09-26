/* fs_leaves.c — the two GEMDOS leaves over a whole drive: `Dfree` ($fc7a68) scans the FAT of a drive
 * it logs in, and `Dgetpath` ($fc6c1a) prints the process's directory node on one.
 *
 * Both open with the same five instructions ($fc7a74, $fc6c22) — an argument of 0 is the running
 * process's current drive and n is drive n-1 — and then log the drive in through `$fc67de`. What
 * they reach below that is the FAT engine and the record layer's path printer, which is why they sit
 * above the drive layer rather than in it.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_drive.h"
#include "gemdos/fs_io.h"
#include "gemdos/fs_leaves.h"
#include "gemdos/fs_records.h"
#include "machine.h"

/* The drive a Dfree/Dgetpath argument names: 1.. is drive n-1, 0 the running process's current
 * drive. A word, unbounded.
 *
 * The ROM stores the drive back into its own argument word before it uses it (`$fc7a8e`, `$fc6c3c`
 * `move.w d0,12(a6)`) and reads it from there. Not reproduced: the word is in the caller's frame, which
 * the differential drops on both shores, and nothing reads it after the leaf returns — unpinned. */
static int16_t drive_of_argument(const uint8_t *image, int16_t drive)
{
    if (drive != 0)
        return (int16_t)(drive - 1);
    return gemdos_current_drive(image);
}

/* $fc7a68 ($36) — the drive's free clusters, clusters, sector size and sector-per-cluster count into
 * the four longwords at `info`; 0, or -1 when the drive will not open (ENSMEM included: the ROM
 * answers `moveq #-1` for any negative WORD `$fc67de` hands back).
 *
 * THE COUNT SCANS CLUSTERS 2 .. m_numcl - 1 AND REPORTS m_numcl AS THE TOTAL: the data area's last
 * two clusters (`m_numcl`, `m_numcl` + 1) are never counted, free or not — the same two the allocator
 * never hands out (`src/gemdos/fs_io.c`). An entry is free when `$fc6038`'s WORD is 0. */
uint32_t gemdos_dfree(uint8_t *image, uint32_t info, int16_t drive)
{
    int16_t logged_in = (int16_t)gemdos_open_drive(image, drive_of_argument(image, drive));
    uint32_t dmd;
    int16_t cluster, free_clusters = 0;

    if (logged_in < 0)
        return GEMDOS_ERROR;
    dmd = gemdos_drive_dmd(image, logged_in);
    for (cluster = FIRST_DATA_CLUSTER; cluster < (int16_t)be16(image + dmd + DMD_NUMCL); cluster++)
        if ((uint16_t)gemdos_fat_get(0, image, (uint16_t)cluster, dmd) == 0)
            free_clusters++;
    wr32(image + info + DISKINFO_FREE, sign_ext16((uint16_t)free_clusters));
    wr32(image + info + DISKINFO_TOTAL, sign_ext16(be16(image + dmd + DMD_NUMCL)));
    wr32(image + info + DISKINFO_SECSIZ, sign_ext16(be16(image + dmd + DMD_RECSIZ)));
    wr32(image + info + DISKINFO_CLSIZ, sign_ext16(be16(image + dmd + DMD_CLSIZ)));
    return 0;
}

/* $fc6c1a ($47) — the running process's current directory on a drive, as "\A\B" at `path`; 0, or
 * EDRIVE with `path` made the empty string when the drive will not open.
 *
 * `$fc6bd2` leaves the text UNTERMINATED after a last `\`, and this writes the NUL over that `\` — so
 * the root, whose path is the lone `\`, comes back as "". */
uint32_t gemdos_dgetpath(uint8_t *image, uint32_t path, int16_t drive)
{
    int16_t named = drive_of_argument(image, drive);
    uint32_t end;

    if ((int32_t)gemdos_open_drive(image, named) < 0) {
        image[path] = '\0';
        return GEMDOS_EDRIVE;
    }
    end = gemdos_dnd_path(image, gemdos_current_directory(image, named), path);
    image[end - 1] = '\0';
    return 0;
}
