"""THE OBJECT DRAW PATH's staging — how a battery draws one object of a REAL tree through just_draw
(`src/aes/objdraw.c`), over `test/aes_gsx.py`'s door (the cursor hidden the AES's way, every VDI call the C makes served
by the VDI's own C cores, the WHOLE image compared, the screen included).

THE TREES ARE THE SNAPSHOT's. The AES's own resource (`aes.resource_tree`: 0 the file selector, 1 the alert, 2 the
desktop's band), the desk's (its application global[], `AES_DESK_APP_GLOBAL`: 0 the menu, 1..13 its dialogs), the menu
bar's (`AES_GL_MNTREE`), the desktop's (`AES_GL_NEWDESK`: the desk's three icons, in the TPA) and the window tree
(`AES_WINDOW_TREE`). A case names an object of one by its index and draws it where ob_offset would put it — every
type and every state the census below finds is drawn from these. What no tree carries (FTEXT, USERDEF, SHADOWED,
CROSSED, ...) a case STAGES on a real object — a state bit set as the ROM's own ob_change would set it, a seeded string
— and says so; nothing here fabricates a record a real one could stand for.

THE TREES ARE WALKED BY THEIR LINKS, as the AES walks them: the AES's tree 2 has no LASTOB object at all, so
`aes.tree_length` would read past it.
"""
import functools
import struct

from harness import BASE_IMAGE, addrs, emu, make_image

import abi
import aes
import aes_gsx as gsx
import aes_obuser as obuser
import case
import test_aes_gemgraf  # gemgraf.h's constants, and gsx_sclip's and gsx_tblt's signatures for the clip's and font's runs
import vdi
from aes_objects import object_word, screen_origin
from case import merge_pokes
from test_aes_gsx import PTSIN_READ_BEFORE_IT_IS_PUT_BACK, screen_changed

JUST_DRAW = "AES_ROM_JUST_DRAW"
SCLIP = "AES_ROM_GSX_SCLIP"

# The OB_TYPE values the census names, and the state bits a case sets — `aes/objects.h`'s, by name.
TYPES = {name: getattr(aes, name) for name in ("G_BOX", "G_TEXT", "G_BOXTEXT", "G_IMAGE", "G_USERDEF", "G_IBOX",
                                               "G_BUTTON", "G_BOXCHAR", "G_STRING", "G_FTEXT", "G_FBOXTEXT", "G_ICON",
                                               "G_TITLE")}
STATE_BITS = {name: 1 << getattr(aes, f"OB_STATE_{name}_BIT")
              for name in ("SELECTED", "CROSSED", "CHECKED", "DISABLED", "OUTLINED", "SHADOWED")}
# ...and OB_FLAGS' low-byte bits, the same way (`aes/objects.h`'s OB_FLAG_*_BIT).
FLAG_BITS = {name: 1 << getattr(aes, f"OB_FLAG_{name}_BIT")
             for name in ("SELECTABLE", "DEFAULT", "EXIT", "EDITABLE", "RBUTTON", "TOUCHEXIT", "HIDETREE")}


def object_long(tree, index, name, image=BASE_IMAGE):
    return case.long_in(image, tree + index * aes.OB_BYTES + aes.field("OB", name).at)


# ---- the snapshot's trees ---------------------------------------------------------------------------------------------
def resource_trees(application_global=None):
    """Every tree of the resource the application `global[]` at `application_global` has loaded (the AES's own when
    None), by index."""
    return [aes.resource_tree(index, application_global=application_global)
            for index in range(aes.resource_tree_count(application_global=application_global))]


@functools.cache
def trees():
    """`{name: tree}`: every tree the snapshot holds that the AES draws."""
    gem = resource_trees()
    desk = resource_trees(aes.AES_DESK_APP_GLOBAL)
    named = {"selector": gem[0], "alert": gem[1], "desktop band": gem[2],
             "menu": case.long_in(BASE_IMAGE, aes.AES_GL_MNTREE), "desk icons": case.long_in(BASE_IMAGE, aes.AES_GL_NEWDESK),
             "windows": aes.AES_WINDOW_TREE}
    named.update({f"desk tree {index}": tree for index, tree in enumerate(desk)})
    return named


def real(name, index):
    """`(tree, index)`: object `index` of the snapshot's tree `name` (`trees()`)."""
    return trees()[name], index


# The real objects more than one battery draws.
EXIT_BUTTON = real("selector", 21)      # OK: a default exit button, border -3
DROP_DOWN = real("menu", 17)            # a box, border -1: a menu's drop-down
MENU_ITEM = real("menu", 29)            # a CHECKED menu item
TRASH = real("desk icons", 6)           # the desk's trash icon
# Where a case draws an icon: on the desktop's pattern, clear of the three the snapshot shows (each drawn over itself
# changes nothing).
ICON_PLACE = (120, 60)


