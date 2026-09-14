/* addrs.h — every ROM and system address this recreate names, in one place.
 *
 * THE SINGLE SOURCE OF TRUTH ACROSS THE LANGUAGE BOUNDARY. The C cores include this; the Python
 * side (`test/`, `tools/boot_snapshot.py`) reads the same `#define`s out of this file through
 * `tools/addrs.py`, which parses it. Neither side keeps a second copy, so an address cannot be
 * right in the reconstruction and wrong in the case that proves it.
 *
 * Addresses here are the machine's own — a ROM address is where the ROM is mapped ($FC0000), and a
 * system-variable address is where TOS itself puts it. They are therefore also Ghidra addresses for
 * this project, whose image is loaded at its real base with no relocation (see ../README.md).
 */
#ifndef TOS102US_ADDRS_H
#define TOS102US_ADDRS_H

#include "os.h"     /* the kit's own map: PSG_PORT_SELECT below is OS_PSG_PORT_SELECT, not a copy */

/* ---- the machine ------------------------------------------------------------------------------ */
#define ROM_BASE            0xfc0000   /* TOS 1.02 US is mapped here and linked for it */
#define ROM_BYTES           0x30000    /* 192 KB */
#define ST_RAM_BYTES        0x100000   /* the 1 MB machine the snapshot was taken on */

/* ---- the 68000 vector slots the OS owns ------------------------------------------------------- */
#define VECTOR_TRAP_GEMDOS  0x84       /* trap #1  -> $fc4f6e */
#define VECTOR_TRAP_GEM     0x88       /* trap #2  -> $fe3ea6 (AES/VDI) */
#define VECTOR_TRAP_BIOS    0xb4       /* trap #13 -> $fc07f8 */
#define VECTOR_TRAP_XBIOS   0xb8       /* trap #14 -> $fc07f2 */
#define VECTOR_VBL          0x70       /* the vertical-blank handler the snapshot is captured in */
#define VECTOR_BYTES        4          /* ...and one slot, which is Setexc's whole index arithmetic */

/* ---- system variables the reconstructed functions read or write -------------------------------- */
#define SYSVAR_PHYSTOP      0x42e      /* long: top of ST RAM */
#define SYSVAR_MEMBOT       0x432      /* long: bottom of the TPA */
#define SYSVAR_MEMTOP       0x436      /* long: top of the TPA */
#define SYSVAR_V_BAS_AD     0x44e      /* long: the logical screen base Setscreen stores */
#define SYSVAR_HZ_200       0x4ba      /* long: the 200 Hz system tick — XBIOS Random's entropy */
#define SYSVAR_SYSBASE      0x4f2      /* long: the OS header, i.e. ROM_BASE */

/* ---- the trap dispatch tables ------------------------------------------------------------------
 * Both are `word count` followed by `count` longword entries; the dispatcher at $fc07fc bounds the
 * function number against the count, and an entry with bit 31 set is INDIRECT — the longword at the
 * masked address is the routine (that is how Rwabs/Getbpb/Mediach reach a hard-disk driver). */
#define BIOS_FUNCTION_TABLE   0xfc0846  /* 12 entries */
#define XBIOS_FUNCTION_TABLE  0xfc0878  /* 65 entries */
#define TRAP_TABLE_COUNT_BYTES 2        /* the leading word */
#define TRAP_TABLE_ENTRY_BYTES 4
#define TRAP_TABLE_INDIRECT   0x80000000u

/* ---- the reconstructed ROM functions ------------------------------------------------------------
 * Both are reached through the XBIOS dispatcher at $fc07fc, which pops the function number and
 * `suba.l a5,a5` — so every ROM function runs with A5 = 0 and reaches both low RAM and the I/O page
 * through 16-bit displacements off it. A case must enter them the same way. */
#define XBIOS_RANDOM_FN     0x11        /* XBIOS function number */
#define XBIOS_RANDOM        0xfc1510
#define XBIOS_GIACCESS_FN   0x1c
#define XBIOS_GIACCESS      0xfc2ea4

/* ---- XBIOS Random ------------------------------------------------------------------------------ */
#define RANDOM_SEED         0x2a4a      /* long, in the OS's own BSS: the LCG's state */
#define RANDOM_MULTIPLIER   0xbb40e62du /* seed = seed * this + 1 */
#define RANDOM_SHIFT        8           /* ...and the result is the state shifted down this far... */
#define RANDOM_MASK         0xffffffu   /* ...and masked to 24 bits */

