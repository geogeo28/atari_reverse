/* vdi/vdi.h — the VDI's call interface, its WORKSTATION record, its RAM, and the ROM data it reads.
 *
 * HOW A VDI CALL REACHES A FUNCTION. `trap #2` with D0 = $73 lands (through `SYSVAR_VDI_ENTRY`) in
 * `$fc9f9e`, which copies the five array pointers of the PARAMETER BLOCK at D1 into the Line-A
 * variables `LINEA_CONTRL`..`LINEA_PTSOUT` — with PTSIN replaced by `VDI_PTSIN_COPY`, into which it
 * copies the caller's points — and calls the dispatcher `$fca9f6`. That clears contrl[2] and
 * contrl[4], finds the workstation whose handle is contrl[6] on the list from `VDI_PHYS_WORK`, makes
 * it `LINEA_CUR_WORK`, copies a dozen of its fields into the Line-A variables, and `jsr`s the function
 * the opcode tables name. A FUNCTION therefore reads its arguments through the Line-A pointers and its
 * attributes through `LINEA_CUR_WORK`, and answers only through memory — the cores are `void`.
 *
 * Every offset carries one ROM access that establishes it; `gemdos/fs.h`'s freeze applies, and so does
 * `vdi/linea.h`'s WIDTH TAG: a field's comment opens with its width, and nothing else does.
 */
#ifndef TOS102US_VDI_VDI_H
#define TOS102US_VDI_VDI_H

#include <stdint.h>

#include "addrs.h"
#include "vdi/linea.h"

/* ---- the parameter block D1 points at: five array pointers -------------------------------------- */
#define PB_CONTRL             0          /* long                                ($fc9fb0)           */
#define PB_INTIN              4          /* long                                ($fc9fb4)           */
#define PB_PTSIN              8          /* long                                ($fc9fb6)           */
#define PB_INTOUT             12         /* long                                ($fc9fba)           */
#define PB_PTSOUT             16         /* long                                ($fc9fbc)           */
#define PB_BYTES              20

/* ---- contrl[], as byte offsets of its words ----------------------------------------------------- */
#define CONTRL_OPCODE         0          /* word: contrl[0]                     ($fcaa08)           */
#define CONTRL_N_PTSIN        2          /* word: contrl[1], points in ptsin    ($fc9fbe)           */
#define CONTRL_N_PTSOUT       4          /* word: contrl[2], points answered    ($fcaa0a clr.w)     */
#define CONTRL_N_INTIN        6          /* word: contrl[3]                     ($fcd70e)           */
#define CONTRL_N_INTOUT       8          /* word: contrl[4], words answered     ($fcaa0e clr.w)     */
#define CONTRL_SUBFUNCTION    10         /* word: contrl[5], the GDP/escape number ($fcbbda)        */
#define CONTRL_HANDLE         12         /* word: contrl[6]                     ($fcaa04)           */
/* contrl[7..8] and [9..10] carry two LONGWORDS where a function takes pointers: the source and
 * destination MFDB of a raster copy, or the new and the old routine of a vex_* exchange. */
#define CONTRL_POINTER_A      14         /* long ($fd038c source MFDB, $fca6b8 new vector)          */
#define CONTRL_POINTER_B      18         /* long ($fd0390 destination MFDB, $fca6b0 old vector)     */

/* ---- the entry's own RAM -------------------------------------------------------------------------
 * PTSIN is COPIED, capped at 1024 words: past the cap `$fc9f9e` writes VDI_PTSIN_CAP_POINTS into the
 * CALLER's contrl[1] and restores the caller's own count after the dispatch ($fc9fec). */
#define VDI_PTSIN_COPY        0x19da     /* bytes[VDI_PTSIN_COPY_BYTES]: the copy ($fc9faa lea)      */
#define VDI_PTSIN_COPY_BYTES  0x800      /* ($fc9fc8 `move.w #1024,d1`, a count of words)           */
#define VDI_PTSIN_CAP_POINTS  512        /*                                     ($fc9fd2)           */
#define VDI_RESULT            0x171e     /* word: the D0 trap #2 answers; cleared by the dispatcher,
                                          * set by the few functions that answer ($fc9ff4, $fcaa12)  */
