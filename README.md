# LiveCut Studio

Phần mềm Windows cắt và ghép video livestream bán hàng, viết bằng Python + PySide6 + FFmpeg. Chạy offline.

## Chạy thử
1. Cài Python 3.10+ và `pip install -r requirements.txt` (hoặc chạy `run.bat`).
2. Tải FFmpeg bản Windows, đặt `ffmpeg.exe` và `ffprobe.exe` vào thư mục `bin/` (hoặc thêm vào PATH).
3. `python main.py`
4. Kiểm thử logic: `python -m unittest tests.test_core`

## Cấu trúc
| Thư mục | Vai trò |
|---|---|
| `ui/` | Theme, icon, cửa sổ chính, sidebar, panel xem trước, phụ đề, timeline, đoạn video |
| `timeline/` | `scale.py` (logic zoom/cuộn, không phụ thuộc Qt) và `view.py` (widget vẽ timeline) |
| `subtitle/` | Đọc, kiểm tra, ghi SRT |
| `project/` | Mô hình dự án (đoạn, nhóm, chuyển cảnh) và lưu/đọc JSON `.livecut` |
| `services/` | ffprobe, tìm FFmpeg, chạy tác vụ nền bằng QThread |
| `utils/` | Timecode, tìm kiếm không dấu, đường dẫn và file tạm |
| `player/`, `editor/`, `export/` | Dành cho giai đoạn 3-9 |

## Tiến độ theo lộ trình
- Giai đoạn 1 (kiến trúc + giao diện): có. Bố cục 5 khu vực kéo đổi kích thước, ẩn/hiện bằng Ctrl+B / Ctrl+R / Ctrl+T, nhớ bố cục giữa các lần mở.
- Phần của giai đoạn 2 đã làm sẵn: nhập video (đọc bằng ffprobe), nhập SRT (tự nhận mã hóa UTF-8/UTF-16/cp1258), cảnh báo SRT lệch thời lượng, tìm kiếm phụ đề không dấu, lưu/mở dự án, tạo/đổi tên/xóa nhóm.
- Giai đoạn 3 (mã nguồn đã viết, cần chạy thử trên máy Windows): trình phát duy nhất `player/video_player.py` có hình + tiếng, Space phát/dừng, tua ±5 giây, tốc độ 0.5x–2x, âm lượng, tắt tiếng; nhấp phụ đề hoặc kéo timeline để seek, thanh trạng thái hiện thời gian seek.
- Chưa làm: tối ưu seek sâu hơn (GĐ4), chọn đoạn (GĐ5-6), quản lý đoạn trong nhóm (GĐ7), xuất (GĐ8), chuyển cảnh (GĐ9). Các nút thuộc giai đoạn này đang tắt và có chú thích giai đoạn sẽ bật.
- Chưa có: sửa/gộp/chia phụ đề và xuất SRT đã sửa (GĐ2 còn lại).