/* ---- XBIOS Giaccess ---------------------------------------------------------------------------- */
#define GIACCESS_REGISTER_MASK 0x0f     /* the YM2149's select latch decodes four bits */
#define GIACCESS_WRITE_FLAG    0x80     /* ...and bit 7 of the register argument means "write" */
/* The chip's select port, in the 24-bit bus form the ROM's own `lea $ffff8800,a0` aliases onto. This
 * project's name for os.h's constant and NOT a second spelling of $ff8800: a core that reached the
 * chip directly would have to hit the address the oracle DECODES, or the PSG model would quietly
 * stop being in the picture. (Today no core does — they call psg.h, which is what makes the accesses
 * comparable — and the Python case that plants a decoy at the port reads the same constant through
 * `harness.OS_PSG_PORT_SELECT`, pinned to os.h by recreate_kit/test/test_os_memory_map.py.) */
#define PSG_PORT_SELECT     OS_PSG_PORT_SELECT

/* ================================================================================================
 * THE BIOS/XBIOS LEAVES THAT READ AND WRITE RAM ONLY (wave 2)
 *
 * Everything below belongs to the group of trap routines whose whole body is system variables, an
 * IOREC ring or the caller's own buffer — no MFP, no ACIA, no shifter — which is what makes them
 * runnable under ROM mode's I/O-read refusal (../README.md, "The image in ROM mode").
 * ============================================================================================= */

/* ---- system variables these routines report or keep -------------------------------------------- */
#define SYSVAR_TIMR_MS      0x442      /* word: the system-timer calibration Tickcal reports, in ms */
#define SYSVAR_DRVBITS      0x4c2      /* long: one bit per mounted drive — Drvmap's whole body */

/* The four BIOS character-device vector TABLES, eight longwords each, built at boot from the ROM
 * image at $fc09ae. Bconstat/Bconin/Bcostat/Bconout are each a walk of one of them, so these are
 * RAM that steers control flow rather than data. */
#define XCONSTAT_TABLE      0x51e
#define XCONIN_TABLE        0x53e
#define XCOSTAT_TABLE       0x55e
#define XCON_TABLE_DEVICES  8          /* ...and how many longwords one of them holds */
#define XCON_TABLE_ENTRY_BYTES 4       /* ...each one a driver address, which is also the index step */
/* Bconout's table at $57e is deliberately absent: every one of its eight drivers writes a chip, so
 * nothing in this wave reaches it and a constant no code reads is a claim nothing checks. */

/* The ROM's own root MEMORY DESCRIPTOR, which Getmpb hands the caller a memory parameter block for.
 * Four longwords: link, start, length, owner (the GEMDOS MD layout). */
#define OS_MEMORY_DESCRIPTOR 0x48e

/* The GEMDOS MEMORY PARAMETER BLOCK Getmpb fills, and the memory DESCRIPTOR on its lists — field
 * offsets, in the order the ROM stores them. Both structures are the caller's view of GEMDOS's
 * allocator, so the names are GEMDOS's own (`mp_mfl`, `m_link`, ...). */
#define MPB_FREE_LIST        0         /* mp_mfl:   the free list's head */
#define MPB_ALLOCATED_LIST   4         /* mp_mal:   the allocated list's, empty at this point */
#define MPB_ROVER            8         /* mp_rover: where the next search starts */
#define MD_LINK              0         /* m_link:   the next descriptor, or 0 */
#define MD_START             4         /* m_start:  the block's base */
#define MD_LENGTH            8         /* m_length: its size in bytes */
#define MD_OWNER             12        /* m_own:    the basepage that owns it, or 0 */

#define KBSHIFT             0xe61      /* byte: the keyboard shift state — the OS header's pkbshift */
#define KEYTBL_STRUCT       0xe62      /* 3 longwords: the unshifted/shifted/CapsLock scancode tables */
#define KEYTBL_FIELD_UNSHIFTED 0       /* ...and which longword is which. Keytbl takes its three */
#define KEYTBL_FIELD_SHIFTED   4       /* arguments in this order and Bioskeys restores them in it, */
#define KEYTBL_FIELD_CAPSLOCK  8       /* so a swapped pair is a real defect rather than a typo */
#define KBRATE_DELAY        0xe82      /* byte: ticks before a held key starts repeating */
#define KBRATE_REPEAT       0xe83      /* byte: ticks between repeats — Kbrate reports BOTH as a word */

