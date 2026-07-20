/* course.c — remaster of the road-geometry part of game_update's course advance (section 12,
 * recreate's game_update_course_advance @0x11xxx).
 *
 * This is the slice of the per-frame course advance that drives the *rendered road*: as the buggy
 * moves forward, the road segment window (RoadPose.seg_data) scrolls up one slot each step, and when
 * a row counter underflows the next packed course record supplies the new tail slope. Feeding the
 * advanced pose to rm_build_road_geometry makes the road's hills/curves follow the leg's authored
 * track. Verified byte-for-byte (seg_data / row_ctr / read_pos) against recreate's g_game_update over
 * a leg drive; the rest of section 12 (collision, the marker/scenery ring, palette/fx/score events)
 * does not affect the road surface and is out of scope here.
 *
 * The one hint at the original's flat-image layout: recreate's segment "shift" copies a 16-word
 * window (seg_data plus adjacent scratch), leaving seg_data[11] = the old seg_data[12]; the tail is
 * then overwritten either way, so a plain 12-slot shift reproduces it exactly.
 */
#include "game.h"

#define COURSE_ROW_STEP   8        /* row_ctr decrement per step; also the read_pos increment */
#define COURSE_READ_MASK  0x1ff8   /* read_pos wraps within the packed stream */
#define COURSE_SLOPE_BIAS 3        /* new slope = (rec_ctl & 7) - this  (range -3..+4) */
#define COURSE_CTL_OFF    2        /* the control byte's offset within a course record */
#define COURSE_ROW_RELOAD 0xf8     /* row_ctr reload = rec_ctl & this */
#define SEG_SLOTS         13       /* RoadPose.seg_data entries */

void rm_road_course_advance(RoadPose *pose, CourseState *cs, const uint8_t *stream) {
    for (int i = 0; i < SEG_SLOTS - 1; i++)          /* scroll the segment window up one slot */
        pose->seg_data[i] = pose->seg_data[i + 1];

    cs->row_ctr = (uint16_t)(cs->row_ctr - COURSE_ROW_STEP);
    if ((int16_t)cs->row_ctr < 0) {
        cs->read_pos = (uint16_t)((cs->read_pos + COURSE_ROW_STEP) & COURSE_READ_MASK);
        const uint8_t *rec = stream - cs->read_pos;  /* records grow downward from the stream base */
        uint8_t rec_ctl = rec[COURSE_CTL_OFF];
        pose->seg_data[SEG_SLOTS - 1] = (int16_t)((rec_ctl & 7) - COURSE_SLOPE_BIAS);   /* new slope */
        cs->row_ctr = (uint16_t)(rec_ctl & COURSE_ROW_RELOAD);
    } else {
        pose->seg_data[SEG_SLOTS - 1] = pose->seg_data[SEG_SLOTS - 2];   /* keep the previous slope */
    }
}
