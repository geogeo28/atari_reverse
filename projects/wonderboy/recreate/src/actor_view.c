/* actor_view.c — the two halves of include/actor_view.h that must NOT be in the header: the slow
 * arm of the door, and the all-live mask a proved record points at.
 *
 * WHY THEY ARE HERE AND NOT `static inline` NEXT DOOR. The header's whole claim is that proving an
 * actor's record is one decision made once, and both halves of that claim would be undone by a copy
 * per module:
 *
 *   * THE ARM MUST NOT INLINE. It is reached by three cases in test_behavior.py and by no frame the
 *     game has ever run — every record the game builds lies inside the image — so inlining its
 *     thirty-two-iteration fill and give-back into each of the hundred-odd doors would spend exactly
 *     the text the change is buying. `static __attribute__((noinline))` in the header says that but
 *     gives each including module its own copy; `static inline __attribute__((noinline))` is refused
 *     by GCC on m68k (-Wattributes) and drops the attribute that matters. One extern definition says
 *     it once and means it in every module.
 *   * TWO SYMBOLS OF ONE NAME ARE A PROFILER FAULT, not an inefficiency. `atari/profile.py`
 *     aggregates cycles BY NAME and refuses a link that names anything twice, because one symbol
 *     would otherwise be charged with the other's work. The header's `static` copies made
 *     `ACTOR_RECORD_ALL_LIVE` and both arms exactly that, once src/map.c, src/player.c and
 *     src/actor.c joined src/behavior.c in opening doors.
 *
 * What STAYS in the header is what must inline to be worth anything: `actor_view_open`'s single
 * bound, and the `rec_*` accessors that are one `d16(An)` each.
 */
#include <stdint.h>

#include "actor_view.h"
#include "bus.h"
#include "machine.h"
#include "os.h"
#include "wonderboy.h"

/* ALIGNED, AND IT IS THE 68000 THAT SAYS SO. `rec_set_w`/`rec_set_l` fetch this array with
 * `be16`/`be32`, which on the big-endian target ARE `move.w`/`move.l` (the kit's machine.h), so an
 * odd base here is an ADDRESS ERROR at every masked store — on the fast arm, which is every store the
 * game makes. A `const uint8_t[]` has ABI alignment 1 and `atari/tos.ld` folds .rodata into .text, so
 * where it lands is whatever the input before it left: green by luck rather than by construction.
 * NO SURFACE HERE CAN SEE IT — the differential .so is little-endian and takes machine.h's byte-wise
 * arm — which is the same shape as the SUBALIGN(1) fault in tos.ld that `smoke.py floppy` caught. */
const uint8_t ACTOR_RECORD_ALL_LIVE[WB_ACTOR_RECORD_BYTES] __attribute__((aligned(4))) = {
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
};

/* The record does not lie wholly inside the image: it is off it, or it straddles the top, or its
 * address is high enough that the 24-bit bus wraps it back to the bottom mid-record. Fill a scratch
 * through `bus_read_byte`, which carries the mask, the wrap and the bound, and record the same
 * predicate per byte as the write mask. */
__attribute__((noinline))
ActorRecord actor_view_open_scratch(ActorView *view, uint8_t *image, uint32_t address) {
    ActorRecord record;

    view->image = image;
    view->address = address;
    for (uint32_t offset = 0; offset < WB_ACTOR_RECORD_BYTES; offset++) {
        uint32_t at = addr_add(address, offset) & WB_BUS_ADDR_MASK;

        view->live[offset] = os_in_image_fixed(at, 1) ? 0xff : 0x00;
        view->scratch[offset] = bus_read_byte(image, at);
    }
    record.bytes = view->scratch;
    record.live = view->live;
    return record;
}

/* Give the whole record back, every byte of it, and let `bus_write_byte` drop the ones the bus does
 * not carry. A byte the body never touched is written with the value the open read, which is the
 * value the image still holds — so the copy is a no-op for it unless SOMETHING ELSE changed that
 * byte while the door was open, and that is the one case this is not exact.
 *
 * NOTHING CAN REACH THAT CASE, and it is worth saying why rather than leaving it to be re-derived.
 * An earlier revision compared against an `as_found` copy and gave back only what the body changed,
 * to protect a byte a HELPER holding the record's ADDRESS had written; every such helper now takes
 * the record instead (src/actor.c, ../STATUS.md's enumeration), so what is left is a byte inside the
 * record's window that some routine writes as a GLOBAL. On this arm the window can only be two
 * things — the image's very top, where the record straddles it, or $0..$1f, where a record above
 * $ffffe0 wraps onto the 68000's vector page — and no reconstructed routine writes either. The
 * selectivity was therefore unpinnable: making this a blanket copy left the whole suite green, and a
 * guard nothing can fail is a guard nobody can maintain. */
__attribute__((noinline))
void actor_view_close_scratch(ActorView *view) {
    for (uint32_t offset = 0; offset < WB_ACTOR_RECORD_BYTES; offset++)
        bus_write_byte(view->image, addr_add(view->address, offset), view->scratch[offset]);
}
