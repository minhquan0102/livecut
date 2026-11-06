"""Hộp thoại xuất các đoạn đã chọn thành một file MP4."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from export.exporter import ExportOptions
from export.worker import ExportWorker
from services import ffmpeg_locator
from services.ffprobe import VideoInfo
from utils import paths
from utils.timecode import format_clock
from .theme import P

QUALITY = [("Cao (file lớn)", 18), ("Cân bằng (khuyên dùng)", 21), ("Nhỏ gọn", 25)]
HEIGHTS = (1080, 720, 480)

_PRIMARY = (f"QPushButton {{ background: {P['accent']}; color: {P['on_accent']}; border: none; "
            f"font-weight: 600; padding: 7px 18px; }}"
            f"QPushButton:hover {{ background: {P['accent_hi']}; }}"
            f"QPushButton:disabled {{ background: {P['raised']}; color: {P['faint']}; }}")
_PROGRESS = (f"QProgressBar {{ background: {P['raised']}; border: none; border-radius: 4px; "
             f"max-height: 8px; min-height: 8px; }}"
             f"QProgressBar::chunk {{ background: {P['accent']}; border-radius: 4px; }}")


class ExportDialog(QDialog):
    def __init__(self, parent, ffmpeg: str, info: VideoInfo, ranges: list[tuple[int, int]],
                 default_path: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xuất video")
        self.setMinimumWidth(580)
        self._ffmpeg, self._info, self._ranges = ffmpeg, info, ranges
        self._worker: ExportWorker | None = None
        self._out = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)
        total = sum(e - s for s, e in ranges)
        head = QLabel(f"{len(ranges)} đoạn · tổng {format_clock(total)}")
        head.setObjectName("PanelTitle")
        hint = QLabel("Chỉ phần được chọn mới được mã hóa lại, nên video livestream dài vẫn xuất nhanh. "
                      "Các đoạn được nối thành một file, giữ nguyên âm thanh gốc.")
        hint.setObjectName("Small")
        hint.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.path = QLineEdit(default_path)
        self.btn_browse = QPushButton("Chọn…")
        prow = QHBoxLayout()
        prow.addWidget(self.path, 1)
        prow.addWidget(self.btn_browse)
        self.res = QComboBox()
        self.res.addItem(f"Giữ nguyên ({info.width}×{info.height})", 0)
        for h in HEIGHTS:
            if h < info.height:
                self.res.addItem(f"{h}p", h)
        self.quality = QComboBox()
        for label, crf in QUALITY:
            self.quality.addItem(label, crf)
        self.quality.setCurrentIndex(1)
        form.addRow("Lưu tại", prow)
        form.addRow("Độ phân giải", self.res)
        form.addRow("Chất lượng", self.quality)
        lay.addLayout(form)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(_PROGRESS)
        self.status = QLabel("")
        self.status.setObjectName("Small")
        self.status.setWordWrap(True)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.btn_open = QPushButton("Mở thư mục")
        self.btn_open.hide()
        self.btn_close = QPushButton("Đóng")
        self.btn_start = QPushButton("Bắt đầu xuất")
        self.btn_start.setStyleSheet(_PRIMARY)
        btns.addWidget(self.btn_open)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)
        btns.addWidget(self.btn_start)
        lay.addLayout(btns)

        self.btn_browse.clicked.connect(self._browse)
        self.btn_start.clicked.connect(self._start)
        self.btn_close.clicked.connect(self._close_or_cancel)
        self.btn_open.clicked.connect(self._open_folder)

    # --- thao tác ---
    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Lưu video", self.path.text(), "Video MP4 (*.mp4)")
        if path:
            self.path.setText(path if path.lower().endswith(".mp4") else path + ".mp4")

    def _say(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {P['danger'] if error else P['muted']};")

    def _start(self) -> None:
        out = self.path.text().strip()
        if not out:
            self._say("Hãy chọn nơi lưu file.", True)
            return
        if not out.lower().endswith(".mp4"):
            out += ".mp4"
            self.path.setText(out)
        if os.path.abspath(out) == os.path.abspath(self._info.path):
            self._say("Không được lưu đè lên video gốc. Hãy chọn tên khác.", True)
            return
        if os.path.exists(out):
            ans = QMessageBox.question(self, "File đã tồn tại", f"Ghi đè file này?\n{out}")
            if ans != QMessageBox.Yes:
                return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        except OSError as exc:
            self._say(f"Không tạo được thư mục: {exc}", True)
            return
        opts = ExportOptions(height=int(self.res.currentData()), crf=int(self.quality.currentData()))
        work = str(paths.temp_dir() / f"export_{int(time.time())}")
        self._worker = ExportWorker(self._ffmpeg, self._info.path, self._ranges, out, opts,
                                    self._info.has_audio, self._info.fps, work, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._out = out
        self.bar.setValue(0)
        self.btn_open.hide()
        self._set_running(True)
        self._say("Đang bắt đầu…")
        self._worker.start()

    def _set_running(self, on: bool) -> None:
        for w in (self.path, self.btn_browse, self.res, self.quality, self.btn_start):
            w.setEnabled(not on)
        self.btn_close.setText("Hủy xuất" if on else "Đóng")
        self.btn_close.setEnabled(True)

    def _on_progress(self, fraction: float, message: str) -> None:
        self.bar.setValue(int(fraction * 1000))
        self._say(f"{message} — {fraction * 100:.0f}%")

    def _on_done(self, path: str) -> None:
        self.bar.setValue(1000)
        self._set_running(False)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        self._say(f"Xong! Đã lưu: {path}  ({paths.human_size(size)})")
        self.btn_open.show()
        self.btn_start.setText("Xuất lại")

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        detail = f"\n\nFFmpeg đang dùng: {self._ffmpeg}\n{ffmpeg_locator.get_version(self._ffmpeg)}"
        self._say((message or "Xuất video thất bại.") + detail, True)

    def _on_cancelled(self) -> None:
        self._set_running(False)
        self.bar.setValue(0)
        self._say("Đã hủy xuất.")

    def _close_or_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.btn_close.setEnabled(False)
            self.btn_close.setText("Đang hủy…")
        else:
            self.reject()

    def _open_folder(self) -> None:
        if self._out:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(self._out))))

    def reject(self) -> None:
        if self._worker and self._worker.isRunning():     # đóng cửa sổ khi đang xuất: hủy rồi đợi dọn dẹp
            self._worker.cancel()
            self._worker.wait(8000)
        super().reject()
