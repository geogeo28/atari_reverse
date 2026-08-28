/* audiotest.c — the harness that proves the two audio modules on a machine. TWO .PRGs, one source.
 *
 * It plays a song for DEMO_FRAMES vblanks, fires every SFX in the catalogue in turn every
 * SFX_INTERVAL_FRAMES, measures what one music tick costs, puts the machine back the way it found
 * it, and writes a binary ledger the host reads (verify.py). Nothing here is part of the audio
 * API — a game calls ym_music_* and dma_sfx_*; this file is the surface that says they work.
 *
 * BLACKICE_MODE picks WHICH material is under test, and nothing else:
 *   0  AUDIOTEST.PRG — mk_song.py's demo tune and mk_samples.py's six placeholders.
 *   1  BICETEST.PRG  — the BLACK ICE score (songs/blackice.py) and its ten cues
 *                      (songs/blackice_sfx.py). Adds the one thing the demo has no material for:
 *                      a SONG SCHEDULE that walks the title theme, the score at all four trace
 *                      band tempi, and the three one-shot songs, on the frames a recording can be
 *                      held to. Building it from this file rather than a second harness is what
 *                      keeps the ledger, the vblank install and the teardown one implementation.
 *
 * WHERE THE TICK IS INSTALLED, AND WHY IT IS THE _vblqueue AND NOT VECTOR $70.
 * TOS's own level-4 handler is not a formality: it reloads the shifter's screen base from
 * _v_bas_ad, runs the cursor and mouse timers, honours _vblsem, and counts _frclock. Taking $70
 * means either reproducing that or breaking it, and a chained handler has to get its own
 * register save, its interrupt-priority state and the hand-off order right — three chances to
 * introduce a fault that only shows on one TOS. The queue is the hook TOS publishes for exactly
 * this: one longword to write, one to put back, our routine runs AFTER the housekeeping and in
 * supervisor mode (which is what the PSG and the DMA registers need), and it does not run at all
 * while _vblsem says the OS is inside a critical section — which is the behaviour we want, not a
 * limitation. The cost is that a free slot must exist; install_vbl_tick refuses loudly if none
 * does, rather than running with no music.
 */
#include <stdint.h>

#include "dma_sfx.h"
#include "ym_music.h"
#if BLACKICE_MODE
#include "blackice_sfx_bank.h"
#include "blackice_sfx_ids.h"
#include "blackice_song.h"
#else
#include "sfx_bank.h"
#include "sfx_ids.h"
#include "song_data.h"
#endif

/* ------------------------------------------------------------------- TOS, from audio_os.s ----- */

long Fcreate(const char *name, short attr);
long Fwrite(short handle, long count, const void *buf);
long Fclose(short handle);
long Super(void *stack);
long audio_leave_supervisor(void *ssp);
void audio_vbl_entry(void);

/* --------------------------------------------------------------------- TOS system variables --- */

typedef void (*VblRoutine)(void);

#define VBL_QUEUE_LENGTH  ((volatile uint16_t *)0x00000454UL)      /* _nvbls  */
#define VBL_QUEUE         ((VblRoutine *volatile *)0x00000456UL)   /* _vblqueue */
#define HZ200_COUNTER     ((volatile uint32_t *)0x000004BAUL)      /* _hz_200 */

#define VBL_SLOT_FREE     ((VblRoutine)0)
#define VBL_SLOT_NONE     0xFFFF                                   /* "no slot was taken" */

/* READING PAGE ZERO, and the only place in this build where -Warray-bounds is turned off.
 *
 * To GCC a dereference of $454 or $4ba is an array subscript far outside any object it knows about
 * — right on a host, wrong on a machine whose OS publishes its state down there. The suppression is
 * scoped to these three accessors, so every real array in this file is still checked. It used to be
 * a build-wide -Wno-array-bounds, which bought quiet for three reads by disarming the warning for
 * every array in every file; that is the trade this replaces. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"

static uint32_t hz200_counter(void)
{
    return *HZ200_COUNTER;
}

static VblRoutine *vbl_queue(void)
{
    return *VBL_QUEUE;
}

static uint16_t vbl_queue_length(void)
{
    return *VBL_QUEUE_LENGTH;
}

#pragma GCC diagnostic pop

/* -------------------------------------------------------------- the material under test ------- */

