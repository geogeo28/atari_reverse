/* os.h — deterministic TOS trap model shared by the oracle (shim.c) and reconstructed
 * OS wrappers. The oracle can't call real TOS, so GEMDOS/BIOS/XBIOS traps are serviced
 * with fixed semantics; a reconstruction must model the SAME return value and image effect
 * for its differential test to hold.
 *
 * Modeled: calls that only touch hardware or files (Setpalette/Setcolor/Setscreen, sound,
 * console I/O, Ikbdws) have NO image effect and return 0. Physbase/Logbase return
 * OS_SCREEN_BASE; Getrez returns 0 (low-res); Malloc bump-allocates from OS_HEAP_BASE;
 * Mshrink/Mfree/Fclose return 0; Fopen returns OS_FILE_HANDLE. XBIOS Supexec runs the
 * passed routine in place (its rts returns to the caller, its D0 becomes the result).
 *
 * DEFERRED (serviced as return 0, effect NOT modeled): GEMDOS Fread (needs a file model),
 * GEMDOS Super, and GEM AES/VDI via trap #2. A function that depends on these cannot be
 * verified until the model is extended — see recreate/README.md. OS_HEAP_BASE/OS_SCREEN_BASE
 * are provisional low-memory arenas that only fit small blocks; functions that Malloc large
 * screen buffers need a larger IMAGE_SIZE first.
 */
#ifndef BB_OS_H
#define BB_OS_H

#define OS_SCREEN_BASE 0x8000u   /* Physbase/Logbase result (in-image screen region) */
#define OS_HEAP_BASE   0x1000u   /* Malloc bump arena start (small blocks only) */
#define OS_FILE_HANDLE 6u        /* Fopen result */

#endif /* BB_OS_H */