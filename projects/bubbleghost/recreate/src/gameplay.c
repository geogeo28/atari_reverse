/* gameplay.c — the in-room simulation: the ghost, the blow, the bubble and the castle's tables.
 *
 * `game_frame_update` @ 0x12322 is the whole of one frame, and everything here is either it, one
 * of the routines it calls, or the world bookkeeping around it. `../notes/gameplay.md` is the
 * design doc and `include/gameplay.h` the frozen record layout; neither is restated here.
 *
 * `game_frame_update` IS PORTED AS NINE SLICES rather than as one function
 * (docs/agent-playbook.md §5), because it never runs straight through: the routine polls the front
 * end, and one of its arms — the `^P` pause — spins until a key arrives that no case can stage.
 * Each slice is entered at its own PC by `test/test_gameplay.py` and diffed at the next one's, so
 * what is verified is exactly the straight-line region the core covers.
 *
 * TWO OF THE NINE ARE NOT ADJACENT TO THE OTHERS, and both are worth knowing before reading them:
 *
 *   * `frame_poll_input` `[0x1233a, 0x12434)` is the front-end poll — `vq_mouse`, `vq_key_s` and
 *     one `Crawio(0xff)` — and it ANSWERS whether the key was `^P` rather than falling into
 *     `frame_poll_pause`, which is the one region here no case can run.
 *   * `frame_death_sequence` `[0x1273c, 0x1294a)` is NESTED inside `frame_step_live_bubble`'s
 *     slice: that slice's cases stop where it begins, and its own cases run it.
 *
 * The composition — the order the nine run in — is read-verified; STATUS.md carries that residual.
 */
#include "machine.h"

#include "blit.h"       /* the two screens and the screen geometry `get_pixel` reads through */
#include "clib.h"       /* c_ldiv / c_strlen, the fp package, and the trap trampoline's slots */
#include "common.h"     /* muls_ext_w — the `muls.w` + `ext.l` every table index here is — and
                        * `GlobalsBase`, the a4 this file's frame path reaches its globals off */
#include "frontend.h"   /* the input block the mouse poll and the key poll fill */
#include "gameplay.h"
#include "sound.h"      /* the trigger API a blow, a pop and a candle reach */

/* THE TOS MODEL, for the front-end poll's three GEMDOS console calls and the death sequence's
 * XBIOS `Random`. It also spells the MFDB record, which `include/blit.h` above spells as the
 * GAME's own — and two of the six names collide (`MFDB_ADDR`, `MFDB_WDWIDTH`). NOTHING IN THIS FILE
 * READS AN MFDB, so the game's six are dropped rather than reconciled: reconciling them is
 * `src/frontend.c`'s job, and it is the one translation unit that means both records. */
#undef MFDB_ADDR
#undef MFDB_WIDTH
#undef MFDB_HEIGHT
#undef MFDB_WDWIDTH
#undef MFDB_STANDARD
#undef MFDB_PLANES
#include "os.h"

/* Reading and writing the game's word globals is `include/common.h`'s `word_at`/`set_word`; only
 * the LONG reader below is this file's, since nothing else needs one. */
static int32_t long_at(const uint8_t *image, uint32_t address) {
    return (int32_t)be32(image + address);
}

/* ================================================================================================
 * get_pixel @ 0x13bea — the whole of the game's hazard sensing
 *
 * Four plane words of one 16-pixel cell, assembled into a colour index. It reads `screen_back`
 * with no clipping and no bounds test at all, so an (x, y) outside the buffer reads whatever lies
 * there — which is why this battery is also run under `make guarded`.
 * ============================================================================================= */

int16_t get_pixel(const uint8_t *image, int16_t x, int16_t y) {
    /* `divs.w #$10` truncates toward zero, so a negative x lands on the cell to its RIGHT and the
     * bit index below goes past 15 — where the `btst` finds the plane word's zero-extended high
     * half and answers 0. Transcribed rather than clamped: it is what the original reads. */
    int16_t cell = (int16_t)(x / PIXELS_PER_WORD);
    uint32_t plane_words = addr_add(addr_add(be32(image + A_screen_back),
                                             muls_ext_w(y, SCREEN_ROW_BYTES)),
                                    muls_ext_w(cell, PLANE_WORD_BYTES));
    /* `move.w #$f,d6 / sub.w` — a WORD subtraction, and `btst Dn,Dm` takes the count modulo 32. */
    unsigned bit = (unsigned)(int16_t)(PIXEL_MSB - (int16_t)(x - (int16_t)(cell * PIXELS_PER_WORD)))
                   & 31u;
    int16_t colour = 0;

    for (unsigned plane = 0; plane < SCREEN_PLANES; plane++) {
        /* The plane word is loaded into a register the routine CLEARED first, so bits 16..31 are
         * zero and a bit index of 16 or more reads 0 rather than the neighbouring word. */
        uint32_t word = be16(image + addr_add(plane_words, 2u * plane));
        if ((word >> bit) & 1u)
            colour = (int16_t)(colour + (1 << plane));
    }
    return colour;
}

/* ================================================================================================
 * bubble_collision_probe @ 0x13004 — eight rim probes, one phase per frame
 *
 * There is no geometry in this game: the bubble pops on any non-background pixel under one of
 * eight offsets read out of `probe_table`. The work buffer at this moment holds the room and its
 * objects but not the two sprites, which is why an object is a hazard and the ghost is not.
 * ============================================================================================= */

void bubble_collision_probe(uint8_t *image) {
    /* The phase is stepped BEFORE it is used and the wrap tests the value the frame arrived with,
     * so the phases actually probed run 1, 2, 3, 4, 5, 0 rather than 0..5. A phase outside that
     * range simply keeps counting up — the test is `== PROBE_PHASES - 1`, not `>=`. */
    int16_t previous = word_at(image, A_probe_phase);
    int16_t phase;
    unsigned probe;

    set_word(image, A_probe_phase, (int16_t)(previous + 1));
    if (previous == (int16_t)PROBE_PHASES - 1)
        set_word(image, A_probe_phase, 0);
    phase = word_at(image, A_probe_phase);

    for (probe = 0; probe < PROBES; probe++) {
        /* The probe's own offset is folded into the `lea`, so it is added in 32 bits; only the
         * PHASE offset goes through an `adda.w` and is truncated to a word. */
        uint32_t pair = addr_add(A_probe_table + probe * PROBE_STRIDE,
                                 muls_ext_w(phase, PROBE_PHASE_STRIDE));
        int16_t x = (int16_t)(word_at(image, A_bubble_x) + word_at(image, pair + PROBE_DX));
        int16_t y = (int16_t)(word_at(image, A_bubble_y) + word_at(image, pair + PROBE_DY));

        if (get_pixel(image, x, y) != 0) {
            set_word(image, A_bubble_alive, 0);
            set_word(image, A_bubble_frame, BUBBLE_POPPED_FRAME);
            return;
        }
    }
}

/* ================================================================================================
 * The world block — reset_world_state @ 0x10f20, save_world_p{1,2}, restore_world_p{1,2}
 *
 * All five routines walk ONE list: the 58 table cells a blown-out candle mutates, over the ten
 * rooms that have one. `reset_world_state` is 174 straight-line stores — each value written to the
 * live cell and to the same slot of BOTH players' blocks — and the four save/restore routines are
 * the same list as `move.w` pairs, so the list is written down once here and driven four ways.
 *
 * THE BLOCK IS FILLED BACKWARDS. Entry 0 of the list below is the block's LAST word, which is what
 * the descending displacements of `save_world_p1` say; `world_block_slot` is that one fact.
 * ============================================================================================= */

typedef struct {
    uint32_t address;   /* the live table cell */
    uint16_t reset;     /* what `reset_world_state` puts there — the "candle lit" default */
} WorldCell;

/* Read off the 58 `move.w #imm,d0 / move.w d0,live / move.w d0,p2 / move.w d0,p1` triples of
 * `reset_world_state` @ 0x10f20, in the order it writes them, and cross-checked against the 58
 * `move.w` pairs of `save_world_p1` @ 0x13ff4 (same live cells, same order) and of
 * `restore_world_p1` @ 0x13d2c (the same pairs reversed). */
