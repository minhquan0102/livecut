"""Chuyển đổi thời gian giữa mili-giây và các định dạng hiển thị."""
from __future__ import annotations


def format_clock(ms: int | float) -> str:
    """'MM:SS' hoặc 'H:MM:SS' khi video dài hơn 1 giờ."""
    s = max(0, int(ms)) // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def format_timecode(ms: int | float) -> str:
    """'HH:MM:SS.mmm' – dùng khi cần độ chính xác (nhập IN/OUT, xuất báo cáo)."""
    ms = max(0, int(ms))
    s, milli = divmod(ms, 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}.{milli:03d}"


def format_srt_time(ms: int | float) -> str:
    """'HH:MM:SS,mmm' theo chuẩn SRT."""
    return format_timecode(ms).replace(".", ",")


def parse_timecode(text: str) -> int:
    """Đọc 'H:MM:SS.mmm', 'MM:SS', 'SS' (dấu ',' hoặc '.' đều được) → mili-giây."""
    s = text.strip().replace(",", ".")
    if not s:
        raise ValueError("Thời gian trống")
    frac = 0
    if "." in s:
        s, f = s.split(".", 1)
        if not f.isdigit():
            raise ValueError(f"Thời gian không hợp lệ: {text!r}")
        frac = int(f.ljust(3, "0")[:3])
    parts = s.split(":")
    if len(parts) > 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Thời gian không hợp lệ: {text!r}")
    nums = [int(p) for p in parts]
    if len(nums) >= 2 and nums[-1] >= 60:
        raise ValueError(f"Giây phải nhỏ hơn 60: {text!r}")
    if len(nums) == 3 and nums[1] >= 60:
        raise ValueError(f"Phút phải nhỏ hơn 60: {text!r}")
    while len(nums) < 3:
        nums.insert(0, 0)
    h, m, sec = nums
    return ((h * 60 + m) * 60 + sec) * 1000 + frac
