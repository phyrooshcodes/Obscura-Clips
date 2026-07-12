# ============================================================
# face_tracker.py — Module 4: Face Tracking & Crop Calculation
# Hardware Target: CPU — Google MediaPipe
# Purpose: Detect the speaker's face frame-by-frame and
#          compute a smooth 9:16 vertical crop window.
#          Zero GPU shader usage — pure CPU optimized graph.
# ============================================================

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ─── Target aspect ratio for vertical clips ─────────────────
TARGET_ASPECT_W = 9
TARGET_ASPECT_H = 16


def compute_crop_coords(
    input_video: str,
    start_ms: int,
    end_ms: int,
    smoothing_window: int = 15,
    sample_every_n_frames: int = 5
) -> Dict:
    """
    Analyze a video segment and compute a smooth 9:16 crop box
    centered on the detected face(s).

    Args:
        input_video:         Path to the source video file.
        start_ms:            Clip start time in milliseconds.
        end_ms:              Clip end time in milliseconds.
        smoothing_window:    Number of frames to average for
                             smooth crop movement.
        sample_every_n_frames: Only run face detection every N
                               frames to reduce CPU load.

    Returns:
        A dict containing:
        {
            "crop_w": int,      # Crop width in pixels
            "crop_h": int,      # Crop height (= source height)
            "crop_x": int,      # Final crop X offset (left edge)
            "src_w":  int,      # Original video width
            "src_h":  int,      # Original video height
            "face_detected": bool
        }
    """
    # Resolve local cascade XML path and download if missing
    from pathlib import Path
    import urllib.request
    
    cascade_path = Path(__file__).parent / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        logger.info(f"[FaceTracker] Cascade file not found locally. Downloading from official OpenCV GitHub...")
        url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                cascade_path.write_bytes(response.read())
            logger.info(f"[FaceTracker] Successfully downloaded cascade file to: {cascade_path}")
        except Exception as e:
            raise RuntimeError(f"[FaceTracker] Failed to download Haar Cascade XML from {url}: {e}") from e

    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    if face_cascade.empty():
        raise RuntimeError(f"[FaceTracker] Failed to load Haar Cascade from {cascade_path}")

    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        raise RuntimeError(f"[FaceTracker] Cannot open video: {input_video}")

    fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Calculate the crop dimensions for 9:16 aspect ratio
    # We always use full height and calculate the matching width
    crop_h = src_h
    crop_w = int(src_h * (TARGET_ASPECT_W / TARGET_ASPECT_H))

    # If source video is already narrower than needed, use source width
    if crop_w > src_w:
        crop_w = src_w

    logger.info(
        f"[FaceTracker] Source: {src_w}x{src_h} | "
        f"9:16 Crop: {crop_w}x{crop_h}"
    )

    # Seek to clip start
    start_frame = int((start_ms / 1000.0) * fps)
    end_frame   = int((end_ms   / 1000.0) * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    face_x_positions: List[float] = []
    frame_idx = start_frame
    face_detected = False

    while frame_idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        # Only run detection every N frames (CPU saver)
        if (frame_idx - start_frame) % sample_every_n_frames == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Detect faces
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(60, 60)
            )

            if len(faces) > 0:
                face_detected = True
                # Sort faces by size (width * height) descending and pick the largest face
                faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                fx, fy, fw, fh = faces[0]
                
                # Calculate face center X in pixels
                face_center_x = fx + (fw / 2.0)
                face_x_positions.append(face_center_x)

        frame_idx += 1

    cap.release()

    # ─── Calculate final crop X offset ──────────────────────
    crop_x = _calculate_smooth_crop_x(
        face_x_positions, crop_w, src_w, smoothing_window
    )

    logger.info(
        f"[FaceTracker] ✅ Face detected: {face_detected} | "
        f"Crop X offset: {crop_x}px | "
        f"Sampled {len(face_x_positions)} face positions."
    )

    return {
        "crop_w":        crop_w,
        "crop_h":        crop_h,
        "crop_x":        crop_x,
        "src_w":         src_w,
        "src_h":         src_h,
        "face_detected": face_detected
    }


def _calculate_smooth_crop_x(
    face_x_positions: List[float],
    crop_w: int,
    src_w: int,
    smoothing_window: int
) -> int:
    """
    Calculate the optimal crop X offset based on collected face positions.

    Uses a rolling average for smooth, stable crop placement.
    Falls back to center crop if no faces were detected.

    Args:
        face_x_positions: List of face center X coordinates (pixels).
        crop_w:           Width of the 9:16 crop box.
        src_w:            Source video width.
        smoothing_window: Rolling average window size.

    Returns:
        Integer X offset (left edge of crop box).
    """
    if not face_x_positions:
        # No face detected → center crop fallback
        logger.warning("[FaceTracker] No face detected — defaulting to center crop.")
        return max(0, (src_w - crop_w) // 2)

    # Apply rolling average smoothing
    if len(face_x_positions) > smoothing_window:
        smoothed = np.convolve(
            face_x_positions,
            np.ones(smoothing_window) / smoothing_window,
            mode="valid"
        )
        avg_face_x = float(np.median(smoothed))
    else:
        avg_face_x = float(np.mean(face_x_positions))

    # Center the crop box on the average face position
    # crop_x = face_center - half_crop_width
    crop_x = int(avg_face_x - crop_w / 2)

    # Clamp to valid range: [0, src_w - crop_w]
    crop_x = max(0, min(crop_x, src_w - crop_w))

    return crop_x
