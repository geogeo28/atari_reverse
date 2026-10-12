/* shell.c — THE SHELL'S LOOP (`aes/shell.h`): sh_main and sh_cmd. Alcyon C in the ROM, ported over its own order:
 * every flag is read back from memory where the ROM's absolute accesses read it, since the desk, a built-in and a
 * launched program each change them under the loop.
 *
 * WHAT IS NOT OURS is reached through THE DESK DOOR (`aes/deskdoor.h`): deskmain and the desk's four built-ins — the
 * ROM's own routines until band 6, one `jsr` each on target, the case's hook off it — and dos_exec, ours, which the
 * door enters with the stack pointer where the ROM's stands. The cartridge's launch (`$fed5c2`) is not reconstructed
 * (ruling W4-R12): its arm halts by name.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/deskdoor.h"
#include "aes/deskmem.h"
#include "aes/evasync.h"
#include "aes/fmdo.h"
#include "aes/gemdosif.h"
#include "aes/geminit.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/objects.h"
#include "aes/shell.h"
#include "aes/shlib.h"
#include "aes/strings.h"
#include "aes/trp14.h"
#include "aes/wmlib.h"

_Static_assert(AES_SH_COMMAND == AES_THEGLO + SH_TAIL_IN_THEGLO, "the tail's first byte ($feb198 move.b d0,10198(a5))");
_Static_assert(SH_BAND_TEXT_SPEC == SH_BAND_TEXT_OBJECT * OB_BYTES + OB_SPEC, "the band's text object's ob_spec ($feb0fc)");

#ifdef RECREATE_HOST_DIFFERENTIAL
uint32_t (*recreate_call_desk_door)(uint8_t *image, uint32_t routine, uint32_t first, uint32_t second);
#else
/* sh_show's ENTRY for sh_find's `jsr (a0)` over the path found — one longword, which is a C frame of one argument —
 * with the target's image base handed through a register GCC cannot see into (`staged_call.h`'s `target_image`). */
static void sh_show_entry(uint32_t command)
{
    aes_sh_show(target_image(), command);
}
#endif

/* What sh_main hands sh_find to show the path it found ($feb272 move.l #$feaddc,(sp)): off target the ROM's address,
 * the hook's key; on target the entry above. */
static inline uint32_t sh_show_routine(void)
{
    return ALCYON_ROUTINE(AES_ROM_SH_SHOW, sh_show_entry);
}

/* The launch band drawn whole with the command line ($feb19c, $feb240 and sh_cmd's three: sh_draw(command, 0, 1)). */
static void draw_the_band(uint8_t *image)
{
    aes_sh_draw(image, be32(image + AES_SHELL_BUFFER), OB_ROOT, SH_BAND_DEPTH);
}

/* ================================================================================================
 * sh_cmd.
 * ============================================================================================= */

/* $feb2fc — sh_cmd: the tail's first byte as one of the desk's four built-ins, each handed the text behind it — 1;
 * any other byte — 0, and the tail is a program's. `$fd` first makes the command line "PRINTING  " and the name. */
FRAME_DIET("no-defer-pop", "no-gcse")
int16_t aes_sh_cmd(uint8_t *image)
{
    switch (image[AES_SH_COMMAND]) {
    case SH_CMD_SHOW:
        desk_door_file(image, AES_ROM_DESK_SHOW_FILE, AES_SH_TAIL_TEXT);
        return SH_CMD_RAN;
    case SH_CMD_PRINT:
        (void)aes_strcpy(image, AES_SH_PRINTING_TEXT, be32(image + AES_SHELL_BUFFER));
        (void)aes_strcat(image, AES_SH_TAIL_TEXT, be32(image + AES_SHELL_BUFFER));
        draw_the_band(image);
        desk_door_file(image, AES_ROM_DESK_PRINT_FILE, AES_SH_TAIL_TEXT);
        return SH_CMD_RAN;
    case SH_CMD_FORMAT:
        draw_the_band(image);
        desk_door_disk(image, AES_ROM_DESK_FORMAT, AES_SH_TAIL_TEXT, be32(image + AES_SHELL_BUFFER));
        return SH_CMD_RAN;
    case SH_CMD_COPY:
        draw_the_band(image);
        desk_door_disk(image, AES_ROM_DESK_COPY_DISK, AES_SH_TAIL_TEXT, be32(image + AES_SHELL_BUFFER));
        return SH_CMD_RAN;
    default:
        return SH_CMD_NONE;
    }
}

