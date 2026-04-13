# ==============================================================================
# SỬA LỖI CHÍNH TẢ OCR - VĂN BẢN TỬ VI / PHONG THỦY (v2.0)
# ==============================================================================
# Tính năng:
#   ✅ Quét file .md → chia nhỏ → sửa lỗi OCR bằng AI (Ollama)
#   ✅ Resume: nối tiếp khi bị gián đoạn
#   ✅ Parallel: xử lý song song nhiều đoạn
#   ✅ Từ điển: thuật ngữ chuyên ngành để AI sửa chính xác hơn
#   ✅ Diff Report: báo cáo HTML so sánh trước/sau
#
# Cách dùng:
#   python sua_loi_ocr.py
#   python sua_loi_ocr.py --model qwen3:4b --chunk-size 2000 --workers 2
#   python sua_loi_ocr.py --dict tu_dien.txt --no-report --reset
#
# Yêu cầu:
#   - Ollama đã chạy + đã pull model
#   - pip install ollama
# ==============================================================================

import os
import sys
import json
import time
import difflib
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Thử import thư viện ollama
try:
    import ollama
except ImportError:
    print("❌ Lỗi: Chưa cài thư viện 'ollama'.")
    print("   Hãy chạy lệnh: pip install ollama")
    sys.exit(1)


# ==============================================================================
# CẤU HÌNH MẶC ĐỊNH
# ==============================================================================

MODEL_MAC_DINH = "qwen3:4b"
KICH_THUOC_DOAN = 2000
THU_MUC_DAU_VAO = "input_md"
THU_MUC_DAU_RA = "output_md"
THU_MUC_TIEN_TRINH = "progress"      # Thư mục lưu tiến trình (resume)
THU_MUC_BAO_CAO = "reports"           # Thư mục lưu báo cáo diff
FILE_TU_DIEN = "tu_dien.txt"          # File từ điển thuật ngữ
SO_WORKER = 1                         # Số luồng song song (1 = tuần tự)


# ==============================================================================
# PROMPT GỬI CHO AI
# ==============================================================================

PROMPT_HE_THONG_GOC = """Bạn là chuyên gia sửa lỗi chính tả tiếng Việt cho văn bản OCR về Tử Vi, Phong Thủy, Kinh Dịch, Hà Lạc Lý Số, Bát Tự.

QUY TẮC BẮT BUỘC:
1. GIỮ NGUYÊN hoàn toàn định dạng Markdown (heading #, ##, ###, bảng <table>, hình ảnh <img>, <div>, link, danh sách).
2. GIỮ NGUYÊN các ký tự Hán tự (chữ Trung Quốc, ví dụ: 陳希夷先生著, 河洛理數).
3. GIỮ NGUYÊN các công thức toán học ($$ ... $$) và LaTeX.
4. GIỮ NGUYÊN các URL, đường dẫn hình ảnh.
5. CHỈ sửa lỗi chính tả tiếng Việt do OCR gây ra.
6. KHÔNG thêm bất kỳ lời giải thích, ghi chú, bình luận, hay markdown code block nào.
7. KHÔNG thay đổi cấu trúc, thứ tự nội dung, hay thêm/bớt dòng trống.
8. Trả về ĐÚNG và CHỈ văn bản đã sửa, không có gì thêm trước hay sau."""

PROMPT_NGUOI_DUNG = """Sửa lỗi chính tả OCR trong đoạn văn bản sau. Chỉ trả về văn bản đã sửa, không giải thích gì thêm:

{van_ban}"""


# ==============================================================================
# TỪ ĐIỂN THUẬT NGỮ
# ==============================================================================

def doc_tu_dien(duong_dan):
    """
    Đọc file từ điển thuật ngữ và trả về:
      - danh_sach_dung: list các thuật ngữ đúng
      - quy_tac_sua: list các cặp (sai, đúng)
    
    Tham số:
        duong_dan (str): Đường dẫn file từ điển
    
    Trả về:
        tuple: (danh_sach_dung, quy_tac_sua)
    """
    danh_sach_dung = []
    quy_tac_sua = []

    if not os.path.isfile(duong_dan):
        return danh_sach_dung, quy_tac_sua

    try:
        with open(duong_dan, "r", encoding="utf-8") as f:
            for dong in f:
                dong = dong.strip()
                # Bỏ dòng trống và comment
                if not dong or dong.startswith("#"):
                    continue
                # Quy tắc sửa lỗi: >> SAI → ĐÚNG
                if dong.startswith(">>"):
                    phan = dong[2:].strip()
                    if "→" in phan:
                        sai, dung = phan.split("→", 1)
                        quy_tac_sua.append((sai.strip(), dung.strip()))
                else:
                    # Thuật ngữ đúng (có thể phân cách bằng dấu phẩy)
                    cac_tu = [t.strip() for t in dong.split(",") if t.strip()]
                    danh_sach_dung.extend(cac_tu)
    except Exception as loi:
        print(f"  ⚠️  Không đọc được từ điển: {loi}")

    return danh_sach_dung, quy_tac_sua