/* The VDI's scratch is the BIOS DISK BUFFER: `_dskbufp` is $16da ($fc02dc), and the VDI borrows its
 * kilobyte — `$a006` builds its crossing list there, and the entry's PTSIN copy starts 0x300 in. */
#define VDI_SCRATCH           0x16da     /* ...up to VDI_TEXT_H_ALIGN           ($fca070 lea)       */
#define VDI_TEXT_H_ALIGN      0x1702     /* word: the dispatcher's copy of WS_H_ALIGN ($fcab04)     */
#define VDI_TEXT_V_ALIGN      0x1704     /* word: ...and of WS_V_ALIGN          ($fcab0c)           */
/* A SHARED word: vqt_extent sums a string's width in it ($fce63e, $fce67a) and v_gtext reads it back
 * ($fcd898); the floppy BIOS uses the same word of the disk buffer for its own ($fc3aee). */
#define VDI_EXTENT_SCRATCH    0x1706     /* word                                ($fce63e)           */

/* ---- the workstation list, and the dispatch ------------------------------------------------------ */
#define VDI_PHYS_WORK         0x7f2e     /* the physical workstation, list head ($fcaa28)           */
#define VDI_PHYS_HANDLE       1          /* ...and its handle                   ($fcb7c8)           */
/* v_opnwk and v_opnvwk (`VDI_ROM_V_OPNWK_OPCODE`, `VDI_ROM_V_OPNVWK_OPCODE` in `addrs.h`) are the two opcodes
 * served WITHOUT a handle lookup — they make the workstation ($fcaa18, $fcaa20). */
#define VDI_OPCODE_TABLE      0xfd372c   /* longwords for opcodes 1..39         ($fcab2e)           */
#define VDI_OPCODE_FIRST      1          /*                                     ($fcab1a)           */
#define VDI_OPCODE_LAST       39         /*                                     ($fcab20)           */
#define VDI_OPCODE_TABLE_EXT  0xfd37c8   /* longwords for opcodes 100..131      ($fcab52)           */
#define VDI_OPCODE_EXT_FIRST  100        /*                                     ($fcab3c)           */
#define VDI_OPCODE_EXT_LAST   131        /*                                     ($fcab42)           */
/* ...and the two SUB-DISPATCHERS behind an opcode, by contrl[5]. Escape (opcode 5, `$fc427a`) indexes a
 * table of WORD offsets from the table itself; the GDP (opcode 11, `$fcbbcc`) a C switch of longwords,
 * whose arms are inline in `$fcbbcc`. `test_vdi_staging.py` resolves an `addrs.h` `<NAME>_SUBFUNCTION`
 * through these. */
#define VDI_ESCAPE_TABLE      0xfc4298   /* word offsets, sub-functions 0..VDI_ESCAPE_LAST ($fc4290) */
#define VDI_ESCAPE_LAST       19         /*                                     ($fc4288 cmp.w #19) */
#define VDI_GDP_FIRST         1          /*                                     ($fcbbf0 ble)       */
#define VDI_GDP_LAST          10         /*                                     ($fcbbf4 cmpi.w #11) */

/* ---- the WORKSTATION record (308 bytes) ---------------------------------------------------------
 * One per open workstation, `Malloc(308)` for a virtual one ($fcd61a), linked by WS_NEXT. The citation
 * is the store or load that fixes each field; `$fca9f6` (the dispatcher's copies into the Line-A
 * variables) and `$fcd402` (init_wk, which fills a new one) between them reach nearly all of it. */
