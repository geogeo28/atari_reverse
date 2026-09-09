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

#include "common.h"     /* LONG_BYTES, WORD_BYTES, `word_at` and `longword_slot` — the strides and
                         * accessors every table in this file is indexed and read through */
#include "globals.h"    /* A4_BASE, which `frontend.h` -> `clib.h` already brings in: named here
                         * because the GEM binding below uses it DIRECTLY, not through either */
#include "gameplay.h"   /* the ghost and bubble the sprite protocol draws, the room
                         * tables the menu searches, and the console flush it reads through */
#include "sound.h"      /* the triggers the menu and the attract sequence fire */
#include "voice.h"      /* the sample buffer the boot path frees once the voice is done */

/* One word of a GEM array named by its index, which is how every `contrl`/`intin`/`ptsin` slot in
 * this file is spelt. The 68000 reaches them as `lea array,a0 / adda.w #index*2,a0`. */
static uint32_t gem_word(uint32_t array, unsigned index) {
    return array + index * WORD_BYTES;
}

static uint32_t vdi_pblock_slot(unsigned index) {
    return A_vdi_pblock + index * LONG_BYTES;
}

/* ---- THE BASE REGISTER THE ORIGINAL KEEPS, AND WHERE THIS FILE'S COPY OF IT WENT ---------------
 *
 * `GlobalsBase` / `globals_base` / `globals_at` were written here for ../STATUS.md's wave 5c and
 * moved to `include/common.h` in wave 6b, once `src/gameplay.c` became the second core to want
 * them — which is that header's own stated trigger. It carries the whole mechanism and the
 * measurement; what is left to say HERE is which slots this file reaches through it, because it is
 * the range that keeps every one of them a `d16` displacement:
 *
 *   * the VDI binding — `A_vdi_pblock` (0x1e8ca) to `contrl[10]`, the second MFDB word (0x23704),
 *     which is -26192 to -6166 off A4_BASE. `vq_key_s` @ 0x16a5e writes four of them per call and
 *     a raster copy ten, which is what made this the file the lever was measured in;
 *   * the sprite protocol — `A_blit_pxy`'s eight words at -7236, the two MFDBs' `fd_addr` at
 *     -7706 (`A_mfdb_src`) and -7726 (`A_mfdb_dst`), the two saved-patch pointers at -7730 and
 *     -7734, and the ghost's and bubble's coordinates and frame indices, -7976 to -7986 (wave 6b);
 *   * NOT the AES binding, which keeps the `image + <address>` form on purpose: `aes_crysif`,
 *     `aes_bind_parameter_block`, `appl_init`, `graf_handle` and `graf_mouse` are BOOT AND MENU and
 *     make 0.00 calls in the profiled frame, so converting them would buy nothing measurable.
 *     `gem_aes` materialises a base for its two saved-register stores and its neighbours do not —
 *     the one place in this file where the two idioms sit side by side. */


/* The GEM trampolines park only the two ADDRESS registers. Unlike `include/clib.h`'s GEMDOS/XBIOS
 * pair they do not pop and re-push their own return address — the selector travels in D0 rather
 * than on the stack — so `A_trap_saved_ret` is untouched by anything in this file.
 *
 * It takes the BASE and not the image. Handing it the image files both saved registers 26 KB BELOW
 * the image — `test_frontend.py`'s `graf_mouse`, `appl_init`, `graf_handle` and `aes_crysif` cases
 * caught exactly that in this wave (11 failures, 2026-09-07) — and `GlobalsBase` above is why the
 * mistake can no longer be written. */
static void gem_trap_save_registers(GlobalsBase globals, CallerAddressRegisters saved) {
    wr32(globals_at(globals, A_trap_saved_a1), saved.a1);
    wr32(globals_at(globals, A_trap_saved_a2), saved.a2);
}

/* ================================================================================================
 * The VDI binding
 * ============================================================================================= */

/* vdi_call @ 0x168d4 — the whole VDI trap. Every entry point below fills `contrl` and jumps here.
 * The `contrl` pointer is re-filed on EVERY call rather than once at start-up, which is why a run
 * entered below `v_opnvwk` still reaches the right array. */
static void vdi_call_at(uint8_t *image, GlobalsBase globals, CallerAddressRegisters saved) {
    gem_trap_save_registers(globals, saved);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_CONTRL)), A_vdi_contrl);
    os_vdi(image, A_vdi_pblock);
}

void vdi_call(uint8_t *image, CallerAddressRegisters saved) {
    vdi_call_at(image, globals_base(image), saved);
}

/* The tail every entry point shares: name the opcode, say how many ptsin PAIRS and intin entries
 * are being handed over, file the workstation handle, trap. The four stores are in the order the
 * original makes them, which is the order they appear in every one of the twelve routines. */
static void vdi_trap(uint8_t *image, GlobalsBase globals, uint16_t opcode, uint16_t ptsin_pairs,
                     uint16_t intin_entries, int16_t handle, CallerAddressRegisters saved) {
    wr16(globals_at(globals, gem_word(A_vdi_contrl, VDI_CONTRL_OPCODE)), opcode);
    wr16(globals_at(globals, gem_word(A_vdi_contrl, VDI_CONTRL_PTSIN_N)), ptsin_pairs);
    wr16(globals_at(globals, gem_word(A_vdi_contrl, VDI_CONTRL_INTIN_N)), intin_entries);
    wr16(globals_at(globals, gem_word(A_vdi_contrl, VDI_CONTRL_HANDLE)), (uint16_t)handle);
    vdi_call_at(image, globals, saved);
}

/* An MFDB address arrives in `contrl` as two words, high half first. The original splits it with
 * `asr.l #8` twice and a `move.w`, and a `move.w` keeps the low word either way — so the shift's
 * sign fill is dropped before it is stored and a logical shift is the same sixteen bits. */
static void vdi_set_mfdb(GlobalsBase globals, unsigned contrl_index, uint32_t mfdb) {
    wr16(globals_at(globals, gem_word(A_vdi_contrl, contrl_index)), (uint16_t)(mfdb >> 16));
    wr16(globals_at(globals, gem_word(A_vdi_contrl, contrl_index + 1)), (uint16_t)(mfdb & 0xffffu));
}

/* vdi_set_src_mfdb @ 0x16890 / vdi_set_dst_mfdb @ 0x168b2 — the same four instructions over the two
 * MFDB slots of `vro_cpyfm`. Both are separate functions in the original and both are called, so
 * `vro_cpyfm` calls the `_at` pair rather than the shared body: it already holds the base, and a
 * port that stopped making these two calls would leave two verified routines with no on-target
 * caller at all — only the differential's direct entries. */
static void vdi_set_src_mfdb_at(GlobalsBase globals, uint32_t mfdb) {
    vdi_set_mfdb(globals, VDI_CONTRL_SRC_MFDB, mfdb);
}

static void vdi_set_dst_mfdb_at(GlobalsBase globals, uint32_t mfdb) {
    vdi_set_mfdb(globals, VDI_CONTRL_DST_MFDB, mfdb);
}

void vdi_set_src_mfdb(uint8_t *image, uint32_t mfdb) {
    vdi_set_src_mfdb_at(globals_base(image), mfdb);
}

void vdi_set_dst_mfdb(uint8_t *image, uint32_t mfdb) {
    vdi_set_dst_mfdb_at(globals_base(image), mfdb);
}

/* vst_height @ 0x168fc — VDI 12. One ptsin pair whose FIRST word is cleared and whose second is the
 * requested height, and four ptsout answers copied out through the caller's four pointers. The game
 * asks for height 6 (menu, hall of fame, save banner) and 4 (the HUD). */
void vst_height(uint8_t *image, int16_t handle, int16_t height, uint32_t char_w, uint32_t char_h,
                uint32_t cell_w, uint32_t cell_h, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    wr16(globals_at(globals, gem_word(A_vdi_ptsin, VDI_PTSIN_X)), 0);
    wr16(globals_at(globals, gem_word(A_vdi_ptsin, VDI_PTSIN_Y)), (uint16_t)height);
    vdi_trap(image, globals, VDI_VST_HEIGHT, 1, 0, handle, saved);
    wr16(image + char_w, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_HEIGHT_CHAR_W))));
    wr16(image + char_h, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_HEIGHT_CHAR_H))));
    wr16(image + cell_w, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_HEIGHT_CELL_W))));
    wr16(image + cell_h, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_HEIGHT_CELL_H))));
}

/* The shape `vst_color` @ 0x16948 and `vsf_color` @ 0x16974 share exactly: one intin entry in, one
 * intout answer back. Text colours seen are 1, 5 and 13; the only fill colours are 11 and 0. */
static int16_t vdi_set_colour(uint8_t *image, uint16_t opcode, int16_t handle, int16_t index,
                              CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    wr16(globals_at(globals, gem_word(A_vdi_intin, 0)), (uint16_t)index);
    vdi_trap(image, globals, opcode, 0, 1, handle, saved);
    return (int16_t)be16(globals_at(globals, gem_word(A_vdi_intout, 0)));
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
    GlobalsBase globals = globals_base(image);

    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_INTIN)), work_in);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_INTOUT)), work_out);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSOUT)),
         addr_add(work_out, VDI_WORK_OUT_PTSOUT_OFFSET));
    vdi_trap(image, globals, VDI_V_OPNVWK, 0, V_OPNVWK_WORK_IN_WORDS,
             (int16_t)be16(image + handle_out), saved);
    wr16(image + handle_out, be16(globals_at(globals, gem_word(A_vdi_contrl, VDI_CONTRL_HANDLE))));

    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_INTIN)), A_vdi_intin);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_INTOUT)), A_vdi_intout);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSOUT)), A_vdi_ptsout);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSIN)), A_vdi_ptsin);
}

/* v_clrwk @ 0x16a06 — VDI 3, no arrays at all. `game_top_loop` calls it once, before the first
 * picture goes up. */
void v_clrwk(uint8_t *image, int16_t handle, CallerAddressRegisters saved) {
    vdi_trap(image, globals_base(image), VDI_V_CLRWK, 0, 0, handle, saved);
}

/* vq_mouse @ 0x16a26 — VDI 124. The button mask comes back in intout[0] and the position in the
 * first ptsout pair. Every attract loop polls this and bails out when the mask reads 1. */
void vq_mouse(uint8_t *image, int16_t handle, uint32_t buttons_out, uint32_t x_out, uint32_t y_out,
              CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    vdi_trap(image, globals, VDI_VQ_MOUSE, 0, 0, handle, saved);
    wr16(image + buttons_out, be16(globals_at(globals, gem_word(A_vdi_intout, 0))));
    wr16(image + x_out, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_MOUSE_X))));
    wr16(image + y_out, be16(globals_at(globals, gem_word(A_vdi_ptsout, VDI_MOUSE_Y))));
}

/* vq_key_s @ 0x16a5e — VDI 128, the shift/control/alt bitmap in intout[0]. One caller: the blow
 * gate inside `game_frame_update`. */
