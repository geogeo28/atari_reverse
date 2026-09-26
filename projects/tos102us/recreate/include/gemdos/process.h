/* gemdos/process.h — the GEMDOS PROCESS group and the HANDLE machinery under it.
 *
 * `src/gemdos/process.c` is `Pterm`/`Pterm0`/`Ptermres`/`Pexec` and the release routine all four
 * reach; `src/gemdos/handles.c` is `Fforce`/`Fdup`/`Fclose` and the dispatcher's own handle
 * resolution. One header, because they are one subsystem: a process IS its basepage, its memory and
 * its six standard handles, and every routine here reads at least two of the three.
 *
 * THE TWO STRUCTURES, and only the second one is new.
 *
 *   * the BASEPAGE. Its offsets are `addrs.h`'s — the trap entry's wave put the save slots there and
 *     this one adds the published longwords and `p_curdir` — because the basepage is the one record
 *     every GEMDOS group indexes and a second home for it would be a second thing to keep right.
 *   * the HANDLE RECORD at `GEMDOS_HANDLE_TABLE` ($8092), which is this group's own: 75 records of
 *     ten bytes, indexed from handle 6, each a longword, an owner and a word reference count. The
 *     fields are below, and each carries the instruction that establishes it.
 *
 *     IT IS NOT THE OPEN FILE DESCRIPTOR, and the two were spelt `OFD_` alike until this wave. The
 *     OFD is the FILE SYSTEM's 64-byte record (`include/gemdos/fs.h`, `OFD_DMD`/`OFD_STRTCL`/…);
 *     what is here is the ten-byte slot whose first longword POINTS at one — or, when it is
 *     negative, names a character device instead. Nothing in this group follows that pointer.
 *
 * WHAT A HANDLE IS IN TOS 1.02, since three different things are spelt as one signed word:
 *
 *   * NEGATIVE — a character DEVICE, and not an index into anything. -1/-2/-3 are CON:/AUX:/PRN:,
 *     which is what a fresh process's `p_uft` holds and what `src/gemdos/console.c` turns into a
 *     BIOS device number by adding three.
 *   * 0..5 — a STANDARD handle, an index into the running process's own `p_uft`, whose byte is then
 *     one of the other two kinds. The dispatcher resolves one before a leaf ever sees it.
 *   * 6 and up — a HANDLE RECORD, at `(handle - 6) * 10` bytes into the table. Its own
 *     first longword is then NEGATIVE for a device (that is how `Fdup` of a standard handle names
 *     one) and a file-system pointer otherwise.
 *
 * ...so "resolve a handle" is a two-step walk that can end on any of the three, and it is written
 * once — `gemdos_resolve_handle` below — because the dispatcher, `Fclose` and `gemdos_force_handle`
 * each walk part of it and a second copy is a second place for the signs to go wrong.
 */
#ifndef TOS102US_GEMDOS_PROCESS_H
#define TOS102US_GEMDOS_PROCESS_H

#include <stdint.h>

#include "addrs.h"
#include "machine.h"

/* ---- the HANDLE RECORD ($8092, 75 records of ten bytes) ---------------------------------------- */
/* What a handle NAMES, and the one field whose sign decides everything: `Fclose` ($fc571c) and the
 * dispatcher's resolution ($fc995c) both read it and branch on `bge`. Negative is a character
 * device; anything else is the file system's own pointer — an OFD, which `Fclose` hands to the file
 * system's close ($fc57ee) and, on the last reference, back to the pool ($fc7f9c). */
#define HANDLE_VALUE         0
#define HANDLE_OWNER         4      /* long: the basepage that opened it — `Fdup` $fc526c stores */
                                    /*   `p_run` here and `gemdos_release_process` $fc80ce hunts it */
#define HANDLE_REFCOUNT      8      /* word: `Fforce` $fc538a bumps it, `Fclose` $fc5730 drops it */
/* `cmpw #75` at $fc524c and $fc80e0 — the table's length, in both the routines that walk it. */
#define GEMDOS_HANDLE_COUNT  75

/* ---- what the handle routines answer ------------------------------------------------------------ */
/* -35: `Fdup` found no free descriptor. The one error in this group that is not `GEMDOS_EIHNDL`. */
#define GEMDOS_ENHNDL       0xffffffddu

