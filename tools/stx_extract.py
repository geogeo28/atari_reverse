#!/usr/bin/env python3
"""Pasti/`.STX` floppy-image reader: protection report + clean `.ST` extraction.

Stdlib only, game-agnostic. A Pasti image records a floppy at (near) flux level —
every sector's address field, its FDC status, its unstable ("fuzzy") bits and the
raw MFM track length — precisely so that *copy protection survives the dump*. The
filesystem underneath is still ordinary FAT12, so the useful pipeline is two steps:

    stx_extract.py GAME.STX --to-st GAME.ST   # flux -> plain sector image
    st_extract.py  GAME.ST  -o extracted      # sector image -> files

Priority is *not producing garbage*, same as `st_extract.py`: a file that is not a
Pasti image, or whose track records do not walk exactly to EOF, is rejected with a
reason rather than half-decoded, and a sector whose data slice escapes its own track
record is refused rather than read out of a neighbouring track.

Geometry is derived from the recorded sectors, not from the FAT12 boot sector, because
a protected disk need not carry a filesystem at all (custom-format loaders are common).
Where a plausible boot sector *is* present its BPB is used as a cross-check and any
disagreement is reported — see `st_extract.py` for the canonical BPB decoder.

A sector that the FDC read badly is *still recorded*: Pasti stores its 512 bytes along
with the status. Those bytes are usually the sector's real content — a CRC error can be
one bad bit in the CRC itself — so by default they are placed and a per-sector WARNING
says the content is unverified. `--strict` restores the conservative rule: place nothing
whose *content* a status bit questions (lost data, CRC error). Either way a slot with no
recorded bytes at all (no descriptor, an unformatted track, record-not-found) is
zero-filled and warned about.

Two kinds of "wrong" are reported separately and they must not be confused:

  PROTECTION — sectors the FDC cannot read cleanly, fuzzy bytes, duplicate or
  out-of-place sector IDs, extra sectors past the standard count, unformatted
  tracks. This is *expected* on a protected disk and is not a warning.

  WARNING — something that damages the filesystem extraction: a standard sector
  missing from the `.ST` (zero-filled) or placed unverified, contradicted geometry,
  disagreeing copies of one sector, a truncated record. Both modes run the placement
  pass, so the verdict depends on the disk and never on which mode was asked for.

Usage:
  python3 stx_extract.py IMAGE.STX                 # header, per-track table, protection
  python3 stx_extract.py IMAGE.STX --to-st OUT.ST  # also write the clean FAT12 image
  python3 stx_extract.py IMAGE.STX --to-st OUT.ST --strict   # zero-fill every flagged sector

Exit status:
  0  clean run
  1  unusable image, or the run completed but emitted warnings (dirty extraction)
  2  bad command line
"""
import struct
import sys
from collections import Counter

USAGE = "usage: stx_extract.py IMAGE.STX [--to-st OUT.ST] [--strict]"
TO_ST_FLAG = "--to-st"
STRICT_FLAG = "--strict"

# --- file header (16 bytes) -----------------------------------------------------
FILE_MAGIC = b"RSY\0"
FILE_HEADER_SIZE = 16
HDR_VERSION_OFF = 4          # u16
HDR_TOOL_OFF = 6             # u16 — which Pasti tool wrote the image
HDR_RESERVED1_OFF = 8        # u16
HDR_TRACK_COUNT_OFF = 10     # u8  — count of track *records*, not cylinders
HDR_REVISION_OFF = 11        # u8
HDR_RESERVED2_OFF = 12       # u32
SUPPORTED_VERSION = 3        # the only layout this reader knows; refuse others

# --- track record header (16 bytes, then the optional blocks below) --------------
TRACK_HEADER_SIZE = 16
TRK_RECORD_SIZE_OFF = 0      # u32 — whole record, used to step to the next one
TRK_FUZZY_SIZE_OFF = 4       # u32 — bytes of fuzzy mask, between descriptors and data
TRK_SECTOR_COUNT_OFF = 8     # u16
TRK_FLAGS_OFF = 10           # u16
TRK_MFM_SIZE_OFF = 12        # u16 — raw MFM cells on the physical track
TRK_NUMBER_OFF = 14          # u8  — side in bit 7, cylinder in bits 0..6
                             # u8 track_type at +15 is not used here

TRACK_FLAG_SECTOR_DESCRIPTORS = 0x0001
TRACK_FLAG_TRACK_IMAGE = 0x0040
TRACK_FLAG_TRACK_IMAGE_SYNC = 0x0080
TRACK_FLAG_BITS = (
    (TRACK_FLAG_SECTOR_DESCRIPTORS, "sectors"),
    (TRACK_FLAG_TRACK_IMAGE, "image"),
    (TRACK_FLAG_TRACK_IMAGE_SYNC, "sync"),
)
TRACK_NUMBER_SIDE_BIT = 0x80
TRACK_NUMBER_CYLINDER_MASK = 0x7F

