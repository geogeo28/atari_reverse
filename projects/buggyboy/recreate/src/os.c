/* os.c — OS-wrapper reconstructions (GEMDOS/BIOS/XBIOS glue @ various addresses).
 *
 * These thin wrappers push arguments and enter TOS via `trap`. Their effect lives in
 * hardware (video shifter, palette) or TOS state, not in our memory image, so the faithful
 * reconstruction touches nothing observable — the differential test confirms the oracle's
 * trap dispatch returns cleanly (reaches rts, no spurious image write). See os.h for the
 * modeled trap semantics both sides share.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "os.h"

/* xbios_setscreen @ 0x12226 — Setscreen(logbase = physbase = physbase_tbl[0], rez = -1).
 * Screen base + resolution are shifter/TOS state, not our image: no observable effect. */
void g_xbios_setscreen(uint8_t *image) { (void)image; }

/* xbios_setpalette @ 0x12eb0 — Setpalette(A0 = 16-word palette) -> hardware palette regs. */
void g_xbios_setpalette(uint8_t *image, uint32_t palette_ptr) { (void)image; (void)palette_ptr; }

/* set_rez @ 0x120f8 — store the low byte of D0 to a config global, then XBIOS 0x19 reads it
 * to set hardware (no image effect). Only the byte write is observable. */
void g_set_rez(uint8_t *image, uint32_t mode) {
    image[A_setrez_mode] = (uint8_t)mode;
}

/* read_joystick @ 0x12110 — busy-wait the IKBD ACIA's TDRE (transmit-ready) bit, then send the
 * 0x16 joystick-interrogate command. The joystick reply arrives via an interrupt we don't run
 * (input is scripted as an image global instead — see HARNESS.md), and the command write lands
 * on hardware, so there is no image effect. The oracle models the ACIA status as always-ready
 * (shim.c) so the real code's wait loop terminates. */
void g_read_joystick(uint8_t *image) { (void)image; }

/* vsync @ XBIOS 0x25 — wait for the next vertical blank (50 Hz). Pure timing, no image effect, so
 * the oracle models it as a no-op; the Atari PRG overrides it with the real XBIOS trap. Used to pace
 * animations that the original throttles to the vblank (e.g. the leg-start "get ready" flash). */
void g_vsync(void) { }

/* dosound @ XBIOS 0x20 — hand a YM2149 command list to TOS's per-VBL sound engine (the leg-start
 * countdown beeps, the engine idle, crash/collision effects). It writes the chip in hardware, not
 * our image, so it has no image effect: a no-op in the harness, the real XBIOS trap in the PRG.
 *
 * The harness records each call's list pointer in a side-effect ledger (reset before a differential
 * run, then compared against the oracle's Dosound trap stream) so a wrong/missing list — invisible to
 * the image diff — fails a test. That ledger — g_dosound plus its three accessors — is kit-wide and
 * lives in tools/recreate_kit/src/dosound_log.c, which kit.mk links into every candidate. This file
 * only documents the seam; game_main.c's PRG build excludes os.c and the kit sources alike, and
 * supplies its own g_dosound that issues the real trap. */

/* wait_music_off @ update_highscore 0x2406 / 0x25ca — spin until the VBL sound driver clears mzflag
 * (i.e. the current tune has played out). The 50 Hz VBL driver advances the tune off-image, so this
 * has no image effect and can never terminate under the oracle; it is a no-op in the harness and a
 * real busy-wait on the Atari PRG (which overrides it). Lets the game-over / results jingles finish. */
void g_wait_music_off(uint8_t *image) { (void)image; }

/* xbios_setcolor @ name-entry 0x24da — XBIOS Setcolor(index, color): set one hardware palette
 * register (the name-entry color-3 flash). Hardware-only, no image effect, so a no-op in the harness;
 * the Atari PRG overrides it with the real trap. */
void g_xbios_setcolor(uint8_t *image, uint32_t index, uint32_t color) { (void)image; (void)index; (void)color; }

/* poke_color_reg @ game_update mode-6 (0x1183e) — the tunnel palette swap writes one word directly
 * to an ST shifter colour register at 0xffff824c + reg_sel. That address is ~16 MB up (far above the
 * 1 MiB image), so the 68000's store there is dropped by the oracle's bounds check exactly as our PSG/
 * IKBD hardware writes are — hence a no-op here; the Atari PRG overrides it with the real poke. */
