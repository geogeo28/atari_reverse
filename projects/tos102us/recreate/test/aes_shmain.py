r"""THE SHELL'S LOOP — what sh_main `$feb0e6` and sh_cmd `$feb2fc` (`src/aes/shell.c`) are proved over: THE DESK DOOR
answered on both shores, a recording GEMDOS wide enough for a whole pass, and the desk's requests as the ROM's own
shel_write leaves them.

THE DESK DOOR (`include/aes/deskdoor.h`). Five routines the shell calls are band 6's — deskmain and the desk's four
built-ins — and no case runs one: a whole desktop session is no argument of a shell pass, and a Format writes a disk.
So each is ANSWERED AT ITS ENTRY, a LABELLED ARGUMENT CLASS wherever it is used (ruling W4-R6's kind):

  * THE ROM'S SHORE reaches them by Line-F, through the handler's RAM copy (`$2c`), whose one operand names the call
    table (`movea.l #$fee900,a0`). A case stages A COPY OF THE ROM'S TABLE in this module's band — every entry the
    ROM's own but the five, which name five RECORDING STUBS beside it — and that operand at the copy. Every other
    Line-F call of the run goes where the ROM's goes. Staged RAM, never a byte of the ROM.
  * OUR SHORE leaves through `recreate_call_desk_door`, keyed by the routine's ROM address: the stub's host twin.

A STUB RECORDS AND ANSWERS, as the recording traps do: its routine's address and the longwords of the frame it was
handed into a LEDGER — with what three words of the shell's hold AT THE CALL, which no run's end shows (the multi-click
count, sh_dodef, gl_shgem) — then D0 the next answer of a SCRIPT, and the WORDS THAT ANSWER LAYS: what the desk's
own shel_write stores before deskmain returns (`asked`: read off the ROM's own run of it, never typed), without which
no pass after the first is the desk's to ask for.

GEMDOS IS THE RECORDING, SCRIPTED TRAP (`aes_gemdosif.Recorder`), an instance of its own: a pass with a launch makes
the desk's Mallocs and Mfrees, sh_find's Fsetdta and Fsfirst, and dos_exec's Pexec — more calls, and other frames,
than either battery's recorder holds.

NOTHING HERE POISONS: the stubs store back the ledger's and the script's pointers (`aes_shell`'s reason).
"""
import ctypes
import functools
import os
import struct
import sys
from collections import namedtuple

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_gemdosif as gd
import aes_objdraw as od
import aes_shell as shell
import case
import gemdos
import isr
import staging
import test_aes_shell_buf as shell_buf
import vdi
from address_hook import AddressHook, bind_pointer
from case import merge_pokes
from opcodes import MOVEQ_0_D0, RTE, RTS
from vdi_helpers import MOVEA_L_ABSOLUTE_A0, STORE_A0_ABSOLUTE

WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
LONG_MASK = aes.LONG_MASK

