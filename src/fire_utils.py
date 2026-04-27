#!/usr/bin/env python3
"""
fire_utils.py - Module phat hien lua va khoi nang cao
He thong Kiem soat Lua - Bai du thi

Pipeline phat hien da tieu chi (multi-criteria verification):

  FIRE (5 tieu chi):
    1. Color: multi-range HSV (do/cam/vang/trang nong)
    2. Core:  phat hien loi lua trang (flame core)
    3. Gradient: tam sang, vien toi (dac trung lua)
    4. Texture: variance cao (lua nhap nhay, khong deu)
    5. Edge: bien khong deu, fractal-like (khac den/vat the)

  SMOKE (4 tieu chi + rejection):
    1. Color: xam/trang, saturation thap
    2. Texture: energy thap (mo, mem, khac vat ran)
    3. Edge density: it canh sac (khac vat the)
    4. Rejection: loai da nguoi, tuong phang, bau troi

  TEMPORAL:
    - Flicker detection (do sang dao dong)
    - Frame voting (xac nhan N frame lien tiep)
    - Motion analysis (phat hien chuyen dong lua/khoi)
    - Score fusion (ket hop YOLO + color + flicker)
"""

import copy
import json
import os
import threading

import numpy as np
import cv2


# ============================================================
# CAU HINH MAC DINH
# ============================================================

DEFAULT_CONFIG = {
    "active_mode": "sensitive",
    "enable_smoke": True,

    "model": {
        "weights": "models/best.pt",
        "imgsz": 640,
        "device": None
    },

    "serial": {
        "port": "COM4",
        "baudrate": 9600,
        "enabled": True
    },

    "paths": {
        "image_dir": "received_images",
        "csv_path": "detections.csv"
    },

    "bbox": {
        "fire_min_area": 0.00005,
        "smoke_min_area": 0.001,
        "fire_max_area": 0.5,
        "smoke_max_area": 0.95,
        "max_area": 0.5,
        "max_aspect": 6.0,
        "min_aspect": 0.15
    },

    "fire_modes": {
        "safe": {
            "yolo_conf": 0.35,
            "verify_threshold": 0.40,
            "confirm_frames": 3,
            "flicker_required": False,
            "use_score_fusion": False,
            "score_threshold": 0.65,
            "score_weights": {"yolo": 0.4, "color": 0.4, "flicker": 0.2}
        },
        "sensitive": {
            "yolo_conf": 0.25,
            "verify_threshold": 0.28,
            "confirm_frames": 1,
            "flicker_required": False,
            "use_score_fusion": False,
            "score_threshold": 0.55,
            "score_weights": {"yolo": 0.35, "color": 0.45, "flicker": 0.2}
        },
        "ultra_sensitive": {
            "yolo_conf": 0.15,
            "verify_threshold": 0.18,
            "confirm_frames": 2,
            "flicker_required": True,
            "use_score_fusion": True,
            "score_threshold": 0.50,
            "score_weights": {"yolo": 0.3, "color": 0.4, "flicker": 0.3}
        }
    },

    "smoke_modes": {
        "safe": {
            "yolo_conf": 0.35,
            "verify_threshold": 0.45,
            "confirm_frames": 3
        },
        "sensitive": {
            "yolo_conf": 0.30,
            "verify_threshold": 0.35,
            "confirm_frames": 2
        },
        "ultra_sensitive": {
            "yolo_conf": 0.15,
            "verify_threshold": 0.25,
            "confirm_frames": 3
        }
    },

    "flicker": {
        "history_size": 5,
        "min_std": 8.0,
        "normalize_factor": 20.0
    }
}


# ============================================================
# LOAD CONFIG
# ============================================================

