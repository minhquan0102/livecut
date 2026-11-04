"""Bộ icon nét đơn (24x24) vẽ từ SVG nhúng sẵn, đổi màu theo trạng thái."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_R = '<rect x="3" y="4" width="18" height="16" rx="2"/>'
_MAG = '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>'
_SPK = '<path d="M4 9v6h4l5 4V5L8 9z"/>'

_BODY = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "film": _R + '<path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"/>',
    "captions": _R + '<path d="M7 11h3M13 11h4M7 15h6M15 15h2"/>',
    "save": '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3M7 21v-7h10v7"/>',
    "export": '<path d="M12 3v12M7 10l5 5 5-5M4 20h16"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    "back": '<path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5"/>',
    "forward": '<path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"/>',
    "volume": _SPK + '<path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
    "mute": _SPK + '<path d="M17 9l5 6M22 9l-5 6"/>',
    "search": _MAG,
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "panel-left": _R + '<path d="M9 4v16"/>',
    "panel-right": _R + '<path d="M15 4v16"/>',
    "panel-bottom": _R + '<path d="M3 15h18"/>',
    "zoom-in": _MAG + '<path d="M8 11h6M11 8v6"/>',
    "zoom-out": _MAG + '<path d="M8 11h6"/>',
    "fit": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "mark-in": '<path d="M9 4H5v16h4M13 12h8M18 9l3 3-3 3"/>',
    "mark-out": '<path d="M15 4h4v16h-4M3 12h8M6 9l-3 3 3 3"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
    "clean": '<path d="M4 20h16M9 20V9l3-5 3 5v11"/>',
}
_FILLED = {"play", "pause"}


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    body = _BODY[name]
    if name in _FILLED:
        attrs = f'fill="{color}" stroke="{color}" stroke-width="1.5"'
    else:
        attrs = f'fill="none" stroke="{color}" stroke-width="1.8"'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {attrs} '
           f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(scale)
    painter = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))
