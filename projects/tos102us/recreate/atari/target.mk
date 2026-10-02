# target.mk — the flags EVERY build of this reconstruction for the 68000 uses, in one place.
#
# Two makefiles read it and must not drift apart:
#
#   * atari/Makefile      — the rebuilt ROM image and the two measurement programs: what SHIPS.
#   * ../Makefile         — Tier 3's numerator (kit.mk's $(BENCH_ELF)), which compiles the same
#                           cores to measure what they cost on the machine.
#
# It carries the INCLUDE PATHS as well as the compiler flags, so the two compile the cores against
# the same headers BY CONSTRUCTION rather than by two lists agreeing. The ROM build compiles no core
# yet — it is a stub ROM plus two .PRG drivers — and the day it does, it MUST add $(TARGET_INCLUDES)
# to its own CFLAGS: a ROM built against the kit's off-target psg.h/hw.h/ipl.h would carry the host
# MODEL (a register file in a C array, a no-op interrupt mask) instead of the machine's ports.
#
# A numerator measured under different flags than the shipped build is a number about a program
# nobody runs — an -O2 here and an -Os there is a different routine — so the two read one definition
# rather than keeping a copy each.
#
# -fno-jump-tables: a switch compiled to a table puts absolute addresses in rodata, and every one of
#   them is another fixup the .PRG's relocation table has to carry correctly.
# -Wno-array-bounds: TOS publishes its state in page zero ($466, $4ba), and a dereference of a small
#   absolute address is exactly what -Warray-bounds is built to shout about — right on a host, wrong
#   on a machine whose OS lives there. The Tier 3 build dereferences MORE of them, not fewer: its
#   image base is 0, which is the machine's own arrangement (tools/recreate_kit/rom_bench.py).
# -fno-strict-aliasing: the cores reach one memory through typed accessors of every width (the kit's
#   `be16`/`be32`/`wr16` are `uint16_t`/`uint32_t` accesses on target), and the ROM's order is a read AFTER a
#   store whatever their widths — an overlap a caller can stage. Under type-based aliasing GCC may keep a
#   longword read across a word store: vqt_width's FONT_HOR_TABLE re-read after ptsout[2] was fused into one
#   (a ptsout over the font's header left a different byte than the ROM, Tier 3's second differential RED).
#   The host `.so` reads bytes and can never show it, so the flag is what makes the target the ROM's program.
#   `test/test_tier3.py` pins it in both makefiles' expanded flags.
TARGET_CFLAGS := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -fno-jump-tables -fno-strict-aliasing \
                 -Wall -Wextra -Werror -Wno-array-bounds

# ...and the HEADERS those flags compile the cores against, here for the same reason the flags are:
# the two makefiles must not drift apart. An include path is relative to the makefile that uses it,
# so each includer says where it stands (RECREATE) and where the kit is (KIT), and the ORDER is the
# whole point — `atari/shim_include` first, because that is where the headers the kit declares
# "off-target only" (psg.h, hw.h, ipl.h) have their target halves, and a build that found the kit's
# first would compile the HOST model into the ROM.
ifndef RECREATE
$(error include target.mk with RECREATE set to the path from THIS makefile's directory to \
recreate/ — "." from recreate/Makefile, ".." from recreate/atari/Makefile. The include paths below \
are relative to the makefile that uses them, and a wrong one finds no header rather than the wrong \
one, so this is a loud error and not a default)
endif
ifndef KIT
$(error include target.mk with KIT set to this makefile's path to tools/recreate_kit)
endif
TARGET_INCLUDES := -I$(RECREATE)/atari/shim_include -I$(RECREATE)/include -I$(KIT)/include

# libgcc, and it is not optional: GCC lowers a 32x32 multiply to a call to __mulsi3, so a core as
# small as XBIOS Random does not link without it (the ROM's own code calls Alcyon's `lmul` at the
# same place, for the same reason).
TARGET_LDLIBS := -lgcc

# THE TRANSCRIBED ROUTINES — the build contract for the day the ROM build links cores. The user's rule
# for the hand-written 68000 is C first, and where the C measures over Tier 3's bar, SHIP the ROM's own
# instructions: `include/transcribed.h` is the one table that says which — for every component — and both
# lists below are read out of it rather than kept beside it (`test/test_transcribed.py` pins that they agree
# with the Python view Tier 3 judges by, and that every `.globl` of the `.S` sources is a row of it).
#
#   * TRANSCRIBED_SOURCES / TRANSCRIBED_ENTRIES — what the ROM build LINKS for these routines: the `.S`
#     files and the entries they define. (Tier 3's blob links them today, beside the C: it measures both.)
#     The sources are the TABLE COMPONENTS' `.S` — the VDI's and the AES's — and not `src/*/*.S`: the BIOS's
#     `trap.S`/`isr.S` and GEMDOS's `trap1.S` are entries of another kind, with no table row, and every `.globl`
#     here must be one.
#   * TRANSCRIBED_C_CORES — the C twins it must NOT link. Each is still compiled — its file holds other
#     cores — so the ROM build compiles with -ffunction-sections, links with --gc-sections, and refuses an
#     image in which one of these is still a C BODY: some C still CALLS the core, and on target that call
#     must go through glue to the `.S` entry. The glue carries the core's NAME (a call inside one file is
#     resolved against the section, so only a weak core and a same-named thunk redirect it — see
#     `TRANSCRIBED_CORE`): `bench/shipped_glue.py` generates it from the table, and Tier 3's shipped-
#     configuration blob (`../Makefile`) links and measures exactly that arrangement today.
#
# `sed` rather than the Python parser because this file is read by two makefiles that share no `$(PY)`,
# and `ENTRY.` rather than `ENTRY(` because make counts every parenthesis in a `$(shell ...)`;
# the pin above is what keeps the two parsers honest.
TRANSCRIBED_TABLE   := $(RECREATE)/include/transcribed.h
# THE ALCYON ENTRIES are the one other kind of `.S` in those directories: target-only GLUE that lets a ROM walker's
# Alcyon call (`jsr (a0)` over a pushed frame) enter a C core — the routine a C caller hands by value where the ROM
# hands its own ROM address (`src/aes/obdraw.S`). No ROM bytes, so no table row: listed here, apart, and linked as
# the C is.
ALCYON_ENTRY_SOURCES := $(RECREATE)/src/aes/obdraw.S
TRANSCRIBED_SOURCES := $(filter-out $(ALCYON_ENTRY_SOURCES), \
                         $(wildcard $(RECREATE)/src/vdi/*.S) $(wildcard $(RECREATE)/src/aes/*.S))
TRANSCRIBED_ENTRIES := $(shell sed -n 's/^[[:space:]]*ENTRY.\([a-z0-9_]*\),.*/\1/p' $(TRANSCRIBED_TABLE))
TRANSCRIBED_C_CORES := $(subst _rom_,_,$(TRANSCRIBED_ENTRIES))
