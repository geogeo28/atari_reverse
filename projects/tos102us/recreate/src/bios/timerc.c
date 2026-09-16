/* The MFP TIMER C handler — vector $114, $fc30c4. Two hundred times a second, which makes it the
 * most-executed routine in the ROM and the one whose cost is a fact about the whole machine.
 *
 *      addq.l  #1,_hz_200          ; every tick, before anything can divide it away
 *      rol.w   $0e88               ; ...and a one-bit rotate of a four-bit pattern
 *      bpl.s   .acknowledge        ; ...so the body below runs on one tick in four: 50 Hz
 *      movem.l d0-a6,-(sp)
 *      lea     0,a5
 *      bsr.s   $fc312a             ; the Dosound driver, one step
 *      <the keyboard's auto-repeat>
 *      move.w  timr_ms,-(sp)
 *      movea.l etv_timer,a0
 *      jsr     (a0)                ; ...the OS tick vector, with the calibration pushed
 *      addq.w  #2,sp
 *      movem.l (sp)+,d0-a6
 * .acknowledge:
 *      bclr    #5,$fffa11          ; the MFP's in-service bit for channel 5
 *      rte
 *
 * THE ACKNOWLEDGEMENT GOES THROUGH `mfp.h`'s DECLARED-MAP read-modify-write rather than `hw.h`'s
 * `hw_bclr8`, and that header carries the argument: $fffa11's other seven bits are seven other
 * channels' in-service flags, and a door whose read half is a fabricated 0 can pin the address and
 * the fact of the store but not the bits the instruction PRESERVES. A case declares what the
 * register held and both sides read it.
 *
 * THE DIVIDER IS A ROTATE, NOT A COUNTER, and that is the whole of why it works: $4444 through
 * $8888, $1111, $2222 and back is a four-state cycle with exactly one negative state, so the body
 * runs on one tick in four and the pattern never needs comparing against anything. A reconstruction
 * that counted to four would agree for as long as the word held one of those four values and
 * diverge the moment a case staged any other — there are 65,532 of them.
 *
 * THE TICK COUNT AND THE ACKNOWLEDGEMENT ARE ON BOTH PATHS. `_hz_200` is bumped before the divider
 * is even rotated, and the MFP's in-service bit is cleared after the two paths meet — so a tick that
 * does no work still counts and still acknowledges, which is what keeps channel 5 firing.
 *
 * WHAT IS NOT RECONSTRUCTED HERE (`recreate.h`): the auto-repeat INJECTION at $fc2c42, which is
 * where a key that has waited out both countdowns goes. That routine translates a scancode through
 * the `Keytbl` tables and writes the IKBD's own IOREC — it is the keyboard half of the ACIA
 * handler's world rather than the timer's, and it belongs with the packet parser. Everything up to
 * it is here: the `conterm` gate, the "is a key held" gate, and both countdowns including the
 * reload from `Kbrate`'s interval byte.
 */
#include <stdint.h>

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif

#include "machine.h"
#include "recreate.h"
#include "m68k_idioms.h"
#include "hw.h"
#include "psg.h"
#include "addrs.h"
#include "mfp.h"
#include "staged_call.h"

/* ---- the Dosound driver's one step ($fc312a) ---------------------------------------------------
 * A byte-coded list: anything under $80 is a YM2149 REGISTER NUMBER followed by the byte to put in
 * it, and $80 and above are the three commands. The driver runs bytes until it hits a command that
 * ends the tick — a ramp, or a pause — so one tick can write any number of registers.
 */

/* Register 7 is the mixer, and the driver READ-MODIFY-WRITES it: the list supplies the six
 * tone/noise enables and the chip's own two I/O-direction bits are kept. Every other register is
 * written outright. */
static void write_one_register(uint8_t reg, uint8_t value)
{
    if (reg == PSG_MIXER_REGISTER)
        value = (uint8_t)((psg_port_read(PSG_MIXER_REGISTER) & PSG_MIXER_PORT_MASK)
                          | (value & PSG_MIXER_CHANNEL_MASK));
    psg_port_write(reg, value);
}

/* `move.b (a0)+,d0` — one byte of the list, with the cursor advanced the 68000's way. */
static uint8_t next_byte(const uint8_t *image, uint32_t *cursor)
{
    uint8_t byte;

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, the way the kit prescribes: the list pointer is whatever XBIOS `Dosound` was
     * handed, so a caller that pointed it outside RAM would walk off the image here where the
     * original walks its own address space. */
    assert(*cursor < ST_RAM_BYTES);
#endif
    byte = image[*cursor];
    *cursor = addr_add(*cursor, 1);
    return byte;
}

/* Command $81: step the accumulator towards an end value and write it to a register, one step a
 * tick. The cursor is wound back over the WHOLE command when the end has not been reached, so the
 * next tick runs the identical four bytes again. */
static uint32_t step_the_ramp(uint8_t *image, uint32_t cursor)
{
    uint8_t reg = next_byte(image, &cursor);
    uint8_t step = next_byte(image, &cursor);
    uint8_t end;

    image[SOUND_RAMP_VALUE] = (uint8_t)(image[SOUND_RAMP_VALUE] + step);
    end = next_byte(image, &cursor);
    /* The ROM SELECTS the register before it reads the step and writes the data port after it has
     * read the end value; `psg_port_write` does both at once. The select is not a ledger entry on
     * either side (only the data access is), so the two are the same ordered chip traffic. */
    psg_port_write(reg, image[SOUND_RAMP_VALUE]);
    if (end == image[SOUND_RAMP_VALUE])
        return cursor;
    /* `subq.w #4,a0` — on an ADDRESS register that is a full 32-bit subtract whatever the size
     * suffix says, so the wind-back wraps exactly as `addr_add` does. */
    return addr_add(cursor, (uint32_t)-(int32_t)DOSOUND_RAMP_OPERANDS);
}

