/* asm_twin.h — the one marker `atari/build.sh`'s asm-twin gate reads out of the headers.
 *
 * A TWIN THAT IS VERIFIED BUT DELIBERATELY NOT SHIPPED. Expands to nothing; the gate scrapes it off
 * the declaration line and moves that twin from its "must be called" arm to a "must NOT be called"
 * one, and keeps the twin's object off the link line entirely.
 *
 * IT IS A DECLARED CATEGORY RATHER THAN AN OMISSION, precisely because the gate's whole purpose is
 * to notice a twin the build stopped calling — that failure is silent (the game stays correct and
 * gets slower), so "we meant that" has to be written down where the gate can read it.
 *
 * WHY IT LIVES IN A HEADER OF ITS OWN, and not beside the twins that use it. `build.sh` GLOBS
 * `include/*.h` for the marker, so the category is build-wide by construction — but this
 * workspace's subsystem headers are standalone, each including only <stdint.h>. Defined in
 * `frame.h`, the marker was unreachable from `sprite.h`: marking a sprite twin gave
 * `error: expected ';' before 'void'` (measured). The alternatives were a second `#define` per
 * header, which CLAUDE.md's one-canonical-definition rule forbids and which lets two spellings
 * drift apart silently, or making one subsystem header include an unrelated one. This file is the
 * shared definition both of those work around.
 *
 * USAGE — the marker OPENS the line, and the gate requires that (`^ZY_TWIN_VERIFICATION_ONLY`), so
 * that neither the `#define` below nor prose citing the macro is scraped as a declaration:
 *
 *     ZY_TWIN_VERIFICATION_ONLY void my_core_asm(uint8_t *image);
 *
 * A multi-line prototype puts the marker and the NAME on its first line: the gate pairs them by
 * taking the first `..._asm(` after the marker on that one line.
 */
#ifndef ZYNAPS_ASM_TWIN_H
#define ZYNAPS_ASM_TWIN_H

#define ZY_TWIN_VERIFICATION_ONLY

#endif /* ZYNAPS_ASM_TWIN_H */
