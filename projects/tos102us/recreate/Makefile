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

# kit.mk's two compile rules depend on `include/*.h`, which is only this project's SHARED headers:
# a component's own sit one level down (include/bios/, include/xbios/, include/gemdos/), and an edit
# to one of them must rebuild both the candidate and the Tier 3 blob just as a top-level one does.
COMPONENT_HEADERS := $(wildcard include/*/*.h)
$(CAND): $(COMPONENT_HEADERS)
$(BENCH_ELF): $(COMPONENT_HEADERS)

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

# THE SHIPPED CONFIGURATION — Tier 3's SECOND blob, for the C that calls a transcribed core. A shipped ROM
# links a routine's `.S` in place of its C twin (`include/transcribed.h`), so the C that calls one
# reaches the ROM's instructions through glue; $(BENCH_ELF) links the C twins beside the `.S` and would
# price every such caller with the twin's cycles in it. This blob is the same sources built the way the
# ROM build will be (`-ffunction-sections`, atari/target.mk), with every transcribed core WEAK
# (`TRANSCRIBED_CORES_WEAK`, the header says why it is the source's attribute) and a GENERATED thunk of
# the same name linked beside it (`bench/shipped_glue.py`): each call lands in the thunk, and the thunk
# enters the `.S`. `bench/tier3.py` measures every row whose C reaches a transcribed core on this blob
# (legend `through`), which is also the glue's own differential.
#
# The glue is regenerated every make and REWRITTEN only when its text changes (`snapshot-inputs`'s
# arrangement): it is derived from test/*.py, and a dependency on those would relink the blob for every
# edit to a battery.
SHIPPED_DIR    := build/bench_shipped
SHIPPED_ELF    := $(SHIPPED_DIR)/bench.elf
SHIPPED_BIN    := $(SHIPPED_DIR)/bench.bin
SHIPPED_GLUE   := $(SHIPPED_DIR)/glue.S
SHIPPED_OBJ    := $(SHIPPED_DIR)/obj
SHIPPED_CFLAGS := $(BENCH_CFLAGS) -ffunction-sections -DTRANSCRIBED_CORES_WEAK
# The per-source compiles are independent, so they run side by side: one `m68k-elf-gcc` per source.
SHIPPED_JOBS   := 8

.PHONY: shipped-glue
shipped-glue: $(CAND) $(SNAPSHOT)
	@$(PY) bench/shipped_glue.py $(SHIPPED_GLUE)

$(SHIPPED_GLUE): shipped-glue ;

$(SHIPPED_ELF): $(BENCH_SRC) $(SHIPPED_GLUE) $(wildcard include/*.h) $(COMPONENT_HEADERS) \
                $(wildcard $(KIT)/include/*.h) $(wildcard atari/shim_include/*.h) atari/target.mk \
                $(KIT)/kit.mk $(KIT)/rom_bench.py $(PROJECT_CONFIG) $(PROJECT_MAKEFILE)
	rm -rf $(SHIPPED_OBJ) && mkdir -p $(SHIPPED_OBJ)
	printf '%s\n' $(BENCH_SRC) | xargs -P $(SHIPPED_JOBS) -n 1 sh -c \
	  'm68k-elf-gcc $(SHIPPED_CFLAGS) -c "$$0" -o $(SHIPPED_OBJ)/$$(echo "$$0" | tr ./ __).o'
	m68k-elf-gcc $(SHIPPED_CFLAGS) -Wl,--build-id=none -Wl,-e0 -Wl,-Ttext=$(BENCH_BASE) \
	  $(SHIPPED_OBJ)/*.o $(SHIPPED_GLUE) $(BENCH_LDLIBS) -o $@

$(SHIPPED_BIN): $(SHIPPED_ELF)
	m68k-elf-objcopy -O binary $(SHIPPED_ELF) $(SHIPPED_BIN)

$(BENCH_TABLE): bench/tier3.py $(wildcard test/*.py) $(BENCH_BIN) $(SHIPPED_BIN) $(CAND) $(ORACLE) $(SNAPSHOT)
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
