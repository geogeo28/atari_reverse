# BLACK ICE - portable engine core.
#
#   make            build the host binary
#   make test       run the pytest suite (builds the host binary first)
#   make m68k       cross-compile the portable core with m68k-elf-gcc -m68000,
#                   which is the gate that keeps the core free of host
#                   assumptions (no libm, no 32-bit int, no malloc)
#   make generated  re-run the table and asset generators and the level compiler
#   make frames     render the golden walk to host/out/ as PNGs
#   make goldens    diff the rendered walk against test/golden/, writing nothing
#   make bless      ACCEPT that diff - only after looking at the frames

PYTHON      ?= $(HOME)/miniconda3/envs/atari_reverse/bin/python
CC          ?= clang
M68K_CC     ?= m68k-elf-gcc

BUILD       := build
INCLUDE     := -Iinclude -Ihost
WARNINGS    := -Wall -Wextra -Wshadow -Wconversion -Wno-sign-conversion
CFLAGS      := -O2 -std=c99 $(WARNINGS) $(INCLUDE)
# -ffreestanding -nostdlib because m68k-elf ships no libc; the platform layer
# supplies the two functions include/mem.h declares.
M68K_CFLAGS := -O2 -std=c99 -m68000 -ffreestanding -nostdlib -fomit-frame-pointer \
               -ffunction-sections -fdata-sections $(WARNINGS) -Iinclude

