#!/usr/bin/env python3
"""
Lightning Whisper Dictation - Native Mac Menu Bar App
No Terminal window - runs completely in the background
"""

import rumps
import sounddevice as sd
import numpy as np
import tempfile
import wave
import pyperclip
import mlx_whisper
import threading
import os
import sys
import time
import subprocess
import gc
import json
import logging
import mlx.core as mx
from Foundation import NSObject
from PyObjCTools import AppHelper
from AppKit import NSEvent
from Quartz import (
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskSecondaryFn,
)
import objc
import ctypes

# Set up logging for diagnosing intermittent freezes
_log_dir = os.path.expanduser("~/Library/Logs")
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "LightningDictation.log")
logging.basicConfig(
    filename=_log_path,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Keep log file from growing forever: truncate if > 1MB
try:
    if os.path.exists(_log_path) and os.path.getsize(_log_path) > 1_000_000:
        with open(_log_path, 'w') as f:
            f.write("--- Log truncated ---\n")
except:
    pass
log = logging.getLogger("dictation")

# Ensure ffmpeg is in PATH for mlx_whisper
os.environ['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + os.environ.get('PATH', '')


def run_on_main_thread(func):
    """Decorator to ensure a function runs on the main thread"""
    def wrapper(*args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)
        else:
            # Schedule on main thread
            AppHelper.callAfter(func, *args, **kwargs)
    return wrapper


class DictationMenuBarApp(rumps.App):
    def __init__(self):
        super(DictationMenuBarApp, self).__init__(
            "🎙️",
            title="🎙️",
            quit_button=rumps.MenuItem("Quit", key="q")
        )

        # English-only models (optimized for English, smaller and faster)
        self.english_models = {
            "tiny.en": {
                "name": "mlx-community/whisper-tiny.en-mlx",
                "description": "Tiny (fastest, ~40MB RAM, good for quick notes)",
                "size_mb": 75
            },
            "base.en": {
                "name": "mlx-community/whisper-base.en-mlx",
                "description": "Base (fast, ~140MB RAM, good accuracy)",
                "size_mb": 145
            },
            "small.en": {
                "name": "mlx-community/whisper-small.en-mlx",
                "description": "Small (balanced, ~480MB RAM, better accuracy)",
                "size_mb": 485
            },
            "medium.en": {
                "name": "mlx-community/whisper-medium.en-mlx-fp32",
                "description": "Medium (best English, ~1.5GB RAM, highest accuracy) ✓",
                "size_mb": 1530
            }
        }

        # Multilingual models (supports all languages, auto-detects)
        self.multilingual_models = {
            "tiny": {
                "name": "mlx-community/whisper-tiny-mlx",
                "description": "Tiny (fastest, ~40MB RAM, good for quick notes)",
                "size_mb": 75
            },
            "base": {
                "name": "mlx-community/whisper-base-mlx",
                "description": "Base (fast, ~140MB RAM, good accuracy)",
                "size_mb": 145
            },
            "small": {
                "name": "mlx-community/whisper-small-mlx",
                "description": "Small (balanced, ~480MB RAM, better accuracy)",
                "size_mb": 485
            },
            "medium": {
                "name": "mlx-community/whisper-medium-mlx",
                "description": "Medium (slower, ~1.5GB RAM, high accuracy)",
                "size_mb": 1530
            },
            "large-v3": {
                "name": "mlx-community/whisper-large-v3-mlx",
                "description": "Large v3 (slow, ~3GB RAM, best accuracy)",
                "size_mb": 3100
            },
            "distil-large-v3": {
                "name": "mlx-community/distil-whisper-large-v3",
                "description": "Distil Large v3 (6x faster, ~2GB RAM, excellent) ✓",
                "size_mb": 1510
            },
            "turbo": {
                "name": "mlx-community/whisper-large-v3-turbo",
                "description": "Turbo (8x faster, ~1.6GB RAM, great speed/accuracy)",
                "size_mb": 1620
            }
        }

        # Language modes
        self.available_languages = {
            "english": {
                "name": "English Only",
                "description": "English Only (optimized, faster)",
                "models": self.english_models,
                "default_model": "small.en"  # Good balance of speed/accuracy for first-time users
            },
            "multilingual": {
                "name": "Multilingual",
                "description": "Multilingual (auto-detect language)",
                "models": self.multilingual_models,
                "default_model": "distil-large-v3"
            }
        }

        # Settings file path
        self.settings_file = os.path.expanduser("~/.lightning_dictation_settings.json")

        # Load all settings
        self.settings = self.load_settings()

        # Load saved language preference or default to english
        self.current_language = self.settings.get('language', 'english')
        if self.current_language not in self.available_languages:
            self.current_language = 'english'

        # Get the models for current language
        self.available_models = self.available_languages[self.current_language]["models"]

        # Load saved model preference or default based on language
        default_model = self.available_languages[self.current_language]["default_model"]
        self.current_model_key = self.settings.get('model', default_model)
        if self.current_model_key not in self.available_models:
            self.current_model_key = default_model
        self.model_name = self.available_models[self.current_model_key]["name"]

        # Hotkey settings - uses Quartz CGEvent flag masks for NSEvent monitoring
        self.available_hotkeys = {
            "double_cmd": {
                "name": "Double-tap Command",
                "flag_mask": kCGEventFlagMaskCommand,
                "description": "Double-tap ⌘ Command"
            },
            "double_ctrl": {
                "name": "Double-tap Control",
                "flag_mask": kCGEventFlagMaskControl,
                "description": "Double-tap ⌃ Control"
            },
            "double_option": {
                "name": "Double-tap Option",
                "flag_mask": kCGEventFlagMaskAlternate,
                "description": "Double-tap ⌥ Option"
            },
            "double_fn": {
                "name": "Double-tap Fn",
                "flag_mask": kCGEventFlagMaskSecondaryFn,
                "description": "Double-tap Fn"
            }
        }
        # Force default hotkey and mode for now (customization disabled)
        self.current_hotkey = 'double_cmd'
        self.recording_mode = 'toggle'

        # Recording state - use threading.Event for thread-safe flags
        self.is_recording = False
        self.is_transcribing = False
        self.audio_data = []
        self.sample_rate = 16000
        self.stream = None

        # Use RLock (reentrant lock) to prevent deadlocks
        self.state_lock = threading.RLock()

        # Transcription timeout and cancellation
        self.transcription_timeout = 120  # 2 minutes max for transcription
        self.max_recording_duration = 300  # 5 minutes max recording
        self.cancel_transcription = threading.Event()
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self._transcription_started_at = None

        # Double-tap Command key detection
        self.last_cmd_press_time = 0
        self.double_tap_window = 0.3  # 300ms window for double tap
        self.cmd_is_pressed = False
        self._cmd_pressed_at = 0  # timestamp for staleness detection
        self.last_toggle_time = 0
        self.min_toggle_interval = 0.5  # Minimum 500ms between toggles

        # Cooldown after transcription timeout to prevent zombie GPU conflicts
        self._transcription_cooldown_until = 0

        # Menu items
        self.status_item = rumps.MenuItem("Status: Ready")

        # Create hotkey selection submenu
        self.hotkey_menu = rumps.MenuItem("Hotkey")
        for key, info in self.available_hotkeys.items():
            checkmark = "✓ " if key == self.current_hotkey else ""
            menu_item = rumps.MenuItem(
                f"{checkmark}{info['description']}",
                callback=lambda sender, k=key: self.change_hotkey(k)
            )
            self.hotkey_menu.add(menu_item)

        # Create recording mode submenu
        self.mode_menu = rumps.MenuItem("Recording Mode")
        toggle_check = "✓ " if self.recording_mode == "toggle" else ""
        ptt_check = "✓ " if self.recording_mode == "push_to_talk" else ""
        self.mode_menu.add(rumps.MenuItem(
            f"{toggle_check}Toggle (tap to start/stop)",
            callback=lambda _: self.change_recording_mode("toggle")
        ))
        self.mode_menu.add(rumps.MenuItem(
            f"{ptt_check}Push-to-Talk (hold to record)",
            callback=lambda _: self.change_recording_mode("push_to_talk")
        ))

        # Create language selection submenu
        self.language_menu = rumps.MenuItem("Language")
        for key, info in self.available_languages.items():
            checkmark = "✓ " if key == self.current_language else ""
            menu_item = rumps.MenuItem(
                f"{checkmark}{info['description']}",
                callback=lambda sender, k=key: self.change_language(k)
            )
            self.language_menu.add(menu_item)

        # Create model selection submenu
        self.model_menu = rumps.MenuItem("Select Model")
        self._rebuild_model_menu()

        self.menu = [
            self.status_item,
            None,  # Separator
            # Hotkey and recording mode menus hidden for now - will revisit later
            # self.hotkey_menu,
            # self.mode_menu,
            self.language_menu,
            self.model_menu,
            None,  # Separator
            rumps.MenuItem("How to Use", callback=self.show_help),
            rumps.MenuItem("Reset App State", callback=self.reset_app_state)
        ]

        # Set up NSEvent monitors for global hotkey detection
        # Global monitor: catches events when OTHER apps are focused
        # Local monitor: catches events when THIS app is focused
        self._setup_nsevent_monitors()

        # Register for macOS sleep/wake notifications
        self._register_wake_observer()

        # Check permissions and guide user on first launch
        threading.Thread(target=self._check_permissions_on_launch, daemon=True).start()

        # Auto-download default model on first launch for better UX
        threading.Thread(target=self._auto_download_model_if_needed, daemon=True).start()

    def _setup_nsevent_monitors(self):
        """Set up NSEvent global and local monitors for modifier key detection.

        This replaces pynput's keyboard.Listener with native macOS event monitoring,
        which works reliably even when other applications have focus.
        """
        NSFlagsChangedMask = 1 << 12  # NSEventMaskFlagsChanged

        # Global monitor - fires when OTHER apps have focus
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSFlagsChangedMask,
            self._handle_global_flags_event
        )

        # Local monitor - fires when THIS app has focus
        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSFlagsChangedMask,
            self._handle_local_flags_event
        )

        log.info("NSEvent global+local monitors installed for modifier keys")

    def _handle_global_flags_event(self, event):
        """Handle modifier key changes when other apps are focused (global monitor)."""
        try:
            flags = event.modifierFlags()
            self._handle_flags_changed(flags)
        except Exception as e:
            log.warning(f"Global flags handler error: {e}")

    def _handle_local_flags_event(self, event):
        """Handle modifier key changes when this app is focused (local monitor).
        Must return the event to pass it through."""
        try:
            flags = event.modifierFlags()
            self._handle_flags_changed(flags)
        except Exception as e:
            log.warning(f"Local flags handler error: {e}")
        return event

    def _handle_flags_changed(self, flags):
        """Core modifier key press/release detection.

        Called from both global and local NSEvent monitors.
        Detects whether the configured hotkey modifier is pressed or released
        by checking if its flag mask is set in the current modifier flags.
        """
        hotkey_config = self.available_hotkeys.get(self.current_hotkey)
        if not hotkey_config:
            return

        mask = hotkey_config['flag_mask']
        is_pressed = bool(flags & mask)

        if is_pressed and not self.cmd_is_pressed:
            # Modifier key was just pressed
            self._on_hotkey_press()
        elif not is_pressed and self.cmd_is_pressed:
            # Modifier key was just released
            self._on_hotkey_release()

    def _check_permissions_on_launch(self):
        """Check and prompt for required macOS permissions on first launch."""
        time.sleep(1.5)  # Let app finish launching

        trusted = self._is_accessibility_trusted(prompt=True)

        if not trusted:
            log.info("Accessibility permission not yet granted - showing guide")
            AppHelper.callAfter(self._show_permission_dialog)
        else:
            log.info("Accessibility permission already granted")

    def _is_accessibility_trusted(self, prompt=False):
        """Check if app has Accessibility permission. If prompt=True, show macOS system prompt."""
        try:
            # Load AXIsProcessTrustedWithOptions from ApplicationServices
            lib = ctypes.cdll.LoadLibrary(
                '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
            )

            if prompt:
                # Use AXIsProcessTrustedWithOptions to trigger macOS permission prompt
                func = lib.AXIsProcessTrustedWithOptions
                func.restype = ctypes.c_bool
                func.argtypes = [ctypes.c_void_p]

                # Create options dict: {kAXTrustedCheckOptionPrompt: true}
                from Foundation import NSDictionary
                options = NSDictionary.dictionaryWithObject_forKey_(
                    True, "AXTrustedCheckOptionPrompt"
                )
                return func(objc.pyobjc_id(options))
            else:
                # Simple check without prompt
                func = lib.AXIsProcessTrusted
                func.restype = ctypes.c_bool
                return func()
        except Exception as e:
            log.warning(f"Accessibility permission check failed: {e}")
            return True  # Assume OK if check fails

    def _show_permission_dialog(self):
        """Show dialog guiding user to grant required permissions."""
        rumps.alert(
            title="Permissions Required",
            message=(
                "Lightning Dictation needs Accessibility permission to:\n\n"
                "• Detect the ⌘ Command key double-tap globally\n"
                "• Auto-paste transcribed text into any app\n\n"
                "macOS should have shown a permission prompt.\n"
                "If not, open:\n"
                "  System Settings → Privacy & Security → Accessibility\n\n"
                "Add and enable Lightning Dictation, then restart the app.\n\n"
                "Microphone access will be requested when you first record."
            )
        )

    def _on_hotkey_press(self):
        """Handle hotkey press - implements double-tap detection and recording toggle."""
        # Watchdog: auto-reset if stuck transcribing too long
        if self.is_transcribing and self._transcription_started_at:
            stuck_duration = time.time() - self._transcription_started_at
            if stuck_duration > self.transcription_timeout + 30:
                with self.state_lock:
                    self.is_transcribing = False
                    self.cancel_transcription.set()
                    self._transcription_started_at = None
                self.update_ui(title="🎙️", status="Status: Ready (auto-recovered)")

        self.cmd_is_pressed = True
        self._cmd_pressed_at = time.time()
        current_time = time.time()

        if self.recording_mode == "push_to_talk":
            # Push-to-talk: start recording immediately on press
            if current_time - self.last_toggle_time >= self.min_toggle_interval:
                self.last_toggle_time = current_time
                if not self.is_recording and not self.is_transcribing:
                    self.start_recording()
        else:
            # Toggle mode: double-tap to start/stop
            if current_time - self.last_cmd_press_time < self.double_tap_window:
                if current_time - self.last_toggle_time >= self.min_toggle_interval:
                    self.last_toggle_time = current_time

                    if self.is_transcribing:
                        self.cancel_current_transcription()
                    elif self.is_recording:
                        self.stop_recording()
                    else:
                        self.start_recording()

                self.last_cmd_press_time = 0
            else:
                self.last_cmd_press_time = current_time

    def _on_hotkey_release(self):
        """Handle hotkey release - used for push-to-talk mode."""
        self.cmd_is_pressed = False

        # Push-to-talk: stop recording on release
        if self.recording_mode == "push_to_talk":
            if self.is_recording:
                self.stop_recording()

    def is_model_downloaded(self, model_name):
        """Check if a model is already downloaded in the Hugging Face cache"""
        # Convert model name to cache directory format
        # e.g., "mlx-community/distil-whisper-large-v3" -> "models--mlx-community--distil-whisper-large-v3"
        cache_dir_name = "models--" + model_name.replace("/", "--")
        cache_path = os.path.expanduser(f"~/.cache/huggingface/hub/{cache_dir_name}")

        # Check if the directory exists and has a snapshots folder with content
        snapshots_path = os.path.join(cache_path, "snapshots")
        if os.path.exists(snapshots_path):
            # Check if there's at least one snapshot with files
            for snapshot in os.listdir(snapshots_path):
                snapshot_dir = os.path.join(snapshots_path, snapshot)
                if os.path.isdir(snapshot_dir) and os.listdir(snapshot_dir):
                    return True
        return False

    def _auto_download_model_if_needed(self):
        """Auto-download the default model on first launch for better UX"""
        # Small delay to let the app fully initialize
        time.sleep(2)

        # Check if the current model is already downloaded
        if self.is_model_downloaded(self.model_name):
            return

        # Show downloading status
        model_info = self.available_models.get(self.current_model_key, {})
        size_mb = model_info.get("size_mb", 500)
        size_str = f"{size_mb}MB" if size_mb < 1000 else f"{size_mb / 1000:.1f}GB"

        # Show a modal alert that stays on top - user must dismiss it
        AppHelper.callAfter(
            rumps.alert,
            "First-Time Setup",
            f"Downloading AI model ({size_str}).\n\n"
            "This only happens once and may take a minute.\n"
            "The app will be ready when the download icon (⬇️) disappears."
        )

        self.update_ui(title="⬇️", status=f"Status: Downloading model ({size_str})...")

        try:
            # Trigger model download by loading it
            from mlx_whisper.load_models import load_model
            import mlx.core as mx
            load_model(self.model_name, dtype=mx.float16)

            self.update_ui(title="🎙️", status="Status: Ready")

            # Show completion alert
            AppHelper.callAfter(
                rumps.alert,
                "Ready to Dictate!",
                "Model download complete.\n\n"
                "Double-tap ⌘ Command to start recording.\n"
                "Double-tap again to stop and paste."
            )
        except Exception as e:
            self.update_ui(title="🎙️", status="Status: Ready (download on first use)")

    def load_settings(self):
        """Load all settings from settings file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def save_settings(self):
        """Save all settings to settings file"""
        try:
            settings = {
                'language': self.current_language,
                'model': self.current_model_key,
                'hotkey': self.current_hotkey,
                'recording_mode': self.recording_mode
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f)
        except:
            pass

    def _rebuild_model_menu(self):
        """Rebuild the model menu based on current language selection"""
        # Clear existing items (only if menu is initialized)
        try:
            # Use keys() to get item names and remove them one by one
            # This works even before the menu is fully attached
            for item_key in list(self.model_menu.keys()):
                del self.model_menu[item_key]
        except:
            pass

        # Add new items for current language's models
        for key, info in self.available_models.items():
            checkmark = "✓ " if key == self.current_model_key else ""
            menu_item = rumps.MenuItem(
                f"{checkmark}{info['description']}",
                callback=lambda sender, k=key: self.change_model(k)
            )
            self.model_menu.add(menu_item)

    def change_language(self, language_key):
        """Change the language mode and update available models"""
        if language_key == self.current_language:
            return

        # Clear the cached model
        try:
            from mlx_whisper.transcribe import ModelHolder
            ModelHolder.model = None
            ModelHolder.model_path = None
        except:
            pass

        # Update language
        self.current_language = language_key
        self.available_models = self.available_languages[language_key]["models"]

        # Reset to default model for this language
        self.current_model_key = self.available_languages[language_key]["default_model"]
        self.model_name = self.available_models[self.current_model_key]["name"]

        self.save_settings()

        gc.collect()
        try:
            mx.metal.clear_cache()
        except:
            pass

        # Update language menu checkmarks
        for item in self.language_menu.values():
            item_text = str(item)
            if item_text.startswith("✓ "):
                item_text = item_text[2:]
            for key, info in self.available_languages.items():
                if info['description'] in item_text:
                    if key == language_key:
                        item.title = f"✓ {info['description']}"
                    else:
                        item.title = info['description']
                    break

        # Rebuild model menu with new language's models
        self._rebuild_model_menu()

        # Update status to show language changed
        self.update_ui(status=f"Status: Language changed to {self.available_languages[language_key]['name']}")

    @run_on_main_thread
    def update_ui(self, title=None, status=None):
        """Thread-safe UI update - always runs on main thread"""
        if title is not None:
            self.title = title
        if status is not None:
            self.status_item.title = status

    def change_hotkey(self, hotkey_key):
        """Change the hotkey for recording"""
        if hotkey_key == self.current_hotkey:
            return

        self.current_hotkey = hotkey_key
        self.save_settings()

        # Update menu checkmarks
        for item in self.hotkey_menu.values():
            item_text = str(item)
            if item_text.startswith("✓ "):
                item_text = item_text[2:]
            for key, info in self.available_hotkeys.items():
                if info['description'] in item_text:
                    if key == hotkey_key:
                        item.title = f"✓ {info['description']}"
                    else:
                        item.title = info['description']
                    break

        # Update status to show hotkey changed
        self.update_ui(status=f"Status: Hotkey changed to {self.available_hotkeys[hotkey_key]['name']}")

    def change_recording_mode(self, mode):
        """Change between toggle and push-to-talk mode"""
        if mode == self.recording_mode:
            return

        self.recording_mode = mode
        self.save_settings()

        # Update menu checkmarks
        for item in self.mode_menu.values():
            item_text = str(item)
            if item_text.startswith("✓ "):
                item_text = item_text[2:]
            if "Toggle" in item_text:
                if mode == "toggle":
                    item.title = f"✓ Toggle (tap to start/stop)"
                else:
                    item.title = "Toggle (tap to start/stop)"
            elif "Push-to-Talk" in item_text:
                if mode == "push_to_talk":
                    item.title = f"✓ Push-to-Talk (hold to record)"
                else:
                    item.title = "Push-to-Talk (hold to record)"

        mode_name = "Toggle" if mode == "toggle" else "Push-to-Talk"
        # Update status to show mode changed
        self.update_ui(status=f"Status: Mode changed to {mode_name}")

    def change_model(self, model_key):
        """Change the Whisper model"""
        if model_key == self.current_model_key:
            return

        # Clear the cached model
        try:
            from mlx_whisper.transcribe import ModelHolder
            ModelHolder.model = None
            ModelHolder.model_path = None
        except:
            pass

        self.current_model_key = model_key
        self.model_name = self.available_models[model_key]["name"]
        self.save_settings()

        gc.collect()
        try:
            mx.metal.clear_cache()
        except:
            pass

        # Update menu checkmarks
        for item in self.model_menu.values():
            item_text = str(item)
            if item_text.startswith("✓ "):
                item_text = item_text[2:]
            for key, info in self.available_models.items():
                if info['description'] in item_text:
                    if key == model_key:
                        item.title = f"✓ {info['description']}"
                    else:
                        item.title = info['description']
                    break

        # Update status to show model changed
        self.update_ui(status=f"Status: Model changed (loads on next use)")

    def show_help(self, _):
        """Show help dialog"""
        hotkey_name = self.available_hotkeys[self.current_hotkey]['name']
        if self.recording_mode == "toggle":
            mode_text = f"1. {hotkey_name} to start recording\n2. Speak clearly\n3. {hotkey_name} again to stop"
        else:
            mode_text = f"1. Hold {hotkey_name} and speak\n2. Release to stop recording"

        language_text = "English Only" if self.current_language == "english" else "Multilingual"
        rumps.alert(
            title="How to Use Lightning Dictation",
            message=f"{mode_text}\n"
                   "4. Text will auto-paste!\n\n"
                   f"Language: {language_text}\n"
                   "Select Language and Model in the menu.\n"
                   "The app runs silently in your menu bar."
        )

    def reset_app_state(self, _):
        """Reset app state if it gets stuck - runs in background to not block UI"""
        # Immediately show visual feedback
        self.update_ui(title="🔄", status="Status: Resetting...")
        # Run reset in background thread
        threading.Thread(target=self._do_reset, daemon=True).start()

    def _do_reset(self):
        """Actual reset logic in background thread"""
        # Stop any active audio stream first (outside the lock to avoid blocking)
        stream_to_close = None
        with self.state_lock:
            stream_to_close = self.stream
            self.stream = None

        if stream_to_close:
            try:
                stream_to_close.stop()
                stream_to_close.close()
            except:
                pass

        # Now reset all state variables
        with self.state_lock:
            self.audio_data = []
            self.is_recording = False
            self.is_transcribing = False
            self.cancel_transcription.set()
            self.consecutive_failures = 0
            self.cmd_is_pressed = False
            self.last_cmd_press_time = 0
            self.last_toggle_time = 0

        # Clear GPU memory
        try:
            gc.collect()
            mx.metal.clear_cache()
        except:
            pass

        # Clear MLX model cache
        try:
            from mlx_whisper.transcribe import ModelHolder
            ModelHolder.model = None
            ModelHolder.model_path = None
        except:
            pass

        gc.collect()

        # Small delay then update UI
        time.sleep(0.3)
        self.cancel_transcription.clear()
        self.update_ui(title="🎙️", status="Status: Ready")

        # Status already updated above

    def audio_callback(self, indata, frames, time_info, status):
        """Called for each audio chunk during recording"""
        if self.is_recording:
            self.audio_data.append(indata.copy())

            # Check if recording has exceeded max duration
            current_duration = len(self.audio_data) * len(indata) / self.sample_rate
            if current_duration >= self.max_recording_duration:
                threading.Thread(target=self._auto_stop_recording, daemon=True).start()

    def _auto_stop_recording(self):
        """Auto-stop recording when max duration reached"""
        if self.is_recording:
            self.update_ui(status=f"Status: Max duration ({self.max_recording_duration // 60} min) reached")
            self._do_stop_recording()

    def play_sound(self, sound_name):
        """Play system sound for audio feedback"""
        try:
            if sound_name == 'pluck1':
                sound_path = '/System/Library/PrivateFrameworks/AXMediaUtilities.framework/Versions/A/Resources/sounds/pluck1.aiff'
            else:
                sound_path = f'/System/Library/Sounds/{sound_name}.aiff'
            subprocess.run(['afplay', sound_path], check=False, timeout=1)
        except:
            pass

    def start_recording(self):
        """Start recording audio - called from keyboard listener thread"""
        # Check cooldown after a transcription timeout (prevents zombie GPU conflicts)
        if time.time() < self._transcription_cooldown_until:
            self.update_ui(status="Status: Cooling down after timeout...")
            return

        with self.state_lock:
            if self.is_recording or self.is_transcribing:
                return

            self.is_recording = True
            self.audio_data = []

        self.update_ui(title="🔴", status="Status: 🔴 Recording...")

        # Play start sound in background
        threading.Thread(target=lambda: self.play_sound('pluck1'), daemon=True).start()

        # Start audio stream - wrapped in try/except to handle device errors
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                callback=self.audio_callback
            )
            self.stream.start()
        except Exception:
            with self.state_lock:
                self.is_recording = False
                self.audio_data = []
            self.stream = None
            self.update_ui(title="❌", status="Status: Mic error - check audio device")
            self._delayed_ready(3)

    def stop_recording(self):
        """Stop recording - called from keyboard listener thread"""
        threading.Thread(target=self._do_stop_recording, daemon=True).start()

    def _do_stop_recording(self):
        """Actual stop recording logic"""
        with self.state_lock:
            if not self.is_recording:
                return
            if self.is_transcribing:
                return

            self.is_recording = False

        self.update_ui(title="⏳", status="Status: Transcribing...")

        # Play stop sound
        threading.Thread(target=lambda: self.play_sound('Pop'), daemon=True).start()

        # Stop audio stream
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
            self.stream = None

        # Process audio
        self.transcribe_and_paste()

    def _run_transcription(self, temp_path, model_name, result_queue):
        """Run transcription in a separate thread"""
        try:
            result = mlx_whisper.transcribe(
                temp_path,
                path_or_hf_repo=model_name,
                verbose=False,
                word_timestamps=False,
                initial_prompt="Hello, how are you? I'm doing well. Let's get started."
            )
            result_queue.put(('success', result['text'].strip()))
        except Exception as e:
            result_queue.put(('error', str(e)))

    def cancel_current_transcription(self):
        """Cancel the current transcription if one is running"""
        if self.is_transcribing:
            self.cancel_transcription.set()
            self.update_ui(title="🎙️", status="Status: Cancelling...")

    def transcribe_and_paste(self):
        """Transcribe audio and paste to active application"""
        import queue

        with self.state_lock:
            if self.is_transcribing:
                return
            self.is_transcribing = True
            self._transcription_started_at = time.time()
            self.cancel_transcription.clear()

        temp_path = None
        try:
            if not self.audio_data:
                self.update_ui(title="🎙️", status="Status: Ready")
                return

            # Combine all audio chunks
            audio_array = np.concatenate(self.audio_data, axis=0).squeeze()
            self.audio_data = []

            # Check if audio is too short
            if len(audio_array) < self.sample_rate * 0.3:
                self.update_ui(title="🎙️", status="Status: Audio too short")
                self._delayed_ready(2)
                return

            audio_duration = len(audio_array) / self.sample_rate
            if audio_duration > 60:
                self.update_ui(status=f"Status: Transcribing {int(audio_duration)}s audio...")

            # Save to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    audio_int16 = (audio_array * 32767).astype(np.int16)
                    wf.writeframes(audio_int16.tobytes())

            del audio_array
            gc.collect()

            # Check if model needs to be downloaded
            model_needs_download = not self.is_model_downloaded(self.model_name)
            if model_needs_download:
                size_mb = self.available_models[self.current_model_key].get("size_mb", 1500)
                if size_mb >= 1000:
                    size_str = f"{size_mb / 1000:.1f}GB"
                else:
                    size_str = f"{size_mb}MB"
                self.update_ui(title="⬇️", status=f"Status: Downloading model ({size_str})...")

            # Run transcription with timeout
            result_queue = queue.Queue()
            transcription_thread = threading.Thread(
                target=self._run_transcription,
                args=(temp_path, self.model_name, result_queue),
                daemon=True
            )
            transcription_thread.start()

            # Wait for transcription with timeout
            start_time = time.time()
            text = None
            timed_out = False
            download_timeout = 600 if model_needs_download else self.transcription_timeout  # 10 min for download

            while True:
                # Check for cancellation
                if self.cancel_transcription.is_set():
                    self.update_ui(title="🎙️", status="Status: Cancelled")
                    self._delayed_ready(1)
                    return

                elapsed = time.time() - start_time
                if elapsed > download_timeout:
                    timed_out = True
                    break

                try:
                    status, result = result_queue.get(timeout=0.5)
                    if status == 'success':
                        text = result
                    else:
                        raise Exception(result)
                    break
                except queue.Empty:
                    if model_needs_download:
                        # Show download progress indicator
                        dots = "." * (int(elapsed) % 4)
                        self.update_ui(status=f"Status: Downloading model{dots}")
                    elif elapsed > 5:
                        self.update_ui(status=f"Status: Transcribing... ({int(elapsed)}s)")
                    continue

            if timed_out:
                self.consecutive_failures += 1

                # Force-clear MLX model to free GPU resources held by zombie thread
                try:
                    from mlx_whisper.transcribe import ModelHolder
                    ModelHolder.model = None
                    ModelHolder.model_path = None
                except:
                    pass

                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.update_ui(title="⚠️", status="Status: Multiple timeouts - try restarting app")
                else:
                    self.update_ui(title="⚠️", status="Status: Timeout - try shorter recording")

                try:
                    gc.collect()
                    mx.metal.clear_cache()
                except:
                    pass

                # Cooldown to prevent cascading GPU resource conflicts from zombie thread
                self._transcription_cooldown_until = time.time() + 10
                self._delayed_ready(2)
                return

            # Clean up temp file
            if temp_path:
                try:
                    os.unlink(temp_path)
                    temp_path = None
                except:
                    pass

            if text:
                self.consecutive_failures = 0
                # Add trailing space if text ends with punctuation (for sentence-by-sentence dictation)
                if text[-1] in '.!?':
                    text = text + ' '
                pyperclip.copy(text)
                time.sleep(0.15)

                # Paste using AppleScript (must use osascript, pynput crashes on macOS 26 from bg thread)
                try:
                    subprocess.run([
                        'osascript', '-e',
                        'tell application "System Events" to keystroke "v" using command down'
                    ], check=True, timeout=2)
                except Exception as paste_error:
                    # Log paste error but don't crash - text is still in clipboard
                    error_log_path = os.path.expanduser("~/Desktop/dictation_error.log")
                    try:
                        with open(error_log_path, 'a') as f:
                            f.write(f"\n\n=== Paste error at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                            f.write(f"Error: {str(paste_error)}\n")
                            f.write("Text copied to clipboard - paste manually with Cmd+V\n")
                    except:
                        pass

                self.update_ui(title="✅", status=f"Status: Pasted - {text[:30]}...")
                self._delayed_ready(2)
            else:
                self.update_ui(title="🎙️", status="Status: No speech detected")
                self._delayed_ready(2)

            gc.collect()
            try:
                mx.metal.clear_cache()
            except:
                pass

        except Exception as e:
            self.consecutive_failures += 1

            # Log error
            import traceback
            error_log_path = os.path.expanduser("~/Desktop/dictation_error.log")
            try:
                with open(error_log_path, 'a') as f:
                    f.write(f"\n\n=== Error at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.write(f"{str(e)}\n")
                    f.write(traceback.format_exc())
            except:
                pass

            self.update_ui(title="❌", status=f"Status: Error - {str(e)[:30]}")
            self._delayed_ready(3)

            try:
                gc.collect()
                mx.metal.clear_cache()
            except:
                pass

        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except:
                    pass

            with self.state_lock:
                self.is_transcribing = False
                self._transcription_started_at = None

    def _delayed_ready(self, seconds):
        """Update UI to ready state after a delay, in background"""
        def do_delay():
            time.sleep(seconds)
            self.update_ui(title="🎙️", status="Status: Ready")
        threading.Thread(target=do_delay, daemon=True).start()

    def _register_wake_observer(self):
        """Register for macOS sleep/wake notifications to reset key state"""
        try:
            from AppKit import NSWorkspace, NSNotificationCenter
            workspace = NSWorkspace.sharedWorkspace()
            nc = workspace.notificationCenter()

            # NSWorkspaceDidWakeNotification fires when Mac wakes from sleep
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidWakeNotification",
                None,
                None,
                lambda notification: self._on_system_wake()
            )
            # Also listen for screen unlock (covers display sleep without full sleep)
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceScreensDidWakeNotification",
                None,
                None,
                lambda notification: self._on_system_wake()
            )
            log.info("Registered sleep/wake observer")
        except Exception as e:
            log.warning(f"Failed to register wake observer: {e}")

    def _on_system_wake(self):
        """Called when macOS wakes from sleep - reset key state"""
        log.info("System wake detected, resetting key state")
        # Reset stale key state (key events are lost across sleep)
        self.cmd_is_pressed = False
        self.last_cmd_press_time = 0


if __name__ == "__main__":
    if sys.platform != 'darwin':
        print("This app only works on macOS")
        sys.exit(1)

    # Set the process name so macOS displays "Lightning Dictation" instead of "python3"
    from Foundation import NSProcessInfo
    NSProcessInfo.processInfo().setProcessName_("Lightning Dictation")

    app = DictationMenuBarApp()
    app.run()
