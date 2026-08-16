#!/usr/bin/env python3
"""Inject WD1772 track images into an hxcfe-produced sector-only Pasti STX.

hxcfe's ATARIST_STX conversion emits, per track, the sector descriptors, the sector
data and (on protected tracks) the fuzzy/weak-bit mask -- but NOT the raw track image
that a WD1772 READ TRACK command returns. Copy-protected games (Rob Northen Copylock)
issue READ TRACK on their protection tracks; without a track image Hatari logs
"fdc stx : no track image for read track ..." and the game hangs on a black screen.

This post-processor decodes each track's flux to that READ TRACK byte stream and splices
it into the STX record as a Pasti track-image sub-record, flipping the track flag so
Hatari serves it. It never touches the sector data or fuzzy mask hxcfe already wrote.

Pasti track record (little-endian), as consumed by Hatari's floppy_stx.c:

    offset field
    0      record_size   (u32)  whole record, header included
    4      fuzzy_size    (u32)  bytes of fuzzy mask
    8      sector_count  (u16)
    10     flags         (u16)  0x01 sector block, 0x40 track image, 0x80 image sync
    12     mfm_size      (u16)  track length in bytes (unused by Hatari when an image is present)
    14     track_number  (u8)   bit7 = side, bits0-6 = cylinder
    15     record_type   (u8)
    16     sector_descriptor[sector_count]   (16 bytes each)
    ...    fuzzy_mask[fuzzy_size]
    ...    pTrackData: [track image sub-record if flag 0x40] then sector data blocks

Sector descriptor (16 bytes): data_offset(u32) bit_pos(u16) read_time(u16)
    id_track(u8) id_head(u8) id_sector(u8) id_size(u8) id_crc(u16 big-endian)
    fdc_status(u8) reserved(u8).

Track-image sub-record, no-sync form (what Aufit writes, flag 0x40 without 0x80):
    track_image_size(u16) then that many raw READ TRACK bytes.

Hatari reads a sector's data from pTrackData + data_offset, so inserting the sub-record
at the front of pTrackData shifts every sector's data by the sub-record's length -- each
data_offset is bumped by exactly that amount and record_size grows by it.
"""
import os
import struct
import sys

from greaseweazle.image.scp import SCP
from greaseweazle.track import PLLTrack
from greaseweazle.codec.ibm import ibm

# --- Pasti/STX layout constants ---
STX_HEADER_SIZE = 16
STX_TRACK_COUNT_OFFSET = 10          # u8 track count in the file header
TRACK_HEADER_SIZE = 16
SECTOR_DESC_SIZE = 16
TRACK_HEADER_FMT = "<IIHHHBB"        # rec_size, fuzzy, nsec, flags, mfm_size, tnum, rtype
SECTOR_DESC_DATAOFF_FMT = "<I"       # data_offset is the first field of a descriptor
TRACK_IMAGE_SIZE_FMT = "<H"          # no-sync sub-record: size word then bytes
SIDE_SHIFT = 7
CYL_MASK = 0x7F

# --- track flags ---
TRK_SECTOR_BLOCK = 0x01              # record carries sector descriptors (hxcfe sets this)
TRK_IMAGE = 0x40                     # record carries a track image -- the bit Hatari checks
TRK_IMAGE_SYNC = 0x80               # image sub-record is prefixed with a sync position
# Aufit also sets 0x20 on imaged tracks; Hatari's reader ignores it, but we mirror the
# known-good ground-truth flag word (0x61) exactly for maximum fidelity to Aufit's output.
AUFIT_IMAGE_EXTRA = 0x20
TRACK_IMAGE_FLAGS = TRK_IMAGE | AUFIT_IMAGE_EXTRA

# --- flux decode parameters (Atari ST double-density MFM) ---
ATARI_CLOCK = 2e-6                    # 2 us bit cell
ATARI_TIME_PER_REV = 0.2             # 300 RPM -> 200 ms per revolution
MFM_CELLS_PER_BYTE = 16              # 8 data bits interleaved with 8 clock bits

MAX_TRACK_IMAGE_SIZE = 0xFFFF        # track_image_size and mfm_size are u16 fields


def read_track_bytes(flux):
    """Decode one revolution of flux into the byte stream a WD1772 READ TRACK returns.

    The WD1772 shifts MFM cells continuously, emitting one byte per 16 cells, and
    realigns its byte boundary whenever it detects the A1 sync mark (0x4489 with its
    missing clock bit). Between syncs the framing is fixed, which is why gap bytes read
    as clean 0x4E once the first sync has locked and why weak-bit regions vary per read.
    """
    flux.cue_at_index()
    raw = PLLTrack(time_per_rev=ATARI_TIME_PER_REV, clock=ATARI_CLOCK, data=flux)
    bits, _timings = raw.get_all_data()
    rev_bits = raw.revolutions[0].nr_bits

    syncs = [s for s in bits.search(ibm.mfm_sync) if s < rev_bits]
    out = bytearray()
    pos = 0
    next_sync = 0
    sync_count = len(syncs)
    while pos + MFM_CELLS_PER_BYTE <= rev_bits:
        while next_sync < sync_count and syncs[next_sync] < pos:
            next_sync += 1
        # A sync starting mid-byte means the WD1772 relocks: jump the boundary onto it.
        if next_sync < sync_count and pos < syncs[next_sync] < pos + MFM_CELLS_PER_BYTE:
            pos = syncs[next_sync]
            continue
        out += ibm.decode(bits[pos:pos + MFM_CELLS_PER_BYTE].tobytes())
        pos += MFM_CELLS_PER_BYTE
    return bytes(out)


