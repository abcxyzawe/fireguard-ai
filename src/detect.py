#!/usr/bin/env python3
"""
Realtime / batch detection - He thong Kiem soat Lua

Su dung:
  python detect.py --source test.jpg --show
  python detect.py --source video.mp4 --save
  python detect.py --source 0 --show          # webcam

Requires: ultralytics, opencv-python
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from fire_utils import (
    load_config, get_mode_config, measure_brightness,
    process_detections, draw_detections,
    FlickerDetector, FrameVoter, DEFAULT_CONFIG
)


def parse_args():
    p = argparse.ArgumentParser(description='YOLO Fire/Smoke Detection')
    p.add_argument('--weights', '-w', default=None,
                   help='Path to weights (default: from config.json)')
    p.add_argument('--source', '-s', default='0',
                   help='Image, video, or webcam index (default: 0)')
    p.add_argument('--imgsz', type=int, default=640,
                   help='Inference image size')
    p.add_argument('--conf', type=float, default=None,
                   help='Confidence threshold (default: from config mode)')
    p.add_argument('--device', '-d', default=None,
                   help='Device: 0 (GPU) or cpu')
    p.add_argument('--save', action='store_true',
                   help='Save annotated results')
    p.add_argument('--save-dir', default='../output/predict',
                   help='Directory for saved results')
    p.add_argument('--show', action='store_true',
                   help='Show detection window')
    p.add_argument('--config', default='config.json',
                   help='Config file path')
    return p.parse_args()


def main():
    args = parse_args()

    # Load config
    config = load_config(args.config)
    mode_config, mode_name = get_mode_config(config)
    bbox_config = config.get("bbox", DEFAULT_CONFIG["bbox"])
    enable_smoke = config.get("enable_smoke", False)
    smoke_config = None
    if enable_smoke:
        smoke_modes = config.get("smoke_modes", DEFAULT_CONFIG["smoke_modes"])
        smoke_config = smoke_modes.get(mode_name, smoke_modes.get("sensitive"))

    # Weights
    weights = args.weights or config["model"]["weights"]
    print(f"[DETECT] Loading model: {weights}")

    model = YOLO(weights)
    model_names = getattr(model, 'names', {}) or {}
    print(f"[DETECT] Classes: {model_names}")
    print(f"[DETECT] Mode: {mode_name}")

    # Source
    source = args.source
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    # Save dir
    save_dir = Path(args.save_dir)
    if args.save:
        save_dir.mkdir(parents=True, exist_ok=True)

    # YOLO conf
    yolo_conf = args.conf or mode_config.get("yolo_conf", 0.25)
    imgsz = args.imgsz
    device = args.device or config["model"].get("device")

    # Detection state
    fc = config.get("flicker", DEFAULT_CONFIG["flicker"])
    flicker = FlickerDetector(
        history_size=fc.get("history_size", 5),
        min_std=fc.get("min_std", 8.0),
        normalize_factor=fc.get("normalize_factor", 20.0)
    )
    fire_voter = FrameVoter()
    smoke_voter = FrameVoter()
    confirm_frames = mode_config.get("confirm_frames", 1)

    # Stream inference
    try:
        stream = model.predict(
            source=source, conf=yolo_conf, imgsz=imgsz,
            device=device, stream=True
        )
    except TypeError:
        results = model.predict(
            source=source, conf=yolo_conf, imgsz=imgsz, device=device
        )
        stream = iter(results)

    fps_time = time.time()
    fps_count = 0

    for i, r in enumerate(stream):
        # Get original image
        if hasattr(r, 'orig_img'):
            img = r.orig_img.copy()
        elif hasattr(r, 'plot'):
            img = r.plot()
        else:
            continue

        # Brightness + flicker
        env_brightness = measure_brightness(img)
        flicker.update(env_brightness)

        # Process detections
        boxes = getattr(r, 'boxes', None)
        det_result = process_detections(
            boxes, img, model_names, mode_config, bbox_config,
            env_brightness, enable_smoke, smoke_config
        )

        # Frame voting
        fire_voter.update(det_result['has_fire'])
        smoke_voter.update(det_result['has_smoke'])
        fire_confirmed = fire_voter.is_confirmed(confirm_frames)
        smoke_confirmed = smoke_voter.is_confirmed(
            smoke_config.get("confirm_frames", 2) if smoke_config else 2
        )

        # FPS
        fps_count += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps = fps_count / elapsed
            fps_count = 0
            fps_time = time.time()
        else:
            fps = fps_count / max(elapsed, 0.001)

        info = f"Mode: {mode_name} | FPS: {fps:.1f} | Brightness: {env_brightness:.0f}"

        # Draw
        annotated = draw_detections(
            img, det_result['fire_bboxes'], det_result['smoke_bboxes'],
            fire_confirmed, smoke_confirmed, info
        )

        # Show
        if args.show:
            cv2.imshow('Fire Detection', annotated)

            path = getattr(r, 'path', '') or ''
            suffix = Path(path).suffix.lower() if path else ''
            video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

            if isinstance(source, int) or suffix in video_exts:
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                if cv2.waitKey(0) & 0xFF == ord('q'):
                    break

        # Save
        if args.save:
            if isinstance(source, int):
                out_path = save_dir / f'frame_{i:06d}.jpg'
            else:
                base = Path(getattr(r, 'path', '') or f'result_{i}').stem
                out_path = save_dir / f'{base}_{i}.jpg'
            cv2.imwrite(str(out_path), annotated)

    if args.show:
        cv2.destroyAllWindows()

    print(f'[DETECT] Done. Results {"saved to " + str(save_dir) if args.save else "not saved"}')


if __name__ == '__main__':
    main()
