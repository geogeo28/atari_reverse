/* handles.c — GEMDOS's handle machinery: `Fforce` ($fc52de), `Fdup` ($fc5216) and `Fclose` ($fc56c6).
 * The resolution the dispatcher does before it calls a handler at all ($fc9924) is the dispatcher's own
 * arm, and lives with it (`src/gemdos/dispatch.c`).
 *
 * THE LAYER THESE THREE MAKE UP is the one between a program's handle and whatever the handle names:
 * a device, a standard-handle index, or an open-file descriptor (`include/gemdos/process.h`). A
 * descriptor naming a character device is theirs whole — its sign is all they read of it. One naming
 * a file is `Fclose`'s to hand on: its OFD goes to the file system's own close (`src/gemdos/fs_file.c`)
 * and, when the last reference goes, back to the pool.
 *
 * WHICH ARMS ARE RECONSTRUCTED:
 *
 *   `Fforce`  every arm. The bound, the device byte stored straight, the refusal of a source in
 *             0..5, an OFD that itself names a device, and the reference count a real file's gets.
 *   `Fdup`    every arm. The free-slot search, the table being full, the descriptor claimed for
 *             `p_run`, and both shapes of what it copies.
 *   `Fclose`  every arm. A negative handle, a standard handle naming a device, a descriptor
 *             naming one — including the release when the last reference goes — the EIHNDL a
 *             handle that names NOTHING answers, which is `$fc51c0` answering 0, and a handle that
 *             resolves to an open FILE, closed through `$fc57ee`.
 *
 * THE TABLE IS WALKED BY ADDRESS, NOT BY INDEX, and the arithmetic is signed on purpose. The ROM
 * computes `(handle - 6) * 10 + $8092` with `muls.w`, and `Fdup` reaches it with a handle it has
 * only proved to be `> 0` — so a standard handle of 1..5 in `p_uft` makes a NEGATIVE displacement
 * and reads the ten bytes before the table. That is the ROM's own shape and `gemdos_descriptor_of`
 * (`include/gemdos/process.h`) keeps it; what it adds is a host-only bound, the way `gemdos/gemdos.h`'s
 * handle accessor does, so the reconstruction says which addresses it claims to describe rather than
 * indexing off its array.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs_file.h"
#include "gemdos/memory.h"
#include "gemdos/process.h"
#include "machine.h"

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
 * the dispatcher's resolution ($fc9924): 6 and up is `handle - 6`, and 0..5 is the running process's `p_uft`
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

    descriptor = gemdos_descriptor_of(handle);
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
             be32(image + gemdos_descriptor_of(source) + HANDLE_VALUE));
    else
        wr32(image + descriptor + HANDLE_VALUE, (uint32_t)(int32_t)source);
    wr16(image + descriptor + HANDLE_REFCOUNT, 1);
    return (uint32_t)(slot + GEMDOS_FIRST_FILE_HANDLE);
}

/* A descriptor's reference count dropped by one — `subq.w #1,8(a0)` — and whether that was the last. */
static int drop_reference(uint8_t *image, uint32_t descriptor)
{
    uint16_t left = (uint16_t)(be16(image + descriptor + HANDLE_REFCOUNT) - 1);

    wr16(image + descriptor + HANDLE_REFCOUNT, left);
    return left == 0;
}

/* $fc56c6 ($3e) — close a handle: 0, or EIHNDL, or what the file system's close answered.
 *
 * THE STANDARD-HANDLE ARM CLEARS THE SLOT BEFORE IT KNOWS WHAT WAS IN IT, which is the order the ROM
 * stores in and therefore the order here: `clr.b` first, then the test that decides whether there is
 * anything else to do. A slot holding a device is the whole of the work; a slot holding a real
 * handle falls into the FILE arm below with that handle, and — this is the ROM's shape rather than
 * an omission — it does NOT re-check whether the descriptor names a device.
 *
 * THE DESCRIPTOR ARM IS A REFERENCE COUNT AND NOTHING ELSE while the descriptor names a device: drop
 * it, and on the last holder release the descriptor.
 *
 * WHAT THE TWO `bge`s FALL INTO IS ONE ARM AND IT HAS TWO OUTCOMES. A standard handle whose byte is
 * not negative, and a descriptor whose value is not negative, both reach $fc576a — which looks the
 * handle up ONE MORE TIME through `$fc51c0` and branches on what it finds. A value of 0 is a handle
 * that names NOTHING and answers `GEMDOS_EIHNDL` with nothing stored; a positive value is an open
 * FILE, and the file system CLOSES IT FIRST ($fc57ee, flags 0) — whoever else still holds the
 * descriptor. Only then is the count dropped, and the last holder gives the OFD back to the pool
 * before releasing the descriptor. What the close answered is the answer: 0, or EINTRN for an OFD
 * already off its directory's list — the last close of an `Fforce`d descriptor (count 2: the first
 * close unlinked the OFD and only dropped the count).
 *
 * `Fdup` + `Fclose` + `Fclose` IS A DOUBLE FREE, faithfully. `Fdup` gives the new descriptor its own
 * count of 1 naming the SAME OFD, so the first close unlinks the OFD and gives it back to the pool;
 * the second runs `$fc57ee` on the freed record (its entry rewritten again if it was dirty — nothing
 * clears OFD_DIRTY), answers EINTRN, and gives it back AGAIN: the chain then links the record to
 * itself and the next two `pool_get`s hand out the same record (`test_gemdos_fs_close.py`).
 */
uint32_t gemdos_fclose(uint8_t *image, int16_t handle)
{
    int16_t looked_up;                  /* what $fc576a is handed: the p_uft byte, or the handle */
    uint32_t ofd, descriptor, closed;

    if (handle < 0)
        return 0;
    if (is_a_standard_handle(handle)) {
        int16_t named = gemdos_standard_handle(image, (unsigned)handle);

        set_standard_handle(image, gemdos_basepage(image), handle, 0);
        if (named < 0)
            return 0;
        looked_up = named;
    } else {
        descriptor = gemdos_descriptor_of(handle);
        if ((int32_t)be32(image + descriptor + HANDLE_VALUE) < 0) {
            if (drop_reference(image, descriptor))
                gemdos_release_descriptor(image, descriptor);
            return 0;
        }
        looked_up = handle;
    }

    ofd = (uint32_t)gemdos_ofd_of_handle(image, looked_up);
    if (ofd == 0)
        return GEMDOS_EIHNDL;
    closed = gemdos_ofd_close(image, ofd, 0);
    descriptor = gemdos_descriptor_of(looked_up);
    if (drop_reference(image, descriptor)) {
        gemdos_pool_free(image, be32(image + descriptor + HANDLE_VALUE));
        gemdos_release_descriptor(image, descriptor);
    }
    return closed;
}
