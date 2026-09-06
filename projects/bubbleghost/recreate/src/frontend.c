/* frontend.c — Bubble Ghost's GEM binding, its boot-time setup, the sprite protocol and the file
 * loaders. What each address and record means is `include/frontend.h`.
 *
 * THE SHAPE OF THIS FILE. Almost everything here is a wrapper: the game reaches the VDI and the AES
 * through the standard DRI binding, in which each entry point copies its C arguments into the
 * parameter block's `contrl`/`intin`/`ptsin` arrays and jumps to the one routine that traps. So the
 * routines below are mostly four stores and a call, and the interesting part is which four.
 *
 * WHAT REPLACES THE TRAP. `vdi_call` @ 0x168d4 and `gem_aes` @ 0x149b6 park the caller's A1/A2 in
 * the trampoline's two save slots — as the original does, because TOS may clobber them and the
 * Alcyon compiler assumes it does not — and then hand the SAME parameter block, at the SAME address
 * in the SAME image, to the kit's GEM model (`os_vdi` / `os_aes`). The oracle's `trap #2` reaches
 * that model through `shim.c`; this reaches it directly. One implementation, one block: what the
 * VDI draws is image state on both sides, and the byte diff covers it (TRAP_MODEL.md, phases 11-13).
 *
 * TWO THINGS EVERY ROUTINE HERE TAKES THAT ITS C PROTOTYPE DOES NOT DECLARE, both of them
 * `docs/agent-playbook.md` §5's "a parameter":
 *   * the CALLER'S A1/A2, because the trampoline files whatever the register file holds and nothing
 *     in the routine computes it;
 *   * for `init_gem_and_screens` and `load_hiscores`, the address of their own STACK FRAME, because
 *     both hand a callee the address of a local and the C reconstruction has no machine stack. The
 *     frame lies in the band the differential drops, so the case hands both sides the same address.
 */
#include "machine.h"

/* THE ONE INCLUDE ORDER IN THIS PROJECT THAT NEEDS EXPLAINING. `include/blit.h` names the MFDB
 * fields as the GAME's own record (the block `build_sprite_bank` fills in) and the kit's `os.h`
 * names them as the MODEL's (the block `vro_cpyfm` reads). This is the only translation unit that
 * includes both, so it drops ALL SIX of the game's spellings and uses the model's — the header that
 * also defines what reading the block means. Dropping only the two that collide by name would leave
 * `MFDB_WIDTH` and its three siblings reachable here, where a line meaning the model's record could
 * silently be written against the game's. `src/blit.c` includes neither `os.h` nor this file and
 * keeps its own set.
 *
 * THE TWO SETS ARE PINNED EQUAL TO EACH OTHER RATHER THAN EACH TO A LITERAL, and not left to a
 * redefinition warning: only two of the six fields are spelt the same in both headers, so a drift in
 * the other four (`MFDB_WIDTH`/`HEIGHT`/`STANDARD`/`PLANES` against `MFDB_W`/`H`/`STAND`/`NPLANES`)
 * could never warn at all — and two assertions against literals would BOTH have to be edited to move
 * a field, which is a pin nobody would notice going slack. The game's six values are captured under
 * private names first, so the assertion below compares one header with the other. */
#include "frontend.h"   /* ...which includes blit.h: the tile geometry and the two screens */
enum {
    GAME_MFDB_ADDR = MFDB_ADDR, GAME_MFDB_WIDTH = MFDB_WIDTH, GAME_MFDB_HEIGHT = MFDB_HEIGHT,
    GAME_MFDB_WDWIDTH = MFDB_WDWIDTH, GAME_MFDB_STANDARD = MFDB_STANDARD,
    GAME_MFDB_PLANES = MFDB_PLANES,
};
#undef MFDB_ADDR
#undef MFDB_WIDTH
#undef MFDB_HEIGHT
#undef MFDB_WDWIDTH
#undef MFDB_STANDARD
#undef MFDB_PLANES

#include "os.h"
_Static_assert(GAME_MFDB_ADDR == MFDB_ADDR && GAME_MFDB_WIDTH == MFDB_W
                   && GAME_MFDB_HEIGHT == MFDB_H && GAME_MFDB_WDWIDTH == MFDB_WDWIDTH
                   && GAME_MFDB_STANDARD == MFDB_STAND && GAME_MFDB_PLANES == MFDB_NPLANES,
               "include/blit.h's MFDB record and the kit os.h's have drifted apart");

#include "common.h"     /* LONG_BYTES and `longword_slot`, the stride of every pointer table here */
#include "gameplay.h"   /* the ghost and bubble the sprite protocol draws */

/* One word of a GEM array named by its index, which is how every `contrl`/`intin`/`ptsin` slot in
 * this file is spelt. The 68000 reaches them as `lea array,a0 / adda.w #index*2,a0`. */
#define GEM_ARRAY_WORD_BYTES 2u

static uint32_t gem_word(uint32_t array, unsigned index) {
    return array + index * GEM_ARRAY_WORD_BYTES;
}

static uint32_t vdi_pblock_slot(unsigned index) {
    return A_vdi_pblock + index * LONG_BYTES;
}

/* The GEM trampolines park only the two ADDRESS registers. Unlike `include/clib.h`'s GEMDOS/XBIOS
 * pair they do not pop and re-push their own return address — the selector travels in D0 rather
 * than on the stack — so `A_trap_saved_ret` is untouched by anything in this file. */
static void gem_trap_save_registers(uint8_t *image, CallerAddressRegisters saved) {
    wr32(image + A_trap_saved_a1, saved.a1);
    wr32(image + A_trap_saved_a2, saved.a2);
}

/* ================================================================================================
 * The VDI binding
 * ============================================================================================= */

/* vdi_call @ 0x168d4 — the whole VDI trap. Every entry point below fills `contrl` and jumps here.
 * The `contrl` pointer is re-filed on EVERY call rather than once at start-up, which is why a run
 * entered below `v_opnvwk` still reaches the right array. */
void vdi_call(uint8_t *image, CallerAddressRegisters saved) {
    gem_trap_save_registers(image, saved);
    wr32(image + vdi_pblock_slot(VDI_PB_CONTRL), A_vdi_contrl);
    os_vdi(image, A_vdi_pblock);
}

/* The tail every entry point shares: name the opcode, say how many ptsin PAIRS and intin entries
 * are being handed over, file the workstation handle, trap. The four stores are in the order the
 * original makes them, which is the order they appear in every one of the twelve routines. */
static void vdi_trap(uint8_t *image, uint16_t opcode, uint16_t ptsin_pairs, uint16_t intin_entries,
                     int16_t handle, CallerAddressRegisters saved) {
    wr16(image + gem_word(A_vdi_contrl, VDI_CONTRL_OPCODE), opcode);
    wr16(image + gem_word(A_vdi_contrl, VDI_CONTRL_PTSIN_N), ptsin_pairs);
    wr16(image + gem_word(A_vdi_contrl, VDI_CONTRL_INTIN_N), intin_entries);
    wr16(image + gem_word(A_vdi_contrl, VDI_CONTRL_HANDLE), (uint16_t)handle);
    vdi_call(image, saved);
}

/* An MFDB address arrives in `contrl` as two words, high half first. The original splits it with
 * `asr.l #8` twice and a `move.w`, and a `move.w` keeps the low word either way — so the shift's
 * sign fill is dropped before it is stored and a logical shift is the same sixteen bits. */
static void vdi_set_mfdb(uint8_t *image, unsigned contrl_index, uint32_t mfdb) {
    wr16(image + gem_word(A_vdi_contrl, contrl_index), (uint16_t)(mfdb >> 16));
    wr16(image + gem_word(A_vdi_contrl, contrl_index + 1), (uint16_t)(mfdb & 0xffffu));
}

/* vdi_set_src_mfdb @ 0x16890 / vdi_set_dst_mfdb @ 0x168b2 — the same four instructions over the two
 * MFDB slots of `vro_cpyfm`. Both are separate functions in the original and both are called. */
void vdi_set_src_mfdb(uint8_t *image, uint32_t mfdb) {
    vdi_set_mfdb(image, VDI_CONTRL_SRC_MFDB, mfdb);
}

