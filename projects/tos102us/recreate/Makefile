# TOS 1.02 US reconstruction. The shared candidate/oracle/test rules live in the kit; this file
# names the project and the one thing a ROM project has that a game does not: the post-boot RAM
# snapshot its differentials run over.
KIT  := ../../../tools/recreate_kit
GAME := tos102us
include $(KIT)/kit.mk

# The snapshot is a BUILD PRODUCT, captured out of headless Hatari from the user's own ROM — which
# is why it is a make rule and not a checked-in file (the ROM is Atari's, and so is its RAM image).
# Capturing costs ~15 s of real time per run, because emulation is real time; it happens once, and
# again only when the tool that defines the stop point changes.
SNAPSHOT := build/boot_ram.bin

# On include/addrs.h too: tools/addrs.py parses it, so the machine's size and the vector slot the
# capture stops in are read from there — a snapshot captured before an edit to it is a capture of a
# different machine than the one the cases describe.
$(SNAPSHOT): tools/boot_snapshot.py tools/addrs.py include/addrs.h
	$(PY) tools/boot_snapshot.py --out $@

.PHONY: snapshot
snapshot: $(SNAPSHOT)

# Every differential reads it, so both suites capture it first rather than failing on a missing file
# (kit.mk owns the recipes; this only adds the prerequisite). `guarded` is the same suite under the
# guarded-image plugin, and it reads the snapshot at exactly the same import.
test: $(SNAPSHOT)
guarded: $(SNAPSHOT)
