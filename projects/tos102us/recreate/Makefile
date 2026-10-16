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

# HOW THE SUITE IS SPREAD OVER THE WORKERS (`--dist worksteal`) is test/conftest.py's, not a PYTEST_ARGS of this file:
# every override of PYTEST_ARGS (`make test PYTEST_ARGS="-n4 -k fuzz"`) would drop it, and `make guarded` has its own.

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
# The blank pre-init machine (below) — named HERE because the snapshot's rule reads it as an order-only prerequisite
# (its vet boots the ROM from it), and a rule's prerequisites are expanded where the rule is read.
PREINIT := build/preinit.bin

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

# ---- THE STORE: WHAT A FROM-EMPTY BUILD NEED NOT MAKE AGAIN (the user's ruling (b), 2026-10-15) ----------------------------
# kept/ (gitignored, beside build/ and never under it: moving build/ aside or `make clean` leaves it) holds
#   * kept/captures/<key>/ — each Hatari capture below (the snapshot, the five pre-init machines), KEYED by the digest of
#     its own rule's prerequisites (the ROM image, the capture tools, the content stamps of the constants they read,
#     the disk it is captured with), of the workspace modules those tools import, of the Hatari that runs them and of
#     the kit's oracle — by CONTENT, so an edit of any of them is another key and the capture is made again (a `touch`
#     re-runs the recipe and is served);
#   * kept/derived/ — test/derived.py's cache (its ROOT), keyed by itself: the tree, the captures' bytes among it.
# A capture's recipe is `$(FROM_THE_STORE) || <the capture>`, then `$(INTO_THE_STORE)`: served where its key is kept,
# made where it is not, and a MADE one kept (a served one is the entry's own bytes, never copied back). The snapshot's
# is `$(FROM_THE_STORE) && <its vet> || <the capture, vetted>`: a served snapshot is vetted too, and one refused is
# captured again and replaces the entry (the vet: the snapshot's rule, below).
# THE KEY IS READ ONCE, BEFORE THE CAPTURE (into `$@.key`), and the capture is kept only if the key read again after it
# is the same: an edit to a keyed file DURING the capture (4-15 s of real time; three agents edit this tree) would
# otherwise keep a capture of the old content under the new content's key, served to every gate after (the gate-speed
# review's race). Such a capture is removed instead, so the next make captures it again.
# EACH ENTRY HAS ITS DIGEST BESIDE IT (`<entry>.sha256`, written as the entry is kept): an entry its digest does not
# match is not served but made again. Both are written to a temporary name and RENAMED into place, never written over:
# a make reading the entry meanwhile reads the whole of the old one.
# `FRESH=1` (`make gates FRESH=1`, at a band's boundary) RE-MAKES EVERYTHING FROM NOTHING, as before the store, WHATEVER
# build/ HOLDS: the captures are phony then (HATARI_CAPTURES, below), so each is made by Hatari again and REPLACES the
# kept one (the authors' runs that follow and the next gate share it), and the derivations are made into build/derived/
# — under a tree key no run made before, since no two captures are bit-identical. `FRESH=0` (or empty) is not FRESH.
# WHAT A DEFAULT GATE NO LONGER PROVES: that the suite holds over FRESH captures (README: two captures are never
# bit-identical; preinit-twice still boots all five pre-init machines again and holds the mask to them), nor that every
# kept answer is made again from nothing (each process still makes its sample of the answers again, held equal).
# A CAPTURE IS KEPT AS IT IS MADE, before any suite has run over it. The one bad class known (a snapshot whose screen
# manager is parked where no history of ours leaves it) is refused by the snapshot's vet, served or made; a capture of
# another bad class would be served red to every default gate of its key until FRESH=1 replaced it. The guard to add if
# one appears: keep the captures into the store from a GREEN gate only (the review's F4; not taken while the vet covers
# every bad class seen).
STORE := kept
CAPTURE_STORE := $(STORE)/captures
FRESH_RUN := $(filter-out 0,$(strip $(FRESH)))
# THE EMULATOR the captures run, not the script on the PATH: Homebrew's `hatari` is two lines that `exec` the app
# bundle's binary, and a key that read the script would see the install's path and version, not the program.
HATARI_ON_PATH := $(realpath $(shell command -v hatari))
HATARI := $(or $(shell sed -n 's/^exec "\([^"]*\)".*/\1/p' $(HATARI_ON_PATH) 2>/dev/null),$(HATARI_ON_PATH))
# AND ITS CONFIGURATION, which no capture tool overrides (no `-c`; HOME is kept): the user's file sets the CPU's cycle
# exactness, the floppy's speed, the fast boot — each a change to what a boot produces. Spelt with `?` for the space in
# its directory's name (a make word cannot hold one; the shell's glob and make's `wildcard` both match it). Where the
# file is not, nothing is keyed for it: Hatari then runs on its defaults.
HATARI_CONFIG := $(HOME)/Library/Application?Support/Hatari/hatari.cfg
CAPTURES_MADE_BY := ../../../tools/st_build.py ../../../tools/hatari_headless.py tools/addrs.py $(HATARI) $(ORACLE) \
                    $(if $(wildcard $(HATARI_CONFIG)),$(HATARI_CONFIG))
