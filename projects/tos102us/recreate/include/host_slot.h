/* host_slot.h — the HOST SLOTS every component shares: fixed image addresses that stand in, off
 * target, for a ROM frame local whose ADDRESS a routine hands on to another.
 *
 * GEMDOS needed them first, and the table began in `gemdos/gemdos.h`; it is here because the VDI needs
 * the same thing (`v_opnwk` points LINEA_CONTRL/INTIN/INTOUT at locals of its own frame and calls
 * vq_color over them), and two components keeping two tables in one band could hand out one address
 * twice with nothing to refuse it. ONE table, one set of held flags, one test (`test/test_host_slots.py`).
 */
#ifndef TOS102US_HOST_SLOT_H
#define TOS102US_HOST_SLOT_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "recreate.h"

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
 * users at once" a fact rather than a comment: a claim of a slot that is held halts by name. So the
 * nestings that do happen (a walk holding its name and cursor while it searches, a search holding its
 * pattern while the FAT routines take the frame word underneath it) are checked on every run, and the
 * one that must not (a routine re-entering itself) cannot pass silently. */
#define HOST_SLOT_SEARCH_PATTERN        0x7f19a  /* $fc663c's pattern: the FCB name, then the attribute */
#define HOST_SLOT_SEARCH_PATTERN_BYTES  12       /* `link #-24` less the two words and two longs beside it */
#define HOST_SLOT_WALK_NAME             0x7f1a6  /* $fc696c's component FCB, the same twelve bytes */
#define HOST_SLOT_WALK_NAME_BYTES       HOST_SLOT_SEARCH_PATTERN_BYTES
#define HOST_SLOT_WALK_CURSOR           0x7f1b2  /* $fc696c's path cursor, carried in AND out */
#define HOST_SLOT_WALK_CURSOR_BYTES     4
#define HOST_SLOT_DELETE_MARK           0x7f1b6  /* $fc7824's `$e5`, the byte its write moves */
#define HOST_SLOT_DELETE_MARK_BYTES     1
#define HOST_SLOT_ATTRIBUTE             0x7f1b7  /* $fc7678's attribute byte, moved by a one-byte transfer */
#define HOST_SLOT_ATTRIBUTE_BYTES       1
#define HOST_SLOT_FRAME_WORD            0x7f1b8  /* $fc6038/$fc5f44's FAT word */
#define HOST_SLOT_FRAME_WORD_BYTES      2
#define HOST_SLOT_CREATE_FREE_NAME      0x7f1de  /* $fc71b6's "\xe5", the name a free slot is searched by */
#define HOST_SLOT_CREATE_FREE_NAME_BYTES 2
#define HOST_SLOT_CREATE_FCB            0x7f1e0  /* $fc71b6's new entry's FCB name, written into it */
#define HOST_SLOT_CREATE_FCB_BYTES      11
#define HOST_SLOT_RENAME_ENTRY          0x7f1ec  /* $fc7af0's `-20(a6)`: `$e5`, an entry's tail, or the new FCB name */
#define HOST_SLOT_RENAME_ENTRY_BYTES    11
#define HOST_SLOT_PEXEC_LOCALS         0x7f210  /* $fc85ea's header fields and first fixup, each read by `Fread` */
#define HOST_SLOT_PEXEC_LOCALS_BYTES   28       /* `LOAD_LOCALS_BYTES` (`gemdos/pexec_load.h`) */
#define HOST_SLOT_C_ENTRY_ARGUMENTS     0x7f284  /* $fc5078's caller's words: the dispatcher's own nested `Fwrite` */
#define HOST_SLOT_C_ENTRY_ARGUMENTS_BYTES 12     /* selector.w, handle.w, count.l, buffer.l */
#define HOST_SLOT_REDIRECTED_BYTE       0x7f290  /* $fc94e4's `-14(a6)`: the byte a redirected read lands in */
#define HOST_SLOT_REDIRECTED_BYTE_BYTES 1
/* The words a ROM door leaves on the stack for its `trap #1` — the function word over the caller's arguments — which
 * the host build hands the dispatcher (`gemdos/gemdos.h`, the gemdos_trap_* shapes): the VDI's `Malloc`/`Mfree` door
 * ($fcfa9c's caller's words) and the AES's glue (dos_free's `move.w d1,-(sp)` over its caller's longword, dos_alloc's
 * two pushes, $fe3c26 / $fe3bba; dos_read's four, the widest). ONE slot for all: no door is reached from under
 * another's trap. */
#define HOST_SLOT_GEMDOS_WORDS          0x7f292
#define HOST_SLOT_GEMDOS_WORDS_BYTES    12       /* function.w, then dos_read's handle.w, count.l, buffer.l */
/* ...and pgmld's Pexec (`src/aes/gemdosif.c`, $fe39bc): the one frame of the AES's glue wider than that slot — the
 * function, the mode and three longwords — handed to the dispatcher the same way. */
#define HOST_SLOT_AES_PGMLD_WORDS       0x7f22c
#define HOST_SLOT_AES_PGMLD_WORDS_BYTES 16       /* function.w, mode.w, name.l, tail.l, environment.l */
#define HOST_SLOT_VDI_VST_FONT_CALL     0x7f29e  /* $fce47c's `-18(a6)` points and `-6(a6)` size: its nested call's arrays */
#define HOST_SLOT_VDI_VST_FONT_CALL_BYTES 10     /* ptsin/ptsout's four words, then intin[0]: COMPACTED, not the frame's layout */
/* ...and the wide lines' and markers' (`vdi/lines.h`): points a frame builds and points LINEA_PTSIN at, and
 * the two words it hands perp_off and perp_off hands quad_xform. */
#define HOST_SLOT_VDI_WIDE_CORNERS      0x7f2a8  /* $fccba0's `-24(a6)`: four corners, and plygn's closing point */
#define HOST_SLOT_VDI_WIDE_CORNERS_BYTES 20      /* five (x, y) points */
#define HOST_SLOT_VDI_WIDE_OFFSET       0x7f2bc  /* $fccba0's `-36`/`-38(a6)`: the offset perp_off turns in place */
#define HOST_SLOT_VDI_WIDE_OFFSET_BYTES 4        /* x.w, y.w */
#define HOST_SLOT_VDI_PERP_DIRECTION    0x7f2c0  /* $fccd92's `-4`/`-6(a6)`: the offset quad_xform folds into quadrant 1 */
#define HOST_SLOT_VDI_PERP_DIRECTION_BYTES 4     /* x.w, y.w */
#define HOST_SLOT_VDI_ARROW_TRIANGLE    0x7f2c4  /* $fcd196's `-28(a6)`: an arrowhead, and plygn's closing point */
#define HOST_SLOT_VDI_ARROW_TRIANGLE_BYTES 16    /* four (x, y) points */
#define HOST_SLOT_VDI_MARKER_POINTS     0x7f2d4  /* $fcba7a's `-32(a6)`: one polyline of a marker, placed */
#define HOST_SLOT_VDI_MARKER_POINTS_BYTES 20     /* five (x, y) points */
/* ...and graphic text's (`vdi/gtext.h`): the box vqt_extent answers into a frame LINEA_PTSOUT is pointed at. */
#define HOST_SLOT_VDI_GTEXT_EXTENT      0x7f4a2  /* $fcd756's `-52(a6)`: the string's four corners, for its alignment */
#define HOST_SLOT_VDI_GTEXT_EXTENT_BYTES 16      /* four (x, y) points */
#define HOST_SLOT_VDI_JUSTIFIED_EXTENT  0x7f4b2  /* $fce9e8's `-36(a6)`: ...and the justified string's */
#define HOST_SLOT_VDI_JUSTIFIED_EXTENT_BYTES 16  /* four (x, y) points */
/* ...and the workstation's (`vdi/workstation.h`): the arrays v_opnwk points LINEA_CONTRL/INTIN/INTOUT at round
 * each of its vq_color calls. */
#define HOST_SLOT_VDI_OPNWK_COLOUR_CALL 0x7f33a  /* $fcb694's `-38`/`-30`/`-26(a6)`: intout, intin, contrl */
#define HOST_SLOT_VDI_OPNWK_COLOUR_CALL_BYTES 22 /* VDI_OPNWK_CALL_BYTES: the frame's own layout from -38, contrl cut after
                                                  * contrl[4], the last word vq_color writes ($fd2e8c) */
/* ...and the AES's (`aes/objops.h`): ob_find's two GRECTs, which it hands ob_actxywh, ob_relxywh, r_set and inside. */
#define HOST_SLOT_AES_OB_FIND_RECTS     0x7f350  /* $fea0a8's `-22(a6)` origin and `-14(a6)` object rectangle */
#define HOST_SLOT_AES_OB_FIND_RECTS_BYTES 16     /* two GRECTs, the origin first: the frame's own layout */
/* ...and the shell's (`aes/shell.h`): sh_envrn's and sh_find's WHOLE frames of locals, whose strings it hands the string
 * helpers and sh_path — the frame's own layout, so an over-long string runs into the locals beside it as the ROM's does. */