# ---- the routines ----------------------------------------------------------------------------------------------------------
SH_MAIN, SH_CMD = "AES_ROM_SH_MAIN", "AES_ROM_SH_CMD"
aes.declare_alcyon(SH_MAIN, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(SH_CMD, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
SHELL = aes.header_constants("shell.h")
DOOR = aes.header_constants("deskdoor.h")
DESKMAIN, SHOW_FILE, PRINT_FILE, FORMAT, COPY_DISK = (
    addrs.AES_ROM_DESKMAIN, addrs.AES_ROM_DESK_SHOW_FILE, addrs.AES_ROM_DESK_PRINT_FILE, addrs.AES_ROM_DESK_FORMAT,
    addrs.AES_ROM_DESK_COPY_DISK)
# Each door routine with the longwords of the frame it is handed (`aes/deskdoor.h`'s three shapes).
FRAME_LONGS = {DESKMAIN: 0, SHOW_FILE: 1, PRINT_FILE: 1, FORMAT: 2, COPY_DISK: 2}
NO_ARGUMENT = 0xFFFF_FFFF                # `staged_call.h`'s STAGED_CALL_NO_ARGUMENT: what a frame without one records
TAIL, TAIL_TEXT = aes.AES_SH_COMMAND, SHELL["AES_SH_TAIL_TEXT"]
ISDEF_SEEN, CART_LAUNCH = SHELL["AES_SH_ISDEF_SEEN"], SHELL["AES_SH_CART_LAUNCH"]
BPEND = aes.header_constants("evasync.h")["AES_GL_BPEND"]
FLAGS = (aes.AES_SH_DOEXEC, aes.AES_SH_ISGEM, aes.AES_SH_DODEF, aes.AES_SH_ISDEF)      # what shel_write stores
for _at, _why in ((ISDEF_SEEN, "sh_main's own word of sh_isdef"), (CART_LAUNCH, "the desk's request for a cartridge's program"),
                  (BPEND, "gl_bpend, which sh_main clears"), (aes.AES_GL_SHGEM, "gl_shgem"),
                  *((flag, "a request of shel_write's") for flag in FLAGS)):
    aes.declare_case_field(_at, WORD_BYTES, _why)
aes.declare_case_field(TAIL, aes.AES_SHELL_LINE_BYTES, "the shell's command tail")
aes.declare_case_field(aes.AES_AD_PFILE, LONG_BYTES, "ad_pfile, which sh_main notes")

# ---- this module's band: the staged call table, the stubs, the door's two tables, the recorder --------------------------------
BAND_AT, BAND_BYTES = 0xE2000, 0x1400
staging.HIGH_BANDS.claim(BAND_AT, BAND_BYTES, "test/aes_shmain.py: the Line-F table's staged copy, the desk door's stubs, a recorder")
LINEF_TABLE = aes.AES_LINEF_TABLE
LINEF_TABLE_BYTES = aes.AES_LINEF_TABLE_ENTRIES * LONG_BYTES
TABLE_AT = BAND_AT
STUBS_AT = TABLE_AT + LINEF_TABLE_BYTES + (-LINEF_TABLE_BYTES % LONG_BYTES)
STUB_ROOM = 0x50                         # a stub's bytes, the longest (a disk routine's)
# WHAT A CALL IS RECORDED WITH BEHIND ITS FRAME: three words as they stand when the routine is entered.
WATCHED = (BPEND, aes.AES_SH_DODEF, aes.AES_GL_SHGEM)
ENTRY_BYTES = 3 * LONG_BYTES + len(WATCHED) * WORD_BYTES
LEDGER_ENTRIES = 6
LEDGER = shell.Table(STUBS_AT + len(FRAME_LONGS) * STUB_ROOM, LEDGER_ENTRIES, ENTRY_BYTES, "desk door's ledger")
# The script: a pointer, then per call the answer and the words it lays — `(address.l, value.w)` each, a NULL
# address the last.
SCRIPT_AT = LEDGER.first + LEDGER_ENTRIES * ENTRY_BYTES
SCRIPT_BYTES = 0x100
SCRIPT_FIRST = SCRIPT_AT + LONG_BYTES
GETREZ_STUB_AT = SCRIPT_AT + SCRIPT_BYTES
GETREZ_STUB_BYTES = 4

# The handler's RAM copy, and its operand that names the table: `movea.l #$fee900,a0` (`aes/aes.h`).
HANDLER_COPY = case.long_in(BASE_IMAGE, addrs.VECTOR_LINE_F)
TABLE_OPERAND_AT = HANDLER_COPY + aes.LINEF_TABLE_OPERAND
assert case.long_in(BASE_IMAGE, TABLE_OPERAND_AT) == LINEF_TABLE, (
    "the Line-F handler's copy does not name the ROM's table where the header says: no door can be staged")
aes.declare_case_field(TABLE_OPERAND_AT, LONG_BYTES, "the Line-F handler's table operand, staged at the copy")

MOVE_L_IMMEDIATE_A0_POSTINC = b"\x20\xfc"          # move.l  #<xxx>,(a0)+
MOVE_L_STACK_A0_POSTINC = b"\x20\xef"              # move.l  d16(sp),(a0)+
MOVE_W_ABSOLUTE_A0_POSTINC = b"\x30\xf9"           # move.w  <xxx>.l,(a0)+
ANSWER_AND_LAY = bytes.fromhex("2018"              # move.l  (a0)+,d0
                               "2218"              # move.l  (a0)+,d1         the next word's address
                               "6706"              # beq.s   past the loop
                               "2241"              # movea.l d1,a1
                               "3298"              # move.w  (a0)+,(a1)
                               "60f6")             # bra.s   to the address read


def _slot(routine):
    """Where `routine`'s call word reads its longword in the table: its ONE entry."""
    table = bytes(BASE_IMAGE[LINEF_TABLE:LINEF_TABLE + LINEF_TABLE_BYTES])
    slots = [at for at in range(0, len(table), LONG_BYTES) if table[at:at + LONG_BYTES] == struct.pack(">I", routine)]
    assert len(slots) == 1, f"the Line-F table names {routine:#x} {len(slots)} times: its door cannot be staged by one entry"
    return slots[0]


def stub_at(routine):
    return STUBS_AT + list(FRAME_LONGS).index(routine) * STUB_ROOM


def stub(routine):
    """`routine`'s recording stub: its address, its frame's longwords (or NO_ARGUMENT) and the watched words into the
    ledger; D0 the script's answer; the answer's words laid; `rts`. A0, A1, D0, D1 are an Alcyon routine's to change."""
    frame = b"".join(MOVE_L_STACK_A0_POSTINC + struct.pack(">H", LONG_BYTES * (1 + nth)) if nth < FRAME_LONGS[routine]
                     else MOVE_L_IMMEDIATE_A0_POSTINC + struct.pack(">I", NO_ARGUMENT) for nth in range(2))
    code = (MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", LEDGER.pointer_at)
            + MOVE_L_IMMEDIATE_A0_POSTINC + struct.pack(">I", routine) + frame
            + b"".join(MOVE_W_ABSOLUTE_A0_POSTINC + struct.pack(">I", at) for at in WATCHED)
            + STORE_A0_ABSOLUTE + struct.pack(">I", LEDGER.pointer_at)
            + MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", SCRIPT_AT) + ANSWER_AND_LAY
            + STORE_A0_ABSOLUTE + struct.pack(">I", SCRIPT_AT) + RTS)
    assert len(code) <= STUB_ROOM
    return code


def _script(answers):
    """The script's bytes for `answers`: each an answer, or `(answer, {address: word, ...})` with what it lays."""
    raw = b""
    for answer in answers:
        value, laid = answer if isinstance(answer, tuple) else (answer, {})
        assert all(laid), "a laid word at address 0 would end the list"
        raw += struct.pack(">I", value & LONG_MASK) + b"".join(struct.pack(">IH", at, word & 0xFFFF) for at, word in laid.items())
        raw += bytes(LONG_BYTES)
    assert len(raw) <= SCRIPT_BYTES - LONG_BYTES, "the script is longer than its room"
    return raw


@functools.cache
def _staged_table():
    table = bytearray(BASE_IMAGE[LINEF_TABLE:LINEF_TABLE + LINEF_TABLE_BYTES])
    for routine in FRAME_LONGS:
        table[_slot(routine):_slot(routine) + LONG_BYTES] = struct.pack(">I", stub_at(routine))
    return bytes(table)


def door_pokes(answers=()):
    """THE DOOR STAGED: the table's copy, the handler's operand at it, the five stubs, an empty ledger and the script
    of `answers` (one per call the run makes through the door, in order)."""
    script = _script(answers)
    return {TABLE_AT: _staged_table(), TABLE_OPERAND_AT: struct.pack(">I", TABLE_AT),
            **{stub_at(routine): stub(routine) for routine in FRAME_LONGS}, **LEDGER.staged(),
            SCRIPT_AT: struct.pack(">I", SCRIPT_FIRST) + script.ljust(SCRIPT_BYTES - LONG_BYTES, bytes([vdi.FILL]))}


# ---- the host twin ----------------------------------------------------------------------------------------------------------
DOOR_SYMBOL = "recreate_call_desk_door"
CALL_DESK_DOOR = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_uint32)
_HOOK = AddressHook(DOOR_SYMBOL, CALL_DESK_DOOR)


def _served(routine):
    """`routine`'s stub as the candidate's image sees it: the same ledger entry, the same answer, the same words laid —
    both pointers bounded before anything is stored through them."""
    def effect(buf, first, second):
        entry = LEDGER.next(buf)
        watched = b"".join(bytes(buf[at:at + WORD_BYTES]) for at in WATCHED)
        isr.poke(buf, entry, struct.pack(">3I", routine, first, second) + watched)
        LEDGER.step(buf, entry)
        at = case.long_in(buf, SCRIPT_AT)
        assert SCRIPT_FIRST <= at < SCRIPT_AT + SCRIPT_BYTES - LONG_BYTES, f"the script's pointer {at:#x} is outside it"
        answer, at = case.long_in(buf, at), at + LONG_BYTES
        while (address := case.long_in(buf, at)):
            isr.poke(buf, address, bytes(buf[at + LONG_BYTES:at + LONG_BYTES + WORD_BYTES]))
            at += LONG_BYTES + WORD_BYTES
            assert at < SCRIPT_AT + SCRIPT_BYTES, "the script's laid words run past it"
        isr.poke(buf, SCRIPT_AT, struct.pack(">I", at + LONG_BYTES))
        return answer
    return effect


EFFECTS = {routine: _served(routine) for routine in FRAME_LONGS}


def door_hook():
    """The door's host twin bound for one case, as `aes.run_function`'s `hook` (or one of `aes.doors`')."""
    return _HOOK.staged(EFFECTS, lambda refused: f"the candidate called {refused[0]:#x} through the desk door, which is "
                                                 f"none of its five routines")


Call = namedtuple("Call", "routine first second bpend dodef shgem")


def calls(image):
    """The door's ledger in `image`: a `Call` per call made, in order — the routine, its frame's longwords
    (NO_ARGUMENT where the frame has none) and the three watched words as the call found them."""
    made = []
    for routine_high, rest in LEDGER.recorded(image):
        raw = struct.pack(">H", routine_high) + rest
        made.append(Call(*struct.unpack(f">3I{len(WATCHED)}H", raw)))
    return made


# ---- GEMDOS: a recorder of this module's own -----------------------------------------------------------------------------------
MALLOC, MFREE, PEXEC = gd.MALLOC, gd.MFREE, gd.PEXEC
FSETDTA, FSFIRST = addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_FSFIRST_FN
GEMDOS_ENTRIES = 48                       # two desk passes (thirteen calls each) and a search's whole walk between them
GEMDOS = gd.Recorder(addrs.VECTOR_TRAP_GEMDOS, GETREZ_STUB_AT + GETREZ_STUB_BYTES, 0x140, {
    MALLOC: LONG_BYTES, MFREE: LONG_BYTES, FSETDTA: LONG_BYTES, FSFIRST: LONG_BYTES + WORD_BYTES,
    PEXEC: gd.PEXEC_FRAME_BYTES}, entries=GEMDOS_ENTRIES)
assert GEMDOS.end <= BAND_AT + BAND_BYTES, f"the band ends at {BAND_AT + BAND_BYTES:#x}, the recorder at {GEMDOS.end:#x}"
GEMDOS_HANDLERS = {gemdos.rom_handler(function): GEMDOS.twin(function) for function in GEMDOS.frame_bytes}
# The longword of a Pexec's frame that names its command tail may hold a site of the glue's own text on no shore
# here (dos_exec is handed the shell's tail) — nothing of this ledger is declared a text site.


def gemdos_hook():
    return gemdos.bound_handlers(GEMDOS_HANDLERS)


def gemdos_calls(image):
    return GEMDOS.calls(image)


# ---- GETREZ, where a run SWITCHES ------------------------------------------------------------------------------------------------
# sh_main asks the XBIOS for the screen's mode after every desk pass (trp14, `$feb1ea`), and a desk pass leaves by the
# dispatcher (desk_free's yield): its runs are the scheduler's (`aes_switching`), which declares no I/O byte — and
# Getrez READS ONE, the shifter's ($ff8260). So in such a run THE XBIOS IS ANSWERED BY A STAGED TRAP on the ROM's
# shore — `moveq #<mode>,d0 / rte` behind vector $b8 — and by Getrez's own C core over the same byte DECLARED on ours
# (`getrez_in_a_child`): a LABELLED ARGUMENT CLASS. The door and the XBIOS's Getrez are each held against the
# machine's own in `test_aes_trp14.py` / `test_xbios_getrez.py`.
MODES = {"low": 0, "medium": 1, "high": 2}


def getrez_pokes(mode):
    """The XBIOS's trap answered `mode`: the vector at a two-instruction handler in this module's band."""
    return {addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", GETREZ_STUB_AT),
            GETREZ_STUB_AT: struct.pack(">H", MOVEQ_0_D0 | mode) + RTE}


def getrez_in_a_child(mode):
    """IN A CHILD, before its run: the shifter's byte declared `mode` for the candidate's own Getrez — the arming every
    fork's run makes (`aes_event.one_run_of`), with the one seed. The child's alone: it dies with it."""
    import aes_event
    aes_event.arm_candidate = functools.partial(aes_event.arm_candidate, io_seed={addrs.SHIFTER_RESOLUTION: mode})


def sh_show_in_a_child(lib):
    """IN A CHILD, before its door is bound: sh_find's routine as sh_main hands it — the ROM's sh_show by its address,
    through the register-carrying hook — SERVED BY THE CHILD'S OWN sh_show over the path in the hook's A0 slot
    (`test_aes_shlib.py` holds that pairing against the ROM's sh_find). The child's binding serves the routines a
    tree walk is handed (`aes.walked_routine_effects`, where it is bound with `objects`) and ends on any other: so
    the one routine is added to those, for this child alone."""
    walked = aes.walked_routine_effects
    core = lib.aes_sh_show
    core.argtypes, core.restype = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32], None

    def shown(buf, registers):
        core(buf, registers[isr.REGISTER["a0"]])
    aes.walked_routine_effects = lambda *names, **named: {**walked(*names, **named), addrs.AES_ROM_SH_SHOW: shown}


