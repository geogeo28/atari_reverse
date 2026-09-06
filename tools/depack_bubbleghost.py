#!/usr/bin/env python3
"""Static decrypter for the ERE Informatique protection wrapper on Bubble Ghost's GHOST.PRG.

This is an ENCRYPTER, not a cruncher: the wrapper leaves the program at its original size and
XORs it word by word, so there is no literal/match stream to inflate — see
docs/packed-executables.md for the crunchers, and projects/bubbleghost/notes/loader.md for the
annotated disassembly this was written from.

The shipped file is a normal-looking .PRG whose entry is a five-word stub that jumps into the
tail of the DATA segment, where the wrapper lives. Three layers run there:

  1. SELF-DECRYPT.  A 262-word `move.w (a1)+,d0 / eor.w d0,(a2)+ / dbf` loop unpacks the
     wrapper's own second half, keyed by the bytes just in front of it. The FIRST word it
     decrypts is the dbf's own displacement, and on a real 68000 that word is already in the
     prefetch queue -- so pass one branches to the STALE target, a fixup tail that ones-
     complements the 15-word key table and zeroes its first word before re-entering the loop.
     A model that ignores the prefetch decrypts the whole run with the wrong keystream.
  2. PROTECTION.  The unpacked code XBIOS-Floprd's track 79 side 0 of drive A: (sectors 245,
     246 and 247, which carry fuzzy bits and bad CRCs), CRCs what it read, then CRCs the
     wrapper's own last 632 bytes with the first CRC as the polynomial. The 16-bit result is
     the key for layer 3 -- the check is not a branch that can be patched out, so the disk
     data is *in* the plaintext. That key is KEY below, recovered by exhaustive search over
     the whole 16-bit space (only one value yields a valid image, and this tool re-checks it).
  3. STREAM CIPHER.  30172 words from image offset 0x14 up, each keyed by the PRECEDING
     plaintext word xor the live SR xor a rotating register: `plain[i+1] = cipher[i+1] ^
     plain[i] ^ SR ^ k[i]`, with k rotated right through X every word. SR is read INSIDE the
     loop (`move.w sr,d1`), so the N and Z flags left by the load of plain[i] are part of the
     key -- that is what SR_FIXED and the flag arithmetic below reproduce.

Layer 3 also restores the 20 bytes of jump table that the wrapper displaced with its entry
stub, and hands GEMDOS's relocation loop a 13-byte DRI stream hidden after the real data. This
tool rebuilds all of that into an ordinary .PRG (text 0xe8ca, data 0x2f4, bss 0x6650, 9
relocations) that goes straight through PrgLoader.

Usage: depack_bubbleghost.py GHOST.PRG [-o GHOST_PLAIN.PRG]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import depack_common
import prg_dis                       # the canonical .PRG header + DRI relocation-stream parser

PRG_MAGIC_WORD = 0x601a
PRG_MAGIC = PRG_MAGIC_WORD.to_bytes(2, "big")

# The entry stub: movea.l 4(sp),a0 / bra.s +2 / <2 dead bytes> / movea.l p_bbase(a0),a0 /
# jmp d16(a0). Everything else is located from the displacement in that jmp, so a different
# build of the wrapper would be rejected here rather than silently mis-decrypted.
STUB_HEAD = bytes.fromhex("206f00046002")
STUB_JUMP_OFF = 8                        # movea.l 24(a0),a0 / jmp d16(a0)
STUB_JUMP = bytes.fromhex("20680018") + bytes.fromhex("4ee8")
STUB_DISP_OFF = STUB_JUMP_OFF + 6        # the signed d16 of the jmp

# Layer 1, as offsets from the wrapper's entry point (the jmp's target).
KEY_TABLE = -0x2e                        # the 16 key words, ending in the Super(d0) helper
KEY_TABLE_NOTTED_WORDS = 15              # all but the first, ones-complemented by the fixup tail
SELF_DECRYPT_DST = 0x24                  # first word decrypted = the dbf's own displacement
SELF_DECRYPT_WORDS = 0x106
STASHED_HEAD = KEY_TABLE + 0xc           # the displaced 20 bytes of the program's jump table
STASHED_LEN = 20

# Layer 3.
CIPHER_START = 0x14                      # first word is the seed, used as a key and left as-is
CIPHER_WORDS = 0x75dc
KEY = 0x586b                             # the CRC pair over the protection track + the wrapper
SR_FIXED = 0x2300                        # supervisor, IPL 3, trace off — the SR TOS hands a .PRG
SR_X, SR_N, SR_Z = 1 << 4, 1 << 3, 1 << 2

# The wrapper's own patch to the basepage: p_bbase moves back to the real relocation stream,
# which the original linker put right after the data and the wrapper then buried under itself.
RELOC_BACKOFF = 0x286
REAL_BSS_LEN = 0x6650

RELOC_STREAM_TERMINATOR = 0          # ends the DRI stream; no step byte can be 0
LONGWORD_BYTES = 4                   # the stream's first-fixup field, and every pointer it fixes


class DepackError(Exception):
    """The file is not the Bubble Ghost wrapper, or it did not decrypt to a valid image."""


def _wr16(buf, off, value):
    struct.pack_into(">H", buf, off, value & 0xffff)


def _xor16(buf, off, value):
    _wr16(buf, off, prg_dis.rd16(buf, off) ^ value)


def _locate_wrapper(image, text_len, data_len):
    """Image offset of the wrapper's entry, read out of the entry stub's `jmp d16(a0)`."""
    if image[:len(STUB_HEAD)] != STUB_HEAD or image[STUB_JUMP_OFF:STUB_DISP_OFF] != STUB_JUMP:
        raise DepackError("entry is not the Bubble Ghost wrapper stub")
    disp = prg_dis.rd16(image, STUB_DISP_OFF)
    bss_base = text_len + data_len                     # what GEMDOS puts in p_bbase
    entry = bss_base + (disp - 0x10000 if disp & 0x8000 else disp)
    if not text_len <= entry < bss_base:
        raise DepackError("wrapper entry 0x%x is outside the data segment" % entry)
    return entry


def _self_decrypt(image, wrapper):
    """Layer 1: unpack the wrapper's second half, prefetch quirk and fixup tail included."""
    key_table = wrapper + KEY_TABLE
    dst = wrapper + SELF_DECRYPT_DST

    # Pass one decrypts a single word and then, because the dbf's displacement was fetched
    # before that same word was rewritten, jumps to the fixup tail instead of looping.
    _xor16(image, dst, prg_dis.rd16(image, key_table))
    for i in range(KEY_TABLE_NOTTED_WORDS):
        _wr16(image, key_table + 2 + 2 * i, ~prg_dis.rd16(image, key_table + 2 + 2 * i))
    _wr16(image, key_table, 0)

    # ...and re-enters the loop with the key pointer reset and the destination one word on.
    src, dst = key_table, dst + 2
    for _ in range(SELF_DECRYPT_WORDS - 1):
        _xor16(image, dst, prg_dis.rd16(image, src))
        src, dst = src + 2, dst + 2