def load_config(config_path=None):
    """Load va merge config tu file JSON."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            _deep_merge(config, file_config)
            print(f"[CONFIG] Loaded: {config_path}")
        except Exception as e:
            print(f"[CONFIG] Warning: {e}, using defaults")
    return config


def _deep_merge(base, override):
    """Deep merge override dict vao base dict."""
    for key, value in override.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def get_mode_config(config, mode=None):
    """Lay fire mode config cho mode hien tai."""
    mode = mode or config.get("active_mode", "sensitive")
    fire_modes = config.get("fire_modes", DEFAULT_CONFIG["fire_modes"])
    if mode not in fire_modes:
        mode = "sensitive"
    return fire_modes[mode], mode


# ============================================================
# LOC BOUNDING BOX
# ============================================================

def is_valid_bbox(bbox, img_shape, is_fire, bbox_config=None):
    """Kiem tra bounding box co hop le khong."""
    if bbox_config is None:
        bbox_config = DEFAULT_CONFIG["bbox"]

    x1, y1, x2, y2 = bbox
    img_h, img_w = img_shape[:2]

    bbox_w = max(0, x2 - x1)
    bbox_h = max(0, y2 - y1)
    if bbox_w == 0 or bbox_h == 0:
        return False

    area_ratio = (bbox_w * bbox_h) / (img_w * img_h)

    if is_fire:
        min_area = bbox_config.get("fire_min_area", 0.00005)
        max_area = bbox_config.get("fire_max_area",
                                   bbox_config.get("max_area", 0.5))
    else:
        min_area = bbox_config.get("smoke_min_area", 0.001)
        max_area = bbox_config.get("smoke_max_area",
                                   bbox_config.get("max_area", 0.85))

    if area_ratio < min_area or area_ratio > max_area:
        return False

    aspect = bbox_w / bbox_h
    if aspect > bbox_config.get("max_aspect", 6.0):
        return False
    if aspect < bbox_config.get("min_aspect", 0.15):
        return False

    return True


# ============================================================
# DO DO SANG MOI TRUONG
# ============================================================

def measure_brightness(img_bgr):
    """Do do sang trung binh cua anh (bo vung troi)."""
    if img_bgr is None or img_bgr.size == 0:
        return 128.0
    h = img_bgr.shape[0]
    region = img_bgr[h // 3:, :]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return float(np.clip(np.mean(gray), 0.0, 255.0))


# ############################################################
#
#   FIRE VERIFICATION - 5 tieu chi
#
# ############################################################

def _fire_color_score(roi_hsv, env_brightness):
    """Diem mau lua da dai (multi-range HSV).

    Phan tich 4 dai mau cua lua:
      - Do dam (H: 0-10) - than lua
      - Cam (H: 10-25) - than lua pho bien nhat
      - Vang (H: 25-35) - dinh lua
      - Trang nong (S thap, V cao) - loi lua

    Moi dai co trong so khac nhau, ket hop thanh diem chung.

    Returns:
        (score: float 0-1, details: dict)
    """
    total = roi_hsv.shape[0] * roi_hsv.shape[1]
    if total == 0:
        return 0.0, {}

    # 4 dai mau lua
    mask_red = cv2.inRange(roi_hsv,
                           np.array([0, 80, 150]), np.array([10, 255, 255]))
    mask_orange = cv2.inRange(roi_hsv,
                              np.array([10, 70, 140]), np.array([25, 255, 255]))
    mask_yellow = cv2.inRange(roi_hsv,
                              np.array([25, 50, 150]), np.array([35, 255, 255]))
    mask_core = cv2.inRange(roi_hsv,
                            np.array([0, 0, 220]), np.array([180, 50, 255]))

    red_r = np.sum(mask_red > 0) / total
    orange_r = np.sum(mask_orange > 0) / total
    yellow_r = np.sum(mask_yellow > 0) / total
    core_r = np.sum(mask_core > 0) / total

    # Ket hop co trong so (core > red > orange > yellow)
    raw = core_r * 3.0 + red_r * 2.5 + orange_r * 2.0 + yellow_r * 1.0

    # Adaptive theo do sang moi truong
    if env_brightness < 80:
        raw *= 1.3          # Toi: tang do nhay
    elif env_brightness < 120:
        raw *= 1.1
    elif env_brightness > 200:
        raw *= 0.75         # Qua sang: giam de tranh false positive

    score = min(raw / 0.6, 1.0)

    details = {'red': red_r, 'orange': orange_r,
               'yellow': yellow_r, 'core': core_r}
    return score, details


def _fire_core_score(roi_hsv):
    """Phat hien loi lua trang (flame core).

    Loi lua la phan nong nhat, co dac diem:
      - Value rat cao (> 230)
      - Saturation rat thap (< 40) -> trang sang

    Day la dau hieu manh nhat phan biet lua that voi
    den, man hinh, phan quang.

    Returns:
        (has_core: bool, ratio: float)
    """
    v = roi_hsv[:, :, 2]
    s = roi_hsv[:, :, 1]
    core_mask = (v > 230) & (s < 40)
    ratio = float(np.mean(core_mask))
    return ratio > 0.002, ratio


def _fire_gradient_score(roi_gray):
    """Diem gradient khong gian (center-bright, edge-dark).

    Lua that co dac tinh:
      - Phan tam/duoi sang nhat (loi lua)
      - Vien/ria toi hon (khoi + moi truong)
    Den/man hinh thi sang deu -> khong co gradient nay.

    Returns:
        float: 0-1
    """
    h, w = roi_gray.shape
    if h < 8 or w < 8:
        return 0.0

    # Vung tam (50% giua)
    ch, cw = h // 4, w // 4
    center = roi_gray[ch:h - ch, cw:w - cw]
    center_mean = float(np.mean(center))

    # Vung vien (4 canh)
    top = float(np.mean(roi_gray[:ch, :]))
    bottom = float(np.mean(roi_gray[h - ch:, :]))
    left = float(np.mean(roi_gray[:, :cw]))
    right = float(np.mean(roi_gray[:, w - cw:]))
    edge_mean = (top + bottom + left + right) / 4.0

    diff = center_mean - edge_mean
    if diff > 15:
        return min(diff / 60.0, 1.0)
    return 0.0


def _fire_texture_score(roi_gray):
    """Diem texture lua (variance cao = nhap nhay, khong deu).

    Lua co texture khong deu do:
      - Nhap nhay (flame flicker)
      - Bien doi mau do/cam/vang lien tuc
      - Khac han den (deu), tuong (phang), man hinh (co cau truc)

    Dung Laplacian variance de do.

    Returns:
        float: 0-1
    """
    if roi_gray.size < 64:
        return 0.0

    lap = cv2.Laplacian(roi_gray, cv2.CV_64F)
    lap_var = float(np.var(lap))

    # Lua co Laplacian variance trung binh-cao
    # < 30: qua phang (den, tuong) -> 0
    # 30-100: bat dau giong lua
    # 100-3000: vung lua -> cao
    # > 5000: qua sac net (text, edge) -> giam
    if lap_var < 30:
        return 0.0
    elif lap_var < 100:
        return (lap_var - 30) / 140.0
    elif lap_var < 3000:
        return min(0.5 + (lap_var - 100) / 5800.0, 1.0)
    else:
        return max(0.5, 1.0 - (lap_var - 3000) / 10000.0)


def _fire_edge_score(roi_gray):
    """Diem bien khong deu (edge irregularity).

    Lua co vien rat khong deu (fractal-like), khac voi:
      - Vat the: vien thang, deu dan
      - Den: vien tron/vuong deu
      - Phan quang: khong co vien ro

    Dung Canny + contour circularity de do.

    Returns:
        float: 0-1
    """
    if roi_gray.size < 64:
        return 0.0

    # Canny edge detection
    edges = cv2.Canny(roi_gray, 50, 150)
    edge_ratio = float(np.mean(edges > 0))

    if edge_ratio < 0.01:
        return 0.0
    if edge_ratio > 0.5:
        return 0.2  # Qua nhieu edge -> co the la text/pattern

    # Tim contours
    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) < 2:
        return 0.1

    # Do khong deu: dung circularity cua contour lon nhat
    areas = [cv2.contourArea(c) for c in contours]
    if max(areas) < 10:
        return 0.1

    top_idx = np.argsort(areas)[-3:]  # 3 contour lon nhat
    irregularity_scores = []
    for idx in top_idx:
        c = contours[idx]
        area = areas[idx]
        if area < 5:
            continue
        perim = cv2.arcLength(c, True)
        if perim < 1:
            continue
        circularity = 4 * np.pi * area / (perim * perim)
        # Lua: circularity thap (0.1-0.4) -> khong tron, khong deu
        # Vat the: circularity cao (0.6-1.0) -> tron/vuong deu
        irregularity = 1.0 - circularity
        irregularity_scores.append(irregularity)

    if not irregularity_scores:
        return 0.1

    avg_irreg = float(np.mean(irregularity_scores))

    # So luong contours cung la dau hieu (lua tao nhieu manh nho)
    count_bonus = min(len(contours) / 20.0, 0.3)

    return min(avg_irreg * 0.7 + count_bonus, 1.0)


def verify_fire_roi(roi_bgr, env_brightness=128.0, threshold=0.28):
    """Xac minh ROI co chua lua hay khong (multi-criteria).

    Ket hop 5 tieu chi voi trong so:
      Color:    35% - mau lua (do/cam/vang/trang)
      Core:     20% - loi lua trang (flame core)
      Gradient: 15% - tam sang, vien toi
      Texture:  15% - variance cao
      Edge:     15% - bien khong deu

    Override: neu co flame core ro rang (> 1%) VA color tot (> 0.4)
    -> xac nhan ngay (lua ro rang, khong can doi du diem).

    Args:
        roi_bgr: numpy array BGR
        env_brightness: do sang moi truong
        threshold: nguong diem tong hop (tu mode config)

    Returns:
        (is_fire: bool, score: float 0-1, details: dict)
    """
    if roi_bgr is None or roi_bgr.size == 0:
        return False, 0.0, {}

    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

    # 5 tieu chi
    color_s, color_detail = _fire_color_score(hsv, env_brightness)
    has_core, core_ratio = _fire_core_score(hsv)
    gradient_s = _fire_gradient_score(gray)
    texture_s = _fire_texture_score(gray)
    edge_s = _fire_edge_score(gray)

    # Core score -> chuyen thanh 0-1
    core_s = min(core_ratio / 0.02, 1.0)

    # Diem tong hop co trong so
    final = (
        color_s * 0.35 +
        core_s * 0.20 +
        gradient_s * 0.15 +
        texture_s * 0.15 +
        edge_s * 0.15
    )

    # Adaptive threshold theo do sang
    if env_brightness < 80:
        adj_threshold = threshold * 0.8     # Toi: ha nguong
    elif env_brightness > 200:
        adj_threshold = threshold * 1.25    # Sang: tang nguong
    else:
        adj_threshold = threshold

    is_fire = final > adj_threshold

    # Override: flame core ro rang + mau tot = chac chan lua
    if has_core and color_s > 0.4:
        is_fire = True

    details = {
        'color': round(color_s, 3),
        'core': round(core_s, 3),
        'gradient': round(gradient_s, 3),
        'texture': round(texture_s, 3),
        'edge': round(edge_s, 3),
        'final': round(final, 3),
        'threshold': round(adj_threshold, 3),
        'color_detail': color_detail
    }

    return is_fire, final, details


# ############################################################
#
#   SMOKE VERIFICATION - 4 tieu chi + rejection
#
# ############################################################

def _smoke_rejection(roi_hsv, roi_gray):
    """Loc bo cac vat the bi nham la khoi.

    Loai bo:
      - Da nguoi (skin tone)
      - Nen phang (tuong, san, giay) -> gray_std qua thap
      - Bau troi xanh (blue sky)
      - Vung toi den (bong toi, khong phai khoi)

    Returns:
        (is_rejected: bool, reason: str)
    """
    total = roi_hsv.shape[0] * roi_hsv.shape[1]
    if total == 0:
        return True, "empty"

    # 1. Loai bo da nguoi (H: 0-25, S: 40-180, V: 80+)
    #    Tang S min tu 20->40 de tranh nham khoi trang (S thap) thanh da
    skin = cv2.inRange(roi_hsv,
                       np.array([0, 40, 80]), np.array([25, 180, 255]))
    if np.sum(skin > 0) / total > 0.25:
        return True, "skin"

    # 2. Loai bo nen phang (variance qua thap)
    gray_std = float(np.std(roi_gray))
    if gray_std < 12:
        return True, "flat_surface"

    # 3. Loai bo bau troi xanh (H: 90-130, S: 50+, V: 120+)
    #    Chi reject khi phan lon ROI la troi xanh thuc su (sang + bao hoa)
    #    Khoi den/xam co the co nen troi nhung khong phai la troi
    sky = cv2.inRange(roi_hsv,
                      np.array([90, 50, 120]), np.array([130, 255, 255]))
    sky_ratio = np.sum(sky > 0) / total
    # Chi reject khi > 50% la troi xanh VA vung toi/xam it (khong phai khoi)
    gray_dark = cv2.inRange(roi_hsv,
                            np.array([0, 0, 20]), np.array([180, 60, 160]))
    gray_dark_ratio = np.sum(gray_dark > 0) / total
    if sky_ratio > 0.5 and gray_dark_ratio < 0.2:
        return True, "blue_sky"

    # 4. Loai bo bui cong truong / bui dat (H: 10-35, S: 25-130)
    #    Bui co sac am (nau/vang dat), khac khoi xam (S rat thap)
    dust_warm = cv2.inRange(roi_hsv,
                            np.array([10, 25, 80]), np.array([35, 130, 230]))
    dust_ratio = np.sum(dust_warm > 0) / total
    # Kiem tra saturation trung binh - bui co S cao hon khoi
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    if dust_ratio > 0.15 and avg_sat > 35:
        return True, "dust"

    # 5. Loai bo vung toi den (V < 30)
    #    Khoi den dam co V thap nhung co texture, nen tang nguong
    dark = np.mean(roi_hsv[:, :, 2] < 25)
    if dark > 0.7:
        return True, "too_dark"

    # 6. Loai bo vat trong suot/sang bong (chai nuoc, kinh, plastic)
    #    Dac diem: co diem sang rat manh (highlight/reflection) + do tuong phan cao
    #    Khoi thuc te khong bao gio co highlight sac nhu vay
    v_channel = roi_hsv[:, :, 2]
    bright_pixels = np.sum(v_channel > 230) / total  # Highlight ratio
    v_std = float(np.std(v_channel))
    # Vat trong suot: co nhieu highlight (>10%) + contrast cao
    if bright_pixels > 0.10 and v_std > 50:
        return True, "transparent_object"

    # 7. Loai bo vat co canh sac qua ro (chai, hop, do vat ran)
    #    Khoi luon mo, mem - khong bao gio co canh sac
    edges = cv2.Canny(roi_gray, 50, 150)
    edge_density = float(np.mean(edges > 0))
    if edge_density > 0.15:
        return True, "sharp_edges"

    return False, ""


def _smoke_color_score(roi_hsv, env_brightness):
    """Diem mau khoi.

    Khoi co dac diem mau:
      - Saturation thap (xam)
      - Value trung binh (khong qua sang, khong qua toi)
      - Bao gom: xam nhat, trang duc, xam den

    Returns:
        (score: float 0-1, details: dict)
    """
    total = roi_hsv.shape[0] * roi_hsv.shape[1]
    if total == 0:
        return 0.0, {}

    # Khoi xam nhat (S thap, V trung binh)
    mask_light = cv2.inRange(roi_hsv,
                             np.array([0, 0, 80]), np.array([180, 35, 200]))
    # Khoi trang duc (S rat thap, V cao)
    mask_white = cv2.inRange(roi_hsv,
                             np.array([0, 0, 185]), np.array([180, 25, 245]))
    # Khoi den/dam (S thap, V thap-trung binh)
    mask_dark = cv2.inRange(roi_hsv,
                            np.array([0, 0, 35]), np.array([180, 50, 100]))

    light_r = np.sum(mask_light > 0) / total
    white_r = np.sum(mask_white > 0) / total
    dark_r = np.sum(mask_dark > 0) / total

    # Kiem tra saturation tong the (khoi co S thap, bui co S cao hon)
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    sat_penalty = 1.0
    if avg_sat > 45:
        # Penalty manh hon khi saturation cao (bui, dat, co)
        sat_penalty = max(0.2, 1.0 - (avg_sat - 45) / 80.0)

    raw = (light_r * 2.0 + white_r * 1.5 + dark_r * 1.0) * sat_penalty

    # Adaptive
    if env_brightness < 80:
        raw *= 1.15
    elif env_brightness > 200:
        raw *= 0.85

    score = min(raw / 0.8, 1.0)

    details = {'light': light_r, 'white': white_r, 'dark': dark_r,
               'avg_sat': avg_sat}
    return score, details


def _smoke_texture_score(roi_gray):
    """Diem texture khoi (energy thap = mo, mem).

    Khoi co texture mem, mo:
      - Laplacian energy THAP (khac vat ran co edge sac)
      - Local std THAP (do dong deu)
    Nguoc lai voi lua (texture variance cao).

    Returns:
        float: 0-1
    """
    if roi_gray.size < 64:
        return 0.0

    # Laplacian energy
    lap = cv2.Laplacian(roi_gray, cv2.CV_64F)
    lap_var = float(np.var(lap))

    # Khoi: Laplacian variance thap (<= 500)
    # Vat ran: Laplacian variance cao (> 1000)
    if lap_var > 1500:
        texture_s = 0.0     # Qua sac -> khong phai khoi
    elif lap_var > 500:
        texture_s = (1500 - lap_var) / 2000.0
    elif lap_var > 50:
        texture_s = 0.5 + (500 - lap_var) / 900.0
    else:
        texture_s = 0.3     # Qua phang -> co the la tuong

    # Local std (khoi co std thap nhung khong bang khong)
    local = cv2.blur(roi_gray.astype(np.float32), (7, 7))
    local_sq = cv2.blur((roi_gray.astype(np.float32))**2, (7, 7))
    local_std = np.sqrt(np.maximum(local_sq - local**2, 0))
    avg_local_std = float(np.mean(local_std))

    # Khoi: avg_local_std 8-40 (co chut bien dong nhung khong nhieu)
    if 8 < avg_local_std < 40:
        texture_s = min(texture_s + 0.2, 1.0)
    elif avg_local_std < 5:
        texture_s *= 0.5    # Qua deu -> tuong/nen

    return max(0.0, min(texture_s, 1.0))


def _smoke_edge_score(roi_gray):
    """Diem mat do canh khoi (edge density thap).

    Khoi co it edge sac vi no mo, mem, ban trong suot.
    Khac voi vat ran co vien ro rang.
    Edge density thap -> kha nang la khoi cao.

    Returns:
        float: 0-1
    """
    if roi_gray.size < 64:
        return 0.0

    edges = cv2.Canny(roi_gray, 30, 100)
    edge_density = float(np.mean(edges > 0))

    # Khoi: edge_density thap (0.01-0.1)
    # Vat ran: edge_density cao (0.15+)
    if edge_density < 0.02:
        return 0.5          # Qua it -> co the la nen phang
    elif edge_density < 0.06:
        return 0.9          # Rat it edge -> giong khoi
    elif edge_density < 0.12:
        return 0.6
    elif edge_density < 0.20:
        return 0.3
    else:
        return 0.0          # Nhieu edge -> khong phai khoi


def verify_smoke_roi(roi_bgr, env_brightness=128.0, threshold=0.35):
    """Xac minh ROI co chua khoi hay khong (multi-criteria).

    Pipeline:
      1. Rejection filter: loai skin, tuong phang, troi, toi
      2. Color:   40% - mau xam/trang, saturation thap
      3. Texture: 35% - energy thap (mo, mem)
      4. Edge:    25% - it canh sac

    Args:
        roi_bgr: numpy array BGR
        env_brightness: do sang moi truong
        threshold: nguong diem tong hop

    Returns:
        (is_smoke: bool, score: float 0-1, details: dict)
    """
    if roi_bgr is None or roi_bgr.size == 0:
        return False, 0.0, {}

    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

    # Rejection filter
    rejected, reason = _smoke_rejection(hsv, gray)
    if rejected:
        return False, 0.0, {'rejected': reason}

    # 3 tieu chi
    color_s, color_detail = _smoke_color_score(hsv, env_brightness)
    texture_s = _smoke_texture_score(gray)
    edge_s = _smoke_edge_score(gray)

    # Diem tong hop
    final = (
        color_s * 0.40 +
        texture_s * 0.35 +
        edge_s * 0.25
    )

    # Adaptive threshold
    if env_brightness < 80:
        adj_threshold = threshold * 0.85
    elif env_brightness > 200:
        adj_threshold = threshold * 1.15
    else:
        adj_threshold = threshold

    is_smoke = final > adj_threshold

    details = {
        'color': round(color_s, 3),
        'texture': round(texture_s, 3),
        'edge': round(edge_s, 3),
        'final': round(final, 3),
        'threshold': round(adj_threshold, 3),
        'color_detail': color_detail
    }

    return is_smoke, final, details


# ############################################################
#
#   LEGACY WRAPPERS (backward compatibility)
#
# ############################################################

def color_fire_check(roi_bgr, color_threshold=0.15, bright_threshold=0.12,
                     env_brightness=128.0, return_ratio=False):
    """Wrapper: dung verify_fire_roi ben trong."""
    is_fire, score, _ = verify_fire_roi(roi_bgr, env_brightness, threshold=0.28)
    if return_ratio:
        return is_fire, score
    return is_fire


def color_smoke_check(roi_bgr, color_threshold=0.20, env_brightness=128.0,
                      gray_mean_range=(60, 190), gray_std_range=(18, 65),
                      return_ratio=False):
    """Wrapper: dung verify_smoke_roi ben trong."""
    is_smoke, score, _ = verify_smoke_roi(roi_bgr, env_brightness, threshold=0.35)
    if return_ratio:
        return is_smoke, score
    return is_smoke


# ============================================================
# PHAT HIEN NHAP NHAY (Flicker Detection)
# ============================================================

class FlickerDetector:
    """Phat hien nhap nhay lua qua bien thien do sang. Thread-safe."""

    def __init__(self, history_size=5, min_std=8.0, normalize_factor=20.0):
        self._history = []
        self._history_size = history_size
        self._min_std = min_std
        self._normalize_factor = normalize_factor
        self._lock = threading.Lock()

    def update(self, brightness):
        with self._lock:
            self._history.append(brightness)
            if len(self._history) > self._history_size:
                self._history.pop(0)

    def compute(self):
        """Returns (has_flicker, score)."""
        with self._lock:
            history = self._history.copy()
        if len(history) < 2:
            return False, 0.0
        std = float(np.std(history))
        score = min(std / self._normalize_factor, 1.0)
        return std >= self._min_std, score

    def reset(self):
        with self._lock:
            self._history.clear()


# ============================================================
# BO PHIEU THEO FRAME (Frame Voting)
# ============================================================

class FrameVoter:
    """Bo phieu theo frame lien tiep. Thread-safe."""

    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    @property
    def count(self):
        with self._lock:
            return self._count

    def update(self, detected):
        with self._lock:
            self._count = self._count + 1 if detected else 0
            return self._count

    def is_confirmed(self, threshold):
        with self._lock:
            return self._count >= threshold

    def reset(self):
        with self._lock:
            self._count = 0


# ============================================================
# MOTION ANALYZER (Temporal Analysis)
# ============================================================

class MotionAnalyzer:
    """Phan tich chuyen dong giua cac frame.

    Phat hien:
      - Lua: chuyen dong nhanh, hon loan trong vung bbox
      - Khoi: chuyen dong cham, huong len tren

    Dung frame differencing (hoat dong tot ca voi FPS thap tu ESP32).
    Thread-safe.
    """

    def __init__(self, alpha=0.4):
        self._prev_gray = None
        self._alpha = alpha
        self._lock = threading.Lock()

    def update(self, frame_gray):
        """Cap nhat frame moi."""
        with self._lock:
            small = cv2.resize(frame_gray, (160, 120))
            if self._prev_gray is None:
                self._prev_gray = small.astype(np.float32)
                return

            # Running average
            cv2.accumulateWeighted(
                small.astype(np.float32), self._prev_gray, self._alpha)

    def get_motion_score(self, frame_gray, bbox=None):
        """Tinh diem chuyen dong trong vung bbox.

        Args:
            frame_gray: gray frame hien tai
            bbox: (x1, y1, x2, y2) hoac None (toan frame)

        Returns:
            float: motion score 0-1
        """
        with self._lock:
            if self._prev_gray is None:
                return 0.0

            small = cv2.resize(frame_gray, (160, 120))
            diff = cv2.absdiff(small, self._prev_gray.astype(np.uint8))

            if bbox is not None:
                # Scale bbox xuong 160x120
                fh, fw = frame_gray.shape[:2]
                sx, sy = 160.0 / fw, 120.0 / fh
                x1 = max(0, int(bbox[0] * sx))
                y1 = max(0, int(bbox[1] * sy))
                x2 = min(160, int(bbox[2] * sx))
                y2 = min(120, int(bbox[3] * sy))
                if x2 > x1 and y2 > y1:
                    diff = diff[y1:y2, x1:x2]

            mean_diff = float(np.mean(diff))
            return min(mean_diff / 40.0, 1.0)

    def get_motion_direction(self, frame_gray, bbox):
        """Uoc luong huong chuyen dong (len/xuong).

        Khoi thuong di len, lua dao dong.

        Returns:
            str: 'up', 'down', 'mixed', 'none'
        """
        with self._lock:
            if self._prev_gray is None:
                return 'none'

            small = cv2.resize(frame_gray, (160, 120))
            diff = cv2.absdiff(small, self._prev_gray.astype(np.uint8))

            fh, fw = frame_gray.shape[:2]
            sx, sy = 160.0 / fw, 120.0 / fh
            x1 = max(0, int(bbox[0] * sx))
            y1 = max(0, int(bbox[1] * sy))
            x2 = min(160, int(bbox[2] * sx))
            y2 = min(120, int(bbox[3] * sy))
            if x2 <= x1 or y2 <= y1:
                return 'none'

            roi_diff = diff[y1:y2, x1:x2]
            h = roi_diff.shape[0]
            if h < 4:
                return 'none'

            top_half = float(np.mean(roi_diff[:h // 2]))
            bot_half = float(np.mean(roi_diff[h // 2:]))

            if top_half > bot_half * 1.3:
                return 'up'
            elif bot_half > top_half * 1.3:
                return 'down'
            return 'mixed'

    def reset(self):
        with self._lock:
            self._prev_gray = None


# ============================================================
# FIRE REGION TRACKER (Temporal Fire Rating)
# ============================================================

class FireRegionTracker:
    """Theo doi vung lua qua nhieu frame de danh gia that/gia.

    Lua that co dac diem:
      - Bap bung: kich thuoc bbox thay doi lien tuc (std > 0)
      - Lan rong: dien tich tang dan theo thoi gian
      - Cuong do thay doi: pixel intensity dao dong

    LED/vat tinh:
      - Bbox gan nhu co dinh qua cac frame
      - Khong thay doi kich thuoc
      - Intensity on dinh

    Rating scale:
      0.0 - 0.3: Rat co the la LED/vat tinh -> REJECT
      0.3 - 0.6: Khong chac chan -> WARNING
      0.6 - 1.0: Rat co the la lua that -> CONFIRM

    Thread-safe.
    """

    def __init__(self, history_size=10, iou_threshold=0.3):
        self._history = []       # list of {'bbox': [x1,y1,x2,y2], 'area': float, 'intensity': float}
        self._history_size = history_size
        self._iou_threshold = iou_threshold
        self._lock = threading.Lock()

    def _iou(self, box1, box2):
        """Tinh Intersection over Union giua 2 bbox."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0

    def update(self, bbox, roi_gray=None):
        """Cap nhat vung fire moi.

        Args:
            bbox: [x1, y1, x2, y2]
            roi_gray: gray ROI de tinh intensity (optional)
        """
        with self._lock:
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            intensity = float(np.mean(roi_gray)) if roi_gray is not None and roi_gray.size > 0 else 0

            entry = {
                'bbox': list(bbox),
                'area': area,
                'intensity': intensity,
                'center': [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
            }

            # Kiem tra co phai cung vung lua khong (IoU > threshold)
            if self._history:
                last = self._history[-1]
                iou = self._iou(bbox, last['bbox'])
                if iou < self._iou_threshold:
                    # Vung lua moi hoan toan -> reset history
                    self._history.clear()

            self._history.append(entry)
            if len(self._history) > self._history_size:
                self._history.pop(0)

    def get_rating(self):
        """Tinh Fire Rating dua tren lich su frame.

        Returns:
            (rating: float 0-1, details: dict)
            - rating cao = kha nang la lua that
            - rating thap = kha nang la LED/vat tinh
        """
        with self._lock:
            history = self._history.copy()

        n = len(history)
        if n < 3:
            return 0.5, {'reason': 'not_enough_frames', 'frames': n}

        areas = [h['area'] for h in history]
        intensities = [h['intensity'] for h in history]
        centers = [h['center'] for h in history]

        # 1. Bap bung: do dao dong kich thuoc (std cua area)
        area_mean = np.mean(areas)
        area_std = np.std(areas)
        area_cv = area_std / area_mean if area_mean > 0 else 0  # coefficient of variation
        # Lua: CV > 0.05 (dao dong > 5%)
        # LED: CV ~ 0 (on dinh)
        flicker_score = min(area_cv / 0.15, 1.0)  # normalize: CV=0.15 -> score=1.0

        # 2. Lan rong: xu huong tang cua area
        if n >= 4:
            first_half = np.mean(areas[:n//2])
            second_half = np.mean(areas[n//2:])
            growth = (second_half - first_half) / first_half if first_half > 0 else 0
            growth_score = min(max(growth, 0) / 0.3, 1.0)  # tang 30% -> score=1.0
        else:
            growth_score = 0.0

        # 3. Dao dong intensity
        if intensities[0] > 0:
            int_std = np.std(intensities)
            int_score = min(int_std / 10.0, 1.0)  # std=10 -> score=1.0
        else:
            int_score = 0.0

        # 4. Vi tri dao dong (lua nhap nhay thay doi vi tri nhe)
        cx = [c[0] for c in centers]
        cy = [c[1] for c in centers]
        pos_std = np.sqrt(np.std(cx)**2 + np.std(cy)**2)
        pos_score = min(pos_std / 5.0, 1.0)  # std=5px -> score=1.0

        # Tong hop rating
        rating = (
            flicker_score * 0.35 +    # Bap bung quan trong nhat
            growth_score * 0.20 +      # Lan rong
            int_score * 0.25 +         # Cuong do thay doi
            pos_score * 0.20           # Vi tri dao dong
        )

        details = {
            'frames': n,
            'flicker': round(flicker_score, 3),
            'growth': round(growth_score, 3),
            'intensity_var': round(int_score, 3),
            'position_var': round(pos_score, 3),
            'area_cv': round(area_cv, 4),
            'rating': round(rating, 3)
        }

        return rating, details

    def is_real_fire(self, min_rating=0.25):
        """Kiem tra co phai lua that khong.

        Args:
            min_rating: nguong toi thieu (default 0.25 - cho phep lua vua bat dau)

        Returns:
            bool
        """
        rating, _ = self.get_rating()
        return rating >= min_rating

    def reset(self):
        with self._lock:
            self._history.clear()


# ============================================================
# KET HOP DIEM (Score Fusion)
# ============================================================

def compute_fire_score(yolo_conf, color_ratio, flicker_score, weights=None):
    """Tinh diem phat hien lua tong hop."""
    if weights is None:
        weights = {"yolo": 0.35, "color": 0.45, "flicker": 0.2}

    w_yolo = weights.get("yolo", 0.35)
    w_color = weights.get("color", 0.45)
    w_flicker = weights.get("flicker", 0.2)

    total = w_yolo + w_color + w_flicker
    if total == 0:
        return 0.0
    w_yolo /= total
    w_color /= total
    w_flicker /= total

    base_score = w_yolo * yolo_conf + w_color * color_ratio + w_flicker * flicker_score
    boost = max(color_ratio * 0.8, flicker_score * 0.7)
    return float(np.clip(max(base_score, boost), 0.0, 1.0))


# ============================================================
# PIPELINE XU LY DETECTION
# ============================================================

def process_detections(boxes, img, model_names, mode_config, bbox_config,
                       env_brightness=128.0, enable_smoke=False, smoke_config=None):
    """Xu ly ket qua YOLO detection tren 1 frame.

    Pipeline nang cao:
      1. Loc bbox (kich thuoc, ty le)
      2. Trich xuat ROI
      3. Fire: verify_fire_roi (5 tieu chi)
      4. Smoke: verify_smoke_roi (rejection + 3 tieu chi)
      5. Tra ve danh sach detection hop le
    """
    result = {
        'fire_bboxes': [],
        'smoke_bboxes': [],
        'has_fire': False,
        'has_smoke': False,
        'fire_scores': [],
    }

    if boxes is None:
        return result

    try:
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)
    except Exception:
        return result

    img_shape = img.shape

    # Nguong verify tu mode config
    fire_threshold = mode_config.get("verify_threshold", 0.28)
    smoke_threshold = 0.35
    if smoke_config:
        smoke_threshold = smoke_config.get("verify_threshold", 0.35)

    use_score_fusion = mode_config.get("use_score_fusion", False)

    for (x1, y1, x2, y2), conf, cls in zip(xyxy, confs, clss):
        cls_id = int(cls)
        if isinstance(model_names, dict):
            name = model_names.get(cls_id, str(cls_id))
        elif isinstance(model_names, (list, tuple)) and cls_id < len(model_names):
            name = model_names[cls_id]
        else:
            name = str(cls_id)

        is_fire = 'fire' in name.lower()
        is_smoke_cls = 'smoke' in name.lower()

        bbox = (float(x1), float(y1), float(x2), float(y2))

        if not is_valid_bbox(bbox, img_shape, is_fire, bbox_config):
            continue

        # ROI extraction
        x1i = max(0, int(x1))
        y1i = max(0, int(y1))
        x2i = min(img_shape[1], int(x2))
        y2i = min(img_shape[0], int(y2))

        if x2i <= x1i or y2i <= y1i:
            continue

        roi = img[y1i:y2i, x1i:x2i]

        # FIRE verification
        if is_fire:
            is_confirmed, fire_score, details = verify_fire_roi(
                roi, env_brightness, threshold=fire_threshold
            )

            if not is_confirmed:
                continue

            result['has_fire'] = True
            bbox_data = {
                'class': name,
                'class_id': cls_id,
                'conf': float(conf),
                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                'verify_score': round(fire_score, 3),
                'verify_details': details
            }
            result['fire_bboxes'].append(bbox_data)

            if use_score_fusion:
                result['fire_scores'].append({
                    'yolo_conf': float(conf),
                    'color_ratio': fire_score,
                    'bbox_data': bbox_data
                })

        # SMOKE verification
        elif is_smoke_cls and enable_smoke:
            is_confirmed, smoke_score, details = verify_smoke_roi(
                roi, env_brightness, threshold=smoke_threshold
            )

            if not is_confirmed:
                continue

            result['has_smoke'] = True
            result['smoke_bboxes'].append({
                'class': name,
                'class_id': cls_id,
                'conf': float(conf),
                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                'verify_score': round(smoke_score, 3),
                'verify_details': details
            })

    return result


# ============================================================
# DRAW UTILS
# ============================================================

def draw_detections(frame, fire_bboxes, smoke_bboxes, fire_confirmed=False,
                    smoke_confirmed=False, info_text=None):
    """Ve bounding boxes va status len frame."""
    for fb in fire_bboxes:
        x1, y1, x2, y2 = fb['bbox']
        vs = fb.get('verify_score', 0)
        label = f"{fb['class']} {fb['conf']:.2f} v:{vs:.2f}"
        color = (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, label, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    for sb in smoke_bboxes:
        x1, y1, x2, y2 = sb['bbox']
        vs = sb.get('verify_score', 0)
        label = f"{sb['class']} {sb['conf']:.2f} v:{vs:.2f}"
        color = (0, 165, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, label, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    if fire_confirmed:
        cv2.putText(frame, "FIRE CONFIRMED!", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
    if smoke_confirmed:
        cv2.putText(frame, "SMOKE DETECTED", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    if info_text:
        cv2.putText(frame, info_text, (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    return frame
