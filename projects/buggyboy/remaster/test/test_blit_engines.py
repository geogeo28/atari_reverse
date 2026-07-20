"""test_blit.py — remaster fine-x blit engine equivalence vs recreate's verified leaf blitters.

blit_objshift (colour-indexed) and blit_objshift2 (plain) are the leaf writers under the roadside-
object dispatcher: they shift a 16-pixel source column to an arbitrary pixel x so a sprite straddles
two destination columns, walking one scanline up per row. recreate's fuzz stages a flat image (noise
dst + noise src, real color_pairs) and drives the g_ engine with image addresses; here we drive the
same flat buffer through recreate's g_ entry (reference) and the remaster engine (dst == src == the
buffer) and diff the whole image — proving equivalence including the "off-edge: draw nothing" cases.

Fuzz spans every fine-x (0..15), every dispatch case (left-clip / left-edge / base / right-edge /
right-clip), colours, row counts, stride words, and both width families, sharded across xdist workers.
"""
import equiv
import pytest

# Flat-image layout mirroring recreate's objshift fuzz (clear of the program + stack guard).
DST_BASE = 0x60000
DST_LO = 0x5c000
DST_SPAN = 0x8000
SRC_BASE = 0x88000
SRC_SPAN = 0x8000                 # generous src arena covering every row's reach either direction

A_COLOR_PAIRS = equiv.A_color_pairs
COLOR_PAIRS_BYTES = 16 * 8

FUZZ_CHUNKS = 8


def _x_for(col, fine_x):
    """x decoding to aligned column `col` (signed multiple of 8) with nibble `fine_x`."""
    return ((col << 1) | (fine_x & 0xf)) & 0xffff


