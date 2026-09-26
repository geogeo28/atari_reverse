/* handles.c — GEMDOS's handle machinery: `Fforce` ($fc52de), `Fdup` ($fc5216), `Fclose` ($fc56c6)
 * and the resolution the dispatcher does before it calls a handler at all ($fc9924).
 *
 * THE LAYER THESE FOUR MAKE UP is the one between a program's handle and whatever the handle names,
 * and it is separable from the file system in exactly the way `include/gemdos/process.h` describes:
 * a handle is a device, a standard-handle index, or an open-file descriptor, and the only thing
 * these routines ever do with the THIRD one's contents is read its sign. A descriptor naming a
 * character device is theirs whole; one naming a file is the file system's the moment its reference
 * count reaches zero, and that is where each of them halts.
 *
 * WHICH ARMS ARE RECONSTRUCTED, and it is the whole of the device story:
 *
 *   `Fforce`  every arm. The bound, the device byte stored straight, the refusal of a source in
 *             0..5, an OFD that itself names a device, and the reference count a real file's gets.
 *   `Fdup`    every arm. The free-slot search, the table being full, the descriptor claimed for
 *             `p_run`, and both shapes of what it copies.
 *   `Fclose`  four of five. A negative handle, a standard handle naming a device, a descriptor
 *             naming one — including the release when the last reference goes — and the EIHNDL a
 *             handle that names NOTHING answers, which is `$fc51c0` answering 0. What halts is a
 *             handle that resolves to an open FILE, which is `$fc57ee`: the file system's own
 *             close, and not a branch of this.
 *   resolve   the walk itself, whole, and the EIHNDL it answers for a handle that names nothing.
 *             What halts is the routing BELOW it ($fc99bc), where a resolved CHARACTER DEVICE turns
 *             an `Fread` into a console read — that one needs `src/gemdos/console.c`'s leaves under
 *             a `Fread`/`Fwrite` that do not exist yet.
 *
 * THE TABLE IS WALKED BY ADDRESS, NOT BY INDEX, and the arithmetic is signed on purpose. The ROM
 * computes `(handle - 6) * 10 + $8092` with `muls.w`, and `Fdup` reaches it with a handle it has
 * only proved to be `> 0` — so a standard handle of 1..5 in `p_uft` makes a NEGATIVE displacement
 * and reads the ten bytes before the table. That is the ROM's own shape and `descriptor_of` below
 * keeps it; what it adds is a host-only bound, the way `gemdos/gemdos.h`'s handle accessor does, so the
 * reconstruction says which addresses it claims to describe rather than indexing off its array.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/process.h"
#include "machine.h"
#include "recreate.h"

/* The descriptor at an INDEX into the table — `muls.w #10` on a signed word, exactly as the ROM's
 * five copies of this arithmetic do it, with no bound of the ROM's own. Exported: the file system's
 * record layer claims and fills these records too (`src/gemdos/fs_records.c`). */
uint32_t gemdos_descriptor_at(int16_t index)
{
    int32_t at = (int32_t)GEMDOS_HANDLE_TABLE + (int32_t)index * GEMDOS_HANDLE_STRIDE;

#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at >= 0 && (uint32_t)at + GEMDOS_HANDLE_STRIDE <= ST_RAM_BYTES);
#endif
    return (uint32_t)at;
}

/* ...and the descriptor a HANDLE names. Every caller has already decided the handle is 6 or above,
 * except `Fdup`, which is where the negative displacement comes from. */
static uint32_t descriptor_of(int16_t handle)
{
    return gemdos_descriptor_at((int16_t)(handle - GEMDOS_FIRST_FILE_HANDLE));
}

/* One of the six standard handles of a basepage that is NOT necessarily `p_run` — `Pexec` forces
 * into the child's. `gemdos_standard_handle` is the `p_run` case of this and reads where this
 * writes; both go through `gemdos/gemdos.h`'s one host-only bound. */
static void set_standard_handle(uint8_t *image, uint32_t basepage, int16_t standard, uint8_t value)
{
    *gemdos_basepage_byte(image, basepage, BASEPAGE_HANDLES + (uint32_t)(int32_t)standard) = value;
}

/* `cmp.w #6 / blt` under a `tst.w / bmi`: 0..5 and nothing else. Both `Fforce`'s arms use it — once
 * on the handle it is writing INTO and once on the one it is writing, which is why a source handle
 * of 0..5 is EIHNDL rather than an alias. */
static int is_a_standard_handle(int16_t handle)
{
    return handle >= 0 && handle < BASEPAGE_STANDARD_HANDLES;
}