# Every target depends on the headers: without this a change to a constant in
# include/ leaves a stale binary behind and the tests go green on it.
HEADERS     := $(wildcard include/*.h) $(wildcard host/*.h)
# Generated, and named explicitly: the wildcard below cannot see a file that
# does not exist yet, so a clean tree would otherwise build without them.
GENERATED_SRC := src/tables.c src/assets_data.c
# Where art/build_art.py writes the native-resolution indexed PNGs mkassets reads.
ART_NATIVE  := art/out/native
# Every portable source, not a hand-listed subset: a new src/*.c joins the host
# build, the shared library and the m68k gate by existing.
CORE_SRC    := $(sort $(wildcard src/*.c) $(GENERATED_SRC))
HOST_SRC    := host/c2p.c host/render_png.c host/main_host.c
# The second host binary: main_host replays and hashes, play_host runs the game
# layer live and prints what it did, so a frame can be looked at (host/README).
PLAY_SRC    := host/c2p.c host/render_png.c host/play_host.c

HOST_BIN    := $(BUILD)/blackice_host
PLAY_BIN    := $(BUILD)/blackice_play
HOST_LIB    := $(BUILD)/libblackice.so
# Every authored level compiles, not a hand-listed subset: a new levels/*.txt
# joins the build and the test sweep by existing.
LEVELS      := $(patsubst levels/%.txt,levels/%.bil,$(wildcard levels/*.txt))

.PHONY: all test m68k libgcc-gate generated frames goldens bless clean \
        atari atari-bench atari-verify

all: $(HOST_BIN) $(PLAY_BIN) $(HOST_LIB) $(LEVELS)

# Generated sources have real rules, so a stale one rebuilds instead of being
# silently compiled.  Each is written to a temp file and renamed only once the
# generator has exited 0: `python gen.py > committed.c` truncates the committed
# file BEFORE running it, so a generator that raises would otherwise leave an
# empty source where a working one used to be.
define generate_source
	$(PYTHON) $< > $@.tmp && mv -f $@.tmp $@
endef

src/tables.c: tools/mktables.py
	$(generate_source)

# mkassets reads the shipped art out of art/out/native/.  That tree is GENERATED
# and not committed (.gitignore), so the wildcard is empty on a clean checkout
# and the guard below builds it before the generator needs it; where it is
# already present, editing a PNG rebuilds this source.
ART_PNG := $(wildcard $(ART_NATIVE)/*.png)

src/assets_data.c: tools/mkassets.py $(ART_PNG)
	@[ -d $(ART_NATIVE) ] || $(MAKE) -C art PYTHON=$(PYTHON)
	$(generate_source)

$(HOST_BIN): $(CORE_SRC) $(HOST_SRC) $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -o $@ $(CORE_SRC) $(HOST_SRC)

$(PLAY_BIN): $(CORE_SRC) $(PLAY_SRC) $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -o $@ $(CORE_SRC) $(PLAY_SRC)

# The shared library is how the pytest suite drives the engine through ctypes.
$(HOST_LIB): $(CORE_SRC) host/c2p.c host/abi.c $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -fPIC -shared -o $@ $(CORE_SRC) host/c2p.c host/abi.c

$(BUILD):
	mkdir -p $(BUILD) host/out

levels/%.bil: levels/%.txt tools/mklevel.py
	$(PYTHON) tools/mklevel.py $< -o $@

# The cross build compiles the portable core only: host/ is deliberately not
# part of it, and neither is any libc beyond memcpy/memset.
# host/abi_m68k.c is the one exception, and it is the point: it asserts the
# published 68000 record offsets with the compiler that will build the target,
# rather than extrapolating them from the host's 8-byte pointers.  Asserts
# only - it contributes no code.
m68k: $(CORE_SRC) host/abi_m68k.c $(HEADERS) | $(BUILD)
	@mkdir -p $(BUILD)/m68k
	@for f in $(CORE_SRC) host/abi_m68k.c; do \
	    $(M68K_CC) $(M68K_CFLAGS) -c $$f -o $(BUILD)/m68k/$$(basename $$f .c).o || exit 1; \
	done
	@m68k-elf-size -t $(BUILD)/m68k/*.o | tail -1
	@$(MAKE) --no-print-directory libgcc-gate
	@echo "m68k cross-compile OK"

# The cost model in include/render.h only holds if the 68000 never calls out to
# a libgcc arithmetic helper: a 32x32 multiply or any divide is a subroutine
# costing several times the `muls.w` / `divu.w` it replaced, and in a per-column
# loop that is tens of thousands of cycles a frame.  This is the gate that keeps
# it true, and an undefined reference to one is a build failure, not a comment.
#
# Three objects are exempt, and each is a case where the 32-bit arithmetic IS
# the algorithm and the algorithm is cold:
#   hash.o      FNV-1a's step is a 32-bit multiply by definition.  It exists so
#               the host replay can compare runs; nothing hashes on target.
#   rng.o       DESIGN 4.3 names a 32-bit LCG.  The sim draws a handful of
#               numbers per 25 Hz tick - see include/rng.h.
#   tables.o    tables_init's two divides run 8192 times, once, at start-up.
LIBGCC_EXEMPT := hash.o rng.o tables.o

# The object list is built in the recipe, not with $(wildcard) at parse time:
# on a clean tree that variable would expand to nothing and the gate would pass
# by having checked nothing at all.  An empty list is a failure here.
libgcc-gate:
	@gated=""; \
	for object in $(BUILD)/m68k/*.o; do \
	    [ -f "$$object" ] || continue; \
	    case " $(LIBGCC_EXEMPT) " in *" `basename $$object` "*) continue;; esac; \
	    gated="$$gated $$object"; \
	done; \
	if [ -z "$$gated" ]; then \
	    echo "FAIL: no objects to gate - the cross build did not run"; exit 1; \
	fi; \
	if m68k-elf-nm -u $$gated | grep -E '__(mul|div|mod|udiv|umod)si3'; then \
	    echo "FAIL: src/ references a libgcc arithmetic helper (see include/render.h)"; \
	    exit 1; \
	fi; \
	echo "libgcc arithmetic-helper gate: clean (`echo $$gated | wc -w | tr -d ' '` objects)"

generated: $(GENERATED_SRC) $(LEVELS)

# The same five frames the goldens keep, for looking at.
frames: $(HOST_BIN) $(LEVELS)
	@mkdir -p host/out
	$(HOST_BIN) --level levels/level1.txt --script test/scripts/walk.txt \
	            --frames 100 --out host/out --png 0,20,40,60,99

# Says what moved and writes nothing.
goldens: $(HOST_BIN) $(LEVELS)
	$(PYTHON) tools/mkgolden.py

# Rewrites the committed goldens.  Run it only when a change to the engine is
# meant to move the pixels, and LOOK at the frames before committing.
bless: $(HOST_BIN) $(LEVELS)
	$(PYTHON) tools/mkgolden.py --bless

# The cross build is part of the gate, not a separate thing to remember: a
# change that only compiles on the host is not a change this engine can ship.
test: $(HOST_BIN) $(HOST_LIB) $(LEVELS) m68k
	$(PYTHON) -m pytest test -q

clean:
	rm -rf $(BUILD) host/out

# ---- the STE target ------------------------------------------------------
# atari/ owns its own build (m68k-elf-gcc, the .PAK, the Hatari harness); these delegate so the
# whole project has one entry point. atari/README.md is canonical for what they produce.

# PYTHON is passed down so the .PAK is packed by the same interpreter the level compiler and the
# asset generators run under; atari/Makefile's own default is only for running it directly.
atari:
	$(MAKE) -C atari PYTHON=$(PYTHON)

atari-bench:
	$(MAKE) -C atari PYTHON=$(PYTHON) bench

atari-verify:
	$(MAKE) -C atari PYTHON=$(PYTHON) verify
