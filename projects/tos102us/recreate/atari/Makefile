# Makefile — the rebuilt TOS 1.02 ROM image and the two programs that measure a ROM from inside it.
#
#   make             build/TOS102RC.IMG, TOSTEST.PRG, TOSBENCH.PRG and the three floppy images
#   make rom         just the ROM
#   make boot        build, then prove the stub ROM boots and paints (out/stub-boot.png)
#   make golden      capture the ORIGINAL ROM's boot surface and both ledgers into golden/
#   make check       build, then run every driver against the original ROM and report
#   make clean
#
# TWO LINKS, TWO LINKER SCRIPTS, AND THEY ARE NOT INTERCHANGEABLE. tos_rom.ld links code that is
# BURNED at 0xFC0000 and never relocated; tos.ld links a base-0 blob that GEMDOS relocates as it
# loads a .PRG. The ROM has no relocation table and no .bss; the programs have both.
#
# BUILD PRODUCTS ARE GITIGNORED. build/ and out/ are covered by the workspace .gitignore's
# `projects/*/recreate/atari/{build,out}/` rules, and golden/ is NOT — it is the tracked evidence.

CC        := m68k-elf-gcc
OBJCOPY   := m68k-elf-objcopy
STRIP     := m68k-elf-strip
PYTHON    ?= python3

BUILD     := build
OUT       := out
GOLDEN    := golden
REPO      := ../../../..
TOOLS     := $(REPO)/tools
ST_BUILD  := $(TOOLS)/st_build.py
# The user's own ROM: read in place, never copied into a tracked path (Atari copyright, and the
# workspace .gitignore refuses `**/TOS*.img` for exactly this reason).
ORIGINAL_ROM ?= $(TOOLS)/hatari/TOS102US.img

# -fno-jump-tables: a switch compiled to a table puts absolute addresses in rodata, and every one of
#   them is another fixup the .PRG's relocation table has to carry correctly.
# -Wno-array-bounds: TOS publishes its state in page zero ($466, $4ba), and a dereference of a small
#   absolute address is exactly what -Warray-bounds is built to shout about — right on a host, wrong
#   on a machine whose OS lives there.
CFLAGS    := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -fno-jump-tables \
             -Wall -Wextra -Werror -Wno-array-bounds

ROM_CFLAGS := $(CFLAGS) -I.
ROM_LDFLAGS := -m68000 -nostdlib -T tos_rom.ld
# -I. as well as -Iprg: st_screen.h states the machine's screen geometry for BOTH builds, so the
# programs read it from the same file the ROM does rather than from a copy of its numbers.
PRG_CFLAGS := $(CFLAGS) -Iprg -I.
# --no-warn-rwx-segments: newer binutils warns that the single LOAD segment is readable,
#   writable and executable. A GEMDOS .PRG has no segments at run time — TOS loads one flat
#   image — so the warning is about a property the target does not have, and it would
#   otherwise print on every link and train a reader to ignore linker warnings.
PRG_LDFLAGS := -m68000 -nostdlib -T tos.ld -Wl,--emit-relocs -Wl,--no-warn-rwx-segments
LDLIBS    := -lgcc

# The image's size, its reset entry and its header field values are romdefs.h's, and checkrom.py
# reads them from there — deliberately NOT repeated here, since a second copy is a second thing to
# keep right.
ROM_IMAGE := $(BUILD)/TOS102RC.IMG

PRG_COMMON_OBJ := $(BUILD)/os.o $(BUILD)/ledger.o
# The prg/ headers as ONE conservative dependency group, and the two the ROM build reads. Listed by
# hand rather than generated: -MMD would write its dependency files into build/, which `make clean`
# removes, and this is a directory of half a dozen sources. A rebuild an object did not need costs
# a second; an object that did not rebuild is a .PRG built against a header that has moved.
ROM_HEADERS := romdefs.h st_screen.h
PRG_HEADERS := prg/ledger.h prg/tosapi.h prg/console.h
# assert_trap_registers.sh counts the trap wrappers it evaluated, so a regex that stopped matching
# reds here instead of passing vacuously over a file it can no longer parse.
TRAP_WRAPPERS := 17

FIXTURES := $(BUILD)/fixtures/ALPHA.DAT $(BUILD)/fixtures/BETA.DAT $(BUILD)/fixtures/DATA64K.BIN
# Written by the one mkdata.py run that writes all of them — see the rule for why it is a stamp.
FIXTURE_STAMP := $(BUILD)/fixtures/.written

