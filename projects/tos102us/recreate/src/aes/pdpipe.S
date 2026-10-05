/* pdpipe.S — gemdosif's two leaves under pstart as the ROM spells them: uda_insuper and psetup — the TRANSCRIPTIONS a
 * target build ships, where `pdpipe.c` is what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Both are hand 68000 over their caller's Alcyon frame, and each C port measures over
 * Tier 3's 1.10 bar: uda_insuper is three instructions (its C 1.50: the image pointer's load and add are half as much
 * again), psetup twelve (its C 1.24, the same floor on four accesses) — so by the user's rule the target carries the
 * ROM's own instructions (`include/transcribed.h`). Neither executes a Line-F word.
 *
 * ONE PINNED REGION, $fe3970..$fe39a5, the two routines as the ROM lays them out
 * (`test/test_aes_pdpipe_transcription.py` pins every byte).
 *
 * psetup IS SUPERVISOR CODE: it parks the status register in its own save word and masks every interrupt round its
 * stores (`aes/switch.h`). REGISTERS, as the ROM leaves them: uda_insuper changes A1; psetup D0, A0, A1 and A2 — A2
 * the GCC ABI's callee-saved, which the table's row says.
 */
#include "addrs.h"
#include "aes/aes.h"
#include "aes/pdpipe.h"

    .text

/* ---- uda_insuper, $fe3970: (uda) -> its in-supervisor word set ------------------------------------------------- */
    .globl  aes_rom_uda_insuper
aes_rom_uda_insuper:
    movea.l 4(%sp),%a1
    move.w  #UDA_INSIDE_THE_AES,(%a1)
    rts
#if UDA_IN_SUPER != 0
#error "uda_insuper stores through (a1) itself: the mark is the UDA's first word"
#endif

/* ---- psetup, $fe397a: (pd, pc) -> an rte frame pushed on the stack pd's UDA saved, under IPL 7 ------------------- */
    .globl  aes_rom_psetup
aes_rom_psetup:
    move.w  %sr,AES_SR_PSETUP
    ori.w   #SR_IPL_MASK,%sr
    movea.l 4(%sp),%a0
    move.l  8(%sp),%d0
    movea.l PD_UDA(%a0),%a1
    movea.l UDA_SUPER_SP(%a1),%a2
    move.l  %d0,-(%a2)
    move.w  #SR_SUPERVISOR,-(%a2)
    move.l  %a2,UDA_SUPER_SP(%a1)
    move.w  AES_SR_PSETUP,%sr
    rts
