# ============================================================
# hook_detector.py — Module 3: Viral Hook Detection
# Hardware Target: ☁ Cloud — NVIDIA NIM API (DGX H100)
# Model: meta/llama-3.3-70b-instruct
# Purpose: Analyze the full transcript and identify the most
#          viral, hook-worthy moments with precise timestamps.
#          Offloads 40GB+ VRAM requirement to the cloud.
# ============================================================

import json
import logging
import re
from typing import List, Dict, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)

import os

# Load from .env file in the project root if it exists
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_root_dir, ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Failed to read .env file: {e}")

# ─── NVIDIA NIM API Configuration ───────────────────────────
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_MODEL       = "qwen/qwen3.5-397b-a17b"

# ─── Prompt Template ────────────────────────────────────────
HOOK_SYSTEM_PROMPT = """You are an elite viral video editor for self-improvement content (like Huberman Lab, Alex Hormozi, Ali Abdaal, Iman Gadzhi). You have 10 years of experience creating viral TikTok/YouTube Shorts clips that get millions of views.

Your job: Read the ENTIRE timestamped transcript below and find the absolute BEST standalone moments that would make someone stop scrolling.

## WHAT MAKES A CLIP GO VIRAL (you MUST follow this):

1. **COMPLETE STANDALONE STORY**: Each clip MUST tell a complete mini-story or teach a complete idea. The viewer should understand the clip WITHOUT needing any outside context. If someone watches ONLY this 30-90 second clip, they should walk away having learned something specific or felt something powerful.

2. **STRONG HOOK IN FIRST 5 SECONDS**: The clip must open with something that immediately grabs attention:
   - A bold claim: "Most people don't realize that..."
   - A counterintuitive fact: "Cold water actually increases dopamine by 250%..."
   - A relatable problem: "You know that feeling when you can't focus on anything..."
   - A direct challenge: "If you're doing this, you're destroying your motivation..."

3. **EMOTIONAL ARC**: Great clips have a beginning (problem/hook), middle (explanation/story), and end (payoff/lesson). Do NOT cut a clip in the middle of an explanation.

4. **ACTIONABLE TAKEAWAY**: The best clips end with something the viewer can DO or REMEMBER. A fact, a technique, a protocol, a mindset shift.

## CRITICAL MISTAKES TO AVOID (clips that do these are WORTHLESS):

❌ DO NOT select moments that are just introductions or transitions ("So let's talk about..." or "Moving on to...")
❌ DO NOT select moments where the speaker is referencing something they said earlier that the clip viewer won't have context for ("As I mentioned before..." or "Going back to what we discussed...")  
❌ DO NOT select moments that end mid-thought or mid-explanation — the clip MUST have a satisfying conclusion
❌ DO NOT select sponsor reads, podcast intros, or meta-commentary about the show itself
❌ DO NOT select clips shorter than 30 seconds — they lack enough substance
❌ DO NOT select moments that require visual aids (charts, images) to make sense — this is AUDIO-FIRST content

## WHAT TO LOOK FOR (these are GOLD):

✅ Specific scientific facts with numbers ("Dopamine increased by 250% above baseline")
✅ Personal stories or anecdotes that illustrate a point
✅ Practical protocols or step-by-step techniques the viewer can apply immediately
✅ Surprising revelations that challenge conventional wisdom
✅ Powerful analogies or metaphors that reframe how people think
✅ Emotional moments where the speaker gets passionate about something
✅ Before/after transformations or case studies

## TIMESTAMP ACCURACY:
- You are given timestamps in [MM:SS.mm] format for each sentence
- Use these timestamps to set PRECISE start_ms and end_ms values
- Convert [MM:SS.mm] → milliseconds: start_ms = (MM * 60 + SS) * 1000 + mm * 10
- Start the clip 2-3 seconds BEFORE the hook sentence to give breathing room
- End the clip at a natural sentence boundary — NEVER mid-sentence

## OUTPUT FORMAT:
Return ONLY a raw JSON array. No markdown fences. No explanations. No commentary.

[
  {
    "start_ms": 12400,
    "end_ms": 58200,
    "hook_score": 9.2,
    "title": "Short punchy clip title (max 8 words)",
    "reason": "One sentence explaining why this specific clip would go viral and what complete idea it teaches.",
    "music_mood": "calm_focus",
    "music_energy": 1
  }
]

For music_mood use ONLY: warm_reflection, calm_focus, measured_momentum.
music_energy: 1 (subtle), 2 (moderate), 3 (driving). For self-improvement, prefer 1 or 2.
Sort by hook_score descending. Be RUTHLESS — only select moments that are truly 8/10 or higher."""

