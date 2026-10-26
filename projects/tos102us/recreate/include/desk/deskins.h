/* desk/deskins.h — THE DESK'S TWO INSTALL DIALOGS (`src/desk/deskins.c`, band 6 W3a's stage 1): ins_disk `$fdf11a`
 * (Options > Install Disk Drive) and ins_app `$fdf3c8` (Options > Install Application) — the ANODE an icon or a
 * program is, edited, made anew or freed. COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1: no host twin).
 *
 * NAMES: the published GEM desktop's (DESKINS), read from their bodies; the file is GEM's split of them from DESKINF.
 */
#ifndef TOS102US_DESK_DESKINS_H
#define TOS102US_DESK_DESKINS_H

/* Each answers whether it changed an ANODE (the desk then saves and redraws) */
#define INS_UNCHANGED         0          /* ($fdf130 clr.w -2(a6); $fdf4c2 clr.w -56(a6))                       */
#define INS_CHANGED           1          /* ($fdf2f8 move.w #1,-2(a6); $fdf698 move.w #1,-56(a6))               */

/* ins_disk's dialog (the desk's install-disk tree) */
#define INS_DISK_LETTER       2          /* ($fdf158 move.w #2,-(sp))                                           */
#define INS_DISK_LABEL        3          /* ($fdf16a move.w #3,-(sp))                                           */
#define INS_DISK_FLOPPY       6          /* the icon chosen: its state's SELECTED bit ($fdf1a0 154 = 6 * 24 + 10) */
#define INS_DISK_INSTALL      8          /* ($fdf1e0 203 = 8 * 24 + 11)                                         */
#define INS_DISK_REMOVE       9          /* ($fdf34c 227)                                                       */
#define INS_DISK_CANCEL       10         /* ($fdf3ac 251)                                                       */
/* ...and its frame from -34(a6), the frame's own layout: the label and the letter as the dialog left them, then as the
 * ANODE had them */
#define INS_DISK_NEW_LABEL    0          /* bytes: fs_sget's                    ($fdf18e addi.l #-34,(sp))      */
#define INS_DISK_NEW_LETTER   14         /* bytes: fs_sget's                    ($fdf17c addi.l #-20,(sp))      */
#define INS_DISK_OLD_LABEL    16         /* bytes: a_pappl's copy               ($fdf144 addi.l #-18,(sp))      */
#define INS_DISK_OLD_LETTER   30         /* bytes[2]: a_letter's low byte, a NUL ($fdf13c -4(a6), -3(a6))       */
#define INS_DISK_FRAME_BYTES  32
/* A letter that removes nothing and installs nothing: blank or none ($fdf1b2 cmpi.b #32; $fdf1ba tst.b) */
#define INS_DISK_BLANK        ' '
/* The cartridge's letter, kept as it is typed — lower case — and installed as a cartridge ($fdf1c8 cmpi.b #99) */
#define INS_CARTRIDGE_LETTER  'c'
#define INS_NO_ICON           (-1)       /* a disk's a_dicon                    ($fdf242 move.w #-1,20(a4))     */
#define INS_HALF              2          /* the screen halved: which side a new icon steps to ($fdf25a divs.w #2) */

