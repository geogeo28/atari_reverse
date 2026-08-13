# TOS trap model — what is modeled, and what is deliberately not

The oracle can't call real TOS, so every `trap` is serviced with fixed semantics
(`include/os.h` + `oracle/shim.c`). This file records, per trap, **what the model does, why that
design, and what it does NOT capture** — so a reconstruction built on top of it knows exactly which
of its behaviour is verified and which is merely un-contradicted.

It is the sibling of [`projects/buggyboy/recreate/HARNESS.md`](../../projects/buggyboy/recreate/HARNESS.md),
which established the governing rule and applied it to the IKBD.

## The governing rule

> The differential contract requires **both cores to see identical inputs.** The reconstruction is
> pure C with no interrupts, so IRQ-driven, time-varying state has no analogue on the candidate
> side and cannot be differentially verified. Therefore: model at the **state** level, not the
> IRQ level — hardware state becomes harness-poked constants, i.e. ordinary test inputs, identical
> on both sides.

And its corollary, which outranks everything below:

> **Never fabricate a result to make a call succeed.** An unmodeled call sets `modeled = 0`,
> `g_unmodeled` counts it, and `emu.run` **raises** rather than diff a fabricated result. A
> partially-modeled call that returns a plausible-looking wrong value is far worse than an honest
> raise: it converts a loud failure into a silent one.

### Refusing on ONE side is a false green (closed)

That raise covers the oracle. It did **not** cover the candidate, and the gap was a false-green
class rather than one function's quirk:

> The candidate calls the same `os.h` helpers, gets the same sentinel — `0` from `os_bconstat` /
> `os_bconin` / `os_super` / `os_gem_trap`, `-1` from the file calls — and carries on. `os_bconin`
> with no key pending touches neither its out-param nor the image, and `os_fopen` on an unstaged
> name touches nothing at all. So a reconstruction could **drop a guard the original has** and stay
> green: the only input that would expose the difference is exactly the one the oracle refuses to
> run.

Measured twice in `projects/joust/recreate/src/input.c`. Deleting `poll_console_key`'s `Bconstat`
gate outright left all 2325 cases green. `save_hiscore`'s `Fopen` is the same shape with no gate to
delete: it hands the candidate `-1` and lets it walk the `Fcreate` fallback, while the same call
rejects the oracle's run.

**Closed by giving the candidate its own tally.** `os_refused()` (`include/os.h`) records each
refusal and hands the sentinel straight back, so a helper cannot tally without also returning;
`src/os_refusal.c` holds the counter and exports `g_os_refusal_reset` / `g_os_refusal_count`, and
`kit.mk` links it into every candidate exactly as it does the Dosound ledger.
`harness.differential()` clears it before **each** candidate run — the `poison=True` re-run included
— and **raises if it comes back non-zero**, unconditionally, because a non-zero *oracle* tally
already raised inside `emu.run()` before the diff was reached. The three symbols are **required**
ABI, not probed-optional like the Dosound ledger: that ledger has an oracle-side witness saying when
it was needed, and this one cannot (the oracle's count is zero by construction), so a missing symbol
would reopen the class in silence. `harness` refuses to import instead.

**What that catches, and what it does not.** Deleting the `Bconstat` gate now fails two named cases
— `test_poll_quit_key_no_key_returns_at_once` and `test_hiscore_key_input_no_key_returns_at_once` —
because those cases really do drive the candidate into `os_bconin`. The `Fopen` instance is the same
mechanism, but **no case in the suite reaches it**: every quit case stages `HIGH.SCO`, so
`save_hiscore`'s `Fopen` succeeds, and the one unstaged case is oracle-only (`emu.run`, no candidate
at all). It was verified by construction instead — a case with `hiscore_dirty = 0`, `HIGH.SCO`
unstaged and `save_hiscore`'s early-out deleted produces **zero byte diffs** and is caught by the
tally alone. So the tally closes the class wherever a case reaches the call; it does not invent
cases, and the `Fcreate` fallback stays unreachable for the reason in limit 2 below.

Two details:

* **A build that must not tally** defines `OS_NO_REFUSAL_TALLY` and gets a no-op `os_refused()`.
  `shim.c` does — it keeps the oracle's own `g_unmodeled` and does not link `src/os_refusal.c` — with
  the `#define` next to the `#include` rather than in `kit.mk`, since a build flag can be forgotten
  where an adjacent line cannot. An **on-target** build whose cores call a refusing helper needs the
  same define: `os_refused` is the one non-`static inline` symbol `os.h` references, and no Atari
  build links the kit's `src/`. None needs it today (BuggyBoy's `game_build.sh` excludes `src/os.c`,
  its only caller, and the `.PRG` still links), but Joust's `src/input.c` *is* an ordinary core that
  calls `os_fopen`, so a Joust on-target build will. The switch is named for what it selects rather
  than for the oracle so that the remedy is one `-D` and not a redesign.
* **`Crawio` is not a refusal.** `os_crawio` and `os_bconin` share `os_console_take_key()`, which
  only reports whether a key was there; `os_bconin` alone turns "none" into a refusal. An idle
  console is a legitimate *result* for a non-blocking read and must not reach the tally.

What it proves is narrow: that a guard is **reached**, not that it is the right guard. Transcribe
guards from the original and reason about them; the tally only stops one from vanishing unnoticed.

## The CPU configuration — a decision, not an inherited default

Everything below is about traps. One thing about the **CPU underneath them** is a modelling
decision too, and it lived nowhere until it was written here:

> **`M68K_EMULATE_TRACE` is OFF.** The oracle's 68000 does not monitor the T bit and never takes a
> trace exception.

It is set by `-DM68K_EMULATE_TRACE=0` in `kit.mk`'s `OCFLAGS` — which `$(ORACLE)` lists as a
prerequisite, so changing it actually relinks — and refused at compile time by an `#error` in
`oracle/shim.c`, which sees the macro's *effective* value after `m68k.h` has pulled in `m68kconf.h`.
Two halves, because they pin different things: the `#error` catches the value being ON however it
got there (`make OCFLAGS=…`, a dropped continuation, an upstream header whose `#ifndef` guard went
away), and the behavioural case named below catches Musashi not honouring it. That placement is the
point.
`oracle/musashi/` is **gitignored and cloned from upstream HEAD** by the `$(MUSASHI)/m68kcpu.c`
rule, so `m68kconf.h` is not under version control: leaving the setting to that header's own
`#define ... M68K_OPT_OFF` meant the CPU the entire workspace's ground truth runs on was untracked,
unpinned, and asserted by no test — a fresh clone at a different upstream commit would have changed
it silently. The header's `#ifndef` guard is what lets the `-D` win. (Verified when it landed: the
rebuilt `liboracle.so` is **byte-identical** to the one the header's default produced, so the flag
changed the provenance of the setting and nothing else.)

**What it costs.** Self-modifying code that single-steps itself cannot run under the oracle. The
gap is latent rather than live: sweeping all five shipped `.PRG`s (BuggyBoy, START, Joust, GXUT20,
SWB) for the trace vector `$24` as an operand finds **one** instruction that writes it, Wonder Boy's
`move.l a0,$24.l` at runtime `$ee0a` — the Copylock's own — and that blob is stubbed out rather than
executed (`projects/wonderboy/recreate/PORTABILITY.md` §6.1). Every other occurrence of the value is
table data or a `$24` struct displacement. The sweep's limit is the one every operand scan in this
workspace has: a vector installed through a register (`lea $24.w,a0` + `move.l`) would not appear in
it.

**Why it is load-bearing rather than merely convenient.** That stub's witness — "did the protection
execute?" — is a memory *difference* over the blob's own bytes. A trace decryptor decrypts and
**re-encrypts** one longword at a time and restores the vectors it saved, so a blob that ran to
COMPLETION would leave almost nothing behind to see. The witness is sound because the blob cannot
complete, and it cannot complete because of this flag. Turning it on is therefore not a local
change: pin it against
`projects/wonderboy/recreate/test/test_copylock.py::test_the_oracles_cpu_takes_no_trace_exception`,
which asserts the setting BEHAVIOURALLY (a probe arms the T bit and requires the trace vector never
to be taken) rather than by reading the flag back. That case lives in a project rather than in the
kit's own suite because the kit's suite deliberately builds no oracle.

**STILL OPEN — this pins ONE of 25 CPU options.** `m68kconf.h` has 25 `#ifndef`-guarded settings
(`M68K_EMULATE_ADDRESS_ERROR`, `M68K_EMULATE_PREFETCH`, `M68K_EMULATE_INT_ACK`, `M68K_SEPARATE_READS`
and the rest), and every one of them is as untracked as the trace flag was, because the clone is
`--depth 1` off upstream HEAD with **no commit pin** — which is the real root. The general fix
Musashi itself offers is `-DMUSASHI_CNF='"<header>"'` (`m68k.h`), letting the kit supply one TRACKED
config header stating every decision, reviewable in a diff and a natural `$(ORACLE)` prerequisite.
Not built: nothing has needed a second option pinned, and the trace flag was pinned because a live
mechanism depends on it. Until it is, a fresh clone at a later upstream commit can move the oracle's
ground truth under every project at once with nothing red.

### The entry state every run begins from

A second decision about the same CPU, and the same kind: it is stated here because it is not an
inherited default either.

> **`osh_run` and `osh_run_bench` force `SR = $2700` after the reset** — supervisor, IPL 7, condition
> codes clear. **The entry CCR is guaranteed clear**, and a caller cannot set it: `emu.run` has no
> entry-CCR parameter, so no other entry condition is expressible.

**Why it is forced rather than left to the reset.** `m68k_pulse_reset()` is faithful to a 68000
reset, which does *not* clear the condition codes: it touches T, the interrupt mask and S, and leaves
`FLAG_X`/`N`/`Z`/`V`/`C` exactly as the previous run left them. Both entry points therefore used to
inherit the CCR of whatever had run before them **in the same process**, and any original that reads
a condition code on entry answered differently depending on run order — `abcd`/`sbcd` fold in X,
`addx` and `roxl` likewise. It surfaced as four Wonder Boy packed-BCD cases that reddened under
`pytest -n auto` and passed on their own, each off by one unit in the lowest digit. Determinism is
the requirement — two identical runs must give identical answers — and `$2700` is the kit's
convention for meeting it, not a claim about any game's own boot SR.

**What it costs.** An original the *game* enters with X set cannot be reproduced from a case. Wonder
Boy has one (`$e058`'s `subq.w #1` sets X, and `$e064` calls a BCD accumulator two instructions
later), registered as honestly unpinned in `projects/wonderboy/recreate/STATUS.md`. Modelling it
means giving `emu.run` an entry-CCR parameter; nothing has needed one yet.

**Pinned on both sides**, the same split as the trace flag above:

* kit-side by [`test/test_entry_state.py`](test/test_entry_state.py), whose `entry_state_probe.c`
  drives `osh_run` in C — one `abcd` three times in one process, with a middle run that wraps and
  leaves X set — because this directory binds no project and so cannot reach the oracle from Python.
  It compiles `shim.c` itself rather than linking the shared `liboracle.so`, so a reverted force
  cannot hide behind a stale artifact;
