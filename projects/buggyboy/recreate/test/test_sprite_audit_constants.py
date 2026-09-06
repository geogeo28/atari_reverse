"""Pin `../tools/sprite_audit.py`'s mirrored constants to their single sources of truth.

The GRAPHICS.GRA audit lives outside `recreate/`, cannot include `include/addrs.h` or the cores, and
so restates a few dozen game addresses, record offsets and jump-table targets. CLAUDE.md's rule
applies: pick one canonical definition and pin the copy equal with a test. A drift then fails with
the name of the constant, rather than leaving the audit silently reading the wrong address and
reporting the artwork there as unused.

Only integer-literal `#define`s are in reach; the audit's remaining constants (the crash-script
record field offsets, the fg_anim record layout) exist nowhere but the disassembly and carry their
game_update.c / sprite.c line references in the script's own comments instead.
"""
import re
import sys
from pathlib import Path

REC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REC.parent / "tools"))

import sprite_audit                                    # noqa: E402

# `#define NAME <integer literal>` and nothing else: the trailing lookahead makes the literal the
# WHOLE definition, so a compound expression is left invisible rather than half-read.
_DEFINE_RE = re.compile(r"^#define\s+(?P<name>\w+)\s+(?P<value>0[xX][0-9a-fA-F]+|\d+)[uU]?"
                        r"(?=\s*(?:/[/*]|$))", re.M)


def _defines(path):
    """{name: value} for every plain integer `#define` in `REC / path`."""
    return {m["name"]: int(m["value"], 0) for m in _DEFINE_RE.finditer((REC / path).read_text())}


# sprite_audit's name -> the addrs.h name it mirrors.
ADDRS_MIRRORS = {
    "A_INPUT_STATE": "A_input_state",
    "A_VIEW_FLAGS": "A_view_flags",
    "A_VIEW_PARITY": "A_view_parity",
    "A_BONUS_TIMER": "A_bonus_timer",
    "A_OBJ_SCAN_OFF": "A_obj_scan_off",
    "A_DSP_TOGGLE": "A_dsp_toggle",
    "A_DSP_VARIANT_IDX": "A_dsp_variant_idx",
    "A_SCROLL_FRAME": "A_scroll_frame",
    "A_HSCROLL_POS": "A_hscroll_pos",
    "A_SCROLL_SPEED": "A_scroll_speed",
    "A_CKPT_SCROLL": "A_ckpt_scroll",
    "A_WHEEL_POS": "A_wheel_pos",
    "A_ANIM_FRAME": "A_anim_frame",
    "A_CRASH_ACTIVE": "A_crash_active",
    "A_CRASH_FRAME": "A_crash_frame",
    "A_CRASH_BARS": "A_crash_bars",
    "A_CRASH_LAP": "A_crash_lap",
    "A_TIME_LEFT": "A_time_left",
    "A_COUNTDOWN_TIMER": "A_countdown_timer",
    "A_COUNTDOWN_SUB": "A_countdown_sub",
    "A_OBJ_LIST_BASE": "A_obj_list_base",
    "A_OBJ_FLAGS": "A_obj_flags",
    "A_OBJ_XOFF_TBL": "A_obj_xoff_tbl",
    "A_EVT_OBJ_TYPE_TBL": "A_evt_obj_type_tbl",
    "OBJ_JUMPTABLE": "A_obj_type_jumptable",
    "CRASH_ANIM_TBL": "A_crash_anim_tbl",
    "FG_ANIM_TBL": "A_fg_anim_tbl",
    "NUM_GLYPH_TBL": "A_num_glyph_tbl",
}

# The cores' own `#define`s the audit restates, under the same name.
SOURCE_MIRRORS = {
    "src/blit.c": ("OBJ_TYPE_BASE", "OBJ_TYPE_STRIDE", "OBJ_SPECIAL_BASE", "OBJ_REC_ROWS",
                   "OBJ_REC_JUMP", "OBJ_H_STUB", "OBJ_H_NOOP"),
    "src/sprite.c": ("BUGGY_BODY_TBL",),
    "src/hud.c": ("HUD_DSP_TBL",),
    "src/text.c": ("NUM_GLYPH_BUF_OFF",),
    "src/highscore.c": ("COUNTDOWN_START",),
}


def test_addresses_mirror_addrs_h():
    defines = _defines("include/addrs.h")
    for ours, theirs in ADDRS_MIRRORS.items():
        assert getattr(sprite_audit, ours) == defines[theirs], f"{ours} != addrs.h {theirs}"


def test_record_geometry_mirrors_the_cores():
    for path, names in SOURCE_MIRRORS.items():
        defines = _defines(path)
        for name in names:
            assert getattr(sprite_audit, name) == defines[name], f"{name} != {path}'s"


def test_object_handler_targets_are_blit_cs_own_set():
    """`_record_is_live` decides a record is real by testing its resolved jump target against this
    set. A handler added to obj_dispatch and not here would make that record look malformed, drop
    its sprite out of the static cross-check, and let genuinely-drawn artwork be reported unused."""
    blit = _defines("src/blit.c")
    assert sprite_audit.OBJ_HANDLER_TARGETS == frozenset(
        value for name, value in blit.items() if name.startswith("OBJ_H_"))


def test_row_pitch_and_buffer_layout():
    """The atlas row pitch is the screen's, and the buffer layout is render_screen's."""
    assert sprite_audit.ATLAS_ROW_BYTES == sprite_audit.rs.ROW_STRIDE
    sprite_audit.check_layout()