static const WorldCell WORLD_CELLS[WORLD_BLOCK_WORDS] = {
    { 0x22b4eu, 0x0004u },   /*  0  candle[3][0]        = 4    */
    { 0x21be4u, 0x00a7u },   /*  1  room[3].map[2][5]   = 167  */
    { 0x21bf8u, 0x00a2u },   /*  2  room[3].map[3][5]   = 162  */
    { 0x20876u, 0x00a2u },   /*  3  object[3][4].tile   = 162  */
    { 0x20884u, 0xffffu },   /*  4  object[3][5].tile   = -1   */
    { 0x20892u, 0x00a7u },   /*  5  object[3][6].tile   = 167  */
    { 0x208a0u, 0xffffu },   /*  6  object[3][7].tile   = -1   */
    { 0x22b5au, 0x0005u },   /*  7  candle[4][0]        = 5    */
    { 0x21c48u, 0x00a7u },   /*  8  room[4].map[1][5]   = 167  */
    { 0x21c5cu, 0x00a2u },   /*  9  room[4].map[2][5]   = 162  */
    { 0x20910u, 0x00a2u },   /* 10  object[4][5].tile   = 162  */
    { 0x2091eu, 0xffffu },   /* 11  object[4][6].tile   = -1   */
    { 0x2092cu, 0x00a7u },   /* 12  object[4][7].tile   = 167  */
    { 0x2093au, 0xffffu },   /* 13  object[4][8].tile   = -1   */
    { 0x22b66u, 0x0005u },   /* 14  candle[5][0]        = 5    */
    { 0x21cd2u, 0x00dcu },   /* 15  room[5].map[2][4]   = 220  */
    { 0x21cd6u, 0x00beu },   /* 16  room[5].map[2][6]   = 190  */
    { 0x20980u, 0x00dcu },   /* 17  object[5][3].tile   = 220  */
    { 0x2098eu, 0xffffu },   /* 18  object[5][4].tile   = -1   */
    { 0x2099cu, 0x00beu },   /* 19  object[5][5].tile   = 190  */
    { 0x209aau, 0xffffu },   /* 20  object[5][6].tile   = -1   */
    { 0x22b8au, 0x0005u },   /* 21  candle[8][0]        = 5    */
    { 0x21e40u, 0x00dcu },   /* 22  room[8].map[2][7]   = 220  */
    { 0x21e56u, 0x00beu },   /* 23  room[8].map[3][8]   = 190  */
    { 0x20b24u, 0x00dcu },   /* 24  object[8][3].tile   = 220  */
    { 0x20b32u, 0xffffu },   /* 25  object[8][4].tile   = -1   */
    { 0x20b40u, 0x00beu },   /* 26  object[8][5].tile   = 190  */
    { 0x20b4eu, 0xffffu },   /* 27  object[8][6].tile   = -1   */
    { 0x22b96u, 0x0004u },   /* 28  candle[9][0]        = 4    */
    { 0x21ec6u, 0x0154u },   /* 29  room[9].map[3][4]   = 340  */
    { 0x21eceu, 0x0078u },   /* 30  room[9].map[3][8]   = 120  */
    { 0x20ba2u, 0x0154u },   /* 31  object[9][2].tile   = 340  */
    { 0x20bb0u, 0xffffu },   /* 32  object[9][3].tile   = -1   */
    { 0x20bbeu, 0x0078u },   /* 33  object[9][4].tile   = 120  */
    { 0x20bccu, 0xffffu },   /* 34  object[9][5].tile   = -1   */
    { 0x22bc6u, 0x0002u },   /* 35  candle[13][0]       = 2    */
    { 0x22092u, 0x0120u },   /* 36  room[13].map[2][4]  = 288  */
    { 0x20dd2u, 0x0120u },   /* 37  object[13][2].tile  = 288  */
    { 0x20de0u, 0xffffu },   /* 38  object[13][3].tile  = -1   */
    { 0x22bd2u, 0x0004u },   /* 39  candle[14][0]       = 4    */
    { 0x220f2u, 0x0128u },   /* 40  room[14].map[1][2]  = 296  */
    { 0x20e7au, 0x0128u },   /* 41  object[14][4].tile  = 296  */
    { 0x20e88u, 0xffffu },   /* 42  object[14][5].tile  = -1   */
    { 0x22beau, 0x0004u },   /* 43  candle[16][0]       = 4    */
    { 0x221e6u, 0x00b6u },   /* 44  room[16].map[1][4]  = 182  */
    { 0x20f92u, 0x00b6u },   /* 45  object[16][4].tile  = 182  */
    { 0x20fa0u, 0xffffu },   /* 46  object[16][5].tile  = -1   */
    { 0x22c0eu, 0x0004u },   /* 47  candle[19][0]       = 4    */
    { 0x22374u, 0x00b9u },   /* 48  room[19].map[3][3]  = 185  */
    { 0x22354u, 0x007bu },   /* 49  room[19].map[1][7]  = 123  */
    { 0x21136u, 0x007bu },   /* 50  object[19][4].tile  = 123  */
    { 0x21144u, 0xffffu },   /* 51  object[19][5].tile  = -1   */
    { 0x21152u, 0x00b9u },   /* 52  object[19][6].tile  = 185  */
    { 0x21160u, 0xffffu },   /* 53  object[19][7].tile  = -1   */
    { 0x22c56u, 0x0007u },   /* 54  candle[25][0]       = 7    */
    { 0x22644u, 0x0079u },   /* 55  room[25].map[3][3]  = 121  */
    { 0x214a8u, 0x0079u },   /* 56  object[25][7].tile  = 121  */
    { 0x214b6u, 0xffffu },   /* 57  object[25][8].tile  = -1   */
};

/* Entry `index` of the list above is the block's word `WORLD_BLOCK_WORDS - 1 - index`. */
static uint32_t world_block_slot(uint32_t block, unsigned index) {
    return block + (WORLD_BLOCK_WORDS - 1u - index) * WORLD_BLOCK_CELL_BYTES;
}

/* reset_world_state @ 0x10f20 — the "all candles lit" defaults into the live tables AND into both
 * players' blocks, once per new game. */
void reset_world_state(uint8_t *image) {
    unsigned index;

    for (index = 0; index < WORLD_BLOCK_WORDS; index++) {
        uint16_t value = WORLD_CELLS[index].reset;

        wr16(image + WORLD_CELLS[index].address, value);
        wr16(image + world_block_slot(A_p2_world_block, index), value);
        wr16(image + world_block_slot(A_p1_world_block, index), value);
    }
}

/* save_world_p1 @ 0x13ff4 / save_world_p2 @ 0x14158 — live cells into one player's block. The two
 * differ only in the block they name, so they are one core called with the block address. */
void save_world(uint8_t *image, uint32_t block) {
    unsigned index;

    for (index = 0; index < WORLD_BLOCK_WORDS; index++)
        wr16(image + world_block_slot(block, index), be16(image + WORLD_CELLS[index].address));
}

/* restore_world_p1 @ 0x13d2c / restore_world_p2 @ 0x13e90 — and the same list the other way. */
void restore_world(uint8_t *image, uint32_t block) {
    unsigned index;

    for (index = 0; index < WORLD_BLOCK_WORDS; index++)
        wr16(image + WORLD_CELLS[index].address, be16(image + world_block_slot(block, index)));
}

/* ================================================================================================
 * itoa_padded @ 0x114ee — (value, buffer, width) -> zero-padded decimal, then reversed
 *
 * The digits come out least-significant first, the field is padded to `width` with '0', the buffer
 * is NUL-terminated and then reversed in place. Every HUD counter is drawn through it.
 * ============================================================================================= */

void itoa_padded(uint8_t *image, int32_t value, uint32_t buffer, int16_t width) {
    /* The original keeps `buffer`, the digit count and the two reversal cursors in its own frame
     * and reloads each before every use, so a `buffer` overlapping that frame would steer it and
     * not this. Every caller's buffer is a local of ITS frame — `hud_draw_counters`' four are —
     * and the differential drops the stack band anyway, so the difference is unobservable here;
     * recorded rather than reproduced. */
    int16_t length = 0;
    int16_t head, tail;

    do {
        uint32_t quotient, remainder;

        /* The original calls `c_ldiv` TWICE per digit with the same arguments — once to take the
         * remainder off the stack, once to take the quotient — because the compiler had nowhere to
         * keep the pair. `c_ldiv` is pure, so one call answering both is the same arithmetic. */
        c_ldiv(DECIMAL_RADIX, (uint32_t)value, &quotient, &remainder);
        image[addr_add(buffer, sign_ext16((uint32_t)length))] = (uint8_t)(remainder + ASCII_ZERO);
        length = (int16_t)(length + 1);
        value = (int32_t)quotient;
    } while (value > 0);

    while (length < width) {
        image[addr_add(buffer, sign_ext16((uint32_t)length))] = (uint8_t)ASCII_ZERO;
        length = (int16_t)(length + 1);
    }
    image[addr_add(buffer, sign_ext16((uint32_t)length))] = 0;

    /* The reversal re-measures the string with `c_strlen` rather than reusing `length`, and keeps
     * the result in a WORD — so a buffer longer than 65,535 bytes would reverse the wrong span.
     * Transcribed as the `subq.w #1` it is. */
    head = 0;
    tail = (int16_t)((uint16_t)c_strlen(image, buffer) - 1u);
    while (head < tail) {
        uint32_t low = addr_add(buffer, sign_ext16((uint32_t)head));
        uint32_t high = addr_add(buffer, sign_ext16((uint32_t)tail));
        uint8_t swap = image[low];

        image[low] = image[high];
        image[high] = swap;
        head = (int16_t)(head + 1);
        tail = (int16_t)(tail - 1);
    }
}

/* ================================================================================================
 * ghost_blow @ 0x129b4 — the eight-direction blow test, and the candle script behind it
 *
 * Called once per blowing frame. It always makes the puff sound, then works out whether the
 * bubble is inside the cone the ghost is facing, and finally whether the room's candle is inside a
 * much tighter window to the ghost's left.
 *
 * `ghost_blow_body` IS THE SLICE `[0x129b4, 0x12ff8)` — everything but the two redraws the candle
 * script ends with (`hud_draw_counters` @ 0x113d2 and `present_score_strip` @ 0x131f0). The score
 * this routine awards IS in the slice; only the drawing of it is not.
 * ============================================================================================= */

#define BLOW_VOICE          1       /* `move.w #$1,-(a7)` @ 0x129b8 and its siblings */
#define BLOW_SFX            3       /* snd_def_fx[3] @ 0x2031a — `pea -19456(a4)` @ 0x129de */
#define BLOW_VOLUME_STEP    8       /* `muls.w #$8` @ 0x129d4: the volume index, scaled by
                                     * sound_enabled so that ^S silences every trigger */
#define BLOW_SFX_NOTE       250     /* `move.w #$fa,-(a7)` @ 0x129cc */
#define BLOW_SFX_PRIORITY   5       /* `move.w #$5,-(a7)` @ 0x129c8 */
#define CANDLE_SFX_FIRST    5       /* `pea -19232(a4)` @ 0x12e14 = snd_def_fx[5]: the ten candle
                                     * rooms' sfx indices select from there on */
