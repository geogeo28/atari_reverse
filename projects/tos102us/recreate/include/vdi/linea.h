/* vdi/linea.h — the LINE-A VARIABLE BLOCK, the drawing vectors, and the $a007 BITBLT / MFDB layouts.
 *
 * The block is the one Atari published: `$a000` answers its base in A0/D0 ($fc9f34 `lea $299a,a0`),
 * and a program reaches every field at a signed displacement from it. TOS itself mostly does not: the
 * VDI's C reaches each field at its ABSOLUTE address (`moveal $29a2,a0`), and the Line-A primitives
 * through `lea $299a,a4` plus a displacement ($fca57e). So the fields are spelt here as ABSOLUTE
 * addresses — the form every ROM citation below has — and a displacement is `LINEA_X - LINEA_BASE`.
 *
 * EVERY FIELD CARRIES ONE ROM ACCESS that establishes it; a field the ROM never touches is not here
 * (the list of those is in `test/vdi.py`'s module docstring). Frozen the way `gemdos/fs.h` is: the
 * only permitted edit is adding a field with its own citation.
 *
 * THE WIDTH TAG. A FIELD's comment opens with its width — `byte`, `word`, `long`, or an array
 * `bytes[N]` / `words[N]` / `longs[N]` whose N is a literal or a constant these headers define — and
 * `test/vdi.py` stages and reads fields BY NAME at exactly that width. A constant whose comment opens
 * with anything else (a count, a mask, a ROM table) is NOT a field and cannot be staged as one; such
 * constants carry a `_COUNT`/`_BYTES`/`_MASK`/`_TABLE`/`_SET`-style suffix so the name says so too.
 *
 * THE CONSOLE OWNS PART OF THIS BLOCK. -$2e..+$2 ($296c..$299c, V_CEL_HT .. WIDTH) and three fields
 * further down ($2840 V_HID_CNT, $284c V_SAV_XY, and the first four drawing vectors) are the BIOS
 * console's state and were named by it first — `CON_*` in `addrs.h`. They are not spelt a second
 * time here; the two the VDI reads as Line-A fields are ALIASES of the console's names, and the three
 * console-range words the console never touches are added below.
 */
#ifndef TOS102US_VDI_LINEA_H
#define TOS102US_VDI_LINEA_H

#include "addrs.h"

#define LINEA_BASE            0x299a     /* what $a000 answers                  ($fc9f34 lea)       */

