/* boot/launch.h — the names BOOT B4 is spelt in: the boot's last slice [$fc047a, gem_entry) — the AUTO runner
 * `$fc0c4a` with the process it runs `$fc0cae`, then the launch of the shell (`src/boot/launch/launch.c`, entered by
 * `src/boot/launch/launch_entry.S`). The names that already exist stay where they are (`addrs.h`: GEMDOS's function
 * numbers, `BASEPAGE_TBASE`, `SYSVAR_DRVBITS`, `SYSVAR_SYSBASE`; `boot/head.h`: `SYSVAR_EXEC_OS`, the BIOS's stack top;
 * `boot/sysvars.h`: `ROM_OS_HEADER`).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`): `launch_entry.S` includes
 * it. The Python side reads it with `layouts.parse_constants` (`test/boot_launch.py`), so a value is spelt once.
 *
 * WHAT SHIPS (the user's ruling R-B4-1, 2026-10-31: "Byte-transcribed .S"): `src/boot/launch/launch.S`, the ROM's own
 * bytes of the launch [$fc047a, $fc0518) and the AUTO runner with its process [$fc0c4a, $fc0d50), laid as the ROM lays
 * them — the bytes between the two FILLED, so every branch between them is the ROM's own word — every operand that
 * leaves them reaching the ROM's bytes IN PLACE, and ONE longword ours: the process's text the runner stores, our linked
 * entry. The C (`launch.c` + `launch_entry.S`) is its C TWIN (the `src/bios/isr.S` precedent): built by its own rule
 * and held against the ROM on every surface it holds, priced by nothing.
 *
 * WHERE EACH IS LAID (rulings "ROM-window overlay" and "Own link rule"). Not in RAM: an AUTO program's `Pexec(0)` CLEARS
 * THE WHOLE TPA ($ca00..$f8000, measured) while the runner that called it is still running. Over a COPY of the image's
 * ROM bytes that no instruction of the slice runs or reads (held: the ROM's own slice is the same run with and without
 * each overlay, `test_boot_launch.py`), neither over the AES's text (Tier 3's AES_OWN_SPANS guard). THE .S within a
 * 16-bit displacement of every ROM byte it reaches in place: over Prtblk's text ($fc31fa.., XBIOS 36: unported, run by
 * nothing of the slice). THE TWIN over the VDI's text. Each linked there by its own Makefile rule (`build/bootlaunch/`).
 */
#ifndef TOS102US_BOOT_LAUNCH_H
#define TOS102US_BOOT_LAUNCH_H

#define LAUNCH_LAID_AT            0xfc3200   /* the .S's first byte when it runs: the ROM's $fc047a */
#define LAUNCH_TWIN_LAID_AT       0xfcc000   /* the C twin's entry glue's first byte */

/* ---- the ROM's two spans the .S transcribes, laid out as the ROM lays them ------------------------------------- */
#define ROM_LAUNCH                0xfc047a   /* `tst.w _cmdload`: the launch's first instruction ... */
#define ROM_LAUNCH_END            0xfc0518   /* ...past its `jmp $fc0030`: the environment's template follows */
#define ROM_AUTO_RUNNER           0xfc0c4a   /* the AUTO runner ... */
#define ROM_AUTO_RUNNER_END       0xfc0d50   /* ...through its process's last `rts` */

/* ---- the system variables the slice reads and lays (`addrs.h` and `boot/head.h` name the rest) ------------------ */
#define SYSVAR_CMDLOAD            0x482      /* word: non-zero = the BIOS runs COMMAND.PRG instead of the GEM shell */
#define SYSVAR_BOOTDEV            0x446      /* word: the drive the boot came from — the environment's letter is
                                              * made from its FIRST (high) byte: `move.b $446,d0` (a ROM bug, kept) */
#define BOOT_ENVIRONMENT          0x840      /* the environment the BIOS hands the shell: "PATH=", "A:\", "" */
#define ENVIRONMENT_DRIVE_MARK    0x23       /* '#': the template's byte that becomes the boot drive's letter */
#define DRIVE_LETTER_A            0x41       /* 'A' */

