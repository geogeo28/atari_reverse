#!/usr/bin/env python3
"""Generate docs/function_graph.html — a standalone, interactive d3.js call-graph explorer for
BUGGYBOY.PRG.

Data model (all derived statically, no runtime deps):
  * nodes  — every named function: address, size, subsystem, verification status/notes, the global
             variables/constants it touches, and its callers/callees.
  * tree   — a BFS spanning tree rooted at the two entry points (_start, and the REFRESH VBL
             handler), so the call structure can be expanded/collapsed.
  * isolated — functions with no inbound edge (dead code, e.g. evt_collision).

Sources: names.txt (fn/var/cmt), recreate/STATUS.md (per-function notes), recreate/include/addrs.h
(variable descriptions), recreate/src/*.c (subsystem = defining file), and a first-pass disassembly
of the PRG (call edges + variable references). Re-run after any of those change:
    python3 gen_graph.py
"""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PRG = os.path.join(HERE, "bin", "BUGGYBOY.PRG")
NAMES = os.path.join(HERE, "names.txt")
STATUS = os.path.join(HERE, "recreate", "STATUS.md")
ADDRS = os.path.join(HERE, "recreate", "include", "addrs.h")
SRCDIR = os.path.join(HERE, "recreate", "src")
DISASM = os.path.join(HERE, "..", "..", "tools", "prg_dis.py")
OUT = os.path.join(HERE, "docs", "function_graph.html")

BASE = 0x10000
TEXT_END = BASE + 0xBCF8
EVT_JT = 0x11AA2            # event_jumptable base
OBJ_JT = 0x13144           # obj_type_jumptable base
EVT_HANDLER_LO = 0x11CDC   # event-handler region (folded into game_update's dispatch)
EVT_HANDLER_HI = 0x11F4C
GAME_UPDATE = 0x1110E
DRAW_OBJECT_LIST = 0x1306E
REFRESH = 0x1B086          # VBL sound handler (installed as a vector, not called from _start)

# subsystem label + colour per source file / fallback prefix
SUBSYS_COLOR = {
    "road": "#4e79a7", "blit": "#59a14f", "sprite": "#8cd17d", "hud": "#f28e2b",
    "sound": "#e15759", "game_update": "#b07aa1", "events": "#d4a6c8", "gameplay": "#9c755f",
    "score": "#edc948", "highscore": "#bab0ac", "results": "#ff9da7", "intermission": "#76b7b2",
    "screen": "#a0cbe8", "text": "#86bcb6", "graphics": "#499894", "input": "#f1ce63",
    "os": "#79706e", "other": "#bab0ac",
}
PREFIX_SUBSYS = [
    ("render_road", "road"), ("blit_road", "road"), ("build_road", "road"), ("draw_ground", "road"),
    ("draw_checkpoint", "road"), ("set_screen_offset", "road"), ("wait_vbl", "road"),
    ("objsprite", "blit"), ("blit_obj", "blit"), ("draw_obj", "blit"), ("draw_object", "blit"),
    ("build_sprite", "blit"),
    ("draw_buggy", "sprite"), ("draw_fg", "sprite"), ("draw_dashboard", "sprite"),
    ("draw_result", "sprite"),
    ("draw_hud", "hud"), ("draw_num", "hud"), ("draw_text", "hud"), ("draw_crash", "hud"),
    ("snd_", "sound"), ("INITTUNE", "sound"), ("INITFX", "sound"), ("TURNOFF", "sound"),
    ("EGOFF", "sound"), ("REFRESH", "sound"), ("stop_music", "sound"), ("play_event_tune", "sound"),
    ("evt_", "events"), ("handle_marker", "events"),
    ("add_score", "score"), ("init_scoretable", "score"),
    ("update_highscore", "highscore"),
    ("draw_results", "results"), ("draw_leg", "results"), ("draw_panel", "results"),
    ("draw_divider", "results"),
    ("intermission", "intermission"), ("fade_step", "intermission"), ("draw_intermission", "intermission"),
    ("check_abort", "intermission"),
    ("game_update", "game_update"), ("probe_collision", "game_update"),
    ("read_input", "input"), ("read_joystick", "input"),
    ("load_graphics", "graphics"), ("unpack_graphics", "graphics"),
    ("clear_screen", "screen"), ("fill_", "screen"), ("flip_screen", "screen"),
    ("gem_", "os"), ("xbios_", "os"), ("set_rez", "os"), ("install_handlers", "os"),
    ("console_", "os"), ("init_leg", "gameplay"), ("init_playfield", "gameplay"),
    ("init_leg_dash", "gameplay"), ("draw_frame", "road"),
    ("_start", "os"), ("main", "os"),
]

