/* geminit.c — GEMINIT (`aes/geminit.h`): gem_main, the INF reader, and the three leaves ini_dlongs, all_run and
 * pinit. Alcyon C in the ROM, ported over its own order: every callee is its C core, every GEMDOS call the glue's door
 * (`aes/gemdosif.h`) with the return site the ROM's own Line-F call parks (a code address stored as the data it is).
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/ctrl.h"
#include "aes/deskleaf.h"
#include "aes/evasync.h"
#include "aes/evdisp.h"
#include "aes/evinput.h"
#include "aes/evlib.h"
#include "aes/fslib.h"
#include "aes/gemctrl.h"
#include "aes/gemdosif.h"
#include "aes/gemgraf.h"
#include "aes/geminit.h"
#include "aes/gemstart.h"
#include "aes/gsxif.h"
#include "aes/infscan.h"
#include "aes/loader.h"
#include "aes/mnlib.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/shell_buf.h"
#include "aes/shlib.h"
#include "aes/strings.h"
#include "aes/switch.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"

/* The ROM reaches four of the five through A5, THEGLO's base (`lea <offset>(a5),a0`): the offsets its instructions
 * carry, held to the absolute addresses the C stores. */
#define THEGLO_SHELL_LINE     8022       /* ($fda00a lea 8022(a5),a0)                                          */
#define THEGLO_SH_COMMAND     10198      /* ($fda014 lea 10198(a5),a0)                                         */
#define THEGLO_SH_PATH_BUFFER 7910       /* ($fda01e lea 7910(a5),a0)                                          */
#define THEGLO_SYSTEM_GLOBAL  7992       /* ($fda028 lea 7992(a5),a0)                                          */
_Static_assert(AES_SHELL_LINE == AES_THEGLO + THEGLO_SHELL_LINE && AES_SH_COMMAND == AES_THEGLO + THEGLO_SH_COMMAND,
               "the shell's two lines lie in THEGLO");
_Static_assert(AES_SH_PATH_BUFFER == AES_THEGLO + THEGLO_SH_PATH_BUFFER
               && AES_SYSTEM_GLOBAL == AES_THEGLO + THEGLO_SYSTEM_GLOBAL, "...and the path and global[]");

/* $fd9ffc — ini_dlongs: the five long pointers, in the ROM's order — the command line, its tail, the working path,
 * the AES's global[], and the screen's lock. */
void aes_ini_dlongs(uint8_t *image)
{
    wr32(image + AES_SHELL_BUFFER, AES_SHELL_LINE);
    wr32(image + AES_SHELL_TAIL, AES_SH_COMMAND);
    wr32(image + AES_SH_PATH_POINTER, AES_SH_PATH_BUFFER);
    wr32(image + AES_RS_SYSTEM_GLOBAL, AES_SYSTEM_GLOBAL);
    wr32(image + AES_AD_WINDSPB, AES_WIND_SPB);
}

/* $fda03e — all_run: a yield (the ROM's loop of one), then the screen's lock taken and given back — the caller
 * waits there for whoever holds it. It sets no D0 (what is left there is the release's — unsync's — and none of its
 * three callers reads it: $fda396, $fddea2 `moveq #1,d0`, $fe5e6c). */
void aes_all_run(uint8_t *image)
{
    int16_t yielded;

    for (yielded = 0; yielded < ALL_RUN_YIELDS; yielded++)
        aes_dsptch(image);
    (void)aes_wm_update(image, WM_BEG_UPDATE);
    (void)aes_wm_update(image, WM_END_UPDATE);
}

/* $fda3d6 — pinit: the PD at `pd` given its CDA, its pipe (the address of its own queue, read from the start) and a
 * blank name. Every other field is left as it is. */
void aes_pinit(uint8_t *image, uint32_t pd, uint32_t cda)
{
    set_bus_long(image, pd + PD_CDA, cda);
    set_bus_long(image, pd + PD_QUEUE_ADDRESS, pd + PD_QUEUE);
    set_bus_word(image, pd + PD_QUEUE_INDEX, 0);
    aes_bfill(image, PD_NAME_BYTES, PD_NAME_FILL, pd + PD_NAME);
}

/* ================================================================================================
 * The INF reader.
 * ============================================================================================= */

