#!/bin/bash

# ============================================================
# Lightning Dictation - One-Click Installer
# ============================================================
# This script will set up everything you need to run
# Lightning Dictation on your Mac.
# ============================================================

set -e  # Exit on any error

# Colors for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}       Lightning Dictation - Installer${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}Error: This app only works on macOS.${NC}"
    exit 1
fi

# Check for Apple Silicon
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${RED}Error: This app requires an Apple Silicon Mac (M1/M2/M3/M4).${NC}"
    echo -e "${RED}Your Mac appears to be: $ARCH${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Apple Silicon Mac detected${NC}"

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}Installing to: $SCRIPT_DIR${NC}"
echo ""

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Homebrew not found. Installing Homebrew...${NC}"
    echo -e "${YELLOW}(This is a package manager for macOS that we need to install dependencies)${NC}"
    echo ""
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for this session
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo -e "${GREEN}✓ Homebrew is installed${NC}"
fi

# Install Python 3.10+ if needed
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Installing Python...${NC}"
    brew install python@3.11
else
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}✓ Python $PYTHON_VERSION is installed${NC}"
fi

# Install ffmpeg (needed for audio processing)
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}Installing ffmpeg (for audio processing)...${NC}"
    brew install ffmpeg
else
    echo -e "${GREEN}✓ ffmpeg is installed${NC}"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
else
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo ""
echo -e "${YELLOW}Updating pip...${NC}"
pip install --upgrade pip --quiet

# Install dependencies
echo ""
echo -e "${YELLOW}Installing Python dependencies...${NC}"
echo -e "${YELLOW}(This may take a few minutes on first install)${NC}"
pip install -r requirements.txt --quiet

echo -e "${GREEN}✓ Dependencies installed${NC}"

# Build the app bundle using py2app
echo ""
echo -e "${YELLOW}Building the app...${NC}"

# Install py2app if needed
pip install py2app --quiet

# Clean old builds
rm -rf build dist 2>/dev/null || true

# Build the app in alias mode (links to source, smaller size)
python setup.py py2app --alias --quiet 2>/dev/null || python setup.py py2app --alias

echo -e "${GREEN}✓ App built successfully${NC}"

# Install to Applications folder
echo ""
echo -e "${YELLOW}Would you like to install to your Applications folder? (recommended) (y/n)${NC}"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    # Remove old version if exists
    rm -rf "/Applications/Lightning Dictation.app" 2>/dev/null || true

    cp -R "dist/Lightning Dictation.app" "/Applications/Lightning Dictation.app"
    echo -e "${GREEN}✓ Installed to Applications folder${NC}"
    APP_PATH="/Applications/Lightning Dictation.app"
else
    APP_PATH="$SCRIPT_DIR/dist/Lightning Dictation.app"
    echo -e "${BLUE}App built at: $APP_PATH${NC}"
fi

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}            Installation Complete!${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "${YELLOW}FIRST LAUNCH - What to expect:${NC}"
echo ""
echo "  1. The app will ask for ${BLUE}Accessibility${NC} permission"
echo "     → This lets it detect ⌘ key globally & auto-paste text"
echo "     → Grant access, then restart the app"
echo ""
echo "  2. On your first recording, macOS will ask for ${BLUE}Microphone${NC} access"
echo "     → Click Allow"
echo ""
echo -e "${BLUE}Usage:${NC}"
echo "   • Double-tap ⌘ Command key to start recording"
echo "   • Double-tap again to stop and paste transcription"
echo ""
echo -e "${BLUE}============================================================${NC}"

# Ask if user wants to launch the app now
echo ""
echo -e "${YELLOW}Would you like to launch Lightning Dictation now? (y/n)${NC}"
read -r launch_response
if [[ "$launch_response" =~ ^[Yy]$ ]]; then
    open "$APP_PATH"
    echo -e "${GREEN}App launched! Look for the 🎙️ icon in your menu bar.${NC}"
fi

echo ""
echo -e "${GREEN}Enjoy Lightning Dictation! 🎙️${NC}"
echo ""
