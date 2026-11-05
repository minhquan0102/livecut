"""Bảng màu, stylesheet và font cho giao diện dark mode."""
from __future__ import annotations

import re

P = {
    "bg": "#0E1014", "panel": "#15181E", "raised": "#1C2028", "hover": "#232833",
    "border": "#262B35", "border_strong": "#363D4A",
    "text": "#E8EAEE", "muted": "#8D95A3", "faint": "#565D6B",
    "accent": "#6C8BFF", "accent_hi": "#8AA3FF", "accent_dim": "#27346B", "on_accent": "#0B0E16",
    "ok": "#38C9A0", "warn": "#F2B84B", "danger": "#EF6B78", "video": "#06070A",
}

_QSS = """
QWidget { color: @text@; background: transparent; }
QMainWindow, QDialog, QMessageBox { background: @bg@; }
#Root { background: @bg@; }
#TopBar { background: @panel@; border-bottom: 1px solid @border@; }
#Brand { background: @accent@; border-radius: 8px; }
#AppTitle { font-size: 15px; font-weight: 700; }
#VSep { background: @border@; }
#Panel, #Rail { background: @panel@; border: 1px solid @border@; border-radius: 10px; }
#PanelHeader { background: transparent; border: none; border-bottom: 1px solid @border@; }
#PanelTitle { font-size: 13px; font-weight: 600; }
#Muted { color: @muted@; }
#Small { color: @muted@; font-size: 12px; }
#Preview { background: @video@; border: 1px solid @border@; border-radius: 10px; }
#Card { background: @raised@; border: 1px solid @border@; border-radius: 8px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 8px; }
QSplitter::handle:vertical { height: 8px; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox {
  background: @raised@; border: 1px solid @border@; border-radius: 8px; padding: 6px 10px;
  selection-background-color: @accent_dim@; }
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus { border-color: @accent@; }
QLineEdit:disabled, QComboBox:disabled { color: @faint@; }
QComboBox::drop-down { border: none; width: 0px; }
QComboBox QAbstractItemView { background: @raised@; border: 1px solid @border_strong@; outline: 0; }
QListView, QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:hover { background: @hover@; }
QListWidget::item:selected { background: @accent_dim@; color: @text@; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @border_strong@; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: @muted@; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong@; border-radius: 3px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: @muted@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: @border_strong@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QSlider::handle:horizontal { background: @text@; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QSlider:disabled::handle:horizontal { background: @faint@; }
QToolTip { background: @raised@; color: @text@; border: 1px solid @border_strong@; padding: 4px 8px; }
QMenu { background: @raised@; border: 1px solid @border_strong@; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: @accent_dim@; }
QStatusBar { background: @panel@; color: @muted@; border-top: 1px solid @border@; }
QStatusBar::item { border: none; }
QPushButton { background: @raised@; border: 1px solid @border_strong@; border-radius: 8px; padding: 6px 14px; }
QPushButton:hover { background: @hover@; }
"""


def build_stylesheet() -> str:
    return re.sub(r"@(\w+)@", lambda m: P[m.group(1)], _QSS)


def apply_theme(app) -> None:
    from PySide6.QtGui import QColor, QFont, QPalette

    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Arial"])
    font.setPointSizeF(10)
    app.setFont(font)
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "raised"),
                      (QPalette.AlternateBase, "panel"), (QPalette.Text, "text"), (QPalette.Button, "raised"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "raised"),
                      (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent_dim"),
                      (QPalette.HighlightedText, "text"), (QPalette.PlaceholderText, "faint")):
        pal.setColor(role, QColor(P[key]))
    app.setPalette(pal)
    app.setStyleSheet(build_stylesheet())
