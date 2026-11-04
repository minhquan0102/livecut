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
    RULER_H = 30

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scale = TimeScale()
        self._playhead = 0
        self._segments: list[tuple[int, int, str]] = []  # (start_ms, end_ms, màu)
        self._dragging = False
        self._hover_x: float | None = None
        self._last_seek = -1
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # --- API ---
    def set_duration(self, ms: int) -> None:
        self.scale.set_duration(ms)
        self._playhead = 0
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
    def _seek_to(self, x: float) -> None:
        ms = int(max(0, min(self.scale.x_to_ms(x), self.scale.duration_ms)))
        self._playhead = ms
        self.update()
        if ms != self._last_seek:
            self._last_seek = ms
            self.seekRequested.emit(ms)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.scale.duration_ms > 0:
            self._dragging = True
            self._seek_to(e.position().x())

    def mouseMoveEvent(self, e) -> None:
        self._hover_x = e.position().x()
        if self._dragging:
            self._seek_to(self._hover_x)
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        self._dragging = False

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