/* $fc5186 — WHICH RECORD a handle names, as a signed index into the table. A walk of its own and not
 * `gemdos_resolve_handle`'s: 6 and up is `handle - 6`, and 0..5 is the running process's `p_uft`
 * byte, minus six again if that byte is POSITIVE. A byte of 0 or below becomes the INDEX ITSELF — so
 * a standard handle naming nothing indexes record 0 and one naming a device indexes before the
 * table. The ROM applies no bound and neither does this.
 *
 * A NEGATIVE HANDLE IS NOT REFUSED HERE. `Fclose` proves its argument non-negative first, but
 * `Fread`, `Fwrite` and `Fseek` (`src/gemdos/fs_io.c`) pass the caller's handle straight in, as
 * `$fc5e6a`/`$fc5eea`/`$fc7cce` do — so the ROM reads the byte `-handle` places BELOW `p_uft`, and so
 * does this (the address arithmetic wraps to the same place). The only bounds are the host build's
 * RAM asserts on that read and on the record it then names.
 */
static int16_t record_index_of(const uint8_t *image, int16_t handle)
{
    int16_t named;

    if (handle >= GEMDOS_FIRST_FILE_HANDLE)
        return (int16_t)(handle - GEMDOS_FIRST_FILE_HANDLE);
    named = gemdos_standard_handle(image, (unsigned)handle);
    return named > 0 ? (int16_t)(named - GEMDOS_FIRST_FILE_HANDLE) : named;
}

/* $fc51c0 — ...and that record's first longword, which is what `Fclose` tells "names nothing" from
 * "names an open file" by, and the OFD `Fread`/`Fwrite`/`Fseek` work on (`src/gemdos/fs_io.c`). */
int32_t gemdos_ofd_of_handle(const uint8_t *image, int16_t handle)
{
    return (int32_t)be32(image + gemdos_descriptor_at(record_index_of(image, handle)) + HANDLE_VALUE);
}

/* $fc52f8 — `Fforce`'s whole body, over a basepage the caller names.
 *
 * THREE ARMS AND ONE OF THEM IS THE POINT. A NEGATIVE `handle` is a character device and is stored
 * as the byte it is; a handle of 6 or above is looked up, and if the descriptor itself names a
 * device then THAT device's byte is stored rather than the handle — so `Fforce(1, Fdup(0))` leaves
 * stdout holding -1 again and the descriptor's reference count untouched. Only a descriptor naming
 * a real file leaves the handle NUMBER in `p_uft`, and that is the one arm that takes a reference.
 */
uint32_t gemdos_force_handle(uint8_t *image, int16_t standard, int16_t handle, uint32_t basepage)
{
    uint32_t descriptor;
    int32_t named;

    if (!is_a_standard_handle(standard))
        return GEMDOS_EIHNDL;
    if (handle < 0) {
        set_standard_handle(image, basepage, standard, (uint8_t)handle);
        return 0;
    }
    if (handle < GEMDOS_FIRST_FILE_HANDLE)
        return GEMDOS_EIHNDL;

    descriptor = descriptor_of(handle);
    named = (int32_t)be32(image + descriptor + HANDLE_VALUE);
    if (named < 0) {
        set_standard_handle(image, basepage, standard, (uint8_t)named);
        return 0;
    }
    set_standard_handle(image, basepage, standard, (uint8_t)handle);
    wr16(image + descriptor + HANDLE_REFCOUNT,
         (uint16_t)(be16(image + descriptor + HANDLE_REFCOUNT) + 1));
    return 0;
}

/* $fc52de ($46) — the trap leaf: the same thing on the running process. Four instructions in the
 * ROM, and every claim about it is a claim about the routine above. */
uint32_t gemdos_fforce(uint8_t *image, int16_t standard, int16_t handle)
{
    return gemdos_force_handle(image, standard, handle, gemdos_basepage(image));
}

/* $fc5216 ($45) — a new open-file descriptor that names whatever `standard` names.
 *
 * WHAT IT COPIES IS THE DESCRIPTOR'S FIRST LONGWORD AND NOT ITS REFERENCE COUNT, which is what makes
 * this a duplicate rather than a reference: the new descriptor starts at ONE however many holders
 * the old one had. Reproduced rather than corrected — a program that `Fdup`s a file and closes both
 * halves closes the file twice in TOS 1.02.
 *
 * THE SEARCH IS FOR A FREE OWNER, not a free value: a descriptor is spare when nobody owns it, which
 * is the field `gemdos_release_process` and `Fclose` both zero when they let one go.
 */
uint32_t gemdos_fdup(uint8_t *image, int16_t standard)
{
    uint32_t descriptor;
    int16_t slot, source;

    if (!is_a_standard_handle(standard))
        return GEMDOS_EIHNDL;

    for (slot = 0; slot < GEMDOS_HANDLE_COUNT; slot++)
        if (be32(image + GEMDOS_HANDLE_TABLE + (uint32_t)slot * GEMDOS_HANDLE_STRIDE + HANDLE_OWNER) == 0)
            break;
    if (slot == GEMDOS_HANDLE_COUNT)
        return GEMDOS_ENHNDL;

    descriptor = GEMDOS_HANDLE_TABLE + (uint32_t)slot * GEMDOS_HANDLE_STRIDE;
    wr32(image + descriptor + HANDLE_OWNER, gemdos_basepage(image));

    source = gemdos_standard_handle(image, (unsigned)standard);
    /* `ble`, so a handle of 0 — an unused slot — takes the same arm a device does and the new
     * descriptor is left naming 0. The dispatcher's resolution answers EIHNDL for exactly that. */
    if (source > 0)
        wr32(image + descriptor + HANDLE_VALUE,
             be32(image + descriptor_of(source) + HANDLE_VALUE));
    else
        wr32(image + descriptor + HANDLE_VALUE, (uint32_t)(int32_t)source);
    wr16(image + descriptor + HANDLE_REFCOUNT, 1);
    return (uint32_t)(slot + GEMDOS_FIRST_FILE_HANDLE);
}

