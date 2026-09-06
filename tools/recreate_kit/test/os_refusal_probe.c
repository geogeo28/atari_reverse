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
#include "raster.h"

/* The model bounds its copies against OS_IMAGE_SIZE, and OS_FS_TABLE lives near the top of it, so
 * the probe needs a full-size image rather than a small scratch buffer. */
#define PROBE_STAGED_NAME  0x1000u   /* where the staged filename string sits */
#define PROBE_OTHER_NAME   0x1020u   /* a filename the table does not hold */
#define PROBE_BUF          0x2000u   /* an in-image transfer buffer */
#define PROBE_XFER_BYTES   4u        /* bytes moved by the Fread/Fwrite "served" cases */
#define PROBE_FILE_BYTES   8u        /* the staged file's length and reserved capacity */

/* AES parameter block: apb[0] -> contrl, apb[2] -> intin, apb[3] -> intout. */
#define PROBE_PBLK         0x3000u
#define PROBE_CONTRL       0x3100u
#define PROBE_INTOUT       0x3200u
#define PROBE_BAD_OPCODE   0x7fffu   /* in neither the AES nor the VDI modeled set */
#define PROBE_BAD_SUBSYS   0x0001u   /* neither GEM_AES nor GEM_VDI */

/* ...and a VDI one, whose five pointers sit at different indices from the AES's six. */
#define PROBE_VDI_PBLK     0x3400u
#define PROBE_INTIN        0x3500u
#define PROBE_PTSIN        0x3600u
#define PROBE_PTSOUT       0x3700u
/* Two MFDBs and the rasters they describe: a 16x16 four-plane block each, well clear of the
 * modeled screen at OS_SCREEN_BASE. */
#define PROBE_MFDB_SRC     0x3800u
#define PROBE_MFDB_DST     0x3820u
#define PROBE_RASTER_SRC   0x4000u
#define PROBE_RASTER_DST   0x5000u
#define PROBE_RASTER_W     16
#define PROBE_RASTER_H     16
#define PROBE_RASTER_WDW   1
#define PROBE_BAD_LOGIC_OP RASTER_OP_COUNT   /* one past the last op there is */

#define PROBE_EXIT_CODE    2         /* any status; os_pterm records it and never refuses */
#define PROBE_BAD_HANDLE   0x0100u   /* far outside OS_FS_FIRST_HANDLE .. +OS_FS_SLOTS */
#define PROBE_BAD_SUPER    0x0decadeu /* a "stack pointer" os_super never handed out */
#define PROBE_WILD_ADDR    0xfffffff0u /* a buffer address outside the image */

static uint8_t *g_image;
static uint32_t g_before;

/* One 16x16 four-plane MFDB at `mfdb`, describing the raster at `addr`. `stand` selects the VDI's
 * device-independent format, which the model refuses. */
static void mfdb_write(uint32_t mfdb, uint32_t addr, uint16_t stand) {
    wr32(g_image + mfdb + MFDB_ADDR, addr);
    wr16(g_image + mfdb + MFDB_W, PROBE_RASTER_W);
    wr16(g_image + mfdb + MFDB_H, PROBE_RASTER_H);
    wr16(g_image + mfdb + MFDB_WDWIDTH, PROBE_RASTER_WDW);
    wr16(g_image + mfdb + MFDB_STAND, stand);
    wr16(g_image + mfdb + MFDB_NPLANES, OS_SCREEN_PLANES);
}

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

    wr32(g_image + PROBE_PBLK + AES_PB_CONTRL * 4, PROBE_CONTRL);
    wr32(g_image + PROBE_PBLK + AES_PB_INTIN * 4, PROBE_INTIN);
    wr32(g_image + PROBE_PBLK + AES_PB_INTOUT * 4, PROBE_INTOUT);

    wr32(g_image + PROBE_VDI_PBLK + VDI_PB_CONTRL * 4, PROBE_CONTRL);
    wr32(g_image + PROBE_VDI_PBLK + VDI_PB_INTIN * 4, PROBE_INTIN);
    wr32(g_image + PROBE_VDI_PBLK + VDI_PB_PTSIN * 4, PROBE_PTSIN);
    wr32(g_image + PROBE_VDI_PBLK + VDI_PB_INTOUT * 4, PROBE_INTOUT);
    wr32(g_image + PROBE_VDI_PBLK + VDI_PB_PTSOUT * 4, PROBE_PTSOUT);

    mfdb_write(PROBE_MFDB_SRC, PROBE_RASTER_SRC, 0);
    mfdb_write(PROBE_MFDB_DST, PROBE_RASTER_DST, 0);
}

/* contrl[index] = value, in the block both parameter blocks above point at. */
static void contrl(int index, uint16_t value) {
    wr16(g_image + PROBE_CONTRL + (uint32_t)index * 2, value);
}

