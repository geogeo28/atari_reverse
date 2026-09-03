/* zynaps_cheats.c — the trainer: a key watcher on the shim's ACIA path, and three pokes.
 *
 * THIS IS THE ONE PLACE THIS PROJECT DELIBERATELY DIVERGES FROM THE 1988 BINARY, and it is written
 * so that the divergence can be MEASURED rather than believed:
 *
 *   * NO CORE IS EDITED. Everything here is shim code in atari/. The frame differential
 *     (`make test`) does not move, and build.sh's three core-containment gates still hold.
 *   * NOTHING FIRES UNTIL A PLAYER ARMS IT. Every judged smoke mode — title, titlefault, game,
 *     gamefault, floppy — asserts that the counts this file publishes are all still zero at the end
 *     of the run (smoke.py's `check_the_trainer_stayed_dormant`). A watcher that had started poking
 *     on its own would redden every one of them.
 *   * EVERY BYTE IT WRITES IS A BYTE THE GAME ALREADY READS, at an address a VERIFIED core names in
 *     one of ../include's headers. Nothing here invents a location, and nothing writes hardware.
 *
 * HOW IT IS ARMED. Hold Z, Y and N together for CHEAT_ARM_HOLD_VBLS vertical blanks — about two
 * seconds — while the TITLE/ATTRACT screen is up. Releasing any of the three resets the timer, and
 * the combo is refused outside that screen. On arming, one of the game's own ORPHANED sound effects
 * plays: the secrets hunt proved nine of the forty-five streams unreachable from any call site
 * (README.md, "Secrets and dead code"), and the trainer resurrects FOUR of them — the arming
 * fanfare and one per cheat key.
 *
 * WHAT THE KEYS DO, once armed and inside the frame loop:
 *   F1  toggle invulnerability   F2  lives back to CHEAT_LIVES   F3  every power-up to its ceiling
 *
 * WHERE THE WORK HAPPENS, AND WHY IT IS SPLIT IN TWO. The ACIA door (`zy_cheat_note_ikbd_byte`) is
 * entered from inside the KEYBOARD interrupt, once per byte the controller sends, so it does the
 * least possible: it maintains a three-byte held-set and latches a bit per cheat key pressed. The
 * state machine — the hold timer, the arming, the jingle and the pokes — runs from `zy_cheats_tick`
 * in the VERTICAL BLANK, after the program's own handler has finished for that frame. Both are
 * interrupts, so every store either one makes into THIS FILE'S OWN STATE is a single 68000
 * instruction and cannot be split by the other: MFP channel 6 is level 6 and the vertical blank is
 * level 4, so the keyboard can interrupt the tick but never the reverse. `take_pending_fire` and the
 * door's `|=` are a `bclr`/`bset` pair on the same byte for exactly that reason — a plain
 * "read, use, clear" would drop a key pressed in between. Measured on the emitted code
 * (`build/zynaps.dis`): `and.b #imm,<abs>` and `or.b #imm,<abs>`, one instruction each.
 *
 * THAT ARGUMENT IS ABOUT THIS FILE'S BYTES AND NOT ABOUT THE IMAGE'S, and the difference is a real
 * residual. The pokes below write bytes the MAIN LINE read-modify-writes over several instructions
 * — `frame_decay_timer` (../src/frame.c) does `wr16(t, be16(t) - 1)` and then steps a level — and
 * the vertical blank preempts the main line. A poke landing inside that window is partly undone:
 * F3 pressed on the one frame the shield timer is being stepped can leave the shield at 2 rather
 * than 3 until the next press. It cannot be fixed from this side (we are the interrupt, not the
 * thing being interrupted) and it is a few instructions' window out of ~400,000 cycles a frame, so
 * it is recorded in README.md's Trainer section rather than papered over.
 */
#include <stdint.h>

#include "machine.h"       /* wr16 — the three decay timers are words */

