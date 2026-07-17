"""tui.py — a quick interactive terminal editor for COURSES.DAT.

Left pane: the selected leg's course-record stream (scrollable). Right pane: a live
ASCII render of that leg's dashboard track-map (a real game asset, decoded from the
file bytes). Switching legs redraws the map; editing a record updates the list.

    python tui.py [PATH/TO/COURSES.DAT]

Keys:
    ↑/↓ or j/k   move selection        PgUp/PgDn   page      Home/End  first/last
    [ / ] or Tab change leg (0..4)
    m            set marker word (hex)  r  set rows (1..31)  t  toggle event bit (0x8000)
    w            save (writes a .bak first, never clobbers blind)
    q            quit (confirms if unsaved)

Pure-decode/render logic lives in course_format.py + mapview.py; this file is just the
curses shell, so it stays thin and the model stays testable without a terminal.
"""
from __future__ import annotations

import curses
from pathlib import Path

import course_format as cf
import mapview
import roadprofile
from course_file import CourseFile

DEFAULT_DAT = Path(__file__).resolve().parents[1] / "bin" / "COURSES.DAT"
RECORDS_PER_LEG = 1024          # full leg block (0x2000 / 8); scroll handles the length
DRIVE_MS = 90                   # auto-drive frame interval (view mode)
VIEW_CURVE_STEP = 0x40          # steering increment per +/- in view mode


