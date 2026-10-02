# TOS 1.02 AES + desktop map (0xFD9ECA..0xFEE8FF, data 0xFEE900..0xFEFFF3) — read-only research 2026-09-29

Artefacts in `aes_map/` (generated during the 2026-09-29 research; plain text, regenerate by the method described here):
`cfg.txt` (recursive descent over Line-F calls + jsr/bsr + both Alcyon switch forms + the AES opcode table + code-pointer
immediates; 736 entries, 84,170 of 84,534 B reached), `inventory.txt` (one line per function: class A/D/S, size, Line-F index,
role, callees, caller count), `part.json` (the call-graph partition), `ram.txt` (every absolute RAM address the text touches,
per class, with its snapshot value), `decomp_status.txt`, `names_candidates.txt` (132 fn lines, NOT applied — the ones since
verified are in names.txt). **`linef_dis.py LO HI` is the disassembler to use** (it decodes GEM's one-word Line-F calls and
returns): not decomp.c or a raw objdump — both mis-decode ~355 Line-F call words as 68851/68881 instructions (psave/prestore/fsave/fb*…).

**Errata found since (the AES foundation, STATUS.md wave 11 — trust these over the text below):** in "optimize" only part is hand
68000 — `0xFECFB2`, `0xFED19E` (ob_sst), `0xFED27C` (everyobj), `0xFED382` (get_par) are Alcyon C; `0xB74A` is window 0's
visible-rectangle list (an ORECT via the window record's +48), not a tree; the three UDAs have different sizes (1,866 / 1,274 /
1,474 B), not one stride; 42 routines own more than one Line-F call word (ob_offset: `$F208` ×4, `$F154` ×3); the fork queue is
fed by 16 ROM-code immediates (6 pushes, ap_tplay's local, forker's and ap_trecd's compares — `test/aes.py`
FORK_FUNCTION_IMMEDIATES); the 100-byte Line-F RAM copy carries ORIGINAL ROM code addresses as data.

**Errata from bands 0+1 (STATUS.md wave 11 bands 0+1):** the TEDINFO text helpers are REVERSED in §2 and the inventory — `0xFECF84` is the text SET (fs_sset) and `0xFECFD6` the GET (fs_sget); `0xFED19E` is ob_sst and `0xFED27C` everyobj (read from the bodies); `0xFEE4DE` ("ROM rsrc fixup") is the resource BUNDLE COPY and its six-part table — the relocation is rom_ram `0xFEE5C8` (through do_rsfix); `0xFE3DB4`/`0xFE3E08` are Alcyon's runtime `lmul`/`ldiv`; `0xFECC6C` is strlen, not strlen+1; `0xFECBC6`/`0xFECBDA` have callers (ap_tplay/ap_trecd) — only `0xFECB8A..0xFECBC5` and `0xFECBD0` are unreached; `0xFED18E` (OB_ADDR) reads its CALLER's frame; the shared tails `0xFED066`/`0xFED06A`/`0xFED06E` are the physical end of inf_what `0xFED03A`; the resources start at `0xFD5B92` (AES) and `0xFD6F52` (desk) — COMPONENTS.md's `0xFD6F3E`/`0xFD83BF` are name strings inside the bundle `0xFD5B88`. The old `linef_dis.py` split 8-byte instructions (a trailing word printed as `.short` or a bogus `LF_CALL 0xFE64A6`) — fixed in `56e22f1`; a "call to aes_unimplemented" read before that fix may not be real.

