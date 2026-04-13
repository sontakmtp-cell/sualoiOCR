# ==============================================================================
# GIAO DIỆN WEB - SỬA LỖI OCR TỬ VI / PHONG THỦY
# ==============================================================================
# Chạy: python web_app.py
# Mở trình duyệt: http://localhost:7860
#
# Yêu cầu: pip install gradio ollama
# ==============================================================================

import os
import sys
import glob
import threading
import time
import difflib

# Import các hàm từ script chính
from sua_loi_ocr import (
    chia_nho_van_ban, sua_loi_chinh_ta,
    doc_tu_dien, tao_prompt_voi_tu_dien, doc_api_config,
    luu_tien_trinh, doc_tien_trinh, xoa_tien_trinh,
    duong_dan_progress, tao_bao_cao_html,
    ghi_output_tang_dan,
    MODEL_MAC_DINH, KICH_THUOC_DOAN,
    THU_MUC_DAU_VAO, THU_MUC_DAU_RA,
    THU_MUC_TIEN_TRINH, THU_MUC_BAO_CAO, FILE_TU_DIEN
)

try:
    import gradio as gr
except ImportError:
    print("❌ Chưa cài thư viện 'gradio'.")
    print("   Chạy: pip install gradio")
    sys.exit(1)

try:
    import ollama
except ImportError:
    print("❌ Chưa cài thư viện 'ollama'.")
    print("   Chạy: pip install ollama")
    sys.exit(1)


# Đường dẫn gốc
THU_MUC_GOC = os.path.dirname(os.path.abspath(__file__))

# Biến toàn cục để điều khiển dừng
dang_chay = False
yeu_cau_dung = False


def lay_danh_sach_file_input():
    """Lấy danh sách file .md trong thư mục input."""
    thu_muc = os.path.join(THU_MUC_GOC, THU_MUC_DAU_VAO)
    if not os.path.isdir(thu_muc):
        return []
    return sorted([
        f for f in os.listdir(thu_muc)
        if f.lower().endswith(".md")
    ])


def lay_danh_sach_file_output():
    """Lấy danh sách file .md trong thư mục output."""
    thu_muc = os.path.join(THU_MUC_GOC, THU_MUC_DAU_RA)
    if not os.path.isdir(thu_muc):
        return []
    return sorted([
        f for f in os.listdir(thu_muc)
        if f.lower().endswith(".md")
    ])


