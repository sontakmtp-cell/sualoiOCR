@echo off
echo ==================================================
echo       CONG CU SUA LOI CHINH TA OCR v2.0
echo ==================================================
echo.

IF EXIST ".venv\Scripts\activate.bat" (
    echo [INFO] Dang kich hoat moi truong ao Python...
    call .venv\Scripts\activate.bat
) ELSE (
    echo [CANH BAO] Khong tim thay moi truong ao .venv.
    echo Neu he thong khong tim thay thu vien, vui long chon menu Cai dat so 3.
    echo.
)

:menu
echo Vui long chon che do hoat dong:
echo [1] Mo giao dien Web UI - Khuyen dung
echo [2] Chay bang dong lenh CLI - Mac dinh
echo [3] Cai dat cac thu vien can thiet - Lan dau
echo [4] Thoat
echo.

set /p choice="Nhap lua chon cua ban 1-4: "

if "%choice%"=="1" goto web
if "%choice%"=="2" goto cli
if "%choice%"=="3" goto install
if "%choice%"=="4" goto exit

echo Lua chon khong hop le. Vui long nhap lai.
goto menu

:web
cls
echo ==================================================
echo Dang khoi dong Giao dien Web...
echo Vui long cho giay lat. Trinh duyet se mo khi san sang.
echo ==================================================
python web_app.py
pause
goto exit

:cli
cls
echo ==================================================
echo Dang khoi dong tien trinh sua loi bang dong lenh...
echo ==================================================
python sua_loi_ocr.py
pause
goto exit

:install
cls
echo ==================================================
echo Dang cai dat cac thu vien can thiet...
echo ==================================================
pip install ollama gradio
echo.
echo Cai dat hoan tat!
pause
cls
goto menu

:exit
exit
