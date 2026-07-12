"""Differential tests for the OS-wrapper functions — validates the trap-dispatch layer.

These wrappers enter TOS via `trap`; the oracle services the trap deterministically (os.h)
and must reach the wrapper's rts without crashing or writing the image. A green case proves
the trap layer works end to end (previously any trap jumped to the zeroed vector page).
"""
import ctypes

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