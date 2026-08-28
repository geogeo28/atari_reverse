# BLACK ICE - portable engine core.
#
#   make            build the host binary
#   make test       run the pytest suite (builds the host binary first)
#   make m68k       cross-compile the portable core with m68k-elf-gcc -m68000,
#                   which is the gate that keeps the core free of host
#                   assumptions (no libm, no 32-bit int, no malloc)
#   make generated  re-run the table and asset generators and the level compiler
#   make frames     render the golden walk to host/out/ as PNGs
#   make goldens    REGENERATE test/golden/ - only after a deliberate change

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
CORE_SRC    := src/tables.c src/assets_placeholder.c src/rng.c src/map.c src/level.c \
               src/player.c src/game.c src/raycast.c src/draw.c src/sprite.c
HOST_SRC    := host/c2p.c host/render_png.c host/main_host.c

HOST_BIN    := $(BUILD)/blackice_host
HOST_LIB    := $(BUILD)/libblackice.so
# Every authored level compiles, not a hand-listed subset: a new levels/*.txt
# joins the build and the test sweep by existing.
LEVELS      := $(patsubst levels/%.txt,levels/%.bil,$(wildcard levels/*.txt))

.PHONY: all test m68k generated frames goldens clean

all: $(HOST_BIN) $(HOST_LIB) $(LEVELS)

$(HOST_BIN): $(CORE_SRC) $(HOST_SRC) $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -o $@ $(CORE_SRC) $(HOST_SRC)

# The shared library is how the pytest suite drives the engine through ctypes.
$(HOST_LIB): $(CORE_SRC) host/c2p.c host/abi.c $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -fPIC -shared -o $@ $(CORE_SRC) host/c2p.c host/abi.c

$(BUILD):
	mkdir -p $(BUILD) host/out

levels/%.bil: levels/%.txt tools/mklevel.py
	$(PYTHON) tools/mklevel.py $< -o $@

# The cross build compiles the portable core only: host/ is deliberately not
# part of it, and neither is any libc beyond memcpy/memset.
m68k: $(CORE_SRC) $(HEADERS) | $(BUILD)
	@mkdir -p $(BUILD)/m68k
	@for f in $(CORE_SRC); do \
	    $(M68K_CC) $(M68K_CFLAGS) -c $$f -o $(BUILD)/m68k/$$(basename $$f .c).o || exit 1; \
	done
	@m68k-elf-size -t $(BUILD)/m68k/*.o | tail -1
	@echo "m68k cross-compile OK"

generated:
	$(PYTHON) tools/mktables.py > src/tables.c
	$(PYTHON) tools/mkassets.py > src/assets_placeholder.c
	$(MAKE) $(LEVELS)

# The same five frames the goldens keep, for looking at.
frames: $(HOST_BIN) $(LEVELS)
	@mkdir -p host/out
	$(HOST_BIN) --level levels/level1.txt --script test/scripts/walk.txt \
	            --frames 100 --out host/out --png 0,20,40,60,99

# Rewrites the committed goldens.  Run it only when a change to the engine is
# meant to move the pixels, and look at the frames before committing.
goldens: $(HOST_BIN) $(LEVELS)
	$(PYTHON) tools/mkgolden.py

test: $(HOST_BIN) $(HOST_LIB) $(LEVELS)
	$(PYTHON) -m pytest test -q

clean:
	rm -rf $(BUILD) host/out