#include "highscore.h"     /* A_scancode_to_char_table, NAME_ENTRY_SCANCODE_MAX */
#include "hud.h"           /* A_lives, A_panel_redraw_mask, A_power_gauge_display, the panel bits */
#include "irq.h"           /* the ACIA handler's own packet state, and its press/release rule */
#include "player.h"        /* A_ship_speed_level, A_weapon_power_level, A_weapon_decay_timer, ... */
#include "sound.h"         /* sound_start — the feedback, in the game's own driver */
#include "weapon.h"        /* the ceilings, the three shield/speed globals, A_selected_weapon */
#include "zynaps_cheats.h"
#include "zynaps_target.h" /* zy_image_base */

#ifdef ZY_CHEATS

/* ================================================================================================
 * The keys.
 *
 * THE THREE COMBO LETTERS ARE LETTERS, NOT SCANCODES, and that distinction is the whole of the
 * French-keyboard problem. An ST keyboard sends POSITION codes: the key that says `Z` on a UK
 * machine and the key that says `Z` on a French AZERTY machine are different keys and send
 * different bytes. The game ships one table that turns a scancode into a character —
 * `scancode_to_char_table` @ 0x19a39, 115 bytes, read by the high-score name entry — so the combo
 * is spelt as the three CHARACTERS and the scancodes are looked up in that table at boot. That
 * makes the trainer's combo the same LETTERS the game itself would print for those keys, and it
 * moves on its own if a localised build ever ships a different table.
 *
 * ...AND THE SHIPPED TABLE IS A PURE QWERTY MAP, WHICH IS WHY THERE IS A SECOND SET. Measured over
 * the 115 bytes: 0x2c spells `Z`, 0x15 `Y`, 0x31 `N` — UK/US positions, with no layout switch
 * anywhere in the image. A French ST's `Z` key sends 0x11 (where QWERTY has `W`) and no table in
 * this program says so, so the lookup alone cannot cover the machine this build is played on. Each
 * combo letter therefore accepts TWO scancodes: the one the game's own table resolves, and the one
 * the letter sits at on AZERTY. `Y` and `N` do not move between the two layouts, so for those two
 * the pair collapses to one code; only `Z` really has two, and the cost of that is that `W`+`Y`+`N`
 * also arms the trainer on a QWERTY keyboard. That is a cheat combo, not a game control, and being
 * armable on both machines is worth more than being unique on one. README.md states it.
 * ============================================================================================= */

/* Where each combo letter sits on a French AZERTY keyboard — the half no table in this image holds.
 * `Z` is at QWERTY's `W` position; `Y` and `N` are at the same position on both layouts, so their
 * codes here equal what the game's table resolves and the pair is a single code in practice. */
#define CHEAT_AZERTY_SCANCODE_Z 0x11u
#define CHEAT_AZERTY_SCANCODE_Y 0x15u
#define CHEAT_AZERTY_SCANCODE_N 0x31u

/* The three cheat keys, and they need no layout argument at all: the function-key block sits above
 * the letters and sends the same scancodes on every ST keyboard. Nothing in the game reads them —
 * `scancode_to_char_table` holds 0xff for all three and the only other scancode compares in the
 * program are SPACE (the pause), `1` and `2` (the menu) — so a press cannot collide with a control.
 */
#define CHEAT_KEY_INVULNERABLE 0x3bu   /* F1 */
#define CHEAT_KEY_LIVES        0x3cu   /* F2 */
#define CHEAT_KEY_POWER        0x3du   /* F3 */

/* About two seconds at 50 Hz. Long enough that the three keys cannot be hit together by accident
 * while a player is thumping the keyboard at the title, short enough to be a hold and not a wait. */
#define CHEAT_ARM_HOLD_VBLS 100u

/* What F2 puts in `A_lives`. The byte is unclamped and the panel's icon row is six wide, so nine
 * lives draw six full icons and the other three are real but off the panel. Nothing above 0x7f may
 * ever go here: `life_icon_for_slot` (../src/hud.c) reads the byte SIGNED, so 0x80 and up draw six
 * EMPTY icons over a full stock. */
#define CHEAT_LIVES 9u