# --- sector descriptor (16 bytes) ------------------------------------------------
# Full layout: u32 data_offset, u16 bit_position, u16 read_time, then the address
# field (u8 id_track, u8 id_head, u8 id_sector, u8 id_size, u16 id_crc big-endian —
# the CRC is the one field stored as it comes off the disk), u8 fdc_status, u8
# reserved. bit_position/read_time/id_crc/reserved carry no decision here and are
# skipped; read_time's information is already in the FDC "variable read time" bit.
SECTOR_DESC_SIZE = 16
SEC_DATA_OFFSET_OFF = 0      # u32 — relative to the track's data area
SEC_ID_TRACK_OFF = 8         # u8
SEC_ID_HEAD_OFF = 9          # u8
SEC_ID_SECTOR_OFF = 10       # u8
SEC_ID_SIZE_OFF = 11         # u8
SEC_FDC_STATUS_OFF = 14      # u8

# IBM/WD address-field size code: bytes = 128 << (code & 3).
SECTOR_SIZE_BASE = 128
SECTOR_SIZE_CODE_MASK = 0x03
STANDARD_SECTOR_SIZE = 512   # the only size a FAT12 `.ST` image can hold
# More than any real floppy format packs into one track (11 at DD, ~22 at HD). A derived
# count above this is not a geometry, it is a malformed image, and believing it would turn a
# small file into a multi-gigabyte `.ST`. Doubles as the BPB's plausibility bound.
MAX_SECTORS_PER_TRACK = 30

# WD1772 read-sector status bits, plus the two Pasti overloads (0x01, 0x80).
FDC_STATUS_OK = 0
FDC_STATUS_VARIABLE_READ_TIME = 0x01   # Pasti: the sector's read time varies per revolution
FDC_STATUS_LOST_DATA = 0x04
FDC_STATUS_CRC_ERROR = 0x08
FDC_STATUS_RECORD_NOT_FOUND = 0x10
FDC_STATUS_DELETED_DATA = 0x20         # deleted-data address mark; the data itself is intact
FDC_STATUS_FUZZY_BITS = 0x80           # Pasti: a fuzzy-bit mask exists for this sector
FDC_STATUS_BITS = (
    (FDC_STATUS_VARIABLE_READ_TIME, "variable read time"),
    (FDC_STATUS_LOST_DATA, "lost data"),
    (FDC_STATUS_CRC_ERROR, "CRC error"),
    (FDC_STATUS_RECORD_NOT_FOUND, "record not found"),
    (FDC_STATUS_DELETED_DATA, "deleted data mark"),
    (FDC_STATUS_FUZZY_BITS, "fuzzy bits"),
)
# Record-not-found is the one status where the image holds no sector data at all: the FDC
# never reached a data field, so there is nothing to place. (Pasti-aware emulators skip the
# data slice for exactly this bit.)
FDC_STATUS_NO_DATA = FDC_STATUS_RECORD_NOT_FOUND
# Bits that question the 512 recorded bytes without denying they exist. Placing them is the
# default — see the module docstring — but never silently.
FDC_STATUS_UNVERIFIED = FDC_STATUS_LOST_DATA | FDC_STATUS_CRC_ERROR
# The other three bits do not disqualify a sector at all. 0x01 and 0x20 are timing and
# address-mark bookkeeping, and 0x80 is Pasti's own overload for "a fuzzy mask exists for
# this sector" — not a WD1772 read error, so a sector carrying only 0x80 reads back fine on
# real hardware. All three are still reported as protection.

# --- FAT12 BPB cross-check -------------------------------------------------------
# A handful of fields read straight out of the placed boot sector; st_extract.py owns the
# full decoder. Sanity bounds keep a non-FAT protected disk from raising false alarms.
BPB_BYTES_PER_SECTOR_OFF = 11
BPB_TOTAL_SECTORS_OFF = 19
BPB_SECTORS_PER_TRACK_OFF = 24
BPB_HEADS_OFF = 26
BOOT_SECTOR_LBA = 0
# (BPB offset, geometry key, display name, plausibility bound). The bound lives next to the
# offset it belongs to: keyed off the display name instead, a wording edit would silently
# swap the limits and disable the check.
BPB_GEOMETRY_FIELDS = (
    (BPB_SECTORS_PER_TRACK_OFF, "sectors_per_track", "sectors/track", MAX_SECTORS_PER_TRACK),
    (BPB_HEADS_OFF, "sides", "sides", 2),
)

TRACK_TABLE_HEADER = "%4s %4s %4s %7s  %-16s %6s %6s %6s" % (
    "REC", "CYL", "SIDE", "SECTORS", "SIZES", "FUZZY", "MFM", "FLAGS")