# event_jumptable handler descriptions, keyed by resolved target address. Every one of the 65 live
# indices resolves to one of these; game_update's gu_dispatch_event reconstructs them all.
EVENT_DESC = {
    0x11C18: "bare rts — unreachable (dispatch sites guard id != 0)",
    0x11BA4: "evt_flag_gate — roadside-object flag sequence, obj_type 1",
    0x11BA8: "evt_flag_gate — obj_type 2",
    0x11BAC: "evt_flag_gate — obj_type 3",
    0x11BB0: "evt_flag_gate — obj_type 4",
    0x11BB4: "evt_flag_gate — obj_type 5",
    0x11C1A: "evt_flag_gate — d7=6 variant (residual: not separately reconstructed)",
    0x11C5A: "score-message A — add_score + tune 8, gate d6&&d7",
    0x11C62: "score-message A — unconditional",
    0x11C6A: "score-message A — gate d6&&!d7",
    0x11CDC: "score-message B — add_score + tune 8, gate d6&&d7",
    0x11CE4: "score-message B — unconditional",
    0x11CEC: "score-message B — gate d6&&!d7",
    0x11CF6: "score-message C — add_score + tune 8, gate d6&&d7",
    0x11CFE: "score-message C — unconditional",
    0x11D08: "score-message C — gate d6&&!d7",
    0x11D12: "checkpoint counters — crash_lap++/crash_active++ + tune 9, gate d6&&d7",
    0x11D1A: "checkpoint counters — unconditional",
    0x11D2E: "checkpoint counters — gate d6&&!d7",
    0x11D38: "no-op (bare rts)",
    0x11D3A: "spawn marker-decay object + add_score + tune 0xa",
    0x11D62: "no-op (bare rts)",
    0x11D64: "arm a spin (spin_reset/spin_word2) if speed>=0x1e and unlocked",
    0x11D8E: "spawn collision object typed by rpm band + marker fx 0/1",
    0x11DCC: "freeze road curve + marker fx 5",
    0x11DE2: "engine-rpm penalty -> speed + marker fx 6",
    0x11E16: "common collision-object spawn + marker fx 3",
    0x11E4E: "finish-line display A + stop_music",
    0x11E5C: "finish-line display B + stop_music",
    0x11E8E: "bonus-number display (left) + build_road_geometry + marker fx 8",
    0x11E96: "bonus-number display (left, id 0x3f)",
    0x11E92: "bonus-number display (right) + build_road_geometry + marker fx 8",
    0x11EAA: "bonus-number display (right, id 0x40)",
}


def compact_indices(nums):
    """[25,27,43,44,45] -> '25, 27, 43-45'"""
    nums = sorted(nums)
    runs, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        runs.append(str(nums[i]) if i == j else "%d–%d" % (nums[i], nums[j]))
        i = j + 1
    return ", ".join(runs)


# curated data/asset catalog: the two data files + the major in-memory structures the code produces
# and consumes. `addr` (when set) links the entry to a named global so "referenced by" is derived
# from the static call graph; extra known producers/consumers are pinned in `refs_extra`. Categories
# order the sidebar. (id, name, addr|None, size|None, category, format, source, refs_extra[fn addr])
ASSET_CATS = ["File", "Sprites / graphics", "Animations", "Course / road", "Palette / colour",
              "Dispatch tables", "Score", "Sound", "Render buffers"]
