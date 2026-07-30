/* wave.c — Joust's between-waves director: wave_manager @ 0x1783c.
 *
 * It is the game's largest routine (2660 bytes over two code chunks) and it is a state machine on
 * ONE byte, game_phase:
 *
 *   phase 0  the wave is being played. Once the last egg is gone and every object still on the
 *            playfield is a player, the wave is over: phase := 2, and one of the end-of-wave bonus
 *            banners goes up (survival / co-operation / conflict / bounty).
 *   phase 2  the bonus banners are up. game_phase doubles as a message GENERATION tag — the
 *            countdown holds while any message slot's MSG_KIND still equals it — so nothing moves
 *            until they expire, then phase := 1.
 *   phase 1  the next wave's banners are up ("WAVE nn", plus whichever special-wave announcement
 *            is due). Same hold; when they expire the phase reaches 0 and the wave starts.
 *
 * Starting a wave is the second chunk (0x17012): bump the wave number and its drawn digits, owe the
 * lava floor another five rows, arm the ground burn, load the platform layout and hand the
 * platforms that disappear to dissolve_platforms, recompute the rider speeds, then either scatter
 * this wave's eggs over the platforms or line up its riders to spawn.
 *
 * Faithfulness beats correctness here as everywhere: most of the banner posts DO NOT test what
 * find_free_message handed back, so a full message table sends a twelve-byte record to address 0
 * (see post_banner), and the egg placement leaves the type counts at -1 rather than at 0.
 */
#include "machine.h"

#include "wave.h"

/* The three rider groups a wave is built from, in the order every loop here walks them. The type
 * number is both the low bits of a spawned rider's flags word and the value an egg carries in
 * OBJ_EGG_SPAWN_FLAGS for the rider it will hatch into.
 *
 * `face_right_on_bit0` is data rather than a rule because the original makes it one: the three
 * spawn loops all `btst #0` the count still owed to pick a facing, but type 2's branch is the other
 * way round (`bne` where types 1 and 3 `beq`), so its riders face in antiphase with the rest.
 * Reproduced, not tidied. */
static const struct {
    uint32_t count_at;            /* where this group's owed-rider count lives */
    uint8_t type;
    uint8_t face_right_on_bit0;
} WAVE_GROUPS[] = {
    {A_wave_type1_count, 1, 1}, {A_wave_type2_count, 2, 0}, {A_wave_type3_count, 3, 1},
};
#define WAVE_GROUP_COUNT (sizeof WAVE_GROUPS / sizeof *WAVE_GROUPS)

/* =================================================================================================
 * The banners.
 * ============================================================================================= */

/* One posted message. The screen offsets and pixel shifts are pure layout — where on the 320x200
 * screen the text lands and how far into its leading cell — so they are spelled out in the table
 * below rather than named one by one; the string says what each banner is. `colour` is
 * draw_string's plane-select byte (see draw.h's A_text_color). */
typedef struct {
    uint32_t string;
    uint32_t dst_off;   /* added to screen_base */
    uint8_t kind;       /* the game_phase generation this banner holds up */
    uint8_t timer;
    uint8_t colour;
    uint8_t shift;
} Banner;

#define ANNOUNCE(str, off, colour, shift) \
    {(str), (off), WAVE_PHASE_ANNOUNCE, BANNER_FRAMES, (colour), (shift)}
#define BONUS(str, off, colour, shift) \
    {(str), (off), WAVE_PHASE_BONUS, BANNER_FRAMES, (colour), (shift)}

/* --- phase 1: the next wave's announcements --- */
static const Banner BANNER_PREPARE_TO_JOUST = ANNOUNCE(STR_PREPARE_TO_JOUST, 0x3238, 1, 0);
static const Banner BANNER_BUZZARD_BAIT =
    {STR_BUZZARD_BAIT, 0x44f8, WAVE_PHASE_ANNOUNCE, BUZZARD_BAIT_CUE, 1, 9};
static const Banner BANNER_WAVE_LABEL = ANNOUNCE(STR_WAVE, 0x2c00, 1, WAVE_LABEL_SHIFT_1DIGIT);
static const Banner BANNER_WAVE_NUMBER =
    ANNOUNCE(A_wave_num_text, 0x2c10, 1, WAVE_NUMBER_SHIFT_1DIGIT);