/* The two builds differ in WHICH song bank, WHICH sample bank and WHICH catalogue they drive; from
 * here down the harness only ever names these. Each blob is named WITH its length, because that is
 * how the audio API takes it: the generators emit a *_BYTES macro beside every array, so neither
 * this file nor a game has a number to invent or to keep in step by hand. */
#if BLACKICE_MODE
#define LEDGER_NAME        "BICELOG.BIN"
#define SFX_CATALOGUE_SIZE BLACKICE_SFX_COUNT
#define SFX_PRIORITY       blackice_sfx_priority
#define SAMPLE_BANK        blackice_sfx_bank
#define SAMPLE_BANK_BYTES  BLACKICE_SFX_BANK_BYTES
#define FIRST_SONG         blackice_title
#define FIRST_SONG_BYTES   BLACKICE_TITLE_BYTES
#else
#define LEDGER_NAME        "AUDIOLOG.BIN"
#define SFX_CATALOGUE_SIZE SFX_COUNT
#define SFX_PRIORITY       sfx_priority
#define SAMPLE_BANK        sfx_bank
#define SAMPLE_BANK_BYTES  SFX_BANK_BYTES
#define FIRST_SONG         demo_song
#define FIRST_SONG_BYTES   DEMO_SONG_BYTES
#endif

/* ------------------------------------------------------------------------ the run's shape ----- */

#if BLACKICE_MODE

/* THE BLACK ICE TIMELINE, in vblanks. Every boundary is a frame the recording is held to, and the
 * three long windows are long on purpose:
 *   1..400        the title theme alone — no cue fires, and the score has not been bound. Its
 *                 drone holds each note two rows (0.48 s), so this is the window verify.py
 *                 measures pitch in. The title's own drum lane DOES play here; it carries no kick
 *                 for exactly that reason (songs/README.md 5).
 *   401..1400     the score, ONE blob, re-tempoed at each band boundary. 250 frames (5 s) a band
 *                 because the tempo check reads the row rate off the recording's own amplitude
 *                 envelope, and telling 4.55 Hz from 5.00 Hz needs a window several seconds long.
 *   1401..2400    band 3 held for 20 s: the DRUM WINDOW. Every lane hit in it is written to the
 *                 ledger with the frame it fired on, and the host identifies each one in the
 *                 recording. No cue fires here, so every drum that is refused is a defect.
 *   2450..2900    one cue a second, the ten fired once each, over the score at band 3.
 *   2970..2972    the priority probe (below).
 *   3030, 3230    the death and level-clear stings, each given more frames than it lasts.
 *   3480..        the 100% exfil pulse.
 *   ..3700        the tail. */
#define BICE_TITLE_FRAMES      400u
#define BICE_BAND_FRAMES       250u
#define BICE_SCORE_FRAME       (BICE_TITLE_FRAMES + 1u)
#define BICE_BAND_FRAME(band)  (BICE_SCORE_FRAME + (band) * BICE_BAND_FRAMES)
/* The drum window opens where band 3's tempo window closes and holds ONE tempo for 20 s. The
 * lane's rows land at the row rate, so a window that spanned a speed change would have the host
 * predicting hit times through a tempo schedule; holding band 3 makes the ledger's own frame
 * numbers the whole timeline. */
#define BICE_DRUM_FIRST_FRAME  (BICE_BAND_FRAME(3u) + BICE_BAND_FRAMES)
#define BICE_DRUM_FRAMES      1000u
#define BICE_DRUM_LAST_FRAME   (BICE_DRUM_FIRST_FRAME + BICE_DRUM_FRAMES)
#define BICE_DEATH_FRAME      3030u
#define BICE_CLEAR_FRAME      3230u
#define BICE_EXFIL_FRAME      3480u

