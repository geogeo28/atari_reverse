# Reconstruction status — TOS 1.02 US

**As of 2026-09-13** — project opened. Nothing is verified yet; this file is the ledger the waves
fill in. Read `../README.md` first for the three evaluation tiers a component is held to.

## Components

| component | Tier 1 (functions verified) | Tier 2 (conformance ledger) | Tier 3 (cycle ratio) | state |
|---|---|---|---|---|
| boot | 0 | — | — | NOT STARTED |
| bios | 0 | — | — | NOT STARTED |
| xbios | 0 | — | — | NOT STARTED |
| gemdos | 0 | — | — | NOT STARTED |
| vdi + linea | 0 | — | — | NOT STARTED |
| aes | 0 | — | — | NOT STARTED |
| desk | 0 | — | — | NOT STARTED |
| data | — | — | — | NOT STARTED |

## Harness

| surface | state |
|---|---|
| Ghidra bootstrap of the ROM at `0xFC0000` | **DONE** 2026-09-13: `run.sh` + `reapply.sh` (≈4 min) → 1,292 functions, 1,219 decompiled, 137,555 of 196,608 B (70.0%) inside function bodies (the rest is the identified data: fonts, resources, the Line-F table); `names.txt` seeds 272 fn / 174 var / 44 cmt with zero apply failures; `a5` pinned to 0 over the BIOS/XBIOS (`unaff_A5` 308 → 107, none left in the pinned range); `COMPONENTS.md` maps every component but the aes/desk code boundary. Open: 73 functions fail to decompile (Alcyon's write-to-`(sp)` first-arg idiom, e.g. `Fread`, `Pexec`, `Setexc`) — listed in `COMPONENTS.md` |
| post-boot RAM snapshot (Tier 1 image) | NOT STARTED |
| oracle ROM mode (`tools/recreate_kit`) | NOT STARTED |
| rebuilt ROM boots in Hatari (`--tos`) | NOT STARTED |
| `TOSTEST.PRG` conformance ledger | NOT STARTED |
| `TOSBENCH.PRG` + boot-time surface | NOT STARTED |

## Wave log

* **Wave 1 (2026-09-13)** — bootstrap: Ghidra import + component map; oracle ROM mode + snapshot;
  ROM build + boot surface. Results are recorded here by the orchestrator at the merge.

## Not reconstructed, and why

(empty — filled per component)
