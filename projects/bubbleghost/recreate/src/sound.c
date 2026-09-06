/* sound.c — Bubble Ghost's sound engine: a three-voice software ADSR + LFO synthesiser for the
 * YM2149, ticked at 200 Hz from Timer C.
 *
 * The shape of the thing: `sound_play` fills one of three VOICE RECORDS from a 56-word definition
 * and arms it; `timer_c_sound_isr` runs, for each armed voice, three near-identical machines — a
 * volume envelope with a triangle LFO, a pitch envelope with a two-rate LFO, a noise envelope with
 * a triangle LFO — and pushes the results at the chip. There is no sequencer and no note stream.
 * `../notes/sound_engine.md` is the design doc; `include/sound.h` is the layout, frozen.
 *
 * THE TWO DOORS TO THE CHIP, and why they are spelt differently here:
 *   - the interrupt handler writes `$ffff8800`/`$ffff8802` directly, because it already owns the
 *     machine at IPL 5 and nothing can interleave with it;
 *   - everything else goes through `psg_gate`, a `trap #9` into `trap9_psg_handler`, which raises
 *     to IPL 7 so the handler above cannot slip between a register select and its data write.
 * Off target both are `psg_port_write`/`psg_port_read` (the kit's psg.h): the ports are outside the
 * memory image, so the differential compares them through the kit's ordered PSG ledger instead.
 *
 * WHY SO MUCH OF THIS IS SPELT IN 16-BIT PIECES. The original is Alcyon C over hand-tuned 68000
 * idiom, and several of its comparisons are narrower than the value they test: the envelope phase
 * is a word compared with `cmp.b`, a long accumulator's sign is tested through its high word, the
 * volume multiply is a `muls.w` on the low words of two longs, and the noise clamp is a `cmp.b` on
 * a word. Each of those is reproduced rather than tidied — they are reachable, and two of them are
 * audible.
 */
#include "machine.h"
#include "psg.h"
#include "hw.h"
#include "sound.h"

/* ================================================================================================
 * 68000 arithmetic C does not give for free
 * ============================================================================================= */

/* `add.l`/`neg.l` on a signed value. Spelt through unsigned because signed overflow is undefined in
 * C and every accumulator here is expected to wrap exactly as the 68000's does. */
static int32_t add_long(int32_t augend, int32_t addend) {
    return (int32_t)((uint32_t)augend + (uint32_t)addend);
}

static int32_t neg_long(int32_t value) {
    return (int32_t)(0u - (uint32_t)value);
}

/* `swap dn` — exchange the register's halves. Used to lift the HIGH word of a 16.16 accumulator
 * into the low word an ensuing word-sized operation will read. */
static uint32_t swap_halves(uint32_t value) {
    return (value >> 16) | (value << 16);
}

/* ================================================================================================
 * Reading and writing a voice record, whose base is an image ADDRESS rather than a host pointer
 *
 * The interrupt handler takes its record base out of the image (`SND_ISR_TOP_VOICE`), so the
 * address is computed the way the 68000 computes it — 32-bit and wrapping — and only then turned
 * into an index. `make guarded` is the surface for that: a base or a stride one record out leaves
 * the image and faults instead of quietly reading the host heap.
 * ============================================================================================= */

static int16_t field_w(const uint8_t *image, uint32_t record, unsigned offset) {
    return (int16_t)be16(image + addr_add(record, offset));
}

static int32_t field_l(const uint8_t *image, uint32_t record, unsigned offset) {
    return (int32_t)be32(image + addr_add(record, offset));
}

static void set_field_w(uint8_t *image, uint32_t record, unsigned offset, int16_t value) {
    wr16(image + addr_add(record, offset), (uint16_t)value);
}

static void set_field_l(uint8_t *image, uint32_t record, unsigned offset, int32_t value) {
    wr32(image + addr_add(record, offset), (uint32_t)value);
}

/* Where voice `voice`'s record lives. `muls.w #$8c,dn` builds a 32-bit product and `adda.w dn,a0`
 * then adds only its SIGN-EXTENDED LOW WORD — which is what makes an out-of-range voice index wrap
 * inside a 64 KB window rather than reach across the address space. Three of the five entry points
 * range-check the index before they get here; `sound_voice_priority` does not. */
static uint32_t voice_record(int16_t voice) {
    return addr_add(A_snd_voice,
                    sign_ext16((uint16_t)((int32_t)voice * (int32_t)SND_VOICE_BYTES)));
}

/* `addq.w #1,n(a0)` on a phase word: attack becomes decay, decay becomes the sustain hold. */
static void advance_phase(uint8_t *image, uint32_t record, unsigned phase_offset) {
    set_field_w(image, record, phase_offset, (int16_t)(field_w(image, record, phase_offset) + 1));
}

/* ================================================================================================
 * THE PSG GATE — psg_gate @ 0x14940 (user mode) and trap9_psg_handler @ 0x14950 (supervisor)
 * ============================================================================================= */

/* Four of the six `psg_gate` call sites push only TWO argument words, so the gate's `mask` is
 * whatever the stack happened to hold. It is never READ at those sites: the handler consults it
 * only for register 7, and none of the four selects register 7. Passing a definite 0 for an
 * argument the original leaves indefinite is safe for exactly that reason, and the PSG ledger is
 * what would say otherwise. */
