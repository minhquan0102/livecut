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
- Giai đoạn 5 (cần chạy thử trên Windows): chọn dòng phụ đề (Ctrl/Shift) -> "Thêm vào video" (Enter) -> các đoạn hiện ở panel "Đoạn video" và trên timeline, có đệm trước/sau chỉnh được; nút "Xem thử" phát lần lượt các đoạn như một video. Logic nằm ở `editor/ranges.py` (có test).
- Giai đoạn 8 (cần chạy thử trên Windows): nút "Xuất video" (Ctrl+E) xuất các đoạn đã chọn thành một file MP4. Chỉ mã hóa phần được chọn (tua thẳng tới đoạn, cắt chính xác từng khung hình, fade âm thanh 20 ms ở mối nối), rồi nối bằng concat. Logic ở `export/exporter.py`, đã kiểm thử với FFmpeg thật (`tests/test_export.py`).
- Chưa làm: kéo thả đổi thứ tự đoạn, chuyển cảnh (GĐ9), lưu/mở dự án đầy đủ, tối ưu seek sâu hơn (GĐ4), chọn đoạn (GĐ5-6), quản lý đoạn trong nhóm (GĐ7), xuất (GĐ8), chuyển cảnh (GĐ9). Các nút thuộc giai đoạn này đang tắt và có chú thích giai đoạn sẽ bật.
- Chưa có: sửa/gộp/chia phụ đề và xuất SRT đã sửa (GĐ2 còn lại).