/* ---- the Mega ST battery clock ($fffc20), the one piece of hardware GEMDOS itself touches -------
 *
 * An RP5C15, absent on every plain ST including the machine the snapshot was captured on. It sits on
 * every other byte of the bus — one register per ODD address — and holds one BCD digit per register.
 * The geometry is HERE rather than in `src/gemdos/process.c` because `test/gemdos_process.py` has to
 * declare the same registers to the harness, and a case and the core it proves must not disagree
 * about which address is which (the header is parsed by `tools/addrs.py`).
 */
#define RTC_BASE             0xfffc20   /* `movea.w #-992,a0`, sign-extended onto the 24-bit bus */
#define RTC_RESET            0x01       /* +1: the reset register the present arm writes */
#define RTC_RESET_VALUE      1          /* ...with this byte ($fc4cd4 `move.b #1,1(a0)`) */
#define RTC_PROBE_HIGH       0x05       /* +5 and +7, which `movep.w` addresses as one word */
#define RTC_PROBE_LOW        0x07
#define RTC_MODE             0x1b       /* +27: the bank/mode register */
#define RTC_TEST             0x1d       /* +29: the test register the present arm clears */
#define RTC_MODE_PROBE       0x09       /* ...what the mode register is set to for the probe... */
#define RTC_MODE_RUN         0x08       /* ...and what it is left at when a chip answered */
#define RTC_PROBE_PATTERN    0x0a05     /* the word written into the two probe registers... */
#define RTC_PROBE_MASK       0x0f0f     /* ...and the four bits of each that really latch */
/* The DIGITS, read HIGHEST register first: the ROM reads registers 1, 3, 5 ... 25 and files them at
 * buffer[12], [11] ... [0], so the buffer runs year-tens, year-units, ... seconds-units. */
#define RTC_DIGITS           13         /* `moveq #12,d0` and its `dbf` */
#define RTC_FIRST_DIGIT      1          /* `moveq #1,d1`: register 1, then every second one */
#define RTC_REGISTER_STEP    2
#define RTC_DIGIT_MASK       0x0f       /* `andi.b #15` — the four bits a BCD digit really is */

/* ---- the process group's own constants ---------------------------------------------------------- */
/* `Setexc($102, -1)` — the TERMINATE VECTOR, read (never written) by `Pterm` before it unwinds. The
 * number is the BIOS's, so $102 * 4 = $408 is where it really lives; `Pterm` asks the BIOS rather
 * than reading $408 itself, which is why the case declares a BIOS call and not a longword. */
#define GEMDOS_TERM_VECTOR   0x102
#define SETEXC_INQUIRE      0xffffffffu /* ...and the handler value that means "report, do not set" */

/* `Pexec`'s four modes, as the two compares at $fc8184/$fc818c leave them: 0 and 3..5, and every
 * other word is EINVFN. They are not a range — 1 and 2 are the gaps the first `tst.w` and the
 * `cmpi.w #3` carve out. */
#define PEXEC_LOAD_AND_GO    0
#define PEXEC_LOAD           3
#define PEXEC_JUST_GO        4
#define PEXEC_CREATE_BASEPAGE 5
/* -33/-39: the file was not found, and there is not enough memory. `Pexec` is the only routine in
 * this group that answers either. */
#define GEMDOS_EFILNF       0xffffffdfu
#define GEMDOS_ENSMEM       0xffffffd9u
/* `cmpi.l #256` at $fc8300: a largest free block smaller than ONE BASEPAGE is refused before the
 * TPA is cut, which is also the size the basepage clear at $fc8398 writes. */
#define BASEPAGE_BYTES       256
/* `cmpi.w #125` at $fc849a — how much of the command tail is copied, NUL or no NUL. The tail lands
 * at `BASEPAGE_COMMAND_TAIL`, which is also where `p_dta` is pointed ($fc83b2). */
#define PEXEC_COMMAND_TAIL_MAX 125
/* Where `Pexec` parks the DISPATCHER's own termination record while its own is armed ($fc81c2) —
 * twelve bytes, the same three longwords `GEMDOS_TERMINATION_JMPBUF` holds. Here rather than in the
 * core because `test_gemdos_process_pexec.py` reads the copy back on both shores. */
#define PEXEC_OUTER_JMPBUF   0x7560
#define JMPBUF_BYTES         12

/* The child's initial stack, built downwards from `p_hitpa` ($fc851a..$fc8582): the basepage, a
 * zero, ten more zeros, the entry point, a zero WORD, and the return address below that. */
#define PEXEC_STACK_ZERO_LONGS 10
#define PEXEC_RETURN_ADDRESS 0x755a

/* ---- the cores ---------------------------------------------------------------------------------- */

