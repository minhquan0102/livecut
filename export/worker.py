"""Chạy việc xuất video ở luồng nền để giao diện không bị đứng."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .exporter import ExportCancelled, ExportOptions, export_ranges


class ExportWorker(QThread):
    progress = Signal(float, str)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, ffmpeg: str, src: str, ranges: list[tuple[int, int]], out_path: str,
                 opts: ExportOptions, has_audio: bool, src_fps: float, work_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._args = (ffmpeg, src, ranges, out_path, opts, has_audio, src_fps, work_dir)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        ffmpeg, src, ranges, out_path, opts, has_audio, fps, work = self._args
        try:
            export_ranges(ffmpeg, src, ranges, out_path, opts, has_audio, fps, work,
                          on_progress=lambda f, m: self.progress.emit(f, m),
                          cancelled=lambda: self._cancel)
        except ExportCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho người dùng thay vì sập luồng
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(out_path)
