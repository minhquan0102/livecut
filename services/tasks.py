"""Chạy tác vụ nặng ở QThread; kết quả quay về luồng giao diện qua signal."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot


class BackgroundTask(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], on_ok, on_error, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self.on_ok = on_ok
        self.on_error = on_error

    def run(self) -> None:
        try:
            self.succeeded.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho người dùng thay vì sập luồng
            self.failed.emit(str(exc))


class TaskRunner(QObject):
    """Giữ tham chiếu tác vụ đang chạy và gọi callback trên luồng giao diện."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tasks: set[BackgroundTask] = set()

    def run(self, fn, on_ok=None, on_error=None) -> None:
        t = BackgroundTask(fn, on_ok, on_error, self)
        t.succeeded.connect(self._ok)
        t.failed.connect(self._fail)
        t.finished.connect(self._done)
        self._tasks.add(t)
        t.start()

    @Slot(object)
    def _ok(self, result) -> None:
        t = self.sender()
        if getattr(t, "on_ok", None):
            t.on_ok(result)

    @Slot(str)
    def _fail(self, message: str) -> None:
        t = self.sender()
        if getattr(t, "on_error", None):
            t.on_error(message)

    @Slot()
    def _done(self) -> None:
        t = self.sender()
        self._tasks.discard(t)
        t.deleteLater()

    def wait_all(self) -> None:
        for t in list(self._tasks):
            t.wait(3000)