def link_order(tree, image=BASE_IMAGE):
    """The objects of `tree` in the order everyobj reaches them — by ob_head and ob_next, depth first."""
    order, seen = [], set()

    def visit(index):
        assert index not in seen and len(seen) < aes.TREE_OBJECTS, f"the tree at {tree:#x} does not end"
        seen.add(index)
        order.append(index)
        child = object_word(image, tree, index, "HEAD")
        while child not in (aes.OB_NIL, index):
            visit(child)
            child = object_word(image, tree, child, "NEXT")
    visit(aes.OB_ROOT)
    return order


def object_type(tree, index, image=BASE_IMAGE):
    return object_word(image, tree, index, "TYPE") & aes.OB_TYPE_MASK


@functools.cache
def census():
    """`[(tree name, index, type, state)]`: every object of every tree the snapshot holds, in link order."""
    return [(name, index, object_type(tree, index), object_word(BASE_IMAGE, tree, index, "STATE") & 0xFFFF)
            for name, tree in trees().items() for index in link_order(tree)]


# ---- the fields the cases reach outside the window (`aes.declare_case_field`) ------------------------------------------
def _declare_case_fields():
    """Every span a case of this module stages outside the AES's window: each tree's objects, each text object's
    TEDINFO and the buffer its raw text is seeded into, and the AES globals the cases set."""
    for name, tree in trees().items():
        objects = link_order(tree)
        aes.declare_case_field(tree, (max(objects) + 1) * aes.OB_BYTES, f"the snapshot's {name} tree")
        for index in objects:
            if object_type(tree, index) not in (aes.G_TEXT, aes.G_BOXTEXT, aes.G_FTEXT, aes.G_FBOXTEXT):
                continue
            tedinfo = object_long(tree, index, "SPEC")
            aes.declare_case_field(tedinfo, aes.TE_BYTES, f"the {name} tree's object {index}'s TEDINFO")
            text = case.long_in(BASE_IMAGE, tedinfo + aes.TE_PTEXT)
            if text != aes.OB_SPEC_NONE:
                aes.declare_case_field(text, case.word_in(BASE_IMAGE, tedinfo + aes.TE_TXTLEN),
                                       f"the {name} tree's object {index}'s raw text")
    aes.declare_case_field(SHELL_BUFFER, aes.AES_SHELL_LINE_BYTES, "the shell's buffer, the desktop band's string")
    for field in ("GL_FONT", "GL_WCLIP", "GL_HCLIP", "GL_HCHAR", "GL_MODE", "AD_INTIN", "EDBLK", "RAWSTR", "TMPLT",
                  "FMTSTR", "BI", "IB"):
        spec = aes.field("AES", field)
        aes.declare_case_field(spec.at, spec.width * (spec.count or 1), f"just_draw's {field}")


def first_of(type_name, *, state=None, tree=None):
    """`(tree, index)` of the first object of `type_name` (and `state`, when given) the census finds."""
    for name, index, kind, its_state in census():
        if kind == TYPES[type_name] and (state is None or its_state == state) and (tree is None or name == tree):
            return trees()[name], index
    raise LookupError(f"no {type_name} object with state {state} in the snapshot's trees")


# ---- staging on a real object ---------------------------------------------------------------------------------------
# This module's band of the AES window: the strings, TEDINFO and USERBLK a case hands a real object.
BAND_OFFSET = 0xB00                     # the gap between test_aes_gemgraf's band and aes_gsx's at +$c00
BAND_BYTES = 0x100
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_objdraw.py: strings and blocks for real objects")
TEXT_AT = BAND_AT                       # a NUL-ended string
TEXT_BYTES = 0x60
TEMPLATE_AT = TEXT_AT + TEXT_BYTES      # a second one: a template, or a raw text
TEMPLATE_BYTES = 0x60
TEDINFO_AT = TEMPLATE_AT + TEMPLATE_BYTES
USERBLK_AT = TEDINFO_AT + aes.TE_BYTES
assert USERBLK_AT + aes.UB_BYTES <= BAND_AT + BAND_BYTES


def state_pokes(tree, index, state):
    """`index`'s ob_state set to `state` — what the ROM's own ob_change stores ($fea3ee move.w)."""
    return aes.object_pokes(tree, index, STATE=state)


def flags_pokes(tree, index, flags):
    return aes.object_pokes(tree, index, FLAGS=flags)


