"""The HOST SLOTS — `include/host_slot.h`'s one table, shared by every component, of the fixed addresses
that stand in, off target, for a ROM frame local whose ADDRESS a routine hands on. GEMDOS's twelve: the FAT
routines' word, the directory search's pattern, the walk's name and cursor, the delete's mark byte,
`Fattrib`'s attribute byte, `create`'s free-slot search name and new entry's FCB name, `Frename`'s entry
buffer, `Pexec`'s loader's header locals, and the dispatcher's two — the argument words of its nested
`Fwrite` ($fc5078) and the byte a redirected read lands in. The VDI's seven: its `Malloc`/`Mfree` words,
vst_font's nested call's arrays, and the wide lines', arrowheads' and markers' points (`vdi/lines.h`).

Every slot must sit where the differential drops bytes on both shores — the oracle's stack band, above
its guard — and below both the deepest frame the kit calls legitimate and the `savptr` frame the
GEMDOS batteries declare, so nothing the ORACLE writes can land on one. And no two may overlap: the C
asserts a slot is never claimed twice, but two ROLES live at once (a walk's name and cursor while it
searches, a search's pattern while the FAT word is taken beneath it) are two different slots, and only
their addresses keep them apart.
"""
from pathlib import Path

from harness import addrs, emu

import gemdos

HEADER = Path(__file__).resolve().parents[1] / "include" / "host_slot.h"
CONSTANTS = addrs.parse(HEADER)
SLOT_PREFIX = "HOST_SLOT_"
WIDTH_SUFFIX = "_BYTES"


def host_slots(constants):
    """`{role: (address, bytes)}` for every slot the header names — each address with its width."""
    return {name[len(SLOT_PREFIX):]: (value, constants[name + WIDTH_SUFFIX])
            for name, value in constants.items()
            if name.startswith(SLOT_PREFIX) and not name.endswith(WIDTH_SUFFIX)}


def misplaced(slots):
    """What is wrong with a slot table: overlaps between neighbours, and spans outside the band."""
    ceiling = min(emu.STACK_TOP - emu.STACK_SCRATCH, gemdos.FRAME_AT)
    spans = sorted((at, at + width, role) for role, (at, width) in slots.items())
    faults = [f"{role} {at:#x}..{end:#x} is outside {emu.STACK_GUARD_LO:#x}..{ceiling:#x}"
              for at, end, role in spans if not emu.STACK_GUARD_LO <= at < end <= ceiling]
    faults += [f"{role} runs into {next_role}" for (_at, end, role), (next_at, _end, next_role)
               in zip(spans, spans[1:]) if end > next_at]
    return faults


