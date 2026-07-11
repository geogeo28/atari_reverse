# 68000 Disassembly

The ST CPU is the Motorola **68000**: 16/32-bit, big-endian, 8 data (D0–D7) + 8
address (A0–A7) registers; A7 = stack. Instructions are 1+ 16-bit words.

## Why a "first-pass" linear sweep is tricky

A linear sweep decodes forward word-by-word. The danger is **instruction length**: if
you miscount one instruction's length you desync and everything after is garbage. Length
depends on the operand **effective-address (EA) mode** and its extension words:

| EA mode (bits) | Extension words |
|----------------|-----------------|
| Dn / An / (An) / (An)+ / -(An) | 0 |
| d16(An) / d8(An,Xn) | 1 |
| abs.w / d16(PC) / d8(PC,Xn) | 1 |
| abs.l | 2 |
| immediate | 1 (byte/word) or 2 (long) |

`tools/prg_dis.py` computes lengths from these rules, so its sweep stays in sync through
real code. It falls back to `dc.w` for unknown opcodes and annotates traps.
**But**: it cannot tell code from data. In a 48 KB game, data regions (tables, strings,
bitmaps) decode as nonsense — that's expected. Use `prg_dis.py` for orientation and the
entry region; use **Ghidra** (which follows references) for real function recovery.

Run a slice:
```bash
python3 tools/prg_dis.py bin/GAME.PRG --start 0x<fileoff> --len 0x<n>
```
(`prg_dis` addresses are image-relative = file_offset − 28.)

## Idioms you'll see constantly

- `dbf Dn,label` (a.k.a. `dbra`) — decrement-and-loop; the workhorse loop. `Dn` counts
  down to −1.
- `movem.l regs,-(sp)` / `movem.l (sp)+,regs` — save/restore register sets.
- `lea $xxxxxxxx.l,An` — load an **absolute** address (this longword is relocated).
- `pea x(pc)` / `pea $abs.l` then `move.w #fn,-(sp)` then `trap #N` — an OS call.
- `link/unlk A6` — stack frame; `A6`-relative locals.

## Jump tables (control flow you must decode by hand)

Two shapes, both common in ST games:

1. **Offset table**: `move.w (tbl,Dn.w*2),Dm; jmp (tbl,Dm.w)` — each entry is a signed
   16-bit offset added to the table base. Handler = `tbl + offset`. BuggyBoy's course-event
   dispatcher (129 entries) and object-type dispatcher are both this. Decode the words,
   add the base, and you get every handler address (see `methodology.md` for the script).
2. **Pointer table**: array of absolute addresses (each is relocated) indexed and `jsr`ed.

Ghidra's "Decompiler Switch Analysis" recovers many of these automatically after the
relocation table is applied; the rest you decode from the raw words.

## Machine detection

ST-family games often branch on machine type via `$ffff8007` (STE/MSTE bus) or the
`_cookie` jar. BuggyBoy's `START.PRG` printed `ST/STE/Mega STE/TT/Falcon`, MHz, and TOS
version — such strings pinpoint the detection routine.

→ Next: [`ghidra-pipeline.md`](ghidra-pipeline.md) (recover real functions),
[`tos-os-calls.md`](tos-os-calls.md) (what the traps mean).