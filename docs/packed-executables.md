# Packed / Crunched Executables

Most cracked or packaged Atari ST releases **crunch the main executable** (Pack-Ice,
Automation, Atomik, Gamex, custom LZ crunchers…). The stored bytes are compressed; a
small depacker stub at the entry (or a separate loader) inflates the real program into
RAM at run time and jumps to it. Static tools can't read compressed code — you must
**depack first**, then analyze. This is the single most common reason the normal pipeline
([`ghidra-pipeline.md`](ghidra-pipeline.md)) produces garbage.

## Detect it

- **First-pass disassembly is nonsense** at the entry (`prg_dis.py` shows random
  `or`/`btst`/`cmpi`, no `Mshrink` prologue, jumps to absurd absolute addresses).
- **High entropy.** `prg_dis.py` prints the body entropy; **> ~6.7 bits/byte** ⇒ likely
  packed/compressed, **< ~6.3** ⇒ probably plain code+data. (Joust: `JOUSTS.CTE` = 6.95
  packed vs `GXUT20.PRG` = 6.25 clean.)
- **Cruncher signature** — `strings` sometimes shows `ICE!`, `PACK`, `TPWM`, packer/group
  names. Absent ⇒ a custom cruncher (common); use the dynamic method below regardless.
- **A tiny loader `.PRG`/`.TOS`** that self-relocates, runs an LZ loop, then a DRI
  relocation loop and `jmp`s — that's a depacker (BuggyBoy's `START.PRG`, Joust's
  `START.TOS`). The game it produces is what you actually want.

## Why the workflow differs

A `.PRG` file is *relocatable image + header + reloc table* → `PrgLoader` parses the
header and applies relocations. A **memory dump** is the *already-inflated, already-
relocated* live image at its real base: no header, no reloc table, and absolute
references already resolve. So for a dump you **do not use PrgLoader** — you import it
raw at its capture base and seed the entry (`LoadDump.java`). The trade-off: a dump loses
the section boundaries and any symbol table, but it's the only view of the real code.

## Dynamic dump with Hatari (general — works for any packer)

Prereqs: a TOS ROM (Homebrew bundles EmuTOS at
`…/Cellar/hatari/*/Hatari.app/Contents/Resources/tos.img`) and the game files in a folder.

1. **Boot the game** (mount the folder as C:, autostart the loader):
   ```bash
   bash tools/hatari_run.sh projects/<name>/bin 'C:\START.TOS'
   ```
   (`--memsize 1` for a 1 MB game, `--monitor rgb`, `--tos-res low`.)
2. **Let the depacker run** to the title/attract screen — the real program is now inflated
   and executing in RAM.
3. **Enter the debugger** (`AltGr+Pause`; set the key in the Hatari GUI if needed).
4. **Dump memory** with `savebin`:
   - Easy/foolproof: dump all RAM and carve later —
     `savebin dump.bin 0 0x100000` (1 MB).
   - Tight: once you know the program's base+length —
     `savebin dump.bin $<base> $<len>`.

### Finding the base / entry / size

- **Trace the load.** Boot with `--trace gemdos,cpu_disasm` (or `--parse` a script) and
  watch for the game's own `Mshrink`/`Malloc`/`Pexec` — those reveal its TPA base. Hatari
  breakpoints: `b pc=$xxxxx`, `b GemdosOpcode=0x4a`, `:once`, then `cont`.
- **Break at the loader's jump.** Reverse the depacker (`prg_dis.py` on the loader) to its
  final `jmp (An)` into the inflated program; break there and read the base from the
  register / the fabricated basepage (loaders stash text/data/bss at `base-0xE4`, DRI style).
- **Or just carve.** Dump all RAM, then in Ghidra scan for the `Mshrink` prologue
  (`2f3c…` / `move.w #$4a,-(sp)`) or a known string to locate the program, and note its base.

## Load the dump into Ghidra

```bash
bash tools/load_dump.sh projects/<name>/ghidra_proj <Name> dump.bin 0x<base> 0x<entry>
```
Imports the dump raw at `<base>`, seeds `<entry>`, auto-analyzes, annotates traps, exports
`decomp.c`. From here it's the **same naming loop** as any other project (names.txt +
`reapply.sh`). Base and capture base **must match** or absolute references won't resolve.

## Caveats

- Dump enough to cover text **and** data (and ideally the initialised BSS the game set up);
  a text-only dump loses data tables the code references.
- No symbols and no section split — expect a bit more manual structure work than a plain PRG.
- If the game re-packs/overlays parts at run time, dump at the moment the code you care
  about is resident (e.g. break inside the level you're analyzing).

## Alternative: static depack

If the depacker is simple (an LZ loop like `START.TOS`'s at `0x32–0x6c`: literal runs +
back-references controlled by `bmi`/`beq`), you can reimplement it in Python and inflate
the stream offline — no emulator. Faster to re-run, but you must nail the exact format and
locate the packed stream; the Hatari method is more robust and packer-agnostic.

→ Detection helper: `prg_dis.py` (entropy line). Loading clean PRGs: [`binary-formats.md`](binary-formats.md).