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

/* GUARDED as `addrs.h` is: `src/vdi/palette.S` reads the ROM tables below, and everything outside the
 * guards is a plain integer `#define` both languages read. */
#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"
#include "vdi/linea.h"

/* An Alcyon `int`: every element of contrl/intin/ptsin/intout/ptsout, and of the ROM's word tables. */
#define VDI_WORD_BYTES        2
/* ...and a longword: a pointer, as the Line-A variables and the font ring hold one. */
#define VDI_LONG_BYTES        4

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
#define CONTRL_POINTER_A      14         /* long ($fd038c source MFDB, $fca6b8 new vector, $fced36 text-effects buffer) */
#define CONTRL_POINTER_B      18         /* long ($fd0390 destination MFDB, $fca6b0 old vector)     */
/* ...and vst_load_fonts' own reading of contrl[7..11], GDOS's call: the text-effects buffer (CONTRL_POINTER_A),
 * the offset of its second half, and the first header of the chain of loaded fonts — which runs one word
 * PAST the eleven the other functions use. */
#define CONTRL_FONT_SCRPT2    18         /* word: -> WS_SCRPT2                  ($fced30)           */
#define CONTRL_FONT_CHAIN     20         /* long: -> WS_LOADED_FONTS            ($fced3c)           */

/* ---- the entry's own RAM -------------------------------------------------------------------------
 * PTSIN is COPIED, capped at 1024 words: past the cap `$fc9f9e` writes VDI_PTSIN_CAP_POINTS into the
 * CALLER's contrl[1] and restores the caller's own count after the dispatch ($fc9fec). */
#define VDI_PTSIN_COPY        0x19da     /* bytes[VDI_PTSIN_COPY_BYTES]: the copy ($fc9faa lea)      */
#define VDI_PTSIN_COPY_BYTES  0x800      /* ($fc9fc8 `move.w #1024,d1`, a count of words)           */
#define VDI_PTSIN_CAP_POINTS  512        /*                                     ($fc9fd2)           */
#define VDI_RESULT            0x171e     /* word: the D0 trap #2 answers; cleared by the dispatcher,
                                          * set by the few functions that answer ($fc9ff4, $fcaa12)  */
#define VDI_RESULT_SET        1          /* the one value those functions store  ($fcae46 move.w #1) */
/* The VDI's scratch is the BIOS DISK BUFFER: `_dskbufp` is $16da ($fc02dc), and the VDI borrows its
 * kilobyte — `$a006` builds its crossing list there, and the entry's PTSIN copy starts 0x300 in. */
#define VDI_SCRATCH           0x16da     /* ...up to VDI_TEXT_H_ALIGN           ($fca070 lea)       */
#define VDI_TEXT_H_ALIGN      0x1702     /* word: the dispatcher's copy of WS_H_ALIGN ($fcab04)     */
#define VDI_TEXT_V_ALIGN      0x1704     /* word: ...and of WS_V_ALIGN          ($fcab0c)           */
/* A SHARED word: vqt_extent sums a string's width in it ($fce63e, $fce67a) and v_gtext reads it back
 * ($fcd898); the floppy BIOS uses the same word of the disk buffer for its own ($fc3aee). */
#define VDI_EXTENT_SCRATCH    0x1706     /* word                                ($fce63e)           */
/* ...and the word after it, where vqt_extent builds the string's HEIGHT before answering both. */
#define VDI_EXTENT_HEIGHT_SCRATCH 0x1708 /* word                                ($fce6fc)           */
/* The text-effects buffer a workstation's WS_SCRTCHP starts at — init_wk and vst_unload_fonts both
 * store this constant ($fcd570, $fcedb4) — and the ROM word its WS_SCRPT2 starts at, which sits in
 * vst_unload_fonts' own tail rather than in the data block ($fcd568, $fcedac: 204). */
