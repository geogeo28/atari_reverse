/* gsx.c — the AES's VDI binding (`aes/gsx.h`): gsx2 and gemgsxif's atoms, hand 68000 in the ROM, ported over their own
 * order. Each wrapper stores what its call carries, makes the call through gsx_ncode, and leaves the parameter block's
 * PTSIN at the AES's own ptsin again — the folded fragment $fe8bb6/$fe8bba (`gsx_call`, `aes/gsx.h`).
 *
 * The cores marked TRANSCRIBED_CORE ship as the ROM's own instructions (`gsx.S`): their C measures over Tier 3's bar on
 * its own cycles and Tier 1 proves it here. The wrappers and gsx_moff make Line-F calls in the ROM, so they ship as C.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/gsx.h"
#include "vdi/vdi.h"

/* The counts the table-driven wrappers' calls are made with: the 3-byte rows of the ROM's table at $fe8bdc (words,
 * points, opcode), spelt here as the values they are (a call carrying none uses `aes/gsx.h`'s GSX_NO_*). */
#define CLIP_POINTS            2      /* $fe8be2: vs_clip, 1 word, 2 points */
#define CLIP_WORDS             1
#define HEIGHT_POINTS          1      /* $fe8be5: vst_height, 0 words, 1 point */
#define RECFL_POINTS           2      /* $fe8be8: vr_recfl, 1 word, 2 points */
#define RECFL_WORDS            1
#define CPYFM_POINTS           4      /* $fe8beb / $fe8bee: vro_cpyfm 1 word, vrt_cpyfm 3 words, 4 points each */
#define VRO_CPYFM_WORDS        1
#define VRT_CPYFM_WORDS        3
#define WIDTH_POINTS           1      /* $fe8bf1: vsl_width, 0 words, 1 point */

/* $fecb5a — gsx2: the block's contrl pointer stored, then the trap. */
TRANSCRIBED_CORE
uint16_t aes_gsx2(uint8_t *image)
{
    wr32(image + AES_GSX_PB_CONTRL, AES_GSX_CONTRL);
    return gsx_trap(image);
}

/* $fe87d2 — gsx_ncode: contrl[0] and [1] as the one longword the frame holds them in, contrl[3], the AES's handle
 * into contrl[6]; then `jmp gsx2`. */
TRANSCRIBED_CORE
uint16_t aes_gsx_ncode(uint8_t *image, int16_t opcode, int16_t n_ptsin, int16_t n_intin)
{
    uint8_t *contrl = image + AES_GSX_CONTRL;       /* `lea $c7e0,a1`, every store made through it */

    REGISTER_BARRIER(contrl, REGISTER_BARRIER_ADDRESS_CLASS);
    wr16(contrl + CONTRL_OPCODE, (uint16_t)opcode);
    wr16(contrl + CONTRL_N_PTSIN, (uint16_t)n_ptsin);
    wr16(contrl + CONTRL_N_INTIN, (uint16_t)n_intin);
    wr16(contrl + CONTRL_HANDLE, be16(image + AES_GL_HANDLE));
    return aes_gsx2(image);
}

/* $fe87f0 — gsx_1code: intin[0] first, then gsx_ncode(opcode, 0, 1). */
TRANSCRIBED_CORE
uint16_t aes_gsx_1code(uint8_t *image, int16_t opcode, int16_t value)
{
    wr16(image + GSX_INTIN_WORD(0), (uint16_t)value);
    return aes_gsx_ncode(image, opcode, GSX_NO_POINTS, GSX_ONE_WORD);
}

/* $fe8ba2 — contrl[7..10]: the two pointers a call carries (MFDBs, or a vector and its old value). */
static void carry_pointers(uint8_t *image, uint32_t first, uint32_t second)
{
    wr32(image + AES_GSX_CONTRL_PTR, first);
    wr32(image + AES_GSX_CONTRL_PTR2, second);
}

/* gsx_moff's first level of the nest ($fe8a7c..): v_hide_c, the AES's flag cleared, the nest counted after the call.
 * Its own function, never inlined, because GCC does not shrink-wrap: inlined, the call's frame is built on the open
 * nest's path too (Tier 3, the open nest's own cycles: 94 inlined, 76 apart, the ROM's 62). Not `hide_cursor`: a
 * static's name must be one node of Tier 3's call graph (`vet_no_row_is_ambiguous`). */
