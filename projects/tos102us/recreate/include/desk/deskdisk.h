/* desk/deskdisk.h — THE DESK'S DISK UTILITIES, unit N (`src/desk/deskdisk.c`): the range `$fed888..$fee497` — the
 * desk's Format (`$fed912`, sh_cmd's `$fc`) and disk copy (`$fedde4`, sh_cmd's `$fb`), the utilities' dialog they
 * share (`$fed888` set up, `$fee236` run), and their helpers. Band 6 wave 4, group G2 (ruling R-W4-4): each routine
 * named `# ctx` until its body is read.
 */
#ifndef TOS102US_DESK_DESKDISK_H
#define TOS102US_DESK_DESKDISK_H

/* ---- band 6 wave 4, group G2 (unit N) ---- */
/* EACH READ FROM ITS BODY (names GEM-ish, `# ctx`: no symbol of the ROM's names them):
 *   $fed888 util_open()                      the utilities' resource (rom_ram's ROM_RSC_FORMAT) made the desk's, its
 *                                            tree (AES_DESK_UTIL_TREE) and its first TEDINFO (AES_DESK_UTIL_TEDINFOS)
 *                                            fetched, the write bar's frame's place kept (AES_DESK_UTIL_BAR_X / _Y),
 *                                            the three dialogs centred (Format's, the copy's, the progress box); the
 *                                            arrow (desk_wait(0)). Its D0: desk_wait's leftover
 *   $fee236 util_show(tree, depth, run, start)
 *                                            `tree`'s objects drawn to `depth` over the utility tree's root box grown
 *                                            8 pixels each way; where `run`, the dialog run (fm_do from `start`). D0:
 *                                            fm_do's or objc_draw's binding's leftover
 *   $fee450 util_redraw()                    the shell's command line drawn again (sh_draw(AES_DESK_UTIL_COMMAND, 0, 1))
 *   $fee466 fat_swap(word)                   a FAT word's two bytes swapped where it lies (`ror.w #8`); D0's word the
 *                                            swapped word
 *   $fee166 util_bars(step, width, tracks)  the progress box's two bars laid out: the step a track (the write bar's
 *                                            frame's width / 80, doubled for a disk of 40 tracks) and the bars' width
 *                                            (step x 80) answered into `step` and `width`, both frames that wide, the
 *                                            box drawn, each bar put at its frame's place in the box; the hourglass
 *   $fee364 util_error(error, drive)         the command line redrawn, the arrow; a negative `error` GEM's critical-
 *                                            error alert (crit_err(error, drive)), any other the utilities' own — 0
 *                                            "not the same type", else "an error has occurred"
 *   $fee3a4 fat_mark(cluster, unread, bpb, fat)
 *                                            `cluster` marked BAD in the FAT at `fat` — the 16-bit FAT's word $ffff, the
 *                                            12-bit FAT's twelve bits $fff (the word swapped in, masked, swapped back).
 *                                            ITS SECOND ARGUMENT IS NEVER READ: on the 12-bit arm the ROM STORES the
 *                                            mask's complement INTO THAT ARGUMENT SLOT, 10(a6) — its caller's frame,
 *                                            which format pops unread (`deskdisk.c`'s header)
 *   $fee294 copy_tracks(op, buffer, filler, device, side, step, first, count)
 *                                            `count` tracks from `first` of `side` read (op Floprd) or written (op
 *                                            Flopwr, each written track read back), nine sectors each into or from
 *                                            `buffer` a track after another, a step of the read / write bar drawn
 *                                            before each; the first failure util_error'd and answered. With no track
 *                                            the ROM answers its CALLER's D4 — at its one call site the copy's track
 *                                            count, the very word it hands as `first` (`deskdisk.c`)
 *   $fed912 desk_format(tail, command)       File > Format's built-in: two 8 KB buffers, the dialog until EXIT; each
 *                                            FORMAT: 80 tracks of one side or two formatted (Flopfmt, nine sectors in
 *                                            a skew table's order turned a skew a side), track 0 read back, the bar
 *                                            stepped; the boot sector made (Protobt) and written TWICE (Flopwr, Getbpb
 *                                            between), the root holding the volume label and both FATs written
 *                                            (Rwabs) with the bad sectors' clusters marked; the space left alerted
 *   $fedde4 desk_copy_disk(tail, command)    the disk copy: all of free memory but a kilobyte for tracks, 600 bytes
 *                                            for the boot sector (THAT Malloc FAILING LEAKS THE FIRST BLOCK: a ROM
 *                                            behaviour, kept); the dialog until EXIT; each COPY: both BPBs, the copy
 *                                            refused where their tracks or sides differ; per side, the tracks read and
 *                                            written a bufferful at a time, the boot sector read, given a new serial
 *                                            (Protobt) and written after the first pass
 *
 * ALCYON C. THE FLOPPY'S XBIOS CALLS ARE A DOOR OF THIS FILE'S (`xbios`): on target the XBIOS's own `trap #14` over
 * the ROM's frame, AES_XBIOS_RETURN parked as the ROM's trp14 door parks it; OFF TARGET the host has no floppy, so
 * the call goes through `desk_disk_xbios_door`, a hook A CASE BINDS (unit J's `desk_floprd_door` precedent). The
 * BIOS's Getbpb and Rwabs go through trp13's C twin (`desk/deskleaf.h`), the disk vectors' hook off target. */
