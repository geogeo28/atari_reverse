/* entity.c — the entity-record housekeeping.
 *
 * entity_kill_if_offscreen @ 0x13c9e: the tail of an entity's per-frame update. Three call sites
 * (0x11a1e, 0x11bd8, 0x11bfa) run it over the 0x2c-byte records the enemy loop at 0x119ee walks
 * (`lea 44(a2),a2` / `dbf d7`), so an entity that has wandered outside the playfield box stops
 * being alive.
 */
#include "machine.h"
#include "entity.h"

/* The box an entity must be strictly inside to stay alive. All four comparisons are signed, and
 * both pairs are exclusive at BOTH ends (`ble`/`bge` on x, `ble`/`blt` on y), so the live band is
 * 0x31..0x17f by x and 0x11..0xaf by y. */
#define ENTITY_KEEP_X_MIN 0x30
#define ENTITY_KEEP_X_MAX 0x180
#define ENTITY_KEEP_Y_MIN 0x10
#define ENTITY_KEEP_Y_MAX 0xb0

/* THE GUARD READS TWO FIELDS AT ONCE, and the kill writes only one. `tst.w 14(a2)` spans
 * ENTITY_ALIVE and its neighbour ENTITY_PIXEL_HIT, so the routine proceeds while EITHER byte is
 * set; `clr.b 14(a2)` then clears the alive byte alone and leaves the pixel-hit flag standing.
 * Reproduced exactly. Whether the wide read is deliberate or a slip is not decidable from this
 * routine — but it is also not OBSERVABLE from it: on the records the two spellings disagree about
 * (alive already 0, pixel-hit set) the clear writes 0 over a 0. See STATUS.md's mutation ledger. */
void entity_kill_if_offscreen(uint8_t *image, uint32_t entity) {
    if (be16(image + entity + ENTITY_ALIVE) == 0)
        return;                                  /* already dead — the box is never consulted */

    int16_t x = (int16_t)be16(image + entity + ENTITY_X);
    int16_t y = (int16_t)be16(image + entity + ENTITY_Y);
    if (x > ENTITY_KEEP_X_MIN && x < ENTITY_KEEP_X_MAX
        && y > ENTITY_KEEP_Y_MIN && y < ENTITY_KEEP_Y_MAX)
        return;

    image[entity + ENTITY_ALIVE] = 0;
}

/* Register map: A2 = the entity record. No outputs but the record itself. */
void g_entity_kill_if_offscreen(uint8_t *image, uint32_t entity) {
    entity_kill_if_offscreen(image, entity);
}