#define HOST_SLOT_AES_SH_ENVRN_FRAME    0x7f364  /* $feae36's -46(a6) up: the name, the compare buffer, the cursor */
#define HOST_SLOT_AES_SH_ENVRN_FRAME_BYTES 47    /* SH_ENVRN_SLOT_BYTES: the frame, then the saved A6's top byte */
#define HOST_SLOT_AES_SH_FIND_FRAME     0x7f394  /* $feafbe's -22(a6) up: the name part, the first-try flag, the PATH index */
#define HOST_SLOT_AES_SH_FIND_FRAME_BYTES 23     /* SH_FIND_SLOT_BYTES: the frame, then the saved A6's top byte */
/* ...and gsx_start's (`aes/gsxif.h`): the stack word its second vst_height hands all four answer pointers, the answers
 * discarded — the large font's size set back after the small one's was asked. */
#define HOST_SLOT_AES_GSX_START_DISCARD 0x7f3ac  /* $fdab72's `lea (sp),a0`: the word under the pointers it pushes */
#define HOST_SLOT_AES_GSX_START_DISCARD_BYTES 2
/* ...and the graphics library's (`aes/gemgraf.h`): frames the ROM hands on by address — gsx_cline's own two points
 * (its arguments), gr_gtext's copy of its GRECT and gr_just's character count (saved D0/D1 words its `movem` restores),
 * gr_box's inner GRECT, gr_xor's GRECT (its arguments, stepped in place), and the step words gr_movebox and
 * gr_growbox / gr_shrinkbox keep in their saved registers' words. */
#define HOST_SLOT_AES_CLINE_POINTS      0x7f3e6  /* $fda8d2's `lea 4(sp),a0`: its arguments, two (x, y) points */
#define HOST_SLOT_AES_CLINE_POINTS_BYTES 8
#define HOST_SLOT_AES_GTEXT_RECT        0x7f3ee  /* $fda62c's `movea.l sp,a3`: a GRECT over its saved D0/D1 */
#define HOST_SLOT_AES_GTEXT_RECT_BYTES  8
#define HOST_SLOT_AES_JUST_COUNT        0x7f3f6  /* $fda5c2's `lea 2(sp)`: its saved D0's low word */
#define HOST_SLOT_AES_JUST_COUNT_BYTES  2
#define HOST_SLOT_AES_BOX_RECT          0x7f3f8  /* $fda7a4's `lea 8(sp),a4`: the GRECT each line is drawn round */
#define HOST_SLOT_AES_BOX_RECT_BYTES    8
#define HOST_SLOT_AES_XOR_RECT          0x7f400  /* $fe83be's `pea` of its own arguments' GRECT */
#define HOST_SLOT_AES_XOR_RECT_BYTES    8
#define HOST_SLOT_AES_MOVEBOX_STEPS     0x7f408  /* $fe8402's `pea 6(sp)`..: its saved D1's low word and D2 */
#define HOST_SLOT_AES_MOVEBOX_STEPS_BYTES 6
#define HOST_SLOT_AES_GROWBOX_STEPS     0x7f40e  /* $fe8340/$fe837a's saved D2's low word, D3 and D4 ($fe831e) */
#define HOST_SLOT_AES_GROWBOX_STEPS_BYTES 10
/* ...and the object library's (`aes/obuser.h`): the PARMBLK ob_user builds in its frame and hands a USERDEF's routine. */
#define HOST_SLOT_AES_OB_USER_PARMBLK   0x7f418  /* $fe9a46's -30(a6): the block, up to the frame's top */
#define HOST_SLOT_AES_OB_USER_PARMBLK_BYTES 30   /* PARM_BYTES (`aes/objects.h`) */
/* ...and just_draw's (`aes/objdraw.h`): its WHOLE frame of locals, whose words it hands ob_sst, gr_crack, gsx_chkclip,
 * the gr_ layer and ob_user by address — the frame's own layout. */
#define HOST_SLOT_AES_JUST_DRAW_FRAME   0x7f436  /* $fe9a88's -48(a6) up: the clip, the GRECT, the spec, state, colours */
#define HOST_SLOT_AES_JUST_DRAW_FRAME_BYTES 48   /* `link a6,#-48` */
/* ...and its two callers' (`aes/objdraw.h`): the position ob_draw hands ob_offset, and ob_change's whole frame, whose
 * words it hands ob_sst, ob_offset and ob_user by address — each the frame's own layout. */
#define HOST_SLOT_AES_OB_DRAW_POSITION  0x7f466  /* $fea028's -8(a6) y, -6(a6) x: the walk's start (`clr.l` of both) */
#define HOST_SLOT_AES_OB_DRAW_POSITION_BYTES 4
#define HOST_SLOT_AES_OB_CHANGE_FRAME   0x7f46a  /* $fea38e's -20(a6) up: the spec, state, GRECT, border, type, flags */
#define HOST_SLOT_AES_OB_CHANGE_FRAME_BYTES 20   /* `link a6,#-20` */
/* ...and the box loops that wait on the mouse (`aes/grwait.h`): gr_stilldn's MOBLK — its own arguments — and its answer
 * words, which it hands ev_multi through the event door, and gr_watchbox's rectangle, which it hands ob_actxywh. */
#define HOST_SLOT_AES_GR_STILLDN_RECTANGLE 0x7f4da  /* $fe851a `pea 36(sp)`: the leave flag and the rectangle */
#define HOST_SLOT_AES_GR_STILLDN_RECTANGLE_BYTES 10 /* EV_MOBLK_WORDS words */
#define HOST_SLOT_AES_GR_STILLDN_ANSWERS 0x7f4e4  /* $fe850c `move.l sp,-(sp)`: the twelve bytes below its return */
#define HOST_SLOT_AES_GR_STILLDN_ANSWERS_BYTES 12 /* EV_MULTI_ANSWER_WORDS words */
#define HOST_SLOT_AES_GR_WATCHBOX_RECT  0x7f4f0  /* $fe84d0 `move.l a6,-(sp)`: the words its `movem` saved D2/D3 in */
#define HOST_SLOT_AES_GR_WATCHBOX_RECT_BYTES 8
/* ...and the drag loops' (`aes/grdrag.h`): the words each `movem` saved registers in, which it hands on by address —
 * gr_draw's summed box (to gsx_xbox), gr_clamp's mouse (to gsx_mxmy), gr_rubwind's box (to gr_clamp and gr_wait),
 * gr_dragbox's mouse, box and the mouse's offset in it, gr_slidebox's two rectangles (to ob_relxywh / ob_actxywh and
 * gr_dragbox) — each the frame's own layout. */
#define HOST_SLOT_AES_GR_DRAW_RECT      0x7f4f8  /* $fe8544 `lea 4(sp),a0`: the words its `movem` saved D0/D1 in */
#define HOST_SLOT_AES_GR_DRAW_RECT_BYTES 8
#define HOST_SLOT_AES_GR_CLAMP_MOUSE    0x7f500  /* $fe86dc `subq.l #4,sp`: the mouse's x, y */
#define HOST_SLOT_AES_GR_CLAMP_MOUSE_BYTES 4
#define HOST_SLOT_AES_GR_RUBWIND_RECT   0x7f504  /* $fe85f0 `lea 2(sp),a3`: the words its `movem` saved D3/D4 in */
#define HOST_SLOT_AES_GR_RUBWIND_RECT_BYTES 8
#define HOST_SLOT_AES_GR_DRAGBOX_FRAME  0x7f50c  /* $fe8652 `lea 6(sp),a0`..: the words saved D2..D5 in, from the mouse */
#define HOST_SLOT_AES_GR_DRAGBOX_FRAME_BYTES 16
#define HOST_SLOT_AES_GR_SLIDEBOX_RECTS 0x7f51c  /* $fe8708 `movea.l sp,a5`: the words saved D0..D3 in */
#define HOST_SLOT_AES_GR_SLIDEBOX_RECTS_BYTES 16
/* ...and the menu library's (`aes/mnlib.h`): menu_sr's GRECT (to ob_actxywh and bb_save / bb_restore), mn_do's
 * answers and MOBLKs (to rect_change and ev_multi, COMPACTED — `MN_DO_*`), mn_register's copy of a process's name. */