void g_poke_color_reg(uint8_t *image, int16_t reg_sel, uint16_t color) { (void)image; (void)reg_sel; (void)color; }

/* console_scancode @ 0x12b24 (init_playfield function-key menu) — GEMDOS Crawio(0xff): a
 * non-blocking raw console poll; the game keeps the scancode byte (swap d0, then & 0xff). The
 * oracle models the console as empty (OS_CRAWIO_RESULT), so no key is ever pending here and the
 * differential test always takes the no-menu path. The Atari PRG overrides this with the real trap. */
uint16_t g_console_scancode(uint8_t *image) { (void)image; return (uint16_t)OS_CRAWIO_RESULT; }

/* console_wait_char @ 0x12b48 — GEMDOS Crawcin (fn 7): a blocking raw read, used only to confirm
 * RETURN after F10. Unreachable under the no-key model (F10 is never seen), so it just returns 0. */
uint16_t g_console_wait_char(uint8_t *image) { (void)image; return 0; }

/* install_handlers @ 0x12124 — Kbdvbase() returns the KBDVBASE vector table; save its pointer and
 * the old mousevec (+0x10) / joyvec (+0x18) vectors (for the restore on exit), then install this
 * game's handlers (the joyvec handler is what read_joystick's reply drives). The oracle returns a
 * fixed in-image KBDVBASE (OS_KBDVBASE) so the reads/writes hit the image. */
#define KBDVBASE_MOUSEVEC 0x10       /* KBDVBASE offset patched with MOUSEVEC_HANDLER */
#define KBDVBASE_JOYVEC   0x18       /* KBDVBASE offset patched with JOYVEC_HANDLER */
#define MOUSEVEC_HANDLER  0x12164    /* installed at KBDVBASE+0x10 */
#define JOYVEC_HANDLER    0x12156    /* installed at KBDVBASE+0x18 */

void g_install_handlers(uint8_t *image) {
    uint32_t kbdvbase = OS_KBDVBASE;                 /* Kbdvbase() result (shared with the shim) */
    wr32(image + A_kbdvbase, kbdvbase);
    wr32(image + A_mousevec_old, be32(image + kbdvbase + KBDVBASE_MOUSEVEC));
    wr32(image + kbdvbase + KBDVBASE_MOUSEVEC, MOUSEVEC_HANDLER);
    wr32(image + A_joyvec_old, be32(image + kbdvbase + KBDVBASE_JOYVEC));
    wr32(image + kbdvbase + KBDVBASE_JOYVEC, JOYVEC_HANDLER);
}



/* gem_aes @ 0x100dc — D1 = &aes_pblk, D0 = 0xC8, trap #2. The AES call's outputs land in the
 * param block's intout array; os_gem_trap models them (see os.h). */
void g_gem_aes(uint8_t *image) { os_gem_trap(image, GEM_AES, A_aes_pblk); }

/* gem_vdi @ 0x100ea — D1 = &vdi_pblk, D0 = 0x73, trap #2. */
void g_gem_vdi(uint8_t *image) { os_gem_trap(image, GEM_VDI, A_vdi_pblk); }

/* _start @ 0x10000 — program entry. Mshrink to release unused memory, then bring GEM up:
 * AES appl_init, AES graf_handle (its physical handle becomes the VDI handle), then
 * VDI v_opnvwk to open the screen workstation — before calling main.
 *
 * Reconstructed up to the `bsr main` at 0x100d4 (the checkpoint): main is the infinite game
 * loop and never returns, so _start is verified there, not at rts. Mshrink has no image effect
 * (os.h). The entry code also clears an AES global-array scratch (0x19a7c..0x19a88) that is
 * already zero at load — a no-op, so it is omitted here. Sets contrl exactly as the original
 * does per call, so the surviving fields (e.g. graf_handle's cell sizes in intout[2..4]) match. */