def le16(data, off):
    return struct.unpack_from("<H", data, off)[0]


def le32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def bit_names(value, table):
    """Flag names for the bits `table` documents, plus any leftover bits as hex."""
    names = [name for bit, name in table if value & bit]
    leftover = value & ~sum(bit for bit, _ in table)
    if leftover:
        names.append("0x%02x" % leftover)
    return names


def fdc_status_text(status):
    names = bit_names(status, FDC_STATUS_BITS)
    return ", ".join(names) if names else "ok"


def track_flags_text(flags):
    names = bit_names(flags, TRACK_FLAG_BITS)
    return "|".join(names) if names else "-"


def track_label(track):
    return "cyl %d side %d" % (track["cylinder"], track["side"])


def sector_label(track, sector):
    return "%s sector %d" % (track_label(track), sector["id_sector"])


def _id_list(sector_ids):
    return ", ".join(str(i) for i in sector_ids)


def st_slot(track_base_lba, sector_id):
    """The `.ST` slot a sector fills: IDs are numbered from 1, the image from 0."""
    return track_base_lba + sector_id - 1


def parse_file_header(data):
    """Decode the 16-byte file header. Raises ValueError if this is not a Pasti image."""
    if len(data) < FILE_HEADER_SIZE:
        raise ValueError("file is %d bytes, shorter than the %d-byte Pasti header"
                         % (len(data), FILE_HEADER_SIZE))
    if data[:len(FILE_MAGIC)] != FILE_MAGIC:
        raise ValueError("magic is %r, not %r" % (data[:len(FILE_MAGIC)], FILE_MAGIC))
    header = dict(
        version=le16(data, HDR_VERSION_OFF),
        tool=le16(data, HDR_TOOL_OFF),
        reserved1=le16(data, HDR_RESERVED1_OFF),
        track_count=data[HDR_TRACK_COUNT_OFF],
        revision=data[HDR_REVISION_OFF],
        reserved2=le32(data, HDR_RESERVED2_OFF),
    )
    if header["version"] != SUPPORTED_VERSION:
        raise ValueError("Pasti version %d — this reader only knows version %d"
                         % (header["version"], SUPPORTED_VERSION))
    if header["track_count"] == 0:
        raise ValueError("header declares 0 track records")
    return header


def _parse_sector_descriptor(data, off, data_area, record_end):
    """One 16-byte address-field/status record, resolved to its sector data slice.

    `data_start` is absolute; `data_in_record` records whether the whole slice stays
    inside its own track record. It must: a slice that escapes would silently serve
    another track's bytes, which is the plausible-looking rubbish this tool refuses.
    """
    size_code = data[off + SEC_ID_SIZE_OFF]
    data_offset = le32(data, off + SEC_DATA_OFFSET_OFF)
    size = SECTOR_SIZE_BASE << (size_code & SECTOR_SIZE_CODE_MASK)
    return dict(
        data_offset=data_offset,
        data_start=data_area + data_offset,
        data_in_record=data_area + data_offset + size <= record_end,
        id_track=data[off + SEC_ID_TRACK_OFF],
        id_head=data[off + SEC_ID_HEAD_OFF],
        id_sector=data[off + SEC_ID_SECTOR_OFF],
        id_size_code=size_code,
        size=size,
        fdc_status=data[off + SEC_FDC_STATUS_OFF],
    )


def _parse_track_record(data, start, limit, record_index):
    """One track record. `limit` is EOF; raises ValueError if the record does not fit."""
    if start + TRACK_HEADER_SIZE > limit:
        raise ValueError("track record %d: header runs past EOF (offset %d of %d)"
                         % (record_index, start, limit))
    record_size = le32(data, start + TRK_RECORD_SIZE_OFF)
    if record_size < TRACK_HEADER_SIZE:
        raise ValueError("track record %d: record size %d is smaller than its header"
                         % (record_index, record_size))
    if start + record_size > limit:
        raise ValueError("track record %d: record size %d overruns EOF (%d bytes left)"
                         % (record_index, record_size, limit - start))
    number = data[start + TRK_NUMBER_OFF]
    track = dict(
        index=record_index,
        offset=start,
        record_size=record_size,
        fuzzy_size=le32(data, start + TRK_FUZZY_SIZE_OFF),
        sector_count=le16(data, start + TRK_SECTOR_COUNT_OFF),
        flags=le16(data, start + TRK_FLAGS_OFF),
        mfm_size=le16(data, start + TRK_MFM_SIZE_OFF),
        cylinder=number & TRACK_NUMBER_CYLINDER_MASK,
        side=1 if number & TRACK_NUMBER_SIDE_BIT else 0,
    )
    track["sectors"] = _parse_track_sectors(data, track)
    return track


