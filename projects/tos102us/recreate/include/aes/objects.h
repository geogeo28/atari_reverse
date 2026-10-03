/* aes/objects.h — the AES's OBJECT LAYER: the OBJECT record and the blocks its ob_spec points at, the two
 * rectangles, the resource file's header and the resource globals — and the one accessor a tree is walked by.
 *
 * A TREE is an array of 24-byte OBJECTs linked by index: ob_next to the next sibling (the LAST sibling's ob_next
 * is its PARENT), ob_head / ob_tail to the first and last child, -1 for none, the root at index 0. The ROM
 * indexes it as `tree + muls.w #24,obj` then an `adda` of the field ($fea5a6..$fea5ac): the index is a SIGNED
 * word and the sum a 32-bit address, which is `m68k_idioms.h`'s `table_entry` — `object_address` below.
 *
 * Every field carries one ROM access and its WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"), which `test/aes.py`
 * parses; frozen the way `gemdos/fs.h` is — the only permitted edits are adding a field with its own citation and
 * adding a named flag or state MASK built from a cited bit (`(1 << *_BIT)`, no width tag: masks are not fields), so
 * every reader shares one spelling rather than redefining it per file. The blocks' fields just_draw reads through its copies of them (`aes/objdraw.h`'s AES_EDBLK, AES_BI, AES_IB) are cited
 * at those copies' addresses; the ones nothing reconstructed reads are not named.
 */
#ifndef TOS102US_AES_OBJECTS_H
#define TOS102US_AES_OBJECTS_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"

/* ---- OBJECT ------------------------------------------------------------------------------------------------ */
#define OB_NEXT               0          /* word: the next sibling, or the parent ($fed3a8 get_par)            */
#define OB_HEAD               2          /* word: the first child, -1 none      ($fea5f8 addq.l #2)            */
#define OB_TAIL               4          /* word: the last child                ($fed3b4 addq.l #4)            */
#define OB_TYPE               6          /* word: G_* in its low byte           ($fea8ec addq.l #6, and.w #$ff) */
#define OB_FLAGS              8          /* word: HIDETREE is bit 7 of its low byte ($fed336, +9 btst #7)      */
#define OB_STATE              10         /* word: SELECTED is bit 0 of its low byte ($fecfee, $fed010 +11)     */
#define OB_SPEC               12         /* long: a colour word, or a block's address ($fea908, $fecf88)       */
#define OB_X                  16         /* word: relative to the parent        ($fea5ac adda.l #16)           */
#define OB_Y                  18         /* word                                ($fea5c0 adda.l #18)           */
#define OB_WIDTH              20         /* word                                ($fda33c addl #20)             */
#define OB_HEIGHT             22         /* word                                ($fda35e adda.l #22)           */
#define OB_BYTES              24         /* ($fea5a6 muls.w #24)                                               */
#define OB_ROOT               0          /* the tree's first object: get_par's `tst.w` ($fed394)               */
#define OB_NIL                (-1)       /* no object: an empty head/tail, get_par of the root ($fed398 moveq #-1) */
#define OB_SPEC_NONE          0xffffffffu /* ob_spec -1: nothing drawn or changed ($fe9ad4, $fea3d2 cmpi.l #-1) */
#define OB_TYPE_MASK          0x00ff     /* ($fea8f0 and.w #255)                                               */
#define OB_FLAG_HIDETREE_BIT  7          /* ...of OB_FLAGS' low byte            ($fed33c btst #7)              */
#define OB_STATE_OUTLINED_BIT 4          /* ...of OB_STATE's low byte           ($fe9316 btst #4)              */
#define OB_STATE_SELECTED_BIT 0          /* ...of OB_STATE's low byte           ($fed022 btst #0)              */
#define OB_FLAG_DEFAULT_BIT   1          /* ...of OB_FLAGS' low byte            ($fed242 btst #1,1(a4))        */
#define OB_FLAG_EXIT_BIT      2          /* ...of OB_FLAGS' low byte            ($fed238 btst #2,1(a4))        */
#define OB_FLAG_EDITABLE_BIT  3          /* ...of OB_FLAGS' low byte: fm_do's fields (find_obj $fe7222 moveq #8) */
#define OB_FLAG_SELECTABLE_BIT 0         /* ...of OB_FLAGS' low byte: fm_button takes it ($fe738a btst #0,-7(a6)) */
#define OB_FLAG_RBUTTON_BIT   4          /* ...of OB_FLAGS' low byte: a radio button ($fe739e btst #4,-7(a6))   */
#define OB_FLAG_TOUCHEXIT_BIT 6          /* ...of OB_FLAGS' low byte: exits on a press ($fe7370 btst #6,-7(a6)) */
#define OB_FLAG_INDIRECT_BIT  0          /* ...of OB_FLAGS' HIGH byte: ob_spec names the spec ($fed204 btst #0,(a4)) */
#define OB_WORD_LOW_BYTE      1          /* a word field's low byte, which a `btst` reads ($fed010 movea.l #11) */
/* The resource format's end-of-tree flag. No ROM instruction cited: the AES walks a tree by its links, and only the
 * batteries' model (`test/aes.py`'s tree_length) reads it — every tree of the snapshot's own resource ends on it. */