/* ================================================================================================
 * The sounds — four of the game's nine unreachable streams, brought back.
 *
 * README.md's "Secrets and dead code" proves ids 19, 23, 25, 29, 35, 37, 38, 42 and 43 unreachable:
 * every one of the 23 instructions that reaches `sound_start` was followed through the spawn, jump
 * and swap graph, and those nine are in no closure. Each is a complete stream — its own `fa`
 * channel header, its own `$e1` terminator — so each plays as its author left it. Using them for
 * the trainer's feedback is the archaeology, not decoration: they are the only sounds in this
 * program a player of the original could never have heard.
 *
 * THE CHANNEL ARGUMENT IS IGNORED FOR ALL FOUR, and that is a property of the streams rather than a
 * guess: `sound_start` overwrites its `channel` parameter from the stream's own `fa <code>` header
 * when there is one, and all nine orphans carry one (../src/sound.c). So the value passed is
 * whatever the caller held, exactly as it is at the game's own call sites, and 0 is spelt here to
 * say that nothing was chosen.
 * ============================================================================================= */
#define CHEAT_SFX_ARMED         0x23u  /* 35 — 2.0 s, `fa 03`; channel code 3 occurs on no
                                        * reachable stream at all, which makes it the fanfare */
#define CHEAT_SFX_INVULNERABLE  0x13u  /* 19 — the only orphan armed on VOICE 1, so the toggle is
                                        * heard over whatever the other two voices are playing */
#define CHEAT_SFX_LIVES         0x25u  /* 37 — one of the pair 42/43 shadow */
#define CHEAT_SFX_POWER         0x26u  /* 38 — ...and the other */
#define CHEAT_SOUND_CHANNEL_IGNORED 0u

/* ================================================================================================
 * The state. Everything the ACIA interrupt writes and the vertical blank reads is `volatile`.
 * ============================================================================================= */

/* One combo letter: the character the game's table spells it as, the AZERTY position no table
 * holds, and what the lookup found. */
struct cheat_combo_key {
    uint8_t letter;
    uint8_t azerty_scancode;
    uint8_t resolved_scancode;   /* 0 = the game's table does not spell this letter */
};

static struct cheat_combo_key g_combo[CHEAT_COMBO_KEYS] = {
    {'Z', CHEAT_AZERTY_SCANCODE_Z, 0},
    {'Y', CHEAT_AZERTY_SCANCODE_Y, 0},
    {'N', CHEAT_AZERTY_SCANCODE_N, 0},
};

/* One byte per combo letter — set by its press, cleared by its release. A byte each rather than
 * bits of one mask so that the door's store is a `move.b` with nothing to read first. */
static volatile uint8_t g_held[CHEAT_COMBO_KEYS];

/* One bit per cheat key pressed and not yet acted on. `bset` from the keyboard interrupt, `bclr`
 * from the vertical blank — see this file's header on why neither may be a load/modify/store. */
#define CHEAT_FIRE_BIT_INVULNERABLE 0u
#define CHEAT_FIRE_BIT_LIVES        1u
#define CHEAT_FIRE_BIT_POWER        2u
/* HOW MANY CHEAT KEYS THERE ARE, which is NOT how many letters spell the combo. The two are
 * unrelated quantities that both happen to be 3 today, and `g_fires` below is indexed by the bits
 * above — so sizing it with `CHEAT_COMBO_KEYS` would put a fourth cheat key's count one past the
 * array, into the next static, from inside an interrupt and with no diagnostic. */
#define CHEAT_KEY_COUNT 3u
static volatile uint8_t g_pending_fires;

static volatile uint8_t g_arming_window_open;
static volatile uint8_t g_play_window_open;

static uint8_t g_armed;
static uint32_t g_hold_vbls;
static uint32_t g_arm_jingles;
static uint32_t g_fires[CHEAT_KEY_COUNT];    /* indexed by CHEAT_FIRE_BIT_* — F1, F2, F3 */

/* The two read-backs zynaps_cheats.h describes: the panel mask after each poke that asked for a
 * repaint, and the tune the arming fanfare actually armed. Both are the GAME'S bytes read again
 * after the write, and both are gone by the time anything outside could sample them. */
static uint8_t g_panel_requests;
static uint32_t g_jingle_stream;

/* Ask the panel for one element through the GAME'S OWN writer, then keep the bit only if the mask
 * really carries it afterwards. The union over every poke is one field saying which bits the
 * trainer got into that byte.
 *
 * ONLY THE BIT THAT WAS ASKED FOR, never the whole mask — a first draft ORed `image[...]` in whole
 * and would have credited the trainer with bits the GAME set in the same frame (`frame_decay_timer`
 * sets the gauge bit on its own whenever the shield steps down), so a poke that asked for the wrong
 * element could still have shown the right bits. What this cannot pin is `A_panel_redraw_mask`
 * itself: the same address is written and read. */
