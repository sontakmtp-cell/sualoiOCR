# 📖 Hướng Dẫn Sử Dụng - Sửa Lỗi Chính Tả OCR v2.0

## 1. Cài đặt

```bash
# Cài Ollama: https://ollama.com/download
ollama pull qwen3:4b

# Cài thư viện Python
pip install ollama
pip install gradio    # (tùy chọn, chỉ cần nếu dùng giao diện Web)
```

## 2. Chuẩn bị

Đặt file `.md` cần sửa vào thư mục `input_md/`.

## 3. Chạy (CLI)

```bash
# Mặc định
python sua_loi_ocr.py

# Đầy đủ tùy chọn
python sua_loi_ocr.py --model qwen3:4b --chunk-size 2000 --workers 2 --dict tu_dien.txt

# Không tạo báo cáo
python sua_loi_ocr.py --no-report

# Xóa tiến trình cũ, chạy lại từ đầu
python sua_loi_ocr.py --reset

# Xem tất cả tùy chọn
python sua_loi_ocr.py --help
```

## 4. Chạy (Web UI)

```bash
python web_app.py
# Mở trình duyệt tại http://localhost:7860
```

## 5. Tính năng mới v2.0

| Tính năng | Mô tả |
|-----------|-------|
| **Resume** | Tự động lưu tiến trình. Nếu bị gián đoạn, chạy lại sẽ tiếp tục từ chỗ dừng |
| **Parallel** | `--workers 2` gửi đồng thời 2 đoạn cho AI, nhanh gấp đôi |
| **Từ điển** | File `tu_dien.txt` chứa thuật ngữ đúng để AI không sửa nhầm |
| **Diff Report** | Tạo báo cáo HTML trong `reports/` so sánh trước/sau |
| **Web UI** | Giao diện đồ họa, xem trực quan, so sánh file, chỉnh từ điển |

## 6. Cấu trúc thư mục

```
├── sua_loi_ocr.py     # Script CLI chính
├── web_app.py         # Giao diện Web
├── tu_dien.txt        # Từ điển thuật ngữ
├── input_md/          # File .md cần sửa
├── output_md/         # File .md đã sửa
├── progress/          # Tiến trình (tự tạo, tự xóa khi xong)
└── reports/           # Báo cáo diff HTML
```
