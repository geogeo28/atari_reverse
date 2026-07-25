# Build the remaster host lib and validate it pixel-identical to the verified recreate/ cores.
# The reference framebuffers come from recreate's libbuggyboy.so, so we reuse recreate's venv
# (ctypes + numpy already pinned there) and build recreate first.
CC      ?= clang
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -Iinclude -Irender/atari/build
RECREATE := ../recreate
PY       := $(RECREATE)/.venv/bin/python

CAND    := build/libremaster.so
# STE hardware-blitter target-only sources (PERF30 C4): they poke supervisor-only 0xFFFF8Axx registers
# and are linked ONLY by the GAME_STE build (render/atari/build_game.sh's $STE_SOURCES), never by the
# host .so / bench — exactly like the src/asm/*.S cores. Excluded from the wildcard so the differential
# build stays host-portable.
STE_SRC := src/blitter.c src/blitter_objshift2.c src/blitter_selftest.c src/blitter_sweep.c
SRC     := $(filter-out $(STE_SRC),$(wildcard src/*.c))
RECON   := $(RECREATE)/build/libbuggyboy.so
# Generated: the sound driver's baked program-data constants. gen_sound_fixture.py emits TWO headers in
# one run — sound_data.h (SND_CONST: const tables + tune note streams, read by src/sound.c every frame)
# and sound_dosound.h (SND_DOSOUND: the TOS Dosound command lists, only the on-target seam includes).
# Both regenerate whenever the generator, the image it bakes from, or the loader that relocates it
# changes. They live in render/atari/build/ with every other generated fixture (one fixture home — the
# m68k cross builds already -I that directory).
SOUND_DATA := render/atari/build/sound_data.h
SOUND_DOSOUND := render/atari/build/sound_dosound.h
SOUND_IMAGE := ../bin/BUGGYBOY.PRG
# The cross-compiled m68k bench.elf — needed by test/test_asm_blit.py (the Musashi differential that
# pins both hand-asm cores (objshift2 + objshift) byte-exact vs the C references; PERF30 A3). Built by bench_build.sh.
BENCH_ELF := render/atari/build/bench.elf

$(SOUND_DATA): render/atari/gen_sound_fixture.py render/atari/fixture_lib.py \
               $(SOUND_IMAGE) $(RECREATE)/oracle/loader.py
	@mkdir -p render/atari/build
	$(PY) render/atari/gen_sound_fixture.py

# The same generator run produces sound_dosound.h; depend on sound_data.h so it is regenerated in step,
# and (make 3.81 has no grouped targets) re-run the idempotent generator if only this header is missing.
$(SOUND_DOSOUND): $(SOUND_DATA)
	@test -f $@ || $(PY) render/atari/gen_sound_fixture.py

$(CAND): $(SRC) $(wildcard include/*.h) $(SOUND_DATA)
	@mkdir -p build
	$(CC) $(CFLAGS) -shared $(SRC) -o $(CAND)

# The reference .so (verified cores) — built by recreate's own Makefile.
$(RECON):
	$(MAKE) -C $(RECREATE) build/libbuggyboy.so

# The m68k bench.elf (native cores + asm + bench wrappers). Rebuilt when any core, the asm, the bench
# wrappers, OR the build glue (os.s / shim / linker script / build script / shim headers) change — so a
# flag or glue edit can't leave a stale elf under `make test`. bench_build.sh regenerates the fixture.
$(BENCH_ELF): $(SRC) $(wildcard src/asm/*.S) render/atari/bench_main.c render/atari/os.s \
              render/atari/shim.c render/atari/tos.ld render/atari/bench_build.sh \
              $(wildcard render/atari/shim_include/*) $(wildcard include/*.h) $(SOUND_DATA)
	bash render/atari/bench_build.sh

.PHONY: ref test bench clean
# Sanity-check the reference capture: prove recreate's render pipeline is deterministic per frame.
ref: $(RECON)
	$(PY) test/capture_ref.py

# Run the equivalence suite (candidate framebuffers vs recreate references). Green = pixel-identical.
# bench.elf is a prerequisite so test_asm_blit.py's Musashi differential always runs (a missing elf
# fails that suite loudly with a build hint rather than skipping — see test_asm_blit.py).
PYTEST_ARGS ?= -n auto --dist worksteal
test: $(CAND) $(RECON) $(BENCH_ELF)
	$(PY) -m pytest -q $(PYTEST_ARGS) test

# Cycle cost vs the original and vs recon on-target (once a cross-compiled build exists). bench.py loads
# the m68k bench.elf and jumps its bench_* wrappers, so it is a prerequisite (a stale/absent elf otherwise
# KeyErrors on the newer bench symbols).
bench: $(CAND) $(BENCH_ELF)
	$(PY) tools/bench.py

clean:
	rm -rf build
