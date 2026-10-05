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


def test_every_host_slot_is_inside_the_dropped_band_and_apart():
    slots = host_slots(CONSTANTS)
    assert set(slots) == {"SEARCH_PATTERN", "WALK_NAME", "WALK_CURSOR", "DELETE_MARK", "ATTRIBUTE", "FRAME_WORD",
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
                          "AES_FS_INPUT_FRAME", "AES_PD_MATCH_NAME", "AES_AP_FIND_NAME"}
    assert not misplaced(slots)


def test_the_check_refuses_a_slot_moved_onto_another():
    """...and the check is not vacuous: the frame word moved onto the delete mark, or out of the band,
    is refused by name."""
    slots = host_slots(CONSTANTS)
    mark_at, _width = slots["DELETE_MARK"]
    word_bytes = slots["FRAME_WORD"][1]
    assert misplaced({**slots, "FRAME_WORD": (mark_at, word_bytes)})
    assert misplaced({**slots, "FRAME_WORD": (gemdos.FRAME_AT, word_bytes)})