def _spans():
    return [(DST_LO, DST_SPAN), (SRC_BASE - SRC_SPAN // 2, SRC_SPAN), (A_COLOR_PAIRS, COLOR_PAIRS_BYTES)]


# ---- blit_objshift (colour-indexed), base_cells 1 (g_blit_objshift) and 2 (g_blit_objshift_w2) ----

def _check_objshift(lib, x, color, rows_m1, stride, base_cells, seed):
    """Differential for the colour-indexed engine. recreate reads the per-row stride via an A3
    pointer; the remaster engine takes the stride value directly. Both read color_pairs and write the
    same staged flat buffer. Returns the whole-image byte-diff count."""
    import random
    ctypes = equiv.ctypes
    ref_name = "g_blit_objshift" if base_cells == 1 else "g_blit_objshift_w2"
    stride_ptr = 0xf0000
    regs = (x & 0xffff, color & 0xffff, rows_m1 & 0xffff, DST_BASE, SRC_BASE, stride_ptr)

    base_img = equiv._flat_image()
    equiv._stage_noise(base_img, random.Random(seed), _spans() + [(stride_ptr, 2)])
    base_img[stride_ptr:stride_ptr + 2] = (stride & 0xffff).to_bytes(2, "big")

    ref = bytearray(base_img)
    fn = getattr(equiv.bench_frame.harness._lib, ref_name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
    fn.restype = None
    fn((ctypes.c_uint8 * equiv.bench_frame.IMAGE_SIZE).from_buffer(ref), *regs)

    cand = bytearray(base_img)
    buf = (ctypes.c_uint8 * equiv.bench_frame.IMAGE_SIZE).from_buffer(cand)
    base = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
    cp = ctypes.cast(ctypes.byref(buf, A_COLOR_PAIRS), ctypes.POINTER(ctypes.c_uint8))
    lib.rm_blit_objshift(base, DST_BASE, base, SRC_BASE, x & 0xffff, color & 0xffff,
                         rows_m1 & 0xffff, stride, cp, base_cells)
    return equiv._diff_over_spans(ref, cand, _spans() + [(stride_ptr, 2)])


OBJSHIFT_CASES = []
for _bc in (1, 2):
    for _fx in range(16):
        for _col in (0x40, -8, 0x98, -16, 0xa0, 0x30, 0x88, 0x90):
            OBJSHIFT_CASES.append((_bc, _fx, _col))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_blit_objshift_matches(chunk, capsys):
    lib = equiv._lib()
    bad = []
    for idx, (bc, fx, col) in enumerate(OBJSHIFT_CASES):
        if idx % FUZZ_CHUNKS != chunk:
            continue
        for color, rows_m1, stride in ((3, 3, 8), (11, 0, 0x10), (14, 5, -8 & 0xffff)):
            x = _x_for(col, fx)
            diff = _check_objshift(lib, x, color, rows_m1, stride, bc, seed=idx * 97 + color)
            if diff:
                bad.append((bc, fx, col, color, rows_m1, stride, diff))
    with capsys.disabled():
        print(f"  objshift chunk {chunk}: {len(bad)} mismatches")
    assert not bad, f"blit_objshift differs: {bad[:8]}"


# ---- blit_objshift2 (plain), width_idx 0/1/2 (base ceiling 0x88/0x90/0x98) ----

def _check_objshift2(lib, x, rows_m1, width_idx, seed):
    def remaster_call(l, buf):
        base = equiv.ctypes.cast(buf, equiv.ctypes.POINTER(equiv.ctypes.c_uint8))
        l.rm_blit_objshift2(base, DST_BASE, base, SRC_BASE, x & 0xffff, rows_m1 & 0xffff, width_idx)

    entry = {0: "g_blit_objshift2"}.get(width_idx)
    if entry:
        regs = (x & 0xffff, rows_m1 & 0xffff, DST_BASE, SRC_BASE)
        return equiv.compare_objshift(lib, entry, remaster_call, regs, _spans(), seed)
    return None   # width_idx 1/2 have no public g_ entry; covered via draw_object_list later


OBJSHIFT2_CASES = []
for _fx in range(16):
    for _col in (-32, -24, -16, -8, 0x0, 0x40, 0x80, 0x88, 0x90, 0x98, 0xa0):
        OBJSHIFT2_CASES.append((_fx, _col))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_blit_objshift2_matches(chunk, capsys):
    lib = equiv._lib()
    bad = []
    for idx, (fx, col) in enumerate(OBJSHIFT2_CASES):
        if idx % FUZZ_CHUNKS != chunk:
            continue
        for rows_m1 in (0, 3, 0x2a):
            x = _x_for(col, fx)
            diff = _check_objshift2(lib, x, rows_m1, 0, seed=idx * 131 + rows_m1)
            if diff:
                bad.append((fx, col, rows_m1, diff))
    with capsys.disabled():
        print(f"  objshift2 chunk {chunk}: {len(bad)} mismatches")
    assert not bad, f"blit_objshift2 differs: {bad[:8]}"


# ---- objsprite engine (the third fine-x blitter), width_idx 0/1/2/3 = g_objsprite_t4/w88/t2/t1 ----

# g_objsprite_t<N>(image, x, rows_m1, dst, src) — bare width prologue, fixed per-row rewind.
OBJSPRITE_ENTRY = {0: "g_objsprite_t4", 1: "g_objsprite_w88", 2: "g_objsprite_t2", 3: "g_objsprite_t1"}


def _check_objsprite(lib, x, rows_m1, width_idx, seed):
    ctypes = equiv.ctypes
    regs = (x & 0xffff, rows_m1 & 0xffff, DST_BASE, SRC_BASE)

    def remaster_call(l, buf):
        base = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
        l.rm_objsprite(base, DST_BASE, base, SRC_BASE, x & 0xffff, rows_m1 & 0xffff, width_idx)

    return equiv.compare_objshift(lib, OBJSPRITE_ENTRY[width_idx], remaster_call, regs, _spans(), seed)


OBJSPRITE_CASES = []
for _wi in (0, 1, 2, 3):
    for _fx in range(16):
        # cover the LEFT clip ladder, BASE span, WIDE clip ladder, and off-edge both sides.
        for _col in (-32, -24, -16, -8, 0x0, 0x40, 0x78, 0x80, 0x88, 0x90, 0x98, 0xa0):
            OBJSPRITE_CASES.append((_wi, _fx, _col))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_objsprite_matches(chunk, capsys):
    lib = equiv._lib()
    bad = []
    for idx, (wi, fx, col) in enumerate(OBJSPRITE_CASES):
        if idx % FUZZ_CHUNKS != chunk:
            continue
        for rows_m1 in (0, 4, 0x1f):
            x = _x_for(col, fx)
            diff = _check_objsprite(lib, x, rows_m1, wi, seed=idx * 149 + rows_m1)
            if diff:
                bad.append((wi, fx, col, rows_m1, diff))
    with capsys.disabled():
        print(f"  objsprite chunk {chunk}: {len(bad)} mismatches")
    assert not bad, f"objsprite differs: {bad[:8]}"
