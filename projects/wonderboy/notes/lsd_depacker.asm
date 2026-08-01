; ============================================================================
; The "LSD!" cruncher's depack routine — faithful transcription
;
; Source   : projects/wonderboy/bin/extracted/AUTO/VAPOUR2.PRG
; Extent   : text $7e6 .. $94a  (file offsets $802 .. $966; text = file - $1c)
; Reimpl.  : tools/depack_lsd.py       (bit-exact; 96/96 files diff clean vs this code
;                                       under Musashi — projects/wonderboy/notes/lsd_differential.py.
;                                       That diff covers the DEPACKED BYTES only: the $ffff8240
;                                       colour flash below is off-image and unverified.)
;
; Entry     a0 = packed file + 4   (just past the 'LSD!' magic)
;           a1 = destination
; Exit      the destination holds `unpacked size` bytes; d0-d5/a0-a3 trashed.
;
; Container
;   +0   'LSD!'
;   +4   be32  unpacked size
;   +8   be32  filesize - 4     ; only used to walk a0 to EOF (see $7f8)
;   +12  packed stream, consumed BACKWARDS from EOF down to +12
;
; Register roles
;   a0  stream pointer, moves DOWN. Bit refills and literal bytes share it.
;   a1  destination pointer, moves DOWN from dest+unpacked_size to dest.
;   a2  match source pointer (scratch)
;   a3  table base (scratch) / end-of-stream limit
;   d0  bit buffer (byte). Bits leave MSB-first; the buffer is spent when the
;       shifted-out remainder is 0, so each byte's LOWEST SET BIT is its end
;       marker. The refill's roxl rotates that marker back in as the new byte's
;       marker, which is why every refilled byte yields a full 8 data bits.
;   d1  decoded literal count / match length
;   d2  bit-count scratch / match offset
;   d3  table index (tier) / bit-count scratch
;   d4  all-ones escape mask / offset bias
;   d5  unpacked size
;
; $90.w        parks the entry a0, so the loop can test "stream exhausted".
; $ffff8240.w  is saved on entry, poked with stream bytes during literal runs
;              (a loading-progress colour flash) and restored before rts.
; ============================================================================

