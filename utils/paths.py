"""Đường dẫn ứng dụng, thư mục tạm và dọn dẹp."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

APP_NAME = "LiveCutStudio"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bin_dir() -> Path:
    return app_dir() / "bin"


def temp_dir() -> Path:
    p = Path(tempfile.gettempdir()) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def temp_usage_bytes() -> int:
    total = 0
    for f in temp_dir().rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def clear_temp() -> int:
    """Xóa file tạm của ứng dụng, trả về số byte đã giải phóng."""
    before = temp_usage_bytes()
    for child in temp_dir().iterdir():
        try:
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        except OSError:
            pass
    return max(0, before - temp_usage_bytes())


def human_size(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