#define VDI_TEXT_SCRATCH      0x17c6     /* ($fcedb4 move.l #$17c6)                                 */
#define VDI_SCRPT2_DEFAULT    0xfcedce   /* ROM ($fcedac move.w $fcedce)                            */

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
/* ...its two values the VDI tells apart. NDC, normalised coordinates, whose y runs up: vst_height turns a
 * requested height into a distance from the bottom row ($fce022 `tst.w 298(a0)`). RC, raster coordinates:
 * below it gdp_ell measures its y radius up from the last row instead ($fcc774 cmpi.w #2 / bge). VALUES of
 * the field, not fields. */
#define VDI_XFM_MODE_NDC      0
#define VDI_XFM_MODE_RC       2
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
#define VDI_INQ_TAB_SPEED_INDEX 6        /* the drawing speed vq_extnd answers  ($fcb97a 12(a0))    */
#define VDI_DEV_TAB_MAX_X_INDEX 0        /* the last pixel column               ($fcb508 -> $26e6)  */
#define VDI_DEV_TAB_MAX_Y_INDEX 1        /* ...and row                          ($fcb520 -> $26e8)  */
/* A pixel's width and height in microns: the device's aspect, which the wide lines scale by. */
#define VDI_DEV_TAB_PIXEL_WIDTH_INDEX 3  /*                                     ($fcca9a -> $26ec)  */
#define VDI_DEV_TAB_PIXEL_HEIGHT_INDEX 4 /*                                     ($fccaa2 -> $26ee)  */
#define VDI_INQ_TAB_EFFECTS_INDEX 2      /* the text effects the device has     ($fce3be -> $2690)  */
#define VDI_INQ_TAB_PLANES_INDEX 4       /*                                     ($fcd71e -> $2694)  */
#define VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX 6 /*                                   ($fcacda -> $27b4)  */
#define VDI_SIZ_TAB_MIN_MARK_WIDTH_INDEX 8 /*                                   ($fcae34 -> $27b8)  */
#define VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX 9 /*                                  ($fcadde -> $27ba)  */
#define VDI_SIZ_TAB_MAX_MARK_HEIGHT_INDEX 11 /*                                 ($fcadee -> $27be)  */
/* ...and the character sizes text_init measures over the system face (`src/vdi/text.c`). */
#define VDI_SIZ_TAB_MIN_CHAR_WIDTH_INDEX 0 /*                                   ($fcdea4 -> $27a8)  */
#define VDI_SIZ_TAB_MIN_CHAR_HEIGHT_INDEX 1 /*                                  ($fcdeac -> $27aa)  */
#define VDI_SIZ_TAB_MAX_CHAR_WIDTH_INDEX 2 /*                                   ($fcdeb4 -> $27ac)  */
#define VDI_SIZ_TAB_MAX_CHAR_HEIGHT_INDEX 3 /*                                  ($fcdeba -> $27ae)  */
#define VDI_DEV_TAB_CHAR_HEIGHTS_INDEX 5 /* the system face's fonts, counted    ($fcdfa0 -> $26f0)  */
/* ...and the entries v_opnwk patches for a mode the defaults are not (`vdi/workstation.h`), with init_wk's
 * line width. */
#define VDI_DEV_TAB_COLOUR_CAPABLE_INDEX 35 /* 0 = no colour                    ($fcb782 -> $272c)  */
#define VDI_DEV_TAB_PALETTE_INDEX 39     /* colours the palette can show        ($fcb788 -> $2734)  */
#define VDI_INQ_TAB_BACKGROUNDS_INDEX 1  /* background colours                  ($fcb790 -> $268e)  */
#define VDI_INQ_TAB_LUT_INDEX 5          /* 1 = a colour look-up table          ($fcb7a0 -> $2696)  */
#define VDI_SIZ_TAB_MIN_LINE_WIDTH_INDEX 4 /*                                   ($fcd52a -> $27b0)  */