CAPTURE_KEY = $$({ echo '$@'; shasum -a 256 $(sort $^ $(CAPTURES_MADE_BY)); } | shasum -a 256 | cut -c1-40)
STORED_CAPTURE = $(CAPTURE_STORE)/$$(cat $@.key)/$(notdir $@)
DIGEST_OF = $$(shasum -a 256 < $(1) | cut -c1-64)
FROM_THE_STORE = echo $(CAPTURE_KEY) > $@.key && [ -z "$(FRESH_RUN)" ] && stored=$(STORED_CAPTURE) && [ -f "$$stored" ] \
	&& [ "$(call DIGEST_OF,"$$stored")" = "$$(cat "$$stored.sha256" 2>/dev/null)" ] && cp "$$stored" $@ && echo "$@: kept, $$stored"
INTO_THE_STORE = stored=$(STORED_CAPTURE) && { cmp -s $@ "$$stored" || $(KEPT_IF_STILL_ITS_KEY); }; status=$$?; rm -f $@.key; exit $$status
KEPT_IF_STILL_ITS_KEY = if [ "$$(cat $@.key)" = "$(CAPTURE_KEY)" ]; then \
	  mkdir -p "$$(dirname "$$stored")" && cp $@ "$$stored.$$$$" && echo "$(call DIGEST_OF,$@)" > "$$stored.sha256.$$$$" \
	  && mv "$$stored.$$$$" "$$stored" && mv "$$stored.sha256.$$$$" "$$stored.sha256"; \
	else rm -f $@; echo "$@: NOT KEPT, AND REMOVED — a file it is keyed by changed while it was captured" >&2; false; fi
ifneq ($(FRESH_RUN),)
export AES_DERIVED_ROOT := $(CURDIR)/build/derived
endif

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

# A SNAPSHOT IS VETTED BEFORE IT IS KEPT (tools/vet_snapshot.py: its screen manager parked as the ROM's boot leaves
# it, under a second). Hatari's floppy makes each boot's start-up history its own, and some captures leave the screen
# manager parked where no history of ours does (2026-10-15: test_aes_takeover red, bench/tier3.py refused). One that
# fails, or that the capture tool refuses, is captured again, up to SNAPSHOT_ATTEMPTS times; then the build stops and
# nothing is kept. The vet and what it reads are ORDER-ONLY: they decide whether a capture is kept, not what is
# captured, so they are no part of its key. A SERVED capture is vetted as well (0.6 s; it catches an entry kept before
# the vet was): one refused is captured again, and the vetted capture replaces the entry.
SNAPSHOT_ATTEMPTS := 4
VET_SNAPSHOT = $(PY) tools/vet_snapshot.py $@
CAPTURE_VETTED = for attempt in $$(seq $(SNAPSHOT_ATTEMPTS)); do \
	  $(PY) tools/boot_snapshot.py --out $@ && $(VET_SNAPSHOT) && exit 0; \
	done; rm -f $@; echo "$@: no capture of $(SNAPSHOT_ATTEMPTS) passed tools/vet_snapshot.py" >&2; exit 1

