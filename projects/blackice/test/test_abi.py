"""Pin the ctypes mirror of every engine struct against the compiler's own
layout.  Without this, a field added to GameState would silently shift every
other field the tests read and produce confident nonsense."""
import ctypes

import blackice


def test_struct_sizes(lib):
    assert ctypes.sizeof(blackice.Level) == lib.bi_sizeof_level()
    assert ctypes.sizeof(blackice.RenderColumn) == lib.bi_sizeof_rendercolumn()
    assert ctypes.sizeof(blackice.RenderScratch) == lib.bi_sizeof_renderscratch()
    assert ctypes.sizeof(blackice.RenderSprite) == lib.bi_sizeof_rendersprite()
    assert ctypes.sizeof(blackice.SpriteList) == lib.bi_sizeof_spritelist()
    assert ctypes.sizeof(blackice.Door) == lib.bi_sizeof_door()


def test_struct_offsets(lib):
    assert blackice.GameState.player.offset == lib.bi_offset_state_player()
    assert blackice.GameState.doors.offset == lib.bi_offset_state_doors()
    assert blackice.GameState.trace_milli.offset == lib.bi_offset_state_trace()
    assert blackice.RenderScratch.wall_dist.offset == lib.bi_offset_scratch_dist()
    assert blackice.RenderScratch.sprites.offset == lib.bi_offset_scratch_sprites()
    assert blackice.Level.cells.offset == lib.bi_offset_level_cells()


def test_the_mirror_covers_the_whole_engine_half_of_gamestate(lib):
    """game.h appends the game layer after trace_milli and promises never to
    interleave it.  Two things must hold: the game layer starts exactly where
    the named half ends - an inserted field would shift every offset the suite
    reads, and comparing sizeof alone would never notice - and the opaque tail
    is big enough that game_init, which writes the game layer, stays inside the
    ctypes buffer."""
    assert blackice.GameState.game_layer_tail.offset == lib.bi_offset_state_gamelayer()
    assert ctypes.sizeof(blackice.GameState) >= lib.bi_sizeof_gamestate(), \
        "the game layer outgrew GAME_LAYER_TAIL_BYTES"


def test_render_column_is_the_documented_68000_record():
    """render.h promises the asm a 12-byte record with every 16-bit field on an
    even offset.  That promise is only true if it is checked."""
    assert ctypes.sizeof(blackice.RenderColumn) == blackice.CONST["RENDER_COLUMN_BYTES"]
    for name in ("top", "rows", "tex_v", "tex_step"):
        assert getattr(blackice.RenderColumn, name).offset % 2 == 0
    assert blackice.RenderColumn.tex_id.offset == 0
    assert blackice.RenderColumn.tex_col.offset == 1
    assert blackice.RenderColumn.top.offset == 2
    assert blackice.RenderColumn.rows.offset == 4
    assert blackice.RenderColumn.tex_v.offset == 6
    assert blackice.RenderColumn.tex_step.offset == 8
    assert blackice.RenderColumn.band.offset == 10
    assert blackice.RenderColumn.side.offset == 11


def test_render_sprite_is_the_documented_68000_record():
    """sprite.h promises the asm this record.  The host build is wider because
    its pointers are, so each offset is shifted back by the pointer overhang
    rather than compared to the host's own sizeof."""
    overhang = 2 * (ctypes.sizeof(ctypes.c_void_p) - 4)
    expected = {"left": 8, "cols": 10, "top": 12, "rows": 14, "tex_u": 16,
                "tex_step_u": 18, "tex_step_v": 20, "dist": 22, "band": 24, "pad": 25}

    assert blackice.RenderSprite.texels.offset == 0
    assert blackice.RenderSprite.spans.offset == ctypes.sizeof(ctypes.c_void_p)
    for name, offset in expected.items():
        assert getattr(blackice.RenderSprite, name).offset - overhang == offset, name
    assert max(expected.values()) + 1 == blackice.CONST["RENDER_SPRITE_BYTES_68K"]