static void request_panel_repaint(uint8_t *image, unsigned bit) {
    panel_request_repaint(image, bit);
    if (image[A_panel_redraw_mask] & (uint8_t)(1u << bit))
        g_panel_requests |= (uint8_t)(1u << bit);
}

/* ================================================================================================
 * Resolving the combo letters against the game's own table.
 * ============================================================================================= */
void zy_cheats_resolve_scancodes(const uint8_t *image) {
    for (unsigned key = 0; key < CHEAT_COMBO_KEYS; key++) {
        g_combo[key].resolved_scancode = 0;
        /* Scancode 0 is not a key, and skipping it means a letter the table does not spell leaves
         * `resolved_scancode` at 0 where nothing can match it. */
        for (unsigned code = 1; code <= NAME_ENTRY_SCANCODE_MAX; code++)
            if (image[A_scancode_to_char_table + code] == g_combo[key].letter) {
                g_combo[key].resolved_scancode = (uint8_t)code;
                break;
            }
    }
}

/* Which combo letter a scancode is, or CHEAT_COMBO_KEYS for none. */
static unsigned combo_key_for_scancode(uint8_t scancode) {
    if (scancode == 0)                       /* never a key, and the "unresolved" sentinel */
        return CHEAT_COMBO_KEYS;
    for (unsigned key = 0; key < CHEAT_COMBO_KEYS; key++)
        if (scancode == g_combo[key].resolved_scancode || scancode == g_combo[key].azerty_scancode)
            return key;
    return CHEAT_COMBO_KEYS;
}

/* ================================================================================================
 * THE ACIA DOOR — one raw byte from the keyboard controller, as `ikbd_acia_isr` pops it.
 *
 * It is called from `hw_read8` (shim_include/hw.h) at the one address that is the 6850's DATA port,
 * so it sees every byte the game's own handler sees, at the same moment and before that handler has
 * decided anything. That is the only place a RELEASE is visible: the program keeps one byte,
 * `A_key_scancode`, which holds the key currently down and is cleared only by its own release — so
 * three keys held together cannot be read out of the image at all.
 *
 * WHICH BYTES ARE KEYS is decided out of the program's OWN packet state rather than by guessing.
 * `ikbd_acia_service_one_byte` (../src/irq.c) reads `A_ikbd_packet_remaining` before it pops the
 * port, so at the instant this runs that byte still says whether the controller is mid-way through
 * a three-byte joystick report; and 0xfd is the header that starts one. Everything else is a
 * scancode, split into press and release by the program's own rule — `cmp.b #$fd,d1` + `bmi`, which
 * is a SIGNED comparison and not a test of bit 7, so 0x7d..0x7f take the release arm and 0xfe/0xff
 * take the press arm. That is the instruction the original executes; it is transcribed rather than
 * corrected here for the same reason ../src/irq.c transcribes it, and the keyboard sends none of
 * the five.
 * ============================================================================================= */
void zy_cheat_note_ikbd_byte(uint8_t byte) {
    const uint8_t *image = zy_image_base;
    uint8_t scancode;
    unsigned key;

    if (image[A_ikbd_packet_remaining] != 0)      /* a joystick report's payload */
        return;
    if (byte == IKBD_JOYSTICK_HEADER)             /* ...and the header that armed it */
        return;

    if ((int8_t)(uint8_t)(byte - IKBD_JOYSTICK_HEADER) < 0) {
        scancode = (uint8_t)(byte & (uint8_t)~KEY_RELEASE_BIT);
        key = combo_key_for_scancode(scancode);
        if (key < CHEAT_COMBO_KEYS)
            g_held[key] = 0;
        return;
    }

    key = combo_key_for_scancode(byte);
    if (key < CHEAT_COMBO_KEYS) {
        g_held[key] = 1;
        return;
    }
    /* The three cheat keys are latched rather than acted on: this is inside the keyboard interrupt,
     * and a poke made here would land in the middle of whatever frame the main line is drawing. */
    if (byte == CHEAT_KEY_INVULNERABLE)
        g_pending_fires |= (uint8_t)(1u << CHEAT_FIRE_BIT_INVULNERABLE);
    else if (byte == CHEAT_KEY_LIVES)
        g_pending_fires |= (uint8_t)(1u << CHEAT_FIRE_BIT_LIVES);
    else if (byte == CHEAT_KEY_POWER)
        g_pending_fires |= (uint8_t)(1u << CHEAT_FIRE_BIT_POWER);
}