_Static_assert(HOST_SLOT_AES_READ_INF_PAIR_BYTES == sizeof(uint16_t), "the reader's local: the pair scan_2 answers");
_Static_assert(HOST_SLOT_AES_GEM_MAIN_ICON_BYTES == sizeof(uint32_t), "gem_main's local: the BITBLK rs_gaddr answers");

/* The ROM's default INF into the buffer ($fda4b4, $fda4c4: the same three pushes twice). */
static void take_the_rom_s_inf(uint8_t *image, uint32_t buffer)
{
    (void)aes_rom_ram(image, ROM_RSC_DESKTOP_INF, buffer, INF_ROM_RAM_NO_SIZE);
}

/* `\DESKTOP.INF` opened ($fda43c..$fda48c): on the drive the call began on, and — where that fails and the drive map
 * has a C: — on C:, which is then THE CURRENT DRIVE (behaviour (c)). With no C: the glue's verdict is set by hand.
 * Answers the handle; the verdict is the glue's word, as the caller tests it. */
static int16_t open_the_inf(uint8_t *image)
{
    int16_t handle;

    (void)aes_dos_chdir(image, AES_READ_INF_CHDIR_RETURN, AES_INF_ROOT);
    handle = (int16_t)aes_dos_open(image, AES_INF_NAME, INF_OPEN_MODE);
    if (!aes_dos_failed(image))
        return handle;
    if (!(aes_isdrive(image) & DRIVE_C_BIT)) {
        wr16(image + AES_DOS_ERR, GEM_DOS_FAILED);
        return handle;
    }
    (void)aes_dos_sdrv(image, AES_READ_INF_SDRV_C_RETURN, DRIVE_C);
    (void)aes_dos_chdir(image, AES_READ_INF_CHDIR_OF_C_RETURN, AES_INF_ROOT_OF_C);
    return (int16_t)aes_dos_open(image, AES_INF_NAME_OF_C, INF_OPEN_MODE);
}

/* The file into the buffer ($fda42a..$fda4d0), or the ROM's default where there is no drive to read, the disk is
 * not usable, or no file opens. Answers whether a file was READ — the read's own verdict is not asked — and, through
 * `count`, what Fread answered: the word the caller ends the text by. */
static int16_t fill_from_the_file(uint8_t *image, uint32_t buffer, int16_t *count)
{
    int16_t drive, handle;

    if (!(uint16_t)aes_isdrive(image) || !be16(image + AES_DISK_USABLE)) {
        take_the_rom_s_inf(image, buffer);
        return INF_NOT_READ;
    }
    drive = (int16_t)aes_dos_gdrv(image, AES_READ_INF_GDRV_RETURN);
    handle = open_the_inf(image);
    if (aes_dos_failed(image)) {
        take_the_rom_s_inf(image, buffer);
        return INF_NOT_READ;
    }
    *count = (int16_t)aes_dos_read(image, handle, INF_BUFFER_BYTES, buffer);
    (void)aes_dos_close(image, AES_READ_INF_CLOSE_RETURN, handle);
    (void)aes_dos_sdrv(image, AES_READ_INF_SDRV_BACK_RETURN, drive);
    return INF_READ;
}

/* The second pair of the `#E` line at `pair_at` ($fda4fc..$fda544). A CHANGE PENDING: the pair rewritten — its high
 * digit kept, its low the device in use less one — and the scan goes on. NONE: the pair's low two bits + 1 asked for
 * as the device, and the scan ends; answers 0 where that is the device in use already, else 1. */
static int16_t act_on_the_screen_line(uint8_t *image, uint32_t pair_at, int16_t *scanning)
{
    uint16_t pair_local;
    uint32_t pair_slot = host_slot_claim(AES_READ_INF_PAIR, &pair_local);
    uint16_t pair;

    (void)aes_scan_2(image, pair_at, pair_slot);
    host_slot_load_words(image, pair_slot, &pair_local, 1);
    pair = pair_local;
    host_slot_release(AES_READ_INF_PAIR);
    if (be16(image + AES_GL_RSCHANGE)) {
        (void)aes_save_2(image, pair_at, (int16_t)((pair & INF_PAIR_KEPT_BITS) | (uint16_t)(be16(image + AES_GL_RESTYPE) - 1)));
        return INF_READ;
    }
    wr16(image + AES_GL_RSCHANGE, GEM_NO_RESCHANGE);
    *scanning = 0;
    return aes_app_reschange(image, (int16_t)((pair & INF_PAIR_DEVICE_BITS) + 1)) ? INF_READ : INF_NOT_READ;
}

