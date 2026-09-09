/* sound_tick.S — the 200 Hz Timer C tick, hand-written: a TRANSCRIPTION of the original binary's
 * own instruction stream for `timer_c_sound_isr` @ 0x1459a, carrying the C signature of the
 * verified core it replaces on the target build (`../sound.c`, `void (uint8_t *image)`).
 *
 * WHY IT EXISTS. The room loop has no Vsync, so cycles a frame ARE the game's speed, and the tick
 * runs 200 times a second. GCC's tick was 2,297 cycles against the original's 1,704 (../../STATUS.md,
 * "Performance") with the C already at the compiler's floor — d16(An) field access, every helper
 * inlined, no libgcc call. What was left was C against hand-asm, so this is the hand-asm, and it is
 * the original's own instructions rather than a fresh translation: a body byte-equal to the
 * original's cannot cost more than the original's.
 *
 * THE C CORE STAYS THE REFERENCE. `../sound.c`'s `timer_c_sound_isr` is what
 * `test/test_sound.py` verifies against the oracle, byte for byte, over the whole image and the
 * PSG ledger; `test/test_sound_asm.py` then verifies THIS against that C, case for case, over the
 * same two surfaces. Both links are exact, so this file is pinned to the original transitively —
 * and `test_asm_body_transcribes_the_original` compares the 792 bytes between
 * `timer_c_sound_isr_body` and `timer_c_sound_isr_body_end` against the .PRG's own
 * 0x145be..0x148d6, which is the stronger of the two claims:
 * not "computes the same thing" but "IS the same machine code".
 *
 * WHAT IS *NOT* TRANSCRIBED, and why each one differs:
 *
 *   the prologue      the original is a VECTOR handler: it saves d0-d3/a0-a2 (its whole working
 *                     set) because an interrupt owes its victim every register. This is a C
 *                     function, so it saves the m68k SysV callee-saved half of that set and leaves
 *                     the caller-saved half to `bg_timer_c_entry`, which is the vector here and
 *                     saves d0-d1/a0-a1 itself.
 *   the two pointers  the original reads `&snd_volume_scale` and `&snd_voice[2]` from its own TEXT
 *                     with `movea.l d16(pc)` and uses them as ABSOLUTE addresses, because the
 *                     program IS the memory. This reconstruction addresses a flat image through a
 *                     base pointer, so the same two longwords are read out of the image and the
 *                     base added to each — `image + address`, the shape `../sound.c` uses.
 *   $484              the original writes TOS's conterm byte directly. Here the tick writes the
 *                     IMAGE's mirror of it (which is what the differential can see) and
 *                     `bg_timer_c_entry` copies that byte out to the machine once the tick returns
 *                     — atari/build.sh's conterm-mirror gate is what keeps that store there.
 *   the SR work       the original drops from IPL 6 to IPL 5 so other MFP channels can nest inside
 *                     it, and leaves by pushing TOS's saved $114 vector rather than `rte`ing. The
 *                     first is a residual this build has never had (../../STATUS.md, "the sound
 *                     engine's residuals"); the second is `bg_timer_c_entry`'s closing pair.
 *
 * IF THAT IPL DROP IS EVER MADE FAITHFUL, THE CHIP WRITES NEED THE GATE BACK. What kept this build
 * safe without it is that the handler owns the machine at IPL 6 for its whole length, so nothing
 * can land between one of the five `move.b <reg>,(%a1)` selects and its data write. At IPL 5 the
 * IKBD can, and `atari/shim_include/psg.h`'s trap #9 gate (or a raise of `bg_in_timer_c`, which
 * `bg_timer_c_entry` no longer does) is what would have to come back with it. Assembly can touch
 * `%sr` where the C could not, so this is now a decision rather than an inability.
 *
 * AND THE ELEVEN INSTRUCTIONS OUTSIDE THE BRACKET ARE NOT UNDER THE TRANSCRIPTION PIN. They are
 * under the differential like everything else — every case runs them — plus one check of their own:
 * `test_the_twin_never_stores_through_its_own_frame` asserts they read `%sp` once and never write
 * it, which is what lets `bg_timer_c_entry` pop the image base back off the stack instead of
 * re-reading it.
 *
 * THE CHIP WRITES ARE THE ORIGINAL'S OWN — five bare `move.b <reg>,(%a1)` / `move.b <data>,2(%a1)`
 * pairs on `%a1` = $ffff8800, with no register mask, exactly as `shim_include/psg.h` describes
 * them. They need no `#ifdef`: the kit's oracle decodes those two ports in its memory callback
 * (`tools/recreate_kit/oracle/shim.c`, `m68k_write_memory_8`), so off target the same two stores
 * land in the oracle's ordered PSG ledger and the test compares that against the ledger the C
 * core's `psg_port_write` fills. This file therefore has ONE spelling for both builds — what the
 * differential runs is what the machine runs, instruction for instruction.
 *
 * WHY THE CONSTANTS ARE RESTATED. `../../include/sound.h` spells its values with C's `u` suffix,
 * which the assembler will not parse, so the handful this file needs are `.equ`s — and CLAUDE.md's
 * rule for two spellings that cannot import each other applies: `test_constants.py`'s
 * `test_asm_twin_equates_match_the_headers` reads them back out of THIS FILE'S OWN OBJECT and
 * refuses a build where one has drifted. The transcription pin is the second net under them: an
 * offset that is wrong is an instruction that is not the original's.
 */

