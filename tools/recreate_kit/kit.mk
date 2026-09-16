# Shared build/test rules for a `projects/<game>/recreate/` differential harness.
# Include it from the project Makefile, which supplies KIT and GAME:
#
#   KIT  := ../../../tools/recreate_kit
#   GAME := buggyboy
#   include $(KIT)/kit.mk
#
# Builds the reconstruction (candidate) and the Musashi-backed oracle, then runs the
# differential harness. `make test` rebuilds both libs and runs pytest.
CC      ?= clang
# -DRECREATE_HOST_DIFFERENTIAL marks THIS build — the candidate .so the harness dlopens — as opposed
# to a project's own on-target build, which compiles the same cores with its own flags and never
# defines it. A core keys a HOST-ONLY check on it (a bound the differential cannot state, asserted
# where there is a process to abort); nothing behavioural may hang off it, or the two builds would
# stop being the same program.
# -DOS_FS_TABLE_RUNTIME makes os.h's OS_FS_TABLE/OS_FS_STAGING variable reads rather than constants,
# so `fs_base` in a project.toml can place the staged-file window (README.md, "The staged-file window
# is the second region a project places"). Both OFF-TARGET builds pass it — this one and $(ORACLE)
# below — because one liboracle.so serves every project and a #define cannot answer "where" per
# project. A project's own .PRG build never passes it and compiles the address it always did.
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -DRECREATE_HOST_DIFFERENTIAL -DOS_FS_TABLE_RUNTIME \
           -Iinclude -I$(KIT)/include
PY      := .venv/bin/python

# A TARGET THAT FAILED MUST NOT SURVIVE WITH A FRESH MTIME — `projects/tos102us/recreate/atari`'s
# own Makefile carries the same line for the same reason. Every rule here writes its target with a
# tool that can fail part-way (a link that ran out of symbols, an objcopy over a truncated ELF), and
# without this the half-written file stays on disk looking newer than its sources: the next make
# reports it up to date and the suite measures it.
.DELETE_ON_ERROR:

