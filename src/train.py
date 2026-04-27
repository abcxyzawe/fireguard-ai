#!/usr/bin/env python3
"""
Training script - He thong Kiem soat Lua

Su dung YOLO11 (hoac YOLOv8) de train/fine-tune model phat hien lua va khoi.

Su dung:
  python train.py                          # Fine-tune tu model hien tai
  python train.py --model yolo11s.pt       # Train tu YOLO11s pretrained
  python train.py --model yolo11n.pt       # Train tu YOLO11n pretrained
  python train.py --from-scratch           # Train tu dau voi YOLO11n
"""

import os
import argparse

os.environ["WANDB_DISABLED"] = "true"

if __name__ == '__main__':
    import torch
    from ultralytics import YOLO

    parser = argparse.ArgumentParser(description='Train Fire/Smoke Detection Model')
    parser.add_argument('--model', '-m', default=None,
                        help='Base model (yolo11n.pt, yolo11s.pt, or path to fine-tune)')
    parser.add_argument('--data', '-d', default='../dataset/data.yaml',
                        help='Dataset config file')
    parser.add_argument('--epochs', '-e', type=int, default=50,
                        help='Number of epochs (default: 50)')
    parser.add_argument('--batch', '-b', type=int, default=8,
                        help='Batch size (default: 8)')
    parser.add_argument('--imgsz', type=int, default=640,
                        help='Image size (default: 640, MUST match inference)')
    parser.add_argument('--name', '-n', default='fire_smoke',
                        help='Run name')
    parser.add_argument('--from-scratch', action='store_true',
                        help='Train from scratch (no pretrained weights)')
    args = parser.parse_args()

    # GPU check
    if torch.cuda.is_available():
        device = 0
        print(f"[TRAIN] GPU: {torch.cuda.get_device_name(device)}")
    else:
        device = 'cpu'
        print("[TRAIN] No GPU, using CPU (slow!)")

    # Model selection
    if args.model:
        model_path = args.model
    elif os.path.exists("../models/best.pt"):
        model_path = "../models/best.pt"
        print("[TRAIN] Fine-tuning from models/best.pt")
    else:
        model_path = "../models/yolo11n.pt"
        print("[TRAIN] Training from YOLO11n pretrained")

    print(f"[TRAIN] Model: {model_path}")
    print(f"[TRAIN] Data:  {args.data}")
    print(f"[TRAIN] Epochs: {args.epochs}, Batch: {args.batch}, ImgSz: {args.imgsz}")

    model = YOLO(model_path)

    # Fine-tune: lower LR; from scratch: higher LR
    is_finetune = "best.pt" in model_path or "last.pt" in model_path
    lr0 = 0.001 if is_finetune else 0.01

    model.train(
        # Dataset
        data=args.data,

        # Training
        epochs=args.epochs,
        imgsz=args.imgsz,       # QUAN TRONG: phai khop voi inference
        batch=args.batch,

        # Learning rate
        lr0=lr0,
        lrf=0.01,

        # Optimizer
        optimizer='AdamW',
        weight_decay=0.0005,

        # Device
        device=device,
        workers=2,              # Windows safe

        # Early stopping
        patience=15,

        # Data augmentation (toi uu cho fire/smoke)
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=5.0,            # Xoay nhe (lua co the nghieng)
        translate=0.1,
        scale=0.3,              # Scale da dang (lua gan/xa)
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.3,
        mosaic=0.7,             # Mosaic tot cho fire detection
        mixup=0.1,              # Mixup nhe giup generalize
        copy_paste=0.0,
        auto_augment=None,

        # Loss weights (toi uu cho 2-class fire/smoke)
        box=7.5,
        cls=1.5,                # Tang cls loss (chi 2 class, can phan biet ro)
        dfl=1.5,

        # Warmup
        warmup_epochs=3.0,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,

        # Validation
        val=True,
        split='val',

        # Save
        save=True,
        save_period=-1,

        # Other
        verbose=True,
        plots=True,
        amp=True,
        cache=False,
        close_mosaic=10,        # Tat mosaic 10 epoch cuoi (on dinh)
        resume=False,
        project="../runs/detect",
        name=args.name,
        deterministic=True,
        seed=42,
    )

    print(f"\n[TRAIN] Done! Best weights: ../runs/detect/{args.name}/weights/best.pt")
    print(f"[TRAIN] Copy best.pt sang models/:")
    print(f"  copy ..\\runs\\detect\\{args.name}\\weights\\best.pt ..\\models\\best.pt")