#define DEMO_FRAMES           3700u
#define SFX_FIRST_FRAME       2450u
#define SFX_INTERVAL_FRAMES     50u
#define SFX_LAST_FRAME        2900u

/* Past 2960, which is where the rotation's last cue — the 1.20 s exfil siren fired at 2900 — stops
 * sounding. The probe claims the voice with that same siren, and starting it while the first one
 * is still playing would cut short the sound the rotation is being judged on: a defect in the
 * TEST, and a recording cannot tell that from a defect in the player. */
#define PROBE_FRAME_CLAIM     2970u
#define PROBE_FRAME_LOWER     2971u
#define PROBE_FRAME_PREEMPT   2972u
/* Priority 3 claims, priority 1 is refused under it, and priority 3 — EQUAL, not higher — takes it
 * back. Equal preempting is DESIGN.md 16's rule stated without ambiguity, and it is the half of
 * the rule a "strictly greater" implementation would still pass a lower-loses test with. */
#define PROBE_SFX_CLAIM        SFX_EXFIL_SIREN   /* priority 3, the longest sample in the bank */
#define PROBE_SFX_LOWER        SFX_BUSTER_SHOT   /* priority 1 */
#define PROBE_SFX_PREEMPT      SFX_TRACE_ALARM   /* priority 3 */

#else

/* THE DEMO'S TIMELINE, in vblanks, and every boundary in it is something the recording has to be
 * able to see:
 *   1..299     music alone — a window with nothing but the tune in it, which verify.py's pitch
 *              check needs, and long enough to reach the second pattern where the lead enters, so
 *              that check covers two channels and not just the bass.
 *   300..850   one SFX every second, the six cycled twice. The last one is an interval short of
 *              the end so the longest sample in the bank finishes before the teardown: a sound cut
 *              off by the teardown is a defect in the TEST, and a recording cannot tell the two
 *              apart.
 *   900..902   the priority probe (below).
 *   ..950      the tail. */
#define DEMO_FRAMES            950u
#define SFX_FIRST_FRAME        300u
#define SFX_INTERVAL_FRAMES     50u
#define SFX_LAST_FRAME         850u

/* THE PRIORITY PROBE: three requests on three consecutive frames, which is the only part of the
 * run that exercises a REFUSAL. Nothing in the rotation above can — the sounds are a second apart
 * and the longest is under one — so without this the "lower priority loses" half of both players
 * would ship untested. A long, high-priority sound is started, a low-priority one is asked for
 * while it is still playing (must be refused), and then a higher-priority one (must take it). */
#define PROBE_FRAME_CLAIM      900u
#define PROBE_FRAME_LOWER      901u
#define PROBE_FRAME_PREEMPT    902u
#define PROBE_SFX_CLAIM        SFX_ENEMY_DEATH   /* priority 5, 0.75 s — still sounding two frames
                                                  * later, which is what the probe needs */
#define PROBE_SFX_LOWER        SFX_DOOR          /* priority 2 */
#define PROBE_SFX_PREEMPT      SFX_GUNSHOT       /* priority 6 */

#endif /* BLACKICE_MODE */

/* The frame loop's own dead-man's handle, in 200 Hz ticks. If the vblank never arrives the loop
 * must end anyway — a hung .PRG under `--run-vbls` looks exactly like a slow one. DERIVED from the
 * timeline: a 50 Hz frame is four 200 Hz ticks, plus five seconds of slack, so a longer run
 * cannot be cut off by a limit somebody forgot to move. */
#define HZ200_PER_VBL           4u
#define FRAME_LOOP_SLACK_HZ200  1000u   /* 5 s */
#define FRAME_LOOP_LIMIT_HZ200  (DEMO_FRAMES * HZ200_PER_VBL + FRAME_LOOP_SLACK_HZ200)

