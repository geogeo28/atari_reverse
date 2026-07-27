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
STE_SRC := src/blitter.c src/blitter_objshift2.c src/blitter_objshift.c src/blitter_selftest.c src/blitter_sweep.c \
           src/blitter_skew.c src/blitter_scroll.c src/blitter_dash.c src/blitter_census.c
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

# --- the on-target BUILD GATE (harness gap #2) ---------------------------------------------------
# Until this existed, `make test` compiled the game shell for NOBODY: render/atari/game_main.c (1721
# lines — every asset binding and every TOS seam) is in neither the host .so (SRC is src/*.c) nor
# bench.elf (bench_build.sh links a 17-file src/ subset), and four more src/ files — frame, flow,
# intermission, results — are in the host .so but not in bench.elf. build_game.sh did compile all of
# them; nothing in the gate ever RAN it. A shell that did not compile therefore reached origin twice in
# one session with the suite green. These targets build the real .PRG (~2 s each; the m68k toolchain is
# already a hard prerequisite via bench.elf), so a broken shell fails `make test`, not a play-test.
#
# They build under gate-only names so the shipping BUGGYBOY.PRG is never clobbered, with GAME_NO_STAGE
# so they never touch the Hatari drive, and they reuse build_game.sh rather than restating its flags —
# a third copy of the cross flags would be exactly the kind of drift this gate exists to catch.
#
# TWO builds because the stock one cannot reach every source: src/blitter_{selftest,sweep,census}.c are
# compiled only under their own measurement flags. Those three combine in ONE extra build (they are
# alternate main() entry points, and the gate only asks whether they compile and link), so between them
# the two builds cover every .c in the project.
GATE_PRG      := render/atari/build/GATE.PRG
GATE_MEAS_PRG := render/atari/build/GATEMEAS.PRG
# Everything the built .PRG is derived from — including the GENERATORS and the fixture's struct source
# (test/adapter.py bakes the asset windows), because a stale gate that skips its rebuild is worth
# nothing. That is not hypothetical: an adapter.py window change is precisely what shipped the truncated
# font fixture.
GATE_DEPS := $(SRC) $(STE_SRC) $(wildcard src/asm/*.S) render/atari/game_main.c render/atari/shim.c \
             render/atari/os.s render/atari/tos.ld render/atari/build_game.sh \
             render/atari/gen_game_fixture.py render/atari/gen_hud_fixture.py \
             render/atari/fixture_lib.py render/atari/mkprg.py \
             test/adapter.py test/equiv.py test/assets_load.py $(RECREATE)/render/render_screen.py \
             $(wildcard render/atari/shim_include/*) $(wildcard render/atari/*.h) \
             $(wildcard include/*.h) $(SOUND_DATA) $(CAND) $(RECON)

# ORDER-ONLY chain (the `|` prerequisites): build_game.sh and bench_build.sh share fixed-name
# intermediates in render/atari/build/ (game_fixture.h, game.elf, game.bin), so two of them running
# concurrently under `make -j` would clobber each other — and could wrap one build's .bin into the
# other's .PRG, i.e. a green gate that validated nothing. The chain serialises the three m68k builds
# without serialising the rest of the Makefile.
$(GATE_PRG): $(GATE_DEPS) | $(BENCH_ELF)
	GAME_NO_STAGE=1 GAME_PRG=$(notdir $(GATE_PRG)) bash render/atari/build_game.sh

$(GATE_MEAS_PRG): $(GATE_DEPS) | $(GATE_PRG)
	GAME_NO_STAGE=1 GAME_STE_SELFTEST=1 GAME_STE_SWEEP=1 GAME_STE_CENSUS=1 \
	    GAME_PRG=$(notdir $(GATE_MEAS_PRG)) bash render/atari/build_game.sh

.PHONY: ref test gate golden bench clean
# Build the shell both ways without running the suite (the gate alone).
gate: $(GATE_PRG) $(GATE_MEAS_PRG)
# Sanity-check the reference capture: prove recreate's render pipeline is deterministic per frame.
ref: $(RECON)
	$(PY) test/capture_ref.py

# Run the equivalence suite (candidate framebuffers vs recreate references). Green = pixel-identical.
# bench.elf is a prerequisite so test_asm_blit.py's Musashi differential always runs (a missing elf
# fails that suite loudly with a build hint rather than skipping — see test_asm_blit.py).
PYTEST_ARGS ?= -n auto --dist worksteal
test: $(CAND) $(RECON) $(BENCH_ELF) $(GATE_PRG) $(GATE_MEAS_PRG)
	$(PY) -m pytest -q $(PYTEST_ARGS) test

# The END-TO-END pin: build GOLDEN.PRG per leg, run it in Hatari, byte-compare its frame 0 against
# recreate's whole ported pipeline. It is NOT part of `make test` — it needs Hatari installed and takes
# ~20 s for the five legs — but it is the only check that runs the shipped shell on a 68000, so run it
# before promoting to main. `make gate` already proves the same build compiles and links.
golden: $(CAND) $(RECON) | $(GATE_MEAS_PRG)
	$(PY) render/atari/run_golden.py

# Cycle cost vs the original and vs recon on-target (once a cross-compiled build exists). bench.py loads
# the m68k bench.elf and jumps its bench_* wrappers, so it is a prerequisite (a stale/absent elf otherwise
# KeyErrors on the newer bench symbols).
bench: $(CAND) $(BENCH_ELF)
	$(PY) tools/bench.py

clean:
	rm -rf build