* game-side by
  `projects/wonderboy/recreate/test/test_hud.py::test_the_oracle_enters_every_run_with_the_condition_codes_clear`,
  over the reconstructions that surfaced it.

Reverting the force reddens both.

### What a run reports back

A third decision about the same CPU, and the one that decides what a differential can see at all:

> **`osh_run` reports `D0..D7` then `A0..A6`** — the full `movem` register set — at `out_regs[0..14]`
> (`OSH_OUT_REGS` in `oracle/shim.c`, mirrored by `emu.REPORTED_REGS`, which is what `emu.run`'s
> result dict is keyed by). **A7 is deliberately excluded**, and nothing past the set is written.

**Why the full set.** The register report is the *observability window*: a routine whose outputs live
in registers the oracle does not report cannot be pinned by a case at all — only by whatever memory
it happens to touch on the way. Narrow it and the harness silently changes what "verified" means for
register-passing code, which is most 68000 leaf code. The window used to be `D0/D1/A0/A1` — the four
a Ghidra-style calling convention returns in — and that was inherited from the first function ported,
not chosen. It cost real coverage: Wonder Boy stopped short of **three** reconstructions for
observability rather than difficulty, each recorded and re-run when this landed
(`projects/wonderboy/recreate/STATUS.md`, batches 3 and 10) — a five-instruction routine whose entire
load-bearing output is `a6/d2/d3/d7`, a plotter's outgoing `d7`, and a mutation that survived only
because the window hid the field it corrupts.

**Why A7 is not in it.** A7 is not the function's register but the *harness's*: `osh_run` forces it to
`sp` on entry and the run's own `rts` pops the sentinel frame back off it, so its final value states
the harness's convention (`STACK_TOP + 4`) rather than anything the function computed. A case
asserting it would be asserting the kit's own arithmetic and calling the function verified.
`osh_min_a7()` — the deepest A7 the run reached, which `harness.differential` already vets its diff
exclude bands against — is the one fact about the stack pointer a case can use.

**What it still costs.** Three limits remain, and they are the same shape as the entry CCR's:

* **the report is at `rts` (or the `stop_pc` checkpoint) only** — no intermediate register state is
  visible, so a value a routine computes and then overwrites is unobservable;
* **no condition codes** — a routine whose output is a flag can only be pinned through something that
  reads the flag (Wonder Boy's scroll cases do it via the caller's rewritten return address);
* **no FP/control registers** — irrelevant on a 68000 target, stated so the omission is a decision.

**Pinned on both sides**, the same split as the two decisions above:

* kit-side by [`test/test_reported_regs.py`](test/test_reported_regs.py), whose
  `reported_regs_probe.c` drives `osh_run` in C: one `movem.l (table).l,d0-d7/a0-a6` puts a distinct
  mark in every reported register, a second run leaves them all at their entry values, and a canary
  one slot past the set catches a run that writes more than it declares. It compiles `shim.c` itself,
  so a narrowed report cannot hide behind a stale `liboracle.so`. The same file pins `emu.py`'s
  mirror against `shim.c` textually (CLAUDE.md §5: the C fills the buffer, the Python allocates it,
  and neither can import the other);
* game-side by every case that asserts a register past `d1`/`a1` — Wonder Boy's map probes
  (`test/test_map.py`) are the first.

**A stale `liboracle.so` is caught rather than tolerated.** The `.so` is shared by every project and
rebuilt only by `kit.mk`'s `$(ORACLE)` rule, so building against an old one is a normal state to be
in; here it would mean the Python side allocating fifteen slots the C side never fills (silent zeros
where a case expects an output) or, in the other direction, the C overrunning the caller's buffer.
`osh_out_regs()` exports the count and `emu.py` checks it against its own mirror at import, naming
the rebuild.

## The harness-poked model state

Four regions of the image are inputs the harness pokes, not program memory. Both cores read the
same bytes, so every one of them is an ordinary, differentially-verifiable test input.

| Address | Constant | Meaning |
| --- | --- | --- |
| `0x500` | `OS_KBDVBASE` | the KBDVBASE struct XBIOS `Kbdvbase` returns |
| `0x600` | `OS_CON_PENDING` | u32, nonzero = a character is waiting at the console |
| `0x604` | `OS_CON_CHAR` | u32, what `Bconin`/`Crawio` return (`scancode << 16 \| ascii`) |
| `0x608` | `OS_RANDOM_VALUE` | u32, what XBIOS `Random` returns (masked to 24 bits) |
| `0x610` | `OS_PSG_REGS` | 16 bytes, the YM2149 register file XBIOS `Giaccess` reads/writes |

They sit in the free low region — clear of the 68000 vector page and above TOS's documented
system-variable area. `recreate_kit/os_map.py` mirrors the addresses (its own module, because
`harness.py` and `oracle/emu.py` both guard the block and neither can import the other),
`test/test_os_memory_map.py` pins the two sets equal, and `harness.console_key()` /
`harness.psg_regs()` build the pokes so the fields that must move together cannot be set half-way.

### They are no longer below every program

They used to be: every project loaded at `0x10000`, and `harness._vet_os_memory_map()` enforced
`load_base >= 0x620`. `projects/wonderboy` cannot obey it — its program relocates itself to the
absolute address `0x400`, and everything below that is the 68000 vector page — so it loads at
`0x3f8` and **the block sits inside its code**. A `project.toml` may now declare
`tos_poked_input_unused = true`, the claim that the game reads none of this state, and get that
layout. The claim is checked rather than assumed, from both directions the hazard has, and **both
guards key on the overlap, never on the flag**:

* **`harness.make_image()`** refuses any poke whose byte range lands in the block. It sits at the
  layer pokes are *applied*, so a hand-written `{OS_RANDOM_VALUE: …}` dict — the only way to stage
  an XBIOS `Random`, since the kit ships no builder for it — is seen exactly like a `console_key()`
  one.
* **`emu.run()`** refuses any run in which a trap *reached* the block (`_vet_no_poked_input_read`,
  keyed on the shim's `osh_poked_input_calls` tally of `Bconstat` / `Bconin` / `Crawio` / `Random` /
  `Giaccess` / `Kbdvbase`). Reached, not read: a `Giaccess` write stores into the register file and
  `Bconin` clears the pending flag, and under the overlap those are writes over the game's own code.
  `Crawio` is tallied for its **read** direction only (`OS_CRAWIO_READ`); printing a character
  touches nothing and must not redden a run.

Two limits of the tally, stated because neither is obvious. It is **oracle-side only**, unlike the
refused-`os_*` tally: a candidate that calls `os_bconstat` where the original does not is caught by
the image diff instead (`os_bconin` clears the pending flag, so the bytes differ) — but a candidate
whose extra call is genuinely image-neutral is not. And it says a poked-input trap was *served*, not
that the block it reached lies in the program; the guard's overlap question is asked about the poked
block alone, which is why the `Kbdvbase` arm below is only covered when that block also overlaps.

`harness.console_key()` / `harness.psg_regs()` refuse too, but as a friendlier early error naming
what was staged; `make_image` is what makes the refusal unbypassable. The second guard is the one
that matters most, and it is the sibling of the Malloc waiver's `_vet_no_malloc_over_program`: the
dangerous reader is the **game**, not the test. A `Bconin` in code that only exists after a depack
reads the program's own instruction bytes, which are nonzero, so the model reports a keystroke
pending, hands back four bytes of code as the key, and **zeroes four bytes of code** at
`OS_CON_PENDING` — identically on both sides, since both run the same `os.h`. The diff is clean and
the case proves nothing.

### Two regions this leaves unvetted

`OS_KBDVBASE` (`0x500`, whose KBDVBASE struct `install_handlers` patches) and `OS_SCREEN_BASE`
(`0x8000`, what `Physbase`/`Logbase` return) have never had a check of their own. They were covered
*incidentally* by the `load_base >= 0x10000` every project happened to use, and the waiver removes
exactly that incidental coverage: at Wonder Boy's `0x3f8`, `0x3f8 <= 0x500` and
`0x8000 < 0x218d0`, so **both regions are now inside a live program** and no layout check looks at
either. One of the two has a partial answer on the other side: `OS_KBDVBASE`'s only reader is XBIOS
`Kbdvbase`, which *is* one of the six traps the tally above counts — so a program that reaches it
reddens the run **whenever the poked block also overlaps** (Wonder Boy, the only waived project, is
such a layout). A program covering `0x500` but not `0x600` would still not be seen, since the guard
keyed on that tally asks about the poked block, not about `0x500`.

`Physbase`/`Logbase` (XBIOS `0x02`/`0x03`) are tallied by nothing, so a program that takes the
modeled screen base and draws into it scribbles its own code on both sides in silence. Closing it
means what the poked block got: its own overlap predicate and its own tally, keyed on
`OS_SCREEN_BASE` rather than on the poked block. It is deliberately **not** folded into the tally
above — that guard's predicate is the wrong question for `0x8000`, and answering it with the poked
block's overlap would be over-strict for one layout and blind for another.
`tools/recreate_kit/test/test_os_memory_map.py::test_every_low_model_address_is_guarded_or_declared_unvetted`
holds the list of two, so a third region cannot join it quietly.

---

## Phase 1 — BIOS `Bconstat` (0x01) / `Bconin` (0x02)

Before this the whole `trap #13` arm was `modeled = 0`; the BIOS branch is new.

**Modeled.** `Bconstat(dev)` returns `-1L` when a character is waiting and `0` when not — the
longword convention Joust reads with `cmp.l #$ffffffff,d0` (`poll_quit_key`, `hiscore_key_input`)
and with `tst.b d0; blt` (`title_screen`). `Bconin(dev)` returns `OS_CON_CHAR` and **consumes** the
keystroke, clearing `OS_CON_PENDING` the way the real console does — so one poke is one keypress
and a polling loop sees the letter exactly once rather than holding it down forever.

**Design choice.** Keystrokes arrive on the IKBD interrupt, which the oracle never runs, so per
HARNESS.md they become poked state rather than a simulated device. Consuming (rather than
latching) the key was chosen because Joust's real consumers — the name-entry loop, the quit poll —
are *loops*: a latched key would make every iteration see the same letter, which is a behaviour no
real run has.

**Not captured.**
- **Only the console (`OS_BIOS_DEV_CON` = 2) is modeled.** `Bconstat`/`Bconin` on any other BIOS
  device raise; there is no keystroke state for them and inventing one would be a fabrication.
- **`Bconin` with nothing pending raises.** On real hardware it *blocks* until a key arrives, and
  there is nothing here to wait for. A test must always stage the key it expects to be read.
