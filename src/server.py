#!/usr/bin/env python3
"""
He thong Kiem soat Lua va Khoi - Server chinh
Web dashboard voi upload anh/video, phat hien lua/khoi bang YOLO + multi-criteria.

Chay server:     python server.py
Chay voi webcam: python server.py --source 0 --show
"""

from flask import Flask, request, jsonify, send_file, redirect, Response, make_response
from datetime import datetime
import os
import threading
import glob
import numpy as np
import cv2
import csv
import json
import base64
import tempfile
from pathlib import Path
import argparse
import serial
import time
import uuid
import requests

from fire_utils import (
    load_config, get_mode_config, measure_brightness,
    process_detections, draw_detections, compute_fire_score,
    FlickerDetector, FrameVoter, MotionAnalyzer, FireRegionTracker,
    DEFAULT_CONFIG, verify_fire_roi
)

# Turret control (optional - requires ESP32-CAM 2 + Arduino)
try:
    from stereo import stereo_distance
    from turret_controller import TurretController
    TURRET_AVAILABLE = True
except Exception as e:
    print(f"[TURRET] module load failed: {e}")
    TURRET_AVAILABLE = False
    stereo_distance = None
    TurretController = None

# ESP32-CAM 2 control endpoint URL (set via /turret/config or env)
ESP2_CONTROL_URL = os.environ.get("ESP2_URL", "")
turret = TurretController(ESP2_CONTROL_URL) if TURRET_AVAILABLE else None
turret_lock = threading.Lock()

# YOLO model (optional import)
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

# SAHI for small object detection
try:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction
    SAHI_AVAILABLE = True
except Exception:
    SAHI_AVAILABLE = False


# ============================================================
# GLOBALS
# ============================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max (video)

# CORS cho React dev server
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

# Config
config = load_config("config.json")

# Model
model = None
model_names = {}
model_lock = threading.Lock()

# Serial
ser = None
ser_lock = threading.Lock()
beep_sent = False
beep_lock = threading.Lock()

# Detection state - per camera
CAM_IDS = ["cam1", "cam2"]
flicker_detector = None
motion_analyzers = {cam: MotionAnalyzer() for cam in CAM_IDS}
fire_voters = {cam: FrameVoter() for cam in CAM_IDS}
smoke_voters = {cam: FrameVoter() for cam in CAM_IDS}
fire_trackers = {cam: FireRegionTracker(history_size=10, iou_threshold=0.3) for cam in CAM_IDS}
last_detection_result = {cam: {} for cam in CAM_IDS}
last_detection_lock = threading.Lock()

# Image storage
image_counter = 0
image_counter_lock = threading.Lock()

# Latest frame for MJPEG stream - per camera
latest_frames = {cam: None for cam in CAM_IDS}
latest_frame_locks = {cam: threading.Lock() for cam in CAM_IDS}
latest_frame_events = {cam: threading.Event() for cam in CAM_IDS}

# Previous frame for smoke motion check - per camera
prev_gray_frames = {cam: None for cam in CAM_IDS}
prev_gray_locks = {cam: threading.Lock() for cam in CAM_IDS}

# Video processing state
video_jobs = {}
video_jobs_lock = threading.Lock()


# ============================================================
# INIT FUNCTIONS
# ============================================================

sahi_model = None

def init_model():
    """Load YOLO model + SAHI model for small fire detection."""
    global model, model_names, sahi_model
    if YOLO is None:
        print("[MODEL] ultralytics not installed, skipping YOLO")
        return False

    weights = config["model"]["weights"]
    if not os.path.exists(weights):
        print(f"[MODEL] Weights not found: {weights}")
        return False

    try:
        model = YOLO(weights)
        model_names = getattr(model, 'names', {}) or {}
        print(f"[MODEL] Loaded: {weights}")
        print(f"[MODEL] Classes: {model_names}")

        # Init SAHI for small fire detection
        if SAHI_AVAILABLE:
            device_str = config["model"].get("device", "cpu")
            sahi_device = f"cuda:{device_str}" if isinstance(device_str, int) else str(device_str)
            sahi_model = AutoDetectionModel.from_pretrained(
                model_type='yolov8',
                model_path=weights,
                confidence_threshold=0.15,
                device=sahi_device
            )
            print(f"[SAHI] Loaded for small fire detection on {sahi_device}")
        else:
            print("[SAHI] Not available, install: pip install sahi")

        return True
    except Exception as e:
        print(f"[MODEL] Failed to load: {e}")
        return False


def init_serial():
    """Init Arduino serial connection."""
    global ser
    serial_config = config.get("serial", {})
    if not serial_config.get("enabled", True):
        print("[SERIAL] Disabled in config")
        return False

    port = serial_config.get("port", "COM4")
    baudrate = serial_config.get("baudrate", 9600)

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)
        print(f"[SERIAL] Connected: {port} @ {baudrate}")
        return True
    except Exception as e:
        ser = None
        print(f"[SERIAL] Not available: {e}")
        return False


def init_flicker():
    """Init flicker detector from config."""
    global flicker_detector
    fc = config.get("flicker", DEFAULT_CONFIG["flicker"])
    flicker_detector = FlickerDetector(
        history_size=fc.get("history_size", 5),
        min_std=fc.get("min_std", 8.0),
        normalize_factor=fc.get("normalize_factor", 20.0)
    )


def ensure_dirs():
    """Tao cac thu muc can thiet."""
    image_dir = config["paths"]["image_dir"]
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs("test_results", exist_ok=True)


def ensure_csv():
    """Tao CSV header neu chua co."""
    csv_path = config["paths"]["csv_path"]
    csv_dir = os.path.dirname(csv_path)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'filename', 'type', 'class', 'class_id',
                'conf', 'x1', 'y1', 'x2', 'y2', 'mode'
            ])


# ============================================================
# BUZZER CONTROL
# ============================================================

def send_buzzer(command="BEEP"):
    """Gui lenh toi Arduino (thread-safe)."""
    with ser_lock:
        if ser is None:
            return False
        try:
            ser.write(f"{command}\n".encode())
            return True
        except Exception as e:
            print(f"[SERIAL] Write error: {e}")
            return False


def handle_buzzer(fire_confirmed):
    """Xu ly buzzer logic."""
    global beep_sent
    with beep_lock:
        if fire_confirmed and not beep_sent:
            if send_buzzer("BEEP"):
                beep_sent = True
                print("[BUZZER] BEEP sent")
        elif not fire_confirmed and beep_sent:
            send_buzzer("STOP")
            beep_sent = False


# ============================================================
# SERVO CONTROL - Tinh goc tu toa do lua trong khung hinh
# ============================================================

# Cau hinh servo
SERVO_CONFIG = {
    "img_w": 800,          # Chieu rong khung hinh
    "img_h": 600,          # Chieu cao khung hinh
    "fov_h": 60.0,         # Goc nhin ngang camera (do) - OV2640 ~60°
    "fov_v": 45.0,         # Goc nhin doc camera (do) - OV2640 ~45°
    "pan_center": 90,      # Goc servo ngang khi nhin thang (0-180)
    "tilt_center": 90,     # Goc servo doc khi nhin thang (0-180)
    "pan_min": 0,
    "pan_max": 180,
    "tilt_min": 0,
    "tilt_max": 180,
    "pan_invert": False,   # Dao chieu ngang (True neu servo lap nguoc)
    "tilt_invert": False,  # Dao chieu doc
}

last_servo_pan = 90
last_servo_tilt = 90


def calc_servo_angles(fire_bboxes):
    """Tinh goc servo tu bbox lua lon nhat.

    Pixel (x,y) trong khung hinh -> goc lech so voi tam -> goc servo.
    """
    if not fire_bboxes:
        return None, None

    # Chon bbox co confidence cao nhat
    best = max(fire_bboxes, key=lambda b: b.get('conf', 0))
    x1, y1, x2, y2 = best['bbox']

    # Tam ngon lua (pixel)
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    cfg = SERVO_CONFIG
    img_w = cfg["img_w"]
    img_h = cfg["img_h"]

    # Lech so voi tam khung hinh (-0.5 den +0.5)
    offset_x = (cx / img_w) - 0.5   # + = phai, - = trai
    offset_y = (cy / img_h) - 0.5   # + = duoi, - = tren

    # Quy doi sang goc (do)
    angle_h = offset_x * cfg["fov_h"]  # Lech ngang (do)
    angle_v = offset_y * cfg["fov_v"]  # Lech doc (do)

    # Dao chieu neu can
    if cfg["pan_invert"]:
        angle_h = -angle_h
    if cfg["tilt_invert"]:
        angle_v = -angle_v

    # Goc servo = tam + lech
    pan = cfg["pan_center"] + angle_h
    tilt = cfg["tilt_center"] + angle_v

    # Gioi han
    pan = max(cfg["pan_min"], min(cfg["pan_max"], pan))
    tilt = max(cfg["tilt_min"], min(cfg["tilt_max"], tilt))

    return round(pan, 1), round(tilt, 1)


def send_servo(fire_bboxes):
    """Tinh goc va gui lenh servo qua Serial."""
    global last_servo_pan, last_servo_tilt

    pan, tilt = calc_servo_angles(fire_bboxes)
    if pan is None:
        return

    # Chi gui khi goc thay doi > 2 do (tranh rung servo)
    if abs(pan - last_servo_pan) < 2.0 and abs(tilt - last_servo_tilt) < 2.0:
        return

    last_servo_pan = pan
    last_servo_tilt = tilt

    command = f"SERVO:{pan:.0f},{tilt:.0f}"
    if send_buzzer(command):  # Dung chung ham gui Serial
        print(f"[SERVO] pan={pan:.0f} tilt={tilt:.0f}")


