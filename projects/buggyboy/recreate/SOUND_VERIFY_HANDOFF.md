# Handoff — verifying BuggyBoy's off-image sound/OS triggers (improvements #2 and #3)

> **STATUS: DONE (both #2 and #3).** Every sink call site is now exercised by a directed differential
> test; `coverage_gap_allow.txt` is empty and `make coverage-gap` reports 0 gaps. The directed tests
> for the checkpoint path also caught **four latent reconstruction bugs** in `game_update` that the
> image diff never reached (see below). Tests: `test/test_gu_jingles.py`, `test_game_update.py::
> test_entry_marker_fx`, `test_highscore.py::test_{made,miss}_tail_jingle`, `test_stop_music.py::
> test_main_racestart_dosound` + `test_dosound_ledger_sensitivity`.
>
> **Bugs found and fixed** (`src/game_update.c`, all on the never-diff-tested course-advance tail):
> 1. `event_type` checkpoint/collision test read the WORD's high byte (`image[0x18eca]`); the original
>    does `move.w (event_type),d1; cmpi.b`, i.e. the LOW byte (`image[0x18ecb]`). → checkpoint/collision
>    events never fired.
> 2. the `draw_checkpoint_anim` gate read `ground_scan_tbl+0` instead of the `+3` marker byte.
> 3. the checkpoint char read the `"SCORE/"` string at `0x18000` instead of its real base `0x18540`.
> 4. the entry marker fx passed `event_type` to `handle_marker`; the original passes the `marker_pending`
>    byte value (`move.b (marker_pending),d0; bsr handle_marker`).
>
> The rest of this file is the original spec, kept for provenance.

---

This is a self-contained spec for two follow-ups to the sound work. Read it with `STATUS.md`,
`docs/on-target-execution.md` §5 ("off-image OS services"), and the memory note
`buggyboy-sound-architecture` for background.

## Why this exists (the blind spot)

The differential harness compares the **memory image** (Musashi oracle vs the compiled candidate `.so`).
Two kinds of sound/OS trigger escape it:

1. **Off-image effects** — XBIOS `Dosound` writes the YM2149, not RAM; `play_event_tune`/`handle_marker`
   only touch the image when their `game_over`/`mzflag` guard is open. Invisible to the image diff
   even when the code runs. → needs **#2 (side-effect ledger)**.
2. **Fuzz-unreached branches** — the call never executes under the fuzz, so nothing is compared.
   → needs **#3 (directed tests)**.

`make coverage-gap` (`tools/coverage_gap.py`) now *finds* these: it lists every call site to a sound/OS
sink that no test executed. The current 7 gaps are read-verified only, listed in
`tools/coverage_gap_allow.txt`. #2 and #3 turn read-verification into diff-verification and let those
allowlist entries be removed.

## Anchors (addresses, files)

Sinks (Ghidra addr): `play_event_tune 0x11c7a`, `handle_marker 0x11cb2`, `stop_music 0x12ec4`,
`stop_music_chk 0x12ebc`, `INITTUNE 0x1b59c`, `INITFX 0x1b560`, and the XBIOS `Dosound` trap (fn `0x20`).
Dosound command lists (`include/addrs.h`): `A_dosound_beep 0x18bba`, `A_dosound_go 0x18bca`,
`A_dosound_idle 0x18ba2`, `A_dosound_collide 0x18b78`, `A_dosound_crash 0x18b92`.
Seam: `g_dosound(image, list_off)` — logs to the ledger in the `.so` (kit-wide since the Joust
project: `tools/recreate_kit/src/dosound_log.c`; it lived in `src/os.c` when this was written), real
XBIOS `Dosound(image+off)` in `render/atari/game_main.c`. `g_stop_music(image, list_off)` / `g_stop_music_chk(...)` thread the list.
Oracle coverage: `oracle/shim.c` `osh_cov_*`; `oracle/emu.py` `cov_enable/reset/visited/data`;
`test/conftest.py` dumps per-worker when `COVGAP_DIR` is set.

The 7 allowlisted gaps (from `coverage_gap_allow.txt`):

| call site | trigger | id | image effect? |
|-----------|---------|----|----------------|
| `0x119ca` | game_update checkpoint (`event_type==0x1a`) | `play_event_tune(5)` | yes (INITTUNE) → **#3** |
| `0x11a8c` | game_update leg-end (`score_str[1]=='5'`) | `play_event_tune(1)` | yes → **#3** |
| `0x11a9c` | game_update collision-marker (`ground_scan[1]==0x1d`) | `play_event_tune(6)` | yes → **#3** |
| `0x1111a` | game_update entry marker fx | `handle_marker(*0x18d14)` | INITFX arms `fxflag` → **#3** |
| `0x12402` | update_highscore miss-tail | `play_event_tune(2)` | yes → **#3** |
| `0x12450` | update_highscore made-tail | `play_event_tune(4/3)` | yes → **#3** |
| `0x10222` | main race-start countdown | `stop_music(A_dosound_beep)` → `Dosound(A0)` | **no** (off-image) → **#2 only** |

Rule of thumb: an `INITTUNE`/`INITFX` id becomes image-visible once the guard is open, so #3 verifies it.
A `Dosound` A0 list writes no RAM ever, so only #2 can verify it.

---

## Improvement #3 — directed differential tests for the reachable gaps

**Goal:** stage each fuzz-unreached branch so its `INITTUNE`/`INITFX` fires **unguarded** (INITTUNE lands
voice records + `cur_tune_id`; INITFX arms `fxflag`/effect params — both image-visible), then the existing
image diff verifies the id. Remove each covered site from `coverage_gap_allow.txt`.

**Pattern to copy:** `test/test_game_update.py::test_event_handler_isolation` already enters individual
handlers at their PC and diffs to rts; `test/test_stop_music.py` shows guard staging. Reuse
`harness.differential(entry, regs, glue, poison=True)`.

**Per gap — what to stage (all with `game_over_flag(0x18c34)=0`, `mzflag(0x1b07a)=0`, `cur_tune_id!=6`
so `play_event_tune` runs INITTUNE):**
- `0x119ca` (tune 5): enter game_update's course-advance section with `A_event_type(0x18eca)=0x1a`.
- `0x11a8c` (tune 1): same, plus `score_str+1 (0x18231)=='5'` (0x35).
- `0x11a9c` (tune 6): `A_ground_scan_tbl+1 (0x18d49)=0x1d` (collision marker), bonus path.
- `0x1111a` (marker fx): set the marker byte at `0x18d14` nonzero at game_update entry; assert INITFX
  armed `fxflag` + the effect record for that fx id.
- `0x12402`/`0x12450`: enter the update_highscore tails with `results_mode` = miss / made respectively
  (see `src/highscore.c` `g_hiscore_gameover` / `g_hiscore_name_entry`).

**Verify:** for each, the whole-image diff passes with the correct id and *fails* if the id is perturbed
(a change-and-diff sensitivity check like the one that confirmed `GU_SCORE_TUNE`). Then delete its line
from `coverage_gap_allow.txt` and confirm `make coverage-gap` still exits 0 (site now covered).

**Out of scope for #3:** `0x10222` (Dosound, off-image) — leave allowlisted until #2.

---

## Improvement #2 — side-effect ledger (trap/call-stream diff)

**Goal:** make off-image OS-call *arguments* diff-verifiable — a wrong or missing `Dosound(A0)` (or
`Setpalette(ptr)`, `Ikbdws`, …) fails a test even though it touches no RAM. This closes the hole for
*executed* calls; combined with #3 (reach the call) and coverage-gap (find unreached calls), sound
triggers become fully verified.

**Design — an ordered event ledger on each side, diffed like the image:**
- **Oracle** (`oracle/shim.c`, `handle_trap`): record `(fn, key-arg)` per serviced trap into a
  ledger array (mirror the existing PSG tap: `g_psg_*` / `osh_psg_count`). Reset per run alongside
  `g_psgn`. Start with `Dosound (fn 0x20) → A0`; the fn/arg conventions are already read in `handle_trap`.
  Expose `osh_trap_count()` / `osh_trap_log()`.
- **Candidate** (`src/os.c`): the seams are no-ops in the `.so`. Make the relevant ones append
  `(id, arg)` to a parallel ledger with reset + accessors — begin with `g_dosound(image, list_off)`
  logging `(DOSOUND, list_off)`. (The PRG's real seams in `game_main.c` are unaffected; this logging is
  the `.so`/harness side only.)
- **Harness** (`test/harness.py` `differential`): after running oracle + candidate, compare the two
  ledgers as an ordered stream (map trap fn → seam id: `Dosound 0x20 ↔ DOSOUND`, oracle `A0` == candidate
  `list_off`, both Ghidra image offsets), and assert equal alongside the image diff.

**Scope / order:** implement `Dosound` first (the one that bit us — the countdown/idle/collision/crash
lists). Then optionally generalise to `Setpalette`/`Setcolor`/`Ikbdws` if useful.

**Verify:** a deliberately-wrong A0 (e.g. `g_stop_music(image, A_dosound_go)` where the original passes
`A_dosound_beep`) makes a test fail; `make test` stays green otherwise. Then `0x10222` (and any other
Dosound site) can leave the allowlist once a test exercises it with the ledger asserted.

## Success criteria
- **#3:** each targeted allowlist line removed; `make coverage-gap` exits 0 with those sites covered;
  `make test` green; a perturbed id fails the new test.
- **#2:** `make test` green; a wrong/missing `Dosound` A0 fails a test; the ledger diff is part of
  `harness.differential`.

Keep the differential suite byte-identical throughout (these are additive observables, not image
changes). Update `STATUS.md`, `coverage_gap_allow.txt`, and the memory note as each gap is closed.
