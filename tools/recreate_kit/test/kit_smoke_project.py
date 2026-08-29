"""The miniature "project" the kit's harness-plumbing suites run a real `harness.differential()` on.

`harness` binds a project's compiled candidate `.so` at import, and this directory deliberately binds
no project — so without something like this the kit's own suite can pin the two MODELS
(`test_psg_model.py`, `test_hw_model.py` drive both implementations from C) but never the layer
between them: `_seed_candidate_psg` / `_vet_psg_state`, `_seed_candidate_hw` / `_vet_hw_state`, and
the refusals that decide whether a case was tested at all.

So this builds one, in a temp directory: a `.PRG` of hand-assembled routines — the ones the models
exist for, one per phase — and a candidate `.so` of `kit_candidate.c` plus the kit's own `src/`,
which is exactly what `kit.mk` links for a real game.

WHY IT IS A MODULE RATHER THAN PART OF A SUITE. `recreate_kit.project.load` refuses a SECOND project
in one process, and `harness` freezes module-level constants from the binding at import — so the kit
can have exactly one bound project per pytest run, however many suites want it. `bind()` is memoized,
so `test_psg_differential.py` and `test_hw_differential.py` share the one binding; whichever imports
first builds it. (That is also why the kit's own `make test` runs serially.)

`bind()` SKIPS the calling module when the shared oracle or a C compiler is absent — `oracle/build/`
is gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).
"""
import atexit
import shutil
import struct
import subprocess
import sys
import tempfile

from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
ORACLE_SO = KIT / "oracle" / "build" / "liboracle.so"
CANDIDATE_SRC = Path(__file__).with_name("kit_candidate.c")

# The miniature project's geometry. image_size must equal os.h's OS_IMAGE_SIZE (harness vets it) and
# load_base must clear the poked-input block and leave the modeled heap and file-staging regions
# above the program — the ordinary layout every real project uses.
LOAD_BASE = 0x10000
IMAGE_SIZE = 0x100000

# ---- Phase 6's routine: the read-modify-write of the YM2149 mixer ----
# In the form Wonder Boy's snd_psg_silence has it at $17f36 (TRAP_MODEL.md, Phase 6): select the
# mixer, read it back, merge the silence mask, write it back. `>H` words, big-endian.
PSG_SELECT = 0xFF8800
PSG_DATA = 0xFF8802
MIXER_REG = 7
SILENCE_MASK = 0x3F
PORT_DIR_BITS = 0xC0                  # what the case declares the chip held: port A/B direction
SILENCED = PORT_DIR_BITS | SILENCE_MASK
GIACCESS_REG = 14                     # PSG port A — the register Joust's floppy routine drives

_RMW_CODE = (struct.pack(">HHI", 0x13FC, MIXER_REG, PSG_SELECT)      # move.b #7,$ff8800.l
             + struct.pack(">HI", 0x1239, PSG_SELECT)                # move.b $ff8800.l,d1
             + struct.pack(">HH", 0x0001, SILENCE_MASK)              # ori.b #$3f,d1
             + struct.pack(">HI", 0x13C1, PSG_DATA)                  # move.b d1,$ff8802.l
             + struct.pack(">H", 0x4E75))                            # rts

# ...and a routine that reaches the SAME chip through the other door: XBIOS Giaccess(data, reg),
# pushed right to left so the shim reads data at caller+2 and reg at caller+4.
XBIOS_GIACCESS = 0x1C
_GIACCESS_CODE = (struct.pack(">HH", 0x3F3C, GIACCESS_REG)           # move.w #14,-(sp)   (reg)
                  + struct.pack(">HH", 0x3F3C, 0)                    # move.w #0,-(sp)    (data)
                  + struct.pack(">HH", 0x3F3C, XBIOS_GIACCESS)       # move.w #$1c,-(sp)  (fn)
                  + struct.pack(">H", 0x4E4E)                        # trap #14
                  + struct.pack(">HH", 0x4FEF, 6)                    # lea 6(sp),sp
                  + struct.pack(">H", 0x4E75))                       # rts

# ---- Phase 7's routine: the tempo selector's two hardware reads ----
# Wonder Boy's snd_music_tick opens with `btst.b #7,$fffa01` / `btst.b #1,$ff820a` and picks the
# music tempo from them ($17c7e and $17c90; PORTABILITY.md, "the BuggyBoy defect"). These are the
# same two reads with the branch left out, so the routine's whole effect is off-image — which is
# precisely why a fabricated 0 is invisible to a byte diff.
MFP_GPIP = 0xFFFA01
SHIFTER_SYNC = 0xFF820A
COLOUR_MONITOR_GPIP = 0xB0            # bit 7 = colour, bits 5/4 = FDC/ACIA idle (active low)
SYNC_50HZ = 0x02                      # bit 1 = 50 Hz