# ============================================================
# DETECTION PIPELINE
# ============================================================

def detect_single_image(img):
    """Detect lua/khoi tren 1 anh.

    Returns:
        (det_result, annotated_img, mode_name)
    """
    if model is None:
        return None, img, "unknown"

    mode_config, mode_name = get_mode_config(config)
    bbox_config = config.get("bbox", DEFAULT_CONFIG["bbox"])
    enable_smoke = config.get("enable_smoke", True)
    smoke_config = None
    if enable_smoke:
        smoke_modes = config.get("smoke_modes", DEFAULT_CONFIG["smoke_modes"])
        smoke_config = smoke_modes.get(mode_name, smoke_modes.get("sensitive"))

    env_brightness = measure_brightness(img)
    yolo_conf = mode_config.get("yolo_conf", 0.25)
    imgsz = config["model"].get("imgsz", 640)
    device = config["model"].get("device")

    try:
        with model_lock:
            results = model.predict(
                source=img, conf=yolo_conf, imgsz=imgsz,
                device=device, verbose=False
            )
    except Exception as e:
        return None, img, mode_name

    if not results:
        return {'fire_bboxes': [], 'smoke_bboxes': [],
                'has_fire': False, 'has_smoke': False}, img, mode_name

    r = results[0]
    boxes = getattr(r, 'boxes', None)

    det_result = process_detections(
        boxes, img, model_names, mode_config, bbox_config,
        env_brightness, enable_smoke, smoke_config
    )

    # SAHI fallback for small fire in single image
    if not det_result['has_fire'] and sahi_model is not None:
        try:
            tmp_path = os.path.join(tempfile.gettempdir(), "sahi_single.jpg")
            cv2.imwrite(tmp_path, img)
            # Slice 640x640 co dinh - tot nhat cho small fire detection
            slice_h = 640
            slice_w = 640
            with model_lock:
                sahi_result = get_sliced_prediction(
                    tmp_path, sahi_model,
                    slice_height=slice_h, slice_width=slice_w,
                    overlap_height_ratio=0.3, overlap_width_ratio=0.3,
                    verbose=0
                )
            # Chi lay 1 fire co confidence cao nhat tu SAHI
            best_fire = None
            for pred in sahi_result.object_prediction_list:
                if pred.category.name == 'fire' and pred.score.value >= 0.50:
                    if best_fire is None or pred.score.value > best_fire.score.value:
                        best_fire = pred
            if best_fire is not None:
                bbox = best_fire.bbox
                x1, y1 = int(bbox.minx), int(bbox.miny)
                x2, y2 = int(bbox.maxx), int(bbox.maxy)
                # Verify fire ROI
                h_img, w_img = img.shape[:2]
                rx1, ry1 = max(0, x1), max(0, y1)
                rx2, ry2 = min(w_img, x2), min(h_img, y2)
                roi = img[ry1:ry2, rx1:rx2]
                verify_threshold = mode_config.get('verify_threshold', 0.28)
                if roi.size > 0:
                    is_fire, v_score, v_details = verify_fire_roi(
                        roi, env_brightness, threshold=verify_threshold
                    )
                else:
                    is_fire, v_score, v_details = False, 0.0, {}
                det_result['has_fire'] = True
                fire_entry = {
                    'bbox': [x1, y1, x2, y2],
                    'conf': best_fire.score.value,
                    'class': 'fire', 'class_id': 1,
                    'source': 'sahi',
                    'verify_score': v_score,
                    'verify_details': v_details
                }
                det_result['fire_bboxes'].append(fire_entry)
                det_result['fire_scores'].append(v_score)
                print(f"[SAHI] Fire in image: conf={best_fire.score.value:.3f} verify={v_score:.3f} at ({x1},{y1})-({x2},{y2})")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            print(f"[SAHI] Single image error: {e}")

    # Ve bounding boxes
    annotated = draw_detections(
        img.copy(),
        det_result['fire_bboxes'],
        det_result['smoke_bboxes'],
        det_result['has_fire'],
        det_result['has_smoke'],
        f"Mode: {mode_name} | Brightness: {env_brightness:.0f}"
    )

    return det_result, annotated, mode_name