#define CANDLE_VOLUME_STEP  13      /* `muls.w #$d` @ 0x12df2 */
#define CANDLE_SFX_NOTE     (-1)    /* `move.w #$ffff,-(a7)` @ 0x12dee */
#define CANDLE_SFX_PRIORITY 10      /* `move.w #$a,-(a7)` @ 0x12dea */

/* The eight values `blow_facing_plus1` takes. It is `(ghost_tile + 1) / 5`, so it is the ghost's
 * facing PLUS ONE — the compiler switched on the quotient rather than on the facing. */
#define FACING_INDEX_LEFT        1
#define FACING_INDEX_DOWN_LEFT   2
#define FACING_INDEX_DOWN        3
#define FACING_INDEX_DOWN_RIGHT  4
#define FACING_INDEX_RIGHT       5
#define FACING_INDEX_UP_RIGHT    6
#define FACING_INDEX_UP          7
#define FACING_INDEX_UP_LEFT     8

/* The four orthogonal facings: a minimum distance along the facing's own axis, and a band across
 * it. The band is LOPSIDED — 15 px one side of the ghost and 5 the other — and which side is the
 * wide one differs between the four, so each bound is named rather than derived from a
 * half-width. */
#define BLOW_ALONG_MIN_LEFT      (-1)   /* `cmpi.w #$ffff,delta_x / bge` @ 0x12ade */
#define BLOW_ALONG_MIN_DOWN      1      /* `cmpi.w #$1,delta_y / ble` @ 0x12b22 */
#define BLOW_ALONG_MIN_RIGHT     3      /* `cmpi.w #$3,delta_x / ble` @ 0x12a56 */
#define BLOW_ALONG_MIN_UP        (-1)   /* `cmpi.w #$ffff,delta_y / bge` @ 0x12a9a */
#define BLOW_ACROSS_NEAR         5      /* the short side of every orthogonal band */
#define BLOW_ACROSS_FAR          15     /* ...and the long one */

/* The four diagonal facings: both components past a threshold, then a CONE — the weighted sum
 * `a*delta_x + b*delta_y` inside +-BLOW_CONE_LIMIT. The weights are asymmetric between the pairs
 * (4/3/3/4), and that asymmetry is in the image rather than a transcription slip. */
#define BLOW_DIAGONAL_MIN        5      /* `cmpi.w #$5` / `cmpi.w #$fffb` on both components */
#define BLOW_CONE_WEIGHT_WIDE    4      /* down-left's delta_x and up-left's delta_y */
#define BLOW_CONE_WEIGHT_NARROW  3      /* down-right's delta_y and up-right's delta_x */
#define BLOW_CONE_WEIGHT_MINOR   2      /* the other component of all four cones */

/* `neg.w` — and `neg.w` of the most negative word is itself, which is why this is not `abs()`. */
static int16_t negate_word(int16_t value) {
    return (int16_t)(0 - value);
}

static int16_t magnitude_word(int16_t value) {
    return value < 0 ? negate_word(value) : value;
}

/* One drift arming, as every one of the eight direction tests performs it: the direction, the
 * velocity ALONG EACH AXIS THE DIRECTION MOVES ON (an orthogonal blow leaves the other velocity
 * alone — the frame's tail has already zeroed it), and a fresh pulse schedule. */
static void arm_drift(uint8_t *image, int16_t dir_x, int16_t dir_y, int16_t speed) {
    set_word(image, A_drift_dir_x, dir_x);
    set_word(image, A_drift_dir_y, dir_y);
    if (dir_x != 0)
        set_word(image, A_drift_vel_x, (int16_t)(dir_x * speed));
    if (dir_y != 0)
        set_word(image, A_drift_vel_y, (int16_t)(dir_y * speed));
    set_word(image, A_drift_interval, 0);
    set_word(image, A_drift_pulse, 0);
    set_word(image, A_drift_speed, speed);
}

/* The cone test both halves of a diagonal blow make: the same weighted sum compared against each
 * limit in turn, in WORD arithmetic (`muls.w` + `add.w`/`sub.w`), so a huge delta wraps. */
static int cone_admits(int16_t weighted_sum) {
    return weighted_sum < BLOW_CONE_LIMIT && weighted_sum > -BLOW_CONE_LIMIT;
}

static int16_t weighted(int16_t weight_x, int16_t delta_x, int16_t weight_y, int16_t delta_y) {
    return (int16_t)((int16_t)(weight_x * delta_x) + (int16_t)(weight_y * delta_y));
}

static void apply_blow(uint8_t *image, int16_t facing_index, int16_t delta_x, int16_t delta_y) {
    switch (facing_index) {
    case FACING_INDEX_RIGHT:
        if (delta_x > BLOW_ALONG_MIN_RIGHT
            && delta_y < BLOW_ACROSS_NEAR && delta_y > -BLOW_ACROSS_FAR)
            arm_drift(image, 1, 0, BLOW_SPEED_ORTHOGONAL);
        break;
    case FACING_INDEX_UP:
        if (delta_y < BLOW_ALONG_MIN_UP
            && delta_x < BLOW_ACROSS_NEAR && delta_x > -BLOW_ACROSS_FAR)
            arm_drift(image, 0, -1, BLOW_SPEED_ORTHOGONAL);
        break;
    case FACING_INDEX_LEFT:
        if (delta_x < BLOW_ALONG_MIN_LEFT
            && delta_y < BLOW_ACROSS_FAR && delta_y > -BLOW_ACROSS_NEAR)
            arm_drift(image, -1, 0, BLOW_SPEED_ORTHOGONAL);
        break;
    case FACING_INDEX_DOWN:
        if (delta_y > BLOW_ALONG_MIN_DOWN
            && delta_x < BLOW_ACROSS_FAR && delta_x > -BLOW_ACROSS_NEAR)
            arm_drift(image, 0, 1, BLOW_SPEED_ORTHOGONAL);
        break;
    case FACING_INDEX_DOWN_LEFT:
        if (delta_x < -BLOW_DIAGONAL_MIN && delta_y > BLOW_DIAGONAL_MIN
            && cone_admits(weighted(BLOW_CONE_WEIGHT_WIDE, delta_x,
                                    BLOW_CONE_WEIGHT_MINOR, delta_y)))
            arm_drift(image, -1, 1, BLOW_SPEED_DIAGONAL);
        break;
    case FACING_INDEX_DOWN_RIGHT:
        if (delta_x > BLOW_DIAGONAL_MIN && delta_y > BLOW_DIAGONAL_MIN
            && cone_admits(weighted(BLOW_CONE_WEIGHT_MINOR, delta_x,
                                    -BLOW_CONE_WEIGHT_NARROW, delta_y)))
            arm_drift(image, 1, 1, BLOW_SPEED_DIAGONAL);
        break;
    case FACING_INDEX_UP_RIGHT:
        if (delta_x > BLOW_DIAGONAL_MIN && delta_y < -BLOW_DIAGONAL_MIN
            && cone_admits(weighted(BLOW_CONE_WEIGHT_NARROW, delta_x,
                                    BLOW_CONE_WEIGHT_MINOR, delta_y)))
            arm_drift(image, 1, -1, BLOW_SPEED_DIAGONAL);
        break;
    case FACING_INDEX_UP_LEFT:
        if (delta_x < -BLOW_DIAGONAL_MIN && delta_y < -BLOW_DIAGONAL_MIN
            && cone_admits(weighted(BLOW_CONE_WEIGHT_MINOR, delta_x,
                                    -BLOW_CONE_WEIGHT_WIDE, delta_y)))
            arm_drift(image, -1, -1, BLOW_SPEED_DIAGONAL);
        break;
    default:
        break;                          /* a facing index outside 1..8 blows nothing */
    }
}

/* ---- addressing the three room-indexed tables --------------------------------------------------
 * The compiler emitted two different shapes for the same access, and they differ once an index is
 * out of range: inside `ghost_blow` the ROOM offset is added in full 32 bits (`add.l a0,d1`) while
 * the SLOT offset goes through an `adda.w`, and the fan test — which reaches a fixed slot — adds
 * the room offset through an `adda.w` instead. Each is transcribed where it is used. */

static uint32_t candle_word(int16_t room, uint32_t field) {
    return addr_add(A_candle_table + field, muls_ext_w(room, CANDLE_STRIDE));
}

static uint32_t object_field(int16_t room, int16_t slot, uint32_t field) {
    return addr_add(A_object_table + field + (uint32_t)((int32_t)room * (int32_t)OBJECT_ROOM_STRIDE),
                    muls_ext_w(slot, OBJECT_STRIDE));
}

static uint32_t room_map_cell(int16_t room, int16_t tile_row, int16_t tile_col) {
    return addr_add(A_room_table
                        + (uint32_t)((int32_t)room * (int32_t)ROOM_STRIDE)
                        + (uint32_t)((int32_t)tile_row * (int32_t)ROOM_MAP_ROW_BYTES),
                    sign_ext16((uint32_t)(tile_col * (int32_t)ROOM_MAP_CELL_BYTES)));
}

static uint32_t room_candle_sfx(int16_t room) {
    return addr_add(A_room_table + ROOM_CANDLE_SFX, muls_ext_w(room, ROOM_STRIDE));
}

static int16_t candle_slot(const uint8_t *image, int16_t room, uint32_t field) {
    return word_at(image, candle_word(room, field));
}

/* One of the two tile-map cells the extinguish patches: the cell the flame object stood on, which
 * the original locates by re-reading that object's own x and y. */
static void patch_room_map(uint8_t *image, int16_t room, int16_t slot, int16_t tile) {
    int16_t tile_col = word_at(image, object_field(room, slot, OBJECT_X));
    int16_t tile_row = word_at(image, object_field(room, slot, OBJECT_Y));

    set_word(image, room_map_cell(room, tile_row, tile_col), tile);
}