def _parse_track_sectors(data, track):
    """The track's sector descriptors, or [] when the record carries none.

    Sector data offsets are relative to the *data area*, which begins after the
    descriptors and the fuzzy mask; an optional raw track image sits at its front,
    so the offsets are not a plain 0/512/1024 progression.
    """
    if not track["flags"] & TRACK_FLAG_SECTOR_DESCRIPTORS or not track["sector_count"]:
        return []
    descriptors = track["offset"] + TRACK_HEADER_SIZE
    data_area = descriptors + SECTOR_DESC_SIZE * track["sector_count"] + track["fuzzy_size"]
    record_end = track["offset"] + track["record_size"]
    if data_area > record_end:
        raise ValueError("track record %d: %d descriptors + %d fuzzy bytes overrun the record"
                         % (track["index"], track["sector_count"], track["fuzzy_size"]))
    return [_parse_sector_descriptor(data, descriptors + SECTOR_DESC_SIZE * i,
                                     data_area, record_end)
            for i in range(track["sector_count"])]


def parse_tracks(data, header):
    """Walk the track records. Raises ValueError unless the walk lands exactly on EOF."""
    tracks = []
    off = FILE_HEADER_SIZE
    for index in range(header["track_count"]):
        track = _parse_track_record(data, off, len(data), index)
        tracks.append(track)
        off += track["record_size"]
    if off != len(data):
        raise ValueError("track records end at %d but the file is %d bytes — %+d"
                         % (off, len(data), len(data) - off))
    return tracks


