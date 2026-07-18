#!/usr/bin/env python3
"""Regenerate docs/assets/ straight from the C reconstruction.

  * screens/sprites (PNG) — the verified g_unpack_graphics + g_draw_* render into an ST framebuffer,
    decoded to RGB with the game's own palette (via recreate/render/render_screen.py, C-driven).
  * palettes (PNG)        — the 16-colour ST palettes read from the image, as swatch strips.
  * audio (WAV)           — g_INITTUNE / g_INITFX seed the driver, then g_REFRESH is stepped per 50 Hz
    frame; the PSG (reg,val) writes it emits feed the YM2149 synth (recreate/sound/ym2149.py).

Also writes assets/manifest.json mapping every media file to its category, caption, and the
reconstruction functions that produce/consume it (consumed by gen_graph.py). Re-run:
    python3 gen_assets.py
"""
import ctypes
import json
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RECREATE = HERE / "recreate"
sys.path.insert(0, str(RECREATE / "render"))          # render_screen (adds oracle/test/tools paths)
sys.path.insert(0, str(RECREATE / "sound"))           # ym2149
sys.path.insert(0, str(HERE.parents[1] / "tools"))    # extract_graphics (RLE decoder)
import render_screen as rs                             # noqa: E402  loads libbuggyboy.so via harness
import harness                                         # noqa: E402
import ym2149                                          # noqa: E402
import extract_graphics as xg                          # noqa: E402  RLE decode + planar->indices
from loader import load_image                          # noqa: E402

LIB = harness._lib
PRG = HERE / "bin" / "BUGGYBOY.PRG"
ASSETS = HERE / "docs" / "assets"


def _w(v):
    return (v & 0xffff).to_bytes(2, "big")


A_RACE_PAL = 0x17FA2       # per-leg in-race scenery/car palette; populated by g_init_leg (verified


def _staged_leg(leg, extra=None):
    """Fresh staged image with graphics unpacked AND g_init_leg run for `leg` — so the object
    records and the per-leg race palette @0x17fa2 are populated. Returns (image, buf)."""
    st = {rs.A_LEG_INDEX: leg.to_bytes(2, "big")}
    if extra:
        st.update(extra)
    image, buf = rs._prepared_image(st)
    LIB.g_init_leg.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    LIB.g_init_leg.restype = None
    LIB.g_init_leg(buf)
    return image, buf


def _leg_pal(image, black_bg=True):
    pal = rs.read_palette(image, A_RACE_PAL)
    if black_bg:
        pal[0] = (0, 0, 0)                             # sprite/scenery bg -> transparent black
    return pal

# ---- audio: drive the reconstructed 50 Hz sound driver ----
REFRESH = 0x1B086
MZFLAG, FXFLAG = 0x1B07A, 0x1B07B
DRIVER_LO, DRIVER_HI = 0x1B030, 0x1B700    # state block + 3 voice records (loop/stop fingerprint)
PSG_CAP = 256
AUDIO_MAX_FRAMES = 400                     # ~8 s @ 50 Hz cap so looping tracks stay a short preview

# reconstruction functions that make up the sound path (for the manifest)
FN_REFRESH, FN_INITTUNE, FN_INITFX = "0x1b086", "0x1b59c", "0x1b560"
FN_VOICE, FN_CMD = "0x1b2ec", "0x1b3be"
FN_PLAY_TUNE, FN_MARKER = "0x11c7a", "0x11cb2"


def _bind_sound_api():
    u8 = ctypes.POINTER(ctypes.c_uint8)
    for nm in ("g_INITTUNE", "g_INITFX"):
        getattr(LIB, nm).argtypes = [u8, ctypes.c_uint32]
        getattr(LIB, nm).restype = None
    LIB.g_REFRESH.argtypes = [u8, u8, u8, ctypes.c_uint32]
    LIB.g_REFRESH.restype = ctypes.c_uint32


