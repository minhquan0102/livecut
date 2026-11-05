"""Xem thử liên tiếp nhiều đoạn bằng đúng một trình phát: hết đoạn này nhảy ngay sang đoạn kế tiếp."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from editor.ranges import SequenceTracker
from .video_player import VideoPlayer


class SequencePreview(QObject):
    activeChanged = Signal(bool)
    rangeChanged = Signal(int)
    finished = Signal()

    def __init__(self, player: VideoPlayer, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._tracker: SequenceTracker | None = None
        player.positionChanged.connect(self._on_position)

    @property
    def active(self) -> bool:
        return self._tracker is not None

    def start(self, ranges: list[tuple[int, int]], index: int = 0) -> None:
        if not ranges or not self._player.is_ready():
            return
        self._tracker = SequenceTracker(ranges)
        self.activeChanged.emit(True)
        self._goto(index)
        self._player.play()

    def stop(self, pause: bool = True) -> None:
        if self._tracker is None:
            return
        self._tracker = None
        self.activeChanged.emit(False)
        if pause:
            self._player.pause()

    def _goto(self, index: int) -> None:
        t = self._tracker
        if t is None:
            return
        pos = t.begin(index)
        self.rangeChanged.emit(t.index)
        self._player.seek(pos)

    def _on_position(self, ms: int) -> None:
        t = self._tracker
        if t is None:
            return
        action, i = t.on_position(ms)
        if action == "goto":
            self._goto(i)
        elif action == "stop":
            self.stop(pause=False)       # người dùng tua đi chỗ khác: giữ nguyên trạng thái phát
        elif action == "done":
            self.stop(pause=True)
            self.finished.emit()