- **No keystroke *sequence*.** A run delivers at most one key. A loop that reads several distinct
  keys (Joust's name entry) has to be verified one poked key per run, exactly as HARNESS.md's
  Phase 2 did for the joystick.
- **Every other BIOS selector still raises** — `Bconout`, `Setexc`, `Kbshift`, `Rwabs`, …

## Phase 2 — GEMDOS `Super` (0x20)

**Modeled — a TOKEN model, not a privilege model.** `Super(0)` returns the fixed cookie
`OS_SUPER_TOKEN`; `Super(OS_SUPER_TOKEN)` accepts it back and returns 0; `Super(1)` (SUP_INQUIRE)
returns `-1` (supervisor). **Any other restore value raises.**

**Design choice, from reading all six of Joust's call sites** (`0x1018a`, `0x1021a`, `0x11d38`,
`0x152ea`, `0x15480`, `0x154a4`):

- three sites (`init_system` twice, `poll_quit_key` once) do `clr.l -(a7); move.w #$20,-(a7);
  trap #1; addq #6,a7` — the returned stack pointer is **discarded**; the call exists only to stay
  in supervisor mode while touching `$484` (conterm) and `$43e` (flock);
- the floppy routine at `0x152dc` does `move sr,d0; btst #13,d0` to test the S bit **itself**, and
  only if it is in user mode does it call `Super(0)`, save the result verbatim to `0x1560e`, and
  later pass that same longword back to `Super(…)` at `0x15480`/`0x154a4`.

So no site ever *inspects* the value; it is either dropped or round-tripped. That is exactly what a
token satisfies, and it avoids the alternative — flipping the 68000 S bit and swapping A7 between
USP and SSP — which would perturb the stack and interact with the harness's stack-guard band for
no observable gain. Refusing an unrecognised restore value keeps the token from silently absorbing
a site that does something else.

**Not captured.**
- **No privilege checking whatsoever.** Musashi starts every `osh_run` in supervisor mode and the
  model never leaves it, so code that genuinely requires supervisor to touch a protected address
  is never tested for it — it simply always succeeds.
- **Consequently, `move sr` reads S = 1 for the whole run.** Joust's floppy routine therefore takes
  its "already supervisor" branch and its three `Super` sites are **unreachable under the oracle**.
  A user-mode path can only be exercised by a model that really flips the S bit.
- The cookie is not a real stack pointer. A site that did arithmetic on `Super(0)`'s result would
  be mismodeled — which is why anything other than the cookie is rejected rather than served.

## Phase 3 — XBIOS `Giaccess` (0x1c) and the YM2149 register file

This is the substantive one: before it there was a write *ledger* but no readable register state,
so a `Giaccess` read had nothing correct to return.

**Modeled.** A 16-byte register file at `OS_PSG_REGS`, in the image. `Giaccess(data, reg)` writes
`data` to register `reg & 0x0f` when bit 7 of `reg` is set, and otherwise reads that register,
zero-extended into D0. Because the file is plain image state, a `Giaccess` write is an ordinary
image write the differential already covers, and `os_giaccess()` is shared verbatim by the shim and
by any reconstruction — the same construction that makes `os_fopen` agree on both sides.

**Initial state: all registers 0.** A fresh image is zero there, so a run is deterministic without
the model asserting anything about the chip's power-on contents. A test whose control flow depends
on a register states it with `harness.psg_regs({...})`. This matters: Joust's `snd_poll_done`
(`0x10a8a`) reads the **mixer** (register 7) and releases `snd_priority` to idle only when all six
tone+noise enables are set, so the value read steers control flow. Both branches are pinned by
`projects/joust/recreate/test/test_os_traps.py::test_snd_poll_done_follows_the_staged_mixer`,
which runs Joust's own function under the oracle with the mixer staged.

**The PSG ledger is unchanged.** `emu.psg_writes()` still reports exactly the direct `$ff8802` byte
writes it always did, in the same order, with the same `(reg, val)` tuples — BuggyBoy's
`test_sound.py` and the remaster suite are untouched. `Giaccess` does **not** append to it; its
writes are visible in the image instead.

**Not captured — and guarded: the direct hardware path.** The register file is fed by `Giaccess`
**only**. A driver that touches `$ff8800`/`$ff8802` directly is captured by the off-image ledger
instead, and those writes deliberately do not reach the file: making them do so would put PSG bytes
in the image on the oracle side only, since BuggyBoy's candidate emits its register stream into
out-param arrays rather than into memory — the whole `test_refresh_*` battery would fail on a
difference that has nothing to do with the reconstruction. So `osh_run` **rejects any run that uses
both paths** (`osh_psg_mixed_paths()`), because such a run could be served a read from a register
file it knows is stale. `emu.run` names that cause specifically, since it is otherwise a puzzling
"unmodeled OS call" on a run whose every trap *was* modeled.

**This guard is live, not hypothetical.** BuggyBoy is direct-only (no `Giaccess` anywhere), but
**Joust reaches both**: its sound driver calls `Giaccess` ten times, while its raw-floppy routine
selects and rewrites PSG port A directly at image `0x1553c` — the standard ST drive-select, six
instructions:

```
0x1553c  move.b #$0e,$ff8800     0x1554c  and.b  #$f8,d1
0x15544  move.b $ff8800,d1       0x15550  or.b   d0,d1
0x1554a  move.b d1,d2            0x15552  move.b d1,$ff8802
```

(reached by `bsr` from `0x15342` and `0x154fc`; the enclosing subroutine starts six bytes earlier
at `0x15536` with `move sr,-(a7); ori.w #$0700,sr`. `0x15540` is the *address operand* of the first
instruction, not an instruction — note the `move.b d1,d2`, which saves the pre-mask port value.)
Any single `osh_run` spanning both layers is therefore refused. The two
touch disjoint registers (14 vs 0–10), so a finer guard keyed on the register number would let such
a run through; the coarse one was chosen because being over-strict fails loudly while being
under-strict fails silently, which is the wrong way round for this contract.

**The direct path serves only byte writes; everything else about it raises.** *(Superseded in part
by Phase 6 below, which gives `$ff8800` a real read model — the second bullet stands unchanged, and
the first is why the read had to be seeded rather than simply served.)* `g_psg_unmodeled` counts,
and `osh_run` rejects, two kinds of direct access — the same "refuse rather than fabricate" answer
the trap dispatch gives an unmodeled selector:

- **any read of either port.** Reading `$ff8800` reads back the selected register on real hardware,
  and the ledger records writes only, so there is nothing correct to return. It used to be served
  as 0, which is exactly the forbidden case: Joust's drive-select
  (`move.b $ff8800,d1; move.b d1,d2; and.b #$f8,d1; or.b d0,d1; move.b d1,$ff8802`) would have port
  A's preserved upper bits forced to zero, and — since a run using *only* the direct path never
  trips the mixed-path guard — a reconstruction of that routine could be marked verified against the
  fabricated read. BuggyBoy never reads the ports (`lea` + `move.b`/`clr.b` writes only, and
  Musashi's `clr` does not emit the 68000's dummy read), so raising costs nothing.
  **Phase 6 narrows this to the DATA port `$ff8802`**: `$ff8800` is answered from a register file the
  case seeds, and a register nothing declared is still refused — the ledger's emptiness was never the
  real obstacle, the chip's *prior contents* were.
- **any other access to the chip's address block.** The ST decodes the YM2149 incompletely, so it
  answers across `$ff8800..$ff88ff` (`PSG_BLOCK_END`); of that, only the byte
  select-latch-then-data sequence on the canonical pair is modeled — not the odd-address decoding
  a `move.w #$0e00,$ff8800` relies on, and not the mirrors. This is what keeps the mixed-path guard
  honest: before, only the *byte* callbacks compared the address against the two ports, **by
  equality**, so a wider access, an odd address, or a mirror reached neither the ledger nor the
  tally and could be combined with `Giaccess` without tripping the guard. Neither binary does any
  of it today — Joust's three direct accesses are byte-sized and port-aligned — so the guard's
  soundness was an unenforced property of the two input binaries. Now every callback width tallies
  any overlap with the block, so a third game cannot silently disarm it.

**Consequence — Joust's raw-floppy routine (`0x152dc`) was unverifiable under this oracle.** Not just
its `Super` sites (Phase 2): the *whole* routine. Because a direct port read was rejected **on its
own**, the `move.b $ff8800,d1` at `0x15544` sank any run that reached it, with or without a
`Giaccess` alongside — so no `emu.run` covering `0x152dc` could ever be green.
**Phase 6 is the "real PSG read model" that sentence was waiting for**: a case that declares port A's
contents (`psg_seed={14: …}`) can now run the drive-select, and the read is served from the declared
value rather than from a fabricated `0`. Two of its other blockers are unaffected — the routine's
`Super` sites stay unreachable while the model never leaves supervisor mode, and a run that also
reached `Giaccess` would still trip the mixed-path guard — so this lifts the PSG wall, not the whole
routine. `projects/joust/recreate/STATUS.md`'s row says exactly that now.

**One opt-in exception, for a job that is not the differential: `emu.audio_capture(True)`.** An
asset extractor drives a game's music replayer tick by tick and reads its register stream out of
`psg_writes()`; that needs the `$ff8800` read-back, so the refusal above made it impossible. With
the mode on, `shim.c` answers a byte read of `$ff8800` from the YM2149 **register file** — which is
what the chip does, and was, before Phase 6, the model the paragraph above says the oracle lacks.
Since Phase 6 that file is the *shared* one and the mode is a **relaxation** of it rather than a
second copy: an undeclared register reads `0` here instead of refusing, an unselected latch likewise,
and the file and latch span runs instead of being re-seeded per run. It also serves the two bits a
replayer's tempo selector reads, `$fffa01` bit 7 (monitor
detect) and `$ff820a` bit 1 (shifter sync), as the **50 Hz colour ST**: both read 0 off-image, 0/0 is
the *monochrome* profile, and a capture that took it would drop 72/256 of every tick and render every
song slow, silently.

*Exactly what is served* is those two bits and nothing more — plus GPIP bits 5 and 4, the FDC and
ACIA interrupt lines, which are **active low** and so are set because idle is 1: serving bit 7 alone
would report both devices as interrupting, a state no quiescent machine is in. Every other bit of
that byte is a fabricated 0. Because the answer is two named bits rather than a machine model, only a
**byte** read of either address is served; a 16- or 32-bit read taking one in would have to fabricate
the neighbouring MFP/shifter registers, so it is recorded rather than served and sinks the run.

> **Superseded in two ways by Phase 7, and read that section for the current rule.** Since Phase 7
> these two addresses are a *seeded model of their own*, and this mode no longer answers them with a
> switch of its own — it **installs a seed** over that model, per run (`hw_enter_run`). Two claims
> this paragraph used to make are therefore no longer true:
>
> * the wide-read refusal is **not** "armed only under capture". The wide-read mask
>   (`osh_hw_wide()`) is recorded on **every** run, and `harness.differential` refuses on it in every
>   differential. What is still capture-only is where `emu.run` *raises* on it — an extractor has no
>   diff to catch it and no second chance;
> * these bytes are **not** fabricated-only-under-capture. Off the mode a case declares them with
>   `hw_seed=`, and a differential whose oracle reads one undeclared is refused.
>
> **The hazard this note exists to prevent**, spelled out because it is the plausible next edit:
> re-gating `shim.c`'s `hw_note_wide_read()` on `g_audio_capture` to make it agree with the sentence
> above. That would restore the paragraph and silently reopen the hole — off the mode, a
> `move.w $ff820a,d1` in a differential would be an unrecorded, unrefused fabrication of the register
> beside it. Correct the *prose* against Phase 7, never the code against this prose.

