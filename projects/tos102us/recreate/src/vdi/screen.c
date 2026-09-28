/* screen.c — the SCREEN AND WORKSTATION PLUMBING: the screen clear, the resolution the physical workstation
 * opens in, and the timer tick and mouse it takes over from the BIOS and gives back (`vdi/screen.h`).
 *
 * ALL HAND 68000, and all reached from the workstation layer rather than by opcode — bar v_clrwk, which is
 * both opcode 3 and the tail every other routine here ends in, and the BIOS's span clear it is a call of.
 * What they call is other layers' and is called BY NAME: the BIOS's cursor lock (`src/bios/vt52.c`),
 * mouse_init and mouse_off (`src/vdi/mouse.c`), and four traps — BIOS `Setexc` and XBIOS `Getrez`,
 * `Setscreen` and `Setpalette` — each taken through the machine's own `trap` on target and its core called
 * directly off it, as `src/vdi/mouse.c`'s Initmous is.
 *
 * WHAT IS NOT RECONSTRUCTED BEHIND THEM: setres's two arms that CHANGE the resolution. Both call
 * `Setscreen(-1, -1, mode)` with a mode the shifter is not in, and XBIOS Setscreen's resolution arm is the
 * console re-initialisation at $fca914, which halts (`src/xbios/setscreen.c` says why). So a colour machine
 * asked for medium in low, or for anything but 1 and 3 in medium, halts inside Setscreen — before it has
 * stored a byte — and every arm that keeps the mode it finds runs whole.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "ipl.h"
#include "staged_call.h"
#include "bios/bcon.h"
#include "bios/vt52.h"
#include "m68k_idioms.h"
#include "xbios/xbios.h"
#include "vdi/vdi.h"
#include "vdi/mouse.h"
#include "vdi/screen.h"
#include "vdi/transcribed.h"

_Static_assert(VDI_TIMER_VECTOR * VECTOR_BYTES == SYSVAR_ETV_TIMER, "Setexc's number is not etv_timer's slot");

/* ================================================================================================
 * The four traps, each the ROM's own on target (`bios/bcon.h`'s and `xbios/xbios.h`'s helpers, which push
 * the ROM's frames) and its core off it.
 * ============================================================================================= */

/* What `Setscreen` is told for an address it is to leave alone (`moveq #-1,d0 / move.l d0,-(sp)` twice). */
#define SETSCREEN_KEEP_ADDRESS 0xffffffffu
/* The D0 a direct call hands the XBIOS cores for the dispatcher's: both results are discarded, so any
 * value serves, and none is observed. */
#define XBIOS_RESULT_DISCARDED 0

/* Setexc(vector, handler) — `move.l <handler>,-(sp) / move.w #vector,-(sp) / move.w #5,-(sp) / trap #13`. */
static uint32_t setexc(uint8_t *image, uint16_t vector, uint32_t handler)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_setexc(image, vector, handler);
#else
    (void)image;
    return bios_trap_vector(BIOS_SETEXC_FN, vector, handler);
#endif
}

/* Only the low BYTE is kept (`move.b d0,d2`): every test below is a byte compare. */
static uint8_t getrez(void)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return xbios_getrez();
#else
    return (uint8_t)xbios_trap_plain(XBIOS_GETREZ_FN);
#endif
}

/* Setscreen(-1, -1, mode): the resolution alone — which halts inside Setscreen (this file's header). */
static void setscreen_mode(uint8_t *image, uint16_t mode)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    (void)xbios_setscreen(image, XBIOS_RESULT_DISCARDED, SETSCREEN_KEEP_ADDRESS, SETSCREEN_KEEP_ADDRESS, mode);
#else
    (void)image;
    xbios_trap_long_long_word(XBIOS_SETSCREEN_FN, SETSCREEN_KEEP_ADDRESS, SETSCREEN_KEEP_ADDRESS, mode);
#endif
}

static void setpalette(uint8_t *image, uint32_t palette)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    (void)xbios_setpalette(image, XBIOS_RESULT_DISCARDED, palette);
#else
    (void)image;
    (void)xbios_trap_long(XBIOS_SETPALETTE_FN, palette);
#endif
}

/* ================================================================================================
 * $fc4b7c, the BIOS's span clear — v_clrwk's whole body, and the end of GEMDOS's program loader.
 * ============================================================================================= */

