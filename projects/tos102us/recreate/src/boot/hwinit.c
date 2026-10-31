/* BOOT B3 — the BIOS's hardware init `$fc2408`, and the boot's stretch around its call, [$fc03b6, $fc03e0).
 *
 * The boot calls the init once (`bsr $fc2408`, after the vectors and system variables: B2), and nothing else does: it
 * puts every chip the BIOS drives into its working state and lays the RAM the drivers keep. In the ROM's order:
 *
 *   $fc2408  the MFP: `movep.l` of zero over GPIP..IERA, IERB..ISRA, ISRB..VR — every interrupt off, nothing pending,
 *            nothing in service, all GPIP lines inputs; VR := $48; `bset #2` in the AER (CTS interrupts rising)
 *   $fc2428  the timer C divider $1111, timr_ms 20; timer C programmed to 200 Hz, its handler on channel 5 ($114)
 *   $fc244c  timer D programmed (the USART's 9600 baud); `movep.l` SCR, UCR, RSR, TSR := 0, $88, 1, 1
 *   $fc2460  port A's DTR (`$fc2ed8`, Offgibit's body) and RTS (`$fc28ae`) dropped
 *   $fc2468  the RS232 and MIDI IOREC records from the ROM's templates; KBDVECS' two error vectors, midivec, midisys,
 *            ikbdsys; the MIDI 6850 reset and configured
 *   $fc24be  conterm 7; clockvec, statvec, mousevec, joyvec; the sound list and its two bytes, the printer's time-out
 *            stamp cleared; the printer strobe high (`$fc20f8`, Ongibit's body); the key repeat 15 / 2; the IKBD IOREC
 *            record; Bioskeys; the IKBD 6850 reset and configured
 *   $fc2522  the RS232's four handlers on channels 12..9 (from the ROM's table), the ACIAs' on 6 ($118), CTS's on 2
 *
 * EVERY HANDLER IS INSTALLED THROUGH `Mfpint`'s BODY (`mfp_install_vector_and_enable`, `$fc2666`): the channel
 * disabled, its vector stored, the channel enabled — the ordered MFP ledger is that body's, seven times. The timer C and
 * ACIA handlers are OURS on target (`BOOT_LINKED_ENTRY`: `src/bios/isr.S`'s entries, the ROM's own instructions,
 * byte-pinned) — CLOSING "NO BUILD STORES AN ENTRY IN ITS VECTOR" FOR `$114` / `$118`; the RS232's five are the ROM's
 * (read off its table, or stored by value: CODE obligations, the RS232 interrupt group is unported), as are KBDVECS'
 * routines (the C twins of the ACIA chain are not ROM-ABI entries).
 *
 * THE MFP's READ-BACKS ARE THE DECLARED MAP's (`test/mfp.py`): the AER's `bset`, the timer programmer's write-and-verify
 * of the timer C data register (`$fc260e`, where a boot with nothing declared spins) and its control-register OR, and
 * `Mfpint`'s enable half re-reading what its disable half cleared — every one a register the 68901 latches.
 *
 * `movep.l` HAS NO C FORM (`Rsconf`'s precedent): it is the four byte stores it makes, high byte first, two bytes apart.
 */
#include <stdint.h>

#include "hw.h"
#include "ipl.h"
#include "psg.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "addrs.h"
#include "boot/hwinit.h"
#include "boot/sysvars.h"
#include "xbios/ikbd.h"
#include "xbios/mfp.h"
#include "xbios/xbios.h"

/* `movep.l d0,d16(a0)`: a longword's four bytes to four MFP registers, high byte first, `MFP_REGISTER_STEP` apart. The
 * four are ordered statements: the ordered write ledger compares them. */
static void mfp_movep_long(uint32_t first, uint32_t value)
{
    hw_write8(first, (uint8_t)(value >> 24));
    hw_write8(first + MFP_REGISTER_STEP, (uint8_t)(value >> 16));
    hw_write8(first + 2 * MFP_REGISTER_STEP, (uint8_t)(value >> 8));
    hw_write8(first + 3 * MFP_REGISTER_STEP, (uint8_t)value);
}

/* `$fc255a` — `move.b (a1)+,(a0)+` under `dbf`: a template out of the ROM into RAM. Every template and destination is
 * even and its length even, so the copy moves words (RAM alone: the store order is no surface); the loop closes on
 * `dbf` (`COUNT_BARRIER` / `CURSOR_BARRIER`: `machine.h`). */
static void copy_template(uint8_t *to, const uint8_t *from, int16_t bytes)
{
    int16_t count = bytes / M68K_WORD_BYTES;

    COUNT_BARRIER(count);
    CURSOR_BARRIER(from);
    CURSOR_BARRIER(to);
    for (count--; count >= 0; count--) {
        wr16(to, be16(from));
        to += M68K_WORD_BYTES;
        from += M68K_WORD_BYTES;
    }
}

/* `$fc28ae` — the RS232's RTS dropped: port A bit 3 cleared by a DIRECT read-modify-write of the PSG (select 14, read,
 * store the data port), under its own interrupt bracket. */
static void rs232_rts_clear(void)
{
    os_ipl_t mask = os_ipl_raise();

    psg_port_write(PSG_PORT_A, (uint8_t)(psg_port_read(PSG_PORT_A) & ~PSG_PORT_A_RTS));
    os_ipl_restore(mask);
}