_LOAD, _UNPACK, _GU, _BRG = 0x12166, 0x10620, 0x1110E, 0x11F4C
_BSS, _BSSM, _INITLEG, _INITSC = 0x1078C, 0x107F2, 0x104B8, 0x1047A
_DOBJ, _DOL, _DGO = 0x1087E, 0x1306E, 0x12EF6
_DBUGGY, _DFG = 0x152AC, 0x1518A          # draw_buggy (body), draw_fg_sprite (foreground/fireball)
CATALOG = [
    ("graphics_gra", "GRAPHICS.GRA", None, 182428, "File",
     "RLE-packed 4-plane ST bitmaps: 0x1234=zero-run, 0x5678=ff-run, 0x1234^3=end, then 4-plane interleave.",
     "On disk. Read by load_graphics into buf_c (+0xc350); decoded by unpack_graphics into the sprite banks.",
     [_LOAD, _UNPACK]),
    ("courses_dat", "COURSES.DAT", None, 63072, "File",
     "Per-leg packed course records: road curve/width segments, roadside-object markers, event bytes.",
     "On disk. Read by load_graphics into the buf_a course area; unpacked per-record by game_update's course-advance.",
     [_LOAD, _GU, _BRG]),
    ("fname_graphics", "\"GRAPHICS.GRA\" path", 0x17E2A, None, "File", "GEMDOS Fopen path string.", "const in image", [_LOAD]),
    ("fname_courses", "\"COURSES.DAT\" path", 0x17E1A, None, "File", "GEMDOS Fopen path string.", "const in image", [_LOAD]),
    # sprites / graphics
    ("sprite_banks", "unpacked sprite banks", None, None, "Sprites / graphics",
     "4-plane object/buggy/HUD sprite cells in buf_c-relative banks.",
     "Decoded from GRAPHICS.GRA by unpack_graphics; drawn by the object/buggy/HUD blitters.",
     [_UNPACK, _DOBJ, _DOL, _DGO]),
    ("sprite_shifts", "sprite shift tables", None, None, "Sprites / graphics",
     "Pre-shifted sprite copies + AND masks for sub-pixel-x blits (one set per fine-x).",
     "Built from the unpacked sprites by build_sprite_shifts / build_sprite_shifts_msk; read by draw_object.",
     [_BSS, _BSSM, _DOBJ]),
    ("buggy_body_tbl", "buggy_body_tbl", 0x177B8, None, "Sprites / graphics", "buggy body sprite records (lean/skid).", "const in image", []),
    ("fg_anim_tbl", "fg_anim_tbl", 0x177A0, None, "Sprites / graphics",
     "foreground-sprite anim frames: 8-byte records {rows-1, dst_off (w), src_off (long, +buf_c)}; frame 1 is the crash fireball / dust cloud.",
     "const in image; indexed by anim_frame in draw_fg_sprite.", [_DFG]),
    ("crash_anim_tbl", "crash_anim_tbl", 0x18690, None, "Sprites / graphics",
     "crash/spin animation script: 8-byte records {step, lean_state, buggy_pitch_off (w), rpm, fg-anim-frame, steer, marker}; flip sub-seq @+0x18 rolls the buggy over (with fireball), spin sub-seq @+0x90 cycles lean 42-44.",
     "const in image; walked by game_update's crash / auto-steer branch, indexed by collision_lock.", [_GU]),
    ("sprite_list", "sprite_list", 0x18D7A, None, "Sprites / graphics", "per-frame roadside-object display list.", "built each frame from the course markers", []),
    ("hud_dsp_tbl", "hud_dsp_tbl", 0x1854C, None, "Sprites / graphics", "dashboard-variant sprite record table.", "const in image", []),
    ("num_glyph_tbl", "num_glyph_tbl", 0x17C5E, None, "Sprites / graphics", "per-digit byte offset into the pre-rendered number sprites.", "const in image", []),
    ("obj_view_xform_tbl", "obj_view_xform_tbl", 0x1722A, None, "Sprites / graphics", "per-view object transform table.", "const in image", []),
    # animations (GIFs rendered by gen_assets.py, driven by the verified draw functions)
    ("anim_buggy_lean", "buggy_lean (animation)", None, None, "Animations",
     "Buggy steering lean sweep — lean_state selects buggy_body_tbl (@0x177b8) frames.",
     "GIF rendered by gen_assets.py: g_draw_buggy per lean_state pose.", [_DBUGGY]),
    ("anim_buggy_skid", "buggy_skid (animation)", None, None, "Animations",
     "Buggy skid — buggy_skid_off (±8) shifts the body drawn from buggy_body_tbl.",
     "GIF rendered by gen_assets.py: g_draw_buggy per skid pose.", [_DBUGGY]),
    ("anim_buggy_crash", "buggy_crash (animation)", None, None, "Animations",
     "Crash roll-over flip — crash_anim_tbl (@0x18690) flip sub-sequence poses the tumbling body + fg fireball.",
     "GIF rendered by gen_assets.py: g_draw_fg_sprite + g_draw_buggy per crash_anim_tbl record.", [_DFG, _DBUGGY, _GU]),
    ("anim_buggy_spin", "buggy_spin (animation)", None, None, "Animations",
     "Spin-out — crash_anim_tbl (@0x18690) spin sub-sequence cycles lean 42-44.",
     "GIF rendered by gen_assets.py: g_draw_buggy per crash_anim_tbl record.", [_DBUGGY, _GU]),
    # course / road
    ("road_curve_tbl", "road_curve_tbl", 0x18EFC, None, "Course / road", "106 longwords: per-row accumulated curve offset.", "built each frame by build_road_geometry", []),
    ("road_width_tbl", "road_width_tbl", 0x18F24, None, "Course / road", "per-row road half-width.", "built each frame by build_road_geometry", []),
    ("road_scanline_tbl", "road_scanline_tbl", 0x190AC, None, "Course / road", "per-scanline road geometry.", "built each frame by build_road_geometry", []),
    ("road_seg_data", "road_seg_data", 0x18D1C, None, "Course / road", "8 longs: active road-segment descriptors.", "unpacked from COURSES.DAT per record", []),
    ("ground_band_records", "ground_band_records", 0x172EA, None, "Course / road", "gradient/solid ground band records (per-entry offset + colour pair).", "const in image", []),
    ("ground_col_offsets", "ground_col_offsets", 0x16A6E, None, "Course / road", "ground column offsets.", "const in image", []),
    ("obj_markers", "obj_markers", 0x18D3C, None, "Course / road", "14 × 0x20-byte per-object roadside marker records.", "seeded by init_leg, advanced from the course stream", []),
    # palette / colour
    ("color_pairs", "color_pairs", 0x15AFA, None, "Palette / colour", "packed colour-pair table for the road/object blitters.", "const in image", []),
    ("leg_start_palette", "leg_start_palette", 0x17F82, None, "Palette / colour", "palette flashed by the leg-start 'get ready' animation.", "const in image", []),
    ("leg_select_palette", "leg_select_palette", 0x17F62, None, "Palette / colour", "leg-select screen palette.", "const in image", []),
    ("crash_color_tbl", "crash_color_tbl", 0x17F5A, None, "Palette / colour", "crash-effect colour cycle.", "const in image", []),
    # dispatch tables
    ("obj_type_jumptable", "obj_type_jumptable", 0x13144, None, "Dispatch tables", "word offsets to the ~25 object-sprite handlers.", "const in image; indexed by object type in draw_object_list", [_DOL]),
    ("event_jumptable", "event_jumptable", 0x11AA2, None, "Dispatch tables", "65 word offsets to the course-event handlers.", "const in image; indexed by event id in game_update", [_GU]),
    ("evt_obj_type_tbl", "evt_obj_type_tbl", 0x18B68, None, "Dispatch tables", "collision-object type per rpm band.", "const in image", []),
    # score
    ("score_delta", "score_delta_* table", 0x17370, None, "Score", "6-byte BCD deltas (gate/msg/time/roll/bonus/evt).", "const in image; passed to add_score", []),
    ("default_scores", "default_scores", 0x184E6, None, "Score", "per-leg default high-score rows.", "const in image; copied by init_scoretable", [_INITSC]),
    ("highscore_table", "highscore_table", 0x18266, None, "Score", "ranked high-score rows (name + score).", "seeded from default_scores; updated by update_highscore", []),
    # sound
    ("snd_cmd_table", "snd_cmd_table", 0x1B394, None, "Sound", "13-entry voice-command jump/param table.", "const in image; used by snd_voice_b", []),
    ("snd_pitch_table", "snd_pitch_table", 0x1B2BE, None, "Sound", "note→pitch table.", "const in image", []),
    ("snd_period_table", "snd_period_table", 0x1B446, None, "Sound", "YM2149 period table.", "const in image", []),
    ("snd_env_table", "snd_env_table", 0x1B440, None, "Sound", "envelope table.", "const in image", []),
    # render buffers
    ("buf_a", "buf_a", 0x18C00, None, "Render buffers", "buffer-a pointer (course/scroll area).", "malloc'd by main; course data lands here", []),
    ("buf_b", "buf_b", 0x18C04, None, "Render buffers", "buffer-b pointer (deinterleave scratch).", "malloc'd by main", []),
    ("buf_c", "buf_c", 0x18C08, None, "Render buffers", "buffer-c pointer; GRAPHICS.GRA read target + sprite banks.", "malloc'd by main", []),
]