void vq_key_s(uint8_t *image, int16_t handle, uint32_t state_out, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    vdi_trap(image, globals, VDI_VQ_KEY_S, 0, 0, handle, saved);
    wr16(image + state_out, be16(globals_at(globals, gem_word(A_vdi_intout, 0))));
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
    GlobalsBase globals = globals_base(image);

    wr16(globals_at(globals, gem_word(A_vdi_ptsin, VDI_PTSIN_X)), (uint16_t)x);
    wr16(globals_at(globals, gem_word(A_vdi_ptsin, VDI_PTSIN_Y)), (uint16_t)y);

    /* THE `intin` STORE BELOW IS THE ONE SLOT IN THIS FILE THAT MUST NOT MOVE TO THE BASE, and the
     * `adda.w` above is why: `sign_ext16` can make the index NEGATIVE (a string long enough for
     * `written * 2` to reach 0x8000), which the original wraps back inside the image and a
     * displacement off the base would carry ~40 KB below it. It is the only GEM slot here reached
     * with a RUN-TIME index, and it stays `image + <wrapped address>` for that reason. */
    uint32_t cursor = text;
    uint16_t written = 0;
    uint16_t character;
    do {
        character = image[cursor];
        cursor = addr_add(cursor, 1);
        wr16(image + addr_add(A_vdi_intin,
                              sign_ext16((uint32_t)(written * WORD_BYTES))),
             character);
        written++;
    } while (character != 0);

    vdi_trap(image, globals, VDI_V_GTEXT, 1, (uint16_t)(written - 1), handle, saved);
}

/* vr_recfl @ 0x16ae2 — VDI 114. It LENDS the VDI the caller's own four-word rectangle as `ptsin`
 * for the duration of the call and puts the library's array back afterwards. Only the bonus bar
 * calls it. */
void vr_recfl(uint8_t *image, int16_t handle, uint32_t pxy, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSIN)), pxy);
    vdi_trap(image, globals, VDI_VR_RECFL, 2, 0, handle, saved);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSIN)), A_vdi_ptsin);
}

/* vro_cpyfm @ 0x16b12 — VDI 109, the raster copy this game blits every 32x32 cell with. Four ptsin
 * pairs (the source rectangle then the destination corner), one intin entry (the logic operation),
 * and the two MFDB addresses split across `contrl[7..10]`. Like `vr_recfl` it lends the VDI the
 * caller's rectangle and restores the library's array.
 */
void vro_cpyfm(uint8_t *image, int16_t handle, int16_t mode, uint32_t pxy, uint32_t src_mfdb,
               uint32_t dst_mfdb, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    wr16(globals_at(globals, gem_word(A_vdi_intin, 0)), (uint16_t)mode);
    vdi_set_src_mfdb_at(globals, src_mfdb);
    vdi_set_dst_mfdb_at(globals, dst_mfdb);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSIN)), pxy);
    vdi_trap(image, globals, VDI_VRO_CPYFM, 4, 1, handle, saved);
    wr32(globals_at(globals, vdi_pblock_slot(VDI_PB_PTSIN)), A_vdi_ptsin);
}

/* ================================================================================================
 * The AES binding
 * ============================================================================================= */

/* gem_aes @ 0x149b6 — the AES trap. Unlike `vdi_call` it takes the parameter block as an argument,
 * because `aes_crysif` pushes the pointer the library keeps rather than a fixed address. */
void gem_aes(uint8_t *image, uint32_t pblock, CallerAddressRegisters saved) {
    gem_trap_save_registers(globals_base(image), saved);
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
                              sign_ext16((uint32_t)(slot * WORD_BYTES))),
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
 * EACH CALL GETS ITS OWN WRAPPER BELOW, and every wrapper names every argument the original pushes.
 * The three that ANSWER a machine fact are here; the four that write the shifter or wait for it go
 * through the kit's XBIOS doors (`os_setscreen`/`os_setpalette`/`os_setcolor`/`os_vsync`), which
 * still have no image effect and record the call in the ordered OS event ledger — so a palette this
 * program loads and one it drops are separable, and an on-target build makes the real trap AT the
 * call rather than a slice later (tools/recreate_kit/include/os.h, "the XBIOS VIDEO AND COLOUR
 * GROUP"). What the ledger cannot carry is Setscreen's physical base and resolution, so those stay
 * arguments the model reads and discards. */
static uint32_t xbios_trap_call(uint8_t *image, uint16_t selector, CallerAddressRegisters saved,
                                uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    switch (selector) {
    case XBIOS_LOGBASE:    return OS_SCREEN_BASE;
    case XBIOS_GETREZ:     return XBIOS_GETREZ_LOW_RES;
    case XBIOS_RANDOM:     return os_random(image);
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
    trap_save_registers(image, saved, return_pc);
    os_setscreen(log_base, phys_base, resolution);
}

/* Setpalette(palette) — sixteen words read off the tail of a picture file. */
static void xbios_setpalette(uint8_t *image, uint32_t palette, CallerAddressRegisters saved,
                             uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    os_setpalette(palette);
}

/* Setcolor(index, value) — one palette entry, which the two end-of-room animations force to white.
 * Its ANSWER (the pen's previous colour) is discarded at both of the game's call sites, which is why
 * the door is void. */
static void xbios_setcolor(uint8_t *image, int16_t index, int16_t value,
                           CallerAddressRegisters saved, uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    os_setcolor(index, value);
}

/* Vsync() — takes no argument and answers nothing. It is the ONLY frame sync the front end makes,
 * three per slideshow frame, and it is off-image by definition: what a real machine spends waiting
 * for the raster is invisible to a differential (`docs/on-target-execution.md`). */
static void xbios_vsync(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    os_vsync();
}

/* Random() — the only XBIOS call in this file whose ANSWER a routine uses. */
static uint32_t xbios_random(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc) {
    return xbios_trap_call(image, XBIOS_RANDOM, saved, return_pc);
}

/* One `jsr` deep: where the callee's own `link a6,#-n` puts its A6, given the caller's A7. A C
 * reconstruction has no machine stack, so a routine that hands a callee a frame has to derive the
 * address the callee's locals will live at (`include/frontend.h`'s `CALL_FRAME_COST`). */
static uint32_t callee_frame(uint32_t caller_stack) {
    return addr_add(caller_stack, -(uint32_t)CALL_FRAME_COST);
}

/* ...and the two routines that hand one out, each from its own `link`. Spelt once apiece because the
 * derivation is load-bearing and easy to get quietly wrong: a frame eight bytes off puts a callee's
 * locals where the original's are not, and the only thing that notices is the one case whose callee
 * reads its own frame (../STATUS.md's residual on `CALL_FRAME_COST`). */
static uint32_t menu_callee_frame(uint32_t frame) {
    return callee_frame(addr_add(frame, -(uint32_t)MENU_LOCAL_BYTES));
}

static uint32_t top_callee_frame(uint32_t frame) {
    return callee_frame(addr_add(frame, -(uint32_t)TOP_LOCAL_BYTES));
}

/* One square of the 6 x 6 serpentine path. Both index scalings are the 68000's: the row through
 * `muls.w` + `add.l` on the table's own address, the column through `asl.l` + `adda.w`. */
static int16_t room_grid_square(const uint8_t *image, int16_t row, int16_t col) {
    uint32_t table_row = A_room_grid + (uint32_t)((int32_t)row * (int32_t)ROOM_GRID_ROW_BYTES);

    return word_at(image, addr_add(table_row, sign_ext16((uint32_t)(col * (int32_t)WORD_BYTES))));
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
                              sign_ext16((uint32_t)(slot * WORD_BYTES))), 1);
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

/* BOTH TAKE THE BASE, and so do the four routines below: eight rectangle words and two MFDB
 * `fd_addr` longwords is TEN slots a copy, which is the same lever the VDI binding above took in
 * ../STATUS.md's wave 5c and the same one it left here unspent. `include/globals.h` carries the
 * mechanism; the numbers are `A_blit_pxy` -7236 and the two MFDBs -7702/-7706 off A4_BASE. */

/* pxy = a full cell at (0,0) in the source, landing with its top-left corner at (x, y). */
static void sprite_pxy_from_cell(GlobalsBase globals, int16_t x, int16_t y) {
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_X1)), 0);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_Y1)), 0);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_X2)), SPRITE_EXTENT);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_Y2)), SPRITE_EXTENT);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_X1)), (uint16_t)x);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_Y1)), (uint16_t)y);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_X2)), (uint16_t)(x + SPRITE_EXTENT));
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_Y2)), (uint16_t)(y + SPRITE_EXTENT));
}

/* ...and the other direction: a full cell at (x, y) in the source, landing at (0,0). */
static void sprite_pxy_to_cell(GlobalsBase globals, int16_t x, int16_t y) {
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_X1)), (uint16_t)x);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_Y1)), (uint16_t)y);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_X2)), (uint16_t)(x + SPRITE_EXTENT));
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_SRC_Y2)), (uint16_t)(y + SPRITE_EXTENT));
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_X1)), 0);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_Y1)), 0);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_X2)), SPRITE_EXTENT);
    wr16(globals_at(globals, gem_word(A_blit_pxy, BLIT_PXY_DST_Y2)), SPRITE_EXTENT);
}

/* Every one of the twelve copies passes the workstation handle and the two MFDBs the sprite bank
 * set up once, so the call site names only the logic operation.
 *
 * `always_inline` IS A MEASUREMENT AND NOT DECORATION, and it repairs a regression the base register
 * above introduced rather than buying something new: GCC inlined this at all seven sites until
 * `vro_cpyfm`'s body shrank around the `asm` barrier, and then out-lined it — which put a `jsr`,
 * four pushed arguments and a `movem` pair (82 cycles) back in front of a body that had just lost
 * 104. Inlined, the raster copy is 376 cycles a site off the objdump against the 548 it cost before
 * this wave; out of line it is 526, which is most of the lever given back. ../STATUS.md's wave 4
 * records the same shape in the shim's GEM door. */
static inline __attribute__((always_inline)) void sprite_copy(uint8_t *image, int16_t mode,
                                                              CallerAddressRegisters saved) {
    vro_cpyfm(image, vdi_handle(image), mode, A_blit_pxy, A_mfdb_src, A_mfdb_dst,
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
    /* THIS ONE IS NOT A PERFORMANCE CONVERSION — it makes 0.00 calls in a profiled frame, which is
     * the same test that leaves the AES binding above on the image form. It takes the base because
     * it shares `sprite_pxy_to_cell` with the three per-frame routines, and one writer beats a
     * second spelling of the same eight stores. Hoisted out of the loop: the barrier is opaque, so
     * inside it GCC would re-materialise the base once a cell. */
    GlobalsBase globals = globals_base(image);

    for (int16_t cell = 0; cell < (int16_t)TILES_PER_BANK; cell++) {
        uint32_t buffer = c_malloc(image, (uint16_t)TILE_BYTES, saved);

        int16_t row = (int16_t)(cell / (int16_t)ROOM_TILE_COLS);
        int16_t x = (int16_t)((cell - (int16_t)(row * (int16_t)ROOM_TILE_COLS))
                              * (int16_t)TILE_PIXELS);
        int16_t y = (int16_t)(row * (int16_t)TILE_PIXELS);

        wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), 0);  /* 0 = the workstation's own screen */
        wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), buffer);
        sprite_pxy_to_cell(globals, x, y);
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
    GlobalsBase globals = globals_base(image);

    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), 0);
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), be32(globals_at(globals, A_ghost_bg)));
    sprite_pxy_to_cell(globals, word_at_base(globals, A_ghost_x),
                       word_at_base(globals, A_ghost_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);

    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), 0);
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), be32(globals_at(globals, A_bubble_bg)));
    sprite_pxy_to_cell(globals, word_at_base(globals, A_bubble_x),
                       word_at_base(globals, A_bubble_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);
}

/* draw_sprites @ 0x134f6 — the ghost's current frame and the bubble's, OR'd onto the work buffer.
 * OR is the transparency: both sprite families use only colour 0 and colour 15, so a mask would buy
 * nothing and the VDI's own clipping keeps a sprite at the screen edge inside the raster. */