def type_pokes(tree, index, type_name):
    """`index`'s type made `type_name` (a G_* name, or a number), its extended high byte kept."""
    kind = TYPES[type_name] if isinstance(type_name, str) else type_name
    high = object_word(BASE_IMAGE, tree, index, "TYPE") & ~aes.OB_TYPE_MASK & 0xFFFF
    return aes.object_pokes(tree, index, TYPE=high | kind)


def spec_pokes(tree, index, spec):
    return aes.object_pokes(tree, index, SPEC=spec & 0xFFFFFFFF)


# A box's spec as ob_sst and gr_crack read it: its first byte the character (a BOXCHAR's), its second the border's
# thickness (signed), its low word the colour word.
BOX_SPEC_FIELDS = ">BbH"
GRAF = test_aes_gemgraf.GRAF


def box_spec(tree, index, **changed):
    """`index`'s ob_spec with any of its `character`, `thickness` or `colour` changed."""
    fields = dict(zip(("character", "thickness", "colour"),
                      struct.unpack(BOX_SPEC_FIELDS, struct.pack(">I", object_long(tree, index, "SPEC")))))
    assert changed.keys() <= fields.keys(), changed
    fields.update(changed)
    return struct.unpack(">I", struct.pack(BOX_SPEC_FIELDS, *fields.values()))[0]


def colour_word(border, text):
    """A colour word with its border's and its text's colours set, as gr_crack splits them — a hollow fill of colour 0,
    the text transparent."""
    return border << GRAF["CRACK_BORDER_SHIFT"] | text << GRAF["CRACK_TEXT_SHIFT"]


def size_pokes(tree, index, width, height):
    return aes.object_pokes(tree, index, WIDTH=width & 0xFFFF, HEIGHT=height & 0xFFFF)


def string_pokes(text, at=TEXT_AT, room=TEXT_BYTES):
    """A NUL-ended string at `at`."""
    assert len(text) < room
    return {at: text + b"\0"}


def seeded_text(tree, index, text):
    """A text object's raw text as the desk's inf_sset leaves it before a dialog is drawn (`aes_obuser.seeded_raw_pokes`),
    within the buffer's te_txtlen."""
    assert len(text) < case.word_in(BASE_IMAGE, object_long(tree, index, "SPEC") + aes.TE_TXTLEN)
    return obuser.seeded_raw_pokes(tree, index, text)


def tedinfo_pokes(tree, index, **fields):
    """Fields of the TEDINFO `index` points at, by name."""
    return aes.tedinfo_pokes(object_long(tree, index, "SPEC"), **fields)


# ---- the desktop's band: its TEXT as sh_draw leaves it ---------------------------------------------------------------
# The AES's tree 2's TEXT (object 2) is sh_draw's ($feada0): ad_pfile (AES_AD_PFILE) names its TEDINFO's te_ptext, and
# sh_draw stores its string through it — the shell's buffer, on the launch path ($feb1a8..) — under
# gsx_sclip(gl_rscreen), right before ob_draw(ad_stdesk, ...). Its -1 in the snapshot is the resource's placeholder
# until the first launch.
BAND_TEXT = 2
SHELL_BUFFER = case.long_in(BASE_IMAGE, aes.AES_SHELL_BUFFER)


def band_text_pokes(command):
    """The band's TEXT as sh_draw leaves it: te_ptext the shell's buffer, `command` in it."""
    return merge_pokes(tedinfo_pokes(trees()["desktop band"], BAND_TEXT, PTEXT=SHELL_BUFFER), string_pokes(
        command, at=SHELL_BUFFER, room=aes.AES_SHELL_LINE_BYTES))


def sh_draw_machine(onto=None):
    """The clip sh_draw sets (gsx_sclip(gl_rscreen): the whole screen), over the snapshot's own font."""
    return screen_clip_machine(onto, font=SNAPSHOT_FONT)


# Two commands a launch could leave there: the band drawn with each differs only if the string is read and drawn.
TWO_COMMANDS = (b"A:\\GEM.PRG", b"A:\\MEG.PRG")


def band_screens(draw):
    """The screens `draw(pokes, **kwargs)` leaves with the band's TEXT as sh_draw leaves it, one per command of
    TWO_COMMANDS. The text changes the font, which reads PTSIN first (`PTSIN_READ_FIRST`; measured: poisoned, the ROM's
    run spins to the cap)."""
    return [vdi.screen_of(draw(band_text_pokes(command), **PTSIN_READ_FIRST).final) for command in TWO_COMMANDS]


