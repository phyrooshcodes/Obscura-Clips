# ============================================================
# renderer.py — Module 6: FFmpeg NVENC Final Renderer
# Hardware Target: GPU — NVENC ASIC Block (RTX 3050)
# Purpose: Encode the final 9:16 vertical clip with:
#          - Precise trim (ss/to)
#          - Face-tracked crop filter
#          - Burned-in ASS subtitle overlay
#          - Hardware-accelerated H.264 encoding via NVENC
#          GPU shader cores remain IDLE — only ASIC encodes.
# ============================================================

import subprocess
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─── NVENC Encoding Defaults ─────────────────────────────────
NVENC_PRESET   = "p4"    # Balanced speed/quality (p1=fastest, p7=best quality)
NVENC_CQ       = "23"    # Constant Quality factor (18=near-lossless, 28=compressed)
AUDIO_BITRATE  = "192k"  # AAC audio quality
_nvenc_available: Optional[bool] = None


def render_clip(
    input_video:   str,
    output_path:   str,
    start_ms:      int,
    end_ms:        int,
    crop_coords:   Dict,
    subtitle_path: str,
    music_choice:  Optional[Dict[str, Any]] = None,
    clip_index:    int = 0
) -> str:
    """
    Render a final vertical clip using FFmpeg with NVENC.

    Applies:
      1. Precise seek (-ss / -to) for lossless frame-accurate trimming
      2. crop= filter for 9:16 face-tracked framing
      3. ass= subtitle burn-in filter (TikTok kinetic style)
      4. h264_nvenc encoder (ASIC block, not shader cores)

    Args:
        input_video:    Path to source MP4.
        output_path:    Path for the rendered output clip.
        start_ms:       Clip start in milliseconds.
        end_ms:         Clip end in milliseconds.
        crop_coords:    Dict from face_tracker.compute_crop_coords().
                        Must contain: crop_w, crop_h, crop_x, src_h.
        subtitle_path:  Path to the .ass subtitle file for this clip.
        clip_index:     Clip number (for logging only).

    Returns:
        Path to the rendered clip.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero return code.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Convert milliseconds to seconds for FFmpeg
    start_s = start_ms / 1000.0
    end_s   = end_ms   / 1000.0

    crop_w = crop_coords["crop_w"]
    crop_h = crop_coords["crop_h"]
    crop_x = crop_coords["crop_x"]
    crop_y = 0  # Always crop from top for full-height capture

    # ─── Build the FFmpeg filter chain ───────────────────────
    # Escape subtitle path for FFmpeg (Windows backslashes → forward slashes,
    # and colons in drive letters must be escaped as \:)
    safe_sub_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

    # Filter chain: crop first, then burn subtitles
    vf_filter = (
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale=1080:1920,"          # Upscale/downscale to exact 1080x1920
        f"ass='{safe_sub_path}'"     # Burn ASS subtitles into frame
    )

    # ─── Build FFmpeg Command ────────────────────────────────
    command = [
        "ffmpeg",
        "-y",                          # Overwrite output without prompting

        # Input with precise seek (input seeking = fast, frame-accurate for H.264)
        "-ss",    f"{start_s:.3f}",
        "-to",    f"{end_s:.3f}",
        "-i",     input_video,
    ]

    if music_choice:
        command += [
            # Loop short tracks to cover the whole clip, then trim precisely in
            # the audio filter. The director supplies a clip-specific excerpt.
            "-stream_loop", "-1",
            "-ss", f"{float(music_choice['start_s']):.3f}",
            "-i", music_choice["path"],
            "-filter_complex", _music_mix_filter(end_s - start_s),
            "-map", "0:v:0",
            "-map", "[mixed_audio]",
        ]

    command += [
        # Video: NVENC hardware encoder
        "-vf",    vf_filter,
        "-c:v",   "h264_nvenc",
        "-preset", NVENC_PRESET,
        "-cq",    NVENC_CQ,

        # Audio: AAC encode
        "-c:a",   "aac",
        "-b:a",   AUDIO_BITRATE,

        # Pixel format for compatibility with all players/phones
        "-pix_fmt", "yuv420p",

        # Metadata
        "-movflags", "+faststart",    # Enables web streaming (moov atom at front)
        "-shortest",
        output_path,
    ]

    logger.info(f"[Renderer] Rendering clip {clip_index + 1}: {output_path}")
    logger.info(
        f"[Renderer] Segment: [{start_s:.2f}s → {end_s:.2f}s] | "
        f"Crop: {crop_w}x{crop_h}+{crop_x}+{crop_y} | "
        f"Encoder: h264_nvenc | Preset: {NVENC_PRESET} | CQ: {NVENC_CQ}"
    )

    try:
        _run_ffmpeg(command)
    except Exception as e:
        err_msg = str(e)
        if "nvenc" in err_msg.lower() or "encoder" in err_msg.lower() or "calledprocesserror" in err_msg.lower():
            logger.warning("[Renderer] ⚠️ NVENC hardware encoder failed (likely outdated Nvidia driver or NVENC API version mismatch).")
            global _nvenc_available
            _nvenc_available = False
            logger.info("[Renderer] Falling back to CPU encoder (libx264)...")
            
            # Construct fallback CPU command
            fallback_command = command.copy()
            
            # Replace h264_nvenc with libx264
            try:
                idx_cv = fallback_command.index("-c:v")
                fallback_command[idx_cv + 1] = "libx264"
            except ValueError:
                pass
                
            # Replace NVENC preset with libx264 preset
            try:
                idx_preset = fallback_command.index("-preset")
                fallback_command[idx_preset + 1] = "medium"
            except ValueError:
                pass
                
            # Replace -cq with -crf
            try:
                idx_cq = fallback_command.index("-cq")
                fallback_command[idx_cq] = "-crf"
                fallback_command[idx_cq + 1] = "23"
            except ValueError:
                pass
                
            logger.info(f"[Renderer] Running fallback CPU command: {' '.join(fallback_command)}")
            _run_ffmpeg(fallback_command)
        else:
            raise e

    logger.info(f"[Renderer] ✅ Clip {clip_index + 1} rendered → {output_path}")
    return output_path


def _run_ffmpeg(command: list) -> None:
    """
    Execute an FFmpeg command and raise a detailed error if it fails.

    Args:
        command: List of command tokens.

    Raises:
        RuntimeError: On non-zero FFmpeg exit code.
    """
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"[Renderer] FFmpeg failed with exit code {e.returncode}.\n"
            f"Command: {' '.join(command)}\n"
            f"FFmpeg stderr:\n{stderr}"
        ) from e


def check_nvenc_available() -> bool:
    """
    Check whether NVENC (h264_nvenc) is available in this FFmpeg build.

    Returns:
        True if NVENC is available, False otherwise.
    """
    global _nvenc_available
    if _nvenc_available is not None:
        return _nvenc_available

    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        output = result.stdout.decode("utf-8", errors="ignore")
        available = "h264_nvenc" in output
        if available:
            # An encoder being listed does not guarantee that the installed
            # driver can initialise it. Test once so every clip does not first
            # suffer a slow, noisy NVENC failure before using the CPU fallback.
            probe = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1",
                    "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            available = probe.returncode == 0
            if not available:
                detail = probe.stderr.decode("utf-8", errors="ignore").strip().splitlines()
                logger.warning(
                    "[Renderer] NVENC is listed but cannot start with this driver; using libx264. %s",
                    detail[-1] if detail else ""
                )
        if available:
            logger.info("[Renderer] ✅ h264_nvenc (NVENC) is available.")
        else:
            logger.warning(
                "[Renderer] ⚠️  h264_nvenc not found. "
                "Falling back to libx264 (CPU encoding)."
            )
        _nvenc_available = available
        return _nvenc_available
    except FileNotFoundError:
        logger.error("[Renderer] ❌ FFmpeg not found in PATH.")
        return False


def _music_mix_filter(clip_duration_s: float) -> str:
    """Return an exact-length, very quiet bed with automatic voice ducking."""
    duration = max(0.1, clip_duration_s)
    fade_in = min(0.8, duration / 3)
    fade_out = min(1.3, duration / 3)
    fade_out_start = max(0.0, duration - fade_out)
    return (
        f"[1:a]aformat=channel_layouts=stereo,atrim=duration={duration:.3f},"
        f"asetpts=N/SR/TB,afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f},"
        f"volume=0.035[bed];"
        f"[bed][0:a]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=300[ducked_bed];"
        f"[0:a][ducked_bed]amix=inputs=2:duration=first:normalize=0:dropout_transition=0,"
        f"alimiter=limit=0.95[mixed_audio]"
    )


def render_clip_cpu_fallback(
    input_video:   str,
    output_path:   str,
    start_ms:      int,
    end_ms:        int,
    crop_coords:   Dict,
    subtitle_path: str,
    music_choice:  Optional[Dict[str, Any]] = None,
    clip_index:    int = 0
) -> str:
    """
    CPU fallback renderer using libx264 — used if NVENC is unavailable.
    Same as render_clip() but with -c:v libx264 and -crf 23.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    start_s = start_ms / 1000.0
    end_s   = end_ms   / 1000.0

    crop_w = crop_coords["crop_w"]
    crop_h = crop_coords["crop_h"]
    crop_x = crop_coords["crop_x"]

    safe_sub_path = subtitle_path.replace("\\", "/").replace(":", "\\:")
    vf_filter = (
        f"crop={crop_w}:{crop_h}:{crop_x}:0,"
        f"scale=1080:1920,"
        f"ass='{safe_sub_path}'"
    )

    command = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-to", f"{end_s:.3f}",
        "-i", input_video,
    ]

    if music_choice:
        command += [
            "-stream_loop", "-1",
            "-ss", f"{float(music_choice['start_s']):.3f}",
            "-i", music_choice["path"],
            "-filter_complex", _music_mix_filter(end_s - start_s),
            "-map", "0:v:0",
            "-map", "[mixed_audio]",
        ]

    command += [
        "-vf", vf_filter,
        "-c:v", "libx264",   # CPU software encoder
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]

    logger.info(f"[Renderer] (CPU fallback) Rendering clip {clip_index + 1}: {output_path}")
    _run_ffmpeg(command)
    logger.info(f"[Renderer] ✅ Clip {clip_index + 1} rendered (CPU) → {output_path}")
    return output_path
