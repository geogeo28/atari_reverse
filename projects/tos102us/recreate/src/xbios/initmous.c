/* XBIOS Initmous ($00) — $fc2f28.
 *
 * Puts the IKBD's mouse into one of four reporting modes and installs the handler its packets are
 * delivered to. The routine builds the whole IKBD command packet in a RAM buffer and then hands it
 * to `Ikbdws`'s own loop; only the disable mode is a single byte sent directly.
 *
 *      tst.w   4(sp)                       ; mode
 *      beq.s   .disable
 *      move.l  10(sp),$e22       ; a5 = 0: KBDVECS + $10, `mousevec`
 *      movea.l 6(sp),a3          ; the parameter block
 *      cmpi.w  #1,4(sp) / beq .relative
 *      cmpi.w  #2,4(sp) / beq .absolute
 *      cmpi.w  #4,4(sp) / beq .keycode
 *      moveq   #0,d0             ; ...and any other mode is refused, vector already stored
 *      rts
 *  .disable:  moveq #$12,d1 / bsr $fc21f2 / move.l #$fc3028,$e22 / bra .done
 *  .relative: lea $e6e,a2 / move.b #8,(a2)+ / move.b #11,(a2)+ / bsr .common
 *             moveq #6,d3  / lea $e6e,a2 / bsr $fc221c / bra .done
 *  .absolute: lea $e6e,a2 / move.b #9,(a2)+ / move.b 4(a3),(a2)+ ... 7(a3)
 *             move.b #12,(a2)+ / bsr .common
 *             move.b #14,(a2)+ / move.b #0,(a2)+ / move.b 8(a3),(a2)+ ... 11(a3)
 *             moveq #16,d3 / lea $e6e,a2 / bsr $fc221c / bra .done
 *  .keycode:  lea $e6e,a2 / move.b #10,(a2)+ / bsr .common
 *             moveq #5,d3  / lea $e6e,a2 / bsr $fc221c
 *  .done:     moveq #-1,d0 / rts
 *  .common ($fc2fd8): move.b 2(a3),(a2)+ / move.b 3(a3),(a2)+
 *             moveq #16,d1 / sub.b (a3),d1 / move.b d1,(a2)+
 *             move.b #7,(a2)+ / move.b 1(a3),(a2)+ / rts
 *
 * This one FAILS TO DECOMPILE — it is on `COMPONENTS.md`'s list of 73, for the Alcyon write-to-`(sp)`
 * idiom — so it is reconstructed from the disassembly above, like `Setexc` before it.
 *
 * THE VECTOR IS STORED BEFORE THE MODE IS KNOWN TO BE VALID, which is not a transcription slip: mode
 * 3 and mode 5 store the caller's handler into `mousevec` and then return 0 having sent nothing, so
 * a caller that checks the result still has its handler installed. Only mode 0 overrides it, with
 * the ROM's own `rts` at `$fc3028` — that is what "no mouse" means here, a handler that discards the
 * packet rather than a null pointer nothing checks.
 *
 * `16 - topmode` IS A BYTE SUBTRACT (`moveq #16,d1` / `sub.b (a3),d1`), so a `topmode` of $20 sends
 * $f0 rather than a negative number, and the ROM does not bound it. The parameter block's fields are
 * bytes and pairs of bytes in the caller's own memory, copied one at a time in the ROM's order —
 * which is the order the 6301 expects its arguments in, so the ledger of sent bytes is the whole of
 * what a case can compare. There is no image byte to check it against: the packet is built in RAM
 * (that IS compared) and then sent (that is the hardware WRITE ledger, compared entry by entry).
 */
#include <stdint.h>

#include "xbios/ikbd.h"
#include "machine.h"
#include "addrs.h"

/* The five bytes every reporting mode ends with: the two mode parameters, the Y origin, and a
 * "set mouse button action" command with its own byte. `$fc2fd8`, which three arms `bsr`. */
static uint32_t mouse_common_parameters(uint8_t *image, uint32_t at, uint32_t param)
{
    image[addr_add(at, 0)] = image[addr_add(param, MOUSE_PARAM_XPARAM)];
    image[addr_add(at, 1)] = image[addr_add(param, MOUSE_PARAM_YPARAM)];
    /* `sub.b`, so this wraps inside a byte exactly as the ROM's does. */
    image[addr_add(at, 2)] = (uint8_t)(MOUSE_TOPMODE_ORIGIN
                                       - image[addr_add(param, MOUSE_PARAM_TOPMODE)]);
    image[addr_add(at, 3)] = IKBD_SET_BUTTON_ACTION;
    image[addr_add(at, 4)] = image[addr_add(param, MOUSE_PARAM_BUTTONS)];
    return at + MOUSE_COMMON_BYTES;
}

/* `move.b n(a3),(a2)+` repeated over a pair of bytes — the packet's big-endian coordinates. */
static uint32_t mouse_copy_pair(uint8_t *image, uint32_t at, uint32_t param, uint32_t field)
{
    image[addr_add(at, 0)] = image[addr_add(param, field)];
    image[addr_add(at, 1)] = image[addr_add(param, field + 1)];
    return at + MOUSE_PARAM_PAIR_BYTES;
}

uint32_t xbios_initmous(uint8_t *image, uint16_t mode, uint32_t param, uint32_t vector)
{
    uint32_t at = INITMOUS_PACKET;
    uint16_t count;

    if (mode == INITMOUS_DISABLE) {
        ikbd_send_byte(IKBD_DISABLE_MOUSE);
        wr32(image + KBDVECS + KBDVECS_MOUSEVEC, MOUSE_DISCARD_HANDLER);
        return INITMOUS_DONE;
    }

    wr32(image + KBDVECS + KBDVECS_MOUSEVEC, vector);

    switch (mode) {
    case INITMOUS_RELATIVE:
        image[at++] = IKBD_SET_RELATIVE_MOUSE;
        image[at++] = IKBD_SET_MOUSE_THRESHOLD;
        at = mouse_common_parameters(image, at, param);
        count = INITMOUS_RELATIVE_COUNT;
        break;

    case INITMOUS_ABSOLUTE:
        image[at++] = IKBD_SET_ABSOLUTE_MOUSE;
        at = mouse_copy_pair(image, at, param, MOUSE_PARAM_XMAX);
        at = mouse_copy_pair(image, at, param, MOUSE_PARAM_YMAX);
        image[at++] = IKBD_SET_MOUSE_SCALE;
        at = mouse_common_parameters(image, at, param);
        image[at++] = IKBD_SET_MOUSE_POSITION;
        image[at++] = MOUSE_POSITION_FILLER;
        at = mouse_copy_pair(image, at, param, MOUSE_PARAM_XINITIAL);
        at = mouse_copy_pair(image, at, param, MOUSE_PARAM_YINITIAL);
        count = INITMOUS_ABSOLUTE_COUNT;
        break;

    case INITMOUS_KEYCODE:
        image[at++] = IKBD_SET_KEYCODE_MOUSE;
        at = mouse_common_parameters(image, at, param);
        count = INITMOUS_KEYCODE_COUNT;
        break;

    default:
        return INITMOUS_UNKNOWN_MODE;       /* the handler above is installed all the same */
    }

    ikbd_send_string(image, count, INITMOUS_PACKET);
    return INITMOUS_DONE;
}
