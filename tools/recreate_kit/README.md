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
├── harness.py        the differential driver (differential/report/make_image/stage_files)
├── kit.mk            shared make rules: candidate .so, Musashi oracle, `test`/`venv`/`oracle`/`clean`
├── include/          machine.h (big-endian image accessors)  os.h (deterministic TOS trap model)
├── oracle/           loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (callbacks)
│                     isa_conformance.py  tos_probe.py   musashi/ + build/ (gitignored)
├── test/             the kit's own regression tests (`make test` here; no project needed)
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
there is no required symbol — with one **optional** group:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_dosound_log_reset` | `void(void)` | clear the ledger before each candidate run |
| `g_dosound_log_count` | `uint32_t(void)` | number of `Dosound` calls logged |
| `g_dosound_log_args`  | `const uint32_t *(void)` | the ordered list pointers (image addresses) |

XBIOS `Dosound(A0)` writes the YM2149, not RAM, so a wrong or missing sound-command list is
**invisible to the image diff**. When the three symbols are present the harness diffs the
candidate's ledger against the oracle's ordered `Dosound` trap stream, catching exactly that. A
game that never issues `Dosound` may omit them (the kit probes once at import, and skips both the
reset and the comparison). It is not a silent downgrade: if the oracle *does* issue `Dosound` while
the candidate exports no ledger, `differential()` fails with that diagnostic — so a game with sound
should implement the ledger rather than drop it. `projects/buggyboy/recreate/src/os.c` is the
reference implementation (~6 lines).

### The shared TOS memory map

`include/os.h` fixes the modeled Malloc heap (`OS_HEAP_BASE`) and the staged-file table
(`OS_FS_TABLE` / `OS_FS_STAGING`) at kit-wide addresses, mirrored in Python by `harness.py` and
pinned equal by `test/test_os_memory_map.py`. They are **not** derived from `project.toml`, so the
harness checks at import that they clear the bound project's program and stay below the stack
guard, and fails with a diagnostic naming `project.toml` when they do not. A game whose text+bss
reaches `0x20000` (heap) or `0xbf000` (staging) needs those constants moved on both sides.

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

## The kit's own tests

`make test` in this directory runs `test/` — checks that belong to `tools/` rather than to any
one game: the cross-language pin between `prg_dis.py`'s and `AtariOsTrapAnnotate.java`'s XBIOS
trap tables, `prg_dis`'s 68000 decoder (reference encodings + an opcode-space sweep for
impossible instruction forms), and the C-vs-Python pin on the TOS memory map above.

They need only pytest — but the kit has no venv of its own, so **`PY` defaults to BuggyBoy's**
(`../../projects/buggyboy/recreate/.venv/bin/python`). That is a known wart: the game-agnostic kit
points at one game to find an interpreter. Any pytest works — `make test PY=/path/to/python`.