#define PSG_GATE_MASK_UNREAD 0u

/* The supervisor half. It raises to IPL 7 (so the 200 Hz handler cannot interleave a register
 * select with a data write), selects `reg & 15`, and then:
 *   - a NEGATIVE `value` means the call is a pure read and nothing is written;
 *   - register 7 alone is a read-modify-write: the mixer is read back and `value` keeps the bits
 *     `mask` names, which is how the other two channels' bits and the port-direction bits TOS owns
 *     survive a per-channel update;
 *   - the selected register is then read back as the return value.
 *
 * ONE EFFECT IS NOT MODELLED: the handler's last act is `move.b #$b,(a0)`, parking the select latch
 * on register 11 so nothing is left pointing at the I/O ports. A bare select with no access is not
 * expressible through psg.h (its calls select and access together) and the oracle ledgers nothing
 * for it either, so the two sides agree by construction — see STATUS.md's residual. */
uint8_t trap9_psg_handler(uint16_t reg, int16_t value, uint16_t mask) {
    const unsigned selected = reg & PSG_REG_SELECT_MASK;

    if (value >= 0) {
        uint8_t outgoing = (uint8_t)value;
        if (selected == PSG_REG_MIXER)
            outgoing |= (uint8_t)(psg_port_read(PSG_REG_MIXER) & (uint8_t)mask);
        psg_port_write(selected, outgoing);
    }
    return psg_port_read(selected);
}

/* The user-mode stub: three argument words off the stack into d1/d0/d2 and `trap #9`. On the
 * machine the dispatch is through the vector at $a4, which `install_sound_vectors` wrote; off
 * target there is no trap to take, so it is a direct call. */
uint8_t psg_gate(uint16_t reg, int16_t value, uint16_t mask) {
    return trap9_psg_handler(reg, value, mask);
}

/* ================================================================================================
 * THE TRIGGER API — sound_play @ 0x142bc and its four siblings
 * ============================================================================================= */

#define SOUND_PLAY_REFUSED (-1)  /* `move.w #$ffff,d0` @ 0x14346 — priority too low */

/* sound_voice_priority @ 0x1455e. 0 means the voice is free. NOTE THE MISSING RANGE CHECK: unlike
 * its three siblings this one indexes the record array with whatever it is given, which is why
 * `voice_record` models the `adda.w` wrap rather than assuming 0..2. */
int16_t sound_voice_priority(const uint8_t *image, int16_t voice) {
    return field_w(image, voice_record(voice), SND_VC_PRIORITY);
}

/* sound_stop_voice @ 0x144c4 — hard silence: the voice becomes free, idle, and mute. */
void sound_stop_voice(uint8_t *image, int16_t voice) {
    uint32_t record;

    if (voice < 0 || voice > (int16_t)(SND_VOICES - 1))
        return;
    record = voice_record(voice);
    set_field_w(image, record, SND_VC_PRIORITY, 0);
    set_field_w(image, record, SND_VC_DURATION, 0);
    psg_gate((uint16_t)PSG_REG_VOLUME((unsigned)voice), 0, PSG_GATE_MASK_UNREAD);
}

/* sound_release_voice @ 0x14510 — note off. Arming the duration counter at 1 with a negative gate
 * makes the handler's key-off path fire on the very next tick, which is what runs the release
 * phase of every machine that is still going. A voice that is already idle is left alone. */
void sound_release_voice(uint8_t *image, int16_t voice) {
    uint32_t record;

    if (voice < 0 || voice > (int16_t)(SND_VOICES - 1))
        return;
    record = voice_record(voice);
    if (field_w(image, record, SND_VC_DURATION) == 0)
        return;
    set_field_w(image, record, SND_VC_DURATION, 1);
    set_field_w(image, record, SND_VC_GATE, -1);
}

/* sound_stop_all @ 0x14576. */
void sound_stop_all(uint8_t *image) {
    for (int16_t voice = 0; voice < (int16_t)SND_VOICES; voice++)
        sound_stop_voice(image, voice);
}

/* Which voice a trigger that named none should take: the first idle one, or — if all three are
 * busy — the lowest-priority one, comparing 0 against 1 and the winner against 2. A TIE GOES TO THE
 * HIGHER INDEX, because both compares are `bge`.
 *
 * THE WHOLE OF THIS IS DEAD IN THE SHIPPED GAME: all fifteen `sound_play` call sites pass a literal
 * 0, 1 or 2 (../notes/sound_engine.md §8). It is reconstructed because it is reachable code, and
 * the differential drives it with synthetic voice arguments no caller uses. */
static int16_t allocate_voice(const uint8_t *image) {
    int16_t voice = 0;
    int16_t lower_of_first_two;

    while (voice < (int16_t)SND_VOICES
           && field_w(image, voice_record(voice), SND_VC_DURATION) != 0)
        voice++;
    if (voice < (int16_t)SND_VOICES)
        return voice;

    lower_of_first_two = (sound_voice_priority(image, 0) >= sound_voice_priority(image, 1)) ? 1 : 0;
    return (sound_voice_priority(image, lower_of_first_two) >= sound_voice_priority(image, 2))
           ? 2 : lower_of_first_two;
}

