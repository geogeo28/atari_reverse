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
TARGET_CFLAGS := -m68000 -O2 -fomit-frame-pointer -ffreestanding -nostdlib -fno-jump-tables \
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