/* The text scanned for `#E` ($fda4d8..$fda54c): ended first where the read ended (behaviour (b): the count a SIGNED
 * WORD), then every `#` looked behind; an `E` there is the screen's line, its second pair five bytes on. The cursor
 * stays on the pair (scan_2's answer is not taken). Answers what the last line acted on answered, 1 with none. */
static int16_t scan_for_the_screen_line(uint8_t *image, uint32_t buffer, int16_t count)
{
    uint32_t cursor = buffer;
    int16_t scanning = 1, read = INF_READ;

    set_bus_byte(image, offset_by(buffer, count), 0);
    while (bus_byte(image, cursor) && scanning) {
        if (bus_byte(image, cursor++) != INF_LINE_MARK || bus_byte(image, cursor) != INF_SCREEN_LINE)
            continue;
        cursor += INF_SECOND_PAIR;
        if (!act_on_the_screen_line(image, cursor, &scanning))
            read = INF_NOT_READ;
    }
    return read;
}

/* $fda408 — the INF reader (`aes/geminit.h`): a block for the text; the shell's GEM buffer into it; the file, or the
 * ROM's default, over that; the screen's line where a file was read; the block back into the shell's buffer, and
 * freed. */
int16_t aes_gem_read_inf(uint8_t *image)
{
    uint32_t buffer = aes_dos_alloc(image, INF_BUFFER_BYTES);
    int16_t count = 0, read;

    (void)aes_sh_get(image, buffer, INF_BUFFER_BYTES);
    read = fill_from_the_file(image, buffer, &count);
    if (read)
        read = scan_for_the_screen_line(image, buffer, count);
    (void)aes_sh_put(image, buffer, INF_BUFFER_BYTES);
    (void)aes_dos_free(image, AES_READ_INF_FREE_RETURN, buffer);
    return read;
}

/* ================================================================================================
 * gem_main.
 * ============================================================================================= */

/* cli and sti ($fe38a4, $fe38aa): every interrupt masked with nothing parked, and every one let in. On target the
 * switch's own two entries (`switch.S`); off target there is no status register (`aes/switch.h`). */
#ifdef RECREATE_HOST_DIFFERENTIAL
static inline void every_interrupt_masked(void)
{
}

static inline void every_interrupt_let_in(void)
{
}
#else
void aes_rom_cli(void);                                                                               /* $fe38a4 */
void aes_rom_sti(void);                                                                               /* $fe38aa */
#define every_interrupt_masked() aes_rom_cli()
#define every_interrupt_let_in() aes_rom_sti()
#endif

/* The ROM reaches the tables and the UDAs through A5, THEGLO's base: the displacements its instructions carry, held
 * to the absolute addresses the C stores. */
#define THEGLO_EVB_TABLE      5274       /* ($fda0ae move.l $c676,5274(a0))                                    */
#define THEGLO_PD_TABLE       4614       /* ($fda142 addi.l #4614,(sp))                                        */
#define THEGLO_CDA_TABLE      5166       /* ($fda130 addi.l #5166,(sp))                                        */
#define THEGLO_UDA1           1866       /* ($fda158 lea 1866(a5),a0)                                          */
#define THEGLO_UDA2           3140       /* ($fda160 lea 3140(a5),a0)                                          */
_Static_assert(AES_EVB_TABLE == AES_THEGLO + THEGLO_EVB_TABLE && AES_PD_TABLE == AES_THEGLO + THEGLO_PD_TABLE
               && AES_CDA_TABLE == AES_THEGLO + THEGLO_CDA_TABLE, "the three tables lie in THEGLO");
_Static_assert(AES_UDA1 == AES_THEGLO + THEGLO_UDA1 && AES_UDA2 == AES_THEGLO + THEGLO_UDA2, "...and the two UDAs");
_Static_assert(AES_PD_COUNT == AES_UDA_COUNT, "a UDA for each static process");

