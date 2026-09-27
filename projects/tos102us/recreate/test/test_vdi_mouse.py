"""The HIDE COUNT, the FORM and the INTERRUPT PATHS (`src/vdi/mouse.c`).

    $fd0254 $a00a hide_mouse      $fd0286 show_cursor       $fcb120 v_show_c (122, $a009)
    $fcb148 v_hide_c (123)        $fd02ca vsc_form (111, $a00b)
    $fcfe28 mouse_isr             $fcff0a default_user_cur  $fcff2a vbl_draw_cursor
    $fca7f8 mouse_init            $fca872 mouse_off

THE CAPTURED MACHINE IS THE STAGE for the hide count: the arrow is drawn at (159, 99), M_HID_CT is 0 and the
save block holds what it covers, so hiding restores the desktop and showing draws the arrow again — real
data both ways. A case that shows it somewhere else stages GCURX/GCURY.

THE ISR is entered as the IKBD handler calls it — A0 the packet — with D0/D1 holding junk whose HIGH WORDS the
ISR hands the user vectors untouched. USER_BUT and USER_MOT point into the AES in the capture, so every ISR
case repoints them at stubs (`vdi_mouse.user_routine`) that RECORD the registers they were handed and answer
registers of their own; USER_CUR stays the ROM's own `default_user_cur` where the case is about what it does.

MOUSE_FLAG is a LOCK held round every routine that touches the sprite: its increment and decrement leave no
trace a differential can see (the oracle takes no interrupt), so only the target build's cycles hold them.
The ISR's and the VBL's `tst.b MOUSE_FLAG` ARE pinned — a held lock skips each whole.

mouse_init and mouse_off take XBIOS Initmous through the ROM's own `trap #14` on the oracle, and the core
directly on the host: `savptr` is staged in the dropped band (`gemdos.machine`'s arrangement), and those
cases do not poison — the attribution pass would invert `savptr` itself.
"""
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import gemdos
import isr
import vdi
import vdi_mouse as mouse
import vdi_raster
from case import merge_pokes
from opcodes import RTS

HIDE = "LINEA_ROM_HIDE_MOUSE"
SHOW = "VDI_ROM_SHOW_CURSOR"
ISR = "VDI_ROM_MOUSE_ISR"
USER_CUR_DEFAULT = "VDI_ROM_DEFAULT_USER_CUR"
VBL = "VDI_ROM_VBL_DRAW_CURSOR"

ARROW_AT = (vdi.linea(BASE_IMAGE, "GCURX"), vdi.linea(BASE_IMAGE, "GCURY"))
VALID = 1 << mouse.MOUSE_H["SPRITE_SAVE_VALID_BIT"]


def test_the_captured_machine_shows_the_arrow_where_the_cases_assume():
    assert ARROW_AT == (159, 99)
    assert vdi.linea(BASE_IMAGE, "M_HID_CT") == 0 and vdi.linea(BASE_IMAGE, "MOUSE_FLAG") == 0
    assert vdi.linea(BASE_IMAGE, "SAVE_STAT") & VALID


def screen_of(image):
    screen = vdi.SCREEN
    return bytes(image[screen.base:screen.base + screen.bytes])


# ---- the hide count ------------------------------------------------------------------------------------

@pytest.mark.parametrize("depth", (0, 1, 2, 0x7FFF, 0xFFFF, 0x8000))
def test_hide_restores_the_screen_only_on_reaching_one(depth):
    result = vdi.run_primitive(HIDE, {}, merge_pokes(vdi.linea_pokes(M_HID_CT=depth, CUR_FLAG=0x5B)))
    assert result.linea("M_HID_CT") == (depth + 1) & 0xFFFF
    assert (result.linea("CUR_FLAG") == 0) == (depth == 0)


@pytest.mark.parametrize("depth", (0, 1, 2, 3, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0xFFFB))
def test_show_draws_only_on_reaching_zero(depth):
    """`subq.w` then `bgt` (a signed compare with 1) and `bmi` (the result's sign alone): a depth of 1
    draws, one below 0 is put back to 0 undrawn — and $8000, whose decrement overflows, DRAWS."""
    pokes = merge_pokes(vdi.linea_pokes(M_HID_CT=depth, GCURX=40, GCURY=30, CUR_FLAG=0x5B),
                        vdi_raster.CANVAS)
    result = vdi.run_primitive(SHOW, {}, pokes)
    drawn = depth in (1, 0x8000)
    assert (screen_of(result.final) != screen_of(vdi.make_image(pokes))) == drawn
    assert (result.linea("CUR_FLAG") == 0) == drawn


