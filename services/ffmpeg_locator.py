"""Tìm FFmpeg/FFprobe: ưu tiên thư mục bin/ cạnh ứng dụng, sau đó PATH."""
from __future__ import annotations

import os
import shutil
import subprocess

from utils.paths import bin_dir


class FFmpegNotFoundError(RuntimeError):
    pass


def hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def find_binary(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    local = bin_dir() / exe
    if local.is_file():
        return str(local)
    return shutil.which(name)


def require_binary(name: str) -> str:
    path = find_binary(name)
    if not path:
        raise FFmpegNotFoundError(
            f"Không tìm thấy {name}. Hãy đặt {name}.exe vào thư mục bin/ cạnh ứng dụng "
            "hoặc thêm FFmpeg vào PATH.")
    return path


def get_version(path: str) -> str:
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10,
                             creationflags=hidden_flags(), errors="replace").stdout
        return out.splitlines()[0] if out else "không rõ phiên bản"
    except (OSError, subprocess.SubprocessError):
        return "không chạy được"


def detect() -> dict[str, tuple[str | None, str]]:
    result = {}
    for name in ("ffmpeg", "ffprobe"):
        p = find_binary(name)
        result[name] = (p, get_version(p) if p else "")
    return result