/* The recorder off, and the lists the event layer and the scheduler keep, empty ($fda076..$fda11a): every event block
 * pushed on the free list in the table's order (the last is its head), the list's head read back from memory each
 * time; the woken, the not-ready, the completed and the delay lists; the fork queue; the screen's lock. AES_ELINKOFF
 * is where an EVB's list link lies — the ROM spells it as the difference of two addresses (behaviour (f)). */
static void empty_the_lists(uint8_t *image)
{
    int16_t index;

    wr16(image + AES_GL_RECD, 0);
    wr16(image + AES_RECORD_LEFT, 0);
    wr32(image + AES_RECORD_CURSOR, 0);
    wr32(image + AES_ELINKOFF, EVB_LINK);
    wr32(image + AES_EUL, 0);
    for (index = 0; index < AES_EVB_COUNT; index++) {
        uint32_t event = table_entry(AES_EVB_TABLE, index, EVB_BYTES);

        wr32(image + event + EVB_NEXT, be32(image + AES_EUL));
        wr32(image + AES_EUL, event);
    }
    wr32(image + AES_DRL, 0);
    wr32(image + AES_NRL, 0);
    wr32(image + AES_ZOMBIE_LIST, 0);
    wr32(image + AES_DELAY_LIST, 0);
    wr16(image + AES_FORK_COUNT, 0);
    wr16(image + AES_FORK_TAIL, 0);
    wr16(image + AES_FORK_HEAD, 0);
    image[AES_FORKER_BUSY] = 0;
    wr16(image + AES_WIND_SPB + SPB_COUNT, 0);
    wr32(image + AES_WIND_SPB + SPB_OWNER, 0);
    wr32(image + AES_WIND_SPB + SPB_WAIT, 0);
}

/* The three static processes, by their place in the PD table. */
enum { SHELL_PROCESS, SCREEN_MANAGER_PROCESS, SPARE_PROCESS };

/* The three static processes ($fda120..$fda174): each PD its CDA (pinit); each its UDA — the shell's is THEGLO's
 * first bytes, whose stack top gem_entry stored —; and the two others' stack tops. */
static void lay_out_the_static_processes(uint8_t *image)
{
    int16_t index;

    for (index = 0; index < AES_PD_COUNT; index++)
        aes_pinit(image, table_entry(AES_PD_TABLE, index, PD_BYTES), table_entry(AES_CDA_TABLE, index, CDA_BYTES));
    wr32(image + table_entry(AES_PD_TABLE, SHELL_PROCESS, PD_BYTES) + PD_UDA, AES_THEGLO);
    wr32(image + table_entry(AES_PD_TABLE, SCREEN_MANAGER_PROCESS, PD_BYTES) + PD_UDA, AES_UDA1);
    wr32(image + table_entry(AES_PD_TABLE, SPARE_PROCESS, PD_BYTES) + PD_UDA, AES_UDA2);
    wr32(image + AES_UDA1 + UDA_SUPER_SP, AES_UDA1_STACK_TOP);
    wr32(image + AES_UDA2 + UDA_SUPER_SP, AES_UDA2_STACK_TOP);
}

/* The first of them made THE RUNNING PROCESS ($fda178..$fda1c8): the count of static processes cleared and READ BACK
 * for which PD — the first —, that PD given the count as its id, the count stepped; alone on the ready list, ready;
 * its CDA the current one. Every field through the pointer memory holds, as the ROM reads it back each time. */
static void run_the_first_process(uint8_t *image)
{
    wr16(image + AES_STATIC_PIDS, 0);
    wr32(image + AES_RLR, table_entry(AES_PD_TABLE, global_word(image, AES_STATIC_PIDS), PD_BYTES));
    set_bus_word(image, be32(image + AES_RLR) + PD_PID, be16(image + AES_STATIC_PIDS));
    wr16(image + AES_STATIC_PIDS, (uint16_t)(be16(image + AES_STATIC_PIDS) + 1));
    set_bus_long(image, be32(image + AES_RLR) + PD_LINK, 0);
    set_bus_word(image, be32(image + AES_RLR) + PD_STAT, PD_STAT_READY);
    wr32(image + AES_GL_CDA, bus_long(image, be32(image + AES_RLR) + PD_CDA));
}

/* gem_main's first stretch ($fda062..$fda1ce): the long pointers, every interrupt masked, `trap #2` taken, the lists
 * and the three processes — to where the interrupts are let in. NOT INLINED on target: what it keeps in registers is
 * then saved in ITS frame, which is gone before the shell runs (`aes_rom_gem_main`, below). */