def test_hide_then_show_is_the_arrow_back_where_it_was():
    hidden = vdi.run_primitive(HIDE, {}, {})
    assert screen_of(hidden.final) != screen_of(BASE_IMAGE)
    shown = vdi.run_primitive(SHOW, {}, case.continued(hidden))
    assert screen_of(shown.final) == screen_of(BASE_IMAGE)


def test_nested_hides_need_as_many_shows():
    once = vdi.run_primitive(HIDE, {}, {})
    twice = vdi.run_primitive(HIDE, {}, case.continued(once))
    first_show = vdi.run_primitive(SHOW, {}, case.continued(twice))
    assert first_show.linea("M_HID_CT") == 1 and screen_of(first_show.final) == screen_of(twice.final)
    second_show = vdi.run_primitive(SHOW, {}, case.continued(first_show))
    assert screen_of(second_show.final) == screen_of(BASE_IMAGE)


def call(name, intin=(), onto=None):
    return merge_pokes(vdi.function_pokes(name, intin), onto)


@pytest.mark.parametrize("depth", (0, 1, 3, 0xFFFF))
@pytest.mark.parametrize("force", (0, 1, 0x100))
def test_v_show_c_forces_the_count_only_for_a_zero_intin(depth, force):
    """intin[0] = 0 sets the depth to 1 first — unless it is already 0, which is then shown to -1 and put
    back to 0 undrawn."""
    pokes = call("VDI_ROM_V_SHOW_C", (force,), merge_pokes(vdi.linea_pokes(M_HID_CT=depth), vdi_raster.CANVAS))
    result = vdi.run_function("VDI_ROM_V_SHOW_C", pokes)
    forced = 1 if force == 0 and depth != 0 else depth
    assert result.linea("M_HID_CT") == (forced - 1 if vdi.signed_word(forced) > 1 else 0)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0


@pytest.mark.parametrize("depth", (0, 1))
def test_v_hide_c_is_hide(depth):
    result = vdi.run_function("VDI_ROM_V_HIDE_C", call("VDI_ROM_V_HIDE_C", onto=vdi.linea_pokes(M_HID_CT=depth)))
    assert result.linea("M_HID_CT") == depth + 1


def test_a00a_through_the_exception():
    """$a009 and $a00b are the VDI functions v_show_c and vsc_form themselves, reached with the Line-A
    pointers a program set — the cases above, entered by the dispatcher's `jsr`."""
    vdi.run_through_exception(HIDE, 0xA, {}, {})


# ---- vsc_form ------------------------------------------------------------------------------------------
FORM_INTIN = (0x1234, 0xFFF7, 0x8001) + (3, 12) + mouse.RANDOM_ROWS[:16] + mouse.RANDOM_ROWS[16:]


@pytest.mark.parametrize("bg,fg", ((0, 1), (15, 2), (16, 3), (-1, 0x7FFF), (0x8000, -16), (-16, 0x4000), (1, -32752)))
def test_vsc_form_maps_both_colours_by_the_sign_of_the_difference(bg, fg):
    """`cmp.w DEV_TAB[13]` then `bmi`: an index at or past the count is colour 1; a NEGATIVE one survives
    while its difference with 16 does not overflow, and reads BELOW MAP_COL."""
    intin = (7, 9, 4, bg & 0xFFFF, fg & 0xFFFF) + mouse.RANDOM_ROWS
    result = vdi.run_function("VDI_ROM_VSC_FORM", call("VDI_ROM_VSC_FORM", intin))
    assert result.linea("M_POS_HX") == 7


def test_vsc_form_keeps_four_bits_of_the_hot_spot_and_the_planes_word_whole():
    result = vdi.run_function("VDI_ROM_VSC_FORM", call("VDI_ROM_VSC_FORM", FORM_INTIN))
    assert (result.linea("M_POS_HX"), result.linea("M_POS_HY"), result.linea("M_PLANES")) == (4, 7, 0x8001)
    assert result.linea("MASK_FORM")[:4] == [FORM_INTIN[5], FORM_INTIN[21], FORM_INTIN[6], FORM_INTIN[22]]