static const Banner BANNER_EGG_WAVE = ANNOUNCE(STR_EGG_WAVE, 0x3240, 1, 7);
static const Banner BANNER_SURVIVAL_WAVE = ANNOUNCE(STR_SURVIVAL_WAVE, 0x3238, 1, 7);
static const Banner BANNER_TEAM_WAVE = ANNOUNCE(STR_TEAM_WAVE, 0x3240, 1, 4);
static const Banner BANNER_TEAM_PLAY_BONUS = ANNOUNCE(STR_TEAM_PLAY_BONUS, 0x57a0, 1, 0xf);
static const Banner BANNER_PTERODACTYL_WAVE = ANNOUNCE(STR_PTERODACTYL_WAVE, 0x3238, 1, 2);
static const Banner BANNER_BEWARE_PTERO = ANNOUNCE(STR_BEWARE_PTERO, 0x3858, 1, 1);
static const Banner BANNER_GLADIATOR_WAVE = ANNOUNCE(STR_GLADIATOR_WAVE, 0x3238, 1, 4);
static const Banner BANNER_BOUNTY_OFFER = ANNOUNCE(STR_BOUNTY_OFFER, 0x57b0, 1, 1);
static const Banner BANNER_DISMOUNT_FIRST = ANNOUNCE(STR_DISMOUNT_FIRST, 0x5ca8, 1, 8);

/* --- phase 2: what the finished wave paid --- */
static const Banner BANNER_CO_OPERATION = BONUS(STR_CO_OPERATION, 0x5d30, 1, 8);
static const Banner BANNER_PLAYER_CONFLICT = BONUS(STR_PLAYER_CONFLICT, 0x5d38, 1, 0xa);
static const Banner BANNER_SURVIVAL_BONUS = BONUS(STR_SURVIVAL_BONUS, 0x5d40, 2, 0xc);
static const Banner BANNER_NO_BONUS = BONUS(STR_NO_BONUS, 0x5d58, 1, 0);
static const Banner BANNER_NO_BOUNTY = BONUS(STR_NO_BOUNTY, 0x5d50, 1, 0xd);
static const Banner BANNER_BOUNTY_TO_P1 = BONUS(STR_BOUNTY_COLLECTED, 0x5d20, 7, 0);
static const Banner BANNER_BOUNTY_TO_P2 = BONUS(STR_BOUNTY_COLLECTED, 0x5d80, 2, 2);

static void write_banner(uint8_t *image, uint32_t message, const Banner *banner, uint8_t shift) {
    wr32(image + message + MSG_STRING, banner->string);
    /* The original spells this as a `move.l` of screen_base followed by an `addi.l` to the same
     * word. Folding the two is exact: the intermediate is never read, and no slot this can land on
     * — a message record, or address 0 when the table is full — overlaps screen_base. */
    wr32(image + message + MSG_SCREEN_PTR, be32(image + A_screen_base) + banner->dst_off);
    image[message + MSG_KIND] = banner->kind;
    image[message + MSG_TIMER] = banner->timer;
    image[message + MSG_COLOR] = banner->colour;
    image[message + MSG_SHIFT] = shift;
}

/* Put `banner` in the first free message slot and hand back the slot.
 *
 * find_free_message returns 0 when all 24 slots are taken, and all but two of wave_manager's twenty
 * posts test nothing — so a full table writes the record over addresses 0..0xb, the bottom of the
 * 68000's vector page. Reproduced rather than guarded, exactly as player_death does.
 *
 * The wave label and the wave number choose their shift at the call site (the original writes
 * 3(a0) inside the branch that picked it), which is what the `_shifted` form is for. */
static uint32_t post_banner_shifted(uint8_t *image, const Banner *banner, uint8_t shift) {
    uint32_t message = find_free_message(image);
    write_banner(image, message, banner, shift);
    return message;
}

static uint32_t post_banner(uint8_t *image, const Banner *banner) {
    return post_banner_shifted(image, banner, banner->shift);
}

/* =================================================================================================
 * 68000 semantics this routine leans on.
 * ============================================================================================= */

/* `subq.b #1,<mem> ; bne` — the byte is stored and the branch tests the stored result, so a counter
 * of 0 wraps to 0xff and is 256 ticks from firing rather than already spent. */
static int tick_down_to_zero(uint8_t *image, uint32_t counter) {
    uint8_t left = (uint8_t)(image[counter] - 1u);
    image[counter] = left;
    return left == 0;
}

/* `subq.b #1,<mem> ; bge` — here the branch tests N == V, not the sign of the truncated byte, and
 * taking one off 0x80 overflows: the stored result is 0x7f but the comparison is NEGATIVE. Doing
 * the subtraction on the SIGNED byte at full precision reproduces exactly that. (src/input.c's
 * `subq_condition` is the same hazard, and it has bitten this project three times.) */