/* ---- the ISR state block `install_sound_vectors` fills (../../include/sound.h) ---------------- */
    .equ SND_ISR_VOLUME_SCALE,  0x14936    /* l: &snd_volume_scale — the original's a2 @ 0x1459e */
    .equ SND_ISR_TOP_VOICE,     0x1493a    /* l: &snd_voice[2] — its a0 @ 0x145a2; the loop walks DOWN */
    .equ SND_ISR_SAVED_CONTERM, 0x1493e    /* b: TOS's own $484, put back when every voice is idle */
    .equ TOS_CONTERM,           0x0484     /* ...the image's mirror of TOS's key-click/bell byte */

/* ---- the voice records ------------------------------------------------------------------------ */
    .equ SND_VOICES,            3
    .equ SND_VOICE_BYTES,       0x8c
    .equ SND_VC_TONE_PERIOD,                   0x02   /* w */
    .equ SND_VC_NOISE_PERIOD,                  0x04   /* w */
    .equ SND_VC_VOLUME_INDEX,                  0x06   /* w */
    .equ SND_VC_VOL_PHASE,                     0x08   /* w */
    .equ SND_VC_VOL_ATTACK_STEP,               0x0a   /* l */
    .equ SND_VC_VOL_DECAY_STEP,                0x0e   /* l */
    .equ SND_VC_VOL_SUSTAIN,                   0x12   /* l */
    .equ SND_VC_VOL_RELEASE_STEP,              0x16   /* l */
    .equ SND_VC_VOL_LFO_LIMIT,                 0x1a   /* l */
    .equ SND_VC_VOL_LFO_STEP,                  0x1e   /* l */
    .equ SND_VC_VOL_LFO_DELAY,                 0x22   /* w */
    .equ SND_VC_PITCH_PHASE,                   0x24   /* w */
    .equ SND_VC_PITCH_STEP1,                   0x26   /* l */
    .equ SND_VC_PITCH_TARGET1,                 0x2a   /* l */
    .equ SND_VC_PITCH_STEP2,                   0x2e   /* l */
    .equ SND_VC_PITCH_TARGET2,                 0x32   /* l */
    .equ SND_VC_PITCH_RELEASE_STEP,            0x36   /* l */
    .equ SND_VC_PITCH_LFO_LIMIT_HI,            0x3a   /* l */
    .equ SND_VC_PITCH_LFO_STEP,                0x3e   /* l */
    .equ SND_VC_PITCH_LFO_STEP_RELOAD_UP,      0x42   /* l */
    .equ SND_VC_PITCH_LFO_LIMIT_LO,            0x46   /* l */
    .equ SND_VC_PITCH_LFO_STEP_RELOAD_DOWN,    0x4a   /* l */
    .equ SND_VC_PITCH_LFO_DELAY,               0x4e   /* w */
    .equ SND_VC_NOISE_PHASE,                   0x50   /* w */
    .equ SND_VC_NOISE_STEP1,                   0x52   /* l */
    .equ SND_VC_NOISE_TARGET1,                 0x56   /* l */
    .equ SND_VC_NOISE_STEP2,                   0x5a   /* l */
    .equ SND_VC_NOISE_TARGET2,                 0x5e   /* l */
    .equ SND_VC_NOISE_RELEASE_STEP,            0x62   /* l */
    .equ SND_VC_NOISE_LFO_LIMIT,               0x66   /* l */
    .equ SND_VC_NOISE_LFO_STEP,                0x6a   /* l */
    .equ SND_VC_NOISE_LFO_DELAY,               0x6e   /* w */
    .equ SND_VC_GATE,                          0x70   /* w */
    .equ SND_VC_PRIORITY,                      0x72   /* w */
    .equ SND_VC_VOL_ENV_ACC,                   0x74   /* l */
    .equ SND_VC_VOL_LFO_ACC,                   0x78   /* l */
    .equ SND_VC_PITCH_ENV_ACC,                 0x7c   /* l */
    .equ SND_VC_PITCH_LFO_ACC,                 0x80   /* l */
    .equ SND_VC_NOISE_ENV_ACC,                 0x84   /* l */
    .equ SND_VC_NOISE_LFO_ACC,                 0x88   /* l */

/* ---- the values the three machines compare against --------------------------------------------- */
    .equ SND_PHASE_ATTACK,                 1      /* ...and segment 1 of the pitch/noise machines */
    .equ SND_PHASE_DECAY,                  2      /* ...and segment 2 */
    .equ SND_PHASE_RELEASE,                4      /* ...and the phase key-off forces */
    .equ SND_VOL_ENV_PEAK,                 0x000f0000  /* the volume attack's hard-wired target */
    .equ SND_VOL_MAX,                      0x0f   /* the PSG's 4-bit level */
    .equ SND_TONE_PERIOD_MAX,              0x0fff /* ...its 12-bit tone period */
    .equ SND_NOISE_PERIOD_MAX,             0x1f   /* ...and its 5-bit noise period */

