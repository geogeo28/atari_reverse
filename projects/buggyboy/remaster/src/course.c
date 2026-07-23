/* course.c — remaster of game_update's course advance (section 12, recreate's
 * game_update_course_advance @0x11xxx).
 *
 * One step of "the course scrolls toward you", taken on the frame the view wraps. The original holds
 * the whole course window as a single grid of 0x20-byte rows — one row per distance band — and each
 * step moves every row one band nearer, then refills the far end from the next packed course record.
 * Here that grid is RoadPose.seg_data (row -1, the road's slope column) plus CourseRing (rows 0..13,
 * the scenery / marker bands); scrolling them together is the whole function.
 *
 * What the road sees is the slope column and each band's road width; what the scenery sees is the
 * band's object type codes. Both come out of the same record, which is why the two halves cannot be
 * separated: one row_ctr underflow refills both.
 *
 * Out of scope here (none of it reads or writes the ring): section 12's collision probe, the record's
 * palette / screen-offset event (rm_course_mode_event in events.c, fired by the caller when this
 * returns true), and the fx-block and horizon-event dispatch that follow it.
 *
 * The one hint at the original's flat-image layout: recreate's slope "shift" copies a 16-word window
 * (seg_data plus adjacent scratch), leaving seg_data[11] = the old seg_data[12]; the tail is then
 * overwritten either way, so a plain 12-slot shift reproduces it exactly.
 */
#include "game.h"
#include "st.h"

#define COURSE_ROW_STEP   8        /* row_ctr decrement per step; also the read_pos increment */
#define COURSE_READ_MASK  0x1ff8   /* read_pos wraps within the packed stream */
#define COURSE_SLOPE_BIAS 3        /* new slope = (rec_ctl & 7) - this  (range -3..+4) */
#define COURSE_ROW_RELOAD 0xf8     /* row_ctr reload = rec_ctl & this */
#define SEG_SLOTS         13       /* RoadPose.seg_data entries */

/* The packed course record read here (NEGATIVE offset from the stream base) uses the shared 8-byte
 * RM_REC_* wire layout in game.h — the same layout gameplay.c's init_ring_seed decodes. */

/* A band that no record refilled keeps only these bits of each code — it ages out the type. */
#define RING_CODE_AGE_MASK 0xffc0

/* An animation type code implies its two successors in the next two slots, so the record only has to
 * carry the first of the three. */
#define CODE_IS_ANIM_RUN(c) ((c) == 0x0d || (c) == 0x10 || (c) == 0x13 || (c) == 0x16)
#define CODE_ANIM_RUN_LEN   3

/* A slot-1 code of this value is echoed into slot 13 of the same band. */
#define CODE_ECHOED         0x2e
#define CODE_ECHO_FROM_SLOT 1
#define CODE_ECHO_TO_SLOT   13

/* Marker-word fixups. A signed raw marker takes one of FOUR paths: two named shoulder layouts that
 * each strip a different subset of the EDGE_* flags, a no-shoulder case that strips only the sign,
 * and a fall-through that returns the word untouched — sign included. That last one is not an edge
 * case (400 of the 5120 records across the five legs) and the surviving sign matters: section 10
 * tests `(int16_t)edge < 0` on this very word, reached through the control table, to enable the
 * shoulder clamps and the off-road push. An unsigned marker keeps only its low byte. */
#define MARKER_RAW_FLAG     0x8000   /* sign of a raw record marker; survives only the fall-through */
#define MARKER_KIND_MASK    0xf01e   /* selects the shoulder layout of a signed marker */
#define MARKER_KIND_RIGHT   0xf012   /* right shoulder only */
#define MARKER_KIND_SIDES   0xf000   /* both shoulders, but not driveable */
#define MARKER_LOW_BYTE     0x00ff   /* an unsigned marker keeps this and nothing else */

/* Scroll every band one nearer. The band leaving the near end is dropped; row 0 is refilled after. */
static void ring_scroll(CourseRing *ring) {
    for (int band = RM_RING_ROWS - 1; band > 0; band--)
        ring->row[band] = ring->row[band - 1];
}

/* Strip a raw record marker word down to the EDGE_* flags its shoulder layout keeps. */
static uint16_t marker_unpack(uint16_t raw) {
    if (!(raw & MARKER_RAW_FLAG))
        return (uint16_t)(raw & MARKER_LOW_BYTE);
    if ((raw & MARKER_KIND_MASK) == MARKER_KIND_RIGHT)
        return (uint16_t)(raw & ~(MARKER_RAW_FLAG | EDGE_LEFT | EDGE_OPEN));
    if ((raw & MARKER_KIND_MASK) == MARKER_KIND_SIDES)
        return (uint16_t)(raw & ~(MARKER_RAW_FLAG | EDGE_OPEN));
    if ((raw & (EDGE_LEFT | EDGE_RIGHT)) == 0)
        return (uint16_t)(raw & ~MARKER_RAW_FLAG);
    return raw;                      /* no fixup matched: keep the word verbatim, sign and all */
}

/* Refill the far band from a freshly pulled record: its selected slots' type codes, then its marker.
 *
 * The codes are unpacked through a scratch row because an animation run started in one of the last
 * slots writes past the band's last slot. Started at slot 13 the original's overflow lands on the
 * marker word, which is overwritten immediately after, so discarding it is the same result; started
 * at slot 14 it would reach the NEXT band's first slot, which this does not reproduce. Neither is
 * reachable in the shipped data — over all 5120 records of the five legs the deepest animation code
 * sits at slot 11, so an expansion reaches slot 13 at most. */
