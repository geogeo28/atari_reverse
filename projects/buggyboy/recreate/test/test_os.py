"""Differential tests for the OS-wrapper functions — validates the trap-dispatch layer.

These wrappers enter TOS via `trap`; the oracle services the trap deterministically (os.h)
and must reach the wrapper's rts without crashing or writing the image. A green case proves
the trap layer works end to end (previously any trap jumped to the zeroed vector page).
"""
import ctypes

import pytest

import harness            # inserts oracle/ onto sys.path
import emu
from harness import differential, report

harness._lib.g_xbios_setscreen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_xbios_setscreen.restype = None
harness._lib.g_xbios_setpalette.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_xbios_setpalette.restype = None
harness._lib.g_set_rez.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_set_rez.restype = None
harness._lib.g_gem_aes.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_gem_aes.restype = None
harness._lib.g_gem_vdi.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_gem_vdi.restype = None
harness._lib.g_start.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_start.restype = None
harness._lib.g_main.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_main.restype = None
harness._lib.g_load_graphics.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_load_graphics.restype = None

PALETTE_PTR = 0x1e000             # scratch (below the stack guard) for the 16-word palette

CONTRL = 0x19a58                  # contrl[0]: the AES/VDI opcode (shared block; = aesvdi_contrl)
INTOUT = 0x19c8c                  # intout[0]: where AES/VDI results land (shared block)

START_MAIN_CALL = 0x100d4         # `bsr main`; _start is verified up to here (main never returns)
START_STACK_BAND = (0x1b000, 0x1b044)   # _start moves A7 to 0x1b044; its stack lives just below


def test_xbios_setpalette():
    # A0 -> palette words; the XBIOS call copies them to hardware, so no image effect.
    pokes = {PALETTE_PTR: bytes(range(32))}
    regs = {"a0": PALETTE_PTR, "_pokes": pokes}
    diffs, _ = differential(0x12eb0, regs,
                            lambda lib, buf: lib.g_xbios_setpalette(buf, PALETTE_PTR))
    assert not diffs, report(diffs[:12])


def test_xbios_setscreen():
    # Reads physbase_tbl[0] and calls Setscreen(base, base, -1) — shifter/TOS state only.
    # The value is arbitrary here: the modeled Setscreen ignores it (no image effect).
    pokes = {0x18bf4: (0x9240).to_bytes(4, "big")}   # physbase_tbl[0]
    regs = {"_pokes": pokes}
    diffs, _ = differential(0x12226, regs, lambda lib, buf: lib.g_xbios_setscreen(buf))
    assert not diffs, report(diffs[:12])


def test_set_rez():
    # Stores D0.b to a config global then calls XBIOS Ikbdws (0x19), a hardware serial write.
    # Byte-exact over varied D0 confirms the reconstruction matches the modeled call.
    for mode in (0x00, 0x12, 0x15, 0x1a, 0xff, 0x142):   # high byte must be ignored (move.b)
        diffs, _ = differential(0x120f8, {"d0": mode},
                                lambda lib, buf, m=mode: lib.g_set_rez(buf, m))
        assert not diffs, f"mode={mode:#x}\n{report(diffs[:12])}"


def _poke_contrl(opcode):
    """Set contrl[0] (the AES/VDI opcode) — the game normally does this before the trap."""
    return {CONTRL: opcode.to_bytes(2, "big")}


def test_gem_aes_appl_init():
    # appl_init (opcode 10) writes ap_id (=0) to intout[0]; a clean trap #2 with no other effect.
    diffs, _ = differential(0x100dc, {"_pokes": _poke_contrl(10)},
                            lambda lib, buf: lib.g_gem_aes(buf))
    assert not diffs, report(diffs[:12])


def test_gem_aes_graf_handle():
    # graf_handle (opcode 77) returns the physical VDI handle + font cell sizes in intout[0..4].
    pokes = _poke_contrl(77)
    diffs, _ = differential(0x100dc, {"_pokes": pokes}, lambda lib, buf: lib.g_gem_aes(buf))
    assert not diffs, report(diffs[:12])
    # os_gem_trap writes the image directly (not via the logged m68k path), so read the modeled
    # values back from the oracle's final image to pin them against an os.h regression.
    mem, _, _ = emu.run(harness.make_image(pokes), 0x100dc)
    assert int.from_bytes(mem[INTOUT:INTOUT + 2], "big") == 1, "intout[0] should be VDI handle 1"
    assert int.from_bytes(mem[INTOUT + 2:INTOUT + 4], "big") == 8, "intout[1] should be 8px cell width"


