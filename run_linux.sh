#!/bin/bash
# ─── Linux Setup and Launch ───────────────────────────────────
echo ""
echo " +==============================================================+"
echo " |         *  O B S C U R A   C L I P S  *                    |"
echo " |   Zero-Strain Local-Hybrid AI Video Clipper                  |"
echo " |   Ryzen 7 + RTX 3050  |  Llama 3.3 70B  |  NVENC            |"
echo " +==============================================================+"
echo ""

# Get script's actual directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# ── Force Terminal ──────────────────────────────────────────────
if [ ! -t 1 ]; then
    # Script was run without a terminal (e.g., double-clicked in file manager)
    for term in gnome-terminal konsole xfce4-terminal mate-terminal lxterminal alacritty kitty x-terminal-emulator; do
        if command -v $term &> /dev/null; then
            exec $term -e "$0" "$@"
            exit 0
        fi
    done
fi

# ── Detect OS / Distro ────────────────────────────────────────
OS_TYPE="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
fi

echo "[INFO] Detected OS: $OS_TYPE"

# Helper function to install package if missing
install_package() {
    local pkg=$1
    echo "[SETUP] Installing $pkg..."
    if [ "$OS_TYPE" = "ubuntu" ] || [ "$OS_TYPE" = "debian" ] || [ "$OS_TYPE" = "pop" ] || [ "$OS_TYPE" = "mint" ]; then
        sudo apt-get update && sudo apt-get install -y "$pkg"
    elif [ "$OS_TYPE" = "fedora" ] || [ "$OS_TYPE" = "rhel" ] || [ "$OS_TYPE" = "centos" ]; then
        sudo dnf install -y "$pkg"
    else
        echo "[WARNING] Unknown package manager. Please install '$pkg' manually."
    fi
}

# 1. Check Python3
if ! command -v python3 &> /dev/null; then
    echo "[SETUP] python3 is missing."
    install_package python3
fi

# 2. Check Python3-venv (Ubuntu/Debian splits this)
if [ "$OS_TYPE" = "ubuntu" ] || [ "$OS_TYPE" = "debian" ] || [ "$OS_TYPE" = "pop" ] || [ "$OS_TYPE" = "mint" ]; then
    if ! dpkg -s python3-venv &> /dev/null; then
        echo "[SETUP] python3-venv is missing."
        sudo apt-get update && sudo apt-get install -y python3-venv
    fi
fi

# 3. Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "[SETUP] ffmpeg is missing."
    install_package ffmpeg
fi

# ── Create venv if missing ────────────────────────────────
if [ ! -d "venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create venv."
        exit 1
    fi
fi

echo "[SETUP] Activating virtual environment..."
source venv/bin/activate

echo "[SETUP] Checking and verifying package dependencies (this is fast)..."
pip install --upgrade pip
pip install -r requirements.txt

# ── Launch ────────────────────────────────────────────────
echo "[INFO] Server starting at http://localhost:7842"
echo "[INFO] Browser will open automatically."
echo "[INFO] Press Ctrl+C to stop."
echo ""

python server.py

echo ""
echo "[INFO] Server stopped."