def tao_prompt_voi_tu_dien(danh_sach_dung, quy_tac_sua):
    """
    Tạo prompt hệ thống có kèm danh sách từ điển thuật ngữ.
    
    Trả về:
        str: Prompt hệ thống đầy đủ
    """
    prompt = PROMPT_HE_THONG_GOC

    phan_bo_sung = []

    # Thêm quy tắc sửa lỗi phổ biến
    if quy_tac_sua:
        cac_cap = ", ".join([f"{s}→{d}" for s, d in quy_tac_sua[:30]])
        phan_bo_sung.append(
            f"\n9. Các lỗi OCR PHỔ BIẾN cần sửa: {cac_cap}"
        )

    # Thêm danh sách thuật ngữ đúng
    if danh_sach_dung:
        # Giới hạn để prompt không quá dài
        cac_tu = ", ".join(danh_sach_dung[:100])
        phan_bo_sung.append(
            f"\n10. Các thuật ngữ ĐÚNG sau đây KHÔNG ĐƯỢC thay đổi: {cac_tu}"
        )

    if phan_bo_sung:
        prompt += "\n" + "\n".join(phan_bo_sung)

    return prompt


# ==============================================================================
# HÀM ĐỌC CẤU HÌNH API
# ==============================================================================

def doc_api_config(duong_dan="api.txt"):
    """
    Đọc cấu hình Online API từ file (ví dụ: api.txt).
    Trả về dict chứa base_url, api_key, model_name hoặc None nếu lỗi.
    """
    config = {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-3.5-turbo"
    }

    if not os.path.isfile(duong_dan):
        return None

    try:
        with open(duong_dan, "r", encoding="utf-8") as f:
            for dong in f:
                dong = dong.strip()
                if not dong or dong.startswith("#") or "=" not in dong:
                    continue
                k, v = dong.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "LLM_API_KEY":
                    config["api_key"] = v
                elif k == "LLM_BASE_URL":
                    config["base_url"] = v
                elif k == "LLM_MODEL_NAME":
                    config["model_name"] = v
                    
        if config["api_key"]:
            return config
    except Exception as loi:
        print(f"  ⚠️  Không đọc được file cấu hình API: {loi}")

    return None


# ==============================================================================
# HÀM CHIA NHỎ VĂN BẢN
# ==============================================================================

def chia_nho_van_ban(noi_dung, kich_thuoc=2000):
    """
    Chia nội dung văn bản thành các đoạn nhỏ (~kich_thuoc ký tự).
    Cắt theo: đoạn văn (\\n\\n) → dòng (\\n) → câu (. )
    """
    if len(noi_dung) <= kich_thuoc:
        return [noi_dung]

    cac_doan = []
    doan_hien_tai = ""
    cac_khoi = noi_dung.split("\n\n")

    for khoi in cac_khoi:
        if len(doan_hien_tai) + len(khoi) + 2 <= kich_thuoc:
            if doan_hien_tai:
                doan_hien_tai += "\n\n" + khoi
            else:
                doan_hien_tai = khoi
        else:
            if doan_hien_tai:
                cac_doan.append(doan_hien_tai)

            if len(khoi) > kich_thuoc:
                # Chia tiếp theo dòng
                cac_dong = khoi.split("\n")
                doan_hien_tai = ""
                for dong in cac_dong:
                    if len(doan_hien_tai) + len(dong) + 1 <= kich_thuoc:
                        if doan_hien_tai:
                            doan_hien_tai += "\n" + dong
                        else:
                            doan_hien_tai = dong
                    else:
                        if doan_hien_tai:
                            cac_doan.append(doan_hien_tai)
                        if len(dong) > kich_thuoc:
                            # Chia theo câu
                            cac_cau = dong.split(". ")
                            doan_hien_tai = ""
                            for i, cau in enumerate(cac_cau):
                                phan_them = cau + (". " if i < len(cac_cau) - 1 else "")
                                if len(doan_hien_tai) + len(phan_them) <= kich_thuoc:
                                    doan_hien_tai += phan_them
                                else:
                                    if doan_hien_tai:
                                        cac_doan.append(doan_hien_tai)
                                    doan_hien_tai = phan_them
                        else:
                            doan_hien_tai = dong
            else:
                doan_hien_tai = khoi

    if doan_hien_tai:
        cac_doan.append(doan_hien_tai)

    return cac_doan


