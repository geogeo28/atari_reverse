"""THE AES's VDI DOOR — how a battery runs an AES routine that reaches the VDI (`aes/gsx.h`, `src/aes/gsx.c`).

ONE `trap #2` CARRIES EVERY GRAPHIC CALL the AES makes: gsx2 stores the parameter block's contrl pointer and traps,
and in ROM mode the oracle takes that trap through the snapshot's own vector ($88 -> GEM's $fe3ea6 -> SYSVAR_VDI_ENTRY
$fc4ebc -> the ROM's VDI). The candidate's bridge (`gsx_trap`) checks both hops and calls the VDI's C twin of its
entry, whose dispatcher leaves through `staged_call.h`'s bare hook: `vdi_functions()` binds it, for every case, to
the C cores of every VDI function the AES's graphics reach — so both shores run a VDI (the ROM's, the reconstructed
one) and a divergence in either reds here. That is a second differential of the VDI, and welcome.

THE SURFACE IS THE WHOLE IMAGE, the screen at the top of RAM included: a call that draws is compared pixel for pixel.

THE MACHINE (`machine`). The snapshot has the AES's cursor SHOWN (gl_moff 0, the VDI's hide depth 0, the arrow drawn
over its save block) — a real state, but one every drawing call would have to draw round. So the door's default is
the cursor HIDDEN THE WAY THE AES HIDES IT: the snapshot run through the ROM's own gsx_moff once and continued from
(`case.continued_from`) — the nest 1, the VDI's depth 1, the background restored from the save block. In it gsx_moff
and gsx_mon are counter-only; `shown_machine` is the snapshot's own, where they reach v_hide_c / v_show_c. Both stage
contrl[0..3], which the snapshot's MASK covers (the idle loop's keyboard poll rewrites them), stale. The oracle
takes no interrupt, so no VBL redraws the cursor behind a case's back.

NEVER STAGED: the drawing vectors $2a14.. (the snapshot's CPU set — `require_cpu_routine` halts both builds on a
repointed one, the blitter's) and a device code other than the snapshot's in `$8908` (a resolution change halts).
"""
import functools

import pytest

from harness import addrs, emu, make_image

import aes
import case
import isr
import vdi
import vdi_entry
import vdi_helpers
from case import merge_pokes

# ---- the VDI functions a candidate's call is served by --------------------------------------------------------------
# Every VDI function the AES's graphics reach (gsxif, gemgraf, gemgrlib and the object draw path), each the
# `VDI_ROM_<FN>` its `_OPCODE` sibling names: ONE table, staged on every case, so a call nothing lists is REFUSED by
# the hook (`address_hook.AddressHook`) rather than served by the wrong function.
REACHED_FUNCTIONS = (
    "VDI_ROM_V_OPNWK", "VDI_ROM_V_CLSWK", "VDI_ROM_ESCAPE", "VDI_ROM_V_PLINE", "VDI_ROM_V_GTEXT", "VDI_ROM_VST_HEIGHT",
    "VDI_ROM_VSL_TYPE", "VDI_ROM_VSL_WIDTH", "VDI_ROM_VSL_COLOR", "VDI_ROM_VST_COLOR", "VDI_ROM_VSF_INTERIOR",
    "VDI_ROM_VSF_STYLE", "VDI_ROM_VSF_COLOR", "VDI_ROM_VSWR_MODE", "VDI_ROM_VQT_ATTRIBUTES", "VDI_ROM_VRO_CPYFM",
    "VDI_ROM_VR_TRNFM", "VDI_ROM_VSC_FORM", "VDI_ROM_VSL_UDSTY", "VDI_ROM_VR_RECFL", "VDI_ROM_VEX_TIMV",
    "VDI_ROM_VRT_CPYFM", "VDI_ROM_V_SHOW_C", "VDI_ROM_V_HIDE_C", "VDI_ROM_VQ_MOUSE", "VDI_ROM_VEX_BUTV",
    "VDI_ROM_VEX_MOTV", "VDI_ROM_VS_CLIP",
)
OPCODE_SUFFIX = "_OPCODE"