static int take_one_off_count(uint8_t *image, uint32_t counter) {
    int32_t left = (int8_t)image[counter] - 1;
    image[counter] = (uint8_t)left;
    return left >= 0;
}

/* =================================================================================================
 * Phase 1 — announcing the wave that is about to start.
 * ============================================================================================= */

/* Post the banners for the coming wave, once per game_phase tick down from 2 to 1.
 *
 * The four special-wave latches are one-shots armed by the bonus half below: each is taken down by
 * one here and announces itself as it lands on zero. Only the wave-number pair is posted every
 * time. */
static void announce_next_wave(uint8_t *image) {
    /* Wave 0 is the start of a game, and "PREPARE TO JOUST" goes into message slot 0 DIRECTLY —
     * no find_free_message, so it overwrites whatever was in that slot. */
    if (image[A_wave_num] == 0)
        write_banner(image, A_message_table, &BANNER_PREPARE_TO_JOUST,
                     BANNER_PREPARE_TO_JOUST.shift);

    /* From wave 9 on the drawn number is two digits wide, so the label slides left and the number
     * right to keep the pair centred. A SIGNED byte compare. */
    int two_digits = (int8_t)image[A_wave_num] >= WAVE_NUM_FIRST_2DIGIT;
    post_banner_shifted(image, &BANNER_WAVE_LABEL,
                        two_digits ? WAVE_LABEL_SHIFT_2DIGIT : WAVE_LABEL_SHIFT_1DIGIT);

    /* The wave NUMBER is the one announcement that checks the slot it was given. */
    uint32_t number = find_free_message(image);
    if (number != 0)
        write_banner(image, number, &BANNER_WAVE_NUMBER,
                     two_digits ? WAVE_NUMBER_SHIFT_2DIGIT : WAVE_NUMBER_SHIFT_1DIGIT);

    if (tick_down_to_zero(image, A_egg_wave_countdown)) post_banner(image, &BANNER_EGG_WAVE);

    if (tick_down_to_zero(image, A_team_wave_countdown)) {
        image[A_player_conflict_flag] = 0;
        if (image[A_players_alive] == 2) {
            post_banner(image, &BANNER_TEAM_WAVE);
            post_banner(image, &BANNER_TEAM_PLAY_BONUS);
        } else {
            post_banner(image, &BANNER_SURVIVAL_WAVE);
        }
    }

    if (tick_down_to_zero(image, A_ptero_wave_countdown)) {
        post_banner(image, &BANNER_PTERODACTYL_WAVE);
        post_banner(image, &BANNER_BEWARE_PTERO);
    }

    /* The gladiator wave is a two-player affair, so the latch is spent either way but only a
     * two-player game is told about it. */
    if (!tick_down_to_zero(image, A_gladiator_wave_countdown)) return;
    if (image[A_players_alive] != 2) return;
    image[A_first_dismount_owner] = 0;
    post_banner(image, &BANNER_GLADIATOR_WAVE);
    post_banner(image, &BANNER_BOUNTY_OFFER);
    post_banner(image, &BANNER_DISMOUNT_FIRST);
}

/* The one thing that happens while the countdown is HELD: on the very first wave, once
 * "PREPARE TO JOUST" has been up long enough for its timer to read exactly BUZZARD_BAIT_CUE,
 * "BUZZARD BAIT!" joins it — with that same timer, so the two clear together. */
static void post_buzzard_bait(uint8_t *image) {
    if (image[A_game_phase] != WAVE_PHASE_ANNOUNCE) return;
    if (image[A_wave_num] != 0) return;
    if (image[A_message_table + MSG_TIMER] != BUZZARD_BAIT_CUE) return;

    uint32_t message = find_free_message(image);
    if (message == 0) return;
    write_banner(image, message, &BANNER_BUZZARD_BAIT, BANNER_BUZZARD_BAIT.shift);
}

/* =================================================================================================
 * Phase 0 — the wave is over; pay for it.
 * ============================================================================================= */

/* Add WAVE_BONUS_THOUSANDS to a player's score. The caller adds straight into a digit BYTE and
 * score_update carries the decimal columns (see score.h's OBJ_SCORE_* comment). */
static void pay_wave_bonus_to_p1(uint8_t *image) {
    image[A_object_table + OBJ_SCORE_LIFE_DIGIT] += WAVE_BONUS_THOUSANDS;
    score_update_p1(image);
}

