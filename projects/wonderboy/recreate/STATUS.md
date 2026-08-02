# Reconstruction status — Wonder Boy in Monsterland

Human-readable C reconstruction of `SWB.PRG` (the original, uncracked 1989 Activision release,
extracted from the Pasti `.stx` of disk 1), each function to be **verified byte-for-byte against the
original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi oracle
running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 103/? — the .RAD depacker (216 bytes), the first gameplay batch (434 bytes), the status
panel's leaves (430 bytes), the second tier above them (710 bytes), the third tier (1412 bytes), the
WHOLE background scroll engine (3398 bytes), the WHOLE consumer tier that reads it (2742 bytes), the
actor tier and its two projection passes (356 bytes) and the WHOLE text subsystem (678 bytes) —
10,376 bytes in all, 40.4 % of everything [`PORTABILITY.md`](PORTABILITY.md) measures.**
`make test`: 1242 cases green, of which 77 are the foundation battery below, 48 are the depacker's
differential, 187 are the first gameplay batch's, 481 are the status panel's — that last figure was
169 after batch 2 and 339 after batch 3, and the whole of the growth is `test/test_hud.py` — 231
are the background scroll subsystem's (65 after batch 5, 148 after batch 6), 113 are the actor
tier's and 105 the text subsystem's (56 after batch 8). A row appears in the
table at the end when a function is reconstructed and green; everything else in `../decomp.c` and
`../names.txt` is still only *named*, not ported.

**`panel_refresh_frame` ($b346) now has NINE of its ten callees reconstructed.** The tenth, `$bbca`,
is the sound-module blocker batch 3 registered, and it is reached by an unconditional `bsr` — so
`$b346` itself stays unported and no seeding can change that. The reasoning is in "The status
panel's third tier" below.

**THE WHOLE BACKGROUND-SCROLL STORY IS CLOSED, PRODUCER AND CONSUMER.** All fifteen routines of the
`$7522..$8228` cluster plus the request raiser at `$d28` that drives it — sixteen in all — are the
ENGINE that fills the eight pre-shifted buffers, and `bg_scroll_blit` (`$82f8`) plus the sixteen
unrolled copy variants at `$83b6..$8dfe` are the CONSUMER that copies one of them to the screen.
All thirty-three are reconstructed and green, 6,140 bytes. Nothing between `$7522` and `$8dfe` is
left named-but-unported, and **`subsystems.tsv` now draws the subsystem around both halves** —
`$7522..$8228`, `$d28..$d76` and `$82f8..$8dfe` are one `video (background scroll)` range set,
which `PORTABILITY.md` measures as 33 functions / 6,140 bytes inside a function body, 100 % of them
reconstructed. See "The background scroll engine", "Closing it" and "The consumer tier" below, and
"The portability re-measure" for what re-drawing that boundary moved.

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

## The oracle defect the status-panel batch surfaced

**Every `emu.run` used to inherit the previous run's condition codes.** A 68000 reset does not clear
the CCR and Musashi is faithful about it — `m68k_pulse_reset()` touches T, the interrupt mask and S,
and leaves `FLAG_X`/`N`/`Z`/`V`/`C` exactly as the last run left them — while `osh_run` set every
data and address register but not `SR`. So a routine that reads a condition code ON ENTRY answered
differently depending on what had run before it, in the same process.

The panel batch's four packed-BCD accumulators are the first reconstructions to read one: `abcd` and
`sbcd` fold in the extend bit, and the two instructions ahead of the first one (`move.w d0,$bd78`
and a `lea`) leave X alone, so entry X is live input. It showed up as four cases that reddened under
`-n auto` and passed on their own, each off by exactly one unit in the lowest digit.

`tools/recreate_kit/oracle/shim.c` now forces `ENTRY_SR` (`$2700`: supervisor, IPL 7, condition
codes clear) after the reset, in **both** entry points: the reset and the force are one
`enter_from_reset()` helper that `osh_run` and `osh_run_bench` share, so they cannot drift (the bench
path was left un-forced when the fix first landed, and inherited the CCR just as `osh_run` had).
Four things about that:

* **it is a correctness fix, not a new capability** — two identical `emu.run` calls now give the
  same answer, which is what a differential rests on. `emu.run` still has no way to SET the entry
  CCR, so the X = 1 entry the game itself reaches stays unreachable from a case (registered below);
* **the entry SR is a stated modelling decision now**, registered in
  `tools/recreate_kit/TRAP_MODEL.md` ("The entry state every run begins from") beside the
  `M68K_EMULATE_TRACE` one, with the same reasoning: `$2700` is the kit's convention for
  determinism, not a claim about any game's own boot SR;
* **it is pinned behaviourally on both sides.** Kit-side by
  `tools/recreate_kit/test/test_entry_state.py`, whose `entry_state_probe.c` runs one `abcd` three
  times in one process (the middle run wraps and leaves X set) — it compiles `shim.c` itself rather
  than linking the shared `liboracle.so`, so a reverted force cannot hide behind a stale artifact.
  Game-side by `test_hud.py::test_the_oracle_enters_every_run_with_the_condition_codes_clear`, over
  the reconstructions that surfaced it. Reverting the shim line and rebuilding reddens 2 of the
  kit's 5 probe cases and the game-side case with `assert 1 == 0`, so neither is vacuous;
* **the other two projects were re-run against the rebuilt oracle at this tree state** — BuggyBoy
  **292 green**, Joust **4368 green**, each with its candidate `.so` deleted first so `make` could
  not re-run a stale library. Since the oracle is shared, that is what says neither depends on a
  leaked flag, which was the risk.

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
* **The gameplay logic is portable now, as far as it has been recovered**: 112 of its 114 recovered
  functions touch no hardware at all (the two exceptions are the game's PRNGs), and 104 (7,638
  bytes) are runnable end-to-end. **61 of them / 2,986 bytes are ported and green** — the
  effect/state leaves, the joystick edge pair, and the whole status panel: its leaves, the second
  tier above them and the third tier, the table at the end. **That figure was 51 out of 138 until
  the 2026-08-02 re-measure**, and none of the movement is batches 5–9's doing: all forty-one of
  their functions end up outside the catch-all (twenty-four moved by the boundary redraw, and the
  seventeen consumer-tier blits were in the video range under either file). The +10 is batch 4's
  status-panel third tier — ten functions / 1,412 bytes ($d93a, $daf8..$db72, $b39c, $b3da, $b8f0)
  that landed after the 2026-08-01 measurement; 2,986 − 1,412 = 1,574 = 434 + 430 + 710, the old
  51's exact composition (see "The portability re-measure"). The
  measurement was right that every leaf's whole surface is memory, and right that they need no new
  harness capability in the sense it meant; the panel batch still cost `test/leaf.py` a
  register-argument glue and a per-routine instruction cap, and it surfaced a defect in the shared
  oracle (above) that a batch of one-instruction setters could never have reached. The second tier
  cost nothing further: a non-leaf differential is the same call with the callees running under the
  oracle. So is every sprite blitter, the background scroll blitter and the
  RAD depacker. **But game logic is also the worst-measured subsystem that can be read at
  all, and the re-measure made it worse rather than better** (only the Copylock, which cannot be
  read, is below it) — those 9,596 bytes are 27.8 % of the 34,496
  bytes of game-logic CODE believed to exist, against 56 % for boot and 69–100 % for sound, disk,
  input, text, actor and video. Carving the three characterised subsystems out took 4,432 measured
  bytes with them and only 14 unmeasured ones.

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
- **The status panel's fifteen `proto` lines have not been through `ApplyNames` yet** — the eight
  the leaves added and the seven the second tier did (`$b54c`, `$b5ea`, `$b74a`, `$b7c6`, `$b7ea`,
  `$bd32`, `$bd4a`). Their storage is read off the disassembly and each one is pinned from the other
  side by a differential case that feeds that register — but a `proto` commits CUSTOM_STORAGE in
  Ghidra, and wrong storage breaks a decompile rather than failing loudly, so they are unverified in
  the DB. That is blocked on the same thing as everything else in `../ghidra_proj`: the `PrgLoader`
  relocation defect below means the DB has to be re-bootstrapped before any re-apply is meaningful.
  `hud_plot_digit` ($b850) deliberately gets a `cmt` and no `proto`, for `hud_blit_meter_cell`'s
  reason and one more: it returns the advanced cursor in `a0` (which the directive forces to void)
  and its `d7` is IN AND OUT.
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
  `test_effects.py` and `test_input.py` all call it. The scroll batch then arrived with a fifth
  spelling of the band — `test_scroll.py`'s `_program_writes`, which subtracts the stack from a write
  set instead of checking one against permissions — and it had drifted: its bound was `<= STACK_TOP`,
  which excludes only the FIRST byte of the return slot and leaves the other three in. The band is
  now one predicate, `leaf.on_machine_stack(addr)`, that both `stray_writes` and `_program_writes`
  call, and its upper bound is `< STACK_TOP` for a stated reason: the longword AT the stack top is
  the return address the runner planted, and a step that rewrites it (`addq.l #4,(a7)`) is program
  output that a case reads, not a frame to excuse. **The in-directory copies are collapsed.** What
  is left of this particular family is `../notes/rad_differential.py`'s copy — a frozen research
  artifact that must run without this directory — and the kit consolidation above; `leaf.py` is the
  shape the kit's version should take (an allowed-ranges list, with the two-sided stack band
  implicit), so folding it in is the same change. The buffer placement and corpus walk in
  `test_rad_depack.py` are still restated from `rad_differential.py`.