def opcode_of(name):
    """The VDI opcode `addrs.<name>`'s `_OPCODE` sibling names."""
    return getattr(addrs, name + OPCODE_SUFFIX)


@functools.cache
def vdi_functions():
    """`{routine address: (no stub, effect)}`: every reached function's C core, where the dispatcher's `jsr` lands."""
    table = {}
    for name in REACHED_FUNCTIONS:
        opcode_of(name)                     # a name with no `_OPCODE` sibling is no VDI function: refused here
        table.update(vdi_entry.function(name))
    return table


def vdi_hook():
    """The binding `aes.run_function`'s `hook` opens per case: the bare hook staged with `vdi_functions()`."""
    return isr.staged_routines(vdi_functions())


# ---- the band the cases stage in ------------------------------------------------------------------------------------
BAND_OFFSET = 0xC00                     # into the AES's window, clear of the bands `test/aes.py` lays from its base
BAND_BYTES = 0x200
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_gsx.py: points, MFDBs, forms and answer words")
POINTS_BYTES = 0x40                     # sixteen points: a caller's pxy array
POINTS_AT = BAND_AT
ANSWERS_AT = POINTS_AT + POINTS_BYTES   # vst_height's four answer words
ANSWERS_BYTES = 0x10
MFDB_AT = ANSWERS_AT + ANSWERS_BYTES    # three MFDBs, each in a slot wider than its AES_MFDB_BYTES
MFDB_SLOTS = 3
MFDB_STRIDE = 0x20
FORM_AT = MFDB_AT + MFDB_SLOTS * MFDB_STRIDE    # two small memory forms
FORM_SLOTS = 2
FORM_BYTES = 0x40
assert MFDB_STRIDE >= aes.AES_MFDB_BYTES and FORM_AT + FORM_SLOTS * FORM_BYTES <= BAND_AT + BAND_BYTES


def mfdb_at(slot):
    """Where MFDB `slot` is staged."""
    assert 0 <= slot < MFDB_SLOTS
    return MFDB_AT + slot * MFDB_STRIDE


def form_at(slot):
    """Where memory form `slot` is staged."""
    assert 0 <= slot < FORM_SLOTS
    return FORM_AT + slot * FORM_BYTES


def points_pokes(*coordinates, at=POINTS_AT):
    """A caller's pxy array: x0, y0, x1, y1, ..."""
    return {at: vdi.pack_words(*coordinates)}