def test_gem_vdi_v_opnvwk():
    # v_opnvwk (opcode 100) fills work_out; we model the two determinate low-res fields:
    # intout[0] = max x = 319, intout[1] = max y = 199.
    pokes = _poke_contrl(100)
    diffs, _ = differential(0x100ea, {"_pokes": pokes}, lambda lib, buf: lib.g_gem_vdi(buf))
    assert not diffs, report(diffs[:12])
    mem, _, _ = emu.run(harness.make_image(pokes), 0x100ea)
    assert int.from_bytes(mem[INTOUT:INTOUT + 2], "big") == 319, "work_out[0] should be max x 319"
    assert int.from_bytes(mem[INTOUT + 2:INTOUT + 4], "big") == 199, "work_out[1] should be max y 199"


MAIN_MALLOC_CKPT = 0x10144        # after Malloc + the five buffer pointers, before Supexec
OS_HEAP_BASE = 0x20000            # mirror of os.h; the modeled Malloc returns this block base


def test_main_malloc_init():
    # main Mallocs its 0x5ee08 work block, rounds it to mem_base, and lays out five buffer
    # pointers. Verified at the checkpoint before Supexec (main never returns).
    diffs, _ = differential(0x10100, {}, lambda lib, buf: lib.g_main(buf), stop_pc=MAIN_MALLOC_CKPT)
    assert not diffs, report(diffs[:12])
    mem, _, _ = emu.run(harness.make_image(), 0x10100, stop_pc=MAIN_MALLOC_CKPT)
    mem_base = (OS_HEAP_BASE + 0x100) & ~0xff
    assert int.from_bytes(mem[0x18bfc:0x18c00], "big") == mem_base, "mem_base"
    assert int.from_bytes(mem[0x18bf8:0x18bfc], "big") == mem_base + 0x57000, "buf_aux"
    assert int.from_bytes(mem[0x18c08:0x18c0c], "big") == mem_base + 0x1c660, "buf_c"


def test_start_gem_init():
    # _start up to `bsr main`: Mshrink (no image effect) + AES appl_init / graf_handle +
    # VDI v_opnvwk setup. Diffed at the checkpoint because main is the infinite game loop and
    # never returns; _start's relocated stack band (just below 0x1b044) is excluded.
    diffs, _ = differential(0x10000, {}, lambda lib, buf: lib.g_start(buf),
                            stop_pc=START_MAIN_CALL, exclude=[START_STACK_BAND])
    assert not diffs, report(diffs[:12])
    # the graf_handle handle must propagate into the VDI handle global.
    mem, _, _ = emu.run(harness.make_image(), 0x10000, stop_pc=START_MAIN_CALL)
    assert int.from_bytes(mem[0x1a0a0:0x1a0a2], "big") == 1, "vdi_handle should be phys handle 1"


def test_exclude_band_guards():
    """A diff exclude band must be provably stack scratch. The harness refuses a band that lies
    entirely below the deepest stack pointer (A) or covers a named global below the stack (D), but
    allows a named global reused as scratch while the stack sits over it (trace_pc during _start)."""
    STACK = 0x1b032                                          # a representative deepest-A7 for _start
    with pytest.raises(AssertionError, match="deepest stack pointer"):
        harness._vet_exclude_bands([(0x400, 0x440)], STACK)  # low vector page, never stack
    with pytest.raises(AssertionError, match="named global"):
        harness._vet_exclude_bands([(0x18c34, 0x1b044)], STACK)  # spans game_over_flag (below stack)
    harness._vet_exclude_bands([(0x1b000, 0x1b044)], STACK)  # trace_pc@0x1b040 is stack-reused: allowed