_HW_READ_CODE = (struct.pack(">HI", 0x1239, MFP_GPIP)                # move.b $fffa01.l,d1
                 + struct.pack(">HI", 0x1439, SHIFTER_SYNC)          # move.b $ff820a.l,d2
                 + struct.pack(">H", 0x4E75))                        # rts

# ...and one that reads only the sync byte, for the case about declaring one address and reading
# the other.
_SYNC_ONLY_CODE = (struct.pack(">HI", 0x1239, SHIFTER_SYNC)          # move.b $ff820a.l,d1
                   + struct.pack(">H", 0x4E75))                      # rts

# ...and one that WRITES the sync byte and then reads it back, which is the shape a whole-frame run
# of Wonder Boy has ($f91c writes it, $17c90 reads it) and which no declaration can describe.
_WRITE_THEN_READ_CODE = (struct.pack(">HHI", 0x13FC, SYNC_50HZ, SHIFTER_SYNC)  # move.b #2,$ff820a.l
                         + struct.pack(">HI", 0x1239, SHIFTER_SYNC)            # move.b $ff820a.l,d1
                         + struct.pack(">H", 0x4E75))                          # rts

# ...and one that reads the sync byte a WORD at a time, taking in the shifter register beside it.
# The address is EVEN: a word read at the odd $fffa01 would be an address error on a real 68000, and
# only executes here because the kit builds Musashi with M68K_EMULATE_ADDRESS_ERROR off — a case
# built on an impossible input stops measuring what it names the day that changes.
_WIDE_READ_CODE = (struct.pack(">HI", 0x3239, SHIFTER_SYNC)          # move.w $ff820a.l,d1
                   + struct.pack(">H", 0x4E75))                      # rts

# ...and the pair the VOLATILE flag exists for. The shifter's video-address counter advances every
# few scanlines, so one declaration describes exactly one read of it: a routine that reads
# $ff8209 TWICE is served the same byte twice, which the counter cannot have held.
SHIFTER_VCOUNT_LOW = 0xFF8209

_VOLATILE_TWICE_CODE = (struct.pack(">HI", 0x1239, SHIFTER_VCOUNT_LOW)   # move.b $ff8209.l,d1
                        + struct.pack(">HI", 0x1439, SHIFTER_VCOUNT_LOW)  # move.b $ff8209.l,d2
                        + struct.pack(">H", 0x4E75))                      # rts

# ...and its control, which is what says the refusal is about VOLATILITY and not about repetition:
# the same shape on a STATIC address is a correct run, because the machine answers a static byte the
# same way every time and one declaration describes both reads.
_STATIC_TWICE_CODE = (struct.pack(">HI", 0x1239, MFP_GPIP)           # move.b $fffa01.l,d1
                      + struct.pack(">HI", 0x1439, MFP_GPIP)         # move.b $fffa01.l,d2
                      + struct.pack(">H", 0x4E75))                   # rts

# ---- Phase 10's routines: stores to memory-mapped I/O registers ----
# Three stores of three different WIDTHS to three different registers, which is what the write
# ledger compares — a shape every game in this workspace has (a shifter colour word, a palette
# longword, an ACIA command byte) and which no memory diff can see, because the oracle drops all
# three.
SHIFTER_PEN0 = 0xFF8240
SHIFTER_PEN1 = 0xFF8244
ACIA_DATA = 0xFFFC02
ACIA_STATUS = 0xFFFC00
ACIA_TX_RDY = 0x02                    # bit 1 of the status byte: the transmit register is empty
PEN0_COLOUR = 0x0777                  # white, as the shifter's three 3-bit fields
PEN_PAIR_COLOURS = 0x01230456         # a longword over pens 2 and 3, distinct in all four bytes
IKBD_COMMAND = 0x16                   # "interrogate the joysticks", the byte three games send

_HW_WRITE_CODE = (struct.pack(">HHI", 0x33FC, PEN0_COLOUR, SHIFTER_PEN0)     # move.w #$777,$ff8240
                  + struct.pack(">HII", 0x23FC, PEN_PAIR_COLOURS, SHIFTER_PEN1)  # move.l #..,$ff8244
                  + struct.pack(">HHI", 0x13FC, IKBD_COMMAND, ACIA_DATA)     # move.b #$16,$fffc02
                  + struct.pack(">H", 0x4E75))                               # rts

