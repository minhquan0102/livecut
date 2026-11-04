"""Thanh công cụ trên cùng."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from . import icons
from .theme import P
from .widgets import IconButton

NOT_YET = "Chưa hoạt động: có từ giai đoạn {n} ({what})."


class TopBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        brand = QLabel()
        brand.setObjectName("Brand")
        brand.setPixmap(icons.pixmap("scissors", P["on_accent"], 18))
        brand.setFixedSize(30, 30)
        brand.setAlignment(Qt.AlignCenter)
        title = QLabel("LiveCut Studio")
        title.setObjectName("AppTitle")
        self.project_label = QLabel("Dự án mới")
        self.project_label.setObjectName("Muted")
        lay.addWidget(brand)
        lay.addSpacing(4)
        lay.addWidget(title)
        lay.addSpacing(10)
        lay.addWidget(self.project_label)
        lay.addSpacing(18)

        self.import_video = IconButton("film", "Nhập video (Ctrl+O)", label="Nhập video")
        self.import_srt = IconButton("captions", "Nhập file phụ đề SRT (Ctrl+Shift+O)", label="Nhập SRT")
        self.open_project = IconButton("folder", "Mở dự án (Ctrl+P)")
        self.save_project = IconButton("save", "Lưu dự án (Ctrl+S)")
        for w in (self.import_video, self.import_srt, self._sep(), self.open_project, self.save_project):
            lay.addWidget(w)
        lay.addStretch(1)

        self.btn_sidebar = IconButton("panel-left", "Ẩn/hiện thanh bên (Ctrl+B)", checkable=True)
        self.btn_bottom = IconButton("panel-bottom", "Ẩn/hiện timeline (Ctrl+T)", checkable=True)
        self.btn_right = IconButton("panel-right", "Ẩn/hiện danh sách phụ đề (Ctrl+R)", checkable=True)
        for b in (self.btn_sidebar, self.btn_bottom, self.btn_right):
            b.setChecked(True)
            lay.addWidget(b)
        self.settings = IconButton("settings", "Công cụ và FFmpeg")
        lay.addWidget(self._sep())
        lay.addWidget(self.settings)
        lay.addSpacing(6)
        self.export = IconButton("export", NOT_YET.format(n=8, what="cắt và xuất video"),
                                 label="Xuất video", variant="primary")
        self.export.setEnabled(False)
        lay.addWidget(self.export)

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setObjectName("VSep")
        s.setFixedSize(1, 20)
        return s

    def set_project_name(self, name: str) -> None:
        self.project_label.setText(name)