static void pay_wave_bonus_to_p2(uint8_t *image) {
    image[A_player2 + OBJ_SCORE_LIFE_DIGIT] += WAVE_BONUS_THOUSANDS;
    score_update_p2(image);
}

/* One player left on the board: the survival bonus, unless the two of them fought over it. */
static void pay_survival_bonus(uint8_t *image) {
    if (image[A_player_conflict_flag] != 0) {
        post_banner(image, &BANNER_NO_BONUS);
        return;
    }

    uint32_t message = post_banner(image, &BANNER_SURVIVAL_BONUS);
    if (be16(image + A_object_table + OBJ_FLAGS) == 0) {
        pay_wave_bonus_to_p2(image);
        return;
    }
    pay_wave_bonus_to_p1(image);
    /* score_update saves and restores A0 (`movem.l #$8080,-(a7)` / `#$0101`), so the record just
     * posted is still to hand: the banner is recoloured to player 1's after the fact. */
    image[message + MSG_COLOR] = BANNER_COLOR_P1;
}

/* Both players still on the board: 3000 each for co-operating, or nothing if they fought. */
static void pay_co_operation_bonus(uint8_t *image) {
    if (image[A_player_conflict_flag] != 0) {
        post_banner(image, &BANNER_PLAYER_CONFLICT);
        return;
    }
    post_banner(image, &BANNER_CO_OPERATION);
    /* Both digits are bumped BEFORE either score_update runs, so each repaint sees both scores
     * already credited. */
    image[A_object_table + OBJ_SCORE_LIFE_DIGIT] += WAVE_BONUS_THOUSANDS;
    image[A_player2 + OBJ_SCORE_LIFE_DIGIT] += WAVE_BONUS_THOUSANDS;
    score_update_p1(image);
    score_update_p2(image);
}

/* The gladiator wave's bounty: it is only ANNOUNCED here — no score is added on this path. */
static void announce_bounty(uint8_t *image) {
    int8_t owner = (int8_t)image[A_first_dismount_owner];
    if (owner == 1) post_banner(image, &BANNER_BOUNTY_TO_P1);
    else if (owner > 1) post_banner(image, &BANNER_BOUNTY_TO_P2);
    else post_banner(image, &BANNER_NO_BOUNTY);
}

/* The wave ends when the last egg is gone and every object still on the playfield is a player.
 * That moves the game to phase 2 and arms the NEXT special wave — the four latches are consulted in
 * a fixed order and exactly one is armed per wave, so the special waves cycle. Only the team latch
 * pays anything as it is armed; the other three simply take their turn. */
static void end_of_wave(uint8_t *image) {
    if (image[A_egg_count] != 0) return;
    if (image[A_players_alive] != image[A_live_object_count]) return;

    image[A_game_phase] = WAVE_PHASE_BONUS;

    if (image[A_team_wave_countdown] == 0) {
        image[A_team_wave_countdown] = SPECIAL_WAVE_LEAD;
        if (image[A_players_alive] == 1) pay_survival_bonus(image);
        else pay_co_operation_bonus(image);
        return;
    }
    if (image[A_egg_wave_countdown] == 0) {
        image[A_egg_wave_countdown] = SPECIAL_WAVE_LEAD;
        return;
    }
    if (image[A_ptero_wave_countdown] == 0) {
        image[A_ptero_wave_countdown] = SPECIAL_WAVE_LEAD;
        return;
    }
    if (image[A_gladiator_wave_countdown] != 0) return;
    image[A_gladiator_wave_countdown] = SPECIAL_WAVE_LEAD;
    if (image[A_players_alive] == 2) announce_bounty(image);
}

/* =================================================================================================
 * Starting the next wave @ 0x17012 — the second of wave_manager's two code chunks.
 * ============================================================================================= */

/* Bump the wave count, and the two ASCII digits the "WAVE nn" banner draws.
 *
 * The count stops climbing at WAVE_NUM_WRAP and drops back to WAVE_NUM_WRAP_TO, so the last ten
 * waves repeat for ever. The digits are carried by hand: '9' + 1 is ':', which is the cue to reset
 * to '0' and bump the tens — and the tens digit starts BLANK, so its first bump makes ' ' + 1 = '!'
 * and that is the cue to force it to '1'. */
