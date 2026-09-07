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

/* AN IMAGE OFFSET BECOMES A MACHINE ADDRESS — except 0, which stays 0. Every pointer this door
 * hands the VDI goes through here: the parameter block's five (or six) array pointers, the image
 * offset `contrl[7..10]` names each MFDB by, and each MFDB's own `fd_addr`.
 *
 * THE SENTINEL IS REACHED, and this wave measured where. For an MFDB's `fd_addr` it is the VDI's
 * "the screen" and must stay 0 so that TOS substitutes the logical base `Setscreen` was given
 * (../notes/frontend.md §1: for this program that base is `screen_back`) — translating it would
 * point the raster copy at the bottom of the image. For a PARAMETER-BLOCK slot it is not a sentinel
 * at all, it is a slot the game has not filled yet: `init_globals` leaves all five of
 * `A_vdi_pblock`'s longwords ZERO (read off the post-init fixture, 2026-09-07) and
 * `../src/frontend.c`'s `v_opnvwk` fills `intin`, `intout` and `ptsout` but not `ptsin`, which it
 * writes only AFTER its own trap returns. So the first VDI call this program makes is made with a
 * ptsin of 0 — and the shipped binary makes it with a ptsin of 0 too, because its block is the same
 * zeroed array. Translating that slot would hand TOS a non-null pointer where the original hands
 * NULL, which is a difference on target with no surface anywhere in this tree.
 *
 * A first draft of this wave split the rule in two on the argument that a parameter-block 0 "cannot
 * arise", took ~46 cycles a raster call out of the door, and was green through both smokes. It is
 * recorded here rather than in a commit message because the reasoning is the transferable half: the
 * call it changes declares zero ptsin PAIRS, so TOS never dereferences what it was handed, and the
 * whole difference was invisible by accident.
 *
 * IT TRANSLATES AGAINST THE IMAGE IT WAS HANDED, not against `bg_image_base`, and that is the other
 * half of the same lesson. `os.h`'s `bg_machine_address` is the global-based spelling and is what
 * the OTHER doors use; here the caller already holds the image it is patching through, so taking it
 * as a parameter makes "these all name one image" a property of the code rather than a note over
 * it — and leaves this file with no second definition of the translation to drift from. */
static uint32_t machine_address(const uint8_t *mem, uint32_t offset) {
    return offset == MFDB_SCREEN_ADDR ? MFDB_SCREEN_ADDR : (uint32_t)(uintptr_t)(mem + offset);
}

/* THE BLOCK THE TRAP IS HANDED. It is static because it has to outlive this function by the length
 * of the trap, and it is `uint32_t` rather than bytes because this file is compiled for the 68000
 * alone: the machine's word order IS the image's, so a slot is one aligned `move.l`. Through a
 * `uint8_t *` it would not be — GCC knows a byte array's alignment is one and stores four times. */
static uint32_t g_machine_pblock[GEM_POINTER_LONGS];

/* THE `contrl` ARRAY IS REACHED THROUGH A CURSOR, NOT AN IMAGE OFFSET, and that is a measurement.
 * `A_vdi_contrl` is 0x236f0, far past the 68000's signed word displacement, so `mem + A_vdi_contrl +
 * index` makes GCC fold the whole constant back and spend `move.l #145136,d0` plus an indexed
 * `(0,a2,d0.l)` access — 26 to 32 cycles — for EVERY slot, however the source is parenthesised
 * (measured 2026-09-07: hoisting a plain local changes nothing, because GCC re-folds it; deleting
 * the barrier again puts every slot back on the indexed form, +56 B of code). Behind
 * `CURSOR_BARRIER` the base stays in one address register and each slot is `move.l 14(a0),d0` at 16
 * to 20.
 *
 * THAT IS A SECOND USE OF THE BARRIER, and `machine.h` documents only the first — "a pointer walked
 * by postincrement". Here it pins a base that never advances, to stop the folder rather than to keep
 * an increment. ../STATUS.md's wave 3b registers the difference for whoever hoists the measurement
 * into the kit beside `CURSOR_BARRIER`'s own note; it is not this file's to make.
 *
 * Only the WRITE side needs a mutable cursor, so the byte offset is what the two directions share. */
static unsigned contrl_word_offset(unsigned index) {
    return index * WORD_SLOT_BYTES;
}

/* contrl[7..8] and contrl[9..10] are each one LONGWORD written across two word slots, which is how
 * `vdi_set_src_mfdb` @ 0x16890 stores them. */
