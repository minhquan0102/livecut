"""Tỷ lệ khung hình và cách đưa video gốc vào khung mới (giống CapCut). Không phụ thuộc Qt.

Ba cách lấp khung:
  crop  : cắt vừa khung; người dùng chọn vùng giữ lại (tâm + thu phóng)
  blur  : giữ toàn cảnh, phần thừa lấp bằng chính video làm mờ
  black : giữ toàn cảnh, phần thừa là viền đen
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# (nhãn, tỉ lệ rộng:cao); None = giữ tỉ lệ gốc
ASPECTS: list[tuple[str, tuple[int, int] | None]] = [
    ("Gốc (giữ tỉ lệ video)", None),
    ("9:16  dọc — TikTok, Reels, Shorts", (9, 16)),
    ("16:9  ngang — YouTube", (16, 9)),
    ("1:1  vuông", (1, 1)),
    ("4:5  Facebook, Instagram", (4, 5)),
    ("3:4  dọc", (3, 4)),
]

MODES: list[tuple[str, str]] = [
    ("Cắt vừa khung — kéo để chọn vùng giữ lại", "crop"),
    ("Giữ toàn cảnh, nền mờ", "blur"),
    ("Giữ toàn cảnh, viền đen", "black"),
]

MAX_ZOOM = 4.0


@dataclass
class FrameSpec:
    aspect: tuple[int, int]
    mode: str = "crop"         # "crop" | "blur" | "black"
    cx: float = 0.5            # tâm vùng giữ lại, 0..1 theo chiều rộng / cao video gốc
    cy: float = 0.5
    zoom: float = 1.0          # 1 = vùng lớn nhất có tỉ lệ đó; lớn hơn = phóng to vào giữa


def _even(x: float, lo: int = 2) -> int:
    return max(lo, int(x) // 2 * 2)


def output_size(aspect: tuple[int, int], short_side: int) -> tuple[int, int]:
    rw, rh = aspect
    if rw <= rh:
        w, h = short_side, short_side * rh / rw
    else:
        w, h = short_side * rw / rh, short_side
    return _even(round(w)), _even(round(h))


def size_choices(aspect: tuple[int, int]) -> list[tuple[str, int, int]]:
    out = []
    for short, tag in ((1080, " (khuyên dùng)"), (720, ""), (480, "")):
        w, h = output_size(aspect, short)
        out.append((f"{w}×{h}{tag}", w, h))
    return out


def crop_rect_f(src_w: int, src_h: int, aspect: tuple[int, int], cx: float, cy: float,
                zoom: float) -> tuple[float, float, float, float]:
    """Vùng giữ lại (x, y, w, h) theo điểm ảnh gốc, chưa làm tròn; luôn nằm trọn trong video."""
    ar = aspect[0] / aspect[1]
    if src_w / src_h >= ar:
        h0, w0 = float(src_h), src_h * ar
    else:
        w0, h0 = float(src_w), src_w / ar
    zoom = min(max(1.0, zoom), MAX_ZOOM)
    w, h = w0 / zoom, h0 / zoom
    x = min(max(cx * src_w - w / 2, 0.0), src_w - w)
    y = min(max(cy * src_h - h / 2, 0.0), src_h - h)
    return x, y, w, h


def crop_rect(src_w: int, src_h: int, aspect: tuple[int, int], cx: float, cy: float,
              zoom: float) -> tuple[int, int, int, int]:
    """Như trên nhưng làm tròn xuống số chẵn (yuv420p cần kích thước và vị trí chẵn)."""
    x, y, w, h = crop_rect_f(src_w, src_h, aspect, cx, cy, zoom)
    return _even(x, 0), _even(y, 0), _even(w), _even(h)


def video_filter(spec: FrameSpec, src_w: int, src_h: int, out_w: int, out_h: int,
                 tail: str) -> tuple[list[str], list[str]]:
    """Trả về (tham số lọc, tham số -map video). `tail` là phần cuối chung, ví dụ 'fps=30,format=yuv420p'."""
    if spec.mode == "crop":
        x, y, w, h = crop_rect(src_w, src_h, spec.aspect, spec.cx, spec.cy, spec.zoom)
        return ["-vf", f"crop={w}:{h}:{x}:{y},scale={out_w}:{out_h}:flags=lanczos,{tail}"], ["-map", "0:v:0"]

    # giữ toàn cảnh: tính sẵn kích thước vừa khung (số chẵn) để không phụ thuộc cách lọc làm tròn
    fit = min(out_w / src_w, out_h / src_h)
    fw, fh = _even(src_w * fit), _even(src_h * fit)
    fw, fh = min(fw, out_w), min(fh, out_h)
    ox, oy = (out_w - fw) // 2 // 2 * 2, (out_h - fh) // 2 // 2 * 2
    if spec.mode == "black":
        vf = (f"scale={fw}:{fh}:flags=lanczos,pad={out_w}:{out_h}:{ox}:{oy}:black,{tail}")
        return ["-vf", vf], ["-map", "0:v:0"]

    cover = max(out_w / src_w, out_h / src_h)
    bw, bh = int(src_w * cover) + 2, int(src_h * cover) + 2
    sw, sh = max(2, out_w // 8), max(2, out_h // 8)     # làm mờ ở độ phân giải thấp cho nhanh
    graph = (f"[0:v]split=2[bg][fg];"
             f"[bg]scale={bw}:{bh},crop={out_w}:{out_h},scale={sw}:{sh},boxblur=2:2,scale={out_w}:{out_h}[b];"
             f"[fg]scale={fw}:{fh}:flags=lanczos[f];"
             f"[b][f]overlay={ox}:{oy},{tail}[v]")
    return ["-filter_complex", graph], ["-map", "[v]"]


def extract_frame(ffmpeg: str, src: str, ms: int, out_path: str, max_width: int = 800,
                  timeout: float = 20.0) -> bool:
    """Lấy một khung hình làm hình tham chiếu cho khung chọn vùng. True nếu thành công."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    cmd = [ffmpeg, "-y", "-nostdin", "-loglevel", "error", "-ss", f"{max(0, ms) / 1000:.3f}", "-i", src,
           "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2", "-q:v", "3", out_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return False
    p = Path(out_path)
    return p.is_file() and p.stat().st_size > 0
