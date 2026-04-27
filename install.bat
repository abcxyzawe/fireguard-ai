@echo off
chcp 65001 >nul
title Cai dat He thong Kiem soat Lua & Khoi
echo.
echo ============================================
echo   CAI DAT HE THONG KIEM SOAT LUA VA KHOI
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat!
    echo Tai Python tai: https://www.python.org/downloads/
    echo Luu y: Tick "Add Python to PATH" khi cai dat
    pause
    exit /b 1
)

echo [OK] Python da cai dat
python --version
echo.

:: Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] pip khong tim thay!
    pause
    exit /b 1
)

echo [OK] pip da san sang
echo.

:: Install dependencies
echo Dang cai dat thu vien...
echo.
pip install -r src\requirements.txt
echo.

if errorlevel 1 (
    echo [LOI] Cai dat that bai!
    pause
    exit /b 1
)

:: Check CUDA
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"Khong co\"}') "
echo.

:: Create output dirs
if not exist "output" mkdir output
if not exist "output\received_images" mkdir output\received_images

echo ============================================
echo   CAI DAT HOAN TAT!
echo ============================================
echo.
echo   Chay "run.bat" de khoi dong server
echo   Truy cap: http://localhost:5000
echo.
pause
