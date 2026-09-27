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
#define VDI_RESULT_SET        1          /* the one value those functions store  ($fcae46 move.w #1) */
/* The VDI's scratch is the BIOS DISK BUFFER: `_dskbufp` is $16da ($fc02dc), and the VDI borrows its
 * kilobyte — `$a006` builds its crossing list there, and the entry's PTSIN copy starts 0x300 in. */
#define VDI_SCRATCH           0x16da     /* ...up to VDI_TEXT_H_ALIGN           ($fca070 lea)       */
#define VDI_TEXT_H_ALIGN      0x1702     /* word: the dispatcher's copy of WS_H_ALIGN ($fcab04)     */
#define VDI_TEXT_V_ALIGN      0x1704     /* word: ...and of WS_V_ALIGN          ($fcab0c)           */
/* A SHARED word: vqt_extent sums a string's width in it ($fce63e, $fce67a) and v_gtext reads it back
 * ($fcd898); the floppy BIOS uses the same word of the disk buffer for its own ($fc3aee). */
#define VDI_EXTENT_SCRATCH    0x1706     /* word                                ($fce63e)           */
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
#define VDI_INQ_TAB_EFFECTS_INDEX 2      /* the text effects the device has     ($fce3be -> $2690)  */
#define VDI_INQ_TAB_PLANES_INDEX 4       /*                                     ($fcd71e -> $2694)  */
#define VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX 6 /*                                   ($fcacda -> $27b4)  */
#define VDI_SIZ_TAB_MIN_MARK_WIDTH_INDEX 8 /*                                   ($fcae34 -> $27b8)  */
#define VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX 9 /*                                  ($fcadde -> $27ba)  */
#define VDI_SIZ_TAB_MAX_MARK_HEIGHT_INDEX 11 /*                                 ($fcadee -> $27be)  */

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
/* Two of LINEA_STYLE's text-effect bits, as vqt_fontinfo tests them in its low byte. */
#define VDI_STYLE_THICKEN_MASK 0x0001    /* bold                                ($fce984 btst #0)   */
#define VDI_STYLE_SKEW_MASK   0x0004     /* italic                              ($fce99a btst #2)   */
/* The value WS_FILL_STYLE holds for the user-defined pattern — the one interior whose planes the
 * dispatcher copies into LINEA_MULTIFILL. A VALUE of the field, not a field. */
#define VDI_INTERIOR_USER     4          /*                                     ($fcaa8e cmpi.w #4) */
/* ...and the other four, in st_fl_ptr's switch order ($fd397c). */
#define VDI_INTERIOR_HOLLOW   0          /*                                     ($fcc9c2)           */
#define VDI_INTERIOR_SOLID    1          /*                                     ($fcc9cc)           */
#define VDI_INTERIOR_PATTERN  2          /*                                     ($fcaf6c cmpi.w #2) */
#define VDI_INTERIOR_HATCH    3          /*                                     ($fcca16)           */

#ifndef __ASSEMBLER__
#include "machine.h"

/* ---- THE CALL, as a function reaches it: through the Line-A pointers -----------------------------
 * The one set of accessors every VDI function's C uses. Each reads its Line-A pointer AT THE CALL, so a
 * read placed after a store sees that store — the ROM's own order, which only shows when the arrays
 * overlap each other or the Line-A variables. A core that reads a pointer once and keeps it, as a ROM
 * routine that loads it into a register does, holds it in a local from `linea_pointer`. */
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
    return (int16_t)be16(image + call_element(image, LINEA_INTIN, index));
}

static inline int16_t ptsin_word(const uint8_t *image, unsigned index)
{
    return (int16_t)be16(image + call_element(image, LINEA_PTSIN, index));
}

static inline void answer_intout(uint8_t *image, unsigned index, uint16_t value)
{
    wr16(image + call_element(image, LINEA_INTOUT, index), value);
}

static inline void answer_ptsout(uint8_t *image, unsigned index, uint16_t value)
{
    wr16(image + call_element(image, LINEA_PTSOUT, index), value);
}

/* contrl[2] and contrl[4], each written only by the functions that answer that array. */
static inline void answer_points(uint8_t *image, uint16_t points)
{
    wr16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_PTSOUT, points);
}

static inline void answer_words(uint8_t *image, uint16_t words)
{
    wr16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTOUT, words);
}

/* The workstation the dispatcher made current, by its record's address. */
static inline uint32_t current_work(const uint8_t *image)
{
    return linea_pointer(image, LINEA_CUR_WORK);
}

/* ---- the reconstructed functions --------------------------------------------------------------- */
void vdi_vsf_perimeter(uint8_t *image);

/* $a000, whose answer is FOUR registers: `results` gets D0, A0, A1, A2 in that order, and D0 is
 * also returned. */
uint32_t linea_init(uint8_t *image, uint32_t *results);
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_VDI_H */