def test_vsc_form_reads_each_word_after_storing_the_one_before():
    """INTIN laid ten bytes below MASK_FORM, so the form it reads IS the form it writes: row 0's data lands on
    the word row 1's mask is read from next. Only the ROM's read-store-read order gives its answer."""
    pokes = merge_pokes(call("VDI_ROM_VSC_FORM"), vdi.linea_pokes(
        INTIN=vdi.LINEA_M_POS_HX, M_POS_HX=3, M_POS_HY=5, M_PLANES=1, M_CDB_BG=2, M_CDB_FG=6,
        MASK_FORM=mouse.RANDOM_ROWS))
    vdi.run_function("VDI_ROM_VSC_FORM", pokes)


# INTIN 34 bytes below MASK_FORM: row 4's DATA word is then read from where row 4's MASK word was just
# stored, which only the ROM's read-store-read-store order within a row gives its answer.
INTIN_OVER_ROW_FOUR = vdi.LINEA_MASK_FORM - 34


def test_vsc_form_stores_each_mask_word_before_reading_its_data_word():
    pokes = merge_pokes(call("VDI_ROM_VSC_FORM"), vdi.linea_pokes(
        INTIN=INTIN_OVER_ROW_FOUR, GDP_SCRATCH=mouse.RANDOM_ROWS[:23], M_POS_HX=3, M_POS_HY=5, M_PLANES=1,
        M_CDB_BG=2, M_CDB_FG=6, MASK_FORM=mouse.RANDOM_ROWS))
    vdi.run_function("VDI_ROM_VSC_FORM", pokes)


def test_vsc_form_then_show_draws_the_new_form():
    formed = vdi.run_function("VDI_ROM_VSC_FORM",
                              call("VDI_ROM_VSC_FORM", FORM_INTIN, merge_pokes(vdi_raster.CANVAS, vdi.linea_pokes(
                                  M_HID_CT=1, GCURX=200, GCURY=150))))
    vdi.run_primitive(SHOW, {}, case.continued(formed))


# ---- the ISR --------------------------------------------------------------------------------------------
ENTRY = {"d0": 0xD0D0_7777, "d1": 0xD1D1_6666}
BUT, MOT, CUR = 0, 1, 2
BUTTON_ANSWER = {"d0": 0x1111_2201, "d1": 0x4321_8765}
MOTION_ANSWER = {"d0": 0x2222_0400, "d1": 0x3333_FFF0}     # off screen both ways: clamped again after


def packet(header, dx=0, dy=0):
    return {mouse.PACKET_AT: bytes([header, dx & 0xFF, dy & 0xFF])}


def isr_routines(but=None, mot=None, cur=None, default_cursor=False):
    routines = dict([mouse.user_routine(BUT, but), mouse.user_routine(MOT, mot)])
    if default_cursor:
        routines[addrs.VDI_ROM_DEFAULT_USER_CUR] = mouse.rom_routine("vdi_default_user_cur")
    else:
        routines.update([mouse.user_routine(CUR)])
    return routines


def isr_pokes(routines, *, stat=0, x=100, y=100, flag=0, hidden=0, extra=None):
    at = {slot: mouse.STUBS_AT + slot * mouse.STUB_STRIDE for slot in (BUT, MOT, CUR)}
    cursor = addrs.VDI_ROM_DEFAULT_USER_CUR if addrs.VDI_ROM_DEFAULT_USER_CUR in routines else at[CUR]
    return merge_pokes(mouse.user_vector_pokes(BUT=at[BUT], MOT=at[MOT], CUR=cursor),
                       vdi.linea_pokes(CUR_MS_STAT=stat, GCURX=x, GCURY=y, MOUSE_FLAG=flag, M_HID_CT=hidden,
                                       MOUSE_BT=0x5A5A),
                       {mouse.MARKS_AT: bytes([vdi.FILL]) * mouse.STUB_SLOTS * mouse.MARK_BYTES}, extra)


def run_isr(header, dx=0, dy=0, *, routines=None, **state):
    routines = routines if routines is not None else isr_routines(BUTTON_ANSWER, MOTION_ANSWER)
    pokes = merge_pokes(isr_pokes(routines, **state), packet(header, dx, dy))
    return mouse.run_calling(ISR, {"a0": mouse.PACKET_AT, **ENTRY}, pokes, routines)


@pytest.mark.parametrize("header", (0x00, 0xF0, 0xF7, 0x78, 0xE8))
def test_a_packet_that_is_not_a_relative_mouse_packet_changes_nothing(header):
    run_isr(header, 5, 5, stat=0x03)
    assert not mouse.CALLS


def test_a_held_lock_skips_the_whole_isr():
    run_isr(0xFB, 5, 5, flag=1)
    assert not mouse.CALLS