/* ---- the negative half: mouse, tables, fonts, input modes, cursor, user vectors ---------------- */
#define LINEA_CUR_FONT        0x2610     /* long: the text font in use          ($fcaace move.l)    */
#define LINEA_GDP_SCRATCH     0x2614     /* words[23]: arc/ellipse scratch      ($fcbca6..$fcbca0)  */
/* ...and the words of it a reconstructed routine reads or writes by name (DRI's names): */
#define LINEA_GDP_N_STEPS     0x2624     /* word: segments per arc              ($fcc6e4 clc_nsteps) */
#define LINEA_GDP_SAVED_BEG_STYLE 0x2628 /* word: s_fa_attr's WS_LINE_BEG       ($fcd0a0)           */
#define LINEA_GDP_SAVED_END_STYLE 0x262a /* word: ...and WS_LINE_END            ($fcd0a8)           */
#define LINEA_GDP_SAVED_FILL_COLOR 0x262c /* word: ...and WS_FILL_COLOR         ($fcd06e)           */
#define LINEA_GDP_SAVED_FILL_PER 0x262e  /* word: ...and WS_FILL_PER            ($fcd07c)           */
#define LINEA_GDP_XRAD        0x263a     /* word: the x radius                  ($fcc6b8)           */
#define LINEA_GDP_YRAD        0x2640     /* word: the y radius                  ($fcc6be)           */
#define LINEA_M_POS_HX        0x2642     /* word: mouse hot spot x              ($fd02e2)           */
#define LINEA_M_POS_HY        0x2644     /* word: ...and y                      ($fd02ee)           */
#define LINEA_M_PLANES        0x2646     /* word: mouse form planes             ($fd02f4)           */
#define LINEA_M_CDB_BG        0x2648     /* word: mouse mask colour, mapped     ($fd030e)           */
#define LINEA_M_CDB_FG        0x264a     /* word: mouse data colour, mapped     ($fd0324)           */
#define LINEA_MASK_FORM       0x264c     /* words[LINEA_MASK_FORM_WORDS]: 16 x (mask, data) ($fd032e) */
#define LINEA_MASK_FORM_WORDS 32         /* ($fd032c `moveq #15` + dbf, two words a pass)           */
#define LINEA_INQ_TAB         0x268c     /* words[VDI_INQ_TAB_WORDS]: vq_extnd's table ($fcb6bc)    */
#define LINEA_DEV_TAB         0x26e6     /* words[VDI_DEV_TAB_WORDS]: v_opnwk's intout ($fcb6a2)    */
#define LINEA_GCURX           0x2740     /* word: mouse x                       ($fcfec2)           */
#define LINEA_GCURY           0x2742     /* word: mouse y                       ($fcfec8)           */
#define LINEA_M_HID_CT        0x2744     /* word: mouse hide depth              ($fcb814)           */
#define LINEA_MOUSE_BT        0x2746     /* word: button state                  ($fcfe6c)           */
#define LINEA_REQ_COL         0x2748     /* words[VDI_REQ_COL_WORDS]: realized RGB, per-mille ($fcb882) */
#define LINEA_SIZ_TAB         0x27a8     /* words[VDI_SIZ_TAB_WORDS]: v_opnwk's ptsout ($fcb6e0)    */
#define LINEA_TERM_CH         0x27c6     /* word: the key that ended a request  ($fca7e8)           */
#define LINEA_CHC_MODE        0x27c8     /* word: choice input mode             ($fcb3c6)           */
#define LINEA_CUR_WORK        0x27ca     /* long: the workstation being served  ($fcaa40)           */
#define LINEA_DEF_FONT        0x27ce     /* long: the default font's header     ($fcdef8)           */
#define LINEA_FONT_RING       0x27d2     /* longs[LINEA_FONT_RING_SLOTS]        ($fcdec0)           */
#define LINEA_FONT_RING_SLOTS 4          /* [3] is the ring's 0 terminator      ($fcded0 clr.l)     */
/* FONT_RING's slot indices: [0] the ROM 6x6 ($fcdec0), [1] the RAM 8x8, whose header's own FONT_NEXT —
 * copied from ROM — already names the RAM 8x16 ($fcb71c), [2] the workstation's loaded fonts, which
 * the dispatcher copies in from WS_LOADED_FONTS on every call ($fcaaa6). */
#define LINEA_FONT_RING_SYSTEM  0
#define LINEA_FONT_RING_BUILTIN 1
#define LINEA_FONT_RING_LOADED  2
#define LINEA_FONT_COUNT      0x27e2     /* word: fonts in the ring             ($fcdfb6)           */
#define LINEA_LINE_CW         0x27e4     /* word: the width the quarter circle is for ($fccab6)     */
#define LINEA_LOC_MODE        0x27e6     /* word: locator input mode            ($fcb3b6)           */
#define LINEA_NUM_QC_LINES    0x27e8     /* word: quarter-circle rows in use    ($fccab0)           */
#define LINEA_Q_CIRCLE        0x27ea     /* words[40]: the quarter circle, to STR_MODE ($fccad8)    */
#define LINEA_STR_MODE        0x283a     /* word: string input mode             ($fcb3ce)           */
#define LINEA_VAL_MODE        0x283c     /* word: valuator input mode           ($fcb3be)           */
#define LINEA_CUR_MS_STAT     0x283e     /* byte: mouse status bits             ($fcfe78)           */
#define LINEA_CUR_X           0x2842     /* word: cursor x the VBL draws at     ($fcff1e)           */
#define LINEA_CUR_Y           0x2844     /* word: ...and y                      ($fcff20)           */
#define LINEA_CUR_FLAG        0x2846     /* byte: bit 0 = cursor moved          ($fcff32 bclr)      */
#define LINEA_MOUSE_FLAG      0x2847     /* byte: nonzero = cursor draw locked  ($fcfe28 tst.b)     */
/* RETSAV (-$152): `$fcfa9c`, the VDI's `trap #1` wrapper, parks its caller's return address here across
 * the trap — which is why that wrapper is not re-entrant. */
