# Makefile — build SPIKE.PRG, the raycast feasibility bench, for a stock Atari STE.
#
# tos.ld and mkprg.py are COPIES of projects/wonderboy/recreate/atari/'s, which are canonical for
# the two gotchas they encode: .bss must abut text+data, and the GEMDOS relocation table is built
# from the ELF's own R_68K_32 fixups. The only edit to tos.ld is the KEEP's object name and the
# .bss SUBALIGN cap, both explained in its header.
#
# The .PRG lands in disk/, which bench.py hands Hatari as a GEMDOS drive with --auto.

CC        := m68k-elf-gcc
OBJCOPY   := m68k-elf-objcopy
PYTHON    := python3

BUILD     := build
DISK      := disk
PRG       := $(DISK)/SPIKE.PRG

# -fno-jump-tables: a switch compiled to a table puts absolute addresses in rodata, and every one
# of them is another fixup the .PRG's relocation table has to carry correctly.
CFLAGS    := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -fno-jump-tables \
             -ffunction-sections -fdata-sections -Wall -Wextra -Werror
LDFLAGS   := -Wl,--emit-relocs -Wl,--gc-sections -T tos.ld

OBJECTS   := $(BUILD)/os.o $(BUILD)/render.o $(BUILD)/main.o $(BUILD)/tables.o

.PHONY: all clean bench verify
all: $(PRG)

tables.c tables.h: gen_tables.py spike.h
	$(PYTHON) gen_tables.py spike.h tables.h tables.c

$(BUILD):
	mkdir -p $(BUILD) $(DISK)

$(BUILD)/%.o: %.S spike.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: %.c spike.h tables.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/spike.elf: $(OBJECTS) tos.ld
	$(CC) $(CFLAGS) $(LDFLAGS) $(OBJECTS) -lgcc -o $@

$(BUILD)/spike.bin: $(BUILD)/spike.elf
	$(OBJCOPY) -O binary $< $@

$(PRG): $(BUILD)/spike.bin $(BUILD)/spike.elf mkprg.py | $(BUILD)
	$(PYTHON) mkprg.py $(BUILD)/spike.elf $(BUILD)/spike.bin $@

bench: $(PRG)
	$(PYTHON) bench.py

# The picture check: the target's own rays against a float reference, and the rendered frame
# against those rays. Needs the artefacts `make bench` leaves in out/.
verify:
	$(PYTHON) verify.py

clean:
	rm -rf $(BUILD) $(PRG) tables.c tables.h out