This does **not** narrow the guard, because it does not apply to a differential — and that is
enforced, not merely stated: `harness.differential()` vets `emu.audio_capture_on()` and refuses
outright. Each served answer is still fabricated with respect to a differential — the model's
invention, not the game's data, so a reconstruction verified against it would be verified against
`shim.c` — which is why the mode is opt-in, off by default, and changes nothing at all while off.
Joust's `0x152dc` stays blocked: the capture mode is not a licence to run it under a differential.
Everything else about the direct path is unchanged in either state, including both refusals above for
a mirror, an odd alias, a non-byte access, and a read of the write-only **data** port `$ff8802` (the
chip reads back through the select port; answering `$ff8802` would invent a port the hardware does
not have).

**The capture spans runs.** The register file *and* the select latch persist across `osh_run` calls
while the mode is on — an extractor calls `osh_run` once per VBL tick, and tick N may read back what
tick N-1 wrote to a register tick N-1 selected, exactly as the chip's own latch and registers survive
a VBL. Neither is reset by a run. Arming is a pure **toggle** and clearing is a separate
`osh_audio_reset()` / `emu.audio_reset()` (the `cov_enable`/`cov_reset` shape): a fused
enable-and-clear could not be issued defensively mid-capture without destroying it. Off the mode both
are per-run: the latch, or run N's `(reg,val)` pairs would be attributed to run N-1's last selected
register and a `-n auto` suite would be order-dependent; the file, because a differential run must
start from the contents its own case declares (Phase 6).

Pinned by `projects/wonderboy/recreate/test/test_audio_capture.py`, whose replayer holds both a
read-back and the tempo selector, and — for the relaxations and the arm-from-off clear, which are
properties of the shared model rather than of a game — by the kit's own `test/test_psg_model.py`.
**A run made under the mode must opt into it**: `emu.run` refuses one that was not scoped by
`emu.audio_capturing()`, since the mode is oracle-global and a run can otherwise be served the mode's
fabricated answers without ever asking for them (a block that raised on its way out, an extractor in
the same process). A served read-back still counts toward `g_psg_direct`, so it **arms the mixed-path guard**
exactly as a direct write does — the register file is fed by the direct path only, so a `Giaccess`
alongside it is as stale as before. That half is pinned in `projects/joust/recreate/test/
test_os_traps.py`, Joust being the only project that reaches both paths at all.

**The PSG ledger reports its own truncation.** `psg_writes()` is the capture's primary data feed, so
an access past `os.h`'s `OS_PSG_LOG_MAX` cap is counted (`osh_psg_dropped`) and named by `emu.run()`
as a cause of its own: a silently truncated register stream would read as a complete capture with a
section of the song missing. Reads occupy ledger entries too since Phase 6, so the cap now counts
accesses rather than writes — the tally is what makes that change loud instead of silent.

**GEMDOS `Crawio` (0x06) reads the same console state** as `Bconstat`/`Bconin` (`os_crawio`), rather
than being a second, disconnected model: one staged key is visible to every console call and is
consumed once, as on real hardware. Unlike `Bconin` it never refuses — "no key"
(`OS_CRAWIO_RESULT`) is a legitimate answer for a non-blocking read, and it is what an image with
nothing staged gives. Its argument picks the **direction** and is honoured: `OS_CRAWIO_READ`
(`0xff`) reads, and any other value is a character to *write* to the console — no image effect and,
crucially, no keystroke consumed, since servicing every `Crawio` as a read would let a program that
merely prints a character swallow the key a later `Bconin` is waiting for. BuggyBoy's eight sites
all pass `0xff`; Joust issues no `Crawio` at all — a byte scan of `JOUST.PRG` finds no `trap #1`
with selector `0x06` anywhere — so only the read path is exercised today.
BuggyBoy's candidate (`src/input.c` `check_abort`, `src/os.c` `console_scancode`) still hardcodes
`OS_CRAWIO_RESULT` instead of calling `os_crawio`. That agrees byte for byte while no test stages a
key — which is every BuggyBoy test, none of which pokes `OS_CON_PENDING` — and if one ever does,
the two sides differ in D0, so the gap fails loudly rather than silently.

Also not captured: **nothing plays sound**. `Dosound` only logs its list pointer, and there is no
VBL sound engine, so the mixer never changes on its own — it holds whatever the program or the
harness last put there. A "wait until the sound finishes" loop therefore terminates only if the
mixer is staged to say so. And `Giaccess`'s return value for a *write* is modeled as 0; TOS does
not define it, so no caller may rely on it.

Finally, the `Giaccess` register file records only each register's **final value**, not the ordered
stream of writes — unlike the direct path's ledger. A `Giaccess`-driven driver is therefore verified
more weakly than a direct-write one: two orderings that end in the same 16 bytes are
indistinguishable. Phase 6 built "one write feeding both a register file and an ordered ledger" for
the **direct** path; doing the same for `Giaccess` would mean appending to a ledger from
`os_giaccess()`, which both sides share — so the two ledgers would agree by construction and prove
nothing unless the oracle's were fed from the trap instead. Not taken. BuggyBoy's `g_REFRESH`
out-params could likewise be replaced by `psg.h` now that it exists, but that reshapes a verified
game's candidate ABI for no new coverage (its stream is already compared, frame by frame, by
`projects/buggyboy/recreate/test/test_sound.py`), so it is noted here rather than taken.

## Phase 4 — GEMDOS `Fcreate` (0x3c) / `Fwrite` (0x40)

**Modeled.** The staged-file table grows a `capacity` field (`OS_FS_OFF_CAPACITY`, entry stride
32 → **36 bytes**). `harness.stage_files()` accepts `(name, data, capacity)` — and the plain
`(name, data)` a read-only file needs, capacity then defaulting to the data's own length —
reserves that many staging bytes, and lays each file out past the previous one's *reservation*, so a
file grown by `Fwrite` cannot land on the next file's bytes. `Fcreate(name, attr)` truncates an
already-staged file to zero length and opens it; `Fwrite(handle, count, buf)` copies into staging
at the cursor, extends the length, and returns the byte count. All of it lands **in the image**, so
both cores see the bytes and the diff covers them.

**Design choice — the harness declares the filesystem.** Nothing here ever invents a staging
address. `Fcreate` of a name the harness never staged returns -1 (→ raise) instead of handing out a
block it has no space for, and `Fwrite` past the reservation returns -1 (→ raise) instead of
overrunning the next file's bytes or fabricating a short-write/disk-full result the harness has no
basis for. `Fcreate` also cannot walk past the table: it only ever matches an occupied slot inside
`OS_FS_SLOTS`, and `stage_files` refuses to declare more files than there are slots.

**Both ends of every copy are bounded** against `OS_IMAGE_SIZE`, not just `count` against the
capacity. `buf` arrives from the emulated program's stack exactly as `count` does, so `Fwrite(6, 4,
0xfffffff0)` would otherwise `memcpy` outside the image buffer — and `Fread`'s side is the worse
one, since it *writes* through `buf`. Every `m68k_*_memory_*` callback bounds-checks its access this
way; `os_fread`/`os_fwrite` are the only two places that touch the image without going through one.
They refuse rather than truncate: a short count the harness has no basis for is a fabricated result.
`OS_IMAGE_SIZE` is kit-wide because a reconstruction calling `os_fread` is handed the image pointer
alone, never a length; `harness._vet_os_memory_map()` pins it equal to the bound project's
`image_size`, so a project that grows its image fails loudly instead of copying past the buffer.

**Not captured.** No directories, no `Fseek`/`Fdelete`/`Fattrib`, no attribute or mode handling
(`Fopen`'s mode and `Fcreate`'s attr word are ignored), no error codes — the model has exactly two
answers, "served" and "refused". Writes do not persist beyond the run: staging is image state, so
it is gone with the image copy.

The table layout is mirrored **field by field** in `harness.py` (`OS_FS_OFF_*`) rather than
concatenated in order, and `test/test_os_memory_map.py` pins every offset against `os.h` — a field
reordered on one side would otherwise drift in silence, which is how the capacity field came to be
missing from the Python entry in the first place.

## Phase 5 — XBIOS `Random` (0x11)

**Modeled.** `Random()` returns `OS_RANDOM_VALUE` masked to 24 bits.

**Design choice — Random is a test INPUT, not a generator.** Real `Random` is derived from the
system clock: time-varying, machine-dependent, and by construction not reproducible by a pure-C
candidate. Under the governing rule that makes it exactly the same kind of thing as `input_state`
in HARNESS.md — a value the harness supplies identically to both sides. Seeding an LCG instead
would have been a *second* cross-side ABI to mirror for one call site (Joust's is at `0x106b8`, in
`init_game`, and it uses only `d0 & 0xfe`), which CLAUDE.md §2 does not justify.

**Not captured.** Every call in one run returns the **same** value. A program that loops until
`Random` differs would spin — but that failure is loud, not silent: the run exceeds `max_insns` and
`emu.run` raises "did not reach rts". This is the one place where the honest answer might instead
have been "leave it raising"; it is modeled because the failure mode of getting it wrong is a
raise, never a wrong image.

## Phase 6 — the SEEDED PSG READ MODEL (the direct `$ff8800`/`$ff8802` path)

Phase 3 left the direct path write-only: the ledger recorded the *order* of the writes and nothing
recorded their *effect*, so a `move.b $ff8800,dn` had no correct answer and raised. This gives it
one. It is the capability three projects' remaining sound and floppy work stands behind.

### Why a write-ledger replay is the wrong model — the finding this is built on

The obvious implementation is "hand back the last value written to the selected register", folding
the ledger into a file that starts at zero. **That recreates the exact false-green class it was
meant to fix**, and the evidence is in every binary this workspace has:

The **routine** column is the function's entry; the **read** column is the `move.b $ff8800,dn` inside
it. They are different addresses, and an earlier revision of this table quoted the read site under
the function's name for three of the four rows — enough to send a reader to the wrong instruction.

| routine | the read | what it preserves | what a fabricated `0` does |
| --- | --- | --- | --- |
| Wonder Boy `snd_psg_silence` `$17f30` | `$17f3e` — `move.b $ff8800,d1; ori.b #$3f,d1` | mixer bits 6–7, the port A/B **I/O direction** lines | writes `$3f`: port A flips to input and the floppy drive-select lines float |
| Wonder Boy `snd_music_tick` `$17c74` | `$17f08`, merged at `$17f12` — `eor.b d0,d3; and.b d2,d3; eor.b d0,d3` | every mixer bit outside this module's `d2` mask | collapses to `shadow & d2`, clearing bits 6–7 as above |
| Wonder Boy `psg_set_drive_select` `$624c` | `$6254`, merged at `$625a` — `andi.b #$f8,d1; or.b d0,d1` | port A bits 3–7 (side select and the rest) | forces them to zero |
| Joust drive-select `0x15536` | `0x15544` — `move.b d1,d2; and.b #$f8,d1; or.b d0,d1` | the same port A bits | the same |