def detect_frame(img, cam_id="cam1"):
    """Pipeline phat hien lua/khoi cho 1 frame (dung cho ESP32/webcam)."""

    if model is None:
        return {"error": "Model not loaded", "fire": False, "smoke": False}

    # Ensure per-camera state exists for dynamic cam_ids
    if cam_id not in motion_analyzers:
        motion_analyzers[cam_id] = MotionAnalyzer()
        fire_voters[cam_id] = FrameVoter()
        smoke_voters[cam_id] = FrameVoter()
        fire_trackers[cam_id] = FireRegionTracker(history_size=10, iou_threshold=0.3)
        last_detection_result[cam_id] = {}
        latest_frames[cam_id] = None
        latest_frame_locks[cam_id] = threading.Lock()
        latest_frame_events[cam_id] = threading.Event()
        prev_gray_frames[cam_id] = None
        prev_gray_locks[cam_id] = threading.Lock()

    mode_config, mode_name = get_mode_config(config)
    bbox_config = config.get("bbox", DEFAULT_CONFIG["bbox"])
    enable_smoke = config.get("enable_smoke", True)
    smoke_config = None
    if enable_smoke:
        smoke_modes = config.get("smoke_modes", DEFAULT_CONFIG["smoke_modes"])
        smoke_config = smoke_modes.get(mode_name, smoke_modes.get("sensitive"))

    env_brightness = measure_brightness(img)

    if flicker_detector:
        flicker_detector.update(env_brightness)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    motion_analyzers[cam_id].update(gray)

    yolo_conf = mode_config.get("yolo_conf", 0.25)
    imgsz = config["model"].get("imgsz", 640)
    device = config["model"].get("device")

    try:
        with model_lock:
            results = model.predict(
                source=img, conf=yolo_conf, imgsz=imgsz,
                device=device, verbose=False
            )
    except Exception as e:
        return {"error": f"Inference error: {e}", "fire": False, "smoke": False}

    if not results:
        fire_voters[cam_id].update(False)
        smoke_voters[cam_id].update(False)
        handle_buzzer(False)
        return {"fire": False, "smoke": False, "detections": []}

    r = results[0]
    boxes = getattr(r, 'boxes', None)

    det_result = process_detections(
        boxes, img, model_names, mode_config, bbox_config,
        env_brightness, enable_smoke, smoke_config
    )

    # Motion check: lua va khoi phai co chuyen dong/nhap nhay
    # Vat dung yen (den LED, chai nuoc, v.v.) se bi reject
    with prev_gray_locks[cam_id]:
        prev_gray_frame = prev_gray_frames[cam_id]
        if prev_gray_frame is not None and prev_gray_frame.shape == gray.shape:
            # Check fire motion - lua phai nhap nhay (motion > 3)
            if det_result['has_fire'] and det_result['fire_bboxes']:
                new_fire_bboxes = []
                for fb in det_result['fire_bboxes']:
                    x1, y1, x2, y2 = fb['bbox']
                    h_img, w_img = gray.shape[:2]
                    x1c, y1c = max(0, x1), max(0, y1)
                    x2c, y2c = min(w_img, x2), min(h_img, y2)
                    if x2c > x1c and y2c > y1c:
                        roi_curr = gray[y1c:y2c, x1c:x2c]
                        roi_prev = prev_gray_frame[y1c:y2c, x1c:x2c]
                        diff = cv2.absdiff(roi_curr, roi_prev)
                        motion = float(np.mean(diff))
                        # Lua nho (< 40x40px) phai co motion cao hon de loai LED
                        bbox_w = x2c - x1c
                        bbox_h = y2c - y1c
                        min_motion = 3.0 if (bbox_w > 40 and bbox_h > 40) else 5.0
                        if motion > min_motion:
                            new_fire_bboxes.append(fb)
                        else:
                            print(f"[FIRE] Rejected static object (motion={motion:.1f}, size={bbox_w}x{bbox_h})")
                    else:
                        new_fire_bboxes.append(fb)
                det_result['fire_bboxes'] = new_fire_bboxes
                det_result['has_fire'] = len(new_fire_bboxes) > 0

            # Check smoke motion - khoi phai di chuyen (motion > 5)
            if det_result['has_smoke'] and det_result['smoke_bboxes']:
                new_smoke_bboxes = []
                for sb in det_result['smoke_bboxes']:
                    x1, y1, x2, y2 = sb['bbox']
                    h_img, w_img = gray.shape[:2]
                    x1c, y1c = max(0, x1), max(0, y1)
                    x2c, y2c = min(w_img, x2), min(h_img, y2)
                    if x2c > x1c and y2c > y1c:
                        roi_curr = gray[y1c:y2c, x1c:x2c]
                        roi_prev = prev_gray_frame[y1c:y2c, x1c:x2c]
                        diff = cv2.absdiff(roi_curr, roi_prev)
                        motion = float(np.mean(diff))
                        if motion > 5.0:
                            new_smoke_bboxes.append(sb)
                        else:
                            print(f"[SMOKE] Rejected static object (motion={motion:.1f})")
                    else:
                        new_smoke_bboxes.append(sb)
                det_result['smoke_bboxes'] = new_smoke_bboxes
                det_result['has_smoke'] = len(new_smoke_bboxes) > 0

        prev_gray_frames[cam_id] = gray.copy()

    # SAHI fallback - chi dung cho detect_single_image, khong dung realtime vi qua cham
    if False and not det_result['has_fire'] and sahi_model is not None:
        try:
            tmp_path = os.path.join(tempfile.gettempdir(), f"sahi_{uuid.uuid4().hex[:8]}.jpg")
            cv2.imwrite(tmp_path, img)
            with model_lock:
                sahi_result = get_sliced_prediction(
                    tmp_path, sahi_model,
                    slice_height=240, slice_width=240,
                    overlap_height_ratio=0.3, overlap_width_ratio=0.3,
                    verbose=0
                )
            # Chi lay 1 fire co confidence cao nhat tu SAHI
            best_fire = None
            for pred in sahi_result.object_prediction_list:
                if pred.category.name == 'fire' and pred.score.value >= 0.50:
                    if best_fire is None or pred.score.value > best_fire.score.value:
                        best_fire = pred
            if best_fire is not None:
                bbox = best_fire.bbox
                x1, y1 = int(bbox.minx), int(bbox.miny)
                x2, y2 = int(bbox.maxx), int(bbox.maxy)
                # Verify fire ROI
                h_img, w_img = img.shape[:2]
                rx1, ry1 = max(0, x1), max(0, y1)
                rx2, ry2 = min(w_img, x2), min(h_img, y2)
                roi = img[ry1:ry2, rx1:rx2]
                verify_threshold = mode_config.get('verify_threshold', 0.28)
                if roi.size > 0:
                    is_fire, v_score, v_details = verify_fire_roi(
                        roi, env_brightness, threshold=verify_threshold
                    )
                else:
                    is_fire, v_score, v_details = False, 0.0, {}
                det_result['has_fire'] = True
                fire_entry = {
                    'bbox': [x1, y1, x2, y2],
                    'conf': best_fire.score.value,
                    'class': 'fire',
                    'class_id': 1,
                    'source': 'sahi',
                    'verify_score': v_score,
                    'verify_details': v_details
                }
                det_result['fire_bboxes'].append(fire_entry)
                det_result['fire_scores'].append(v_score)
                print(f"[SAHI] Small fire detected! conf={best_fire.score.value:.3f} verify={v_score:.3f} at ({x1},{y1})-({x2},{y2})")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            print(f"[SAHI] Error: {e}")

    use_score_fusion = mode_config.get("use_score_fusion", False)
    score_threshold = mode_config.get("score_threshold", 0.55)
    score_weights = mode_config.get("score_weights")
    fusion_confirmed = False

    if use_score_fusion and det_result['fire_scores']:
        has_flicker, flicker_score = (
            flicker_detector.compute() if flicker_detector else (False, 0.0)
        )
        for score_data in det_result['fire_scores']:
            fused = compute_fire_score(
                score_data['yolo_conf'], score_data['color_ratio'],
                flicker_score, score_weights
            )
            if fused >= score_threshold:
                fusion_confirmed = True
                break

    has_fire = det_result['has_fire']
    if use_score_fusion:
        has_fire = has_fire and fusion_confirmed

    # Fire Region Tracker: theo doi vung lua qua frame, tinh rating
    fire_rating = 0.5
    fire_rating_details = {}
    cam_fire_tracker = fire_trackers[cam_id]
    if has_fire and det_result['fire_bboxes']:
        best_fire = max(det_result['fire_bboxes'], key=lambda b: b['conf'])
        bbox = best_fire['bbox']
        x1, y1, x2, y2 = bbox
        h_img, w_img = gray.shape[:2]
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w_img, x2), min(h_img, y2)
        roi_gray = gray[y1c:y2c, x1c:x2c] if x2c > x1c and y2c > y1c else None
        cam_fire_tracker.update(bbox, roi_gray)
        fire_rating, fire_rating_details = cam_fire_tracker.get_rating()

        # Rating thap (< 0.15) sau nhieu frame = LED/vat tinh -> reject
        if fire_rating_details.get('frames', 0) >= 5 and fire_rating < 0.15:
            has_fire = False
            print(f"[FIRE-RATING] Rejected static fire (rating={fire_rating:.3f}, details={fire_rating_details})")
    else:
        # Khong co fire -> reset tracker sau 1 khoang
        pass

    fire_voters[cam_id].update(has_fire)
    smoke_voters[cam_id].update(det_result['has_smoke'])

    confirm_frames = mode_config.get("confirm_frames", 1)
    fire_confirmed = fire_voters[cam_id].is_confirmed(confirm_frames)

    smoke_confirm = 2
    if smoke_config:
        smoke_confirm = smoke_config.get("confirm_frames", 2)
    smoke_confirmed = smoke_voters[cam_id].is_confirmed(smoke_confirm)

    if mode_config.get("flicker_required", False) and fire_confirmed:
        if flicker_detector:
            has_flicker, _ = flicker_detector.compute()
            if not has_flicker:
                fire_confirmed = False

    handle_buzzer(fire_confirmed)

    # Gui servo huong vao lua (chi dung cam1 lam cam chinh)
    if fire_confirmed and cam_id == "cam1":
        send_servo(det_result['fire_bboxes'])

    result = {
        "fire": fire_confirmed,
        "smoke": smoke_confirmed,
        "fire_raw": has_fire,
        "fire_count": fire_voters[cam_id].count,
        "fire_rating": round(fire_rating, 3),
        "fire_rating_details": fire_rating_details,
        "fire_bboxes": det_result['fire_bboxes'],
        "smoke_bboxes": det_result['smoke_bboxes'],
        "mode": mode_name,
        "brightness": round(env_brightness, 1),
        "cam_id": cam_id,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    }

    with last_detection_lock:
        last_detection_result[cam_id] = result.copy()

    # Luu lich su phat hien
    add_to_history(det_result, img, cam_id=cam_id)

    return result


def log_detections(filename, result, mode_name):
    """Ghi detection vao CSV."""
    csv_path = config["paths"]["csv_path"]
    timestamp = result.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    rows = []
    for fb in result.get("fire_bboxes", []):
        x1, y1, x2, y2 = fb['bbox']
        rows.append([
            timestamp, filename, 'fire', fb['class'], fb['class_id'],
            f"{fb['conf']:.3f}", x1, y1, x2, y2, mode_name
        ])
    for sb in result.get("smoke_bboxes", []):
        x1, y1, x2, y2 = sb['bbox']
        rows.append([
            timestamp, filename, 'smoke', sb['class'], sb['class_id'],
            f"{sb['conf']:.3f}", x1, y1, x2, y2, mode_name
        ])

    if rows:
        try:
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
        except Exception as e:
            print(f"[CSV] Write error: {e}")


# ============================================================
# VIDEO PROCESSING
# ============================================================