def redrawn_as_it_stands(result):
    """Whether a draw WROTE the screen and left it as staged — an object drawn over its own pixels, as the snapshot
    shows it (a label in another font or at another place differs)."""
    written = any(vdi.SCREEN.base <= at < vdi.SCREEN.base + vdi.SCREEN.bytes for at in result.info["writes"])
    return written and not screen_changed(result)


# ---- USERDEF: a USERBLK on a real object, its routine `test/aes_obuser.py`'s -----------------------------------------
USERDEF_PARM = 0x5EED0B1E               # the USERBLK's ub_parm, which the PARMBLK carries to the routine


def userdef_pokes(tree, index, answer):
    """`index` made a USERDEF whose USERBLK (in this band) names `aes_obuser`'s routine answering `answer`."""
    return merge_pokes(type_pokes(tree, index, "G_USERDEF"), spec_pokes(tree, index, USERBLK_AT),
                       aes.userblk_pokes(USERBLK_AT, CODE=obuser.USERDEF_AT, PARM=USERDEF_PARM),
                       obuser.userdef_pokes(answer))


def userdef_doors(answer):
    """The VDI's door and the USERDEF routine's, opened together for one case."""
    return aes.doors(gsx.vdi_hook, obuser.userdef_hook(answer))


# ---- the machine: the door's, the IBM font cached --------------------------------------------------------------------
# THE SNAPSHOT CACHES THE SMALL FONT (gl_font 5): the desk's last text was an icon's label. Every label and IBM text a
# tree draws after its first finds the IBM font (3) cached instead, gsx_tblt then skipping vst_height — so the default
# machine stages that; an ICON's label is in the small font, so an icon is drawn over the snapshot's own cache; and a
# FONT CHANGE is a case of its own.
# gl_font CACHES THE VDI's FACE: its only writers are gsx_start ($fdaace, -1, the VDI left at IBM) and gsx_tblt
# ($fdad4a, right after its own vst_height). So the IBM font cached is the AES's word AND the VDI's text size — what the
# ROM's own gsx_tblt of the IBM font leaves. Its run, of no characters (nothing drawn), from the snapshot's machine; laid
# over a machine as the run's WRITES only, so it keeps whatever that machine stages (a shown cursor, a clip).
FONT_IBM = GRAF["GSX_FONT_IBM"]
TBLT = "AES_ROM_GSX_TBLT"
SNAPSHOT_FONT = aes.field_pokes("AES", GL_FONT=case.word_in(BASE_IMAGE, aes.AES_GL_FONT))    # the small font


def rom_run(routine, arguments, pokes, **kwargs):
    """The ROM's own `routine` (an `addrs` name) over `arguments` staged on `pokes`, the oracle alone (`kwargs` are
    `emu.run`'s): `(staged, final, writes)`, its write ledger whole."""
    staged = aes.staged(routine, arguments, pokes)
    final, writes, regs = emu.run(make_image(staged), getattr(addrs, routine), **kwargs)
    assert not regs.get("writes_truncated"), f"{routine}'s run overflowed the write ledger"
    return staged, final, writes


def _ibm_font_as_the_rom_caches_it():
    _staged, final, writes = rom_run(TBLT, (FONT_IBM, 0, 0, 0), gsx.machine(SNAPSHOT_FONT))
    assert case.word_in(final, aes.AES_GL_FONT) == FONT_IBM, "the ROM's gsx_tblt did not cache the IBM font"
    return merge_pokes(case.written_by(writes), gsx.CONTRL_STALE)


IBM_FONT_CACHED = _ibm_font_as_the_rom_caches_it()
# THE ATTRIBUTION PASS IS OFF (`test_aes_gsx.PTSIN_READ_BEFORE_IT_IS_PUT_BACK`) for a draw that READS the parameter
# block's PTSIN before any call points it — gsx_tblt's v_gtext and vst_height never do ($fdad0a, $fe8b22) — and LATER
# makes a call whose wrapper stores it back ($fe8bd0): a label (or a font change) followed by a state's mark. The pass
# inverts every byte the ROM's run stores, so the poisoned run hands the VDI $ff673b and both sides read the I/O page
# (measured: the oracle refuses the unmodelled read). Each such case's machine stages STALE what the draw stores.
PTSIN_READ_FIRST = PTSIN_READ_BEFORE_IT_IS_PUT_BACK


def machine(onto=None, font=IBM_FONT_CACHED):
    """The door's machine (`aes_gsx.machine`), the IBM font cached unless `font` says otherwise, `onto` over it."""
    return gsx.machine(merge_pokes(font, onto))


def snapshot_font_machine(onto=None):
    """...over the snapshot's own font cache instead: an icon's (its label is in the small font), and a whole tree's
    first draw's."""
    return machine(onto, font=SNAPSHOT_FONT)


