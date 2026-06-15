#!/usr/bin/env bash
# ============================================================
#  FireGuard AI - Setup tu dong (Mac / Linux / Raspberry Pi)
#  Cai thu vien Python + tai model ve folder models/
#  Chay:  bash setup.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo ""
echo "============================================"
echo "  FireGuard AI - Dang cai dat..."
echo "============================================"
echo ""

# --- 1. Cai thu vien Python ---
echo "[1/2] Cai thu vien Python (pip install)..."
pip install -r src/requirements.txt

# --- 2. Tai model neu chua co ---
if [ -f "models/best.pt" ]; then
  echo "[2/2] Model da co san (models/best.pt) - bo qua tai."
else
  echo "[2/2] Tai model best.pt tu GitHub Release..."
  mkdir -p models
  curl -L -o models/best.pt \
    "https://github.com/abcxyzawe/fireguard-ai/releases/download/v1.0/best.pt"
fi

echo ""
echo "============================================"
echo "  XONG! Chay server bang lenh:"
echo "    cd src && python server.py"
echo "============================================"
echo ""