void g_start(uint8_t *image) {
    uint8_t *contrl = image + A_aesvdi_contrl;   /* contrl[i] at +2*i; contrl[6] at +12 */

    /* AES appl_init: contrl = {10, 0, 1, 0, 0} -> ap_id in intout[0]. */
    wr16(contrl + 0, AES_APPL_INIT);
    wr16(contrl + 2, 0); wr16(contrl + 4, 1); wr16(contrl + 6, 0); wr16(contrl + 8, 0);
    os_gem_trap(image, GEM_AES, A_aes_pblk);

    /* AES graf_handle: contrl = {77, 0, 5, 0, 0} -> handle + font cell sizes in intout[0..4]. */
    wr16(contrl + 0, AES_GRAF_HANDLE);
    wr16(contrl + 2, 0); wr16(contrl + 4, 5); wr16(contrl + 6, 0); wr16(contrl + 8, 0);
    os_gem_trap(image, GEM_AES, A_aes_pblk);

    /* Reuse the returned physical handle (intout[0]) as the VDI workstation handle. */
    uint16_t handle = be16(image + A_vdi_ws_handle);
    wr16(image + A_vdi_handle, handle);

    /* VDI v_opnvwk: contrl[0]=100, [1]=0, [3]=11 (intin count), [6]=handle; leaves contrl[2]=5
     * from graf_handle untouched, as the original does. work_in (intin) = ten 1s then a 2. */
    wr16(contrl + 0, VDI_V_OPNVWK);
    wr16(contrl + 2, 0); wr16(contrl + 6, 11); wr16(contrl + 12, handle);
    for (int i = 0; i < 10; i++) wr16(image + A_vdi_intin + 2 * i, 1);
    wr16(image + A_vdi_intin + 20, 2);
    os_gem_trap(image, GEM_VDI, A_vdi_pblk);
}

/* load_graphics @ 0x12166 — read COURSES.DAT into mem_base, then GRAPHICS.GRA into buf_c+0xc350,
 * then decompress the graphics. Reconstructed up to the `bsr unpack_graphics` at 0x121f2 (the
 * checkpoint): this verifies both file reads land byte-exact; the decompressor is a separate
 * function. Each Fopen bails to rts on a negative handle, exactly as the original does; Fread
 * uses the just-returned handle and Fclose reads it back from the handle global. */
#define COURSES_READ_MAX  0xf660u    /* COURSES.DAT read count (equals its file size) */
#define GRAPHICS_READ_MAX 0x3f500u   /* GRAPHICS.GRA read count (>= file size -> whole file) */

void g_load_graphics(uint8_t *image) {
    int32_t handle = os_fopen(image, A_fname_courses);
    if (handle < 0) return;
    wr16(image + A_gfx_file_handle, (uint16_t)handle);
    os_fread(image, (uint16_t)handle, COURSES_READ_MAX, be32(image + A_mem_base));
    os_fclose(image, be16(image + A_gfx_file_handle));

    handle = os_fopen(image, A_fname_graphics);
    if (handle < 0) return;
    wr16(image + A_gfx_file_handle, (uint16_t)handle);
    os_fread(image, (uint16_t)handle, GRAPHICS_READ_MAX,
             be32(image + A_buf_c) + GFX_LOAD_OFFSET);
    os_fclose(image, be16(image + A_gfx_file_handle));
    /* checkpoint here; the original falls through to unpack_graphics (0x620). */
}

/* main @ 0x10100 — the game driver. Reconstructed up to the checkpoint at 0x10144: Malloc the
 * work block, round it up to mem_base, and lay out the five buffer pointers. main never returns
 * (it enters the infinite game loop after a long init of mostly-separate functions), so this
 * verifies the Malloc + buffer-base setup. Malloc(0x5ee08) returns OS_HEAP_BASE — the first and
 * only Malloc reached before the checkpoint — and the game rounds it up to a 0x100 boundary.
 * The `d0 < 0` (Malloc-failed -> rts) branch is unreachable with the modeled Malloc. */
#define MAIN_MEM_ALIGN  0x100      /* mem_base = (Malloc result + 0x100) & ~0xff */
#define MEM_BUF_AUX_OFF 0x57000    /* the five work buffers, as offsets from mem_base */
#define MEM_BUF_A_OFF   0x1900
#define MEM_BUF_B_OFF   0xf660
#define MEM_BUF_C_OFF   0x1c660

void g_main(uint8_t *image) {
    uint32_t mem_base = (OS_HEAP_BASE + MAIN_MEM_ALIGN) & ~0xffu;
    wr32(image + A_buf_aux, mem_base + MEM_BUF_AUX_OFF);
    wr32(image + A_mem_base, mem_base);
    wr32(image + A_buf_a, mem_base + MEM_BUF_A_OFF);
    wr32(image + A_buf_b, mem_base + MEM_BUF_B_OFF);
    wr32(image + A_buf_c, mem_base + MEM_BUF_C_OFF);
}