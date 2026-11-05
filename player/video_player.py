"""Trình phát video duy nhất (QMediaPlayer + QAudioOutput + QVideoWidget), giữ suốt phiên làm việc.

- Đổi video chỉ gọi setSource trên cùng một player, không tạo player mới.
- Seek chạy bất đồng bộ trong backend nên không treo giao diện.
- Khi kéo timeline, các yêu cầu seek được gộp lại: chỉ gửi vị trí mới nhất mỗi ~30 ms.
- Mọi thời gian tính bằng mili-giây, cùng đơn vị với phần còn lại của dự án.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

DRAG_COALESCE_MS = 30


class VideoPlayer(QObject):
    positionChanged = Signal(int)    # ms
    durationChanged = Signal(int)    # ms
    playingChanged = Signal(bool)
    loaded = Signal()
    failed = Signal(str)
    seekLatency = Signal(float)      # ms từ lúc yêu cầu seek đến khi backend báo vị trí mới

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background:#000;")
        self._audio = QAudioOutput(self)
        self._audio.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self.video_widget)

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(lambda ms: self.durationChanged.emit(int(ms)))
        self._player.playbackStateChanged.connect(
            lambda st: self.playingChanged.emit(st == QMediaPlayer.PlayingState))
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)

        self._pending: int | None = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(DRAG_COALESCE_MS)
        self._drag_timer.timeout.connect(self._flush)
        self._t0: float | None = None
        self._target = 0
        self._ready = False
        self._error_reported = False

    # --- trạng thái ---
    def has_media(self) -> bool:
        return not self._player.source().isEmpty()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def position(self) -> int:
        return int(self._player.position())

    def duration(self) -> int:
        return int(self._player.duration())

    # --- điều khiển ---
    def load(self, path: str) -> None:
        self._ready = False
        self._error_reported = False
        self._pending = None
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))

    def unload(self) -> None:
        self._ready = False
        self._pending = None
        self._player.stop()
        self._player.setSource(QUrl())

    def play(self) -> None:
        if self._ready:
            self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if not self._ready:
            return
        self.pause() if self.is_playing() else self.play()

    def seek(self, ms: int) -> None:
        """Nhảy ngay (nhấp phụ đề, nút tua)."""
        if not self._ready:
            return
        self._pending = None
        self._send(ms)

    def seek_drag(self, ms: int) -> None:
        """Gộp seek khi đang kéo timeline."""
        if not self._ready:
            return
        self._pending = int(ms)
        if not self._drag_timer.isActive():
            self._drag_timer.start()

    def seek_relative(self, delta_ms: int) -> None:
        self.seek(self.position() + delta_ms)

    def set_rate(self, rate: float) -> None:
        self._player.setPlaybackRate(rate)

    def set_volume(self, percent: int) -> None:
        self._audio.setVolume(max(0, min(percent, 100)) / 100.0)

    def set_muted(self, muted: bool) -> None:
        self._audio.setMuted(muted)

    # --- nội bộ ---
    def _send(self, ms: int) -> None:
        dur = self.duration()
        ms = max(0, min(int(ms), dur if dur > 0 else int(ms)))
        self._t0 = time.perf_counter()
        self._target = ms
        self._player.setPosition(ms)

    def _flush(self) -> None:
        if self._pending is not None:
            ms, self._pending = self._pending, None
            self._send(ms)

    def _on_position(self, ms: int) -> None:
        if self._t0 is not None and abs(ms - self._target) < 1500:
            self.seekLatency.emit((time.perf_counter() - self._t0) * 1000.0)
            self._t0 = None
        self.positionChanged.emit(int(ms))

    def _on_status(self, status) -> None:
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and not self._ready:
            if self._player.duration() > 0:
                self._ready = True
                self._player.pause()  # hiện khung hình đầu tiên, không tự phát
                self.loaded.emit()
        elif status == QMediaPlayer.InvalidMedia:
            self._report("Định dạng hoặc codec của video không được hỗ trợ.")

    def _on_error(self, _err, message: str) -> None:
        self._report(message or "Không phát được video.")

    def _report(self, message: str) -> None:
        if not self._error_reported:
            self._error_reported = True
            self.failed.emit(message)