/* Fold a MIDI note into the only window `snd_note_period` really holds (24..108 = C1..C8), by
 * whole octaves. The 24 slots below it are not padding: they are `snd_volume_scale` and
 * `snd_mixer_and_mask`, packed into the table's unreachable head. */
static int16_t fold_note_into_table(int16_t note) {
    while (note > SND_NOTE_MAX)
        note = (int16_t)(note - SND_NOTE_OCTAVE);
    while (note < SND_NOTE_MIN)
        note = (int16_t)(note + SND_NOTE_OCTAVE);
    return note;
}

/* Copy a definition into the record it describes: def[1..55] land at record offsets 0x02..0x6e, so
 * a definition IS the record's first 0x70 bytes minus its duration word. */
static void load_definition(uint8_t *image, uint32_t record, uint32_t definition) {
    for (unsigned word = 1; word < SND_DEF_WORDS; word++)
        wr16(image + addr_add(record, 2u * word), be16(image + addr_add(definition, 2u * word)));
}

static void clear_accumulators(uint8_t *image, uint32_t record) {
    set_field_l(image, record, SND_VC_PITCH_LFO_ACC, 0);
    set_field_l(image, record, SND_VC_PITCH_ENV_ACC, 0);
    set_field_l(image, record, SND_VC_NOISE_LFO_ACC, 0);
    set_field_l(image, record, SND_VC_NOISE_ENV_ACC, 0);
    set_field_l(image, record, SND_VC_VOL_LFO_ACC, 0);
    set_field_l(image, record, SND_VC_VOL_ENV_ACC, 0);
}

/* Arm the tone half and return the mixer bit that has to be SET (a set bit turns the channel off).
 * A negative base period means "this voice makes no tone": the mixer bit goes up and the whole
 * pitch machine is switched off with it. */
static uint16_t arm_tone(uint8_t *image, uint32_t record, unsigned voice, int16_t note) {
    int16_t period;

    if (field_w(image, record, SND_VC_TONE_PERIOD) < 0) {
        set_field_l(image, record, SND_VC_PITCH_LFO_LIMIT_HI, 0);
        set_field_w(image, record, SND_VC_PITCH_PHASE, 0);
        return (uint16_t)PSG_MIXER_TONE_OFF(voice);
    }
    if (note >= 0) {
        int16_t slot = fold_note_into_table(note);
        set_field_w(image, record, SND_VC_TONE_PERIOD,
                    (int16_t)be16(image + addr_add(A_snd_note_period,
                                                   sign_ext16((uint16_t)(2 * slot)))));
    }
    /* Both halves are non-negative here — the branch above guaranteed it — so the `asr.w #8` this
     * transcribes never sees a negative word. */
    period = field_w(image, record, SND_VC_TONE_PERIOD);
    psg_gate((uint16_t)PSG_REG_TONE_LOW(voice), (int16_t)(period & 0xff), PSG_GATE_MASK_UNREAD);
    psg_gate((uint16_t)PSG_REG_TONE_HIGH(voice), (int16_t)(period >> 8), PSG_GATE_MASK_UNREAD);
    return 0;
}

/* The same for the noise half, on the one register all three channels share. */
static uint16_t arm_noise(uint8_t *image, uint32_t record, unsigned voice) {
    if (field_w(image, record, SND_VC_NOISE_PERIOD) < 0) {
        set_field_l(image, record, SND_VC_NOISE_LFO_LIMIT, 0);
        set_field_w(image, record, SND_VC_NOISE_PHASE, 0);
        return (uint16_t)PSG_MIXER_NOISE_OFF(voice);
    }
    psg_gate(PSG_REG_NOISE, field_w(image, record, SND_VC_NOISE_PERIOD), PSG_GATE_MASK_UNREAD);
    return 0;
}

/* sound_play @ 0x142bc — the whole trigger API. Returns the voice it used, or -1 when the voice's
 * current sound outranks this one. */
int16_t sound_play(uint8_t *image, uint32_t definition, int16_t voice, int16_t volume,
                   int16_t note, int16_t priority) {
    const int16_t chosen = (voice >= 0 && voice <= (int16_t)(SND_VOICES - 1))
                           ? voice : allocate_voice(image);
    const uint32_t record = voice_record(chosen);
    uint16_t mixer_bits;
    int16_t duration;

    if (priority < field_w(image, record, SND_VC_PRIORITY))
        return SOUND_PLAY_REFUSED;
    sound_stop_voice(image, chosen);

    duration = (int16_t)be16(image + definition);
    if (duration == 0)
        return chosen;              /* a zero-duration definition is simply "stop that voice" */

    load_definition(image, record, definition);
    set_field_w(image, record, SND_VC_GATE, note);
    set_field_w(image, record, SND_VC_PRIORITY, priority);
    clear_accumulators(image, record);

    mixer_bits = arm_tone(image, record, (unsigned)chosen, note);
    mixer_bits |= arm_noise(image, record, (unsigned)chosen);
    /* `chosen` is 0..2 by construction, so this index needs none of `voice_record`'s wrap care. */
    psg_gate(PSG_REG_MIXER, (int16_t)mixer_bits,
             be16(image + addr_add(A_snd_mixer_and_mask, 2u * (uint32_t)chosen)));

    if (volume >= 0)
        set_field_w(image, record, SND_VC_VOLUME_INDEX, volume);
    if (field_w(image, record, SND_VC_VOL_PHASE) == SND_PHASE_IDLE) {
        /* No envelope at all: peg the accumulator at full scale and write the index straight to the
         * chip, which is how a constant-volume voice is made. */
        set_field_l(image, record, SND_VC_VOL_ENV_ACC, SND_VOL_ENV_PEAK);
        psg_gate((uint16_t)PSG_REG_VOLUME((unsigned)chosen),
                 field_w(image, record, SND_VC_VOLUME_INDEX), PSG_GATE_MASK_UNREAD);
    }
    set_field_w(image, record, SND_VC_DURATION, duration);   /* LAST: this arms the voice */
    return chosen;
}

