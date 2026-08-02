# recreate_kit — the shared differential harness

The game-agnostic half of a `projects/<game>/recreate/` reconstruction: load a GEMDOS `.PRG`
into a flat image, run the original 68000 code under Musashi, run the reconstruction's C on the
same image, and diff. Every game-specific part (the `src/` cores, `include/addrs.h`, the
`test/test_*.py` battery) stays in the project. How the harness works — and why differential
testing rather than byte-matching — is documented in
[`projects/buggyboy/recreate/README.md`](../../projects/buggyboy/recreate/README.md), the
worked reference example.

```
tools/recreate_kit/
├── project.py        bind one recreate/ dir to the kit (reads its project.toml)
├── harness.py        the differential driver (differential/report/make_image/stage_files,
│                     plus the model-state pokes console_key/psg_regs)
├── os_map.py         the harness-poked input block + the overlap arithmetic its guards ask for
│                     (shared by harness.py and oracle/emu.py; importable with nothing built)
├── kit.mk            shared make rules: candidate .so, Musashi oracle, `test`/`venv`/`oracle`/`clean`
├── include/          machine.h (big-endian image accessors)  os.h (deterministic TOS trap model)
├── src/              C linked into EVERY candidate .so: dosound_log.c (the Dosound ledger below)
├── oracle/           loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (callbacks)
│                     isa_conformance.py  tos_probe.py   musashi/ + build/ (gitignored)
├── test/             the kit's own regression tests (`make test` here; no project needed)
├── TRAP_MODEL.md     what each modeled TOS trap does — and what it deliberately does NOT capture
└── Makefile          runs test/
```

## Adding a game

1. Write `projects/<game>/recreate/project.toml`:

   ```toml
   name       = "<game>"
   prg        = "../bin/<GAME>.PRG"     # relative to recreate/
   names      = "../names.txt"
   lib        = "build/lib<game>.so"
   load_base  = 0x10000
   image_size = 0x100000
   ```

   `load_base` must clear the poked-input block (`0x620`) and `image_size` must equal `os.h`'s
   `OS_IMAGE_SIZE`, which `os_fread`/`os_fwrite` bound their copies against — the harness checks
   both at import and names `project.toml` when they disagree.

2. `projects/<game>/recreate/Makefile`:

   ```make
   KIT  := ../../../tools/recreate_kit
   GAME := <game>
   include $(KIT)/kit.mk
   ```

3. `projects/<game>/recreate/test/harness.py` — a 16-line shim that binds the kit and
   star-re-exports it, so every test can keep saying `from harness import differential, report`.
   Copy it from `projects/buggyboy/recreate/test/harness.py`.

### What the candidate `.so` must export

`differential(entry, regs, glue, …)` only calls what the project's own `glue` callbacks name, so
there is no required symbol — with two groups the kit supplies for you:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_dosound_log_reset` | `void(void)` | clear the ledger before each candidate run |
| `g_dosound_log_count` | `uint32_t(void)` | number of `Dosound` calls logged |
| `g_dosound_log_args`  | `const uint32_t *(void)` | the ordered list pointers (image addresses) |
| `g_dosound`           | `void(uint8_t *, uint32_t)` | what a reconstruction calls at a `Dosound` site |

XBIOS `Dosound(A0)` writes the YM2149, not RAM, so a wrong or missing sound-command list is
**invisible to the image diff**. The harness diffs the candidate's ledger against the oracle's
ordered `Dosound` trap stream, catching exactly that. All four symbols come from `src/dosound_log.c`,
which `kit.mk` links into every candidate — the ledger is one implementation shared by every game
rather than a copy per project, and its cap is `os.h`'s `OS_DOSOUND_LOG_MAX`, the same one the
oracle's mirror ledger truncates at.

The Dosound ledger is one of the two things the model keeps **off-image**, which is exactly what a
candidate has to mirror by hand — everything else the trap model touches is plain image state that
`include/os.h`'s `os_*` helpers write identically on both sides. The other is the direct
`$ff8800`/`$ff8802` PSG write stream, compared as an ordered `(reg, val)` list (BuggyBoy's
`g_REFRESH` emits it through out-params). See [`TRAP_MODEL.md`](TRAP_MODEL.md).

The harness still treats the group as *optional* at import (it probes the three accessors once), so
a candidate built outside `kit.mk` keeps working: it is then served without the ledger while the
oracle issues no `Dosound` at all, and `differential()` fails with that diagnostic the moment one
appears. A reconstruction built for the real Atari supplies its own `g_dosound` that issues the
real trap and does not compile this file — see `projects/buggyboy/recreate/render/atari/game_main.c`.

The second group is the **refused-`os_*`-call tally**, from `src/os_refusal.c` (likewise linked into
every candidate by `kit.mk`). Unlike the ledger above it is **required**, not optional:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_os_refusal_reset` | `void(void)` | clear the tally before each candidate run |
| `g_os_refusal_count` | `uint32_t(void)` | refused `os_*` calls the candidate made |
| `os_refused`         | `int32_t(int32_t)` | what `include/os.h`'s helpers route a refusal through |