/* ---- the chip: atari/shim_include/psg.h's two numbers, and the one register named as a constant.
 * The volume register is `voice + 8` and the tone pair `2 * voice` and `2 * voice + 1`, which the
 * body builds with `addq.b #8` and `add.b %d1,%d1` — those are ../../include/sound.h's
 * PSG_REG_VOLUME(v) / PSG_REG_TONE_LOW(v) / PSG_REG_TONE_HIGH(v) spelt as the arithmetic they are,
 * and the transcription pin is what holds them to it. ------------------------------------------- */
    .equ BG_PSG_SELECT,                    0xffff8800  /* write = select a register */
    .equ BG_PSG_DATA_OFFSET,               2      /* ...and $ffff8802 takes the data */
    .equ PSG_REG_NOISE,                    6      /* one register for all three channels */

/* ---- one encoding gas will not choose ----------------------------------------------------------
 * `cmp #imm,%dn` has two legal encodings on the 68000: CMPI (0x0c00), which is what gas emits for
 * every spelling of it, and CMP with an IMMEDIATE SOURCE (0xb03c | dn << 9), which is what the
 * original's assembler emitted at all thirteen of its sites. Same four (or six) bytes and the same
 * timing — but not the same bytes, and the transcription pin compares bytes. So the body spells
 * these thirteen by hand. `reg` is the register NUMBER, because the opcode carries it in bits 11-9
 * — `D0`/`D1` below name the two the body uses — and every use carries the address and the bytes it
 * stands for in its comment column, which is what the transcription pin compares.
 */
    .equ D0, 0
    .equ D1, 1
    .macro  cmp_imm_b imm, reg          /* cmp.b #imm,%d<reg> */
    .short  0xb03c + (\reg << 9)
    .short  (\imm) & 0xff
    .endm
    .macro  cmp_imm_w imm, reg          /* cmp.w #imm,%d<reg> */
    .short  0xb07c + (\reg << 9)
    .short  (\imm)
    .endm
    .macro  cmp_imm_l imm, reg          /* cmp.l #imm,%d<reg> */
    .short  0xb0bc + (\reg << 9)
    .long   (\imm)
    .endm

    .text

/* timer_c_sound_isr_asm(uint8_t *image) — the twin of ../sound.c's `timer_c_sound_isr`.
 *
 * Enters with the image base at 4(%sp) and returns with every callee-saved register put back.
 * The register map for the whole run is the original's, plus one:
 *
 *     %a3   the image base            (ours: the original addressed memory absolutely)
 *     %a2   image + &snd_volume_scale — the 16-word table `write_volume`'s index reads
 *     %a0   image + the voice record being serviced; walks DOWN a record a voice
 *     %a1   $ffff8800, the chip
 *     %d2   the voice number, 2 down to 0 — and the channel the register numbers are built from
 *     %d0/%d1/%d3  scratch
 */
    .globl  timer_c_sound_isr_asm
timer_c_sound_isr_asm:
    movem.l %d2-%d3/%a2-%a3,-(%sp)      | the m68k SysV callee-saved half of the original's set;
                                        | `bg_timer_c_entry` saves %d0-%d1/%a0-%a1, being the vector
    movea.l 20(%sp),%a3                 | 4 arg + 16 saved: the image base
    /* The two pointers, read out of the ISR state block and turned into host pointers. The block
     * is at 0x14936, past a d16 displacement's reach, so the offset goes through %d0 as an index —
     * once each, outside the loop. */
    move.l  #SND_ISR_VOLUME_SCALE,%d0
    movea.l (%a3,%d0.l),%a2
    adda.l  %a3,%a2
    movea.l (SND_ISR_TOP_VOICE-SND_ISR_VOLUME_SCALE)(%a3,%d0.l),%a0   | the SAME %d0: the two fields
                                        | are four bytes apart and `d8(An,Xn)` reaches that far, so
                                        | the second index costs no reload
    adda.l  %a3,%a0                     | voice 2 first: the loop walks down, so voice 0 gets the
                                        | last word on the shared noise register
    movea.w #BG_PSG_SELECT,%a1          | ...and a WORD immediate: `movea.w` sign-extends, and bit 15
                                        | of $8800 is set, so this is $ffff8800 in 8 cycles rather
                                        | than 12 — one of the few places the twin beats the
                                        | original, whose own `movea.l #$ffff8800,a1` is at 0x145a6
    moveq   #SND_VOICES-1,%d2
    clr.b   TOS_CONTERM(%a3)            | unconditional, every tick: TOS's key click and bell drive
                                        | the chip too, and the handler owns it while anything plays

timer_c_sound_isr_body:
    /* ---- THE TRANSCRIBED BODY: 0x145be..0x148d6 of the original, byte for byte. Every line's
     * comment column is the address and the bytes it stands for, and `test_sound_asm.py`
     * compares the whole span against the .PRG. Nothing here may be `improved`: an instruction
     * that computes the same thing differently is a failure of that pin, on purpose.
     *
     * ONE VOICE PER PASS, voice 2 down to voice 0 (`dbf %d2` at the end), each pass running the
     * three machines in turn — volume, pitch, noise — and closing on the key-off countdown. */
