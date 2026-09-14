/* BIOS Getmpb (function 0) — $fc0a46.
 *
 * Hands the caller the memory parameter block GEMDOS starts from: a free list holding ONE descriptor
 * that spans the whole TPA, an empty allocated list, and the rover parked on the free list. It is
 * how a program that wants to run GEMDOS's memory manager itself gets the initial world; TOS itself
 * calls it once, out of the GEMDOS init.
 *
 *      movea.l 4(sp),a0            ; the MPB the CALLER supplies — three longwords
 *      lea     OS_MEMORY_DESCRIPTOR,a1
 *      move.l  a1,(a0)             ; mp_mfl   = the ROM's own root descriptor
 *      clr.l   4(a0)               ; mp_mal   = nothing allocated yet
 *      move.l  a1,8(a0)            ; mp_rover = the free list's head
 *      clr.l   (a1)                ; m_link   = the list ends here
 *      move.l  SYSVAR_MEMBOT,4(a1) ; m_start  = the bottom of the TPA
 *      move.l  SYSVAR_MEMTOP,d0
 *      sub.l   SYSVAR_MEMBOT,d0
 *      move.l  d0,8(a1)            ; m_length = memtop - membot
 *      clr.l   12(a1)              ; m_own    = unowned
 *      rts
 *
 * THE DESCRIPTOR IS NOT THE CALLER'S. Both lists point at $048e, a fixed block in the OS's own low
 * RAM, so two callers get MPBs that share one descriptor and the second call rebuilds the first's.
 * That is the ROM's design, not a transcription slip: the descriptor is rebuilt from `_membot` and
 * `_memtop` every time, which is why a case that moves either of them is the sharp one.
 *
 * `_membot` IS READ AFTER THE THREE MPB STORES, and twice — once for `m_start` and once inside the
 * subtraction. Neither is an accident of transcription: the MPB is the CALLER's pointer and nothing
 * bounds it, so an MPB laid over the system variables has its three stores land on `_membot` itself
 * before the read. A reconstruction that hoisted the read to the top would describe the machine as
 * it was on entry rather than as those stores left it, and `test_bios_getmpb.py` stages exactly that
 * overlap (`mp_rover` on `_membot`).
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"

#define LIST_HEAD_BYTES 4       /* one longword: a list head in the MPB, a field in the descriptor */

void bios_getmpb(uint8_t *image, uint32_t mpb)
{
    uint8_t *descriptor = image + OS_MEMORY_DESCRIPTOR;

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* The MPB is the CALLER's pointer and the routine does not check it; a case that passed one
     * outside RAM would index the candidate's `uint8_t *image` into host memory rather than diverge.
     * HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to abort"). */
    assert(mpb + MPB_ROVER + LIST_HEAD_BYTES <= ST_RAM_BYTES);
#endif

    wr32(image + addr_add(mpb, MPB_FREE_LIST), OS_MEMORY_DESCRIPTOR);
    wr32(image + addr_add(mpb, MPB_ALLOCATED_LIST), 0);
    wr32(image + addr_add(mpb, MPB_ROVER), OS_MEMORY_DESCRIPTOR);

    /* ...and only now `_membot`, twice, exactly where the ROM reads it (see the note above). */
    wr32(descriptor + MD_LINK, 0);
    wr32(descriptor + MD_START, be32(image + SYSVAR_MEMBOT));
    wr32(descriptor + MD_LENGTH, be32(image + SYSVAR_MEMTOP) - be32(image + SYSVAR_MEMBOT));
    wr32(descriptor + MD_OWNER, 0);
}
