"""Đọc, kiểm tra và ghi file SRT. Không phụ thuộc Qt nên kiểm thử được độc lập."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from utils.timecode import format_clock, format_srt_time

_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
MARKS = ("", "selected", "review", "removed")


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    mark: str = ""  # "", "selected", "review", "removed"

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class ParseResult:
    cues: list[Cue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str


def _ms(h: str, m: str, s: str, frac: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def parse_srt(text: str) -> ParseResult:
    result = ParseResult()
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return result
    for n, block in enumerate(re.split(r"\n[ \t]*\n", text), start=1):
        lines = block.split("\n")
        ti = next((i for i, ln in enumerate(lines[:2]) if _TIME.search(ln)), None)
        if ti is None:
            result.warnings.append(f"Khối {n}: không có dòng thời gian, đã bỏ qua.")
            continue
        g = _TIME.search(lines[ti]).groups()  # type: ignore[union-attr]
        start, end = _ms(*g[0:4]), _ms(*g[4:8])
        body = "\n".join(ln.rstrip() for ln in lines[ti + 1:]).strip()
        if ti == 1 and lines[0].strip().isdigit():
            index = int(lines[0].strip())
        else:
            index = len(result.cues) + 1
        result.cues.append(Cue(index, start, end, body))
    return result


def read_srt_file(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1258", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def serialize_srt(cues: list[Cue]) -> str:
    out = []
    for i, c in enumerate(cues, start=1):
        out.append(f"{i}\n{format_srt_time(c.start_ms)} --> {format_srt_time(c.end_ms)}\n{c.text}\n")
    return "\n".join(out)


def validate_cues(cues: list[Cue], duration_ms: int | None = None) -> list[Issue]:
    issues: list[Issue] = []
    if not cues:
        return [Issue("error", "File SRT không có phụ đề nào đọc được.")]
    bad = sum(1 for c in cues if c.end_ms <= c.start_ms)
    if bad:
        issues.append(Issue("warning", f"{bad} phụ đề có thời gian kết thúc không sau thời gian bắt đầu."))
    unordered = sum(1 for a, b in zip(cues, cues[1:]) if b.start_ms < a.start_ms)
    if unordered:
        issues.append(Issue("warning", f"{unordered} phụ đề không theo thứ tự thời gian."))
    overlap = sum(1 for a, b in zip(cues, cues[1:]) if a.start_ms <= b.start_ms < a.end_ms)
    if overlap:
        issues.append(Issue("warning", f"{overlap} cặp phụ đề chồng thời gian lên nhau."))
    if duration_ms and duration_ms > 0:
        last_end = max(c.end_ms for c in cues)
        beyond = sum(1 for c in cues if c.start_ms >= duration_ms)
        if last_end > duration_ms + 2000:
            msg = (f"SRT dài hơn video: phụ đề cuối kết thúc lúc {format_clock(last_end)}, "
                   f"video chỉ dài {format_clock(duration_ms)}.")
            if beyond:
                msg += f" {beyond} phụ đề nằm hoàn toàn ngoài video."
            issues.append(Issue("error", msg))
        elif last_end < duration_ms * 0.5:
            issues.append(Issue(
                "warning",
                f"SRT chỉ phủ đến {format_clock(last_end)} trong video dài {format_clock(duration_ms)}. "
                "Hãy kiểm tra đúng file SRT chưa."))
    return issues