Every one of them preserves bits **the game never writes**, so on the first read a replayed ledger
has no value for them and answers `0` — a value TOS never leaves there. A reconstruction merging the
same fabricated `0` agrees with the oracle byte for byte and is verified against `shim.c`. Worse, the
class hides: `projects/wonderboy/recreate/PORTABILITY.md` §3 records that **T1 is empty** — every
PSG *writer* in that game also *reads* — so not one byte of its sound is verifiable through the
ledger alone, and §4's Correction 2 records a `snd_music_tick` case that came back green only because
control flow never reached the read.

> **So the chip's contents on entry are an INPUT of the run, not a consequence of it** — the same
> kind of thing as a poked keystroke or `OS_RANDOM_VALUE`, and subject to the same governing rule:
> the harness supplies it identically to both sides, or the model refuses to run.

### Modeled

**A 16-byte register file, off-image, fed by the direct path only**, plus a `known` bitmask saying
which of its registers have contents at all, plus a `latch-known` flag saying whether anything has
selected a register yet. Four rules:

* **a byte write to `$ff8800`** latches the register number, and marks the latch known. A value
  above `$0f` is **refused** rather than masked down — see the edge table;
* **a byte write to `$ff8802`** stores into the latched register **and** appends a `WRITE` event to
  the ordered ledger. One write, both surfaces: the ledger is what catches a missing, extra or
  reordered access, the file is what a read-back answers from. The register becomes *known*;
* **a byte read of `$ff8800`** returns the latched register's contents **if it is known** — declared
  by the case's seed, or written earlier in the same run — and appends a `READ` event to the same
  ledger. Otherwise the run is **refused**: `osh_psg_unseeded()` returns a bitmask of the registers
  read while unknown and `emu.run` raises, naming them and the `psg_seed=` that would declare them;
* **a byte read of `$ff8800` with nothing selected** is refused in its own tally
  (`osh_psg_no_select()`). A read answers the *latched* register, and the `0` the latch would
  otherwise start from is `shim.c`'s convention rather than the chip's state — on a real ST it holds
  whatever the last driver to touch the chip left there. **The latch is deliberately NOT seedable.**
  A seed declares what a register *contains*, which the routine cannot compute; the select is an
  *instruction*, which the run either executes or does not, and every PSG driver in every input
  binary selects immediately before it reads (`$17f36` before `$17f3e`, `$624c` before `$6254`,
  `0x1553c` before `0x15544`). A seedable latch would let a case declare that an instruction ran.
  The remedy is to enter at or before the routine's own select — so the refusal names that, not a
  `psg_seed=`. If an input binary ever *does* read a latch it inherited, that is a new claim about
  entry state and it should arrive with the evidence, not with a keyword argument already in place.

**Reads are part of the compared stream**, and that is not bookkeeping. A reconstruction that reads
the WRONG register still writes the right one: given a decoy register holding the byte the real one
held, its write stream *and* the register file it leaves are a correct run's, byte for byte. Only the
read entry separates them. `emu.psg_writes()` is the **write-only projection** of the same stream and
keeps its contract unchanged — it is the audio extractor's data feed and every existing consumer's.

**The seed is the case's, and it is per-run.** `emu.run(..., psg_seed={7: 0xc0})` /
`harness.differential(..., psg_seed=…)` install it before **every** run — an empty one included, so a
seed cannot leak from the previous case — and the file is rebuilt from it at the top of each
`osh_run`. A register another case wrote is therefore not readable here, for the reason `ENTRY_SR`
forces the condition codes: two identical runs must give identical answers whatever ran between them,
and under `pytest -n auto` "whatever ran between them" is not stable.

**The final state is part of the observable surface.** `emu.run` reports `psg_events` (the ordered
stream, reads included), `psg` (its write-only projection), `psg_file` and `psg_known`;
`harness.differential` compares the stream and the file against the candidate's after every run. They
live outside the memory image, so nothing else could catch a divergence in them — which is the whole
reason they are exported rather than left as diagnostics.

Their relation is worth stating plainly, because it decides what each one is *for*. The **ledger** is
the net under the reconstruction: it catches an access missing, extra, wrong, out of order, or aimed
at the wrong register — the last of those being why it carries reads, and being invisible to every
other surface there is. The **file** adds no coverage of the game code on top of that: under equal
seeds an equal ledger implies an equal file, since both sides store on exactly the writes they log.
It is compared as a cross-check of the two model *implementations* against each other — a
register-width mask added on one side, capture state leaking into a differential — which is the one
thing the ledger comparison cannot see.

### The candidate side

`include/psg.h` + `src/psg.c` — linked into every candidate by `kit.mk`, exactly like the Dosound
ledger and the refusal tally:

```c
void    psg_port_write(unsigned reg, uint8_t value);   /* select, then data */
uint8_t psg_port_read(unsigned reg);                   /* select, then read back $ff8800 */
```

Named for the **ports** rather than for the chip because Joust's `src/sound.c` already has
`psg_read`/`psg_write` meaning *the `Giaccess` path*; the two are precisely what the mixed-path guard
keeps apart, and a header declaring a clashing name would be a compile error waiting for the first
file that includes both. A read of an undeclared register on this side — or a call naming a register
number the chip does not have — tallies through the existing **`os_refused()`**, not a new counter,
so `harness.differential`'s unconditional `_vet_no_os_refusal` already throws the case away. That
closes the model's refusals on **both** sides, which is the property "Refusing on ONE side is a false
green" (above) exists to state: the oracle's run is rejected, and a candidate that sails past on an
invented value is rejected too.

The candidate has no select of its own — it selects and accesses in one call — so the *latch*
refusal has no mirror here, and needs none: a reconstruction cannot express a read of a register it
did not name.

### The YM2149 edge semantics: what is modeled, what is refused, what is not modeled

