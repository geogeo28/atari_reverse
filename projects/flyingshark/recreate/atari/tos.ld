/* tos.ld — link the demo at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * rodata folds into text so it is reachable; .bss (the 1 MiB image) is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary.
 *
 * GEMDOS places BSS immediately after text+data (at tlen+dlen), so .bss MUST start there with no
 * gap. A BSS symbol with a large alignment (e.g. the 256-aligned screen image) would otherwise
 * push .bss past the end of the emitted binary, and every BSS access on-target would land at the
 * wrong address (the classic "handle 0 / silent corruption" bug). We force text+data — and hence
 * the whole load — to a 256-byte boundary and drop any per-symbol alignment inside .bss (SUBALIGN 1),
 * so .bss abuts text+data exactly while the 256-aligned load base keeps the image page-aligned.
 *
 * SHARED WITH projects/joust/recreate/atari/tos.ld and projects/wonderboy/recreate/atari/tos.ld —
 * the THREE are identical BELOW THIS PARAGRAPH (each copy names the others, so the markers differ
 * and nothing else does), and a change to any belongs in all three. Registered as a kit candidate
 * alongside mkprg.py, and there are three copies now rather than two, which is what
 * ../STATUS.md's "Follow-ups the kit should absorb" row says; until that move happens, this
 * marker is the only thing linking them.
 */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS
{
  . = 0;
  .text : {
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
  .bss (NOLOAD) : SUBALIGN(1) {
    *(.bss .bss.*)
    *(COMMON)
  }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}

