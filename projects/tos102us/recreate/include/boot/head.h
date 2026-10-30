/* boot/head.h — the names THE HEAD (`src/boot/head/head.S`, `[$fc0030, $fc02cc)`) is spelt in: the system variables,
 * the chips' registers and the ROM's own addresses it reads, stores or reaches, and its magics and bounds.
 *
 * ASSEMBLER-SAFE (plain integer `#define`s only, as `addrs.h`): `head.S` includes both. The Python side reads it with
 * `layouts.parse_constants` (`test/boot_head.py`), so a value is spelt once across the boundary.
 *
 * WHERE THE HEAD IS LAID — `HEAD_LAID_AT` (ruling "ROM-window overlay", 2026-10-29). The oracle serves RAM (1 MB) and
 * the ROM window [$fc0000, $ff0000) and answers 0 for every other address, so the head can run only in one of the
 * two — and the head clears RAM under itself (the cold arm `$400..phystop`, both arms `$980..$10000`). It is laid over
 * a COPY of the image's ROM bytes at `HEAD_LAID_AT` (A LABELLED STAGING, `test/boot.py`'s `Overlay`): a span the
 * head's slices never execute nor read on either shore (held: `test_boot_head.py`), and within a 16-bit displacement
 * of every ROM address the head reaches pc-relative ($fc0008 .. $fc0e1a), so every such operand keeps the ROM's
 * length. The Makefile's own link rule (`build/boothead/`) links the head there; no other blob holds it. */
#ifndef TOS102US_BOOT_HEAD_H
#define TOS102US_BOOT_HEAD_H

#define HEAD_LAID_AT              0xfc6000   /* the head's first byte when it runs (the ROM's $fc0030) */

/* ---- the reset ------------------------------------------------------------------------------------------------- */
#define HEAD_SR_MASKED            0x2700     /* supervisor, every interrupt masked: what a reset forces ($fc0030) */

/* ---- the cartridge port (D2: the image reads 0 there — the no-cartridge arms alone run) -------------------------- */
#define CARTRIDGE_PORT            0xfa0000   /* a cartridge's first longword: its magic */
#define CARTRIDGE_DIAGNOSTIC_MAGIC 0xfa52235f /* ...a DIAGNOSTIC cartridge's, entered before anything is set up */
#define CARTRIDGE_DIAGNOSTIC_ENTRY 0xfa0004  /* ...at the longword after its magic, its return link in A6 */

/* ---- the system variables the head reads and stores ------------------------------------------------------------- */
#define SYSVAR_MEMVALID           0x420      /* long: memory valid if it holds MEMVALID_MAGIC (with the two below) */
#define SYSVAR_MEMCTRL            0x424      /* byte: the memory controller's configuration, as the sizing found it */
#define SYSVAR_RESVALID           0x426      /* long: RESVALID_MAGIC if a reset-resident routine is hooked (D12) */
#define SYSVAR_RESVECTOR          0x42a      /* long: ...that routine, entered with its return link in A6 */
#define SYSVAR_MEMVAL2            0x43a      /* long: the second memory-valid magic */
#define SYSVAR_MEMVAL3            0x51a      /* long: the third */
#define SYSVAR_END_OS             0x4fa      /* long: the first byte of RAM the OS does not own */
#define SYSVAR_EXEC_OS            0x4fe      /* long: the shell the BIOS starts (GEM, or the header's reset) */
#define SYSVAR_HDV_INIT           0x46a      /* long: the hard-disk vectors the head installs: init ... */
#define SYSVAR_HDV_BOOT           0x47a      /* ...and boot (`HDV_BPB`, `HDV_RWABS`, `HDV_MEDIACH`: `addrs.h`) */
#define SYSVAR_PRV_LSTO           0x506      /* long: the printer's output status */
#define SYSVAR_PRV_LST            0x50a      /* long: ...its output */
#define SYSVAR_PRV_AUXO           0x50e      /* long: the RS232's output status */
#define SYSVAR_PRV_AUX            0x512      /* long: ...its output */
#define MEMVALID_MAGIC            0x752019f3
#define MEMVAL2_MAGIC             0x237698aa
#define MEMVAL3_MAGIC             0x5555aaaa
#define RESVALID_MAGIC            0x31415926
#define RESVECTOR_ODD_BIT         0          /* an odd resvector is no routine: `btst #0` refuses it */

/* ---- the chips ------------------------------------------------------------------------------------------------- */
/* The ROM spells every I/O register it addresses as a longword `$ffff....`: the 24-bit bus drops the top byte, so it
 * is the register's address with the top byte set (ADDED, not OR-ed: `|` starts a comment in m68k GNU as). */
