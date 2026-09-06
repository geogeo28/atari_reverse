/* clib.h — the Alcyon/DRI C runtime linked into Bubble Ghost: the OS trap glue, the free-list
 * allocator, the low-level file layer and the software floating-point package.
 *
 * This is the compiler's own library rather than the game's code, so almost nothing here is
 * BubbleGhost-specific — but every address is, because the linker placed the library's state in
 * this program's BSS and DATA. Addresses are absolute (`include/globals.h`'s A4_BASE + the `n(a4)`
 * displacement the instructions carry), the way every subsystem header in this project spells them.
 *
 * WHAT VERIFIES EACH GROUP is in ../STATUS.md's "Verified — clib" section, one row per routine.
 */
#ifndef BG_CLIB_H
#define BG_CLIB_H

#include <stdint.h>

#include "machine.h"
#include "globals.h"

/* ================================================================================================
 * The OS trap trampolines — `gemdos_trap` @ 0x15e58, `xbios_trap` @ 0x15e3c
 *
 * Every GEMDOS and XBIOS call in the program goes through one of these six-instruction stubs. Each
 * parks A1, A2 and its own return address in three fixed longwords, traps, restores the two address
 * registers and returns — because TOS is free to clobber A1/A2 and the Alcyon compiler is not. The
 * three slots are the trampolines' WHOLE image effect, which is what makes them verifiable at all:
 * a reconstruction cannot execute a trap, so each wrapper below writes these three and then calls
 * the kit's model of the call itself (tools/recreate_kit/include/os.h).
 * ============================================================================================= */

/* The two address registers a trampoline parks, as the CALLER left them. The C ABI carries no such
 * thing, so every wrapper that traps takes them as an argument and files them where the trampoline
 * does — which is the whole of what a reconstruction can reproduce about the trap glue, and what
 * makes `gemdos_trap` and `xbios_trap` verifiable rather than merely read. */
typedef struct {
    uint32_t a1;
    uint32_t a2;
} CallerAddressRegisters;

#define A_trap_saved_ret 0x1e932u   /* longword: the trampoline's own return address, popped off the
                                     * stack so the selector word ends up at 2(sp) where TOS reads
                                     * it, and pushed back before the `rts` */
#define A_trap_saved_a2  0x1e936u   /* longword: A2 across the trap */
#define A_trap_saved_a1  0x1e93au   /* longword: A1 across the trap */

/* Where each wrapper's `jsr` to the trampoline returns to — the byte after the `jsr`, which is what
 * the trampoline files in A_trap_saved_ret. One per wrapper because it is a call-site constant, not
 * a value any of them computes. */
/* `xbios_trap` has no RET_* of its own: it is entered from all over the program, so the address it
 * files is its CALLER's and the case declares it. */
#define RET_GEMDOS_MALLOC          0x15c92u
#define RET_GEMDOS_MFREE           0x15ca8u
#define RET_GEMDOS_MALLOC_OR_FAIL  0x167e0u
#define RET_C_CLOSE_FCLOSE         0x14c64u
#define RET_C_CREAT_FCREATE        0x14cc2u
#define RET_C_OPEN_FOPEN           0x15e0au
#define RET_C_READ_FREAD_FIRST     0x166feu   /* the read that fills the caller's buffer */
#define RET_C_READ_FREAD_REFILL    0x16762u   /* ...and the text mode's top-up read */

/* ...and the same for the buffered layer and the console, one per trap site. Several routines trap
 * from more than one place, and WHICH site ran is the only thing a case can see about a trampoline
 * that is otherwise a no-op — so each one is named where it is used rather than derived. */
#define RET_C_FILBUF_FSEEK         0x14f28u   /* c_filbuf asks GEMDOS where the file is directly,
                                              * rather than through c_lseek */
#define RET_C_LSEEK_FSEEK          0x15a06u   /* the seek c_lseek answers with when it succeeds. Its
                                              * four OTHER sites (0x15a30, 0x15a4a, 0x15ab0,
                                              * 0x15ac6) are the failure path, which src/clib.c does
                                              * NOT transcribe and no case reaches — so they get no
                                              * constant here either; ../STATUS.md has the residual */
#define RET_C_WRITE_FWRITE_RUN     0x16cc8u   /* c_write's three: the run of bytes before a newline, */
#define RET_C_WRITE_FWRITE_CRLF    0x16cfeu   /* the CR/LF pair the newline expands to, */
#define RET_C_WRITE_FWRITE_TAIL    0x16d60u   /* and the tail — the whole buffer, in binary mode */
#define RET_C_CONOUT_CR            0x16b7eu   /* c_conout_write's two: the CR it prefixes a newline
                                              * with, and the byte itself */
