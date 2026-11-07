"""Cắt các đoạn đã chọn và nối thành một file MP4 bằng FFmpeg. Không phụ thuộc Qt.

Cách làm (nhanh cho video dài, chỉ mã hóa phần được chọn):
  1. Mỗi đoạn: `-ss` đặt TRƯỚC `-i` nên tua thẳng tới vị trí (không giải mã từ đầu file), mã hóa lại để cắt
     chính xác từng khung hình, thêm fade âm thanh cực ngắn ở hai đầu để mối nối không bị tiếng click.
  2. Mọi đoạn dùng cùng thông số (độ phân giải, fps, âm thanh) nên nối bằng concat demuxer với `-c copy`:
     bước nối gần như tức thì.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


class ExportCancelled(RuntimeError):
    pass


class ExportError(RuntimeError):
    pass


@dataclass
class ExportOptions:
    width: int = 0             # width và height cùng > 0 thì đổi kích thước; 0 = giữ nguyên
    height: int = 0
    fps: float = 0.0           # 0 = giữ fps của video gốc (làm tròn)
    crf: int = 21              # càng nhỏ càng nét, file càng lớn
    preset: str = "veryfast"
    audio_bitrate: str = "192k"
    fade_ms: int = 20          # fade âm thanh ở hai đầu mỗi đoạn


def _sec(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def target_size(src_w: int, src_h: int, short_side: int) -> tuple[int, int]:
    """Kích thước mới theo CẠNH NGẮN (đúng cho cả video ngang lẫn video dọc), giữ tỉ lệ, số chẵn."""
    def even(x: float) -> int:
        return max(2, int(round(x / 2)) * 2)
    if src_w <= src_h:
        return even(short_side), even(src_h * short_side / src_w)
    return even(src_w * short_side / src_h), even(short_side)


def resolution_choices(src_w: int, src_h: int) -> list[tuple[str, int, int]]:
    """Danh sách lựa chọn (nhãn, rộng, cao); (0, 0) là giữ nguyên. Chỉ cho phóng to lên 1080p, không thu nhỏ nhầm."""
    choices = [(f"Giữ nguyên ({src_w}×{src_h})", 0, 0)]
    short = min(src_w, src_h)
    for target in (1080, 720, 480):
        if target < short:
            w, h = target_size(src_w, src_h, target)
            choices.append((f"{target}p ({w}×{h})", w, h))
        elif target > short and target == 1080:
            w, h = target_size(src_w, src_h, target)
            choices.append((f"1080p ({w}×{h}) — phóng to", w, h))
    return choices


def effective_fps(opts: ExportOptions, src_fps: float) -> float:
    if opts.fps > 0:
        return opts.fps
    if 5 <= src_fps <= 120:
        return round(src_fps, 3) if abs(src_fps - round(src_fps)) > 0.01 else float(round(src_fps))
    return 30.0


def build_segment_cmd(ffmpeg: str, src: str, start_ms: int, end_ms: int, out: str,
                      opts: ExportOptions, has_audio: bool, src_fps: float) -> list[str]:
    dur = max(1, end_ms - start_ms)
    if opts.width > 0 and opts.height > 0:
        scale = f"scale={opts.width}:{opts.height}:flags=lanczos"        # lanczos giữ nét tốt hơn bicubic mặc định
    else:
        scale = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    vf = f"{scale},fps={effective_fps(opts, src_fps):g},format=yuv420p"
    cmd = [ffmpeg, "-y", "-nostdin", "-loglevel", "error",
           "-ss", _sec(start_ms), "-i", src, "-t", _sec(dur),
           "-map", "0:v:0"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", opts.preset, "-crf", str(opts.crf),
            "-video_track_timescale", "90000"]
    if has_audio:
        fade = min(opts.fade_ms, dur // 2) / 1000
        af = (f"afade=t=in:st=0:d={fade:.3f},"
              f"afade=t=out:st={max(0.0, dur / 1000 - fade):.3f}:d={fade:.3f}")
        cmd += ["-af", af, "-c:a", "aac", "-strict", "-2", "-b:a", opts.audio_bitrate, "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", out]
    return cmd


def write_concat_list(paths: Sequence[str], list_path: str) -> None:
    lines = []
    for p in paths:
        escaped = p.replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    Path(list_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_concat_cmd(ffmpeg: str, list_path: str, out: str) -> list[str]:
    return [ffmpeg, "-y", "-nostdin", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", "-movflags", "+faststart", out]


def parse_out_time_ms(line: str) -> int | None:
    """Đọc 'out_time_us=1234567' (hoặc out_time_ms, cùng đơn vị micro-giây) -> mili-giây."""
    for key in ("out_time_us=", "out_time_ms="):
        if line.startswith(key):
            try:
                return max(0, int(line[len(key):]) // 1000)
            except ValueError:
                return None
    return None


def _run(cmd: list[str], cancelled: Callable[[], bool], on_time: Callable[[int], None] | None = None) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags)
    tail: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancelled():
                proc.kill()
                raise ExportCancelled()
            line = line.strip()
            t = parse_out_time_ms(line)
            if t is not None:
                if on_time:
                    on_time(t)
            elif line and "=" not in line.split(" ")[0]:
                tail.append(line)
                tail = tail[-12:]
        rc = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout:
            proc.stdout.close()
    if cancelled():
        raise ExportCancelled()
    if rc != 0:
        raise ExportError("FFmpeg báo lỗi:\n" + "\n".join(tail[-8:]))


def export_ranges(ffmpeg: str, src: str, ranges: Sequence[tuple[int, int]], out_path: str,
                  opts: ExportOptions, has_audio: bool, src_fps: float, work_dir: str,
                  on_progress: Callable[[float, str], None] | None = None,
                  cancelled: Callable[[], bool] = lambda: False) -> str:
    """Xuất các đoạn (start_ms, end_ms) thành một file. Trả về đường dẫn file."""
    if not ranges:
        raise ExportError("Chưa có đoạn nào để xuất.")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    total = sum(e - s for s, e in ranges) or 1
    done = 0
    parts: list[str] = []
    n = len(ranges)
    try:
        for i, (s, e) in enumerate(ranges, 1):
            part = str(work / f"part_{i:04d}.mp4")
            dur = e - s

            def on_time(t: int, base=done, i=i) -> None:
                if on_progress:
                    on_progress(min(0.98, (base + min(t, dur)) / total), f"Đang cắt đoạn {i}/{n}")

            _run(build_segment_cmd(ffmpeg, src, s, e, part, opts, has_audio, src_fps), cancelled, on_time)
            parts.append(part)
            done += dur
            if on_progress:
                on_progress(min(0.98, done / total), f"Đang cắt đoạn {i}/{n}")
        if on_progress:
            on_progress(0.99, "Đang nối các đoạn")
        list_path = str(work / "list.txt")
        write_concat_list(parts, list_path)
        tmp_out = str(work / "joined.mp4")
        _run(build_concat_cmd(ffmpeg, list_path, tmp_out), cancelled)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_out, out_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if on_progress:
        on_progress(1.0, "Hoàn tất")
    return out_path