static __attribute__((noinline)) void lay_the_processes(uint8_t *image)
{
    aes_ini_dlongs(image);
    every_interrupt_masked();
    aes_install_trap2(image);
    empty_the_lists(image);
    lay_out_the_static_processes(image);
    run_the_first_process(image);
}

/* The AES's own resource, and the two mouse forms kept by the address of their bits ($fda1f2..$fda23e): rs_gaddr
 * answers where the form's data pointer lies, and the pointer is read through it into the same longword. */
static void take_a_mouse_form(uint8_t *image, int16_t form, uint32_t kept_at)
{
    (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_BIPDATA, form, kept_at);
    wr32(image + kept_at, bus_long(image, be32(image + kept_at)));
}

/* The AES resource's three icons made the device's own ($fda262..$fda2b8): each BITBLK's address answered into
 * gem_main's local, the BITBLK copied to the AES's scratch one, and its bits transformed IN PLACE. */
static void transform_the_icons(uint8_t *image)
{
    uint32_t icon_local;
    int16_t index;

    for (index = 0; index < GEM_ICONS; index++) {
        uint32_t icon_slot = host_slot_claim(AES_GEM_MAIN_ICON, &icon_local);

        (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_BITBLK, index, icon_slot);
        host_slot_load_long(image, icon_slot, &icon_local);
        host_slot_release(AES_GEM_MAIN_ICON);
        aes_lbcopy(image, AES_BI, icon_local, BI_BYTES);
        (void)aes_gsx_trans(image, be32(image + AES_BI + BI_PDATA), (int16_t)be16(image + AES_BI + BI_WB),
                            be32(image + AES_BI + BI_PDATA), (int16_t)be16(image + AES_BI + BI_WB),
                            (int16_t)be16(image + AES_BI + BI_HL));
    }
}

/* The tick's routine exchanged with the VDI's ($fda2c2..$fda2da, $fda3ac..$fda3c4), the interrupts masked round it:
 * `routine` handed vex_timv, the one it displaces kept in AES_TICK_CHAIN, the tick's milliseconds in AES_GL_TICK_MS. */
static void exchange_the_tick(uint8_t *image, uint32_t routine)
{
    aes_spl7_save(image);
    wr16(image + AES_GL_TICK_MS, aes_gsx_tick(image, routine, AES_TICK_CHAIN));
    aes_spl_restore(image);
}

/* The launch band sized to the screen ($fda304..$fda38c): the tree's address read once; its three first objects as
 * wide as the screen (cells across by a cell's width, a signed word product's low word); the root as high (cells
 * down by a cell's height), the bar and the text a cell's height and a little. */
static void size_the_band(uint8_t *image)
{
    uint32_t tree;
    int16_t object;

    (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_TREE, GEM_BAND_TREE, AES_AD_STDESK);
    tree = be32(image + AES_AD_STDESK);
    for (object = 0; object < GEM_BAND_WIDE_OBJECTS; object++)
        set_bus_word(image, table_entry(tree, object, OB_BYTES) + OB_WIDTH,
                     (uint16_t)m68k_muls_w(be16(image + AES_GL_WCHAR), be16(image + AES_GL_NCOLS)));
    set_bus_word(image, tree + OB_HEIGHT, (uint16_t)m68k_muls_w(be16(image + AES_GL_HCHAR), be16(image + AES_GL_NROWS)));
    set_bus_word(image, tree + GEM_BAND_BAR * OB_BYTES + OB_HEIGHT, (uint16_t)(be16(image + AES_GL_HCHAR) + GEM_BAND_BAR_EXTRA));
    set_bus_word(image, tree + GEM_BAND_TEXT * OB_BYTES + OB_HEIGHT, (uint16_t)(be16(image + AES_GL_HCHAR) + GEM_BAND_TEXT_EXTRA));
}

/* GEM BROUGHT UP, from the interrupts let in to the last turn before the shell ($fda1d0..$fda396). NOT INLINED on
 * target, for `lay_the_processes`' reason. */
