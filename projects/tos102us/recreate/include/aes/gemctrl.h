/* aes/gemctrl.h — the SCREEN MANAGER: its four HANDLERS (`src/aes/gemctrl.c`), what its main loop calls when the wait
 * it sleeps in comes back with a button or with the mouse on the menu bar — they run in the screen manager's process
 * (PD1), on its stack, the screen's lock taken by ctlmgr — and THE LOOP ITSELF with the routine that makes the process
 * (`src/aes/ctlmgr.c`: ctlmgr `$fe49d2`, ictlmgr `$fe4a6a`; below).
 *
 *   $fe456a ct_msgup(message, owner, five words)   the message sent to `owner` (ap_sendmsg, in the manager's own
 *                                                  buffer) unless it is 0 — then the button waited UP, a yield a turn
 *   $fe45a2 hctl_window(window, x, y)              a press on a window: any but the top one is asked to come to the
 *                                                  top; on the top one the gadget under the mouse is worked — a box
 *                                                  watched, the window dragged or rubber-banded, a slider dragged,
 *                                                  an arrow or a page repeated while the button is down — and its
 *                                                  owner told by a message
 *   $fe48ce hctl_button(x, y)                      a button: one the menu bar posted for itself is swallowed; else
 *                                                  the window under the mouse, if it is no part of the desktop
 *   $fe4908 hctl_rect(x, y)                        the mouse on the bar's titles: the menu worked (mn_do) and the
 *                                                  choice sent — MN_SELECTED to the menu's process, or AC_OPEN to
 *                                                  the accessory whose entry it was
 *
 * ALL ALCYON C, each entered by a Line-F call over the frame its caller pushed. D0 is nobody's: ctlmgr reads no
 * answer, and each leaves there what its last callee did.
 */
#ifndef TOS102US_AES_GEMCTRL_H
#define TOS102US_AES_GEMCTRL_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/wmlib.h"

/* ---- the messages the screen manager sends (a message's first word) ------------------------------------------------ */
#define CT_NO_MESSAGE         0          /* nothing to tell: ct_msgup only waits ($fe456e tst.w 8(a6))         */
#define MN_SELECTED_MESSAGE   10         /* a menu item chosen                  ($fe499e moveq #10,d6)         */
#define WM_TOPPED             21         /* a window that is not the top one pressed ($fe489c moveq #21,d4)    */
#define WM_CLOSED             22         /* the closer let go inside its box    ($fe4652 moveq #22,d0)         */
#define WM_FULLED             23         /* ...the fuller                       ($fe4656 moveq #23,d0)         */
#define WM_ARROWED            24         /* an arrow, or a slider's track beside its elevator ($fe47da moveq #24,d4) */
#define WM_HSLID              25         /* the horizontal elevator dragged     ($fe47e4 moveq #25,d0)         */
#define WM_VSLID              26         /* ...the vertical one                 ($fe47e8 moveq #26,d0)         */
#define WM_SIZED              27         /* the sizer rubber-banded             ($fe4792 moveq #27,d4)         */
#define WM_MOVED              28         /* the title dragged                   ($fe46e4 moveq #28,d4)         */
#define AC_OPEN               40         /* an accessory's menu entry chosen    ($fe4994 moveq #40,d6)         */

/* The left button in `aes/gsx.h`'s AES_BUTTON, read as the low byte's bit 0 ($fe4596, $fe4888 btst #0,$c90b). */
#define CT_BUTTON_LOW_BYTE    1
#define CT_LEFT_BUTTON        0x01

/* ---- hctl_window --------------------------------------------------------------------------------------------------- */
/* GEM's MOVER, the one gadget bit the window library itself never reads (`aes/wmlib.h`'s WK_*). */
#define WK_MOVER              0x0008     /* ($fe467a btst #3,10333(a0))                                        */
/* A watched box's state outside the press, and after it: none ($fe4636 clr.w (sp), $fe465e clr.w -(sp)). */
#define HCTL_BOX_NORMAL       0
/* ob_find's depth over W_ACTIVE: deeper than the tree ($fe45d0 move.w #10,-(sp)). */
#define HCTL_FIND_DEPTH       10
/* The rectangle a dragged window's corner is kept in: from the left edge, below the menu bar, as far right as leaves
 * a box and six pixels of the title on the screen — and no bound below ($fe4682..$fe46a2). */
#define HCTL_DRAG_LEFT        0          /* ($fe46a2 clr.w -(sp))                                              */
#define HCTL_DRAG_TITLE_KEPT  6          /* ($fe469a subq.w #6,(sp))                                           */
#define HCTL_DRAG_NO_BOUND    10000      /* ($fe4682 move.w #10000,(sp))                                       */
/* The smallest a window is rubber-banded to: a character cell each way — seven boxes along a side that carries a
 * scroll bar ($fe4722..$fe4766). */