.PHONY: all rom prgs disks boot golden check test-host clean
all: rom prgs disks

# A TARGET THAT FAILED MUST NOT SURVIVE WITH A FRESH MTIME. Every gate here runs after the file it
# gates has been written — checkrom.py after objcopy, st_build.py's own checks as it writes — and
# without this a ROM that failed its header check, or a floppy image cut short, stays on disk
# looking newer than its sources, so the next make skips the rule and every driver measures it.
.DELETE_ON_ERROR:

rom: $(ROM_IMAGE)
prgs: $(BUILD)/TOSTEST.PRG $(BUILD)/TOSBENCH.PRG
disks: $(BUILD)/BLANK.ST $(BUILD)/TOSTEST.ST $(BUILD)/TOSBENCH.ST

$(BUILD) $(OUT) $(BUILD)/fixtures:
	mkdir -p $@

# ---- the ROM -------------------------------------------------------------------------------------

$(BUILD)/header.o: header.S $(ROM_HEADERS) | $(BUILD)
	$(CC) $(ROM_CFLAGS) -c $< -o $@

$(BUILD)/boot_stub.o: boot_stub.c $(ROM_HEADERS) | $(BUILD)
	$(CC) $(ROM_CFLAGS) -c $< -o $@

$(BUILD)/tos_rom.elf: $(BUILD)/header.o $(BUILD)/boot_stub.o tos_rom.ld
	$(CC) $(ROM_LDFLAGS) -o $@ $(BUILD)/header.o $(BUILD)/boot_stub.o $(LDLIBS)

# checkrom.py IS THE BUILD'S OWN CONFORMANCE CHECK, and every failure it names is silent otherwise:
# a ROM of the wrong length reaches Hatari as an image it identifies by header alone and boots into
# whatever the truncation left; a reset entry that moved makes the machine jump into the middle of
# its own OS header; and an os_magic pointing nowhere produces a ROM that looks perfect and has no
# GEM. Its header comment has the mutation that made the third one necessary.
$(ROM_IMAGE): $(BUILD)/tos_rom.elf checkrom.py $(ROM_HEADERS)
	$(OBJCOPY) -O binary $< $(ROM_IMAGE)
	@$(PYTHON) checkrom.py $(ROM_IMAGE) $(BUILD)/tos_rom.elf $(ORIGINAL_ROM)

# ---- the two programs ------------------------------------------------------------------------------

$(BUILD)/os.o: prg/os.S | $(BUILD)
	@bash $(TOOLS)/assert_trap_registers.sh --expect $(TRAP_WRAPPERS) $<
	$(CC) $(PRG_CFLAGS) -c $< -o $@

$(BUILD)/ledger.o: prg/ledger.c $(PRG_HEADERS) | $(BUILD)
	$(CC) $(PRG_CFLAGS) -c $< -o $@

$(BUILD)/tostest.o: tostest/tostest.c $(PRG_HEADERS) st_screen.h | $(BUILD)
	$(CC) $(PRG_CFLAGS) -c $< -o $@

$(BUILD)/tosbench.o: tosbench/tosbench.c $(PRG_HEADERS) prg/fixtures.h | $(BUILD)
	$(CC) $(PRG_CFLAGS) -c $< -o $@

$(BUILD)/tostest.elf: $(PRG_COMMON_OBJ) $(BUILD)/tostest.o tos.ld
	$(CC) $(PRG_LDFLAGS) -o $@ $(PRG_COMMON_OBJ) $(BUILD)/tostest.o $(LDLIBS)

$(BUILD)/tosbench.elf: $(PRG_COMMON_OBJ) $(BUILD)/tosbench.o tos.ld
	$(CC) $(PRG_LDFLAGS) -o $@ $(PRG_COMMON_OBJ) $(BUILD)/tosbench.o $(LDLIBS)

# The .PRG is the flat image plus a GEMDOS relocation table built from the ELF's own fixups.
define LINK_PRG
	$(STRIP) --strip-debug $<
	$(OBJCOPY) -O binary $< $(basename $<).bin
	$(PYTHON) mkprg.py $< $(basename $<).bin $@
endef

$(BUILD)/TOSTEST.PRG: $(BUILD)/tostest.elf mkprg.py
	$(LINK_PRG)

$(BUILD)/TOSBENCH.PRG: $(BUILD)/tosbench.elf mkprg.py
	$(LINK_PRG)

