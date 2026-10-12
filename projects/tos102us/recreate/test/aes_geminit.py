r"""GEM'S START-UP — what gemstart's `.S` (`src/aes/gemstart.S`) and geminit's C (`src/aes/geminit.c`: gem_main, the INF
reader) are proved through, on both shores at once (`test_aes_gemstart.py`, `test_aes_geminit_inf.py`,
`test_aes_geminit_main.py`).

THE READER'S MACHINE. The reader asks GEMDOS up to sixteen times — a block, the drive map, the drive, a directory, a
file, a read, a close, the drive again, the block back — and what the read LEAVES IN THE BLOCK is what it then scans.
So its `trap #1` is `aes_gemdosif`'s RECORDING, SCRIPTED TRAP with one thing more (`ReadLaid`): the handler LAYS THE
FILE'S BYTES INTO THE BLOCK AT THE READ — a labelled staging: the text GEMDOS would have read is the case's — on both
shores, the host twin the same effect. Laid before the run it would be gone: the reader copies the shell's buffer over
the block first.

  * THE LEDGER holds every call's function and its frame's own bytes in order, AND WHAT THE GLUE HAD PARKED AT EACH
    (the two return longwords): the seven sites the reader's Line-F calls park are held one by one, not the last alone.
  * THE BLOCK is a case's own bytes with a GUARD each side, staged FILLed: the reader ends the text at the block + the
    count the read answered — one byte PAST the block for a whole one, BELOW it for a read that failed (behaviour (b)).

BANDS BORROWED, as `aes_loader` borrows them (a machine holds one recorder or the other): the recorder lies in
`aes_gemdosif`'s band, the block and the file's bytes in `aes_fslib`'s script band.

Light on purpose: `test_aes_irq.py` imports this module for gem_entry's by-value sites, at every worker's start.
"""
import ctypes
import struct

from harness import addrs

import aes
import aes_fslib
import aes_gemdosif
import aes_shell
import case
import gemdos
import gemdos_process as process
import isr
import opcodes as op
import transcription
import vdi
import vdi_helpers
from case import merge_pokes

WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
BUS = aes.OS_BUS_ADDR_MASK
GEMINIT = aes.header_constants("geminit.h")
GEMSTART = aes.header_constants("gemstart.h")
LOADER = aes.header_constants("loader.h")
GSXIF = aes.header_constants("gsxif.h")
RESOURCE = aes.header_constants("resource.h")

# ---- gemstart: gem_entry's by-value sites -------------------------------------------------------------------------------
# The three routines gem_entry stores BY VALUE, by the `lea` that names each (census (b), `test_aes_rom_data.py`), and
# THIS BUILD'S ENTRY the `.S`'s operand names in its place (`test_aes_gemstart.py` holds each to its pin). The first two
# are of the switch's kind (`irq.S`: `test_aes_irq.py` takes them off its owed list by this table), the third the trap
# door's.
STORED_BY_VALUE = {0xFD9F86: "aes_rom_justretf", 0xFD9F92: "aes_rom_tick_glue", 0xFD9F9E: "aes_rom_ub_trampoline"}
# ...and where each is stored: what the relocation registry will map the day a build's gem_entry runs (slice B).
STORED_INTO = {0xFD9F86: GSXIF["AES_DRWADDR"], 0xFD9F92: GEMSTART["AES_TICK_ROUTINE"], 0xFD9F9E: aes.AES_USERDEF_TRAMPOLINE}

def default_inf_bytes(memory):
    """How long the ROM's own default INF is: its part's length word in the table the start-up laid in `memory`
    (`aes/resource.h`) — what rom_ram's part 3 copies."""
    return case.word_in(memory, aes.AES_RSC_TABLE + RESOURCE["ROM_RSC_DESKTOP_INF"] * RESOURCE["ROM_RSC_ENTRY_BYTES"]
                        + RESOURCE["ROM_RSC_BYTES"])


# THE USABLE-DISK WORD IS A RETURN ADDRESS'S LOW WORD. `$8992` lies INSIDE gem_entry's first stack — the two bytes under
# its top, `$8994` — so the `move.w #1,$8992` gem_entry makes ($fd9f64) is overwritten by the very next `jsr` it makes
# on that stack: size_theglo's, at the loop's top, whose return address `$00fd9f78` lands on `$8990..$8993`. What the
# reader and ldaccs then test is `$9f78` — non-zero by the ROM's layout, never the 1. In a build it is the low word of
# wherever THAT build links the instruction behind its `jsr`: a word that differs between the shores BY NATURE, and
# that must not be 0 (`test_aes_gemstart.py` holds it on both blobs; `test_aes_geminit_boot.py` reads the ROM's off
# its own boot). AND IT IS `$9f78` ONLY WHILE NO INTERRUPT LANDS ON THAT STACK: gem_entry's clear of THEGLO runs on it
# at mask 3, and an exception frame taken there lays the interrupted PC over the same four bytes — the machine's own
# captures hold `$9f80` or `$9f82` (the clear loop's two instructions) at the idle, by the capture. So the idle
# snapshot's MASK covers the word (`tools/boot_snapshot.py`: `$8930..$8bff`), and it is NOT A DECLARED CASE FIELD
# below: every case of the reader's STAGES ITS OWN (`reader_machine`), as `aes_gsx` stages the VDI's contrl words.
SIZE_THEGLO_CALLED_AT = 0xFD9F72
SIZE_THEGLO_RETURNS_TO = SIZE_THEGLO_CALLED_AT + transcription.JSR_BYTES
THE_ROM_S_USABLE_WORD = SIZE_THEGLO_RETURNS_TO & aes.WORD_MASK
LEAVES_THE_FIRST_STACK_AT = 0xFD9FBC    # gem_entry's `movea.l a6,sp`: PD0's stack from here — the last PC a frame up there can hold
MOVEA_L_A6_SP = 0x2E4E