void vdi_set_dst_mfdb(uint8_t *image, uint32_t mfdb) {
    vdi_set_mfdb(image, VDI_CONTRL_DST_MFDB, mfdb);
}

/* vst_height @ 0x168fc — VDI 12. One ptsin pair whose FIRST word is cleared and whose second is the
 * requested height, and four ptsout answers copied out through the caller's four pointers. The game
 * asks for height 6 (menu, hall of fame, save banner) and 4 (the HUD). */
void vst_height(uint8_t *image, int16_t handle, int16_t height, uint32_t char_w, uint32_t char_h,
                uint32_t cell_w, uint32_t cell_h, CallerAddressRegisters saved) {
    wr16(image + gem_word(A_vdi_ptsin, VDI_PTSIN_X), 0);
    wr16(image + gem_word(A_vdi_ptsin, VDI_PTSIN_Y), (uint16_t)height);
    vdi_trap(image, VDI_VST_HEIGHT, 1, 0, handle, saved);
    wr16(image + char_w, be16(image + gem_word(A_vdi_ptsout, VDI_HEIGHT_CHAR_W)));
    wr16(image + char_h, be16(image + gem_word(A_vdi_ptsout, VDI_HEIGHT_CHAR_H)));
    wr16(image + cell_w, be16(image + gem_word(A_vdi_ptsout, VDI_HEIGHT_CELL_W)));
    wr16(image + cell_h, be16(image + gem_word(A_vdi_ptsout, VDI_HEIGHT_CELL_H)));
}

/* The shape `vst_color` @ 0x16948 and `vsf_color` @ 0x16974 share exactly: one intin entry in, one
 * intout answer back. Text colours seen are 1, 5 and 13; the only fill colours are 11 and 0. */
static int16_t vdi_set_colour(uint8_t *image, uint16_t opcode, int16_t handle, int16_t index,
                              CallerAddressRegisters saved) {
    wr16(image + gem_word(A_vdi_intin, 0), (uint16_t)index);
    vdi_trap(image, opcode, 0, 1, handle, saved);
    return (int16_t)be16(image + gem_word(A_vdi_intout, 0));
}

int16_t vst_color(uint8_t *image, int16_t handle, int16_t index, CallerAddressRegisters saved) {
    return vdi_set_colour(image, VDI_VST_COLOR, handle, index, saved);
}

int16_t vsf_color(uint8_t *image, int16_t handle, int16_t index, CallerAddressRegisters saved) {
    return vdi_set_colour(image, VDI_VSF_COLOR, handle, index, saved);
}

/* v_opnvwk @ 0x169a0 — VDI 100. The one call that LENDS the VDI three of the caller's own arrays:
 * `work_in` becomes intin for the duration, and `work_out` becomes both intout and — 45 words on —
 * ptsout. All four library arrays are restored afterwards, `ptsin` included, which is the only
 * place in the program that ever writes that slot at start-up.
 *
 * THE HANDLE IT PASSES IN IS WHATEVER `*handle_out` ALREADY HOLDS, and its only caller hands it the
 * BSS zero: `init_gem_and_screens` throws `graf_handle`'s answer away. TOS tolerates that and so
 * does the model, which reads `contrl[6]` for nothing but its own reply. */
void v_opnvwk(uint8_t *image, uint32_t work_in, uint32_t handle_out, uint32_t work_out,
              CallerAddressRegisters saved) {
    wr32(image + vdi_pblock_slot(VDI_PB_INTIN), work_in);
    wr32(image + vdi_pblock_slot(VDI_PB_INTOUT), work_out);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSOUT),
         addr_add(work_out, VDI_WORK_OUT_PTSOUT_OFFSET));
    vdi_trap(image, VDI_V_OPNVWK, 0, V_OPNVWK_WORK_IN_WORDS,
             (int16_t)be16(image + handle_out), saved);
    wr16(image + handle_out, be16(image + gem_word(A_vdi_contrl, VDI_CONTRL_HANDLE)));

    wr32(image + vdi_pblock_slot(VDI_PB_INTIN), A_vdi_intin);
    wr32(image + vdi_pblock_slot(VDI_PB_INTOUT), A_vdi_intout);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSOUT), A_vdi_ptsout);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSIN), A_vdi_ptsin);
}

/* v_clrwk @ 0x16a06 — VDI 3, no arrays at all. `game_top_loop` calls it once, before the first
 * picture goes up. */
void v_clrwk(uint8_t *image, int16_t handle, CallerAddressRegisters saved) {
    vdi_trap(image, VDI_V_CLRWK, 0, 0, handle, saved);
}

/* vq_mouse @ 0x16a26 — VDI 124. The button mask comes back in intout[0] and the position in the
 * first ptsout pair. Every attract loop polls this and bails out when the mask reads 1. */
void vq_mouse(uint8_t *image, int16_t handle, uint32_t buttons_out, uint32_t x_out, uint32_t y_out,
              CallerAddressRegisters saved) {
    vdi_trap(image, VDI_VQ_MOUSE, 0, 0, handle, saved);
    wr16(image + buttons_out, be16(image + gem_word(A_vdi_intout, 0)));
    wr16(image + x_out, be16(image + gem_word(A_vdi_ptsout, VDI_MOUSE_X)));
    wr16(image + y_out, be16(image + gem_word(A_vdi_ptsout, VDI_MOUSE_Y)));
}

/* vq_key_s @ 0x16a5e — VDI 128, the shift/control/alt bitmap in intout[0]. One caller: the blow
 * gate inside `game_frame_update`. */
void vq_key_s(uint8_t *image, int16_t handle, uint32_t state_out, CallerAddressRegisters saved) {
    vdi_trap(image, VDI_VQ_KEY_S, 0, 0, handle, saved);
    wr16(image + state_out, be16(image + gem_word(A_vdi_intout, 0)));
}

/* v_gtext @ 0x16a86 — VDI 8, and every piece of text the game draws goes through it.
 *
 * The string is widened byte by byte into `intin` INCLUDING its terminator — the loop stores first
 * and tests the stored word — and the length reported in `contrl[3]` is therefore one less than the
 * number of words written. The index into `intin` is added with `adda.w`, so a string long enough
 * to make `index * 2` overflow a signed word wraps rather than running on; nothing the game draws
 * comes near that, and the arithmetic is transcribed rather than simplified. */
void v_gtext(uint8_t *image, int16_t handle, int16_t x, int16_t y, uint32_t text,
             CallerAddressRegisters saved) {
    wr16(image + gem_word(A_vdi_ptsin, VDI_PTSIN_X), (uint16_t)x);
    wr16(image + gem_word(A_vdi_ptsin, VDI_PTSIN_Y), (uint16_t)y);

    uint32_t cursor = text;
    uint16_t written = 0;
    uint16_t character;
    do {
        character = image[cursor];
        cursor = addr_add(cursor, 1);
        wr16(image + addr_add(A_vdi_intin,
                              sign_ext16((uint32_t)(written * GEM_ARRAY_WORD_BYTES))),
             character);
        written++;
    } while (character != 0);

    vdi_trap(image, VDI_V_GTEXT, 1, (uint16_t)(written - 1), handle, saved);
}

/* vr_recfl @ 0x16ae2 — VDI 114. It LENDS the VDI the caller's own four-word rectangle as `ptsin`
 * for the duration of the call and puts the library's array back afterwards. Only the bonus bar
 * calls it. */
void vr_recfl(uint8_t *image, int16_t handle, uint32_t pxy, CallerAddressRegisters saved) {
    wr32(image + vdi_pblock_slot(VDI_PB_PTSIN), pxy);
    vdi_trap(image, VDI_VR_RECFL, 2, 0, handle, saved);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSIN), A_vdi_ptsin);
}

/* vro_cpyfm @ 0x16b12 — VDI 109, the raster copy this game blits every 32x32 cell with. Four ptsin
 * pairs (the source rectangle then the destination corner), one intin entry (the logic operation),
 * and the two MFDB addresses split across `contrl[7..10]`. Like `vr_recfl` it lends the VDI the
 * caller's rectangle and restores the library's array. */
