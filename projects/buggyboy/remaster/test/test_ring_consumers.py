"""test_ring_consumers.py — pin the ring's OTHER consumers' address arithmetic.

The original aliases four more subsystems onto the ring's flat row grid: the object-list
dispatcher's two flag streams, draw_game_objects' sprite-slot count, draw_ground's per-band
markers, and the buggy/foreground sprite gates. The ring's VALUES over time are already pinned
band-by-band by the leg drives (test_course_ring / test_leg_drive); what THESE tests pin is the
MAPPING — that each src/course.c helper reads exactly the bytes the original's consumer reads —
by comparing every helper against the raw image bytes at the aliased addresses, over real
captured states (5 legs x 3 warmup depths).

Two stated gaps, so nobody reads more coverage out of this file than is in it:
- The game_main.c WIRING (the ring_st refresh sites, the row-1/row-12 flag-stream pointers, the
  restart reset) has no host test — `make test` never runs game_main.c. It is verified on-target: the
  golden frame-0 compare plus autodrive runs (see PORTING.md).
- The fixed pass consumes ring bands 12/13's slot words, which the leg drives verify only by
  marker (the still-unported horizon-event dispatch clears bytes there) — the mapping is pinned
  here, but those bands' VALUES stay dispatch-unfaithful until the dispatch is ported.
"""
import ctypes
import re

import adapter
import equiv
import pytest

RING_BYTES = adapter.RM_RING_ROWS * adapter.RING_ROW_BYTES
SPRITE_COUNT_CAP = 11          # mirrors RM_RING_SPRITE_ROWS (pinned below against game.h)

CASES = [(leg, warmup) for leg in range(5) for warmup in (30, 60, 90)]


