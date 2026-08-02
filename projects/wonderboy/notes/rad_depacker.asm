; ============================================================================
; The .RAD / .CRU resource cruncher's depack routine — faithful transcription
;
; Source   : projects/wonderboy/bin/disk1/AUTO/SWB.PRG
; Extent   : text $596a .. $5a40 (216 bytes of code: $5a42 - $596a) + the
;            scratch long at $5a42
;            (file offsets $5986 .. $5a5c; text = file - $1c)
; Runtime  : $5d62 .. $5e38, scratch long $5e3a.  SWB.PRG's text is NOT
;            position-independent: the entry stub at text $213e0 does
;              move.l #text_end,-(a7) / move.w #$20,-(a7) / trap #1   ; Super()
;              move   #$2700,sr
;              lea $400.l,a1 / lea $8.l,a0 / move.l #$84f6,d0
;            .lp move.l (a0)+,(a1)+ / subq.l #1,d0 / bne .lp
;              jmp $400.l
;            i.e. it copies text $8.. down to absolute $400 and jumps there, so
;            every absolute operand in the body (this routine's $5e3a included)
;            reads as `text offset + $3f8`. Addresses in the left column below
;            are the RUNTIME addresses, so they match the operands as written.
; Reimpl.  : tools/depack_rad.py   (bit-exact; 41/41 intact streams diff clean
;                                   vs this code under Musashi, plus 4 damaged
;                                   ones both sides refuse —
;                                   projects/wonderboy/notes/rad_differential.py)
;
; Entry     a0 = the file as read off disk (header included)
;           a1 = destination
; Exit      the destination holds `unpacked length` bytes.
;           d0 = $ffffffff and a7 NOT restored  if the checksum failed —
;           `moveq #$ff,d0` SIGN-EXTENDS, so the status is the whole longword,
;           not a byte; on success d0 is only the spent bit buffer, not a
;           status word.  d0-d5/a0-a2 trashed.
; Callers   five, all of the shape
;             lea <load buffer>,a0 / lea <destination>,a1 / jsr $5d62.w
;           at runtime $e4c6, $e536, $e57e, $e644, $e67a.
;
; Container (no magic; the game reaches these files only via its own file index
;            table at runtime $2143e, 40 entries x 16 bytes)
;   +0   be32  packed length = filesize - 12  ; only used to walk a0 to EOF
;   +4   be32  unpacked length
;   +8   be32  checksum: XOR of every longword of the stream
;   +12  packed stream, consumed BACKWARDS from EOF down to +12
;
; Register roles
;   a0  stream pointer, moves DOWN a longword at a time.
;   a1  destination base; only ever compared against, never written through.
;   a2  write pointer, moves DOWN from dest+unpacked length to dest.
;   d0  bit buffer (longword). Bits leave LSB-first; the buffer is spent when
;       the shifted-out remainder is 0, so each longword's HIGHEST SET BIT is
;       its end marker. The refill sets X and roxr's a fresh 1 into bit 31 as
;       the next marker, which is why every refilled longword yields a full 32
;       data bits. The seed longword carries no injected marker, so its own top
;       set bit ends it.
;   d1  bit count for the getbits helper / offset width
;   d2  decoded field (literal byte, count, offset)
;   d3  copy counter, always LENGTH-1 (a plain dbf follows)
;   d4  literal-run base bias (0 or 8)
;   d5  running checksum; must be 0 when the stream is exhausted.
;
; $5e3a  parks the entry a7 so the success path can restore it.
;        Nothing else outside [dest, dest+unpacked) is written — no palette,
;        no PSG, no disk. The whole effect of this routine is diffable.
; ============================================================================

; ---- entry ---------------------------------------------------------------
005d62: 23cf 00005e3a    move.l  a7,$5e3a.l            ; park the stack pointer
005d68: 2018             move.l  (a0)+,d0              ; d0 = packed length
005d6a: 2218             move.l  (a0)+,d1              ; d1 = unpacked length
005d6c: 2a18             move.l  (a0)+,d5              ; d5 = checksum seed
005d6e: 2449             movea.l a1,a2                 ; a0 now = file+12 = stream start
005d70: d1c0             adda.l  d0,a0                 ; a0 = file+12+packed = EOF
005d72: d5c1             adda.l  d1,a2                 ; a2 = dest + unpacked (fill downwards)
005d74: 2020             move.l  -(a0),d0              ; seed the bit buffer (no marker injected:
005d76: b185             eor.l   d0,d5                 ; this longword's own top set bit is it)

; ---- main loop: one token per pass ---------------------------------------
005d78: e288        L_TOP:  lsr.l   #1,d0               ; getbit
005d7a: 6604             bne.s   $5d80
005d7c: 6100 0096        bsr.w   REFILL
005d80: 653a             bcs.s   L_SEL                 ; 1 -> a 2-bit selector follows

; ---- "0x": literal run, or the shortest match ----------------------------
005d82: 7208             moveq   #8,d1                 ; pre-set: 8 offset bits ...
005d84: 7601             moveq   #1,d3                 ; ... and length 2 (d3 = length-1)
005d86: e288             lsr.l   #1,d0                 ; getbit
005d88: 6604             bne.s   $5d8e
005d8a: 6100 0088        bsr.w   REFILL
005d8e: 6558             bcs.s   L_OFFSET              ; "01" -> match, length 2, 8-bit offset
005d90: 7203             moveq   #3,d1                 ; "00" -> literal run, 3-bit count ...
005d92: 4244             clr.w   d4                    ; ... biased by 0  -> 1..8 bytes

; ---- literal run: d3+1 bytes, 8 stream bits each -------------------------
005d94: 6100 008a    L_LIT:  bsr.w   GETBITS           ; d2 = the count field
005d98: 3602             move.w  d2,d3
005d9a: d644             add.w   d4,d3                 ; d3 = count-1 (the dbf copies d3+1)
005d9c: 7207        L_LIT_BYTE: moveq #7,d1            ; 8 bits, inline (not via GETBITS)
005d9e: e288        L_LIT_BIT:  lsr.l #1,d0            ; getbit
005da0: 6604             bne.s   $5da6
005da2: 6100 0070        bsr.w   REFILL
005da6: e392             roxl.l  #1,d2                 ; d2 = (d2 << 1) | bit
005da8: 51c9 fff4        dbf     d1,L_LIT_BIT
005dac: 1502             move.b  d2,-(a2)              ; the literal byte
005dae: 51cb ffec        dbf     d3,L_LIT_BYTE
005db2: 6000 0042        bra.w   L_MORE

; ---- selector 3: the long literal run ------------------------------------
005db6: 7208        L_LIT_LONG: moveq #8,d1            ; 8-bit count ...
005db8: 7808             moveq   #8,d4                 ; ... biased by 8  -> 9..264 bytes
005dba: 60d8             bra.s   L_LIT

; ---- "1x": a 2-bit selector ----------------------------------------------
005dbc: 7202        L_SEL:  moveq   #2,d1
005dbe: 6100 0060        bsr.w   GETBITS               ; d2 = selector
005dc2: b43c 0002        cmp.b   #2,d2
005dc6: 6d16             blt.s   L_SHORT               ; 0,1 -> fixed-length match
005dc8: b43c 0003        cmp.b   #3,d2
005dcc: 67e8             beq.s   L_LIT_LONG            ; 3   -> long literal run
                                                       ; 2   -> long match:
005dce: 7208             moveq   #8,d1
005dd0: 6100 004e        bsr.w   GETBITS               ; 8-bit length field
005dd4: 3602             move.w  d2,d3                 ; d3 = length-1  -> 1..256 bytes
005dd6: 323c 000c        move.w  #12,d1                ; 12 offset bits -> 0..4095
005dda: 6000 000c        bra.w   L_OFFSET

; ---- selectors 0 and 1: length 3 with 9 offset bits, length 4 with 10 ----
005dde: 323c 0009    L_SHORT: move.w #9,d1
005de2: d242             add.w   d2,d1                 ; 9 or 10 offset bits
005de4: 5442             addq.w  #2,d2
005de6: 3602             move.w  d2,d3                 ; d3 = 2 or 3 -> length 3 or 4

; ---- copy the match ------------------------------------------------------
005de8: 6100 0036    L_OFFSET: bsr.w GETBITS           ; d2 = offset
005dec: 534a        L_COPY: subq.w  #1,a2
005dee: 14b2 2000        move.b  0(a2,d2.w),(a2)       ; source is ABOVE the write pointer, i.e.
005df2: 51cb fff8        dbf     d3,L_COPY             ; already-written output. One byte at a
                                                       ; time, so offset < length repeats a run.

; ---- done? ---------------------------------------------------------------
005df6: b3ca        L_MORE: cmpa.l a2,a1
005df8: 6d00 ff7e        blt.w   L_TOP                 ; keep going while dest < write pointer
005dfc: 4a85             tst.l   d5                    ; every longword XORed back out?
005dfe: 6608             bne.s   L_BAD
005e00: 2e79 00005e3a    movea.l $5e3a.l,a7
005e06: 4e75             rts

; ---- checksum failure: stall, then report --------------------------------
005e08: 303c ffff    L_BAD:  move.w #$ffff,d0
005e0c: 51c8 fffe        dbf     d0,$5e0c              ; ~65536-iteration delay
005e10: 70ff             moveq   #$ff,d0               ; the one defined status value: moveq
                                                       ; sign-extends, so d0 = $ffffffff
005e12: 4e75             rts                           ; note: a7 is NOT restored here

; ---- refill the bit buffer, returning the first bit in C -----------------
005e14: 2020        REFILL: move.l -(a0),d0
005e16: b185             eor.l   d0,d5                 ; checksum every longword read
005e18: 44fc 0010        move    #$10,ccr              ; X = 1: the next end-of-longword marker
005e1c: e290             roxr.l  #1,d0                 ; C = bit 0 (the data bit), marker -> bit 31
005e1e: 4e75             rts

; ---- read d1 bits into d2, MSB first -------------------------------------
005e20: 5341        GETBITS: subq.w #1,d1
005e22: 4242             clr.w   d2                    ; only the LOW WORD; d1 <= 16 keeps the
005e24: e288        L_GB:   lsr.l   #1,d0               ; old high word out of the result
005e26: 660a             bne.s   $5e32
005e28: 2020             move.l  -(a0),d0              ; REFILL, inlined
005e2a: b185             eor.l   d0,d5
005e2c: 44fc 0010        move    #$10,ccr
005e30: e290             roxr.l  #1,d0
005e32: e392             roxl.l  #1,d2
005e34: 51c9 ffee        dbf     d1,L_GB
005e38: 4e75             rts

005e3a: 0000 0000    SAVED_A7: dc.l 0

; ============================================================================
; NOT this routine: SPRITES .CRU
;
; SPRITES.CRU carries the same two leading length longs, but they are EQUAL
; (both $441ba = filesize - 64), i.e. the container's stored form. The game
; never hands it to this routine: the loader reads it to $25298 and the sprite
; setup at runtime $e87c indexes its body at $252d8 = load address + 64. So its
; header is 64 bytes and the remaining 278,970 bytes are verbatim sprite data.
;
; The 64-byte header is not all length fields: its last 32 bytes, +$20..+$3f,
; are a 16-entry ST PALETTE — every word <= $777 with bit 3 of each nibble
; clear, entry 0 black, then $333 $555 $777 $600 $754 ... The BODY at +$40 is
; not (it holds words like $25a8), so the palette lives in the header, ahead of
; the sprite data, not at the start of the body. Fields +$8..+$1f are
; $01e10000 followed by zeros and are not yet identified.
; See docs/binary-formats.md.
;
; NOT this routine either: the "LSD!" cruncher of notes/lsd_depacker.asm. That
; is a CRACKED release's packer, not the game's: on the original disks every
; .RAD/.CRU carries this container and nothing else (no file on either disk
; starts with the 'LSD!' magic), and SWB.PRG itself is plain, unpacked code.
; The two are easy to confuse because both wrap a backwards-consumed stream in
; a 12-byte header; the tells are the magic, the longword-at-a-time refill, and
; this one's checksum long.
; ============================================================================