/* The BIOS's own `bzero(from, to)` — hand assembly, reached by `jsr` with two longwords (Alcyon's frame)
 * from v_clrwk ($fca666) and from `Pexec`'s loader (`src/gemdos/pexec_load.c`). Named in the VDI's block
 * because the transcription table is the VDI's (`vdi/transcribed.h`): the target ships `screen.S`, the
 * ROM's own `movem` loop, which this C measures at nearly four times the cost of. Its three steps are the
 * three below: one byte if `from` is odd, then the whole 256-byte blocks — eight `movem.l` of eight zero
 * registers, DOWNWARDS from the top of the blocks, which leaves the same bytes as upwards — then single
 * bytes up to `to`.
 *
 * THE ODD BYTE AND THE BLOCK SIZE ARE THE 68000'S, not the result's: any split of the span clears the
 * same bytes, in any order, so no image compare can tell them apart (the mutation sweep records both as
 * equivalent). What the odd byte buys on target is alignment — a longword store at an odd address is an
 * address error — and what the blocks buy is speed. Each longword goes through `wr32`, the image's own
 * accessor — one `move.l` on target, four byte stores on the host, whose image is a byte array with no
 * longword alignment to rely on.
 *
 * THE COUNTING IS 32 BITS AND THE STORES ARE 24: `from`, `to` and their difference are whole registers,
 * and the bus drops the top byte of every address a store drives — so a `_v_bas_ad` of $ff0f8000 clears
 * the screen at $0f8000 (`span_bytes`).
 *
 * `to` IS COMPARED FOR EQUALITY, never order: a span whose odd first byte already reaches `to` steps
 * past it, and a `to` BELOW `from` makes the block count a huge unsigned one — either way the clear runs
 * on through the address space. Transcribed. The loader reaches the second: TEXT+DATA longer than the
 * TPA leave a NEGATIVE room, a header BSS length of $80000000 or more is negative too and passes the
 * SIGNED check against it, and the loader then reads TEXT past `p_hitpa`, asks `Fread` for a ~4 GB
 * relocation chunk, and hands this a span that ends below where it starts. Not staged — on the machine it
 * clears RAM below the TPA until something faults — and on the host `span_bytes` aborts before the first
 * block is stored (test_vdi_screen.py pins the abort). */
#define CLEAR_LONG_BYTES     4                  /* `movem.l` of zero registers: a longword each */

/* `width` bytes at the address the bus drives for `at`. HOST-ONLY bound, the kit's way (kit.mk: "asserted
 * where there is a process to abort"). Spelt without the sum `driven + width`, which wraps in 32 bits for
 * the near-4 GB block count a `to` below `from` makes — and would pass. */
static uint8_t *span_bytes(uint8_t *image, uint32_t at, uint32_t width)
{
    uint32_t driven = bus_address(at);

#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(width <= ST_RAM_BYTES && driven <= ST_RAM_BYTES - width);
#else
    (void)width;
#endif
    return image + driven;
}

TRANSCRIBED_CORE
void vdi_clear_span(uint8_t *image, uint32_t from, uint32_t to)
{
    uint32_t blocks;

    if (from & 1)
        *span_bytes(image, from++, 1) = 0;
    blocks = (to - from) & VDI_CLEAR_BLOCK_MASK;
    if (blocks != 0) {
        uint8_t *longs = span_bytes(image, from, blocks);
        uint32_t count;

        for (count = blocks / CLEAR_LONG_BYTES; count != 0; count--, longs += CLEAR_LONG_BYTES)
            wr32(longs, 0);
        from += blocks;
    }
    while (from != to)
        *span_bytes(image, from++, 1) = 0;
}

/* ================================================================================================
 * The routines.
 * ============================================================================================= */

/* $fca654 — v_clrwk (3): the whole screen zeroed through the BIOS's span clear. `_v_bas_ad` is read twice,
 * the end first (`move.l $44e,-(sp) / addi.l #32000,(sp)` then the start) — nothing between the two reads
 * writes it, so one read is the same function. The sum is a LONGWORD add, unwrapped. */
void vdi_v_clrwk(uint8_t *image)
{
    uint32_t base = be32(image + SYSVAR_V_BAS_AD);

    vdi_clear_span(image, base, base + VDI_SCREEN_BYTES);
}

/* The two palettes and what each answers, which setres's five arms end in. */
static uint32_t open_low(uint8_t *image)
{
    setpalette(image, VDI_PALETTE_LOW);
    return VDI_SETRES_ANSWER_LOW;
}

