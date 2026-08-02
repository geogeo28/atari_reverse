# Reconstruction status — Wonder Boy in Monsterland

Human-readable C reconstruction of `SWB.PRG` (the original, uncracked 1989 Activision release,
extracted from the Pasti `.stx` of disk 1), each function to be **verified byte-for-byte against the
original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi oracle
running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 0/? — nothing is reconstructed yet.** The harness is stood up and proven against the
original code (`make test`: 77 cases green), and `../decomp.c` and `../names.txt` exist, but no
function has been ported. The function table below is therefore empty rather than partial: a row
appears when a function is reconstructed and green.

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
  bytes) are runnable end-to-end. So is every sprite blitter, the background scroll blitter and the
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
overlays which both implementations refuse (`docs/binary-formats.md` has the format).

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
  * **Its reachability today is zero.** `src/` is empty and no Wonder Boy test calls
    `differential()`. And under this build, forgetting the stub does not go green: it fails loudly
    with `did not reach checkpoint`.
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
  `RELOCATOR_INSN_CAP` — the derived one tracks `WB_BODY_LONGS` and the copy does not.
- **`test/layout.py`'s header scraper is the third copy** of the same idea (`joust`'s
  `test_constants.py`, `buggyboy`'s `test_course_ring.py`). It belongs in the kit; folding the three
  together was left out of this change as out of scope. It now has cases of its own
  (`test/test_layout.py`) and refuses the two readings it used to get wrong — a duplicate `#define`
  (it took the last silently) and a leading-zero decimal, which C reads as octal and Python refuses
  (it died with a bare `ValueError` naming neither the header nor the constant).

## Functions (by address)

None yet.

| Addr | Name | Bytes | Status | Verification |
|------|------|-------|--------|--------------|