/* Set up a vro_cpyfm call: logic op, and the two MFDB addresses split across contrl[7..10]. */
static void cpyfm(uint16_t logic_op) {
    contrl(VDI_CONTRL_OPCODE, VDI_VRO_CPYFM);
    wr16(g_image + PROBE_INTIN, logic_op);
    contrl(VDI_CONTRL_SRC_MFDB, (uint16_t)(PROBE_MFDB_SRC >> 16));
    contrl(VDI_CONTRL_SRC_MFDB + 1, (uint16_t)PROBE_MFDB_SRC);
    contrl(VDI_CONTRL_DST_MFDB, (uint16_t)(PROBE_MFDB_DST >> 16));
    contrl(VDI_CONTRL_DST_MFDB + 1, (uint16_t)PROBE_MFDB_DST);
    for (int i = 0; i < 6; i++) wr16(g_image + PROBE_PTSIN + (uint32_t)i * 2, 0);
}

/* Set up a vr_recfl over a small on-screen rectangle under the given fill interior. */
#define PROBE_RECFL_X1 4
#define PROBE_RECFL_Y1 4
#define PROBE_RECFL_X2 12
#define PROBE_RECFL_Y2 8

static void recfl(uint16_t interior) {
    contrl(VDI_CONTRL_OPCODE, VDI_VR_RECFL);
    wr16(g_image + OS_VDI_STATE + OS_VDI_OFF_FILL_INTERIOR, interior);
    wr16(g_image + PROBE_PTSIN, PROBE_RECFL_X1);
    wr16(g_image + PROBE_PTSIN + 2, PROBE_RECFL_Y1);
    wr16(g_image + PROBE_PTSIN + 4, PROBE_RECFL_X2);
    wr16(g_image + PROBE_PTSIN + 6, PROBE_RECFL_Y2);
}

/* Each case runs on a freshly reset image so one case's image effect cannot steer the next — and on
 * a freshly reset EVENT LEDGER, because that ledger now carries state of its own: `g_os_event`
 * latches a recorded Pterm and refuses every later append (src/os_log.c), so a case that terminates
 * would otherwise make every case after it refuse. */