#define OB_FLAG_LASTOB        0x0020     /* OB_FLAGS: the tree's last object                                   */
/* The object TYPES whose ob_spec is a colour word and not a block's address: the load's relocation (fix_objects) leaves it. */
#define G_BOX                 20         /* ($fea8f4 cmp.w #20)                                                */
#define G_IBOX                25         /* ($fea8fa cmp.w #25)                                                */
#define G_BOXCHAR             27         /* ($fea900 cmp.w #27)                                                */
/* ...and the rest of the types ob_sst's border switch names (`sub.w #20` / `cmp.w #12`, table $fefd52: G_BOX..G_TITLE). */
#define G_TEXT                21         /* a TEDINFO's thickness               ($fefd56 -> $fed222)           */
#define G_BOXTEXT             22         /* ($fefd5a -> $fed222)                                               */
#define G_BUTTON              26         /* -1, one less for EXIT, one less for DEFAULT ($fefd6a -> $fed236)   */
#define G_FTEXT               29         /* ($fefd76 -> $fed222)                                               */
#define G_FBOXTEXT            30         /* ($fefd7a -> $fed222)                                               */
#define G_TITLE               32         /* a thickness of 1                    ($fefd82 -> $fed21e)           */
/* ...and the types only just_draw's two jump tables tell apart (table $fefba0 / $fefbcc, `sub.w #20` / `#21`). */
#define G_IMAGE               23         /* a BITBLK blitted                    ($fefbd4 -> $fe9cfa)           */
#define G_USERDEF             24         /* a USERBLK's routine called          ($fefbd8 -> $fe9db2)           */
#define G_STRING              28         /* the string path                     ($fe9b2a cmpi.w #28)           */
#define G_ICON                31         /* an ICONBLK drawn                    ($fefbf4 -> $fe9d56)           */
/* The rest of OB_STATE's low byte, beside SELECTED and OUTLINED — just_draw's state block tests each ($fe9e88..). */
#define OB_STATE_CROSSED_BIT  1          /* two diagonals                       ($fe9f9c btst #1)              */
#define OB_STATE_CHECKED_BIT  2          /* a check mark                        ($fe9f6a btst #2)              */
#define OB_STATE_DISABLED_BIT 3          /* dimmed by a pattern                 ($fe9fde btst #3)              */
#define OB_STATE_SHADOWED_BIT 5          /* a shadow below and right            ($fe9ef0 btst #5)              */
/* The masks of those bits the form library tests (`src/aes/fmlib.c`, `src/aes/fmdo.c`): each one its bit's. */
#define OB_FLAG_SELECTABLE    (1 << OB_FLAG_SELECTABLE_BIT)
#define OB_FLAG_DEFAULT       (1 << OB_FLAG_DEFAULT_BIT)
#define OB_FLAG_EXIT          (1 << OB_FLAG_EXIT_BIT)
#define OB_FLAG_EDITABLE      (1 << OB_FLAG_EDITABLE_BIT)
#define OB_FLAG_RBUTTON       (1 << OB_FLAG_RBUTTON_BIT)
#define OB_FLAG_TOUCHEXIT     (1 << OB_FLAG_TOUCHEXIT_BIT)
#define OB_STATE_SELECTED     (1 << OB_STATE_SELECTED_BIT)
#define OB_STATE_DISABLED     (1 << OB_STATE_DISABLED_BIT)
#define OB_STATE_OUTLINED     (1 << OB_STATE_OUTLINED_BIT)

/* ---- the blocks OB_SPEC points at ---------------------------------------------------------------------------
 * rsrc_gaddr's resource types (`$fea742`'s switch, table $fefbf8) name each pointer field: R_TEPTEXT..R_TEPVALID
 * (8..10) and R_IBPMASK..R_IBPTEXT (11..13) are the block's address plus these offsets. */