**Errata from band 2 wave 1 (STATUS.md wave 11 band 2 wave 1):** three gemgsxif names were swapped in the inventory — `0xFE8A38` is gsx_mfset (not "gsx_moff/mon"), `0xFE8A72` gsx_moff (not "gr_mouse arm helper") and `0xFE8A8E` gsx_mon (not gsx_mfset; fixed in `inventory.txt`). gemgraf (`0xFDA56E..`), gemgrlib (`0xFE82D6..`) and gemgsxif (`0xFE8790..`) are HAND 68000 (movem prologues, no `link`, register-contract fragments, pc-relative tables), not Alcyon C as §3's authorship line says; nearly every routine in them makes Line-F calls, so only their Line-F-free leaves can ship as `.S`. §1.5's "two direct ones in gemgraf" (`0xFDA8E6` gsx_attr, `0xFDAD0A` gsx_tblt) are NOT trap sites: they fill contrl by hand and Line-F-call gsx2 (`$F038`) — gsx2's `trap #2` at `0xFECB6A` is the AES's only one. The parameter block is `0x9466` as §1.5 says (`0xC7EE..0xC7F5` is contrl[7..10], the MFDB / vex pointer slots — STATUS.md had called it the block). `0xFEFBA0`/`0xFEFBCC` (11 rows each) are just_draw `0xFE9A88`'s two Alcyon jump tables, not ob_edit's, and `0xFEA01C` is just_draw's tail, not a function; `0xFDAE96`/`0xFDAEE2` are the desk's (Alcyon list routines through `0xC6A6`), misfiled in gemgraf's range. TOS 1.02's WS_* values are FULL 0, CURR 1, PREV 2, WORK 3, TRUE 4 (w_getxptr's table `0xFEFCCA`; wind_get's arms hand w_getsize 3/1/2/0 at `0xFEC742..0xFEC754`), not GEM's CURR 0 / PREV 1 / FULL 2, and the window record's GRECTs are +16 FULL, +24 WORK, +32 PREV — the CURRENT rectangle is the window tree's object (`0x9734` + wh*24 + 16). newrect `0xFE5CEE` cuts the windows BEFORE wh in tree order (everyobj stops on `last` = wh), not "every other window", walks gl_wtree (`0x9B2C` → `0x9734`) and has no Line-F call word. The ROM text holds **39** absolute operands naming AES code, not 37 (the design note's list omitted `0xFE3C84` — install_trap2 runs twice —, `0xFE66B6`, ap_tplay's second `0xFED424` push and gem_entry's `0xFD9F92`/`0xFD9F9E`); `0xFEE8D6`'s `movea.l #` names `0xFEE900`, the Line-F CALL TABLE — data, not code. A fourth code-bytes-read-as-data site: the Line-F handler's `lea (pc,$FEE8F8)` + `move.w d1,(a0)` WRITES its own movem mask (beside gr_watchbox `0xFE84CA`, gr_rubbox `0xFE85CE`, gr_dragbox `0xFE869C` reading gr_setup's/gr_draw's `move.l #` immediates). `0xFEADDC` is sh_main's sh_find routine (it calls `0xFEADA0` twice). vst_height `0xFE8B22` and vsl_width `0xFE8B92` never set PTSIN and rely on the previous call having put it back (`0xFE8BD0`); vr_recfl's op-table row passes n_intin = 1. gsx_fix's form arm shifts one WORD (`lsl.w #3`, `lsr.w #4`), so a byte width ≥ `$2000` wraps to 0. sh_find's DTA (`0xB89A`) IS rs_str's buffer; the path buffer `0xBB3E` is `$52` bytes, directly under the AES's global[] at `0xBB90`. A linear objdump of the AES text re-syncs at ~295 places; `0xFE39B4` is a data word (Pexec's empty tail) before a `jmp 0xFE3C3E`. The ROM-address census (`recreate/test/test_aes_rom_data.py`) now holds the AES's code immediates and pc-relative data references both ways (sources → list, ROM text → list).

**Errata from band 2 wave 2 (STATUS.md wave 11 band 2 wave 2):** `0xFE89C6` is gsx_setmb proper; `0xFE883E` (the band-2 design note's "gsx_setmb") is gsx_graphic `0xFE8828`'s TAIL — the `gsx_setmb($FED3BE, $FED3E4, &drwaddr $947A)` call — which gsx_init enters by `bsr` (named gsx_setmb_aes); gsx_setmb's third argument is never read. In gemgrlib `0xFE8472` is gr_scale and `0xFE82E6` gr_stepcalc (the design note had them swapped; `0xFE82D6` is stepcalc's half-difference fragment and `0xFE831E` grow/shrinkbox's shared prologue, which reads its CALLER's arguments at 44(sp)); gr_growbox `0xFE8340` and gr_shrinkbox `0xFE837A` are confirmed. gr_setup `0xFE85B0` clips to `0x98A4` gl_rscreen (the whole screen), not gl_rfull `0x98AC`. `0xC844` is GEM's ad_intin (gsx_start `0xFDAC14` stores `$95BA`): gsx_mfset's destination and gsx_tcalc's xstrpix target, not a "mouse form" slot. `0xFE886A` is gsx_escapes' register entry (D0 = the escape, gsx_graphic's two `bsr`s); `0xFE8BB6`/`0xFE8BBA` are gsx_call (no separate routine in the C). Every gemgsxif routine is hand 68000 although `inventory.txt` marks many `A`. gr_clamp `0xFE86DC` (with its fragment `0xFE86C2`), gr_draw `0xFE8532` and gr_xdraw `0xFE8564` are reached only from the interactive loops (gr_rubbox/gr_dragbox, gr_wait) — band 3. gr_mkstate's fourth word is the keyboard shift state `0xC72A`, read through a pc-relative address table at `0xFE8780`. gl_mlen `0xC920` is read by gsx_mret and written by nothing in the AES; `0xC916` is an attribute cache nothing reads. ratinit's v_show_c(0) FORCES the cursor shown (`0xFCB12A`). gsx_chkclip counts an edge EQUAL to the clip's as touching (`blt`); gsx_tblt never sets PTSIN; gsx_tcalc's count is a byte (wraps at 256); gr_box's negative thickness draws -t+1 lines; gr_gicon pushes an extra word (GEM's dropped `tmode`). gsx_bxpts `0xFDA956`, gsx_xline `0xFDAE38` and gr_stepcalc have no Line-F call word (`bsr`-only). The AES's one `$A000` word is gsx_mfsave's (`0xFEE498`). gsx_malloc's save buffer is `$3400` bytes (`0xFE879C`), never checked against a drop-down's size.

**Errata from band 2 wave 3 (STATUS.md wave 11 band 2 wave 3):** `0xFDDEC6` (unnamed in the inventory) is far_call — `move.l 12(a6),-(sp); movea.l 8(a6),a0; jsr (a0)`, D0 the routine's — and ob_user `0xFE9A46`'s only callee, by `$F118` at `0xFE9A80`; ob_user's own call word is `$F148` (just_draw `0xFE9DC4`, ob_change `0xFEA43A`). ob_format `0xFE99A4` has TWO call words: `$F92C` (ob_edit, `0xFE9746`/`0xFE9918`) and `$F13C` (just_draw, `0xFE9C8A`). `0xFEA028` is ob_draw and `0xFEA38E` ob_change, read from the bodies (no longer by context); ob_draw has one call word, `$F200` (14 sites), and hands everyobj just_draw `0xFE9A88` BY VALUE (`0xFEA08C` `move.l #$FE9A88,-(sp)`); ob_change has two, `$F214` (15 sites) and `$F098` (gr_watchbox, `0xFE84E6`); just_draw is also entered by `$F16C` (ob_change `0xFEA4AC`). `0xFEA01C` is just_draw's TAIL (the `move.l #$30001` + bb_fill call), confirmed, not a function. just_draw's two jump tables decoded from the ROM: `0xFEFBA0` (border + fill) 20/25/27 → `0xFE9BA6`, 26 → `0xFE9BC8` (BUTTON's re-test of the type inside the shared arm), 22/30 → `0xFE9BDA`, the rest → `0xFE9C3E`; `0xFEFBCC` (contents) 21/22 → `0xFE9CC2`, 23 → `0xFE9CFA`, 24 → `0xFE9DB2`, 27 → `0xFE9C92`, 29/30 → `0xFE9C56`, 31 → `0xFE9D56`, 25/26/28 → `0xFE9DEA`; the G_STRING rows of both are DEAD (STRING branches to the label at `0xFE9B2A` before either table). The AES resource's tree 2 (the desktop band, `0xCFF4`, 3 objects) has NO LASTOB flag — a length walk runs past it into garbage, so walk links; its G_TEXT (obj 2, TEDINFO `0xD18C`) has te_ptext -1 in the snapshot, the placeholder sh_draw `0xFEADA0` overwrites through ad_pfile `0xC7A2` (set at `0xFEB102` to `*(ad_stdesk + 60)`; ad_stdesk `0xC820` = tree 2) at `0xFEADCA`, right before its ob_draw. `0x9B26` is gl_mntree (the desk's menu, `0xE098`) and `0xC942` gl_newdesk (the desk's icon tree, at `0x181D2` in the TPA in this snapshot: TRASH, A:, B:). just_draw's buffers: `0x9C20` edblk (a TEDINFO), `0xB756` rawstr, `0xB7A7` tmplt — ODD, byte access only —, `0xB7F8` the editor's 81-byte buffer, `0xB849` fmtstr (81 bytes each, GEM's MAX_LEN), `0xC732` BITBLK and `0xC740` ICONBLK copies. gl_font `0x980C` has exactly two writers, gsx_start `0xFDAACE` (-1) and gsx_tblt `0xFDAD4A` (after its own vst_height): a cache of the VDI's face. The bindings at `0xFDE2FE` (in `0xFDE2E8`) and `0xFDE32C` (in `0xFDE30E`) store and return the D0 ob_draw / ob_change leave (gsx_mon's, or ob_change's old state on an early return), though both routines are void in GEM. Every editable field of the desk's resource is an FBOXTEXT, and every raw text in both resources starts '@'.

## Five things that change the plan
1. **GEM never enters the AES through its own ABI.** The desktop calls the AES *implementation* functions directly (Line-F), not
   `trap #2`: `0xFE65AA` has one caller (the trap handler), and the desk carries its own binding layer `0xFDDE54..0xFDE4CC` (34
   wrappers, each `dsptch(); <internal>()` — e.g. `0xFDE430` → wm_create `0xFEC602`, `0xFDDED8` → ev_multi `0xFE6998`). So the AES's
   testable surface is ~60 internal C entry points (`ap_*/ev_*/ob_*/fm_*/gr_*/mn_*/wm_*/rs_*/sh_*`, table in §1), and the desk can
   only be reconstructed after them. The partition is clean: desk = `0xFDB014..0xFE387C` (34.8 KB, 206 fns, 33.4 KB desk-only by
   reachability) + its userdef callback `0xFDE500..0xFDE8A5`; everything from `0xFE387C` up is AES (§2).
2. **The snapshot is inside the dispatcher's idle loop.** `rlr` (`0xC794`) = NULL, `indisp` (`0xC67E`) = 1, both processes
   (PD0 shell/desk `0xAE5E`, PD1 SCRENMGR `0xAF16`) sit on `nrl` (`0xC726`) blocked in evnt_multi, and the CPU spins in
   `0xFE4D68` polling the keyboard THROUGH THE VDI (`chkkbd 0xFE4CD6`: VDI 128/33/31). Every case must POKE `rlr` (most AES code
   dereferences it) and must decide `indisp`: with the snapshot's 1, `dsptch 0xFE387C` is a bare `rts`, so a blocking primitive
   (`ev_mwait 0xFE40B2`) falls straight through — a usable lever, not real behaviour. The MASK is exactly this idle loop's footprint
   (§4). Blocking = `mwait → dsptch → disp 0xFE4D9E → switchto 0xFE3930` (an `rte` into ANOTHER process's UDA) — never returns.
3. **The Line-F handler runs from RAM and self-modifies.** `$2C` = `0xCC0E`, a Malloc'd 100-byte copy of `0xFEE8C2`; every Line-F
   return with a non-empty register mask WRITES its mask into `0xCC44` (the `movem` at `0xFEE8F6`+2 of the copy; snapshot 0x30C0).
   The original writes that word on ~2/3 of all returns and a C candidate never does → a per-byte dropped difference every AES row
   needs. And the recreate ROM must still Malloc(100)+copy 100 B at init or every later TPA block (desk globals at `0x143B4`,
   the handler itself) moves.
4. **Tier 3 will be generous on calls, but the desk's state is NOT in GEMBSS.** A Line-F call+return costs ~270 cycles more than
   `jsr`/`rts` (§1.4), 2,230 call sites; a gcc build with direct calls should sit well under 1.10 except the hand-asm layers
   (optimize `0xFECB5A..0xFED3BD`, gemdosif, irq glue). Meanwhile the desk reaches ALL its globals through ONE pointer, `0xC6A6`
   (94 references, only 1 elsewhere) → a 19,094-byte GEMDOS Malloc block at `0x143B4` (plus 512 @`0x18E4A`, 920 @`0x1904A`,
   16,000 @`0x193E2`, 1 KB userdef stack below `0x1D662`) allocated by `0xFEE80A` — desk cases stage/compare TPA, not `0x8900..`.
5. **Decompile quality in this range is poor and misleading.** 50 hard fails, 472 of 726 functions end in `halt_baddata` (the
   Line-F RETURN word; no return value), ~355 Line-F CALLS decode as coprocessor ops (`restoreFPUStateFrame` in 22 fns,
   `saveFPUStateFrame` in 13) and some calls simply vanish (`mwait_act 0xFE4B9C`'s `disp_act` call is absent from its C). Every
   Line-F call's d0 is invisible (389 `in_D0` uses in 98 fns). Port from linef_dis.py disassembly; treat decomp.c as a hint.

## 1. Entry mechanics
### 1.1 trap #2 → AES (`0xFE3EA6`, installed `0xFE3C78`; old vector → `0x8C2A` = `0xFC4EBC` VDI glue)
`d0==0` → `Pterm(0)` (`0xFE3EC0`); `d0==200/201` → AES; else `move.l 0x8C2A,-(sp); rts` (so AES→VDI calls pass through here
first). AES path: `jsr 0xFE3890` (spl7, SR→`0x8996`); **caller regs d1–a6 pushed onto the USER stack** (`move usp,a0; movem.l
d1-a6,-(a0); move a0,usp` — 56 bytes below the caller's USP are written); `a6 = rlr->p_uda` (`0xC794`→+8); `uda+0 := 1`
(in-super), `uda+66 := usp`, `uda+70 := ssp`, `sp := uda+62` (per-process supervisor stack); spl restore; `aes_entry(d0.w, 0,
d1.l)` via `movea.l #0xFE65AA,a0; jsr (a0)`; then the reverse, `uda+62 := sp`, regs popped from USP, `rte` (`0xFE3F3C`).
`aes_entry 0xFE65AA` (`link a6,#-4`): `200` → `aes_marshal 0xFE64E6(pb)` (`$f2b4`); then, for both 200 and **201**, `dsptch()`
(`$f2b8`) and `$f2bc` = **`0xFE3F08`, the trap handler's OWN epilogue called as a function**: `move.w 4(sp),d0` (the `clr.w (sp)`
= 0), spl7, `adda.l #24,sp` discards aes_entry's frame + the handler's pushes, restores USP/regs from the UDA, `rte`. So aes_entry
never returns through its `f001`, the user gets d0 = 0, and **`d0 = 201` is a pure yield** (dispatch, no call). `aes_marshal`
(`link a6,#-66`): copies contrl (4 words, `wcopy 0xFECC40` via `$f170`), intin (contrl[1] words), addrin (2·contrl[3] words) into
its frame, calls `aes_dispatch 0xFE5D9C(op, &contrl, intin, intout, addrin)` via `$f2b0`, copies intout (contrl[2]) back; op 112
(rsrc_gaddr) writes addrout[0] := `*(0x944C)` (`0xFE658C`).
### 1.2 The dispatcher `0xFE5D9C` (Alcyon switch, `link a6,#-20`)
`sub #10; cmp #115; bhi default; jmp *(0xFEF834+4*(op-10))` (`0xFE64BA`); arms end in `bra` to a `tst.w (sp)+` ladder
`0xFE64D2..0xFE64E0` and return `d6` (intout[0]) via `f031`. Default arm `0xFE64A6`: `fm_error`-style alert `$f1a8(0x1B0000,1)`,
returns −1. Opcode → arm → implementation (from the arm's Line-F call):
10 appl_init `FE5DB2` (inline: global[] fill, pid) | 11/12 appl_read/write `FE5DF2/6` → ap_rdwr `FE65C4` | 13 `FE5E0C`→ap_find `FE65DA`
| 14 `FE5E1A`→ap_tplay `FE6610` | 15 `FE5E2C`→ap_trecd `FE6766` | 19 appl_exit `FE5E40`→`FE91A4`,`FE65C4`,`FDA03E`
| 20 ev_keybd `FE6894` | 21 ev_button `FE68A4` | 22 ev_mouse `FE68E4` | 23 ev_mesag `FE6910` | 24 ev_timer `FE6936` | 25 ev_multi
`FE6998` | 26 ev_dclick `FE6C5E` | 30 mn_bar `FE902A` | 31/32/33 → do_chg `FE8C14` | 34 menu_text → strcpy `FECBE6` | 35 mn_register
`FE91E2` | 40 ob_add `FEA1BA` | 41 ob_delete `FEA21E` | 42 ob_draw `FEA028` (+`FDA7F8`) | 43 ob_find `FEA0A8` | 44 ob_offset `FEA584`
| 45 ob_order `FEA2BE` | 46 ob_edit `FE9678` | 47 ob_change `FEA38E` | 50 fm_do `FE74A4` | 51 fm_dial `FE75EC` | 52 fm_alert
`FE7002` | 53 fm_error `FE7712` | 54 form_center → ob_center `FE92AE` | 55 fm_keybd `FE7298` | 56 fm_button `FE7346` | 70 gr_rubbox
`FE85C6` | 71 gr_dragbox `FE8640` | 72 gr_movebox `FE8402` | 73/74 arms `FE6216`/`FE621E` → gr_growbox `FE8340` / gr_shrinkbox `FE837A` through the dispatcher's one
`movea.l #fn,a0; jsr (a0)` (`FE622E`) | 75 gr_watchbox `FE84BA` | 76 gr_slidebox `FE86FA` | 77 graf_handle `FE6266`
(inline) | 78 graf_mouse `FE628E` → `FE8A72 FE8A8E FEAA86 FE8A38` | 79 gr_mkstate `FE8768` | 80/81 sc_read/write `FEAC80/94` | 90
fs_input `FE7D90` | 100..107 wm_create/open/close/delete/get/set/find/update `FEC602 FEC6DA FEC6F0 FEC706 FEC722 FEC83A FECA4A
FECA68` | 108 wm_calc arm `FE63AE` → `FECAAC` | 110..114 rs_load/free/gaddr/saddr/obfix `FEAC5C FEAA58 FEAA86 FEAAB2 FEA69C` |
120..125 sh_read/write/get/put/find/envrn `FEACA8 FEACD4 FEAD26 FEAD40 FEAFBE FEAE36`.
Gaps (48, all → `0xFE64A6`): 16–18, 27–29, 36–39, 48–49, 57–69, 82–89, 91–99, 109, 115–119.
### 1.3 Line-F (the GEM call mechanism)
Install `0xFD9F2E`: **only if the top byte of `$2C` is non-zero** (boot's default `0x0BFC0B50` is; a program-installed 24-bit
handler would stop GEM installing its own), `Malloc(100)`, copy 50 words from `0xFEE8C2` (62 B handler + 38 B of the call table),
`$2C :=` the block (snapshot `0xCC0E`). Handler (ROM `0xFEE8C2`, `= $2C` copy):
```
FEE8C2 341F      move.w (sp)+,d2        ; caller SR
FEE8C4 205F      movea.l (sp)+,a0       ; PC of the $Fxxx word (68000 stacks the faulting PC)
FEE8C6 3218      move.w (a0)+,d1        ; opcode, a0 = return address
FEE8C8 0801 0000 btst #0,d1 / FEE8CC 6614 bne ret
FEE8CE 46C2      move.w d2,sr           ; back to the CALLER's mode+IPL (user → pushes on USP)
FEE8D0 2F08      move.l a0,-(sp)        ; = jsr's return address
FEE8D2 0241 0FFF andi.w #$fff,d1 / FEE8D6 207C 00FE E900 movea.l #table,a0 / FEE8DC 2070 1000 movea.l 0(a0,d1.w),a0 / 4ED0 jmp (a0)
ret: FEE8E2 0241 0FFE andi.w #$ffe,d1 / 6712 beq plain / E549 lsl.w #2,d1 / 007C 0700 ori #$700,sr
     FEE8EE 41FA 0008 lea mask(pc),a0 / 3081 move.w d1,(a0)   ; SELF-MODIFY the movem mask (RAM copy +0x36 = 0xCC44)
     588F addq.l #4,sp (= Alcyon's tst.l (sp)+) / FEE8F6 4CDF xxxx movem.l (sp)+,<mask>
plain: FEE8FA 46C2 move.w d2,sr / 4E5E unlk a6 / 4E75 rts
```
Call word `$F000|off` (even, off = byte offset, 658 entries `0xFEE900..0xFEF347`, 600 distinct targets); return word
`$F001|m` with post-increment movem mask `(m&$ffe)<<2`, i.e. word bit j restores register j+2 (bit1..5 = d3..d7, bit9..11 = a3..a5): `$f031`
→ `0x00C0` = d6/d7, `$f801` → `0x2000` = a5, `$fc21` → `0x3080` = d7/a4/a5, `$fe01` → `0x3800` = a3-a5, `$f839` → `0x20E0`. The
lowest register the prologue saved is the argument slot the `addq #4,sp` discards (Alcyon `link; movem.l d5-d7,-(sp)` ↔ return
restores d6-d7). Clobbers: d1, d2, a0 (+ CCR = caller's) on a call; d1, d2, a0 on a return. Callees may equally return by `rts`
(all the asm helpers do). **The return path's movem pops the SUPERVISOR stack** (SR restored only after it), so any function
with a non-empty mask works only when its caller runs in supervisor mode — true for all GEM code (gem_entry `Super` at
`0xFD9EFC`; the AES runs on the UDA super stack). Accessories run in USER mode (`gotopgm 0xFE38B0` `rte`s into `p_tbase` with
S cleared) and use `trap #2`, never Line-F. Interrupt handlers `jsr` into C (`0xFED3D0`, `0xFED454`) whose Line-F returns then run
at IPL≥ their level; the `ori #$700` around the patch is what makes that safe.
**For a C reconstruction:** a Line-F call is exactly `jsr target` + clobber d1/d2/a0; a Line-F return is exactly the Alcyon epilogue.
Nothing observable remains EXCEPT (a) the RAM word `0xCC44` the original rewrites, (b) the 100-byte Malloc + copy at init, (c) CCR
restore (irrelevant to C). Direct C calls on target are faithful. 2,230 call sites / 454 return sites (304 with a mask) found.
### 1.4 Cost (68000, cycles): call path ≈ 34 (exception) + 118 = ~152 vs `jsr abs.l` 20 (+132); masked return ≈ 204+8n vs
Alcyon epilogue 52+8n (+152); plain return ≈ 140 vs `unlk;rts` 28 (+112). **~250–285 cycles per call/return pair** that a gcc
build (`jsr`/`bsr`) does not pay. Tier 3's denominator must run with `$2C` → `0xCC0E` as captured (it is) and drop `0xCC44`.
### 1.5 AES → VDI: exactly ONE `trap #2`: `gsx2 0xFECB5A` (`lea 0x9466,a0; move.l #0xC7E0,(a0); move.l a0,d1; moveq #115,d0;
trap #2`). Param block `0x9466` = contrl `0xC7E0`, intin `0x95BA`, ptsin `0x98C4`, intout `0x9706`, ptsout `0x9ABC`. Callers:
`gsx_ncode 0xFE87D2` (opcode, n_ptsin, n_intin) and two direct ones in gemgraf (`0xFDA8E6`, `0xFDAD0A`, raster copy). The path is
`trap #2 → 0xFE3EA6 (3 compares, chain) → 0xFC4EBC → vdi_entry`. The AES also uses Line-A `$A000` once (`0xFEE498`: Line-A base −
0x358 = `0x2642` M_POS_HX; saves/restores the 74-byte mouse form via `LBCOPY`), and GEMDOS through `__DOS 0xFE39B6` → `0xFE3C3E`
(`trap #1`, return address parked at `0x8C1E`, `DOS_ERR 0x98EC`, `DOS_AX 0xC918` — not re-entrant), BIOS/XBIOS via
`0xFEE478`/`0xFEE488` (return parked at `0x95AE`/`0x95B2`), `0xFD9FC6` (return at `0x8900`).

## 2. The aes/desk boundary (roots: AES arms + trap + ptr + gem_entry with the edge sh_main→deskmain CUT, vs deskmain)
Desk main = **`0xFE272E`** (844 B), called once, from `sh_main 0xFEB0E6` (`0xFEB1DC`, between `desk_alloc 0xFEE80A` and
`desk_free 0xFEE870`) — the ROM desktop is a SUBROUTINE of the AES shell running in PD0, not a process of its own. The
`"\DESKTOP.INF"` reader at `0xFDA444` (fn `0xFDA408`) is **AES-side** (gem_main reading `#E` resolution/double-click); the desk's
own INF parse/write is `0xFDB5FC`/`0xFDBB34` (strings `0xFEF414`/`0xFEF420`).
Result: A-only 229 fns / 26.6 KB, D-only 209 / 34.1 KB, shared 298 / 29.5 KB (sizes overlap in the dispatcher arms).
| range | verdict | confidence | evidence |
|---|---|---|---|
| `FD9ECA..FDA56D` | AES gemstart + geminit | high | MUPB entry; gem_main `FDA062` builds THEGLO |
| `FDA56E..FDAF1F` | SHARED gemgraf (VDI wrappers) | high | callers both sides; gsx calls |
| `FDAF20..FDB013` | SHARED inf-scan helpers | high | called by `FDA408` and desk `FDB082/FDB5FC/FDBB34` |
| `FDB014..FE387B` | **DESK** | high | 33.4 of 34.8 KB desk-only; strings `FEF364..FEF465`, `FEF560..FEF770`; switch tables `FEF364..FEF770` |
| ↳ `FDDE54..FDE4CC` | desk AES bindings | high | each `dsptch()`+internal call |
| ↳ `FDE500..FDE8A5` | desk G_USERDEF draw (dir lines `%L %W am/pm`) | high | reached only via ptr `0x8C32`→`0xFE3F3E` (copied to desk G+5580 at `FE3094`); 30-B PARMBLK copy `FDE850` |
| ↳ `FDBAE0 FDBECC FDDDE6 FDE094 FDE2E8 FDE354 FE0B6E FE1BDC` | desk code the AES also calls | medium | e.g. `FE1BDC` from format/copy |
| `FE387C..FED477` | AES | high | everything under the dispatcher |
| `FED478..FEE497` | cartridge apps + shell post-exit utilities (launch `FED61E`, print `FED624`, **format `FED912`, disk copy `FEDDE4`**) | medium | reached only from `sh_cmd 0xFEB2FC` (command byte `0xC42E`: FE/FD/FC/FB), but their strings sit INSIDE the desk's data run (`FEF47E..FEF55F`) — desk-authored ST extras linked late; schedule with the desk band |
| `FEE498..FEE8FF` | AES init tail (mouse-form save, ROM rsrc fixup `FEE4DE`/`FEE5C8`, desk_alloc/free, handler) | high | |
Desk-only leaves living in AES modules: `FE3A7C FE3AB0..FE3B02 FE3BA0 FE3C16..FE3C22` (DOS glue), `FE8862`, `FECEEE`, `FECFB2`,
`FECFEE`, `FED522/FED534`. COMPONENTS.md's "45-entry switch table at 0xFEFB88" is three tables: search-switch labels of `FE98E0`
(6 values @`FEFB70`, 7 labels @`FEFB88`) + `FEFBA0`/11 (`FE9C3C`) + `FEFBCC`/11 (`FE9DE8`) + `FEFBF8`/17 (`FEA850`) — all ob_edit.
**Shared utility layer** (both sides call): `optimize` hand asm `0xFECB5A..0xFED3BD` (2.1 KB: gsx2, mul_div `FECB6E`, strcpy
`FECBE6`/`FECEB8`, strlen `FECE8C`/`FECC6C`, streq `FECE9C`, strcat `FECEDA`, toupper `FECE74`, bfill `FECE5E`, LBCOPY `FECC7E`,
rc_copy/equal/intersect/union/constrain `FECCCA FECD0C FECD22 FECD8C FECDE4`, inside `FECCD6`, min/max `FECE42/4E`, fmt_str/unfmt
8.3 `FECF24/58`, ob text get/set `FECF84/FECFD6`, merge_str (%-format) `FED070`, wildcmp `FED12E`, OB_ADDR `FED18E` (tree+24*obj),
everyobj walker `FED19E`, get_par `FED27C`); gemgraf; gemgsxif `FE8790..FE8C13`; DOS/BIOS glue `FE39A6..FE3C61`; inf-scan.

## 3. Inventory — aes_map/inventory.txt (736 lines) and cfg.txt; module cut (bytes by class)
| range | B | module | A/D/S |
|---|---:|---|---|
| FD9ECA | 306 | gemstart asm (Mshrink, Super, Line-F install, loop gem_main) | A |
| FD9FFC | 1392 | geminit: gem_main `FDA062`, #E inf `FDA408` | A |
| FDA56E | 2438 | gemgraf (gr_*/bb_* over gsx) | S |
| FDAF20 | 244 | inf scan helpers | S |
| FDB014 | 34816 | DESK | D |
| FE387C | 2096 | gemdosif asm: dsptch `FE387C`, spl `FE3890/9C/A4/AA`, gotopgm `FE38B0`, savestate `FE38D4`, switchto `FE3930`, tas `FE395C`, psetup `FE397A`, DOS glue, trap2 install `FE3C6E`/restore `FE3C62`, critic install `FE3C84` + handler `FE3CBE` (own stack `0x9446`, → eralert `FE768C`), trap#2 `FE3EA6`, userdef trampoline `FE3F3E` | A/S |
| FE3F5E | 906 | gemasync: EVB alloc/insert, ev_mwait `FE40B2`, iasync `FE40EC`, apret `FE41BC`, acancel `FE427A` | S |
| FE42E8 | 640 | accessory loader `FE4394` (`\*.ACC`, ≤6, cartridge `FED478/FED554`), per-ACC 2,226-B Malloc `FE44D4` | A |
| FE456A | 1454 | gemctrl: ctlmgr process `FE49D2` (= PD1 p_ldaddr), window-control hits `FE45A2` (switch `FEF7E2`/17), menu tracking `FE4908` | A |
| FE4B1A | 744 | gemdisp: forkq `FE4B1A`, disp_act `FE4B74`, mwait_act `FE4B9C`, forker `FE4BC6`, chkkbd `FE4CD6`, idle `FE4D68`, disp `FE4D9E` | S |
| FE4E02 | 2380 | geminput: tchange `FE4E02`, b_click `FE4F40`, b_delay `FE4FB0`, kchange `FE5180`, mchange `FE534C`, post_* | A/S |
| FE5750 | 786 | PD find `FE5750`, pd_get `FE57E0`, nameit `FE5856`, pd_start `FE5886`, pipe copy `FE58C0/FE5988` | S |
| FE5A62 | 826 | gemrlist (ORECT pool `0xB396`, free head `0xC824`) | A |
| FE5D9C | 2088 | gemsuper: dispatcher + arms, marshal `FE64E6`, entry `FE65AA` | A |
| FE65C4 | 720 | gemaplib | A/S |
| FE6894 | 1026 | gemevlib | S |
| FE6C98 | 1268 | gemfmalt (alert layout `FE6C98/FE6D84/FE6DF8`, fm_alert) | S |
| FE718E | 1568 | gemfmlib | S |
| FE7782 | 2900 | gemfslib (fs_input 1,350 B) | A |
| FE82D6 | 1194 | gemgrlib | S |
| FE8790 | 1206 | gemgsxif (gsx_ncode `FE87D2`, init `FE8808`, vex_* hookup, mouse on/off/form) | S |
| FE8C14 | 1608 | gemmnlib (mn_do `FE8D6E` 700 B) | A/S |
| FE9260 | 4724 | gemobjop + gemobed (ob_edit `FE9678` 1,942 B) | S |
| FEA028 | 1650 | gemoblib | S |
| FEA69C | 1498 | gemrslib | S |
| FEAC80 | 40 | gemsclib | A |
| FEACA8 | 1816 | gemshlib + sh_main `FEB0E6` + sh_cmd `FEB2FC` | A |
| FEB3C0 | 6030 | gemwmlib + gemwrect (w_* draw/redraw, wm_set 526 B, `FEC0CA` 720 B, `FEBA9C` 802 B) | S |
| FECB5A | 2128 | optimize (hand asm) | S |
| FED3BE | 184 | irq glue asm | A |
| FED478 | 4118 | cart + shell post-exit utils (format 1,232 B, copy 898 B) | A |
| FEE498 | 1054 | mouse-form save, ROM resource relocation (`FEE4DE` from gem_entry; `FEE5C8`), desk_alloc/free | A/S |
| FEE8C2 | 62 | Line-F handler | A |
Authorship: Alcyon C everywhere except gemstart, gemdosif, optimize, irq glue, the handler (hand asm, no `link`). Unreached
(dead, or data inside text): `FDAD74..FDADA3` (pointer table), `FDE0EE..FDE121`, `FE395C`, `FE8BDC..FE8BF3` (data),
`FECB8A..FECBD9` (tiny setters), `FED4B0`, ~1 KB total.

## 4. Data structures (GEMBSS `0x8900..0xC9FF`; snapshot values in ram.txt)
**THEGLO** (`a5 = 0x9C58` in gem_main; cleared `0x9C58..0xC66F` = 5,388 words at `0xFD9F78`, count from `0xFEE800`):
| addr (offset) | what | snapshot |
|---|---|---|
| `9C58` (+0) | UDA0 (PD0 shell/desk), super stack top `A3A2` | live frames `9FA5..A214` (MASKED) |
| `A3A2` (+74A) | UDA1 (PD1 SCRENMGR), top `A898` | live frames `A771..A7DE` (MASKED) |
| `A89C` (+C44) | UDA2 (spare PD2), top `AE5A` | unused |
| `AE5E` (+1206) | PD[3] × 184 = 56-B header + 128-B message pipe (+0x38) | PD0 name blank, PD1 `SCRENMGR` |
| `B086` (+142E) | CDA[3] × 36 | |
| `B0F2` (+149A) | EVB[15] × 28; free list `eul 0xC676` | PD0 holds 3 (`B1EE B20A B226`), PD1 3 (`B242 B25E B27A`) |
| `B296` (+163E) | fork queue 32 × {fcode, fdata}; head idx `9BF2`, tail `C6B0`, count `fpcnt C906` | empty |
| `B396..` | ORECT pool (12 B, linked) | |
| `BBAE`, `BC2E` | shell buffers (`C79E`→`BBAE`); `BC2E` = the DESKTOP.INF text (`#a000000…`) | populated |
| `C42E/C42F` | sh_cmd byte + tail | 0 |
| `C4AE` (+2856) | WINDOW[8] × 56 (+0 flags bit0 used, +2 owner PD, +6 kind, +40..46 slider pos/size) | only w0 = desktop, PD0, 0,11,320×189, tree `B74A` |
PD header: +0 p_link, +8 p_uda, +12 name[8], +20 p_cda, +24 p_ldaddr/basepage, +28 p_pid, +30 p_stat (0 run, 1 wait), +32 p_evbits,
+34 p_evwait, +36 p_evflg, +38 p_evlist, +54 p_qindex, +56 queue[128]. UDA: +0 in-super flag, +2..+57 d0–a5, +62 super sp,
+66 usp, +70 trap-time ssp. EVB: +0 next, +4/+8 dq links, +12 pd, +22 e_mask, +24 e_return. Accessory PD/UDA/CDA/5 EVBs =
one 2,226-B Malloc each, listed at `0xC6B2[]`, pids 3+ (`0xC682` count, `0xC680` static count ≤ 3).
**Scheduler globals:** rlr `C794` (NULL), nrl `C726` (= PD0 → PD1), drl `9C16` (0), indisp `C67E` (byte 1), forker-busy `C6AE`,
SR saves `8994/8996/8998`, dispatcher/savestate stack top `8C1A`, gl_recd `C79A`, record buffer `96EE`/count `9728`, timer
countdown `9492`/elapsed `948E` (0 = no ev_timer pending).
**Other AES globals:** boot stack `0x8900..0x898E` (gem_entry `sp := 0x898E`); `8C1E/8C22` DOS/trap glue return stashes, `8C26` old
critic, `8C2A` old trap #2, `8C32` userdef trampoline ptr, `8C36/8C3A` its sp save / 1 KB stack; `9446` crit-err stack top; `9466`
gsx pb; `947A/947E` saved USER_CUR/…; `9482/9486` irq sp saves; `948A` old USER_TIM (`0xFCA652` vdi_nop); `94F2` but/mot irq stack
top, `9552` timer irq stack top; `9560/9564` mouse-form save; `95BA/98C4/9706/9ABC` VDI intin/ptsin/intout/ptsout; `C7E0` contrl.
Interrupt vectors (VDI, snapshot): USER_BUT `0x2960`→`FED3BE`, USER_MOT `0x2968`→`FED3E4`, USER_TIM `0x2958`→`FED426`.
**The desk's globals:** `*(0xC6A6)` = `0x143B4` (19,094 B), `C82E`→`18E4A`, `C85E`→`1904A`, `C67A`→`193E2`; populated in the snapshot.
**The MASK, explained** (README labels corrected): `0x8930+0x2D0` = the DISPATCHER stack below `0x8C1A` (savestate's `lea 0x8c1a,sp`
at `0xFE3922`), not a generic ISP; `0x9488+0xC4` = the irq handlers' private stacks (`94F2`, `9552`) — timer fires every tick;
`0x9FA5`/`0xA19B` = PD0's UDA stack, `0xA771` = PD1's; `0xC7E1+7` = the AES's VDI contrl[0..3], rewritten on every `chkkbd` poll
(VDI 128, 33, 31) — so any AES case that calls the VDI must stage contrl itself; `0xF7FA2` below `_memtop`: not traced (unverified).

## 5. The hard parts for Tier 1
* **Blocking.** `ev_mwait FE40B2`: `rlr->p_evwait := mask; if !(p_evflg & mask) { p_stat := 1; dsptch(); } return p_evflg`.
  `dsptch FE387C`: `if (indisp) rts; else push SR,a0; jmp disp`. `disp FE4D9E`: savestate(rlr->uda) → `rlr = rlr->link` →
  mwait_act/disp_act → `do { forker(); idle(); } while (fpcnt)` → `gl_cda 97FA := rlr->p_cda` → `switchto(rlr->uda)` = restore
  regs + `rte` into that process. `idle FE4D68` loops `chkkbd(); drl → rlr` until `rlr || fpcnt`. So a caller resumes only when
  some fork function (from an irq or chkkbd) completes its EVB and moves its PD to `drl`. Test shapes: (a) disp with staged lists
  and 2 UDAs, run ends at the `rte` into a sentinel context; (b) "self-resume": stage `p_evflg & mask ≠ 0` or the snapshot's
  `indisp=1` so the block falls through; (c) slice at the Line-F call to `ev_multi`/`ev_button` for the interactive loops.
* **Never returns:** gem_entry/gem_main loop (`FD9FC4 bra`), sh_main, ctlmgr `FE49D2`, deskmain's event loop, disp/switchto,
  gotopgm, the idle loop (until an event), fm_do, mn_do `FE8D6E`, gr_dragbox/rubbox/watchbox/slidebox, fs_input.
* **Interrupt input:** button/motion/timer arrive through the VDI's USER_* vectors; the handlers switch to private stacks, `jsr` C
  (`b_click FE4F40`, `forkq(mchange,x,y)`, `forkq(tchange, elapsed)` + `b_delay(1)`), then chain (timer → `0x948A`). Keyboard is
  POLLED, not interrupt-driven (chkkbd from the idle loop; VDI 128 vq_key_s + 33 vsin_mode + 31 vsm_string sample → forkq(kchange)).
  forker calls each fork function by `jsr (a0)` on its ROM address (`FE4CBA`) → the candidate needs an address→C table (the
  `recreate_call_vector` pattern); `appl_trecord` recording rides inside forker (`FE4C1E..FE4CAA`, merges consecutive tchange).
  Direct-entry cases like the BIOS isr.S ones.
* **Desk accessories:** none in the snapshot (blank floppy; `C682=0`). The loader needs GEMDOS `Fsfirst "\*.ACC"` + `Pexec 3`
  (the RAM-disk staging exists) and runs them in user mode via gotopgm.
* **The snapshot state to poke per case:** `rlr` (`C794`, NULL!), `indisp` (`C67E`), the VDI arrays (contrl in the MASK), and for
  desk code the TPA heap block. `C794` NULL means functions reading `rlr->…` read the vector page — every unposed case is wrong.
* **Pure over data (easy):** optimize helpers; rect math; everyobj/get_par/ob_find/ob_offset/ob_add/ob_delete/ob_order (tree
  edits); rs_obfix/rs_gaddr/rs_saddr (over the live ROM-derived resources in RAM); gemrlist; alert layout (`FE6C98..FE6DF8`
  builds a tree, no drawing); wm_calc; fm_keybd/fm_button decision logic; merge_str/fmt_str/wildcmp. Use the snapshot's own trees
  (desktop `0xB74A`, menu/alert trees of the relocated resources) as seeded real data.
* **Stateful but finite:** ob_draw/ob_change (VDI pixels at `0xF8000`, mouse must be off or its save block `0x2850` perturbs), gemgraf,
  wm_open/close/set (redraw + message posting to pipes), mn_bar, fm_dial (blit save/restore), fm_alert (draws + fm_do = blocks).

## 6. Bands (approximate bytes; tests' staging)
* **band 0 — leaves (≈3.3 KB):** 0A optimize asm (2.1K, `.S` transcription, stage buffers) | 0B inf-scan (0.25K) | 0C gemrlist (0.8K,
  stage the ORECT pool) | mul_div.
* **band 1 — object/resource (≈5 KB):** everyobj/get_par/OB text (in optimize), ob_find/offset/add/delete/order (1.1K), ob_center,
  rs_obfix/gaddr/saddr/free + rsrc relocation `FEE4DE/FEE5C8` (1.5K+0.8K), sc_read/write. Stage: rlr, the resource globals; data = the
  snapshot's trees.
* **band 2 — graphics over the VDI (≈4.5 KB):** gsx2 + gsx_ncode + gemgsxif (1.2K), gemgraf (2.4K), mouse-form save (`$A000`), ob_draw/
  ob_change draw path, gr_movebox/grow helpers. The ORACLE runs the ROM VDI through `trap #2` → `FE3EA6` → `FC4EBC`; the CANDIDATE
  calls the reconstructed VDI directly. Stage the AES's VDI arrays; hide the mouse; compare the screen.
* **band 3 — form/menu/window (≈19 KB):** gemwmlib+wrect (6.0K), gemobed/objop (4.7K), gemfslib (2.9K), gemfmlib (1.6K), gemmnlib (1.6K),
  gemfmalt (1.3K), gemgrlib interactive (0.8K). Non-blocking pieces first; loops sliced at their ev_* call or run with a satisfied
  event.
* **band 4 — event/scheduler/input (≈9 KB):** gemdosif asm (2.1K: savestate/switchto/dsptch/gotopgm/psetup `.S`), gemdisp (0.75K),
  gemasync (0.9K), geminput (2.4K), gemevlib (1.0K), gemaplib (0.7K), PD/pipes (0.8K), irq glue (0.2K). Needs staged PD/UDA/EVB lists,
  the fork-function address map, direct irq entry, `rte`-terminated runs.
* **band 5 — application/shell/entry (≈8 KB):** gemsuper (2.1K: trap handler .S + marshal + arms), gemshlib+sh_main+sh_cmd (1.8K),
  accessory loader (0.6K), gemctrl ctlmgr (1.5K), geminit+gemstart (1.7K), desk_alloc/free, the Line-F handler (keep the RAM copy).
  gem_main from scratch writes all of THEGLO and Mallocs → compare against a pre-init image, not the snapshot.
* **band 6 — desktop (≈39 KB):** desk 34.8K (bindings 1.2K first, userdef 0.8K, INF read/write, dir windows, file ops via GEMDOS/RAM
  disk, menus `FE2344` switches `FEF700`/9 `FEF724`/19) + shell post-exit utils 4.1K (format/copy need FDC → XBIOS Flopfmt/Floprd;
  stage like the file system: hardware-free only through the BIOS door).
Cross-deps: band 1 ob_change/ob_draw → band 2; fm_*/mn_*/gr_* loops → band 4's ev_*; desk bindings → everything; the forker map
spans bands 4/2 (mchange draws the cursor via `FED412` → saved USER_CUR).

## 7. Tier-3 risks and decompile failures
* **Line-F overhead favours C** (~270 cycles/pair; §1.4). Rows that are one call wrapping a tiny body (arms, bindings, setters) will
  measure far below 1.0 — expected, not suspicious.
* **Hand asm is the risk:** optimize's string/rect loops (`move.b (a0)+,(a1)+; bne` style; `movem` rect loads `FECCA6`/`FECCBE`),
  savestate/switchto (movem of all regs, USP), the irq glue — transcribe as `.S` like the VDI did; a C port of rc_intersect/strcpy
  could be 1.2–1.5×.
* **Alcyon idioms:** first argument stored into the pre-reserved slot `move.w x,(sp)` (every call site), the extra saved register
  as arg slot, two switch forms (jump table `cmp #N-1; bhi; asl #2; adda.l #T; movea.l (a0); jmp (a0)` — 24 tables; search table
  `ext.l; movea.l #T,a0; moveq #N-1,d1; cmp.l (a0)+,d0; dbeq; movea.l 4(N-1)(a0),a0; jmp (a0)` with N values then N+1 labels, last
  = default — `FE72D8`/7, `FE95C0`/12, `FE98E0`/6), `dbmi` clear loops, muls-by-stride array indexing (184, 56, 36, 28, 24).
* **Hidden writes:** `0xCC44` (Line-F mask patch); caller's user stack (trap #2 saves 56 B below USP); `0x8C1E`/`0x95AE`/`0x95B2`/
  `0x8900` return stashes; `DOS_ERR 98EC`/`DOS_AX C918` on every GEMDOS call; forker sets `rlr := −1` while running forks
  (`FE4BDC`); aes_marshal writes addrout for op 112 from `0x944C`.
* **decomp.c in range:** 726 fns (my CFG 736: +arms/pointer-only fns), 150 clean, 526 with warnings, 50 FAIL ("Cannot properly adjust
  input varnodes": list in aes_map/decomp_status.txt); 473 "Control flow encountered bad instruction data" = the Line-F return word;
  ~355 Line-F calls mis-decoded as coprocessor ops (`psave` 95, `frestore` 53, `prestore` 52, `fsave` 26, `ftan*` 27, `fb*` 41 …)
  vs LineFResolve's 1,979 resolved (CFG: 2,230 call + 454 return words); `in_D0` 389 uses; "Treating indirect jump as call" 20 (the
  switch tables, forker, userdef, trap handler). The two dispatcher arms Ghidra could not make functions (`FE6216`, `FE63AE`) are
  just arms (73 shares its tail with 74 and calls through `jsr (a0)`; 108 calls wm_calc).