/* THE ROOM NUMBER IS RE-READ AT EVERY USE below, as the original re-reads `-7674(a4)` before each
 * of its twenty-eight table accesses between 0x12d26 and 0x12ff8 — and that is not a stylistic
 * choice. The map patch stores into `room_table[room].map[y][x]`, whose column offset is
 * `adda.w`-truncated, and a column of 2923 puts `room_table[0].map[0][x]` at exactly
 * `A_room_number`: the first patch can therefore CHANGE THE ROOM the second patch and the record
 * retire then work on. A reconstruction that read the room once is a different program.
 * `test_gameplay.py::test_ghost_blow_candle_patch_can_move_the_room_number` is that case. */
static int16_t current_room(const uint8_t *image) {
    return word_at(image, A_room_number);
}

/* Store `tile` into the object slot the CURRENT room's candle record names in `field`.
 *
 * THE ROOM IS RE-READ PER CALL, and that is what matters: a store made here can land on
 * `A_room_number` itself (see `current_room` above), so the next call must work on the room the
 * previous store left. Four calls, four reads.
 *
 * The two reads INSIDE one call are the original's instruction stream transcribed, and they are
 * provably one: nothing between them writes memory, so caching the room within a single call is
 * byte-identical for every input. Measured as a surviving mutation and recorded as an equivalent in
 * ../STATUS.md rather than left looking like a hole. */
static void set_object_tile_for(uint8_t *image, uint32_t field, int16_t tile) {
    set_word(image, object_field(current_room(image),
                                 candle_slot(image, current_room(image), field),
                                 OBJECT_TILE), tile);
}

/* The scripted half: blowing a candle out. It replaces the two lit-flame object slots with the two
 * the record names, patches the room's own tile map at the cells those objects occupied — so the
 * change survives a re-entry into the room — and retires the record. */
static void extinguish_candle(uint8_t *image) {
    int16_t flame_a, tile_a, tile_b;
    int16_t delta_x, delta_y, sfx;

    flame_a = candle_slot(image, current_room(image), CANDLE_FLAME_SLOT_A);
    if (flame_a == CANDLE_NONE)
        return;

    delta_x = (int16_t)((int16_t)(word_at(image, object_field(current_room(image), flame_a,
                                                              OBJECT_X)) * ENTRY_POINT_PIXELS)
                        - word_at(image, A_ghost_x));
    set_word(image, A_delta_x, delta_x);
    flame_a = candle_slot(image, current_room(image), CANDLE_FLAME_SLOT_A);
    delta_y = (int16_t)((int16_t)(word_at(image, object_field(current_room(image), flame_a,
                                                              OBJECT_Y)) * ENTRY_POINT_PIXELS)
                        - word_at(image, A_ghost_y));
    set_word(image, A_delta_y, delta_y);

    if (word_at(image, A_blow_facing_plus1) != CANDLE_FACING_INDEX)
        return;
    if (delta_x >= -(int16_t)CANDLE_DX_NEAR || delta_x <= -(int16_t)CANDLE_DX_FAR)
        return;
    if (delta_y >= CANDLE_DY_MAX || delta_y <= CANDLE_DY_MIN)
        return;

    sfx = word_at(image, room_candle_sfx(current_room(image)));
    if (sfx != CANDLE_NONE)
        sound_play(image,
                   addr_add(A_snd_def_fx + CANDLE_SFX_FIRST * SND_DEF_BYTES,
                            muls_ext_w(sfx, SND_DEF_BYTES)),
                   BLOW_VOICE,
                   (int16_t)(word_at(image, A_sound_enabled) * CANDLE_VOLUME_STEP),
                   CANDLE_SFX_NOTE, CANDLE_SFX_PRIORITY);

    /* From here every table access re-reads BOTH the room and the record, as the original does:
     * with an out-of-range room or slot a store can land inside `candle_table` or on
     * `A_room_number` itself, so caching either across these six stores is not the same program.
     * `set_object_tile_for` below is that re-read, once. */
    tile_a = word_at(image, candle_word(current_room(image), CANDLE_TILE_A));
    tile_b = word_at(image, candle_word(current_room(image), CANDLE_TILE_B));

    set_object_tile_for(image, CANDLE_FLAME_SLOT_A, CANDLE_NONE);
    set_object_tile_for(image, CANDLE_FLAME_SLOT_B, CANDLE_NONE);
    set_object_tile_for(image, CANDLE_DEST_A, tile_a);
    set_object_tile_for(image, CANDLE_DEST_B, tile_b);

    patch_room_map(image, current_room(image),
                   candle_slot(image, current_room(image), CANDLE_FLAME_SLOT_A), tile_a);
    patch_room_map(image, current_room(image),
                   candle_slot(image, current_room(image), CANDLE_FLAME_SLOT_B), tile_b);

    set_word(image, candle_word(current_room(image), CANDLE_FLAME_SLOT_A), CANDLE_NONE);

    wr32(image + A_score, (uint32_t)(long_at(image, A_score) + CANDLE_SCORE));
    if (long_at(image, A_score) > long_at(image, A_hi_score))
        wr32(image + A_hi_score, (uint32_t)long_at(image, A_score));
}

void ghost_blow_body(uint8_t *image) {
    int16_t delta_x, delta_y, facing_index;

    /* The puff is triggered only if voice 1 is idle, so holding the blow does not restart it. */
    if (sound_voice_priority(image, BLOW_VOICE) == 0)
        sound_play(image, A_snd_def_fx + BLOW_SFX * SND_DEF_BYTES, BLOW_VOICE,
                   (int16_t)(word_at(image, A_sound_enabled) * BLOW_VOLUME_STEP),
                   BLOW_SFX_NOTE, BLOW_SFX_PRIORITY);

    delta_x = (int16_t)(word_at(image, A_bubble_x) - word_at(image, A_ghost_x));
    set_word(image, A_delta_x, delta_x);
    delta_y = (int16_t)(word_at(image, A_bubble_y) - word_at(image, A_ghost_y));
    set_word(image, A_delta_y, delta_y);
    facing_index = (int16_t)((int16_t)(word_at(image, A_ghost_tile) + 1) / GHOST_TILES_PER_FACING);
    set_word(image, A_blow_facing_plus1, facing_index);

    if (magnitude_word(delta_x) < BLOW_RANGE && magnitude_word(delta_y) < BLOW_RANGE)
        apply_blow(image, facing_index, delta_x, delta_y);

    /* Reached whether or not the bubble was blown, and it re-uses `delta_x`/`delta_y` for its own
     * measurement — which is why those two globals hold the CANDLE's offsets after this returns. */
    extinguish_candle(image);
}

/* ================================================================================================
 * game_frame_update @ 0x12322 — one frame, in nine slices
 *
 * The slice boundaries are named in `include/gameplay.h`'s prototypes and in
 * `test/test_gameplay.py`'s ENTRY_/STOP_ pairs; the two regions between them that are NOT here are
 * the front-end poll (0x1233a..0x12434) and the death sequence (0x1273c..0x1294a).
 * ============================================================================================= */

#define POP_VOICE            2      /* `move.w #$2,-(a7)` @ 0x12706 */
#define POP_SFX              4      /* snd_def_fx[4] @ 0x2038a — `pea -19344(a4)` @ 0x1270a */
#define POP_VOLUME_STEP      11     /* `muls.w #$b` @ 0x12700 */
#define POP_SFX_NOTE         (-1)   /* `move.w #$ffff,-(a7)` @ 0x126f8 */
#define POP_SFX_PRIORITY     5      /* `move.w #$5,-(a7)` @ 0x126f4 */

/* The bubble is DEAD but still on an early animation frame — the one dead path that falls straight
 * through to the drift pulse instead of entering the death sequence. */
#define BUBBLE_DEATH_TRIGGER_FRAME 3   /* `cmpi.w #$3,-7986(a4) / ble` @ 0x1273c */

/* Where `xbios_trap` @ 0x15e3c returns to for each of the two `Setcolor` sites in this routine.
 * The trampoline files its caller's return address, so the address is a property of the call site
 * (include/clib.h, "Where each wrapper's `jsr` to the trampoline returns to"). */
#define RET_SETCOLOR_SPENT  0x12502u   /* the `jsr` @ 0x124fe, on the frame the breath runs out */
#define RET_SETCOLOR_IDLE   0x1255au   /* the `jsr` @ 0x12556, every idle frame */

/* Slice 1, `[0x12322, 0x1233a)` — the bubble's nine-frame sparkle, advanced once per frame. */
void frame_advance_bubble_frame(uint8_t *image) {
    int16_t previous = word_at(image, A_bubble_frame);

    set_word(image, A_bubble_frame, (int16_t)(previous + 1));
    if (previous > (int16_t)BUBBLE_LAST_FRAME)
        set_word(image, A_bubble_frame, BUBBLE_FIRST_FRAME);
}

/* Slice 2, `[0x12434, 0x124a4)` — the mouse, divided down onto the room area.
 *
 * The three divisors are DOUBLES in the program's DATA segment and the divide runs through the
 * Alcyon software float package (`include/clib.h`), accumulator and all — so the intermediate is
 * an eight-byte value in the image and the result is truncated toward zero, not rounded. Room 35
 * is the ending room and is scaled differently. */
static void divide_into_accumulator(uint8_t *image, int16_t numerator, uint32_t divisor) {
    fp_acc_load_long(image, sign_ext16((uint32_t)numerator));
    /* `fp_dispatch`'s widening scratch is its OWN stack local, and opcode 0x803's source is a
     * plain double that is never widened — so no address is needed and none is passed. */
    fp_dispatch(image, FP_OP_DIVIDE, A_fp_acc, divisor, 0, 0);
}

