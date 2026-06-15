@echo off
REM ============================================================
REM  FireGuard AI - Setup cho may CO GPU NVIDIA (CUDA 12.1)
REM  Cai torch ban CUDA + thu vien + tai model
REM  Chay file nay THAY CHO setup.bat neu may co GPU NVIDIA.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   FireGuard AI - Setup GPU (CUDA 12.1)
echo ============================================
echo.

REM --- 1. Cai torch ban CUDA 12.1 TRUOC (de pip khong cai ban CPU) ---
echo [1/3] Cai PyTorch ban CUDA 12.1...
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (
  echo [LOI] Cai torch CUDA that bai. Kiem tra Python + mang.
  pause
  exit /b 1
)

REM --- 2. Cai cac thu vien con lai (torch da co -> bo qua) ---
echo [2/3] Cai cac thu vien con lai...
python -m pip install -r src\requirements.txt

REM --- 3. Tai model ---
if exist "models\best.pt" (
  echo [3/3] Model da co san - bo qua tai.
) else (
  echo [3/3] Tai model best.pt...
  if not exist "models" mkdir models
  curl -L -o models\best.pt "https://github.com/abcxyzawe/fireguard-ai/releases/download/v1.0/best.pt"
)

echo.
echo ============================================
echo   XONG (GPU)! Kiem tra GPU bang:
echo     python -c "import torch; print(torch.cuda.is_available())"
echo   Neu in 'True' la dung GPU. Chay server:
echo     cd src ^&^& python server.py
echo ============================================
echo.
pause