#include "addrs.h"

/* THE UTILITY TREE's OBJECTS (`AES_DESK_UTIL_TREE`, the resource's tree 0): Format's dialog at its root, the copy's
 * at 11, the progress box at 17 — each a sub-tree drawn and run by its own root's address. */
#define UTIL_FORMAT_DIALOG    0          /* ($fed964: fm_do of the tree itself)                                 */
#define UTIL_DOUBLE_SIDED     8          /* its "Double Sided" radio button     ($fed9a6 tst.w 202(a0))        */
#define UTIL_FORMAT_EXIT      9          /* its EXIT                            ($fed96e tst.w 226(a0))        */
#define UTIL_FORMAT_GO        10         /* its FORMAT                          ($fed988 clr.w 250(a0))        */
#define UTIL_FORMAT_START     3          /* fm_do's start object                ($fed954 move.w #3,(sp))       */
#define UTIL_COPY_DIALOG      11         /* ($fede98 addi.l #264,(sp))                                          */
#define UTIL_COPY_EXIT        15         /* ($fedea8 tst.w 370(a0))                                            */
#define UTIL_COPY_GO          16         /* ($fedec2 clr.w 394(a0))                                            */
#define UTIL_COPY_START       0          /* fm_do's start: none                 ($fede8a clr.w (sp))           */
#define UTIL_PROGRESS         17         /* the progress box                    ($fed902 addi.l #408,(sp))     */
#define UTIL_PROGRESS_TEXT    18         /* its line: the command shown         ($fed9c0 move.l 12(a6),444(a0)) */
#define UTIL_WRITE_FRAME      20         /* the write bar's frame (Format's bar, the copy's writes) ($fed8c0 496(a0)) */
#define UTIL_WRITE_BAR        21         /* ...the bar                          ($fedbde add.w d0,524(a1))     */
#define UTIL_READ_FRAME       22         /* the read bar's frame (the copy's reads) ($fee1fa 544(a1))           */
#define UTIL_READ_BAR         25         /* ...the bar                          ($fee2a8 moveq #25,d5)         */
/* THE COPY RE-LINKS THE PROGRESS BOX (`$fede66..$fede78`, undone at `$fee138`): the write bar's frame's next — in the
 * box's sub-tree, numbered from it — the read bar's frame, and the box's last child the read bar's subtree's, so the
 * box shows both bars; Format's box ends at the write bar's frame. */