/* The three IOREC rings the interrupt handlers fill and the BIOS drains, in XBIOS Iorec's own order.
 * The RS232 record is the first of a PAIR (its output record follows at $c62); the other two are
 * single. */
#define IOREC_RS232         0xc54
#define IOREC_IKBD          0xc76
#define IOREC_MIDI          0xd84

/* ...and one record's fields. `size` is in BYTES, and so are `head`/`tail`, which index the ring
 * rather than count records — a keyboard record is four bytes wide and a MIDI one is a single byte. */
#define IOREC_BUFFER        0           /* long: the ring's base address */
#define IOREC_SIZE          4           /* word: the ring's length in bytes */
#define IOREC_HEAD          6           /* word: the BIOS's read index */
#define IOREC_TAIL          8           /* word: the interrupt handler's write index */
#define IOREC_KEY_BYTES     4           /* the IKBD ring's record: scancode word + ASCII word */
#define IOREC_MIDI_BYTES    1           /* the MIDI ring's record: one raw byte */

/* The alpha-cursor / console state block the BIOS console driver and the VDI escape share. Cursconf
 * reaches it through `lea $2994,a4` and addresses the rest at negative displacements off it. */
#define CON_STATE_FLAGS     0x2994     /* byte: bit 0 = cursor blinks, bit 1 = cursor drawn now */
#define CON_STATE_SPARE     0x2995     /* byte: Cursconf 6 writes it and 7 reads it back */
#define CON_BLINK_RATE      0x2982     /* byte: vertical blanks between cursor blinks ($2994 - 18) */

/* ---- the BIOS routines (trap #13, table $fc0846) ------------------------------------------------ */
#define BIOS_GETMPB_FN      0
#define BIOS_GETMPB         0xfc0a46
#define BIOS_BCONSTAT_FN    1
#define BIOS_BCONSTAT       0xfc0984
#define BIOS_BCONIN_FN      2
#define BIOS_BCONIN         0xfc098c
#define BIOS_SETEXC_FN      5
#define BIOS_SETEXC         0xfc0a72
#define BIOS_TICKCAL_FN     6
#define BIOS_TICKCAL        0xfc0a8a
#define BIOS_BCOSTAT_FN     8
#define BIOS_BCOSTAT        0xfc0994
#define BIOS_DRVMAP_FN      10
#define BIOS_DRVMAP         0xfc0a2e
#define BIOS_KBSHIFT_FN     11
#define BIOS_KBSHIFT        0xfc0a34

/* ---- the XBIOS routines (trap #14, table $fc0878) ----------------------------------------------- */
#define XBIOS_LOGBASE_FN    3
#define XBIOS_LOGBASE       0xfc0aa6
#define XBIOS_IOREC_FN      14
#define XBIOS_IOREC         0xfc28f6
#define IOREC_TABLE         0xfc2902   /* ...and the three-longword table in ROM it indexes, unbounded */
#define IOREC_TABLE_ENTRY_BYTES 4      /* ...one ring address, which is also the index step */
#define XBIOS_KEYTBL_FN     16
#define XBIOS_KEYTBL        0xfc302e
#define XBIOS_PROTOBT_FN    18
#define XBIOS_PROTOBT       0xfc15f8
#define XBIOS_CURSCONF_FN   21
#define XBIOS_CURSCONF      0xfc4698
#define XBIOS_BIOSKEYS_FN   24
#define XBIOS_BIOSKEYS      0xfc305a
#define XBIOS_KBRATE_FN     35
#define XBIOS_KBRATE        0xfc309a
#define XBIOS_SUPEXEC_FN    38
#define XBIOS_SUPEXEC       0xfc097e

/* ---- the character-device DRIVERS the three Bcon* entries jump through --------------------------
 * A vector, not an entry point: the tables above hold these, and which of them a device number
 * reaches is a fact about the RAM the snapshot captured rather than about the ROM. Only the drivers
 * whose whole body is an IOREC are here; the printer's, the RS232's and the console's OUTPUT drivers
 * poll the MFP or the ACIA and are out of reach (../README.md, the I/O-read refusal). */