# ---- the floppies ----------------------------------------------------------------------------------
#
# THREE IMAGES, AND THE BLANK ONE IS NOT AN ACCIDENT. The boot surface is captured with a floppy in
# drive A because the boot's floppy probe reaches a different place with a disk present than with an
# empty drive, and "different" would be a difference between two captures rather than between two
# ROMs. A disk with no AUTO folder lets the ROM boot to its own desktop with nothing of ours running.
#
# THE TWO PROGRAM DISKS CARRY THE SAME ROOT FILES, so TOSTEST's directory walk sees the same three
# entries whichever disk it is run from, and TOSBENCH has its 64 KB read fixture. Only \AUTO\ differs
# — TOS runs every \AUTO\*.PRG on the boot drive, so one program per disk is what makes each run be
# about that program.

# prg/fixtures.h is the spec mkdata.py writes FROM (it parses the header), so an edit to the
# names, the sizes or the counter's period rewrites the files as well as rebuilding TOSBENCH.
#
# ONE RUN WRITES ALL THREE, AND THE STAMP IS WHAT SAYS SO. The system make is 3.81, which has no
# grouped-target rule (`&:`), and three targets sharing one recipe is three runs of mkdata.py — at
# the same time, over the same files, under `make -j`. The disks depend on the stamp instead, and
# the fixture paths are only named on the command line.
$(FIXTURE_STAMP): mkdata.py prg/fixtures.h cdefines.py | $(BUILD)/fixtures
	$(PYTHON) mkdata.py $(BUILD)/fixtures
	@touch $@

$(BUILD)/BLANK.ST: $(ST_BUILD) | $(BUILD)
	$(PYTHON) $(ST_BUILD) $@ --label TOSBLANK

$(BUILD)/TOSTEST.ST: $(BUILD)/TOSTEST.PRG $(FIXTURE_STAMP) $(ST_BUILD)
	$(PYTHON) $(ST_BUILD) $@ --label TOSTEST --auto $(BUILD)/TOSTEST.PRG:TOSTEST.PRG $(FIXTURES)

$(BUILD)/TOSBENCH.ST: $(BUILD)/TOSBENCH.PRG $(FIXTURE_STAMP) $(ST_BUILD)
	$(PYTHON) $(ST_BUILD) $@ --label TOSBENCH --auto $(BUILD)/TOSBENCH.PRG:TOSBENCH.PRG $(FIXTURES)

# ---- measurement -------------------------------------------------------------------------------------

boot: all | $(OUT)
	$(PYTHON) boot_surface.py capture --rom $(ROM_IMAGE) --out $(OUT)/stub

# THE THREE DRIVERS RUN AT ONCE AND ALL THREE ARE REPORTED. They are independent — each boots its
# own machine, into its own work directory, against its own artefacts — so running them in a row
# only makes the wall clock longer; and a recipe of three commands stops at the first non-zero one,
# which hides two of the three answers exactly when a reader most wants all of them. Each driver's
# output is captured and printed whole, in a fixed order, so a concurrent run still reads as a
# report rather than as three interleaved ones.
#
# `set +e` and an explicit status: a failed driver is this target's failure, after the other two
# have had their say.
define RUN_DRIVERS
	@set +e; status=0; \
	for driver in boot_surface tostest tosbench; do \
	  ( $(PYTHON) $$driver.py $(1) --rom $(ORIGINAL_ROM) > $(OUT)/$$driver-$(1).out 2>&1; \
	    echo $$? > $(OUT)/$$driver-$(1).status ) & \
	done; \
	wait; \
	for driver in boot_surface tostest tosbench; do \
	  echo "===== $$driver $(1)"; cat $(OUT)/$$driver-$(1).out; \
	  if [ "`cat $(OUT)/$$driver-$(1).status`" != 0 ]; then \
	    status=1; echo "===== $$driver $(1): FAILED (exit `cat $(OUT)/$$driver-$(1).status`)"; \
	  fi; \
	done; \
	[ $$status = 0 ] && echo "===== all three drivers passed" ; \
	exit $$status
endef

golden: all | $(OUT)
	$(call RUN_DRIVERS,golden)

check: all | $(OUT)
	$(call RUN_DRIVERS,compare)

# The host-side pins: the system-variable table against names.txt and against prg/tosapi.h. No
# emulator, no target build — pure Python, so it runs in a second and belongs in every sweep.
# The recreate venv and not `python3`: the project's pytest lives there (see ../Makefile).
HOST_PYTHON ?= ../.venv/bin/python
test-host:
	$(HOST_PYTHON) -m pytest -q test_atari_pins.py

clean:
	rm -rf $(BUILD) $(OUT)