#define RET_C_CONOUT_BYTE          0x16b96u
#define RET_C_CONIN_CRAWCIN        0x1654au   /* c_conin's blocking read... */
#define RET_C_CONIN_ECHO_ESC       0x1656eu   /* ...and its echoes: ESC then 'D' backs the cursor up
                                              * over a rubbed-out character, */
#define RET_C_CONIN_ECHO_LEFT      0x1657cu
#define RET_C_CONIN_ECHO_EOL_CR    0x165a8u   /* CR then LF ends the line on RETURN, */
#define RET_C_CONIN_ECHO_EOL_LF    0x165b6u
#define RET_C_CONIN_ECHO_EOF_CR    0x165f4u   /* the same pair on the end-of-file character — a
                                              * SECOND pair of sites, not the one above, */
#define RET_C_CONIN_ECHO_EOF_LF    0x16602u
#define RET_C_CONIN_ECHO_CHAR      0x16626u   /* and every ordinary character echoes itself */

/* THE TRAMPOLINE'S WHOLE IMAGE EFFECT, in one place. Both stubs write these three longwords and
 * nothing else, so every wrapper that traps calls this instead of spelling the three stores again —
 * `src/clib.c`'s wrappers and `src/sound.c`'s two `Supexec` callers, which carried a second copy
 * until this moved here. It is a header inline rather than a function because it is the only thing
 * two translation units share and a `.c` for three stores would be its own file. */
static inline void trap_save_registers(uint8_t *image, CallerAddressRegisters saved,
                                       uint32_t return_pc) {
    wr32(image + A_trap_saved_a1, saved.a1);
    wr32(image + A_trap_saved_a2, saved.a2);
    wr32(image + A_trap_saved_ret, return_pc);
}

/* ...and the block itself, built from the two values a case hands the candidate. EVERY glue
 * function in this reconstruction opens with one, and each of `src/clib.c`, `src/frontend.c` and
 * `src/gameplay.c` carried its own spelling until this moved here.
 *
 * BY VALUE, because that is what a routine which traps and then returns wants: it files what its
 * caller was holding and nothing it does travels back. The `*_reporting` forms below are the other
 * shape — a POINTER, for a routine whose own callees change A1 in a way the CALLER's later traps
 * then file (`c_getfdmode` leaving A1 at `A_c_errno`). `include/frontend.h` says which routines
 * thread the pointer form and why. */
static inline CallerAddressRegisters caller_registers(uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = {a1, a2};
    return saved;
}

/* ================================================================================================
 * Shared C-library state
 * ============================================================================================= */

#define A_c_errno 0x1ea6eu          /* word: the last GEMDOS return code the library saw */

/* ================================================================================================
 * The free-list allocator — `c_malloc` @ 0x15b54, `c_free` @ 0x15bfe, `c_morecore` @ 0x15af2
 *
 * A textbook K&R circular free list. Every block carries a six-byte header — a `next` pointer and a
 * size in GRANULES — and `c_malloc` hands back the address just past the header of the block it
 * carved. The list is kept in ascending address order and `c_free` coalesces with the neighbour on
 * each side.
 * ============================================================================================= */

#define A_c_malloc_freelist 0x1ea70u /* longword: the roving pointer c_malloc searches from. Zero
                                      * until the first allocation, which self-initialises the list
                                      * to the empty sentinel below */
#define A_c_malloc_sentinel 0x1ea74u /* the zero-length block the empty list points at: its `next`
                                      * is itself and its size word (0x1ea78) is 0 */

#define MALLOC_GRANULE      6u       /* bytes per granule — also the header's own size, so a block
                                      * of n granules spans n*6 bytes INCLUDING its header */
#define FREE_OFF_NEXT       0u       /* longword: the next free block, ascending, wrapping */
#define FREE_OFF_SIZE       4u       /* word: the block's size in granules, header included */
#define FREE_HEADER_BYTES   6u       /* = MALLOC_GRANULE; what c_malloc adds to reach the payload */

/* c_morecore rounds its request up to a whole number of these and asks GEMDOS for that many
 * granules — 0x418 granules is 6,288 bytes, the library's arena quantum. */
#define MORECORE_QUANTUM_GRANULES 0x418u

/* ================================================================================================
 * The fd-mode side table — `c_setfdmode` @ 0x15cae, `c_clearfdmode` @ 0x15cfa, `c_getfdmode` 0x15d36
 *
 * GEMDOS handles carry no text/binary flag, so the library keeps its own: 76 (handle, mode) word
 * pairs, searched linearly. `c_read` and `c_write` ask it whether to translate CR/LF.
 * ============================================================================================= */