`harness.differential()` clears the tally, runs the candidate, and **raises if it is non-zero** —
closing a false-green class in which a reconstruction could drop a guard the original has and stay
green, because the refusal rejected the oracle's run only. See [`TRAP_MODEL.md`](TRAP_MODEL.md),
"Refusing on ONE side is a false green".

Reconstruction code never calls `os_refused` itself — `os.h` does, at every point a helper answers
"the model cannot serve this". It is nonetheless part of the exported ABI: the tests that pin the
mechanism call it directly to stand in for a refusal, and `harness` probes all three at import.
Absence is a hard error there rather than a graceful degrade, because the tally has no oracle-side
witness the way the Dosound ledger does: the oracle's own count is zero by construction, so a
missing symbol would reopen the false-green class on a suite that stays entirely green.

### The modeled TOS traps

Which GEMDOS/BIOS/XBIOS calls are serviced, with what semantics, and — just as important — what
each model deliberately does not capture, is written up in **[`TRAP_MODEL.md`](TRAP_MODEL.md)**.
Read it before reconstructing any function that traps. The one rule that outranks the rest: an
unmodeled call sets `modeled = 0` and `emu.run` **raises**, because a partially-modeled call that
returns a plausible-looking wrong value turns a loud failure into a silent one.

Three regions of the image are **harness-poked inputs** rather than program memory, so that
hardware whose real value is time-varying still reaches both cores identically:
`OS_CON_PENDING`/`OS_CON_CHAR` (the pending console keystroke — `harness.console_key()`),
`OS_RANDOM_VALUE` (what XBIOS `Random` returns), and `OS_PSG_REGS` (the YM2149 register file XBIOS
`Giaccess` reads and writes — `harness.psg_regs()`).

### The shared TOS memory map

`include/os.h` fixes the modeled Malloc heap (`OS_HEAP_BASE`), the staged-file table
(`OS_FS_TABLE` / `OS_FS_STAGING`) and the poked-input block above at kit-wide addresses, mirrored
in Python by `harness.py` — except `OS_HEAP_BASE`, which sits in `oracle/emu.py` where the per-run
Malloc guard below needs it, and the poked-input block, which sits in `os_map.py` because
`harness.py` and `emu.py` both guard it. Both are re-exported (`harness.OS_HEAP_BASE`,
`harness.OS_CON_PENDING`, …). `test/test_os_memory_map.py` pins every constant equal to `os.h` and
refuses a second Python copy. They are **not** derived from `project.toml`, so the
harness checks at import that they clear the bound project's program, stay below the stack guard,
sit below its `load_base`, and that `OS_IMAGE_SIZE` matches its `image_size` — failing with a
diagnostic naming `project.toml` when they do not. A game whose text+bss reaches `0x20000` (heap) or
`0xbf000` (staging) needs those constants moved on both sides.

