# ============================================================
# transcriber.py — Module 2: ASR Transcription
# Hardware Target: CPU (Ryzen 7) — faster-whisper INT8
# Purpose: Transcribe audio to text with word-level timestamps.
#          Uses CTranslate2 INT8 quantization (<200MB RAM,
#          0MB VRAM).
# ============================================================

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    language: str = None
) -> List[Dict]:
    """
    Transcribe an audio file using faster-whisper on CPU (INT8).

    Args:
        audio_path:  Path to the 16kHz mono WAV file.
        model_size:  Whisper model size. Options: "tiny", "base", "small".
                     "base"  → fastest, good for clear speech.
                     "small" → more accurate, ~2x slower.
        language:    ISO 639-1 code (e.g. "en"). None = auto-detect.

    Returns:
        A flat list of word-timestamp dicts:
        [
            {"word": "Hello", "start": 0.24, "end": 0.56},
            {"word": "world", "start": 0.60, "end": 0.90},
            ...
        ]
        All times are in SECONDS (float).
    """
    # Lazy import to keep startup fast if module is not used
    from faster_whisper import WhisperModel
    import os
    import sys
    from pathlib import Path

    # Dynamically inject local CUDA runtime library paths into Windows DLL search path
    try:
        venv_site = Path(sys.executable).parent.parent / "Lib" / "site-packages"
        nvidia_dir = venv_site / "nvidia"
        if nvidia_dir.exists():
            for sub in nvidia_dir.iterdir():
                bin_dir = sub / "bin"
                if bin_dir.exists():
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
                    # Also tell Python 3.8+ to search this folder for DLLs
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(str(bin_dir))
    except Exception as e:
        logger.warning(f"[Transcriber] Failed to add local CUDA paths: {e}")

    model = None
    try:
        logger.info(f"[Transcriber] Attempting to load faster-whisper model: '{model_size}' on GPU (cuda, float16)...")
        model = WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16"
        )
        logger.info("[Transcriber] ✅ Whisper initialized on GPU CUDA successfully!")
    except Exception as e:
        logger.warning(f"[Transcriber] GPU acceleration failed: {e}. Falling back to CPU (int8)...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )

    logger.info(f"[Transcriber] Transcribing: {audio_path} ...")

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,   # Critical: per-word timing for subtitle engine
        language=language,
        beam_size=5,            # Balanced accuracy/speed
        vad_filter=True,        # Voice Activity Detection — skips silence automatically
        vad_parameters={
            "min_silence_duration_ms": 500
        }
    )

    logger.info(
        f"[Transcriber] Detected language: '{info.language}' "
        f"(probability: {info.language_probability:.2f})"
    )

    # Flatten all segment words into a single ordered list
    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                words.append({
                    "word": word.word.strip(),
                    "start": round(word.start, 3),
                    "end":   round(word.end,   3)
                })

    logger.info(f"[Transcriber] ✅ Transcribed {len(words)} words total.")
    return words


def words_to_full_text(words: List[Dict]) -> str:
    """
    Reconstruct a full plain-text transcript from the word list.
    Used to build the LLM prompt in hook_detector.

    Args:
        words: List of word-timestamp dicts from transcribe_audio().

    Returns:
        A single string with all words joined by spaces.
    """
    return " ".join(w["word"] for w in words)


def words_to_timed_transcript(words: List[Dict]) -> str:
    """
    Build a timestamped transcript string for the LLM hook detector,
    grouping words into clean sentences/segments to prevent huge verbose
    prompt payloads and 504 Gateway Timeouts on the LLM API.

    Args:
        words: List of word-timestamp dicts.

    Returns:
        Timestamped string for LLM prompt injection.
    """
    if not words:
        return ""

    lines = []
    current_group = []
    group_start = words[0]["start"]

    for i, w in enumerate(words):
        word_text = w["word"].strip()
        current_group.append(word_text)

        # Check for sentence ending punctuation
        clean_word = word_text.rstrip(")\"']}`")
        ends_with_punc = bool(clean_word and clean_word[-1] in (".", "?", "!"))

        # Check for pause gap (>1.5s) between words
        large_gap = False
        if i < len(words) - 1:
            gap = words[i+1]["start"] - w["end"]
            if gap > 1.5:
                large_gap = True

        # Keep groups to a maximum of 25 words to maintain timestamp granularity
        too_long = len(current_group) >= 25

        if ends_with_punc or large_gap or too_long or i == len(words) - 1:
            minutes = int(group_start // 60)
            seconds = group_start % 60
            text = " ".join(current_group)
            lines.append(f"[{minutes:02d}:{seconds:05.2f}] {text}")

            if i < len(words) - 1:
                group_start = words[i+1]["start"]
                current_group = []

    return "\n".join(lines)