void vro_cpyfm(uint8_t *image, int16_t handle, int16_t mode, uint32_t pxy, uint32_t src_mfdb,
               uint32_t dst_mfdb, CallerAddressRegisters saved) {
    wr16(image + gem_word(A_vdi_intin, 0), (uint16_t)mode);
    vdi_set_src_mfdb(image, src_mfdb);
    vdi_set_dst_mfdb(image, dst_mfdb);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSIN), pxy);
    vdi_trap(image, VDI_VRO_CPYFM, 4, 1, handle, saved);
    wr32(image + vdi_pblock_slot(VDI_PB_PTSIN), A_vdi_ptsin);
}

/* ================================================================================================
 * The AES binding
 * ============================================================================================= */

/* gem_aes @ 0x149b6 — the AES trap. Unlike `vdi_call` it takes the parameter block as an argument,
 * because `aes_crysif` pushes the pointer the library keeps rather than a fixed address. */
void gem_aes(uint8_t *image, uint32_t pblock, CallerAddressRegisters saved) {
    gem_trap_save_registers(image, saved);
    os_aes(image, pblock);
}

/* aes_crysif @ 0x14b2e — the whole AES binding. The opcode goes in `control[0]`; the three counts
 * that follow it are a table lookup, not something the caller says, and the table entries are
 * SIGNED bytes widened to words (`move.b` then `ext.w`).
 *
 * The table is indexed with `adda.w`, so an opcode far enough below 10 or above the table's end
 * reaches a wrapped offset rather than a linear one — transcribed, though every call site in the
 * program passes 10, 77 or 78. */
int16_t aes_crysif(uint8_t *image, int16_t opcode, CallerAddressRegisters saved) {
    wr16(image + gem_word(A_aes_control, AES_CONTROL_OPCODE), (uint16_t)opcode);

    uint32_t counts = addr_add(AES_CONTROL_TABLE,
                               sign_ext16((uint32_t)((opcode - (int16_t)AES_TABLE_FIRST_OPCODE)
                                                     * (int32_t)AES_TABLE_STRIDE)));
    for (uint16_t slot = AES_CONTROL_FIRST_COUNT; slot < AES_CONTROL_COUNT_SLOTS; slot++) {
        uint16_t count = (uint16_t)sign_ext8(image[counts]);
        counts = addr_add(counts, 1);
        wr16(image + addr_add(A_aes_control,
                              sign_ext16((uint32_t)(slot * GEM_ARRAY_WORD_BYTES))),
             count);
    }

    gem_aes(image, be32(image + A_aes_pblock), saved);
    return (int16_t)be16(image + gem_word(A_aes_int_out, 0));
}

/* The six parameter-block slots `appl_init` points at the library's six arrays, plus the block
 * pointer `gem_aes` then traps on. Written out once rather than in a loop because the six arrays
 * are six separate globals in six separate places, which is what the `lea`s say. */
static void aes_bind_parameter_block(uint8_t *image) {
    wr32(image + A_aes_p_control, A_aes_control);
    wr32(image + A_aes_p_global, A_aes_global);
    wr32(image + A_aes_p_int_in, A_aes_int_in);
    wr32(image + A_aes_p_int_out, A_aes_int_out);
    wr32(image + A_aes_p_addr_in, A_aes_addr_in);
    wr32(image + A_aes_p_addr_out, A_aes_addr_out);
    wr32(image + A_aes_pblock, A_aes_p_control);
}

/* appl_init @ 0x14b94 — bind the parameter block, register with the AES, keep the application id. */
int16_t appl_init(uint8_t *image, CallerAddressRegisters saved) {
    aes_bind_parameter_block(image);
    aes_crysif(image, AES_APPL_INIT, saved);
    wr16(image + A_aes_ap_id, be16(image + gem_word(A_aes_int_out, 0)));
    return (int16_t)be16(image + A_aes_ap_id);
}

/* graf_handle @ 0x14be8 — the physical workstation handle in int_out[0] and the four font cell
 * sizes behind it. Its one caller passes the SAME scratch word for all four out-parameters and
 * discards the return, so what the game keeps of this call is nothing at all. */
int16_t graf_handle(uint8_t *image, uint32_t char_w, uint32_t char_h, uint32_t cell_w,
                    uint32_t cell_h, CallerAddressRegisters saved) {
    aes_crysif(image, AES_GRAF_HANDLE, saved);
    wr16(image + char_w, be16(image + gem_word(A_aes_int_out, AES_HANDLE_CHAR_W)));
    wr16(image + char_h, be16(image + gem_word(A_aes_int_out, AES_HANDLE_CHAR_H)));
    wr16(image + cell_w, be16(image + gem_word(A_aes_int_out, AES_HANDLE_CELL_W)));
    wr16(image + cell_h, be16(image + gem_word(A_aes_int_out, AES_HANDLE_CELL_H)));
    return (int16_t)be16(image + gem_word(A_aes_int_out, 0));
}

/* graf_mouse @ 0x14c1e — hide or show the GEM pointer. The AES sees the mode in int_in[0] and a
 * mouse-form pointer in addr_in[0]; both of the game's call sites push only the mode word, so the
 * long this reads as `mform` is really the caller's own return address. It is an argument here for
 * that reason, and the AES ignores it for M_OFF and M_ON. */
void graf_mouse(uint8_t *image, int16_t mode, uint32_t mform, CallerAddressRegisters saved) {
    wr16(image + gem_word(A_aes_int_in, 0), (uint16_t)mode);
    wr32(image + A_aes_addr_in, mform);
    aes_crysif(image, AES_GRAF_MOUSE, saved);
}

/* ================================================================================================
 * Boot-time setup
 * ============================================================================================= */

/* One XBIOS call made straight through the trampoline. The game has no XBIOS binding functions: it
 * pushes the selector and any arguments and `jsr`s `xbios_trap` @ 0x15e3c, so what a reconstruction
 * reproduces is the trampoline's three save slots plus what the model answers. A selector this
 * subsystem does not make refuses loudly rather than returning a plausible zero.
 *
 * EACH CALL GETS ITS OWN WRAPPER BELOW, and every wrapper names every argument the original pushes
 * even though the model reads none of them. All four write the shifter or report a machine fact and
 * so have no image effect at all (TRAP_MODEL.md, "the video and colour calls are modeled as
 * no-ops"), which means a wrong palette, a wrong screen base or a wrong resolution is invisible to
 * the differential and shows only on target (`docs/on-target-execution.md`). Dropping an argument
 * from the signature is how it would stop being part of the routine at all, and an on-target build
 * — whose trampoline really pushes them — is where that would surface as a crash rather than as a
 * diff. So they are carried and discarded here, once, rather than never written down. */
static uint32_t xbios_trap_call(uint8_t *image, uint16_t selector, CallerAddressRegisters saved,
                                uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    switch (selector) {
    case XBIOS_LOGBASE:    return OS_SCREEN_BASE;
    case XBIOS_GETREZ:     return XBIOS_GETREZ_LOW_RES;
    case XBIOS_SETSCREEN:  return 0;
    case XBIOS_SETPALETTE: return 0;
    default:               return (uint32_t)os_refused(0);
    }
}

/* Getrez() and Logbase() take no argument at all. */
static uint32_t xbios_getrez(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc) {
    return xbios_trap_call(image, XBIOS_GETREZ, saved, return_pc);
}

static uint32_t xbios_logbase(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc) {
    return xbios_trap_call(image, XBIOS_LOGBASE, saved, return_pc);
}

/* Setscreen(log_base, phys_base, resolution) — THREE arguments, and the game passes all three at
 * both of its call sites (`save_hiscores` moves the logical base onto the visible screen and back).
 * A resolution of -1 would mean "leave it"; this game always passes 0. */
static void xbios_setscreen(uint8_t *image, uint32_t log_base, uint32_t phys_base,
                            int16_t resolution, CallerAddressRegisters saved, uint32_t return_pc) {
    (void)log_base;
    (void)phys_base;
    (void)resolution;
    xbios_trap_call(image, XBIOS_SETSCREEN, saved, return_pc);
}

/* Setpalette(palette) — sixteen words read off the tail of a picture file. */
static void xbios_setpalette(uint8_t *image, uint32_t palette, CallerAddressRegisters saved,
                             uint32_t return_pc) {
    (void)palette;
    xbios_trap_call(image, XBIOS_SETPALETTE, saved, return_pc);
}

