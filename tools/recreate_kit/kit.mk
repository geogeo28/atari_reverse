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
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -DRECREATE_HOST_DIFFERENTIAL -Iinclude -I$(KIT)/include
PY      := .venv/bin/python

CAND    := build/lib$(GAME).so
# The project's own cores, plus the kit sources every candidate must export (the Dosound ledger the
# harness diffs off-image sound against — see "What the candidate .so must export" in README.md).
SRC     := $(wildcard src/*.c) $(wildcard src/machine/*.c) $(wildcard $(KIT)/src/*.c)

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
OCFLAGS := -O2 -fPIC -DM68K_EMULATE_TRACE=0 \
           -I$(KIT)/include -I$(MUSASHI) -I$(GENDIR) -I$(MUSASHI)/softfloat

$(CAND): $(SRC) $(wildcard include/*.h) $(wildcard $(KIT)/include/*.h)
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
$(ORACLE): $(KIT)/oracle/shim.c $(KIT)/include/os.h $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c $(KIT)/kit.mk
	$(CC) $(OCFLAGS) -shared \
	  $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c $(KIT)/oracle/shim.c \
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