void frame_scale_mouse_to_ghost(uint8_t *image) {
    GlobalsBase globals = globals_base(image);
    uint32_t x_scale = word_at_base(globals, A_room_number) == ROOM_WIDE
                           ? A_const_mouse_x_scale_room35 : A_const_mouse_x_scale;

    divide_into_accumulator(image, word_at_base(globals, A_mouse_x), x_scale);
    set_word_at_base(globals, A_ghost_x, (int16_t)fp_acc_to_long(image));
    divide_into_accumulator(image, word_at_base(globals, A_mouse_y), A_const_mouse_y_scale);
    set_word_at_base(globals, A_ghost_y, (int16_t)fp_acc_to_long(image));
}

/* Slice 3, `[0x124a4, 0x1255c)` — blowing, or recovering.
 *
 * `saved` is the caller's A1/A2 at entry, which is what the two `Setcolor` calls' trampoline files
 * (docs/agent-playbook.md §5, "a parameter"). Nothing between the entry and either trap writes an
 * address register — `sound_voice_priority` @ 0x1455e and `sound_release_voice` @ 0x14510 touch
 * only D0/A0 — so the registers the trampoline sees ARE the ones the slice was entered with. */
void frame_blow_or_recover(uint8_t *image, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);
    int16_t shift = word_at_base(globals, A_key_shift_state);
    int16_t breath;

    if (shift != (int16_t)KEY_SHIFT_NONE && shift != (int16_t)KEY_SHIFT_CTRL_ONLY) {
        set_word_at_base(globals, A_ghost_anim, GHOST_BLOW_ANIM);
        set_word_at_base(globals, A_ghost_tile,
                         (int16_t)((int16_t)(word_at_base(globals, A_ghost_facing)
                                             * GHOST_TILES_PER_FACING)
                                   + word_at_base(globals, A_ghost_anim)));
        breath = (int16_t)(word_at_base(globals, A_breath) - 1);
        set_word_at_base(globals, A_breath, breath);
        if (breath >= 0) {
            /* THE SLICE'S ONE PRECONDITION: `ghost_blow_body` is `ghost_blow` MINUS its two
             * redraws, and the original reaches those only when the candle script fires — every
             * other exit branches over them. So this call is the whole of `ghost_blow` exactly
             * while the current room has no candle left, which is what
             * `test_gameplay.py::blow_slice_pokes` stages (STATUS.md records it as a residual). */
            ghost_blow_body(image);
            return;
        }
        /* Out of air: the puff is released, the gauge is pinned at empty and the ghost turns pink
         * until the player lets go. */
        if (sound_voice_priority(image, BLOW_VOICE) != 0)
            sound_release_voice(image, BLOW_VOICE);
        set_word_at_base(globals, A_breath, 0);
        /* ...through XBIOS `Setcolor(GHOST_PEN, GHOST_COLOUR_SPENT)`. It writes the shifter and no
         * image byte, so the trampoline's three save slots are still the only bytes a diff can see
         * — but the CALL is now an ordered event, and on target it really moves the pen. */
        trap_save_registers_at_base(globals, saved, RET_SETCOLOR_SPENT);
        os_setcolor(GHOST_PEN, GHOST_COLOUR_SPENT);
        return;
    }

    if (sound_voice_priority(image, BLOW_VOICE) != 0)
        sound_release_voice(image, BLOW_VOICE);
    /* The idle walk cycle, and the gauge refilling three times as fast as it drains. */
    {
        int16_t previous = word_at_base(globals, A_ghost_anim);

        set_word_at_base(globals, A_ghost_anim, (int16_t)(previous + 1));
        if (previous > (int16_t)GHOST_IDLE_ANIM_LAST)
            set_word_at_base(globals, A_ghost_anim, 0);
    }
    breath = (int16_t)(word_at_base(globals, A_breath) + BREATH_REFILL_PER_FRAME);
    set_word_at_base(globals, A_breath, breath);
    if (breath > (int16_t)BREATH_MAX)
        set_word_at_base(globals, A_breath, BREATH_MAX);
    /* ...and `Setcolor(GHOST_PEN, GHOST_COLOUR_IDLE)`, the same call the other way. */
    trap_save_registers_at_base(globals, saved, RET_SETCOLOR_IDLE);
    os_setcolor(GHOST_PEN, GHOST_COLOUR_IDLE);
}

/* Slice 4, `[0x1255c, 0x125e6)` — the mouse buttons step the facing, one step per press.
 *
 * Each button has its own BYTE edge latch: the step happens on the frame the button is seen down
 * with the latch armed, and the latch re-arms on the first frame the button is not that one. */
static void step_facing(GlobalsBase globals, int16_t delta) {
    int16_t facing = (int16_t)(word_at_base(globals, A_ghost_facing) + delta);

    set_word_at_base(globals, A_ghost_facing, facing);
    /* Both tests are made AFTER the store, so the out-of-range value is written and only then
     * replaced — and each end wraps to the other. */
    if (delta > 0 ? facing > (int16_t)GHOST_FACINGS - 1 : facing < 0)
        set_word_at_base(globals, A_ghost_facing, delta > 0 ? 0 : (int16_t)GHOST_FACINGS - 1);
    set_word_at_base(globals, A_ghost_tile,
                     (int16_t)(word_at_base(globals, A_ghost_facing) * GHOST_TILES_PER_FACING));
}

void frame_step_facing(uint8_t *image) {
    GlobalsBase globals = globals_base(image);
    int16_t buttons = word_at_base(globals, A_mouse_buttons);
    uint8_t *left_ready = globals_at(globals, A_btn_left_ready);
    uint8_t *right_ready = globals_at(globals, A_btn_right_ready);

    if (buttons == 1 && *left_ready != 0) {
        *left_ready = 0;
        step_facing(globals, +1);
    }
    if (buttons != 1)
        *left_ready = 1;
    if (buttons == 2 && *right_ready != 0) {
        *right_ready = 0;
        step_facing(globals, -1);
    }
    if (buttons != 2)
        *right_ready = 1;
    /* ...and the tile is recomputed WITH the animation frame, which the two steps above leave out. */
    set_word_at_base(globals, A_ghost_tile,
                     (int16_t)((int16_t)(word_at_base(globals, A_ghost_facing)
                                         * GHOST_TILES_PER_FACING)
                               + word_at_base(globals, A_ghost_anim)));
}

/* Slice 5, `[0x125e6, 0x126e2)` — the fans.
 *
 * The only object type with behaviour, and it is hard-coded to object slots 3 and 4 of the current
 * room: a recreate that reordered a room's slots would break its fan. Because the slot is a
 * constant the compiler folded it into the `lea`, so here — unlike everywhere in `ghost_blow` —
 * it is the ROOM offset that goes through an `adda.w` and is truncated to a word. */
static uint32_t fan_field(int16_t room, unsigned slot, uint32_t field) {
    return addr_add(A_object_table + slot * OBJECT_STRIDE + field,
                    muls_ext_w(room, OBJECT_ROOM_STRIDE));
}

/* IT TAKES BOTH, and the split is that `fan_field` is a RUN-TIME address: the room number goes
 * through `muls_ext_w` and `addr_add`, which is the original's own `adda.w` truncation.
 * `include/common.h`'s `globals_at` states the rule — it is `image + (int32_t)address` where the
 * image form is `image + (uint32_t)address`, the same byte for every address this program can build
 * and a different one only for an address it cannot. The three object fields therefore stay on
 * `image`, where the arithmetic that produced them belongs, and only the five FIXED globals move to
 * the base. `src/frontend.c`'s `draw_sprites` and `v_gtext` carry the same split. */
static void apply_fan(const uint8_t *image, GlobalsBase globals, int16_t room, unsigned slot) {
    int16_t delta_x, delta_y;

    if (word_at(image, fan_field(room, slot, OBJECT_TILE)) != (int16_t)OBJECT_FAN_TILE)
        return;

    /* The two scratch globals are written whether or not the fan reaches the bubble, so a room
     * with a fan leaves different `delta_x`/`delta_y` behind than one without. */
    delta_x = (int16_t)((int16_t)(word_at(image, fan_field(room, slot, OBJECT_X))
                                  * ENTRY_POINT_PIXELS)
                        - word_at_base(globals, A_bubble_x));
    set_word_at_base(globals, A_delta_x, delta_x);
    delta_y = (int16_t)((int16_t)(word_at(image, fan_field(room, slot, OBJECT_Y))
                                  * ENTRY_POINT_PIXELS)
                        - word_at_base(globals, A_bubble_y));
    set_word_at_base(globals, A_delta_y, delta_y);

    if (delta_x <= FAN_DX_MIN || delta_x >= FAN_DX_MAX)
        return;
    if (delta_y <= -(int16_t)FAN_DY_LIMIT || delta_y >= (int16_t)FAN_DY_LIMIT)
        return;

    /* A fan pushes LEFT only: two pixels this frame through `x_impulse`, plus a one-hundredth of a
     * pixel a frame of drift that the pulse below keeps re-arming. */
    set_word_at_base(globals, A_drift_dir_x, -1);
    set_word_at_base(globals, A_x_impulse, -(int16_t)FAN_PUSH_PIXELS);
    set_word_at_base(globals, A_drift_vel_x, -1);
}

void frame_apply_fans(uint8_t *image) {
    GlobalsBase globals = globals_base(image);

    /* The original re-reads `-7674(a4)` for each of its eight accesses here too, and caching it is
     * safe ONLY because every store this slice makes is to a fixed global — `A_delta_x`,
     * `A_delta_y`, `A_drift_dir_x`, `A_x_impulse`, `A_drift_vel_x` — and none of them is
     * `A_room_number`. That is not true of `extinguish_candle`, which is why it re-reads. */
    int16_t room = word_at_base(globals, A_room_number);

    apply_fan(image, globals, room, OBJECT_FAN_SLOT_A);
    apply_fan(image, globals, room, OBJECT_FAN_SLOT_B);
}

