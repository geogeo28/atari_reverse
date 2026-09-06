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

## Alternative: static depack (no emulator)

If the depacker is a simple LZ loop (literal runs + back-references, controlled by
`bmi`/`beq` — like `START.TOS`'s at `0x32–0x6c`), reimplement it in Python and inflate
the stream offline. Faster and fully scriptable; you must identify the exact format and
stream offset, but the output is self-validating (a correct depack of a GEMDOS program
starts with `60 1a`).

`tools/depack_gamex.py` does exactly this for the **Gamex / "PP" LZSS** cruncher
(control byte: `0`=end, `0x01–0x7f`=literal run, `0x80–0xff`=match with `&0x3f` length,
bit6 = short/long offset). It auto-scans for the stream offset that yields a valid PRG:

```bash
python3 tools/depack_gamex.py projects/<name>/bin/GAME.CTE projects/<name>/bin/GAME.PRG
```

`tools/depack_lsd.py` does the same for the **"LSD!" backwards-LZ** cruncher (Wonder Boy in
Monsterland). Two things make that family different from Gamex-style forward LZ, and both
generalise — expect them from any Pack-Ice-descended ST cruncher:

- **The stream is consumed backwards**, from EOF down to the end of the header, and the output
  is filled backwards too (a match copies from *above* the write pointer). The header's third
  long is only there to walk the source pointer to EOF. Take EOF from that field, never from the
  length of your buffer — the routine never learns that length, so bytes past EOF are slack, and
  honouring that is what lets you depack a stream *sliced out of a larger file* (the payload
  embedded at VAPOUR2's text `$94c`, which inflates to 136,979 bytes) or one read back in whole
  sectors.
- **The bitstream is byte-buffered with a self-carried marker**: `lsl.b #1,dn` shifts a bit out,
  and the buffer is spent when the remainder hits 0, so each byte's *lowest set bit* is its end
  marker; the refill's `roxl.b #1,dn` rotates that marker back in as the new byte's marker. Once
  you see that `lsl.b / bne / move.b -(a0),dn / roxl.b` quartet you have found the bit reader,
  and the tables it indexes right after it are the length/offset codes.

Both containers on that disk share a 12-byte header shape, which is a trap: only the `LSD!` one
is this cruncher, and the magic-less one is the game's own resource format (a *second*, unrelated
cruncher — `tools/depack_rad.py`, specified in
[`binary-formats.md`](binary-formats.md#game-resource-containers-a-worked-example-rad--cru)).
Detect on the magic, not on the shape. The two differ in every detail that matters: the game's
own one buffers bits a **longword** at a time rather than a byte, injects its marker explicitly
(`move #$10,ccr` + `roxr.l #1,dn` instead of `roxl.b`), spends its header's third long on a
**checksum** rather than on locating EOF, and encodes its tokens with fixed inline fields
instead of the tier tables the `LSD!` one indexes.

```bash
python3 tools/depack_lsd.py IN [-o OUT]
```

Ground truth for a depacker written this way is cheap — see
`projects/wonderboy/notes/lsd_differential.py`, which drops the original routine into a flat image
and runs it under the recreate_kit Musashi oracle to diff its output buffer against the Python one,
file by file. It needs that oracle built first (any project's kit.mk target will do:
`make -C projects/joust/recreate oracle`), and it borrows nothing else from the kit — no
`project.toml`, no candidate `.so`.

Worked on Joust: `JOUSTS.CTE` (37 KB, entropy 6.95) → `JOUST.PRG` (114 KB, entropy 4.01,
1227 relocations) — a standard PRG that then goes straight through the normal pipeline
(`PrgLoader`, no memory dump needed). Use Hatari when the packer is unknown/complex or
self-modifying; use a static depacker when you can read the algorithm.

## When the wrapper ENCRYPTS instead of crunching

Not every wrapper is a cruncher. A protection wrapper may leave the program at its original length
and simply **XOR it against a keystream whose key comes off the disk** — Bubble Ghost's `GHOST.PRG`
(ERE Informatique, 1987) does exactly that, and `tools/depack_bubbleghost.py` is the worked tool.
The difference matters before you write a line of Python: there is no literal/match stream to
inflate, so nothing self-validates as you decode it — you get the whole image right, or you get
noise.

**Recognise it:**

- **Same size in, same size out.** The header's `text`/`data` cover the whole file with no room for
  an inflated image, and the entropy is high (7.68) with no cruncher signature anywhere. A cruncher
  that big has to write its output *somewhere*: no `Malloc`, no destination pointer above the image
  and no inflated-length field means nothing is being inflated.
- **The tail looks like a keystream, not like code.** A short, periodic-looking run of words just in
  front of the wrapper's entry, walked by a `move.w (a1)+,d0 / eor.w d0,(a2)+ / dbf` loop, is a key
  table — a cruncher's tables index lengths and offsets and are read many times over, a key table is
  read once, in order.
- **`move.w sr,dn` INSIDE the loop.** That is not housekeeping: it puts the **CPU's own condition
  codes** into the keystream, so the flags left by the previous load are part of the key and a
  reimplementation has to model N, Z and X per iteration. Bubble Ghost's inner step is
  `plain[i+1] = cipher[i+1] ^ plain[i] ^ SR ^ k[i]`, with `k` rotated right through X each word.
- **The check reads the disk and then never branches on it.** A `Floprd` of a protection track
  followed by a CRC whose *result is used as data* — rather than a `beq` to a failure path — means
  the protection is **inside the plaintext**. There is nothing to patch out: wrong disk, wrong key,
  rubbish program. (Bubble Ghost CRCs the fuzzy sectors of track 79, then CRCs the wrapper's own
  last 632 bytes with that as the polynomial, so patching the loader also changes the key.)

**A 16-bit key falls to an exhaustive search.** When the derived key is a word you do not need the
disk at all: decrypt the image 65,536 times and score each result on **plaintext plausibility**.
Useful scores, cheapest first — a `60 1a` or a legal opcode where the entry must be, byte entropy
falling into the ~5-bit range typical of 68000 code+data, a high proportion of decodable
instructions across the first few hundred words, printable ASCII where the strings should be, and a
**DRI relocation stream that parses** where the header says it starts. One key stands out by orders
of magnitude. The depacker then carries it as a constant and *re-validates* its output rather than
re-deriving it, because re-deriving it needs the floppy. A longer key defeats this, and the dynamic
Hatari route above is what is left.

### The 68000 prefetch queue, or: the whole run decrypted against the wrong keystream

The gotcha that cost the first attempt, and it generalises to any self-modifying loop:

**a word the loop has already fetched takes effect one iteration late.** Bubble Ghost's self-decrypt
loop points its destination at the `dbf`'s *own displacement word* — the first `eor` rewrites the
branch target — but the 68000 fetched that word before the store, so **pass one branches to the
stale target**: a fixup tail that ones-complements the key table and re-enters the loop. A static
model that reads the patched displacement takes the new branch on pass one, never runs the fixup,
and decrypts every following word against a keystream that is wrong from the first byte.

The symptom is the worst kind — garbage output with nothing to point at, because the error is in
iteration 1 of a loop that runs hundreds of times. So whenever a decrypt loop writes anywhere inside
its own body (the displacement, an immediate, the next instruction), **model the stale fetch**: run
that iteration with the word as it was *before* the store. Two words of prefetch is the rule on a
plain 68000; if the loop is tighter than the one above, take the fetch order from
[`m68k-disassembly.md`](m68k-disassembly.md).

→ Detection helper: `prg_dis.py` (entropy line). Loading clean PRGs: [`binary-formats.md`](binary-formats.md).