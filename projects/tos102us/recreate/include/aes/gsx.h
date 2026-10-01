/* aes/gsx.h — the AES's road to the VDI: its parameter block and binding globals, the bridge every graphic call
 * crosses, and the binding layer's atoms (`src/aes/gsx.c`).
 *
 * THE ONE `trap #2`. Every VDI call the AES makes ends in gsx2 ($fecb5a): the parameter block's contrl pointer stored,
 * D0 = GEM_SELECTOR_VDI, D1 = the block, `trap #2`. The trap's two hops are RAM — vector $88 (GEM's $fe3ea6, whose
 * arm for any selector but 0/200/201 is `move.l SYSVAR_VDI_ENTRY,-(sp); rts`) and that system variable ($fc4ebc, the
 * BIOS's VDI door: `jsr VDI_ROM_ENTRY; rte`) — and VDI_ROM_ENTRY saves D1-A6 round the lot, so D0 is all a call
 * changes. `gsx_trap` below is that crossing, taken two ways (`gemdos/gemdos.h`'s `gemdos_trap_word_long`
 * arrangement): ON TARGET the machine's own trap; OFF TARGET both hops CHECKED against the snapshot's — a case that
 * repoints either halts by name on the host, never served by the wrong code — and the VDI's own C twin of
 * VDI_ROM_ENTRY called on the block, whose dispatcher leaves through `staged_call.h`'s bare hook (a case binds it to
 * the VDI's C cores: `test/aes_gsx.py`'s `vdi_functions`).
 *
 * THE BINDING. Hand 68000, every routine (gemgsxif's and gsx2) entered by a Line-F call or a `bsr` over the frame its
 * caller pushed — Alcyon's words and longs. The wrappers point the block's PTSIN at the caller's points for the one
 * call and back at the AES's own ptsin after it ($fe8bd0), and load contrl[7..10] with the MFDB / vector pointers a
 * call carries. The internal fragments $fe8bb6/$fe8bba (the call by a 3-byte row of $fe8bdc: opcode, points and
 * words, then PTSIN restored) and $fe8ba2/$fe8bae (contrl[7..10] and PTSIN from the caller's frame) read their
 * CALLER's frame through A0, so they are folded into their callers rather than given rows (the OB_ADDR precedent).
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h`. The arrays the block points at are `aes/aes.h`'s AES_GSX_* addresses.
 */
#ifndef TOS102US_AES_GSX_H
#define TOS102US_AES_GSX_H

/* GUARDED as `vdi/vdi.h` is: `src/aes/gsx.S` reads the fields, and everything outside the guards is a plain integer
 * `#define` both languages read. */
#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"
#include "aes/aes.h"

/* ---- the parameter block D1 names ($9466): five array pointers, the VDI's PB_* order --------------------------- */
#define AES_GSX_PB_CONTRL     0x9466     /* long: pb[0], := AES_GSX_CONTRL     ($fecb60 move.l #$c7e0,(a0))    */
#define AES_GSX_PB_INTIN      0x946a     /* long: pb[1]                        ($fe8ada move.l #$95ba)         */
#define AES_GSX_PB_PTSIN      0x946e     /* long: pb[2], a caller's points for one call ($fe8bae, $fe8bd0)     */
#define AES_GSX_PB_INTOUT     0x9472     /* long: pb[3]                        ($fe8ae4 move.l #$9706)         */
#define AES_GSX_PB_PTSOUT     0x9476     /* long: pb[4]                        ($fe8aee move.l #$9abc)         */

/* ---- the AES's contrl[] ($c7e0): the words the binding writes. contrl[0..3] are in the snapshot's MASK (the idle
 * loop's keyboard poll rewrites them), so a case that reaches the VDI stages them. ---------------------------------- */
#define AES_GSX_OPCODE        0xc7e0     /* word: contrl[0]                    ($fe87dc move.l (a0)+,(a1)+)    */
#define AES_GSX_N_PTSIN       0xc7e2     /* word: contrl[1], the same longword ($fe87dc)                       */
#define AES_GSX_N_PTSOUT      0xc7e4     /* word: contrl[2], the VDI's answer  ($fcaa0a clr.w: the dispatcher's) */
#define AES_GSX_N_INTIN       0xc7e6     /* word: contrl[3]                    ($fe87e0 move.w (a0)+,(a1))     */
#define AES_GSX_N_INTOUT      0xc7e8     /* word: contrl[4], the VDI's answer  ($fcaa0e clr.w: the dispatcher's) */
#define AES_GSX_SUBFUNCTION   0xc7ea     /* word: contrl[5], an escape's number ($fe886a move.w d0,$c7ea)      */
#define AES_GSX_HANDLE        0xc7ec     /* word: contrl[6]                    ($fe87e4 move.w $c766,(a1))     */
/* contrl[7..8] and [9..10] are `aes/aes.h`'s AES_GSX_CONTRL_PTR / AES_GSX_CONTRL_PTR2. */