/* Slice 6, `[0x126e2, 0x1294a)` — the bubble's own step.
 *
 * Answers non-zero when the frame has entered the DEATH SEQUENCE at 0x1273c — `frame_death_sequence`
 * below, which is a slice of its own because it is 526 bytes with a world of its own to stage. That
 * is a flag this reconstruction needs to say where this slice stops, not a value the original
 * computes: the original simply falls into the sequence. */
int16_t frame_step_live_bubble(uint8_t *image) {
    GlobalsBase globals = globals_base(image);

    if (word_at_base(globals, A_bubble_alive) != 0) {
        bubble_collision_probe(image);
        if (word_at_base(globals, A_bubble_frame) == (int16_t)BUBBLE_POPPED_FRAME) {
            sound_play(image, A_snd_def_fx + POP_SFX * SND_DEF_BYTES, POP_VOICE,
                       (int16_t)(word_at_base(globals, A_sound_enabled) * POP_VOLUME_STEP),
                       POP_SFX_NOTE, POP_SFX_PRIORITY);
            return 0;
        }
        /* The velocity is in hundredths of a pixel and `x_impulse` is in whole ones. */
        set_word_at_base(globals, A_bubble_x,
                         (int16_t)(word_at_base(globals, A_bubble_x)
                                   + (int16_t)(word_at_base(globals, A_drift_vel_x)
                                               / DRIFT_VELOCITY_SCALE)
                                   + word_at_base(globals, A_x_impulse)));
        set_word_at_base(globals, A_bubble_y,
                         (int16_t)(word_at_base(globals, A_bubble_y)
                                   + (int16_t)(word_at_base(globals, A_drift_vel_y)
                                               / DRIFT_VELOCITY_SCALE)));
        return 0;
    }
    return word_at_base(globals, A_bubble_frame) > BUBBLE_DEATH_TRIGGER_FRAME;
}

/* Slice 7, `[0x1294a, 0x129b0)` — the drift pulse, and the frame's tail.
 *
 * The bubble does not integrate a velocity every frame: both velocities and the fan's impulse are
 * cleared here, and re-armed only when the pulse counter reaches zero. The speed decays by 50 per
 * pulse to a floor of 100 and the gap between pulses grows to 20 frames, so a blown bubble steps
 * 3, 2.5, 2, 1.5, 1 pixels and visibly stalls. */
void frame_drift_pulse(uint8_t *image) {
    int16_t pulse = word_at(image, A_drift_pulse);
    int16_t speed, interval;

    set_word(image, A_drift_vel_x, 0);
    set_word(image, A_drift_vel_y, 0);
    set_word(image, A_x_impulse, 0);
    set_word(image, A_drift_pulse, (int16_t)(pulse - 1));
    if (pulse != 0)
        return;

    speed = word_at(image, A_drift_speed);
    set_word(image, A_drift_vel_x, (int16_t)(word_at(image, A_drift_dir_x) * speed));
    set_word(image, A_drift_vel_y, (int16_t)(word_at(image, A_drift_dir_y) * speed));

    speed = (int16_t)(speed - DRIFT_SPEED_DECAY);
    set_word(image, A_drift_speed, speed);
    if (speed < DRIFT_SPEED_FLOOR)
        set_word(image, A_drift_speed, DRIFT_SPEED_FLOOR);

    interval = (int16_t)(word_at(image, A_drift_interval) + 1);
    set_word(image, A_drift_interval, interval);
    if (interval > DRIFT_INTERVAL_MAX)
        set_word(image, A_drift_interval, DRIFT_INTERVAL_MAX);
    set_word(image, A_drift_pulse,
             (int16_t)(word_at(image, A_drift_interval) / DRIFT_INTERVAL_DIVISOR));
}

/* ================================================================================================
 * The front-end poll — the slice `[0x1233a, 0x12434)`
 *
 * Two VDI queries and one GEMDOS key read, then the three control keys the game watches for. Its
 * A1/A2 are the caller's throughout: `vq_mouse`/`vq_key_s` reach the GEM trampoline, the console
 * calls reach the GEMDOS one, and nothing between them writes an address register.
 * ============================================================================================= */

/* `while (Cconis()) Crawcin();` — the idiom that appears twice, once before the read and once
 * inside the pause. Every key already queued is thrown away, so a held key cannot run the game a
 * frame per keystroke. The `Crawcin` cannot refuse: nothing reaches it unless `Cconis` has just
 * said a key is waiting.
 *
 * EXPORTED, because the front end's menu opens every one of its four key reads with it — the
 * `menu_draw`, `menu_ask_player_count`, `menu_ask_practice_level` and `menu_read_level_tens` slices
 * of `src/frontend.c` each end with one. It is declared in `include/gameplay.h` under this project's
 * rule that a subsystem's own header is where another subsystem reaches it. */
void drain_console_queue(uint8_t *image, uint32_t cconis_return, uint32_t crawcin_return,
                         CallerAddressRegisters saved) {
    for (;;) {
        uint32_t key;

        trap_save_registers(image, saved, cconis_return);
        if (os_cconis(image) == 0)
            return;
        trap_save_registers(image, saved, crawcin_return);
        os_crawcin(image, &key);
    }
}

/* One `Crawio(0xff)`, the non-blocking raw read: the LOW BYTE of its answer is the ASCII, and that
 * byte is all the game keeps. An idle console answers `OS_CRAWIO_RESULT`, so the poll runs on. */
static void read_raw_key(uint8_t *image, GlobalsBase globals, uint32_t crawio_return,
                         CallerAddressRegisters saved) {
    trap_save_registers_at_base(globals, saved, crawio_return);
    *globals_at(globals, A_key_raw) = (uint8_t)os_crawio(image, OS_CRAWIO_READ);
}

/* `move.b -7686(a4),d0 / ext.w d0` — the key compared as a SIGNED byte widened to a word, so a
 * key with bit 7 set can never equal one of the three control codes. Both readers below hold the
 * base already, which is why this takes it rather than the image. */
static int16_t key_as_word(GlobalsBase globals) {
    return (int16_t)(int8_t)*globals_at(globals, A_key_raw);
}

/* ^P, `[0x1239e, 0x123de)` — everything queued is thrown away and the game then SPINS on `Crawio`
 * until a second ^P arrives.
 *
 * READ-VERIFIED, and no case runs it (../STATUS.md's residual). The flush drains EVERYTHING a case
 * has staged, so the resuming key would have to arrive after it — and the console model stages a
 * queue rather than an arrival. The kit's scheduled-write model does stage an arrival, but it is
 * keyed to the byte the original's own compare re-reads, and this wait's compare reads `A_key_raw`,
 * which the routine writes itself: the byte that really changes is the model's console block,
 * inside the trap. There is no site to name, so the loop is transcribed and said to be unrun. */
void frame_poll_pause(uint8_t *image, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    *globals_at(globals, A_key_raw) = 0;
    drain_console_queue(image, RET_POLL_PAUSE_CCONIS, RET_POLL_PAUSE_CRAWCIN, saved);
    while (key_as_word(globals) != KEY_PAUSE)
        read_raw_key(image, globals, RET_POLL_PAUSE_CRAWIO, saved);
}

/* ^R: the whole game is thrown away — both players' scores, the live score, the life count and
 * both "still playing" flags. The turn ends because `A_lives` is left at the -1 `game_top_loop`
 * tests for. */
static void reset_game_from_keyboard(GlobalsBase globals) {
    set_word_at_base(globals, A_level_complete, 0);
    wr32(globals_at(globals, A_lives), (uint32_t)(int32_t)HUD_LIVES_EXHAUSTED);
    wr32(globals_at(globals, A_p2_score), 0);
    wr32(globals_at(globals, A_p1_score), 0);
    wr32(globals_at(globals, A_score), 0);
    set_word_at_base(globals, A_p2_playing, 0);
    set_word_at_base(globals, A_p1_playing, 0);
}

/* ...and the poll itself, which ANSWERS whether the key was ^P rather than falling into the pause.
 *
 * The flag is this reconstruction's, not the original's — the original branches straight into the
 * loop above. It exists because the loop is the one thing here no case can run: a silent
 * fall-through into unrunnable code would make the difference between "the pause was entered" and
 * "the key was ignored" invisible, and every case below asserts the answer instead
 * (docs/agent-playbook.md §5, and `frame_step_live_bubble`'s residual is the same shape). */
int16_t frame_poll_input(uint8_t *image, CallerAddressRegisters saved) {
    GlobalsBase globals = globals_base(image);

    vq_mouse(image, vdi_handle(image), A_mouse_buttons, A_mouse_x, A_mouse_y, saved);
    vq_key_s(image, vdi_handle(image), A_key_shift_state, saved);

    /* The flush runs only when the PREVIOUS frame left a key behind — `tst.b` on the byte itself,
     * not on the sign-extended word, so any non-zero key arms it. */
    if (*globals_at(globals, A_key_raw) != 0)
        drain_console_queue(image, RET_POLL_FLUSH_CCONIS, RET_POLL_FLUSH_CRAWCIN, saved);
    read_raw_key(image, globals, RET_POLL_CRAWIO, saved);

    if (key_as_word(globals) == KEY_PAUSE)
        return 1;
    if (key_as_word(globals) == KEY_SOUND_TOGGLE) {
        set_word_at_base(globals, A_sound_enabled,
                         word_at_base(globals, A_sound_enabled) == 0 ? 1 : 0);
        return 0;
    }
    if (key_as_word(globals) == KEY_RESET)
        reset_game_from_keyboard(globals);
    return 0;
}

