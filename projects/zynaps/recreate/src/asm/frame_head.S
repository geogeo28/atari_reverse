| frame_head.S — the asm twin for the frame loop's FIRST STAGE, TRANSCRIBED from the original binary.
|
|   frame_panel_scroll_and_ship_stage_asm  <- the original @ [0x10f4e, 0x113c0), the C reference
|                                             frame_panel_scroll_and_ship_stage in ../frame.c
|
| WHAT A TWIN IS is written out in README.md beside this file and in frame.S, and holds here word for
| word: the C in ../frame.c is byte-for-byte equivalent to the original (test/test_frame.py's
| differential against the Musashi oracle), the original's own instructions are in
| ../../out/prg_dis.txt, and everything from the body label on is that instruction sequence in order.
|
| WHAT THE STAGE DOES. It is the loop's head: repaint whichever pieces of the status panel asked for
| one, service the pause key, step the backdrop scroller by one 2-pixel column, arm the mothership
| once the level has scrolled far enough, paint the playfield, then read the joystick and move the
| ship. 240 instructions and fifteen calls.
|
| IT HAS TWO EXITS AND ANSWERS WHICH ONE IT TOOK. The player-control block is guarded by three tests
| — the ship's death explosion running (0x111c4), its record dead (0x111d6), its record exploding
| (0x111de) — and each branches to 0x1167c, PAST the 0x113c0 the fall-through reaches. The C returns
| 1 for the fall-through and 0 for the gated arm, and so does this twin, in %d0.
|
| THE FOUR TRANSLATIONS, and only these four.
|
| **1. The image base — two reserved registers, AND A REGISTER PERMUTATION frame.S did not need.**
| The original IS the image, so it reads globals absolutely (`tst.b $19aad.l`). The reconstruction is
| position-independent and gets the image as a pointer, so the twenty-nine globals this stage names
| become base-relative, and two address registers have to be given up to make that possible:
|
|     %a6 = image            the raw base: argument 0 of every trampoline below, which is what the
|                            door checks against the emulated image base before it substitutes a
|                            host pointer over it
|     %a5 = image + FGB      FGB = 0x18000, so `A_screen_back-FGB(%a5)` is -0x682 and
|                            `A_scroll_col_workspace-FGB(%a5)` +0x1fae — the whole set spans
|                            0x1797e..0x19fae, comfortably inside one signed 16-bit displacement
|
| frame.S can reserve that pair outright because its own span never touches either. THIS span
| touches both — `movea.l $17982.l,a6` is its very first instruction and `movea.l (a0),a5` is at
| 0x1105c — and never once names %a3 or %a4. So the two the original uses are RENAMED onto the two it
| does not:
|
|     the original's a5  ->  %a3          the original's a6  ->  %a4
|
| A rename is the smallest translation there is: same instruction, same addressing mode, same cycle
| count, and every transcribed line below carries the original's own text in its comment where the
| register moved. The alternative — reserving %a3/%a4 and leaving a5/a6 alone — would have put this
| file's global window on a different register from every other twin in the family, which is also
| what `asm_frame_common.windowed_operands` reads for.
|
| test_asm_frame_head.py asserts the window over every operand in this file, so a global added later
| that fell outside it is named here, and refused by gas as "displacement too large for this
| architecture" — the assembler is the gate, this is the message that says which global.
|
| **2. A pointer LOADED OUT OF THE IMAGE is an offset — and this stage never dereferences one, so
| NOTHING here adds the base back.** Read that carefully, because it is the opposite of what
| sprite.S and frame.S do. The four longwords this stage loads out of the image — `A_screen_front`,
| `A_screen_back`, `A_map_page_ptr` and `A_map_ptr`, plus the page pointer it reads out of
| `A_map_page_table` — only ever go through ARITHMETIC (`lea 152(a0),a0`, `adda.l d0,a5`,
| `suba.l #A_map_unpacked,a6`) and then into a core that takes an OFFSET. The reconstruction stores
| them as offsets, so keeping them as offsets is both the correct value and the cheaper one; adding
| %a6 and subtracting it again in the stub would be two instructions the original does not have.
| `lea $19fae.l,a0` (the scroll workspace) and `lea $577fe.l,a5` (the ship's sprite bank) are the
| same story from the other end: the original's absolute-long `lea` loads exactly the offset constant
| the C passes, so those two lines are THE ORIGINAL'S OWN BYTES.
|
| The three registers that DO hold pointers — `A_map_page_table` (dereferenced at 0x1105c),
| `A_player_record` (0x111d6 on) and `A_ship_speed_table` (0x11236 on) — are `lea`d through the
| window and are real pointers, exactly as the original's are real addresses.
|
| **3. TWO SEAMS SPLIT BY BUILD, and they are the pause.** Three of this stage's spins are on
| `A_key_scancode`, a byte only the keyboard interrupt writes. ON TARGET they are the original's own
| instructions, because on a real machine the interrupt really does write it — which is what
| ../../../../tools/recreate_kit/include/sched.h says of itself, and why the target's own sched.h
| supplies a `static inline` with no linkable symbol at all. OFF TARGET they go through the kit so
| the poll ledger sees them, exactly as ../frame.c's `frame_pause_if_space` does: `sched_wait8` for
| the first and third, and for the middle one — a loop whose BODY rewrites both palette counters on
| every pass, so it cannot be a `sched_wait8` — a `sched_poll8` under the same cap and the same
| `os_refused` tally the C uses. The `#ifdef` is IN THE BODY, not hidden in a stub, so the
| transcription-order pin reads both arms.
|
| **THE `#ifdef`-ED INSTRUCTIONS HAVE NO OFF-TARGET SURFACE.** 0x10fe6/0x10fec, 0x10ffe/0x11006 and
| 0x11008/0x1100e assemble only in the target build: a wrong polled byte or a wrong branch there
| passes every test in this workspace. `bash atari/build.sh game && python3 atari/smoke.py game` is
| their surface, and STATUS.md records it as such.
|
| **4. The twenty page blits are called DIRECTLY, not through the door.** The original dispatches
| them through its own table of routine addresses at 0x179aa (`A_scroll_blit_jump_table`), which in
| our world holds the ORIGINAL's addresses and is useless to us; ../frame.c replaces it with a C
| array of function pointers, each wrapped in `ZY_SCROLL()`. So this file carries its own twenty-entry
| table, and it points at WAVE A'S OWN TWINS (`scroll_page_to_screen_pNN_asm`, src/asm/scroll_blit.S),
| which are in this same blob in BOTH builds — off target as well, which is why they need no door
| slot and why asm_frame_common.DOOR_TABLE has no row for them. test_asm_scroll.py has already proved
| each of them byte-equal to the C blit the differential's other shore runs.
|
| The same reasoning does NOT extend to `draw_score_panel` and the three column emitters: those ARE
| in the door table, so off target they reach the host C through it. On target their `ZY_CALL` names
| the wave-A/B twin the C's own `ZY_SCROLL()`/`ZY_TEXT()` seam would have called.
|
| **AND THE BYTE PIN IS GONE, as it is for frame.S** — almost every instruction here names a global.
| WHAT STANDS IN ITS PLACE is named in test_asm_frame_head.py: the differential over staged worlds
| per exit arm, the cost bars, and a TRANSCRIPTION-ORDER pin (all 240 of the original's instruction
| addresses present exactly once, ascending, no gaps and no extras).
|
| TWO PLACES WHERE gas IS CHEAPER THAN THE ORIGINAL, said here rather than hidden (README.md asks
| for exactly this):
|   * `d16(An)` with a ZERO displacement. The original writes `cmpi.w #$42,0(a2)` and
|     `move.w #$40,0(a2)` — mode 101 with a displacement word of 0, 16 cycles. gas shortens
|     `ENTITY_X(%a2)` to `(%a2)`, mode 010, 12 cycles. Six instructions in the ship's horizontal arms
|     (0x112f2, 0x112fc, 0x11308, 0x1139e, 0x113aa, 0x113b4), 4 cycles each, and there is no way to
|     spell the long form in gas that a reader would thank us for.
|   * `lea .Lscroll_blit_table,%a0` assembles PC-relative (8 cycles) where the original's
|     `lea $179aa.l,a0` is absolute long (12). The table is this file's own and PC-relative is the
|     correct addressing for it.
| Both are BELOW the original, so neither can hide a regression behind the cost bars.
|
| REGISTERS. The prologue saves %d2/%d5-%d7 and %a2-%a6 — every callee-saved register the stage
| touches, plus the two it reserves. It does NOT save %d3/%d4: nothing in the span writes them.
| **The surface that catches a clobbered callee-saved register is NOT the differential** (it compares
| the image, and a corrupted %a2 leaves the image perfect and breaks the C CALLER instead): it is
| `bash atari/build.sh game && python3 atari/smoke.py game`. README.md's "Registers" says so at
| length, and it is why this twin is not done until the game smoke is green.

        .text

| WHICH BUILD IS THIS. The kit's Makefile defines RECREATE_HOST_DIFFERENTIAL for the off-target
| assembly (tools/recreate_kit/kit.mk's ASM_CFLAGS); the target build defines nothing. Everything
| door-shaped in this file hangs off the one project-private name below, so the door reads as one
| story rather than as several appearances of a kit marker.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define ZY_ASM_FRAME_HEAD_DOOR 1
#endif


| ---- the constants, named exactly as the headers in ../../include name them ----------------------
| test/test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these to its
| header, and requires every .S to contribute at least one — so a name that drifted from its header
| fails rather than going unchecked.
        .equ    A_asteroid_section_flag,       0x198fd     | init.h
        .equ    A_boss_sequence_active,        0x19aad     | sprite.h
        .equ    A_explosion_group_active_bits, 0x19670     | enemy.h
        .equ    A_explosion_phase_odd,         0x198c5     | enemy.h
        .equ    A_joystick_state,              0x19681     | irq.h
        .equ    A_key_scancode,                0x19685     | irq.h
        .equ    A_map_column,                  0x198a6     | init.h
        .equ    A_map_offset,                  0x1823e     | init.h
        .equ    A_map_page,                    0x198a5     | init.h
        .equ    A_map_page_ptr,                0x17986     | init.h
        .equ    A_map_page_table,              0x1798a     | init.h
        .equ    A_map_ptr,                     0x18242     | init.h
        .equ    A_map_unpacked,                0x478ae     | scroll.h
        .equ    A_mothership_index,            0x1987c     | init.h
        .equ    A_mothership_pending,          0x198af     | init.h
        .equ    A_mothership_prep_stage,       0x19911     | mothership.h
        .equ    A_mothership_ready,            0x198b0     | mothership.h
        .equ    A_palette_rotate_countdown,    0x19684     | irq.h
        .equ    A_palette_swap_countdown,      0x19683     | irq.h
        .equ    A_panel_logo_countdown,        0x19dce     | init.h
        .equ    A_panel_redraw_mask,           0x19904     | hud.h
        .equ    A_player_record,               0x17d7a     | enemy.h
        .equ    A_screen_back,                 0x1797e     | video.h
        .equ    A_screen_front,                0x17982     | video.h
        .equ    A_scroll_col_workspace,        0x19fae     | scroll.h
        .equ    A_scroll_frozen,               0x198b1     | enemy.h
        .equ    A_scroll_pos,                  0x195cc     | init.h
        .equ    A_ship_speed_level,            0x19907     | player.h
        .equ    A_ship_speed_table,            0x19370     | player.h
        .equ    A_ship_sprite_bank,            0x577fe     | frame.h
        .equ    A_ship_tilt,                   0x198b3     | player.h
        .equ    A_ship_tilt_countdown,         0x198b2     | player.h
        .equ    ALIVE_BIT_EXPLODING,           7           | frame.h
        .equ    ENTITY_ALIVE,                  0x0e        | entity.h
        .equ    ENTITY_SPRITE,                 0x0a        | entity.h
        .equ    ENTITY_X,                      0x00        | entity.h
        .equ    ENTITY_Y,                      0x04        | entity.h
        .equ    EXPLOSION_BIT_SHIP_DEATH,      1           | frame.h
        .equ    KEY_SCANCODE_SPACE,            0x39        | frame.h
        .equ    MAP_COLUMN_BYTES,              0x24        | scroll.h
        .equ    MOTHERSHIP_INDEX_SEGMENTED,    5           | frame.h
        .equ    MOTHERSHIP_TRIGGER_SCROLL_POS, 0xc80       | frame.h
        .equ    PANEL_LOGO_PERIOD,             0x1f4       | frame.h
        .equ    PANEL_REDRAW_GAUGE_BIT,        2           | hud.h
        .equ    PANEL_REDRAW_LIVES_BIT,        4           | hud.h
        .equ    PANEL_REDRAW_POWERUP_BIT,      0           | hud.h
        .equ    PANEL_REDRAW_WEAPON_BIT,       1           | hud.h
        .equ    PAUSE_PALETTE_COUNTDOWN,       8           | frame.h
        .equ    SCROLL_PHASES,                 20          | scroll.h
        .equ    SCROLL_WINDOW_BYTES,           152         | scroll.h
        .equ    SHIP_MIRROR_Y,                 0x30        | player.h
        .equ    SHIP_SPEED_DX_LEFT,            0           | frame.h
        .equ    SHIP_SPEED_DX_RIGHT,           2           | frame.h
        .equ    SHIP_SPEED_DY_DOWN,            6           | player.h
        .equ    SHIP_SPEED_DY_UP,              4           | player.h
        .equ    SHIP_SPRITE_GAP,               1600        | sprite.h
        .equ    SHIP_TILT_MAX,                 6           | player.h
        .equ    SHIP_TILT_PERIOD,              4           | player.h
        .equ    SHIP_Y_MAX,                    0x9c        | player.h
        .equ    SHIP_Y_MIN,                    0x20        | player.h

| ...and the ones ../frame.c defines for itself rather than in a header, spelt as that file spells
| them. test_constants.py cannot pin these — there is no header side to pin them to — so
| test_asm_frame_head.py reads the C's own `#define`s and pins them there instead.
        .equ    JOYSTICK_UP_BIT,               0
        .equ    JOYSTICK_DOWN_BIT,             1
        .equ    JOYSTICK_LEFT_BIT,             2
        .equ    JOYSTICK_RIGHT_BIT,            3
        .equ    JOYSTICK_UP_DOWN_MASK,         3
        .equ    SHIP_TILT_CENTRE,              3
        .equ    SHIP_X_HOME,                   0x40
        .equ    SHIP_X_HOME_EDGE,              0x42
        .equ    SHIP_X_MAX,                    0x150
        .equ    SHIP_X_SHADOW_HOME,            0x50
        .equ    SHIP_MIRROR_X,                 0x2c
        .equ    SHIP_MIRROR_SPRITE,            0x36
        .equ    SHIP_TILT_BANK_BYTES,          (2 * SHIP_SPRITE_GAP)
| The shadow's column in the right-hand clamp at 0x113ba, which is DEAD CODE — the `bge` above it
| goes straight to 0x113c0 — and is the one pair of instructions ../frame.c does not transcribe at
| all. This file must: the transcription pin asks for all 240 addresses.
        .equ    SHIP_X_SHADOW_MAX,             0x160

| The two answers, which ../frame.c returns as bare literals rather than as an enum, so there is no
| header spelling for them. test_asm_frame_head.py pins both against the arms it drives.
        .equ    HEAD_EXIT_PLAYER_GATED,        0           | -> 0x1167c, one of the three gates
        .equ    HEAD_EXIT_FELL_THROUGH,        1           | -> 0x113c0

        .equ    ZY_DOOR_sched_wait8,                   16  | wave C's slot, reused by the pause
        .equ    ZY_DOOR_draw_score_panel,              18
        .equ    ZY_DOOR_draw_lives_icons,              19
        .equ    ZY_DOOR_hud_draw_logo_anim,            20
        .equ    ZY_DOOR_hud_draw_powerup_icon,         21
        .equ    ZY_DOOR_hud_draw_weapon_icon,          22
        .equ    ZY_DOOR_draw_power_gauge,              23
        .equ    ZY_DOOR_scroll_emit_tile_column,       24
        .equ    ZY_DOOR_scroll_emit_column_shift2,     25
        .equ    ZY_DOOR_scroll_emit_column_shift0,     26
        .equ    ZY_DOOR_mothership_begin,              27
        .equ    ZY_DOOR_mothership_segments_respawn,   28
        .equ    ZY_DOOR_mothership_spawn_head,         29
        .equ    ZY_DOOR_mothership_sprite_build_step,  30
        .equ    ZY_DOOR_playfield_clear,               31
        .equ    ZY_DOOR_sched_poll8,                   32
        .equ    ZY_DOOR_os_refused,                    33

#ifdef ZY_ASM_FRAME_HEAD_DOOR
| The three PCs the ORIGINAL re-reads the scancode at, which is what a case's `wait_sites` names and
| what the poll ledger keys on. ../frame.c spells the same three as PAUSE_*_WAIT_PC.
        .equ    PAUSE_RELEASE_WAIT_PC,         0x10fe6
        .equ    PAUSE_PRESS_WAIT_PC,           0x10ffe
        .equ    PAUSE_SECOND_RELEASE_WAIT_PC,  0x11008
        .equ    PAUSE_KEY_RELEASED,            0           | `until` — the byte the wait ends on
| The kit's own cap (tools/recreate_kit/include/os.h). The middle spin is spelt out rather than
| wrapped in `sched_wait8`, so it has to carry the cap itself or a case whose schedule never releases
| would hang the twin instead of failing it — ../frame.c's loop says the same thing at length.
        .equ    OS_SCHED_POLL_MAX,             4096
#endif


| The global window's origin. Not a header constant: it is this file's own, and the only thing that
| makes it right is that every global the stage names lands within a signed 16-bit displacement of
| it. test_asm_frame_head.py asserts exactly that over the whole list.
        .equ    FGB, 0x18000

| What the prologue pushes, and the argument offset measured past it.
        .equ    SAVED, (9 * 4)                  | %d2/%d5-%d7 and %a2-%a6
        .equ    ARG_IMAGE, 4 + SAVED

        .macro  HEAD_PROLOGUE
        movem.l %d2/%d5-%d7/%a2-%a6,-(%sp)
        movea.l ARG_IMAGE(%sp),%a6              | the raw image base
        movea.l %a6,%a5
        adda.l  #FGB,%a5                        | ...and the globals' window
        .endm

        .macro  HEAD_EPILOGUE
        movem.l (%sp)+,%d2/%d5-%d7/%a2-%a6
        rts
        .endm

| ================================================================================================
| unsigned frame_panel_scroll_and_ship_stage_asm(uint8_t *image)
|
| THE REGISTER RENAME, once more where the body starts using it: %a3 is the original's a5 and %a4 is
| the original's a6. Every line whose register moved carries the original's own text in its comment.
| ================================================================================================
        .globl  frame_panel_scroll_and_ship_stage_asm
frame_panel_scroll_and_ship_stage_asm:
        HEAD_PROLOGUE
        .globl  frame_panel_scroll_and_ship_stage_body
frame_panel_scroll_and_ship_stage_body:

| ==== band 1 — 0x10f4e .. 0x10fd8 ================================================================
| The status panel: the score, the lives strip, the logo animation on an idle panel, and the three
| bits that each run one repaint and then clear themselves.
    movea.l A_screen_front-FGB(%a5),%a4                     | 010f4e movea.l $17982.l,a6
    jbsr    door_draw_score_panel                           | 010f54 bsr.w $136c8
    btst    #PANEL_REDRAW_LIVES_BIT,A_panel_redraw_mask-FGB(%a5)    | 010f58 btst #4,$19904.l
    jbeq    .L10f68                                         | 010f60
    jbsr    door_draw_lives_icons                           | 010f64 bsr.w $134ca
.L10f68:
    not.b   A_explosion_phase_odd-FGB(%a5)                  | 010f68
| The logo runs only while NO repaint at all is pending — `tst.b` on the whole mask, not on a bit.
    tst.b   A_panel_redraw_mask-FGB(%a5)                    | 010f6e
    jbne    .L10f90                                         | 010f74
    subi.w  #1,A_panel_logo_countdown-FGB(%a5)              | 010f78
    jbne    .L10f90                                         | 010f80
    move.w  #PANEL_LOGO_PERIOD,A_panel_logo_countdown-FGB(%a5)      | 010f84
    jbsr    door_hud_draw_logo_anim                         | 010f8c bsr.w $1452c
.L10f90:
    btst    #PANEL_REDRAW_POWERUP_BIT,A_panel_redraw_mask-FGB(%a5)  | 010f90
    jbeq    .L10fa8                                         | 010f98
    jbsr    door_hud_draw_powerup_icon                      | 010f9c bsr.w $1459c
    bclr    #PANEL_REDRAW_POWERUP_BIT,A_panel_redraw_mask-FGB(%a5)  | 010fa0
.L10fa8:
    btst    #PANEL_REDRAW_WEAPON_BIT,A_panel_redraw_mask-FGB(%a5)   | 010fa8
    jbeq    .L10fc2                                         | 010fb0
    clr.b   %d0                                             | 010fb4 the icon's LEFT cell
    jbsr    door_hud_draw_weapon_icon                       | 010fb6 bsr.w $145da
    bclr    #PANEL_REDRAW_WEAPON_BIT,A_panel_redraw_mask-FGB(%a5)   | 010fba
.L10fc2:
    btst    #PANEL_REDRAW_GAUGE_BIT,A_panel_redraw_mask-FGB(%a5)    | 010fc2
    jbeq    .L10fda                                         | 010fca
    jbsr    door_draw_power_gauge                           | 010fce bsr.w $137ca
    bclr    #PANEL_REDRAW_GAUGE_BIT,A_panel_redraw_mask-FGB(%a5)    | 010fd2

| ==== band 2 — 0x10fda .. 0x1100e ================================================================
| THE PAUSE, and the one place in this file whose instructions differ by build. Space held down
| pauses: wait for the release, then loop restarting both palette counters until it is pressed
| again, then wait for THAT release. The header says why the middle one cannot be a `sched_wait8`
| and why neither arm's operands have an off-target surface.
.L10fda:
    cmpi.b  #KEY_SCANCODE_SPACE,A_key_scancode-FGB(%a5)     | 010fda
    jbne    .L11010                                         | 010fe2
#ifdef ZY_ASM_FRAME_HEAD_DOOR
        jbsr    door_sched_wait_pause_release           |         the kit's counted, capped wait
        tst.l   %d0
        jbeq    .L11010                                 |         cap exhausted -> the pause is void
        moveq   #0,%d1                                  |         ...and the cap's own poll counter
#else
.L10fe6:
    tst.b   A_key_scancode-FGB(%a5)                         | 010fe6
    jbne    .L10fe6                                         | 010fec
#endif
.L10fee:
    move.b  #PAUSE_PALETTE_COUNTDOWN,A_palette_swap_countdown-FGB(%a5)      | 010fee
    move.b  #PAUSE_PALETTE_COUNTDOWN,A_palette_rotate_countdown-FGB(%a5)    | 010ff6
#ifdef ZY_ASM_FRAME_HEAD_DOOR
        jbsr    door_sched_poll_pause_press             |         %d0 = the byte, through the kit
        cmpi.b  #KEY_SCANCODE_SPACE,%d0
        jbeq    .L11008                                 |         pressed again -> wait for release
        addq.l  #1,%d1
        cmpi.l  #OS_SCHED_POLL_MAX,%d1
        jbcs    .L10fee                                 |         under the cap -> another pass
        jbsr    door_os_refused                         |         at it -> tally, and give the pause up
        jbra    .L11010
#else
    cmpi.b  #KEY_SCANCODE_SPACE,A_key_scancode-FGB(%a5)     | 010ffe
    jbne    .L10fee                                         | 011006
#endif
.L11008:
#ifdef ZY_ASM_FRAME_HEAD_DOOR
        jbsr    door_sched_wait_pause_second_release    |         ...whose answer the C discards too
#else
    tst.b   A_key_scancode-FGB(%a5)                         | 011008
    jbne    .L11008                                         | 01100e
#endif

| ==== band 3 — 0x11010 .. 0x11100 ================================================================
| The scroller. A boss encounter owns the playfield and skips it entirely; an asteroid section has no
| map, so its cursor is DERIVED from the scroll position; otherwise page 0 of the eight-page ring
| decodes a fresh tile column and pages 1..7 re-emit page 0's workspace two pixels further along.
.L11010:
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011010
    jbne    .L11102                                         | 011016
    tst.b   A_asteroid_section_flag-FGB(%a5)                | 01101a
    jbeq    .L11046                                         | 011020
    move.l  A_scroll_pos-FGB(%a5),%d7                       | 011024
    lsr.l   #3,%d7                                          | 01102a undoes SCROLL_PHASE_STEP
    mulu.w  #MAP_COLUMN_BYTES,%d7                           | 01102c
    move.l  %d7,A_map_offset-FGB(%a5)                       | 011030
    addi.l  #A_map_unpacked,%d7                             | 011036 add.l #$478ae,d7 (gas: ADDI)
    move.l  %d7,A_map_ptr-FGB(%a5)                          | 01103c
    jbra    .L11102                                         | 011042
.L11046:
    move.b  A_map_page-FGB(%a5),%d0                         | 011046
    andi.l  #0xff,%d0                                       | 01104c and.l #$ff,d0 (gas: ANDI)
    lsl.l   #2,%d0                                          | 011052 one MAP_PAGE_PTR_BYTES pointer
    lea     A_map_page_table-FGB(%a5),%a0                   | 011054 a REAL POINTER: read below
    adda.l  %d0,%a0                                         | 01105a
    movea.l (%a0),%a3                                       | 01105c movea.l (a0),a5 — an OFFSET
    move.l  %a3,A_map_page_ptr-FGB(%a5)                     | 01105e move.l a5,$17986.l
    tst.b   A_map_page-FGB(%a5)                             | 011064
    jbne    .L110c6                                         | 01106a
| Page 0. `map_offset` is republished from the cursor only on the UNFROZEN arm; the frozen one steps
| the cursor back a column and leaves the offset where it was.
    movea.l A_map_ptr-FGB(%a5),%a4                          | 01106e movea.l $18242.l,a6 — an OFFSET
    tst.b   A_scroll_frozen-FGB(%a5)                        | 011074
    jbeq    .L11086                                         | 01107a
    lea     -MAP_COLUMN_BYTES(%a4),%a4                      | 01107e lea -36(a6),a6
    jbra    .L11098                                         | 011082
.L11086:
    suba.l  #A_map_unpacked,%a4                             | 011086 suba.l #$478ae,a6
    move.l  %a4,A_map_offset-FGB(%a5)                       | 01108c move.l a6,$1823e.l
    movea.l A_map_ptr-FGB(%a5),%a4                          | 011092 movea.l $18242.l,a6
.L11098:
    movea.l A_map_page_ptr-FGB(%a5),%a3                     | 011098 movea.l $17986.l,a5
    move.b  A_map_column-FGB(%a5),%d0                       | 01109e
    andi.l  #0xff,%d0                                       | 0110a4
    lsl.l   #3,%d0                                          | 0110aa one SCROLL_PHASE_STEP cell
    adda.l  %d0,%a3                                         | 0110ac adda.l d0,a5
    movea.l A_screen_back-FGB(%a5),%a0                      | 0110ae the back buffer, an OFFSET
    lea     SCROLL_WINDOW_BYTES(%a0),%a0                    | 0110b4 lea 152(a0),a0
    jbsr    door_scroll_emit_tile_column                    | 0110b8 bsr.w $162c2
    move.l  %a4,A_map_ptr-FGB(%a5)                          | 0110bc move.l a6,$18242.l — the cursor
    jbra    .L11102                                         | 0110c2
| Pages 1..7: re-emit the workspace page 0 filled.
.L110c6:
    movea.l A_map_page_ptr-FGB(%a5),%a1                     | 0110c6
    move.b  A_map_column-FGB(%a5),%d0                       | 0110cc
    andi.l  #0xff,%d0                                       | 0110d2
    lsl.l   #3,%d0                                          | 0110d8
    adda.l  %d0,%a1                                         | 0110da
    movea.l A_screen_back-FGB(%a5),%a2                      | 0110dc
    lea     SCROLL_WINDOW_BYTES(%a2),%a2                    | 0110e2 lea 152(a2),a2
    lea     A_scroll_col_workspace,%a0                      | 0110e6 THE ORIGINAL'S OWN BYTES: the
                                                            |        absolute-long `lea` loads
                                                            |        exactly the offset the C passes
    tst.b   A_scroll_frozen-FGB(%a5)                        | 0110ec
    jbne    .L110fe                                         | 0110f2
    jbsr    door_scroll_emit_column_shift2                  | 0110f6 bsr.w $169f2
    jbra    .L11102                                         | 0110fa
.L110fe:
    jbsr    door_scroll_emit_column_shift0                  | 0110fe bsr.w $16a56

| ==== band 4 — 0x11102 .. 0x111c2 ================================================================
| The mothership trigger and its per-frame build step, then the playfield: cleared for a boss or an
| asteroid field, otherwise one of the twenty specialised page blits.
.L11102:
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011102
    jbne    .L1115c                                         | 011108
    tst.b   A_mothership_ready-FGB(%a5)                     | 01110c
    jbne    .L1115c                                         | 011112
    cmpi.l  #MOTHERSHIP_TRIGGER_SCROLL_POS,A_scroll_pos-FGB(%a5)    | 011116
    jblt    .L1115c                                         | 011120
    move.b  #1,A_mothership_pending-FGB(%a5)                | 011124
    move.b  #1,A_scroll_frozen-FGB(%a5)                     | 01112c
    move.b  A_mothership_index-FGB(%a5),%d2                 | 011134
    ext.w   %d2                                             | 01113a
    cmpi.w  #MOTHERSHIP_INDEX_SEGMENTED,%d2                 | 01113c cmp.w #$5,d2 (gas: CMPI)
    jbge    .L11150                                         | 011140
| Neither callee reads a register, so the two `move.w`s below name nothing — include/frame.h says so
| where it declines to give them constants. They are transcribed because they are the original's.
    move.w  #0,%d5                                          | 011144
    jbsr    door_mothership_begin                           | 011148 bsr.w $14eda
    jbra    .L1115c                                         | 01114c
.L11150:
    move.w  #0xa,%d2                                        | 011150
    move.w  #0,%d5                                          | 011154
    jbsr    door_mothership_segments_respawn                | 011158 bsr.w $1504a
.L1115c:
    tst.b   A_mothership_prep_stage-FGB(%a5)                | 01115c
    jbeq    .L11182                                         | 011162
| A BYTE compare of a sign-extended byte, where the trigger above makes a WORD one of the same
| global. Transcribed, not tidied.
    move.b  A_mothership_index-FGB(%a5),%d2                 | 011166
    ext.w   %d2                                             | 01116c
    cmpi.b  #MOTHERSHIP_INDEX_SEGMENTED,%d2                 | 01116e cmp.b #$5,d2 (gas: CMPI)
    jbge    .L1117e                                         | 011172
    jbsr    door_mothership_spawn_head                      | 011176 bsr.w $14f64
    jbra    .L11182                                         | 01117a
.L1117e:
    jbsr    door_mothership_sprite_build_step               | 01117e bsr.w $15128
.L11182:
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011182
    jbne    .L11196                                         | 011188
    tst.b   A_asteroid_section_flag-FGB(%a5)                | 01118c
    jbeq    .L1119e                                         | 011192
.L11196:
    jbsr    door_playfield_clear                            | 011196 bsr.w $1597c
    jbra    .L111c4                                         | 01119a
.L1119e:
    movea.l A_screen_back-FGB(%a5),%a4                      | 01119e movea.l $1797e.l,a6 — an OFFSET
    movea.l A_map_page_ptr-FGB(%a5),%a3                     | 0111a4 movea.l $17986.l,a5 — an OFFSET
    move.b  A_map_column-FGB(%a5),%d0                       | 0111aa
    andi.l  #0xff,%d0                                       | 0111b0
    lsl.l   #2,%d0                                          | 0111b6 one entry of the table below
    lea     .Lscroll_blit_table,%a0                         | 0111b8 lea $179aa.l,a0 — OURS, because
                                                            |        the original's table holds the
                                                            |        original's own addresses
    adda.l  %d0,%a0                                         | 0111be
    movea.l (%a0),%a1                                       | 0111c0
    jsr     (%a1)                                           | 0111c2

| ==== band 5 — 0x111c4 .. 0x113ba ================================================================
| The three player gates, the tilt auto-recentre, and the joystick's four directions. Everything from
| 0x111c4 to 0x111e2 is the stage's OTHER exit.
.L111c4:
    btst    #EXPLOSION_BIT_SHIP_DEATH,A_explosion_group_active_bits-FGB(%a5)    | 0111c4
    jbne    .Lexit_player_gated                             | 0111cc bne.w $1167c
    lea     A_player_record-FGB(%a5),%a2                     | 0111d0 a REAL POINTER: read below
    move.b  ENTITY_ALIVE(%a2),%d0                           | 0111d6 move.b 14(a2),d0
    jbeq    .Lexit_player_gated                             | 0111da beq.w $1167c
    btst    #ALIVE_BIT_EXPLODING,%d0                        | 0111de
    jbne    .Lexit_player_gated                             | 0111e2 bne.w $1167c
| The auto-centre: with neither up nor down pressed the tilt bank rolls back towards its middle
| frame, one step every SHIP_TILT_PERIOD frames, and the ship's y follows it.
    move.b  A_joystick_state-FGB(%a5),%d0                   | 0111e6
    andi.b  #JOYSTICK_UP_DOWN_MASK,%d0                      | 0111ec and.b #$3,d0 (gas: ANDI)
    jbne    .L1128e                                         | 0111f0
    subi.b  #1,A_ship_tilt_countdown-FGB(%a5)               | 0111f4
    jbne    .L1128e                                         | 0111fc
    move.b  #SHIP_TILT_PERIOD,A_ship_tilt_countdown-FGB(%a5)        | 011200
    move.b  A_ship_tilt-FGB(%a5),%d0                        | 011208
    cmpi.b  #SHIP_TILT_CENTRE,%d0                           | 01120e cmp.b #$3,d0 (gas: CMPI)
    jbeq    .L1128e                                         | 011212
    lea     A_ship_speed_table-FGB(%a5),%a4                 | 011216 lea $19370.l,a6 — a REAL POINTER
    move.b  A_ship_speed_level-FGB(%a5),%d0                 | 01121c
    ext.w   %d0                                             | 011222
    lsl.l   #3,%d0                                          | 011224 one SHIP_SPEED_ENTRY_BYTES entry
    adda.w  %d0,%a4                                         | 011226 adda.w d0,a6
    move.b  A_ship_tilt-FGB(%a5),%d0                        | 011228
    cmpi.b  #SHIP_TILT_CENTRE,%d0                           | 01122e
    jblt    .L11264                                         | 011232
    move.w  SHIP_SPEED_DY_DOWN(%a4),%d0                     | 011236 move.w 6(a6),d0
    add.w   %d0,ENTITY_Y(%a2)                               | 01123a add.w d0,4(a2)
    add.w   %d0,SHIP_MIRROR_Y(%a2)                          | 01123e add.w d0,48(a2)
    cmpi.w  #SHIP_Y_MAX,ENTITY_Y(%a2)                       | 011242
    jble    .L11258                                         | 011248
    move.w  #SHIP_Y_MAX,ENTITY_Y(%a2)                       | 01124c
    move.w  #SHIP_Y_MAX,SHIP_MIRROR_Y(%a2)                  | 011252
.L11258:
    subi.b  #1,A_ship_tilt-FGB(%a5)                         | 011258
    jbra    .L1128e                                         | 011260
.L11264:
    move.w  SHIP_SPEED_DY_UP(%a4),%d0                       | 011264 move.w 4(a6),d0
    sub.w   %d0,ENTITY_Y(%a2)                               | 011268
    sub.w   %d0,SHIP_MIRROR_Y(%a2)                          | 01126c
    cmpi.w  #SHIP_Y_MIN,ENTITY_Y(%a2)                       | 011270
    jbge    .L11286                                         | 011276
    move.w  #SHIP_Y_MIN,ENTITY_Y(%a2)                       | 01127a
    move.w  #SHIP_Y_MIN,SHIP_MIRROR_Y(%a2)                  | 011280
.L11286:
    addi.b  #1,A_ship_tilt-FGB(%a5)                         | 011286
| The joystick decode. The two vertical arms are routines ../../names.txt names (`ship_move_up`,
| `ship_move_down`) and are transcribed in place below; the horizontal ones have no `rts` of their
| own — `bra 0x113c0` ends each of them.
.L1128e:
    move.b  A_ship_speed_level-FGB(%a5),%d0                 | 01128e
    ext.w   %d0                                             | 011294
    lsl.l   #3,%d0                                          | 011296
    lea     A_ship_speed_table-FGB(%a5),%a4                 | 011298 lea $19370.l,a6
    adda.w  %d0,%a4                                         | 01129e adda.w d0,a6
    move.b  A_joystick_state-FGB(%a5),%d0                   | 0112a0
    btst    #JOYSTICK_UP_BIT,%d0                            | 0112a6
    jbeq    .L112b2                                         | 0112aa
    jbsr    .L11318                                         | 0112ae bsr.w $11318 ship_move_up
.L112b2:
    btst    #JOYSTICK_DOWN_BIT,%d0                          | 0112b2
    jbeq    .L112be                                         | 0112b6
    jbsr    .L1135a                                         | 0112ba bsr.w $1135a ship_move_down
.L112be:
    move.b  A_ship_tilt-FGB(%a5),%d1                        | 0112be
    andi.l  #0xff,%d1                                       | 0112c4
    mulu.w  #SHIP_TILT_BANK_BYTES,%d1                       | 0112ca one tilt frame: ship + shadow
    lea     A_ship_sprite_bank,%a3                          | 0112ce lea $577fe.l,a5 — THE ORIGINAL'S
                                                            |        OWN BYTES: a longword naming a
                                                            |        sprite bank is ALREADY an offset
    adda.l  %d1,%a3                                         | 0112d4 adda.l d1,a5
    move.l  %a3,ENTITY_SPRITE(%a2)                          | 0112d6 move.l a5,10(a2)
    lea     SHIP_SPRITE_GAP(%a3),%a3                        | 0112da lea 1600(a5),a5
    move.l  %a3,SHIP_MIRROR_SPRITE(%a2)                     | 0112de move.l a5,54(a2)
    btst    #JOYSTICK_RIGHT_BIT,%d0                         | 0112e2
    jbne    .L1139e                                         | 0112e6
    btst    #JOYSTICK_LEFT_BIT,%d0                          | 0112ea
    jbeq    .Lexit_fell_through                             | 0112ee beq.w $113c0
    cmpi.w  #SHIP_X_HOME_EDGE,ENTITY_X(%a2)                 | 0112f2
    jble    .L11308                                         | 0112f8
    move.w  SHIP_SPEED_DX_LEFT(%a4),%d6                     | 0112fa move.w (a6),d6
    sub.w   %d6,ENTITY_X(%a2)                               | 0112fc
    sub.w   %d6,SHIP_MIRROR_X(%a2)                          | 011300 sub.w d6,44(a2)
    jbra    .Lexit_fell_through                             | 011304 bra.w $113c0
.L11308:
    move.w  #SHIP_X_HOME,ENTITY_X(%a2)                      | 011308
    move.w  #SHIP_X_SHADOW_HOME,SHIP_MIRROR_X(%a2)          | 01130e
    jbra    .Lexit_fell_through                             | 011314 bra.w $113c0
| ---- ship_move_up @ 0x11318, `bsr`d from 0x112ae ------------------------------------------------
.L11318:
    subq.b  #1,A_ship_tilt_countdown-FGB(%a5)               | 011318
    jbne    .L11336                                         | 01131e
    move.b  #SHIP_TILT_PERIOD,A_ship_tilt_countdown-FGB(%a5)        | 011320
    tst.b   A_ship_tilt-FGB(%a5)                            | 011328
    jbeq    .L11336                                         | 01132e
    subq.b  #1,A_ship_tilt-FGB(%a5)                         | 011330
.L11336:
    cmpi.w  #SHIP_Y_MIN,ENTITY_Y(%a2)                       | 011336
    jble    .L1134c                                         | 01133c
    move.w  SHIP_SPEED_DY_UP(%a4),%d6                       | 01133e move.w 4(a6),d6
    sub.w   %d6,ENTITY_Y(%a2)                               | 011342
    sub.w   %d6,SHIP_MIRROR_Y(%a2)                          | 011346
    rts                                                     | 01134a
.L1134c:
    move.w  #SHIP_Y_MIN,ENTITY_Y(%a2)                       | 01134c
    move.w  #SHIP_Y_MIN,SHIP_MIRROR_Y(%a2)                  | 011352
    rts                                                     | 011358
| ---- ship_move_down @ 0x1135a, `bsr`d from 0x112ba ----------------------------------------------
.L1135a:
    subq.b  #1,A_ship_tilt_countdown-FGB(%a5)               | 01135a
    jbne    .L1137a                                         | 011360
    move.b  #SHIP_TILT_PERIOD,A_ship_tilt_countdown-FGB(%a5)        | 011362
    cmpi.b  #SHIP_TILT_MAX,A_ship_tilt-FGB(%a5)             | 01136a
    jbeq    .L1137a                                         | 011372
    addq.b  #1,A_ship_tilt-FGB(%a5)                         | 011374
.L1137a:
    cmpi.w  #SHIP_Y_MAX,ENTITY_Y(%a2)                       | 01137a
    jbge    .L11390                                         | 011380
    move.w  SHIP_SPEED_DY_DOWN(%a4),%d6                     | 011382 move.w 6(a6),d6
    add.w   %d6,ENTITY_Y(%a2)                               | 011386
    add.w   %d6,SHIP_MIRROR_Y(%a2)                          | 01138a
    rts                                                     | 01138e
.L11390:
    move.w  #SHIP_Y_MAX,ENTITY_Y(%a2)                       | 011390
    move.w  #SHIP_Y_MAX,SHIP_MIRROR_Y(%a2)                  | 011396
    rts                                                     | 01139c
| ---- the joystick's right-hand arm @ 0x1139e, and the clamp that is DEAD CODE -------------------
| `bge` at 0x113a4 goes straight to 0x113c0, so 0x113b4 and 0x113ba are unreachable. ../frame.c does
| not transcribe them at all and says so; this file must, because the transcription pin asks for all
| 240 addresses. They are laid out where they are so that a fall-through — which cannot happen —
| would still land on the stage's own 0x113c0 exit rather than on a trampoline.
.L1139e:
    cmpi.w  #SHIP_X_MAX,ENTITY_X(%a2)                       | 01139e
    jbge    .Lexit_fell_through                             | 0113a4 bge.s $113c0
    move.w  SHIP_SPEED_DX_RIGHT(%a4),%d6                    | 0113a6 move.w 2(a6),d6
    add.w   %d6,ENTITY_X(%a2)                               | 0113aa
    add.w   %d6,SHIP_MIRROR_X(%a2)                          | 0113ae
    jbra    .Lexit_fell_through                             | 0113b2 bra.s $113c0
    move.w  #SHIP_X_MAX,ENTITY_X(%a2)                       | 0113b4 DEAD CODE
    move.w  #SHIP_X_SHADOW_MAX,SHIP_MIRROR_X(%a2)           | 0113ba DEAD CODE

| ================================================================================================
| THE TWO EXITS. The original does not `rts`: it either runs on into 0x113c0 (the next slice) or
| `bra`s to 0x1167c past it. `frame_loop_once` stays C, so the twin answers with which of the two it
| would have taken — exactly what `frame_panel_scroll_and_ship_stage` returns.
| ================================================================================================
.Lexit_fell_through:                            | -> 0x113c0
        moveq   #HEAD_EXIT_FELL_THROUGH,%d0
        jbra    .Lreturn
.Lexit_player_gated:                            | -> 0x1167c
        moveq   #HEAD_EXIT_PLAYER_GATED,%d0
.Lreturn:
        HEAD_EPILOGUE

| ================================================================================================
| THE TRAMPOLINES — one thin block per callee, and the whole of the register translation.
|
| The original passes its callees' arguments IN REGISTERS and reads one answer back out of one. The
| reconstruction's cores carry C signatures and the m68k SysV ABI, so each site needs a block that
| binds one to the other. They all have the same four parts:
|
|   1. save the ABI's CALL-CLOBBERED file (%d0-%d1/%a0-%a1). The C cores preserve %d2-%d7/%a2-%a6 by
|      the ABI, so with this `movem` a trampoline preserves EVERY register — which is what the
|      original's callees do and what the twin's own instructions after the call assume. The one
|      that must DELIVER a value saves less, and says so where it does it.
|   2. push the arguments right to left and call.
|   3. apply the answer, where the site reads one.
|   4. restore and `rts`.
|
| NO STUB HERE NEEDS frame.S's PUSH_OFFSET, AND THAT IS A PROPERTY OF THIS STAGE rather than an
| oversight: every argument it passes is ALREADY an image offset (this file's header, translation 2).
| The three registers that hold real pointers — the map page table, the player record, the ship speed
| table — are never passed to anybody.
|
| SO EVERY STUB IS X-TRANSPARENT, and nothing here has to carry the 68000's X: this span contains no
| `abcd`/`addx` and no site reads a condition code across a call — every one of the fifteen is
| followed by a `btst`, a `tst`, a `bclr`, a `move` or a `bra`, all of which set or ignore the flags
| themselves. `move.l An,-(%sp)` touches N/Z/V/C and never X, and `lea`/`movem`/`rts` touch nothing.
|
| WHAT THE DOOR IS. Off target there is no C in the emulated address space at all, so `ZY_DOOR_*`
| names an address the harness watches for: the twin `jsr`s to it, tools/recreate_kit/asm_twin.py
| services the callback by calling the host C, and resumes the blob. ON TARGET the door does not
| exist and the same `jsr` names the real core — and where that core has a twin of its own, the
| `ZY_CALL` below names the TWIN, because that is what ../frame.c's own `ZY_SCROLL()`/`ZY_TEXT()`
| seam resolves to on target. The bodies above are identical either way.
| ================================================================================================
| THE DOOR'S BAND IS THE KIT'S CONSTANT, USED DIRECTLY. tools/recreate_kit/asm_twin.py owns
| DOOR_BASE/DOOR_STRIDE because it is what WATCHES the band, and kit.mk passes both in as -D's. An
| `.equ` of our own here would be a second spelling with nothing pinning it equal.
#ifdef ZY_ASM_FRAME_HEAD_DOOR
# define ZY_CALL(slot, fn)      jsr     (RECREATE_DOOR_BASE + (slot) * RECREATE_DOOR_STRIDE)
#else
# define ZY_CALL(slot, fn)      jsr     fn
#endif

        .macro  SCRATCH_SAVE
        movem.l %d0-%d1/%a0-%a1,-(%sp)
        .endm
        .macro  SCRATCH_RESTORE
        movem.l (%sp)+,%d0-%d1/%a0-%a1
        .endm

| ---- void draw_score_panel(uint8_t *image, uint32_t buffer) ---- A4 = the front buffer's OFFSET
        .globl  door_draw_score_panel
door_draw_score_panel:
        SCRATCH_SAVE
        move.l  %a4,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_draw_score_panel, draw_score_panel_asm)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void draw_lives_icons(uint8_t *image) ----
        .globl  door_draw_lives_icons
door_draw_lives_icons:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_draw_lives_icons, draw_lives_icons)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void hud_draw_logo_anim(uint8_t *image) ----
        .globl  door_hud_draw_logo_anim
door_hud_draw_logo_anim:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_hud_draw_logo_anim, hud_draw_logo_anim)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void hud_draw_powerup_icon(uint8_t *image) ----
        .globl  door_hud_draw_powerup_icon