/* ---- the ROM data the VDI reads, $fd32f4..$fd39f5 ---------------------------------------------- */
#define VDI_MAX_VERTICES_DEFAULT 0xfd32f4 /* word -> INQ_TAB[14]                ($fcb6d0)           */
#define VDI_LINE_STYLES       0xfd32f6   /* the style masks; [0] is WS_UD_LS's default ($fcd5b2)    */
#define VDI_UD_PATTERN_DEFAULT 0xfd3304  /* 16 words -> WS_UD_PATRN             ($fcd596)           */
/* The pattern tables st_fl_ptr indexes, starting at VDI_PATTERNS_UPPER ($fcc9f8): FOUR, each a ROW MASK
 * word (rows - 1, what st_fl_ptr stores as WS_PATMSK) and then its patterns, (mask + 1) rows each; a
 * style index picks a table by a threshold and is rebased into it. Then the one-row HOLLOW and SOLID
 * "patterns", whose mask st_fl_ptr leaves at 0. */
#define VDI_PATTERNS_UPPER    0xfd3324   /* pattern styles 9..24, 16 x 8 rows ($fcc9f8 mask)       */
#define VDI_PATTERNS_LOWER    0xfd3426   /* pattern styles 1..8, 8 x 4 rows     ($fcc9dc mask)      */
#define VDI_PATTERNS_LOWER_COUNT 8       /*                                     ($fcc9d6 cmp.w #8)  */
#define VDI_HATCHES_LOWER     0xfd3468   /* hatch styles 1..6, 6 x 8 rows       ($fcca1c mask)      */
#define VDI_HATCHES_LOWER_COUNT 6        /*                                     ($fcca16 cmp.w #6)  */
#define VDI_HATCHES_UPPER     0xfd34ca   /* hatch styles 7..12, 6 x 16 rows     ($fcca38 mask)      */
#define VDI_PATTERN_TABLE_HEADER_BYTES 2 /* the mask word the rows follow     ($fcc9f0 +2)        */
#define VDI_PATTERN_HOLLOW    0xfd358c   /* one row, $0000                      ($fcc9c2)           */
#define VDI_PATTERN_SOLID     0xfd358e   /* one row, $ffff                      ($fcc9cc)           */
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
/* ...and just before THAT, the highest colour index per plane count: bytes indexed by LINEA_PLANES
 * itself, so entry 0 is the low byte of the `rts` in front of them ($fd2de0 `(pc,d1.w)` at $fd2e3f). */
#define VDI_PEN_MASKS         0xfd2e3f   /*                                     ($fd2de0, $fd2ea8)  */
/* LINEA_STYLE's text-effect bits: vqt_fontinfo tests two of them in its low byte, TextBlt all four. */
#define VDI_STYLE_THICKEN_MASK 0x0001    /* bold                                ($fce984 btst #0)   */
#define VDI_STYLE_LIGHTEN_MASK 0x0002    /* light                               ($fd2424 btst #1)   */
#define VDI_STYLE_SKEW_MASK   0x0004     /* italic                              ($fce99a btst #2)   */
#define VDI_STYLE_OUTLINE_MASK 0x0010    /* outlined                            ($fd1ea2 btst #4)   */
/* ...and the one TextBlt never reads: v_gtext draws the underline itself, a line a row. */
#define VDI_STYLE_UNDERLINE_MASK 0x0008  /* underlined                          ($fcdd00 btst #3)   */
/* The value WS_FILL_STYLE holds for the user-defined pattern — the one interior whose planes the
 * dispatcher copies into LINEA_MULTIFILL. A VALUE of the field, not a field. */
#define VDI_INTERIOR_USER     4          /*                                     ($fcaa8e cmpi.w #4) */
/* The value WS_LINE_BEG / WS_LINE_END hold for a plain SQUARE end (bit 0 set asks for an arrowhead). A VALUE
 * of the fields, not a field. */
