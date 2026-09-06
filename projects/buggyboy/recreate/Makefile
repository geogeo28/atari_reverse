# BuggyBoy reconstruction. The shared candidate/oracle/test rules live in the kit; this file
# only names the game and adds the BuggyBoy-specific reporting targets.
KIT  := ../../../tools/recreate_kit
GAME := buggyboy
include $(KIT)/kit.mk

.PHONY: audit bench coverage-gap

# Audit GRAPHICS.GRA for artwork the game never draws: build a read/write-instrumented copy of the
# reconstruction (through this Makefile's own rules, via the kit's EXTRA_CFLAGS/EXTRA_SRC hooks),
# drive every scene, then poison-prove the verdict. $(CAND) is a prerequisite because the script's
# `import harness` dlopens the PLAIN candidate before it builds the instrumented one.
# `make audit AUDIT_ARGS='--quick --out ../out/sprite_audit'`. See ../docs/sprite_audit.md.
AUDIT_ARGS ?=
audit: $(CAND) $(ORACLE)
	$(PY) ../tools/sprite_audit.py $(AUDIT_ARGS)

# Report sink call sites (Dosound/INITTUNE/INITFX/stop_music) that no test executes — off-image or
# fuzz-unreached sound/OS triggers the differential diff can't see. See tools/coverage_gap.py.
coverage-gap: $(CAND) $(ORACLE)
	$(PY) tools/coverage_gap.py

# Rank the per-frame in-race pipeline by its cost on the original 68000 (Musashi cycle count) — which
# function is the bottleneck. `make bench BENCH_ARGS='2 100'` picks leg/warmup. See tools/bench_frame.py.
BENCH_ARGS ?=
bench: $(CAND) $(ORACLE)
	$(PY) tools/bench_frame.py $(BENCH_ARGS)
