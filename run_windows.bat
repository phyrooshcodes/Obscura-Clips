@echo off
title Obscura Clips
color 0A
cls

echo.
echo  +==============================================================+
echo  ^|         *  O B S C U R A   C L I P S  *                    ^|
echo  ^|   Zero-Strain Local-Hybrid AI Video Clipper                  ^|
echo  ^|   Ryzen 7 + RTX 3050  ^|  Llama 3.3 70B  ^|  NVENC            ^|
echo  +==============================================================+
echo.

:: Change to the folder where this bat file lives
cd /d "%~dp0"

:: ── Check Python ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found in PATH.
    echo          Install from https://python.org and re-run.
    pause & exit /b 1
)

:: ── Check FFmpeg ──────────────────────────────────────────
where ffmpeg >nul 2>&1
if errorlevel 1 (
    :: Try the known install location
    if exist "C:\ffmpeg\bin\ffmpeg.exe" (
        set PATH=%PATH%;C:\ffmpeg\bin
    ) else (
        echo  [ERROR] FFmpeg not found. Add C:\ffmpeg\bin to your PATH.
        pause & exit /b 1
    )
)

:: ── Create venv if missing ────────────────────────────────
if not exist "venv\" (
    echo  [SETUP] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 ( echo  [ERROR] Failed to create venv. & pause & exit /b 1 )
)

call venv\Scripts\activate.bat

echo  [SETUP] Checking and verifying package dependencies (this is fast)...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: ── Launch ────────────────────────────────────────────────
echo  [INFO]  Server starting at http://localhost:7842
echo  [INFO]  Browser will open automatically.
echo  [INFO]  Press Ctrl+C to stop.
echo.

python server.py

echo.
echo  [INFO] Server stopped.
pause
exit /b 0
