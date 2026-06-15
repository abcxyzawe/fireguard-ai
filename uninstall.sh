#!/usr/bin/env bash
# ============================================================
#  FireGuard AI - Go cai dat (Mac / Linux / Raspberry Pi)
#  Xoa cac thu vien Python da cai + model da tai
# ============================================================
cd "$(dirname "$0")"

echo ""
echo "============================================"
echo "  FireGuard AI - GO CAI DAT"
echo "============================================"
echo ""
echo "CANH BAO: Se go thu vien: flask, ultralytics, sahi,"
echo "  torch, torchvision, opencv-python, numpy, pillow,"
echo "  pyserial, requests"
echo ""
echo "Luu y: torch/numpy/opencv co the dang dung cho du an KHAC."
echo ""
read -p "Ban co chac muon go? (y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Da huy."
  exit 0
fi

# --- Go thu vien Python ---
echo ""
echo "[1/2] Dang go thu vien Python..."
pip uninstall -y -r src/requirements.txt

# --- Xoa model ---
echo ""
read -p "[2/2] Xoa luon model models/best.pt? (y/n): " delmodel
if [ "$delmodel" = "y" ] || [ "$delmodel" = "Y" ]; then
  if [ -f "models/best.pt" ]; then
    rm -f models/best.pt
    echo "Da xoa models/best.pt"
  else
    echo "Khong tim thay models/best.pt"
  fi
else
  echo "Giu lai model."
fi

echo ""
echo "============================================"
echo "  XONG! Da go cai dat."
echo "============================================"
echo ""
