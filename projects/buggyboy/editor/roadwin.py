"""roadwin.py — a real graphical window that DRIVES BuggyBoy through the verified reconstruction.

This is the whole game running: each frame injects your held keys as input_state, calls the
verified g_game_update + g_draw_frame, and blits the resulting ST framebuffer (game palette) to a
scaled pygame window. The road, roadside object SPRITES, the buggy and the HUD are all the game's
own verified rendering — nothing is faked or overlaid.

    mlenv python roadwin.py --leg 0

    arrows / WASD  accelerate / brake / steer     space  fire
    [ / ]          previous / next leg (restart)  r  restart leg
    p              save a PNG of the current frame  esc / q  quit

Needs pygame + numpy + the built recreate/build/libbuggyboy.so (run `make` in recreate/ once).
"""
from __future__ import annotations

import sys

import numpy as np
import pygame

import roadview as rv

SCALE = 3                     # window = 320*SCALE x 200*SCALE
W, H = rv.rs.W, rv.rs.H
FPS = 30
LAST_LEG = 4


def indices_to_surface(idx, pal):
    """(H,W) palette indices + 16-colour palette -> a pygame Surface (unscaled 320x200)."""
    lut = np.array(pal, dtype=np.uint8)                       # 16 x 3
    rgb = lut[idx]                                            # H x W x 3
    return pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))   # make_surface wants (W,H,3)


def frame_indices(image):
    rows = rv.rs._decode_interleaved(image, rv.rs.SCREEN_BASE)
    return np.frombuffer(b"".join(bytes(r) for r in rows), dtype=np.uint8).reshape(H, W) & 0xF


def held_input(keys) -> int:
    bits = 0
    if keys[pygame.K_UP] or keys[pygame.K_w]:
        bits |= rv.IN_ACCEL
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        bits |= rv.IN_BRAKE
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        bits |= rv.IN_LEFT
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        bits |= rv.IN_RIGHT
    if keys[pygame.K_SPACE]:
        bits |= rv.IN_FIRE
    return bits


def main(argv):
    leg = int(argv[argv.index("--leg") + 1]) if "--leg" in argv else 0

    pygame.init()
    screen = pygame.display.set_mode((W * SCALE, H * SCALE))
    pygame.display.set_caption("BuggyBoy — verified reconstruction")
    font = pygame.font.SysFont("monospace", 16)
    clock = pygame.time.Clock()

    session = rv.GameSession(leg)
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif e.key == pygame.K_r:
                    session.reset(leg)
                elif e.key == pygame.K_RIGHTBRACKET:
                    leg = min(LAST_LEG, leg + 1); session.reset(leg)
                elif e.key == pygame.K_LEFTBRACKET:
                    leg = max(0, leg - 1); session.reset(leg)
                elif e.key == pygame.K_p:
                    out = rv.default_out() / f"drive_leg{leg}.png"
                    rv.write_png(session.image, out)

        image = session.step(held_input(pygame.key.get_pressed()))
        surface = indices_to_surface(frame_indices(image), session.palette())
        screen.blit(pygame.transform.scale(surface, (W * SCALE, H * SCALE)), (0, 0))
        screen.blit(font.render(f"leg {leg}", True, (255, 255, 255), (0, 0, 0)), (4, 4))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