/* The tick measurement: two timed loops, one empty and one calling the tick, each counted in 200 Hz
 * ticks. The host does the arithmetic (verify.py) — this side only counts, so the .PRG needs no
 * 32-bit divide.
 *
 * THE TWO ITERATION COUNTS DIFFER ON PURPOSE, and it is what makes the subtraction mean anything.
 * TOS's own vblank and 200 Hz handlers run inside both loops and inflate each by a share of its
 * ELAPSED TIME, so the two only cancel when both loops last about as long — a 2,000-call empty loop
 * finishes inside one 200 Hz tick, measures 0, and hands the tick every interrupt of a one-second
 * run. Both counts below are chosen for roughly half a second. */
#define BENCH_IDLE_ITERATIONS 200000UL
#define BENCH_TICK_ITERATIONS   2000UL
#define BENCH_EDGE_SPIN_LIMIT 200000u /* bounded, so a machine with Timer C off cannot hang here */

/* --------------------------------------------------------------------------- the ledger ------- */

#define LEDGER_MAGIC     0x41554431UL   /* 'AUD1' */
#define LEDGER_VERSION   6
/* THE SLOT COUNT IS FIXED, because verify.py's `>%dI` unpack is one shape for both builds — but
 * each build's timeline produces a different number of events, so the count is ASSERTED against
 * the timeline rather than checked by hand. Without this, a build whose rotation outgrew the
 * ledger would silently drop the events past the end (tally_sfx guards the store) and hand the
 * host a short, plausible-looking list. */
#define PROBE_EVENT_COUNT 3
#define SFX_EVENT_COUNT   (1u + (SFX_LAST_FRAME - SFX_FIRST_FRAME) / SFX_INTERVAL_FRAMES \
                           + PROBE_EVENT_COUNT)
#define LEDGER_SFX_SLOTS 16
typedef char ledger_has_a_slot_for_every_sfx_event[LEDGER_SFX_SLOTS >= SFX_EVENT_COUNT ? 1 : -1];

/* THE DRUM WINDOW'S HITS, one packed word each: the frame it fired on, and the bank sample index
 * the lane named. Packed because the host's whole use of it is "which sample, at which frame", and
 * two parallel arrays of 160 would be 640 bytes of .PRG for no more information.
 *
 * The slot count covers the window at the FASTEST tempo the window is ever played at — one hit per
 * row, and a row is BAND_SPEEDS[3] frames — with room over. Only hits inside the window are
 * recorded; the title's and the exfil pulse's lanes still play, they are simply not the evidence. */
#define LEDGER_DRUM_SLOTS       160
#define LEDGER_DRUM_INDEX_MASK  0xFFu
#define LEDGER_DRUM_FRAME_SHIFT 8

#if BLACKICE_MODE
/* One hit per row is the most a lane can carry, and the window's rows are its frames divided by
 * the fastest speed it is ever played at. Asserted rather than counted by hand: a window that
 * outgrew the array would silently record only its first 160 hits, and the host would measure a
 * short list without knowing it was short. */
#define DRUM_WINDOW_MAX_HITS (BICE_DRUM_FRAMES / BLACKICE_FASTEST_BAND_SPEED + 1u)
typedef char ledger_has_a_slot_for_every_drum_hit[LEDGER_DRUM_SLOTS >= DRUM_WINDOW_MAX_HITS
                                                  ? 1 : -1];
#endif
#define LEDGER_ATTR      0

/* Every field is a 32-bit big-endian word, so the struct has no padding and verify.py's `>%dI`
 * unpack is the whole parser. */
