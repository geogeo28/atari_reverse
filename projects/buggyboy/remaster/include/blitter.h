/* blitter.h — the Atari STE/Mega-ST hardware BLiTTER (0xFFFF8A00) register block + a small masked-blit
 * driver. Used ONLY by the STE build target (GAME_STE, render/atari/build_game.sh); the stock ST binary
 * never sees this file. The blitter emits the SAME framebuffer bytes as the 68000 RMW engines it
 * replaces, so the byte-compare pins still hold — that is the whole point of the STE build (PERF30 C4).
 *
 * SUPERVISOR ONLY: the 0xFFFF8Axx I/O page bus-errors from user mode. Every register access below runs
 * from a Supexec excursion or the VBL (already supervisor) — see src/blitter.c and game_main.c.
 *
 * Register map (STE hardware, big-endian; the byte registers are the control tail):
 *   0x8A00..0x8A1E  halftone RAM        16 words       (HOP source when HOP selects halftone)
 *   0x8A20          src_x_inc  word (signed)  0x8A22 src_y_inc word (signed)   0x8A24 src_addr long
 *   0x8A28/2A/2C    endmask1/2/3  words        (first / middle / last dst word of each line)
 *   0x8A2E          dst_x_inc  word (signed)  0x8A30 dst_y_inc word (signed)   0x8A32 dst_addr long
 *   0x8A36          x_count word  0x8A38 y_count word
 *   0x8A3A          HOP byte      0x8A3B LOP byte
 *   0x8A3C          control byte  (bit7 BUSY/START, bit6 HOG, bit5 SMUDGE, bits3-0 halftone line)
 *   0x8A3D          skew byte     (bit7 FXSR, bit6 NFSR, bits3-0 skew count)
 */
#ifndef RM_BLITTER_H
#define RM_BLITTER_H

#include <stdint.h>
#include "st.h"

/* XBIOS 38 (os.s): run func in supervisor, return to the caller's mode. Declared here as the ONE source
 * for the STE driver + self-test (both reach the supervisor-only 0xFFFF8Axx page through it). */
extern long Supexec(long (*func)(void));

/* ---- register addresses (one source of truth; no bare 0x8Axx literals anywhere else) ---- */
#define BLT_BASE          0xFFFF8A00UL
#define BLT_HALFTONE      (BLT_BASE + 0x00)    /* 16 words */
#define BLT_SRC_X_INC     (BLT_BASE + 0x20)    /* word, signed */
#define BLT_SRC_Y_INC     (BLT_BASE + 0x22)    /* word, signed */
#define BLT_SRC_ADDR      (BLT_BASE + 0x24)    /* long */
#define BLT_ENDMASK1      (BLT_BASE + 0x28)    /* word — first dst word of each line */
#define BLT_ENDMASK2      (BLT_BASE + 0x2A)    /* word — middle dst words */
#define BLT_ENDMASK3      (BLT_BASE + 0x2C)    /* word — last dst word of each line */
#define BLT_DST_X_INC     (BLT_BASE + 0x2E)    /* word, signed */
#define BLT_DST_Y_INC     (BLT_BASE + 0x30)    /* word, signed */
#define BLT_DST_ADDR      (BLT_BASE + 0x32)    /* long */
#define BLT_X_COUNT       (BLT_BASE + 0x36)    /* word — dst words per line */
#define BLT_Y_COUNT       (BLT_BASE + 0x38)    /* word — number of lines */
#define BLT_HOP           (BLT_BASE + 0x3A)    /* byte */
#define BLT_LOP           (BLT_BASE + 0x3B)    /* byte */
#define BLT_CONTROL       (BLT_BASE + 0x3C)    /* byte */
#define BLT_SKEW          (BLT_BASE + 0x3D)    /* byte */

/* ---- control byte bits (0x8A3C) ---- */
#define BLT_CTL_BUSY      0x80                 /* write 1 = start; reads 1 while running */
#define BLT_CTL_HOG       0x40                 /* 1 = hold the bus until done; 0 = shared (64-word bursts) */
#define BLT_CTL_SMUDGE    0x20

/* ---- skew byte bits (0x8A3D) ---- */
#define BLT_SKEW_FXSR     0x80                 /* force an extra source read at line start */
#define BLT_SKEW_NFSR     0x40                 /* suppress the final source read at line end */
#define BLT_SKEW_MASK     0x0F                 /* skew count (bit shift applied to the source, 0..15) */

/* ---- HOP (halftone operation, 0x8A3A) ---- */
#define BLT_HOP_ONE       0                    /* operand = all ones */
#define BLT_HOP_HALFTONE  1                    /* operand = halftone RAM */
#define BLT_HOP_SRC       2                    /* operand = source (the masked-blit choice) */
#define BLT_HOP_SRC_AND_HT 3                   /* operand = source AND halftone */

/* ---- LOP (logic operation, 0x8A3B) — 16 ops of (source op dst) ---- */
#define BLT_LOP_ZERO      0x0
#define BLT_LOP_AND       0x1                  /* dst = src AND dst  (the cookie-cut CLEAR pass) */
#define BLT_LOP_SRC       0x3                  /* dst = src          (plain copy) */
#define BLT_LOP_DST       0x5                  /* dst = dst */
#define BLT_LOP_XOR       0x6                  /* dst = src XOR dst */
#define BLT_LOP_OR        0x7                  /* dst = src OR dst   (the cookie-cut PAINT pass) */
#define BLT_LOP_ONE       0xF

/* ---- typed register accessors (supervisor only) ---- */
#define BLT_W(reg)   (*(volatile uint16_t *)(reg))
#define BLT_L(reg)   (*(volatile uint32_t *)(reg))
#define BLT_B(reg)   (*(volatile uint8_t  *)(reg))

/* One fully-specified blitter pass. All fields map 1:1 to registers; the driver (blit_run) pokes them
 * and starts the chip. x_count is dst words per line, y_count lines. src/dst_addr are byte addresses of
 * the first (top) word; the +inc walk goes forward through memory. endmask1/3 clip the first/last dst
 * word of every line; endmask2 (usually 0xFFFF) covers the middle. skew shifts the source right 0..15
 * bits into the dst word grid; fxsr/nfsr handle the edge source reads for a skewed run. */
typedef struct {
    uint32_t src_addr, dst_addr;
    int16_t  src_x_inc, src_y_inc, dst_x_inc, dst_y_inc;
    uint16_t endmask1, endmask2, endmask3;
    uint16_t x_count, y_count;
    uint8_t  hop, lop, skew_ctl;               /* skew_ctl = skew count | FXSR/NFSR bits */
} BlitPass;

/* Detect a usable blitter (STE or better) via the _MCH cookie. Must run supervisor (reads _p_cookies at
 * 0x5A0). Returns 1 if the machine has a blitter, 0 on a plain ST / no cookie jar. */
int blitter_present(void);

/* Same check, callable from user mode: wraps blitter_present() in a Supexec excursion. */
int blitter_available(void);

/* On-target driver proof (GAME_STE_SELFTEST build): reproduce rm_blit_objshift2 with the blitter and
 * return the XOR-diff framebuffer (all-zero == byte-exact) plus the mismatch byte count. */
const uint8_t *blitter_selftest(long *mismatch_out);

/* Run one blitter pass to completion (HOG mode) from the current supervisor context. See src/blitter.c
 * for the HOG-vs-shared justification. */
void blit_run(const BlitPass *p);

#endif /* RM_BLITTER_H */