/* ================================================================================================
 * sh_main.
 *
 * ITS FRAME LIES UNDER EVERY FRAME OF THE DESK for the whole session, and the door halts a build whose own runs
 * deeper than the ROM's (`aes/deskdoor.h`: 26 bytes under sh_main's return address, and sh_cmd's 14 more under its
 * own). So sh_main's body is its loop and its calls through the door — deskmain, dos_exec, and sh_cmd for the four
 * built-ins — and nothing else: each step round them is a routine of its own (NOT INLINED: a step inlined brings its
 * registers into sh_main's frame — eleven saved where the whole loop was one body), and the two entries carry the
 * frame diet's marks (`stack_diet.h`) for what -O2 would otherwise keep in registers across the loop.
 * ============================================================================================= */
#define A_STEP static __attribute__((noinline))

/* The screen as the next program needs it ($feb130..$feb184): a launch the desk did not qualify (AES_SH_ISDEF still
 * set) is GEM's; the workstation switched only where that changes; and the windows and the mouse set up afresh
 * whenever the screen is GEM's. AES_SH_ISDEF_SEEN is stored and read by nothing. */
static void set_the_screen(uint8_t *image)
{
    wr16(image + AES_SH_ISDEF_SEEN, 0);
    if (be16(image + AES_SH_ISDEF)) {
        wr16(image + AES_SH_ISGEM, 1);
        wr16(image + AES_SH_ISDEF_SEEN, 1);
    }
    wr16(image + AES_SH_ISDEF, 1);
    if (be16(image + AES_SH_ISGEM) != be16(image + AES_GL_SHGEM)) {
        wr16(image + AES_GL_SHGEM, be16(image + AES_SH_ISGEM));
        if (be16(image + AES_GL_SHGEM))
            (void)aes_sh_tographic(image);
        else
            (void)aes_sh_toalpha(image);
    }
    if (be16(image + AES_GL_SHGEM)) {
        aes_wm_start(image);
        aes_ratinit(image);
    }
}

/* The cartridge's program ($feb186..$feb1ce), where the desk asked for one: the tail's length byte made of its
 * text, the band drawn — and cart_exec, NOT RECONSTRUCTED: no machine here has a cartridge and the routine is the
 * cartridge slice's (ruling W4-R12), so the arm halts by name on both builds where the ROM would call it. */
static void run_a_cartridge_s_program_if_asked(uint8_t *image)
{
    if (!be16(image + AES_SH_CART_LAUNCH))
        return;
    image[AES_SH_COMMAND] = (uint8_t)aes_strlen(image, AES_SH_TAIL_TEXT);
    draw_the_band(image);
    recreate_not_reconstructed("sh_main: the desk asked for a cartridge's program — cart_exec ($fed5c2) is not "
                               "reconstructed");
}

/* The desk has returned `answer` ($feb1de..$feb22a): the multi-click count it may have left is cleared — after EVERY
 * return —, its memory freed; the band's root made the colour desktop's unless the screen is monochrome (Getrez 2;
 * 4 is no mode of this machine's); and 0 ends the shell, anything else asks for what the shell's buffers now hold. */
A_STEP void after_the_desk(uint8_t *image, int16_t answer)
{
    int16_t resolution;

    wr16(image + AES_GL_BPEND, 0);
    aes_desk_free(image);
    resolution = (int16_t)aes_trp14(image, AES_SH_MAIN_GETREZ_RETURN, XBIOS_GETREZ_FN);
    if (resolution != SH_REZ_HIGH && resolution != SH_REZ_NONE_OF_THE_ST_S)
        set_bus_long(image, be32(image + AES_AD_STDESK) + OB_SPEC, SH_BAND_COLOUR_SPEC);
    if (answer)
        wr16(image + AES_SH_DODEF, 0);
    else
        wr16(image + AES_SH_DOEXEC, 0);
}