door_hud_draw_powerup_icon:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_hud_draw_powerup_icon, hud_draw_powerup_icon)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void hud_draw_weapon_icon(uint8_t *image, uint8_t right_cell) ---- D0 = the cell
|
| The parameter is a `uint8_t` and the original's callee reads it with `tst.b d0` (0x145e6), so only
| the LOW BYTE of the longword pushed here is ever read — which is as well, because the site's own
| `clr.b %d0` at 0x10fb4 leaves the other three bytes of %d0 exactly as it found them.
        .globl  door_hud_draw_weapon_icon
door_hud_draw_weapon_icon:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_hud_draw_weapon_icon, hud_draw_weapon_icon)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void draw_power_gauge(uint8_t *image) ----
        .globl  door_draw_power_gauge
door_draw_power_gauge:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_draw_power_gauge, draw_power_gauge)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- uint32_t scroll_emit_tile_column(uint8_t *image, uint32_t screen_edge, uint32_t page,
|                                       uint32_t map_column) ---- A0, A3, A4; the answer in A4
|
| THE ONE THAT DELIVERS A REGISTER. The original's callee leaves the next map cursor in its A6 —
| this file's %a4 — and 0x110bc stores it, so the C's return value goes back there. %a4 is not in
| SCRATCH_SAVE's list, so the restore below cannot undo it.
        .globl  door_scroll_emit_tile_column