.Lvoice:
    tst.w (%a0)                                               | 145be: 4a50
    beq.w .Lnext_voice                                        | 145c0: 67000300
    move.w SND_VC_VOL_PHASE(%a0),%d0                          | 145c4: 30280008
    move.l SND_VC_VOL_ENV_ACC(%a0),%d1                        | 145c8: 22280074
    cmp_imm_b SND_PHASE_ATTACK,D0                         | 145cc: b03c0001
    bne.s .Lvol_decay                                         | 145d0: 6618
    add.l SND_VC_VOL_ATTACK_STEP(%a0),%d1                     | 145d2: d2a8000a
    cmp_imm_l SND_VOL_ENV_PEAK,D1                         | 145d6: b2bc000f0000
    blt.s .Lvol_env_store                                     | 145dc: 6d3e
    move.l #SND_VOL_ENV_PEAK,%d1                              | 145de: 223c000f0000
    addq.w #1,SND_VC_VOL_PHASE(%a0)                           | 145e4: 52680008
    bra.s .Lvol_env_store                                     | 145e8: 6032
.Lvol_decay:
    cmp_imm_b SND_PHASE_DECAY,D0                          | 145ea: b03c0002
    bne.s .Lvol_release                                       | 145ee: 6614
    add.l SND_VC_VOL_DECAY_STEP(%a0),%d1                      | 145f0: d2a8000e
    cmp.l SND_VC_VOL_SUSTAIN(%a0),%d1                         | 145f4: b2a80012
    bgt.s .Lvol_env_store                                     | 145f8: 6e22
    move.l SND_VC_VOL_SUSTAIN(%a0),%d1                        | 145fa: 22280012
    addq.w #1,SND_VC_VOL_PHASE(%a0)                           | 145fe: 52680008
    bra.s .Lvol_env_store                                     | 14602: 6018
.Lvol_release:
    cmp_imm_b SND_PHASE_RELEASE,D0                        | 14604: b03c0004
    bne.s .Lvol_lfo                                           | 14608: 6616
    add.l SND_VC_VOL_RELEASE_STEP(%a0),%d1                    | 1460a: d2a80016
    tst.l %d1                                                 | 1460e: 4a81
    bgt.s .Lvol_env_store                                     | 14610: 6e0a
    moveq #0,%d1                                              | 14612: 7200
    move.w %d1,SND_VC_VOL_PHASE(%a0)                          | 14614: 31410008
    move.w #1,(%a0)                                           | 14618: 30bc0001
.Lvol_env_store:
    move.l %d1,SND_VC_VOL_ENV_ACC(%a0)                        | 1461c: 21410074

    /* The triangle LFO the volume and noise machines share: accumulate, fold at either limit,
     * negate the step where it folds. A limit of 0 is the machine's off switch. */
.Lvol_lfo:
    move.l SND_VC_VOL_LFO_LIMIT(%a0),%d0                      | 14620: 2028001a
    beq.s .Lvol_out                                           | 14624: 6728
    tst.w SND_VC_VOL_LFO_DELAY(%a0)                           | 14626: 4a680022
    beq.s .Lvol_lfo_step                                      | 1462a: 6706
    subq.w #1,SND_VC_VOL_LFO_DELAY(%a0)                       | 1462c: 53680022
    bra.s .Lvol_out                                           | 14630: 601c
.Lvol_lfo_step:
    move.l SND_VC_VOL_LFO_ACC(%a0),%d1                        | 14632: 22280078
    add.l SND_VC_VOL_LFO_STEP(%a0),%d1                        | 14636: d2a8001e
    cmp.l %d0,%d1                                             | 1463a: b280
    bge.s .Lvol_lfo_fold                                      | 1463c: 6c06
    neg.l %d0                                                 | 1463e: 4480
    cmp.l %d0,%d1                                             | 14640: b280
    bgt.s .Lvol_lfo_store                                     | 14642: 6e06
.Lvol_lfo_fold:
    move.l %d0,%d1                                            | 14644: 2200
    neg.l SND_VC_VOL_LFO_STEP(%a0)                            | 14646: 44a8001e
.Lvol_lfo_store:
    move.l %d1,SND_VC_VOL_LFO_ACC(%a0)                        | 1464a: 21410078

    /* Push the voice's level at the chip: the envelope plus the LFO, scaled by the volume table
     * (`muls.w` on two LOW WORDS) and clamped to 4 bits. Skipped when neither machine runs. */
.Lvol_out:
    move.w SND_VC_VOL_PHASE(%a0),%d0                          | 1464e: 30280008
    or.w SND_VC_VOL_LFO_LIMIT(%a0),%d0                        | 14652: 8068001a
    beq.s .Lpitch_env                                         | 14656: 6730
    move.w SND_VC_VOLUME_INDEX(%a0),%d0                       | 14658: 30280006
    add.w %d0,%d0                                             | 1465c: d040
    move.w (%a2,%d0.w),%d0                                    | 1465e: 30320000
    move.l SND_VC_VOL_ENV_ACC(%a0),%d1                        | 14662: 22280074
    add.l SND_VC_VOL_LFO_ACC(%a0),%d1                         | 14666: d2a80078
    bpl.s .Lvol_scale                                         | 1466a: 6a04
    moveq #0,%d0                                              | 1466c: 7000
    bra.s .Lvol_write                                         | 1466e: 600e
