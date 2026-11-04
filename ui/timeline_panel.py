"""Panel timeline: tiêu đề, nút zoom, đồng hồ, thanh cuộn ngang."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollBar

from timeline.view import TimelineView
from utils.timecode import format_clock
from .widgets import IconButton, Panel


class TimelinePanel(Panel):
    seekRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__("Timeline", parent)
        self.clock = QLabel("00:00 / 00:00")
        self.clock.setObjectName("Muted")
        self.btn_out = IconButton("zoom-out", "Thu nhỏ (Ctrl + cuộn chuột xuống)", size=28)
        self.btn_in = IconButton("zoom-in", "Phóng to (Ctrl + cuộn chuột lên)", size=28)
        self.btn_fit = IconButton("fit", "Vừa toàn bộ video", size=28)
        for w in (self.clock, self.btn_out, self.btn_in, self.btn_fit):
            self.add_action(w)

        self.view = TimelineView()
        self.scroll = QScrollBar(Qt.Horizontal)
        self.body.addWidget(self.view, 1)
        self.body.addWidget(self.scroll)

        self.btn_out.clicked.connect(lambda: self.view.zoom(1.5))
        self.btn_in.clicked.connect(lambda: self.view.zoom(1 / 1.5))
        self.btn_fit.clicked.connect(self.view.fit)
        self.view.viewChanged.connect(self._sync_scroll)
        self.view.seekRequested.connect(self._on_seek)
        self.scroll.valueChanged.connect(self._on_scroll)
        self._duration = 0
        self._sync_scroll()

    def set_duration(self, ms: int) -> None:
        self._duration = ms
        self.view.set_duration(ms)
        self._update_clock(0)

    def jump_to(self, ms: int) -> None:
        self.view.set_playhead(ms, follow=True)
        self._update_clock(ms)

    def _on_seek(self, ms: int) -> None:
        self._update_clock(ms)
        self.seekRequested.emit(ms)

    def _update_clock(self, ms: int) -> None:
        self.clock.setText(f"{format_clock(ms)} / {format_clock(self._duration)}")

    def _sync_scroll(self) -> None:
        s = self.view.scale
        maxv = max(0, int(s.duration_ms - s.visible_ms))
        self.scroll.blockSignals(True)
        self.scroll.setRange(0, maxv)
        self.scroll.setPageStep(max(1, int(s.visible_ms)))
        self.scroll.setValue(int(s.start_ms))
        self.scroll.blockSignals(False)
        self.scroll.setEnabled(maxv > 0)

    def _on_scroll(self, value: int) -> None:
        self.view.scale.set_start(value)
        self.view.update()
