/* host_slot.h — the HOST SLOTS every component shares: fixed image addresses that stand in, off
 * target, for a ROM frame local whose ADDRESS a routine hands on to another.
 *
 * GEMDOS needed them first, and the table began in `gemdos/gemdos.h`; it is here because the VDI needs
 * the same thing (`v_opnwk` points LINEA_CONTRL/INTIN/INTOUT at locals of its own frame and calls
 * vq_color over them), and two components keeping two tables in one band could hand out one address
 * twice with nothing to refuse it. ONE table, one held mask, one test (`test/test_host_slots.py`).
 */
#ifndef TOS102US_HOST_SLOT_H
#define TOS102US_HOST_SLOT_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#include <limits.h>
#endif
#include <stdint.h>

#include "machine.h"

/* ---- HOST SLOTS: a frame local whose ADDRESS a core hands on ---------------------------------------
 * The ROM's file system passes the address of a local in its own stack frame to a routine that reaches
 * memory through the image: `$fc6038`/`$fc5f44` hand the engine `-2(a6)` as a FAT transfer's buffer,
 * `$fc663c` hands its pattern `-24(a6)` to `$fc5d28`, `$fc5672` and `$fc5c9a`, `$fc696c` its component
 * FCB `-24(a6)` and its path cursor `-4(a6)` (to `$fc68dc`, which reads AND writes it), and `$fc7824`
 * the byte `-4(a6)` its `$e5` mark is written from, and `$fc71b6` its free-slot search name `-10(a6)`
 * (to `$fc663c`) and the new entry's FCB name `-22(a6)` (built by `$fc5d28`, written by `$fc5f1c`), and
 * `$fc7af0` (`Frename`) its entry buffer `-20(a6)` (a `$e5` mark, an entry's ten tail bytes, a new FCB name), and
 * `$fc7678` (`Fattrib`) the low byte of its own attribute ARGUMENT `15(a6)`, read or written in place, and the
 * dispatcher `$fc94e4` the byte `-14(a6)` a redirected read lands in and — through `$fc5078` — the argument words of
 * its own nested `Fwrite`, pushed on its stack, and `Pexec`'s loader `$fc85ea` the five locals it `Fread`s the
 * program's header and first relocation offset into (`-8`, `-66`, `-30`, `-10`, `-38(a6)`), laid out as one slot;
 * and the VDI's `trap #1` door `$fcfa9c` the words its caller pushed, which the host build hands the dispatcher, and
 * vst_font `$fce47c` the arrays it points LINEA_INTIN/PTSIN/PTSOUT at round its nested vst_height/vst_point.
 * ON TARGET the C local IS that frame slot and its address is the one passed. OFF TARGET a C local is
 * host memory the image cannot reach, so each role has a fixed address instead: inside the oracle's
 * stack band, which the differential drops on both shores — exactly where the ROM's own copy of the
 * local lives — and below the deepest frame the kit calls legitimate. ONE TABLE, here, of every such address and its width; `test_host_slots.py`
 * reads it and pins every span inside that band and apart from every other.
 *
 * A SLOT IS CLAIMED FOR ITS LIVE RANGE AND RELEASED AFTER IT, and the host build makes "never two
 * users at once" a fact rather than a comment: a claim of a slot that is held is an assert. So the
 * nestings that do happen (a walk holding its name and cursor while it searches, a search holding its
 * pattern while the FAT routines take the frame word underneath it) are checked on every run, and the
 * one that must not (a routine re-entering itself) cannot pass silently. */
