#!/usr/bin/env python3
"""Differential check: an injected STX against the hxcfe sector-only STX it was built from.

This is the regression guard for the byte-surgery in inject_track_images.py. The flag and
Hatari-boot checks in test_scp_to_stx.sh do NOT depend on the data_offset / record_size
fixups -- a bug that dropped the offset shift would still flag 0x61 and still boot clean.
This re-parse pins exactly that arithmetic, needs no emulator, and asserts per track:

  (a) round-trip     -- sum(record_size)+header == file length, no trailing/overflow bytes
  (b) sector data    -- every payload byte-identical to hxcfe's (injection adds only images)
  (c) offset shift   -- every sector's data_offset grew by exactly (track_image_size + 2)
  (d) fuzzy mask     -- byte-identical to hxcfe's
  (e) flags          -- injected == hxcfe | 0x60 (track image + Aufit's cosmetic 0x20)

Exit status is non-zero on any mismatch, so a mutation to the splice is caught here.
"""
import struct
import sys

STX_HEADER_SIZE = 16
STX_TRACK_COUNT_OFFSET = 10
TRACK_HEADER_SIZE = 16
SECTOR_DESC_SIZE = 16
TRACK_HEADER_FMT = "<IIHHHBB"
SECTOR_DESC_FMT = "<IHHBBBBHBB"      # data_off, bitpos, rtime, C,H,R,N, crc, fdc, reserved
TRACK_IMAGE_SIZE_FMT = "<H"
INJECT_FLAG_MASK = 0x60              # TRK_IMAGE (0x40) | Aufit cosmetic 0x20
SUB_RECORD_HEADER = 2               # the u16 track_image_size word before the MFM bytes


def parse_records(data):
    off = STX_HEADER_SIZE
    recs = []
    for _ in range(data[STX_TRACK_COUNT_OFFSET]):
        rec_size, fuzzy, nsec, flags, mfm, tnum, rtype = struct.unpack_from(TRACK_HEADER_FMT, data, off)
        recs.append(dict(off=off, rec_size=rec_size, fuzzy=fuzzy, nsec=nsec,
                         flags=flags, mfm=mfm, tnum=tnum, rtype=rtype))
        off += rec_size
    return off, recs


def descriptors(data, rec):
    base = rec["off"] + TRACK_HEADER_SIZE
    out = []
    for i in range(rec["nsec"]):
        f = struct.unpack_from(SECTOR_DESC_FMT, data, base + i * SECTOR_DESC_SIZE)
        out.append(dict(data_off=f[0], bitpos=f[1], rtime=f[2], c=f[3], h=f[4],
                        r=f[5], n=f[6], crc=f[7], fdc=f[8]))
    return out


def track_data_start(rec):
    return rec["off"] + TRACK_HEADER_SIZE + rec["nsec"] * SECTOR_DESC_SIZE + rec["fuzzy"]


def fuzzy_mask(data, rec):
    start = rec["off"] + TRACK_HEADER_SIZE + rec["nsec"] * SECTOR_DESC_SIZE
    return data[start:start + rec["fuzzy"]]


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: verify_injection.py <hxcfe-sector-only.stx> <injected.stx>")
    hx = open(argv[1], "rb").read()
    inj = open(argv[2], "rb").read()

    end_hx, rh = parse_records(hx)
    end_inj, ri = parse_records(inj)
    problems = []

    # (a) round-trip: records must tile the whole file exactly
    if end_hx != len(hx):
        problems.append(f"hxcfe round-trip: parsed end {end_hx} != file length {len(hx)}")
    if end_inj != len(inj):
        problems.append(f"injected round-trip: parsed end {end_inj} != file length {len(inj)}")
    if len(rh) != len(ri):
        problems.append(f"track count changed {len(rh)} -> {len(ri)}")

    total = identical = 0
    for a, b in zip(rh, ri):
        tn = a["tnum"]
        if a["tnum"] != b["tnum"] or a["nsec"] != b["nsec"] or a["fuzzy"] != b["fuzzy"]:
            problems.append(f"tnum={tn}: header geometry changed")
            continue

        # the injected image sub-record sits at the front of pTrackData
        td = track_data_start(b)
        img_size = struct.unpack_from(TRACK_IMAGE_SIZE_FMT, inj, td)[0]
        expected_shift = img_size + SUB_RECORD_HEADER

        # (c) record_size grew by exactly the sub-record length
        if b["rec_size"] - a["rec_size"] != expected_shift:
            problems.append(f"tnum={tn}: rec_size delta {b['rec_size']-a['rec_size']} != {expected_shift}")

        # (e) flags OR-ed with the image bits, nothing else
        if b["flags"] != (a["flags"] | INJECT_FLAG_MASK):
            problems.append(f"tnum={tn}: flags {a['flags']:#06x} -> {b['flags']:#06x}, "
                            f"expected {a['flags']|INJECT_FLAG_MASK:#06x}")

        # (c) every data_offset bumped by exactly the shift; other descriptor fields intact
        da, db = descriptors(hx, a), descriptors(inj, b)
        for x, y in zip(da, db):
            if y["data_off"] - x["data_off"] != expected_shift:
                problems.append(f"tnum={tn} sec{x['r']}: data_off delta "
                                f"{y['data_off']-x['data_off']} != {expected_shift}")
            for k in ("bitpos", "rtime", "c", "h", "r", "n", "crc", "fdc"):
                if x[k] != y[k]:
                    problems.append(f"tnum={tn} sec{x['r']}: field {k} changed {x[k]} -> {y[k]}")

        # (b) sector payloads byte-identical, read at each file's own pTrackData + data_offset
        td_hx = track_data_start(a)
        for x, y in zip(da, db):
            size = 128 << (x["n"] & 3)
            pa = hx[td_hx + x["data_off"]: td_hx + x["data_off"] + size]
            pb = inj[td + y["data_off"]: td + y["data_off"] + size]
            total += 1
            if pa == pb:
                identical += 1
            else:
                problems.append(f"tnum={tn} sec{x['r']}: sector payload changed")

        # (d) fuzzy mask untouched
        if fuzzy_mask(hx, a) != fuzzy_mask(inj, b):
            problems.append(f"tnum={tn}: fuzzy mask changed")

    print(f"round-trip: hxcfe end={end_hx}/{len(hx)}  injected end={end_inj}/{len(inj)}")
    print(f"sector payloads identical to hxcfe: {identical}/{total}")
    if problems:
        print(f"FAIL: {len(problems)} problem(s):")
        for p in problems[:20]:
            print(f"  {p}")
        sys.exit(1)
    print("OK: offset/size fixups, sector data, fuzzy mask and flags all correct")


if __name__ == "__main__":
    main(sys.argv)