static void bump_wave_number(uint8_t *image) {
    uint8_t wave = (uint8_t)(image[A_wave_num] + 1u);
    image[A_wave_num] = wave == WAVE_NUM_WRAP ? (uint8_t)WAVE_NUM_WRAP_TO : wave;

    uint8_t units = (uint8_t)(image[A_wave_num_units] + 1u);
    image[A_wave_num_units] = units;
    if (units != DIGIT_PAST_9) return;

    image[A_wave_num_units] = '0';
    uint8_t tens = (uint8_t)(image[A_wave_num_tens] + 1u);
    image[A_wave_num_tens] = tens == TENS_PAST_BLANK ? (uint8_t)TENS_FIRST : tens;
}

/* Waves 3 and 4 set the ground burning in from both ends; wave 4 starts it three cells further in
 * at each end, where both flames are fully on screen and neither needs clipping to one cell. */
static void arm_ground_burn(uint8_t *image) {
    uint32_t left = A_ground_anim + GA_FLAME_LEFT;
    uint32_t right = A_ground_anim + GA_FLAME_RIGHT;

    wr16(image + A_ground_anim + GA_ROWS_LATCH, 1);   /* > 0, which is what arms the routine */
    wr16(image + A_ground_anim + GA_ROWS, 0);         /* ...and it climbs up from no rows at all */
    wr32(image + left + SPR_SRC, FLAME_FRAME_FIRST);
    wr32(image + right + SPR_SRC,
         FLAME_FRAME_FIRST + GROUND_BURN_RIGHT_FRAME_INDEX * FLAME_FRAME_BYTES);
    wr32(image + left + SPR_DST_OFF, GROUND_BURN_WAVE3_LEFT_DST);
    wr32(image + right + SPR_DST_OFF, GROUND_BURN_WAVE3_RIGHT_DST);
    wr16(image + left + SPR_CELL_SELECT, GROUND_BURN_WAVE3_LEFT_CELLS);
    wr16(image + right + SPR_CELL_SELECT, GROUND_BURN_WAVE3_RIGHT_CELLS);
    wr16(image + left + SPR_SHIFT, GROUND_BURN_WAVE3_LEFT_SHIFT);
    wr16(image + right + SPR_SHIFT, GROUND_BURN_WAVE3_RIGHT_SHIFT);

    if (image[A_wave_num] == GROUND_BURN_FIRST_WAVE) return;

    wr32(image + left + SPR_DST_OFF, GROUND_BURN_WAVE4_LEFT_DST);
    wr32(image + right + SPR_DST_OFF, GROUND_BURN_WAVE4_RIGHT_DST);
    wr16(image + left + SPR_CELL_SELECT, GROUND_BURN_WAVE4_CELLS);
    wr16(image + right + SPR_CELL_SELECT, GROUND_BURN_WAVE4_CELLS);
    wr16(image + left + SPR_SHIFT, GROUND_BURN_WAVE4_LEFT_SHIFT);
    wr16(image + right + SPR_SHIFT, GROUND_BURN_WAVE4_RIGHT_SHIFT);
}

/* Load this wave's platform layout and rider counts — one longword out of A_wave_layout_table — and
 * hand the platforms that DISAPPEAR to dissolve_platforms.
 *
 * The seed really is `old AND NOT new`, which is what ../../names.txt claims at dissolve_platforms:
 * a platform that was there last wave and is not there this one gets an effect_table slot, and the
 * kind stored is 1-BASED (bit 0 of the mask is kind 1), which is why that routine indexes
 * platform_sprites one record low. Only EFF_KIND is written; the slot's other fields are whatever
 * the previous dissolve left, and dissolve_platforms rebuilds them when it sees EFF_TIMER at 0.
 *
 * The table index is `ext.w` then `mulu.w #4` — the wave number as a SIGNED BYTE, so a wave number
 * past 0x7f reads BELOW the table. */
static void load_wave_layout(uint8_t *image) {
    uint8_t was_present = image[A_wave_layout_mask];
    int16_t index = (int16_t)((int8_t)image[A_wave_num] * 4);
    /* Folded into one uint32_t before it reaches the pointer: `image + base + sign_ext16(...)`
     * would group as `(image + base) + <a huge positive ptrdiff>` and walk forwards instead. */
    uint32_t entry = A_wave_layout_table + sign_ext16((uint16_t)index);
    wr32(image + A_wave_layout_mask, be32(image + entry));

    uint8_t vanishing = (uint8_t)(was_present & ~image[A_wave_layout_mask]);
    uint32_t slot = A_effect_table;
    for (unsigned kind = 1; kind <= PLATFORM_COUNT; kind++) {
        int dissolving = vanishing & 1u;
        vanishing >>= 1;
        if (!dissolving) continue;
        wr16(image + slot + EFF_KIND, (uint16_t)kind);
        slot += EFF_RECORD;
    }

    /* ...and the same mask, one bit per byte, is what the platforms themselves are drawn from. */
    uint8_t present = image[A_wave_layout_mask];
    for (uint32_t at = A_platform_present; at < A_platform_present_END; at++) {
        image[at] = present & 1u;
        present >>= 1;
    }
}

