/* boot/hwinit.h — the names BOOT B3 is spelt in: the BIOS's hardware init `$fc2408` (`src/boot/hwinit.c`,
 * `bios_hardware_init`) and the boot's stretch around its call, [$fc03b6, $fc03e0) (`src/boot/hwinit_entry.S`, which
 * calls the init and then `boot_ikbd_reset`). The names that already exist stay in `addrs.h` (`MFP_IERB`, `IOREC_RS232`,
 * `KBDVECS_MIDISYS`, `SYSVAR_TIMER_C_DIVIDER`, ...).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`): `hwinit_entry.S` includes
 * it. The Python side reads it with `layouts.parse_constants` (`test/boot_hwinit.py`), so a value is spelt once. */
#ifndef TOS102US_BOOT_HWINIT_H
#define TOS102US_BOOT_HWINIT_H

/* ---- the MFP: three `movep.l` of zero over its first twelve registers, then the vector base --------------------- */
#define MFP_REGISTER_STEP         2          /* the 68901 lies on alternate (odd) bytes: `movep`'s stride */
#define HWINIT_MFP_VECTOR_BASE    0x48       /* VR: vectors $40..$4f (bits 7-4), SOFTWARE end-of-interrupt (bit 3) */
#define MFP_AER_CTS_BIT           2          /* `bset #2` in the AER: GPIP 2, the RS232's CTS, interrupts rising */

/* ---- the two timers it programs (the programmer `$fc25b0`: `mfp_timer_program`) --------------------------------- */
#define HWINIT_TIMER_C_CONTROL    0x50       /* timer C: the 2.4576 MHz clock divided by 64 ... */
#define HWINIT_TIMER_C_DATA       0xc0       /* ...and by 192: the 200 Hz system tick */
#define HWINIT_TIMER_D_CONTROL    0x01       /* timer D: divided by 4 ... */
#define HWINIT_TIMER_D_DATA       0x02       /* ...and by 2, its output toggling: the USART's clock, 9600 baud at / 16 */
#define HWINIT_TIMER_C_DIVIDER    0x1111     /* SYSVAR_TIMER_C_DIVIDER's first value: one bit in four, 50 Hz */
#define HWINIT_TIMR_MS            20         /* SYSVAR_TIMR_MS: the tick the 50 Hz body reports, in ms */

/* ---- the USART: one `movep.l #$00880101,38(a0)` — SCR, UCR, RSR, TSR in that order ------------------------------ */
#define HWINIT_USART              0x00880101 /* SCR 0; UCR $88 (clock / 16, 8 bits, 1 stop, no parity); RSR, TSR on */

/* ---- the MFP channels it installs a handler on, at MFP_VECTOR_TABLE + channel * 4 ------------------------------- */
#define MFP_CHANNEL_RS232_CTS     2          /* GPIP 2: the RS232's clear-to-send */
#define MFP_CHANNEL_TIMER_C       5          /* timer C: the system tick (VECTOR_TIMER_C) */
#define MFP_CHANNEL_ACIA          6          /* the two 6850s' shared line (VECTOR_ACIA) */
#define MFP_CHANNEL_RS232_FIRST   9          /* channels 9..12: the USART's transmit error, transmit empty, receive
                                              * error and receive full, ... */
#define RS232_HANDLERS            4          /* ...installed from the last down (`moveq #3,d1` + `dbf`) */

/* ---- the two 6850 ACIAs' control registers (the status registers' addresses: `addrs.h`) ------------------------- */
#define ACIA_MASTER_RESET         0x03       /* control bits 1-0 = 11: the chip reset, before it is configured */
#define MIDI_ACIA_CONFIGURATION   0x95       /* clock / 16 (31250 baud), 8 bits 1 stop, receive interrupt on */
#define IKBD_ACIA_CONFIGURATION   0x96       /* clock / 64 (7812.5 baud), 8 bits 1 stop, receive interrupt on */

