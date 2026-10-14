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
#endif

#endif /* TOS102US_DESK_DESKTOP_H */