#define A_fd_mode_table   0x1e93eu
#define FD_MODE_SLOTS     0x4cu      /* 76 — the loop bound all three routines carry */
#define FD_MODE_ENTRY     4u         /* handle word, then mode word */
#define FD_MODE_OFF_FD    0u
#define FD_MODE_OFF_MODE  2u
#define FD_MODE_BINARY    0x2000u    /* the one mode bit anything sets; 0 means text */

/* WHERE c_getfdmode READS WHEN THE HANDLE IS NOT IN THE TABLE. Its loop tests, steps, and stops
 * when the cursor reaches the table's end — so an exhausted search leaves the cursor one entry PAST
 * the last slot and the `move.w 2(a0),d0` that follows reads a word that is not in the table at
 * all. `A_fd_mode_table + FD_MODE_SLOTS * FD_MODE_ENTRY + FD_MODE_OFF_MODE` is A_c_malloc_freelist,
 * so an unknown handle is answered with the HIGH HALF OF THE ALLOCATOR'S ROVING POINTER: zero until
 * something has allocated, and the arena's high word afterwards. Reproduced rather than fixed, and
 * src/clib.c holds the `_Static_assert` that keeps the two addresses equal.
 */

/* ================================================================================================
 * The low-level file layer — `c_open` 0x15d64, `c_creat` 0x14c7a, `c_close` 0x14c3c, `c_read` 0x1667c
 *
 * Three names are intercepted before GEMDOS ever sees them and answered with a pseudo-handle, which
 * is why the handles are large NEGATIVE words: a real GEMDOS handle is a small positive number, so
 * `handle > FD_DEVICE_CON` (a SIGNED word compare) is the library's test for "a real file".
 * ============================================================================================= */

#define FD_DEVICE_CON 0x8300u        /* "CON:" — the console, as a word: -32000 */
#define FD_DEVICE_AUX 0x82ffu        /* "AUX:" — the serial port */
#define FD_DEVICE_PRT 0x82feu        /* "PRT:" — the printer */

/* The two copies of the device-name table the linker emitted, one per caller. Each is three
 * NUL-terminated names on a six-byte stride, in CON:/AUX:/PRT: order. */
#define A_creat_device_names 0x251c6u   /* c_creat compares against this copy */
#define A_open_device_names  0x251ecu   /* ...and c_open against this one */
#define DEVICE_NAME_STRIDE   6u

#define OPEN_MODE_TRUNCATE 0x0001u   /* bit 0: unlink the file first (GEMDOS Fdelete) */
#define OPEN_MODE_WRITE    0x0002u   /* what c_creat asks c_open for */

#define TEXT_MODE_CR 0x0du           /* the byte c_read's text path drops */

/* ================================================================================================
 * The buffered `FILE` layer — `c_fopen` 0x156e2, `c_fclose` 0x14d72, `c_fflush` 0x14dc4,
 * `c_filbuf` 0x14e80, `c_flsbuf` 0x14fb0, `c_putc` 0x150ee, `c_fread` 0x15878
 *
 * THE RECORD IS FROZEN. Seven fields on a 20-byte stride, read off the post-init image and pinned
 * by the battery: every routine below indexes it, so nobody adds a field to it. Each field's
 * provenance is its tag — `pinned` means a case would fail if the offset were wrong.
 * ============================================================================================= */

#define A_c_iob        0x1eb08u      /* the 73 records themselves, ending at C_IOB_END */
#define C_IOB_SLOTS    73u
#define C_IOB_STRIDE   20u
#define C_IOB_END      0x1f0bcu      /* = A_c_iob + C_IOB_SLOTS * C_IOB_STRIDE; the bound c_fopen
                                      * and c_exit both spell as `A_c_iob + 0x5b4` */
#define A_c_stdout     0x1eb1cu      /* = A_c_iob + C_IOB_STRIDE — record 1, which `c_printf` writes
                                      * to and `c_filbuf` flushes before it reads the console */

#define FILE_OFF_PTR    0u           /* long: the next byte to hand out or to fill  (pinned) */
#define FILE_OFF_CNT    4u           /* word: how many more times PTR may step before the buffer
                                      * has to be refilled or flushed                (pinned) */
#define FILE_OFF_BASE   6u           /* long: the buffer                             (pinned) */
#define FILE_OFF_FLAGS  10u          /* word: the FILE_* bits below                  (pinned) */
#define FILE_OFF_FD     12u          /* word: the c_open handle, or a pseudo-device  (pinned) */
#define FILE_OFF_OFFSET 14u          /* long: the file position the BUFFER starts at (pinned) */
#define FILE_OFF_BUFSIZ 18u          /* word: how big the buffer is                  (pinned) */

