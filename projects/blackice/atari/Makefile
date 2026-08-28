# Makefile — build BLACK ICE for a stock Atari STE.
#
#   make            disk/BLACKICE.PRG (the game) + disk/BENCH.PRG + disk/BLACKICE.PAK,
#                   and floppy/ staged as the 720 KB disk BRIEF.md's distribution rule describes
#   make bench      build, then run the bench headless in Hatari and print the timing table
#   make verify     build, then compare the target's rendered pixels against the host reference
#   make clean
#
# TWO PROGRAMS, ONE SOURCE TREE. BLACKICE.PRG reads the joystick and plays; BENCH.PRG is the same
# code with -DBLACKICE_BENCH, which replaces the input with a compiled-in copy of the SAME script the
# host reference replays and runs the fixture passes. They must not diverge — that is the whole
# point of building them from one main.c — so both are built by `make all` and a change that breaks
# one breaks the build.
#
# tos.ld and mkprg.py are COPIES of ../spike/'s, which are copies of
# projects/wonderboy/recreate/atari/'s; those are canonical for the two gotchas they encode (.bss
# must abut text+data, and the GEMDOS relocation table is built from the ELF's own R_68K_32 fixups).

CC        := m68k-elf-gcc
OBJCOPY   := m68k-elf-objcopy
STRIP     := m68k-elf-strip
HOSTCC    ?= cc
# Inherited from the parent make when this is reached through its `atari` target, so the .PAK is
# packed by the same interpreter the level compiler runs under (../Makefile pins the conda env).
PYTHON    ?= python3

BUILD     := build
DISK      := disk
FLOPPY    := floppy
OUT       := out
ENGINE    := ..
INCLUDES  := -I. -I$(ENGINE)/include -I$(ENGINE)/pipeline -I$(ENGINE)/audio

# -fno-jump-tables: a switch compiled to a table puts absolute addresses in rodata, and every one of
#   them is another fixup the .PRG's relocation table has to carry correctly.
# -Wno-array-bounds: TOS publishes its state in page zero ($44e, $454, $4ba), and a dereference of a
#   small absolute address is exactly what -Warray-bounds is built to shout about. Right on a host,
#   wrong on a machine whose OS lives there. (The audio build carries the same suppression.)
CFLAGS    := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -fno-jump-tables \
             -ffunction-sections -fdata-sections -Wall -Wextra -Wno-array-bounds $(INCLUDES)
# The platform's own code is held to -Werror; src/ and audio/ are other agents' and are not.
PLATFORM_CFLAGS := $(CFLAGS) -Werror
LDFLAGS   := -m68000 -nostdlib -T tos.ld -Wl,--emit-relocs -Wl,--gc-sections
LDLIBS    := -lgcc

# The portable engine core, minus src/draw.c and src/assets_data.c: the target draws with
# render.S and binds its assets from the .PAK (atari/assets.c), so linking either would only add a
# second, unreachable copy of the same job.
ENGINE_SRC := $(ENGINE)/src/tables.c $(ENGINE)/src/rng.c $(ENGINE)/src/hash.c $(ENGINE)/src/map.c \
              $(ENGINE)/src/level.c $(ENGINE)/src/player.c $(ENGINE)/src/game.c \
              $(ENGINE)/src/raycast.c $(ENGINE)/src/sprite.c \
              $(ENGINE)/src/sim.c $(ENGINE)/src/entities.c $(ENGINE)/src/ai.c \
              $(ENGINE)/src/weapons.c $(ENGINE)/src/pickups.c $(ENGINE)/src/trace.c \
              $(ENGINE)/src/events.c
# DESIGN 16: the first playable is YM-only, so the DMA sample path is not linked.
AUDIO_SRC  := $(ENGINE)/audio/ym_music.c $(ENGINE)/audio/blackice_song.c
PLATFORM_SRC := main.c hud.c assets.c overlay.c
SHARED_SRC := $(ENGINE)/pipeline/depack.c