/* ...and GEMDOS `Super`, through the other trampoline. The value the model hands back for `Super(0)`
 * is a COOKIE rather than a stack pointer, and this routine never inspects it — it only passes it
 * back to leave supervisor mode, which is what makes the cookie sound (os.h). */
static uint32_t gemdos_super(uint8_t *image, uint32_t argument, CallerAddressRegisters saved,
                             uint32_t return_pc) {
    uint32_t previous_stack = 0;

    trap_save_registers(image, saved, return_pc);
    os_super(argument, &previous_stack);
    return previous_stack;
}

/* init_gem_and_screens @ 0x10118 — register with the AES, open a virtual workstation, take the two
 * screen bases off XBIOS, and silence the keyboard click.
 *
 * `frame` is the routine's own A6 (see this file's header comment): its three locals are the four
 * out-parameters `graf_handle` writes through and the two words that catch answers nothing reads.
 *
 * THE WORK BUFFER IS CARVED OUT BELOW THE VISIBLE SCREEN, not allocated: `Logbase - 32000`. On a
 * real machine that is the 32,000 bytes under the screen TOS was already showing. */
void init_gem_and_screens(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t scratch_out = addr_add(frame, (uint32_t)INIT_FRAME_SCRATCH_OUT);

    wr16(image + addr_add(frame, (uint32_t)INIT_FRAME_AP_ID),
         (uint16_t)appl_init(image, saved));

    for (uint16_t slot = 0; slot < WORK_IN_ONES; slot++)
        wr16(image + addr_add(A_vdi_work_in,
                              sign_ext16((uint32_t)(slot * GEM_ARRAY_WORD_BYTES))), 1);
    wr16(image + gem_word(A_vdi_work_in, WORK_IN_COORD_SLOT), WORK_IN_COORD_RASTER);

    wr16(image + addr_add(frame, (uint32_t)INIT_FRAME_PHYS_HANDLE),
         (uint16_t)graf_handle(image, scratch_out, scratch_out, scratch_out, scratch_out, saved));
    v_opnvwk(image, A_vdi_work_in, A_vdi_handle, A_vdi_work_out, saved);

    wr16(image + A_screen_rez,
         (uint16_t)xbios_getrez(image, saved, RET_INIT_GETREZ));
    wr32(image + A_screen_back,
         xbios_logbase(image, saved, RET_INIT_LOGBASE_BACK) - SCREEN_BYTES);
    wr32(image + A_screen_phys,
         xbios_logbase(image, saved, RET_INIT_LOGBASE_PHYS));

    wr32(image + A_super_saved_ssp,
         gemdos_super(image, be32(image + A_super_arg), saved, RET_INIT_SUPER_ENTER));

    wr16(image + A_conterm_addr_w, CONTERM_ADDRESS);
    wr32(image + A_conterm_addr_l, sign_ext16(be16(image + A_conterm_addr_w)));
    image[be32(image + A_conterm_addr_l)] = 0;

    gemdos_super(image, be32(image + A_super_saved_ssp), saved, RET_INIT_SUPER_LEAVE);
}

/* ================================================================================================
 * The sprite protocol — four routines, twelve `vro_cpyfm` calls, one rectangle
 *
 * Every copy in this group moves one 32x32 cell, so all four fill the same eight-word `blit_pxy`
 * and only the corners differ. The two helpers below are that rectangle: a copy FROM a cell's own
 * origin (the grab and the sprite draw) and a copy TO it (the background save).
 * ============================================================================================= */

/* pxy = a full cell at (0,0) in the source, landing with its top-left corner at (x, y). */
static void sprite_pxy_from_cell(uint8_t *image, int16_t x, int16_t y) {
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_X1), 0);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_Y1), 0);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_X2), SPRITE_EXTENT);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_Y2), SPRITE_EXTENT);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_X1), (uint16_t)x);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_Y1), (uint16_t)y);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_X2), (uint16_t)(x + SPRITE_EXTENT));
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_Y2), (uint16_t)(y + SPRITE_EXTENT));
}

/* ...and the other direction: a full cell at (x, y) in the source, landing at (0,0). */
static void sprite_pxy_to_cell(uint8_t *image, int16_t x, int16_t y) {
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_X1), (uint16_t)x);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_Y1), (uint16_t)y);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_X2), (uint16_t)(x + SPRITE_EXTENT));
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_SRC_Y2), (uint16_t)(y + SPRITE_EXTENT));
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_X1), 0);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_Y1), 0);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_X2), SPRITE_EXTENT);
    wr16(image + gem_word(A_blit_pxy, BLIT_PXY_DST_Y2), SPRITE_EXTENT);
}

/* Every one of the twelve copies passes the workstation handle and the two MFDBs the sprite bank
 * set up once, so the call site names only the logic operation. */
static void sprite_copy(uint8_t *image, int16_t mode, CallerAddressRegisters saved) {
    vro_cpyfm(image, (int16_t)be16(image + A_vdi_handle), mode, A_blit_pxy, A_mfdb_src, A_mfdb_dst,
              saved);
}

/* build_sprite_bank @ 0x132ec, its grab loop [0x13330, 0x1342e): sixty `c_malloc(512)` + copy pairs
 * that lift each 32x32 cell off the bank screen `build_sprite_bank_prepare` (include/blit.h) has
 * just painted, then two more allocations for the two background patches.
 *
 * The source MFDB's `fd_addr` is cleared to 0 — the VDI's "the screen" — before every grab, and the
 * destination's is the buffer just allocated. The cell's position on the 10-wide bank screen is
 * `(index % 10, index / 10)` in cells, scaled to pixels.
 *
 * WHICH TABLE A CELL LANDS IN is a straight index test: 0..46 are the ghost's frames and 47..59 the
 * bubble's, and the second table is reached with the UNBIASED index off a base 47 longwords below
 * `bubble_sprite` — so the two `lea`s differ by exactly that bias. */
void build_sprite_bank_grab_cells(uint8_t *image, CallerAddressRegisters saved) {
    for (int16_t cell = 0; cell < (int16_t)TILES_PER_BANK; cell++) {
        uint32_t buffer = c_malloc(image, (uint16_t)TILE_BYTES, saved);

        int16_t row = (int16_t)(cell / (int16_t)ROOM_TILE_COLS);
        int16_t x = (int16_t)((cell - (int16_t)(row * (int16_t)ROOM_TILE_COLS))
                              * (int16_t)TILE_PIXELS);
        int16_t y = (int16_t)(row * (int16_t)TILE_PIXELS);

        wr32(image + A_mfdb_src + MFDB_ADDR, 0);      /* 0 = the workstation's own screen */
        wr32(image + A_mfdb_dst + MFDB_ADDR, buffer);
        sprite_pxy_to_cell(image, x, y);
        sprite_copy(image, VDI_MODE_S_ONLY, saved);

        uint32_t table = cell < (int16_t)SPRITE_BANK_BUBBLE_FIRST
            ? A_ghost_sprite
            : A_bubble_sprite - SPRITE_BANK_BUBBLE_FIRST * LONG_BYTES;
        wr32(image + longword_slot(table, cell), buffer);
    }
    wr32(image + A_ghost_bg, c_malloc(image, (uint16_t)TILE_BYTES, saved));
    wr32(image + A_bubble_bg, c_malloc(image, (uint16_t)TILE_BYTES, saved));
}

/* save_sprite_backgrounds @ 0x1342e — lift the 32x32 patch of the work buffer that is about to be
 * covered by each sprite into its own buffer, so `restore_sprite_backgrounds` can put it back. */