/* ================================================================================================
 * THE 200 Hz HANDLER — timer_c_sound_isr @ 0x1459a
 * ============================================================================================= */

/* The volume envelope, whose three live phases each have a hard-wired target: full scale for the
 * attack, the record's own sustain level for the decay, zero for the release. Phase 3 is the
 * sustain hold and stores nothing at all.
 *
 * The phase is compared with `cmp.b`, so only its low byte selects the branch — a phase word of
 * 0x0101 is an attack. Faithful rather than tidy: the field is a word everywhere else. */
static void step_volume_envelope(uint8_t *image, uint32_t record) {
    const uint8_t phase = (uint8_t)field_w(image, record, SND_VC_VOL_PHASE);
    int32_t level = field_l(image, record, SND_VC_VOL_ENV_ACC);

    if (phase == SND_PHASE_ATTACK) {
        level = add_long(level, field_l(image, record, SND_VC_VOL_ATTACK_STEP));
        if (level >= SND_VOL_ENV_PEAK) {
            level = SND_VOL_ENV_PEAK;
            advance_phase(image, record, SND_VC_VOL_PHASE);
        }
    } else if (phase == SND_PHASE_DECAY) {
        int32_t sustain = field_l(image, record, SND_VC_VOL_SUSTAIN);
        level = add_long(level, field_l(image, record, SND_VC_VOL_DECAY_STEP));
        if (level <= sustain) {
            level = sustain;
            advance_phase(image, record, SND_VC_VOL_PHASE);
        }
    } else if (phase == SND_PHASE_RELEASE) {
        level = add_long(level, field_l(image, record, SND_VC_VOL_RELEASE_STEP));
        if (level <= 0) {
            level = 0;
            set_field_w(image, record, SND_VC_VOL_PHASE, SND_PHASE_IDLE);
            /* The silence sentinel: one more tick, which the key-off path spends writing volume 0. */
            set_field_w(image, record, SND_VC_DURATION, 1);
        }
    } else {
        return;
    }
    set_field_l(image, record, SND_VC_VOL_ENV_ACC, level);
}

/* The triangle LFO the volume and noise machines share: accumulate the step, fold at either limit,
 * and negate the step where it folds. A limit of 0 is the machine's off switch, and the onset delay
 * counts down once and is never reloaded. */
static void step_triangle_lfo(uint8_t *image, uint32_t record, unsigned limit_offset,
                              unsigned accumulator_offset) {
    const unsigned step_offset = limit_offset + SND_LFO_STEP_FROM_LIMIT;
    const unsigned delay_offset = limit_offset + SND_LFO_DELAY_FROM_LIMIT;
    int32_t limit = field_l(image, record, limit_offset);
    int16_t delay;
    int32_t value;

    if (limit == 0)
        return;
    delay = field_w(image, record, delay_offset);
    if (delay != 0) {
        set_field_w(image, record, delay_offset, (int16_t)(delay - 1));
        return;
    }

    value = add_long(field_l(image, record, accumulator_offset),
                     field_l(image, record, step_offset));
    if (value < limit) {
        limit = neg_long(limit);
        if (value > limit) {
            set_field_l(image, record, accumulator_offset, value);
            return;
        }
    }
    set_field_l(image, record, step_offset, neg_long(field_l(image, record, step_offset)));
    set_field_l(image, record, accumulator_offset, limit);
}

/* Push the voice's level at the chip. The gate is "the envelope is running OR the LFO's limit is
 * large enough to show in its high word" — `or.w 26(a0),d0` reads the high half of a long.
 *
 * THE MULTIPLY IS A `muls.w` ON TWO LOW WORDS, which is the one place this engine can alias: the
 * summed accumulator is shifted right 8 and only its low 16 bits reach the multiply, so a sum at or
 * above 0x01000000 folds. The shipped definitions stay far below that; the arithmetic is
 * transcribed as written rather than widened. */