# ...and the IKBD send loop itself, `ikbd_send_cmd`'s four instructions: it is the routine the ACIA
# status slot's MODEL DEFAULT exists for, and it terminates only because that default has TDRE set.
_ACIA_SEND_CODE = (struct.pack(">HHI", 0x0839, 1, ACIA_STATUS)               # btst #1,$fffc00.l
                   + struct.pack(">BB", 0x67, 0xF6)                          # beq.s back to the btst
                   + struct.pack(">HHI", 0x13FC, IKBD_COMMAND, ACIA_DATA)    # move.b #$16,$fffc02
                   + struct.pack(">H", 0x4E75))                              # rts

# ...and the OTHER end of the same device: an ACIA INTERRUPT HANDLER's entry shape, which reads the
# status byte and then POPS the data port once. This is the read the ACIA data slot exists for, and
# one per-run constant describes it exactly because there is one read of it.
_ACIA_RECEIVE_CODE = (struct.pack(">HI", 0x1039, ACIA_STATUS)                # move.b $fffc00.l,d0
                      + struct.pack(">HI", 0x1239, ACIA_DATA)                # move.b $fffc02.l,d1
                      + struct.pack(">H", 0x4E75))                           # rts

# ...and the shape one constant CANNOT describe, which is why the data port is VOLATILE: two reads
# of it in one run pop two different bytes off the keyboard controller, and a single declaration
# would serve the first one twice.
_ACIA_RECEIVE_TWICE_CODE = (struct.pack(">HI", 0x1239, ACIA_DATA)            # move.b $fffc02.l,d1
                            + struct.pack(">HI", 0x1439, ACIA_DATA)          # move.b $fffc02.l,d2
                            + struct.pack(">H", 0x4E75))                     # rts

# ...and the composite the SPLIT-REGISTER exemption exists for: send a command and then service
# the reply, both through `$fffc02`. Every other modeled address would be stale after that write;
# this one is not, because the write went to the transmit register and the read pops the receive one.
_ACIA_SEND_THEN_RECEIVE_CODE = (struct.pack(">HHI", 0x13FC, IKBD_COMMAND, ACIA_DATA)  # move.b #,..
                                + struct.pack(">HI", 0x1239, ACIA_DATA)   # move.b $fffc02.l,d1
                                + struct.pack(">H", 0x4E75))              # rts

# ...and Phase 10's READ-MODIFY-WRITE trio, the shape `hw_bset8`/`hw_bclr8`/`hw_and8` exist for.
# All three are Zynaps's own instructions (`_start` @ 0x1068e and 0x10056, `mfp_ack_timer_b` @
# 0x1076c), and all three read a register the seeded READ model does not name — so the oracle serves
# a fabricated 0 for the read half and stores what that 0 produces. That is the byte the candidate
# side must ledger, and the reason a reconstruction may not spell these as a plain store: on the
# machine the read half is the byte the chip really holds.
MFP_IERB = 0xFFFA09                   # interrupt enable B; bit 6 is the keyboard ACIA
MFP_ISRA = 0xFFFA0F                   # ...and in-service A, whose bit 0 is Timer B
SHIFTER_MODE = 0xFF8260               # the resolution byte
MFP_ACIA_CHANNEL_BIT = 6
MFP_ISRA_TIMER_B_BIT = 0
SHIFTER_MODE_RESOLUTION_MASK = 0xFC   # `andi.b #$fc` — clears the two resolution bits

_HW_RMW_CODE = (struct.pack(">HHI", 0x08F9, MFP_ACIA_CHANNEL_BIT, MFP_IERB)    # bset #6,$fffa09.l
                + struct.pack(">HHI", 0x08B9, MFP_ISRA_TIMER_B_BIT, MFP_ISRA)  # bclr #0,$fffa0f.l
                + struct.pack(">HHI", 0x0239, SHIFTER_MODE_RESOLUTION_MASK, SHIFTER_MODE)
                + struct.pack(">H", 0x4E75))                                   # rts

_ROUTINES = (_RMW_CODE, _GIACCESS_CODE, _HW_READ_CODE, _SYNC_ONLY_CODE, _WRITE_THEN_READ_CODE,
             _WIDE_READ_CODE, _VOLATILE_TWICE_CODE, _STATIC_TWICE_CODE,
             _HW_WRITE_CODE, _ACIA_SEND_CODE, _ACIA_RECEIVE_CODE, _ACIA_RECEIVE_TWICE_CODE,
             _ACIA_SEND_THEN_RECEIVE_CODE, _HW_RMW_CODE)