door_scroll_emit_tile_column:
        SCRATCH_SAVE
        move.l  %a4,-(%sp)                      | the map cursor
        move.l  %a3,-(%sp)                      | the page, already stepped to this column's cell
        move.l  %a0,-(%sp)                      | the screen edge
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_scroll_emit_tile_column, scroll_emit_tile_column_asm)
        lea     16(%sp),%sp
        movea.l %d0,%a4                         | the cursor the original's callee answers in A6
        SCRATCH_RESTORE
        rts

| ---- void scroll_emit_column_shift2(uint8_t *image, uint32_t workspace, uint32_t page,
|                                     uint32_t edge) ---- A0, A1, A2
        .globl  door_scroll_emit_column_shift2
door_scroll_emit_column_shift2:
        SCRATCH_SAVE
        move.l  %a2,-(%sp)
        move.l  %a1,-(%sp)
        move.l  %a0,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_scroll_emit_column_shift2, scroll_emit_column_shift2_asm)
        lea     16(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void scroll_emit_column_shift0(uint8_t *image, uint32_t workspace, uint32_t page,
|                                     uint32_t edge) ---- A0, A1, A2
        .globl  door_scroll_emit_column_shift0
door_scroll_emit_column_shift0:
        SCRATCH_SAVE
        move.l  %a2,-(%sp)
        move.l  %a1,-(%sp)
        move.l  %a0,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_scroll_emit_column_shift0, scroll_emit_column_shift0_asm)
        lea     16(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void mothership_begin(uint8_t *image) ----
        .globl  door_mothership_begin
door_mothership_begin:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_begin, mothership_begin)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void mothership_segments_respawn(uint8_t *image) ----
        .globl  door_mothership_segments_respawn
