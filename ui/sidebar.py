"""Thanh bên: dự án, video, nhóm, công cụ."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QVBoxLayout, QWidget)

from project.model import Project
from services.ffprobe import VideoInfo
from utils.paths import human_size, temp_dir
from utils.timecode import format_clock
from .widgets import EmptyState, FadeStack, IconButton, Panel

PAGES = [("folder", "Dự án"), ("film", "Video"), ("layers", "Nhóm"), ("scissors", "Công cụ")]


def _value_label() -> QLabel:
    lab = QLabel("—")
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def _grid(rows: list[str]) -> tuple[QGridLayout, dict[str, QLabel]]:
    g = QGridLayout()
    g.setHorizontalSpacing(12)
    g.setVerticalSpacing(8)
    g.setColumnStretch(1, 1)
    labels = {}
    for i, name in enumerate(rows):
        k = QLabel(name)
        k.setObjectName("Muted")
        k.setAlignment(Qt.AlignTop)
        v = _value_label()
        g.addWidget(k, i, 0, Qt.AlignTop)
        g.addWidget(v, i, 1)
        labels[name] = v
    return g, labels


class Sidebar(QWidget):
    importVideoRequested = Signal()
    importSrtRequested = Signal()
    projectRenamed = Signal(str)
    groupsChanged = Signal()
    clearTempRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(52)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(6, 10, 6, 10)
        rl.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav: list[IconButton] = []
        for i, (icon_name, tip) in enumerate(PAGES):
            b = IconButton(icon_name, tip, size=38, checkable=True)
            self.group.addButton(b, i)
            self.nav.append(b)
            rl.addWidget(b)
        rl.addStretch(1)
        root.addWidget(rail)

        self.panel = Panel(PAGES[0][1])
        self.panel.setMinimumWidth(230)
        self.stack = FadeStack()
        self.stack.addWidget(self._build_project())
        self.stack.addWidget(self._build_video())
        self.stack.addWidget(self._build_groups())
        self.stack.addWidget(self._build_tools())
        self.panel.body.addWidget(self.stack, 1)
        root.addWidget(self.panel, 1)

        self.nav[0].setChecked(True)
        self.group.idClicked.connect(self.show_page)

    def show_page(self, i: int) -> None:
        self.nav[i].setChecked(True)
        self.panel.set_title(PAGES[i][1])
        self.stack.fade_to(i)

    # --- trang Dự án ---
    def _build_project(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        name_label = QLabel("Tên dự án")
        name_label.setObjectName("Muted")
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(lambda: self.projectRenamed.emit(self.name_edit.text().strip()))
        grid, self.proj_labels = _grid(["Video nguồn", "File SRT", "Số phụ đề", "Số nhóm"])
        b1 = IconButton("film", label="Nhập video", size=34)
        b2 = IconButton("captions", label="Nhập SRT", size=34)
        b1.clicked.connect(self.importVideoRequested)
        b2.clicked.connect(self.importSrtRequested)
        for x in (name_label, self.name_edit):
            lay.addWidget(x)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(b1)
        lay.addWidget(b2)
        lay.addStretch(1)
        return w

    # --- trang Video ---
    def _build_video(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.video_empty = EmptyState("film", "Chưa có video", "Thông tin video hiện ở đây sau khi nhập.")
        self.video_rows = ["Tên file", "Thời lượng", "Độ phân giải", "FPS", "Codec hình", "Codec tiếng",
                           "Dung lượng", "Bitrate"]
        self.video_info_box = QWidget()
        grid, self.video_labels = _grid(self.video_rows)
        self.video_info_box.setLayout(grid)
        self.video_info_box.hide()
        lay.addWidget(self.video_empty, 1)
        lay.addWidget(self.video_info_box)
        lay.addStretch(0)
        return w

    def set_video(self, info: VideoInfo | None) -> None:
        self.video_empty.setVisible(info is None)
        self.video_info_box.setVisible(info is not None)
        if info is None:
            return
        import os
        v = self.video_labels
        v["Tên file"].setText(os.path.basename(info.path))
        v["Thời lượng"].setText(format_clock(info.duration_ms))
        v["Độ phân giải"].setText(f"{info.width} × {info.height}")
        v["FPS"].setText(f"{info.fps:.2f}".rstrip("0").rstrip("."))
        v["Codec hình"].setText(info.video_codec)
        v["Codec tiếng"].setText(info.audio_codec or "Không có âm thanh")
        v["Dung lượng"].setText(human_size(info.size_bytes))
        v["Bitrate"].setText(f"{info.bitrate / 1_000_000:.1f} Mb/s" if info.bitrate else "—")

    # --- trang Nhóm ---
    def _build_groups(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        row = QHBoxLayout()
        self.g_add = IconButton("plus", "Thêm nhóm", label="Thêm nhóm", size=32)
        self.g_rename = IconButton("edit", "Đổi tên nhóm")
        self.g_delete = IconButton("trash", "Xóa nhóm")
        row.addWidget(self.g_add)
        row.addStretch(1)
        row.addWidget(self.g_rename)
        row.addWidget(self.g_delete)
        self.group_list = QListWidget()
        self.group_empty = EmptyState("layers", "Chưa có nhóm", "Tạo nhóm như “Sản phẩm A” hoặc “Công dụng” để gom các đoạn.")
        lay.addLayout(row)
        lay.addWidget(self.group_empty, 1)
        lay.addWidget(self.group_list, 1)
        self.g_add.clicked.connect(self._add_group)
        self.g_rename.clicked.connect(self._rename_group)
        self.g_delete.clicked.connect(self._delete_group)
        return w

    def _selected_group(self):
        row = self.group_list.currentRow()
        if self.project is None or row < 0:
            return None
        return self.project.groups[row]

    def _add_group(self) -> None:
        if self.project is None:
            return
        name, ok = QInputDialog.getText(self, "Thêm nhóm", "Tên nhóm:")
        if ok and name.strip():
            self.project.add_group(name)
            self.refresh_groups()
            self.group_list.setCurrentRow(len(self.project.groups) - 1)
            self.groupsChanged.emit()

    def _rename_group(self) -> None:
        g = self._selected_group()
        if g is None:
            return
        name, ok = QInputDialog.getText(self, "Đổi tên nhóm", "Tên nhóm:", text=g.name)
        if ok and name.strip():
            g.name = name.strip()
            self.refresh_groups()
            self.groupsChanged.emit()

    def _delete_group(self) -> None:
        g = self._selected_group()
        if g is None:
            return
        if QMessageBox.question(self, "Xóa nhóm", f"Xóa nhóm “{g.name}”? Các đoạn video không bị xóa.") == QMessageBox.Yes:
            self.project.remove_group(g.id)
            self.refresh_groups()
            self.groupsChanged.emit()

    def refresh_groups(self) -> None:
        self.group_list.clear()
        groups = self.project.groups if self.project else []
        for g in groups:
            self.group_list.addItem(f"{g.name}  ({len(g.items)})")
        self.group_empty.setVisible(not groups)
        self.group_list.setVisible(bool(groups))
        self.g_rename.setEnabled(bool(groups))
        self.g_delete.setEnabled(bool(groups))

    # --- trang Công cụ ---
    def _build_tools(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        grid, self.tool_labels = _grid(["FFmpeg", "FFprobe", "File tạm"])
        self.tool_labels["FFmpeg"].setText("Đang kiểm tra…")
        self.btn_clean = IconButton("clean", "Xóa file tạm của ứng dụng", label="Dọn file tạm", size=34)
        self.btn_clean.clicked.connect(self.clearTempRequested)
        lay.addLayout(grid)
        lay.addWidget(self.btn_clean)
        lay.addStretch(1)
        return w

    def set_ffmpeg_status(self, status: dict) -> None:
        for key, label in (("ffmpeg", "FFmpeg"), ("ffprobe", "FFprobe")):
            path, version = status[key]
            self.tool_labels[label].setText(f"{version}\n{path}" if path else
                                            "Không tìm thấy. Đặt vào thư mục bin/ cạnh ứng dụng hoặc thêm vào PATH.")

    def set_temp_usage(self, nbytes: int) -> None:
        self.tool_labels["File tạm"].setText(f"{human_size(nbytes)}\n{temp_dir()}")

    # --- đồng bộ với dự án ---
    def set_project(self, project: Project) -> None:
        self.project = project
        self.refresh_project()
        self.refresh_groups()

    def refresh_project(self) -> None:
        p = self.project
        if p is None:
            return
        import os
        self.name_edit.setText(p.name)
        self.proj_labels["Video nguồn"].setText(os.path.basename(p.video_path) or "—")
        self.proj_labels["File SRT"].setText(os.path.basename(p.srt_path) or "—")
        self.proj_labels["Số phụ đề"].setText(str(len(p.cues)))
        self.proj_labels["Số nhóm"].setText(str(len(p.groups)))