/* ---- the AUTO runner's scratch: its own system variables below the OS header's copy at $940 ------------------- */
#define AUTO_RETURN               0x980      /* long: where the runner returns — the process returns there for it */
#define AUTO_PATH                 0x984      /* long: -> the search's whole path "\AUTO\*.PRG" ... */
#define AUTO_PATTERN              0x988      /* long: ...and -> its last name, "*.PRG": the folder is what lies before */
#define AUTO_DTA                  0x98c      /* the process's DTA (44 bytes): the program found, by name at ... */
#define AUTO_DTA_NAME             30         /* ...this offset (`gemdos/fs.h`'s DTA_NAME, C-only: pinned equal) */
#define AUTO_PROGRAM_NAME         0x9b8      /* the program's path, "\AUTO\" and the name found, built for Pexec(0) */
#define AUTO_SEARCH_ATTRIBUTES    7          /* Fsfirst's: read-only, hidden and system files found too */
#define AUTO_PROCESS_BYTES        0x100      /* the process keeps its basepage alone (Mshrink), and its stack is the
                                              * basepage's own top: `lea 256(a5),sp` — the command tail under it */
#define NO_AUTO_PROCESS           0          /* the runner's answer where the boot drive is not in `_drvbits` */

/* ---- GEMDOS, as the slice calls it (the function numbers `addrs.h` has not named, and Pexec's two modes the glue
 * pushes: `gemdos/process.h` is C-only, so they are spelt here and pinned equal to its own in `launch.c`) -------- */
#define GEMDOS_MSHRINK_FN         0x4a
#define MSHRINK_RESERVED_WORD     0          /* Mshrink's first word, which GEMDOS does not read: `clr.w -(sp)` */
#define SUPER_ON_THE_CALLER_S_STACK 0        /* Super(0): supervisor mode on the stack the caller stands on */
#define SUPER_FRAME_BYTES         6          /* Super's words: the function and the stack */
#define BASEPAGE_ARGUMENT         4          /* a process Pexec enters finds its basepage at 4(sp) */
#define LAUNCH_PEXEC_LOAD_AND_GO  0
#define LAUNCH_PEXEC_JUST_GO      4
#define LAUNCH_PEXEC_CREATE_BASEPAGE 5
#define PEXEC_FRAME_BYTES         16         /* Pexec's words: the function, the mode, the name, the tail, the
                                              * environment (`adda.w #16,sp` — the runner's) */
#define LAUNCH_STRAY_WORD         2          /* the launch's Pexec(5) drops 14 of its 16 (`adda.w #14,sp`, $fc04ea: a
                                              * ROM bug, kept): its Pexec(4) frame stands a word lower */
#define BTST_REGISTER_BIT_MASK    31         /* `btst Dn,Dn` tests bit (Dn mod 32) of a data register */

/* ---- the ROM's own bytes the slice reads in place (TABLE obligations, D11 open: `test_boot_rom_data.py`) ---------- */
#define ROM_ENVIRONMENT_TEMPLATE  0xfc0518   /* "PATH=" 0 "#:\" 0 0 $ff: copied through its first byte with the top
                                              * bit set, the mark replaced */
#define ROM_COMMAND_PRG           0xfc0524   /* "COMMAND.PRG": the `_cmdload` arm's program */
#define ROM_EMPTY_STRING          0xfc0537   /* the NUL that ends "GEM.PRG": every empty name, tail and environment */
#define ROM_AUTO_PATH             0xfc0c36   /* "\AUTO\*.PRG" ... */
#define ROM_AUTO_PATTERN          0xfc0c3c   /* ...and its "*.PRG" */

/* ---- the ROM's code the slice reaches (a CODE obligation) ----------------------------------------------------- */
#define ROM_RESET_ENTRY           0xfc0030   /* where the boot goes if the shell's Pexec ever returns: the reset */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* The process the runner launches: its first instruction (`launch_entry.S`), which the runner stores as its text. */
extern const char boot_auto_process_entry[];

uint32_t boot_auto_runner(uint8_t *image);
void boot_auto_process(uint8_t *image, uint32_t basepage);
void boot_launch_sysbase(uint8_t *image);
uint32_t boot_launch_gem(uint8_t *image);
#endif

#endif /* TOS102US_BOOT_LAUNCH_H */