#define HOST_SLOT_AES_MENU_SR_RECT      0x7f52c  /* $fe8cb6's -8(a6) */
#define HOST_SLOT_AES_MENU_SR_RECT_BYTES 8
#define HOST_SLOT_AES_MN_DO_FRAME       0x7f534  /* $fe8d6e's -52(a6) answers, -36(a6) and -26(a6) MOBLKs */
#define HOST_SLOT_AES_MN_DO_FRAME_BYTES 32       /* MN_DO_FRAME_WORDS words */
#define HOST_SLOT_AES_MN_REGISTER_NAME  0x7f554  /* $fe91e2's -14(a6) */
#define HOST_SLOT_AES_MN_REGISTER_NAME_BYTES 14  /* MN_REGISTER_NAME_BYTES */
/* ...and the object editor's (`aes/obedit.h`): pxl_rect's GRECT, which it hands ob_actxywh and gr_just; curfld's two,
 * which it hands pxl_rect and the clip calls; and ob_edit's locals whose addresses it hands ob_stfn and check — each
 * the frame's own layout. */
#define HOST_SLOT_AES_PXL_RECT_FIELD    0x7f56a  /* $fe941c's -8(a6): the field's GRECT, its corner moved by gr_just */
#define HOST_SLOT_AES_PXL_RECT_FIELD_BYTES 8
#define HOST_SLOT_AES_CURFLD_RECTS      0x7f572  /* $fe948a's -16(a6) the cursor's GRECT, -8(a6) the clip saved */
#define HOST_SLOT_AES_CURFLD_RECTS_BYTES 16
#define HOST_SLOT_AES_OB_EDIT_FRAME     0x7f582  /* $fe9678's -42(a6) the typed character, -40..-34(a6) the four places */
#define HOST_SLOT_AES_OB_EDIT_FRAME_BYTES 10
/* ...and the window library's (`aes/wmlib.h`): the GRECTs w_clipdraw, w_cpwalk, w_move and wm_get hand rc_copy,
 * rc_intersect, w_getsize, gsx_gclip, gsx_sclip and w_mvfix by address — each the frame's own layout. */
#define HOST_SLOT_AES_W_CLIPDRAW_RECT   0x7f5d4  /* $feb646's -8(a6): a visible rectangle, cut by the clip */
#define HOST_SLOT_AES_W_CLIPDRAW_RECT_BYTES 8
#define HOST_SLOT_AES_W_CPWALK_RECT     0x7f5dc  /* $feb712's -8(a6): the rectangle the gadgets are drawn under */
#define HOST_SLOT_AES_W_CPWALK_RECT_BYTES 8
#define HOST_SLOT_AES_W_MOVE_RECTS      0x7f5e4  /* $febf00's -16(a6) where the window is, -8(a6) where it was */
#define HOST_SLOT_AES_W_MOVE_RECTS_BYTES 16
#define HOST_SLOT_AES_WM_GET_RECT       0x7f5f4  /* $fec722's -8(a6): the work area the list arms walk over */
#define HOST_SLOT_AES_WM_GET_RECT_BYTES 8
/* ...and its half that reaches the event layer (`aes/wmupdate.h`): the GRECTs w_setactive, w_redraw, draw_change,
 * wm_opcl and wm_set hand on by address, and the word draw_change hands w_move — each the frame's own layout. */
#define HOST_SLOT_AES_W_SETACTIVE_RECT  0x7f69e  /* $feba54's -8(a6): the top window's work area, for ct_chgown */
#define HOST_SLOT_AES_W_SETACTIVE_RECT_BYTES 8
#define HOST_SLOT_AES_W_REDRAW_RECTS    0x7f6a6  /* $febe2a's -16(a6) the work area cut, -8(a6) the rectangle asked */
#define HOST_SLOT_AES_W_REDRAW_RECTS_BYTES 16
#define HOST_SLOT_AES_DRAW_CHANGE_FRAME 0x7f6b6  /* $fec0ca's -14(a6) w_move's stop word up to its -8(a6) old GRECT */
#define HOST_SLOT_AES_DRAW_CHANGE_FRAME_BYTES 14
#define HOST_SLOT_AES_WM_OPCL_RECT      0x7f6c4  /* $fec676's -8(a6): the caller's GRECT, copied */
#define HOST_SLOT_AES_WM_OPCL_RECT_BYTES 8
#define HOST_SLOT_AES_WM_SET_RECT       0x7f6cc  /* $fec83a's -18(a6): WF_TOP's window rectangle */
#define HOST_SLOT_AES_WM_SET_RECT_BYTES 8
/* ...and the form library's (`aes/fmlib.h`): fm_parse's string index, which it hands fm_strbrk twice, and fm_build's four
 * GRECTs, which it hands r_set and ob_setxywh — each the frame's own layout. */
#define HOST_SLOT_AES_FM_PARSE_INDEX    0x7f6d4  /* $fe6d84's -2(a6) */
#define HOST_SLOT_AES_FM_PARSE_INDEX_BYTES 2
#define HOST_SLOT_AES_FM_BUILD_RECTS    0x7f6d6  /* $fe6df8's -32(a6) ms, -24(a6) bt, -16(a6) ic, -8(a6) al */
#define HOST_SLOT_AES_FM_BUILD_RECTS_BYTES 32
/* ...and its half that waits on the user (`aes/fmdo.h`): fm_do's answers, index and next object (to ev_multi, ob_edit,
 * fm_keybd and fm_button), fm_button's answers and flags (to ev_button and ob_fs), fm_alert's clip, box, tree, icon and
 * parse answers (to gsx_gclip, ob_center, rs_gaddr and fm_parse), eralert's drive name and the pointer to it, and
 * fm_error's own argument word — merge_str's %S and %W, handed by address — each the frame's own layout. */
#define HOST_SLOT_AES_FM_DO_FRAME       0x7f6f6  /* $fe74a4's -20(a6) up                                         */
#define HOST_SLOT_AES_FM_DO_FRAME_BYTES 20       /* FM_DO_FRAME_BYTES                                            */
#define HOST_SLOT_AES_FM_BUTTON_FRAME   0x7f70a  /* $fe7346's -26(a6) up                                         */
#define HOST_SLOT_AES_FM_BUTTON_FRAME_BYTES 26   /* FM_BUTTON_FRAME_BYTES                                        */
#define HOST_SLOT_AES_FM_ALERT_FRAME    0x7f724  /* $fe7002's -34(a6) up                                         */
#define HOST_SLOT_AES_FM_ALERT_FRAME_BYTES 34    /* FM_ALERT_FRAME_BYTES                                         */
#define HOST_SLOT_AES_ERALERT_FRAME     0x7f746  /* $fe768c's -14(a6) up to its -8(a6) pointer                   */
#define HOST_SLOT_AES_ERALERT_FRAME_BYTES 10     /* ERALERT_FRAME_BYTES                                          */
#define HOST_SLOT_AES_FM_ERROR_CODE     0x7f750  /* $fe7712's 8(a6): its argument, handed as fp+8 ($fe7764)      */
#define HOST_SLOT_AES_FM_ERROR_CODE_BYTES 2
/* ...and the file selector's (`aes/fslib.h`): fs_start's tree (to rs_gaddr), fs_format's two answers (to fs_sset),
 * fs_nscroll's clip and rows (to gsx_gclip, ob_actxywh and gsx_sclip) and fs_input's answers, row, mouse and count (to
 * fs_sset, ob_offset, fs_nscroll, gsx_mxmy and fs_newdir) — each the frame's own layout. */
#define HOST_SLOT_AES_FS_START_TREE     0x7f752  /* $fe7782's -4(a6)                                             */
#define HOST_SLOT_AES_FS_START_TREE_BYTES 4
#define HOST_SLOT_AES_FS_FORMAT_FRAME   0x7f756  /* $fe7a44's -10(a6) up to its -6(a6) pointer                   */
#define HOST_SLOT_AES_FS_FORMAT_FRAME_BYTES 8    /* FS_FORMAT_FRAME_BYTES                                        */
#define HOST_SLOT_AES_FS_NSCROLL_FRAME  0x7f75e  /* $fe7b92's -18(a6) clip, -10(a6) rows                         */
#define HOST_SLOT_AES_FS_NSCROLL_FRAME_BYTES 16  /* FS_NSCROLL_FRAME_BYTES                                       */
#define HOST_SLOT_AES_FS_INPUT_FRAME    0x7f76e  /* $fe7d90's -38(a6) up to its -6(a6) count                     */
#define HOST_SLOT_AES_FS_INPUT_FRAME_BYTES 34    /* FS_INPUT_FRAME_BYTES                                         */
/* ...and the process layer's (`aes/pdpipe.h`): pd_match's copy of a PD's name (to movs and streq) and ap_find's copy of
 * the name it is asked for (to lstcpy and fpdnm) — each the frame's own layout, ap_find's with the two bytes past it. */
