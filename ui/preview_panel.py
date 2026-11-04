"""Khu vực xem trước. Giai đoạn 1: khung hiển thị + thanh điều khiển; trình phát gắn ở giai đoạn 3."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QStackedLayout

from utils.timecode import format_clock
from .widgets import EmptyState, IconButton, Panel

PLAYER_NOTE = "Chưa hoạt động: trình phát có từ giai đoạn 3 (video preview có hình và tiếng)."
MARK_NOTE = "Chưa hoạt động: đánh dấu IN/OUT có từ giai đoạn 6 (chọn đoạn thủ công)."


class PreviewPanel(Panel):
    importRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Xem trước", parent)
        self.file_label = QLabel("")
        self.file_label.setObjectName("Small")
        self.add_action(self.file_label)

        self.surface = QFrame()
        self.surface.setObjectName("Preview")
        self.surface.setMinimumSize(320, 180)
        stack = QStackedLayout(self.surface)
        self.empty = EmptyState("film", "Chưa có video", "Nhập video livestream để bắt đầu.", "Nhập video")
        self.empty.actionClicked.connect(self.importRequested)
        stack.addWidget(self.empty)
        self.body.addWidget(self.surface, 1)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.btn_back = IconButton("back", PLAYER_NOTE)
        self.btn_play = IconButton("play", PLAYER_NOTE)
        self.btn_fwd = IconButton("forward", PLAYER_NOTE)
        self.btn_in = IconButton("mark-in", MARK_NOTE)
        self.btn_out = IconButton("mark-out", MARK_NOTE)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("Muted")
        self.speed = QComboBox()
        self.speed.addItems(["0.5x", "1x", "1.5x", "2x"])
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(64)
        self.speed.setToolTip(PLAYER_NOTE)
        self.btn_mute = IconButton("volume", PLAYER_NOTE)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip(PLAYER_NOTE)
        for w in (self.btn_back, self.btn_play, self.btn_fwd):
            row.addWidget(w)
        row.addSpacing(10)
        row.addWidget(self.time_label)
        row.addStretch(1)
        for w in (self.btn_in, self.btn_out):
            row.addWidget(w)
        row.addSpacing(10)
        row.addWidget(self.speed)
        row.addWidget(self.btn_mute)
        row.addWidget(self.volume)
        self.body.addLayout(row)
        for w in (self.btn_back, self.btn_play, self.btn_fwd, self.btn_in, self.btn_out,
                  self.speed, self.btn_mute, self.volume):
            w.setEnabled(False)

    def show_video_loaded(self, name: str, duration_ms: int) -> None:
        self.file_label.setText(name)
        self.time_label.setText(f"00:00 / {format_clock(duration_ms)}")
        self.empty.set_text("Đã nạp thông tin video", "Trình phát hình và tiếng được gắn ở giai đoạn 3.")
