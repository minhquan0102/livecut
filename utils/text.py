"""Chuẩn hóa văn bản để tìm kiếm tiếng Việt không phân biệt dấu."""
from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").lower()