#define HOST_SLOT_AES_PD_MATCH_NAME     0x7f790  /* $fe56f6's -10(a6) up                                         */
#define HOST_SLOT_AES_PD_MATCH_NAME_BYTES 10     /* PD_MATCH_FRAME_BYTES                                         */
#define HOST_SLOT_AES_AP_FIND_NAME      0x7f79a  /* $fe65da's -10(a6) up, then the saved A6's two top bytes      */
#define HOST_SLOT_AES_AP_FIND_NAME_BYTES 12      /* AP_FIND_SLOT_BYTES                                           */
/* ...and the opcode switch's (`aes/gemsuper.h`): the marshal's WHOLE frame — its copies of the program's control,
 * int_in and addr_in and the answer words, whose addresses it hands the switch and every arm hands on — the frame's
 * own layout, so a count past an array runs into the arrays above it as the ROM's does; and the longword graf_mouse
 * has rs_gaddr answer a bit image's address into. The marshal's frame is LIVE ACROSS EVERY WAIT an arm makes: one
 * frame for every process, as the door users' own are (below, THE AUDIT) — ACCEPTED FOR BAND 5 WAVE 1, where the one
 * C process inside the marshal is the caller; WAVE 3 (an accessory's trap running our marshal on the host while the
 * desk is parked in its own) OWES `host_slot_claim_for` and HOST_PROCESSES frames of room. THE SLOT RUNS ON PAST THE
 * FRAME: the copy back of int_out READS past it where the program's count says so (the ROM's saved A6, its return
 * address, its argument), and off target those words are the slot's last sixteen bytes — a MODEL of what a caller
 * leaves above the frame, which a case stages and the C never writes (`aes/gemsuper.h`, MARSHAL_HOST_CALLER_BYTES). */
#define HOST_SLOT_AES_MARSHAL_FRAME     0x7f2e8  /* $fe64e6's -62(a6) up, then the caller's words above it       */
#define HOST_SLOT_AES_MARSHAL_FRAME_BYTES 78     /* MARSHAL_FRAME_BYTES + MARSHAL_HOST_CALLER_BYTES              */
#define HOST_SLOT_AES_DISPATCH_MOUSE_FORM 0x7f1f8 /* $fe5d9c's -12(a6): graf_mouse's form ($fe62b2 pea)          */
#define HOST_SLOT_AES_DISPATCH_MOUSE_FORM_BYTES 4
/* ---- band 5 wave 3, slice L (`aes/loader.h`) ---- sndcli's local: the basepage pgmld answers through the address it
 * is handed, read back once the load has succeeded. */
#define HOST_SLOT_AES_SNDCLI_BASEPAGE   0x7f336  /* $fe42e8's -6(a6)                                             */
#define HOST_SLOT_AES_SNDCLI_BASEPAGE_BYTES 4
/* ---- end of slice L's ---- */
/* ---- band 5 wave 4, slice I (`aes/geminit.h`) ---- the INF reader's local: the pair of hex digits scan_2 answers
 * through the address it is handed; and gem_main's: the BITBLK address rs_gaddr answers the same way, three times. */
#define HOST_SLOT_AES_READ_INF_PAIR     0x7f3ba  /* $fda408's -2(a6)                                             */
#define HOST_SLOT_AES_READ_INF_PAIR_BYTES 2
#define HOST_SLOT_AES_GEM_MAIN_ICON     0x7f3bc  /* $fda062's -4(a6)                                             */
#define HOST_SLOT_AES_GEM_MAIN_ICON_BYTES 4
/* ---- end of slice I's ---- */
/* ---- band 6 wave 1a, unit D (`desk/deskbind.h`) ---- THE DESK'S BINDINGS' FRAME: the words a binding hands an AES
 * routine BY ADDRESS — in the ROM its caller's own argument words (a GRECT, a MOBLK: `move.l a6,(sp) / addi.l #16,(sp)`)
 * or a local of its `link` (ev_multi's six answers, rs_gaddr's bit image). ONE frame for all forty: the desk is one
 * process and a binding calls no binding while it holds it. Live across the wait of evnt_multi, evnt_button and
 * wind_get's yield — one frame for every process, sound as the door users' own are (below, THE AUDIT). */
#define HOST_SLOT_AES_DESK_BIND_FRAME   0x7f3c0  /* $fdded8's -20(a6) answers, its 16(a6) and 26(a6) rectangles    */
#define HOST_SLOT_AES_DESK_BIND_FRAME_BYTES 32   /* BIND_FRAME_BYTES: evnt_multi's, the widest                    */
/* ---- end of unit D's ---- */
/* ---- band 6 wave 1a, unit O (`desk/deskleaf.h`) ---- three frames of the desk's DOS glue that GEMDOS is handed BY
 * ADDRESS: dos_label's whole `link` (its search path, then the DTA it sets — the frame's own layout), dos_space's
 * (Dfree's four longwords) and the two argument words dos_setdt hands Fdatime where they lie. None is held across a
 * wait: each is a leaf that traps and returns. */
#define HOST_SLOT_AES_DOS_LABEL_FRAME   0x7f656  /* $fe3b02's -52(a6) path, -44(a6) DTA                           */
#define HOST_SLOT_AES_DOS_LABEL_FRAME_BYTES 52   /* LABEL_FRAME_BYTES                                            */
#define HOST_SLOT_AES_DOS_SPACE_DFREE   0x7f68a  /* $fe3b6a's -16(a6)                                            */
#define HOST_SLOT_AES_DOS_SPACE_DFREE_BYTES 16   /* DFREE_BYTES                                                  */
#define HOST_SLOT_AES_DOS_SETDT_STAMP   0x7f69a  /* $fe3ae8's `pea 10(sp)`: its caller's time and date words      */
#define HOST_SLOT_AES_DOS_SETDT_STAMP_BYTES 4    /* DOS_STAMP_BYTES                                              */
/* ---- end of unit O's ---- */
/* BAND 6 WAVE 1b: a block per group, each group's slots in its own block — one slot per role, `_Static_assert` of each
 * frame against its `_BYTES` in the unit's `.c`; each id in `enum host_slot` below, in its group's region. (Wave 1b's
 * address windows are gone: band 6 wave 2's prep RE-LAID THE WHOLE TABLE — every slot packed down onto the band's floor
 * in its address order, its parity kept — so the band's free bytes are one run; wave 2's windows are in that run.) */
/* ---- band 6 wave 1b, group G1 (units I, L) ---- */
/* Unit I's window leaves' one frame (`desk/deskwin.h`): the GRECTs a leaf hands a binding or a rectangle routine BY
 * ADDRESS — its `link` locals in the ROM (do_wfull's three, do_wredraw's piece and the caller's own clip words), or
 * ini_str's string address. No leaf of the unit calls another while it holds it; held across the yields of the
 * bindings it calls (wind_get's, objc_draw's, the boxes'). */
#define HOST_SLOT_AES_DESK_WIN_FRAME    0x7f4c2  /* $fe0f9c's -24(a6) up                                          */
#define HOST_SLOT_AES_DESK_WIN_FRAME_BYTES 24    /* WIN_FRAME_BYTES                                              */
/* ...and unit L's (`desk/deskview.h`): win_sinfo's merge parameters, win_shwall's rectangle. */
#define HOST_SLOT_AES_DESK_VIEW_FRAME   0x7f562  /* $fe37ee's -6(a6) up                                           */
#define HOST_SLOT_AES_DESK_VIEW_FRAME_BYTES 8    /* VIEW_FRAME_BYTES                                             */
/* ---- end of group G1's ---- */
/* ---- band 6 wave 1b, group G2 (units A, K, J) ---- */
/* app_tran's (`desk/deskapp.h`): the BITBLK address rs_gaddr answers into its frame — HELD ACROSS THE YIELD of the
 * rsrc_gaddr binding, which stores it before its dsptch and is read after it (one desk process: one frame). */
#define HOST_SLOT_AES_APP_TRAN_BITBLK   0x7f360  /* $fdb186's -4(a6)                                              */
#define HOST_SLOT_AES_APP_TRAN_BITBLK_BYTES 4    /* APP_TRAN_BITBLK_BYTES                                        */
/* men_update's (`desk/desktop.h`): i_find's two answers, the FNODE and whether a program, handed BY ADDRESS — given
 * back before its men_list's yields. */
#define HOST_SLOT_AES_MEN_UPDATE_FIND   0x7f3e0  /* $fe1cb6's -6(a6) FNODE, -2(a6) is-a-program                   */
#define HOST_SLOT_AES_MEN_UPDATE_FIND_BYTES 6    /* FIND_FRAME_BYTES                                             */
/* ---- end of group G2's ---- */
/* ---- band 6 wave 1b, group G3 (units B, G) ---- */
/* deskact's (`desk/deskact.h`): the frame words its hit tests and drags hand on BY ADDRESS — gr_isdown's two answers
 * of evnt_multi and gr_bwait's four of gr_isdown, BOTH HELD ACROSS evnt_multi's WAIT; act_chkobj's, act_chg's and
 * act_allchg's rectangles, handed to rc_intersect / rc_copy / rc_union and held across their callees (act_allchg's
 * across act_chkobj's own: two roles, one desk process). */
