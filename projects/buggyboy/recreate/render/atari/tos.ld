/* tos.ld — link the demo at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * rodata folds into text so it is reachable; .bss (the 1 MiB image) is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary.
 *
 * GEMDOS places BSS immediately after text+data (at tlen+dlen), so .bss MUST start there with no
 * gap. A BSS symbol with a large alignment (e.g. the 256-aligned screen image) would otherwise
 * push .bss past the end of the emitted binary, and every BSS access on-target would land at the
 * wrong address (the classic "handle 0 / silent corruption" bug). We force text+data — and hence
 * the whole load — to a 256-byte boundary and drop any per-symbol alignment inside .bss (SUBALIGN 1),
 * so .bss abuts text+data exactly while the 256-aligned load base keeps the image page-aligned. */
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

