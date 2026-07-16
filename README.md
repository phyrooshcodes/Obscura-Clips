# ✦ Obscura Clips
### Zero-Strain Local-Hybrid AI Video Clipper
> GPU-Accelerated & Thermally Optimized

---

## What It Does

Obscura Clips takes any long-form video (such as podcasts, interviews, or lectures) and automatically produces viral-ready **9:16 vertical clips** with:

- 🎙️ **GPU AI Transcription** — `faster-whisper` (runs on CUDA with float16 fallback to CPU INT8)
- 🧠 **Smart Hook Detection** — **Llama 3.3 70B** with fallback to **Qwen 122B / 397B** via NVIDIA NIM cloud API (finds actual 10/10 standalone stories)
- 👁️ **Face-Tracked Cropping** — OpenCV Haar Cascades (keeps the speaker centered in the 9:16 crop)
- 💬 **Kinetic Subtitles** — TikTok-style word-sliding opacity animation
- 🎵 **Curated Background Music** — Intelligent ambient/lofi/synth music selection with automated speech-ducking sidechain compression
- 🚀 **NVENC GPU Encoding** — Offloads video rendering completely to the RTX GPU hardware encoding block

---

## Hardware & System Requirements

| Stage | Hardware Target | Details |
|---|---|---|
| Audio Demux | CPU (disk I/O) | Extremely fast audio extraction |
| ASR Transcription | **GPU (CUDA)** | Uses `faster-whisper` with local CUDA DLL runtime injection |
| Hook Detection | **☁ NVIDIA NIM** | Llama 3.3 70B with Qwen fallback runs in the cloud to select premium clips |
| Face Tracking | CPU OpenCV | Auto-tracks speaker movement to keep them centered |
| Audio Mixing | CPU FFmpeg | Loops, fades, and ducks background music behind vocals |
| Final Render | **GPU NVENC** | GPU-accelerated video encoding (100+ FPS, keeps shaders cool) |

---

## Setup Instructions

### 1. External System Prerequisites
1. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add `C:\ffmpeg\bin` to your system `PATH`.
2. **NVIDIA GPU Drivers**: Ensure your Nvidia drivers are updated. The pipeline auto-configures and runs Whisper and NVENC on CUDA.
3. **NVIDIA NIM API Key**: 
   * Sign up for a free account at [NVIDIA build](https://build.nvidia.com/) to get free API credits.
   * Rename `.env.example` in this folder to `.env`.
   * Add your API key:
     ```env
     NVIDIA_API_KEY=nvapi-XXXXXX
     ```

### 2. How to Run (One-Click)
Simply double-click **`run_windows.bat`**. The script will automatically:
1. Detect Python and FFmpeg.
2. Initialize the Python virtual environment (`venv`) if it's the first run and install all libraries (including CUDA runtime packages).
3. Start the Web Dashboard server.
4. Open the app automatically in your browser at **`http://localhost:7842`**.

---

## Command Line Usage (Advanced)

If you prefer to run it via CLI:

```bash
# Activate venv
venv\Scripts\activate

# Basic run (takes defaults: small Whisper model, max 10 clips)
python local_clipping_pipeline.py --input video.mp4

# Run with custom max clips (up to 30) and custom background music
python local_clipping_pipeline.py --input video.mp4 --max-clips 15 --music lofi
```

### All Flags

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | *(required)* | Path to input video |
| `--output-dir` / `-o` | `output/` | Where rendered clips are saved |
| `--model` / `-m` | `small` | Whisper model: `tiny`, `base`, `small` (default) |
| `--language` / `-l` | auto | ISO 639-1 language code |
| `--max-clips` | `10` | Max number of clips to generate (1-30) |
| `--music` | `none` | Music vibe: `none`, `auto`, `ambient`, `lofi`, `focus` |
| `--keep-temp` | false | Keep `temp/` folder (useful for debugging) |

---

## Project Structure

```
Obscura Clips/
├── run_windows.bat          ← Double click to run the app
├── .env.example             ← Rename to .env and enter NVIDIA key
├── requirements.txt
├── README.md
├── modules/
│   ├── audio_demux.py       ← Stage 1: Demux audio
│   ├── transcriber.py       ← Stage 2: GPU/CPU Whisper Transcription
│   ├── hook_detector.py     ← Stage 3: Llama & Qwen NIM Hook Detection
│   ├── face_tracker.py      ← Stage 4: OpenCV face tracking
│   ├── subtitle_engine.py   ← Stage 5: TikTok sliding-opacity ASS subtitle gen
│   └── renderer.py          ← Stage 6: FFmpeg NVENC render & Audio sidechain
├── output/                  ← Final clips saved here (auto-created)
└── temp/                    ← Temporary audio/word cache (auto-cleaned)
```
