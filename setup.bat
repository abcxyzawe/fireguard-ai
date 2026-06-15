@echo off
REM ============================================================
REM  FireGuard AI - Setup tu dong (Windows)
REM  Cai thu vien Python + tai model ve folder models\
REM  Chay:  double-click file nay HOAC go  setup.bat  trong cmd
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   FireGuard AI - Dang cai dat...
echo ============================================
echo.

REM --- 1. Cai thu vien Python ---
echo [1/2] Cai thu vien Python (pip install)...
python -m pip install -r src\requirements.txt
if errorlevel 1 (
  echo.
  echo [LOI] pip install that bai. Kiem tra da cai Python chua?
  pause
  exit /b 1
)

REM --- 2. Tai model neu chua co ---
if exist "models\best.pt" (
  echo [2/2] Model da co san ^(models\best.pt^) - bo qua tai.
) else (
  echo [2/2] Tai model best.pt tu GitHub Release...
  if not exist "models" mkdir models
  curl -L -o models\best.pt "https://github.com/abcxyzawe/fireguard-ai/releases/download/v1.0/best.pt"
  if errorlevel 1 (
    echo.
    echo [LOI] Tai model that bai. Tai thu cong tai:
    echo   https://github.com/abcxyzawe/fireguard-ai/releases/tag/v1.0
    echo   roi bo file best.pt vao folder models\
    pause
    exit /b 1
  )
)

echo.
echo ============================================
echo   XONG! Chay server bang lenh:
echo     cd src
echo     python server.py
echo ============================================
echo.
pause