def child_doors(mode):
    """The source a switching row's fork runs first: both doors bound, sh_find's routine served, the shifter's byte
    declared."""
    return f"{CHILD_DOORS}aes_shmain.sh_show_in_a_child(lib); aes_shmain.getrez_in_a_child({mode}); "


# ---- both doors in a CHILD (`aes_event.declare_child_doors`' kind: source a row's fork runs first) ------------------------------
CHILD_REFUSED = 7                        # the child's exit status where a door refuses (`aes_gemdosif`'s)
_CHILD_TRAMPOLINES = []
CHILD_DOORS = "import aes_shmain; aes_shmain.bind_in_a_child(lib); "


def _ending_the_child(serve):
    """`serve`, whose refusal — a callback cannot raise into C — ends the child by name."""
    def served(*arguments):
        try:
            return serve(*arguments)
        except Exception as refused:
            print(refused, file=sys.stderr, flush=True)
            os._exit(CHILD_REFUSED)
    return served


def bind_in_a_child(lib):
    """The scripted GEMDOS of this module and the desk door, bound into `lib` — the candidate the child loaded."""
    def gemdos_handler(buf, handler, arguments, argument_bytes):
        assert handler in GEMDOS_HANDLERS, f"the candidate called GEMDOS handler {handler:#x}, which the script does not serve"
        return GEMDOS_HANDLERS[handler](buf, arguments, argument_bytes)

    def door(buf, routine, first, second):
        assert routine in EFFECTS, f"the candidate called {routine:#x} through the desk door: none of its five routines"
        return EFFECTS[routine](buf, first, second)
    for symbol, prototype, serve in ((gd.GEMDOS_HANDLER_HOOK, gemdos.CALL_HANDLER, gemdos_handler),
                                     (DOOR_SYMBOL, CALL_DESK_DOOR, door)):
        trampoline = prototype(_ending_the_child(serve))
        _CHILD_TRAMPOLINES.append(trampoline)
        bind_pointer(symbol, trampoline, lib)