class StxImage:
    """A Pasti image: header, track records, derived geometry, and the `.ST` sector map."""

    def __init__(self, data, strict=False):
        self.data = data
        self.strict = strict
        self.header = parse_file_header(data)
        self.tracks = parse_tracks(data, self.header)
        self.warnings = []
        self.padding = self._trailing_unformatted_records()
        self.geometry = self._derive_geometry()
        self.standard_ids = frozenset(range(1, self.geometry["sectors_per_track"] + 1))
        self.sector_map = self._build_sector_map()
        # The BPB can only be read once the boot sector is placed, and it is what decides
        # whether a trailing unformatted track is dump padding or a hole — so the missing
        # sectors are reported last, after that verdict is in.
        self.volume_sectors = self._cross_check_bpb()
        self._drop_padding_inside_volume()
        self._report_unfilled_sectors()

    # --- sector classification ---------------------------------------------------

    def sector_bytes(self, sector):
        return self.data[sector["data_start"]:sector["data_start"] + sector["size"]]

    def has_recorded_data(self, sector):
        """True if the image really holds 512 bytes for this sector, whatever their quality."""
        return (sector["data_in_record"] and sector["size"] == STANDARD_SECTOR_SIZE
                and not sector["fdc_status"] & FDC_STATUS_NO_DATA)

    def is_trusted(self, sector):
        """True if those bytes are a verified read — no status bit questions the content."""
        return (self.has_recorded_data(sector)
                and not sector["fdc_status"] & FDC_STATUS_UNVERIFIED)

    def is_placeable(self, sector):
        """True if this sector may fill an `.ST` slot under the mode that was asked for."""
        if not self.has_recorded_data(sector) or sector["id_sector"] not in self.standard_ids:
            return False
        return not self.strict or self.is_trusted(sector)

    def standard_descriptors(self, track):
        """Descriptors shaped like an `.ST` sector: 512 bytes, wholly inside their record.

        Shape is a property of the format, not of this dump, so counting these stays immune
        to read damage — while keeping an oversized protection sector, or one whose data
        slice escapes its record, from voting on the disk's sector numbering.
        """
        return [sector for sector in track["sectors"]
                if sector["size"] == STANDARD_SECTOR_SIZE and sector["data_in_record"]]

    # --- geometry ----------------------------------------------------------------

    def _trailing_unformatted_records(self):
        """Record indices of unformatted tracks past the last formatted cylinder of a side.

        These *look* like ordinary dump padding — an 82-track drive over an 80-track volume.
        The test is by cylinder, not record order, because nothing in the format guarantees
        the records are in physical order. It is only provisional: a protected disk can leave
        a cylinder inside its own volume unformatted, which lands in exactly this set, so the
        BPB gets the final say in `_drop_padding_inside_volume`.
        """
        last_formatted = {}
        for track in self.tracks:
            if track["sectors"]:
                side = track["side"]
                last_formatted[side] = max(last_formatted.get(side, -1), track["cylinder"])
        return {t["index"] for t in self.tracks if not t["sectors"]
                and t["cylinder"] > last_formatted.get(t["side"], -1)}

    def _drop_padding_inside_volume(self):
        """Demote any "padding" track whose sectors fall inside the declared FAT12 volume.

        Cylinder order alone cannot tell a drive's trailing spare from a deliberately
        unformatted cylinder at the end of a protected disk — both sit past the last
        formatted cylinder. The BPB's total sector count is the independent witness, and a
        track that owns filesystem sectors is a hole to be warned about, never padding.
        """
        if self.volume_sectors is None:
            return
        self.padding = {track["index"] for track in self.tracks
                        if track["index"] in self.padding and not self._owns_volume_sectors(track)}

    def _owns_volume_sectors(self, track):
        """True if this track's `.ST` slots exist at all and fall inside the declared volume."""
        if track["side"] >= self.geometry["sides"]:
            # A side no formatted track uses is not part of the layout, so this record owns no
            # slots — demoting it would point `track_lba` at another cylinder's, or past the end.
            return False
        return self.track_lba(track) < self.volume_sectors

    def _derive_geometry(self):
        """Cylinders, sides and sectors/track read off the recorded sectors."""
        formatted = [t for t in self.tracks if t["index"] not in self.padding]
        if not formatted:
            raise ValueError("every track record is unformatted — there is no filesystem here")
        geometry = dict(
            # Sides come from formatted tracks only: an empty side-1 record would double
            # the LBA stride and shift every sector of the image. Cylinders span *all*
            # records, so an unformatted spare cylinder still costs only trailing zeros.
            sides=max(t["side"] for t in formatted) + 1,
            cylinders=max(t["cylinder"] for t in self.tracks) + 1,
            sectors_per_track=self._derive_sectors_per_track(formatted),
        )
        geometry["total_sectors"] = (geometry["cylinders"] * geometry["sides"]
                                     * geometry["sectors_per_track"])
        self._check_one_record_per_track(geometry)
        return geometry

    def _derive_sectors_per_track(self, formatted):
        """The modal count of sector *descriptors* per formatted track.

        A wrong count is not a small error: sectors/track is the LBA stride, so one too
        many or one too few shifts every track after the first and garbles the whole
        filesystem. It is therefore a warning whenever the winning count is not held by
        an outright majority of the formatted tracks.

        The vote counts descriptors, not sectors that read *cleanly*: how a track was
        formatted is a property of the disk, while how well it read is a property of this
        one dump. Voting on clean reads would let read damage on a bare majority of tracks
        shrink the stride and silently garble the entire filesystem.
        """
        counts = Counter(len(self.standard_descriptors(track)) for track in formatted)
        counts.pop(0, None)                 # an unformatted track votes for nothing
        if not counts:
            raise ValueError("no formatted track carries a standard %d-byte sector descriptor —"
                             " there is no sector numbering to derive a layout from"
                             % STANDARD_SECTOR_SIZE)
        # Tie-break on the larger count purely for determinism; the tie itself warns below.
        best = max(counts, key=lambda n: (counts[n], n))
        if best > MAX_SECTORS_PER_TRACK:
            raise ValueError("the recorded tracks claim %d sectors each — no floppy format holds"
                             " more than %d, so this is not a geometry"
                             % (best, MAX_SECTORS_PER_TRACK))
        if counts[best] * 2 <= sum(counts.values()):
            self.warnings.append("sectors/track is ambiguous — %s; using %d"
                                 % (", ".join("%d track(s) hold %d" % (c, n)
                                              for n, c in sorted(counts.items())), best))
        return best

    def _check_one_record_per_track(self, geometry):
        """One record per cylinder/side, or the `.ST` layout cannot be trusted."""
        seen = Counter((t["cylinder"], t["side"]) for t in self.tracks)
        for (cylinder, side), count in sorted(seen.items()):
            if count > 1:
                self.warnings.append("cyl %d side %d has %d track records — their sectors"
                                     " compete for the same .ST slots"
                                     % (cylinder, side, count))
        expected = geometry["cylinders"] * geometry["sides"]
        if len(seen) != expected:
            self.warnings.append("%d distinct cyl/side records but the geometry implies %d"
                                 % (len(seen), expected))

    def _plausible_bpb(self):
        """The placed boot sector, but only if its BPB is coherent enough to be evidence.

        A protected disk may carry no filesystem at all, so a custom loader in sector 1 must
        not raise false alarms. Every field is bounds-checked before *any* of them is used —
        checking each one only as it is compared would let a loader that happens to hold
        `0x0200` at offset 11 have its garbage elsewhere believed.
        """
        boot = self.sector_map[BOOT_SECTOR_LBA] if self.sector_map else None
        if not boot or le16(boot, BPB_BYTES_PER_SECTOR_OFF) != STANDARD_SECTOR_SIZE:
            return None
        if any(not 1 <= le16(boot, offset) <= limit
               for offset, _, _, limit in BPB_GEOMETRY_FIELDS):
            return None
        declared = le16(boot, BPB_TOTAL_SECTORS_OFF)
        track = le16(boot, BPB_SECTORS_PER_TRACK_OFF) * le16(boot, BPB_HEADS_OFF)
        # A floppy volume is a whole number of cylinders of the BPB's own geometry. A total
        # that is not one did not come from a formatter, so none of this is a BPB.
        return boot if declared and not declared % track else None

    def _cross_check_bpb(self):
        """Cross-check the derived geometry against the boot sector's BPB.

        Returns the volume size the BPB declares, in sectors, or None when there is no
        plausible BPB to check against.
        """
        boot = self._plausible_bpb()
        if boot is None:
            return None
        for offset, key, field, _ in BPB_GEOMETRY_FIELDS:
            claimed = le16(boot, offset)
            if claimed != self.geometry[key]:
                self.warnings.append("boot sector's BPB says %d %s, the recorded sectors say"
                                     " %d — the .ST layout follows the sectors"
                                     % (claimed, field, self.geometry[key]))
        declared = le16(boot, BPB_TOTAL_SECTORS_OFF)
        # Not an equality: a disk may legitimately carry spare cylinders past the end of its
        # volume. But the volume must *fit* in what was recorded — when it does not, the LBA
        # stride is too small and every track after the first is placed at the wrong offset.
        if declared > self.geometry["total_sectors"]:
            self.warnings.append("boot sector's BPB declares an %d-sector volume but the derived"
                                 " geometry only holds %d — %d sectors/track cannot be right"
                                 % (declared, self.geometry["total_sectors"],
                                    self.geometry["sectors_per_track"]))
        return declared

    # --- the `.ST` sector map -----------------------------------------------------

    def track_base_lba(self, cylinder, side):
        """The `.ST` sector one cylinder/side starts at."""
        return ((cylinder * self.geometry["sides"] + side) * self.geometry["sectors_per_track"])

    def track_lba(self, track):
        return self.track_base_lba(track["cylinder"], track["side"])

    def _build_sector_map(self):
        """One slot per `.ST` sector: its bytes, or None where nothing could be placed."""
        blocks = [None] * self.geometry["total_sectors"]
        for lba, copies in sorted(self.placement_candidates().items()):
            blocks[lba] = self._choose_copy(lba, copies)
        return blocks

    def placement_candidates(self):
        """`.ST` slot -> the (track, sector) descriptors whose bytes could fill it."""
        candidates = {}
        for track in self.tracks:
            base = self.track_lba(track)
            for sector in track["sectors"]:
                if self.is_placeable(sector):
                    candidates.setdefault(st_slot(base, sector["id_sector"]), []).append(
                        (track, sector))
        return candidates

    def _choose_copy(self, lba, copies):
        """The bytes for one `.ST` slot, warning when the copies of it disagree.

        A verified read always beats a status-flagged one, so a re-read that came back clean
        wins over a damaged copy without a word. Only copies of equal standing can conflict,
        and then the *last* is kept: when one cyl/side was recorded more than once the later
        record is the later re-read, which is also what a straight sector-by-sector overwrite
        would have produced.
        """
        trusted = [(track, sector) for track, sector in copies if self.is_trusted(sector)]
        best = trusted or copies
        payloads = [self.sector_bytes(sector) for _, sector in best]
        if len(set(payloads)) > 1:
            self.warnings.append("%s: %d recorded copies of .ST sector %d disagree — kept the"
                                 " last (track record %d)"
                                 % (sector_label(*best[-1]), len(best), lba, best[-1][0]["index"]))
        if not trusted:
            track, sector = best[-1]
            self.warnings.append("%s: placed from a sector the FDC flagged 0x%02x (%s) —"
                                 " content unverified"
                                 % (sector_label(track, sector), sector["fdc_status"],
                                    fdc_status_text(sector["fdc_status"])))
        return payloads[-1]

    def _report_unfilled_sectors(self):
        """Warn about every `.ST` slot inside the volume that no record could fill.

        The layout grid is walked, not the track records: a cylinder/side whose record is
        missing from the file altogether still owns filesystem sectors, and iterating records
        would leave exactly those zero-filled slots unnamed — the one case where the `.ST`
        looks complete and nothing says otherwise.

        The two causes are not the same fact and must not read the same: a sector with a
        descriptor exists in the image and simply failed to qualify (so `--strict`, or a
        status the reader will not place, is what emptied the slot), while a sector with no
        descriptor was never formatted and nothing anywhere can recover it.
        """
        recorded_ids = self._recorded_ids_by_track()
        padded = self._padding_tracks()
        for cylinder in range(self.geometry["cylinders"]):
            for side in range(self.geometry["sides"]):
                if (cylinder, side) in padded:
                    continue
                self._report_unfilled_track(cylinder, side,
                                            recorded_ids.get((cylinder, side), frozenset()))

    def _report_unfilled_track(self, cylinder, side, recorded_ids):
        base = self.track_base_lba(cylinder, side)
        unfilled = [sector_id for sector_id in sorted(self.standard_ids)
                    if self.sector_map[st_slot(base, sector_id)] is None]
        never_formatted = [sector_id for sector_id in unfilled if sector_id not in recorded_ids]
        not_placed = [sector_id for sector_id in unfilled if sector_id in recorded_ids]
        where = "cyl %d side %d" % (cylinder, side)
        if never_formatted:
            self.warnings.append("%s: sector(s) %s were never formatted — no bytes exist"
                                 " anywhere in the image, zero-filled"
                                 % (where, _id_list(never_formatted)))
        if not_placed:
            self.warnings.append("%s: sector(s) %s are recorded but could not be placed —"
                                 " zero-filled" % (where, _id_list(not_placed)))

    def _recorded_ids_by_track(self):
        """(cyl, side) -> every sector ID any record for it carries.

        Records are merged so that a disk dumped twice does not get one sector reported as
        "never formatted" merely because the *other* record is the one that carries it.
        """
        merged = {}
        for track in self.tracks:
            merged.setdefault((track["cylinder"], track["side"]), set()).update(
                sector["id_sector"] for sector in track["sectors"])
        return merged

    def _padding_tracks(self):
        """The (cyl, side) pairs whose only records are dump padding — no volume sectors."""
        return {(t["cylinder"], t["side"]) for t in self.tracks if t["index"] in self.padding}

    def recovered_sectors(self):
        return sum(1 for block in self.sector_map if block is not None)

    def st_bytes(self):
        return b"".join(block if block is not None else bytes(STANDARD_SECTOR_SIZE)
                        for block in self.sector_map)