.Lvol_scale:
    asr.l #8,%d1                                              | 14670: e081
    muls.w %d1,%d0                                            | 14672: c1c1
    swap %d0                                                  | 14674: 4840
    cmp_imm_w SND_VOL_MAX,D0                              | 14676: b07c000f
    ble.s .Lvol_write                                         | 1467a: 6f02
    moveq #SND_VOL_MAX,%d0                                    | 1467c: 700f
.Lvol_write:
    move.b %d2,%d1                                            | 1467e: 1202
    addq.b #8,%d1                                             | 14680: 5001
    move.b %d1,(%a1)                                          | 14682: 1281
    move.b %d0,BG_PSG_DATA_OFFSET(%a1)                        | 14684: 13400002

    /* The pitch machine's three-segment envelope: each segment carries its own target and the
     * compare's direction follows the SIGN OF THE STEP, so a segment may sweep either way. */
.Lpitch_env:
    move.w SND_VC_PITCH_PHASE(%a0),%d0                        | 14688: 30280024
    move.l SND_VC_PITCH_ENV_ACC(%a0),%d1                      | 1468c: 2228007c
    cmp_imm_b SND_PHASE_ATTACK,D0                         | 14690: b03c0001
    bne.s .Lpitch_seg2                                        | 14694: 6622
    add.l SND_VC_PITCH_STEP1(%a0),%d1                         | 14696: d2a80026
    tst.w SND_VC_PITCH_STEP1(%a0)                             | 1469a: 4a680026
    bmi.s .Lpitch_seg1_falling                                | 1469e: 6b08
    cmp.l SND_VC_PITCH_TARGET1(%a0),%d1                       | 146a0: b2a8002a
    blt.s .Lpitch_env_store                                   | 146a4: 6d56
    bra.s .Lpitch_seg1_done                                   | 146a6: 6006
.Lpitch_seg1_falling:
    cmp.l SND_VC_PITCH_TARGET1(%a0),%d1                       | 146a8: b2a8002a
    bgt.s .Lpitch_env_store                                   | 146ac: 6e4e
.Lpitch_seg1_done:
    move.l SND_VC_PITCH_TARGET1(%a0),%d1                      | 146ae: 2228002a
    addq.w #1,SND_VC_PITCH_PHASE(%a0)                         | 146b2: 52680024
    bra.s .Lpitch_env_store                                   | 146b6: 6044
.Lpitch_seg2:
    cmp_imm_b SND_PHASE_DECAY,D0                          | 146b8: b03c0002
    bne.s .Lpitch_release                                     | 146bc: 6622
    add.l SND_VC_PITCH_STEP2(%a0),%d1                         | 146be: d2a8002e
    tst.w SND_VC_PITCH_STEP2(%a0)                             | 146c2: 4a68002e
    bmi.s .Lpitch_seg2_falling                                | 146c6: 6b08
    cmp.l SND_VC_PITCH_TARGET2(%a0),%d1                       | 146c8: b2a80032
    blt.s .Lpitch_env_store                                   | 146cc: 6d2e
    bra.s .Lpitch_seg2_done                                   | 146ce: 6006
.Lpitch_seg2_falling:
    cmp.l SND_VC_PITCH_TARGET2(%a0),%d1                       | 146d0: b2a80032
    bgt.s .Lpitch_env_store                                   | 146d4: 6e26
.Lpitch_seg2_done:
    move.l SND_VC_PITCH_TARGET2(%a0),%d1                      | 146d6: 22280032
    addq.w #1,SND_VC_PITCH_PHASE(%a0)                         | 146da: 52680024
    bra.s .Lpitch_env_store                                   | 146de: 601c
.Lpitch_release:
    cmp_imm_b SND_PHASE_RELEASE,D0                        | 146e0: b03c0004
    bne.s .Lpitch_lfo                                         | 146e4: 661a
    add.l SND_VC_PITCH_RELEASE_STEP(%a0),%d1                  | 146e6: d2a80036
    tst.w SND_VC_PITCH_RELEASE_STEP(%a0)                      | 146ea: 4a680036
    bmi.s .Lpitch_release_falling                             | 146ee: 6b06
    tst.l %d1                                                 | 146f0: 4a81
    bmi.s .Lpitch_env_store                                   | 146f2: 6b08
    bra.s .Lpitch_release_zero                                | 146f4: 6004
.Lpitch_release_falling:
    tst.l %d1                                                 | 146f6: 4a81
    bgt.s .Lpitch_env_store                                   | 146f8: 6e02
.Lpitch_release_zero:
    moveq #0,%d1                                              | 146fa: 7200
.Lpitch_env_store:
    move.l %d1,SND_VC_PITCH_ENV_ACC(%a0)                      | 146fc: 2141007c

    /* The pitch LFO, which is not a plain triangle: the step is reloaded from one of two fields
     * when the add carries out of 32 bits (rising) or fails to (falling) — a two-rate sweep. */
