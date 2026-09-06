#!/usr/bin/env python3
"""Audit GRAPHICS.GRA for artwork the game never draws.

GRAPHICS.GRA is a 3328-byte header followed by an RLE stream. `g_unpack_graphics` (the verified
reconstruction of `unpack_graphics @0x10620`) turns those into two consumable tables:

  * buf_b  — 208 road-texture records x 16 pre-shifted copies x 16 bytes = 0xd000 bytes, built from
             the 3328-byte header by `build_sprite_shifts` / `_msk`. Header record `i` owns exactly
             buf_b[i * 0x100 ... (i+1) * 0x100), so a read there names the header record it came from.
  * buf_c  — 240000 bytes of sprite/scenery atlas: page 0 whole, page 1 compacted to its two low
             bit-planes, then pages 2..7 whole. Every sprite blitter sources from here.

METHOD (dynamic read coverage, then a static cross-check, then a poison proof):

 1. Build an INSTRUMENTED copy of the reconstruction. `build/audit/machine.h` shadows the kit's
    `machine.h` on the include path: it includes the real one, then macro-wraps `be16`/`be32`/
    `wr16`/`wr32`/`memcpy`/`memset` so every access inside the buf_b..buf_c window is recorded.
    Nothing else changes, so the instrumented .so is still the verified reconstruction (it passes
    the whole differential suite -- see docs/sprite_audit.md).
 2. Drive that .so through the game: all five legs (twice each -- a real throttled drive and a
    forced course-stream), the leg-select / leg-results / results / high-score / name-entry screens,
    the intermission scroller over its whole scroll range, every HUD dashboard variant, the buggy's
    lean / skid / crash / spin poses, the road backdrop at every band and fine-scroll position, and
    a sweep of every roadside object type x record slot x view x parity x screen-x, in every leg.
 3. A byte counts as USED only if it was read while still holding its unpacked value, judged per
    staged image: a byte the game overwrites before reading (the dashboard map `init_leg_dash`
    builds over the atlas) carries no file content there and is reported separately.
 4. Cross-check statically: walk the per-type and special object records the dispatcher resolves
    (buf_a + 0x8a0 + type * 0xd0 + slot, and buf_a + 0x21d0 + slot) plus the fixed source anchors
    the code carries as constants, and confirm every source pointer lands in read territory.
 5. Prove the verdict: overwrite every never-read byte of the whole window, re-drive all of step 2
    poisoned, and require that drive to agree byte for byte with the clean one over everything they
    touched. A never-read region that the poison run changes would mean a read path the
    instrumentation missed.

Usage:
    python3 tools/sprite_audit.py [--out DIR] [--frames N] [--quick] [--no-poison]

Precondition: the plain candidate `recreate/build/libbuggyboy.so` must already be built (`make` or
`make test` under `recreate/`) -- `import harness` dlopens it before the instrumented copy is made.
`recreate/Makefile` has an `audit` target that builds it first and then runs this script.

`--out DIR` (optional) writes two PNGs per atlas page -- the artwork as the game holds it, and the
same with the never-read regions tinted -- plus the raw coverage bitmap. Generated media is not
committed, so point it at the gitignored `out/`, e.g. `--out out/sprite_audit`.
"""
import argparse
import ctypes
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent          # projects/buggyboy/
RECREATE = PROJECT / "recreate"
WORKSPACE = PROJECT.parents[1]                            # the reverse/ workspace root
KIT = WORKSPACE / "tools" / "recreate_kit"

sys.path.insert(0, str(WORKSPACE / "tools"))              # recreate_kit + extract_graphics + prg_dis
from recreate_kit import project                          # noqa: E402
project.load(RECREATE)                                    # binds loader/emu/oracle to this game
for _sub in ("test", "render", "tools"):
    sys.path.insert(0, str(RECREATE / _sub))

import harness                                            # noqa: E402  (loads the plain candidate)
import extract_graphics as xg                             # noqa: E402  (write_png)
from prg_dis import rd16, rd32, s16                       # noqa: E402  (the workspace's BE readers)
# render_screen / bench_frame / hiscore_demo resolve `harness._lib` at call time, so importing them
# here -- before main() swaps in the instrumented .so -- binds nothing to the plain candidate.
import render_screen as rs                                # noqa: E402
import bench_frame                                        # noqa: E402
import hiscore_demo                                       # noqa: E402

# ---------------------------------------------------------------------------------------------
# The unpacked layout (mirrors recreate/src/graphics.c and render/render_screen.py).
# ---------------------------------------------------------------------------------------------
GRAPHICS_FILE = PROJECT / "bin" / "GRAPHICS.GRA"
HEADER_BYTES = 0xd00                  # the raw sprite/texture header ahead of the RLE stream
HEADER_RECORDS = 208                  # build_sprite_shifts count: 208 * 16 bytes == HEADER_BYTES
HEADER_RECORD_BYTES = 16              # four plane accumulators, stored as 4 hi words + 4 lo words
SHIFTS_PER_RECORD = 16                # pre-shift positions emitted per record
SHIFT_ENTRY_BYTES = 16                # 4 plane words + 4 overflow words
SHIFT_BLOCK_BYTES = SHIFTS_PER_RECORD * SHIFT_ENTRY_BYTES     # 0x100: one record's buf_b footprint
BUF_B_BYTES = HEADER_RECORDS * SHIFT_BLOCK_BYTES              # 0xd000, exactly buf_c - buf_b

ATLAS_BYTES = 240000                  # buf_c holds this much after unpack_graphics compacts page 1
WINDOW_BYTES = BUF_B_BYTES + ATLAS_BYTES      # [buf_b, buf_c + ATLAS_BYTES): the recorded window
PAGE_BYTES = 32000                    # one 320x200 4-plane page
PAGE1_KEPT_BYTES = 16000              # page 1 survives as its two low planes only
PAGE1_OFFSET = PAGE_BYTES             # where the compacted page 1 sits in buf_c
PAGES_TAIL_OFFSET = PAGE_BYTES + PAGE1_KEPT_BYTES             # 48000: pages 2..7 start here
PAGE_COUNT = 8
SCREEN_W, SCREEN_H = 320, 200
ATLAS_ROW_BYTES = 160                 # one 320-pixel 4-plane scanline: every blitter's row pitch
GROUP_BYTES = 8                       # one 16-pixel 4-plane cell
GROUP_PIXELS = 16
GROUPS_PER_ROW = SCREEN_W // GROUP_PIXELS
PAGE1_GROUP_BYTES = 4                 # the compacted page keeps only planes 0 and 1 of each group

# The in-race scenery/car palette: `main` hands 0x17fa2 to Setpalette at the start of a leg (@0x206),
# and g_init_leg refills registers 5 and 7..11 of it per leg from the leg's palette record (see
# gameplay.c, OBJDISP_DST 0x17fb0, whose record head lands at 0x17fb0 - 4 = register 5). So the PNGs
# must run g_init_leg first and only then read this address.
RACE_PALETTE = 0x17fa2
BACKGROUND_INDEX = 0                  # atlas "empty" colour; forced to black so sprites read clearly

# ---------------------------------------------------------------------------------------------
# Game state addresses used to pose the drives. Those render_screen already names are used from it;
# the rest are mirrored from recreate/include/addrs.h and pinned by
# recreate/test/test_sprite_audit_constants.py.
# ---------------------------------------------------------------------------------------------
A_INPUT_STATE = 0x18c44
A_VIEW_FLAGS, A_VIEW_PARITY, A_BONUS_TIMER = 0x18c56, 0x18c60, 0x18d08
A_OBJ_SCAN_OFF = 0x18c58
A_DSP_TOGGLE, A_DSP_VARIANT_IDX = 0x18c7c, 0x18c7e
A_SCROLL_FRAME, A_HSCROLL_POS, A_SCROLL_SPEED = 0x18cb2, 0x18cb8, 0x18cb4
A_CKPT_SCROLL = 0x18c72
A_WHEEL_POS = 0x18cc0
A_ANIM_FRAME = 0x18d0c
A_CRASH_ACTIVE, A_CRASH_FRAME, A_CRASH_BARS, A_CRASH_LAP = 0x18c7a, 0x18c78, 0x18d00, 0x18c4a
A_TIME_LEFT = 0x18cfc
A_COUNTDOWN_TIMER, A_COUNTDOWN_SUB = 0x18262, 0x18264
INPUT_THROTTLE = 0x01

