"""Danh sách phụ đề SRT, tìm kiếm không phân biệt dấu và khung nội dung đã chọn."""
from __future__ import annotations

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QRectF, QSize, QSortFilterProxyModel, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListView, QPlainTextEdit, QStackedWidget,
                               QStyle, QStyledItemDelegate)

from subtitle.srt import Cue
from utils.text import fold
from utils.timecode import format_clock
from .theme import P
from .widgets import EmptyState, IconButton, Panel

MARK_COLORS = {"selected": P["ok"], "review": P["warn"], "removed": P["danger"]}
CUE_ROLE = int(Qt.UserRole) + 1
FOLD_ROLE = int(Qt.UserRole) + 2


class CueModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self._cues: list[Cue] = []
        self._folded: list[str] = []

    def set_cues(self, cues: list[Cue]) -> None:
        self.beginResetModel()
        self._cues = list(cues)
        self._folded = [fold(c.text) for c in self._cues]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cues)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self._cues[index.row()].text
        if role == CUE_ROLE:
            return self._cues[index.row()]
        if role == FOLD_ROLE:
            return self._folded[index.row()]
        return None


class CueFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._needle = ""

    def set_needle(self, text: str) -> None:
        self._needle = fold(text.strip())
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent) -> bool:
        if not self._needle:
            return True
        return self._needle in self.sourceModel().index(row, 0, parent).data(FOLD_ROLE)