| the access | answer | why |
| --- | --- | --- |
| byte write `$ff8800` (select), value `0x00..0x0f` | latch it; mark the latch known | the ST decodes four bits into a register number |
| byte write `$ff8800` (select), value **above `0x0f`** | **REFUSED** (`osh_psg_unmodeled`), latch untouched | this used to mask the value down to four bits, on the claim that "the upper bits are ignored — Hatari's model". That claim does not survive checking: the YM2149 requires the select byte's upper nibble to be **zero**, and the ST's incomplete decoding is about the *address*, not the *value*. Masking is also asymmetric — the oracle would silently select register 14 for `move.b #$1e,$ff8800` while the candidate's `psg_port_write(0x1e, …)` refuses the same call — so both sides refuse. No input binary writes one; the day one does it needs a model, not a mask |
| byte write `$ff8802` (data) | store + log a `WRITE` event | |
| byte read `$ff8800`, register **known** | its contents; log a `READ` event | what the chip does: the select port reads the selected register back |
| byte read `$ff8800`, register **unknown** | **REFUSED** (`osh_psg_unseeded`) | the value is an input; inventing it is the false green above |
| byte read `$ff8800`, **nothing selected yet** | **REFUSED** (`osh_psg_no_select`) | there is no latched register to answer from, and the latch's initial `0` is `shim.c`'s convention rather than the chip's state. Not seedable — see "Modeled" above |
| byte read `$ff8802` | **REFUSED** (`osh_psg_unmodeled`) | the data port is write-only; the chip reads back through `$ff8800`. Answering it would invent a port the hardware does not have |
| any 16/32-bit access to the block, either direction | **REFUSED** | only the byte protocol is modeled; a wide access also decodes odd addresses the model does not |
| any odd alias (`$ff8801`/`$ff8803`) or mirror up to `$ff88ff` | **REFUSED** | the ST decodes the chip incompletely; the mirrors are not modeled, and tallying them is what stops one from silently disarming the mixed-path guard |
| register **widths** (R1/R3/R5/R13 are 4-bit, R6/R8/R9/R10 5-bit) | **NOT modeled** — a read-back returns the whole byte that was written | the real chip returns 0 in the unimplemented bits. Storing the byte unmasked is the choice that cannot silently corrupt a reconstruction: for every value a game actually writes the two agree, and a case that wants the chip's answer can seed it. A register-width table would be a second model to get wrong, and no input binary exercises the difference |
| ports A/B (R14/R15) read-back | the last value written | on the ST both ports are **outputs** (port A = floppy drive/side select, port B = printer data), and an output port reads back its own latch. That is what both drive-select routines depend on. A port configured as an INPUT would read pin state, which this models not at all — and nothing sets R7's direction bits to make one |
| the select latch itself | not compared between the sides | the candidate's API selects and accesses in one call, so a select with no access is not expressible there. A driver whose *only* effect were leaving a register selected would be unmodeled |
| a data write with **nothing selected** | stored into register 0 (the latch's placeholder), logged as such | unlike a *read*, this has an unambiguous comparable answer on both sides: the candidate names its register explicitly, so a reconstruction that meant a different one diverges in the ledger. It is a fabrication about the real chip and is recorded here as one — no game does it, and refusing it would buy a guard with no witness |

### One chip, three files — how they relate

* **`OS_PSG_REGS` (`0x610`, in the image)** — the `Giaccess` path's file, Phase 3. Unchanged and
  **not merged** with this one. It is in the image on purpose: `os_giaccess()` is shared verbatim by
  the shim and by a reconstruction, so its writes are ordinary diffed memory and cost no ABI at all.
  Merging the two would take that state off-image and turn a free property into a mirrored one.
* **the direct file (this phase, off-image)** — fed by `$ff8802` writes only.
* Because neither sees the other's stores, **the mixed-path guard stays exactly as it was**: a run
  that uses both is refused. This phase gives the direct file readable contents, which is a different
  question from the two files agreeing. Merging them is what would retire the guard, at the cost
  above; that trade is recorded here and not taken.
* **the audio-capture file** — was a third copy; it is now **the same array**, and the mode is a
  documented *relaxation* of this model (an unknown register reads `0`, an unselected latch likewise,
  and the file and latch span runs).
  Every pin the mode had holds unchanged (`projects/wonderboy/recreate/test/test_audio_capture.py`,
  13 cases, and Joust's arming case): the read-back, the cross-run persistence,
  `audio_reset()` as the only clear *mid-capture*, re-arming an armed capture as a no-op, a served
  read still arming the mixed-path guard, and `osh_psg_dropped`'s truncation report. Two consequences
  of sharing the array had to be closed rather than documented:

  * a run made while the mode is OFF leaves its own registers **and its own select latch** behind, so
    **arming from off now clears both** — otherwise a capture armed bare would start on whatever the
    last differential left, and under `pytest -n auto` on which case that was is not reproducible.
    The latch half was measured, not theorised: select register 10 in a run, arm, write the data port
    bare, and the byte landed in 10 — a capture writing a register it had never named.
    `emu.audio_capturing()` resets anyway; this makes structural what was a convention, and leaves
    the idempotent-re-arm pin untouched (that one re-arms an *already-armed* capture);
  * the mode being oracle-global means a run can be served its fabricated answers without asking, so
    **`emu.run` refuses a run made under the mode that did not opt in** — `emu.audio_capturing()` is
    what declares the intent, and every existing capture already goes through it. Without that, a
    block that raised on its way out, or an extractor sharing the process, silently turns later runs
    into capture runs; `harness.differential`'s `_vet_audio_capture_off` covers only the cases that
    go through the harness, and most PSG cases call `emu.run` directly.

### Why the model is always on and only the SEED is opt-in

The seed follows `stop_pc`/`poison`: a per-run keyword on `emu.run` and `harness.differential`. The
*model* is not switchable, and deliberately:

* with no seed it behaves exactly as Phase 3 did — every read of a register nothing wrote is refused
  — so there is no second behaviour for the same instruction stream, and nothing to forget to arm;
* the one thing it adds unconditionally is a read-back of a register **this run wrote**, which no
  case can be wrong about: the chip returns the last value written, and both sides compute it from
  the same write;
* a flag would have to be threaded through every case that merely *might* reach the PSG, and the
  cost of forgetting it is a refused run either way — so the flag would buy nothing and could only be
  set wrongly.
* A `project.toml` waiver was considered and is not needed: nothing about the model is a claim about
  the game, so there is no claim to enforce per run.

### What is pinned, and what is not

**The model** is pinned kit-side by [`test/test_psg_model.py`](test/test_psg_model.py) and its
`psg_model_probe.c`, which drives **both** implementations in one process: a seeded read served; an
undeclared read refused **on both sides**; a read with nothing selected refused in its own tally, and
a seed shown not to help it; a select above `$0f` refused on both sides; a read-modify-write reading
back its own write; the ordered ledger byte-identical over a recorded write-only sequence — and its
write projection asserted separately per case, which is the regression pin every `psg_writes()`
consumer rests on; the file **not** surviving a run; the capture mode's relaxations plus the
arm-from-off clear of **both** the register file and the select latch. And the negative control the
house style demands — three mutant candidates, each caught while touching no image byte at all:

* one that **skips the write**, caught by both off-image surfaces;
* one that **ignores the read-back**, likewise. This is what a fabricated `0` would have hidden:
  `0 | $3f` and `read | $3f` agree, so it would have been green;
* one that **reads the wrong register** — the transposed RMW. Its register file, its known mask and
  its whole *write* stream are a correct run's, exactly; the ledger's read entry is the only thing
  that separates them, which is the case that put reads in the compared stream.

**The plumbing** — `harness.differential`'s own PSG code, which the kit could not previously reach at
all — is pinned by [`test/test_psg_differential.py`](test/test_psg_differential.py). It builds a
miniature project in a temp directory (a `.PRG` holding the same RMW in 68000 code, and a candidate
`.so` from `test/kit_candidate.c` plus `src/`) and runs real `differential()` calls through it: the
green case, then `_vet_psg_state` and `_seed_candidate_psg` each stubbed out via `monkeypatch` and
shown to be load-bearing (with the comparison gone, the skips-the-write mutant passes the entire
differential clean), the missing-ABI arm refusing **by name**, and both arms of the two-doors guard.

**Mutation sweep.** The four load-bearing model lines (serve an unknown register; skip the per-run
re-seed; drop the candidate's known check; stop storing writes into the file) redden 4/4.

**Not pinned.** The ledger's **cap** arm — a run of `OS_PSG_LOG_MAX` accesses — has no case: reaching
it needs 4,096 register accesses in one run, and nothing that exists does that. Ports A/B read back as
outputs because nothing configures them as inputs, so the input-pin behaviour the table calls "not
modeled at all" is unreachable rather than untested. The register-**width** masks are likewise
unexercised: no input binary writes a value the real chip would truncate.

**One trap for the next game, stated because nothing enforces it.** `_vet_psg_state` runs on every
`differential()` call and compares the candidate's `psg.h` ledger — so a candidate that emits its
register stream through a *project-specific* ABI has an empty one. BuggyBoy is exactly that
(`g_REFRESH`'s out-params), and it stays green only because its PSG-reaching cases drive `emu.run`
plus the out-params by hand rather than going through `differential()`. Converting them would fail
with a stream mismatch that is about the ABI, not the reconstruction. The fix, when someone does it,
is to move that candidate onto `psg_port_write()` — not to add a waiver. The same warning is
recorded where a BuggyBoy session will meet it, in
[`projects/buggyboy/recreate/README.md`](../../projects/buggyboy/recreate/README.md)'s "Harness gaps"
section.

## Phase 7 — the SEEDED HARDWARE READ MODEL (a named set of I/O bytes)

Phase 6 established the distinction this phase extends: **a seed is a declared case input, not a
fabrication.** There it was the YM2149's register contents. Here it is a small named set of hardware
BYTES outside the chip — `$fffa01` (the MFP GPIP), `$ff820a` (the shifter's sync mode) and the two
video-address-counter bytes `$ff8207`/`$ff8209` — served from a file the case declares, recorded in
an ordered ledger both sides keep, and refused when nothing declared them.

The first two **steer a branch**, which is the shape the phase was built for. The counter pair is the
same false green with a **wider blast radius**: those bytes are summed into an arithmetic result
(Wonder Boy's `$51ac` hashes them into a 1..4 draw), so a fabricated `0` does not merely pick the
wrong side of a branch — it collapses the whole draw to a constant, and both cores then agree on it.

### The defect it is built on, which shipped

Every other off-image read answers `0`, identically on both sides, so the differential agrees with
itself on whatever that `0` implies. For a value that is merely *stored*, that is incompleteness. For
a value that **steers a branch**, it is a green run whose behaviour is wrong on the machine — and
this workspace has shipped one. `projects/wonderboy/recreate/PORTABILITY.md` records the pattern
verbatim, in the game's own code at `$17c74`:

```
$17c7e  btst.b #7,$fffa01     ; MFP GPIP bit 7 = monochrome-monitor detect
$17c86  bne.s  $17c90
$17c88  move.b #$48,2274(a3)  ; -> tempo := $48   (the MONO branch)
$17c90  btst.b #1,$ff820a     ; the 50/60 Hz sync register — BuggyBoy's exact register
$17c98  bne.s  $17ca0
$17c9a  move.b #$2b,2274(a3)  ; -> tempo := $2b
```

Both bytes read `0`, so bit 7 clear says *monochrome* and bit 1 clear says *60 Hz*: the mono branch
is taken unconditionally, and both sides store `$48`. **This is the `$ffff820a` defect that was
invisible to BuggyBoy's entire differential and only surfaced on real hardware** (see the memory note
"BuggyBoy real-hardware TOS gotcha": a hardware READ the oracle answers `0` for is invisible to the
whole differential, by construction). It is present in Wonder Boy before a line is ported.

> **So the byte a branch reads is an INPUT of the run, not a consequence of it** — the same governing
> rule as Phase 6's register contents and as a poked keystroke: the harness supplies it identically
> to both sides, or the model refuses to run.

### Modeled

**A file of bytes, one per modeled address**, plus a `known` mask saying which of them the case
declared. `include/os.h` owns the set — `OS_HW_MFP_GPIP`, `OS_HW_SHIFTER_SYNC`,
`OS_HW_SHIFTER_VCOUNT_MID`, `OS_HW_SHIFTER_VCOUNT_LOW`, their slot numbers, `os_hw_slot()` and
`os_hw_volatile_slots()` — because both sides decode it: `shim.c` from a bus address, `src/hw.c`
from the constant a reconstruction spells.

Each slot carries a **VOLATILE flag**, and it is the criterion the counter pair is admitted under
rather than a note about it. A STATIC byte (the monitor detect, the sync mode) is one the machine
answers the same way every time, so a run may read it as often as it likes: one declaration
describes every read of it, and how many there were is no part of what the case claimed. (Nothing
ported re-reads one today — the tempo head reads each of its two bytes once. What does re-read
`$fffa01` is an FDC poll, and that is the shape the non-goal below excludes for its own reason.)
A VOLATILE one (the two counter bytes) is a value the
machine changes on its own, and a per-run constant describes it for exactly ONE read: the second read
would be served the first read's byte, which the counter cannot have held twice. `os.h` derives the
mask from the same one table as the addresses, so **a slot added there is STATIC unless it says
otherwise** — the conservative direction, since a slot wrongly called volatile refuses runs that are
fine while one wrongly called static serves a fabrication. Five rules:

* **a byte read of a modeled address, declared** → the declared byte, plus a `READ` entry in the
  ordered ledger. `harness.differential` compares that stream against the candidate's;
* **a byte read of a modeled address, UNDECLARED** → served `0` — exactly what it was served before
  this phase existed — recorded in `osh_hw_unseeded()`, and **still ledgered**, since a read that
  happened is a fact both sides must report the same way. The *refusal* is a differential's, not
  `emu.run`'s; the next section is entirely about that;
* **a SECOND byte read of a VOLATILE address in one run** → served the same declared byte as the
  first, and recorded in `osh_hw_reread()`, tallied on the read that *repeats* so the mask names the
  slot a case must do something about. Refused in a differential, and **not fixable by declaring
  more**: one number cannot be two. The remedy is the case's shape — end it before the second read,
  or split it into two runs each declaring what the counter held then. A STATIC address is exempt,
  and that exemption is a statement about the machine rather than a softening: repeated reads of one
  really are described by a single declaration, so refusing them would refuse correct runs;
* **a 16/32-bit read taking a modeled address in** → recorded (`osh_hw_wide()`), never served. A
  wider read also takes in the neighbouring MFP/shifter registers, which the model would have to
  fabricate as `0` — the same false green one address over. The overlap test is a span test
  (`os_hw_slots_touched()`, in `os.h` beside the table so the whole decode has one home), so a long
  read straddling *into* the byte from below is caught too. It is a slot MASK, like the two above
  and for their reason: the refusal has to name the address, not the whole set;
* **a WRITE to a modeled address** → **dropped**, exactly as every other hardware write off the PSG
  ports is dropped. Phase 7 models what these addresses *answer*, not what storing to them does, so
  there is nothing for a reconstruction to mirror and `hw.h` has no `hw_write8()`. What *is* recorded
  is that the write happened, because a later READ of the same address is then served the byte the
  case declared the machine held **on entry** while an instruction of this very run has replaced it.
  That combination — `osh_hw_stale()` — is refused, with its own message, because no declaration can
  fix it. This is a live case, not a hypothetical: Wonder Boy writes `move.b #2,$ff820a` at `$f91c`
  and reads bit 1 of the same address at `$17c90`, so any whole-frame run covers both.

**The seed is the case's, and it is per-run.** `emu.run(..., hw_seed={0xfffa01: 0xb0})` /
`harness.differential(..., hw_seed=…)` install it before **every** run — an empty one included, so a
seed cannot leak from the previous case — and the file is rebuilt from it at the top of each
`osh_run` *and* each `osh_run_bench` (both go through `enter_from_reset`). Declaring an address
outside the modeled set is a `ValueError` rather than a silent no-op: a case that seeds `$ff8609`
would otherwise install nothing, read a fabricated `0`, and pass while testing the read it meant to
declare not at all.

### The divergence from Phase 6: the refusal fires in `differential()`, not in `emu.run`

Phase 6's model is **always on**: an undeclared PSG read sinks the run inside `emu.run`, for every
caller. Phase 7's does not. An undeclared hardware read is *served and recorded*, and only
`harness.differential` refuses. **This is deliberate, and it is the one asymmetry between the two
phases.** Two reasons:

* **a bare `emu.run` is not a verification.** It is how this workspace drives a game's relocator, its
  Copylock and its bootstrap (`projects/wonderboy/recreate/test/test_copylock.py`,
  `test_bootstrap.py`) — code whose hardware reads are nobody's enumerated list, and which no
  reconstruction is being compared against. An always-on refusal would sink those runs to close a
  false green they cannot have: nothing is being verified, so nothing can be falsely verified.
  Zero regression for them was a requirement of this phase, not a hope;
* **a false green needs something being verified.** That is exactly what a differential is: the
  candidate and the oracle agreeing on a branch that a fabricated `0` chose for both of them. The
  refusal is placed precisely where that can happen, and nowhere else.

The split has a second consequence worth stating: the **wide-read** mask is recorded on every run
but raised on in two different places — under audio capture by `emu.run` (an extractor has no diff to
catch it and no second chance), and in a differential by `_vet_hw_reads_are_declared`. Off both, it
stays the ordinary off-image `0` a bare run has always been given.

One thing the split does **not** cover, and deliberately: the read ledger's own **truncation**.
`osh_hw_dropped()` is a cause in `emu.run` for *every* caller, exactly like the PSG ledger's, because
that is not a question of a fabricated byte — it is `hw_events()` reporting a truncated stream as a
complete one, and a bare-run reader has no diff to notice. It is reachable: a poll loop on `$fffa01`
does 4,096 reads in a few thousand instructions.

**The four refusals are tested narrowest first** — stale, then wide, then the volatile re-read, then
undeclared. One read can set two masks at once (a read of an address the run wrote *and* never
declared sets both; a second read of an undeclared volatile byte sets both), and
reporting that one as "declare it" sends the reader to add a `hw_seed` and hit the un-seedable
refusal on the next run. That ordering is a case, not a comment.

### The audio-capture mode is now a SEED over this model

The mode used to answer these two addresses from a `switch` of its own in `m68k_read_memory_8`. It no
longer has one: `hw_enter_run()` installs the **capture profile** — a 50 Hz colour ST, GPIP bit 7 set
with the two active-low interrupt lines idle, sync bit 1 set — through the same code path that
installs a case's seed. So "what the mode serves" is by construction "what a case declaring those
bytes serves", and the two cannot drift.

Three properties follow, and each is a case in `test/test_hw_model.py`:

* the profile is installed **per run**, not at arming — so disarming the mode is enough: the very
  next run is back on the case's own declaration, with no reset call, and the profile cannot leak
  into a differential;
* while armed, the profile **wins** over a case's declaration — which is why `emu.run` refuses a
  `hw_seed` passed under the mode outright rather than installing one that would be silently ignored;
* `harness.differential`'s veto on the mode (`_vet_audio_capture_off`) is **unchanged and still
  load-bearing**: under the mode a green would mean the reconstruction agrees with `shim.c`'s
  declared machine, not with the game's.

The fold is inert with respect to the extraction it exists for: re-running
`projects/wonderboy/tools/extract_audio.py` after it produces all 87 files (17 songs + 26 SFX, `.ym`
and `.wav`, plus the manifest) **byte-identical** to the committed `out/audio`.

### The candidate side

`include/hw.h` + `src/hw.c` — linked into every candidate by `kit.mk`, exactly like `psg.h` and the
refusal tally:

```c
uint8_t hw_read8(uint32_t addr);   /* addr is an os.h OS_HW_* constant */
```

A read of a declared address is served and ledgered. An **undeclared** one, or an address outside the
modeled set, tallies through the existing **`os_refused()`** — not a new counter — so
`harness.differential`'s unconditional `_vet_no_os_refusal` already throws the case away. That closes
the refusal on **both** sides, which is the property "Refusing on ONE side is a false green" exists
to state.

One asymmetry inside the candidate, deliberate: an *undeclared modeled* address is logged (the oracle
logs its own, so a stream missing it would diverge for the wrong reason), while an address **outside
the set** is not (the oracle records nothing for it either).

There is no masking to the 24-bit bus on this side. The oracle masks because it decodes a real 68000
access; a reconstruction spells the address itself, and `0xfffffa01` reaching `hw_read8` is a mistake
worth a refusal rather than a silent equivalence.

### The edge semantics: what is modeled, what is refused, what is not modeled

Rows are keyed by **the modeled set** rather than by one address, because the set grows: it is
`$fffa01`, `$ff820a`, `$ff8207` and `$ff8209` today, and `os.h`'s `OS_HW_*` table is the list.

| the access | answer | why |
| --- | --- | --- |
| byte read of a **modeled** address, **declared** | the declared byte; log a `READ` entry | the byte is the case's input, exactly as a PSG register's contents are |
| byte read of a **modeled** address, **undeclared** | `0`, recorded in `osh_hw_unseeded()`, still logged | served so a bare `emu.run` is unchanged; recorded so `harness.differential` can refuse. See the divergence above |
| **second** byte read of a **VOLATILE** address in one run (`$ff8207`/`$ff8209`) | the declared byte again, recorded in `osh_hw_reread()` | a seed is a per-run CONSTANT and the counter is not: the second answer would be one the address cannot have held twice. Refused in a differential; **not seedable** — split the case |
| second byte read of a **STATIC** address (`$fffa01`/`$ff820a`) | the declared byte again, and nothing recorded | the machine's own answer really is the same every time, so one declaration describes both reads and the run is correct |
| byte read after **this run wrote** the address | `0`/the declared byte, recorded in `osh_hw_stale()` | the model drops hardware writes, so the seed describes a machine the program has already changed. Refused in a differential; **not seedable** |
| 16/32-bit read taking one in | **REFUSED** in a differential (`osh_hw_wide()`, naming the address); under capture `emu.run` sinks the run | the neighbouring MFP/shifter registers would have to be fabricated as `0` |
| **write** to a **modeled** address | dropped, noted | a hardware write has always been invisible; making it visible would mean every already-ported reconstruction that writes the address had to mirror it, for a value nothing reads back |
| any **other** hardware address, read or write | unchanged: `0` / dropped, silently | the model is a NAMED SET. Serving an address nobody declared would be the fabrication over again under a new name |
| the rest of the GPIP byte (parallel busy, ring indicator, the STE DMA line) | **whatever the case declares** | the model serves a byte, not a machine. A case declaring `$b0` is declaring those bits `0`; the two bits games branch on are the reason the address is in the set at all |

### The explicit NON-GOAL: the FDC/DMA registers (`$ff8604`+)

They are **not** in the modeled set and Phase 7 does not put them there. The reason is structural
rather than a matter of effort, and stating it exactly matters now that the modeled set contains a
counter: **the criterion is not "the value never changes on the machine" — it is that a per-run
constant can describe any byte read AT MOST ONCE per run.** A byte that changes between accesses is
perfectly describable if the run only looks at it once, which is why the shifter's video counter is
admissible: `$51ac` reads `$ff8207` once and `$ff8209` once, and one read of one address is exactly
what one declared byte is. The criterion is also *enforced* rather than argued — the two counter
bytes are flagged VOLATILE, and a second read of one in the same run is a refusal.

An FDC poll fails that criterion by its nature, not by bad luck. `fdc_wait_irq` (`$62da`) polls
`$fffa01` bit 5 *until it changes*; `fdc_wait_irq_bounded` polls the DMA address counter at
`$ff8609`/`$860b`/`$860d` *until it advances*. **Reading many times per run is the whole of what a
poll loop is**, so there is no case shape that reduces one to a single read: declaring a status
register either terminates the loop immediately (which is what a `0` already does) or hangs it
forever. Modeling those needs a *transaction* model — what the drive is doing between accesses —
which is a different thing from this one, and it should arrive with the evidence for what the
sequence really is.

Note the consequence for `$fffa01`, since it is in the set: a case *may* declare it with bit 5 set,
and an FDC wait loop given that will spin until `max_insns`. That failure is loud (`emu.run` raises
"did not reach rts"), not silent, so the address earns its place for the bit-7 branch it was added
for.

### The honest limit

**What this pins is "given byte X, both cores agree", not "a real ST serves X".** The declaration is
the case's claim about the machine, and the model's whole contribution is to make that claim
*explicit and shared* instead of implicit and fabricated. A case that declares `$fffa01 = 0xb0` has
stated "a 50 Hz colour ST"; whether the machine the game shipped on was one is a documented claim
about hardware, not a differential result.

That is the same standing arrangement BuggyBoy's remaster runs under — its colour engine and its
50/60 Hz music branch are pinned by the differential *given* the machine's answers, and the answers
themselves are documented facts re-checked on real hardware. Phase 7 does not close that gap; it
moves the fabrication out of `shim.c` and into a place a reader can see, argue with, and correct.
Before it, the wrong branch was taken silently on both sides. After it, a case that does not say
which machine it means is **refused**, and one that says the wrong thing is wrong *in writing*.

### What is pinned, and what is not

**The model** is pinned kit-side by [`test/test_hw_model.py`](test/test_hw_model.py) and its
`hw_model_probe.c`, which drives **both** implementations in one process (84 cases, as pytest
collects them): a declared read
served and ledgered; a declaration not consumed by one run and not surviving one either; an
undeclared read served `0` **and recorded** on both sides; declaring one address not declaring the
other; two reads compared **in order**; the three wide-read shapes recorded by SLOT and unledgered;
the write-then-read case recorded separately from a missing declaration, and a write nothing reads
back left alone; the bench starting from the case's declaration with its own empty ledger; the
capture fold measured against `osh_hw_capture_profile()` rather than against restated constants, plus
its override and its non-survival. Every wide-read case uses an address a 68000 can really execute a
word/long read at — the kit builds Musashi with `M68K_EMULATE_ADDRESS_ERROR` off, so a case planted
at an odd address would stop measuring the refusal the day that moved. And the negative controls,
each caught while touching no image byte:

* a candidate that **reads the wrong modeled address**, declared to the same byte — its value, its
  declared file and its (empty) image effect are a correct run's exactly;
* a candidate that **never reads and hardcodes the answer**, which is what a port written against a
  fabricated `0` looks like once the byte is declared;
* a candidate that **serves an address outside the set**, which must refuse *and* stay out of the
  ledger.

**The plumbing** is pinned by [`test/test_hw_differential.py`](test/test_hw_differential.py) (19
cases), through the shared miniature project in `test/kit_smoke_project.py` — whose `.PRG` holds the
tempo selector's two reads as real 68000 code: the green case; the undeclared refusal naming both
addresses and the `hw_seed=` to add; **the same run through `emu.run` served rather than refused**,
which is the divergence stated as a case so a "fix" cannot regress the probe suites; `_vet_hw_state`
and `_seed_candidate_hw` each stubbed out via `monkeypatch` and shown load-bearing (with the
comparison gone, the wrong-order mutant passes the entire differential clean); the declared-byte
comparison shown to catch what the read stream cannot — a candidate handed a *different declaration*
from the oracle's (through the REAL `_seed_candidate_hw`, captured before the patch, so the control
cannot drift from the plumbing), whose streams still match entry for entry; the missing-ABI arm
refusing **by name**; the stale and wide refusals, each naming its address, and stale winning over
undeclared when one read is both; **the VOLATILE re-read refused and its STATIC control served** —
a `.PRG` routine that reads `$ff8209` twice against a faithful candidate that reads it twice too, so
that with the harness's volatile branch removed every surface agrees and the differential comes back
green (measured: the case then reds with DID NOT RAISE), beside the same shape on `$fffa01`, which
must stay green or the tempo selector itself becomes unrunnable; a declaration the run never reads
left alone; a case touching the
model not at all left green; the smoke `.PRG`'s address literals pinned equal to `emu.HW_ADDRS`; and
both guards around the capture fold.

Two properties of the *diagnostics* are cases rather than conventions, because a remedy string is
this phase's whole surface for the reader. The stale refusal renders the case's seed as a reader
would type it (`{0xfffa01: 0xb0}`, not Python's decimal `{16775681: 176}`) and prescribes rather than
contradicts when there is no seed at all; and a CANDIDATE-side refusal names the hardware address,
since `os_refused()` is one tally shared by every refusing helper and the bare count sends the reader
hunting for a missing `Bconstat` gate.

**The suite's own seed is deliberately not the capture profile's bytes.** Seeded with `$b0`/`$02`,
every green case would stay green if the mode's declaration leaked into a disarmed run; seeded with
`0`, if the seed were never installed at all. The only two cases that involve the profile read it
from `emu.hw_capture_profile()` — the same rule `hw_model_probe.c` states for its own
`DECLARED_BYTE`.

**Mutation sweep — 18/18 caught**, each with the oracle force-relinked (the `.so` removed, never
merely touched): serve-without-logging; log-without-serving; the seed not reinstalled per run; the
capture profile diverging from the fold, and its known-mask widened to every slot; the undeclared,
stale, wide and write masks each dropped; the span test off by one; the refusals reordered so
"declare it" wins over the un-seedable one; the declared-byte comparison deleted; the candidate-side
refusal losing the address it names; a key dropped from a table row; the candidate serving an
undeclared byte, not resetting its ledger, logging an unmodeled address, and dropping a refused read
from its ledger.

**The volatile flag's own mutant makes it 19**, measured when the flag landed: `harness`'s volatile
branch disabled — a Python-side mutant, so no relink is involved — after which
`test_a_second_read_of_a_volatile_address_is_refused_and_not_seedable` reds with DID NOT RAISE
rather than with a stream mismatch. That distinction is the finding: the run was otherwise green in
every surface a differential has, which is exactly the false green the flag closes. The other 18
were not re-run for it.

That last one is why the narrative tests here are a short list. Seven of them re-asserted a table row
in prose and were deleted, their arguments moved into the row's own comment; the sweep is what says
the rows still carry the coverage, and it does. What survives pins a relation BETWEEN cases (the two
sides agreeing; a mutant separated from a correct run; what a capture was served, against the profile
it installs) or a fact about the SOURCE rather than about a run (the slot numbers against `os.h`, the
capture profile's known-mask against the bytes it has) — plus one that closes the table's own blind
spot, since a case may claim a SUBSET of the keys the probe prints and a key claimed by nothing would
otherwise be measured by nothing.

**Not pinned.** The ledger's **cap** arm has no case, for `OS_PSG_LOG_MAX`'s reason: it needs 4,096
modeled reads in one run, and nothing that exists does that (an FDC poll loop could, which is why the
cap is sized like the PSG's rather than like Dosound's).

Two entries that used to stand here are now closed, and are recorded as closed rather than deleted,
since "no consumer" was the honest state this phase shipped in. **The model has consumers**: Wonder
Boy's `$17c74` tempo selector declares `$fffa01`/`$ff820a`, and its `rng_next` declares `$ff8209` —
the branch shape and the arithmetic shape, one project. And **`tools/hw_portability.py` prices the
modeled set as `T2 SEEDED_READ`**, not as the `T4 HW_READ` it priced them at when only the audio
capture answered them; the census pins `HW_SEEDED_ADDRS` and `OS_HW_NSLOTS` against `os.h`, so a
fifth modeled byte cannot be added while the classifier goes on under-counting it.

## What a candidate must mirror (cross-side ABI)

Everything the model reads or writes in the image is shared by construction — a reconstruction that
calls `os_bconstat`/`os_bconin`/`os_crawio`/`os_giaccess`/`os_random`/`os_fopen`/`os_fcreate`/
`os_fread`/`os_fwrite`/`os_fclose` from `include/os.h` agrees with the oracle byte for byte and has
nothing to mirror by hand. Two things are **not** in the image and must be matched explicitly:

| what | where the oracle keeps it | what the candidate must do |
| --- | --- | --- |
| XBIOS `Dosound(A0)` list pointers | `shim.c`'s `g_dosound_arg` ledger | export the `g_dosound*` ledger ABI (README.md); `harness.differential` compares them |
| direct `$ff8800`/`$ff8802` PSG accesses, **reads included** | `shim.c`'s `g_psg_kind`/`g_psg_reg`/`g_psg_val` ledger | emit the same ordered `(kind, reg, val)` stream — call `psg_port_write()` / `psg_port_read()` from `psg.h` (BuggyBoy predates it and emits through `g_REFRESH` out-params instead) |
| the YM2149's register contents, which a read-back returns | `shim.c`'s `g_psg_file` + its known mask | `psg_port_read()`/`psg_port_write()` keep the same file; `harness.differential` compares it, and the case seeds both sides with `psg_seed=` (Phase 6) |
| reads of the modeled hardware bytes `$fffa01`, `$ff820a`, `$ff8207`, `$ff8209` | `shim.c`'s `g_hw_log_slot`/`g_hw_log_val` ledger + `g_hw_file` | emit the same ordered `(slot, val)` stream — call `hw_read8()` from `hw.h` with an `OS_HW_*` constant; the case declares both sides' bytes with `hw_seed=` (Phase 7). A VOLATILE one (`$ff8207`/`$ff8209`) may be read at most ONCE per run: a second read is refused, and the remedy is the case's shape — end it before the second read, or split it into two runs |

`OS_SUPER_TOKEN` is not off-image state but it is still a shared value: a reconstruction of a
function that calls `Super` must return the same constant, since the program can store it into the
image where the diff compares it. Using `os_super()` from `os.h` gets that for free.

## Four limits the input layer found

Recorded here because each one is a property of the *model*, not of Joust: any game's
reconstruction meets them, and none was written down before.

**1. A poked constant only survives if the routine does not initialise it first.** State-level
poking (the governing rule) puts the value in the image *before* the run, so a routine that clears
its own input wipes it on entry and the poke buys nothing. Both of Joust's IKBD readers do exactly
that — `read_joysticks` (`0x11d9a`) and `hiscore_joystick_input` (`0x14538`) both `clr.l
ikbd_packet` before sending the "interrogate joysticks" command and spinning on the reply. A staged
packet is therefore erased by the routine itself and the spin never ends. The only way in is to
enter the oracle **at the wait loop** with the packet already staged, which is what
`hiscore_joystick_input` does (verified from `0x1454e` onward) and what `read_joysticks` does too
(rotated at `0x11db0`; the `control_player` it goes on to call is itself verified). So: check
whether the routine writes its own poked input before assuming state-level modelling reaches it.

**2. The `Fopen` → `Fcreate` fallback is unreachable by construction.** `os_fcreate` *is* `os_fopen`
plus a truncation, so for any one name both succeed (staged) or both are refused (not staged) —
there is no image in which `Fopen` returns an error and `Fcreate` then returns a handle. Every
program's "open it, else create it" idiom therefore has its create arm reproduced but unverified,
and both `< 0` tests with it. Pinned by
`projects/joust/recreate/test/test_input.py::test_fcreate_fallback_is_unreachable_under_the_model`.
Making it reachable would mean letting `Fcreate` invent staging space for a name the harness never
declared, which is the fabrication the model exists to refuse.

**3. `Pterm` does not stop the run — and misreports itself.** It is unmodeled (below), so the shim
counts it and then *resumes* the caller with a fabricated `D0 = 0`, because the trap dispatch has
one exit path. Execution runs on past a call that should never return, until the instruction cap.
Worse, the run can no longer stop at the sentinel even in principle: `Pterm`'s own
`move.w #retcode,-(a7); move.w #$4c,-(a7)` lands on the sentinel long itself (Joust's quit path
reaches `trap #1` with A7 back at `STACK_TOP + 4`), leaving `00 4c 00 00` where `00 00 00 02` was —
the selector in the sentinel's **high word**. And `emu.run` tests `reached` *before* it tests the
unmodeled causes, so what comes back is `did not reach rts within 200000 instructions` rather than
the honest `unmodeled OS behaviour`. Diff such a path at a **checkpoint `stop_pc`** placed before
the trap; with one set, the same run reports the honest cause.

**4. Model writes bypass the write-set, so `poison` never checks them.** The `os_*` helpers reach
`g_mem` directly rather than through `m68k_write_memory_*`, so nothing calls `logw` for them:
`os_bconin` clearing `OS_CON_PENDING`, `os_fwrite` filling a staged file and `os_gem_trap` filling
`intout` are all **absent from `info["writes"]`**, which holds the 68000's own stores only. The
image diff still covers those bytes — they are ordinary image state on both sides, which is the
whole point of sharing `os.h` — but two things follow. A test that wants to assert on model state
must read the oracle's final image, not its write set (`test_input.py::_oracle_final`). And
`harness.differential(poison=True)` poisons exactly the oracle's write set, so a byte only the
*model* wrote is never canaried: a candidate that omits it can still pass the attribution check by
landing on a value the input image already held.

## Still unmodeled (an honest raise is the right answer)

`Pterm` (0x4c) and `Dgetdrv` (0x19) both appear in Joust and are **not** modeled. `Pterm` ends the
process and never returns, so there is no post-state to diff; `Dgetdrv`'s answer is a property of
the machine the harness does not have. `Pexec`, `Fseek`, GEM opcodes outside the three in
`os_gem_trap`, and every BIOS selector but the two above are in the same position. They raise.