def process_video_thread(job_id, video_path):
    """Xu ly video trong background thread."""
    job = video_jobs[job_id]
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        job['status'] = 'error'
        job['error'] = 'Cannot open video'
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    job['total_frames'] = total_frames
    job['fps'] = fps
    job['width'] = w
    job['height'] = h
    job['status'] = 'processing'

    # Output video
    out_path = os.path.join("test_results", f"result_{job_id}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    frame_idx = 0
    fire_frames = 0
    smoke_frames = 0
    # Process every N frames for speed (skip frames)
    skip = max(1, int(fps / 10))  # Process ~10 fps

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        if frame_idx % skip == 0:
            det_result, annotated, mode_name = detect_single_image(frame)
            if det_result and det_result['has_fire']:
                fire_frames += 1
            if det_result and det_result['has_smoke']:
                smoke_frames += 1
            out.write(annotated)
            # Luu frame moi nhat de preview
            _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            job['preview_b64'] = base64.b64encode(buf).decode('utf-8')
        else:
            out.write(frame)

        job['current_frame'] = frame_idx
        job['fire_frames'] = fire_frames
        job['smoke_frames'] = smoke_frames

    cap.release()
    out.release()

    job['status'] = 'done'
    job['output_path'] = out_path
    job['fire_frames'] = fire_frames
    job['smoke_frames'] = smoke_frames
    print(f"[VIDEO] Job {job_id} done: {fire_frames} fire, {smoke_frames} smoke frames")


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route('/')
def index():
    """Dashboard chinh."""
    return DASHBOARD_HTML


def _process_upload_async(img, filename, filepath, cam_id):
    """Background thread xu ly detect cho upload - khong block ESP32."""
    try:
        cv2.imwrite(filepath, img)
    except Exception as e:
        print(f"[SAVE] Error: {e}")

    result = detect_frame(img, cam_id=cam_id)

    # Ve bbox len frame roi luu cho MJPEG stream
    annotated = draw_detections(
        img.copy(),
        result.get('fire_bboxes', []),
        result.get('smoke_bboxes', []),
        result.get('fire', False),
        result.get('smoke', False),
        f"Mode: {result.get('mode', '')} | {cam_id}"
    )

    _, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
    frame_bytes = jpeg.tobytes()
    # Ensure per-camera locks exist for dynamic cam_ids
    if cam_id not in latest_frame_locks:
        latest_frame_locks[cam_id] = threading.Lock()
        latest_frame_events[cam_id] = threading.Event()
        latest_frames[cam_id] = None
    with latest_frame_locks[cam_id]:
        latest_frames[cam_id] = frame_bytes
    latest_frame_events[cam_id].set()

    mode_config, mode_name = get_mode_config(config)
    if result.get("fire") or result.get("smoke"):
        log_detections(filename, result, mode_name)

    fire_status = "FIRE!" if result.get("fire") else "OK"
    smoke_status = " + SMOKE" if result.get("smoke") else ""
    n_fire = len(result.get("fire_bboxes", []))
    n_smoke = len(result.get("smoke_bboxes", []))
    print(f"[{cam_id}] {filename} | {fire_status}{smoke_status} | "
          f"fire:{n_fire} smoke:{n_smoke} | mode:{mode_name}")


@app.route('/upload', methods=['POST'])
def upload_image():
    """Nhan anh JPEG tu ESP32-CAM - tra ve ngay, detect chay background."""
    global image_counter

    data = request.get_data()
    if not data or len(data) < 100:
        return jsonify({"error": "No image data"}), 400

    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Invalid image"}), 400

    image_dir = config["paths"]["image_dir"]
    with image_counter_lock:
        image_counter += 1
        counter = image_counter

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"esp32_{timestamp}_{counter:04d}.jpg"
    filepath = os.path.join(image_dir, filename)

    cam_id = request.args.get("cam", "cam1")

    # Detect chay background - ESP32 khong can doi
    threading.Thread(
        target=_process_upload_async,
        args=(img.copy(), filename, filepath, cam_id),
        daemon=True
    ).start()

    # Tra ket qua truoc do cho ESP32 (neu co)
    with last_detection_lock:
        cam_result = last_detection_result.get(cam_id, {})
        prev = cam_result.copy() if cam_result else {}

    # Build response voi toa do lua cho fire_turret
    resp = {
        "status": "ok",
        "filename": filename,
        "cam_id": cam_id,
        "fire": prev.get("fire", False),
        "smoke": prev.get("smoke", False)
    }

    # Them primary_target + fire_targets cho turret servo
    fire_bboxes = prev.get("fire_bboxes", [])
    if fire_bboxes:
        # Chon bbox confidence cao nhat lam primary target
        best = max(fire_bboxes, key=lambda b: b.get('conf', 0))
        x1, y1, x2, y2 = best['bbox']
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        resp["primary_target"] = {
            "x": cx,
            "y": cy,
            "conf": round(best.get('conf', 0), 3)
        }
        resp["fire_targets"] = []
        for fb in fire_bboxes:
            bx1, by1, bx2, by2 = fb['bbox']
            area_pct = ((bx2 - bx1) * (by2 - by1)) / (800 * 600) * 100
            resp["fire_targets"].append({
                "center": [int((bx1 + bx2) / 2), int((by1 + by2) / 2)],
                "bbox": fb['bbox'],
                "conf": round(fb.get('conf', 0), 3),
                "area_percent": round(area_pct, 1)
            })

    return jsonify(resp)


@app.route('/detect_upload', methods=['POST'])
def detect_upload():
    """Upload anh tu web UI de detect."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Doc anh
    file_bytes = file.read()
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Invalid image file"}), 400

    # Detect
    det_result, annotated, mode_name = detect_single_image(img)

    # Encode annotated image thanh base64
    _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    img_b64 = base64.b64encode(buf).decode('utf-8')

    # Encode original
    _, buf_orig = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    orig_b64 = base64.b64encode(buf_orig).decode('utf-8')

    # Build response
    fire_bboxes = det_result['fire_bboxes'] if det_result else []
    smoke_bboxes = det_result['smoke_bboxes'] if det_result else []
    has_fire = det_result['has_fire'] if det_result else False
    has_smoke = det_result['has_smoke'] if det_result else False

    # Format detections
    detections = []
    for fb in fire_bboxes:
        d = {
            'type': 'fire',
            'conf': round(fb['conf'], 3),
            'verify': round(fb.get('verify_score', 0), 3),
            'bbox': fb['bbox']
        }
        if 'verify_details' in fb:
            details = fb['verify_details']
            d['color'] = round(details.get('color', 0), 3)
            d['texture'] = round(details.get('texture', 0), 3)
            d['edge'] = round(details.get('edge', 0), 3)
        detections.append(d)

    for sb in smoke_bboxes:
        d = {
            'type': 'smoke',
            'conf': round(sb['conf'], 3),
            'verify': round(sb.get('verify_score', 0), 3),
            'bbox': sb['bbox']
        }
        if 'verify_details' in sb:
            details = sb['verify_details']
            d['color'] = round(details.get('color', 0), 3)
            d['texture'] = round(details.get('texture', 0), 3)
            d['edge'] = round(details.get('edge', 0), 3)
        detections.append(d)

    return jsonify({
        "status": "ok",
        "fire": has_fire,
        "smoke": has_smoke,
        "fire_count": len(fire_bboxes),
        "smoke_count": len(smoke_bboxes),
        "detections": detections,
        "image": img_b64,
        "original": orig_b64,
        "mode": mode_name,
        "size": f"{img.shape[1]}x{img.shape[0]}"
    })


@app.route('/detect_video', methods=['POST'])
def detect_video():
    """Upload video de detect."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Save temp video
    ext = os.path.splitext(file.filename)[1] or '.mp4'
    tmp_path = os.path.join(tempfile.gettempdir(), f"fire_detect_{uuid.uuid4().hex[:8]}{ext}")
    file.save(tmp_path)

    # Create job
    job_id = uuid.uuid4().hex[:8]
    with video_jobs_lock:
        video_jobs[job_id] = {
            'status': 'starting',
            'filename': file.filename,
            'current_frame': 0,
            'total_frames': 0,
            'fire_frames': 0,
            'smoke_frames': 0,
            'preview_b64': None,
            'output_path': None,
            'error': None
        }

    # Start processing thread
    t = threading.Thread(target=process_video_thread, args=(job_id, tmp_path), daemon=True)
    t.start()

    return jsonify({"status": "ok", "job_id": job_id})


@app.route('/video_status/<job_id>')
def video_status(job_id):
    """Check video processing status."""
    with video_jobs_lock:
        job = video_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "status": job['status'],
        "filename": job['filename'],
        "current_frame": job['current_frame'],
        "total_frames": job['total_frames'],
        "fire_frames": job['fire_frames'],
        "smoke_frames": job['smoke_frames'],
        "preview": job.get('preview_b64'),
        "error": job.get('error'),
        "progress": round(job['current_frame'] / max(job['total_frames'], 1) * 100, 1)
    })


@app.route('/video_result/<job_id>')
def video_result(job_id):
    """Download video ket qua."""
    with video_jobs_lock:
        job = video_jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({"error": "Not ready"}), 404

    out_path = job.get('output_path')
    if out_path and os.path.exists(out_path):
        return send_file(out_path, mimetype='video/mp4',
                         as_attachment=True,
                         download_name=f"detected_{job['filename']}")
    return jsonify({"error": "File not found"}), 404