ENGINE_OBJ   := $(patsubst $(ENGINE)/src/%.c,$(BUILD)/eng_%.o,$(ENGINE_SRC))
AUDIO_OBJ    := $(patsubst $(ENGINE)/audio/%.c,$(BUILD)/aud_%.o,$(AUDIO_SRC)) $(BUILD)/ym_psg.o
SHARED_OBJ   := $(BUILD)/depack.o
ASM_OBJ      := $(BUILD)/os.o $(BUILD)/render.o $(BUILD)/cast.o
GAME_OBJ     := $(patsubst %.c,$(BUILD)/game_%.o,$(PLATFORM_SRC))
BENCH_OBJ    := $(patsubst %.c,$(BUILD)/bench_%.o,$(PLATFORM_SRC))
COMMON_OBJ   := $(ASM_OBJ) $(ENGINE_OBJ) $(AUDIO_OBJ) $(SHARED_OBJ)

HEADERS   := plat.h tos.h assets.h hud.h $(wildcard $(ENGINE)/include/*.h)
LEVELS    := $(patsubst $(ENGINE)/levels/%.txt,$(ENGINE)/levels/%.bil,$(wildcard $(ENGINE)/levels/*.txt))
HUD_ART   := $(ENGINE)/art/out/native/hud_strip.png
DUMPS     := $(BUILD)/dumps
PAK       := $(DISK)/BLACKICE.PAK

.PHONY: all bench verify libgcc-gate clean
all: $(DISK)/BLACKICE.PRG $(DISK)/BENCH.PRG $(PAK) libgcc-gate

# The cost model this whole directory is built on only holds if the 68000 never calls out to a
# libgcc arithmetic helper: a 32x32 multiply or any divide is a subroutine costing several times
# the `muls.w` / `divu.w` it replaced. ../Makefile gates src/ on exactly this; the platform's own
# objects were NOT gated until a review found __udivsi3, __umodsi3 and __divsi3 in the per-frame
# HUD path — the same fault class that had already cost this file 170 ms a frame once.
#
# FOUR OBJECTS ARE EXEMPT, and in each the 32-bit arithmetic IS the algorithm and the algorithm is
# cold. The first three are ../Makefile's own exemptions, restated here because this link contains
# those objects and the gate would otherwise disagree with the one that already covers them:
#   eng_hash.o     FNV-1a's step is a 32-bit multiply by definition; nothing hashes on target.
#   eng_rng.o      DESIGN 4.3 names a 32-bit LCG; the sim draws a handful a tick (include/rng.h).
#   eng_tables.o   tables_init's two divides run 8,192 times, once, at start-up.
#   bench_main.o   put_num and ticks_to_us format the report the program writes through GEMDOS
#                  after the last frame is drawn; nothing there runs while anything is timed.
LIBGCC_EXEMPT := eng_hash.o eng_rng.o eng_tables.o bench_main.o
LIBGCC_HELPERS := '__(mul|div|mod|udiv|umod)si3'

libgcc-gate: $(COMMON_OBJ) $(GAME_OBJ) $(BENCH_OBJ)
	@gated=""; \
	for object in $(COMMON_OBJ) $(GAME_OBJ) $(BENCH_OBJ); do \
	    case " $(LIBGCC_EXEMPT) " in *" `basename $$object` "*) continue;; esac; \
	    gated="$$gated $$object"; \
	done; \
	if [ -z "$$gated" ]; then echo "FAIL: nothing to gate"; exit 1; fi; \
	if m68k-elf-nm -u $$gated | grep -E $(LIBGCC_HELPERS); then \
	    echo "FAIL: atari/ references a libgcc arithmetic helper (see plat.h's divu16)"; \
	    exit 1; \
	fi; \
	echo "libgcc arithmetic-helper gate: clean (`echo $$gated | wc -w | tr -d ' '` objects)"

$(BUILD) $(DISK) $(FLOPPY) $(FLOPPY)/AUTO $(OUT) $(DUMPS):
	mkdir -p $@

# ---- generated sources ---------------------------------------------------------------------------

# The bench's input is the SAME script the host reference replays; mkscript.py turns it into the C
# array so the two builds cannot drift apart.
$(BUILD)/bench_script.h: mkscript.py $(ENGINE)/test/scripts/walk.txt $(ENGINE)/include/player.h | $(BUILD)
	$(PYTHON) mkscript.py $(ENGINE)/include/player.h $(ENGINE)/test/scripts/walk.txt $@

# ---- objects -------------------------------------------------------------------------------------

$(BUILD)/%.o: %.S plat.h | $(BUILD)
	$(CC) $(PLATFORM_CFLAGS) -c $< -o $@

$(BUILD)/ym_psg.o: $(ENGINE)/audio/ym_psg.S $(ENGINE)/audio/ym_psg.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/game_%.o: %.c $(HEADERS) | $(BUILD)
	$(CC) $(PLATFORM_CFLAGS) -c $< -o $@

# BENCH_CAPTURE names which pass the held screenshot belongs to; empty means main.c's default (the
# last one, WALK160). `make verify` sets it to compare the 80-column c2p as well.
BENCH_CAPTURE ?=
BENCH_CAPTURE_FLAG := $(if $(BENCH_CAPTURE),-DBENCH_CAPTURE_PASS=$(BENCH_CAPTURE),)

$(BUILD)/bench_%.o: %.c $(HEADERS) $(BUILD)/bench_script.h | $(BUILD)
	$(CC) $(PLATFORM_CFLAGS) -DBLACKICE_BENCH $(BENCH_CAPTURE_FLAG) -I$(BUILD) -c $< -o $@

$(BUILD)/eng_%.o: $(ENGINE)/src/%.c $(HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/aud_%.o: $(ENGINE)/audio/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/depack.o: $(ENGINE)/pipeline/depack.c $(ENGINE)/pipeline/depack.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

# ---- linking --------------------------------------------------------------------------------------

$(BUILD)/blackice.elf: $(COMMON_OBJ) $(GAME_OBJ) tos.ld
	$(CC) $(LDFLAGS) -o $@ $(COMMON_OBJ) $(GAME_OBJ) $(LDLIBS)

$(BUILD)/bench.elf: $(COMMON_OBJ) $(BENCH_OBJ) tos.ld
	$(CC) $(LDFLAGS) -o $@ $(COMMON_OBJ) $(BENCH_OBJ) $(LDLIBS)

# The .PRG is the flat image plus a GEMDOS relocation table built from the ELF's own fixups. The
# two are spelled out rather than pattern-matched because the ELF names are lower case and the
# GEMDOS names upper, and a pattern rule would have to make those agree.
define LINK_PRG
	$(STRIP) --strip-debug $<
	$(OBJCOPY) -O binary $< $(basename $<).bin
	$(PYTHON) mkprg.py $< $(basename $<).bin $@
	@ls -l $@
endef

$(DISK)/BLACKICE.PRG: $(BUILD)/blackice.elf mkprg.py | $(DISK)
	$(LINK_PRG)

$(DISK)/BENCH.PRG: $(BUILD)/bench.elf mkprg.py | $(DISK)
	$(LINK_PRG)

# The floppy layout BRIEF.md's distribution rule wants: the game in AUTO/ so a 720 KB image made
# from this directory boots straight into it with no desktop, and the archive beside it.
#
# IT IS NOT STAGED INSIDE disk/, AND THAT IS A MEASURED FINDING. An AUTO folder on Hatari's GEMDOS
# drive is executed by EmuTOS at boot, BEFORE --auto gets to run anything: with a copy of the game
# there, every `--auto C:\BENCH.PRG` silently ran the GAME instead — which never terminates — and
# the bench produced no ledger and no BENCH.TXT while looking, from the outside, like a hang in the
# renderer. Keep the emulator's drive free of AUTO.
$(FLOPPY)/AUTO/BLACKICE.PRG: $(DISK)/BLACKICE.PRG | $(FLOPPY)/AUTO
	cp $< $@

$(FLOPPY)/BLACKICE.PAK: $(PAK) | $(FLOPPY)
	cp $< $@

all: $(FLOPPY)/AUTO/BLACKICE.PRG $(FLOPPY)/BLACKICE.PAK $(DISK)/BLACKICE.ST

# The bootable 720 KB image: what `run.sh` boots and what goes onto a real floppy (tools/st_build.py
# is deterministic, so its sha256 is the check that a physical write took). TOS runs AUTO\*.PRG
# itself, so the emulator's own --auto is not involved on this route.
ST_BUILD := ../../../tools/st_build.py
$(DISK)/BLACKICE.ST: $(FLOPPY)/AUTO/BLACKICE.PRG $(FLOPPY)/BLACKICE.PAK $(ST_BUILD)
	$(PYTHON) $(ST_BUILD) $@ --label BLACKICE --auto $(FLOPPY)/AUTO/BLACKICE.PRG:BLACKICE.PRG \
	    $(FLOPPY)/BLACKICE.PAK:BLACKICE.PAK

# ---- the resource archive --------------------------------------------------------------------------

# dumpassets is a HOST program: it links the engine's own asset arrays and writes them out, so the
# art the target loads is byte-identical to the art the host reference draws with. That identity is
# what makes atari/verify.py's pixel comparison a test of the drawers rather than of the pipeline.
# src/map.c is here because src/tables.c calls map_cell_texture; the set is "whatever the asset
# arrays drag in", not a curated list.
DUMPASSETS_SRC := dumpassets.c $(ENGINE)/src/assets_data.c $(ENGINE)/src/tables.c \
                  $(ENGINE)/src/map.c

$(BUILD)/dumpassets: $(DUMPASSETS_SRC) | $(BUILD)
	$(HOSTCC) -Wall -Wextra -Werror -std=c99 -I$(ENGINE)/include -o $@ $(DUMPASSETS_SRC)

$(DUMPS)/walltex.bin: $(BUILD)/dumpassets | $(DUMPS)
	$(BUILD)/dumpassets $(DUMPS)

# The level compiler lives in the parent build; the .bil blobs are its output and the PAK's input.
$(ENGINE)/levels/%.bil: $(ENGINE)/levels/%.txt
	$(MAKE) -C $(ENGINE) $@

$(PAK): mkpak.py $(DUMPS)/walltex.bin $(HUD_ART) $(LEVELS) | $(DISK)
	$(PYTHON) mkpak.py --dumps $(DUMPS) --levels $(ENGINE)/levels --hud $(HUD_ART) --out $@

# ---- measurement -----------------------------------------------------------------------------------

bench: all
	$(PYTHON) bench.py

# WALK80 is index 3 of main.c's BENCH_PASSES, and it is the pass that draws through bi_c2p_low —
# which is what DESIGN v2.1 17.3's shipping detail level uses, so it has to be compared too.
BENCH_PASS_WALK80 := 3

# The bench runs FIRST, and that is not a convenience: verify.py compares out/frame.png, so without
# a fresh capture it can pass against the screenshot of a previous build. That is exactly how a
# mutation sweep of this gate came back green on a deliberately broken drawer.
verify: bench | $(OUT)
	$(PYTHON) verify.py
	@echo "-- and again with the 80-column c2p, which is the shipping detail level"
	@rm -f $(BENCH_OBJ) $(BUILD)/bench.elf $(DISK)/BENCH.PRG
	@$(MAKE) --no-print-directory $(DISK)/BENCH.PRG BENCH_CAPTURE=$(BENCH_PASS_WALK80)
	$(PYTHON) bench.py > $(OUT)/bench-low.log
	$(PYTHON) verify.py
	@rm -f $(BENCH_OBJ) $(BUILD)/bench.elf $(DISK)/BENCH.PRG
	@$(MAKE) --no-print-directory $(DISK)/BENCH.PRG

clean:
	rm -rf $(BUILD) $(DISK) $(FLOPPY) out