#define PROGRESS_WRITE_FRAME_NEXT_COPY 5   /* (UTIL_READ_FRAME in the box's numbering) ($fede6c move.w #5,480(a0)) */
#define PROGRESS_WRITE_FRAME_NEXT_FORMAT 0 /* (the box itself: the frame its last child) ($fee13e clr.w 480(a0))  */
#define PROGRESS_LAST_CHILD_COPY 7        /*                                    ($fede78 move.w #7,412(a0))    */
#define PROGRESS_LAST_CHILD_FORMAT 3      /* (UTIL_WRITE_FRAME in its numbering) ($fee148 move.w #3,412(a0))    */
/* A BAR'S TWO COLOURS (its G_BOX's ob_spec): blanked while it is drawn once a side is done, then the bar's own. */
#define UTIL_BAR_SPEC_BLANK   0x00011100 /*                                     ($fee0de move.l #$11100,12(a0)) */
#define UTIL_BAR_SPEC_FILLED  0x000111a1 /*                                     ($fee10e move.l #$111a1,12(a0)) */
#define UTIL_DIALOG_MARGIN    8          /* util_show's clip: the root box grown so much each way ($fee260 subq.w #8) */
#define UTIL_DRAW_DEPTH_DIALOG 2         /* Format's dialog drawn to depth 2    ($fed958 move.l #$20001)       */
#define UTIL_DRAW_DEPTH_COPY  1          /* the copy's to depth 1               ($fede8c move.l #$10001)       */
#define UTIL_DRAW_DEPTH_BOX   1          /* the progress box                    ($fee1ba move.w #1,-(sp))      */
#define UTIL_DRAW_DEPTH_BAR   0          /* a bar, alone                        ($fedbe2 clr.w (sp); clr.l)    */
#define UTIL_RUN              1
#define UTIL_DRAW_ONLY        0
#define UTIL_NO_START         0
/* THE UTILITIES' TEDINFOS (`AES_DESK_UTIL_TEDINFOS`): Format's drive line, its label field, the copy's two drives. */
#define UTIL_TED_FORMAT_DRIVE 0          /* te_ptext := the tail                ($fed938 move.l 8(a6),(a0))    */
#define UTIL_TED_LABEL        1          /* the volume label typed: its te_txtlen reset, its te_ptext copied ($fed94e) */
#define UTIL_TED_COPY_SOURCE  2          /* te_ptext := the tail                ($fede32 move.l 8(a6),56(a0))  */
#define UTIL_TED_COPY_DESTINATION 3      /* te_ptext := the tail + 3: "A: B:"'s second drive ($fede44)           */
#define UTIL_LABEL_TXTLEN     12         /* the label's eleven bytes and the NUL ($fed94e move.w #12,52(a0))   */
#define COPY_DESTINATION_IN_THE_TAIL 3   /* the tail's "A:\0B:" — its second letter ($fede3c addq.l #3,d0)     */
/* THE PROGRESS BARS (util_bars): their width cut into one step a track of the 80 a disk may have, doubled for 40. */
#define UTIL_BAR_TRACKS       80         /* ($fee196 divs.w #80)                                               */
#define UTIL_BAR_HALF_TRACKS  40         /* ($fee222 cmpi.w #40,16(a6))                                        */
#define UTIL_BAR_HOURGLASS    1          /* util_bars ends on desk_wait(1)      ($fee22e move.w #1,(sp))       */

