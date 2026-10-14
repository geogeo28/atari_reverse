/* desk/deskglobals.h — THE DESK'S GLOBALS, ONE HOME (band 6 wave 1b's fix pass): every offset into the block the desk
 * allocates at its start (`aes/aes.h` AES_DESK_GLOBALS holds its address; GEM's GLOBES), the ANODE's layout, the
 * object indexes, views and sort keys more than one unit reads, and the small helpers every unit of the desk used to
 * spell for itself. ONE NAME PER OFFSET — GEM's where the published desktop names the field (`g_*`, `ml_*`); the ROM's
 * own instruction that reads or writes it beside each. A unit's header includes this one; no unit defines an offset of
 * the block again.
 *
 * (Wave 1b's four groups named the same fields apart — g_wicon three ways, the screen's objects three — and two
 * headers once gave one name two facts; the reviewers' finding A-5 / B-9 is why this file exists.)
 */
#ifndef TOS102US_DESK_DESKGLOBALS_H
#define TOS102US_DESK_DESKGLOBALS_H

/* ---- the block, by offset ------------------------------------------------------------------------------------------ */
#define DESK_FILES_FREE       0          /* long: g_favail                      ($fdf708 move.l a4,(a5))       */
#define DESK_PATH_POOL        4          /* PNODEs[PATH_NODES]: g_plist         ($fdf744 lea 4(a5),a0)         */
#define DESK_PATHS_FREE       704        /* long: g_pavail — where a sixth pool node would lie ($fdf748)       */
#define DESK_PATHS_OPEN       708        /* long: g_phead                       ($fdf74c clr.l 708(a5))        */
#define DESK_PATH_BUFFER      712        /* bytes: a buffer fpd_start points DESK_PATH_BUFFER_POINTER at (# ctx) */
#define DESK_PATH_BUFFER_POINTER 834     /* long                                ($fdf770 move.l a0,834(a5))    */
#define DESK_DTA              838        /* bytes: the DTA the directory read searches with ($fdf764)          */
#define DESK_DTA_POINTER      966        /* long: ...and its address, dos_sdta's ($fdfc8a move.l 966(a0),(sp))  */
#define DESK_G_WINDOWS_OPEN   0x03ca     /* word: how many WNODEs are taken     ($fe2bb0 cmpi.w #4,970(a3))     */
#define DESK_G_ICONS          0x03cc     /* ICONBLK[]: g_icons, one an icon object ($fdbfda addi.l #972,d0; $fe3114) */
#define DESK_G_INDEX          0x14cc     /* words: g_index, the ICONBLK each object shows, by number
                                          *                                     ($fdbfca move.w 18(a5),5324(a0)) */
