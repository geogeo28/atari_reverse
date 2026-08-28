/*
 * render_png.h - host-only PNG output for the golden-frame tests.
 */
#ifndef BLACKICE_RENDER_PNG_H
#define BLACKICE_RENDER_PNG_H

#include <stdint.h>

/*
 * Write a 320x200 indexed-colour PNG of a planar screen, decoding it back
 * through planar_pixel so the file also proves the c2p round-trips.
 * Returns 0 on success.
 */
int render_png_write(const char *path, const uint8_t *planar);

#endif /* BLACKICE_RENDER_PNG_H */