/* Every fourth wave the type-1 riders get a notch faster, every eighth the type-2s and every
 * sixteenth the type-3s, each capped at RIDER_SPEED_MAX. The three come off ONE register that is
 * shifted further for each type, so the later types are always at or below the earlier ones.
 *
 * The wave number is decremented as a BYTE inside a word register, so wave 0 enters this as 0xff
 * and every type comes out at the cap.
 *
 * Returns that register as the egg placement's first rng_advance will see it — it is left in D0
 * across everything between, which is a real (if accidental) input to the random cursor. */
static uint16_t set_rider_speeds(uint8_t *image) {
    static const uint32_t SPEEDS[] = {A_speed_type1, A_speed_type2, A_speed_type3};
    uint16_t rank = (uint8_t)(image[A_wave_num] - 1u);

    rank = (uint16_t)(rank >> 2);               /* `lsr.w #2`, then `lsr.w #1` before each of the */
    wr16(image + A_speed_type1, rank);          /* other two, so the shifts are 2, 3 and 4 */
    rank = (uint16_t)(rank >> 1);
    wr16(image + A_speed_type2, rank);
    rank = (uint16_t)(rank >> 1);
    wr16(image + A_speed_type3, rank);

    for (unsigned type = 0; type < sizeof SPEEDS / sizeof *SPEEDS; type++) {
        int16_t speed = (int16_t)(be16(image + SPEEDS[type]) + 1u);
        wr16(image + SPEEDS[type], speed > RIDER_SPEED_MAX ? (uint16_t)RIDER_SPEED_MAX
                                                           : (uint16_t)speed);
    }
    return rank;
}

/* --- scattering this wave's eggs ------------------------------------------------------------- */

/* Give this egg the next rider type still owed, or say the wave is full.
 *
 * The type is written into the record BEFORE its count is tested, so a wave whose counts are all
 * spent still leaves the last (unused) record carrying type 3 — and every count ends at -1 rather
 * than 0, which is exactly what makes the rider-spawning loops below stand down. */
static int claim_rider_type(uint8_t *image, uint32_t object) {
    for (unsigned group = 0; group < WAVE_GROUP_COUNT; group++) {
        image[object + OBJ_EGG_SPAWN_FLAGS] = WAVE_GROUPS[group].type;
        if (take_one_off_count(image, WAVE_GROUPS[group].count_at)) return 1;
    }
    return 0;
}

/* Is the {platform, x} pair at `candidate` — the scratch slot one past the last accepted egg —
 * within EGG_SPREAD_GAP of an egg already placed on that same platform? The window is measured as
 * an UNSIGNED word from both ends, so it covers -8..+8. */
static int egg_is_crowded(const uint8_t *image, uint32_t candidate) {
    for (uint32_t placed = A_egg_spread_scratch; placed != candidate;
         placed += EGG_SPREAD_RECORD) {
        if (be16(image + placed) != be16(image + candidate)) continue;
        uint16_t gap = (uint16_t)(be16(image + placed + 2) - be16(image + candidate + 2));
        if (gap <= EGG_SPREAD_GAP || gap >= EGG_SPREAD_GAP_WRAPPED) return 1;
    }
    return 0;
}

/* Drop this wave's eggs on the platforms, one object slot at a time.
 *
 * Each egg picks a platform and an x within it from the program's own bytes (rng_ptr), and is
 * re-rolled until it lands somewhere that is neither a repeat of the last x nor within
 * EGG_SPREAD_GAP of an egg already on that platform. The {platform, x} pairs accepted so far are
 * kept in the padding after wave_manager's own code (A_egg_spread_scratch).
 *
 * `mix` is D0 as rng_advance sees it, which is a leftover: on the first roll it is what
 * set_rider_speeds left behind, and after that the masked platform selector. Only its low seven
 * bits reach the cursor (rng_advance masks with 0xfe), but they do reach it. draw_x is borrowed as
 * the "last accepted x" — nothing is being drawn — and it is cleared ONCE, outside the re-roll, so
 * that memory carries from one egg to the next. */
