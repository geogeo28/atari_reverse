"""test_sprite.py — remaster buggy/foreground sprite equivalence vs recreate's verified cores.

draw_fg_sprite (the foreground buggy) and draw_buggy (the player car body + lean overlay + lower
body) blit masked 4-plane sprites into the draw buffer. Each case stages a realistic mid-race frame
(road + ground already drawn), pokes the dynamic sprite scalars to exercise a branch, runs recreate's
g_draw_fg_sprite / g_draw_buggy as the reference and the matching remaster core on the same
background, and asserts the whole framebuffer is byte-identical — the strictest equivalence contract.

The pokes drive the real asset tables through their branches: upright (flag==0) vs leaning (flag!=0)
body frames, the spin-abort gate, and the lean-overlay / lower-body sub-draws.
"""
import adapter
import equiv
import pytest

CASES = [(0, 60), (1, 90), (4, 60)]

# draw_fg_sprite branches: normal draw, a suppressed draw, and the two spin-abort gates (a hard
# curve while spin_state is negative arms the counter and skips the draw). spin_state is a byte at
# A_sp_spin_state, so the poke's HIGH byte lands there (_w16 writes big-endian).
FG_POKES = [
    {},                                                                 # normal foreground draw (frame 0)
    {adapter.A_sp_anim_frame: 8},                                       # a later fg frame the crash script picks
    {adapter.A_sp_anim_frame: 16},                                      # and another
    {adapter.A_sp_sprite_suppress: 1},                                  # suppressed -> no draw
    {adapter.A_sp_spin_state: 0xff00, adapter.A_sp_road_curve: 0x0200}, # right-curve spin abort
    {adapter.A_sp_spin_state: 0x8000, adapter.A_sp_road_curve: 0xfe00}, # left-curve spin abort
]
# The anim_frame pokes above are real rec[5] values (0, 8, 16 are the only frames the crash script
# emits, observed over legs 0/1/4 slalom drives): the crash/jump script advances the foreground
# sprite through them, which is the state apply_player's fan-out has to reach (test_leg_drive pins it).

# draw_buggy branches: a spread of leans covering flag==0 (upright, WHEELS_CELLS) and flag!=0
# (leaning, BUGGY_BODY_CELLS inline blit), plus crash/pitch/skid position offsets, and one case that
# opens the lower-body draw gate (buggy_draw_flag + all suppressors clear).
BUGGY_POKES = [
    {adapter.A_sp_lean: 0},
    {adapter.A_sp_lean: 5},
    {adapter.A_sp_lean: 9, adapter.A_sp_crash_disp: 0xa0, adapter.A_sp_skid: 8},
    {adapter.A_sp_lean: 3, adapter.A_sp_pitch: 0x20, adapter.A_sp_skid: 0xfff8},
    {adapter.A_sp_lean: 36},                                            # flag!=0 leaning frame
    {adapter.A_sp_lean: 41},                                            # flag!=0 leaning frame
    {adapter.A_sp_lean: 2, adapter.A_sp_speed_raw: 0x4000,              # lean-overlay frame advance
     adapter.A_sp_lean_accum: 0, adapter.A_sp_lean_frame: 8},
    {adapter.A_sp_lean: 2, adapter.A_sp_buggy_draw_flag: 1,             # lower body draws
     adapter.A_sp_buggy_gate: 0, adapter.A_sp_sprite_suppress: 0,
     adapter.A_sp_collision_lock: 0, adapter.A_sp_spin_reset: 0,
     adapter.A_sp_spin_counter: 0, adapter.A_sp_wheel_pos: 0},
]


@pytest.mark.parametrize("leg,warmup", CASES)
@pytest.mark.parametrize("pokes", FG_POKES)
def test_draw_fg_sprite_matches(leg, warmup, pokes, capsys):
    lib = equiv._lib()
    image = equiv.sprite_background(leg=leg, warmup=warmup, pokes=pokes)
    diff = equiv.compare_sprite(lib, image, "g_draw_fg_sprite",
                                lib.rm_draw_fg_sprite, adapter.sprite_state)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} pokes={pokes}: diff={diff}")
    assert diff == 0, f"draw_fg_sprite differs in {diff} bytes (leg={leg}, pokes={pokes})"


@pytest.mark.parametrize("leg,warmup", CASES)
@pytest.mark.parametrize("pokes", BUGGY_POKES)
def test_draw_buggy_matches(leg, warmup, pokes, capsys):
    lib = equiv._lib()
    image = equiv.sprite_background(leg=leg, warmup=warmup, pokes=pokes)
    diff = equiv.compare_sprite(lib, image, "g_draw_buggy",
                                lib.rm_draw_buggy, adapter.sprite_state)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} pokes={pokes}: diff={diff}")
    assert diff == 0, f"draw_buggy differs in {diff} bytes (leg={leg}, pokes={pokes})"
