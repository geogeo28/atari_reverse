/* bubble_backend.c — the GEM door, and the three libc functions a freestanding build owes GCC.
 *
 * THE GEM DOOR IS THE INTERESTING HALF. `os_vdi`/`os_aes` (shim_include/os.h) call in here rather
 * than trapping directly, because a `trap #2` cannot be made with the block the game built: every
 * pointer in it is an IMAGE OFFSET. That is exactly right in the differential's world, where the
 * image IS the machine's memory and starts at 0, and exactly right on the original, whose arrays
 * are absolute against the base it runs at. Here the VDI would take `0x236f0` for an address and
 * read its `contrl` out of the 68000's vector page.
 *
 * THE PARAMETER BLOCK IS RESTATED, NOT PATCHED. The trap is handed a block of the shim's own — the
 * same five (or six) pointers, translated — so the VDI still reads its operands out of, and writes
 * its answers into, the game's OWN arrays, with no copy back and no field this door has to know the
 * meaning of. The image's block is never touched at all.
 *
 * A RASTER COPY IS STILL PATCH-TRAP-RESTORE, because two of its operands are reached by
 * dereferencing the image rather than by being handed over: `contrl[7..10]` names two MFDBs, and
 * each MFDB names a raster. Those four longwords are patched in place and put straight back, so the
 * image the cores read afterwards holds exactly what it held before.
 *
 * NOTHING RE-ENTERS IT. The one interrupt this build installs is Timer C, whose handler is the
 * verified sound ISR and touches no GEM state at all, so a patch is never live across an interrupt
 * that could read it.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"

#include "bubble_mfdb.h"    /* ../include/blit.h, with its MFDB field offsets pinned against the
                             * kit's own — `frontend.h` below pulls blit.h in either way */
#include "bubble_target.h"
#include "frontend.h"       /* A_vdi_contrl and the parameter blocks' shapes */
#include "tos.h"

volatile uint32_t bg_vdi_calls;
volatile uint32_t bg_aes_calls;
volatile uint32_t bg_vdi_raster_copies;

/* ================================================================================================
 * The two parameter blocks, as counts of longwords
 * ============================================================================================= */

/* `vdi_pblock` @ 0x1e8ca is five array pointers — contrl, intin, ptsin, intout, ptsout — and the
 * AES block six: control, global, int_in, int_out, addr_in, addr_out. Both are spelt as counts
 * rather than as end addresses, because what the door does with them is a loop. */
#define VDI_POINTER_LONGS 5u
#define AES_POINTER_LONGS 6u
#define GEM_POINTER_LONGS AES_POINTER_LONGS   /* the longer of the two, so one staging block serves */
#define POINTER_BYTES     4u

_Static_assert(VDI_POINTER_LONGS <= GEM_POINTER_LONGS,
               "the staging block is sized for the AES's six longwords, and the VDI's block no "
               "longer fits in it — `build_machine_pblock` would write past the array");

/* The `contrl` word indices this door reads, the opcode whose operands are pointers, and the MFDB's
 * raster-pointer offset are ALL THE KIT'S — `VDI_CONTRL_OPCODE`, `VDI_CONTRL_SRC_MFDB`,
 * `VDI_CONTRL_DST_MFDB`, `VDI_VRO_CPYFM`, `MFDB_ADDR`, `MFDB_SCREEN_ADDR` in recreate_kit/include/os.h,
 * which the shadow beside this file pulls in. They are the same numbers the game's own binding
 * uses, and a second spelling of them here is exactly the drift CLAUDE.md §5 is about; a first draft
 * had one, and the compiler said so. */
#define WORD_SLOT_BYTES 2u

/* An image offset becomes a machine address — except 0, which is the VDI's "the screen" and must
 * stay 0 so that TOS substitutes the logical base `Setscreen` was given (../notes/frontend.md §1:
 * for this program that base is `screen_back`). Translating it would point the raster copy at the
 * bottom of the image instead. */
static uint32_t machine_address(uint32_t offset) {
    return offset == MFDB_SCREEN_ADDR ? MFDB_SCREEN_ADDR
                                      : (uint32_t)(uintptr_t)bg_image_base + offset;
}

/* THE BLOCK THE TRAP IS HANDED. It is static because it has to outlive this function by the length
 * of the trap, and it is `uint32_t` rather than bytes because this file is compiled for the 68000
 * alone: the machine's word order IS the image's, so a slot is one aligned `move.l`. Through a
 * `uint8_t *` it would not be — GCC knows a byte array's alignment is one and stores four times. */
static uint32_t g_machine_pblock[GEM_POINTER_LONGS];

static uint32_t contrl_word_address(uint32_t contrl, unsigned index) {
    return contrl + index * WORD_SLOT_BYTES;
}

/* contrl[7..8] and contrl[9..10] are each one LONGWORD written across two word slots, which is how
 * `vdi_set_src_mfdb` @ 0x16890 stores them. */
static uint32_t contrl_long(const uint8_t *mem, uint32_t contrl, unsigned index) {
    return be32(mem + contrl_word_address(contrl, index));
}

static void set_contrl_long(uint8_t *mem, uint32_t contrl, unsigned index, uint32_t value) {
    wr32(mem + contrl_word_address(contrl, index), value);
}