typedef struct {
    uint32_t magic;
    uint32_t version;
    /* WHERE TOS PUT US. A .PRG's load address is the OS's next free block, so it cannot be known
     * host-side; one known symbol's runtime address is what lets verify.py place the ELF's symbols
     * for Hatari's profiler. */
    uint32_t text_probe;
    uint32_t machine_has_dma;
    uint32_t song_accepted;
    uint32_t bank_accepted;
    uint32_t vbl_slot;
    uint32_t frames_run;
    uint32_t hz200_elapsed;        /* over the frame loop: turns frames into real time, measured */
    uint32_t bench_idle_iterations;
    uint32_t bench_hz200_idle;     /* the empty body, i.e. the loop and the call overhead */
    uint32_t bench_tick_iterations;
    uint32_t bench_hz200_tick;     /* the same loop with ym_music_tick in it */
    uint32_t sfx_events;
    uint32_t dma_starts;
    uint32_t ym_starts;
    uint32_t sfx_refused;
    uint32_t probe_claim_started;   /* the priority probe's three answers, in order */
    uint32_t probe_lower_started;   /* ...this one must be 0: a quieter claim loses */
    uint32_t probe_preempt_started;
    uint32_t drum_requests;         /* every hit the lane published, over the whole run */
    /* How many of them the DMA voice TOOK — not how many were heard. On a frame carrying both a
     * lane hit and a cue, the drum starts first and the cue overwrites it microseconds later; the
     * hardware saw both starts, which is why the trace check sums this with the cue count. */
    uint32_t drum_started;
    uint32_t drum_window_hits;      /* how many are recorded below */
    uint32_t drum_window_started;   /* ...and how many of those started the voice. No cue fires
                                     * inside the window, so a difference is a defect. */
    uint32_t sfx_frame[LEDGER_SFX_SLOTS];
    uint32_t sfx_index[LEDGER_SFX_SLOTS];
    uint32_t drum_hit[LEDGER_DRUM_SLOTS];   /* (frame << 8) | bank sample index */
} AudioTestLedger;

static AudioTestLedger ledger;

/* ------------------------------------------------------------------------- the frame state ---- */

static volatile uint32_t frame_counter;
static uint16_t sfx_countdown;
static uint8_t next_sfx;
static uint16_t vbl_slot_taken = VBL_SLOT_NONE;

/* ------------------------------------------------------------------------ the song schedule --- */

#if BLACKICE_MODE

/* One entry per song change the run performs. THE FOUR TRACE BANDS ARE NOT FOUR SONGS: bands 1-3
 * carry no blob, because DESIGN.md 16 makes the tempo the meter and the driver can be re-tempoed
 * where it stands — ym_music_set_speed replaces the frames-per-row ym_music_init read out of the
 * header, and the loop plays on from the row it was on. A cue with a blob re-binds and restarts;
 * BAND_FROM_BLOB means "do not override the frames-per-row that blob's own header carries", which
 * is what the three one-shot songs want — their tempo is their own, not a trace band's. */
#define BAND_FROM_BLOB 0xFFu

typedef struct {
    uint32_t frame;
    const unsigned char *song;   /* 0 = keep playing what is bound, and only change the tempo */
    uint32_t bytes;              /* that blob's length, for ym_music_init to check it against */
    uint8_t band;                /* index into BLACKICE_BAND_SPEED, or BAND_FROM_BLOB */
} SongCue;

static const SongCue song_schedule[] = {
    { BICE_BAND_FRAME(0u), blackice_score, BLACKICE_SCORE_BYTES, 0u },
    { BICE_BAND_FRAME(1u), 0,              0u,                   1u },
    { BICE_BAND_FRAME(2u), 0,              0u,                   2u },
    { BICE_BAND_FRAME(3u), 0,              0u,                   3u },
    { BICE_DEATH_FRAME,    blackice_death, BLACKICE_DEATH_BYTES, BAND_FROM_BLOB },
    { BICE_CLEAR_FRAME,    blackice_clear, BLACKICE_CLEAR_BYTES, BAND_FROM_BLOB },
    { BICE_EXFIL_FRAME,    blackice_exfil, BLACKICE_EXFIL_BYTES, BAND_FROM_BLOB },
};
#define SONG_CUE_COUNT ((uint8_t)(sizeof song_schedule / sizeof song_schedule[0]))

static uint8_t next_cue;

/* Every blob in the schedule was already accepted once, before the frame loop started (see
 * bind_songs), so a re-init here cannot fail — which is why this returns nothing to record. */
