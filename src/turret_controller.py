"""
Turret controller for FireGuard.

Responsibilities:
  - Target selection: pick fire bbox closest to image center
  - Target locking: keep current target until it disappears
  - Ballistics: compute pan/tilt servo angles from image-space error
                and apply distance-based pitch compensation
  - Burst firing: trigger pump for 2-3s when target is centered & stable
  - Command builder: emit JSON for ESP32-CAM 2 /control endpoint

Distance compensation formula (user-specified):
    θ = (1/2) * arcsin( g * R / v² )
    where:
        g = 9.81 m/s²
        v = 37 m/s   (water jet velocity from 100 PSI, via Bernoulli)
        R = horizontal distance from nozzle to target (meters)
    θ is the EXTRA pitch angle (radians) to add upward.
"""

import math
import time
import requests


# ============================================================
# PHYSICAL CONSTANTS
# ============================================================
GRAVITY      = 9.81        # m/s²
# Ap suat bom 100 PSI -> van toc tia nuoc:  v = sqrt(2*P/rho)
#   P = 100 PSI = 689476 Pa,  rho = 1000 kg/m3  ->  v ~ 37 m/s
WATER_VEL    = 37.0        # m/s (tu 100 PSI)


# ============================================================
# SERVO MAPPING (image pixel → servo degree)
# Tune these per physical mounting.
# ============================================================
IMG_WIDTH  = 800
IMG_HEIGHT = 600

PAN_HOME, PAN_MIN, PAN_MAX     = 90,  0,   180
TILT_HOME, TILT_MIN, TILT_MAX  = 90,  20,  160

# Field of view (degrees) of camera, approximate for OV2640
CAM_FOV_HORIZONTAL = 70.0
CAM_FOV_VERTICAL   = 55.0


# ============================================================
# CONTROL THRESHOLDS
# ============================================================
CENTER_TOLERANCE_PX  = 40     # bbox center within ± px of image center → centered
STABLE_FRAMES        = 3      # need N consecutive centered frames before fire
BURST_DURATION_MS    = 2500   # default burst length
BURST_COOLDOWN_S     = 4.0    # min gap between bursts


# ============================================================
# CORE FUNCTIONS
# ============================================================
def gravity_compensation_deg(distance_m, v=WATER_VEL, g=GRAVITY):
    """Calculate extra tilt angle (degrees, positive = upward)
    needed to hit target at horizontal distance R.

        θ = ½ arcsin(gR / v²)

    Returns 0.0 if distance is None or out of physical range."""
    if distance_m is None or distance_m <= 0:
        return 0.0
    arg = (g * distance_m) / (v * v)
    if arg >= 1.0:
        # Target beyond max ballistic range — return max angle (45°)
        return 45.0
    theta_rad = 0.5 * math.asin(arg)
    return math.degrees(theta_rad)


def pixel_to_servo_angles(target_cx, target_cy,
                          current_pan, current_tilt,
                          img_w=IMG_WIDTH, img_h=IMG_HEIGHT):
    """Convert target image coordinates → desired servo (pan, tilt) angles.

    Uses simple proportional mapping by camera FOV. Camera and turret are
    assumed coaxially mounted (camera moves with turret).

    target_cx, target_cy : pixel coordinates of target center
    current_pan, current_tilt : current servo angles (degrees)
    """
    # Image-space error (-1..+1) from center
    err_x = (target_cx - img_w / 2) / (img_w / 2)
    err_y = (target_cy - img_h / 2) / (img_h / 2)

    # Convert to angle: half-FOV per side
    angle_x = err_x * (CAM_FOV_HORIZONTAL / 2.0)
    angle_y = err_y * (CAM_FOV_VERTICAL   / 2.0)

    # Apply to current servo position (turret moves opposite to error)
    # If target is to the right (err_x > 0), pan right (increase angle).
    new_pan  = current_pan  + angle_x
    new_tilt = current_tilt - angle_y    # image y grows downward

    new_pan  = max(PAN_MIN,  min(PAN_MAX,  new_pan))
    new_tilt = max(TILT_MIN, min(TILT_MAX, new_tilt))
    return new_pan, new_tilt


def select_target(bboxes, prev_target=None,
                  img_w=IMG_WIDTH, img_h=IMG_HEIGHT,
                  iou_threshold=0.2):
    """Pick the best fire bbox to engage.

    Priority:
      1. If prev_target still overlaps a current bbox (IoU > thresh), keep it (LOCK).
      2. Otherwise pick the bbox closest to image center.

    bboxes : list of [x1, y1, x2, y2]
    prev_target : previously locked bbox (or None)

    Returns: chosen bbox or None.
    """
    if not bboxes:
        return None

    # Try to keep previous lock
    if prev_target is not None:
        for b in bboxes:
            if _iou(prev_target, b) >= iou_threshold:
                return b

    # Pick nearest to center
    cx_img, cy_img = img_w / 2, img_h / 2
    def dist_to_center(b):
        cx = (b[0] + b[2]) / 2
        cy = (b[1] + b[3]) / 2
        return (cx - cx_img) ** 2 + (cy - cy_img) ** 2
    return min(bboxes, key=dist_to_center)


