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

$(CAND): $(SRC) $(wildcard include/*.h)
	@mkdir -p build
	$(CC) $(CFLAGS) -shared $(SRC) -o $(CAND)

# The reference .so (verified cores) — built by recreate's own Makefile.
$(RECON):
	$(MAKE) -C $(RECREATE) build/libbuggyboy.so

.PHONY: ref test bench clean
# Sanity-check the reference capture: prove recreate's render pipeline is deterministic per frame.
ref: $(RECON)
	$(PY) test/capture_ref.py

# Run the equivalence suite (candidate framebuffers vs recreate references). Green = pixel-identical.
PYTEST_ARGS ?= -n auto --dist worksteal
test: $(CAND) $(RECON)
	$(PY) -m pytest -q $(PYTEST_ARGS) test

# Cycle cost vs the original and vs recon on-target (once a cross-compiled build exists).
bench: $(CAND)
	$(PY) tools/bench.py

clean:
	rm -rf build