static void apply_song_cue(const SongCue *cue)
{
    if (cue->song != 0) {
        ym_music_init(cue->song, cue->bytes);
    }
    if (cue->band != BAND_FROM_BLOB) {
        ym_music_set_speed(BLACKICE_BAND_SPEED[cue->band]);
    }
    if (cue->song != 0) {
        ym_music_start();
    }
}

static void step_song_schedule(void)
{
    while (next_cue < SONG_CUE_COUNT && frame_counter >= song_schedule[next_cue].frame) {
        apply_song_cue(&song_schedule[next_cue]);
        next_cue++;
    }
}

#endif /* BLACKICE_MODE */

/* --------------------------------------------------------------------------- firing an SFX ---- */

/* Fire one SFX down the path this MACHINE has, and this is the routing a game wants.
 *
 * THE CHOICE IS ON THE HARDWARE, NOT ON THE ANSWER. Falling back to the YM whenever dma_sfx_play
 * returns 0 would look like robustness and is the opposite: on an STE a 0 means a HIGHER-priority
 * sample is still playing, and the "fallback" would then steal a music channel to play the very
 * sound the priority just said to drop. dma_sfx_available answers a question about the machine, so
 * it is the one that decides. */
static int sfx_fire(uint8_t index)
{
    if (dma_sfx_available()) {
        return dma_sfx_play(index, SFX_PRIORITY[index]);
    }
    return ym_music_sfx_play(index);
}

static void tally_sfx(uint8_t index, int started)
{
    uint32_t slot = ledger.sfx_events;

    if (!started) {
        ledger.sfx_refused++;
    } else if (dma_sfx_available()) {
        ledger.dma_starts++;
    } else {
        ledger.ym_starts++;
    }
    if (slot < LEDGER_SFX_SLOTS) {
        ledger.sfx_frame[slot] = frame_counter;
        ledger.sfx_index[slot] = index;
    }
    ledger.sfx_events++;
}

static void fire_next_sfx(void)
{
    uint8_t index = next_sfx;

    next_sfx++;
    if (next_sfx >= SFX_CATALOGUE_SIZE) {
        next_sfx = 0;
    }
    tally_sfx(index, sfx_fire(index));
}

static void run_priority_probe(void)
{
    if (frame_counter == PROBE_FRAME_CLAIM) {
        ledger.probe_claim_started = (uint32_t)sfx_fire(PROBE_SFX_CLAIM);
        tally_sfx(PROBE_SFX_CLAIM, (int)ledger.probe_claim_started);
    } else if (frame_counter == PROBE_FRAME_LOWER) {
        ledger.probe_lower_started = (uint32_t)sfx_fire(PROBE_SFX_LOWER);
        tally_sfx(PROBE_SFX_LOWER, (int)ledger.probe_lower_started);
    } else if (frame_counter == PROBE_FRAME_PREEMPT) {
        ledger.probe_preempt_started = (uint32_t)sfx_fire(PROBE_SFX_PREEMPT);
        tally_sfx(PROBE_SFX_PREEMPT, (int)ledger.probe_preempt_started);
    }
}

#if BLACKICE_MODE

/* THE FOURTH TRACK, and the whole of the platform's part in it. The driver published a bank index
 * for this row; this hands it to the DMA voice at YM_DRUM_PRIORITY, which is 0 — below every cue,
 * so a gunshot always cuts a hi-hat and a hi-hat never cuts a gunshot.
 *
 * It is called IMMEDIATELY after ym_music_tick, in the same vblank, because ym_music.h's take is a
 * read then a clear and a tick landing between the two would throw the hit away.
 *
 * On a plain ST dma_sfx_play refuses and writes no $ffff89xx byte, so this costs one refused call
 * a row and the lane simply does not exist — which is why channel C still carries a full YM kit. */
