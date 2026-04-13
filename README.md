# Công Cụ Sửa Lỗi Chính Tả OCR v2.0 - Tử Vi / Phong Thủy

Công cụ sử dụng AI (Local Ollama hoặc API Online) để tự động quét và sửa các lỗi chính tả do nhận dạng ký tự quang học (OCR) gây ra trong các file Markdown, đặc biệt tối ưu cho các văn bản về Tử Vi, Phong Thủy, Kinh Dịch, Bát Tự.

## 🌟 Tính Năng Nổi Bật (Phiên bản 2.0)

- **AI Chuyên Dụng**: Sử dụng mô hình Ollama cục bộ (mặc định: `qwen3:4b`) hoặc API trực tuyến (OpenAI-compatible) đảm bảo tính riêng tư hoặc tốc độ cao. Giữ nguyên định dạng Markdown (headings, tables, links, images, math/LaTeX, v.v.).
- **Tiếp Tục Xử Lý (Resume)**: Lưu tiến trình trong thư mục `progress/`. Nếu quá trình bị gián đoạn, ứng dụng sẽ tiếp tục xử lý từ đoạn bị dừng ở lần chạy tiếp theo.
- **Xử Lý Song Song (Parallel)**: Hỗ trợ xử lý nhiều đoạn văn bản cùng lúc (`--workers`) giúp tăng tốc độ đáng kể.
- **Từ Điển Thuật Ngữ**: Sử dụng `tu_dien.txt` chứa danh sách các thuật ngữ đúng để ngăn AI sửa sai các từ chuyên ngành tôn giáo, tâm linh, phong thủy.
- **Báo Cáo Thay Đổi (Diff Report)**: Tự động xuất file báo cáo định dạng HTML trong `reports/` để so sánh trực quan và thống kê tỷ lệ sửa đổi giữa bản gốc và bản đã sửa.
- **Giao Diện Trực Quan (Web UI)**: Cung cấp giao diện web thân thiện thông qua Gradio để chọn file, theo dõi tiến độ, cấu hình mô hình từ điển và so sánh file ngay trên trình duyệt.

## 📂 Cấu Trúc Thư Mục

```text
├── sua_loi_ocr.py     # Script CLI chính xử lý logic
├── web_app.py         # Script chạy giao diện Web UI (Gradio)
├── khoi_dong.bat      # File chạy nhanh trên Windows
├── tu_dien.txt        # Từ điển thuật ngữ không thay đổi
├── api.txt            # Cấu hình chứa API Key (nếu dùng cloud)
├── input_md/          # Thư mục chứa các file .md cần sửa
├── output_md/         # Thư mục lưu kết quả file .md sau khi sửa
├── progress/          # Nơi lưu tiến trình xử lý (tự khởi tạo và xóa đi khi xong file)
└── reports/           # Chứa các báo cáo .html kết quả so sánh file diff
```

## 🚀 Cài Đặt

1. **Cài Đặt Ollama**: Tải và cài đặt tại [ollama.com/download](https://ollama.com/download)
   - Tải model mặc định: `ollama pull qwen3:4b`
2. **Cài Đặt Thư Viện Python**:
   - Sử dụng menu cài đặt trong `khoi_dong.bat`.
   - Hoặc cài thủ công: `pip install ollama gradio`

## 🖥 Chuẩn Bị File

Hãy chép tất cả các tệp văn bản đuôi `.md` cần chỉnh sửa vào thư mục `input_md/`.

## 📌 Cách Sử Dụng

Bạn có thể chạy ứng dụng qua giao diện Web thân thiện hoặc dòng lệnh CLI linh hoạt:

### 1. Khởi Động Nhanh (Windows)
Chạy file `khoi_dong.bat` và chọn chế độ bạn muốn sử dụng từ Menu:
- `[1]` Mở Web UI
- `[2]` Chạy qua CLI
- `[3]` Cài đặt các thư viện cần thiết

### 2. Giao Diện Web UI
Vào Terminal, gõ lệnh:
```bash
python web_app.py
```
Sau đó truy cập: [http://localhost:7860](http://localhost:7860) trong trình duyệt của bạn.

### 3. Dòng Lệnh (CLI)
Sử dụng dòng lệnh cho mục đích tự động hoá hoặc để tuỳ chỉnh sâu:
```bash
# Chạy mặc định với mọi cấu hình tiêu chuẩn
python sua_loi_ocr.py

# Tuỳ chỉnh mô hình, số từ cắt nhỏ, số luồng và dùng file từ điển khác
python sua_loi_ocr.py --model qwen3:4b --chunk-size 2000 --workers 2 --dict tu_dien.txt

# Để ứng dụng không xuất báo cáo diff HTML
python sua_loi_ocr.py --no-report

# Bỏ qua lưu tiến trình cũ (resume), xử lý từ đầu
python sua_loi_ocr.py --reset

# Trợ giúp các tham số command line
python sua_loi_ocr.py --help
```

## 🌐 Tùy Chọn Sử Dụng LLM API (Online)

Nếu không muốn dùng Local Ollama, bạn có thể thiết lập LLM API tương thích OpenAI:
1. Mở file `api.txt` trực tiếp hoặc chỉnh sửa qua tab **Cấu hình API** trong Web UI.
2. Thêm cấu hình:
    ```ini
    LLM_API_KEY=sk-...your-key...
    LLM_BASE_URL=https://api.openai.com/v1
    LLM_MODEL_NAME=gpt-4o-mini
    ```
3. Khởi động Web UI, đánh dấu vào `Dùng Online API (api.txt)`, hoặc truyền thêm flag qua CLI (nếu script hỗ trợ).