def parse_names():
    fns, varname, cmt = {}, {}, {}
    for line in open(NAMES):
        line = line.rstrip("\n")
        m = re.match(r"(?:fn|proto) (0x[0-9a-f]+) (\S+)", line)
        if m:
            fns[int(m.group(1), 16)] = m.group(2)
            continue
        m = re.match(r"var (0x[0-9a-f]+) (\S+)", line)
        if m:
            varname[int(m.group(1), 16)] = m.group(2)
            continue
        m = re.match(r"cmt (0x[0-9a-f]+) (.+)", line)
        if m:
            cmt[int(m.group(1), 16)] = m.group(2).strip()
    return fns, varname, cmt


def parse_addrs():
    """A_<name> 0x<addr> /* desc */  ->  addr -> desc"""
    desc = {}
    for line in open(ADDRS):
        m = re.match(r"\s*#define\s+A_\w+\s+(0x[0-9a-f]+)\s*/\*\s*(.*?)\s*\*/", line)
        if m:
            desc[int(m.group(1), 16)] = m.group(2)
    return desc


def parse_status():
    """| `0x..` | `name` | bytes | status | notes |"""
    meta = {}
    for line in open(STATUS):
        if not line.startswith("| `0x"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 5:
            continue
        addr = int(parts[0].strip("` "), 16)
        notes = "|".join(parts[4:]).strip()  # rejoin if notes contained a pipe
        meta[addr] = {"bytes": parts[2], "status": parts[3], "notes": notes}
    return meta


def parse_index_sizes():
    sizes = {}
    out = subprocess.run(["python3", DISASM, PRG], capture_output=True, text=True).stdout
    # the analyzer's disassembly is what we parse for edges; sizes come from names.txt spacing gaps
    return sizes, out


def read16s(data, ghidra_addr):
    off = ghidra_addr - BASE + 0x1C
    return int.from_bytes(data[off:off + 2], "big", signed=True)


def subsystem_for(name, defined_in):
    if name in defined_in:
        stem = defined_in[name]
        if stem in SUBSYS_COLOR:
            return stem
    for pre, sub in PREFIX_SUBSYS:
        if name.startswith(pre):
            return sub
    return "other"


def src_definitions():
    """map function base-name -> source file stem (subsystem) via its g_<name> definition."""
    defined = {}
    for fname in os.listdir(SRCDIR):
        if not fname.endswith(".c"):
            continue
        stem = fname[:-2]
        for line in open(os.path.join(SRCDIR, fname)):
            m = re.match(r"[A-Za-z].*\bg_(\w+)\s*\(", line)
            if m:
                defined.setdefault(m.group(1), stem)
    return defined


def build():
    fns, varname, _cmt = parse_names()
    vardesc = parse_addrs()
    status = parse_status()
    defined = src_definitions()
    data = open(PRG, "rb").read()
    _, dis = parse_index_sizes()

    starts = sorted(fns)

    def extent(addr):
        i = starts.index(addr)
        nxt = starts[i + 1] if i + 1 < len(starts) else TEXT_END
        return addr, nxt

    # interval owner: which function's body an address falls in (event-handler gap -> game_update)
    def owner(addr):
        if EVT_HANDLER_LO <= addr < EVT_HANDLER_HI:
            return GAME_UPDATE
        o = None
        for s in starts:
            if s <= addr:
                o = s
            else:
                break
        if o is None:
            return None
        _, end = extent(o)
        return o if addr < end else None

    callees = {a: set() for a in fns}     # caller -> {callee}
    fnvars = {a: set() for a in fns}      # function -> {var addr}
    mnem_at = {}                          # instr addr -> mnemonic (for fall-through detection)

    line_re = re.compile(r"^([0-9a-f]{6}): [0-9a-f ]{2,}?\s{2,}(\S+)\s*(.*)$")
    ctl_re = re.compile(r"\$([0-9a-f]+)")
    imm_re = re.compile(r"#?\$([0-9a-f]+)")
    for line in dis.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16) + BASE
        mnem, ops = m.group(2), m.group(3)
        mnem_at[addr] = mnem
        own = owner(addr)
        if own is None:
            continue
        if mnem[:3] in ("bsr", "jsr", "jmp", "bra"):
            t = ctl_re.search(ops)
            if t:
                tgt = int(t.group(1), 16) + BASE
                if tgt in fns and tgt != own:
                    callees[own].add(tgt)
        if "<RELOC ptr>" in line:
            for im in imm_re.findall(ops):
                va = int(im, 16) + BASE
                if va in varname:
                    fnvars[own].add(va)

    # fall-through edges: a function entered by falling off the end of the preceding code (no call),
    # e.g. the fill_words->fill_span / draw_text->draw_text_row aliases and init_playfield's inline
    # console menu (console_scancode/console_wait_char). Add prev->F when the instruction ending at
    # F.start is not an unconditional terminator (rts/rte/rtr/rtd/bra/jmp).
    TERM = ("rts", "rte", "rtr", "rtd", "bra", "jmp")
    instr_addrs = sorted(mnem_at)
    import bisect
    for f in starts:
        j = bisect.bisect_left(instr_addrs, f) - 1
        if j < 0:
            continue
        prev = instr_addrs[j]
        if 0 < f - prev <= 10 and not mnem_at[prev].startswith(TERM):
            src = owner(prev)
            if src is not None and src != f:
                callees[src].add(f)

    # jump-table edges

    for i in range(65):  # event_jumptable -> named handlers (others fold into game_update)
        t = (EVT_JT + read16s(data, EVT_JT + i * 2)) & 0xFFFFFF
        if t in fns:
            callees[GAME_UPDATE].add(t)
    for i in range(90):  # obj_type_jumptable -> object-sprite handlers
        t = (OBJ_JT + read16s(data, OBJ_JT + i * 2)) & 0xFFFFFF
        if 0x131F6 <= t < 0x15016 and t in fns:
            callees[DRAW_OBJECT_LIST].add(t)

    # inbound / callers
    callers = {a: set() for a in fns}
    for c, outs in callees.items():
        for t in outs:
            callers[t].add(c)

    entries = {0x10000, REFRESH}
    idx_names = {int(l.split()[0], 16) for l in open("/tmp/decomp_index.txt")} if os.path.exists("/tmp/decomp_index.txt") else set()

    nodes = {}
    for a in starts:
        name = fns[a]
        st = status.get(a, {})
        vlist = [{"addr": "0x%05x" % v, "name": varname[v], "desc": vardesc.get(v, "")}
                 for v in sorted(fnvars[a])]
        no_in = not callers[a] and a not in entries
        if a in entries:
            kind = "entry"
        elif no_in:
            kind = "dead"
        elif a not in idx_names and name not in ("REFRESH",):
            kind = "helper"
        else:
            kind = "core"
        nodes["0x%05x" % a] = {
            "addr": "0x%05x" % a, "name": name,
            "subsystem": subsystem_for(name, defined),
            "bytes": st.get("bytes", ""), "status": st.get("status", ""),
            "notes": st.get("notes", ""), "kind": kind,
            "callees": ["0x%05x" % t for t in sorted(callees[a])],
            "callers": ["0x%05x" % t for t in sorted(callers[a])],
            "vars": vlist,
        }

    # event jump-table: idx -> handler, grouped by resolved target (game_update dispatches all 65).
    ev_groups = {}
    for idx in range(65):
        t = (EVT_JT + read16s(data, EVT_JT + idx * 2)) & 0xFFFFFF
        ev_groups.setdefault(t, []).append(idx)
    events = []
    for t in sorted(ev_groups, key=lambda x: min(ev_groups[x])):
        o = owner(t)
        link = ("0x%05x" % t) if t in fns else (
            ("0x%05x" % o) if (o is not None and o != GAME_UPDATE and o in fns) else None)
        name = fns[t] if t in fns else "0x%05x" % t
        events.append({"idx": compact_indices(ev_groups[t]), "target": "0x%05x" % t,
                       "name": name, "desc": EVENT_DESC.get(t, ""), "link": link})
    gu = "0x%05x" % GAME_UPDATE
    if gu in nodes:
        nodes[gu]["events"] = events
        nodes[gu]["eventIdxTotal"] = sum(len(v) for v in ev_groups.values())

    # data/asset catalog: files + in-memory structures, wired to the functions that touch them.
    var_refs = {}                              # var addr -> [fn addr] that reference it (static)
    for f, vs in fnvars.items():
        for v in vs:
            var_refs.setdefault(v, set()).add(f)
    assets = []
    for aid, name, addr, size, cat, fmt, source, extra in CATALOG:
        refs = set(extra)
        if addr is not None:
            refs |= var_refs.get(addr, set())
        refs = ["0x%05x" % r for r in sorted(refs) if r in fns]
        assets.append({"id": aid, "name": name, "addr": ("0x%05x" % addr) if addr else "",
                       "size": size, "cat": cat, "format": fmt, "source": source, "refs": refs})

    # BFS spanning tree from the entry points
    parent = {}
    order = {a: [] for a in fns}
    visited = set()

    def bfs(root):
        q = [root]
        visited.add(root)
        while q:
            cur = q.pop(0)
            for t in sorted(callees[cur]):
                if t not in visited:
                    visited.add(t)
                    parent[t] = cur
                    order[cur].append(t)
                    q.append(t)

    bfs(0x10000)
    bfs(REFRESH)
    isolated = sorted(a for a in fns if a not in visited)

    def make_tree(a):
        return {"addr": "0x%05x" % a, "name": fns[a],
                "subsystem": subsystem_for(fns[a], defined),
                "kind": nodes["0x%05x" % a]["kind"],
                "children": [make_tree(c) for c in order[a]]}

    tree = {
        "addr": "root", "name": "BUGGYBOY.PRG", "subsystem": "other", "kind": "root",
        "children": [make_tree(0x10000), make_tree(REFRESH)],
    }

    # media: docs/assets/manifest.json (produced by gen_assets.py, C-driven). Attach each media file
    # to the reconstruction functions that produce/consume it and to its catalog asset (by assetId).
    media = []
    manifest_path = os.path.join(os.path.dirname(OUT), "assets", "manifest.json")
    if os.path.exists(manifest_path):
        media = json.load(open(manifest_path))
        asset_by_id = {a["id"]: a for a in assets}
        for mi, m in enumerate(media):
            for fn_hex in m.get("functions", []):
                if fn_hex in nodes:
                    nodes[fn_hex].setdefault("media", []).append(mi)
            aid = m.get("assetId")
            if aid and aid in asset_by_id:
                asset_by_id[aid].setdefault("media", []).append(mi)

    return {
        "nodes": nodes, "tree": tree,
        "isolated": ["0x%05x" % a for a in isolated],
        "assets": assets, "assetCats": ASSET_CATS, "media": media,
        "subsysColor": SUBSYS_COLOR,
        "stats": {"functions": len(fns), "edges": sum(len(v) for v in callees.values()),
                  "isolated": len(isolated), "media": len(media)},
    }