def test_supexec_nested():
    """Supexec must run the passed routine in place and return its D0 to the caller."""
    stub = bytes.fromhex("487900010020"  # pea 0x10020 (routine)
                         "3f3c0026"       # move.w #0x26,-(sp)  (Supexec)
                         "4e4e"           # trap #14
                         "5c8f"           # addq.l #6,a7
                         "4e75")          # rts
    routine = bytes.fromhex("23fcdeadbeef0000c000"  # move.l #0xdeadbeef,(0xc000).l
                            "303c1234"              # move.w #0x1234,d0
                            "4e75")                 # rts
    img = harness.make_image({0x10000: stub, 0x10020: routine})
    mem, _, out = emu.run(img, 0x10000)
    assert mem[0xc000:0xc004] == bytes.fromhex("deadbeef"), "Supexec routine did not execute"
    assert out["d0"] & 0xffff == 0x1234, "Supexec did not return the routine's result"


def test_fread_file_model():
    """Fopen/Fread/Fclose over a staged file: the bytes land in the buffer and the handle +
    (short) byte count come back. Also pins harness.stage_files against os.h's table layout —
    a mismatch makes os_fopen miss the entry and emu.run raise (unmodeled)."""
    data = bytes(range(16))
    stage_pokes, handles = harness.stage_files([("TEST.DAT", data)])
    assert handles["TEST.DAT"] == 6
    # Stub @0x10000: Fopen("TEST.DAT",0) -> d6; save handle; Fread(d6, 0x20, 0x30000); save
    # bytes-read; Fclose(d6); rts. Name at 0x10044 (just past the 0x44-byte stub). Buf @0x30000,
    # bytes-read word @0x30020, handle word @0x30022 (free region, below the program).
    stub = bytes.fromhex(
        "3f3c0000"          # move.w #0,-(a7)          ; mode
        "2f3c00010044"      # move.l #0x10044,-(a7)    ; &name
        "3f3c003d"          # move.w #0x3d,-(a7)       ; Fopen
        "4e41" "508f"       # trap #1 ; addq.l #8,a7
        "3c00"              # move.w d0,d6             ; save handle
        "33c600030022"      # move.w d6,(0x30022).l    ; store handle
        "2f3c00030000"      # move.l #0x30000,-(a7)    ; &buf
        "2f3c00000020"      # move.l #0x20,-(a7)       ; count 32 (> size 16 -> short read)
        "3f06"              # move.w d6,-(a7)          ; handle
        "3f3c003f"          # move.w #0x3f,-(a7)       ; Fread
        "4e41" "defc000c"   # trap #1 ; adda.w #0xc,a7
        "33c000030020"      # move.w d0,(0x30020).l    ; store bytes-read
        "3f06"              # move.w d6,-(a7)          ; handle
        "3f3c003e"          # move.w #0x3e,-(a7)       ; Fclose
        "4e41" "588f"       # trap #1 ; addq.l #4,a7
        "4e75")             # rts
    pokes = {0x10000: stub, 0x10044: b"TEST.DAT\0", **stage_pokes}
    mem, _, _ = emu.run(harness.make_image(pokes), 0x10000)
    assert mem[0x30000:0x30010] == data, "Fread should copy the staged bytes into the buffer"
    assert mem[0x30010:0x30020] == bytes(16), "Fread must not write past the file's actual size"
    assert int.from_bytes(mem[0x30020:0x30022], "big") == 16, "Fread should return the byte count"
    assert int.from_bytes(mem[0x30022:0x30024], "big") == 6, "Fopen should return handle 6"


# load_graphics globals (see names.txt / addrs.h) and the checkpoint before bsr unpack_graphics.
A_MEM_BASE, A_BUF_C = 0x18bfc, 0x18c08
GFX_LOAD_OFFSET = 0xc350
LOAD_GRAPHICS_CKPT = 0x121f2
COURSES_DEST, GRAPHICS_BASE = 0x20000, 0x40000   # in-image scratch dests (below the FS regions)


