"""Differential test for blit_road_scroll @ 0x10326 (horizontal fine-scroll of the road playfield).

Run-to-rts, no register args. Advances hscroll_pos by road_seg_head*scroll_speed (wrapped into
[0, 0x280)), then blits 20 scanlines x 20 four-plane columns from the double-wide playfield in buf_c
to the screen's road band, rotating each column pair left by the fine shift (hscroll & 0xf); once
the scroll passes 0x140 the row tail wraps to the source start. Finally the area above the band is
filled with 0xffff0000. The test stages the screen + buf_c arenas and the scroll globals, then diffs
the whole image: a sweep with zero delta pins every shift/coarse/edge case, a fuzz group exercises
the hscroll update + wrap. Poisoned.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x10326

A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_SCREEN_OFFSET = 0x18d18
A_ROAD_SEG_HEAD, A_SCROLL_SPEED, A_HSCROLL_POS, A_HSCROLL_STEP2 = 0x18cb6, 0x18cb4, 0x18cb8, 0x18cac

SCREEN = 0x8000                # visible buffer; blit writes [SCREEN, SCREEN+0x4100)
SCREEN_SPAN = 0x4100
BUF_C = 0x30000                # double-wide playfield source
BUF_C_SPAN = 0x4000            # covers wrap_base (buf_c + screen_offset) + 20 rows * 0x140 + margin


def _w(val, n=2):
    return (val & ((1 << (8 * n)) - 1)).to_bytes(n, "big")


def _pokes(seed, flip, hscroll, seg_head, speed, screen_off):
    rng = random.Random(seed)
    return {
        A_FLIP_IDX: _w(flip),
        A_PHYSBASE + flip: _w(SCREEN, 4),
        A_BUF_C: _w(BUF_C, 4),
        A_SCREEN_OFFSET: _w(screen_off),
        A_ROAD_SEG_HEAD: _w(seg_head),
        A_SCROLL_SPEED: _w(speed),
        A_HSCROLL_POS: _w(hscroll),
        A_HSCROLL_STEP2: _w(0x1234),               # nonzero so the step write is observable
        SCREEN: bytes(rng.randrange(256) for _ in range(SCREEN_SPAN)),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
    }


def _check(seed, flip, hscroll, seg_head, speed, screen_off):
    regs = {"_pokes": _pokes(seed, flip, hscroll, seg_head, speed, screen_off)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_blit_road_scroll(b), poison=True)
    assert not diffs, (f"flip={flip} hscroll={hscroll:#x} seg_head={seg_head} speed={speed} "
                       f"screen_off={screen_off:#x}\n{report(diffs[:12])}")


def test_scroll_sweep():
    # Zero delta -> h == hscroll: pins every fine shift, coarse offset, and the edge (>= 0x140) branch.
    HS = [0, 1, 0xf, 0x10, 0x1f, 0x13e, 0x13f, 0x140, 0x141, 0x150, 0x1ff, 0x27e, 0x27f]
    for flip in (0, 4):
        for off in (0, 0x1900):
            for hs in HS:
                _check(seed=hs + flip, flip=flip, hscroll=hs, seg_head=0, speed=0, screen_off=off)


def test_scroll_delta_fuzz():
    rng = random.Random(11)
    for i in range(60):
        _check(seed=1000 + i, flip=rng.choice((0, 4)),
               hscroll=rng.randrange(0x280),
               seg_head=rng.randrange(-0x40, 0x40),
               speed=rng.randrange(-8, 8),
               screen_off=rng.choice((0, 0x1900)))
