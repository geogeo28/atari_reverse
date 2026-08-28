/* tos.ld — link the demo at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * rodata folds into text so it is reachable; .bss (the 1 MiB image) is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary.
 *
 * GEMDOS places BSS immediately after text+data (at tlen+dlen), so .bss MUST start there with no
 * gap. A BSS symbol with a large alignment (e.g. the 256-aligned screen image) would otherwise
 * push .bss past the end of the emitted binary, and every BSS access on-target would land at the
 * wrong address (the classic "handle 0 / silent corruption" bug). We force text+data — and hence
 * the whole load — to a 256-byte boundary and cap per-symbol alignment inside .bss at a WORD
 * (SUBALIGN 2), so .bss abuts text+data exactly while the 256-aligned load base keeps the image
 * page-aligned.
 *
 * IT IS SUBALIGN(2) AND NOT SUBALIGN(1), AND THE DIFFERENCE IS AN ADDRESS ERROR. Packing .bss at
 * BYTE granularity strips the word alignment the 68000 requires of every `move.w`/`move.l`, so a
 * longword in .bss lands on an odd address whenever the object before it has odd size, and the
 * program dies at its first store to it. Nothing in the C can defend against it, because SUBALIGN
 * overrides a variable's own `__attribute__((aligned))`; and build.sh's `--gc-sections` re-rolls
 * that dice EVERY BUILD, because collecting an unreferenced datum reshuffles .bss and the odd-size
 * neighbour is then produced by the linker's reachability walk rather than by an edit anyone made.
 * The cap costs at most one padding byte per object and moves nothing else: the dot is already
 * 256-aligned when `.bss` opens, so a 2-aligned output section still abuts text+data exactly.
 * BOTH FAULTS AND BOTH REPRODUCTIONS ARE IN ../STATUS.md ("## Performance", 2026-08-26), which is
 * canonical for them; the surface that caught them is `python3 atari/smoke.py floppy`.
 *
 * COPIED FROM projects/joust/recreate/atari/tos.ld, and the two have DIVERGED: this one carries
 * the `.text` KEEP and the SUBALIGN(2) cap below, and Joust's does not, because Joust does not
 * link with --gc-sections and has not met the alignment fault. Both belong there the day it does —
 * the KEEP is inert without the collector, and SUBALIGN(2) is a correctness fix that costs a
 * padding byte per object. Everything else is still identical and a change to it belongs in both.
 * Copied rather than moved kit-side for mkprg.py's reason; registered as
 * a kit candidate in ../STATUS.md's batch 43 phase A queue.
 */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS
{
  . = 0;
  .text : {
    /* THE KEEP IS THE .s FILE'S WHOLE `.text` — `_start`, the ten TOS trap wrappers, and
     * `wb_vbl_entry`/`wb_acia_entry` — every one of which is entered from the vector table or from
     * GEMDOS at RUNTIME, which no relocation names and build.sh's `--gc-sections` therefore cannot
     * see. It names THAT ONE OBJECT (build.sh keys objects `<directory>_<file.ext>.o` through its
     * `unit_key`) and not `*(.text)`, which would root every plain `.text` in the link — libgcc's
     * members included — keeping bodies the collector should drop and reordering the placement.
     * Inert today, because ENTRY(_start) already roots this section and the whole file is in it;
     * it is here for the day that stops being true, where the failure would be a machine that
     * hangs rather than a link that complains. ../STATUS.md has the measurement. */
    /* COPIED from projects/wonderboy/recreate/atari/tos.ld; the ONE edit is this object name:
     * this build's entry/wrapper/interrupt file is audio_os.s (see the Makefile). */
    KEEP(*audio_os.o(.text))
    *(.text._start)
    *(.text .text.*)
    *(.rodata .rodata.*)
  }
  .data : {
    *(.data .data.*)
    *(.got .got.*)
  }
  . = ALIGN(256);              /* pad text+data to a 256 boundary so .bss abuts it AND stays aligned */
  _bss_start = .;
  .bss (NOLOAD) : SUBALIGN(2) {
    *(.bss .bss.*)
    *(COMMON)
  }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}