static uint32_t open_medium(uint8_t *image)
{
    setpalette(image, VDI_PALETTE_MEDIUM);
    return VDI_SETRES_ANSWER_MEDIUM;
}

/* $fca6d4 — setres: the mode v_opnwk's intin[0] asks for, the shifter switched into it if it is not
 * there already, its palette queued for the next blank, and the mode plus one answered.
 *
 * THE MODE IS READ BEFORE THE ASK, and a mono machine never reads the ask at all. What a colour machine is
 * asked is ONE word compared with 1 and with 3; anything else is low — so `intin[0] = 4`, GEM's "high", on
 * a colour machine opens LOW. A shifter byte of mode 3 (no such mode, but Getrez masks two bits) is
 * "not low" to the current-mode arm and "not medium" to the medium one. */
uint32_t vdi_setres(uint8_t *image)
{
    uint8_t mode = getrez();
    int16_t asked;

    if (mode == SHIFTER_MODE_HIGH) {
        setpalette(image, VDI_PALETTE_MEDIUM);
        return VDI_SETRES_ANSWER_HIGH;
    }
    asked = intin_word(image, 0);
    if (asked == VDI_SETRES_DEVICE_CURRENT)
        return mode == SHIFTER_MODE_LOW ? open_low(image) : open_medium(image);
    if (asked == VDI_SETRES_DEVICE_MEDIUM) {
        if (mode != SHIFTER_MODE_MEDIUM)
            setscreen_mode(image, SHIFTER_MODE_MEDIUM);
        return open_medium(image);
    }
    if (mode != SHIFTER_MODE_LOW)
        setscreen_mode(image, SHIFTER_MODE_LOW);
    return open_low(image);
}

/* $fca670 — init_timer_mouse: USER_TIM at its default (the bare `rts` of VDI_ROM_NOP), the VDI's tick
 * installed as etv_timer with the handler it displaces kept in NEXT_TIM — the exchange made with interrupts
 * MASKED, since timer C calls through that vector — then the mouse on, the console's cursor locked off,
 * and the screen cleared (`bra v_clrwk`). */
void vdi_init_timer_mouse(uint8_t *image)
{
    os_ipl_t mask;

    wr32(image + LINEA_USER_TIM, VDI_ROM_NOP);
    mask = os_ipl_raise();
    wr32(image + LINEA_NEXT_TIM, setexc(image, VDI_TIMER_VECTOR, VDI_ROM_TIMER_TICK));
    os_ipl_restore(mask);
    vdi_mouse_init(image);
    console_hide_cursor(image);
    vdi_v_clrwk(image);
}

/* $fca78a — timer_tick, the etv_timer handler: USER_TIM called, then the handler it displaced chained to
 * with the tick word still under the return address.
 *
 * NEXT_TIM IS READ AFTER USER_TIM RETURNS, so a user routine that repoints it is chained through the new
 * value. What the ROM does and this cannot spell from C is the CHAIN itself: `movem.l (sp)+,d0-a6 /
 * move.l NEXT_TIM,-(sp) / rts` enters the old handler with the caller's own registers and return address,
 * where this calls it — pushing the tick word again — and comes back. So the SHIPPED build takes the ROM's
 * own entry (`screen.S`, `vdi/transcribed.h`): etv_timer holds that entry's address, and timer C enters it
 * with its convention, which a C function of `(image, tick)` does not have. This twin is what Tier 1 proves
 * the order against; the handler it calls reads the same word at 4(sp), and only one that read a register
 * timer C left, or looked past its own frame, could tell the two apart. */
TRANSCRIBED_CORE
void vdi_timer_tick(uint8_t *image, int16_t tick_ms)
{
    call_vector(image, be32(image + LINEA_USER_TIM));
    call_vector_word(image, be32(image + LINEA_NEXT_TIM), (uint16_t)tick_ms);
}

/* $fca7a2 — restore_timer_mouse: etv_timer given back — UNMASKED, where the install masked — then the
 * mouse off, the screen cleared, and the console's cursor forced back on (`bra $fc45be`, the BIOS's
 * `ESC e`). Setexc's answer is dropped; a NEXT_TIM with bit 31 set makes it a read, and leaves the VDI's
 * tick installed. */
void vdi_restore_timer_mouse(uint8_t *image)
{
    (void)setexc(image, VDI_TIMER_VECTOR, be32(image + LINEA_NEXT_TIM));
    vdi_mouse_off(image);
    vdi_v_clrwk(image);
    console_show_cursor(image);
}