/* THE FLOPPY: the XBIOS's functions and frames (each the ROM's push order), the BIOS's two. */
#define XBIOS_FLOPWR_FN       9          /* (XBIOS_FLOPRD_FN: `desk/desksupp.h`) ($fedc36 move.w #9,-(sp))      */
#define XBIOS_FLOPFMT_FN      10         /*                                     ($fedaf0 move.w #10,-(sp))     */
#define XBIOS_STUB_11_FN      11         /* the copy asks it of each drive and hands its answer on as Floprd's and
                                          * Flopwr's filler longword; THIS ROM's is a stub, `$fc0fc0` answers 0
                                          *                                     ($feded4 move.w #11,-(sp))     */
#define XBIOS_FLOPRW_WORDS    10         /* Floprd / Flopwr: the function, buffer.l, filler.l, device, sector,
                                          * track, side, count                  ($fedba4 adda.l #18 + its slot) */
#define XBIOS_FLOPFMT_WORDS   13         /* the function, buffer.l, skew.l, device, sectors, track, side,
                                          * interleave, magic.l, virgin         ($fedaf6 adda.l #24 + its slot) */
#define XBIOS_PROTOBT_WORDS   7          /* the function, buffer.l, serial.l, type, executable ($fedc1c)        */
#define XBIOS_STUB_11_WORDS   2          /* the function, the drive             ($fededa addq.l #2)            */
#define XBIOS_FRAME_WORDS     XBIOS_FLOPFMT_WORDS     /* the widest                                             */
#define FLOPPY_SECTORS        9          /* a track's: formatted, read, written ($fedade, $fee2e2 move.w #9)   */
#define FLOPPY_SECTOR_SHIFT   9          /* a sector's 512 bytes                ($fedc84 moveq #9,d1; asl.w)   */
#define FLOPPY_TRACK_BYTES    4608       /* nine sectors                        ($fee34a addi.l #4608,d7)      */
#define FLOPPY_FIRST_SECTOR   1          /* the boot sector: sector 1 of track 0, side 0, one ($fedb8c)        */
#define FLOPPY_BOOT_TRACK     0
#define FLOPPY_BOOT_SIDE      0
#define FLOPPY_ONE_SECTOR     1
#define FLOPPY_NO_FILLER      0          /* Format's Floprd's filler            ($fedb90 clr.l -(sp))          */
#define FLOPFMT_BY_THE_SKEW   (-1)       /* the interleave: the skew table's order ($fedad4 move.w #-1,-(sp))   */
#define FLOPFMT_MAGIC         0x87654321 /*                                     ($fedace move.l #$87654321)    */
#define FLOPFMT_VIRGIN        0xe5e5     /* each sector's fill                  ($fedaca move.w #$e5e5,(sp))   */
#define FLOPFMT_BAD_SECTORS   (-16)      /* Flopfmt's "bad sectors": their list at the buffer's head, 0 ended ($fedb02) */
#define FORMAT_GOOD_TRACKS    2          /* a bad sector on track 0 or 1 is fatal ($fedb18 cmpi.w #2,d6)       */
#define FORMAT_BAD_ROOM       16         /* the bad list may grow while a track's nine more fit ($fedb24 cmpi.w #16) */
#define FORMAT_FAILED         1          /* a failure's verdict: util_error(1) and the format abandoned ($fedb36) */
#define PROTOBT_NEW_SERIAL    0x01000000 /* a random serial                     ($fedc0e move.l #$1000000)     */
#define PROTOBT_KEEP          (-1)       /* the type / executable kept          ($fee006 move.w #-1)           */
#define PROTOBT_NOT_EXECUTABLE 0         /*                                     ($fedc0a clr.w (sp))           */
#define BIOS_RWABS_WRITE_NO_MEDIA_CHECK 3 /* Rwabs's flag: a write, the media change not asked ($fedce6 #$40003)  */
#define FAT_FIRST_RECORD      1          /* the first FAT follows the boot sector ($fedd5c move.w #1,-(sp))     */
/* THE FORMAT's ARITHMETIC OF THE DISK: two sides 80 tracks or one, its skew, its prototype boot sector's type. */
#define FORMAT_BUFFER_BYTES   8192       /* each of its two buffers             ($fed91a move.l #8192,(sp))    */
#define FORMAT_TRACKS         80         /*                                     ($fed992 move.w #80,-30(a6))   */
#define FORMAT_SIDES_SINGLE   1          /*                                     ($fed98c move.w #1,-32(a6))    */
#define FORMAT_SIDES_DOUBLE   2          /*                                     ($fed9ac move.w #2,-32(a6))    */
#define FORMAT_SKEW_SINGLE    3          /* the skew table turned so far a side ($fed998 move.w #3,-72(a6))    */
#define FORMAT_SKEW_DOUBLE    2          /*                                     ($fed9b4 move.w #2,-72(a6))    */
#define FORMAT_TYPE_SINGLE    2          /* Protobt's disk type: 80 tracks, one side ($fed99e moveq #2,d5)     */
#define FORMAT_TYPE_DOUBLE    3          /* ...two                              ($fed9b2 moveq #3,d5)          */
#define FORMAT_SKEW_TABLE     0xfefd96   /* the ROM's skew table: 3, 4 .. 9, 1, 2 ($feda12 addal #$fefd96,a1)  */
#define FORMAT_LABEL_ATTRIBUTE_WORD 8    /* the root's first entry: bytes 10, 11 — no name byte, FA_LABEL ($fedcb2) */
#define FORMAT_LABEL_ATTRIBUTE_AT 10
#define FORMAT_LABEL_BYTES    11         /* the label's name and extension      ($fedcb8 move.w #11,(sp))      */
#define FAT_MEDIA_WORD_0      0xf7ff     /* the FAT's first two words           ($fedd14 move.w #$f7ff,(a4))   */
#define FAT_MEDIA_WORD_1      0xff00     /*                                     ($fedd18 move.w #$ff00,2(a4))  */
#define FAT_FIRST_CLUSTER     2          /* the data area's first cluster       ($fedd38 addq.w #2,d0)         */
#define FORMAT_ALERT_DEFAULT  1          /* fm_alert's default button, each of the unit's ($fedcc4, $fee38a)   */
/* THE COPY's: all of free memory but a kilobyte, no less than a track's worth; 600 bytes for the boot sector. */
#define COPY_HELD_BACK_BYTES  1024       /* ($feddf6 addi.l #-1024,d0)                                          */
#define COPY_BOOT_BYTES       600        /* ($fede16 move.l #600,(sp))                                         */
#define COPY_PASSES           2          /* the bufferfuls of tracks, then the rest ($fee0b4 cmpi.w #2,-12(a6))  */
#define COPY_FIRST_BAR        UTIL_WRITE_BAR  /* the bars blanked once a side is copied: 21, then 25 ($fee0c6) */
#define COPY_BAR_STRIDE       4          /*                                     ($fee116 addq.w #4,-10(a6))    */
#define COPY_LAST_BAR_BOUND   26         /*                                     ($fee11a cmpi.w #26,-10(a6))   */
/* THE DRIVER'S RECORD Getbpb answers (`gemdos/fs.h`'s BPB_* and two of the floppy driver's own past them). */
#define FLOPPY_BPB_TRACKS     18         /* word: the disk's tracks             ($fedf0a move.w 18(a5),d0)     */
#define FLOPPY_BPB_SIDES      20         /* word: its sides                     ($fedf14 move.w 20(a5),d0)     */
#define BPB_BFLAGS_LOW_BYTE   17         /* BPB_BFLAGS's low byte: bit 0, the FAT is 16-bit ($fee3ac btst #0,17(a0)) */
#define BPB_FAT16_BIT         0
/* fat_mark's twelve bits, at cluster x 1.5: an even cluster the word's low twelve (byte-swapped), an odd one the high. */
#define FAT16_BAD             0xffff     /* ($fee3c8 move.w #-1,(a0))                                           */
#define FAT12_BAD_EVEN        0x0fff     /* the value stored into the argument slot ($fee3e0 move.w #4095,10(a6)) */
#define FAT12_KEEP_EVEN       0xf000     /*                                     ($fee3fc move.w #-4096,-8(a6)) */
#define FAT12_BAD_ODD         0xfff0     /*                                     ($fee3ee move.w #-16,10(a6))   */
#define FAT12_KEEP_ODD        0x000f     /*                                     ($fee3f4 move.w #15,-8(a6))    */
#define FAT_SWAP_BITS         8          /* ($fee470 ror.w #8,d0)                                              */
/* THE ALERTS (ROM strings), util_error's verdicts. */
#define UTIL_ERROR_NOT_THE_SAME_TYPE 0   /* the copy's BPBs differ              ($fedf20 clr.w -(sp))          */
#define UTIL_ALERT_ERROR      0xfef48a   /* "[3][An error has occurred during|format or copy. ..." ($fee384)    */
#define UTIL_ALERT_NOT_THE_SAME_TYPE 0xfef4e0 /* "[3][The source disk is not|the same type as the|destination disk.]" */
#define UTIL_ALERT_SPACE      0xfef52a   /* "[1][This disk has %L bytes|available to user.][ OK ]" ($feddb4)     */
#define UTIL_REDRAW_OBJECT    0          /* sh_draw(command, 0, 1)              ($fee454 move.w #1,(sp); clr.w) */
#define UTIL_REDRAW_DEPTH     1

/* THE FRAMES THE ROM HANDS ON BY ADDRESS, each a host slot off target (`host_slot.h`, group G2's window):
 *   util_open's rectangle `-8(a6)`, handed ob_center three times;
 *   ONE FRAME FORMAT AND THE COPY SHARE (both sh_cmd's built-ins: never nested) — COMPACTED: util_bars' two answers
 *   (Format's -22 / -20(a6), the copy's -14 / -26(a6)), Format's Dfree answers (dos_space's -12 / -8(a6), the second
 *   merge_str's parameter) and its skew table (-52(a6), Flopfmt's second longword); HELD ACROSS THE DIALOGS' fm_do,
 *   util_error's alerts and Format's fm_alert — a "held where parked" fact the binding owes
 *   (`aes_event.SLOTS_HELD_WHERE_PARKED`);
 *   fat_mark's FAT word `-2(a6)`, handed fat_swap twice. */
#define UTIL_OPEN_RECT_BYTES  8
#define UTIL_FRAME_BAR_STEP   0          /* word: util_bars' step a track       (-22 / -14(a6))                */
#define UTIL_FRAME_BAR_WIDTH  2          /* word: ...its width                  (-20 / -26(a6))                */
#define UTIL_FRAME_SPACE_TOTAL 4         /* long: dos_space's total             (-12(a6))                      */
#define UTIL_FRAME_SPACE_FREE 8          /* long: ...the free space: the alert's %L (-8(a6))                   */
#define UTIL_FRAME_SKEW       12         /* words[9]: the skew table Flopfmt is handed (-52(a6))               */
#define UTIL_FRAME_BYTES      (UTIL_FRAME_SKEW + FLOPPY_SECTORS * 2)
#define FAT_MARK_WORD_BYTES   2

/* THE RETURN SITES THE DOORS PARK: each the word after its Line-F call. */
#define AES_FORMAT_FLOPFMT_RETURN      0xfedaf6
#define AES_FORMAT_FLOPRD_RETURN       0xfedba4
#define AES_FORMAT_PROTOBT_RETURN      0xfedc1c
#define AES_FORMAT_FLOPWR_RETURN       0xfedc3c
#define AES_FORMAT_GETBPB_RETURN       0xfedc4c
#define AES_FORMAT_FLOPWR_AGAIN_RETURN 0xfedc6a
#define AES_FORMAT_ROOT_RWABS_RETURN   0xfedcee
#define AES_FORMAT_FAT_RWABS_RETURN    0xfedd6e
#define AES_FORMAT_FAT2_RWABS_RETURN   0xfedd8c
#define AES_FORMAT_FREE_RETURN         0xfeddd4    /* ...its three dos_frees: the first buffer, the tree, the second */
#define AES_FORMAT_FREE_TREE_RETURN    0xfedddc
#define AES_FORMAT_FREE_LIST_RETURN    0xfedde0
#define AES_COPY_DESTINATION_GETBPB_RETURN 0xfeded0
#define AES_COPY_DESTINATION_STUB_RETURN   0xfededa
#define AES_COPY_SOURCE_GETBPB_RETURN  0xfedee8
#define AES_COPY_SOURCE_STUB_RETURN    0xfedef4
#define AES_COPY_FLOPRD_RETURN         0xfee000
#define AES_COPY_PROTOBT_RETURN        0xfee01e
#define AES_COPY_FLOPWR_RETURN         0xfee072
#define AES_COPY_FREE_RETURN           0xfee154    /* ...its three: the tracks' block, the tree, the boot sector's */
#define AES_COPY_FREE_TREE_RETURN      0xfee15c
#define AES_COPY_FREE_BOOT_RETURN      0xfee162
#define AES_COPY_TRACKS_RETURN         0xfee300    /* copy_tracks' Floprd / Flopwr                              */
#define AES_COPY_TRACKS_VERIFY_RETURN  0xfee332    /* ...a written track's read back                            */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_util_open(uint8_t *image);                                                              /* $fed888 */
void aes_desk_util_show(uint8_t *image, uint32_t tree, int16_t depth, int16_t run, int16_t start);   /* $fee236 */
void aes_desk_util_redraw(uint8_t *image);                                                            /* $fee450 */
uint16_t aes_desk_fat_swap(uint8_t *image, uint32_t word);                                            /* $fee466 */
void aes_desk_util_bars(uint8_t *image, uint32_t step, uint32_t width, int16_t tracks);              /* $fee166 */
void aes_desk_util_error(uint8_t *image, int16_t error, int16_t drive);                              /* $fee364 */
void aes_desk_fat_mark(uint8_t *image, int16_t cluster, int16_t unread, uint32_t bpb, uint32_t fat); /* $fee3a4 */
int16_t aes_desk_copy_tracks(uint8_t *image, int16_t op, uint32_t buffer, uint32_t filler, int16_t device,
                             int16_t side, int16_t step, int16_t first, int16_t count);              /* $fee294 */
int16_t aes_desk_format(uint8_t *image, uint32_t tail, uint32_t command);                            /* $fed912 */
int16_t aes_desk_copy_disk(uint8_t *image, uint32_t tail, uint32_t command);                         /* $fedde4 */

#ifdef RECREATE_HOST_DIFFERENTIAL
/* OFF TARGET: the XBIOS call a case binds — `frame` its `words` in the ROM's push order (the function first). */
extern int32_t (*desk_disk_xbios_door)(uint8_t *image, const uint16_t *frame, uint16_t words);
#endif
#endif
/* ---- end of group G2's wave-4 ---- */

#endif /* TOS102US_DESK_DESKDISK_H */