#define TE_PTEXT              0          /* long: the text                      ($fea78e, R_TEPTEXT's arm)     */
#define TE_PTMPLT             4          /* long: the template                  ($fea7d2 addq.l #4)            */
#define TE_PVALID             8          /* long: the validation string         ($fea7dc addq.l #8)            */
#define TE_FONT               12         /* word: 3 the IBM font, 5 the small   ($fe9cd6 move.w $9c2c: edblk+12) */
#define TE_JUST               16         /* word: 0 left, 1 right, 2 centred    ($fe9cdc move.w $9c30: edblk+16) */
#define TE_COLOR              18         /* word: the colour word gr_crack splits ($fe9b76 move.w $9c32: edblk+18) */
#define TE_THICKNESS          22         /* word: the border's thickness        ($fed224 adda.l #22)           */
#define TE_TXTLEN             24         /* word: the text's length + 1, set by fix_tedinfo ($fea95a addl #24) */
#define TE_TMPLEN             26         /* word: ...and the template's         ($fea978 addl #26)             */
#define TE_BYTES              28         /* ($fea790 moveq #28)                                                */
#define IB_PMASK              0          /* long                                ($fea796, R_IBPMASK's arm)     */
#define IB_PDATA              4          /* long                                ($fea7f6 addq.l #4)            */
#define IB_PTEXT              8          /* long                                ($fea800 addq.l #8)            */
#define IB_CHAR               12         /* word: colours and a character, gr_gicon's ($fe9d86 move.l $c74c: ib+12) */
#define IB_XCHAR              14         /* word: the character's place in the icon ($fe9d86: the same long)  */
#define IB_YCHAR              16         /* word                                ($fe9d80 move.w $c750: ib+16)  */
#define IB_XICON              18         /* word: the icon's GRECT, x first     ($fe9d68 add.l d0,$c752: ib+18) */
#define IB_YICON              20         /* word: ...its y, the same longword   ($fe9d68)                      */
#define IB_XTEXT              26         /* word: the label's GRECT, x first    ($fe9d6e add.l d0,$c75a: ib+26) */
#define IB_YTEXT              28         /* word: ...its y, the same longword   ($fe9d6e)                      */
#define IB_BYTES              34         /* ($fea798 moveq #34)                                                */
#define BI_PDATA              0          /* long                                ($fea79e, R_BIPDATA's arm)     */
#define BI_WB                 4          /* word: the form's width in bytes     ($fe9d1c move.w $c736: bi+4)   */
#define BI_HL                 6          /* word: its height in lines           ($fe9d16 move.w $c738: bi+6)   */
#define BI_X                  8          /* word: the corner blitted from, x first ($fe9d3e move.l $c73a: bi+8) */
#define BI_Y                  10         /* word: ...its y, the same longword   ($fe9d3e)                      */
#define BI_COLOR              12         /* word: the foreground colour         ($fe9d0c move.w $c73e: bi+12)  */
#define BI_BYTES              14         /* ($fea7a0 moveq #14)                                                */
#define UB_CODE               0          /* long: the drawing routine           ($fe9a7e ob_user)              */
#define UB_PARM               4          /* long: its argument                  ($fe9a70)                      */
#define UB_BYTES              8
/* The PARMBLK ob_user builds in its own frame (`link #-34`, the block at -30(a6)) and hands the USERBLK's routine by
 * address — the routine's one argument, which the published GEM calls PARMBLK (pb_*). */
#define PARM_TREE             0          /* long: the tree                      ($fe9a4a move.l 8(a6),-30(a6)) */
#define PARM_OBJECT           4          /* word: the object                    ($fe9a50 move.w 12(a6),-26(a6)) */
#define PARM_PREVSTATE        6          /* word: the state before the change   ($fe9a56 move.l 22(a6),-24(a6)) */
#define PARM_CURRSTATE        8          /* word: ...and after, one longword with it ($fe9a56)                 */
#define PARM_RECT             10         /* bytes[GRECT_BYTES]: the object on the screen ($fe9a5c pea -20(a6), rc_copy) */
#define PARM_CLIP             18         /* bytes[GRECT_BYTES]: the clip        ($fe9a66 pea -12(a6), gsx_gclip) */
#define PARM_PARM             26         /* long: the USERBLK's UB_PARM         ($fe9a70 move.l 4(a0),-4(a6))  */
#define PARM_BYTES            30         /* ($fe9a76 pea -30(a6)): -30(a6) up to the frame's top               */

/* ---- GRECT and ORECT ---------------------------------------------------------------------------------------
 * A GRECT is four words, x y w h; rc_intersect and the rest of the hand-68000 rectangle layer read it at 0..6
 * ($fecd22). An ORECT is a GRECT behind a link — the window's visible-rectangle list, from the pool at
 * `AES_ORECT_POOL`. */
#define GRECT_X               0          /* word                                ($fecd2a cmp.w (a0),d0)        */
#define GRECT_Y               2          /* word                                ($fecd50 cmp.w 2(a0),d0)       */
#define GRECT_W               4          /* word                                ($fecd32 add.w 4(a0),d1)       */
#define GRECT_H               6          /* word                                ($fecd5e add.w 6(a0),d1)       */
#define GRECT_BYTES           8          /* rc_copy's two longwords             ($feccd0)                      */
#define ORECT_LINK            0          /* long                                ($fe5ae0 move.l a4,(a3))       */
#define ORECT_X               4          /* word                                ($fe5ae2)                      */
#define ORECT_Y               6          /* word                                ($fe5afa)                      */
#define ORECT_W               8          /* word                                ($fe5ae8)                      */
#define ORECT_H               10         /* word                                ($fe5b1a)                      */
#define ORECT_BYTES           12         /* ($fe5a76 muls.w #12)                                               */