#define WS_CHUP               0          /* word: text rotation, 1/10 degree    ($fcab14)           */
#define WS_CLIP               2          /* word: clipping on                   ($fcaa46)           */
#define WS_CUR_FONT           4          /* long: font header in use            ($fcaace)           */
#define WS_DDA_INC            8          /* word: text scaling increment        ($fcaab6)           */
#define WS_MULTIFILL          10         /* word: user pattern is multi-plane   ($fcaa96)           */
#define WS_PATMSK             12         /* word                                ($fcaa86)           */
#define WS_PATPTR             14         /* long                                ($fcaa7e)           */
#define WS_PTS_MODE           18         /* word: 1 = height set by vst_point   ($fce284)           */
#define WS_SCRTCHP            20         /* long                                ($fcaaf4)           */
#define WS_SCRPT2             24         /* word                                ($fcaaec)           */
#define WS_STYLE              26         /* word: text effects                  ($fcaafc)           */
#define WS_T_SCLSTS           28         /* word                                ($fcaabe)           */
#define WS_FILL_COLOR         30         /* word: mapped colour                 ($fcd51a)           */
#define WS_FILL_INDEX         32         /* word: fill style index              ($fcd4fc)           */
#define WS_FILL_PER           34         /* word: fill outlined                 ($fcd53a)           */
#define WS_FILL_STYLE         36         /* word: fill interior 0..4            ($fcd4c4)           */
#define WS_H_ALIGN            38         /* word                                ($fcab04)           */
#define WS_HANDLE             40         /* word                                ($fcaa2e)           */
#define WS_LINE_BEG           42         /* word: line start end-style          ($fcd532)           */
#define WS_LINE_COLOR         44         /* word: mapped colour                 ($fcd44a)           */
#define WS_LINE_END           46         /* word: line end end-style            ($fcd536)           */
#define WS_LINE_INDEX         48         /* word: line style, 0-based           ($fcd42c)           */
#define WS_LINE_WIDTH         50         /* word                                ($fcd52a)           */
#define WS_LOADED_FONTS       52         /* long: first GDOS-loaded font        ($fcaaa6)           */
#define WS_MARK_COLOR         56         /* word: mapped colour                 ($fcd480)           */
#define WS_MARK_HEIGHT        58         /* word                                ($fcd4a4)           */
#define WS_MARK_INDEX         60         /* word: marker type, 0-based          ($fcd462)           */
#define WS_MARK_SCALE         62         /* word                                ($fcd4ac)           */
#define WS_NEXT               64         /* long: next workstation, 0 ends      ($fcaa34)           */
#define WS_NUM_FONTS          68         /* word                                ($fcaaae)           */
#define WS_SCALED             70         /* word: text is scaled                ($fcaac6)           */
#define WS_SCRATCH_HEAD       72         /* bytes[FONT_HEADER_BYTES]: the scaled header ($fce128)   */
#define WS_TEXT_COLOR         162        /* word: mapped colour                 ($fcd4a0)           */
#define WS_UD_LS              164        /* word: user line style               ($fcb4b2)           */
#define WS_UD_PATRN           166        /* words[64]: up to 4 planes x 16 rows ($fcd59c lea)       */
#define WS_V_ALIGN            294        /* word                                ($fcab0c)           */
#define WS_WRT_MODE           296        /* word: write mode 0..3               ($fcaa76)           */
#define WS_XFM_MODE           298        /* word: coordinate system (intin[10]) ($fcd51e)           */
#define WS_XMN_CLIP           300        /* word                                ($fcaa56)           */
#define WS_XMX_CLIP           302        /* word                                ($fcaa66)           */
#define WS_YMN_CLIP           304        /* word                                ($fcaa5e)           */
#define WS_YMX_CLIP           306        /* word                                ($fcaa6e)           */
#define WS_BYTES              308        /*                                     ($fcd61a Malloc)    */

/* ---- the tables' sizes, and the WORD INDEXES of the entries the ROM names ------------------------ */
#define VDI_DEV_TAB_WORDS     45         /* v_opnwk's intout                    ($fcb6b0 cmp.w #45) */
#define VDI_INQ_TAB_WORDS     45         /* vq_extnd's intout                   ($fcb6ca)           */
#define VDI_SIZ_TAB_WORDS     12         /* v_opnwk's ptsout, six points        ($fcb6ee cmp.w #12) */
#define VDI_REQ_COL_COMPONENTS 3         /* per colour: R, G, B                 ($fcb89a..$fcb8a0)  */
#define VDI_REQ_COL_WORDS     48         /* sixteen colours, to SIZ_TAB         ($fcb882, $27a8)    */
#define VDI_MAP_COL_ENTRIES   16         /* one word per VDI colour index       ($fd370c follows)   */
#define VDI_DEV_TAB_FACES_INDEX 10       /* the dispatcher's copy of WS_NUM_FONTS ($fcaaae -> $26fa) */
#define VDI_DEV_TAB_COLOURS_INDEX 13     /* the bound every colour index is tested against ($fcad98) */
#define VDI_INQ_TAB_MAX_VERTICES_INDEX 14 /*                                    ($fcb6d0 -> $26a8)  */
#define VDI_INQ_TAB_CLIP_INDEX 19        /* the dispatcher's copy of WS_CLIP    ($fcaa50 -> $26b2)  */