def sector_size_summary(track):
    """Sector sizes as a compact "10x512" / "9x512+1x1024" string."""
    if not track["sectors"]:
        return "-"
    sizes = Counter(s["size"] for s in track["sectors"])
    return "+".join("%dx%d" % (count, size) for size, count in sorted(sizes.items()))


def _sector_anomalies(image, track):
    """Per-sector protection findings for one track."""
    found = []
    per_track = image.geometry["sectors_per_track"]
    for sector in track["sectors"]:
        where = sector_label(track, sector)
        if sector["fdc_status"] != FDC_STATUS_OK:
            found.append("%s: FDC status 0x%02x (%s)"
                         % (where, sector["fdc_status"], fdc_status_text(sector["fdc_status"])))
        if sector["size"] != STANDARD_SECTOR_SIZE:
            found.append("%s: %d-byte sector (size code %d)"
                         % (where, sector["size"], sector["id_size_code"]))
        if sector["id_track"] != track["cylinder"]:
            found.append("%s: address field claims track %d, physically on cylinder %d"
                         % (where, sector["id_track"], track["cylinder"]))
        if sector["id_head"] != track["side"]:
            found.append("%s: address field claims head %d, physically on side %d"
                         % (where, sector["id_head"], track["side"]))
        if sector["id_sector"] not in image.standard_ids:
            found.append("%s: sector ID outside the standard 1..%d numbering — not in the .ST"
                         % (where, per_track))
        if not sector["data_in_record"]:
            found.append("%s: data at +%d escapes its own track record — not in the .ST"
                         % (where, sector["data_offset"]))
    return found


