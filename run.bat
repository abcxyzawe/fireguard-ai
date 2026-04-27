@echo off
title Fire Detection Server

if not exist "models\best.pt" (
    echo [ERROR] Model not found: models\best.pt
    pause
    exit /b 1
)

echo [OK] Model: models\best.pt
echo [OK] Starting server...
echo.
echo   Dashboard:  http://localhost:5000
echo   Press Ctrl+C to stop
echo.

cd src
python server.py
pause
