/* render.c — the remaster render entry point (the seam the equivalence harness calls).
 *
 * rm_render_frame() is Phase A's contract: given native game state, produce the 320x200 ST
 * framebuffer that must come out pixel-identical to recreate's render pipeline (render_road +
 * blit_road_scroll + draw_game_objects + draw_hud). Right now it is a STUB that clears the screen —
 * it exists so the build, the .so export, and the harness seam are real. Each subsystem lands here
 * (or in its own src file called from here) one at a time, green under the equivalence harness.
 */
#include <string.h>

#include "game.h"
#include "screen.h"

void rm_render_frame(const GameState *state, Framebuffer *fb) {
    (void)state;                 /* TODO(phase-A): road, objects, HUD read from state */
    memset(fb->px, 0, SCREEN_BYTES);
}