# ---- the reader, and how it is called -----------------------------------------------------------------------------------
READ_INF = "AES_ROM_GEM_READ_INF"
aes.declare_alcyon(READ_INF, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
INF_BUFFER_BYTES = GEMINIT["INF_BUFFER_BYTES"]
DISK_USABLE, RSCHANGE, RESTYPE = LOADER["AES_DISK_USABLE"], GSXIF["AES_GL_RSCHANGE"], GSXIF["AES_GL_RESTYPE"]
for _at, _what in ((RSCHANGE, "the resolution-change word"), (RESTYPE, "the device code")):
    aes.declare_case_field(_at, WORD_BYTES, f"the INF reader's cases: {_what}")
aes.declare_case_field(aes.AES_SHELL_GEM_BUFFER, INF_BUFFER_BYTES, "the shell's GEM buffer, which the INF reader replaces")

MALLOC, MFREE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN
DGETDRV, DSETDRV, DSETPATH = addrs.GEMDOS_DGETDRV_FN, addrs.GEMDOS_DSETDRV_FN, addrs.GEMDOS_DSETPATH_FN
FOPEN, FREAD, FCLOSE = addrs.GEMDOS_FOPEN_FN, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FCLOSE_FN
# Each function the reader's calls reach, with how many bytes of its frame are ITS OWN (`aes_gemdosif.Recorder`).
FRAME_BYTES = {DGETDRV: 0, DSETDRV: WORD_BYTES, FCLOSE: WORD_BYTES, MALLOC: LONG_BYTES, MFREE: LONG_BYTES,
               DSETPATH: LONG_BYTES, FOPEN: LONG_BYTES + WORD_BYTES, FREAD: WORD_BYTES + 2 * LONG_BYTES}

# ---- the block and the file's bytes, in `aes_fslib`'s script band ---------------------------------------------------------
GUARD_BYTES = 0x40                      # each side of the block: where a NUL outside it lands
GUARD_FILL = 0x5C                       # ...staged so: no byte the reader stores (0, a digit, a blank)
BLOCK_AT = aes_fslib.SCRIPT_BAND_AT + GUARD_BYTES
FILE_AT = BLOCK_AT + INF_BUFFER_BYTES + GUARD_BYTES
FILE_ROOM = INF_BUFFER_BYTES + WORD_BYTES       # a whole block's worth, and a byte more than it (never laid: refused)
assert FILE_AT + FILE_ROOM <= aes_fslib.SCRIPT_BAND_AT + aes_fslib.SCRIPT_BYTES, "the block and the file run out of the band they borrow"
BLOCK_FILL = 0xA5                       # the block before the reader: nothing it copies there or reads

MOVE_W_ABSOLUTE_TO_D1 = 0x3239          # move.w  <xxx>.l,d1
BMI_S = 0x6B                            # bmi.s   <d8>
DBF_BACK_TO_THE_MOVE = aes_fslib.DBF_BACK_TO_THE_MOVE
NOTHING_TO_LAY = 0xFFFF                 # the count cell of a read that lays nothing: `dbf`'s -1


class ReadLaid(aes_gemdosif.Recorder):
    """A RECORDER THAT LAYS THE FILE AT THE READ: behind its script three cells — where the file's bytes are staged,
    where the read's buffer is, and how many bytes less one (NOTHING_TO_LAY: none). The handler, past the answer: for
    Fread alone, that many bytes copied. Every register but D0 as found; the host twin is the same effect."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_cell = self.script.first + self.script.entries * LONG_BYTES
        self.buffer_cell = self.file_cell + LONG_BYTES
        self.count_cell = self.buffer_cell + LONG_BYTES
        self.end = self.count_cell + WORD_BYTES
        assert len(self.stub()) <= self.ledger.pointer_at - self.at, "the handler runs into its own ledger"

    def after_the_answer(self):
        if not hasattr(self, "count_cell"):         # the parent's own sizing pass, before the cells are placed
            return []
        cells = [struct.pack(">I", cell) for cell in (self.file_cell, self.buffer_cell, self.count_cell)]
        load = (vdi.pack_words(op.PUSH_A1, op.PUSH_D1) + vdi_helpers.MOVEA_L_ABSOLUTE_A0 + cells[0]
                + vdi.pack_words(op.MOVEA_L_ABSOLUTE_A1) + cells[1] + vdi.pack_words(MOVE_W_ABSOLUTE_TO_D1) + cells[2])
        copy = vdi.pack_words(op.MOVE_B_A0_TO_A1, op.DBF_D1, DBF_BACK_TO_THE_MOVE & aes.WORD_MASK)
        return [vdi.pack_words(op.CMPI_W_STACK, FREAD, vdi_helpers.FRAME_WORDS_AT), (op.BNE_S, "no read"), load,
                (BMI_S, "nothing to lay"), copy, ("label", "nothing to lay"), vdi.pack_words(op.POP_D1, op.POP_A1),
                ("label", "no read")]

    def pokes(self, answers, text=None):
        """The parent's; the file's `text` staged (None: a read lays nothing) and the three cells."""
        laid = b"" if text is None else text
        assert len(laid) <= FILE_ROOM, f"a file of {len(laid)} bytes: more than its room of {FILE_ROOM}"
        count = NOTHING_TO_LAY if not laid else len(laid) - 1
        return {**super().pokes(answers), FILE_AT: laid.ljust(FILE_ROOM, bytes([vdi.FILL])),
                self.file_cell: struct.pack(">IIH", FILE_AT, BLOCK_AT, count)}

    def twin(self, function):
        answering = super().twin(function)
        if function != FREAD:
            return answering

        def handler(buf, arguments, argument_bytes):
            answer = answering(buf, arguments, argument_bytes)
            count = case.word_in(buf, self.count_cell)
            if count != NOTHING_TO_LAY:
                source = case.long_in(buf, self.file_cell)
                isr.poke(buf, case.long_in(buf, self.buffer_cell) & BUS,
                         ctypes.string_at(ctypes.addressof(buf.contents) + source, count + 1))
            return answer
        return handler


CALLS_RECORDED = 16                     # the longest road makes 15 (the C: retry that reads): the ledger refuses a 17th
HANDLER_ROOM = 0x100
RECORDER = ReadLaid(addrs.VECTOR_TRAP_GEMDOS, aes_gemdosif.PATH_AT + aes_gemdosif.PATH_BYTES, HANDLER_ROOM, FRAME_BYTES,
                    entries=CALLS_RECORDED, parked=(aes.AES_DOS_RETURN, aes.AES_TRAP1_RETURN))
assert RECORDER.end <= aes_gemdosif.BAND_AT + aes_gemdosif.BAND_BYTES, "the reader's trap runs out of the band it borrows"
HANDLERS = {gemdos.rom_handler(function): RECORDER.twin(function) for function in FRAME_BYTES}


def scripted_hook():
    """The host twin bound as `aes.run_function`'s `hook`."""
    return gemdos.bound_handlers(HANDLERS)


# THE HOST'S DISPATCHER RESOLVES A FILE HANDLE before it calls Fread's handler (`aes_shell`, OPEN_FOR_THE_HOST): the
# handle a script's Fopen answers is staged OPEN for it — a descriptor naming a stand-in nothing reads.
HANDLE = aes_shell.SCRIPTED_HANDLE


def opened_for_the_host(handle):
    return process.descriptor_poke(handle, aes_shell.BAND_AT, gemdos.BASEPAGE)


def reader_machine(answers, text=None, *, usable=1, change_pending=0, device=2, pokes=None, handle=HANDLE):
    """THE READER'S MACHINE (the module's docstring): the leaf machine, the glue's four words stale, every `trap #1`
    answered by the script of `answers` with `text` laid at the read; the block and its guards FILLed; the three words
    the reader reads — the usable-disk word, the pending change, the device in use — as the case says; and `handle`
    open for the host's dispatcher."""
    block = {BLOCK_AT - GUARD_BYTES: bytes([GUARD_FILL]) * GUARD_BYTES + bytes([BLOCK_FILL]) * INF_BUFFER_BYTES
             + bytes([GUARD_FILL]) * GUARD_BYTES}
    words = {DISK_USABLE: struct.pack(">H", usable), RSCHANGE: struct.pack(">H", change_pending),
             RESTYPE: struct.pack(">H", device)}
    return aes.leaf_machine(onto=merge_pokes(aes_gemdosif.STALE_DOS, opened_for_the_host(handle), RECORDER.pokes(answers, text),
                                             block, words, pokes))


def run_reader(answers, text=None, **machine):
    """The reader over its machine, both shores — UNPOISONED (the handler stores back its own pointers: the scripted
    trap's rule, `aes_shell`)."""
    return aes.run_function(READ_INF, (), reader_machine(answers, text, **machine), hook=scripted_hook, poison=False)


def calls(result):
    """The run's GEMDOS calls, in order: `[(function, its frame's own bytes), ...]`."""
    return RECORDER.calls(result.final)


def parked(result):
    """`[(AES_DOS_RETURN, AES_TRAP1_RETURN), ...]` as each call found them."""
    return RECORDER.parked_at(result.final)


call = RECORDER.call