/* ---- the ROM data the VDI reads, $fd32f4..$fd39f5 ---------------------------------------------- */
#define VDI_MAX_VERTICES_DEFAULT 0xfd32f4 /* word -> INQ_TAB[14]                ($fcb6d0)           */
#define VDI_LINE_STYLES       0xfd32f6   /* the style masks; [0] is WS_UD_LS's default ($fcd5b2)    */
#define VDI_UD_PATTERN_DEFAULT 0xfd3304  /* 16 words -> WS_UD_PATRN             ($fcd596)           */
#define VDI_FILL_PATTERNS     0xfd3324   /* the pattern tables st_fl_ptr indexes ($fcc9f8)          */
#define VDI_DEV_TAB_DEFAULT   0xfd3598   /* VDI_DEV_TAB_WORDS                   ($fcb69c)           */
#define VDI_SIZ_TAB_DEFAULT   0xfd35f2   /* VDI_SIZ_TAB_WORDS                   ($fcb6da)           */
#define VDI_INQ_TAB_DEFAULT   0xfd360a   /* VDI_INQ_TAB_WORDS                   ($fcb6b6)           */
#define VDI_MAP_COL           0xfd36ec   /* VDI index -> hardware pen           ($fcd444)           */
#define VDI_REV_MAP_COL       0xfd370c   /* ...and back                         ($fcbda0)           */
#define VDI_SINE_TABLE        0xfd3848   /* isin's per-degree table             ($fcabfe)           */
#define VDI_ISIN_SWITCH       0xfd3900   /* switch tables, one per C `switch`:  ($fcabd0)           */
#define VDI_VSIN_MODE_SWITCH  0xfd3914   /*                                     ($fcb3e2)           */
#define VDI_VQIN_MODE_SWITCH  0xfd3928   /*                                     ($fcb448)           */
#define VDI_MARKER_SHAPES     0xfd393c   /* v_pmarker's shape table             ($fcbb16)           */
#define VDI_GDP_SWITCH        0xfd3954   /*                                     ($fcbd6a)           */
#define VDI_FILL_STYLE_SWITCH 0xfd397c   /*                                     ($fcca6a)           */
#define VDI_GTEXT_SWITCH      0xfd3990   /*                                     ($fcd9ea)           */
#define VDI_INITMOUS_PARAMS   0xfd39a8   /* the parameter block for XBIOS Initmous ($fca85e pea)    */
#define VDI_DEFAULT_MOUSE_FORM 0xfd39ac  /* the arrow                           ($fca81c)           */
/* ...and one table before that range: vq_color's 3-bit shifter level -> per-mille, eight words. */
#define VDI_VQ_COLOR_LEVELS   0xfd2f22   /*                                     ($fd2efc)           */
/* The value WS_FILL_STYLE holds for the user-defined pattern — the one interior whose planes the
 * dispatcher copies into LINEA_MULTIFILL. A VALUE of the field, not a field. */
#define VDI_INTERIOR_USER     4          /*                                     ($fcaa8e cmpi.w #4) */

/* ---- the reconstructed functions --------------------------------------------------------------- */
void vdi_vsf_perimeter(uint8_t *image);

/* $a000, whose answer is FOUR registers: `results` gets D0, A0, A1, A2 in that order, and D0 is
 * also returned. */
uint32_t linea_init(uint8_t *image, uint32_t *results);

#endif /* TOS102US_VDI_VDI_H */