/* The flag bits, each named from what the routines below do with it rather than from a header this
 * program does not ship. `init_globals` establishes three records: stdin as READ|UNBUFFERED and
 * both stdout and stderr as WRITE|LINEBUF, all three on the CON: pseudo-handle. */
#define FILE_READ       0x0001u      /* opened for reading */
#define FILE_WRITE      0x0002u      /* ...or for writing; "READ or WRITE" is "this slot is in use" */
#define FILE_APPEND     0x0004u      /* seek to the end before every flush */
#define FILE_UNBUFFERED 0x0008u      /* no buffer: one byte at a time, through A_c_unbuf_chars */
#define FILE_MYBUF      0x0010u      /* the buffer came from GEMDOS Malloc, so c_fclose Mfrees it */
#define FILE_EOF        0x0020u      /* the last refill hit end of file */
#define FILE_ERR        0x0040u      /* ...or failed */
#define FILE_DIRTY      0x0080u      /* the buffer holds bytes nobody has written out yet */
#define FILE_LINEBUF    0x0100u      /* flush at every newline, and after a full buffer */
#define FILE_IN_USE     (FILE_READ | FILE_WRITE)
#define FILE_AT_END     (FILE_EOF | FILE_ERR)          /* c_filbuf refuses to refill past either */
#define FILE_BYTE_AT_A_TIME (FILE_UNBUFFERED | FILE_LINEBUF)  /* both ask c_read for ONE byte */

#define A_c_unbuf_chars 0x1eabcu     /* C_IOB_SLOTS single bytes, one per record: where an
                                      * UNBUFFERED stream's buffer points when Malloc failed or
                                      * was never asked. c_filbuf and c_flsbuf index it by the
                                      * record's own slot number */
#define A_c_bufsiz      0x1eb06u     /* word: 0x200, the buffer size c_fopen gives a new stream */
#define A_c_fopen_slot_hint 0x1ea7au /* long: a FILE c_fopen should reuse before scanning for a free
                                      * one. Zero after init_globals, and cleared again on use;
                                      * nothing in this program ever sets it */

/* c_fopen's mode string: an optional 'b', then one of r/w/a, then an optional '+'. The game's own
 * two calls pass "br". */
#define FOPEN_MODE_BINARY_PREFIX 'b'
#define FOPEN_MODE_READ          'r'
#define FOPEN_MODE_WRITE         'w'
#define FOPEN_MODE_APPEND        'a'
#define FOPEN_MODE_UPDATE        '+'

#define TEXT_MODE_LF 0x0au           /* the byte c_write expands and c_flsbuf flushes a line at */

/* ================================================================================================
 * The console — `c_conout_write` 0x16b5e, `c_conin` 0x16518
 *
 * `c_write` routes the three pseudo-handles to a per-device writer; only CON:'s is reconstructed
 * (see src/clib.c). `c_conin` is the cooked reader behind them: it echoes as it goes and hands the
 * caller one character of a line at a time, so it keeps a line buffer of its own.
 * ============================================================================================= */

#define A_c_conin_read_pos 0x1e8deu  /* word: how far the caller has taken the line apart */
#define A_c_conin_length   0x1e8e0u  /* word: ...and how much of it c_conin has gathered */
#define A_c_conin_buffer   0x1e8e2u  /* the line itself */

#define CONIN_BACKSPACE 0x08u        /* rubs the last character out, and echoes ESC 'D' */
#define CONIN_RETURN    0x0du        /* ends the line: a LF is stored, a CR/LF pair echoed */
#define CONIN_INTERRUPT 0x03u        /* ^C — the library terminates the program here */
#define CONIN_EOF       0x1au        /* ^Z — stored, echoed, and answered as -1 when read back */
#define CONIN_ECHO_ESCAPE   0x1bu    /* the two bytes that back the cursor up over a rubbed-out */
#define CONIN_ECHO_LEFT     'D'      /* character (VT52 "cursor left") */
#define CONIN_EXIT_STATUS   2u       /* what ^C passes to c_exit */

/* ================================================================================================
 * The printf engine — `c_printf` 0x164c2, `c_vfprintf` 0x16496, `c_sprintf` 0x164d8,
 * `c_fputs` 0x164ee, `c_doprnt` 0x1620c, `c_fmt_integer` 0x15e74, `c_fmt_getnum` 0x161b8,
 * `c_fmt_float` 0x15fe0, `c_fcvt` 0x15588
 * ============================================================================================= */

