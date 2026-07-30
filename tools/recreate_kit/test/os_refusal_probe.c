/* os_refusal_probe.c — the fixture behind test_os_refusal.py.
 *
 * Every `os_*` helper in ../include/os.h that cannot serve a call routes its sentinel through
 * os_refused(), which is what makes a candidate-side refusal visible to harness.differential()
 * (see "refusing a call, on BOTH sides" in os.h). Nothing else pins those call sites: the
 * differential suites cannot, because a CORRECT reconstruction never reaches one — which is exactly
 * why reverting any single `return os_refused(...)` to a bare `return` leaves every game suite
 * green. This drives each helper directly and reports how much the tally moved.
 *
 * Output is one line per case: `<case-name> <tally delta>`. The Python side owns the expectations,
 * so adding a case here without claiming its delta there fails loudly rather than silently.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "os.h"

/* The model bounds its copies against OS_IMAGE_SIZE, and OS_FS_TABLE lives near the top of it, so
 * the probe needs a full-size image rather than a small scratch buffer. */
#define PROBE_STAGED_NAME  0x1000u   /* where the staged filename string sits */
#define PROBE_OTHER_NAME   0x1020u   /* a filename the table does not hold */
#define PROBE_BUF          0x2000u   /* an in-image transfer buffer */
#define PROBE_XFER_BYTES   4u        /* bytes moved by the Fread/Fwrite "served" cases */
#define PROBE_FILE_BYTES   8u        /* the staged file's length and reserved capacity */

/* GEM parameter block: apb[0] -> contrl, apb[3] -> intout (os_gem_trap reads both). */
#define PROBE_PBLK         0x3000u
#define PROBE_CONTRL       0x3100u
#define PROBE_INTOUT       0x3200u
#define PROBE_BAD_OPCODE   0x7fffu   /* in neither the AES nor the VDI modeled set */
#define PROBE_BAD_SUBSYS   0x0001u   /* neither GEM_AES nor GEM_VDI */

#define PROBE_BAD_HANDLE   0x0100u   /* far outside OS_FS_FIRST_HANDLE .. +OS_FS_SLOTS */
#define PROBE_BAD_SUPER    0x0decadeu /* a "stack pointer" os_super never handed out */
#define PROBE_WILD_ADDR    0xfffffff0u /* a buffer address outside the image */

static uint8_t *g_image;
static uint32_t g_before;

static void image_reset(void) {
    memset(g_image, 0, OS_IMAGE_SIZE);
    memcpy(g_image + PROBE_STAGED_NAME, "STAGED.DAT", 11);
    memcpy(g_image + PROBE_OTHER_NAME, "ABSENT.DAT", 11);

    uint8_t *entry = os_fs_slot(g_image, 0);
    memcpy(entry, "STAGED.DAT", 11);
    wr32(entry + OS_FS_OFF_STAGING, OS_FS_STAGING);
    wr32(entry + OS_FS_OFF_SIZE, PROBE_FILE_BYTES);
    wr32(entry + OS_FS_OFF_CURSOR, 0);
    wr32(entry + OS_FS_OFF_OPEN, 1);
    wr32(entry + OS_FS_OFF_CAPACITY, PROBE_FILE_BYTES);

    wr32(g_image + PROBE_PBLK + 0 * 4, PROBE_CONTRL);
    wr32(g_image + PROBE_PBLK + 3 * 4, PROBE_INTOUT);
}

/* Each case runs on a freshly reset image so one case's image effect cannot steer the next. */
static void begin(void) {
    image_reset();
    g_os_refusal_reset();
    g_before = g_os_refusal_count();
}

static void report(const char *name) {
    printf("%s %u\n", name, g_os_refusal_count() - g_before);
}

#define CASE(name, body) do { begin(); { body; } report(name); } while (0)

