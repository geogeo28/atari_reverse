/* disk.h — the FILE-LOAD SEAM: "put the whole of this named file at this address".
 *
 * WHY A SEAM AND NOT A PORT. A game that loads from floppy does it through a raw sector driver — a
 * WD1772/DMA state machine and, above it, whatever on-disk filesystem the publisher used. That code
 * is hardware end to end: the memory differential cannot see a single one of its effects, so it is
 * not portable and not verifiable, and a kit that modelled the controller would be modelling a chip
 * in order to verify code nobody wants to read. What the layer ABOVE it wants is one answer — the
 * file's bytes, at an address — and that answer the kit can give.
 *
 * So a reconstruction cuts its boot chain at the LOWEST routine whose inputs are FILE-SHAPED (a
 * name, a destination) rather than sector-shaped (a track, a side, a sector count), declares
 * everything below that routine an excluded boundary, and calls `disk_read_file` across the cut.
 * That is a DECLARED SUBSTITUTION, not a reconstruction, and a project that uses it owes its reader
 * the seam's address, its callers, and what differs from the original's own loading — see
 * projects/wonderboy/recreate/STATUS.md's batch 44 phase B for this kit's first user and the shape
 * of that disclosure.
 *
 * WHAT MAKES THE SUBSTITUTION CHECKABLE. Off target this is `os_fopen`/`os_fread`/`os_fclose` over
 * the staged-file model (os.h, "staged files"), whose whole state — the table, the cursors, the
 * bytes — lives IN THE IMAGE. So when a case pokes the same substitution into the ORACLE as
 * hand-assembled GEMDOS traps, the two implementations' bookkeeping is compared by the ordinary byte
 * diff and nothing has to be taken on trust. The oracle's trap dispatch and this file's helper are
 * two statements of one model, and the differential is what holds them equal.
 *
 * ON-TARGET builds do not compile src/disk.c, exactly as they do not compile src/hw.c: a
 * reconstruction on a real Atari issues the real GEMDOS traps, and the project's backend defines
 * this symbol. It is a REAL symbol and deliberately not a `static inline` in os.h — an inline would
 * be compiled into the .PRG with nothing for a linker scan to catch, which is the false-green class
 * the on-target seam checks exist to refuse.
 */
#ifndef RECREATE_KIT_DISK_H
#define RECREATE_KIT_DISK_H

#include <stdint.h>

/* Read the whole of the file named by the NUL-terminated string at `name_ptr` (an image address) to
 * `dest` (an image address). Returns DISK_READ_OK, or DISK_READ_FAILED if the name does not resolve
 * or the file could not be read whole.
 *
 * THE RETURN IS THE SEAM'S CONTRACT, NOT THE BYTE COUNT. The routine being substituted for reports
 * success and failure, and a caller that tested a length would be testing something the original
 * never handed it. A project whose loader really does spend the length must widen this deliberately.
 *
 * READ TO EOF, NO LENGTH ARGUMENT. The caller of a whole-file loader does not know the length — the
 * original's own reader takes it from the directory entry it just found. Both sides ask for more
 * than the file holds and are served what there is, which is what GEMDOS `Fread` does on the machine
 * and what `os_fread` does in the model. */
int32_t disk_read_file(uint8_t *mem, uint32_t name_ptr, uint32_t dest);

#define DISK_READ_OK      0
#define DISK_READ_FAILED  (-1)

#endif /* RECREATE_KIT_DISK_H */