#define VDI_LINE_END_SQUARE   0          /*                                     ($fcd0b0 clr.w)     */
/* A point of ptsin / ptsout, or of a frame's own point list: (x, y), two words. */
#define VDI_POINT_BYTES       4
#define VDI_POINT_Y           2          /* y, the second word                                      */
#define VDI_POINT_WORDS       (VDI_POINT_BYTES / VDI_WORD_BYTES) /* a word index into a point list steps by it */
/* ...and the other four, in st_fl_ptr's switch order ($fd397c). */
#define VDI_INTERIOR_HOLLOW   0          /*                                     ($fcc9c2)           */
#define VDI_INTERIOR_SOLID    1          /*                                     ($fcc9cc)           */
#define VDI_INTERIOR_PATTERN  2          /*                                     ($fcaf6c cmpi.w #2) */
#define VDI_INTERIOR_HATCH    3          /*                                     ($fcca16)           */
/* The value WS_FILL_PER is tested for — EXACTLY 1, so any other value, 2 or -1, leaves a fill unoutlined — and
 * stored as ($fcd53a v_opnwk's default, $fcd084 s_fa_attr's outlined fill), and the LN_MASK its outline is drawn
 * in. VALUES, not fields. */
#define VDI_FILL_PERIMETER_ON 1          /*                                     ($fcbc16, $fcc252 cmpi.w #1) */
#define VDI_PERIMETER_LINE_MASK 0xffff   /* solid                               ($fcbc1e, $fcc25a)  */

#ifndef __ASSEMBLER__
#include "machine.h"
#include "m68k_idioms.h"

/* ---- THE CALL, as a function reaches it: through the Line-A pointers -----------------------------
 * The one set of accessors every VDI function's C uses. Each reads its Line-A pointer AT THE CALL, so a
 * read placed after a store sees that store — the ROM's own order, which only shows when the arrays
 * overlap each other or the Line-A variables. A core that reads a pointer once and keeps it, as a ROM
 * routine that loads it into a register does, holds it in a local from `linea_pointer`.
 *
 * THE 24-BIT BUS. The pointers are a program's longwords, stored by the `trap #2` entry as they came, top
 * byte and all (`src/vdi/entry.c`) — and so is a workstation record's address. Every accessor below that
 * DEREFERENCES one sums the element's or field's offset FIRST and only then puts the address on the bus,
 * as the 68000's `d16(An)` / `(An,Dn)` does (`bus_dereference`: free on target; `test_vdi_bus_pointers.py`).
 * `call_element` and `current_work` answer the raw sum, for a core that carries it on. NEW code reaching a
 * caller's word through a held pointer uses m68k_idioms.h's `bus_word` / `set_bus_word` (they also refuse an odd
 * address); `caller_word` below is the older reader that only masks. */
static inline uint32_t linea_pointer(const uint8_t *image, uint32_t variable)
{
    return be32(image + variable);
}

/* `array[index]`'s address, for `array` one of LINEA_CONTRL/INTIN/PTSIN/INTOUT/PTSOUT. */
static inline uint32_t call_element(const uint8_t *image, uint32_t array, unsigned index)
{
    return linea_pointer(image, array) + index * VDI_WORD_BYTES;
}

static inline int16_t intin_word(const uint8_t *image, unsigned index)
{
    return (int16_t)be16(image + bus_dereference(call_element(image, LINEA_INTIN, index)));
}

static inline int16_t ptsin_word(const uint8_t *image, unsigned index)
{
    return (int16_t)be16(image + bus_dereference(call_element(image, LINEA_PTSIN, index)));
}

static inline void answer_intout(uint8_t *image, unsigned index, uint16_t value)
{
    wr16(image + ram_store(bus_dereference(call_element(image, LINEA_INTOUT, index)), M68K_WORD_BYTES), value);
}