/* WHAT `c_doprnt` UNDERSTANDS, read off its own dispatch chain: `%[-][0][width][.precision][l]`
 * and then one of these. There is no `%%`, no `+`/space flag, no `*` width, no `p`/`n`/`i`; an
 * unrecognised conversion character is copied out as itself. */
#define FMT_CONV_SIGNED    'd'       /* the four integer conversions, which share c_fmt_integer */
#define FMT_CONV_UNSIGNED  'u'
#define FMT_CONV_OCTAL     'o'
#define FMT_CONV_HEX       'x'
#define FMT_CONV_CHAR      'c'
#define FMT_CONV_STRING    's'
/* The three float conversions share c_fmt_float, which tells them apart by 'f' ALONE: 'e' and 'g'
 * take the same path, so %g formats as %e. */
#define FMT_CONV_EXPONENT  'e'
#define FMT_CONV_FIXED     'f'
#define FMT_CONV_GENERAL   'g'
#define FMT_FLAG_LEFT      '-'
#define FMT_FLAG_ZERO      '0'
#define FMT_PRECISION_MARK '.'
#define FMT_LONG_MARK      'l'
#define FMT_ESCAPE         '%'

#define FMT_BASE_DECIMAL 10u
#define FMT_BASE_OCTAL    8u
#define FMT_BASE_HEX     16u
#define FMT_DIGIT_SLOTS  20u         /* c_fmt_integer's own `-40(a6)` scratch: 20 WORDS, one digit
                                      * each, emitted in reverse. Base 8 of a longword is 11 */
#define FMT_HEX_LETTER_BASE 'A'      /* a digit of 10 or more prints as 'A'..'F' */
/* What is left of a longword after one `asr.l` step of the octal and hex digit loops: the shift
 * fills from the sign bit, and these clear the fill again. */
#define FMT_OCTAL_STEP_MASK 0x1fffffffu
#define FMT_HEX_STEP_MASK   0x0fffffffu

#define FMT_NO_PRECISION 0x0100u     /* c_doprnt's "no `.` was given". It is a real 256, not a
                                      * sentinel outside the range: `%.256s` and `%s` are the same
                                      * format to this engine, and `c_fmt_float` reads it as "use
                                      * six digits" */
#define FMT_FLOAT_DEFAULT_PRECISION 6u

#define A_fcvt_ten          0x1eab4u /* the double c_fcvt scales by. init_globals writes
                                      * 0x4024000000000001 — ten, one ulp high */
#define A_fcvt_max_digits   0x1eaa6u /* word: 7, the most digits %f will ask c_fcvt for */
#define A_fmt_float_zero    0x251feu /* the double c_fmt_float compares against to find the sign */
#define A_fmt_float_exponent_format 0x25206u  /* "%d" — c_fmt_float prints its exponent through
                                               * c_sprintf, so the engine calls itself */
#define A_crlf              0x2520au /* the two bytes c_write expands a newline to */
#define CRLF_BYTES          2u

/* THE TWO PIECES OF SCRATCH A RECONSTRUCTION CANNOT PUT ON ITS OWN STACK.
 *
 * `c_fcvt` scales its working copy of the value with `fp_mul`/`fp_div`, and `c_vfprintf` formats
 * into a buffer that `c_fputs` then walks with `c_strlen`-shaped code — both of those read and
 * write the IMAGE by address, so the bytes have to live in the image. The originals are frame
 * locals (`-14(a6)` and `-256(a6)`); a reconstruction has no frame in the image at all, so it
 * names two addresses inside the band the differential DROPS as stack, which is where the
 * original's are too.
 *
 * NEITHER IS PINNED, and that is the honest statement rather than an oversight: both sides write
 * into a region nothing compares, so a candidate using different addresses would still be green.
 * What IS pinned is what each produces — `A_fp_acc` and the digits c_fcvt hands back for the
 * first, and the bytes c_fputs pushes into the FILE for the second. */
#define CLIB_SCRATCH_BASE 0x000ffb00u  /* = emu.STACK_TOP - emu.STACK_SCRATCH, the LOWEST address
                                           * the kit still reads as a call frame's own: below it a
                                           * write is "program output, not stack" and the oracle's
                                           * half of that check would call it one
                                           * (tools/recreate_kit/oracle/emu.py, STACK_SCRATCH) */
#define C_FCVT_DOUBLE_BYTES     8u        /* the working copy c_fcvt scales */
#define C_EXPONENT_ARGS_BYTES   6u        /* the list c_fmt_float hands c_sprintf: a `char *` then
                                           * the exponent as a word */