static void write_volume(uint8_t *image, uint32_t record, unsigned voice, uint32_t volume_scale) {
    const uint16_t running = (uint16_t)field_w(image, record, SND_VC_VOL_PHASE)
                           | (uint16_t)field_w(image, record, SND_VC_VOL_LFO_LIMIT);
    int32_t modulated;
    int16_t scale;
    uint16_t level;

    if (running == 0)
        return;

    /* The index is doubled as a WORD and then sign-extended, and nothing bounds it: a volume index
     * outside 0..15 reads past the 16-word table exactly as the original does. */
    scale = (int16_t)be16(image + addr_add(volume_scale,
                sign_ext16((uint16_t)(2 * field_w(image, record, SND_VC_VOLUME_INDEX)))));

    modulated = add_long(field_l(image, record, SND_VC_VOL_ENV_ACC),
                         field_l(image, record, SND_VC_VOL_LFO_ACC));
    if (modulated < 0) {
        level = 0;
    } else {
        int32_t scaled = (int32_t)scale * (int16_t)(modulated >> SND_VOL_ENV_SHIFT);
        level = (uint16_t)((uint32_t)scaled >> 16);       /* `swap d0` */
        if ((int16_t)level > SND_VOL_MAX)
            level = SND_VOL_MAX;
    }
    psg_port_write(PSG_REG_VOLUME(voice), (uint8_t)level);
}

/* The three-segment envelope the PITCH and NOISE machines share. It differs from the volume one in
 * two ways: each segment carries its own target, and the direction of the comparison follows the
 * SIGN OF THE STEP, so a segment may sweep either way. The release runs to zero and — unlike the
 * volume release — neither clears the phase nor re-arms the duration counter.
 *
 * The step's sign is read as `tst.w` on its HIGH WORD, which is the long's sign bit either way. */
static void step_swept_envelope(uint8_t *image, uint32_t record, unsigned phase_offset,
                                unsigned accumulator_offset) {
    const uint8_t phase = (uint8_t)field_w(image, record, phase_offset);
    int32_t value = field_l(image, record, accumulator_offset);
    int32_t step;

    if (phase == SND_PHASE_ATTACK || phase == SND_PHASE_DECAY) {
        const unsigned segment = (phase == SND_PHASE_ATTACK) ? SND_ENV_STEP1_FROM_PHASE
                                                             : SND_ENV_STEP2_FROM_PHASE;
        const unsigned step_offset = phase_offset + segment;
        const int32_t target = field_l(image, record, step_offset + SND_ENV_TARGET_FROM_STEP);
        step = field_l(image, record, step_offset);
        value = add_long(value, step);
        if (!(step < 0 ? value > target : value < target)) {
            value = target;
            advance_phase(image, record, phase_offset);
        }
    } else if (phase == SND_PHASE_RELEASE) {
        step = field_l(image, record, phase_offset + SND_ENV_RELEASE_FROM_PHASE);
        value = add_long(value, step);
        if (!(step < 0 ? value > 0 : value < 0))
            value = 0;
    } else {
        return;
    }
    set_field_l(image, record, accumulator_offset, value);
}

/* The pitch LFO, which is NOT a plain triangle: the step is added to the accumulator and, if that
 * add carries out of 32 bits (rising) or fails to (falling), the step is replaced from one of two
 * reload fields — a two-rate sweep. The rising and falling halves also use different limits. At
 * either limit the step is negated as usual. The musical intent of the reload pair is not grounded,
 * so the names keep offset+role. */
static void step_pitch_lfo(uint8_t *image, uint32_t record) {
    int32_t limit = field_l(image, record, SND_VC_PITCH_LFO_LIMIT_HI);
    int32_t step, accumulator, value;
    int16_t delay;
    int at_limit;

    if (limit == 0)
        return;
    delay = field_w(image, record, SND_VC_PITCH_LFO_DELAY);
    if (delay != 0) {
        set_field_w(image, record, SND_VC_PITCH_LFO_DELAY, (int16_t)(delay - 1));
        return;
    }

    step = field_l(image, record, SND_VC_PITCH_LFO_STEP);
    accumulator = field_l(image, record, SND_VC_PITCH_LFO_ACC);
    value = add_long(step, accumulator);
    if (step >= 0) {
        if (long_add_extend((uint32_t)step, (uint32_t)accumulator))
            set_field_l(image, record, SND_VC_PITCH_LFO_STEP,
                        field_l(image, record, SND_VC_PITCH_LFO_STEP_RELOAD_UP));
        at_limit = !(value < limit);
    } else {
        limit = field_l(image, record, SND_VC_PITCH_LFO_LIMIT_LO);
        if (!long_add_extend((uint32_t)step, (uint32_t)accumulator))
            set_field_l(image, record, SND_VC_PITCH_LFO_STEP,
                        field_l(image, record, SND_VC_PITCH_LFO_STEP_RELOAD_DOWN));
        at_limit = !(value > limit);
    }
    if (at_limit) {
        value = limit;
        set_field_l(image, record, SND_VC_PITCH_LFO_STEP,
                    neg_long(field_l(image, record, SND_VC_PITCH_LFO_STEP)));
    }
    set_field_l(image, record, SND_VC_PITCH_LFO_ACC, value);
}

/* Push the voice's tone period at the chip. The modulation is RELATIVE — `base * (1 + delta/4096)`
 * — with `delta` the high word of the summed accumulators, and the product rounded by adding one
 * when its own bit 15 is set (the `bpl` after the second `swap`). */