class CueDelegate(QStyledItemDelegate):
    PAD = 10
    MAX_LINES = 3

    def sizeHint(self, option, index) -> QSize:
        cue = index.data(CUE_ROLE)
        w = max(option.rect.width(), 240) - 2 * self.PAD - 12
        fm = option.fontMetrics
        text_h = min(fm.boundingRect(0, 0, w, 10_000, int(Qt.TextWordWrap), cue.text).height(),
                     fm.lineSpacing() * self.MAX_LINES)
        return QSize(option.rect.width(), 2 * self.PAD + 18 + text_h + 4)

    def paint(self, p: QPainter, option, index) -> None:
        cue = index.data(CUE_ROLE)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(4, 2, -4, -2)
        if option.state & QStyle.State_Selected:
            p.setBrush(QColor(P["accent_dim"]))
        elif option.state & QStyle.State_MouseOver:
            p.setBrush(QColor(P["hover"]))
        else:
            p.setBrush(Qt.NoBrush)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 8, 8)
        if cue.mark in MARK_COLORS:
            p.setBrush(QColor(MARK_COLORS[cue.mark]))
            p.drawRoundedRect(QRectF(r.left() + 3, r.top() + 8, 3, r.height() - 16), 1.5, 1.5)
        x = r.left() + self.PAD + 6
        w = r.width() - 2 * self.PAD - 6
        small = option.font
        small.setPointSizeF(max(8.0, small.pointSizeF() - 1.5))
        p.setFont(small)
        p.setPen(QColor(P["accent_hi"]))
        p.drawText(QRectF(x, r.top() + self.PAD, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{format_clock(cue.start_ms)} – {format_clock(cue.end_ms)}")
        big = option.font
        big.setPointSizeF(small.pointSizeF() + 1.5)
        p.setFont(big)
        p.setPen(QColor(P["text"]))
        p.setClipRect(r)
        p.drawText(QRectF(x, r.top() + self.PAD + 20, w, r.height() - self.PAD - 20),
                   int(Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft), cue.text)
        p.restore()


class CueListView(QListView):
    """Tính lại chiều cao dòng khi đổi độ rộng (có trì hoãn để kéo splitter vẫn mượt)."""

    def __init__(self) -> None:
        super().__init__()
        self._relayout = QTimer(self)
        self._relayout.setSingleShot(True)
        self._relayout.setInterval(60)
        self._relayout.timeout.connect(self.doItemsLayout)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._relayout.start()


class SubtitlePanel(Panel):
    cueActivated = Signal(int)          # start_ms của dòng đang chọn
    selectionChangedCues = Signal(list)  # các Cue đang chọn, theo thời gian
    importRequested = Signal()
    chosenChanged = Signal()             # tập dòng "đã chọn vào video" vừa thay đổi

    def __init__(self, parent=None) -> None:
        super().__init__("Phụ đề", parent)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Small")
        self.add_action(self.count_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm trong phụ đề (không cần gõ dấu)")
        self.search.setClearButtonEnabled(True)
        self.body.addWidget(self.search)
        self.btn_add_all = IconButton("plus", "Đưa tất cả các dòng đang hiện sau khi tìm vào video",
                                      label="Thêm tất cả kết quả")
        self.btn_add_all.hide()
        self.body.addWidget(self.btn_add_all)

        self.model = CueModel()
        self.proxy = CueFilter()
        self.proxy.setSourceModel(self.model)
        self.view = CueListView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(CueDelegate(self.view))
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setMouseTracking(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setUniformItemSizes(False)
        self.view.setLayoutMode(QListView.Batched)
        self.view.setBatchSize(300)

        self.empty = EmptyState("captions", "Chưa có phụ đề", "Nhập file SRT của video để chọn đoạn theo lời nói.",
                                "Nhập SRT")
        self.empty.actionClicked.connect(self.importRequested)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.view)
        self.body.addWidget(self.stack, 1)

        self.detail_title = QLabel("Nội dung đã chọn")
        self.detail_title.setObjectName("Small")
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(96)
        self.detail.setPlaceholderText("Chọn một hoặc nhiều dòng phụ đề.")
        self.body.addWidget(self.detail_title)
        self.body.addWidget(self.detail)

        self.btn_add = IconButton("plus", "Đưa các dòng đang chọn vào video (phím Enter)",
                                  label="Thêm vào video", variant="primary")
        self.btn_remove = IconButton("trash", "Bỏ các dòng đang chọn khỏi video (phím Delete)",
                                     label="Bỏ khỏi video")
        acts = QHBoxLayout()
        acts.setSpacing(6)
        acts.addWidget(self.btn_add, 1)
        acts.addWidget(self.btn_remove, 1)
        self.body.addLayout(acts)
        self.btn_add.clicked.connect(lambda: self.set_mark_on_selection("selected"))
        self.btn_remove.clicked.connect(lambda: self.set_mark_on_selection(""))
        for keys, mark in (((Qt.Key_Return, Qt.Key_Enter), "selected"), ((Qt.Key_Delete,), "")):
            for k in keys:
                sc = QShortcut(QKeySequence(k), self.view)
                sc.setContext(Qt.WidgetShortcut)
                sc.activated.connect(lambda m=mark: self.set_mark_on_selection(m))

        self.search.textChanged.connect(self._on_search)
        self.btn_add_all.clicked.connect(self.add_all_matches)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)
        self.view.selectionModel().currentChanged.connect(self._on_current)

    def set_cues(self, cues: list[Cue]) -> None:
        self.model.set_cues(cues)
        self.stack.setCurrentIndex(1 if cues else 0)
        self.detail.clear()
        self._update_count()

    def _update_count(self) -> None:
        total, shown = self.model.rowCount(), self.proxy.rowCount()
        if total == 0:
            self.count_label.setText("")
        elif shown == total:
            self.count_label.setText(f"{total:,} dòng".replace(",", "."))
        else:
            self.count_label.setText(f"{shown:,} / {total:,}".replace(",", "."))

    def _on_search(self, text: str) -> None:
        self.proxy.set_needle(text)
        self._update_count()
        shown = self.proxy.rowCount()
        has_query = bool(text.strip()) and shown > 0
        self.btn_add_all.setVisible(has_query)
        if has_query:
            self.btn_add_all.set_label(f"Thêm tất cả {shown:,} kết quả".replace(",", "."))

    def add_all_matches(self) -> None:
        """Đánh dấu mọi dòng đang hiện (khớp từ khóa) là đã chọn vào video."""
        changed = False
        for row in range(self.proxy.rowCount()):
            cue = self.proxy.index(row, 0).data(CUE_ROLE)
            if cue.mark != "selected":
                cue.mark = "selected"
                changed = True
        if changed:
            self.view.viewport().update()
            self.chosenChanged.emit()

    def set_mark_on_selection(self, mark: str) -> None:
        cues = self.selected_cues()
        if not cues:
            return
        for c in cues:
            c.mark = mark
        self.view.viewport().update()
        self.chosenChanged.emit()

    def refresh_marks(self) -> None:
        self.view.viewport().update()

    def selected_cues(self) -> list[Cue]:
        rows = self.view.selectionModel().selectedRows()
        return sorted((r.data(CUE_ROLE) for r in rows), key=lambda c: c.start_ms)

    def _on_selection(self, *_args) -> None:
        cues = self.selected_cues()
        if len(cues) == 1:
            self.detail.setPlainText(cues[0].text)
        elif cues:
            self.detail.setPlainText(
                f"{len(cues)} dòng, từ {format_clock(cues[0].start_ms)} đến {format_clock(max(c.end_ms for c in cues))}.")
        else:
            self.detail.clear()
        self.selectionChangedCues.emit(cues)

    def _on_current(self, current, _previous) -> None:
        cue = current.data(CUE_ROLE) if current.isValid() else None
        if cue is not None:
            self.cueActivated.emit(cue.start_ms)
