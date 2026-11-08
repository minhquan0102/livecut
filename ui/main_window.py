"""Cửa sổ chính: lắp ráp các panel và nối tín hiệu."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget)

from editor.ranges import apply_order, build_ranges, combine, manual_ranges, range_key
from player.sequence import SequencePreview
from player.video_player import VideoPlayer
from project.model import Project
from services import ffmpeg_locator
from services.ffprobe import VideoInfo, probe
from services.tasks import TaskRunner
from subtitle.srt import parse_srt, read_srt_file, validate_cues
from utils import paths
from utils.timecode import format_clock
from .export_dialog import ExportDialog
from .preview_panel import PreviewPanel
from .range_dialog import RangeDialog
from .segment_panel import SegmentPanel
from .sidebar import Sidebar
from .subtitle_panel import SubtitlePanel
from .theme import P
from .timeline_panel import TimelinePanel
from .topbar import TopBar

VIDEO_FILTER = "Video (*.mp4 *.mkv *.mov *.avi *.flv *.ts *.webm *.m4v);;Tất cả file (*.*)"
PROJECT_EXT = "Dự án LiveCut (*.livecut)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(1100, 680)
        self.resize(1480, 900)
        self.project = Project()
        self.project_path = ""
        self.video: VideoInfo | None = None
        self.runner = TaskRunner(self)
        self.player = VideoPlayer(self)
        self.sequence = SequencePreview(self.player, self)
        self.ranges: list = []
        self._editing_key: int | None = None     # khoảng thủ công đang chỉnh trên timeline
        self._mark_in: int | None = None
        self.settings = QSettings("LiveCutStudio", "LiveCutStudio")
        self._build_ui()
        self._wire()
        self._restore_layout()
        self.sidebar.set_project(self.project)
        self.sidebar.set_temp_usage(paths.temp_usage_bytes())
        self.runner.run(ffmpeg_locator.detect, self.sidebar.set_ffmpeg_status)
        self._refresh_title()

    # --- dựng giao diện ---
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.topbar = TopBar()
        v.addWidget(self.topbar)

        self.sidebar = Sidebar()
        self.preview = PreviewPanel()
        self.subtitles = SubtitlePanel()
        self.timeline = TimelinePanel()
        self.segments = SegmentPanel()
        self.preview.attach_video_widget(self.player.video_widget)

        self.top_split = QSplitter(Qt.Horizontal)
        for w in (self.sidebar, self.preview, self.subtitles):
            self.top_split.addWidget(w)
        self.bottom_split = QSplitter(Qt.Horizontal)
        self.bottom_split.addWidget(self.timeline)
        self.bottom_split.addWidget(self.segments)
        self.main_split = QSplitter(Qt.Vertical)
        self.main_split.addWidget(self.top_split)
        self.main_split.addWidget(self.bottom_split)
        for s in (self.top_split, self.bottom_split, self.main_split):
            s.setHandleWidth(8)
            s.setChildrenCollapsible(False)
        self.top_split.setStretchFactor(1, 1)
        self.bottom_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(0, 1)
        self.top_split.setSizes([300, 760, 400])
        self.bottom_split.setSizes([1000, 420])
        self.main_split.setSizes([600, 290])

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.addWidget(self.main_split)
        v.addWidget(body, 1)
        self.setCentralWidget(root)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Sẵn sàng")

    def _wire(self) -> None:
        t = self.topbar
        t.import_video.clicked.connect(self.import_video)
        t.import_srt.clicked.connect(self.import_srt)
        t.open_project.clicked.connect(self.open_project)
        t.save_project.clicked.connect(self.save_project)
        t.settings.clicked.connect(lambda: self._show_tools())
        t.export.clicked.connect(self.export_video)
        t.btn_sidebar.toggled.connect(self.sidebar.setVisible)
        t.btn_right.toggled.connect(self.subtitles.setVisible)
        t.btn_bottom.toggled.connect(self.bottom_split.setVisible)
        self.preview.importRequested.connect(self.import_video)
        self.subtitles.importRequested.connect(self.import_srt)
        self.sidebar.importVideoRequested.connect(self.import_video)
        self.sidebar.importSrtRequested.connect(self.import_srt)
        self.sidebar.projectRenamed.connect(self._rename_project)
        self.sidebar.clearTempRequested.connect(self._clear_temp)
        self.sidebar.groupsChanged.connect(self.sidebar.refresh_project)
        self.subtitles.cueActivated.connect(self.timeline.jump_to)
        # trình phát
        p, pv = self.player, self.preview
        self.subtitles.cueActivated.connect(p.seek)          # nhấp phụ đề -> nhảy ngay
        self.timeline.seekRequested.connect(p.seek_drag)     # kéo/nhấp timeline -> seek (gộp yêu cầu)
        pv.playToggled.connect(p.toggle)
        pv.seekRelative.connect(p.seek_relative)
        pv.speedChanged.connect(p.set_rate)
        pv.volumeChanged.connect(p.set_volume)
        pv.muteToggled.connect(p.set_muted)
        p.playingChanged.connect(pv.set_playing)
        p.positionChanged.connect(self._on_player_position)
        p.durationChanged.connect(pv.set_duration)
        p.loaded.connect(pv.show_player)
        p.failed.connect(self._on_player_failed)
        # chọn câu -> đoạn -> xem thử liên tiếp
        self.subtitles.chosenChanged.connect(self._refresh_chosen)
        self.segments.paddingChanged.connect(self._refresh_chosen)
        self.segments.clearRequested.connect(self._clear_chosen)
        self.segments.previewRequested.connect(self._toggle_sequence)
        self.segments.rangeActivated.connect(self._on_range_clicked)
        self.segments.orderChanged.connect(self._on_order_changed)
        self.segments.sortRequested.connect(self._reset_order)
        self.sequence.activeChanged.connect(self.segments.set_previewing)
        self.sequence.rangeChanged.connect(self.segments.highlight)
        self.sequence.finished.connect(lambda: self.statusBar().showMessage("Đã xem hết phần đã chọn", 4000))
        # chọn khoảng tự do (kéo timeline, IN/OUT, nhập giờ)
        self.timeline.addRangeRequested.connect(self._add_selection)
        self.timeline.typeRangeRequested.connect(self._type_range)
        self.preview.markIn.connect(self._mark_in_here)
        self.preview.markOut.connect(self._mark_out_here)
        self.segments.rangeClicked.connect(self._on_range_selected)
        self.segments.rangeEditRequested.connect(self._type_range)
        self.segments.removeRequested.connect(self._remove_ranges)
        p.loaded.connect(self._refresh_chosen)
        p.seekLatency.connect(lambda ms: self.statusBar().showMessage(f"Seek: {ms:.0f} ms", 3000))
        for seq, fn in (("Ctrl+O", self.import_video), ("Ctrl+Shift+O", self.import_srt),
                        ("Ctrl+P", self.open_project), ("Ctrl+S", self.save_project),
                        ("Space", p.toggle), ("Ctrl+E", self.export_video), ("I", self._mark_in_here), ("O", self._mark_out_here), ("Ctrl+B", t.btn_sidebar.click), ("Ctrl+R", t.btn_right.click),
                        ("Ctrl+T", t.btn_bottom.click)):
            QShortcut(QKeySequence(seq), self, activated=fn)

    def _on_player_position(self, ms: int) -> None:
        self.preview.set_position(ms)
        if not self.timeline.view.is_dragging:      # đang kéo thì để timeline tự vẽ, tránh giật
            self.timeline.jump_to(ms, follow=self.player.is_playing())

    # --- các đoạn được chọn từ phụ đề ---
    def _refresh_chosen(self) -> None:
        self.sequence.stop()
        chosen = [c for c in self.project.cues if c.mark == "selected"]
        before, after = self.segments.padding_ms()
        dur = self.video.duration_ms if self.video else 0
        both = combine(build_ranges(chosen, before, after, dur), manual_ranges(self.project.manual, dur))
        self.ranges = apply_order(both, self.project.order)
        if self.project.order:                      # bỏ các khóa cũ không còn đoạn tương ứng
            self.project.order = [range_key(r) for r in self.ranges]
        self.segments.set_ranges(self.ranges, {c.index: c for c in self.project.cues})
        self.timeline.view.set_segments(
            [(r.start_ms, r.end_ms, P["warn"] if r.manual else P["ok"]) for r in self.ranges])
        if self._editing_key is not None and self._editing_key not in {range_key(r) for r in self.ranges}:
            self._stop_editing()
        self.segments.set_preview_enabled(bool(self.ranges) and self.player.is_ready())
        can_export = bool(self.ranges) and self.video is not None
        self.topbar.export.setEnabled(can_export)
        self.topbar.export.setToolTip(
            "Xuất các đoạn đã chọn thành một file MP4 (Ctrl+E)" if can_export
            else "Chọn câu phụ đề hoặc kéo chọn một khoảng trên timeline trước khi xuất")

    # --- khoảng tự chọn ---
    def _duration(self) -> int:
        return self.video.duration_ms if self.video else 0

    def _stop_editing(self) -> None:
        self._editing_key = None
        self.timeline.set_editing(False)
        self.timeline.set_selection(None)

    def _add_selection(self) -> None:
        """Thêm khoảng đang chọn trên timeline; nếu đang chỉnh một khoảng thì cập nhật nó."""
        sel = self.timeline.view.selection()
        if sel is not None:
            self._commit_manual(*sel)

    def _commit_manual(self, start: int, end: int) -> None:
        m = self.project.manual_by_id(-self._editing_key) if self._editing_key is not None else None
        if m is not None:
            m.start_ms, m.end_ms = start, end
            msg = "Đã cập nhật khoảng"
        else:
            self.project.add_manual(start, end)
            msg = "Đã thêm khoảng"
        self._editing_key = None
        self.timeline.set_editing(False)
        self.timeline.set_selection(None)
        self._refresh_chosen()
        self.statusBar().showMessage(f"{msg} {format_clock(start)} → {format_clock(end)}", 4000)

    def _type_range(self, key=None) -> None:
        """Hộp nhập giờ: thêm khoảng mới, hoặc sửa khoảng thủ công `key` (nhấp đúp trong danh sách)."""
        if self.video is None:
            return
        if isinstance(key, int) and key < 0 and self.project.manual_by_id(-key) is not None:
            m = self.project.manual_by_id(-key)
            a, b = m.start_ms, m.end_ms
            self._editing_key = key
            self.timeline.set_editing(True)
        else:
            sel = self.timeline.view.selection()
            a, b = sel if sel else (self.player.position(), self.player.position() + 5000)
        dlg = RangeDialog(self, a, b, self._duration(), editing=self._editing_key is not None)
        if dlg.exec() and dlg.result_range:
            self._commit_manual(*dlg.result_range)
        elif isinstance(key, int) and key < 0:
            self._stop_editing()

    def _mark_in_here(self) -> None:
        if self.video is None or not self.player.is_ready():
            return
        self._mark_in = self.player.position()
        self.timeline.view.set_mark_in(self._mark_in)
        self.statusBar().showMessage(f"IN tại {format_clock(self._mark_in)} — bấm O để chốt điểm kết thúc", 5000)

    def _mark_out_here(self) -> None:
        if self.video is None or not self.player.is_ready():
            return
        if self._mark_in is None:
            self.statusBar().showMessage("Bấm I (hoặc nút IN) để đánh dấu điểm bắt đầu trước", 4000)
            return
        end = self.player.position()
        if end - self._mark_in < 100:
            self.statusBar().showMessage("Điểm OUT phải sau điểm IN", 4000)
            return
        start, self._mark_in = self._mark_in, None
        self.timeline.view.set_mark_in(None)
        self._editing_key = None
        self._commit_manual(start, end)

    def _on_range_selected(self, key: int) -> None:
        """Nhấp một đoạn trong danh sách: nếu là khoảng thủ công thì nạp lên timeline để kéo tay nắm."""
        m = self.project.manual_by_id(-key) if key < 0 else None
        if m is None:
            if self._editing_key is not None:
                self._stop_editing()
            return
        self._editing_key = key
        self.timeline.set_editing(True)
        self.timeline.set_selection((m.start_ms, m.end_ms), reveal=True)

    def _remove_ranges(self, keys: list) -> None:
        by_key = {range_key(r): r for r in self.ranges}
        for k in keys:
            r = by_key.get(k)
            if r is None:
                continue
            if k < 0:
                self.project.manual = [m for m in self.project.manual if m.id != -k]
            else:
                for c in self.project.cues:
                    if c.index in r.cue_indexes and c.mark == "selected":
                        c.mark = ""
        self.project.order = [k for k in self.project.order if k not in set(keys)]
        self.subtitles.refresh_marks()
        self._refresh_chosen()

    def export_video(self) -> None:
        if not self.ranges or self.video is None:
            return
        self.sequence.stop()
        try:
            ffmpeg = ffmpeg_locator.require_binary("ffmpeg")
        except ffmpeg_locator.FFmpegNotFoundError as exc:
            self._error("Thiếu FFmpeg", str(exc))
            return
        stem = os.path.splitext(os.path.basename(self.video.path))[0]
        default = os.path.join(os.path.dirname(self.video.path), f"{stem}_cut.mp4")
        ExportDialog(self, ffmpeg, self.video, [(r.start_ms, r.end_ms) for r in self.ranges], default,
                     self.project.cues, self.player.position()).exec()

    def _on_order_changed(self, keys: list) -> None:
        self.project.order = [int(k) for k in keys]
        self._refresh_chosen()

    def _reset_order(self) -> None:
        self.project.order = []
        self._refresh_chosen()

    def _clear_chosen(self) -> None:
        self.project.manual = []
        self._stop_editing()
        for c in self.project.cues:
            if c.mark == "selected":
                c.mark = ""
        self.subtitles.refresh_marks()
        self._refresh_chosen()

    def _toggle_sequence(self) -> None:
        if self.sequence.active:
            self.sequence.stop()
        elif self.ranges:
            self.sequence.start([(r.start_ms, r.end_ms) for r in self.ranges])

    def _on_range_clicked(self, ms: int) -> None:
        self.player.seek(ms)
        self.timeline.jump_to(ms)

    def _on_player_failed(self, message: str) -> None:
        self.preview.show_error(message)
        QMessageBox.warning(
            self, "Không phát được video",
            message + "\n\nThử chuyển video sang MP4 (H.264 + AAC) rồi nhập lại.")

    def _show_tools(self) -> None:
        if not self.topbar.btn_sidebar.isChecked():
            self.topbar.btn_sidebar.click()
        self.sidebar.show_page(3)

    # --- trạng thái ---
    def _last_dir(self) -> str:
        return self.settings.value("last_dir", "", str)

    def _remember_dir(self, path: str) -> None:
        self.settings.setValue("last_dir", os.path.dirname(path))

    def _refresh_title(self) -> None:
        self.setWindowTitle(f"{self.project.name} – LiveCut Studio")
        self.topbar.set_project_name(self.project.name)

    def _rename_project(self, name: str) -> None:
        if name:
            self.project.name = name
            self._refresh_title()

    def _clear_temp(self) -> None:
        freed = paths.clear_temp()
        self.sidebar.set_temp_usage(paths.temp_usage_bytes())
        self.statusBar().showMessage(f"Đã giải phóng {paths.human_size(freed)}", 4000)

    def _error(self, title: str, message: str) -> None:
        self.statusBar().showMessage(title, 5000)
        QMessageBox.warning(self, title, message)

    # --- import video ---
    def import_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Nhập video", self._last_dir(), VIDEO_FILTER)
        if path:
            self._load_video(path)

    def _load_video(self, path: str) -> None:
        self._remember_dir(path)
        self.statusBar().showMessage("Đang đọc thông tin video…")
        self.runner.run(lambda: probe(path), self._on_video_ready, lambda m: self._error("Không đọc được video", m))

    def _on_video_ready(self, info: VideoInfo) -> None:
        self.video = info
        self.project.video_path = info.path
        self.sidebar.set_video(info)
        self.sidebar.refresh_project()
        self.timeline.set_duration(info.duration_ms)
        self._mark_in = None
        self._stop_editing()
        self._refresh_chosen()
        self.preview.show_video_loaded(os.path.basename(info.path), info.duration_ms)
        self.player.load(info.path)
        self.statusBar().showMessage("Đã nhập video", 4000)
        self._check_srt()

    # --- import SRT ---
    def import_srt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Nhập phụ đề SRT", self._last_dir(), "Phụ đề (*.srt);;Tất cả file (*.*)")
        if not path:
            return
        self._remember_dir(path)
        try:
            result = parse_srt(read_srt_file(path))
        except OSError as exc:
            self._error("Không đọc được SRT", str(exc))
            return
        if not result.cues:
            self._error("File SRT trống", "Không đọc được phụ đề nào. Hãy kiểm tra định dạng file.")
            return
        self.project.srt_path = path
        self.project.cues = result.cues
        self.project.order = []
        self.subtitles.set_cues(result.cues)
        self._refresh_chosen()
        self.sidebar.refresh_project()
        self.statusBar().showMessage(f"Đã nhập {len(result.cues)} phụ đề", 4000)
        notes = [f"• {w}" for w in result.warnings[:5]]
        if len(result.warnings) > 5:
            notes.append(f"… và {len(result.warnings) - 5} cảnh báo khác.")
        self._check_srt(extra=notes)

    def _check_srt(self, extra: list[str] | None = None) -> None:
        if not self.project.cues:
            return
        issues = validate_cues(self.project.cues, self.video.duration_ms if self.video else None)
        lines = [f"• {i.message}" for i in issues] + (extra or [])
        if lines:
            QMessageBox.warning(self, "Kiểm tra file SRT", "\n".join(lines))

    # --- lưu / mở dự án ---
    def save_project(self) -> None:
        path = self.project_path
        if not path:
            suggested = os.path.join(self._last_dir(), self.project.name + ".livecut")
            path, _ = QFileDialog.getSaveFileName(self, "Lưu dự án", suggested, PROJECT_EXT)
            if not path:
                return
            if not path.endswith(".livecut"):
                path += ".livecut"
        try:
            self.project.save(path)
        except OSError as exc:
            self._error("Không lưu được dự án", str(exc))
            return
        self.project_path = path
        self.statusBar().showMessage(f"Đã lưu {os.path.basename(path)}", 4000)

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Mở dự án", self._last_dir(), PROJECT_EXT)
        if not path:
            return
        try:
            project = Project.load(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._error("Không mở được dự án", str(exc))
            return
        self._remember_dir(path)
        self.project, self.project_path, self.video = project, path, None
        self.sidebar.set_project(project)
        self.sidebar.set_video(None)
        self.subtitles.set_cues(project.cues)
        self.timeline.set_duration(0)
        self._mark_in = None
        self._editing_key = None
        self.timeline.set_editing(False)
        self.player.unload()
        self.preview.reset()
        self._refresh_chosen()
        self._refresh_title()
        if project.video_path and os.path.isfile(project.video_path):
            self._load_video(project.video_path)
        elif project.video_path:
            self._error("Không tìm thấy video nguồn", f"File không còn ở:\n{project.video_path}\nHãy nhập lại video.")

    # --- bố cục ---
    def _restore_layout(self) -> None:
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        for key, split in (("top", self.top_split), ("bottom", self.bottom_split), ("main", self.main_split)):
            state = self.settings.value("split_" + key)
            if state:
                split.restoreState(state)

    def closeEvent(self, e) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        for key, split in (("top", self.top_split), ("bottom", self.bottom_split), ("main", self.main_split)):
            self.settings.setValue("split_" + key, split.saveState())
        self.player.unload()
        self.runner.wait_all()
        super().closeEvent(e)
