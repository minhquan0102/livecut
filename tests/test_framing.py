"""Kiểm thử tỉ lệ khung và các kiểu lấp khung (crop / blur / black), có chạy FFmpeg thật."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from export.exporter import ExportOptions, build_segment_cmd, export_ranges
from export.framing import (ASPECTS, FrameSpec, crop_rect, crop_rect_f, extract_frame, output_size,
                            size_choices)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class GeometryTests(unittest.TestCase):
    def test_output_sizes(self):
        self.assertEqual(output_size((9, 16), 1080), (1080, 1920))
        self.assertEqual(output_size((16, 9), 1080), (1920, 1080))
        self.assertEqual(output_size((1, 1), 720), (720, 720))
        self.assertEqual(output_size((4, 5), 1080), (1080, 1350))
        self.assertEqual(output_size((3, 4), 1080), (1080, 1440))

    def test_every_listed_size_is_even(self):
        for _label, aspect in ASPECTS:
            if aspect:
                for _l, w, h in size_choices(aspect):
                    self.assertEqual((w % 2, h % 2), (0, 0))

    def test_crop_landscape_to_portrait_is_centered_full_height(self):
        x, y, w, h = crop_rect(1920, 1080, (9, 16), 0.5, 0.5, 1.0)
        self.assertEqual((y, h), (0, 1080))
        self.assertAlmostEqual(w / h, 9 / 16, delta=0.01)
        self.assertAlmostEqual(x + w / 2, 960, delta=2)

    def test_crop_portrait_to_landscape_is_full_width(self):
        x, y, w, h = crop_rect(720, 1280, (16, 9), 0.5, 0.5, 1.0)
        self.assertEqual((x, w), (0, 720))
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)

    def test_zoom_shrinks_region(self):
        _, _, w1, h1 = crop_rect_f(1920, 1080, (9, 16), 0.5, 0.5, 1.0)
        _, _, w2, h2 = crop_rect_f(1920, 1080, (9, 16), 0.5, 0.5, 2.0)
        self.assertAlmostEqual(w2, w1 / 2)
        self.assertAlmostEqual(h2, h1 / 2)

    def test_region_always_inside_video(self):
        for cx in (-1, 0, 0.5, 1, 2):
            for cy in (-1, 0, 0.5, 1, 2):
                for zoom in (1, 1.7, 4, 99):
                    x, y, w, h = crop_rect(1920, 1080, (9, 16), cx, cy, zoom)
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, 1920)
                    self.assertLessEqual(y + h, 1080)
                    self.assertEqual((x % 2, y % 2, w % 2, h % 2), (0, 0, 0, 0))

    def test_pan_moves_region(self):
        left = crop_rect(1920, 1080, (9, 16), 0.0, 0.5, 1.0)[0]
        right = crop_rect(1920, 1080, (9, 16), 1.0, 0.5, 1.0)[0]
        self.assertEqual(left, 0)
        self.assertGreater(right, 1000)

    def test_command_uses_filter_complex_only_for_blur(self):
        base = dict(width=1080, height=1920, src_w=1920, src_h=1080)
        for mode, complex_graph in (("crop", False), ("black", False), ("blur", True)):
            o = ExportOptions(frame=FrameSpec((9, 16), mode), **base)
            cmd = build_segment_cmd("ffmpeg", "a.mp4", 0, 1000, "o.mp4", o, True, 30)
            self.assertEqual("-filter_complex" in cmd, complex_graph, mode)
            self.assertEqual("-vf" in cmd, not complex_graph, mode)
            self.assertIn("[v]" if complex_graph else "0:v:0", cmd)


@unittest.skipUnless(FFMPEG and FFPROBE, "cần ffmpeg và ffprobe")
class RealFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.land = os.path.join(cls.dir, "land.mp4")
        cls.port = os.path.join(cls.dir, "port.mp4")
        for path, size in ((cls.land, "1280x720"), (cls.port, "720x1280")):
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"testsrc2=size={size}:rate=30:duration=6", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=6", "-c:v", "libx264", "-c:a", "aac", "-shortest",
                            path], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def export(self, src, sw, sh, aspect, mode, short=720, cx=0.5, cy=0.5, zoom=1.0):
        w, h = output_size(aspect, short)
        o = ExportOptions(width=w, height=h, src_w=sw, src_h=sh, frame=FrameSpec(aspect, mode, cx, cy, zoom))
        self._n = getattr(self, "_n", 0) + 1
        out = os.path.join(self.dir, f"o_{mode}_{self._n}.mp4")
        export_ranges(FFMPEG, src, [(500, 2500)], out, o, True, 30.0, os.path.join(self.dir, "w"))
        return out, (w, h)

    def probe(self, path):
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-show_entries", "format=duration", "-of", "csv=p=0:s=,", path],
                           capture_output=True, text=True, check=True).stdout.split()
        wh, dur = r[0].split(","), float(r[1])
        return int(wh[0]), int(wh[1]), dur

    def pixel(self, path, x, y):
        raw = subprocess.run([FFMPEG, "-loglevel", "error", "-ss", "0.5", "-i", path, "-frames:v", "1",
                              "-vf", f"crop=1:1:{x}:{y},format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        return raw[0]

    def test_every_aspect_and_mode_produces_exact_size(self):
        for src, sw, sh in ((self.land, 1280, 720), (self.port, 720, 1280)):
            for _label, aspect in ASPECTS:
                if aspect is None:
                    continue
                for mode in ("crop", "blur", "black"):
                    out, (w, h) = self.export(src, sw, sh, aspect, mode)
                    ow, oh, dur = self.probe(out)
                    self.assertEqual((ow, oh), (w, h), f"{os.path.basename(src)} {aspect} {mode}")
                    self.assertAlmostEqual(dur, 2.0, delta=0.2)

    def test_black_mode_has_black_bars_and_blur_mode_fills_them(self):
        # video ngang 1280x720 đưa vào khung dọc 9:16: phần trên cùng phải là viền (đen / mờ)
        black, _ = self.export(self.land, 1280, 720, (9, 16), "black")
        self.assertLessEqual(self.pixel(black, 5, 5), 20)
        blur, _ = self.export(self.land, 1280, 720, (9, 16), "blur")
        self.assertGreater(self.pixel(blur, 5, 5), 25, "nền mờ phải lấy màu từ video, không đen")

    def test_crop_pan_changes_picture(self):
        left, _ = self.export(self.land, 1280, 720, (9, 16), "crop", cx=0.0)
        right, _ = self.export(self.land, 1280, 720, (9, 16), "crop", cx=1.0)
        samples = [(x, y) for x in (30, 200, 400) for y in (100, 500, 900)]
        l = [self.pixel(left, x, y) for x, y in samples]
        r = [self.pixel(right, x, y) for x, y in samples]
        self.assertNotEqual(l, r)

    def test_extract_frame(self):
        out = os.path.join(self.dir, "still.jpg")
        self.assertTrue(extract_frame(FFMPEG, self.land, 1500, out, max_width=640))
        self.assertGreater(os.path.getsize(out), 1000)
        self.assertFalse(extract_frame(FFMPEG, os.path.join(self.dir, "none.mp4"), 0,
                                       os.path.join(self.dir, "x.jpg")))


if __name__ == "__main__":
    unittest.main()