static uint32_t contrl_long(const uint8_t *contrl, unsigned index) {
    return be32(contrl + contrl_word_offset(index));
}

static void set_contrl_long(uint8_t *contrl, unsigned index, uint32_t value) {
    wr32(contrl + contrl_word_offset(index), value);
}

/* ================================================================================================
 * The door
 * ============================================================================================= */

/* ONE SLOT, as a function taking its two cursors rather than a macro reaching for two locals by
 * name — `../include/common.h`'s `copy_one_longword` is the same shape for the same reason, and the
 * object is byte-identical either way (measured 2026-09-07, so this is style with a measurement
 * behind it rather than in spite of one). */
static void stage_one_pointer(const uint8_t *mem, const uint8_t **offset_slot, uint32_t **staged) {
    *(*staged)++ = machine_address(mem, be32(*offset_slot));
    *offset_slot += POINTER_BYTES;
}

/* BOTH COUNTS ARE PINNED, because the run below hard-codes the VDI's in its SHAPE. An assert on the
 * DIFFERENCE alone is green for `4` and `5` — and `build_machine_pblock` would then stage a fifth
 * slot out of whatever follows the game's block, on every VDI call. */
_Static_assert(VDI_POINTER_LONGS == 5u,
               "the VDI block is no longer five longwords, and `build_machine_pblock` below spells "
               "five stores");
_Static_assert(AES_POINTER_LONGS == VDI_POINTER_LONGS + 1,
               "the AES block is no longer the VDI's five plus one, so the sixth slot below is no "
               "longer the whole of the difference between them");

/* The game's block of `longs` image offsets, restated as machine addresses in the shim's own.
 *
 * THE RUN IS SPELT OUT RATHER THAN LOOPED, and the objdump is the reason. As a loop GCC walks both
 * ends by postincrement — `movel %a0@+,%d0 / addl %d1,%d0 / movel %d0,%a1@+` — but `longs` arrives
 * CONSTANT after inlining, so it closes the loop against an ABSOLUTE end address (`cmpal #imm32,%a0`
 * at 14 cycles where a `dbf` is 10): 46 cycles a slot, 230 for the VDI's five. Spelt out, GCC drops
 * the postincrements for a displacement read and an absolute store and the five come to ~250 with
 * `machine_address`'s 0 test in them, 202 without — the door's biggest cost after the trap itself,
 * and the loop control is what the spelling buys back.
 *
 * Barriering either cursor is WORSE, measured both ways: on `offset_slot` the read moves off the
 * postincrement (72 cycles a slot), and on `staged` this function stops being inlined at all.
 *
 * `always_inline` on BOTH this and `stage_and_trap` is likewise a measurement: with the length
 * arriving as a value rather than a literal GCC puts one or the other out of line, and the `jsr`
 * then takes the door's six live values off the registers and back into the frame — the spills the
 * `noinline` note below describes, and 836 B of object against 688. */
__attribute__((always_inline))
static inline void build_machine_pblock(const uint8_t *mem, uint32_t pblock, unsigned longs) {
    const uint8_t *offset_slot = mem + pblock;
    uint32_t *staged = g_machine_pblock;

    stage_one_pointer(mem, &offset_slot, &staged);   /* contrl  / control */
    stage_one_pointer(mem, &offset_slot, &staged);   /* intin   / global  */
    stage_one_pointer(mem, &offset_slot, &staged);   /* ptsin   / int_in  */
    stage_one_pointer(mem, &offset_slot, &staged);   /* intout  / int_out */
    stage_one_pointer(mem, &offset_slot, &staged);   /* ptsout  / addr_in */
    if (longs == AES_POINTER_LONGS)
        stage_one_pointer(mem, &offset_slot, &staged);   /* ...and the AES's addr_out */
}

/* The block restated and handed over: every path through the door ends here, and the SELECTOR is
 * what says how long the block is — spelling the two at each call site would be one fact in two
 * places, and a mismatched pair either over-reads the game's block or leaves the AES's `addr_out`
 * holding the previous call's stale machine address. */
__attribute__((always_inline))
static inline void stage_and_trap(uint32_t selector, const uint8_t *mem, uint32_t pblock) {
    build_machine_pblock(mem, pblock,
                         selector == GEM_VDI ? VDI_POINTER_LONGS : AES_POINTER_LONGS);
    (void)bg_gem_trap((long)selector, g_machine_pblock);
}

