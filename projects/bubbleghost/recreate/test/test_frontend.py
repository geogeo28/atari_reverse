"""Differential tests for the front end (src/frontend.c).

WHAT IS HERE. The GEM binding itself — `vdi_call` @ 0x168d4, `gem_aes` @ 0x149b6 and the sixteen
entry points that fill their parameter blocks (twelve VDI, four AES) — plus the boot-time setup
`init_gem_and_screens` @ 0x10118, the four `vro_cpyfm` routines that are the game's sprite protocol,
the room composer, the presentation screen, the four file loaders and the hall of fame.

THE TRAP IS THE POINT, and it is what makes these cases different from every other battery in this
project. The oracle really executes `trap #2` and `shim.c` services it out of the kit's GEM model;
the candidate calls that same model, over the same parameter block, at the same address in the same
image (TRAP_MODEL.md, phases 11-13). So what a case has to get wrong for the diff to notice is the
BLOCK: an opcode in the wrong `contrl` slot, an intin count one short, a lent array pointer never
put back. Every one of those is image state, and the four things the model does not put in the
image — `graf_mouse`'s mode, and the console/IKBD/cursor events — are compared as the ordered OS
event ledger `harness.differential` carries anyway.

TWO INPUTS EVERY CASE DECLARES, both of them `docs/agent-playbook.md` §5's "a parameter":

* THE CALLER'S A1/A2. Both trampolines park them, and nothing in the routine computes them, so the
  case hands the same pair to the oracle (in `regs`) and to the candidate (as glue arguments).
* AN OPEN WORKSTATION. `harness.vdi_state(screen=...)` stages the attributes `v_opnvwk` would have
  installed, and names a SCREEN inside `test/abi.py`'s scratch map — because the model's default is
  `OS_SCREEN_BASE` = 0x8000, where a 32,000-byte clear would run over nothing this battery staged
  and prove nothing about where the game really draws (STATUS.md, "Model gaps").

...and one the parameter block needs: `vdi_pblock`'s five array pointers are ZERO in the loaded
image. Only `v_opnvwk`'s tail ever writes four of them, so every case entered below it stages them,
exactly as the running program would have left them.
"""
import ctypes
import pathlib
import random

import pytest

import abi
import emu
import harness
from harness import report

REC = pathlib.Path(__file__).resolve().parents[1]

# ---- entry addresses (Ghidra == run-time; see README.md, "The image model") --------------------
ENTRY_VDI_CALL = 0x168d4
ENTRY_VDI_SET_SRC_MFDB = 0x16890
ENTRY_VDI_SET_DST_MFDB = 0x168b2
ENTRY_VST_HEIGHT = 0x168fc
ENTRY_VST_COLOR = 0x16948
ENTRY_VSF_COLOR = 0x16974
ENTRY_V_OPNVWK = 0x169a0
ENTRY_V_CLRWK = 0x16a06
ENTRY_VQ_MOUSE = 0x16a26
ENTRY_VQ_KEY_S = 0x16a5e
ENTRY_V_GTEXT = 0x16a86
ENTRY_VR_RECFL = 0x16ae2
ENTRY_VRO_CPYFM = 0x16b12
ENTRY_GEM_AES = 0x149b6
ENTRY_AES_CRYSIF = 0x14b2e
ENTRY_APPL_INIT = 0x14b94
ENTRY_GRAF_HANDLE = 0x14be8
ENTRY_GRAF_MOUSE = 0x14c1e
ENTRY_INIT_GEM_AND_SCREENS = 0x10118
ENTRY_BUILD_SPRITE_BANK = 0x132ec
ENTRY_SAVE_SPRITE_BACKGROUNDS = 0x1342e
ENTRY_DRAW_SPRITES = 0x134f6
ENTRY_RESTORE_SPRITE_BACKGROUNDS = 0x135d2
ENTRY_SHOW_PRESENTATION = 0x10eb8
ENTRY_LOAD_DEMO = 0x10dea
ENTRY_LOAD_PRESENTATION = 0x10e44
ENTRY_LOAD_LEVEL_PICTURES = 0x1396c
ENTRY_LOAD_HISCORES = 0x121a0
ENTRY_DRAW_ROOM_TO_STAGE = 0x13a08
ENTRY_DRAW_ROOM_TO_STAGE_CELL = 0x13a20   # the `pea` that opens the loop body's `vq_mouse`...
STOP_DRAW_ROOM_TO_STAGE_CELL = 0x13afa    # ...to the `addq.w #1,-2(a6)` that ends the body
ENTRY_DRAW_HALL_OF_FAME = 0x11dbc
ENTRY_HISCORE_INSERT_AND_SAVE = 0x11f84
ENTRY_SAVE_HISCORES = 0x1207a
STOP_SAVE_HISCORES_PROLOGUE = 0x120ce   # the `clr.w -(a7)` that opens c_creat's push
ENTRY_HISCORE_SUBMIT_PLAYERS = 0x11d6e

# The front end's state machine. `title_menu_loop` RETURNS on its two game-starting arms, so those
# are whole runs; every other region of it and every region of `game_top_loop` is a mid-entry slice.
ENTRY_TITLE_MENU_OPEN = 0x115d6         # the routine, down to its first blocking read
STOP_TITLE_MENU_OPEN = 0x116c4
ENTRY_MENU_DRAW = 0x115de               # ...and the redraw loop's own re-entry into it
STOP_MENU_DRAW = 0x116c4
ENTRY_MENU_READ_KEY = 0x116c4           # the `move.w #$8,-(a7)` that opens Cnecin
STOP_MENU_READ_KEY = 0x11700            # ...to the first of the four dispatch compares
ENTRY_MENU_ASK_PLAYER_COUNT = 0x11708
STOP_MENU_ASK_PLAYER_COUNT = 0x11774
ENTRY_MENU_READ_PLAYER_COUNT = 0x11774
STOP_MENU_PLAYER_COUNT_CHOSEN = 0x117cc # a count was chosen and the arm ends...
STOP_MENU_PLAYER_COUNT_AGAIN = 0x1175a  # ...or it was not, and the ask goes round again
ENTRY_MENU_ASK_PRACTICE_LEVEL = 0x117de
STOP_MENU_ASK_PRACTICE_LEVEL = 0x1183e
ENTRY_MENU_READ_LEVEL_TENS = 0x1183e
STOP_MENU_READ_LEVEL_TENS = 0x1186c
ENTRY_MENU_READ_LEVEL_UNITS = 0x1186c
STOP_MENU_READ_LEVEL_UNITS = 0x1191e
ENTRY_DEMO_RECORD = 0x11992             # the `movea.l demo_cursor,a0` that opens one record...
STOP_DEMO_RECORD = 0x11acc              # ...to the `cmpi.w #$1,mouse_buttons` that ends it
STOP_DEMO_REPLAY = 0x11ae6              # ...and the `Random()` push that follows the whole loop
ENTRY_MENU_ATTRACT_SEQUENCE = 0x11930
STOP_MENU_ATTRACT_SEQUENCE = 0x11ae6    # ...to the `Random()` push that opens the slideshow
ENTRY_MENU_ATTRACT_SLIDESHOW = 0x11ae6
STOP_MENU_ATTRACT_SLIDESHOW = 0x11c34
ENTRY_MENU_ATTRACT_SLIDESHOW_ROOM = 0x11b30   # one room of it, which is all one run can afford
STOP_MENU_ATTRACT_SLIDESHOW_ROOM = 0x11c1c
ENTRY_MENU_ATTRACT_TITLE = 0x11c34
STOP_MENU_ATTRACT_TITLE = 0x11ca8       # the `bra.w` into the redraw test
ENTRY_MENU_HALL_OF_FAME = 0x11cba
STOP_MENU_HALL_OF_FAME = 0x11d60        # the redraw test itself
ENTRY_GAME_TOP_BOOT = 0x101e6
STOP_GAME_TOP_BOOT = 0x10232            # the `jsr play_voice`, which the model cannot run
ENTRY_GAME_TOP_BOOT_TAIL = 0x10236
STOP_GAME_TOP_BOOT_TAIL = 0x1024e       # the push that opens `c_free(voi_buffer)`
ENTRY_GAME_TOP_BOOT_ARM = 0x10258
STOP_GAME_TOP_BOOT_ARM = 0x1027e
ENTRY_GAME_NEW_GAME = 0x1027e
STOP_GAME_NEW_GAME = 0x102b0            # the `jsr title_menu_loop`
ENTRY_GAME_TURN_INIT = 0x102b4
STOP_GAME_TURN_INIT = 0x1037a
ENTRY_GAME_PLAYER_CHANGE = 0x1037a
STOP_GAME_PLAYER_CHANGE = 0x105e0
ENTRY_GAME_ROOM_SETUP = 0x105e0
STOP_GAME_ROOM_SETUP = 0x1078a          # the `bra.w` into the room loop's first test
ENTRY_GAME_ROOM_FRAME_TAIL = 0x10792    # where `game_frame_update` returns
STOP_GAME_ROOM_FRAME_TAIL = 0x108d2
ENTRY_GAME_ENDING_SEQUENCE = 0x108ec
STOP_GAME_ENDING_SEQUENCE = 0x10ce0
ENTRY_GAME_ROOM_EXIT = 0x10af8
STOP_GAME_ROOM_EXIT = 0x10ce0           # the two end-of-room paths rejoin here
ENTRY_GAME_END_OF_TURN = 0x10ce0
STOP_GAME_END_OF_TURN = 0x10d34   # the room loop's own `while (either player is in)`
ENTRY_GAME_OVER_CARD = 0x10d44
STOP_GAME_OVER_CARD = 0x1027e           # ...and back to the top of the game loop

# ---- mirrors of include/frontend.h -------------------------------------------------------------
A_VDI_PBLOCK = 0x1e8ca
LONGWORD_SLOT_BYTES = 4        # one parameter-block slot / one pointer-table entry
A_VDI_CONTRL = 0x236f0
A_VDI_INTIN = 0x235f0
A_VDI_PTSIN = 0x234f0
A_VDI_INTOUT = 0x233f0
A_VDI_PTSOUT = 0x232f0
A_VDI_HANDLE = 0x232ee
A_VDI_WORK_IN = 0x2377a
A_VDI_WORK_OUT = 0x23708
VDI_WORK_OUT_WORDS = 57        # 45 intout entries then 6 ptsout PAIRS (`include/frontend.h`)
AES_CONTROL_TABLE = 0x149d2
A_AES_AP_ID = 0x1f0bc
A_AES_PBLOCK = 0x1f0be
A_AES_P_CONTROL = 0x1f0c2
A_AES_ADDR_OUT = 0x1f0da
A_AES_ADDR_IN = 0x1f0e2
A_AES_INT_OUT = 0x1f0ee
A_AES_INT_IN = 0x1f0fe
A_AES_GLOBAL = 0x1f120
A_AES_CONTROL = 0x1f140
AES_TABLE_FIRST_OPCODE = 10
AES_TABLE_STRIDE = 3
AES_CONTROL_COUNT_SLOTS = 4
A_SCREEN_REZ = 0x23146
A_SUPER_ARG = 0x22f6c
A_SUPER_SAVED_SSP = 0x22f70
A_CONTERM_ADDR_W = 0x22f6a
A_CONTERM_ADDR_L = 0x22f66
CONTERM_ADDRESS = 0x484
WORK_IN_ONES = 10
WORK_IN_COORD_RASTER = 2
XBIOS_GETREZ_LOW_RES = 0
A_PRE_PALETTE = 0x23126
DAT_BANK_PRE = 6
PALETTE_BYTES = 0x20
A_HALL_SCORES = 0x22f8c
A_HALL_ROOMS = 0x22f78
A_GHOST_SPRITE = 0x23028
A_BUBBLE_SPRITE = 0x22ff4
A_GHOST_BG = 0x230e8
A_BUBBLE_BG = 0x230e4
VDI_MODE_S_ONLY = 3
VDI_MODE_S_OR_D = 7
A_DEMO_BASE = 0x23160
A_DEMO_CURSOR = 0x23164
A_NAME_GHOST_DEM = 0x24fe0
A_NAME_GHOST_PRE = 0x24fec
A_NAME_GHOST_SCR = 0x25176
A_NAME_GHOST_SCR_CREAT = 0x25156
A_NAME_GHOST_DAT = 0x251b2
DEMO_FILE_BYTES = 0x1770
PICTURE_BYTES = 0x7800
DAT_BANKS_FROM_FILE = 6
HISCORE_SLOTS = 5
HISCORE_SCORE_DIGITS = 6
HISCORE_ROOM_DIGITS = 2
A_HISCORE_CANDIDATE = 0x22fa0
A_HISCORE_PENDING_SCORE = 0x2317e
A_HISCORE_PENDING_ROOM = 0x23192
A_PLAYER_COUNT = 0x2316c
A_P2_SCORE = 0x23182
A_P1_SCORE = 0x23186
A_P2_MAX_ROOM = 0x23194
A_P1_MAX_ROOM = 0x23196
HALL_BACKDROP_ROOM = 0
A_TEXT_SCORE_LABELS = 0x2511c
TEXT_SCORE_LABEL_BYTES = 10
A_TEXT_HALL = 0x2514e

# ---- ...and the state machine's own (include/frontend.h) ---------------------------------------
A_PRACTICE_MODE = 0x2315c
A_PRACTICE_GRID_ROW = 0x23158
A_PRACTICE_GRID_COL = 0x2315a
A_P2_TURN = 0x23168
A_AMBIENT_SFX_COUNTDOWN = 0x22fc0
DEMO_RECORD_BYTES = 6
TOP_BONUS_BAR_FULL = 0x13e
TOP_BONUS_BAR_FLOOR = 0x23

# ---- mirrors of include/gameplay.h and include/sound.h ------------------------------------------
A_P1_TURN = 0x2316a
A_SHOW_PLAYER_CHANGE = 0x231a0
A_P1_PLAYING = 0x2319a
A_P2_PLAYING = 0x23198
A_P1_LIVES = 0x2318e
A_P2_LIVES = 0x2318a
A_P1_BONUS_BAR = 0x2317c
A_P2_BONUS_BAR = 0x2317a
A_P1_GRID_COL = 0x23178
A_P2_GRID_COL = 0x23176
A_P1_GRID_ROW = 0x23174
A_P2_GRID_ROW = 0x23172
A_P1_DEATHS_IN_ROOM = 0x2319e
A_P2_DEATHS_IN_ROOM = 0x2319c
A_P1_ENTRY_DIR = 0x231a4
A_P2_ENTRY_DIR = 0x231a2
A_GRID_ROW = 0x23154
A_GRID_COL = 0x23156
A_ENTRY_DIR = 0x23152
A_IN_ROOM = 0x23150
A_DEATHS_IN_ROOM = 0x22f62
A_BONUS_TICK = 0x22f76
A_BONUS_BAR = 0x22fb4
A_LIVES = 0x22fa8
A_HI_SCORE = 0x22fac
A_SOUND_ENABLED = 0x2315e
A_LOA_IMAGE = 0x237a0
A_NAME_GHOST_LOA = 0x22f58
A_NAME_GHOST_VOI = 0x22f4e
A_SND_VOICE = 0x22daa
SND_VOICE_BYTES = 0x8c
SND_VOICES = 3
SND_VC_PRIORITY = 0x72
TOS_VEC_TRAP9 = 0xa4
SND_TRAP9_HANDLER_ENTRY = 0x14950

# ---- mirrors of include/blit.h and include/gameplay.h ------------------------------------------
A_SCREEN_PHYS = 0x23148
A_SCREEN_BACK = 0x2314c
A_DAT_BANK = 0x2312a
A_MFDB_SRC = 0x23100
A_MFDB_DST = 0x230ec
SCREEN_BYTES = 32000
A_GHOST_X = 0x22ff2
A_GHOST_Y = 0x22ff0
A_GHOST_TILE = 0x22fea
A_BUBBLE_X = 0x22fee
A_BUBBLE_Y = 0x22fec
A_BUBBLE_FRAME = 0x22fe8
A_SCORE = 0x22fb0
A_MAX_ROOM_REACHED = 0x22f74
TILE_PIXELS = 32
TILE_BYTES = 0x200
ROOM_BYTES = 0x6400
ROOM_TILE_ROWS = 5
ROOM_TILE_COLS = 10
# `include/frontend.h` derives this from TILE_PIXELS rather than naming 31 again; the scraper
# `test_constants.py` uses reads integer literals only, so it is derived here the same way.
SPRITE_EXTENT = TILE_PIXELS - 1
A_ROOM_NUMBER = 0x23120

# How the sixty grabbed cells are split between the two pointer tables (`include/frontend.h`).
GHOST_CELLS = 47
BUBBLE_CELLS = 13

# The two output arrays a boot-time case seeds so that the model's writes into them are visible.
# BOTH ARE SEEDED WITH THE DEFAULT GUARD, like every other span in this file. The sixteen bytes
# either side are other slots of the same two parameter blocks — `work_in` above `work_out`,
# `addr_in`/`int_in` around `int_out` — and every case that means to set one of those stages it as a
# later layer, so noise there is an input both sides read alike and is what would catch a fill one
# word too far.
VDI_WORK_OUT_SPAN = (A_VDI_WORK_OUT, A_VDI_WORK_OUT + 2 * VDI_WORK_OUT_WORDS)
AES_INT_OUT_SPAN = (A_AES_INT_OUT, A_AES_INT_OUT + 0x10)

# ---- the kit's own model constants a case names -------------------------------------------------
# Mirrored here rather than imported so a change on either side fails by name; `harness` re-exports
# the memory map, and the two workstation answers are pinned against a real oracle run below.
OS_VDI_HANDLE = 1
OS_AES_AP_ID = 0
OS_SCREEN_MAX_X = 319
OS_SCREEN_MAX_Y = 199
OS_SCREEN_COLOURS = 16
OS_VDI_WORK_OUT_INTS = 45
VDI_WORK_OUT_COLOURS = 13   # the work_out entry holding how many colours the device shows
AES_M_OFF = 256
AES_M_ON = 257

# ---- where a case stages the world -------------------------------------------------------------
# THE MAP KEEPS THE MACHINE'S OWN RELATIONSHIPS, because three routines here depend on them: the
# staging area a room is composed into is one room BELOW the work buffer, and the visible screen is
# one screen above it. So the three are laid out contiguously from the scratch map's base, in that
# order, and the small blocks follow.
#
# The VDI's own screen — what an MFDB whose `fd_addr` is 0 means — is declared to be the WORK
# buffer, which is where the running game points its logical base (`Setscreen(log = screen_back)`).
STAGE = abi.SCRATCH                     # screen_back - ROOM_BYTES: where a room is composed
WORK = STAGE + ROOM_BYTES               # screen_back, the work buffer the VDI draws into
PHYS = WORK + SCREEN_BYTES              # screen_phys, the visible screen
OUT = PHYS + SCREEN_BYTES               # out-parameter words, one per line below
SPRITE_A = OUT + 0x40                   # two 32x32x4 cells, for the MFDB cases
SPRITE_B = SPRITE_A + TILE_BYTES
TEXT = SPRITE_B + TILE_BYTES     # staged strings
PXY = TEXT + 0x80                       # a caller's own eight-word rectangle
MFDB_A = PXY + 0x20                     # ...and a caller's own MFDBs
MFDB_B = MFDB_A + 0x20
# The two rasters the sprite MFDBs' `fd_addr` holds ON ENTRY to the three per-frame routines: junk,
# not zero. See SPRITE_MFDB_POKES.
MFDB_JUNK_SRC = MFDB_B + 0x20
MFDB_JUNK_DST = MFDB_JUNK_SRC + TILE_BYTES
SPRITE_TABLE_BASE = MFDB_JUNK_DST + TILE_BYTES   # the 62 cells `build_sprite_bank` allocates
SCRATCH_TOP = SPRITE_TABLE_BASE + (GHOST_CELLS + BUBBLE_CELLS + 2) * TILE_BYTES

# The four out-parameter words `vst_height` and `graf_handle` write through, spelt separately so a
# case can tell a swapped pair apart.
OUT_SLOTS = tuple(OUT + 2 * index for index in range(4))

# An entered routine's own A6. `emu.run` forces A7 to `emu.STACK_TOP` and writes the sentinel return
# address there, so a routine that opens with `link a6,#-n` — which is every routine here that takes
# a `frame` argument — leaves A6 one longword below. Its locals are inside the stack-guard band the
# differential drops, which is why the frame is an argument rather than something the core can name.
FRAME_A6 = emu.STACK_TOP - 4

# `draw_room_to_stage`'s OWN frame, for the per-cell slice, and it sits ABOVE `emu.STACK_TOP` rather
# than a longword below it. The slice is entered at the top of the loop BODY, whose first four
# instructions push `vq_mouse`'s arguments — and the harness forces A7 to STACK_TOP, so a frame at
# `STACK_TOP - 4` would have those pushes land on the routine's own `-4(a6)`/`-2(a6)`. The real
# routine's `link a6,#$ffe4` puts A7 twenty-eight bytes BELOW A6; this reproduces that relationship
# from the other side. LINK_BYTES is comfortably more than the frame is, and the whole of it lies in
# the band the differential drops as stack (`abi.stack_args` pokes into the same band).
DRAW_ROOM_LINK_BYTES = 0x20      # `link a6,#$ffe4` reserves 28; rounded up to a longword multiple
FRAME_DRAW_ROOM_A6 = emu.STACK_TOP + DRAW_ROOM_LINK_BYTES
# ...and its two loop variables, which a mid-loop entry stages instead of running to.
FRAME_TILE_ROW = FRAME_DRAW_ROOM_A6 - 4    # the routine's -4(a6)
FRAME_TILE_COL = FRAME_DRAW_ROOM_A6 - 2    # ...and its -2(a6)

# ...and where `save_hiscores`' OWN A6 lands, per entry point. It is reached through up to two
# callers, and each `link a6,#-n` costs the longword it pushes plus `n`, with a `jsr`'s return
# address between them. Derived rather than measured so a `link` size cannot drift from it.
LINK_SAVE_HISCORES = 12          # `link a6,#$fff4` @ 0x1207a
LINK_INSERT_AND_SAVE = 10        # `link a6,#$fff6` @ 0x11f84
LINK_SUBMIT_PLAYERS = 0          # `link a6,#$0`    @ 0x11d6e
RETURN_ADDRESS_BYTES = 4
SAVED_A6_BYTES = 4


def _callee_frame(*link_sizes):
    """The A6 a chain of `link a6,#-n` routines leaves, entered with A7 = `emu.STACK_TOP`."""
    frame = emu.STACK_TOP
    for depth, size in enumerate(link_sizes):
        if depth:
            frame -= RETURN_ADDRESS_BYTES
        frame -= SAVED_A6_BYTES
        if depth + 1 < len(link_sizes):
            frame -= size
    return frame


FRAME_SAVE_HISCORES = _callee_frame(LINK_SAVE_HISCORES)
FRAME_SAVE_FROM_INSERT = _callee_frame(LINK_INSERT_AND_SAVE, LINK_SAVE_HISCORES)
FRAME_SAVE_FROM_SUBMIT = _callee_frame(LINK_SUBMIT_PLAYERS, LINK_INSERT_AND_SAVE,
                                       LINK_SAVE_HISCORES)

# The caller's A1/A2, which the two trampolines park. Distinctive and odd-looking on purpose: a
# reconstruction that filed a zero, or filed them in the wrong slots, differs in four bytes.
CALLER_A1 = 0x00b0c0de
CALLER_A2 = 0x00d0e0f0