def xu_ly_web(ten_file, model, chunk_size, workers, su_dung_tu_dien, su_dung_api, progress=gr.Progress()):
    """
    Hàm xử lý chính cho Web UI.
    Trả về log text từng bước.
    """
    global dang_chay, yeu_cau_dung
    
    if dang_chay:
        yield "⚠️ Đang có tiến trình chạy. Hãy đợi hoặc nhấn Dừng."
        return

    dang_chay = True
    yeu_cau_dung = False
    log = []

    try:
        # --- Chuẩn bị ---
        thu_muc_vao = os.path.join(THU_MUC_GOC, THU_MUC_DAU_VAO)
        thu_muc_ra = os.path.join(THU_MUC_GOC, THU_MUC_DAU_RA)
        thu_muc_pg = os.path.join(THU_MUC_GOC, THU_MUC_TIEN_TRINH)
        thu_muc_bc = os.path.join(THU_MUC_GOC, THU_MUC_BAO_CAO)
        os.makedirs(thu_muc_ra, exist_ok=True)
        os.makedirs(thu_muc_pg, exist_ok=True)
        os.makedirs(thu_muc_bc, exist_ok=True)

        duong_dan_file = os.path.join(thu_muc_vao, ten_file)
        if not os.path.isfile(duong_dan_file):
            yield f"❌ Không tìm thấy file: {ten_file}"
            return

        # --- Đọc file ---
        log.append(f"📄 File: {ten_file}")
        with open(duong_dan_file, "r", encoding="utf-8") as f:
            noi_dung = f.read()

        if not noi_dung.strip():
            yield "⏭️ File trống."
            return

        log.append(f"📏 Kích thước: {len(noi_dung):,} ký tự")
        yield "\n".join(log)

        # --- Cấu hình AI ---
        api_config = None
        if su_dung_api:
            duong_dan_api = os.path.join(THU_MUC_GOC, "api.txt")
            api_config = doc_api_config(duong_dan_api)
            if not api_config:
                yield "❌ Lỗi: Không thể dùng Online API. Hãy kiểm tra `api.txt` hoặc thiết lập trong tab Cấu Hình API."
                return
            log.append(f"🌐 Chế độ: Online API ({api_config['model_name']})")
        else:
            log.append(f"🔌 Chế độ: Local Ollama ({model})")

        yield "\n".join(log)

        # --- Từ điển ---
        if su_dung_tu_dien:
            td_path = os.path.join(THU_MUC_GOC, FILE_TU_DIEN)
            ds_dung, qt_sua = doc_tu_dien(td_path)
            prompt = tao_prompt_voi_tu_dien(ds_dung, qt_sua)
            log.append(f"📖 Từ điển: {len(ds_dung)} thuật ngữ, {len(qt_sua)} quy tắc")
        else:
            from sua_loi_ocr import PROMPT_HE_THONG_GOC
            prompt = PROMPT_HE_THONG_GOC
            log.append("📖 Từ điển: TẮT")
        yield "\n".join(log)

        # --- Chia nhỏ ---
        cac_doan = chia_nho_van_ban(noi_dung, chunk_size)
        tong = len(cac_doan)
        log.append(f"✂️ Chia thành {tong} đoạn")
        yield "\n".join(log)

        # Đường dẫn output (để ghi từng đoạn)
        out_path = os.path.join(thu_muc_ra, ten_file)

        # --- Kiểm tra resume ---
        pg_path = duong_dan_progress(thu_muc_pg, ten_file)
        tien_trinh = doc_tien_trinh(pg_path)
        bat_dau = 0
        ket_qua = [None] * tong

        if tien_trinh and tien_trinh.get("tong_doan") == tong:
            kq_cu = tien_trinh.get("ket_qua", [])
            for j in range(len(kq_cu)):
                if j < tong and kq_cu[j] is not None:
                    ket_qua[j] = kq_cu[j]
                    
            da_lam = sum(1 for k in ket_qua if k is not None)
            if 0 < da_lam < tong:
                bat_dau = da_lam  # chỉ để ước tính tiến độ thôi
                log.append(f"🔄 Resume: tiếp tục từ trạng thái {da_lam}/{tong} đoạn")
                yield "\n".join(log)

        # --- Xử lý ---
        pg_data = {
            "ten_file": ten_file, "tong_doan": tong,
            "da_xu_ly": bat_dau, "ket_qua": ket_qua
        }

        thoi_gian_bat_dau = time.time()

        for i in range(tong):
            if ket_qua[i] is not None:
                continue
                
            if yeu_cau_dung:
                # Ghi output trước khi dừng (đoạn đã xong + đoạn gốc chưa xử lý)
                ghi_output_tang_dan(out_path, ket_qua, cac_doan)
                log.append(f"\n⏸️ Đã dừng. Tiến trình đã lưu.")
                log.append(f"📁 Kết quả tạm: {out_path}")
                yield "\n".join(log)
                return

            # update UI progress (approximate)
            da_lam_so = sum(1 for k in ket_qua if k is not None)
            progress(da_lam_so / tong, desc=f"Đoạn {i+1}/{tong}")

            if da_lam_so > bat_dau:
                tg = time.time() - thoi_gian_bat_dau
                con = (tg / (da_lam_so - bat_dau)) * (tong - da_lam_so)
                p, g = int(con // 60), int(con % 60)
                log.append(f"  🔄 Đoạn {i+1}/{tong} - còn ~{p}p{g:02d}s")
            else:
                log.append(f"  🔄 Đoạn {i+1}/{tong}...")

            yield "\n".join(log)

            ket_qua[i] = sua_loi_chinh_ta(cac_doan[i], model, prompt, api_config)
            log[-1] += " ✅"

            pg_data["da_xu_ly"] = i + 1
            pg_data["ket_qua"][i] = ket_qua[i]
            luu_tien_trinh(pg_path, pg_data)

            # Ghi output ngay sau mỗi đoạn
            ghi_output_tang_dan(out_path, ket_qua, cac_doan)

            yield "\n".join(log)

        # --- Ghi file kết quả cuối cùng (đảm bảo đầy đủ) ---
        noi_dung_sua = "\n\n".join(
            d if d is not None else cac_doan[j]
            for j, d in enumerate(ket_qua)
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(noi_dung_sua)

        # Tạo báo cáo
        try:
            bc = tao_bao_cao_html(noi_dung, noi_dung_sua, ten_file, thu_muc_bc)
            log.append(f"\n📊 Báo cáo: {bc}")
        except Exception:
            pass

        xoa_tien_trinh(pg_path)

        tg_tong = time.time() - thoi_gian_bat_dau
        log.append(f"\n🏁 HOÀN TẤT! ({int(tg_tong//60)}p{int(tg_tong%60):02d}s)")
        log.append(f"📁 Đã lưu: {out_path}")
        yield "\n".join(log)

    except Exception as loi:
        log.append(f"\n❌ Lỗi: {loi}")
        yield "\n".join(log)
    finally:
        dang_chay = False


def dung_xu_ly():
    """Gửi tín hiệu dừng."""
    global yeu_cau_dung
    yeu_cau_dung = True
    return "⏸️ Đã gửi yêu cầu dừng... đợi đoạn hiện tại hoàn thành."


def so_sanh_file(ten_file):
    """Đọc file gốc và file đã sửa, trả về nội dung 2 cột."""
    if not ten_file:
        return "Chọn file để so sánh", "", ""

    goc_path = os.path.join(THU_MUC_GOC, THU_MUC_DAU_VAO, ten_file)
    sua_path = os.path.join(THU_MUC_GOC, THU_MUC_DAU_RA, ten_file)

    noi_dung_goc = ""
    noi_dung_sua = ""

    if os.path.isfile(goc_path):
        with open(goc_path, "r", encoding="utf-8") as f:
            noi_dung_goc = f.read()

    if os.path.isfile(sua_path):
        with open(sua_path, "r", encoding="utf-8") as f:
            noi_dung_sua = f.read()
    else:
        return noi_dung_goc, "(Chưa có file đã sửa)", ""

    # Tạo thống kê
    d_goc = noi_dung_goc.splitlines()
    d_sua = noi_dung_sua.splitlines()
    khac = sum(1 for a, b in zip(d_goc, d_sua) if a != b)
    tong = max(len(d_goc), len(d_sua))
    ty_le = round(khac / max(tong, 1) * 100, 1)
    thong_ke = f"📊 {khac}/{tong} dòng thay đổi ({ty_le}%)"

    return noi_dung_goc, noi_dung_sua, thong_ke


def doc_tu_dien_web():
    """Đọc nội dung file từ điển để hiển thị."""
    td_path = os.path.join(THU_MUC_GOC, FILE_TU_DIEN)
    if os.path.isfile(td_path):
        with open(td_path, "r", encoding="utf-8") as f:
            return f.read()
    return "(Không tìm thấy file tu_dien.txt)"


def luu_tu_dien_web(noi_dung):
    """Lưu nội dung từ điển."""
    td_path = os.path.join(THU_MUC_GOC, FILE_TU_DIEN)
    with open(td_path, "w", encoding="utf-8") as f:
        f.write(noi_dung)
    return "✅ Đã lưu từ điển!"


def doc_file_api_web():
    """Đọc nội dung api.txt để hiển thị."""
    api_path = os.path.join(THU_MUC_GOC, "api.txt")
    if os.path.isfile(api_path):
        with open(api_path, "r", encoding="utf-8") as f:
            return f.read()
    return "LLM_API_KEY=\nLLM_BASE_URL=https://api.openai.com/v1\nLLM_MODEL_NAME=gpt-3.5-turbo\n"


def luu_file_api_web(noi_dung):
    """Lưu cấu hình api.txt."""
    api_path = os.path.join(THU_MUC_GOC, "api.txt")
    with open(api_path, "w", encoding="utf-8") as f:
        f.write(noi_dung)
    return "✅ Đã lưu cấu hình API!"


# ==============================================================================
# GIAO DIỆN GRADIO
# ==============================================================================

def tao_giao_dien():
    """Tạo giao diện Gradio với 3 tab."""

    with gr.Blocks(
        title="Sửa Lỗi OCR - Tử Vi / Phong Thủy",
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="cyan",
        ),
        css="""
        .header { text-align: center; margin-bottom: 20px; }
        .header h1 { color: #1a73e8; }
        """
    ) as app:

        gr.Markdown("""
        # 🔮 Sửa Lỗi Chính Tả OCR — Tử Vi / Phong Thủy
        *Sử dụng AI (Ollama) để tự động sửa lỗi chính tả OCR trong văn bản Markdown*
        """, elem_classes="header")

        # ===== TAB 1: XỬ LÝ =====
        with gr.Tab("🔄 Xử lý"):
            with gr.Row():
                with gr.Column(scale=2):
                    dd_file = gr.Dropdown(
                        choices=lay_danh_sach_file_input(),
                        label="📂 Chọn file từ input_md/",
                        interactive=True,
                    )
                    with gr.Row():
                        txt_model = gr.Textbox(
                            value=MODEL_MAC_DINH,
                            label="🤖 Model",
                            scale=2,
                        )
                        num_chunk = gr.Number(
                            value=KICH_THUOC_DOAN,
                            label="✂️ Chunk size",
                            scale=1,
                        )
                        num_workers = gr.Number(
                            value=1,
                            label="⚡ Workers",
                            scale=1,
                            minimum=1, maximum=4,
                        )
                    with gr.Row():
                        chk_dict = gr.Checkbox(
                            value=True,
                            label="📖 Dùng từ điển thuật ngữ",
                        )
                        chk_api = gr.Checkbox(
                            value=False,
                            label="🌐 Dùng Online API (api.txt)",
                        )
                    with gr.Row():
                        btn_chay = gr.Button("▶️ Bắt đầu", variant="primary", scale=2)
                        btn_dung = gr.Button("⏸️ Dừng", variant="stop", scale=1)
                        btn_lam_moi = gr.Button("🔄 Làm mới DS", scale=1)

                with gr.Column(scale=3):
                    txt_log = gr.Textbox(
                        label="📋 Log xử lý",
                        lines=25,
                        max_lines=50,
                        interactive=False,
                    )

            # Sự kiện
            btn_chay.click(
                fn=xu_ly_web,
                inputs=[dd_file, txt_model, num_chunk, num_workers, chk_dict, chk_api],
                outputs=txt_log,
            )
            btn_dung.click(fn=dung_xu_ly, outputs=txt_log)
            btn_lam_moi.click(
                fn=lambda: gr.update(choices=lay_danh_sach_file_input()),
                outputs=dd_file,
            )

        # ===== TAB 2: SO SÁNH =====
        with gr.Tab("📊 So sánh"):
            dd_file_ss = gr.Dropdown(
                choices=lay_danh_sach_file_output(),
                label="📂 Chọn file đã xử lý",
                interactive=True,
            )
            btn_lam_moi_ss = gr.Button("🔄 Làm mới DS")
            txt_thong_ke = gr.Textbox(label="Thống kê", interactive=False)
            with gr.Row():
                txt_goc = gr.Textbox(label="📄 Văn bản GỐC", lines=20, interactive=False)
                txt_sua = gr.Textbox(label="✅ Văn bản ĐÃ SỬA", lines=20, interactive=False)

            dd_file_ss.change(
                fn=so_sanh_file,
                inputs=dd_file_ss,
                outputs=[txt_goc, txt_sua, txt_thong_ke],
            )
            btn_lam_moi_ss.click(
                fn=lambda: gr.update(choices=lay_danh_sach_file_output()),
                outputs=dd_file_ss,
            )

        # ===== TAB 3: TỪ ĐIỂN =====
        with gr.Tab("📖 Từ điển"):
            gr.Markdown("Chỉnh sửa danh sách thuật ngữ chuyên ngành. Mỗi dòng 1 thuật ngữ (hoặc nhiều thuật ngữ cách nhau bằng dấu phẩy).")
            txt_tu_dien = gr.Textbox(
                value=doc_tu_dien_web(),
                label="Nội dung tu_dien.txt",
                lines=25,
                interactive=True,
            )
            with gr.Row():
                btn_luu_td = gr.Button("💾 Lưu từ điển", variant="primary")
                txt_trang_thai = gr.Textbox(label="Trạng thái", interactive=False)

            btn_luu_td.click(
                fn=luu_tu_dien_web,
                inputs=txt_tu_dien,
                outputs=txt_trang_thai,
            )

        # ===== TAB 4: API CẤU HÌNH =====
        with gr.Tab("🌐 Cấu hình API"):
            gr.Markdown("Chỉnh sửa nội dung file cấu hình `api.txt` trực tiếp. Cần thiết khi sử dụng chế độ Online API.")
            txt_api = gr.Textbox(
                value=doc_file_api_web(),
                label="Nội dung api.txt",
                lines=10,
                interactive=True,
            )
            with gr.Row():
                btn_luu_api = gr.Button("💾 Lưu cấu hình", variant="primary")
                txt_trang_thai_api = gr.Textbox(label="Trạng thái", interactive=False)

            btn_luu_api.click(
                fn=luu_file_api_web,
                inputs=txt_api,
                outputs=txt_trang_thai_api,
            )

    return app


# ==============================================================================
# CHẠY
# ==============================================================================

if __name__ == "__main__":
    app = tao_giao_dien()
    print("🌐 Mở trình duyệt tại: http://localhost:7860")
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