static void place_wave_eggs(uint8_t *image, uint16_t mix) {
    uint32_t object = A_enemy_objects;
    uint32_t placed_end = A_egg_spread_scratch;
    uint8_t hatch_timer = (uint8_t)(EGG_HATCH_TIMER_BASE - image[A_wave_num]);

    wr16(image + A_draw_x, 0);

    for (;;) {
        wr32(image + A_rng_ptr, be32(image + A_rng_ptr) + RNG_EGG_ADVANCE);
        rng_advance(image, mix);

        uint32_t cursor = be32(image + A_rng_ptr);
        uint16_t roll = (uint16_t)(be16(image + cursor) + be16(image + cursor + 2));
        if (roll == 0) { mix = 0; continue; }

        mix = (uint16_t)(roll & EGG_PLATFORM_SELECT_MASK);
        uint32_t platform = A_platform_table + mix;
        wr16(image + placed_end, mix);
        wr16(image + object + OBJ_EGG_Y,
             (uint16_t)(be16(image + platform + PLAT_Y0) + EGG_REST_ABOVE_PLATFORM));

        /* A second word pair off the cursor, reduced modulo the platform's width. A divu.w whose
         * quotient will not fit leaves the dividend alone, and the `swap` then reads its high half
         * — which is zero, since the dividend is a word sum. A platform of ZERO width is a 68000
         * divide-by-zero exception, so it is out of reach of the differential either way; the
         * shipped platform_table has none. */
        uint16_t span = (uint16_t)(be16(image + platform + PLAT_X1)
                                   - be16(image + platform + PLAT_X0));
        uint32_t spread = (uint16_t)(be16(image + cursor + 4) + be16(image + cursor + 6));
        if (spread == 0) continue;

        uint16_t offset = (uint16_t)(divu_w(spread, span) >> 16);   /* the `divu.w` + `swap` pair */
        if (offset == be16(image + A_draw_x)) continue;
        wr16(image + A_draw_x, offset);

        uint16_t x = (uint16_t)(offset + be16(image + platform + PLAT_X0));
        wr16(image + object + OBJ_EGG_X, x);
        wr16(image + placed_end + 2, x);
        if (egg_is_crowded(image, placed_end)) continue;

        placed_end += EGG_SPREAD_RECORD;
        image[object + OBJ_EGG_FALL_TIMER] = EGG_REST_FALL_TIMER;
        image[object + OBJ_EGG_ROLL_TIMER] = EGG_REST_ROLL_TIMER;
        hatch_timer = (uint8_t)(hatch_timer + EGG_HATCH_TIMER_STEP);
        image[object + OBJ_EGG_HATCH_TIMER] = hatch_timer;
        image[object + OBJ_EGG_ROWS] = EGG_REST_ROWS;
        wr32(image + object + OBJ_EGG_DST, be32(image + A_screen_base));
        wr32(image + object + OBJ_EGG_SRC, A_egg_sprite_still);

        if (!claim_rider_type(image, object)) return;

        image[object + OBJ_EGG_STATE] = EGG_STATE_RESTING;
        object += OBJ_SIZE;
        if (object >= A_object_table_END) return;   /* `cmpa.l` + `bcs` — UNSIGNED */
    }
}

/* --- arming the pterodactyls and lining up the riders ----------------------------------------- */

/* Reload the pterodactyl scheduler and clear every slot. On a pterodactyl wave the first slot is
 * armed at once, and from wave PTERO_FIRST_ARMED_WAVE on it arrives almost immediately. */
static void arm_pterodactyls(uint8_t *image) {
    uint16_t interval = (uint16_t)(SPAWN_INTERVAL_BASE
                                   - (uint16_t)(image[A_wave_num] << SPAWN_INTERVAL_WAVE_SHIFT));
    wr16(image + A_spawn_interval, interval);
    wr16(image + A_spawn_timer, interval);

    for (uint32_t slot = A_pterodactyl_table; slot < A_pterodactyl_table_END; slot += PT_RECORD)
        wr16(image + slot + PT_FLAGS, 0);

    if (image[A_ptero_wave_countdown] != 0) return;
    wr16(image + A_pterodactyl_table + PT_FLAGS, 1);
    /* `cmpi.b #$f ; bls` — an UNSIGNED byte compare. */
    if (image[A_wave_num] >= PTERO_FIRST_ARMED_WAVE)
        wr16(image + A_spawn_timer, PTERO_IMMEDIATE_TIMER);
}

