# Makefile — build the audio modules' on-target harnesses, and prove them in Hatari.
#
#   make                   both .PRGs: disk/AUDIOTEST.PRG and disk/BICETEST.PRG
#   make verify            AUDIOTEST.PRG in Hatari — mk_song.py's demo tune, mk_samples.py's six
#   make verify-blackice   BICETEST.PRG in Hatari — the BLACK ICE score, cues and drum lane
#   make listen-blackice   the same run recorded to out/audio-blackice.wav, no checks
#   make clean
#
# THE GENERATED SOURCES ARE BUILD PRODUCTS, not checked-in data: song_data.*, sfx_bank.*,
# ym_notes.h, sfx_ids.h and the blackice_* set all come out of the four Python tools, so the songs
# and the samples have exactly one authored form (the descriptions inside those tools) and the C
# can never drift from it.
#
# EVERY TOOL OUTPUT IS A TARGET, INCLUDING THE ONES ONLY THE VERIFIER READS. out/*_meta.json and
# out/*.bin are what verify.py predicts the recording from, and leaving them off the graph made
# `make clean && make verify` fail on a missing file rather than regenerate it — the acceptance
# test for this directory is a clean tree, so the metadata has to be as much a build product as
# the C is.

CC      := m68k-elf-gcc
OBJCOPY := m68k-elf-objcopy
STRIP   := m68k-elf-strip
PYTHON  := python3

BUILD := build
DISK  := disk
OUT   := out
SONGS := songs

# -ffunction-sections/-fdata-sections + --gc-sections: the link drops every body no live call
# reaches, which is what keeps each .PRG to the code that harness actually runs.
# -Warray-bounds STAYS ON. Reading TOS's system variables ($454/$456/$4ba/$5a0/$42e) is a
# dereference of a small absolute address, which is exactly what that warning is built to shout
# about — right on a host, wrong on a machine whose OS publishes its state in page zero. Suppressing
# it build-wide, which this Makefile used to do, also switched it off for every array in every file:
# the price of quieting five reads was losing the check on all the real ones. It is suppressed at
# those five reads instead, with `#pragma GCC diagnostic` and a why-comment (audiotest.c, dma_sfx.c).
# -MMD -MP: the compiler writes each object's real header dependencies into build/*.d, which the
# include at the bottom feeds back to make. Without it only the GENERATED headers are prerequisites
# and editing ym_music.h rebuilds nothing — you keep a stale object and ship a .PRG whose C and
# whose header disagree, which is the worst failure class there is for code that runs on target.
CFLAGS := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -MMD -MP \
          -ffunction-sections -fdata-sections -Wall -Wextra -Werror
# --emit-relocs keeps the R_68K_32 fixups mkprg.py turns into the GEMDOS relocation table.
LDFLAGS := -m68000 -nostdlib -T tos.ld -Wl,--emit-relocs -Wl,--gc-sections
# libgcc supplies the 68000's missing arithmetic (32-bit multiply and divide helpers). Linking it
# explicitly is what -nostdlib takes away.
LDLIBS := -lgcc

# What each tool writes. The .h/.c are what the compiler needs; the out/ files are what verify.py
# needs, and both halves are prerequisites of the things that read them.
DEMO_SONG_FILES := song_data.c song_data.h ym_notes.h sfx_ids.h \
                   $(OUT)/demo_song.bin $(OUT)/song_meta.json
DEMO_BANK_FILES := sfx_bank.c sfx_bank.h $(OUT)/sfx_bank.bin $(OUT)/sfx_meta.json
BICE_SONG_STEMS := blackice_title blackice_score blackice_death blackice_clear blackice_exfil
BICE_SONG_FILES := blackice_song.c blackice_song.h blackice_sfx_ids.h \
                   $(BICE_SONG_STEMS:%=$(OUT)/%.bin) $(BICE_SONG_STEMS:%=$(OUT)/%_meta.json)
BICE_BANK_FILES := blackice_sfx_bank.c blackice_sfx_bank.h \
                   $(OUT)/blackice_sfx_bank.bin $(OUT)/blackice_sfx_meta.json

GENERATED := $(DEMO_SONG_FILES) $(DEMO_BANK_FILES) $(BICE_SONG_FILES) $(BICE_BANK_FILES)
# The generated HEADERS every object must wait for; the .c files are compiled by name below.
GENERATED_HEADERS := song_data.h ym_notes.h sfx_ids.h sfx_bank.h \
                     blackice_song.h blackice_sfx_ids.h blackice_sfx_bank.h