static void __attribute__((noinline)) gsx_moff_hide(uint8_t *image)
{
    gsx_call(image, VDI_ROM_V_HIDE_C_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr16(image + AES_GL_MOUSE_SHOWN, GSX_MOUSE_HIDDEN);
    wr16(image + AES_GL_MOFF, (uint16_t)(be16(image + AES_GL_MOFF) + 1));
}

/* $fe8a72 — gsx_moff: the cursor hidden on the first level of the nest, the nest counted on every call. The nest
 * already open returns at once with no frame (the hide path is `gsx_moff_hide`): the word counted is the one just
 * tested, which is the ROM's `addq.w` over it with nothing run between. */
void aes_gsx_moff(uint8_t *image)
{
    uint8_t *nest = image + AES_GL_MOFF;     /* the ROM's `tst.w` and `addq.w` of one absolute word: the barrier
                                                keeps it ONE address register, formed once (84 cycles without, 76) */
    uint16_t depth;

    REGISTER_BARRIER(nest, REGISTER_BARRIER_ADDRESS_CLASS);
    depth = be16(nest);
    if (depth) {
        wr16(nest, (uint16_t)(depth + 1));
        return;
    }
    gsx_moff_hide(image);
}

/* $fe8a8e — gsx_mon: the nest counted down (a WORD `sub.w`: 0 goes to $ffff, not to zero), and the cursor shown at
 * once when it reaches zero. */
TRANSCRIBED_CORE
void aes_gsx_mon(uint8_t *image)
{
    uint16_t nest = (uint16_t)(be16(image + AES_GL_MOFF) - 1);

    wr16(image + AES_GL_MOFF, nest);
    if (nest)
        return;
    aes_gsx_1code(image, VDI_ROM_V_SHOW_C_OPCODE, GSX_SHOW_COUNTED);
    wr16(image + AES_GL_MOUSE_SHOWN, GSX_MOUSE_SHOWN);
}

/* $fe8afa — v_pline: the caller's points for the one call. */
uint16_t aes_v_pline(uint8_t *image, int16_t count, uint32_t points)
{
    wr32(image + AES_GSX_PB_PTSIN, points);
    return gsx_call(image, VDI_ROM_V_PLINE_OPCODE, count, GSX_NO_WORDS);
}

/* $fe8b0e — vs_clip: the flag into intin[0], the corners' points for the call. */
uint16_t aes_vs_clip(uint8_t *image, int16_t flag, uint32_t points)
{
    wr16(image + GSX_INTIN_WORD(0), (uint16_t)flag);
    wr32(image + AES_GSX_PB_PTSIN, points);
    return gsx_call(image, VDI_ROM_VS_CLIP_OPCODE, CLIP_POINTS, CLIP_WORDS);
}

/* $fe8b22 — vst_height: ptsin = (0, height), and ptsout's four words out through the four pointers, each word READ
 * after the store before it — so a pointer into ptsout changes what the next one is handed. */
uint16_t aes_vst_height(uint8_t *image, int16_t height, uint32_t char_width, uint32_t char_height,
                        uint32_t cell_width, uint32_t cell_height)
{
    const uint8_t *ptsout = image + AES_GSX_PTSOUT;  /* `lea $9abc,a0`, every answer read through it */
    uint16_t answer;

    wr16(image + GSX_PTSIN_WORD(0), 0);
    wr16(image + GSX_PTSIN_WORD(1), (uint16_t)height);
    answer = gsx_call(image, VDI_ROM_VST_HEIGHT_OPCODE, HEIGHT_POINTS, GSX_NO_WORDS);
    set_bus_word(image, char_width, be16(ptsout));
    set_bus_word(image, char_height, be16(ptsout + VDI_WORD_BYTES));
    set_bus_word(image, cell_width, be16(ptsout + 2 * VDI_WORD_BYTES));
    set_bus_word(image, cell_height, be16(ptsout + 3 * VDI_WORD_BYTES));
    return answer;
}

/* $fe8b50 — vr_recfl: the corners' points, the MFDB into contrl[7..8]. */
uint16_t aes_vr_recfl(uint8_t *image, uint32_t points, uint32_t mfdb)
{
    wr32(image + AES_GSX_PB_PTSIN, points);
    wr32(image + AES_GSX_CONTRL_PTR, mfdb);
    return gsx_call(image, VDI_ROM_VR_RECFL_OPCODE, RECFL_POINTS, RECFL_WORDS);
}

/* $fe8b60 — vro_cpyfm: the mode, the two rectangles' points, the two MFDBs. */
uint16_t aes_vro_cpyfm(uint8_t *image, int16_t mode, uint32_t points, uint32_t source, uint32_t destination)
{
    wr16(image + GSX_INTIN_WORD(0), (uint16_t)mode);
    wr32(image + AES_GSX_PB_PTSIN, points);
    carry_pointers(image, source, destination);
    return gsx_call(image, VDI_ROM_VRO_CPYFM_OPCODE, CPYFM_POINTS, VRO_CPYFM_WORDS);
}

/* $fe8b72 — vrt_cpyfm: vro_cpyfm's, and the two colours into intin[1..2] after the MFDBs. */
uint16_t aes_vrt_cpyfm(uint8_t *image, int16_t mode, uint32_t points, uint32_t source, uint32_t destination,
                       int16_t foreground, int16_t background)
{
    wr16(image + GSX_INTIN_WORD(0), (uint16_t)mode);
    wr32(image + AES_GSX_PB_PTSIN, points);
    carry_pointers(image, source, destination);
    wr16(image + GSX_INTIN_WORD(1), (uint16_t)foreground);
    wr16(image + GSX_INTIN_WORD(2), (uint16_t)background);
    return gsx_call(image, VDI_ROM_VRT_CPYFM_OPCODE, CPYFM_POINTS, VRT_CPYFM_WORDS);
}

/* $fe8b88 — vrn_trnfm: the two MFDBs, nothing else. */
uint16_t aes_vrn_trnfm(uint8_t *image, uint32_t source, uint32_t destination)
{
    carry_pointers(image, source, destination);
    return gsx_call(image, VDI_ROM_VR_TRNFM_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
}

/* $fe8b92 — vsl_width: ptsin = (width, 0). */
uint16_t aes_vsl_width(uint8_t *image, int16_t width)
{
    wr16(image + GSX_PTSIN_WORD(0), (uint16_t)width);
    wr16(image + GSX_PTSIN_WORD(1), 0);
    return gsx_call(image, VDI_ROM_VSL_WIDTH_OPCODE, WIDTH_POINTS, GSX_NO_WORDS);
}

/* $fda992 — gsx_fix: the MFDB at `mfdb` set up for `address` — 0 the screen (its size out of the workstation's
 * work_out, its planes the AES's), anything else a one-plane form `bytes_across` wide. The address is stored FIRST and
 * the workstation's words read after it, word by word between the stores — an MFDB laid over gl_ws reads what it just
 * wrote. Every width is a WORD (`lsl.w`, `addq.w`, `lsr.w`), so they wrap. */
TRANSCRIBED_CORE
void aes_gsx_fix(uint8_t *image, uint32_t mfdb, uint32_t address, int16_t bytes_across, int16_t height)
{
    uint16_t width;

    set_bus_long(image, mfdb + MFDB_ADDR, address);
    if (!address) {
        width = (uint16_t)(be16(image + GSX_WS_WORD(GSX_WS_XRES)) + 1);
        set_bus_word(image, mfdb + MFDB_W, width);
        set_bus_word(image, mfdb + MFDB_H, (uint16_t)(be16(image + GSX_WS_WORD(GSX_WS_YRES)) + 1));
        set_bus_word(image, mfdb + MFDB_WDWIDTH, (uint16_t)(width >> GSX_PIXELS_PER_WORD_SHIFT));
        set_bus_word(image, mfdb + MFDB_STAND, MFDB_FORMAT_DEVICE);
        set_bus_word(image, mfdb + MFDB_NPLANES, be16(image + AES_GL_NPLANES));
        return;
    }
    width = (uint16_t)((uint16_t)bytes_across << GSX_PIXELS_PER_BYTE_SHIFT);
    set_bus_word(image, mfdb + MFDB_W, width);
    set_bus_word(image, mfdb + MFDB_H, (uint16_t)height);
    set_bus_word(image, mfdb + MFDB_WDWIDTH, (uint16_t)(width >> GSX_PIXELS_PER_WORD_SHIFT));
    set_bus_word(image, mfdb + MFDB_STAND, MFDB_FORMAT_DEVICE);
    set_bus_word(image, mfdb + MFDB_NPLANES, GSX_FORM_PLANES);
}