One waiver exists for the heap: only a GEMDOS `Malloc` ever writes at `OS_HEAP_BASE`, so a game
that issues none can set `tos_malloc_unused = true` in its `project.toml` (justifying it there) and
let its program cover that region — `projects/joust/recreate/project.toml` is the worked example.
`OS_FS_TABLE` has no waiver: the harness stages files itself, so an overlap there is always live.

The waiver is a claim about the *game*, so it is not taken on trust. `emu.run()` calls
`_vet_no_malloc_over_program()` after every oracle run and fails if the run served a GEMDOS `Malloc`
while `OS_HEAP_BASE` lies inside the loaded program — the one case where a green diff means
nothing, since the candidate mirrors the same `OS_HEAP_BASE` and would scribble the identical bytes
over the identical program area. Two details make it hold:

* it counts **serviced `Malloc` traps** (`osh_malloc_count`), not movement of the bump pointer. A
  `Malloc` whose size rounds to zero — canonically `Malloc(-1)`, GEMDOS's "how big is the largest
  free block?" query — is fully served and returns a block at `OS_HEAP_BASE` without moving the
  pointer, so a pointer test would wave exactly that case through;
* it lives in `emu.run()` rather than in `differential()`, so an oracle-only run and the poison
  re-run inside `_attribution_check` are covered by the same check.

It keys on the *overlap*, never on the flag, so it stays correct if `OS_HEAP_BASE` or a project's
`load_base` moves, and setting the flag on a game that does allocate does not buy a green run. The
flag itself must be a real TOML boolean (`project.py` rejects anything else: a quoted `"false"` is
truthy in Python and would silently waive the check). What it does *not* cover: a program that
reaches `OS_HEAP_BASE` through some other route than the modeled `Malloc` — nothing here watches
plain writes into that region. `projects/joust/recreate/test/test_heap_guard.py` exercises the whole
guard, since Joust is the only project it is armed for.

A **second waiver**, `tos_poked_input_unused`, exists for the poked-input block and is built the
same way. `load_base >= OS_POKE_BLOCK_END` (`0x620`) is impossible for a program that runs at a
fixed low address — `projects/wonderboy/` loads at `0x3f8`, because its `.PRG` relocates itself to
absolute `0x400` and there is nothing below that but the 68000 vector page. A game that reads
**none** of the poked state (no `Bconstat`/`Bconin`/`Crawio`, no `Random`, no `Giaccess`, no
`Kbdvbase`) can declare the flag and let its program cover the block.

Like the heap waiver it buys a layout and not a green run, and for the same reason: the claim is
about the *game*, so it is re-tested rather than trusted. Two guards, covering the two directions
the hazard has, both keyed on the **overlap** and never on the flag:

* **`emu.run()`** refuses any run in which a trap reached the block — `_vet_no_poked_input_read()`,
  keyed on the shim's `osh_poked_input_calls` tally exactly as the heap guard is keyed on
  `osh_malloc_count` (and oracle-side only, unlike the refusal tally: see
  [`TRAP_MODEL.md`](TRAP_MODEL.md) for the two limits that carries).
  This is the direct sibling of the Malloc re-check, and the half that matters:
  the dangerous reader is the game, not the test. A `Bconin` in code that only exists after a depack
  reads the program's own (nonzero) instruction bytes, is told a keystroke is pending, gets four
  bytes of code back as the key, and has four more bytes of code **zeroed** — identically on both
  sides, since both run the same `os.h`, so the diff comes back clean.
* **`harness.make_image()`** refuses any poke whose byte range lands in the block. It sits where
  pokes are *applied*, which is the layer nothing can go round: the block holds three kinds of state
  and the kit ships two builders, so hand-writing `{OS_RANDOM_VALUE: …}` into a poke dict is the
  only way any project stages an XBIOS `Random` — an idiom already in use in Joust's suite — and it
  is seen exactly like a `console_key()` one.