.Lpitch_lfo:
    move.l SND_VC_PITCH_LFO_LIMIT_HI(%a0),%d0                 | 14700: 2028003a
    beq.s .Lpitch_out                                         | 14704: 6742
    tst.w SND_VC_PITCH_LFO_DELAY(%a0)                         | 14706: 4a68004e
    beq.s .Lpitch_lfo_rising                                  | 1470a: 6706
    subq.w #1,SND_VC_PITCH_LFO_DELAY(%a0)                     | 1470c: 5368004e
    bra.s .Lpitch_out                                         | 14710: 6036
.Lpitch_lfo_rising:
    move.l SND_VC_PITCH_LFO_STEP(%a0),%d1                     | 14712: 2228003e
    bmi.s .Lpitch_lfo_falling                                 | 14716: 6b12
    add.l SND_VC_PITCH_LFO_ACC(%a0),%d1                       | 14718: d2a80080
    bcc.s .Lpitch_lfo_limit_up                                | 1471c: 6406
    move.l SND_VC_PITCH_LFO_STEP_RELOAD_UP(%a0),SND_VC_PITCH_LFO_STEP(%a0)| 1471e: 21680042003e
.Lpitch_lfo_limit_up:
    cmp.l %d0,%d1                                             | 14724: b280
    blt.s .Lpitch_lfo_store                                   | 14726: 6d1c
    bra.s .Lpitch_lfo_fold                                    | 14728: 6014
.Lpitch_lfo_falling:
    move.l SND_VC_PITCH_LFO_LIMIT_LO(%a0),%d0                 | 1472a: 20280046
    add.l SND_VC_PITCH_LFO_ACC(%a0),%d1                       | 1472e: d2a80080
    bcs.s .Lpitch_lfo_limit_down                              | 14732: 6506
    move.l SND_VC_PITCH_LFO_STEP_RELOAD_DOWN(%a0),SND_VC_PITCH_LFO_STEP(%a0)| 14734: 2168004a003e
.Lpitch_lfo_limit_down:
    cmp.l %d0,%d1                                             | 1473a: b280
    bgt.s .Lpitch_lfo_store                                   | 1473c: 6e06
.Lpitch_lfo_fold:
    move.l %d0,%d1                                            | 1473e: 2200
    neg.l SND_VC_PITCH_LFO_STEP(%a0)                          | 14740: 44a8003e
.Lpitch_lfo_store:
    move.l %d1,SND_VC_PITCH_LFO_ACC(%a0)                      | 14744: 21410080

    /* Push the tone period: base * (1 + delta/4096), rounded on its own bit 15 and clamped to 12
     * bits, written low byte then high. */
.Lpitch_out:
    move.w SND_VC_PITCH_PHASE(%a0),%d0                        | 14748: 30280024
    or.w SND_VC_PITCH_LFO_LIMIT_HI(%a0),%d0                   | 1474c: 8068003a
    beq.s .Lnoise_env                                         | 14750: 673e
    move.l SND_VC_PITCH_LFO_ACC(%a0),%d0                      | 14752: 20280080
    add.l SND_VC_PITCH_ENV_ACC(%a0),%d0                       | 14756: d0a8007c
    swap %d0                                                  | 1475a: 4840
    muls.w SND_VC_TONE_PERIOD(%a0),%d0                        | 1475c: c1e80002
    asl.l #4,%d0                                              | 14760: e980
    swap %d0                                                  | 14762: 4840
    bpl.s .Lperiod_bias                                       | 14764: 6a02
    addq.w #1,%d0                                             | 14766: 5240
.Lperiod_bias:
    add.w SND_VC_TONE_PERIOD(%a0),%d0                         | 14768: d0680002
    bpl.s .Lperiod_clamp_high                                 | 1476c: 6a04
    moveq #0,%d0                                              | 1476e: 7000
    bra.s .Lperiod_write                                      | 14770: 600a
.Lperiod_clamp_high:
    cmp_imm_w SND_TONE_PERIOD_MAX,D0                      | 14772: b07c0fff
    ble.s .Lperiod_write                                      | 14776: 6f04
    move.w #SND_TONE_PERIOD_MAX,%d0                           | 14778: 303c0fff
.Lperiod_write:
    move.b %d2,%d1                                            | 1477c: 1202
    add.b %d1,%d1                                             | 1477e: d201
    move.b %d1,(%a1)                                          | 14780: 1281
    move.b %d0,BG_PSG_DATA_OFFSET(%a1)                        | 14782: 13400002
    addq.b #1,%d1                                             | 14786: 5201
    move.b %d1,(%a1)                                          | 14788: 1281
    asr.w #8,%d0                                              | 1478a: e040
    move.b %d0,BG_PSG_DATA_OFFSET(%a1)                        | 1478c: 13400002

    /* The noise machine: the same three-segment envelope as the pitch one, on its own fields. */
.Lnoise_env:
    move.w SND_VC_NOISE_PHASE(%a0),%d0                        | 14790: 30280050
    move.l SND_VC_NOISE_ENV_ACC(%a0),%d1                      | 14794: 22280084
    cmp_imm_b SND_PHASE_ATTACK,D0                         | 14798: b03c0001
    bne.s .Lnoise_seg2                                        | 1479c: 6622
    add.l SND_VC_NOISE_STEP1(%a0),%d1                         | 1479e: d2a80052
    tst.w SND_VC_NOISE_STEP1(%a0)                             | 147a2: 4a680052
    bmi.s .Lnoise_seg1_falling                                | 147a6: 6b08
    cmp.l SND_VC_NOISE_TARGET1(%a0),%d1                       | 147a8: b2a80056
    blt.s .Lnoise_env_store                                   | 147ac: 6d56
    bra.s .Lnoise_seg1_done                                   | 147ae: 6006
