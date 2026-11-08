"""Khung kéo được trên hình video để chọn vùng giữ lại (giống CapCut)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from export.framing import MAX_ZOOM, crop_rect_f
from .theme import P


class FrameEditor(QWidget):
    """Hiện một khung hình của video, phủ mờ phần bị cắt bỏ. Kéo chuột để di chuyển vùng giữ lại,
    cuộn chuột để thu phóng. Tọa độ lưu dạng 0..1 theo video gốc nên không phụ thuộc kích thước hình."""
    zoomChanged = Signal(float)
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setCursor(Qt.OpenHandCursor)
        self._pix: QPixmap | None = None
        self._aspect: tuple[int, int] | None = None
        self._cx, self._cy, self._zoom = 0.5, 0.5, 1.0
        self._grab: tuple[float, float] | None = None

    # --- API ---
    def set_pixmap(self, pm: QPixmap | None) -> None:
        self._pix = pm if (pm is not None and not pm.isNull()) else None
        self.update()

    def has_image(self) -> bool:
        return self._pix is not None

    def set_aspect(self, aspect: tuple[int, int] | None) -> None:
        self._aspect = aspect
        self._clamp()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = min(max(1.0, zoom), MAX_ZOOM)
        self._clamp()
        self.update()
        self.changed.emit()

    def reset(self) -> None:
        self._cx, self._cy, self._zoom = 0.5, 0.5, 1.0
        self.zoomChanged.emit(self._zoom)
        self.update()
        self.changed.emit()

    def center(self) -> tuple[float, float]:
        return self._cx, self._cy

    def zoom(self) -> float:
        return self._zoom

    # --- hình học ---
    def _image_rect(self) -> QRectF:
        if self._pix is None:
            return QRectF()
        avail = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        pw, ph = self._pix.width(), self._pix.height()
        s = min(avail.width() / pw, avail.height() / ph)
        w, h = pw * s, ph * s
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h)

    def _crop_norm(self) -> tuple[float, float, float, float] | None:
        if self._pix is None or self._aspect is None:
            return None
        pw, ph = self._pix.width(), self._pix.height()
        x, y, w, h = crop_rect_f(pw, ph, self._aspect, self._cx, self._cy, self._zoom)
        return x / pw, y / ph, w / pw, h / ph

    def _clamp(self) -> None:
        c = self._crop_norm()
        if c is None:
            return
        _x, _y, w, h = c
        self._cx = min(max(self._cx, w / 2), 1 - w / 2)
        self._cy = min(max(self._cy, h / 2), 1 - h / 2)

    def _to_norm(self, pos: QPointF) -> tuple[float, float]:
        r = self._image_rect()
        return (pos.x() - r.left()) / r.width(), (pos.y() - r.top()) / r.height()

    # --- vẽ ---
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(P["video"]))
        if self._pix is None:
            p.setPen(QColor(P["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Không lấy được hình xem trước")
            return
        r = self._image_rect()
        p.drawPixmap(r.toRect(), self._pix)
        c = self._crop_norm()
        if c is None:
            return
        nx, ny, nw, nh = c
        cr = QRectF(r.left() + nx * r.width(), r.top() + ny * r.height(), nw * r.width(), nh * r.height())
        dim = QPainterPath()
        dim.setFillRule(Qt.OddEvenFill)
        dim.addRect(r)
        dim.addRect(cr)
        p.fillPath(dim, QColor(0, 0, 0, 160))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(P["accent"]), 2))
        p.drawRect(cr)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))              # lưới chia ba để dễ canh bố cục
        for i in (1, 2):
            p.drawLine(QPointF(cr.left() + cr.width() * i / 3, cr.top()),
                       QPointF(cr.left() + cr.width() * i / 3, cr.bottom()))
            p.drawLine(QPointF(cr.left(), cr.top() + cr.height() * i / 3),
                       QPointF(cr.right(), cr.top() + cr.height() * i / 3))

    # --- chuột ---
    def mousePressEvent(self, e) -> None:
        c = self._crop_norm()
        if e.button() != Qt.LeftButton or c is None:
            return
        px, py = self._to_norm(e.position())
        nx, ny, nw, nh = c
        inside = nx <= px <= nx + nw and ny <= py <= ny + nh
        self._grab = (px - self._cx, py - self._cy) if inside else (0.0, 0.0)   # bấm ngoài khung: khung nhảy tới đó
        self.setCursor(Qt.ClosedHandCursor)
        self._drag_to(px, py)

    def mouseMoveEvent(self, e) -> None:
        if self._grab is not None:
            self._drag_to(*self._to_norm(e.position()))

    def mouseReleaseEvent(self, _e) -> None:
        self._grab = None
        self.setCursor(Qt.OpenHandCursor)

    def _drag_to(self, px: float, py: float) -> None:
        gx, gy = self._grab or (0.0, 0.0)
        self._cx, self._cy = px - gx, py - gy
        self._clamp()
        self.update()
        self.changed.emit()

    def wheelEvent(self, e) -> None:
        if self._aspect is None:
            return
        self.set_zoom(self._zoom + e.angleDelta().y() / 120 * 0.1)
        self.zoomChanged.emit(self._zoom)
        e.accept()