#define LINEA_RETSAV          0x2848     /* long                                ($fcfa9c)           */
#define LINEA_SAVE_BLOCK      0x2850     /* bytes[LINEA_SAVE_BLOCK_BYTES]: the sprite's save block ($fcff4a) */
#define LINEA_SAVE_BLOCK_BYTES 0x108     /* ...up to USER_TIM, the next field   ($fca670)           */
#define LINEA_USER_TIM        0x2958     /* long: the timer routine vex_timv installs ($fca670)     */
#define LINEA_NEXT_TIM        0x295c     /* long: the etv_timer it chains to    ($fca692)           */
#define LINEA_USER_BUT        0x2960     /* long: button-change routine         ($fca7fe)           */
#define LINEA_USER_CUR        0x2964     /* long: cursor-draw routine           ($fca80a)           */
#define LINEA_USER_MOT        0x2968     /* long: mouse-motion routine          ($fca804)           */
/* ...then the console's -$2e..-$6 (`CON_*`), and the three words of that range it never touches: */
#define LINEA_V_REZ_HZ        0x298e     /* word: screen width in pixels        ($fca9d6)           */
#define LINEA_V_REZ_VT        0x2996     /* word: screen height in pixels       ($fca9d0)           */
#define LINEA_BYTES_LIN       0x2998     /* word: bytes per screen line         ($fca1bc muls.w)    */