/* ins_app's dialog (the desk's install-application tree) */
#define INS_APP_NAME          2          /* ($fdf43c move.w #2,-(sp))                                           */
#define INS_APP_EXTENSION     3          /* ($fdf44e move.w #3,-(sp))                                           */
#define INS_APP_KIND_FIRST    6          /* GEM, TOS, TOS-takes-parameters: three radio buttons ($fdf4ee #6, #3) */
#define INS_APP_KINDS         3
#define INS_APP_GEM           6          /* ($fdf468 154 = 6 * 24 + 10)                                         */
#define INS_APP_TOS           7          /* ($fdf48c 178)                                                       */
#define INS_APP_TTP           8          /* ($fdf47e 202)                                                       */
#define INS_APP_OK            9          /* ($fdf56a 227 = 9 * 24 + 11)                                         */
#define INS_APP_CANCEL        10         /* ($fdf6c2 250)                                                       */
#define INS_APP_ICON_FIRST    11         /* the icons' radio buttons             ($fdf4a6 addw #11; $fdf542 #17) */
#define INS_APP_ICONS         17
#define INS_APP_ICON_BASE     3          /* an application's a_aicon less this: its button ($fdf49a subq.w #3) */
#define INS_APP_DOCUMENT_ICON 4          /* ...and its documents' a_dicon        ($fdf684 addq.w #4,d0)         */
/* a_flags, GEM's AF_*: what the kind buttons read and set */
#define AF_ISCRYS             0x0001     /* a GEM program                       ($fdf45e btst #0,5(a5))         */
#define AF_ISGRAF             0x0002
#define AF_ISPARM             0x0008     /* a TOS program that takes parameters ($fdf474 btst #3,5(a5))         */
#define AF_ISFMEM             0x0010     /* kept from the old flags              ($fdf578 btst #4,-51(a6))      */
#define INS_APP_FLAGS_GEM     (AF_ISCRYS | AF_ISGRAF) /* ($fdf502 move.w #3,-54(a6))                           */
#define INS_APP_FLAGS_TOS     0          /* ($fdf50a clr.w -54(a6))                                             */
#define INS_APP_FLAGS_TTP     AF_ISPARM  /* ($fdf510 move.w #8,-54(a6))                                         */
#define INS_APP_WILD          '*'        /* a_pappl's first byte, a pattern     ($fdf3e2 cmpi.b #42)            */
#define INS_APP_ANY           '?'        /* ($fdf3ec cmpi.b #63)                                                */
#define INS_APP_DOT           '.'        /* ($fdf418 cmpi.b #46)                                                */
#define INS_APP_NO_OBJECT     (-1)       /* a new program's a_obid               ($fdf5d6 move.w #-1,8(a4))     */
#define AES_DESK_INS_ANY_DATA 0xfef5d4   /* "*.*": a data pattern's head        ($fdf628 move.l #$fef5d4)       */
#define INS_APP_PATTERN_HEAD  2          /* "*." — the extension copied over the second '*' ($fdf634 #-44)      */
#define APP_ALLOC_AT_THE_TAIL 0          /* app_alloc's: ins_disk's node          ($fdf20e clr.w (sp))          */
#define APP_ALLOC_AT_THE_HEAD 1          /* ...ins_app's                         ($fdf5be move.w #1,(sp))       */
/* ...and its frame from -46(a6), the frame's own layout: the INF texts it builds (the name, then "*." and the
 * extension over its third byte), the extension and the name as the dialog left them, then as the ANODE had them */
#define INS_APP_BUILT         0          /* bytes                               ($fdf5de addi.l #-46,(sp))      */
#define INS_APP_NEW_EXTENSION 14         /* bytes: fs_sget's                    ($fdf4da addi.l #-32,(sp))      */
#define INS_APP_OLD_EXTENSION 18         /* bytes: a_pdata's past its dot       ($fdf428 addi.l #-28,(sp))      */
#define INS_APP_NEW_NAME      22         /* bytes: fs_sget's                    ($fdf4c8 addi.l #-24,(sp))      */
#define INS_APP_OLD_NAME      34         /* bytes: fmt_str's of the name        ($fdf3fe addi.l #-12,(sp))      */
#define INS_APP_FRAME_BYTES   46

#ifndef __ASSEMBLER__
#include <stdint.h>

#ifndef RECREATE_HOST_DIFFERENTIAL
int16_t aes_desk_ins_disk(uint8_t *image, uint32_t anode);                                             /* $fdf11a */
int16_t aes_desk_ins_app(uint8_t *image, uint32_t name, uint32_t anode);                               /* $fdf3c8 */
#endif
#endif

#endif /* TOS102US_DESK_DESKINS_H */