door_mothership_segments_respawn:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_segments_respawn, mothership_segments_respawn)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void mothership_spawn_head(uint8_t *image) ----
        .globl  door_mothership_spawn_head
door_mothership_spawn_head:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_spawn_head, mothership_spawn_head)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void mothership_sprite_build_step(uint8_t *image) ----
        .globl  door_mothership_sprite_build_step
door_mothership_sprite_build_step:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_sprite_build_step, mothership_sprite_build_step)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void playfield_clear(uint8_t *image) ----
        .globl  door_playfield_clear
door_playfield_clear:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_playfield_clear, playfield_clear)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- the twenty page blits, and the table 0x111b8 indexes ---------------------------------------
|
| NOT DOORS, in either build: each entry calls WAVE A'S OWN TWIN, which is in this same blob (this
| file's header, translation 4). One trampoline apiece rather than one shared block reached by a
| `bra`, because the shared form would cost this per-frame call an extra `lea` and `bra` to save
| nineteen copies of six instructions a macro writes anyway.
        .macro  BLIT_TRAMPOLINE twin
        SCRATCH_SAVE
        move.l  %a4,-(%sp)                      | the back buffer, an OFFSET
        move.l  %a3,-(%sp)                      | the page, an OFFSET
        move.l  %a6,-(%sp)
        jsr     \twin
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts
        .endm