static inline void answer_ptsout(uint8_t *image, unsigned index, uint16_t value)
{
    wr16(image + ram_store(bus_dereference(call_element(image, LINEA_PTSOUT, index)), M68K_WORD_BYTES), value);
}

/* A word of contrl by its byte offset (CONTRL_*), read or stored through the pointer at the call. */
static inline int16_t contrl_word(const uint8_t *image, uint32_t offset)
{
    return (int16_t)be16(image + bus_dereference(linea_pointer(image, LINEA_CONTRL) + offset));
}

static inline void set_contrl_word(uint8_t *image, uint32_t offset, uint16_t value)
{
    wr16(image + ram_store(bus_dereference(linea_pointer(image, LINEA_CONTRL) + offset), M68K_WORD_BYTES), value);
}

/* contrl[2] and contrl[4], each written only by the functions that answer that array. */
static inline void answer_points(uint8_t *image, uint16_t points)
{
    set_contrl_word(image, CONTRL_N_PTSOUT, points);
}

static inline void answer_words(uint8_t *image, uint16_t words)
{
    set_contrl_word(image, CONTRL_N_INTOUT, words);
}

/* ---- a WORD of the VDI's own RAM — a Line-A variable, a scratch word — by its address ------------
 * Signed where the ROM's Alcyon C reads an `int` (`ram_word`), unsigned where its hand 68000 reads a
 * pattern or a count (`ram_uword`). */
static inline int16_t ram_word(const uint8_t *image, uint32_t at)
{
    return (int16_t)be16(image + at);
}

static inline uint16_t ram_uword(const uint8_t *image, uint32_t at)
{
    return be16(image + at);
}

static inline void set_ram_word(uint8_t *image, uint32_t at, uint16_t value)
{
    wr16(image + at, value);
}

static inline void add_ram_word(uint8_t *image, uint32_t at, uint16_t delta)
{
    wr16(image + at, (uint16_t)(be16(image + at) + delta));
}

/* ...and a word of a CALLER's array at an address a core holds from `linea_pointer` (a ptsin cursor it
 * walks), put on the bus as the accessors above put theirs — where `ram_word`'s address is the VDI's own. */
static inline int16_t caller_word(const uint8_t *image, uint32_t at)
{
    return (int16_t)be16(image + bus_dereference(at));
}

/* `table_entry` — the address of a sign-extended table index — is m68k_idioms.h's (the AES's object layer shares it). */

/* ...and word `index` of a word array (a table, ptsin, the fill queue). */
static inline uint32_t word_entry(uint32_t array, int32_t index)
{
    return table_entry(array, index, VDI_WORD_BYTES);
}

/* The workstation the dispatcher made current, by its record's address. */
static inline uint32_t current_work(const uint8_t *image)
{
    return linea_pointer(image, LINEA_CUR_WORK);
}

/* A word of the workstation record at `work` (WS_*), for a routine that HOLDS the record as the ROM holds it
 * in a register (`movea.l $27ca,a4` once) — signed, as its Alcyon `int`. */
static inline int16_t work_word(const uint8_t *image, uint32_t work, uint32_t field)
{
    return (int16_t)be16(image + bus_dereference(work + field));
}

/* ...and a store into it. */
static inline void set_work_word(uint8_t *image, uint32_t work, uint32_t field, uint16_t value)
{
    wr16(image + ram_store(bus_dereference(work + field), M68K_WORD_BYTES), value);
}

/* ...and a longword store (a pointer field). */
static inline void set_work_long(uint8_t *image, uint32_t work, uint32_t field, uint32_t value)
{
    wr32(image + ram_store(bus_dereference(work + field), M68K_LONG_BYTES), value);
}

/* ...and a store into the CURRENT workstation's, LINEA_CUR_WORK read at the store. */
static inline void set_current_work_word(uint8_t *image, uint32_t field, uint16_t value)
{
    wr16(image + ram_store(bus_dereference(current_work(image) + field), M68K_WORD_BYTES), value);
}