void draw_sprites(uint8_t *image, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    /* THE TWO TABLE SLOTS STAY ON THE IMAGE, and they are the only run-time addresses in this
     * group. `include/common.h`'s `globals_at` carries the rule: it is `image + (int32_t)address`
     * where the image form is `image + (uint32_t)address`, so the two agree on every address this
     * program can build and disagree only on one it cannot. Converting a run-time address would
     * buy nothing and would put the host and the 32-bit target on different sides of that. */
    uint32_t ghost_cell = longword_slot(A_ghost_sprite, word_at_base(globals, A_ghost_tile));
    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), be32(image + ghost_cell));
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), 0);
    sprite_pxy_from_cell(globals, word_at_base(globals, A_ghost_x),
                         word_at_base(globals, A_ghost_y));
    sprite_copy(image, VDI_MODE_S_OR_D, saved);

    uint32_t bubble_cell = longword_slot(A_bubble_sprite, word_at_base(globals, A_bubble_frame));
    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), be32(image + bubble_cell));
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), 0);
    sprite_pxy_from_cell(globals, word_at_base(globals, A_bubble_x),
                         word_at_base(globals, A_bubble_y));
    sprite_copy(image, VDI_MODE_S_OR_D, saved);
}

/* restore_sprite_backgrounds @ 0x135d2 — undo `draw_sprites`, leaving the work buffer holding the
 * room and its objects only, which is what `bubble_collision_probe` reads. */
void restore_sprite_backgrounds(uint8_t *image, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), be32(globals_at(globals, A_ghost_bg)));
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), 0);
    sprite_pxy_from_cell(globals, word_at_base(globals, A_ghost_x),
                         word_at_base(globals, A_ghost_y));
    sprite_copy(image, VDI_MODE_S_ONLY, saved);

    wr32(globals_at(globals, A_mfdb_src + MFDB_ADDR), be32(globals_at(globals, A_bubble_bg)));
    wr32(globals_at(globals, A_mfdb_dst + MFDB_ADDR), 0);
    sprite_pxy_from_cell(globals, word_at_base(globals, A_bubble_x),
                         word_at_base(globals, A_bubble_y));
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
    vq_mouse(image, vdi_handle(image), A_mouse_buttons, A_mouse_x, A_mouse_y,
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
    v_gtext(image, vdi_handle(image), x, y, text, saved);
}