static void begin(void) {
    image_reset();
    g_os_event_reset();
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
    CASE("gem_pblock_outside_image", wr16(g_image + PROBE_CONTRL, AES_APPL_INIT);
                                     os_gem_trap(g_image, GEM_AES, PROBE_WILD_ADDR));
    CASE("aes_appl_exit_served", wr16(g_image + PROBE_CONTRL, AES_APPL_EXIT);
                                 os_aes(g_image, PROBE_PBLK));
    CASE("aes_graf_mouse_served", wr16(g_image + PROBE_CONTRL, AES_GRAF_MOUSE);
                                  wr16(g_image + PROBE_INTIN, AES_M_OFF);
                                  os_aes(g_image, PROBE_PBLK));

    /* ---- the VDI: every refusal the raster model can reach ---- */
    CASE("vdi_served", contrl(VDI_CONTRL_OPCODE, VDI_VSF_COLOR);
                       wr16(g_image + PROBE_INTIN, 5);
                       os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_cpyfm_served", cpyfm(RASTER_OP_S_ONLY); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_cpyfm_bad_logic_op", cpyfm(PROBE_BAD_LOGIC_OP); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_cpyfm_standard_format", cpyfm(RASTER_OP_S_ONLY);
                                      mfdb_write(PROBE_MFDB_SRC, PROBE_RASTER_SRC,
                                                 MFDB_STANDARD_FORMAT);
                                      os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_cpyfm_raster_outside_image", cpyfm(RASTER_OP_S_ONLY);
                                           mfdb_write(PROBE_MFDB_SRC, PROBE_WILD_ADDR, 0);
                                           os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_cpyfm_null_mfdb", cpyfm(RASTER_OP_S_ONLY);
                                contrl(VDI_CONTRL_DST_MFDB, 0);
                                contrl(VDI_CONTRL_DST_MFDB + 1, 0);
                                os_vdi(g_image, PROBE_VDI_PBLK));
    /* vr_recfl's FILL INTERIOR. Hollow and solid are the two the model paints; pattern, hatch and
     * user-defined each need a pattern table it does not have, and filling them solid would draw
     * pixels no real machine draws — so the whole call is refused. */
    CASE("vdi_recfl_hollow_served", recfl(VDI_FILL_HOLLOW); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_recfl_solid_served", recfl(VDI_FILL_SOLID); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_recfl_pattern_interior", recfl(VDI_FILL_PATTERN); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_recfl_hatch_interior", recfl(VDI_FILL_HATCH); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_recfl_user_interior", recfl(VDI_FILL_USER); os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_clrwk_served", contrl(VDI_CONTRL_OPCODE, VDI_V_CLRWK);
                             os_vdi(g_image, PROBE_VDI_PBLK));
    CASE("vdi_clrwk_screen_outside_image", contrl(VDI_CONTRL_OPCODE, VDI_V_CLRWK);
                                           wr32(g_image + OS_VDI_STATE + OS_VDI_OFF_SCREEN,
                                                PROBE_WILD_ADDR);
                                           os_vdi(g_image, PROBE_VDI_PBLK));

    /* ---- os_bconstat / os_bconin / os_crawio ---- */
    CASE("bconstat_bad_device", os_bconstat(g_image, OS_BIOS_DEV_CON + 1, &out));
    CASE("bconstat_served", os_bconstat(g_image, OS_BIOS_DEV_CON, &out));
    CASE("bconin_no_key", os_bconin(g_image, OS_BIOS_DEV_CON, &out));
    CASE("bconin_bad_device", wr32(g_image + OS_CON_PENDING, 1);
                              os_bconin(g_image, OS_BIOS_DEV_CON + 1, &out));
    CASE("bconin_served", wr32(g_image + OS_CON_PENDING, 1);
                          os_bconin(g_image, OS_BIOS_DEV_CON, &out));
    /* GEMDOS's console door onto the SAME staged key. Cconis only looks, so it never refuses;
     * the two blocking reads refuse an idle console, because the real calls would WAIT. */
    CASE("cconis_no_key", os_cconis(g_image));
    CASE("cconis_key", wr32(g_image + OS_CON_PENDING, 1); os_cconis(g_image));
    CASE("crawcin_no_key", os_crawcin(g_image, &out));
    CASE("crawcin_served", wr32(g_image + OS_CON_PENDING, 1); os_crawcin(g_image, &out));
    CASE("cnecin_no_key", os_cnecin(g_image, &out));
    CASE("cnecin_served", wr32(g_image + OS_CON_PENDING, 1); os_cnecin(g_image, &out));
    /* Crawio never refuses — an idle console is a RESULT for a non-blocking read. */
    CASE("crawio_read_idle", os_crawio(g_image, OS_CRAWIO_READ));
    CASE("crawio_read_key", wr32(g_image + OS_CON_PENDING, 1); os_crawio(g_image, OS_CRAWIO_READ));
    CASE("crawio_write", os_crawio(g_image, 'A'));

    /* ---- the OTHER character devices, and the process ending ----
     * Handing a byte to a device always succeeds in this model, and so does ending; the serial line
     * is the one that cannot be READ, because no case can stage a byte for it to return. */
    CASE("cauxout", os_cauxout('A'));
    CASE("cprnout", os_cprnout('A'));
    CASE("pterm", os_pterm(PROBE_EXIT_CODE));
    CASE("cauxin", os_cauxin());
    /* ...and `os_pterm`'s CALLER contract, which is the one contract in os.h that the callee cannot
     * keep for itself: the oracle's run ends at the trap, so a second event on this side can only be
     * a reconstruction that went on running past the termination. */
    CASE("event_after_pterm", os_pterm(PROBE_EXIT_CODE); os_cconout('A'));

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

    CASE("fseek_bad_handle", os_fseek(g_image, 0, PROBE_BAD_HANDLE, OS_FSEEK_FROM_START));
    CASE("fseek_closed_slot", wr32(os_fs_slot(g_image, 0) + OS_FS_OFF_OPEN, 0);
                              os_fseek(g_image, 0, staged_handle, OS_FSEEK_FROM_START));
    CASE("fseek_bad_mode", os_fseek(g_image, 0, staged_handle, OS_FSEEK_FROM_END + 1));
    CASE("fseek_before_start", os_fseek(g_image, (uint32_t)-1, staged_handle, OS_FSEEK_FROM_START));
    CASE("fseek_past_capacity",
         os_fseek(g_image, PROBE_FILE_BYTES + 1, staged_handle, OS_FSEEK_FROM_START));
    CASE("fseek_from_start", os_fseek(g_image, PROBE_XFER_BYTES, staged_handle,
                                      OS_FSEEK_FROM_START));
    CASE("fseek_from_current", os_fseek(g_image, PROBE_XFER_BYTES, staged_handle,
                                        OS_FSEEK_FROM_CURRENT));
    CASE("fseek_from_end", os_fseek(g_image, 0, staged_handle, OS_FSEEK_FROM_END));

    CASE("fclose_bad_handle", os_fclose(g_image, PROBE_BAD_HANDLE));
    CASE("fclose_served", os_fclose(g_image, staged_handle));

    /* Fdelete answers BOTH ways rather than refusing either — deleting a file the table does not
     * hold is a legal outcome with a GEMDOS error code of its own (os.h says why this one is an
     * answer where os_fopen's identical "no such name" is a refusal). What the delete leaves behind
     * IS a refusal, and the third case is the one that says so: the name is gone, so re-opening it
     * refuses exactly as an unstaged name always did. */
    CASE("fdelete_unstaged", os_fdelete(g_image, PROBE_OTHER_NAME));
    CASE("fdelete_served", os_fdelete(g_image, PROBE_STAGED_NAME));
    CASE("fdelete_then_fopen", os_fdelete(g_image, PROBE_STAGED_NAME);
                               os_fopen(g_image, PROBE_STAGED_NAME));

    free(g_image);
    return 0;
}
