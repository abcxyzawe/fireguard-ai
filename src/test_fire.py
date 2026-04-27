#!/usr/bin/env python3
"""
Test script - He thong Kiem soat Lua

Test phat hien lua/khoi voi anh hoac video, hien thi chi tiet
diem phan tich cua tung tieu chi.

Su dung:
  python test_fire.py image.jpg                    # Test 1 anh
  python test_fire.py fire_video.mp4               # Test video
  python test_fire.py folder/                      # Test tat ca anh trong folder
  python test_fire.py image.jpg --verbose          # Hien chi tiet diem
  python test_fire.py video.mp4 --save             # Luu ket qua
  python test_fire.py --source 0                   # Webcam

Yeu cau: ultralytics, opencv-python, fire_utils.py
"""

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from fire_utils import (
    load_config, get_mode_config, measure_brightness,
    process_detections, draw_detections, verify_fire_roi, verify_smoke_roi,
    FlickerDetector, FrameVoter, MotionAnalyzer, DEFAULT_CONFIG
)


def parse_args():
    p = argparse.ArgumentParser(
        description='Test Fire/Smoke Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_fire.py photo.jpg
  python test_fire.py fire_video.mp4 --verbose
  python test_fire.py test_images/ --save
  python test_fire.py --source 0
        """
    )
    p.add_argument('input', nargs='?', default=None,
                   help='Image, video file, or folder path')
    p.add_argument('--source', '-s', default=None,
                   help='Webcam index (e.g., 0)')
    p.add_argument('--weights', '-w', default=None,
                   help='Model weights path')
    p.add_argument('--config', default='config.json',
                   help='Config file path')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Show detailed verification scores')
    p.add_argument('--save', action='store_true',
                   help='Save annotated results')
    p.add_argument('--save-dir', default='../output/test_results',
                   help='Output directory for saved results')
    p.add_argument('--no-show', action='store_true',
                   help='Do not display results (for batch processing)')
    p.add_argument('--mode', '-m', default=None,
                   help='Detection mode: safe, sensitive, ultra_sensitive')
    return p.parse_args()


def print_detection_details(result, env_brightness, verbose=False):
    """In chi tiet ket qua detection."""
    fire_bboxes = result.get('fire_bboxes', [])
    smoke_bboxes = result.get('smoke_bboxes', [])

    if not fire_bboxes and not smoke_bboxes:
        print("  -> No fire/smoke detected")
        return

    for fb in fire_bboxes:
        x1, y1, x2, y2 = fb['bbox']
        print(f"  [FIRE] conf={fb['conf']:.3f} verify={fb.get('verify_score', 0):.3f} "
              f"bbox=({x1},{y1},{x2},{y2})")
        if verbose and 'verify_details' in fb:
            d = fb['verify_details']
            print(f"         color={d.get('color', 0):.3f} "
                  f"core={d.get('core', 0):.3f} "
                  f"gradient={d.get('gradient', 0):.3f} "
                  f"texture={d.get('texture', 0):.3f} "
                  f"edge={d.get('edge', 0):.3f}")
            print(f"         final={d.get('final', 0):.3f} "
                  f"threshold={d.get('threshold', 0):.3f} "
                  f"brightness={env_brightness:.0f}")
            cd = d.get('color_detail', {})
            if cd:
                print(f"         HSV: red={cd.get('red', 0):.3f} "
                      f"orange={cd.get('orange', 0):.3f} "
                      f"yellow={cd.get('yellow', 0):.3f} "
                      f"core={cd.get('core', 0):.4f}")

    for sb in smoke_bboxes:
        x1, y1, x2, y2 = sb['bbox']
        print(f"  [SMOKE] conf={sb['conf']:.3f} verify={sb.get('verify_score', 0):.3f} "
              f"bbox=({x1},{y1},{x2},{y2})")
        if verbose and 'verify_details' in sb:
            d = sb['verify_details']
            print(f"          color={d.get('color', 0):.3f} "
                  f"texture={d.get('texture', 0):.3f} "
                  f"edge={d.get('edge', 0):.3f}")
            print(f"          final={d.get('final', 0):.3f} "
                  f"threshold={d.get('threshold', 0):.3f}")


def test_image(model, model_names, img_path, mode_config, bbox_config,
               smoke_config, env_args):
    """Test detection tren 1 anh."""
    img = cv2.imread(img_path)
    if img is None:
        print(f"  [ERROR] Cannot read: {img_path}")
        return None, None

    env_brightness = measure_brightness(img)
    yolo_conf = mode_config.get("yolo_conf", 0.25)
    imgsz = env_args['imgsz']
    device = env_args['device']

    results = model.predict(
        source=img, conf=yolo_conf, imgsz=imgsz,
        device=device, verbose=False
    )

    if not results:
        return {'fire_bboxes': [], 'smoke_bboxes': [],
                'has_fire': False, 'has_smoke': False, 'fire_scores': []}, img

    r = results[0]
    boxes = getattr(r, 'boxes', None)

    det_result = process_detections(
        boxes, img, model_names, mode_config, bbox_config,
        env_brightness, env_args['enable_smoke'], smoke_config
    )

    return det_result, img


def test_video(model, model_names, source, mode_config, bbox_config,
               smoke_config, env_args, args):
    """Test detection tren video/webcam."""
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open: {source}")
        return

    # Video writer for save
    writer = None
    if args.save:
        save_dir = Path(args.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_name = Path(str(source)).stem if isinstance(source, str) else "webcam"
        out_path = save_dir / f"{out_name}_result.mp4"
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        print(f"[SAVE] Recording to: {out_path}")

    flicker = FlickerDetector()
    fire_voter = FrameVoter()
    smoke_voter = FrameVoter()
    motion = MotionAnalyzer()

    confirm_frames = mode_config.get("confirm_frames", 1)
    smoke_confirm = 2
    if smoke_config:
        smoke_confirm = smoke_config.get("confirm_frames", 2)

    fps_time = time.time()
    fps_count = 0
    frame_idx = 0
    total_fire = 0
    total_smoke = 0

    print(f"[VIDEO] Playing... Press 'q' to quit, 'p' to pause")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        env_brightness = measure_brightness(frame)
        flicker.update(env_brightness)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion.update(gray)

        # YOLO
        yolo_conf = mode_config.get("yolo_conf", 0.25)
        results = model.predict(
            source=frame, conf=yolo_conf,
            imgsz=env_args['imgsz'],
            device=env_args['device'], verbose=False
        )

        det_result = {'fire_bboxes': [], 'smoke_bboxes': [],
                      'has_fire': False, 'has_smoke': False, 'fire_scores': []}
        if results:
            r = results[0]
            boxes = getattr(r, 'boxes', None)
            det_result = process_detections(
                boxes, frame, model_names, mode_config, bbox_config,
                env_brightness, env_args['enable_smoke'], smoke_config
            )

        # Voting
        fire_voter.update(det_result['has_fire'])
        smoke_voter.update(det_result['has_smoke'])
        fire_confirmed = fire_voter.is_confirmed(confirm_frames)
        smoke_confirmed = smoke_voter.is_confirmed(smoke_confirm)

        if fire_confirmed:
            total_fire += 1
        if smoke_confirmed:
            total_smoke += 1

        # FPS
        fps_count += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps = fps_count / elapsed
            fps_count = 0
            fps_time = time.time()
        else:
            fps = fps_count / max(elapsed, 0.001)

        # Motion score
        motion_s = motion.get_motion_score(gray)

        info = (f"Frame:{frame_idx} FPS:{fps:.1f} "
                f"Bright:{env_brightness:.0f} Motion:{motion_s:.2f}")

        annotated = draw_detections(
            frame.copy(), det_result['fire_bboxes'], det_result['smoke_bboxes'],
            fire_confirmed, smoke_confirmed, info
        )

        # Verbose print
        if args.verbose and (det_result['has_fire'] or det_result['has_smoke']):
            print(f"\n[Frame {frame_idx}]")
            print_detection_details(det_result, env_brightness, verbose=True)

        # Save
        if writer:
            writer.write(annotated)

        # Show
        if not args.no_show:
            cv2.imshow('Fire Detection Test', annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('p'):
                cv2.waitKey(0)  # Pause until any key

    cap.release()
    if writer:
        writer.release()
    if not args.no_show:
        cv2.destroyAllWindows()

    print(f"\n[VIDEO] Done: {frame_idx} frames")
    print(f"[VIDEO] Fire confirmed frames: {total_fire}")
    print(f"[VIDEO] Smoke confirmed frames: {total_smoke}")


def main():
    args = parse_args()

    # Determine source
    source = args.input or args.source
    if source is None:
        print("Usage: python test_fire.py <image|video|folder> [--verbose]")
        print("       python test_fire.py --source 0")
        sys.exit(1)

    # Config
    config = load_config(args.config)
    if args.mode:
        config['active_mode'] = args.mode

    mode_config, mode_name = get_mode_config(config)
    bbox_config = config.get("bbox", DEFAULT_CONFIG["bbox"])
    enable_smoke = config.get("enable_smoke", True)
    smoke_config = None
    if enable_smoke:
        smoke_modes = config.get("smoke_modes", DEFAULT_CONFIG["smoke_modes"])
        smoke_config = smoke_modes.get(mode_name, smoke_modes.get("sensitive"))

    # Model
    weights = args.weights or config["model"]["weights"]
    imgsz = config["model"].get("imgsz", 640)
    device = config["model"].get("device")

    print(f"[TEST] Model: {weights}")
    print(f"[TEST] Mode: {mode_name}")
    print(f"[TEST] Smoke detection: {'ON' if enable_smoke else 'OFF'}")

    model = YOLO(weights)
    model_names = getattr(model, 'names', {}) or {}
    print(f"[TEST] Classes: {model_names}\n")

    env_args = {
        'imgsz': imgsz,
        'device': device,
        'enable_smoke': enable_smoke
    }

    source_path = Path(source) if not source.isdigit() else None

    # Webcam
    if source.isdigit() or args.source is not None:
        test_video(model, model_names, source, mode_config, bbox_config,
                   smoke_config, env_args, args)
        return

    # Directory
    if source_path and source_path.is_dir():
        exts = ['*.jpg', '*.jpeg', '*.png', '*.bmp']
        images = []
        for ext in exts:
            images.extend(sorted(source_path.glob(ext)))

        if not images:
            print(f"[ERROR] No images found in: {source}")
            return

        print(f"[TEST] Found {len(images)} images in {source}\n")

        save_dir = Path(args.save_dir)
        if args.save:
            save_dir.mkdir(parents=True, exist_ok=True)

        total_fire = 0
        total_smoke = 0

        for i, img_path in enumerate(images):
            print(f"[{i+1}/{len(images)}] {img_path.name}")

            det_result, img = test_image(
                model, model_names, str(img_path), mode_config, bbox_config,
                smoke_config, env_args
            )

            if det_result is None:
                continue

            env_brightness = measure_brightness(img)
            n_fire = len(det_result.get('fire_bboxes', []))
            n_smoke = len(det_result.get('smoke_bboxes', []))
            total_fire += n_fire
            total_smoke += n_smoke

            print_detection_details(det_result, env_brightness, args.verbose)

            if args.save and img is not None:
                annotated = draw_detections(
                    img.copy(),
                    det_result.get('fire_bboxes', []),
                    det_result.get('smoke_bboxes', []),
                    det_result.get('has_fire', False),
                    det_result.get('has_smoke', False)
                )
                out_path = save_dir / f"result_{img_path.name}"
                cv2.imwrite(str(out_path), annotated)

            if not args.no_show and img is not None:
                annotated = draw_detections(
                    img.copy(),
                    det_result.get('fire_bboxes', []),
                    det_result.get('smoke_bboxes', []),
                    det_result.get('has_fire', False),
                    det_result.get('has_smoke', False)
                )
                cv2.imshow('Fire Detection Test', annotated)
                key = cv2.waitKey(0) & 0xFF
                if key == ord('q'):
                    break

        if not args.no_show:
            cv2.destroyAllWindows()

        print(f"\n{'='*50}")
        print(f"[SUMMARY] {len(images)} images")
        print(f"[SUMMARY] Fire detections: {total_fire}")
        print(f"[SUMMARY] Smoke detections: {total_smoke}")
        if args.save:
            print(f"[SUMMARY] Results saved to: {save_dir}")
        return

    # Single file
    if source_path and source_path.exists():
        suffix = source_path.suffix.lower()
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

        if suffix in video_exts:
            # Video
            test_video(model, model_names, source, mode_config, bbox_config,
                       smoke_config, env_args, args)
        else:
            # Image
            print(f"[TEST] Image: {source}")
            det_result, img = test_image(
                model, model_names, source, mode_config, bbox_config,
                smoke_config, env_args
            )

            if det_result is None:
                return

            env_brightness = measure_brightness(img)
            print_detection_details(det_result, env_brightness, args.verbose)

            if img is not None:
                annotated = draw_detections(
                    img.copy(),
                    det_result.get('fire_bboxes', []),
                    det_result.get('smoke_bboxes', []),
                    det_result.get('has_fire', False),
                    det_result.get('has_smoke', False)
                )

                if args.save:
                    save_dir = Path(args.save_dir)
                    save_dir.mkdir(parents=True, exist_ok=True)
                    out_path = save_dir / f"result_{source_path.name}"
                    cv2.imwrite(str(out_path), annotated)
                    print(f"\n[SAVE] Result saved: {out_path}")

                if not args.no_show:
                    cv2.imshow('Fire Detection Test', annotated)
                    print("\nPress any key to close...")
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
    else:
        print(f"[ERROR] File not found: {source}")


if __name__ == '__main__':
    main()