.Lnoise_seg1_falling:
    cmp.l SND_VC_NOISE_TARGET1(%a0),%d1                       | 147b0: b2a80056
    bgt.s .Lnoise_env_store                                   | 147b4: 6e4e
.Lnoise_seg1_done:
    move.l SND_VC_NOISE_TARGET1(%a0),%d1                      | 147b6: 22280056
    addq.w #1,SND_VC_NOISE_PHASE(%a0)                         | 147ba: 52680050
    bra.s .Lnoise_env_store                                   | 147be: 6044
.Lnoise_seg2:
    cmp_imm_b SND_PHASE_DECAY,D0                          | 147c0: b03c0002
    bne.s .Lnoise_release                                     | 147c4: 6622
    add.l SND_VC_NOISE_STEP2(%a0),%d1                         | 147c6: d2a8005a
    tst.w SND_VC_NOISE_STEP2(%a0)                             | 147ca: 4a68005a
    bmi.s .Lnoise_seg2_falling                                | 147ce: 6b08
    cmp.l SND_VC_NOISE_TARGET2(%a0),%d1                       | 147d0: b2a8005e
    blt.s .Lnoise_env_store                                   | 147d4: 6d2e
    bra.s .Lnoise_seg2_done                                   | 147d6: 6006
.Lnoise_seg2_falling:
    cmp.l SND_VC_NOISE_TARGET2(%a0),%d1                       | 147d8: b2a8005e
    bgt.s .Lnoise_env_store                                   | 147dc: 6e26
.Lnoise_seg2_done:
    move.l SND_VC_NOISE_TARGET2(%a0),%d1                      | 147de: 2228005e
    addq.w #1,SND_VC_NOISE_PHASE(%a0)                         | 147e2: 52680050
    bra.s .Lnoise_env_store                                   | 147e6: 601c
.Lnoise_release:
    cmp_imm_b SND_PHASE_RELEASE,D0                        | 147e8: b03c0004
    bne.s .Lnoise_lfo                                         | 147ec: 661a
    add.l SND_VC_NOISE_RELEASE_STEP(%a0),%d1                  | 147ee: d2a80062
    tst.w SND_VC_NOISE_RELEASE_STEP(%a0)                      | 147f2: 4a680062
    bmi.s .Lnoise_release_falling                             | 147f6: 6b06
    tst.l %d1                                                 | 147f8: 4a81
    bmi.s .Lnoise_env_store                                   | 147fa: 6b08
    bra.s .Lnoise_release_zero                                | 147fc: 6004
.Lnoise_release_falling:
    tst.l %d1                                                 | 147fe: 4a81
    bgt.s .Lnoise_env_store                                   | 14800: 6e02
.Lnoise_release_zero:
    moveq #0,%d1                                              | 14802: 7200
.Lnoise_env_store:
    move.l %d1,SND_VC_NOISE_ENV_ACC(%a0)                      | 14804: 21410084

    /* ...and the same triangle LFO as the volume one. */
.Lnoise_lfo:
    move.l SND_VC_NOISE_LFO_LIMIT(%a0),%d0                    | 14808: 20280066
    beq.s .Lnoise_out                                         | 1480c: 6728
    tst.w SND_VC_NOISE_LFO_DELAY(%a0)                         | 1480e: 4a68006e
    beq.s .Lnoise_lfo_step                                    | 14812: 6706
    subq.w #1,SND_VC_NOISE_LFO_DELAY(%a0)                     | 14814: 5368006e
    bra.s .Lnoise_out                                         | 14818: 601c
.Lnoise_lfo_step:
    move.l SND_VC_NOISE_LFO_ACC(%a0),%d1                      | 1481a: 22280088
    add.l SND_VC_NOISE_LFO_STEP(%a0),%d1                      | 1481e: d2a8006a
    cmp.l %d0,%d1                                             | 14822: b280
    bge.s .Lnoise_lfo_fold                                    | 14824: 6c06
    neg.l %d0                                                 | 14826: 4480
    cmp.l %d0,%d1                                             | 14828: b280
    bgt.s .Lnoise_lfo_store                                   | 1482a: 6e06
.Lnoise_lfo_fold:
    move.l %d0,%d1                                            | 1482c: 2200
    neg.l SND_VC_NOISE_LFO_STEP(%a0)                          | 1482e: 44a8006a
.Lnoise_lfo_store:
    move.l %d1,SND_VC_NOISE_LFO_ACC(%a0)                      | 14832: 21410088

    /* Push the noise period — ONE register for all three channels, so voice 0, serviced last, is
     * the one that wins. Its upper clamp is a BYTE compare on a word: reproduced, not fixed. */