@app.route('/save_capture', methods=['POST'])
def save_capture():
    """Luu anh capture khi tam ngam trung fire."""
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "No image"}), 400

    # Decode base64 image
    img_data = data['image'].split(',')[1] if ',' in data['image'] else data['image']
    img_bytes = base64.b64decode(img_data)

    # Luu vao folder captures/
    cap_dir = os.path.join(os.path.dirname(__file__), '..', 'captures')
    os.makedirs(cap_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
    filename = f'capture_{ts}.jpg'
    filepath = os.path.join(cap_dir, filename)

    with open(filepath, 'wb') as f:
        f.write(img_bytes)

    print(f"[CAPTURE] Saved: {filename}")
    return jsonify({"status": "ok", "filename": filename})


@app.route('/status')
def status():
    """Tra ve trang thai hien tai - ho tro nhieu camera."""
    with last_detection_lock:
        all_cams = {}
        for cam_id, cam_result in last_detection_result.items():
            all_cams[cam_id] = cam_result.copy() if cam_result else {}

    mode_config, mode_name = get_mode_config(config)

    # Backward compatible: last_detection = cam1 result
    cam1_result = all_cams.get("cam1", {})

    return jsonify({
        "server": "running",
        "model_loaded": model is not None,
        "serial_connected": ser is not None,
        "mode": mode_name,
        "last_detection": cam1_result,
        "cameras": all_cams
    })


# ============================================================
# TURRET ENDPOINTS (stereo + servo + pump control)
# ============================================================
def _bboxes_from_result(cam_result):
    """Extract fire bboxes [[x1,y1,x2,y2],...] from a cam detection result dict."""
    if not cam_result:
        return []
    out = []
    for fb in cam_result.get("fire_bboxes", []) or []:
        bb = fb.get("bbox") if isinstance(fb, dict) else fb
        if bb and len(bb) == 4:
            out.append([int(v) for v in bb])
    return out


@app.route('/turret/config', methods=['GET', 'POST'])
def turret_config():
    """Get / set ESP32-CAM 2 control URL.
    POST body: {"esp2_url": "http://10.199.56.103"}
    """
    global ESP2_CONTROL_URL
    if not TURRET_AVAILABLE:
        return jsonify({"error": "turret module not available"}), 500
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        url = data.get("esp2_url", "").strip()
        ESP2_CONTROL_URL = url
        if turret:
            turret.esp2_url = url
        return jsonify({"ok": True, "esp2_url": ESP2_CONTROL_URL})
    return jsonify({"esp2_url": ESP2_CONTROL_URL})


@app.route('/turret/process', methods=['POST'])
def turret_process():
    """Run one turret control cycle.

    Uses latest cam1 + cam2 detection results from `last_detection_result`,
    computes stereo distance, picks/locks target, sends servo+pump command
    to ESP32-CAM 2.

    Returns: {"command": {...}, "esp_response": {...} or null}
    """
    if not TURRET_AVAILABLE or turret is None:
        return jsonify({"error": "turret module not available"}), 500

    with last_detection_lock:
        cam1 = last_detection_result.get("cam1", {})
        cam2 = last_detection_result.get("cam2", {})

    bboxes_left  = _bboxes_from_result(cam1)
    bboxes_right = _bboxes_from_result(cam2)

    # Stereo distance (None if can't pair)
    distance_m = None
    if bboxes_left and bboxes_right:
        try:
            d, _pair = stereo_distance(bboxes_left, bboxes_right)
            distance_m = d
        except Exception as e:
            print(f"[TURRET] stereo error: {e}")

    with turret_lock:
        cmd = turret.update(bboxes_left, bboxes_right, distance_m=distance_m)
        resp = turret.send(cmd) if turret.esp2_url else None

    return jsonify({"command": cmd, "esp_response": resp})


@app.route('/turret/state', methods=['GET'])
def turret_state():
    """Snapshot of controller state."""
    if not TURRET_AVAILABLE or turret is None:
        return jsonify({"error": "turret module not available"}), 500
    with turret_lock:
        return jsonify({
            "pan":      turret.current_pan,
            "tilt":     turret.current_tilt,
            "target":   list(map(int, turret.target)) if turret.target else None,
            "distance_m":  turret.last_distance,
            "centered_streak": turret.centered_streak,
            "last_burst_at":   turret.last_burst_at,
            "esp2_url":  turret.esp2_url,
        })


@app.route('/turret/home', methods=['POST'])
def turret_home():
    """Reset turret to home position, pump off."""
    if not TURRET_AVAILABLE or turret is None:
        return jsonify({"error": "turret module not available"}), 500
    with turret_lock:
        turret.home()
    return jsonify({"ok": True})


@app.route('/latest')
@app.route('/latest/<cam_id>')
def latest_image(cam_id="cam1"):
    """Tra ve anh moi nhat cua camera."""
    # Uu tien frame trong memory
    if cam_id in latest_frame_locks:
        with latest_frame_locks[cam_id]:
            frame = latest_frames.get(cam_id)
        if frame:
            return Response(frame, mimetype='image/jpeg')
    # Fallback: doc tu disk
    image_dir = config["paths"]["image_dir"]
    images = sorted(glob.glob(os.path.join(image_dir, "*.jpg")))
    if not images:
        return "No images", 404
    return send_file(images[-1], mimetype='image/jpeg')


@app.route('/stream')
@app.route('/stream/<cam_id>')
def mjpeg_stream(cam_id="cam1"):
    """MJPEG stream - hien thi realtime tren dashboard. Ho tro /stream/<cam_id>."""
    # Ensure event/lock exist for this cam_id
    if cam_id not in latest_frame_events:
        latest_frame_events[cam_id] = threading.Event()
        latest_frame_locks[cam_id] = threading.Lock()
        latest_frames[cam_id] = None

    def generate(cid):
        while True:
            latest_frame_events[cid].wait(timeout=2.0)
            latest_frame_events[cid].clear()
            with latest_frame_locks[cid]:
                frame = latest_frames[cid]
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate(cam_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/config', methods=['GET', 'POST'])
def config_endpoint():
    """Doc/ghi config."""
    global config
    if request.method == 'GET':
        return jsonify(config)

    try:
        new_config = request.get_json()
        if not new_config:
            return jsonify({"error": "Invalid JSON"}), 400

        from fire_utils import _deep_merge
        _deep_merge(config, new_config)

        with open("config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        return jsonify({"status": "ok", "config": config})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ============================================================
# HISTORY API
# ============================================================

detection_history = []  # Luu lich su phat hien
MAX_HISTORY = 200

def add_to_history(det_result, img=None, cam_id="cam1"):
    """Them su kien phat hien vao lich su."""
    if not det_result.get('has_fire') and not det_result.get('has_smoke'):
        return
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cam_id': cam_id,
        'fire': det_result.get('has_fire', False),
        'smoke': det_result.get('has_smoke', False),
        'fire_count': len(det_result.get('fire_bboxes', [])),
        'smoke_count': len(det_result.get('smoke_bboxes', [])),
        'fire_bboxes': det_result.get('fire_bboxes', []),
        'smoke_bboxes': det_result.get('smoke_bboxes', []),
    }
    if img is not None:
        try:
            h, w = img.shape[:2]
            scale = min(320 / w, 320 / h)
            small = cv2.resize(img, (int(w * scale), int(h * scale)))
            _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 60])
            entry['thumbnail'] = base64.b64encode(buf).decode('utf-8')
        except Exception:
            pass
    detection_history.insert(0, entry)
    if len(detection_history) > MAX_HISTORY:
        detection_history.pop()


@app.route('/history')
def history_endpoint():
    """Tra ve lich su phat hien."""
    limit = request.args.get('limit', 50, type=int)
    filter_type = request.args.get('type', 'all')
    results = detection_history[:limit]
    if filter_type == 'fire':
        results = [r for r in results if r['fire']][:limit]
    elif filter_type == 'smoke':
        results = [r for r in results if r['smoke']][:limit]
    return jsonify({'history': results, 'total': len(detection_history)})


# ============================================================
# STANDALONE WEBCAM MODE
# ============================================================

def run_standalone(source=0, show=True):
    """Chay detection voi webcam hoac video file."""
    if model is None:
        print("[ERROR] Model not loaded!")
        return

    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {source}")
        return

    print(f"[STANDALONE] Running on source: {source}")
    print(f"[STANDALONE] Press 'q' to quit")

    fps_time = time.time()
    fps_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result = detect_frame(frame, cam_id="webcam")

        fire_bboxes = result.get("fire_bboxes", [])
        smoke_bboxes = result.get("smoke_bboxes", [])
        fire_confirmed = result.get("fire", False)
        smoke_confirmed = result.get("smoke", False)

        fps_count += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps = fps_count / elapsed
            fps_count = 0
            fps_time = time.time()
        else:
            fps = fps_count / max(elapsed, 0.001)

        info = f"Mode: {result.get('mode', '?')} | FPS: {fps:.1f} | Brightness: {result.get('brightness', 0)}"

        annotated = draw_detections(
            frame.copy(), fire_bboxes, smoke_bboxes,
            fire_confirmed, smoke_confirmed, info
        )

        if show:
            cv2.imshow("Fire Detection", annotated)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    if show:
        cv2.destroyAllWindows()
    print("[STANDALONE] Done")


# ============================================================
# DASHBOARD HTML
# ============================================================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kiem soat Lua & Khoi</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#fff;color:#222;min-height:100vh}
.header{background:#fff;padding:14px 24px;border-bottom:1px solid #ddd;display:flex;
  align-items:center;justify-content:space-between}