/* ...and a read of one, LINEA_CUR_WORK read at the read — unsigned, for a mode compared or a pen passed on. */
static inline uint16_t current_work_word(const uint8_t *image, uint32_t field)
{
    return be16(image + bus_dereference(current_work(image) + field));
}

/* ---- a word of a Line-A DEVICE TABLE (LINEA_DEV_TAB / SIZ_TAB / INQ_TAB) by its index ----------------
 * Signed where the ROM's Alcyon C reads an `int` (`table_word`), unsigned where it compares one as a count
 * (`table_uword`) — `ram_word`'s pair, over the table's own index. */
static inline int16_t table_word(const uint8_t *image, uint32_t table, unsigned index)
{
    return ram_word(image, table + index * VDI_WORD_BYTES);
}

static inline uint16_t table_uword(const uint8_t *image, uint32_t table, unsigned index)
{
    return ram_uword(image, table + index * VDI_WORD_BYTES);
}

static inline void set_table_word(uint8_t *image, uint32_t table, unsigned index, uint16_t value)
{
    set_ram_word(image, table + index * VDI_WORD_BYTES, value);
}

/* The drawing colour as every VDI caller of a rasterizer stages it: COLBITn = colour & (1 << n) — the
 * plane's BIT, not 0/1 ($fcba16.., $fcc0fe..). */
#define VDI_COLBIT_PLANES     4          /* COLBIT0..COLBIT3                                        */

static inline void set_colour_bits(uint8_t *image, uint16_t colour)
{
    unsigned plane;

    for (plane = 0; plane < VDI_COLBIT_PLANES; plane++)
        wr16(image + LINEA_COLBIT0 + plane * VDI_WORD_BYTES, colour & (uint16_t)(1u << plane));
}

/* ...staged from the current workstation's fill pen, as the fill and area callers stage it. ALWAYS inlined:
 * as a plain inline GCC lays out contour_fill's tail differently, and one of its paths gains a `bra.w`
 * (measured on the shipped flags) — the helper is to change the spelling, not the code. */
static inline __attribute__((always_inline)) void set_fill_colour_bits(uint8_t *image)
{
    set_colour_bits(image, current_work_word(image, WS_FILL_COLOR));
}

/* Whether LINEA_STYLE asks for `effect` (a VDI_STYLE_* mask) — the text routines' `btst` on its low byte. */
static inline int style_asks_for(const uint8_t *image, uint16_t effect)
{
    return (be16(image + LINEA_STYLE) & effect) != 0;
}

/* `words` words from `from` to `to`, in ascending order, one `move.w (a5)+,(a4)+` at a time. Host pointers: a
 * caller holding image addresses passes `image + address`. */
static inline void copy_words(uint8_t *to, const uint8_t *from, unsigned words)
{
    for (unsigned word = 0; word < words; word++)
        wr16(to + word * VDI_WORD_BYTES, be16(from + word * VDI_WORD_BYTES));
}

/* A point (x, y) copied from `from` to `to`: x first, then y (`move.w (a4),8(a5) / move.w 2(a4),10(a5)`). */
static inline void copy_point(uint8_t *image, uint32_t to, uint32_t from)
{
    wr16(image + to, be16(image + from));
    wr16(image + to + VDI_POINT_Y, be16(image + from + VDI_POINT_Y));
}

/* ---- the reconstructed functions --------------------------------------------------------------- */
void vdi_vsf_perimeter(uint8_t *image);

/* $a000, whose answer is FOUR registers: `results` gets D0, A0, A1, A2 in that order (the order
 * `test_vdi_linea_init.py` declares them in), and D0 is also returned. */
enum { LINEA_INIT_D0, LINEA_INIT_A0, LINEA_INIT_A1, LINEA_INIT_A2, LINEA_INIT_ANSWERS };
uint32_t linea_init(uint8_t *image, uint32_t *results);
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_VDI_H */