#define HOST_SLOT_AES_GR_ISDOWN_ANSWERS 0x7f166  /* $fdc152's -16(a6) clicks and -14(a6) key                      */
#define HOST_SLOT_AES_GR_ISDOWN_ANSWERS_BYTES 4  /* GR_ISDOWN_FRAME_BYTES                                        */
#define HOST_SLOT_AES_GR_BWAIT_ANSWERS  0x7f16a  /* $fdc4fe's -10(a6)..-4(a6): the mouse, the button, the keys    */
#define HOST_SLOT_AES_GR_BWAIT_ANSWERS_BYTES 8   /* GR_BWAIT_FRAME_BYTES                                         */
#define HOST_SLOT_AES_ACT_CHKOBJ_RECTS  0x7f172  /* $fdc86e's -18(a6) and -10(a6)                                */
#define HOST_SLOT_AES_ACT_CHKOBJ_RECTS_BYTES 16  /* ACT_CHKOBJ_FRAME_BYTES                                       */
#define HOST_SLOT_AES_ACT_CHG_RECT      0x7f182  /* $fdc9e4's -10(a6)                                            */
#define HOST_SLOT_AES_ACT_CHG_RECT_BYTES 8       /* ACT_CHG_FRAME_BYTES                                          */
#define HOST_SLOT_AES_ACT_ALLCHG_RECTS  0x7f18a  /* $fdcabc's -20(a6) and -12(a6)                                */
#define HOST_SLOT_AES_ACT_ALLCHG_RECTS_BYTES 16  /* ACT_ALLCHG_FRAME_BYTES                                       */
/* ---- end of group G3's ---- */
/* ---- band 6 wave 1b, group G4 (units C, H, E, F) ---- */
/* Frame locals whose address each routine hands a binding or a string helper. TWO ARE HELD ACROSS A BINDING'S YIELD
 * (the dispatcher runs before the binding returns): the rectangle the dialog helpers get from form_center and hand on,
 * and fun_msg's message — the formatters' frames hold no binding. One frame for every process: only the desk's
 * process runs these. Unit C's four dialog helpers share one rectangle (none calls another while holding it). */
#define HOST_SLOT_AES_DESK_DIR_RECT     0x7f100  /* $fdcf04/$fdcfa8/$fdcfea's -8(a6) x y w h, $fdd04c's -8(a6) GRECT */
#define HOST_SLOT_AES_DESK_DIR_RECT_BYTES 8
#define HOST_SLOT_AES_DESK_FUN_MSG      0x7f108  /* $fdfda6's -16(a6): the message appl_write is handed           */
#define HOST_SLOT_AES_DESK_FUN_MSG_BYTES 16
#define HOST_SLOT_AES_DESK_MY_ITOA_NUMBER 0x7f118 /* $fde500's 8(a6): its own argument word, merge_str's parameter */
#define HOST_SLOT_AES_DESK_MY_ITOA_NUMBER_BYTES 2
#define HOST_SLOT_AES_DESK_OB_SFCB_FRAME 0x7f11a /* $fde610's -50(a6) up: the size, time, date texts, the SFCB copy */
#define HOST_SLOT_AES_DESK_OB_SFCB_FRAME_BYTES 50
#define HOST_SLOT_AES_DESK_INF_DTTMSZ_FRAME 0x7f14c /* $fdea9a's -26(a6) up: the date, time and size texts         */
#define HOST_SLOT_AES_DESK_INF_DTTMSZ_FRAME_BYTES 26
/* ---- end of group G4's ---- */
/* BAND 6 WAVE 2: an ADDRESS WINDOW per group, cut from the one free run the prep's re-lay left ($7f7a6..$7f9d2, 556 B)
 * and sized to the cut's measured need (each routine's span from its lowest handed frame offset to its frame top); the
 * run's last 14 B ($7f9c4..$7f9d2) are KEPT BACK. A group's slots lie inside its own window only — a slot per role, or
 * one slot a unit's routines share where they never nest; `_Static_assert` of each frame against its `_BYTES` in the
 * unit's `.c`. Out of room: STOP and report — never borrow another group's window, never widen the band. Each id in
 * `enum host_slot` below, in its group's region. */
/* ---- band 6 wave 2, group G1 (units C, F, E) ---- window $7f7a6..$7f7dc (54 B) */
/* The two frames the group's routines hand on, each a routine's whole `link` frame laid as the ROM's (they never nest:
 * inf_folder's walk counts with no tree, so draws nothing; the userdef draw runs on the desk's userdef stack) */
#define HOST_SLOT_AES_DESK_INF_FOLDER_FRAME 0x7f7a6 /* $fde9ce's -16(a6) up: the two counts' texts, d_doop's count word */
#define HOST_SLOT_AES_DESK_INF_FOLDER_FRAME_BYTES 16
#define HOST_SLOT_AES_DESK_USERDEF_FRAME 0x7f7b6 /* $fde844's -38(a6) up: the clip kept, the PARMBLK copied           */
#define HOST_SLOT_AES_DESK_USERDEF_FRAME_BYTES 38
/* ---- end of group G1's wave-2 ---- */
/* ---- band 6 wave 2, group G2 (units H, G, M) ---- window $7f7dc..$7f844 (104 B) */
/* Unit H's drivers' frames (`desk/deskfun.h`), each a routine's handed span — its lowest handed offset to its frame top,
 * the ROM's layout: one slot a routine, the six fill the window (they nest: fun_desk2win's over fun_disk, fun_op's,
 * fun_rebld's; each is held across its routine's own yields and waits — the alerts, form_do, the copy engine's). */
#define HOST_SLOT_AES_DESK_FUN_REBLD_FRAME 0x7f7dc /* $fdfdf2's -8(a6) up: wind_get's four answers                */
#define HOST_SLOT_AES_DESK_FUN_REBLD_FRAME_BYTES 8
#define HOST_SLOT_AES_DESK_FUN_MKDIR_FRAME 0x7f7e4 /* $fdfebc's -26(a6) up: the name unformatted, the field's text */
#define HOST_SLOT_AES_DESK_FUN_MKDIR_FRAME_BYTES 26
#define HOST_SLOT_AES_DESK_FUN_D2DESK_FRAME 0x7f7fe /* $fe0500's -42(a6) up: the alerts' parameters and texts, i_find's */
#define HOST_SLOT_AES_DESK_FUN_D2DESK_FRAME_BYTES 42
#define HOST_SLOT_AES_DESK_FUN_OP_FRAME 0x7f828    /* $fe003a's -8(a6) up: the copy engine's three answers        */
#define HOST_SLOT_AES_DESK_FUN_OP_FRAME_BYTES 8
#define HOST_SLOT_AES_DESK_FUN_WIN2WIN_FRAME 0x7f830 /* $fe0258's -8(a6) up: i_find's two answers                 */
#define HOST_SLOT_AES_DESK_FUN_WIN2WIN_FRAME_BYTES 8
#define HOST_SLOT_AES_DESK_FUN_DESK2WIN_FRAME 0x7f838 /* $fe0454's -12(a6) up: i_find's answers, both calls'       */
#define HOST_SLOT_AES_DESK_FUN_DESK2WIN_FRAME_BYTES 12
/* ---- end of group G2's wave-2 ---- */
/* ---- band 6 wave 2, group G3 (units I, J, K, L) ---- window $7f844..$7f962 (286 B: $fe1a18's 138 contiguous in it) */
/* fun_close's whole `link` (`desk/desksupp.h`): the spec fpd_parse splits into its extension, name, path and drive
 * word — the ROM's layout, the path's 122 bytes between — HELD while close_window or close_folder runs over it (the
 * folder's path, name and extension are handed on down to do_fopen and do_diropen, across their yields and the waits
 * of drive_check's retry alert and do_diropen's failure alert). */
#define HOST_SLOT_AES_DESK_FUN_CLOSE_FRAME 0x7f844 /* $fe1a18's -138(a6) up                                      */
#define HOST_SLOT_AES_DESK_FUN_CLOSE_FRAME_BYTES 138 /* FUN_CLOSE_FRAME_BYTES                                    */
/* Unit I's openers' (`desk/deskwin.h`): desk_clear's and desk_verify's work area, do_wopen's corner and two
 * rectangles — no one of the three calls another or is called while another holds it. */
