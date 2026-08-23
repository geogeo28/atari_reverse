/* disk.c — the off-target half of the file-load seam. WHY it exists is in ../include/disk.h.
 *
 * It lives in the kit, beside src/hw.c and src/psg.c, because the seam is kit-wide: any game whose
 * boot chain ends in a sector driver wants the same substitution, and kit.mk sweeps every kit source
 * into every project's candidate — so this is one implementation shared by every game rather than a
 * copy per project.
 *
 * NO LEDGER, and that is a decision rather than an omission. src/hw.c and src/psg.c export ordered
 * read/write streams because the effects they model are OFF-IMAGE and so invisible to the byte diff.
 * This one is the opposite: the staged-file table, every cursor, every open flag and every byte
 * served all live inside the image, so a candidate that opened the wrong file, read the wrong count,
 * or forgot to close is separable from a correct one by the ordinary comparison. Adding a ledger
 * here would compare the model against itself.
 */
#include <stdint.h>

#include "os.h"
#include "disk.h"

/* More than any staged file can hold, so `os_fread` serves what there is and stops at EOF. It is
 * the image size and not a round number because that is the true ceiling: `os_fread` clamps to the
 * file's remaining length first and then refuses a copy that would leave the image, so no larger
 * request can ever move more bytes than a file really has. */
#define DISK_READ_TO_EOF  OS_IMAGE_SIZE

int32_t disk_read_file(uint8_t *mem, uint32_t name_ptr, uint32_t dest) {
    /* BOUND THE NAME BEFORE `os_fopen` READS THROUGH IT. `os_fopen` compares up to OS_FS_NAME bytes
     * at `mem + name_ptr` with no check of its own, so a wild pointer reads off the end of the
     * harness's buffer — on the CANDIDATE side only, since the oracle's Musashi masks an access to
     * the 24-bit bus before it decodes it. The two shores would then refuse on different inputs and
     * the difference would present as a mystery diff. `dest` needs no check here: `os_fread` bounds
     * the copy itself and refuses one that would leave the image. */
    if (!os_in_image(name_ptr, OS_FS_NAME))
        return os_refused(DISK_READ_FAILED);

    int32_t handle = os_fopen(mem, name_ptr);
    if (handle < 0)
        return DISK_READ_FAILED;                  /* os_fopen already tallied the refusal */

    int32_t got = os_fread(mem, (uint16_t)handle, DISK_READ_TO_EOF, dest);
    /* CLOSE EVEN ON A FAILED READ. The slot is a finite resource (OS_FS_SLOTS of them) and a run
     * that leaked one would change the table's bytes, which the byte diff compares — so a leak here
     * is not merely untidy, it is a divergence from the oracle's own stub, which closes. */
    (void)os_fclose(mem, (uint16_t)handle);
    return got < 0 ? DISK_READ_FAILED : DISK_READ_OK;
}