def _iou(a, b):
    """Intersection over Union for two bboxes [x1,y1,x2,y2]."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ============================================================
# CONTROLLER (stateful)
# ============================================================
class TurretController:
    """Holds current state: locked target, servo position, burst cooldown.

    Call `process(bboxes_left, bboxes_right, frame_pair)` each cycle to
    update the controller. It returns a dict you can POST to ESP32-CAM 2's
    /control endpoint.
    """

    def __init__(self, esp2_url=None):
        self.esp2_url      = esp2_url      # e.g. "http://10.199.56.103"
        self.target        = None          # locked bbox
        self.target_lost_count = 0
        self.centered_streak   = 0
        self.last_burst_at     = 0.0
        self.current_pan       = PAN_HOME
        self.current_tilt      = TILT_HOME
        self.last_distance     = None

    # --------------------------------------------------------
    def update(self, bboxes_left, bboxes_right, distance_m=None):
        """Run one control step.

        bboxes_left  : list of [x1,y1,x2,y2] from camera 1 (master / reference)
        bboxes_right : list of [x1,y1,x2,y2] from camera 2 (used for stereo)
        distance_m   : optional override (else computed from stereo elsewhere)

        Returns: command dict {pan, tilt, pump, burst_ms} (or None if no action)
        """
        # 1. Select / lock target
        tgt = select_target(bboxes_left, prev_target=self.target)
        if tgt is None:
            self.target_lost_count += 1
            if self.target_lost_count >= 3:
                # target gone for too long — release lock
                self.target = None
                self.centered_streak = 0
            return self._idle_command()
        self.target_lost_count = 0
        self.target = tgt

        # 2. Distance (from stereo)
        if distance_m is not None:
            self.last_distance = distance_m

        # 3. Compute new servo angles aiming at target center
        cx = (tgt[0] + tgt[2]) / 2.0
        cy = (tgt[1] + tgt[3]) / 2.0
        new_pan, new_tilt = pixel_to_servo_angles(
            cx, cy, self.current_pan, self.current_tilt
        )

        # 4. Distance-based gravity compensation (ADD upward = subtract from tilt
        #    if servo tilt 90 = horizontal and lower = up. For symmetry assume
        #    larger tilt = aim higher, so we ADD theta.)
        comp = gravity_compensation_deg(self.last_distance)
        new_tilt = max(TILT_MIN, min(TILT_MAX, new_tilt + comp))

        self.current_pan  = round(new_pan,  1)
        self.current_tilt = round(new_tilt, 1)

        # 5. Centered? track streak
        is_centered = (
            abs(cx - IMG_WIDTH / 2) < CENTER_TOLERANCE_PX and
            abs(cy - IMG_HEIGHT / 2) < CENTER_TOLERANCE_PX
        )
        self.centered_streak = (self.centered_streak + 1) if is_centered else 0

        # 6. Decide pump (burst firing)
        now = time.time()
        should_fire = (
            self.centered_streak >= STABLE_FRAMES and
            (now - self.last_burst_at) > BURST_COOLDOWN_S
        )
        if should_fire:
            self.last_burst_at = now

        return {
            "pan":      int(round(self.current_pan)),
            "tilt":     int(round(self.current_tilt)),
            "pump":     bool(should_fire),
            "burst_ms": BURST_DURATION_MS if should_fire else 0,
            "_debug": {
                "target_bbox": list(map(int, tgt)),
                "distance_m": round(self.last_distance, 2) if self.last_distance else None,
                "compensation_deg": round(comp, 2),
                "centered_streak": self.centered_streak,
                "is_centered": is_centered,
            },
        }

    # --------------------------------------------------------
    def _idle_command(self):
        """No target — keep position, pump off."""
        return {
            "pan":  int(round(self.current_pan)),
            "tilt": int(round(self.current_tilt)),
            "pump": False,
            "burst_ms": 0,
            "_debug": {"target_bbox": None, "distance_m": None,
                       "compensation_deg": 0.0,
                       "centered_streak": 0, "is_centered": False},
        }

    # --------------------------------------------------------
    def send(self, command, timeout=1.0):
        """POST command to ESP32-CAM 2 /control endpoint.

        Returns response dict or None on failure."""
        if not self.esp2_url:
            return None
        # strip _debug before sending (ESP doesn't need it)
        payload = {k: v for k, v in command.items() if not k.startswith("_")}
        try:
            r = requests.post(
                f"{self.esp2_url.rstrip('/')}/control",
                json=payload,
                timeout=timeout,
            )
            return r.json() if r.ok else None
        except Exception as e:
            print(f"[TURRET] send error: {e}")
            return None

    # --------------------------------------------------------
    def home(self):
        """Reset to home position, pump off."""
        self.current_pan = PAN_HOME
        self.current_tilt = TILT_HOME
        self.target = None
        self.centered_streak = 0
        if self.esp2_url:
            try:
                requests.get(f"{self.esp2_url.rstrip('/')}/home", timeout=1.0)
            except Exception:
                pass