# THE PINNED ROLES, by the wave that added them: a group of band 6 wave 1b names its own roles inside its own block, so
# no two authors edit one line; the pin is their union.
ROLES_BEFORE_BAND_6_WAVE_1B = {"SEARCH_PATTERN", "WALK_NAME", "WALK_CURSOR", "DELETE_MARK", "ATTRIBUTE", "FRAME_WORD",
                               "CREATE_FREE_NAME", "CREATE_FCB", "RENAME_ENTRY", "C_ENTRY_ARGUMENTS",
                               "REDIRECTED_BYTE", "PEXEC_LOCALS", "GEMDOS_WORDS", "VDI_VST_FONT_CALL",
                               "VDI_WIDE_CORNERS", "VDI_WIDE_OFFSET", "VDI_PERP_DIRECTION", "VDI_ARROW_TRIANGLE",
                               "VDI_MARKER_POINTS", "VDI_GTEXT_EXTENT", "VDI_JUSTIFIED_EXTENT",
                               "VDI_OPNWK_COLOUR_CALL", "AES_OB_FIND_RECTS", "AES_SH_ENVRN_FRAME",
                               "AES_SH_FIND_FRAME", "AES_GSX_START_DISCARD", "AES_CLINE_POINTS",
                               "AES_GTEXT_RECT", "AES_JUST_COUNT", "AES_BOX_RECT", "AES_XOR_RECT", "AES_MOVEBOX_STEPS",
                               "AES_GROWBOX_STEPS", "AES_OB_USER_PARMBLK", "AES_JUST_DRAW_FRAME",
                               "AES_OB_DRAW_POSITION", "AES_OB_CHANGE_FRAME",
                               "AES_GR_STILLDN_RECTANGLE", "AES_GR_STILLDN_ANSWERS", "AES_GR_WATCHBOX_RECT",
                               "AES_GR_DRAW_RECT", "AES_GR_CLAMP_MOUSE", "AES_GR_RUBWIND_RECT", "AES_GR_DRAGBOX_FRAME",
                               "AES_GR_SLIDEBOX_RECTS", "AES_MENU_SR_RECT", "AES_MN_DO_FRAME", "AES_MN_REGISTER_NAME",
                               "AES_PXL_RECT_FIELD", "AES_CURFLD_RECTS", "AES_OB_EDIT_FRAME",
                               "AES_W_CLIPDRAW_RECT", "AES_W_CPWALK_RECT", "AES_W_MOVE_RECTS", "AES_WM_GET_RECT",
                               "AES_W_SETACTIVE_RECT", "AES_W_REDRAW_RECTS", "AES_DRAW_CHANGE_FRAME", "AES_WM_OPCL_RECT",
                               "AES_WM_SET_RECT", "AES_FM_PARSE_INDEX", "AES_FM_BUILD_RECTS", "AES_FM_DO_FRAME",
                               "AES_FM_BUTTON_FRAME", "AES_FM_ALERT_FRAME", "AES_ERALERT_FRAME", "AES_FM_ERROR_CODE",
                               "AES_FS_START_TREE", "AES_FS_FORMAT_FRAME", "AES_FS_NSCROLL_FRAME",
                               "AES_FS_INPUT_FRAME", "AES_PD_MATCH_NAME", "AES_AP_FIND_NAME",
                               "AES_MARSHAL_FRAME", "AES_DISPATCH_MOUSE_FORM",
                               "AES_PGMLD_WORDS", "AES_HCTL_WINDOW_SIZE", "AES_HCTL_WINDOW_CORNER",
                               "AES_HCTL_WINDOW_DRAG_RECT", "AES_HCTL_WINDOW_DRAG_ANSWERS", "AES_HCTL_RECT_CHOICE",
                               "AES_CTLMGR_ANSWERS",
                               "AES_AMOUSE_MOBLK", "AES_AP_RDWR_QPB", "AES_EV_MULTI_QPB", "AES_INOROUT_RECT",
                               "AES_SNDCLI_BASEPAGE",                  # band 5 wave 3, slice L
                               "AES_READ_INF_PAIR", "AES_GEM_MAIN_ICON",   # band 5 wave 4, slice I
                               "AES_DESK_BIND_FRAME",                      # band 6 wave 1a, unit D
                               "AES_DOS_LABEL_FRAME", "AES_DOS_SPACE_DFREE", "AES_DOS_SETDT_STAMP"}   # band 6 wave 1a, unit O
# ---- band 6 wave 1b, group G1 (units I, L) ----
ROLES_G1 = {"AES_DESK_WIN_FRAME", "AES_DESK_VIEW_FRAME"}
# ---- end of group G1's ----
# ---- band 6 wave 1b, group G2 (units A, K, J) ----
ROLES_G2 = {"AES_APP_TRAN_BITBLK", "AES_MEN_UPDATE_FIND"}
# ---- end of group G2's ----
# ---- band 6 wave 1b, group G3 (units B, G) ----
ROLES_G3 = {"AES_GR_ISDOWN_ANSWERS", "AES_GR_BWAIT_ANSWERS", "AES_ACT_CHKOBJ_RECTS", "AES_ACT_CHG_RECT", "AES_ACT_ALLCHG_RECTS"}
# ---- end of group G3's ----
# ---- band 6 wave 1b, group G4 (units C, H, E, F) ----
ROLES_G4 = {"AES_DESK_DIR_RECT", "AES_DESK_FUN_MSG", "AES_DESK_MY_ITOA_NUMBER", "AES_DESK_OB_SFCB_FRAME", "AES_DESK_INF_DTTMSZ_FRAME"}
# ---- end of group G4's ----
# BAND 6 WAVE 2: each group names its roles in its own block, AND its window — `{group: ((lo, hi), ...)}`, cut from the
# one free run band 6 wave 2's prep re-laid the table into (`$7f7a6..$7f9d2`; `$7f9c4..$7f9d2` kept back): a group's
# slot lies inside its own windows, and no other slot lies inside any window.
# (the wave-2 fix pass's) G3's and G4's shrunk to the extents their slots use: $7f910..$7f962 (82 B) and $7f99a..$7f9d2
# (56 B, the 14 kept back among them) are the band's free bytes again
WAVE_2_WINDOWS = {"G1": ((0x7f7a6, 0x7f7dc),), "G2": ((0x7f7dc, 0x7f844),), "G3": ((0x7f844, 0x7f910),),
                  "G4": ((0x7f962, 0x7f99a),)}