static void write_tone_period(uint8_t *image, uint32_t record, unsigned voice) {
    const uint16_t running = (uint16_t)field_w(image, record, SND_VC_PITCH_PHASE)
                           | (uint16_t)field_w(image, record, SND_VC_PITCH_LFO_LIMIT_HI);
    const int16_t base = field_w(image, record, SND_VC_TONE_PERIOD);
    uint32_t modulated, scaled, swapped;
    int16_t depth, period;

    if (running == 0)
        return;

    modulated = (uint32_t)add_long(field_l(image, record, SND_VC_PITCH_LFO_ACC),
                                   field_l(image, record, SND_VC_PITCH_ENV_ACC));
    depth = (int16_t)(uint16_t)swap_halves(modulated);
    scaled = (uint32_t)((int32_t)depth * base) << SND_PITCH_MOD_SHIFT;
    swapped = swap_halves(scaled);
    period = (int16_t)(uint16_t)swapped;
    if (swapped & 0x80000000u)
        period = (int16_t)(period + 1);
    period = (int16_t)(period + base);

    if (period < 0)
        period = 0;
    else if (period > SND_TONE_PERIOD_MAX)
        period = SND_TONE_PERIOD_MAX;
    psg_port_write(PSG_REG_TONE_LOW(voice), (uint8_t)period);
    psg_port_write(PSG_REG_TONE_HIGH(voice), (uint8_t)((uint16_t)period >> 8));
}

/* Push the noise period at the chip — one register for all three channels, so the last voice the
 * handler services (voice 0) is the one that wins.
 *
 * THE UPPER CLAMP IS A BYTE COMPARE ON A WORD (`cmp.b #$1f,d0`), so a result of, say, 0x90 is a
 * NEGATIVE byte, slips past the clamp, and the chip takes its low five bits. Reproduced, not
 * fixed: it is the engine's own behaviour and it is audible. */
static void write_noise_period(uint8_t *image, uint32_t record) {
    const uint16_t running = (uint16_t)field_w(image, record, SND_VC_NOISE_PHASE)
                           | (uint16_t)field_w(image, record, SND_VC_NOISE_LFO_LIMIT);
    uint32_t modulated;
    int16_t value;
    uint8_t period;

    if (running == 0)
        return;

    modulated = (uint32_t)add_long(field_l(image, record, SND_VC_NOISE_LFO_ACC),
                                   field_l(image, record, SND_VC_NOISE_ENV_ACC));
    value = (int16_t)(uint16_t)((uint16_t)swap_halves(modulated)
                                + (uint16_t)field_w(image, record, SND_VC_NOISE_PERIOD));
    if (value < 0)
        period = 0;
    else if ((int8_t)(uint8_t)value > SND_NOISE_PERIOD_MAX)
        period = SND_NOISE_PERIOD_MAX;
    else
        period = (uint8_t)value;
    psg_port_write(PSG_REG_NOISE, period);
}

/* Force one of the two swept machines into its release, at key-off. A machine that is already idle
 * is left alone; one that is running gets its release step turned round if it does not already
 * point back toward zero — the two signs are compared by XORing the accumulator's HIGH WORD with
 * the step's, so equal signs (a step running away from zero) is a non-negative result. */
static void release_swept_machine(uint8_t *image, uint32_t record, unsigned phase_offset,
                                  unsigned accumulator_offset) {
    const unsigned step_offset = phase_offset + SND_ENV_RELEASE_FROM_PHASE;
    int16_t step_sign, accumulator_sign;

    if (field_w(image, record, phase_offset) == 0)
        return;
    set_field_w(image, record, phase_offset, SND_PHASE_RELEASE);
    step_sign = field_w(image, record, step_offset);
    accumulator_sign = field_w(image, record, accumulator_offset);
    if ((int16_t)(accumulator_sign ^ step_sign) >= 0)
        set_field_l(image, record, step_offset, neg_long(field_l(image, record, step_offset)));
}

/* The end of a voice's life, run only while the gate is negative — a sound triggered with
 * `note >= 0` sustains until a caller stops it and never comes through here. */
static void key_off(uint8_t *image, uint32_t record, unsigned voice) {
    int16_t remaining;

    if (field_w(image, record, SND_VC_GATE) >= 0)
        return;
    remaining = (int16_t)(field_w(image, record, SND_VC_DURATION) - 1);
    set_field_w(image, record, SND_VC_DURATION, remaining);
    if (remaining != 0)
        return;

    set_field_w(image, record, SND_VC_PRIORITY, 0);
    if (field_w(image, record, SND_VC_VOL_PHASE) == SND_PHASE_IDLE) {
        psg_port_write(PSG_REG_VOLUME(voice), 0);
        return;
    }
    /* A second decrement takes the counter to -1, so this whole block fires exactly once while the
     * release phases it starts here run themselves out. */
    set_field_w(image, record, SND_VC_DURATION, (int16_t)(remaining - 1));
    set_field_w(image, record, SND_VC_VOL_PHASE, SND_PHASE_RELEASE);
    release_swept_machine(image, record, SND_VC_PITCH_PHASE, SND_VC_PITCH_ENV_ACC);
    release_swept_machine(image, record, SND_VC_NOISE_PHASE, SND_VC_NOISE_ENV_ACC);
}

