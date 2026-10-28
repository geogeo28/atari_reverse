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

/* ---- BAND 6 WAVE 2: each group adds the offsets and values more than one unit reads inside its own block, by GEM's
 * name where one exists, the ROM's instruction beside each — a name already above is USED, never spelt again ---- */
/* ---- band 6 wave 2, group G1 (units C, F, E) ---- */
/* The copy engine's tallies — dir_op and d_doop count into them, inf_folder (Show Info) reads them, and the desk's
 * other counters read g_size (GEM's g_nfiles, g_ndirs, g_size) */
#define DESK_G_NFILES         7288       /* long: the files counted             ($fdd66e addq.l #1,7288(a3))    */
#define DESK_G_NDIRS          7292       /* long: ...the folders                ($fdd4c2 addq.l #1,7292(a3))    */
#define DESK_G_SIZE           7296       /* long: ...their bytes                ($fdd680 add.l d0,7296(a3))     */
/* g_1text: the text a line of the text view is made in (dr_code's, ob_sfcb's) and the drivers' scratch text */
#define DESK_G_1TEXT          7300       /* bytes                               ($fde7ea addi.l #7300,(sp))     */
/* The deepest folder level a dir_op's walks reached — kept by unit C, read by fun_op (`$fe00a0`) */
#define AES_DESK_OP_DEPTH     0xc674     /* word                                ($fdd92e clr.w $c674)           */
/* ---- end of group G1's wave-2 ---- */
/* ---- band 6 wave 2, group G2 (units H, G, M) ---- */
#define DESK_MKDIR_TREE       8100       /* long: the New Folder dialog's tree  ($fdfece move.l 8100(a0),d7)    */
/* ---- end of group G2's wave-2 ---- */
/* ---- band 6 wave 2, group G3 (units I, J, K, L) ---- */
#define DESK_G_A_CMD          0x1e98     /* long: a_cmd, the launch's command   ($fe0aee move.l 7832(a5),-(sp)) */
#define DESK_G_A_TAIL         0x1f1c     /* long: a_tail, ...and its tail       ($fe0aea move.l 7964(a5),(sp)) */
#define DESK_G_WLASTSEL       0x1fb0     /* word: g_wlastsel, the window last opened or on top ($fe0f30 move.w d6,8112(a4)) */
/* ---- end of group G3's wave-2 ---- */
/* ---- band 6 wave 2, group G4 (units A, B) ---- */
#define DESK_G_XYOBPTS        7428       /* words: g_xyobpts, a drag's icon corners ($fdcdf2 addi.l #7428,(sp)) */
#define DESK_G_AFILE          8208       /* bytes[INF_BUFFER_BYTES]: g_afile, DESKTOP.INF as read or written
                                          *                                     ($fdb652 addi.l #8208,(sp))    */
#define DESK_G_AFSIZE         10256      /* word: g_afsize, its length          ($fdb698 move.w d0,10256(a3))  */
#define DESK_G_BUFFER         10258      /* bytes: gl_buffer, the INF's texts, kept from g_pbuff on ($fdb60a)  */
#define DESK_G_ALIST          12310      /* ANODE[DESK_ANODES]: g_alist, the pool ($fdb622 addi.l #12310,d0)   */
#define ANODE_BYTES           28         /* ($fdb61c muls.w #28,d1)                                             */
#define DESK_ANODES           32         /* NUM_ANODES: the pool's last node's link cleared ($fdb648 clr.l 13178(a3)) */
/* ---- end of group G4's wave-2 ---- */
/* ---- band 6 wave 2's fix pass: values more than one unit spelt, given ONE home ---- */
#define DESK_SEARCH_ALL       0x16       /* hidden, system and folders: the copy engine's, fun_mkdir's and fun_disk's
                                          * searches ($fdd486, $fdffa6, $fe03ac move.w #22,(sp))               */
#define DESK_WAIT_BUSY        1          /* desk_wait's busy bee                  ($fdd2dc move.w #1,(sp))      */
#define DESK_WAIT_DONE        0          /* ...and the arrow again (its every other caller's word 0)            */
/* ---- end of band 6 wave 2's fix pass ---- */
/* ---- BAND 6 WAVE 4: the same rule, a block per group — a name already in this header or `aes/aes.h` is USED ---- */
/* ---- band 6 wave 4, group G1 (unit M) ---- */
/* THE SHOW / PRINT ENGINE's three words (`$fed632` and its parts): where it is in its 4,096-byte buffer — -1 once the
 * viewer has shown the file's end —, whether the last Fread came short, and what that Fread answered. */
#define AES_SHOW_INDEX        0x9556     /* word: the next byte's index         ($fed668 move.w a6,$9556)      */
#define AES_SHOW_AT_EOF       0x9558     /* word: 1 once an Fread came short    ($fed714 move.w #1,$9558)      */
#define AES_SHOW_COUNT        0x955a     /* word: the last Fread's answer       ($fed70a move.w d0,$955a)      */
/* ---- end of group G1's wave-4 ---- */
/* ---- band 6 wave 4, group G2 (unit N) ---- */
/* THE DISK UTILITIES' globals (`desk/deskdisk.h`): what util_open fetches, and the command line sh_cmd hands Format
 * and the copy — kept for util_redraw. */
#define AES_DESK_UTIL_TREE    0xc946     /* long: the utility tree (rsrc_gaddr(R_TREE, 0)) ($fed89e move.l #$c946) */
#define AES_DESK_UTIL_TEDINFOS 0x96fe    /* long: its first TEDINFO (rsrc_gaddr(R_TEDINFO, 0)) ($fed8aa)        */
#define AES_DESK_UTIL_BAR_X   0xc90e     /* word: the write bar's frame's place in the progress box, as fetched */
#define AES_DESK_UTIL_BAR_Y   0xc910     /* word                                ($fed8c0, $fed8ce)             */
#define AES_DESK_UTIL_COMMAND 0xc6e6     /* long: the command line shown        ($fed93c move.l 12(a6),$c6e6)  */
/* ---- end of group G2's wave-4 ---- */
/* ---- BAND 6 W3a, stage 1 (`desk/deskinf.h`, `desk/deskins.h`): the dialogs' trees and the desk's message buffer ---- */
#define DESK_A_RMSG           7684       /* long: a_rmsg, the buffer evnt_multi reads a message into ($fde970 7684(a0)) */
#define DESK_FILE_INFO_TREE   8056       /* long: Show Info's tree for a file    ($fdeb22 move.l 8056(a3),d7)   */
#define DESK_DISK_INFO_TREE   8060       /* long: ...for a disk                  ($fdee08 move.l 8060(a5),d7)   */
#define DESK_FOLDER_INFO_TREE 8064       /* long: ...for a folder                ($fded32 move.l 8064(a3))      */
#define DESK_OPEN_APPL_TREE   8076       /* long: OPEN APPLICATION's parameters  ($fdf098 move.l 8076(a0),d7)   */
#define DESK_INS_DISK_TREE    8080       /* long: Install Disk Drive's           ($fdf12c move.l 8080(a0),d7)   */
#define DESK_INS_APP_TREE     8084       /* long: Install Application's          ($fdf3da move.l 8084(a0),d7)   */
#define DESK_PREFS_TREE       8104       /* long: Set Preferences'               ($fdef20 move.l 8104(a5),d7)   */
/* ---- ...and stage 2's (`desk/desksupp.h`, `desk/desktop.h`): the two info boxes the menus show whole ---- */
#define DESK_ABOUT_TREE       8068       /* long: Desk > Desktop Info's           ($fe1e66 move.l 8068(a0),d5)   */
#define DESK_TRASH_INFO_TREE  8072       /* long: the trash's Show Info          ($fe17c8 move.l 8072(a3),d6)   */
#define DESK_BLITTER_ON       (DESK_PREFERENCES + 4) /* word: the third preference, the Blitter item's check ($fe211e 8122) */
/* ---- ...and stage 3's (`desk/desktop.h`): the message the desk's loop read, which hndl_msg handles ---- */
#define DESK_G_RMSG           7668       /* words[8]: the message itself, a_rmsg's buffer ($fe2356 move.w 7668(a4),d0) */
/* ---- end of band 6 W3a's ---- */
/* ---- BAND 6 W3b's prep (`desk/desktop.h`): the pointer pair deskmain stores beside a_cmd / a_tail, each to the
 * 36-byte buffer below it — GEM's own deskmain names them a_fcb1 / a_fcb2 (an FCB's 36 bytes; the names inferred from
 * GEM's source, the size and the order). READ BY NOTHING: the four instructions below are the only ones of the AES's
 * ROM text that name either offset (read off its whole disassembly) ---- */
#define DESK_G_FCB1           7968       /* bytes[36]: g_fcb1                   ($fe27ba lea 7968(a5),a0)       */
#define DESK_A_FCB1           8004       /* long: a_fcb1, := g_fcb1             ($fe27be move.l a0,8004(a5))    */
#define DESK_G_FCB2           8008       /* bytes[36]: g_fcb2                   ($fe27c2 lea 8008(a5),a0)       */
#define DESK_A_FCB2           8044       /* long: a_fcb2, := g_fcb2             ($fe27c6 move.l a0,8044(a5))    */
/* ---- end of band 6 W3b's prep ---- */

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
