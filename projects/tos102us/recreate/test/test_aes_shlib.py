"""gemshlib's SCREEN SWITCHES and the shell's BAND (`src/aes/shlib.c`): sh_tographic `$fead5a`, sh_toalpha `$fead82`,
sh_draw `$feada0` and sh_show `$feaddc`.

    sh_toalpha():    gsx_mfset(ad_armice); cli(); giveerr(); sti(); gsx_moff(); gsx_mfree(); gsx_graphic(FALSE); 1
    sh_tographic():  cli(); retake(); sti(); gsx_graphic(TRUE); gsx_sclip(&gl_rscreen); gsx_malloc();
                     gsx_mfset(ad_hgmice); ratinit(); 1
    sh_draw(cmd, object, depth):  if (gl_shgem && !sh_dodef) { tree = ad_stdesk; gsx_sclip(&gl_rscreen);
                                  *ad_pfile = cmd; ob_draw(tree, object, depth); }
    sh_show(cmd):    for (i = 1; i < 3; i++) sh_draw(cmd, i, 0)

EVERY CALL OUT is taken as its own battery takes it, all at once: the VDI by its C cores under the AES's `trap #2`
(`aes_gsx.vdi_hook`, the screen compared), GEMDOS by the recording, scripted trap (`aes_gemdosif`: gsx_malloc's
Malloc, gsx_mfree's Mfree — the ledger compared), the BIOS's Setexc by the machine's own trap on the ROM's shore and
the BIOS's C core on ours (the trap's save in the stack band), ob_draw's just_draw by its C core.
WHAT DIFFERS BY NATURE: spl7_save's SR save word (`aes_event.sr_drops`: dropped where the ROM's run stores it).

WHAT REACHES EACH TODAY — sh_main's launch loop (`$feb136..$feb2f0`), which no run reaches yet (the snapshot's desk
is up and running):
  * THE SCREEN SWITCHES are run as sh_main runs them round a program that is not GEM's (`$feb178`, then `$feb174`
    when the next is): sh_toalpha over the post-boot machine — graphics on, GEM's vectors up, the cursor as the
    AES's own gsx_moff leaves it, and as the snapshot shows it — and sh_tographic OVER THE MACHINE THE ROM'S OWN
    sh_toalpha LEFT. gem_main's own first sh_tographic (`$fda2c0`) is OWED on the pre-init machine.
  * sh_draw's DRAWING ARM needs a launch in flight: `LAUNCHING` is the post-boot machine after THE ROM'S OWN
    shel_write(doexec, isgem, ...) — the desk's own way of asking for one: the command in the shell's buffer,
    sh_dodef cleared. The arguments are sh_main's (`$feb19c..$feb1a8`: the shell's buffer, the root, depth 1) and
    sh_show's. AN ARGUMENT CLASS all the same, labelled: the desk has not returned, so the band is drawn over the
    desk's screen. OWED: sh_main's own calls.
"""
import functools

import pytest

from harness import BASE_IMAGE, _lib, addrs, bench_tier3, emu, make_image

import aes
import aes_event
import aes_gemdosif as gd
import aes_gsx as gsx
import aes_objdraw as od
import aes_shell as shell
import aes_trap_order as order
import case
import isr
import routines
import test_aes_gemgraf as gemgraf
import test_aes_gsxif as gsxif
import test_aes_ob_draw as ob_draw
import test_aes_shell_buf as shell_buf
import test_aes_vectors as vectors
import vdi
from case import merge_pokes
from test_aes_gsx import screen_changed

