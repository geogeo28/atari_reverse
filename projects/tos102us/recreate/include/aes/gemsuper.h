/* aes/gemsuper.h — THE AES'S OPCODE SWITCH and the copy round it (`src/aes/gemsuper.c`, GEM's gemsuper): what a
 * program's `trap #2` reaches once the trap door has taken its process's stack.
 *
 *   $fe64e6 aes_marshal(parameter block)    the program's control, int_in and addr_in copied into its own frame, the
 *                                           switch called over the copies, its answer and int_out copied back — and
 *                                           rsrc_gaddr's address, into addr_out
 *   $fe5d9c aes_dispatch(opcode, global, int_in, int_out, addr_in)
 *                                           ONE routine: a head, a jump through the table at $fef834 (opcodes
 *                                           10..125, 116 longwords naming 69 arms), a ladder of `tst.w (sp)+` the
 *                                           arms leave by, `move.w d6,d0` — D0.w: the call's answer, int_out[0]
 *
 * THE SWITCH'S ARMS ARE NOT ROUTINES (the inventory counted 69 of them): each is a label inside $fe5d9c..$fe64e5,
 * reached by `jmp (a0)` and left by a branch into the ladder. An arm reads its arguments out of int_in and addr_in,
 * hands the answer words' ADDRESSES in int_out on, and keeps what its routine answers in D6 — or keeps D6's 1
 * (`moveq #1,d6`, $fe5da8): the arms that ignore their routine's D0 ANSWER 1 WHATEVER IT DID (scrp_read, fsel_input,
 * wind_open, wind_get, objc_draw, ...). The 48 opcodes of the range with no routine, and every opcode outside it,
 * share the default arm: the alert "Bad Function #" and -1.
 *
 * ALCYON C, each entered by a Line-F call over its caller's frame (the dispatch's opcode a WORD, its four pointers
 * longwords). aes_entry ($fe65aa, 26 bytes) — which calls the marshal for selector 200 alone, then dsptch — ships with
 * the trap door.
 */
#ifndef TOS102US_AES_GEMSUPER_H
#define TOS102US_AES_GEMSUPER_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"

/* ---- the program's PARAMETER BLOCK: six pointers, read where each is used ($fe64ee .. $fe659e) ------------------- */
#define AESPB_CONTROL        0          /* long                                ($fe64ee movea.l 8(a6),a0 / (a0)) */
#define AESPB_GLOBAL         4          /* long                                ($fe654e movea.l #4,a0)         */
#define AESPB_INT_IN         8          /* long                                ($fe6506 movea.l #8,a0)         */
#define AESPB_INT_OUT        12         /* long                                ($fe657a movea.l #12,a0)        */
#define AESPB_ADDR_IN        16         /* long                                ($fe652c movea.l #16,a0)        */
#define AESPB_ADDR_OUT       20         /* long                                ($fe6594 movea.l #20,a0)        */

/* ---- THE MARSHAL'S FRAME (`link a6,#-66`: four bytes of Alcyon's argument slot below), from -62(a6), as the ROM lays
 * it: the three copies and the answer words. NO COPY IS BOUNDED BY ITS ARRAY — each takes its count from the copied
 * control — so a count past an array runs into the arrays above it, and past the frame into the saved A6 and the
 * return address (`src/aes/gemsuper.c`, THE COUNTS). */
#define MARSHAL_ADDR_IN       0          /* longs[2]                            ($fe653a pea -62(a6))           */
#define MARSHAL_INT_OUT       8          /* words[7]: [0] the switch's answer   ($fe6546 pea -54(a6); $fe6568)  */
#define MARSHAL_INT_IN        22         /* words[16]                           ($fe6514 pea -40(a6))           */
#define MARSHAL_CONTROL       54         /* words[4]: the opcode and three counts ($fe64f4 pea -8(a6))          */
#define MARSHAL_FRAME_BYTES   62
/* The copied control's words: the opcode, and how many words of int_in, of int_out, and longwords of addr_in. */
#define MARSHAL_OPCODE        (MARSHAL_CONTROL + 0)      /* ($fe655c move.w -8(a6),-(sp); $fe658c cmpi.w #112) */
#define MARSHAL_N_INT_IN      (MARSHAL_CONTROL + 2)      /* ($fe64fc tst.w -6(a6))                             */
#define MARSHAL_N_INT_OUT     (MARSHAL_CONTROL + 4)      /* ($fe656c tst.w -4(a6))                             */
#define MARSHAL_N_ADDR_IN     (MARSHAL_CONTROL + 6)      /* ($fe651c tst.w -2(a6))                             */
#define MARSHAL_CONTROL_WORDS 4          /* ($fe64ea move.w #4,(sp)): control[4], addr_out's count, is never read */
/* How many WORDS each copy may move and stay inside the frame: from its array's place to the frame's top. The two
 * copies IN are refused past it (they would STORE over the saved A6 and the return address); the copy BACK only READS
 * past it, and is reproduced (`src/aes/gemsuper.c`, THE COUNTS). */