/* ================================================================================================
 * The three pokes.
 *
 * EVERY ADDRESS IS A CORE HEADER'S, EVERY CEILING IS THE GAME'S OWN. Nothing below chooses a
 * number: `WEAPON_POWER_LEVEL_MAX`, `SHIELD_LEVEL_MAX`, `SHIP_SPEED_LEVEL_MAX` and
 * `POWERUP_DECAY_TICKS` are the constants ../src/weapon.c's five commit arms write, spelt in
 * ../include/weapon.h and ../include/player.h as the instructions that test them.
 * ============================================================================================= */

static void cheat_toggle_invulnerable(uint8_t *image) {
    /* Read by exactly three sites — the two landscape collisions (0x11e66, 0x11eb2) and the lethal
     * entity touch (0x13d0e) — and written by NOTHING in the shipped program: a dormant flag the
     * author left wired up and never set. Any non-zero value suppresses all three. */
    image[A_ship_invulnerable] = (uint8_t)!image[A_ship_invulnerable];
    sound_start(image, CHEAT_SFX_INVULNERABLE, CHEAT_SOUND_CHANNEL_IGNORED);
}

static void cheat_refill_lives(uint8_t *image) {
    image[A_lives] = CHEAT_LIVES;
    /* The panel's own request bit. Bit 4 is the odd one of the five: the frame head has no `bclr`
     * for it, because `draw_lives_icons` clears it itself once it has drawn — so asking here is
     * exactly what the extra-life award at 0x12e36 does, and the row repaints on the next frame. */
    request_panel_repaint(image, PANEL_REDRAW_LIVES_BIT);
    sound_start(image, CHEAT_SFX_LIVES, CHEAT_SOUND_CHANNEL_IGNORED);
}

