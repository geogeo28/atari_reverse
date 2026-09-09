/* bubble_mfdb.h — the ONE place the kit's and the game's MFDB field offsets are reconciled.
 *
 * `MFDB_ADDR` and `MFDB_WDWIDTH` are spelt twice in this build's include closure: the kit's `os.h`
 * names the GEM Memory Form Definition Block's fields for its software VDI, and `../include/blit.h`
 * names them for the game's own binding. `bubble_main.c` is the only translation unit in the tree
 * that includes both, so the redefinition is its to deal with — and since wave 5a the GEM door is
 * assembly and takes the KIT's spelling straight from `build.sh`'s two-language loop, which is what
 * makes the assertion below the only thing left holding the two sides of the number together.
 *
 * A BARE `#undef` PAIR WOULD HIDE A REAL BUG, which is why this file exists instead of one. The two
 * headers agree today (0 and 8); if `blit.h` ever stopped agreeing with the kit, the cores and this
 * build's GEM door would read a raster pointer from different offsets and the VDI would copy from
 * the wrong address. So the kit's values are CAPTURED, `blit.h` is let in, and the two are pinned
 * equal — one assertion in place of two blind `#undef`s.
 *
 * Resolving the duplicate properly is the PROJECT's change — one of the two headers stops naming
 * the fields — and not this directory's (CLAUDE.md §3).
 *
 * ANGLE FORM ON BOTH INCLUDES: docs/on-target-execution.md class 12b. A quoted include from inside
 * `shim_include/` is found by this file's own directory first, which is not where either header is.
 */
#ifndef BUBBLEGHOST_SHIM_MFDB_H
#define BUBBLEGHOST_SHIM_MFDB_H

#include <os.h>      /* the kit's spelling, through the shadow beside this file */

enum { KIT_MFDB_ADDR = MFDB_ADDR, KIT_MFDB_WDWIDTH = MFDB_WDWIDTH };

#undef MFDB_ADDR
#undef MFDB_WDWIDTH
#include <blit.h>    /* ...and the game's, which is what every reader below this line gets */

_Static_assert(MFDB_ADDR == KIT_MFDB_ADDR && MFDB_WDWIDTH == KIT_MFDB_WDWIDTH,
               "../include/blit.h and the kit's os.h no longer agree about where the MFDB keeps its "
               "raster pointer and its width, so the cores and this build's GEM door would read "
               "them from different offsets");

#endif /* BUBBLEGHOST_SHIM_MFDB_H */
