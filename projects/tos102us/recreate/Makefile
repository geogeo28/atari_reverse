# TOS 1.02 US reconstruction. The shared candidate/oracle/test rules live in the kit; this file
# names the project and the one thing a ROM project has that a game does not: the post-boot RAM
# snapshot its differentials run over.
KIT  := ../../../tools/recreate_kit
GAME := tos102us

# TIER 3's NUMERATOR: the same cores, built for the 68000 and run under the same oracle, so every
# verified function carries a `recreate / original` cycle ratio and not just the original's cost.
# kit.mk owns the rules (`bench_base` in project.toml turns them on); the FLAGS are the shipped ROM
# build's own, read from the one file that states them, because a numerator measured under other
# flags is a number about a program nobody runs. Set BEFORE the include, which is where kit.mk reads
# them, including the include-path list: the ROM build and this one compile the cores against the
# same headers by construction rather than by two lists agreeing.
RECREATE := .
include atari/target.mk
BENCH_CFLAGS := $(TARGET_CFLAGS) $(TARGET_INCLUDES)
BENCH_LDLIBS := $(TARGET_LDLIBS)

include $(KIT)/kit.mk

# ...and the one prerequisite kit.mk cannot know: the target header shadows the cores compile
# against. (`project.toml` and this makefile are kit.mk's own prerequisites of the same rule, and
# atari/target.mk is reached through this file.)
$(BENCH_ELF): $(wildcard atari/shim_include/*.h) atari/target.mk

# The snapshot is a BUILD PRODUCT, captured out of headless Hatari from the user's own ROM — which
# is why it is a make rule and not a checked-in file (the ROM is Atari's, and so is its RAM image).
# Capturing costs ~15 s of real time per run, because emulation is real time; it happens once, and
# again only when the tool that defines the stop point changes.
SNAPSHOT := build/boot_ram.bin

# WHAT THE CAPTURE REALLY DEPENDS ON, which is not include/addrs.h. tools/boot_snapshot.py parses
# that header, but it reads exactly TWO of its nine hundred constants — the machine's size and the
# vector slot the capture stops in — and every wave edits the header. A prerequisite on the whole
# file therefore re-ran 15 s of real emulation for an edit to a GEMDOS address the capture never
# looks at, and, with two agents' makes running in one tree, made them race on the capture (wave 8:
# the first one failed at $cc46 while the second was writing the file).
#
# So the prerequisite is a CONTENT STAMP of those two values, rewritten only when it differs — and
# the ROM itself, which really is an input and was not named at all.
SNAPSHOT_INPUTS := build/snapshot_inputs.txt
SNAPSHOT_CONSTANTS := ST_RAM_BYTES VECTOR_VBL
ROM_IMAGE := ../../../tools/hatari/TOS102US.img

.PHONY: snapshot-inputs
snapshot-inputs:
	@mkdir -p $(dir $(SNAPSHOT_INPUTS))
	@$(PY) tools/addrs.py $(SNAPSHOT_CONSTANTS) > $(SNAPSHOT_INPUTS).new
	@cmp -s $(SNAPSHOT_INPUTS).new $(SNAPSHOT_INPUTS) \
	  && rm -f $(SNAPSHOT_INPUTS).new \
	  || mv $(SNAPSHOT_INPUTS).new $(SNAPSHOT_INPUTS)

# An order-only-free dependency on the phony above: the recipe runs every make, and the FILE's
# timestamp moves only when one of the two values really changed.
$(SNAPSHOT_INPUTS): snapshot-inputs ;

$(SNAPSHOT): tools/boot_snapshot.py $(SNAPSHOT_INPUTS) $(ROM_IMAGE)
	$(PY) tools/boot_snapshot.py --out $@

.PHONY: snapshot
snapshot: $(SNAPSHOT)

# TIER 3's table: every verified function's `recreate / original` cycle ratio. It runs the ORIGINAL
# too, so it needs the snapshot exactly as the suites do; `bench/tier3.py` exits non-zero on a row
# the gate refuses or a verified case nobody priced, and `test/test_tier3.py` is the same registry
# run by `make test`.
#
# THE TABLE IS A FILE AND ONLY THE PRINTING IS PHONY, which is what lets STATUS.md's Tier 3 column be
# PINNED against it (`test/test_status.py`): a ledger quoting numbers nothing re-derives is the shape
# that goes stale, and a target with no file has nothing to read. Its prerequisites are every input
# of the measurement — the blob, both .so files, the snapshot, the registry, and `test/` because the
# ROWS are `test_boot_snapshot.VERIFIED_CASES` (see bench/tier3.py).
BENCH_TABLE := $(BENCH_DIR)/tier3.txt

$(BENCH_TABLE): bench/tier3.py $(wildcard test/*.py) $(BENCH_BIN) $(CAND) $(ORACLE) $(SNAPSHOT)
	$(PY) bench/tier3.py --out $@

.PHONY: bench
bench: $(BENCH_TABLE)
	@cat $(BENCH_TABLE)

# Every differential reads the snapshot, so both suites capture it first rather than failing on a
# missing file (kit.mk owns the recipes; this only adds the prerequisite). `guarded` is the same
# suite under the guarded-image plugin, and it reads the snapshot at exactly the same import.
# The TABLE is a prerequisite too, because `test/test_status.py` pins STATUS.md's Tier 3 column
# against it — a pin that skipped for want of a file would be no pin at all.
test: $(SNAPSHOT) $(BENCH_TABLE)
guarded: $(SNAPSHOT) $(BENCH_TABLE)