#define HOST_SLOT_SEARCH_PATTERN        0x7f1e0  /* $fc663c's pattern: the FCB name, then the attribute */
#define HOST_SLOT_SEARCH_PATTERN_BYTES  12       /* `link #-24` less the two words and two longs beside it */
#define HOST_SLOT_WALK_NAME             0x7f1ec  /* $fc696c's component FCB, the same twelve bytes */
#define HOST_SLOT_WALK_NAME_BYTES       HOST_SLOT_SEARCH_PATTERN_BYTES
#define HOST_SLOT_WALK_CURSOR           0x7f1f8  /* $fc696c's path cursor, carried in AND out */
#define HOST_SLOT_WALK_CURSOR_BYTES     4
#define HOST_SLOT_DELETE_MARK           0x7f1fe  /* $fc7824's `$e5`, the byte its write moves */
#define HOST_SLOT_DELETE_MARK_BYTES     1
#define HOST_SLOT_ATTRIBUTE             0x7f1ff  /* $fc7678's attribute byte, moved by a one-byte transfer */
#define HOST_SLOT_ATTRIBUTE_BYTES       1
#define HOST_SLOT_FRAME_WORD            0x7f200  /* $fc6038/$fc5f44's FAT word */
#define HOST_SLOT_FRAME_WORD_BYTES      2
#define HOST_SLOT_CREATE_FREE_NAME      0x7f240  /* $fc71b6's "\xe5", the name a free slot is searched by */
#define HOST_SLOT_CREATE_FREE_NAME_BYTES 2
#define HOST_SLOT_CREATE_FCB            0x7f244  /* $fc71b6's new entry's FCB name, written into it */
#define HOST_SLOT_CREATE_FCB_BYTES      11
#define HOST_SLOT_RENAME_ENTRY          0x7f250  /* $fc7af0's `-20(a6)`: `$e5`, an entry's tail, or the new FCB name */
#define HOST_SLOT_RENAME_ENTRY_BYTES    11
#define HOST_SLOT_PEXEC_LOCALS         0x7f280  /* $fc85ea's header fields and first fixup, each read by `Fread` */
#define HOST_SLOT_PEXEC_LOCALS_BYTES   28       /* `LOAD_LOCALS_BYTES` (`gemdos/pexec_load.h`) */
#define HOST_SLOT_C_ENTRY_ARGUMENTS     0x7f300  /* $fc5078's caller's words: the dispatcher's own nested `Fwrite` */
#define HOST_SLOT_C_ENTRY_ARGUMENTS_BYTES 12     /* selector.w, handle.w, count.l, buffer.l */
#define HOST_SLOT_REDIRECTED_BYTE       0x7f310  /* $fc94e4's `-14(a6)`: the byte a redirected read lands in */
#define HOST_SLOT_REDIRECTED_BYTE_BYTES 1
/* The words a ROM door leaves on the stack for its `trap #1` — the function word over the caller's arguments — which
 * the host build hands the dispatcher (`gemdos/gemdos.h`, the gemdos_trap_* shapes): the VDI's `Malloc`/`Mfree` door
 * ($fcfa9c's caller's words) and the AES's glue (dos_free's `move.w d1,-(sp)` over its caller's longword, dos_alloc's
 * two pushes, $fe3c26 / $fe3bba; dos_read's four, the widest). ONE slot for all: no door is reached from under
 * another's trap. */
#define HOST_SLOT_GEMDOS_WORDS          0x7f320
#define HOST_SLOT_GEMDOS_WORDS_BYTES    12       /* function.w, then dos_read's handle.w, count.l, buffer.l */
#define HOST_SLOT_VDI_VST_FONT_CALL     0x7f330  /* $fce47c's `-18(a6)` points and `-6(a6)` size: its nested call's arrays */
#define HOST_SLOT_VDI_VST_FONT_CALL_BYTES 10     /* ptsin/ptsout's four words, then intin[0]: COMPACTED, not the frame's layout */
/* ...and the wide lines' and markers' (`vdi/lines.h`): points a frame builds and points LINEA_PTSIN at, and
 * the two words it hands perp_off and perp_off hands quad_xform. */
