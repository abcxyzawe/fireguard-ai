@echo off
REM ============================================================
REM  FireGuard AI - Go cai dat (Windows)
REM  Xoa cac thu vien Python da cai + model da tai
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   FireGuard AI - GO CAI DAT
echo ============================================
echo.
echo CANH BAO: Se go cac thu vien Python sau:
echo   flask, ultralytics, sahi, torch, torchvision,
echo   opencv-python, numpy, pillow, pyserial, requests
echo.
echo Luu y: torch/numpy/opencv co the dang dung cho
echo du an KHAC tren may. Chi go neu chac chan.
echo.
set /p confirm="Ban co chac muon go? (y/n): "
if /i not "%confirm%"=="y" (
  echo Da huy.
  pause
  exit /b 0
)

REM --- Go thu vien Python ---
echo.
echo [1/2] Dang go thu vien Python...
python -m pip uninstall -y -r src\requirements.txt

REM --- Xoa model ---
echo.
set /p delmodel="[2/2] Xoa luon model models\best.pt? (y/n): "
if /i "%delmodel%"=="y" (
  if exist "models\best.pt" (
    del /q "models\best.pt"
    echo Da xoa models\best.pt
  ) else (
    echo Khong tim thay models\best.pt
  )
) else (
  echo Giu lai model.
)

echo.
echo ============================================
echo   XONG! Da go cai dat.
echo   (Code va file repo van con - xoa thu cong
echo    folder neu muon xoa han du an)
echo ============================================
echo.
pause