/* $fc52f8 — the whole of `Fforce`, with the basepage as a parameter so that `Pexec` can force a
 * handle into the CHILD's. 0, or `GEMDOS_EIHNDL`. */
uint32_t gemdos_force_handle(uint8_t *image, int16_t standard, int16_t handle, uint32_t basepage);

/* $fc52de ($46) — the same thing on `p_run`. */
uint32_t gemdos_fforce(uint8_t *image, int16_t standard, int16_t handle);

/* $fc5216 ($45) — a new HANDLE RECORD naming whatever `standard` names. The new handle, or
 * `GEMDOS_EIHNDL` / `GEMDOS_ENHNDL`. */
uint32_t gemdos_fdup(uint8_t *image, int16_t standard);

/* $fc56c6 ($3e) — close a handle. Always 0 on the arms this reconstructs (see the core). */
uint32_t gemdos_fclose(uint8_t *image, int16_t handle);

/* $fc9924 — the dispatcher's own resolution of a handle ARGUMENT, walking `p_uft` and the table.
 * `arguments` is the caller's word list and `descriptor` the table's, because WHICH word holds the
 * handle is what the descriptor decides. */
int32_t gemdos_resolve_handle(const uint8_t *image, uint32_t arguments, uint16_t descriptor);

/* The handle table's record at a signed INDEX (`handle - 6` for a file handle): `muls.w #10` then
 * `addl #$8092`, no bound of the ROM's own — the host build asserts it stays in RAM. */
uint32_t gemdos_descriptor_at(int16_t index);

/* ...the record a HANDLE names. Every caller has already decided the handle is 6 or above, except
 * `Fdup`, which is where the negative displacement comes from. */
static inline uint32_t gemdos_descriptor_of(int16_t handle)
{
    return gemdos_descriptor_at((int16_t)(handle - GEMDOS_FIRST_FILE_HANDLE));
}

/* ...and a record given back: its value and its OWNER zeroed, which is what puts it back in the free
 * searches (`Fdup`'s, `$fc6f5c`'s). The reference count is left as it was. */
static inline void gemdos_release_descriptor(uint8_t *image, uint32_t descriptor)
{
    wr32(image + descriptor + HANDLE_VALUE, 0);
    wr32(image + descriptor + HANDLE_OWNER, 0);
}

/* $fc51c0 — the first longword of the record a handle names (via $fc5186, which reads `p_uft` for
 * 0..5): 0 for nothing, the file system's OFD for an open file. No bound, the ROM's own. */
int32_t gemdos_ofd_of_handle(const uint8_t *image, int16_t handle);

/* $fc51de — copy one `p_curdir` entry into `basepage` and bump the directory's reference count. */
void gemdos_inherit_curdir(uint8_t *image, int16_t entry, int16_t node, uint32_t basepage);

/* $fc8092 — everything a process owns, given back: its handles, its descriptors, its directories
 * and its memory. Called by `Pterm` and by `Pexec` when the load fails. */
void gemdos_release_process(uint8_t *image, uint32_t basepage);

/* $fc5092 — GEMDOS's clock re-read from the Mega ST's battery clock, which `Pterm` does on the way
 * out. A no-op on a machine without one, which is every plain ST. */
void gemdos_resync_clock(uint8_t *image);

/* $fc8028 ($4c), $fc8086 ($00), $fc7fd8 ($31). NONE OF THE THREE RETURNS TO ITS CALLER: each ends in
 * the trap entry's epilogue, whose `rte` resumes the PARENT's own GEMDOS call. What they return here
 * is the exit code they planted, which is what the host build has instead of an `rte` — the case is
 * a CHECKPOINT at the `jsr` (`test/gemdos_process.py`). */
uint32_t gemdos_pterm(uint8_t *image, uint16_t status);
uint32_t gemdos_pterm0(uint8_t *image);
uint32_t gemdos_ptermres(uint8_t *image, uint32_t keep, uint16_t status);

/* $fc817a ($4b) and the slice of it at $fc8242 that every mode but the refused one reaches. The
 * split is the dispatcher's: `Pexec` arms a termination record of its own between them, and that
 * record is the 68000 frame of the `jsr` that armed it (`src/gemdos/dispatch.c`). */
uint32_t gemdos_pexec(uint8_t *image, uint16_t mode, uint32_t name, uint32_t tail, uint32_t env);
uint32_t gemdos_pexec_create(uint8_t *image, uint16_t mode, uint32_t name, uint32_t tail,
                             uint32_t env);

#endif /* TOS102US_GEMDOS_PROCESS_H */
