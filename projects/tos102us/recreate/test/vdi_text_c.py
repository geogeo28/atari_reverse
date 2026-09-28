"""What the TEXT LAYER's batteries share (`src/vdi/text.c`): the two Alcyon calls' signatures, a band of real
fonts, the GDOS chain vst_load_fonts is handed, and the ring as the dispatcher leaves it.

THE FONTS ARE THE ROM'S. Every staged header starts as a byte copy of one of the three ROM headers — its
offset table and form pointers still the ROM's — and a case changes only what a GDOS font of another face or
size would: its id, point size, metrics and flags. Where a routine reads a FORM (text_init's and
vst_load_fonts' byte swap) the form is a copy of the ROM font's own, turned into Intel byte order the way a
font file holds it, so the swap has a right answer the case can name: the ROM's form.

WHAT NO ROM FONT HAS is a horizontal offset table or a proportional offset table: all three are monospaced
and flagged so. `proportional_font` builds the one a GDOS proportional face would carry — an advance per
character that differs — and its HOR_TABLE, for the two arms (vqt_extent's bold widening, vqt_width's
offsets) that only such a font reaches.

THE RING. The snapshot's is [ROM 6x6] [RAM 8x8 -> RAM 8x16] [loaded] [0], all face 1, and the dispatcher
copies WS_LOADED_FONTS into the loaded slot on every call; `loaded_machine` stages exactly that, so the size
setters walk the system face across TWO slots and on into a loaded chain behind them.
"""
from harness import BASE_IMAGE

import staging
import vdi
from vdi import IMAGE_ARG, WORD_BYTES
from vdi_text import FONTS, font_field

# ---- the Alcyon calls: `void f(void)` in the ROM, the image alone here --------------------------------
vdi.declare_alcyon("VDI_ROM_TEXT_INIT", None, (IMAGE_ARG,))
vdi.declare_alcyon("VDI_ROM_MAKE_HEADER", None, (IMAGE_ARG,))

HEADER = vdi.FONT_HEADER_BYTES

# ---- the band: in the free RAM above the oracle's stack band, held dead in the snapshot ----------------
BAND_BASE = 0xC4000
BAND_BYTES = 0x6000
BAND_AT = staging.HIGH_BANDS.claim(BAND_BASE, BAND_BYTES, "test/vdi_text_c.py: fonts, their tables and forms")
vdi.declare_case_field(BAND_AT, BAND_BYTES, "the text layer's staged fonts, tables and forms")
HEADER_STRIDE = 0x60
HEADER_SLOTS = 16
LONG_CONTRL_AT = BAND_AT + HEADER_STRIDE * HEADER_SLOTS        # vst_load_fonts' twelve-word contrl
LONG_CONTRL_BYTES = vdi.CONTRL_FONT_CHAIN + vdi.LONG_BYTES
TABLES_OFFSET = 0x800                                          # past the headers and the long contrl
TABLES_AT = BAND_AT + TABLES_OFFSET                            # a proportional font's two tables
TABLES_BYTES = 0x800
FORMS_AT = TABLES_AT + TABLES_BYTES                            # Intel-order copies of ROM forms
FORMS_BYTES = BAND_BYTES - (FORMS_AT - BAND_AT)
assert LONG_CONTRL_AT + LONG_CONTRL_BYTES <= TABLES_AT


def header_at(slot):
    assert 0 <= slot < HEADER_SLOTS
    return BAND_AT + slot * HEADER_STRIDE


def rom_header_pokes(at, base="8x8", **fields):
    """A header at `at`: ROM font `base`'s 90 bytes, with `fields` staged over it by name."""
    rom = FONTS[base]
    return vdi.merge_pokes({at: bytes(BASE_IMAGE[rom:rom + HEADER])}, vdi.field_pokes("FONT", at, **fields))


def chain_pokes(fonts, first_slot=0):
    """`fonts` — `(base, {fields})` pairs — as headers in consecutive slots from `first_slot`, each linked to
    the next through FONT_NEXT and the last ending the chain. Answers `(pokes, [header addresses])`."""
    pokes, headers = {}, [header_at(first_slot + index) for index in range(len(fonts))]
    for index, (base, fields) in enumerate(fonts):
        following = headers[index + 1] if index + 1 < len(fonts) else 0
        pokes = vdi.merge_pokes(pokes, rom_header_pokes(headers[index], base, **{"NEXT": following, **fields}))
    return pokes, headers


# ---- forms: a ROM font's own, and the same in Intel byte order ----------------------------------------------
def form_bytes(font):
    return font_field(font, "FORM_WIDTH") * font_field(font, "FORM_HEIGHT")


def rom_form(font):
    at = font_field(font, "DAT_TABLE")
    return bytes(BASE_IMAGE[at:at + form_bytes(font)])


def intel_order(data):
    """Every word's two bytes exchanged — a form as a GEM font file holds it."""
    return b"".join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data), 2))


def intel_forms(*fonts):
    """Intel-order copies of `fonts`' ROM forms, back to back in the forms band. Answers `(pokes, [address])`."""
    pokes, at, where = {}, FORMS_AT, []
    for font in fonts:
        assert at + form_bytes(font) <= FORMS_AT + FORMS_BYTES, "the forms band is full"
        pokes[at] = intel_order(rom_form(font))
        where.append(at)
        at += form_bytes(font)
    return pokes, where


