"""Danh sách đoạn video được tạo từ các dòng phụ đề đã chọn, có đệm và nút xem thử liên tiếp."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QStackedWidget)

from editor.ranges import Range, range_key, total_ms
from utils.timecode import format_clock
from .widgets import EmptyState, IconButton, Panel

MAX_TEXT = 140
KEY_ROLE = int(Qt.UserRole) + 1


class SegmentPanel(Panel):
    previewRequested = Signal()
    clearRequested = Signal()
    rangeActivated = Signal(int)     # start_ms của đoạn được nhấp
    paddingChanged = Signal()
    orderChanged = Signal(list)      # danh sách khóa đoạn theo thứ tự mới sau khi kéo thả
    sortRequested = Signal()         # trả về thứ tự theo thời gian
    rangeClicked = Signal(int)       # khóa của đoạn được nhấp (âm = khoảng thủ công)
    rangeEditRequested = Signal(int) # nhấp đúp vào khoảng thủ công -> nhập giờ
    removeRequested = Signal(list)   # khóa các đoạn cần xóa

    def __init__(self, parent=None) -> None:
        super().__init__("Đoạn video", parent)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Small")
        self.btn_sort = IconButton("layers", "Sắp lại các đoạn theo thứ tự thời gian trong video")
        self.btn_remove = IconButton("x", "Xóa đoạn đang chọn khỏi video (phím Delete)")
        self.btn_clear = IconButton("trash", "Bỏ chọn tất cả các đoạn")
        self.btn_preview = IconButton("play", "Xem thử lần lượt các đoạn đã chọn như một video",
                                      label="Xem thử", variant="primary")
        for w in (self.count_label, self.btn_remove, self.btn_sort, self.btn_clear, self.btn_preview):
            self.add_action(w)
        self.btn_remove.setEnabled(False)
        self.btn_sort.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.btn_preview.setEnabled(False)

        pad = QHBoxLayout()
        pad.setSpacing(6)
        self.pad_before = self._spin("Thêm thời gian trước mỗi đoạn để không cắt mất đầu câu")
        self.pad_after = self._spin("Thêm thời gian sau mỗi đoạn để không cắt mất cuối câu")
        lab1, lab2 = QLabel("Đệm trước"), QLabel("sau")
        lab1.setObjectName("Small")
        lab2.setObjectName("Small")
        for w in (lab1, self.pad_before, lab2, self.pad_after):
            pad.addWidget(w)
        pad.addStretch(1)
        self.body.addLayout(pad)

        self.empty = EmptyState("scissors", "Chưa có đoạn nào",
                                "Chọn các dòng phụ đề rồi bấm “Thêm vào video”, hoặc kéo trên timeline / bấm I và O để chọn khoảng tự do.")
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)   # kéo thả để đổi thứ tự
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setToolTip("Kéo thả để đổi thứ tự các đoạn. Video xuất sẽ theo đúng thứ tự này.")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.list)
        self.body.addWidget(self.stack, 1)

        self.pad_before.valueChanged.connect(lambda _v: self.paddingChanged.emit())
        self.pad_after.valueChanged.connect(lambda _v: self.paddingChanged.emit())
        self.btn_preview.clicked.connect(self.previewRequested)
        self.btn_clear.clicked.connect(self.clearRequested)
        self.btn_sort.clicked.connect(self.sortRequested)
        # emit sau khi thao tác kéo thả kết thúc (không dựng lại danh sách ngay trong lúc đang thả)
        self.list.model().rowsMoved.connect(lambda *_a: QTimer.singleShot(0, self._emit_order))
        self.list.itemClicked.connect(self._on_clicked)
        self.list.itemDoubleClicked.connect(self._on_double)
        self.btn_remove.clicked.connect(self._emit_remove)
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.list)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(self._emit_remove)
        self.list.itemSelectionChanged.connect(
            lambda: self.btn_remove.setEnabled(bool(self.list.selectedItems())))

    def _on_clicked(self, it) -> None:
        self.rangeActivated.emit(int(it.data(Qt.UserRole)))
        self.rangeClicked.emit(int(it.data(KEY_ROLE)))

    def _on_double(self, it) -> None:
        if int(it.data(KEY_ROLE)) < 0:
            self.rangeEditRequested.emit(int(it.data(KEY_ROLE)))

    def _emit_remove(self) -> None:
        keys = [int(it.data(KEY_ROLE)) for it in self.list.selectedItems()]
        if keys:
            self.removeRequested.emit(keys)

    @staticmethod
    def _spin(tip: str) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0.0, 5.0)
        s.setSingleStep(0.1)
        s.setDecimals(1)
        s.setValue(0.3)
        s.setSuffix(" s")
        s.setFixedWidth(78)
        s.setToolTip(tip)
        return s

    def padding_ms(self) -> tuple[int, int]:
        return round(self.pad_before.value() * 1000), round(self.pad_after.value() * 1000)

    def set_ranges(self, ranges: list[Range], cues_by_index: dict) -> None:
        self.list.clear()
        for n, r in enumerate(ranges, 1):
            text = " ".join(cues_by_index[i].text.replace("\n", " ")
                            for i in r.cue_indexes if i in cues_by_index)
            if r.manual:
                text = "✂ Khoảng tự chọn — nhấp để chỉnh trên timeline, nhấp đúp để nhập giờ"
            if len(text) > MAX_TEXT:
                text = text[:MAX_TEXT].rstrip() + "…"
            item = QListWidgetItem(
                f"{n:02d}   {format_clock(r.start_ms)} → {format_clock(r.end_ms)}   ·   "
                f"{r.duration_ms / 1000:.1f}s\n{text}")
            item.setData(Qt.UserRole, r.start_ms)
            item.setData(KEY_ROLE, range_key(r))
            self.list.addItem(item)
        self.stack.setCurrentIndex(1 if ranges else 0)
        self.btn_clear.setEnabled(bool(ranges))
        self.btn_sort.setEnabled(len(ranges) > 1)
        self.count_label.setText(f"{len(ranges)} đoạn · {format_clock(total_ms(ranges))}" if ranges else "")

    def _emit_order(self) -> None:
        self.orderChanged.emit([self.list.item(i).data(KEY_ROLE) for i in range(self.list.count())])

    def set_preview_enabled(self, on: bool) -> None:
        self.btn_preview.setEnabled(on)

    def set_previewing(self, on: bool) -> None:
        self.btn_preview.set_icon_name("pause" if on else "play")
        self.btn_preview.set_label("Dừng" if on else "Xem thử")
        if not on:
            self.list.clearSelection()

    def highlight(self, row: int) -> None:
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)       # không phát itemClicked nên không gây seek
            self.list.scrollToItem(self.list.item(row))