#define MARSHAL_INT_IN_ROOM   ((MARSHAL_FRAME_BYTES - MARSHAL_INT_IN) / 2)       /* 20: the array's 16, then control  */
#define MARSHAL_ADDR_IN_ROOM  ((MARSHAL_FRAME_BYTES - MARSHAL_ADDR_IN) / 2)      /* 31: the whole frame              */
#define MARSHAL_INT_OUT_ROOM  ((MARSHAL_FRAME_BYTES - MARSHAL_INT_OUT) / 2)      /* 27: int_out, int_in, control     */
/* WHAT LIES ABOVE THE FRAME, which a copy back of more than 27 words hands the program: in the ROM the saved A6, the
 * return address ($fe65bc, aes_entry's) and the marshal's argument, the parameter block's address; in our build what
 * GCC's frame has there — the saved A6, OUR return address, the image pointer and then the block's address. OFF
 * TARGET the frame is a host slot and no stack lies above it: the slot runs on by these sixteen bytes, A MODEL of the
 * caller's words that a case stages (the C never writes it), and a count that would read past the model is refused
 * by name — off target alone. */
#define MARSHAL_HOST_CALLER_BYTES 16     /* the saved A6, the return address, and two longwords of arguments         */
#define MARSHAL_HOST_INT_OUT_ROOM (MARSHAL_INT_OUT_ROOM + MARSHAL_HOST_CALLER_BYTES / 2)     /* 35 words           */

/* ---- THE SWITCH -------------------------------------------------------------------------------------------------- */
/* What an arm answers when it keeps none of its routine's ($fe5da8 moveq #1,d6), and the default arm's ($fe64b6). */
#define AES_ANSWER_DONE       1
#define AES_ANSWER_NO_SUCH_CALL (-1)
/* The opcodes `addrs.h` pairs with no routine (AES_ROM_<FN>_OPCODE: the arm calls one routine by one Line-F word):
 * an arm that is inline, falls into another's, or makes several calls. */
#define AES_APPL_INIT_OPCODE  10         /* inline                              (table[0]  -> $fe5db2)          */
#define AES_APPL_READ_OPCODE  11         /* `moveq #1,d0`, then appl_write's call (table[1]  -> $fe5df2)        */
#define AES_APPL_EXIT_OPCODE  19         /* mn_clsda, the pipe drained, all_run (table[9]  -> $fe5e40)          */
#define AES_MENU_TEXT_OPCODE  34         /* lstcpy over the item's ob_spec      (table[24] -> $fe5fee)          */
#define AES_GRAF_HANDLE_OPCODE 77        /* inline                              (table[67] -> $fe6266)          */
#define AES_GRAF_MOUSE_OPCODE 78         /* gsx_moff / gsx_mon / rs_gaddr + gsx_mfset (table[68] -> $fe628e)    */

/* appl_init's answers in the program's global[] ($fe5db2 .. $fe5dde): the AES's version, how many applications it
 * runs at once, the caller's id — and, from global[10], the screen's planes, THEGLO's address and the two words the
 * desk keeps for the drives it found. */
#define AES_GLOBAL_VERSION    0          /* word: $0120                         ($fe5db4 move.l #$01200001,(a0)+) */
#define AES_GLOBAL_COUNT      2          /* word: 1                             (the same longword's low half)  */
#define AES_GLOBAL_ID         4          /* word: the running process's id      ($fe5dc0 move.w 28(a1),(a0))    */
#define AES_GLOBAL_NPLANES    20         /* word: gl_nplanes                    ($fe5dc6 adda.l #20; $fe5dcc)   */
#define AES_GLOBAL_THEGLO     22         /* long: THEGLO's address              ($fe5dd2 move.l #$9c58,(a0)+)   */
#define AES_GLOBAL_BVDISK     26         /* word                                ($fe5dd8)                       */
#define AES_GLOBAL_BVHARD     28         /* word                                ($fe5dde)                       */
#define AES_VERSION           0x0120     /* TOS 1.02's AES                      ($fe5db4)                       */
#define AES_APPLICATIONS      1          /* one at a time                       ($fe5db4)                       */
/* The two words the desk sets with one call of its own ($fdde58 / $fdde60, band 6) and appl_init hands every program:
 * GEM's gl_bvdisk and gl_bvhard, the drive bit vectors. `ctx` names: read from that setter's two stores alone. */