def _numbering_anomalies(image, track):
    """Duplicate / missing sector IDs, judged against the disk's standard numbering.

    "Never formatted" and "recorded but never read cleanly" are reported apart, because only
    the second leaves 512 bytes in the image that something could still be recovered from.
    The second set is therefore built from sectors that really *hold* those bytes: a sector
    of the wrong size, one whose slice escapes its record, or one the FDC never found has an
    address field and no content, and claiming otherwise would send a reader hunting for
    bytes Pasti never stored. Those are already named one by one by `_sector_anomalies`.
    """
    found = []
    where = track_label(track)
    counts = Counter(s["id_sector"] for s in track["sectors"])
    for sector_id, count in sorted(counts.items()):
        if count > 1:
            found.append("%s: sector ID %d appears %d times" % (where, sector_id, count))
    recorded = {s["id_sector"] for s in track["sectors"]}
    with_bytes = {s["id_sector"] for s in track["sectors"] if image.has_recorded_data(s)}
    read_cleanly = {s["id_sector"] for s in track["sectors"] if image.is_trusted(s)}
    absent = sorted(image.standard_ids - recorded)
    damaged = sorted((image.standard_ids & with_bytes) - read_cleanly)
    if absent:
        found.append("%s: no sector %s at all — never formatted, nothing recorded"
                     % (where, _id_list(absent)))
    if damaged:
        found.append("%s: sector %s recorded but never read cleanly — its 512 bytes are in"
                     " the image" % (where, _id_list(damaged)))
    return found