/* A program is to be run ($feb240..$feb29a, $feb2da): the band, the desk next whatever happens, the command looked
 * for — as given, at the root or down PATH, the path found shown in the band — and the process named after it. Not
 * found, fm_error says so (MS-DOS's error 2) and there is nothing to run. */
A_STEP int the_command_is_found(uint8_t *image)
{
    draw_the_band(image);
    wr16(image + AES_SH_DODEF, 1);
    if (!aes_sh_find(image, be32(image + AES_SHELL_BUFFER), sh_show_routine())) {
        (void)aes_fm_error(image, SH_ERROR_FILE_NOT_FOUND);
        return 0;
    }
    aes_pd_nameit(image, be32(image + AES_RLR), aes_sh_name(image, AES_SHELL_LINE));
    return 1;
}

/* What dos_exec's failure becomes ($feb2ae..$feb2d4, $feb25e): nothing unless the screen is GEM's and the glue's
 * word is below SH_LAUNCH_ERRORS_BELOW — then fm_error is handed the MS-DOS number of it, `~error - 30`. The word
 * is whatever Pexec answered, a program's own exit code included (`aes/gemdosif.h`). */
A_STEP void show_what_the_launch_left(uint8_t *image)
{
    int16_t error = (int16_t)be16(image + AES_DOS_AX);

    if (!be16(image + AES_GL_SHGEM) || !aes_dos_failed(image) || error >= SH_LAUNCH_ERRORS_BELOW)
        return;
    (void)aes_fm_error(image, (int16_t)(~error - SH_DOS_ERROR_BIAS));
}

/* What a pass runs. */
enum { THE_SHELL_ENDS, THE_DESK, A_COMMAND };

/* A PASS BEGINS ($feb130..$feb1da): the screen; a cartridge's program; then the desk, its memory taken — or a
 * command. NOTHING IS ASKED ANY MORE where AES_SH_DOEXEC is clear: the ROM tests it where a pass ends ($feb2f0) and
 * this where the next would begin — the same test, since sh_main sets the word before its first pass. */
A_STEP int a_pass_begins(uint8_t *image)
{
    if (!be16(image + AES_SH_DOEXEC))
        return THE_SHELL_ENDS;
    set_the_screen(image);
    run_a_cartridge_s_program_if_asked(image);
    if (!be16(image + AES_SH_DODEF))
        return A_COMMAND;
    aes_desk_alloc(image);
    return THE_DESK;
}

/* $feb0e6 — sh_main: the launch band's text object noted, every flag set for the desk — and then, until a pass
 * leaves nothing asked (AES_SH_DOEXEC), one of: a cartridge's program; the desk; a command the desk left — a
 * built-in of its own, which sh_cmd runs and which leaves the desk next ($feb22e..$feb23c), or a program. The desk
 * runs first, and again after anything else.
 *
 * THE ROM'S LAUNCH IS A LOOP ($feb258..$feb2ec) over two words of its frame — an error to show, and a retry nothing
 * sets — which runs the command once and, where that left an error, fm_error once: the two steps as they are here. */
FRAME_DIET("no-defer-pop", "no-function-cse", "no-move-loop-invariants")
void aes_sh_main(uint8_t *image)
{
    int pass;

    wr32(image + AES_AD_PFILE, bus_long(image, be32(image + AES_AD_STDESK) + SH_BAND_TEXT_SPEC));
    wr16(image + AES_SH_ISGEM, 1);
    wr16(image + AES_GL_SHGEM, 1);
    wr16(image + AES_SH_ISDEF, 1);
    wr16(image + AES_SH_DOEXEC, 1);
    wr16(image + AES_SH_DODEF, 1);
    while ((pass = a_pass_begins(image)) != THE_SHELL_ENDS) {
        if (pass == THE_DESK) {
            after_the_desk(image, desk_door_deskmain(image));
        } else if (aes_sh_cmd(image)) {
            wr16(image + AES_SH_DODEF, 1);
        } else if (the_command_is_found(image)) {
            desk_door_dos_exec(image, be32(image + AES_SHELL_BUFFER), SH_PEXEC_LOAD_AND_GO, be32(image + AES_SHELL_TAIL));
            show_what_the_launch_left(image);
        }
    }
}
