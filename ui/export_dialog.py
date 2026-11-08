"""Hộp thoại xuất các đoạn đã chọn thành một file MP4."""
from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSlider, QVBoxLayout,
                               QWidget)

from editor.ranges import cut_cues
from export import framing
from export.exporter import ExportOptions, resolution_choices
from export.framing import ASPECTS, MAX_ZOOM, MODES, FrameSpec, size_choices
from export.worker import ExportWorker
from services import ffmpeg_locator
from services.ffprobe import VideoInfo
from subtitle.srt import Cue, serialize_srt
from utils import paths
from utils.timecode import format_clock
from .frame_editor import FrameEditor
from .theme import P

# (nhãn, CRF, preset): CRF càng nhỏ càng nét; preset chậm hơn nén hiệu quả hơn
QUALITY = [("Rất cao — gần như bản gốc (xuất chậm hơn)", 16, "fast"),
           ("Cao (khuyên dùng)", 18, "veryfast"),
           ("Cân bằng", 21, "veryfast"),
           ("Nhỏ gọn", 25, "veryfast")]

_PRIMARY = (f"QPushButton {{ background: {P['accent']}; color: {P['on_accent']}; border: none; "
            f"font-weight: 600; padding: 7px 18px; }}"
            f"QPushButton:hover {{ background: {P['accent_hi']}; }}"
            f"QPushButton:disabled {{ background: {P['raised']}; color: {P['faint']}; }}")
_PROGRESS = (f"QProgressBar {{ background: {P['raised']}; border: none; border-radius: 4px; "
             f"max-height: 8px; min-height: 8px; }}"
             f"QProgressBar::chunk {{ background: {P['accent']}; border-radius: 4px; }}")