/* One voice's whole tick: three machines, three chip writes, then the countdown. An idle voice
 * (duration 0) costs nothing at all. */
static void sound_voice_tick(uint8_t *image, uint32_t record, unsigned voice,
                             uint32_t volume_scale) {
    if (field_w(image, record, SND_VC_DURATION) == 0)
        return;

    step_volume_envelope(image, record);
    step_triangle_lfo(image, record, SND_VC_VOL_LFO_LIMIT, SND_VC_VOL_LFO_ACC);
    write_volume(image, record, voice, volume_scale);

    step_swept_envelope(image, record, SND_VC_PITCH_PHASE, SND_VC_PITCH_ENV_ACC);
    step_pitch_lfo(image, record);
    write_tone_period(image, record, voice);

    step_swept_envelope(image, record, SND_VC_NOISE_PHASE, SND_VC_NOISE_ENV_ACC);
    step_triangle_lfo(image, record, SND_VC_NOISE_LFO_LIMIT, SND_VC_NOISE_LFO_ACC);
    write_noise_period(image, record);

    key_off(image, record, voice);
}

/* timer_c_sound_isr @ 0x1459a — the 200 Hz tick.
 *
 * Its two pointers come out of the ISR state block rather than from `include/sound.h`, because that
 * is where the handler itself reads them: `install_sound_vectors` parks `&snd_volume_scale` and
 * `&snd_voice[2]` there and the handler walks DOWN, so voice 2 is serviced first and voice 0 gets
 * the last word on the shared noise register.
 *
 * TWO THINGS THE OFF-TARGET BUILD CANNOT EXPRESS, both of them SR manipulation with no image
 * effect: the drop from IPL 6 to IPL 5 that lets other MFP channels nest inside this handler, and
 * the exit — the handler does not `rte`, it pushes TOS's saved $114 vector and `rts`es, chaining to
 * the Timer C work TOS still wants done. See STATUS.md's residuals. */
void timer_c_sound_isr(uint8_t *image) {
    const uint32_t volume_scale = be32(image + SND_ISR_VOLUME_SCALE);
    uint32_t record = be32(image + SND_ISR_TOP_VOICE);
    uint16_t still_sounding = 0;
    unsigned voice;

    /* Unconditional, every tick: TOS's key click and bell drive the PSG too, and the handler owns
     * the chip while anything is playing. */
    image[TOS_CONTERM] = 0;

    for (voice = SND_VOICES; voice-- > 0; ) {
        sound_voice_tick(image, record, voice, volume_scale);
        record = addr_add(record, (uint32_t)-(int32_t)SND_VOICE_BYTES);
    }

    /* `lea -140(a0),a0` ran once per voice, so the cursor now sits one record BELOW voice 0 and the
     * three duration counters are at +0x8c, +0x118 and +0x1a4 from it — which is how the original
     * reads them (0x148ca). */
    for (voice = 0; voice < SND_VOICES; voice++)
        still_sounding |= (uint16_t)field_w(image,
                                            addr_add(record, (voice + 1) * SND_VOICE_BYTES),
                                            SND_VC_DURATION);
    if (still_sounding == 0)
        image[TOS_CONTERM] = image[SND_ISR_SAVED_CONTERM];
}

/* ================================================================================================
 * INSTALL / REMOVE — install_sound_vectors @ 0x148ea, remove_sound_vectors @ 0x1491c
 * ============================================================================================= */

/* Save what has to be put back, hand the handler its two pointers, take the two vectors, and put
 * the MFP into automatic end-of-interrupt mode.
 *
 * THE MFP WRITE IS THE ONE OFF-IMAGE EFFECT HERE and it is load-bearing: clearing bit 3 of the
 * vector register is what lets the handler's own IPL drop actually re-enable the MFP, since no
 * in-service bit is left latched for software to clear. The kit's hardware WRITE ledger is what
 * compares it (TRAP_MODEL.md, Phase 10); nothing in the image records it. */
void install_sound_vectors(uint8_t *image) {
    wr32(image + SND_ISR_SAVED_TIMER_C, be32(image + TOS_VEC_TIMER_C));
    wr32(image + SND_ISR_VOLUME_SCALE, A_snd_volume_scale);
    wr32(image + SND_ISR_TOP_VOICE, A_snd_voice + (SND_VOICES - 1) * SND_VOICE_BYTES);
    image[SND_ISR_SAVED_CONTERM] = image[TOS_CONTERM];

    wr32(image + TOS_VEC_TRAP9, SND_TRAP9_HANDLER_ENTRY);
    wr32(image + TOS_VEC_TIMER_C, SND_ISR_ENTRY);
    hw_write8(MFP_VECTOR_REG, MFP_VECTOR_AUTO_EOI);
}

/* ...and back. The trap #9 vector is deliberately NOT restored: the original leaves it pointing at
 * its own handler, which stays resident for the life of the program. */
