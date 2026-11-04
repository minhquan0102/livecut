"""Thành phần giao diện dùng chung: nút icon có hiệu ứng hover, panel, trạng thái trống."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QPropertyAnimation, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from . import icons
from .theme import P


def mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


class IconButton(QToolButton):
    """Nút tự vẽ: icon + nhãn tùy chọn, nền chuyển mượt khi rê chuột."""

    def __init__(self, name: str, tooltip: str = "", label: str = "", size: int = 32,
                 variant: str = "ghost", checkable: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._name, self._label, self._variant = name, label, variant
        self._icon_px, self._h, self._hover = 18, size, 0.0
        self.setToolTip(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.valueChanged.connect(self._on_anim)
        if label:
            self.setFixedHeight(size)
        else:
            self.setFixedSize(size, size)

    def set_icon_name(self, name: str) -> None:
        self._name = name
        self.update()

    def sizeHint(self) -> QSize:
        if not self._label:
            return QSize(self._h, self._h)
        return QSize(26 + self._icon_px + 8 + self.fontMetrics().horizontalAdvance(self._label), self._h)

    def _on_anim(self, v) -> None:
        self._hover = float(v)
        self.update()

    def _go(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e) -> None:
        self._go(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._go(0.0)
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t, on, checked = self._hover, self.isEnabled(), self.isChecked()
        if self._variant == "primary":
            bg = mix(QColor(P["accent"]), QColor(P["accent_hi"]), t) if on else QColor(P["raised"])
            fg = QColor(P["on_accent"]) if on else QColor(P["faint"])
        elif checked:
            bg, fg = mix(QColor(P["accent_dim"]), QColor(P["accent"]).darker(150), t), QColor(P["accent_hi"])
        else:
            bg = QColor(P["hover"])
            bg.setAlphaF(t if on else 0.0)
            fg = mix(QColor(P["muted"]), QColor(P["text"]), t) if on else QColor(P["faint"])
        if self.isDown() and on:
            bg = bg.darker(115)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(P["accent"]), 1.5))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        px, fm = self._icon_px, self.fontMetrics()
        text_w = fm.horizontalAdvance(self._label) if self._label else 0
        total = px + (8 + text_w if self._label else 0)
        x = (self.width() - total) / 2
        p.drawPixmap(QPointF(x, (self.height() - px) / 2), icons.pixmap(self._name, fg.name(), px))
        if self._label:
            p.setPen(fg)
            p.drawText(QRectF(x + px + 8, 0, text_w + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self._label)


class Panel(QFrame):
    """Khung bo góc có tiêu đề và vùng nút thao tác bên phải."""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName("PanelHeader")
        self.header.setFixedHeight(44)
        self._hl = QHBoxLayout(self.header)
        self._hl.setContentsMargins(14, 0, 8, 0)
        self._hl.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PanelTitle")
        self._hl.addWidget(self.title_label)
        self._hl.addStretch(1)
        outer.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(12, 10, 12, 12)
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)

    def add_action(self, w: QWidget) -> None:
        self._hl.addWidget(w)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)


class EmptyState(QWidget):
    actionClicked = Signal()

    def __init__(self, icon_name: str, title: str, hint: str = "", action: str = "", parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icons.pixmap(icon_name, P["faint"], 34))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.title = QLabel(title)
        self.title.setObjectName("PanelTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.hint = QLabel(hint)
        self.hint.setObjectName("Small")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        for w in (self.icon_label, self.title, self.hint):
            lay.addWidget(w)
        if action:
            btn = IconButton("plus", label=action, size=34)
            btn.clicked.connect(self.actionClicked)
            lay.addSpacing(6)
            lay.addWidget(btn, 0, Qt.AlignCenter)

    def set_text(self, title: str, hint: str = "") -> None:
        self.title.setText(title)
        self.hint.setText(hint)


class FadeStack(QStackedWidget):
    """Chuyển trang với hiệu ứng mờ dần ngắn."""

    def fade_to(self, index: int) -> None:
        if index == self.currentIndex():
            return
        self.setCurrentIndex(index)
        w = self.currentWidget()
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