static __attribute__((noinline)) void bring_gem_up(uint8_t *image)
{
    uint32_t screen_manager;

    every_interrupt_let_in();
    screen_manager = aes_ictlmgr(image, (int16_t)bus_word(image, be32(image + AES_RLR) + PD_PID));
    wr32(image + AES_CTL_PD, screen_manager);
    wr32(image + AES_GL_KOWNER, screen_manager);
    wr32(image + AES_GL_MOWNER, screen_manager);
    (void)aes_gem_read_inf(image);
    (void)aes_rom_ram(image, ROM_RSC_AES, be32(image + AES_RS_SYSTEM_GLOBAL), GEM_ROM_RAM_NO_SIZE);
    take_a_mouse_form(image, GEM_ARROW_IMAGE, AES_AD_ARMICE);
    take_a_mouse_form(image, GEM_HOURGLASS_IMAGE, AES_AD_HGMICE);
    aes_ldaccs(image);
    (void)aes_set_defdrv(image);
    wr16(image + AES_GL_BDESIRED, 0);
    wr16(image + AES_GL_BTRUE, 0);
    wr16(image + AES_GL_CLICK_TICKS, 0);
    wr16(image + AES_GL_BCLICK, 0);
    aes_gsx_init(image);
    transform_the_icons(image);
    aes_spl7_save(image);
    (void)aes_takeerr(image);
    aes_spl_restore(image);
    (void)aes_sh_tographic(image);
    exchange_the_tick(image, be32(image + AES_TICK_ROUTINE));
    (void)aes_ev_dclick(image, GEM_DCLICK_RATE, GEM_DCLICK_SET);
    if (!be16(image + AES_RSC_AES_FRESH)) {
        (void)aes_rs_fixit(image, be32(image + AES_RS_SYSTEM_GLOBAL));
        wr16(image + AES_RSC_AES_FRESH, AES_RSC_AES_FIXED);
    }
    aes_wm_start(image);
    aes_fs_start(image);
    size_the_band(image);
    image[AES_INDISP] = 0;
    aes_dsptch(image);
    aes_all_run(image);
}

/* ...AND TAKEN DOWN, in the ROM's order ($fda39a..$fda3d2): the save buffer; the critical-error handler given back;
 * the AES's resource; the accessories; the VDI's own tick put back (the one kept is handed in, and kept again); the
 * workstation closed, the screen left for text; `trap #2` given back. Each vector under a mask of its own. */
static __attribute__((noinline)) void take_gem_down(uint8_t *image)
{
    aes_gsx_mfree(image);
    aes_spl7_save(image);
    (void)aes_giveerr(image);
    aes_spl_restore(image);
    (void)aes_rs_free(image, be32(image + AES_RS_SYSTEM_GLOBAL));
    aes_free_accs(image);
    exchange_the_tick(image, be32(image + AES_TICK_CHAIN));
    aes_gsx_wsclose(image);
    aes_gsx_escapes(image, GEM_ESCAPE_EXIT_ALPHA);
    aes_spl7_save(image);
    aes_restore_trap2(image);
    aes_spl_restore(image);
}

/* $fda062 — gem_main, over `image` (`aes/geminit.h`). THE SHELL RUNS UNDER THIS FRAME FOR THE WHOLE SESSION — the
 * desk and every program it starts stack below it, on UDA0 — so the three stretches round it are routines of their
 * own, whose frames are gone before it is called and after it returns: what is left here is the image base alone. */
static inline void gem_main(uint8_t *image)
{
    lay_the_processes(image);
    bring_gem_up(image);
    aes_sh_main(image);
    take_gem_down(image);
}

#ifdef RECREATE_HOST_DIFFERENTIAL
void aes_gem_main(uint8_t *image)
{
    gem_main(image);
}

/* The first stretch as a call of its own (`aes/geminit.h`): what a case holds to the ROM's own boot run between
 * gem_main's entry and its `sti`. */
void aes_gem_main_lays_the_processes(uint8_t *image)
{
    lay_the_processes(image);
}
#else
/* ...and on target, entered by gem_entry's `jsr` with nothing: the image base through a register GCC cannot see into
 * (`staged_call.h`'s `target_image`: a pushed 0 and a thunk would be eight bytes under the shell, for good).
 * `no-defer-pop` (`stack_diet.h`): the shell is called with nothing of the stretch before it left on the stack. */
FRAME_DIET("no-defer-pop")
void aes_rom_gem_main(void)
{
    gem_main(target_image());
}
#endif