#define C_EXPONENT_ARGS_OFF_VALUE 4u      /* ...and where that word sits in it */
#define C_VFPRINTF_BUFFER_BYTES 256u      /* c_vfprintf's `link a6,#$fefe` reserves exactly this */

/* THE BUFFER IS LAST ON PURPOSE. It is the one span with no bound on what is written into it — a
 * format producing more than 256 bytes runs off the end — so it is placed ABOVE the other two, into
 * unused band, rather than below them where an overrun would land on c_fcvt's working double. That
 * is the direction the original overruns too: its `-256(a6)` buffer grows up into its own frame. */
#define CLIB_SCRATCH_FCVT_DOUBLE      CLIB_SCRATCH_BASE
#define CLIB_SCRATCH_EXPONENT_ARGS    (CLIB_SCRATCH_FCVT_DOUBLE + C_FCVT_DOUBLE_BYTES)
#define CLIB_SCRATCH_VFPRINTF_BUFFER  (CLIB_SCRATCH_EXPONENT_ARGS + C_EXPONENT_ARGS_BYTES)
#define CLIB_SCRATCH_BYTES (C_FCVT_DOUBLE_BYTES + C_EXPONENT_ARGS_BYTES + C_VFPRINTF_BUFFER_BYTES)

/* How many digits `c_fcvt` may be asked for. The original writes them into `c_fmt_float`'s own
 * 30-byte frame and would smash it for a precision much past 25; the reconstruction holds them in a
 * C array this size instead, and ../STATUS.md records the overflow as read-verified rather than
 * pretending it is reproduced.
 *
 * IT IS A BOUND THE CODE ENFORCES, not a comment. `c_fcvt` writes `ndigits + 3` bytes, and
 * `c_fmt_float` takes its `ndigits` from a PRECISION IN THE FORMAT STRING — so `%.70f` would run
 * off the end of the array. That is a wild write in the harness's own process, which arrives as an
 * xdist worker vanishing rather than as a diff, so `c_fmt_float` refuses such a precision through
 * `os_refused` and reddens the run by name instead. */
#define C_FCVT_DIGITS_MAX 64u
#define C_FCVT_DIGITS_OVERHEAD 3u    /* ...the bytes c_fcvt writes beyond `ndigits`: the leading
                                      * digit, the one the rounding needs, and the terminator */
#define C_FCVT_NDIGITS_MAX (C_FCVT_DIGITS_MAX - C_FCVT_DIGITS_OVERHEAD)

/* ================================================================================================
 * The software floating-point package — `fp_dispatch` @ 0x153fe and the seven routines it calls
 *
 * THE WORKING FORM IS NOT AN IEEE DOUBLE. Every arithmetic routine unpacks its operands into a
 * 32-BIT mantissa whose implicit leading 1 sits in bit 31 and an 11-bit biased exponent, does its
 * work there, and repacks. The 21 lowest mantissa bits of an IEEE double are therefore DISCARDED on
 * the way in and rebuilt as zeros on the way out — this package carries about 32 bits of precision,
 * not 53, and that is what decides the demo/slideshow ranges the front end computes from
 * XBIOS Random (../names.txt, the plate at 0x115d6).
 * ============================================================================================= */

#define A_fp_op_table       0x1ea7eu /* 7 longwords, indexed by fp_dispatch's low opcode byte. Each
                                      * points into the `jmp` island at BG_LOAD_BASE rather than at
                                      * the routine, which is how the linker resolved them */
#define A_fp_acc            0x1ea9au /* the 8-byte accumulator fp_acc_load_long / fp_acc_to_long use */
#define A_fp_sub_sign_flag  0x1eaa2u /* word: 0x8000 when fp_sub entered the shared add body, 0 when
                                      * fp_add did. The body XORs it back into the SOURCE's sign
                                      * word on the way out, undoing the flip fp_sub made */
#define A_fp_ccr            0x1eaa4u /* word: the whole SR fp_cmp captured, which fp_dispatch loads
                                      * back into the real CCR so a float compare can be followed by
                                      * an ordinary Bcc */

#define FP_OP_ADD          0u
#define FP_OP_SUB          1u
#define FP_OP_MUL          2u
#define FP_OP_DIV          3u
#define FP_OP_CMP          4u
#define FP_OP_SELECTOR     0x00ffu   /* the low byte of fp_dispatch's opcode word indexes the table */
#define FP_OP_SOURCE_KIND  0xff00u   /* ...and the high byte says what the source operand IS */
#define FP_SOURCE_SHORT    0x2000u   /* a 16-bit int, widened through fp_long_to_double */
#define FP_SOURCE_LONG     0x2800u   /* a 32-bit int, likewise */
#define FP_SOURCE_FLOAT    0x1000u   /* a 32-bit float, widened through fp_float_to_double */
#define FP_SOURCE_DOUBLE   0x0800u   /* ...and this one means the source already IS an
                                      * eight-byte double, passed through untouched. It is what
                                      * the game's own four call sites carry, and what
                                      * `c_fmt_float` asks for when it looks at a value's sign;
                                      * fp_dispatch reaches it as the `else` of the three above. */