/* ---- the binding's globals -------------------------------------------------------------------------------------- */
#define AES_GL_HANDLE         0xc766     /* word: the AES's workstation handle ($fe87e4)                       */
/* The cursor's HIDE NEST: gsx_moff hides on the first level and counts, gsx_mon counts down and shows at zero —
 * the AES's own depth, beside the VDI's LINEA_M_HID_CT. The snapshot holds 0 (the cursor drawn). */
#define AES_GL_MOFF           0xc86a     /* word: hide nesting                 ($fe8a72 tst.w, $fe8a86 addq.w) */
#define AES_GL_MOUSE_SHOWN    0x9b6e     /* word: 0 hidden, 1 shown            ($fe8a80 clr.w, $fe8aa4 move.w) */
/* The clip gsx_sclip sets and gsx_gclip answers, a GRECT spread over four words ($fda808.. move.w (a0)+). */
#define AES_GL_XCLIP          0x95b6     /* word                               ($fda808)                       */
#define AES_GL_YCLIP          0x9704     /* word                               ($fda80e)                       */
#define AES_GL_WCLIP          0x95b8     /* word                               ($fda814)                       */
#define AES_GL_HCLIP          0xc7de     /* word                               ($fda81a)                       */
/* The attribute CACHES gsx_start fills with -1 ($fdaab0) and the setters compare before calling the VDI. */
#define AES_GL_MODE           0xc848     /* word: the writing mode             ($fda914 lea, $fdaac8 move.w)   */
#define AES_GL_TCOLOR         0x971a     /* word: the text colour              ($fda92c lea, $fdaabc move.w)   */
#define AES_GL_LCOLOR         0xc904     /* word: the line colour              ($fda93a lea, $fdaab6 move.w)   */
#define AES_GL_FIS            0x9aec     /* word: the fill interior            ($fdac3c lea, $fdaada move.w)   */
#define AES_GL_PATT           0x98a2     /* word: the fill style               ($fdac54 lea, $fdaad4 move.w)   */
#define AES_GL_FONT           0x980c     /* word: the text font                ($fdad12 lea, $fdaace move.w)   */
/* v_opnwk's answer: its intout (45 words) then its ptsout (6 points) — the wrapper points PTSOUT 90 bytes in. */
#define AES_GL_WS_WORDS       57         /* ($fe8ac0 lea 90(a1),a1: 45 words, then 12)                          */
#define AES_GL_WS             0xc892     /* words[AES_GL_WS_WORDS]: work_out   ($fda996 lea, $fe8892 pea)      */
#define AES_GL_NPLANES        0xc914     /* word: the screen's planes          ($fda9b2, $fdab20 move.w d1)    */
/* The three MFDBs the blits use: the VDI's layout (`vdi/linea.h` MFDB_*), fd_addr and nine words. */
#define AES_MFDB_BYTES        20         /* an MFDB, three reserved words after MFDB_NPLANES                    */
#define AES_GL_SRC            0x9ba6     /* bytes[AES_MFDB_BYTES]: a blit's source ($fda9d6 lea)               */
#define AES_GL_DST            0x9bde     /* bytes[AES_MFDB_BYTES]: ...destination ($fda9dc lea)                */
#define AES_GL_TMP            0x9c44     /* bytes[AES_MFDB_BYTES]: the save buffer's ($fe87a4 move.l d0)       */
#define AES_GL_MFORM_AT       0xc844     /* long: where gsx_mfset copies a form ($fdac14 move.l #$95ba)        */
#define AES_XRAT              0x9c0c     /* word: the mouse's x                ($fe537e move.w)                */
#define AES_YRAT              0x9c0e     /* word: ...and y                     ($fe539e move.w)                */
#define AES_BUTTON            0xc90a     /* word: the buttons' state           ($fe526c move.w 8(a6))          */
#define AES_GL_GRAPHIC        0xc90c     /* word: in graphics mode             ($fe88d4 move.w #1)             */

/* ---- the binding's immediates, one name for `gsx.c` and `gsx.S` alike ------------------------------------------- */
#define GSX_ONE_WORD          1          /* gsx_1code's `move.l #1,-(sp)`: no points, one word ($fe87f8)        */
/* gsx_mon's v_show_c(1), which ignores the VDI's own hide depth — and, in the same `moveq #1,d0`, the step it counts
 * its nest down by ($fe8a8e). */