GHOST_DAT = (REC.parent / "bin" / "GHOST.DAT").read_bytes()
GHOST_PRE = (REC.parent / "bin" / "GHOST.PRE").read_bytes()
GHOST_DEM = (REC.parent / "bin" / "GHOST.DEM").read_bytes()

_u8p = ctypes.POINTER(ctypes.c_uint8)


def _bind(name, argument_count, returns=None):
    symbol = getattr(harness._lib, name)
    symbol.argtypes = [_u8p] + [ctypes.c_uint32] * argument_count
    symbol.restype = returns


for _name, _args in (("g_vdi_call", 2), ("g_gem_aes", 3), ("g_vdi_set_src_mfdb", 1),
                     ("g_vdi_set_dst_mfdb", 1), ("g_vst_height", 8), ("g_v_opnvwk", 5),
                     ("g_v_clrwk", 3), ("g_vq_mouse", 6), ("g_vq_key_s", 4), ("g_v_gtext", 6),
                     ("g_vr_recfl", 4), ("g_vro_cpyfm", 7), ("g_graf_mouse", 4),
                     ("g_init_gem_and_screens", 3), ("g_build_sprite_bank", 2),
                     ("g_build_sprite_bank_grab_cells", 2), ("g_save_sprite_backgrounds", 2),
                     ("g_draw_sprites", 2), ("g_restore_sprite_backgrounds", 2),
                     ("g_show_presentation", 2), ("g_load_demo", 2), ("g_load_presentation", 2),
                     ("g_load_level_pictures", 2), ("g_load_hiscores", 3),
                     ("g_draw_room_to_stage", 2), ("g_draw_hall_of_fame", 3),
                     ("g_save_hiscores", 3), ("g_save_hiscores_prologue", 3),
                     ("g_hiscore_insert_and_save", 3),
                     ("g_hiscore_submit_players", 3)):
    _bind(_name, _args)
for _name, _args in (("g_vst_color", 4), ("g_vsf_color", 4), ("g_aes_crysif", 3),
                     ("g_appl_init", 2), ("g_graf_handle", 6)):
    _bind(_name, _args, ctypes.c_int32)
# ...and the one that answers an ADDRESS: the A2 one loop cell leaves for the next cell's poll.
_bind("g_draw_room_to_stage_cell", 4, ctypes.c_uint32)


# ================================================================================ staging helpers

def _pblock_pokes():
    """The five VDI array pointers and the AES's seven, as an open workstation leaves them.

    The loaded image holds all of them as zeroes: `v_opnvwk`'s tail is the only thing that ever
    writes four of the VDI's, and `appl_init` the only thing that writes the AES's. So a case
    entered below either one stages what that call would have left, and the two cases that DO run
    them stage nothing and watch them appear.
    """
    return {
        A_VDI_PBLOCK: b"".join(abi.long(array) for array in
                               (A_VDI_CONTRL, A_VDI_INTIN, A_VDI_PTSIN, A_VDI_INTOUT, A_VDI_PTSOUT)),
        A_AES_PBLOCK: abi.long(A_AES_P_CONTROL),
        A_AES_P_CONTROL: b"".join(abi.long(array) for array in
                                  (A_AES_CONTROL, A_AES_GLOBAL, A_AES_INT_IN, A_AES_INT_OUT,
                                   A_AES_ADDR_IN, A_AES_ADDR_OUT)),
    }


def _workstation_pokes(screen=WORK, **attributes):
    """An open workstation drawing into `screen`, plus the handle the game keeps its own copy of."""
    return abi.merge_pokes(harness.vdi_state(screen=screen, **attributes),
                           {A_VDI_HANDLE: abi.word(OS_VDI_HANDLE)})


def _world(seed, spans=(), extra=None, screen=WORK, **attributes):
    """`abi.stage_world` with this battery's own layers: the two parameter blocks and an open
    workstation, then the case's own bytes."""
    return abi.stage_world(seed, spans, _pblock_pokes(),
                           _workstation_pokes(screen, **attributes), extra or {})


def _run(entry, glue, pokes, regs=None, **kwargs):
    """One differential, entered with this program's `a4` and the caller's A1/A2."""
    entry_regs = {"a1": CALLER_A1, "a2": CALLER_A2}
    entry_regs.update(regs or {})
    return abi.run_with_a4(entry, glue, pokes=pokes, regs=entry_regs, **kwargs)