def _stream_decrypt(image, key):
    """Layer 3: the chained word cipher whose keystream includes the CPU's own flags."""
    at = CIPHER_START
    previous = prg_dis.rd16(image, at)
    extend = 0
    for _ in range(CIPHER_WORDS):
        flags = (SR_FIXED | (SR_X if extend else 0) | (SR_N if previous & 0x8000 else 0)
                 | (SR_Z if previous == 0 else 0))
        keystream = previous ^ flags ^ key
        at += 2
        previous = prg_dis.rd16(image, at) ^ keystream
        _wr16(image, at, previous)
        extend, key = key & 1, ((key >> 1) | (extend << 15)) & 0xffff


def _reloc_stream(image, image_end):
    """The DRI relocation bytes buried at `image_end`, plus the offsets they fix.

    Decoding the stream is prg_dis.parse_reloc's job — the one canonical DRI parser. What this
    adds is the raw SPAN of bytes, which the depacker has to re-emit as the rebuilt .PRG's own
    table: the stream runs to its first zero byte past the first-fixup longword (0 is the
    terminator and no step byte can be 0). The private walk that used to live here had already
    DIVERGED from the canonical one — a zero first longword fell through into the byte loop
    instead of ending the table — which is exactly the drift CLAUDE.md §6 is about.

    `image_end` is both where the stream starts and the end of the image its fixups may point
    into: the linker put the table right after text+data, and this output carries no symbols.
    """
    if image_end + LONGWORD_BYTES > len(image):
        raise DepackError("relocation stream starts past the end of the image")
    end = image.find(RELOC_STREAM_TERMINATOR, image_end + LONGWORD_BYTES)
    if end < 0:
        raise DepackError("relocation stream is not terminated")
    fixups = sorted(prg_dis.parse_reloc(image, {"reloc_off": image_end, "absf": 0}))
    for fixup in fixups:
        if fixup & 1 or fixup + LONGWORD_BYTES > image_end:
            raise DepackError("relocation offset 0x%x is not a longword inside the image" % fixup)
        if prg_dis.rd32(image, fixup) >= image_end:
            raise DepackError("relocated pointer at 0x%x does not point into the image" % fixup)
    return bytes(image[image_end:end + 1]), fixups


def decode(data):
    """Decrypt a shipped GHOST.PRG into an ordinary, relocatable GEMDOS .PRG."""
    if len(data) < prg_dis.HEADER_LEN or data[:2] != PRG_MAGIC:
        raise DepackError("not a GEMDOS .PRG")
    text_len, data_len = struct.unpack_from(">II", data, 2)
    if prg_dis.HEADER_LEN + text_len + data_len > len(data):
        raise DepackError("header describes more image than the file holds")
    image = bytearray(data[prg_dis.HEADER_LEN:prg_dis.HEADER_LEN + text_len + data_len])

    wrapper = _locate_wrapper(image, text_len, data_len)
    _self_decrypt(image, wrapper)
    _stream_decrypt(image, KEY)
    stashed = wrapper + STASHED_HEAD
    image[0:STASHED_LEN] = image[stashed:stashed + STASHED_LEN]

    real_data_end = text_len + data_len - RELOC_BACKOFF
    real_data_len = real_data_end - text_len
    if real_data_len < 0:
        raise DepackError("data segment is too short to hold the buried relocation stream")
    reloc, fixups = _reloc_stream(image, real_data_end)
    if not fixups:
        raise DepackError("decrypted image has no relocations — wrong key?")

    header = struct.pack(prg_dis.PRG_HEADER_FORMAT, PRG_MAGIC_WORD, text_len, real_data_len,
                         REAL_BSS_LEN, 0, 0, 0, 0)   # no symbols, no reserved/flags, ABSFLAG clear
    return header + bytes(image[:real_data_end]) + reloc


if __name__ == "__main__":
    sys.exit(depack_common.main("depack_bubbleghost.py", __doc__, decode, DepackError))
