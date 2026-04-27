"""
Stereo vision module for FireGuard turret.

Computes distance from camera baseline to fire target using disparity:
    distance = (focal_length_px * baseline_m) / disparity_px

Calibration values are PLACEHOLDERS — user said "tôi tự calibrate sau".
Replace BASELINE_M and FOCAL_PX with calibrated values from a checkerboard.
"""

import math
import numpy as np
import cv2


# ============================================================
# CALIBRATION (replace with real calibrated values)
# ============================================================
# Distance between cam1 and cam2 lenses, meters
BASELINE_M = 0.05          # 5 cm — adjust after physical measurement
# Effective focal length in pixels (depends on resolution + lens)
# For OV2640 at 800x600 with default FOV ~70°: focal_px ≈ width/(2*tan(fov/2)) ≈ 570
FOCAL_PX = 570.0


def bbox_center(bbox):
    """bbox = [x1, y1, x2, y2] -> (cx, cy) in pixels."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def match_bbox(bboxes_a, bboxes_b, tol_y=40):
    """Pair the most-likely-same fire region between two camera views.

    Both cameras are roughly aligned horizontally (rectified later by user).
    Match by smallest |y_a - y_b| + similar size, within `tol_y` rows.
    Returns (bbox_a, bbox_b) or (None, None).
    """
    if not bboxes_a or not bboxes_b:
        return None, None

    best = None
    best_score = float('inf')
    for ba in bboxes_a:
        cax, cay = bbox_center(ba)
        wa = ba[2] - ba[0]
        ha = ba[3] - ba[1]
        for bb in bboxes_b:
            cbx, cby = bbox_center(bb)
            wb = bb[2] - bb[0]
            hb = bb[3] - bb[1]
            dy = abs(cay - cby)
            if dy > tol_y:
                continue
            size_diff = abs(wa - wb) + abs(ha - hb)
            score = dy + 0.3 * size_diff
            if score < best_score:
                best_score = score
                best = (ba, bb)
    return best if best else (None, None)


def compute_disparity(bbox_left, bbox_right):
    """Disparity = x_left - x_right (positive when target in front of cameras).

    Bigger disparity → closer target.
    """
    if bbox_left is None or bbox_right is None:
        return None
    cl, _ = bbox_center(bbox_left)
    cr, _ = bbox_center(bbox_right)
    d = cl - cr
    return d if d > 0.5 else None  # ignore tiny / negative disparity


def distance_from_disparity(disparity_px, baseline_m=BASELINE_M, focal_px=FOCAL_PX):
    """distance = focal_px * baseline_m / disparity_px  → meters."""
    if disparity_px is None or disparity_px <= 0:
        return None
    return float(focal_px * baseline_m / disparity_px)


def stereo_distance(bboxes_left, bboxes_right):
    """Convenience: pair the best bbox match and return (distance_m, paired_bboxes).

    Returns (None, (None, None)) if no valid pair / disparity.
    """
    bl, br = match_bbox(bboxes_left, bboxes_right)
    if bl is None or br is None:
        return None, (None, None)
    d_px = compute_disparity(bl, br)
    if d_px is None:
        return None, (bl, br)
    R = distance_from_disparity(d_px)
    return R, (bl, br)