void remove_sound_vectors(uint8_t *image) {
    wr32(image + TOS_VEC_TIMER_C, be32(image + SND_ISR_SAVED_TIMER_C));
    image[TOS_CONTERM] = image[SND_ISR_SAVED_CONTERM];
    hw_write8(MFP_VECTOR_REG, MFP_VECTOR_SW_EOI);
}

/* ================================================================================================
 * sound_start @ 0x14982 / sound_stop @ 0x1499c — the two the game itself calls
 * ============================================================================================= */

/* Both reach the installer through `Supexec`, and so through `xbios_trap` @ 0x15e3c, which parks
 * the CALLER'S a1/a2 and its own return address in three BSS longs before the trap and reads them
 * back after. Those three stores are ordinary image state the differential compares, so a
 * reconstruction that skipped them would be red — which is why `saved` is an argument: a1/a2 are
 * the register file this routine inherited and nothing in its own body computes them.
 *
 * THE SLOTS, THE TYPE AND THE THREE STORES ARE THE CLIB SUBSYSTEM'S (include/clib.h), called from
 * there rather than restated: `trap_save_registers` is a header inline both this file and
 * src/clib.c reach, so the trampoline's image effect has one spelling.
 *
 * The return address is a property of THIS routine's code — the byte after its own `jsr` — so it is
 * a call-site constant in the same shape as clib.h's `RET_*` family. */
#define RET_SOUND_START_SUPEXEC 0x14992u  /* the PC after `jsr $15e3c(pc)` @ 0x1498e */
#define RET_SOUND_STOP_SUPEXEC  0x149b0u  /* ...and after the one @ 0x149ac */

void sound_start(uint8_t *image, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_SOUND_START_SUPEXEC);
    install_sound_vectors(image);
    sound_stop_all(image);
}

void sound_stop(uint8_t *image, CallerAddressRegisters saved) {
    sound_stop_all(image);
    trap_save_registers(image, saved, RET_SOUND_STOP_SUPEXEC);
    remove_sound_vectors(image);
}

/* ================================================================================================
 * The glue — the differential's view of each core (README.md, "Adding a function")
 *
 * This program is Alcyon/DRI C, so every argument arrives on the stack as a word (or a longword for
 * the definition pointer) and every `short` answer comes back in D0's LOW WORD. The glues take
 * those as `uint32_t` and narrow them exactly as the callee's `move.w n(a6),dn` does.
 * ============================================================================================= */

uint32_t g_sound_play(uint8_t *image, uint32_t definition, uint32_t voice, uint32_t volume,
                      uint32_t note, uint32_t priority) {
    return (uint16_t)sound_play(image, definition, (int16_t)voice, (int16_t)volume,
                                (int16_t)note, (int16_t)priority);
}

void g_sound_stop_voice(uint8_t *image, uint32_t voice) {
    sound_stop_voice(image, (int16_t)voice);
}

void g_sound_release_voice(uint8_t *image, uint32_t voice) {
    sound_release_voice(image, (int16_t)voice);
}

uint32_t g_sound_voice_priority(uint8_t *image, uint32_t voice) {
    return (uint16_t)sound_voice_priority(image, (int16_t)voice);
}

void g_sound_stop_all(uint8_t *image) {
    sound_stop_all(image);
}

void g_timer_c_sound_isr(uint8_t *image) {
    timer_c_sound_isr(image);
}

/* N ticks in one call, for the cases that need a state a single tick cannot reach — a decay running
 * into its sustain, an LFO folding, a duration counting down to key-off. The oracle side is an
 * 18-byte stub that `jsr`s the handler in a `dbf` loop (test/test_sound.py's `isr_tick_stub`); this
 * is its C twin, and it composes the reconstructed handler rather than restating any of it. */
void g_timer_c_sound_isr_ticks(uint8_t *image, uint32_t ticks) {
    for (uint32_t tick = 0; tick < ticks; tick++)
        timer_c_sound_isr(image);
}

/* The gate's answer is a byte in D0 (`moveq #0,d0` then `move.b (a0),d0`), so the whole longword is
 * comparable and the case checks it. `image` is unused — the ports are off-image — but every glue
 * takes it, so the differential's caller needs no special case. */
uint32_t g_psg_gate(uint8_t *image, uint32_t reg, uint32_t value, uint32_t mask) {
    (void)image;
    return psg_gate((uint16_t)reg, (int16_t)value, (uint16_t)mask);
}

void g_install_sound_vectors(uint8_t *image) {
    install_sound_vectors(image);
}

void g_remove_sound_vectors(uint8_t *image) {
    remove_sound_vectors(image);
}

/* Register map: a1/a2 are the caller's, read by `xbios_trap` and by nothing in these two routines.
 * The case takes them FROM THE ORACLE's own input registers, which is what it set them to. */
void g_sound_start(uint8_t *image, uint32_t caller_a1, uint32_t caller_a2) {
    CallerAddressRegisters saved = {caller_a1, caller_a2};

    sound_start(image, saved);
}

void g_sound_stop(uint8_t *image, uint32_t caller_a1, uint32_t caller_a2) {
    CallerAddressRegisters saved = {caller_a1, caller_a2};

    sound_stop(image, saved);
}