#define HCTL_BAR_BOXES        7          /* ($fe4748 muls.w #7,d6; $fe4766 muls.w #7,d5)                       */
#define HCTL_HORIZONTAL_GADGETS (WK_LFARROW | WK_RTARROW | WK_HSLIDE)             /* ($fe473c andi.w #3584,d0)  */
#define HCTL_VERTICAL_GADGETS (WK_UPARROW | WK_DNARROW | WK_VSLIDE)               /* ($fe475a andi.w #448,d0)   */
/* A press on a slider's track: the page BEFORE the elevator, or — at or past the elevator's corner — the one after,
 * numbered one further on ($fe47ca, $fe47d8 addq.w #1,d3). */
#define HCTL_PAGE_AFTER       1
/* WM_ARROWED's action, by gadget: nine words from the up arrow on — line up, line down, page up, page down, a word
 * no gadget reads (the horizontal bar's), line left, line right, page left, page right ($fe4834 adda.l #$fef7d0). */
#define AES_ARROW_ACTIONS     0xfef7d0   /* words[HCTL_ARROW_ACTIONS]           ($fe483a move.w (a0),-18(a6))  */
#define HCTL_ARROW_ACTIONS    9
#define HCTL_ARROW_ACTION_BYTES 2
/* What ctlmgr holds and an arrow's repeat lets go of: the screen's lock, given up while the owner scrolls and taken
 * again before the handler returns ($fe483e clr.w (sp) .. $fe4896: `aes/wmupdate.h`'s codes). */
#define HCTL_MESSAGE_SENT     1          /* `aes/evlib.h`'s AES_CTL_MESSAGE_SENT ($fe487e move.w #1,$97fe)     */
/* The four words of a message about a window that is NOT the top one: x, y, w and h are locals the ROM never set on
 * that path ($fe489e..$fe48aa push -24..-18(a6)) — what the screen manager's stack holds there. A DECLARED DIVERGENCE
 * (`STATUS.md`): on the machine those four words are NOT arbitrary — at every real arrival measured they are the same
 * residue of ctlmgr's preceding ev_multi at that depth, the halves of a ROM text address and of a RAM address (`$00fe
 * $a85a $0000 $0002` on the low-resolution machine with two accessories) — and an application that reads words 4..7
 * of WM_TOPPED sees them. A C frame cannot hold another build's code addresses by nature, and none is faked: the C
 * hands this word four times. The differential is green there because the ROM's routine is entered on the harness's
 * zeroed stack; `test_aes_gemctrl.py` holds what the real arrival carries. */
#define HCTL_STALE_WORD       0

/* hctl_window's frame locals whose ADDRESS it hands on, as two host slots that are never live together with a wait
 * between them — and two that are (`host_slot.h`).
 *   THE SIZE: the window's rectangle (w_getsize's answer) and the four words r_get unpacks it into — read into C
 *   locals at once, so nothing of it is live when a gadget's loop waits. */
#define HCTL_SIZE_RECT        0          /* bytes[GRECT_BYTES]                  ($fe45e6 -8(a6))               */
#define HCTL_SIZE_X           8          /* word                                ($fe4614 -18(a6))              */
#define HCTL_SIZE_Y           10         /* word                                ($fe460c -20(a6))              */
#define HCTL_SIZE_W           12         /* word                                ($fe4604 -22(a6))              */
#define HCTL_SIZE_H           14         /* word                                ($fe45fc -24(a6))              */
#define HCTL_SIZE_BYTES       16
/*   THE ELEVATOR'S CORNER ob_offset answers into, for a press on a slider's track. */
#define HCTL_CORNER_X         0          /* word                                ($fe47a0 -30(a6))              */
#define HCTL_CORNER_Y         2          /* word                                ($fe4798 -32(a6))              */
#define HCTL_CORNER_BYTES     4
/*   THE RECTANGLE A DRAG IS HELD BY — gr_dragbox's bound ($fe46a4 -16(a6)), or gr_rubwind's twin offsets ($fe476a
 *   -8(a6)) — and THE TWO WORDS IT ANSWERS INTO (the corner, or the size). Live across every wait of the drag, in
 *   the screen manager's own frame: a slot per process each. */
#define HCTL_DRAG_RECT_BYTES  8          /* GRECT_BYTES                                                        */
#define HCTL_DRAG_FIRST       0          /* word: x, or the width                                              */
#define HCTL_DRAG_SECOND      2          /* word: y, or the height                                             */
#define HCTL_DRAG_ANSWER_BYTES 4

/* ---- hctl_rect ------------------------------------------------------------------------------------------------------ */
/* The desk menu's title: the first one, object 3 of every menu tree ($fe4948 cmpi.w #3,-2(a6)). */
#define HCTL_DESK_TITLE       3
/* mn_do's two answers, in the screen manager's own frame across every wait of the menu: a slot per process. */
#define HCTL_CHOICE_ITEM      0          /* word                                ($fe4930 -4(a6))               */
#define HCTL_CHOICE_TITLE     2          /* word                                ($fe4934 -2(a6))               */
#define HCTL_CHOICE_BYTES     4
/* desk_pid[] (`aes/mnlib.h`'s AES_DESK_PID): a process id a registered accessory, a word each ($fe496a adda.l a0,a0). */
#define HCTL_DESK_PID_BYTES   2