/* Commands $82..$ff: the next byte is how many ticks to wait before looking at the list again, and
 * a wait of ZERO ends the list outright — `movea.w #0,a0`, so the cursor stored below is 0 and the
 * next tick returns at once. */
static uint32_t set_the_wait(uint8_t *image, uint32_t cursor)
{
    image[SOUND_LIST_DELAY] = next_byte(image, &cursor);
    return image[SOUND_LIST_DELAY] == 0 ? 0 : cursor;
}

static void step_the_sound_driver(uint8_t *image)
{
    uint32_t cursor = be32(image + SOUND_LIST_POINTER);
    uint8_t waiting;

    if (cursor == 0)
        return;                                     /* nothing is playing */
    waiting = image[SOUND_LIST_DELAY];
    if (waiting != 0) {
        image[SOUND_LIST_DELAY] = (uint8_t)(waiting - 1);
        return;                                     /* ...still inside a pause */
    }
    for (;;) {
        /* `move.b (a0)+,d0 / bmi` picks the commands out, and the ROM then tells the two it names
         * apart with `addq.b #1,d0 / bpl` and two compares on the BUMPED byte — which is the same
         * function as the three tests below: $80 and $81 are the two commands, and everything else
         * from $82 to $ff (the $ff the `bpl` catches included) is a wait. */
        uint8_t command = next_byte(image, &cursor);

        if (command < DOSOUND_COMMAND_FLOOR) {
            write_one_register(command, next_byte(image, &cursor));
            continue;
        }
        if (command == DOSOUND_LOAD_TEMP) {
            image[SOUND_RAMP_VALUE] = next_byte(image, &cursor);
            continue;
        }
        cursor = command == DOSOUND_RAMP ? step_the_ramp(image, cursor)
                                         : set_the_wait(image, cursor);
        break;
    }
    wr32(image + SOUND_LIST_POINTER, cursor);
}

/* ---- the keyboard's auto-repeat ---------------------------------------------------------------- */

/* Two countdowns behind two gates: `conterm` bit 1 turns repeating off altogether, and a zero
 * scancode means no key is being held. The delay counts the wait before the FIRST repeat and the
 * interval counts between them, so the delay is only decremented while it is non-zero and the
 * interval is reloaded from `Kbrate`'s byte every time it runs out. */
static void step_the_key_repeat(uint8_t *image)
{
    if (!(image[SYSVAR_CONTERM] & (1u << CONTERM_REPEAT_BIT)))
        return;
    if (image[SYSVAR_KB_REPEAT_KEY] == 0)
        return;
    if (image[SYSVAR_KB_REPEAT_DELAY] != 0) {
        image[SYSVAR_KB_REPEAT_DELAY] = (uint8_t)(image[SYSVAR_KB_REPEAT_DELAY] - 1);
        if (image[SYSVAR_KB_REPEAT_DELAY] != 0)
            return;
    }
    image[SYSVAR_KB_REPEAT_LEFT] = (uint8_t)(image[SYSVAR_KB_REPEAT_LEFT] - 1);
    if (image[SYSVAR_KB_REPEAT_LEFT] != 0)
        return;
    image[SYSVAR_KB_REPEAT_LEFT] = image[KBRATE_REPEAT];
    recreate_not_reconstructed(
        "the auto-repeat injection at $fc2c42 — it translates the held scancode through the Keytbl "
        "tables into the IKBD's IOREC, which is the keyboard half of the ACIA handler's world");
}

/* ---- the handler ------------------------------------------------------------------------------- */

/* `rol.w <ea>` — a memory rotate by ONE, which the 68000 spells without a count operand. The WORD
 * form of `machine.h`'s rotate, not the longword one: the word's own bit 15 comes back in at bit 0,
 * where rotating the longword this word sits inside would carry a neighbouring byte's bit into it. */
#define TIMER_C_DIVIDER_ROTATE 1

/* Declared here rather than in a header because `src/bios/isr.S` is its only other caller and an
 * assembler reads no prototype: this says the symbol is deliberately exported, and to whom. */
void service_this_timer_c_tick(uint8_t *image);

/* The SERVICED tick — the one in four the divider lets through, which is what the ROM saves the
 * register file across. EXPORTED for `service_this_vertical_blank`'s reason: `src/bios/isr.S` is
 * the handler a shipped ROM installs in vector $114, and the tick count, the divider and the
 * acknowledgement around this are the handler rather than the body. */
void service_this_timer_c_tick(uint8_t *image)
{
    step_the_sound_driver(image);
    step_the_key_repeat(image);
    call_vector_word(image, be32(image + SYSVAR_ETV_TIMER), be16(image + SYSVAR_TIMR_MS));
}

void isr_timer_c(uint8_t *image)
{
    uint16_t divider;

    wr32(image + SYSVAR_HZ_200, be32(image + SYSVAR_HZ_200) + 1);
    divider = rotate_left16(be16(image + SYSVAR_TIMER_C_DIVIDER), TIMER_C_DIVIDER_ROTATE);
    wr16(image + SYSVAR_TIMER_C_DIVIDER, divider);
    if (divider & SIGN_BIT16)
        service_this_timer_c_tick(image);
    mfp_clear_bit(MFP_ISRB, MFP_ISRB_TIMER_C_BIT);
}