def _bind(lib):
    lib.rm_ring_store_st.argtypes = [ctypes.POINTER(adapter.CourseRing), ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_ring_store_st.restype = None
    lib.rm_ring_sprite_count.argtypes = [ctypes.POINTER(adapter.CourseRing)]
    lib.rm_ring_sprite_count.restype = ctypes.c_uint16
    lib.rm_ring_ground_markers.argtypes = [ctypes.POINTER(adapter.CourseRing), ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_ring_ground_markers.restype = None
    lib.rm_ring_buggy_gate.argtypes = [ctypes.POINTER(adapter.CourseRing)]
    lib.rm_ring_buggy_gate.restype = ctypes.c_uint8
    lib.rm_ring_fg_gate.argtypes = [ctypes.POINTER(adapter.CourseRing)]
    lib.rm_ring_fg_gate.restype = ctypes.c_int8


def test_sprite_count_cap_matches_the_c():
    """The cap is duplicated here to keep the reference walk independent; pin it to game.h."""
    text = (adapter.REMASTER / "include/game.h").read_text()
    found = re.search(r"^#define\s+RM_RING_SPRITE_ROWS\s+(\d+)\b", text, re.M)
    assert found, "RM_RING_SPRITE_ROWS moved out of game.h"
    assert int(found.group(1)) == SPRITE_COUNT_CAP


def test_sprite_count_walk_logic():
    """The captured cases only ever sample counts 0 and 11 (the shipped course data rarely parks a
    negative marker inside the window), so the walk's break logic needs directed cases: force one
    negative marker at each depth of a REAL captured ring and pin the count. Synthetic input is
    fair here — it pins the walk algorithm itself, not a claim about what the course data reaches
    (which the parametrized cases report honestly)."""
    lib = equiv._lib()
    _bind(lib)
    image = equiv.road_background(leg=0, warmup=30)

    for stop_row in range(1, SPRITE_COUNT_CAP + 1):
        ring = adapter.course_ring(image)
        for row in range(SPRITE_COUNT_CAP + 1):
            ring.row[row].marker &= 0x7fff          # open every row in the window...
        ring.row[stop_row].marker |= 0x8000          # ...then close exactly one
        count = lib.rm_ring_sprite_count(ctypes.byref(ring))
        assert count == stop_row - 1, f"negative marker at row {stop_row}: count {count}"

    ring = adapter.course_ring(image)
    ring.row[0].marker |= 0x8000                     # row 0 gates the whole walk
    assert lib.rm_ring_sprite_count(ctypes.byref(ring)) == 0


def test_gate_suppress_bit_reachable():
    """At least one sampled case must carry the bit-7 suppress flag, or the gate mapping would be
    pinned only ever against zero bytes and PORTING.md's 'live SUPPRESS case' claim could go
    silently false when the captures change."""
    lib = equiv._lib()
    _bind(lib)
    for leg, warmup in CASES:
        image = equiv.road_background(leg=leg, warmup=warmup)
        ring = adapter.course_ring(image)
        gates = lib.rm_ring_buggy_gate(ctypes.byref(ring)) | (lib.rm_ring_fg_gate(ctypes.byref(ring)) & 0xff)
        if gates & 0x80:
            return
    pytest.fail("no sampled case carries the suppress bit — extend CASES until one does")


@pytest.mark.parametrize("leg,warmup", CASES)
def test_ring_consumer_views_match_the_image(leg, warmup, capsys):
    lib = equiv._lib()
    _bind(lib)
    image = equiv.road_background(leg=leg, warmup=warmup)
    ring = adapter.course_ring(image)

    # 1. The serialized ST mirror is byte-identical to the original's row grid — this is what the
    #    object-list dispatcher's flag streams walk, so it pins the whole layout (slot order,
    #    marker offset, row stride, big-endianness).
    mirror = (ctypes.c_uint8 * RING_BYTES)()
    lib.rm_ring_store_st(ctypes.byref(ring), mirror)
    grid = bytes(image[adapter.A_ring_base:adapter.A_ring_base + RING_BYTES])
    assert bytes(mirror) == grid, "serialized ring != the original's row grid"

    # 2. The sprite-slot count equals the original's walk down the grid's marker column
    #    (row 0 gates, then consecutive non-negative markers over rows 1.., capped).
    def marker(row):
        base = adapter.A_sprite_list_base + row * adapter.RING_ROW_BYTES
        value = (image[base] << 8) | image[base + 1]
        return value - 0x10000 if value & 0x8000 else value

    expect = 0
    if marker(0) >= 0:
        while expect < SPRITE_COUNT_CAP and marker(expect + 1) >= 0:
            expect += 1
    count = lib.rm_ring_sprite_count(ctypes.byref(ring))
    assert count == expect, f"sprite count {count} != the image walk's {expect}"

    # 3. The ground markers equal the descriptor bytes draw_ground reads (descriptor + 3, which is
    #    ring row byte 0xf — slot 7's low byte; PORTING.md's earlier "slot 6" note was off by one).
    markers = (ctypes.c_uint8 * adapter.GROUND_SCAN_ENTRIES)()
    lib.rm_ring_ground_markers(ctypes.byref(ring), markers)
    ref_markers = bytes(
        image[adapter.A_ground_scan_tbl + i * adapter.GROUND_SCAN_STRIDE + adapter.GROUND_MARKER_OFF]
        for i in range(adapter.GROUND_SCAN_ENTRIES))
    assert bytes(markers) == ref_markers, "ground markers != the descriptor bytes"

    # 4. The sprite gates equal the two aliased bytes (row 11's marker, high/low).
    buggy_gate = lib.rm_ring_buggy_gate(ctypes.byref(ring))
    fg_gate = lib.rm_ring_fg_gate(ctypes.byref(ring)) & 0xff
    assert buggy_gate == image[adapter.A_sp_buggy_gate], "buggy_gate != image byte"
    assert fg_gate == image[adapter.A_sp_fg_gate], "fg_gate != image byte"

    with capsys.disabled():
        suppress = (buggy_gate | fg_gate) & 0x80
        print(f"  leg={leg} warmup={warmup}: sprite_count={count} "
              f"gates={buggy_gate:#04x}/{fg_gate:#04x}{' SUPPRESS' if suppress else ''}")
