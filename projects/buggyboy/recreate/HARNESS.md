# Harness / oracle extension plan — input-driven functions

The differential harness (README.md) proves a reconstructed function correct by running the real
68000 code (Musashi oracle) and the C reconstruction on the same image and diffing. That works for
any function whose behaviour is a pure function of the image + registers. A handful of functions
are **not** — their control flow is driven by the IKBD keyboard/joystick, whose state arrives via a
hardware interrupt the oracle doesn't run. This doc scopes the extension that makes them verifiable.

## Affected functions

| Fn | Addr | Needs the extension? | Why |
|----|------|----------------------|-----|
| `read_joystick` | `0x12110` | HW read only | busy-waits `IKBD_STATUS&2`, writes `0x16` to `IKBD_DATA` |
| `read_input` | `0x120b0` | globals only | pure logic over `input_state`/`last_key` |
| `check_abort` | `0x128ea` | globals only | compares `input_state` vs `0x18c42` |
| `update_highscore` | `0x1238e` | globals + timed loop | ranking + table insert + name-entry loop |
| `intermission_poll` | `0x12914` | **no** — misclassified | it's a pure table-driven block blit; no IKBD (**Phase 0**) |

## Root cause

`read_joystick` does `do {} while ((IKBD_STATUS & 2)==0); IKBD_DATA = 0x16;`. The oracle returns
**0** for any read above the 1 MiB image (`m68k_read_memory_8: a<g_size ? … : 0`), so the TX-ready
bit is never set → **infinite loop**. And `input_state` (`0x18c44`) / `last_key` are written by the
IKBD interrupt handler (installed by `install_handlers` at the `ikbdsys` vector), which the oracle
never runs.

## Design decision — model at the **state** level, not the IRQ level

The differential contract requires **both cores to see identical inputs**. The reconstruction is
pure C with no interrupts, so IRQ-driven, time-varying `input_state` has no analogue on the
candidate side and cannot be differentially verified. Therefore:

- **Memory model:** hook `IKBD_STATUS`/`IKBD_DATA` in `shim.c`'s memory callbacks exactly like the
  existing **PSG capture** (`$ff8800/8802`): `IKBD_STATUS` returns TX-ready, `IKBD_DATA` writes are
  swallowed (no image effect).
- **Input as data:** `input_state`/`last_key`/`0x18c42` become **harness-poked constants** —
  ordinary test inputs, identical on both sides. A constant per run is a valid differential test;
  different constants exercise different branches (no-input→timeout, fire, up, down).
- **Explicit limit (documented, not hidden):** a realistic *keystroke sequence* isn't simulated
  end-to-end; each branch is covered by its own fixed-input run, and the letter-edit arithmetic is
  confirmed by reading.

## Phases (each gated on `make test` green)

- **Phase 0 — reclassify `intermission_poll`.** It's a data-driven block blit, not input. Reconstruct
  + fuzz like `draw_dashboard`; no extension involved. **← done (verified, STATUS.md).**
- **Phase 1 — IKBD memory model.** Add `IKBD_STATUS`/`IKBD_DATA` cases to `shim.c` (mirror PSG).
  *Verify:* `read_joystick` runs to `rts` with a clean whole-image diff. **← done: `shim.c` models
  `IKBD_STATUS` ($fffc00) as TDRE-ready so the busy-wait terminates; the command write to
  `IKBD_DATA` lands above the image and is dropped. `read_joystick` verified (test_input.py).**
- **Phase 2 — leaf input fns.** Reconstruct `read_input` + `check_abort`; tests sweep poked
  `input_state`/`last_key`/`0x18c42`. *Verify:* run-to-rts, all-branch fuzz. **← done: `read_input`
  (image-diff fuzz over joystick/keyboard branches) and `check_abort` (return-value fuzz; GEMDOS
  Crawio fn 6 modeled as no-key in shim.c + os.h) verified in test_input.py.**
- **Phase 3 — `update_highscore`.** (a) audit remaining traps — XBIOS `Vsync` (0x25) is already a
  no-op; still to identify the GEMDOS `trap #1` in the two tune-wait loops. (b) add a knob to pin
  `MZFLAG`=0. (c) reconstruct ranking + row-shift/insert (**this populates `highscore_table` → the
  results screen's SCORE/NAME columns render**) + draw calls + loop. *Verify:* checkpoint-first
  (after ranking+insert+first `draw_results_screen`), then full run-to-rts under fixed-input
  scenarios (`input_state ∈ {0, 0x80, 1, 8}`) with raised `max_insns`. **← done, and simpler than
  planned: checkpointing at the two prefix exits (`0x12450` made / `0x123e6` missed) — before the
  interactive loop — verifies the ranking/shift/insert (the SCORE/NAME payoff) with no MZFLAG pin,
  no in-loop trap modeling, and no input timeline. The name-entry loop stays read-only. See
  src/highscore.c + test_highscore.py.**
- **Phase 4 — `install_handlers` (optional).** Needs XBIOS `Kbdvbase` (34) modeled to return an
  in-image KBDVBASE struct. *Verify:* run-to-rts diffing the saved/installed vectors.

## Risks / unknowns

- **Instruction budget:** the no-input timeout path is ~510 frames × `draw_results_screen` → tens of
  millions of instructions. Mitigation: checkpoint verification sidesteps it.
- **`0x18c42` semantics:** confirm it isn't rewritten from `input_state` inside the loop by an
  untraced path; if it is, poke it too (still deterministic).
- **Tune-wait `trap #1` fn:** needs identifying; if stateful (unlikely) it's more than a no-op.

## Sequencing

`0 → 1 → 2 → 3 (checkpoint) → 3 (full) → 4`. Phase 0 is a free win; 1–2 de-risk the memory model
before the big function; Phase 3's checkpoint gets the SCORE/NAME render payoff early. Minimal path
to "SCORE/NAME renders" = Phase 1 + Phase 3-to-checkpoint.