static void ring_refill(CourseRow *band, const uint8_t *rec) {
    uint16_t code_slot[RM_RING_SLOTS + CODE_ANIM_RUN_LEN - 1] = {0};
    uint16_t select = be16(rec + RM_REC_SELECT_OFF);
    const uint8_t *code = rec + RM_REC_CODES_OFF;

    for (int slot = 0; slot < RM_RING_SLOTS; slot++) {
        if (!(select & (1u << (RM_RING_SLOTS - 1 - slot))))
            continue;
        uint8_t type = *code++;
        code_slot[slot] = type;
        if (CODE_IS_ANIM_RUN(type)) {
            code_slot[slot + 1] = (uint16_t)(type + 1);
            code_slot[slot + 2] = (uint16_t)(type + 2);
        }
    }
    for (int slot = 0; slot < RM_RING_SLOTS; slot++)
        band->slot[slot] = code_slot[slot];
    if (band->slot[CODE_ECHO_FROM_SLOT] == CODE_ECHOED)
        band->slot[CODE_ECHO_TO_SLOT] = CODE_ECHOED;

    band->marker = marker_unpack(be16(rec + RM_REC_MARKER_OFF));
}

/* Age the far band in place: no record was pulled, so it keeps its marker and merely loses the low
 * bits of each type code. */
static void ring_age(CourseRow *band) {
    for (int slot = 0; slot < RM_RING_SLOTS; slot++)
        band->slot[slot] &= RING_CODE_AGE_MASK;
}

void rm_ring_store_st(const CourseRing *ring, uint8_t *dst) {
    for (int band = 0; band < RM_RING_ROWS; band++, dst += RM_RING_ROW_BYTES) {
        const CourseRow *row = &ring->row[band];
        for (int slot = 0; slot < RM_RING_SLOTS; slot++)
            wr16(dst + slot * 2, row->slot[slot]);
        wr16(dst + RM_RING_SLOTS * 2, row->marker);
    }
}

uint16_t rm_ring_sprite_count(const CourseRing *ring) {
    if ((int16_t)ring->row[0].marker < 0)
        return 0;
    uint16_t count = 0;
    while (count < RM_RING_SPRITE_ROWS && (int16_t)ring->row[count + 1].marker >= 0)
        count++;
    return count;
}

/* draw_ground's marker byte: this slot's low byte (byte 0xf of the serialized row). */
#define RING_GROUND_MARKER_SLOT 7

void rm_ring_ground_markers(const CourseRing *ring, uint8_t *markers) {
    for (int band = 0; band < GROUND_SCAN_ENTRIES; band++)
        markers[band] = (uint8_t)(ring->row[band].slot[RING_GROUND_MARKER_SLOT] & 0xff);
}

uint8_t rm_ring_buggy_gate(const CourseRing *ring) {
    return (uint8_t)(ring->row[RM_RING_GATE_ROW].marker >> 8);
}

int8_t rm_ring_fg_gate(const CourseRing *ring) {
    return (int8_t)(ring->row[RM_RING_GATE_ROW].marker & 0xff);
}

/* Poke one big-endian byte into the live ring at flat grid offset `flat_off`, inverting the
 * rm_ring_store_st mapping: the grid is RM_RING_ROWS rows of 16 words (15 slots + the marker), so a
 * flat offset resolves to (band, word, byte-parity). See RM_RING_OBJ_ACTIVE_OFF in game.h. */
void rm_ring_poke_byte(CourseRing *ring, unsigned flat_off, uint8_t val) {
    unsigned band = flat_off / RM_RING_ROW_BYTES;
    unsigned in_row = flat_off % RM_RING_ROW_BYTES;
    unsigned word = in_row / 2;
    uint16_t *w = (word == RM_RING_SLOTS) ? &ring->row[band].marker : &ring->row[band].slot[word];
    if (in_row & 1) *w = (uint16_t)((*w & 0xff00) | val);                    /* low byte */
    else            *w = (uint16_t)((*w & 0x00ff) | ((uint16_t)val << 8));   /* high byte */
}

bool rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring, const uint8_t *stream) {
    for (int i = 0; i < SEG_SLOTS - 1; i++)          /* scroll the slope column up one slot */
        pose->seg_data[i] = pose->seg_data[i + 1];
    ring_scroll(ring);

    cs->row_ctr = (uint16_t)(cs->row_ctr - COURSE_ROW_STEP);
    if ((int16_t)cs->row_ctr < 0) {
        cs->read_pos = (uint16_t)((cs->read_pos + COURSE_ROW_STEP) & COURSE_READ_MASK);
        const uint8_t *rec = stream - cs->read_pos;  /* records grow downward from the stream base */
        uint8_t rec_ctl = rec[RM_REC_CTL_OFF];
        pose->seg_data[SEG_SLOTS - 1] = (int16_t)((rec_ctl & 7) - COURSE_SLOPE_BIAS);   /* new slope */
        cs->row_ctr = (uint16_t)(rec_ctl & COURSE_ROW_RELOAD);
        ring_refill(&ring->row[0], rec);
        return true;                                 /* record pulled: the caller fires the mode event */
    }
    pose->seg_data[SEG_SLOTS - 1] = pose->seg_data[SEG_SLOTS - 2];   /* keep the previous slope */
    ring_age(&ring->row[0]);
    return false;
}