@pytest.mark.parametrize("header,stat", ((0xFA, 0x00), (0xF9, 0x00), (0xFB, 0x01), (0xF8, 0x03), (0xFA, 0xE2)))
def test_a_button_change_calls_user_but_and_records_what_changed(header, stat):
    """The IKBD's right button is bit 0 and the VDI's left one: swapped on the way in. USER_BUT is handed
    the new buttons over the entry D0's high word and the old in D1; its D0 answer is the state."""
    result = run_isr(header, stat=stat)
    buttons = (header & 1) << 1 | (header >> 1) & 1
    assert mouse.handed(result, BUT) == (ENTRY["d0"] & 0xFFFF_0000 | buttons,
                                         ENTRY["d1"] & 0xFFFF_0000 | stat & 3)
    assert result.linea("MOUSE_BT") == BUTTON_ANSWER["d0"] & 0xFFFF


@pytest.mark.parametrize("header,stat", ((0xF8, 0x00), (0xFA, 0x01), (0xF9, 0x22)))
def test_unchanged_buttons_call_nothing_and_clear_the_moved_bit(header, stat):
    run_isr(header, stat=stat | 0x20)
    assert not mouse.CALLS


@pytest.mark.parametrize("dx,dy", ((3, -4), (-128, 127), (1, 0), (0, -1)))
@pytest.mark.parametrize("header,stat", ((0xF8, 0x00), (0xFA, 0x00)))
def test_motion_is_handed_to_user_mot_clamped_and_again_to_user_cur(dx, dy, header, stat):
    """USER_MOT is handed the moved position (clamped) and may move it anywhere — its answer is clamped
    AGAIN before GCURX/GCURY and USER_CUR see it. After a button change, D1's high word is whatever
    USER_BUT left there."""
    result = run_isr(header, dx, dy, stat=stat, x=5, y=196)
    assert result.linea("GCURX") == 319 and result.linea("GCURY") == 0
    assert mouse.handed(result, CUR) == (MOTION_ANSWER["d0"] & 0xFFFF_0000 | 319,
                                         MOTION_ANSWER["d1"] & 0xFFFF_0000)


@pytest.mark.parametrize("x,y,dx,dy", ((0, 0, -5, -5), (319, 199, 9, 9), (-3, 250, 1, 1)))
def test_the_moved_position_is_clamped_before_user_mot(x, y, dx, dy):
    routines = isr_routines(BUTTON_ANSWER)
    result = run_isr(0xF8, dx, dy, routines=routines, x=x & 0xFFFF, y=y & 0xFFFF)
    handed = mouse.handed(result, MOT)
    assert (handed[0] & 0xFFFF, handed[1] & 0xFFFF) == (min(max(x + dx, 0), 319), min(max(y + dy, 0), 199))


@pytest.mark.parametrize("hidden", (0, 1))
def test_the_default_user_cur_queues_the_position_while_shown(hidden):
    routines = isr_routines(BUTTON_ANSWER, default_cursor=True)
    result = run_isr(0xF9, 7, -2, routines=routines, stat=0x01, hidden=hidden, extra=vdi.linea_pokes(
        CUR_X=0x5A5A, CUR_Y=0x5A5A, CUR_FLAG=0x40))
    assert (result.linea("CUR_FLAG") == 0x41) == (hidden == 0)


def test_the_packet_is_read_where_the_rom_reads_it():
    """dx is read twice — for the motion test and again for the sum — so a USER_BUT that rewrites the
    packet is seen by the second read. Its stub stores a new dx over the packet."""
    at = mouse.STUBS_AT + BUT * mouse.STUB_STRIDE
    stub = b"\x13\xfc\x00\x10" + struct.pack(">I", mouse.PACKET_AT + 1) + b"\x4e\x75"   # move.b #$10,dx

    def effect(buf, _registers):
        buf[mouse.PACKET_AT + 1] = 0x10
    routines = {at: (stub, effect), **dict([mouse.user_routine(MOT), mouse.user_routine(CUR)])}
    result = run_isr(0xFA, 1, 1, routines=routines, x=50, y=50)
    assert result.linea("GCURX") == 50 + 0x10


# A second packet, in the same band: the one a user routine points A0 at.
MOVED_PACKET_AT = mouse.PACKET_AT + mouse.PACKET_BYTES // 2
MOVED_DX, MOVED_DY = 0x20, 0x30


