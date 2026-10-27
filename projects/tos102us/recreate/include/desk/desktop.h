/* desk/desktop.h — UNIT K, THE DESK'S MAIN LOOP'S HELPERS (`src/desk/desktop.c`; band 6 wave 1b, group G2): the menus
 * kept in step with the selection and the view, the item under a click found, the windows' state kept for the INF.
 *
 *   $fe1bf6 i_find(window, item, &fnode, &is_app)  the ANODE of a desktop icon (window 0) or of a window's file:
 *                                            app_afind by its object and name, or by the window's FNODE's name and
 *                                            whether it is a folder; the FNODE (0 on the desktop) stored
 *   $fe1c8c men_list(tree, items, enable)    menu_ienable of each item of a NUL-ended BYTE list — each a signed
 *                                            byte, so an item of $80 or more asks the bar redrawn (its word's top bit)
 *   $fe1cb6 men_update(tree)                 the menu's items enabled, then those no selection allows disabled,
 *                                            item list by item list: by each selected icon's ANODE type, by whether a
 *                                            window is on top (and its name the root's), by how many are selected
 *   $fe1f2a do_viewmenu(item)                a View item: the view (icons / text) or the sort; where either changed,
 *                                            its check moved and the windows made again (win_view); 0
 *   $fe2536 cnx_put()                        the INF's view, sort, preferences and resolution, and the four windows'
 *                                            rectangles, scroll, icon and path kept in g_cnxsave
 *
 * ALCYON C, each a `link` and a Line-F return; every menu change through unit D's binding, which yields.
 * men_list, men_update and cnx_put answer nothing in C: the word the ROM leaves is a COUNTED divergence
 * (`test/test_desk_top.py`), read by no caller.
 *
 * NAMES: the published GEM desktop's DESKTOP / DESKMAIN where the body is its routine.
 *
 * BAND 6 WAVE 2 (group G3), each read from its body (names `# ctx`):
 *   $fe22a6 hndl_kbd(key)                    Esc ($011b): the window on top re-read (fun_rebld); 0
 *   $fe2618 cnx_get()                        the INF's view and sort through the View menu's handler, its preferences,
 *                                            the double-click rate, the resolution word; each window kept (a path)
 *                                            opened again: a window for its icon, its scroll, its spec parsed, its
 *                                            corner on do_xyfix's column (IN g_cnxsave), its drive and path made
 *                                            current — then do_diropen, or the window freed where that failed; then
 *                                            cnx_put
 */
#ifndef TOS102US_DESK_DESKTOP_H
#define TOS102US_DESK_DESKTOP_H

#include "desk/deskglobals.h"

/* ---- the desk's global block: `desk/deskglobals.h` (the menu, the selection, the View items checked, the preferences,
 * g_cnxsave's fields) --------------------------------------------------------------------------------------------------- */