/* ================================================================================================
 * The door
 * ============================================================================================= */

/* The game's block of `longs` image offsets, restated as machine addresses in the shim's own. */
static void build_machine_pblock(const uint8_t *mem, uint32_t pblock, unsigned longs) {
    for (unsigned slot = 0; slot < longs; slot++)
        g_machine_pblock[slot] = machine_address(be32(mem + pblock + slot * POINTER_BYTES));
}

/* One MFDB of a raster copy, as the things the trap has to put back: the image offset `contrl` named
 * it by, and the raster address inside it. */
typedef struct {
    uint32_t mfdb;      /* what contrl[7..8] or contrl[9..10] held */
    uint32_t raster;    /* ...and what that MFDB's own fd_addr held */
    int translated;     /* ...unless the other operand named the SAME MFDB and did it already */
} SavedMfdb;

/* Both are patched IN PLACE, so the MFDB the VDI reads is the game's own. An earlier draft copied
 * each MFDB into the shim's memory instead and pointed `contrl` at the copy; the copy was twenty
 * BYTE moves through a pointer GCC could not prove even, and it was most of what this door cost
 * (atari/README.md, "Performance").
 *
 * ONE MFDB CAN BE BOTH OPERANDS, and that is what `already` is for. The copy this replaced was immune
 * by construction — it read the pristine image twice, into two separate buffers — and an in-place
 * patch is not: a second pass over the same block would translate an ALREADY translated raster, and
 * the restore would then leave a machine address in the game's own MFDB for good, silently and for
 * every later frame. No call site in this program does it (`../src/frontend.c` always passes
 * `A_mfdb_src` and `A_mfdb_dst`), so this costs one comparison a raster copy to keep an exported
 * entry point that takes both as arguments from being a landmine. */
static void patch_mfdb(uint8_t *mem, uint32_t contrl, unsigned contrl_index, SavedMfdb *saved,
                       const SavedMfdb *already) {
    saved->mfdb = contrl_long(mem, contrl, contrl_index);
    saved->raster = 0;
    saved->translated = already == 0 || already->mfdb != saved->mfdb;
    if (saved->translated) {
        saved->raster = be32(mem + saved->mfdb + MFDB_ADDR);
        wr32(mem + saved->mfdb + MFDB_ADDR, machine_address(saved->raster));
    }
    set_contrl_long(mem, contrl, contrl_index, machine_address(saved->mfdb));
}

static void restore_mfdb(uint8_t *mem, uint32_t contrl, unsigned contrl_index,
                         const SavedMfdb *saved) {
    if (saved->translated)
        wr32(mem + saved->mfdb + MFDB_ADDR, saved->raster);
    set_contrl_long(mem, contrl, contrl_index, saved->mfdb);
}

/* A raster copy's two MFDBs, patched. Answers whether it did anything, so the restore below runs
 * only for the call that needs it. */
static int stage_raster_copy(uint8_t *mem, uint32_t contrl, SavedMfdb *source,
                             SavedMfdb *destination) {
    if (be16(mem + contrl_word_address(contrl, VDI_CONTRL_OPCODE)) != VDI_VRO_CPYFM)
        return 0;

    patch_mfdb(mem, contrl, VDI_CONTRL_SRC_MFDB, source, 0);
    patch_mfdb(mem, contrl, VDI_CONTRL_DST_MFDB, destination, source);
    bg_vdi_raster_copies++;
    return 1;
}

int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock) {
    SavedMfdb source, destination;
    const unsigned longs = selector == GEM_VDI ? VDI_POINTER_LONGS : AES_POINTER_LONGS;
    int raster = 0;

    if (selector == GEM_VDI) {
        raster = stage_raster_copy(mem, A_vdi_contrl, &source, &destination);
        bg_vdi_calls++;
    } else {
        bg_aes_calls++;
    }

    build_machine_pblock(mem, pblock, longs);
    (void)bg_gem_trap((long)selector, g_machine_pblock);

    if (raster) {
        restore_mfdb(mem, A_vdi_contrl, VDI_CONTRL_SRC_MFDB, &source);
        restore_mfdb(mem, A_vdi_contrl, VDI_CONTRL_DST_MFDB, &destination);
    }
    /* The kit's door answers "modeled" — 1 when it serviced the call. TOS services every opcode
     * this program makes, and a `trap #2` has no way to say otherwise, so the answer is always 1
     * and the cores' refusal arms are unreachable here. That is a residual and not a claim: the
     * README's "Unpinned" section carries it. */
    return 1;
}

/* ================================================================================================
 * The three libc functions, hand-written
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC noticing that each of these is a memcpy or
 * a memset and replacing its body with a call to itself; `build.sh` passes it and there is no other
 * defence, so a build that lost the flag would recurse until the stack ran out.
 * ============================================================================================= */

void *memcpy(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    while (n--)
        *to++ = *from++;
    return dst;
}

void *memmove(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    if (to > from) {                       /* descending, so an overlap is read before it is written */
        to += n;
        from += n;
        while (n--)
            *--to = *--from;
        return dst;
    }
    while (n--)
        *to++ = *from++;
    return dst;
}

void *memset(void *dst, int c, unsigned long n) {
    uint8_t *to = dst;

    while (n--)
        *to++ = (uint8_t)c;
    return dst;
}