/* Fill the next object slots with this group's riders, all awaiting respawn. Bit 0 of the count
 * still owed picks each one's facing, which is why they alternate — see WAVE_GROUPS for the sense
 * of that test, which type 2 takes the other way round. */
static uint32_t spawn_rider_group(uint8_t *image, uint32_t object, unsigned group) {
    uint32_t count_at = WAVE_GROUPS[group].count_at;
    if ((int8_t)image[count_at] <= 0) return object;

    do {
        uint16_t flags = (uint16_t)(OBJ_FLAG_RESPAWN | WAVE_GROUPS[group].type);
        if ((image[count_at] & 1u) == WAVE_GROUPS[group].face_right_on_bit0)
            flags |= OBJ_FLAG_FACING_RIGHT;
        wr16(image + object + OBJ_FLAGS, flags);

        object += OBJ_SIZE;
        image[count_at] = (uint8_t)(image[count_at] - 1u);
    } while (image[count_at] != 0);
    return object;
}

/* Everything a new wave needs: the count, the floor, the burn, the layout, the speeds, then either
 * this wave's eggs or its riders. The two are alternatives — the egg placement spends the same
 * three type counts the rider loops read, leaving them negative — which is how an egg wave has no
 * riders in it. */
static void start_next_wave(uint8_t *image) {
    bump_wave_number(image);

    /* The opening waves owe the lava another five rows each, so the floor builds up over them. */
    if ((int8_t)image[A_wave_num] <= FLOOR_LAST_WAVE) {
        image[A_floor_rows_left] += FLOOR_ROWS_PER_WAVE;
        image[A_floor_step_timer] = FLOOR_STEP_FRAMES;
    }
    if ((int8_t)image[A_wave_num] >= GROUND_BURN_FIRST_WAVE
        && (int8_t)image[A_wave_num] <= GROUND_BURN_LAST_WAVE)
        arm_ground_burn(image);

    load_wave_layout(image);
    image[A_flap_delay] = (uint8_t)(FLAP_DELAY_BASE - ((image[A_wave_num] >> 4) + 1u));

    /* A new wave breaks both players' egg chains and forgets who was hunting whom. */
    image[A_object_table + OBJ_EGG_CHAIN] = 0;
    image[A_player2 + OBJ_EGG_CHAIN] = 0;
    wr16(image + A_hunter_counts, 0);

    uint16_t rng_mix = set_rider_speeds(image);

    /* Wipe the whole enemy area — flags, physics, egg sub-records and all — then rewind the
     * round-robin spawn cursor. */
    for (uint32_t at = A_enemy_objects; at != A_object_table_END; at += 2) wr16(image + at, 0);
    image[A_spawn_in_progress] = 0;
    wr32(image + A_spawn_point_cursor, A_spawn_points);

    if (image[A_egg_wave_countdown] == 0) place_wave_eggs(image, rng_mix);

    arm_pterodactyls(image);

    uint32_t object = A_enemy_objects;
    for (unsigned group = 0; group < WAVE_GROUP_COUNT; group++)
        object = spawn_rider_group(image, object, group);
}

/* =================================================================================================
 * wave_manager @ 0x1783c — the dispatcher.
 * ============================================================================================= */

/* Is anything still holding the between-waves countdown? Three things can: a message of the current
 * generation still on screen, a pterodactyl still in the air, or — on wave 3 alone — the ground
 * burn still running. */
static int countdown_is_held(const uint8_t *image) {
    for (uint32_t message = A_message_table; message != A_message_table_END;
         message += MSG_RECORD)
        if (image[message + MSG_KIND] == image[A_game_phase]) return 1;

    for (uint32_t slot = A_pterodactyl_table; slot != A_pterodactyl_table_END; slot += PT_RECORD)
        if (be16(image + slot + PT_FLAGS) != 0) return 1;

    return image[A_wave_num] == GROUND_BURN_FIRST_WAVE
           && (int16_t)be16(image + A_ground_anim + GA_ROWS_LATCH) > 0;
}

void wave_manager(uint8_t *image) {
    if (image[A_game_phase] == WAVE_PHASE_PLAYING) {
        end_of_wave(image);
        return;
    }

    if (countdown_is_held(image)) {
        post_buzzard_bait(image);
        return;
    }

    image[A_game_phase]--;
    if (image[A_game_phase] == 0) start_next_wave(image);
    else announce_next_wave(image);
}

void g_wave_manager(uint8_t *image) { wave_manager(image); }