class EditorTUI:
    def __init__(self, cffile: CourseFile):
        self.cf = cffile
        self.leg = 0
        self.sel = 0
        self.top = 0            # first visible record row (scroll)
        self.dirty = False
        self.msg = "loaded"
        self.mode = "rec"       # rec | map | road | view (live 3rd-person render)
        self.mx = self.my = 0   # map paint cursor (pixel coords, 0..127 x 0..39)
        self.pen = None         # None | "draw" | "erase": movement paints while a pen is down
        self.view_curve = 0     # live steering curve for the 3rd-person view
        self.driving = False    # view mode: auto-advance along the leg
        self._roadview = None   # lazily imported roadview module (needs the .so)
        self._roadview_err = None
        self.recs = self.cf.records(self.leg, RECORDS_PER_LEG)
        self.map_lines = mapview.render_ascii(mapview.decode_map(bytes(self.cf.data), self.leg))
        self.segs = roadprofile.road_profile(bytes(self.cf.data), self.leg, RECORDS_PER_LEG)

    # ---- state transitions ----
    def reload_leg(self) -> None:
        self.recs = self.cf.records(self.leg, RECORDS_PER_LEG)
        self.map_lines = mapview.render_ascii(mapview.decode_map(bytes(self.cf.data), self.leg))
        self.segs = roadprofile.road_profile(bytes(self.cf.data), self.leg, RECORDS_PER_LEG)

    def set_leg(self, leg: int) -> None:
        self.leg = max(0, min(cf.LEG_COUNT - 1, leg))
        self.sel = self.top = 0
        self.reload_leg()
        self.msg = f"leg {self.leg}"

    def move(self, delta: int) -> None:
        self.sel = max(0, min(len(self.recs) - 1, self.sel + delta))

    # ---- drawing ----
    def draw(self, scr) -> None:
        if self.mode == "map":
            self.draw_map(scr)
        elif self.mode == "road":
            self.draw_road(scr)
        elif self.mode == "view":
            self.draw_view(scr)
        else:
            self.draw_records(scr)

    def _roadview_mod(self):
        """Lazy-import roadview (needs the .so). Returns the module or None; caches the error."""
        if self._roadview is None and self._roadview_err is None:
            try:
                import roadview
                self._roadview = roadview
            except Exception as e:  # noqa: BLE001
                self._roadview_err = f"{type(e).__name__}: {e}"
        return self._roadview

    def draw_view(self, scr) -> None:
        scr.erase()
        h, w = scr.getmaxyx()
        drive = " DRIVE" if self.driving else ""
        header = (f" 3rd-person road — leg {self.leg}  seg {self.sel}/{len(self.segs)}  "
                  f"curve {self.view_curve:+#x}{drive}")
        scr.addnstr(0, 0, header.ljust(w - 1)[:w - 1], w - 1, curses.A_REVERSE)

        rv = self._roadview_mod()
        body_h = max(1, h - 3)
        if rv is None:
            scr.addnstr(2, 0, f"road render unavailable: {self._roadview_err}"[:w - 1], w - 1)
            scr.addnstr(3, 0, "build it: (cd recreate && make)"[:w - 1], w - 1)
        else:
            try:
                img = rv.render_frame_from_bytes(bytes(self.cf.data), self.leg, self.sel,
                                                 curve=self.view_curve)
                for i, ln in enumerate(rv.to_ascii_fit(img, w - 1, body_h)):
                    if 2 + i >= h - 1:
                        break
                    scr.addnstr(2 + i, 0, ln[:w - 1], w - 1)
            except Exception as e:  # noqa: BLE001
                scr.addnstr(2, 0, f"render failed: {e}"[:w - 1], w - 1)

        footer = (" [←→/hl] drive pos  [+/-] steer  [space] auto-drive  [P] PNG  "
                  "[ [ ] ] leg  [d] records  [q] quit")
        pad = max(0, (w - 1) - len(footer))
        bar = (self.msg + "   ")[:pad].ljust(pad) + footer
        scr.addnstr(h - 1, 0, bar, w - 1, curses.A_REVERSE)
        scr.refresh()

    def draw_records(self, scr) -> None:
        scr.erase()
        h, w = scr.getmaxyx()
        dirty = " *modified*" if self.dirty else ""
        header = f" BuggyBoy course editor — {self._name()} [leg {self.leg}/{cf.LEG_COUNT}]{dirty}"
        scr.addnstr(0, 0, header.ljust(w), w, curses.A_REVERSE)

        map_w = max(map((lambda s: len(s)), self.map_lines), default=0)
        list_w = max(20, w - map_w - 3)
        body_h = h - 3

        # scroll to keep selection visible
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + body_h:
            self.top = self.sel - body_h + 1

        # record list
        for i in range(body_h):
            idx = self.top + i
            if idx >= len(self.recs):
                break
            r = self.recs[idx]
            ev = r.classify_marker()
            mk = f"{r.marker:04x}" if r.marker_is_event else "    "
            line = (f"{idx:>4} m:{r.select_mask:04x} r{r.row_count:<2} "
                    f"M:{mk} {ev:<11} {r.payload.hex(' ')}")
            attr = curses.A_REVERSE if idx == self.sel else curses.A_NORMAL
            scr.addnstr(2 + i, 0, line.ljust(list_w)[:list_w], list_w, attr)

        # map pane (right)
        mx = list_w + 2
        scr.addnstr(1, mx, f"leg {self.leg} track map".center(map_w)[:max(0, w - mx)],
                    max(0, w - mx), curses.A_BOLD)
        for i, ml in enumerate(self.map_lines):
            if 2 + i >= h - 1:
                break
            scr.addnstr(2 + i, mx, ml[:max(0, w - mx)], max(0, w - mx))

        # footer + status: never write the screen's bottom-right cell (curses raises ERR),
        # so cap the last line at w-1 and clamp padding when the terminal is narrow.
        footer = " [↑↓/jk] move  [ [ ] /Tab] leg  [m]arker [r]ows [t]oggle  [g]map [d]road [v]iew  [w]rite  [q]uit"
        pad = max(0, (w - 1) - len(footer))
        bar = (self.msg + "   ")[:pad].ljust(pad) + footer
        scr.addnstr(h - 1, 0, bar, w - 1, curses.A_REVERSE)
        scr.refresh()

    def draw_map(self, scr) -> None:
        scr.erase()
        h, w = scr.getmaxyx()
        on = self.cf.get_map_pixel(self.leg, self.mx, self.my)
        pen = f"  PEN:{self.pen}" if self.pen else ""
        dirty = " *modified*" if self.dirty else ""
        header = (f" PAINT course shape — leg {self.leg}  cursor ({self.mx:>3},{self.my:>2}) "
                  f"{'TRACK' if on else 'field'}{pen}{dirty}")
        scr.addnstr(0, 0, header.ljust(w - 1)[:w - 1], w - 1, curses.A_REVERSE)

        vw, vh = max(1, w - 1), max(1, h - 3)
        x0 = min(max(0, self.mx - vw // 2), max(0, mapview.MAP_W - vw))
        y0 = min(max(0, self.my - vh // 2), max(0, mapview.MAP_H - vh))
        grid = mapview.decode_map(bytes(self.cf.data), self.leg)   # live: decoded from bytes
        for i, ml in enumerate(mapview.window(grid, x0, y0, vw, vh)):
            scr.addnstr(2 + i, 0, ml, vw)
        # highlight the cursor cell over whatever it sits on
        cy, cx = 2 + (self.my - y0), self.mx - x0
        if 2 <= cy < h - 1 and 0 <= cx < vw:
            scr.addnstr(cy, cx, "+" if on else "x", 1, curses.A_REVERSE)

        footer = (" [↑↓←→/hjkl] move  [space] toggle  [p] draw-pen  [e] erase-pen  "
                  "[ [ ] ] leg  [g] records  [w]rite  [q]uit")
        pad = max(0, (w - 1) - len(footer))
        bar = (self.msg + "   ")[:pad].ljust(pad) + footer
        scr.addnstr(h - 1, 0, bar, w - 1, curses.A_REVERSE)
        scr.refresh()

    def draw_road(self, scr) -> None:
        scr.erase()
        h, w = scr.getmaxyx()
        s = self.segs[self.sel] if self.sel < len(self.segs) else None
        info = (f"seg {self.sel}  slope {s.slope:+d}  rows {s.rows}  elev {s.elev1}"
                if s else "no segment")
        dirty = " *modified*" if self.dirty else ""
        header = f" ROAD elevation (side view) — leg {self.leg}  {info}{dirty}"
        scr.addnstr(0, 0, header.ljust(w - 1)[:w - 1], w - 1, curses.A_REVERSE)

        vw, vh = max(1, w - 1), max(3, h - 3)
        x0 = min(max(0, self.sel - vw // 2), max(0, len(self.segs) - vw))
        for i, ml in enumerate(roadprofile.render_profile(self.segs, vw, vh, x0, self.sel)):
            scr.addnstr(2 + i, 0, ml, vw)

        footer = (" [←→/hl] segment  [+/-] slope  [P] render 3rd-person PNG  [ [ ] ] leg  "
                  "[g] map [d] records  [w]rite  [q]uit")
        pad = max(0, (w - 1) - len(footer))
        bar = (self.msg + "   ")[:pad].ljust(pad) + footer
        scr.addnstr(h - 1, 0, bar, w - 1, curses.A_REVERSE)
        scr.refresh()

    def _name(self) -> str:
        return self.cf.path.name if self.cf.path else "COURSES.DAT"

    # ---- editing ----
    def _prompt(self, scr, label: str) -> str | None:
        h, w = scr.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        scr.addnstr(h - 1, 0, (label + " ").ljust(w - 1), w - 1, curses.A_REVERSE)
        scr.move(h - 1, min(len(label) + 1, w - 1))
        try:
            s = scr.getstr(h - 1, len(label) + 1, 16).decode(errors="ignore").strip()
        except Exception:
            s = ""
        curses.noecho()
        curses.curs_set(0)
        return s or None

    def edit_marker(self, scr) -> None:
        s = self._prompt(scr, f"marker word for #{self.sel} (hex, e.g. 8800):")
        if s is None:
            return
        try:
            word = int(s, 16) & 0xFFFF
        except ValueError:
            self.msg = "not a hex word"
            return
        self.cf.set_marker(self.leg, self.sel, word)
        self._after_edit(f"#{self.sel} marker := 0x{word:04x}")

    def edit_rows(self, scr) -> None:
        s = self._prompt(scr, f"rows for #{self.sel} (1..31):")
        if s is None:
            return
        try:
            rows = max(1, min(31, int(s)))
        except ValueError:
            self.msg = "not a number"
            return
        self.cf.set_control(self.leg, self.sel, rows, self.recs[self.sel].decay_seed)
        self._after_edit(f"#{self.sel} rows := {rows}")

    def toggle_event(self) -> None:
        r = self.recs[self.sel]
        self.cf.set_marker(self.leg, self.sel, r.marker ^ 0x8000)
        self._after_edit(f"#{self.sel} event bit toggled")

    def adjust_slope(self, delta: int) -> None:
        """Raise/lower the selected segment's elevation slope (clamped to -3..+4)."""
        if self.sel >= len(self.segs):
            return
        seg = self.segs[self.sel]
        slope = max(-3, min(4, seg.slope + delta))
        if slope != seg.slope:
            self.cf.set_control(self.leg, self.sel, seg.rows, slope)
            self._after_edit(f"seg {self.sel} slope := {slope:+d}")

    def render_road_png(self) -> None:
        """Render the current leg/segment as a third-person PNG via the verified renderer.

        Uses the in-memory (possibly edited) bytes, so slope edits show up. Lazy-imported so
        the TUI never hard-depends on the built .so; failures land in the status line.
        """
        try:
            rv = self._roadview_mod()
            if rv is None:
                self.msg = f"roadview unavailable: {self._roadview_err}"
                return
            img = rv.render_frame_from_bytes(bytes(self.cf.data), self.leg, self.sel,
                                             curve=self.view_curve)
            out = rv.default_out() / f"road_leg{self.leg}_seg{self.sel}.png"
            rv.write_png(img, out)
            self.msg = f"wrote {out}"
        except Exception as e:  # noqa: BLE001 - surface any staging/.so failure in the status line
            self.msg = f"render failed: {e}"

    def _after_edit(self, msg: str) -> None:
        self.dirty = True
        self.reload_leg()
        self.msg = msg

    # ---- map painting ----
    def move_cursor(self, dx: int, dy: int) -> None:
        self.mx = max(0, min(mapview.MAP_W - 1, self.mx + dx))
        self.my = max(0, min(mapview.MAP_H - 1, self.my + dy))
        if self.pen == "draw":
            self._paint(True)
        elif self.pen == "erase":
            self._paint(False)

    def _paint(self, on: bool) -> None:
        self.cf.set_map_pixel(self.leg, self.mx, self.my, on)
        self.dirty = True

    def toggle_pixel(self) -> None:
        state = self.cf.toggle_map_pixel(self.leg, self.mx, self.my)
        self.dirty = True
        self.msg = f"pixel ({self.mx},{self.my}) := {'track' if state else 'field'}"

    def set_pen(self, pen: str | None) -> None:
        self.pen = None if self.pen == pen else pen   # toggle; only one pen at a time
        self.msg = f"pen: {self.pen}" if self.pen else "pen up"
        if self.pen:                                   # paint the current cell on pen-down
            self._paint(self.pen == "draw")

    def save(self) -> None:
        try:
            dst = self.cf.save()
        except Exception as e:  # noqa: BLE001 - surface any I/O failure in the status line
            self.msg = f"save failed: {e}"
            return
        self.dirty = False
        self.msg = f"wrote {dst.name} (backup {dst.name}.bak)"

    # ---- main loop ----
    def run(self, scr) -> None:
        curses.curs_set(0)
        scr.keypad(True)
        while True:
            self.draw(scr)
            # auto-drive: in view mode with driving on, poll so getch times out and we advance
            scr.timeout(DRIVE_MS if (self.mode == "view" and self.driving) else -1)
            c = scr.getch()
            if c == -1:                                   # timeout tick -> drive forward
                if self.mode == "view" and self.driving:
                    self.move_forward()
                continue
            # shared keys (all modes)
            if c in (ord("q"), 27):
                if not self.dirty or self._prompt(scr, "unsaved changes — quit? (y/N):") in ("y", "Y"):
                    return
            elif c == ord("w"):
                self.save()
            elif c == ord("g"):
                self.mode = "rec" if self.mode == "map" else "map"
                self.pen = None
                self.msg = "paint mode" if self.mode == "map" else "record mode"
            elif c == ord("d"):
                self.mode = "rec" if self.mode == "road" else "road"
                self.pen = None
                self.msg = "road mode" if self.mode == "road" else "record mode"
            elif c == ord("v"):
                self.mode = "rec" if self.mode == "view" else "view"
                self.driving = False
                self.msg = "3rd-person view" if self.mode == "view" else "record mode"
            elif c == ord("]"):
                self.set_leg(self.leg + 1)
            elif c == ord("["):
                self.set_leg(self.leg - 1)
            elif self.mode == "map":
                self._key_map(c)
            elif self.mode == "road":
                self._key_road(c)
            elif self.mode == "view":
                self._key_view(c)
            else:
                self._key_records(c, scr)

    def move_forward(self) -> None:
        """Advance one segment along the leg, wrapping at the end (auto-drive)."""
        self.sel = self.sel + 1 if self.sel + 1 < len(self.segs) else 0

    def _key_view(self, c: int) -> None:
        if c in (curses.KEY_RIGHT, ord("l")):
            self.move(1)
        elif c in (curses.KEY_LEFT, ord("h")):
            self.move(-1)
        elif c in (ord("+"), ord("=")):
            self.view_curve = min(0x400, self.view_curve + VIEW_CURVE_STEP)
        elif c in (ord("-"), ord("_")):
            self.view_curve = max(-0x400, self.view_curve - VIEW_CURVE_STEP)
        elif c == ord(" "):
            self.driving = not self.driving
            self.msg = "driving" if self.driving else "paused"
        elif c == ord("P"):
            self.render_road_png()

    def _key_records(self, c: int, scr) -> None:
        if c in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif c in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif c == curses.KEY_NPAGE:
            self.move(20)
        elif c == curses.KEY_PPAGE:
            self.move(-20)
        elif c == curses.KEY_HOME:
            self.sel = 0
        elif c == curses.KEY_END:
            self.sel = len(self.recs) - 1
        elif c == ord("\t"):
            self.set_leg(self.leg + 1)
        elif c == ord("m"):
            self.edit_marker(scr)
        elif c == ord("r"):
            self.edit_rows(scr)
        elif c == ord("t"):
            self.toggle_event()

    def _key_map(self, c: int) -> None:
        if c in (curses.KEY_DOWN, ord("j")):
            self.move_cursor(0, 1)
        elif c in (curses.KEY_UP, ord("k")):
            self.move_cursor(0, -1)
        elif c in (curses.KEY_LEFT, ord("h")):
            self.move_cursor(-1, 0)
        elif c in (curses.KEY_RIGHT, ord("l")):
            self.move_cursor(1, 0)
        elif c == ord(" "):
            self.toggle_pixel()
        elif c == ord("p"):
            self.set_pen("draw")
        elif c == ord("e"):
            self.set_pen("erase")

    def _key_road(self, c: int) -> None:
        if c in (curses.KEY_RIGHT, ord("l")):
            self.move(1)
        elif c in (curses.KEY_LEFT, ord("h")):
            self.move(-1)
        elif c == curses.KEY_NPAGE:
            self.move(20)
        elif c == curses.KEY_PPAGE:
            self.move(-20)
        elif c in (ord("+"), ord("=")):
            self.adjust_slope(1)
        elif c in (ord("-"), ord("_")):
            self.adjust_slope(-1)
        elif c == ord("P"):
            self.render_road_png()


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else DEFAULT_DAT
    if not path.exists():
        print(f"not found: {path}")
        return 1
    app = EditorTUI(CourseFile.load(path))
    curses.wrapper(app.run)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