/* $fc2408 — entered with A5 = 0 (the boot's), the image's base. */
void bios_hardware_init(uint8_t *image)
{
    int16_t handler;

    mfp_movep_long(MFP_GPIP, 0);
    mfp_movep_long(MFP_IERB, 0);
    mfp_movep_long(MFP_ISRB, 0);
    hw_write8(MFP_VR, HWINIT_MFP_VECTOR_BASE);
    mfp_set_bit(MFP_AER, MFP_AER_CTS_BIT);

    wr16(image + SYSVAR_TIMER_C_DIVIDER, HWINIT_TIMER_C_DIVIDER);
    wr16(image + SYSVAR_TIMR_MS, HWINIT_TIMR_MS);
    mfp_timer_program(image, MFP_TIMER_C, HWINIT_TIMER_C_CONTROL, HWINIT_TIMER_C_DATA);
    mfp_install_vector_and_enable(image, MFP_CHANNEL_TIMER_C, BOOT_LINKED_ENTRY(ISR_TIMER_C, isr_timer_c_entry));
    mfp_timer_program(image, MFP_TIMER_D, HWINIT_TIMER_D_CONTROL, HWINIT_TIMER_D_DATA);
    mfp_movep_long(MFP_SCR, HWINIT_USART);
    (void)xbios_offgibit(HWINIT_UNREAD_D0, PORT_A_DTR_CLEAR_MASK);
    rs232_rts_clear();

    copy_template(image + IOREC_RS232, image + ROM_IOREC_RS232_TEMPLATE, IOREC_RS232_TEMPLATE_BYTES);
    copy_template(image + IOREC_MIDI, image + ROM_IOREC_MIDI_TEMPLATE, IOREC_TEMPLATE_BYTES);
    wr32(image + KBDVECS + KBDVECS_VKBDERR, ACIA_SERVICE_RTS);
    wr32(image + KBDVECS + KBDVECS_VMIDERR, ACIA_SERVICE_RTS);
    wr32(image + KBDVECS + KBDVECS_MIDIVEC, MIDI_QUEUE_BYTE);
    wr32(image + KBDVECS + KBDVECS_MIDISYS, MIDI_ACIA_SERVICE);
    wr32(image + KBDVECS + KBDVECS_IKBDSYS, IKBD_ACIA_SERVICE);
    hw_write8(MIDI_ACIA_STATUS, ACIA_MASTER_RESET);
    hw_write8(MIDI_ACIA_STATUS, MIDI_ACIA_CONFIGURATION);

    image[SYSVAR_CONTERM] = HWINIT_CONTERM;
    wr32(image + KBDVECS + KBDVECS_CLOCKVEC, ROM_IKBD_CLOCK_PACKET);
    wr32(image + KBDVECS + KBDVECS_STATVEC, ROM_HWINIT_RTS);
    wr32(image + KBDVECS + KBDVECS_MOUSEVEC, ROM_HWINIT_RTS);
    wr32(image + KBDVECS + KBDVECS_JOYVEC, ROM_HWINIT_RTS);
    wr32(image + SOUND_LIST_POINTER, 0);
    image[SOUND_LIST_DELAY] = 0;
    image[SOUND_RAMP_VALUE] = 0;
    wr32(image + PRINTER_RETRY_AT, 0);
    (void)xbios_ongibit(HWINIT_UNREAD_D0, PRINTER_STROBE_SET_MASK);
    image[KBRATE_DELAY] = HWINIT_KBRATE_DELAY;
    image[KBRATE_REPEAT] = HWINIT_KBRATE_REPEAT;
    copy_template(image + IOREC_IKBD, image + ROM_IOREC_IKBD_TEMPLATE, IOREC_TEMPLATE_BYTES);
    xbios_bioskeys(image);
    hw_write8(IKBD_ACIA_STATUS, ACIA_MASTER_RESET);
    hw_write8(IKBD_ACIA_STATUS, IKBD_ACIA_CONFIGURATION);

    for (handler = RS232_HANDLERS - 1; handler >= 0; handler--)
        mfp_install_vector_and_enable(image, MFP_CHANNEL_RS232_FIRST + handler,
                                      be32(image + ROM_RS232_HANDLER_TABLE + handler * M68K_LONG_BYTES));
    mfp_install_vector_and_enable(image, MFP_CHANNEL_ACIA, BOOT_LINKED_ENTRY(ISR_ACIA, isr_acia_entry));
    mfp_install_vector_and_enable(image, MFP_CHANNEL_RS232_CTS, ROM_RS232_CTS_HANDLER);
}

/* [$fc03ba, $fc03da) — after the init's return: the IKBD's reset command (Ikbdws: `$80 $01`, read where it lies) and the
 * pause the 6301 is owed after it. The init's call before it, the cartridge's hook 2 and the way on after it are the
 * entry's (`src/boot/hwinit_entry.S`). */
void boot_ikbd_reset(uint8_t *image)
{
    ikbd_send_string(image, IKBD_RESET_COMMAND_COUNT, ROM_IKBD_RESET_COMMAND);
    rts_delay(BOOT_IKBD_RESET_DBF_COUNT);
}
