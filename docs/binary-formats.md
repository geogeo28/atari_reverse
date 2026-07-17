# Binary Formats (GEMDOS executables)

Everything you need to parse an Atari ST program before disassembly. Reference
parser: `tools/prg_dis.py` (stdlib, no deps).

## The GEMDOS `.PRG` header (28 bytes, big-endian)

| Off | Size | Field | Notes |
|----:|-----:|-------|-------|
| 0x00 | 2 | magic | **`0x601A`** (a `bra.s +26` — legacy) |
| 0x02 | 4 | text length | code segment |
| 0x06 | 4 | data length | initialized data (often 0; merged into text by Devpac) |
| 0x0A | 4 | bss length | zero-init (not stored in file) |
| 0x0E | 4 | symbol table length | 0 or a DRI symbol table |
| 0x12 | 4 | reserved | |
| 0x16 | 4 | flags | TPA/fastload bits |
| 0x1A | 2 | absflag | if non-zero, **no relocation** |

File layout: `header(28) | TEXT | DATA | SYMBOLS | RELOC-TABLE`.
Extensions `.PRG` (GEM), `.TOS` (console), `.TTP` (takes params) share this format.

TEXT and DATA load **contiguously** at the load address; BSS is a zero-filled region
right after. Everything is position-independent — it can load anywhere, fixed up by the
relocation table.

## DRI symbol table (14 bytes/entry)

`[8 bytes name (space/nul padded)] [2 bytes type] [4 bytes value]`

Type word is a bitfield; the section bits decide the address base:

| Bit | Meaning |
|----:|---------|
| 0x8000 | defined |
| 0x2000 | global |
| 0x0400 | **DATA** section → addr = base + tlen + value |
| 0x0200 | **TEXT** section → addr = base + value |
| 0x0100 | **BSS** section → addr = base + tlen + dlen + value |
| 0x0048 | (both set) extended/long name — next entries hold extra name chars |

BuggyBoy kept 11 TEXT symbols (a sound driver's exports: `INITTUNE`, `EGVOL`…).
Beware: assemblers put **inline variables in the TEXT section too**, so a TEXT symbol
is not necessarily code — don't blindly make them functions.

## Relocation table (DRI format)

At `28 + tlen + dlen + slen`. Encodes offsets (into the TEXT+DATA image) of 32-bit
longwords that must have the load base added.

- First entry: a **32-bit** offset (the first fixup). `0` ⇒ no relocations.
- Then a stream of **bytes**: `0` = end; `1` = advance cursor by 254 (span > 255);
  any other `b` = advance by `b`, and fix up the longword there.

To relocate: for each fixup offset, `*(u32*)(image+off) += load_base`. Do this and
absolute references become correct — the single biggest lever for good disassembly.

## Quick recon

```bash
python3 tools/prg_dis.py projects/<name>/bin/GAME.PRG | head -60
```
Prints header sizes, reloc count, embedded strings, and a first-pass disassembly.
Strings often reveal filenames the program loads, menu text, and author credits
(BuggyBoy: `"coded by Martin W.Ward"`, `"COURSES.DAT"`, `"GRAPHICS.GRA"`).

## Building a `.PRG` (reverse direction: recompiling the reconstruction)

Once functions are reconstructed in C, you can cross-compile them back into a runnable
GEMDOS `.PRG` (`m68k-elf-gcc`, link at base 0 with `--emit-relocs`, `objcopy -O binary`,
then wrap with a header + reloc table). BuggyBoy does this in
`projects/buggyboy/recreate/render/atari/` (`mkprg.py`, `tos.ld`). Two gotchas cost real
debugging time — both manifest as the program *seeming* to run but silently corrupting:

**`.bss` must abut TEXT+DATA (no alignment gap).** GEMDOS places BSS immediately at
`load_base + tlen + dlen` and zeroes `blen` bytes. If a BSS symbol has a large alignment
(e.g. a 256-byte-aligned screen buffer), the linker pushes `.bss` to a boundary *past* the
end of `.data`; `objcopy -O binary` does **not** emit that trailing gap, so on-target every
BSS address is off by the gap and stores land in the wrong place (classic silent
corruption). Fix: force text+data to the same boundary and drop per-symbol alignment inside
`.bss` (`. = ALIGN(256); .bss (NOLOAD) : SUBALIGN(1)`), and pad the emitted binary up to
`_bss_start` so `tlen` reaches where GEMDOS will put BSS.

**A returned file handle of `0` means the open silently failed — never a valid file.**
GEMDOS reserves the low handles: **0 = stdin (keyboard)**, 1 = stdout, 2 = aux, 3 = prn. A
successful `Fopen`/`Fcreate` returns a real handle (≥ 6; Hatari's GEMDOS-HD uses **64+**); a
*failed* open returns a **negative** error. So handle 0 is the tell-tale of a broken build,
not a missing file — and it's insidious: `Fread(0,…)` then reads the **keyboard** (blocks
forever under headless Hatari), and `Fwrite(0,…)` writes to **stdout** (silently discarded,
0-byte output files). If your loader "hangs in the decompressor" or writes empty dumps,
check the handle first (`hatari --trace gemdos`). In the BuggyBoy build the trigger was the
order of the trap wrappers in the entry `.s`: the file-I/O wrappers (`Fopen`…`Fwrite`) must
come **first**, right after `_start`, matching the known-good demo layout — placing the
control wrappers (`Super`/`Malloc`/`Crawio`) before them made Hatari hand back handle 0.

Verify a build headlessly: run it under Hatari with a GEMDOS drive, have the shim dump a
framebuffer / result file to `C:`, read it back and diff against the host reconstruction
(`render/atari/run_hatari.py`, `game_smoke.py`). See [`tos-os-calls.md`](tos-os-calls.md)
for the trap selectors and startup sequence to mirror.

→ Next: [`m68k-disassembly.md`](m68k-disassembly.md) or [`ghidra-pipeline.md`](ghidra-pipeline.md).