# ---- band 6 wave 2, group G1 (units C, F, E) ----
ROLES_WAVE_2_G1 = {"AES_DESK_INF_FOLDER_FRAME", "AES_DESK_USERDEF_FRAME"}
# ---- end of group G1's wave-2 ----
# ---- band 6 wave 2, group G2 (units H, G, M) ----
ROLES_WAVE_2_G2 = {"AES_DESK_FUN_REBLD_FRAME", "AES_DESK_FUN_MKDIR_FRAME", "AES_DESK_FUN_D2DESK_FRAME", "AES_DESK_FUN_OP_FRAME",
                   "AES_DESK_FUN_WIN2WIN_FRAME", "AES_DESK_FUN_DESK2WIN_FRAME"}
# ---- end of group G2's wave-2 ----
# ---- band 6 wave 2, group G3 (units I, J, K, L) ----
ROLES_WAVE_2_G3 = {"AES_DESK_FUN_CLOSE_FRAME", "AES_DESK_OPEN_FRAME", "AES_DESK_SUPP_FRAME", "AES_DESK_CNX_GET_FRAME",
                   "AES_DESK_SCROLL_FRAME"}
# ---- end of group G3's wave-2 ----
# ---- band 6 wave 2, group G4 (units A, B) ----
ROLES_WAVE_2_G4 = {"AES_GR_DRGPLNS_FRAME", "AES_ACT_BDOWN_FRAME", "AES_APP_START_ENVIRONMENT"}
# ---- end of group G4's wave-2 ----
ROLES_WAVE_2 = {"G1": ROLES_WAVE_2_G1, "G2": ROLES_WAVE_2_G2, "G3": ROLES_WAVE_2_G3, "G4": ROLES_WAVE_2_G4}
PINNED_ROLES = ROLES_BEFORE_BAND_6_WAVE_1B | ROLES_G1 | ROLES_G2 | ROLES_G3 | ROLES_G4 | set().union(*ROLES_WAVE_2.values())


def outside_the_windows(slots):
    """What breaks band 6 wave 2's windows: a group's slot not wholly inside one of its own windows, any other slot
    reaching into a window, a window outside the band or over another."""
    ceiling = min(emu.STACK_TOP - emu.STACK_SCRATCH, gemdos.FRAME_AT)
    windows = sorted((lo, hi, group) for group, spans in WAVE_2_WINDOWS.items() for lo, hi in spans)
    faults = [f"{group}'s window {lo:#x}..{hi:#x} is outside the band" for lo, hi, group in windows
              if not emu.STACK_GUARD_LO <= lo < hi <= ceiling]
    faults += [f"{group}'s window runs into {next_group}'s" for (_lo, hi, group), (next_lo, _hi, next_group)
               in zip(windows, windows[1:]) if hi > next_lo]
    owner = {role: group for group, roles in ROLES_WAVE_2.items() for role in roles}
    for role, (at, width) in slots.items():
        inside = [group for lo, hi, group in windows if lo <= at and at + width <= hi]
        touches = [group for lo, hi, group in windows if at < hi and lo < at + width]
        if role in owner and inside != [owner[role]]:
            faults.append(f"{role} is not inside {owner[role]}'s window")
        elif role not in owner and touches:
            faults.append(f"{role} reaches into {touches[0]}'s window")
    return faults


def test_every_host_slot_is_inside_the_dropped_band_and_apart():
    slots = host_slots(CONSTANTS)
    assert set(slots) == PINNED_ROLES
    assert not misplaced(slots)
    assert not outside_the_windows(slots)


def test_the_windows_refuse_a_slot_of_another_group_or_out_of_its_own(monkeypatch):
    """...and the windows' check is not vacuous: a slot of wave 1b moved into G3's window, and a G1 role whose slot lies
    in G4's, are each refused by name."""
    slots = host_slots(CONSTANTS)
    (g3_lo, _g3_hi), (g4_lo, _g4_hi) = WAVE_2_WINDOWS["G3"][0], WAVE_2_WINDOWS["G4"][0]
    assert outside_the_windows({**slots, "FRAME_WORD": (g3_lo, slots["FRAME_WORD"][1])}) == ["FRAME_WORD reaches into G3's window"]
    monkeypatch.setitem(ROLES_WAVE_2, "G1", ROLES_WAVE_2["G1"] | {"A_PHANTOM_ROLE"})
    assert outside_the_windows({**slots, "A_PHANTOM_ROLE": (g4_lo, 2)}) == ["A_PHANTOM_ROLE is not inside G1's window"]


def test_the_check_refuses_a_slot_moved_onto_another():
    """...and the check is not vacuous: the frame word moved onto the delete mark, or out of the band,
    is refused by name."""
    slots = host_slots(CONSTANTS)
    mark_at, _width = slots["DELETE_MARK"]
    word_bytes = slots["FRAME_WORD"][1]
    assert misplaced({**slots, "FRAME_WORD": (mark_at, word_bytes)})
    assert misplaced({**slots, "FRAME_WORD": (gemdos.FRAME_AT, word_bytes)})