HOOK_USER_TEMPLATE = """Here is the COMPLETE timestamped transcript of a self-improvement video.
Each line starts with [MM:SS.mm] showing when that sentence begins.

READ THE ENTIRE TRANSCRIPT CAREFULLY before selecting clips.
Think about which moments would make someone STOP SCROLLING on TikTok.

--- TRANSCRIPT START ---
{transcript}
--- TRANSCRIPT END ---

Total video duration: {duration_str}

Now identify the top {max_clips} viral clip moments (or fewer if the content doesn't have that many truly great moments). Remember:
- Each clip MUST be a COMPLETE standalone idea (30-90 seconds)
- Each clip MUST have a strong opening hook
- Each clip MUST have a satisfying conclusion — NOT cut off mid-thought
- Use the [MM:SS.mm] timestamps to calculate precise start_ms and end_ms values
- Be RUTHLESS in quality — only select truly viral-worthy moments

Return ONLY the JSON array."""


# ─── Client Initialization ──────────────────────────────────
def _get_client() -> OpenAI:
    key = os.environ.get("NVIDIA_API_KEY", NVIDIA_API_KEY)
    if not key:
        raise ValueError(
            "\n[ERROR] NVIDIA_API_KEY is not set!\n"
            "Please create a file named '.env' in your project root containing:\n"
            "NVIDIA_API_KEY=nvapi-YOUR_API_KEY_HERE\n"
            "Or set it as an environment variable."
        )
    return OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=key
    )


def adjust_clip_to_sentences(
    words: List[Dict],
    start_ms: int,
    end_ms: int,
    video_duration_seconds: float,
    max_expansion_s: float = 8.0
) -> Tuple[int, int]:
    """
    Snap start_ms and end_ms to the closest actual words in the transcript,
    then adjust backward and forward to find natural sentence boundaries
    (ending in '.', '?', '!') or natural gaps (>1.0s) between words.
    """
    if not words:
        return start_ms, end_ms
        
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    
    # Find word closest to start_s
    start_idx = min(range(len(words)), key=lambda i: abs(words[i]["start"] - start_s))
    # Find word closest to end_s
    end_idx = min(range(len(words)), key=lambda i: abs(words[i]["end"] - end_s))
    
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
        
    orig_start_s = words[start_idx]["start"]
    orig_end_s = words[end_idx]["end"]
    
    # 1. Walk start_idx backward to find the beginning of the sentence
    curr_start_idx = start_idx
    for i in range(start_idx - 1, -1, -1):
        if orig_start_s - words[i]["start"] > max_expansion_s:
            break
            
        word_text = words[i]["word"].strip()
        ends_with_punc = any(word_text.endswith(p) for p in (".", "?", "!"))
        large_gap = (words[i+1]["start"] - words[i]["end"]) > 1.0
        
        if ends_with_punc or large_gap:
            curr_start_idx = i + 1
            break
            
    # 2. Walk end_idx forward to find the end of the sentence
    curr_end_idx = end_idx
    for i in range(end_idx, len(words)):
        if words[i]["end"] - orig_end_s > max_expansion_s:
            break
            
        word_text = words[i]["word"].strip()
        ends_with_punc = any(word_text.endswith(p) for p in (".", "?", "!"))
        
        large_gap = False
        if i < len(words) - 1:
            large_gap = (words[i+1]["start"] - words[i]["end"]) > 1.0
            
        if ends_with_punc or large_gap or i == len(words) - 1:
            curr_end_idx = i
            break
            
    new_start_ms = int(words[curr_start_idx]["start"] * 1000)
    # Add a 150ms cushion at the end to prevent syllable clipping
    new_end_ms = min(int(words[curr_end_idx]["end"] * 1000) + 150, int(video_duration_seconds * 1000))
    
    return new_start_ms, new_end_ms


def _validate_and_clamp_clips(
    clips: List[Dict],
    video_duration_seconds: float,
    words: List[Dict]
) -> List[Dict]:
    """Validate, snap to sentence boundaries, and clamp end timestamps of clips."""
    max_ms = int(video_duration_seconds * 1000)
    valid_clips = []
    for clip in clips:
        start = clip.get("start_ms", 0)
        end = clip.get("end_ms", 0)
        
        # Snap and adjust clip to actual sentence boundaries for clean cuts
        start, end = adjust_clip_to_sentences(words, start, end, video_duration_seconds)
        
        # Discard clips that start beyond video duration
        if start >= max_ms or start < 0:
            logger.warning(f"[HookDetector] Discarding clip with out-of-bounds start: {clip.get('title', 'Untitled')} ({start/1000:.1f}s)")
            continue
            
        # Clamp end to video duration
        end = min(end, max_ms)
        
        # Discard clips where start >= end after clamping
        if start >= end:
            logger.warning(f"[HookDetector] Discarding clip with invalid range: {clip.get('title', 'Untitled')} ({start/1000:.1f}s -> {end/1000:.1f}s)")
            continue

        # Discard clips that are too short (under 30s) after clamping/snapping
        if (end - start) < 30000:
            logger.warning(f"[HookDetector] Discarding clip that is too short ({(end - start)/1000:.1f}s): {clip.get('title', 'Untitled')}")
            continue
            
        clip["start_ms"] = start
        clip["end_ms"] = end
        valid_clips.append(clip)
    return valid_clips