def test_the_packet_is_read_through_the_a0_user_but_hands_back():
    """The ISR reads dx and dy as `n(a0)` AFTER calling USER_BUT, which may leave A0 anywhere ($fcfe7e): a
    routine that points it at another packet moves the cursor by THAT packet's bytes."""
    routines = isr_routines({"d0": BUTTON_ANSWER["d0"], "a0": MOVED_PACKET_AT})
    result = run_isr(0xFA, 1, 1, routines=routines, x=50, y=50,
                     extra={MOVED_PACKET_AT: bytes([0xF8, MOVED_DX, MOVED_DY])})
    assert (result.linea("GCURX"), result.linea("GCURY")) == (50 + MOVED_DX, 50 + MOVED_DY)


def test_the_moved_test_reads_the_packet_user_but_hands_back():
    """...and so does the "did it move?" test (`move.b 1(a0),d0 / or.b 2(a0),d0`): a still packet handed back
    for a moving one clears the moved bit and calls no motion routine."""
    routines = isr_routines({"d0": BUTTON_ANSWER["d0"], "a0": MOVED_PACKET_AT})
    result = run_isr(0xFA, 1, 1, routines=routines, x=50, y=50, stat=0x20,
                     extra={MOVED_PACKET_AT: bytes([0xF8, 0, 0])})
    assert result.linea("CUR_MS_STAT") & 0x20 == 0


def test_user_cur_is_handed_the_a0_user_mot_left():
    """...and hands the A0 each routine leaves to the next: USER_CUR is entered with USER_MOT's. Its stub
    records A0 where `mouse.handed` records D0 for the others."""
    at, mark = mouse.STUBS_AT + CUR * mouse.STUB_STRIDE, mouse.mark_at(CUR)
    stub = isr.store_register(isr.MOVE_L_A0_ABSOLUTE, mark) + RTS

    def effect(buf, registers):
        isr.poke(buf, mark, struct.pack(">I", registers[isr.STAGED_REGISTERS.index("a0")]))
    routines = {**dict([mouse.user_routine(BUT), mouse.user_routine(MOT, {"a0": MOVED_PACKET_AT})]),
                at: (stub, effect)}
    result = run_isr(0xF8, 1, 1, routines=routines)
    assert result.long(mark) == MOVED_PACKET_AT


# ---- default_user_cur and the VBL -------------------------------------------------------------------------

@pytest.mark.parametrize("hidden", (0, 1, 0xFFFF))
def test_default_user_cur_queues_only_while_shown(hidden):
    pokes = vdi.linea_pokes(M_HID_CT=hidden, CUR_X=0x5A5A, CUR_Y=0x5A5A, CUR_FLAG=0x80)
    result = vdi.run_primitive(USER_CUR_DEFAULT, {"d0": 0x1234_0102, "d1": 0x5678_0304}, pokes)
    assert (result.linea("CUR_X"), result.linea("CUR_Y"), result.linea("CUR_FLAG")) == (
        (0x0102, 0x0304, 0x81) if hidden == 0 else (0x5A5A, 0x5A5A, 0x80))


@pytest.mark.parametrize("flag", (0x00, 0xFE))
def test_the_vbl_takes_the_bit_and_draws_nothing_without_one(flag):
    result = vdi.run_primitive(VBL, {}, vdi.linea_pokes(CUR_FLAG=flag))
    assert result.linea("CUR_FLAG") == flag & 0xFE and screen_of(result.final) == screen_of(BASE_IMAGE)


def test_a_held_lock_skips_the_vbl():
    result = vdi.run_primitive(VBL, {}, vdi.linea_pokes(CUR_FLAG=1, MOUSE_FLAG=1))
    assert result.linea("CUR_FLAG") == 1


@pytest.mark.parametrize("where", ((159, 99), (40, 20), (0, 0), (318, 197), (0xFFFF, 150)))
def test_the_vbl_moves_the_arrow_to_the_queued_place(where):
    """The arrow restored off (159, 99) with the capture's own save block, and drawn at CUR_X/CUR_Y."""
    x, y = where
    vdi.run_primitive(VBL, {}, vdi.linea_pokes(CUR_FLAG=0x81, CUR_X=x, CUR_Y=y))


def test_isr_then_vbl_moves_the_arrow():
    routines = isr_routines(BUTTON_ANSWER, default_cursor=True)
    moved = run_isr(0xF8, 20, -10, routines=routines, x=ARROW_AT[0], y=ARROW_AT[1])
    vdi.run_primitive(VBL, {}, case.continued(moved))