$(SNAPSHOT): tools/boot_snapshot.py $(SNAPSHOT_INPUTS) $(ROM_IMAGE) | tools/vet_snapshot.py $(PREINIT) $(CAND) $(ORACLE)
	@$(FROM_THE_STORE) && $(VET_SNAPSHOT) || ($(CAPTURE_VETTED))
	@$(INTO_THE_STORE)

.PHONY: snapshot
snapshot: $(SNAPSHOT)

# THE PRE-INIT MACHINES (tools/preinit_snapshot.py): the same machine stopped a boot earlier, at the AES's entry — what
# test/aes_boot.py boots the ROM's own gem_main from. TWO, each four seconds of Hatari, once: with the snapshot's blank
# floppy in the drive (the desk's machine), and with the test accessories' (tools/accessory_disk.py) in it FROM POWER-ON
# (the accessory machine: GEMDOS's cache and the driver's record are then that disk's own, nothing swapped in).
# Build products of their OWN: the snapshot above, its rule and everything derived from it are untouched, and their
# names are outside every pattern of test/derived.py's tree key, so capturing them moves no kept derivation —
# test/aes_boot.py's are keyed by their CONTENT. The suites ask for them as they ask for the snapshot: a test that
# needs one fails on a missing file, it does not skip.
#
# THEIR OWN CONTENT STAMP of the header constants the tool reads, made as the snapshot's is (a word added to
# SNAPSHOT_CONSTANTS would capture the snapshot again, which this must never do).
PREINIT_ACC := build/preinit_acc.bin
ACC_DISK := build/acc/ACCDISK.ST
PREINIT_INPUTS := build/preinit_inputs.txt
PREINIT_CONSTANTS := ST_RAM_BYTES AES_ROM_GEM_ENTRY SR_SUPERVISOR SHIFTER_PALETTE SHIFTER_PALETTE_ENTRIES SHIFTER_RESOLUTION
PREINIT_TOOL := tools/preinit_snapshot.py tools/boot_snapshot.py

.PHONY: preinit-inputs
preinit-inputs:
	@mkdir -p $(dir $(PREINIT_INPUTS))
	@$(PY) tools/addrs.py $(PREINIT_CONSTANTS) > $(PREINIT_INPUTS).new
	@cmp -s $(PREINIT_INPUTS).new $(PREINIT_INPUTS) \
	  && rm -f $(PREINIT_INPUTS).new \
	  || mv $(PREINIT_INPUTS).new $(PREINIT_INPUTS)

$(PREINIT_INPUTS): preinit-inputs ;

$(PREINIT): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE)
	@$(FROM_THE_STORE) || $(PY) tools/preinit_snapshot.py --out $@
	@$(INTO_THE_STORE)

$(ACC_DISK): tools/accessory_disk.py test/acc/testacc.S test/acc/acc.ld atari/mkprg.py include/gemdos/pexec_load.h
	$(PY) tools/accessory_disk.py --out $@

$(PREINIT_ACC): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(ACC_DISK)
	@$(FROM_THE_STORE) || $(PY) tools/preinit_snapshot.py --disk $(ACC_DISK) --work build/preinit_acc_snapshot --out $@
	@$(INTO_THE_STORE)

# THE SEVEN-ACCESSORY PRE-INIT MACHINE (band 5 wave 3): a THIRD capture, with seven test accessories in the drive from
# power-on — one more than the loader takes — for the loader's at-most-six arm, five allocated PDs and the EVB supply
# run out. Its own disk, its own scratch directory, four more seconds of Hatari, once. NOT among REGISTRY_READS: no
# registered row is made from it (the registry's import does not read the file), so only the suites ask for it.
PREINIT_ACC7 := build/preinit_acc7.bin
ACC7_DISK := build/acc/ACC7DISK.ST

$(ACC7_DISK): tools/accessory_disk.py test/acc/testacc.S test/acc/acc.ld atari/mkprg.py include/gemdos/pexec_load.h
	$(PY) tools/accessory_disk.py --seven --out $@