void save_sprite_backgrounds(uint8_t *image, CallerAddressRegisters saved) {
    wr32(image + A_mfdb_src + MFDB_ADDR, 0);
    wr32(image + A_mfdb_dst + MFDB_ADDR, be32(image + A_ghost_bg));
    sprite_pxy_to_cell(image, (int16_t)be16(image + A_ghost_x), (int16_t)be16(image + A_ghost_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);

    wr32(image + A_mfdb_src + MFDB_ADDR, 0);
    wr32(image + A_mfdb_dst + MFDB_ADDR, be32(image + A_bubble_bg));
    sprite_pxy_to_cell(image, (int16_t)be16(image + A_bubble_x), (int16_t)be16(image + A_bubble_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);
}

/* draw_sprites @ 0x134f6 — the ghost's current frame and the bubble's, OR'd onto the work buffer.
 * OR is the transparency: both sprite families use only colour 0 and colour 15, so a mask would buy
 * nothing and the VDI's own clipping keeps a sprite at the screen edge inside the raster. */
void draw_sprites(uint8_t *image, CallerAddressRegisters saved) {
    uint32_t ghost_cell = longword_slot(A_ghost_sprite, (int16_t)be16(image + A_ghost_tile));
    wr32(image + A_mfdb_src + MFDB_ADDR, be32(image + ghost_cell));
    wr32(image + A_mfdb_dst + MFDB_ADDR, 0);
    sprite_pxy_from_cell(image, (int16_t)be16(image + A_ghost_x), (int16_t)be16(image + A_ghost_y));
    sprite_copy(image, VDI_MODE_S_OR_D, saved);

    uint32_t bubble_cell = longword_slot(A_bubble_sprite, (int16_t)be16(image + A_bubble_frame));
    wr32(image + A_mfdb_src + MFDB_ADDR, be32(image + bubble_cell));
    wr32(image + A_mfdb_dst + MFDB_ADDR, 0);
    sprite_pxy_from_cell(image, (int16_t)be16(image + A_bubble_x),
                         (int16_t)be16(image + A_bubble_y));
    sprite_copy(image, VDI_MODE_S_OR_D, saved);
}

/* restore_sprite_backgrounds @ 0x135d2 — undo `draw_sprites`, leaving the work buffer holding the
 * room and its objects only, which is what `bubble_collision_probe` reads. */
void restore_sprite_backgrounds(uint8_t *image, CallerAddressRegisters saved) {
    wr32(image + A_mfdb_src + MFDB_ADDR, be32(image + A_ghost_bg));
    wr32(image + A_mfdb_dst + MFDB_ADDR, 0);
    sprite_pxy_from_cell(image, (int16_t)be16(image + A_ghost_x), (int16_t)be16(image + A_ghost_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);

    wr32(image + A_mfdb_src + MFDB_ADDR, be32(image + A_bubble_bg));
    wr32(image + A_mfdb_dst + MFDB_ADDR, 0);
    sprite_pxy_from_cell(image, (int16_t)be16(image + A_bubble_x),
                         (int16_t)be16(image + A_bubble_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);
}

/* ================================================================================================
 * The room composer and the hall of fame
 * ============================================================================================= */

/* draw_room_to_stage @ 0x13a08 — compose the current room's 5 x 10 tile map into the staging area a
 * room's worth below the work buffer.
 *
 * THIS IS THE ROUTINE THAT SITS ON THIS SUBSYSTEM'S SLICE BOUNDARY, which is why it is here and not
 * in `src/blit.c`. Its loop body is the tile draw, which `include/blit.h` owns and has verified as
 * `draw_room_tile_to_stage`; its other statement is a `vq_mouse` per cell, which is this
 * subsystem's VDI binding and was unported when `src/blit.c` cut its slice around it. Composing the
 * two is the whole routine, and nothing here restates either half.
 *
 * The poll's answers go into the input block the game reads everywhere else; the loop ignores them.
 * Fifty polls per room is what makes the pointer's position current by the time the room appears.
 *
 * WHERE THE TILE DRAW LEAVES A2. Each cell's `vq_mouse` traps with whatever the PREVIOUS cell's
 * `move.l (a3)+,(a2)+` run left there, so the register is threaded from one iteration to the next.
 * `draw_room_tile_to_stage` (include/blit.h) reports it, which is `docs/agent-playbook.md` §5's
 * "derivable" case answered by the routine that derives it: this file used to re-compute the
 * destination arithmetic itself, and the two copies could have drifted apart. */
/* ONE CELL, [0x13a20, 0x13afa) — the loop's whole body, and a function of its own because it is
 * what the per-cell differential runs. A poll's effect on the input block is IDEMPOTENT under a
 * fixed mouse state, so a run to `rts` cannot tell fifty polls from one: only a case that stops
 * between two cells can, and that case needs a callable body. Answers the A2 for the next cell. */
uint32_t draw_room_to_stage_cell(uint8_t *image, int16_t tile_row, int16_t tile_col,
                                 CallerAddressRegisters live) {
    vq_mouse(image, (int16_t)be16(image + A_vdi_handle), A_mouse_buttons, A_mouse_x, A_mouse_y,
             live);
    return draw_room_tile_to_stage(image, tile_row, tile_col);
}

void draw_room_to_stage(uint8_t *image, CallerAddressRegisters saved) {
    CallerAddressRegisters live = saved;

    for (int16_t tile_row = 0; tile_row < (int16_t)ROOM_TILE_ROWS; tile_row++)
        for (int16_t tile_col = 0; tile_col < (int16_t)ROOM_TILE_COLS; tile_col++)
            live.a2 = draw_room_to_stage_cell(image, tile_row, tile_col, live);
}

/* One `v_gtext` at this screen's own workstation handle, which every line of the hall of fame and
 * every text card shares. */
static void hall_text(uint8_t *image, int16_t x, int16_t y, uint32_t text,
                      CallerAddressRegisters saved) {
    v_gtext(image, (int16_t)be16(image + A_vdi_handle), x, y, text, saved);
}

static void hall_pen(uint8_t *image, int16_t pen, CallerAddressRegisters saved) {
    vst_color(image, (int16_t)be16(image + A_vdi_handle), pen, saved);
}

/* draw_hall_of_fame @ 0x11dbc — room 0 as the backdrop, five fixed labels, and the table drawn from
 * its BEST entry down, so slot 4 lands on the "SCORE 1:" row.
 *
 * `frame` is the routine's own A6: the two digit buffers `itoa_padded` formats into are stack
 * locals (see this file's header comment). */
void draw_hall_of_fame(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    static const int16_t label_y_offsets[] = HALL_LABEL_Y_OFFSETS;
    uint32_t score_text = addr_add(frame, (uint32_t)HALL_FRAME_SCORE_TEXT);
    uint32_t room_text = addr_add(frame, (uint32_t)HALL_FRAME_ROOM_TEXT);
    int16_t handle = (int16_t)be16(image + A_vdi_handle);

    vst_height(image, handle, HALL_TEXT_HEIGHT, A_text_char_w, A_text_char_h, A_text_cell_w,
               A_text_cell_h, saved);
    hall_pen(image, HALL_PEN_LABEL, saved);

    wr16(image + A_room_number, HALL_BACKDROP_ROOM);
    draw_room_to_stage(image, saved);
    stage_to_work(image);

    hall_pen(image, HALL_PEN_LABEL, saved);
    for (unsigned label = 0; label < HISCORE_SLOTS; label++)
        hall_text(image, HALL_LABEL_X, (int16_t)(HALL_BASE_Y - label_y_offsets[label]),
                  A_text_score_labels + label * TEXT_SCORE_LABEL_BYTES, saved);

    for (int16_t slot = (int16_t)HISCORE_SLOTS - 1; slot >= 0; slot--) {
        int16_t row_y = (int16_t)(HALL_BASE_Y - slot * HALL_ROW_PITCH);

        hall_pen(image, HALL_PEN_LABEL, saved);
        hall_text(image, HALL_HALL_X, row_y, A_text_hall, saved);

        itoa_padded(image, (int32_t)be32(image + longword_slot(A_hall_scores, slot)), score_text,
                    (int16_t)HISCORE_SCORE_DIGITS);
        hall_pen(image, HALL_PEN_NUMBER, saved);
        hall_text(image, HALL_SCORE_X, row_y, score_text, saved);

        itoa_padded(image, (int32_t)be32(image + longword_slot(A_hall_rooms, slot)), room_text,
                    (int16_t)HISCORE_ROOM_DIGITS);
        hall_text(image, HALL_ROOM_X, row_y, room_text, saved);
    }
}

/* WHAT `c_read` AND `c_write` LEAVE IN A1, WHICH THIS FILE'S NEXT TRAP THEN FILES.
 *
 * Both consult the fd-mode side table through `c_getfdmode` @ 0x15d36, whose scan loop builds its
 * end sentinel as `lea fd_mode_table,a0 / movea.l a0,a1 / adda.w #$130,a1` and never writes A1
 * again. So either call, on a real file handle, returns with A1 one word past that table — which is
 * `c_errno` — and whatever traps next parks THAT in the trampoline's save slot rather than the
 * caller's own A1. It is `docs/agent-playbook.md` §5's "derivable" case: the value comes from a
 * callee's own instructions and is a constant, not something a caller could compute.
 *
 * SO EVERY LOADER BELOW CALLS `c_read_reporting` / `c_write_reporting` (include/clib.h), which are
 * those two routines threading their own A1 through a register block held BY POINTER. This file
 * used to wrap `c_read`/`c_write` and assign `live.a1 = A_c_errno` unconditionally afterwards,
 * which is wrong on exactly the arms that return early: `c_read` bails at 0x16710 on a NEGATIVE
 * Fread before it ever reaches `c_getfdmode`, and both routines' console arms return before it too.
 * The reporting forms record A1 where the original writes it and nowhere else.
 *
 * (Nothing in this file opens a console pseudo-handle — every name it hands `c_open`/`c_creat` is a
 * disk file, which `test_no_loader_opens_a_console_pseudo_handle` is what says. And no run here can
 * reach the negative-read arm: the model REFUSES an unstaged file rather than answering an error,
 * so ../STATUS.md carries it as a residual.) */

/* save_hiscores @ 0x1207a — write the five entries to GHOST.SCR, with a banner on the visible
 * screen while it happens.
 *
 * `frame` is the routine's own A6: the digit buffer and the loop counter are stack locals, and the
 * counter is not merely a local (see `include/frontend.h`'s SAVE_FRAME_SLOT) — both `graf_mouse`
 * call sites push only the mode word and a zero word, so the `addr_in` long the AES reads is that
 * zero over the counter. Keeping it in the image is what makes the two mouse forms come out right.
 *
 * The file is created in TEXT mode, but every byte written is a digit: `itoa_padded` zero-pads, so
 * there is no newline for `c_write` to expand and the file is exactly 40 ASCII bytes. */
/* save_hiscores' prologue [0x1207a, 0x120ce): the text attributes, the move of the logical base onto
 * the VISIBLE screen so the banner is seen, and the mouse SHOWN.
 *
 * It is a core of its own for one reason: the mouse form is only observable HERE. `graf_mouse`'s
 * whole image effect is `int_in[0]` and `addr_in`, and the routine's closing `graf_mouse` overwrites
 * both before the `rts` — so a case that ran the routine whole could not tell this call's form from
 * any other value (../STATUS.md). A case enters at the routine and stops at the `clr.w -(a7)` that
 * begins `c_creat`'s argument push. */
void save_hiscores_prologue(uint8_t *image, uint32_t frame, CallerAddressRegisters live) {
    int16_t handle = (int16_t)be16(image + A_vdi_handle);

    vst_height(image, handle, HALL_TEXT_HEIGHT, A_text_char_w, A_text_char_h, A_text_cell_w,
               A_text_cell_h, live);
    vst_color(image, handle, HALL_PEN_LABEL, live);
    xbios_setscreen(image, be32(image + A_screen_phys), be32(image + A_screen_phys),
                    SETSCREEN_KEEP_RESOLUTION, live, RET_SAVE_HISCORES_SETSCREEN_PHYS);
    graf_mouse(image, AES_M_ON, be16(image + addr_add(frame, (uint32_t)SAVE_FRAME_SLOT)), live);
}

void save_hiscores(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    uint32_t text = addr_add(frame, (uint32_t)SAVE_FRAME_TEXT);
    uint32_t counter = addr_add(frame, (uint32_t)SAVE_FRAME_SLOT);

    save_hiscores_prologue(image, frame, *live);

    int16_t file = c_creat(image, A_name_ghost_scr_creat, C_CREAT_MODE_TEXT, *live);
    if (file >= 0) {
        v_gtext(image, (int16_t)be16(image + A_vdi_handle), SAVE_BANNER_X, SAVE_BANNER_Y,
                A_text_saving_banner, *live);
        wr16(image + counter, 0);
        while ((int16_t)be16(image + counter) < (int16_t)HISCORE_SLOTS) {
            int16_t slot = (int16_t)be16(image + counter);

            itoa_padded(image, (int32_t)be32(image + longword_slot(A_hall_scores, slot)), text,
                        (int16_t)HISCORE_SCORE_DIGITS);
            c_write_reporting(image, (uint16_t)file, text, (int16_t)HISCORE_SCORE_DIGITS, live);
            itoa_padded(image, (int32_t)be32(image + longword_slot(A_hall_rooms, slot)), text,
                        (int16_t)HISCORE_ROOM_DIGITS);
            c_write_reporting(image, (uint16_t)file, text, (int16_t)HISCORE_ROOM_DIGITS, live);

            wr16(image + counter, (uint16_t)(slot + 1));
        }
        c_close(image, (uint16_t)file, *live);
    }

    graf_mouse(image, AES_M_OFF, be16(image + counter), *live);
    xbios_setscreen(image, be32(image + A_screen_back), be32(image + A_screen_phys),
                    SETSCREEN_KEEP_RESOLUTION, *live, RET_SAVE_HISCORES_SETSCREEN_BACK);
}

/* hiscore_insert_and_save @ 0x11f84 — offer the candidate to the table, and if it beats the WORST
 * entry, overwrite that entry, re-sort, and write the file.
 *
 * THE THREE ROUTINES IN THIS CHAIN THREAD ONE `live` REGISTER FILE, because `save_hiscores` RETURNS
 * with A1 changed: its `c_write`s leave A1 at `c_errno` (above), the two-player arm above then
 * offers the second score with no intervening trap, and every trap in that second pass files what
 * the first left. Passing the file by pointer is how that escapes rather than being lost at the
 * `return`.
 *
 * THE SORT IS FIVE PASSES OF FOUR ADJACENT COMPARES, unconditionally: it counts its swaps in a
 * local and never reads the count, so there is no early exit. Five passes is what a value inserted
 * at slot 0 needs to reach slot 4. */
static void swap_longs(uint8_t *image, uint32_t lower, uint32_t upper) {
    uint32_t held = be32(image + upper);

    wr32(image + upper, be32(image + lower));
    wr32(image + lower, held);
}

void hiscore_insert_and_save(uint8_t *image, uint32_t save_frame, CallerAddressRegisters *live) {
    if ((int32_t)be32(image + A_hiscore_candidate) <= (int32_t)be32(image + A_hall_scores))
        return;

    wr32(image + A_hiscore_candidate, 0);
    wr32(image + A_hall_scores, be32(image + A_hiscore_pending_score));
    wr32(image + A_hall_rooms, sign_ext16(be16(image + A_hiscore_pending_room)));

    for (int16_t pass = 0; pass < (int16_t)HISCORE_SORT_PASSES; pass++) {
        for (int16_t slot = 0; slot < (int16_t)HISCORE_SORT_COMPARES; slot++) {
            uint32_t lower_score = longword_slot(A_hall_scores, slot);
            uint32_t upper_score = longword_slot(A_hall_scores + LONG_BYTES, slot);
            if ((int32_t)be32(image + lower_score) <= (int32_t)be32(image + upper_score))
                continue;
            swap_longs(image, lower_score, upper_score);
            swap_longs(image, longword_slot(A_hall_rooms, slot),
                       longword_slot(A_hall_rooms + LONG_BYTES, slot));
        }
    }
    save_hiscores(image, save_frame, live);
}

/* hiscore_submit_players @ 0x11d6e — offer the table one score per player.
 *
 * In two-player mode it offers each player's own score and best room in turn; in one-player mode
 * the caller has already put the score in `hiscore_candidate`, so this only fills the pending pair
 * from the live score and the best room reached. */
void hiscore_submit_players(uint8_t *image, uint32_t save_frame, CallerAddressRegisters *live) {
    if (be16(image + A_player_count) == PLAYER_COUNT_TWO) {
        wr32(image + A_hiscore_candidate, be32(image + A_p1_score));
        wr32(image + A_hiscore_pending_score, be32(image + A_p1_score));
        wr16(image + A_hiscore_pending_room, be16(image + A_p1_max_room));
        hiscore_insert_and_save(image, save_frame, live);

        wr32(image + A_hiscore_candidate, be32(image + A_p2_score));
        wr32(image + A_hiscore_pending_score, be32(image + A_p2_score));
        wr16(image + A_hiscore_pending_room, be16(image + A_p2_max_room));
        hiscore_insert_and_save(image, save_frame, live);
        return;
    }
    wr32(image + A_hiscore_pending_score, be32(image + A_score));
    wr16(image + A_hiscore_pending_room, be16(image + A_max_room_reached));
    hiscore_insert_and_save(image, save_frame, live);
}

/* ================================================================================================
 * The presentation screen and the file loaders
 * ============================================================================================= */

/* show_presentation @ 0x10eb8 — paint the GHOST.PRE picture. It is bank 6 of the tile bank, so the
 * ordinary bank painter draws it; the visible screen is cleared first, the file's own palette is
 * installed, and the finished picture is copied up in one 30,720-byte run. */
void show_presentation(uint8_t *image, CallerAddressRegisters saved) {
    wr16(image + A_bank_index, DAT_BANK_PRE);
    draw_tile_bank_screen(image);
    clear_physical_screen(image);
    xbios_setpalette(image, be32(image + A_pre_palette), saved,
                     RET_SHOW_PRESENTATION_SETPALETTE);

    copy_longs_ascending(image, be32(image + A_screen_back), be32(image + A_screen_phys),
                         CLEARED_SCREEN_BYTES / LONG_BYTES);
}

/* The four loaders share one shape: open, allocate, read, close — and RETRY the whole thing while
 * the open failed. Under the kit's model an unstaged name is a refused run rather than a negative
 * handle, so the retry runs once and the failure arm is read-verified (../STATUS.md).
 *
 * READ THE `continue` INSIDE THE `do { } while (file < 0)` CAREFULLY: in a do-while it jumps to the
 * CONDITION, not to the top, so `if (file < 0) continue;` is the original's `bmi` back to the open —
 * the loop re-tests the same `file` it just failed on and goes round. That is the whole retry, and
 * it is spelt this way rather than as a `while (…) { }` because the original really does open, test,
 * and fall through into the body. */

/* load_demo @ 0x10dea — the whole of GHOST.DEM into one buffer, with the replay cursor parked at
 * its head. The cursor is what the malloc's answer is stored in FIRST; the base is a copy of it. */
void load_demo(uint8_t *image, CallerAddressRegisters saved) {
    CallerAddressRegisters live = saved;
    int16_t file;
    do {
        file = c_open(image, A_name_ghost_dem, C_OPEN_MODE_READ_BINARY, live);
        if (file < 0)
            continue;
        wr32(image + A_demo_cursor, c_malloc(image, (uint16_t)DEMO_FILE_BYTES, live));
        wr32(image + A_demo_base, be32(image + A_demo_cursor));
        c_read_reporting(image, (uint16_t)file, be32(image + A_demo_cursor),
                           (uint16_t)DEMO_FILE_BYTES, &live);
        c_close(image, (uint16_t)file, live);
    } while (file < 0);
}

/* load_presentation @ 0x10e44 — the title picture into `dat_bank[6]` and the 32-byte palette that
 * follows it in the file into `pre_palette`. */
void load_presentation(uint8_t *image, CallerAddressRegisters saved) {
    uint32_t picture_bank = A_dat_bank + DAT_BANK_PRE * LONG_BYTES;
    CallerAddressRegisters live = saved;
    int16_t file;
    do {
        file = c_open(image, A_name_ghost_pre, C_OPEN_MODE_READ_BINARY, live);
        if (file < 0)
            continue;
        wr32(image + picture_bank, c_malloc(image, (uint16_t)PICTURE_BYTES, live));
        c_read_reporting(image, (uint16_t)file, be32(image + picture_bank),
                           (uint16_t)PICTURE_BYTES, &live);
        wr32(image + A_pre_palette, c_malloc(image, (uint16_t)PALETTE_BYTES, live));
        c_read_reporting(image, (uint16_t)file, be32(image + A_pre_palette),
                           (uint16_t)PALETTE_BYTES, &live);
        c_close(image, (uint16_t)file, live);
    } while (file < 0);
}

/* load_level_pictures @ 0x1396c — the six 30,720-byte tile banks of GHOST.DAT and the palette that
 * follows them, each into its own allocation. */
void load_level_pictures(uint8_t *image, CallerAddressRegisters saved) {
    CallerAddressRegisters live = saved;
    int16_t file;
    do {
        file = c_open(image, A_name_ghost_dat, C_OPEN_MODE_READ_BINARY, live);
        if (file < 0)
            continue;
        for (int16_t bank = 0; bank < (int16_t)DAT_BANKS_FROM_FILE; bank++) {
            uint32_t slot = longword_slot(A_dat_bank, bank);
            wr32(image + slot, c_malloc(image, (uint16_t)PICTURE_BYTES, live));
            c_read_reporting(image, (uint16_t)file, be32(image + slot),
                               (uint16_t)PICTURE_BYTES, &live);
        }
        wr32(image + A_dat_palette, c_malloc(image, (uint16_t)PALETTE_BYTES, live));
        c_read_reporting(image, (uint16_t)file, be32(image + A_dat_palette),
                           (uint16_t)PALETTE_BYTES, &live);
        c_close(image, (uint16_t)file, live);
    } while (file < 0);
}

/* One field of GHOST.SCR: zero-padded ASCII digits, parsed with the C library's 32-bit multiply and
 * stopped by the first byte outside '0'..'9'. The buffer is NUL-terminated by the caller, so the
 * terminator is what stops it on a full-width field.
 *
 * The digit is SIGN-extended before it is added (`move.b` / `ext.w` / `ext.l`), which matters only
 * for a byte the loop would already have refused — but it is the arithmetic the original does. */
static uint32_t parse_padded_number(const uint8_t *image, uint32_t text) {
    uint32_t value = 0;
    uint16_t index = 0;
    for (;;) {
        int16_t digit = (int16_t)sign_ext8(image[addr_add(text, sign_ext16(index))]);
        if (digit < '0' || digit > '9')
            return value;
        value = c_lmul(value, DECIMAL_RADIX) + (uint32_t)(int32_t)digit - '0';
        index++;
    }
}

/* load_hiscores @ 0x121a0 — five (score, room) pairs of ASCII digits, read six bytes and two bytes
 * at a time. `frame` is the routine's own A6: the two digit buffers are stack locals (see this
 * file's header comment).
 *
 * WITH NO FILE the table is not left alone: every score reads 0 and every room reads 1, which is
 * what a fresh install shows. Under the model that arm is unreachable — an unstaged name refuses
 * the run rather than answering negative — so it is transcribed and read-verified. */
void load_hiscores(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t score_text = addr_add(frame, (uint32_t)HISCORE_FRAME_SCORE_TEXT);
    uint32_t room_text = addr_add(frame, (uint32_t)HISCORE_FRAME_ROOM_TEXT);

    CallerAddressRegisters live = saved;
    int16_t file = c_open(image, A_name_ghost_scr, C_OPEN_MODE_READ_TEXT, live);
    if (file < 0) {
        for (int16_t slot = 0; slot < (int16_t)HISCORE_SLOTS; slot++) {
            wr32(image + longword_slot(A_hall_scores, slot), 0);
            wr32(image + longword_slot(A_hall_rooms, slot), HISCORE_MISSING_ROOM);
        }
        return;
    }

    for (int16_t slot = 0; slot < (int16_t)HISCORE_SLOTS; slot++) {
        c_read_reporting(image, (uint16_t)file, score_text, (uint16_t)HISCORE_SCORE_DIGITS,
                           &live);
        image[addr_add(score_text, HISCORE_SCORE_DIGITS)] = 0;
        wr32(image + longword_slot(A_hall_scores, slot),
             parse_padded_number(image, score_text));

        c_read_reporting(image, (uint16_t)file, room_text, (uint16_t)HISCORE_ROOM_DIGITS, &live);
        image[addr_add(room_text, HISCORE_ROOM_DIGITS)] = 0;
        wr32(image + longword_slot(A_hall_rooms, slot),
             parse_padded_number(image, room_text));
    }
    c_close(image, (uint16_t)file, live);
}

/* ================================================================================================
 * Glue
 *
 * Alcyon/DRI C passes arguments on the stack (test/abi.py), so a case pokes them where the callee
 * reads them and the same values arrive here as C arguments. Every routine in this file also takes
 * the CALLER'S A1/A2, which the case takes from the oracle's own input registers.
 * ============================================================================================= */

void g_vdi_call(uint8_t *image, uint32_t a1, uint32_t a2) {
    vdi_call(image, caller_registers(a1, a2));
}

void g_gem_aes(uint8_t *image, uint32_t pblock, uint32_t a1, uint32_t a2) {
    gem_aes(image, pblock, caller_registers(a1, a2));
}

void g_vdi_set_src_mfdb(uint8_t *image, uint32_t mfdb) { vdi_set_src_mfdb(image, mfdb); }
void g_vdi_set_dst_mfdb(uint8_t *image, uint32_t mfdb) { vdi_set_dst_mfdb(image, mfdb); }

void g_vst_height(uint8_t *image, uint32_t handle, uint32_t height, uint32_t char_w,
                  uint32_t char_h, uint32_t cell_w, uint32_t cell_h, uint32_t a1, uint32_t a2) {
    vst_height(image, (int16_t)handle, (int16_t)height, char_w, char_h, cell_w, cell_h,
               caller_registers(a1, a2));
}

int32_t g_vst_color(uint8_t *image, uint32_t handle, uint32_t index, uint32_t a1, uint32_t a2) {
    return vst_color(image, (int16_t)handle, (int16_t)index, caller_registers(a1, a2));
}

int32_t g_vsf_color(uint8_t *image, uint32_t handle, uint32_t index, uint32_t a1, uint32_t a2) {
    return vsf_color(image, (int16_t)handle, (int16_t)index, caller_registers(a1, a2));
}

void g_v_opnvwk(uint8_t *image, uint32_t work_in, uint32_t handle_out, uint32_t work_out,
                uint32_t a1, uint32_t a2) {
    v_opnvwk(image, work_in, handle_out, work_out, caller_registers(a1, a2));
}

void g_v_clrwk(uint8_t *image, uint32_t handle, uint32_t a1, uint32_t a2) {
    v_clrwk(image, (int16_t)handle, caller_registers(a1, a2));
}

void g_vq_mouse(uint8_t *image, uint32_t handle, uint32_t buttons_out, uint32_t x_out,
                uint32_t y_out, uint32_t a1, uint32_t a2) {
    vq_mouse(image, (int16_t)handle, buttons_out, x_out, y_out, caller_registers(a1, a2));
}

void g_vq_key_s(uint8_t *image, uint32_t handle, uint32_t state_out, uint32_t a1, uint32_t a2) {
    vq_key_s(image, (int16_t)handle, state_out, caller_registers(a1, a2));
}

void g_v_gtext(uint8_t *image, uint32_t handle, uint32_t x, uint32_t y, uint32_t text,
               uint32_t a1, uint32_t a2) {
    v_gtext(image, (int16_t)handle, (int16_t)x, (int16_t)y, text, caller_registers(a1, a2));
}

void g_vr_recfl(uint8_t *image, uint32_t handle, uint32_t pxy, uint32_t a1, uint32_t a2) {
    vr_recfl(image, (int16_t)handle, pxy, caller_registers(a1, a2));
}

void g_vro_cpyfm(uint8_t *image, uint32_t handle, uint32_t mode, uint32_t pxy, uint32_t src_mfdb,
                 uint32_t dst_mfdb, uint32_t a1, uint32_t a2) {
    vro_cpyfm(image, (int16_t)handle, (int16_t)mode, pxy, src_mfdb, dst_mfdb,
              caller_registers(a1, a2));
}

int32_t g_aes_crysif(uint8_t *image, uint32_t opcode, uint32_t a1, uint32_t a2) {
    return aes_crysif(image, (int16_t)opcode, caller_registers(a1, a2));
}

int32_t g_appl_init(uint8_t *image, uint32_t a1, uint32_t a2) {
    return appl_init(image, caller_registers(a1, a2));
}

int32_t g_graf_handle(uint8_t *image, uint32_t char_w, uint32_t char_h, uint32_t cell_w,
                      uint32_t cell_h, uint32_t a1, uint32_t a2) {
    return graf_handle(image, char_w, char_h, cell_w, cell_h, caller_registers(a1, a2));
}

void g_graf_mouse(uint8_t *image, uint32_t mode, uint32_t mform, uint32_t a1, uint32_t a2) {
    graf_mouse(image, (int16_t)mode, mform, caller_registers(a1, a2));
}

/* `frame` is the routine's own A6, which the case computes from `emu.STACK_TOP`. */
void g_init_gem_and_screens(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    init_gem_and_screens(image, frame, caller_registers(a1, a2));
}

void g_build_sprite_bank_grab_cells(uint8_t *image, uint32_t a1, uint32_t a2) {
    build_sprite_bank_grab_cells(image, caller_registers(a1, a2));
}

/* The whole of `build_sprite_bank` @ 0x132ec: `include/blit.h`'s verified prefix and the grab loop
 * above, composed. The composition is what one case runs to `rts` — it is not a third routine. */
void g_build_sprite_bank(uint8_t *image, uint32_t a1, uint32_t a2) {
    build_sprite_bank_prepare(image);
    build_sprite_bank_grab_cells(image, caller_registers(a1, a2));
}

void g_save_sprite_backgrounds(uint8_t *image, uint32_t a1, uint32_t a2) {
    save_sprite_backgrounds(image, caller_registers(a1, a2));
}

void g_draw_sprites(uint8_t *image, uint32_t a1, uint32_t a2) {
    draw_sprites(image, caller_registers(a1, a2));
}

void g_restore_sprite_backgrounds(uint8_t *image, uint32_t a1, uint32_t a2) {
    restore_sprite_backgrounds(image, caller_registers(a1, a2));
}

void g_draw_room_to_stage(uint8_t *image, uint32_t a1, uint32_t a2) {
    draw_room_to_stage(image, caller_registers(a1, a2));
}

/* The per-cell slice's glue. It answers the A2 the cell leaves, which the case compares against the
 * oracle's own A2 at the stop PC — so the register this reconstruction reports is verified and not
 * merely self-consistent. */
uint32_t g_draw_room_to_stage_cell(uint8_t *image, uint32_t tile_row, uint32_t tile_col,
                                   uint32_t a1, uint32_t a2) {
    return draw_room_to_stage_cell(image, (int16_t)tile_row, (int16_t)tile_col,
                                   caller_registers(a1, a2));
}

/* `frame` is the routine's own A6, as `g_init_gem_and_screens`'. */
void g_draw_hall_of_fame(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    draw_hall_of_fame(image, frame, caller_registers(a1, a2));
}

/* `save_frame` is `save_hiscores`' own A6, which the case derives from `emu.STACK_TOP` and the
 * `link` size of every routine between the entry point and it. */
void g_save_hiscores_prologue(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    save_hiscores_prologue(image, frame, caller_registers(a1, a2));
}

void g_save_hiscores(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    save_hiscores(image, frame, &live);
}

void g_hiscore_insert_and_save(uint8_t *image, uint32_t save_frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    hiscore_insert_and_save(image, save_frame, &live);
}

void g_hiscore_submit_players(uint8_t *image, uint32_t save_frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    hiscore_submit_players(image, save_frame, &live);
}

void g_show_presentation(uint8_t *image, uint32_t a1, uint32_t a2) {
    show_presentation(image, caller_registers(a1, a2));
}

void g_load_demo(uint8_t *image, uint32_t a1, uint32_t a2) {
    load_demo(image, caller_registers(a1, a2));
}

void g_load_presentation(uint8_t *image, uint32_t a1, uint32_t a2) {
    load_presentation(image, caller_registers(a1, a2));
}

void g_load_level_pictures(uint8_t *image, uint32_t a1, uint32_t a2) {
    load_level_pictures(image, caller_registers(a1, a2));
}

void g_load_hiscores(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    load_hiscores(image, frame, caller_registers(a1, a2));
}