SH_TOGRAPHIC, SH_TOALPHA, SH_DRAW, SH_SHOW = "AES_ROM_SH_TOGRAPHIC", "AES_ROM_SH_TOALPHA", "AES_ROM_SH_DRAW", "AES_ROM_SH_SHOW"
aes.declare_alcyon(SH_TOGRAPHIC, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
aes.declare_alcyon(SH_TOALPHA, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
aes.declare_alcyon(SH_DRAW, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.WORD_ARG))
aes.declare_alcyon(SH_SHOW, None, (vdi.IMAGE_ARG, vdi.LONG_ARG))
SHLIB = aes.header_constants("shlib.h")
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
GL_SHGEM = aes.AES_GL_SHGEM
aes.declare_case_field(GL_SHGEM, aes.WORD_BYTES, "gl_shgem: the program being launched is GEM's")
ARGUMENT_CLASS = "ARGUMENT CLASS"
MALLOC, MFREE = gd.MALLOC, gd.MFREE
GRAPHIC, ALPHA = aes.GSX_GRAPHIC, aes.GSX_ALPHA

# ---- THE SCREEN SWITCHES ---------------------------------------------------------------------------------------------------
SWITCH_DOORS = aes.doors(gsx.vdi_hook, gd.scripted_hook)
# spl7_save's word (each build's own condition codes) where the ROM's run stores it, beside the Line-F mask word.
SWITCH_DROPS = aes.LINE_F_MASK_WINDOW + aes_event.sr_drops(aes.AES_SR_SPL)
SWITCH_INSNS = 400_000                  # past the oracle's default: the screen cleared, the cursor drawn
GEMDOS_OK = 0
SAVE_BUFFER = gsxif.SNAPSHOT_BUFFER_AT  # the block the boot's own gsx_malloc got: what the scripted Malloc answers


def switch_machine(answer, base=gsx.machine, onto=None):
    """`base` (the door's machine, the cursor hidden — or `gsx.shown_machine`) with the BIOS trap's save in the stack
    band, GEMDOS scripted to answer `answer`, the glue's words stale, `onto` over it."""
    return merge_pokes(base(), gd.STALE_DOS, aes_event.savptr_in_the_band(), gd.scripted_pokes([answer]), onto)


def switch(name, machine, **kwargs):
    """A screen switch against the ROM's, every door bound — UNPOISONED (the BIOS trap's `savptr`, the scripted
    trap's pointers: `test_aes_vectors`, `aes_gemdosif`)."""
    return aes.run_function(name, (), machine, hook=SWITCH_DOORS, poison=False, dropped_windows=SWITCH_DROPS,
                            max_insns=SWITCH_INSNS, **kwargs)


@functools.cache
def in_alpha(base=gsx.machine):
    """THE MACHINE THE ROM'S OWN sh_toalpha LEAVES over `base`: text mode, the critical-error handler the BIOS's
    again, the mouse off, the save buffer given back (the scripted Mfree) — as pokes, the ledger and script fresh."""
    staged = aes.staged(SH_TOALPHA, (), switch_machine(GEMDOS_OK, base))
    final, writes, regs = emu.run(make_image(staged), addrs.AES_ROM_SH_TOALPHA, {}, max_insns=SWITCH_INSNS)
    assert not regs.get("writes_truncated")
    return merge_pokes(case.continued_from(staged, final, writes), aes_event.savptr_in_the_band(),
                       gd.scripted_pokes([SAVE_BUFFER]))


BASES = {"the cursor hidden": gsx.machine, "the cursor shown (the snapshot's)": gsx.shown_machine}


@THROUGH
@pytest.mark.parametrize("base", BASES)
def test_sh_toalpha_hands_the_screen_to_a_text_program(base, through_line_f):
    """The arrow set, giveerr under the mask (etv_critic the BIOS's again; vector $88 stays GEM's), the mouse off,
    ONE Mfree — the save buffer's — and the workstation in text mode (the screen cleared: compared whole)."""
    result = switch(SH_TOALPHA, switch_machine(GEMDOS_OK, BASES[base]), through_line_f=through_line_f)
    assert result.answer() == SHLIB["SH_SWITCHED"]
    assert gd.calls(result.final) == [gd.call(MFREE, ("l", SAVE_BUFFER))]
    assert vectors.four(result.final) == (vectors.GEM_S_TRAP2, vectors.BIOS_VDI_DOOR, vectors.BIOS_CRITIC, vectors.BIOS_CRITIC)
    assert result.field("AES", "GL_GRAPHIC") == ALPHA and screen_changed(result)
    assert result.long(aes.AES_DOS_RETURN) == aes.AES_GSX_MFREE_RETURN


@THROUGH
@pytest.mark.parametrize("base", BASES)
def test_sh_tographic_takes_the_screen_back_from_the_machine_sh_toalpha_left(base, through_line_f):
    """retake under the mask (both vectors GEM's; nothing saved), graphics again, the clip the whole screen, ONE
    Malloc — the save buffer's — the busy mouse set and the mouse counted on."""
    result = switch(SH_TOGRAPHIC, in_alpha(BASES[base]), through_line_f=through_line_f)
    assert result.answer() == SHLIB["SH_SWITCHED"]
    assert gd.calls(result.final) == [gd.call(MALLOC, ("l", aes.GSX_SAVE_BUFFER_BYTES))]
    assert vectors.four(result.final) == (vectors.GEM_S_TRAP2, vectors.BIOS_VDI_DOOR, vectors.CRIT_ERR, vectors.BIOS_CRITIC)
    assert result.field("AES", "GL_GRAPHIC") == GRAPHIC
    assert gemgraf.clip_of(result) == tuple(case.word_in(BASE_IMAGE, aes.AES_GL_RSCREEN + 2 * word) for word in range(4))


def test_sh_tographic_over_a_refused_malloc_goes_on():
    """A ROM BEHAVIOUR, KEPT: gsx_malloc's block is not checked — refused, the save buffer is NULL (AES_DOS_ERR set)
    and the switch completes all the same."""
    result = switch(SH_TOGRAPHIC, merge_pokes(in_alpha(), gd.scripted_pokes([0])))
    assert result.answer() == 1 and result.field("AES", "DOS_ERR") == 1


def test_the_switches_mask_the_interrupts_round_the_vector_take():
    """THE BRACKET, on the ROM's own runs: each stores spl7_save's word (the SR as it was) — its presence on OUR
    target build is Tier 3's symmetric rule (`tier3.vet_what_our_run_stored`: a row that drops the word must store
    it), which the registered rows below fall under."""
    for name, machine in ((SH_TOALPHA, switch_machine(GEMDOS_OK)), (SH_TOGRAPHIC, in_alpha())):
        _final, writes, _regs = emu.run(make_image(aes.staged(name, (), machine)), getattr(addrs, name), {},
                                        max_insns=SWITCH_INSNS)
        assert aes.AES_SR_SPL in writes, name


# ---- THE ORDER OF A SWITCH'S CALLS OUT, across the doors (`aes_trap_order`) ---------------------------------------------------
# No image at a switch's end holds it: the calls commute in memory. Each registered row's two runs — the ROM's, and
# our build's on each blob — are watched at the four trap handlers: ONE ledger of the VDI's, GEMDOS's and the BIOS's
# calls in the order the machine took them, with what the vectors and the mouse's count held at each.
TO_ALPHA_ROW, TO_GRAPHIC_ROW = "to a text program, the cursor hidden", "back from the machine the ROM's sh_toalpha left"
VDI, DOS, BIOS_TRAP = order.GEM, order.GEMDOS, order.BIOS
VSC_FORM, ESCAPE, VEX_BUTV, VEX_MOTV, VS_CLIP, V_SHOW_C = (
    addrs.VDI_ROM_VSC_FORM_OPCODE, addrs.VDI_ROM_ESCAPE_OPCODE, addrs.VDI_ROM_VEX_BUTV_OPCODE, addrs.VDI_ROM_VEX_MOTV_OPCODE,
    addrs.VDI_ROM_VS_CLIP_OPCODE, addrs.VDI_ROM_V_SHOW_C_OPCODE)
SETEXC = addrs.BIOS_SETEXC_FN
# What gsx_graphic makes of the VDI either way: the escape (enter / exit alpha), then the two glue vectors.
GSX_GRAPHIC_S = [(VDI, ESCAPE), (VDI, VEX_BUTV), (VDI, VEX_MOTV)]
CALLS_IN_ORDER = {
    # the arrow; giveerr; (the mouse off: counted, no VDI call — it is hidden already); the buffer freed; then text
    (SH_TOALPHA, TO_ALPHA_ROW): [(VDI, VSC_FORM), (BIOS_TRAP, SETEXC), (DOS, MFREE), *GSX_GRAPHIC_S],
    # retake; graphics; the clip; the buffer; the busy mouse; ratinit's show
    (SH_TOGRAPHIC, TO_GRAPHIC_ROW): [(BIOS_TRAP, SETEXC), *GSX_GRAPHIC_S, (VDI, VS_CLIP), (DOS, MALLOC), (VDI, VSC_FORM),
                                     (VDI, V_SHOW_C)],
}


@functools.cache
def _watched_on(path, name, label):
    tier3 = bench_tier3()
    return order.on_both_shores(tier3, tier3.RomBench(path), tier3.row_named((routines.core_symbol(name), label)))


@pytest.mark.parametrize("name,label", CALLS_IN_ORDER, ids=lambda value: value)
@pytest.mark.parametrize("path", isr.BLOBS.values(), ids=isr.BLOBS)
def test_a_switch_takes_its_traps_in_the_rom_s_order(path, name, label):
    """ONE LEDGER ACROSS THE DOORS, both shores: our build takes the ROM's traps, in the ROM's order, each with the
    vectors and the mouse's count as the ROM's call found them — and the ROM's own are what the source's order says."""
    the_rom_s, ours = _watched_on(path, name, label)
    assert the_rom_s.names() == CALLS_IN_ORDER[(name, label)]
    assert ours.made == the_rom_s.made, (ours.names(), the_rom_s.names())


def test_sh_toalpha_hides_the_mouse_after_giveerr_and_before_it_frees_the_buffer():
    """...and what the witnesses say of the calls that are no trap: at giveerr's Setexc the critical-error handler is
    still GEM's and the mouse's count the one the arrow's call found; at the Mfree the handler is the BIOS's again
    and the count one more — hidden BEFORE the buffer under it is freed."""
    the_rom_s, _ours = _watched_on(isr.BLOBS["the bench blob"], SH_TOALPHA, TO_ALPHA_ROW)
    setexc, mfree = the_rom_s.names().index((BIOS_TRAP, SETEXC)), the_rom_s.names().index((DOS, MFREE))
    assert the_rom_s.held(setexc, order.ETV_CRITIC) == vectors.CRIT_ERR and the_rom_s.held(mfree, order.ETV_CRITIC) == vectors.BIOS_CRITIC
    assert aes.high_word(the_rom_s.held(mfree, aes.AES_GL_MOFF)) == aes.high_word(the_rom_s.held(setexc, aes.AES_GL_MOFF)) + 1


# ---- sh_draw and sh_show -----------------------------------------------------------------------------------------------------
BAND = od.trees()["desktop band"]
SHELL_BUFFER = od.SHELL_BUFFER
TAIL_AT = shell_buf.SECOND              # a command tail the launch's shel_write is handed
PTEXT_AT = case.long_in(BASE_IMAGE, aes.AES_AD_PFILE)
DRAW_DOORS = ob_draw.doors()
SH_MAIN_S = (aes.OB_ROOT, 1)            # sh_main's call: the band's root, one level down ($feb19c..$feb1a8)
WHOLE_SCREEN = tuple(case.word_in(BASE_IMAGE, aes.AES_GL_RSCREEN + 2 * word) for word in range(4))


@functools.cache
def launching(command=od.TWO_COMMANDS[0], gem=1):
    """`LAUNCHING`: the post-boot machine (the snapshot's font, the desktop's clip, the cursor hidden) after THE ROM'S
    OWN shel_write(1, gem, 0, command, tail) — `command` in the shell's buffer, sh_dodef and sh_isdef cleared."""
    pokes = merge_pokes(ob_draw.machine(), ob_draw.STALE_SLOTS, od.string_pokes(command, at=shell_buf.BUFFER, room=0x80),
                        od.string_pokes(b"", at=TAIL_AT, room=0x80))
    staged, final, writes = od.rom_run(shell_buf.SH_WRITE, (1, gem, 0, shell_buf.BUFFER, TAIL_AT), pokes)
    return merge_pokes(case.continued_from(staged, final, writes), gsx.CONTRL_STALE)


def draw(name, arguments, machine, **kwargs):
    return aes.run_function(name, arguments, machine, hook=DRAW_DOORS, max_insns=ob_draw.OB_DRAW_INSNS,
                            **{**od.PTSIN_READ_FIRST, **kwargs})


def test_launching_is_what_the_rom_s_own_shel_write_leaves():
    image = make_image(launching())
    assert (case.word_in(image, aes.AES_SH_DODEF), case.word_in(image, GL_SHGEM), case.word_in(image, aes.AES_SH_DOEXEC)) == (0, 1, 1)
    assert bytes(image[SHELL_BUFFER:SHELL_BUFFER + len(od.TWO_COMMANDS[0])]) == od.TWO_COMMANDS[0]
    assert case.word_in(BASE_IMAGE, aes.AES_SH_DODEF) == 1, "the capture: the desk is the one running"


@THROUGH
def test_sh_draw_while_the_desk_runs_draws_nothing(through_line_f):
    """THE CAPTURE'S OWN STATE (sh_dodef set): no clip, no store through ad_pfile, no draw."""
    result = draw(SH_DRAW, (SHELL_BUFFER, *SH_MAIN_S), merge_pokes(ob_draw.machine(), ob_draw.STALE_SLOTS),
                  through_line_f=through_line_f)
    assert aes.stored_nothing(result)


def test_sh_draw_for_a_program_that_is_not_gem_s_draws_nothing():
    """ARGUMENT CLASS (gl_shgem staged 0: sh_main's own copy of sh_isgem, `$feb162`, which no run makes yet)."""
    result = draw(SH_DRAW, (SHELL_BUFFER, *SH_MAIN_S), merge_pokes(launching(), {GL_SHGEM: bytes(aes.WORD_BYTES)}))
    assert aes.stored_nothing(result)


@THROUGH
def test_sh_draw_draws_the_band_with_the_command_as_sh_main_calls_it(through_line_f):
    """ARGUMENT CLASS (`LAUNCHING`; sh_main's arguments). The clip the whole screen, the band's text pointed at the
    command (the shell's buffer, by the pointer handed), the band drawn from its root one level down — over each of
    two commands a different screen: the string is read and drawn."""
    screens = []
    for command in od.TWO_COMMANDS:
        result = draw(SH_DRAW, (SHELL_BUFFER, *SH_MAIN_S), launching(command), through_line_f=through_line_f)
        assert result.long(PTEXT_AT) == SHELL_BUFFER and gemgraf.clip_of(result) == WHOLE_SCREEN
        screens.append(vdi.screen_of(result.final))
    assert screens[0] != screens[1] and screen_changed(result)


def test_sh_draw_asks_gl_shgem_as_a_word():
    """ARGUMENT CLASS (gl_shgem staged $0100: nonzero, its low byte zero — `tst.w $9b2a`). The band is drawn."""
    result = draw(SH_DRAW, (SHELL_BUFFER, *SH_MAIN_S), merge_pokes(launching(), {GL_SHGEM: b"\x01\x00"}))
    assert result.long(PTEXT_AT) == SHELL_BUFFER and screen_changed(result)


def test_sh_draw_stores_the_command_s_pointer_as_handed():
    """ARGUMENT CLASS. A command pointer with a top byte is stored as it is (ob_draw reads the text on the bus)."""
    result = draw(SH_DRAW, (SHELL_BUFFER | aes.BUS_TAG, *SH_MAIN_S), launching())
    assert result.long(PTEXT_AT) == SHELL_BUFFER | aes.BUS_TAG


def test_sh_draw_reads_the_band_s_tree_before_it_sets_the_clip_and_draws_any_object_asked():
    """ARGUMENT CLASS. The TEXT alone (object 2, depth 0 — sh_show's second pass)."""
    result = draw(SH_DRAW, (SHELL_BUFFER, od.BAND_TEXT, 0), launching())
    assert result.long(PTEXT_AT) == SHELL_BUFFER and screen_changed(result)


# sh_show is handed the path sh_find found: the working path's buffer ($feb0c8 `move.l $c800,-(sp)`).
FOUND_PATHS = (b"A:\\GEM.PRG", b"A:\\APPS\\MEG.PRG")
SH_SHOW_PUSHED = 12                     # below sh_show's A6: its six bytes of locals, sh_draw's object word and path


def show_machine(path):
    return merge_pokes(launching(), shell.working_path(path.decode("latin-1")))


A_TREE_WITH_CHILDREN_UNDER_ITS_FIRST_OBJECT = "menu"


def test_sh_show_draws_each_object_alone_whatever_hangs_under_it():
    """FIRST OF sh_show's CASES, for what it alone can say cleanly: a walk one object too long draws the menu's
    THIRD object here — another screen, a failed test — where over the band, which has no third, it never comes
    back (a hung suite and no verdict).
    ARGUMENT CLASS (ad_stdesk staged at ANOTHER OF THE AES's OWN TREES — the menu's, whose objects 1 and 2 have
    children; the band's two objects are leaves, over which a depth of 0 and of 1 draw the same). sh_show's depth is
    0: object 1 and object 2 alone — a deeper walk draws the children, another screen."""
    tree = od.trees()[A_TREE_WITH_CHILDREN_UNDER_ITS_FIRST_OBJECT]
    assert aes.signed(aes.read_field(BASE_IMAGE, "OB", "HEAD", tree + aes.OB_BYTES)) != aes.OB_NIL, "object 1 has a child"
    machine = merge_pokes(show_machine(FOUND_PATHS[0]), aes.field_pokes("AES", AD_STDESK=tree))
    result = draw(SH_SHOW, (aes.AES_SH_PATH_BUFFER,), machine)
    assert screen_changed(result)


def test_sh_show_draws_the_band_s_two_objects_with_the_path():
    """ARGUMENT CLASS (`LAUNCHING`; sh_find's argument). Objects 1 and 2 each drawn alone with the path handed —
    two paths, two screens — the band's text left pointing at it. Entered DIRECTLY: no Line-F word names sh_show
    (its one caller reaches it by address: sh_find's `jsr (a0)`, below)."""
    assert not aes.line_f_call_sites(SH_SHOW)
    screens = []
    for path in FOUND_PATHS:
        result = draw(SH_SHOW, (aes.AES_SH_PATH_BUFFER,), show_machine(path))
        assert result.long(PTEXT_AT) == aes.AES_SH_PATH_BUFFER and gemgraf.clip_of(result) == WHOLE_SCREEN
        screens.append(vdi.screen_of(result.final))
    assert screens[0] != screens[1]


def _shown_by_our_sh_show(buf, registers):
    """sh_find's routine served by OUR sh_show: the path it is called over (the register hook's A0 slot)."""
    _lib.aes_sh_show(buf, registers[isr.REGISTER["a0"]])


def test_sh_find_handed_sh_show_as_sh_main_hands_it_shows_the_path_it_found():
    """THE BY-VALUE SITE (`$feb272 move.l #$feaddc,(sp)`): the ROM's own sh_find handed THE ROM'S sh_show's address,
    as sh_main hands it, against our sh_find calling OUR sh_show through `call_alcyon_pointer` — GEMDOS scripted to
    find the file as given. ARGUMENT CLASS (`LAUNCHING`). The band shows the path sh_find built; the whole image
    and the GEMDOS ledger are the ROM's."""
    routines_ = {**aes.walkers(od.JUST_DRAW), addrs.AES_ROM_SH_SHOW: (b"", _shown_by_our_sh_show)}
    doors = aes.doors(gsx.vdi_hook, shell.scripted_hook, aes.alcyon_object_hook(routines_))
    machine = merge_pokes(launching(), shell.STALE_DOS, shell.OPEN_FOR_THE_HOST, shell.DIRTY_FRAMES,
                          shell.scripted_pokes([0, 0]), shell.spec("GEM.PRG"), shell.working_path())
    result = aes.run_function(shell.SH_FIND, (shell.SPEC_AT, addrs.AES_ROM_SH_SHOW), machine, hook=doors,
                              max_insns=ob_draw.OB_DRAW_INSNS, poison=False)
    assert result.answer() == 1 and result.long(PTEXT_AT) == aes.AES_SH_PATH_BUFFER
    assert screen_changed(result)


def test_sh_show_s_first_draw_is_object_1_alone_with_the_path():
    """The walk's start, on the ROM's own run stopped at sh_draw's entry: the path handed, object 1, depth 0
    (`$feade0 move.w #1,-2(a6)`, `$feade8 clr.w (sp)`). Its end — object 2 the last — is the screen's and the
    VDI's: a third draw would be another image."""
    staged = aes.staged(SH_SHOW, (aes.AES_SH_PATH_BUFFER,), show_machine(FOUND_PATHS[0]))
    final, _writes, regs = emu.run(make_image(staged), addrs.AES_ROM_SH_SHOW, {}, stop_pc=addrs.AES_ROM_SH_DRAW)
    frame = regs["a6"] - SH_SHOW_PUSHED     # sh_show's A6: its `link #-6`, then the object's word and the path pushed
    assert (case.long_in(final, frame), case.word_in(final, frame + 4), case.word_in(final, frame + 6)) == (
        aes.AES_SH_PATH_BUFFER, SHLIB["SH_SHOW_FIRST"], SHLIB["SH_SHOW_DEPTH"])


# ---- the registry --------------------------------------------------------------------------------------------------------------
def _register(label, name, arguments, machine, hook):
    aes.register(label, name, arguments, machine, hook=hook)


# The two screen switches' rows are settled by the event layer's one registrar (`aes_event.register_row`), which
# names no routine: every word that differs by nature which the ROM's run stores — the mask word, spl7_save's SR
# save word under the vector take's bracket — staged at the value the run leaves and dropped at Tier 3 by name, with
# the companion that drops nothing (a drop held to OUR run's ledger too: a build that lost the bracket stores no
# word and is refused).
aes_event.register_row("to a text program, the cursor hidden", SH_TOALPHA, (), switch_machine(GEMDOS_OK), hook=SWITCH_DOORS)
aes_event.register_row("back from the machine the ROM's sh_toalpha left", SH_TOGRAPHIC, (), in_alpha(), hook=SWITCH_DOORS)
_register("the desk running: nothing drawn", SH_DRAW, (SHELL_BUFFER, *SH_MAIN_S),
          merge_pokes(ob_draw.machine(), ob_draw.STALE_SLOTS), DRAW_DOORS)
_register(f"{ARGUMENT_CLASS}: a launch asked by the ROM's shel_write, the band drawn as sh_main draws it", SH_DRAW,
          (SHELL_BUFFER, *SH_MAIN_S), launching(), DRAW_DOORS)
_register(f"{ARGUMENT_CLASS}: a launch asked by the ROM's shel_write, the path sh_find found shown", SH_SHOW,
          (aes.AES_SH_PATH_BUFFER,), show_machine(FOUND_PATHS[0]), DRAW_DOORS)
