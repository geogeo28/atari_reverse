| autoprg.S — THE TEST AUTO PROGRAM boot B4's AUTO disks hold (`test/boot_launch.py`, built by
| `tools/accessory_disk.py`'s own `build`, linked by `acc.ld`, wrapped by `atari/mkprg.py`): a GEMDOS program that
| terminates at once — `Pterm0`. What the boot's AUTO runner does with it is the subject, not the program: found by
| Fsfirst / Fsnext in `\AUTO`, loaded and run by Pexec(0) (which clears the whole TPA first), and gone again.

| `clr.w -(sp)` pushes Pterm0's function number, 0 — the whole program four bytes, a length the link pads nothing to.

    .text
    .globl  _start
_start:
    clr.w   -(%sp)                      | Pterm0: the process ends, its return code 0
    trap    #1