# draw_object_list's three input streams and the dispatcher's record geometry (blit.c / addrs.h).
A_OBJ_LIST_BASE, A_OBJ_FLAGS, A_OBJ_XOFF_TBL = 0x16c06, 0x18ebc, 0x18f26
OBJ_TYPE_BASE, OBJ_TYPE_STRIDE = 0x8a0, 0xd0        # buf_a + this + type * stride = the type record
OBJ_SPECIAL_BASE = 0x21d0                           # buf_a + this: the negative-flag record block
OBJ_REC_SRC, OBJ_REC_ROWS, OBJ_REC_JUMP = 0x00, 0x04, 0x06
OBJ_SLOTS = tuple(range(0, 0xc0, 0x10))             # the d6 record offsets draw_game_objects uses
OBJ_TYPES = tuple(range(1, 64))                     # flag word low 6 bits; type 0 draws nothing
OBJ_SPECIAL_FLAG = 0x8000                           # negative flag word: special pass, normal type 0
OBJ_LIST_ENTRIES = 15                               # objects per display row
OBJ_JUMPTABLE = 0x13144                             # A_obj_type_jumptable
# The table's word entries run from OBJ_JUMPTABLE up to the first handler body, so its length is the
# distance to OBJ_H_STUB. Indexes past it (0x68, 0x6c, 0x6e) read instruction words and "resolve"
# into code -- the bound is what keeps a junk record out of the static cross-check.
OBJ_H_STUB = 0x131ac                # t4 then t1 with x += 0x40, src += 0x20
OBJ_JUMPTABLE_BYTES = OBJ_H_STUB - OBJ_JUMPTABLE    # 0x68
OBJ_H_NOOP = 0x13df8                # a bare rts: a record resolving here draws nothing
# Every other jump-table target obj_dispatch resolves (recreate/src/blit.c, the OBJ_H_* block).
OBJ_HANDLER_TARGETS = frozenset((
    OBJ_H_NOOP, OBJ_H_STUB,
    0x13642, 0x1352c, 0x133b6, 0x131f6,             # T1, T2, W88, T4
    0x1466a, 0x144b2,                               # LO1, LO2
    0x1363e, 0x13528, 0x133b2,                      # T16, T49, T3
    0x13628, 0x13512, 0x13204,                      # T41, T42, T53
    0x131f2, 0x131ca, 0x131d0, 0x131e0,             # HI0, XF0, A6GATE_T4, A6GATE_W88
    0x13622, 0x1361c, 0x1350c, 0x13506,             # PRE_T1_A6, PRE_T1_XFORM, T42PRE, T4CPRE
    0x133ac, 0x133a6,                               # PREW88_44, PREW88_4E
    0x1465c, 0x14664, 0x144a2, 0x144ac,             # DBL, LO_FULL, DBL2, LO_FULL2
    0x13dfa, 0x13e48, 0x13e50, 0x13e5c, 0x13e7c,    # P24, P26, P28, P2A, P2C
    0x13e88, 0x13eae, 0x13eb4, 0x13ec0, 0x13ec6, 0x13ed2,   # P2E, P30, P32, P34, P36, P38
))
OBJ_DRAWING_TARGETS = OBJ_HANDLER_TARGETS - {OBJ_H_NOOP}

# A scratch draw arena for the object sweep, clear of every staged buffer (buf_c ends at 0x76fe0).
SWEEP_ARENA = (0x80000, 0xc0000)
SWEEP_DRAW_BUF = 0x98000
SWEEP_VIEWS = (0, 2, 4, 6, 8, 0x10)
SWEEP_PARITIES = (0, 2)
SWEEP_X = (0x08, 0x58, 0x98)                        # left-clipped, fully on screen, right-clipped
SWEEP_COLOUR = 5
_SWEEP_ARENA_ZEROS = bytes(SWEEP_ARENA[1] - SWEEP_ARENA[0])   # built once; the sweep clears per object

HUD_VARIANT_IDXS = tuple(range(0, 0x40, 8))         # dsp_variant_idx cycles +8 & 0x38
INTERMISSION_SCROLL_RANGE = range(-160, 161, 2)     # covers the scroller top to bottom
RESULTS_MODES = (0, 1, 2)
# g_hiscore_name_entry and g_hiscore_gameover are joystick/music spin loops that never return without
# hardware, so the audit drives their two drawing halves instead: the jingle seam, and every "TIME nn"
# the countdown can show, each followed by the results redraw those loops perform. The real countdown
# starts at COUNTDOWN_START and drops one every CD_SUB_PERIOD+1 = 18 ticks (highscore.c), so the
# displayed values are exactly 30 down to 0 -- driving the timer directly walks the same digit pairs
# (including the '/' the tens digit becomes below 10) for a eighteenth of the frames.
COUNTDOWN_START = 0x1e                              # highscore.c COUNTDOWN_START
COUNTDOWN_VALUES = tuple(range(COUNTDOWN_START, -1, -1))
CRASH_FX_FRAMES = 0x80          # draw_crash_fx frames driven, enough to drain the bonus and roll over

# The road backdrop is a double-wide (640 px) 20-scanline strip; blit_road_scroll picks the band with
# set_screen_offset (the leg's 16-entry scroll table) and the window inside it with hscroll_pos, which
# wraps at SCROLL_WRAP. A drive only walks hscroll_pos as fast as the car happens to scroll, so the
# sweep sets it directly across the whole wrap instead -- otherwise the untouched half of every band
# would look like unused artwork.
SCROLL_FRAMES = tuple(range(16))
SCROLL_WRAP = 0x280
SCROLL_POSITIONS = tuple(range(0, SCROLL_WRAP, 8))
CKPT_SCROLL_POSITIONS = (0, 4, 8, 0xc, 0x10)        # game_update steps it by 4 and resets past 0x10
RESULTS_POSITIONS = (0, 1, 5, 9)
LEGS = tuple(range(5))
DEFAULT_RACE_FRAMES = 6000                          # ~2 minutes of play per drive at 50 Hz
QUICK_RACE_FRAMES = 600

# Buggy pose sweeps, held inside the ranges the game's own tables cover: lean indexes
# buggy_body_tbl (8 bytes per state; entries 0..49 are records, 50 onward is bitmap data), wheel_pos
# indexes a five-entry piece-list table (game_update clamps it to 0..4), and the skid/pitch offsets
# only move the sprite on screen. The foreground-sprite frames are swept from fg_anim_tbl's own
# extent, because A_anim_frame is a raw byte offset into that short table and an invented value would
# blit from wherever the bytes past it happen to point.
LEAN_STATES = tuple(range(0, 50))
SKID_OFFSETS = (0, 4, 8, 0xfffc, 0xfff8)
PITCH_OFFSETS = (0, 0x10, 0x20, 0x40, 0xffe0)
WHEEL_POSITIONS = tuple(range(5))

# The crash/spin script: 8-byte records walked by game_update.c step 6 (lines 316-337). The walk is
# `idx += (uint8_t)(8 - rec[STEP])` and it ends on a record whose lean byte has bit 7 set.
CRASH_ANIM_TBL = 0x18690
CRASH_REC_STEP = 0              # rec+0: the advance is (8 - this) & 0xff
CRASH_REC_LEAN = 1              # rec+1: lean state; bit 7 set = sequence terminator, not a pose
CRASH_REC_PITCH = 2             # rec+2: signed buggy_pitch_off word
CRASH_REC_FG_FRAME = 5          # rec+5: byte offset into fg_anim_tbl for the foreground sprite
CRASH_TERMINAL = 0x80
A_EVT_OBJ_TYPE_TBL = 0x18b68    # word[8] of further script entry indexes, per rpm band (0x11d8e)
EVT_OBJ_TYPES = 8
CRASH_ANIM_TBL_BYTES = A_EVT_OBJ_TYPE_TBL - CRASH_ANIM_TBL   # the table runs up to that neighbour
# The script entry indexes the code writes into collision_lock: the small and big crash starts
# (game_update.c:217, :436, :441), the two finish-line records (GU_DISP_FINISH_A/B) and the two
# bonus-number records (GU_DISP_TYPE_L/R). The per-leg entries in evt_obj_type_tbl are read from the
# image on top of these.
CRASH_SCRIPT_ENTRIES = (8, 0x18, 0x90, 0x1a8, 0x3e8, 0x460)
CRASH_SCRIPT_MAX_STEPS = 64     # a walk longer than the table can hold is a loop; stop and move on

