# GITHUB RELEASE GUIDE & USER INSTRUCTIONS

Copy and paste the markdown content below directly into your GitHub Release Description or repository download page:

```markdown
# ✦ Obscura Clips v1.0.0

An automated, hybrid-AI vertical video clipping pipeline optimized to run natively on consumer Windows laptops (built and tested on Ryzen 7 + RTX 3050 Laptop GPU).

## 🚀 Key Features
- **GPU-Accelerated Transcription**: Uses `faster-whisper` on CUDA float16 for up to 10x faster speech processing.
- **Titan-class AI Hook Detection**: Leverages **Qwen 3.5 397B** via the cloud (NVIDIA NIM) to choose highly engaging standalone clips.
- **Smart Framing**: Crop and center the speaker in 9:16 vertical frames automatically using MediaPipe.
- **Kinetic Subtitles**: Burn in clean, high-impact subtitles with sliding-opacity animations.
- **Ducked Background Music**: Choose ambient, lofi, or synth instrumental beds that dynamically duck under spoken vocals.

---

## 🛠️ How to Download and Run

### 1. Download the Project
1. Download the **Source code (zip)** below.
2. Extract the ZIP to a folder on your computer (e.g. `C:\ObscuraClips`).

### 2. Install Prerequisites (External)
Before starting, ensure you have these installed on your Windows machine:
1. **Python (3.10 - 3.12)**: Download from [python.org](https://www.python.org/). Check the box **"Add Python to PATH"** during setup.
2. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html). Add its `/bin` directory to your Windows system PATH.

### 3. Add Your NVIDIA API Key
1. Get a free API key with complimentary credits by signing up at [NVIDIA build](https://build.nvidia.com/).
2. In the extracted `Obscura Clips` folder, rename the file `.env.example` to `.env`.
3. Open `.env` in a text editor and add your key:
   ```env
   NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE
   ```

### 4. One-Click Launch
Double-click **`Start Obscura Clips.bat`**. 
- The script will automatically build your local virtual environment (`venv/`), install libraries (including CUDA runtimes), and launch the server.
- The web dashboard will automatically open in your browser at **`http://localhost:7842`**!

---

*Note for Packagers: The virtual environment (`venv/`), intermediate file caches (`temp/`), and final renders (`output/`) are excluded from this release to keep the download size under 10MB.*
```