#define HOST_SLOT_VDI_WIDE_CORNERS      0x7f340  /* $fccba0's `-24(a6)`: four corners, and plygn's closing point */
#define HOST_SLOT_VDI_WIDE_CORNERS_BYTES 20      /* five (x, y) points */
#define HOST_SLOT_VDI_WIDE_OFFSET       0x7f354  /* $fccba0's `-36`/`-38(a6)`: the offset perp_off turns in place */
#define HOST_SLOT_VDI_WIDE_OFFSET_BYTES 4        /* x.w, y.w */
#define HOST_SLOT_VDI_PERP_DIRECTION    0x7f358  /* $fccd92's `-4`/`-6(a6)`: the offset quad_xform folds into quadrant 1 */
#define HOST_SLOT_VDI_PERP_DIRECTION_BYTES 4     /* x.w, y.w */
#define HOST_SLOT_VDI_ARROW_TRIANGLE    0x7f360  /* $fcd196's `-28(a6)`: an arrowhead, and plygn's closing point */
#define HOST_SLOT_VDI_ARROW_TRIANGLE_BYTES 16    /* four (x, y) points */
#define HOST_SLOT_VDI_MARKER_POINTS     0x7f370  /* $fcba7a's `-32(a6)`: one polyline of a marker, placed */
#define HOST_SLOT_VDI_MARKER_POINTS_BYTES 20     /* five (x, y) points */
/* ...and graphic text's (`vdi/gtext.h`): the box vqt_extent answers into a frame LINEA_PTSOUT is pointed at. */
#define HOST_SLOT_VDI_GTEXT_EXTENT      0x7f600  /* $fcd756's `-52(a6)`: the string's four corners, for its alignment */
#define HOST_SLOT_VDI_GTEXT_EXTENT_BYTES 16      /* four (x, y) points */
#define HOST_SLOT_VDI_JUSTIFIED_EXTENT  0x7f610  /* $fce9e8's `-36(a6)`: ...and the justified string's */
#define HOST_SLOT_VDI_JUSTIFIED_EXTENT_BYTES 16  /* four (x, y) points */
/* ...and the workstation's (`vdi/workstation.h`): the arrays v_opnwk points LINEA_CONTRL/INTIN/INTOUT at round
 * each of its vq_color calls. */
#define HOST_SLOT_VDI_OPNWK_COLOUR_CALL 0x7f400  /* $fcb694's `-38`/`-30`/`-26(a6)`: intout, intin, contrl */
#define HOST_SLOT_VDI_OPNWK_COLOUR_CALL_BYTES 22 /* VDI_OPNWK_CALL_BYTES: the frame's own layout from -38, contrl cut after
                                                  * contrl[4], the last word vq_color writes ($fd2e8c) */
/* ...and the AES's (`aes/objops.h`): ob_find's two GRECTs, which it hands ob_actxywh, ob_relxywh, r_set and inside. */
#define HOST_SLOT_AES_OB_FIND_RECTS     0x7f420  /* $fea0a8's `-22(a6)` origin and `-14(a6)` object rectangle */
#define HOST_SLOT_AES_OB_FIND_RECTS_BYTES 16     /* two GRECTs, the origin first: the frame's own layout */
/* ...and the shell's (`aes/shell.h`): sh_envrn's and sh_find's WHOLE frames of locals, whose strings it hands the string
 * helpers and sh_path — the frame's own layout, so an over-long string runs into the locals beside it as the ROM's does. */
#define HOST_SLOT_AES_SH_ENVRN_FRAME    0x7f440  /* $feae36's -46(a6) up: the name, the compare buffer, the cursor */
#define HOST_SLOT_AES_SH_ENVRN_FRAME_BYTES 47    /* SH_ENVRN_SLOT_BYTES: the frame, then the saved A6's top byte */
#define HOST_SLOT_AES_SH_FIND_FRAME     0x7f480  /* $feafbe's -22(a6) up: the name part, the first-try flag, the PATH index */
#define HOST_SLOT_AES_SH_FIND_FRAME_BYTES 23     /* SH_FIND_SLOT_BYTES: the frame, then the saved A6's top byte */
/* ...and gsx_start's (`aes/gsxif.h`): the stack word its second vst_height hands all four answer pointers, the answers
 * discarded — the large font's size set back after the small one's was asked. */
#define HOST_SLOT_AES_GSX_START_DISCARD 0x7f4a0  /* $fdab72's `lea (sp),a0`: the word under the pointers it pushes */
#define HOST_SLOT_AES_GSX_START_DISCARD_BYTES 2
/* ...and the graphics library's (`aes/gemgraf.h`): frames the ROM hands on by address — gsx_cline's own two points
 * (its arguments), gr_gtext's copy of its GRECT and gr_just's character count (saved D0/D1 words its `movem` restores),
 * gr_box's inner GRECT, gr_xor's GRECT (its arguments, stepped in place), and the step words gr_movebox and
 * gr_growbox / gr_shrinkbox keep in their saved registers' words. */