/* ================================================================================================
 * The death sequence — the slice `[0x1273c, 0x1294a)`
 *
 * `frame_step_live_bubble` falls into this when the popped bubble's frame counter has run past
 * `BUBBLE_DEATH_TRIGGER_FRAME`. It is three animations, a respawn and — in a two-player game — the
 * handover.
 * ============================================================================================= */

/* Where one player's turn is parked. `include/gameplay.h` freezes the record and declares the two
 * instances; they are DEFINED here, in the subsystem that owns the state, and `src/frontend.c`'s
 * player-change slice reads the same two to put a turn back. */
const PlayerTurnSlots PLAYER_ONE_SLOTS = {
    A_p1_max_room, A_p1_lives, A_p1_score, A_p1_bonus_bar, A_p1_grid_col, A_p1_grid_row,
    A_p1_deaths_in_room, A_p1_entry_dir, A_p1_world_block,
};
const PlayerTurnSlots PLAYER_TWO_SLOTS = {
    A_p2_max_room, A_p2_lives, A_p2_score, A_p2_bonus_bar, A_p2_grid_col, A_p2_grid_row,
    A_p2_deaths_in_room, A_p2_entry_dir, A_p2_world_block,
};

/* `Random()` scaled into DEATH_HOLD's 2..6 through the software float package, which is how the
 * original does it: the 24-bit answer is widened to a double, divided by a constant just above
 * 2^24, multiplied by five and offset by two, then truncated toward zero. */
static int16_t random_hold_frames(uint8_t *image, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_DEATH_RANDOM);
    fp_acc_load_long(image, os_random(image));
    /* Each source is a plain double in DATA, never widened, so `fp_dispatch`'s widening scratch is
     * unused and none is passed — as in `divide_into_accumulator` above. */
    fp_dispatch(image, FP_OP_DIVIDE, A_fp_acc, A_const_random_divisor, 0, 0);
    fp_dispatch(image, FP_OP_MULTIPLY, A_fp_acc, A_const_random_scale, 0, 0);
    fp_dispatch(image, FP_OP_PLUS, A_fp_acc, A_const_random_offset, 0, 0);
    return (int16_t)fp_acc_to_long(image);
}

/* One word of the current room's entry-point table, which is a PAIR per entry direction: `field` is
 * ROOM_ENTRY_X or ROOM_ENTRY_Y, each a tile index the caller scales up to pixels.
 *
 * The original builds a WORD index — `muls.w #$2` on the direction, and `add.w #$1` again for the
 * y — scales it with `asl.l #1` and adds it with `adda.w`. So the byte offset is
 * `direction * ROOM_ENTRY_STRIDE + field`, TRUNCATED TO A WORD before it reaches the row pointer:
 * a direction big enough to overflow wraps back into the table rather than reaching past it.
 *
 * EXPORTED, because the front end's room setup places the bubble through the same table and the
 * same three constants (`src/frontend.c`'s `game_room_setup`). */
int16_t room_entry_coordinate(const uint8_t *image, int16_t direction, unsigned field) {
    uint32_t row = addr_add(A_room_table + ROOM_ENTRY_POINTS,
                            (uint32_t)(word_at(image, A_room_number) * (int32_t)ROOM_STRIDE));
    int16_t offset = (int16_t)(direction * (int16_t)ROOM_ENTRY_STRIDE + (int16_t)field);

    return word_at(image, addr_add(row, sign_ext16((uint32_t)offset)));
}

/* The bubble put back at the room's entry point, with every drift term disarmed. */
static void respawn_bubble_at_entry_point(uint8_t *image) {
    int16_t direction = word_at(image, A_entry_dir);

    set_word(image, A_ghost_tile, 0);
    set_word(image, A_ghost_facing, 0);
    set_word(image, A_ghost_anim, 0);
    set_word(image, A_bubble_frame, BUBBLE_FIRST_FRAME);
    set_word(image, A_bubble_alive, 1);
    set_word(image, A_drift_dir_x, 0);
    set_word(image, A_drift_dir_y, 0);
    set_word(image, A_drift_interval, 0);
    set_word(image, A_drift_pulse, 0);
    set_word(image, A_drift_speed, DRIFT_SPEED_INITIAL);

    set_word(image, A_bubble_x,
             (int16_t)(room_entry_coordinate(image, direction, ROOM_ENTRY_X)
                       * (int16_t)ENTRY_POINT_PIXELS));
    set_word(image, A_bubble_y,
             (int16_t)(room_entry_coordinate(image, direction, ROOM_ENTRY_Y)
                       * (int16_t)ENTRY_POINT_PIXELS));
    set_word(image, A_drift_vel_x, 0);
    set_word(image, A_drift_vel_y, 0);
}

/* The eight live values, plus the world block, into one player's own slots. */
static void park_turn(uint8_t *image, const PlayerTurnSlots *slots) {
    set_word(image, slots->max_room, word_at(image, A_max_room_reached));
    wr32(image + slots->lives, (uint32_t)long_at(image, A_lives));
    wr32(image + slots->score, (uint32_t)long_at(image, A_score));
    set_word(image, slots->bonus_bar, word_at(image, A_bonus_bar));
    set_word(image, slots->grid_col, word_at(image, A_grid_col));
    set_word(image, slots->grid_row, word_at(image, A_grid_row));
    set_word(image, slots->deaths_in_room, word_at(image, A_deaths_in_room));
    set_word(image, slots->entry_dir, word_at(image, A_entry_dir));
    save_world(image, slots->world_block);
}

void frame_death_sequence(uint8_t *image, uint32_t hud_frame, CallerAddressRegisters saved) {
    if (word_at(image, A_bubble_frame) <= (int16_t)BUBBLE_DEATH_TRIGGER_FRAME)
        return;
    set_word(image, A_bubble_frame, BUBBLE_DEATH_TRIGGER_FRAME);

    /* 1. The ghost walked back to facing 0, one whole facing per frame. */
    while (word_at(image, A_ghost_tile) > (int16_t)GHOST_TILES_PER_FACING - 1) {
        set_word(image, A_ghost_tile,
                 (int16_t)(word_at(image, A_ghost_tile) - (int16_t)GHOST_TILES_PER_FACING));
        animation_frame(image, saved);
    }

    sound_release_voice(image, BLOW_VOICE);
    /* ...and the ghost put back to its idle colour, through XBIOS `Setcolor`. */
    trap_save_registers(image, saved, RET_DEATH_SETCOLOR);
    os_setcolor(GHOST_PEN, GHOST_COLOUR_IDLE);

    /* 2. The five death cells, each held for a random 2..6 frames. The hold is DECREMENTED every
     * frame and re-rolled when it has gone negative, so the first cell is shown
     * DEATH_HOLD_INITIAL + 1 times before the roll ever happens. */
    set_word(image, A_seq_counter, DEATH_HOLD_INITIAL);
    set_word(image, A_ghost_tile, DEATH_GHOST_FIRST_TILE);
    while (word_at(image, A_ghost_tile) < (int16_t)DEATH_GHOST_LAST_TILE) {
        if (word_at(image, A_seq_counter) < 0) {
            set_word(image, A_seq_counter, random_hold_frames(image, saved));
            set_word(image, A_ghost_tile, (int16_t)(word_at(image, A_ghost_tile) + 1));
        }
        set_word(image, A_seq_counter, (int16_t)(word_at(image, A_seq_counter) - 1));
        animation_frame(image, saved);
    }

    /* 3. Ten frames of the last cell, standing still. */
    for (set_word(image, A_seq_counter, 0);
         word_at(image, A_seq_counter) < (int16_t)DEATH_PAUSE_FRAMES;
         set_word(image, A_seq_counter, (int16_t)(word_at(image, A_seq_counter) + 1)))
        animation_frame(image, saved);

    respawn_bubble_at_entry_point(image);
    wr32(image + A_lives, (uint32_t)(long_at(image, A_lives) - 1));
    set_word(image, A_deaths_in_room, (int16_t)(word_at(image, A_deaths_in_room) + 1));
    hud_draw_counters(image, hud_frame, saved);
    present_score_strip(image);

    /* The handover, in a two-player game only: the room loop is broken so `game_top_loop` can put
     * up the next player's card, and this turn is parked. */
    if (word_at(image, A_player_count) != (int16_t)PLAYER_COUNT_TWO)
        return;
    set_word(image, A_in_room, 0);
    set_word(image, A_show_player_change, 1);
    park_turn(image, word_at(image, A_p1_turn) != 0 ? &PLAYER_ONE_SLOTS : &PLAYER_TWO_SLOTS);
}

/* ================================================================================================
 * The HUD painters — hud_draw_counters @ 0x113d2, hud_bonus_bar_fill @ 0x112c8 and
 * hud_bonus_bar_shrink @ 0x11346
 *
 * All three draw through the front end's VDI binding (`include/frontend.h`) and take two arguments
 * their C prototypes would not have (docs/agent-playbook.md §5, "a parameter"):
 *
 *   * THEIR OWN STACK FRAME, because what they hand the VDI lives in it — the four counter strings
 *     `itoa_padded` fills, and the four-word rectangle `vr_recfl` is lent. A C reconstruction has
 *     no machine stack, and the frame lies in the band the differential drops, so both sides are
 *     handed the same address.
 *   * THE CALLER'S A1/A2, which the GEM trampoline files on every VDI call.
 *
 * ...and `hud_bonus_bar_fill` is the one routine in this file where the second is not constant
 * through the run: its scanline copy leaves A2 one row past the bar, and the NEXT column's
 * `vr_recfl` files that instead of the caller's. That is §5's "derivable" case — the value comes
 * from the routine's own instructions — so the core computes it rather than taking it per call.
 * ============================================================================================= */

_Static_assert(BONUS_BAR_ROW_OFFSET == BONUS_BAR_Y * SCREEN_ROW_BYTES,
               "the bonus bar's `add.l #$7620` is not row BONUS_BAR_Y of the screen");
