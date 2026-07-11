# Joust (Atari ST, Gamex release) — validation target

Used to **validate the framework on a second, different game**. Verdict: the framework
generalizes to clean GEMDOS binaries of any extension, and the boundary is **packing** —
exactly the predicted gap. This project drove the new
[`docs/packed-executables.md`](../../docs/packed-executables.md) capability.

## Files (`bin/`)
- `GXUT20.PRG` — Gamex save-state utility. **Clean, unpacked** (textbook `Mshrink`
  prologue, 148 relocations, entropy 6.24). The normal pipeline works on it as-is.
- `START.TOS` — Gamex loader: self-relocating **LZ depacker + DRI relocator** (same shape
  as BuggyBoy's `START.PRG`); references a chained `JOUL1.TOS` (not shipped in `bin/`).
- `JOUSTS.CTE` — **the game, PACKED** (entropy 6.95, entry disassembles to garbage,
  0 relocations). Not directly analyzable.
- `JOUST.PCH` — patch/data · `HIGH.SCO` — high score · `README.TXT` — Gamex notes (by "PP").

## What generalized ✓
- Extension-agnostic: `.PRG`/`.TOS`/`.CTE` are all GEMDOS `601a`; `prg_dis`/`PrgLoader`/
  trap-annotate key off the magic, not the name.
- `GXUT20.PRG` is a ready target for the full naming loop.
- `START.TOS` matched the documented "custom loader/depacker" pattern; `prg_dis` read it cleanly.

## Where it hit the wall ✗ (→ new capability)
`JOUSTS.CTE` is crunched, so static tools can't touch the real game. Fix: depack first,
per `docs/packed-executables.md`.

## Next step (open)
Depack via Hatari and analyze the dump:
```bash
bash ../../tools/hatari_run.sh bin 'C:\START.TOS'      # run to title, AltGr+Pause, savebin dump.bin 0 0x100000
bash ../../tools/load_dump.sh ghidra_proj Joust dump.bin 0x<base> 0x<entry>
# then the usual names.txt + reapply loop
```
Prereq: find the depacked base/entry (trace GEMDOS load, or carve the dump). See the doc.
`GXUT20.PRG` can be bootstrapped directly with `new_project`-style `headless.sh` any time.