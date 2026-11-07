"""Kiểm thử xuất video bằng FFmpeg thật trên video giả lập (tự bỏ qua nếu máy không có ffmpeg)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from export.exporter import (ExportCancelled, ExportOptions, build_segment_cmd, export_ranges,
                             parse_out_time_ms, resolution_choices, target_size, write_concat_list)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class PureTests(unittest.TestCase):
    def test_target_size_uses_short_side_for_portrait_and_landscape(self):
        self.assertEqual(target_size(720, 1280, 1080), (1080, 1920))
        self.assertEqual(target_size(720, 1280, 480), (480, 854))
        self.assertEqual(target_size(1920, 1080, 720), (1280, 720))

    def test_portrait_720x1280_never_offers_a_downscale_labelled_1080p(self):
        # lỗi cũ: video dọc 720x1280 chọn "1080p" bị thu nhỏ còn 608x1080
        ch = resolution_choices(720, 1280)
        self.assertEqual(ch[0][1:], (0, 0))
        self.assertIn((1080, 1920), [c[1:] for c in ch])
        self.assertTrue(all(w >= 2 and h >= 2 and w % 2 == 0 and h % 2 == 0 for _l, w, h in ch[1:]))
        self.assertTrue(any("phóng to" in c[0] for c in ch if c[1:] == (1080, 1920)))
        self.assertIn((480, 854), [c[1:] for c in ch])

    def test_landscape_1080p_source_offers_only_downscales(self):
        sizes = [c[1:] for c in resolution_choices(1920, 1080)]
        self.assertEqual(sizes, [(0, 0), (1280, 720), (854, 480)])

    def test_lanczos_scaler_used(self):
        cmd = build_segment_cmd("ffmpeg", "a.mp4", 0, 1000, "o.mp4", ExportOptions(width=1080, height=1920), True, 30)
        self.assertIn("scale=1080:1920:flags=lanczos", cmd[cmd.index("-vf") + 1])

    def test_parse_progress(self):
        self.assertEqual(parse_out_time_ms("out_time_us=2500000"), 2500)
        self.assertIsNone(parse_out_time_ms("frame=10"))
        self.assertIsNone(parse_out_time_ms("out_time_us=N/A"))

    def test_seek_before_input_and_fade(self):
        cmd = build_segment_cmd("ffmpeg", "a.mp4", 10_000, 12_500, "o.mp4", ExportOptions(), True, 30)
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-t") + 1], "2.500")
        self.assertIn("afade=t=in", cmd[cmd.index("-af") + 1])
        i = cmd.index("-strict")                     # FFmpeg cũ coi AAC là thử nghiệm, cần -strict -2
        self.assertEqual(cmd[i + 1], "-2")

    def test_no_audio_uses_an(self):
        cmd = build_segment_cmd("ffmpeg", "a.mp4", 0, 1000, "o.mp4", ExportOptions(), False, 30)
        self.assertIn("-an", cmd)
        self.assertNotIn("-af", cmd)

    def test_concat_list_escapes_quote(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.txt")
            write_concat_list(["C:\\tmp\\it's.mp4"], p)
            self.assertEqual(open(p, encoding="utf-8").read().strip(), "file 'C:/tmp/it'\\''s.mp4'")


@unittest.skipUnless(FFMPEG and FFPROBE, "cần ffmpeg và ffprobe")
class RealExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.with_audio = os.path.join(cls.dir, "a.mp4")
        cls.no_audio = os.path.join(cls.dir, "n.mp4")
        base = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=640x360:rate=30:duration=30"]
        subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:duration=30", "-g", "150",
                               "-c:v", "libx264", "-c:a", "aac", "-shortest", cls.with_audio], check=True)
        subprocess.run(base + ["-c:v", "libx264", cls.no_audio], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def probe(self, path):
        out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format",
                              "-show_streams", path], capture_output=True, text=True, check=True).stdout
        d = json.loads(out)
        kinds = [s["codec_type"] for s in d["streams"]]
        return float(d["format"]["duration"]), kinds, d["streams"]

    def run_export(self, src, ranges, has_audio=True, cancelled=lambda: False, progress=None):
        out = os.path.join(self.dir, "out.mp4")
        work = os.path.join(self.dir, "work")
        export_ranges(FFMPEG, src, ranges, out, ExportOptions(), has_audio, 30.0, work,
                      on_progress=progress, cancelled=cancelled)
        self.assertFalse(os.path.exists(work), "phải dọn thư mục tạm")
        return out

    def test_duration_matches_selection_and_has_audio(self):
        ranges = [(2_000, 4_000), (10_000, 12_500), (20_300, 21_300)]   # 5.5 giây, không rơi đúng keyframe
        events = []
        out = self.run_export(self.with_audio, ranges, progress=lambda f, m: events.append(f))
        dur, kinds, _ = self.probe(out)
        self.assertAlmostEqual(dur, 5.5, delta=0.15)
        self.assertIn("video", kinds)
        self.assertIn("audio", kinds)
        self.assertEqual(events[-1], 1.0)
        self.assertEqual(sorted(events), events, "tiến độ không được lùi")

    def test_no_audio_source(self):
        out = self.run_export(self.no_audio, [(1_000, 3_000), (5_000, 6_000)], has_audio=False)
        dur, kinds, _ = self.probe(out)
        self.assertAlmostEqual(dur, 3.0, delta=0.15)
        self.assertEqual(kinds, ["video"])

    def test_resolution_option(self):
        out = os.path.join(self.dir, "small.mp4")
        export_ranges(FFMPEG, self.with_audio, [(0, 2_000)], out, ExportOptions(width=320, height=180), True, 30.0,
                      os.path.join(self.dir, "w2"))
        _, _, streams = self.probe(out)
        v = next(s for s in streams if s["codec_type"] == "video")
        self.assertEqual(v["height"], 180)

    def test_cancel_cleans_up(self):
        with self.assertRaises(ExportCancelled):
            self.run_export(self.with_audio, [(0, 5_000), (6_000, 9_000)], cancelled=lambda: True)

    def test_bad_ffmpeg_reports_error(self):
        from export.exporter import ExportError
        with self.assertRaises(ExportError):
            export_ranges(FFMPEG, os.path.join(self.dir, "khong_ton_tai.mp4"), [(0, 1000)],
                          os.path.join(self.dir, "x.mp4"), ExportOptions(), True, 30.0,
                          os.path.join(self.dir, "w3"))


if __name__ == "__main__":
    unittest.main()