#define HOST_SLOT_AES_DESK_OPEN_FRAME   0x7f8ce  /* $fe0e38's 14(a6), 16(a6), -8(a6), -16(a6) (compacted)          */
#define HOST_SLOT_AES_DESK_OPEN_FRAME_BYTES 20   /* OPEN_FRAME_BYTES                                             */
/* Unit J's (`desk/desksupp.h`): do_fopen's, close_folder's and close_window's work areas, desk_do_format's command tail
 * and its pointer and app_afind's answer — no one of the four nests in another. do_fopen's is HELD across do_diropen
 * (its rectangle is do_diropen's `pt`), desk_do_format's ACROSS fun_alert's WAIT (its tail is read after it). */
#define HOST_SLOT_AES_DESK_SUPP_FRAME   0x7f8e2  /* $fe1800's -16(a6) up; $fe14ba's / $fe1972's -12(a6) up         */
#define HOST_SLOT_AES_DESK_SUPP_FRAME_BYTES 16   /* SUPP_FRAME_BYTES                                             */
/* Unit K's (`desk/desktop.h`): cnx_get's extension, name and drive word, the ROM's layout — HELD across do_diropen. */
#define HOST_SLOT_AES_DESK_CNX_GET_FRAME 0x7f8f2 /* $fe2618's -14(a6) up                                         */
#define HOST_SLOT_AES_DESK_CNX_GET_FRAME_BYTES 14 /* CNX_GET_FRAME_BYTES                                         */
/* Unit L's (`desk/deskview.h`): win_blt's two rectangles, win_slide's wind_get answers, win_bdall's work area — given
 * back before each calls another of the unit. */
#define HOST_SLOT_AES_DESK_SCROLL_FRAME 0x7f900  /* $fe3310's -30(a6) and -22(a6) (compacted)                    */
#define HOST_SLOT_AES_DESK_SCROLL_FRAME_BYTES 16 /* SCROLL_FRAME_BYTES                                           */
/* ---- end of group G3's wave-2 ---- */
/* ---- band 6 wave 2, group G4 (units A, B) ---- window $7f962..$7f9c4 (98 B) */
/* Unit B's drag (`desk/deskact.h`): gr_drgplns's rectangles and the words it hands graf_mkstate and i_find, with the two
 * argument words graf_mkstate writes; act_bdown's rubber box, the drop's corner and window, evnt_button's answers and
 * the three argument words it writes. act_bdown calls gr_drgplns holding its own: two slots. BOTH ARE HELD ACROSS THE
 * DRAG'S WAITS — gr_bwait's evnt_multi, every turn of the loop, and act_bdown's evnt_button after it — a "held where
 * parked" fact of the binding's (`aes_event.SLOTS_HELD_WHERE_PARKED`). */
#define HOST_SLOT_AES_GR_DRGPLNS_FRAME  0x7f962  /* $fdc57a's -56(a6)..-30(a6), then 8(a6), 10(a6)                 */
#define HOST_SLOT_AES_GR_DRGPLNS_FRAME_BYTES 30  /* DRGPLNS_FRAME_BYTES                                           */
#define HOST_SLOT_AES_ACT_BDOWN_FRAME   0x7f980  /* $fdcd34's -28(a6)..-20(a6), -12(a6)..-2(a6), 16..20(a6)        */
#define HOST_SLOT_AES_ACT_BDOWN_FRAME_BYTES 24   /* ACT_BDOWN_FRAME_BYTES                                        */
/* Unit A's: app_start's word the INF's #E line is scanned into (scan_2's answer), twice. */
#define HOST_SLOT_AES_APP_START_ENVIRONMENT 0x7f998 /* $fdb5fc's -14(a6)                                         */
#define HOST_SLOT_AES_APP_START_ENVIRONMENT_BYTES 2 /* APP_START_ENVIRONMENT_BYTES                               */
/* ---- end of group G4's wave-2 ---- */
/* ...and the screen manager's handlers' (`aes/gemctrl.h`). hctl_window's: the window's rectangle with the four words
 * r_get unpacks it into, and the elevator's corner ob_offset answers into — each read out and given back before any
 * wait; THE RECTANGLE A DRAG IS HELD BY (gr_dragbox's bound, gr_rubwind's twin offsets) and THE TWO WORDS IT ANSWERS
 * INTO, live in the screen manager's frame across every wait of the drag — A SLOT PER PROCESS each (below; COMPACTED,
 * not the frame's layout: no gap of the band holds nine frames of the ROM's 36 bytes). hctl_rect's: mn_do's two
 * answers, live across every wait of the menu — a slot per process too. */
/* ...and THEIR CALLER's, ctlmgr's (`aes/gemctrl.h`): the six answer words it hands its main wait, live for as long as
 * the screen manager sleeps in it. ONE FRAME: the screen manager alone runs ctlmgr, and is in it once. */
#define HOST_SLOT_AES_CTLMGR_ANSWERS   0x7f3ae  /* $fe49d2's -12(a6) up: `link a6,#-12`                          */
#define HOST_SLOT_AES_CTLMGR_ANSWERS_BYTES 12   /* EV_MULTI_ANSWER_WORDS words                                   */
#define HOST_SLOT_AES_HCTL_WINDOW_SIZE  0x7f1fc  /* $fe45a2's -8(a6) rectangle, then its -18..-24(a6) x, y, w, h   */
#define HOST_SLOT_AES_HCTL_WINDOW_SIZE_BYTES 16  /* HCTL_SIZE_BYTES                                              */
#define HOST_SLOT_AES_HCTL_WINDOW_CORNER 0x7f20c /* $fe45a2's -30(a6) x, -32(a6) y: ob_offset's answers          */
#define HOST_SLOT_AES_HCTL_WINDOW_CORNER_BYTES 4 /* HCTL_CORNER_BYTES                                            */
#define HOST_SLOT_AES_HCTL_WINDOW_DRAG_RECT 0x7f23c /* $fe45a2's -16(a6) bound, or its -8(a6) offsets             */
#define HOST_SLOT_AES_HCTL_WINDOW_DRAG_RECT_BYTES 72 /* HOST_PROCESSES (9) frames of a GRECT's eight bytes        */
#define HOST_SLOT_AES_HCTL_WINDOW_DRAG_ANSWERS 0x7f1ba /* $fe45a2's -18/-20(a6) corner, or its -22/-24(a6) size    */
#define HOST_SLOT_AES_HCTL_WINDOW_DRAG_ANSWERS_BYTES 36 /* HOST_PROCESSES (9) frames of two words                  */
#define HOST_SLOT_AES_HCTL_RECT_CHOICE  0x7f47e  /* $fe4908's -4(a6) item, -2(a6) title                          */
#define HOST_SLOT_AES_HCTL_RECT_CHOICE_BYTES 36  /* HOST_PROCESSES (9) frames of HCTL_CHOICE_BYTES (4)           */
/* ...and the waits' (`aes/evwait.h`, `aes/evlib.h`): amouse's copy of the MOBLK it is handed (to lbcopy and inside),
 * and the QPB that ap_rdwr's own arguments are — the process, the length, the buffer — whose address it hands
 * ev_block (a wait that parks keeps that address in its EVB: a place in its caller's stack, by nature). The QPB is A
 * SLOT PER PROCESS (below): the wait's EVB points into it for as long as its process is blocked. */
#define HOST_SLOT_AES_AMOUSE_MOBLK      0x7f5fc  /* $fe5666's -10(a6) up                                         */
#define HOST_SLOT_AES_AMOUSE_MOBLK_BYTES 10      /* EV_MOBLK_WORDS words                                         */
#define HOST_SLOT_AES_AP_RDWR_QPB       0x7f60e  /* $fe65c4's 10(a6) up: its arguments after the code            */
#define HOST_SLOT_AES_AP_RDWR_QPB_BYTES 72       /* HOST_PROCESSES (9) frames of AP_RDWR_QPB_BYTES (8): evlib.c holds it */
/* ...and ev_multi's own QPB (`aes/evmulti.h`): where it waits for a MESSAGE among other events it builds the QPB in
 * its own frame — the running process, sixteen bytes, the caller's buffer — and hands iasync its address ($fe6b40..
 * $fe6b54), which the pipe's wait keeps as ap_rdwr's is kept. A SLOT PER PROCESS for the same reason. */
#define HOST_SLOT_AES_EV_MULTI_QPB      0x7f58c  /* $fe6998's -8(a6) up: the process, the length, the buffer     */
#define HOST_SLOT_AES_EV_MULTI_QPB_BYTES 72      /* HOST_PROCESSES (9) frames of the QPB's eight bytes: evmulti.c holds it */
/* ...and the posts' (`aes/evinput.h`): the rectangle inorout unpacks from a mouse wait's EVB (to inside). */
#define HOST_SLOT_AES_INOROUT_RECT      0x7f606  /* $fe54b8's -8(a6) up                                          */
#define HOST_SLOT_AES_INOROUT_RECT_BYTES 8       /* INOROUT_RECT_BYTES                                           */