- **The status-panel batch's own scaffolding is collapsed into `test/leaf.py`**, which
  `test_effects.py` and `test_hud.py` now share one definition of each: the operand encoders `word()`
  / `longword()` (both MASK to their width — the 68000's operand field holds exactly two or four
  bytes, and without the mask a negative `dbf` displacement raises `OverflowError` instead of failing
  readably); the five opcode encodings both batteries spell (`RTS` and the four `move.w` forms —
  each keeps its own single-use encodings next to the routines that need them); the write-set readers
  `read_bytes` / `read_int`, which replaced this directory's two spellings of "the value the original
  left at an address" and fixed the one real defect in them (both sorted their failure message's
  addresses as STRINGS, so `$b10` sorted before `$b9`); `assert_rows`, which collapsed the three
  row-comparison idioms `test_hud.py` had; and `assert_batch_is_complete`. **What is left in this
  family:** each battery keeps its own `_filler`/`_rows`/`_seeded_rows` seeding helpers, which are
  geometry-specific rather than shared. The meter-cell battery's hand-rolled plane loop, registered
  here when the leaves landed, is **collapsed**: the second tier needed the identical comparison for
  every digit, so `_plotted_column` / `_assert_column` / `_seeded_column` now live once in
  `test_hud.py` and the meter cell, the meter's own pass and all nine digit batteries call them. They
  stayed in that file rather than moving to `leaf.py` because nothing outside the panel plots an
  8-row column. **The same collapse then happened on the C side**: `src/hud.c` carried the plane loop
  twice — once in `hud_blit_meter_cell` over a host pointer, once in `plot_column` over `addr_add` —
  and `plot_column` now takes a row count and serves both, so the meter's cell walks its destination
  through the 68000's address ALU as well and a stride mutation reaches both routines. **The scroll
  batch added the branch assemblers to the same collapse**: `test_scroll.py` arrived with a third
  spelling of the branch-displacement arithmetic (`branch_w` / `dbf` / `_bsr_w` against
  `test_hud.py`'s `_forward_branch` / `_dbf` / `_bsr_to`), so `forward_branch(spanned)`,
  `backward_branch(body)` and `bsr_w(here, target)` — plus the `BRANCH_EXTENSION` of 2 all three turn
  on and the one `BSR_W` opcode — now live once in `leaf.py` and both batteries call them. Only the
  displacements moved: each battery still spells its own branch OPCODES, byte constants in one file
  and integers fed to `_op()` in the other, because that is where they differ. The whole-body entry
  pins are the proof the hoist changed nothing — 1590 bytes of scroll and every panel routine still
  match the shipped image byte for byte.
- **`tst.w Dn` now has a user in each battery.** Batch 7 collapsed `test_scroll.py`'s own two
  single-register spellings into the encoder `tst_w_dn(reg)` (four registers use it), and
  `test_hud.py` still carries the byte constants `TST_W_D5` / `TST_W_D6`. Registered on the terms
  the rotate above was: **trigger** = a third user; **home** = `test/leaf.py`, beside the branch
  assemblers, in `tst_w_dn`'s parametrised form rather than as more per-register constants.
- **RESOLVED (batch 6: the preshift was the third user; now `machine.h`'s `rotate_left32`).** `rol.l`
  used to be written twice on the C side — `src/hud.c`'s unguarded `rotate_left32(value, bits)` for
  its literal counts of 4 and 8, and `src/scroll.c`'s `rotate_left32_by_register(value, count)` for a
  RUNTIME one (a phase word, 0..14, or the 16 the right edge substitutes for phase 0), which had to
  survive a count of 0 where the 68000 rotates by nothing and C's `value >> 32` is undefined. Batch 5
  registered the trigger as the preshift batch, and that is what fired: `bg_scroll_preshift_rows`
  (`$8144`) rotates by `rol.l #2` and was the third caller. The guarded form now lives once in the
  kit's `tools/recreate_kit/include/machine.h` beside `addr_add`/`sign_ext16`, and both files call it.
  It masks the count to five bits, which is the 68000's REGISTER form exactly — `rol.l Dm,Dn` rotates
  by `Dm mod 64` and a 32-bit rotate is cyclic mod 32 — so it is total for every count a caller can
  hand it, and costs a literal-count caller nothing after inlining. Being a kit file touching three
  projects, it lands as its own commit ahead of the batch.
- **RESOLVED (batch 8: `actor_followed_x_within` was the third user; now `machine.h`'s
  `set_low_word`).** It used to be written twice, in two projects — `src/scroll.c` and joust's
  `recreate/src/object.c` — and the two bodies said the same thing: a `move.w`/`clr.w` on a longword
  register replaces the low word and leaves the high one alone. `$67f8` returns its answer in d0's
  low word with the caller's high half surviving, which is the registered trigger; the helper now
  lives once in `tools/recreate_kit/include/machine.h` next to `set_low_byte`, and both projects
  call it. Being a kit file touching three projects it lands as its own commit ahead of the batch,
  as `rotate_left32` did, and BuggyBoy (292) and Joust (4368) were re-run green against it.
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
| `0xb372` | `select_table_21e8c_and_tick_b39a` (`src/hud.c`) | 40 | verified | 12 cases: 4 flag words (including two whose LOW byte is zero, so a port that read a byte fails on one of them) x 3 tick seeds including the wrap, each asserting the published pointer and the ticked word, with the pointer pre-seeded to the other table + entry pin |
| `0xb410` | `hud_blit_record_bitmap` | 52 | verified | 22 cases: 8 selectors (the four handlers' own 5..8, plus $00, the $20 whose product SIGN-EXTENDS below the table, the largest that still fits a word and the $40 that overflows it back to entry 0) x 2 screen buffers, each comparing all 32 rows against the game's own bitmap; plus 3 entry `d0`s x 2 record addresses, since `move.b` leaves d0's high byte alive and a0 is the only thing that says where the record is + entry pin |
| `0xb562` | `bcd_add_counter_bd6e` | 32 | verified | 10 cases: 6 valid-BCD (nibble carry, byte carry, the four-digit wrap, the $4e56 call site's own +5 with a high word the `.w` staging must drop), 3 non-digit nibbles pinned against the oracle alone, and the 0 + 0 that holds the entry extend bit + entry pin |
| `0xb582` | `bcd_sub_counter_bd6e` | 32 | verified | 9 cases: 6 valid-BCD (nibble borrow, byte borrow, the wrap through zero) and 3 non-digit nibbles + entry pin |
| `0xb5a2` | `bcd_add_score_bd70` | 36 | verified | 9 cases: 6 valid-BCD over eight digits (both live call sites' addends, a carry across three bytes, the full wrap, every digit pair carrying at once) and 3 non-digit nibbles. Also the routine the oracle's entry-CCR regression case runs + entry pin |
| `0xb5c6` | `bcd_sub_score_bd70` | 36 | verified | 7 cases: 4 valid-BCD and 3 non-digit nibbles. **Dead as shipped** — no reference anywhere in the image + entry pin |
| `0xb6c2` | `hud_blit_meter_cell` | 34 | verified | 40 cases: the 5 cell bitmaps `$b61e` passes x 4 entries of the offset table (including odd ones) x both of the game's screen buffers, since this one takes its destination out of `screen_back` too; each comparing all 32 plane bytes, bounding the write set to one byte per plane so the bytes between them are proved untouched, and comparing the ADVANCED cursor against both the oracle's `a1` and the reconstruction's return value + entry pin |
| `0xb6fe` | `hud_meter_add_clamped` | 36 | verified | 20 cases: a 5-point boundary sweep x 3 amounts carrying garbage above their low word, plus the 5 out-of-range cases that make the compare's SIGNEDNESS and the 16-bit wrap observable. Its `ble` clamps where the effect handlers' `bgt` stores; the strictness is unobservable either way (see below) + entry pin |
| `0xbb8a` | `hud_blit_cell_copy` | 22 | verified | 8 cases: `$b8f0`'s own blank tile and three of its icons x 2 of its own destinations, all 14 rows compared against the game's data over a seeded destination + entry pin |
| `0xbba0` | `hud_blit_cell_or` | 30 | verified | The same 8 cases, with the expected row stated as `seed OR source` — plus a guard that the seeds actually overlap an icon, without which every case would agree with a plain copy + entry pin |
| `0xbcd6` | `hud_blit_panel_frame` | 80 | verified | 8 cases: 4 of the indices `$bbca` produces (its reset, 1, the $a it stamps and the $c it wraps at) x 2 screen buffers, all 32 rows compared + entry pin |
| `0xb54c` | `hud_draw_counter_bd6e` | 22 | verified | 13 cases: 5 counter fields x 2 screen buffers (so nothing about the destination is hardcoded), plus 3 entry `d7`s over one field — `move.w`/`swap` bury the caller's high word BELOW the four digits, and all three must draw the same thing + entry pin |
| `0xb5ea` | `hud_draw_four_digits` | 52 | verified | 15 cases: 6 fields (all-zero, a lone significant digit, zeros on both sides of one, no suppression at all, all-nines, and nibbles above 9) x 2 cursors, plus 2 that enter with the caller's `d0` set either way (the `moveq` must make them agree) and 1 that enters with the latch already raised + entry pin |
| `0xb61e` | `hud_draw_meter` | 164 | verified | 20 cases: 10 (value, maximum) pairs x 2 screen buffers, each asserting the restore flag, every cell drawn and its position in `meter_cell_offsets`. The pairs reach all five cell bitmaps, every remainder 0..3, an empty meter, a full one and the 10-cell maximum; a case-level guard fails a sweep that stopped reaching one of the five + entry pin |
| `0xb74a` | `hud_draw_score_and_size_meter` | 124 | verified | 17 cases: a 13-point threshold sweep (both sides of all five steps, plus `$0`, `$7fffffff` and the `$99999999` that reads NEGATIVE and matches none), each also comparing the eight digits, plus 2 screen buffers x 2 fonts. A guard fails a sweep that stopped reaching a step or the no-match arm + entry pin |
| `0xb7c6` | `hud_draw_larger_score` | 36 | verified | 10 cases: 6 (score, high score) pairs — either ahead, equal, both signed-negative forms and the `$80000000`/`$7fffffff` boundary — plus 2 screen buffers x 2 fonts + entry pin |
| `0xb7ea` | `hud_draw_eight_digits` | 100 | verified | 14 cases: 6 fields x 2 fonts (only the FIRST digit takes the caller's `d0`, which is what the sweep separates) plus 2 cursors + entry pin |
| `0xb850` | `hud_plot_digit` | 160 | verified | 45 cases: all 16 nibbles x 2 fonts over a raised latch, 2 cursors (one even, one ODD) x 2 fonts, the two suppressed-zero forms, the two that raise the latch, and 5 entry `d0`s that pin the `cmpi.w` on d0's low word. Each compares all 32 plane bytes, bounds the write set to one byte per plane, and compares the advanced cursor against both the oracle's `a0` and the reconstruction's return value + entry pin |
| `0xbd32` | `hud_draw_stage_number` | 24 | verified | 13 cases: 5 stage words x 2 fonts (the `swap`/`rol.l #8` must select the LOW byte — `$ff99` draws 9 and 9, not f and f), plus 3 entry `d7`s + entry pin |
| `0xbd4a` | `hud_draw_two_digits` | 28 | verified | 8 cases: 4 fields x 2 fonts, including the all-zero field that draws TWO blanks — the case only this walk can produce, since it is the one that never forces the latch + entry pin |
| `0xb39c` | `hud_draw_newest_record` | 62 | verified | 10 cases: 8 (list word, fresh flag, record) combinations reaching all four arms — the reset `$ffff`, the `$8000` that shows the empty test is SIGNED, the `$0000` that is NOT empty, fresh-with-digits, fresh-with-the-`$ff`-sentinel and neither arm — plus 2 screen buffers. Each asserts all 32 bitmap rows against the game's own data, the restore flag raised only on the bitmap arm, and the latch word untouched when the sentinel screens the digits out + entry pin |
| `0xb3da` | `hud_draw_record_digits` | 54 | verified | 18 cases: 6 record low bytes (a blanked leading zero, a forced trailing one, nibbles above 9, and the `$ff` its caller screens out) x 2 screen buffers, plus 3 entry (`d0`, `d7`) pairs that must not reach the digits and 3 record addresses + entry pin |
| `0xb8f0` | `hud_refresh_dirty_slots` | 666 | verified | 52 cases: 5 slots x 3 value bytes x 2 screen buffers for the two-way arm, the sixth slot's 8 values (its six chain arms, the zero arm and the fall-through that leaves the cell blanked) x 2 buffers, 3 request bytes, all six dirty at once x 2 buffers, and a pass with none dirty that must write nothing. Each asserts `blank OR icon` over all 14 rows, the restore flag raised and the request byte cleared + entry pin |
| `0xd93a` | `panel_restore_dirty_regions` | 446 | verified | 18 cases: each of the 15 flags raised ALONE (so a walk that restored a neighbour's region fails on the stray write), all 15 raised x 2 screen orders, and none raised. Every case seeds both screen pointers and runs the pair both ways round + entry pin |
| `0x75fc` | `bg_scroll_serve_right` (`src/scroll.c`) | 16 | verified | 3 cases: the step moves and the fill runs, the step only arms the latch and the fill STILL runs, and the step at the scroll's limit consumes the `bsr` so the pass writes exactly one byte. Each compares the whole write set for EQUALITY against a model of the step followed by the fill ON ITS OUTPUT + whole-body entry pin built from the two callees' addresses in `../names.txt` |
| `0x760c` | `bg_scroll_serve_left` | 16 | verified | The same 3 cases mirrored |
| `0x79d2` | `bg_scroll_step_right` | 106 | verified | 8 cases: both sides of the limit test, three latch words (armed / disarmed / a small POSITIVE one, which the two directions treat differently), and three phase/cell carries — mid-cell, a carry into the next cell, and one that wraps `bg_scroll_x` and zeroes the row offset. Every case reads the skip decision off the ORACLE's own rewritten return address and requires the reconstruction's flag to match + whole-body entry pin |
| `0x795e` | `bg_scroll_step_left` | 116 | verified | 9 cases: the same shape mirrored, plus a fourth borrow case that pins the `andi.w #$7f` this direction applies to `bg_scroll_row_byte_offset` and the right step does not |
| `0x7c08` | `bg_scroll_fill_right_column` | 678 | verified | 13 cases over the three words that place the column: four phases (including 0, where the mask clears the whole cell and the rotation becomes a whole 16 with the map cursor pulled back), three `bg_scroll_x` (including 1, where the second cell leaves the 128-byte row), and four coarse rows (0 = no second half, 1 = a one-tile-row second half, 10, and mid). Each compares the write set for EQUALITY against a Python model of the fill and every written byte against that model's value; the destination is seeded address-keyed over the whole $5800 buffer plus a scanline either side + whole-body entry pin |
| `0x7eb2` | `bg_scroll_fill_left_column` | 658 | verified | The same 13 cases mirrored, which pin the four differences: no `bg_scroll_x` bias, the map column fifteen cells to the left, the mask INVERTED while the phase is nonzero, and the two halves of the rotated longword swapped over + whole-body entry pin |
| `0x761c` | `bg_scroll_step_up` | 414 | verified | 8 cases x both directions: mid-ring; each ring cursor parked on each direction's wrap ROW alone (four seeds, which under the two directions give all four one-cursor-at-a-time combinations AND pin that a step ignores the wrap row it is not walking towards); one cursor on EACH wrap row, which no direction wraps both of; a coarse-row republish; and the position boundary that consumes TWO calls. Each compares the write set for equality against a model of both cursors, reads the skip off the oracle's rewritten return address (and requires it to be sentinel + 8, not + 4), and a further case asserts all sixteen `bg_scroll_buffer_rows` pointers against `buffer + row * 128` after a wrap in each direction + whole-body entry pin |
| `0x77ba` | `bg_scroll_step_down` | 420 | verified | The same battery mirrored, which pins the two places the pair are not mirror images: the boundary is `bg_scroll_limit_y` rather than zero, and the wrap test is `cmpi.w #$ae` where the up step's is `tst.w` |
| `0x7a3e` | `bg_scroll_fill_top_row` | 220 | verified | 6 cases: three `bg_scroll_tile_row` (mid-tile, 0 — where the step-BACK wraps and pulls the map cursor a row up — and the last pair) x three `bg_scroll_x` (0, whose second count is -1 = no second half; 1, whose second count is exactly 0; and 15). Each compares the write set for equality against a Python model, asserts the returned `d0` against BOTH the reconstruction's and the oracle's, and a seventh case asserts the fill touched exactly one scanline PAIR of one buffer + whole-body entry pin |
| `0x7b1a` | `bg_scroll_fill_bottom_row` | 238 | verified | The same 6 cases mirrored, pinning the four differences: the other row pointer, the map row ten strides further down, the tile-row step AFTER the draw rather than before it, and the `$ffff` marker it returns where the top fill returns 0 |
| `0x8144` | `bg_scroll_preshift_rows` | 228 | verified | 6 entry `d0`s: the two markers, both of them again under a tile offset in the HIGH half (which `tst.w` must not see), and the two words either side of the sign boundary. Each compares the write set for equality against a model of 7 copies x 2 rows x 16 cells, and asserts the walk started at copy 1 and ended at copy 7. Two more cases pin the ring: the extent of what it wrote, and that cell 0's rotated-out bits are parked in `bg_scroll_preshift_carry` and ORed into cell 15 + whole-body entry pin |
| `0x75d4` | `bg_scroll_serve_up` | 20 | verified | 2 cases: the step moves and both the fill and the pre-shift run, and the step at the boundary consumes BOTH calls so the pass writes exactly one byte — the request it consumed. Write set compared for equality against the composed model + whole-body entry pin built from the three callees' addresses in `../names.txt` |
| `0x75e8` | `bg_scroll_serve_down` | 20 | verified | The same 2 cases mirrored |
| `0x759a` | `bg_scroll_serve_requests` | 58 | verified | 6 cases: each direction raised alone, all four at once (which is what pins the ORDER — up, down, right, left — since each handler runs on the state the previous one left), and a pass with nothing raised that must write nothing at all. Each compares the whole write set for equality against the four sub-models composed in that order + whole-body entry pin |
| `0xd28` | `bg_scroll_raise_requests` | 78 | verified | 7 positions: centred (raising nothing), off-centre both ways on both axes, one pixel either side of the vertical centre, the origin, and `$8000` — the one position where the `subi.w`/`bgt` pair's OVERFLOW flag makes the branch disagree with the sign of the difference. Each states the distance the case expects, and compares the oracle's whole `d0`/`d1` against it, high halves included (they are the caller's and must survive) + whole-body entry pin |
| `0x7522` | `bg_scroll_run_queue` | 112 | verified | 5 cases: the `scroll_follow_frozen` gate both with a request already raised and with none, a centred position that raises nothing, and one- and two-step drains on both axes at once. Each compares the whole write set for equality against a model that raises, halves, drains and clears — running the dispatch pass as many times as the queue owes + whole-body entry pin, whose two `bra.s` loop-closing displacements come out of the geometry |
| `0x82f8` | `bg_scroll_blit` (`src/scroll.c`) | 110 | verified | 12 cases: 8 over the three position words (both phases at the ends of the eight buffers, four columns including the two that need no source-row wrap and the two that do, and five ring rows — 0, just below the wrap boundary, exactly ON it, one past it, mid-ring and the last row a vertical step can produce) x both screen buffers x a case that states the write set as the 240x160 window rather than as whatever the model produced, x one out-of-range ring row that separates the `bpl`'s wrapped-sign reading from a boundary comparison. Each compares the whole write set for EQUALITY against a Python model of the dispatcher and the variant together, and a further 8 assert the copy never read outside the buffer the phase named + whole-body entry pin |
| `0x83b6` | `bg_scroll_copy_x0` … `0x8d58` `bg_scroll_copy_x15` | 16 x 154/166 | verified | ONE legend for sixteen regular variants. Each is entered AT its own address with the four registers the dispatcher hands over (a0/a1/d7/d6) and copies four scanlines to the source buffer's end plus two past the `lea -$5800(a0),a0` rewind, its whole write set compared for equality against the model; four more are run with the "no second half" marker so the rewind never happens, and one asserts the rewind lands on the buffer's own first scanline. Each variant's WHOLE body is pinned against the image, assembled from one pattern parametrised by the column — and three of them (`x0`, `x2`, `x15`) are pinned a second time against bytes transcribed straight out of `../out/wonderboy_dis.txt`, so the pattern itself cannot be what is wrong. The jump table, the sixteen lengths and the gaps between them are pinned as well: the family tiles `$83b6..$8dfe` exactly |
| `0xdaf8` | `panel_restore_44x8` | 26 | verified | 4 cases: its 2 regions x 2 screen orders, all 8 rows of 44 bytes compared against the source screen + entry pin |
| `0xdb12` | `panel_restore_32x20` | 34 | verified | 2 cases: its one region x 2 screen orders, all 20 rows + entry pin |
| `0xdb34` | `panel_restore_none` | 2 | verified | 1 case: a bare `rts`, run over a band seeded the width of the WIDEST restore on both screens, which must be left untouched + entry pin |
| `0xdb36` | `panel_restore_32x29` | 34 | verified | 2 cases: its one region (the record bitmap's own origin, 29 rows where the bitmap draws 32) x 2 screen orders + entry pin |
| `0xdb58` | `panel_restore_16x14` | 26 | verified | 12 cases: its 6 regions — one per HUD slot, in the HUD-slot cell's own geometry — x 2 screen orders + entry pin |
| `0xdb72` | `panel_restore_24x32` | 62 | verified | 2 cases: its one region (the panel frame's origin and geometry) x 2 screen orders, all 32 rows + entry pin |
| `0x67e0` | `followed_actor_record` (`src/actor.c`) | 24 | verified | 5 flag words: the `$0000` and `$ffff` the image writes, plus `$0001`, `$7fff` and `$8000`. It writes NO memory, so its a1 is the whole surface — compared against the record the case names AND against the reconstruction's return value, with a case-level guard that nothing was written. The two small positives are what separate its `bne` from `project_actor_list`'s `bpl` on the same word + whole-body entry pin |
| `0x67c2` | `actor_set_side_flag` | 30 | verified | 37 cases: 9 (followed x, actor x) pairs — both sides, equal, one apart either way, both negative, and both signed boundaries — x 4 flag-byte seeds (bit 3 already raised, already clear, and both with every neighbouring bit set, which a byte-wide `bset`/`bclr` must leave alone). Plus one against the a32 record, seeded so a port that hardcoded the other one answers the other way + whole-body entry pin |
| `0x67f8` | `actor_followed_x_within` | 42 | verified | 27 cases: 13 (followed x, actor x, reach) triples — both arms of the `bgt`, both sides of each arm's boundary and the boundary itself, a zero reach, both actors negative, one either side of zero, and the two where the 16-bit ADD WRAPS out of the positive half (which an unbounded model answers the other way round on) — x 2 entry `d0` high halves, since only the low word is written. Plus one against the a32 record + whole-body entry pin |
| `0x8dfe` | `project_followed_actor` | 104 | verified | 13 cases: 11 over the state the body reads — both records, the small-positive `$a32` its callee's `bne` picks and a `bpl` would not, the positive `$a30` its own `bpl` runs on and a `bne` would not, all four combinations of the flicker bit and the frame toggle, and positions that wrap both subtractions — plus 2 negative `$a30`s that must write NOTHING at all. Each states the write set exactly (the six bytes of screen record 12) and asserts the oracle's a0/a1 against the model + whole-body entry pin |
| `0x8e66` | `project_actor_list` | 156 | verified | 17 cases: 7 (`$a30`, `$a32`) pairs reaching all three tables — including the sign boundary of each flag and the small positive `$a32` that separates this pass's `bpl` from `$67e0`'s `bne` — x 2 frame toggles, plus a stale published pointer the pass must ignore, a write set stated as the GEOMETRY (nineteen six-byte records back to back plus the published longword), and a guard that the address-keyed seed still arms the flicker bit on some records and not others + whole-body entry pin |
| `0xbf5e` | `text_plot_glyph` (`src/text.c`) | 210 | verified | 31 cases: 5 glyph sources (both ends of the frame-glyph run, two of the font's own, and the all-zero space) x 6 cursors (the buffer's first cell and its odd twin, a mid-buffer pair, and the last full text row's pair), each stating the 32 written bytes exactly and comparing the returned cursor against both the oracle's a1 and the reconstruction's. Plus a four-step cell walk that shows the +1/+7 alternation lands two plane groups on + whole-body entry pin |
| `0xbf4e` | `text_plot_char` | 16 | verified | 14 cases: 7 character codes x 2 cursors. The codes are the space the table starts at, two ordinary glyphs, the largest byte, one BELOW the first char (where the byte subtraction wraps), and two carrying rubbish in d0's high half — one harmless, one whose shifted low word is negative and indexes below the font. Each compares the indexed source against the oracle's a0 as well as the plotted bytes + whole-body entry pin |
| `0xbd8a` | `text_run_message_box` | 452 | verified | 38 differential cases over the ten state bytes: an idle frame that must write NOTHING, 2 dismiss requests, 24 composes (6 shipped messages — the minimum height, the other top line, the maximum height and line count, the shortest string, the one whose line overruns the frame, and the table's last entry — x 4 lifetime phases, including the two the shipped data cannot produce), a compose that beats an already-active box, 8 blits (4 countdown phases x the table's two extreme geometries), a blit into the other screen buffer and one at a top line whose scanline offset SIGN-EXTENDS. Each states the write set exactly — the whole 6400-byte buffer plus the latched fields, or the blitted rectangle plus the countdown — against a model built from `_model_plot` and the game's own message records. Plus 4 structural pins on the $a09c table (self-bounding three ways), one that the seven state fields tile the band, one on the geometry constants' identities + whole-body entry pin |

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

### The status panel batch

Eleven leaves of `panel_refresh_frame` (`$b346`), the game loop's once-a-frame status pass, in one
file: `src/hud.c`, 430 bytes of code across `$b372..$bd26`. `$b346` itself is `jsr $d93a` plus nine
`bsr`s and an `rts`, and that call list — the record list's display, the four-digit counter, the
score, the high score, the meter, the six HUD slots, the panel animation, a text pass and the
table-select — is the evidence for treating this region as one subsystem rather than as eleven
unrelated addresses. `../names.txt` gained the whole region: the eleven names, `$b346` itself,
`$bf4e` (which is NOT ported — see below), and eleven globals.

**This batch is the first that is not "a `move` and an `rts`."** Three things follow, and they are
what the 169 cases are shaped by:

* **Nine of the eleven take REGISTERS**, which Ghidra recovered none of (`void FUN(void)` for all
  eleven). The interfaces are read off the disassembly and `../names.txt` now carries a `proto` line
  for each one the directive can express. `hud_blit_meter_cell` gets a `cmt` instead: it returns its
  result in `a1`, and `ApplyNames`' `proto` forces a void return, so a `proto` there would record
  something false. `test/leaf.py` gained `register_glue(name, argtypes, restype)` for this — the
  shape `image_glue` already had for the register-less ones — and a `max_insns` argument: the
  straight-line leaves run at most six instructions, so `leaf.LEAF_INSN_CAP` is 64, and a routine
  that blits 32 rows needs a cap stated from its own geometry instead (400 here).
* **Five of them DRAW**, and **three** take their destination from `screen_back` (`$750`), a
  longword in MEMORY — `hud_blit_record_bitmap`, `hud_blit_meter_cell` and `hud_blit_panel_frame`.
  So every one of their cases seeds it, and seeds it with BOTH of the game's own buffers, because a
  reconstruction that hardcoded `$70000` would otherwise pass. (The remaining two,
  `hud_blit_cell_copy` and `hud_blit_cell_or`, are handed an address their caller `$b8f0` already
  resolved, in `a1`; there is no `$750` read to pin.) The expected bytes come from the game's own
  bitmaps in the loaded image, so each case says WHICH bytes moved; the allowed write set is one
  entry per row, which is what pins the 160-byte scanline stride as a stray write rather than only
  as a diff. `src/hud.c` inherits `src/rad.c`'s **off-image divergence class** through that pointer,
  and one more besides: an address computed as `base + adda.w delta` wraps at 32 bits on a 68000 and
  does not on a host pointer, so every address in the file is built as a `uint32_t` first. That is
  not decoration — the `$20` selector case reddened until it was. It is now the kit's
  `addr_add(base, delta)` (`tools/recreate_kit/include/machine.h`), which `src/effects.c`'s record
  pointer uses too; it was a `static` in `src/hud.c` until the second caller appeared.
* **Four of them are packed-BCD accumulators** over the score (`$bd70`, eight digits) and the
  counter below it (`$bd6e`, four). Their expected value is stated in DECIMAL and converted back,
  which is a different statement from the nibble arithmetic in `src/hud.c` rather than a copy of it.
  Three cases per routine deliberately feed a nibble above 9, which is not BCD: the decimal model
  declines to predict those and the differential is their whole pin — worth stating, because the
  68000's manual leaves `abcd` on such an operand UNDEFINED, so those twelve cases hold the port to
  the ORACLE's model of it and not to hardware. The game cannot reach them (both fields start
  cleared and only ever see BCD constants).

Five things a later reader should not have to re-derive:

* **`$bf4e` was in the batch and was NOT ported then. It is not a leaf.** *(Batch 8 ported it, with
  `$bf5e`, as `text_plot_char` + `text_plot_glyph` — see "The actor tier and the text plotter"
  below. What follows is the reading that deferred it, and it was right about every part of the
  shape.)* The hardware scan calls it a
  16-byte T0 function with an empty callee set; its 16 bytes have no `rts`, and it FALLS THROUGH
  into `$bf5e`, a 210-byte unrolled glyph plotter with eight `bsr` callers of its own. A
  differential entered at `$bf4e` would execute 226 bytes and verify a routine outside this batch.
  It is named and its shape recorded in `../names.txt`; porting it means porting `$bf5e` with it.
  **Read this as a caveat on the scan, not on that one address**: "T0, no callees, N bytes" is a
  claim about the bytes Ghidra put in the function, and a fall-through target is invisible to it.
* **The disassembler in `../out/wonderboy_dis.txt` prints `abcd`/`sbcd` wrong.** `c308` and `8308`
  come out as `and.b d1,a0` and `or.b d1,a0`, which would make the four accumulators read as
  nonsense. Ghidra has them right (`bcdAdjust` and `in_XF` in `../decomp.c`), and so does the
  entry-byte pin, which is built from the opcodes. `tools/prg_dis.py` is unfixed; `../names.txt`
  records the trap on `$b562`.
* **The BCD routines' entry X flag is live input and is NOT pinned beyond X = 0.** `abcd` folds in
  the extend bit and nothing between the entry and the first one touches it. X = 0 is now the
  oracle's guaranteed entry condition (see "The oracle defect..." above) and one case holds the port
  to it — 0 + 0 comes out 1 if the port assumes otherwise — but the GAME reaches `$b5a2` with X = 1:
  `$e058` does `subq.w #1,hud_meter_value`, which sets X when the meter was already zero, and
  `$e064` calls it two instructions later. So a meter at zero scores one extra unit, and neither
  `emu.run` nor this battery can express that. Honestly unpinned, and the first reconstruction in
  this workspace whose entry condition is a CONDITION CODE rather than a register.
* **`hud_meter_add_clamped` is the general form of the two effect handlers and not the same
  comparison.** `$b6fe` does `add.w d0,$b6fa` — a read-modify-write on MEMORY, so the raised value
  is stored before anything is tested — and its `ble` clamps where `$10296`'s `bgt` still stores.
  The difference is unobservable for the same reason batch 1 registered: the two arms store the same
  word at the boundary. The boundary sweep pins the comparison's POSITION, never its strictness.
* **The registers the blits leave behind are dead, and that is checked rather than assumed.**
  `hud_blit_meter_cell`'s advanced cursor IS read back (`$b61e` halves the distance it travelled to
  count the cells it drew), so the C returns it and every case compares it against the oracle's `a1`.
  The rest are not: all 18 `$bb8a`/`$bba0` call sites reload `a0` and `a1` immediately before the
  `bsr`, and `$b6c2` has **five** call sites, all inside `$b61e` — `$b648` and `$b6b8` are `dbf`
  loop bodies (the full cells and the empty ones), `$b660`/`$b676`/`$b68c` are the three arms of the
  one-shot `cmpi.w`/`bne` chain that draws the single partial cell — every one of which `lea`s `a2`
  in the instruction immediately before, the two loop sites doing so inside the loop body. The kit's
  oracle reports `d0`/`d1`/`a0`/`a1` only, so `a2` could not have been compared in any case.

Reference counts in `../names.txt` for this region are **byte scans of the whole image** for each
address as an `abs.l` operand and, where it fits, as an `abs.w` one — not walks of the 252 recovered
functions, which is the qualifier batch 1's notes had to keep attaching. **That method has one blind
spot: a PC-RELATIVE operand.** `lea $b6e4(pc),a0` encodes as `41fa 0052`, a displacement with the
target address nowhere in the bytes, so no scan for `$0000b6e4` can see it. A `d16(pc)` sweep (every
even offset whose opcode carries EA mode 7 / reg 2, resolved to `pc + 2 + d16`) was run over all
eight addresses this batch counts and found exactly one such reference in the image — `$b690`, now
recorded under `meter_cell_offsets`, which therefore has two references and not one. Two results
that survive the sweep and are worth having: `frame_tick_b39a` has exactly two references (this
batch's `addq.w #1` and `rng_next`'s read), so the panel pass is the **only** writer of the PRNG's
only non-hardware entropy; and `bcd_addend_bd78` has exactly four, all of them the accumulators' own
staging writes, so that scratch longword is invisible to the rest of the program.

Mutation-checked rather than assumed, re-measured at this tree state (each rebuilt with the `.so`
deleted first, since a same-second rebuild otherwise re-runs the stale library — 481 green each time
it was restored): the BCD decimal correction `+6` → `+5` reddens 19; **dropping the meter's clamp
branch** reddens 11; **swapping the table-select's two arms** reddens 12; degrading the **OR blit to
a copy** reddens 8; returning the **unadvanced cursor** from the meter cell reddens 40; dropping the
**sign extension** in the indexed bitmap address reddens 6; and a **row stride of 158 instead of
160** reddens 38. 8 mutations, 1 survivor.

Two of those numbers moved since the batch first landed, both for stated reasons rather than for
drift: the meter cursor's went 20 → 40 because its battery now runs over both screen buffers, and
the stride's 22 → 38 because `src/hud.c`'s three identical row loops are now one `copy_rows`, so the
mutation reaches the record bitmap, the HUD-cell copy and the panel frame at once instead of the
record blit alone. The refactor made that mutation coarser; no per-blit stride survives it.

That survivor is `<=` → **`<`** in `hud_meter_add_clamped`, and it is the equivalence above rather
than a coverage hole: the two comparisons differ only where the raise lands exactly on the maximum,
and there both arms store the maximum. It is the same inert bit batch 1's clamp has, mirrored.

### The status panel's second tier

Nine routines, 710 bytes, in the same file: `src/hud.c`, `$b54c..$bd65`. Eight of them are **the
first reconstructions in this workspace that are not leaves** — the three field walks, the four
fields above them and the meter's own pass, each of which calls another, the tallest chain three deep
(`hud_draw_score_and_size_meter` → `hud_draw_eight_digits` → `hud_plot_digit`). The ninth,
`hud_plot_digit`, calls nothing: it is a leaf, and came in with this batch only because six of the
other eight cannot be ported without it. So the twenty routines in `src/hud.c` are **twelve leaves
and eight non-leaves**, which is not the batch-2 / batch-3 line.
The differential shape that makes that work is the one Joust established: on the original's side the
`bsr` runs its callee under the oracle, on the reconstruction's side the C calls the ported C, and
the two are required to agree byte for byte anyway. So a defect anywhere in a chain reddens every
case above it — the eight-digit walk's mutations redden the score and the high score too.

**The cluster is the digit plotter and everything that walks a field of digits.** `hud_plot_digit`
($b850) rotates a register left by a nibble and draws the nibble that was on top: 8 rows of one
8-pixel column, four plane bytes at +0/+2/+4/+6. Above it are three field walks (4, 8 and 2 digits),
and above those the four fields `panel_refresh_frame` draws — the counter, the score (which also
sizes the meter), the high score and the stage number. `hud_draw_meter` ($b61e) is in the batch for a
different reason: its callee `hud_blit_meter_cell` was already ported, so it was the one candidate
that needed no prerequisite at all.

**$b850 WAS THE PREREQUISITE, AND IT WAS NOT IN BATCH 2.** Six of the nine could not be ported
without it (their whole closure is `→ $b850`), so the leaf came in with the tier that needs it. It
has sixteen call sites, and the two the batch does NOT reach are inside `$b3da`, which stays unported
— so the leaf is verified over a superset of the fields ported here, but not over that caller's use
of it.

**Three candidates were STOPPED, and the reasons are findings.** The batch was scoped off
`../out/hw_scan.tsv`, which classified all three as clean-closure game logic:

* **`$bbca` ($bcd6's driver, 268 bytes) IS NOT IN THIS SUBSYSTEM.** The scan gives it one callee;
  besides its four `bsr $bcd6` it does `lea $17adc.l,a1 / jsr 56(a1)` at `$bc9c`/`$bca2` — a FIXED
  call to `$17b14`, the `movem`-wrapped thunk into `snd_trigger_effect` (`$1a48a`). A differential
  entered at `$bbca` runs the sound module on the oracle's side, so porting it means porting that
  closure too. **Read this as a caveat on the scan, not on that one address**: "N callees" is a claim
  about the calls Ghidra RESOLVED — the same class of blind spot as the fall-through that made
  `$bf4e` not-a-leaf. Recorded on `$bbca` in `../names.txt`.
  **UNRESOLVED, and not to be guessed at: why the scan dropped `$bca2` entirely.** An unresolved
  indirect call is supposed to be *reported*, as an `I` record that `hw_portability.py` lists under
  "unresolved indirect call/jump site(s)" — and `jsr d16(An)` does land there normally: the same
  `../out/hw_scan.tsv` opens its ledger with `I 0x716 0x726 jsr (0xe,A0)`. For `$bbca` that file has
  four `E 0xbbca 0xbcd6 CALL` rows, ten `I` rows in the whole image, and **no `I` row for `$bca2`**,
  so this site is in neither ledger and nothing in the output flags it. Whether Ghidra never made the
  instruction a call-flow reference, or the script's own filter dropped it, is **not diagnosed** —
  the earlier reading "a `jsr d16(An)` off an immediate `lea` is invisible to the graph" is wrong as
  a general rule and was replaced by this. Marked for investigation; until it is, treat *any* call
  site absent from both ledgers as a scan defect, not as a known limit.
  (`docs/on-target-execution.md` rule 4 and `tools/ghidra_scripts/HwPortabilityScan.java`'s `I`
  record carry the short form.)
* **`$b8f0` (the six HUD slots, 666 bytes) is in scope but oversized.** Its closure is clean and both
  callees (`hud_blit_cell_copy`/`hud_blit_cell_or`) are already ported, so it is portable today; at
  666 bytes and 18 blit call sites it is a batch of its own. Now named and scoped in `../names.txt`
  (`hud_refresh_dirty_slots`): six slot records, a request byte each, blank-then-OR per slot.
  *(Landed in batch 4.)*
* **`$b346` itself cannot be ported until four more are.** It is ten calls and an `rts`; SIX of the
  ten are now reconstructed (`$b54c`, `$b74a`, `$b7c6`, `$b61e`, `$bd32`, `$b372`) and four are not
  — `$d93a` (446 bytes, the screen-region restore), `$b39c` (whose own `$b3da` is `$b850`'s other
  caller), `$b8f0` and `$bbca`. *(Batch 4 landed three of the four; `$bbca` remains, and the section
  after this one records why it is a hard stop rather than a queue position.)*

Six things a later reader should not have to re-derive:

* **Every entry pin here is the routine's WHOLE BODY, not its first instruction.** All nine matched
  byte for byte on the first run, which is the strongest single result in the batch: it means the
  step immediates, the branch displacements, the shift counts, the glyph stride, the five score
  thresholds and every `bsr` target were read correctly before a differential was run. Two of them
  are built rather than transcribed and that is deliberate: a `bsr.w` displacement is computed from
  the two entry points `../names.txt` gives (so a reconstruction aimed at the wrong callee fails at
  its own address), and the shift/rotate opcodes are assembled from the geometry constants (so
  `asl.w #5` is spelled out of `WB_DIGIT_GLYPH_LEN` and `asr.w #2` out of `WB_METER_CELL_UNITS`,
  rather than restating the counts).
* **THE FONT IS AN UNSET REGISTER.** `panel_refresh_frame` sets neither `d0` nor `d7` before any of
  its nine `bsr`s, and `$b850` reads `d0` (`cmpi.w #1,d0` picks between two overlapping glyph tables,
  and also picks what a suppressed zero looks like). So the glyphs three of the four fields are drawn
  with are whatever the routine before them left behind. That is the game's behaviour, not a gap in
  the reading; the port takes `d0` as an argument and every battery sweeps both sides of the compare.
  The four-digit walk is the exception — its first instruction is `moveq #0,d0` — and a case that
  enters it with `d0 = 1` and gets the same bytes is what pins that.
* **The leading-zero latch is a WORD IN MEMORY, and the three walks disagree about it.**
  `digit_significant_seen_b84e` suppresses a zero until something significant has printed. The
  four-digit walk forces it before its LAST digit, the eight-digit walk before its last TWO, and the
  two-digit walk not at all — so a stage number below 10 really is drawn as one digit and a blank.
  All three clear it on the way out, which is why every case can read the final value back. The
  battery states that rule independently of `src/hud.c` (`_field_expected`) rather than copying it.
* **A "blank" is not nothing.** Under the default glyphs a suppressed zero is `clr.b` on three planes
  and `st` on the fourth — a solid $ff, i.e. a coloured bar — while under the alternate glyphs all
  four are cleared. That single plane byte is the *only* place `d0` is observable on a zero digit,
  which is why the `cmpi.w`-on-the-low-word case runs on a suppressed zero rather than on a glyph.
* **The two glyph tables OVERLAP.** `$145bc` is `$1447c + $140`, exactly ten glyphs in, so "the font"
  is a window into one twenty-glyph block and a case that fed the wrong table would still read real
  image data. Pinned by its own assert.
* **`$b74a`'s five thresholds are SIGNED longword compares.** A score whose top nibble is 8 or 9
  reads negative, matches none of the five and leaves `hud_meter_max` untouched — which the sweep
  reaches with `$99999999`, a value the game's own BCD accumulator can produce. `$b7c6` has the same
  signedness: a score with bit 31 set loses to any small high score.

Three things this battery knowingly does not pin, all of them registered rather than argued:

* **`hud_plot_digit`'s OUTGOING `d7`.** The rotation is the routine's other output and the oracle
  reports `d0`/`d1`/`a0`/`a1` only. What the cases do pin is the rotation's effect on the digit
  *selected* (all sixteen nibbles), and the three walks pin the carry-over from one digit to the next
  — a port that rotated the wrong way reddens 110 cases (the figure the mutation register below
  measures on this tree; it was 112 before `rotate_left32` was shared, and the paragraph after that
  register says why sharing it LOWERED the count, and why batch 6 makes it a FLOOR rather than the
  count). Only the value in the register at the instant of the `rts` is unobservable.
* **WHICH HALF OF THE CALLER'S `d7` ENDS UP UNDER THE FIELD.** `move.w field,d7 / swap d7` leaves the
  caller's own high word in the low half, and neither the four-digit walk (four rotations) nor the
  two-digit one (two, after a `rol.l #8`) can rotate it back up. So `entry_digits >> 16` and
  `entry_digits & 0xffff` are indistinguishable through memory *and* through the four reported
  registers — a mutation swapping them survives all 651 (re-measured on this tree). The port is
  faithful by reading; no seeding
  would change that, because the bits never reach an observer. Same family as "the registers the
  blits leave behind".
* **`hud_draw_meter`'s RUNAWAY LOOP.** Every step after the `divu` is 16-bit, so a maximum below the
  value makes the empty-cell count negative, the `bne` still takes the loop and the `dbf` runs it
  down through 65535 iterations, walking the cursor far past `meter_cell_offsets`' ten entries and
  blitting off the end of the screen. `src/hud.c` reproduces it by construction (the count is a
  `uint16_t` and the loop is its exact value), no case reaches it — the battery's own `_meter_plan`
  refuses to build one — and **whether the game's own writers can produce it was not established**:
  `$fe4a` resets both words to `$14` and `$b74a` only raises the maximum, but the value has writers
  outside the recovered set. Honestly unpinned.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and compared byte for byte against a pristine copy afterwards — 649 green each time; every
figure below was re-measured against the tree as the batch landed, not against the draft it was
written on. The review then added the two raised-entry-latch cases, taking the suite to **651**; the
per-mutation counts below were NOT re-measured against those two, only the staged-field survivor
was):
a **blank filling the wrong plane** reddens 61; the shared 32-bit rotate **reversed** reddens 110;
the font selected on **d0's whole longword** reddens 1; the eight-digit walk **forcing the latch one
digit late** reddens 7; the two-digit walk **forcing the latch** like the other two reddens 8; the
score's threshold compare made **strict** reddens 5; the score compared **unsigned** reddens 1; the
meter's partial cells for **remainders 3 and 1 swapped** reddens 4; the empty count dividing the
maximum by **2 instead of 4** reddens 18; and the stage number's **`rol.l #8` cut to a nibble**
reddens 11. **12 mutations, 10 killed, 2 survivors — one equivalence and one ORACLE BLIND SPOT.**
The equivalence is the `>` → `>=` in `hud_draw_larger_score`: at equality the two fields hold the
same bytes, so both arms draw the same digits — the same inert bit batch 1's and batch 2's clamps
have. **The staged-field half above is NOT an equivalence and should not be filed as one**: `>> 16`
and `& 0xffff` put *different words in d7*, i.e. different machine state, and the two are
indistinguishable only through the `d0`/`d1`/`a0`/`a1` window the kit's oracle reports. It is the
same family as "the registers the blits leave behind" and "`hud_plot_digit`'s outgoing `d7`" — a
missing observer, not an inert bit. **Re-run this mutation if the oracle ever grows `d7` reporting**;
it should die then, and if it does not, the reading was wrong.

Three of those numbers are worth reading rather than skimming. The **font-on-the-longword** mutation
reddens exactly ONE case — the `d0 = $dead0001` blank — because that is the only case whose `d0` has
rubbish above a low word of 1; that is a battery with one case per claim, not a thin pin. The
**unsigned score compare** likewise reddens exactly the `$99999999` case, the only seed with bit 31
set. And the rotate's 110 is lower than the 112 the same mutation gave before `rotate_left32` was
factored out of the two rotate sites: it now flips the stage number's `rol.l #8` as well, and a
handful of stage cases come out identical under two flips that the nibble flip alone reddened. A
shared helper makes that mutation COARSER, exactly as the leaves' `copy_rows` did to the stride one.
**Read 110 as a FLOOR, not the count, since batch 6.** It was measured while `rotate_left32` was
`src/hud.c`'s own; the helper now lives in the kit's `include/machine.h` and `src/scroll.c` calls it
twice, so flipping it today also reddens scroll cases — the same coarsening one step further out. The
panel's own 110 was not re-measured, because the mutation no longer isolates the panel.

### The status panel's third tier

Ten routines, 1412 bytes, in the same file: `src/hud.c`. They are `panel_refresh_frame`'s three
remaining table walks and the six blits under one of them — the region restore that opens the frame
(`$d93a` and `$daf8`/`$db12`/`$db34`/`$db36`/`$db58`/`$db72`), the newest record's display (`$b39c`
and `$b3da`) and the six HUD slots (`$b8f0`). With them the pass has **nine of its ten callees
reconstructed**.

**WHAT THE THREE WALKS HAVE IN COMMON is a REQUEST BYTE that is consumed rather than read.** Each
finds its work by testing a byte something else raised and clearing it in the same breath: the
fifteen restore flags at `$dbb0`, the fresh-record flag `$b54a` (which `$b39c` tests but never
clears — see below), and the six slot request bytes at `$bbbf`/`$bbc1`/… So these are the first
reconstructions here whose write set includes bytes they were *told about* as well as bytes they
drew, and every case asserts the clear as well as the pixels.

**`$d93a` IS THE OTHER HALF OF EVERY `st $dbbN` IN THIS SUBSYSTEM,** and its table is the strongest
single piece of evidence the batch produced. Fifteen entries, each naming a screen offset; **eleven
of those offsets are constants `include/wonderboy.h` already carried** for a draw in this file — the
score, the high score, the counter, the record bitmap, the six slot cells and the panel frame — and
two of the five blit geometries are geometries this file already had: `$db58` moves 16 bytes over 14
rows, which *is* `hud_blit_cell_copy`'s cell, and `$db72` moves 24 over 32, which is the panel
frame's. So an entry means "put the front buffer's pixels back over what that draw dirtied", and the
header reuses the constants rather than restating them (a test asserts the two geometries are the
same numbers, since nothing else would).

**THE PAIRING IS NOT EXACT, and the port reproduces the original rather than the intent.** Five
things a later reader should not have to re-derive:

* the `$2800` entry restores **29 rows where `hud_blit_record_bitmap` draws 32**;
* the `$aa0` entry (the meter's — `panel_restore_flag_dbb3` has exactly one writer in the image,
  `hud_draw_meter`'s `st`) covers rows 17..36, and `meter_cell_offsets` starts at `$a01`, **row 16**,
  so the restore misses the meter's top row;
* the counter's entry `bsr`s **`$db34`, which is a bare `rts`** — a routine, not an absent call,
  which is why it is reconstructed as one and has an entry pin of its own;
* the **first three entries have no `bsr` at all**: they compute both cursors and fall through to the
  next test. They clear their flag and draw nothing, exactly like the `$db34` entry, and the
  difference between the two shapes is visible in the disassembly and nowhere else.
* **three of the eleven blitting entries have no writer in the image at all.** A whole-image
  `abs.l` scan for each of the fifteen flag bytes finds a writer for only eight — `$dbb3`, `$dbb5`
  and `$dbb6..$dbbb` — so the other seven (`$dbb0`/`$dbb1`/`$dbb2`/`$dbb4`/`$dbbc`/`$dbbd`/`$dbbe`)
  are never raised by anything a scan can see; four of those seven are dead entries anyway, and the
  remaining three DO blit, **including the panel frame's own `$dbbc`**. Recorded on
  `panel_restore_flags` in `../names.txt`; the differential enters `$d93a` directly, so the cases
  reach every entry regardless.

**THE RECORD'S DIGITS ARE DRAWN INSIDE THE RECORD'S BITMAP.** `$b3da` plots at `screen_back + $3490`,
which is row 84 byte 16, and `hud_blit_record_bitmap` fills rows 64..95 of bytes 0..31 — so on a
frame that takes both of `$b39c`'s arms the bitmap goes down first and the two digits are stamped
into it. The battery pins that geometry as its own assert and compares the bitmap's rows with the
digit bytes left out; without it the bitmap assert would have been red for the wrong reason. `$b3da`
is also **a fourth digit-field walk**, beside `$b5ea`/`$b7ea`/`$bd4a`, and the only one that forces
the ALTERNATE font (`move.w #1,d0` before *each* of its two plots) — which is why `hud_plot_digit`'s
sixteen call sites are now all inside reconstructed code.

**`record_fresh_flag` ($b54a) IS NEVER CLEARED.** It has exactly two operand references in the whole
image — one `st` at `$1262`, inside the unrecovered list-walker at `$1208`, and `$b39c`'s `tst.b` —
and no `clr` among them. So once something raises it the record's bitmap is redrawn every frame from
then on. The claim is an `abs.l` scan and cannot see a writer that reaches the byte through an
address register; stated that way in `../names.txt` rather than as "nothing clears it".

**`$b346` IS STILL NOT PORTABLE, and the reason is now final rather than arithmetic.** Its one
remaining callee is `$bbca`, the sound-module blocker batch 3 registered — and the `bsr.w $bbca` at
`$b364` is one of ten UNCONDITIONAL calls, not a branch. So no seeding of the image can steer a run
entered at `$b346` around it: the oracle would execute the `jsr 56(a1)` thunk into
`snd_trigger_effect` whatever the timers hold. Porting `$b346` therefore means porting `$bbca`,
and porting `$bbca` means either porting the sound module or shipping a reconstruction with a whole
subsystem call silently missing on one side. Neither was done, and **`$bbca` remains the single
blocker**; the `$bd2c > $a` branch inside it that skips the thunk is a seedable escape *if* that
routine is ever ported on its own terms, which is a scoping decision for a sound batch and not for
this one.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and compared byte for byte against a pristine copy afterwards — 793 green each time):
the restore's source **stepping a row instead of a scanline** reddens 35; the `32x29` restore moving
the record bitmap's **32 rows** reddens 5; the bare `rts` **quietly blitting a cell** reddens 4; the
walk restoring **front from back** reddens 13; the walk **leaving its flag raised** reddens 17; the
walk **ignoring its flag entirely** reddens 16; a **dead entry given a blit** reddens 3; **two
restore regions swapped** reddens 2; the record display's empty test made **unsigned** reddens 2; the
record digits taking the record's **high byte** reddens 22; those digits drawn in the **default
font** reddens 24; their **latch forced one digit early** reddens 9; the slot pass **ORing before the
blank is laid down** reddens 35; the slot pass reading the **request byte as the value** reddens 25;
the slot pass **leaving the request byte set** reddens 51; the sixth slot's **out-of-range variant
drawing the last icon** reddens 2; and its **variant chain off by one** reddens 10.
**18 mutations, 17 killed, 1 survivor.**

**THE SURVIVOR IS DEAD DATA IN THE PORT, and it is registered rather than fixed.** Replacing
`WB_SCORE_ORIGIN` with `0x1234` in `PANEL_RESTORE_REGIONS`' first row leaves all 793 green. The
first three entries have no `bsr`, so their origin is never used for anything a case can observe —
the ORIGINAL's `lea` operands for those entries ARE pinned, byte for byte, by `$d93a`'s whole-body
entry pin, but the port's own copy of them is not, and no seeding can make it so. That is the
CLAUDE.md rule for a branch the data cannot reach, applied to a constant: say so and leave it
honestly unpinned. `src/hud.c` marks the three rows DOCUMENTARY at the table.

**Four of the eighteen were survivors first, and the fixes are house patterns worth keeping.** The
`32x29` restore moving 32 rows and the bare `rts` blitting a cell both survived the first sweep: the
cases seeded exactly the region's own geometry, so an over-copy read ZEROS from the source screen
and wrote them over ZEROS on the destination, and both sides still agreed. **A screen-to-screen blit
is the shape that has this hole** — the bitmap blits do not, because their source is real image data
(a probe confirms it: one row too many on the record bitmap, the HUD cell and the panel frame each
redden, and `test_the_bitmap_sources_are_non_zero_past_their_last_row` now keeps that property from
being lost silently). So every region case seeds its region WIDENED by a margin
(`REGION_MARGIN_ROWS`/`_BYTES`) on both screens, with filler keyed on the ADDRESS rather than on a
row index — the widened bands of two side-by-side slot cells overlap, and an index-keyed filler
would have let the later poke silently rewrite the earlier one. The review then found the same hole
ONE LEVEL UP, and the last two mutations are its measure: the walk's cases seeded a band only for
the entries that WERE to be restored, so "flag down ⇒ region untouched" and "a dead entry stays
dead" were pinned nowhere. `_run_restore_walk` now seeds all fifteen bands whatever the case, the
four dead entries at the WIDEST of the five geometries. The general lesson is written up in
[`docs/methodology.md`](../../../docs/methodology.md), "The seeding hole a mutation sweep finds".

**One branch of the slot pass is unreachable from the game's own data, and is pinned only by
fabricated bytes.** The sixth slot's variant chain has six arms; the recovered setters
(`src/effects.c`) write 1, 2, 3, 4 and 6, so **arm 5 and the `> 6` fall-through are reached in this
battery only by a value byte a case invents**. Both are pinned against the ORIGINAL (the differential
runs the real chain on the same invented byte), which is a real pin — but read the STATUS row's
"the sixth slot's 8 values" as eight *addressable* values, not eight the game produces.

**Every one of the ten entry pins is the routine's WHOLE BODY and every one matched on the first
run** (`panel_restore_none` included, all two bytes of it) — 1412 bytes, including `$b8f0`'s 666 and `$d93a`'s 446. Both of those are built from the same
table the reconstruction is (the six slots and the fifteen restore entries), so a routine wired to
the wrong region, flag, cell or callee fails at its own address rather than as a diff. The `movem`
masks are now built from a register LIST rather than transcribed, which is what ties `$daf8`'s
44-byte row to the eleven registers it moves.

### The background scroll engine (batch 5), and what the cluster turned out to be

Six routines, 1590 bytes, in a new file: `src/scroll.c`. The cluster at `$7522..$8228` was
unexplored — the hw scan could say only that it was fifteen functions with no hardware access and
every callee inside itself. **It is the level's SCROLLING ENGINE**, and the shape is worth stating
before the batch notes because everything else follows from it.

**THE GAME KEEPS EIGHT PRE-SHIFTED COPIES OF THE BACKGROUND.** `$5800` bytes each, tiling
`$44000..$70000` — the map `project.toml` already recorded from a longword scan, now explained. Copy
N is the same tile map drawn two pixels further left than copy N-1, so a two-pixel horizontal scroll
is a change of BUFFER and not a redraw, and the only work per step is the ONE tile column the scroll
uncovers. `bg_scroll_blit` (`$82f8`, named in a previous pass but not ported) is the consumer: it
copies the chosen buffer to the screen. Three independent readings agree on the model:

* `bg_scroll_phase` (`$83ac`) is used THREE ways in one routine — `mulu.w #$2c00` to pick the
  buffer, as a byte index into `bg_scroll_edge_masks`, and as the `rol.l` count that shifts the
  tiles. That is only coherent if the buffer index and the pixel offset are the same number. It was
  named `bg_scroll_buffer # ctx` before this batch; the `# ctx` tag is now gone and the name is
  `bg_scroll_phase`.
* `bg_scroll_preshift_rows` (`$8144`, read here and ported in batch 6) does nothing but walk a freshly drawn row
  through the seven remaining copies, `rol.l #2` at a time — the other half of the same scheme.
* The eight buffer addresses `bg_scroll_step_up`/`_down` reload are exactly `$44000 + N * $5800`.

**THE STEPS RETURN THROUGH THE STACK, and that is the batch's transferable finding.** A step with
nothing to do does `addq.l #4,(a7)` (or `#8`, in the vertical pair) and `rts`, returning PAST its
caller's `bsr` to the fill. One act means both "no movement" and "skip the redraw". **Ghidra models
none of it** — `../decomp.c` shows a bare `return` for that arm and an unconditional pair of calls
in the caller, so a reconstruction written from the decompiler would read correct and behave wrong.
It is not a hw-scan blind spot (the routines have an `rts`, no hidden callee, no hardware), it is a
decompiler one, and it is now written up as general 68000 method in
[`docs/m68k-disassembly.md`](../../../docs/m68k-disassembly.md).

It also broke the harness, in the way that idiom always will: the kit stops a run when the PC
reaches the sentinel it pushed as the return address, and the skipping arm returns to *sentinel + 4*
instead. `test/leaf.py` gained a `stop_pc` passthrough for it, and — because a second stop PC on its
own would let both arms pass the same case — every step case **reads the decision off the oracle's
own stack**: `emu.run` writes the sentinel AT A7, so the skipping arm has rewritten that longword to
sentinel + 4 and the other arm never wrote there at all. The reconstruction's returned flag is then
required to agree with it. Neither side is trusted to report its own answer.

**THE FILL CASES COMPARE A WRITE SET FOR EQUALITY, not for containment.** A column fill is a
read-modify-write over a buffer — `and.l` a mask over the cell the scroll vacated, then `or.w` the
rotated tiles back into it — which is the shape batch 4's mutation sweep found the seeding hole in.
Two defences, from opposite directions: every case seeds the whole `$5800` buffer PLUS a scanline
either side with a byte keyed on the ADDRESS (so an over-run writes something wrong, rather than
zeros over zeros — with a per-case salt taken from the case NAME by `crc32`, not by `hash()`, whose
randomisation per process would make a failure unreplayable and the red counts below unstable), and
every case then requires the oracle's write set to be EXACTLY the address set
a Python model of the fill produces, and every byte in it to be that model's value. The model is
written from the disassembly rather than from `src/scroll.c`, so it is a third statement of the
geometry and not a copy of the second.

**THE TILE SOURCE IS THE GAME'S OWN PIXELS, and there are only sixteen of them in the .PRG.** The
region `bg_tile_bitmaps` covers holds 148 bitmaps of 128 bytes; tiles 0..119 and 136..147 are ZERO
in the shipped file and filled at runtime (as the map, the tile index and the row stride all are —
they live past the program's end at `$218d0`). Only tiles **120..135** ship. Every case draws from
those, so no rotation is a rotation of zeros, and
`test_the_shipped_tile_bitmaps_are_the_sixteen_the_header_names` is the reading that fixes the two
numbers in `include/wonderboy.h` rather than asserting them.

**FOUR PIECES OF EVIDENCE CAME OUT OF THE READING that the batch did not need but the next one
will.** All four are in `../names.txt`:

* **`bg_scroll_raise_requests` (`$d28`) is what drives the whole cluster**, and it settles the
  direction names independently. It compares two words at `$9934`/`$9936` against `$5a` and `$30`
  and raises the request byte for the side the value falls on, returning the distances. So "left"
  means the tracked object is left of centre, and the routine that request reaches is the one that
  DECREMENTS `bg_scroll_pos_x` and fills the column at the map cursor's own cell — while "right"
  decrements nothing and fills fifteen cells further on. The two namings were derived separately and
  agree.
* **Two of the four request bytes have no writer anywhere in the image.** An `abs.l` scan finds a
  writer only for `$8230` and `$8232`, both inside `bg_scroll_run_queue` — and both are WORD moves
  of a byte PAIR, so `$8231` and `$8233` are raised only as the low halves of them. Same family as
  batch 4's "three of the eleven blitting entries have no writer": stated as what the scan sees, not
  as "nothing raises them", because a write through an address register is invisible to it.
* **The two split tables are the ring geometry, and both are pinned as data.**
  `bg_scroll_col_split_table` entry k is `(10 - k, k - 1)` and `bg_scroll_row_split_table` entry k is
  `(15 - k, k - 1)`, so a fill's two `dbf` halves always sum to exactly one buffer's worth of tile
  rows and entry 0's second count is `-1` = no wrap needed. Neither table has an `abs.l` reference of
  its own: both are reached only by a `lea` on the word before them, which is why
  `bg_scroll_col_split_table`'s `var` line records that its justification is
  `bg_scroll_y_coarse`'s `move.w (a5)+,d0`.
* **`bg_scroll_edge_masks` is `$ffff << phase` for every entry but the first**, which is `$0000`
  rather than the `$ffff` the rule would give — so phase 0 clears the whole cell and redraws it, and
  the right-hand fill's `move.w #$10,d5` / `lea -1(a3),a3` special case exists to feed it a whole
  fresh tile. Both are asserted against the shipped image.

**Every one of the six entry pins is the routine's WHOLE BODY and every one matched on the first
run** — 1590 bytes including two 670-byte routines of sixteen-times-unrolled loops. They are built
from the same constants the reconstruction is (the buffer geometry, the masks, the map offsets, the
callees' addresses out of `../names.txt`), and the loops are assembled programmatically so the `dbf`
and `bcc.w` displacements come out of the pieces they jump over rather than being transcribed. A
seventh case asserts each pin's LENGTH against the size `../out/hw_scan.tsv` records, because a
whole-body pin that happened to be a prefix would otherwise pass.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 858 green each time, re-measured
against the tree as it landed rather than against the draft the sweep was first written on):
the mask **inverted at every phase** reddens 3; the coarse row scaled by a **scanline instead of a
tile block** reddens 26; the clear loop **one scanline short** reddens 30; the two halves of the
rotated longword **swapped** reddens 30; the phase-zero redraw **without the map step-back** reddens
3; the second half given the **first half's count** reddens 24; the latch test made **strict**
reddens 3; the left step's row offset left **unmasked** reddens 3; the request byte **left raised**
reddens 3; the rotate turned into a **rotate right** reddens 24; the tile index read as a **byte
table** reddens 30; the split table indexed by the **word instead of the pair** reddens 26; the right
edge given **no x bias** reddens 15; the no-second-half test made an **equality** reddens 6; the map
walked by **one cell instead of a row** reddens 30; and the second cell taken from the **wrong side**
reddens 15. **16 mutations, 16 killed, 0 survivors.**

**One of the sixteen was a coverage finding, and the case that closes it is in the batch.** On the
first sweep the no-second-half test (`(int16_t)second < 0`) made an equality reddened only 4 — the
coarse-row-0 cases, where the count is `-1`. The count is exactly `0` at coarse row **1**, and no
case used it, so the boundary between "one tile row in the second half" and "no second half" was
pinned on one side only. `FILL_CASES` now carries `coarse1`, and the figure above is the 6 it
reddens with that case present.

**The four mutations that redden only 3 are the step and request-handler ones, and that is the
battery's shape rather than a thin pin.** Those routines write six words between them, and the
battery has one case per claim: the latch's three words, the phase carry's three positions, the
borrow's four. A mutation to one of them reddens exactly the cases that address it — the same
reading batch 2's "one case per claim" note records.

**Two things this batch does NOT pin**, both by construction rather than by omission:

* **The registers the fills leave behind.** Both walk out with every address register far past where
  it started; the kit's oracle reports `d0`/`d1`/`a0`/`a1` only, and both call sites `rts`
  immediately, so there is nothing a case could compare against. Same family as the panel blits'.
* **The 65536-iteration `dbf`.** Both fills take their lengths from `bg_scroll_col_split_table`,
  whose first words are 10 down to 0 — a negative first count would run 65536 tile rows and walk out
  of the buffers, and no seeding through `bg_scroll_y_coarse` can produce one, because the table is
  the game's own data and a case that rewrote it would be pinning an invented record. Reproduced by
  construction in `src/scroll.c` (`uint16_t` counters and do/while loops) and honestly unreached.

### Closing the scroll engine (batch 6): the vertical half and the tier above it

Ten routines, 1808 bytes, into the same `src/scroll.c`. With batch 5's six that is the **whole**
`$7522..$8228` cluster plus `$d28`: 3398 bytes, sixteen routines, nothing left named-but-unported and
nothing STOPPED. The cluster's own shape — a request queue drained once a frame, dispatching to
handlers that each consume their byte — is now reconstructed end to end, so a case entered at
`bg_scroll_run_queue` runs the entire engine for one frame under the oracle.

**THE VERTICAL HALF SCROLLS BY MOVING POINTERS, and that is why the pre-shift exists.** There is
nothing to pre-shift vertically: a two-scanline scroll is a change of row within the same buffer. So
the position is a ROW INDEX (`bg_scroll_y`) and the eight buffers' cached row pointers move with it,
the fill copies one map row of tiles into copy 0 **unrotated**, and `bg_scroll_preshift_rows` then
walks that fresh row through the other seven copies, `rol.l #2` at a time. That routine is the other
half of batch 5's eight-copy scheme, and porting it is what makes the horizontal half's "a scroll is
a buffer switch" a closed loop rather than an assertion.

**THERE ARE TWO RING CURSORS, NOT ONE, and batch 5's reading of `$761c` was wrong about them.**
`bg_scroll_y` (`$83a8`) governs the window's top scanline pair and the EVEN half of
`bg_scroll_buffer_rows`; `bg_scroll_y_bottom` (`$83aa`, unnamed until this batch) governs its bottom
pair and the odd half. Each has its own wrap test inside the same step, and `$fb96` starts them 158
rows apart — the visible 160-line window's two ends. Batch 5's `cmt` claimed the two halves reload to
`$49700..` and `$49800..`; they reload to the SAME eight addresses, and the `$49800` figure was the
*down* step's. Both `cmt`s are rewritten, and the case `bottom-cursor-at-its-own-wrap` — one cursor at
its wrap and the other not — is what a port driving both from one row word fails on.

**ONLY PAIR 0 OF `bg_scroll_buffer_rows` IS EVER READ.** An `abs.l` scan gives `$82a6` and `$82aa`
seven references each (four in the steps, one in the matching row fill, one in the pre-shift, one in
the init) and `$82ae..$82e2` only the steps' and the init's. The pre-shift chains from one copy to the
next by adding `$5800` rather than by reading the next pointer, so pairs 1..7 are bookkeeping nothing
consumes. Recorded in `../names.txt` rather than acted on: the steps still write them, and the
reconstruction still writes them, because that is what the original does.

**THE OVERFLOW FLAG IS PART OF A `subi.w`/`bgt` PAIR, and this batch found it the hard way.**
`bg_scroll_raise_requests` decides which side of the screen the followed object is on with
`subi.w #$30,d0 / bgt / blt`. The obvious C — take the wrapped difference, test its sign — is wrong at
one position: `$8000 - $30` is `$7fd0`, which reads *positive* while the 68000's `blt` (which reads
`N xor V`) takes the *negative* arm. The first draft had exactly that bug and the
`wrapped-at-the-lowest-position` case caught it; the fix compares the POSITION against the centre as
signed words, while the distance returned stays the wrapped difference. The same case records the
second thing that breaks there: the routine's "both distances come back positive" property fails, because
`neg.w $7fd0` is `$8030`. Both are reproduced rather than tidied, and the general rule is now in
[`docs/m68k-disassembly.md`](../../../docs/m68k-disassembly.md).

**THE SKIP IS `#8` HERE, AND THE BATTERY HAD TO LEARN THE DIFFERENCE.** A vertical step with nothing
to do does `addq.l #8,(a7)` — two return addresses, because it has a fill AND a pre-shift to consume.
`test/test_scroll.py`'s `STEP_SKIP_BYTES` is now a per-step map rather than the single `4` batch 5's
reviewer flagged, `_oracle_skipped` takes the distance and asserts the oracle landed at
*sentinel + that*, and the run's second stop PC comes from the same map. A step that consumed the
wrong NUMBER of calls fails on the assert rather than reading as a plain skip.

**THE VERTICAL CASES SEED ALL EIGHT BUFFERS.** The pre-shift writes 1792 bytes across seven copies, so
batch 5's "one buffer plus a scanline either side" is not enough margin: a walk that chained by the
wrong stride, or ran one copy too far, would land on zeros. `_scroll_pokes(whole_region=True)` seeds
`$44000..$70000` plus a scanline either side, keyed on the ADDRESS with the same salt as the
horizontal seeding — so a case that uses both (every dispatch and queue case does) gets one consistent
image where the two overlap. The block is `lru_cache`d, because it is 180 KB of Python-level byte
generation that would otherwise be redone per case.

**A SERVE AND EVERYTHING ABOVE IT RUNS WITHOUT THE ATTRIBUTION PASS**, and the reason is structural
rather than a convenience: the vertical step writes the sixteen row POINTERS and the fill under it
then draws THROUGH them, so poisoning the step's outputs in the input image would aim the fill at an
address the run stores to — off the image, in C. The step, the two row fills and the pre-shift are all
run WITH poisoning (none of them stores through a value it also writes); only the four serve routines,
the dispatch pass and the queue turn it off. This is exactly the case `leaf.run`'s `poison=False` was
documented for in batch 5.

**Every one of the ten entry pins is the routine's WHOLE BODY and every one matched on the first run**
— 1808 bytes, including two 400-byte steps of eight-times-unrolled `move.l`/`subi.l` and the
pre-shift's three nested loops. The routines with callees needed something the straight-line ones did
not: a `bsr.w`'s displacement depends on where it is assembled, so `test/test_scroll.py` gained a small
`_Assembler` that tracks the cursor, and each call's target still comes out of `../names.txt`. The
queue's two drain loops close with a `bra.s`, whose byte displacement is asserted to fit rather than
transcribed.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 937 green each time, and the whole
sweep re-run against the tree as it LANDED rather than against the draft it was written on. The
review then added the two vertical-step wrap seeds the function table's `$761c` row describes, taking the
suite to **941**; the per-mutation counts below were NOT re-measured against those four cases, so
read each as a floor): the row
pointers stepped by **rows instead of scanlines** reddens 19; both cursors driven from the **top row
word** reddens 18; the down step wrapping at **zero instead of `$ae`** reddens 4; the coarse row
republished from the **bottom cursor** reddens 18; the top fill **masking the tile row before testing
its sign** reddens 6; the row fill's second half rewinding **one cell instead of one scanline**
reddens 18; a row fill copying **one scanline instead of the pair** reddens 20; its map walking **down
a column instead of across a row** reddens 20; the bottom fill drawing into the **top row pointer**
reddens 10; its map row **nine strides down instead of ten** reddens 10; the pre-shift **rotating
right** reddens 15; **carrying into the next cell** reddens 15; **dropping the row's wrap-around
carry** reddens 15; **chaining by the phase stride** reddens 15; picking its source on the
**longword's sign** reddens 7; a vertical serve **leaving its request raised** reddens 6; the dispatch
pass serving the **horizontal pair first** reddens 1; the raiser testing the **wrapped difference**
reddens 1; the queue draining the **vertical axis first** reddens 2; **not halving** the distances
reddens 2; and clearing the raised pair **as a word** reddens 2. **21 mutations, 21 killed, 0
survivors.**

**The three that redden 1 or 2 are one-case-per-claim, not thin pins.** Only `all-four` can see the
dispatch ORDER, only `wrapped-at-the-lowest-position` reaches the overflow branch, and only the
two-step queue cases can see which axis drains first — the same shape batch 2's note records. Each is
the case written for that claim, and each dies.

**One kit file moved, and it is the registered trigger firing.** `rotate_left32` was duplicated
between `src/hud.c` (constant counts, no zero guard) and `src/scroll.c` (a runtime count, guarded);
batch 5 recorded that a third user would collapse them. The pre-shift's `rol.l #2` is that third user,
so the guarded form now lives in `tools/recreate_kit/include/machine.h` and both files call it. It
masks the count to five bits before the zero guard, which is the 68000's register form exactly
(`rol.l Dm,Dn` rotates by `Dm mod 64`, and a 32-bit rotate is cyclic mod 32, so mod 64 and mod 32
give the same value) — total for every count instead of undefined above 31 — and costs a
constant-count caller nothing after inlining. Being a kit file, it lands as its own commit ahead of
this batch.

**What is NOT pinned, both by construction:**

* **The registers the routines leave behind**, except the two row fills' `d0` — which IS an output,
  read by `bg_scroll_preshift_rows`, and compared on both sides in every case.
* **The runaway counts, which are TWO different unreachability arguments.** Every `dbf` here takes its
  length from a split table whose first words count down to 0, so a negative one runs `count + 1`
  passes — 32,769 to 65,536 — rather than none; that is out of reach of the game's own data, because
  the tables are the shipped image's and a case that rewrote one would be pinning an invented record.
  `bg_scroll_run_queue`'s two drains are a `while` rather than a `dbf`, so a negative count runs its
  own VALUE in passes, 32,768 to 65,535 — and their count is a halved distance, not a table entry.
  `$d28` can return one: the `wrapped-at-the-lowest-position` case in this very battery makes it
  return $8030, which halves to $c018, i.e. 49,176 passes. What keeps the drains unreached is
  therefore the range of the game's own follow positions, which this batch did not establish — NOT
  the range of what `$d28` can return. Both shapes are reproduced by construction (`uint16_t`
  counters, do/while and `while` loops) and left unreached.

**Deferred, deliberately: `subsystems.tsv` still calls this cluster "game logic".** Its
`video (background scroll)` range is `$82f8..$8dfe` — the blit that CONSUMES these buffers — while
`$7522..$8228` and `$d28` fall into the catch-all. Both are now known to be the same subsystem, but
re-drawing the boundary moves every figure in [`PORTABILITY.md`](PORTABILITY.md), which is a
measurement to re-run rather than a line to edit. Left as it is, and recorded here.
**CLOSED 2026-08-02 by the re-measure at the end of this file** — both ranges are
`video (background scroll)` now.

### The consumer tier (batch 7): the blit, and sixteen routines that are one routine

Seventeen routines, 2,742 bytes, into the same `src/scroll.c`. With batches 5 and 6 that is the
**whole** background-scroll story — `$7522..$8228` and `$d28` produce the eight pre-shifted buffers,
`$82f8..$8dfe` consumes one of them — 33 routines and 6,140 bytes, with nothing between `$7522` and
`$8dfe` left named-but-unported and nothing STOPPED.

**THE SIXTEEN VARIANTS ARE ONE ROUTINE WITH ONE NUMBER IN IT, AND THAT IS THE BATCH'S FINDING.**
`$83b6..$8dfe` is sixteen unrolled copy routines a jump table names. They are byte-identical apart
from where each splits its thirty `move.l (a0)+,(a1)+` about the source row's 128-byte ring seam,
which is exactly what `bg_scroll_x` says: column 0 and 1 need no split at all (30 longwords from
`8 * x` still fit the 32 a row holds), and every other column copies `32 - 2x` longwords, rewinds a
whole row with `lea -128(a0),a0`, and copies the remaining `2x - 2`. That is why two bodies are 154
bytes and fourteen are 166 — the twelve being the two extra `lea`s each of a variant's two halves
costs. So `src/scroll.c` reconstructs all sixteen as ONE function taking the column as an argument,
and the table collapses into that argument.

**THE REGULARITY IS TESTED, NOT ASSUMED, AND IN THREE INDEPENDENT WAYS.** A parametrised pattern
that was wrong in the same way sixteen times would pass sixteen pins built from it, so:

* every variant's WHOLE body is assembled from the pattern and pinned against the image, and its
  length against the size `../out/hw_scan.tsv` records (154, 154, then fourteen 166s);
* **three of them are pinned a second time against bytes transcribed straight out of
  `../out/wonderboy_dis.txt`** — `x0` (no seam), `x2` (the first that needs one) and `x15` (whose
  seam is at the other end). These are what fix the pattern itself — and they are TRANSCRIBED rather
  than computed for a concrete reason: a hand-computed `dbf` displacement for `x2` and `x15` came out
  two short, and reading the bytes off the image is what settled it;
* the sixteen table entries, the sixteen lengths and the gaps between them are asserted to tile
  `$83b6..$8dfe` exactly, and a whole-image `abs.l` scan requires each variant address to occur
  **exactly once** — in its own table entry — and the table itself exactly once, inside
  `bg_scroll_blit`'s body. So the table is the only way in and `$832e`'s `lea` its only reader.

**`bpl` READS N ALONE, AND THAT IS THE OTHER HALF OF BATCH 6'S FINDING.** The dispatcher decides
whether the window runs off the buffer's end with `subi.w #$10,d6 / bpl`, which looks like the
`subi.w`/`bgt` pair batch 6 got wrong. It is not the same: `bgt`/`blt` read `N xor V` and `bpl`/`bmi`
read `N`, so here the wrapped difference's own sign really *is* the test, and the reconstruction says
so. The two readings — the wrapped sign, and a comparison of the row against the boundary — agree on
every ring row the game can produce and part company from `$8010` up. Most of that range is
unrunnable, because the same word feeds `move.w #$b0,d7 / sub.w`: a row of `$8010` asks for 32,928
scanlines and walks off the image. **A row of `$fffe` does not**, and the case that seeds it copies
160 scanlines where the boundary reading would copy 178 — which is what turned the sweep's one
survivor into a kill.

**THE DIFFERENTIAL ENTERS BOTH WAYS, because either alone leaves half the mechanism unpinned.** A
case entered at `$82f8` runs the dispatcher AND the variant its `jmp (a2)` reaches, so the table is
exercised as the game exercises it; a case entered at a VARIANT supplies the four registers the
dispatcher would have (a0 = source, a1 = destination, d7 and d6 the two `dbf` counts) and pins that
body on its own, four scanlines to the buffer's end plus two past the rewind. Both kinds seed all
eight source buffers AND both screen buffers, address-keyed with the same salt, so a copy that ran
one scanline long, chained by the wrong stride or read the wrong buffer lands on bytes that are
wrong *for where they were written* rather than on zeros.

**ONE CORRECTION TO `../names.txt`, from re-reading the dispatcher.** Its `cmt` (and the block
comment above it) said the blit "enters [the variant] twice, once per side of the source buffer's
vertical wrap, through the `jmp (a2)` at `$8350`/`$8364`". It does not. Those two jumps are the two
ARMS of the `bpl` — one loading `d6 = $ffff` outright (the window fits: no second half) and the other
computing both counts from the ring row — and exactly one of them executes per call. The vertical
split happens INSIDE the variant, at its own `tst.w d6 / bpl / rts`. Both texts are rewritten.

**Every one of the seventeen entry pins is the routine's WHOLE BODY.** The dispatcher's 110 bytes end
at `jmp (a2)`, which is its only exit and the reason it has no `rts`; the table begins in the very
next word, which the pin asserts. The three shifts in it are spelt as the constants they scale BY
rather than as the counts in the opcodes (`_shift_for`), so a header constant that moved fails the
pin instead of quietly disagreeing with it.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 1023 green each time, and the whole
sweep re-run against the tree as it LANDED rather than against the draft it was written on; the
batch's review then added the 1024th case, a static image scan that runs no reconstructed code and
so moves no figure here): the
scanline **never split at the seam** reddens 25; the seam rewind **one cell instead of one row**
reddens 25; a wrapping scanline **not re-advanced past the row it rewound** reddens 25; the
destination stepped **a whole screen line instead of the gap** reddens 32; the seam placed **one cell
per column instead of one longword pair** reddens 25; a half running **its count instead of its count
plus one** reddens 32; the second half rewound **one row instead of one buffer** reddens 23; the
no-second-half marker read as **a zero test** reddens 9; the ring row scaled by **a cell instead of a
scanline** reddens 10; the phase scaled by **a whole buffer instead of half of one** reddens 10; the
two halves' counts **swapped** reddens 8; the first half **one scanline long** reddens 8; the window's
origin within the screen **dropped** reddens 12; the variant picked by **the phase instead of the
column** reddens 10; and the wrap test made **an unsigned comparison of the row against the boundary**
reddens 1. **15 mutations, 15 killed, 0 survivors.**

**That last one reddens 1 because it is one-case-per-claim, and it is the batch's coverage finding.**
On the first sweep it was the only SURVIVOR: nothing in the battery could tell the wrapped-sign
reading from the boundary one, because the two agree on every row the game produces. The `$fffe`
case above is what closes it, and it is recorded this way round because that is how the case came to
exist — the sweep found the hole and the case was written for it, rather than the other way about.

**What is NOT pinned, and why:**

* **A COLUMN OUTSIDE 0..15.** `movea.l (0,a2,d1.w),a2` bounds nothing, so the original would jump
  through the longword after the table — which is `bg_scroll_x` itself. C has no such behaviour to
  reproduce and `bg_scroll_copy_column` is undefined there. The domain is established instead rather
  than asserted, and by a case rather than by prose: a whole-image `abs.l` scan
  (`test_the_column_is_a_nibble_wherever_the_image_writes_it`) gives `bg_scroll_x` exactly three
  writing sites — a `subq.w #1` and an `addq.w #1`, each immediately followed by its OWN
  `andi.w #$f`, and the `clr.w` at `$fb7e`.
* **THE REGISTERS THE COPY LEAVES BEHIND.** It walks out with a0/a1 far past where they started and
  its one call site `rts`s immediately, so there is nothing to compare against — the same family as
  the column fills'.
* **THE 65536-ITERATION `dbf`.** Each half's count is a `dbf`, so a negative one would run 65,536
  scanlines. Reproduced by construction (`uint16_t`, do/while) and out of reach through
  `bg_scroll_blit`, whose two counts provably sum to the window's 160 scanlines for every ring row
  the vertical steps can produce — asserted over all 88 of them.

**`$8dfe` IS QUEUED, NOT SKIPPED.** `game_main_loop` calls it immediately before `bg_scroll_run_queue`
and it is 104 bytes with the same "read a position, subtract the scroll" shape as `$8e66` just after
it — but it opens `jsr $67e0.w`, a callee this reconstruction does not have, so its closure is not
satisfied and it is not in this batch. It is a `$67e0` batch, not a scroll one. **CLOSED by batch 8**,
which ported `$67e0`, `$8dfe` and `$8e66` together — and the reading was right about more than it
knew: `$8dfe` writes `scroll_follow_x`, i.e. the very word this batch's `bg_scroll_raise_requests`
steers on, because that word is screen record 12 of `$8e66`'s array.

**Still deferred, and now more visibly: `subsystems.tsv` calls the ENGINE "game logic".** Its
`video (background scroll)` range is `$82f8..$8dfe` — exactly this batch — while `$7522..$8228` and
`$d28` fall into the catch-all. Both are now reconstructed, so the boundary is measurably wrong in a
way that flatters neither side; re-drawing it moves every figure in [`PORTABILITY.md`](PORTABILITY.md),
which is a measurement to re-run rather than a line to edit. Left as it is, and recorded here.
**QUEUED, alongside the `$67e0` batch above: re-draw `subsystems.tsv`'s game-logic/video boundary and
re-run `tools/hw_portability.py` over it, then restate `PORTABILITY.md` from what it prints** —
trigger: now that `$7522..$8dfe` is closed, the game-logic/video split is measurably wrong.
**CLOSED 2026-08-02** — the re-measure is the last section of this file; background scroll went
17 functions / 2,742 B to **33 / 6,140 B**, and game logic 138 / 14,028 B to **114 / 9,596 B**.

### The actor tier and the text plotter (batch 8): the queued small tiers, cleared

Seven routines, 582 bytes, in two new files. `src/actor.c` takes the five-routine cluster batch 7
queued as "a `$67e0` batch, not a scroll one"; `src/text.c` takes the two-entry-point plotter batch
2 registered as "named and NOT ported, because porting it means porting `$bf5e` with it". Both
queue entries are closed.

**WHAT `$67e0` TURNED OUT TO BE, AND IT IS THE BATCH'S FINDING.** The scan calls it a 24-byte leaf
with fifteen callers and nothing else. Reading it, and then the four routines above it, gives a
whole subsystem: the game keeps its moving objects as **nineteen 32-byte records in one of three
parallel tables** (`$996c` / `$9bd0` / `$9e34`) that two mode flags pick between, and once a frame
it projects the chosen table into a parallel array of **nineteen SIX-byte screen records** at
`$98ec` — map position minus the scroll, plus the sprite to draw. `$67e0` returns **slot 12** of
that table (`$9aec` == `$996c + 12 * 32`, `$9fb4` == `$9e34 + 12 * 32`), and slot 12 of the screen
array **is `$9934`** — `scroll_follow_x`, which `bg_scroll_raise_requests` already steers the camera
by. So "the followed object", which batch 5 could only read off the scroll's own arithmetic, is
slot 12 of the actor table, and `$8dfe` exists to refresh exactly that one record in
`game_main_loop` immediately BEFORE `bg_scroll_run_queue` reads it. The arithmetic is a case
(`test_the_scrolls_follow_words_are_screen_record_twelve`), not a remark.

**THE SAME FLAG IS READ TWO DIFFERENT WAYS AND BOTH READINGS ARE KEPT.** `$67e0` tests
`state_flag_a32` with `bne`; `$8e66` tests the same word with `bpl`. `../names.txt` records that
the image only ever writes it `$0000` or `$ffff`, so **the game cannot tell the two apart** — a
small positive word is the only input that does, and there is one per routine
(`SELECTOR_CASES`' `one` / `largest-positive`, `FOLLOWED_CASES`' `a32-small-positive`,
`LIST_CASES`' `a32-small-positive`). Without them the mutation "read the sign instead of nonzero"
survives; with them it reddens 3.

**`$8dfe`'s GATE IS WHAT KEEPS THE TIER CONSISTENT.** `$67e0` has no `$a30` form: in that mode
`$8e66` projects `$9bd0`, whose slot 12 is an address `$67e0` never returns. `$8dfe`'s
`tst.w $a30.w / bpl / rts` is what stops it refreshing slot 12 from the wrong table — and `bpl`
reads N alone, so a positive `$a30` runs the body where a `bne` would return. That is the batch's
one-case-per-claim mutation: reading the gate as a zero test reddens exactly 1.

**THE TWO PROJECTION PASSES ARE ONE BLOCK.** `$8dfe`'s `$8e20..$8e64` and `$8e66`'s
`$8eb4..$8ef8` are the same SIXTY-EIGHT BYTES, so `src/actor.c` reconstructs them as one
`project_actor` helper and the two entry pins are built from one `_projection_block()`. That the
two really are byte-identical is a case of its own
(`test_the_projection_is_one_block_the_two_passes_share`), for batch 7's reason: a pattern that was
wrong in the same way twice would pass two pins built from it.

**THE TEXT TIER TURNED OUT TO BE ONE ROUTINE WITH TWO ENTRY POINTS, AND `$bd8a` EXPLAINS THE 88.**
`$bf4e` has no `rts`: four instructions turn a character code into a glyph pointer and it FALLS
THROUGH into `$bf5e`, whose `rts` returns to `$bf4e`'s caller. So the C is a prelude that CALLS the
plotter and returns its result — exactly what the fall-through is — and `$bf5e` keeps a name of its
own because eight `bsr` sites enter it directly with a pointer they already hold. `../names.txt`
recorded the plotter's 88-byte row advance as "NOT a 160-byte scanline — unexplained, do not assume
a screen buffer". It is now explained: the destination is the off-screen message buffer at `$c03a`,
**88 bytes wide and 6400 long, ending exactly at `panel_restore_dirty_regions` (`$d93a`)**, which
`$bd8a` clears, composes into, and then blits to `screen_back` 88 bytes plus a 72-byte skip per
scanline — 88 + 72 being the screen's own 160. Both halves are cases
(`test_the_row_advance_is_the_buffers_line_and_not_the_screens`), and the `cmt` on `$bf5e` is
rewritten. The returned cursor's `+1` / `+7` alternation is the other half of the same geometry:
two 8-pixel cells share each 8-byte plane group.

**THE EIGHT `$be2a..$be9a` CALLERS ARE NOT A TIER — THEY ARE ONE FUNCTION.** The batch was scoped
to consider them next; a whole-image scan says all eight `bsr` sites, and the ninth into `$bf4e`,
lie INSIDE `$bd8a`, a single 452-byte routine. It is named
(`text_compose_message_box`, from a read of its body) and **QUEUED, not skipped** — see below.

**ONE NAME CORRECTED.** `$bf4e` was `text_glyph_source_from_d0`, which describes the prelude alone;
now that the prelude and the plotter are reconstructed as what the fall-through makes them, it is
`text_plot_char`. Its `cmt` is rewritten and the "NOT reconstructed" caveat replaced by the three
semantics the port keeps: the `subi` is a BYTE op, the `lsl` a LONGWORD one, and the index is the
low WORD SIGN-EXTENDED. Only the last is unreachable from the game, whose one caller enters with
`moveq #0,d0 / move.b (a6)+,d0`; a case reaches it with a `d0` that indexes below the font and
stays inside the image.

**FOUR `proto` LINES WERE NOT WRITTEN, DELIBERATELY.** `ApplyNames`' `proto` forces a VOID return,
so a directive on `followed_actor_record` (whose whole result is a1), `actor_followed_x_within`
(d0 in and out), `text_plot_glyph` or `text_plot_char` (a1 in and out) would record something
false — `hud_blit_meter_cell`'s reason, one tier on. Each carries its register map in its `cmt`
instead. `actor_set_side_flag` is the one routine here that really returns nothing, and it has one.

**Two kit/test hoists this batch's third users triggered**, both of them registered above rather
than invented here:

* **`set_low_word` is now `tools/recreate_kit/include/machine.h`'s**, beside `set_low_byte`.
  `actor_followed_x_within` returns d0 with only its low word written, which was the registered
  third user (`src/scroll.c` and joust's `recreate/src/object.c` were the first two); both now call
  the kit's. Being a kit file touching three projects it lands as its own commit ahead of the
  batch, exactly as `rotate_left32` did — **BuggyBoy (292) and Joust (4368) were re-run green
  against it**.
* **Seven helpers are now `test/leaf.py`'s.** Two new batteries needing the same pieces made each
  of them a third user, and all three batteries import them rather than restating them:
  `opcode()` and `lea_abs_l()` (the encoders every pin spells), `lea_d16()` (likewise — the only
  other encoder all three batteries needed), `keyed_byte()` and `case_salt()` (address-keyed
  seeding and its reproducible per-case salt, with the two mixing multipliers named where they
  live), and `program_writes()` and `merge_bands()` (the oracle's write set minus the machine
  stack, and the bands `leaf.run` wants). `test_scroll.py`'s local copies are deleted and it
  imports them (its `branch_w(opcode, …)` parameter, which shadowed the new name, is now
  `condition`); the shared `merge_bands()` sorts internally, so the `sorted()` its callers used to
  wrap the argument in is gone.
  **What deliberately stays local, and why:** every battery's own OPCODES (`tst_w_abs_w`,
  `lea_indexed`, `subi_b_dn`, …), for batch 7's stated reason — that is where the batteries differ,
  and a shared 68000 assembler is not what this is. And `_keyed_block()`, the one-line
  `bytes(keyed_byte(…))` wrapper, which `test_scroll.py` and `test_actor.py` each still spell:
  **registered** on the same terms as the two hoists above — **trigger** = a third user; **home** =
  `test/leaf.py`, beside `keyed_byte()`. The two copies carry different docstrings (the scroll one
  records a measured no-caching decision), which is the only reason it was not folded in here.

Mutation-checked rather than assumed (each rebuilt with the `.so` DELETED first, since a
same-second rebuild otherwise re-runs the stale library, and each source restored and byte-compared
against a pristine copy afterwards, and the whole sweep re-run against the tree as it
LANDED rather than against the draft it was written on — 1193 green each time it was restored): the selector reading the
flag's **sign instead of nonzero** reddens 3; the side flag raised on **equal** as well reddens 4;
the side flag moved to **bit 4** reddens 37; the reach test's ADD **not wrapping to 16 bits**
reddens 4; the reach test returning **a whole longword instead of a low word** reddens 13; the
projection using the **Y bias horizontally** reddens 27; the flicker arm needing **either condition
instead of both** reddens 18; the followed projection's gate read as **a zero test** reddens 1; the
list pass testing **a32 before a30** reddens 2; the list pass stepping the screen cursor by **an
actor record** reddens 16; the plotter stepping **a SCREEN scanline** between rows reddens 45; the
plotter's four plane bytes made **contiguous** reddens 45; the two cell advances **swapped** reddens
45; the character subtraction made **a longword one** reddens 2; and the glyph index **not
sign-extended** reddens 2. **16 mutations, 15 killed, 1 survivor.**

**The survivor is an EQUIVALENCE, and it is now stated as one.** `$bf5e` reads the parity of the
cursor its eight rows ENDED on; reading the STARTING cursor's instead survives, because the body
spans 622 bytes and 622 is even. `src/text.c` keeps the original's reading and
`test_the_parity_the_tail_reads_is_the_starting_cursors_own` asserts the evenness that makes the two
the same bit — so the day a geometry constant turns the span odd, the equivalence fails loudly
instead of the port quietly diverging.

**What this batch does NOT pin:**

* **THE REGISTERS THE TWO PROJECTIONS LEAVE BEHIND.** Both walk out with a0 one record past the
  last one they read and a1 at the end of what they wrote; `game_main_loop` reloads everything
  before its next `jsr`, so the C returns neither and the cases assert the ORACLE's against the
  model. The same family as the column fills'.
* **d7, WHICH THE PLOTTER CLOBBERS.** It parks the ended cursor there for the `btst`. The kit's
  oracle reports d0/d1/a0/a1 only, so no case can compare it; no caller reads it either.
* **A GLYPH POINTER OUTSIDE THE IMAGE.** `text_plot_char`'s sign-extended index can name a source
  far below the font. The case that reaches that arithmetic keeps the source inside the image;
  off-image is `src/rad.c`'s registered divergence class (the shim answers zeros, the C indexes a
  host buffer) and bounding it would be a kit change.
* **WHAT THE TWO MODE FLAGS SELECT.** `../names.txt` names each for its mechanism and nothing more:
  `$a30` has ten operand sites — five writers of `$0000`/`$ffff` (three `move.w #$ffff` at `$1ae6`,
  `$1e96`, `$e0d0` and two `clr.w`) against five bare `tst.w` readers (`$4ec`, `$8dfe`, `$8e66`,
  `$dbc0`, `$ff42`) — and `$a32` has sixteen: three writers against thirteen bare `tst.w` readers.
  That one of the three actor tables is "this level's actors" is not established.

**QUEUED, and it is the tier directly above this one: `$bd8a` (`text_compose_message_box`, 452
bytes).** Its closure is satisfied now — both plotter entry points are reconstructed and it calls
nothing else — but it is not small, and it reads the TEN bytes at `$c030..$c039`: four BYTE fields
(`$c030`/`$c031`, the two flags it runs on, and `$c032`/`$c033`, its two cell counts) and three
WORDS (`$c034`/`$c036`/`$c038`, its timers). That band is `WB_TEXT_STATE_BYTES`, which this batch
pins only by its EXTENT — what the fields mean, and the message-pointer table at `$a09c` that
`$bd8a` indexes, are not read. Its one caller is `game_main_loop`'s `jsr $bd8a.l` at `$4fc`.
**CLOSED by batch 9**, which ported it, read all seven state fields and the `$a09c` table — and
renamed it, because "compose" is one of its three arms.

### The message box (batch 9): the text subsystem, CLOSED end to end

One routine, 452 bytes, into the file batch 8 opened. It is the queue entry above, and closing it
closes the whole `$bd8a..$c030` block: **every routine in the text subsystem is now reconstructed,
its one caller is `game_main_loop`, and it calls nothing outside itself.**

**WHAT THE "COMPOSER" TURNED OUT TO BE, AND IT IS THE BATCH'S FINDING: A LIFECYCLE, NOT A DRAW.**
`$bd8a` runs once a frame and has THREE arms, picked by the two flag bytes:

1. **`text_request` nonzero** — a message id was posted since the last frame. `$ff` dismisses (clear
   both flags, draw nothing); otherwise the 1-based id indexes `text_message_table`, whose record
   gives the box's height and top scanline and then the string. The box is composed into
   `text_buffer` and **deliberately NOT blitted** — the arm `rts`s at `$bed0`, so the frame a
   message is requested on shows nothing.
2. **`text_request` zero and `text_box_active` nonzero** — tick the countdown and blit the
   **already-composed** buffer to `screen_back`. This is the arm that runs on every frame of a
   message's life but the first.
3. **both zero** — `rts` having written not one byte (a case of its own).

So `text_buffer` is a **CACHE, not a scratchpad**, and `$c032`/`$c033` exist to carry the composed
box's geometry from the one compose frame to every blit frame after it. That is also why the 6400
bytes are cleared and redrawn only on a request: composing costs ~16,000 instructions, blitting
~1,800. `../names.txt` renames the routine `text_run_message_box` for it — the same correction batch
8 made to `text_glyph_source_from_d0`, and for the same reason: the old name described one arm.

**THE TABLE AT `$a09c` IS SELF-BOUNDING, AND NOTHING ELSE COULD HAVE BOUNDED IT.** A whole-image
scan finds **exactly one** reference to `$a09c` — the routine's own `lea` — so no count is declared
anywhere. The shipped data gives it three ways over, and all three are cases
(`test_the_message_table_is_bounded_by_its_own_data`): pointer 0 names `$a270`, the first byte PAST
the 117-pointer block; every record ends exactly where the next begins; and the last ends at
`$b346`, which is `panel_refresh_frame`. A count one too small would leave a gap before that
routine, one too large would read a "pointer" out of a record's text. A record is
`{byte height in cell rows, byte top scanline, string}`, `$0a` newline and `$ff` terminator — the
same shape as batch 5's split tables, established from the reader's own walk.

**`$c036` IS A ONE-WAY LATCH, AND THE SCAN IS WHAT SAYS SO.** `text_lifetime_armed` has **exactly
two** operand sites in the whole image, both inside `$bd8a`: the `move.w #$ffff` that sets it and
the `tst.w` that reads it. Nothing ever clears it. So after the first message that posted a
lifetime, every later box decrements `text_lifetime_left` each frame whether or not it asked for
one — and since only an EXACT zero takes the box down, a box composed with no lifetime under an
armed latch counts down from whatever the previous message left and usually wraps past zero rather
than landing on it. Both of those phases are seeded cases (`no-lifetime-already-armed`,
`armed-and-wrapping-past-zero`), and both are **live gameplay states, not dead branches** — the
paragraph above is the argument that the game reaches them. What no shipped **record** encodes is a
lifetime: it is posted by a caller alongside `text_request`, so the phases arise from the state
history rather than from any record's data. That is exactly why seeding them is legitimate — the
cases poke the ten bytes of plain RAM the arm reads, which is a reading of the instructions, and no
record is fabricated.
`$c032`, `$c033` and `$c038` have no site outside `$bd8a` either.

**THE FRAME IS 22 CELLS WIDE, ALWAYS, AND THAT IS WHAT EXPLAINS THE BUFFER'S 88.** A corner, twenty
`move.w #$13,d0 / dbf` edges and a corner is `WB_TEXT_BOX_CELLS` = the whole `WB_TEXT_BUFFER_LINE`;
the blit moves exactly `WB_TEXT_BLIT_LONGWORDS` = the same 88 bytes. Only the HEIGHT varies, from
`$c032`. Every one of the composer's step constants is that same geometry from another side — 616 is
a cell row less a buffer line, 80 is the interior in cells, 704 is eight buffer lines — so
`test_the_boxs_geometry_constants_are_one_set_of_numbers` asserts each against the others rather
than transcribing them.

**THE SHIPPED DATA OVERRUNS THE FRAME, AND THE CODE LETS IT.** Nothing clamps a text line to the
twenty interior cells. Over all 117 records, heights run 3..9, top scanlines are only 50 or 60, and
line counts never exceed height minus 2 — but **message 113 has a 21-character line** that plots
over the frame's right edge. It is a case
(`test_exactly_one_shipped_message_overruns_the_frames_right_edge`) and a compose case, and it also
bounds the missing clamp: the overrun is exactly one cell, so every plot still lands inside the
buffer's own row.

**THE RUNAWAY THE SHIPPED TABLE CANNOT CAUSE.** `move.b $c032,d0 / subq.w #3,d0 / dbf` counts the
interior rows in a WORD, so a height below 3 would draw 65,536 rows and walk far past the buffer.
Reproduced by construction (`uint16_t`, do/while) and asserted unreachable over all 117 records —
the same family as the scroll's `dbf` counts.

Mutation-checked rather than assumed (each rebuilt with the `.so` DELETED first, and the source
restored and byte-compared against a pristine copy afterwards — 1242 green each time it was
restored): the two arms **swapped**, so an active box beats a new request, reddens 2; the **dismiss
arm dropped**, so `$ff` is an ordinary id, reddens 2; the countdown expiring on **`<= 0`** instead
of an exact zero reddens 2; the countdown **armed unconditionally** reddens 13; the expiring frame
**not drawn** reddens 2; **one interior row too many** reddens 25; the interior skip made a **whole
row advance** reddens 25; the text lines started at the buffer's **cell 0** reddens 25; the blit's
top line **not sign-extended** reddens 1; the blit's rows made **contiguous** reddens 10; and the
frame's bottom row drawn with the **top row's glyph triple** reddens 25. **13 mutations, 11 killed,
2 survivors.**

**Both survivors are EQUIVALENCES, and both are now stated as ones.**

* **The blit arm's `clr.b $c030`.** It opens an arm reached only when `text_request` is ALREADY
  zero, so the write changes no byte and dropping it from the reconstruction survives. The C keeps
  it, because it is a write the ORIGINAL makes and the cases state the oracle's write set exactly —
  the oracle making it is pinned even though the candidate omitting it cannot be.
  `test_the_blit_arms_request_clear_is_a_write_of_a_byte_already_zero` says so.
* **The order of the newline and terminator tests.** `$0a` and `$ff` are distinct, so no byte can
  take both branches and swapping the two `cmp.b`s is an equivalence for every input.
  `test_the_newline_and_the_terminator_cannot_be_the_same_byte` asserts the distinctness that makes
  it one, so the day the two constants meet it fails loudly.

**ONE MUTATION WAS A REAL HOLE AND IS NOW PINNED.** "The blit's top line is not sign-extended"
survived the first sweep: `mulu.w #$a0,d0` is a 32-bit product but `lea 48(a1,d0.w),a1` takes its
LOW WORD, sign-extended, and the shipped records only ask for 50 or 60 — neither reaches it.
`$c033` is not re-read from the record on that arm, though: it is plain RAM the blit reads, so a
case seeds it at 205 (the smallest top line that overflows the word) and the box lands BELOW
`screen_back` instead of far past it. That is the same move batch 8 made with the small-positive
mode flags, and it turns the survivor into 1 red.

**TWO COLLAPSES THIS BATCH'S THIRD USERS TRIGGERED, one per language.**

* **Thirteen more helpers are now `test/leaf.py`'s**, and `test_scroll.py` / `test_actor.py` /
  `test_text.py` import them instead of restating them. The encoders `tst.b`/`tst.w`/`clr.b`/`clr.w`/
  `st`/`subq.w` on an `<abs>.l`, `mulu.w #imm,Dn`, `movea.l <abs>.w,An`, `move.w #imm,Dn` and
  `moveq #0,Dn` — every one of them spelt in two files, and `move.w #imm,Dn` in three. The two
  branch assemblers went with them: `branch(condition, *over)` / `branch_over(condition, span)` and
  `dbf(reg, *body)` / `dbf_over(reg, body_bytes)`, which is where the drift actually was —
  `test_scroll.py` and `test_text.py` each had a `dbf` of its own with a DIFFERENT signature (one
  taking the pieces, the other their length), and the same forward branch was `branch_w` in one file
  and `_branch` in two others. Each shape now has one name, the pieces form and the length form named
  apart, so a call site says which it is. **The registered `_keyed_block` entry is CLOSED** —
  `test_text.py` was the third user batch 8 said would trigger it, and `keyed_block()` now lives once
  in `leaf.py` beside `keyed_byte()`, carrying the scroll copy's measured no-caching note. `moveq`
  kept the systematic `moveq_0_dn` spelling over `test_text.py`'s `moveq_zero`, matching
  `move_w_imm_dn` / `clr_w_dn` / `tst_w_dn`. The whole-body entry pins are the proof the hoist
  changed nothing: every routine in all three batteries still matches the shipped image byte for
  byte.
* **`copy_longwords` is shared between `src/scroll.c` and `src/text.c`**, declared in
  `include/scroll.h` and defined where it already was. The message box's blit row is the same run of
  `move.l (a0)+,(a1)+` the sixteen scroll copy variants spend their length on, down to the in/out
  cursors, so `text.c`'s inner loop and its `TEXT_LONGWORD_BYTES` are gone. It stays project-local
  rather than moving to the kit's `machine.h` because both users are this game: **registered** on the
  usual terms — **trigger** = a third user, in this project or another; **home** =
  `tools/recreate_kit/include/machine.h`, beside `addr_add` and `rotate_left32`.

**What this batch does NOT pin:**

* **WHAT `$bd8a` LEAVES IN d0/d1/a0/a1/d6/a6.** Each arm walks out with different rubbish — the
  terminator byte and the last glyph's source, or the blit's two ended cursors — and
  `game_main_loop` reloads everything before its next `jsr`. The C returns nothing; the cases assert
  the ORACLE's against the model where the arm defines them. The same family as the projections'.
* **THE ATTRIBUTION (POISON) PASS, ON THIS ROUTINE.** Every non-trivial arm WRITES `text_request`,
  so poisoning the oracle's outputs turns a zero request into `$ff` and both cores then take the
  DISMISS arm — the pass would agree, having tested the wrong arm. The driver's cases run with
  `poison=False` and replace it with an address-keyed destination, an EXACT write set and a model
  built from the game's own data. Registered here because it is a deviation from every other
  battery in this project.
* **AN ID PAST `WB_TEXT_MESSAGE_COUNT`.** `subi.b #$1,d0 / lsl.w #2,d0` indexes with a word, so ids
  118..256 read a "pointer" out of the record bytes and walk wherever it names. Fifty-two writers
  raise `$c030` and only their immediates are bounded (they top out at `$64`); the rest are
  `move.b d0` / `move.b (a0)` and nothing read here bounds them. Reaching it from a case means
  fabricating a pointer into a table the game ships, which is what CLAUDE.md's coverage rule
  refuses. Left honestly unpinned.
* **WHAT ANY GIVEN MESSAGE ID MEANS.** The 117 records are read as geometry and text; which game
  event raises which id is a property of the 52 writers, none of which this batch read.

### The portability re-measure (2026-08-02): the boundary the campaign proved wrong

The queue entries batches 6 and 7 left open, closed together. No code changed and no test moved —
`make test` is 1242 green before and after — because this is a **measurement**, not a
reconstruction: `subsystems.tsv` was re-drawn and `tools/hw_portability.py` re-run over the same
`../out/hw_scan.tsv`. [`PORTABILITY.md`](PORTABILITY.md) §0 records it in full.

**What moved.** Five ranges left the "game logic" catch-all, each on evidence a batch established
and each cited in `subsystems.tsv` itself: `$7522..$8228` and `$d28..$d76` (the scroll ENGINE, to
join its consumer under `video (background scroll)`), `$67c2..$6822` and `$8dfe..$8f02` (a new
`actor (table + projection)`), and `$bd8a..$c030` (a new `text (message box)`). The exact `hi` of
each is the `body_end` the scan records for its last function, so the ranges tile and no entry is
claimed twice. The `$a09c` message table is deliberately NOT in the file: ranges match a function
ENTRY, and that is data.

| | before | after |
|---|---|---|
| game logic | 138 fns / 14,028 B measured, 36.0 % of 38,942 B CODE | **114 / 9,596 B, 27.8 % of 34,496 B** |
| video (background scroll) | 17 / 2,742 B, 97.2 % | **33 / 6,140 B, 98.5 %** |
| text (message box) | — | **3 / 678 B, 100.0 %** |
| actor (table + projection) | — | **5 / 356 B, 100.0 %** |
| game logic, runnable end-to-end | 128 / 12,070 B | **104 / 7,638 B** |
| game logic, ported and green | 51 fns | **61 / 2,986 B** |

**Every whole-program figure is unchanged** — 220/252 functions and 21,534/25,696 bytes runnable,
83.8 % of what is measured and 39.3 % of believed code, 28 functions / 3,348 B at false-green risk,
and both tier tables byte-identical. A subsystem partition relabels the same 252 functions; the two
reports differ in exactly four rows, which was checked by diffing them rather than argued.

**THE CATCH-ALL GOT WORSE, AND THAT IS THE FINDING.** Carving three characterised subsystems out of
"game logic" was expected to leave a smaller, better-understood remainder. It did the opposite: the
bucket lost 4,432 **measured** bytes and only 14 unmeasured ones, so its coverage fell from 36.0 %
to 27.8 % and the CODE it holds outside every function body is now 72.2 % of it. What the catch-all
was hiding was not confusion — it was the three best-measured subsystems in it.

**THE REPORT CAN NOW SAY "GREEN", NOT ONLY "RUNNABLE".** The campaign created a fact the original
measurement had no column for: **105 functions / 10,376 bytes are reconstructed and pinned by a
differential** — 40.4 % of what is measured, 18.9 % of believed code, and 48.2 % of everything the
harness can run at all. `PORTABILITY.md`'s coverage table carries it as a column now. It reads 105
where this file's header reads 103, and the difference is a counting rule, not a disagreement:
`src/rad.c` is one reconstruction of what Ghidra splits into three functions.

**The limitation to state with it: the Ghidra DB is stale.** Batches 5–9's names, `cmt`s and
`proto`s have not been through `../reapply.sh`, and the DB still wants the re-bootstrap the
`PrgLoader` defect forced. **It affects no figure here, and that was checked rather than assumed**:
all 171 `fn` addresses in `../names.txt` are already `F` records in the scan, so naming since the
scan created no function body the scan lacks, and every column is keyed on addresses and body
extents. A re-scan would change only the name strings (`FUN_00007522` where `../names.txt` now says
`bg_scroll_run_queue`). The 29,158 bytes in no function body are untouched by any of this — 24,900
of them are now charged to game logic.