# ─── Main Hook Detection Function ───────────────────────────
def detect_hooks(
    words: List[Dict],
    video_duration_seconds: float,
    max_clips: int = 10
) -> List[Dict]:
    """
    Query the smartest model with the full transcript first. If it succeeds,
    return those hooks. If it fails or times out, fall back to the parallel chunked workflow.
    """
    import concurrent.futures

    if not words:
        return []

    # A. First Attempt: Full transcript query using smartest models
    logger.info("[HookDetector] Attempting single smartest model query on full transcript for 10/10 quality...")
    from modules.transcriber import words_to_timed_transcript
    full_tx = words_to_timed_transcript(words)
    
    user_message = HOOK_USER_TEMPLATE.format(
        transcript=full_tx,
        duration_str=f"{int(video_duration_seconds // 60):02d}:{int(video_duration_seconds % 60):02d}",
        max_clips=max_clips
    )
    
    smartest_models = [
        "qwen/qwen3.5-397b-a17b",              # Primary: Qwen3.5 397B (mixture-of-experts titan)
        "qwen/qwen3.5-122b-a10b",              # Fallback 1: Qwen3.5 122B
        "meta/llama-3.3-70b-instruct",          # Fallback 2: Llama 3.3 70B
    ]
    
    client = _get_client()
    for m in smartest_models:
        try:
            logger.info(f"[HookDetector] Querying full transcript with smartest model: {m} ...")
            completion = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": HOOK_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message}
                ],
                temperature=0.2,       # Low temperature = more focused, less random
                max_tokens=4096,       # Generous output for detailed JSON with reasons
                top_p=0.85,
                timeout=240.0          # 4-minute timeout for full-transcript digesting
            )
            raw_response = completion.choices[0].message.content.strip()
            raw_clips = _parse_json_response(raw_response)
            if raw_clips and len(raw_clips) >= 1:
                valid_clips = _validate_and_clamp_clips(raw_clips, video_duration_seconds, words)
                if len(valid_clips) >= 1:
                    logger.info(f"[HookDetector] ✅ Smart single model ({m}) successfully returned {len(valid_clips)} premium hooks.")
                    # Sort and limit
                    valid_clips = sorted(valid_clips, key=lambda x: x.get("hook_score", 0.0), reverse=True)[:max_clips]
                    
                    # Print summary
                    logger.info(f"[HookDetector] Final selected clips:")
                    for i, clip in enumerate(valid_clips, 1):
                        logger.info(f"  Clip {i}: [{clip['start_ms']/1000:.1f}s → {clip['end_ms']/1000:.1f}s] Score={clip.get('hook_score','?')} | {clip.get('title','Untitled')}")
                    return valid_clips
        except Exception as e:
            logger.warning(f"[HookDetector] Full-transcript query failed or timed out with {m}: {e}. Trying next model...")

    # B. Second Attempt (Fallback): Split words into 10-minute chunks with 1-minute overlap
    logger.warning("[HookDetector] ⚠️ Full-transcript query failed on all smart models. Falling back to parallel chunked workflow...")
    
    chunk_size = 600.0  # 10 minutes in seconds
    overlap = 60.0      # 1 minute in seconds
    
    chunks = []
    start_s = 0.0
    while start_s < video_duration_seconds:
        end_s = min(start_s + chunk_size, video_duration_seconds)
        chunk_words = [w for w in words if start_s <= w["start"] < end_s]
        if chunk_words:
            chunks.append({
                "start_s": start_s,
                "end_s": end_s,
                "words": chunk_words
            })
        if end_s >= video_duration_seconds:
            break
        start_s += (chunk_size - overlap)

    logger.info(f"[HookDetector] Video length: {video_duration_seconds:.1f}s. Processing in {len(chunks)} parallel chunks.")

    available_models = [
        "qwen/qwen3.5-397b-a17b",
        "qwen/qwen3.5-122b-a10b",
        "meta/llama-3.3-70b-instruct",
    ]

    all_raw_clips = []

    # 2. Worker function to query a single chunk
    def process_chunk(idx, chunk):
        import time
        if idx > 0:
            stagger = idx * 4.0
            logger.info(f"[HookDetector] Staggering Chunk {idx+1} start by {stagger:.1f}s to avoid rate limits...")
            time.sleep(stagger)

        from modules.transcriber import words_to_timed_transcript
        timed_tx = words_to_timed_transcript(chunk["words"])

        start_min = int(chunk["start_s"] // 60)
        start_sec = int(chunk["start_s"] % 60)
        end_min = int(chunk["end_s"] // 60)
        end_sec = int(chunk["end_s"] % 60)
        duration_str = f"{start_min:02d}:{start_sec:02d} to {end_min:02d}:{end_sec:02d}"

        # Per-chunk we ask for a proportional number of clips
        chunk_fraction = (chunk["end_s"] - chunk["start_s"]) / video_duration_seconds
        chunk_max = max(2, round(max_clips * chunk_fraction))

        user_message = HOOK_USER_TEMPLATE.format(
            transcript=timed_tx,
            duration_str=duration_str,
            max_clips=chunk_max
        )

        # Distribute model selection round-robin
        preferred_model = available_models[idx % len(available_models)]
        chunk_models = [preferred_model] + [m for m in available_models if m != preferred_model]

        client = _get_client()
        completion = None
        last_err = None

        for m in chunk_models:
            try:
                logger.info(f"[HookDetector] Chunk {idx+1}/{len(chunks)} ({duration_str}) querying model: {m} ...")
                completion = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": HOOK_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_message}
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                    top_p=0.85,
                    timeout=180.0
                )
                logger.info(f"[HookDetector] Chunk {idx+1} successfully completed with {m}")
                break
            except Exception as e:
                logger.warning(f"[HookDetector] Chunk {idx+1} failed with {m}: {e}")
                last_err = e
                continue

        if not completion:
            raise RuntimeError(f"Chunk {idx+1} failed on all models. Last error: {last_err}")

        raw_response = completion.choices[0].message.content.strip()
        return _parse_json_response(raw_response)

    # 3. Execute queries concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as executor:
        futures = {executor.submit(process_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
        for future in concurrent.futures.as_completed(futures):
            chunk_idx = futures[future]
            try:
                chunk_clips = future.result()
                all_raw_clips.extend(chunk_clips)
            except Exception as e:
                logger.error(f"[HookDetector] ❌ Chunk {chunk_idx+1} failed processing: {e}")

    # 4. Deduplicate and merge clips
    clips = _deduplicate_clips(all_raw_clips, max_clips)

    # Validate and clamp clip timestamps to prevent FFmpeg out-of-bound crashes
    clips = _validate_and_clamp_clips(clips, video_duration_seconds, words)

    logger.info(f"[HookDetector] ✅ Deduplicated down to {len(clips)} viral clips across all chunks.")
    for i, clip in enumerate(clips, 1):
        start_s = clip["start_ms"] / 1000
        end_s   = clip["end_ms"]   / 1000
        logger.info(
            f"  Clip {i}: [{start_s:.1f}s → {end_s:.1f}s] "
            f"Score={clip.get('hook_score','?')} | {clip.get('title','Untitled')}"
        )

    return clips


def _deduplicate_clips(clips: List[Dict], max_clips: int) -> List[Dict]:
    """
    Remove clips that overlap significantly, keeping the ones with higher hook scores.
    """
    sorted_clips = sorted(clips, key=lambda c: c.get("hook_score", 0), reverse=True)
    deduped = []

    for c in sorted_clips:
        start = c.get("start_ms")
        end = c.get("end_ms")
        if start is None or end is None:
            continue

        overlap_found = False
        for accepted in deduped:
            a_start = accepted["start_ms"]
            a_end = accepted["end_ms"]

            # Calculate intersection window
            intersect_start = max(start, a_start)
            intersect_end = min(end, a_end)

            if intersect_end > intersect_start:
                intersect_len = intersect_end - intersect_start
                len_c = end - start
                len_a = a_end - a_start

                # If overlap exceeds 40% of either clip length, consider it a duplicate
                if (intersect_len / len_c > 0.4) or (intersect_len / len_a > 0.4):
                    overlap_found = True
                    break

        if not overlap_found:
            deduped.append(c)

    return sorted(deduped, key=lambda c: c.get("hook_score", 0), reverse=True)[:max_clips]


def _parse_json_response(raw: str) -> List[Dict]:
    """
    Robustly parse a JSON array from the LLM response.
    Handles cases where the model wraps JSON in markdown fences.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    cleaned = cleaned.strip("`").strip()

    # Find the JSON array boundaries
    start_idx = cleaned.find("[")
    end_idx   = cleaned.rfind("]")

    if start_idx == -1 or end_idx == -1:
        raise RuntimeError(
            f"[HookDetector] No JSON array found in LLM response.\n"
            f"Raw response:\n{raw}"
        )

    json_str = cleaned[start_idx : end_idx + 1]

    try:
        clips = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"[HookDetector] JSON parse error: {e}\n"
            f"Attempted to parse:\n{json_str}"
        ) from e

    if not isinstance(clips, list):
        raise RuntimeError("[HookDetector] Expected a JSON array but got something else.")

    return clips
