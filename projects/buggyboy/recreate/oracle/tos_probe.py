"""Real-TOS oracle: cross-check the deterministic trap model (shim.c + os.h) against a genuine
TOS ROM running under Hatari, headless.

We can't diff addresses against real TOS — the shim returns *fixed* results (Malloc -> a set
base, Physbase -> a set screen) on purpose, so the differential harness stays deterministic. So
this validates two kinds of claim:

  * exact-value calls  — Getrez (low-res == 0) and Fopen/Fread (byte-exact file data + the
    cursor/EOF byte counts). The shim must match TOS here to the byte.
  * semantic invariants — Malloc rounds an odd request up to an even size and hands back
    non-overlapping, even-aligned blocks. The shim honors the same invariant; only the concrete
    base is (deliberately) different.

Mechanism: hand-assemble a tiny GEMDOS program that runs the calls, writes a fixed-layout record
to C:\\OUT.BIN, and Pterm0s. Auto-run it on a headless Hatari GEMDOS drive (SDL dummy video), then
read the record back from the host directory — no debugger/breakpoint/load-address needed.

If Hatari or a TOS ROM isn't installed, available() is False and the cross-check test skips.
"""
import glob
import os
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path

# ---- what the probe exercises (single source of truth, shared with the expectation) ----
MALLOC_A = 0x101          # odd -> the block must round up to 0x102
MALLOC_B = 0x10
PROBE_INPUT = bytes(range(16))  # the file the program Freads; small + distinctive
INPUT_LEN = len(PROBE_INPUT)
READ_SIZES = (5, 5, 100, 100)   # sequential Fread requests over PROBE_INPUT (the last two hit EOF)
LOW_RES = 0               # Getrez result for low resolution

# ---- OUT.BIN record layout (big-endian), built by the program, parsed by capture() ----
_R_PTR1, _R_PTR2, _R_REZ, _R_COUNTS, _R_DATA = 0x00, 0x04, 0x08, 0x0a, 0x12
_REC_LEN = _R_DATA + 16   # 0x22: ptr1 u32 | ptr2 u32 | rez u16 | 4x count u16 | 16 data bytes

# GEMDOS / XBIOS selectors used by the program.
_MALLOC, _FOPEN, _FREAD, _FCLOSE, _FCREATE, _FWRITE, _PTERM0 = 0x48, 0x3d, 0x3f, 0x3e, 0x3c, 0x40, 0x00
_GETREZ = 0x04            # XBIOS trap #14


class _Asm:
    """Minimal big-endian 68k emitter tracking the current offset for PC-relative refs."""
    def __init__(self):
        self.b = bytearray()

    @property
    def off(self):
        return len(self.b)

    def _w(self, v):
        self.b += struct.pack(">H", v & 0xffff)

    def _l(self, v):
        self.b += struct.pack(">I", v & 0xffffffff)

    # immediates / stack
    def push_w(self, v):   self._w(0x3f3c); self._w(v)              # move.w #v,-(sp)
    def push_l(self, v):   self._w(0x2f3c); self._l(v)             # move.l #v,-(sp)
    def push_d6(self):     self._w(0x3f06)                         # move.w d6,-(sp)   (handle)
    def push_areg(self, a): self._w(0x2f08 | a)                   # move.l An,-(sp)
    def pop(self, n):      self._w(0xdefc); self._w(n)            # adda.w #n,sp
    def trap(self, n):     self._w(0x4e40 | (n & 0xf))
    # register moves
    def d0_to_d6(self):     self._w(0x3c00)                       # move.w d0,d6
    def d0_to_areg(self, a): self._w(0x2040 | (a << 9))          # movea.l d0,An
    def st_l(self, disp, a): self._w(0x2140 | (a << 9)); self._w(disp)   # move.l d0,(disp,An)
    def st_w(self, disp, a): self._w(0x3140 | (a << 9)); self._w(disp)   # move.w d0,(disp,An)
    def lea(self, disp, src, dst): self._w(0x41e8 | (dst << 9) | src); self._w(disp)  # lea (disp,An),Am

    def mshrink_prologue(self):
        """Release the unused TPA back to GEMDOS so Malloc has a free pool. A freshly Pexec'd
        program owns all of memory; without this, Malloc returns nothing (basepage at 4(sp))."""
        self._w(0x206f); self._w(0x0004)   # movea.l 4(sp),a0    (basepage)
        self._w(0x2028); self._w(0x000c)   # move.l  12(a0),d0   (p_tlen)
        self._w(0xd0a8); self._w(0x0014)   # add.l   20(a0),d0   (+ p_dlen)
        self._w(0xd0a8); self._w(0x001c)   # add.l   28(a0),d0   (+ p_blen)
        self._w(0x0680); self._l(0x100)    # addi.l  #$100,d0    (+ basepage)
        self._w(0x2f00)                    # move.l  d0,-(sp)     (new size)
        self._w(0x2f08)                    # move.l  a0,-(sp)     (block = basepage)
        self._w(0x4267)                    # clr.w   -(sp)        (reserved 0)
        self._w(0x3f3c); self._w(0x4a)     # move.w  #$4a,-(sp)   (Mshrink)
        self._w(0x4e41)                    # trap #1
        self._w(0xdefc); self._w(0x000c)   # adda.w  #12,sp
    # a placeholder pea (d16,pc) whose displacement is patched once the data offset is known
    def pea_pc_fixup(self):
        fix = self.off
        self._w(0x487a); self._w(0)
        return fix

    def patch_pea(self, fix, target):
        self.b[fix + 2:fix + 4] = struct.pack(">H", (target - (fix + 2)) & 0xffff)