def _unformatted_finding(image, track):
    where = track_label(track)
    if track["sector_count"]:
        return ("%s: declares %d sectors but carries no descriptor block (flags 0x%04x)"
                % (where, track["sector_count"], track["flags"]))
    padding = " — past the last formatted cylinder" if track["index"] in image.padding else ""
    return "%s: unformatted (no sectors)%s" % (where, padding)


def protection_report(image):
    """Every anomaly on the disk, in track order, as report lines."""
    lines = []
    for track in image.tracks:
        if not track["sectors"]:
            lines.append(_unformatted_finding(image, track))
            continue
        if track["fuzzy_size"]:
            lines.append("%s: %d fuzzy (unstable) bytes recorded"
                         % (track_label(track), track["fuzzy_size"]))
        lines += _sector_anomalies(image, track)
        lines += _numbering_anomalies(image, track)
    return lines


def print_track_table(image):
    print(TRACK_TABLE_HEADER)
    for track in image.tracks:
        print("%4d %4d %4d %7d  %-16s %6d %6d %6s"
              % (track["index"], track["cylinder"], track["side"], track["sector_count"],
                 sector_size_summary(track), track["fuzzy_size"], track["mfm_size"],
                 track_flags_text(track["flags"])))


def print_summary(image):
    header = image.header
    geometry = image.geometry
    print("HEADER  Pasti v%d, tool %d, revision %d, %d track records, reserved %d/%d"
          % (header["version"], header["tool"], header["revision"], header["track_count"],
             header["reserved1"], header["reserved2"]))
    print("GEOMETRY %d cylinders x %d side(s) x %d sectors/track x %d bytes = %d bytes"
          % (geometry["cylinders"], geometry["sides"], geometry["sectors_per_track"],
             STANDARD_SECTOR_SIZE, geometry["total_sectors"] * STANDARD_SECTOR_SIZE))
    recovered = image.recovered_sectors()
    policy = "strict — a status-flagged sector is never placed" if image.strict else \
             "default — a status-flagged sector is placed, its bytes unverified"
    print("SECTORS %d of %d placed from the image, %d zero-filled; %s"
          % (recovered, geometry["total_sectors"], geometry["total_sectors"] - recovered, policy))


def print_protection(image):
    lines = protection_report(image)
    print("\n--- PROTECTION (%d finding(s); expected on a protected disk, not an error) ---"
          % len(lines))
    for line in lines:
        print("  %s" % line)
    if not lines:
        print("  none — every track is a plain %d-sector format"
              % image.geometry["sectors_per_track"])


def write_st(image, out_path):
    payload = image.st_bytes()
    with open(out_path, "wb") as fh:
        fh.write(payload)
    print("WROTE   %s — %d bytes" % (out_path, len(payload)))


BAD_COMMAND_LINE = (None, None, False)


def _parse_args(args):
    """(image path, out path or None, strict) — or BAD_COMMAND_LINE after printing why."""
    if args[0].startswith("-"):
        sys.stderr.write("%s\n" % USAGE)
        return BAD_COMMAND_LINE
    out_path = None
    strict = False
    rest = args[1:]
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == STRICT_FLAG:
            strict = True
            continue
        if flag != TO_ST_FLAG:
            sys.stderr.write("unexpected argument %r\n%s\n" % (flag, USAGE))
            return BAD_COMMAND_LINE
        if out_path is not None:
            sys.stderr.write("%s given twice\n%s\n" % (TO_ST_FLAG, USAGE))
            return BAD_COMMAND_LINE
        if not rest or not rest[0] or rest[0].startswith("-"):
            sys.stderr.write("%s needs one non-empty output path\n%s\n" % (TO_ST_FLAG, USAGE))
            return BAD_COMMAND_LINE
        out_path, rest = rest[0], rest[1:]
    return args[0], out_path, strict


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    path, out_path, strict = _parse_args(args)
    if path is None:
        return 2
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as err:
        sys.stderr.write("cannot read %s: %s\n" % (path, err))
        return 1
    try:
        image = StxImage(data, strict=strict)
    except ValueError as err:
        sys.stderr.write("%s: not a usable Pasti image: %s\n" % (path, err))
        return 1
    print("IMAGE   %s (%d bytes)" % (path, len(data)))
    print_summary(image)
    if out_path is None:
        print()
        print_track_table(image)
    else:
        try:
            write_st(image, out_path)
        except OSError as err:
            sys.stderr.write("cannot write %s: %s\n" % (out_path, err))
            return 1
    print_protection(image)
    for warning in image.warnings:
        sys.stderr.write("WARNING %s\n" % warning)
    return 1 if image.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