.Lblit_p00:     BLIT_TRAMPOLINE scroll_page_to_screen_p00_asm
.Lblit_p01:     BLIT_TRAMPOLINE scroll_page_to_screen_p01_asm
.Lblit_p02:     BLIT_TRAMPOLINE scroll_page_to_screen_p02_asm
.Lblit_p03:     BLIT_TRAMPOLINE scroll_page_to_screen_p03_asm
.Lblit_p04:     BLIT_TRAMPOLINE scroll_page_to_screen_p04_asm
.Lblit_p05:     BLIT_TRAMPOLINE scroll_page_to_screen_p05_asm
.Lblit_p06:     BLIT_TRAMPOLINE scroll_page_to_screen_p06_asm
.Lblit_p07:     BLIT_TRAMPOLINE scroll_page_to_screen_p07_asm
.Lblit_p08:     BLIT_TRAMPOLINE scroll_page_to_screen_p08_asm
.Lblit_p09:     BLIT_TRAMPOLINE scroll_page_to_screen_p09_asm
.Lblit_p10:     BLIT_TRAMPOLINE scroll_page_to_screen_p10_asm
.Lblit_p11:     BLIT_TRAMPOLINE scroll_page_to_screen_p11_asm
.Lblit_p12:     BLIT_TRAMPOLINE scroll_page_to_screen_p12_asm
.Lblit_p13:     BLIT_TRAMPOLINE scroll_page_to_screen_p13_asm
.Lblit_p14:     BLIT_TRAMPOLINE scroll_page_to_screen_p14_asm
.Lblit_p15:     BLIT_TRAMPOLINE scroll_page_to_screen_p15_asm
.Lblit_p16:     BLIT_TRAMPOLINE scroll_page_to_screen_p16_asm
.Lblit_p17:     BLIT_TRAMPOLINE scroll_page_to_screen_p17_asm
.Lblit_p18:     BLIT_TRAMPOLINE scroll_page_to_screen_p18_asm
.Lblit_p19:     BLIT_TRAMPOLINE scroll_page_to_screen_p19_asm

        .align  2