$(PREINIT_ACC7): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(ACC7_DISK)
	@$(FROM_THE_STORE) || $(PY) tools/preinit_snapshot.py --disk $(ACC7_DISK) --work build/preinit_acc7_snapshot --out $@
	@$(INTO_THE_STORE)

# THE DESKTOP.INF PRE-INIT MACHINE (band 5 wave 4, ruling W4-R7): a FOURTH capture, with the blank disk plus the ROM's
# own default DESKTOP.INF in the drive from power-on and no accessory — what the `#E` reader's FILE arm, its `#E`
# parse and app_reschange in place are booted over, and (its view pair patched in the image) a drive window whose
# items are drawn through ub_trampoline. Its own disk, its own scratch directory, four more seconds of Hatari, once.
# The disk needs the ROM image (the text is cut out of it). AMONG REGISTRY_READS since slice B registered rows made of it.
PREINIT_INF := build/preinit_inf.bin
INF_DISK := build/acc/INFDISK.ST

$(INF_DISK): tools/accessory_disk.py $(ROM_IMAGE)
	$(PY) tools/accessory_disk.py --inf --out $@

$(PREINIT_INF): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(INF_DISK)
	@$(FROM_THE_STORE) || $(PY) tools/preinit_snapshot.py --disk $(INF_DISK) --work build/preinit_inf_snapshot --out $@
	@$(INTO_THE_STORE)

# ---- BEGIN band 6 wave 0, slice H: THE FILES PRE-INIT MACHINE (ruling W6-R10) — a FIFTH capture -------------------------------
# With the files disk in the drive from power-on (tools/accessory_disk.py --files: the ROM's default DESKTOP.INF, a text
# longer than the viewer's page, a program and the folder AUTO with a file in it; no accessory): what the desk's own
# acts — a file shown, a folder opened, a copy, a delete — are continued over (test/aes_desk.py). Its own disk, its
# own scratch directory, four more seconds of Hatari, once. NOT among REGISTRY_READS: no registered row is made of it.
PREINIT_FILES := build/preinit_files.bin
FILES_DISK := build/acc/FILESDISK.ST

$(FILES_DISK): tools/accessory_disk.py test/acc/testacc.S test/acc/acc.ld atari/mkprg.py include/gemdos/pexec_load.h $(ROM_IMAGE)
	$(PY) tools/accessory_disk.py --files --out $@

$(PREINIT_FILES): $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(FILES_DISK)
	@$(FROM_THE_STORE) || $(PY) tools/preinit_snapshot.py --disk $(FILES_DISK) --work build/preinit_files_snapshot --out $@
	@$(INTO_THE_STORE)

.PHONY: preinit-files
preinit-files: $(PREINIT_FILES)
test guarded gates: $(PREINIT_FILES)
preinit-twice: $(FILES_DISK)
# ---- END band 6 wave 0, slice H -----------------------------------------------------------------------------------------------

# EVERY HATARI CAPTURE, made again under FRESH whatever build/ holds (THE STORE, above): phony then, so make runs each
# recipe, and the recipe serves nothing.
HATARI_CAPTURES = $(SNAPSHOT) $(PREINIT) $(PREINIT_ACC) $(PREINIT_ACC7) $(PREINIT_INF) $(PREINIT_FILES)
ifneq ($(FRESH_RUN),)
.PHONY: $(HATARI_CAPTURES)
endif

.PHONY: preinit preinit-acc preinit-acc7 preinit-inf
preinit: $(PREINIT)
preinit-acc: $(PREINIT_ACC)
preinit-acc7: $(PREINIT_ACC7)
preinit-inf: $(PREINIT_INF)