# ==============================================================================
# HÀM GỌI AI SỬA LỖI CHÍNH TẢ
# ==============================================================================

def sua_loi_chinh_ta_api(doan_van_ban, prompt_he_thong, api_config):
    """
    Gửi một đoạn văn bản cho AI qua Online API (OpenAI-compatible) thay vì Ollama.
    """
    so_lan_thu = 2
    url = api_config['base_url'].rstrip('/') + '/chat/completions'
    
    headers = {
        "Authorization": f"Bearer {api_config['api_key']}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": api_config['model_name'],
        "messages": [
            {"role": "system", "content": prompt_he_thong},
            {"role": "user", "content": PROMPT_NGUOI_DUNG.format(van_ban=doan_van_ban)}
        ],
        "temperature": 0.1,
    }
    
    req_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    for lan_thu in range(so_lan_thu):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                ket_qua = json.loads(response.read().decode("utf-8"))
            
            van_ban_da_sua = ket_qua["choices"][0]["message"]["content"].strip()

            # Loại bỏ markdown code block nếu AI tự ý bọc thêm
            if van_ban_da_sua.startswith("```") and van_ban_da_sua.endswith("```"):
                cac_dong = van_ban_da_sua.split("\n")
                van_ban_da_sua = "\n".join(cac_dong[1:-1])

            return van_ban_da_sua

        except Exception as loi:
            if lan_thu < so_lan_thu - 1:
                print(f"    ⚠️  Lỗi Online API, thử lại... ({loi})")
                time.sleep(3)
            else:
                print(f"    ❌ Thất bại Online API: {loi}. Giữ nguyên gốc.")
                return doan_van_ban


def sua_loi_chinh_ta(doan_van_ban, ten_model, prompt_he_thong, api_config=None):
    """
    Gửi một đoạn văn bản cho AI qua Ollama hoặc Online API để sửa lỗi chính tả.
    Retry 1 lần nếu lỗi. Trả về nguyên văn nếu thất bại hoàn toàn.
    """
    if api_config:
        return sua_loi_chinh_ta_api(doan_van_ban, prompt_he_thong, api_config)

    so_lan_thu = 2

    for lan_thu in range(so_lan_thu):
        try:
            ket_qua = ollama.chat(
                model=ten_model,
                messages=[
                    {"role": "system", "content": prompt_he_thong},
                    {"role": "user", "content": PROMPT_NGUOI_DUNG.format(van_ban=doan_van_ban)}
                ],
                options={
                    "temperature": 0.1,
                    "num_predict": 4096,
                }
            )

            van_ban_da_sua = ket_qua["message"]["content"].strip()

            # Loại bỏ markdown code block nếu AI tự ý bọc thêm
            if van_ban_da_sua.startswith("```") and van_ban_da_sua.endswith("```"):
                cac_dong = van_ban_da_sua.split("\n")
                van_ban_da_sua = "\n".join(cac_dong[1:-1])

            return van_ban_da_sua

        except Exception as loi:
            if lan_thu < so_lan_thu - 1:
                print(f"    ⚠️  Lỗi, thử lại... ({loi})")
                time.sleep(3)
            else:
                print(f"    ❌ Thất bại: {loi}. Giữ nguyên gốc.")
                return doan_van_ban


# ==============================================================================
# RESUME: LƯU VÀ PHỤC HỒI TIẾN TRÌNH
# ==============================================================================

def duong_dan_progress(thu_muc_tien_trinh, ten_file):
    """Trả về đường dẫn file progress JSON cho một file cụ thể."""
    return os.path.join(thu_muc_tien_trinh, ten_file + ".progress.json")


