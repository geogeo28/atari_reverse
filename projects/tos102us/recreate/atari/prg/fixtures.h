/* fixtures.h — the data files the two conformance floppies carry: their names, their sizes and the
 * pattern their bytes follow.
 *
 * ONE SPEC, TWO READERS, AND THEY RUN ON DIFFERENT MACHINES. `../mkdata.py` writes these files on
 * the host at build time (it parses this header, so the spec is not restated in Python), and
 * TOSBENCH opens and reads one of them on the target. A name or a size that drifted between the two
 * would not fail a build: it would fail as a `Fopen` returning -33 inside a timed workload, or —
 * worse — as a read that returned fewer bytes than the bench believed it asked for and therefore a
 * timing that is about a shorter file.
 *
 * THE NAMES ARE DISTINCT IN THEIR FIRST EIGHT CHARACTERS, which is what a ledger record's blob
 * holds (ledger.h, LEDGER_BLOB_BYTES): `ALPHA.DA`, `BETA.DAT`, `DATA64K.`. A directory walk that
 * returned the entries in a different order is then visible in the records rather than hidden by
 * truncation.
 *
 * THE CONTENTS ARE A COUNTER, NOT ZEROES, and FIXTURE_PATTERN_PERIOD is why it is 251: a prime,
 * therefore coprime with both the 512-byte sector and the 1,024-byte cluster, so a chunk delivered
 * from the wrong place cannot read back correctly. A run of zeroes would read back correctly from a
 * driver that never issued the read at all.
 */
#ifndef TOS102US_FIXTURES_H
#define TOS102US_FIXTURES_H

/* The byte at offset N is N modulo this. */
#define FIXTURE_PATTERN_PERIOD  251

/* Two small files, present only so the directory walk has more than one entry to return. */
#define FIXTURE_ALPHA_NAME      "ALPHA.DAT"
#define FIXTURE_ALPHA_BYTES     16
#define FIXTURE_BETA_NAME       "BETA.DAT"
#define FIXTURE_BETA_BYTES      300

/* TOSBENCH's read workload: 64 KB, read in 8 KB chunks — sixteen sectors a chunk, and therefore
 * several cluster and track boundaries inside the timed span. */
#define FIXTURE_DATA_NAME       "DATA64K.BIN"
#define FIXTURE_DATA_BYTES      65536

#endif /* TOS102US_FIXTURES_H */