static void fire_drum_hit(void)
{
    uint16_t hit = ym_music_take_drum_hit();
    int started;

    if (hit == YM_DRUM_NONE) {
        return;
    }
    started = dma_sfx_play((uint8_t)hit, YM_DRUM_PRIORITY);
    ledger.drum_requests++;
    if (started) {
        ledger.drum_started++;
    }
    if (frame_counter >= BICE_DRUM_FIRST_FRAME && frame_counter < BICE_DRUM_LAST_FRAME
        && ledger.drum_window_hits < LEDGER_DRUM_SLOTS) {
        ledger.drum_hit[ledger.drum_window_hits] =
            (frame_counter << LEDGER_DRUM_FRAME_SHIFT) | (hit & LEDGER_DRUM_INDEX_MASK);
        ledger.drum_window_hits++;
        ledger.drum_window_started += (uint32_t)started;
    }
}

#endif /* BLACKICE_MODE */

/* The body audio_os.s's audio_vbl_entry calls, once per vblank, from TOS's queue walk. */
void audio_vbl_tick(void)
{
    frame_counter++;
#if BLACKICE_MODE
    step_song_schedule();
#endif
    ym_music_tick();
#if BLACKICE_MODE
    fire_drum_hit();
#endif

    if (frame_counter > SFX_LAST_FRAME) {
        run_priority_probe();
        return;
    }
    if (frame_counter < SFX_FIRST_FRAME) {
        return;
    }
    if (sfx_countdown != 0) {
        sfx_countdown--;
        return;
    }
    fire_next_sfx();
    sfx_countdown = SFX_INTERVAL_FRAMES - 1;
}

/* ------------------------------------------------------------------ installing and removing --- */

static uint16_t install_vbl_tick(void)
{
    VblRoutine *slots = vbl_queue();
    uint16_t count = vbl_queue_length();
    uint16_t slot;

    for (slot = 0; slot < count; slot++) {
        if (slots[slot] == VBL_SLOT_FREE) {
            slots[slot] = audio_vbl_entry;
            return slot;
        }
    }
    return VBL_SLOT_NONE;
}

static void remove_vbl_tick(uint16_t slot)
{
    if (slot != VBL_SLOT_NONE) {
        vbl_queue()[slot] = VBL_SLOT_FREE;
    }
}

/* --------------------------------------------------------------------- measuring the tick ----- */

typedef void (*BenchBody)(void);

/* noinline, both of them: an empty body the compiler can SEE it is calling costs nothing at all,
 * and the baseline then measures zero — a wrong subtraction rather than a small one. */
__attribute__((noinline)) static void bench_idle(void)
{
}

__attribute__((noinline)) static void bench_tick(void)
{
    ym_music_tick();
}

/* 200 Hz ticks spent running `body` `iterations` times. Called through a pointer so the compiler
 * cannot inline either body: the idle run then carries the SAME loop and call overhead as the
 * loaded one, and the subtraction host-side leaves the tick alone. TOS's own 200 Hz handler runs
 * during both and cancels the same way. */
static uint32_t bench_hz200(BenchBody body, uint32_t iterations)
{
    /* volatile: bench_hz200 is small enough to inline into its caller, and with the target visible
     * the empty body disappears. Reloading the pointer each iteration costs the same in both
     * loops, so it cancels in the subtraction. */
    volatile BenchBody call = body;
    uint32_t edge = hz200_counter();
    uint32_t spin;
    uint32_t index;

    for (spin = 0; spin < BENCH_EDGE_SPIN_LIMIT && hz200_counter() == edge; spin++) {
    }
    edge = hz200_counter();
    for (index = 0; index < iterations; index++) {
        call();
    }
    return hz200_counter() - edge;
}

/* Measured with the tune running (a row step lands on one frame in `speed`, so its share is in the
 * average), and AFTER the demo rather than before it: the burst of ticks is audible, and putting
 * it at the end keeps the recorded WAV's first sound the tune's first note. */