# ---- mouse_init / mouse_off ---------------------------------------------------------------------------

def trap_pokes(pokes=None):
    return merge_pokes(gemdos.machine(), pokes)


def test_mouse_init_installs_the_defaults_and_the_isr():
    pokes = trap_pokes(merge_pokes(call("VDI_ROM_VSC_FORM", FORM_INTIN), vdi.linea_pokes(
        MOUSE_BT=0x5A5A, CUR_MS_STAT=0x5A, MOUSE_FLAG=0x5A, CUR_X=0x5A5A, CUR_Y=0x5A5A, CUR_FLAG=0x5A),
        {mouse.VBL_QUEUE: bytes([vdi.FILL]) * 4}))
    result = vdi.run_primitive("VDI_ROM_MOUSE_INIT", {}, pokes, poison=False)
    assert result.linea("INTIN") == vdi.INTIN_AT
    assert result.long(addrs.KBDVECS + addrs.KBDVECS_MOUSEVEC) == addrs.VDI_ROM_MOUSE_ISR
    assert result.long(mouse.VBL_QUEUE) == addrs.VDI_ROM_VBL_DRAW_CURSOR


def test_mouse_off_empties_the_vbl_slot_and_disables_the_mouse():
    result = vdi.run_primitive("VDI_ROM_MOUSE_OFF", {}, trap_pokes(), poison=False)
    assert result.long(mouse.VBL_QUEUE) == 0


# ---- the rows Tier 3 prices -------------------------------------------------------------------------------
vdi.register("linea_hide_mouse, the arrow removed", addrs.LINEA_ROM_HIDE_MOUSE, {})
vdi.register("linea_hide_mouse, already hidden", addrs.LINEA_ROM_HIDE_MOUSE, vdi.linea_pokes(M_HID_CT=1))
vdi.register("vdi_show_cursor, drawn", addrs.VDI_ROM_SHOW_CURSOR,
             merge_pokes(vdi.linea_pokes(M_HID_CT=1, GCURX=40, GCURY=30), vdi_raster.CANVAS))
vdi.register("vdi_show_cursor, still hidden", addrs.VDI_ROM_SHOW_CURSOR, vdi.linea_pokes(M_HID_CT=2))
vdi.register("vdi_v_show_c, forced", addrs.VDI_ROM_V_SHOW_C,
             call("VDI_ROM_V_SHOW_C", (0,), merge_pokes(vdi.linea_pokes(M_HID_CT=3, GCURX=40, GCURY=30),
                                                         vdi_raster.CANVAS)))
vdi.register("vdi_v_hide_c, the arrow removed", addrs.VDI_ROM_V_HIDE_C, call("VDI_ROM_V_HIDE_C"))
vdi.register("vdi_vsc_form, a form", addrs.VDI_ROM_VSC_FORM, call("VDI_ROM_VSC_FORM", FORM_INTIN))
vdi.register("vdi_default_user_cur, queued", addrs.VDI_ROM_DEFAULT_USER_CUR, {}, regs={"d0": 10, "d1": 20})
vdi.register("vdi_vbl_draw_cursor, the arrow moved", addrs.VDI_ROM_VBL_DRAW_CURSOR,
             vdi.linea_pokes(CUR_FLAG=1, CUR_X=40, CUR_Y=20))
vdi.register("vdi_vbl_draw_cursor, nothing queued", addrs.VDI_ROM_VBL_DRAW_CURSOR, vdi.linea_pokes(CUR_FLAG=0))
vdi.register("vdi_mouse_off, the mouse off", addrs.VDI_ROM_MOUSE_OFF, trap_pokes())
vdi.register("vdi_mouse_init, the defaults", addrs.VDI_ROM_MOUSE_INIT, trap_pokes(call("VDI_ROM_VSC_FORM")))


def isr_row(label, header, dx, dy, routines, **state):
    pokes = merge_pokes(isr_pokes(routines, **state), packet(header, dx, dy), mouse.staged(routines))
    vdi.register(f"vdi_mouse_isr, {label}", addrs.VDI_ROM_MOUSE_ISR, pokes, regs={"a0": mouse.PACKET_AT, **ENTRY})


isr_row("a button and motion", 0xFA, 3, -2, isr_routines(BUTTON_ANSWER, default_cursor=True))
isr_row("motion only", 0xF8, -1, 1, isr_routines(default_cursor=True))
isr_row("not a mouse packet", 0xF0, 0, 0, isr_routines())
