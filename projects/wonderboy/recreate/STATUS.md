# Reconstruction status — Wonder Boy in Monsterland

Human-readable C reconstruction of `SWB.PRG` (the original, uncracked 1989 Activision release,
extracted from the Pasti `.stx` of disk 1), each function to be **verified byte-for-byte against the
original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi oracle
running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 32/? — the .RAD depacker (216 bytes) and the first gameplay batch (434 bytes).**
`make test`: 312 cases green, of which 77 are the foundation battery below, 48 are the depacker's
differential and 187 are the gameplay batch's. A row appears in the table at the end when a function
is reconstructed and green; everything else in `../decomp.c` and `../names.txt` is still only
*named*, not ported.

## What the harness has established

These are the results of `test/test_bootstrap.py`, all of them read off the original binary or off
the original code running under the oracle:

- **The loader is correct for this .PRG.** text = `0x214d8`, no data, no bss, three relocation
  entries; the image at `load_base` is the file's text verbatim apart from those three longwords,
  each `raw + load_base`.
- **The program is not position-independent — it relocates ITSELF to the absolute address `0x400`.**
  The entry point is a trampoline (`move.w d0,d0` / `jmp $213e0.l`, the target relocated) into a
  relocator at the end of the text, which copies `0x84f6` longwords (`0x213d8` bytes) from
  `load_base + 8` to `0x400` and jumps there. Run under the oracle to its `jmp`, with the
  destination compared against the file's own bytes, the neighbours on both sides proved untouched,
  and the write set proved to be exactly the destination range. Constants in
  [`include/wonderboy.h`](include/wonderboy.h).
- **`load_base = 0x3f8` makes the loaded image the runtime image.** `load_base + 8 == 0x400`, so the
  relocator's source and destination coincide and its copy is an identity copy — the program's own
  absolute operands address the loaded image directly, no staging step is needed, and the base
  agrees with `../names.txt` (checked against two of its anchors, `startup_relocate_and_run` at
  `0x217d8` and `cold_start` at `0x400`).
- **The game issues exactly ONE TOS trap in its whole image**: the GEMDOS `Super` at file offset
  `0x213ea`, immediately preceded by its in-line `move.w #$20,-(a7)` selector, with its argument
  (a relocated operand) pinned to the first byte past the program. Every other even-aligned
  `trap #N` encoding in the file sits inside an ASCII message string — pinned by offset, so a fifth
  one appearing anywhere fails the case. **The same five hits survive relocation**: the scan reads
  the file, but what the 68000 executes is the relocated image, and each of the three fixups
  rewrites four bytes that could in principle create or destroy a `trap #N` encoding, so the scan is
  re-run over the loaded image rather than argued about. So the game drives the hardware directly,
  including the floppy: it loads its own overlays by name with no GEMDOS file call anywhere.
- **The Copylock is stubbed, and every stubbed run proves it.** `test/copylock.py` offers two
  mechanisms with different domains — poke `copylock_arm_flag := 0` (undone by the game's own
  `move.w #$ffff` at `$e51e`/`$e6dc`, so it is valid only below an arming site) and poke `rts` over
  `copylock_entry` (valid anywhere, because an arming site does not write code) — and applies both
  by default. `copylock.run()` then refuses any result whose memory shows the protection ran, using
  a **difference** witness rather than a write-set one: at this load base the relocator's identity
  copy writes all 2,220 of the protection's bytes without changing any, so a write-set witness
  reports a false "it executed" for a `move.l (a0)+,(a1)+` loop. The guarantee is exactly "any run
  that COMPLETES the `movem.l d0-a7,(a6)` at `$ed4c`" — the five instructions before it are a blind
  window, and a caller's own pokes could land on both sides of the comparison, so `run()` refuses a
  `stop_pc` inside the blob and `stubbed_image()` refuses a poke overlapping the watched span. 40
  cases in `test/test_copylock.py`, including the negative controls for what an unstubbed run does:
  entered at the guard it reaches the decryptor at `$ee02` and **never returns** (the kit's Musashi
  is built with `M68K_EMULATE_TRACE` off, so the blob cannot self-decrypt), while entered at an
  arming site it **does** come back — to `$e7c8` in 184,997 instructions with 2,053 bytes of the
  protection scrambled, which is the false green in its exact shape. What the stub is worth, and the
  seven things it knowingly does not verify, are in [`PORTABILITY.md`](PORTABILITY.md) §6.1.