def main():
    model = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(model))
    with open(OUT, "w") as f:
        f.write(html)
    print("wrote %s  (%d functions, %d edges, %d isolated)"
          % (OUT, model["stats"]["functions"], model["stats"]["edges"], model["stats"]["isolated"]))


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BuggyBoy — function call-graph explorer</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root { --bg:#12151c; --panel:#1b1f2a; --panel2:#232838; --ink:#e6e9ef; --dim:#8b93a7;
          --line:#39415a; --accent:#f28e2b; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--ink);
    font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  #app { display:grid; grid-template-columns:1fr 380px; grid-template-rows:auto 1fr; height:100vh; }
  header { grid-column:1/3; display:flex; align-items:center; gap:14px; padding:10px 16px;
    background:var(--panel); border-bottom:1px solid var(--line); flex-wrap:wrap; }
  header h1 { font-size:15px; margin:0; font-weight:600; letter-spacing:.02em; }
  header .stat { color:var(--dim); font-size:12px; }
  header input { background:var(--panel2); border:1px solid var(--line); color:var(--ink);
    border-radius:6px; padding:6px 10px; width:220px; outline:none; }
  header button { background:var(--panel2); border:1px solid var(--line); color:var(--ink);
    border-radius:6px; padding:6px 10px; cursor:pointer; }
  header button:hover { border-color:var(--accent); }
  #graph { position:relative; overflow:hidden; grid-column:1; grid-row:2; }
  #graph svg { width:100%; height:100%; display:block; cursor:grab; }
  #graph svg:active { cursor:grabbing; }
  .link { fill:none; stroke:var(--line); stroke-width:1.2px; }
  .node circle { stroke:#12151c; stroke-width:1.5px; cursor:pointer; }
  .node text { fill:var(--ink); font-size:11px; paint-order:stroke; stroke:#12151c;
    stroke-width:3px; cursor:pointer; }
  .node.collapsed circle { stroke:var(--ink); stroke-width:2px; }
  .node.selected text { fill:var(--accent); font-weight:700; }
  aside { grid-column:2; grid-row:2; background:var(--panel); border-left:1px solid var(--line);
    overflow:auto; padding:16px; }
  aside h2 { font-size:15px; margin:0 0 2px; }
  aside .addr { color:var(--dim); font-family:ui-monospace,Menlo,monospace; font-size:12px; }
  aside .badge { display:inline-block; padding:2px 8px; border-radius:99px; font-size:11px;
    margin:6px 6px 0 0; }
  aside .notes { margin:12px 0; padding:10px 12px; background:var(--panel2); border-radius:8px;
    border:1px solid var(--line); font-size:12.5px; }
  aside section { margin-top:14px; }
  aside section h3 { font-size:12px; text-transform:uppercase; letter-spacing:.08em;
    color:var(--dim); margin:0 0 6px; }
  #navPane { margin-top:18px; border-top:1px solid var(--line); padding-top:10px; }
  .chip { display:inline-block; padding:3px 9px; margin:0 5px 5px 0; border-radius:6px;
    background:var(--panel2); border:1px solid var(--line); cursor:pointer;
    font-family:ui-monospace,Menlo,monospace; font-size:11.5px; }
  .chip:hover { border-color:var(--accent); }
  .chip.dead { border-color:var(--accent); }
  .chip.asset { border-left:3px solid #edc948; }
  .acat { font-size:10.5px; text-transform:uppercase; letter-spacing:.07em; color:var(--dim);
    margin:10px 0 4px; }
  .var { padding:6px 0; border-bottom:1px solid var(--line); }
  .var b { font-family:ui-monospace,Menlo,monospace; color:#a0cbe8; }
  .var .vd { color:var(--dim); font-size:12px; }
  .evt-row { display:grid; grid-template-columns:88px 1fr; gap:8px; padding:6px 0;
    border-bottom:1px solid var(--line); align-items:start; }
  .evt-idx { font-family:ui-monospace,Menlo,monospace; font-size:11px; color:var(--accent);
    background:#2a2f40; border-radius:5px; padding:2px 6px; text-align:center; }
  .evt-name { font-family:ui-monospace,Menlo,monospace; font-size:11.5px; color:#a0cbe8; }
  .evt-desc { grid-column:2; color:var(--dim); font-size:11.5px; }
  .media { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .media figure { margin:0; }
  .media img { width:100%; border:1px solid var(--line); border-radius:6px; background:#000;
    image-rendering:pixelated; cursor:pointer; }
  .media audio { width:100%; height:30px; }
  .media figcaption { color:var(--dim); font-size:10.5px; margin-top:2px; }
  .media .full { grid-column:1/3; }
  .legend { display:flex; flex-wrap:wrap; gap:8px; }
  .legend span { display:flex; align-items:center; gap:5px; font-size:11.5px; color:var(--dim); }
  .legend i { width:11px; height:11px; border-radius:3px; display:inline-block; }
  .empty { color:var(--dim); }
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>🚗 BuggyBoy — call graph</h1>
    <span class="stat" id="stats"></span>
    <input id="search" placeholder="search function… (Enter)">
    <button id="expandAll">Expand all</button>
    <button id="collapseAll">Collapse</button>
    <button id="reset">Fit</button>
    <span style="flex:1"></span>
    <div class="legend" id="legend"></div>
  </header>
  <div id="graph"></div>
  <aside>
    <div id="detailPane"><p class="empty">Click a node to inspect a function. Circles with a solid
      ring have hidden children — click to expand. The two roots are the program entry
      (<code>_start</code>) and the <code>REFRESH</code> VBL sound interrupt.</p></div>
    <div id="navPane">
      <section><h3>Data &amp; assets</h3><div id="assets"></div></section>
      <section><h3>Isolated / dead functions</h3><div id="isolated"></div></section>
    </div>
  </aside>
</div>
<script>
const DATA = __DATA__;
if (typeof d3 === "undefined") {
  document.getElementById("graph").innerHTML =
    '<p style="padding:24px;color:#e15759;font-size:14px">d3.js could not be loaded from the CDN ' +
    '(this page needs an internet connection for <code>d3js.org</code>). For fully offline use, ' +
    'download <code>d3.v7.min.js</code> next to this file and change the &lt;script src&gt; to it.</p>';
  throw new Error("d3 unavailable");
}
const NODES = DATA.nodes, COLORS = DATA.subsysColor;
const color = s => COLORS[s] || COLORS.other;
const esc = s => (s == null ? "" : String(s)).replace(/[&<>]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// ---- legend ----
const legend = d3.select("#legend");
Object.keys(COLORS).filter(k=>k!=="other").forEach(k=>{
  const s = legend.append("span");
  s.append("i").style("background", COLORS[k]);
  s.append("text").text(k);
});
d3.select("#stats").text(`${DATA.stats.functions} functions · ${DATA.stats.edges} edges · ${DATA.stats.isolated} isolated · ${DATA.stats.media||0} media`);

// ---- tree layout ----
const svg = d3.select("#graph").append("svg");
const g = svg.append("g");
const gLink = g.append("g"), gNode = g.append("g");
const zoom = d3.zoom().scaleExtent([0.15, 3]).on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);

const root = d3.hierarchy(DATA.tree);
let i = 0;
const dx = 17, dy = 210;
const tree = d3.tree().nodeSize([dx, dy]);
const diagonal = d3.linkHorizontal().x(d=>d.y).y(d=>d.x);

// start collapsed below depth 1 (roots + their direct children visible)
root.x0 = 0; root.y0 = 0;
const allDesc = root.descendants();            // captured while children still full
allDesc.forEach(d => d.id = ++i);
const byAddr = new Map();
allDesc.forEach(d => { if (!byAddr.has(d.data.addr)) byAddr.set(d.data.addr, d); });
allDesc.forEach(d => { d._children = d.children; if (d.depth > 1) d.children = null; });

let selected = null;

function update(source) {
  const nodes = root.descendants(), links = root.links();
  tree(root);
  let left=root, right=root;
  root.eachBefore(n=>{ if(n.x<left.x)left=n; if(n.x>right.x)right=n; });
  const t = svg.transition().duration(250);

  const node = gNode.selectAll("g.node").data(nodes, d=>d.id);
  const nodeEnter = node.enter().append("g")
    .attr("class","node")
    .attr("transform",`translate(${source.y0},${source.x0})`)
    .on("click",(e,d)=>{ toggle(d); select(d); });
  nodeEnter.append("circle").attr("r",4.5);
  nodeEnter.append("text").attr("dy","0.32em")
    .attr("x",d=>d._children||d.children ? -8 : 8)
    .attr("text-anchor",d=>d._children||d.children ? "end" : "start")
    .text(d=>d.data.name);

  const nodeMerge = nodeEnter.merge(node);
  nodeMerge.transition(t).attr("transform",d=>`translate(${d.y},${d.x})`);
  nodeMerge.attr("class",d=>"node"+(d._children?" collapsed":"")+(selected===d?" selected":""));
  nodeMerge.select("circle")
    .attr("r",d=>d.data.kind==="root"?6:d.data.kind==="entry"?6:4.5)
    .attr("fill",d=>d.data.kind==="dead"?"#e15759":color(d.data.subsystem));
  nodeMerge.select("text")
    .attr("x",d=>d._children||d.children ? -8 : 8)
    .attr("text-anchor",d=>d._children||d.children ? "end" : "start");

  node.exit().transition(t).remove()
    .attr("transform",`translate(${source.y},${source.x})`);

  const link = gLink.selectAll("path.link").data(links, d=>d.target.id);
  const linkEnter = link.enter().append("path").attr("class","link")
    .attr("d",()=>{const o={x:source.x0,y:source.y0};return diagonal({source:o,target:o});});
  linkEnter.merge(link).transition(t).attr("d",diagonal);
  link.exit().transition(t).remove()
    .attr("d",()=>{const o={x:source.x,y:source.y};return diagonal({source:o,target:o});});

  root.eachBefore(d=>{ d.x0=d.x; d.y0=d.y; });
}

function toggle(d){
  if (d.children){ d._children=d.children; d.children=null; }
  else { d.children=d._children; d._children=null; }
  update(d);
}
function expandAncestors(d){ let p=d.parent; while(p){ if(p._children){p.children=p._children;p._children=null;} p=p.parent; } }

function fit(){
  const b=g.node().getBBox();
  const gw=svg.node().clientWidth, gh=svg.node().clientHeight;
  const scale=Math.min(0.9, 0.9/Math.max(b.width/gw, b.height/gh));
  const tx=gw/2-scale*(b.x+b.width/2), ty=gh/2-scale*(b.y+b.height/2);
  svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity.translate(tx,ty).scale(scale));
}

// ---- details panel ----
const MEDIA = DATA.media || [];
function renderMedia(idxs){
  if(!idxs || !idxs.length) return "";
  const items = idxs.map(i=>MEDIA[i]).filter(Boolean).map(m=>{
    const body = m.kind==="audio"
      ? `<audio controls preload="none" src="assets/${m.file}"></audio>`
      : `<img src="assets/${m.file}" title="${esc(m.caption)}" onclick="window.open(this.src)">`;
    return `<figure class="${m.kind==='audio'?'full':''}">${body}<figcaption>${esc(m.caption)}</figcaption></figure>`;
  }).join("");
  return `<section><h3>Media (${idxs.length}) — C reconstruction output</h3><div class="media">${items}</div></section>`;
}
function nodeChip(addr, extraClass){
  const n = NODES[addr]; if(!n) return "";
  return `<span class="chip ${extraClass||''}" data-addr="${addr}" style="border-left:3px solid ${color(n.subsystem)}">${esc(n.name)}</span>`;
}
function select(d){
  selected = d;
  gNode.selectAll("g.node").attr("class",x=>"node"+(x._children?" collapsed":"")+(selected===x?" selected":""));
  const addr = d.data.addr;
  if (addr==="root"){ return; }
  showDetails(addr);
}
function showDetails(addr){
  const n = NODES[addr]; if(!n) return;
  const kindLabel = {entry:"entry point", dead:"⚠ isolated / dead", helper:"reconstruction helper", core:"core function"}[n.kind]||n.kind;
  const varsHtml = n.vars.length
    ? n.vars.map(v=>`<div class="var"><b>${esc(v.name)}</b> <span class="addr">${v.addr}</span><div class="vd">${esc(v.desc)}</div></div>`).join("")
    : `<span class="empty">— none referenced</span>`;
  const callees = n.callees.length ? n.callees.map(a=>nodeChip(a)).join("") : `<span class="empty">— leaf</span>`;
  const callers = n.callers.length ? n.callers.map(a=>nodeChip(a)).join("") : `<span class="empty">— none (entry or dead)</span>`;
  const eventsHtml = n.events ? `<section><h3>Event jump-table (${n.eventIdxTotal} indices → ${n.events.length} handlers)</h3>
    <div>${n.events.map(e=>`<div class="evt-row">
      <span class="evt-idx">${e.idx}</span>
      ${e.link ? `<span class="chip" data-addr="${e.link}">${esc(e.name)}</span>` : `<span class="evt-name">${esc(e.name)}</span>`}
      <span class="evt-desc">${esc(e.desc)}</span>
    </div>`).join("")}</div></section>` : "";
  d3.select("#detailPane").html(`
    <h2>${esc(n.name)}</h2>
    <div class="addr">${n.addr}${n.bytes?` · ${esc(n.bytes)} bytes`:""}</div>
    <span class="badge" style="background:${color(n.subsystem)}22;border:1px solid ${color(n.subsystem)}">${esc(n.subsystem)}</span>
    <span class="badge" style="background:#2a2f40">${kindLabel}</span>
    ${n.status?`<span class="badge" style="background:#2a2f40">${esc(n.status)}</span>`:""}
    ${n.notes?`<div class="notes">${esc(n.notes)}</div>`:""}
    <section><h3>Calls (${n.callees.length})</h3><div>${callees}</div></section>
    <section><h3>Called by (${n.callers.length})</h3><div>${callers}</div></section>
    ${renderMedia(n.media)}
    ${eventsHtml}
    <section><h3>Variables / constants (${n.vars.length})</h3>${varsHtml}</section>
  `);
  d3.select("#detailPane").selectAll(".chip").on("click", function(){ jumpTo(this.getAttribute("data-addr")); });
}
// ---- data/asset details ----
const ASSETS = {}; DATA.assets.forEach(a=>ASSETS[a.id]=a);
function showAsset(id){
  const a = ASSETS[id]; if(!a) return;
  selected = null;
  gNode.selectAll("g.node").attr("class",x=>"node"+(x._children?" collapsed":""));
  const refs = a.refs.length ? a.refs.map(r=>nodeChip(r)).join("") : `<span class="empty">— none captured statically (accessed via computed addressing)</span>`;
  d3.select("#detailPane").html(`
    <h2>${esc(a.name)}</h2>
    <div class="addr">${a.addr||""}${a.size?` · ${a.size.toLocaleString()} bytes`:""}</div>
    <span class="badge" style="background:#edc94822;border:1px solid #edc948">${esc(a.cat)}</span>
    <div class="notes"><b>Format:</b> ${esc(a.format)}<br><b>Source:</b> ${esc(a.source)}</div>
    ${renderMedia(a.media)}
    <section><h3>Referenced by (${a.refs.length})</h3><div>${refs}</div></section>
  `);
  d3.select("#detailPane").selectAll(".chip").on("click", function(){ jumpTo(this.getAttribute("data-addr")); });
}
function jumpTo(addr){
  const d = byAddr.get(addr);
  if (d){ expandAncestors(d); update(root); select(d);
    const t=d3.zoomTransform(svg.node());
    svg.transition().duration(400).call(zoom.transform,
      d3.zoomIdentity.translate(svg.node().clientWidth/2 - t.k*d.y, svg.node().clientHeight/2 - t.k*d.x).scale(t.k));
  } else { showDetails(addr); }  // isolated node: details only (not in tree)
}

// ---- data & assets (grouped by category) ----
const abox = d3.select("#assets");
DATA.assetCats.forEach(cat=>{
  const items = DATA.assets.filter(a=>a.cat===cat);
  if(!items.length) return;
  abox.append("div").attr("class","acat").text(cat);
  const wrap = abox.append("div");
  items.forEach(a=> wrap.append("span").attr("class","chip asset").attr("data-id",a.id).text(a.name));
});
abox.selectAll(".chip.asset").on("click", function(){ showAsset(this.getAttribute("data-id")); });

// ---- isolated list ----
d3.select("#isolated").html(DATA.isolated.map(a=>nodeChip(a,"dead")).join("") || '<span class="empty">none</span>');
d3.select("#isolated").selectAll(".chip").on("click", function(){ showDetails(this.getAttribute("data-addr")); });

// ---- controls ----
d3.select("#search").on("keydown", function(e){
  if(e.key!=="Enter") return;
  const q=this.value.trim().toLowerCase(); if(!q) return;
  const hit=Object.keys(NODES).find(a=>NODES[a].name.toLowerCase().includes(q));
  if(hit) jumpTo(hit);
});
d3.select("#expandAll").on("click",()=>{ root.each(d=>{ if(d._children){d.children=d._children;d._children=null;} }); update(root); setTimeout(fit,300); });
d3.select("#collapseAll").on("click",()=>{ root.descendants().forEach(d=>{ if(d.depth>1){ if(d.children){d._children=d.children;d.children=null;} } }); update(root); setTimeout(fit,300); });
d3.select("#reset").on("click", fit);

update(root);
setTimeout(fit, 350);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