def luu_tien_trinh(duong_dan, du_lieu):
    """Lưu tiến trình xử lý vào file JSON."""
    try:
        with open(duong_dan, "w", encoding="utf-8") as f:
            json.dump(du_lieu, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Nếu không lưu được thì bỏ qua, không ảnh hưởng chức năng chính


def doc_tien_trinh(duong_dan):
    """Đọc tiến trình từ file JSON. Trả về None nếu không có."""
    if not os.path.isfile(duong_dan):
        return None
    try:
        with open(duong_dan, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def xoa_tien_trinh(duong_dan):
    """Xóa file progress khi hoàn thành."""
    try:
        if os.path.isfile(duong_dan):
            os.remove(duong_dan)
    except Exception:
        pass


# ==============================================================================
# DIFF REPORT: BÁO CÁO THAY ĐỔI HTML
# ==============================================================================

def tao_bao_cao_html(noi_dung_goc, noi_dung_sua, ten_file, thu_muc_bao_cao):
    """
    Tạo file HTML báo cáo thay đổi giữa văn bản gốc và văn bản đã sửa.
    
    Trả về:
        str: Đường dẫn file HTML đã tạo
    """
    os.makedirs(thu_muc_bao_cao, exist_ok=True)

    dong_goc = noi_dung_goc.splitlines()
    dong_sua = noi_dung_sua.splitlines()

    # Tính thống kê
    tong_dong_goc = len(dong_goc)
    tong_dong_sua = len(dong_sua)
    so_dong_thay_doi = 0
    so_tu_thay_doi = 0

    # Dùng difflib để tạo diff
    differ = difflib.unified_diff(dong_goc, dong_sua, lineterm="", n=0)
    cac_thay_doi = []

    for dong in differ:
        if dong.startswith("---") or dong.startswith("+++") or dong.startswith("@@"):
            continue
        if dong.startswith("-"):
            so_dong_thay_doi += 1
            # Đếm từ thay đổi (ước lượng)
            so_tu_thay_doi += len(dong.split())

    # Tỷ lệ thay đổi
    ty_le = round(so_dong_thay_doi / max(tong_dong_goc, 1) * 100, 1)

    # Tạo bảng diff HTML bằng HtmlDiff
    html_diff = difflib.HtmlDiff(wrapcolumn=80)
    bang_diff = html_diff.make_table(
        dong_goc, dong_sua,
        fromdesc="📄 Văn bản GỐC (có lỗi OCR)",
        todesc="✅ Văn bản ĐÃ SỬA",
        context=True,
        numlines=2
    )

    # Tạo HTML hoàn chỉnh
    thoi_gian = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Báo cáo sửa lỗi OCR - {ten_file}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 20px;
            background: #1a1a2e;
            color: #e0e0e0;
        }}
        h1 {{
            color: #00d4ff;
            border-bottom: 2px solid #00d4ff;
            padding-bottom: 10px;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .stat-card {{
            background: #16213e;
            border: 1px solid #0f3460;
            border-radius: 10px;
            padding: 15px 25px;
            min-width: 150px;
            text-align: center;
        }}
        .stat-card .number {{
            font-size: 2em;
            font-weight: bold;
            color: #00d4ff;
        }}
        .stat-card .label {{
            color: #a0a0a0;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        table.diff {{
            width: 100%;
            border-collapse: collapse;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            background: #0d1117;
            border-radius: 8px;
            overflow: hidden;
        }}
        table.diff th {{
            background: #161b22;
            color: #c9d1d9;
            padding: 10px;
            text-align: left;
        }}
        table.diff td {{
            padding: 2px 8px;
            border-bottom: 1px solid #21262d;
            vertical-align: top;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .diff_add {{
            background-color: #0d4429 !important;
            color: #aff5b4;
        }}
        .diff_sub {{
            background-color: #442019 !important;
            color: #ffa198;
        }}
        .diff_chg {{
            background-color: #341a04 !important;
            color: #ffdfb6;
        }}
        .diff_header {{
            background: #161b22 !important;
            color: #8b949e;
        }}
        td.diff_header {{
            font-weight: bold;
        }}
        .footer {{
            margin-top: 30px;
            color: #666;
            font-size: 0.85em;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>📊 Báo cáo Sửa lỗi OCR</h1>
    <p><strong>File:</strong> {ten_file} | <strong>Thời gian:</strong> {thoi_gian}</p>
    
    <div class="stats">
        <div class="stat-card">
            <div class="number">{tong_dong_goc}</div>
            <div class="label">Dòng gốc</div>
        </div>
        <div class="stat-card">
            <div class="number">{so_dong_thay_doi}</div>
            <div class="label">Dòng thay đổi</div>
        </div>
        <div class="stat-card">
            <div class="number">{ty_le}%</div>
            <div class="label">Tỷ lệ thay đổi</div>
        </div>
        <div class="stat-card">
            <div class="number">~{so_tu_thay_doi}</div>
            <div class="label">Từ thay đổi (ước lượng)</div>
        </div>
    </div>
    
    <h2>📝 Chi tiết thay đổi</h2>
    {bang_diff}
    
    <div class="footer">
        Tạo bởi Sửa Lỗi OCR v2.0 | Tử Vi / Phong Thủy / Kinh Dịch
    </div>
</body>
</html>"""

    # Lưu file
    ten_bao_cao = ten_file + ".diff.html"
    duong_dan_bc = os.path.join(thu_muc_bao_cao, ten_bao_cao)
    with open(duong_dan_bc, "w", encoding="utf-8") as f:
        f.write(html)

    return duong_dan_bc


# ==============================================================================
# HÀM GHI OUTPUT TỪNG ĐOẠN (INCREMENTAL)
# ==============================================================================

def ghi_output_tang_dan(duong_dan_dau_ra, ket_qua_cac_doan, cac_doan_goc):
    """
    Ghi file output ngay sau mỗi đoạn xử lý xong.
    Đoạn nào đã sửa → dùng kết quả đã sửa.
    Đoạn nào chưa sửa → giữ nguyên văn bản gốc.
    """
    noi_dung = "\n\n".join(
        ket_qua_cac_doan[i] if ket_qua_cac_doan[i] is not None else cac_doan_goc[i]
        for i in range(len(cac_doan_goc))
    )
    try:
        with open(duong_dan_dau_ra, "w", encoding="utf-8") as f:
            f.write(noi_dung)
    except Exception:
        pass  # Nếu không ghi được thì bỏ qua, không ảnh hưởng chính


# ==============================================================================
# HÀM XỬ LÝ MỘT FILE (CÓ RESUME + PARALLEL + DICT + DIFF)
# ==============================================================================

def xu_ly_file(duong_dan_file, thu_muc_dau_ra, ten_model, kich_thuoc_doan,
               so_thu_tu, tong_so_file, prompt_he_thong, so_workers,
               thu_muc_tien_trinh, thu_muc_bao_cao, tao_report, ghi_de=False, api_config=None):
    """
    Xử lý một file .md với đầy đủ tính năng:
    resume, parallel, từ điển (qua prompt), diff report.
    """
    ten_file = os.path.basename(duong_dan_file)
    print(f"\n{'='*60}")
    print(f"📄 [{so_thu_tu}/{tong_so_file}] Đang xử lý: {ten_file}")
    print(f"{'='*60}")

    # --- Đọc file ---
    try:
        with open(duong_dan_file, "r", encoding="utf-8") as f:
            noi_dung = f.read()
    except Exception as loi:
        print(f"  ❌ Không đọc được file: {loi}")
        return False

    if not noi_dung.strip():
        print(f"  ⏭️  File trống, bỏ qua.")
        return False

    print(f"  📏 Kích thước: {len(noi_dung):,} ký tự")

    # --- Chia nhỏ văn bản ---
    cac_doan = chia_nho_van_ban(noi_dung, kich_thuoc_doan)
    tong_so_doan = len(cac_doan)
    print(f"  ✂️  Đã chia thành {tong_so_doan} đoạn")

    # --- Chuẩn bị đường dẫn output (để ghi từng đoạn) ---
    duong_dan_dau_ra = os.path.join(thu_muc_dau_ra, ten_file)

    # --- Kiểm tra xem file đã từng xử lý xong chưa ---
    duong_dan_pg = duong_dan_progress(thu_muc_tien_trinh, ten_file)
    tien_trinh = doc_tien_trinh(duong_dan_pg)
    
    if os.path.exists(duong_dan_dau_ra) and not tien_trinh and not ghi_de:
        print(f"  ⏭️  File đã tồn tại trong output_md (đã xử lý trước đây). Bỏ qua.")
        return True

    doan_bat_dau = 0
    ket_qua_cac_doan = [None] * tong_so_doan

    if tien_trinh and tien_trinh.get("tong_doan") == tong_so_doan:
        da_xu_ly = tien_trinh.get("da_xu_ly", 0)
        ket_qua_cu = tien_trinh.get("ket_qua", [])
        
        # Phục hồi TẤT CẢ các đoạn đã xong (kể cả không theo thứ tự do chạy song song)
        for j in range(len(ket_qua_cu)):
            if j < tong_so_doan and ket_qua_cu[j] is not None:
                ket_qua_cac_doan[j] = ket_qua_cu[j]
                
        da_hoan_thanh_thuc_te = sum(1 for k in ket_qua_cac_doan if k is not None)
                
        if da_hoan_thanh_thuc_te > 0 and da_hoan_thanh_thuc_te < tong_so_doan:
            print(f"  🔄 Phát hiện tiến trình cũ: đã xong {da_hoan_thanh_thuc_te}/{tong_so_doan} đoạn.")
            print(f"  ➡️  Tiếp tục xử lý các đoạn còn lại...")
            doan_bat_dau = da_hoan_thanh_thuc_te
        elif da_hoan_thanh_thuc_te >= tong_so_doan:
            print(f"  ✅ File đã xử lý xong hoàn toàn trước đó. Bỏ qua.")
            print(f"     (Dùng --reset để xử lý lại)")
            return True

    # --- Khởi tạo progress ---
    if doan_bat_dau == 0:
        tien_trinh_moi = {
            "ten_file": ten_file,
            "tong_doan": tong_so_doan,
            "da_xu_ly": 0,
            "ket_qua": [None] * tong_so_doan,
            "bat_dau_luc": datetime.now().isoformat()
        }
    else:
        tien_trinh_moi = tien_trinh

    # --- Xử lý các đoạn ---
    thoi_gian_bat_dau = time.time()
    so_doan_con_lai = tong_so_doan - doan_bat_dau

    if so_workers <= 1:
        # === XỬ LÝ TUẦN TỰ ===
        for i in range(tong_so_doan):
            if ket_qua_cac_doan[i] is not None:
                continue
                
            doan = cac_doan[i]
            stt = i + 1

            # Hiển thị tiến trình
            da_lam = sum(1 for k in ket_qua_cac_doan if k is not None)
            if da_lam > doan_bat_dau:
                thoi_gian_da_qua = time.time() - thoi_gian_bat_dau
                toc_do = thoi_gian_da_qua / (da_lam - doan_bat_dau)
                con_lai = toc_do * (tong_so_doan - i)
                phut_con = int(con_lai // 60)
                giay_con = int(con_lai % 60)
                print(f"  🔄 Đoạn {stt}/{tong_so_doan} ({len(doan)} ký tự) "
                      f"- còn ~{phut_con}p{giay_con:02d}s", end="", flush=True)
            else:
                print(f"  🔄 Đoạn {stt}/{tong_so_doan} ({len(doan)} ký tự)", end="", flush=True)

            # Gọi AI
            doan_da_sua = sua_loi_chinh_ta(doan, ten_model, prompt_he_thong, api_config)
            ket_qua_cac_doan[i] = doan_da_sua
            print(f" ✅")

            # Lưu tiến trình ngay
            tien_trinh_moi["da_xu_ly"] = i + 1
            tien_trinh_moi["ket_qua"][i] = doan_da_sua
            luu_tien_trinh(duong_dan_pg, tien_trinh_moi)

            # Ghi output ngay lập tức (đoạn nào xong thì cập nhật)
            ghi_output_tang_dan(duong_dan_dau_ra, ket_qua_cac_doan, cac_doan)

    else:
        # === XỬ LÝ SONG SONG ===
        print(f"  ⚡ Chế độ song song: {so_workers} workers")
        dem_hoan_thanh = sum(1 for k in ket_qua_cac_doan if k is not None)
        khoi_diem = dem_hoan_thanh

        with ThreadPoolExecutor(max_workers=so_workers) as executor:
            # Gửi tất cả đoạn chưa xử lý
            tuong_lai = {}
            for i in range(tong_so_doan):
                if ket_qua_cac_doan[i] is not None:
                    continue
                future = executor.submit(
                    sua_loi_chinh_ta, cac_doan[i], ten_model, prompt_he_thong, api_config
                )
                tuong_lai[future] = i

            # Thu thập kết quả
            for future in as_completed(tuong_lai):
                idx = tuong_lai[future]
                try:
                    ket_qua = future.result()
                    ket_qua_cac_doan[idx] = ket_qua
                except Exception as loi:
                    print(f"    ❌ Đoạn {idx+1} lỗi: {loi}. Giữ nguyên.")
                    ket_qua_cac_doan[idx] = cac_doan[idx]

                dem_hoan_thanh += 1
                da_lam = dem_hoan_thanh - khoi_diem
                if da_lam > 0:
                    thoi_gian_da_qua = time.time() - thoi_gian_bat_dau
                    toc_do = thoi_gian_da_qua / da_lam
                    con_lai = toc_do * (tong_so_doan - dem_hoan_thanh)
                    phut_con = int(con_lai // 60)
                    giay_con = int(con_lai % 60)
                    print(f"  ✅ Đoạn {idx+1} xong "
                          f"[{dem_hoan_thanh}/{tong_so_doan}] "
                          f"- còn ~{phut_con}p{giay_con:02d}s")
                else:
                    print(f"  ✅ Đoạn {idx+1} xong [{dem_hoan_thanh}/{tong_so_doan}]")

                # Lưu tiến trình
                tien_trinh_moi["da_xu_ly"] = dem_hoan_thanh
                tien_trinh_moi["ket_qua"][idx] = ket_qua_cac_doan[idx]
                luu_tien_trinh(duong_dan_pg, tien_trinh_moi)

                # Ghi output ngay lập tức
                ghi_output_tang_dan(duong_dan_dau_ra, ket_qua_cac_doan, cac_doan)

    # --- Ghi file kết quả cuối cùng (đảm bảo đầy đủ) ---
    noi_dung_da_sua = "\n\n".join(
        d if d is not None else cac_doan[i]
        for i, d in enumerate(ket_qua_cac_doan)
    )
    try:
        with open(duong_dan_dau_ra, "w", encoding="utf-8") as f:
            f.write(noi_dung_da_sua)
    except Exception as loi:
        print(f"  ❌ Không lưu được file: {loi}")
        return False

    # --- Tạo báo cáo diff ---
    if tao_report:
        try:
            duong_dan_bc = tao_bao_cao_html(noi_dung, noi_dung_da_sua, ten_file, thu_muc_bao_cao)
            print(f"  📊 Báo cáo diff: {duong_dan_bc}")
        except Exception as loi:
            print(f"  ⚠️  Không tạo được báo cáo: {loi}")

    # --- Xóa file progress (đã hoàn thành) ---
    xoa_tien_trinh(duong_dan_pg)

    # --- Thống kê ---
    thoi_gian_tong = time.time() - thoi_gian_bat_dau
    phut = int(thoi_gian_tong // 60)
    giay = int(thoi_gian_tong % 60)
    print(f"\n  ✅ Hoàn thành! Đã lưu: {duong_dan_dau_ra}")
    print(f"  ⏱️  Thời gian: {phut} phút {giay} giây")
    return True


# ==============================================================================
# HÀM CHÍNH
# ==============================================================================

def main():
    """Hàm chính: phân tích tham số, kiểm tra, và xử lý tất cả file .md."""

    # --- Phân tích tham số ---
    bp = argparse.ArgumentParser(
        description="Sửa lỗi chính tả OCR trong file Markdown Tử Vi / Phong Thủy bằng AI (Ollama) v2.0"
    )
    bp.add_argument("--model", "-m", default=MODEL_MAC_DINH,
                    help=f"Model Ollama (mặc định: {MODEL_MAC_DINH})")
    bp.add_argument("--chunk-size", "-c", type=int, default=KICH_THUOC_DOAN,
                    help=f"Ký tự mỗi đoạn (mặc định: {KICH_THUOC_DOAN})")
    bp.add_argument("--input", "-i", default=THU_MUC_DAU_VAO,
                    help=f"Thư mục đầu vào (mặc định: {THU_MUC_DAU_VAO})")
    bp.add_argument("--output", "-o", default=THU_MUC_DAU_RA,
                    help=f"Thư mục đầu ra (mặc định: {THU_MUC_DAU_RA})")
    bp.add_argument("--workers", "-w", type=int, default=SO_WORKER,
                    help=f"Số luồng song song (mặc định: {SO_WORKER})")
    bp.add_argument("--dict", "-d", default=FILE_TU_DIEN,
                    help=f"File từ điển thuật ngữ (mặc định: {FILE_TU_DIEN})")
    bp.add_argument("--no-report", action="store_true",
                    help="Không tạo báo cáo diff HTML")
    bp.add_argument("--reset", action="store_true",
                    help="Xóa toàn bộ tiến trình cũ, chạy lại từ đầu")
    bp.add_argument("--use-api", action="store_true",
                    help="Sử dụng Online API thay vì Ollama (sử dụng cấu hình từ api.txt)")
    ts = bp.parse_args()

    # --- Đường dẫn ---
    thu_muc_goc = os.path.dirname(os.path.abspath(__file__))
    thu_muc_dau_vao = os.path.join(thu_muc_goc, ts.input)
    thu_muc_dau_ra = os.path.join(thu_muc_goc, ts.output)
    thu_muc_tien_trinh = os.path.join(thu_muc_goc, THU_MUC_TIEN_TRINH)
    thu_muc_bao_cao = os.path.join(thu_muc_goc, THU_MUC_BAO_CAO)
    duong_dan_tu_dien = os.path.join(thu_muc_goc, ts.dict)
    duong_dan_api = os.path.join(thu_muc_goc, "api.txt")

    # --- Đọc cấu hình API ---
    api_config = None
    if ts.use_api:
        api_config = doc_api_config(duong_dan_api)
        if not api_config:
            print(f"❌ Lỗi: Bạn đã chọn --use-api nhưng không tìm thấy file cấu hình {duong_dan_api} hoặc thiếu LLM_API_KEY.")
            sys.exit(1)

    # --- Hiển thị cấu hình ---
    print("=" * 60)
    print("🔧 SỬA LỖI OCR v2.0 — TỬ VI / PHONG THỦY")
    print("=" * 60)
    if api_config:
        print(f"  Chế độ     : ONLINE API (Mô hình: {api_config['model_name']})")
    else:
        print(f"  Chế độ     : LOCAL OLLAMA (Model: {ts.model})")
    print(f"  Chunk size : {ts.chunk_size} ký tự")
    print(f"  Workers    : {ts.workers}")
    print(f"  Từ điển    : {ts.dict}")
    print(f"  Diff report: {'TẮT' if ts.no_report else 'BẬT'}")
    print(f"  Thư mục vào: {ts.input}")
    print(f"  Thư mục ra : {ts.output}")
    print()

    # --- Kiểm tra thư mục đầu vào ---
    if not os.path.isdir(thu_muc_dau_vao):
        print(f"❌ Không tìm thấy thư mục: {thu_muc_dau_vao}")
        sys.exit(1)

    # --- Tạo thư mục ---
    os.makedirs(thu_muc_dau_ra, exist_ok=True)
    os.makedirs(thu_muc_tien_trinh, exist_ok=True)
    if not ts.no_report:
        os.makedirs(thu_muc_bao_cao, exist_ok=True)

    # --- Reset tiến trình nếu cần ---
    if ts.reset:
        print("🗑️  Xóa toàn bộ tiến trình cũ...")
        for f in os.listdir(thu_muc_tien_trinh):
            if f.endswith(".progress.json"):
                os.remove(os.path.join(thu_muc_tien_trinh, f))
        print("  ✅ Đã xóa.")

    # --- Đọc từ điển ---
    danh_sach_dung, quy_tac_sua = doc_tu_dien(duong_dan_tu_dien)
    if danh_sach_dung or quy_tac_sua:
        print(f"📖 Từ điển: {len(danh_sach_dung)} thuật ngữ đúng, {len(quy_tac_sua)} quy tắc sửa")
    else:
        print(f"📖 Từ điển: không tìm thấy hoặc trống (tiếp tục không dùng từ điển)")

    # Tạo prompt có kèm từ điển
    prompt_he_thong = tao_prompt_voi_tu_dien(danh_sach_dung, quy_tac_sua)

    # --- Quét file .md ---
    danh_sach_file = sorted([
        os.path.join(thu_muc_dau_vao, f)
        for f in os.listdir(thu_muc_dau_vao)
        if f.lower().endswith(".md")
    ])

    if not danh_sach_file:
        print(f"⚠️  Không tìm thấy file .md nào trong: {thu_muc_dau_vao}")
        sys.exit(0)

    print(f"\n📂 Tìm thấy {len(danh_sach_file)} file .md:")
    for f in danh_sach_file:
        print(f"   - {os.path.basename(f)}")

    # --- Kiểm tra kết nối AI ---
    if api_config:
        print(f"\n🔌 Chế độ Online API được chọn. Xin lưu ý cước phí hoặc rate limit từ nhà cung cấp.")
    else:
        print(f"\n🔌 Kiểm tra Ollama (model: {ts.model})...")
        try:
            ollama.chat(
                model=ts.model,
                messages=[{"role": "user", "content": "Xin chào"}],
                options={"num_predict": 5}
            )
            print("  ✅ Kết nối thành công!")
        except Exception as loi:
            print(f"  ❌ Lỗi: {loi}")
            print(f"  → Kiểm tra: ollama serve | ollama pull {ts.model}")
            sys.exit(1)

    # --- Xử lý từng file ---
    tong_thoi_gian = time.time()
    so_thanh_cong = 0

    for i, duong_dan in enumerate(danh_sach_file, 1):
        thanh_cong = xu_ly_file(
            duong_dan_file=duong_dan,
            thu_muc_dau_ra=thu_muc_dau_ra,
            ten_model=ts.model,
            kich_thuoc_doan=ts.chunk_size,
            so_thu_tu=i,
            tong_so_file=len(danh_sach_file),
            prompt_he_thong=prompt_he_thong,
            so_workers=ts.workers,
            thu_muc_tien_trinh=thu_muc_tien_trinh,
            thu_muc_bao_cao=thu_muc_bao_cao,
            tao_report=not ts.no_report,
            ghi_de=ts.reset,
            api_config=api_config
        )
        if thanh_cong:
            so_thanh_cong += 1

    # --- Tổng kết ---
    tong = time.time() - tong_thoi_gian
    phut = int(tong // 60)
    giay = int(tong % 60)
    print(f"\n{'='*60}")
    print(f"🏁 HOÀN TẤT!")
    print(f"   Đã xử lý : {so_thanh_cong}/{len(danh_sach_file)} file")
    print(f"   Thời gian : {phut} phút {giay} giây")
    print(f"   Kết quả   : {thu_muc_dau_ra}/")
    if not ts.no_report:
        print(f"   Báo cáo   : {THU_MUC_BAO_CAO}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