class ExportDialog(QDialog):
    def __init__(self, parent, ffmpeg: str, info: VideoInfo, ranges: list[tuple[int, int]],
                 default_path: str, cues: list[Cue] | None = None, position_ms: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xuất video")
        self.setMinimumWidth(640)
        self._ffmpeg, self._info, self._ranges = ffmpeg, info, ranges
        self._cues = cues or []
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
        self.aspect = QComboBox()
        for label, _a in ASPECTS:
            self.aspect.addItem(label)
        self.mode = QComboBox()
        for label, _m in MODES:
            self.mode.addItem(label)
        self.res = QComboBox()
        self._res: list[tuple[str, int, int]] = []
        self.quality = QComboBox()
        for label, _crf, _preset in QUALITY:
            self.quality.addItem(label)
        self.quality.setCurrentIndex(1)
        form.addRow("Lưu tại", prow)
        form.addRow("Tỷ lệ khung", self.aspect)
        form.addRow("Cách lấp khung", self.mode)
        form.addRow("Độ phân giải", self.res)
        form.addRow("Chất lượng", self.quality)
        lay.addLayout(form)

        # khung kéo được trên hình video (chỉ hiện khi chọn "Cắt vừa khung")
        self.editor_box = QWidget()
        eb = QVBoxLayout(self.editor_box)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(8)
        self.editor = FrameEditor()
        eb.addWidget(self.editor)
        zrow = QHBoxLayout()
        zlab = QLabel("Thu phóng")
        zlab.setObjectName("Small")
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(10, int(MAX_ZOOM * 10))
        self.zoom.setValue(10)
        self.btn_reset_frame = QPushButton("Đặt lại")
        zrow.addWidget(zlab)
        zrow.addWidget(self.zoom, 1)
        zrow.addWidget(self.btn_reset_frame)
        eb.addLayout(zrow)
        fhint = QLabel("Kéo trên hình để chọn vùng giữ lại, cuộn chuột để thu phóng. "
                       "Hình lấy tại vị trí video đang xem khi bạn bấm Xuất.")
        fhint.setObjectName("Small")
        fhint.setWordWrap(True)
        eb.addWidget(fhint)
        lay.addWidget(self.editor_box)
        self.chk_srt = QCheckBox("Xuất kèm file phụ đề .srt khớp với video mới")
        self.chk_srt.setChecked(True)
        self.chk_srt.setVisible(bool(self._cues))
        lay.addWidget(self.chk_srt)

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

        self.aspect.currentIndexChanged.connect(self._on_aspect)
        self.mode.currentIndexChanged.connect(self._update_frame_ui)
        self.zoom.valueChanged.connect(lambda v: self.editor.set_zoom(v / 10))
        self.editor.zoomChanged.connect(self._sync_zoom)
        self.btn_reset_frame.clicked.connect(self.editor.reset)
        self._load_still(position_ms)
        self._on_aspect()

        self.btn_browse.clicked.connect(self._browse)
        self.btn_start.clicked.connect(self._start)
        self.btn_close.clicked.connect(self._close_or_cancel)
        self.btn_open.clicked.connect(self._open_folder)

    # --- khung hình ---
    def _selected_aspect(self) -> tuple[int, int] | None:
        return ASPECTS[self.aspect.currentIndex()][1]

    def _load_still(self, position_ms: int) -> None:
        """Lấy một khung hình từ video làm hình tham chiếu cho việc chọn vùng."""
        dur = self._info.duration_ms
        ms = position_ms if 0 < position_ms < dur else (self._ranges[0][0] + 500 if self._ranges else 0)
        tmp = str(paths.temp_dir() / f"still_{int(time.time() * 1000)}.jpg")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if framing.extract_frame(self._ffmpeg, self._info.path, ms, tmp):
                pm = QPixmap()
                if pm.loadFromData(Path(tmp).read_bytes()):
                    self.editor.set_pixmap(pm)
        except OSError:
            pass
        finally:
            QApplication.restoreOverrideCursor()
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _on_aspect(self) -> None:
        aspect = self._selected_aspect()
        info = self._info
        self._res = resolution_choices(info.width, info.height) if aspect is None else size_choices(aspect)
        self.res.clear()
        for label, _w, _h in self._res:
            self.res.addItem(label)
        self.editor.set_aspect(aspect)
        self._update_frame_ui()

    def _update_frame_ui(self) -> None:
        has_aspect = self._selected_aspect() is not None
        self.mode.setEnabled(has_aspect)
        crop = has_aspect and MODES[self.mode.currentIndex()][1] == "crop"
        self.editor_box.setVisible(crop)
        self.adjustSize()

    def _sync_zoom(self, zoom: float) -> None:
        self.zoom.blockSignals(True)
        self.zoom.setValue(round(zoom * 10))
        self.zoom.blockSignals(False)

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
        _label, w, h = self._res[self.res.currentIndex()]
        _q, crf, preset = QUALITY[self.quality.currentIndex()]
        aspect = self._selected_aspect()
        frame = None
        if aspect is not None:
            cx, cy = self.editor.center()
            frame = FrameSpec(aspect, MODES[self.mode.currentIndex()][1], cx, cy, self.editor.zoom())
        opts = ExportOptions(width=w, height=h, crf=crf, preset=preset, frame=frame,
                             src_w=self._info.width, src_h=self._info.height)
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
        for w in (self.path, self.btn_browse, self.aspect, self.mode, self.res, self.quality, self.editor,
                  self.zoom, self.btn_reset_frame, self.chk_srt, self.btn_start):
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
        note = self._write_srt(path)
        self._say(f"Xong! Đã lưu: {path}  ({paths.human_size(size)})" + note)
        self.btn_open.show()
        self.btn_start.setText("Xuất lại")

    def _write_srt(self, video_path: str) -> str:
        if not (self._cues and self.chk_srt.isChecked()):
            return ""
        chosen = {c.index for c in self._cues if c.mark == "selected"}
        srt_path = os.path.splitext(video_path)[0] + ".srt"
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(serialize_srt(cut_cues(self._ranges, self._cues, chosen)))
        except OSError as exc:
            return f"\nKhông ghi được file phụ đề: {exc}"
        return f"\nPhụ đề: {srt_path}"

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
