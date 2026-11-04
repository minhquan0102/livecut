"""Đọc thông tin video bằng ffprobe (chạy trong luồng nền, không khóa UI)."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from fractions import Fraction

from .ffmpeg_locator import hidden_flags, require_binary


class ProbeError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    path: str
    duration_ms: int
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    has_audio: bool
    size_bytes: int
    bitrate: int


def _fps(text: str) -> float:
    try:
        f = Fraction(text)
        return float(f)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str) -> VideoInfo:
    exe = require_binary("ffprobe")
    proc = subprocess.run(
        [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=60, errors="replace", creationflags=hidden_flags())
    if proc.returncode != 0:
        raise ProbeError(proc.stderr.strip() or "ffprobe không đọc được file này.")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProbeError("File không có luồng hình ảnh.")
    fmt = data.get("format", {})
    dur = fmt.get("duration") or video.get("duration") or 0
    return VideoInfo(
        path=path,
        duration_ms=int(float(dur) * 1000),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_fps(video.get("avg_frame_rate", "0/1")),
        video_codec=video.get("codec_name", "?"),
        audio_codec=audio.get("codec_name", "") if audio else "",
        has_audio=audio is not None,
        size_bytes=int(fmt.get("size") or os.path.getsize(path)),
        bitrate=int(fmt.get("bit_rate") or 0),
    )