/* $fc56c6 ($3e) — close a handle, and answer 0 whatever happened on every arm this reconstructs.
 *
 * THE STANDARD-HANDLE ARM CLEARS THE SLOT BEFORE IT KNOWS WHAT WAS IN IT, which is the order the ROM
 * stores in and therefore the order here: `clr.b` first, then the test that decides whether there is
 * anything else to do. A slot holding a device is the whole of the work; a slot holding a real
 * handle falls into the FILE arm below with that handle, and — this is the ROM's shape rather than
 * an omission — it does NOT re-check whether the descriptor names a device.
 *
 * THE DESCRIPTOR ARM IS A REFERENCE COUNT AND NOTHING ELSE while the descriptor names a device: drop
 * it, and on the last holder zero the value and the owner, which is what puts the slot back in
 * `Fdup`'s search.
 *
 * WHAT THE TWO `bge`s FALL INTO IS ONE ARM AND IT HAS TWO OUTCOMES. A standard handle whose byte is
 * not negative, and a descriptor whose value is not negative, both reach $fc576a — which looks the
 * handle up ONE MORE TIME through `$fc51c0` and branches on what it finds. A value of 0 is a handle
 * that names NOTHING and answers `GEMDOS_EIHNDL` with nothing stored; only a positive value is a
 * real open FILE, and that is the arm with a whole close behind it ($fc57ee flushes and releases the
 * file system's record) and the one that halts.
 */
uint32_t gemdos_fclose(uint8_t *image, int16_t handle)
{
    int16_t looked_up;                  /* what $fc576a is handed: the p_uft byte, or the handle */

    if (handle < 0)
        return 0;
    if (is_a_standard_handle(handle)) {
        int16_t named = gemdos_standard_handle(image, (unsigned)handle);

        set_standard_handle(image, gemdos_basepage(image), handle, 0);
        if (named < 0)
            return 0;
        looked_up = named;
    } else {
        uint32_t descriptor = descriptor_of(handle);

        if ((int32_t)be32(image + descriptor + HANDLE_VALUE) < 0) {
            uint16_t left = (uint16_t)(be16(image + descriptor + HANDLE_REFCOUNT) - 1);

            wr16(image + descriptor + HANDLE_REFCOUNT, left);
            if (left != 0)
                return 0;
            wr32(image + descriptor + HANDLE_VALUE, 0);
            wr32(image + descriptor + HANDLE_OWNER, 0);
            return 0;
        }
        looked_up = handle;
    }
    if (gemdos_ofd_of_handle(image, looked_up) == 0)
        return GEMDOS_EIHNDL;
    recreate_not_reconstructed("GEMDOS: Fclose of a handle that names an open FILE");
}

/* $fc9924 — which handle a call's arguments name, and what it resolves to.
 *
 * WHICH WORD holds the handle is the descriptor's to say, and it says it by being $81: that is
 * `Fseek`, whose first argument is a LONGWORD offset, so its handle is the third word. `Fread` and
 * `Fwrite` are $82 and take the handle first. No other selector reaches here — the character-device
 * group has had its descriptor rewritten by the time the `btst #7` runs (`src/gemdos/dispatch.c`).
 *
 * The walk itself is `gemdos/process.h`'s three kinds, and what comes back is a LONGWORD rather than
 * a handle: 0 for a handle that names nothing, negative for a character device, and the file
 * system's own pointer otherwise.
 */
int32_t gemdos_resolve_handle(const uint8_t *image, uint32_t arguments, uint16_t descriptor)
{
    uint32_t at = arguments + (descriptor == GEMDOS_DESC_HANDLE_AT_THIRD_WORD
                               ? GEMDOS_ARGUMENT_THIRD_WORD : GEMDOS_ARGUMENT_WORD);
    int16_t handle = (int16_t)be16(image + at);

    if (handle >= GEMDOS_FIRST_FILE_HANDLE)
        return (int32_t)be32(image + descriptor_of(handle) + HANDLE_VALUE);
    if (handle < 0)
        return handle;
    handle = gemdos_standard_handle(image, (unsigned)handle);
    if (handle > 0)
        return (int32_t)be32(image + descriptor_of(handle) + HANDLE_VALUE);
    return handle;
}
