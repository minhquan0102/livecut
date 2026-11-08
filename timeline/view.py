"""Widget vẽ timeline: thước thời gian, đoạn đã chọn, playhead; zoom và cuộn."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ui.theme import P
from utils.timecode import format_clock
from .scale import TimeScale, pick_tick_step


class TimelineView(QWidget):
    seekRequested = Signal(int)
    viewChanged = Signal()
    selectionChanged = Signal()      # người dùng kéo xong / chỉnh tay nắm
    RULER_H = 30
    HANDLE_PX = 7                    # vùng bắt chuột quanh tay nắm
    MIN_SEL_MS = 100

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scale = TimeScale()
        self._playhead = 0
        self._segments: list[tuple[int, int, str]] = []  # (start_ms, end_ms, màu)
        self._dragging = False
        self._hover_x: float | None = None
        self._last_seek = -1
        self._sel: tuple[int, int] | None = None     # khoảng đang chọn (start_ms, end_ms)
        self._mark_in: int | None = None
        self._drag_kind = ""                         # "", "scrub", "new", "start", "end"
        self._anchor_ms = 0
        self._press_x = 0.0
        self._moved = False
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    # --- API ---
    def set_duration(self, ms: int) -> None:
        self.scale.set_duration(ms)
        self._playhead = 0
        self._sel = self._mark_in = None
        self.update()
        self.viewChanged.emit()

    def set_playhead(self, ms: int, follow: bool = False) -> None:
        self._playhead = max(0, min(int(ms), self.scale.duration_ms))
        if follow:
            self.scale.ensure_visible(self._playhead)
            self.viewChanged.emit()
        self.update()

    def set_segments(self, segments: list[tuple[int, int, str]]) -> None:
        self._segments = list(segments)
        self.update()

    def selection(self) -> tuple[int, int] | None:
        return self._sel

    def set_selection(self, sel: tuple[int, int] | None, reveal: bool = False) -> None:
        if sel is not None:
            d = self.scale.duration_ms
            a, b = sorted((max(0, int(sel[0])), int(sel[1])))
            if d > 0:
                a, b = min(a, d), min(b, d)
            sel = (a, b) if b - a >= 1 else None
        self._sel = sel
        if reveal and sel is not None:
            self.scale.ensure_visible(sel[0])
            self.viewChanged.emit()
        self.update()

    def set_mark_in(self, ms: int | None) -> None:
        self._mark_in = ms
        self.update()

    def zoom(self, factor: float) -> None:
        self.scale.zoom_at(self.width() / 2, factor)
        self.update()
        self.viewChanged.emit()

    def fit(self) -> None:
        self.scale.fit()
        self.update()
        self.viewChanged.emit()

    # --- vẽ ---
    def resizeEvent(self, e) -> None:
        self.scale.set_width(self.width())
        self.update()
        self.viewChanged.emit()
        super().resizeEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, w, h = self.scale, self.width(), self.height()
        p.fillRect(self.rect(), QColor(P["panel"]))
        track = QRectF(0, self.RULER_H, w, h - self.RULER_H)
        p.fillRect(track, QColor(P["bg"]))
        if s.duration_ms <= 0:
            p.setPen(QColor(P["faint"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Nhập video để hiển thị timeline")
            return
        self._paint_ruler(p, w)
        top, bottom = self.RULER_H + 12, h - 14
        for start, end, color in self._segments:
            x1, x2 = s.ms_to_x(start), s.ms_to_x(end)
            if x2 < 0 or x1 > w:
                continue
            c = QColor(color)
            fill = QColor(c)
            fill.setAlpha(110)
            p.setPen(QPen(c, 1.2))
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(max(x1, -4), top, max(x2 - x1, 3), bottom - top), 5, 5)
        self._paint_selection(p, top, bottom, h)
        if self._hover_x is not None and not self._dragging:
            p.setPen(QPen(QColor(P["border_strong"]), 1))
            p.drawLine(QPointF(self._hover_x, self.RULER_H), QPointF(self._hover_x, h))
        px = s.ms_to_x(self._playhead)
        if -8 <= px <= w + 8:
            acc = QColor(P["accent"])
            p.setPen(QPen(acc, 1.5))
            p.drawLine(QPointF(px, 0), QPointF(px, h))
            p.setPen(Qt.NoPen)
            p.setBrush(acc)
            p.drawPolygon(QPolygonF([QPointF(px - 6, 0), QPointF(px + 6, 0), QPointF(px, 10)]))

    def _paint_selection(self, p: QPainter, top: float, bottom: float, h: int) -> None:
        s = self.scale
        if self._mark_in is not None:
            x = s.ms_to_x(self._mark_in)
            c = QColor(P["warn"])
            p.setPen(QPen(c, 2, Qt.DashLine))
            p.drawLine(QPointF(x, self.RULER_H), QPointF(x, h))
            p.setPen(c)
            p.drawText(QRectF(x + 4, self.RULER_H + 1, 40, 12), Qt.AlignLeft | Qt.AlignVCenter, "IN")
        if self._sel is None:
            return
        x1, x2 = s.ms_to_x(self._sel[0]), s.ms_to_x(self._sel[1])
        acc = QColor(P["accent"])
        fill = QColor(acc)
        fill.setAlpha(60)
        p.setPen(QPen(acc, 2))
        p.setBrush(fill)
        p.drawRect(QRectF(x1, self.RULER_H + 2, max(x2 - x1, 1), h - self.RULER_H - 4))
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        for x in (x1, x2):                      # tay nắm hai đầu
            p.drawRoundedRect(QRectF(x - 4, top, 8, bottom - top), 3, 3)
        p.setPen(QColor(P["on_accent"]))
        for x in (x1, x2):
            mid = (top + bottom) / 2
            p.drawLine(QPointF(x - 1, mid - 6), QPointF(x - 1, mid + 6))
            p.drawLine(QPointF(x + 1, mid - 6), QPointF(x + 1, mid + 6))

    def _paint_ruler(self, p: QPainter, w: int) -> None:
        s = self.scale
        step = pick_tick_step(s.ms_per_px)
        minor = max(step // 5, 1)
        end = min(s.x_to_ms(w), s.duration_ms)
        p.setPen(QPen(QColor(P["border"]), 1))
        p.drawLine(0, self.RULER_H, w, self.RULER_H)
        t = int(s.start_ms // step) * step
        while t <= end:
            x = s.ms_to_x(t)
            p.setPen(QPen(QColor(P["border_strong"]), 1))
            p.drawLine(QPointF(x, self.RULER_H - 12), QPointF(x, self.RULER_H))
            label = format_clock(t) if step >= 1000 else f"{format_clock(t)}.{t % 1000:03d}"
            p.setPen(QColor(P["muted"]))
            p.drawText(QRectF(x + 4, 4, 90, 18), Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setPen(QPen(QColor(P["border"]), 1))
            for k in range(1, 5):
                tm = t + k * minor
                if tm <= s.duration_ms:
                    xm = s.ms_to_x(tm)
                    p.drawLine(QPointF(xm, self.RULER_H - 5), QPointF(xm, self.RULER_H))
            t += step

    # --- chuột ---
    def _clamp_ms(self, x: float) -> int:
        return int(max(0, min(self.scale.x_to_ms(x), self.scale.duration_ms)))

    def _seek_to(self, x: float) -> None:
        ms = self._clamp_ms(x)
        self._playhead = ms
        self.update()
        if ms != self._last_seek:
            self._last_seek = ms
            self.seekRequested.emit(ms)

    def _handle_at(self, x: float) -> str:
        if self._sel is None:
            return ""
        dx = {k: abs(x - self.scale.ms_to_x(v)) for k, v in zip(("start", "end"), self._sel)}
        k = min(dx, key=dx.get)
        return k if dx[k] <= self.HANDLE_PX else ""

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self.scale.duration_ms <= 0:
            return
        x, y = e.position().x(), e.position().y()
        self._press_x, self._moved = x, False
        handle = self._handle_at(x) if y > self.RULER_H else ""
        if handle:
            self._drag_kind = handle
        elif y <= self.RULER_H:                 # kéo trên thước = tua
            self._drag_kind = "scrub"
            self._dragging = True
            self._seek_to(x)
        else:                                   # kéo trong vùng đoạn = chọn khoảng mới; bấm nhẹ = tua
            self._drag_kind = "new"
            self._anchor_ms = self._clamp_ms(x)
            self._dragging = True

    def mouseMoveEvent(self, e) -> None:
        x = e.position().x()
        self._hover_x = x
        k = self._drag_kind
        if k == "scrub":
            self._seek_to(x)
        elif k in ("start", "end") and self._sel is not None:
            ms, (a, b) = self._clamp_ms(x), self._sel
            self._moved = True
            self._sel = (min(ms, b - self.MIN_SEL_MS), b) if k == "start" else (a, max(ms, a + self.MIN_SEL_MS))
        elif k == "new":
            if not self._moved and abs(x - self._press_x) < 4:
                return
            self._moved = True
            ms = self._clamp_ms(x)
            a, b = sorted((self._anchor_ms, ms))
            self._sel = (a, max(b, a + self.MIN_SEL_MS)) if b - a >= 1 else None
        else:
            self.setCursor(Qt.SizeHorCursor if (e.position().y() > self.RULER_H and self._handle_at(x))
                           else Qt.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        k, moved = self._drag_kind, self._moved
        self._drag_kind, self._dragging, self._moved = "", False, False
        if k == "new" and not moved:
            self._seek_to(self._press_x)
        elif k in ("new", "start", "end") and moved:
            self.selectionChanged.emit()

    def leaveEvent(self, e) -> None:
        self._hover_x = None
        self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e) -> None:
        if self.scale.duration_ms <= 0:
            return
        dy, dx = e.angleDelta().y(), e.angleDelta().x()
        if e.modifiers() & Qt.ControlModifier:
            self.scale.zoom_at(e.position().x(), 0.8 ** (dy / 120.0))
        else:
            self.scale.pan_px(-(dy or dx) / 120.0 * 80)
        self.update()
        self.viewChanged.emit()
        e.accept()