.Lscroll_blit_table:
        .long   .Lblit_p00, .Lblit_p01, .Lblit_p02, .Lblit_p03, .Lblit_p04
        .long   .Lblit_p05, .Lblit_p06, .Lblit_p07, .Lblit_p08, .Lblit_p09
        .long   .Lblit_p10, .Lblit_p11, .Lblit_p12, .Lblit_p13, .Lblit_p14
        .long   .Lblit_p15, .Lblit_p16, .Lblit_p17, .Lblit_p18, .Lblit_p19
| The index at 0x111b6 is `and.l #$ff` then `lsl.l #2` with no bound, exactly as the original's is.
| What keeps it inside the table is that A_map_column has two writers and both wrap it at
| SCROLL_PHASES (../frame.c says which two), so the table has to be exactly that long.
        .if     (. - .Lscroll_blit_table) != (SCROLL_PHASES * 4)
        .error  "the page-blit table is not SCROLL_PHASES entries long"
        .endif

#ifdef ZY_ASM_FRAME_HEAD_DOOR
| THE LAST FOUR ARE OFF-TARGET ONLY. On target the body spins on the scancode with the original's own
| instructions (band 2 says why), and the target's own sched.h supplies only a `static inline` with
| no linkable symbol — so these stubs would not even link there.
|
| ---- int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc) ----
| THE ANSWER IS DELIVERED IN %d0 (0 = the poll cap was exhausted), which band 2 branches on, so
| neither wait stub restores %d0.
        .globl  door_sched_wait_pause_release
