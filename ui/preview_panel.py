"""Khu vực xem trước: khung video + thanh điều khiển phát. Trình phát nằm ở player/video_player.py."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QStackedLayout,
                               QWidget)

from utils.timecode import format_clock
from .widgets import EmptyState, IconButton, Panel

RATES = [0.5, 1.0, 1.5, 2.0]
SKIP_MS = 5000


class PreviewPanel(Panel):
    importRequested = Signal()
    playToggled = Signal()
    seekRelative = Signal(int)       # ms, âm = tua lùi
    speedChanged = Signal(float)
    volumeChanged = Signal(int)
    muteToggled = Signal(bool)
    markIn = Signal()
    markOut = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Xem trước", parent)
        self._duration = 0
        self.file_label = QLabel("")
        self.file_label.setObjectName("Small")
        self.add_action(self.file_label)

        self.surface = QFrame()
        self.surface.setObjectName("Preview")
        self.surface.setMinimumSize(320, 180)
        self.stack = QStackedLayout(self.surface)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.empty = EmptyState("film", "Chưa có video", "Nhập video livestream để bắt đầu.", "Nhập video")
        self.empty.actionClicked.connect(self.importRequested)
        self.stack.addWidget(self.empty)          # trang 0: trạng thái trống / đang tải
        self.body.addWidget(self.surface, 1)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.btn_back = IconButton("back", "Tua lùi 5 giây")
        self.btn_play = IconButton("play", "Phát / Tạm dừng (Space)")
        self.btn_fwd = IconButton("forward", "Tua nhanh 5 giây")
        self.btn_in = IconButton("mark-in", "Đánh dấu điểm bắt đầu (phím I)")
        self.btn_out = IconButton("mark-out", "Đánh dấu điểm kết thúc và thêm khoảng vào video (phím O)")
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("Muted")
        self.speed = QComboBox()
        self.speed.addItems([f"{r:g}x" for r in RATES])
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(64)
        self.speed.setToolTip("Tốc độ phát")
        self.btn_mute = IconButton("volume", "Tắt/bật tiếng (M)", checkable=True)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip("Âm lượng")
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

        self.btn_play.clicked.connect(self.playToggled)
        self.btn_back.clicked.connect(lambda: self.seekRelative.emit(-SKIP_MS))
        self.btn_fwd.clicked.connect(lambda: self.seekRelative.emit(SKIP_MS))
        self.speed.currentIndexChanged.connect(lambda i: self.speedChanged.emit(RATES[i]))
        self.volume.valueChanged.connect(self.volumeChanged)
        self.btn_mute.toggled.connect(self._on_mute)

        self.btn_in.clicked.connect(self.markIn)
        self.btn_out.clicked.connect(self.markOut)
        self.set_controls_enabled(False)

    # --- API cho MainWindow ---
    def attach_video_widget(self, w: QWidget) -> None:
        self.stack.addWidget(w)                   # trang 1: video

    def set_controls_enabled(self, on: bool) -> None:
        for w in (self.btn_back, self.btn_play, self.btn_fwd, self.speed, self.btn_mute, self.volume,
                  self.btn_in, self.btn_out):
            w.setEnabled(on)

    def show_video_loaded(self, name: str, duration_ms: int) -> None:
        """Đã đọc thông tin video, đang mở trong trình phát."""
        self._duration = duration_ms
        self.file_label.setText(name)
        self.time_label.setText(f"00:00 / {format_clock(duration_ms)}")
        self.empty.set_text("Đang mở video…", "")
        self.stack.setCurrentIndex(0)

    def show_player(self) -> None:
        self.stack.setCurrentIndex(1)
        self.set_controls_enabled(True)

    def show_error(self, message: str) -> None:
        self.stack.setCurrentIndex(0)
        self.set_controls_enabled(False)
        self.empty.set_text("Không phát được video", message)

    def reset(self) -> None:
        self._duration = 0
        self.file_label.setText("")
        self.time_label.setText("00:00 / 00:00")
        self.empty.set_text("Chưa có video", "Nhập video livestream để bắt đầu.")
        self.stack.setCurrentIndex(0)
        self.set_controls_enabled(False)
        self.set_playing(False)

    def set_duration(self, ms: int) -> None:
        self._duration = ms

    def set_position(self, ms: int) -> None:
        self.time_label.setText(f"{format_clock(ms)} / {format_clock(self._duration)}")

    def set_playing(self, playing: bool) -> None:
        self.btn_play.set_icon_name("pause" if playing else "play")

    def _on_mute(self, muted: bool) -> None:
        self.btn_mute.set_icon_name("mute" if muted else "volume")
        self.muteToggled.emit(muted)