#define PREFERENCE_WORDS      3
/* ---- the View menu's items: the view's first, then the sort's ------------------------------------------------------- */
#define VIEW_ITEM_ICONS       29         /* ($fe1f62 sub.w #29,d0: the table $fef6c4's first row)                */
#define VIEW_ITEM_TEXT        30
#define SORT_ITEM_NAME        32         /* ($fe2554 add.w #-32,d0)                                              */
#define SORT_ITEM_DATE        33
#define SORT_ITEM_SIZE        34
#define SORT_ITEM_TYPE        35
/* (...and the sort keys the items set, SORT_BY_*: `desk/deskglobals.h`) */
#define VIEWMENU_DONE         0          /* ($fe1f3c clr.w d6, $fe1fda move.w d6,d0)                             */
/* ---- a window's g_cnxsave entry (`desk/deskview.h`: DESK_G_WINDOW_SAVES, WINDOW_SAVE_BYTES) -------------------------- */
#define SAVE_X                0          /* words[4]: wind_get's WF_CXYWH answers ($fe25a0..$fe25ac)              */
#define SAVE_Y                2
#define SAVE_W                4
#define SAVE_H                6
#define SAVE_CVCOL            8          /* word: the WNODE's first column      ($fe25c8 move.w 12(a4),8(a5))    */
#define SAVE_CVROW            10         /*                                     ($fe25ce move.w 14(a4),10(a5))   */
#define SAVE_OBID             12         /* word: its icon; 0 for none          ($fe25d4 move.w 8(a4),12(a5))    */
#define SAVE_PATH             14         /* bytes: its path; empty for none     ($fe25dc addi.l #14,(sp))        */
#define WF_CXYWH              5          /* wind_get's current rectangle       ($fe25ae move.w #5,-(sp))        */
/* ---- men_update's item lists: the ROM's NUL-ended byte tables -------------------------------------------------------- */
#define MENU_FIRST_ITEM       18         /* ($fe1cc2 moveq #18,d6)                                               */
#define MENU_LAST_ITEM        40         /* ($fe1cd4 cmp.w #40,d6: ble)                                          */
#define AES_MEN_NEVER         0xfef64a   /* the separators: never enabled                                         */
#define AES_MEN_HARD_DISK     0xfef646   /* a selected disk past 'B'                                              */
#define AES_MEN_APPLICATION   0xfef650   /* a selected program                                                    */
#define AES_MEN_DOCUMENT      0xfef654   /* a selected file that is none                                          */
#define AES_MEN_FOLDER        0xfef658
#define AES_MEN_FLOPPY        0xfef65e   /* a selected disk A: or B:                                              */
#define AES_MEN_TRASH         0xfef662
#define AES_MEN_NONE_SELECTED 0xfef66a
#define AES_MEN_NO_WINDOW     0xfef670
#define AES_MEN_A_WINDOW      0xfef674   /* ...enabled where a window is on top                                   */
#define AES_MEN_MANY_SELECTED 0xfef67e
#define AES_MEN_CARTRIDGE     0xfef684
#define AES_MEN_CLOSE         0xfef68a   /* the File menu's Close: disabled where the top window's name is $9888's */
#define AES_DESK_ROOT_NAME    0x9888     /* bytes: a window's name that has no parent to close to (empty at every
                                          * arrival)                                 ($fe1dee move.l #$9888,(sp)) */
/* men_list's enable, menu_ienable's flag — not `aes/gemsuper.h`'s MENU_DISABLED, the object state bit it sets */
#define MENU_ITEM_DISABLED    0
#define MENU_ITEM_ENABLED     1
/* i_find's app_afind arguments */
#define DESKTOP_WINDOW        0          /* i_find's window: the desktop         ($fe1c0e tst.w d7)              */
#define AFIND_ON_THE_DESKTOP  1          /* ($fe1c22 move.l #$0001ffff: 1, then -1)                              */
#define AFIND_IN_A_WINDOW     0          /* ($fe1c76 clr.w -(sp))                                                */
#define AFIND_ANY             (-1)       /* any type / any object                                                */
/* men_update's frame: i_find's two answers, handed on BY ADDRESS ($fe1cf0 -2(a6) is_app, $fe1cf6 -6(a6) fnode). */
#define FIND_FNODE            0          /* long                                                                 */
#define FIND_IS_APP           4          /* word                                                                 */
#define FIND_FRAME_BYTES      6
/* ---- band 6 wave 2 ---------------------------------------------------------------------------------------------- */
/* hndl_kbd's key: Esc's scan and ASCII, aes/obedit.h's OB_EDIT_KEY_ESCAPE ($fe22ae cmpi.w #283,8(a6)) */
#define HNDL_KBD_DONE         0          /* ($fe22aa clr.w -2(a6))                                               */
#define CNX_DCLICK_RATE       3          /* evnt_dclick's rate, set              ($fe2650 move.w #3,-(sp))       */
#define CNX_DCLICK_SET        1          /* ($fe264c move.w #1,(sp))                                             */
#define CNX_RESOLUTION_BASE   1          /* the INF's resolution word is from 0, the word set from 1 ($fe265c addq.w #1) */
#define CNX_NEW_WINDOW        1          /* do_diropen's `new`                   ($fe270c move.w #1,-(sp))       */
/* CNX_GET'S FRAME — fpd_parse's extension, name and drive word, the ROM's layout (-14(a6) up: the name's eight bytes
 * run into the drive word's high byte where it has eight characters), HELD across do_diropen (the name and extension
 * are its). */
#define CNX_GET_FRAME_EXT     0          /* bytes[4]                             ($fe269c -14(a6))               */
#define CNX_GET_FRAME_NAME    4          /* bytes[8]                             ($fe26a4 -10(a6))               */
#define CNX_GET_FRAME_DRIVE   12         /* word                                 ($fe26b4 -2(a6))                */
#define CNX_GET_FRAME_BYTES   14

/* ==== BAND 6 W3a, STAGE 2: TWO MENUS' HANDLERS — do_optnmenu, do_deskmenu (`src/desk/desktop.c`), COMPILED FOR THE
 * TARGET ALONE (the user's R3, ruling O1: no host twin) ==============================================================
 *   $fe1fde do_optnmenu(item)                the Options menu: the selection's root's box read (get_xywh) and its
 *                                            first selected icon's ANODE (win_isel, i_find); 37 Install Disk Drive
 *                                            (ins_disk; changed: the desktop rebuilt and redrawn), 38 Install
 *                                            Application (ins_app of a program; changed: the windows rebuilt and shown),
 *                                            40 Set Preferences (inf_pref, its answer the handler's), 41 Save Desktop
 *                                            and 42 Print Screen (each asked by an alert first), 44 the Blitter
 *                                            (Blitmode, the check moved); 39 and 43 nothing. inf_pref's answer, else 0
 *   $fe1e4c do_deskmenu(item)                Desk > Desktop Info (item 9): the info box shown, its exit object's
 *                                            state cleared. 0, always */
#define OPTN_INSTALL_DISK     37         /* the table $fef6e0's first row       ($fe2156 subw #37,d0)           */
#define OPTN_INSTALL_APP      38
#define OPTN_PREFERENCES      40
#define OPTN_SAVE_DESKTOP     41
#define OPTN_PRINT_SCREEN     42
#define OPTN_BLITTER          44         /* ...and menu_icheck's item           ($fe2148 move.w #44,-(sp))      */
#define MENU_NOTHING_DONE     0          /* do_optnmenu's and do_deskmenu's answer where no arm sets one
                                          *                                     ($fe1fec clr.w d7, $fe1e58 clr.w d6) */
#define OPTN_ALERT_DEFAULT    1          /* form_alert's default button         ($fe20d8 move.w #1,-(sp))       */
#define OPTN_ALERT_OK         1          /* ...the button that goes on          ($fe20e0 cmpw #1,d0)            */
#define AES_SAVE_DESKTOP_ALERT 0xfef56a  /* "[1][ |Save desktop ?][ OK |Cancel]" ($fe20d2 move.l #$fef56a,(sp)) */
#define AES_PRINT_SCREEN_ALERT 0xfef58e  /* "[1][ |Print screen display ?][ OK |Cancel]" ($fe20fc)               */
#define APP_SAVE_TO_DISK      1          /* app_save's word                     ($fe20ee move.w #1,(sp))        */
#define XBIOS_BLITMODE_FN     64         /* Blitmode                            ($fe212c move.w #64,-(sp))      */
#define AES_OPTNMENU_BLITMODE_RETURN 0xfe2132 /* trp14's parked return: the word after its Line-F call          */
#define DESKTOP_WORK_WINDOW   0          /* wind_get's and do_wredraw's window: the desktop ($fe2074 clr.w -(sp)) */
/* do_optnmenu's frame: get_xywh's (later wind_get's) box from -8(a6) up — h, w, y, x —, i_find's two answers below it
 * (`FIND_*`: -12(a6) the FNODE, -14(a6) is-a-program) */
#define OPTN_BOX_X            0          /* ($fe1ffe -2(a6))                                                     */
#define OPTN_BOX_Y            2          /* ($fe1ffa -4(a6))                                                     */
#define OPTN_BOX_W            4          /* ($fe1ff6 -6(a6))                                                     */
#define OPTN_BOX_H            6          /* ($fe1ff2 -8(a6))                                                     */
#define OPTN_BOX_BYTES        8
#define DESK_INFO_ITEM        9          /* Desk > Desktop Info                 ($fe1e5a cmpw #9,d7)            */
#define ABOUT_OK              11         /* the info box's exit object          ($fe1e74 adda.l #274: 11's state) */

/* ==== BAND 6 W3a, STAGE 3: THE DESK'S THREE DISPATCHERS AND THE FILE MENU — hndl_msg, hndl_menu, do_filemenu,
 * hndl_button (`src/desk/desktop.c`), COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1: no host twin) ===========
 *   $fe2344 hndl_msg()                       the message the desk's loop read (DESK_G_RMSG): a window's message clears
 *                                            the selection first; MN_SELECTED the menu's (hndl_menu, the last window
 *                                            verified first), its answer the handler's; WM_REDRAW, TOPPED, CLOSED (File >
 *                                            Close's arm), FULLED, ARROWED, H/VSLID, SIZED, MOVED each its window's act;
 *                                            the INF's windows kept (cnx_put) after a close, a full, a size or a move;
 *                                            the message emptied, the menu brought up to date. MN_SELECTED's answer, else 0
 *   $fe22ce hndl_menu(title, item)           the title's handler (Desk, File, View — the windows sorted, rebuilt and shown
 *                                            again under the busy bee —, Options), then the title shown normal. Its answer
 *   $fe1e80 do_filemenu(item)                File: Open / Show Info / Format of the first icon selected, New Folder in the
 *                                            window on top (the selection cleared), Close / Close Window of it. The
 *                                            opener's, the shower's or Format's answer, else 0
 *   $fe2172 hndl_button(clicks, x, y, button, keys)  a click: its window found (the selection cleared where another,
 *                                            the window verified, kept as the last); one click selects (act_bsclick) and,
 *                                            the button still down (graf_mkstate INTO ITS OWN ARGUMENT `button` — the
 *                                            thunk's copy: deskmain pops the ROM's unread), drags what act_bdown answers
 *                                            (fun_drag); two open (act_bsclick, then do_filemenu's Open). The menu brought
 *                                            up to date. fun_drag's or the opener's answer, else 0 */
/* the message's words (DESK_G_RMSG): its type, then its window (or a menu's title) and four more */
#define RMSG_TYPE             0          /* msg[0]                              ($fe2356 7668(a4))              */
#define RMSG_HANDLE           6          /* msg[3]: the window, or MN_SELECTED's title ($fe2390 7674(a4))       */
#define RMSG_TITLE            RMSG_HANDLE
#define RMSG_X                8          /* msg[4]: MN_SELECTED's item, an arrow, a slider's place ($fe2458 7676) */
#define RMSG_ITEM             RMSG_X
#define RMSG_Y                10         /* msg[5]                              ($fe245e 7678(a4))              */
#define RMSG_W                12         /* msg[6]                              ($fe2470 7680(a4))              */
#define RMSG_H                14         /* msg[7]                              ($fe2476 7682(a4))              */
#define HNDL_MSG_NOTHING_DONE 0          /* ($fe2354 move.w d4,d7: 0)                                           */
#define REDRAW_NO_WINDOW      0          /* WM_REDRAW of window 0: nothing      ($fe239c tst.w 7674(a4))        */
#define DESK_VERIFY_UNCHANGED 0          /* desk_verify's `changed`: MN_SELECTED's, a top's, a click's ($fe2384, $fe23f6, $fe219e clr.w (sp)) */
/* win_slide's `vertical`: the H and V sliders' messages */
#define SLIDE_HORIZONTAL      0          /* ($fe243a clr.w (sp))                                                */
#define SLIDE_VERTICAL        1          /* ($fe2448 move.w #1,(sp))                                            */
#define TOPPED_ZERO           0          /* wind_set WF_TOP's four words        ($fe23b6 clr.l, clr.l)          */
/* hndl_menu's titles: the menu bar's */
#define MENU_TITLE_DESK       3          /* ($fe231a cmpw #3,d0)                                                */
#define MENU_TITLE_FILE       4
#define MENU_TITLE_VIEW       5
#define MENU_TITLE_OPTIONS    6
#define MENU_TITLE_NORMAL     1          /* menu_tnormal's `normal`             ($fe2332 move.w #1,(sp))        */
/* do_filemenu's items: the table $fef6a0's rows (20, 24 and 26 do nothing) */
#define FILE_ITEM_OPEN        18         /* ($fe1f0e subw #18,d0)                                               */
#define FILE_ITEM_SHOW_INFO   19
#define FILE_ITEM_NEW_FOLDER  21
#define FILE_ITEM_CLOSE       22         /* ...and WM_CLOSED's                  ($fe240a move.w #22,(sp))       */
#define FILE_ITEM_CLOSE_WINDOW 23
#define FILE_ITEM_FORMAT      25
#define FUN_CLOSE_A_FOLDER    0          /* fun_close's `close_it`: up one folder ($fe1ee0 clr.w (sp))          */
#define FUN_CLOSE_THE_WINDOW  1          /* ...the window whole                 ($fe1ef4 move.w #1,(sp))        */
#define FILEMENU_NOTHING_DONE 0          /* ($fe1e8e clr.w d7)                                                  */
/* hndl_button */
#define BUTTON_ONE_CLICK      1          /* ($fe21c6 cmpi.w #1,8(a6))                                           */
#define BSCLICK_ONE           0          /* act_bsclick's `double_click`        ($fe21d0 clr.w (sp))            */
#define BSCLICK_TWO           1          /* ($fe2268 move.w #1,(sp))                                            */
#define BUTTON_LEFT_DOWN      0x0001     /* graf_mkstate's button word, bit 0  ($fe220c btst #0,15(a6))        */
#define BDOWN_NOTHING_DRAGGED (-1)       /* act_bdown's answer                  ($fe223c cmpw #-1,d4)           */
#define BUTTON_NOTHING_DONE   0          /* ($fe2184 clr.w -2(a6))                                              */

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t aes_i_find(uint8_t *image, int16_t window, int16_t item, uint32_t fnode_out, uint32_t is_app_out); /* $fe1bf6 */
void aes_men_update(uint8_t *image, uint32_t tree);                                              /* $fe1cb6 */
int16_t aes_do_viewmenu(uint8_t *image, int16_t item);                                           /* $fe1f2a */
void aes_cnx_put(uint8_t *image);                                                                /* $fe2536 */
void aes_men_list(uint8_t *image, uint32_t tree, uint32_t items, int16_t enable);                /* $fe1c8c */
/* band 6 wave 2 (group G3) */
int16_t aes_hndl_kbd(uint8_t *image, int16_t key);                                               /* $fe22a6 */
void aes_cnx_get(uint8_t *image);                                                                /* $fe2618 */
#ifndef RECREATE_HOST_DIFFERENTIAL
/* band 6 W3a, stage 2: target-only */
int16_t aes_do_optnmenu(uint8_t *image, int16_t item);                                           /* $fe1fde */
int16_t aes_do_deskmenu(uint8_t *image, int16_t item);                                           /* $fe1e4c */
/* band 6 W3a, stage 3: target-only */
int16_t aes_hndl_msg(uint8_t *image);                                                            /* $fe2344 */
int16_t aes_hndl_menu(uint8_t *image, int16_t title, int16_t item);                              /* $fe22ce */
int16_t aes_do_filemenu(uint8_t *image, int16_t item);                                           /* $fe1e80 */
int16_t aes_hndl_button(uint8_t *image, int16_t clicks, int16_t x, int16_t y, int16_t button, int16_t keys); /* $fe2172 */
#endif
#endif

#endif /* TOS102US_DESK_DESKTOP_H */