#define HOST_SLOT_AES_CLINE_POINTS      0x7f500  /* $fda8d2's `lea 4(sp),a0`: its arguments, two (x, y) points */
#define HOST_SLOT_AES_CLINE_POINTS_BYTES 8
#define HOST_SLOT_AES_GTEXT_RECT        0x7f508  /* $fda62c's `movea.l sp,a3`: a GRECT over its saved D0/D1 */
#define HOST_SLOT_AES_GTEXT_RECT_BYTES  8
#define HOST_SLOT_AES_JUST_COUNT        0x7f510  /* $fda5c2's `lea 2(sp)`: its saved D0's low word */
#define HOST_SLOT_AES_JUST_COUNT_BYTES  2
#define HOST_SLOT_AES_BOX_RECT          0x7f514  /* $fda7a4's `lea 8(sp),a4`: the GRECT each line is drawn round */
#define HOST_SLOT_AES_BOX_RECT_BYTES    8
#define HOST_SLOT_AES_XOR_RECT          0x7f51c  /* $fe83be's `pea` of its own arguments' GRECT */
#define HOST_SLOT_AES_XOR_RECT_BYTES    8
#define HOST_SLOT_AES_MOVEBOX_STEPS     0x7f524  /* $fe8402's `pea 6(sp)`..: its saved D1's low word and D2 */
#define HOST_SLOT_AES_MOVEBOX_STEPS_BYTES 6
#define HOST_SLOT_AES_GROWBOX_STEPS     0x7f52a  /* $fe8340/$fe837a's saved D2's low word, D3 and D4 ($fe831e) */
#define HOST_SLOT_AES_GROWBOX_STEPS_BYTES 10
/* ...and the object library's (`aes/obuser.h`): the PARMBLK ob_user builds in its frame and hands a USERDEF's routine. */
#define HOST_SLOT_AES_OB_USER_PARMBLK   0x7f540  /* $fe9a46's -30(a6): the block, up to the frame's top */
#define HOST_SLOT_AES_OB_USER_PARMBLK_BYTES 30   /* PARM_BYTES (`aes/objects.h`) */
/* ...and just_draw's (`aes/objdraw.h`): its WHOLE frame of locals, whose words it hands ob_sst, gr_crack, gsx_chkclip,
 * the gr_ layer and ob_user by address — the frame's own layout. */
#define HOST_SLOT_AES_JUST_DRAW_FRAME   0x7f560  /* $fe9a88's -48(a6) up: the clip, the GRECT, the spec, state, colours */
#define HOST_SLOT_AES_JUST_DRAW_FRAME_BYTES 48   /* `link a6,#-48` */
/* ...and its two callers' (`aes/objdraw.h`): the position ob_draw hands ob_offset, and ob_change's whole frame, whose
 * words it hands ob_sst, ob_offset and ob_user by address — each the frame's own layout. */
#define HOST_SLOT_AES_OB_DRAW_POSITION  0x7f590  /* $fea028's -8(a6) y, -6(a6) x: the walk's start (`clr.l` of both) */
#define HOST_SLOT_AES_OB_DRAW_POSITION_BYTES 4
#define HOST_SLOT_AES_OB_CHANGE_FRAME   0x7f5a0  /* $fea38e's -20(a6) up: the spec, state, GRECT, border, type, flags */
#define HOST_SLOT_AES_OB_CHANGE_FRAME_BYTES 20   /* `link a6,#-20` */