COMMON_OBJECTS := $(BUILD)/audio_os.o $(BUILD)/ym_psg.o $(BUILD)/ym_music.o $(BUILD)/dma_sfx.o
DEMO_OBJECTS   := $(COMMON_OBJECTS) $(BUILD)/audiotest.o $(BUILD)/song_data.o $(BUILD)/sfx_bank.o
BICE_OBJECTS   := $(COMMON_OBJECTS) $(BUILD)/bicetest.o $(BUILD)/blackice_song.o \
                  $(BUILD)/blackice_sfx_bank.o

.PHONY: all verify verify-blackice listen-blackice clean

all: $(DISK)/AUDIOTEST.PRG $(DISK)/BICETEST.PRG

# ONE TARGET PER TOOL CARRIES THE RECIPE; the rest of that tool's outputs depend on it with an
# EMPTY recipe (the bare `;`). A rule with several targets and one recipe is NOT "these targets are
# made together" in GNU make — it expands to one independent rule per target, so `make -j` starts a
# copy of the tool per output and four mk_song.py processes rewrite song_data.c at once. Measured:
# up to 4 concurrent runs at -j8. It survives today only because the tools are deterministic, which
# is luck, not correctness. The empty recipe is also what stops make trying an implicit rule.
song_data.c: mk_song.py
	$(PYTHON) mk_song.py
$(filter-out song_data.c,$(DEMO_SONG_FILES)): song_data.c ;

sfx_bank.c: mk_samples.py
	$(PYTHON) mk_samples.py
$(filter-out sfx_bank.c,$(DEMO_BANK_FILES)): sfx_bank.c ;

blackice_song.c: $(SONGS)/blackice.py mk_song.py
	$(PYTHON) $(SONGS)/blackice.py
$(filter-out blackice_song.c,$(BICE_SONG_FILES)): blackice_song.c ;

blackice_sfx_bank.c: $(SONGS)/blackice_sfx.py mk_samples.py
	$(PYTHON) $(SONGS)/blackice_sfx.py
$(filter-out blackice_sfx_bank.c,$(BICE_BANK_FILES)): blackice_sfx_bank.c ;

$(BUILD)/%.o: %.c $(GENERATED_HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -DBLACKICE_MODE=0 -c $< -o $@

# The BLACK ICE harness is audiotest.c again with the other material selected. One source, two
# objects: the ledger, the vblank install and the teardown cannot drift between the two runs.
$(BUILD)/bicetest.o: audiotest.c $(GENERATED_HEADERS) | $(BUILD)
	$(CC) $(CFLAGS) -DBLACKICE_MODE=1 -c $< -o $@

$(BUILD)/audio_os.o: audio_os.s | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

# .S, capital: it goes through the C preprocessor, which is how it and ym_music.c share ym_psg.h.
$(BUILD)/ym_psg.o: ym_psg.S ym_psg.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/audiotest.elf: $(DEMO_OBJECTS) tos.ld
	$(CC) $(LDFLAGS) -o $@ $(DEMO_OBJECTS) $(LDLIBS)

$(BUILD)/bicetest.elf: $(BICE_OBJECTS) tos.ld
	$(CC) $(LDFLAGS) -o $@ $(BICE_OBJECTS) $(LDLIBS)

# The ELF -> flat binary -> GEMDOS .PRG step, written once and used by both.
define link_prg
	$(STRIP) --strip-debug $<
	$(OBJCOPY) -O binary $< $(basename $<).bin
	$(PYTHON) mkprg.py $< $(basename $<).bin $@
	@ls -l $@
endef

$(DISK)/AUDIOTEST.PRG: $(BUILD)/audiotest.elf mkprg.py | $(DISK)
	$(link_prg)

$(DISK)/BICETEST.PRG: $(BUILD)/bicetest.elf mkprg.py | $(DISK)
	$(link_prg)

$(BUILD) $(DISK) $(OUT):
	mkdir -p $@

verify: $(DISK)/AUDIOTEST.PRG $(DEMO_SONG_FILES) $(DEMO_BANK_FILES) | $(OUT)
	$(PYTHON) verify.py

verify-blackice: $(DISK)/BICETEST.PRG $(BICE_SONG_FILES) $(BICE_BANK_FILES) | $(OUT)
	$(PYTHON) verify.py --blackice

# The one output here meant for ears rather than numbers: the same BICETEST.PRG, recorded off the
# emulated STE and written as a .wav the host can play. No trace, no plain-ST run, no checks.
listen-blackice: $(DISK)/BICETEST.PRG $(BICE_SONG_FILES) $(BICE_BANK_FILES) | $(OUT)
	$(PYTHON) verify.py --blackice --listen

clean:
	rm -rf $(BUILD) $(DISK) $(OUT) $(GENERATED) __pycache__ $(SONGS)/__pycache__

# The header dependencies -MMD wrote on the last build. `-include` and a wildcard, so a tree with no
# build/ (which is what `make clean` leaves) is not an error.
-include $(wildcard $(BUILD)/*.d)