def test_load_graphics():
    """load_graphics reads COURSES.DAT + GRAPHICS.GRA into their buffers. Stage the real files,
    point mem_base/buf_c at scratch buffers, and diff at the checkpoint before unpack_graphics."""
    bin_dir = harness.PRG.parent
    courses = (bin_dir / "COURSES.DAT").read_bytes()
    graphics = (bin_dir / "GRAPHICS.GRA").read_bytes()
    stage_pokes, _ = harness.stage_files([("COURSES.DAT", courses), ("GRAPHICS.GRA", graphics)])
    pokes = {A_MEM_BASE: COURSES_DEST.to_bytes(4, "big"),
             A_BUF_C: GRAPHICS_BASE.to_bytes(4, "big"),
             **stage_pokes}
    diffs, _ = differential(0x12166, {"_pokes": pokes},
                            lambda lib, buf: lib.g_load_graphics(buf), stop_pc=LOAD_GRAPHICS_CKPT)
    assert not diffs, report(diffs[:12])
    # both files must have landed byte-exact at their targets.
    mem, _, _ = emu.run(harness.make_image(pokes), 0x12166, stop_pc=LOAD_GRAPHICS_CKPT)
    assert mem[COURSES_DEST:COURSES_DEST + len(courses)] == courses, "COURSES.DAT mis-loaded"
    gfx = GRAPHICS_BASE + GFX_LOAD_OFFSET
    assert mem[gfx:gfx + len(graphics)] == graphics, "GRAPHICS.GRA mis-loaded"


# ---------------------------------------------------------------------------
# Shim-contract tests — exercise the deterministic TOS trap model (shim.c + os.h) directly at
# its edges: bump-allocation, the file cursor/EOF, and the handle lifecycle. The wrapper tests
# above only touch the happy path each reconstruction needs; these pin the semantics *both*
# sides rely on, so a regression fails here instead of silently inside a caller's diff. Each
# drives a tiny hand-assembled 68k stub through the oracle (emu.run) and asserts on the final
# image — or, for a contract violation, that emu.run rejects the run rather than trusting it.
# ---------------------------------------------------------------------------

# GEMDOS trap #1 selectors used by the stubs (see docs/tos-os-calls.md).
GEMDOS_MALLOC, GEMDOS_FOPEN, GEMDOS_FREAD, GEMDOS_FCLOSE = 0x48, 0x3d, 0x3f, 0x3e

STUB_ENTRY = 0x10000              # stubs run from here on a throwaway image copy
SCRATCH = 0x30000                 # free image page (above the program, below the heap/FS regions)
NAME_PTR = SCRATCH + 0x300        # staged filename string lives here (clear of the read buffers)

# 68k byte-emitters — one place for the encodings instead of hand-hexing each stub. Verified
# against the encodings already proven green in test_fread_file_model / test_supexec_nested.
def _push_l(imm):  return b"\x2f\x3c" + imm.to_bytes(4, "big")   # move.l #imm,-(a7)
def _push_w(imm):  return b"\x3f\x3c" + imm.to_bytes(2, "big")   # move.w #imm,-(a7)
def _push_d6():    return b"\x3f\x06"                            # move.w d6,-(a7)   (saved handle)
def _pop(n):       return b"\xde\xfc" + n.to_bytes(2, "big")     # adda.w #n,a7      (stack cleanup)
def _trap1():      return b"\x4e\x41"                            # trap #1
def _st_l(addr):   return b"\x23\xc0" + addr.to_bytes(4, "big")  # move.l d0,(addr).l
def _d0_to_d6():   return b"\x3c\x00"                            # move.w d0,d6      (save handle)
def _rts():        return b"\x4e\x75"

# Argument byte-counts to pop after each trap: pushed args + the 2-byte selector word.
_MALLOC_POP, _FOPEN_POP, _FREAD_POP, _FCLOSE_POP = 6, 8, 12, 4


def _malloc(amount):
    return _push_l(amount) + _push_w(GEMDOS_MALLOC) + _trap1() + _pop(_MALLOC_POP)


def _fopen(name_ptr, mode=0):
    return (_push_w(mode) + _push_l(name_ptr) + _push_w(GEMDOS_FOPEN)
            + _trap1() + _pop(_FOPEN_POP) + _d0_to_d6())


def _fread(count, buf):
    return (_push_l(buf) + _push_l(count) + _push_d6() + _push_w(GEMDOS_FREAD)
            + _trap1() + _pop(_FREAD_POP))


def _fclose():
    return _push_d6() + _push_w(GEMDOS_FCLOSE) + _trap1() + _pop(_FCLOSE_POP)


def _run_stub(code, extra_pokes=None):
    return emu.run(harness.make_image({STUB_ENTRY: code, **(extra_pokes or {})}), STUB_ENTRY)