/* ---- ctlmgr `$fe49d2` and ictlmgr `$fe4a6a` (`src/aes/ctlmgr.c`) ----------------------------------------------------
 *   $fe49d2 ctlmgr()        THE SCREEN MANAGER'S PROCESS, entered once by switchto's `rte` (psetup's frame) and never
 *                           left. ONCE: the menu bar's rectangle copied into the active one, the leave word of its
 *                           own mouse wait cleared. THEN, A TURN AFTER A TURN: the top window's owner given the mouse
 *                           and the keys (w_setactive); THE MAIN WAIT — a key, a button, the mouse onto the bar;
 *                           the screen's lock taken; a button handed to hctl_button, the mouse on the bar to
 *                           hctl_rect (both, in that order, where one wake brought both); the lock let go.
 *   $fe4a6a ictlmgr(pid)    no accessory has an entry in the desk menu yet; the process made (pstart) to begin at
 *                           ctlmgr, named SCRENMGR, ctlmgr its load address too. `pid` is read by nobody.
 * ALCYON C both. ctlmgr's frame is its six answer words (`link a6,#-12`) and two saved registers. */
/* The main wait's events ($fe4a12 move.w #7,-(sp)): `aes/evdoor.h`'s EV_MU_KEYBD | EV_MU_BUTTON | EV_MU_M1. A KEY IS
 * WAITED FOR AND THEN IGNORED — bit 0 of the answer is tested by nothing ($fe4a26, $fe4a44: bits 1 and 2): it is
 * eaten, the lock taken and let go round nothing. */
#define CTL_WAIT_EVENTS       7
/* ...its button: ONE click, any button's change counted, the state wanted the left one down alone ($fe49fe move.l
 * #$0001ff01,-(sp): `aes/aes.h`'s BUTTON_PARM_* — clicks 1, mask $ff, state $01). */
#define CTL_WAIT_CLICKS       1
#define CTL_WAIT_BUTTON_MASK  0xff
#define CTL_WAIT_BUTTON_STATE 0x01
/* ...and what it does not wait for: a timer, a message ($fe49fc, $fe4a04 clr.l -(sp)). BOTH mouse rectangles are the
 * screen manager's own MOBLK, gl_ctwait (`aes/evinput.h`'s AES_GL_CTWAIT_LEAVE), though only the first is asked. */
#define CTL_WAIT_NONE         0
/* The answers a handler is handed: the mouse where the event found it, the first two words ($fe4a3c, $fe4a5a move.l
 * -12(a6),-(sp): x the high word, y the low). */
#define CTL_ANSWER_MOUSE_X    0
#define CTL_ANSWER_MOUSE_Y    1
/* A wake by a button or by the bar counts one multi-click wait off — never the last one (`aes/evasync.h`'s
 * AES_GL_BPEND; $fe4a2c, $fe4a4a cmpi.w #1 / ble: a SIGNED compare). */
#define CTL_BPEND_KEPT        1
/* The process's name, the ROM's own string ($fe4a86 move.l #$fef826,-(sp)): "SCRENMGR.LOC", of which pd_nameit keeps
 * the eight characters before the dot. */
#define AES_SCRENMGR_NAME     0xfef826   /* bytes: "SCRENMGR.LOC\0"                                              */

#ifndef __ASSEMBLER__
#ifdef RECREATE_HOST_DIFFERENTIAL
/* OFF TARGET ctlmgr is its two parts, each a call that returns: the once-only part, and ONE TURN of the loop — from
 * the loop's top (`addrs.h`'s AES_ROM_CTLMGR_LOOP) to the next arrival there. The host runs ONE process's C, its
 * caller's (`host_slot.h`, THE AUDIT): each refuses by name an entry made inside the dispatcher — a parked process
 * "resumed" in C from the model's process hook. */
void aes_ctlmgr_begins(uint8_t *image);                                                              /* $fe49d2 */
void aes_ctlmgr_turn(uint8_t *image);                                                                /* $fe49f2 */
#else
/* ON TARGET it is THE ENTRY the screen manager's first frame names: entered by switchto's `rte` on the process's empty
 * stack — no return address, no argument, nothing expected in any register — and never left. */
__attribute__((noreturn)) void aes_rom_ctlmgr(void);                                                 /* $fe49d2 */
#endif
uint32_t aes_ictlmgr(uint8_t *image, int16_t pid);                                                   /* $fe4a6a */

void aes_ct_msgup(uint8_t *image, int16_t message, int16_t owner, int16_t word3, int16_t word4, int16_t word5,
                  int16_t word6, int16_t word7);                                                      /* $fe456a */
void aes_hctl_window(uint8_t *image, int16_t window, int16_t mouse_x, int16_t mouse_y);              /* $fe45a2 */
void aes_hctl_button(uint8_t *image, int16_t mouse_x, int16_t mouse_y);                              /* $fe48ce */
void aes_hctl_rect(uint8_t *image, int16_t mouse_x, int16_t mouse_y);                                /* $fe4908 */
#endif

#endif /* TOS102US_AES_GEMCTRL_H */