CAND    := build/lib$(GAME).so
# The two files a project writes that this one READS rather than defaults: the binding (`project.toml`
# — the same name `recreate_kit.project.CONFIG_NAME` opens) and the makefile that included this one,
# which is where a project sets BENCH_CFLAGS and anything else these rules ask of it. Named once, so
# the rules below can depend on them.
PROJECT_CONFIG   := project.toml
PROJECT_MAKEFILE := $(firstword $(MAKEFILE_LIST))
# The project's own cores, plus the kit sources every candidate must export (the Dosound ledger the
# harness diffs off-image sound against — see "What the candidate .so must export" in README.md).
# `src/*/*.c` rather than the one subdirectory it used to name: a project big enough to have
# COMPONENTS keeps one per directory (projects/tos102us has src/xbios/, src/bios/, src/gemdos/…),
# and a file the build silently did not compile would fail at dlsym with the candidate's ABI error
# rather than at the missing source. It subsumes the old `src/machine/*.c`; `src/asm/*.S` is not a
# `.c` and is still built by the twin rules below.
SRC     := $(wildcard src/*.c) $(wildcard src/*/*.c) $(wildcard $(KIT)/src/*.c)

# A VARIANT build of the same candidate — a tool that compiles the cores with an extra header or an
# extra translation unit and wants ONE set of build rules, not a copy of them. It overrides CAND on
# the command line and adds its flags/sources here, e.g. BuggyBoy's
# `projects/buggyboy/tools/sprite_audit.py`:
#
#   make CAND=build/libbuggyboy_audit.so EXTRA_CFLAGS=-Ibuild/audit EXTRA_SRC=build/audit/audit.c
#
# EXTRA_CFLAGS goes FIRST so a shadowing -I wins over the project's and the kit's. Both are empty for
# a normal build, which is therefore byte-for-byte the build it was before. A variant's generated
# headers are not prerequisites of the rule below, so the variant's own tooling must delete its .so
# before invoking make rather than trusting a timestamp.
CFLAGS  := $(EXTRA_CFLAGS) $(CFLAGS)
SRC     += $(EXTRA_SRC)

# Musashi + the oracle .so are shared by every project, so they live (and build) in the kit.
MUSASHI := $(KIT)/oracle/musashi
GENDIR  := $(KIT)/oracle/build
ORACLE  := $(GENDIR)/liboracle.so
# Deliberately NOT -Iinclude: liboracle.so is shared by every project, so the *project's* headers
# must not be reachable from it — make's timestamps could not detect such a leak across projects.
#
# The CPU's trace exception is DELIBERATELY OFF — a stated modelling decision, not an inherited
# default (TRAP_MODEL.md, "The CPU configuration"). $(MUSASHI) is gitignored and cloned from upstream
# HEAD by the rule below, so m68kconf.h is untracked and unpinned: were this left to the header's own
# `#define M68K_EMULATE_TRACE M68K_OPT_OFF`, a fresh clone at a different upstream commit would change
# the oracle's CPU silently. Its `#ifndef` guard is what lets this -D win. Turning it ON would make
# the oracle single-step self-decrypting protection code (Wonder Boy's Copylock is the live case),
# which is what its stub's "forgetting it is loud, not silent" property rests on NOT happening —
# see projects/wonderboy/recreate/PORTABILITY.md §6.1.
OCFLAGS := -O2 -fPIC -DM68K_EMULATE_TRACE=0 -DOS_FS_TABLE_RUNTIME \
           -I$(KIT)/include -I$(MUSASHI) -I$(GENDIR) -I$(MUSASHI)/softfloat

# On this file too, as $(ORACLE) is: CFLAGS and SRC are decided here, so a candidate built
# before a change to either is a stale .so the suite would go on dlopening.
$(CAND): $(SRC) $(wildcard include/*.h) $(wildcard $(KIT)/include/*.h) $(KIT)/kit.mk
	@mkdir -p build
	$(CC) $(CFLAGS) -shared $(SRC) -o $(CAND)

# Musashi generates its opcode tables from m68k_in.c before the core can compile.
$(MUSASHI)/m68kcpu.c:
	git clone --depth 1 https://github.com/kstenerud/Musashi.git $(MUSASHI)

$(GENDIR)/m68kops.c: $(MUSASHI)/m68kmake.c $(MUSASHI)/m68k_in.c
	@mkdir -p $(GENDIR)
	$(CC) -O2 -o $(GENDIR)/m68kmake $(MUSASHI)/m68kmake.c
	cd $(GENDIR) && ./m68kmake . ../musashi/m68k_in.c

# $(KIT)/kit.mk is a prerequisite because OCFLAGS above configures the oracle's CPU: without it,
# changing -DM68K_EMULATE_TRACE leaves make reporting "up to date" and the STALE .so re-running —
# which would make the behavioural pin over that flag look non-vacuous when it was never rebuilt.
# The GEM/VDI model and the raster core underneath it are SHARED SOURCES, compiled into the oracle
# here and swept into every candidate by SRC above — that is what makes "both sides draw the same
# pixels" true by construction rather than by two transcriptions agreeing (include/raster.h). They
# are the only kit `src/` files the oracle links: the rest (the refusal tally, the Dosound and event
# ledgers, the heap) are the CANDIDATE's halves of models the shim mirrors itself.
ORACLE_SHARED_SRC := $(KIT)/src/gem.c $(KIT)/src/raster.c

$(ORACLE): $(KIT)/oracle/shim.c $(KIT)/include/os.h $(KIT)/include/raster.h $(ORACLE_SHARED_SRC) $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c $(KIT)/kit.mk
	$(CC) $(OCFLAGS) -shared \
	  $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c $(KIT)/oracle/shim.c \
	  $(ORACLE_SHARED_SRC) \
	  -o $(ORACLE)

# ---- the ASM TWINS (optional; a project has them once it writes a src/asm/*.S) -----------------
# A twin is a hand-written m68k transcription of the ORIGINAL binary's own instruction sequence for
# one routine, carrying the C signature of the verified core it substitutes for on the target build.
# It is assembled here into ONE blob so `test` can run it under Musashi and diff it against that core
# — see $(KIT)/asm_twin.py, which loads what this produces, and the project's own src/asm/README.md.
#
# A project with no src/asm/ sets nothing and gets nothing: ASM_SRC is empty, ASM_BIN is empty, and
# `test` above gains no prerequisite. Projects that HAVE twins get them built before every `make
# test`, so a suite can never run against a stale blob (or fail to run for want of a build step
# nobody remembered).
ASM_SRC := $(wildcard src/asm/*.S)
ifneq ($(ASM_SRC),)
ASM_DIR := build/asm
ASM_ELF := $(ASM_DIR)/twins.elf
ASM_BIN := $(ASM_DIR)/twins.bin
# ...and one object PER SOURCE, kept rather than assembled straight to the blob. A test that asks
# what a `.S` defines has to ask its own object: the linked blob is one flat symbol table, so two
# files that both `.equ SCREEN_ROW_BYTES` collapse into whichever the linker emitted last, and a pin
# over the blob would check one file's value and silently vouch for the other's (measured — a wrong
# value in one `.S` was covered by its neighbour's correct one).
ASM_OBJ := $(patsubst src/asm/%.S,$(ASM_DIR)/%.o,$(ASM_SRC))
# The link base is asm_twin.py's, ASKED OF IT rather than spelt again here: the loader places the
# blob at that address and a second spelling could drift from it silently (the blob would load at
# one base and run with its absolute references resolved against another).
ASM_LINK_BASE := $(shell $(PY) -c 'import sys; sys.path.insert(0, "$(KIT)/.."); \
                                   from recreate_kit import asm_twin; print(asm_twin.asm_link_base())')
# -Wl,--build-id=none: a build-id note would be laid down as an allocated section and objcopy would
# carry it into the flat blob, moving every symbol after it.
# -nostdlib: the twins call nothing and must not drag in a C runtime that would need one.
# -Wl,-e0: the blob has no `_start` and needs none — every twin is entered by SYMBOL, from Python or
# from the C that links it. Setting the ELF entry explicitly is what stops ld warning about that.
#
# -DRECREATE_HOST_DIFFERENTIAL marks this as the OFF-TARGET assembly of the twins, exactly as it
# marks the candidate .so above, and it is what a `.S` selects its CALLBACK DOOR stubs on: off target
# a door stub jumps into asm_twin.py's band, on target it reaches the real C core (asm_twin.py, "THE
# CALLBACK DOOR"). The twin BODY must be byte-identical either way — it always `bsr`s the stub — so
# what hangs off this flag is the one instruction that stands in for a link, and nothing else. A
# project's own target build (its atari/build.sh, its own flags) never defines it.
#
# ...and the door's BAND is asked of asm_twin.py for the same reason ASM_LINK_BASE is: a `.S` that
# spelt the base itself would keep jumping to the old address the day it moved, and would execute
# the zeros there rather than stopping at a door.
ASM_DOOR_FLAGS := $(shell $(PY) -c 'import sys; sys.path.insert(0, "$(KIT)/.."); \
                                    from recreate_kit import asm_twin; print(asm_twin.asm_door_flags())')
ASM_CFLAGS := -m68000 -nostdlib -DRECREATE_HOST_DIFFERENTIAL $(ASM_DOOR_FLAGS) \
              -Iinclude -I$(KIT)/include

# $(KIT)/kit.mk is a prerequisite of BOTH rules for the $(ORACLE) rule's reason: ASM_CFLAGS above
# configures the assembly, and without it a flag change leaves every already-built object reporting
# "up to date". A blob half-assembled under one flag set and half under another is the worst shape
# this could take — one twin's door stub taking the on-target arm inside an off-target blob — and
# make would say nothing.
$(ASM_DIR)/%.o: src/asm/%.S $(KIT)/kit.mk $(KIT)/asm_twin.py
	@mkdir -p $(ASM_DIR)
	m68k-elf-gcc $(ASM_CFLAGS) -c $< -o $@

$(ASM_ELF): $(ASM_OBJ) $(KIT)/asm_twin.py $(KIT)/kit.mk
	@[ -n "$(ASM_LINK_BASE)" ] || { echo "ERROR: asm_twin.asm_link_base() gave nothing"; exit 1; }
	@[ -n "$(ASM_DOOR_FLAGS)" ] || { echo "ERROR: asm_twin.asm_door_flags() gave nothing, so the"; \
	  echo "       twins would assemble with no door band and fail at LINK naming the macro"; \
	  echo "       rather than the shell-out that did not run"; exit 1; }
	m68k-elf-gcc $(ASM_CFLAGS) -Wl,--build-id=none -Wl,-e0 \
	  -Wl,-Ttext=$(ASM_LINK_BASE) $(ASM_OBJ) -o $(ASM_ELF)

$(ASM_BIN): $(ASM_ELF)
	m68k-elf-objcopy -O binary $(ASM_ELF) $(ASM_BIN)
endif

# ---- TIER 3's NUMERATOR: the cores cross-compiled for the target (a ROM project) ----------------
# The differential proves the C equals the original; this build is what says what it COSTS. It is the
# same C, compiled by m68k-elf-gcc with the flags the SHIPPED build uses — which is why BENCH_CFLAGS
# is the project's to supply and is not defaulted here: flags invented by the kit would measure a
# program nobody ships. $(KIT)/rom_bench.py loads what this produces and runs it under the oracle.
#
# Opt-in through project.toml's `bench_base`, asked of rom_bench.py rather than read here, for
# ASM_LINK_BASE's reason: the blob's link base and the loader's idea of it are one value, and a
# second spelling would drift silently — the blob would load at one address and run with its absolute
# references resolved against another. The shell-out does NOT bind the project (rom_bench.bench_base
# says why), so it stays evaluable before the snapshot a binding insists on exists.
#
# THE KEY'S PRESENCE IS DECIDED BY GREP AND ITS VALUE BY THE PROBE, and splitting the two is what
# makes a broken probe LOUD. The probe prints nothing for a project that declares no `bench_base` —
# and it also prints nothing when it cannot run at all (no venv yet, `PY` overridden to something
# that is not a Python), which is indistinguishable from the first. Deciding the block on that
# output alone silently drops the whole numerator: no blob, no `test:` prerequisite, and a gate that
# passes because it never ran. `make -n test PY=/nonexistent/python` is the repro.
BENCH_DECLARED := $(shell grep -l '^bench_base' $(PROJECT_CONFIG) 2>/dev/null)
ifneq ($(BENCH_DECLARED),)
BENCH_BASE := $(shell $(PY) -c 'import sys; sys.path.insert(0, "$(KIT)/.."); \
                                from recreate_kit import rom_bench; print(rom_bench.bench_base())')
ifeq ($(BENCH_BASE),)
$(error $(PROJECT_CONFIG) declares bench_base, but asking rom_bench.bench_base() for its value \
printed nothing — the probe could not run. Check PY ($(PY)): without this the Tier 3 numerator \
would be dropped silently, blob, prerequisite and gate together)
endif
ifndef BENCH_CFLAGS
$(error project.toml declares bench_base = $(BENCH_BASE), so this project builds its cores for the \
target — set BENCH_CFLAGS (and BENCH_LDLIBS) to the SHIPPED build's own flags before including \
kit.mk. A Tier 3 numerator measured under flags the shipped build does not use is a number about \
nothing)
endif
BENCH_DIR := build/bench
BENCH_ELF := $(BENCH_DIR)/bench.elf
BENCH_BIN := $(BENCH_DIR)/bench.bin
# The same sweep $(SRC) makes of the project's cores, one directory deep, plus the kit's entry probe
# — the empty function rom_bench.py measures the oracle's own entry overhead on. A core the sweep
# missed surfaces as a missing SYMBOL when a bench row asks for it, naming the function.
#
# THE `.S` FILES ARE CORES TOO, and in a ROM project some of them have to be. An exception handler
# cannot be C on the target — it is entered with a 68000 exception frame, moves the stack pointer
# between the supervisor and user stacks, and owes its caller a register file no C compiler can
# promise — so the reconstruction carries the ROM's own instruction sequence, and the only build in
# which that sequence RUNS is this one. Assembled by the same `m68k-elf-gcc` invocation as the C
# (gcc dispatches on the extension, and `.S` capital-S is the cpp'd form, so a `.S` may include the
# project's addrs.h), under the SHIPPED build's own flags for the reason every other source here is.
# The sweep MIRRORS the `.c` one, both depths: `src/*.S` beside `src/*/*.S`, because a project whose
# cores sit at the top of `src/` keeps its transcriptions there too, and a wildcard that is one
# directory off is silently empty rather than an error.
#
# What it is NOT is `src/asm/*.S`: that is the ASM TWINS' directory above, which is a .PRG project's
# mechanism and mutually exclusive with this one — rom_bench.py refuses a project with no `rom` key
# and asm_twin.py refuses one WITH it, both by testing the project's ROM MODE rather than its name —
# so the two sweeps cannot collide over one file.
BENCH_SRC := $(wildcard src/*.c) $(wildcard src/*/*.c) \
             $(wildcard src/*.S) $(wildcard src/*/*.S) \
             $(KIT)/bench/entry_probe.c
