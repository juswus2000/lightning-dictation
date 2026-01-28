# Lightning Dictation

**Blazing-fast voice-to-text for Mac using on-device AI.**

Lightning Dictation runs entirely on your Mac using Apple Silicon's Neural Engine - no internet required, no subscriptions, completely private.

![Menu Bar Icon](https://img.shields.io/badge/Menu%20Bar-🎙️-blue)
![macOS](https://img.shields.io/badge/macOS-13%2B-green)
![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-M1%2FM2%2FM3%2FM4-orange)

## Features

- **100% Private** - All transcription happens on your device
- **Lightning Fast** - Powered by MLX and Apple Silicon
- **No Internet Required** - Works completely offline
- **Free Forever** - No subscriptions or API costs
- **Multiple Languages** - English optimized + 50+ languages supported
- **Simple to Use** - Just double-tap ⌘ and speak

## Requirements

- **Mac with Apple Silicon** (M1, M2, M3, or M4 chip)
- **macOS 13 (Ventura)** or later
- **~2GB free disk space** (for AI models)

## Quick Install (Recommended)

### One-Command Install

Open Terminal and run:

```bash
git clone https://github.com/juswus2000/lightning-dictation.git
cd Lightning-Dictation
./install.sh
```

That's it! The installer will:
1. Install any missing dependencies (Homebrew, Python, ffmpeg)
2. Set up the Python environment
3. Download required packages
4. Build and optionally install the app

### Grant Permissions

After installation, you need to grant permissions:

1. **Microphone Access**
   - The app will request this automatically on first use
   - Click "Allow" when prompted

2. **Accessibility Access** (Required for auto-paste)
   - Open **System Settings** → **Privacy & Security** → **Accessibility**
   - Click the **+** button
   - Navigate to and select **Lightning Dictation**
   - Make sure the toggle is **ON**

3. **Menu Bar Access** (macOS 26 Tahoe only)
   - Open **System Settings** → **Menu Bar**
   - Find **Lightning Dictation** in the list
   - Enable the toggle

## How to Use

1. **Start the app** - Look for the 🎙️ icon in your menu bar

2. **Record your voice:**
   - **Double-tap** the ⌘ Command key to start recording
   - Speak clearly
   - **Double-tap** ⌘ again to stop

3. **Text appears automatically** - Transcribed text is pasted wherever your cursor is

### Menu Bar Options

Click the 🎙️ icon to access:
- **Language** - Switch between English and Multilingual modes
- **Model** - Choose transcription quality vs speed
- **How to Use** - Quick help
- **Reset App State** - Fix any stuck states

## Models

| Model | Speed | Accuracy | RAM Usage |
|-------|-------|----------|-----------|
| Tiny | Fastest | Good | ~40MB |
| Base | Fast | Better | ~140MB |
| Small | Balanced | Great | ~480MB |
| Medium | Slower | Best | ~1.5GB |
| Large | Slowest | Highest | ~3GB |

The default model (Medium English) offers the best balance for most users.

## Troubleshooting

### App icon doesn't appear in menu bar
- **macOS 26+**: Go to System Settings → Menu Bar and enable Lightning Dictation
- **Older macOS**: Check if too many menu bar icons are hiding it behind the notch

### Text doesn't paste automatically
- Ensure Accessibility permission is granted (see installation steps)
- The text is always copied to clipboard - you can paste manually with ⌘V

### Transcription is slow or stuck
- Click the menu bar icon and select "Reset App State"
- Try a smaller model if you have limited RAM
- Restart the app

### "Lightning Dictation quit unexpectedly"
- Grant both Microphone and Accessibility permissions
- Try removing and re-adding Accessibility permission

## Manual Installation

If you prefer to install manually:

```bash
# Clone the repository
git clone https://github.com/juswus2000/lightning-dictation.git
cd Lightning-Dictation

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build the app
pip install py2app
python setup.py py2app --alias

# Run the app
open "dist/Lightning Dictation.app"
```

## Uninstall

```bash
# Remove from Applications (if installed there)
rm -rf "/Applications/Lightning Dictation.app"

# Remove the project folder
rm -rf ~/path/to/Lightning-Dictation

# Remove settings file
rm ~/.lightning_dictation_settings.json

# Remove cached AI models (optional, frees ~3GB)
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-*
```

## Privacy

Lightning Dictation is designed with privacy as a core principle:

- **No data leaves your Mac** - All processing is local
- **No accounts required** - No sign-up, no tracking
- **No internet needed** - Works in airplane mode
- **Open source** - Audit the code yourself

## Credits

Built with:
- [MLX](https://github.com/ml-explore/mlx) - Apple's machine learning framework
- [Whisper](https://github.com/openai/whisper) - OpenAI's speech recognition model
- [mlx-whisper](https://github.com/ml-explore/mlx-examples) - MLX port of Whisper
- [rumps](https://github.com/jaredks/rumps) - Menu bar app framework

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

If you encounter issues:
1. Check the [Troubleshooting](#troubleshooting) section
2. [Open an issue](https://github.com/juswus2000/lightning-dictation/issues) on GitHub

---

Made with ❤️ for the Mac community