static void measure_tick_cost(void)
{
#if BLACKICE_MODE
    /* Load the tick with the song the GAME spends its time in, not whichever one the schedule
     * happened to leave bound: blackice_exfil has a silent channel and no arpeggio, and measuring
     * it would report a per-frame cost the score never pays. The score at the FASTEST band is the
     * worst case — three sounding channels, an arpeggio and a vibrato, and the most row steps. */
    ym_music_init(blackice_score, BLACKICE_SCORE_BYTES);
    ym_music_set_speed(BLACKICE_BAND_SPEED[BLACKICE_BAND_COUNT - 1u]);
#endif
    ym_music_start();
    ledger.bench_idle_iterations = BENCH_IDLE_ITERATIONS;
    ledger.bench_tick_iterations = BENCH_TICK_ITERATIONS;
    ledger.bench_hz200_idle = bench_hz200(bench_idle, BENCH_IDLE_ITERATIONS);
    ledger.bench_hz200_tick = bench_hz200(bench_tick, BENCH_TICK_ITERATIONS);
    ym_music_stop();
}

/* ------------------------------------------------------------------------------ the run ------- */

/* Accept every blob the run will bind, and leave the FIRST one bound. Validating all of them here
 * — rather than trusting a mid-run re-init — is what lets the schedule's apply_song_cue be a
 * routine with nothing to report: a blob that this refuses never reaches the frame loop, and the
 * ledger says so before a single frame has been recorded. */
static uint32_t bind_songs(void)
{
#if BLACKICE_MODE
    uint8_t cue;

    for (cue = 0; cue < SONG_CUE_COUNT; cue++) {
        if (song_schedule[cue].song != 0
            && !ym_music_init(song_schedule[cue].song, song_schedule[cue].bytes)) {
            return 0;
        }
    }
#endif
    return (uint32_t)ym_music_init(FIRST_SONG, FIRST_SONG_BYTES);
}

/* Takes the vblank slot back BEFORE recording what the loop saw. Reading frame_counter with the
 * tick still installed can catch a vblank between the loop's exit test and the store, which
 * records one frame more than ran — a rare, baffling failure of an exact comparison host-side. */
static void run_frame_loop(uint16_t slot)
{
    uint32_t started = hz200_counter();

    while (frame_counter < DEMO_FRAMES) {
        if (hz200_counter() - started >= FRAME_LOOP_LIMIT_HZ200) {
            break;
        }
    }
    remove_vbl_tick(slot);
    ledger.hz200_elapsed = hz200_counter() - started;
    ledger.frames_run = frame_counter;
}

/* Everything that touches $ffff8800 / $ffff89xx / the system variables, in supervisor mode. */
static void run_under_supervisor(void)
{
    ledger.machine_has_dma = (uint32_t)dma_sfx_available();
    ledger.song_accepted = bind_songs();
    ledger.bank_accepted = (uint32_t)dma_sfx_init(SAMPLE_BANK, SAMPLE_BANK_BYTES);

    ym_music_start();
    vbl_slot_taken = install_vbl_tick();
    ledger.vbl_slot = vbl_slot_taken;
    if (vbl_slot_taken != VBL_SLOT_NONE) {
        run_frame_loop(vbl_slot_taken);
    }

    /* Teardown BEFORE the measurement, so a machine that fails halfway is still handed back a
     * silent PSG and a stopped DMA. */
    ym_music_stop();
    dma_sfx_stop();
    measure_tick_cost();
}

static void write_ledger(void)
{
    long handle = Fcreate(LEDGER_NAME, LEDGER_ATTR);

    if (handle < 0) {
        return;
    }
    Fwrite((short)handle, (long)sizeof(ledger), &ledger);
    Fclose((short)handle);
}

void audiotest_main(void)
{
    void *ssp;

    ledger.magic = LEDGER_MAGIC;
    ledger.version = LEDGER_VERSION;
    ledger.text_probe = (uint32_t)&audio_vbl_tick;

    ssp = (void *)Super(0);
    run_under_supervisor();
    audio_leave_supervisor(ssp);

    write_ledger();
}