int main(void) {
    g_image = calloc(OS_IMAGE_SIZE, 1);
    if (!g_image) return 1;
    uint32_t out;
    uint16_t staged_handle = OS_FS_FIRST_HANDLE;

    /* ---- os_gem_trap ---- */
    CASE("gem_bad_subsystem", wr16(g_image + PROBE_CONTRL, AES_APPL_INIT);
                              os_gem_trap(g_image, PROBE_BAD_SUBSYS, PROBE_PBLK));
    CASE("gem_bad_aes_opcode", wr16(g_image + PROBE_CONTRL, PROBE_BAD_OPCODE);
                               os_gem_trap(g_image, GEM_AES, PROBE_PBLK));
    CASE("gem_bad_vdi_opcode", wr16(g_image + PROBE_CONTRL, PROBE_BAD_OPCODE);
                               os_gem_trap(g_image, GEM_VDI, PROBE_PBLK));
    CASE("gem_served", wr16(g_image + PROBE_CONTRL, AES_APPL_INIT);
                       os_gem_trap(g_image, GEM_AES, PROBE_PBLK));

    /* ---- os_bconstat / os_bconin / os_crawio ---- */
    CASE("bconstat_bad_device", os_bconstat(g_image, OS_BIOS_DEV_CON + 1, &out));
    CASE("bconstat_served", os_bconstat(g_image, OS_BIOS_DEV_CON, &out));
    CASE("bconin_no_key", os_bconin(g_image, OS_BIOS_DEV_CON, &out));
    CASE("bconin_bad_device", wr32(g_image + OS_CON_PENDING, 1);
                              os_bconin(g_image, OS_BIOS_DEV_CON + 1, &out));
    CASE("bconin_served", wr32(g_image + OS_CON_PENDING, 1);
                          os_bconin(g_image, OS_BIOS_DEV_CON, &out));
    /* Crawio never refuses — an idle console is a RESULT for a non-blocking read. */
    CASE("crawio_read_idle", os_crawio(g_image, OS_CRAWIO_READ));
    CASE("crawio_read_key", wr32(g_image + OS_CON_PENDING, 1); os_crawio(g_image, OS_CRAWIO_READ));
    CASE("crawio_write", os_crawio(g_image, 'A'));

    /* ---- os_super ---- */
    CASE("super_unknown_token", os_super(PROBE_BAD_SUPER, &out));
    CASE("super_enter", os_super(OS_SUPER_ENTER, &out));
    CASE("super_inquire", os_super(OS_SUPER_INQUIRE, &out));
    CASE("super_restore", os_super(OS_SUPER_TOKEN, &out));

    /* ---- the file calls ---- */
    CASE("fopen_unstaged", os_fopen(g_image, PROBE_OTHER_NAME));
    CASE("fopen_served", os_fopen(g_image, PROBE_STAGED_NAME));
    /* os_fcreate refuses only THROUGH os_fopen, so this pins that it does not double-count. */
    CASE("fcreate_unstaged", os_fcreate(g_image, PROBE_OTHER_NAME));
    CASE("fcreate_served", os_fcreate(g_image, PROBE_STAGED_NAME));

    CASE("fread_bad_handle", os_fread(g_image, PROBE_BAD_HANDLE, PROBE_XFER_BYTES, PROBE_BUF));
    CASE("fread_closed_slot", wr32(os_fs_slot(g_image, 0) + OS_FS_OFF_OPEN, 0);
                              os_fread(g_image, staged_handle, PROBE_XFER_BYTES, PROBE_BUF));
    CASE("fread_buffer_outside_image",
         os_fread(g_image, staged_handle, PROBE_XFER_BYTES, PROBE_WILD_ADDR));
    CASE("fread_served", os_fread(g_image, staged_handle, PROBE_XFER_BYTES, PROBE_BUF));

    CASE("fwrite_bad_handle", os_fwrite(g_image, PROBE_BAD_HANDLE, PROBE_XFER_BYTES, PROBE_BUF));
    CASE("fwrite_past_capacity",
         os_fwrite(g_image, staged_handle, PROBE_FILE_BYTES + 1, PROBE_BUF));
    CASE("fwrite_buffer_outside_image",
         os_fwrite(g_image, staged_handle, PROBE_XFER_BYTES, PROBE_WILD_ADDR));
    CASE("fwrite_served", os_fwrite(g_image, staged_handle, PROBE_XFER_BYTES, PROBE_BUF));

    CASE("fclose_bad_handle", os_fclose(g_image, PROBE_BAD_HANDLE));
    CASE("fclose_served", os_fclose(g_image, staged_handle));

    free(g_image);
    return 0;
}