#define HEAD_BUS_TOP_BYTE         0xff000000
#define ON_THE_BUS(io)            ((io) + HEAD_BUS_TOP_BYTE)
#define MEMORY_CONTROLLER         0xff8001   /* the MMU's bank configuration register */
#define SHIFTER_SYNC_MODE         0xff820a   /* the shifter's sync mode: bit 1 = 50 Hz */
#define HEAD_SYNC_50HZ            2          /* `move.b #2,$ff820a`: a PAL header's refresh */
#define HEAD_PSG_DATA_OFFSET      (PSG_PORT_DATA - PSG_PORT_SELECT)   /* `2(a0)` off the select port */
#define HEAD_PSG_MIXER_PORTS_OUT  PSG_MIXER_PORT_MASK   /* register 7: both I/O ports outputs, every channel off */
#define HEAD_PSG_PORT_A_DESELECTED 7         /* register 14: both drives deselected, side 0 */
#define HEAD_SCREEN_BASE          0x10000    /* the boot's first screen base, `$ff8201/3` := $01/$00 */

/* ---- the ROM's own bytes the head reads in place (D11 open: each an obligation, `test_boot_rom_data.py`) -------- */
#define ROM_OS_CONF_LOW           0xfc001d   /* the header's os_conf, its low byte: bit 0 set = a PAL machine */
#define OS_CONF_PAL_BIT           0
#define ROM_OS_MAGIC              0xfc0014   /* the header's os_magic: -> GEM's memory-usage parameter block */
#define ROM_HEADER_AS_MUPB        0xfc0008   /* ...or, with no GEM, the header itself read as one (os_end, os_rsv) */
#define MUPB_MAGIC                0x87654321 /* a MUPB's first longword */
#define MUPB_END_OS               4          /* ...then the OS's end */
#define MUPB_EXEC_OS              8          /* ...then the shell to start */
#define ROM_BOOT_PALETTE          0xfc06a8   /* the 16 colours the head loads */
/* ...and the ROM's code it reaches in place by `bra.w`, each returning through the link the head leaves in A6 / A5 */
#define ROM_MEMVALID_CHECK        0xfc0688   /* the three magics compared: Z set = memory valid, `jmp (a6)` */
#define ROM_BANK_TEST             0xfc0672   /* one bank's alias compare: Z set = the pattern found there (the bank aliases at that offset), `jmp (a5)` */
#define ROM_SYNC_WAIT             0xfc0e1a   /* the display sync wait on MFP Timer B, `jmp (a6)` (a PAL header's arm) */
/* ...and the ROM's code whose addresses it stores in the vectors (a rebuilt ROM owes each its linked address) */
#define ROM_HDV_INIT              0xfc0f44
#define ROM_HDV_RW                0xfc12b6
#define ROM_HDV_BPB               0xfc0fca
#define ROM_HDV_MEDIACH           0xfc117a
#define ROM_HDV_BOOT              0xfc1560
#define ROM_SCR_DUMP              0xfc0d62

/* ---- the cold arm's sizing (D1 open: on the oracle's flat megabyte it answers its own memctrl) ---------------- */
#define HEAD_MEMCTRL_SIZING       0x0a       /* both banks 2 MB while the patterns are laid */
#define HEAD_PATTERN_LO           0x8        /* the pattern laid at [$8, $200) ... */
#define HEAD_PATTERN_HI           0x200
#define HEAD_BANK_BYTES           0x200000   /* ...and at the same offsets of the second bank: one bank's span */
#define HEAD_PATTERN_STEP         0xfa54     /* the pattern word's step (`add.w #$fa54,d0`) */
#define HEAD_ALIAS_128K           0x208      /* where the bank test finds the pattern of a 128 KB bank (its alias) ... */
#define HEAD_ALIAS_512K           0x408      /* ...of a 512 KB bank ... */
#define HEAD_ALIAS_2M             0x8        /* ...and of a 2 MB bank: the pattern where it was laid */
#define HEAD_MEMCTRL_BANK_SHIFT   2          /* one bank's two bits of memctrl, shifted down per bank */
#define HEAD_MEMCTRL_SIZE_STEP    4          /* ...and one step of the field being filled (bits 3..2) */
#define HEAD_COLD_STACK           0x8000     /* the stack the cold arm stands on — cleared under it at $fc0206 */
#define VECTOR_BUS_ERROR          0x8        /* vector 2: the RAM probe's end on a machine (D1: never taken here) */
#define HEAD_PROBE_STEP           0x20000    /* the probe's 128 KB steps */
#define HEAD_PROBE_PATTERN_STEP   0xfb55     /* its pattern word's step */
#define HEAD_PROBE_WORDS          43         /* the words it writes and reads back below each step */

/* ---- the clears and the screen --------------------------------------------------------------------------------- */
#define HEAD_SCREEN_BYTES         0x8000     /* the 32 KB screen at the top of RAM */
#define HEAD_RAM_CLEAR_FLOOR      0x400      /* the cold arm clears [$400, phystop) */
#define HEAD_MOVEM_CLEAR_BYTES    16         /* one `movem.l d0-d3,-(a0)` */
#define HEAD_CLEAR_LO             0x980      /* both arms clear [$980, $10000) */
#define HEAD_CLEAR_HI             0x10000
#define HEAD_SCREEN_CLEAR_BYTES   16         /* one pass of the screen clear: four `move.l d0,(a0)+` */
#define HEAD_BIOS_STACK_TOP       0x755a     /* `lea $755a,sp`: the BIOS's stack, where C can stand (ruling D7's end) */

#endif /* TOS102US_BOOT_HEAD_H */
