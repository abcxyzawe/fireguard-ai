#!/usr/bin/env python3
"""
Folder monitor - He thong Kiem soat Lua

Theo doi thu muc anh, phat hien lua va ghi log CSV.

Su dung:
  python location.py                           # Monitor received_images2/
  python location.py --dir my_images/          # Monitor thu muc khac
  python location.py --dir images/ --watch     # Watch mode (lien tuc)
"""

import os
import glob
import csv
import argparse
import time
from datetime import datetime
from collections import deque

import cv2
from ultralytics import YOLO

from fire_utils import (
    load_config, get_mode_config, measure_brightness,
    process_detections, DEFAULT_CONFIG
)


def parse_args():
    p = argparse.ArgumentParser(description='Fire Detection - Folder Monitor')
    p.add_argument('--dir', '-d', default='../output/received_images',
                   help='Image directory to monitor')
    p.add_argument('--csv', default=None,
                   help='CSV output path (default: from config)')
    p.add_argument('--config', default='config.json',
                   help='Config file path')
    p.add_argument('--watch', '-w', action='store_true',
                   help='Continuously watch for new images')
    p.add_argument('--extensions', nargs='+', default=['jpg', 'jpeg', 'png'],
                   help='Image extensions to process')
    return p.parse_args()


def ensure_csv(csv_path):
    """Tao CSV header neu chua co."""
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'filename', 'class', 'class_id',
                'conf', 'x1', 'y1', 'x2', 'y2', 'mode'
            ])
        print(f"[CSV] Created: {csv_path}")


def write_detections(csv_path, filename, detections, mode_name):
    """Ghi fire detections vao CSV."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    try:
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                writer.writerow([
                    timestamp, filename, det['class'], det['class_id'],
                    f"{det['conf']:.3f}", x1, y1, x2, y2, mode_name
                ])
    except Exception as e:
        print(f"[CSV] Write error: {e}")


def detect_image(model, model_names, img_path, mode_config, bbox_config,
                 yolo_conf, imgsz, device, enable_smoke, smoke_config):
    """Phat hien lua/khoi trong 1 anh."""
    img = cv2.imread(img_path)
    if img is None:
        return None

    env_brightness = measure_brightness(img)

    try:
        results = model.predict(
            source=img, conf=yolo_conf, imgsz=imgsz,
            device=device, verbose=False
        )
    except Exception as e:
        print(f"  [ERROR] Inference: {e}")
        return None

    if not results:
        return {'fire_bboxes': [], 'smoke_bboxes': [], 'has_fire': False, 'has_smoke': False}

    r = results[0]
    boxes = getattr(r, 'boxes', None)

    return process_detections(
        boxes, img, model_names, mode_config, bbox_config,
        env_brightness, enable_smoke, smoke_config
    )


def main():
    args = parse_args()

    # Config
    config = load_config(args.config)
    mode_config, mode_name = get_mode_config(config)
    bbox_config = config.get("bbox", DEFAULT_CONFIG["bbox"])
    enable_smoke = config.get("enable_smoke", False)
    smoke_config = None
    if enable_smoke:
        smoke_modes = config.get("smoke_modes", DEFAULT_CONFIG["smoke_modes"])
        smoke_config = smoke_modes.get(mode_name, smoke_modes.get("sensitive"))

    # Paths
    image_dir = args.dir
    csv_path = args.csv or config["paths"].get("csv_path", "detections.csv")

    # Model
    weights = config["model"]["weights"]
    imgsz = config["model"].get("imgsz", 640)
    device = config["model"].get("device")
    yolo_conf = mode_config.get("yolo_conf", 0.25)

    print(f"[LOCATION] Loading model: {weights}")
    model = YOLO(weights)
    model_names = getattr(model, 'names', {}) or {}
    print(f"[LOCATION] Classes: {model_names}")

    # Init
    os.makedirs(image_dir, exist_ok=True)
    ensure_csv(csv_path)

    # Gioi han processed_files (tranh memory leak)
    processed_files = deque(maxlen=10000)

    print(f"[LOCATION] Monitoring: {image_dir}")
    print(f"[LOCATION] CSV output: {csv_path}")
    print(f"[LOCATION] Mode: {mode_name}")
    print(f"[LOCATION] Extensions: {args.extensions}")
    if args.watch:
        print("[LOCATION] Watch mode: ON (Ctrl+C to stop)\n")
    else:
        print("[LOCATION] Single scan mode\n")

    # Stats
    total_processed = 0
    total_fire = 0
    total_smoke = 0

    while True:
        try:
            # Scan cho tat ca extensions
            images = []
            for ext in args.extensions:
                images.extend(glob.glob(os.path.join(image_dir, f"*.{ext}")))
            images = sorted(images)

            new_count = 0
            for img_path in images:
                filename = os.path.basename(img_path)
                if filename in processed_files:
                    continue

                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                print(f"[{timestamp}] Processing: {filename}")

                result = detect_image(
                    model, model_names, img_path, mode_config, bbox_config,
                    yolo_conf, imgsz, device, enable_smoke, smoke_config
                )

                if result is None:
                    print(f"  [ERROR] Could not process image")
                    processed_files.append(filename)
                    continue

                fire_bboxes = result.get('fire_bboxes', [])
                smoke_bboxes = result.get('smoke_bboxes', [])

                if fire_bboxes:
                    print(f"  FIRE DETECTED - {len(fire_bboxes)} detection(s)")
                    write_detections(csv_path, filename, fire_bboxes, mode_name)
                    total_fire += len(fire_bboxes)

                if smoke_bboxes:
                    print(f"  SMOKE DETECTED - {len(smoke_bboxes)} detection(s)")
                    write_detections(csv_path, filename, smoke_bboxes, mode_name)
                    total_smoke += len(smoke_bboxes)

                if not fire_bboxes and not smoke_bboxes:
                    print(f"  No fire/smoke detected")

                processed_files.append(filename)
                total_processed += 1
                new_count += 1

            if not args.watch:
                break

            if new_count == 0:
                time.sleep(0.5)

        except KeyboardInterrupt:
            print(f"\n[LOCATION] Stopped")
            break
        except Exception as e:
            print(f"[LOCATION] Error: {e}")
            if not args.watch:
                break
            time.sleep(1)

    print(f"\n[LOCATION] Summary: {total_processed} images, "
          f"{total_fire} fire, {total_smoke} smoke detections")


if __name__ == '__main__':
    main()