def capture(kind, sound_id):
    """Seed the driver via the C INITTUNE/INITFX, then step g_REFRESH, capturing one loop / the
    natural end. Returns (per-frame 16-register snapshots, retrigger flags)."""
    barr = bytearray(load_image(PRG))
    buf = (ctypes.c_uint8 * len(barr)).from_buffer(barr)
    if kind == "tune":
        LIB.g_INITTUNE(buf, sound_id); flag = MZFLAG
    else:
        LIB.g_INITFX(buf, sound_id); flag = FXFLAG
    preg, pval = (ctypes.c_uint8 * PSG_CAP)(), (ctypes.c_uint8 * PSG_CAP)()
    regs, snaps, retrigs, seen = [0] * 16, [], [], {}
    for f in range(AUDIO_MAX_FRAMES):
        n = LIB.g_REFRESH(buf, preg, pval, PSG_CAP)
        state = bytes(bytearray(buf[DRIVER_LO:DRIVER_HI]))
        if state in seen:                              # frame repeated -> stopped (p=1) or looped
            break
        seen[state] = f
        writes = [(preg[i], pval[i]) for i in range(n)]
        for reg, val in writes:
            if reg < 16:
                regs[reg] = val
        snaps.append(list(regs))
        retrigs.append(any(reg == 13 for reg, _ in writes))
        if buf[flag] == 0:                             # driver self-terminated
            break
    return snaps, retrigs


def render_audio(manifest):
    outdir = ASSETS / "audio"
    outdir.mkdir(parents=True, exist_ok=True)
    for kind, ids in (("tune", range(10)), ("fx", range(9))):
        base_fns = ([FN_REFRESH, FN_INITTUNE, FN_VOICE, FN_CMD, FN_PLAY_TUNE] if kind == "tune"
                    else [FN_REFRESH, FN_INITFX, FN_CMD, FN_MARKER])
        for sid in ids:
            snaps, retrigs = capture(kind, sid)
            if not snaps:
                continue
            samples = ym2149.render(snaps, retrigs)
            if np.abs(samples).max() < 1e-3:           # normalised silence -> nothing to hear
                continue
            path = outdir / f"{kind}_{sid:02d}.wav"
            pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(ym2149.RATE)
                w.writeframes(pcm.tobytes())
            manifest.append({"file": f"audio/{path.name}", "kind": "audio", "cat": kind,
                             "caption": "%s %d — %.1fs (YM2149, C driver)" % (kind, sid, len(snaps) / 50.0),
                             "functions": base_fns, "assetId": "snd_cmd_table"})
            print("  wrote", path.relative_to(ASSETS))


# ---- graphics: C-driven scene renders (render_screen.py) ----
def _emit(sub, name, image, pal, caption, functions, asset_id, manifest):
    outdir = ASSETS / sub
    outdir.mkdir(parents=True, exist_ok=True)
    rows = rs._decode_interleaved(image, rs.SCREEN_BASE)
    rs.write_png(str(outdir / name), rs.W, rs.H, rows, pal)
    manifest.append({"file": "%s/%s" % (sub, name), "kind": "image", "cat": sub,
                     "caption": caption, "functions": functions, "assetId": asset_id})
    print("  wrote", (outdir / name).relative_to(ASSETS))


def _write_scene(sub, name, image, pal_addr, black_bg, caption, functions, asset_id, manifest):
    pal = rs.read_palette(image, pal_addr)
    if black_bg:
        pal[0] = (0, 0, 0)
    _emit(sub, name, image, pal, caption, functions, asset_id, manifest)


def render_graphics(manifest):
    # menu/results screens carry their own (correct) palettes at fixed addresses.
    _write_scene("screens", "leg_results_0.png", rs.render_leg_results(0), rs.PALETTE_ADDR, False,
                 "Leg-results screen (draw_leg_results)", ["0x125f2", "0x1225a"], None, manifest)
    _write_scene("screens", "results_0.png", rs.render_results_screen(), rs.PALETTE_ADDR, False,
                 "Race-end results screen (draw_results_screen)", ["0x1225a"], None, manifest)
    _write_scene("screens", "highscore_0.png", rs.render_highscore_screen(0), rs.PALETTE_ADDR, False,
                 "High-score screen (update_highscore + draw_results_screen)",
                 ["0x1238e", "0x1225a", "0x1047a"], "highscore_table", manifest)
    _write_scene("screens", "intermission.png", rs.render_intermission(), rs.PALETTE_ADDR, False,
                 "Attract / intermission screen (draw_intermission)", ["0x129ba", "0x127a0"], None, manifest)
    # buggy — drawn with the leg-0 in-race scenery palette (0x17fa2, set by init_leg).
    img, buf = _staged_leg(0)
    LIB.g_draw_buggy.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    LIB.g_draw_buggy.restype = None
    LIB.g_draw_buggy(buf)
    _emit("sprites", "buggy.png", img, _leg_pal(img), "Player buggy (draw_buggy + wheels/hi/lo, race palette)",
          ["0x152ac", "0x151f6", "0x153fa", "0x154c6"], "sprite_banks", manifest)
    # per-leg course maps — each with its own leg race palette.
    LIB.g_init_leg_dash.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    LIB.g_init_leg_dash.restype = None
    LIB.g_draw_dashboard.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    LIB.g_draw_dashboard.restype = None
    for leg in range(5):
        img, buf = _staged_leg(leg, {rs.A_MEM_BASE: rs.MEM_BASE.to_bytes(4, "big")})
        LIB.g_init_leg_dash(buf)
        LIB.g_draw_dashboard(buf, rs.DASH_DST_OFF)
        _emit("course", "legmap_%d.png" % leg, img, _leg_pal(img),
              "Leg %d course map (init_leg_dash + draw_dashboard, leg %d palette)" % (leg, leg),
              ["0x104b8", "0x12d38", "0x150a4"], "courses_dat", manifest)


