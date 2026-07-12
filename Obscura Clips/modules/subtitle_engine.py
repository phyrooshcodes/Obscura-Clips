# ============================================================
# subtitle_engine.py — Module 5: Kinetic Subtitle Generator
# Hardware Target: CPU — Pure Python String Engine
# Purpose: Transform word-level timestamps into TikTok-style
#          rapid-fire ASS subtitle files with 2-3 words per
#          frame, yellow bold text, black outline, center-mid.
#          0% GPU usage — pure algorithmic string logic.
# ============================================================

import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# ─── Kinetic Subtitle Configuration ─────────────────────────
MAX_CHARS_PER_GROUP  = 16     # Max characters before forcing a new group
MAX_WORDS_PER_GROUP  = 3      # Max words per subtitle frame
MIN_SUBTITLE_DURATION = 0.25  # Seconds — minimum display time per group

# ─── ASS Style Constants ─────────────────────────────────────────────────────────
# ASS Colour format: &HAABBGGRR  (alpha, blue, green, red in hex)
# Bright Yellow = &H0000FFFF (A=00, B=00, G=FF, R=FF)
# Black Outline  = &H00000000
# Shadow         = &H80000000 (50% transparent black)
#
# Alignment codes (numpad layout):
#  7=top-left   8=top-center    9=top-right
#  4=mid-left   5=mid-center    6=mid-right   ← Alignment=5 for center-middle
#  1=bot-left   2=bot-center    3=bot-right

ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,Arial,90,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,0,5,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text

"""

# Alignment=5 is center-middle (numpad 5)
# Fontsize=90 for large readable text on 1080x1920 canvas
# Outline=5 for thick black stroke
# PrimaryColour=&H0000FFFF = bright yellow


def generate_ass_subtitles(
    words: List[Dict],
    clip_start_s: float,
    clip_end_s: float,
    output_path: str
) -> str:
    """
    Generate a TikTok-style ASS subtitle file for a clip segment.

    Args:
        words:        Full word-timestamp list from transcriber.
        clip_start_s: Clip start time in SECONDS (float).
        clip_end_s:   Clip end time in SECONDS (float).
        output_path:  Where to save the .ass file.

    Returns:
        Path to the generated ASS file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Filter words that fall within this clip's time window
    clip_words = [
        w for w in words
        if w["start"] >= clip_start_s and w["end"] <= clip_end_s
    ]

    if not clip_words:
        logger.warning(
            f"[SubtitleEngine] No words found in range "
            f"[{clip_start_s:.2f}s → {clip_end_s:.2f}s]. "
            "Creating empty subtitle file."
        )
        _write_ass(output_path, [])
        return output_path

    # Normalize timestamps: make them relative to clip start
    for w in clip_words:
        w = dict(w)  # Don't mutate the original

    normalized_words = [
        {
            "word":  w["word"],
            "start": round(w["start"] - clip_start_s, 3),
            "end":   round(w["end"]   - clip_start_s, 3)
        }
        for w in clip_words
    ]

    # Group words into kinetic subtitle frames
    groups = _group_words_kinetic(normalized_words)

    logger.info(
        f"[SubtitleEngine] {len(clip_words)} words → "
        f"{len(groups)} subtitle groups for clip "
        f"[{clip_start_s:.1f}s → {clip_end_s:.1f}s]"
    )

    _write_ass(output_path, groups)
    logger.info(f"[SubtitleEngine] ✅ ASS file written → {output_path}")
    return output_path


def _group_words_kinetic(words: List[Dict]) -> List[Dict]:
    """
    Split word list into rapid-fire 2-3 word groups.
    Each group contains the original word dictionaries.

    Rules:
    - Max MAX_WORDS_PER_GROUP words per group
    - Max MAX_CHARS_PER_GROUP chars per group (force break if exceeded)
    - Minimum MIN_SUBTITLE_DURATION seconds display time

    Returns:
    Convert list of words to list of group dicts:
        [{"words": [...], "start": 0.24, "end": 0.90}, ...]
    """
    groups = []
    i = 0

    while i < len(words):
        group_words_data = []
        group_chars = 0
        group_start = words[i]["start"]
        group_end   = words[i]["end"]

        while i < len(words) and len(group_words_data) < MAX_WORDS_PER_GROUP:
            w_data = words[i]
            word = w_data["word"]
            candidate_chars = group_chars + len(word) + (1 if group_words_data else 0)

            if group_words_data and candidate_chars > MAX_CHARS_PER_GROUP:
                break  # This word goes in the next group

            group_words_data.append(w_data)
            group_chars    = candidate_chars
            group_end      = w_data["end"]
            i += 1

        duration = group_end - group_start

        # Enforce minimum display duration
        if duration < MIN_SUBTITLE_DURATION:
            group_end = group_start + MIN_SUBTITLE_DURATION

        groups.append({
            "words": group_words_data,
            "start": group_start,
            "end":   group_end
        })

    return groups