def test_malloc_bump_and_rounding():
    """Malloc bump-allocates from OS_HEAP_BASE, and rounds an odd request up to an even size,
    so the next block starts on the rounded boundary (shim.c: g_heap += (n + 1) & ~1)."""
    odd = 0x101                                        # odd -> the block is rounded to 0x102
    code = (_malloc(odd) + _st_l(SCRATCH)              # base1
            + _malloc(0x10) + _st_l(SCRATCH + 4)       # base2
            + _rts())
    mem, _, _ = _run_stub(code)
    base1 = int.from_bytes(mem[SCRATCH:SCRATCH + 4], "big")
    base2 = int.from_bytes(mem[SCRATCH + 4:SCRATCH + 8], "big")
    assert base1 == OS_HEAP_BASE, "first Malloc returns the heap base"
    assert base2 == OS_HEAP_BASE + ((odd + 1) & ~1), "next block starts past the rounded first block"


def test_fread_sequential_cursor_and_eof():
    """Sequential Freads advance a per-file cursor; the read crossing the last byte returns the
    partial remainder, and the read after EOF returns 0 — the file-cursor contract in os.h."""
    data = bytes(range(16))
    stage, handles = harness.stage_files([("SEQ.DAT", data)])
    assert handles["SEQ.DAT"] == 6
    b0, b1, b2, b3 = SCRATCH, SCRATCH + 0x10, SCRATCH + 0x20, SCRATCH + 0x30
    n0, n1, n2, n3 = SCRATCH + 0x100, SCRATCH + 0x104, SCRATCH + 0x108, SCRATCH + 0x10c
    code = (_fopen(NAME_PTR)
            + _fread(5, b0) + _st_l(n0)                # 5 bytes,  cursor 0 -> 5
            + _fread(5, b1) + _st_l(n1)                # 5 bytes,  cursor 5 -> 10
            + _fread(100, b2) + _st_l(n2)              # 6 remain, cursor 10 -> 16
            + _fread(100, b3) + _st_l(n3)              # EOF -> 0
            + _fclose() + _rts())
    mem, _, _ = _run_stub(code, {NAME_PTR: b"SEQ.DAT\0", **stage})
    assert mem[b0:b0 + 5] == data[0:5]
    assert mem[b1:b1 + 5] == data[5:10]
    assert mem[b2:b2 + 6] == data[10:16]
    read = lambda a: int.from_bytes(mem[a:a + 4], "big")
    assert (read(n0), read(n1), read(n2), read(n3)) == (5, 5, 6, 0)
    assert mem[b2 + 6:b2 + 0x10] == bytes(0x0a), "Fread must not write past the partial count"
    assert mem[b3:b3 + 0x10] == bytes(0x10), "the post-EOF read writes nothing"


def test_fopen_reopen_resets_cursor():
    """Closing and reopening a staged file rewinds its cursor: the second session reads from
    byte 0 again (os_fopen resets the cursor to 0)."""
    data = bytes(range(16))
    stage, _ = harness.stage_files([("RE.DAT", data)])
    first, second = SCRATCH, SCRATCH + 0x10
    code = (_fopen(NAME_PTR) + _fread(4, first) + _fclose()
            + _fopen(NAME_PTR) + _fread(4, second) + _fclose() + _rts())
    mem, _, _ = _run_stub(code, {NAME_PTR: b"RE.DAT\0", **stage})
    assert mem[first:first + 4] == data[0:4]
    assert mem[second:second + 4] == data[0:4], "reopen should rewind to the start"


def test_fread_on_closed_handle_is_rejected():
    """Reading a closed handle is not silently served: os_fread returns -1, the shim counts the
    call unmodeled, and emu.run refuses to trust the run — so a caller can't be falsely verified."""
    data = bytes(range(16))
    stage, _ = harness.stage_files([("CL.DAT", data)])
    code = _fopen(NAME_PTR) + _fclose() + _fread(4, SCRATCH) + _rts()
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run_stub(code, {NAME_PTR: b"CL.DAT\0", **stage})


def test_fopen_missing_file_is_rejected():
    """An unstaged filename can never be falsely verified: os_fopen returns -1, which the shim
    treats as unmodeled and emu.run rejects (os.h: 'a loader reading a file we didn't stage')."""
    code = _fopen(NAME_PTR) + _rts()
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run_stub(code, {NAME_PTR: b"NOPE.DAT\0"})