#define AES_GL_BVDISK         0xc850     /* word                                ($fdde58 move.w 8(a6),$c850)    */
#define AES_GL_BVHARD         0xc828     /* word                                ($fdde60 move.w 10(a6),$c828)   */

/* appl_exit drains what is left in the caller's pipe into the object editor's validation buffer (`aes/obedit.h`'s
 * AES_VALSTR, a scratch nothing reads back): one read of as many bytes as the pipe holds ($fe5e4e .. $fe5e66) —
 * ap_rdwr's code for a read, AP_RDWR_READ, is beside its code for a write (`aes/evdoor.h`). */

/* evnt_multi's int_in ($fe5ec2 .. $fe5f30): the flags; the clicks, and the button mask and state that the arm packs
 * into one word's two bytes; the two mouse rectangles, read in place; the timer's count, low word first. */
#define EVNT_MULTI_FLAGS      0
#define EVNT_MULTI_CLICKS     1
#define EVNT_MULTI_MASK       2          /* shifted into the high byte          ($fe5ef4 lsl.w #8,d1)           */
#define EVNT_MULTI_STATE      3
#define EVNT_MULTI_MOUSE1     4          /* words[5]: a MOBLK                   ($fe5f26 .. addq.l #8)          */
#define EVNT_MULTI_MOUSE2     9          /* words[5]                            ($fe5f1c .. addi.l #18)         */
#define EVNT_MULTI_TIME_LOW   14         /* ($fe5eda move.w 28(a0),d0)                                          */
#define EVNT_MULTI_TIME_HIGH  15         /* ($fe5ed4 move.w 30(a0),d0 / swap)                                   */
/* The timer the arm hands ev_multi when the flags ask for none: the ROM hands its own frame's -4(a6) UNSET (whatever
 * the stack held there — ev_multi reads it under EV_MU_TIMER alone); the C hands this. */
#define EVNT_MULTI_NO_TIMER   0

/* The object state each menu arm has do_chg change, as its own immediate ($fe5f6a #4, $fe5fa6 #8, $fe5fd8 #1). */
#define MENU_CHECKED          0x0004     /* menu_icheck: OB_STATE's CHECKED                                     */
#define MENU_DISABLED         0x0008     /* menu_ienable: DISABLED                                              */
#define MENU_SELECTED         0x0001     /* menu_tnormal: SELECTED                                              */
/* menu_ienable's item carries a flag in its top bit — a word's sign bit (`m68k_idioms.h`'s SIGN_BIT16): the bar is
 * redrawn ($fe5f86 andi.w #$8000); the item is the rest ($fe5fb0 andi.w #$7fff). */

/* graf_mouse's form numbers ($fe6292 .. $fe62b0): one of the AES's own forms (the system resource's bit images,
 * three past the number), the caller's own, or the cursor hidden and shown. */
#define GRAF_MOUSE_LAST_FORM  255        /* above it: hide and show             ($fe6292 cmpi.w #255 / bls)     */
#define GRAF_MOUSE_USER_FORM  255        /* addr_in[0] is the form              ($fe62ac cmpi.w #255 / beq)     */
#define GRAF_MOUSE_HIDE       256        /* ($fe6298)                                                           */
#define GRAF_MOUSE_SHOW       257        /* ($fe62a2)                                                           */
#define GRAF_MOUSE_FIRST_IMAGE 3         /* form 0 is bit image 3               ($fe62b8 addq.w #3,(sp))        */

/* graf_mkstate answers what gr_mkstate leaves in D0: its `dbf` counter run out, all ones ($fe8770 moveq #3,d0 ..
 * $fe877a dbf; $fe62fe move.w d0,d6) — NOT the 1 the other arms of no answer keep. */
#define GRAF_MKSTATE_ANSWER   (-1)

/* The default arm's alert ($fe64a6 .. $fe64b2): AES string 27, "Bad Function #", no values, its one button the
 * default. */