def _write_ass(output_path: str, groups: List[Dict]) -> None:
    """
    Write the ASS file generating dynamic word-by-word slide-up and fade-in
    animations. Uses alpha layer overrides for alignment matching.

    Args:
        output_path: File path to write.
        groups:      List of group dicts.
    """
    lines = [ASS_HEADER]

    for group in groups:
        group_start = group["start"]
        group_end   = group["end"]
        group_words = group["words"]
        
        if not group_words:
            continue
            
        W_texts = [w["word"].upper() for w in group_words]
        
        for j, w in enumerate(group_words):
            w_start = w["start"]
            w_end   = w["end"]
            
            # Find start of next word or group end
            next_start = group_words[j+1]["start"] if j < len(group_words) - 1 else group_end
            
            # 1. ANIMATION PHASE: Slides up from y=985 to y=960 and fades in (150ms max)
            anim_dur = min(0.150, next_start - w_start)
            if anim_dur > 0.01:
                start_ts = _seconds_to_ass_time(w_start)
                end_ts   = _seconds_to_ass_time(w_start + anim_dur)
                
                # Previous words: invisible (alpha=FF)
                pre_part = ""
                if j > 0:
                    pre_part = "{\\alpha&HFF&}" + " ".join(W_texts[:j]) + " "
                    
                # Current word: visible (alpha=00), bright yellow (c=00FFFF)
                active_part = "{\\alpha&H00&\\c&H00FFFF&}" + W_texts[j]
                
                # Next words: invisible (alpha=FF)
                post_part = ""
                if j < len(W_texts) - 1:
                    post_part = " {\\alpha&HFF&}" + " ".join(W_texts[j+1:])
                    
                text = "{\\move(540,985,540,960,0,150)\\fad(150,0)}" + pre_part + active_part + post_part
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")
                
            # 2. STATIC PHASE: Word stays highlighted at y=960 until next word starts
            static_start = w_start + anim_dur
            if next_start - static_start > 0.01:
                start_ts = _seconds_to_ass_time(static_start)
                end_ts   = _seconds_to_ass_time(next_start)
                
                # Previous words: visible (alpha=00), white color (c=FFFFFF)
                pre_part = ""
                if j > 0:
                    pre_part = "{\\alpha&H00&\\c&HFFFFFF&}" + " ".join(W_texts[:j]) + " "
                    
                # Current word: visible (alpha=00), bright yellow (c=00FFFF)
                active_part = "{\\alpha&H00&\\c&H00FFFF&}" + W_texts[j]
                
                # Next words: invisible (alpha=FF)
                post_part = ""
                if j < len(W_texts) - 1:
                    post_part = " {\\alpha&HFF&}" + " ".join(W_texts[j+1:])
                    
                text = "{\\pos(540,960)}" + pre_part + active_part + post_part
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")
                
        # 3. POST-GROUP PAUSE: Render entire phrase statically in white
        last_w_end = group_words[-1]["end"]
        if group_end - last_w_end > 0.05:
            start_ts = _seconds_to_ass_time(last_w_end)
            end_ts   = _seconds_to_ass_time(group_end)
            text     = "{\\pos(540,960)\\c&HFFFFFF&}" + " ".join(W_texts)
            lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _seconds_to_ass_time(seconds: float) -> str:
    """
    Convert a float seconds value to ASS timestamp format: H:MM:SS.cc
    (hundredths of a second, not milliseconds)

    Args:
        seconds: Time in seconds.

    Returns:
        ASS time string, e.g. "0:00:03.24"
    """
    seconds  = max(0.0, seconds)
    hours    = int(seconds // 3600)
    minutes  = int((seconds % 3600) // 60)
    secs     = seconds % 60
    centisec = int(round((secs - int(secs)) * 100))
    return f"{hours}:{minutes:02d}:{int(secs):02d}.{centisec:02d}"
