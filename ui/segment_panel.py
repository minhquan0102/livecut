"""Danh sách đoạn video đã chọn. Giai đoạn 1 chỉ có trạng thái trống; đoạn được tạo từ giai đoạn 5-6."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QStackedWidget

from .widgets import EmptyState, Panel


class SegmentPanel(Panel):
    def __init__(self, parent=None) -> None:
        super().__init__("Đoạn video", parent)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Small")
        self.add_action(self.count_label)
        self.empty = EmptyState("scissors", "Chưa có đoạn nào",
                                "Đoạn được tạo khi bạn chọn phụ đề (giai đoạn 5) hoặc khoanh vùng trên timeline (giai đoạn 6).")
        self.list = QListWidget()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.list)
        self.body.addWidget(self.stack, 1)