#define ROM_BARE_RTS        0xfc0670   /* the shared `rts`: the vector for a device with no driver */
#define XCONSTAT_RS232      0xfc2138
#define XCONSTAT_CON        0xfc2226   /* the console's INPUT status is the IKBD ring's */
#define XCONSTAT_MIDI       0xfc2044
#define XCONIN_CON          0xfc223c
#define XCONIN_MIDI         0xfc2060
#define XCOSTAT_CON         0xfc226c   /* the screen is never busy: `moveq #-1,d0` and nothing else */
/* MIDI's reader ends `move.b (a1,d1.w),d0`, a BYTE into the D0 its status driver had just filled
 * with `moveq #-1` — so Bconin(MIDI) answers this OR the byte, and never the bare byte. */
#define MIDI_RESULT_PREFIX  0xffffff00u

/* ---- XBIOS Keytbl / Bioskeys -------------------------------------------------------------------- */
#define KEYTBL_UNSHIFTED_ROM 0xfc2288  /* the three 128-byte scancode tables Bioskeys restores */
#define KEYTBL_SHIFTED_ROM   0xfc2308
#define KEYTBL_CAPSLOCK_ROM  0xfc2388

/* ---- XBIOS Cursconf ----------------------------------------------------------------------------- */
#define CURSCONF_JUMP_TABLE   0xfc46b2  /* eight SIGNED WORD displacements, from the table's own address */
#define CURSCONF_MAX_FUNCTION 7        /* `cmp.w #7,d0 / bhi` — above it the routine just returns */
#define CURSCONF_HIDE         0        /* these two DRAW, and are not reconstructed here */
#define CURSCONF_SHOW         1
#define CURSCONF_BLINK        2
#define CURSCONF_STEADY       3
#define CURSCONF_SET_RATE     4
#define CURSCONF_GET_RATE     5
#define CURSCONF_SET_SPARE    6
#define CURSCONF_GET_SPARE    7
#define CON_FLAG_BLINKS       0        /* bit number, as the ROM's `bset #0,(a4)` names it */

/* ---- XBIOS Protobt ------------------------------------------------------------------------------
 * The boot-sector prototyper: pure computation over the caller's 512-byte buffer, plus one call into
 * XBIOS Random when the serial number it is given will not fit in three bytes. */
#define BOOT_SECTOR_BYTES    512
#define BOOT_SECTOR_WORDS    256
#define BOOT_SERIAL_AT       8         /* buf[8..10]: the three-byte disk serial number */
#define BOOT_SERIAL_BYTES    3
#define BOOT_SERIAL_MAX      0xffffff  /* ...so a larger one is replaced by a random one */
#define BOOT_BPB_AT          11        /* buf[11..29]: the BPB the prototype table supplies */
#define BOOT_BPB_BYTES       19
#define BOOT_CHECKSUM_AT     510       /* buf[510..511]: the word that makes the sector sum to... */
#define BOOT_EXECUTABLE_SUM  0x1234    /* ...this, which is what makes a boot sector executable */
#define PROTOBT_BPB_TABLE    0xfd2f32  /* four 19-byte BPB prototypes, indexed by disk type */

/* ---- XBIOS Getrez ($04) — the first reconstruction to read a HARDWARE register ------------------
 * Every routine above this line is RAM only, which is what made it reachable before the DECLARED
 * I/O MAP existed. Getrez is three instructions and one of them is a read of the shifter, so it is
 * the smallest function that needs a case to say what the machine answers there
 * (`io_seed={SHIFTER_RESOLUTION: <byte>}`; TRAP_MODEL.md, Phase 15).
 *
 * The register is the kit's, not this project's: `OS_HW_IO_*` bound the page it is in, and a second
 * spelling of $ff8260 here would be a second place for the address to be right in the
 * reconstruction and wrong in the case that proves it. This project names WHICH register, and the
 * kit owns the page. */
#define SHIFTER_RESOLUTION  0xff8260   /* the shifter's resolution byte; bits 0-1 are the mode */
#define GETREZ_MODE_MASK    0x03       /* `and.b #3,d0` — 0 low, 1 medium, 2 high */
#define XBIOS_GETREZ_FN     0x04
#define XBIOS_GETREZ        0xfc0aac

#endif /* TOS102US_ADDRS_H */