static void cheat_max_powerups(uint8_t *image) {
    /* The five commit arms' stores, at their ceilings, in one go — see README.md's Trainer section
     * for the arm-by-arm mapping. `A_power_gauge_display` is the HUD's mirror of the shield level
     * and `powerup_upgrade_shield` writes the two together (0x13f5e), so they are written together
     * here. `A_selected_weapon` takes the SEEKER: it is the one weapon whose arm does not clear the
     * shots already in flight, and the fire dispatcher reads 4 for it (0x113d0). */
    image[A_weapon_power_level] = WEAPON_POWER_LEVEL_MAX;
    image[A_shield_level] = SHIELD_LEVEL_MAX;
    image[A_power_gauge_display] = SHIELD_LEVEL_MAX;
    image[A_selected_weapon] = WEAPON_KIND_SEEKER;
    /* THE SPEED LEVEL'S REAL CEILING IS 1 AND NOT 8. `A_ship_speed_table` @ 0x19370 holds exactly
     * TWO eight-byte entries and what follows the second is a relocated pointer, so a level of 2
     * indexes out of the table into pointer bytes and flies the ship at a garbage delta. The
     * capsule's own arm cannot be borrowed as a bound either: its clamp is an EQUALITY (`cmpi.b
     * #$2` + `bne`), so a byte already past 2 walks straight on. `SHIP_SPEED_LEVEL_MAX` is the
     * value that arm writes back, and it is the highest this may ever be. */
    image[A_ship_speed_level] = SHIP_SPEED_LEVEL_MAX;
    /* The three decay timers, refilled exactly as the arms refill them. Each counts down and takes
     * one level away when it reaches zero (`frame_decay_timer`, ../src/frame.c), so a maxed ship
     * starts losing levels about a thousand frames from here — F3 again is the answer, and
     * README.md says so rather than this file freezing a timer the game means to run. */
    wr16(image + A_weapon_decay_timer, POWERUP_DECAY_TICKS);
    wr16(image + A_shield_decay_timer, POWERUP_DECAY_TICKS);
    wr16(image + A_speed_decay_timer, POWERUP_DECAY_TICKS);
    /* THESE THREE STORES ARE UNPINNED ON TARGET, and saying so is better than the counter that used
     * to sit here. It read the three words back straight after writing them, through the SAME
     * `A_*_decay_timer` expressions — so it returned 3 whatever the addresses were, including for
     * the defect its own failure message named. Nor can `smoke.py` take the measurement from
     * outside: the timers tick once a frame AND the section start has just set them to this same
     * ceiling, so a value read a few frames after the press is a few short of full whether the
     * trainer wrote it or not (measured: 967/966/964 against 1000, from a run in which all three
     * had landed). The addresses are the ones ../include/weapon.h and ../include/player.h give the
     * game's own commit arms, and `make test` pins those arms; nothing on target distinguishes this
     * refill from the section's. README.md's Trainer section carries it as a residual. */
    /* THE THREE LAUNCH-STOCK COUNTERS ARE NOT TOUCHED, and leaving them out is a measurement rather
     * than an omission: `A_missile_launch_counter`/`_bomb_`/`_seeker_` (0x198b5/6/8) are written by
     * the section restart and decremented by the three launchers, and NOTHING IN THE IMAGE READS
     * ONE — no branch anywhere tests them, and 0x198b8 is never even initialised. What actually
     * bounds firing is the in-flight count, which the two levels above already max. Poking them
     * would look like an effect and be none. */
    request_panel_repaint(image, PANEL_REDRAW_POWERUP_BIT);
    request_panel_repaint(image, PANEL_REDRAW_WEAPON_BIT);
    request_panel_repaint(image, PANEL_REDRAW_GAUGE_BIT);
    sound_start(image, CHEAT_SFX_POWER, CHEAT_SOUND_CHANNEL_IGNORED);
}

/* ================================================================================================
 * The state machine — one vertical blank of it.
 * ============================================================================================= */

/* Claim one pending cheat key, as a `bclr` the keyboard interrupt's `bset` cannot be lost under. */
static unsigned take_pending_fire(unsigned bit) {
    if ((g_pending_fires & (1u << bit)) == 0)
        return 0;
    g_pending_fires &= (uint8_t)~(1u << bit);
    return 1;
}

static unsigned the_whole_combo_is_held(void) {
    for (unsigned key = 0; key < CHEAT_COMBO_KEYS; key++)
        if (!g_held[key])
            return 0;
    return 1;
}

static void arm_the_trainer(uint8_t *image) {
    g_armed = 1;
    g_arm_jingles++;
    sound_start(image, CHEAT_SFX_ARMED, CHEAT_SOUND_CHANNEL_IGNORED);
    /* WHAT THE DRIVER WAS ACTUALLY ARMED WITH, read back out of the voice record. The fanfare's
     * stream opens `fa 03` and channel code 3 is `voice_for_channel`'s fall-through, so it is voice
     * 3's record that was rewritten; the RESTART pointer is the one of the three `sound_start`
     * writes that the interpreter does not then walk, so it still holds the stream's head a frame
     * later. `smoke.py` predicts the value with its own port of `sound_lookup_tune`. */
    g_jingle_stream = be32(image + A_sound_voice3 + VOICE_STREAM_RESTART);
}

/* Act on whatever keys were pressed since the last vertical blank, counting each. The count is the
 * surface: `smoke.py` reads it back out of the record, and a cheat that fired when it should not
 * have shows up as a number no judged mode is allowed to have. */
static void serve_pending_fires(uint8_t *image) {
    if (take_pending_fire(CHEAT_FIRE_BIT_INVULNERABLE)) {
        cheat_toggle_invulnerable(image);
        g_fires[CHEAT_FIRE_BIT_INVULNERABLE]++;
    }
    if (take_pending_fire(CHEAT_FIRE_BIT_LIVES)) {
        cheat_refill_lives(image);
        g_fires[CHEAT_FIRE_BIT_LIVES]++;
    }
    if (take_pending_fire(CHEAT_FIRE_BIT_POWER)) {
        cheat_max_powerups(image);
        g_fires[CHEAT_FIRE_BIT_POWER]++;
    }
}