# ---- a PROPORTIONAL font, as GDOS would load one ------------------------------------------------------------
# Characters FIRST..LAST with advances that differ, cycling through ADVANCES, and a HOR_TABLE of (left, right)
# byte pairs with negative offsets among them. Its form stays the 8x8's: no routine here draws it.
PROPORTIONAL_FIRST = 0
PROPORTIONAL_LAST = 255
ADVANCES = (3, 5, 7, 4, 6, 9, 2, 8, 11)
HOR_OFFSETS = ((0, 1), (-1, 2), (2, -3), (-4, 0), (1, 1), (0x7F, -0x80))
HOR_ENTRY_BYTES = 2                                            # (left, right), a byte each
PROPORTIONAL_OFF_AT = TABLES_AT
PROPORTIONAL_OFF_ROOM = 0x280                                  # the offset table's 257 words, rounded up
PROPORTIONAL_HOR_AT = PROPORTIONAL_OFF_AT + PROPORTIONAL_OFF_ROOM
PROPORTIONAL_HOR_END = PROPORTIONAL_HOR_AT + (PROPORTIONAL_LAST - PROPORTIONAL_FIRST + 1) * HOR_ENTRY_BYTES
assert (PROPORTIONAL_LAST - PROPORTIONAL_FIRST + 2) * WORD_BYTES <= PROPORTIONAL_OFF_ROOM
# ...and a HOR table's entry 32768 entries BELOW its base, which is where vqt_width's `(a0,a1.w)` index reads
# for a character $4000 past the first (`test_vdi_text_measure.py`): the entry, and the base it is below —
# which is OUTSIDE the band, so the entries the other cases read there (characters $8000: index 0; $7fff and
# $ffff: index -1) are claimed on their own, and no other character of that font is asked.
WRAPPED_HOR_ENTRY_OFFSET = 0x600
WRAPPED_HOR_ENTRY_AT = TABLES_AT + WRAPPED_HOR_ENTRY_OFFSET
WORD_INDEX_REACH = 0x8000                                      # how far below its base a `.w` index reaches
WRAPPED_HOR_TABLE = WRAPPED_HOR_ENTRY_AT + WORD_INDEX_REACH
assert PROPORTIONAL_HOR_END <= WRAPPED_HOR_ENTRY_AT
assert WRAPPED_HOR_ENTRY_AT + HOR_ENTRY_BYTES <= TABLES_AT + TABLES_BYTES
WRAPPED_HOR_BASE_BYTES = 2 * HOR_ENTRY_BYTES                   # index -1 and index 0
WRAPPED_HOR_BASE_AT = staging.HIGH_BANDS.claim(WRAPPED_HOR_TABLE - HOR_ENTRY_BYTES, WRAPPED_HOR_BASE_BYTES,
                                               "test/vdi_text_c.py: the wrapping font's HOR entries at its base")
vdi.declare_case_field(WRAPPED_HOR_BASE_AT, WRAPPED_HOR_BASE_BYTES, "the wrapping font's HOR entries at its base")


def proportional_offsets():
    offsets, x = [], 0
    for character in range(PROPORTIONAL_FIRST, PROPORTIONAL_LAST + 2):
        offsets.append(x)
        x += ADVANCES[character % len(ADVANCES)]
    return offsets


def proportional_hor():
    return bytes(value & 0xFF for character in range(PROPORTIONAL_FIRST, PROPORTIONAL_LAST + 1)
                 for value in HOR_OFFSETS[character % len(HOR_OFFSETS)])


def proportional_font(at, *, flags=vdi.FONT_FLAG_SWAPPED_MASK | vdi.FONT_FLAG_HOR_TABLE_MASK, **fields):
    """A proportional face-3 font at `at`, its offset and hor tables in the tables band."""
    header = rom_header_pokes(at, "8x8", ID=3, POINT=12, FIRST_ADE=PROPORTIONAL_FIRST, LAST_ADE=PROPORTIONAL_LAST,
                              FLAGS=flags, OFF_TABLE=PROPORTIONAL_OFF_AT, HOR_TABLE=PROPORTIONAL_HOR_AT,
                              THICKEN=2, LEFT_OFFSET=2, RIGHT_OFFSET=5, **fields)
    return vdi.merge_pokes(header, {PROPORTIONAL_OFF_AT: vdi.pack_words(*proportional_offsets()),
                                    PROPORTIONAL_HOR_AT: proportional_hor()})


def proportional_advance(character):
    offsets = proportional_offsets()
    index = character - PROPORTIONAL_FIRST
    return offsets[index + 1] - offsets[index]


def rom_advance(font, character):
    """The advance of `character` in ROM font `font`: two neighbouring entries of its offset table."""
    at = font_field(font, "OFF_TABLE") + (character - font_field(font, "FIRST_ADE")) * WORD_BYTES
    return (vdi.rom_word(at + WORD_BYTES) - vdi.rom_word(at)) & 0xFFFF


# ---- the machine: a workstation dispatched over a loaded chain ------------------------------------------------
def loaded_machine(chain=None, *, virtual=None, onto=None, **record):
    """A workstation whose LOADED_FONTS is `chain`'s first header (0 for none) — dispatched, so the ring's
    loaded slot holds it — over `onto`, with `record` staged into it by field. `virtual` is a handle for a
    virtual workstation instead of the physical one."""
    staged = onto if chain is None else vdi.merge_pokes(onto, chain[0])
    loaded = 0 if chain is None else chain[1][0]
    if virtual is not None:
        return vdi.virtual_workstation(virtual, onto=staged, LOADED_FONTS=loaded, **record)
    return vdi.dispatched_pokes(onto=staged, LOADED_FONTS=loaded, **record)


def work_at(pokes):
    """The workstation `pokes` made current."""
    return vdi.linea(vdi.make_image(pokes), "CUR_WORK")


def assert_dead_in_the_snapshot():
    for at, size in ((BAND_AT, BAND_BYTES), (WRAPPED_HOR_BASE_AT, WRAPPED_HOR_BASE_BYTES)):
        assert bytes(BASE_IMAGE[at:at + size]) == bytes(size)