#define DESK_G_USERBLKS       0x15cc     /* USERBLK[], one an object            ($fe3076 addi.l #5580,d0)      */
#define DESK_G_NUM            0x19cc     /* word: g_num, the view's item count  ($fe2ae2 move.w ...,6604(a5))  */
#define DESK_G_PXY            0x19ce     /* long: g_pxy, the view's item points ($fe2aec move.l a0,6606(a5))   */
#define DESK_G_IVIEW          0x19d2     /* word: g_iview, the windows' view    ($fe2a8a; $fdc8d4 move.w 6610(a0)) */
#define DESK_G_IWEXT          0x19d4     /* word: an item's width               ($fe2ab4)                      */
#define DESK_G_IHEXT          0x19d6     /* word: ...its height                 ($fe2ab8)                      */
#define DESK_G_IWSPC          0x19d8     /* word: the space beside an item      ($fe2ad8)                      */
#define DESK_G_IHSPC          0x19da     /* word: ...under it                   ($fe2adc)                      */
#define DESK_G_IWINT          0x19dc     /* word: the pitch across              ($fe2b3c)                      */
#define DESK_G_IHINT          0x19de     /* word: ...and down                   ($fe2b48)                      */
#define DESK_G_INCOL          0x19e0     /* word: the columns across the desk   ($fe2b56)                      */
#define DESK_G_ISORT          0x19e2     /* word: g_isort, the windows' sort    ($fe2a90; $fdfb2a move.w 6626(a0)) */
#define DESK_G_TMPPTH         0x19e4     /* bytes: g_tmppth, a path the desk builds — app_getfh's name, par_chk's
                                          * copy of the source                  ($fdb1e2 addi.l #6628; $fdd81c) */
#define DESK_PAR_DESTINATION  6756       /* bytes: par_chk's copy of the destination ($fdd826 adda.l #6756)     */
#define DESK_G_DESK_RECT      0x1e08     /* bytes[GRECT_BYTES]: the desk's work area, wind_create's ($fe2c36)   */
#define DESK_AREA_Y           7690       /* word: g_ydesk, DESK_G_DESK_RECT's y ($fdb588 move.w 7690(a3),d0)   */
#define DESK_AREA_H           7694       /* word: g_hdesk, ...and its height    ($fdb5ca move.w 7694(a3),(sp)) */
#define DESK_G_FULL_W         0x1e14     /* word: the width the columns divide  ($fe2b4c move.w 7700(a5),d0)    */
#define DESK_G_CMD            0x1e18     /* bytes: g_cmd                        ($fe0a8c addi.l #7704,(sp))     */
#define DESK_G_TAIL           0x1e9c     /* byte: g_tail[0], the tail's count   ($fe0aae move.b d0,7836(a5))    */
#define DESK_G_TAIL_TEXT      0x1e9d     /* bytes: g_tail[1..]                  ($fe0a9c addi.l #7837,(sp))     */
#define DESK_G_ALERT          0x1f70     /* long: a_alert, an alert's text: rs_gaddr's free string, or what merge_str
                                          * made of it                          ($fdfd6e, $fe3816 addi.l #8048) */
#define DESK_MENU_TREE        8052       /* long: the desk's menu                ($fe1f92 move.l 8052(a5),-(sp)) */
#define DESK_COPY_DIALOG_TREE 8088       /* long: the copy / delete dialog's tree ($fdcf88 move.l 8088(a5))     */
#define DESK_NAMECON_TREE     8096       /* long: the name-conflict dialog's tree ($fdcf5c move.l 8096(a5))     */
#define DESK_SELECTION_ROOT   8108       /* word: the root whose children are selected ($fe1d92 move.w 8108(a0)) */
#define DESK_SELECTION_WINDOW 8110       /* word: ...its window's handle          ($fe1d00 move.w 8110(a0))     */
#define DESK_VIEW_ITEM        8114       /* word: the View menu's checked view item ($fe1f8e move.w 8114(a5))   */
#define DESK_SORT_ITEM        8116       /* word: ...and checked sort item       ($fe1fb4 move.w 8116(a5))      */
#define DESK_PREFERENCES      8118       /* words[3]: the preferences the INF keeps ($fe255c move.w 8118(a3))   */
#define DESK_GRID_W           8124       /* word: g_icw, the icons' grid across  ($fdb51e move.w 8124(a3),d5)  */
#define DESK_GRID_H           8126       /* word: g_ich, ...and down             ($fdb590 move.w 8126(a3),d4)  */
#define DESK_G_NMICON         0x1fc0     /* word: the icon view's item count    ($fe2b18)                      */
#define DESK_G_NMTEXT         0x1fc2     /* word: the text view's               ($fe2ae2)                      */
#define DESK_G_XYICON         0x1fc4     /* bytes: the icon view's item points  ($fe2b1e lea 8132(a5))         */
#define DESK_G_XYTEXT         0x1fe8     /* bytes: the text view's              ($fe2ae8 lea 8168(a5))         */
#define DESK_G_WICON          0x200c     /* word: g_wicon, an icon object's width ($fdbf5c, $fdc34c move.w 8204) */
#define DESK_G_HICON          0x200e     /* word: g_hicon, ...and its height — g_wicon's longword's low word
                                          *                                     ($fdbf58, $fdc348 move.w 8206) */
#define DESK_STRING_CURSOR    12306      /* long: g_pbuff, where the next INF text is kept ($fdb034 move.l 12306(a3)) */
#define DESK_ANODES_FREE      13206      /* long: g_aavail                      ($fdaea8 movea.l 13206(a3),a5)  */
#define DESK_ANODES_IN_USE    13210      /* long: g_ahead                       ($fdaeb8 tst.l 13210(a3))       */
#define DESK_G_IBLIST         13214      /* ICONBLK[]: g_iblist, the ROM's ICONBLKs ($fdb236 addi.l #13214,(sp); $fdc998) */
#define DESK_MASK_ICONBLKS    13418      /* ICONBLK[]: ...their copy, pointing at the masks — the template of each
                                          * icon an object is made from         ($fdb24e, $fe3148 addi.l #13418) */
#define DESK_IMAGE_KINDS      13622      /* words: per image index, a mask's place in the mask block, else -1
                                          *                                     ($fdb312 move.w #1,13622(a0)) */
#define DESK_CNX_SORT         13646      /* word: the INF's sort, kept               ($fe2558 move.w d0,13646(a3))  */
#define DESK_CNX_VIEW         13648      /* word: ...its view                    ($fe254c move.w d0,13648(a3))  */
#define DESK_CNX_PREFERENCES  13650      /* words[3]                             ($fe255c move.w ..,13650(a3))  */
#define DESK_CNX_RESOLUTION   13656      /* word: the resolution, from 0         ($fe2576 move.w d0,13656(a3))  */
#define DESK_G_WINDOW_SAVES   0x355a     /* g_cnxsave: the window positions the INF keeps ($fe2bca adda.l #13658,a4) */
#define DESK_ICON_IMAGES      14202      /* long: the block of the icons' images         ($fdb2e2 move.l d0,14202(a5)) */
#define DESK_ICON_MASKS       14206      /* long: ...and of their masks                  ($fdb38a move.l d0,14206(a5)) */
#define DESK_G_SCREEN         0x3782     /* long: g_screen, the POINTER to the screen's tree ($fe0788 move.l a0,14210(a5)) */
#define DESK_COPY_DIALOG_UP   14230      /* word: ml_dlpr, the copy dialog is up ($fdcf7a tst.w 14230(a5))      */
#define DESK_NAMECON_UP       14232      /* word: ml_havebox, the name-conflict dialog is up ($fdcf56)          */
#define DESK_FNAME_TEXT       14273      /* bytes: ml_ftmp, get_fname's name    ($fdd184 addi.l #14273,(sp))   */
#define DESK_G_LONG_STRING    0x37ce     /* bytes: g_lngstr, ini_str's buffer   ($fe0ba4 addi.l #14286,(sp))    */
#define DESK_FILE_INDEX       14302      /* longs: ml_pfndx, the sort's files by place ($fdfb64 14302(a0))     */
#define DESK_G_SCREEN_OBJECTS 0x3e1e     /* OBJECT[DESK_SCREEN_OBJECTS]: the screen's tree ITSELF, inline in the
                                          * block — what g_screen points at     ($fe0784 lea 15902(a5),a0)      */

/* ---- the screen's tree: the objects every unit names ------------------------------------------------------------- */
#define DESKTOP_ROOT          1          /* the desktop object under the screen's root ($fdbf08, $fe0cc4, $fdc8c2) */

/* ---- an ANODE: one INF line's icon, on the lists DESK_ANODES_FREE / DESK_ANODES_IN_USE ------------------------------ */
#define ANODE_NEXT            0          /* long: a_next                        ($fdaeb0 move.l (a5),13206(a3)) */
#define ANODE_FLAGS           4          /* word: a_flags — AF_ISDESK its bit 2 ($fdb09e move.w #7,4(a4); $fdc0be) */
#define ANODE_FLAG_ISDESK_BIT 2          /* ...tested in the word's low byte    ($fdc0be btst #2,5(a3))         */
#define ANODE_ON_THE_DESKTOP  0x0004     /* ...and as a mask: AF_ISDESK, its spot in the INF line ($fdb106)      */
#define ANODE_TYPE            6          /* word: a_type                        ($fdb098 move.w #3,6(a4))      */
#define ANODE_OBID            8          /* word: a_obid, its desktop icon object ($fdbf92 move.w d7,8(a5))     */
#define ANODE_PAPPL           10         /* long: a_pappl, the application's name pattern ($fdb164; $fdc0dc)   */
#define ANODE_PDATA           14         /* long: a_pdata, its data files' pattern ($fdb174; $fdc0c8)          */
#define ANODE_AICON           18         /* word: a_aicon, an application's icon ($fdb130; $fe30e6)            */
#define ANODE_DICON           20         /* word: a_dicon, a document's         ($fdb140; $fe30f4)             */
#define ANODE_LETTER          22         /* word: a_letter, the drive's         ($fdb15c move.w d0,22(a4))     */
#define ANODE_XSPOT           24         /* word: a_xspot, where it lies on the desktop ($fdb110; $fdc32c)     */
#define ANODE_YSPOT           26         /* word: a_yspot                       ($fdb120; $fdc33c)             */
#define ANODE_NONE            0          /* no node: a list's end, app_afind's miss ($fdc0f6 clr.l d0)          */
/* a_type, GEM's AT_* (app_parse stores them; app_afind's and i_find's searches ask for them) */
#define AT_ISFILE             0          /* a program, or a file's node         ($fdb0c2 clr.w 6(a4); $fe2f58) */
#define AT_ISFOLD             1          /*                                     ($fdb0e4 move.w #1,6(a4))      */
#define AT_ISDISK             2          /*                                     ($fdb0a6 move.w #2,6(a4))      */
#define AT_ISTRSH             3          /*                                     ($fdb098 move.w #3,6(a4))      */
#define AT_ISCART             4          /*                                     ($fdb0b4 move.w #4,6(a4))      */

/* ---- what more than one unit reads --------------------------------------------------------------------------------- */
#define ICONBLK_BYTES         34         /* an ICONBLK                          ($fdb26e, $fe310e muls.w #34)  */
#define DRIVE_LETTER_FIRST    'A'        /* a drive's number is its letter less this ($fdbf80, $fe09f8, $fdf836) */
#define V_ICON                0          /* g_iview's two views                 ($fe2b28 tst.w d0; $fdc9d0)    */
#define V_TEXT                1          /*                                     ($fe2b2c cmp.w #1,d0; $fdc9d6) */
#define SORT_BY_NAME          0          /* g_isort, pn_fcomp's keys ($fdfad4 tst.w d0 / $fdfad8 #1 / $fdfade #2 / $fdfae6 #3) */
#define SORT_BY_DATE          1
#define SORT_BY_SIZE          2
#define SORT_BY_TYPE          3

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/objects.h"

/* The block's address, as every routine of the desk reloads it from AES_DESK_GLOBALS. */
static inline uint32_t desk_globals(const uint8_t *image)
{
    return be32(image + AES_DESK_GLOBALS);
}

/* The screen's objects, as the ROM indexes them: off the desk's globals, not through g_screen. */
static inline uint32_t screen_objects(const uint8_t *image)
{
    return desk_globals(image) + DESK_G_SCREEN_OBJECTS;
}

/* A word of the GRECT at `rect`, read over the 68000's 24-bit bus. */
static inline int16_t rect_word(const uint8_t *image, uint32_t rect, uint32_t field)
{
    return (int16_t)bus_word(image, rect + field);
}

/* A GRECT laid at `rect` (a frame of the routine's own, or a host slot). */
static inline void lay_rect(uint8_t *image, uint32_t rect, int16_t x, int16_t y, int16_t w, int16_t h)
{
    wr16(image + rect + GRECT_X, (uint16_t)x);
    wr16(image + rect + GRECT_Y, (uint16_t)y);
    wr16(image + rect + GRECT_W, (uint16_t)w);
    wr16(image + rect + GRECT_H, (uint16_t)h);
}
#endif

#endif /* TOS102US_DESK_DESKGLOBALS_H */
