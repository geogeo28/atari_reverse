"""How a case enters a TOS ROM function: the frame the XBIOS dispatcher leaves behind.

Every BIOS/XBIOS routine is reached through the dispatcher at `$fc07fc`, which pops the function
number and does `suba.l a5,a5` — so a routine runs with A5 = 0 and reaches low RAM and the I/O page
through 16-bit displacements off it, and its arguments are the words the CALLER pushed, still on the
stack above the return address.

`emu.run` forces A7 to `emu.STACK_TOP` and plants the sentinel return address there, which is
exactly the frame a `jsr` leaves: the first argument word is at 4(A7). Spelt once here because two
files need it — the batteries that stage arguments, and `test_boot_snapshot.py`, which must know
which bytes of the stack band a case owns.
"""
# `emu` comes THROUGH the shim rather than as a bare `import emu`: the kit's oracle directory only
# reaches sys.path once `harness` has bound the project, so importing it first fails.
import harness
from harness import emu

# The first argument slot: one longword of return address above A7, as the dispatcher's caller left
# it. `harness.SENTINEL_SLOT_BYTES` is the kit's name for that longword, and sharing the spelling is
# what stops the harness's stray-write guard and a case's pokes disagreeing about which bytes of the
# stack band the case staged.
FIRST_ARG = emu.STACK_TOP + harness.SENTINEL_SLOT_BYTES
