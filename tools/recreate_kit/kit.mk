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

.PHONY: test clean venv oracle guarded
# (Re)build just the shared Musashi oracle.
oracle: $(ORACLE)

# Create the project venv and install the pinned Python deps (numpy, pyresidfp, pytest).
venv:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt

# Run the differential suite in parallel across cores (pytest-xdist). Override with
# e.g. `make test PYTEST_ARGS=-n0` for a serial run, or `PYTEST_ARGS='-n4 -k fuzz'`.
PYTEST_ARGS ?= -n auto
test: $(CAND) $(ORACLE)
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
guarded: $(CAND) $(ORACLE)
	PYTHONPATH=$(KIT)/.. $(PY) -m pytest -q $(GUARDED_PYTEST_ARGS) -p recreate_kit.guarded_image test

# Project artifacts only. The oracle + generated opcode tables in $(GENDIR) are SHARED by every
# project (and would be deleted out from under a concurrent build), so they have their own target
# in the kit: `make -C $(KIT) clean`.
clean:
	rm -rf build
