"""Hộp nhập thời gian bắt đầu / kết thúc của một khoảng bằng tay."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout)

from editor.ranges import validate_range
from utils.timecode import format_timecode

class RangeDialog(QDialog):
    def __init__(self, parent, start_ms: int, end_ms: int, duration_ms: int, editing: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sửa khoảng" if editing else "Thêm khoảng bằng thời gian")
        self.setMinimumWidth(380)
        self._duration = duration_ms
        self.result_range: tuple[int, int] | None = None
        self.start = QLineEdit(format_timecode(start_ms))
        self.end = QLineEdit(format_timecode(end_ms))
        form = QFormLayout()
        form.addRow("Bắt đầu", self.start)
        form.addRow("Kết thúc", self.end)
        hint = QLabel("Nhập dạng 1:23:45.500, 12:30 hoặc 90 (giây). Dấu , hoặc . đều được.")
        hint.setObjectName("Small")
        hint.setWordWrap(True)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #EF6B78;")
        self.error.setWordWrap(True)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Lưu" if editing else "Thêm")
        box.button(QDialogButtonBox.Cancel).setText("Hủy")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(self.error)
        lay.addWidget(box)

    def _accept(self) -> None:
        try:
            self.result_range = validate_range(self.start.text(), self.end.text(), self._duration)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