/* ---- the PSG's port A: the two RS232 lines it drops, by the ROM's two read-modify-writes ------------------------- */
#define PORT_A_DTR_CLEAR_MASK     0xffef     /* `moveq #-17,d2` into Offgibit's body ($fc2ed8): bit 4, DTR, cleared */
#define PSG_PORT_A_RTS            0x08       /* `andi.b #$f7` ($fc28ae): bit 3, RTS, cleared */
#define HWINIT_UNREAD_D0          0          /* the D0 Offgibit / Ongibit hand back unchanged, which nothing reads */

/* ---- the system variables it lays (beside `addrs.h`'s) ------------------------------------------------------------ */
#define HWINIT_CONTERM            0x07       /* conterm: key click, key repeat, the bell on ^G */
#define HWINIT_KBRATE_DELAY       15         /* ticks before a held key repeats ... */
#define HWINIT_KBRATE_REPEAT      2          /* ...and between repeats */

/* ---- the ROM's own bytes it reads in place (TABLE obligations, D11 open: `test_boot_rom_data.py`) ---------------- */
#define ROM_IOREC_IKBD_TEMPLATE   0xfc2562   /* the IKBD ring's record, copied to IOREC_IKBD */
#define ROM_IOREC_MIDI_TEMPLATE   0xfc2570   /* the MIDI ring's, copied to IOREC_MIDI */
#define ROM_IOREC_RS232_TEMPLATE  0xfc257e   /* the RS232's input and output rings and their flow state, to IOREC_RS232 */
#define IOREC_TEMPLATE_BYTES      14         /* `moveq #13` + `dbf`: one ring's record */
#define IOREC_RS232_TEMPLATE_BYTES 34        /* `moveq #33` + `dbf`: two records and the six bytes after them */
#define ROM_RS232_HANDLER_TABLE   0xfc25a0   /* four longwords: the handlers of channels 9..12, in channel order */

/* ---- the ROM's code it stores by value where this build links none (CODE obligations) ----------------------------- */
#define ROM_RS232_CTS_HANDLER     0xfc27ae   /* channel 2's handler (unported: the RS232 interrupt group) */
#define ROM_IKBD_CLOCK_PACKET     0xfc1f08   /* KBDVECS' clockvec: the $fc time-of-day packet (unported) */
#define ROM_HWINIT_RTS            0xfc2558   /* this routine's own `rts`: statvec, mousevec and joyvec, idle */

/* ---- the boot's stretch [$fc03b6, $fc03e0): the init, the IKBD reset, the pause, the cartridge's hook 2 --------- */
#define ROM_IKBD_RESET_COMMAND    0xfc053a   /* the IKBD's reset command, $80 $01, read in place (TABLE) ... */
#define IKBD_RESET_COMMAND_COUNT  1          /* ...sent by Ikbdws, whose count is one less than its bytes */
#define BOOT_IKBD_RESET_DBF_COUNT 32767      /* `move.l #32767,d0` + `bsr` to an `rts` + `dbf`: 32,768 passes */
#define ROM_CARTRIDGE_HOOKS       0xfc0646   /* the cartridge's application hooks, D0 the init bit (CODE: the boot's,
                                              * unported, called four times; D2 open — the port reads 0 here) */
#define CARTRIDGE_HOOK_IKBD_RESET 2          /* the bit the boot calls the hooks with after the IKBD reset */
#define ROM_BOOT_IKBD_RESET_DONE  0xfc03e0   /* where the ROM's boot goes on: the resolution read (B5's) */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* The MFP handlers this build links (`src/bios/isr.S`): stored by `BOOT_LINKED_ENTRY` (`boot/sysvars.h`). */
#ifndef RECREATE_HOST_DIFFERENTIAL
extern const char isr_timer_c_entry[], isr_acia_entry[];
#endif

void bios_hardware_init(uint8_t *image);
void boot_ikbd_reset(uint8_t *image);
#endif

#endif /* TOS102US_BOOT_HWINIT_H */