/* Each slot's bit in the held mask. */
enum host_slot {
    HOST_SLOT_ID_SEARCH_PATTERN,
    HOST_SLOT_ID_WALK_NAME,
    HOST_SLOT_ID_WALK_CURSOR,
    HOST_SLOT_ID_DELETE_MARK,
    HOST_SLOT_ID_ATTRIBUTE,
    HOST_SLOT_ID_FRAME_WORD,
    HOST_SLOT_ID_CREATE_FREE_NAME,
    HOST_SLOT_ID_CREATE_FCB,
    HOST_SLOT_ID_RENAME_ENTRY,
    HOST_SLOT_ID_PEXEC_LOCALS,
    HOST_SLOT_ID_C_ENTRY_ARGUMENTS,
    HOST_SLOT_ID_REDIRECTED_BYTE,
    HOST_SLOT_ID_GEMDOS_WORDS,
    HOST_SLOT_ID_VDI_VST_FONT_CALL,
    HOST_SLOT_ID_VDI_WIDE_CORNERS,
    HOST_SLOT_ID_VDI_WIDE_OFFSET,
    HOST_SLOT_ID_VDI_PERP_DIRECTION,
    HOST_SLOT_ID_VDI_ARROW_TRIANGLE,
    HOST_SLOT_ID_VDI_MARKER_POINTS,
    HOST_SLOT_ID_VDI_GTEXT_EXTENT,
    HOST_SLOT_ID_VDI_JUSTIFIED_EXTENT,
    HOST_SLOT_ID_VDI_OPNWK_COLOUR_CALL,
    HOST_SLOT_ID_AES_OB_FIND_RECTS,
    HOST_SLOT_ID_AES_SH_ENVRN_FRAME,
    HOST_SLOT_ID_AES_SH_FIND_FRAME,
    HOST_SLOT_ID_AES_GSX_START_DISCARD,
    HOST_SLOT_ID_AES_CLINE_POINTS,
    HOST_SLOT_ID_AES_GTEXT_RECT,
    HOST_SLOT_ID_AES_JUST_COUNT,
    HOST_SLOT_ID_AES_BOX_RECT,
    HOST_SLOT_ID_AES_XOR_RECT,
    HOST_SLOT_ID_AES_MOVEBOX_STEPS,
    HOST_SLOT_ID_AES_GROWBOX_STEPS,
    HOST_SLOT_ID_AES_OB_USER_PARMBLK,
    HOST_SLOT_ID_AES_JUST_DRAW_FRAME,
    HOST_SLOT_ID_AES_OB_DRAW_POSITION,
    HOST_SLOT_ID_AES_OB_CHANGE_FRAME,
    HOST_SLOT_ID_COUNT                /* not a slot: how many there are */
};

#ifdef RECREATE_HOST_DIFFERENTIAL
/* One bit per slot, defined in `src/host_slot.c`: a long long, as the table has outgrown a 32-bit mask. */
extern unsigned long long host_slots_held;
_Static_assert(HOST_SLOT_ID_COUNT <= sizeof host_slots_held * CHAR_BIT,
               "a slot past the held mask's width would alias a low one's bit, silently");

static inline uint32_t host_slot_take(enum host_slot slot, uint32_t host_at)
{
    assert(!(host_slots_held & 1ull << slot));
    host_slots_held |= 1ull << slot;
    return host_at;
}

static inline void host_slot_give_back(enum host_slot slot)
{
    host_slots_held &= ~(1ull << slot);
}

/* The image address a frame local of role ROLE is handed on at: its slot, claimed, off target... */
#define host_slot_claim(ROLE, local) \
    ((void)(local), host_slot_take(HOST_SLOT_ID_##ROLE, HOST_SLOT_##ROLE))
#define host_slot_release(ROLE) host_slot_give_back(HOST_SLOT_ID_##ROLE)
#else
/* ...and the local's own address on target, where nothing is held. */
#define host_slot_claim(ROLE, local) ((uint32_t)(uintptr_t)(local))
#define host_slot_release(ROLE) ((void)0)
#endif

/* A slot that carries a LONGWORD IN and OUT of the call it is handed to (the walk's cursor): off target
 * the local's value is copied into the slot before and back out after; on target the slot is the local
 * and there is nothing to copy. */
static inline void host_slot_store_long(uint8_t *image, uint32_t slot_at, const uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    wr32(image + slot_at, *local);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

static inline void host_slot_load_long(const uint8_t *image, uint32_t slot_at, uint32_t *local)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    *local = be32(image + slot_at);
#else
    (void)image, (void)slot_at, (void)local;
#endif
}

#endif /* TOS102US_HOST_SLOT_H */