#define FP_EXPONENT_BITS   0x07ffu   /* the 11-bit biased exponent, once shifted down out of word 0 */
#define FP_EXPONENT_SHIFT  4u        /* ...and how far down: the mantissa's top nibble is below it */
#define FP_SIGN_BIT        0x8000u   /* word 0's bit 15 */
#define FP_EXPONENT_BIAS   0x03ffu   /* what a stored exponent is biased by: `c_fcvt` subtracts it to
                                      * get a value's true binary exponent, and `fp_mul` folds the
                                      * two operands' exponents with it (e = ea - BIAS + eb) */
#define FP_BIAS_DIV        0x03feu   /* fp_div's:                e = ea - eb + this */
#define FP_LONG_EXPONENT   0x041du   /* fp_long_to_double presets this before normalising */
#define FP_TRUNC_EXPONENT  0x041eu   /* fp_double_to_long's "the point is here" exponent */

/* fp_pack_double's rounding: bit 8 is the guard bit, and the mask below is the guard bit plus the
 * sticky bits under it — an exact halfway with nothing beneath it rounds to even by doing nothing. */
#define FP_ROUND_GUARD_DOUBLE  0x0100u
#define FP_ROUND_STICKY_DOUBLE 0x02ffu
#define FP_ROUND_INCREMENT_DOUBLE 0x0100u
#define FP_ROUND_INCREMENT_FLOAT  0x0200u   /* the single-precision tail rounds one bit higher */

/* ================================================================================================
 * Cores and glue
 * ============================================================================================= */

/* --- string and 32-bit arithmetic --- */
uint32_t c_strlen(const uint8_t *image, uint32_t str);
int16_t  c_strcmp(const uint8_t *image, uint32_t left, uint32_t right);
void     c_ldiv(uint32_t divisor, uint32_t dividend, uint32_t *quotient, uint32_t *remainder);
uint32_t c_lmul(uint32_t left, uint32_t right);

/* --- the fd-mode side table --- */
void     c_setfdmode(uint8_t *image, uint16_t handle, uint16_t mode);
void     c_clearfdmode(uint8_t *image, uint16_t handle);
uint16_t c_getfdmode(const uint8_t *image, uint16_t handle);

/* --- the runtime's startup hooks --- */
void     crt0_setup_args(uint8_t *image, uint32_t command_tail);

/* --- the allocator --- */
uint32_t c_malloc(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved);
void     c_free(uint8_t *image, uint32_t payload);
uint32_t c_morecore(uint8_t *image, uint16_t granules_wanted, CallerAddressRegisters saved);
uint32_t gemdos_malloc(uint8_t *image, uint32_t bytes, CallerAddressRegisters saved);
uint32_t gemdos_mfree(uint8_t *image, uint32_t block, CallerAddressRegisters saved);
uint32_t gemdos_malloc_or_fail(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved);

/* --- the file layer --- */
int16_t  c_open(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved);
int16_t  c_creat(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved);
int16_t  c_close(uint8_t *image, uint16_t handle, CallerAddressRegisters saved);
int32_t  c_read(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
                CallerAddressRegisters saved);

/* THE SAME TWO ROUTINES, REPORTING THE A1 THEY LEAVE BEHIND. Both ask the fd-mode table, and
 * `c_getfdmode` comes back with A1 one entry past it (= `A_c_errno`) — so every trap the CALLER
 * reaches afterwards files that, not what it was holding before. The buffered layer below carries
 * the register block by pointer for exactly this; a caller elsewhere that makes several of these
 * calls in a row wants these forms rather than re-deriving `A_c_errno` after each one. */
int32_t  c_read_reporting(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
                          CallerAddressRegisters *saved);
int16_t  c_write_reporting(uint8_t *image, uint16_t handle, uint32_t buffer, int16_t length,
                           CallerAddressRegisters *saved);