# THE MASK HELD TO THE CAPTURES (`make preinit-twice`): each of the five machines booted TWICE MORE, into a directory of
# its own — never over a capture above, which the suites and the registry read — and the two machines held equal
# outside `preinit_snapshot.MASK`, registers and palette included (`--twice` exits non-zero and names every unmasked
# byte). A prerequisite of `gates` alone: `make test` stays the suites.
# THE FIVE PAIRS RUN SIDE BY SIDE, each into its own directory, log and status (the `gates` recipe's arrangement): a
# capture is four seconds of REAL TIME in Hatari, not of CPU, so five at once take one pair's wall — measured 8-9 s
# against 40 s in turn, every verdict "identical" (gate-speed pass, 2026-10-15). Each log is printed after, in turn.
PREINIT_TWICE_DIR := build/preinit_twice
PREINIT_TWICE := $(PY) tools/preinit_snapshot.py --twice
TWICE_RAN = > $(PREINIT_TWICE_DIR)/$(1).log 2>&1; echo $$? > $(PREINIT_TWICE_DIR)/$(1).status
TWICE_PAIRS := blank acc acc7 inf files

.PHONY: preinit-twice
preinit-twice: $(PREINIT_TOOL) $(PREINIT_INPUTS) $(ROM_IMAGE) $(ACC_DISK) $(ACC7_DISK) $(INF_DISK)
	@mkdir -p $(PREINIT_TWICE_DIR) && rm -f $(PREINIT_TWICE_DIR)/*.status
	@( $(PREINIT_TWICE) --work $(PREINIT_TWICE_DIR)/blank --out $(PREINIT_TWICE_DIR)/blank.bin $(call TWICE_RAN,blank) ) & \
	 ( $(PREINIT_TWICE) --disk $(ACC_DISK) --work $(PREINIT_TWICE_DIR)/acc --out $(PREINIT_TWICE_DIR)/acc.bin $(call TWICE_RAN,acc) ) & \
	 ( $(PREINIT_TWICE) --disk $(ACC7_DISK) --work $(PREINIT_TWICE_DIR)/acc7 --out $(PREINIT_TWICE_DIR)/acc7.bin $(call TWICE_RAN,acc7) ) & \
	 ( $(PREINIT_TWICE) --disk $(INF_DISK) --work $(PREINIT_TWICE_DIR)/inf --out $(PREINIT_TWICE_DIR)/inf.bin $(call TWICE_RAN,inf) ) & \
	 ( $(PREINIT_TWICE) --disk $(FILES_DISK) --work $(PREINIT_TWICE_DIR)/files --out $(PREINIT_TWICE_DIR)/files.bin $(call TWICE_RAN,files) ) & \
	 wait
	@failed=0; for pair in $(TWICE_PAIRS); do \
	   echo "== preinit-twice $$pair: exit status $$(cat $(PREINIT_TWICE_DIR)/$$pair.status)"; \
	   cat $(PREINIT_TWICE_DIR)/$$pair.log; \
	   [ "$$(cat $(PREINIT_TWICE_DIR)/$$pair.status)" = 0 ] || failed=1; \
	 done; exit $$failed

gates: preinit-twice

test guarded gates: $(PREINIT) $(PREINIT_ACC) $(PREINIT_ACC7) $(PREINIT_INF)
# ...AND SO DOES EVERY TARGET WHOSE RECIPE IMPORTS THE REGISTRY (`test_boot_snapshot`: bench/shipped_glue.py,
# test/derived.py, bench/tier3.py): the screen manager's rows are registered FROM those machines (an arrival is the
# ROM's own run over one), so the import reads both files — and `gates`' own prerequisites above come AFTER its
# recipe rule's, whose first leaf is `shipped-glue`. Named once, used by the three rules below
# (`test/test_makefile.py` holds that no importer of the registry is without them).
# ...AND THE FOURTH SINCE BAND 5 WAVE 4's SLICE B: the build's own start-up is priced over the DESKTOP.INF machine too
# (`test/aes_ourboot.py`: the reader's file arm), so the registry's import reads that capture.
REGISTRY_READS := $(SNAPSHOT) $(PREINIT) $(PREINIT_ACC) $(PREINIT_INF)

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
shipped-glue: $(CAND) $(ORACLE) $(REGISTRY_READS)
shipped-glue: | derived
	@$(PY) bench/shipped_glue.py $(SHIPPED_GLUE)

$(SHIPPED_GLUE): shipped-glue ;

$(SHIPPED_ELF): $(BENCH_SRC) $(SHIPPED_GLUE) $(PROJECT_HEADERS) \
                $(wildcard $(KIT)/include/*.h) $(wildcard atari/shim_include/*.h) atari/target.mk \
                $(KIT)/kit.mk $(KIT)/rom_bench.py $(PROJECT_CONFIG) $(PROJECT_MAKEFILE)
	rm -rf $(SHIPPED_OBJ) && mkdir -p $(SHIPPED_OBJ)
	printf '%s\n' $(BENCH_SRC) | xargs -P $(SHIPPED_JOBS) -n 1 sh -c \
	  'm68k-elf-gcc $(SHIPPED_CFLAGS) -c "$$0" -o $(SHIPPED_OBJ)/$$(echo "$$0" | tr ./ __).o'
	m68k-elf-gcc $(SHIPPED_CFLAGS) -Wl,--build-id=none -Wl,-e0 -Wl,-Ttext=$(BENCH_BASE) \
	  $(SHIPPED_OBJ)/*.o $(SHIPPED_GLUE) $(BENCH_LDLIBS) -o $@

$(SHIPPED_BIN): $(SHIPPED_ELF)
	m68k-elf-objcopy -O binary $(SHIPPED_ELF) $(SHIPPED_BIN)

# THE ROM-ONLY DERIVATIONS, MADE ONCE FOR THE TREE BEFORE ANY PROCESS THAT WILL ASK FOR THEM (`test/derived.py`): the
# registry's import is twenty-five seconds of the ROM's own runs, which the bench makes and every xdist worker of both
# suites makes again — unless they are kept. This step makes them over every core and keeps them under
# kept/derived/ (THE STORE, above), by content (a tree it was run for already costs it a tenth of a second); the table and both suites
# ask after it and are served. ORDER-ONLY for the table: it must come first, and must never be what rebuilds it.
# AND FOR THE GLUE, which imports the whole registry in ONE process: cold, that import was the build's longest serial
# stretch (65 s); made over every core first, it is 29 s and the glue's import 5 s (gate-speed pass, 2026-10-15). So the
# shipped blob is NOT among this step's prerequisites: no derivation reads it at import (the tree's key does not name
# it, and a warm with the blob present after one without it makes no new answer — measured, 1,978 kept either way).
.PHONY: derived
derived: $(CAND) $(ORACLE) $(REGISTRY_READS) $(BENCH_BIN)
	@$(PY) test/derived.py

# The measuring pass is spread over every core (`bench/tier3.py --jobs`, its default): the table is the one a single
# process writes, line for line.
$(BENCH_TABLE): bench/tier3.py $(wildcard test/*.py) $(BENCH_BIN) $(SHIPPED_BIN) $(CAND) $(ORACLE) $(REGISTRY_READS) | derived
	$(PY) bench/tier3.py --out $@

.PHONY: bench
bench: $(BENCH_TABLE)
	@cat $(BENCH_TABLE)

# Every differential reads the snapshot, so both suites capture it first rather than failing on a
# missing file (kit.mk owns the recipes; this only adds the prerequisite). `guarded` is the same
# suite under the guarded-image plugin, and it reads the snapshot at exactly the same import.
# The TABLE is a prerequisite too, because `test/test_status.py` pins STATUS.md's Tier 3 column
# against it — a pin that skipped for want of a file would be no pin at all.
test: $(SNAPSHOT) $(BENCH_TABLE) derived
guarded: $(SNAPSHOT) $(BENCH_TABLE) derived

# ---- THE GATES AS ONE COMMAND ------------------------------------------------------------------------------------------
# `make guarded`, `make bench` and the ROM build (`make -C atari -B all`) are run before every commit. They share ONE
# build — the libraries, both blobs, the snapshot, the table, the derivations — which is made first, once; what is
# left is two jobs that read it and write nothing the other reads (the suite its own log and its own pytest cache; the
# ROM build its own directory), so they run SIDE BY SIDE, and `gates` ends non-zero if either did, having printed each
# one's last lines. The same pytest command line as kit.mk's `guarded` (GUARDED_PYTEST_ARGS applies, given on the
# command line or in the environment; its default here is GATE_WORKERS, below), over the same files.
# THE GUARDED SUITE ONLY (the user's ruling (a'), 2026-10-15): `make test` runs the same tests with the same assertions
# over a plain bytearray candidate image where `guarded` puts PROT_NONE pages around it, so a run of both was the same
# CPU-bound work twice. WHAT THE GATE NO LONGER PROVES: that the suite passes over the plain image as `make test` builds
# it — an access that stays in bounds behaves the same in both. `make test` stays a target, for authors and by hand.
GATES_DIR := build/gates
GATE_LINES_SHOWN := 6
GATE_PYTEST = PYTHONPATH=$(KIT)/.. $(PY) -m pytest -q $(WATCHDOG_PLUGIN) -o cache_dir=$(GATES_DIR)/$(1).cache $(2) test
GATE_RAN = > $(GATES_DIR)/$(1).log 2>&1; echo $$? > $(GATES_DIR)/$(1).status
GATE_JOBS := guarded atari
# The ROM build's own make, NAMED HERE and not spelt `$$(MAKE)` in the recipe: a recipe line that spells it is run by
# `make -n` too (make's rule for recursive makes), and this one line starts the suite.
ROM_BUILD := $(MAKE) -C atari -B all
# THE SUITE'S WORKERS, unless the command line (or the environment) names GUARDED_PYTEST_ARGS: a worker per core, as
# many as the machine's memory holds at GATE_WORKER_BYTES each — a worker's measured peak (2.1 GB RSS, guarded alone at
# 10 workers) and the ~0.7 GB a compressed worker takes back when it touches its pages again. 10 on the 10-core 32 GB
# machine: summed workers' peak 11.2 GB, the compressor at 6.5 GB, no swap added (2026-10-15) — below the 5 + 5 of the
# two suites side by side that went before (7.7 GB compressed); kit.mk's `-n auto` x 2 had been SIGKILLed.
GATE_WORKER_BYTES := 3221225472
# (A `define`: test/test_makefile.py's reading of this file expands what a one-line definition holds, and a shell
# arithmetic's parentheses would stop it there.) The memory is Darwin's `sysctl -n hw.memsize`; elsewhere (Linux)
# `getconf`'s pages times their size.
define GATE_WORKERS_HELD
memory=$$(sysctl -n hw.memsize 2>/dev/null || echo $$(( $$(getconf _PHYS_PAGES) * $$(getconf PAGESIZE) ))); \
cores=$$(getconf _NPROCESSORS_ONLN); held=$$(( memory / $(GATE_WORKER_BYTES) )); echo $$(( held < 1 ? 1 : (held < cores ? held : cores) ))
endef
GATE_WORKERS := $(shell $(GATE_WORKERS_HELD))
GATE_GUARDED_ARGS := $(if $(filter command environment,$(firstword $(origin GUARDED_PYTEST_ARGS))),$(GUARDED_PYTEST_ARGS),-n $(GATE_WORKERS))

.PHONY: gates
gates: $(CAND) $(ORACLE) $(ASM_BIN) $(SNAPSHOT) $(BENCH_TABLE) derived
	@rm -rf $(GATES_DIR) && mkdir -p $(GATES_DIR)
	@( $(call GATE_PYTEST,guarded,$(GATE_GUARDED_ARGS) -p recreate_kit.guarded_image) $(call GATE_RAN,guarded) ) & \
	 ( $(ROM_BUILD) $(call GATE_RAN,atari) ) & \
	 wait
	@failed=0; for gate in $(GATE_JOBS); do \
	   echo "== $$gate: exit status $$(cat $(GATES_DIR)/$$gate.status) ($(GATES_DIR)/$$gate.log)"; \
	   tail -n $(GATE_LINES_SHOWN) $(GATES_DIR)/$$gate.log; \
	   [ "$$(cat $(GATES_DIR)/$$gate.status)" = 0 ] || failed=1; \
	 done; exit $$failed