/* ---- the positive half, from the base ------------------------------------------------------- */
#define LINEA_PLANES          CON_PLANES      /* word: bit planes               ($fca1c2)           */
#define LINEA_WIDTH           CON_LINE_BYTES  /* word: bytes per line           ($fd005e)           */
#define LINEA_CONTRL          0x299e     /* long: the call's contrl array       ($fc9fb2)           */
#define LINEA_INTIN           0x29a2     /* long: intin                         ($fc9fb4)           */
#define LINEA_PTSIN           0x29a6     /* long: ptsin — VDI_PTSIN_COPY on a trap entry ($fc9fb8) */
#define LINEA_INTOUT          0x29aa     /* long: intout                        ($fc9fba)           */
#define LINEA_PTSOUT          0x29ae     /* long: ptsout                        ($fc9fbc)           */
#define LINEA_COLBIT0         0x29b2     /* word: plane 0 of the drawing colour ($fcb63c)           */
#define LINEA_COLBIT1         0x29b4     /* word                                ($fcb648)           */
#define LINEA_COLBIT2         0x29b6     /* word                                ($fcb654)           */
#define LINEA_COLBIT3         0x29b8     /* word                                ($fcb660)           */
#define LINEA_LSTLIN          0x29ba     /* word: last line of a polyline flag  ($fcbe94)           */
#define LINEA_LN_MASK         0x29bc     /* word: line style mask               ($fcba0c)           */
#define LINEA_WRT_MODE        0x29be     /* word: write mode 0..3               ($fcaa76)           */
#define LINEA_X1              0x29c0     /* word                                ($fca0f4)           */
#define LINEA_Y1              0x29c2     /* word                                ($fca902)           */
#define LINEA_X2              0x29c4     /* word                                ($fca0fa)           */
#define LINEA_Y2              0x29c6     /* word                                ($fcb67e)           */
#define LINEA_PATPTR          0x29c8     /* long: fill pattern                  ($fcaa7e)           */
#define LINEA_PATMSK          0x29cc     /* word: pattern row index mask        ($fcaa86)           */
#define LINEA_MULTIFILL       0x29ce     /* word: multi-plane pattern flag      ($fcaa96)           */
#define LINEA_CLIP            0x29d0     /* word: clipping on                   ($fcaa4a)           */
#define LINEA_XMINCL          0x29d2     /* word                                ($fcaa56)           */
#define LINEA_YMINCL          0x29d4     /* word                                ($fcaa5e)           */
#define LINEA_XMAXCL          0x29d6     /* word                                ($fcaa66)           */
#define LINEA_YMAXCL          0x29d8     /* word                                ($fcaa6e)           */
#define LINEA_XACC_DDA        0x29da     /* word: text scaling accumulator      ($fcdbae)           */
#define LINEA_DDA_INC         0x29dc     /* word: text scaling increment        ($fcaab6)           */
#define LINEA_T_SCLSTS        0x29de     /* word: text scale direction          ($fcaabe)           */
#define LINEA_MONO_STATUS     0x29e0     /* word: font is monospaced            ($fcaae6)           */
#define LINEA_SOURCEX         0x29e2     /* word: glyph x in the font form      ($fcdc00)           */
#define LINEA_SOURCEY         0x29e4     /* word                                ($fcdc24 clr.w)     */
#define LINEA_DESTX           0x29e6     /* word: glyph x on screen             ($fcda18)           */
#define LINEA_DESTY           0x29e8     /* word                                ($fcda2e)           */
#define LINEA_DELX            0x29ea     /* word: glyph width                   ($fcdc1e)           */
#define LINEA_DELY            0x29ec     /* word: glyph height                  ($fcdb7c)           */
#define LINEA_FBASE           0x29ee     /* long: the font form                 ($fcd83e)           */
#define LINEA_FWIDTH          0x29f2     /* word: font form width in bytes      ($fcd846)           */
#define LINEA_STYLE           0x29f4     /* word: text effects                  ($fcaafc)           */
#define LINEA_LITEMASK        0x29f6     /* word: lighten mask                  ($fcd7b8)           */
#define LINEA_SKEWMASK        0x29f8     /* word: italic skew mask              ($fcd7da)           */
#define LINEA_WEIGHT          0x29fa     /* word: bold thickening               ($fcd7a6)           */
#define LINEA_R_OFF           0x29fc     /* word: italic right offset           ($fcd7d2)           */
#define LINEA_L_OFF           0x29fe     /* word: italic left offset            ($fcd7ca)           */
#define LINEA_SCALE           0x2a00     /* word: text scaling on               ($fcaac6)           */
#define LINEA_CHUP            0x2a02     /* word: text rotation                 ($fcab14)           */
#define LINEA_TEXT_FG         0x2a04     /* word: text colour                   ($fcdb74)           */
#define LINEA_SCRTCHP         0x2a06     /* long: text effects scratch buffer   ($fcaaf4)           */
#define LINEA_SCRPT2          0x2a0a     /* word: offset of its second half     ($fcaaec)           */
#define LINEA_TEXT_BG         0x2a0c     /* word: text background colour        ($fd2164 `114(a6)`) */
#define LINEA_COPY_TRAN       0x2a0e     /* word: 0 = opaque copy, else transparent ($fcb5cc)       */
#define LINEA_SEEDABORT       0x2a10     /* long: contour fill's abort test     ($fd08e4)           */