.Lnoise_out:
    move.w SND_VC_NOISE_PHASE(%a0),%d0                        | 14836: 30280050
    or.w SND_VC_NOISE_LFO_LIMIT(%a0),%d0                      | 1483a: 80680066
    beq.s .Lkey_off                                           | 1483e: 6724
    move.l SND_VC_NOISE_LFO_ACC(%a0),%d0                      | 14840: 20280088
    add.l SND_VC_NOISE_ENV_ACC(%a0),%d0                       | 14844: d0a80084
    swap %d0                                                  | 14848: 4840
    add.w SND_VC_NOISE_PERIOD(%a0),%d0                        | 1484a: d0680004
    bpl.s .Lnoise_clamp_high                                  | 1484e: 6a04
    moveq #0,%d0                                              | 14850: 7000
    bra.s .Lnoise_write                                       | 14852: 6008
.Lnoise_clamp_high:
    cmp_imm_b SND_NOISE_PERIOD_MAX,D0                     | 14854: b03c001f
    ble.s .Lnoise_write                                       | 14858: 6f02
    moveq #SND_NOISE_PERIOD_MAX,%d0                           | 1485a: 701f
.Lnoise_write:
    move.b #PSG_REG_NOISE,(%a1)                               | 1485c: 12bc0006
    move.b %d0,BG_PSG_DATA_OFFSET(%a1)                        | 14860: 13400002

    /* The end of a voice's life, run only while the gate is negative. The counter reaching 0 frees
     * the voice; a second decrement takes it to -1, so the release block fires exactly once. */
.Lkey_off:
    tst.w SND_VC_GATE(%a0)                                    | 14864: 4a680070
    bpl.s .Lnext_voice                                        | 14868: 6a58
    subq.w #1,(%a0)                                           | 1486a: 5350
    bne.s .Lnext_voice                                        | 1486c: 6654
    clr.w SND_VC_PRIORITY(%a0)                                | 1486e: 42680072
    tst.w SND_VC_VOL_PHASE(%a0)                               | 14872: 4a680008
    bne.s .Lkey_off_release                                   | 14876: 660e
    move.b %d2,%d1                                            | 14878: 1202
    addq.w #8,%d1                                             | 1487a: 5041
    move.b %d1,(%a1)                                          | 1487c: 1281
    move.b #0,BG_PSG_DATA_OFFSET(%a1)                         | 1487e: 137c00000002
    bra.s .Lnext_voice                                        | 14884: 603c
.Lkey_off_release:
    subq.w #1,(%a0)                                           | 14886: 5350
    moveq #SND_PHASE_RELEASE,%d0                              | 14888: 7004
    move.w %d0,SND_VC_VOL_PHASE(%a0)                          | 1488a: 31400008
    tst.w SND_VC_PITCH_PHASE(%a0)                             | 1488e: 4a680024
    beq.s .Lkey_off_noise                                     | 14892: 6714
    move.w %d0,SND_VC_PITCH_PHASE(%a0)                        | 14894: 31400024
    move.w SND_VC_PITCH_RELEASE_STEP(%a0),%d1                 | 14898: 32280036
    move.w SND_VC_PITCH_ENV_ACC(%a0),%d3                      | 1489c: 3628007c
    eor.w %d1,%d3                                             | 148a0: b343
    bmi.s .Lkey_off_noise                                     | 148a2: 6b04
    neg.l SND_VC_PITCH_RELEASE_STEP(%a0)                      | 148a4: 44a80036
.Lkey_off_noise:
    tst.w SND_VC_NOISE_PHASE(%a0)                             | 148a8: 4a680050
    beq.s .Lnext_voice                                        | 148ac: 6714
    move.w %d0,SND_VC_NOISE_PHASE(%a0)                        | 148ae: 31400050
    move.w SND_VC_NOISE_RELEASE_STEP(%a0),%d1                 | 148b2: 32280062
    move.w SND_VC_NOISE_ENV_ACC(%a0),%d3                      | 148b6: 36280084
    eor.w %d1,%d3                                             | 148ba: b343
    bmi.s .Lnext_voice                                        | 148bc: 6b04
    neg.l SND_VC_NOISE_RELEASE_STEP(%a0)                      | 148be: 44a80062

    /* Down one record, and round again — then the three duration counters read back from where the
     * cursor now sits, one record BELOW voice 0. */
.Lnext_voice:
    lea -SND_VOICE_BYTES(%a0),%a0                             | 148c2: 41e8ff74
    dbf %d2,.Lvoice                                           | 148c6: 51cafcf6
    move.w SND_VOICE_BYTES(%a0),%d0                           | 148ca: 3028008c
    or.w 2*SND_VOICE_BYTES(%a0),%d0                           | 148ce: 80680118
    or.w 3*SND_VOICE_BYTES(%a0),%d0                           | 148d2: 806801a4
timer_c_sound_isr_body_end:
    /* ...and the original's `bne.s` over its own conterm restore. Its store is
     * `move.b $1493e(pc),$484.w` — one instruction, because the program IS the memory; here both
     * halves are image bytes and the source is past a d16 displacement, so it goes through %d0. */
    bne.s   .Ldone
    move.l  #SND_ISR_SAVED_CONTERM,%d0
    move.b  (%a3,%d0.l),TOS_CONTERM(%a3)
.Ldone:
    movem.l (%sp)+,%d2-%d3/%a2-%a3
    rts
