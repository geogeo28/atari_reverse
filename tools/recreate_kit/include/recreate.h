/* recreate.h — how a reconstruction says "this arm is not reconstructed", without returning.
 *
 * A reconstruction is not always a whole routine. An OS entry dispatches: TOS's `Bconstat` walks a
 * table of eight device drivers and jumps into one, and `Cursconf` jumps through eight arms of the
 * console driver — and a wave reconstructs the arms it can run, not all of them. The arms it did
 * not are the hazard. An arm that RETURNS a value is indistinguishable, to every case and to every
 * caller, from one that was reconstructed: the number it hands back is the reconstruction's own
 * invention, and a case that reached it would be verified against that invention rather than
 * against the original. So an unreconstructed arm must not return at all.
 *
 * `recreate_not_reconstructed(what)` is that halt. `what` names the arm, for a reader who hits it.
 *
 * IT IS THE SAME PROGRAM ON BOTH BUILDS, which is what kit.mk's RECREATE_HOST_DIFFERENTIAL rule
 * requires of anything keyed on that macro ("nothing behavioural may hang off it, or the two builds
 * would stop being the same program"). Neither build returns; they differ only in what they can SAY
 * on the way down. The host differential runs inside a process with a stderr and an `abort()`, so it
 * names the arm and aborts — the same ending `assert(0)` has always had here. The target has
 * neither, so it traps: GCC lowers `__builtin_trap()` on the 68000 to `trap #7`, which the machine
 * takes through vector $9c into whatever the OS installed there. Both are "control does not come
 * back", which is the property the caller and the case depend on.
 *
 * It is DELIBERATELY not an `assert`. An assert is a statement that something cannot happen, which
 * a NULL-check or a bound is; this is a statement that something has not been WRITTEN, and the two
 * read very differently at a call site — an assert invites `-DNDEBUG`, where compiling this one out
 * would turn a halt into a fall-through past the end of a value-returning function.
 */
#ifndef RECREATE_KIT_RECREATE_H
#define RECREATE_KIT_RECREATE_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <stdio.h>
#include <stdlib.h>
#endif

/* `noreturn` is load-bearing rather than documentation: it is what lets a value-returning function
 * end on this call with no `return` after it — which is the whole point, since any value written
 * there would be the fabrication this exists to prevent — without tripping -Wreturn-type under the
 * target build's -Werror. */
#define RECREATE_NORETURN __attribute__((noreturn))

#ifdef RECREATE_HOST_DIFFERENTIAL
static inline RECREATE_NORETURN void recreate_not_reconstructed(const char *what)
{
    fprintf(stderr, "recreate: not reconstructed: %s\n", what);
    abort();
}
#else
static inline RECREATE_NORETURN void recreate_not_reconstructed(const char *what)
{
    (void)what;     /* no stderr on the machine: the trap is the whole report */
    __builtin_trap();
}
#endif

#endif /* RECREATE_KIT_RECREATE_H */