void zy_cheats_tick(void) {
    uint8_t *image = zy_image_base;

    if (!g_armed) {
        /* A key released — or the wrong screen — puts the timer back to nothing. */
        if (g_arming_window_open && the_whole_combo_is_held()) {
            if (++g_hold_vbls >= CHEAT_ARM_HOLD_VBLS)
                arm_the_trainer(image);
        } else {
            g_hold_vbls = 0;
        }
    }
    if (g_armed && g_play_window_open)
        serve_pending_fires(image);
    else
        g_pending_fires = 0;   /* a press outside the frame loop is dropped, never banked */
}

void zy_cheats_arming_window(unsigned open) {
    /* THE HELD-SET STARTS EMPTY EVERY TIME THE WINDOW OPENS, and that is a recovery rather than
     * tidiness: a letter is cleared only by its own BREAK code arriving at the ACIA, so one lost
     * break — an overrun while interrupts are masked through a floppy read, say — would latch that
     * letter for the rest of the run and leave the combo armable by the other two alone. Clearing
     * here bounds the damage to one pass of the attract loop and costs a fresh press.
     *
     * `g_hold_vbls` is NOT cleared here: `zy_cheats_tick`'s own `else` zeroes it on every vertical
     * blank the window is shut or the set incomplete, and one writer for one piece of state is the
     * whole of why that reset lives there. */
    for (unsigned key = 0; key < CHEAT_COMBO_KEYS; key++)
        g_held[key] = 0;
    g_arming_window_open = (uint8_t)(open != 0);
}

void zy_cheats_play_window(unsigned open) {
    g_play_window_open = (uint8_t)(open != 0);
}

void zy_cheats_report(struct zy_cheat_counts *out) {
    out->armed = g_armed;
    out->arm_jingles = g_arm_jingles;
    out->invulnerable_fires = g_fires[CHEAT_FIRE_BIT_INVULNERABLE];
    out->lives_fires = g_fires[CHEAT_FIRE_BIT_LIVES];
    out->power_fires = g_fires[CHEAT_FIRE_BIT_POWER];
    out->panel_requests = g_panel_requests;
    out->jingle_stream = g_jingle_stream;
    for (unsigned key = 0; key < CHEAT_COMBO_KEYS; key++)
        out->scancode[key] = g_combo[key].resolved_scancode;
}

#else /* !ZY_CHEATS */

/* THE PURIST BUILD — `ZY_NOCHEATS=1 bash atari/build.sh <mode>`, which is an ENVIRONMENT VARIABLE
 * and not a mode of its own (build.sh's `case` would reject one). It compiles this arm instead: six
 * empty functions, no watcher, no key table, no pokes. `smoke.py` tells this build's zeros from a
 * dormant trainer's by asking the ELF whether the watcher's data is in it at all and comparing that
 * against the record's `cheats_built`. The floppy is NOT rebuilt for this: README.md says why one
 * disk carries the dormant watcher.
 *
 * `zy_cheat_note_ikbd_byte` IS DEFINED HERE TOO, and that is the point of it being here rather than
 * behind an `#ifdef` in shim_include/hw.h: the tap's CALL is unconditional, so the verified cores
 * compile to the same machine code in both builds and `ZY_CHEATS` reaches no core translation unit.
 * That header's own note carries the argument. */
void zy_cheat_note_ikbd_byte(uint8_t byte) { (void)byte; }
void zy_cheats_resolve_scancodes(const uint8_t *image) { (void)image; }
void zy_cheats_arming_window(unsigned open) { (void)open; }
void zy_cheats_play_window(unsigned open) { (void)open; }
void zy_cheats_tick(void) { }

/* A WHOLE-STRUCT ZERO rather than a field list, so a member added to `struct zy_cheat_counts` and
 * forgotten here cannot reach `g_record` as stack garbage — which would report the purist build's
 * trainer as having fired. */
void zy_cheats_report(struct zy_cheat_counts *out) {
    struct zy_cheat_counts nothing = {0};

    *out = nothing;
}

#endif /* ZY_CHEATS */