/* ---- the TEN DRAWING VECTORS: TOS 1.02's extension past the published block ---------------------
 * Every CPU/blitter-specific body is reached through one of these longwords. `$fc4dde` fills all ten
 * from one of two ROM tables by bit 0 of D0 (the blit mode, kept at LINEA_BLIT_MODE); the boot always
 * picks the CPU set and only XBIOS Blitmode can pick the other. The first four are the console's
 * (`CON_VECTOR_*`); the other six are the VDI's and Line-A's.
 *
 * HOW A CORE REACHES A BODY THROUGH ONE, which is the BIOS console's arrangement (`src/bios/
 * conout_glyph.c`) made the rule: the core calls the CPU body's reconstruction BY NAME, after
 * `require_cpu_routine` (`include/ram_vector.h`) has checked the vector holds the CPU routine the
 * captured machine has — anything else HALTS on both builds (`recreate_not_reconstructed`). Chosen over
 * the by-address hook (`include/staged_call.h`) because the bodies are ROM code this project
 * reconstructs: a hook would make every drawing case stage a Python twin of a rasterizer. A case that
 * REPOINTS a vector (the blitter set, a program's own routine) is therefore served by the halt, and
 * says so; a function whose job is to call whatever a vector holds — USER_TIM/BUT/MOT/CUR and NEXT_TIM,
 * which in the snapshot point INTO THE AES — goes through `staged_call.h`'s hook, and its case
 * repoints the vector at a stub it stages rather than running the AES's code. */
#define LINEA_VECTORS         CON_VECTOR_GLYPH   /* the first slot                ($fc4df6 lea)     */
#define LINEA_VECTOR_COUNT    10         /* ($fc4dfc `moveq #9` + dbf)                              */
#define LINEA_VECTOR_BITBLT   0x2a24     /* long: $a007/$a00e's bit-block engine ($fd05dc)          */
#define LINEA_VECTOR_FAST_TEXT 0x2a28    /* long: byte-aligned text             ($fcf9b8 `58(a5)`)  */
#define LINEA_VECTOR_RECT_FILL 0x2a2c    /* long: $a005's filled rectangle body ($fcfcc4)           */
#define LINEA_VECTOR_VLINE    0x2a30     /* long: $a003's vertical line         ($fca204 `150(a4)`) */
#define LINEA_VECTOR_HLINE    0x2a34     /* long: $a004's horizontal line body  ($fca5c4 `154(a4)`) */
#define LINEA_VECTOR_TEXTBLT  0x2a38     /* long: $a008's TextBlt               ($fcee5e)           */
#define LINEA_BLITTER_SET_PTR 0x2a3c     /* long: -> LINEA_BLITTER_SET          ($fca9a8)           */
#define LINEA_CPU_SET_PTR     0x2a40     /* long: -> LINEA_CPU_SET              ($fca99e)           */
#define LINEA_BLIT_MODE       0x2a44     /* word: the mode the vectors were filled for ($fc4dde)    */
#define LINEA_BLIT_MODE_BLITTER_MASK 1   /* bit 0: the blitter set              ($fc4dea btst #0)   */
#define LINEA_BLITTER_SET     0xfc4e0e   /* ROM: ten longwords, the blitter bodies ($fca9a8)        */
#define LINEA_CPU_SET         0xfc4e36   /* ROM: ten longwords, the CPU bodies  ($fca99e)           */

/* ---- the Line-A exception's own tables -------------------------------------------------------
 * `$fc9f0c` keeps the low twelve bits of the $Axxx word and serves 0..15 through a longword table;
 * anything higher returns having done nothing. `$a000` answers the font table in A1 and the opcode
 * table in A2 ($fc9f3c, $fc9f42): the three ROM font headers, in `FONT_ROM_*` order, and after them a
 * zero longword ($fc9f96) — which is data, not the head of the SEEDABORT stub at $fc9f9a. */
#define LINEA_OPCODE_TABLE    0xfc9f4a   /* 16 longwords, $a000..$a00f          ($fc9f24)           */
#define LINEA_OPCODE_MASK     0xfff      /*                                     ($fc9f12 and.w)     */
#define LINEA_OPCODE_LAST     15         /*                                     ($fc9f1c cmp.w)     */
#define LINEA_FONT_TABLE      0xfc9f8a   /*                                     ($fc9f3c lea)       */
#define LINEA_FONT_TABLE_ENTRIES 3