/* A SLOT PER PROCESS: a frame local that stays LIVE WHILE ITS PROCESS IS BLOCKED — its routine reached the dispatcher
 * with the local's address parked in a record ANOTHER process reads (ap_rdwr's QPB, through its pipe wait's EVB: the
 * desk parked in its read, the screen manager's write serving it through that address). In the ROM each is on its own
 * process's stack; off target the role's span is HOST_PROCESSES frames, the running process's id choosing one — an
 * address the image alone decides, the same in whichever host run the frame was laid — each with its own held flag:
 * a process is never in the routine twice, which is refused as every claim of a held slot is.
 *
 * THE AUDIT OF EVERY OTHER SLOT HELD ACROSS A WAIT (band 4 wave 3; read off the runs, and pinned:
 * `test_aes_event.SLOTS_HELD_WHERE_PARKED`). A door user holds frames of its own while its process is PARKED inside
 * the event layer: gr_stilldn's rectangle and answers (under gr_wait, gr_watchbox, the drag loops and fm_button too),
 * gr_watchbox's rectangle, gr_rubwind's, gr_dragbox's frame, gr_slidebox's rectangles, mn_do's frame, fm_do's and
 * fm_button's. EACH IS ONE FRAME FOR EVERY PROCESS, and that is sound only while ONE C process can be inside the
 * routine ON THE HOST — which is every host run there is: the host does not switch stacks, so the one process whose
 * C a run holds is its CALLER's, and any other process the scheduler enters is the ROM's own code (the model's
 * nested run, `aes_switch.Scheduling`), which claims nothing. THAT THE SCREEN MANAGER IS C ON TARGET (band 5 wave 2:
 * ctlmgr in mn_do while the desk sits in fm_do or a drag) CHANGES NOTHING HERE: a slot is a host thing, and on the
 * machine each frame is on its own process's stack. What these roles owe is owed THE DAY THE HOST RUNS A SECOND
 * PROCESS'S C — a model that resumes a parked process in C, which is not built: HOST_PROCESSES frames each, claimed
 * with `host_slot_claim_for` as the two QPBs are. Until then the invariant is HELD, not assumed
 * (`test_aes_event.py`): the model's process hook is the ROM's nested run and nothing else; a second process's C
 * forced in through that hook is refused where it begins (ctlmgr's host entries, `src/aes/ctlmgr.c`) and, were it to
 * reach a shared role, where it claims (`host_slot_take`, by name). A slot NEWLY held across a wait reds the table.
 * WHAT IS HELD TODAY, on every door user's run through the host's model: the call RETURNS with no slot held (the
 * give-back after a wait, which no host run reached before a call could come back from one). */
#define HOST_PROCESSES                  9        /* the AES's: three static PDs and six accessories ($fe445a cmp.w #6) */

/* Each slot's index in the held flags. */
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
    HOST_SLOT_ID_AES_GR_STILLDN_RECTANGLE,
    HOST_SLOT_ID_AES_GR_STILLDN_ANSWERS,
    HOST_SLOT_ID_AES_GR_WATCHBOX_RECT,
    HOST_SLOT_ID_AES_GR_DRAW_RECT,
    HOST_SLOT_ID_AES_GR_CLAMP_MOUSE,
    HOST_SLOT_ID_AES_GR_RUBWIND_RECT,
    HOST_SLOT_ID_AES_GR_DRAGBOX_FRAME,
    HOST_SLOT_ID_AES_GR_SLIDEBOX_RECTS,
    HOST_SLOT_ID_AES_MENU_SR_RECT,
    HOST_SLOT_ID_AES_MN_DO_FRAME,
    HOST_SLOT_ID_AES_MN_REGISTER_NAME,
    HOST_SLOT_ID_AES_PXL_RECT_FIELD,
    HOST_SLOT_ID_AES_CURFLD_RECTS,
    HOST_SLOT_ID_AES_OB_EDIT_FRAME,
    HOST_SLOT_ID_AES_W_CLIPDRAW_RECT,
    HOST_SLOT_ID_AES_W_CPWALK_RECT,
    HOST_SLOT_ID_AES_W_MOVE_RECTS,
    HOST_SLOT_ID_AES_WM_GET_RECT,
    HOST_SLOT_ID_AES_W_SETACTIVE_RECT,
    HOST_SLOT_ID_AES_W_REDRAW_RECTS,
    HOST_SLOT_ID_AES_DRAW_CHANGE_FRAME,
    HOST_SLOT_ID_AES_WM_OPCL_RECT,
    HOST_SLOT_ID_AES_WM_SET_RECT,
    HOST_SLOT_ID_AES_FM_PARSE_INDEX,
    HOST_SLOT_ID_AES_FM_BUILD_RECTS,
    HOST_SLOT_ID_AES_FM_DO_FRAME,
    HOST_SLOT_ID_AES_FM_BUTTON_FRAME,
    HOST_SLOT_ID_AES_FM_ALERT_FRAME,
    HOST_SLOT_ID_AES_ERALERT_FRAME,
    HOST_SLOT_ID_AES_FM_ERROR_CODE,
    HOST_SLOT_ID_AES_FS_START_TREE,
    HOST_SLOT_ID_AES_FS_FORMAT_FRAME,
    HOST_SLOT_ID_AES_FS_NSCROLL_FRAME,
    HOST_SLOT_ID_AES_FS_INPUT_FRAME,
    HOST_SLOT_ID_AES_PD_MATCH_NAME,
    HOST_SLOT_ID_AES_AP_FIND_NAME,
    HOST_SLOT_ID_AES_MARSHAL_FRAME,
    HOST_SLOT_ID_AES_DISPATCH_MOUSE_FORM,
    HOST_SLOT_ID_AES_PGMLD_WORDS,
    HOST_SLOT_ID_AES_SNDCLI_BASEPAGE, /* band 5 wave 3, slice L */
    HOST_SLOT_ID_AES_READ_INF_PAIR,   /* band 5 wave 4, slice I */
    HOST_SLOT_ID_AES_GEM_MAIN_ICON,   /* band 5 wave 4, slice I */
    HOST_SLOT_ID_AES_DESK_BIND_FRAME, /* band 6 wave 1a, unit D */
    HOST_SLOT_ID_AES_DOS_LABEL_FRAME, /* band 6 wave 1a, unit O */
    HOST_SLOT_ID_AES_DOS_SPACE_DFREE, /* band 6 wave 1a, unit O */
    HOST_SLOT_ID_AES_DOS_SETDT_STAMP, /* band 6 wave 1a, unit O */
    /* ---- band 6 wave 1b, group G1 (units I, L) ---- */
    HOST_SLOT_ID_AES_DESK_WIN_FRAME,  /* band 6 wave 1b, group G1 */
    HOST_SLOT_ID_AES_DESK_VIEW_FRAME, /* band 6 wave 1b, group G1 */
    /* ---- end of group G1's ---- */
    /* ---- band 6 wave 1b, group G2 (units A, K, J) ---- */
    HOST_SLOT_ID_AES_APP_TRAN_BITBLK, /* band 6 wave 1b, group G2 */
    HOST_SLOT_ID_AES_MEN_UPDATE_FIND, /* band 6 wave 1b, group G2 */
    /* ---- end of group G2's ---- */
    /* ---- band 6 wave 1b, group G3 (units B, G) ---- */
    HOST_SLOT_ID_AES_GR_ISDOWN_ANSWERS,   /* band 6 wave 1b, group G3 */
    HOST_SLOT_ID_AES_GR_BWAIT_ANSWERS,    /* band 6 wave 1b, group G3 */
    HOST_SLOT_ID_AES_ACT_CHKOBJ_RECTS,    /* band 6 wave 1b, group G3 */
    HOST_SLOT_ID_AES_ACT_CHG_RECT,        /* band 6 wave 1b, group G3 */
    HOST_SLOT_ID_AES_ACT_ALLCHG_RECTS,    /* band 6 wave 1b, group G3 */
    /* ---- end of group G3's ---- */
    /* ---- band 6 wave 1b, group G4 (units C, H, E, F) ---- */
    HOST_SLOT_ID_AES_DESK_DIR_RECT,          /* band 6 wave 1b, group G4 */
    HOST_SLOT_ID_AES_DESK_FUN_MSG,           /* band 6 wave 1b, group G4 */
    HOST_SLOT_ID_AES_DESK_MY_ITOA_NUMBER,    /* band 6 wave 1b, group G4 */
    HOST_SLOT_ID_AES_DESK_OB_SFCB_FRAME,     /* band 6 wave 1b, group G4 */
    HOST_SLOT_ID_AES_DESK_INF_DTTMSZ_FRAME,  /* band 6 wave 1b, group G4 */
    /* ---- end of group G4's ---- */
    /* ---- band 6 wave 2, group G1 (units C, F, E) ---- */
    HOST_SLOT_ID_AES_DESK_INF_FOLDER_FRAME,
    HOST_SLOT_ID_AES_DESK_USERDEF_FRAME,
    /* ---- end of group G1's wave-2 ---- */
    /* ---- band 6 wave 2, group G2 (units H, G, M) ---- */
    HOST_SLOT_ID_AES_DESK_FUN_REBLD_FRAME,
    HOST_SLOT_ID_AES_DESK_FUN_MKDIR_FRAME,
    HOST_SLOT_ID_AES_DESK_FUN_D2DESK_FRAME,
    HOST_SLOT_ID_AES_DESK_FUN_OP_FRAME,
    HOST_SLOT_ID_AES_DESK_FUN_WIN2WIN_FRAME,
    HOST_SLOT_ID_AES_DESK_FUN_DESK2WIN_FRAME,
    /* ---- end of group G2's wave-2 ---- */
    /* ---- band 6 wave 2, group G3 (units I, J, K, L) ---- */
    HOST_SLOT_ID_AES_DESK_FUN_CLOSE_FRAME,
    HOST_SLOT_ID_AES_DESK_OPEN_FRAME,
    HOST_SLOT_ID_AES_DESK_SUPP_FRAME,
    HOST_SLOT_ID_AES_DESK_CNX_GET_FRAME,
    HOST_SLOT_ID_AES_DESK_SCROLL_FRAME,
    /* ---- end of group G3's wave-2 ---- */
    /* ---- band 6 wave 2, group G4 (units A, B) ---- */
    HOST_SLOT_ID_AES_GR_DRGPLNS_FRAME,       /* band 6 wave 2, group G4 */
    HOST_SLOT_ID_AES_ACT_BDOWN_FRAME,        /* band 6 wave 2, group G4 */
    HOST_SLOT_ID_AES_APP_START_ENVIRONMENT,  /* band 6 wave 2, group G4 */
    /* ---- end of group G4's wave-2 ---- */
    HOST_SLOT_ID_AES_HCTL_WINDOW_SIZE,
    HOST_SLOT_ID_AES_HCTL_WINDOW_CORNER,
    HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_RECT,     /* a slot per process: the screen manager's frame across a drag's waits */
    HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_RECT_LAST = HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_RECT + HOST_PROCESSES - 1,
    HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_ANSWERS,  /* a slot per process: ...and the two words the drag answers into */
    HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_ANSWERS_LAST = HOST_SLOT_ID_AES_HCTL_WINDOW_DRAG_ANSWERS + HOST_PROCESSES - 1,
    HOST_SLOT_ID_AES_HCTL_RECT_CHOICE,          /* a slot per process: mn_do's answers across the menu's waits */
    HOST_SLOT_ID_AES_HCTL_RECT_CHOICE_LAST = HOST_SLOT_ID_AES_HCTL_RECT_CHOICE + HOST_PROCESSES - 1,
    HOST_SLOT_ID_AES_CTLMGR_ANSWERS,
    HOST_SLOT_ID_AES_AMOUSE_MOBLK,
    HOST_SLOT_ID_AES_AP_RDWR_QPB,     /* a slot per process: HOST_PROCESSES flags, this one process 0's */
    HOST_SLOT_ID_AES_AP_RDWR_QPB_LAST = HOST_SLOT_ID_AES_AP_RDWR_QPB + HOST_PROCESSES - 1,
    HOST_SLOT_ID_AES_EV_MULTI_QPB,    /* a slot per process too */
    HOST_SLOT_ID_AES_EV_MULTI_QPB_LAST = HOST_SLOT_ID_AES_EV_MULTI_QPB + HOST_PROCESSES - 1,
    HOST_SLOT_ID_AES_INOROUT_RECT,
    HOST_SLOT_ID_COUNT                /* not a slot: how many there are */
};