/* --- the buffered FILE layer --- */
uint32_t c_fopen(uint8_t *image, uint32_t path, uint32_t mode, CallerAddressRegisters saved);
int16_t  c_fclose(uint8_t *image, uint32_t file, CallerAddressRegisters *saved);
int16_t  c_fflush(uint8_t *image, uint32_t file, CallerAddressRegisters *saved);
int16_t  c_filbuf(uint8_t *image, uint32_t file, CallerAddressRegisters *saved);
int16_t  c_flsbuf(uint8_t *image, uint16_t byte, uint32_t file, CallerAddressRegisters *saved);
int16_t  c_putc(uint8_t *image, uint16_t byte, uint32_t file, CallerAddressRegisters *saved);
int16_t  c_fread(uint8_t *image, uint32_t buffer, int16_t size, int16_t items, uint32_t file,
                 CallerAddressRegisters *saved);
int32_t  c_lseek(uint8_t *image, int16_t handle, int32_t offset, int16_t whence,
                 CallerAddressRegisters saved);

/* --- the console, and the per-device writer c_write picks --- */
int16_t  c_write(uint8_t *image, uint16_t handle, uint32_t buffer, int16_t length,
                 CallerAddressRegisters saved);
void     c_conout_write(uint8_t *image, uint32_t buffer, int16_t length,
                        CallerAddressRegisters saved);
int16_t  c_conin(uint8_t *image, uint16_t handle, CallerAddressRegisters saved);

/* --- the printf engine ---
 *
 * WHAT THE ENGINE INHERITS FROM ITS CALLER'S MACHINE STATE rather than from an argument. Two
 * values, both real, neither derivable inside the routine that reads it, so both are threaded from
 * the top of the chain (docs/agent-playbook.md §5, "a parameter"):
 *
 *   * `inherited_conversion` — `c_doprnt` keeps its conversion character in D7 and SKIPS THE LOAD
 *     when the format ends in a bare `%`, dispatching on whatever D7 held on entry. The same word
 *     reaches `c_fmt_integer`, which likewise leaves D7 alone unless the conversion is one of
 *     d/u/o/x — so an unrecognised conversion is formatted in a BASE of the caller's making.
 *   * `status_high` — the status register above the condition codes. `c_fmt_float` finds a value's
 *     sign with `fp_dispatch`'s compare, and `fp_cmp` stores the WHOLE SR at `A_fp_ccr`, which the
 *     image diff compares — so the reconstruction has to be told the half it cannot compute.
 */
typedef struct {
    uint16_t inherited_conversion;
    uint16_t status_high;
} PrintfCallerState;

/* `out_cursor` is the original's `char **`: the emitters ADVANCE the caller's own pointer, which
 * for `c_doprnt` is its argument slot and for a direct-entry case is a cell in the image. */
int16_t  c_fmt_getnum(const uint8_t *image, uint32_t *cursor);
void     c_fmt_integer(uint8_t *image, uint16_t conversion, uint16_t is_long, uint32_t *out_cursor,
                       int32_t value, uint16_t base_when_conversion_unknown);
void     c_fmt_float(uint8_t *image, uint16_t conversion, int16_t precision, uint32_t *out_cursor,
                     uint32_t value_high, uint32_t value_low, PrintfCallerState caller);
void     c_fcvt(uint8_t *image, uint32_t value_high, uint32_t value_low, uint8_t *digits,
                int16_t *decimal_point, int16_t ndigits);
int32_t  c_doprnt(uint8_t *image, uint32_t out, uint32_t argp, PrintfCallerState caller);
int32_t  c_sprintf(uint8_t *image, uint32_t out, uint32_t argp, PrintfCallerState caller);
int16_t  c_vfprintf(uint8_t *image, uint32_t file, uint32_t argp, PrintfCallerState caller,
                    CallerAddressRegisters *saved);
int16_t  c_printf(uint8_t *image, uint32_t argp, PrintfCallerState caller,
                  CallerAddressRegisters *saved);
void     c_fputs(uint8_t *image, uint32_t text, uint32_t file, CallerAddressRegisters *saved);

/* --- the floating-point package --- */
void     fp_pack_double(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent);
void     fp_pack_float(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent);
void     fp_long_to_double(uint8_t *image, uint32_t operand);
void     fp_float_to_double(uint8_t *image, uint32_t operand);
void     fp_double_to_long(uint8_t *image, uint32_t operand);
void     fp_acc_load_long(uint8_t *image, uint32_t value);
uint32_t fp_acc_to_long(uint8_t *image);
void     fp_add(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_sub(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_mul(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_div(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_cmp(uint8_t *image, uint32_t left, uint32_t right, uint16_t status_high);
void     fp_dispatch(uint8_t *image, uint16_t opcode, uint32_t dst, uint32_t src,
                     uint32_t widen_scratch, uint16_t status_high);

/* --- the XBIOS trampoline, exercised through one modeled call --- */
uint32_t xbios_physbase(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc);

#endif /* BG_CLIB_H */