# THE CLIP: the snapshot's is the desktop below the menu bar (0, 11, 320, 189), which every dialog and the desk's
# windows are drawn under. The menu bar is drawn under the WHOLE screen's — the clip as the ROM's own
# gsx_sclip(gl_rscreen) leaves it (the AES's four words and the VDI's), continued from. Its run is made OVER the font's
# machine and the font not laid again after it: the font's writes hold the VDI's clip words too, and would put the
# desktop's clip back.
def clip_set_by_the_rom(grect_at, pokes):
    """`pokes` continued from the ROM's own gsx_sclip of the GRECT at `grect_at`: the AES's four clip words and the
    VDI's, as it leaves them."""
    _staged, final, writes = rom_run(SCLIP, (grect_at,), pokes)
    return case.continued_from(pokes, final, writes)


@functools.cache
def _screen_clip_pokes(font):
    return clip_set_by_the_rom(aes.AES_GL_RSCREEN, machine(font=dict(font)))


def screen_clip_machine(onto=None, font=IBM_FONT_CACHED):
    """`machine(font=font)` with the clip the whole screen, contrl[0..3] stale again, `onto` over it."""
    return merge_pokes(_screen_clip_pokes(tuple(font.items())), gsx.CONTRL_STALE, onto)


# just_draw's FRAME (`link a6,#-48`): its border colour is the frame's last word, -2(a6) — in the ROM's run entered
# direct, A6 is the saved A6's slot under the return address under abi.FIRST_ARG; in the C, the host slot's last word.
HOST_FRAME_AT = aes.HOST_SLOTS["HOST_SLOT_AES_JUST_DRAW_FRAME"]
HOST_FRAME_BYTES = aes.HOST_SLOTS["HOST_SLOT_AES_JUST_DRAW_FRAME_BYTES"]
ROM_FRAME_TOP = abi.FIRST_ARG - 2 * aes.LONG_BYTES         # A6: below the return address and the saved A6
FRAME_BORDER = -aes.WORD_BYTES                              # -2(a6)
ROM_BORDER_AT = ROM_FRAME_TOP + FRAME_BORDER
HOST_BORDER_AT = HOST_FRAME_AT + HOST_FRAME_BYTES + FRAME_BORDER
# THE FRAME STAGED STALE, on both shores alike: just_draw reads locals it never wrote — a BUTTON's fill colour and
# pattern before it clears them, a TITLE's border colour ever — so a direct draw finds the same STALE words in the
# ROM's frame and in the C's, and a C that skipped one of the ROM's stores reads STALE where the ROM read its own.
_STALE_HOST_FRAME = aes.stale_host_slot("AES_JUST_DRAW_FRAME")
STALE_FRAME = {ROM_FRAME_TOP - HOST_FRAME_BYTES: _STALE_HOST_FRAME[HOST_FRAME_AT], **_STALE_HOST_FRAME}


# ---- the runs -----------------------------------------------------------------------------------------------------------
def arguments(tree, index, at=None):
    """just_draw's frame: the tree, the object and where it is drawn — `at`, or where ob_offset would put it."""
    x, y = screen_origin(BASE_IMAGE, tree, index) if at is None else at
    return tree, index, x, y


def draw(tree, index, pokes=None, *, at=None, onto=None, userdef=None, **kwargs):
    """just_draw of object `index` of `tree` over `machine()` (or `onto`), `pokes` laid on it — and, for a USERDEF
    staged by `userdef_pokes`, `userdef` its routine's answer, the routine's door opened beside the VDI's."""
    staged = merge_pokes(machine() if onto is None else onto, STALE_FRAME, pokes)
    hook = gsx.vdi_hook if userdef is None else userdef_doors(userdef)
    return aes.run_function(JUST_DRAW, arguments(tree, index, at), staged, hook=hook, **kwargs)


def drawn_nothing(result):
    """No VDI call made: contrl[0] (the opcode) never stored."""
    return not result.info["writes"].keys() & set(range(aes.AES_GSX_CONTRL, aes.AES_GSX_CONTRL + aes.WORD_BYTES))


def register(label, tree, index, pokes=None, *, at=None, onto=None, userdef=None, through_line_f=False):
    """...and the same draw as a `VERIFIED_CASES` row."""
    staged = merge_pokes(machine() if onto is None else onto, pokes)
    hook = gsx.vdi_hook if userdef is None else userdef_doors(userdef)
    aes.register(label, JUST_DRAW, arguments(tree, index, at), staged, through_line_f=through_line_f, hook=hook)


_declare_case_fields()