/* ---- the RESOURCE file: its header, and the globals rsrc_* keep --------------------------------------------
 * Every section's OFFSET from the header is a word of it; `$fea716` reads word `n` of the header and adds the
 * header's address, so the words are spelt by the index `$fea742` hands it, doubled. */
#define RSH_OBJECT            2          /* word: offset of the OBJECTs          ($fea786 moveq #1: word 1)    */
#define RSH_TEDINFO           4          /* word                                ($fea78e moveq #2)             */
#define RSH_ICONBLK           6          /* word                                ($fea796 moveq #3)             */
#define RSH_BITBLK            8          /* word                                ($fea79e moveq #4)             */
#define RSH_FRSTR             10         /* word: the free strings' pointers    ($fea808 move.w #5)            */
#define RSH_FRIMG             16         /* word: the free images' pointers     ($fea81c move.w #8)            */
#define RSH_TRINDEX           18         /* word: the trees' pointers           ($fea876 move.w #9)            */
#define RSH_NOBS              20         /* word: OBJECTs                       ($fea8ca adda.l #20)           */
#define RSH_NTREE             22         /* word: trees                         ($fea896 adda.l #22)           */
#define RSH_NTED              24         /* word: TEDINFOs                      ($fea926 adda.l #24)           */
#define RSH_NIB               26         /* word: ICONBLKs                      ($feabd6 adda.l #26)           */
#define RSH_NBB               28         /* word: BITBLKs                       ($feac02 movea.l #28)          */
#define RSH_NSTRING           30         /* word: free strings                  ($feac1c movea.l #30)          */
#define RSH_NIMAGES           32         /* word: free images                   ($feac36 movea.l #32)          */
#define RSH_RSSIZE            34         /* word: the file's whole length       ($feab44 move.w $c88e,d7)      */
#define RSH_BYTES             36         /* rsrc_load's first read              ($feab32 move.w #36)           */
/* The globals: which application's `global[]` the calls are for, and its header (global[7..8], ap_pmem). */
#define AES_RS_GLOBAL         0x9802     /* long: the caller's global[]         ($feaa3c)                      */
#define AES_RS_HDR            0x9c3c     /* long: its resource header           ($feaa50)                      */
#define AES_RS_INDEX          0x9ba4     /* word: the trindex byte offset       ($fea762)                      */
#define AES_RS_SYSTEM_GLOBAL  0x9806     /* long: the AES's own global[], for its ROM resource ($fda02c)       */
#define AES_RS_STRING         0xb89a     /* rs_str's copy of a free string, and its answer ($fea704 move.l #) */
#define AES_RS_ADDROUT        0x944c     /* long: rsrc_gaddr's answer, for addrout[0] ($fe65a2)                */
#define AES_RS_HEADER_COPY    0xc86c     /* bytes[RSH_BYTES]: rsrc_load's read of the file's header ($feab2c)   */
#define AES_GLOBAL_PMEM       14         /* global[7..8]: the header            ($feaa4a adda.l #14)           */
#define AES_GLOBAL_PTREE      10         /* global[5..6]: the tree table        ($fea776 adda.l #10)           */
#define AES_GLOBAL_LMEM       18         /* global[9]: the resource's length    ($feabc2 adda.l #18)           */

#ifndef __ASSEMBLER__
#include "machine.h"
#include "m68k_idioms.h"

/* The address of field `field` of object `object` of the tree at `tree`, as the ROM forms it — the signed word
 * index scaled, summed with the tree, the field added — UNMASKED, as the ROM hands it on (wcopy puts each word it
 * reaches on the bus; a byte is read through `m68k_idioms.h`'s `bus_byte`, which puts it there)... */
static inline uint32_t object_address(uint32_t tree, int16_t object, uint32_t field)
{
    return table_entry(tree, object, OB_BYTES) + field;
}

/* ...a word field of it, as the Alcyon `int` the C reads (`move.w` then compared signed). */
static inline int16_t object_word(const uint8_t *image, uint32_t tree, int16_t object, uint32_t field)
{
    return (int16_t)bus_word(image, object_address(tree, object, field));
}

/* ...and one stored, as the ROM's `move.w` into the same address. */
static inline void set_object_word(uint8_t *image, uint32_t tree, int16_t object, uint32_t field, int16_t value)
{
    set_bus_word(image, object_address(tree, object, field), (uint16_t)value);
}
#endif

#endif /* TOS102US_AES_OBJECTS_H */