#define AES_BAD_FUNCTION_STRING 27
#define AES_BAD_FUNCTION_VALUES 0
#define AES_BAD_FUNCTION_BUTTON 1

/* The ONE word an answer pointer is handed past (two bytes): int_out[0] is the switch's own. */
#define AES_FIRST_ANSWER      1

/* ---- THE ARMS' WORDS, where an arm does not simply push int_in[0], [1], ... in order: each named by its binding's
 * parameter. An arm hands a RECTANGLE by the address of its first word in int_in (four words, read in place) and an
 * ANSWER by the address of its word in int_out. */
#define OBJC_DRAW_CLIP        2          /* int_in[2..5]: the clip              ($fe6056 addq.l #4,(sp))        */
#define OBJC_EDIT_CHAR        1          /* int_in: the object, the character, the index, the kind             */
#define OBJC_EDIT_INDEX       2          /* ...answered back in int_out[1], edited there ($fe60bc move.w 4(a1),2(a0)) */
#define OBJC_EDIT_KIND        3          /* ($fe60c2 move.w 6(a1),(sp))                                         */
#define OBJC_CHANGE_CLIP      2          /* int_in[2..5]: int_in[1] is reserved, never read ($fe60e2 addq.l #4,(sp)) */
#define OBJC_CHANGE_STATE     6          /* ...and both pushed as one longword  ($fe60ea move.l 12(a0),-(sp))   */
#define OBJC_CHANGE_REDRAW    7
#define OBJC_OFFSET_X         1          /* int_out[1], [2]                                                     */
#define OBJC_OFFSET_Y         2
#define FORM_DIAL_LITTLE      1          /* int_in[1..4]: the little box                                        */
#define FORM_DIAL_BIG         5          /* int_in[5..8]: the big one                                           */
#define FORM_KEYBD_KEY        1          /* int_in[1]: the key, answered back in int_out[2]                     */
#define FORM_KEYBD_NEXT       2          /* int_in[2]: the next object, answered back in int_out[1]             */
#define FORM_KEYBD_NEXT_OUT   1
#define FORM_KEYBD_KEY_OUT    2
#define GRAF_BOX_FROM         0          /* graf_growbox / graf_shrinkbox: int_in[0..3], then int_in[4..7]      */
#define GRAF_BOX_TO           4
#define GRAF_RUBBOX_WIDTH     1          /* graf_rubberbox's int_out[1], [2]: the last width and height         */
#define GRAF_RUBBOX_HEIGHT    2
#define GRAF_DRAGBOX_BOUND    4          /* int_in[4..7]: the rectangle the box is kept inside                  */
#define GRAF_DRAGBOX_X        1          /* int_out[1], [2]: where the box was left                             */
#define GRAF_DRAGBOX_Y        2
#define GRAF_WATCHBOX_OBJECT  1          /* int_in[1..3]: int_in[0] is reserved, never read ($fe623c move.l 2(a0)) */
#define GRAF_WATCHBOX_INSIDE  2
#define GRAF_WATCHBOX_OUTSIDE 3
#define GRAF_HANDLE_WCHAR     1          /* int_out[1..4]: a character cell's size, then a box's                */
#define GRAF_HANDLE_HCHAR     2
#define GRAF_HANDLE_WBOX      3
#define GRAF_HANDLE_HBOX      4
#define GRAF_MKSTATE_X        1          /* int_out[1..4]: the mouse, its buttons, the shift keys               */
#define GRAF_MKSTATE_Y        2
#define GRAF_MKSTATE_BUTTONS  3
#define GRAF_MKSTATE_KEYS     4
#define WIND_RECT             1          /* wind_create / wind_open: int_in[1..4], after the kind or the handle */
#define WIND_SET_VALUES       2          /* wind_set: int_in[2..5], after the handle and the field              */
#define WIND_CALC_X           1          /* wind_calc's int_out[1..4]: the rectangle it answers                 */
#define WIND_CALC_Y           2
#define WIND_CALC_W           3
#define WIND_CALC_H           4

#ifndef __ASSEMBLER__
uint16_t aes_dispatch(uint8_t *image, int16_t opcode, uint32_t global, uint32_t int_in, uint32_t int_out,
                      uint32_t addr_in);                                                             /* $fe5d9c */
void aes_marshal(uint8_t *image, uint32_t parameter_block);                                          /* $fe64e6 */
#endif

#endif /* TOS102US_AES_GEMSUPER_H */