# ---- palettes: swatch strips read from the image ----
SWATCH = 24


def render_palettes(manifest):
    outdir = ASSETS / "palettes"
    outdir.mkdir(parents=True, exist_ok=True)
    base = load_image(PRG)
    pals = [
        ("results_screen_palette", rs.PALETTE_ADDR, ["0x1238e", "0x12eb0"], "results_screen_palette"),
        ("leg_select_palette", 0x17F62, ["0x12af6", "0x12eb0"], "leg_select_palette"),
        ("leg_start_palette", 0x17F82, ["0x12af6"], "leg_start_palette"),
    ]
    W, H = 16 * SWATCH, SWATCH
    rows = [[x // SWATCH for x in range(W)] for _ in range(H)]
    for name, addr, functions, asset_id in pals:
        pal = rs.read_palette(base, addr)
        rs.write_png(str(outdir / (name + ".png")), W, H, rows, pal)
        manifest.append({"file": "palettes/%s.png" % name, "kind": "image", "cat": "palette",
                         "caption": "%s — 16-colour ST palette @0x%05x" % (name, addr),
                         "functions": functions, "assetId": asset_id})
        print("  wrote", (outdir / (name + ".png")).relative_to(ASSETS))
    # per-leg in-race scenery palette (0x17fa2, set by init_leg) — the colours the objects use.
    for leg in range(5):
        img, _ = _staged_leg(leg)
        pal = rs.read_palette(img, A_RACE_PAL)
        name = "race_palette_leg%d" % leg
        rs.write_png(str(outdir / (name + ".png")), W, H, rows, pal)
        manifest.append({"file": "palettes/%s.png" % name, "kind": "image", "cat": "palette",
                         "caption": "leg %d in-race scenery/car palette (@0x17fa2, set by init_leg)" % leg,
                         "functions": ["0x104b8", "0x12eb0"], "assetId": None})
        print("  wrote", (outdir / (name + ".png")).relative_to(ASSETS))


# ---- sprite sheets: the full decoded GRAPHICS.GRA art (all sprites) ----
GFX_HEADER = 3328                          # bytes before the RLE stream (== g_unpack_graphics' skip)
SHEET_BYTES = 32000                        # one 4-plane 320x200 page


def render_sheets(manifest):
    """Decode GRAPHICS.GRA to its 8 contiguous 4-plane pages (the game's full sprite atlas) and
    render each as a PNG. This is the exact RLE+planar decode that g_unpack_graphics performs before
    it de-interleaves and slices the pages into sprite banks."""
    outdir = ASSETS / "sprites"
    outdir.mkdir(parents=True, exist_ok=True)
    dec = bytearray(xg.rle_decode((HERE / "bin" / "GRAPHICS.GRA").read_bytes()[GFX_HEADER:]))
    if len(dec) % SHEET_BYTES:                          # pad a final partial page so it renders
        dec += b"\x00" * (SHEET_BYTES - len(dec) % SHEET_BYTES)
    img, _ = _staged_leg(0)
    pal = _leg_pal(img)                                 # leg-0 in-race scenery palette
    nsheets = len(dec) // SHEET_BYTES
    for s in range(nsheets):
        rows = xg.render_indices(dec, s * SHEET_BYTES)
        name = "sheet_%02d.png" % s
        rs.write_png(str(outdir / name), xg.W, xg.H, rows, pal)
        manifest.append({"file": "sprites/%s" % name, "kind": "image", "cat": "sprites",
                         "caption": "GRAPHICS.GRA sheet %d/%d — decoded 4-plane page (g_unpack_graphics RLE)" % (s, nsheets - 1),
                         "functions": ["0x10620", "0x1078c", "0x107f2", "0x1087e", "0x1306e"],
                         "assetId": "sprite_banks"})
        print("  wrote", (outdir / name).relative_to(ASSETS))


# ---- minimal GIF89a encoder (frames are 16-colour indexed -> a natural GIF match) ----
def _lzw(indices, mcs):
    clear, eoi = 1 << mcs, (1 << mcs) + 1
    out, acc, nbits = bytearray(), 0, 0

    def emit(code, size):
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(acc & 0xFF); acc >>= 8; nbits -= 8

    size = mcs + 1
    table = {(i,): i for i in range(clear)}
    nxt = clear + 2
    emit(clear, size)
    w = ()
    for px in indices:
        wp = w + (px,)
        if wp in table:
            w = wp
        else:
            emit(table[w], size)
            if nxt < 4096:
                table[wp] = nxt; nxt += 1
                if nxt == (1 << size) + 1 and size < 12:   # GIF early-change: widen one code after the boundary
                    size += 1
            else:
                emit(clear, size); table = {(i,): i for i in range(clear)}; nxt = clear + 2; size = mcs + 1
            w = (px,)
    emit(table[w], size)
    emit(eoi, size)
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def write_gif(path, frames, palette, delay_cs=10, transparent=None):
    """frames: list of row-lists of palette indices (0..15); palette: list of (r,g,b). Loops forever.

    transparent: a palette index to render as transparent. When set, each frame also uses disposal
    method 2 (restore to background) so the transparent background is cleared between frames instead
    of the previous frame showing through (which would leave trails)."""
    h = len(frames[0]); w = len(frames[0][0])
    pal = list(palette)[:16] + [(0, 0, 0)] * (16 - len(palette))
    gct = b"".join(bytes(c) for c in pal)              # 16-entry global colour table (size field 3)
    bg = transparent or 0                              # logical-screen background index
    # GCE packed field: disposal method (bits 2-4) | transparent-colour flag (bit 0).
    packed = (2 << 2) | 1 if transparent is not None else 0
    tidx = transparent if transparent is not None else 0
    buf = bytearray(b"GIF89a")
    buf += w.to_bytes(2, "little") + h.to_bytes(2, "little") + bytes([0xF3, bg, 0])  # 0xF3: GCT, 16 cols
    buf += gct
    buf += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"   # loop forever
    for fr in frames:
        buf += bytes([0x21, 0xF9, 0x04, packed, delay_cs & 0xFF, (delay_cs >> 8) & 0xFF, tidx, 0x00])
        buf += b"\x2c" + (0).to_bytes(2, "little") * 2 + w.to_bytes(2, "little") + h.to_bytes(2, "little") + b"\x00"
        pixels = [px for row in fr for px in row]
        data = _lzw(pixels, 4)
        buf += bytes([4])                              # min code size
        i = 0
        while i < len(data):
            chunk = data[i:i + 255]
            buf += bytes([len(chunk)]) + chunk; i += 255
        buf += b"\x00"                                 # block terminator
    buf += b"\x3b"
    Path(path).write_bytes(buf)


# ---- animations: pose the buggy per frame via the verified g_draw_* engine, assemble a GIF ----
A_WHEEL_POS, A_LEAN_STATE, A_SKID = 0x18cc0, 0x18cc2, 0x18cbc
A_BUGGY_PITCH_OFF, A_ANIM_FRAME = 0x18cbe, 0x18d0c   # crash pose: vertical pitch + fg fireball frame
CRASH_ANIM_TBL = 0x18690                             # crash script: 8-byte records indexed by collision_lock
CRASH_REC = 8                                        # bytes per crash_anim_tbl record
CRASH_FLIP_START = 0x18                              # first record of the flip (roll-over) sub-sequence
CRASH_SPIN_START = 0x90                              # first record of the spin-out sub-sequence
CRASH_SPIN_FRAMES = 3                                # spin-out is an endless lean 42/43/44 cycle; one loop

# per-animation draw chain: which verified engine entries to blit, in the game's draw order.
DRAW_BODY = ("g_draw_buggy",)                                  # body only (lean / skid poses)
DRAW_CRASH = ("g_draw_fg_sprite", "g_draw_buggy")             # fireball under the tumbling body

# The cleared framebuffer background is palette index 0 (never used by the drawn sprite pixels, only
# by their transparency mask). We mark it transparent in the GIF and recolour it purple, so it blends
# with the page in browsers yet shows as a purple key in viewers that ignore GIF transparency.
GIF_BG_INDEX = 0
GIF_BG_PURPLE = (255, 0, 255)


def _anim_frame(pose, draw_fns=DRAW_BODY):
    image, buf = rs._prepared_image(pose)
    for name in draw_fns:
        fn = getattr(harness._lib, name)
        fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        fn.restype = None
        fn(buf)
    return rs._decode_interleaved(image, rs.SCREEN_BASE)


def render_animations(manifest):
    outdir = ASSETS / "sprites"
    outdir.mkdir(parents=True, exist_ok=True)
    pal_img, _ = _staged_leg(0)
    pal = _leg_pal(pal_img)                            # leg-0 race palette (buggy colours)
    pal[GIF_BG_INDEX] = GIF_BG_PURPLE                  # background -> purple, marked transparent below
    base = {rs.A_LEG_INDEX: (0).to_bytes(2, "big")}

    def w(v):
        return (v & 0xffff).to_bytes(2, "big")

    # crash: pose the buggy from the game's own crash_anim_tbl (verified game_update script) instead
    # of hand-authoring. Each 8-byte record sets the tumble body frame (lean_state), the vertical
    # pitch (buggy_pitch_off), and the foreground fireball frame (anim_frame, 0x08 at the peak).
    tbl_img, _ = rs._prepared_image(base)

    def crash_pose(idx):
        rec = CRASH_ANIM_TBL + idx
        return {**base,
                A_LEAN_STATE:      w(tbl_img[rec + 1]),               # tumble body frame
                A_BUGGY_PITCH_OFF: bytes(tbl_img[rec + 2:rec + 4]),   # vertical pitch (be16, verbatim)
                A_ANIM_FRAME:      w(tbl_img[rec + 5])}               # fg fireball frame

    # flip (roll-over): walk from the start, advancing by each record's own (8 - step) rule, until
    # the terminal sentinel (lean high bit set), exactly as game_update does.
    flip_poses, idx = [], CRASH_FLIP_START
    while (tbl_img[CRASH_ANIM_TBL + idx + 1] & 0x80) == 0:      # rec[1] < 0 -> terminal
        flip_poses.append(crash_pose(idx))
        idx += CRASH_REC - tbl_img[CRASH_ANIM_TBL + idx]
    # spin-out: the game cycles lean 42/43/44 endlessly (no terminal), so take one 3-frame loop.
    spin_poses = [crash_pose(CRASH_SPIN_START + i * CRASH_REC) for i in range(CRASH_SPIN_FRAMES)]

    # the buggy-body draw chain (draw_buggy + wheels/lo/hi); the flip adds the fg fireball entry.
    body_fns = ["0x152ac", "0x151f6", "0x153fa", "0x154c6"]
    anims = [
        ("buggy_lean.gif", "Buggy lean sweep (lean_state, g_draw_buggy)",
         [{**base, A_LEAN_STATE: w(v)} for v in (0, 6, 12, 0x18, 0x1c, 0x18, 12, 6)], DRAW_BODY, body_fns),
        ("buggy_skid.gif", "Buggy skid (skid_off ±8, g_draw_buggy)",
         [{**base, A_SKID: w(v & 0xffff)} for v in (0, 4, 8, 4, 0, -4, -8, -4)], DRAW_BODY, body_fns),
        ("buggy_crash.gif", "Buggy crash flip (crash_anim_tbl: tumbling g_draw_buggy + g_draw_fg_sprite fireball)",
         flip_poses, DRAW_CRASH, ["0x1518a"] + body_fns),
        ("buggy_spin.gif", "Buggy spin-out (crash_anim_tbl: lean 42-44 cycle, g_draw_buggy)",
         spin_poses, DRAW_BODY, body_fns),
    ]
    for name, caption, poses, draw_fns, functions in anims:
        frames = [_anim_frame(p, draw_fns) for p in poses]
        if len({tuple(tuple(r) for r in f) for f in frames}) < 2:
            print("  (skip %s: frames identical)" % name); continue
        write_gif(str(outdir / name), frames, pal, delay_cs=12, transparent=GIF_BG_INDEX)
        manifest.append({"file": "sprites/%s" % name, "kind": "image", "cat": "sprites",
                         "caption": caption, "functions": functions,
                         "assetId": "anim_" + name[:-4]})   # -> the "Animations" catalog asset (drop .gif)
        print("  wrote", (outdir / name).relative_to(ASSETS))


# ---- individual roadside-object sprites: drive the real blitter one object at a time ----
# obj_type_jumptable index -> handler name (the objsprite_* / handler_* family, by sprite width).
OBJ_HANDLERS = {
    0x131f6: "objsprite_t4", 0x13204: "objsprite_t53", 0x133a6: "objsprite_t39",
    0x133ac: "objsprite_t34", 0x133b2: "objsprite_t3", 0x133b6: "objsprite_w88",
    0x13506: "objsprite_t38", 0x1350c: "objsprite_t33", 0x13512: "objsprite_t42",
    0x13528: "objsprite_t49", 0x1352c: "objsprite_t2", 0x1361c: "objsprite_t37",
    0x13622: "objsprite_t32", 0x13628: "objsprite_t41", 0x1363e: "objsprite_t16",
    0x13642: "objsprite_t1", 0x1465c: "draw_obj_handler_dbl", 0x14664: "draw_obj_handler_lo",
}
# engine-internal alt entries the courses dispatch to (not standalone named functions).
OBJ_ENGINE_NAME = {0x131d0: "objsprite", 0x13dfa: "objsprite_wide", 0x144a2: "objshift",
                   0x144ac: "objshift_w2", 0x144b2: "objshift_w2"}
OBJ_JUMPTABLE = 0x13144
OBJ_CODE_LO, OBJ_CODE_HI = 0x131d0, 0x14700   # valid object-handler code span (objsprite/blit families)
BUF_A_BASE = 0x21900                 # render_screen MEM_BASE + 0x1900 (== value staged at 0x18c00)
OBJ_TYPE_BASE, OBJ_TYPE_STRIDE = 0x8a0, 0xd0
# a5 list / a3 flag / a4 xoff streams the dispatcher reads (from test_object_list.py).
A_LIST_BASE, A_FLAGS, A_XOFF_TBL, A_OBJ_SCAN_OFF = 0x16c06, 0x18ebc, 0x18f26, 0x18c58
A_VIEW_FLAGS, A_VIEW_PARITY, A_BONUS_TIMER = 0x18c56, 0x18c60, 0x18d08
N_OBJECTS = 15
# Handlers use two dst bases (a6+0 for objsprite, a6+0x3ac0 for the handler_lo/objshift families), so
# place a6 mid a big zeroed arena and decode a window that captures both (+ upward perspective draws).
# The arena must clear the real staged regions — buf_c (sprite data) runs 0x3c660..0x7b660 — so use
# the free space above them.
OBJ_ARENA_LO, OBJ_ARENA_HI = 0x80000, 0xC0000
OBJ_A6 = 0x98000
OBJ_DECODE = 0x94000
OBJ_X = 0x58                         # mid-screen x so the object draws as a masked sprite (not edge-filled)


def _rd16(buf, a):
    return int.from_bytes(bytes(buf[a:a + 2]), "big")


def _rd32(buf, a):
    return int.from_bytes(bytes(buf[a:a + 4]), "big")


def _handler_for(buf, jumpidx):
    off = _rd16(buf, OBJ_JUMPTABLE + jumpidx)
    if off & 0x8000:
        off -= 0x10000
    return (OBJ_JUMPTABLE + off) & 0xFFFFFF


def _crop_nonzero(rows, margin=2):
    ys = [y for y, r in enumerate(rows) if any(r)]
    if not ys:
        return None
    xs = [x for r in rows for x, v in enumerate(r) if v]
    y0, y1 = max(0, min(ys) - margin), min(len(rows), max(ys) + 1 + margin)
    x0, x1 = max(0, min(xs) - margin), min(len(rows[0]), max(xs) + 1 + margin)
    return [r[x0:x1] for r in rows[y0:y1]]


def _draw_one_object(image, buf, obj_type, colour):
    """Stage a single object of `obj_type` at mid-screen and run the real g_draw_object_list into a
    fresh black buffer; return the cropped sprite (rows of palette indices) or None."""
    def wr(a, b):
        image[a:a + len(b)] = b
    image[OBJ_ARENA_LO:OBJ_ARENA_HI] = bytes(OBJ_ARENA_HI - OBJ_ARENA_LO)   # zero the whole draw arena
    lst = _w(0) + _w(0) + b"".join(_w(OBJ_X if i == 0 else 0) for i in range(N_OBJECTS))
    wr(A_LIST_BASE, lst)
    wr(A_FLAGS, b"".join(_w(obj_type if i == 0 else 0) for i in range(N_OBJECTS)))
    for a in (A_XOFF_TBL, A_OBJ_SCAN_OFF, A_VIEW_FLAGS, A_VIEW_PARITY, A_BONUS_TIMER):
        wr(a, _w(0))
    harness._lib.g_draw_object_list.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
    harness._lib.g_draw_object_list.restype = None
    harness._lib.g_draw_object_list(buf, A_LIST_BASE, A_FLAGS, OBJ_A6, 0, 0, colour)
    return _crop_nonzero(rs._decode_interleaved(image, OBJ_DECODE))


def render_object_sprites(manifest):
    outdir = ASSETS / "objects"
    outdir.mkdir(parents=True, exist_ok=True)
    seen, n = {}, 0
    for leg in range(5):
        image, buf = _staged_leg(leg)                               # records + per-leg race palette
        pal = _leg_pal(image)
        for t in range(1, 64):
            base = BUF_A_BASE + OBJ_TYPE_BASE + ((t * OBJ_TYPE_STRIDE) & 0xFFFF)
            jumpidx = _rd16(buf, base + 0x06)
            rows_m1 = _rd16(buf, base + 0x04)
            colour = _rd16(buf, base - 0x10)
            src = _rd32(buf, base)
            handler = _handler_for(buf, jumpidx) if jumpidx and jumpidx < 0x60 and not jumpidx & 1 else 0
            if not (OBJ_CODE_LO <= handler < OBJ_CODE_HI) or rows_m1 >= 0x60 or src == 0 or src >= 0x40000:
                continue
            key = (jumpidx, src, rows_m1)
            if key in seen:
                continue
            sprite = _draw_one_object(image, buf, t, colour or 5)
            if sprite is None or len(sprite) < 3 or len(sprite[0]) < 3:
                continue
            seen[key] = True
            if handler in OBJ_HANDLERS:
                hname, hlink = OBJ_HANDLERS[handler], "0x%05x" % handler
            else:                                     # engine-internal alt entry: name + link to its engine
                hname = OBJ_ENGINE_NAME.get(handler, "fn%05x" % handler)
                hlink = "0x14680" if 0x144a2 <= handler < 0x14700 else (
                    "0x131f6" if OBJ_CODE_LO <= handler < 0x13ed6 else None)
            short = hname.replace("objsprite_", "").replace("draw_obj_handler_", "h_")
            name = "obj_%s_t%02x.png" % (short, t)
            functions = ([hlink] if hlink else []) + ["0x1306e", "0x1087e"]
            rs.write_png(str(outdir / name), len(sprite[0]), len(sprite), sprite, pal)
            manifest.append({"file": "objects/%s" % name, "kind": "image", "cat": "objects",
                             "caption": "roadside object type 0x%02x -> %s (%dx%d, leg %d)"
                             % (t, hname, len(sprite[0]), len(sprite), leg),
                             "functions": functions, "assetId": "sprite_banks"})
            n += 1
            print("  wrote", (outdir / name).relative_to(ASSETS))
    print("  (%d distinct object sprites)" % n)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    _bind_sound_api()
    manifest = []
    print("audio (C sound driver -> YM2149):")
    render_audio(manifest)
    print("graphics (C draw_* renders):")
    render_graphics(manifest)
    print("sprite sheets (GRAPHICS.GRA decode):")
    render_sheets(manifest)
    print("object sprites (C blitter, one per type):")
    render_object_sprites(manifest)
    print("animations (C draw_buggy -> GIF):")
    render_animations(manifest)
    print("palettes:")
    render_palettes(manifest)
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("\n%d media files + manifest.json written to %s" % (len(manifest), ASSETS))


if __name__ == "__main__":
    main()
