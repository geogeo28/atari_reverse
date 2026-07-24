# Build the remaster host lib and validate it pixel-identical to the verified recreate/ cores.
# The reference framebuffers come from recreate's libbuggyboy.so, so we reuse recreate's venv
# (ctypes + numpy already pinned there) and build recreate first.
CC      ?= clang
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -Iinclude
RECREATE := ../recreate
PY       := $(RECREATE)/.venv/bin/python

CAND    := build/libremaster.so
SRC     := $(wildcard src/*.c)
RECON   := $(RECREATE)/build/libbuggyboy.so
# The cross-compiled m68k bench.elf — needed by test/test_asm_blit.py (the Musashi differential that
# pins the hand-asm objshift2 core byte-exact vs the C reference; PERF30 A3). Built by bench_build.sh.
BENCH_ELF := render/atari/build/bench.elf

$(CAND): $(SRC) $(wildcard include/*.h)
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
              $(wildcard render/atari/shim_include/*) $(wildcard include/*.h)
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

# Cycle cost vs the original and vs recon on-target (once a cross-compiled build exists).
bench: $(CAND)
	$(PY) tools/bench.py

clean:
	rm -rf build