def _mfdb(address, width=TILE_PIXELS, height=TILE_PIXELS, planes=4):
    """A GEM Memory Form Definition Block over a raster the model can address."""
    return abi.word(address >> 16) + abi.word(address) + abi.word(width) + abi.word(height) \
        + abi.word((width + 15) // 16) + abi.word(0) + abi.word(planes) + abi.word(0) * 3


# `abi.read_word` / `abi.read_long` are the decoders every battery shares — the other half of
# `abi.word` / `abi.long`. Aliased here so the cases below read as they always did.
_word = abi.read_word
_long = abi.read_long


# ======================================================================== the VDI trap and its glue

def test_vdi_call_files_the_registers_and_dispatches():
    """`vdi_call` entered directly: it parks A1/A2, re-points `contrl`, and traps.

    The opcode is staged rather than passed — this routine takes no arguments at all — and
    `vq_key_s`'s is used because its whole effect is one `intout` word, so the case sees the
    dispatch happen without any drawing in the way.
    """
    pokes = abi.merge_pokes(
        _workstation_pokes(),
        # every pblock slot BUT `contrl`, which is what this routine files on every call: staging it
        # would make the store unobservable, since it would already hold what the routine writes.
        {A_VDI_PBLOCK + LONGWORD_SLOT_BYTES: b"".join(
            abi.long(array) for array in (A_VDI_INTIN, A_VDI_PTSIN, A_VDI_INTOUT, A_VDI_PTSOUT))},
        {A_VDI_CONTRL: abi.word(128) + abi.word(0) + abi.word(0) + abi.word(0)},
        harness.key_shift(0x0f))
    diffs, _ = _run(ENTRY_VDI_CALL, lambda lib, buf: lib.g_vdi_call(buf, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("mfdb", (0, 0x1234, WORK, 0xfffefffe, 0x80000000))
@pytest.mark.parametrize("half", ("src", "dst"))
def test_vdi_set_mfdb_splits_the_pointer(mfdb, half):
    """The pointer lands in `contrl[7..8]` or `contrl[9..10]`, high word first.

    0x80000000 and 0xfffefffe are here because the original splits with `asr.l`, an ARITHMETIC
    shift: the sign fill it produces is dropped by the `move.w` that follows, so a reconstruction
    using a logical shift must agree — and only a pointer with the top bit set can show it does.
    """
    entry = ENTRY_VDI_SET_SRC_MFDB if half == "src" else ENTRY_VDI_SET_DST_MFDB
    symbol = "g_vdi_set_src_mfdb" if half == "src" else "g_vdi_set_dst_mfdb"
    pokes = _world(0x1689, extra=abi.stack_args((4, mfdb)))
    diffs, _ = _run(entry, lambda lib, buf: getattr(lib, symbol)(buf, mfdb), pokes)
    assert not diffs, f"{half} {mfdb:#x}\n{report(diffs)}"


# ============================================================================== the VDI entry points

@pytest.mark.parametrize("height", (4, 6, 0, -1, 0x7fff))
def test_vst_height(height):
    """VDI 12: one ptsin pair in, four ptsout words out through four separate pointers."""
    pokes = _world(0x1690 + (height & 0xff), spans=((OUT, OUT + 0x40),),
                   extra=abi.stack_args((2, OS_VDI_HANDLE), (2, height), (4, OUT_SLOTS[0]),
                                        (4, OUT_SLOTS[1]), (4, OUT_SLOTS[2]), (4, OUT_SLOTS[3])))
    diffs, _ = _run(ENTRY_VST_HEIGHT,
                    lambda lib, buf: lib.g_vst_height(buf, OS_VDI_HANDLE, height & 0xffff,
                                                      *OUT_SLOTS, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"height {height}\n{report(diffs)}"


@pytest.mark.parametrize("index", (0, 1, 5, 11, 13, 15, 16, -1, 0x1234))
@pytest.mark.parametrize("which", ("vst", "vsf"))
def test_set_colour(index, which):
    """VDI 22 / 25: the pen the model clamps to 0..15, echoed back through `intout[0]`.

    The out-of-range values are the clamp's two ends, which are the model's own behaviour and part
    of what a reconstruction must not second-guess — it stores what the call answers, not what it
    asked for.
    """
    entry = ENTRY_VST_COLOR if which == "vst" else ENTRY_VSF_COLOR
    symbol = "g_vst_color" if which == "vst" else "g_vsf_color"
    pokes = _world(0x1694 + (index & 0xff),
                   extra=abi.stack_args((2, OS_VDI_HANDLE), (2, index)))
    diffs, info = _run(entry,
                       lambda lib, buf: getattr(lib, symbol)(buf, OS_VDI_HANDLE, index & 0xffff,
                                                             CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"{which}_color {index}\n{report(diffs)}"
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff, (
        f"{which}_color({index}) answered {info['ret'] & 0xffff:#x}, "
        f"the original {info['regs']['d0'] & 0xffff:#x}")


def _work_in(values):
    return {A_VDI_WORK_IN: b"".join(abi.word(v) for v in values)}


GAME_WORK_IN = (1,) * WORK_IN_ONES + (WORK_IN_COORD_RASTER,)
OTHER_WORK_IN = (2, 3, 4, 5, 6, 7, 13, 1, 2, 11, WORK_IN_COORD_RASTER)


@pytest.mark.parametrize("work_in", (GAME_WORK_IN, OTHER_WORK_IN))
def test_v_opnvwk_lends_and_restores_the_arrays(work_in):
    """VDI 100, the one call that lends the VDI three of the CALLER's own arrays.

    Two `work_in` arrays, because the attributes a workstation opens with come out of that array:
    a swapped slot installs a different text or fill colour, which every later drawing call reads.
    `work_out` is seeded with noise first, so the 42 entries the model ZEROES are visible; without
    that a reconstruction which never pointed `intout` at the caller's array would still match.

    The parameter block is NOT staged here — this case starts from the loaded image's zeroes and
    watches all four pointers appear, which is what the running program does at start-up.
    """
    pokes = abi.stage_world(
        0x169a, (VDI_WORK_OUT_SPAN,),
        harness.vdi_state(screen=WORK), _work_in(work_in),
        {A_VDI_HANDLE: abi.word(0)},           # the BSS zero the game really passes in
        abi.stack_args((4, A_VDI_WORK_IN), (4, A_VDI_HANDLE), (4, A_VDI_WORK_OUT)))
    diffs, _ = _run(ENTRY_V_OPNVWK,
                    lambda lib, buf: lib.g_v_opnvwk(buf, A_VDI_WORK_IN, A_VDI_HANDLE,
                                                    A_VDI_WORK_OUT, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, report(diffs)


def test_v_opnvwk_answers_the_workstation_the_model_declares():
    """...and the answer itself, so the mirrors above are pinned against a real oracle run.

    The three `work_out` fields the model fills in and the handle it reports are what every case in
    this file assumes; reading them off the oracle is what stops those assumptions being beliefs.
    """
    pokes = abi.merge_pokes(harness.vdi_state(screen=WORK), _work_in(GAME_WORK_IN),
                            {A_VDI_HANDLE: abi.word(0)},
                            abi.stack_args((4, A_VDI_WORK_IN), (4, A_VDI_HANDLE),
                                           (4, A_VDI_WORK_OUT)))
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_V_OPNVWK,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})

    assert _word(final, A_VDI_HANDLE) == OS_VDI_HANDLE
    assert _word(final, A_VDI_WORK_OUT) == OS_SCREEN_MAX_X
    assert _word(final, A_VDI_WORK_OUT + 2) == OS_SCREEN_MAX_Y
    assert _word(final, A_VDI_WORK_OUT + 2 * VDI_WORK_OUT_COLOURS) == OS_SCREEN_COLOURS
    # ...and the 42 entries the model has nothing to say about really are ZEROED rather than left,
    # which is what a caller walking `contrl[4]`'s count would otherwise read back as attributes.
    reported = [_word(final, A_VDI_WORK_OUT + 2 * index) for index in range(OS_VDI_WORK_OUT_INTS)]
    for index, value in enumerate(reported):
        if index in (0, 1, VDI_WORK_OUT_COLOURS):
            continue
        assert value == 0, f"work_out[{index}] = {value:#x}, not zeroed"


def test_v_clrwk_clears_the_declared_screen():
    """VDI 3 over a screen full of noise: the whole 32,000 bytes, and nothing outside them."""
    pokes = _world(0x16a0, spans=((WORK, WORK + SCREEN_BYTES),),
                   extra=abi.stack_args((2, OS_VDI_HANDLE)))
    diffs, _ = _run(ENTRY_V_CLRWK,
                    lambda lib, buf: lib.g_v_clrwk(buf, OS_VDI_HANDLE, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("state", ((10, 20, 0), (0, 0, 1), (319, 199, 2), (-1, -1, 0xffff)))
def test_vq_mouse(state):
    """VDI 124: the button mask out of `intout[0]` and the position out of the first ptsout pair.

    The three out-parameters are three SEPARATE words here, though the game's one call site passes
    three separate globals too — a reconstruction that swapped x and y differs in four bytes.
    """
    x, y, buttons = state
    pokes = _world(0x16a2, spans=((OUT, OUT + 0x40),),
                   extra=abi.merge_pokes(harness.mouse_state(x, y, buttons),
                                         abi.stack_args((2, OS_VDI_HANDLE), (4, OUT_SLOTS[0]),
                                                        (4, OUT_SLOTS[1]), (4, OUT_SLOTS[2]))))
    diffs, _ = _run(ENTRY_VQ_MOUSE,
                    lambda lib, buf: lib.g_vq_mouse(buf, OS_VDI_HANDLE, OUT_SLOTS[0], OUT_SLOTS[1],
                                                    OUT_SLOTS[2], CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"mouse {state}\n{report(diffs)}"


@pytest.mark.parametrize("shift", (0, 1, 2, 3, 4, 0xffff))
def test_vq_key_s(shift):
    """VDI 128: the shift/control/alt bitmap the blow gate reads."""
    pokes = _world(0x16a5, spans=((OUT, OUT + 0x40),),
                   extra=abi.merge_pokes(harness.key_shift(shift),
                                         abi.stack_args((2, OS_VDI_HANDLE), (4, OUT_SLOTS[0]))))
    diffs, _ = _run(ENTRY_VQ_KEY_S,
                    lambda lib, buf: lib.g_vq_key_s(buf, OS_VDI_HANDLE, OUT_SLOTS[0], CALLER_A1,
                                                    CALLER_A2), pokes)
    assert not diffs, f"shift {shift:#x}\n{report(diffs)}"


# The strings the front end really draws, plus the two degenerate lengths. The menu line is the
# longest thing in the program's DATA; the empty string is what pins the terminator being COPIED —
# a reconstruction that stopped before storing it would report a length of -1 and hand the VDI a
# `contrl[3]` of 0xffff, which is a different call.
GTEXT_STRINGS = (b"", b"A", b"HALL:", b"SCORE 1:", b"Press [G] .......to play the Game",
                 b"G A M E    O V E R", b"\x80\xff\x01mixed bytes")


@pytest.mark.parametrize("text", GTEXT_STRINGS)
@pytest.mark.parametrize("at", ((0x18, 0x48), (0, 0), (312, 199), (-8, 4)))
def test_v_gtext(text, at):
    """VDI 8: the string widened into `intin` a byte at a time, terminator included.

    Drawn at the game's own left margin and at three positions the model has to clip — the origin,
    the far corner and a negative x — because the glyphs land on the declared screen and the byte
    diff is what compares them.
    """
    x, y = at
    pokes = _world(0x16a8 + len(text), spans=((WORK, WORK + SCREEN_BYTES),),
                   extra=abi.merge_pokes({TEXT: text + b"\0"},
                                         abi.stack_args((2, OS_VDI_HANDLE), (2, x), (2, y),
                                                        (4, TEXT))))
    diffs, _ = _run(ENTRY_V_GTEXT,
                    lambda lib, buf: lib.g_v_gtext(buf, OS_VDI_HANDLE, x & 0xffff, y & 0xffff,
                                                   TEXT, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"{text!r} at {at}\n{report(diffs)}"


@pytest.mark.parametrize("rect", ((35, 189, 318, 189), (0, 0, 319, 199), (100, 50, 60, 20)))
@pytest.mark.parametrize("interior,colour", ((1, 11), (1, 0), (0, 11)))
def test_vr_recfl(rect, interior, colour):
    """VDI 114 over the caller's OWN four-word rectangle, which it lends the VDI and takes back.

    The first rectangle is the bonus bar's own row. The hollow interior is here because the model
    reads the fill INTERIOR before the fill colour — a hollow fill paints colour 0 whatever pen is
    set — and a case that only ever ran solid could not tell the two reads apart.
    """
    pokes = _world(0x16ae + interior, spans=((WORK, WORK + SCREEN_BYTES),),
                   fill_interior=interior, fill_color=colour,
                   extra=abi.merge_pokes({PXY: b"".join(abi.word(v) for v in rect)},
                                         abi.stack_args((2, OS_VDI_HANDLE), (4, PXY))))
    diffs, _ = _run(ENTRY_VR_RECFL,
                    lambda lib, buf: lib.g_vr_recfl(buf, OS_VDI_HANDLE, PXY, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, f"{rect} interior {interior} pen {colour}\n{report(diffs)}"


CPYFM_RECTS = (
    (0, 0, SPRITE_EXTENT, SPRITE_EXTENT, 0, 0, SPRITE_EXTENT, SPRITE_EXTENT),
    (0, 0, SPRITE_EXTENT, SPRITE_EXTENT, 100, 60, 100 + SPRITE_EXTENT, 60 + SPRITE_EXTENT),
    (0, 0, SPRITE_EXTENT, SPRITE_EXTENT, 300, 190, 300 + SPRITE_EXTENT, 190 + SPRITE_EXTENT),
    (0, 0, SPRITE_EXTENT, SPRITE_EXTENT, -8, -8, -8 + SPRITE_EXTENT, -8 + SPRITE_EXTENT),
)


@pytest.mark.parametrize("rect", CPYFM_RECTS)
@pytest.mark.parametrize("mode", (VDI_MODE_S_ONLY, VDI_MODE_S_OR_D))
@pytest.mark.parametrize("direction", ("cell_to_screen", "screen_to_cell", "cell_to_cell"))
def test_vro_cpyfm(rect, mode, direction):
    """VDI 109 in all three directions the game uses, over the two logic operations it asks for.

    `fd_addr == 0` is the VDI's own screen and anything else is a memory raster, so the three
    directions are three different MFDB pairs — and the two off-screen destinations are what the
    model clips, which is what the game relies on to draw a sprite at the screen edge.
    """
    src = 0 if direction == "screen_to_cell" else SPRITE_A
    dst = 0 if direction == "cell_to_screen" else SPRITE_B
    pokes = _world(0x16b1 + mode, spans=((WORK, WORK + SCREEN_BYTES),
                                         (SPRITE_A, SPRITE_B + TILE_BYTES)),
                   extra=abi.merge_pokes({MFDB_A: _mfdb(src), MFDB_B: _mfdb(dst),
                                          PXY: b"".join(abi.word(v) for v in rect)},
                                         abi.stack_args((2, OS_VDI_HANDLE), (2, mode), (4, PXY),
                                                        (4, MFDB_A), (4, MFDB_B))))
    diffs, _ = _run(ENTRY_VRO_CPYFM,
                    lambda lib, buf: lib.g_vro_cpyfm(buf, OS_VDI_HANDLE, mode, PXY, MFDB_A, MFDB_B,
                                                     CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"{direction} mode {mode} {rect}\n{report(diffs)}"


# ============================================================================== the AES entry points

def test_gem_aes_files_the_registers_and_dispatches():
    """`gem_aes` entered directly with a parameter block on the stack, and `appl_exit`'s opcode
    staged in `control[0]` — the one modeled AES call the game never makes, so this case reaches
    the trap without also being a test of one of the three wrappers below."""
    pokes = _world(0x149b, extra=abi.merge_pokes({A_AES_CONTROL: abi.word(19)},
                                                 abi.stack_args((4, A_AES_P_CONTROL))))
    diffs, _ = _run(ENTRY_GEM_AES,
                    lambda lib, buf: lib.g_gem_aes(buf, A_AES_P_CONTROL, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, report(diffs)


AES_OPCODES = (10, 19, 77, 78)


@pytest.mark.parametrize("opcode", AES_OPCODES)
def test_aes_crysif(opcode):
    """The whole AES binding: opcode into `control[0]`, three SIGNED table bytes into `control[1..3]`,
    trap, answer `int_out[0]`."""
    pokes = _world(0x14b2 + opcode, extra=abi.stack_args((2, opcode)))
    diffs, info = _run(ENTRY_AES_CRYSIF,
                       lambda lib, buf: lib.g_aes_crysif(buf, opcode, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"opcode {opcode}\n{report(diffs)}"
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff


@pytest.mark.parametrize("row", ((0x81, 0x7f, 0xff), (0xff, 0x80, 0x01)))
def test_aes_crysif_widens_the_count_bytes_as_signed(row):
    """The three count bytes are widened with `ext.w`, i.e. SIGNED — and the game's own table cannot
    show it.

    Every row the program asks for (opcodes 10, 19, 77 and 78) holds counts of 0, 1 or 5, so an
    unsigned widening produces the same three words and passes every other case in this file. The
    first byte at or above 0x80 in the whole table belongs to opcode 126, which the model does not
    serve — so the run would be refused rather than compared, and the branch is unreachable through
    a serviced call.

    What this case does instead is stage the ROW: the table is ordinary image memory that both sides
    read, so a row with a high byte in it is an input to the routine's own arithmetic rather than a
    fabricated answer from anywhere. Measured — an unsigned widening survived the whole battery
    until this case existed (STATUS.md).
    """
    opcode = 10
    entry = AES_CONTROL_TABLE + (opcode - AES_TABLE_FIRST_OPCODE) * AES_TABLE_STRIDE
    pokes = _world(0x14b20 + row[0], extra=abi.merge_pokes({entry: bytes(row)},
                                                           abi.stack_args((2, opcode))))
    diffs, _ = _run(ENTRY_AES_CRYSIF,
                    lambda lib, buf: lib.g_aes_crysif(buf, opcode, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"row {row}\n{report(diffs)}"


def test_aes_control_table_holds_what_the_reconstruction_reads():
    """The three counts for each opcode the game asks for, read off the loaded image.

    The table is in TEXT and is never written, so this is an assertion about the binary rather than
    about a run — and it is what says the `(opcode - 10) * 3` index is the right one, which no
    differential could show on its own because both sides compute it from the same bytes.
    """
    expected = {10: (0, 1, 0), 19: (0, 1, 0), 77: (0, 5, 0), 78: (1, 1, 1)}
    assert set(expected) == set(AES_OPCODES)
    for opcode, counts in expected.items():
        entry = AES_CONTROL_TABLE + (opcode - AES_TABLE_FIRST_OPCODE) * AES_TABLE_STRIDE
        assert tuple(bytes(harness.BASE_IMAGE[entry:entry + AES_TABLE_STRIDE])) == counts, (
            f"opcode {opcode}'s (n_intin, n_intout, n_addrin) row is not {counts} — either the "
            f"table's first opcode is not {AES_TABLE_FIRST_OPCODE} or its stride is not "
            f"{AES_TABLE_STRIDE}")
    assert AES_TABLE_STRIDE == AES_CONTROL_COUNT_SLOTS - 1, (
        "the three table bytes fill control[1..3], so the stride and the loop bound move together")


def test_appl_init_binds_the_parameter_block():
    """The six array pointers, the block pointer, and the application id — from a ZEROED block, so
    every one of the seven longwords has to be written for the case to pass."""
    pokes = abi.stage_world(0x14b9, (AES_INT_OUT_SPAN,), harness.vdi_state(screen=WORK))
    diffs, info = _run(ENTRY_APPL_INIT,
                       lambda lib, buf: lib.g_appl_init(buf, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, report(diffs)
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff


def test_graf_handle():
    """AES 77: the workstation handle in `int_out[0]` and the four font cell sizes behind it, copied
    out through four SEPARATE pointers — which is not what its one caller does (it passes the same
    scratch word four times), so the four are told apart here and nowhere else."""
    pokes = _world(0x14be, spans=((OUT, OUT + 0x40),),
                   extra=abi.stack_args((4, OUT_SLOTS[0]), (4, OUT_SLOTS[1]), (4, OUT_SLOTS[2]),
                                        (4, OUT_SLOTS[3])))
    diffs, info = _run(ENTRY_GRAF_HANDLE,
                       lambda lib, buf: lib.g_graf_handle(buf, *OUT_SLOTS, CALLER_A1, CALLER_A2),
                       pokes)
    assert not diffs, report(diffs)
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff == OS_VDI_HANDLE


@pytest.mark.parametrize("mode", (AES_M_OFF, AES_M_ON))
def test_graf_mouse(mode):
    """AES 78, whose whole effect is OFF-IMAGE: hiding the GEM pointer touches no memory at all, so
    the ordered OS event ledger `harness.differential` compares is the only thing that can tell a
    reconstruction which makes the call from one which does not."""
    pokes = _world(0x14c1 + mode, extra=abi.stack_args((2, mode), (4, CALLER_A1)))
    diffs, _ = _run(ENTRY_GRAF_MOUSE,
                    lambda lib, buf: lib.g_graf_mouse(buf, mode, CALLER_A1, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, f"mode {mode}\n{report(diffs)}"


# =========================================================================== boot-time setup

def test_init_gem_and_screens():
    """The whole of `init_gem_and_screens`, run to `rts` from a machine that has none of its state.

    Nothing is staged but the frame and the noise: this routine REGISTERS with the AES, opens the
    workstation, and takes both screen bases off XBIOS, so every pointer it leaves behind is one it
    computed. The one thing it reads that it never writes is `super_arg`, which is the bss zero —
    i.e. `Super(0)`, the only argument the model hands back a cookie for.
    """
    pokes = abi.stage_world(
        0x1011, (VDI_WORK_OUT_SPAN, AES_INT_OUT_SPAN),
        {CONTERM_ADDRESS: b"\xa5",           # so clearing the conterm byte is a visible change
         A_AES_AP_ID: abi.word(0xbeef)})     # ...and so is `appl_init` filing the id it is given
    diffs, _ = _run(ENTRY_INIT_GEM_AND_SCREENS,
                    lambda lib, buf: lib.g_init_gem_and_screens(buf, FRAME_A6, CALLER_A1,
                                                                CALLER_A2), pokes)
    assert not diffs, report(diffs)


def test_init_gem_and_screens_leaves_the_screens_a_screen_apart():
    """...and what it left, read off the oracle: the two bases and the resolution the model answers.

    `screen_back` is `Logbase - 32000`, which under the model puts the work buffer at 0x300 — the
    reason every other battery in this project pokes the two pointers instead of taking them from
    here (STATUS.md, "Model gaps"). Pinning it is what keeps that note true.
    """
    image = harness.make_image({CONTERM_ADDRESS: b"\xa5", A_AES_AP_ID: abi.word(0xbeef)})
    final, _writes, _regs = emu.run(image, ENTRY_INIT_GEM_AND_SCREENS,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})

    assert _long(final, A_SCREEN_PHYS) - _long(final, A_SCREEN_BACK) == SCREEN_BYTES
    assert _word(final, A_SCREEN_REZ) == XBIOS_GETREZ_LOW_RES
    assert final[CONTERM_ADDRESS] == 0
    assert _word(final, A_CONTERM_ADDR_W) == CONTERM_ADDRESS
    assert _long(final, A_CONTERM_ADDR_L) == CONTERM_ADDRESS
    assert _long(final, A_SUPER_SAVED_SSP) != 0, "Super(0) answered with no cookie at all"
    assert _word(final, A_AES_AP_ID) == OS_AES_AP_ID, "appl_init did not keep the application id"


# ================================================================================ the sprite protocol

# Where the sprite bank's 62 allocations land. `c_malloc` carves them out of the model's arena, so
# the case stages nothing there — but the bank cases DO need the six GHOST.DAT banks, which
# `build_sprite_bank_prepare` paints onto the work buffer before the grabs.
# The banks sit in the UPPER half of the model's Malloc arena, well clear of the bottom of it —
# where `build_sprite_bank`'s own 62 allocations really land — and clear of the scratch map above.
# The gaps between them are irregular for `test_blit.py`'s reason: 60 tiles of 512 bytes is exactly
# a bank, so with the banks packed the `divs.w #$3c` split collapses, and with a CONSTANT stride a
# bank's address is still affine in its index.
BANK_BASE = 0x50000
DAT_BANK_BYTES = 0x7800
BANK_ADDRESSES = tuple(BANK_BASE + index * DAT_BANK_BYTES + index * index * 0x40 + index * 0x110
                       for index in range(7))

SPRITE_POINTER_POKES = {
    A_SCREEN_PHYS: abi.long(PHYS),
    A_SCREEN_BACK: abi.long(WORK),
    A_DAT_BANK: b"".join(abi.long(address) for address in BANK_ADDRESSES),
}
BANK_SPANS = tuple((address, address + DAT_BANK_BYTES) for address in BANK_ADDRESSES)
# The six banks GHOST.DAT really fills, sliced ONCE at import: three cases stage them and each was
# re-slicing 184 KB per run. Bank 6 is GHOST.PRE's and is staged by the case that needs it.
GHOST_DAT_BANK_POKES = {address: GHOST_DAT[index * DAT_BANK_BYTES:(index + 1) * DAT_BANK_BYTES]
                        for index, address in enumerate(BANK_ADDRESSES[:DAT_BANKS_FROM_FILE])}


def test_build_sprite_bank():
    """The WHOLE of `build_sprite_bank` @ 0x132ec, run to `rts` — which is `include/blit.h`'s
    verified prefix composed with the grab loop this subsystem owns.

    The grab loop was `src/blit.c`'s residual: sixty `c_malloc(512)` + `vro_cpyfm` pairs that lift
    each cell off the bank screen the prefix has just painted. Running the routine whole is what
    pins the composition as well as the loop — the prefix's MFDB geometry is what the grabs then
    use, and nothing else in the suite runs the two together.

    The real GHOST.DAT is what the bank is painted from, so the 62 buffers hold the game's own
    sprites and a wrong cell origin lands a visibly different 512 bytes.
    """
    _build_sprite_bank_case(0x132e)


# The grabs are ~60 `c_malloc` + `vro_cpyfm` pairs, which is far more than a default run.
BUILD_SPRITE_BANK_INSNS = 4_000_000

# THE ARENA THE SIXTY-TWO GRABS ALLOCATE INTO IS SEEDED WITH NOISE, and that is what stands in for
# the poison pass this one routine cannot have.
#
# WHY IT IS NEEDED: cell 50 — `bubble_sprite[3]`, GHOST.DAT tile 50 — is 512 ZERO bytes in the real
# file, and a freshly-`c_malloc`ed buffer over untouched image is zero too. So a grab that never
# happened writes nothing and leaves exactly what it would have written. Measured: `if (cell != 50)`
# passed all 225 cases of this battery before this span was seeded.
#
# WHY NOT `poison=True`: the attribution pass pre-inverts every byte the oracle wrote, and the
# allocator's own free-list headers are among them. Both sides then walk a corrupt list and the
# ORACLE never reaches its `rts` — the run is refused at the instruction cap rather than compared.
# That is `docs/agent-playbook.md` §8's "a routine that reads back what it has just written", and
# seeding the destinations instead is exactly the remedy `harness._vet_poison_is_attributable`
# names. The span is generous: 62 x 512 bytes of cells plus the pools `c_morecore` rounds up to.
MALLOC_ARENA_SEEDED_BYTES = 0x10000


def _build_sprite_bank_case(seed):
    arena = (emu.OS_HEAP_BASE, emu.OS_HEAP_BASE + MALLOC_ARENA_SEEDED_BYTES)
    pokes = abi.stage_world(seed, ((WORK, WORK + SCREEN_BYTES), arena) + BANK_SPANS,
                            _pblock_pokes(), _workstation_pokes(), SPRITE_POINTER_POKES,
                            GHOST_DAT_BANK_POKES)
    diffs, _ = _run(ENTRY_BUILD_SPRITE_BANK,
                    lambda lib, buf: lib.g_build_sprite_bank(buf, CALLER_A1, CALLER_A2), pokes,
                    max_insns=BUILD_SPRITE_BANK_INSNS)
    assert not diffs, report(diffs)


def _sprite_bank_pokes():
    """The 60 sprite pointers plus the two background buffers, all inside the scratch map."""
    cells = tuple(SPRITE_TABLE_BASE + index * TILE_BYTES
                  for index in range(GHOST_CELLS + BUBBLE_CELLS + 2))
    return ({A_GHOST_SPRITE: b"".join(abi.long(cells[i]) for i in range(GHOST_CELLS)),
             A_BUBBLE_SPRITE: b"".join(abi.long(cells[GHOST_CELLS + i])
                                       for i in range(BUBBLE_CELLS)),
             A_GHOST_BG: abi.long(cells[-2]),
             A_BUBBLE_BG: abi.long(cells[-1])},
            (cells[0], cells[-1] + TILE_BYTES))


# THE TWO MFDBs' `fd_addr` ON ENTRY IS DISTINCTIVE JUNK, NOT ZERO, and that is what makes the trio's
# twelve pointer stores observable. Each of `save_sprite_backgrounds`, `draw_sprites` and
# `restore_sprite_backgrounds` writes both halves of both MFDBs — four stores each — and half of
# those stores write ZERO, meaning "the workstation's own screen". Staged over a zero they are
# invisible: deleting one leaves the field holding the value it was about to be given. Staged over a
# raster of its own, a deleted store makes the copy read or write THAT raster instead of the screen,
# and the byte diff says so.
#
# The junk rasters are 32x32x4 cells inside the scratch map, seeded with noise by every case that
# uses them (SPRITE_MFDB_SPANS), so a copy that lands on one differs — and, being in-image and the
# size the MFDB declares, an errant copy stays inside the image under `make guarded`.
SPRITE_MFDB_POKES = {
    A_MFDB_SRC: _mfdb(MFDB_JUNK_SRC),
    A_MFDB_DST: _mfdb(MFDB_JUNK_DST),
}
SPRITE_MFDB_SPANS = ((MFDB_JUNK_SRC, MFDB_JUNK_DST + TILE_BYTES),)

SPRITE_PLACEMENTS = (
    (0, 0, 0, 40, 40, 4),
    (100, 60, 12, 200, 100, 8),
    (300, 190, 46, 0, 0, 12),     # both sprites at a corner the VDI has to clip
    (-8, -8, 20, 312, 195, 0),
)


SPRITE_ROUTINES = {
    "save": (ENTRY_SAVE_SPRITE_BACKGROUNDS, "g_save_sprite_backgrounds"),
    "draw": (ENTRY_DRAW_SPRITES, "g_draw_sprites"),
    "restore": (ENTRY_RESTORE_SPRITE_BACKGROUNDS, "g_restore_sprite_backgrounds"),
}


def _sprite_case(routine, placement, seed, poison=False):
    """One of the three per-frame routines over one (ghost, bubble) placement."""
    ghost_x, ghost_y, ghost_tile, bubble_x, bubble_y, bubble_frame = placement
    entry, symbol = SPRITE_ROUTINES[routine]
    bank_pokes, bank_span = _sprite_bank_pokes()
    pokes = _world(seed, spans=((WORK, WORK + SCREEN_BYTES), bank_span) + SPRITE_MFDB_SPANS,
                   extra=abi.merge_pokes(bank_pokes, SPRITE_MFDB_POKES, {
                       A_GHOST_X: abi.word(ghost_x), A_GHOST_Y: abi.word(ghost_y),
                       A_GHOST_TILE: abi.word(ghost_tile), A_BUBBLE_X: abi.word(bubble_x),
                       A_BUBBLE_Y: abi.word(bubble_y), A_BUBBLE_FRAME: abi.word(bubble_frame)}))
    diffs, _ = _run(entry, lambda lib, buf: getattr(lib, symbol)(buf, CALLER_A1, CALLER_A2), pokes,
                    poison=poison)
    assert not diffs, f"{routine} {placement}\n{report(diffs)}"


@pytest.mark.parametrize("placement", SPRITE_PLACEMENTS)
@pytest.mark.parametrize("routine", sorted(SPRITE_ROUTINES))
def test_sprite_protocol(placement, routine):
    """The three per-frame `vro_cpyfm` pairs: save the two patches, OR the two sprites on, put the
    patches back.

    These were `src/blit.c`'s residuals — a refused oracle run before the model grew VDI opcode
    109 — and they belong with the sprite protocol rather than with the raw blitters, so they are
    here (STATUS.md).

    Each placement drives BOTH sprites at once, and the third puts them at a corner the copy has to
    clip: that is the only thing in the program that depends on the VDI clipping a raster copy
    rather than the game bounding it.
    """
    _sprite_case(routine, placement, seed=0x1342 + placement[2])


# The three, in the order one frame runs them, as (oracle entry, candidate glue).
SPRITE_FRAME_SEQUENCE = tuple(SPRITE_ROUTINES[name] for name in ("save", "draw", "restore"))


def test_sprite_save_draw_restore_round_trips():
    """...and the three COMPOSED, on both sides: one frame of the protocol run as a sequence.

    THIS IS A DIFFERENTIAL, not a property check on the oracle. `harness.differential` runs one
    entry against one glue, so a composition of three is spelt here: three chained `emu.run`s on one
    image against three chained candidate calls on one candidate buffer, then the same byte diff the
    harness would do. What it adds to the three per-routine cases is the STATE EACH LEAVES FOR THE
    NEXT — the two background buffers `save` fills and `restore` reads back, and the two MFDBs all
    three re-point — which no single-routine case runs across.

    The round trip on top of it is the protocol's whole point: the work buffer comes back byte for
    byte, so what the collision probe reads afterwards is the room and its objects only.
    """
    bank_pokes, bank_span = _sprite_bank_pokes()
    pokes = _world(0x134f, spans=((WORK, WORK + SCREEN_BYTES), bank_span) + SPRITE_MFDB_SPANS,
                   extra=abi.merge_pokes(bank_pokes, SPRITE_MFDB_POKES, {
                       A_GHOST_X: abi.word(80), A_GHOST_Y: abi.word(40),
                       A_GHOST_TILE: abi.word(17), A_BUBBLE_X: abi.word(150),
                       A_BUBBLE_Y: abi.word(90), A_BUBBLE_FRAME: abi.word(7)}))
    image = harness.make_image(pokes)
    before = bytes(image[WORK:WORK + SCREEN_BYTES])
    # THE CANDIDATE'S BUFFER IS TAKEN FIRST, off the image as staged: `emu.run` hands back the image
    # its run left, so copying after the oracle chain would start the candidate from the oracle's
    # own output and compare a program with itself.
    candidate = harness.candidate_image(image)

    regs = {"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2}
    oracle = image
    for entry, _symbol in SPRITE_FRAME_SEQUENCE:
        oracle, _writes, _regs = emu.run(oracle, entry, regs=dict(regs))

    harness.arm_candidate()
    for _entry, symbol in SPRITE_FRAME_SEQUENCE:
        getattr(harness._lib, symbol)(candidate, CALLER_A1, CALLER_A2)
    assert harness._lib.g_os_refusal_count() == 0, (
        "the candidate made a refused os_* call during the sequence, so nothing below was tested")

    final = bytes(candidate)
    diffs = [(a, oracle[a], final[a]) for a in range(emu.STACK_GUARD_LO) if oracle[a] != final[a]]
    assert not diffs, report(diffs)
    assert bytes(oracle[WORK:WORK + SCREEN_BYTES]) == before, (
        "save + draw + restore did not leave the work buffer as it found it")


# ============================================================ the presentation screen and the files

def _show_presentation_case(seed, poison=False):
    pokes = abi.merge_pokes(
        abi.seed_spans(seed, ((WORK, PHYS + SCREEN_BYTES),) + BANK_SPANS, guard=abi.GUARD_BYTES),
        _pblock_pokes(), _workstation_pokes(), SPRITE_POINTER_POKES,
        {BANK_ADDRESSES[DAT_BANK_PRE]: GHOST_PRE[:DAT_BANK_BYTES],
         A_PRE_PALETTE: abi.long(BANK_ADDRESSES[DAT_BANK_PRE] + DAT_BANK_BYTES - PALETTE_BYTES)},
        allow_overlap=True)
    diffs, _ = _run(ENTRY_SHOW_PRESENTATION,
                    lambda lib, buf: lib.g_show_presentation(buf, CALLER_A1, CALLER_A2), pokes,
                    poison=poison)
    assert not diffs, report(diffs)


def test_show_presentation():
    """Bank 6 painted onto the work buffer, the visible screen cleared, the palette installed, and
    the whole 30,720-byte picture copied up.

    The palette call is XBIOS `Setpalette`, which the model answers as a no-op: what a reconstruction
    can reproduce of it is the trampoline's three save slots, and the case seeds them with noise so
    a missing call differs.
    """
    _show_presentation_case(0x10eb)


def _staged(*files):
    """`harness.stage_files` for the loaders, whose names come out of the program's own DATA."""
    pokes, _handles = harness.stage_files(list(files))
    return pokes


def test_load_demo():
    """GHOST.DEM: one `c_malloc(0x1770)`, one `c_read`, and the replay cursor parked at the head."""
    pokes = abi.merge_pokes(_pblock_pokes(), _workstation_pokes(),
                            _staged(("A:GHOST.DEM", GHOST_DEM[:DEMO_FILE_BYTES])))
    diffs, _ = _run(ENTRY_LOAD_DEMO,
                    lambda lib, buf: lib.g_load_demo(buf, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, report(diffs)


def test_load_demo_leaves_the_cursor_on_the_base():
    """...and the two pointers really are equal afterwards, which is what a replay restarts from."""
    pokes = abi.merge_pokes(_pblock_pokes(), _workstation_pokes(),
                            _staged(("A:GHOST.DEM", GHOST_DEM[:DEMO_FILE_BYTES])))
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_LOAD_DEMO,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})
    base = _long(final, A_DEMO_BASE)
    cursor = _long(final, A_DEMO_CURSOR)
    assert base == cursor != 0
    assert bytes(final[base:base + 6]) == GHOST_DEM[:6], "the file's first record is not at the base"


def test_load_presentation():
    """GHOST.PRE: the picture into `dat_bank[6]` and the 32 bytes behind it into `pre_palette`."""
    pokes = abi.merge_pokes(_pblock_pokes(), _workstation_pokes(),
                            _staged(("A:GHOST.PRE", GHOST_PRE[:PICTURE_BYTES + PALETTE_BYTES])))
    diffs, _ = _run(ENTRY_LOAD_PRESENTATION,
                    lambda lib, buf: lib.g_load_presentation(buf, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, report(diffs)


def test_load_level_pictures():
    """GHOST.DAT: six 30,720-byte banks and the palette, six separate allocations in file order."""
    pokes = abi.merge_pokes(_pblock_pokes(), _workstation_pokes(),
                            _staged(("A:GHOST.DAT", GHOST_DAT)))
    diffs, _ = _run(ENTRY_LOAD_LEVEL_PICTURES,
                    lambda lib, buf: lib.g_load_level_pictures(buf, CALLER_A1, CALLER_A2), pokes,
                    max_insns=4_000_000)
    assert not diffs, report(diffs)


def _hiscore_file(entries):
    """GHOST.SCR: five (6-digit score, 2-digit room) pairs of zero-padded ASCII, no separators."""
    return b"".join(f"{score:06d}{room:02d}".encode("ascii") for score, room in entries)


HISCORE_FILES = (
    ((0, 1), (0, 1), (0, 1), (0, 1), (0, 1)),
    ((100, 2), (2500, 7), (13000, 12), (44500, 23), (999999, 35)),
    ((1, 0), (999999, 99), (0, 0), (500000, 1), (7, 35)),
)


@pytest.mark.parametrize("entries", HISCORE_FILES)
def test_load_hiscores(entries):
    """Five (score, room) pairs parsed digit by digit through the C library's 32-bit multiply."""
    pokes = abi.stage_world(
        0x121a, (HALL_TABLE_SPAN,), _pblock_pokes(), _workstation_pokes(),
        _staged(("A:GHOST.SCR", _hiscore_file(entries))))
    diffs, _ = _run(ENTRY_LOAD_HISCORES,
                    lambda lib, buf: lib.g_load_hiscores(buf, FRAME_A6, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, f"{entries}\n{report(diffs)}"


def test_load_hiscores_short_field_stops_at_the_first_non_digit():
    """A file whose fields are not all digits: the parse stops where the digits do.

    The game never writes such a file — `itoa_padded` zero-pads every field — but the parser has no
    length check at all, so what bounds it is the byte test, and only a case with a non-digit in the
    middle of a field exercises that.
    """
    text = b"12 45607" + b"00034507" + b"0000ab08" + b"00000109" + b"00000210"
    pokes = abi.stage_world(
        0x121b, (HALL_TABLE_SPAN,), _pblock_pokes(), _workstation_pokes(),
        _staged(("A:GHOST.SCR", text)))
    diffs, _ = _run(ENTRY_LOAD_HISCORES,
                    lambda lib, buf: lib.g_load_hiscores(buf, FRAME_A6, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, report(diffs)


def test_load_hiscores_reads_the_table_the_note_describes():
    """...and the table it leaves, so `../notes/frontend.md` §4's layout is executed, not argued."""
    entries = ((100, 2), (2500, 7), (13000, 12), (44500, 23), (999999, 35))
    pokes = abi.merge_pokes(_pblock_pokes(), _workstation_pokes(),
                            _staged(("A:GHOST.SCR", _hiscore_file(entries))))
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_LOAD_HISCORES,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})

    for slot, (score, room) in enumerate(entries):
        assert _long(final, A_HALL_SCORES + slot * 4) == score
        assert _long(final, A_HALL_ROOMS + slot * 4) == room


# ============================================================================ attribution and fuzz
#
# CHUNKS is the shard count for every fuzz below. All of them are chunk-SEEDED rather than
# chunk-partitioned (`test/abi.py`'s `shard` docstring tells the two apart): each chunk draws its
# own cases from its own generator, so the suite runs CHUNKS times as many as one chunk does and no
# chunk repeats another's.
CHUNKS = 8


@pytest.mark.parametrize("routine", ("v_clrwk", "v_gtext", "vro_cpyfm", "save", "draw", "restore",
                                     "show_presentation"))
def test_attribution(routine):
    """The poison pass: every byte the oracle wrote is pre-inverted, so a candidate that "matched"
    only because the region already held the right bytes now differs (docs/agent-playbook.md §4).

    The seven here are the routines whose output is DATA. The ones left out are left out for §8's
    reason rather than by oversight: `v_opnvwk`, the file loaders and `build_sprite_bank` read back
    what they have just written (the workstation handle, the buffer pointer a `c_read` is then
    handed, the allocator's own free list), so pre-inverting it diverts the run instead of catching a
    coincidence. `test_build_sprite_bank` seeds its destinations instead — see
    `_build_sprite_bank_case`, which says what that buys and why the poison pass could not.
    """
    if routine == "v_clrwk":
        pokes = _world(0x2a0, spans=((WORK, WORK + SCREEN_BYTES),),
                       extra=abi.stack_args((2, OS_VDI_HANDLE)))
        glue = lambda lib, buf: lib.g_v_clrwk(buf, OS_VDI_HANDLE, CALLER_A1, CALLER_A2)
        entry = ENTRY_V_CLRWK
    elif routine == "v_gtext":
        text = b"SCORE 1:"
        pokes = _world(0x2a1, spans=((WORK, WORK + SCREEN_BYTES),),
                       extra=abi.merge_pokes({TEXT: text + b"\0"},
                                             abi.stack_args((2, OS_VDI_HANDLE), (2, 0x38),
                                                            (2, 0x48), (4, TEXT))))
        glue = lambda lib, buf: lib.g_v_gtext(buf, OS_VDI_HANDLE, 0x38, 0x48, TEXT, CALLER_A1,
                                              CALLER_A2)
        entry = ENTRY_V_GTEXT
    elif routine == "vro_cpyfm":
        rect = CPYFM_RECTS[1]
        pokes = _world(0x2a2, spans=((WORK, WORK + SCREEN_BYTES),
                                     (SPRITE_A, SPRITE_B + TILE_BYTES)),
                       extra=abi.merge_pokes({MFDB_A: _mfdb(SPRITE_A), MFDB_B: _mfdb(0),
                                              PXY: b"".join(abi.word(v) for v in rect)},
                                             abi.stack_args((2, OS_VDI_HANDLE),
                                                            (2, VDI_MODE_S_ONLY), (4, PXY),
                                                            (4, MFDB_A), (4, MFDB_B))))
        glue = lambda lib, buf: lib.g_vro_cpyfm(buf, OS_VDI_HANDLE, VDI_MODE_S_ONLY, PXY, MFDB_A,
                                                MFDB_B, CALLER_A1, CALLER_A2)
        entry = ENTRY_VRO_CPYFM
    elif routine == "show_presentation":
        return _show_presentation_case(0x2a3, poison=True)
    else:
        return _sprite_case(routine, (60, 30, 21, 180, 110, 9), seed=0x2a4, poison=True)
    diffs, _ = _run(entry, glue, pokes, poison=True)
    assert not diffs, f"{routine}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_vro_cpyfm_fuzz(chunk):
    """Random rectangles, MFDB geometries and logic operations, in all three raster directions.

    THE LOGIC OPERATION IS DRAWN FROM ALL SIXTEEN, not the two the game uses: the wrapper hands the
    VDI whatever `intin[0]` it was given, so an operation the game never asks for is an ordinary
    input to it — and one of the sixteen going somewhere else in `intin` would show here first.
    The extents are drawn small so the rectangles often fall partly off the destination, which is
    the clip the game relies on for a sprite at the screen edge.
    """
    rng = random.Random(0x16b12 + chunk)
    for _case in range(12):
        mode = rng.randrange(16)
        width = rng.choice((8, 16, 32, 48))
        height = rng.choice((8, 16, 32, 40))
        direction = rng.randrange(3)
        src = 0 if direction == 1 else SPRITE_A
        dst = 0 if direction == 0 else SPRITE_B
        sx1, sy1 = rng.randrange(width), rng.randrange(height)
        rect = (sx1, sy1, sx1 + rng.randrange(width - sx1), sy1 + rng.randrange(height - sy1),
                rng.randrange(-40, 340), rng.randrange(-40, 220), 0, 0)
        pokes = _world(0x16b12 + chunk * 0x100 + _case,
                       spans=((WORK, WORK + SCREEN_BYTES),
                              (SPRITE_A, SPRITE_B + TILE_BYTES)),
                       extra=abi.merge_pokes(
                           {MFDB_A: _mfdb(src, width, height), MFDB_B: _mfdb(dst, width, height),
                            PXY: b"".join(abi.word(v) for v in rect)},
                           abi.stack_args((2, OS_VDI_HANDLE), (2, mode), (4, PXY), (4, MFDB_A),
                                          (4, MFDB_B))))
        diffs, _ = _run(ENTRY_VRO_CPYFM,
                        lambda lib, buf: lib.g_vro_cpyfm(buf, OS_VDI_HANDLE, mode, PXY, MFDB_A,
                                                         MFDB_B, CALLER_A1, CALLER_A2), pokes)
        assert not diffs, f"mode {mode} {rect} {width}x{height}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_v_gtext_fuzz(chunk):
    """Random byte strings at random positions: what a case has to get wrong is the length reported
    in `contrl[3]`, and a string whose bytes are arbitrary is what makes a mis-widened byte show."""
    rng = random.Random(0x16a86 + chunk)
    for _case in range(8):
        length = rng.randrange(0, 24)
        text = bytes(rng.randrange(1, 256) for _ in range(length))
        x, y = rng.randrange(-40, 340), rng.randrange(-8, 210)
        pokes = _world(0x16a86 + chunk * 0x100 + length,
                       spans=((WORK, WORK + SCREEN_BYTES),),
                       extra=abi.merge_pokes({TEXT: text + b"\0"},
                                             abi.stack_args((2, OS_VDI_HANDLE), (2, x), (2, y),
                                                            (4, TEXT))))
        diffs, _ = _run(ENTRY_V_GTEXT,
                        lambda lib, buf: lib.g_v_gtext(buf, OS_VDI_HANDLE, x & 0xffff, y & 0xffff,
                                                       TEXT, CALLER_A1, CALLER_A2), pokes)
        assert not diffs, f"{text!r} at ({x}, {y})\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_sprite_protocol_fuzz(chunk):
    """Random ghost/bubble placements and frames through all three per-frame routines.

    The tile and frame indices are drawn from the whole table, so a reconstruction that reached the
    bubble's table with the biased index — the way `build_sprite_bank` does, and the way these three
    do NOT — lands on a different buffer.
    """
    rng = random.Random(0x134f6 + chunk)
    for _case in range(8):
        placement = (rng.randrange(-40, 340), rng.randrange(-40, 220), rng.randrange(GHOST_CELLS),
                     rng.randrange(-40, 340), rng.randrange(-40, 220), rng.randrange(BUBBLE_CELLS))
        for routine in ("save", "draw", "restore"):
            _sprite_case(routine, placement, seed=0x134f6 + chunk * 0x100 + _case)


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_load_hiscores_fuzz(chunk):
    """Random five-entry files, including scores that overflow six digits when parsed."""
    rng = random.Random(0x121a0 + chunk)
    for _case in range(6):
        entries = tuple((rng.randrange(0, 1000000), rng.randrange(0, 100))
                        for _ in range(HISCORE_SLOTS))
        pokes = abi.stage_world(
            0x121a0 + chunk * 0x100 + _case, (HALL_TABLE_SPAN,),
            _pblock_pokes(), _workstation_pokes(),
            _staged(("A:GHOST.SCR", _hiscore_file(entries))))
        diffs, _ = _run(ENTRY_LOAD_HISCORES,
                        lambda lib, buf: lib.g_load_hiscores(buf, FRAME_A6, CALLER_A1, CALLER_A2),
                        pokes)
        assert not diffs, f"{entries}\n{report(diffs)}"


# ============================================================== what the program's own DATA holds
#
# Three cases that read the loaded image rather than running anything. Each pins an address this
# reconstruction reaches a STRING or a start-up value through — facts a differential covers only
# indirectly (a wrong filename refuses the run; a wrong label draws different pixels), and which are
# cheaper and clearer to state here.

FILE_NAMES = {
    "A_NAME_GHOST_DEM": (A_NAME_GHOST_DEM, b"A:GHOST.DEM"),
    "A_NAME_GHOST_PRE": (A_NAME_GHOST_PRE, b"A:GHOST.PRE"),
    "A_NAME_GHOST_SCR": (A_NAME_GHOST_SCR, b"A:GHOST.SCR"),
    # A SECOND COPY of the same eleven bytes, and the one `save_hiscores` creates through. The two
    # are different addresses holding one string, so the model — which resolves a staged file by
    # NAME — cannot tell them apart, and only this says each is where the reconstruction reads it.
    "A_NAME_GHOST_SCR_CREAT": (A_NAME_GHOST_SCR_CREAT, b"A:GHOST.SCR"),
    "A_NAME_GHOST_DAT": (A_NAME_GHOST_DAT, b"A:GHOST.DAT"),
}


# `c_open` and `c_creat` each compare a path against their OWN copy of the three device names
# (`include/clib.h`), and a match short-circuits GEMDOS and yields a pseudo-handle instead of a file.
A_CREAT_DEVICE_NAMES = 0x251c6
A_OPEN_DEVICE_NAMES = 0x251ec
DEVICE_NAME_STRIDE = 6
DEVICE_NAME_COUNT = 3


def test_no_loader_opens_a_console_pseudo_handle():
    """None of the five names this subsystem opens is "CON:", "AUX:" or "PRT:".

    THIS IS THE PREMISE `src/frontend.c`'s A1 tracking RESTS ON. `c_read` and `c_write` return
    without touching A1 on a console handle — their device arms exit above `c_getfdmode` — so the
    `_reporting` forms would file nothing and every later trap would carry the caller's own A1
    instead of `c_errno`. Every case here happens to open a disk file, so no case could ever show
    the difference; what makes the claim true is the NAMES, and this is where they are checked.

    A pseudo-handle is 0x8300 / 0x82ff / 0x82fe (`include/clib.h`'s FD_DEVICE_*), and it is reached
    by a `c_strcmp` against the tables below and by nothing else — so a name that matches none of
    the six strings can never produce one.
    """
    devices = {bytes(harness.BASE_IMAGE[table + index * DEVICE_NAME_STRIDE:
                                        table + index * DEVICE_NAME_STRIDE + DEVICE_NAME_STRIDE])
               .split(b"\0")[0]
               for table in (A_CREAT_DEVICE_NAMES, A_OPEN_DEVICE_NAMES)
               for index in range(DEVICE_NAME_COUNT)}
    assert devices, "neither device-name table holds a string, so this proves nothing"
    for name, (_address, text) in FILE_NAMES.items():
        assert text not in devices, (
            f"{name} is {text!r}, which is one of the device names {sorted(devices)} — `c_open` "
            f"would hand back a pseudo-handle and the A1 this subsystem threads would be wrong")


def test_the_two_copies_of_the_hiscore_filename_are_different_addresses():
    """`load_hiscores` opens one and `save_hiscores` creates through the other."""
    assert A_NAME_GHOST_SCR != A_NAME_GHOST_SCR_CREAT


@pytest.mark.parametrize("name", sorted(FILE_NAMES))
def test_the_loaders_open_the_names_the_reconstruction_points_at(name):
    """Each loader hands `c_open` a fixed DATA address; this says which file that is."""
    address, expected = FILE_NAMES[name]
    actual = bytes(harness.BASE_IMAGE[address:address + len(expected) + 1])
    assert actual == expected + b"\0", f"{name} holds {actual!r}, not {expected!r}"


def test_the_hall_of_fame_labels_are_where_the_reconstruction_reads_them():
    """The five "SCORE n:" labels ten bytes apart, and "HALL:" behind them.

    `draw_hall_of_fame` walks the five with a fixed stride rather than a pointer table, so the
    stride is part of the reconstruction and this is what says the strings really lie that way.
    """
    for label in range(HISCORE_SLOTS):
        address = A_TEXT_SCORE_LABELS + label * TEXT_SCORE_LABEL_BYTES
        expected = f"SCORE {label + 1}:".encode("ascii")
        actual = bytes(harness.BASE_IMAGE[address:address + len(expected) + 1])
        assert actual == expected + b"\0", f"label {label} holds {actual!r}"
    assert bytes(harness.BASE_IMAGE[A_TEXT_HALL:A_TEXT_HALL + 6]) == b"HALL:\0"


def test_super_arg_is_the_bss_zero_the_boot_path_traps_with(post_init_image):
    """`init_gem_and_screens` pushes `super_arg` without ever writing it, so what it traps with is
    whatever `init_globals` left — and only `Super(0)` gets a cookie back from the model.

    The reconstruction reads the longword rather than assuming, but the CLAIM that the boot path is
    a `Super(0)` is about this byte, and nothing else in the suite looks at it.
    """
    assert int.from_bytes(bytes(post_init_image[A_SUPER_ARG:A_SUPER_ARG + 4]), "big") == 0


# ================================================================== the room composer and the hall

# `draw_room_to_stage` reads the room's own tile map out of the shipped table and the tiles out of
# the six GHOST.DAT banks, so these cases stage the world the way `test_blit.py` does — but with the
# staging area, the work buffer and the visible screen in the machine's own relationship, because
# this routine composes into the first and `stage_to_work` then moves it into the second.
def _room_world(seed, room, mouse=(120, 70, 1), extra=None):
    return abi.stage_world(
        seed, ((STAGE, PHYS + SCREEN_BYTES),) + BANK_SPANS,
        _pblock_pokes(), _workstation_pokes(), SPRITE_POINTER_POKES,
        GHOST_DAT_BANK_POKES,
        harness.mouse_state(*mouse),
        {A_ROOM_NUMBER: abi.word(room)}, extra or {})


# A MOUSE READING PER CELL, so no two cells of the per-cell battery below poll the same state and a
# case that filed the wrong one differs. The three values are spread over the ranges `vq_mouse`
# reports — a screen position and a button mask — and are a function of the cell index only.
def _cell_mouse_state(cell):
    return (7 * cell + 3, 5 * cell + 11, cell & 3)


ROOM_CELLS = tuple((row, col) for row in range(ROOM_TILE_ROWS) for col in range(ROOM_TILE_COLS))


@pytest.mark.parametrize("room", (0, 1, 17, 35))
def test_draw_room_to_stage(room):
    """The whole 5 x 10 composer, run to `rts` — `include/blit.h`'s verified tile draw and this
    subsystem's `vq_mouse`, composed.

    `src/blit.c` verified ONE iteration of this loop and cut its slice around the per-cell mouse
    poll, which was the VDI binding and unported. Running the routine whole is what closes that
    residual, and it also pins the loop scaffolding `src/blit.c` could only read-verify: fifty cells
    in row-major order, and fifty polls with them.
    """
    pokes = _room_world(0x13a0 + room, room)
    diffs, _ = _run(ENTRY_DRAW_ROOM_TO_STAGE,
                    lambda lib, buf: lib.g_draw_room_to_stage(buf, CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"room {room}\n{report(diffs)}"


# The A2 each cell of the loop is ENTERED with. Cell 0 is entered with the caller's, and every later
# cell with what the previous cell's tile draw left — which is what `draw_room_to_stage` threads and
# what `test_draw_room_to_stage_cell` compares against the oracle's own A2 at the stop PC.
CELL_ENTRY_A2 = CALLER_A2


@pytest.mark.parametrize("cell", range(len(ROOM_CELLS)))
def test_draw_room_to_stage_cell(cell):
    """ONE CELL of the 5 x 10 loop, `[0x13a20, 0x13afa)`: the poll and the tile draw, in order.

    THIS IS WHAT MAKES THE FORTY-NINE INTERIOR POLLS OBSERVABLE. A `vq_mouse` over a fixed mouse
    state is IDEMPOTENT — it writes the same three words into the input block every time and files
    the same A1 — so `test_draw_room_to_stage`, which runs to `rts`, cannot tell fifty polls from
    one: only the last write survives. Measured: guarding the poll to the last cell passed the whole
    battery. Stopping between two cells is the only thing that can see an interior poll, and this
    stops at every one of the fifty, each with a mouse reading of its own (`_cell_mouse_state`).

    THE A2 IS COMPARED, not merely threaded: the core answers the A2 its tile draw leaves and this
    checks it against the oracle's A2 at the same PC, which is what closes `src/frontend.c`'s
    "derivable register" residual.
    """
    tile_row, tile_col = ROOM_CELLS[cell]
    pokes = _room_world(0x13a20 + cell, room=1, mouse=_cell_mouse_state(cell),
                        extra={FRAME_TILE_ROW: abi.word(tile_row),
                               FRAME_TILE_COL: abi.word(tile_col)})
    diffs, info = _run(ENTRY_DRAW_ROOM_TO_STAGE_CELL,
                       lambda lib, buf: lib.g_draw_room_to_stage_cell(buf, tile_row, tile_col,
                                                                      CALLER_A1, CELL_ENTRY_A2),
                       pokes, regs={"a6": FRAME_DRAW_ROOM_A6, "a2": CELL_ENTRY_A2},
                       stop_pc=STOP_DRAW_ROOM_TO_STAGE_CELL)
    assert not diffs, f"cell {cell} = ({tile_row}, {tile_col})\n{report(diffs)}"
    assert info["ret"] == info["regs"]["a2"], (
        f"cell {cell} = ({tile_row}, {tile_col}): the core answers "
        f"{info['ret']:#x} as the A2 it leaves, but the original leaves {info['regs']['a2']:#x}")


HALL_TABLES = (
    ((0, 0, 0, 0, 0), (1, 1, 1, 1, 1)),
    ((100, 2500, 13000, 44500, 999999), (2, 7, 12, 23, 35)),
    ((7, 7, 7, 7, 7), (0, 99, 5, 5, 5)),
)


# The two hall-of-fame tables, which sit end to end: `hall_rooms[5]` then `hall_scores[5]`. Seeded
# WITH the default guard, like every other span in this file — the sixteen bytes either side are
# `max_room_reached`/`bonus_tick` below and `hiscore_candidate`/`lives`/`hi_score` above, none of
# which these three routines read, and every case that means to set one of them stages it as a later
# layer. So the guard costs nothing and is what would catch a table write one longword too far.
HALL_TABLE_SPAN = (A_HALL_ROOMS, A_HALL_SCORES + HISCORE_SLOTS * 4)


def _hall_table_pokes(scores, rooms):
    return {A_HALL_SCORES: b"".join(abi.long(v) for v in scores),
            A_HALL_ROOMS: b"".join(abi.long(v) for v in rooms)}


# The room the case leaves in `room_number` before the call. NOT the backdrop room: the routine
# clears the word itself, and staging the value it writes would make that store unobservable.
HALL_ROOM_ON_ENTRY = 17


@pytest.mark.parametrize("table", HALL_TABLES)
def test_draw_hall_of_fame(table):
    """The whole screen, run to `rts`: room 0 as the backdrop, five fixed labels, then the table
    drawn from its BEST entry down so slot 4 lands on the "SCORE 1:" row.

    Every glyph lands on the declared screen, so the byte diff compares the picture; the text is
    formatted through `include/gameplay.h`'s verified `itoa_padded` into two stack buffers, which is
    why this routine takes the frame as an argument.
    """
    scores, rooms = table
    pokes = _room_world(0x11db + scores[0] % 0x100, HALL_ROOM_ON_ENTRY,
                        extra=_hall_table_pokes(scores, rooms))
    diffs, _ = _run(ENTRY_DRAW_HALL_OF_FAME,
                    lambda lib, buf: lib.g_draw_hall_of_fame(buf, FRAME_A6, CALLER_A1, CALLER_A2),
                    pokes)
    assert not diffs, f"{table}\n{report(diffs)}"


# (candidate, pending score, pending room, the table it is offered to). The first four insert; the
# last two do not, which is the arm that runs to `rts`.
HISCORE_OFFERS = (
    (500, 500, 9, (0, 0, 0, 0, 0)),
    (1000000, 1000000, 35, (100, 2500, 13000, 44500, 999999)),
    (3000, 3000, 8, (100, 2500, 13000, 44500, 999999)),
    (101, 101, 2, (100, 2500, 13000, 44500, 999999)),
    (100, 100, 2, (100, 2500, 13000, 44500, 999999)),
    (-5, -5, 1, (0, 0, 0, 0, 0)),
    # The pending ROOM is a word widened to a long with `ext.l`, i.e. SIGNED — and the game's own
    # data cannot show it: a room is 0..35, and even a corrupt GHOST.SCR parses at most 99. So the
    # word is staged with the high bit set, which is what it is: an ordinary input to the routine.
    # Measured — an unsigned widening survived the whole battery until this row existed (STATUS.md).
    (600, 600, -1, (0, 0, 0, 0, 0)),
    (700, 700, 0x8000, (0, 0, 0, 0, 0)),
    # A table that is NOT already sorted, which is the only shape that needs more than one bubble
    # pass — a single insert at slot 0 walks to the top in one. The game always keeps the table
    # sorted, so its own data cannot reach the second pass; a corrupt GHOST.SCR parses into any
    # order, and this stages one. Measured — four passes instead of five survived the whole battery
    # until this row existed (STATUS.md).
    (50, 50, 4, (10, 999999, 44500, 13000, 2500)),
)


# GHOST.SCR's staging: 40 bytes written into a slot reserved with room to spare, so a write that
# ran long would be refused by the model rather than landing on the next file's bytes.
HISCORE_FILE_BYTES = HISCORE_SLOTS * (HISCORE_SCORE_DIGITS + HISCORE_ROOM_DIGITS)
HISCORE_FILE_CAPACITY = 64
# `include/frontend.h`'s SAVE_FRAME_SLOT. NOT in MIRRORS: the header writes the frame offsets as
# parenthesised negatives, which `test_constants.py`'s scraper reads integer literals only and
# cannot see. A drift shows immediately anyway — the case would stage the wrong word and the
# first mouse form would differ on the spot.
SAVE_FRAME_SLOT = -12


# What `save_hiscores` finds in its own `slot` local on entry. It is not scratch: the FIRST
# `graf_mouse`'s `addr_in` long is `0 << 16 | slot`, so a case that let it be zero could not tell a
# reconstruction that reads the word from one that passes a constant.
SAVE_COUNTER_ON_ENTRY = 0x5a5a


def _hiscore_world(seed, scores, rooms, save_frame=None, extra=None):
    """Everything the three hall-of-fame writers need: an open workstation, the table, GHOST.SCR.

    `save_frame`, when given, is `save_hiscores`' own A6 — the case stages its `slot` local, which
    is an INPUT to the first mouse form (see SAVE_COUNTER_ON_ENTRY).
    """
    counter = ({save_frame + SAVE_FRAME_SLOT: abi.word(SAVE_COUNTER_ON_ENTRY)}
               if save_frame is not None else {})
    return abi.stage_world(
        seed, (HALL_TABLE_SPAN,),
        _pblock_pokes(), _workstation_pokes(), _hall_table_pokes(scores, rooms), counter,
        _staged(("A:GHOST.SCR", b"", HISCORE_FILE_CAPACITY)), extra or {})


@pytest.mark.parametrize("table", HALL_TABLES)
def test_save_hiscores(table):
    """The whole of `save_hiscores`, run to `rts`: the banner on the visible screen, forty ASCII
    bytes into a freshly created GHOST.SCR, and the mouse shown and hidden around it.

    THE LOOP COUNTER IS PART OF THE OUTPUT, not just a local. Both `graf_mouse` call sites push only
    the mode word and a zero word, so the `addr_in` LONG the AES stores is that zero over the
    counter above it — `0 << 16 | slot`. The first call therefore files whatever the frame held on
    entry and the second files HISCORE_SLOTS, and `aes_addr_in` is image state the diff compares.
    """
    scores, rooms = table
    pokes = _hiscore_world(0x1207 + scores[0] % 0x100, scores, rooms,
                           save_frame=FRAME_SAVE_HISCORES)
    diffs, _ = _run(ENTRY_SAVE_HISCORES,
                    lambda lib, buf: lib.g_save_hiscores(buf, FRAME_SAVE_HISCORES, CALLER_A1,
                                                         CALLER_A2), pokes)
    assert not diffs, f"{table}\n{report(diffs)}"


@pytest.mark.parametrize("counter", (0, SAVE_COUNTER_ON_ENTRY, 0xffff))
def test_save_hiscores_prologue(counter):
    """`save_hiscores` up to the `c_creat` push — which is the only place its FIRST mouse form is
    observable.

    Both `graf_mouse` sites push only the mode word and a zero word, so the `addr_in` LONG the AES
    stores is that zero over the routine's own `slot` local; the closing call overwrites `addr_in`
    before the `rts`, so a case that ran the routine whole could not tell this call's form from any
    other value. Three entry counters, because the value IS the form.
    """
    scores, rooms = (100, 2500, 13000, 44500, 999999), (2, 7, 12, 23, 35)
    pokes = abi.merge_pokes(
        _hiscore_world(0x1206 + (counter & 0xff), scores, rooms),
        {FRAME_SAVE_HISCORES + SAVE_FRAME_SLOT: abi.word(counter)},
        allow_overlap=True)
    diffs, _ = _run(ENTRY_SAVE_HISCORES,
                    lambda lib, buf: lib.g_save_hiscores_prologue(buf, FRAME_SAVE_HISCORES,
                                                                  CALLER_A1, CALLER_A2), pokes,
                    stop_pc=STOP_SAVE_HISCORES_PROLOGUE)
    assert not diffs, f"counter {counter:#x}\n{report(diffs)}"


def test_save_hiscores_writes_the_file_the_note_describes():
    """...and the forty bytes it wrote, read back out of the staged file.

    `../notes/frontend.md` §4's layout — six zero-padded score digits then two room digits, five
    times, no separators — is executed here rather than argued. The handle is created in TEXT mode,
    so a newline would be expanded; `itoa_padded` writes none.
    """
    scores, rooms = (100, 2500, 13000, 44500, 999999), (2, 7, 12, 23, 35)
    pokes = _hiscore_world(0x1208, scores, rooms, save_frame=FRAME_SAVE_HISCORES)
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_SAVE_HISCORES,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})
    staging = harness.OS_FS_STAGING
    written = bytes(final[staging:staging + HISCORE_FILE_BYTES])
    assert written == _hiscore_file(tuple(zip(scores, rooms)))


@pytest.mark.parametrize("offer", HISCORE_OFFERS)
def test_hiscore_insert_and_save(offer):
    """`hiscore_insert_and_save` run to `rts`, both arms.

    The candidate is compared against `hall_scores[0]`, the WORST entry, and an insert overwrites
    that slot, bubble-sorts five passes of four adjacent compares — enough for a value dropped at
    slot 0 to walk all the way to slot 4, which the second offer here does — and then writes the
    file. The equal case (candidate == the worst entry) is the boundary: the test is `>`, so it does
    not insert and never reaches `save_hiscores`.
    """
    candidate, pending_score, pending_room, scores = offer
    pokes = _hiscore_world(0x11f8 + (candidate & 0xff), scores, (1, 2, 3, 4, 5),
                           save_frame=FRAME_SAVE_FROM_INSERT,
                           extra={A_HISCORE_CANDIDATE: abi.long(candidate),
                                  A_HISCORE_PENDING_SCORE: abi.long(pending_score),
                                  A_HISCORE_PENDING_ROOM: abi.word(pending_room)})
    diffs, _ = _run(ENTRY_HISCORE_INSERT_AND_SAVE,
                    lambda lib, buf: lib.g_hiscore_insert_and_save(buf, FRAME_SAVE_FROM_INSERT,
                                                                   CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"{offer}\n{report(diffs)}"


def test_hiscore_insert_leaves_the_table_ascending():
    """...and the table really is sorted afterwards, which is what makes slot 4 the best entry and
    what `game_top_loop` seeds the displayed hi-score from."""
    scores, rooms = (100, 2500, 13000, 44500, 999999), (2, 7, 12, 23, 35)
    pokes = _hiscore_world(0x11f9, scores, rooms, save_frame=FRAME_SAVE_FROM_INSERT,
                           extra={A_HISCORE_CANDIDATE: abi.long(50000),
                                  A_HISCORE_PENDING_SCORE: abi.long(50000),
                                  A_HISCORE_PENDING_ROOM: abi.word(30)})
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_HISCORE_INSERT_AND_SAVE,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2})

    after = [_long(final, A_HALL_SCORES + slot * 4) for slot in range(HISCORE_SLOTS)]
    assert after == sorted(after) == [2500, 13000, 44500, 50000, 999999]
    assert _long(final, A_HALL_ROOMS + 3 * 4) == 30, "the room did not travel with its score"


# (player count, p1 score, p2 score, p1 best room, p2 best room, live score, best room reached).
# Both counts, and both whether the offer beats the table — the two-player arm offers twice, so the
# third row inserts once and the fourth twice.
SUBMIT_CASES = (
    (1, 0, 0, 0, 0, 500, 6),
    (2, 400, 300, 11, 12, 0, 0),
    (2, 0, 0, 1, 1, 0, 0),
    (2, 2000000, 300, 11, 12, 0, 0),
    (2, 2000000, 3000000, 11, 12, 0, 0),
)


@pytest.mark.parametrize("case", SUBMIT_CASES)
def test_hiscore_submit_players(case):
    """`hiscore_submit_players`, run to `rts`.

    In two-player mode it offers each player's own score and best room in turn; in one-player mode
    the caller has already filed the score in `hiscore_candidate` and this only fills the pending
    pair. The last two rows insert — once and twice — so the whole chain down to the file write runs.
    """
    players, p1_score, p2_score, p1_room, p2_room, score, max_room = case
    scores, rooms = (1000000, 1000000, 1000000, 1000000, 1000000), (1, 2, 3, 4, 5)
    pokes = _hiscore_world(0x11d6 + players, scores, rooms, save_frame=FRAME_SAVE_FROM_SUBMIT,
                           extra={A_PLAYER_COUNT: abi.word(players),
                                  A_P1_SCORE: abi.long(p1_score), A_P2_SCORE: abi.long(p2_score),
                                  A_P1_MAX_ROOM: abi.word(p1_room),
                                  A_P2_MAX_ROOM: abi.word(p2_room),
                                  A_SCORE: abi.long(score),
                                  A_MAX_ROOM_REACHED: abi.word(max_room),
                                  A_HISCORE_CANDIDATE: abi.long(0)})
    diffs, _ = _run(ENTRY_HISCORE_SUBMIT_PLAYERS,
                    lambda lib, buf: lib.g_hiscore_submit_players(buf, FRAME_SAVE_FROM_SUBMIT,
                                                                  CALLER_A1, CALLER_A2), pokes)
    assert not diffs, f"{case}\n{report(diffs)}"


def test_the_scratch_map_fits_inside_the_span_abi_reserves():
    """Every region this battery stages lies inside `test/abi.py`'s scratch window.

    The map keeps the machine's own relationships, so it grows from the base rather than being
    packed — and `SCRATCH_BYTES` is the bound `test_image_model.py` pins below the staged-file
    table. A region past it would be staged over the harness's own memory and the whole battery
    would be about something else.
    """
    assert SCRATCH_TOP <= abi.SCRATCH + abi.SCRATCH_BYTES, (
        f"the scratch map ends at {SCRATCH_TOP:#x}, past "
        f"{abi.SCRATCH + abi.SCRATCH_BYTES:#x}")
    assert BANK_ADDRESSES[-1] + DAT_BANK_BYTES < abi.STUB, (
        "the staged GHOST.DAT banks reach the stub band")
    assert BANK_BASE > emu.OS_HEAP_BASE + (GHOST_CELLS + BUBBLE_CELLS + 2) * TILE_BYTES, (
        "the staged banks overlap the bottom of the Malloc arena, where `build_sprite_bank`'s own "
        "62 allocations land")


# ================================================================================= the declared pins

# ==================================================== the front end's state machine
#
# `title_menu_loop` @ 0x115d6 and `game_top_loop` @ 0x101e6 — the two routines everything else in
# this project is called from. `../notes/frontend.md` §2 draws the machine.
#
# HOW THEY ARE RUN. Every region of both routines is a MID-ENTRY SLICE, entered with A6 STAGED — and
# staged ABOVE `emu.STACK_TOP`: the harness forces A7 to STACK_TOP, and the real routine's
# `link a6,#-n` puts A7 exactly `n` bytes below A6, so a frame at `STACK_TOP + n` reproduces that
# relationship and the callee frames a slice derives land where the oracle really puts them (the same
# argument as `FRAME_DRAW_ROOM_A6`'s above). `game_top_loop` is a `do { … } while (true)` and never
# returns; `title_menu_loop` does return, but every pass of it ends at a blocking console read the
# model cannot cross, which is the note below the menu's own section.

MENU_LOCAL_BYTES = 16                  # `link a6,#$fff0` @ 0x115d6
TOP_LOCAL_BYTES = 10                   # `link a6,#$fff6` @ 0x101e6
MENU_FRAME_COUNTER = -6                # the only frame local a case stages; `include/frontend.h`
                                       # spells it `(-6)`, which `test_constants.py`'s scraper reads
                                       # as no literal at all, so it cannot be a MIRRORS row

FRAME_MENU_SLICE_A6 = emu.STACK_TOP + MENU_LOCAL_BYTES
FRAME_TOP_SLICE_A6 = emu.STACK_TOP + TOP_LOCAL_BYTES

# ...and where `save_hiscores`' own A6 lands when the menu's opening reaches it, three `jsr`s down
# through `hiscore_submit_players` (which reserves nothing) and `hiscore_insert_and_save`. It is
# derived here exactly as `src/frontend.c` derives it, so that the two agree by construction — and
# the case that reaches it stages `SAVE_COUNTER_ON_ENTRY` there, which is what makes the derivation
# OBSERVABLE: the routine's first `graf_mouse` reads its mouse form out of that word.
SUBMIT_LOCAL_BYTES = 0                 # `link a6,#$0`    @ 0x11d6e
INSERT_LOCAL_BYTES = 10                # `link a6,#$fff6` @ 0x11f84
CALL_FRAME_COST = 8                    # a `jsr`'s return address + the callee's own saved A6
MENU_SUBMIT_FRAME = FRAME_MENU_SLICE_A6 - MENU_LOCAL_BYTES - CALL_FRAME_COST
MENU_INSERT_FRAME = MENU_SUBMIT_FRAME - SUBMIT_LOCAL_BYTES - CALL_FRAME_COST
MENU_SAVE_FRAME = MENU_INSERT_FRAME - INSERT_LOCAL_BYTES - CALL_FRAME_COST

# Where the demo file is staged in the scratch map, and the sound state a trigger walks.
DEMO_BUFFER = SCRATCH_TOP
DEMO_BUFFER_TOP = DEMO_BUFFER + DEMO_FILE_BYTES
assert DEMO_BUFFER_TOP < abi.SCRATCH + abi.SCRATCH_BYTES, (
    "the demo buffer runs past the scratch map that test_image_model.py pins")
SOUND_VOICE_SPAN = (A_SND_VOICE, A_SND_VOICE + SND_VOICES * SND_VOICE_BYTES)

# ...and the two file names that sit immediately above those records, INSIDE the guard band the seed
# writes either side of every span. `init_globals` builds them in the BSS (which is why `strings`
# finds neither in the .PRG), and the voice player opens them by name — so noise over them makes
# `os_fopen` refuse a name nothing staged and the whole run with it. They are put back as a later
# layer rather than by shrinking the guard, because the guard is what would catch a voice record
# written one word too far.
VOICE_NAMES_IN_BSS = {A_NAME_GHOST_VOI: b"GHOST.VOI\x00", A_NAME_GHOST_LOA: b"GHOST.LOA\x00"}
# ...and the ADJACENCY that makes the layer necessary is asserted rather than assumed: the repair is
# position-dependent, and if the voice records ever move it would silently stop covering the bytes
# the guard actually lands on while the guard went on eating something else.
assert SOUND_VOICE_SPAN[1] == A_NAME_GHOST_VOI, (
    "the voice records no longer end exactly at GHOST.VOI's name, so VOICE_NAMES_IN_BSS is repairing "
    "the wrong bytes — re-derive which globals the seed's guard band now covers")
assert A_NAME_GHOST_LOA < SOUND_VOICE_SPAN[1] + abi.GUARD_BYTES, (
    "GHOST.LOA's name is no longer inside the guard band, so half of this layer is dead")

# The `trap #9` vector is ZERO in the post-init image — `install_sound_vectors` @ 0x148ea writes it
# — so any case that can reach `sound_play` stages it or the oracle jumps to address 0 (STATUS.md,
# "Model gaps").
TRAP9_VECTOR = {TOS_VEC_TRAP9: abi.long(SND_TRAP9_HANDLER_ENTRY)}

# THE THREE VOICES ARE FREE ON ENTRY, and every case here says so rather than leaving it to the
# noise the seed writes over their records. `sound_play` REFUSES a voice whose priority is at or
# above the one it is offering (`include/sound.h`, SND_VC_PRIORITY), so over random priorities every
# trigger in this section is a no-op — and a trigger that never runs cannot tell one volume, one
# definition or one note from another. Measured: with the records left noisy, the level-clear
# trigger's volume could be changed from 9 to 8 with the whole suite green.
VOICES_FREE = {A_SND_VOICE + voice * SND_VOICE_BYTES + SND_VC_PRIORITY: abi.word(0)
               for voice in range(SND_VOICES)}

# ...AND THE SOUND IS ON, for the other half of the same reason. Every trigger in this section scales
# its volume by `A_sound_enabled` (`menu_volume`), which the loaded image holds as ZERO — so over the
# default every step multiplies to 0 and one volume constant is indistinguishable from another.
# Measured: `WIPE_SFX_VOLUME` could be changed from 8 to 1 with the whole suite green.
SOUND_ON = {A_SOUND_ENABLED: abi.word(1)}

# ...and what the YM2149 held on ENTRY, an input of the run like any other (TRAP_MODEL.md, Phase 6):
# `psg_gate` reads register 7 back to merge the mixer bits, and the model refuses to invent what
# nothing wrote. The whole file is declared rather than the registers one path happens to touch.
PSG_ON_ENTRY = {register: (0x37 + register * 0x13) & 0xff for register in range(16)}

# A hall of fame whose WORST entry no candidate can beat, so `hiscore_submit_players` — the first
# thing `title_menu_loop` does — takes its early return and no run below has to stage GHOST.SCR.
# The one case that DOES offer a winning score stages the file and says so.
HALL_UNBEATABLE = ((999999, 999999, 999999, 999999, 999999), (35, 35, 35, 35, 35))

for _name, _args in (("g_demo_play_record", 2),
                     ("g_demo_replay_from_record", 3), ("g_menu_attract_sequence", 3),
                     ("g_menu_hall_of_fame", 3), ("g_game_top_boot", 3),
                     ("g_menu_attract_slideshow", 3), ("g_menu_attract_title", 3),
                     ("g_menu_attract_slideshow_room", 3),
                     ("g_title_menu_open", 3), ("g_menu_draw", 3),
                     ("g_menu_ask_player_count", 3), ("g_menu_ask_practice_level", 2),
                     ("g_menu_read_level_tens", 2), ("g_menu_read_level_units", 3),
                     ("g_game_top_boot_tail", 3), ("g_game_top_boot_arm", 2),
                     ("g_game_new_game", 0), ("g_game_turn_init", 0), ("g_game_end_of_turn", 0),
                     ("g_game_player_change", 3), ("g_game_room_setup", 3),
                     ("g_game_room_frame_tail", 3), ("g_game_ending_sequence", 3),
                     ("g_game_room_exit", 3), ("g_game_over_card", 3)):
    _bind(_name, _args)


def _state_machine_world(seed, extra=None, mouse=(120, 70, 0), spans=(), room=1,
                         hall=HALL_UNBEATABLE):
    """The world every case in this section runs in: the two parameter blocks, an open workstation,
    the three screens in the machine's own relationship, the six GHOST.DAT banks, the sprite bank
    and its two MFDBs, the sound driver's vector and voice records, a mouse and a hall of fame.

    ONE WORLD FOR ALL OF THEM, because these routines COMPOSE: any of them may reach the room
    composer, the sprite protocol, the HUD painters and the sound triggers, and a per-slice world
    would be the same eight layers with a different one missing each time.
    """
    bank_pokes, bank_span = _sprite_bank_pokes()
    return abi.stage_world(
        seed,
        ((STAGE, PHYS + SCREEN_BYTES), bank_span, HALL_TABLE_SPAN, SOUND_VOICE_SPAN)
        + BANK_SPANS + SPRITE_MFDB_SPANS + tuple(spans),
        _pblock_pokes(), _workstation_pokes(), SPRITE_POINTER_POKES, GHOST_DAT_BANK_POKES,
        bank_pokes, SPRITE_MFDB_POKES, TRAP9_VECTOR, harness.mouse_state(*mouse),
        VOICE_NAMES_IN_BSS, VOICES_FREE, SOUND_ON, _hall_table_pokes(*hall),
        {A_ROOM_NUMBER: abi.word(room)},
        extra or {})


def _state_machine_run(entry, glue, pokes, frame_a6=None, **kwargs):
    """One differential, entered with this program's `a4`, the caller's A1/A2, the staged frame and
    the chip contents every `sound_play` on the way reads back."""
    regs = {"a1": CALLER_A1, "a2": CALLER_A2}
    if frame_a6 is not None:
        regs["a6"] = frame_a6
    kwargs.setdefault("psg_seed", PSG_ON_ENTRY)
    kwargs.setdefault("max_insns", STATE_MACHINE_MAX_INSNS)
    return abi.run_with_a4(entry, glue, pokes=pokes, regs=regs, **kwargs)


# Every case here composes several routines over a 32,000-byte screen, and the two end-of-room
# animations run a hundred frames of it; the four text cards each count 300,000 empty iterations.
# MEASURED, not guessed: every case in this section passes at 1,500,000 and five of them fail at
# 1,250,000, so the cap is a little over the worst one. It matters that it is not far more — the cap
# is what a slice that stops reaching its `stop_pc` runs into, and at 60,000,000 one such case took
# 17.8 s against a 2.0 s whole-file suite.
STATE_MACHINE_MAX_INSNS = 2_000_000

# --------------------------------------------------- title_menu_loop, region by region
#
# EVERY REGION ENDS AT A BLOCKING CONSOLE READ, and the reason is the trap model rather than the
# routine: each of this program's four key reads is `while (Cconis()) Crawcin(); c = Cnecin();` — a
# flush and then a blocking read — and the model's console is ONE queue that the flush empties, so a
# run that reaches the `Cnecin` finds nothing there and the call refuses (TRAP_MODEL.md, Phase 13).
# On a real machine the key arrives after the flush, which a staged queue cannot express. So a slice
# stops at the `Cnecin` push and the next one starts there with its own key staged; ../STATUS.md
# records the gap and what closing it would need.


def test_title_menu_open():
    """`title_menu_loop` @ 0x115d6 — the slice `[0x115d6, 0x116c4)`: the last game's scores offered
    to the hall of fame, the menu painted, and the keyboard flushed.

    THE FLUSH IS WHAT THE STAGED QUEUE IS FOR HERE: three keys are staged and the loop is expected
    to eat all three, which is the behaviour that stops a held key running the menu once per
    keystroke — and is why the read after it is a slice of its own.
    """
    pokes = _state_machine_world(0x115d6, extra=harness.console_keys(["G", "1", "2"]))
    diffs, _ = _state_machine_run(
        ENTRY_TITLE_MENU_OPEN,
        lambda lib, buf: lib.g_title_menu_open(buf, FRAME_MENU_SLICE_A6, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_TITLE_MENU_OPEN)
    assert not diffs, report(diffs)


def test_title_menu_open_submits_the_last_games_scores():
    """The one case that reaches the hall-of-fame WRITER, and the only thing in this section that
    can see a CALLEE FRAME at all.

    Every other case stages a table no candidate can beat, so `hiscore_submit_players` takes its
    early return; here the candidate beats the worst entry, the table is re-sorted and GHOST.SCR is
    created. `save_hiscores`' `graf_mouse` reads its mouse form out of its OWN frame — which this
    routine derives three `jsr`s deep — so this is what pins that derivation. Measured: with only
    the early-return cases, `CALL_FRAME_COST` could be halved with the whole suite green.
    """
    beatable = ((10, 20, 30, 40, 50), (1, 2, 3, 4, 5))
    pokes = _state_machine_world(
        0x11d6, hall=beatable,
        extra=abi.merge_pokes(harness.console_keys(["G"]),
                              {MENU_SAVE_FRAME + SAVE_FRAME_SLOT: abi.word(SAVE_COUNTER_ON_ENTRY)},
                              abi.long_pokes({A_HISCORE_CANDIDATE: 12345, A_SCORE: 12345}),
                              abi.word_pokes({A_MAX_ROOM_REACHED: 7, A_PLAYER_COUNT: 1}),
                              _staged(("A:GHOST.SCR", b"", HISCORE_FILE_CAPACITY))))
    diffs, _ = _state_machine_run(
        ENTRY_TITLE_MENU_OPEN,
        lambda lib, buf: lib.g_title_menu_open(buf, FRAME_MENU_SLICE_A6, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_TITLE_MENU_OPEN)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("queued", (0, 1, 3, 7))
def test_menu_draw(queued):
    """...and the same without the submitter — the slice `[0x115de, 0x116c4)`, which is where the
    redraw loop re-enters the routine after an arm that did not start a game.

    `queued` is how many keys the flush has to eat, from none to the model's whole queue.
    """
    keys = harness.console_keys(["a"] * queued) if queued else {}
    pokes = _state_machine_world(0x115de + queued, extra=keys)
    diffs, _ = _state_machine_run(
        ENTRY_MENU_DRAW,
        lambda lib, buf: lib.g_menu_draw(buf, FRAME_MENU_SLICE_A6, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_DRAW)
    assert not diffs, f"{queued} keys queued\n{report(diffs)}"


# The keys the menu dispatches on, plus the ones that only exercise the fold: a lower-case letter is
# folded to upper, and a key with bit 7 set is NEGATIVE as a sign-extended byte and so is not.
MENU_KEYS = ("G", "P", "D", "H", "g", "p", "d", "h", "z", "1", "`", "a", "\x80", "\xff", "\x00")


@pytest.mark.parametrize("key", MENU_KEYS)
def test_menu_read_key_and_fold(key):
    """The key that ends a pass — the slice `[0x116c4, 0x11700)`: one blocking read, the logical
    screen back onto the work buffer, and the fold to upper case.

    THE ANSWER IS COMPARED against the oracle's own D0 at the same PC, which is what the four
    compares after it branch on: the fold is a BYTE subtract and the test above it is on the
    SIGN-EXTENDED byte, so nothing at or above 0x80 is folded and only these rows say so.
    """
    pokes = _state_machine_world(0x116c4 + ord(key), extra=harness.console_key(key))
    diffs, info = _state_machine_run(
        ENTRY_MENU_READ_KEY,
        lambda lib, buf: lib.g_menu_read_key_and_fold(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                      CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_READ_KEY)
    assert not diffs, f"key {key!r}\n{report(diffs)}"
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff, (
        f"key {key!r}: the core answers {info['ret'] & 0xffff:#x}, the original "
        f"{info['regs']['d0'] & 0xffff:#x}")


def test_menu_ask_player_count():
    """`[G]`, the ask — the slice `[0x11708, 0x11774)`: the two lines onto the visible screen, and
    the flush the loop's first pass makes before it reads a digit."""
    pokes = _state_machine_world(0x11708, extra=harness.console_keys(["1", "2"]))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ASK_PLAYER_COUNT,
        lambda lib, buf: lib.g_menu_ask_player_count(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                     CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ASK_PLAYER_COUNT)
    assert not diffs, report(diffs)


# (key, the player count it chooses, whether the arm ends). '0' and 'x' are the two ways a key is
# neither 1 nor 2 — one is a digit and one is not — and both send the ask round again.
PLAYER_COUNT_KEYS = (("1", 1, True), ("2", 2, True), ("0", 0, False), ("x", 0, False),
                     ("3", 0, False))


@pytest.mark.parametrize("key,count,chosen", PLAYER_COUNT_KEYS)
def test_menu_read_player_count(key, count, chosen):
    """`[G]`, the read — the slice `[0x11774, 0x117cc)` when a count is chosen and
    `[0x11774, 0x1175a)` when it is not.

    THE BRANCH IS THE ANSWER, not a loop: the next pass would begin with a flush and another
    blocking read, which is where a slice has to end. The core reports which way it went and the
    case checks both the flag and the count that came out of it.
    """
    stop = STOP_MENU_PLAYER_COUNT_CHOSEN if chosen else STOP_MENU_PLAYER_COUNT_AGAIN
    pokes = _state_machine_world(0x11774 + ord(key), extra=harness.console_key(key))
    diffs, info = _state_machine_run(
        ENTRY_MENU_READ_PLAYER_COUNT,
        lambda lib, buf: lib.g_menu_read_player_count(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                      CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=stop)
    assert not diffs, f"key {key!r}\n{report(diffs)}"
    assert (info["ret"] & 0xffff != 0) == chosen, f"key {key!r}: the wrong arm was reported"


@pytest.mark.parametrize("key,count,chosen", PLAYER_COUNT_KEYS)
def test_menu_read_player_count_files_the_count(key, count, chosen):
    """...and the count the run leaves, which the diff proves equal but does not name."""
    pokes = _state_machine_world(0x11774 + ord(key), extra=harness.console_key(key))
    stop = STOP_MENU_PLAYER_COUNT_CHOSEN if chosen else STOP_MENU_PLAYER_COUNT_AGAIN
    image, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_MENU_READ_PLAYER_COUNT,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2,
                                          "a6": FRAME_MENU_SLICE_A6},
                                    stop_pc=stop, psg_seed=PSG_ON_ENTRY,
                                    max_insns=STATE_MACHINE_MAX_INSNS)
    assert _word(image, A_PLAYER_COUNT) == count, f"key {key!r}"


def test_menu_ask_practice_level():
    """`[P]`, the ask — the slice `[0x117de, 0x1183e)`: every score zeroed, one player, the prompt,
    and the first digit's flush."""
    pokes = _state_machine_world(
        0x117de, extra=abi.merge_pokes(harness.console_keys(["0", "5"]),
                                       abi.long_pokes({A_SCORE: 4321, A_P1_SCORE: 111,
                                                    A_P2_SCORE: 222}),
                                       abi.word_pokes({A_PLAYER_COUNT: 2})))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ASK_PRACTICE_LEVEL,
        lambda lib, buf: lib.g_menu_ask_practice_level(buf, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ASK_PRACTICE_LEVEL)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("key", ("0", "1", "3", "9", "x"))
def test_menu_read_level_tens(key):
    """`[P]`'s first digit — the slice `[0x1183e, 0x1186c)`: the read, filed as a WORD less '0', and
    then the second digit's flush. A non-digit is kept as whatever it is: the gate below is what
    rejects it."""
    pokes = _state_machine_world(0x1183e + ord(key), extra=harness.console_keys([key, "4"]))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_READ_LEVEL_TENS,
        lambda lib, buf: lib.g_menu_read_level_tens(buf, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_READ_LEVEL_TENS)
    assert not diffs, f"tens {key!r}\n{report(diffs)}"


# (tens already read, units key, the level, the grid square). The rows are both ends of the gate,
# the two digits' carry, one square from each of the six grid rows, and the two REFUSALS: level 0 is
# room 0, which sits behind the start square, and 36 is one past the last room.
PRACTICE_LEVELS = (
    (0, "1", 1, (5, 4)),
    (0, "9", 9, (4, 3)),
    (1, "0", 10, (4, 4)),
    (1, "7", 17, (3, 0)),
    (2, "4", 24, (1, 5)),
    (3, "5", 35, (0, 5)),
    (0, "0", 0, None),
    (3, "6", 36, None),
    (9, "9", 99, None),
)


@pytest.mark.parametrize("tens,units,level,square", PRACTICE_LEVELS)
def test_menu_read_level_units(tens, units, level, square):
    """`[P]`'s second digit and everything after it — the slice `[0x1186c, 0x1191e)`: the level
    assembled, the 0 < n < 36 gate, and the 6 x 6 search that turns the level into a square."""
    pokes = _state_machine_world(0x1186c + level,
                                 extra=abi.merge_pokes(harness.console_key(units),
                                                       abi.word_pokes({A_PRACTICE_GRID_ROW: tens})))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_READ_LEVEL_UNITS,
        lambda lib, buf: lib.g_menu_read_level_units(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                     CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_READ_LEVEL_UNITS)
    assert not diffs, f"level {level}\n{report(diffs)}"


@pytest.mark.parametrize("tens,units,level,square", PRACTICE_LEVELS)
def test_menu_read_level_units_finds_the_square(tens, units, level, square):
    """...and the square it found, which `game_top_loop` starts a practice game at. A level outside
    1..35 sets nothing at all, which is what keeps room 0 — the hall-of-fame backdrop — off the
    menu."""
    pokes = _state_machine_world(0x1186c + level,
                                 extra=abi.merge_pokes(harness.console_key(units),
                                                       abi.word_pokes({A_PRACTICE_GRID_ROW: tens})))
    image, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_MENU_READ_LEVEL_UNITS,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2,
                                          "a6": FRAME_MENU_SLICE_A6},
                                    stop_pc=STOP_MENU_READ_LEVEL_UNITS, psg_seed=PSG_ON_ENTRY,
                                    max_insns=STATE_MACHINE_MAX_INSNS)
    assert _word(image, A_PRACTICE_MODE) == (0 if square is None else 1), f"level {level}"
    if square is not None:
        assert (_word(image, A_PRACTICE_GRID_ROW), _word(image, A_PRACTICE_GRID_COL)) == square, (
            f"level {level} is not at grid {square}")


def test_the_two_random_divisors_are_distinct_addresses_holding_one_value():
    """The slideshow's LENGTH and its ROOM divide by 16794009.0 out of two SEPARATE DATA addresses.

    No run can tell them apart — `fp_dispatch` reads the operand's value, and the two hold the same
    eight bytes — so the pin is the addresses' own contents, exactly as
    `test_the_loaders_open_the_names_the_reconstruction_points_at` pins GHOST.SCR's two copies. A
    reconstruction that read one where the original reads the other is byte-identical, and this is
    the only thing that says which is which.
    """
    image = harness.BASE_IMAGE
    length = bytes(image[A_CONST_DEMO_LENGTH_DIVISOR:A_CONST_DEMO_LENGTH_DIVISOR + DOUBLE_BYTES])
    room = bytes(image[A_CONST_DEMO_ROOM_DIVISOR:A_CONST_DEMO_ROOM_DIVISOR + DOUBLE_BYTES])
    assert A_CONST_DEMO_LENGTH_DIVISOR != A_CONST_DEMO_ROOM_DIVISOR, (
        "the two divisors are one address, so the C should name it once")
    assert length == room == abi.double(DEMO_RANDOM_DIVISOR), (
        f"the two divisors hold {length.hex()} and {room.hex()}, not "
        f"{abi.double(DEMO_RANDOM_DIVISOR).hex()} — `../notes/frontend.md` §6 derives both attract "
        f"ranges from this value")


def test_the_menu_regions_meet_at_every_blocking_read():
    """The regions above TILE `title_menu_loop`'s straight-line paths with no gap, and every join is
    a `Cnecin` push — which is the whole claim this file makes about that routine.

    A gap would be a region no case runs and nobody notices; a join anywhere else would mean a
    slice really could have run further, and the model gap would be being used as an excuse.
    """
    for name, entry, stop in (("[G] ask", ENTRY_MENU_ASK_PLAYER_COUNT, ENTRY_MENU_READ_PLAYER_COUNT),
                              ("the menu", ENTRY_MENU_DRAW, ENTRY_MENU_READ_KEY),
                              ("[P] ask", ENTRY_MENU_ASK_PRACTICE_LEVEL, ENTRY_MENU_READ_LEVEL_TENS),
                              ("[P] tens", ENTRY_MENU_READ_LEVEL_TENS, ENTRY_MENU_READ_LEVEL_UNITS)):
        assert entry < stop, f"{name} is empty or backwards"
        assert bytes(harness.BASE_IMAGE[stop:stop + len(CNECIN_PUSH)]) == CNECIN_PUSH, (
            f"{name} stops at {stop:#x}, which is not a `move.w #$8,-(a7)` opening a Cnecin call")


# `move.w #$8,-(a7)` — GEMDOS Cnecin's selector pushed, which is where each region above ends.
CNECIN_PUSH = bytes.fromhex("3f3c0008")

# ------------------------------------------------------------------------------- the demo player

def _demo_pokes(records, cursor_record=0):
    """GHOST.DEM staged in the scratch map, with the replay cursor parked on one of its records."""
    body = bytes(records)
    assert len(body) <= DEMO_FILE_BYTES, "a staged demo is longer than the file the loader reads"
    return abi.merge_pokes(
        {DEMO_BUFFER: body},
        abi.long_pokes({A_DEMO_BASE: DEMO_BUFFER,
                     A_DEMO_CURSOR: DEMO_BUFFER + cursor_record * DEMO_RECORD_BYTES}))


# The six-byte records this battery drives one at a time, chosen for what each one reaches: the
# origin, a blowing cell of two different facings (the puff trigger), a popped bubble (the pop
# trigger), a record whose bytes are NEGATIVE (each is read signed and scaled), and the extremes.
DEMO_RECORDS = (
    (0, 0, 0, 0, 0, 0),
    (40, 30, 4, 60, 20, 7),          # ghost facing 0, blowing
    (10, 10, 29, 90, 40, 11),        # facing 5, blowing
    (50, 25, 3, 70, 35, 0),          # the bubble popped
    (-8, -8, 39, -4, -2, 4),         # negative coordinates, and facing 7 blowing
    (127, 127, 12, 127, 127, 12),
    (-128, -128, 0, -128, -128, 8),
)


def _demo_record_bytes(record):
    return bytes(value & 0xff for value in record)


@pytest.mark.parametrize("record", DEMO_RECORDS)
def test_demo_play_record(record):
    """ONE GHOST.DEM record — the slice `[0x11992, 0x11acc)`: six signed bytes into the six globals
    the renderer reads, the frame drawn, and the two sound triggers the record can fire."""
    body = _demo_record_bytes(record) + bytes(DEMO_RECORD_BYTES)
    pokes = _state_machine_world(0x1199 + (record[2] & 0xff),
                                 spans=((DEMO_BUFFER, DEMO_BUFFER_TOP),),
                                 extra=_demo_pokes(body))
    diffs, _ = _state_machine_run(
        ENTRY_DEMO_RECORD, lambda lib, buf: lib.g_demo_play_record(buf, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_DEMO_RECORD)
    assert not diffs, f"record {record}\n{report(diffs)}"


DEMO_FUZZ_CHUNKS = 8
DEMO_FUZZ_RECORDS = 8


def _random_demo_record(rng):
    """Six bytes with the two CELL INDICES kept inside the sprite bank they choose from.

    The four coordinate bytes are unconstrained — each is read signed and scaled, and a record may
    legitimately park a sprite off the play area. The other two are not free: `draw_sprites` uses
    them to index the ghost's 47 and the bubble's 13 pointer tables with no bound of its own, so a
    byte outside those ranges hands `vro_cpyfm` a pointer nothing allocated and the VDI model
    refuses the run. The real GHOST.DEM holds only legal indices, which is the same statement.
    """
    return bytes((rng.randrange(256), rng.randrange(256), rng.randrange(GHOST_CELLS),
                  rng.randrange(256), rng.randrange(256), rng.randrange(BUBBLE_CELLS)))


@pytest.mark.parametrize("chunk", range(DEMO_FUZZ_CHUNKS))
def test_demo_play_record_fuzz(chunk):
    """...and random records, CHUNK-SEEDED so the suite runs `DEMO_FUZZ_CHUNKS` times as many as one
    chunk does (`test/abi.py`'s `shard` docstring tells the two shard shapes apart)."""
    rng = random.Random(0x11992 + chunk)
    for index in range(DEMO_FUZZ_RECORDS):
        body = bytes(_random_demo_record(rng) + _random_demo_record(rng))
        pokes = _state_machine_world(0x11992 + chunk * 0x100 + index,
                                     spans=((DEMO_BUFFER, DEMO_BUFFER_TOP),),
                                     extra=_demo_pokes(body))
        diffs, _ = _state_machine_run(
            ENTRY_DEMO_RECORD, lambda lib, buf: lib.g_demo_play_record(buf, CALLER_A1, CALLER_A2),
            pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_DEMO_RECORD)
        assert not diffs, f"chunk {chunk} record {index} = {body[:6].hex()}\n{report(diffs)}"


# How many records the composition below chains. The whole replay is 980, which is far more than one
# oracle run can afford — each record redraws the room — so what this pins is the LOOP rather than
# the file: the cursor stepping six bytes a record, the counter falling, and the mouse poll at the
# end of each pass deciding whether there is another.
DEMO_CHAINED_RECORDS = 4


@pytest.mark.parametrize("first", (0, 1, 100))
def test_demo_replay_chains_records(first):
    """`DEMO_CHAINED_RECORDS` records of the REAL GHOST.DEM in one run — the slice
    `[0x11992, 0x11ae6)`, entered at the loop body as the routine's own `bra` skips into it.

    A per-record case cannot see the loop at all: it runs one body and stops. This runs the body,
    the test, the counter and the next body, over the game's own data, which is what says the cursor
    is stepped once per record and the counter read before it is decremented.
    """
    pokes = _state_machine_world(
        0x11ae + first, spans=((DEMO_BUFFER, DEMO_BUFFER_TOP),),
        extra=abi.merge_pokes(
            _demo_pokes(GHOST_DEM[:DEMO_FILE_BYTES], cursor_record=first),
            {FRAME_MENU_SLICE_A6 + MENU_FRAME_COUNTER: abi.long(DEMO_CHAINED_RECORDS - 1)}))
    diffs, _ = _state_machine_run(
        ENTRY_DEMO_RECORD,
        lambda lib, buf: lib.g_demo_replay_from_record(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                       CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_DEMO_REPLAY)
    assert not diffs, f"from record {first}\n{report(diffs)}"


# The mouse state an attract case runs under. With the button DOWN every phase of the sequence bails
# out at its own first test — which is what makes the whole 980-record replay, the slideshow and the
# 37,000-poll idle affordable in one run while still running one pass of each.
MOUSE_ABORT = (200, 100, 1)


def test_menu_attract_sequence():
    """`[D]`, phase one — the slice `[0x11930, 0x11ae6)`, with the left button held: room 1 composed
    and given its ambience, then ONE record of the replay.

    One record and not none, because the button is polled by the record body rather than before it —
    which is the loop's own shape, and why the abort is affordable here at all.
    """
    pokes = _state_machine_world(0x11930, mouse=MOUSE_ABORT,
                                 spans=((DEMO_BUFFER, DEMO_BUFFER_TOP),),
                                 extra=_demo_pokes(GHOST_DEM[:DEMO_FILE_BYTES]))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ATTRACT_SEQUENCE,
        lambda lib, buf: lib.g_menu_attract_sequence(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                     CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ATTRACT_SEQUENCE)
    assert not diffs, report(diffs)


# The `Random()` the slideshow draws BOTH its length and each of its rooms from. It is one poked
# longword per run (`harness.OS_RANDOM_VALUE`), so the two answers are not independent: 0 gives the
# shortest slideshow the range allows (5 rooms) of the lowest room it allows (1), which is what makes
# running the phase with the button UP affordable. The upper value is the 24-bit maximum, which is
# what `../notes/frontend.md` §6 derives both ranges' upper ends from — 15 rooms is too many to run,
# so it is used only with the button down.
SLIDESHOW_RANDOM_LOW = 0
# ...and the divisor both scalings use, at its two DATA addresses (include/frontend.h).
A_CONST_DEMO_LENGTH_DIVISOR = 0x250ec
A_CONST_DEMO_ROOM_DIVISOR = 0x25104
DEMO_RANDOM_DIVISOR = 16794009.000000015
DOUBLE_BYTES = 8
SLIDESHOW_RANDOM_HIGH = 0xffffff
# ...and the phase is 5 rooms x 30 frames of a 25,600-byte present, so it needs a cap of its own.
SLIDESHOW_MAX_INSNS = 20_000_000


@pytest.mark.parametrize("value", (SLIDESHOW_RANDOM_LOW, SLIDESHOW_RANDOM_HIGH))
def test_menu_attract_slideshow(value):
    """`[D]`, phase two — the slice `[0x11ae6, 0x11c34)`, with the left button held: the length drawn
    from `Random()` through the fp package, and the loop leaving at its first test.

    The two values are the range's own ends: `Random()` is one poked longword, and 0 and the 24-bit
    maximum are what `../notes/frontend.md` §6 derives 5 and 15 from. Only the LENGTH is observable
    here — it is drawn before the loop's first test — and one ROOM of the loop is the case below.
    """
    pokes = _state_machine_world(0x11ae6 + value, mouse=MOUSE_ABORT,
                                 extra={harness.OS_RANDOM_VALUE: abi.long(value)})
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ATTRACT_SLIDESHOW,
        lambda lib, buf: lib.g_menu_attract_slideshow(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                      CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ATTRACT_SLIDESHOW)
    assert not diffs, f"random {value:#x}\n{report(diffs)}"


@pytest.mark.parametrize("value", (SLIDESHOW_RANDOM_LOW, SLIDESHOW_RANDOM_HIGH))
def test_menu_attract_slideshow_room(value):
    """ONE room of it — the slice `[0x11b30, 0x11c1c)`, with the button UP so the whole body runs.

    THIS IS WHAT RUNS THE PHASE AT ALL. Everything inside the loop — the room roll's own three
    constants, `menu_show_room`, the ambience, the frame countdown and the THREE `Vsync`s, each with
    its own trampoline return address — is unreachable from the phase head with the button held, and
    unaffordable with it up (five rooms of thirty 25,600-byte presents fills the oracle's write
    ledger). Measured: with only the head's cases, the room roll's constants could be swapped and any
    of the three `Vsync` return addresses changed with the whole suite green.
    """
    pokes = _state_machine_world(0x11b30 + value, mouse=(200, 100, 0),
                                 extra={harness.OS_RANDOM_VALUE: abi.long(value)})
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ATTRACT_SLIDESHOW_ROOM,
        lambda lib, buf: lib.g_menu_attract_slideshow_room(buf, FRAME_MENU_SLICE_A6, CALLER_A1,
                                                           CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ATTRACT_SLIDESHOW_ROOM,
        max_insns=SLIDESHOW_MAX_INSNS)
    assert not diffs, f"random {value:#x}\n{report(diffs)}"


# The title phase's idle loop is DEMO_TITLE_POLLS mouse polls with nothing else in them, which is far
# more than one run can afford; the button-down row is what leaves it after one test. The button-UP
# row is what runs `show_presentation` and its trigger, which the other one skips entirely.
TITLE_MAX_INSNS = 30_000_000


@pytest.mark.parametrize("mouse", (MOUSE_ABORT, (200, 100, 0)))
def test_menu_attract_title(mouse):
    """`[D]`, phase three — the slice `[0x11c34, 0x11ca8)`: the title picture, its trigger, and the
    37,000-poll idle the mouse button ends."""
    bank_pokes, _bank_span = _sprite_bank_pokes()
    pokes = _state_machine_world(
        0x11c34 + mouse[2], mouse=mouse,
        spans=((BANK_ADDRESSES[DAT_BANK_PRE], BANK_ADDRESSES[DAT_BANK_PRE] + DAT_BANK_BYTES),),
        extra={BANK_ADDRESSES[DAT_BANK_PRE]: GHOST_PRE[:DAT_BANK_BYTES]})
    diffs, _ = _state_machine_run(
        ENTRY_MENU_ATTRACT_TITLE,
        lambda lib, buf: lib.g_menu_attract_title(buf, FRAME_MENU_SLICE_A6, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_ATTRACT_TITLE,
        max_insns=TITLE_MAX_INSNS)
    assert not diffs, f"mouse {mouse}\n{report(diffs)}"


@pytest.mark.parametrize("max_room", (0, 1, 17, 35))
def test_menu_hall_of_fame(max_room):
    """`[H]` — the slice `[0x11cba, 0x11d60)`: the table, the furthest room reached as the backdrop
    behind the HUD, room 0 as the picture, and an idle loop the button ends."""
    pokes = _state_machine_world(0x11cb + max_room, mouse=MOUSE_ABORT,
                                 extra=abi.word_pokes({A_MAX_ROOM_REACHED: max_room}))
    diffs, _ = _state_machine_run(
        ENTRY_MENU_HALL_OF_FAME,
        lambda lib, buf: lib.g_menu_hall_of_fame(buf, FRAME_MENU_SLICE_A6, CALLER_A1, CALLER_A2),
        pokes, frame_a6=FRAME_MENU_SLICE_A6, stop_pc=STOP_MENU_HALL_OF_FAME)
    assert not diffs, f"max room {max_room}\n{report(diffs)}"


# ---------------------------------------------------------------- game_top_loop, slice by slice

def _top_run(entry, glue, pokes, stop, **kwargs):
    """One `game_top_loop` slice: entered inside the routine, with its own frame staged."""
    return _state_machine_run(entry, glue, pokes, frame_a6=FRAME_TOP_SLICE_A6, stop_pc=stop,
                              **kwargs)


# The boot path's four files, staged under the names the program opens. GHOST.LOA and GHOST.VOI
# carry no drive letter because `init_globals` builds those two names in the BSS rather than in
# DATA (`test_voice.py` says so from the other side).
GHOST_LOA = (REC.parent / "bin" / "GHOST.LOA").read_bytes()
GHOST_VOI = (REC.parent / "bin" / "GHOST.VOI").read_bytes()
GHOST_SCR_SHIPPED = b"".join(b"%06d%02d" % (score, room)
                             for score, room in zip((10, 20, 30, 40, 50), (1, 2, 3, 4, 5)))


def test_game_top_boot():
    """`game_top_boot` @ 0x101e6 — the slice `[0x101e6, 0x10232)`: the mouse hidden, the voice player
    and the title picture loaded, the workstation cleared, the IKBD told to stop reporting the
    mouse, the logical screen moved to the work buffer and the picture shown.

    It stops at the `jsr play_voice`, which enters a SECOND PROGRAM the model cannot run
    (../STATUS.md, "Not reconstructed").
    """
    pokes = _state_machine_world(
        0x101e6, spans=((emu.OS_HEAP_BASE, emu.OS_HEAP_BASE + MALLOC_ARENA_SEEDED_BYTES),
                        (A_LOA_IMAGE, A_LOA_IMAGE + len(GHOST_LOA))),
        # THE OPENING `graf_mouse`'S MOUSE FORM CANNOT BE STAGED HERE, and ../STATUS.md records the
        # residual: the call pushes only a zero word and the mode, so the `addr_in` LONG the AES
        # reads spans that zero and the word at `frame - 10` — which, for a slice whose frame must
        # sit exactly `TOP_LOCAL_BYTES` above `emu.STACK_TOP`, IS `emu.STACK_TOP`, where the harness
        # writes its own sentinel return address. Both sides read the sentinel's zero high word, so
        # a reconstruction reading a different offset of the same frame would match anyway.
        extra=_staged(("GHOST.LOA", GHOST_LOA), ("GHOST.VOI", GHOST_VOI),
                      ("A:GHOST.PRE", GHOST_PRE)))
    diffs, _ = _top_run(ENTRY_GAME_TOP_BOOT,
                        lambda lib, buf: lib.g_game_top_boot(buf, FRAME_TOP_SLICE_A6, CALLER_A1,
                                                             CALLER_A2),
                        pokes, STOP_GAME_TOP_BOOT)
    assert not diffs, report(diffs)


def test_game_top_boot_tail():
    """`game_top_boot_tail` @ 0x10236 — the slice `[0x10236, 0x1024e)`: the six level pictures and
    the hall of fame read off disk, then the IKBD told to report the mouse again."""
    pokes = _state_machine_world(
        0x10236, spans=((emu.OS_HEAP_BASE, emu.OS_HEAP_BASE + MALLOC_ARENA_SEEDED_BYTES),),
        extra=_staged(("A:GHOST.DAT", GHOST_DAT), ("A:GHOST.SCR", GHOST_SCR_SHIPPED)))
    diffs, _ = _top_run(ENTRY_GAME_TOP_BOOT_TAIL,
                        lambda lib, buf: lib.g_game_top_boot_tail(buf, FRAME_TOP_SLICE_A6,
                                                                  CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_TOP_BOOT_TAIL)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("hall", (HALL_UNBEATABLE, ((0, 0, 0, 0, 0), (1, 1, 1, 1, 1))))
def test_game_top_boot_arm(hall):
    """`game_top_boot_arm` @ 0x10258 — the slice `[0x10258, 0x1027e)`: the sixty sprite cells
    grabbed, the sound driver installed and silenced, GHOST.DEM read, and the four globals a fresh
    boot starts from — one of which is the displayed high score, taken from the hall of fame's BEST
    entry (its LAST, since the table is sorted ascending)."""
    pokes = _state_machine_world(
        0x10258 + hall[0][0], hall=hall,
        spans=((emu.OS_HEAP_BASE, emu.OS_HEAP_BASE + MALLOC_ARENA_SEEDED_BYTES),),
        extra=_staged(("A:GHOST.DEM", GHOST_DEM)))
    diffs, _ = _top_run(ENTRY_GAME_TOP_BOOT_ARM,
                        lambda lib, buf: lib.g_game_top_boot_arm(buf, CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_TOP_BOOT_ARM)
    assert not diffs, f"hall {hall[0]}\n{report(diffs)}"


@pytest.mark.parametrize("practice", (0, 1))
@pytest.mark.parametrize("score", (0, 12345))
def test_game_new_game(practice, score):
    """`game_new_game` @ 0x1027e — the slice `[0x1027e, 0x102b0)`, which ends at the `jsr
    title_menu_loop`: both players back in, the whole world reset, and the score offered to the hall
    of fame — except in a practice game, which scores nothing and offers zero."""
    pokes = _state_machine_world(0x1027e + practice * 4 + (score & 0xff),
                                 extra=abi.merge_pokes(
                                     abi.word_pokes({A_PRACTICE_MODE: practice}),
                                     abi.long_pokes({A_SCORE: score})))
    diffs, _ = _top_run(ENTRY_GAME_NEW_GAME, lambda lib, buf: lib.g_game_new_game(buf),
                        pokes, STOP_GAME_NEW_GAME)
    assert not diffs, f"practice {practice} score {score}\n{report(diffs)}"


@pytest.mark.parametrize("practice,grid", ((0, (0, 0)), (1, (2, 3)), (1, (5, 5))))
@pytest.mark.parametrize("player_count", (1, 2))
def test_game_turn_init(practice, grid, player_count):
    """`game_turn_init` @ 0x102b4 — the slice `[0x102b4, 0x1037a)`: where the chosen game starts, and
    both players' twenty-slot shelves seeded from it. A practice game starts at the square `[P]`
    found; an ordinary one at (5, 4), which IS room 1."""
    grid_row, grid_col = grid
    pokes = _state_machine_world(
        0x102b4 + practice * 0x40 + grid_row * 8 + grid_col + player_count,
        extra=abi.word_pokes({A_PRACTICE_MODE: practice, A_PLAYER_COUNT: player_count,
                           A_PRACTICE_GRID_ROW: grid_row, A_PRACTICE_GRID_COL: grid_col}))
    diffs, _ = _top_run(ENTRY_GAME_TURN_INIT, lambda lib, buf: lib.g_game_turn_init(buf),
                        pokes, STOP_GAME_TURN_INIT)
    assert not diffs, f"practice {practice} grid {grid} players {player_count}\n{report(diffs)}"


# Whose turn it is, whether the other player is still in, and how many lives each has left — the
# three things `game_player_change` branches on. Each row is (p1_turn, p2_turn, p1_lives, p2_lives,
# p1_playing, p2_playing).
PLAYER_CHANGE_STATES = (
    (0, 1, 5, 5, 1, 1),          # the first handover of a fresh game: player one comes up
    (1, 0, 5, 5, 1, 1),          # ...and back to player two
    (1, 0, -1, 5, 1, 1),         # player one has run out: the card, then player two's turn
    (0, 1, 5, -1, 1, 1),         # ...and the other way round
    (1, 0, -1, -1, 0, 1),        # both out, and player one is not playing any more
    (0, 1, 3, 3, 1, 0),          # the other player is out, so the turn does NOT change hands
)


@pytest.mark.parametrize("state", PLAYER_CHANGE_STATES)
@pytest.mark.parametrize("player_count", (1, 2))
def test_game_player_change(state, player_count):
    """`game_player_change` @ 0x1037a — the slice `[0x1037a, 0x105e0)`, and the whole of two-player
    mode: the "G A M E   O V E R" card for a player who has run out, the handover, the incoming
    player's twenty slots and 58-word world put back, and the "P L A Y E R  x" card.

    A ONE-PLAYER GAME SKIPS ALL OF IT, which is the `player_count` row: the slice is entered and
    returns having written nothing, and that is as much a behaviour as the rest.
    """
    p1_turn, p2_turn, p1_lives, p2_lives, p1_playing, p2_playing = state
    pokes = _state_machine_world(
        0x1037a + p1_turn * 2 + p2_turn + (p1_lives & 7) * 8 + player_count,
        extra=abi.merge_pokes(
            abi.word_pokes({A_PLAYER_COUNT: player_count, A_SHOW_PLAYER_CHANGE: 1,
                         A_P1_TURN: p1_turn, A_P2_TURN: p2_turn,
                         A_P1_PLAYING: p1_playing, A_P2_PLAYING: p2_playing,
                         A_P1_MAX_ROOM: 12, A_P2_MAX_ROOM: 7,
                         A_P1_BONUS_BAR: 0x100, A_P2_BONUS_BAR: 0x80,
                         A_P1_GRID_COL: 2, A_P2_GRID_COL: 4,
                         A_P1_GRID_ROW: 3, A_P2_GRID_ROW: 1,
                         A_P1_DEATHS_IN_ROOM: 1, A_P2_DEATHS_IN_ROOM: 2,
                         A_P1_ENTRY_DIR: 0, A_P2_ENTRY_DIR: 3}),
            abi.long_pokes({A_P1_LIVES: p1_lives & 0xffffffff, A_P2_LIVES: p2_lives & 0xffffffff,
                         A_P1_SCORE: 4321, A_P2_SCORE: 8765})))
    diffs, _ = _top_run(ENTRY_GAME_PLAYER_CHANGE,
                        lambda lib, buf: lib.g_game_player_change(buf, FRAME_TOP_SLICE_A6,
                                                                  CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_PLAYER_CHANGE)
    assert not diffs, f"{state} players {player_count}\n{report(diffs)}"


def test_game_player_change_is_skipped_without_a_handover():
    """...and the other way it does nothing: two players, but no handover pending."""
    pokes = _state_machine_world(0x1038, extra=abi.word_pokes({A_PLAYER_COUNT: 2,
                                                            A_SHOW_PLAYER_CHANGE: 0}))
    diffs, _ = _top_run(ENTRY_GAME_PLAYER_CHANGE,
                        lambda lib, buf: lib.g_game_player_change(buf, FRAME_TOP_SLICE_A6,
                                                                  CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_PLAYER_CHANGE)
    assert not diffs, report(diffs)


# (grid_row, grid_col, entry_dir, max_room_reached, practice, player_count, show_player_change).
# The rows cover: a fresh room entered from the left, one entered from BELOW (the only way this game
# awards a spare life), a room already seen, a practice room (whose entry direction comes from the
# room number rather than from the previous room) and the two-player re-entry.
ROOM_SETUP_STATES = (
    (5, 4, 0, 0, 0, 1, 0),
    (4, 0, 1, 5, 0, 1, 0),
    (3, 3, 2, 35, 0, 1, 0),
    (0, 5, 3, 0, 1, 1, 0),
    # ...and the other two arms of the practice entry direction, which is THREE ranges and five
    # SINGLETONS in the original — none of which any row reached until these five. The grid squares
    # are chosen for the table's own boundaries — BOTH ENDS of each range, or a range that moved by
    # one at the end nobody reached would survive: (5,4)/(5,0) are rooms 1 and 5, (3,4)/(3,0) are 13
    # and 17, (1,4)/(1,0) are 25 and 29; (4,0) is room 6, one of the five singletons. The row above,
    # room 35, is the fall-through.
    (5, 4, 3, 0, 1, 1, 0),
    (5, 0, 3, 0, 1, 1, 0),
    (3, 4, 3, 0, 1, 1, 0),
    (3, 0, 3, 0, 1, 1, 0),
    (1, 4, 3, 0, 1, 1, 0),
    (1, 0, 3, 0, 1, 1, 0),
    (4, 0, 3, 0, 1, 1, 0),
    (2, 2, 1, 35, 0, 2, 1),
)


@pytest.mark.parametrize("state", ROOM_SETUP_STATES)
def test_game_room_setup(state):
    """`game_room_setup` @ 0x105e0 — the slice `[0x105e0, 0x1078a)`: the room the grid square names,
    the bubble placed at the entry point it arrives through, the room composed and slid in, the HUD
    drawn, and the bonus bar refilled the first time a room is seen."""
    grid_row, grid_col, entry_dir, max_room, practice, players, handover = state
    pokes = _state_machine_world(
        0x105e0 + grid_row * 8 + grid_col + entry_dir * 64,
        extra=abi.merge_pokes(
            abi.word_pokes({A_GRID_ROW: grid_row, A_GRID_COL: grid_col, A_ENTRY_DIR: entry_dir,
                         A_MAX_ROOM_REACHED: max_room, A_PRACTICE_MODE: practice,
                         A_PLAYER_COUNT: players, A_SHOW_PLAYER_CHANGE: handover}),
            abi.long_pokes({A_LIVES: 3, A_SCORE: 4242, A_HI_SCORE: 90000})))
    diffs, _ = _top_run(ENTRY_GAME_ROOM_SETUP,
                        lambda lib, buf: lib.g_game_room_setup(buf, FRAME_TOP_SLICE_A6, CALLER_A1,
                                                               CALLER_A2),
                        pokes, STOP_GAME_ROOM_SETUP)
    assert not diffs, f"{state}\n{report(diffs)}"


# (bubble_x, bubble_y, room, bonus_tick, bonus_bar, ambient, lives). The rows cover: an ordinary
# frame, each of the four exits, the bar's three-frame tick and its floor, the room-35 win, and the
# ambient countdown underflowing (which is the only thing that re-rolls it).
ROOM_FRAME_STATES = (
    (160, 60, 12, 2, 0x100, 5, 3),
    (0x121, 60, 12, 1, 0x100, 5, 3),
    (-1, 60, 12, 0, 0x24, 5, 3),
    (160, 0x81, 12, 0, 0x23, 5, 3),
    (160, -1, 12, 2, 0x100, 0, 3),
    (0xc4, 60, 35, 2, 0x100, 5, 3),
    (0xc3, 60, 35, 2, 0x100, 5, 3),
    (160, 60, 12, 2, 0x100, 5, -1),
)


@pytest.mark.parametrize("state", ROOM_FRAME_STATES)
def test_game_room_frame_tail(state):
    """`game_room_frame_tail` @ 0x10792 — the slice `[0x10792, 0x108d2)`, entered where
    `game_frame_update` returns: the bonus bar's three-frame tick, the four ways out of a room and
    the fifth that is winning, the room's own ambience, and the five calls that put the frame up."""
    bubble_x, bubble_y, room, tick, bar, ambient, lives = state
    pokes = _state_machine_world(
        0x10792 + (bubble_x & 0xff) + (bubble_y & 0xff) * 4, room=room,
        extra=abi.merge_pokes(
            abi.word_pokes({A_BUBBLE_X: bubble_x, A_BUBBLE_Y: bubble_y, A_BONUS_TICK: tick,
                         A_BONUS_BAR: bar, A_AMBIENT_SFX_COUNTDOWN: ambient, A_IN_ROOM: 1,
                         A_GRID_ROW: 3, A_GRID_COL: 3, A_ENTRY_DIR: 0,
                         A_GHOST_X: 80, A_GHOST_Y: 40, A_GHOST_TILE: 17,
                         A_BUBBLE_FRAME: 7}),
            abi.long_pokes({A_LIVES: lives & 0xffffffff, A_SCORE: 1234, A_HI_SCORE: 5678})))
    diffs, _ = _top_run(ENTRY_GAME_ROOM_FRAME_TAIL,
                        lambda lib, buf: lib.g_game_room_frame_tail(buf, FRAME_TOP_SLICE_A6,
                                                                    CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_ROOM_FRAME_TAIL)
    assert not diffs, f"{state}\n{report(diffs)}"


# (player_count, p1_turn, bonus_bar). The last row's bar is ALREADY AT THE FLOOR, so the tally runs
# zero times — which is the only way the level-clear trigger's own volume survives to the end of the
# run. Measured: with every row cashing a bar in, the trigger's volume could be changed from 9 to 8
# with the whole suite green, because each tally step rewrites the same voice record.
ENDING_STATES = ((1, 1, 0x50), (2, 1, 0x50), (2, 0, 0x50), (1, 1, TOP_BONUS_BAR_FLOOR))


@pytest.mark.parametrize("player_count,p1_turn,bonus_bar", ENDING_STATES)
def test_game_ending_sequence(player_count, p1_turn, bonus_bar):
    """`game_ending_sequence` @ 0x108ec — the slice `[0x108ec, 0x10ce0)`: the whole of winning. The
    ghost walks right to room 35's door, the door's two objects are opened and then retired, the
    ghost falls through, the bonus bar is cashed in at TOP_BONUS_PER_STEP a step, and the winner's
    turn is parked (two players) or the game ends (one)."""
    pokes = _state_machine_world(
        0x108ec + player_count * 2 + p1_turn + bonus_bar, room=35,
        extra=abi.merge_pokes(
            abi.word_pokes({A_PLAYER_COUNT: player_count, A_P1_TURN: p1_turn,
                         A_P2_TURN: 1 - p1_turn, A_P1_PLAYING: 1, A_P2_PLAYING: 1,
                         A_BONUS_BAR: bonus_bar, A_MAX_ROOM_REACHED: 35,
                         A_GHOST_X: 150, A_GHOST_Y: 60, A_GHOST_TILE: 22,
                         A_BUBBLE_X: 0xf8, A_BUBBLE_Y: 0xffee, A_BUBBLE_FRAME: 6}),
            abi.long_pokes({A_SCORE: 20000, A_HI_SCORE: 30000, A_LIVES: 2})))
    diffs, _ = _top_run(ENTRY_GAME_ENDING_SEQUENCE,
                        lambda lib, buf: lib.g_game_ending_sequence(buf, FRAME_TOP_SLICE_A6,
                                                                    CALLER_A1, CALLER_A2),
                        pokes, STOP_GAME_ENDING_SEQUENCE)
    assert not diffs, f"players {player_count} p1_turn {p1_turn} bar {bonus_bar}\n{report(diffs)}"


# (practice, lives, show_player_change, max_room_reached, deaths_in_room, bonus_bar). The rows
# cover: the ordinary exit from a fresh room (which awards the room bonus and the tally), an exit
# from a room already visited (which awards neither), a practice game (which ends the turn), a turn
# that has already run out, a pending handover, and a room left after several deaths.
ROOM_EXIT_STATES = (
    (0, 2, 0, 0, 0, 0x50),
    (0, 2, 0, 35, 0, 0x50),
    (0, 2, 0, 0, 3, 0x2d),
    # 100 deaths is far more than five lives can produce and is STAGED rather than reached: the
    # bonus is `5000 - deaths * 500` computed in a WORD and only then widened, and the game's own
    # data never overflows that word. Measured as a survivor without this row.
    (0, 2, 0, 0, 100, 0x50),
    (1, 2, 0, 0, 0, 0x50),
    (0, -1, 0, 0, 0, 0x50),
    (0, 2, 1, 0, 0, 0x50),
)


@pytest.mark.parametrize("state", ROOM_EXIT_STATES)
def test_game_room_exit(state):
    """`game_room_exit` @ 0x10af8 — the slice `[0x10af8, 0x10ce0)`: leaving a room the ordinary way.
    The bubble is popped and parked, the ghost walks back to its first cell, the room's own bonus is
    awarded the FIRST time it is left, and the bar is cashed in at half the winning rate."""
    practice, lives, handover, max_room, deaths, bar = state
    pokes = _state_machine_world(
        0x10af8 + practice * 32 + (lives & 7) * 4 + handover, room=12,
        extra=abi.merge_pokes(
            abi.word_pokes({A_PRACTICE_MODE: practice, A_SHOW_PLAYER_CHANGE: handover,
                         A_MAX_ROOM_REACHED: max_room, A_DEATHS_IN_ROOM: deaths,
                         A_BONUS_BAR: bar, A_GRID_ROW: 3, A_GRID_COL: 3,
                         A_GHOST_X: 100, A_GHOST_Y: 50, A_GHOST_TILE: 33, A_BUBBLE_FRAME: 9}),
            abi.long_pokes({A_LIVES: lives & 0xffffffff, A_SCORE: 8000, A_HI_SCORE: 9000})))
    diffs, _ = _top_run(ENTRY_GAME_ROOM_EXIT,
                        lambda lib, buf: lib.g_game_room_exit(buf, FRAME_TOP_SLICE_A6, CALLER_A1,
                                                              CALLER_A2),
                        pokes, STOP_GAME_ROOM_EXIT)
    assert not diffs, f"{state}\n{report(diffs)}"


# (player_count, p1_turn, p1_lives, p2_lives, lives)
END_OF_TURN_STATES = (
    (1, 1, 5, 5, 3),
    (1, 1, 5, 5, -1),
    (2, 1, -1, 5, -1),
    (2, 0, 5, -1, -1),
    (2, 1, 5, -1, 3),
    (2, 0, -1, 5, 3),
)


@pytest.mark.parametrize("state", END_OF_TURN_STATES)
def test_game_end_of_turn(state):
    """`game_end_of_turn` @ 0x10ce0 — the slice `[0x10ce0, 0x10d34)`: who, if anyone, is still in.
    A two-player game asks each player's own life count and only about the one whose turn it was; a
    one-player game asks the live count and takes both players out with it."""
    player_count, p1_turn, p1_lives, p2_lives, lives = state
    pokes = _state_machine_world(
        0x10ce0 + player_count * 8 + p1_turn * 4 + (lives & 3),
        extra=abi.merge_pokes(
            abi.word_pokes({A_PLAYER_COUNT: player_count, A_P1_TURN: p1_turn,
                         A_P2_TURN: 1 - p1_turn, A_P1_PLAYING: 1, A_P2_PLAYING: 1,
                         A_SHOW_PLAYER_CHANGE: 0}),
            abi.long_pokes({A_P1_LIVES: p1_lives & 0xffffffff, A_P2_LIVES: p2_lives & 0xffffffff,
                         A_LIVES: lives & 0xffffffff})))
    diffs, _ = _top_run(ENTRY_GAME_END_OF_TURN, lambda lib, buf: lib.g_game_end_of_turn(buf),
                        pokes, STOP_GAME_END_OF_TURN)
    assert not diffs, f"{state}\n{report(diffs)}"


@pytest.mark.parametrize("player_count,practice", ((1, 0), (1, 1), (2, 0)))
def test_game_over_card(player_count, practice):
    """`game_over_card` @ 0x10d44 — the slice `[0x10d44, 0x1027e)`, which ends at the branch back to
    the top of the game loop. ONE-PLAYER, NON-PRACTICE games only: a two-player game has already
    shown each player their own card and a practice game shows none."""
    pokes = _state_machine_world(0x10d44 + player_count * 2 + practice,
                                 extra=abi.word_pokes({A_PLAYER_COUNT: player_count,
                                                    A_PRACTICE_MODE: practice}))
    diffs, _ = _top_run(ENTRY_GAME_OVER_CARD,
                        lambda lib, buf: lib.g_game_over_card(buf, FRAME_TOP_SLICE_A6, CALLER_A1,
                                                              CALLER_A2),
                        pokes, STOP_GAME_OVER_CARD)
    assert not diffs, f"players {player_count} practice {practice}\n{report(diffs)}"


MIRRORS = (
    ("A_VDI_PBLOCK", "include/frontend.h", "A_vdi_pblock"),
    ("A_VDI_CONTRL", "include/frontend.h", "A_vdi_contrl"),
    ("A_VDI_INTIN", "include/frontend.h", "A_vdi_intin"),
    ("A_VDI_PTSIN", "include/frontend.h", "A_vdi_ptsin"),
    ("A_VDI_INTOUT", "include/frontend.h", "A_vdi_intout"),
    ("A_VDI_PTSOUT", "include/frontend.h", "A_vdi_ptsout"),
    ("A_VDI_HANDLE", "include/frontend.h", "A_vdi_handle"),
    ("A_VDI_WORK_IN", "include/frontend.h", "A_vdi_work_in"),
    ("A_VDI_WORK_OUT", "include/frontend.h", "A_vdi_work_out"),
    ("AES_CONTROL_TABLE", "include/frontend.h", "AES_CONTROL_TABLE"),
    ("A_AES_AP_ID", "include/frontend.h", "A_aes_ap_id"),
    ("A_AES_PBLOCK", "include/frontend.h", "A_aes_pblock"),
    ("A_AES_P_CONTROL", "include/frontend.h", "A_aes_p_control"),
    ("A_AES_ADDR_OUT", "include/frontend.h", "A_aes_addr_out"),
    ("A_AES_ADDR_IN", "include/frontend.h", "A_aes_addr_in"),
    ("A_AES_INT_OUT", "include/frontend.h", "A_aes_int_out"),
    ("A_AES_INT_IN", "include/frontend.h", "A_aes_int_in"),
    ("A_AES_GLOBAL", "include/frontend.h", "A_aes_global"),
    ("A_AES_CONTROL", "include/frontend.h", "A_aes_control"),
    ("AES_TABLE_FIRST_OPCODE", "include/frontend.h", "AES_TABLE_FIRST_OPCODE"),
    ("AES_TABLE_STRIDE", "include/frontend.h", "AES_TABLE_STRIDE"),
    ("AES_CONTROL_COUNT_SLOTS", "include/frontend.h", "AES_CONTROL_COUNT_SLOTS"),
    ("A_SCREEN_REZ", "include/frontend.h", "A_screen_rez"),
    ("A_SUPER_ARG", "include/frontend.h", "A_super_arg"),
    ("A_SUPER_SAVED_SSP", "include/frontend.h", "A_super_saved_ssp"),
    ("A_CONTERM_ADDR_W", "include/frontend.h", "A_conterm_addr_w"),
    ("A_CONTERM_ADDR_L", "include/frontend.h", "A_conterm_addr_l"),
    ("CONTERM_ADDRESS", "include/frontend.h", "CONTERM_ADDRESS"),
    ("WORK_IN_ONES", "include/frontend.h", "WORK_IN_ONES"),
    ("WORK_IN_COORD_RASTER", "include/frontend.h", "WORK_IN_COORD_RASTER"),
    ("XBIOS_GETREZ_LOW_RES", "include/frontend.h", "XBIOS_GETREZ_LOW_RES"),
    ("A_PRE_PALETTE", "include/frontend.h", "A_pre_palette"),
    ("DAT_BANK_PRE", "include/frontend.h", "DAT_BANK_PRE"),
    ("PALETTE_BYTES", "include/frontend.h", "PALETTE_BYTES"),
    ("A_HALL_SCORES", "include/frontend.h", "A_hall_scores"),
    ("A_HALL_ROOMS", "include/frontend.h", "A_hall_rooms"),
    ("A_GHOST_SPRITE", "include/frontend.h", "A_ghost_sprite"),
    ("A_BUBBLE_SPRITE", "include/frontend.h", "A_bubble_sprite"),
    ("A_GHOST_BG", "include/frontend.h", "A_ghost_bg"),
    ("A_BUBBLE_BG", "include/frontend.h", "A_bubble_bg"),
    ("TILE_BYTES", "include/blit.h", "TILE_BYTES"),
    ("TILE_PIXELS", "include/blit.h", "TILE_PIXELS"),
    ("VDI_MODE_S_ONLY", "include/frontend.h", "VDI_MODE_S_ONLY"),
    ("VDI_MODE_S_OR_D", "include/frontend.h", "VDI_MODE_S_OR_D"),
    ("A_DEMO_BASE", "include/frontend.h", "A_demo_base"),
    ("A_DEMO_CURSOR", "include/frontend.h", "A_demo_cursor"),
    ("A_NAME_GHOST_DEM", "include/frontend.h", "A_name_ghost_dem"),
    ("A_NAME_GHOST_PRE", "include/frontend.h", "A_name_ghost_pre"),
    ("A_NAME_GHOST_SCR", "include/frontend.h", "A_name_ghost_scr"),
    ("A_NAME_GHOST_SCR_CREAT", "include/frontend.h", "A_name_ghost_scr_creat"),
    ("A_NAME_GHOST_DAT", "include/frontend.h", "A_name_ghost_dat"),
    ("DEMO_FILE_BYTES", "include/frontend.h", "DEMO_FILE_BYTES"),
    ("PICTURE_BYTES", "include/frontend.h", "PICTURE_BYTES"),
    ("DAT_BANKS_FROM_FILE", "include/frontend.h", "DAT_BANKS_FROM_FILE"),
    ("HISCORE_SLOTS", "include/frontend.h", "HISCORE_SLOTS"),
    ("HISCORE_SCORE_DIGITS", "include/frontend.h", "HISCORE_SCORE_DIGITS"),
    ("HISCORE_ROOM_DIGITS", "include/frontend.h", "HISCORE_ROOM_DIGITS"),
    ("A_SCREEN_PHYS", "include/blit.h", "A_screen_phys"),
    ("A_SCREEN_BACK", "include/blit.h", "A_screen_back"),
    ("A_DAT_BANK", "include/blit.h", "A_dat_bank"),
    ("A_MFDB_SRC", "include/blit.h", "A_mfdb_src"),
    ("A_MFDB_DST", "include/blit.h", "A_mfdb_dst"),
    ("SCREEN_BYTES", "include/blit.h", "SCREEN_BYTES"),
    ("A_HISCORE_CANDIDATE", "include/frontend.h", "A_hiscore_candidate"),
    ("A_HISCORE_PENDING_SCORE", "include/frontend.h", "A_hiscore_pending_score"),
    ("A_HISCORE_PENDING_ROOM", "include/frontend.h", "A_hiscore_pending_room"),
    ("A_PLAYER_COUNT", "include/frontend.h", "A_player_count"),
    ("A_P2_SCORE", "include/frontend.h", "A_p2_score"),
    ("A_P1_SCORE", "include/frontend.h", "A_p1_score"),
    ("A_P2_MAX_ROOM", "include/frontend.h", "A_p2_max_room"),
    ("A_P1_MAX_ROOM", "include/frontend.h", "A_p1_max_room"),
    ("HALL_BACKDROP_ROOM", "include/frontend.h", "HALL_BACKDROP_ROOM"),
    ("A_TEXT_SCORE_LABELS", "include/frontend.h", "A_text_score_labels"),
    ("TEXT_SCORE_LABEL_BYTES", "include/frontend.h", "TEXT_SCORE_LABEL_BYTES"),
    ("A_TEXT_HALL", "include/frontend.h", "A_text_hall"),
    ("A_PRACTICE_MODE", "include/frontend.h", "A_practice_mode"),
    ("A_PRACTICE_GRID_ROW", "include/frontend.h", "A_practice_grid_row"),
    ("A_PRACTICE_GRID_COL", "include/frontend.h", "A_practice_grid_col"),
    ("A_P2_TURN", "include/frontend.h", "A_p2_turn"),
    ("A_AMBIENT_SFX_COUNTDOWN", "include/frontend.h", "A_ambient_sfx_countdown"),
    ("A_CONST_DEMO_LENGTH_DIVISOR", "include/frontend.h", "A_const_demo_length_divisor"),
    ("A_CONST_DEMO_ROOM_DIVISOR", "include/frontend.h", "A_const_demo_room_divisor"),
    ("DEMO_RECORD_BYTES", "include/frontend.h", "DEMO_RECORD_BYTES"),
    ("TOP_BONUS_BAR_FULL", "include/frontend.h", "TOP_BONUS_BAR_FULL"),
    ("TOP_BONUS_BAR_FLOOR", "include/frontend.h", "TOP_BONUS_BAR_FLOOR"),
    ("MENU_LOCAL_BYTES", "include/frontend.h", "MENU_LOCAL_BYTES"),
    ("SUBMIT_LOCAL_BYTES", "include/frontend.h", "SUBMIT_LOCAL_BYTES"),
    ("INSERT_LOCAL_BYTES", "include/frontend.h", "INSERT_LOCAL_BYTES"),
    ("CALL_FRAME_COST", "include/frontend.h", "CALL_FRAME_COST"),
    ("TOP_LOCAL_BYTES", "include/frontend.h", "TOP_LOCAL_BYTES"),
    ("A_P1_TURN", "include/gameplay.h", "A_p1_turn"),
    ("A_SHOW_PLAYER_CHANGE", "include/gameplay.h", "A_show_player_change"),
    ("A_P1_PLAYING", "include/gameplay.h", "A_p1_playing"),
    ("A_P2_PLAYING", "include/gameplay.h", "A_p2_playing"),
    ("A_P1_LIVES", "include/gameplay.h", "A_p1_lives"),
    ("A_P2_LIVES", "include/gameplay.h", "A_p2_lives"),
    ("A_P1_BONUS_BAR", "include/gameplay.h", "A_p1_bonus_bar"),
    ("A_P2_BONUS_BAR", "include/gameplay.h", "A_p2_bonus_bar"),
    ("A_P1_GRID_COL", "include/gameplay.h", "A_p1_grid_col"),
    ("A_P2_GRID_COL", "include/gameplay.h", "A_p2_grid_col"),
    ("A_P1_GRID_ROW", "include/gameplay.h", "A_p1_grid_row"),
    ("A_P2_GRID_ROW", "include/gameplay.h", "A_p2_grid_row"),
    ("A_P1_DEATHS_IN_ROOM", "include/gameplay.h", "A_p1_deaths_in_room"),
    ("A_P2_DEATHS_IN_ROOM", "include/gameplay.h", "A_p2_deaths_in_room"),
    ("A_P1_ENTRY_DIR", "include/gameplay.h", "A_p1_entry_dir"),
    ("A_P2_ENTRY_DIR", "include/gameplay.h", "A_p2_entry_dir"),
    ("A_GRID_ROW", "include/gameplay.h", "A_grid_row"),
    ("A_GRID_COL", "include/gameplay.h", "A_grid_col"),
    ("A_ENTRY_DIR", "include/gameplay.h", "A_entry_dir"),
    ("A_IN_ROOM", "include/gameplay.h", "A_in_room"),
    ("A_DEATHS_IN_ROOM", "include/gameplay.h", "A_deaths_in_room"),
    ("A_BONUS_TICK", "include/gameplay.h", "A_bonus_tick"),
    ("A_BONUS_BAR", "include/gameplay.h", "A_bonus_bar"),
    ("A_LIVES", "include/gameplay.h", "A_lives"),
    ("A_HI_SCORE", "include/gameplay.h", "A_hi_score"),
    ("A_SOUND_ENABLED", "include/gameplay.h", "A_sound_enabled"),
    ("A_LOA_IMAGE", "include/voice.h", "A_loa_image"),
    ("A_NAME_GHOST_LOA", "include/voice.h", "A_name_ghost_loa"),
    ("A_NAME_GHOST_VOI", "include/voice.h", "A_name_ghost_voi"),
    ("A_SND_VOICE", "include/sound.h", "A_snd_voice"),
    ("SND_VOICE_BYTES", "include/sound.h", "SND_VOICE_BYTES"),
    ("SND_VC_PRIORITY", "include/sound.h", "SND_VC_PRIORITY"),
    ("SND_VOICES", "include/sound.h", "SND_VOICES"),
    ("TOS_VEC_TRAP9", "include/sound.h", "TOS_VEC_TRAP9"),
    ("SND_TRAP9_HANDLER_ENTRY", "include/sound.h", "SND_TRAP9_HANDLER_ENTRY"),
    ("ROOM_BYTES", "include/blit.h", "ROOM_BYTES"),
    ("ROOM_TILE_ROWS", "include/blit.h", "ROOM_TILE_ROWS"),
    ("ROOM_TILE_COLS", "include/blit.h", "ROOM_TILE_COLS"),
    ("A_ROOM_NUMBER", "include/gameplay.h", "A_room_number"),
    ("A_SCORE", "include/gameplay.h", "A_score"),
    ("A_MAX_ROOM_REACHED", "include/gameplay.h", "A_max_room_reached"),
    ("A_GHOST_X", "include/gameplay.h", "A_ghost_x"),
    ("A_GHOST_Y", "include/gameplay.h", "A_ghost_y"),
    ("A_GHOST_TILE", "include/gameplay.h", "A_ghost_tile"),
    ("A_BUBBLE_X", "include/gameplay.h", "A_bubble_x"),
    ("A_BUBBLE_Y", "include/gameplay.h", "A_bubble_y"),
    ("A_BUBBLE_FRAME", "include/gameplay.h", "A_bubble_frame"),
)

# SIXTEEN BYTES, not the usual eight or ten. The twelve VDI entry points are near-identical —
# every one opens `link a6,#$0` and most write `contrl[0]` next — and two PAIRS agree for the first
# twelve bytes and separate only at the opcode or the `contrl` slot they name
# (`vdi_set_src_mfdb`/`vdi_set_dst_mfdb`, `vst_color`/`vsf_color`). A shorter prologue would let one
# of each pair stand for the other, and a mistyped entry would run the wrong call and come back
# clean. Every prologue below is checked to be distinct from every other.
ENTRY_PROLOGUES = {
    "ENTRY_VDI_CALL": "29499a20294a9a1c486ce7d6295f99b0",
    "ENTRY_VDI_SET_SRC_MFDB": "4e560000202e0008e080e0803940e7e4",
    "ENTRY_VDI_SET_DST_MFDB": "4e560000202e0008e080e0803940e7e8",
    "ENTRY_VST_HEIGHT": "4e560000426ce5d6396e000ae5d8397c",
    "ENTRY_VST_COLOR": "4e560000396e000ae6d6397c0016e7d6",
    "ENTRY_VSF_COLOR": "4e560000396e000ae6d6397c0019e7d6",
    "ENTRY_V_OPNVWK": "4e560000296e000899b4296e001099bc",
    "ENTRY_V_CLRWK": "4e560000397c0003e7d6426ce7d8426c",
    "ENTRY_VQ_MOUSE": "4e560000397c007ce7d6426ce7d8426c",
    "ENTRY_VQ_KEY_S": "4e560000397c0080e7d6426ce7d8426c",
    "ENTRY_V_GTEXT": "4e56fffe396e000ae5d6396e000ce5d8",
    "ENTRY_VR_RECFL": "4e560000296e000a99b8397c0072e7d6",
    "ENTRY_VRO_CPYFM": "4e560000396e000ae6d62f2e00104eba",
    "ENTRY_GEM_AES": "29499a20294a9a1c222f0004303c00c8",
    "ENTRY_AES_CRYSIF": "4e56fffa396e0008a226302e0008907c",
    "ENTRY_APPL_INIT": "4e56fffe41eca2262948a1a841eca206",
    "ENTRY_GRAF_HANDLE": "4e5600003f3c004d4ebaff3c548f206e",
    "ENTRY_GRAF_MOUSE": "4e560000396e0008a1e4296e000aa1c8",
    "ENTRY_INIT_GEM_AND_SCREENS": "4e56fffa4eba4a763d40fffc426efffa",
    "ENTRY_BUILD_SPRITE_BANK": "4e56fff4426ce2044eba03a4397c0020",
    "ENTRY_SAVE_SPRITE_BACKGROUNDS": "4e56000042ace1e6202ce1ce2940e1d2",
    "ENTRY_DRAW_SPRITES": "4e560000302ce0d0e58041ece10ed0c0",
    "ENTRY_RESTORE_SPRITE_BACKGROUNDS": "4e560000202ce1ce2940e1e642ace1d2",
    "ENTRY_SHOW_PRESENTATION": "4e56000048e70030397c0006e2044eba",
    "ENTRY_LOAD_DEMO": "4e56fffe3f3c2000486c00c64eba4f6c",
    "ENTRY_LOAD_PRESENTATION": "4e56fffe3f3c2000486c00d24eba4f12",
    "ENTRY_LOAD_LEVEL_PICTURES": "4e56fffc3f3c2000486c02984eba23ea",
    "ENTRY_LOAD_HISCORES": "4e56ffea4267486c025c4eba3bb85c8f",
    "ENTRY_DRAW_ROOM_TO_STAGE": "4e56ffe448e70030426efffc600000f6",
    "ENTRY_DRAW_HALL_OF_FAME": "4e56ffea3d7c0072fffa486ce09c486c",
    "ENTRY_HISCORE_INSERT_AND_SAVE": "4e56fff6426efffa202ce086b0ace072",
    "ENTRY_SAVE_HISCORES": "4e56fff4486ce09c486ce09e486ce0a0",
    "ENTRY_HISCORE_SUBMIT_PLAYERS": "4e5600000c6c0002e252662e296ce26c",
    "ENTRY_DRAW_ROOM_TO_STAGE_CELL": "486ce1fe486ce200486ce2023f2ce3d4",
    "ENTRY_TITLE_MENU_OPEN": "4e56fff04eba0792303c00003940e242",
    "ENTRY_MENU_DRAW": "303c00003940e2423d40fff64eba2f8a",
    "ENTRY_MENU_READ_KEY": "3f3c00084eba478e548f1d40ffff4267",
    "ENTRY_MENU_ASK_PLAYER_COUNT": "3d7c0001fff6426ce25242672f2ce22e",
    "ENTRY_MENU_READ_PLAYER_COUNT": "3f3c00084eba46de548f1d40fffe042e",
    "ENTRY_MENU_ASK_PRACTICE_LEVEL": "203c000000002940e2682940e26c2940",
    "ENTRY_MENU_READ_LEVEL_TENS": "3f3c00084eba4614548f3940e23e046c",
    "ENTRY_MENU_READ_LEVEL_UNITS": "3f3c00084eba45e6548f3940e240046c",
    "ENTRY_DEMO_RECORD": "206ce24a10104880c1fc00033940e0d8",
    "ENTRY_MENU_ATTRACT_SEQUENCE": "426ce202397c0001e2064eba1dd64eba",
    "ENTRY_MENU_ATTRACT_SLIDESHOW": "3f3c00114eba4350548f4eba39be486c",
    "ENTRY_MENU_ATTRACT_SLIDESHOW_ROOM": "3f3c00114eba4306548f4eba3974486c",
    "ENTRY_MENU_ATTRACT_TITLE": "0c6c0001e20267324ebaf27a3f3c0005",
    "ENTRY_MENU_HALL_OF_FAME": "4eba01004ebaf23e202ce2082f003f3c",
    "ENTRY_GAME_TOP_BOOT": "4e56fff642673f3c01004eba4a2c588f",
    "ENTRY_GAME_TOP_BOOT_TAIL": "4eba37344eba1f643f3c00083f3c0004",
    "ENTRY_GAME_TOP_BOOT_ARM": "4eba30924eba47244eba4314397c0002",
    "ENTRY_GAME_NEW_GAME": "303c00013940e27e3940e280426ce0a4",
    "ENTRY_GAME_TURN_INIT": "426ce05a397c0001e20642ace096397c",
    "ENTRY_GAME_PLAYER_CHANGE": "0c6c0002e2526600025e302ce2866700",
    "ENTRY_GAME_ROOM_SETUP": "397c0001e0a6302ce23c322ce23ac3fc",
    "ENTRY_GAME_ROOM_FRAME_TAIL": "302ce05c536ce05c0c4000016c22397c",
    "ENTRY_GAME_ENDING_SEQUENCE": "3f3c00014eba3c1e548f3f3c000a3f3c",
    "ENTRY_GAME_ROOM_EXIT": "302ce2426708297cffffffffe08e0cac",
    "ENTRY_GAME_END_OF_TURN": "0c6c0002e25266360cac00000000e274",
    "ENTRY_GAME_OVER_CARD": "0c6c0001e252660000920c6c0000e242",
}

# ...and the CHECKPOINTS, pinned the same way and for the same reason: a `stop_pc` one instruction
# early diffs a routine before its last store and comes back clean. `test_constants.py` requires a
# row here for every module-level `STOP_*` that is a program address.
STOP_PROLOGUES = {
    # the `clr.w -(a7)` + `pea` that open `c_creat`'s push, which is where the prologue slice ends
    "STOP_SAVE_HISCORES_PROLOGUE": "4267486c023c4eba2ba45c8f3d40fff6",
    # the `addq.w #1,-2(a6)` that closes the room composer's loop body
    "STOP_DRAW_ROOM_TO_STAGE_CELL": "526efffe0c6e000afffe6d00ff1a526e",
    "STOP_TITLE_MENU_OPEN": "3f3c00084eba478e548f1d40ffff4267",
    "STOP_MENU_DRAW": "3f3c00084eba478e548f1d40ffff4267",
    "STOP_MENU_READ_KEY": "b07c0047660000ca3d7c0001fff6426c",
    "STOP_MENU_ASK_PLAYER_COUNT": "3f3c00084eba46de548f1d40fffe042e",
    "STOP_MENU_PLAYER_COUNT_CHOSEN": "60000592102effff4880b07c00506600",
    "STOP_MENU_PLAYER_COUNT_AGAIN": "600a3f3c00074eba46f6548f3f3c000b",
    "STOP_MENU_ASK_PRACTICE_LEVEL": "3f3c00084eba4614548f3940e23e046c",
    "STOP_MENU_READ_LEVEL_TENS": "3f3c00084eba45e6548f3940e240046c",
    "STOP_MENU_READ_LEVEL_UNITS": "60000440102effff4880b07c00446600",
    "STOP_DEMO_RECORD": "0c6c0001e2026712202efffa53aefffa",
    "STOP_DEMO_REPLAY": "3f3c00114eba4350548f4eba39be486c",
    "STOP_MENU_ATTRACT_SEQUENCE": "3f3c00114eba4350548f4eba39be486c",
    "STOP_MENU_ATTRACT_SLIDESHOW": "0c6c0001e20267324ebaf27a3f3c0005",
    "STOP_MENU_ATTRACT_SLIDESHOW_ROOM": "0c6c0001e2026710302efff8536efff8",
    "STOP_MENU_ATTRACT_TITLE": "600000b6102effff4880b07c00486600",
    "STOP_MENU_HALL_OF_FAME": "0c6e0000fff66700f8764e5e4e754e56",
    "STOP_GAME_TOP_BOOT": "4eba3ab64eba37344eba1f643f3c0008",
    "STOP_GAME_TOP_BOOT_TAIL": "2f2ce8824eba59aa588f4eba30924eba",
    "STOP_GAME_TOP_BOOT_ARM": "303c00013940e27e3940e280426ce0a4",
    "STOP_GAME_NEW_GAME": "4eba1324426ce05a397c0001e20642ac",
    "STOP_GAME_TURN_INIT": "0c6c0002e2526600025e302ce2866700",
    "STOP_GAME_PLAYER_CHANGE": "397c0001e0a6302ce23c322ce23ac3fc",
    "STOP_GAME_ROOM_SETUP": "600001464eba1b92302ce05c536ce05c",
    "STOP_GAME_ROOM_FRAME_TAIL": "302ce236670c0cacffffffffe08e6e00",
    "STOP_GAME_ENDING_SEQUENCE": "0c6c0002e25266360cac00000000e274",
    "STOP_GAME_ROOM_EXIT": "0c6c0002e25266360cac00000000e274",
    "STOP_GAME_END_OF_TURN": "302ce2806600f640302ce27e6600f638",
    "STOP_GAME_OVER_CARD": "303c00013940e27e3940e280426ce0a4",
}


def test_every_entry_prologue_is_distinct():
    """...and that no two of them are the same bytes, which is what makes the pin above load-bearing.

    Two pairs really do agree for twelve bytes, so the length was chosen rather than inherited; a
    later entry added at a shorter length would silently vouch for its neighbour.
    """
    seen = {}
    for name, prologue in ENTRY_PROLOGUES.items():
        assert prologue not in seen, (
            f"{name} and {seen[prologue]} open with the same {len(prologue) // 2} bytes, so the "
            f"pin cannot tell them apart — lengthen every prologue in this file")
        seen[prologue] = name