_Static_assert(BONUS_BAR_SCANLINE_LONGS * LONG_BYTES == SCREEN_ROW_BYTES,
               "the bonus bar's copy loop is not one whole scanline");

/* One word of the four-word rectangle the two bar routines build in their own frame. */
#define BAR_PXY_WORD_BYTES 2u

static uint32_t bar_pxy_word(uint32_t rectangle, unsigned index) {
    return addr_add(rectangle, index * BAR_PXY_WORD_BYTES);
}

/* The bar's single scanline, work buffer to visible screen — the tail both bar routines share.
 * It ANSWERS the A2 the copy leaves (one longword past the row it wrote), because the next
 * `vr_recfl`'s trampoline files that register. */
static uint32_t present_bonus_scanline(uint8_t *image) {
    uint32_t src = addr_add(be32(image + A_screen_back), BONUS_BAR_ROW_OFFSET);
    uint32_t dst = addr_add(be32(image + A_screen_phys), BONUS_BAR_ROW_OFFSET);

    copy_longs_ascending(image, src, dst, BONUS_BAR_SCANLINE_LONGS);
    return addr_add(dst, BONUS_BAR_SCANLINE_LONGS * LONG_BYTES);
}

/* hud_draw_counters @ 0x113d2 — score, hi-score, room and lives, in text height 4 and pen 5. */
void hud_draw_counters(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t score_text = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_SCORE_TEXT));
    uint32_t hi_text = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_HI_TEXT));
    uint32_t room_text = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_ROOM_TEXT));
    uint32_t lives_text = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_LIVES_TEXT));

    vst_height(image, vdi_handle(image), HUD_TEXT_HEIGHT, A_text_char_w, A_text_char_h,
               A_text_cell_w, A_text_cell_h, saved);
    vst_color(image, vdi_handle(image), HUD_TEXT_PEN, saved);

    /* `itoa_padded` takes a LONG, and the room number is a word — so the routine keeps a widened
     * copy of it in a global of its own rather than on its stack. */
    wr32(image + A_hud_room_long, (uint32_t)(int32_t)word_at(image, A_room_number));

    itoa_padded(image, long_at(image, A_score), score_text, HUD_SCORE_DIGITS);
    itoa_padded(image, long_at(image, A_hi_score), hi_text, HUD_SCORE_DIGITS);
    itoa_padded(image, long_at(image, A_hud_room_long), room_text, HUD_ROOM_DIGITS);

    if (long_at(image, A_lives) < 0) {
        /* The last life is drawn as "0" and the counter is then normalised to exactly -1 — which
         * matters for a count that arrived at -2 or below, and is what `game_top_loop`'s
         * `cmpi.l #$ffffffff` ends the turn on. The zero really is stored before the format call:
         * `itoa_padded` is handed the GLOBAL, not a register holding the old value. */
        wr32(image + A_lives, 0);
        itoa_padded(image, long_at(image, A_lives), lives_text, HUD_LIVES_DIGITS);
        wr32(image + A_lives, (uint32_t)(int32_t)HUD_LIVES_EXHAUSTED);
    } else {
        itoa_padded(image, long_at(image, A_lives), lives_text, HUD_LIVES_DIGITS);
    }

    v_gtext(image, vdi_handle(image), HUD_COUNTER_X, HUD_ROW_TOP, score_text, saved);
    v_gtext(image, vdi_handle(image), HUD_COUNTER_X, HUD_ROW_BOTTOM, hi_text, saved);
    v_gtext(image, vdi_handle(image), HUD_ROOM_X, HUD_ROW_TOP, room_text, saved);
    v_gtext(image, vdi_handle(image), HUD_LIVES_X, HUD_ROW_BOTTOM, lives_text, saved);
}

/* hud_bonus_bar_fill @ 0x112c8 — one filled column per unit, from the bar's left end to its
 * current right end, each followed by the scanline copy that shows it. */
void hud_bonus_bar_fill(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    uint32_t rectangle = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_BAR_PXY));
    CallerAddressRegisters live = saved;
    int16_t column;

    set_word(image, bar_pxy_word(rectangle, HUD_PXY_Y1), BONUS_BAR_Y);
    set_word(image, bar_pxy_word(rectangle, HUD_PXY_Y2), BONUS_BAR_Y);
    vsf_color(image, vdi_handle(image), BONUS_BAR_PEN, live);

    /* `A_bonus_bar` is re-read every pass, as the `cmp.w -8038(a4),d0` at the bottom of the loop
     * is: a column the VDI drew over the global would change the bound mid-run. */
    for (column = BONUS_BAR_LEFT; column < word_at(image, A_bonus_bar); column++) {
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X1), column);
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X2), column);
        vr_recfl(image, vdi_handle(image), rectangle, live);
        live.a2 = present_bonus_scanline(image);
    }
}

/* hud_bonus_bar_shrink @ 0x11346 — erase `units` columns off the bar's right end in one rectangle.
 * The rectangle is built RIGHT to LEFT (x1 above x2), which the VDI normalises. */
void hud_bonus_bar_shrink(uint8_t *image, uint32_t frame, int16_t units,
                          CallerAddressRegisters saved) {
    uint32_t rectangle = addr_add(frame, sign_ext16((uint32_t)HUD_FRAME_BAR_PXY));

    set_word(image, bar_pxy_word(rectangle, HUD_PXY_Y1), BONUS_BAR_Y);
    set_word(image, bar_pxy_word(rectangle, HUD_PXY_Y2), BONUS_BAR_Y);

    /* The surviving column is one past what is erased. When fewer than BONUS_BAR_LEFT columns would
     * be left, the whole bar down to its floor is erased instead — from a FIXED right end, not from
     * wherever `A_bonus_bar` had got to. */
    if ((int16_t)(word_at(image, A_bonus_bar) - units + 1) < BONUS_BAR_LEFT) {
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X2), BONUS_BAR_LEFT);
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X1), BONUS_BAR_SHRINK_LEFT);
    } else {
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X2),
                 (int16_t)(word_at(image, A_bonus_bar) - units + 1));
        set_word(image, bar_pxy_word(rectangle, HUD_PXY_X1), word_at(image, A_bonus_bar));
    }

    vsf_color(image, vdi_handle(image), BONUS_BAR_ERASE_PEN, saved);
    vr_recfl(image, vdi_handle(image), rectangle, saved);
    present_bonus_scanline(image);
}

/* ================================================================================================
 * Glue. Alcyon/DRI C passes arguments on the stack (test/abi.py), so the oracle side of a case
 * pokes them at 4(A7) and the candidate side is handed the same values as C arguments here.
 * ============================================================================================= */

/* `get_pixel` answers in D0, and the Alcyon ABI's answer for a `short` is D0's LOW WORD — which is
 * what the battery compares against the oracle's register file. */
uint32_t g_get_pixel(const uint8_t *image, uint32_t x, uint32_t y) {
    return (uint16_t)get_pixel(image, (int16_t)x, (int16_t)y);
}

void g_bubble_collision_probe(uint8_t *image) { bubble_collision_probe(image); }
void g_reset_world_state(uint8_t *image) { reset_world_state(image); }
void g_save_world(uint8_t *image, uint32_t block) { save_world(image, block); }
void g_restore_world(uint8_t *image, uint32_t block) { restore_world(image, block); }

void g_itoa_padded(uint8_t *image, uint32_t value, uint32_t buffer, uint32_t width) {
    itoa_padded(image, (int32_t)value, buffer, (int16_t)width);
}

void g_ghost_blow_body(uint8_t *image) { ghost_blow_body(image); }

void g_frame_advance_bubble_frame(uint8_t *image) { frame_advance_bubble_frame(image); }
void g_frame_scale_mouse_to_ghost(uint8_t *image) { frame_scale_mouse_to_ghost(image); }

/* The caller's A1/A2 — the registers the two `Setcolor` trampolines file (see the core). */
void g_frame_blow_or_recover(uint8_t *image, uint32_t a1, uint32_t a2) {
    frame_blow_or_recover(image, caller_registers(a1, a2));
}

/* The three HUD painters: their own frame, and the caller's A1/A2 the GEM trampoline files. */
void g_hud_draw_counters(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    hud_draw_counters(image, frame, caller_registers(a1, a2));
}

void g_hud_bonus_bar_fill(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    hud_bonus_bar_fill(image, frame, caller_registers(a1, a2));
}

void g_hud_bonus_bar_shrink(uint8_t *image, uint32_t frame, uint32_t units, uint32_t a1,
                            uint32_t a2) {
    hud_bonus_bar_shrink(image, frame, (int16_t)units, caller_registers(a1, a2));
}

/* The two regions that used to sit BETWEEN the slices: the front-end poll and the death sequence.
 * `hud_frame` is the A6 `hud_draw_counters` runs on when the sequence calls it. */
uint32_t g_frame_poll_input(uint8_t *image, uint32_t a1, uint32_t a2) {
    return (uint16_t)frame_poll_input(image, caller_registers(a1, a2));
}

void g_frame_poll_pause(uint8_t *image, uint32_t a1, uint32_t a2) {
    frame_poll_pause(image, caller_registers(a1, a2));
}

void g_frame_death_sequence(uint8_t *image, uint32_t hud_frame, uint32_t a1, uint32_t a2) {
    frame_death_sequence(image, hud_frame, caller_registers(a1, a2));
}

void g_frame_step_facing(uint8_t *image) { frame_step_facing(image); }
void g_frame_apply_fans(uint8_t *image) { frame_apply_fans(image); }
uint32_t g_frame_step_live_bubble(uint8_t *image) {
    return (uint16_t)frame_step_live_bubble(image);
}
void g_frame_drift_pulse(uint8_t *image) { frame_drift_pulse(image); }