/* A frame's slot AS A TARGET LOCAL (`uint16_t frame_local[FRAME_LOCAL_WORDS(<slot bytes>)]`): WORDS, so the frame
 * starts on an even address. Its words and longs are read and written in place (`wr16`/`be32` are native accesses on
 * target), and a `uint8_t` array of the slot's odd size is packed at an odd offset — an address error on every call
 * on a 68000. */
#define FRAME_LOCAL_WORDS(slot_bytes)  (((slot_bytes) + 1) / 2)

#ifdef RECREATE_HOST_DIFFERENTIAL
/* One flag per slot, defined in `src/host_slot.c`: an array, so the table has no width to outgrow (a bit mask did,
 * twice — 32 bits, then 64). */
extern unsigned char host_slots_held[HOST_SLOT_ID_COUNT];

static inline uint32_t host_slot_take(enum host_slot slot, uint32_t host_at)
{
    if (host_slots_held[slot])
        recreate_not_reconstructed("a host slot claimed while it is held: a routine entered again before it gave its "
                                   "frame back — by itself, or by A SECOND PROCESS'S C, which the host does not run: "
                                   "the role is one frame for every process (host_slot.h, THE AUDIT)");
    host_slots_held[slot] = 1;
    return host_at;
}

static inline void host_slot_give_back(enum host_slot slot)
{
    host_slots_held[slot] = 0;
}

/* ...and of a SLOT PER PROCESS, `process`'s frame of the role's span. A process id that is none of the AES's — a PD
 * whose id word is out of range, `rlr` holding no PD at all — is REFUSED BY NAME: the ROM's routine never reads the
 * id (its frame is on whatever stack it is run on) and carries on, and off target there is no frame to hand it. */
static inline uint32_t host_slot_take_for(enum host_slot slot, uint32_t host_at, uint32_t span_bytes, uint32_t process)
{
    if (process >= HOST_PROCESSES)
        recreate_not_reconstructed("a frame local kept per process, for a running process whose id is none of the "
                                   "AES's (HOST_PROCESSES): off target its frame is its process's host slot");
    return host_slot_take((enum host_slot)(slot + process), host_at + process * (span_bytes / HOST_PROCESSES));
}

/* ...and given back BY THE ADDRESS THE CLAIM ANSWERED — the frame that was claimed, whichever process is running
 * by now: a routine that blocked comes back after other processes ran, and the running one is asked nothing. */
static inline void host_slot_give_back_for(enum host_slot slot, uint32_t host_at, uint32_t span_bytes, uint32_t claimed)
{
    uint32_t frame = (claimed - host_at) / (span_bytes / HOST_PROCESSES);

    assert(frame < HOST_PROCESSES && host_slots_held[slot + frame]);
    host_slot_give_back((enum host_slot)(slot + frame));
}

/* The image address a frame local of role ROLE is handed on at: its slot, claimed, off target... */
#define host_slot_claim(ROLE, local) \
    ((void)(local), host_slot_take(HOST_SLOT_ID_##ROLE, HOST_SLOT_##ROLE))
#define host_slot_release(ROLE) host_slot_give_back(HOST_SLOT_ID_##ROLE)
#define host_slot_claim_for(ROLE, local, process) \
    ((void)(local), host_slot_take_for(HOST_SLOT_ID_##ROLE, HOST_SLOT_##ROLE, HOST_SLOT_##ROLE##_BYTES, process))
#define host_slot_release_for(ROLE, claimed) \
    host_slot_give_back_for(HOST_SLOT_ID_##ROLE, HOST_SLOT_##ROLE, HOST_SLOT_##ROLE##_BYTES, claimed)
#else
/* ...and the local's own address on target, where nothing is held (and `process` is not evaluated: the local is on
 * the running process's stack already). */
#define host_slot_claim(ROLE, local) ((uint32_t)(uintptr_t)(local))
#define host_slot_release(ROLE) ((void)0)
#define host_slot_claim_for(ROLE, local, process) ((uint32_t)(uintptr_t)(local))
#define host_slot_release_for(ROLE, claimed) ((void)0)
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

/* ...and a slot whose WORDS a core builds as a C local and hands on to be READ (gr_stilldn's MOBLK): copied into the
 * slot off target, the local itself on target. */
static inline void host_slot_store_words(uint8_t *image, uint32_t slot_at, const uint16_t *local, uint32_t words)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    for (uint32_t word = 0; word < words; word++)
        wr16(image + slot_at + word * sizeof *local, local[word]);
#else
    (void)image, (void)slot_at, (void)local, (void)words;
#endif
}

/* ...and a slot whose WORDS a callee ANSWERS INTO, read back as the C local they are (ctlmgr's answers: read through
 * the image on target they would cost its frame two address registers, `src/aes/ctlmgr.c`): copied out of the slot
 * off target, the local itself on target. */
static inline void host_slot_load_words(const uint8_t *image, uint32_t slot_at, uint16_t *local, uint32_t words)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    for (uint32_t word = 0; word < words; word++)
        local[word] = be16(image + slot_at + word * sizeof *local);
#else
    (void)image, (void)slot_at, (void)local, (void)words;
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