def _entries():
    """Each routine's load address, in the order they are concatenated into the .PRG's text."""
    addresses, pc = [], LOAD_BASE
    for code in _ROUTINES:
        addresses.append(pc)
        pc += len(code)
    return addresses


(RMW_ENTRY, GIACCESS_ENTRY, HW_READ_ENTRY, SYNC_ONLY_ENTRY, WRITE_THEN_READ_ENTRY,
 WIDE_READ_ENTRY, VOLATILE_TWICE_ENTRY, STATIC_TWICE_ENTRY,
 HW_WRITE_ENTRY, ACIA_SEND_ENTRY, ACIA_RECEIVE_ENTRY, ACIA_RECEIVE_TWICE_ENTRY,
 ACIA_SEND_THEN_RECEIVE_ENTRY, HW_RMW_ENTRY) = _entries()

PRG_MAGIC = 0x601A


def _build_prg(text):
    """A minimal GEMDOS .PRG carrying `text` and nothing else — no data, no bss, no relocations.

    The relocation table is one zero longword, which `prg_dis.parse_reloc` reads as "no fixups": the
    routines above are position-independent (absolute hardware addresses only), so there is nothing
    to relocate and the loader places the text verbatim at load_base.
    """
    header = struct.pack(">HIIIIIIH", PRG_MAGIC, len(text), 0, 0, 0, 0, 0, 0)
    return header + text + struct.pack(">I", 0)


def _write_project(root):
    """Lay out the miniature project: its .PRG, an empty name map, and a project.toml."""
    (root / "smoke.prg").write_bytes(_build_prg(b"".join(_ROUTINES)))
    (root / "names.txt").write_text("")     # harness reads it for diff labels; nothing to name
    (root / "project.toml").write_text(
        'name = "kit_smoke"\n'
        'prg = "smoke.prg"\n'
        'names = "names.txt"\n'
        'lib = "libkitsmoke.so"\n'
        f"load_base = {LOAD_BASE}\n"
        f"image_size = {IMAGE_SIZE}\n")


def _build_candidate(root):
    """Compile kit_candidate.c + the kit's own src/ into the project's candidate .so.

    Exactly what kit.mk builds for a real project (its SRC sweeps `$(KIT)/src/*.c`), so the ABI this
    exercises is the ABI a game gets — including the refusal tally and the Dosound ledger the harness
    requires or probes at import.
    """
    sources = sorted((KIT / "src").glob("*.c")) + [CANDIDATE_SRC]
    subprocess.run(
        ["cc", "-std=c11", "-O0", "-fPIC", "-shared", f"-I{KIT / 'include'}",
         *[str(src) for src in sources], "-o", str(root / "libkitsmoke.so")],
        check=True, capture_output=True, text=True)


_harness = None


def bind():
    """Build and bind the miniature project once per process; return the bound `harness` module.

    Memoized because `project.load` freezes the binding for the whole process and `harness` derives
    module-level constants from it at import — so the second suite to ask gets the first one's
    binding rather than a refusal. Call it at MODULE scope in the suite that needs it, so a missing
    oracle or compiler skips that module rather than erroring inside a test.
    """
    global _harness
    if _harness is not None:
        return _harness

    if not ORACLE_SO.exists():
        pytest.skip(f"{ORACLE_SO} is not built (gitignored) — "
                    f"run `make -C tools/recreate_kit oracle`", allow_module_level=True)
    if shutil.which("cc") is None:
        pytest.skip("no C compiler, so the miniature candidate cannot be built",
                    allow_module_level=True)
    root = Path(tempfile.mkdtemp(prefix="kit_smoke_"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    _write_project(root)
    try:
        _build_candidate(root)
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"the miniature candidate did not compile: {exc.stderr}",
                    allow_module_level=True)

    sys.path.insert(0, str(KIT.parent))          # reverse/tools, so `recreate_kit` imports
    from recreate_kit import project             # noqa: E402
    project.load(root)
    # `recreate_kit.harness`, not a bare `import harness`: the kit's own module uses relative
    # imports, and each project's test/harness.py is the thin shim that re-exports it after binding
    # (projects/<game>/recreate/test/harness.py). This module IS that shim, for one throwaway
    # project — so it imports the package module directly rather than growing a second copy.
    from recreate_kit import harness as kit_harness   # noqa: E402  (importable only once bound)
    _harness = kit_harness
    return _harness