## The kit change this project required

`load_base` **must** be below the kit's `OS_POKE_BLOCK_END` floor (`0x620`): the game runs at the
fixed absolute address `0x400`, and everything below that is the 68000 vector page. So the kit
gained a second waiver, built exactly like the existing `tos_malloc_unused` one and off by default:

* `project.toml` may declare `tos_poked_input_unused = true` — the claim that the game reads none of
  the harness-poked state (no `Bconstat`/`Bconin`/`Crawio`, no `Random`, no `Giaccess`, no
  `Kbdvbase`), which is what lets its program cover that block;
* the claim then buys the layout and **never a green run**, because two guards re-test it instead of
  trusting it, both keyed on the *overlap* rather than on the flag:
  * `emu.run()` refuses any run in which a trap reached the block (`_vet_no_poked_input_read`, keyed
    on the oracle's new `osh_poked_input_calls` tally) — the direct sibling of the Malloc waiver's
    per-run re-check, and the half that watches the **game** rather than the test. One case per
    counted trap pins all six increments; the tally is oracle-side only, and `TRAP_MODEL.md` states
    what that does and does not cover;
  * `harness.make_image()` refuses any poke whose byte range lands in the block, at the layer pokes
    are applied — so a hand-written `{OS_RANDOM_VALUE: …}` dict, the only way to stage an XBIOS
    `Random`, is seen exactly like a `console_key()` one;
  * `console_key()` / `psg_regs()` still refuse as well, but only as a friendlier early error.

Pinned by [`test/test_poked_input_guard.py`](test/test_poked_input_guard.py) — including that the
unwaived check really does fire here, and a negative control that disarms the run guard and measures
the false green it prevents (a `Bconin` reading the program's own bytes, being told a key is
pending, and zeroing four bytes of code). Wonder Boy is the only project the overlap exists for, so
the wiring can only be pinned here; the geometry underneath is pinned kit-side in
`tools/recreate_kit/test/test_os_map.py`. BuggyBoy (292 cases) and Joust (4368 cases) were re-run
green after the change.

## Blockers, in the order they will be hit

**1. The game's one trap is refused by the kit's trap model.** It calls `Super(<end of program>)` —
real GEMDOS's "enter supervisor mode with THIS supervisor stack". The kit's `Super` is a token
model that accepts only `0`, `1` and its own cookie (`tools/recreate_kit/TRAP_MODEL.md`, Phase 2),
so `emu.run` raises rather than fabricate a result. Pinned by
`test_the_games_only_trap_is_a_super_the_kit_refuses`. It costs nothing today — the oracle already
runs in supervisor mode, so an oracle run simply enters one instruction later, at
`WB_RELOCATOR_COPY_OFF` — but any case that must cross that instruction is blocked until the model
takes a third `Super` form.

**2. The game's own I/O is all direct hardware, and the oracle models almost none of it — MEASURED,
see [`PORTABILITY.md`](PORTABILITY.md).** With one trap in the whole image, everything the game does
to the shifter, the PSG, the IKBD and the floppy controller is a raw register access: 126 accesses
over 120 instructions, 31 reads and 95 writes, of which 18 are register-indirect and invisible to
any operand scan.

The measurement's answer, in the terms that decide a reconstruction order. **Every figure below is
out of the 25,696 bytes Ghidra has put inside a function body, which is 46.8 % of the ~54,854 bytes
`../notes/architecture.md` calls CODE** — the denominator is part of the finding, not a caveat:

* **220 of 252 functions (21,534 of 25,696 bytes, 83.8 % of what is measured; 39.3 % of the
  program's believed code) can be run end-to-end under the oracle today.** The blocker on the rest
  is the kit's outright rejection of a direct PSG **read** (`TRAP_MODEL.md`, Phase 3) — the same
  wall that put Joust's raw-floppy routine off its list. Here it is exactly three instructions: the
  floppy drive-select's read-modify-write of port A, and two mixer read-modify-writes in the sound
  module.
* **28 functions (3,348 bytes, 13.0 %) are at FALSE-GREEN risk**, and that is a *lower* bound — a
  conditional branch below them depends on a hardware read the shim answers `0` on both sides.
  Proven, not argued: under the oracle this game's floppy *polls* report a flawless error-free
  transfer on their first status test while moving nothing (the MFP FDC line is active low), the
  *commands* above them then reject that fabricated status and report hard failure, and the music
  replay tempo is chosen unconditionally by a zeroed `$fffa01` bit 7 / `$ff820a` bit 1 — BuggyBoy's
  defect, present before a line is ported.
* **T1 is empty**: every PSG writer in this game also reads the PSG, so no byte of the sound
  subsystem is verifiable *through the modeled write ledger*. That is not the same as unverifiable
  — `snd_trigger_effect` (`$1a48a`) is T0 with an exact closure and is diffable today, and 62 % of
  the sound module is runnable now.
* **The gameplay logic is portable now, as far as it has been recovered**: 136 of its 138 recovered
  functions touch no hardware at all (the two exceptions are the game's PRNGs), and 128 (12,070
  bytes) are runnable end-to-end. **The first 31 of them are ported** — the effect/state leaves and
  the joystick edge pair, the table at the end — which cost nothing in harness capability: every one
  is a T0 leaf whose whole surface is memory, exactly as the measurement predicted. So is every sprite blitter, the background scroll blitter and the
  RAD depacker. **But game logic is also the worst-measured subsystem that can be read at
  all** (only the Copylock, which cannot, is below it) — those 14,028 bytes are 36 % of the 38,942
  bytes of game-logic CODE believed to exist, against 56 % for boot and 69–100 % for sound, disk,
  input and video.

`PORTABILITY.md` also prices each missing harness capability in functions and bytes, and
[`../notes/portability_predictions.py`](../notes/portability_predictions.py) re-runs thirteen of the
classifications against the real oracle — three of the first nine were wrong on the first pass, and
the corrections are recorded in both files — plus a fourteenth check pinning the 16
background-scroll names to the jump table the game dispatches through.

**A workspace-wide defect surfaced on the way**: `tools/ghidra_scripts/PrgLoader.java` mis-parsed
the DRI relocation table's 254-byte span marker as a fixup, so **every** project's Ghidra DB was
built over corrupted bytes (536 spurious fixups here, 93 in BuggyBoy, 44 in Joust). It is fixed and
pinned by `tools/recreate_kit/test/test_reloc_table.py`; the reconstructions are unaffected because
`oracle/loader.py` always used the correct parser, but the DBs and `decomp.c` need re-bootstrapping.

**3. The overlays are decoded; the memory ceiling still is not.** `OVALAY*.RAD`, `TILEDATA.RAD`,
`SPRITES.CRU`, `DATADISK.RAD` on disk 2 are packed data the game loads by name (the names are in
the image at `0x21226`). Their **format is now established and pinned**: the depack routine is the
game's own, at text `0x596a` / runtime `0x5d62`, transcribed in `notes/rad_depacker.asm`,
reimplemented as `tools/depack_rad.py`, and diffed against the original under Musashi by
`notes/rad_differential.py` — 41/41 intact streams byte-identical, plus the 4 protection-damaged
overlays which both implementations refuse (`docs/binary-formats.md` has the format). The routine
itself is now **reconstructed** as well (`src/rad.c`, the table at the end), on the same corpus but
as a whole-image differential, so the format is pinned from both sides: a host reimplementation that
refuses what it cannot safely decode, and a faithful port that reproduces what the 68000 does
instead — garbage decode and all.

The **destinations** are readable from the five call sites, all at runtime addresses: overlays
depack to `0x217d8` (`0x3ce8` each), `TILEDATA.RAD` loads at `0x44000` and depacks to `0x4f000`
(`0x14a80`), the three full-screen files load at `0x49800` and depack to `0x6ff80` / `0x77f80`
(`0x7d80` each), and `SPRITES.CRU` is loaded raw to `0x25298` and never depacked. The highest
address any of them reaches is `0x7fd00`. That is **not** yet a memory ceiling: these buffers are
reused across phases rather than live at once, and nothing here audits the rest of the program for
other buffers — see `project.toml`'s `image_size` comment, which this narrows but does not close.

## Unverified claims this project currently rests on

- **Both waivers rest on the same fact — one trap in the image — and that scan covers the shipped
  `.PRG` only.** The game demonstrably depacks data, and it could depack code; a trap encoding that
  exists only after depacking is invisible to a scan of the file. That is why neither waiver is
  trusted: the Malloc half is re-enforced per run by `emu._vet_no_malloc_over_program()` and the
  poked-input half by `emu._vet_no_poked_input_read()`, so a trap that only exists after a depack
  reddens the run it appears in rather than being diffed. What no check covers is `OS_SCREEN_BASE`
  (`0x8000`, what `Physbase`/`Logbase` return), which is also inside this program: those two traps
  are tallied by nothing, so a program that drew into the modeled screen base would scribble its own
  code identically on both sides. Inert today for the same reason as everything else here — there is
  one trap in the image, and it is a `Super` — and recorded in
  `tools/recreate_kit/TRAP_MODEL.md`.
- **`image_size = 0x100000`** fits every address read out of the code so far (highest: `0x7fd00`),
  but no audit has established a ceiling — see blocker 3.
- **The ASCII-run rule** that separates the one real trap from the four message-table false hits is
  a heuristic with a wide measured margin (runs of 12–16 bytes vs 4), not a proof. It no longer
  stands alone: the five even-aligned hits are also pinned by offset, and the Super site by its
  selector push and its relocated argument.
- **`../run.sh` passes `0x3f8`**, so a re-bootstrap agrees with this directory and with
  `../names.txt`. It still re-imports and wipes the DB, so iterate with `../reapply.sh`.
- **The kit's relocation arithmetic has no test of its own.** `test_the_loader_changed_exactly_the
  _three_relocated_longwords` covers `oracle/loader.py`'s fixup loop, which BuggyBoy and Joust also
  rest on, from inside one project's suite. The game-specific half (no fixup lands inside the copied
  body) belongs here; the arithmetic half belongs in `tools/recreate_kit/test/`.
- **A reconstruction verified under the Copylock stub is verified for the game's DISARMED steady
  state** — the second and subsequent resource loads — **and not for the first.** The protection's
  own effects (the 96-byte register save area, the three vector installs, the decrypt cursor, the
  key it returns in `d0`) never happen under the stub, and `disk_check_signature` (`$5e3e`), the
  `$ecba` pointer table and the readers of `$f89a`/`$f89c` stay reachable only from inside the
  ciphertext. `PORTABILITY.md` §6.1's "KNOWINGLY UNPINNED" list is the full register.
- **All three of the Copylock module's protections stop at `copylock.run()`'s door, and
  `recreate_kit.harness.differential()` is a second door**: it calls `emu.run` itself, so
  `differential(entry, regs={"_pokes": copylock.stub_pokes()}, stop_pc=...)` gets no witness, no
  poke vetting and no `stop_pc` vetting, and its author must call
  `copylock.assert_did_not_execute()` by hand. Four things about that gap, so the next author
  neither over- nor under-reacts to it:
  * **Nothing that calls `differential()` goes near the protection yet.** `test_rad_depack.py` is
    the first caller, and `rad_depack` neither reaches the Copylock nor is reached from it: it is
    entered directly, its whole run is inside its own two buffers, and its cases stub nothing. The
    gap opens the day a differential runs a function on the boot path. And under this build,
    forgetting the stub does not go green: it fails loudly with `did not reach checkpoint`.
  * **The identified fix is `differential()` returning its final image**, so a caller can run the
    witness over it. Not built — nothing uses it yet, and CLAUDE.md §2 rules out speculative
    features. It is the cheaper and safer of the two candidates, and the one to build the day a
    boot-path differential is written. It closes the WITNESS half only; the two input guards would
    still have to be reached through `copylock.stubbed_image`, i.e. `differential` would need to
    take an image rather than build one.
  * **A per-run forbidden-WRITE veto in the kit was REJECTED**, not deferred. It would fire on
    `test_bootstrap.py`'s relocator runs, which write all 2,220 of the protection's bytes without
    changing one of them — the exact false positive that forced the witness to be a memory
    *difference* rather than a write set in the first place.
  * **That rejection is about the write-set FORM, not about the kit hosting a veto at all.** A
    difference-based veto over project-registered immutable ranges has no false positive on those
    relocator runs — the identity copy changes nothing — and would be the general form of this
    module's witness. It is also unbuilt, and it is the same change as returning the final image,
    so do not read "rejected" as "the kit cannot host this".
- **The Copylock witness's soundness rests on a kit-wide CPU setting**, `M68K_EMULATE_TRACE=0`. A
  trace decryptor re-encrypts as it goes and restores the vectors it saved, so a blob that ran to
  COMPLETION would leave the witness almost nothing to see; what stops it completing is that flag.
  It is now pinned in `tools/recreate_kit/kit.mk`'s `OCFLAGS` (it used to be the vendored, gitignored
  `m68kconf.h`'s own default — untracked, and asserted by no test), documented in
  `TRAP_MODEL.md`, and asserted behaviourally by
  `test_copylock.py::test_the_oracles_cpu_takes_no_trace_exception`.
- **Three test helpers are now duplicated rather than shared, and the shared home is the kit.**
  `test_copylock.py`'s `_image_writes` is the fourth copy of the `< emu.STACK_GUARD_LO` stack-band
  filter in this workspace (`notes/portability_predictions.py`, two in `projects/joust`) and its
  `_run_reaching` the second; `LONGWORD = 4` and the `rts` opcode literal are each a second/third
  spelling inside this directory alone. All of them belong in `tools/recreate_kit/harness.py`
  alongside the diff's own use of that band; folding them together is a kit change touching three
  projects and was left out of this one as out of scope. Related: `_run_reaching` clears the
  oracle's process-global coverage bitset, which is harmless only because this project has no
  session-wide coverage `conftest.py` the way `projects/buggyboy` does. Two more found by the
  review of the Copylock work and left alone for the same reason, both inside `test/`:
  `test_copylock.py`'s even-aligned operand sweep re-implements `test_bootstrap.py`'s
  `_even_aligned()`, and its `RELOCATOR_INSN_BUDGET` is a hand-rounded copy of that file's derived
  `RELOCATOR_INSN_CAP` — the derived one tracks `WB_BODY_LONGS` and the copy does not. The depacker
  work added a scratch-band predicate deliberately TIGHTER than the registered
  `< emu.STACK_GUARD_LO` family (it bounds the band above as well as below, since A7 enters at
  `STACK_TOP` and grows down); the gameplay batch needed the same one for two more batteries, so it
  now lives once in `test/leaf.py` as `stray_writes(writes, allowed)` and `test_rad_depack.py`,
  `test_effects.py` and `test_input.py` all call it. **The in-directory copies are collapsed.** What
  is left of this particular family is `../notes/rad_differential.py`'s copy — a frozen research
  artifact that must run without this directory — and the kit consolidation above; `leaf.py` is the
  shape the kit's version should take (an allowed-ranges list, with the two-sided stack band
  implicit), so folding it in is the same change. The buffer placement and corpus walk in
  `test_rad_depack.py` are still restated from `rad_differential.py`.
- **`RAD_HDR_LEN` (`include/rad.h`) and `HDR_LEN` (`tools/depack_rad.py`) are the same 12 bytes in
  two languages, accepted as pinned BEHAVIOURALLY rather than textually.** CLAUDE.md §5 asks for one
  canonical definition with the other held equal by a test; here each side has its own differential
  over the game's own corpus, so a drifted copy reddens its own suite on the first file it decodes.
  `depack_rad.py` is a workspace tool that must run without this project, so it cannot scrape this
  directory's headers the way `test/layout.py` does — which is why the equality is bought with
  behaviour instead.
- **`test/layout.py`'s header scraper is the third copy** of the same idea (`joust`'s
  `test_constants.py`, `buggyboy`'s `test_course_ring.py`). It belongs in the kit; folding the three
  together was left out of this change as out of scope. It now has cases of its own
  (`test/test_layout.py`) and refuses the two readings it used to get wrong — a duplicate `#define`
  (it took the last silently) and a leading-zero decimal, which C reads as octal and Python refuses
  (it died with a bare `ValueError` naming neither the header nor the constant).

## Functions (by address)

| Addr | Name | Bytes | Status | Verification |
|------|------|-------|--------|--------------|
| `0x682` | `joy1_newly_pressed` | 18 | verified | 21 cases: 7 frame-pairs (idle / pressed / HELD / released / mixed / all bits) x 3 entry `d0`s. It writes no memory at all, so the returned `d0` is the whole surface — compared as a full longword, which is what pins the byte-op width |
| `0x88c` | `joy1_latch_edge` | 20 | verified | 5 cases seeding all three pipeline bytes distinctly, plus a write-set assertion that each stage took its predecessor's byte (so a port that shifted the wrong way cannot pass) |
| `0x5d62` | `rad_depack` (`src/rad.c`) | 216 | verified | 45 differential cases: the 41 intact `.RAD` streams of the game's own corpus decode byte-for-byte identically (whole-image diff + `d0`), and the 4 protection-damaged overlays reproduce the garbage decode *and* the failure status. Plus a synthetic corrupted checksum, an attribution (poison) pass folded into the two smallest intact cases, and a per-case guard that the only bytes written are the destination and the scratch long |
| `0x10200` | `set_state_bbc8_1ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1020a` | `set_state_bbc8_2ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10214` | `set_state_bbc8_3ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1021e` | `set_state_bbc8_4ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10228` | `set_state_bbc8_6ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10232` | `set_state_6f9c_ffff` | 8 | verified | 4 setter cases + entry pin (the entry pin is what covers its SHORT operand) |
| `0x10296` | `effect_add4_clamped_b6fa` | 38 | verified | 10 cases: a 5-point sweep of where `value + 4` lands relative to the maximum (-4, -1, 0, +1, +4 — which pins the comparison against a SHIFTED one, though not against a non-strict one: see the batch notes) and 5 more outside the meter's own range that make the compare's SIGNEDNESS and the 16-bit wrap observable. Each case also asserts the word the meter ended at |
| `0x102bc` | `effect_add2_clamped_b6fa` | 38 | verified | Same battery as `0x10296`, with `value + 2` |
| `0x102e2` | `effect_set_bd6a_1` | 10 | verified | 4 setter cases + entry pin |
| `0x102ec` | `effect_set_bd6a_2` | 10 | verified | 4 setter cases + entry pin |
| `0x102f6` | `effect_set_bd6a_3` | 10 | verified | 4 setter cases + entry pin |
| `0x10300` | `effect_set_bd6a_4` | 10 | verified | 4 setter cases + entry pin |
| `0x1030a` | `effect_set_bbc2_80ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10314` | `effect_set_bd66_1` | 10 | verified | 4 setter cases + entry pin |
| `0x1031e` | `effect_set_bd66_2` | 10 | verified | 4 setter cases + entry pin |
| `0x10328` | `effect_set_bd66_3` | 10 | verified | 4 setter cases + entry pin |
| `0x10332` | `effect_set_bd66_4` | 10 | verified | 4 setter cases + entry pin |
| `0x1033c` | `effect_set_bd66_5` | 10 | verified | 4 setter cases + entry pin |
| `0x10346` | `effect_set_bbbe_05ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10350` | `effect_set_bd68_1` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10360` | `effect_set_bd68_2` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10370` | `effect_set_bd68_3` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10380` | `effect_set_bbc0_05ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1038a` | `effect_set_bbc6_01ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10394` | `effect_push_record_0605` | 18 | verified | 4 write-pointer cases: the reset value, mid-list, one that makes the record land ON the pointer's own high word, and one far outside the list. Hand-seeded attribution instead of the poison pass — see below |
| `0x103a6` | `effect_push_record_0508` | 18 | verified | Same battery as `0x10394`, with the record `$0508` |
| `0x103b8` | `effect_push_record_0705` | 18 | verified | Same battery as `0x10394`, with the record `$0705` |
| `0x103ca` | `effect_push_record_0803` | 18 | verified | Same battery as `0x10394`, with the record `$0803` |
| `0x103dc` | `effect_restore_b6fa_to_max` | 12 | verified | 4 cases, including a maximum BELOW the counter (which this routine LOWERS it to, unlike the two clamped adds) + entry pin |

### The .RAD depacker

The 216 bytes are the whole routine, `0x5d62..0x5e3a`, which `../names.txt` splits into three:
`rad_depack` plus the leaf helpers `rad_refill_bit_buffer` (`0x5e14`) and `rad_get_bits` (`0x5e20`).
The C folds the first into `rad_bit` — the original's inline `lsr.l #1,d0` and the refill it falls
into are paired at every call site — and keeps the second under its own name.

Four things about this row that a later reader should not have to re-derive — the register of every
way the port and the original are knowingly not the same:

* **The scratch long at `0x5e3a` is written by the test's glue, not by the port.** The original
  parks its CALLER's stack pointer there (`move.l a7,$5e3a.l`) to restore on the success path; a C
  port has no such register, so `g_rad_depack` takes the stack pointer the oracle entered with and
  writes it, and the byte-for-byte diff still covers the write. Nothing else in the image reads that
  long (`../names.txt`, `rad_saved_a7`), so the port owes it nothing else.
* **The failure path's 65536-iteration delay loop is not reproduced.** It is timing only, and this
  differential's surfaces are memory and `d0`; the oracle counts the instructions and nothing
  asserts on them. If a caller is ever found to depend on that stall, this is where it bites.
* **On the failure path the original does not restore `a7` either.** Only the success path reloads
  it (`movea.l $5e3a.l,a7`); the failure path falls through the delay loop straight to its `rts`.
  That is a REGISTER-level asymmetry, outside this differential's memory + `d0` surface, and the C
  port has no machine stack to reproduce it with. Already recorded in `../notes/rad_depacker.asm`'s
  header, `include/wonderboy.h`'s `WB_RAD_SAVED_SP` and `../names.txt`'s `rad_saved_a7` comment;
  noted here so the register of asymmetries is in one place.
* **Two deviations are latent rather than pinned**, both stated in `src/rad.c`'s file comment. The
  loop's end test is now the SIGNED compare the original's `cmpa.l a2,a1 / blt` is, but only a
  header with bit 31 set in a length can tell a signed test from an unsigned one, and no corpus
  stream has one — the form is faithful by reading, not by a case that went red then green, so that
  divergence class stays UNPINNED. And an access that leaves the mapped image diverges by
  construction: the kit's shim answers the read with zeros and drops the write, while the C indexes
  a host buffer and is undefined behaviour. Every corpus case keeps both buffers and every oracle
  write inside the image, so neither is reachable from this battery; bounding the C's accesses would
  be a kit change, not a port one, and was not made.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, since a same-second
rebuild otherwise re-runs the stale library): dropping the checksum branch reddens exactly the 5
cases that reach it (the 4 damaged files and the synthetic one), while an off-by-one in the match
source, a literal-run base of 8 instead of 9, a shortest-match length of 3 instead of 2, and
dropping the scratch-long write each redden all 46 cases that decode a stream.

### The first gameplay batch

31 leaves in two files: `src/input.c` (the two joystick routines, `0x682` and `0x88c`) and
`src/effects.c` (the 29 at `0x10200..0x103e7` — the six `set_state_*` stubs and the 23 handlers of
`effect_handler_table`). 434 bytes of code: 38 in the joystick pair and 396 in the 29 — whose
`$10200..$103e7` span is 488 bytes, the difference being `effect_handler_table`'s 23 longwords,
which sit inside the span between the stubs and the first handler. This is also the first *game
logic* the project has ported: no hardware, no OS, no callee, every one entered directly by its
case. `test/leaf.py` is the shared driver — it looks each entry point up in `../names.txt` rather
than restating an address, and requires the original's write set to stay inside the words the case
says it may touch.

**"4 setter cases" in the table above means**: the destination word is pre-set to `$0000`, `$ffff`,
`$1234` and `$a55a` in turn, the whole image is diffed, the kit's attribution (poison) pass runs on
top, and the write set is bounded to that one word. The `$ffff` seed matters because one routine
*writes* `$ffff`: on that case alone the plain diff proves nothing and the attribution pass is what
holds it. Every row also carries an **entry pin** — the bytes at the entry compared against the
instruction the battery reconstructs from the same address and immediate the C uses, so a wrong
constant fails at its own address instead of surfacing as a puzzling diff.

Six things a later reader should not have to re-derive:

* **The names are at the MECHANISM, and the batch did not change that.** `effect_set_bd66_3` says a
  3 goes into `$bd66`; what a 3 there means is still open. Reading the bodies *did* firm up the
  shapes, and `../names.txt` now carries them: `$bbbe..$bbc9` is six 2-byte HUD slots
  `{value, changed}` swept once a frame by `$b8f0`, so a handler's single `move.w #$Nff` means
  "value := N, redraw me"; `$b6fa`/`$b6f8` are the value and maximum of a meter drawn in four-unit
  cells by `$b61e`; `$b546` is a longword write pointer advanced *before* its store. The obvious
  readings (a vitality bar, an item inventory) are still **not** verified — no cell's graphics were
  followed to a meaning — and no name here asserts one.
* **One `# ctx` tag came off**, the cluster comment at `0x10200`. Reading the six bodies also
  corrected it: they are *not* "six 10-byte stubs". Five write `hud_slot_bbc8` through a long
  absolute operand at 10 bytes each, and `set_state_6f9c_ffff` uses a **short** one and is 8 — which
  is why `effect_handler_table` begins at `$1023a`. That was the only tagged line in the batch; the
  other six tagged lines in `../names.txt` are on names nothing here ports.
* **`$6f9c` has no reader among the recovered functions — but it does have one in the image.**
  `set_state_6f9c_ffff` is its only writer of the 252, and none of them reads it. Unrecovered code
  at `$6f84` does: `tst.w $6f9c.l / beq / clr.w $6f9c.l / move.w #$36,4(a0)`, i.e. it consumes the
  word as a ONE-SHOT flag — tests it, clears it (so `$6f8e` is a second writer, outside the
  recovered set) and stamps `$36` into an object field. That is more than the batch started with,
  and `../names.txt` now records it; what the `$36` selects is still unknown, so the name stays at
  the mechanism.
* **The record pushes run WITHOUT the poison pass, deliberately.** Their output includes the write
  pointer, and poisoning inverts an oracle-written byte — so the pass would hand the next store an
  odd (or off-image) address and take an address error instead of producing a case. The attribution
  it buys is done by hand: the destination word is seeded to the record's own complement, and the
  case asserts that before it runs, so a port that advanced the pointer without storing still
  diverges. `src/effects.c` also inherits the depacker's **off-image divergence class** through that
  same pointer (the oracle's shim drops a write past the image; the C indexes a host buffer, which
  is undefined behaviour) — every case seeds a pointer well inside the image, so the battery never
  enters it, and bounding it would be a kit change.
* **The clamp is signed and 16-bit, and only the tests reach the parts that show it.** The meter's
  own range is `$18..$28`, so nothing the game does distinguishes `bgt` from an unsigned compare or
  shows the `addq.w` wrapping — the five out-of-range cases per routine are synthetic on purpose,
  and they are the reason the port's `(int16_t)` casts are pinned rather than merely plausible. The
  batch's one genuinely unreachable-by-real-data note is that pair: `../names.txt` records it on
  `0x10296`.
* **The `bgt`'s STRICTNESS is faithful but unobservable, and that is an equivalence, not a coverage
  hole.** The original stores when the raise lands exactly on the maximum, and `src/effects.c`'s `>`
  reproduces it — but `>=` would store the same word on that very case, so the two implementations
  are indistinguishable through memory, `d0`, or anything else a differential can see. No seeding
  fixes this and none should be attempted: unlike the branches real data cannot reach (which better
  data *would* pin), there is nothing here to pin. What the boundary sweep does pin is the
  comparison's POSITION — a `> max+1` reddens at offset +1 and a `> max-2` at offset -1.

Two register-level asymmetries, outside the memory surface and so outside most of this battery:

* **`joy1_newly_pressed` returns in `d0`, and only its low byte is the answer** — every instruction
  is a `.b` op, so the caller's top 24 bits survive. `g_joy1_newly_pressed` takes the `d0` the
  oracle was entered with and reproduces the whole longword, which each case compares (the same
  shape as `g_rad_depack`'s entry stack pointer). No `proto` line was added for it: Ghidra already
  recovers `byte joy1_newly_pressed(void)`, which is correct, so the interface is recorded as a
  `cmt` instead. **`d1` is clobbered and nothing checks it.**
* **The two clamped adds leave their working value in `d0`**, and no case asserts on it. That is
  safe at both dispatch sites and checked, not assumed: `$ddec` and `$de62` each `jsr (a0)` into the
  handler and then execute `move.w #$3,d0` as their very next instruction, so a handler's `d0` is
  dead the moment it returns. It would only bite if a handler were ever called from somewhere else,
  and nothing in the image reaches these addresses except through `effect_handler_table`.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, since a same-second
rebuild otherwise re-runs the stale library — 312 green each time it was restored): a setter aimed at
the **wrong address** and a setter with the **wrong immediate** each redden exactly that routine's 4
cases; **dropping the clamp branch** reddens 8 (the clamping cases of both adds, and no others);
`and` → **`or`** in `joy1_newly_pressed` reddens 12 of its 21; writing a HUD slot's **value byte
only** reddens all 36 slot cases; and **storing before advancing** the record pointer reddens all 16
push cases. A seventh, comparing **unsigned** instead of signed, reddens 18 — the 8 out-of-range
cases as designed, and the whole boundary sweep as well, because the attribution pass inverts the
meter's own bytes and so drives every one of those runs negative too. 7 mutations, 0 survivors.

An eighth, `>` → **`>=`** in the clamp, **survives all 312** — and no seeding would change that. It
is the equivalence registered above, not a hole: at a raise landing exactly on the maximum both arms
store the same word, so the mutant IS the original as far as any observer goes. "0 survivors" above
therefore means *of the observable mutations*; a sweep that flips this comparison's strictness (or
any other semantically inert bit) will report a survivor that no case can or should kill.
