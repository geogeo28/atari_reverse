# Build the reconstruction (candidate) and the Musashi-backed oracle, then run the
# differential harness. `make test` rebuilds both libs and runs pytest.
CC      ?= clang
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -Iinclude
PY      := .venv/bin/python

CAND    := build/libbuggyboy.so
SRC     := $(wildcard src/*.c) $(wildcard src/machine/*.c)

MUSASHI := oracle/musashi
GENDIR  := oracle/build
ORACLE  := oracle/build/liboracle.so
OCFLAGS := -O2 -fPIC -Iinclude -I$(MUSASHI) -I$(GENDIR) -I$(MUSASHI)/softfloat

$(CAND): $(SRC) $(wildcard include/*.h)
	@mkdir -p build
	$(CC) $(CFLAGS) -shared $(SRC) -o $(CAND)

# Musashi generates its opcode tables from m68k_in.c before the core can compile.
$(MUSASHI)/m68kcpu.c:
	git clone --depth 1 https://github.com/kstenerud/Musashi.git $(MUSASHI)

$(GENDIR)/m68kops.c: $(MUSASHI)/m68kmake.c $(MUSASHI)/m68k_in.c
	@mkdir -p $(GENDIR)
	$(CC) -O2 -o $(GENDIR)/m68kmake $(MUSASHI)/m68kmake.c
	cd $(GENDIR) && ./m68kmake . ../musashi/m68k_in.c

$(ORACLE): oracle/shim.c include/os.h $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c
	$(CC) $(OCFLAGS) -shared \
	  $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c oracle/shim.c \
	  -o $(ORACLE)

.PHONY: test clean venv bench coverage-gap
# Create the project venv and install the pinned Python deps (numpy, pyresidfp, pytest).
venv:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt

# Run the differential suite in parallel across cores (pytest-xdist). Override with
# e.g. `make test PYTEST_ARGS=-n0` for a serial run, or `PYTEST_ARGS='-n4 -k fuzz'`.
PYTEST_ARGS ?= -n auto
test: $(CAND) $(ORACLE)
	$(PY) -m pytest -q $(PYTEST_ARGS) test

# Report sink call sites (Dosound/INITTUNE/INITFX/stop_music) that no test executes — off-image or
# fuzz-unreached sound/OS triggers the differential diff can't see. See tools/coverage_gap.py.
coverage-gap: $(CAND) $(ORACLE)
	$(PY) tools/coverage_gap.py

# Rank the per-frame in-race pipeline by its cost on the original 68000 (Musashi cycle count) — which
# function is the bottleneck. `make bench BENCH_ARGS='2 100'` picks leg/warmup. See tools/bench_frame.py.
BENCH_ARGS ?=
bench: $(CAND) $(ORACLE)
	$(PY) tools/bench_frame.py $(BENCH_ARGS)

clean:
	rm -rf build $(GENDIR)/m68kmake $(GENDIR)/m68kops.* $(ORACLE)