def parse_track_records(data):
    """Yield (offset, header_fields_dict) for every track record in the STX buffer."""
    ntracks = data[STX_TRACK_COUNT_OFFSET]
    off = STX_HEADER_SIZE
    for _ in range(ntracks):
        rec_size, fuzzy, nsec, flags, mfm_size, tnum, rtype = struct.unpack_from(
            TRACK_HEADER_FMT, data, off)
        yield off, dict(rec_size=rec_size, fuzzy=fuzzy, nsec=nsec, flags=flags,
                        mfm_size=mfm_size, tnum=tnum, rtype=rtype,
                        side=tnum >> SIDE_SHIFT, cyl=tnum & CYL_MASK)
        off += rec_size


def build_imaged_record(data, off, hdr, image):
    """Return a new track record with the track-image sub-record spliced in.

    Layout of an hxcfe record with a sector block and no image:
        [16B header][nsec descriptors][fuzzy mask][sector data region]
    pTrackData == start of the sector data region. We prepend the image sub-record there
    and bump every descriptor's data_offset by the sub-record length so Hatari still
    resolves each sector at pTrackData + data_offset.
    """
    desc_start = off + TRACK_HEADER_SIZE
    fuzzy_start = desc_start + hdr["nsec"] * SECTOR_DESC_SIZE
    track_data_start = fuzzy_start + hdr["fuzzy"]

    descriptors = bytearray(data[desc_start:fuzzy_start])
    fuzzy_mask = data[fuzzy_start:track_data_start]
    sector_data_region = data[track_data_start:off + hdr["rec_size"]]

    sub_record = struct.pack(TRACK_IMAGE_SIZE_FMT, len(image)) + image
    shift = len(sub_record)
    for i in range(hdr["nsec"]):
        pos = i * SECTOR_DESC_SIZE
        old_off = struct.unpack_from(SECTOR_DESC_DATAOFF_FMT, descriptors, pos)[0]
        struct.pack_into(SECTOR_DESC_DATAOFF_FMT, descriptors, pos, old_off + shift)

    new_flags = hdr["flags"] | TRACK_IMAGE_FLAGS
    new_rec_size = hdr["rec_size"] + shift
    new_header = struct.pack(TRACK_HEADER_FMT, new_rec_size, hdr["fuzzy"], hdr["nsec"],
                             new_flags, len(image), hdr["tnum"], hdr["rtype"])
    return new_header + bytes(descriptors) + fuzzy_mask + sub_record + sector_data_region


def inject(stx_path, scp_path, out_path):
    out_dir = os.path.dirname(out_path) or "."
    if not os.path.isdir(out_dir):
        sys.exit(f"error: output directory does not exist: {out_dir}")
    data = open(stx_path, "rb").read()
    scp = SCP("x", None)
    scp.from_bytes(open(scp_path, "rb").read())

    out = bytearray(data[:STX_HEADER_SIZE])
    imaged = skipped = 0
    for off, hdr in parse_track_records(data):
        record = data[off:off + hdr["rec_size"]]

        if hdr["flags"] & TRK_IMAGE:                 # already has an image -- leave it
            out += record
            skipped += 1
            continue
        if not (hdr["flags"] & TRK_SECTOR_BLOCK) or hdr["nsec"] == 0:
            out += record                            # no sector block: offsets are not ours to shift
            skipped += 1
            continue

        flux = scp.get_track(hdr["cyl"], hdr["side"])
        if flux is None:                             # no flux for this track -- cannot image it
            out += record
            skipped += 1
            continue

        image = read_track_bytes(flux)
        if not 0 < len(image) <= MAX_TRACK_IMAGE_SIZE:
            raise ValueError(f"cyl {hdr['cyl']} side {hdr['side']}: bad image size {len(image)}")
        out += build_imaged_record(data, off, hdr, image)
        imaged += 1

    open(out_path, "wb").write(out)
    print(f"imaged {imaged} track(s), left {skipped} unchanged -> {out_path} ({len(out)} bytes)")
    return imaged


def main(argv):
    if len(argv) != 4:
        sys.exit("usage: inject_track_images.py <hxcfe.stx> <flux.scp> <out.stx>")
    if inject(argv[1], argv[2], argv[3]) == 0:
        sys.exit("error: no tracks were imaged (no matching flux?)")


if __name__ == "__main__":
    main(sys.argv)