def build_capture_tos():
    """Assemble the GEMDOS capture program -> .PRG/.TOS bytes (no relocations; PC-relative data)."""
    a = _Asm()
    REC = 4          # a4 = result-record base (also Malloc's first block, used as scratch)
    PTR = 3          # a3 = scratch address register

    a.mshrink_prologue()                                # free the TPA so Malloc has a pool

    # --- Malloc A (odd), keep the block as the record buffer; Malloc B ---
    a.push_l(MALLOC_A); a.push_w(_MALLOC); a.trap(1); a.pop(6)
    a.d0_to_areg(REC); a.st_l(_R_PTR1, REC)             # a4 = ptr1; record[ptr1] = ptr1
    a.push_l(MALLOC_B); a.push_w(_MALLOC); a.trap(1); a.pop(6)
    a.st_l(_R_PTR2, REC)                                # record[ptr2]

    # --- Getrez (XBIOS 4) ---
    a.push_w(_GETREZ); a.trap(14); a.pop(2)
    a.st_w(_R_REZ, REC)                                 # record[rez]

    # --- Fopen("IN.DAT") -> d6 ---
    a.push_w(0)                                         # mode = read
    name_fix = a.pea_pc_fixup()                         # &name
    a.push_w(_FOPEN); a.trap(1); a.pop(8); a.d0_to_d6()

    # --- sequential Freads into the record's data area; store each byte count ---
    # Lay each read's buffer at the running cursor, so the bytes actually returned land
    # contiguously at _R_DATA. Over-large requests (past EOF) just return the remainder.
    cursor = 0
    for i, count in enumerate(READ_SIZES):
        a.lea(_R_DATA + cursor, REC, PTR)               # a3 = &record[data + cursor]
        a.push_areg(PTR); a.push_l(count); a.push_d6()
        a.push_w(_FREAD); a.trap(1); a.pop(12)
        a.st_w(_R_COUNTS + 2 * i, REC)                  # record[count i]
        cursor += min(count, INPUT_LEN - cursor)        # bytes this read actually returns

    # --- Fclose(IN.DAT) ---
    a.push_d6(); a.push_w(_FCLOSE); a.trap(1); a.pop(4)

    # --- Fcreate("OUT.BIN") -> d6, Fwrite the record, Fclose ---
    a.push_w(0)
    out_fix = a.pea_pc_fixup()
    a.push_w(_FCREATE); a.trap(1); a.pop(8); a.d0_to_d6()
    a.push_areg(REC); a.push_l(_REC_LEN); a.push_d6()   # Fwrite(d6, _REC_LEN, &record)
    a.push_w(_FWRITE); a.trap(1); a.pop(12)
    a.push_d6(); a.push_w(_FCLOSE); a.trap(1); a.pop(4)

    # --- Pterm0 ---
    a.push_w(_PTERM0); a.trap(1)

    # --- embedded, PC-relative data ---
    name_off = a.off; a.b += b"IN.DAT\0"
    out_off = a.off;  a.b += b"OUT.BIN\0"
    a.patch_pea(name_fix, name_off)
    a.patch_pea(out_fix, out_off)

    text = bytes(a.b)
    header = struct.pack(">HIIIIIIH", 0x601a, len(text), 0, 0, 0, 0, 0, 0)
    return header + text + b"\x00\x00\x00\x00"          # empty relocation table


def find_hatari():
    return shutil.which("hatari")


def find_tos_rom():
    for pat in ("/opt/homebrew/Cellar/hatari/*/Hatari.app/Contents/Resources/tos.img",
                "/usr/local/Cellar/hatari/*/Hatari.app/Contents/Resources/tos.img",
                "/usr/share/hatari/tos.img"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def available():
    return bool(find_hatari() and find_tos_rom())


def capture(timeout=45):
    """Run the capture program under real TOS and return the parsed record.

    Returns {"ptr1", "ptr2", "rez", "counts": (…), "read": bytes}. Raises RuntimeError if the
    program never produced OUT.BIN (a Hatari/boot failure), so a broken run can't pass silently.
    """
    hatari, rom = find_hatari(), find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available")

    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        (drive / "PROBE.TOS").write_bytes(build_capture_tos())
        (drive / "IN.DAT").write_bytes(PROBE_INPUT)
        out = drive / "OUT.BIN"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--monitor", "rgb", "--tos-res", "low", "--tos", rom, "--run-vbls", "4000",
                "--harddrive", str(drive), "--auto", "C:\\PROBE.TOS"]
        proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if out.exists() and out.stat().st_size >= _REC_LEN:
                    time.sleep(0.3)                     # let the write flush
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

        if not (out.exists() and out.stat().st_size >= _REC_LEN):
            raise RuntimeError("capture program did not produce OUT.BIN (Hatari/boot failure)")
        rec = out.read_bytes()

    u32 = lambda o: struct.unpack_from(">I", rec, o)[0]
    u16 = lambda o: struct.unpack_from(">H", rec, o)[0]
    return {
        "ptr1": u32(_R_PTR1),
        "ptr2": u32(_R_PTR2),
        "rez": u16(_R_REZ),
        "counts": tuple(u16(_R_COUNTS + 2 * i) for i in range(len(READ_SIZES))),
        "read": rec[_R_DATA:_R_DATA + 16],
    }


if __name__ == "__main__":
    print("available:", available())
    if available():
        print(capture())