# Fixed source tables in the program image whose entries hold a buf_c-relative source long, plus the
# plain constants the screen blitters carry. draw_buggy_hi / draw_buggy_lo are deliberately absent:
# their sources are a base plus a signed word from a piece list, so they are resolved by running the
# real code in the buggy-pose scene rather than re-derived here.
# draw_num's big sprite character set: num_glyph_tbl maps an ASCII byte to a page-2 offset, and each
# glyph is NUM_GLYPH_ROWS scanlines of one 16-pixel cell. It is the font the leg-name banner and the
# name-entry "TIME nn" are drawn in -- so per-character read coverage says which characters the
# game's own strings ever contain.
NUM_GLYPH_TBL = 0x17c5e         # word byte-offset per ASCII character, into the buffer below
NUM_GLYPH_BUF_OFF = 0xbb80      # buf_c + this = the character set (page 2 offset 0)
NUM_GLYPH_ROWS = 15             # scanlines blitted per character (draw_num's dbf #$e)
NUM_GLYPH_CHARS = "/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

FG_ANIM_TBL = 0x177a0           # [rows-1:w, dst:w, src:l] per foreground-sprite frame
FG_ANIM_STRIDE = 8              # bytes per frame record
FG_ANIM_SRC = 4                 # record field: the buf_c-relative source long
BUGGY_BODY_TBL = 0x177b8        # [src:l, flag:b, rows-1:b, pos:w] per lean state
FG_ANIM_FRAMES = tuple(range(0, BUGGY_BODY_TBL - FG_ANIM_TBL, FG_ANIM_STRIDE))   # 0x00, 0x08, 0x10
BUGGY_BODY_STRIDE = 8           # bytes per lean state in that table
HUD_DSP_TBL = 0x1854c           # [src:l, dst:w, rows-1:w] per dashboard variant
FIXED_SOURCE_CONSTANTS = (
    ("digit glyph buffer (draw_num)", 0xbb80),
    ("checkpoint banner (draw_checkpoint_anim)", 0x9c40),
    ("intermission backdrop (intermission_poll)", 0x32c80),
    ("results row block A (draw_results_screen)", 0x12430),
    ("results row block B (draw_results_screen)", 0x12438),
    ("results column A (draw_results_screen)", 0x11a30),
    ("results column B (draw_results_screen)", 0x11f30),
)

COVERAGE_READ = 0x01                  # read while still holding its unpacked value
COVERAGE_PENDING = 0x02               # written in the bound image; cleared whenever a fresh one binds
COVERAGE_WRITTEN = 0x04               # written by some image at some point (sticky)

POISON_BYTE = 0x5a                    # what the verification pass writes over never-read bytes
MIN_REGION_GROUPS = 8                 # smallest unread blob worth naming as a region in the report
MAX_REGIONS_LISTED = 12               # per page; the tail is summarised as a count


# ---------------------------------------------------------------------------------------------
# Building the instrumented library
# ---------------------------------------------------------------------------------------------
AUDIT_MACHINE_H = """/* Generated by tools/sprite_audit.py -- do not edit; it is rewritten on every run.
 *
 * Shadows the kit's machine.h on the include path: include the real one, then macro-wrap every
 * memory accessor so reads and writes inside a bound address window are recorded. The wrappers are
 * pure bookkeeping, so the resulting .so behaves exactly like the plain candidate.
 */
#ifndef BB_SPRITE_AUDIT_MACHINE_H
#define BB_SPRITE_AUDIT_MACHINE_H
#include <string.h>
#include <stdint.h>
#include "%(kit_machine_h)s"

#define BB_AUDIT_READ    %(read)#04xu   /* read while still holding its unpacked value */
#define BB_AUDIT_PENDING %(pending)#04xu   /* written in the image currently bound (driver clears) */
#define BB_AUDIT_WRITTEN %(written)#04xu   /* written at some point by some image (sticky) */

extern const uint8_t *bb_audit_lo;
extern const uint8_t *bb_audit_hi;
extern uint8_t *bb_audit_map;

/* A byte is marked READ only while it still holds its unpacked value: once the game has written it,
 * later reads see the game's own data and say nothing about the file's content. The gate is
 * BB_AUDIT_PENDING, which the driver clears whenever it binds a freshly unpacked image -- a byte
 * one image overwrote is pristine again in the next, and must not stay suppressed across scenes. */
static inline void bb_audit_touch(const uint8_t *ptr, unsigned nbytes, unsigned flag) {
    if (ptr + nbytes <= bb_audit_lo || ptr >= bb_audit_hi)
        return;
    for (unsigned i = 0; i < nbytes; i++) {
        const uint8_t *at = ptr + i;
        if (at < bb_audit_lo || at >= bb_audit_hi)
            continue;
        uint8_t *slot = &bb_audit_map[at - bb_audit_lo];
        if (flag == BB_AUDIT_READ) {
            if (!(*slot & BB_AUDIT_PENDING))
                *slot |= BB_AUDIT_READ;
        } else {
            *slot |= BB_AUDIT_PENDING | BB_AUDIT_WRITTEN;
        }
    }
}

static inline uint16_t bb_audit_be16(const uint8_t *p) { bb_audit_touch(p, 2, BB_AUDIT_READ); return be16(p); }
static inline uint32_t bb_audit_be32(const uint8_t *p) { bb_audit_touch(p, 4, BB_AUDIT_READ); return be32(p); }
static inline void bb_audit_wr16(uint8_t *p, uint16_t v) { bb_audit_touch(p, 2, BB_AUDIT_WRITTEN); wr16(p, v); }
static inline void bb_audit_wr32(uint8_t *p, uint32_t v) { bb_audit_touch(p, 4, BB_AUDIT_WRITTEN); wr32(p, v); }

static inline void *bb_audit_memcpy(void *dst, const void *src, size_t n) {
    bb_audit_touch((const uint8_t *)src, (unsigned)n, BB_AUDIT_READ);
    bb_audit_touch((const uint8_t *)dst, (unsigned)n, BB_AUDIT_WRITTEN);
    return memcpy(dst, src, n);
}

static inline void *bb_audit_memset(void *dst, int c, size_t n) {
    bb_audit_touch((const uint8_t *)dst, (unsigned)n, BB_AUDIT_WRITTEN);
    return memset(dst, c, n);
}

#undef memcpy
#undef memset
#define be16(p)         bb_audit_be16(p)
#define be32(p)         bb_audit_be32(p)
#define wr16(p, v)      bb_audit_wr16((p), (v))
#define wr32(p, v)      bb_audit_wr32((p), (v))
#define memcpy(d, s, n) bb_audit_memcpy((d), (s), (n))
#define memset(d, c, n) bb_audit_memset((d), (c), (n))
#endif
"""

AUDIT_C = """/* Generated by tools/sprite_audit.py -- the coverage map the wrappers in machine.h write to. */
#include <stdint.h>

const uint8_t *bb_audit_lo = 0;
const uint8_t *bb_audit_hi = 0;
uint8_t *bb_audit_map = 0;

void bb_audit_bind(const uint8_t *lo, const uint8_t *hi, uint8_t *map) {
    bb_audit_lo = lo;
    bb_audit_hi = hi;
    bb_audit_map = map;
}
"""

AUDIT_BUILD_DIR = "build/audit"                       # relative to recreate/, as the -I flag wants
AUDIT_LIBRARY = "build/libbuggyboy_audit.so"


def build_instrumented_library():
    """Compile the reconstruction with the read/write-recording machine.h shadowed in front of the
    kit's. Returns the path of the instrumented .so.

    The build goes through the project's own Makefile (the kit's EXTRA_CFLAGS / EXTRA_SRC hooks) so
    there is one set of build rules, not a copy of them here. The .so is DELETED first: the generated
    headers are not prerequisites of the candidate rule, and make would otherwise hand the drive the
    previous instrumented library -- silently auditing yesterday's code.
    """
    audit_dir = RECREATE / AUDIT_BUILD_DIR
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "machine.h").write_text(AUDIT_MACHINE_H % {
        "kit_machine_h": KIT / "include" / "machine.h",
        "read": COVERAGE_READ, "pending": COVERAGE_PENDING, "written": COVERAGE_WRITTEN})
    (audit_dir / "audit.c").write_text(AUDIT_C)

    out = RECREATE / AUDIT_LIBRARY
    out.unlink(missing_ok=True)
    subprocess.run(["make", f"CAND={AUDIT_LIBRARY}", f"EXTRA_CFLAGS=-I{AUDIT_BUILD_DIR}",
                    f"EXTRA_SRC={AUDIT_BUILD_DIR}/audit.c"], cwd=RECREATE, check=True)
    if not out.exists():
        raise SystemExit(f"make reported success but {out} was not produced")
    return out


