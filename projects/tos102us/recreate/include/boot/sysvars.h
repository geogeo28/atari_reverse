/* boot/sysvars.h — the names BOOT B2 (`src/boot/sysvars.c`, `[$fc02cc, $fc03b6)` and `$fc0eba`) is spelt in: the
 * system variables it lays, the 68000 vectors it fills, and the ROM's own bytes it reads or stores by value.
 * The names that already exist stay in `addrs.h` (`SYSVAR_NVBLS`, `VECTOR_VBL`, `XCONSTAT_TABLE`, ...).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`): `sysvars_entry.S` includes
 * it. The Python side reads it with `layouts.parse_constants` (`test/boot_sysvars.py`), so a value is spelt once. */
#ifndef TOS102US_BOOT_SYSVARS_H
#define TOS102US_BOOT_SYSVARS_H

/* ---- where the ROM's boot goes on after the span: `bsr $fc2408`, the BIOS's hardware init (B3's) ---------------- */
#define ROM_BOOT_HARDWARE_INIT_CALL 0xfc03b6

/* ---- the system variables the span lays (`addrs.h` names the rest) ------------------------------------------- */
#define SYSVAR_ETV_CRITIC         0x404      /* long: -> the critical-error handler GEMDOS calls */
#define SYSVAR_ETV_TERM           0x408      /* long: -> the routine a process's termination calls */
#define SYSVAR_SEEKRATE           0x440      /* word: the floppy's step rate, the WD1772's code */
#define SYSVAR_FVERIFY            0x444      /* byte: non-zero = verify every floppy write */
#define SYSVAR_DSKBUFP            0x4c6      /* long: -> the 1 KB disk buffer the boot reads sectors into */
#define BOOT_NVBLS                8          /* the VBL queue's slots */
#define BOOT_VBL_SLOTS            0x4ce      /* ...laid in the system variables themselves, each cleared */
#define BOOT_FVERIFY_ON           0xff       /* `st`: writes verified */
#define BOOT_SEEKRATE_3MS         3          /* the WD1772's 3 ms step */
#define BOOT_DISK_BUFFER          0x16da     /* the disk buffer, below the BIOS's stack */
#define BOOT_DUMPFLG_IDLE         0xffff     /* -1: no screen dump asked for */
#define BOOT_SAVE_AREA_TOP        0x93a      /* savptr's first value: the BIOS's register-save area grows down from here */

/* ---- the 68000's vector table: what the span fills ------------------------------------------------------------ */
#define VECTOR_FIRST_BOMB         0x8        /* vector 2, the bus error: the first the "bombs" handler takes ... */
#define VECTOR_FIRST_BOMB_NUMBER  2
#define VECTOR_BOMBS              62         /* ...through vector 63 (`moveq #61` + `dbf`) */
#define VECTOR_NUMBER_SHIFT       24         /* ...each handler longword carries ITS VECTOR NUMBER in its top byte (the
                                              * 24-bit bus drops it; the bombs handler reads it back off the PC) */
#define VECTOR_DIVIDE_BY_ZERO     0x14       /* vector 5: a bare `rte` instead (no bombs for a division by zero) */
#define VECTOR_AUTOVECTOR_1       0x64       /* the level 1..7 autovectors: a bare `rte` each, before two are given */
#define AUTOVECTOR_LEVELS         7          /*   their handlers (`VECTOR_HBL`, `VECTOR_VBL`: `addrs.h`) */

/* ---- the ROM's code the span stores by value (CODE obligations on a rebuilt ROM: `test_boot_rom_data.py`) ----- */
#define ROM_BARE_RTE              0xfc07ce   /* the shared `rte`: every exception nothing else takes */
#define ROM_BOMBS_ENTRY           0xfc0b50   /* the exception handler that draws the bombs (unported: `bsr` stub + body) */
#define ROM_ETV_CRITIC_DEFAULT    0xfc07ee   /* `moveq #-1,d0` / `rts`: the critical-error handler's default (unported) */

/* ---- the ROM's own bytes the span reads in place (TABLE obligations, D11 open) -------------------------------- */
#define ROM_XCON_TABLES           0xfc09ae   /* the four character-device tables' defaults, copied to XCONSTAT_TABLE */
#define XCON_TABLES               4          /* xconstat, xconin, xcostat, xconout: `XCON_TABLE_DEVICES` longwords each */
#define ROM_OS_HEADER             ROM_BASE   /* the OS header (its first `OS_HEADER_BYTES`), copied into RAM at $fc0eba */

/* ---- $fc0eba: the OS header in RAM, and `_sysbase` pointed at it ----------------------------------------------- */
#define OS_HEADER_RAM             0x940      /* where the copy lies */
#define OS_HEADER_BYTES           48         /* `moveq #47` + `dbf`: the header through its last field */
#define OS_HEADER_RESET           4          /* the header's reset handler (its second longword) */
#define OS_HEADER_CONF            0x1c       /* the header's os_conf word ... */
#define OS_HEADER_DOSDATE         0x1e       /* ...and the word after it: the copy's os_conf takes ITS value */
#define OS_HEADER_JUMP            (OS_HEADER_RAM - 6)   /* `jmp <reset>.l` laid below the copy ($93a) ... */
#define OS_HEADER_JUMP_TARGET     (OS_HEADER_RAM - 4)   /* ...its target longword ... */
#define OS_HEADER_BRANCH_TO_JUMP  0x60f8     /* ...and the copy's first word: `bra.s` back to that `jmp` */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* A HANDLER STORED IN A VECTOR: OUR linked entry on target, where the build links one (the ROM's own instructions,
 * byte-pinned: `src/bios/isr.S`, `src/bios/trap.S`, `src/vdi/entry.S`), and off target the ROM's address — the host
 * links no entry, and the differential's ROM run stores the ROM's (`test_boot_sysvars.py` maps the target's back). */
#ifdef RECREATE_HOST_DIFFERENTIAL
#define BOOT_LINKED_ENTRY(rom_address, entry) ((uint32_t)(rom_address))
#else
#define BOOT_LINKED_ENTRY(rom_address, entry) ((uint32_t)(uintptr_t)(entry))
extern const char isr_hbl_entry[], isr_vbl_entry[], bios_trap13[], xbios_trap14[], linea_rom_dispatch[];
#endif

void boot_os_header_to_ram(uint8_t *image);
void boot_sysvars_and_vectors(uint8_t *image);
#endif

#endif /* TOS102US_BOOT_SYSVARS_H */