STALE_ANSWERS = {ANSWERS_AT: vdi.pack_words(*[aes.STALE_WORD] * (ANSWERS_BYTES // aes.WORD_BYTES))}
MFDB_FIELDS = ("ADDR", "W", "H", "WDWIDTH", "STAND", "NPLANES")


def mfdb_of(result, at):
    """The MFDB at `at` as `result` left it, its fields in MFDB_FIELDS' order."""
    return tuple(vdi.read_field(result.final, "MFDB", name, at) for name in MFDB_FIELDS)


# The AES's own two MFDBs, gl_src and gl_dst, staged stale: a blit's case sees every field its call stores.
GL_MFDBS_STALE = {aes.AES_GL_SRC: bytes([case.SLACK_FILL]) * aes.AES_MFDB_BYTES,
                  aes.AES_GL_DST: bytes([case.SLACK_FILL]) * aes.AES_MFDB_BYTES}


# ---- the fields the cases reach outside the window (`aes.declare_case_field`) -----------------------------------------
# contrl[0..3] are NOT among them: the snapshot's MASK covers them, which is why every machine below stages them.
CASE_WORDS_OF_AN_ARRAY = 8              # intin's and ptsin's first words: the most any atom's call writes or a case stages
for _name in ("GL_HANDLE", "GL_MOFF", "GL_MOUSE_SHOWN", "GL_NPLANES", "GSX_HANDLE", "GSX_PB_CONTRL", "GSX_PB_INTIN",
              "GSX_PB_PTSIN", "GSX_PB_INTOUT", "GSX_PB_PTSOUT", "GSX_CONTRL_PTR", "GSX_CONTRL_PTR2"):
    _field = aes.field("AES", _name)
    aes.declare_case_field(_field.at, _field.width, f"the VDI binding's {_name}")
for _array in (aes.AES_GSX_INTIN, aes.AES_GSX_PTSIN, aes.AES_GSX_PTSOUT, aes.AES_GL_WS):
    aes.declare_case_field(_array, CASE_WORDS_OF_AN_ARRAY * aes.WORD_BYTES, "an array the VDI binding's calls carry")


# ---- the machine -----------------------------------------------------------------------------------------------------
CONTRL_STALE = aes.stale_fields("GSX_OPCODE", "GSX_N_PTSIN", "GSX_N_PTSOUT", "GSX_N_INTIN")
NEST_SHOWN = 0                          # the snapshot's gl_moff
NEST_HIDDEN = 1                         # ...and after the one gsx_moff `machine` is continued from


def shown_machine(onto=None):
    """The snapshot's own: the AES's cursor shown and drawn, contrl[0..3] stale."""
    return aes.leaf_machine(onto=merge_pokes(CONTRL_STALE, onto))


@functools.cache
def _hidden():
    """The snapshot after the ROM's own gsx_moff: its end state, as the pokes a run starts from."""
    pokes = shown_machine()
    final, writes, regs = emu.run(make_image(pokes), addrs.AES_ROM_GSX_MOFF)
    assert not regs.get("writes_truncated"), "gsx_moff's run overflowed the write ledger"
    assert aes.read_field(final, "AES", "GL_MOFF") == NEST_HIDDEN, "the ROM's gsx_moff did not hide the cursor"
    return case.continued_from(pokes, final, writes)


def machine(onto=None):
    """The door's default: the cursor hidden by the AES (`_hidden`), contrl[0..3] stale again, `onto` over it."""
    return merge_pokes(_hidden(), CONTRL_STALE, onto)


# ---- the run doors ---------------------------------------------------------------------------------------------------
def run_gsx(name, arguments, pokes=None, *, onto=None, **kwargs):
    """`aes.run_function` of the AES routine `addrs.<name>` over `machine()` (or `onto`, a machine of the case's own)
    with `pokes` laid on it, the candidate's VDI calls served by `vdi_functions()`."""
    staged = merge_pokes(machine() if onto is None else onto, pokes)
    return aes.run_function(name, arguments, staged, hook=vdi_hook, **kwargs)


def register(label, name, arguments, pokes=None, *, onto=None, through_line_f=False, io_seed=None):
    """...and the same machine as a `VERIFIED_CASES` row (`aes.register`), its companion served the same way."""
    staged = merge_pokes(machine() if onto is None else onto, pokes)
    return aes.register(label, name, arguments, staged, through_line_f=through_line_f, hook=vdi_hook, io_seed=io_seed)


def register_rows(rows, line_f=()):
    """A battery's rows `{label: (name, arguments, pokes)}`, each registered direct, then those labelled in `line_f`
    once more through the routine's Line-F call word."""
    for label, (name, arguments, pokes) in rows.items():
        register(label, name, arguments, pokes)
    for label in line_f:
        name, arguments, pokes = rows[label]
        register(label, name, arguments, pokes, through_line_f=True)


# Each case run twice: entered direct, and through the routine's Line-F call word.
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))


# ---- the host's refusals -----------------------------------------------------------------------------------------------
def pointer(value):
    """A pointer argument of a host core's child call (`vdi_helpers.refusal_over`'s `arguments`)."""
    return ("ctypes.c_uint32", str(value))


def odd_pointer_refused(symbol, arguments, pokes=None):
    """A host core's refusal of a word or longword through an odd pointer: the 68000's address error, which the
    oracle's Musashi does not raise (`m68k_idioms.h`'s bus family)."""
    returncode, stderr, _image = vdi_helpers.refusal_over(symbol, machine(pokes), arguments=arguments, read_back=False)
    assert returncode != 0 and "address error" in stderr, stderr