# ---------------------------------------------------------------------------------------------
# Little helpers over the flat game image
# ---------------------------------------------------------------------------------------------
def _word(value):
    return (value & 0xffff).to_bytes(2, "big")


def _poke16(image, addr, value):
    image[addr:addr + 2] = _word(value)


def _view(image):
    """The ctypes `uint8_t *` the reconstruction's entry points take."""
    return (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(image)


def check_layout():
    """The assumptions this tool makes about where the game's buffers sit, asserted once."""
    assert rs.BUF_C - rs.BUF_B == BUF_B_BYTES, "buf_b is not 208 * 0x100 bytes wide"
    arena_lo, arena_hi = SWEEP_ARENA
    assert arena_lo >= rs.BUF_AUX + PAGE_BYTES, "the sweep arena overlaps buf_aux"
    assert arena_hi <= harness.IMAGE_SIZE, "the sweep arena runs past the image"
    assert arena_lo <= SWEEP_DRAW_BUF < arena_hi, "the sweep draw buffer is outside its arena"


# ---------------------------------------------------------------------------------------------
# The witness digest that turns "no read was recorded" into "the picture does not depend on it"
# ---------------------------------------------------------------------------------------------
class Witness:
    """A digest over every image a drive touched, with the never-read window bytes zeroed.

    Two drives whose digests agree -- one over the real data, one with those bytes poisoned -- prove
    that nothing the game draws depends on them, including through read paths the instrumentation
    does not wrap.

    The mask is only known after the first drive, so that drive digests each image's
    outside-the-window bytes as it goes and keeps that digest beside the window slice;
    `finalise(mask)` then masks the stash and closes. A later drive is given the mask up front and
    keeps nothing. Both fold the same per-image pair -- outside digest, then masked window -- in the
    same image order, so the two are comparable; folding all the outside digests first and the
    windows afterwards would not be.
    """

    def __init__(self, lo, hi, mask=None):
        self._lo, self._hi = lo, hi
        self._mask = mask
        self._digest = hashlib.sha256()
        self._stash = None if mask is not None else []

    def add(self, image):
        outside = hashlib.sha256()
        view = memoryview(image)
        outside.update(view[:self._lo])
        outside.update(view[self._hi:])
        window = np.frombuffer(image, dtype=np.uint8, offset=self._lo,
                               count=self._hi - self._lo).copy()
        if self._stash is None:
            self._fold(outside.digest(), window, self._mask)
        else:
            self._stash.append((outside.digest(), window))

    def _fold(self, outside_digest, window, mask):
        self._digest.update(outside_digest)
        window[mask] = 0
        self._digest.update(window.tobytes())

    def finalise(self, mask=None):
        for outside_digest, window in self._stash or ():
            self._fold(outside_digest, window, self._mask if mask is None else mask)
        self._stash = []
        return self._digest.hexdigest()


# ---------------------------------------------------------------------------------------------
# Scenes: one staged image at a time, handed to whichever sink is driving
# ---------------------------------------------------------------------------------------------
class Scene:
    """Owns the image currently being driven and hands each finished one to the sink.

    Exactly one image is pinned at a time, and the pin is load-bearing: the next image is staged --
    and, in the race scenes, unpacked -- while `bb_audit_bind` still points into this one, so
    releasing it early could let the allocator hand the same addresses to its successor and have the
    recorder attribute the new image's writes to the old map. An image is retired (and so digested)
    only once its successor exists, which is also the moment its own state stops changing.
    """

    def __init__(self, sink):
        self._sink = sink
        self._image = None
        self._pin = None

    def bind(self, image):
        pin = _view(image)                     # created before the previous pin is dropped
        self._retire()
        self._image, self._pin = image, pin
        self._sink.bound(image, pin)
        return pin

    def close(self):
        self._retire()

    def _retire(self):
        if self._image is not None:
            self._sink.retired(self._image)
        self._image = self._pin = None


class Drive:
    """Runs the scene list once. Subclasses decide what happens to each image."""

    def __init__(self, witness=None, label=""):
        self.witness = witness
        self.label = label

    def record(self, name, run):
        print(f"  {self.label}driving {name} ...", flush=True)
        started = time.perf_counter()
        scene = Scene(self)
        run(scene)
        scene.close()
        self.finished(name, time.perf_counter() - started)

    def bound(self, image, pin):
        """Called when `image` becomes the scene's live image."""

    def retired(self, image):
        if self.witness is not None:
            self.witness.add(image)

    def finished(self, name, seconds):
        """Called at the end of each scene."""


class Coverage(Drive):
    """One byte of state per byte of [buf_b, buf_c + ATLAS_BYTES), unioned across every scene."""

    def __init__(self, lib, witness=None):
        super().__init__(witness=witness)
        self.lib = lib
        self.lo = rs.BUF_B
        self.hi = rs.BUF_C + ATLAS_BYTES
        self.map = np.zeros(WINDOW_BYTES, dtype=np.uint8)
        self.lib.bb_audit_bind.argtypes = [ctypes.c_void_p] * 3
        self.lib.bb_audit_bind.restype = None
        self.scene_totals = []
        self._before = 0

    def read_count(self):
        return int((self.map & COVERAGE_READ).sum())

    def record(self, name, run):
        self._before = self.read_count()
        super().record(name, run)

    def bound(self, image, pin):
        """Attach `image` (a freshly unpacked game image) to the recorder.

        The per-image write gate is cleared here: this image's atlas is pristine again, so a byte an
        earlier image overwrote must be allowed to record a read.
        """
        self.map &= ~np.uint8(COVERAGE_PENDING)
        base = ctypes.addressof(pin)
        self.lib.bb_audit_bind(base + self.lo, base + self.hi, self.map.ctypes.data)

    def finished(self, name, seconds):
        self.lib.bb_audit_bind(None, None, None)
        after = self.read_count()
        self.scene_totals.append((name, after - self._before, after, seconds))


# ---------------------------------------------------------------------------------------------
# Scene drivers
# ---------------------------------------------------------------------------------------------
class Driver:
    """Calls the instrumented library's `g_*` entries and stages the images the scenes need."""

    def __init__(self, lib):
        self.lib = lib
        self.poison_mask = None       # set to a never-read boolean mask for the poison drive
        # One post-unpack image, copied for every staged scene. `_prepared_image` applies its pokes
        # BEFORE g_unpack_graphics, but no address this tool pokes feeds the unpacker (it reads only
        # the buffer-base longs and the staged GRAPHICS.GRA), so staging by copy is equivalent to
        # re-running the unpack per scene -- and 300-odd unpacks cheaper.
        template, pin = rs._prepared_image({})
        del pin
        self._template = template

    def call(self, name, buf, *extra):
        fn = getattr(self.lib, name)
        fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * len(extra)
        fn.restype = None
        fn(buf, *extra)

    def staged(self, pokes=None):
        """A fresh image with the real data files staged and g_unpack_graphics already run."""
        image = bytearray(self._template)
        for addr, value in (pokes or {}).items():
            image[addr:addr + len(value)] = value
        self.poison(image)
        return image

    def poison(self, image):
        """Overwrite the bytes `poison_mask` selects, so a read of one would change what is drawn."""
        if self.poison_mask is None:
            return
        lo, hi = rs.BUF_B, rs.BUF_C + ATLAS_BYTES
        np.frombuffer(image, dtype=np.uint8, offset=lo, count=hi - lo)[self.poison_mask] = POISON_BYTE

    def race(self, scene, leg, frames, forced):
        """One drive of `leg`: real course, oracle init_leg, then `frames` full rendered frames.

        `forced` streams the course at one section per frame (bench_frame's warmup rule) so a short
        run still walks the whole leg; otherwise the throttle is held and the car drives normally.
        """
        state = bench_frame.mid_race_state(leg, 0)
        self.poison(state)
        buf = scene.bind(state)
        state[rs.A_MEM_BASE:rs.A_MEM_BASE + 4] = rs.MEM_BASE.to_bytes(4, "big")
        self.call("g_init_leg_dash", buf)                 # builds the HUD course map into buf_c
        self.call("g_draw_leg_labels", buf)               # stamps the dashboard leg name into buf_c
        for _ in range(frames):
            if forced:
                bench_frame._force_advance(state)
            else:
                _poke16(state, A_INPUT_STATE, INPUT_THROTTLE)
            self.call("g_game_update", buf)
            self.call("g_draw_frame", buf)

    def leg_screens(self, scene):
        """The leg-select board: the leg-results screen, its panels, labels and dashboard map."""
        for leg in LEGS:
            image = self.staged({rs.A_LEG_INDEX: _word(leg),
                                 rs.A_MEM_BASE: rs.MEM_BASE.to_bytes(4, "big")})
            buf = scene.bind(image)
            for entry in ("g_init_leg_dash", "g_draw_leg_results", "g_draw_panel5", "g_draw_panel3",
                          "g_draw_panel2", "g_draw_divider", "g_draw_leg_labels"):
                self.call(entry, buf)
            self.call("g_draw_dashboard", buf, rs.DASH_DST_OFF)

    def results_screens(self, scene):
        """The results / high-score screen over its modes and ranks, plus the two drawing halves of
        the name-entry tail: the jingle seam, and every "TIME nn" the countdown can show with the
        redraw that follows it. g_hiscore_name_entry and g_hiscore_gameover themselves are
        joystick/music spin loops that never return without hardware; their bodies compose only calls
        covered here (see docs/sprite_audit.md, "What this audit does and does not establish").

        mode and rank are poked AFTER g_update_highscore, which writes both itself (highscore.c
        ~71-79) -- poking them before it would leave the loop redrawing one screen five times over.
        """
        for leg in LEGS:
            for mode in RESULTS_MODES:
                for pos in RESULTS_POSITIONS:
                    image = self.staged({rs.A_LEG_INDEX: _word(leg),
                                         hiscore_demo.A_SCORE_BCD: hiscore_demo.PLAYER})
                    buf = scene.bind(image)
                    self.call("g_init_scoretable", buf)
                    self.call("g_update_highscore", buf)
                    _poke16(image, rs.A_HISCORE_POS, pos)
                    _poke16(image, rs.A_RESULTS_MODE, mode)
                    for entry in ("g_draw_results_screen", "g_hiscore_name_entry_jingle"):
                        self.call(entry, buf)
                    for timer in COUNTDOWN_VALUES:
                        _poke16(image, A_COUNTDOWN_TIMER, timer)
                        _poke16(image, A_COUNTDOWN_SUB, 0)    # no decrement: render this value
                        self.call("g_hiscore_countdown", buf)
                        self.call("g_draw_results_screen", buf)

    def intermission(self, scene):
        """The attract-mode scroller across its whole travel, plus the backdrop restore blit."""
        for scroll in INTERMISSION_SCROLL_RANGE:
            image = self.staged({rs.A_LEG_INDEX: _word(0), rs.A_SCROLL: _word(scroll)})
            buf = scene.bind(image)
            self.call("g_init_scoretable", buf)
            self.call("g_draw_intermission", buf)
            self.call("g_intermission_poll", buf)

    def hud_variants(self, scene):
        """Every dashboard-variant sprite the HUD can select, plus the crash/game-over effect."""
        for leg in LEGS:
            for idx in HUD_VARIANT_IDXS:
                image = self.staged({rs.A_LEG_INDEX: _word(leg), A_DSP_TOGGLE: _word(0),
                                     A_DSP_VARIANT_IDX: _word(idx)})
                buf = scene.bind(image)
                self.call("g_init_leg", buf)
                _poke16(image, A_DSP_TOGGLE, 0)               # g_init_leg resets both
                _poke16(image, A_DSP_VARIANT_IDX, idx)
                self.call("g_draw_hud", buf)
        image = self.staged({rs.A_LEG_INDEX: _word(0)})
        buf = scene.bind(image)
        for field, value in ((A_CRASH_ACTIVE, 1), (A_CRASH_FRAME, 0x20), (A_CRASH_BARS, 5),
                             (A_CRASH_LAP, 3), (A_TIME_LEFT, 0x40)):
            _poke16(image, field, value)
        for _ in range(CRASH_FX_FRAMES):
            self.call("g_draw_crash_fx", buf, rs.SCREEN_BASE)

    def buggy_poses(self, scene):
        """The player car through its lean / wheel / skid / pitch range and its own crash script."""
        for leg in LEGS:
            image = self.staged({rs.A_LEG_INDEX: _word(leg)})
            buf = scene.bind(image)
            for lean in LEAN_STATES:
                for wheel in WHEEL_POSITIONS:
                    _poke16(image, rs.A_LEAN_STATE, lean)
                    _poke16(image, A_WHEEL_POS, wheel)
                    self.call("g_draw_buggy", buf)
            for skid in SKID_OFFSETS:
                for pitch in PITCH_OFFSETS:
                    _poke16(image, rs.A_LEAN_STATE, 0)
                    _poke16(image, rs.A_BUGGY_SKID, skid)
                    _poke16(image, rs.A_BUGGY_PITCH, pitch)
                    self.call("g_draw_buggy", buf)
            for lean, pitch, frame in crash_script_poses(image):   # the flip / spin-out sequences
                _poke16(image, rs.A_LEAN_STATE, lean)
                _poke16(image, rs.A_BUGGY_PITCH, pitch)
                _poke16(image, A_ANIM_FRAME, frame)
                self.call("g_draw_fg_sprite", buf)     # the fireball, under the tumbling body
                self.call("g_draw_buggy", buf)
            for frame in FG_ANIM_FRAMES:               # every frame the table holds, script or not
                _poke16(image, A_ANIM_FRAME, frame)
                self.call("g_draw_fg_sprite", buf)
            self.call("g_draw_checkpoint_anim", buf)

    def road_scroll_sweep(self, scene):
        """Every road-backdrop band, at every fine-scroll position the wrap allows.

        scroll_speed is zeroed so blit_road_scroll's own advance is a no-op and hscroll_pos stays
        where the sweep puts it; everything else is the real blitter reading the real band.
        """
        for leg in LEGS:
            image = self.staged({rs.A_LEG_INDEX: _word(leg)})
            buf = scene.bind(image)
            self.call("g_init_leg", buf)
            _poke16(image, A_SCROLL_SPEED, 0)
            for frame in SCROLL_FRAMES:
                _poke16(image, A_SCROLL_FRAME, frame)
                self.call("g_set_screen_offset", buf)
                for position in SCROLL_POSITIONS:
                    _poke16(image, A_HSCROLL_POS, position)
                    self.call("g_blit_road_scroll", buf)
            for position in CKPT_SCROLL_POSITIONS:
                _poke16(image, A_CKPT_SCROLL, position)
                self.call("g_draw_checkpoint_anim", buf)

    def object_sweep(self, scene):
        """Every roadside object type -- and the special pass -- through every record slot, view,
        parity and screen-x.

        This is the reachability sweep: it ignores what the course data actually schedules and draws
        each type straight from its record, so a sprite only some leg's traffic reaches still counts.
        A flag word with bit 15 set selects the special-record block at buf_a + 0x21d0 + slot
        (blit.c's SPECIAL pass); its low six bits are 0, so the normal pass draws nothing alongside.
        """
        dispatch = self.lib.g_draw_object_list
        dispatch.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
        dispatch.restype = None
        flag_words = OBJ_TYPES + (OBJ_SPECIAL_FLAG,)
        for leg in LEGS:
            image = self.staged({rs.A_LEG_INDEX: _word(leg)})
            buf = scene.bind(image)
            self.call("g_init_leg", buf)                   # fills the per-type records for this leg
            for view in SWEEP_VIEWS:
                for parity in SWEEP_PARITIES:
                    _poke16(image, A_VIEW_FLAGS, view)
                    _poke16(image, A_VIEW_PARITY, parity)
                    _poke16(image, A_BONUS_TIMER, 0)
                    _poke16(image, A_OBJ_SCAN_OFF, 0)
                    _poke16(image, A_OBJ_XOFF_TBL, 0)
                    for screen_x in SWEEP_X:
                        for flag_word in flag_words:
                            _stage_one_object(image, flag_word, screen_x)
                            for slot in OBJ_SLOTS:
                                dispatch(buf, A_OBJ_LIST_BASE, A_OBJ_FLAGS,
                                         SWEEP_DRAW_BUF, 0, slot, SWEEP_COLOUR)


def _stage_one_object(image, flag_word, screen_x):
    """Put a single object carrying `flag_word` at `screen_x` in an otherwise empty display row."""
    arena_lo, arena_hi = SWEEP_ARENA
    image[arena_lo:arena_hi] = _SWEEP_ARENA_ZEROS
    row = _word(0) + _word(0) + b"".join(_word(screen_x if i == 0 else 0)
                                         for i in range(OBJ_LIST_ENTRIES))
    image[A_OBJ_LIST_BASE:A_OBJ_LIST_BASE + len(row)] = row
    flags = b"".join(_word(flag_word if i == 0 else 0) for i in range(OBJ_LIST_ENTRIES))
    image[A_OBJ_FLAGS:A_OBJ_FLAGS + len(flags)] = flags


def drive_everything(driver, sink, race_frames):
    """Run every scene into one drive, in a fixed order so a re-run reproduces exactly.

    The order also matters to the poison proof, which digests the images each scene touched: the
    clean and poisoned drives must present the same sequence.
    """
    for leg in LEGS:
        sink.record(f"race leg {leg} (throttle held)",
                    lambda scene, leg=leg: driver.race(scene, leg, race_frames, forced=False))
    for leg in LEGS:
        sink.record(f"race leg {leg} (forced course stream)",
                    lambda scene, leg=leg: driver.race(scene, leg, race_frames, forced=True))
    sink.record("leg-select / leg-results screens", driver.leg_screens)
    sink.record("results / high-score / name entry", driver.results_screens)
    sink.record("intermission scroller", driver.intermission)
    sink.record("HUD variants + crash effect", driver.hud_variants)
    sink.record("buggy poses + checkpoint anim", driver.buggy_poses)
    sink.record("road backdrop + checkpoint scroll sweep", driver.road_scroll_sweep)
    sink.record("roadside object type sweep", driver.object_sweep)


# ---------------------------------------------------------------------------------------------
# Mapping coverage back onto the header records and the atlas pages
# ---------------------------------------------------------------------------------------------
def header_record_report(coverage_map, header_bytes):
    """Per header record: was any of its 16 pre-shifted copies in buf_b ever read?

    Returns a list of dicts, one per record, carrying the record's raw 16 source bytes so an unused
    one can be shown for what it is.
    """
    sources = [bytes(header_bytes[i * HEADER_RECORD_BYTES:(i + 1) * HEADER_RECORD_BYTES])
               for i in range(HEADER_RECORDS)]
    records = []
    for index in range(HEADER_RECORDS):
        block = coverage_map[index * SHIFT_BLOCK_BYTES:(index + 1) * SHIFT_BLOCK_BYTES]
        shifts_read = [bool((block[s * SHIFT_ENTRY_BYTES:(s + 1) * SHIFT_ENTRY_BYTES]
                             & COVERAGE_READ).any()) for s in range(SHIFTS_PER_RECORD)]
        records.append({
            "index": index,
            "read": any(shifts_read),
            "shifts_read": sum(shifts_read),
            "source": sources[index],
            "blank": not any(sources[index]),
        })
    # A never-read record whose bytes also sit at a record that IS read costs the game no unique
    # texture -- it is a duplicate table slot, not lost artwork. Pair them up so the report can say so.
    for record in records:
        record["duplicate_of"] = [other["index"] for other in records
                                  if other["read"] and other["source"] == record["source"]]
    return records


def header_record_pattern(source):
    """The record's 16-pixel 4-plane pattern as one hex nibble per pixel (plane 0 = LSB).

    build_sprite_shifts reads word[k] as plane k's high half and word[k+4] as its low half, so the
    stored 16 pixels are the high words -- the low words are what shifts in behind them.
    """
    planes = [int.from_bytes(source[2 * k:2 * k + 2], "big") for k in range(4)]
    return "".join("%x" % sum(((plane >> (15 - bit)) & 1) << index
                              for index, plane in enumerate(planes))
                   for bit in range(16))


def atlas_page_slices():
    """(page, buf_c start, byte length, bytes per 16-pixel group) for each page, in buf_c order."""
    slices = [(0, 0, PAGE_BYTES, GROUP_BYTES), (1, PAGE1_OFFSET, PAGE1_KEPT_BYTES, PAGE1_GROUP_BYTES)]
    for page in range(2, PAGE_COUNT):
        slices.append((page, PAGES_TAIL_OFFSET + (page - 2) * PAGE_BYTES, PAGE_BYTES, GROUP_BYTES))
    return slices


def page_grids(atlas_bytes, atlas_cov, start, length, group_bytes):
    """Per 16-pixel group of one page: was it read, was it written, does it hold ink?

    Groups are the natural unit: every blitter reads a whole 4-plane cell at a time. The compacted
    page keeps only two planes per group, so its group is 4 bytes rather than 8.
    """
    rows = length // (GROUPS_PER_ROW * group_bytes)
    cov = atlas_cov[start:start + length].reshape(rows, GROUPS_PER_ROW, group_bytes)
    pix = np.frombuffer(atlas_bytes[start:start + length], dtype=np.uint8).reshape(
        rows, GROUPS_PER_ROW, group_bytes)
    read = (cov & COVERAGE_READ).any(axis=2)
    written = (cov & COVERAGE_WRITTEN).any(axis=2)
    ink = (pix != 0).any(axis=2)
    return read, written, ink


def unread_regions(read, ink, min_groups=MIN_REGION_GROUPS):
    """Bounding boxes of connected blobs of never-read groups that still hold ink.

    4-connected flood fill over the group grid; boxes are returned in pixel coordinates, largest
    first, so the report can name the biggest untouched pictures.
    """
    target = ink & ~read
    rows, cols = target.shape
    seen = np.zeros_like(target)
    boxes = []
    for row in range(rows):
        for col in range(cols):
            if not target[row, col] or seen[row, col]:
                continue
            stack, blob = [(row, col)], []
            seen[row, col] = True
            while stack:
                at_row, at_col = stack.pop()
                blob.append((at_row, at_col))
                for step_row, step_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_row, next_col = at_row + step_row, at_col + step_col
                    if not (0 <= next_row < rows and 0 <= next_col < cols):
                        continue
                    if target[next_row, next_col] and not seen[next_row, next_col]:
                        seen[next_row, next_col] = True
                        stack.append((next_row, next_col))
            if len(blob) < min_groups:
                continue
            blob_rows = [at_row for at_row, _ in blob]
            blob_cols = [at_col for _, at_col in blob]
            boxes.append({"x": min(blob_cols) * GROUP_PIXELS, "y": min(blob_rows),
                          "w": (max(blob_cols) - min(blob_cols) + 1) * GROUP_PIXELS,
                          "h": max(blob_rows) - min(blob_rows) + 1, "groups": len(blob)})
    boxes.sort(key=lambda b: -b["groups"])
    return boxes


# ---------------------------------------------------------------------------------------------
# The static cross-check: every source pointer the game can resolve must land in read territory
# ---------------------------------------------------------------------------------------------
def _crash_script_entries(image):
    """Every index the game writes into collision_lock: the fixed starts plus the per-rpm-band
    table init_leg fills. A zero entry is "no script", and an odd one is not a record boundary."""
    entries = list(CRASH_SCRIPT_ENTRIES)
    entries += [rd16(image, A_EVT_OBJ_TYPE_TBL + slot * 2) for slot in range(EVT_OBJ_TYPES)]
    return sorted({entry for entry in entries
                   if entry and not entry % 2 and entry < CRASH_ANIM_TBL_BYTES})


def crash_script_poses(image):
    """The (lean, pitch, foreground frame) triples crash_anim_tbl can actually put on screen.

    The script is a linked walk, not an array: game_update.c step 6 advances the index by
    `(uint8_t)(8 - rec[STEP])` and stops on a record whose lean byte has bit 7 set. Walking it from
    the real entry points -- rather than reading N fixed-stride records from 0 -- is what keeps
    A_anim_frame inside fg_anim_tbl and the lean inside buggy_body_tbl; a terminator's lean byte is
    0x80-something, which would index buggy_body_tbl well past its end.

    Two records (indexes 0x190 and 0x2a8) carry step 8, so their advance is 0 and the script holds on
    them until some other state moves it. They are poses like any other, but the walk must stop there
    rather than spin.
    """
    poses = set()
    for entry in _crash_script_entries(image):
        index = entry
        for _ in range(CRASH_SCRIPT_MAX_STEPS):
            record = CRASH_ANIM_TBL + index
            lean = image[record + CRASH_REC_LEAN]
            if lean & CRASH_TERMINAL:
                break
            poses.add((lean, rd16(image, record + CRASH_REC_PITCH),
                       image[record + CRASH_REC_FG_FRAME]))
            step = (8 - image[record + CRASH_REC_STEP]) & 0xff
            index += step
            if step == 0 or index >= CRASH_ANIM_TBL_BYTES:
                break
    return sorted(poses)


def fixed_source_pointers(image):
    """buf_c source offsets the program's own fixed tables and constants name."""
    pointers = {}
    for label, offset in FIXED_SOURCE_CONSTANTS:
        pointers.setdefault(offset, []).append(label)
    for lean in LEAN_STATES:
        pointers.setdefault(rd32(image, BUGGY_BODY_TBL + lean * BUGGY_BODY_STRIDE),
                            []).append(f"buggy body lean {lean}")
    for idx in HUD_VARIANT_IDXS:
        pointers.setdefault(rd32(image, HUD_DSP_TBL + idx), []).append(f"HUD variant 0x{idx:02x}")
    for frame in FG_ANIM_FRAMES:
        pointers.setdefault(rd32(image, FG_ANIM_TBL + frame + FG_ANIM_SRC),
                            []).append(f"fg frame 0x{frame:02x}")
    return {src: labels for src, labels in pointers.items() if src < ATLAS_BYTES}


def character_set_report(image, atlas_cov):
    """Per character of draw_num's sprite font: was any byte of its glyph ever read?

    The glyph's source is num_glyph_tbl[char] + NUM_GLYPH_BUF_OFF, NUM_GLYPH_ROWS scanlines of one
    cell. Every character in the table is drawable by construction -- any string reaching draw_num
    that contains it renders it -- so an unread glyph means no string the drive produced used it.
    """
    status = []
    for char in NUM_GLYPH_CHARS:
        offset = NUM_GLYPH_BUF_OFF + rd16(image, NUM_GLYPH_TBL + ord(char) * 2)
        read = any((atlas_cov[offset + row * ATLAS_ROW_BYTES:
                              offset + row * ATLAS_ROW_BYTES + GROUP_BYTES]
                    & COVERAGE_READ).any() for row in range(NUM_GLYPH_ROWS))
        status.append((char, offset, read))
    return status


def object_record_pointers(driver):
    """Walk the object records g_init_leg fills, per leg, and collect their buf_c source spans.

    Returns (pointers, malformed) where `pointers` maps (source offset, rows-1) to the records that
    name it and `malformed` counts slots whose jump index says "no sprite here".
    """
    pointers, malformed = {}, 0
    for leg in LEGS:
        image = driver.staged({rs.A_LEG_INDEX: _word(leg)})
        pin = _view(image)
        driver.call("g_init_leg", pin)
        del pin
        blocks = [(f"type 0x{obj_type:02x}", rs.BUF_A + OBJ_TYPE_BASE + obj_type * OBJ_TYPE_STRIDE)
                  for obj_type in OBJ_TYPES]
        blocks.append(("special", rs.BUF_A + OBJ_SPECIAL_BASE))
        for label, base in blocks:
            for slot in OBJ_SLOTS:
                record = base + slot
                src = rd32(image, record + OBJ_REC_SRC)
                rows = rd16(image, record + OBJ_REC_ROWS)
                jump = rd16(image, record + OBJ_REC_JUMP)
                if not _record_is_live(image, src, jump):
                    malformed += 1
                    continue
                pointers.setdefault((src, rows), []).append((leg, label, slot, rows, jump))
    return pointers, malformed


def _record_is_live(image, src, jump):
    """A record names a real sprite only if its jump index is inside obj_type_jumptable and resolves
    to a handler that draws something.

    No height heuristic: a record's rows-1 word is whatever the sprite is tall (type 0x36 slot 0 is
    0x64 rows), and rejecting the tall ones dropped real artwork from the cross-check.
    """
    if src == 0 or src >= ATLAS_BYTES:
        return False
    if jump % 2 or jump >= OBJ_JUMPTABLE_BYTES:
        return False
    target = OBJ_JUMPTABLE + s16(rd16(image, OBJ_JUMPTABLE + jump))
    return target in OBJ_DRAWING_TARGETS


def source_span(src, rows_m1):
    """The atlas bytes a sprite sourced at `src` with `rows_m1`+1 rows can read.

    Every blitter walks its source UP one 160-byte scanline per row (per row it advances a cell at a
    time and then rewinds by the row pitch plus the cells), and a left-clipped sprite starts part-way
    into its first row -- so probing the 8 bytes at `src` alone can miss a sprite that is drawn.
    """
    return max(0, src - rows_m1 * ATLAS_ROW_BYTES), min(ATLAS_BYTES, src + ATLAS_ROW_BYTES)


def static_cross_check(spans, atlas_cov):
    """Source spans no dynamic scene ever read in -- each one is a hole in the drive, not a find."""
    misses = []
    for (src, rows_m1), users in sorted(spans.items()):
        lo, hi = source_span(src, rows_m1)
        if not (atlas_cov[lo:hi] & COVERAGE_READ).any():
            misses.append((src, users))
    return misses


def fixed_cross_check(pointers, atlas_cov):
    """The fixed tables carry no row count, so their sources are probed one cell wide."""
    return static_cross_check({(src, 0): labels for src, labels in pointers.items()}, atlas_cov)


# ---------------------------------------------------------------------------------------------
# The poison proof
# ---------------------------------------------------------------------------------------------
def poison_verification(driver, race_frames, never_read):
    """Re-drive EVERY scene with the never-read window bytes overwritten, and require the result to
    match the clean drive byte for byte.

    The instrumentation only sees the accessors it wraps, so "the recorder saw no read" is a claim
    about the recorder. This is the claim about the program: each drive digests every image it
    touched, with the never-read bytes zeroed in both so the poison itself cannot show up. If any of
    those bytes reached a pixel, a buffer or a piece of state, the digests diverge.
    """
    driver.poison_mask = never_read
    witness = Witness(rs.BUF_B, rs.BUF_C + ATLAS_BYTES, mask=never_read)
    drive_everything(driver, Drive(witness=witness, label="poisoned: "), race_frames)
    driver.poison_mask = None
    return witness.finalise()


# ---------------------------------------------------------------------------------------------
# PNG output
# ---------------------------------------------------------------------------------------------
def decode_page(atlas_bytes, start, group_bytes):
    """One page's palette indices, from the interleaved form buf_c holds after unpack_graphics.

    Neither render_screen._decode_interleaved nor st_pixels.decode_planar is reused here: both are
    fixed at four planes, and buf_c's page 1 is the two-plane compacted one. One vectorised decoder
    over `group_bytes // 2` planes covers both shapes without a second copy of the bit shuffle.
    """
    planes = group_bytes // 2
    words = np.frombuffer(atlas_bytes, dtype=">u2", offset=start,
                          count=SCREEN_H * GROUPS_PER_ROW * planes).reshape(
                              SCREEN_H, GROUPS_PER_ROW, planes, 1)
    bits = (words >> np.arange(GROUP_PIXELS - 1, -1, -1, dtype=np.uint16)) & 1
    indices = (bits.astype(np.uint8) << np.arange(planes, dtype=np.uint8)[:, None]).sum(axis=2)
    return indices.reshape(SCREEN_H, SCREEN_W).astype(np.uint8)


HIGHLIGHT_RGB = (255, 0, 220)         # tint over groups the game never reads
HIGHLIGHT_MIX = 0.62                  # how strongly the tint wins over the artwork underneath
PALETTE_COLOURS = 16                  # an ST low-res palette; the tint ramp adds a second copy above it


def write_page_pngs(outdir, atlas_bytes, atlas_cov, palette):
    """Per page: the artwork as the game holds it, and the same with never-read groups tinted."""
    rgb_palette = list(palette)
    rgb_palette[BACKGROUND_INDEX] = (0, 0, 0)     # the atlas's "empty" colour, blacked out once
    tint_palette = _build_tint_palette(rgb_palette)
    written = []
    for page, start, length, group_bytes in atlas_page_slices():
        rows = decode_page(atlas_bytes, start, group_bytes)
        plain = outdir / f"page{page}.png"
        xg.write_png(str(plain), SCREEN_W, SCREEN_H, rows, rgb_palette)

        read, _written, ink = page_grids(atlas_bytes, atlas_cov, start, length, group_bytes)
        overlay = outdir / f"page{page}_unread.png"
        xg.write_png(str(overlay), SCREEN_W, SCREEN_H, _tint_unread(rows, ink & ~read), tint_palette)
        written += [plain, overlay]
    return written


def _tint_unread(rows, highlight):
    """Re-index each pixel into the tint ramp: 0..15 the real colours, 16..31 their tinted twins.

    Only cells that hold ink AND were never read are tinted -- an unread cell of empty background is
    not a finding, and tinting it would bury the ones that are.
    """
    per_pixel = np.repeat(highlight, GROUP_PIXELS, axis=1)
    return rows + per_pixel.astype(np.uint8) * PALETTE_COLOURS


def _build_tint_palette(rgb_palette):
    """The first PALETTE_COLOURS entries are the game's colours; the next are the same blended
    toward HIGHLIGHT_RGB, which is how a never-read cell is marked."""
    return list(rgb_palette) + [
        tuple(int(base[channel] * (1 - HIGHLIGHT_MIX) + HIGHLIGHT_RGB[channel] * HIGHLIGHT_MIX)
              for channel in range(3)) for base in rgb_palette[:PALETTE_COLOURS]]


# ---------------------------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------------------------
def report_scenes(coverage):
    print("=" * 96)
    print("GRAPHICS.GRA usage audit")
    print("=" * 96)
    print("\nScenes driven (bytes each one added to the union):")
    for name, added, running, seconds in coverage.scene_totals:
        print(f"  {name:<40s} +{added:>7d}   running {running:>7d}   {seconds:6.2f}s")


def report_header_records(buf_b_cov, records):
    print(f"\nHeader / road-texture table (buf_b): "
          f"{int((buf_b_cov & COVERAGE_READ).sum())}/{BUF_B_BYTES} bytes read")
    unused = [record for record in records if not record["read"]]
    blank = [record for record in unused if record["blank"]]
    print(f"  {HEADER_RECORDS - len(unused)}/{HEADER_RECORDS} records used, "
          f"{len(unused)} never read ({len(blank)} of those all-zero)")
    for record in unused:
        note = "all-zero" if record["blank"] else header_record_pattern(record["source"])
        twins = record["duplicate_of"]
        same = f"  == used record(s) {twins}" if twins else "  (no used record holds these bytes)"
        print(f"    record {record['index']:3d}  file 0x{record['index'] * HEADER_RECORD_BYTES:04x}"
              f"  buf_b 0x{record['index'] * SHIFT_BLOCK_BYTES:04x}  {record['source'].hex()}"
              f"  {note}{same}")
    partial = [record for record in records
               if record["read"] and record["shifts_read"] < SHIFTS_PER_RECORD]
    print(f"  {len(partial)} used records are read at only some of their 16 pre-shift positions")


def report_atlas(atlas_bytes, atlas_cov):
    read_bytes = int((atlas_cov & COVERAGE_READ).sum())
    clobbered = int(((atlas_cov & (COVERAGE_WRITTEN | COVERAGE_READ)) == COVERAGE_WRITTEN).sum())
    print(f"\nAtlas (buf_c): {read_bytes}/{ATLAS_BYTES} bytes read, {ATLAS_BYTES - read_bytes} never "
          f"read, of which {clobbered} are overwritten by the game before any read")
    unread_ink = 0
    for page, start, length, group_bytes in atlas_page_slices():
        read, written, ink = page_grids(atlas_bytes, atlas_cov, start, length, group_bytes)
        note = " (planes 2,3 discarded by unpack_graphics)" if page == 1 else ""
        unread_ink += int((ink & ~read).sum())
        print(f"  page {page}: {int(read.sum()):5d}/{read.size} cells read, "
              f"{int((ink & ~read).sum()):5d} unread cells hold ink, "
              f"{int(written.sum()):4d} the game writes over{note}")
        boxes = unread_regions(read, ink)
        for box in boxes[:MAX_REGIONS_LISTED]:
            print(f"      unread region  x={box['x']:3d} y={box['y']:3d} "
                  f"{box['w']:3d}x{box['h']:3d} px  ({box['groups']} cells)")
        if len(boxes) > MAX_REGIONS_LISTED:
            print(f"      ... and {len(boxes) - MAX_REGIONS_LISTED} smaller unread blobs")
    print(f"  {unread_ink} never-read cells across all pages hold ink (the candidate unused artwork)")


def report_charset(charset):
    drawn = "".join(char for char, _offset, read in charset if read)
    never = "".join(char for char, _offset, read in charset if not read)
    print(f"\nSprite character set (draw_num via num_glyph_tbl @0x{NUM_GLYPH_TBL:05x}): "
          f"{len(drawn)}/{len(charset)} characters drawn")
    print(f"  drawn:      {drawn}")
    print(f"  never drawn: {never or '(none)'}  "
          f"-- drawable by construction; no string the drive produced contains them")


def report_static(spans, malformed, misses, fixed_pointers, fixed_misses):
    print(f"\nStatic cross-check: {len(spans)} distinct buf_c source spans in the object "
          f"records ({malformed} empty/malformed slots skipped)")
    if not misses:
        print("  every one lands in territory the dynamic union read")
    for src, users in misses:
        print(f"  0x{src:05x} never read, named by {len(users)} record(s), e.g. {users[0]}")
    print(f"Fixed source tables (buggy body, HUD variants, foreground frames, screen constants): "
          f"{len(fixed_pointers)} pointers")
    if not fixed_misses:
        print("  every one lands in territory the dynamic union read")
    for src, labels in fixed_misses:
        print(f"  0x{src:05x} never read, named by: {', '.join(sorted(set(labels)))}")


# ---------------------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None,
                        help="directory for the per-page PNGs and the raw coverage bitmap")
    parser.add_argument("--frames", type=int, default=DEFAULT_RACE_FRAMES,
                        help="rendered frames per leg drive (default %(default)s)")
    parser.add_argument("--quick", action="store_true",
                        help="short drives; enough to shake the tooling out, not to trust a verdict")
    parser.add_argument("--no-poison", action="store_true",
                        help="skip the poison proof (it re-drives every scene)")
    args = parser.parse_args()
    race_frames = QUICK_RACE_FRAMES if args.quick else args.frames

    lib = ctypes.CDLL(str(build_instrumented_library()))
    harness._lib = lib                                    # every render/bench helper calls through it
    check_layout()

    driver = Driver(lib)
    clean = Witness(rs.BUF_B, rs.BUF_C + ATLAS_BYTES)     # the main drive doubles as the clean witness
    coverage = Coverage(lib, witness=clean)
    drive_everything(driver, coverage, race_frames)

    reference = driver.staged()                           # a pristine post-unpack image to read from
    atlas_bytes = bytes(reference[rs.BUF_C:rs.BUF_C + ATLAS_BYTES])
    header_bytes = GRAPHICS_FILE.read_bytes()[:HEADER_BYTES]
    coverage_map = coverage.map.copy()
    atlas_cov = coverage_map[BUF_B_BYTES:]

    records = header_record_report(coverage_map[:BUF_B_BYTES], header_bytes)
    spans, malformed = object_record_pointers(driver)
    misses = static_cross_check(spans, atlas_cov)
    fixed_pointers = fixed_source_pointers(reference)
    fixed_misses = fixed_cross_check(fixed_pointers, atlas_cov)
    charset = character_set_report(reference, atlas_cov)

    report_scenes(coverage)
    report_header_records(coverage_map[:BUF_B_BYTES], records)
    report_atlas(atlas_bytes, atlas_cov)
    report_charset(charset)
    report_static(spans, malformed, misses, fixed_pointers, fixed_misses)
    print(f"\nTotal recorded reads across buf_b + buf_c: "
          f"{int((coverage_map & COVERAGE_READ).sum())} bytes")

    if not args.no_poison:
        never_read = ~(coverage_map & COVERAGE_READ).astype(bool)
        clean_digest = clean.finalise(never_read)
        identical = poison_verification(driver, race_frames, never_read) == clean_digest
        verdict = "PASS" if identical else "FAIL -- a never-read byte changed what the game drew"
        print(f"\nPoison proof: every scene re-driven with {int(never_read.sum())} never-read "
              f"buf_b+buf_c bytes overwritten with 0x{POISON_BYTE:02x}; {verdict}")

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        staged_leg = driver.staged({rs.A_LEG_INDEX: _word(0)})
        leg_pin = _view(staged_leg)
        driver.call("g_init_leg", leg_pin)                # fills the in-race palette at RACE_PALETTE
        del leg_pin
        palette = rs.read_palette(staged_leg, RACE_PALETTE)
        files = write_page_pngs(args.out, atlas_bytes, atlas_cov, palette)
        (args.out / "coverage.bin").write_bytes(coverage_map.tobytes())
        print(f"\nWrote {len(files)} PNGs + coverage.bin to {args.out}")


if __name__ == "__main__":
    main()