#define GSX_SHOW_AT_ONCE      1
#define GSX_MOUSE_HIDDEN      0          /* AES_GL_MOUSE_SHOWN's two values ($fe8a80 clr.w, $fe8aa4 move.w #1)  */
#define GSX_MOUSE_SHOWN       1
/* gsx_fix's MFDB of a form in memory: a byte width is eight pixels, a word sixteen ($fda9bc lsl.w #3, lsr.w #4), and
 * one plane ($fda9c8 move.w #1). */
#define GSX_PIXELS_PER_BYTE_SHIFT 3
#define GSX_PIXELS_PER_WORD_SHIFT 4
#define GSX_FORM_PLANES       1

#ifndef __ASSEMBLER__
/* ---- the atoms (`src/aes/gsx.c`). A word argument is an Alcyon `int`; each VDI call answers D0.w as the trap left
 * it (`vdi/entry.h`: VDI_RESULT), which no caller reads but the differential compares. ------------------------------ */
uint16_t aes_gsx2(uint8_t *image);                                                                  /* $fecb5a */
uint16_t aes_gsx_ncode(uint8_t *image, int16_t opcode, int16_t n_ptsin, int16_t n_intin);           /* $fe87d2 */
uint16_t aes_gsx_1code(uint8_t *image, int16_t opcode, int16_t value);                              /* $fe87f0 */
void aes_gsx_moff(uint8_t *image);                                                                  /* $fe8a72 */
void aes_gsx_mon(uint8_t *image);                                                                   /* $fe8a8e */
uint16_t aes_v_pline(uint8_t *image, int16_t count, uint32_t points);                               /* $fe8afa */
uint16_t aes_vs_clip(uint8_t *image, int16_t flag, uint32_t points);                                /* $fe8b0e */
uint16_t aes_vst_height(uint8_t *image, int16_t height, uint32_t char_width, uint32_t char_height,
                        uint32_t cell_width, uint32_t cell_height);                                 /* $fe8b22 */
uint16_t aes_vr_recfl(uint8_t *image, uint32_t points, uint32_t mfdb);                              /* $fe8b50 */
uint16_t aes_vro_cpyfm(uint8_t *image, int16_t mode, uint32_t points, uint32_t source, uint32_t destination);
                                                                                                    /* $fe8b60 */
uint16_t aes_vrt_cpyfm(uint8_t *image, int16_t mode, uint32_t points, uint32_t source, uint32_t destination,
                       int16_t foreground, int16_t background);                                     /* $fe8b72 */
uint16_t aes_vrn_trnfm(uint8_t *image, uint32_t source, uint32_t destination);                      /* $fe8b88 */
uint16_t aes_vsl_width(uint8_t *image, int16_t width);                                              /* $fe8b92 */
void aes_gsx_fix(uint8_t *image, uint32_t mfdb, uint32_t address, int16_t bytes_across, int16_t height);
                                                                                                    /* $fda992 */

/* ---- THE BRIDGE: the block at AES_GSX_PB through `trap #2`, its D0.w answered ---------------------------------- */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include "ram_vector.h"
#include "vdi/entry.h"

static inline uint16_t gsx_trap(uint8_t *image)
{
    require_cpu_routine(image, VECTOR_TRAP_GEM, GEM_TRAP2,
                        "the AES's trap #2: vector $88 no longer GEM's $fe3ea6 — the call would run other code");
    require_cpu_routine(image, SYSVAR_VDI_ENTRY, GEM_TRAP2_VDI_DOOR,
                        "the AES's trap #2: SYSVAR_VDI_ENTRY no longer the BIOS's VDI door $fc4ebc");
    return vdi_entry(image, AES_GSX_PB);
}
#else
/* The ROM's own `moveq #$73,d0 / move.l <block>,d1 / trap #2`: the VDI's entry restores D1-A6 from its own frame,
 * so D0 is the one register the call changes. No PERF entry prices it: it IS the ROM's trap. */
static inline uint16_t gsx_trap(uint8_t *image)
{
    register uint32_t answer __asm__("d0") = GEM_SELECTOR_VDI;
    register uint32_t block __asm__("d1") = AES_GSX_PB;

    (void)image;
    __asm__ volatile ("trap #2" : "+d"(answer) : "d"(block) : "memory", "cc");
    return (uint16_t)answer;
}
#endif
#endif /* !__ASSEMBLER__ */

#endif /* TOS102US_AES_GSX_H */
