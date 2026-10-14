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
# hands its own ROM address (`src/aes/wmupdate.S`: newrect, mkrect; just_draw has none since ob_draw holds its walk as
# its own body and calls it as C calls, `src/aes/obdraw.c`). No ROM bytes, so no table row: listed here, apart, and
# linked as the C is.
ALCYON_ENTRY_SOURCES := $(RECREATE)/src/aes/wmupdate.S
# THE SWITCH is the third kind: the hand 68000 of the process switch, which has NO C SPELLING at all (a second stack,
# an rte frame built from the caller's return address) — the ROM's own bytes, like a transcription, but with no C twin
# to exclude, no row and no bar: every build links it, and its entries carry the names the event layer's C calls
# (`aes_dsptch`, `include/aes/switch.h`). Listed here, apart; pinned by `test/test_aes_switch.py` (the switch's bytes,
# disp's stream) and `test/test_aes_irq.py` (the glue's).
SWITCH_SOURCES := $(RECREATE)/src/aes/switch.S $(RECREATE)/src/aes/irq.S
# THE TRAP DOOR is the switch's sibling and a fourth kind (band 5 wave 3, slice T): `trap #2`'s handler, its way out,
# aes_entry's stream and the desk's G_USERDEF door — the ROM's bytes, no C twin, no row. Listed APART from the switch
# because it is LINKED AND NOT YET INSTALLED: every build links it, and until the door is bound the build's own code
# still names the ROM's handler by value (`test/test_aes_trapdoor.py` holds who does; the switch's rule is that
# nobody does). Pinned by `test/test_aes_trapdoor.py`.
TRAPDOOR_SOURCES := $(RECREATE)/src/aes/trapdoor.S
TRANSCRIBED_SOURCES := $(filter-out $(ALCYON_ENTRY_SOURCES) $(SWITCH_SOURCES) $(TRAPDOOR_SOURCES), \
                         $(wildcard $(RECREATE)/src/vdi/*.S) $(wildcard $(RECREATE)/src/aes/*.S))
# ---- band 5 wave 4, slice I ----
# GEMSTART is a fifth kind, the switch's and the trap door's sibling: gem_entry — THE ROUTINE THAT SETS UP THE FIRST STACK,
# entered by no call and never returning — and gem_gemdos_call, the ROM's bytes, no C twin, no row; and the Line-F handler
# gem_entry copies, as data. Listed APART because, like the trap door before the narrow flip, it is LINKED AND NOT YET
# ENTERED: every build links it, and the BIOS still starts the ROM's gem_entry until the our-boot machine runs ours
# (slice B). Pinned by `test/test_aes_gemstart.py`. Taken out of the transcriptions' wildcard here, in its own line.
GEMSTART_SOURCES := $(RECREATE)/src/aes/gemstart.S
TRANSCRIBED_SOURCES := $(filter-out $(GEMSTART_SOURCES), $(TRANSCRIBED_SOURCES))
# ---- end of slice I's ----
# ---- band 6 wave 0, slice T ----
# THE LINE-F TABLE is a sixth kind, and the first that holds NO ROM INSTRUCTION: GENERATED (`bench/linef_table.py`; the
# file is checked in and `test/test_aes_lineftable.py` holds it equal to the generator's text) — a table of ours for
# the ROM's Line-F call table, entry for entry, and the thunks that take a ROM caller's Alcyon frame into each C core
# an entry names. Target-only glue, no table row, no C twin. Listed APART because it is LINKED AND NOT BOUND: every
# build links it, and no word of a build names it until the handler's operand is relocated (gemstart.S's eighth, slice
# B's — ruling W6-R1). Taken out of the transcriptions' wildcard here, in its own line.
LINEFTABLE_SOURCES := $(RECREATE)/src/aes/lineftable.S
TRANSCRIBED_SOURCES := $(filter-out $(LINEFTABLE_SOURCES), $(TRANSCRIBED_SOURCES))
# ---- end of slice T's ----
# ---- band 6 wave 1a, the fix pass ----
# THE DESK'S BIOS DOOR is a seventh kind, and a transcription in waiting: trp13 (`$fee478`), the ROM's sixteen bytes,
# byte-pinned, its C twin proved at Tier 1 (`aes_trp13`, `src/desk/deskleaf.c`) and measured over the bar (+214 cycles
# a call) — trp14's case. Listed APART, and outside the transcriptions' two directories, because it is LINKED AND NOT
# ENTERED: every build links it (kit.mk sweeps `src/*/*.S`), no word of a build names it, and it has NO ROW of
# `include/transcribed.h` — a row would make the Line-F table's entries for it ours, which waits for the binding
# (ruling W6-R1). At its flip it becomes a row as `src/aes/trp14.S` is. Pinned by `test/test_desk_leaves.py`.
DESKDOOR_SOURCES := $(RECREATE)/src/desk/trp13.S
# ---- end of the fix pass's ----
TRANSCRIBED_ENTRIES := $(shell sed -n 's/^[[:space:]]*ENTRY.\([a-z0-9_]*\),.*/\1/p' $(TRANSCRIBED_TABLE))
TRANSCRIBED_C_CORES := $(subst _rom_,_,$(TRANSCRIBED_ENTRIES))