; ---- alternate entry: callers holding a0 = file (not file+4) --------------
0007e6: d1fc 00000004    adda.l  #4,a0                 ; skip the 'LSD!' magic
; ---- entry ---------------------------------------------------------------
0007ec: 3f38 8240        move.w  $ffff8240.w,-(a7)     ; save palette entry 0
0007f0: 21c8 0090        move.l  a0,$90.w              ; remember file+4
0007f4: 2a18             move.l  (a0)+,d5              ; d5 = unpacked size
0007f6: d3c5             adda.l  d5,a1                 ; a1 = dest + unpacked size (fill downwards)
0007f8: d1d0             adda.l  (a0),a0               ; a0 = (file+8) + (filesize-4)
0007fa: 91fc 00000004    suba.l  #4,a0                 ; a0 = file + filesize   (EOF)
000800: 4a60             tst.w   -(a0)                 ; last word: $8000 or $0000 in every file seen
000802: 6a02             bpl.s   $806
000804: 5388             subq.l  #1,a0                 ; negative -> skip one more byte
000806: 1020             move.b  -(a0),d0              ; seed the bit buffer (no marker rotated in:
                                                       ; this byte's own low set bit is its marker)

; ---- main loop: [optional literal run] then, unless spent, one match ------
000808: e308        L_TOP:  lsl.b   #1,d0               ; getbit
00080a: 6604             bne.s   $810
00080c: 1020             move.b  -(a0),d0
00080e: e310             roxl.b  #1,d0
000810: 6464             bcc.s   $876                  ; 0 -> no literals

; ---- literal run ---------------------------------------------------------
000812: 4241             clr.w   d1                    ; d1 = 0 -> run of 1 byte
000814: e308             lsl.b   #1,d0                 ; getbit
000816: 6604             bne.s   $81c
000818: 1020             move.b  -(a0),d0
00081a: e310             roxl.b  #1,d0
00081c: 6442             bcc.s   $860                  ; 0 -> exactly one literal
00081e: 47fa 0038        lea     LIT_TAB(pc),a3        ; -> $858
000822: 7603             moveq   #3,d3                 ; start at the narrowest tier
000824: 4241        L_LIT_TIER: clr.w d1
000826: 1433 3000        move.b  0(a3,d3.w),d2         ; d2 = bit count for this tier
00082a: 4882             ext.w   d2
00082c: 78ff             moveq   #$ff,d4               ; sign-extends: d4 = $ffffffff
00082e: e56c             lsl.w   d2,d4
000830: 4644             not.w   d4                    ; d4 = (1 << bits) - 1  (the escape value)
000832: 5342             subq.w  #1,d2
000834: e308        L_LIT_BIT:  lsl.b #1,d0             ; getbit
000836: 6604             bne.s   $83c
000838: 1020             move.b  -(a0),d0
00083a: e310             roxl.b  #1,d0
00083c: e351             roxl.w  #1,d1                 ; d1 = (d1 << 1) | bit
00083e: 51ca fff4        dbf     d2,$834
000842: 4a43             tst.w   d3
000844: 6706             beq.s   $84c                  ; widest tier: no escape left
000846: b841             cmp.w   d1,d4
000848: 56cb ffda        dbne    d3,$824               ; all-ones -> widen (d3--) and re-read
00084c: 1433 3004    L_LIT_ADD: move.b 4(a3,d3.w),d2   ; d2 = base for the tier we stopped at
000850: 4882             ext.w   d2
000852: d242             add.w   d2,d1
000854: 6000 000a        bra.w   $860
                                                       ; bits:  10  3  2  2   (tier 0..3)
000858:                  LIT_TAB: dc.b $0a,$03,$02,$02
                                                       ; base:  14  7  4  1
00085c:                           dc.b $0e,$07,$04,$01
                                                       ; -> run lengths 1 | 2..4 | 5..7 | 8..14 | 15..1038
000860: 1320        L_LIT_CPY: move.b -(a0),-(a1)      ; the literal itself
000862: 2f00             move.l  d0,-(a7)              ; --- colour flash: show the stream bytes
000864: 1010             move.b  (a0),d0               ;     in palette entry 0 while unpacking
000866: e198             rol.l   #8,d0
000868: 1028 0001        move.b  1(a0),d0
00086c: 31c0 8240        move.w  d0,$ffff8240.w
000870: 201f             move.l  (a7)+,d0              ; --- end colour flash
000872: 51c9 ffec        dbf     d1,$860               ; d1+1 literals in total

; ---- end of stream? ------------------------------------------------------
000876: 2678 0090    L_MATCH: movea.l $90.w,a3         ; a3 = file+4
00087a: 508b             addq.l  #8,a3                 ; a3 = file+12 = start of the stream
00087c: b1cb             cmpa.l  a3,a0
00087e: 6f00 00c6        ble.w   $946                  ; consumed it all -> done

; ---- match length: unary prefix picks a tier -----------------------------
000882: 47fa 003a        lea     LEN_TAB(pc),a3        ; -> $8be
000886: 7403             moveq   #3,d2
000888: e308        L_LEN_UN:   lsl.b #1,d0             ; getbit
00088a: 6604             bne.s   $890
00088c: 1020             move.b  -(a0),d0
00088e: e310             roxl.b  #1,d0
000890: 6404             bcc.s   $896                  ; a 0 bit ends the prefix
000892: 51ca fff4        dbf     d2,$888               ; 0,10,110,1110 -> d2 = 3,2,1,0
                                                       ; 1111          -> d2 = -1
000896: 4241             clr.w   d1
000898: 5242             addq.w   #1,d2                ; tier = 4,3,2,1,0
00089a: 1633 2000        move.b  0(a3,d2.w),d3         ; bit count
00089e: 6712             beq.s   $8b2                  ; 0 bits -> nothing to read
0008a0: 4883             ext.w   d3
0008a2: 5343             subq.w  #1,d3
0008a4: e308        L_LEN_BIT:  lsl.b #1,d0             ; getbit
0008a6: 6604             bne.s   $8ac
0008a8: 1020             move.b  -(a0),d0
0008aa: e310             roxl.b  #1,d0
0008ac: e351             roxl.w  #1,d1
0008ae: 51cb fff4        dbf     d3,$8a4
0008b2: 1633 2005    L_LEN_ADD: move.b 5(a3,d2.w),d3
0008b6: 4883             ext.w   d3
0008b8: d243             add.w   d3,d1                 ; d1 = match length
0008ba: 6000 000c        bra.w   $8c8
                                                       ; bits: 10  2  1  0  0   (tier 0..4)
0008be:                  LEN_TAB: dc.b $0a,$02,$01,$00,$00
                                                       ; base: 10  6  4  3  2
0008c3:                           dc.b $0a,$06,$04,$03,$02
                                                       ; -> lengths 2 | 3 | 4..5 | 6..9 | 10..1033

; ---- match offset --------------------------------------------------------
0008c8: 0c41 0002        cmpi.w  #2,d1
0008cc: 6740             beq.s   $90e                  ; length 2 has its own, shorter, offset code
0008ce: 47fa 0032        lea     OFF_TAB(pc),a3        ; -> $902
0008d2: 7601             moveq   #1,d3
0008d4: e308        L_OFF_UN:   lsl.b #1,d0             ; getbit
0008d6: 6604             bne.s   $8dc
0008d8: 1020             move.b  -(a0),d0
0008da: e310             roxl.b  #1,d0
0008dc: 6404             bcc.s   $8e2
0008de: 51cb fff4        dbf     d3,$8d4               ; 0,10 -> d3 = 1,0 ; 11 -> d3 = -1
0008e2: 5243             addq.w  #1,d3                 ; tier = 2,1,0
0008e4: 4242             clr.w   d2
0008e6: 1833 3000        move.b  0(a3,d3.w),d4         ; bit count MINUS ONE (plain dbf below)
0008ea: 4884             ext.w   d4
0008ec: e308        L_OFF_BIT:  lsl.b #1,d0             ; getbit
0008ee: 6604             bne.s   $8f4
0008f0: 1020             move.b  -(a0),d0
0008f2: e310             roxl.b  #1,d0
0008f4: e352             roxl.w  #1,d2
0008f6: 51cc fff4        dbf     d4,$8ec
0008fa: e34b             lsl.w   #1,d3                 ; the bases are words
0008fc: d473 3004        add.w   4(a3,d3.w),d2         ; d2 = match offset
000900: 6030             bra.s   $932
                                                       ; bits-1: 11  4  7   -> 12, 5, 8 bits
000902:                  OFF_TAB: dc.b $0b,$04,$07,$00
                                                       ; base:  288  0  32
000906:                           dc.w $0120,$0000,$0020
                                                       ; -> offsets 0..31 | 32..287 | 288..4383
00090c:                           dc.w $0000            ; padding

; ---- match offset, length == 2 -------------------------------------------
00090e: 4242             clr.w   d2
000910: 7605             moveq   #5,d3                 ; 6 bits
000912: 4244             clr.w   d4                    ; bias 0
000914: e308             lsl.b   #1,d0                 ; getbit
000916: 6604             bne.s   $91c
000918: 1020             move.b  -(a0),d0
00091a: e310             roxl.b  #1,d0
00091c: 6404             bcc.s   $922
00091e: 7608             moveq   #8,d3                 ; 9 bits
000920: 7840             moveq   #$40,d4               ; bias 64
000922: e308        L_OFF2_BIT: lsl.b #1,d0             ; getbit
000924: 6604             bne.s   $92a
000926: 1020             move.b  -(a0),d0
000928: e310             roxl.b  #1,d0
00092a: e352             roxl.w  #1,d2
00092c: 51cb fff4        dbf     d3,$922
000930: d444             add.w   d4,d2                 ; -> offsets 0..63 | 64..575

; ---- copy the match ------------------------------------------------------
000932: 45f1 2000    L_COPY: lea  0(a1,d2.w),a2        ; a2 = dest ptr + offset
000936: 48c1             ext.l   d1
000938: d5c1             adda.l  d1,a2                 ; ... + length  (source is ABOVE the write
00093a: 5341             subq.w  #1,d1                 ; pointer, i.e. already-written output)
00093c: 1322             move.b  -(a2),-(a1)
00093e: 51c9 fffc        dbf     d1,$93c               ; d1+1 = length bytes
000942: 6000 fec4        bra.w   $808

000946: 31df 8240    L_DONE: move.w (a7)+,$ffff8240.w  ; restore palette entry 0
00094a: 4e75             rts

; ============================================================================
; NOT this routine: the magic-less .RAD/.CRU container
;
; 6 files (AUTO/CREDITS.RAD, OVALAY0B, OVALAY11, OVALAY6A, TILEDATA.RAD,
; TITLESCR.RAD) carry no 'LSD!' magic. They are NOT an LSD! header variant —
; they are the game's own resource container, and the 37 LSD!-wrapped .RAD/.CRU
; files inflate to exactly that same container (so those are doubly packed):
;
;   +0  be32  packed length = filesize - 12
;   +4  be32  unpacked length ($3ce8 for every OVALAY*, $7d80 for the two
;             screens, $14a80 for TILEDATA; SPRITES.CRU stores +0 == +4, i.e.
;             stored-not-packed, and its body starts with 16-word ST palettes)
;   +8  ..    stream
;
; Feeding one to this routine never closes cleanly (the output under/overruns),
; so it is a second, different cruncher. Its depacker is NOT in VAPOUR2.PRG:
; neither the loader stub nor the 136,979-byte LSD!-packed payload embedded at
; text $94c contains a backwards bit-reader (no `lsl.b #1,dn / roxl.b #1,dn`
; pair anywhere in either). Unsolved — see the report in the session notes.
; ============================================================================