/* A RASTER COPY IS ITS OWN FRAME, AND `noinline` IS A MEASUREMENT RATHER THAN DECORATION. Folded
 * into the door as a flag-guarded stage/restore pair around one shared trap, every value the restore
 * needs had to be initialised on the paths that stage nothing, and GCC kept all six in the stack
 * frame and reloaded them around the `jsr` — fifteen stack accesses at 16 to 28 cycles each, with
 * the callee-saved registers the door leaves free going unused (returning them as a struct by value
 * spills identically; measured, wave 3b). With a frame of its own the body is straight-line and the
 * six live in d2-d5/a2-a4 across the trap: the whole raster path counts 1,056 cycles off the objdump
 * against 1,190 for the same source inlined, so the extra `jsr` and `movem` pay for themselves.
 *
 * THE TWO MFDBs ARE PATCHED IN PLACE, so the MFDB the VDI reads is the game's own. An earlier draft
 * copied each into the shim's memory and pointed `contrl` at the copy; the copy was twenty BYTE
 * moves through a pointer GCC could not prove even, and it was most of what this door cost
 * (atari/README.md, "Performance").
 *
 * ITS THREE ARGUMENTS ALL NAME ONE IMAGE — `contrl` IS `mem + A_vdi_contrl` and `pblock` an offset
 * into the same `mem` — and that is now STRUCTURAL rather than a note: every translation below goes
 * through `machine_address(mem, ...)`, so a `contrl` from a second image would be patched with
 * addresses computed against that same second image rather than silently against a global one. The
 * old shape translated against `bg_image_base` while patching through `mem`, and said so in a
 * comment over `patch_mfdb`'s two parameters; this one has three and says it in the code. */
__attribute__((noinline))
static void raster_copy_call(uint8_t *mem, uint8_t *contrl, uint32_t pblock) {
    const uint32_t source_mfdb = contrl_long(contrl, VDI_CONTRL_SRC_MFDB);
    const uint32_t destination_mfdb = contrl_long(contrl, VDI_CONTRL_DST_MFDB);
    uint8_t *const source_raster_slot = mem + source_mfdb + MFDB_ADDR;
    const uint32_t source_raster = be32(source_raster_slot);
    /* ONE MFDB CAN BE BOTH OPERANDS, and a second pass over it would translate an ALREADY
     * translated raster — the restore would then leave a machine address in the game's own MFDB for
     * good, silently and for every later frame. No call site in this program does it
     * (`../src/frontend.c` always passes `A_mfdb_src` and `A_mfdb_dst`); the comparison keeps an
     * exported entry point that takes both as arguments from being a landmine. A staged slot is
     * never 0 because `mem` never is, so the pointer IS the "was it staged" flag. */
    uint8_t *destination_raster_slot = 0;
    uint32_t destination_raster = 0;

    wr32(source_raster_slot, machine_address(mem, source_raster));
    set_contrl_long(contrl, VDI_CONTRL_SRC_MFDB, machine_address(mem, source_mfdb));
    if (destination_mfdb != source_mfdb) {
        destination_raster_slot = mem + destination_mfdb + MFDB_ADDR;
        destination_raster = be32(destination_raster_slot);
        wr32(destination_raster_slot, machine_address(mem, destination_raster));
    }
    set_contrl_long(contrl, VDI_CONTRL_DST_MFDB, machine_address(mem, destination_mfdb));

    stage_and_trap(GEM_VDI, mem, pblock);

    wr32(source_raster_slot, source_raster);
    set_contrl_long(contrl, VDI_CONTRL_SRC_MFDB, source_mfdb);
    if (destination_raster_slot)
        wr32(destination_raster_slot, destination_raster);
    set_contrl_long(contrl, VDI_CONTRL_DST_MFDB, destination_mfdb);
}

int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock) {
    if (selector != GEM_VDI) {
        bg_aes_calls++;
        stage_and_trap(selector, mem, pblock);
    } else {
        uint8_t *contrl = mem + A_vdi_contrl;   /* ...and only a VDI call has one, so only it pays */

        CURSOR_BARRIER(contrl);
        bg_vdi_calls++;
        if (be16(contrl + contrl_word_offset(VDI_CONTRL_OPCODE)) == VDI_VRO_CPYFM) {
            bg_vdi_raster_copies++;
            raster_copy_call(mem, contrl, pblock);
        } else {
            stage_and_trap(GEM_VDI, mem, pblock);
        }
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