# ---- THE DESK'S REQUESTS, as the ROM's own shel_write leaves them -----------------------------------------------------------------
def tail(command_byte, text=b""):
    """A command tail: its first byte — a program's tail's length, or one of sh_cmd's four — then its text."""
    return bytes([command_byte]) + text + b"\0"


@functools.cache
def asked(command=od.TWO_COMMANDS[0], tail_=b"\0", gem=1, over=None):
    """THE MACHINE AFTER THE ROM'S OWN shel_write(1, gem, 0, command, tail) over `over` (the desk's machine by
    default: `test_aes_shlib.launching`'s, with a tail of the case's): the two lines in the shell's buffers, sh_doexec
    and sh_isgem as asked, sh_dodef and sh_isdef cleared."""
    import test_aes_ob_draw as ob_draw
    base = merge_pokes(ob_draw.machine(), ob_draw.STALE_SLOTS) if over is None else dict(over)
    pokes = merge_pokes(base, od.string_pokes(command, at=shell_buf.BUFFER, room=aes.AES_SHELL_LINE_BYTES),
                        {shell_buf.SECOND: tail_.ljust(aes.AES_SHELL_LINE_BYTES, b"\0")})
    staged, final, writes = od.rom_run(shell_buf.SH_WRITE, (1, gem, 0, shell_buf.BUFFER, shell_buf.SECOND), pokes)
    return case.continued_from(staged, final, writes)


def asked_words(gem=1):
    """`{address: word}`: the four flags as the ROM's shel_write(1, gem, ...) leaves them — what a deskmain that asks
    for a launch lays before it returns."""
    image = make_image(asked(gem=gem))
    return {flag: case.word_in(image, flag) for flag in FLAGS}