`console_key()` / `psg_regs()` refuse as well (`_vet_poked_input_available()`), but only as a
friendlier early error naming what was staged; they are not the guard. A project whose `load_base`
already clears the block keeps both builders however its `project.toml` is written, because the
overlap, not the flag, is what decides.

The block's Python mirror lives in **`os_map.py`**, its own module: `harness.py` and `oracle/emu.py`
both guard it and neither can import the other, and it must stay importable with nothing built so
that the kit's own suite can pin the geometry (`test/test_os_map.py`). What that suite still cannot
reach is the *wiring* — both guards live in modules that load a compiled `.so` at import — so that
half stays pinned in `projects/wonderboy/recreate/test/test_poked_input_guard.py`, the only project
the overlap exists for.

## Binding

`loader`/`emu` are plain top-level modules (so `import emu` keeps working everywhere), but they
hold **no** game constants: `project.load(<recreate dir>)` reads `project.toml`, puts
`recreate_kit/oracle/` on `sys.path`, and rebinds `loader.LOAD_BASE` / `loader.IMAGE_SIZE`
**before** `emu` is first imported — `emu.STACK_TOP` / `STACK_GUARD_LO` are derived from
`IMAGE_SIZE` at import time. Any standalone script that imports the oracle directly must
therefore bind first:

```python
sys.path.insert(0, str(REC.parents[2] / "tools"))   # reverse/tools
from recreate_kit import project
project.load(REC)                                   # REC = the project's recreate/ dir
import emu
```

`load()` is idempotent, and refuses to rebind to a *second* project inside one process.

## Building, and what `clean` owns

`liboracle.so` and Musashi's generated opcode tables (`oracle/build/`) are **shared**: every
project's `make test` links the same file. So the two `clean` targets are deliberately split —

| command | removes |
| --- | --- |
| `make clean` in `projects/<game>/recreate/` | that project's `build/` only |
| `make -C tools/recreate_kit clean` | the shared `oracle/build/` (affects every project) |

`make oracle` from a project rebuilds the shared oracle without running the suite. The oracle is
compiled **without** the project's `include/` on the header path, so a stray include can never make
the shared artifact game-specific — make's timestamps could not detect that across projects.

## Beyond the differential: running the cores on target

The differential proves the cores produce the original's **memory image**. It cannot prove the game
runs, because everything the oracle models as a no-op — the palette, the shifter, the PSG, the IKBD,
TOS's own variables — leaves no image bytes to compare, and a reconstruction can be byte-perfect
under `make test` while displaying nothing. Building the verified cores into a real GEMDOS `.PRG`
and running it under Hatari is a separate discipline with its own failure modes, and both worked
examples (`projects/buggyboy/recreate/render/atari/`, `projects/joust/recreate/atari/`) are on the
kit. Read [`docs/on-target-execution.md`](../../docs/on-target-execution.md) before starting one —
in particular "The observable surfaces", which enumerates the six things an on-target run can be
watched on and states the rule this workspace's pre-commit gate now carries: every on-target change
names the surface that would catch its failure, and a change that names none has found something.

## The kit's own tests

`make test` in this directory runs `test/` — checks that belong to `tools/` rather than to any
one game: the cross-language pin between `prg_dis.py`'s and `AtariOsTrapAnnotate.java`'s XBIOS
trap tables, `prg_dis`'s 68000 decoder (reference encodings + an opcode-space sweep for
impossible instruction forms), the C-vs-Python pin on the TOS memory map above,
`project._bool_flag`'s refusal of a non-boolean waiver flag (for **every** waiver flag, checked
against `project.load` itself so a new one cannot ship untested), and `os_map`'s overlap geometry.

They must keep running in a bare checkout — no oracle build, no candidate `.so` — which is why the
poked-input geometry was moved into `os_map.py` to be tested here at all.

They need only pytest — but the kit has no venv of its own, so **`PY` defaults to BuggyBoy's**
(`../../projects/buggyboy/recreate/.venv/bin/python`). That is a known wart: the game-agnostic kit
points at one game to find an interpreter. Any pytest works — `make test PY=/path/to/python`.
