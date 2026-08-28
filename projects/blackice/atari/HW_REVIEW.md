# Hardware-seam review (static; not a play-test — see QA.md for the headless play-test)

# QA.md — platform-layer review ledger (`atari/`)

**Scope of this document, stated first because it is the thing most likely to be misread:**
this was a **static hardware-seam review**, read-only. **No scenario was executed.** No build was
run, no Hatari was launched, no screenshot was captured. Every row below marked BLOCKED is blocked
because it was never in this pass's scope, not because it failed.

- Reviewer: platform-layer finder (recall-biased), 68000 / TOS / STE seam.
- Sources read at: `main.c` **58,347 B (01:44)**, `os.S` 01:39, `render.S` 01:31, `plat.h`, `tos.h`,
  `assets.c/.h`, `hud.c/.h`, `verify.py`, `Makefile`, `tos.ld`, `README.md`, `../design/BRIEF.md`,
  plus `../audio/ym_psg.{S,h}`, `../audio/ym_music.c`, `../src/raycast.c`, `../src/level.c`.
- Findings re-checked against: `main.c` **74,103 B (02:34)**, `os.S` 02:09, `render.S` 02:34,
  `disk/BLACKICE.PRG` (02:43 — asm cast, joystick port 1 only, ST-Low forced).
- **Every finding below was raised against the 01:44 source.** The status column is a fresh
  `grep`/`sed` confirmation against the 02:34 source, done for this document. Nothing was rebuilt.

---

## Runtime scenarios

| # | Scenario | Status | Why |
|---|---|---|---|
| 1 | Boot to first frame on the 02:43 build | **BLOCKED** | Never in scope; needs a Hatari run this pass did not perform. |
| 2 | Movement / joystick + keyboard | **BLOCKED** | Same. Also structurally blocked headless — see D1. |
| 3 | Clean exit + desktop usable | **BLOCKED** | Same; and the IKBD half is unmeasurable by the current gate (D1). |
| 4 | Rendered pixels vs host oracle | **NOT RUN** | Owned by `make verify`; README records PASS (0/51,200) on the pre-02:34 build. |
| 5 | Frame-time table | **NOT RUN** | Owned by `make bench`; README's table predates the 02:34 asm cast. |

Exact commands, none of which were run here:

```sh
cd projects/blackice/atari
make bench      # headless Hatari -> ledger + BENCH.TXT + out/frame.png
make verify     # pixels, silhouette, teardown, machine health (depends on bench)
make libgcc-gate
```

**Screenshots: none captured by this pass.** `out/frame.png` / `out/frame_screen.png` on disk are
from an earlier run and must not be read as evidence for the 02:43 build — README's own fault #9
records a mutation sweep that came back green precisely because it compared a stale `out/frame.png`.

---

## Ranked defects

Ranked as raised. Status re-confirmed against the 02:34 source for this document.

| # | Finding | Where (01:44) | Status vs 02:34/02:43 |
|---|---|---|---|
| D1 | **Teardown surface covers neither BRIEF gotcha.** `RESTORED_REGIONS` is palette / video base / sync / STE / shiftmode + `_v_bas_ad`, `nvbls`, `_vblqueue`. The IKBD mode (`$12`/`$14` -> `$1a`/`$08`) and the PSG state are unmeasured; `grep -c 'ikbd\|IKBD\|8800' verify.py` = **0**. The joyvec hole is declared out loud at line 486; these two are not mentioned. | `verify.py:146-152` | **OPEN** — unchanged |
| D2 | Resolution never *set*: `Getrez` saved/restored only, `Setscreen(..., SETSCREEN_KEEP)`. 4-plane data into a mono/medium screen. | `main.c:1478, 870` | **FIXED** — `Setscreen(..., REZ_ST_LOW)` (1108) + `REZ_ST_HIGH` refusal (1130) |
| D3 | Port-0 joystick ORed into input; `$12` stops mouse *packets*, not the port-0 quadrature lines, so a mouse nudge is phantom input. | `os.S:347`, `main.c:795` | **FIXED** — `bi_joy_port0` gone; port 1 only |
| D4 | No floppy deselect after loading (BRIEF gotcha unimplemented; PSG port A never written anywhere). | `assets.c:520` | **FIXED** — `bi_floppy_deselect` (`os.S:484+`), called `main.c:1803` |
| D5 | Music armed but never ticked when `_vblqueue` is full: `frame_clock` and `flip` both had fallbacks, `ym_music_tick` had none -> silent run, no diagnostic. | `main.c:823`, `bi_vbl_tick` | **FIXED** — level-4 vector chain fallback (1066-1068); `g_vbl_installed` now always 1 |
| D6 | `frame_band` clamps the sprite-derived bottom to `RENDER_H` but not the column-derived one; c2p then converts rows past the window into the HUD strip. | `main.c:381` | **FIXED** — explicit clamp at 604-605 |
| D7 | Game build gated on `ledger_placement_error()`, a bench-only address -> "REFUSED" boot on a smaller TPA. | `main.c:1455` | **FIXED** — `#ifdef` split; game build returns 0 |
| D8 | `bi_fill` terminator `cmpa.l/bne` is exact-equality on a pointer stepped 40 at a time: a byte count that is not a multiple of `FILL_CHUNK_BYTES` runs away down through `.bss`. | `render.S:510` | **FIXED** — terminator is now `bhi` |

**7 of 8 closed by the 02:34 pass. D1 is the only one still open**, and it is the gate itself, not
the program: it cannot see the class of regression that D3 and D4 belong to.

---

## Recommended next step

Close D1 by giving the teardown check the two surfaces it lacks — an IKBD round-trip probe and a
PSG register dump — or, failing that, say so in the output the way the `joyvec` note already does
(`verify.py:486`). An undeclared hole in a gate reads as coverage.

Then run scenarios 1-3 on the 02:43 build; they remain unexecuted.