door_sched_wait_pause_release:
        movem.l %d1/%a0-%a1,-(%sp)
        pea     PAUSE_RELEASE_WAIT_PC
        pea     PAUSE_KEY_RELEASED
        pea     A_key_scancode
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sched_wait8, sched_wait8)
        lea     16(%sp),%sp
        movem.l (%sp)+,%d1/%a0-%a1
        rts

        .globl  door_sched_wait_pause_second_release
door_sched_wait_pause_second_release:
        movem.l %d1/%a0-%a1,-(%sp)
        pea     PAUSE_SECOND_RELEASE_WAIT_PC
        pea     PAUSE_KEY_RELEASED
        pea     A_key_scancode
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sched_wait8, sched_wait8)
        lea     16(%sp),%sp
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- uint8_t sched_poll8(uint8_t *image, uint32_t addr, uint32_t site_pc) ----
| ONE POLL of the middle spin, whose body band 2 has to spell out. The byte comes back in %d0 and
| band 2 compares it as a BYTE, so whatever the host left in the other three does not matter.
        .globl  door_sched_poll_pause_press
door_sched_poll_pause_press:
        movem.l %d1/%a0-%a1,-(%sp)
        pea     PAUSE_PRESS_WAIT_PC
        pea     A_key_scancode
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sched_poll8, sched_poll8)
        lea     12(%sp),%sp
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- int32_t os_refused(int32_t sentinel) ---- TAKES NO IMAGE POINTER, and its answer is discarded
        .globl  door_os_refused
door_os_refused:
        SCRATCH_SAVE
        clr.l   -(%sp)                          | the sentinel ../frame.c passes
        ZY_CALL(ZY_DOOR_os_refused, os_refused)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts
#endif