/* ---- the $a007 BITBLT parameter block (76 bytes) -----------------------------------------------
 * `$fd05fc` ($a007) adds 76 to the caller's A6 and jumps into the engine, which reads the block as
 * the NEGATIVE half of a `link a6,#-76` frame — the frame `$fd0346` ($a00e, copy raster) builds from
 * two MFDBs. So every offset below is cited as an access at `frame - 76 + offset`. */
#define BITBLT_B_WD           0          /* word: width in pixels               ($fd052a -76(a6))   */
#define BITBLT_B_HT           2          /* word: height                        ($fd0534 -74)       */
#define BITBLT_PLANE_CT       4          /* word: planes                        ($fd03e8 -72)       */
#define BITBLT_FG_COL         6          /* word: foreground colour             ($fd048e -70)       */
#define BITBLT_BG_COL         8          /* word: background colour             ($fd0478 -68)       */
#define BITBLT_OP_TAB         10         /* bytes[BITBLT_OP_TAB_BYTES]: logic op per colour bit pair ($fd049c) */
#define BITBLT_OP_TAB_BYTES   4
#define BITBLT_S_XMIN         14         /* word                                ($fd050c -62)       */
#define BITBLT_S_YMIN         16         /* word                                ($fd0510 -60)       */
#define BITBLT_S_FORM         18         /* long: source form base              ($fd0400 -58)       */
#define BITBLT_S_NXWD         22         /* word: bytes to the next word, same plane ($fd03ee -54)  */
#define BITBLT_S_NXLN         24         /* word: bytes to the next line        ($fd03f8 -52)       */
#define BITBLT_S_NXPL         26         /* word: bytes to the next plane       ($fd04e0 -50)       */
#define BITBLT_D_XMIN         28         /* word                                ($fd0514 -48)       */
#define BITBLT_D_YMIN         30         /* word                                ($fd0518 -46)       */
#define BITBLT_D_FORM         32         /* long                                ($fd0404 -44)       */
#define BITBLT_D_NXWD         36         /* word                                ($fd03f4 -40)       */
#define BITBLT_D_NXLN         38         /* word                                ($fd03fc -38)       */
#define BITBLT_D_NXPL         40         /* word                                ($fd04e4 -36)       */
#define BITBLT_P_ADDR         42         /* long: pattern, 0 for none           ($fd0382 -34)       */
#define BITBLT_P_NXLN         46         /* word                                ($fd0376 -30)       */
#define BITBLT_P_NXPL         48         /* word                                ($fd0372 -28)       */
#define BITBLT_P_MASK         50         /* word                                ($fd037c -26)       */
#define BITBLT_SPACE          52         /* bytes[24]: the CPU engine's own scratch ($fd10bc -24)   */
#define BITBLT_BYTES          76         /* ($fd034a link #-76, $fd05fc adda.w #76)                 */

/* ---- the MFDB (memory form definition block) as $a00e and vr_trnfm read it -------------------- */
#define MFDB_ADDR             0          /* long: base, 0 = the screen          ($fd0394)           */
#define MFDB_H                6          /* word: height                        ($fd2d48)           */
#define MFDB_WDWIDTH          8          /* word: width in words                ($fd03b2)           */
#define MFDB_STAND            10         /* word: 1 = device-independent format ($fd2d50)           */
#define MFDB_NPLANES          12         /* word                                ($fd03ae)           */
/* MFDB_STAND's two values, as vr_trnfm stores them into its destination. */
#define MFDB_FORMAT_DEVICE    0          /* planes interleaved word by word     ($fd2d60 clr.w)     */
#define MFDB_FORMAT_STANDARD  1          /* one plane after another             ($fd2d56 move.w #1) */

#endif /* TOS102US_VDI_LINEA_H */
