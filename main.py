"""Điểm vào của LiveCut Studio."""
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LiveCut Studio")
    app.setOrganizationName("LiveCutStudio")
    apply_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