.header h1{font-size:1.1rem;font-weight:600;color:#333}
.header .sub{color:#888;font-size:0.75rem}
.badge{background:#e8e8e8;color:#555;padding:3px 10px;border-radius:4px;font-size:0.72rem}
.container{max-width:1200px;margin:0 auto;padding:16px}
.tabs{display:flex;gap:0;border-bottom:1px solid #ddd;margin-bottom:16px}
.tab{padding:8px 20px;cursor:pointer;font-size:0.85rem;color:#666;border:none;background:none;
  border-bottom:2px solid transparent}
.tab:hover{color:#333}
.tab.active{color:#d44;border-bottom-color:#d44;font-weight:600}
.panel{display:none}.panel.active{display:block}
.upload-zone{border:2px dashed #ccc;border-radius:8px;padding:40px;text-align:center;
  cursor:pointer;margin-bottom:16px;transition:border-color .2s}
.upload-zone:hover,.upload-zone.dragover{border-color:#d44}
.upload-zone p{color:#888;font-size:0.82rem;margin-top:6px}
.upload-zone input{display:none}
.result-grid{display:grid;grid-template-columns:1fr 340px;gap:16px;margin-top:16px}
@media(max-width:860px){.result-grid{grid-template-columns:1fr}}
.img-box{background:#f5f5f5;border-radius:8px;padding:12px;text-align:center;position:relative;
  min-height:280px;display:flex;align-items:center;justify-content:center}
.img-box img{max-width:100%;max-height:550px;border-radius:4px}
.img-box .btns{position:absolute;top:8px;right:8px;display:flex;gap:4px}
.sbtn{background:#fff;color:#555;border:1px solid #ccc;padding:3px 8px;border-radius:4px;
  font-size:0.7rem;cursor:pointer}
.sbtn.active{background:#d44;color:#fff;border-color:#d44}
.sidebar{display:flex;flex-direction:column;gap:12px}
.card{background:#f9f9f9;border-radius:8px;padding:14px;border:1px solid #eee}
.card h4{color:#888;font-size:0.7rem;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.big{font-size:1.3rem;font-weight:700}
.c-ok{color:#2a2}.c-fire{color:#d33}.c-smoke{color:#c80}
.det-list{max-height:380px;overflow-y:auto}
.det-item{background:#fff;border-radius:6px;padding:10px;margin-bottom:6px;border-left:3px solid #ccc}
.det-item.fire{border-left-color:#d33}
.det-item.smoke{border-left-color:#c80}
.det-item .dh{display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px}
.det-item .dt{font-weight:600}.det-item.fire .dt{color:#d33}.det-item.smoke .dt{color:#c80}
.det-item .dc{color:#888;font-size:0.75rem}
.bar{height:3px;background:#eee;border-radius:2px;margin-top:4px}
.bar-f{height:100%;border-radius:2px}
.det-item.fire .bar-f{background:#d33}
.det-item.smoke .bar-f{background:#c80}
.dd{display:flex;gap:4px;margin-top:5px;font-size:0.68rem;color:#999}
.dd span{background:#f0f0f0;padding:1px 5px;border-radius:3px}
.vid-box{background:#f9f9f9;border-radius:8px;padding:16px;border:1px solid #eee;margin-top:16px}
.pbar{width:100%;height:6px;background:#eee;border-radius:3px;margin:10px 0}
.pfill{height:100%;background:#d44;border-radius:3px;transition:width .3s}
.ptxt{display:flex;justify-content:space-between;font-size:0.75rem;color:#888}
.esp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.esp-card{background:#f9f9f9;border-radius:8px;padding:16px;border:1px solid #eee}
.esp-card h3{color:#888;font-size:0.7rem;text-transform:uppercase;margin-bottom:6px}
.esp-card .value{font-size:1.6rem;font-weight:700}
.esp-img{max-width:100%;max-height:320px;border-radius:6px;margin-top:8px}
.loading{display:none;text-align:center;padding:24px}
.loading.show{display:block}
.spinner{display:inline-block;width:28px;height:28px;border:2px solid #eee;
  border-top-color:#d44;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.btn{background:#d44;color:#fff;border:none;padding:8px 18px;border-radius:6px;
  cursor:pointer;font-size:0.82rem;font-weight:500}
.btn:hover{background:#b33}
footer{text-align:center;padding:16px;color:#bbb;font-size:0.7rem;margin-top:30px}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Kiem soat Lua & Khoi</h1>
    <div class="sub">He thong phat hien lua va khoi</div>
  </div>
  <div class="badge" id="mode-badge">SENSITIVE</div>
</div>
<div class="container">
  <div class="tabs">
    <button class="tab active" onclick="switchTab('image')">Test Anh</button>
    <button class="tab" onclick="switchTab('video')">Test Video</button>
    <button class="tab" onclick="switchTab('esp32')">ESP32-CAM</button>
  </div>

  <div class="panel active" id="panel-image">
    <div class="upload-zone" id="img-drop" onclick="document.getElementById('img-input').click()">
      <b>Chon anh hoac keo tha vao day</b>
      <p>JPG, PNG, BMP, WEBP</p>
      <input type="file" id="img-input" accept="image/*">
    </div>
    <div class="loading" id="img-loading"><div class="spinner"></div><p style="margin-top:8px;color:#888;font-size:.82rem">Dang xu ly...</p></div>
    <div id="img-result" style="display:none">
      <div class="result-grid">
        <div class="img-box">
          <div class="btns">
            <button class="sbtn active" onclick="showOrig(false)">Ket qua</button>
            <button class="sbtn" onclick="showOrig(true)">Goc</button>
          </div>
          <img id="res-img" src="">
        </div>
        <div class="sidebar">
          <div class="card"><h4>Ket qua</h4><div class="big" id="res-status">---</div>
            <p style="color:#888;font-size:.75rem;margin-top:3px" id="res-info"></p></div>
          <div class="card" id="target-card" style="display:none"><h4>Toa do dap lua</h4>
            <div id="target-info" style="font-family:monospace;font-size:.82rem;line-height:1.8"></div></div>
          <div class="card"><h4>Chi tiet</h4><div class="det-list" id="det-list">
            <p style="color:#aaa;font-size:.8rem">Chua co</p></div></div>
        </div>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-video">
    <div class="upload-zone" id="vid-drop" onclick="document.getElementById('vid-input').click()">
      <b>Chon video hoac keo tha vao day</b>
      <p>MP4, AVI, MOV (toi da 200MB)</p>
      <input type="file" id="vid-input" accept="video/*">
    </div>
    <div id="vid-progress" style="display:none">
      <div class="vid-box">
        <div style="display:flex;justify-content:space-between">
          <span id="vid-filename" style="font-weight:500"></span>
          <span id="vid-percent" style="color:#d44;font-weight:600">0%</span>
        </div>
        <div class="pbar"><div class="pfill" id="vid-bar" style="width:0%"></div></div>
        <div class="ptxt"><span id="vid-frames">0/0</span><span id="vid-detections">Fire: 0 | Smoke: 0</span></div>
      </div>
      <div style="margin-top:12px;text-align:center">
        <img id="vid-preview" src="" style="max-width:100%;max-height:360px;border-radius:6px;display:none">
      </div>
      <div id="vid-done" style="display:none;text-align:center;margin-top:12px">
        <button class="btn" onclick="downloadVideo()">Tai video ket qua</button>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-esp32">
    <div class="esp-grid">
      <div class="esp-card"><h3>Trang thai</h3><div class="value" id="esp-status" style="color:#2a2">An toan</div></div>
      <div class="esp-card"><h3>Mode</h3><div class="value" id="esp-mode" style="font-size:1.1rem">---</div></div>
      <div class="esp-card"><h3>Do sang</h3><div class="value" id="esp-bright" style="font-size:1.1rem">---</div></div>
      <div class="esp-card"><h3>Fire frames</h3><div class="value" id="esp-fire" style="font-size:1.1rem;color:#d33">0</div></div>
    </div>
    <div class="esp-card" style="margin-top:12px;display:none" id="esp-target-card">
      <h3>Toa do dap lua</h3>
      <div id="esp-target" style="font-family:monospace;font-size:.85rem;line-height:1.8"></div>
    </div>
    <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="esp-card" style="text-align:center"><h3>Live Stream + Tam ngam</h3>
        <div id="esp-canvas-wrap" style="position:relative;display:inline-block;cursor:crosshair">
          <img id="esp-img" class="esp-img" src="/stream" onerror="this.src='/latest'" style="display:block;max-width:100%;max-height:400px">
          <canvas id="esp-overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none"></canvas>
          <div id="crosshair" style="position:absolute;left:50%;top:50%;width:30px;height:30px;border:2px solid #0f0;border-radius:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:10;box-shadow:0 0 8px #0f0">
            <div style="position:absolute;top:50%;left:0;right:0;height:1px;background:#0f0"></div>
            <div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:#0f0"></div>
          </div>
        </div>
        <div style="margin-top:6px;font-size:.8rem;color:#888">
          <span id="crosshair-pos">Tam: (---, ---)</span> |
          <span id="crosshair-status" style="color:#888">Keo chuot de di chuyen tam ngam</span>
        </div>
        <div id="capture-alert" style="display:none;margin-top:6px;padding:8px;background:#1a4d1a;border:1px solid #0f0;border-radius:6px;color:#0f0;font-weight:bold;text-align:center">
          DA CHUP! Tam trung muc tieu</div>
      </div>
      <div class="esp-card"><h3>Log</h3>
        <div id="esp-log" style="max-height:280px;overflow-y:auto;font-family:monospace;font-size:.75rem;line-height:1.7;color:#888">
          Cho du lieu tu ESP32-CAM...</div>
        <div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <button class="btn" onclick="manualCapture()" style="font-size:.8rem;padding:4px 12px;background:#1a6b1a">Chup anh</button>
          <button class="btn" onclick="downloadCaptures()" style="font-size:.8rem;padding:4px 12px">Tai anh da chup</button>
          <span id="capture-count" style="font-size:.8rem;color:#888">0 anh</span>
        </div>
      </div>
    </div>
  </div>
</div>
<footer>He thong Kiem soat Lua & Khoi</footer>

<script>
function switchTab(n){
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',['image','video','esp32'][i]===n));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('panel-'+n).classList.add('active');
}
const imgDrop=document.getElementById('img-drop'),imgInput=document.getElementById('img-input');
['dragenter','dragover'].forEach(e=>imgDrop.addEventListener(e,ev=>{ev.preventDefault();imgDrop.classList.add('dragover')}));
['dragleave','drop'].forEach(e=>imgDrop.addEventListener(e,ev=>{ev.preventDefault();imgDrop.classList.remove('dragover')}));
imgDrop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length)uploadImg(ev.dataTransfer.files[0])});
imgInput.addEventListener('change',()=>{if(imgInput.files.length)uploadImg(imgInput.files[0])});
let rB='',oB='';
async function uploadImg(f){
  document.getElementById('img-loading').classList.add('show');
  document.getElementById('img-result').style.display='none';
  const fd=new FormData();fd.append('file',f);
  try{
    const r=await fetch('/detect_upload',{method:'POST',body:fd});
    const d=await r.json();
    if(d.error){alert(d.error);return}
    rB=d.image;oB=d.original;
    document.getElementById('res-img').src='data:image/jpeg;base64,'+rB;
    const s=document.getElementById('res-status');
    if(d.fire){s.textContent='PHAT HIEN LUA';s.className='big c-fire'}
    else if(d.smoke){s.textContent='PHAT HIEN KHOI';s.className='big c-smoke'}
    else{s.textContent='AN TOAN';s.className='big c-ok'}
    document.getElementById('res-info').textContent=`${d.size} | Fire: ${d.fire_count} | Smoke: ${d.smoke_count}`;
    // Hien thi toa do dap lua
    const tc=document.getElementById('target-card');
    const ti=document.getElementById('target-info');
    if(d.detections&&d.detections.length){
      let thtml='';
      d.detections.forEach((x,i)=>{
        const b=x.bbox;
        const cx=Math.round((b[0]+b[2])/2);
        const cy=Math.round((b[1]+b[3])/2);
        const w=b[2]-b[0];
        const h=b[3]-b[1];
        const color=x.type==='fire'?'#d33':'#c80';
        const label=x.type==='fire'?'LUA':'KHOI';
        thtml+=`<div style="margin-bottom:8px;padding:6px 8px;background:#fff;border-radius:4px;border-left:3px solid ${color}">`;
        thtml+=`<span style="color:${color};font-weight:700">${label} #${i+1}</span> <span style="color:#888">(${(x.conf*100).toFixed(0)}%)</span><br>`;
        thtml+=`<span style="color:#555">Tam: <b>(${cx}, ${cy})</b></span><br>`;
        thtml+=`<span style="color:#888">BBox: (${b[0]},${b[1]}) - (${b[2]},${b[3]})</span><br>`;
        thtml+=`<span style="color:#888">Kich thuoc: ${w}x${h}px</span>`;
        thtml+=`</div>`;
      });
      tc.style.display='block';
      ti.innerHTML=thtml;
    }else{tc.style.display='none'}
    const l=document.getElementById('det-list');
    if(!d.detections||!d.detections.length){l.innerHTML='<p style="color:#2a2;font-size:.82rem">Khong phat hien gi</p>'}
    else{l.innerHTML=d.detections.map(x=>{
      const c=x.type,p=(x.conf*100).toFixed(1),v=(x.verify*100).toFixed(1);
      const b=x.bbox;const cx=Math.round((b[0]+b[2])/2);const cy=Math.round((b[1]+b[3])/2);
      let dd='';if(x.color!==undefined)dd=`<div class="dd"><span>Color ${x.color}</span><span>Texture ${x.texture}</span><span>Edge ${x.edge}</span></div>`;
      let coords=`<div class="dd"><span>Tam: (${cx},${cy})</span><span>BBox: ${b[0]},${b[1]}-${b[2]},${b[3]}</span></div>`;
      return`<div class="det-item ${c}"><div class="dh"><span class="dt">${c==='fire'?'Lua':'Khoi'}</span><span class="dc">${p}% | verify ${v}%</span></div><div class="bar"><div class="bar-f" style="width:${p}%"></div></div>${coords}${dd}</div>`
    }).join('')}
    document.getElementById('img-result').style.display='block';
  }catch(e){alert(e.message)}
  finally{document.getElementById('img-loading').classList.remove('show')}
}
function showOrig(o){
  document.getElementById('res-img').src='data:image/jpeg;base64,'+(o?oB:rB);
  document.querySelectorAll('.sbtn').forEach((b,i)=>b.classList.toggle('active',o?i===1:i===0));
}
const vidDrop=document.getElementById('vid-drop'),vidInput=document.getElementById('vid-input');
let jobId=null;
['dragenter','dragover'].forEach(e=>vidDrop.addEventListener(e,ev=>{ev.preventDefault();vidDrop.classList.add('dragover')}));
['dragleave','drop'].forEach(e=>vidDrop.addEventListener(e,ev=>{ev.preventDefault();vidDrop.classList.remove('dragover')}));
vidDrop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length)uploadVid(ev.dataTransfer.files[0])});
vidInput.addEventListener('change',()=>{if(vidInput.files.length)uploadVid(vidInput.files[0])});
async function uploadVid(f){
  vidDrop.style.display='none';document.getElementById('vid-progress').style.display='block';
  document.getElementById('vid-done').style.display='none';
  document.getElementById('vid-filename').textContent=f.name;
  const fd=new FormData();fd.append('file',f);
  try{const r=await fetch('/detect_video',{method:'POST',body:fd});const d=await r.json();
    if(d.error){alert(d.error);return}jobId=d.job_id;pollVid()}catch(e){alert(e.message)}
}
async function pollVid(){
  if(!jobId)return;
  try{const r=await fetch('/video_status/'+jobId);const d=await r.json();
    document.getElementById('vid-percent').textContent=d.progress+'%';
    document.getElementById('vid-bar').style.width=d.progress+'%';
    document.getElementById('vid-frames').textContent=d.current_frame+'/'+d.total_frames;
    document.getElementById('vid-detections').textContent='Fire: '+d.fire_frames+' | Smoke: '+d.smoke_frames;
    if(d.preview){const p=document.getElementById('vid-preview');p.src='data:image/jpeg;base64,'+d.preview;p.style.display='block'}
    if(d.status==='done'){document.getElementById('vid-done').style.display='block';
      document.getElementById('vid-percent').textContent='Xong!';return}
    if(d.status==='error'){alert(d.error);return}
  }catch(e){}
  setTimeout(pollVid,1500);
}
function downloadVideo(){if(jobId)window.open('/video_result/'+jobId)}
// === CROSSHAIR (Tam ngam gia lap) ===
let crossX=50, crossY=50; // % position
let isDragging=false;
let captureList=[];
const wrap=document.getElementById('esp-canvas-wrap');
const ch=document.getElementById('crosshair');
const espImg=document.getElementById('esp-img');

function updateCrosshair(){
  ch.style.left=crossX+'%';
  ch.style.top=crossY+'%';
  // Tinh toa do pixel thuc (dua tren kich thuoc anh goc 640x480)
  const px=Math.round(crossX/100*640);
  const py=Math.round(crossY/100*480);
  document.getElementById('crosshair-pos').textContent=`Tam: (${px}, ${py})`;
}
updateCrosshair();

wrap.addEventListener('mousedown',e=>{isDragging=true;moveCross(e);e.preventDefault()});
document.addEventListener('mousemove',e=>{if(isDragging)moveCross(e)});
document.addEventListener('mouseup',()=>{isDragging=false});
wrap.addEventListener('touchstart',e=>{isDragging=true;moveCross(e.touches[0]);e.preventDefault()});
document.addEventListener('touchmove',e=>{if(isDragging)moveCross(e.touches[0])});
document.addEventListener('touchend',()=>{isDragging=false});

function moveCross(e){
  const rect=wrap.getBoundingClientRect();
  crossX=Math.max(0,Math.min(100,(e.clientX-rect.left)/rect.width*100));
  crossY=Math.max(0,Math.min(100,(e.clientY-rect.top)/rect.height*100));
  updateCrosshair();
}

// Kiem tra tam ngam co nam trong fire bbox khong
function checkCrosshairHit(fireBboxes){
  if(!fireBboxes||!fireBboxes.length)return false;
  const px=crossX/100*640, py=crossY/100*480;
  for(const f of fireBboxes){
    const b=f.bbox;
    if(px>=b[0]&&px<=b[2]&&py>=b[1]&&py<=b[3])return true;
  }
  return false;
}

// Auto capture khi tam trung fire
let lastCapture=0;
function autoCapture(det,manual=false){
  const now=Date.now();
  if(!manual&&now-lastCapture<3000)return;
  lastCapture=now;
  // Luu anh tu canvas
  const img=document.getElementById('esp-img');
  const canvas=document.createElement('canvas');
  canvas.width=img.naturalWidth||640;
  canvas.height=img.naturalHeight||480;
  const ctx=canvas.getContext('2d');
  ctx.drawImage(img,0,0,canvas.width,canvas.height);
  // Ve crosshair len anh
  const cx=crossX/100*canvas.width, cy=crossY/100*canvas.height;
  ctx.strokeStyle='#00ff00';ctx.lineWidth=2;
  ctx.beginPath();ctx.arc(cx,cy,15,0,Math.PI*2);ctx.stroke();
  ctx.beginPath();ctx.moveTo(cx-20,cy);ctx.lineTo(cx+20,cy);ctx.stroke();
  ctx.beginPath();ctx.moveTo(cx,cy-20);ctx.lineTo(cx,cy+20);ctx.stroke();
  // Ve fire bbox
  if(det.fire_bboxes){
    ctx.strokeStyle='#ff0000';ctx.lineWidth=2;
    det.fire_bboxes.forEach(f=>{
      const b=f.bbox;
      ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);
    });
  }
  // Text
  ctx.fillStyle='#00ff00';ctx.font='bold 16px monospace';
  ctx.fillText('TARGET LOCKED - '+det.timestamp,10,25);
  const dataUrl=canvas.toDataURL('image/jpeg',0.9);
  captureList.push({time:det.timestamp,img:dataUrl});
  document.getElementById('capture-count').textContent=captureList.length+' anh';
  // Hieu ung chup
  const alert=document.getElementById('capture-alert');
  alert.style.display='block';
  setTimeout(()=>{alert.style.display='none'},2000);
  // Gui ve server luu
  fetch('/save_capture',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({image:dataUrl,timestamp:det.timestamp})}).catch(()=>{});
}

function manualCapture(){
  const det={timestamp:new Date().toISOString().replace('T',' ').substring(0,23),
    fire_bboxes:window._lastFireBboxes||[]};
  autoCapture(det,true);
}

function downloadCaptures(){
  captureList.forEach((c,i)=>{
    const a=document.createElement('a');
    a.href=c.img;a.download=`capture_${i+1}_${c.time.replace(/[: ]/g,'_')}.jpg`;
    a.click();
  });
}

let espLog=[];
async function updateESP(){
  try{const r=await fetch('/status');const d=await r.json();
    document.getElementById('esp-mode').textContent=d.mode||'---';
    document.getElementById('mode-badge').textContent=(d.mode||'').toUpperCase();
    const det=d.last_detection||{};const se=document.getElementById('esp-status');
    if(det.fire){se.textContent='LUA!';se.style.color='#d33'}
    else if(det.smoke){se.textContent='KHOI';se.style.color='#c80'}
    else{se.textContent='An toan';se.style.color='#2a2'}
    document.getElementById('esp-bright').textContent=(det.brightness||0).toFixed(0);
    document.getElementById('esp-fire').textContent=det.fire_count||0;
    // Hien thi toa do dap lua realtime
    const etc=document.getElementById('esp-target-card');
    const ett=document.getElementById('esp-target');
    const fb=det.fire_bboxes||[];
    const sb=det.smoke_bboxes||[];
    if(fb.length||sb.length){
      let h='';
      fb.forEach((f,i)=>{const b=f.bbox;const cx=Math.round((b[0]+b[2])/2);const cy=Math.round((b[1]+b[3])/2);
        h+=`<div style="color:#d33"><b>LUA #${i+1}</b> | Tam: <b>(${cx}, ${cy})</b> | BBox: (${b[0]},${b[1]})-(${b[2]},${b[3]}) | ${(f.conf*100).toFixed(0)}%</div>`});
      sb.forEach((s,i)=>{const b=s.bbox;const cx=Math.round((b[0]+b[2])/2);const cy=Math.round((b[1]+b[3])/2);
        h+=`<div style="color:#c80"><b>KHOI #${i+1}</b> | Tam: <b>(${cx}, ${cy})</b> | BBox: (${b[0]},${b[1]})-(${b[2]},${b[3]}) | ${(s.conf*100).toFixed(0)}%</div>`});
      etc.style.display='block';ett.innerHTML=h;
    }else{etc.style.display='none'}
    // Luu fire bboxes cho manual capture
    window._lastFireBboxes=fb;
    // Crosshair hit check
    const cs=document.getElementById('crosshair-status');
    const chEl=document.getElementById('crosshair');
    if(fb.length&&checkCrosshairHit(fb)){
      cs.textContent='TRUNG MUC TIEU!';cs.style.color='#0f0';
      chEl.style.borderColor='#f00';chEl.style.boxShadow='0 0 15px #f00';
      autoCapture(det);
    }else if(fb.length){
      cs.textContent='Chua trung - di chuyen tam ngam vao vung lua';cs.style.color='#fc0';
      chEl.style.borderColor='#0f0';chEl.style.boxShadow='0 0 8px #0f0';
    }else{
      cs.textContent='Keo chuot de di chuyen tam ngam';cs.style.color='#888';
      chEl.style.borderColor='#0f0';chEl.style.boxShadow='0 0 8px #0f0';
    }
    if(det.timestamp){const c=det.fire?'#d33':(det.smoke?'#c80':'#2a2');
      const t=det.fire?'FIRE':(det.smoke?'SMOKE':'OK');
      let coords='';
      if(fb.length){const b=fb[0].bbox;coords=` | (${Math.round((b[0]+b[2])/2)},${Math.round((b[1]+b[3])/2)})`}
      espLog.unshift(`<span style="color:${c}">[${det.timestamp}] ${t}${coords}</span>`);
      if(espLog.length>40)espLog.pop();
      document.getElementById('esp-log').innerHTML=espLog.join('<br>')}
  }catch(e){}
}
setInterval(updateESP,500);updateESP();
</script>
</body>
</html>"""


# ============================================================
# CAM2 TRIGGER POLLING
# ============================================================

cam2_thread = None
cam2_running = False

def cam2_poll_loop():
    """Poll cam2 (trigger mode) - goi GET /trigger de lay anh, roi detect."""
    global cam2_running, image_counter
    cam2_running = True
    print("[CAM2] Trigger polling started")

    consecutive_errors = 0
    MAX_ERRORS = 10

    while cam2_running:
        cam2_cfg = config.get("cam2_trigger", {})
        if not cam2_cfg.get("enabled", False):
            time.sleep(5)
            continue

        ip = cam2_cfg.get("ip", "192.168.137.100")
        port = cam2_cfg.get("port", 80)
        interval = cam2_cfg.get("interval", 2.0)
        url = f"http://{ip}:{port}/trigger"

        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200 and len(resp.content) > 100:
                nparr = np.frombuffer(resp.content, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    image_dir = config["paths"]["image_dir"]
                    with image_counter_lock:
                        image_counter += 1
                        counter = image_counter
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"cam2_{timestamp}_{counter:04d}.jpg"
                    filepath = os.path.join(image_dir, filename)

                    # Detect trong thread hien tai (cam2 da la background thread roi)
                    _process_upload_async(img.copy(), filename, filepath, "cam2")
                    consecutive_errors = 0
                else:
                    print("[CAM2] Invalid image from trigger")
                    consecutive_errors += 1
            else:
                consecutive_errors += 1
        except requests.exceptions.ConnectTimeout:
            if consecutive_errors == 0:
                print(f"[CAM2] Timeout connecting to {url}")
            consecutive_errors += 1
        except requests.exceptions.ConnectionError:
            if consecutive_errors == 0:
                print(f"[CAM2] Cannot reach {url}")
            consecutive_errors += 1
        except Exception as e:
            if consecutive_errors == 0:
                print(f"[CAM2] Error: {e}")
            consecutive_errors += 1

        if consecutive_errors == MAX_ERRORS:
            print(f"[CAM2] {MAX_ERRORS} errors in a row, will keep retrying silently...")

        time.sleep(interval)

    print("[CAM2] Trigger polling stopped")


def start_cam2_polling():
    """Khoi dong thread poll cam2."""
    global cam2_thread
    if cam2_thread and cam2_thread.is_alive():
        return
    cam2_cfg = config.get("cam2_trigger", {})
    if not cam2_cfg.get("enabled", False):
        print("[CAM2] Disabled in config")
        return
    cam2_thread = threading.Thread(target=cam2_poll_loop, daemon=True)
    cam2_thread.start()
    ip = cam2_cfg.get("ip", "192.168.137.100")
    print(f"[CAM2] Polling cam2 at {ip}:{cam2_cfg.get('port', 80)} every {cam2_cfg.get('interval', 2.0)}s")


# ============================================================
# TURRET BACKGROUND LOOP
# ============================================================
turret_running = False
turret_thread = None

def turret_control_loop():
    """Continuously process latest cam1+cam2 detections and command ESP2 turret."""
    global turret_running
    if not (TURRET_AVAILABLE and turret):
        return
    turret_running = True
    print("[TURRET] Control loop started")
    INTERVAL = 0.4  # 2.5 Hz update rate

    while turret_running:
        if not turret.esp2_url:
            time.sleep(2.0)
            continue
        try:
            with last_detection_lock:
                cam1 = last_detection_result.get("cam1", {})
                cam2 = last_detection_result.get("cam2", {})
            bb_l = _bboxes_from_result(cam1)
            bb_r = _bboxes_from_result(cam2)

            distance_m = None
            if bb_l and bb_r:
                try:
                    d, _ = stereo_distance(bb_l, bb_r)
                    distance_m = d
                except Exception:
                    pass

            with turret_lock:
                cmd = turret.update(bb_l, bb_r, distance_m=distance_m)
                turret.send(cmd)
        except Exception as e:
            print(f"[TURRET] loop error: {e}")
        time.sleep(INTERVAL)
    print("[TURRET] Control loop stopped")


def start_turret_loop():
    global turret_thread
    if not (TURRET_AVAILABLE and turret):
        print("[TURRET] Disabled (module unavailable)")
        return
    if turret_thread and turret_thread.is_alive():
        return
    turret_thread = threading.Thread(target=turret_control_loop, daemon=True)
    turret_thread.start()
    print(f"[TURRET] Started (esp2_url={turret.esp2_url or 'NOT SET'})")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Fire Detection Server')
    parser.add_argument('--source', '-s', default=None,
                        help='Webcam index or video file (standalone mode)')
    parser.add_argument('--show', action='store_true',
                        help='Show detection window (standalone mode)')
    parser.add_argument('--port', '-p', type=int, default=5000,
                        help='Server port (default: 5000)')
    parser.add_argument('--weights', '-w', default=None,
                        help='Override model weights path')
    parser.add_argument('--no-serial', action='store_true',
                        help='Disable Arduino serial')
    args = parser.parse_args()

    # Override config
    if args.weights:
        config["model"]["weights"] = args.weights
    if args.no_serial:
        config.setdefault("serial", {})["enabled"] = False

    # Init
    ensure_dirs()
    ensure_csv()
    init_model()
    init_serial()
    init_flicker()

    if args.source is not None:
        run_standalone(source=args.source, show=args.show)
    else:
        # Start cam2 trigger polling
        start_cam2_polling()
        # Start turret control loop (no-op if turret module unavailable / no ESP2 URL)
        start_turret_loop()

        print(f"\n{'='*50}")
        print(f"  He thong Kiem soat Lua & Khoi")
        print(f"  Dashboard: http://localhost:{args.port}")
        print(f"  Mode: {config.get('active_mode', 'sensitive')}")
        print(f"  Model: {'Loaded' if model else 'NOT LOADED'}")
        print(f"  Serial: {'Connected' if ser else 'Not available'}")
        cam2_cfg = config.get("cam2_trigger", {})
        if cam2_cfg.get("enabled"):
            print(f"  Cam2: {cam2_cfg.get('ip')}:{cam2_cfg.get('port')} (trigger mode)")
        else:
            print(f"  Cam2: Disabled")
        print(f"  Turret: {'ON · ' + turret.esp2_url if (turret and turret.esp2_url) else 'OFF (no ESP2 URL)'}")
        print(f"{'='*50}\n")
        app.run(host='0.0.0.0', port=args.port, threaded=True)


if __name__ == '__main__':
    main()