# -Wl,-e0: the blob has no `_start` and needs none — every core is entered by SYMBOL, from Python.
# -Wl,--build-id=none: a build-id note is an allocated section, and objcopy would carry it into the
# flat blob and move every symbol after it.
# One compile-and-link rather than one object per source (the twins' shape): nothing here asks a
# single translation unit what it defines, which is the whole reason those are kept apart.
# $(PROJECT_CONFIG) and the project's own makefile are prerequisites because both DECIDE this build:
# the first carries `bench_base`, which is the link address, and the second carries BENCH_CFLAGS,
# which is what the cores are compiled with. Without them a change to either leaves make reporting
# "up to date" and the suite measuring a blob built under the previous configuration.
$(BENCH_ELF): $(BENCH_SRC) $(wildcard include/*.h) $(wildcard $(KIT)/include/*.h) $(KIT)/kit.mk \
              $(KIT)/rom_bench.py $(PROJECT_CONFIG) $(PROJECT_MAKEFILE)
	@mkdir -p $(BENCH_DIR)
	m68k-elf-gcc $(BENCH_CFLAGS) -Wl,--build-id=none -Wl,-e0 -Wl,-Ttext=$(BENCH_BASE) \
	  $(BENCH_SRC) $(BENCH_LDLIBS) -o $@

$(BENCH_BIN): $(BENCH_ELF)
	m68k-elf-objcopy -O binary $(BENCH_ELF) $(BENCH_BIN)

# Both suites build it, for $(ASM_BIN)'s reason: a Tier 3 gate that ran against a stale blob would
# report yesterday's cycles, and one that SKIPPED for want of a build step would report none.
test: $(BENCH_BIN)
guarded: $(BENCH_BIN)
endif

.PHONY: test clean venv oracle guarded asm
# (Re)build just the shared Musashi oracle.
oracle: $(ORACLE)

# (Re)build just the project's asm twins. No-op for a project that has none.
asm: $(ASM_BIN)

# Create the project venv and install the pinned Python deps (numpy, pyresidfp, pytest).
venv:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt

# Run the differential suite in parallel across cores (pytest-xdist). Override with
# e.g. `make test PYTEST_ARGS=-n0` for a serial run, or `PYTEST_ARGS='-n4 -k fuzz'`.
PYTEST_ARGS ?= -n auto
test: $(CAND) $(ORACLE) $(ASM_BIN)
	$(PY) -m pytest -q $(PYTEST_ARGS) test

# The same suite over an image whose surroundings are PROT_NONE, so a candidate that indexes its
# `uint8_t *image` past either end FAULTS instead of quietly reading the host heap. It is the
# surface for any change that bounds a SPAN rather than a single access — a span one element too
# generous proves a walk in-image that is not, and reads where there is no image to differ.
#
# DELIBERATELY NOT PART OF `test`, and it must not become one: a fault is a dead pytest worker and
# not a named assertion, so the run is a CENSUS of that class rather than a gate (README.md, "The
# guarded-image sweep, and the seam it hangs on", has the whole argument). Darwin/BSD only — the
# plugin refuses at `pytest_configure` elsewhere.
#
# PYTHONPATH reaches `tools/`, which is $(KIT)'s parent, because the plugin is imported as
# `recreate_kit.guarded_image`; everything else is the `test` target with that plugin loaded.
GUARDED_PYTEST_ARGS ?= -n auto
guarded: $(CAND) $(ORACLE) $(ASM_BIN)
	PYTHONPATH=$(KIT)/.. $(PY) -m pytest -q $(GUARDED_PYTEST_ARGS) -p recreate_kit.guarded_image test

# Project artifacts only. The oracle + generated opcode tables in $(GENDIR) are SHARED by every
# project (and would be deleted out from under a concurrent build), so they have their own target
# in the kit: `make -C $(KIT) clean`.
clean:
	rm -rf build