static void hall_pen(uint8_t *image, int16_t pen, CallerAddressRegisters saved) {
    vst_color(image, vdi_handle(image), pen, saved);
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
    int16_t handle = vdi_handle(image);

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
    int16_t handle = vdi_handle(image);

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
        v_gtext(image, vdi_handle(image), SAVE_BANNER_X, SAVE_BANNER_Y,
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
 * The front end's state machine — `title_menu_loop` @ 0x115d6
 *
 * The menu, its four key arms, and the `[D]` attract sequence. `../notes/frontend.md` §2 draws the
 * whole machine; what follows is the routine, and the two things about it worth knowing first:
 *
 *   * IT RETURNS, unlike everything else at this level, and only on the two arms that start a game
 *     — `[G]` with a player count, or `[P]` with a level in 1..35. `[D]` and `[H]` fall through to
 *     the redraw, which is why a whole run needs a key queue that ends in `G`/`1`.
 *   * ITS LOCALS LIVE IN THE IMAGE, at `frame + MENU_FRAME_*`. The arms are verified as mid-entry
 *     slices as well as whole runs, and a slice has to find the locals the part before it left.
 * ============================================================================================= */

/* `Cnecin` — the BLOCKING half of every key read in this program. The flush that precedes it is
 * `src/gameplay.c`'s `drain_console_queue`, called separately at each of the four sites, because a
 * slice has to END between the two (see this section's header comment). `cnecin_return` is where
 * the trampoline returns to, which is all that separates one site from another. */
static uint32_t menu_take_key(uint8_t *image, uint32_t cnecin_return,
                              CallerAddressRegisters saved) {
    uint32_t key = 0;

    trap_save_registers(image, saved, cnecin_return);
    os_cnecin(image, &key);
    return key;
}

/* Setscreen(log, phys) with the two bases this program always passes, which is the only thing the
 * front end changes about the screen: text is drawn straight onto the visible page and the game
 * itself into the buffer below it (`../notes/frontend.md` §5). */
static void draw_onto_visible_screen(uint8_t *image, CallerAddressRegisters saved,
                                     uint32_t return_pc) {
    xbios_setscreen(image, be32(image + A_screen_phys), be32(image + A_screen_phys),
                    SETSCREEN_KEEP_RESOLUTION, saved, return_pc);
}

static void draw_into_work_buffer(uint8_t *image, CallerAddressRegisters saved,
                                  uint32_t return_pc) {
    xbios_setscreen(image, be32(image + A_screen_back), be32(image + A_screen_phys),
                    SETSCREEN_KEEP_RESOLUTION, saved, return_pc);
}

/* `vst_height(handle, MENU_TEXT_HEIGHT)` answers through the same four globals everywhere in this
 * program, so the four addresses are spelt once. */
static void menu_text_pen(uint8_t *image, int16_t height, int16_t pen,
                          CallerAddressRegisters saved) {
    vst_height(image, vdi_handle(image), height, A_text_char_w, A_text_char_h, A_text_cell_w,
               A_text_cell_h, saved);
    vst_color(image, vdi_handle(image), pen, saved);
}

static void menu_text(uint8_t *image, int16_t x, int16_t y, uint32_t text,
                      CallerAddressRegisters saved) {
    v_gtext(image, vdi_handle(image), x, y, text, saved);
}

/* The volume every front-end sound is played at: the definition's own level scaled by the `[S]`
 * toggle, so a silenced game plays every trigger at volume 0 rather than skipping it. */
static int16_t menu_volume(const uint8_t *image, int16_t step) {
    return (int16_t)(word_at(image, A_sound_enabled) * step);
}

/* The room's own ambience out of the 36-entry level table, reached with `muls.w` + `adda.w` — so a
 * room outside 0..35 wraps rather than indexing past the table (`include/common.h`'s `muls_ext_w`).
 * Its fx-table twin is `include/sound.h`'s `sound_fx_definition`, which `src/blit.c` shares. */
static uint32_t sound_room_ambience(int16_t room) {
    return addr_add(A_snd_def_level, muls_ext_w(room, (int32_t)SND_DEF_BYTES));
}

/* ...and the trigger that plays it, which the front end fires at five places and always the same
 * way: the CURRENT room's definition on voice 0, one-shot, at MENU_SFX_PRIORITY. Only the volume
 * step differs, which is why it is the one argument. */
static void play_room_ambience(uint8_t *image, int16_t volume_step) {
    sound_play(image, sound_room_ambience(word_at(image, A_room_number)), MENU_AMBIENCE_VOICE,
               menu_volume(image, volume_step), MENU_SFX_NOTE_ONE_SHOT, MENU_SFX_PRIORITY);
}

static void menu_poll_mouse(uint8_t *image, CallerAddressRegisters saved) {
    vq_mouse(image, vdi_handle(image), A_mouse_buttons, A_mouse_x, A_mouse_y, saved);
}

static int menu_aborted(const uint8_t *image) {
    return word_at(image, A_mouse_buttons) == MOUSE_BUTTON_LEFT;
}

/* `d0 = *counter; (*counter)--; return d0 <= 0;` — the LONG countdown every attract loop is bounded
 * by, at four sites. THE ORDER IS THE LOAD-BEARING PART: the test reads the value the counter
 * ARRIVED with, so the loop runs one more pass than the count says and leaves the counter one below
 * zero. Written once because four hand-copies are four chances to write it the other way round. */
static int menu_countdown_expired(uint8_t *image, uint32_t counter) {
    int32_t remaining = (int32_t)be32(image + counter);

    wr32(image + counter, (uint32_t)(remaining - 1));
    return remaining <= 0;
}

/* `acc = acc * scale + offset`, truncated TOWARD ZERO by `fp_acc_to_long` — the tail both of this
 * file's `Random()` scalings share. The truncation is where every range in `../notes/frontend.md`
 * §6 comes from: `fp_double_to_long` shifts the mantissa with a bare `lsr.l` and no rounding term.
 *
 * Each source is a plain double in DATA, never widened, so `fp_dispatch`'s widening scratch is
 * unused and none is passed — as `src/gameplay.c`'s death hold does it. */
static int16_t fp_scale_and_truncate(uint8_t *image, uint32_t scale, uint32_t offset) {
    fp_dispatch(image, FP_OP_MULTIPLY, A_fp_acc, scale, 0, 0);
    fp_dispatch(image, FP_OP_PLUS, A_fp_acc, offset, 0, 0);
    return (int16_t)fp_acc_to_long(image);
}

/* `Random() / divisor * scale + offset` — the attract sequence's two ranges, each with its own
 * three constants, which is why the same divisor sits at two DATA addresses. */
static int16_t random_divided_and_scaled(uint8_t *image, uint32_t divisor, uint32_t scale,
                                         uint32_t offset, CallerAddressRegisters saved,
                                         uint32_t return_pc) {
    fp_acc_load_long(image, xbios_random(image, saved, return_pc));
    fp_dispatch(image, FP_OP_DIVIDE, A_fp_acc, divisor, 0, 0);
    return fp_scale_and_truncate(image, scale, offset);
}

/* `Random() * scale + offset` — the room ambience's countdown, whose scale is small enough that no
 * divisor is needed. */
static int16_t random_scaled(uint8_t *image, uint32_t scale, uint32_t offset,
                             CallerAddressRegisters saved, uint32_t return_pc) {
    fp_acc_load_long(image, xbios_random(image, saved, return_pc));
    return fp_scale_and_truncate(image, scale, offset);
}

/* Paint one room into the work buffer and show it, which is how all three attract phases and the
 * hall of fame put a room on screen: the composer stages it, the instant move copies it up, and the
 * HUD row is drawn over it. */
static void menu_show_room(uint8_t *image, uint32_t hud_frame, CallerAddressRegisters saved) {
    draw_hud_row_tiles(image);
    hud_draw_counters(image, hud_frame, saved);
    present_hud_row(image);
    draw_room_to_stage(image, saved);
    stage_to_work(image);
    present_room(image);
}

/* The eight ghost cells the replay makes the puff sound on — cell GHOST_BLOW_ANIM of each of the
 * eight facings. The original spells eight `cmpi.w` in this order; the list is derived from the two
 * `include/gameplay.h` constants that produce it rather than written out again. */
static int demo_record_is_blowing(int16_t tile) {
    for (uint16_t facing = 0; facing < GHOST_FACINGS; facing++)
        if (tile == (int16_t)(facing * GHOST_TILES_PER_FACING + GHOST_BLOW_ANIM))
            return 1;
    return 0;
}

/* One byte of a GHOST.DEM record, read SIGNED: a record may park a sprite off the left of the play
 * area, and `move.b (a0),d0 / ext.w d0` is what lets it. The cursor is stepped in 32 bits. */
static int16_t demo_field(const uint8_t *image, uint32_t cursor, unsigned field) {
    return (int16_t)(int8_t)image[addr_add(cursor, field)];
}

/* ONE GHOST.DEM RECORD — the slice `[0x11992, 0x11acc)`.
 *
 * Six bytes into the six globals the renderer reads, then the frame. THERE IS NO `Vsync` HERE: the
 * replay runs at whatever the renderer costs, which is `../notes/frontend.md` §8's one behavioural
 * trap — a reconstruction that added a frame sync would be changing behaviour, not fixing it. */
void demo_play_record(uint8_t *image, CallerAddressRegisters saved) {
    uint32_t cursor = be32(image + A_demo_cursor);

    set_word(image, A_ghost_x,
             (int16_t)(demo_field(image, cursor, DEMO_FIELD_GHOST_X) * DEMO_SCALE_X));
    set_word(image, A_ghost_y,
             (int16_t)(demo_field(image, cursor, DEMO_FIELD_GHOST_Y) * DEMO_SCALE_Y));
    set_word(image, A_ghost_tile, demo_field(image, cursor, DEMO_FIELD_GHOST_TILE));
    set_word(image, A_bubble_x,
             (int16_t)(demo_field(image, cursor, DEMO_FIELD_BUBBLE_X) * DEMO_SCALE_X));
    set_word(image, A_bubble_y,
             (int16_t)(demo_field(image, cursor, DEMO_FIELD_BUBBLE_Y) * DEMO_SCALE_Y));
    set_word(image, A_bubble_frame, demo_field(image, cursor, DEMO_FIELD_BUBBLE_FRAME));
    wr32(image + A_demo_cursor, addr_add(cursor, DEMO_RECORD_BYTES));

    save_sprite_backgrounds(image, saved);
    draw_sprites(image, saved);
    present_room(image);

    if (demo_record_is_blowing(word_at(image, A_ghost_tile)))
        sound_play(image, sound_fx_definition(SND_FX_PUFF), PUFF_VOICE,
                   menu_volume(image, MENU_AMBIENCE_VOLUME), DEMO_PUFF_NOTE, MENU_SFX_PRIORITY);
    else
        sound_release_voice(image, PUFF_VOICE);

    if (word_at(image, A_bubble_frame) == (int16_t)BUBBLE_POPPED_FRAME)
        sound_play(image, sound_fx_definition(SND_FX_BUBBLE_POP), DEMO_POP_VOICE,
                   menu_volume(image, MENU_LOUD_VOLUME), MENU_SFX_NOTE_ONE_SHOT,
                   MENU_SFX_PRIORITY);

    restore_sprite_backgrounds(image, saved);
    objects_animate_and_draw(image);
    menu_poll_mouse(image, saved);
}

/* ...and the loop around it, entered AT THE TEST as the original's `bra` enters it: the mouse is
 * polled by the record body, so the first pass runs a record whatever the button holds. */
static void demo_replay(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t counter = addr_add(frame, (uint32_t)MENU_FRAME_COUNTER);

    while (!menu_aborted(image)) {
        if (menu_countdown_expired(image, counter))
            return;
        demo_play_record(image, saved);
    }
}

/* The same loop entered AT THE BODY — the slice `[0x11992, 0x11ae6)`, which is what a case that
 * chains several records enters and what the routine's own `bra` skips over on the first pass. */
void demo_replay_from_record(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    demo_play_record(image, saved);
    demo_replay(image, frame, saved);
}

/* `[D]`, phase one — the slice `[0x11930, 0x11ae6)`: room 1 composed, shown and given its ambience,
 * then the GHOST.DEM replay. Every phase of the sequence ends the moment the left mouse button is
 * seen down, and the button is polled by the record body rather than before it, so the replay always
 * plays at least one record. */
void menu_attract_sequence(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t counter = addr_add(frame, (uint32_t)MENU_FRAME_COUNTER);

    set_word(image, A_mouse_buttons, 0);
    set_word(image, A_room_number, DEMO_FIRST_ROOM);
    menu_show_room(image, menu_callee_frame(frame), saved);
    play_room_ambience(image, MENU_AMBIENCE_VOLUME);

    wr32(image + counter, DEMO_RECORDS);
    wr32(image + A_demo_cursor, be32(image + A_demo_base));
    demo_replay(image, frame, saved);
}

/* ONE ROOM of the slideshow — the slice `[0x11b30, 0x11c1c)`: a random room composed, shown and
 * given its ambience, then held for DEMO_SLIDESHOW_FRAMES frames.
 *
 * It is a slice of its own because the loop around it is not affordable in one run: five rooms is
 * the shortest the range allows and each is thirty 25,600-byte presents, which fills the oracle's
 * write ledger. So the body is run once and the loop is the composition (../STATUS.md's residual). */
void menu_attract_slideshow_room(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t counter = addr_add(frame, (uint32_t)MENU_FRAME_COUNTER);

    set_word(image, A_room_number,
             random_divided_and_scaled(image, A_const_demo_room_divisor, A_const_demo_room_scale,
                                       A_const_demo_room_offset, saved, RET_DEMO_ROOM_RANDOM));
    menu_show_room(image, menu_callee_frame(frame), saved);
    play_room_ambience(image, MENU_AMBIENCE_VOLUME);

    wr32(image + counter, DEMO_SLIDESHOW_FRAMES);
    while (!menu_aborted(image)) {
        if (menu_countdown_expired(image, counter))
            break;
        objects_animate_and_draw(image);
        /* THE ONLY FRAME SYNC IN THE WHOLE ATTRACT SEQUENCE, and three of them per frame. It is an
         * XBIOS no-op in the model, so what a reconstruction reproduces is the trampoline's three
         * save slots (../STATUS.md's residual) — three separate calls rather than a loop, because
         * the trampoline files a different return address for each. */
        xbios_vsync(image, saved, RET_DEMO_VSYNC_A);
        xbios_vsync(image, saved, RET_DEMO_VSYNC_B);
        xbios_vsync(image, saved, RET_DEMO_VSYNC_C);
        present_room(image);
        menu_poll_mouse(image, saved);
    }
}

/* `[D]`, phase two — the slice `[0x11ae6, 0x11c34)`: a slideshow of 5..15 random rooms. Both the
 * LENGTH and each ROOM come from `Random()` through the fp package, and both truncate toward zero —
 * which is where `../notes/frontend.md` §2's ranges come from, and why the attract mode can never
 * show room 35. */
void menu_attract_slideshow(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t rooms_left = addr_add(frame, (uint32_t)MENU_FRAME_SLIDESHOW);

    wr16(image + rooms_left,
         (uint16_t)random_divided_and_scaled(image, A_const_demo_length_divisor,
                                             A_const_demo_length_scale, A_const_demo_length_offset,
                                             saved, RET_DEMO_LENGTH_RANDOM));
    while (!menu_aborted(image)) {
        /* The slideshow's own count is the one that is a WORD — `move.w`/`subq.w` rather than the
         * longwords `menu_countdown_expired` reads — and is otherwise the same countdown. */
        int16_t rooms_remaining = (int16_t)be16(image + rooms_left);

        wr16(image + rooms_left, (uint16_t)(rooms_remaining - 1));
        if (rooms_remaining <= 0)
            break;
        menu_attract_slideshow_room(image, frame, saved);
    }
}

/* `[D]`, phase three — the slice `[0x11c34, 0x11ca8)`: the title picture, and then DEMO_TITLE_POLLS
 * mouse polls with nothing else in them at all. A run that arrives here with the button already down
 * skips the picture and falls straight out. */
void menu_attract_title(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t counter = addr_add(frame, (uint32_t)MENU_FRAME_COUNTER);

    if (!menu_aborted(image)) {
        show_presentation(image, saved);
        play_room_ambience(image, MENU_LOUD_VOLUME);
    }

    wr32(image + counter, DEMO_TITLE_POLLS);
    while (!menu_aborted(image)) {
        if (menu_countdown_expired(image, counter))
            break;
        menu_poll_mouse(image, saved);
    }
}

/* `[H]` — the slice `[0x11cba, 0x11d60)`. The table, then the room the player got furthest into as
 * a backdrop, then an idle loop the mouse button ends. */
void menu_hall_of_fame(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t counter = addr_add(frame, (uint32_t)MENU_FRAME_COUNTER);
    uint32_t callee = menu_callee_frame(frame);

    draw_hall_of_fame(image, callee, saved);
    clear_physical_screen(image);
    /* GHOST.DAT's palette, not GHOST.PRE's — the backdrop below is room 0, a GHOST.DAT picture.
     * `move.l -7672(a4)` @ 0x11cc2, the same global the menu installs @ 0x115f2; `show_presentation`
     * is the only reader of `A_pre_palette`. NOTHING IN THE HARNESS CAN TELL THE TWO APART:
     * `Setpalette` is a modeled no-op and its argument push lands in the dropped frame band, so this
     * is read-verified against the disassembly and its surface is an on-target run. */
    xbios_setpalette(image, be32(image + A_dat_palette), saved, RET_HALL_SETPALETTE);
    present_room(image);

    set_word(image, A_room_number, word_at(image, A_max_room_reached));
    draw_hud_row_tiles(image);
    hud_draw_counters(image, callee, saved);
    present_hud_row(image);
    set_word(image, A_room_number, HALL_BACKDROP_ROOM);
    play_room_ambience(image, MENU_LOUD_VOLUME);

    set_word(image, A_mouse_buttons, 0);
    wr32(image + counter, HALL_IDLE_POLLS);
    while (!menu_aborted(image)) {
        if (menu_countdown_expired(image, counter))
            break;
        objects_animate_and_draw(image);
        present_room(image);
        menu_poll_mouse(image, saved);
    }
}

/* THE FOUR KEY READS ARE EACH A SLICE OF THEIR OWN, and the reason is the trap model rather than
 * the routine. Every read in this program is `while (Cconis()) Crawcin(); c = Cnecin();` — a FLUSH
 * followed by a BLOCKING read — and the model's console is one queue that the flush empties, so a
 * run that reaches the `Cnecin` finds nothing there and the call refuses (TRAP_MODEL.md, Phase 13:
 * "a blocking read with nothing staged REFUSES rather than fabricating a key"). On a real machine
 * the key arrives AFTER the flush, which is a moment the staged queue cannot express.
 *
 * So each region ENDS at a `Cnecin` push and the next one begins there, with its own key staged.
 * ../STATUS.md records the model gap; closing it means a second staged stream the flush does not
 * drain, of `os_console_take_key`'s shape.
 */

/* `[G]`, the ask — the slice `[0x11708, 0x11774)`. The two lines are drawn onto the visible screen
 * and the first flush runs; the digit itself is the next slice's. */
void menu_ask_player_count(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    wr16(image + addr_add(frame, (uint32_t)MENU_FRAME_CHOSE), 1);
    set_word(image, A_player_count, 0);
    draw_onto_visible_screen(image, saved, RET_MENU_G_SETSCREEN_PHYS);
    menu_text(image, MENU_PLAYERS_X, MENU_PLAYERS_Y, A_text_one_player, saved);
    menu_text(image, MENU_PLAYERS_X, MENU_PLAYERS_Y + MENU_TEXT_Y_PITCH, A_text_two_players, saved);
    /* The loop's test is made before its body, and `player_count` was just cleared, so the first
     * thing that happens is the flush. */
    drain_console_queue(image, RET_MENU_G_CCONIS, RET_MENU_G_CRAWCIN, saved);
}

/* ...and the read — the slice `[0x11774, 0x117cc)` when a count is chosen, `[0x11774, 0x1175a)`
 * when it is not.
 *
 * IT ANSWERS WHETHER A COUNT WAS CHOSEN rather than looping, for `frame_poll_input`'s reason
 * (`src/gameplay.c`): the loop's next pass begins with a flush and a blocking read, which is where
 * a slice has to end, so the branch is the thing to report. */
int16_t menu_read_player_count(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t digit = addr_add(frame, (uint32_t)MENU_FRAME_DIGIT);

    image[digit] = (uint8_t)menu_take_key(image, RET_MENU_G_CNECIN, saved);
    image[digit] = (uint8_t)(image[digit] - MENU_DIGIT_ZERO);
    if ((int16_t)(int8_t)image[digit] == 1)
        set_word(image, A_player_count, 1);
    else if ((int16_t)(int8_t)image[digit] == (int16_t)PLAYER_COUNT_TWO)
        set_word(image, A_player_count, PLAYER_COUNT_TWO);

    if (word_at(image, A_player_count) == 0)
        return 0;
    draw_into_work_buffer(image, saved, RET_MENU_G_SETSCREEN_BACK);
    return 1;
}

/* `[P]`, the ask — the slice `[0x117de, 0x1183e)`: every score zeroed, one player, the prompt, and
 * the first of the two digits' flushes. */
void menu_ask_practice_level(uint8_t *image, CallerAddressRegisters saved) {
    wr32(image + A_p2_score, 0);
    wr32(image + A_p1_score, 0);
    wr32(image + A_score, 0);
    set_word(image, A_player_count, 1);
    draw_onto_visible_screen(image, saved, RET_MENU_P_SETSCREEN_PHYS);
    menu_text(image, MENU_LEVEL_X, MENU_LEVEL_Y, A_text_enter_level, saved);
    drain_console_queue(image, RET_MENU_P_TENS_CCONIS, RET_MENU_P_TENS_CRAWCIN, saved);
}

/* One digit of `[P]`'s two, filed as a WORD: `move.w d0,…` keeps the low half of the console
 * answer, which is the ASCII — the scancode is in the half thrown away. */
static void menu_take_level_digit(uint8_t *image, uint32_t slot, uint32_t cnecin_return,
                                  CallerAddressRegisters saved) {
    wr16(image + slot, (uint16_t)menu_take_key(image, cnecin_return, saved));
    wr16(image + slot, (uint16_t)(be16(image + slot) - MENU_DIGIT_ZERO));
}

/* The tens digit — the slice `[0x1183e, 0x1186c)`: the read, and then the units digit's flush. */
void menu_read_level_tens(uint8_t *image, CallerAddressRegisters saved) {
    menu_take_level_digit(image, A_practice_grid_row, RET_MENU_P_TENS_CNECIN, saved);
    drain_console_queue(image, RET_MENU_P_UNITS_CCONIS, RET_MENU_P_UNITS_CRAWCIN, saved);
}

/* ...and the units digit with everything that follows it — the slice `[0x1186c, 0x1191e)`: the
 * level assembled, the 0 < n < 36 gate, and the 6 x 6 search that turns the level into a square of
 * the serpentine path (`../notes/frontend.md` §2).
 *
 * THE SEARCH REUSES THE TWO DIGIT GLOBALS AS ITS OWN LOOP COUNTERS, WITH THE ROLES REVERSED — the
 * outer loop counts in `A_practice_grid_col` over grid ROWS — and puts them back the right way
 * round from the frame at the end. */
void menu_read_level_units(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t level_slot = addr_add(frame, (uint32_t)MENU_FRAME_LEVEL);
    uint32_t found_row = addr_add(frame, (uint32_t)MENU_FRAME_FOUND_ROW);
    uint32_t found_col = addr_add(frame, (uint32_t)MENU_FRAME_FOUND_COL);
    int16_t level;

    menu_take_level_digit(image, A_practice_grid_col, RET_MENU_P_UNITS_CNECIN, saved);
    level = (int16_t)(MENU_LEVEL_TENS * (int16_t)be16(image + A_practice_grid_row)
                      + (int16_t)be16(image + A_practice_grid_col));
    wr16(image + level_slot, (uint16_t)level);

    if (level > (int16_t)MENU_LEVEL_LOWEST && level < (int16_t)MENU_LEVEL_ABOVE) {
        set_word(image, A_practice_mode, 1);
        wr16(image + addr_add(frame, (uint32_t)MENU_FRAME_CHOSE), 1);

        for (wr16(image + A_practice_grid_col, 0);
             (int16_t)be16(image + A_practice_grid_col) < (int16_t)ROOM_GRID_ROWS;
             wr16(image + A_practice_grid_col,
                  (uint16_t)((int16_t)be16(image + A_practice_grid_col) + 1))) {
            for (wr16(image + A_practice_grid_row, 0);
                 (int16_t)be16(image + A_practice_grid_row) < (int16_t)ROOM_GRID_COLS;
                 wr16(image + A_practice_grid_row,
                      (uint16_t)((int16_t)be16(image + A_practice_grid_row) + 1))) {
                int16_t row = (int16_t)be16(image + A_practice_grid_col);
                int16_t col = (int16_t)be16(image + A_practice_grid_row);

                if (room_grid_square(image, row, col) != (int16_t)be16(image + level_slot))
                    continue;
                /* The LAST match wins, and no value of `room_grid` repeats — so there is exactly
                 * one and the choice never shows (`../notes/frontend.md` §2). */
                wr16(image + found_row, (uint16_t)row);
                wr16(image + found_col, (uint16_t)col);
            }
        }
        wr16(image + A_practice_grid_col, be16(image + found_col));
        wr16(image + A_practice_grid_row, be16(image + found_row));
    }
    draw_into_work_buffer(image, saved, RET_MENU_P_SETSCREEN_BACK);
}

/* The menu itself, and the flush that ends every pass of it — the slice `[0x115de, 0x116c4)` as the
 * redraw loop re-enters it, and the tail of `[0x115d6, 0x116c4)` the routine is entered at. */
void menu_draw(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    set_word(image, A_practice_mode, 0);
    wr16(image + addr_add(frame, (uint32_t)MENU_FRAME_CHOSE), 0);

    sound_stop_all(image);
    clear_physical_screen(image);
    xbios_setpalette(image, be32(image + A_dat_palette), saved, RET_MENU_SETPALETTE);
    set_word(image, A_mouse_buttons, 0);
    draw_onto_visible_screen(image, saved, RET_MENU_SETSCREEN_PHYS);

    menu_text_pen(image, MENU_TEXT_HEIGHT, MENU_PEN, saved);
    menu_text(image, MENU_TEXT_X, MENU_TEXT_Y_GAME, A_text_menu_game, saved);
    menu_text(image, MENU_TEXT_X, MENU_TEXT_Y_GAME + MENU_TEXT_Y_PITCH, A_text_menu_practice,
              saved);
    menu_text(image, MENU_TEXT_X, MENU_TEXT_Y_GAME + 2 * MENU_TEXT_Y_PITCH, A_text_menu_demo,
              saved);
    menu_text(image, MENU_TEXT_X, MENU_TEXT_Y_GAME + 3 * MENU_TEXT_Y_PITCH, A_text_menu_hall,
              saved);
    drain_console_queue(image, RET_MENU_CCONIS, RET_MENU_CRAWCIN, saved);
}

/* Where `save_hiscores`' own A6 lands when `title_menu_loop` reaches it: three `jsr`s down, through
 * `hiscore_submit_players` (which reserves nothing) and `hiscore_insert_and_save`. */
static uint32_t menu_hiscore_save_frame(uint32_t frame) {
    uint32_t submit = menu_callee_frame(frame);
    uint32_t insert = callee_frame(addr_add(submit, -(uint32_t)SUBMIT_LOCAL_BYTES));

    return callee_frame(addr_add(insert, -(uint32_t)INSERT_LOCAL_BYTES));
}

/* title_menu_loop @ 0x115d6, its opening — the slice `[0x115d6, 0x116c4)`: last game's scores
 * offered to the hall of fame, then the menu drawn and the keyboard flushed. */
void title_menu_open(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    hiscore_submit_players(image, menu_hiscore_save_frame(frame), live);
    menu_draw(image, frame, *live);
}

/* ...and the key that ends a pass — the slice `[0x116c4, 0x11700)`: one blocking read, the logical
 * screen back onto the work buffer, and the fold to upper case.
 *
 * IT ANSWERS THE FOLDED KEY, which is what the four compares after it branch on. The compares
 * themselves write nothing, so the dispatch is read-verified and each arm's own slice is entered at
 * its first instruction. */
int16_t menu_read_key_and_fold(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t key_slot = addr_add(frame, (uint32_t)MENU_FRAME_KEY);

    image[key_slot] = (uint8_t)menu_take_key(image, RET_MENU_CNECIN, saved);
    draw_into_work_buffer(image, saved, RET_MENU_SETSCREEN_BACK);
    /* The fold is a BYTE subtract guarded by a test on the SIGN-EXTENDED byte, so a key with bit 7
     * set is negative and is never folded. */
    if ((int16_t)(int8_t)image[key_slot] > (int16_t)MENU_KEY_LOWER_A)
        image[key_slot] = (uint8_t)(image[key_slot] - MENU_KEY_CASE_BIT);
    return (int16_t)(int8_t)image[key_slot];
}

/* title_menu_loop @ 0x115d6 — the composition, which is READ-VERIFIED for the reason the file's
 * next section gives about `game_top_loop`: every pass of it ends in a blocking console read, and a
 * run that reaches one finds the queue its own flush has just emptied. The order is
 *
 *     title_menu_open                         — the submitter, the menu, the flush
 *     do {
 *         key = menu_read_key_and_fold
 *         'G' -> menu_ask_player_count; while (!menu_read_player_count) flush
 *         'P' -> menu_ask_practice_level; menu_read_level_tens; menu_read_level_units
 *         'D' -> menu_attract_sequence
 *         'H' -> menu_hall_of_fame
 *         if (still nothing chosen) menu_draw            — and read another key
 *     } while (nothing chosen);
 *
 * ...and it returns to `game_top_loop` with `player_count` (and, for `[P]`, the practice square)
 * set. ../STATUS.md carries the residual. */

/* ================================================================================================
 * game_top_loop @ 0x101e6 — the program
 *
 * `main` calls it and never gets it back: it is a `do { … } while (true)` whose body is one whole
 * GAME, and inside that a room loop whose body is one whole ROOM. `../notes/frontend.md` §2 draws
 * the shape; the eleven routines below are its straight-line regions, each verified as a `stop_pc`
 * SLICE entered at its own PC (../STATUS.md carries the `[start, end)` of each).
 *
 * THE COMPOSITION IS READ-VERIFIED and is deliberately not written as a C function: it does not
 * terminate, so there is nothing a case could run and a `for (;;)` here would be code no test could
 * reach. `src/gameplay.c` says the same of `game_frame_update`, for the same reason.
 *
 * THE ORDER THE SLICES RUN IN, which is what that residual is about:
 *
 *     game_top_boot                     — once, ending at the `jsr play_voice`
 *     game_top_boot_tail                — once, from just after it
 *     do {
 *         game_new_game                 — ending at the `jsr title_menu_loop`
 *         title_menu_loop
 *         game_turn_init
 *         do {
 *             game_player_change        — the two-player card and the handover
 *             game_room_setup           — ending at the room loop's first test
 *             do { game_frame_update; game_room_frame_tail; } while (in room, lives left)
 *             level_complete ? game_ending_sequence : game_room_exit
 *             game_end_of_turn
 *         } while (either player is still playing);
 *         game_over_card                — and back to `game_new_game`
 *     } while (true);
 * ============================================================================================= */

/* An empty count, which is the whole of every text card's hold: no `Vsync`, no timer, just
 * iterations. It costs the model nothing (there is no clock) and is transcribed rather than dropped
 * because the counter is image state that outlives the loop. */
static void top_busy_wait(uint8_t *image, uint32_t frame, uint32_t iterations) {
    uint32_t slot = addr_add(frame, (uint32_t)TOP_FRAME_DELAY);

    wr32(image + slot, 0);
    while ((int32_t)be32(image + slot) < (int32_t)iterations)
        wr32(image + slot, be32(image + slot) + 1);
}

/* The whole of `build_sprite_bank` @ 0x132ec: `include/blit.h`'s verified prefix, which paints bank
 * 0 onto the work buffer, and the grab loop above that lifts sixty cells off it. */
void build_sprite_bank(uint8_t *image, CallerAddressRegisters saved) {
    build_sprite_bank_prepare(image);
    build_sprite_bank_grab_cells(image, saved);
}

/* game_top_boot @ 0x101e6 — the slice `[0x101e6, 0x10232)`, which ends at the `jsr play_voice`.
 *
 * IT STOPS THERE BECAUSE `play_voice` RUNS A SECOND PROGRAM. GHOST.LOA is an `ABSFLAG` .PRG read
 * into the BSS as data and entered with a `jsr`; it programs an MFP timer and busy-waits on a flag
 * its own interrupt handler sets, and the kit fires no interrupts (../STATUS.md, "Not
 * reconstructed"). `src/voice.c`'s `play_voice_arm` is the part of it this project has. */
void game_top_boot(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    /* `clr.w -(a7)` then the mode word: the `addr_in` LONG the AES reads spans that pushed zero and
     * the word above it, which is this frame's own — the same shape `save_hiscores`' two calls
     * have, and the reason the mouse form is read out of the image rather than passed as 0. */
    graf_mouse(image, AES_M_OFF, be16(image + addr_add(frame, (uint32_t)TOP_FRAME_DELAY)), *live);
    load_voice_player(image, live);
    load_presentation(image, *live);
    v_clrwk(image, vdi_handle(image), *live);
    os_ikbd_out(IKBD_MOUSE_OFF);
    draw_into_work_buffer(image, *live, RET_TOP_SETSCREEN_BACK);
    show_presentation(image, *live);
}

/* game_top_boot_tail @ 0x10236 — the slice `[0x10236, 0x1024e)`, from just after `play_voice`: the
 * two remaining loaders and the IKBD command that turns mouse reporting back on.
 *
 * IT STOPS SHORT OF THE `c_free` THAT FOLLOWS, which is `game_top_free_voice_buffer` below. */
void game_top_boot_tail(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    uint32_t callee = top_callee_frame(frame);

    load_level_pictures(image, *live);
    load_hiscores(image, callee, *live);
    os_ikbd_out(IKBD_MOUSE_RELATIVE);
}

/* game_top_free_voice_buffer @ 0x1024e — the one call between the two slices, and the only
 * allocation this program ever gives back.
 *
 * READ-VERIFIED, AND NO CASE RUNS IT (../STATUS.md's residual). The block being returned is the one
 * `load_voice_player` allocated, and a slice entered fresh has no such block: `A_voi_buffer` holds
 * the loaded image's zero, so both sides would walk a free list built out of whatever lies below
 * address 0. It is a function of its own rather than a statement inside either neighbour because a
 * slice's candidate runs the WHOLE core it names — a call the oracle stopped before would be made
 * anyway, on that same absent block. `c_free` itself has nine cases in `test_clib.py`. */
void game_top_free_voice_buffer(uint8_t *image) {
    c_free(image, be32(image + A_voi_buffer));
}

/* game_top_boot_arm @ 0x10258 — the slice `[0x10258, 0x1027e)`: the sprite bank grabbed, the sound
 * driver installed and silenced, and the four globals a fresh boot starts from. */
void game_top_boot_arm(uint8_t *image, CallerAddressRegisters *live) {
    build_sprite_bank(image, *live);
    sound_start(image, *live);
    sound_stop_all(image);

    set_word(image, A_bonus_tick, TOP_BONUS_TICK_RELOAD);
    /* The displayed high score is the BEST entry, which is the LAST of the ascending table. */
    wr32(image + A_hi_score,
         be32(image + longword_slot(A_hall_scores, (int16_t)HISCORE_SLOTS - 1)));
    set_word(image, A_room_number, DEMO_FIRST_ROOM);
    wr32(image + A_score, 0);
    load_demo(image, *live);
}

/* game_new_game @ 0x1027e — the slice `[0x1027e, 0x102b0)`, which ends at the `jsr title_menu_loop`:
 * both players back in, a fresh world, and the score offered to the hall of fame. */
void game_new_game(uint8_t *image) {
    set_word(image, A_p2_playing, 1);
    set_word(image, A_p1_playing, 1);
    set_word(image, A_level_complete, 0);
    reset_world_state(image);
    set_word(image, A_bonus_bar, TOP_BONUS_BAR_FULL);
    wr32(image + A_lives, TOP_LIVES_PER_TURN);
    /* A practice game scores nothing, so the candidate it offers is zero. */
    if (word_at(image, A_practice_mode) != 0)
        wr32(image + A_score, 0);
    wr32(image + A_hiscore_candidate, be32(image + A_score));
}

/* One value into both players' copies of a field, which is how every line of `game_turn_init`
 * reads: the live global is set and then handed to player two and player one, in that order. */
static void top_seed_both_players(uint8_t *image, uint32_t p2_slot, uint32_t p1_slot,
                                  int16_t value) {
    set_word(image, p2_slot, value);
    set_word(image, p1_slot, value);
}

static void top_seed_both_players_long(uint8_t *image, uint32_t p2_slot, uint32_t p1_slot,
                                       uint32_t value) {
    wr32(image + p2_slot, value);
    wr32(image + p1_slot, value);
}

/* game_turn_init @ 0x102b4 — the slice `[0x102b4, 0x1037a)`: where the chosen game starts.
 *
 * A practice game starts at the square `[P]` found and shows room 0 until the room loop looks the
 * real one up; an ordinary game starts at (5, 4), which IS room 1 — the first square of the
 * serpentine path (`../notes/frontend.md` §2). */
void game_turn_init(uint8_t *image) {
    set_word(image, A_max_room_reached, 0);
    set_word(image, A_room_number, DEMO_FIRST_ROOM);
    wr32(image + A_score, 0);
    set_word(image, A_entry_dir, TOP_ENTRY_DIR_RIGHT);

    if (word_at(image, A_practice_mode) != 0) {
        set_word(image, A_grid_col, word_at(image, A_practice_grid_col));
        set_word(image, A_grid_row, word_at(image, A_practice_grid_row));
        set_word(image, A_room_number, 0);
    } else {
        set_word(image, A_grid_col, TOP_START_GRID_COL);
        set_word(image, A_grid_row, TOP_START_GRID_ROW);
        set_word(image, A_room_number, DEMO_FIRST_ROOM);
    }

    /* Player TWO holds the turn on entry, so the swap at the top of the first room hands it to
     * player one — which is why a two-player game opens with "PLAYER ONE". */
    set_word(image, A_p1_turn, 0);
    set_word(image, A_p2_turn, 1);

    top_seed_both_players(image, A_p2_max_room, A_p1_max_room, word_at(image, A_max_room_reached));
    top_seed_both_players_long(image, A_p2_lives, A_p1_lives, be32(image + A_lives));
    top_seed_both_players_long(image, A_p2_score, A_p1_score, 0);
    set_word(image, A_bonus_bar, TOP_BONUS_BAR_FULL);
    top_seed_both_players(image, A_p2_bonus_bar, A_p1_bonus_bar, TOP_BONUS_BAR_FULL);
    top_seed_both_players(image, A_p2_grid_col, A_p1_grid_col, word_at(image, A_grid_col));
    top_seed_both_players(image, A_p2_grid_row, A_p1_grid_row, word_at(image, A_grid_row));
    set_word(image, A_deaths_in_room, 0);
    top_seed_both_players(image, A_p2_deaths_in_room, A_p1_deaths_in_room, 0);
    top_seed_both_players(image, A_p2_entry_dir, A_p1_entry_dir, word_at(image, A_entry_dir));

    set_word(image, A_show_player_change,
             word_at(image, A_player_count) == (int16_t)PLAYER_COUNT_TWO ? 1 : 0);
}

/* "G A M E   O V E R" over "P L A Y E R   O N E", drawn onto the visible screen and held. */
static void top_player_out_card(uint8_t *image, uint32_t frame, uint32_t game_over_text,
                                uint32_t player_text, CallerAddressRegisters saved,
                                uint32_t phys_return, uint32_t back_return) {
    draw_onto_visible_screen(image, saved, phys_return);
    menu_text(image, TOP_CARD_X, TOP_CARD_Y_TOP, game_over_text, saved);
    menu_text(image, TOP_CARD_OUT_X, TOP_CARD_Y_BOTTOM, player_text, saved);
    top_busy_wait(image, frame, TOP_CARD_DELAY);
    draw_into_work_buffer(image, saved, back_return);
}

/* One player's turn taken off its shelf: eight globals and the 58-word world block. */
static void top_restore_player(uint8_t *image, const PlayerTurnSlots *slots) {
    set_word(image, A_max_room_reached, word_at(image, slots->max_room));
    wr32(image + A_lives, be32(image + slots->lives));
    wr32(image + A_score, be32(image + slots->score));
    set_word(image, A_bonus_bar, word_at(image, slots->bonus_bar));
    set_word(image, A_grid_col, word_at(image, slots->grid_col));
    set_word(image, A_grid_row, word_at(image, slots->grid_row));
    set_word(image, A_deaths_in_room, word_at(image, slots->deaths_in_room));
    set_word(image, A_entry_dir, word_at(image, slots->entry_dir));
}

/* game_player_change @ 0x1037a — the slice `[0x1037a, 0x105e0)`, and the whole of two-player mode.
 *
 * A one-player game skips all of it. The two-player one announces each player as they run out,
 * hands the turn to the other, puts that player's world back and says whose turn it is. */
void game_player_change(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    if (word_at(image, A_player_count) != (int16_t)PLAYER_COUNT_TWO)
        return;
    if (word_at(image, A_show_player_change) == 0)
        return;

    menu_text_pen(image, MENU_TEXT_HEIGHT, MENU_PEN, saved);

    if (word_at(image, A_p1_turn) != 0 && (int32_t)be32(image + A_p1_lives) < 0)
        top_player_out_card(image, frame, A_text_game_over_p1, A_text_player_one_out, saved,
                            RET_TOP_P1_OUT_PHYS, RET_TOP_P1_OUT_BACK);
    if (word_at(image, A_p2_turn) != 0 && (int32_t)be32(image + A_p2_lives) < 0)
        top_player_out_card(image, frame, A_text_game_over_p2, A_text_player_two_out, saved,
                            RET_TOP_P2_OUT_PHYS, RET_TOP_P2_OUT_BACK);

    /* The handover, which runs whether or not either card was drawn: whoever is up passes the turn
     * to the other, provided the other is still in. */
    if (word_at(image, A_p1_turn) != 0 && word_at(image, A_p2_playing) != 0) {
        set_word(image, A_p1_turn, 0);
        set_word(image, A_p2_turn, 1);
    } else if (word_at(image, A_p2_turn) != 0 && word_at(image, A_p1_playing) != 0) {
        set_word(image, A_p1_turn, 1);
        set_word(image, A_p2_turn, 0);
    }

    draw_onto_visible_screen(image, saved, RET_TOP_TURN_PHYS);
    if (word_at(image, A_p1_turn) != 0 && (int32_t)be32(image + A_p1_lives) > HUD_LIVES_EXHAUSTED) {
        top_restore_player(image, &PLAYER_ONE_SLOTS);
        restore_world(image, PLAYER_ONE_SLOTS.world_block);
        menu_text(image, TOP_CARD_TURN_X, TOP_CARD_TURN_Y, A_text_player_one_up, saved);
    }
    if (word_at(image, A_p2_turn) != 0 && (int32_t)be32(image + A_p2_lives) > HUD_LIVES_EXHAUSTED) {
        top_restore_player(image, &PLAYER_TWO_SLOTS);
        restore_world(image, PLAYER_TWO_SLOTS.world_block);
        menu_text(image, TOP_CARD_TURN_X, TOP_CARD_TURN_Y, A_text_player_two_up, saved);
    }
    top_busy_wait(image, frame, TOP_HANDOVER_DELAY);
    draw_into_work_buffer(image, saved, RET_TOP_TURN_BACK);
}

/* Whether a room is entered from its right-hand side, from the bottom, or from the left. It is only
 * asked in PRACTICE mode, where there is no previous room to have come from, and it is THREE ranges
 * and five singletons in the original — transcribed, because nothing about the numbers derives. */
static int16_t top_practice_entry_dir(int16_t room) {
    static const struct { int16_t first, last; } right_ranges[] = TOP_PRACTICE_RIGHT_RANGES;
    static const int16_t bottom_rooms[] = TOP_PRACTICE_BOTTOM_ROOMS;

    for (unsigned i = 0; i < sizeof right_ranges / sizeof right_ranges[0]; i++)
        if (room >= right_ranges[i].first && room <= right_ranges[i].last)
            return TOP_ENTRY_DIR_RIGHT;
    for (unsigned i = 0; i < sizeof bottom_rooms / sizeof bottom_rooms[0]; i++)
        if (room == bottom_rooms[i])
            return TOP_ENTRY_DIR_BOTTOM;
    return TOP_ENTRY_DIR_LEFT;
}

/* game_room_setup @ 0x105e0 — the slice `[0x105e0, 0x1078a)`: the room the grid square names, the
 * bubble placed at the entry point it is arriving through, and the whole screen composed. */
void game_room_setup(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t callee = top_callee_frame(frame);
    int16_t entry_dir;
    int16_t square;

    set_word(image, A_ambient_sfx_countdown, 1);
    set_word(image, A_room_number,
             room_grid_square(image, word_at(image, A_grid_row), word_at(image, A_grid_col)));

    set_word(image, A_drift_dir_x, 0);
    set_word(image, A_drift_dir_y, 0);
    set_word(image, A_drift_interval, 0);
    set_word(image, A_drift_pulse, 0);
    set_word(image, A_drift_speed, TOP_DRIFT_SPEED_ON_ENTRY);
    set_word(image, A_bubble_alive, 1);

    if (word_at(image, A_practice_mode) != 0)
        set_word(image, A_entry_dir, top_practice_entry_dir(word_at(image, A_room_number)));

    /* The bubble at the entry point of the side it is arriving through, which is the same read
     * `src/gameplay.c`'s respawn makes — one tile index per axis, scaled up to pixels. */
    entry_dir = word_at(image, A_entry_dir);
    set_word(image, A_bubble_x,
             (int16_t)(room_entry_coordinate(image, entry_dir, ROOM_ENTRY_X) * ENTRY_POINT_PIXELS));
    set_word(image, A_bubble_y,
             (int16_t)(room_entry_coordinate(image, entry_dir, ROOM_ENTRY_Y) * ENTRY_POINT_PIXELS));

    draw_room_to_stage(image, saved);
    room_wipe_in(image);
    draw_hud_row_tiles(image);
    hud_draw_counters(image, callee, saved);
    present_hud_row(image);

    /* A room never seen before refills the bonus bar and, if it was entered from BELOW, awards a
     * spare life — which is the only way this game gives one. */
    square = room_grid_square(image, word_at(image, A_grid_row), word_at(image, A_grid_col));
    if (square > word_at(image, A_max_room_reached)) {
        set_word(image, A_show_player_change, 0);
        set_word(image, A_bonus_bar, TOP_BONUS_BAR_FULL);
        hud_bonus_bar_fill(image, callee, saved);
        set_word(image, A_max_room_reached,
                 room_grid_square(image, word_at(image, A_grid_row), word_at(image, A_grid_col)));
        if (word_at(image, A_entry_dir) == (int16_t)TOP_ENTRY_DIR_BOTTOM) {
            int32_t lives = (int32_t)be32(image + A_lives) + 1;

            wr32(image + A_lives, (uint32_t)lives);
            if (lives > TOP_LIVES_MAX)
                wr32(image + A_lives, TOP_LIVES_MAX);
            hud_draw_counters(image, callee, saved);
            present_score_strip(image);
        }
    } else if (word_at(image, A_player_count) == (int16_t)PLAYER_COUNT_TWO
               && word_at(image, A_show_player_change) != 0) {
        set_word(image, A_show_player_change, 0);
        hud_bonus_bar_fill(image, callee, saved);
    }

    set_word(image, A_mouse_buttons, 0);
    set_word(image, A_in_room, 1);
}

/* game_room_frame_tail @ 0x10792 — the slice `[0x10792, 0x108d2)`, entered where
 * `game_frame_update` returns: the bonus bar's tick, the four ways out of a room, the win test, the
 * room's own ambience and the five calls that put the frame on screen. */
void game_room_frame_tail(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t callee = top_callee_frame(frame);
    int16_t tick = word_at(image, A_bonus_tick);

    set_word(image, A_bonus_tick, (int16_t)(tick - 1));
    if (tick < 1) {
        int16_t bar;

        set_word(image, A_bonus_tick, TOP_BONUS_TICK_RELOAD);
        bar = (int16_t)(word_at(image, A_bonus_bar) - 1);
        set_word(image, A_bonus_bar, bar);
        if (bar < (int16_t)TOP_BONUS_BAR_FLOOR)
            set_word(image, A_bonus_bar, TOP_BONUS_BAR_FLOOR);
        hud_bonus_bar_shrink(image, callee, 1, saved);
    }

    /* The four exits, each of which steps one square of the grid and says which side of the NEXT
     * room the bubble will arrive through. All four tests are made, so a bubble that has left
     * through two of them at once takes the last one's exit. */
    if (word_at(image, A_bubble_x) > (int16_t)TOP_EXIT_RIGHT) {
        set_word(image, A_in_room, 0);
        set_word(image, A_entry_dir, TOP_ENTRY_DIR_LEFT);
        set_word(image, A_grid_col, (int16_t)(word_at(image, A_grid_col) + 1));
    }
    if (word_at(image, A_bubble_x) < 0) {
        set_word(image, A_in_room, 0);
        set_word(image, A_entry_dir, TOP_ENTRY_DIR_RIGHT);
        set_word(image, A_grid_col, (int16_t)(word_at(image, A_grid_col) - 1));
    }
    if (word_at(image, A_bubble_y) > (int16_t)TOP_EXIT_BOTTOM) {
        set_word(image, A_in_room, 0);
        set_word(image, A_entry_dir, TOP_ENTRY_DIR_TOP);
        set_word(image, A_grid_row, (int16_t)(word_at(image, A_grid_row) + 1));
    }
    if (word_at(image, A_bubble_y) < 0) {
        set_word(image, A_in_room, 0);
        set_word(image, A_entry_dir, TOP_ENTRY_DIR_BOTTOM);
        set_word(image, A_grid_row, (int16_t)(word_at(image, A_grid_row) - 1));
    }

    /* ...and the fifth way out, which is winning: the last room's own right-hand door. */
    if (word_at(image, A_room_number) == (int16_t)TOP_ROOM_LAST
        && word_at(image, A_bubble_x) > (int16_t)TOP_WIN_X) {
        set_word(image, A_level_complete, 1);
        set_word(image, A_in_room, 0);
    } else {
        set_word(image, A_level_complete, 0);
    }

    if (word_at(image, A_in_room) == 0)
        return;
    if ((int32_t)be32(image + A_lives) <= HUD_LIVES_EXHAUSTED)
        return;

    /* The room's ambience, re-rolled every 20..69 frames (`../notes/frontend.md` §6). */
    {
        int16_t countdown = word_at(image, A_ambient_sfx_countdown);

        set_word(image, A_ambient_sfx_countdown, (int16_t)(countdown - 1));
        if (countdown < 0) {
            set_word(image, A_ambient_sfx_countdown,
                     random_scaled(image, A_const_ambient_scale, A_const_ambient_offset,
                                   saved, RET_TOP_AMBIENCE_RANDOM));
            play_room_ambience(image, TOP_AMBIENCE_VOLUME);
        }
    }
    animation_frame(image, saved);
}

/* The two ghost cells the end-of-room walks alternate between, flipped every other frame by a hold
 * counter in the frame. Both animations use it and neither uses anything else. */
static void top_flip_walk_cell(uint8_t *image, uint32_t frame) {
    uint32_t hold = addr_add(frame, (uint32_t)TOP_FRAME_ANIM_HOLD);
    int32_t remaining = (int32_t)be32(image + hold);

    wr32(image + hold, (uint32_t)(remaining - 1));
    if (remaining != 0)
        return;
    wr32(image + hold, TOP_ENDING_HOLD);
    set_word(image, A_ghost_tile,
             word_at(image, A_ghost_tile) == (int16_t)TOP_ENDING_TILE_LOW
                 ? (int16_t)TOP_ENDING_TILE_HIGH : (int16_t)TOP_ENDING_TILE_LOW);
}

/* The bubble's sparkle, advanced once per animation frame — the same wrap `game_frame_update`'s
 * first slice makes, spelt again here because this animation runs without it. */
static void top_advance_bubble_cell(uint8_t *image) {
    int16_t previous = word_at(image, A_bubble_frame);

    set_word(image, A_bubble_frame, (int16_t)(previous + 1));
    if (previous > (int16_t)TOP_ENDING_ANIM_LAST)
        set_word(image, A_bubble_frame, TOP_ENDING_ANIM_FIRST);
}

/* One room-35 door object retired: given its "open" tile, and then the -1 the object animator
 * skips. Two of them make the door. */
static uint32_t top_ending_object(uint16_t slot) {
    return A_object_table + TOP_ROOM_LAST * OBJECT_ROOM_STRIDE + slot * OBJECT_STRIDE
           + OBJECT_TILE;
}

/* The score tally that empties the bonus bar, which both end-of-room paths run: the bar is stepped
 * down five columns at a time and each step is worth points and one note of a rising glissando. */
static void top_tally_step_sound(uint8_t *image) {
    int16_t note = (int16_t)(TOP_TALLY_NOTE_BASE
                             - word_at(image, A_bonus_bar) / TOP_TALLY_NOTE_DIVISOR);

    sound_play(image, sound_fx_definition(SND_FX_BONUS_TALLY), TOP_TALLY_VOICE,
               menu_volume(image, TOP_TALLY_VOLUME), note, TOP_TALLY_PRIORITY);
}

static void top_bank_score(uint8_t *image, uint32_t callee, CallerAddressRegisters saved) {
    if ((int32_t)be32(image + A_score) > (int32_t)be32(image + A_hi_score))
        wr32(image + A_hi_score, be32(image + A_score));
    hud_draw_counters(image, callee, saved);
    present_score_strip(image);
}

/* game_ending_sequence @ 0x108ec — the slice `[0x108ec, 0x10ce0)`: the whole of winning. The ghost
 * walks right to the door, the door opens, the ghost falls through it, and the bar is cashed in. */
void game_ending_sequence(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t callee = top_callee_frame(frame);

    sound_release_voice(image, PUFF_VOICE);
    sound_play(image, sound_fx_definition(SND_FX_LEVEL_CLEAR), TOP_ENDING_VOICE,
               menu_volume(image, TOP_ENDING_VOLUME), MENU_SFX_NOTE_ONE_SHOT, TOP_ENDING_PRIORITY);
    wr32(image + addr_add(frame, (uint32_t)TOP_FRAME_ANIM_HOLD), TOP_ENDING_HOLD);
    xbios_setcolor(image, TOP_ENDING_PEN, TOP_ENDING_COLOUR, saved, RET_TOP_ENDING_SETCOLOR);

    /* 1. Right to the door, the ghost's own cell walking down five at a time until it is inside
     *    the two-cell walk's range and the flip-flop takes over. */
    for (;;) {
        /* The step is made BEFORE the test and on the value the test then uses, so the walk ends
         * one past `TOP_ENDING_WALK_TO` rather than at it. */
        int16_t x = word_at(image, A_bubble_x);

        set_word(image, A_bubble_x, (int16_t)(x + 1));
        if (x >= (int16_t)TOP_ENDING_WALK_TO)
            break;
        top_advance_bubble_cell(image);
        if (word_at(image, A_ghost_tile) > (int16_t)TOP_ENDING_TILE_FLOOR
            && word_at(image, A_ghost_tile) < (int16_t)TOP_ENDING_TILE_CEILING)
            set_word(image, A_ghost_tile,
                     (int16_t)(word_at(image, A_ghost_tile) - TOP_ENDING_TILE_STEP));
        else
            top_flip_walk_cell(image, frame);
        animation_frame(image, saved);
    }

    /* 2. The door, which is two object slots given their open tiles. */
    set_word(image, top_ending_object(TOP_ENDING_OBJECT_A), TOP_ENDING_TILE_A);
    set_word(image, top_ending_object(TOP_ENDING_OBJECT_B), TOP_ENDING_TILE_B);

    /* 3. ...and down through it. */
    wr32(image + addr_add(frame, (uint32_t)TOP_FRAME_ANIM_HOLD), TOP_ENDING_HOLD);
    for (;;) {
        int16_t y = word_at(image, A_bubble_y);

        set_word(image, A_bubble_y, (int16_t)(y - 1));
        if (y <= (int16_t)TOP_ENDING_FALL_TO)
            break;
        top_advance_bubble_cell(image);
        top_flip_walk_cell(image, frame);
        animation_frame(image, saved);
    }
    set_word(image, top_ending_object(TOP_ENDING_OBJECT_A), (int16_t)TOP_OBJECT_RETIRED);
    set_word(image, top_ending_object(TOP_ENDING_OBJECT_B), (int16_t)TOP_OBJECT_RETIRED);

    /* 4. The bar cashed in at TOP_BONUS_PER_STEP a step. */
    while (word_at(image, A_bonus_bar) > (int16_t)TOP_BONUS_BAR_FLOOR) {
        hud_bonus_bar_shrink(image, callee, TOP_BONUS_STEP, saved);
        top_tally_step_sound(image);
        set_word(image, A_bonus_bar, (int16_t)(word_at(image, A_bonus_bar) - TOP_BONUS_STEP));
        wr32(image + A_score, be32(image + A_score) + TOP_BONUS_PER_STEP);
        top_bank_score(image, callee, saved);
    }
    sound_stop_voice(image, TOP_TALLY_VOICE);
    hud_bonus_bar_shrink(image, callee, TOP_BONUS_STEP, saved);

    /* 5. ...and the winner's turn is over. In two-player mode the turn is parked and the other
     *    player carries on; in one-player mode the game ends. */
    if (word_at(image, A_player_count) == (int16_t)PLAYER_COUNT_TWO) {
        const PlayerTurnSlots *slots = word_at(image, A_p1_turn) != 0 ? &PLAYER_ONE_SLOTS
                                                                     : &PLAYER_TWO_SLOTS;
        uint32_t playing = word_at(image, A_p1_turn) != 0 ? A_p1_playing : A_p2_playing;

        set_word(image, A_show_player_change, 1);
        set_word(image, playing, 0);
        set_word(image, slots->max_room, word_at(image, A_max_room_reached));
        wr32(image + slots->score, be32(image + A_score));
        return;
    }
    set_word(image, A_p1_playing, 0);
    set_word(image, A_p2_playing, 0);
}

/* game_room_exit @ 0x10af8 — the slice `[0x10af8, 0x10ce0)`: leaving a room the ordinary way. The
 * bubble is popped and parked, the room's own bonus is awarded the FIRST time it is left, and the
 * bar is cashed in at half the winning rate. */
void game_room_exit(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t callee = top_callee_frame(frame);

    /* A practice game is over the moment its one room is left. */
    if (word_at(image, A_practice_mode) != 0)
        wr32(image + A_lives, (uint32_t)HUD_LIVES_EXHAUSTED);
    if ((int32_t)be32(image + A_lives) <= HUD_LIVES_EXHAUSTED)
        return;
    if (word_at(image, A_show_player_change) != 0)
        return;

    sound_release_voice(image, PUFF_VOICE);
    sound_play(image, sound_fx_definition(SND_FX_ROOM_EXIT), TOP_ENDING_VOICE,
               menu_volume(image, TOP_TALLY_VOLUME), MENU_SFX_NOTE_ONE_SHOT, TOP_ENDING_PRIORITY);

    set_word(image, A_bubble_frame, TOP_ENDING_POP_FRAME);
    set_word(image, A_bubble_x, TOP_ENDING_PARK_X);
    set_word(image, A_bubble_y, TOP_ENDING_PARK_Y);
    while (word_at(image, A_ghost_tile) > (int16_t)TOP_ENDING_TILE_FLOOR) {
        set_word(image, A_ghost_tile,
                 (int16_t)(word_at(image, A_ghost_tile) - TOP_ENDING_TILE_STEP));
        animation_frame(image, saved);
    }

    /* TOP_ROOM_BONUS for the room, less TOP_DEATH_PENALTY for every death in it — computed in a
     * WORD and only then widened, so a room left after eleven deaths would score negative. */
    if (room_grid_square(image, word_at(image, A_grid_row), word_at(image, A_grid_col))
        > word_at(image, A_max_room_reached)) {
        int16_t bonus = (int16_t)(TOP_ROOM_BONUS
                                  - word_at(image, A_deaths_in_room) * TOP_DEATH_PENALTY);

        wr32(image + A_score, be32(image + A_score) + sign_ext16((uint32_t)bonus));
        set_word(image, A_deaths_in_room, 0);
        top_bank_score(image, callee, saved);
    }

    xbios_setcolor(image, TOP_ENDING_PEN, TOP_ENDING_COLOUR, saved, RET_TOP_EXIT_SETCOLOR);
    wr32(image + addr_add(frame, (uint32_t)TOP_FRAME_ANIM_HOLD), TOP_ENDING_HOLD);
    set_word(image, A_ghost_tile, TOP_ENDING_TILE_LOW);
    for (set_word(image, A_seq_counter, 0);
         word_at(image, A_seq_counter) < (int16_t)TOP_ENDING_FALL_FRAMES;
         set_word(image, A_seq_counter, (int16_t)(word_at(image, A_seq_counter) + 1))) {
        top_flip_walk_cell(image, frame);
        animation_frame(image, saved);
    }

    while (word_at(image, A_bonus_bar) > (int16_t)TOP_BONUS_BAR_FLOOR) {
        hud_bonus_bar_shrink(image, callee, TOP_BONUS_STEP, saved);
        set_word(image, A_bonus_bar, (int16_t)(word_at(image, A_bonus_bar) - TOP_BONUS_STEP));
        /* ...and the tally pays only in a room that has not been cashed in before. */
        if (room_grid_square(image, word_at(image, A_grid_row), word_at(image, A_grid_col))
            > word_at(image, A_max_room_reached)) {
            wr32(image + A_score, be32(image + A_score) + TOP_BONUS_PER_STEP_EXIT);
            top_tally_step_sound(image);
            top_bank_score(image, callee, saved);
        }
    }
    sound_stop_voice(image, TOP_TALLY_VOICE);
    hud_bonus_bar_shrink(image, callee, TOP_BONUS_STEP, saved);
}

/* game_end_of_turn @ 0x10ce0 — the slice `[0x10ce0, 0x10d34)`: who, if anyone, is still playing. */
void game_end_of_turn(uint8_t *image) {
    if (word_at(image, A_player_count) == (int16_t)PLAYER_COUNT_TWO) {
        if ((int32_t)be32(image + A_p1_lives) < 0 && word_at(image, A_p1_turn) != 0) {
            set_word(image, A_show_player_change, 1);
            set_word(image, A_p1_playing, 0);
        }
        if ((int32_t)be32(image + A_p2_lives) < 0 && word_at(image, A_p2_turn) != 0) {
            set_word(image, A_show_player_change, 1);
            set_word(image, A_p2_playing, 0);
        }
        return;
    }
    if ((int32_t)be32(image + A_lives) < 0) {
        set_word(image, A_p1_playing, 0);
        set_word(image, A_p2_playing, 0);
    }
}

/* game_over_card @ 0x10d44 — the slice `[0x10d44, 0x1027e)`, which ends at the branch back to the
 * top of the game loop. ONE-PLAYER, NON-PRACTICE games only: a two-player game has already shown
 * each player their own card, and a practice game shows none. */
void game_over_card(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    if (word_at(image, A_player_count) != 1)
        return;
    if (word_at(image, A_practice_mode) != 0)
        return;

    menu_text_pen(image, MENU_TEXT_HEIGHT, MENU_PEN, saved);
    draw_onto_visible_screen(image, saved, RET_TOP_GAME_OVER_PHYS);
    menu_text(image, TOP_CARD_X, TOP_CARD_TURN_Y, A_text_game_over, saved);
    top_busy_wait(image, frame, TOP_CARD_DELAY);
    draw_into_work_buffer(image, saved, RET_TOP_GAME_OVER_BACK);
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

void g_build_sprite_bank(uint8_t *image, uint32_t a1, uint32_t a2) {
    build_sprite_bank(image, caller_registers(a1, a2));
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

void g_title_menu_open(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    title_menu_open(image, frame, &live);
}

void g_menu_draw(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_draw(image, frame, caller_registers(a1, a2));
}

int32_t g_menu_read_key_and_fold(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    return menu_read_key_and_fold(image, frame, caller_registers(a1, a2));
}

void g_menu_ask_player_count(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_ask_player_count(image, frame, caller_registers(a1, a2));
}

int32_t g_menu_read_player_count(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    return menu_read_player_count(image, frame, caller_registers(a1, a2));
}

void g_menu_ask_practice_level(uint8_t *image, uint32_t a1, uint32_t a2) {
    menu_ask_practice_level(image, caller_registers(a1, a2));
}

void g_menu_read_level_tens(uint8_t *image, uint32_t a1, uint32_t a2) {
    menu_read_level_tens(image, caller_registers(a1, a2));
}

void g_menu_read_level_units(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_read_level_units(image, frame, caller_registers(a1, a2));
}

void g_demo_play_record(uint8_t *image, uint32_t a1, uint32_t a2) {
    demo_play_record(image, caller_registers(a1, a2));
}

void g_demo_replay_from_record(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    demo_replay_from_record(image, frame, caller_registers(a1, a2));
}

void g_menu_attract_sequence(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_attract_sequence(image, frame, caller_registers(a1, a2));
}

void g_menu_attract_slideshow(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_attract_slideshow(image, frame, caller_registers(a1, a2));
}

void g_menu_attract_slideshow_room(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_attract_slideshow_room(image, frame, caller_registers(a1, a2));
}

void g_menu_attract_title(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_attract_title(image, frame, caller_registers(a1, a2));
}

void g_menu_hall_of_fame(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    menu_hall_of_fame(image, frame, caller_registers(a1, a2));
}

void g_game_top_boot(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    game_top_boot(image, frame, &live);
}

void g_game_top_boot_tail(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    game_top_boot_tail(image, frame, &live);
}

void g_game_top_boot_arm(uint8_t *image, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    game_top_boot_arm(image, &live);
}

void g_game_new_game(uint8_t *image) { game_new_game(image); }
void g_game_turn_init(uint8_t *image) { game_turn_init(image); }
void g_game_end_of_turn(uint8_t *image) { game_end_of_turn(image); }

void g_game_player_change(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_player_change(image, frame, caller_registers(a1, a2));
}

void g_game_room_setup(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_room_setup(image, frame, caller_registers(a1, a2));
}

void g_game_room_frame_tail(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_room_frame_tail(image, frame, caller_registers(a1, a2));
}

void g_game_ending_sequence(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_ending_sequence(image, frame, caller_registers(a1, a2));
}

void g_game_room_exit(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_room_exit(image, frame, caller_registers(a1, a2));
}

void g_game_over_card(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    game_over_card(image, frame, caller_registers(a1, a2));
}
